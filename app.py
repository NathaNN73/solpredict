"""SolPredict — Tipo de cambio USD/PEN con predicciones ML.

Panel de monitoreo del sol peruano frente al dólar. Usa modelos ARIMA/Prophet
para proyectar el tipo de cambio a 7 días y detectar ventanas favorables de compra.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from alerts import state as alert_state
from data_collection import backfill, storage
from data_collection.fetcher import FetchError, fetch_current_rate

# ---------------------------------------------------------------------------
# Estilos globales
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SolPredict — USD/PEN",
    page_icon="📈",
    layout="wide",
)

st.markdown("""
<style>
    /* Título principal sin padding extra */
    .main-header {
        padding-top: 0;
        margin-top: -3rem;
    }
    .main-header h1 {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a1a2e;
    }
    /* Cards con sombra suave */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e8ecf1;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .metric-card .label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #6b7280;
        margin-bottom: 0.25rem;
    }
    .metric-card .value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #111827;
    }
    .metric-card .source {
        font-size: 0.7rem;
        color: #9ca3af;
        margin-top: 0.25rem;
    }
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #f8fafc;
        border-right: 1px solid #e8ecf1;
    }
    /* Ocultar decoraciones de Streamlit */
    #MainMenu, footer, header[data-testid="stHeader"] {
        display: none;
    }
    /* Alertas con borde izquierdo */
    .alert-success {
        border-left: 4px solid #10b981;
        background: #ecfdf5;
        padding: 1rem 1.25rem;
        border-radius: 0 8px 8px 0;
    }
    .alert-warning {
        border-left: 4px solid #f59e0b;
        background: #fffbeb;
        padding: 1rem 1.25rem;
        border-radius: 0 8px 8px 0;
    }
    .alert-info {
        border-left: 4px solid #3b82f6;
        background: #eff6ff;
        padding: 1rem 1.25rem;
        border-radius: 0 8px 8px 0;
    }
    /* Footer */
    .app-footer {
        text-align: center;
        color: #9ca3af;
        font-size: 0.75rem;
        padding-top: 2rem;
    }
    /* Divider */
    hr {
        margin: 1.5rem 0;
        border-color: #e8ecf1;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


def _fmt_ts(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        ts = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso
    return f"{ts.day} {MESES[ts.month - 1]} {ts.year}, {ts.strftime('%H:%M')}"


def _is_stale(iso: str | None, hours: int = 24) -> bool:
    if iso is None:
        return True
    try:
        ts = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return True
    return datetime.now() - ts > timedelta(hours=hours)


def _vol_color(vol_14d: float, vol_30d_avg: float) -> str:
    if vol_30d_avg == 0:
        return "green"
    r = vol_14d / vol_30d_avg
    if r > 2.0:
        return "red"
    if r > 1.0:
        return "orange"
    return "green"


def _vol_metrics(df: pd.DataFrame) -> dict:
    rates = df.set_index("date")["rate"].astype(float)
    if len(rates.dropna()) < 14:
        return {"v14": 0.0, "v30": 0.0, "color": "green"}
    v14 = float(rates.tail(14).std())
    if len(rates.dropna()) < 30:
        return {"v14": v14, "v30": v14, "color": "green"}
    v30 = float(rates.tail(30).rolling(14).std().mean())
    return {"v14": round(v14, 4), "v30": round(v30, 4), "color": _vol_color(v14, v30)}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def _load_rates():
    return storage.read_rates()


def _refrescar():
    try:
        rate, source = fetch_current_rate()
        storage.append_rate(datetime.now().strftime("%Y-%m-%d"), rate, source)
        st.toast(f"Tipo de cambio actualizado: S/ {rate:.4f}", icon="✅")
    except FetchError as exc:
        st.error(f"No se pudo obtener el tipo de cambio.\n\n{chr(10).join(exc.failed_sources)}")
        return
    backfill.backfill_if_needed()
    _load_rates.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
c1, c2 = st.columns([4, 1])
with c1:
    st.markdown('<div class="main-header"><h1>SolPredict</h1></div>', unsafe_allow_html=True)
    st.caption("Tipo de cambio USD/PEN · Predicciones · Alertas de compra")
with c2:
    st.button("Actualizar ahora", on_click=_refrescar, use_container_width=True,
              type="primary", icon="🔄")

st.markdown("<hr>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
df = _load_rates()

if df.empty:
    st.info("##### Todavía no hay datos.\n\nHacé clic en **Actualizar ahora** para traer el tipo de cambio de SUNAT y cargar el histórico de los últimos 90 días.", icon="ℹ️")
    st.stop()

# ---------------------------------------------------------------------------
# Fila 1 — Tasa actual + Señal
# ---------------------------------------------------------------------------
left, right = st.columns([1, 1])

latest = df.iloc[-1]
current_rate = float(latest["rate"])
source = latest.get("source", "?")
fetched = latest.get("fetched_at", None)
alert = alert_state.get_current_alert()

with left:
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">USD/PEN &middot; {source.upper()}</div>
        <div class="value">S/ {current_rate:.4f}</div>
        <div class="source">Actualizado {_fmt_ts(fetched)}</div>
    </div>
    """, unsafe_allow_html=True)
    if _is_stale(fetched):
        st.caption("⚠️ Datos con más de 24 h — actualizá para ver la tasa del día.")

with right:
    if alert["type"] == "BUY_SIGNAL":
        conf = alert.get("confidence", "NORMAL")
        trough = alert.get("predicted_trough", 0)
        day = alert.get("trough_day", 0)
        if conf == "LOW":
            cls = "alert-warning"
            title = "Señal de compra · Confianza baja"
            body = (
                f"El modelo proyecta que el dólar bajaría a "
                f"**S/ {trough:.4f}** en el día {day}.<br><br>"
                f"⚠️ La volatilidad está elevada — tomá la predicción con cautela."
            )
        else:
            cls = "alert-success"
            title = "Señal de compra"
            body = (
                f"El modelo proyecta que el dólar bajaría a "
                f"**S/ {trough:.4f}** en el día {day}.<br><br>"
                f"Ventana favorable detectada."
            )
        st.markdown(f'<div class="{cls}"><strong>{title}</strong><br><span style="font-size:0.9rem;color:#374151;">{body}</span></div>', unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="alert-info">
            <strong>Sin señales activas</strong><br>
            <span style="font-size:0.9rem;color:#374151;">
            Por ahora no se detecta una ventana clara de compra. El modelo
            evalúa la tendencia cada vez que actualizás los datos.
            </span>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Fila 2 — Volatilidad + métricas rápidas
# ---------------------------------------------------------------------------
vol = _vol_metrics(df)
vol_labels = {"green": "Normal", "orange": "Elevada", "red": "Alta"}
cols = st.columns(4)

cols[0].metric("Volatilidad 14d", f"{vol['v14']:.4f}",
               delta=f"Promedio 30d: {vol['v30']:.4f}",
               delta_color="off" if vol["color"] == "green" else "inverse")
cols[1].metric("Máximo 90d", f"S/ {float(df['rate'].max()):.4f}")
cols[2].metric("Mínimo 90d", f"S/ {float(df['rate'].min()):.4f}")
cols[3].metric("Días con datos", len(df))

if vol["color"] == "red":
    st.warning("La volatilidad está **alta** — las predicciones en mercados turbulentos son menos confiables.", icon="⚠️")
elif vol["color"] == "orange":
    st.info("La volatilidad está **elevada** — conviene monitorear de cerca.", icon="ℹ️")

# ---------------------------------------------------------------------------
# Gráfico
# ---------------------------------------------------------------------------
st.subheader("Histórico y proyección a 7 días")

rates = df.set_index("date")["rate"].astype(float)
fig = go.Figure()

# Línea histórica
fig.add_trace(go.Scatter(
    x=rates.index, y=rates.values, mode="lines", name="Histórico",
    line=dict(color="#2563eb", width=2.2),
    hovertemplate="%{x|%d %b %Y}<br>S/ %{y:.4f}<extra></extra>",
))

# Forecast
try:
    from forecasting import cache as fc_cache
    fc = fc_cache.get_forecast()
    preds = fc.get("predictions", [])
    if preds:
        fd = [pd.Timestamp(p["date"]) for p in preds]
        fv = [p["predicted"] for p in preds]
        l80 = [p["lower_80"] for p in preds]
        u80 = [p["upper_80"] for p in preds]
        l95 = [p["lower_95"] for p in preds]
        u95 = [p["upper_95"] for p in preds]

        fig.add_trace(go.Scatter(
            x=fd + fd[::-1], y=u95 + l95[::-1], fill="toself",
            fillcolor="rgba(37,99,235,0.08)", line=dict(width=0),
            name="Intervalo 95%", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=fd + fd[::-1], y=u80 + l80[::-1], fill="toself",
            fillcolor="rgba(37,99,235,0.18)", line=dict(width=0),
            name="Intervalo 80%", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=fd, y=fv, mode="lines+markers",
            name=f"Proyección ({fc.get('model','?')})",
            line=dict(color="#f59e0b", width=2.2, dash="dash"),
            marker=dict(size=5),
            hovertemplate="%{x|%d %b %Y}<br>S/ %{y:.4f}<extra></extra>",
        ))
        mape = fc.get("mape", 0)
        fig.add_annotation(x=fd[0], y=fv[0], text=f"Error est. MAPE {mape:.1f}%",
                           showarrow=True, arrowhead=1, ax=50, ay=-35,
                           font=dict(size=10, color="#6b7280"))
except (ValueError, ImportError):
    st.caption("Proyección no disponible — se necesitan al menos 14 días de datos.")

fig.update_layout(
    xaxis_title=None, yaxis_title="Soles por dólar",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1,
                font=dict(size=11)),
    margin=dict(l=0, r=0, t=10, b=0), height=420,
    plot_bgcolor="#fafbfc", paper_bgcolor="#ffffff",
)
fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#e5e7eb",
                 zeroline=False, showline=True, linecolor="#d1d5db")
fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#e5e7eb",
                 zeroline=False, showline=True, linecolor="#d1d5db")
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("""
<div class="app-footer">
    SolPredict · Datos de SUNAT, CDN y ExchangeRate-API ·
    Las proyecciones son estimaciones estadísticas, no asesoría financiera.
</div>
""", unsafe_allow_html=True)
