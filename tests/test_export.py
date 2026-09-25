import csv
import os
import tempfile
import unittest
from unittest.mock import patch
from decimal import Decimal
from pathlib import Path

import filmow_to_letterboxd_essentials as app


ANALYTIC_COLUMNS = [
    "imdbID",
    "tmdbID",
    "tmdbTitle",
    "tmdbYear",
    "tmdbCountry",
    "tmdbDirectors",
    "filmowTitle",
    "filmowYear",
    "filmowRating",
    "Rating10",
]
SYNTHETIC_COLUMNS = ["imdbID", "tmdbID"]
LETTERBOXD_FILMOW_COLUMNS = ["imdbID", "tmdbID", "Rating"]
LETTERBOXD_IMDB_COLUMNS = ["imdbID", "tmdbID", "Rating10"]
TRAKT_HISTORY_COLUMNS = ["imdb_id", "tmdb_id", "type"]
TRAKT_RATINGS_COLUMNS = ["imdb_id", "tmdb_id", "type", "rating"]


def sample_row(**overrides):
    row = {
        "imdbID": "tt0000001",
        "tmdbID": "42",
        "tmdbTitle": "Matrix, The",
        "tmdbYear": "1999",
        "tmdbCountry": "US",
        "tmdbDirectors": "Lana, Lilly Wachowski",
        "filmowTitle": "A Matrix",
        "filmowYear": "1999",
        "filmowRating": "4.5",
        "Rating10": "8.2",
        # Deliberate internal aliases and unrelated data must never leak.
        "Rating": "4.5",
        "rating": "8.2",
        "imdb_id": "tt-internal",
        "tmdb_id": "999",
        "idOrigin": "Fallback Semântico",
    }
    row.update(overrides)
    return row


def read_csv(path):
    with Path(path).open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class ExportContractTests(unittest.TestCase):
    def test_modo_precisa_imdb_respects_origin_and_mode(self):
        # Synthetic has IDs, but no longer needs an IMDb rating.
        self.assertFalse(app.modo_precisa_imdb("sintetica", "imdb"))
        self.assertFalse(app.modo_precisa_imdb("sintetica", "filmow"))

        self.assertFalse(app.modo_precisa_imdb("letterboxd", "filmow"))
        self.assertTrue(app.modo_precisa_imdb("letterboxd", "imdb"))
        self.assertFalse(app.modo_precisa_imdb("trakt", "filmow"))
        self.assertTrue(app.modo_precisa_imdb("trakt", "imdb"))

    def test_all_export_headers_are_exact_and_ordered(self):
        cases = [
            ("analitica", "filmow", ANALYTIC_COLUMNS),
            ("analitica", "imdb", ANALYTIC_COLUMNS),
            ("sintetica", "filmow", SYNTHETIC_COLUMNS),
            ("sintetica", "imdb", SYNTHETIC_COLUMNS),
            ("letterboxd", "filmow", LETTERBOXD_FILMOW_COLUMNS),
            ("letterboxd", "imdb", LETTERBOXD_IMDB_COLUMNS),
            # ``trakt`` describes the export family; Ratings is the only
            # column-bearing Trakt CSV whose schema can be selected directly.
            ("trakt", "filmow", TRAKT_RATINGS_COLUMNS),
            ("trakt", "imdb", TRAKT_RATINGS_COLUMNS),
        ]
        for modo, origem_nota, expected in cases:
            with self.subTest(modo=modo, origem_nota=origem_nota):
                self.assertEqual(
                    app.colunas_exportacao(modo, origem_nota), expected
                )

    def test_preparar_linha_selects_only_contract_fields(self):
        source = sample_row()
        cases = [
            (
                "analitica",
                "imdb",
                ANALYTIC_COLUMNS,
                {
                    "imdbID": "tt0000001",
                    "tmdbID": "42",
                    "tmdbTitle": "Matrix, The",
                    "tmdbYear": "1999",
                    "tmdbCountry": "US",
                    "tmdbDirectors": "Lana, Lilly Wachowski",
                    "filmowTitle": "A Matrix",
                    "filmowYear": "1999",
                    "filmowRating": "4.5",
                    "Rating10": "8.2",
                },
            ),
            (
                "sintetica",
                "filmow",
                SYNTHETIC_COLUMNS,
                {"imdbID": "tt0000001", "tmdbID": "42"},
            ),
            (
                "letterboxd",
                "filmow",
                LETTERBOXD_FILMOW_COLUMNS,
                {"imdbID": "tt0000001", "tmdbID": "42", "Rating": "4.5"},
            ),
            (
                "letterboxd",
                "imdb",
                LETTERBOXD_IMDB_COLUMNS,
                {"imdbID": "tt0000001", "tmdbID": "42", "Rating10": "8.2"},
            ),
            (
                "trakt",
                "imdb",
                TRAKT_RATINGS_COLUMNS,
                {
                    "imdb_id": "tt0000001",
                    "tmdb_id": "42",
                    "type": "movie",
                    "rating": "8.2",
                },
            ),
        ]
        for modo, origem_nota, colunas, expected in cases:
            with self.subTest(modo=modo, origem_nota=origem_nota):
                actual = app.preparar_linha_exportacao(
                    source, modo, origem_nota
                )
                self.assertEqual(set(actual), set(colunas))
                self.assertEqual(actual, expected)

    def test_preparar_linha_is_pure(self):
        source = sample_row()
        snapshot = dict(source)
        app.preparar_linha_exportacao(source, "trakt", "filmow")
        self.assertEqual(source, snapshot)

    def test_filmow_to_trakt_conversion_uses_decimal_semantics(self):
        cases = [
            (0, "0.0"),
            (0.0, "0.0"),
            ("4.5", "9.0"),
            (Decimal("2.5"), "5.0"),
            (5, "10.0"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    app.converter_rating_filmow_para_trakt(value), expected
                )

    def test_invalid_or_missing_filmow_ratings_are_empty(self):
        for value in (None, "", "not-a-number", -0.1, 5.1, "NaN"):
            with self.subTest(value=value):
                actual = app.converter_rating_filmow_para_trakt(value)
                self.assertEqual(actual, "")
                self.assertNotIsInstance(actual, Decimal)

    def test_preparation_preserves_zero_and_uses_blank_for_missing_invalid(self):
        source = sample_row(
            imdbID="tt-zero",
            tmdbID="0",
            filmowRating=0,
            Rating10=0,
        )
        filmow = app.preparar_linha_exportacao(source, "trakt", "filmow")
        imdb = app.preparar_linha_exportacao(source, "trakt", "imdb")
        self.assertEqual(filmow["rating"], "0.0")
        self.assertEqual(imdb["rating"], 0)

        source = sample_row(filmowRating=None, Rating10=None)
        filmow = app.preparar_linha_exportacao(source, "trakt", "filmow")
        imdb = app.preparar_linha_exportacao(source, "trakt", "imdb")
        self.assertEqual(filmow["rating"], "")
        self.assertEqual(imdb["rating"], "")

        source = sample_row(filmowRating=6, Rating10=11)
        filmow = app.preparar_linha_exportacao(source, "trakt", "filmow")
        imdb = app.preparar_linha_exportacao(source, "trakt", "imdb")
        self.assertEqual(filmow["rating"], "")
        self.assertEqual(imdb["rating"], "")

    def test_trakt_filmow_doubles_and_trakt_imdb_keeps_original_scale(self):
        source = sample_row(filmowRating="3.5", Rating10="7.4")
        filmow = app.preparar_linha_exportacao(source, "trakt", "filmow")
        imdb = app.preparar_linha_exportacao(source, "trakt", "imdb")
        self.assertEqual(filmow["rating"], "7.0")
        self.assertEqual(imdb["rating"], "7.4")

    def _export_and_read(self, modo, origem_nota, rows):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                result = app.exportar_linhas(
                    rows, modo, origem_nota, "usuário", "20260925_031132"
                )
                files = sorted(Path.cwd().glob("*.csv"))
                contents = {path.name: read_csv(path) for path in files}
            finally:
                os.chdir(previous)
        self.assertIsInstance(result, dict)
        self.assertIn("arquivos", result)
        self.assertIn("metricas", result)
        self.assertIsInstance(result["metricas"], dict)
        self.assertEqual(
            sorted(Path(path).name for path in result["arquivos"]),
            sorted(contents),
        )
        self.assertTrue(all(Path(path).is_absolute() or ".." not in Path(path).parts
                            for path in result["arquivos"]))
        return contents

    def test_export_sanitizes_username_for_local_file_names(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                result = app.exportar_linhas(
                    [sample_row()], "sintetica", "imdb", "../../perfil", "20260925_031132"
                )
                names = [Path(path).name for path in result["arquivos"]]
            finally:
                os.chdir(previous)
        self.assertEqual(names, ["exportacao_sintetica_perfil_20260925_031132.csv"])
        self.assertNotIn("/", names[0])
        self.assertNotIn("\\", names[0])


        rows = [
            sample_row(),
            sample_row(
                imdbID="tt-zero",
                tmdbID="0",
                filmowRating=0,
                Rating10=0,
            ),
            sample_row(
                imdbID="tt-missing",
                tmdbID="0",
                filmowRating=None,
                Rating10=None,
            ),
            sample_row(
                imdbID="tt-invalid",
                tmdbID="0",
                filmowRating=5.1,
                Rating10=10.1,
            ),
        ]

        cases = [
            (
                "analitica",
                "imdb",
                ["exportacao_analitica_usuário_20260925_031132.csv"],
                ANALYTIC_COLUMNS,
            ),
            (
                "sintetica",
                "imdb",
                ["exportacao_sintetica_usuário_20260925_031132.csv"],
                SYNTHETIC_COLUMNS,
            ),
            (
                "letterboxd",
                "filmow",
                ["exportacao_letterboxd_usuário_20260925_031132.csv"],
                LETTERBOXD_FILMOW_COLUMNS,
            ),
            (
                "letterboxd",
                "imdb",
                ["exportacao_letterboxd_usuário_20260925_031132.csv"],
                LETTERBOXD_IMDB_COLUMNS,
            ),
        ]
        for modo, origem_nota, expected_files, columns in cases:
            with self.subTest(modo=modo, origem_nota=origem_nota):
                contents = self._export_and_read(modo, origem_nota, rows)
                self.assertEqual(sorted(contents), expected_files)
                data = contents[expected_files[0]]
                self.assertEqual(list(data[0]), columns)
                self.assertEqual(len(data), len(rows))
                self.assertEqual([row["imdbID"] for row in data], [
                    "tt0000001", "tt-zero", "tt-missing", "tt-invalid"
                ])
                self.assertEqual(data[1]["imdbID"], "tt-zero")
                # Synthetic deliberately has no rating field; it must still keep
                # every row, including rows whose notes are empty or invalid.
                if modo == "sintetica":
                    self.assertNotIn("rating", data[1])
                    continue
                nota_col = "Rating10" if origem_nota == "imdb" and modo != "analitica" else None
                if modo == "analitica":
                    self.assertEqual(data[1]["filmowRating"], "0")
                    self.assertEqual(data[1]["Rating10"], "0")
                    self.assertEqual(data[2]["filmowRating"], "")
                    self.assertEqual(data[2]["Rating10"], "")
                    self.assertEqual(data[3]["filmowRating"], "")
                elif nota_col:
                    self.assertEqual(data[1][nota_col], "0")
                    self.assertEqual(data[2][nota_col], "")
                    self.assertEqual(data[3][nota_col], "")
                else:
                    self.assertEqual(data[1]["Rating"], "0")
                    self.assertEqual(data[2]["Rating"], "")
                    self.assertEqual(data[3]["Rating"], "")

    def test_trakt_pair_failure_does_not_publish_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                original_writer = app._escrever_csv_temporario
                chamadas = {"count": 0}

                def falhar_no_segundo(caminho, colunas, linhas):
                    chamadas["count"] += 1
                    if chamadas["count"] == 2:
                        raise OSError("falha simulada")
                    return original_writer(caminho, colunas, linhas)

                with patch.object(
                    app, "_escrever_csv_temporario", side_effect=falhar_no_segundo
                ):
                    with self.assertRaises(OSError):
                        app.exportar_linhas(
                            [sample_row()], "trakt", "filmow", "usuario", "20260925_031132"
                        )
                self.assertEqual(list(Path.cwd().glob("*.csv")), [])
                self.assertEqual(list(Path.cwd().glob("*.tmp")), [])
            finally:
                os.chdir(previous)

    def test_trakt_exports_separate_history_and_ratings_files(self):
        rows = [
            sample_row(filmowRating="3.5", Rating10="7.4"),
            sample_row(imdbID="tt-zero", tmdbID="0", filmowRating=0, Rating10=0),
            sample_row(imdbID="tt-empty", tmdbID="0", filmowRating=None, Rating10=None),
            sample_row(imdbID="tt-invalid", tmdbID="0", filmowRating=6, Rating10=11),
        ]
        for origem_nota in ("filmow", "imdb"):
            with self.subTest(origem_nota=origem_nota):
                contents = self._export_and_read("trakt", origem_nota, rows)
                self.assertEqual(
                    sorted(contents),
                    [
                        "exportacao_history_trakt_usuário_20260925_031132.csv",
                        "exportacao_ratings_trakt_usuário_20260925_031132.csv",
                    ],
                )
                history = contents[
                    "exportacao_history_trakt_usuário_20260925_031132.csv"
                ]
                ratings = contents[
                    "exportacao_ratings_trakt_usuário_20260925_031132.csv"
                ]
                self.assertEqual(list(history[0]), TRAKT_HISTORY_COLUMNS)
                self.assertEqual(list(ratings[0]), TRAKT_RATINGS_COLUMNS)
                # Empty and invalid ratings remain rows in Ratings, especially zero.
                self.assertEqual(len(history), len(rows))
                self.assertEqual(len(ratings), len(rows))
                self.assertTrue(all(row["type"] == "movie" for row in history))
                self.assertTrue(all(row["type"] == "movie" for row in ratings))
                self.assertEqual(ratings[1]["rating"], "0.0" if origem_nota == "filmow" else "0")
                self.assertEqual(ratings[2]["rating"], "")
                self.assertEqual(ratings[3]["rating"], "")
                self.assertEqual(ratings[0]["rating"], "7.0" if origem_nota == "filmow" else "7.4")


if __name__ == "__main__":
    unittest.main()
