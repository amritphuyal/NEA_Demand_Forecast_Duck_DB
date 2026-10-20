# Phase 3 — Models + Backtests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Honest, laptop-sized forecasts for (a) daily demand / peak / India import 1–30 days ahead, (b) the monthly winter outlook (Nov–Apr), (c) import need — each picked by a rolling-origin backtest, stored in the lake (`ml.*`), and run live by `nea forecast`.

**Architecture:** `src/nea_forecast/model.py` = features + models + backtest harness (one module, plain functions). Daily: **direct** models, one per horizon h ∈ {1, 7, 14, 30}, features known at the origin day t only. Monthly: per-month models on NEA report + customs series. Results upsert into `ml.backtest_metrics` / `ml.forecasts`; charts + `docs/model-results.md` (images embedded from `docs/model/`).

**Tech Stack:** numpy (installed; linear model via `lstsq`), lightgbm (new dep, Task 3 only), DuckDB/DuckLake, matplotlib.

**Spec:** `docs/blueprint.md` § Model strategy + `docs/eda-findings.md` § Phase 3 inputs.

## Global Constraints

- Model ladder, stop at the simplest that holds: baselines → linear (numpy) → LightGBM. A more complex model is kept only if its **winter MAE is > 5% better** than the next simpler one (blueprint rule). **No LSTM.** No statsforecast (numba = heavy); ETS/ARIMA only if linear loses to a baseline (decision logged).
- **No leakage:** a feature for origin t uses data ≤ t only. Future weather/discharge = **climatology** (day-of-year mean, 2010-01-01 → 2022-12-31, i.e. before any NDOR target), never actuals. Current anomaly (value at t − climatology at t) is allowed.
- Daily data = NDOR (`gold.daily_features`, `qa_ok`) + widget after mapping: `requirement_mwh = national_energy_demand_mwh`, `net_exchange_india_mwh = import_mwh − export_mwh`, `peak_demand_mw = national_peak_mw`, domestic gen = `nea_gen + nea_sub_gen + ipp_gen` (verified 2026-10-26: 67,912 total − 21,517 export = 46,395 national). Widget date = `first_seen::DATE − 1 day` (figures are the previous day).
- Metrics: MAE always; MAPE only for demand/peak (import crosses 0). Reported overall and **winter-only** (Nov–Apr). Every metric row has `n`.
- Daily backtest origins: every day from 2024-05-01 to last NDOR date − h; train on all rows with target date < origin. Monthly backtest: hold out winter 2024/25 and 2025/26 (train strictly before each Nov).
- Logs: through CLI tee (`data/logs/<ts>-model.log` / `-forecast.log`), each step `▶ start` / `✔ done in Xs` + metrics table / `✖ FAILED` (others continue), like ingest/eda.
- Lake writes only in `ml` schema; `nea model` and `nea forecast` open the lake read-write.
- Commits via `/caveman:caveman-commit`, no Claude attribution; change-log entry per task.

## Review Focus

1. **Leakage through rolling features / climatology** → a feature at origin t must not change when data after t is altered. Test in Task 1.
2. **Gaps (17-day NDOR gap)** → lag features by date; missing lag → row dropped, not shifted. Test in Task 1.
3. **Horizon arithmetic** → seasonal naive for h=14 uses y(target − 14), never y(target − 7) (would peek past origin). Test in Task 1.
4. **Import crosses zero** → no MAPE on import (division by ~0); MAE only. Test in Task 4.
5. **Live forecast with too little widget history** → `nea forecast` skips daily (logs why) when < 8 consecutive widget days, still writes monthly outlook. Test in Task 6.

---

## File Structure

```
src/nea_forecast/model.py     # features, models, backtest, forecast
src/nea_forecast/schema.sql   # + ml.backtest_metrics, ml.forecasts
src/nea_forecast/cli.py       # + `nea model` (backtest), `nea forecast` (live)
tests/test_model.py
docs/model/*.png, docs/model-results.md
```

`schema.sql` additions:
- `ml.backtest_metrics(run_id VARCHAR, model VARCHAR, target VARCHAR, horizon INTEGER, season VARCHAR, mae DOUBLE, mape DOUBLE, n INTEGER, created_at TIMESTAMP)` — key `(run_id, model, target, horizon, season)`.
- `ml.forecasts(run_id VARCHAR, model VARCHAR, target VARCHAR, horizon INTEGER, origin DATE, date DATE, yhat DOUBLE, created_at TIMESTAMP)` — key `(run_id, model, target, origin, date)`. `horizon` = days (daily) or months (monthly).

---

### Task 1: Daily features, baselines, backtest harness, `nea model`

**Interfaces:**
- Produces:
  - `daily_frame(con) -> dict[date, dict]` — NDOR qa_ok rows + mapped widget rows, keys `requirement_mwh, peak_demand_mw, net_exchange_india_mwh, domestic_gen_mwh, dow, is_holiday, tmean_terai, discharge_index`.
  - `climatology(con) -> dict[tuple[str, int], float]` — `(column, day_of_year) → mean` for `tmean_terai`, `discharge_index`, over 2010-01-01 → 2022-12-31 (7-day centered smoothing).
  - `features(frame, clim, origin: date, h: int, target: str) -> dict | None` — `y_t` (origin value), `y_mean7`, `y_snaive` = y(target_date − 7·⌈h/7⌉), target-day `dow` one-hot, `is_holiday`, `clim_temp`, `clim_q`, `q_anom` (discharge at origin − clim). None if any lag missing.
  - `BASELINES = {"naive": y_t, "snaive": y_snaive}`.
  - `backtest(con, models: dict[str, Callable], targets, horizons) -> list[dict]` (metric rows), and `run_backtest(con)` → upsert `ml.backtest_metrics`, print table, save `docs/model/backtest_daily.png` (winter MAE by model × horizon).
  - CLI `nea model` → `run_backtest(connect())`.
- [ ] **Step 1: Failing tests** — `test_features_no_leakage` (change all frame values after origin → identical features); `test_snaive_h14_uses_two_weeks_back`; `test_missing_lag_returns_none` (gap on y(t)); `test_backtest_perfect_weekly_series_snaive_mae_zero`.
- [ ] **Step 2–4:** FAIL → implement → PASS. `uv run nea model` prints baseline metrics for 3 targets × 4 horizons.
- [ ] **Step 5: Commit** `feat(model): daily features, baselines, backtest`.

### Task 2: Linear model

**Interfaces:** `fit_linear(X: np.ndarray, y) -> coef` (standardize, ridge λ = 1.0 via augmented `lstsq`), `linear` model callable in `MODELS`. Feature matrix from `features` dicts in fixed key order.
- [ ] **Step 1: Failing test** — synthetic y = 3·x1 − 2·x2 + 5 → coefficients recovered within 1%.
- [ ] **Step 2–4:** FAIL → implement → PASS. Re-run `nea model`; log linear vs baseline winter MAE.
- [ ] **Step 5: Commit** `feat(model): ridge linear daily model`.

### Task 3: LightGBM (kept only if > 5% better)

- `uv add lightgbm`. `lgbm` model: `LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=10)`, same features + `tmin_ktm` climatology (EDA: test it here).
- `select(metrics) -> dict[(target, horizon), model]` — simplest model within 5% of best winter MAE; printed and saved as `docs/model/selection.json`.
- [ ] **Step 1: Failing test** — `select` picks `linear` when lgbm is only 3% better, `lgbm` when 10% better.
- [ ] **Step 2–4:** FAIL → implement → PASS. If lgbm is never selected, remove it from `MODELS` and the dep (`uv remove lightgbm`), note in change log.
- [ ] **Step 5: Commit** `feat(model): lightgbm candidate and model selection`.

### Task 4: Import need — direct vs demand − generation

- `import_need_compare(con) -> list[dict]`: for each horizon, MAE of (a) selected model on `net_exchange_india_mwh`, (b) selected `requirement_mwh` forecast − selected `domestic_gen_mwh` forecast. Upsert as model names `direct` / `diff` under target `import_need`. MAE only.
- [ ] **Step 1: Failing test** — metric rows for `import_need` have `mape is None`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(model): compare direct vs demand-minus-generation import`.

### Task 5: Monthly winter outlook

**Interfaces:**
- `monthly_frame(con) -> dict[date, dict]` — AD month → `demand_gwh` (report `national_demand`, GWh, BS→AD start month as in EDA), `import_gwh` (customs ×1.09 to report level, per EDA), `discharge_mean` (monthly mean `discharge_index`).
- Models: `snaive_growth` (same month last year × (1 + trailing 12-month growth)), `linear_m` (log y ~ trend + month dummies + log discharge anomaly), per target `demand_gwh`, `import_gwh`. Horizon = months ahead from Oct origin (1–6 = Nov–Apr).
- Backtest winters 2024/25 and 2025/26 → `ml.backtest_metrics` (horizon = month index). Chart `docs/model/backtest_monthly.png` (actual vs both models).
- [ ] **Step 1: Failing test** — `snaive_growth` on series growing exactly 10%/yr with fixed seasonality → MAPE 0.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(model): monthly winter outlook backtest`.

### Task 6: Live `nea forecast` + results doc

- `forecast(con, today: date) -> int`: monthly outlook for the coming Nov–Apr with selected monthly models → `ml.forecasts` (run_id = `live-<YYYYmmdd>`); daily 1–30 d with selected daily models **only if** the widget has ≥ 8 consecutive days ending yesterday, else log `daily skipped: widget has N days (need 8)`. Chart `docs/model/forecast_<run_id>.png`.
- `docs/model-results.md`: backtest tables (winter MAE/MAPE per target × horizon × model), selected models, embedded charts, limits (2 winters of daily data; widget-only live daily).
- Blueprint: Phase 3 done, Phase 4 next. Cron in `docs/flow.md`: `nea ingest all && nea forecast` daily.
- [ ] **Step 1: Failing test** — widget with 3 days → result has monthly rows, zero daily rows, log line contains `daily skipped`.
- [ ] **Step 2–4:** FAIL → implement → PASS. `uv run nea forecast` on real lake.
- [ ] **Step 5: Commit** `feat(model): live forecast command and results doc`.
