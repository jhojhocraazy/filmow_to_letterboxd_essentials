import unittest
from unittest.mock import patch

import filmow_to_letterboxd_essentials as app


class ConfidenceTests(unittest.TestCase):
    def test_normalize_text_removes_accents_case_and_roman_suffix(self):
        self.assertEqual(app.normalize_text("  Érasington (II)  "), "erasington")

    def test_similarity_identical_titles(self):
        self.assertEqual(app.similarity("matrix", "matrix"), 1.0)

    def test_exact_title_and_matching_year_director_are_accepted(self):
        filmow = {
            "AllTitles": ["Matrix"],
            "Year": "1999",
            "Directors": "Lana Wachowski, Lilly Wachowski",
        }
        candidate = {
            "tmdbTitle": "Matrix",
            "tmdbOriginalTitle": "The Matrix",
            "tmdbAltTitles": [],
            "tmdbYear": "1999",
            "tmdbDirectors": "Lana Wachowski, Lilly Wachowski",
        }
        self.assertGreaterEqual(app.calculate_confidence(candidate, filmow), 40)

    def test_wrong_year_and_director_are_rejected_by_fallback_threshold(self):
        filmow = {
            "AllTitles": ["Tropa de Elite 2"],
            "Year": "2010",
            "Directors": "José Padilha",
        }
        candidate = {
            "tmdbTitle": "Tropa de Elite",
            "tmdbOriginalTitle": "",
            "tmdbAltTitles": [],
            "tmdbYear": "2007",
            "tmdbDirectors": "José Padilha",
        }
        score = app.calculate_confidence(candidate, filmow)
        self.assertLess(score, 100)

    def test_missing_values_do_not_raise(self):
        candidate = {
            "tmdbTitle": "",
            "tmdbOriginalTitle": "",
            "tmdbAltTitles": [],
            "tmdbYear": "",
            "tmdbDirectors": "",
        }
        filmow = {"AllTitles": [], "Year": "", "Directors": ""}
        self.assertEqual(app.calculate_confidence(candidate, filmow), 0)

    def test_alternative_title_can_produce_a_valid_fast_track_score(self):
        filmow = {
            "AllTitles": ["A Máquina"],
            "Year": "1999",
            "Directors": "Lana Wachowski",
        }
        candidate = {
            "tmdbTitle": "The Matrix",
            "tmdbOriginalTitle": "The Matrix",
            "tmdbAltTitles": ["A Máquina"],
            "tmdbYear": "1999",
            "tmdbDirectors": "Lana Wachowski",
        }
        self.assertEqual(app.calculate_confidence(candidate, filmow), 100)

    def test_resolve_tmdb_rejects_candidate_below_fallback_threshold(self):
        filmow = {
            "PrimaryTitle": "A Máquina",
            "AllTitles": ["A Máquina"],
            "Year": "1999",
            "Directors": "Lana Wachowski",
        }
        weak_candidate = {
            "tmdbID": "1",
            "imdbID": "tt0000001",
            "tmdbTitle": "Filme Diferente",
            "tmdbOriginalTitle": "",
            "tmdbAltTitles": [],
            "tmdbYear": "2001",
            "tmdbCountry": "US",
            "tmdbDirectors": "Outra Pessoa",
        }
        with patch.object(
            app,
            "fetch_tmdb",
            return_value={"results": [{"id": 1}]},
        ), patch.object(app, "get_tmdb_details", return_value=weak_candidate):
            result, score = app.resolve_tmdb_by_search(filmow)

        self.assertIsNone(result)
        self.assertLess(score, 100)

    def test_resolve_tmdb_accepts_candidate_at_fallback_threshold(self):
        filmow = {
            "PrimaryTitle": "A Máquina",
            "AllTitles": ["A Máquina"],
            "Year": "1999",
            "Directors": "Lana Wachowski",
        }
        strong_candidate = {
            "tmdbID": "603",
            "imdbID": "tt0133093",
            "tmdbTitle": "A Máquina",
            "tmdbOriginalTitle": "The Matrix",
            "tmdbAltTitles": [],
            "tmdbYear": "1999",
            "tmdbCountry": "US",
            "tmdbDirectors": "Lana Wachowski",
        }
        with patch.object(
            app,
            "fetch_tmdb",
            return_value={"results": [{"id": 603}]},
        ), patch.object(app, "get_tmdb_details", return_value=strong_candidate):
            result, score = app.resolve_tmdb_by_search(filmow)

        self.assertEqual(result, strong_candidate)
        self.assertGreaterEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
