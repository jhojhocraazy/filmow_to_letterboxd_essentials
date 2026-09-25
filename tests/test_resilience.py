import io
import unittest
from unittest.mock import Mock, patch

import requests
from bs4 import BeautifulSoup
from rich.console import Console

import filmow_to_letterboxd_essentials as app


HTML = """
<html><body>
<script type="application/ld+json">{"sameAs": "https://www.imdb.com/title/tt0133093/"}</script>
<span class="mb-2">A Matrix</span>
<span class="movie__title fw-semibold h2">Matrix</span>
<div class="movie__year">(1999)</div>
<div class="movie__mobile-directors"><a>Lana Wachowski</a></div>
</body></html>
"""


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.console_patch = patch.object(
            app, "console", Console(file=io.StringIO(), force_terminal=False)
        )
        self.console_patch.start()

    def tearDown(self):
        self.console_patch.stop()

    def test_filmow_retry_does_not_sleep_after_last_attempt(self):
        response = Mock(status_code=503, headers={})
        session = Mock()
        session.get.return_value = response
        sleeps = []
        with patch.object(app, "MAX_RETRIES", 2), patch.object(app.time, "sleep", side_effect=sleeps.append):
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                app.obter_pagina_blindada(session, "https://filmow.com/x", delay=0)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(sleeps, [0, 3])

    def test_filmow_does_not_retry_permanent_client_error(self):
        response = Mock(status_code=404, headers={})
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404", response=response
        )
        session = Mock()
        session.get.return_value = response
        with patch.object(app.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
                app.obter_pagina_blindada(session, "https://filmow.com/x", delay=0)
        self.assertEqual(session.get.call_count, 1)

    def test_processar_filme_extracts_movie_and_validates_json_ld(self):
        page = BeautifulSoup(HTML, "html.parser")
        details = {
            "tmdbID": "603",
            "imdbID": "tt0133093",
            "tmdbTitle": "A Matrix",
            "tmdbOriginalTitle": "The Matrix",
            "tmdbAltTitles": ["Matrix"],
            "tmdbYear": "1999",
            "tmdbCountry": "US",
            "tmdbDirectors": "Lana Wachowski",
        }

        def fake_fetch(endpoint, params=None):
            if endpoint.startswith("/find/"):
                return {"movie_results": [{"id": 603}]}
            return details

        with patch.object(app, "obter_pagina_blindada", return_value=page), patch.object(
            app, "fetch_tmdb", side_effect=fake_fetch
        ), patch.object(
            app, "get_tmdb_details", return_value=details
        ):
            result = app.processar_filme(
                MockSession(), "/filme/a-matrix", "4.5", {"tt0133093": {"rating": 8.2}}
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["imdbID"], "tt0133093")
        self.assertEqual(result["tmdbID"], "603")
        self.assertEqual(result["filmowRating"], "4.5")
        self.assertEqual(result["Rating10"], 8.2)

    def test_json_ld_graph_and_list_are_supported(self):
        html = """
        <script type="application/ld+json">[{"@graph": [
          {"sameAs": ["https://www.imdb.com/title/tt0000001/"]}
        ]}]</script>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(app.extrair_imdb_jsonld(soup), "tt0000001")

    def test_json_ld_null_and_empty_values_do_not_raise(self):
        html = """
        <script type="application/ld+json">{"sameAs": null}</script>
        <script type="application/ld+json"></script>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.assertIsNone(app.extrair_imdb_jsonld(soup))

    def test_processar_filme_preserves_numeric_zero(self):
        page = BeautifulSoup(HTML, "html.parser")
        details = {
            "tmdbID": "603", "imdbID": "tt0133093", "tmdbTitle": "A Matrix",
            "tmdbOriginalTitle": "The Matrix", "tmdbAltTitles": [],
            "tmdbYear": "1999", "tmdbCountry": "US", "tmdbDirectors": "Lana Wachowski",
        }
        with patch.object(app, "obter_pagina_blindada", return_value=page), patch.object(
            app, "fetch_tmdb", return_value={"movie_results": [{"id": 603}]}
        ), patch.object(app, "get_tmdb_details", return_value=details):
            result = app.processar_filme(MockSession(), "/filme/a-matrix", 0, {})
        self.assertEqual(result["filmowRating"], 0)
        self.assertEqual(result["Rating"], 0)

    def test_invalid_json_ld_does_not_prevent_fallback(self):
        page = BeautifulSoup(HTML.replace(
            '{"sameAs": "https://www.imdb.com/title/tt0133093/"}',
            '{invalid json}'
        ), "html.parser")
        details = {
            "tmdbID": "603",
            "imdbID": "tt0133093",
            "tmdbTitle": "A Matrix",
            "tmdbOriginalTitle": "The Matrix",
            "tmdbAltTitles": [],
            "tmdbYear": "1999",
            "tmdbCountry": "US",
            "tmdbDirectors": "Lana Wachowski",
        }
        with patch.object(app, "obter_pagina_blindada", return_value=page), patch.object(
            app, "fetch_tmdb", return_value=details
        ), patch.object(
            app, "resolve_tmdb_by_search", return_value=(details, 110)
        ) as fallback:
            result = app.processar_filme(MockSession(), "/filme/a-matrix", "4.5", {})

        self.assertIsNotNone(result)
        fallback.assert_called_once()


class MockSession:
    pass


if __name__ == "__main__":
    unittest.main()
