"""CSV-backed rate storage with duplicate-date detection.

Schema (one row per day, date is the unique key)::

    date,rate,source,fetched_at
    2026-08-04,3.720,SUNAT,2026-08-04T10:30:00

Writing the same date twice is a no-op (skip without overwriting) per the
data-collection spec. Reads return a :class:`pandas.DataFrame` ordered by date.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

import config

logger = logging.getLogger(__name__)

COLUMNS = ["date", "rate", "source", "fetched_at"]


def _ensure_csv(path: Path = config.RATES_CSV) -> None:
    """Create the data directory and an empty CSV with the header row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(COLUMNS)


def _existing_dates(path: Path = config.RATES_CSV) -> set[str]:
    """Return the set of dates already stored in the CSV."""
    if not path.exists():
        return set()
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return {row["date"] for row in reader if row.get("date")}


def append_rate(
    date: str,
    rate: float,
    source: str,
    fetched_at: str | None = None,
    path: Path = config.RATES_CSV,
) -> bool:
    """Append ``(date, rate, source, fetched_at)`` unless ``date`` exists.

    Returns ``True`` when a row was appended, ``False`` when the date was
    already present (duplicate skip). ``fetched_at`` defaults to now (local,
    ISO 8601). The public contract is ``-> None``; the bool return exists for
    testability and is harmless to ignore.
    """
    _ensure_csv(path)
    if date in _existing_dates(path):
        return False

    if fetched_at is None:
        fetched_at = datetime.now().isoformat(timespec="seconds")

    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([date, rate, source, fetched_at])
    return True


def read_rates(days: int | None = None, path: Path = config.RATES_CSV) -> pd.DataFrame:
    """Return the stored rates as a DataFrame, optionally limited to last ``days``.

    ``days=None`` returns every record. The returned DataFrame is sorted
    ascending by date. If the CSV does not exist an empty (schema-correct)
    DataFrame is returned.
    """
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)

    try:
        df = pd.read_csv(path, dtype={"source": str}, parse_dates=["date"])
    except (pd.errors.ParserError, ValueError) as exc:
        logger.warning("Corrupt or unparseable CSV at %s (%s); treating as empty", path, exc)
        return pd.DataFrame(columns=COLUMNS)

    df = df.sort_values("date").reset_index(drop=True)

    if days is None:
        return df
    if days <= 0:
        return df.iloc[0:0]  # keep schema, drop rows
    return df.tail(days).reset_index(drop=True)