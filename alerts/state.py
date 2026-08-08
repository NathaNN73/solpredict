"""Alert state persistence with 24-hour deduplication.

Alerts are written to :data:`config.ALERTS_JSON`. Only one alert of a given
type is kept within a 24-hour rolling window — later evaluations that produce
the same signal type are silently skipped.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import config
from alerts import confidence, detector
from data_collection import storage
from forecasting import cache as forecast_cache

logger = logging.getLogger(__name__)


def _read_alerts(path: Path = config.ALERTS_JSON) -> list[dict]:
    """Return the list of persisted alerts, or an empty list."""
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
        return []
    except (json.JSONDecodeError, TypeError):
        logger.warning("Alerts file corrupt; treating as empty")
        return []


def _is_duplicate(alert_type: str, existing: list[dict]) -> bool:
    """True when an alert of ``alert_type`` exists within 24 hours."""
    cutoff = datetime.now() - timedelta(hours=config.ALERT_DEDUP_HOURS)
    for alert in existing:
        if alert.get("type") != alert_type:
            continue
        try:
            ts = datetime.fromisoformat(alert["generated_at"])
        except (KeyError, ValueError):
            continue
        if ts > cutoff:
            return True
    return False


def get_current_alert(path: Path = config.ALERTS_JSON) -> dict:
    """Return the most recent alert or a ``NO_ACTION`` state.

    Only alerts generated within the dedup window are considered "current".
    Stale alerts are ignored without deleting the file.
    """
    existing = _read_alerts(path)
    cutoff = datetime.now() - timedelta(hours=config.ALERT_DEDUP_HOURS)

    for alert in reversed(existing):
        try:
            ts = datetime.fromisoformat(alert["generated_at"])
        except (KeyError, ValueError):
            continue
        if ts > cutoff:
            return alert

    return {"type": "NO_ACTION"}


def evaluate_and_persist(path: Path = config.ALERTS_JSON) -> dict:
    """Run the full alert pipeline: fetch rates, evaluate signal, persist.

    Steps:
      1. Read historical rates and latest forecast.
      2. Detect buy signal via :func:`detector.evaluate_signal`.
      3. Compute confidence via :func:`confidence.compute_confidence`.
      4. Persist the alert (unless it is a duplicate).
      5. Return the alert dict for the dashboard.
    """
    # ---- Read data ----------------------------------------------------------
    df = storage.read_rates()
    if df.empty:
        return {"type": "NO_ACTION"}

    current_rate = float(df.iloc[-1]["rate"])

    # Build a forecast from the trainer (already cached if fresh).
    try:
        forecast = forecast_cache.get_forecast()
    except ValueError:
        # No data for forecasting yet.
        return {"type": "NO_ACTION"}

    predictions = forecast.get("predictions", [])

    # ---- Evaluate -----------------------------------------------------------
    signal = detector.evaluate_signal(predictions, current_rate)

    if signal["type"] == "NO_ACTION":
        return signal

    # ---- Confidence ---------------------------------------------------------
    rates = df.set_index("date")["rate"].astype(float)
    conf = confidence.compute_confidence(rates)
    signal["confidence"] = conf
    signal["generated_at"] = pd.Timestamp.now().isoformat(timespec="seconds")

    # ---- Persist (with dedup) -----------------------------------------------
    existing = _read_alerts(path)
    if _is_duplicate(signal["type"], existing):
        logger.info("Duplicate %s alert suppressed (within %dh window)",
                     signal["type"], config.ALERT_DEDUP_HOURS)
        return signal

    existing.append(signal)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    logger.info("New %s alert persisted (confidence=%s, trough=%.4f day %d)",
                signal["type"], conf, signal.get("predicted_trough", 0),
                signal.get("trough_day", 0))
    return signal
