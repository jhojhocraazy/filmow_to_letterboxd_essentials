import os
import csv
import gzip
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
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

# Definição estrita de cabeçalhos de exportação por plataforma
COLUNAS_ANALITICA = [
    "imdbID", "tmdbID", "tmdbTitle", "tmdbYear", "tmdbCountry", 
    "tmdbDirectors", "filmowTitle", "filmowYear", "filmowRating", "Rating10"
]
COLUNAS_SINTETICA = ["imdbID", "tmdbID", "Rating10"]
COLUNAS_LETTERBOXD = ["imdbID", "tmdbID", "Rating"]

def limpar_tela():
    """Limpa o buffer do terminal compatibilizando chamadas Windows (cls) e Unix (clear)."""
    os.system('cls' if os.name == 'nt' else 'clear')

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

def normalize_text(text):
    """
    Função: Achatar e despoluir strings de títulos de filmes.
    Motivo: Remove acentuação, maiúsculas e numerais romanos injetados (como (I) ou (II)), 
    garantindo que o cálculo matemático de similaridade não reprove homônimos formatados de forma diferente.
    """
    if not text:
        return ""
    text = re.sub(r'\s*\([IVXLCDM]+\)\s*', '', text)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    return text.strip().lower()

def similarity(a, b):
    """Calcula a proporção de identidade (0.0 a 1.0) entre duas strings para sustentar a auditoria semântica."""
    return SequenceMatcher(None, a, b).ratio()

def fetch_tmdb(endpoint, params=None):
    """
    Função: Despachador de requisições centralizado para a API do TMDb.
    Motivo: Isola a injeção da chave de autenticação e trata bloqueios (HTTP 429 - Too Many Requests)
    nativamente com pausas de 2 segundos.
    """
    if params is None:
        params = {}
    params['api_key'] = TMDB_API_KEY
    url = f"https://api.themoviedb.org/3{endpoint}"
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 429:
                time.sleep(2)
                continue
            if response.status_code == 200:
                return response.json()
            return None
        except requests.exceptions.RequestException:
            time.sleep(2)
    return None

def get_tmdb_details(tmdb_id):
    """
    Função: Coletar metadados cinematográficos absolutos usando um ID matriz.
    Motivo: Força o endpoint `/movie` (bloqueando lixo televisivo) e expande os metadados
    trazendo apêndices críticos como `alternative_titles` e a equipe de direção para sustentar a auditoria.
    """
    endpoint = f"/movie/{tmdb_id}"
    params = {"append_to_response": "credits,alternative_titles", "language": "pt-BR"}
    data = fetch_tmdb(endpoint, params)
    
    if not data:
        return None
    
    title = data.get('title', '')
    original_title = data.get('original_title', '')
    release_date = data.get('release_date', '')
    alt_titles_data = data.get('alternative_titles', {}).get('titles', [])
    imdb_id = data.get('imdb_id', '')
        
    alt_titles = [item.get('title', '') for item in alt_titles_data]
    directors = [crew['name'] for crew in data.get('credits', {}).get('crew', []) if crew.get('job') == 'Director' or crew.get('department') == 'Directing']
    countries = [c.get('iso_3166_1', '') for c in data.get('production_countries', [])]
    
    return {
        "tmdbID": str(data.get('id', '')),
        "imdbID": imdb_id,
        "tmdbTitle": title,
        "tmdbOriginalTitle": original_title,
        "tmdbAltTitles": alt_titles,
        "tmdbYear": release_date.split('-')[0] if release_date else "",
        "tmdbCountry": ", ".join(countries),
        "tmdbDirectors": ", ".join(directors)
    }

def calculate_confidence(candidate, filmow_data):
    """
    Função: Auditoria matemática de colisão de dados.
    Motivo: Se o ID recuperado pertencer a uma obra com ano diferente ou diretor não compatível, 
    ele recebe deduções (punição) na pontuação. Isso barra o erro sistêmico do Filmow de atribuir
    o ID do filme "Tropa de Elite 1" na página do "Tropa de Elite 2", por exemplo.
    """
    score = 0
    f_titles = [normalize_text(t) for t in filmow_data['AllTitles']]
    c_titles = [normalize_text(candidate['tmdbTitle']), normalize_text(candidate.get('tmdbOriginalTitle', ''))] + [normalize_text(t) for t in candidate.get('tmdbAltTitles', [])]
    c_titles = [t for t in c_titles if t]
    
    exact_match = False
    partial_match = False
    
    # Avaliação de Títulos (Peso Primário)
    for ft in f_titles:
        if ft in c_titles:
            exact_match = True
            break
        for ct in c_titles:
            if similarity(ft, ct) > 0.8:
                partial_match = True

    if exact_match:
        score += 40
    elif partial_match:
        score += 20

    # Avaliação Temporal (Punição severa se os anos divergirem em mais de 2 anos)
    c_year = candidate['tmdbYear']
    f_year = filmow_data['Year']
    if c_year and f_year:
        try:
            diff = abs(int(c_year) - int(f_year))
            if diff == 0:
                score += 30
            elif diff == 1:
                score += 15
            elif diff > 2:
                score -= 50 
        except ValueError:
            pass

    # Avaliação Diretor (Validação cruzada de assinatura)
    c_dirs = [normalize_text(d) for d in candidate['tmdbDirectors'].split(', ')]
    f_dirs = [normalize_text(d) for d in filmow_data['Directors'].split(', ')]
    if c_dirs and f_dirs:
        dir_match = False
        for cd in c_dirs:
            for fd in f_dirs:
                if cd == fd or similarity(cd, fd) > 0.80 or cd in fd or fd in cd:
                    dir_match = True
                    break
        if dir_match:
            score += 30
        else:
            score -= 20
    return score

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
    ultimo_erro = None
    for tentativa in range(MAX_RETRIES):
        time.sleep(delay)
        try:
            resposta = sessao.get(url, timeout=30)
            if resposta.status_code == 429:
                retry_after = resposta.headers.get("Retry-After")
                espera = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (2**tentativa))
                time.sleep(espera)
                continue
                
            if resposta.status_code in (500, 502, 503, 504, 520, 521, 522, 524):
                espera = min(60, 3 * (2**tentativa))
                time.sleep(espera)
                continue

            resposta.raise_for_status()
            return BeautifulSoup(resposta.text, "html.parser")
            
        except Exception as e:
            ultimo_erro = e
            espera = min(60, 3 * (2**tentativa))
            time.sleep(espera)
            
    raise Exception(f"Falha ao acessar {url}. Erro: {ultimo_erro}")

def processar_filme(sessao, url_path, nota_usuario, ratings_dict):
    """
    Função: Core ETL (Extração, Transformação e Carga) operando em Thread isolada.
    Motivo: Vasculha as tripas do HTML da página do filme, extrai metadados estruturados de JSON-LD
    e direciona o fluxo entre o canal Fast-Track e o Fallback, emitindo os valores brutos para o CSV.
    """
    url_completa = urljoin(BASE_URL, url_path)
    sopa = obter_pagina_blindada(sessao, url_completa)
    
    imdb_id = None
    # 1. Via Expressa de Leitura: Furtividade JSON-LD ignorando quebras de layout
    scripts_json = sopa.find_all("script", type="application/ld+json")
    for script in scripts_json:
        try:
            dados = json.loads(script.string)
            same_as = dados.get("sameAs", [])
            if isinstance(same_as, str): same_as = [same_as]
            for url in same_as:
                match = re.search(r'imdb\.com/title/(tt\d+)', url)
                if match:
                    imdb_id = match.group(1)
                    break
        except json.JSONDecodeError:
            pass
        if imdb_id: break

    # 2. Coleta de Atributos Secundários para formar a blindagem matemática
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
        "Rating": nota_usuario or ""
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

    # 5. Fechamento de Bloco e Retorno de Dicionário Amplo (suporta todos os modelos de CSV)
    if final_imdb and final_tmdb:
        r_info = ratings_dict.get(final_imdb)
        nota_matriz = r_info['rating'] if r_info else ""
        nota_print = f"[bold yellow]{nota_matriz}[/bold yellow]" if nota_matriz else "[dim]Sem nota pública[/dim]"
        
        console.print(f"[bold white]{primary_title} ({year})[/bold white] → TMDb: {final_tmdb} | IMDb: {final_imdb} | Origem: {origem_id} | Público: {nota_print}")
        
        return {
            "imdbID": final_imdb,
            "tmdbID": final_tmdb,
            "imdb_id": final_imdb,
            "tmdb_id": final_tmdb,
            "type": "movie", # Topologia estrita para não quebrar o importador do Trakt
            "tmdbTitle": tmdb_candidate["tmdbTitle"] if tmdb_candidate else "",
            "tmdbYear": tmdb_candidate["tmdbYear"] if tmdb_candidate else "",
            "tmdbCountry": tmdb_candidate["tmdbCountry"] if tmdb_candidate else "",
            "tmdbDirectors": tmdb_candidate["tmdbDirectors"] if tmdb_candidate else "",
            "filmowTitle": primary_title,
            "filmowYear": year,
            "filmowRating": nota_usuario or "",
            "Rating10": nota_matriz,
            "Rating": nota_usuario or "",
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

    for pagina_atual in range(1, total_paginas + 1):
        console.print(f"\n[bold magenta]=== PÁGINA {pagina_atual}/{total_paginas} (Processamento Concorrente) ===[/bold magenta]")
        url_alvo = url_base if pagina_atual == 1 else f"{url_base}?pagina={pagina_atual}"
        sopa = primeira_pagina if pagina_atual == 1 else obter_pagina_blindada(sessao, url_alvo)
        
        itens_grade = sopa.select("#movies-list li.movie_list_item")
        tarefas = []
        
        # Despacho de tarefas paralelas gerenciado pela classe ThreadPoolExecutor nativa
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for item in itens_grade:
                link_tag = item.select_one("a.tip-movie[href]")
                if not link_tag: continue
                    
                nota_tag = item.select_one(".star-rating[title]")
                nota_match = re.search(r"Nota: ([0-5](?:\.5)?)", nota_tag["title"]) if nota_tag else None
                nota = nota_match.group(1) if nota_match else ""
                
                metricas["processados"] += 1
                tarefas.append(executor.submit(processar_filme, sessao, link_tag["href"], nota, ratings_dict))
                
            for futuro in as_completed(tarefas):
                resultado = futuro.result()
                if resultado:
                    linhas_csv.append(resultado)
                    metricas["resolvidos"] += 1
                else:
                    metricas["falhas"] += 1

    return linhas_csv, metricas

def exibir_documentacao():
    """Painel estrutural para orientar operação via CLI."""
    doc_texto = """[bold cyan]1. VISÃO GERAL[/bold cyan]
Este script consolida a migração do seu histórico do Filmow para plataformas terceiras estritamente cinematográficas.
O sistema cruza metadados visuais com o TMDb e o IMDb, garantindo alinhamento de chaves e bloqueando séries de TV.

[bold cyan]2. VIA EXPRESSA (FAST-TRACK JSON-LD) COM AUDITORIA[/bold cyan]
O extrator intercepta a tag furtiva `sameAs` injetada no código-fonte das páginas. Para impedir colisão de falsos positivos 
(como continuações que dividem o mesmo ID genérico no Filmow), o motor submete o ID a uma prova matemática cruzando ano e direção.

[bold cyan]3. MECANISMO DE CONTINGÊNCIA (FALLBACK)[/bold cyan]
Quando o Filmow falha em prover a chave ou provê lixo (IDs televisivos), o sistema raspa os atributos secundários 
e dispara uma Busca Semântica paralela restrita a filmes no TMDb. A aprovação exige grau de confiança estrutural > 100.

[bold cyan]4. INTELIGÊNCIA OFFLINE E MULTITHREADING[/bold cyan]
As notas públicas do IMDb são carregadas em RAM (~30MB), erradicando a necessidade de raspar o domínio da Amazon. 
A fila processa até 5 obras simultaneamente, operando no limite seguro do Firewall do Cloudflare (WAF).

[bold cyan]5. OS ARQUIVOS GERADOS[/bold cyan]
Você pode selecionar o formato dinâmico antes de iniciar a extração:
→ [bold white]Analítica:[/bold white] Inventário total para debugar discrepâncias entre títulos originais e traduções.
→ [bold white]Sintética:[/bold white] Estrutura estrita contendo os IDs e a nota global do IMDb (Rating10).
→ [bold white]Letterboxd Essencial:[/bold white] Arquivo formatado para importação do LB, isolando a sua nota pessoal fracionada.
→ [bold white]Trakt.tv:[/bold white] Divide sua grade em History (marcação) e Ratings (notas públicas), padronizados com 'type: movie'."""
    
    limpar_tela()
    console.print(Panel.fit(doc_texto, title="[bold white]📖 MANUAL DE OPERAÇÃO E ARQUITETURA[/bold white]", border_style="blue"))

def exibir_menu_e_obter_selecao():
    """Menu Interativo de Inicialização."""
    menu_texto = """[bold cyan]Selecione o formato de exportação:[/bold cyan]

[bold white]1.[/bold white] Analítica (Todos os metadados)
[bold white]2.[/bold white] Sintética (imdbID, tmdbID, Rating10 - Notas do IMDb)
[bold white]3.[/bold white] Letterboxd Essencial (imdbID, tmdbID, Rating - Notas do Filmow)
[bold white]4.[/bold white] Trakt.tv (History e Ratings separados - Notas do IMDb)

[bold white]6.[/bold white] [bold green]📖 Documentação e Como Usar[/bold green]

[bold white]0.[/bold white] Sair"""
    
    console.print("\n")
    console.print(Panel.fit(menu_texto.strip(), title="[bold white]MENU DE OPERAÇÃO[/bold white]", border_style="blue"))
    
    opcoes_map = {
        "1": "analitica",
        "2": "sintetica",
        "3": "letterboxd",
        "4": "trakt",
        "6": "DOC"
    }
    
    while True:
        escolha = input("\nDigite o número da opção desejada: ").strip()
        if escolha == "0":
            sys.exit(0)
        if escolha in opcoes_map:
            return opcoes_map[escolha]
        console.print("[red]Opção inválida. Tente novamente.[/red]")

def main():
    """Função Principal: Inicia o ambiente, as constantes em memória e a gravação de discos de telemetria."""
    limpar_tela()
    
    global TMDB_API_KEY
    TMDB_API_KEY = carregar_credencial("tmdb_api.txt", "Digite sua API Key do TMDb v3")
    ratings_dict = carregar_datasets_imdb()
    
    username = input("\nDigite o nome de usuário do Filmow: ").strip().lower()
    if not username:
        sys.exit(0)
        
    sessao = cloudscraper.create_scraper()
    primeira_execucao = True
    
    while True:
        if not primeira_execucao:
            limpar_tela()
        primeira_execucao = False
        
        selecao = exibir_menu_e_obter_selecao()
        
        if selecao == "DOC":
            exibir_documentacao()
            console.input("\n[bold cyan]Pressione ENTER para voltar ao menu inicial...[/bold cyan]")
            continue
            
        modo = selecao
        
        start_time = time.time()
        try:
            console.print(f"\n[cyan]Iniciando varredura integral do perfil {username}...[/cyan]")
            linhas_exportacao, metricas = extrair_historico_completo(sessao, username, ratings_dict)
        except Exception as e:
            console.print(f"\n[bold red]Erro crítico durante a extração: {e}[/bold red]")
            console.input("\n[bold cyan]Pressione ENTER para voltar ao menu inicial...[/bold cyan]")
            continue
            
        # Formatação de cronometragem da operação
        tempo_execucao = time.time() - start_time
        h, rem = divmod(tempo_execucao, 3600)
        m, s = divmod(rem, 60)
        tempo_formatado = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
        
        relatorio_texto = f"""[bold cyan]Métricas de Execução[/bold cyan]
Tempo Total de Varredura: [bold white]{tempo_formatado}[/bold white]
Obras Processadas: [bold white]{metricas['processados']}[/bold white]

[bold cyan]Desempenho de Resolução[/bold cyan]
Identidades Resolvidas (Sucesso): [bold green]{metricas['resolvidos']}[/bold green]
Falhas de Identidade (Omissões): [bold red]{metricas['falhas']}[/bold red]
"""

        if linhas_exportacao:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Sub-rota de isolamento para CSVs compatíveis com Trakt.tv (Divide em 2 arquivos)
            if modo == "trakt":
                nome_arquivo_history = f"exportacao_history_trakt_{username}_{timestamp}.csv"
                with open(nome_arquivo_history, mode='w', newline='', encoding='utf-8') as f:
                    escritor_history = csv.DictWriter(f, fieldnames=["imdb_id", "tmdb_id", "type"], extrasaction='ignore')
                    escritor_history.writeheader()
                    escritor_history.writerows(linhas_exportacao)
                    
                nome_arquivo_ratings = f"exportacao_ratings_trakt_{username}_{timestamp}.csv"
                linhas_com_nota = [linha for linha in linhas_exportacao if linha.get("rating")]
                if linhas_com_nota:
                    with open(nome_arquivo_ratings, mode='w', newline='', encoding='utf-8') as f:
                        escritor_ratings = csv.DictWriter(f, fieldnames=["imdb_id", "tmdb_id", "type", "rating"], extrasaction='ignore')
                        escritor_ratings.writeheader()
                        escritor_ratings.writerows(linhas_com_nota)
                
                relatorio_texto += "\n[bold green][✓] Arquivos de exportação gerados (Trakt.tv):[/bold green]\n"
                relatorio_texto += f"    → {nome_arquivo_history} ([bold white]{len(linhas_exportacao)}[/bold white] check-ins)\n"
                if linhas_com_nota:
                    relatorio_texto += f"    → {nome_arquivo_ratings} ([bold white]{len(linhas_com_nota)}[/bold white] avaliações)\n"
            
            # Rota nativa Letterboxd / Analítica
            else:
                if modo == "analitica":
                    colunas = COLUNAS_ANALITICA
                elif modo == "sintetica":
                    colunas = COLUNAS_SINTETICA
                else:
                    colunas = COLUNAS_LETTERBOXD

                nome_arquivo = f"exportacao_{modo}_{username}_{timestamp}.csv"
                with open(nome_arquivo, mode='w', newline='', encoding='utf-8') as f:
                    # 'extrasaction=ignore' dropa as chaves do dicionário que não pertencem ao formato alvo
                    escritor = csv.DictWriter(f, fieldnames=colunas, extrasaction='ignore')
                    escritor.writeheader()
                    escritor.writerows(linhas_exportacao)
                    
                relatorio_texto += f"\n[bold green][✓] Arquivo de importação gerado: {nome_arquivo}[/bold green]\n"

            # Gravação de relatório em texto puro (Remove tags rich para txt via Regex)
            nome_log = f"relatorio_filmow_{timestamp}.txt"
            with open(nome_log, "w", encoding="utf-8") as f:
                f.write("=== RELATORIO OPERACIONAL FILMOW ===\n")
                f.write(re.sub(r'\[.*?\]', '', relatorio_texto))
                
            relatorio_texto += f"[bold green][✓] Log salvo para consulta:[/bold green] {nome_log}\n"

        console.print("\n")
        console.print(Panel.fit(relatorio_texto.strip(), title="[bold white]RELATÓRIO OPERACIONAL FILMOW[/bold white]", border_style="blue"))
        
        console.input("\n[bold cyan]Pressione ENTER para voltar ao menu inicial...[/bold cyan]")

if __name__ == "__main__":
    main()