"""Trend-based buy signal detector.

Evaluates forecast predictions against a minimum-increase threshold and a
monotonic-trend requirement. Returns a structured alert dict for consumption
by the alert state manager and the dashboard.
"""

from __future__ import annotations

import config


def evaluate_signal(
    predictions: list[dict],
    current_rate: float,
) -> dict:
    """Evaluate forecast predictions and return an alert dict.

    Conditions for a BUY_SIGNAL (both must be true):
      1. At least one predicted rate exceeds ``current_rate * (1 + threshold)``
         where ``threshold`` is :data:`config.BUY_SIGNAL_THRESHOLD` (default 1.5%).
      2. The predicted values are monotonically increasing for at least 3
         consecutive days.

    Returns a dict with:
      - ``type``: ``"BUY_SIGNAL"`` or ``"NO_ACTION"``
      - ``current_rate``: the rate the signal was evaluated against
      - ``predicted_peak``: highest predicted rate in the window (BUY_SIGNAL only)
      - ``peak_day``: 1-based day index of the peak (BUY_SIGNAL only)
      - ``generated_at``: omitted here; added by :mod:`alerts.state`.
    """
    if not predictions:
        return {"type": "NO_ACTION", "current_rate": current_rate}

    # --- Condition 1: magnitude check ---------------------------------------
    target = current_rate * (1 + config.BUY_SIGNAL_THRESHOLD)
    predicted_rates = [p["predicted"] for p in predictions]
    peak_value = max(predicted_rates)

    if peak_value < target:
        return {"type": "NO_ACTION", "current_rate": current_rate}

    # --- Condition 2: monotonic run ≥ 3 days --------------------------------
    longest_run = 0
    current_run = 1
    for i in range(1, len(predicted_rates)):
        if predicted_rates[i] > predicted_rates[i - 1]:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 1
    longest_run = max(longest_run, current_run)

    if longest_run < 3:
        return {"type": "NO_ACTION", "current_rate": current_rate}

    # Both conditions satisfied → BUY_SIGNAL.
    peak_day = predicted_rates.index(peak_value) + 1  # 1-based
    return {
        "type": "BUY_SIGNAL",
        "current_rate": current_rate,
        "predicted_peak": round(peak_value, 4),
        "peak_day": peak_day,
    }
