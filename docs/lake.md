# Querying the lake (DuckLake)

All data and results live in one DuckLake lakehouse:
- **Catalog:** `data/lake/nea.sqlite`
- **Data:** Parquet files under `data/lake/data/`

Reads work while an ingest is running.

## Three ways to query

**1. From this repo (easiest):**

```bash
uv run nea sql "FROM ml.forecasts WHERE run_id LIKE 'live-%' ORDER BY target, model, date"
uv run nea status                       # every table: rows + date range
```

**2. DuckDB CLI or any DuckDB client** (DBeaver, Python, a notebook):

```sql
INSTALL ducklake; INSTALL sqlite;
ATTACH 'ducklake:sqlite:data/lake/nea.sqlite' AS lake (READ_ONLY);
USE lake;
FROM gold.daily_features LIMIT 5;
```

**3. Python:**

```python
from nea_forecast.lake import connect
con = connect(read_only=True)
df = con.sql("FROM gold.monthly_summary").df()   # needs pandas; or .fetchall()
```

**Time travel.** Every write is a snapshot, so you can read a table as it was before:

```sql
FROM ducklake_snapshots('lake');
FROM silver.nea_daily AT (VERSION => 42);
```

## What's in it

Layers:
- **bronze:** what ran.
- **silver:** clean source tables.
- **gold:** joined, model-ready views.
- **ml:** model output.

| Table | One row per | Use it for |
|---|---|---|
| `bronze.ingest_log` | source × key | what was fetched, when, status (`ok`, `not_found`, `parse_error`, `fetch_error`) |
| `silver.nea_daily` | day (2023-04-14 → 2025-01-11) | NEA daily energy balance: generation, import, export, demand, peak, interruption |
| `silver.nea_widget` | snapshot (2026-10-25 →) | NEA homepage daily figures (same definitions as NDOR) |
| `silver.nea_document` | report | downloaded NEA reports (PDF + Markdown paths) |
| `silver.report_monthly` | report × table × series × month | every month-wise table found in NEA reports (raw long format) |
| `silver.report_annual` / `report_energy_history` | FY / year | annual peak, energy, sources from NEA reports |
| `silver.weather_daily` | day × point | ERA5 max/min temperature, rain; 6 points, 2010 → |
| `silver.river_discharge_daily` | day × point | GloFAS river flow; 3 basins + 5 plants, 2010 → |
| `silver.river_discharge_forecast` | issue day × day × point | GloFAS forecast (ensemble mean, p25, p75), ~7 months ahead |
| `silver.plant_outage` | plant | capacity out of service (Aug 2026 flood, Kulekhani shortfall) with sources |
| `silver.india_trade_monthly` | month × direction × measure | India customs: Nepal import/export, MWh and ₹ crore, 2017 → |
| `silver.iex_cross_border_monthly` | month × market | Nepal buy/sell + price on India's power exchange, 2023 → |
| `silver.macro_yearly` | year × indicator | World Bank GDP, population |
| `silver.dim_calendar` | day | BS date, weekday, holiday, season, fiscal year |
| `silver.river_level_obs` | gauge × time | DHM gauge levels (empty: site down) |
| `gold.daily_features` | day | calendar ⟕ NEA daily ⟕ weather ⟕ river index: **the daily modelling table** |
| `gold.monthly_summary` | BS month | daily data rolled up by BS month |
| `gold.annual_history` | year | annual energy, peak, import + GDP, population |
| `gold.report_monthly_balance` | FY × BS month × unit | validated monthly balance from NEA reports (MW and GWh) |
| `ml.backtest_metrics` | run × model × target × horizon × season × weather | MAE, MAPE, interval coverage, pinball loss, Diebold–Mariano p |
| `ml.forecasts` | run × model × target × origin × date | forecasts with P10/P90. `run_id`: `bt-*` = backtest, `live-YYYYmmdd` = live |

## Useful queries

```sql
-- Winter outlook, base vs flood-adjusted import
SELECT model, target, date, round(yhat) AS yhat, round(p10) AS p10, round(p90) AS p90
FROM ml.forecasts WHERE run_id = (SELECT max(run_id) FROM ml.forecasts WHERE run_id LIKE 'live-%')
ORDER BY target, model, date;

-- Which model won, and by how much (latest backtest, winter, ex-ante)
SELECT target, horizon, model, round(mae) AS mae, round(mape, 1) AS mape, round(dm_p, 3) AS dm_p, round(coverage, 2) AS coverage
FROM ml.backtest_metrics
WHERE run_id = (SELECT max(run_id) FROM ml.backtest_metrics) AND season = 'winter' AND weather = 'clim'
ORDER BY target, horizon, mae;

-- Daily demand and import with weather and river flow
SELECT date, requirement_mwh, net_exchange_india_mwh, tmin_ktm, tmean_terai, discharge_index
FROM gold.daily_features WHERE requirement_mwh IS NOT NULL ORDER BY date DESC LIMIT 30;

-- Flood damage register
SELECT plant, capacity_mw, status, expected_return FROM silver.plant_outage ORDER BY capacity_mw DESC;

-- River-flow forecast for the Narayani basin, latest issue
SELECT date, round(discharge_m3s) AS mean, round(p25) AS p25, round(p75) AS p75 FROM silver.river_discharge_forecast
WHERE point = 'narayani_devghat' AND issued = (SELECT max(issued) FROM silver.river_discharge_forecast) ORDER BY date;
```
