"""Pure identity-matching rules used to validate Filmow movie candidates.

Este módulo não faz I/O. Recebe dicionários já extraídos e devolve apenas
a pontuação de confiança, permitindo testar a parte mais sensível do ETL
sem Filmow, TMDb, IMDb ou sistema de arquivos.
"""

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_text(text):
    """Normalize titles and names for conservative comparison."""
    if not text:
        return ""
    # Numeral romano entre parênteses é uma variação editorial recorrente
    # do título e não uma evidência de que as obras sejam diferentes.
    text = re.sub(r"\s*\([IVXLCDM]+\)\s*", "", text)
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
    return text.strip().lower()


def similarity(a, b):
    """Return the identity ratio between two normalized strings."""
    return SequenceMatcher(None, a, b).ratio()


def calculate_confidence(candidate, filmow_data):
    """Score a movie candidate against Filmow metadata."""
    score = 0
    # Títulos normalizados são comparados em conjunto porque a página pode
    # exibir mais de uma nomenclatura regional para a mesma obra.
    f_titles = [normalize_text(t) for t in filmow_data["AllTitles"]]
    c_titles = [normalize_text(candidate["tmdbTitle"]), normalize_text(candidate.get("tmdbOriginalTitle", ""))] + [normalize_text(t) for t in candidate.get("tmdbAltTitles", [])]
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

    # O ano funciona como evidência cruzada: uma obra com mesmo título,
    # mas lançamento incompatível, deve receber forte penalidade.
    c_year = candidate["tmdbYear"]
    f_year = filmow_data["Year"]
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

    # Diretor ausente não pode gerar pontos; comparar duas strings vazias
    # criaria confiança artificial sem evidência real.
    c_dirs = [normalize_text(d) for d in candidate["tmdbDirectors"].split(", ") if normalize_text(d)]
    f_dirs = [normalize_text(d) for d in filmow_data["Directors"].split(", ") if normalize_text(d)]
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
