# Blueprint

## Mission

Forecast Nepal (NEA) electricity demand, focused on **winter** (Nov–Apr). In winter, run-of-river hydro output drops, Kulekhani (the only storage reservoir) is drawn down, and Nepal buys power from India. Good winter forecasts = better import planning.

Forecast targets:
1. **Daily short-term:** peak demand (MW) + energy requirement (MWh), 7–30 days ahead.
2. **Winter seasonal outlook:** monthly demand vs domestic hydro supply, Nov–Apr.
3. **India import need:** net import (MWh/MW), directly and as demand − domestic generation.

All ingested data and results live in DuckLake and are queryable with DuckDB. Results are presented on a static website on Cloudflare.

## Key facts (from research, 2026-10-25)

- Daily NEA reports (NDOR) on transd.nea.org.np exist only **2023-04-14 → 2025-01-11** (639 PDFs). Two winters of daily data.
- Longer history = NEA annual + monthly/yearly operational reports (monthly/annual figures) and Wayback copies of old LDC PDFs.
- NEA sites sit behind F5 bot protection; DHM/BIPAD refuse non-Nepal IPs → pipeline runs on a laptop in Nepal.
- Long river discharge history (1984→) from Open-Meteo GloFAS; weather (1940→) from Open-Meteo ERA5.
- **26 Aug 2026 Bhotekoshi/Trishuli flood:**
  - ~250 MW destroyed and ~230 MW cut off (≈10% of capacity).
  - Kulekhani is running continuously, below its safe level.
  - India is supplying up to 654 MW until 31 Dec.
  - Handled as a sourced outage register (`outages.json`, [models/outages.md](models/outages.md)).

## Architecture

```
 sources (sources.json)
   NEA transd NDOR ─┐   Wayback NDOR ─┐   NEA reports ─┐   Open-Meteo ─┐   DHM river-watch ─┐
                    ▼                 ▼                ▼               ▼                    ▼
 fetch.py   httpx (polite, retries) ──► Playwright fallback on F5 challenge
                    │
 data/raw/<source>/  immutable PDF / JSON / HTML / Markdown         (bronze files)
                    │
 lake.bronze.ingest_log   (source, key, status)  → incremental skip  (bronze log)
                    │  parse (pdfplumber / json / regex)
 lake.silver.*      nea_daily, nea_document, weather_daily, river_discharge_daily,
                    river_level_obs, dim_calendar                     (typed, deduped)
                    │  SQL views
 lake.gold.*        daily_features, monthly_summary, annual_history,  (model-ready)
                    report_monthly_balance
                    │  nea eda → docs/eda/     nea model / nea forecast (Phase 3)
 lake.ml.*          backtest_metrics, forecasts (P10/P90)   + outages.json, GloFAS forecast
                    │  Phase 4: COPY ... TO parquet
 site/data/*.parquet ──► Cloudflare Pages (DuckDB-WASM / charts)
```

Lakehouse = DuckLake: catalog `data/lake/nea.sqlite` (SQLite: readers work during an ingest), Parquet under `data/lake/data/`. Snapshots give time travel (`AT (VERSION => n)`).

## Roadmap

| Phase | Scope | Plan | Status |
|---|---|---|---|
| 1 | Ingestion + DuckLake (NDOR, NEA reports → Markdown + monthly/annual tables + OCR, weather, discharge, NEA widget, India customs + CERC, World Bank, calendar, gold views) | `docs/superpowers/plans/2026-10-25-phase1-ingestion-lakehouse.md` | done 2026-10-25 (DHM gauges pending: site down) |
| 2 | EDA: seasonality, weather/holiday/discharge effects, import-source reconciliation, gaps → model inputs; DHM manual loader when data arrives | `docs/superpowers/plans/2026-10-25-phase2-eda.md` → `docs/eda-findings.md` | done 2026-10-25 |
| 3 | Models + backtests → `ml.*` (inputs: `docs/eda-findings.md` § Phase 3 inputs) | `docs/superpowers/plans/2026-10-26-phase3-models.md` → `docs/model-results.md` | done 2026-10-26 |
| 4 | `nea export` → Parquet → Cloudflare Pages site | later | next |

## Model strategy

Climb the ladder, stop at the simplest model that holds:

1. **Baselines:** seasonal naive (same weekday last week), same-BS-date-last-year.
2. **Statistical:** `statsforecast` AutoETS / AutoARIMA / MSTL, with exogenous temperature, holidays, river discharge.
3. **Gradient boosting:** LightGBM on lag, calendar, weather and discharge features.

Evaluation: rolling-origin backtest; MAE + MAPE overall **and winter-only**. Pick the simplest model within 5% of the best.

**No LSTM.** ~640 daily points is too little for deep learning; revisit only if daily history exceeds 5 years.

Seasonal outlook: monthly series from annual reports + ETS/SARIMA. Import need = demand forecast − domestic generation forecast (generation regressed on GloFAS discharge; GloFAS seasonal forecast as the future driver), and also modelled directly on `net_exchange_india_mwh`. Everything runs on a laptop CPU.

## Open risks

- NDOR series stops Jan 2025 → daily model trains on 2 winters; post-2025 data needs NEA (user is asking) or Grid-India proxy.
- Government sites can change layout, block bots, or go down → raw files kept, parsers fail loudly per key (logged, not fatal).
- GloFAS is modelled discharge, not gauge truth → validate against DHM data once the email request is answered.
- **Climate shocks:** floods and GLOFs destroy plants that history never lost (Aug 2026: ~480 MW). The models can't learn this, so `outages.json` must be kept current, and import forecasts carry that uncertainty.
- **Live daily data depends on the NEA homepage widget** (short history; layout may change).
