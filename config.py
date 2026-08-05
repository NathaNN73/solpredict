"""Central configuration for SolPredict MVP.

Holds API endpoints, alerting thresholds, cache TTLs, and on-disk data paths.
Keeping these in one module makes the rest of the codebase testable and
tunable without scattered magic values.
"""

from pathlib import Path

# --- Project paths ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
RATES_CSV = DATA_DIR / "rates.csv"
FORECAST_JSON = DATA_DIR / "forecast.json"
ALERTS_JSON = DATA_DIR / "alerts.json"

# --- API endpoints (prioritized fallback chain) ----------------------------
SUNAT_ENDPOINT = "https://api.apis.net.pe/v1/tipo-cambio-sunat"
CDN_ENDPOINT = (
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"
)
BACKUP_ENDPOINT = "https://api.exchangerate-api.com/v4/latest/PEN"

# CDN historical endpoint template; {date} is replaced with YYYY-MM-DD.
CDN_HISTORICAL_TEMPLATE = (
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date}/v1/currencies/usd.json"
)

# --- Alerting thresholds ----------------------------------------------------
BUY_SIGNAL_THRESHOLD = 0.015  # 1.5% predicted increase triggers a BUY signal
VOLATILITY_MULTIPLIER = 2.0   # 14d std must exceed 2x the 30d avg std => LOW confidence

# --- Cache and dedup TTLs --------------------------------------------------
FORECAST_CACHE_TTL_HOURS = 12
ALERT_DEDUP_HOURS = 24

# --- Rate validation bounds (reasonable USD/PEN range) --------------------
RATE_MIN = 2.0
RATE_MAX = 5.0

# --- Backfill configuration ------------------------------------------------
MAX_BACKFILL_DAYS = 90
GAP_THRESHOLD_DAYS = 3  # gaps strictly greater than this trigger a backfill