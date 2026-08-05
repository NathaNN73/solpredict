# Tasks: solpredict-mvp

## Implementation Tasks

### Group 1: Setup (est. 48 lines)

| # | Task | Files | Est. Lines | Depends On | Status |
|---|------|-------|------------|------------|--------|
| T1 | Create project skeleton | `requirements.txt`, `config.py`, `data/.gitkeep`, `lib/__init__.py` | 30 | - | ✅ PR#1 |
| T2 | Create package init files and directory structure | `data_collection/__init__.py`, `forecasting/__init__.py`, `alerts/__init__.py` | 18 | T1 | ✅ PR#1 |

### Group 2: Data Collection (est. 185 lines)

| # | Task | Files | Est. Lines | Depends On | Status |
|---|------|-------|------------|------------|--------|
| T3 | Implement rate range validator | `lib/validators.py` (+ tests) | 35 | T1 | ✅ PR#1 |
| T4 | Implement multi-source fetcher with fallback chain | `data_collection/fetcher.py` (+ tests) | 70 | T1 | ✅ PR#1 |
| T5 | Implement CSV storage with dedup | `data_collection/storage.py` (+ tests) | 45 | T1 | ✅ PR#1 |
| T6 | Implement historical backfill with gap detection | `data_collection/backfill.py` (+ tests) | 60 | T4, T5 | ✅ PR#1 |

### Group 3: Forecasting (est. 170 lines)

| # | Task | Files | Est. Lines | Depends On |
|---|------|-------|------------|------------|
| T7 | Implement ARIMA and Prophet model wrappers | `forecasting/models.py` (+ tests) | 70 | T1 |
| T8 | Implement trainer with model selection and MAPE | `forecasting/trainer.py` (+ tests) | 65 | T7, T5 |
| T9 | Implement 12h forecast cache | `forecasting/cache.py` (+ tests) | 35 | T8 |

### Group 4: Alerts (est. 145 lines)

| # | Task | Files | Est. Lines | Depends On |
|---|------|-------|------------|------------|
| T10 | Implement trend detector (≥1.5% + monotonic 3d) | `alerts/detector.py` (+ tests) | 55 | T1 |
| T11 | Implement volatility-adjusted confidence | `alerts/confidence.py` (+ tests) | 40 | T1 |
| T12 | Implement alert state persistence with 24h dedup | `alerts/state.py` (+ tests) | 50 | T10, T11 |

### Group 5: Dashboard UI (est. 175 lines)

| # | Task | Files | Est. Lines | Depends On |
|---|------|-------|------------|------------|
| T13 | Rate display panel + stale data warning | `app.py` (partial) | 35 | T4, T5 |
| T14 | Historical rate chart with Plotly | `app.py` (partial) | 40 | T5, T13 |
| T15 | Forecast overlay with confidence bands | `app.py` (partial) | 45 | T9, T14 |
| T16 | Alert panel + volatility meter | `app.py` (partial) | 40 | T12, T15 |
| T17 | Manual refresh button + loading states | `app.py` (partial) | 30 | T16 |

### Group 6: Integration & Polish (est. 80 lines)

| # | Task | Files | Est. Lines | Depends On |
|---|------|-------|------------|------------|
| T18 | Integration tests (pipeline: fetch→store→train→alert) | `tests/test_integration.py` | 55 | T6, T9, T12 |
| T19 | Error handling edge cases and README | various + `README.md` | 45 | T18 |

---

## Dependency Graph

```
T1 ──┬── T2
     ├── T3 ──────────────────────────────────────────────┐
     ├── T4 ──┬── T6 ──────────────────────────────────┐  │
     │        │                                          │  │
     ├── T5 ──┼── T8 ── T9 ──────────────────────────┐  │  │
     │        │                                        │  │  │
     ├── T7 ──┘                                        │  │  │
     │                                                  │  │  │
     ├── T10 ──┬── T12 ─────────────────────────────┐  │  │  │
     │         │                                      │  │  │  │
     └── T11 ─┘                                      │  │  │  │
                                                      │  │  │  │
T13 ── T14 ── T15 ── T16 ── T17    ← Dashboard chain  │  │  │  │
  │      │      │      │                               │  │  │  │
  └──────┴──────┴──────┴───────────────────────────────┤  │  │  │
                                                        │  │  │  │
T18 ── T19   ← Integration                              │  │  │  │
  │                                                      ▼  ▼  ▼  ▼
  └── depends on: T6, T9, T12 (all backend modules done)
```

**Parallelizable clusters:**
- Group 2 (T3, T4, T5) can run in parallel after T1
- Group 3 (T7) and Group 4 (T10, T11) can run in parallel after T1
- T6 depends on T4+T5; T8 depends on T5+T7; T12 depends on T10+T11
- Dashboard (T13-T17) is strictly sequential and starts after T4+T5 are done
- Integration (T18) starts after all backend modules complete

---

## Review Workload Forecast

| Metric | Value |
|--------|-------|
| Total estimated changed lines | ~803 |
| Chained PRs recommended | Yes |
| 400-line budget risk | **High** — exceeds 2x budget |
| Decision needed before apply | Yes |

### Recommended PR Split (if chaining)

| PR | Groups | Lines | Description |
|----|--------|-------|-------------|
| PR #1 | T1-T6 | ~233 | Setup + Data Collection (skeleton + fetcher + storage + backfill) |
| PR #2 | T7-T9 | ~170 | Forecasting (models + trainer + cache) |
| PR #3 | T10-T12 | ~145 | Alert Engine (detector + confidence + state) |
| PR #4 | T13-T17 | ~175 | Dashboard UI (all Streamlit panels) |
| PR #5 | T18-T19 | ~80 | Integration tests + polish |
