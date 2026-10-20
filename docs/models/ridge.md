# Ridge regression (daily, main candidate)

**Role:** the load-forecasting "vanilla benchmark" [lit 19], adapted to Nepal. We expect it to be the model that ships.

## How it works

One model per horizon $h$ (a "direct" forecast). Each is trained on rows $(x(t,h),\, y_{t+h})$ by minimising

$$\sum_t \big(y_{t+h} - \beta_0 - \beta^\top x(t,h)\big)^2 + \lambda \lVert\beta\rVert^2$$

with standardised features. $\lambda \in \{0.1, 1, 10, 100\}$ is picked on the last 60 days of each training window (time-ordered, never random). It is solved in closed form with numpy (`lstsq` on the augmented system), so there's no iterative training and the same data always gives the same model.

## Features $x(t,h)$, all known at origin $t$

| Group | Features | Why (evidence) |
|---|---|---|
| Level | $y_t$, 7-day mean, `snaive` value | carries the 12%/yr growth and current level; protects against structural drift |
| Calendar (target day) | weekday one-hot, `is_holiday` | Saturday −5%, holidays −5.1% (EDA) |
| Heating | HDD = max(0, 15 °C − Kathmandu mean temp) | winter heating effect; Dec–Feb corr −0.24 (EDA), same sign as the IEEE PES Nepal finding [lit 2] |
| Cooling | CDD = max(0, Terai mean temp − 24 °C), Terai mean temp | summer cooling, corr 0.64, +1,170 MWh/°C (EDA) |
| Recency | temperature anomaly at $t$ and 7-day mean anomaly | the "recency effect" of Wang, Liu & Hong [lit 37] |
| River | discharge climatology on target day, discharge anomaly at $t$ (and 7-day mean) | generation ~ discharge corr 0.82 (EDA); persistence is strong on snow-fed rivers [lit 16] |
| Trend | days since 2023-01-01 | slow growth on top of level |

**Ex-ante vs ex-post.** Target-day weather and discharge are **climatology** (2010–2022 mean for that day of year) in the main results. The ex-post variant puts in the actual values; the gap between the two is the value a real weather forecast would add [lit 24, 30].

HDD/CDD thresholds (15 °C, 24 °C) are fixed up front. Task 2 reports a ±3 °C sensitivity check, so the choice can't be tuned to the test.

## Why ridge (and not plain OLS or GAM)

- Regression with temperature and calendar terms is in every GEFCom winning entry [lit 20–22].
- Ridge shrinks coefficients, which stops about 20 features from overfitting 400–600 rows.
- HDD/CDD give the bent temperature response a GAM would fit, with two numbers instead of a spline [lit 21]. If the residuals still show curvature against temperature, a spline term is the next step (documented, not built).

## Assumptions and limits

- The relationships are linear in the features; interactions only enter through HDD/CDD and the season split.
- The coefficients are assumed stable from 2023 to 2025. Task 2 checks this by fitting on 2023 vs 2024 and comparing signs and sizes.
- Climatology can't predict a cold wave. Expect the largest errors in extreme weeks; the intervals widen for them.

## How it is tested

- Unit test: synthetic $y = 3x_1 - 2x_2 + 5$ → coefficients recovered within 1%.
- Leakage test: changing any data after the origin leaves the features unchanged.
- Backtest: rolling origin, compared with the baselines on winter MAE plus the Diebold–Mariano test.

## Results

_Filled by `nea model` (Phase 3, Task 2): winter and overall MAE/MAPE per horizon, ex-ante vs ex-post, coefficient table, stability check._
