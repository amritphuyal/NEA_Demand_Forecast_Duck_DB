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

Run `bt-20261026-082024` (`nea model`, 2026-10-26). Winter origins only, from Nov 2024 to Jan 2025: MAE, with MAPE in brackets.

| Target | Model | h=1 | h=7 | h=14 | h=30 |
|---|---|---|---|---|---|
| requirement MWh | naive | **974 (3.0%)** | **1,626 (5.1%)** | **2,385 (7.5%)** | **4,042 (12.5%)** |
| | snaive | 1,537 (4.8%) | 1,626 (5.1%) | 2,385 (7.5%) | 4,284 (13.2%) |
| | wma30 | 1,573 (4.9%) | 2,194 (6.8%) | 2,632 (8.1%) | 4,361 (13.5%) |
| peak MW | naive | **59 (3.3%)** | **82 (4.6%)** | **109 (6.2%)** | 186 (10.3%) |
| | wma30 | 80 (4.4%) | 104 (5.7%) | 119 (6.5%) | **175 (9.6%)** |
| domestic gen MWh | naive | **657 (2.0%)** | **1,606 (4.8%)** | **2,927 (8.6%)** | **6,692 (20.4%)** |
| net exchange MWh | naive | **695** | **2,164** | **3,501** | **6,982** |
| import need MWh | naive | **869** | **2,445** | **3,726** | **7,793** |

- At h = 7 and h = 14, `naive` and `snaive` are the same forecast (target − 7·k = origin), as designed.
- Winter persistence is strong: demand and generation change slowly from day to day. By 30 days ahead, errors grow 4–10×. That's where the weather and river terms should help.
- Next-day peak naive gives 3.3% (our national daily data). The Pulchowk thesis reports LSTM 2.95% and WMA 3.0% on its series. So ridge has to beat a strong floor.
