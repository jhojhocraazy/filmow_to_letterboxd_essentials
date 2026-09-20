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

console = Console()
BASE_URL = "https://filmow.com"
RATINGS_FILE = Path("title.ratings.tsv.gz")
MAX_RETRIES = 5
DELAY_REQUISICAO = 0.5
TMDB_API_KEY = ""
MAX_WORKERS = 5

COLUNAS_ANALITICA = [
    "imdbID", "tmdbID", "tmdbTitle", "tmdbYear", "tmdbCountry", 
    "tmdbDirectors", "filmowTitle", "filmowYear", "filmowRating", "Rating10"
]
COLUNAS_SINTETICA = ["imdbID", "tmdbID", "Rating10"]
COLUNAS_LETTERBOXD = ["imdbID", "tmdbID", "Rating"]

def limpar_tela():
    os.system('cls' if os.name == 'nt' else 'clear')

def carregar_credencial(nome_arquivo, prompt_msg):
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
            next(f)
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
    if not text:
        return ""
    text = re.sub(r'\s*\([IVXLCDM]+\)\s*', '', text)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    return text.strip().lower()

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def fetch_tmdb(endpoint, params=None):
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

def get_tmdb_details(tmdb_id, media_type="movie"):
    endpoint = f"/{media_type}/{tmdb_id}"
    params = {"append_to_response": "credits,alternative_titles,external_ids", "language": "pt-BR"}
    data = fetch_tmdb(endpoint, params)
    
    if not data:
        return None
    
    if media_type == "movie":
        title = data.get('title', '')
        original_title = data.get('original_title', '')
        release_date = data.get('release_date', '')
        alt_titles_data = data.get('alternative_titles', {}).get('titles', [])
        imdb_id = data.get('imdb_id', '')
    else:
        title = data.get('name', '')
        original_title = data.get('original_name', '')
        release_date = data.get('first_air_date', '')
        alt_titles_data = data.get('alternative_titles', {}).get('results', [])
        imdb_id = data.get('external_ids', {}).get('imdb_id', '')
        
    alt_titles = [item.get('title', '') for item in alt_titles_data]
    directors = [crew['name'] for crew in data.get('credits', {}).get('crew', []) if crew.get('job') == 'Director' or crew.get('department') == 'Directing']
    
    if media_type == "tv" and not directors:
        directors = [creator['name'] for creator in data.get('created_by', [])]

    countries = [c.get('iso_3166_1', '') for c in data.get('production_countries', [])]
    
    return {
        "media_type": media_type,
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
    score = 0
    f_titles = [normalize_text(t) for t in filmow_data['AllTitles']]
    c_titles = [normalize_text(candidate['tmdbTitle']), normalize_text(candidate.get('tmdbOriginalTitle', ''))] + [normalize_text(t) for t in candidate.get('tmdbAltTitles', [])]
    c_titles = [t for t in c_titles if t]
    
    exact_match = False
    partial_match = False
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
    query = filmow_data['PrimaryTitle']
    best_candidate = None
    best_score = -999

    for media_type in ["movie", "tv"]:
        results = fetch_tmdb(f"/search/{media_type}", {"query": query, "language": "pt-BR"})
        if results and results.get('results'):
            candidates = results['results'][:5]
            for item in candidates:
                details = get_tmdb_details(item['id'], media_type)
                if not details: continue
                score = calculate_confidence(details, filmow_data)
                if score > best_score:
                    best_score = score
                    best_candidate = details

    if best_score >= 100 and best_candidate and best_candidate['imdbID']:
        return best_candidate, best_score
    return None, best_score

def obter_pagina_blindada(sessao, url, delay=DELAY_REQUISICAO):
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
    url_completa = urljoin(BASE_URL, url_path)
    sopa = obter_pagina_blindada(sessao, url_completa)
    
    imdb_id = None
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

    origem_id = "N/A"
    final_imdb = ""
    final_tmdb = ""
    tmdb_candidate = None

    if imdb_id:
        find_data = fetch_tmdb(f"/find/{imdb_id}", {"external_source": "imdb_id"})
        if find_data:
            if find_data.get("movie_results"):
                final_tmdb = str(find_data["movie_results"][0]["id"])
                tmdb_candidate = get_tmdb_details(final_tmdb, "movie")
            elif find_data.get("tv_results"):
                final_tmdb = str(find_data["tv_results"][0]["id"])
                tmdb_candidate = get_tmdb_details(final_tmdb, "tv")
                
        if final_tmdb:
            final_imdb = imdb_id
            origem_id = "[green]JSON-LD Fast-Track[/green]"

    if not final_imdb or not final_tmdb:
        filmow_data = {
            "PrimaryTitle": primary_title,
            "AllTitles": all_titles,
            "Directors": filmow_directors,
            "Year": year,
            "Rating": nota_usuario or ""
        }
        
        tmdb_candidate, score = resolve_tmdb_by_search(filmow_data)
        if tmdb_candidate:
            final_imdb = tmdb_candidate["imdbID"]
            final_tmdb = tmdb_candidate["tmdbID"]
            origem_id = "[yellow]Fallback Semântico[/yellow]"

    if final_imdb and final_tmdb:
        r_info = ratings_dict.get(final_imdb)
        nota_matriz = r_info['rating'] if r_info else ""
        nota_print = f"[bold yellow]{nota_matriz}[/bold yellow]" if nota_matriz else "[dim]Sem nota pública[/dim]"
        
        trakt_type = "movie"
        if tmdb_candidate and "media_type" in tmdb_candidate:
            trakt_type = "show" if tmdb_candidate["media_type"] == "tv" else "movie"
            
        console.print(f"[bold white]{primary_title} ({year})[/bold white] → TMDb: {final_tmdb} | IMDb: {final_imdb} | Origem: {origem_id} | Público: {nota_print}")
        
        return {
            "imdbID": final_imdb,             # Key Letterboxd
            "tmdbID": final_tmdb,             # Key Letterboxd
            "imdb_id": final_imdb,            # Key Trakt
            "tmdb_id": final_tmdb,            # Key Trakt
            "type": trakt_type,               # Key Trakt (movie ou show)
            "tmdbTitle": tmdb_candidate["tmdbTitle"] if tmdb_candidate else "",
            "tmdbYear": tmdb_candidate["tmdbYear"] if tmdb_candidate else "",
            "tmdbCountry": tmdb_candidate["tmdbCountry"] if tmdb_candidate else "",
            "tmdbDirectors": tmdb_candidate["tmdbDirectors"] if tmdb_candidate else "",
            "filmowTitle": primary_title,
            "filmowYear": year,
            "filmowRating": nota_usuario or "",
            "Rating10": nota_matriz,          # Key Analitica/Sintetica
            "Rating": nota_usuario or "",     # Key Letterboxd Essencial
            "rating": nota_matriz             # Key Trakt Ratings
        }
    else:
        console.print(f"[bold red]✖ {primary_title} ({year})[/bold red] → [dim]Falha na resolução de identidade.[/dim]")
        return None

def extrair_historico_completo(sessao, username, ratings_dict):
    url_base = f"{BASE_URL}/usuario/{username}/filmes/ja-vi/"
    primeira_pagina = obter_pagina_blindada(sessao, url_base)
    
    if not primeira_pagina.select_one("#movies-list"):
        raise ValueError(f"Usuário '{username}' não possui histórico público.")

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
    doc_texto = """[bold cyan]1. VISÃO GERAL[/bold cyan]
Este script consolida a migração do seu histórico do Filmow para plataformas terceiras. O sistema cruza os metadados 
visuais com o The Movie Database (TMDb) e o Internet Movie Database (IMDb), garantindo alinhamento de chaves.

[bold cyan]2. VIA EXPRESSA (FAST-TRACK JSON-LD)[/bold cyan]
O extrator intercepta a tag furtiva `sameAs` injetada no código-fonte das páginas do Filmow. Quando o ID oficial 
do IMDb está presente, o motor pula a fase de auditoria comparativa (Score) e roteia o dado instantaneamente.

[bold cyan]3. MECANISMO DE CONTINGÊNCIA (FALLBACK)[/bold cyan]
Quando o Filmow não possui a chave matriz registrada, o sistema raspa atributos secundários (título original, ano e diretor) 
e dispara uma Busca Semântica paralela no TMDb. A aprovação só ocorre se o cálculo de identidade ultrapassar 100 pontos.

[bold cyan]4. INTELIGÊNCIA OFFLINE E MULTITHREADING[/bold cyan]
As notas públicas do IMDb são carregadas em RAM (~60MB), erradicando a necessidade de raspar o domínio da Amazon. 
A fila de navegação processa 5 páginas de filmes simultaneamente, acelerando a extração em mais de 80% e respeitando 
o Firewall do Cloudflare (WAF).

[bold cyan]5. OS ARQUIVOS GERADOS[/bold cyan]
Você pode selecionar o formato dinâmico antes de iniciar a extração:
→ [bold white]Analítica:[/bold white] Inventário total para debugar discrepâncias entre títulos originais e traduções.
→ [bold white]Sintética:[/bold white] Estrutura estrita contendo os IDs e a nota global do IMDb (Rating10).
→ [bold white]Letterboxd Essencial:[/bold white] Arquivo formatado para importação do LB, isolando a sua nota pessoal fracionada.
→ [bold white]Trakt.tv:[/bold white] Divide sua grade em dois arquivos (History e Ratings) com as notas públicas do IMDb e 
   topologia à prova de falhas (detecta e marca minisséries como 'show'), impedindo quebras no importador nativo."""
    
    limpar_tela()
    console.print(Panel.fit(doc_texto, title="[bold white]📖 MANUAL DE OPERAÇÃO E ARQUITETURA[/bold white]", border_style="blue"))

def exibir_menu_e_obter_selecao():
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
            else:
                if modo == "analitica":
                    colunas = COLUNAS_ANALITICA
                elif modo == "sintetica":
                    colunas = COLUNAS_SINTETICA
                else:
                    colunas = COLUNAS_LETTERBOXD

                nome_arquivo = f"exportacao_{modo}_{username}_{timestamp}.csv"
                with open(nome_arquivo, mode='w', newline='', encoding='utf-8') as f:
                    escritor = csv.DictWriter(f, fieldnames=colunas, extrasaction='ignore')
                    escritor.writeheader()
                    escritor.writerows(linhas_exportacao)
                    
                relatorio_texto += f"\n[bold green][✓] Arquivo de importação gerado: {nome_arquivo}[/bold green]\n"

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