import gzip
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import filmow_to_letterboxd_essentials as app
import tmdb_client


class IntegrationTests(unittest.TestCase):
    def test_fetch_tmdb_uses_api_key_without_exposing_it(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"ok": True}
        with patch.object(app, "TMDB_API_KEY", "test-key"), patch.object(
            app.requests, "get", return_value=response
        ) as get:
            result = app.fetch_tmdb("/movie/1")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(get.call_args.kwargs["params"]["api_key"], "test-key")

    def test_get_tmdb_details_returns_movie_metadata(self):
        payload = {
            "id": 603,
            "imdb_id": "tt0133093",
            "title": "A Matrix",
            "original_title": "The Matrix",
            "release_date": "1999-03-30",
            "alternative_titles": {"titles": [{"title": "Matrix"}]},
            "credits": {"crew": [{"job": "Director", "name": "Lana Wachowski"}]},
            "production_countries": [{"iso_3166_1": "US"}],
        }
        with patch.object(tmdb_client, "fetch_tmdb", return_value=payload):
            result = app.get_tmdb_details(603)

        self.assertEqual(result["tmdbID"], "603")
        self.assertEqual(result["imdbID"], "tt0133093")
        self.assertEqual(result["tmdbYear"], "1999")
        self.assertEqual(result["tmdbDirectors"], "Lana Wachowski")

    def test_tmdb_details_cache_reuses_successful_lookup(self):
        details = {
            "tmdbID": "603",
            "imdbID": "tt0133093",
            "tmdbTitle": "A Matrix",
            "tmdbYear": "1999",
            "tmdbDirectors": "Lana Wachowski",
        }
        app.TMDB_DETAILS_CACHE.clear()
        app.TMDB_DETAILS_LOCKS.clear()
        app.TMDB_CACHE_STATS.update({"hits": 0, "misses": 0, "stores": 0})
        with patch.object(app, "_get_tmdb_details", return_value=details) as get_details:
            first = app.get_tmdb_details(603)
            second = app.get_tmdb_details(603)

        self.assertIs(first, second)
        get_details.assert_called_once()
        self.assertEqual(app.TMDB_CACHE_STATS, {"hits": 1, "misses": 1, "stores": 1})

    def test_tmdb_details_cache_serializes_same_id_lookups(self):
        details = {
            "tmdbID": "603",
            "imdbID": "tt0133093",
            "tmdbTitle": "A Matrix",
            "tmdbYear": "1999",
            "tmdbDirectors": "Lana Wachowski",
        }
        app.TMDB_DETAILS_CACHE.clear()
        app.TMDB_DETAILS_LOCKS.clear()
        app.TMDB_CACHE_STATS.update({"hits": 0, "misses": 0, "stores": 0})
        with patch.object(app, "_get_tmdb_details", return_value=details) as get_details:
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(app.get_tmdb_details, [603] * 5))

        self.assertTrue(all(result is details for result in results))
        get_details.assert_called_once()
        self.assertEqual(app.TMDB_CACHE_STATS, {"hits": 4, "misses": 1, "stores": 1})

    def test_load_ratings_reads_gzip_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            ratings_file = Path(directory) / "ratings.tsv.gz"
            with gzip.open(ratings_file, "wt", encoding="utf-8") as stream:
                stream.write("tconst\trating\tnumVotes\n")
                stream.write("tt0133093\t8.2\t100\n")
            with patch.object(app, "RATINGS_FILE", ratings_file):
                ratings = app.carregar_datasets_imdb()

        self.assertEqual(ratings["tt0133093"], {"rating": 8.2, "votes": 100})


if __name__ == "__main__":
    unittest.main()
