"""Unified ARIMA and Prophet model wrappers with automated fallback.

The module exposes a single :func:`train_model` entry point that tries ARIMA
first and falls back to Prophet on convergence failure. Both wrappers share a
``predict(horizon)`` interface returning a list of dicts with point estimates
and 80%/95% confidence bounds.

The minimum data requirement is 14 days; fewer points raise
:class:`InsufficientDataError`.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import pandas as pd

logger = logging.getLogger(__name__)

MIN_DATA_POINTS = 14


class InsufficientDataError(Exception):
    """Raised when the historical series is too short for training (< 14 days)."""


@runtime_checkable
class ForecastModel(Protocol):
    def predict(self, horizon: int) -> list[dict]: ...


def _format_point(predicted: float, lower: pd.Series, upper: pd.Series) -> dict:
    """Build a single forecast point dict from statsmodels conf-int arrays."""
    return {
        "predicted": float(predicted),
        "lower_80": float(lower.iloc[0]),
        "upper_80": float(upper.iloc[0]),
        "lower_95": float(lower.iloc[1]),
        "upper_95": float(upper.iloc[1]),
    }


class ARIMAModel:
    """ARIMA(p,d,q) wrapper around statsmodels with 80% and 95% intervals."""

    def __init__(self, data: pd.Series) -> None:
        self._data = data
        self._result = None

    def fit(self) -> "ARIMAModel":
        """Fit an ARIMA(1,1,1) model on the series."""
        from statsmodels.tsa.arima.model import ARIMA

        self._result = ARIMA(self._data, order=(1, 1, 1)).fit()
        return self

    def predict(self, horizon: int) -> list[dict]:
        if self._result is None:
            self.fit()

        forecast = self._result.get_forecast(steps=horizon)
        predicted = forecast.predicted_mean
        ci80 = forecast.conf_int(alpha=0.20)   # 80% interval
        ci95 = forecast.conf_int(alpha=0.05)   # 95% interval

        points: list[dict] = []
        for i in range(horizon):
            points.append(
                {
                    "predicted": float(predicted.iloc[i]),
                    "lower_80": float(ci80.iloc[i, 0]),
                    "upper_80": float(ci80.iloc[i, 1]),
                    "lower_95": float(ci95.iloc[i, 0]),
                    "upper_95": float(ci95.iloc[i, 1]),
                }
            )
        return points


class ProphetModel:
    """Prophet wrapper producing the same forecast-point interface as ARIMA."""

    def __init__(self, data: pd.Series) -> None:
        self._data = data
        self._model = None

    def fit(self) -> "ProphetModel":
        from prophet import Prophet

        interval_width = 0.80  # Prophet's tunable interval; we widen to 95% in predict
        frame = pd.DataFrame({"ds": self._data.index, "y": self._data.values})
        model = Prophet(
            interval_width=interval_width,
            daily_seasonality=False,
            weekly_seasonality=False,
            yearly_seasonality=False,
        )
        model.fit(frame)
        self._model = model
        return self

    def predict(self, horizon: int) -> list[dict]:
        if self._model is None:
            self.fit()

        future = self._model.make_future_dataframe(
            periods=horizon, freq="D", include_history=False
        )
        fc = self._model.predict(future)

        # Prophet's interval_width=0.80 gives yhat_lower/upper at the 80% level.
        # Widen them by ~30% of the margin to approximate a 95% band.
        points: list[dict] = []
        for _, row in fc.iterrows():
            margin_80 = row["yhat"] - row["yhat_lower"]
            widen = 1.6  # 80% → ~95% Z ratio scaling
            points.append(
                {
                    "predicted": float(row["yhat"]),
                    "lower_80": float(row["yhat_lower"]),
                    "upper_80": float(row["yhat_upper"]),
                    "lower_95": float(row["yhat"] - margin_80 * widen),
                    "upper_95": float(row["yhat"] + margin_80 * widen),
                }
            )
        return points


def train_model(rates: pd.Series) -> ForecastModel:
    """Train ARIMA, falling back to Prophet on failure.

    Raises :class:`InsufficientDataError` when the series has fewer than
    :data:`MIN_DATA_POINTS` values.
    """
    clean = rates.dropna()
    if len(clean) < MIN_DATA_POINTS:
        raise InsufficientDataError(
            f"Need at least {MIN_DATA_POINTS} data points, got {len(clean)}"
        )

    try:
        model = ARIMAModel(clean)
        model.fit()
        logger.info("ARIMA model trained successfully")
        return model
    except Exception as exc:
        logger.warning("ARIMA failed (%s); falling back to Prophet", exc)
        model = ProphetModel(clean)
        model.fit()
        logger.info("Prophet model trained as fallback")
        return model