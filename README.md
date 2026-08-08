# SolPredict

USD/PEN exchange rate tracker with ML forecasting and smart buy alerts.

Track the Peruvian Sol against the US Dollar, get 7-day ARIMA/Prophet predictions with confidence bands, and receive intelligent alerts when the model detects a favorable buying window.

## Quick Start

```bash
# 1. Clone and set up virtual environment
git clone https://github.com/NathaNN73/solpredict.git
cd solpredict
python -m venv .venv

# 2. Activate (Windows)
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
streamlit run app.py
```

Click **Refresh Data** on first run to fetch rates from SUNAT and backfill 90 days of historical data.


### Data Sources

| Source | Priority | What It Provides |
|---|---|---|
| SUNAT (apis.net.pe) | Primary | Official Peruvian tax authority rates — `compra` and `venta` |
| CDN currency-api | Historical + fallback | Free daily snapshots, no API key, unlimited backfill |
| ExchangeRate-API | Backup | Last-resort current rate, free tier 1500 req/month |

All sources are tried in order. If one fails, the next is used automatically.

### Forecasting

- **ARIMA(1,1,1)** is the default model — fast, interpretable, works well for short forex windows
- **Prophet** (Meta) is the automatic fallback if ARIMA fails to converge
- 7-day forecast with 80% and 95% confidence bands
- MAPE (Mean Absolute Percentage Error) computed on 7-day holdout
- Results cached for 12 hours to avoid redundant training

### Smart Alerts

A **Buy Signal** fires when both conditions are met:
1. The forecast predicts at least a **1.5% increase** within 7 days
2. The predicted trend is **monotonically increasing for 3+ consecutive days**

Confidence is adjusted by volatility:
- **Normal**: market is stable, forecast is reliable
- **Low**: recent volatility is 2× the 30-day average — proceed with caution

Alerts are deduplicated within a 24-hour window.

## Configuration

All tunable parameters live in `config.py`:

| Parameter | Default | Description |
|---|---|---|
| `BUY_SIGNAL_THRESHOLD` | 1.5% | Minimum predicted increase to trigger an alert |
| `VOLATILITY_MULTIPLIER` | 2.0× | 14d volatility must exceed this multiple of 30d avg to downgrade confidence |
| `FORECAST_CACHE_TTL_HOURS` | 12h | How long a forecast is considered fresh |
| `ALERT_DEDUP_HOURS` | 24h | Minimum time between alerts of the same type |
| `MAX_BACKFILL_DAYS` | 90 | Historical data window |
| `RATE_MIN` / `RATE_MAX` | 2.0 / 5.0 | Validation bounds for fetched rates |



## API Reliability

All three data sources are free and have been tested working as of August 2026. The app handles failures gracefully:

- Individual API failures: automatic fallback to the next source
- All sources down: error message shown, rates.csv preserved
- Corrupt cache files: regenerated automatically
- Insufficient data: informational message, no crash

## License

MIT — see [LICENSE](LICENSE).
