"""SolPredict MVP — USD/PEN Exchange Rate Dashboard.

Streamlit web app that displays current rates, historical trends, ML
forecasts with confidence bands, volatility metrics, and smart buy alerts.

Usage:
    streamlit run app.py
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from alerts import confidence as alert_confidence
from alerts import state as alert_state
from data_collection import backfill, storage
from data_collection.fetcher import FetchError, fetch_current_rate

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SolPredict — USD/PEN",
    page_icon="💰",
    layout="wide",
)

st.title("💰 SolPredict — USD/PEN Exchange Rate Tracker")
st.caption("Smart alerts for buying dollars at the right moment.")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_stale(fetched_at_str: str | None, hours: int = 24) -> bool:
    """Return True when the fetch timestamp is older than ``hours``."""
    if fetched_at_str is None:
        return True
    try:
        ts = datetime.fromisoformat(fetched_at_str)
    except (ValueError, TypeError):
        return True
    return datetime.now() - ts > timedelta(hours=hours)


def _volatility_color(vol_14d: float, vol_30d_avg: float) -> str:
    """Return CSS color for volatility: green / orange / red."""
    if vol_30d_avg == 0:
        return "green"
    ratio = vol_14d / vol_30d_avg
    if ratio > 2.0:
        return "red"
    if ratio > 1.0:
        return "orange"
    return "green"


def _compute_volatility_metrics(df: pd.DataFrame) -> dict:
    """Return {vol_14d, vol_30d_avg, color} from stored rates."""
    rates = df.set_index("date")["rate"].astype(float)
    if len(rates.dropna()) < 14:
        return {"vol_14d": 0.0, "vol_30d_avg": 0.0, "color": "green"}
    recent = rates.tail(14)
    vol_14d = float(recent.std())
    if len(rates.dropna()) < 30:
        return {"vol_14d": vol_14d, "vol_30d_avg": vol_14d, "color": "green"}
    baseline = rates.tail(30)
    vol_30d_avg = float(baseline.rolling(14).std().mean())
    return {
        "vol_14d": round(vol_14d, 4),
        "vol_30d_avg": round(vol_30d_avg, 4),
        "color": _volatility_color(vol_14d, vol_30d_avg),
    }


# ---------------------------------------------------------------------------
# Data pipeline
# ---------------------------------------------------------------------------


@st.cache_data(ttl=3600)
def _read_rates():
    return storage.read_rates()


def _refresh_data():
    """Fetch current rate + backfill, then clear caches."""
    try:
        rate, source = fetch_current_rate()
        today_str = datetime.now().strftime("%Y-%m-%d")
        storage.append_rate(today_str, rate, source)
        st.success(f"Rate fetched: {rate:.4f} PEN/USD (source: {source})")
    except FetchError as exc:
        st.error(f"All sources failed:\n{chr(10).join(exc.failed_sources)}")
        return

    backfill.backfill_if_needed()
    _read_rates.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Sidebar — controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Refresh Data", use_container_width=True):
        with st.spinner("Fetching latest rates..."):
            _refresh_data()

    st.divider()
    st.caption(f"Buy threshold: {config.BUY_SIGNAL_THRESHOLD:.1%}")
    st.caption(f"Volatility multiplier: {config.VOLATILITY_MULTIPLIER:.1f}x")
    st.caption(f"Forecast cache: {config.FORECAST_CACHE_TTL_HOURS}h")
    st.caption(f"Alert dedup: {config.ALERT_DEDUP_HOURS}h")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df = _read_rates()

if df.empty:
    st.warning("No data yet. Click **Refresh Data** to fetch rates from SUNAT.")
    st.stop()

# ---------------------------------------------------------------------------
# Row 1 — Current Rate + Alert
# ---------------------------------------------------------------------------
col_rate, col_alert = st.columns([1, 1])

with col_rate:
    latest = df.iloc[-1]
    current_rate = float(latest["rate"])
    source = latest.get("source", "unknown")
    fetched = latest.get("fetched_at", None)

    st.metric(
        label=f"USD/PEN — {source.upper()}",
        value=f"S/ {current_rate:.4f}",
    )
    if fetched:
        st.caption(f"Last updated: {fetched}")
    if _is_stale(fetched):
        st.warning("Data is stale — click Refresh to update.")

with col_alert:
    alert = alert_state.get_current_alert()
    if alert["type"] == "BUY_SIGNAL":
        conf = alert.get("confidence", "NORMAL")
        peak = alert.get("predicted_peak", 0)
        day = alert.get("peak_day", 0)
        if conf == "LOW":
            st.warning(
                f"#### Buy Signal (Low Confidence)\n\n"
                f"Predicted peak: **S/ {peak:.4f}** on day {day}\n\n"
                f"High market volatility — forecast less reliable."
            )
        else:
            st.success(
                f"#### Buy Signal\n\n"
                f"Predicted peak: **S/ {peak:.4f}** on day {day}\n\n"
                f"Favorable window detected."
            )
    else:
        st.info("#### No Action\n\nNo favorable buying window detected.")

# ---------------------------------------------------------------------------
# Row 2 — Volatility
# ---------------------------------------------------------------------------
vol = _compute_volatility_metrics(df)
vol_label_map = {"green": "Normal", "orange": "Elevated", "red": "High"}
vol_icon_map = {"green": "🟢", "orange": "🟠", "red": "🔴"}

st.metric(
    label=f"Volatility (14-day) — {vol_label_map[vol['color']]} {vol_icon_map[vol['color']]}",
    value=f"{vol['vol_14d']:.4f}",
    delta=f"30d avg: {vol['vol_30d_avg']:.4f}",
)
if vol["color"] == "red":
    st.warning("High volatility — forecasts less reliable.")
elif vol["color"] == "orange":
    st.info("Elevated volatility — monitor closely.")

# ---------------------------------------------------------------------------
# Row 3 — Historical Chart + Forecast
# ---------------------------------------------------------------------------
st.subheader("Historical Rates & Forecast")

rates = df.set_index("date")["rate"].astype(float)
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=rates.index,
        y=rates.values,
        mode="lines",
        name="Historical",
        line=dict(color="#1f77b4", width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>S/ %{y:.4f}<extra></extra>",
    )
)

# Add forecast overlay if available
try:
    from forecasting import cache as fc_cache

    forecast = fc_cache.get_forecast()
    preds = forecast.get("predictions", [])
    if preds:
        fc_dates = [pd.Timestamp(p["date"]) for p in preds]
        fc_values = [p["predicted"] for p in preds]
        fc_lower_80 = [p["lower_80"] for p in preds]
        fc_upper_80 = [p["upper_80"] for p in preds]
        fc_lower_95 = [p["lower_95"] for p in preds]
        fc_upper_95 = [p["upper_95"] for p in preds]

        # 95% band (wider, lighter)
        fig.add_trace(
            go.Scatter(
                x=fc_dates + fc_dates[::-1],
                y=fc_upper_95 + fc_lower_95[::-1],
                fill="toself",
                fillcolor="rgba(31,119,180,0.1)",
                line=dict(width=0),
                name="95% confidence",
                hoverinfo="skip",
            )
        )
        # 80% band (narrower, darker)
        fig.add_trace(
            go.Scatter(
                x=fc_dates + fc_dates[::-1],
                y=fc_upper_80 + fc_lower_80[::-1],
                fill="toself",
                fillcolor="rgba(31,119,180,0.25)",
                line=dict(width=0),
                name="80% confidence",
                hoverinfo="skip",
            )
        )
        # Forecast line
        fig.add_trace(
            go.Scatter(
                x=fc_dates,
                y=fc_values,
                mode="lines+markers",
                name=f"Forecast ({forecast.get('model', '?')})",
                line=dict(color="#ff7f0e", width=2, dash="dash"),
                hovertemplate="%{x|%Y-%m-%d}<br>S/ %{y:.4f}<extra></extra>",
            )
        )

        mape = forecast.get("mape", 0)
        fig.add_annotation(
            x=fc_dates[0],
            y=fc_values[0],
            text=f"MAPE: {mape:.1f}%",
            showarrow=True,
            arrowhead=1,
            ax=40,
            ay=-30,
            font=dict(size=11, color="gray"),
        )

except (ValueError, ImportError):
    st.caption("Forecast unavailable — need more historical data.")

fig.update_layout(
    xaxis_title="Date",
    yaxis_title="PEN per USD",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=0, r=0, t=30, b=0),
    height=450,
)
fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.15)")
fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.15)")

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "SolPredict MVP — Data from SUNAT, CDN currency-api, and ExchangeRate-API. "
    "Forecasts are estimates, not financial advice."
)
