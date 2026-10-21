# Prediction intervals (P10 / P90)

**Role:** turn every point forecast into a range. Import is bought ahead, so a planner needs "between X and Y with 80% confidence", not just one number. Probabilistic forecasting is the field standard since GEFCom2014 [lit 22, 34].

## How it works (split conformal, rolling)

1. The rolling backtest already produces **out-of-sample** errors $e = y - \hat y$ for every (target, horizon, origin).
2. For a new forecast at horizon $h$, take the **last 60 errors already known at the forecast origin** (target date ≤ origin) for that model, target and horizon. At least 30 are needed; otherwise there's no interval.
3. P10 = $\hat y + q_{0.10}(e)$ and P90 = $\hat y + q_{0.90}(e)$, where $q$ is the empirical quantile.

This makes no assumption about the error distribution (it can be skewed). The 60-origin window keeps it adaptive when the error level changes, a simplified form of adaptive conformal inference for time series, where the usual exchangeability assumption fails [lit 36].

## How it is checked

- **Coverage:** the share of actuals inside [P10, P90] should be about 80%. It is reported per horizon and season. Much lower means the intervals are too narrow, and that is reported, not hidden.
- **Pinball loss** at 0.1 and 0.9: the standard score for quantile forecasts [lit 22].

## Limits

- The window doesn't separate seasons. Out-of-sample errors exist only from May 2024, so in the test winter the window is mostly monsoon/autumn errors (see Results).
- The intervals cover model error under climatology weather; an extreme cold wave or drought beyond 2010–2022 can fall outside.

## Results

Run of 2026-10-26 (`nea model`). Winter coverage of [P10, P90] for the selected models; the target is 80%.

| Target | h=1 | h=7 | h=14 | h=30 |
|---|---|---|---|---|
| requirement | 89% | 92% | 80% | 95% |
| peak | 91% | 92% | 92% | 97% |
| domestic gen | 94% | 89% | 80% | 97% |
| net exchange | 84% | 88% | 98% | **67%** |
| import need (direct model) | 81% | 92% | 97% | **58%** |

- **Demand, peak and generation: too wide (cautious).** 89–97% fall inside instead of 80%. The 60-error window at winter origins is mostly monsoon/autumn errors, which are larger. For planning, an interval that is too wide is the safe failure.
- **Import at 30 days: too narrow.** Winter import swings harder than the summer errors in the window suggest. Read these as "at least this uncertain".
- **Why not fixed now:** the fix is a winter-only error window. But out-of-sample errors start in May 2024, so no earlier winter exists to fill it, and tuning the window on the one test winter would be fitting to the test. Once the widget gives a second winter of daily data, switch to same-season windows (one parameter in `_bounds`).
- Live import need (difference method) uses deliberately conservative bounds: demand P10 − generation P90 and demand P90 − generation P10.
- 3,270 backtest forecasts with P10/P90 are stored in `ml.forecasts` (run_id `bt-*`) for the site.
