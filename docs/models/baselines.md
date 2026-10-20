# Baselines (daily)

**Role:** the bar every other model must clear. If a model can't beat these, it doesn't ship.

## How they work

Forecast made at origin day $t$ for target day $t+h$ ($h$ = 1, 7, 14, 30):

| Name | Forecast $\hat y_{t+h}$ | Idea |
|---|---|---|
| `naive` | $y_t$ | tomorrow looks like today |
| `snaive` | $y_{t+h-7k}$ with $k = \lceil h/7 \rceil$ | same weekday, latest week already observed at $t$ |
| `wma30` | $\sum_{i=0}^{29} w_i\, y_{t-i} / \sum w_i$, $w_i = 30 - i$ | 30-day linearly weighted moving average: the reference the Pulchowk peak-load thesis used [lit 3] |

`snaive` respects the horizon. For $h = 14$ ($k = 2$) it uses $y_t$, the same weekday 14 days before the target. It never uses $y_{t+7}$, which is after the origin and unknown at forecast time.

## Why

- Naive and seasonal naive are the standard floor in forecasting practice [lit 33] and in GEFCom comparisons [lit 20].
- `wma30` makes our numbers comparable to the only published Nepal national peak study: LSTM 2.950% vs WMA 3.005% MAPE [lit 3].

## Assumptions and limits

- No weather, no holidays, no growth beyond what the lags carry. Expect them to fail on holidays (−5%) and at season turns (Nov, Apr).
- A missing lag date (NDOR gap) → no forecast for that origin, not a shifted value.

## How it is tested

Unit tests (`tests/test_model.py`):
- On a perfectly weekly series, `snaive` has MAE 0.
- `snaive` at h = 14 reads the date two weeks back.
- A gap returns no forecast.

The backtest protocol is in [README](README.md#3-how-the-models-are-tested-defend-these-points-first).

## Results

_Filled from `ml.backtest_metrics` by `nea model` (Phase 3, Task 1)._
