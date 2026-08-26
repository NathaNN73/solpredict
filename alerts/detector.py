"""Trend-based buy signal detector — based on REAL observed rates.

Detects favorable moments to buy dollars from the actual USD/PEN history,
not from ML forecast (which is unreliable for short-horizon forex).

The pair is USD/PEN (soles per dollar): a LOWER rate means dollars are
cheaper — the ideal time to buy.

A BUY_SIGNAL fires when BOTH hold:
  1. The short moving average (MA_SHORT_DAYS) sits below the long moving
     average (MA_LONG_DAYS) — the dollar is in a confirmed downtrend.
  2. The rate dropped at least MOMENTUM_THRESHOLD over the last
     MOMENTUM_WINDOW_DAYS — the move is large enough to matter.
"""

from __future__ import annotations

import pandas as pd

import config


def evaluate_signal(rates: pd.Series) -> dict:
    """Evaluate real rate history and return an alert dict.

    ``rates`` is a pandas Series indexed by date with rate values (soles per
    dollar), sorted ascending by date.

    Returns a dict with:
      - ``type``: ``"BUY_SIGNAL"`` or ``"NO_ACTION"``
      - ``current_rate``: the latest observed rate
      - ``momentum_pct``: percentage change over the momentum window
        (negative = dollar dropping) — BUY_SIGNAL only
      - ``ma_short`` / ``ma_long``: the moving averages — BUY_SIGNAL only
    """
    clean = rates.dropna()

    if len(clean) < config.MA_LONG_DAYS:
        current = float(clean.iloc[-1]) if len(clean) else 0.0
        return {"type": "NO_ACTION", "current_rate": current}

    current = float(clean.iloc[-1])
    ma_short = float(clean.tail(config.MA_SHORT_DAYS).mean())
    ma_long = float(clean.tail(config.MA_LONG_DAYS).mean())

    reference = float(clean.iloc[-1 - config.MOMENTUM_WINDOW_DAYS])
    momentum = (current - reference) / reference  # negative => dollar dropping

    # Condition 1: short MA below long MA => confirmed downtrend.
    downtrend = ma_short < ma_long

    # Condition 2: the drop is large enough to matter.
    dropped_enough = momentum <= -config.MOMENTUM_THRESHOLD

    if not (downtrend and dropped_enough):
        return {"type": "NO_ACTION", "current_rate": current}

    return {
        "type": "BUY_SIGNAL",
        "current_rate": round(current, 4),
        "momentum_pct": round(momentum * 100, 2),
        "ma_short": round(ma_short, 4),
        "ma_long": round(ma_long, 4),
    }
