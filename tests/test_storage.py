"""Tests for CSV storage with duplicate detection."""

import csv

import pandas as pd
import pytest

from data_collection import storage


@pytest.fixture
def csv_path(tmp_path):
    """Fresh CSV path under a temp directory."""
    path = tmp_path / "rates.csv"
    storage._ensure_csv(path)
    return path


class TestFirstWrite:
    def test_creates_csv_with_header(self, tmp_path):
        path = tmp_path / "none.csv"
        assert not path.exists()
        added = storage.append_rate("2026-08-01", 3.72, "sunat", path=path)
        assert added is True
        assert path.exists()
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == storage.COLUMNS
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-08-01"
        assert rows[0]["rate"] == "3.72"
        assert rows[0]["source"] == "sunat"

    def test_returns_true_on_new_date(self, csv_path):
        assert storage.append_rate("2026-08-02", 3.71, "cdn", path=csv_path) is True


class TestDuplicateSkip:
    def test_same_date_skipped(self, csv_path):
        storage.append_rate("2026-08-04", 3.72, "sunat", path=csv_path)
        added = storage.append_rate("2026-08-04", 3.80, "cdn", path=csv_path)
        assert added is False
        df = storage.read_rates(path=csv_path)
        assert len(df) == 1
        # original rate preserved, not overwritten
        assert float(df.iloc[0]["rate"]) == 3.72
        assert df.iloc[0]["source"] == "sunat"

    def test_different_dates_all_stored(self, csv_path):
        for day in ("2026-08-01", "2026-08-02", "2026-08-03"):
            storage.append_rate(day, 3.70, "cdn", path=csv_path)
        df = storage.read_rates(path=csv_path)
        assert len(df) == 3


class TestReadWithLimit:
    def test_read_all(self, csv_path):
        for i, day in enumerate(("2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04")):
            storage.append_rate(day, 3.70 + i * 0.01, "cdn", path=csv_path)
        df = storage.read_rates(path=csv_path)
        assert len(df) == 4
        assert list(df.columns) == storage.COLUMNS

    def test_read_last_n_days(self, csv_path):
        for i, day in enumerate(("2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04")):
            storage.append_rate(day, 3.70 + i * 0.01, "cdn", path=csv_path)
        df = storage.read_rates(days=2, path=csv_path)
        assert len(df) == 2
        # tail keeps the most recent dates (read_rates parses date -> Timestamp)
        assert df.iloc[0]["date"] == pd.Timestamp("2026-08-03")
        assert df.iloc[1]["date"] == pd.Timestamp("2026-08-04")

    def test_read_zero_days_returns_empty_schema(self, csv_path):
        storage.append_rate("2026-08-01", 3.70, "cdn", path=csv_path)
        df = storage.read_rates(days=0, path=csv_path)
        assert len(df) == 0
        assert list(df.columns) == storage.COLUMNS


class TestEmptyStore:
    def test_read_nonexistent_returns_empty_df(self, tmp_path):
        path = tmp_path / "absent.csv"
        df = storage.read_rates(path=path)
        assert df.empty
        assert list(df.columns) == storage.COLUMNS

    def test_ensure_csv_idempotent(self, tmp_path):
        path = tmp_path / "x.csv"
        storage._ensure_csv(path)
        storage._ensure_csv(path)  # should not duplicate header
        with path.open(encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        assert lines.count(",".join(storage.COLUMNS)) == 1


class TestDefaultFetchedAt:
    def test_fetched_at_auto_populated(self, csv_path):
        # Pass no fetched_at -> storage stamps it with now.
        storage.append_rate("2026-08-05", 3.72, "sunat", path=csv_path)
        df = storage.read_rates(path=csv_path)
        assert pd.notna(df.iloc[0]["fetched_at"])
        assert isinstance(df.iloc[0]["fetched_at"], str) or pd.notnull(df.iloc[0]["fetched_at"])