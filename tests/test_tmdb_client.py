import unittest
from unittest.mock import Mock, patch

import requests

import tmdb_client


class TmdbClientTests(unittest.TestCase):
    def test_fetch_uses_api_key_and_returns_json(self):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True}
        with patch.object(tmdb_client.requests, "get", return_value=response) as get:
            result = tmdb_client.fetch_tmdb(
                "/movie/1", {"language": "pt-BR"}, api_key="test-key"
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(get.call_args.kwargs["params"]["api_key"], "test-key")
        self.assertEqual(get.call_args.kwargs["params"]["language"], "pt-BR")

    def test_fetch_retries_429_with_injected_sleep(self):
        rate_limited = Mock(status_code=429)
        success = Mock(status_code=200)
        success.json.return_value = {"ok": True}
        sleeps = []
        with patch.object(
            tmdb_client.requests,
            "get",
            side_effect=[rate_limited, success],
        ):
            result = tmdb_client.fetch_tmdb(
                "/movie/1", api_key="test-key", max_retries=2, sleep=sleeps.append
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [2])

    def test_fetch_retries_all_5xx_with_exponential_backoff_without_final_sleep(self):
        sleeps = []
        with patch.object(
            tmdb_client.requests,
            "get",
            side_effect=[Mock(status_code=status, headers={}) for status in (500, 502, 503, 504, 599)],
        ) as get:
            result = tmdb_client.fetch_tmdb(
                "/movie/1", api_key="secret", max_retries=5, sleep=sleeps.append
            )

        self.assertIsNone(result)
        self.assertEqual(get.call_count, 5)
        self.assertEqual(sleeps, [2, 4, 8, 16])
        self.assertEqual(get.call_args.kwargs["timeout"], 15)
        self.assertEqual(get.call_args.kwargs["params"]["api_key"], "secret")

    def test_fetch_honors_numeric_retry_after_with_cap(self):
        early = Mock(status_code=503, headers={"Retry-After": "4.5"})
        late = Mock(status_code=503, headers={"Retry-After": "600"})
        success = Mock(status_code=200, headers={})
        success.json.return_value = {"ok": True}
        sleeps = []
        with patch.object(
            tmdb_client.requests, "get", side_effect=[early, late, success]
        ):
            result = tmdb_client.fetch_tmdb(
                "/movie/1", max_retries=3, sleep=sleeps.append
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [4.5, 60])

    def test_fetch_ignores_non_numeric_retry_after_and_uses_backoff(self):
        response = Mock(status_code=500, headers={"Retry-After": "later"})
        sleeps = []
        with patch.object(tmdb_client.requests, "get", return_value=response):
            result = tmdb_client.fetch_tmdb(
                "/movie/1", max_retries=1, sleep=sleeps.append
            )

        self.assertIsNone(result)
        self.assertEqual(sleeps, [])

    def test_fetch_retries_request_exceptions_without_sleeping_after_last_attempt(self):
        sleeps = []
        error = requests.exceptions.Timeout("offline")
        with patch.object(tmdb_client.requests, "get", side_effect=error) as get:
            result = tmdb_client.fetch_tmdb(
                "/movie/1", max_retries=3, sleep=sleeps.append
            )

        self.assertIsNone(result)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleeps, [2, 4])

    def test_fetch_retries_invalid_json_on_2xx_and_can_recover(self):
        invalid = Mock(status_code=200, headers={})
        invalid.json.side_effect = ValueError("invalid JSON")
        success = Mock(status_code=201, headers={})
        success.json.return_value = {"ok": True}
        sleeps = []
        with patch.object(tmdb_client.requests, "get", side_effect=[invalid, success]):
            result = tmdb_client.fetch_tmdb(
                "/movie/1", max_retries=2, sleep=sleeps.append
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [2])

    def test_fetch_does_not_retry_auth_or_missing_resources(self):
        for status in (401, 403, 404):
            with self.subTest(status=status):
                response = Mock(status_code=status, headers={})
                sleeps = []
                with patch.object(
                    tmdb_client.requests, "get", return_value=response
                ) as get:
                    result = tmdb_client.fetch_tmdb(
                        "/movie/1", max_retries=3, sleep=sleeps.append
                    )

                self.assertIsNone(result)
                self.assertEqual(get.call_count, 1)
                self.assertEqual(sleeps, [])

    def test_get_details_normalizes_movie_metadata(self):
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
            result = tmdb_client.get_tmdb_details(603, api_key="test-key")

        self.assertEqual(result["tmdbID"], "603")
        self.assertEqual(result["imdbID"], "tt0133093")
        self.assertEqual(result["tmdbYear"], "1999")
        self.assertEqual(result["tmdbAltTitles"], ["Matrix"])
        self.assertEqual(result["tmdbDirectors"], "Lana Wachowski")


if __name__ == "__main__":
    unittest.main()
