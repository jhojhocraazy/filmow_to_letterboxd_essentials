import io
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from rich.console import Console

import filmow_to_letterboxd_essentials as app


PAGE = """
<html><body>
<div id="movies-list">
  <li class="movie_list_item"><a class="tip-movie" href="/filme/1">One</a><span class="star-rating" title="Nota: 4.5"></span></li>
  <li class="movie_list_item"><a class="tip-movie" href="/filme/2">Two</a><span class="star-rating" title="Nota: 3.0"></span></li>
</div>
</body></html>
"""


class PerformancePipelineTests(unittest.TestCase):
    def setUp(self):
        self.console_patch = patch.object(
            app, "console", Console(file=io.StringIO(), force_terminal=False)
        )
        self.console_patch.start()

    def tearDown(self):
        self.console_patch.stop()

    def test_default_concurrency_setting_is_five(self):
        self.assertEqual(app.MAX_WORKERS, 5)

    def test_page_pipeline_collects_all_submitted_items(self):
        page = BeautifulSoup(PAGE, "html.parser")
        result = {
            "imdbID": "tt1",
            "tmdbID": "1",
            "type": "movie",
            "filmowRating": "4.5",
            "Rating10": 8.0,
        }
        with patch.object(app, "obter_pagina_blindada", return_value=page), patch.object(
            app, "processar_filme", return_value=result
        ) as process:
            rows, metrics = app.extrair_historico_completo(
                object(), "usuario", {}
            )

        self.assertEqual(process.call_count, 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(metrics["processados"], 2)
        self.assertEqual(metrics["resolvidos"], 2)
        self.assertEqual(metrics["falhas"], 0)

    def test_worker_exception_does_not_abort_other_movies(self):
        page = BeautifulSoup(PAGE, "html.parser")
        resultados = {
            "/filme/1": {
                "imdbID": "tt1",
                "tmdbID": "1",
                "type": "movie",
            }
        }

        def processar(_sessao, url_path, _nota, _ratings):
            if url_path == "/filme/2":
                raise RuntimeError("filme inválido")
            return resultados[url_path]

        with patch.object(app, "obter_pagina_blindada", return_value=page), patch.object(
            app, "processar_filme", side_effect=processar
        ):
            rows, metrics = app.extrair_historico_completo(object(), "usuario", {})

        self.assertEqual([row["imdbID"] for row in rows], ["tt1"])
        self.assertEqual(metrics, {"processados": 2, "resolvidos": 1, "falhas": 1})


if __name__ == "__main__":
    unittest.main()
