# LightGBM (daily, challenger)

**Role:** tests whether nonlinear interactions the ridge model misses are worth the extra complexity. It is kept only if it proves it.

## How it works

Gradient-boosted decision trees: each new small tree fits the errors of the trees before it. Settings are chosen for small data and fixed before testing:

`n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=10, subsample=0.8, colsample_bytree=0.8`

- **Features:** same as [ridge](ridge.md), plus Kathmandu minimum-temperature climatology. EDA left it below the 0.3 bar, and trees can test it at little risk.
- **Target:** the relative change $y_{t+h}/y_t - 1$, not the level. Trees can't extrapolate: demand grows 12%/yr, so a level target would cap forecasts at the highest value seen in training. Predicting the change and multiplying back by $y_t$ avoids that.

## Why consider it

- LightGBM ensembles won M5 [lit 25], and boosting was part of a GEFCom2017 top-3 entry [lit 23].
- Trees capture thresholds and interactions (holiday × season, discharge × temperature) without hand-made terms.

## Why it may lose here

M5 had about 42,000 series; we have one series with about 600 rows. On small samples ML tends to overfit where linear models hold [lit 29], and Hong notes that regression wins when good drivers exist [lit 24].

## Selection rule

`select()` keeps LightGBM for a (target, horizon) only if **both** hold:
1. Its winter MAE is more than 5% below ridge's.
2. A Diebold–Mariano test on the paired absolute errors gives p < 0.10.

If it is never selected, it is removed from the code and dependencies and the change log records why. A model that doesn't earn its place isn't kept.

## How it is tested

- `select()` unit test: 3% better → ridge; 10% better and significant → LightGBM.
- Same rolling-origin backtest as ridge, same features, ex-ante weather.

## Results

_Filled by `nea model` (Phase 3, Task 3): MAE vs ridge per horizon, DM p-values, selected or dropped._
