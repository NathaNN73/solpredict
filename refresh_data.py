"""Scheduled data refresh for SolPredict.

Fetches today's USD/PEN rate and backfills any historical gaps, leaving
``data/rates.csv`` updated and ready to be committed by CI (see
``.github/workflows/refresh-data.yml``).

This script intentionally does NOT regenerate the forecast or alerts. Those
depend on the heavy Prophet/statsmodels stack, which the app already handles
on demand via ``forecasting.cache`` (12h TTL). Keeping this script pandas-only
makes the scheduled job cheap and reliable.

Usage:
    python refresh_data.py
"""

from __future__ import annotations

import sys
from datetime import datetime

from data_collection import backfill, storage
from data_collection.fetcher import FetchError, fetch_current_rate


def refresh() -> int:
    """Run one refresh cycle. Returns a process exit code (0 = ok)."""
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. Fetch today's rate and store it (storage dedups by date).
    try:
        rate, source = fetch_current_rate()
    except FetchError as exc:
        print(f"WARN: all rate sources failed: {exc.failed_sources}")
        print("      skipping today's rate; still attempting backfill")
    else:
        if storage.append_rate(today, rate, source):
            print(f"stored today's rate: {rate} from {source}")
        else:
            print(f"today's rate already present: {rate} from {source}")

    # 2. Backfill any historical gaps beyond the allowed threshold.
    added = backfill.backfill_if_needed()
    if added:
        print(f"backfilled {added} missing day(s)")
    else:
        print("no backfill needed")

    return 0


if __name__ == "__main__":
    sys.exit(refresh())
