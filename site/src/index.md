---
toc: false
---

```js
import {q} from "./components/db.js";
import {DEMAND_MONTHLY, IMPORT_MONTHLY, LATEST_LIVE, freshness} from "./components/common.js";
```

# How much electricity will Nepal need from India this winter?

```js
display(await freshness())
```

Nepal's grid is almost all **run-of-river hydro**. In winter (Nov–Apr) the rivers run low, generation falls, and Nepal buys power from India. This site forecasts that winter need from 16 years of weather and river data, NEA's own reports, and India's customs records, and shows the evidence behind every number.

```js
const fc = await q(`SELECT model, target, date, yhat, p10, p90 FROM forecasts
  WHERE run_id = ${LATEST_LIVE} AND target IN ('import_gwh', 'demand_gwh') ORDER BY date`);
const lost = (await q(`SELECT sum(capacity_mw) AS mw, sum(capacity_mw) FILTER (status = 'destroyed') AS destroyed FROM plant_outage`))[0];
const sum = (model, target, months) => fc.filter((d) => d.model === model && d.target === target && (!months || months.includes(d.date.getUTCMonth()))).reduce((s, d) => s + d.yhat, 0);
const JAN_APR = [0, 1, 2, 3];
const adj = sum("combo+outage", "import_gwh", JAN_APR), base = sum("combo", "import_gwh", JAN_APR), demand = sum("combo", "demand_gwh");
```

<div class="grid grid-cols-4">
  <div class="card"><h2>Import Jan–Apr 2027</h2><span class="big">${adj.toLocaleString('en', {maximumFractionDigits: 0})} GWh</span><p class="muted">flood-adjusted forecast</p></div>
  <div class="card"><h2>Without the flood</h2><span class="big">${base.toLocaleString('en', {maximumFractionDigits: 0})} GWh</span><p class="muted">models only: +${((adj / base - 1) * 100).toFixed(0)}% from flood losses</p></div>
  <div class="card"><h2>Capacity lost (Aug 2026 flood)</h2><span class="big">${lost.mw.toFixed(0)} MW</span><p class="muted">${lost.destroyed.toFixed(0)} MW destroyed, rest cut off</p></div>
  <div class="card"><h2>Winter demand Nov–Apr</h2><span class="big">${demand.toLocaleString('en', {maximumFractionDigits: 0})} GWh</span><p class="muted">within 1% of the GDP-growth path</p></div>
</div>

```js
const hist = await q(`${IMPORT_MONTHLY} AND month >= '2022-01-01' ORDER BY month`);
```

<div class="card">

```js
Plot.plot({
  title: "Monthly import from India (GWh): history and winter 2026/27 forecast",
  subtitle: "Shaded = P10–P90. Red adds generation lost in the Aug 2026 flood.",
  width, height: 340, y: {grid: true, label: "GWh / month"}, x: {label: null},
  color: {legend: true, domain: ["actual (customs)", "forecast: models only", "forecast: with flood losses"], range: ["currentColor", "steelblue", "#d62728"]},
  marks: [
    Plot.lineY(hist, {x: "month", y: "gwh", stroke: () => "actual (customs)"}),
    Plot.areaY(fc.filter((d) => d.target === "import_gwh"), {x: "date", y1: "p10", y2: "p90", fill: (d) => d.model === "combo" ? "forecast: models only" : "forecast: with flood losses", fillOpacity: 0.15}),
    Plot.lineY(fc.filter((d) => d.target === "import_gwh"), {x: "date", y: "yhat", stroke: (d) => d.model === "combo" ? "forecast: models only" : "forecast: with flood losses", marker: "circle"}),
    Plot.ruleY([0])
  ]
})
```

</div>

```js
const dem = await q(`${DEMAND_MONTHLY} AND month >= '2022-01-01' ORDER BY month`);
```

<div class="card">

```js
Plot.plot({
  title: "Monthly national demand (GWh): NEA reports and forecast",
  width, height: 300, y: {grid: true, label: "GWh / month"}, x: {label: null},
  marks: [
    Plot.lineY(dem, {x: "month", y: "gwh"}),
    Plot.areaY(fc.filter((d) => d.target === "demand_gwh"), {x: "date", y1: "p10", y2: "p90", fill: "steelblue", fillOpacity: 0.2}),
    Plot.lineY(fc.filter((d) => d.target === "demand_gwh"), {x: "date", y: "yhat", stroke: "steelblue", marker: "circle", tip: true})
  ]
})
```

</div>

## The story in four points

1. **Demand is not the problem: supply is.** Monsoon demand is higher than winter demand, but in the monsoon Nepal *exports*. In winter it *imports*, because the rivers are low ([Analysis](./analysis)).
2. **Rivers drive imports.** Domestic generation follows river flow (correlation 0.82), and imports move the other way (−0.77). GloFAS forecasts this winter's rivers 13–30% below normal from January ([Forecast](./forecast)).
3. **The August 2026 flood changed the picture.** About 510 MW of hydro and solar was destroyed or cut off, and Kulekhani, the only storage reservoir, is running down. No model can learn this from history, so it is added explicitly from a sourced register ([Map](./map), [Forecast](./forecast)).
4. **Simple models win here, and we show why.** Ridge regression beats every baseline for daily demand (2.5% error next day, 5–8% at 30 days). LightGBM was tested and lost, which is expected on two winters of data ([Models](./models), [Method](./method)).

<style>
.big { font-size: 2rem; font-weight: 700; }
.muted { color: var(--theme-foreground-muted); }
.small { font-size: 0.85rem; }
</style>
