---
toc: true
---

```js
import {q} from "./components/db.js";
import {freshness} from "./components/common.js";
const selection = FileAttachment("data/selection.json").json();
```

# Models: how they were tested and which one won

```js
display(await freshness())
```

**The ladder.** Start with naive baselines, climb to ridge regression, then LightGBM. A more complex model is used only if its **winter** error is more than 5% lower **and** a Diebold–Mariano test says the gain is not luck (p < 0.10). After that, the simplest model within 5% of the winner is taken.

**The test.** A rolling origin: for every day from May 2024, each model is trained only on data before that day and forecasts 1, 7, 14 and 30 days ahead. Future weather comes from the long-term average for that day of the year (what you'd really know), not the actual weather.

## Winter error by horizon

```js
const bt = await q(`SELECT model, target, horizon, mae, mape, n FROM backtest_metrics
  WHERE season = 'winter' AND weather = 'clim' AND target NOT IN ('demand_gwh', 'import_gwh') AND model IN ('naive', 'snaive', 'wma30', 'ridge', 'lgbm')`);
const T = {requirement_mwh: "Daily demand (MWh)", peak_demand_mw: "Peak (MW)", domestic_gen_mwh: "Domestic generation (MWh)", net_exchange_india_mwh: "Net import (MWh)", import_need_mwh: "Import need (MWh)"};
```

```js
// one small chart per target: each has its own units and scale
function small(data, colorKey, domain, label) {
  return htl.html`<div style="display: flex; flex-wrap: wrap; gap: 12px;">${Object.keys(T).filter((t) => data.some((d) => d.target === t)).map((t) => htl.html`<div class="card" style="margin: 0;">${
    Plot.plot({title: T[t], width: 300, height: 220, x: {label: "horizon (days)", ticks: [1, 7, 14, 30]},
      y: {grid: true, label: "winter MAE", zero: true}, color: {domain, tickFormat: label},
      marks: [Plot.lineY(data.filter((d) => d.target === t), {x: "horizon", y: "mae", stroke: colorKey, marker: "dot", tip: true})]})}</div>`)}</div>`;
}
display(Plot.legend({color: {domain: ["naive", "snaive", "wma30", "ridge", "lgbm"]}}));
display(small(bt, "model", ["naive", "snaive", "wma30", "ridge", "lgbm"]));
```

Each chart has its own units, and lower is better. For demand and peak, ridge is lowest at every horizon. LightGBM overfits: about 600 days is too little for trees.

## Which model ships

```js
const sel = Object.entries(await selection).map(([k, v]) => ({target: k.split("|")[0], horizon: k.split("|")[1], model: v}));
const win = await q(`SELECT target, horizon, model, mae, mape, coverage, dm_p FROM backtest_metrics WHERE season = 'winter' AND weather = 'clim'`);
const look = new Map(win.map((d) => [`${d.target}|${d.horizon}|${d.model}`, d]));
display(Inputs.table(sel.map((s) => ({...s, ...(look.get(`${s.target}|${s.horizon}|${s.model}`) ?? {})})),
  {columns: ["target", "horizon", "model", "mae", "mape", "coverage", "dm_p"],
   format: {mae: (x) => x?.toFixed(0), mape: (x) => x == null ? "" : x.toFixed(1) + "%", coverage: (x) => x == null ? "" : (100 * x).toFixed(0) + "%", dm_p: (x) => x?.toFixed(3) ?? ""},
   header: {mape: "MAPE", coverage: "P10–P90 coverage", dm_p: "DM p vs simpler"}}))
```

- `import_need_method` = **diff**: import need is forecast as demand − generation. It beat the direct model at 14–30 days and ties at 1–7.
- **Coverage** is the share of actual values inside the P10–P90 range (target 80%). Above 80% the range is cautious; below, too narrow.

## How much would better weather knowledge help?

```js
const wx = await q(`SELECT target, horizon, weather, mae FROM backtest_metrics WHERE model = 'ridge' AND season = 'winter' AND target IN ('requirement_mwh', 'domestic_gen_mwh', 'import_need_mwh')`);
const W = {clim: "normal weather (what we use)", q_actual: "river flow known", actual: "all weather known"};
```

```js
display(Plot.legend({color: {domain: Object.keys(W), tickFormat: (k) => W[k]}}));
display(small(wx, "weather", Object.keys(W), (k) => W[k]));
```

Knowing the river flow (a perfect river forecast) helps generation only a little. Knowing *all* the weather helps generation more, but nobody has that 30 days ahead. For demand, actual weather doesn't help at all.

## Backtest: forecasts vs what happened

```js
const PICKS = [["requirement_mwh", 7, "Demand, 7 days ahead"], ["peak_demand_mw", 1, "Peak, 1 day ahead"], ["domestic_gen_mwh", 30, "Generation, 30 days ahead"]];
const pick = view(Inputs.radio(PICKS, {value: PICKS[0], format: (d) => d[2], label: "Show"}));
```

```js
const fb = await q(`SELECT f.date, f.yhat, f.p10, f.p90, CASE '${pick[0]}' WHEN 'requirement_mwh' THEN d.requirement_mwh WHEN 'peak_demand_mw' THEN d.peak_demand_mw
  ELSE d.nea_gen_mwh + d.nea_sub_gen_mwh + d.ipp_gen_mwh END AS actual
  FROM forecasts f JOIN daily_features d USING (date) WHERE f.run_id LIKE 'bt-%' AND f.target = '${pick[0]}' AND f.horizon = ${pick[1]} ORDER BY f.date`);
```

```js
Plot.plot({width, height: 320, y: {grid: true}, color: {legend: true},
  marks: [Plot.areaY(fb, {x: "date", y1: "p10", y2: "p90", fill: "steelblue", fillOpacity: 0.2}),
    Plot.lineY(fb, {x: "date", y: "actual", stroke: () => "actual", strokeWidth: 1}),
    Plot.lineY(fb, {x: "date", y: "yhat", stroke: () => "forecast", strokeWidth: 1, tip: true})]})
```

## Monthly winter outlook: two hold-out winters

```js
const mb = await q(`SELECT model, target, horizon, mae, mape FROM backtest_metrics WHERE target IN ('demand_gwh', 'import_gwh')`);
const MON = ["", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr"];
```

```js
Plot.plot({width, height: 260, x: {label: "month (forecast made 31 Oct)", tickFormat: (h) => MON[h], ticks: [1, 2, 3, 4, 5, 6]}, y: {grid: true, label: "MAE (GWh/month)"},
  fx: {label: null, tickFormat: (t) => t === "demand_gwh" ? "Demand" : "Import"}, color: {legend: true}, facet: {data: mb, x: "target"},
  marks: [Plot.lineY(mb, {x: "horizon", y: "mae", stroke: "model", fx: "target", marker: "dot", tip: true})]})
```

No single model won both winters, so the outlook uses **combo**, the average of the three. Combinations are the most reliable choice on short series.
