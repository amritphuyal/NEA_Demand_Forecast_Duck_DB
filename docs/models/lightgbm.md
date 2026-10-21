# LightGBM (daily, challenger)

**Role:** tests whether nonlinear interactions the ridge model misses are worth the extra complexity. It is kept only if it proves it.

## How it works

Gradient-boosted decision trees: each new small tree fits the errors of the trees before it. Settings are chosen for small data and fixed before testing:

`num_boost_round=300, learning_rate=0.05, num_leaves=15, min_data_in_leaf=10, bagging_fraction=0.8, feature_fraction=0.8` (native `lgb.train`)

- **Features:** same as [ridge](ridge.md), plus Kathmandu minimum-temperature climatology. EDA left it below the 0.3 bar, and trees can test it at little risk.
- **Target:** the change from today, $y_{t+h} - y_t$, not the level. Trees can't extrapolate: demand grows 12%/yr, so a level target would cap forecasts at the highest value seen in training. Predicting the change and adding $y_t$ back avoids that. An absolute change (not a ratio) is used because net exchange and import cross zero.

## Why consider it

- LightGBM ensembles won M5 [lit 25], and boosting was part of a GEFCom2017 top-3 entry [lit 23].
- Trees capture thresholds and interactions (holiday × season, discharge × temperature) without hand-made terms.

## Why it may lose here

M5 had about 42,000 series; we have one series with about 600 rows. On small samples ML tends to overfit where linear models hold [lit 29], and Hong notes that regression wins when good drivers exist [lit 24].

## Selection rule

`select()` keeps LightGBM for a (target, horizon) only if **both** hold:
1. Its winter MAE is more than 5% below the current best (climbing from the best baseline).
2. A Diebold–Mariano test on the paired absolute errors gives p < 0.10.

Then the **simplest** model within 5% of the winner is used (blueprint rule): equal skill goes to the less complex model.

If it is never selected, it is removed from the code and dependencies and the change log records why. A model that doesn't earn its place isn't kept.

## How it is tested

- `select_one()` unit tests:
  - 3% better → stays.
  - 10% better but p = 0.4 → stays.
  - LightGBM only 0.6% better than ridge → ridge.
- Same rolling-origin backtest as ridge, same features, ex-ante weather.

## Results

Run `bt-20261026-082917`. Winter MAE (MAPE); p = Diebold–Mariano LightGBM vs ridge.

| Target | h=1 | h=7 | h=14 | h=30 |
|---|---|---|---|---|
| requirement | 936 (2.8%) vs ridge 812 · p=0.03 | 1,674 (5.1%) vs 1,136 · p=0.008 | 2,806 (8.4%) vs 1,327 · p<0.001 | 3,410 (10.6%) vs 1,531 · p<0.001 |
| peak MW | 49 (2.7%) vs 44 · p=0.26 | 115 (6.3%) vs 53 · p<0.001 | 121 (6.6%) vs 54 · p<0.001 | 190 (10.7%) vs 70 · p<0.001 |
| domestic gen | 757 vs 634 · p=0.02 | 1,406 vs 1,331 · p=0.68 | 2,517 vs 2,003 · p=0.08 | 2,920 vs 2,871 · p=0.74 |
| net exchange | 825 vs 607 · p=0.001 | 1,646 vs 1,174 · p=0.05 | 2,157 vs 2,169 · p=0.99 | 4,030 vs 4,104 · p=0.88 |
| import need | 948 vs 791 · p=0.02 | 2,003 vs 1,369 · p=0.007 | 2,658 vs 2,638 · p=0.98 | **4,326** vs 4,716 · p=0.28 |

**Verdict:** LightGBM is **significantly worse** than ridge for demand and peak. At 14–30 days its error is 2–3× higher, the expected small-data overfit [lit 29]. It is selected in **one** case, import need at 30 days (8% lower MAE than ridge).

That selection is weak: ridge itself didn't significantly beat the naive baseline there (p = 0.16), LightGBM did, and LightGBM vs ridge is not significant (p = 0.28). It is kept in the code for that case and flagged. If the next winter's backtest doesn't confirm it, LightGBM and its dependency go.
