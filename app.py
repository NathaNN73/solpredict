"""SolPredict — Tipo de cambio USD/PEN con predicciones ML."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from alerts import state as alert_state
from data_collection import backfill, storage
from data_collection.fetcher import FetchError, fetch_current_rate

st.set_page_config(page_title="SolPredict", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: #0f1117; }
    section[data-testid="stSidebar"] { display: none; }
    .block-container { padding-top: 1.5rem; }
    #MainMenu, footer, header[data-testid="stHeader"] { display: none; }

    .header-row { display:flex; align-items:center; justify-content:space-between; margin-bottom:1.5rem; }
    .header-row h1 { font-size:1.5rem; font-weight:600; color:#e4e6f0; letter-spacing:-0.02em; margin:0; }
    .header-config { font-size:0.68rem; color:#4b5068; }
    .header-config span { margin-left:1rem; }

    .card-rate { background:#161822; border:1px solid #1e2030; border-radius:10px; padding:1.25rem 1.5rem; }
    .card-rate .label { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.08em; color:#6b708a; margin-bottom:0.35rem; }
    .card-rate .value { font-size:2rem; font-weight:700; color:#f0f0f5; letter-spacing:-0.02em; line-height:1.1; }
    .card-rate .meta { font-size:0.7rem; color:#4b5068; margin-top:0.4rem; }

    .signal { border-radius:10px; padding:1.25rem 1.5rem; border:1px solid #1e2030; }
    .signal-buy { background:#0d2818; border-color:#1a4d2e; }
    .signal-buy .sig-title { color:#4ade80; }
    .signal-buy .sig-body { color:#86efac; }
    .signal-warn { background:#2d1f0d; border-color:#5c3d0e; }
    .signal-warn .sig-title { color:#fbbf24; }
    .signal-warn .sig-body { color:#fde68a; }
    .signal-none { background:#161822; border-color:#1e2030; }
    .signal-none .sig-title { color:#6b708a; }
    .signal-none .sig-body { color:#4b5068; }
    .sig-title { font-weight:600; font-size:0.9rem; margin-bottom:0.35rem; }
    .sig-body { font-size:0.82rem; line-height:1.5; }

    div[data-testid="stMetric"] { background:#161822; border:1px solid #1e2030; border-radius:10px; padding:0.85rem 1rem; }
    div[data-testid="stMetric"] label { color:#6b708a !important; font-size:0.7rem !important; text-transform:uppercase; letter-spacing:0.06em; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color:#e4e6f0 !important; font-size:1.1rem !important; font-weight:600; }
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] { font-size:0.72rem; color:#4b5068 !important; }

    div[data-testid="stButton"] button { background:#2563eb; color:white; border:none; border-radius:8px; font-weight:500; font-size:0.82rem; padding:0.4rem 1rem; }
    div[data-testid="stButton"] button:hover { background:#3b82f6; }
    .footer { text-align:center; color:#2e3247; font-size:0.7rem; padding-top:3rem; }
</style>
""", unsafe_allow_html=True)

MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]

def _fmt_ts(iso):
    if not iso: return "—"
    try: ts = datetime.fromisoformat(iso)
    except: return iso
    return f"{ts.day} {MESES[ts.month-1]} {ts.year}, {ts.strftime('%H:%M')}"

def _is_stale(iso, h=24):
    if iso is None: return True
    try: ts = datetime.fromisoformat(iso)
    except: return True
    return datetime.now() - ts > timedelta(hours=h)

def _vol_color(v14, v30):
    if v30 == 0: return "green"
    r = v14/v30
    if r > 2.0: return "red"
    if r > 1.0: return "orange"
    return "green"

def _vol_metrics(df):
    rates = df.set_index("date")["rate"].astype(float)
    if len(rates.dropna()) < 14: return {"v14":0,"v30":0,"color":"green"}
    v14 = float(rates.tail(14).std())
    if len(rates.dropna()) < 30: return {"v14":v14,"v30":v14,"color":"green"}
    v30 = float(rates.tail(30).rolling(14).std().mean())
    return {"v14":round(v14,4),"v30":round(v30,4),"color":_vol_color(v14,v30)}

@st.cache_data(ttl=3600)
def _load(): return storage.read_rates()

def _refrescar():
    try:
        rate, source = fetch_current_rate()
        storage.append_rate(datetime.now().strftime("%Y-%m-%d"), rate, source)
        st.toast(f"Tasa actualizada: S/ {rate:.4f}", icon="✅")
    except FetchError as exc:
        st.error(f"No se pudo obtener el tipo de cambio.\n\n{chr(10).join(exc.failed_sources)}")
        return
    backfill.backfill_if_needed()
    _load.clear()

# ── Header ──
st.markdown(f"""
<div class="header-row">
    <div>
        <h1>SolPredict</h1>
        <div style="font-size:0.78rem;color:#6b708a;margin-top:0.25rem;">USD/PEN · proyección a 7 días · señales de compra</div>
    </div>
    <div style="text-align:right;">
""", unsafe_allow_html=True)
col_btn, _ = st.columns([1,3])
with col_btn: st.button("Actualizar", on_click=_refrescar, type="primary", use_container_width=True)
st.markdown(f"""
        <div class="header-config">
            <span>Umbral {config.BUY_SIGNAL_THRESHOLD:.1%}</span>
            <span>Volatilidad {config.VOLATILITY_MULTIPLIER:.0f}x</span>
            <span>Caché {config.FORECAST_CACHE_TTL_HOURS}h</span>
            <span>Anti-spam {config.ALERT_DEDUP_HOURS}h</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

df = _load()
if df.empty:
    st.info("Todavía no hay datos. Hacé clic en **Actualizar** para empezar.")
    st.stop()

latest = df.iloc[-1]
current_rate = float(latest["rate"])
source = latest.get("source","?")
fetched = latest.get("fetched_at")
alert = alert_state.get_current_alert()

a, b = st.columns([1,1])
with a:
    st.markdown(f"""<div class="card-rate"><div class="label">{source.upper()}</div><div class="value">S/ {current_rate:.4f}</div><div class="meta">{_fmt_ts(fetched)}</div></div>""", unsafe_allow_html=True)
with b:
    if alert["type"] == "BUY_SIGNAL":
        conf = alert.get("confidence","NORMAL")
        t, d = alert.get("predicted_trough",0), alert.get("trough_day",0)
        if conf == "LOW":
            cls, title = "signal signal-warn", "Señal de compra · Confianza baja"
            body = f"El modelo proyecta un mínimo de <b>S/ {t:.4f}</b> en el día {d}.<br>La volatilidad está elevada — precaución."
        else:
            cls, title = "signal signal-buy", "Señal de compra"
            body = f"El modelo proyecta un mínimo de <b>S/ {t:.4f}</b> en el día {d}.<br>El dólar está bajando — ventana favorable."
        st.markdown(f'<div class="{cls}"><div class="sig-title">{title}</div><div class="sig-body">{body}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown("""<div class="signal signal-none"><div class="sig-title">Sin señales activas</div><div class="sig-body">No se detecta una ventana clara de compra en este momento.</div></div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
vol = _vol_metrics(df)
m1,m2,m3,m4 = st.columns(4)
m1.metric("Volatilidad 14d", f"{vol['v14']:.4f}", delta=f"Media 30d {vol['v30']:.4f}", delta_color="off")
m2.metric("Máximo 90d", f"S/ {float(df['rate'].max()):.4f}")
m3.metric("Mínimo 90d", f"S/ {float(df['rate'].min()):.4f}")
m4.metric("Observaciones", len(df))
if vol["color"] == "red": st.caption("⚠️ Volatilidad alta — las proyecciones son menos confiables.")
elif vol["color"] == "orange": st.caption("⚠️ Volatilidad elevada — conviene monitorear de cerca.")

st.markdown("<br>", unsafe_allow_html=True)
st.subheader("Histórico y proyección")
rates = df.set_index("date")["rate"].astype(float)
fig = go.Figure()
fig.add_trace(go.Scatter(x=rates.index, y=rates.values, mode="lines", name="Histórico", line=dict(color="#60a5fa", width=1.8), hovertemplate="%{x|%d %b %Y}<br>S/ %{y:.4f}<extra></extra>"))
try:
    from forecasting import cache as fc_cache
    fc = fc_cache.get_forecast()
    preds = fc.get("predictions",[])
    if preds:
        fd = [pd.Timestamp(p["date"]) for p in preds]
        fv = [p["predicted"] for p in preds]
        l80,u80 = [p["lower_80"] for p in preds], [p["upper_80"] for p in preds]
        l95,u95 = [p["lower_95"] for p in preds], [p["upper_95"] for p in preds]
        fig.add_trace(go.Scatter(x=fd+fd[::-1], y=u95+l95[::-1], fill="toself", fillcolor="rgba(96,165,250,0.06)", line=dict(width=0), name="95%", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fd+fd[::-1], y=u80+l80[::-1], fill="toself", fillcolor="rgba(96,165,250,0.12)", line=dict(width=0), name="80%", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fd, y=fv, mode="lines+markers", name=f"Proyección ({fc.get('model','?')})", line=dict(color="#fbbf24", width=1.8, dash="dash"), marker=dict(size=4,color="#fbbf24"), hovertemplate="%{x|%d %b %Y}<br>S/ %{y:.4f}<extra></extra>"))
except (ValueError, ImportError): pass
fig.update_layout(xaxis_title=None, yaxis_title=None, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10,color="#6b708a")), margin=dict(l=0,r=0,t=10,b=0), height=380, plot_bgcolor="#0f1117", paper_bgcolor="#0f1117", font=dict(color="#8b8fa3", size=10))
fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#1a1d2e", zeroline=False, showline=True, linecolor="#1e2030")
fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#1a1d2e", zeroline=False, showline=True, linecolor="#1e2030", tickformat=".2f")
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
st.markdown('<div class="footer">SolPredict · SUNAT · CDN · ExchangeRate-API</div>', unsafe_allow_html=True)
