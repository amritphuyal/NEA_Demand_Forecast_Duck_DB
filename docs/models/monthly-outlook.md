# Monthly winter outlook (Nov–Apr)

**Role:** before winter starts (origin = end of October), forecast each month's demand and import for Nov–Apr.

## Data

- **Demand:** NEA annual-report monthly balance, national demand GWh, 2021-07 → 2026-05 (53 months; BS months mapped to the AD month they start in).
- **Import:** customs monthly 2017 → (×1.09 to the NEA level); also the NEA report import.
- **Driver:** monthly mean `discharge_index` (anomaly vs climatology).

## Models

| Name | Forecast | Why |
|---|---|---|
| `snaive_growth` | same month last year × (1 + trailing 12-month growth) | captures seasonality and the 12%/yr growth in one line; strong in short monthly series |
| `linear_m` | $\log y = a + b\,\text{trend} + \text{month dummies} + c\,\text{discharge anomaly}$ | log keeps growth multiplicative; the discharge term lets a dry year raise import |
| `ets` | statsmodels Holt-Winters on $\log y$: damped additive trend, additive 12-month season | the standard monthly benchmark [lit 33]; damping stops over-extrapolating growth |
| `combo` | equal-weight mean of the three | combinations beat single methods in M4 [lit 26] |

**Annual cross-check.** The sum of the Nov–Apr forecast is compared with the annual path implied by GDP elasticity (2.6, EDA) and the IMF/World Bank GDP outlook. A gap of more than 10% is flagged in the results. This matches local practice: NEA's long-term forecasts use GDP elasticity [lit 7].

## Testing

- Hold-out winters 2024/25 and 2025/26: train strictly before each 1 November and forecast 1–6 months ahead.
- Metrics: MAPE for demand, MAE for import, per month-ahead.
- Unit test: a series growing exactly 10%/yr with a fixed season → `snaive_growth` MAPE 0.

## Limits

- 53 months is about 4.4 seasonal cycles: enough for ETS seasonality, but the intervals are wide.
- Two hold-out winters means "best model" is weakly established. `combo` is the default unless one model wins both winters.
- New large plants (commissioning dates) aren't modelled, so import forecasts can be too high in the winter a big plant comes online.

## Results

_Filled by `nea model` (Phase 3, Task 5)._
