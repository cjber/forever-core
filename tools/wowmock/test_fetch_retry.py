"""Wago.fetch waits out a wago.tools 429 or 503 instead of failing the scene."""

import io
import tempfile
import unittest
import urllib.error
from email.utils import formatdate
from unittest.mock import patch

import wowmock
from wowmock import Wago


def error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError("https://wago.tools/x", code, "x", headers, io.BytesIO(b""))


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FetchRetryTest(unittest.TestCase):
    def wago(self):
        return Wago(cache=tempfile.mkdtemp())

    def run_fetch(self, outcomes):
        sleeps = []
        calls = iter(outcomes)
        self.requests = 0

        def urlopen(request, timeout):
            self.requests += 1
            outcome = next(calls)
            if isinstance(outcome, Exception):
                raise outcome
            return Response(outcome)

        with (
            patch.object(wowmock.urllib.request, "urlopen", urlopen),
            patch.object(wowmock.time, "sleep", sleeps.append),
        ):
            return self.wago().fetch("https://wago.tools/x"), sleeps

    def test_429_then_200_succeeds_and_honours_retry_after(self):
        data, sleeps = self.run_fetch([error(429, "7"), b"ok"])
        self.assertEqual(data, b"ok")
        self.assertEqual(sleeps, [7.0])

    def test_503_backs_off_exponentially_without_retry_after(self):
        data, sleeps = self.run_fetch([error(503), error(503), b"ok"])
        self.assertEqual(data, b"ok")
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_retry_after_is_capped(self):
        _, sleeps = self.run_fetch([error(429, "9999"), b"ok"])
        self.assertEqual(sleeps, [wowmock.RETRY_CAP])

    def test_retry_after_http_date_is_honoured(self):
        with patch.object(wowmock.time, "time", return_value=1000.0):
            _, sleeps = self.run_fetch([error(429, formatdate(1030.0, usegmt=True)), b"ok"])
        self.assertEqual(sleeps, [30.0])

    def test_unusable_retry_after_falls_back_to_backoff(self):
        for value in ("NaN", "inf", "soon"):
            _, sleeps = self.run_fetch([error(429, value), b"ok"])
            self.assertEqual(sleeps, [2.0], value)

    def test_gives_up_after_the_bounded_attempts(self):
        outcomes = [error(429)] * wowmock.FETCH_ATTEMPTS + [b"ok"]
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.run_fetch(outcomes)
        self.assertEqual(caught.exception.code, 429)
        self.assertEqual(self.requests, wowmock.FETCH_ATTEMPTS)

    def test_other_errors_are_not_retried(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.run_fetch([error(404), b"ok"])


if __name__ == "__main__":
    unittest.main()
