# Phase 3 — Models + Backtests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Honest, laptop-sized forecasts with P10/P90 for (a) daily demand / peak / import need 1–30 days ahead, (b) the monthly winter outlook (Nov–Apr), (c) import need. Each is picked by a rolling-origin backtest, stored in `ml.*`, documented per model in `docs/models/`, and run live by `nea forecast`.

**Architecture:** `src/nea_forecast/model.py` holds features, models, backtest, selection, intervals and forecast as plain functions. Daily models are **direct**, one per horizon h ∈ {1, 7, 14, 30}, using only features known at origin t. Monthly models run on the NEA report and customs series. Results upsert into `ml.backtest_metrics` / `ml.forecasts`. Charts go to `docs/model/` and are embedded in `docs/model-results.md`, and each `docs/models/*.md` gets its Results section filled.

**Tech Stack:** numpy (ridge via `lstsq`), lightgbm (Task 3; removed if never selected), statsmodels (ETS, Task 5), DuckDB/DuckLake, matplotlib.

**Spec:** `docs/blueprint.md` § Model strategy, `docs/eda-findings.md` § Phase 3 inputs, `docs/models/README.md` (approach and defence), `docs/models/literature.md` (evidence; gaps 1–8 from the 2026-10-26 review are closed by Tasks 1–6).

## Global Constraints

- **Ladder:** baselines → ridge → LightGBM. A more complex model is kept only if its **winter MAE is > 5% better AND a Diebold–Mariano test gives p < 0.10**. No LSTM, no statsforecast.
- **No leakage:** a feature for origin t uses data ≤ t only. Target-day weather and discharge are **climatology** (day-of-year mean 2010-01-01 → 2022-12-31, 7-day centred smoothing) in the main (**ex-ante**) results. An **ex-post** run with actual target-day values is reported next to it, never used for selection.
- **Daily data** = NDOR (`gold.daily_features`, `qa_ok`) + widget with this mapping:
  - `requirement_mwh = national_energy_demand_mwh`
  - `net_exchange_india_mwh = import_mwh − export_mwh`
  - `peak_demand_mw = national_peak_mw`
  - domestic generation = `nea_gen + nea_sub_gen + ipp_gen`
  - widget date = `first_seen::DATE − 1`
  - The mapping was verified 2026-10-26: 67,912 − 21,517 = 46,395.
- **Targets:** `requirement_mwh`, `peak_demand_mw`, `domestic_gen_mwh`, `net_exchange_india_mwh`, `import_need_mwh` (= requirement − domestic generation; see `docs/models/import-need.md`).
- **Metrics:** MAE always. MAPE only for demand and peak. Interval **coverage** and **pinball** loss (0.1/0.9). Every metric is reported overall and winter-only (Nov–Apr), with `n`.
- **Backtest windows:**
  - Daily origins: every day 2024-05-01 → last date − h; train on targets dated before the origin.
  - Monthly: hold-out winters 2024/25 and 2025/26.
- **Logs:** go through the CLI tee (`data/logs/<ts>-model.log` / `-forecast.log`). Each step prints `▶` / `✔` with a metrics table, or `✖ FAILED` (the others continue).
- **Writes:** lake writes only in `ml`; charts in `docs/model/`. Each task fills the Results section of its `docs/models/*.md`.
- **Commits:** `/caveman:caveman-commit`, no Claude attribution, one change-log entry per task.

## Review Focus

1. **Leakage through rolling features or climatology** → features at origin t must not change when data after t is altered. Test: Task 1.
2. **Gaps** (the 17-day NDOR gap) → lags are taken by date; a missing lag drops the row instead of shifting it. Test: Task 1.
3. **Horizon arithmetic** → `snaive` at h = 14 reads target − 14 days. Test: Task 1.
4. **Import crosses zero** → no MAPE for exchange or import need. Test: Task 4.
5. **Short widget history in a live run** → daily forecasts are skipped with a log line when there are fewer than 8 consecutive days; the monthly outlook is still written. Test: Task 7.

---

## File Structure

```
src/nea_forecast/model.py     # features, models, backtest, select, intervals, forecast
src/nea_forecast/schema.sql   # + ml.backtest_metrics, ml.forecasts
src/nea_forecast/cli.py       # + `nea model`, `nea forecast`
tests/test_model.py
docs/model/*.png, docs/model-results.md, docs/models/*.md (Results sections)
```

`schema.sql`:
- `ml.backtest_metrics`
  - Columns: `run_id VARCHAR, model VARCHAR, target VARCHAR, horizon INTEGER, season VARCHAR, weather VARCHAR, mae DOUBLE, mape DOUBLE, coverage DOUBLE, pinball DOUBLE, dm_p DOUBLE, n INTEGER, created_at TIMESTAMP`
  - `weather` ∈ `clim`, `actual`. `dm_p` is versus the next simpler model.
  - Key: `(run_id, model, target, horizon, season, weather)`.
- `ml.forecasts`
  - Columns: `run_id VARCHAR, model VARCHAR, target VARCHAR, horizon INTEGER, origin DATE, date DATE, yhat DOUBLE, p10 DOUBLE, p90 DOUBLE, created_at TIMESTAMP`
  - Key: `(run_id, model, target, origin, date)`.

---

### Task 1: Daily frame, features, baselines, backtest, `nea model`

**Interfaces:**
- `daily_frame(con) -> dict[date, dict]`: NDOR plus mapped widget rows. Columns: the 5 targets, `dow`, `is_holiday`, `tmean_ktm`, `tmean_terai`, `discharge_index`.
- `climatology(con) -> dict[tuple[str, int], float]`: maps (column, day of year) to the smoothed 2010–2022 mean.
- `features(frame, clim, origin, h, target, weather="clim") -> dict | None`. Returns None if any lag is missing. Features:
  - `y_t`, `y_mean7`, `y_snaive` (target − 7·⌈h/7⌉)
  - weekday one-hot and `is_holiday` of the target day
  - `hdd` = max(0, 15 − tmean_ktm) and `cdd` = max(0, tmean_terai − 24) for the target day; `tmean_terai`
  - `temp_anom_t` and `temp_anom_7` (recency)
  - `q_clim` for the target day, `q_anom_t`, `q_anom_7`
  - `trend` (days since 2023-01-01)
  - `weather="actual"` swaps target-day climatology for actual values (ex-post).
- `BASELINES`: `naive`, `snaive`, `wma30` (weights 30..1).
- `backtest(con, models, targets, horizons, weather) -> list[dict]` returns metric rows plus per-origin errors (kept in memory for DM and intervals).
- `run_backtest(con)` upserts `ml.backtest_metrics`, prints the table, and saves `docs/model/backtest_daily.png`.
- CLI `nea model`.

- [ ] **Step 1: Failing tests**
  - `test_features_no_leakage`
  - `test_snaive_h14_two_weeks_back`
  - `test_missing_lag_returns_none`
  - `test_backtest_weekly_series_snaive_mae_zero`
  - `test_wma30_weights`
- [ ] **Step 2–4:** FAIL → implement → PASS. `uv run nea model` prints the baselines for 5 targets × 4 horizons.
- [ ] **Step 5:** Fill the Results section of `docs/models/baselines.md`. **Commit:** `feat(model): daily features, baselines, backtest`.

### Task 2: Ridge

**Interfaces:**
- `fit_ridge(X, y, lam) -> (mean, std, coef)`, solved by standardising, then augmented `lstsq`.
- `ridge` model: λ ∈ {0.1, 1, 10, 100}, chosen on the last 60 days of each training window.
- `dm_test(e1, e2, h) -> p`: Diebold–Mariano on absolute errors, with HAC variance at lag h−1.

- [ ] **Step 1: Failing tests**
  - Synthetic y = 3x₁ − 2x₂ + 5 → coefficients within 1%.
  - `dm_test` on identical errors → p = 1. On e2 = 2·e1 with n = 200 → p < 0.01.
- [ ] **Step 2–4:** FAIL → implement → PASS. Run `nea model` (ex-ante and ex-post).
- [ ] **Step 5: Checks**
  - HDD/CDD thresholds ±3 °C sensitivity (winter MAE table).
  - Coefficient stability: fit on 2023 vs 2024; compare signs and sizes.
  - Write both, plus the coefficient table, into `docs/models/ridge.md` Results.
- **Commit:** `feat(model): ridge daily model and DM test`.

### Task 3: LightGBM and selection

- `uv add lightgbm`.
- `lgbm` model:
  - target `y_{t+h}/y_t − 1`, multiplied back by `y_t`
  - params as in `docs/models/lightgbm.md`
  - features + `tmin_ktm` climatology
- `select(metrics, errors) -> dict[(target, horizon), model]`:
  - The simplest model wins unless the next model's winter MAE is > 5% better and DM p < 0.10.
  - Output: `docs/model/selection.json`.

- [ ] **Step 1: Failing test:** 3% better → simpler model. 10% better with p 0.01 → complex model. 10% better with p 0.4 → simpler model.
- [ ] **Step 2–4:** FAIL → implement → PASS. If LightGBM is never selected: `uv remove lightgbm`, delete its code, log why.
- [ ] **Step 5:** Fill Results in `docs/models/lightgbm.md`. **Commit:** `feat(model): lightgbm challenger and selection`.

### Task 4: Import need, direct vs difference

- `import_need_compare(con, errors)`. For each horizon:
  - `direct`: the selected model on `import_need_mwh`.
  - `diff`: the selected `requirement` forecast minus the selected `domestic_gen` forecast.
  - Also report `net_exchange_india_mwh` direct.
  - MAE and DM only. Ties go to `diff` (it explains the cause).
- [ ] **Step 1: Failing test:** metric rows for `import_need` and `net_exchange` have `mape is None`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Fill Results in `docs/models/import-need.md`.
- [ ] **Step 5: Commit:** `feat(model): import need direct vs difference`.

### Task 5: Monthly winter outlook

- `uv add statsmodels`.
- `monthly_frame(con)` returns rows keyed by AD month:
  - `demand_gwh` from the report (BS → AD start month)
  - `import_gwh` from customs ÷1.09 (customs reads 9% above NEA)
  - `discharge_anom`
- Models:
  - `snaive_growth`
  - `linear_m`: log y ~ trend + month dummies + discharge anomaly
  - `ets`: ExponentialSmoothing on log y, damped additive trend, additive season 12
  - `combo`: mean of the three
- Backtest winters 2024/25 and 2025/26 (origin 31 Oct, h = 1..6).
- Annual cross-check against the GDP-elasticity path; flag gaps over 10%.
- Chart: `docs/model/backtest_monthly.png`.

- [ ] **Step 1: Failing tests**
  - `snaive_growth` on exact 10%/yr growth with a fixed season → MAPE 0.
  - `combo` = mean of its parts.
- [ ] **Step 2–4:** FAIL → implement → PASS. Fill Results in `docs/models/monthly-outlook.md`.
- [ ] **Step 5: Commit:** `feat(model): monthly outlook with ETS and combination`.

### Task 6: Prediction intervals

- `intervals(errors, target, horizon, season, window=60) -> (q10, q90)`: empirical quantiles of the last 60 out-of-sample errors.
- Backtest scoring: coverage and pinball, per target × horizon × season, written to `ml.backtest_metrics`.
- Monthly: the same, with residuals from the hold-out winters (flagged low n).

- [ ] **Step 1: Failing test:** errors uniform on [−10, 10] → q10 ≈ −8, q90 ≈ 8; coverage on the same distribution ≈ 0.8 ± 0.05.
- [ ] **Step 2–4:** FAIL → implement → PASS. Fill Results in `docs/models/intervals.md`.
- [ ] **Step 5: Commit:** `feat(model): conformal P10/P90 intervals`.

### Task 7: Live `nea forecast` and results doc

- `forecast(con, today) -> int`:
  - Monthly outlook for the coming Nov–Apr, with P10/P90, into `ml.forecasts`.
  - Daily 1–30 days only if the widget has ≥ 8 consecutive days ending yesterday. Otherwise log `daily skipped: widget has N days (need 8)`.
  - `run_id = live-<YYYYmmdd>`. Chart: `docs/model/forecast_<run_id>.png`.
- `docs/model-results.md`: selected models, winter tables, embedded charts, limits. Link each `docs/models/*.md`.
- Blueprint: Phase 3 done. `docs/flow.md` cron: `nea ingest all && nea forecast`.

- [ ] **Step 1: Failing test:** 3 widget days → monthly rows written, 0 daily rows, log contains `daily skipped`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Run `uv run nea forecast`.
- [ ] **Step 5: Commit:** `feat(model): live forecast and results doc`.
