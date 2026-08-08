"""SolPredict MVP — Panel de tipo de cambio USD/PEN.

Aplicación web con Streamlit que muestra el tipo de cambio actual, tendencias
históricas, predicciones ML con bandas de confianza, volatilidad y alertas
inteligentes de compra.

Uso:
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
# Configuración de página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SolPredict — USD/PEN",
    page_icon="💰",
    layout="wide",
)

st.title("💰 SolPredict — Tipo de Cambio USD/PEN")
st.caption("Alertas inteligentes para comprar dólares en el momento justo.")

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _is_stale(fetched_at_str: str | None, hours: int = 24) -> bool:
    """True si el timestamp tiene más de ``hours`` horas de antigüedad."""
    if fetched_at_str is None:
        return True
    try:
        ts = datetime.fromisoformat(fetched_at_str)
    except (ValueError, TypeError):
        return True
    return datetime.now() - ts > timedelta(hours=hours)


def _volatility_color(vol_14d: float, vol_30d_avg: float) -> str:
    """Color semáforo: verde / naranja / rojo."""
    if vol_30d_avg == 0:
        return "green"
    ratio = vol_14d / vol_30d_avg
    if ratio > 2.0:
        return "red"
    if ratio > 1.0:
        return "orange"
    return "green"


def _compute_volatility_metrics(df: pd.DataFrame) -> dict:
    """Devuelve {vol_14d, vol_30d_avg, color} desde los datos almacenados."""
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
# Pipeline de datos
# ---------------------------------------------------------------------------


@st.cache_data(ttl=3600)
def _read_rates():
    return storage.read_rates()


def _refresh_data():
    """Obtiene tipo de cambio actual + backfill, luego limpia cachés."""
    try:
        rate, source = fetch_current_rate()
        today_str = datetime.now().strftime("%Y-%m-%d")
        storage.append_rate(today_str, rate, source)
        st.success(f"Tipo de cambio obtenido: {rate:.4f} PEN/USD (fuente: {source})")
    except FetchError as exc:
        st.error(f"Todas las fuentes fallaron:\n{chr(10).join(exc.failed_sources)}")
        return

    backfill.backfill_if_needed()
    _read_rates.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Barra lateral — controles
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Controles")
    if st.button("🔄 Actualizar datos", use_container_width=True):
        with st.spinner("Obteniendo tipo de cambio..."):
            _refresh_data()

    st.divider()
    st.caption(f"Umbral de compra: {config.BUY_SIGNAL_THRESHOLD:.1%}")
    st.caption(f"Multiplicador de volatilidad: {config.VOLATILITY_MULTIPLIER:.1f}x")
    st.caption(f"Caché de predicción: {config.FORECAST_CACHE_TTL_HOURS}h")
    st.caption(f"Anti-spam de alertas: {config.ALERT_DEDUP_HOURS}h")

# ---------------------------------------------------------------------------
# Cargar datos
# ---------------------------------------------------------------------------
df = _read_rates()

if df.empty:
    st.warning("Sin datos todavía. Hacé clic en **Actualizar datos** para obtener el tipo de cambio de SUNAT.")
    st.stop()

# ---------------------------------------------------------------------------
# Fila 1 — Tipo de cambio actual + Alerta
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
        st.caption(f"Última actualización: {fetched}")
    if _is_stale(fetched):
        st.warning("⚠️ Datos desactualizados — hacé clic en Actualizar.")

with col_alert:
    alert = alert_state.get_current_alert()
    if alert["type"] == "BUY_SIGNAL":
        conf = alert.get("confidence", "NORMAL")
        trough = alert.get("predicted_trough", 0)
        day = alert.get("trough_day", 0)
        if conf == "LOW":
            st.warning(
                f"#### 🟡 Señal de compra (confianza baja)\n\n"
                f"Mínimo estimado: **S/ {trough:.4f}** en el día {day}\n\n"
                f"⚠️ Alta volatilidad — la predicción es menos confiable."
            )
        else:
            st.success(
                f"#### 🟢 Señal de compra\n\n"
                f"Mínimo estimado: **S/ {trough:.4f}** en el día {day}\n\n"
                f"El dólar está bajando — ventana favorable detectada."
            )
    else:
        st.info("#### 🔵 Sin acción\n\nNo se detectó una ventana de compra favorable.")

# ---------------------------------------------------------------------------
# Fila 2 — Volatilidad
# ---------------------------------------------------------------------------
vol = _compute_volatility_metrics(df)
vol_label_map = {"green": "Normal", "orange": "Elevada", "red": "Alta"}
vol_icon_map = {"green": "🟢", "orange": "🟠", "red": "🔴"}

st.metric(
    label=f"Volatilidad (14 días) — {vol_label_map[vol['color']]} {vol_icon_map[vol['color']]}",
    value=f"{vol['vol_14d']:.4f}",
    delta=f"Promedio 30d: {vol['vol_30d_avg']:.4f}",
)
if vol["color"] == "red":
    st.warning("⚠️ Alta volatilidad — las predicciones son menos confiables.")
elif vol["color"] == "orange":
    st.info("⚠️ Volatilidad elevada — monitoreá de cerca.")

# ---------------------------------------------------------------------------
# Fila 3 — Gráfico histórico + predicción
# ---------------------------------------------------------------------------
st.subheader("Histórico y predicción")

rates = df.set_index("date")["rate"].astype(float)
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=rates.index,
        y=rates.values,
        mode="lines",
        name="Histórico",
        line=dict(color="#1f77b4", width=2),
        hovertemplate="%{x|%d/%m/%Y}<br>S/ %{y:.4f}<extra></extra>",
    )
)

# Agregar predicción si está disponible
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

        # Banda 95% (más ancha, más clara)
        fig.add_trace(
            go.Scatter(
                x=fc_dates + fc_dates[::-1],
                y=fc_upper_95 + fc_lower_95[::-1],
                fill="toself",
                fillcolor="rgba(31,119,180,0.1)",
                line=dict(width=0),
                name="Confianza 95%",
                hoverinfo="skip",
            )
        )
        # Banda 80% (más angosta, más oscura)
        fig.add_trace(
            go.Scatter(
                x=fc_dates + fc_dates[::-1],
                y=fc_upper_80 + fc_lower_80[::-1],
                fill="toself",
                fillcolor="rgba(31,119,180,0.25)",
                line=dict(width=0),
                name="Confianza 80%",
                hoverinfo="skip",
            )
        )
        # Línea de predicción
        fig.add_trace(
            go.Scatter(
                x=fc_dates,
                y=fc_values,
                mode="lines+markers",
                name=f"Predicción ({forecast.get('model', '?')})",
                line=dict(color="#ff7f0e", width=2, dash="dash"),
                hovertemplate="%{x|%d/%m/%Y}<br>S/ %{y:.4f}<extra></extra>",
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
    st.caption("⚠️ Predicción no disponible — se necesitan más datos históricos.")

fig.update_layout(
    xaxis_title="Fecha",
    yaxis_title="PEN por USD",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=0, r=0, t=30, b=0),
    height=450,
)
fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.15)")
fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.15)")

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Pie de página
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "SolPredict MVP — Datos de SUNAT, CDN currency-api y ExchangeRate-API. "
    "Las predicciones son estimaciones, no constituyen asesoría financiera."
)
