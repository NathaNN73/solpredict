"""12-hour TTL cache for forecast results.

Reads and writes :data:`config.FORECAST_JSON`. When the cached file is missing,
corrupt, or older than :data:`config.FORECAST_CACHE_TTL_HOURS` the cache is
regenerated via :func:`forecasting.trainer.generate_forecast`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import config
from data_collection import storage
from forecasting import trainer

logger = logging.getLogger(__name__)


def _is_stale(generated_at: str) -> bool:
    """Return True when ``generated_at`` is older than the TTL or unparseable."""
    try:
        ts = datetime.fromisoformat(generated_at)
    except (ValueError, TypeError):
        return True
    age = datetime.now() - ts
    return age > timedelta(hours=config.FORECAST_CACHE_TTL_HOURS)


def get_forecast(path: Path = config.FORECAST_JSON) -> dict:
    """Return the cached forecast if fresh (< 12h); otherwise regenerate.

    Enhancement: the cached ``predictions`` array is always truncated to 7
    entries, keeping contracts tight even if a prior run returned more.
    """
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not _is_stale(data.get("generated_at", "")):
                logger.info("Returning cached forecast (age < %dh)", config.FORECAST_CACHE_TTL_HOURS)
                data["predictions"] = data["predictions"][:7]
                return data
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Forecast cache corrupt (%s); regenerating", exc)

    return regenerate_forecast(path)


def regenerate_forecast(path: Path = config.FORECAST_JSON) -> dict:
    """Train a fresh forecast from stored rates and persist it to ``path``."""
    df = storage.read_rates()
    if df.empty:
        raise ValueError("No historical rate data available for forecasting")

    rates = df.set_index("date")["rate"].astype(float)
    forecast = trainer.generate_forecast(rates)
    save_forecast(forecast, path)
    return forecast


def save_forecast(data: dict, path: Path = config.FORECAST_JSON) -> None:
    """Write ``data`` to the forecast JSON file, creating the directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")