# Import need (daily and monthly)

**Role:** answer how much power Nepal must buy from India.

## Two definitions (keep them apart)

The NDOR energy balance gives:

$$\text{net\_exchange} = \text{import} - \text{export} = \text{requirement} - \text{interruption} - \text{deficit} - \text{domestic\_gen}$$

| Quantity | Formula | Meaning |
|---|---|---|
| **Actual net import** | `net_exchange_india_mwh` | what NEA actually bought, after cutting load |
| **Import need** | requirement − domestic generation | what full demand would require; it includes unserved load (interruption + deficit, up to 2.8 GWh/day in April, per EDA) |

For planning, **import need** is the honest target: actual import understates need whenever NEA sheds load.

## Two ways to forecast it

1. **Direct:** the selected daily model ([ridge](ridge.md) or [lightgbm](lightgbm.md)) trained on the target itself.
2. **Difference:** forecast requirement and domestic generation separately, then subtract. The generation model uses the same features; river discharge carries the physics (generation ~ discharge corr 0.82; dry-season run-of-river < 40% of capacity [lit 13]).

Both are scored with MAE only (the series crosses zero, so MAPE is meaningless). The better one on winter MAE (> 5% and DM p < 0.10) ships. If neither wins, the **difference** method is preferred because it explains *why* import moves: demand up, or rivers down.

## Monthly

Customs import 2017 → is scaled ×1.09 to the NEA report level (EDA reconciliation, customs vs NDOR corr 0.99). It is forecast with the [monthly outlook](monthly-outlook.md) models. As a cross-check: monthly demand outlook − generation implied by discharge climatology.

## Evidence

- Import tracks discharge (corr −0.77, EDA) and was about a third of national need in dry 2018 [lit 14].
- No published study forecasts import from discharge [lit, §2]. This is our design, built on the physical balance above, and that's why both methods are tested against each other rather than one being assumed.

## Limits

- India-side constraints (IEX price, transmission limits, bilateral contracts) aren't modelled; forecasts assume supply is available.
- Import share fell from 37% to 6% (2019 → 2026), so history overstates future import. Lag features and the difference method adapt; the monthly model uses recent years only.

## Results

_Filled by `nea model` (Phase 3, Task 4): direct vs difference MAE per horizon, winter only._
