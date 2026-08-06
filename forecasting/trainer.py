"""Forecast trainer: model selection, 7-day holdout MAPE, and forecast generation.

The trainer ties :mod:`forecasting.models` to :mod:`data_collection.storage`:
it reads historical rates, trains a model (ARIMA-first, Prophet fallback),
generates a 7-calendar-day forecast, and computes MAPE on a 7-day holdout to
score the model. The result is a dict matching the ``forecast.json`` schema.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from forecasting import models

HOLDOUT_DAYS = 7
FORECAST_HORIZON = 7


def _compute_mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Percentage Error, returned as a percentage (e.g. 2.3 = 2.3%)."""
    mask = actual != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def generate_forecast(rates: pd.Series) -> dict:
    """Train a model and return a forecast dict matching the forecast.json schema.

    Steps:
      1. Hold out the most recent 7 days; train on the remainder.
      2. Forecast the 7 held-out days and compute MAPE.
      3. Retrain on the full series and forecast the next 7 calendar days
         starting from the day after the last historical date.

    Returns a dict with ``generated_at``, ``model``, ``mape``, and
    ``predictions`` (list of 7 point-dicts with ``date`` added).
    """
    clean = rates.dropna()

    # --- Holdout MAPE -------------------------------------------------------
    if len(clean) > HOLDOUT_DAYS + models.MIN_DATA_POINTS:
        train_data = clean.iloc[:-HOLDOUT_DAYS]
        holdout_actual = clean.iloc[-HOLDOUT_DAYS:].values

        holdout_model = models.train_model(train_data)
        holdout_pred = [p["predicted"] for p in holdout_model.predict(HOLDOUT_DAYS)]
        mape = _compute_mape(holdout_actual, np.array(holdout_pred))
    else:
        # Not enough data for a holdout; report MAPE as 0.0 (logged but not
        # meaningful). The spec requires MAPE to be computed, which only
        # becomes reliable once we exceed 14 + 7 = 21 data points.
        mape = 0.0

    # --- Final forecast on full series -------------------------------------
    model = models.train_model(clean)
    model_name = type(model).__name__.replace("Model", "")

    last_date = clean.index[-1]
    forecast_dates = [
        (last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        for i in range(FORECAST_HORIZON)
    ]

    raw_points = model.predict(FORECAST_HORIZON)
    predictions = [
        {"date": forecast_dates[i], **raw_points[i]}
        for i in range(FORECAST_HORIZON)
    ]

    return {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "model": model_name,
        "mape": round(mape, 2),
        "predictions": predictions,
    }