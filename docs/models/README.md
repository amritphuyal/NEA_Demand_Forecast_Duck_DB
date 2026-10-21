# Forecasting approach (Phase 3)

One page that explains and defends **what** we forecast, **with which models**, **how they are tested**, and **why this is the right size** for the data. Each model has its own document (table below). The evidence is in [literature.md](literature.md); the data facts are in [../eda-findings.md](../eda-findings.md).

## 1. The need → the model

| Need (user brief) | Target | Horizon | Model family | Doc |
|---|---|---|---|---|
| Daily short-term demand | `requirement_mwh` (energy), `peak_demand_mw` | 1, 7, 14, 30 days | baselines → ridge regression → LightGBM (if it earns it) | [baselines](baselines.md), [ridge](ridge.md), [lightgbm](lightgbm.md) |
| Winter seasonal outlook | monthly demand GWh, monthly import GWh | Nov–Apr (1–6 months) | seasonal naive × growth, log-linear, ETS, combination | [monthly-outlook](monthly-outlook.md) |
| India import need | `net_exchange_india_mwh` (daily), import GWh (monthly) | as above | direct model vs demand − domestic generation | [import-need](import-need.md) |
| Plan with risk, not one number | P10 / P50 / P90 for every target | all | split conformal intervals | [intervals](intervals.md) |

## 2. Why this ladder and not deep learning

1. **Data size.** We have 612 daily points (two winters), 53 monthly points and 14 annual points. Deep learning needs far more. On a Nepal national peak-load series, LSTM beat a 30-day moving average by 0.05 MAPE points [lit 3]. Tree models and even linear models beat deep networks on tabular data of this size [lit 27, 28].
2. **What wins in load forecasting.** Regression with temperature, calendar and trend is in every winning GEFCom entry, and the "vanilla benchmark" is exactly that [lit 19–22]. Our ridge model is that benchmark adapted to Nepal (two temperature regions, holidays, river discharge).
3. **Climb, then stop.** Each step must beat the one below it on **winter** error by more than 5% **and** pass a Diebold–Mariano test (p < 0.10). Otherwise the simpler model is used. That makes the choice of a complex model something the data has to prove; it isn't assumed.
4. **Laptop.** The full backtest (5 targets × 4 horizons × 5 models × 2 weather modes + monthly) runs in about 75 s on CPU; the live forecast in about 3 s. Dependencies: numpy, statsmodels (ETS) and lightgbm (challenger only; no live forecast uses it).

## 3. How the models are tested (defend these points first)

| Question a reviewer will ask | Our answer |
|---|---|
| Did you test on data the model saw? | No. **Rolling origin:** for each origin day t (2024-05-01 → end), train only on targets dated before t, forecast t + h. |
| Did you use future weather you wouldn't have? | Main results are **ex-ante**: future temperature and discharge come from **climatology** (2010–2022 day-of-year mean, all before any target date). We also report **ex-post** (actual weather) to show how much a weather forecast could add [lit 24, 30]. |
| Is the error measured where it matters? | MAE always; MAPE for demand and peak only (import crosses zero). Reported **overall and winter-only**. |
| Is "better" just noise? | 5% margin **plus** a Diebold–Mariano test on the paired loss differences. |
| How sure is each forecast? | P10/P90 from conformal residual quantiles per horizon and season; we report **coverage** (should be ~80%) and pinball loss. |
| Do gaps break lags? | Lags are taken **by date**. If a lag is missing, the row is dropped, not shifted (17-day NDOR gap in Sep 2023). |

## 4. Known limits (state them before others do)

- **Two winters of daily data.** The daily backtest covers only winter 2024/25 (Nov → 11 Jan). Winter error figures carry wide uncertainty; the intervals reflect that.
- **Live daily data comes from the NEA widget** (from 2026-10-25). Its definitions match NDOR exactly (verified 2026-10-26), but its history is short.
- **Structural change.** Demand grows 12%/yr, and new hydro shifts import sharply (37% → 6% share). Lag features carry the level forward; we check coefficient stability across 2023 vs 2024 fits.
- **GloFAS is modelled discharge,** not gauge data. It is used as an index; DHM gauge data, when it arrives, will validate it.
- **NEA's official method is unpublished.** We could not compare against an NEA daily or monthly benchmark.

## 5. Where results live

- Lake: `ml.backtest_metrics` (every model × target × horizon × season, with `n`), `ml.forecasts` (with P10/P90).
- Docs: each model doc has a **Results** section filled from the backtest; the summary with charts is in [../model-results.md](../model-results.md).
- Commands: `nea model` (backtest), `nea forecast` (live). Logs: `data/logs/<time>-model.log`.
