"""Tests for the historical backfill module.

CDN HTTP calls are mocked so tests are deterministic and offline.
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from data_collection import backfill, storage


TODAY = date(2026, 8, 5)


def _seed_dates(path, dates, base_rate=3.70):
    for d in dates:
        storage.append_rate(d, base_rate, "cdn", path=path)


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "rates.csv"
    storage._ensure_csv(path)
    return path


class TestFirstRunBackfill:
    def test_empty_store_triggers_full_backfill(self, csv_path):
        rate_map = {
            (TODAY - timedelta(days=i)).isoformat(): 3.70 + i * 0.001
            for i in range(90)
        }

        def fake_fetch(date_str):
            return rate_map[date_str]

        with patch("data_collection.backfill.fetch_cdn_historical", side_effect=fake_fetch):
            count = backfill.backfill_if_needed(path=csv_path, today=TODAY)

        # 90 historical snapshots fetched for the empty store.
        assert count == 90
        df = storage.read_rates(path=csv_path)
        assert len(df) == 90

    def test_returns_zero_when_nothing_fetched_and_store_still_empty(self, csv_path):
        # CDN fails for every date -> 0 appended even though backfill ran.
        with patch("data_collection.backfill.fetch_cdn_historical", side_effect=ValueError("down")):
            count = backfill.backfill_if_needed(path=csv_path, today=TODAY)
        assert count == 0
        df = storage.read_rates(path=csv_path)
        assert df.empty


class TestGapFill:
    def test_large_gap_triggers_fetch_of_missing_only(self, csv_path):
        # Store has dates for the recent 5 days, then a 5-day gap, then older dates.
        recent = [(TODAY - timedelta(days=i)).isoformat() for i in range(5)]            # 5 recent
        gap_start = TODAY - timedelta(days=10)
        gap_dates = [(gap_start - timedelta(days=i)).isoformat() for i in range(5)]      # 5-day gap
        older = [(gap_start - timedelta(days=10 + i)).isoformat() for i in range(3)]     # older

        seeded = recent + gap_dates + older
        _seed_dates(csv_path, sorted(set(seeded)))

        df_before = storage.read_rates(path=csv_path)
        added_before = len(df_before)

        fetched: list[str] = []

        def fake_fetch(date_str):
            fetched.append(date_str)
            return 3.71

        with patch("data_collection.backfill.fetch_cdn_historical", side_effect=fake_fetch):
            count = backfill.backfill_if_needed(path=csv_path, today=TODAY)

        # The 5-day gap exceeds GAP_THRESHOLD_DAYS (3) so backfill runs.
        assert count >= 1
        # Only previously-missing dates were fetched; none of the seeded ones.
        seeded_set = set(sorted(set(seeded)))
        assert all(d not in seeded_set for d in fetched)
        assert len(df_before) + count == len(storage.read_rates(path=csv_path))

    def test_small_gap_below_threshold_is_skipped(self, csv_path):
        # Seed the full 90-day window EXCEPT a 2-day gap (<= threshold).
        gap_days = {(TODAY - timedelta(days=3)).isoformat(),
                    (TODAY - timedelta(days=4)).isoformat()}
        all_dates = [(TODAY - timedelta(days=i)).isoformat() for i in range(90)]
        _seed_dates(csv_path, [d for d in all_dates if d not in gap_days])

        with patch("data_collection.backfill.fetch_cdn_historical", side_effect=AssertionError) as mock_fetch:
            count = backfill.backfill_if_needed(path=csv_path, today=TODAY)
        assert count == 0  # longest gap (2) does not exceed threshold (3)
        assert mock_fetch.call_count == 0  # CDN never contacted


class TestNoGapSkip:
    def test_complete_store_no_backfill(self, csv_path):
        # Store every day in the 90-day window -> no missing -> 0.
        all_dates = [(TODAY - timedelta(days=i)).isoformat() for i in range(90)]
        _seed_dates(csv_path, all_dates)

        with patch("data_collection.backfill.fetch_cdn_historical", side_effect=AssertionError) as mock_fetch:
            count = backfill.backfill_if_needed(path=csv_path, today=TODAY)
        assert count == 0
        assert mock_fetch.call_count == 0


class TestPartialFailure:
    def test_partial_failure_still_appends_successful_dates(self, csv_path):
        # Day 3 (from today) fails, others succeed.
        def fake_fetch(date_str):
            d = date.fromisoformat(date_str)
            if d == TODAY - timedelta(days=3):
                raise ValueError("missing snapshot")
            return 3.72

        with patch("data_collection.backfill.fetch_cdn_historical", side_effect=fake_fetch):
            count = backfill.backfill_if_needed(path=csv_path, today=TODAY)

        # First run on empty store -> 90 attempted, 1 failed -> 89 appended.
        assert count == 89
        df = storage.read_rates(path=csv_path)
        assert len(df) == 89
        assert (TODAY - timedelta(days=3)).isoformat() not in set(df["date"].astype(str))