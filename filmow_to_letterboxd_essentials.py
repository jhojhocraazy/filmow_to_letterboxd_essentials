import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin

try:
    import cloudscraper
    import requests
    from bs4 import BeautifulSoup
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("Dependências ausentes. Execute: pip install cloudscraper requests beautifulsoup4 rich")
    sys.exit(1)

console = Console()
BASE_URL = "https://filmow.com"

CSV_COLUMNS_ANALITICA = (
    "imdbID",
    "tmdbID",
    "tmdbTitle",
    "tmdbYear",
    "tmdbCountry",
    "tmdbDirectors",
    "filmowTitle",
    "filmowYear",
    "filmowCountry",
    "filmowDirectors",
    "filmowRating"
)

CSV_COLUMNS_SINTETICA = (
    "imdbID",
    "tmdbID"
)

CSV_COLUMNS_LETTERBOXD = (
    "imdbID",
    "tmdbID",
    "filmowRating"
)

CSV_LIMIT = 1900
REQUEST_DELAY = 1.0
MAX_RETRIES = 5

def load_tmdb_key():
    key_path = Path("tmdb_key.txt")
    if key_path.exists():
        with open(key_path, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    console.print("[yellow]Chave da API do TMDb não encontrada localmente.[/yellow]")
    key = input("Insira sua API Key v3 Auth do TMDb: ").strip()
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(key)
    return key

TMDB_API_KEY = load_tmdb_key()

def get_page(session, url, delay=REQUEST_DELAY):
    last_response = None
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        time.sleep(delay)
        try:
            last_response = session.get(url, timeout=30)
            
            if last_response.status_code == 429:
                retry_after = last_response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (2**attempt))
                console.print(f"[yellow]Rate limit atingido, aguardando {wait:.0f}s...[/yellow]")
                time.sleep(wait)
                continue
                
            if last_response.status_code in (500, 502, 503, 504, 520, 521, 522, 524):
                wait = min(60, 3 * (2**attempt))
                console.print(f"[yellow][RETRY] Erro {last_response.status_code} no servidor. Aguardando {wait}s...[/yellow]")
                time.sleep(wait)
                continue

            last_response.raise_for_status()
            return BeautifulSoup(last_response.text, "html.parser")
            
        except requests.exceptions.RequestException as e:
            last_error = e
            wait = min(60, 3 * (2**attempt))
            console.print(f"[yellow][RETRY] Falha de rede ({type(e).__name__}). Aguardando {wait}s...[/yellow]")
            time.sleep(wait)
            
    if last_error:
        raise last_error
    if last_response is not None:
        last_response.raise_for_status()
    raise Exception(f"Falha ao acessar a página após {MAX_RETRIES} tentativas.")

def get_last_page(soup):
    pages = [
        int(page)
        for link in soup.select(".pagination a[href]")
        if (match := re.search(r"pagina=(\d+)", link["href"]))
        for page in [match.group(1)]
    ]
    return max(pages, default=1)

def get_total_movies(session, username, delay=REQUEST_DELAY):
    profile_url = f"{BASE_URL}/usuario/{username}/"
    soup = get_page(session, profile_url, delay=delay)
    for selector, pattern in (
        ('a.movie-list__view-all[href*="/filmes/ja-vi/"] span', r"\((\d+)\)"),
        ('a.movie-list__view-all[href*="/filmes/ja-vi/"]', r"\((\d+)\)"),
    ):
        element = soup.select_one(selector)
        if not element:
            continue
        match = re.search(pattern, element.get_text(strip=True))
        if match:
            return int(match.group(1))
    return None

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

    directors = [
        crew['name'] for crew in data.get('credits', {}).get('crew', []) 
        if crew.get('job') == 'Director' or crew.get('department') == 'Directing'
    ]
    
    if media_type == "tv" and not directors:
        directors = [creator['name'] for creator in data.get('created_by', [])]

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
                if not details:
                    continue
                score = calculate_confidence(details, filmow_data)
                if score > best_score:
                    best_score = score
                    best_candidate = details

    if best_score >= 100 and best_candidate and best_candidate['imdbID']:
        return best_candidate, best_score
    else:
        return None, best_score

def print_visual_block(tmdb_result, filmow_data, route_type):
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Atributo", style="cyan", width=12)
    table.add_column("TMDb (Destino)", style="green")
    table.add_column("Filmow (Origem)", style="dim")

    if tmdb_result:
        if route_type == "JSON-LD":
            border_style = "green"
            title = f"[bold green]✓ IMDb ID Confirmado: {tmdb_result['imdbID']}[/bold green]"
        else:
            border_style = "yellow"
            title = f"[bold yellow]⚠ Fallback Validado: {tmdb_result['imdbID']}[/bold yellow]"

        table.add_row("Título", tmdb_result['tmdbOriginalTitle'], filmow_data['PrimaryTitle'])
        table.add_row("Ano", tmdb_result['tmdbYear'], filmow_data['Year'])
        table.add_row("Diretor", tmdb_result['tmdbDirectors'], filmow_data['Directors'])
        table.add_row("ID TMDb", tmdb_result['tmdbID'], f"Nota: {filmow_data['Rating']}")

        panel = Panel(table, title=title, border_style=border_style, padding=(0, 1))
        console.print(panel)
    else:
        table.add_row("Título", "[red]N/A[/red]", filmow_data['PrimaryTitle'])
        table.add_row("Ano", "[red]N/A[/red]", filmow_data['Year'])
        table.add_row("Diretor", "[red]N/A[/red]", filmow_data['Directors'])
        table.add_row("Status", "[red]Falha na Validação[/red]", f"Nota: {filmow_data['Rating']}")

        panel = Panel(table, title="[bold red]✖ SEM CONFIANÇA NECESSÁRIA[/bold red]", border_style="red", padding=(0, 1))
        console.print(panel)

def get_movie(session, path, rating, delay=REQUEST_DELAY):
    soup = get_page(session, urljoin(BASE_URL, path), delay=delay)
    
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    imdb_id = None
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            same_as = data.get("sameAs", [])
            if isinstance(same_as, str):
                same_as = [same_as]
            for url in same_as:
                match = re.search(r'imdb\.com/title/(tt\d+)', url)
                if match:
                    imdb_id = match.group(1)
                    break
        except json.JSONDecodeError:
            pass
        if imdb_id:
            break

    all_titles = []
    title_element_mb2 = soup.select_one("span.mb-2")
    if title_element_mb2:
        all_titles.append(title_element_mb2.get_text(strip=True))
        
    title_element_h2 = soup.select_one("span.movie__title.fw-semibold.h2")
    if title_element_h2:
        all_titles.append(title_element_h2.get_text(strip=True))

    all_titles = [t for t in all_titles if t]
    if not all_titles:
        raise ValueError("título principal não encontrado")

    primary_title = all_titles[0]

    directors = [link.get_text(strip=True) for link in soup.select(".movie__mobile-directors a")]
    year_element = soup.select_one(".movie__year")
    year_match = re.search(r"\d{4}", year_element.get_text()) if year_element else None
    year = year_match.group() if year_match else ""

    country_links = soup.select("a[href*='/paises/']")
    country = country_links[0].get_text(strip=True) if country_links else ""

    filmow_data = {
        "PrimaryTitle": primary_title,
        "AllTitles": all_titles,
        "Directors": ", ".join(directors),
        "Year": year,
        "Country": country,
        "Rating": rating or ""
    }

    tmdb_result = None
    route_type = None

    if imdb_id:
        find_data = fetch_tmdb(f"/find/{imdb_id}", {"external_source": "imdb_id"})
        if find_data:
            candidate = None
            if find_data.get("movie_results"):
                tmdb_internal_id = find_data["movie_results"][0]["id"]
                candidate = get_tmdb_details(tmdb_internal_id, "movie")
            elif find_data.get("tv_results"):
                tmdb_internal_id = find_data["tv_results"][0]["id"]
                candidate = get_tmdb_details(tmdb_internal_id, "tv")
                
            if candidate:
                score = calculate_confidence(candidate, filmow_data)
                if score >= 40:
                    tmdb_result = candidate
                    route_type = "JSON-LD"
                else:
                    tmdb_result = None
                
    if not tmdb_result:
        tmdb_result, best_score = resolve_tmdb_by_search(filmow_data)
        if tmdb_result:
            route_type = "FALLBACK"

    print_visual_block(tmdb_result, filmow_data, route_type)

    return {
        "imdbID": tmdb_result["imdbID"] if tmdb_result else "",
        "tmdbID": tmdb_result["tmdbID"] if tmdb_result else "",
        "tmdbTitle": tmdb_result["tmdbTitle"] if tmdb_result else "",
        "tmdbYear": tmdb_result["tmdbYear"] if tmdb_result else "",
        "tmdbCountry": tmdb_result["tmdbCountry"] if tmdb_result else "",
        "tmdbDirectors": tmdb_result["tmdbDirectors"] if tmdb_result else "",
        "filmowTitle": filmow_data["PrimaryTitle"],
        "filmowYear": filmow_data["Year"],
        "filmowCountry": filmow_data["Country"],
        "filmowDirectors": filmow_data["Directors"],
        "filmowRating": filmow_data["Rating"]
    }

def get_movies(username, delay=REQUEST_DELAY):
    session = cloudscraper.create_scraper()
    watched_url = f"{BASE_URL}/usuario/{username}/filmes/ja-vi/"
    first_page = get_page(session, watched_url, delay=delay)

    if not first_page.select_one("#movies-list"):
        raise ValueError(f"usuário '{username}' não encontrado ou sem filmes assistidos")

    total_movies = get_total_movies(session, username, delay=delay)
    if total_movies is None:
        raise ValueError(f"não foi possível obter o total de filmes de '{username}'")

    console.print(f"[bold cyan]Usuário {username} encontrado. Total a importar: {total_movies}[/bold cyan]")

    movies = []
    total_pages = get_last_page(first_page)

    for page_number in range(1, total_pages + 1):
        console.print(f"\n[bold magenta]Página {page_number}/{total_pages}[/bold magenta]")
        soup = (
            first_page
            if page_number == 1
            else get_page(session, f"{watched_url}?pagina={page_number}", delay=delay)
        )

        for item in soup.select("#movies-list li.movie_list_item"):
            link = item.select_one("a.tip-movie[href]")
            if not link:
                continue
            rating_element = item.select_one(".star-rating[title]")
            rating_match = (
                re.search(r"Nota: ([0-5](?:\.5)?)", rating_element["title"])
                if rating_element
                else None
            )
            try:
                movie = get_movie(
                    session,
                    link["href"],
                    rating_match.group(1) if rating_match else None,
                    delay=delay,
                )
                movies.append(movie)
            except Exception as error:
                console.print(f"[bold red][ERRO] Falha ao extrair {link['href']}: {error}[/bold red]")

    if not movies:
        raise RuntimeError("nenhum filme foi importado; nenhum CSV foi criado")
    return movies

def write_csv_files(username, movies, modo):
    output_directory = Path.cwd() / "exportacoes"
    output_directory.mkdir(parents=True, exist_ok=True)
    
    if modo == "analitica":
        colunas = CSV_COLUMNS_ANALITICA
    elif modo == "sintetica":
        colunas = CSV_COLUMNS_SINTETICA
    else:
        colunas = CSV_COLUMNS_LETTERBOXD
        
    files = []
    
    chunks = [
        movies[index : index + CSV_LIMIT]
        for index in range(0, len(movies), CSV_LIMIT)
    ]
    
    for number, chunk in enumerate(chunks, start=1):
        suffix = f"-{number}" if len(chunks) > 1 else ""
        filename = f"{username}_{modo}{suffix}.csv"
        path = output_directory / filename
        
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=colunas, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(chunk)
        files.append(path)
        
    return files

def interactive_menu():
    console.clear()
    console.print(Panel("[bold cyan]=== Extrator Filmow -> TMDb/Letterboxd ===[/bold cyan]", expand=False))
    usuario = input("Nome de usuário no Filmow: ").strip().lower()
    while not usuario:
        usuario = input("O nome de usuário não pode ser vazio. Nome no Filmow: ").strip().lower()
        
    console.print("\n[bold]Formatos de Extração:[/bold]")
    console.print("1. Analítica (Todos os metadados)")
    console.print("2. Sintética (Apenas imdbID e tmdbID)")
    console.print("3. Letterboxd Essencial (Apenas imdbID, tmdbID e filmowRating)")
    
    opcao = input("Escolha o formato (1, 2 ou 3): ").strip()
    if opcao == "2":
        modo = "sintetica"
    elif opcao == "3":
        modo = "letterboxd"
    else:
        modo = "analitica"
    
    return usuario, modo

def main():
    parser = argparse.ArgumentParser(description="Exporta filmes assistidos do Filmow reconciliando IDs no TMDb.")
    parser.add_argument("usuario", nargs="?", help="nome de usuário no Filmow")
    parser.add_argument("--modo", choices=["analitica", "sintetica", "letterboxd"], default="analitica", help="formato de exportação do CSV (padrão: analitica)")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="segundos de espera entre requisições (padrão: 1.0)")
    
    args = parser.parse_args()
    
    if args.usuario:
        username = args.usuario.strip().lower()
        modo = args.modo
    else:
        username, modo = interactive_menu()

    console.clear()

    try:
        movies_data = get_movies(username, delay=args.delay)
        files = write_csv_files(username, movies_data, modo)
    except Exception as error:
        console.print(f"[bold red]Erro: {error}[/bold red]")
        return 1

    console.print(f"\n[bold green]Concluído no formato {modo.upper()}:[/bold green]")
    for path in files:
        console.print(path.resolve())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())