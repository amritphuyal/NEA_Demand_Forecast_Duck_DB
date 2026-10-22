# Data Flow (end to end)

## In one picture

```
 1. INGEST            2. STORE (DuckLake)              3. ANALYSE / MODEL          4. USE
 nea ingest all  ──►  data/raw/<source>/  (files)  ──► nea eda      → docs/eda/    docs/*.md + charts
  NEA reports         bronze.ingest_log (what ran)     nea model    → ml.backtest_ nea sql "…"
  NEA widget          silver.*  (clean tables)                        metrics       ml.forecasts
  weather, rivers     gold.*    (joined views)         nea forecast → ml.forecasts  website (site/)
  India trade, GDP    ml.*      (model output)                        docs/model/
  outages.json
```

**Every day:**
1. `nea ingest all` fetches only what is new.
2. `nea forecast` writes today's forecasts.

**After each winter, or when models change:** `nea model` re-tests the models and re-selects them.

**To publish:** `nea export` (lake → `site/src/data/*.parquet`), then `cd site && npm run deploy` ([deploy.md](deploy.md)). Diagrams: [architecture.md](architecture.md).

Every command writes a time-stamped log to `data/logs/<YYYYmmdd-HHMMSS>-<command>.log`. Each step logs `▶ start` and then `✔ done` or `✖ FAILED`; a failing step never stops the others.

## Commands

| Command | What it does | Output |
|---|---|---|
| `nea ingest <source…>` / `all` | fetch new data per source (table below) | `data/raw/…`, `silver.*` |
| `nea status` | row counts + date range per table, ingest log summary | screen |
| `nea eda` | exploratory analysis: 6 questions | `docs/eda/*.png`, `docs/eda/summary.json` |
| `nea model` | rolling-origin backtest of all models, Diebold–Mariano, selection, intervals | `ml.backtest_metrics`, `ml.forecasts` (`bt-*`), `docs/model/*.png`, `docs/model/selection.json` |
| `nea forecast` | live forecasts: winter monthly outlook (+ flood adjustment), daily 1–30 d once the widget has 8 days | `ml.forecasts` (`live-YYYYmmdd`), `docs/model/forecast_live-*.png` |
| `nea sql "<query>"` | read-only SQL on the lake | screen |
| `nea export` | Parquet snapshot of the lake for the website (+ points, selection, manifest) | `site/src/data/` |
| `nea search <regex>` | search the downloaded NEA report Markdown | screen |
| `nea maintain` | merge small Parquet files, expire snapshots > 30 days | — |

## Sources (`nea ingest …`), in run order

| Source | What | Incremental rule | Raw file | Table |
|---|---|---|---|---|
| `ndor` | NEA daily operational report PDFs (2023-04 → 2025-01; NEA stopped publishing) | listing pages until one has nothing new; failed keys retried | `nea_ndor/{slug}.pdf` | `silver.nea_daily` |
| `widget` | NEA homepage "Energy Details" (daily figures, from 2026-10-25) | new snapshot when the numbers change | `nea_widget/*.json` | `silver.nea_widget` |
| `docs` | NEA monthly/yearly/annual report PDFs → Markdown | listing minus logged keys | `nea_docs/{category}/{slug}.pdf/.md` | `silver.nea_document` |
| `reports` | month-wise tables from that Markdown | re-parse every run (fast) | — | `silver.report_monthly`, `report_annual`, `report_energy_history` |
| `ocr` | image-only balance tables (RapidOCR) | PDFs already done are skipped | `nea_docs/ocr/*.json` | `silver.report_monthly` |
| `weather` | ERA5 temperature + rain, 6 points | all points in one request, from last stored day − 3 d (recent days are provisional; still-unpublished days come next run) | `open_meteo/weather/*.json` | `silver.weather_daily` |
| `discharge` | GloFAS river flow, 3 basins + 5 plants | same as weather (one request, last day − 3 d) | `open_meteo/discharge/*.json` | `silver.river_discharge_daily` |
| `discharge_forecast` | GloFAS river-flow **forecast**, ~7 months, ensemble mean/p25/p75 | one issue per run day | `open_meteo/discharge_forecast/{date}.json` | `silver.river_discharge_forecast` |
| `outages` | hand-kept register of capacity out of service (`outages.json`: Aug 2026 flood, Kulekhani shortfall) | full refresh from the JSON | — | `silver.plant_outage` |
| `dhm` | DHM river-watch gauges (site down since 2026-10) | append snapshot | `dhm/*.json` | `silver.river_level_obs` |
| `calendar` | BS dates, holidays, season, fiscal year | rebuild 2010 → today + 400 d | — | `silver.dim_calendar` |
| `macro` | World Bank GDP, population | full refresh | `world_bank/*.json` | `silver.macro_yearly` |
| `cerc` | Nepal buy/sell on India's power exchange (CERC) | new monthly Excel files | `cerc/*.xlsx` | `silver.iex_cross_border_monthly` |
| `india_trade` | India customs electricity trade with Nepal, monthly | missing months + last 120 days re-checked | `india_trade/*.json` | `silver.india_trade_monthly` |

Rules everywhere:
- A key is logged `ok` only after its table write commits, so a crash mid-run is retried next run.
- `parse_error` / `fetch_error` keys are retried; `not_found` keys are not.
- Upsert = delete matching keys + insert in one transaction (DuckLake has no primary keys).
- Raw files are readable (PDF, Markdown, JSON, CSV) and never overwritten, so silver can be rebuilt from them.

## Keeping the flood register current

`outages.json` lists capacity out of service with sources. When NEA reports a plant or line restored:
1. Set its `expected_return` date in `outages.json`.
2. Run `nea ingest outages && nea forecast`.

The `+outage` import forecast drops automatically.

## Schedule (laptop in Nepal)

NEA fetches use headless real Chrome (automation flags masked). If F5 starts blocking, set `NEA_HEADED=1` (needs the `DISPLAY` of the logged-in session).

```cron
0 */3 * * * cd /path/to/repo && uv run nea ingest all >> data/ingest.log 2>&1
30 6 * * *  cd /path/to/repo && uv run nea forecast   >> data/ingest.log 2>&1
0 4 * * 0   cd /path/to/repo && uv run nea maintain   >> data/ingest.log 2>&1
# after each winter (May) or when models change: uv run nea model
```
