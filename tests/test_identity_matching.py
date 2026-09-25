import unittest

from identity_matching import calculate_confidence, normalize_text, similarity


class IdentityMatchingTests(unittest.TestCase):
    def test_normalize_text_removes_accents_case_and_roman_suffix(self):
        self.assertEqual(normalize_text("  Érasington (II)  "), "erasington")

    def test_similarity_identical_titles(self):
        self.assertEqual(similarity("matrix", "matrix"), 1.0)

    def test_exact_title_year_and_director_receive_full_fast_track_score(self):
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
        self.assertEqual(calculate_confidence(candidate, filmow), 100)

    def test_alternative_title_is_accepted_when_metadata_matches(self):
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
        self.assertEqual(calculate_confidence(candidate, filmow), 100)

    def test_empty_director_values_do_not_create_false_confidence(self):
        candidate = {
            "tmdbTitle": "",
            "tmdbOriginalTitle": "",
            "tmdbAltTitles": [],
            "tmdbYear": "",
            "tmdbDirectors": "",
        }
        filmow = {"AllTitles": [], "Year": "", "Directors": ""}
        self.assertEqual(calculate_confidence(candidate, filmow), 0)

    def test_wrong_year_and_director_stay_below_fallback_threshold(self):
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
        self.assertLess(calculate_confidence(candidate, filmow), 100)


if __name__ == "__main__":
    unittest.main()
