"""Tests for the multi-source rate fetcher.

Each source function is mocked independently so the fallback chain and the
all-fail path can be exercised without touching the network.
"""

import json
from unittest.mock import patch

import pytest

from data_collection import fetcher
from data_collection.fetcher import FetchError, fetch_current_rate, fetch_cdn_historical


# --- Per-source success ----------------------------------------------------

class TestSUNATSource:
    def test_sunat_success(self):
        with patch("data_collection.fetcher._fetch_sunat", return_value=3.72):
            rate, source = fetch_current_rate()
        assert rate == 3.72
        assert source == "sunat"


class TestCDNSource:
    def test_cdn_fallback_when_sunat_fails(self):
        def fake_cdn(date=None):
            assert date is None
            return 3.68
        with patch("data_collection.fetcher._fetch_sunat", side_effect=ValueError("down")), \
             patch("data_collection.fetcher._fetch_cdn", side_effect=fake_cdn):
            rate, source = fetch_current_rate()
        assert rate == 3.68
        assert source == "cdn"


class TestBackupSource:
    def test_backup_fallback_when_sunat_and_cdn_fail(self):
        with patch("data_collection.fetcher._fetch_sunat", side_effect=ValueError("down")), \
             patch("data_collection.fetcher._fetch_cdn", side_effect=ValueError("down")), \
             patch("data_collection.fetcher._fetch_backup", return_value=3.75):
            rate, source = fetch_current_rate()
        assert rate == 3.75
        assert source == "backup"


# --- Fallback chain order ---------------------------------------------------

class TestFallbackOrder:
    def test_sunat_tried_first(self):
        order: list[str] = []

        def track_sunat():
            order.append("sunat")
            return 3.70

        with patch("data_collection.fetcher._fetch_sunat", side_effect=track_sunat), \
             patch("data_collection.fetcher._fetch_cdn", side_effect=AssertionError), \
             patch("data_collection.fetcher._fetch_backup", side_effect=AssertionError):
            fetch_current_rate()
        assert order == ["sunat"]

    def test_cdn_not_called_when_sunat_succeeds(self):
        with patch("data_collection.fetcher._fetch_sunat", return_value=3.70), \
             patch("data_collection.fetcher._fetch_cdn", side_effect=AssertionError), \
             patch("data_collection.fetcher._fetch_backup", side_effect=AssertionError):
            rate, source = fetch_current_rate()
        assert source == "sunat"
        assert rate == 3.70


# --- All sources fail ------------------------------------------------------

class TestAllFail:
    def test_all_fail_raises_fetch_error(self):
        with patch("data_collection.fetcher._fetch_sunat", side_effect=ValueError("down")), \
             patch("data_collection.fetcher._fetch_cdn", side_effect=ValueError("down")), \
             patch("data_collection.fetcher._fetch_backup", side_effect=ValueError("down")):
            with pytest.raises(FetchError) as exc_info:
                fetch_current_rate()
        assert exc_info.value.failed_sources  # non-empty list of failures

    def test_all_fail_records_failed_sources(self):
        with patch("data_collection.fetcher._fetch_sunat", side_effect=ValueError("sun")), \
             patch("data_collection.fetcher._fetch_cdn", side_effect=ValueError("cdn")), \
             patch("data_collection.fetcher._fetch_backup", side_effect=ValueError("bk")):
            with pytest.raises(FetchError) as exc_info:
                fetch_current_rate()
        sources = exc_info.value.failed_sources
        assert len(sources) == 3
        assert all(name in sources[0] + sources[1] + sources[2]
                   for name in ("sunat", "cdn", "backup"))


# --- Invalid rate treated as failure ---------------------------------------

class TestInvalidRateFallback:
    def test_out_of_range_sunat_falls_through(self):
        # SUNAT returns 0.01 (invalid) -> validator rejects -> CDN is used.
        with patch("data_collection.fetcher._fetch_sunat", side_effect=ValueError("bad")), \
             patch("data_collection.fetcher._fetch_cdn", return_value=3.72):
            rate, source = fetch_current_rate()
        assert rate == 3.72
        assert source == "cdn"


# --- Historical CDN fetch --------------------------------------------------

class TestHistoricalFetch:
    def test_historical_fetch_returns_rate(self):
        with patch("data_collection.fetcher._fetch_cdn", return_value=3.65) as mock:
            rate = fetch_cdn_historical("2026-07-15")
        mock.assert_called_once_with(date="2026-07-15")
        assert rate == 3.65

    def test_historical_fetch_failure_raises_value_error(self):
        with patch("data_collection.fetcher._fetch_cdn", side_effect=KeyError("usd")):
            with pytest.raises(ValueError):
                fetch_cdn_historical("2026-07-15")


# --- End-to-(mocked) end integration ----------------------------------------

class TestSourceParsing:
    """Exercise _get_json + source parsing with mocked urlopen payloads."""

    def test_sunat_parses_venta(self):
        payload = json.dumps({"venta": 3.72, "compra": 3.70}).encode()
        self._assert_urlopen_returns(payload, "sunat", 3.72)

    def test_cdn_parses_usd_pen(self):
        payload = json.dumps({"usd": {"pen": 3.68}}).encode()
        self._assert_urlopen_returns(payload, "cdn", 3.68)

    def test_backup_parses_inverse_usd(self):
        # rates.USD = 0.2666 -> 1/0.2666 ~= 3.751
        expected = 1.0 / 0.2666
        payload = json.dumps({"rates": {"USD": 0.2666}}).encode()
        self._assert_urlopen_returns(payload, "backup", pytest.approx(expected, rel=1e-6))

    @staticmethod
    def _assert_urlopen_returns(payload_bytes, expected_source, expected_rate):
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = payload_bytes
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp):
            rate, source = fetch_current_rate()
        assert source == expected_source
        assert rate == expected_rate