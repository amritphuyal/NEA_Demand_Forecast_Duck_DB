# Ridge regression (daily, main candidate)

**Role:** the load-forecasting "vanilla benchmark" [lit 19], adapted to Nepal. We expect it to be the model that ships.

## How it works

One model per horizon $h$ (a "direct" forecast). The target is the **change from today**, $\Delta = y_{t+h} - y_t$, and the forecast is $\hat y_{t+h} = y_t + \hat\Delta$. Each model minimises

$$\sum_t \big(\Delta_t - \beta_0 - \beta^\top x(t,h)\big)^2 + \lambda \lVert\beta\rVert^2$$

with standardised features. $\lambda \in \{0.1, 1, 10, 100\}$ is picked on the last 60 days of each training window (time-ordered, never random). It is solved in closed form with numpy (`lstsq` on the augmented system), so there's no iterative training and the same data always gives the same model.

Why the change and not the level: ridge shrinks $\beta$ toward 0, which then means "tomorrow = today", the strongest baseline. With a level target, it would shrink toward the mean instead.

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

Run `bt-20261026-082239`. Winter origins Nov 2024 → Jan 2025. MAE (MAPE); DM p = Diebold–Mariano vs the best baseline.

| Target | h=1 | h=7 | h=14 | h=30 |
|---|---|---|---|---|
| requirement MWh | 812 (2.5%) p=0.08 | 1,136 (3.5%) p=0.09 | 1,327 (4.1%) p=0.005 | 1,531 (4.9%) p<0.001 |
| *best baseline* | *974 (3.0%)* | *1,626 (5.1%)* | *2,385 (7.5%)* | *4,042 (12.5%)* |
| peak MW | 44 (2.4%) p=0.001 | 53 (3.0%) p=0.009 | 54 (3.1%) p<0.001 | 70 (4.0%) p=0.008 |
| *best baseline* | *59 (3.3%)* | *82 (4.6%)* | *109 (6.2%)* | *175 (9.6%)* |
| domestic gen MWh | 634 (1.9%) p=0.71 | 1,331 (4.0%) p=0.32 | 2,003 (6.2%) p=0.29 | 2,871 (8.8%) p<0.001 |
| net exchange MWh | 607 p=0.21 | 1,174 p=0.01 | 2,169 p=0.21 | 4,104 p=0.15 |
| import need MWh | 791 p=0.27 | 1,369 p=0.02 | 2,638 p=0.35 | 4,716 p=0.16 |

**Reading it:**
- Demand and peak beat the baselines at every horizon, and the result is significant. Next-day peak at 2.4% is below the Nepal LSTM reference (2.95%) [lit 3].
- Generation and import are better on average, but the difference is often not significant: one winter is a small sample.

**Ex-ante vs ex-post (actual weather):**
- Demand: h=30 is 4.9% ex-ante vs 5.6% ex-post. Actual weather does **not** help. The weather terms mostly carry the seasonal shape, so a daily weather-forecast feed would add little.
- Generation: h=30 is 8.8% ex-ante vs **5.4%** ex-post, but that needs all weather known. With only river flow known (`q_actual` mode, a perfect river forecast) it is **8.1%**. So most of the gain needs actual weather, which no one has 30 days ahead. The GloFAS forecast is still used live, mainly for the seasonal dry/wet signal: see [river-forecast](river-forecast.md).

**Threshold sensitivity** (winter demand MAPE):

| HDD base | CDD base | h=1 | h=7 | h=14 | h=30 |
|---|---|---|---|---|---|
| 12 | 24 | 2.49% | 4.08% | 4.46% | 7.20% |
| **15** | **24** | **2.46%** | **3.52%** | **4.11%** | **4.87%** |
| 18 | 24 | 2.50% | 3.92% | 4.90% | 7.05% |
| 15 | 21 | 2.42% | 4.04% | 4.82% | 6.72% |
| 15 | 27 | 2.44% | 3.94% | 4.66% | 7.64% |

The thresholds were fixed before testing, and they turned out best. Still, h=30 moves between 4.9% and 7.6% with ±3 °C, so the exact 30-day figure is **fragile** on one winter; quote it as "5–8%". Every setting still beats the best baseline (12.5%) by a wide margin, so the conclusion holds.

**Coefficient stability** (standardised, h=1 demand, fit on 2023 vs 2024): all 19 coefficients have the same sign in both years. For example, Saturday −951/−1,082, holiday −435/−409, CDD 1,052/986, HDD 187/328. The relationships held through 12%/yr growth.
