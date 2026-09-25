"""CLI ETL para extrair o histórico Filmow e exportar IDs e notas.

O módulo principal orquestra coleta, resolução de identidade e exportação.
As regras puras de matching e o cliente TMDb foram extraídos para módulos
próprios, mas os wrappers locais preservam a interface histórica da aplicação.
"""

import os
import csv
import gzip
import json
import re
import sys
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from identity_matching import calculate_confidence, normalize_text, similarity
from tmdb_client import fetch_tmdb as _fetch_tmdb, get_tmdb_details as _get_tmdb_details

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

try:
    import cloudscraper
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Dependências ausentes. Execute: py -m pip install cloudscraper requests beautifulsoup4 rich")
    sys.exit(1)

# Inicialização de variáveis globais e de interface
console = Console()
BASE_URL = "https://filmow.com"
RATINGS_FILE = Path("title.ratings.tsv.gz")
MAX_RETRIES = 5
DELAY_REQUISICAO = 0.5
TMDB_API_KEY = ""
MAX_WORKERS = 5 # Limite de concorrência para não disparar o WAF (Cloudflare)
# Cache local da execução: evita repetir detalhes do mesmo TMDb ID.
# O lock por ID serializa apenas esse ID; IDs diferentes continuam paralelos.
TMDB_DETAILS_CACHE = {}
TMDB_DETAILS_LOCKS = {}
TMDB_CACHE_LOCK = Lock()
TMDB_CACHE_STATS = {"hits": 0, "misses": 0, "stores": 0}

# Definição estrita de cabeçalhos de exportação por plataforma.
# Os dois contratos Letterboxd são dinâmicos porque a origem escolhida define
# tanto o nome quanto a escala da coluna de avaliação.
COLUNAS_ANALITICA = [
    "imdbID", "tmdbID", "tmdbTitle", "tmdbYear", "tmdbCountry", 
    "tmdbDirectors", "filmowTitle", "filmowYear", "filmowRating", "Rating10"
]
COLUNAS_SINTETICA = ["imdbID", "tmdbID"]
COLUNAS_LETTERBOXD_FILMOW = ["imdbID", "tmdbID", "Rating"]
COLUNAS_LETTERBOXD_IMDB = ["imdbID", "tmdbID", "Rating10"]
# Alias de compatibilidade para integrações e testes que já conhecem o contrato Filmow.
COLUNAS_LETTERBOXD = COLUNAS_LETTERBOXD_FILMOW
ORIGENS_NOTAS_VALIDAS = {"filmow", "imdb"}


def modo_precisa_imdb(modo, origem_nota=None):
    """Informa se o modo selecionado depende do dataset público do IMDb."""
    if modo == "analitica":
        return True
    if modo in {"letterboxd", "trakt"}:
        return origem_nota == "imdb"
    return False


def _validar_origem_nota(modo, origem_nota):
    if modo in {"letterboxd", "trakt"} and origem_nota not in ORIGENS_NOTAS_VALIDAS:
        raise ValueError("Letterboxd e Trakt exigem explicitamente a origem Filmow ou IMDb.")
    return origem_nota


def colunas_exportacao(modo, origem_nota=None):
    """Retorna uma cópia do contrato público correspondente à escolha do usuário."""
    _validar_origem_nota(modo, origem_nota)
    if modo == "analitica":
        return list(COLUNAS_ANALITICA)
    if modo == "sintetica":
        return list(COLUNAS_SINTETICA)
    if modo == "letterboxd":
        return list(
            COLUNAS_LETTERBOXD_FILMOW
            if origem_nota == "filmow"
            else COLUNAS_LETTERBOXD_IMDB
        )
    if modo == "trakt":
        return ["imdb_id", "tmdb_id", "type", "rating"]
    raise ValueError(f"Formato de exportação desconhecido: {modo}")


def _valor_ou_vazio(valor):
    """Preserva zero como nota válida e converte somente ausência real em vazio."""
    return "" if valor is None else valor


def _rating_numerico(valor, minimo, maximo):
    if valor is None or valor == "":
        return None
    try:
        nota = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError):
        return None
    if not nota.is_finite() or nota < minimo or nota > maximo:
        return None
    return nota


def converter_rating_filmow_para_trakt(valor):
    """Converte a nota Filmow 0–5 para 0–10 sem alterar o dado bruto da linha."""
    nota = _rating_numerico(valor, 0, 5)
    if nota is None:
        return ""
    # O Filmow usa meias estrelas. Entradas fora dessa grade são tratadas
    # como inválidas para não inventar um arredondamento não solicitado.
    if (nota * 2) != (nota * 2).to_integral_value():
        return ""
    return f"{nota * 2:.1f}"


def _rating_filmow_exportavel(valor):
    convertido = converter_rating_filmow_para_trakt(valor)
    if convertido == "" and valor not in (None, ""):
        return ""
    return _valor_ou_vazio(valor)


def _rating_imdb_exportavel(valor):
    nota = _rating_numerico(valor, 0, 10)
    if nota is None:
        return ""
    return _valor_ou_vazio(valor)


def preparar_linha_exportacao(linha, modo, origem_nota=None):
    """Deriva somente os campos públicos, sem mutar IDs ou confiança."""
    _validar_origem_nota(modo, origem_nota)
    linha = dict(linha or {})

    if modo == "analitica":
        return {
            "imdbID": linha.get("imdbID", linha.get("imdb_id", "")),
            "tmdbID": linha.get("tmdbID", linha.get("tmdb_id", "")),
            "tmdbTitle": linha.get("tmdbTitle", ""),
            "tmdbYear": linha.get("tmdbYear", ""),
            "tmdbCountry": linha.get("tmdbCountry", ""),
            "tmdbDirectors": linha.get("tmdbDirectors", ""),
            "filmowTitle": linha.get("filmowTitle", ""),
            "filmowYear": linha.get("filmowYear", ""),
            "filmowRating": _rating_filmow_exportavel(linha.get("filmowRating", "")),
            "Rating10": _rating_imdb_exportavel(linha.get("Rating10", linha.get("rating", ""))),
        }

    if modo == "sintetica":
        return {
            "imdbID": linha.get("imdbID", linha.get("imdb_id", "")),
            "tmdbID": linha.get("tmdbID", linha.get("tmdb_id", "")),
        }

    if modo == "letterboxd":
        base = {
            "imdbID": linha.get("imdbID", linha.get("imdb_id", "")),
            "tmdbID": linha.get("tmdbID", linha.get("tmdb_id", "")),
        }
        if origem_nota == "filmow":
            base["Rating"] = _rating_filmow_exportavel(linha.get("filmowRating", linha.get("Rating", "")))
        else:
            base["Rating10"] = _rating_imdb_exportavel(linha.get("Rating10", linha.get("rating", "")))
        return base

    if modo == "trakt":
        resultado = {
            "imdb_id": linha.get("imdbID", linha.get("imdb_id", "")),
            "tmdb_id": linha.get("tmdbID", linha.get("tmdb_id", "")),
            "type": "movie",
            "rating": "",
        }
        if origem_nota == "filmow":
            resultado["rating"] = converter_rating_filmow_para_trakt(
                linha.get("filmowRating", linha.get("Rating", ""))
            )
        else:
            resultado["rating"] = _rating_imdb_exportavel(linha.get("Rating10", linha.get("rating", "")))
        return resultado

    raise ValueError(f"Formato de exportação desconhecido: {modo}")


def _escrever_csv_temporario(caminho, colunas, linhas):
    caminho = Path(caminho)
    temporario = caminho.with_name(f".{caminho.name}.tmp")
    with temporario.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=colunas,
            extrasaction="ignore",
        )
        escritor.writeheader()
        escritor.writerows(linhas)
        arquivo.flush()
        os.fsync(arquivo.fileno())
    return temporario


def _escrever_csv_atomico(nome_arquivo, colunas, linhas):
    """Publica um CSV somente depois de escrevê-lo por completo."""
    caminho = Path(nome_arquivo)
    temporario = _escrever_csv_temporario(caminho, colunas, linhas)
    try:
        os.replace(temporario, caminho)
    finally:
        if temporario.exists():
            temporario.unlink()
    return str(caminho)


def _publicar_par_csv_atomico(pares):
    """Prepara e publica dois CSVs como um conjunto, com recuperação básica."""
    temporarios = []
    backups = []
    publicados = []
    try:
        for caminho, colunas, linhas in pares:
            temporarios.append(_escrever_csv_temporario(caminho, colunas, linhas))
        for caminho, _, _ in pares:
            caminho = Path(caminho)
            if caminho.exists():
                backup = caminho.with_name(f".{caminho.name}.bak.tmp")
                if backup.exists():
                    backup.unlink()
                os.replace(caminho, backup)
                backups.append((backup, caminho))
        for temporario, (caminho, _, _) in zip(temporarios, pares):
            os.replace(temporario, Path(caminho))
            publicados.append(Path(caminho))
    except Exception:
        for publicado in publicados:
            if publicado.exists():
                publicado.unlink()
        for backup, caminho in reversed(backups):
            if backup.exists():
                os.replace(backup, caminho)
        raise
    finally:
        for temporario in temporarios:
            if temporario.exists():
                temporario.unlink()
        for backup, _ in backups:
            if backup.exists():
                backup.unlink()


def _componente_seguro_username(username):
    """Cria um nome de arquivo local sem permitir separadores de caminho."""
    original = str(username or "usuario")
    seguro = "".join(
        caractere if caractere.isalnum() or caractere in "._-" else "_"
        for caractere in original
    ).strip("._")
    return (seguro or "usuario")[:80]


def exportar_linhas(linhas, modo, origem_nota=None, username="usuario", timestamp=None):
    """Gera os arquivos públicos e devolve caminhos e métricas agregadas."""
    colunas = colunas_exportacao(modo, origem_nota)
    linhas = list(linhas or [])
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivos = []
    metricas = {
        "modo": modo,
        "origem_nota": origem_nota or "ambas",
        "linhas": len(linhas),
        "com_nota": 0,
        "sem_nota": 0,
        "notas_invalidas": 0,
    }

    if not linhas:
        return {"arquivos": arquivos, "metricas": metricas}

    preparadas = [preparar_linha_exportacao(linha, modo, origem_nota) for linha in linhas]
    username_arquivo = _componente_seguro_username(username)
    if modo == "trakt":
        nome_history = f"exportacao_history_trakt_{username_arquivo}_{timestamp}.csv"
        nome_ratings = f"exportacao_ratings_trakt_{username_arquivo}_{timestamp}.csv"
        _publicar_par_csv_atomico(
            [
                (nome_history, ["imdb_id", "tmdb_id", "type"], preparadas),
                (nome_ratings, colunas, preparadas),
            ]
        )
        arquivos.extend([nome_history, nome_ratings])
    else:
        nome_arquivo = f"exportacao_{modo}_{username_arquivo}_{timestamp}.csv"
        arquivos.append(_escrever_csv_atomico(nome_arquivo, colunas, preparadas))

    if modo in {"letterboxd", "trakt"}:
        if modo == "trakt":
            campo_nota = "rating"
        elif origem_nota == "filmow":
            campo_nota = "Rating"
        else:
            campo_nota = "Rating10"
        metricas["com_nota"] = sum(1 for linha in preparadas if linha.get(campo_nota, "") != "")
        metricas["sem_nota"] = len(preparadas) - metricas["com_nota"]
        if origem_nota == "filmow":
            metricas["notas_invalidas"] = sum(
                1
                for linha in linhas
                if linha.get("filmowRating", linha.get("Rating", "")) not in (None, "")
                and converter_rating_filmow_para_trakt(
                    linha.get("filmowRating", linha.get("Rating", ""))
                ) == ""
            )
    return {"arquivos": arquivos, "metricas": metricas}

def limpar_tela():
    """Tenta limpar o terminal sem impedir a operação se o shell falhar."""
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
    except OSError:
        pass

def limpar_para_menu():
    """Prepara o terminal para uma nova tela do menu principal."""
    limpar_tela()


def carregar_credencial(nome_arquivo, prompt_msg):
    """
    Função: Lidar com a persistência de chaves de API e sessões.
    Motivo: Evita o recadastramento manual a cada execução. Grava um arquivo de texto local
    que deve ser isolado no .gitignore para impedir vazamentos de segurança no GitHub.
    """
    caminho = Path(nome_arquivo)
    if caminho.exists():
        valor = caminho.read_text(encoding="utf-8").strip()
        if valor:
            return valor
    console.print(f"[yellow]{nome_arquivo} não encontrado ou vazio.[/yellow]")
    valor = input(f"{prompt_msg}: ").strip()
    caminho.write_text(valor, encoding="utf-8")
    console.print(f"[green]Credencial salva em {nome_arquivo} para execuções futuras.[/green]\n")
    return valor

def carregar_datasets_imdb():
    """
    Função: Fazer o download condicional e a alocação em memória (RAM) das notas globais do IMDb.
    Motivo: Operar requisições offline. Se o script batesse na web para buscar a nota de cada filme,
    o tempo de varredura escalaria em minutos adicionais e a Amazon bloquearia o IP por abuso.
    """
    url_ratings = "https://datasets.imdbws.com/title.ratings.tsv.gz"
    if not RATINGS_FILE.exists():
        console.print("[cyan]Baixando base de notas oficial do IMDb (~30MB)...[/cyan]")
        resp = requests.get(url_ratings, stream=True, timeout=60)
        resp.raise_for_status()
        with open(RATINGS_FILE, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)

    ratings_dict = {}
    console.print("[cyan]Indexando avaliações do IMDb na RAM...[/cyan]")
    try:
        with gzip.open(RATINGS_FILE, "rt", encoding="utf-8") as f:
            next(f) # Pula o cabeçalho original
            for linha in f:
                partes = linha.strip().split("\t")
                if len(partes) == 3:
                    ratings_dict[partes[0]] = {"rating": float(partes[1]), "votes": int(partes[2])}
        console.print(f"[green]Índice construído: {len(ratings_dict):,} notas carregadas.[/green]\n")
    except Exception as e:
        console.print(f"[bold red]Erro crítico ao compilar matriz offline: {e}[/bold red]")
        sys.exit(1)
    return ratings_dict

def fetch_tmdb(endpoint, params=None):
    """Preserve the application API while delegating TMDb I/O to the client module."""
    return _fetch_tmdb(endpoint, params, api_key=TMDB_API_KEY, max_retries=MAX_RETRIES)


def get_tmdb_details(tmdb_id):
    """Cache TMDb details and serialize concurrent lookups for the same ID."""
    cache_key = str(tmdb_id)
    with TMDB_CACHE_LOCK:
        cached = TMDB_DETAILS_CACHE.get(cache_key)
        if cached is not None:
            TMDB_CACHE_STATS["hits"] += 1
            return cached
        details_lock = TMDB_DETAILS_LOCKS.setdefault(cache_key, Lock())

    # O segundo check é necessário: outra thread pode ter preenchido o cache
    # enquanto esta thread aguardava o lock específico do TMDb ID.
    with details_lock:
        with TMDB_CACHE_LOCK:
            cached = TMDB_DETAILS_CACHE.get(cache_key)
            if cached is not None:
                TMDB_CACHE_STATS["hits"] += 1
                return cached
            TMDB_CACHE_STATS["misses"] += 1

        details = _get_tmdb_details(tmdb_id, api_key=TMDB_API_KEY, max_retries=MAX_RETRIES)
        if details is not None:
            with TMDB_CACHE_LOCK:
                TMDB_DETAILS_CACHE.setdefault(cache_key, details)
                TMDB_CACHE_STATS["stores"] += 1
        return details


def resolve_tmdb_by_search(filmow_data):
    """
    Função: Mecanismo de Contingência Estrutural (Fallback).
    Motivo: Acionado quando a via rápida falha (o Filmow não tem ID) ou sofre reprovação matemática
    por colisão de série de TV. Dispara busca semântica livre restrita a filmes no TMDb.
    """
    query = filmow_data['PrimaryTitle']
    best_candidate = None
    best_score = -999

    # Força a busca estritamente por filmes para impedir a importação de séries documentais
    results = fetch_tmdb("/search/movie", {"query": query, "language": "pt-BR"})
    if results and results.get('results'):
        candidates = results['results'][:5]
        for item in candidates:
            details = get_tmdb_details(item['id'])
            if not details: continue
            score = calculate_confidence(details, filmow_data)
            # Retém a obra somente se ela se provar a candidata matematicamente superior
            if score > best_score:
                best_score = score
                best_candidate = details

    # O fallback é deliberadamente mais restritivo que o JSON-LD: ele só aceita
    # candidatos com evidências combinadas de título, ano e direção.
    # Limite mínimo de homologação para evitar ancoragem em filmes aleatórios
    if best_score >= 100 and best_candidate and best_candidate['imdbID']:
        return best_candidate, best_score
    return None, best_score

def obter_pagina_blindada(sessao, url, delay=DELAY_REQUISICAO):
    """
    Função: Navegador blindado contra Firewalls (WAF).
    Motivo: Mantém o motor rodando interceptando os Rate Limits do Cloudflare (429) e quedas (502).
    Lê a tag 'Retry-After' no cabeçalho ou aguarda exponencialmente antes da retentativa.
    """
    # O primeiro sleep é intencional: reduz a pressão inicial sobre o WAF.
    ultimo_erro = "nenhuma causa registrada"
    for tentativa in range(MAX_RETRIES):
        if tentativa == 0:
            time.sleep(delay)
        try:
            resposta = sessao.get(url, timeout=30)
            status = resposta.status_code
            if status == 429:
                ultimo_erro = "HTTP 429 (rate limit)"
                if tentativa < MAX_RETRIES - 1:
                    retry_after = resposta.headers.get("Retry-After")
                    espera = (
                        min(60, float(retry_after))
                        if retry_after and retry_after.replace(".", "", 1).isdigit()
                        else min(60, 5 * (2**tentativa))
                    )
                    time.sleep(espera)
                continue

            if 500 <= status < 600:
                ultimo_erro = f"HTTP {status}"
                if tentativa < MAX_RETRIES - 1:
                    time.sleep(min(60, 3 * (2**tentativa)))
                continue

            resposta.raise_for_status()
            return BeautifulSoup(resposta.text, "html.parser")

        except requests.exceptions.HTTPError as erro:
            status = erro.response.status_code if erro.response is not None else "desconhecido"
            if isinstance(status, int) and 400 <= status < 500 and status != 429:
                raise RuntimeError(f"Falha permanente ao acessar {url}: HTTP {status}") from erro
            ultimo_erro = erro
            if tentativa < MAX_RETRIES - 1:
                time.sleep(min(60, 3 * (2**tentativa)))
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as erro:
            ultimo_erro = erro
            if tentativa < MAX_RETRIES - 1:
                time.sleep(min(60, 3 * (2**tentativa)))

    raise RuntimeError(f"Falha ao acessar {url}. Última causa: {ultimo_erro}")

def _iterar_objetos_jsonld(dados):
    """Entrega objetos JSON-LD, inclusive quando a página usa @graph ou listas."""
    if isinstance(dados, dict):
        grafo = dados.get("@graph")
        if isinstance(grafo, list):
            for item in grafo:
                yield from _iterar_objetos_jsonld(item)
        yield dados
    elif isinstance(dados, list):
        for item in dados:
            yield from _iterar_objetos_jsonld(item)


def extrair_imdb_jsonld(soup):
    """Obtém o primeiro ID IMDb de estruturas JSON-LD varied e tolerantes."""
    for script in soup.find_all("script", type="application/ld+json"):
        if not getattr(script, "string", None):
            continue
        try:
            dados = json.loads(script.string)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for objeto in _iterar_objetos_jsonld(dados):
            same_as = objeto.get("sameAs", [])
            if isinstance(same_as, str):
                same_as = [same_as]
            if not isinstance(same_as, list):
                continue
            for valor in same_as:
                if not isinstance(valor, str):
                    continue
                match = re.search(r"imdb\.com/title/(tt\d+)", valor)
                if match:
                    return match.group(1)
    return None


def processar_filme(sessao, url_path, nota_usuario, ratings_dict):
    """
    Função: Core ETL (Extração, Transformação e Carga) operando em Thread isolada.
    Motivo: Vasculha as tripas do HTML da página do filme, extrai metadados estruturados de JSON-LD
    e direciona o fluxo entre o canal Fast-Track e o Fallback, emitindo os valores brutos para o CSV.
    """
    url_completa = urljoin(BASE_URL, url_path)
    sopa = obter_pagina_blindada(sessao, url_completa)
    
    # A extração é isolada para que JSON-LD inesperado apenas desative a via
    # expressa; o pipeline ainda pode tentar o fallback sem perder o filme.
    imdb_id = extrair_imdb_jsonld(sopa)
    # 2. Coleta de atributos secundários para formar a blindagem matemática.
    all_titles = []
    if sopa.select_one("span.mb-2"):
        all_titles.append(sopa.select_one("span.mb-2").get_text(strip=True))
    if sopa.select_one("span.movie__title.fw-semibold.h2"):
        all_titles.append(sopa.select_one("span.movie__title.fw-semibold.h2").get_text(strip=True))

    all_titles = [t for t in all_titles if t]
    primary_title = all_titles[0] if all_titles else "Desconhecido"
    
    directors_list = [link.get_text(strip=True) for link in sopa.select(".movie__mobile-directors a")]
    filmow_directors = ", ".join(directors_list)

    ano_elem = sopa.select_one(".movie__year")
    ano_match = re.search(r"\d{4}", ano_elem.get_text()) if ano_elem else None
    year = ano_match.group() if ano_match else ""

    filmow_data = {
        "PrimaryTitle": primary_title,
        "AllTitles": all_titles,
        "Directors": filmow_directors,
        "Year": year,
        "Rating": "" if nota_usuario is None else nota_usuario
    }

    origem_id = "N/A"
    final_imdb = ""
    final_tmdb = ""
    tmdb_candidate = None

    # 3. Auditoria do ID coletado via JSON-LD
    if imdb_id:
        find_data = fetch_tmdb(f"/find/{imdb_id}", {"external_source": "imdb_id"})
        # Omissão deliberada de tv_results para bloquear séries sumariamente
        if find_data and find_data.get("movie_results"):
            tmdb_candidate_temp = get_tmdb_details(str(find_data["movie_results"][0]["id"]))
            if tmdb_candidate_temp:
                score = calculate_confidence(tmdb_candidate_temp, filmow_data)
                # O limite de corte > 40 impede a absorção de "Tropa de Elite 2" sob o ID do "1"
                if score >= 40:
                    final_tmdb = tmdb_candidate_temp["tmdbID"]
                    final_imdb = tmdb_candidate_temp["imdbID"] or imdb_id
                    tmdb_candidate = tmdb_candidate_temp
                    origem_id = "[green]JSON-LD Validado[/green]"
                else:
                    console.print(f"[dim]Falso positivo ignorado no ID {imdb_id} para '{primary_title}'. Roteando para Fallback...[/dim]")

    # 4. Acionamento de Contingência (Fallback Semântico)
    if not final_imdb or not final_tmdb:
        tmdb_candidate, score = resolve_tmdb_by_search(filmow_data)
        if tmdb_candidate:
            final_imdb = tmdb_candidate["imdbID"]
            final_tmdb = tmdb_candidate["tmdbID"]
            origem_id = "[yellow]Fallback Semântico[/yellow]"

    # A origem é mantida para auditoria e relatórios, mas não é um campo
    # exportado: os cabeçalhos públicos continuam sendo contratos estáveis.
    # 5. Fechamento de Bloco e Retorno de Dicionário Amplo (suporta todos os modelos de CSV)
    if final_imdb and final_tmdb:
        r_info = ratings_dict.get(final_imdb) if ratings_dict else None
        nota_matriz = r_info['rating'] if r_info else ""
        nota_print = (
            f"[bold yellow]{nota_matriz}[/bold yellow]"
            if nota_matriz not in (None, "")
            else "[dim]Sem nota pública[/dim]"
        )
        
        console.print(f"[bold white]{primary_title} ({year})[/bold white] → TMDb: {final_tmdb} | IMDb: {final_imdb} | Origem: {origem_id} | Público: {nota_print}")
        
        return {
            "imdbID": final_imdb,
            "tmdbID": final_tmdb,
            "imdb_id": final_imdb,
            "tmdb_id": final_tmdb,
            "type": "movie", # Topologia estrita para não quebrar o importador do Trakt
            "idOrigin": origem_id.replace("[green]", "").replace("[/green]", "").replace("[yellow]", "").replace("[/yellow]", ""),
            "tmdbTitle": tmdb_candidate["tmdbTitle"] if tmdb_candidate else "",
            "tmdbYear": tmdb_candidate["tmdbYear"] if tmdb_candidate else "",
            "tmdbCountry": tmdb_candidate["tmdbCountry"] if tmdb_candidate else "",
            "tmdbDirectors": tmdb_candidate["tmdbDirectors"] if tmdb_candidate else "",
            "filmowTitle": primary_title,
            "filmowYear": year,
            "filmowRating": "" if nota_usuario is None else nota_usuario,
            "Rating10": nota_matriz,
            "Rating": "" if nota_usuario is None else nota_usuario,
            "rating": nota_matriz
        }
    else:
        console.print(f"[bold red]✖ {primary_title} ({year})[/bold red] → [dim]Falha na resolução de identidade cinematográfica.[/dim]")
        return None

def extrair_historico_completo(sessao, username, ratings_dict):
    """
    Função: Mapeamento topológico e Orquestrador Multithreading.
    Motivo: Identifica o escopo da extração e divide o processamento massivo das páginas
    em threads simultâneas para reduzir varreduras de 40 minutos para médias de 7 minutos.
    """
    url_base = f"{BASE_URL}/usuario/{username}/filmes/ja-vi/"
    primeira_pagina = obter_pagina_blindada(sessao, url_base)
    
    if not primeira_pagina.select_one("#movies-list"):
        raise ValueError(f"Usuário '{username}' não possui histórico público.")

    # Captura a última página da barra de paginação para delimitar o Range
    paginas = [int(m.group(1)) for l in primeira_pagina.select(".pagination a[href]") if (m := re.search(r"pagina=(\d+)", l["href"]))]
    total_paginas = max(paginas, default=1)
    
    console.print(f"[bold green]✓ Perfil mapeado. {total_paginas} páginas de histórico localizadas.[/bold green]\n")

    linhas_csv = []
    metricas = {"processados": 0, "resolvidos": 0, "falhas": 0}
    proximo_indice = 0

    for pagina_atual in range(1, total_paginas + 1):
        console.print(f"\n[bold magenta]=== PÁGINA {pagina_atual}/{total_paginas} (Processamento Concorrente) ===[/bold magenta]")
        url_alvo = url_base if pagina_atual == 1 else f"{url_base}?pagina={pagina_atual}"
        sopa = primeira_pagina if pagina_atual == 1 else obter_pagina_blindada(sessao, url_alvo)
        if not sopa.select_one("#movies-list"):
            raise ValueError(f"A página {pagina_atual} não contém uma lista válida de filmes.")

        itens_grade = sopa.select("#movies-list li.movie_list_item")
        tarefas = []
        indice_por_futuro = {}
        resultados_pagina = {}

        # O executor é recriado por página para limitar o pico de tarefas e
        # manter o WAF dentro do orçamento de requisições configurado.
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for item in itens_grade:
                link_tag = item.select_one("a.tip-movie[href]")
                if not link_tag:
                    continue
                nota_tag = item.select_one(".star-rating[title]")
                nota_match = re.search(r"Nota: ([0-5](?:\.5)?)", nota_tag["title"]) if nota_tag else None
                nota = nota_match.group(1) if nota_match else ""
                metricas["processados"] += 1
                indice = proximo_indice
                proximo_indice += 1
                futuro = executor.submit(processar_filme, sessao, link_tag["href"], nota, ratings_dict)
                tarefas.append(futuro)
                indice_por_futuro[futuro] = indice

            # O consumo continua sendo as_completed(), mas cada resultado guarda
            # o índice original para que a ordem do CSV não dependa da thread.
            for futuro in as_completed(tarefas):
                indice = indice_por_futuro[futuro]
                try:
                    resultado = futuro.result()
                except Exception as erro:
                    metricas["falhas"] += 1
                    console.print(f"[yellow]Falha isolada em um filme: {erro}[/yellow]")
                    continue
                if resultado:
                    resultados_pagina[indice] = resultado
                    metricas["resolvidos"] += 1
                else:
                    metricas["falhas"] += 1

        linhas_csv.extend(resultados_pagina[indice] for indice in sorted(resultados_pagina))

    return linhas_csv, metricas

def exibir_documentacao():
    """Ajuda rápida acompanhada dos detalhes técnicos sem misturar os níveis."""
    doc_texto = """[bold cyan]GUIA RÁPIDO[/bold cyan]
1. Escolha o formato de exportação.
2. Para Letterboxd ou Trakt, escolha a origem das avaliações.
3. Confira o resumo e confirme.
4. Acompanhe o progresso e aguarde a geração dos arquivos.

[bold cyan]CONFIANÇA DE IDENTIDADE[/bold cyan]
O ID coletado no Filmow é auditado pelo TMDb. Se a prova não for suficiente,
o sistema usa busca semântica restrita a filmes. O fallback exige score >= 100.

[bold cyan]FORMATOS[/bold cyan]
→ [bold white]Analítica:[/bold white] IDs, metadados, filmowRating e Rating10.
→ [bold white]Sintética:[/bold white] Somente imdbID e tmdbID.
→ [bold white]Letterboxd:[/bold white] Rating para Filmow ou Rating10 para IMDb.
→ [bold white]Trakt:[/bold white] History sem notas e Ratings com a origem escolhida.

[bold cyan]DESEMPENHO[/bold cyan]
Até cinco filmes são processados simultaneamente. O dataset IMDb é obtido
somente quando o formato selecionado precisa das notas públicas."""
    console.print(Panel.fit(doc_texto, title="[bold white]AJUDA E ARQUITETURA[/bold white]", border_style="blue"))


def exibir_menu_e_obter_selecao():
    """Menu principal com destinos e uma ajuda opcional."""
    menu_texto = """[bold cyan]Qual formato você deseja gerar?[/bold cyan]

[bold white]1.[/bold white] Analítica — metadados, notas do Filmow e do IMDb
[bold white]2.[/bold white] Sintética — somente IDs IMDb e TMDb
[bold white]3.[/bold white] Letterboxd — escolher origem das notas
[bold white]4.[/bold white] Trakt — History sem notas e Ratings separado

[bold white]H.[/bold white] Ajuda
[bold white]0.[/bold white] Sair"""
    console.print(Panel.fit(menu_texto, title="[bold white]FILMOW → LETTERBOXD / TRAKT[/bold white]", border_style="blue"))
    opcoes_map = {
        "1": "analitica",
        "2": "sintetica",
        "3": "letterboxd",
        "4": "trakt",
        "h": "DOC",
    }
    while True:
        escolha = input("\nDigite a opção desejada: ").strip().lower()
        if escolha == "0":
            sys.exit(0)
        if escolha in opcoes_map:
            return opcoes_map[escolha]
        console.print("[red]Opção inválida. Tente novamente.[/red]")


def obter_origem_nota(modo):
    """Pergunta a origem somente quando ela altera o arquivo público."""
    if modo not in {"letterboxd", "trakt"}:
        return None
    if modo == "letterboxd":
        texto = """[bold cyan]Origem das notas do Letterboxd[/bold cyan]
1. Filmow — coluna Rating, escala original 0–5
2. IMDb — coluna Rating10, escala original 0–10
0. Voltar"""
    else:
        texto = """[bold cyan]Origem das notas do Trakt Ratings[/bold cyan]
1. Filmow — nota multiplicada por 2 para a escala 0–10
2. IMDb — nota pública original na escala 0–10
0. Voltar"""
    while True:
        console.print(Panel.fit(texto, title="[bold white]ORIGEM DAS AVALIAÇÕES[/bold white]", border_style="blue"))
        escolha = input("\nDigite a origem desejada: ").strip().lower()
        if escolha == "0":
            return None
        if escolha == "1":
            return "filmow"
        if escolha == "2":
            return "imdb"
        console.print("[red]Origem inválida. Tente novamente.[/red]")


def confirmar_configuracao_exportacao(username, modo, origem_nota=None):
    """Mostra o contrato final e impede iniciar uma varredura ainda não aprovada."""
    origem_texto = "ambas" if modo == "analitica" else ("nenhuma" if modo == "sintetica" else origem_nota)
    colunas = ", ".join(colunas_exportacao(modo, origem_nota))
    texto = f"""[bold]Usuário:[/bold] {escape(username)}
[bold]Formato:[/bold] {escape(modo)}
[bold]Origem das avaliações:[/bold] {escape(origem_texto)}
[bold]Colunas:[/bold] {escape(colunas)}
[bold]Conversão:[/bold] {'Filmow × 2' if modo == 'trakt' and origem_nota == 'filmow' else 'não'}"""
    console.print(Panel.fit(texto, title="[bold white]CONFIRMAR EXPORTAÇÃO[/bold white]", border_style="yellow"))
    while True:
        escolha = input("\n1. Iniciar  2. Voltar ao menu  0. Cancelar: ").strip()
        if escolha == "1":
            return True
        if escolha == "2":
            return False
        if escolha == "0":
            raise KeyboardInterrupt
        console.print("[red]Opção inválida. Tente novamente.[/red]")


def criar_sessao_filmow():
    """Cria a sessão blindada em um ponto injetável para os testes offline."""
    return cloudscraper.create_scraper()


def _gravar_relatorio_atomico(nome_log, relatorio_texto):
    """Publica o relatório somente depois de escrevê-lo por completo."""
    caminho = Path(nome_log)
    temporario = caminho.with_name(f".{caminho.name}.tmp")
    try:
        texto_simples = re.sub(r'\[.*?\]', '', relatorio_texto)
        with temporario.open("w", encoding="utf-8") as arquivo:
            arquivo.write("=== RELATORIO OPERACIONAL FILMOW ===\n")
            arquivo.write(texto_simples)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    finally:
        if temporario.exists():
            temporario.unlink()
    return str(caminho)


def main():
    """Orquestra seleção, execução, exportação e auditoria sem misturar serviços."""
    global TMDB_API_KEY
    limpar_tela()
    TMDB_API_KEY = carregar_credencial("tmdb_api.txt", "Digite sua API Key do TMDb v3")

    # O dataset é caro em startup e memória. Uma vez carregado, pode ser
    # reutilizado quando o usuário alterna entre dois formatos que o exigem.
    ratings_dict = None
    sessao = criar_sessao_filmow()

    try:
        while True:
            modo = exibir_menu_e_obter_selecao()
            if modo == "DOC":
                limpar_para_menu()
                exibir_documentacao()
                console.input("\n[bold cyan]Pressione ENTER para voltar...[/bold cyan]")
                limpar_para_menu()
                continue

            origem_nota = (
                obter_origem_nota(modo)
                if modo in {"letterboxd", "trakt"}
                else None
            )
            if modo in {"letterboxd", "trakt"} and origem_nota is None:
                limpar_para_menu()
                continue

            username = input("\nUsuário público do Filmow: ").strip().lower()
            if not username:
                console.print("[yellow]Operação cancelada: usuário vazio.[/yellow]")
                limpar_para_menu()
                continue
            if not confirmar_configuracao_exportacao(username, modo, origem_nota):
                limpar_para_menu()
                continue

            if modo_precisa_imdb(modo, origem_nota) and ratings_dict is None:
                ratings_dict = carregar_datasets_imdb()
            ratings_da_execucao = ratings_dict or {}

            console.print("\n[cyan]1/4 Preparando recursos...[/cyan]")
            console.print("[cyan]2/4 Lendo o histórico público...[/cyan]")
            console.print("[cyan]3/4 Validando as identidades...[/cyan]")
            inicio = time.time()
            try:
                linhas, metricas = extrair_historico_completo(
                    sessao,
                    username,
                    ratings_da_execucao,
                )
            except KeyboardInterrupt:
                console.print("\n[yellow]Processamento cancelado. Nenhum arquivo final foi publicado.[/yellow]")
                console.input("\n[bold cyan]Pressione ENTER para voltar ao menu...[/bold cyan]")
                limpar_para_menu()
                continue
            except Exception as erro:
                console.print(f"\n[bold red]Erro crítico durante a extração: {erro}[/bold red]")
                console.input("\n[bold cyan]Pressione ENTER para voltar ao menu...[/bold cyan]")
                limpar_para_menu()
                continue

            duracao = time.time() - inicio
            horas, restante = divmod(duracao, 3600)
            minutos, segundos = divmod(restante, 60)
            tempo = f"{int(horas):02d}:{int(minutos):02d}:{int(segundos):02d}"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            console.print("[cyan]4/4 Gerando arquivos...[/cyan]")
            resultado_exportacao = exportar_linhas(
                linhas,
                modo,
                origem_nota,
                username,
                timestamp,
            )
            metricas_exportacao = resultado_exportacao["metricas"]

            relatorio = f"""[bold cyan]Métricas de Execução[/bold cyan]
Tempo Total de Varredura: [bold white]{tempo}[/bold white]
Obras Processadas: [bold white]{metricas['processados']}[/bold white]
Identidades Resolvidas: [bold green]{metricas['resolvidos']}[/bold green]
Falhas de Identidade: [bold red]{metricas['falhas']}[/bold red]
Formato: [bold white]{modo}[/bold white]
Origem das avaliações: [bold white]{metricas_exportacao['origem_nota']}[/bold white]
Linhas exportadas: [bold white]{metricas_exportacao['linhas']}[/bold white]"""
            if modo in {"letterboxd", "trakt"}:
                relatorio += (
                    f"\nCom nota válida: [bold white]{metricas_exportacao['com_nota']}[/bold white]"
                    f"\nSem nota: [bold white]{metricas_exportacao['sem_nota']}[/bold white]"
                    f"\nValores inválidos: [bold white]{metricas_exportacao['notas_invalidas']}[/bold white]"
                )
            if resultado_exportacao["arquivos"]:
                relatorio += "\n\n[bold green]Arquivos gerados:[/bold green]"
                for arquivo in resultado_exportacao["arquivos"]:
                    relatorio += f"\n    → {arquivo}"
            else:
                relatorio += "\n\n[bold yellow]Nenhum CSV foi gerado porque não houve linhas resolvidas.[/bold yellow]"

            nome_log = _gravar_relatorio_atomico(
                f"relatorio_filmow_{timestamp}.txt",
                relatorio,
            )
            relatorio += f"\n\n[bold green]Relatório salvo:[/bold green] {nome_log}"
            console.print(Panel.fit(
                relatorio.strip(),
                title="[bold white]RELATÓRIO OPERACIONAL FILMOW[/bold white]",
                border_style="blue",
            ))
            console.input("\n[bold cyan]Pressione ENTER para voltar ao menu...[/bold cyan]")
            limpar_para_menu()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[cyan]Operação encerrada.[/cyan]")


if __name__ == "__main__":
    main()