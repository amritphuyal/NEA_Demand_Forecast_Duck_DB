# River-flow forecast (GloFAS)

**Role:** replace "normal river flow for this time of year" (climatology) with an actual forecast where one exists. In winter, river flow drives domestic generation, and generation drives import.

## Source

Open-Meteo flood API, GloFAS v4 (seamless: 30-day daily forecast, then the 7-month seasonal forecast), ~5 km grid, ensemble of 50 members:
- **Ingester:** `nea ingest discharge_forecast`.
- **Query:** one request for all 8 points.
- **Fields:** `river_discharge_mean`, `_p25`, `_p75`, to about 7 months ahead.
- **Storage:** `silver.river_discharge_forecast`, one issue per run day, so past forecasts stay available and can be scored later.

## How it is used

| Where | Without a forecast | With the forecast |
|---|---|---|
| Daily generation model (live) | target-day river index = climatology | the generation model is trained in **q_actual** mode (river flow known, temperature from climatology) and fed the GloFAS ensemble mean for target days |
| Monthly `linear_m` (live) | discharge anomaly = last observed month (persistence) | anomaly of the forecast monthly mean vs the 2010–2022 same-month mean |

Demand models keep climatology: actual weather didn't help demand (see [ridge](ridge.md)).

## What a forecast can add (backtest upper bound)

GloFAS keeps no archive of its past forecasts here, so the forecast itself can't be backtested. Instead, the **q_actual** backtest gives the model the *actual* river flow, which is a perfect forecast and therefore the best case. Winter MAE:

| Target | h | climatology | perfect river forecast | all weather known |
|---|---|---|---|---|
| domestic generation | 30 | 2,871 (8.8%) | 2,600 (8.1%) | 1,759 (5.4%) |
| import need | 30 | 4,716 | 4,352 | 3,359 |
| net exchange | 30 | 4,104 | 3,874 | 2,760 |

**Honest reading:** even a perfect river forecast cuts the 30-day generation error only from 8.8% to 8.1%. Most of the ex-post gain needs the actual *weather* too, which no one has 30 days ahead. So the GloFAS forecast is mainly useful for the **seasonal signal** (is this a dry or wet winter?), not for daily precision.

## This winter (issued 2026-10-26)

Forecast river flow vs the 2010–2022 normal (sum of the Karnali, Koshi and Narayani basins):

| Nov | Dec | Jan | Feb | Mar | Apr |
|---|---|---|---|---|---|
| +24% | −6% | −13% | −26% | −24% | −30% |

A dry late winter: lower run-of-river output from January, on top of the flood losses ([outages](outages.md)). The monthly import model takes the anomaly into account. Its effect in the combination is small (import +0–3 GWh/month), because the import series' monthly coefficient on discharge is weak. The outage adjustment is the bigger correction.

## Limits

- GloFAS is a global model at ~5 km. Global streamflow forecasts have been weak at Nepal run-of-river sites [lit 17]. Treat it as a basin-scale signal.
- It doesn't know about damaged intakes: a river can be full while the plant is gone. Plant losses are handled separately in [outages](outages.md).
