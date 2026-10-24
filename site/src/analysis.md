---
toc: true
---

```js
import {q} from "./components/db.js";
import {freshness} from "./components/common.js";
```

# Analysis: what drives demand and imports

```js
display(await freshness())
```

Daily figures use the 612 checked NEA daily reports (Apr 2023 – Jan 2025); all-zero report days are excluded. Every number below is computed live from the data.

## 1. Seasonality: winter imports are a supply problem

```js
const season = await q(`SELECT season, avg(requirement_mwh) / 1000 AS demand, avg(net_exchange_india_mwh) / 1000 AS net_import, count(*) AS days
  FROM daily_features WHERE qa_ok GROUP BY 1 ORDER BY 1`);
const bsm = await q(`SELECT bs_month, avg(requirement_mwh) / 1000 AS demand, avg(net_exchange_india_mwh) / 1000 AS net_import FROM daily_features WHERE qa_ok GROUP BY 1 ORDER BY 1`);
const NAMES = ["Baishakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin", "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"];
```

```js
Inputs.table(season, {format: {demand: (x) => x.toFixed(1) + " GWh/day", net_import: (x) => x.toFixed(1) + " GWh/day"}})
```

```js
Plot.plot({title: "By Nepali month: average demand and net import from India (GWh/day; negative = export)", width, height: 300,
  fx: {domain: NAMES, label: null, padding: 0.1}, x: {axis: null}, y: {grid: true, label: "GWh/day"}, color: {legend: true, domain: ["demand", "net import"], range: ["var(--nea-demand)", "var(--nea-import)"]},
  marks: [Plot.ruleY([0]),
    Plot.barY(bsm.flatMap((d) => [{m: NAMES[d.bs_month - 1], k: "demand", v: d.demand}, {m: NAMES[d.bs_month - 1], k: "net import", v: d.net_import}]),
      {fx: "m", x: "k", y: "v", fill: "k", tip: true})]})
```

Demand peaks in the monsoon (Jestha–Bhadra), when Nepal **exports**. Imports happen in Poush–Chaitra (Dec–Apr), when demand is *lower* but the rivers are low.

```js
const cal = await q(`SELECT
  100 * (avg(requirement_mwh) FILTER (is_saturday) / avg(requirement_mwh) FILTER (NOT is_saturday) - 1) AS saturday_pct,
  100 * avg(h / nh - 1) AS holiday_pct
  FROM daily_features d, (SELECT bs_year, bs_month, avg(requirement_mwh) FILTER (is_holiday) h, avg(requirement_mwh) FILTER (NOT is_holiday) nh
                          FROM daily_features WHERE qa_ok GROUP BY 1, 2) m
  WHERE d.qa_ok AND d.bs_year = m.bs_year AND d.bs_month = m.bs_month AND h IS NOT NULL`);
```

Calendar effects: Saturday (the weekend) **${cal[0].saturday_pct.toFixed(1)}%**; public holidays **${cal[0].holiday_pct.toFixed(1)}%** vs other days of the same month.

## 2. Temperature

```js
const temp = await q(`SELECT date, requirement_mwh / 1000 AS demand, tmin_ktm, tmean_terai,
  CASE WHEN month(date) IN (12, 1, 2) THEN 'core winter (Dec–Feb)' WHEN season = 'summer' THEN 'summer' ELSE 'shoulder' END AS period
  FROM daily_features WHERE qa_ok AND NOT is_saturday AND NOT is_holiday`);
const tc = await q(`SELECT 'Dec–Feb vs Kathmandu night low' AS relation, corr(requirement_mwh, tmin_ktm) AS r, regr_slope(requirement_mwh, tmin_ktm) AS mwh_per_degC, count(*) AS n
  FROM daily_features WHERE qa_ok AND NOT is_saturday AND NOT is_holiday AND month(date) IN (12, 1, 2)
  UNION ALL SELECT 'Summer vs Terai mean temperature', corr(requirement_mwh, tmean_terai), regr_slope(requirement_mwh, tmean_terai), count(*)
  FROM daily_features WHERE qa_ok AND NOT is_saturday AND NOT is_holiday AND season = 'summer'`);
```

<div class="grid grid-cols-2">

```js
Plot.plot({title: "Core winter: colder Kathmandu nights → slightly more demand", width: width / 2, height: 280, x: {label: "Kathmandu min °C"}, y: {label: "GWh/day", grid: true},
  marks: [Plot.dot(temp.filter((d) => d.period.startsWith("core")), {x: "tmin_ktm", y: "demand", r: 2.5, fill: "var(--nea-demand)", tip: true}), Plot.linearRegressionY(temp.filter((d) => d.period.startsWith("core")), {x: "tmin_ktm", y: "demand"})]})
```

```js
Plot.plot({title: "Summer: hotter Terai → more demand (cooling)", width: width / 2, height: 280, x: {label: "Terai mean °C"}, y: {label: "GWh/day", grid: true},
  marks: [Plot.dot(temp.filter((d) => d.period === "summer"), {x: "tmean_terai", y: "demand", r: 2.5, fill: "var(--nea-import)", tip: true}), Plot.linearRegressionY(temp.filter((d) => d.period === "summer"), {x: "tmean_terai", y: "demand"})]})
```

</div>

```js
Inputs.table(tc, {format: {r: (x) => x.toFixed(2), mwh_per_degC: (x) => x.toFixed(0)}})
```

## 3. River flow drives generation and imports

```js
const lag = await q(`
  WITH d AS (SELECT date, nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh AS g, net_exchange_india_mwh AS x FROM daily_features WHERE qa_ok)
  SELECT k AS lag_days, corr(d.g, f.discharge_index) AS generation, corr(d.x, f.discharge_index) AS net_import
  FROM range(0, 31) r(k) JOIN d ON true JOIN daily_features f ON f.date = d.date - CAST(k AS INTEGER)
  GROUP BY k ORDER BY k`);
const sc = await q(`SELECT date, discharge_index, (nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh) / 1000 AS generation, net_exchange_india_mwh / 1000 AS net_import, season
  FROM daily_features WHERE qa_ok AND discharge_index IS NOT NULL`);
```

<div class="grid grid-cols-2">

```js
Plot.plot({title: "River index vs domestic generation (GWh/day)", width: width / 2, height: 280, x: {type: "log", label: "river index (m³/s, 3 basins)"}, y: {grid: true},
  color: {legend: true, domain: ["winter", "summer"], range: ["var(--nea-demand)", "#c28a12"]}, marks: [Plot.dot(sc, {x: "discharge_index", y: "generation", stroke: "season", r: 2, tip: true})]})
```

```js
Plot.plot({title: "Correlation with river flow k days earlier", width: width / 2, height: 280, y: {domain: [-1, 1], grid: true}, x: {label: "lag (days)"},
  color: {legend: true, domain: ["generation", "net import"], range: ["var(--nea-river)", "var(--nea-import)"]}, marks: [Plot.ruleY([0]),
    Plot.lineY(lag.flatMap((d) => [{k: d.lag_days, s: "generation", r: d.generation}, {k: d.lag_days, s: "net import", r: d.net_import}]), {x: "k", y: "r", stroke: "s", tip: true})]})
```

</div>

Generation follows river flow (r ≈ ${lag[0].generation.toFixed(2)}) and imports move the opposite way (r ≈ ${lag[0].net_import.toFixed(2)}). The lag curve is flat because the seasonal cycle dominates, so same-day flow plus a 7-day mean is enough.

## 4. Long-term growth

```js
const g = (await q(`SELECT 100 * (pow(max_by(total_gwh, year) / min_by(total_gwh, year), 1.0 / (max(year) - min(year))) - 1) AS energy_cagr,
  100 * (pow(max_by(national_peak_mw, year) / min_by(national_peak_mw, year), 1.0 / (max(year) - min(year))) - 1) AS peak_cagr,
  regr_slope(ln(total_gwh), ln(gdp_usd_2015)) AS elasticity, regr_r2(ln(total_gwh), ln(gdp_usd_2015)) AS r2, min(year) AS y0, max(year) AS y1
  FROM annual_history WHERE total_gwh > 0`))[0];
const ann = await q(`SELECT year, total_gwh, gdp_usd_2015 / 1e9 AS gdp_bn FROM annual_history WHERE gdp_usd_2015 IS NOT NULL ORDER BY year`);
```

${g.y0}–${g.y1}: energy grew **${g.energy_cagr.toFixed(1)}%/yr** and peak **${g.peak_cagr.toFixed(1)}%/yr**. Energy rises **${g.elasticity.toFixed(1)}×** as fast as GDP (log-log slope, R² ${g.r2.toFixed(2)}). That growth is why every model carries the latest level forward instead of a long-run average.

```js
Plot.plot({width, height: 280, x: {type: "log", label: "GDP (billion USD, 2015 prices, log)"}, y: {type: "log", label: "energy GWh (log)", grid: true},
  marks: [Plot.line(ann, {x: "gdp_bn", y: "total_gwh", marker: "dot"}), Plot.text(ann, {x: "gdp_bn", y: "total_gwh", text: (d) => String(d.year), dy: -10, fontSize: 10})]})
```
