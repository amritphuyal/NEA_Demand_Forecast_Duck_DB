# Prediction intervals (P10 / P90)

**Role:** turn every point forecast into a range. Import is bought ahead, so a planner needs "between X and Y with 80% confidence", not just one number. Probabilistic forecasting is the field standard since GEFCom2014 [lit 22, 34].

## How it works (split conformal, rolling)

1. The rolling backtest already produces **out-of-sample** errors $e = y - \hat y$ for every (target, horizon, origin).
2. For a new forecast at horizon $h$, take the errors of the **last 60 origins** for that target and horizon, same season (winter/summer).
3. P10 = $\hat y + q_{0.10}(e)$ and P90 = $\hat y + q_{0.90}(e)$, where $q$ is the empirical quantile.

This makes no assumption about the error distribution (it can be skewed). The 60-origin window keeps it adaptive when the error level changes, a simplified form of adaptive conformal inference for time series, where the usual exchangeability assumption fails [lit 36].

## How it is checked

- **Coverage:** the share of actuals inside [P10, P90] should be about 80%. It is reported per horizon and season. Much lower means the intervals are too narrow, and that is reported, not hidden.
- **Pinball loss** at 0.1 and 0.9: the standard score for quantile forecasts [lit 22].

## Limits

- Winter has only one daily backtest winter, so winter intervals rest on about 70 origins: treat them as indicative.
- The intervals cover model error under climatology weather; an extreme cold wave or drought beyond 2010–2022 can fall outside.

## Results

_Filled by `nea model` (Phase 3, Task 6): coverage and pinball loss per target × horizon × season._
