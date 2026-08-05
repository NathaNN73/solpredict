"""Historical backfill with gap detection.

On first run (empty store) the module backfills up to ``MAX_BACKFILL_DAYS`` of
history from the CDN currency-api. On subsequent runs it only fetches when a
gap strictly larger than ``GAP_THRESHOLD_DAYS`` consecutive days is detected.
Each missing date is fetched independently so a single CDN failure does not
abort the whole backfill (partial fill is acceptable per the error strategy).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import config
from data_collection import storage
from data_collection.fetcher import fetch_cdn_historical


def _target_dates(today: date, days: int) -> list[date]:
    """Return ``days`` consecutive calendar dates ending at ``today``."""
    return [today - timedelta(days=offset) for offset in range(days)][::-1]


def _longest_consecutive_gap(missing: Iterable[date], reference: list[date]) -> int:
    """Length of the longest run of missing dates within ``reference``.

    ``reference`` must be the contiguous, sorted list of expected dates; this
    lets a "gap" be a maximal run of dates present in reference but absent from
    the stored set.
    """
    missing_set = set(missing)
    longest = 0
    run = 0
    for d in reference:
        if d in missing_set:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return longest


def backfill_if_needed(
    path=config.RATES_CSV,
    today: date | None = None,
) -> int:
    """Backfill missing historical rates from the CDN, returning appended count.

    Returns ``0`` when no backfill is needed (store has data and every gap is
    within the allowed threshold).
    """
    today = today or date.today()
    target = _target_dates(today, config.MAX_BACKFILL_DAYS)

    existing = storage._existing_dates(path)
    missing = [d for d in target if d.isoformat() not in existing]

    if existing:
        # Only act when the longest missing run exceeds the threshold.
        if _longest_consecutive_gap(missing, target) <= config.GAP_THRESHOLD_DAYS:
            return 0

    if not missing:
        return 0

    count = 0
    for d in missing:
        try:
            rate = fetch_cdn_historical(d.isoformat())
        except ValueError:
            # CDN snapshot missing for this date — skip, partial fill is ok.
            continue
        if storage.append_rate(d.isoformat(), rate, "cdn", path=path):
            count += 1
    return count