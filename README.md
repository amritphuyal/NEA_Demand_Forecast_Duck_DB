# NEA Demand Forecast (DuckDB / DuckLake)

Forecast Nepal Electricity Authority (NEA) electricity demand, with focus on the **winter dry season** (Nov–Apr): river flows drop, run-of-river hydro falls, Kulekhani is the only storage reservoir, and Nepal imports power from India.

Pipeline: scrape public sources (NEA reports, river discharge, gauges, weather) with plain Python (no LLM) → immutable raw files → DuckLake lakehouse (Parquet + DuckDB) → features → forecasts → static website (Cloudflare).

## Quickstart

```bash
uv sync
uv run playwright install chromium     # fallback fetcher for NEA's bot protection
uv run nea ingest all                  # incremental: only new data is fetched
uv run nea status                      # rows + date range per table
uv run nea eda                         # analysis numbers + charts -> docs/eda/
uv run nea model                       # backtest + model selection -> ml.backtest_metrics, docs/model/
uv run nea forecast                    # live forecasts with P10/P90 -> ml.forecasts
uv run nea sql "FROM ml.forecasts LIMIT 5"   # query any lake table (see docs/lake.md)
uv run nea export                      # lake -> Parquet snapshot for the website
cd site && npm install && npm run dev  # website preview (docs/site.md); npm run deploy -> Cloudflare Pages
uv run pytest                          # offline tests
```

Query the lake from any DuckDB shell:

```sql
INSTALL ducklake; INSTALL sqlite;
ATTACH 'ducklake:sqlite:data/lake/nea.sqlite' AS lake (READ_ONLY);  -- works even while an ingest runs
FROM lake.gold.daily_features LIMIT 5;
```

## Layout

| Path | What |
|---|---|
| `sources.json` | Source registry: URLs, points, status (read by the code) |
| `outages.json` | Capacity out of service (Aug 2026 flood, Kulekhani), with sources; edit as NEA restores plants |
| `src/nea_forecast/` | Ingesters, lakehouse, CLI |
| `data/raw/` | Immutable downloads (bronze, gitignored) |
| `data/lake/` | DuckLake catalog + Parquet files (gitignored) |
| `docs/blueprint.md` | Mission, architecture, roadmap, model strategy |
| `docs/flow.md` | End-to-end flow, every command and source, incremental rules, cron |
| `docs/lake.md` | Every lake table, how to query it, example queries |
| `site/` | Website (Observable Framework + DuckDB-WASM + Leaflet), deployed to Cloudflare Pages: `docs/site.md` |
| `docs/data-sources.md` | Every source researched, status, extra data points |
| `docs/eda-findings.md` | EDA results + Phase 3 model inputs |
| `docs/models/` | Forecasting approach + one doc per model + literature review (defence of the method) |
| `docs/model-results.md` | What ships, backtest results, live winter outlook |
| `docs/developer/decisions.md` | Architecture decisions + change log |
| `docs/superpowers/plans/` | Phase implementation plans |

## Credits

- Inspired by [nea-data-warehouse](https://github.com/Unknown-333/nea-data-warehouse) by **Aayush Paudel** ([@Unknown-333](https://github.com/Unknown-333)): NDOR URL pattern, report field list, energy-balance check idea. Re-implemented here (no code copied).
- Data: Nepal Electricity Authority (NEA), Department of Hydrology and Meteorology Nepal (DHM), [Open-Meteo](https://open-meteo.com/) (CC BY 4.0), Copernicus GloFAS (river discharge), ECMWF ERA5 (weather).

Educational, non-commercial project.
