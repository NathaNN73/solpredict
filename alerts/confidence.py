"""Volatility-adjusted confidence for alert signals.

Confidence is "NORMAL" by default and downgraded to "LOW" when recent
volatility (14-day std dev) exceeds twice the longer-term average (30-day
rolling std dev). This prevents overconfident buy signals during turbulent
market periods.
"""

from __future__ import annotations

import pandas as pd

import config


def compute_confidence(rates: pd.Series) -> str:
    """Return ``"NORMAL"`` or ``"LOW"`` based on volatility comparison.

    Requires at least 30 data points to compute a meaningful 30-day average.
    Falls back to ``"NORMAL"`` when insufficient data is available — the
    dashboard can then choose to display an informational note rather than a
    warning.

    The comparison follows the spec definition:
      14-day std dev > 2 × (30-day average std dev) → ``"LOW"``
    """
    if len(rates.dropna()) < 30:
        return "NORMAL"

    recent = rates.tail(14)
    baseline = rates.tail(30)

    vol_14d = float(recent.std())
    vol_30d_avg = float(baseline.rolling(14).std().mean())

    if vol_30d_avg == 0:
        return "NORMAL"

    if vol_14d > config.VOLATILITY_MULTIPLIER * vol_30d_avg:
        return "LOW"

    return "NORMAL"
