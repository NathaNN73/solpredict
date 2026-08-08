"""Trend-based buy signal detector.

Evaluates forecast predictions to find favorable moments to buy dollars.
Since the pair is USD/PEN (soles per dólar), a LOWER rate means dollars
are cheaper — the ideal time to buy.

A BUY_SIGNAL fires when the forecast predicts a significant DECREASE.
"""

from __future__ import annotations

import config


def evaluate_signal(
    predictions: list[dict],
    current_rate: float,
) -> dict:
    """Evaluate forecast predictions and return an alert dict.

    Conditions for a BUY_SIGNAL (both must be true):
      1. At least one predicted rate is BELOW ``current_rate * (1 - threshold)``
         where ``threshold`` is :data:`config.BUY_SIGNAL_THRESHOLD` (default 1.5%).
         In other words: the dollar is predicted to drop at least 1.5%.
      2. The predicted values are monotonically DECREASING for at least 3
         consecutive days, confirming a downward trend.

    Returns a dict with:
      - ``type``: ``"BUY_SIGNAL"`` or ``"NO_ACTION"``
      - ``current_rate``: the rate the signal was evaluated against
      - ``predicted_trough``: lowest predicted rate in the window (BUY_SIGNAL only)
      - ``trough_day``: 1-based day index of the trough (BUY_SIGNAL only)
      - ``generated_at``: omitted here; added by :mod:`alerts.state`.
    """
    if not predictions:
        return {"type": "NO_ACTION", "current_rate": current_rate}

    # --- Condition 1: magnitude check — rate must DROP ≥ threshold -----------
    target = current_rate * (1 - config.BUY_SIGNAL_THRESHOLD)
    predicted_rates = [p["predicted"] for p in predictions]
    trough_value = min(predicted_rates)

    if trough_value > target:
        return {"type": "NO_ACTION", "current_rate": current_rate}

    # --- Condition 2: monotonic DECREASING run ≥ 3 days ----------------------
    longest_run = 0
    current_run = 1
    for i in range(1, len(predicted_rates)):
        if predicted_rates[i] < predicted_rates[i - 1]:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 1
    longest_run = max(longest_run, current_run)

    if longest_run < 3:
        return {"type": "NO_ACTION", "current_rate": current_rate}

    # Both conditions satisfied → BUY_SIGNAL (dollar is dropping).
    trough_day = predicted_rates.index(trough_value) + 1  # 1-based
    return {
        "type": "BUY_SIGNAL",
        "current_rate": current_rate,
        "predicted_trough": round(trough_value, 4),
        "trough_day": trough_day,
    }
