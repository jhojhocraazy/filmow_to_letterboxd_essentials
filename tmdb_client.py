"""TMDb API client and movie metadata normalization.

O módulo concentra autenticação por parâmetro, política de retry e a
normalização do payload bruto para o dicionário usado pelo matching.
A credencial é recebida por argumento e nunca é registrada.
"""

import time

import requests

BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_MAX_RETRIES = 5
DEFAULT_TIMEOUT = 15
MAX_RETRY_AFTER = 60


def _retry_delay(response, failed_attempt):
    """Return a bounded delay, honoring a numeric ``Retry-After`` header."""
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(max(float(retry_after), 0), MAX_RETRY_AFTER)
        except (TypeError, ValueError):
            pass
    return 2 ** failed_attempt


def fetch_tmdb(endpoint, params=None, api_key="", max_retries=DEFAULT_MAX_RETRIES, sleep=time.sleep):
    """Fetch TMDb JSON while handling rate limits and transient failures."""
    params = dict(params or {})
    params["api_key"] = api_key
    url = f"{BASE_URL}{endpoint}"
    attempts = max(0, max_retries)
    # 429 and every 5xx response is transient. Authentication and missing
    # resource responses are returned immediately rather than retried.
    for attempt in range(attempts):
        response = None
        try:
            response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except (ValueError, requests.exceptions.RequestException):
                    pass
            elif response.status_code != 429 and not 500 <= response.status_code < 600:
                return None
        except requests.exceptions.RequestException:
            pass

        if attempt < attempts - 1:
            sleep(_retry_delay(response, attempt + 1))
    return None


def get_tmdb_details(tmdb_id, api_key="", max_retries=DEFAULT_MAX_RETRIES, sleep=time.sleep):
    """Fetch and normalize metadata from the TMDb movie endpoint."""
    # O endpoint /movie é intencional: ele impede que uma série seja
    # importada como se fosse um filme.
    data = fetch_tmdb(
        f"/movie/{tmdb_id}",
        {"append_to_response": "credits,alternative_titles", "language": "pt-BR"},
        api_key=api_key,
        max_retries=max_retries,
        sleep=sleep,
    )
    if not data:
        return None

    title = data.get("title", "")
    original_title = data.get("original_title", "")
    release_date = data.get("release_date", "")
    alt_titles_data = data.get("alternative_titles", {}).get("titles", [])
    imdb_id = data.get("imdb_id", "")
    alt_titles = [item.get("title", "") for item in alt_titles_data]
    directors = [
        crew["name"]
        for crew in data.get("credits", {}).get("crew", [])
        if crew.get("job") == "Director" or crew.get("department") == "Directing"
    ]
    countries = [country.get("iso_3166_1", "") for country in data.get("production_countries", [])]

    return {
        "tmdbID": str(data.get("id", "")),
        "imdbID": imdb_id,
        "tmdbTitle": title,
        "tmdbOriginalTitle": original_title,
        "tmdbAltTitles": alt_titles,
        "tmdbYear": release_date.split("-")[0] if release_date else "",
        "tmdbCountry": ", ".join(countries),
        "tmdbDirectors": ", ".join(directors),
    }
