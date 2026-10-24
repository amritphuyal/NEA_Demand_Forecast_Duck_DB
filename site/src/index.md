---
toc: false
---

```js
import {q} from "./components/db.js";
import {DEMAND_MONTHLY, IMPORT_MONTHLY, LATEST_LIVE, BASINS, freshness} from "./components/common.js";
```

# How much electricity will Nepal need from India this winter?

```js
const fc = await q(`SELECT model, target, date, yhat, p10, p90 FROM forecasts
  WHERE run_id = ${LATEST_LIVE} AND target IN ('import_gwh', 'demand_gwh') ORDER BY date`);
const lost = (await q(`SELECT sum(capacity_mw) AS mw, sum(capacity_mw) FILTER (status = 'destroyed') AS destroyed FROM plant_outage`))[0];
const sum = (model, target, months) => fc.filter((d) => d.model === model && d.target === target && (!months || months.includes(d.date.getUTCMonth()))).reduce((s, d) => s + d.yhat, 0);
const JAN_APR = [0, 1, 2, 3];
const adj = sum("combo+outage", "import_gwh", JAN_APR), base = sum("combo", "import_gwh", JAN_APR), demand = sum("combo", "demand_gwh");
const START = new Date("2019-01-01");
const river = await q(`SELECT date_trunc('month', date)::DATE AS month, avg(discharge_index) AS q FROM daily_features
  WHERE date >= '${START.toISOString().slice(0, 10)}' AND discharge_index IS NOT NULL GROUP BY 1 ORDER BY 1`);
const riverFc = await q(`
  WITH d AS (SELECT date, sum(discharge_m3s) AS q, sum(p25) AS p25, sum(p75) AS p75 FROM river_discharge_forecast
             WHERE issued = (SELECT max(issued) FROM river_discharge_forecast) AND point IN (${BASINS}) GROUP BY date HAVING count(*) = 3),
       clim AS (SELECT month(date) AS m, avg(discharge_index) AS normal FROM daily_features WHERE year(date) BETWEEN 2010 AND 2022 GROUP BY 1)
  SELECT date_trunc('month', date)::DATE AS month, avg(q) AS q, avg(p25) AS p25, avg(p75) AS p75, any_value(normal) AS normal
  FROM d JOIN clim ON clim.m = month(d.date) GROUP BY 1 ORDER BY 1`);
const winterFc = riverFc.filter((d) => JAN_APR.includes(d.month.getUTCMonth()));
const riverAnom = winterFc.reduce((s, d) => s + d.q, 0) / winterFc.reduce((s, d) => s + d.normal, 0) - 1;
const imp = await q(`${IMPORT_MONTHLY} AND month >= '${START.toISOString().slice(0, 10)}' ORDER BY month`);
const fmt = (x) => x.toLocaleString("en", {maximumFractionDigits: 0});
```

<p class="nea-lede">From January to April 2027 Nepal will need about <strong>${fmt(adj)} GWh</strong> of electricity from India. The models alone expect ${fmt(base)} GWh; the rest comes from the August 2026 flood, which took ${fmt(lost.mw)} MW off the grid.</p>

```js
const X = {domain: [START, new Date("2027-05-01")]};
const today = new Date();
const imports = fc.filter((d) => d.target === "import_gwh");
```

<figure class="nea-mirror">

<div class="nea-key"><span style="--c: var(--nea-river)">River flow, three big basins</span><span style="--c: var(--theme-foreground-muted)">Normal flow (2010–2022)</span><span style="--c: var(--nea-import)">Import from India, with flood losses</span><span style="--c: color-mix(in srgb, var(--nea-import) 45%, transparent)">Import, models only</span></div>

```js
Plot.plot({
  width, height: 210, marginLeft: 64, marginBottom: 0, x: {...X, axis: null},
  y: {label: "River flow (m³/s)", grid: true, ticks: 4, tickFormat: (d) => d ? `${d / 1000}k` : ""},
  marks: [
    Plot.areaY(river, {x: "month", y: "q", fill: "var(--nea-river)", fillOpacity: 0.28, curve: "monotone-x"}),
    Plot.lineY(river, {x: "month", y: "q", stroke: "var(--nea-river)", strokeWidth: 1.5, curve: "monotone-x", tip: {format: {x: "%b %Y"}}}),
    Plot.areaY(riverFc, {x: "month", y1: "p25", y2: "p75", fill: "var(--nea-river)", fillOpacity: 0.18, curve: "monotone-x"}),
    Plot.lineY(riverFc, {x: "month", y: "q", stroke: "var(--nea-river)", strokeWidth: 2, strokeDasharray: "4,3", curve: "monotone-x"}),
    Plot.lineY(riverFc, {x: "month", y: "normal", stroke: "var(--theme-foreground-muted)", strokeWidth: 1, curve: "monotone-x"}),
    Plot.ruleX([today], {stroke: "var(--theme-foreground-faint)", strokeDasharray: "2,3"}),
    Plot.text(["today"], {x: today, frameAnchor: "top", dx: -5, dy: 2, textAnchor: "end", fill: "var(--theme-foreground-muted)", fontSize: 11})
  ]
})
```

```js
Plot.plot({
  width, height: 230, marginLeft: 64, marginTop: 28, x: {...X, axis: "top", label: null, tickFormat: "%Y"},
  y: {label: "Import (GWh/month)", reverse: true, grid: true, ticks: 4, labelAnchor: "bottom"},
  marks: [
    Plot.areaY(imp, {x: "month", y: "gwh", fill: "var(--nea-import)", fillOpacity: 0.28, curve: "monotone-x"}),
    Plot.lineY(imp, {x: "month", y: "gwh", stroke: "var(--nea-import)", strokeWidth: 1.5, curve: "monotone-x", tip: {format: {x: "%b %Y"}}}),
    Plot.areaY(imports.filter((d) => d.model === "combo+outage"), {x: "date", y1: "p10", y2: "p90", fill: "var(--nea-import)", fillOpacity: 0.15, curve: "monotone-x"}),
    Plot.lineY(imports.filter((d) => d.model === "combo"), {x: "date", y: "yhat", stroke: "var(--nea-import)", strokeOpacity: 0.45, strokeWidth: 1.5, strokeDasharray: "4,3", curve: "monotone-x"}),
    Plot.lineY(imports.filter((d) => d.model === "combo+outage"), {x: "date", y: "yhat", stroke: "var(--nea-import)", strokeWidth: 2.5, curve: "monotone-x", tip: {format: {x: "%b %Y"}}}),
    Plot.ruleX([today], {stroke: "var(--theme-foreground-faint)", strokeDasharray: "2,3"}),
    Plot.ruleY([0], {stroke: "var(--theme-foreground)"})
  ]
})
```

<figcaption>Every dry season the rivers fall and imports rise. Dashed river line: GloFAS forecast, band = ensemble quartiles. Import band: P10–P90.</figcaption>
</figure>

<dl class="nea-figures">
  <div class="import"><dt>Import, Jan–Apr 2027</dt><dd>${fmt(adj)} <small>GWh</small></dd><p>+${((adj / base - 1) * 100).toFixed(0)}% on the models-only ${fmt(base)} GWh</p></div>
  <div class="river"><dt>River flow, Jan–Apr 2027</dt><dd>${riverAnom > 0 ? "+" : "−"}${Math.abs(riverAnom * 100).toFixed(0)}<small>% vs normal</small></dd><p>GloFAS forecast, three big basins</p></div>
  <div><dt>Capacity lost in the Aug 2026 flood</dt><dd>${fmt(lost.mw)} <small>MW</small></dd><p>${fmt(lost.destroyed)} MW destroyed, the rest cut off</p></div>
  <div class="demand"><dt>Demand, Nov 2026–Apr 2027</dt><dd>${fmt(demand)} <small>GWh</small></dd><p>within 1% of the GDP-growth path</p></div>
</dl>

```js
const dem = await q(`${DEMAND_MONTHLY} AND month >= '2022-01-01' ORDER BY month`);
```

## Demand keeps growing, winter included

```js
Plot.plot({
  width, height: 280, marginLeft: 64, y: {grid: true, label: "Demand (GWh/month)", tickFormat: (d) => d.toLocaleString("en")}, x: {label: null},
  marks: [
    Plot.lineY(dem, {x: "month", y: "gwh", stroke: "var(--theme-foreground)", strokeWidth: 1.25, tip: {format: {x: "%b %Y"}}}),
    Plot.areaY(fc.filter((d) => d.target === "demand_gwh" && d.model === "combo"), {x: "date", y1: "p10", y2: "p90", fill: "var(--nea-demand)", fillOpacity: 0.18}),
    Plot.lineY(fc.filter((d) => d.target === "demand_gwh" && d.model === "combo"), {x: "date", y: "yhat", stroke: "var(--nea-demand)", strokeWidth: 2.5, tip: {format: {x: "%b %Y"}}})
  ]
})
```

<p class="small muted">Thin line: NEA monthly reports. Blue: forecast with P10–P90 band.</p>

## The story in four points

1. **Demand is not the problem: supply is.** Monsoon demand is higher than winter demand, but in the monsoon Nepal *exports*. In winter it *imports*, because the rivers are low ([Analysis](./analysis)).
2. **Rivers drive imports.** Domestic generation follows river flow (correlation 0.82), and imports move the other way (−0.77). GloFAS forecasts this winter's rivers 13–30% below normal from January ([Forecast](./forecast)).
3. **The August 2026 flood changed the picture.** About 510 MW of hydro and solar was destroyed or cut off, and Kulekhani, the only storage reservoir, is running down. No model can learn this from history, so it is added explicitly from a sourced register ([Map](./map), [Forecast](./forecast)).
4. **Simple models win here, and we show why.** Ridge regression beats every baseline for daily demand (2.5% error next day, 5–8% at 30 days). LightGBM was tested and lost, which is expected on two winters of data ([Models](./models), [Method](./method)).

```js
display(await freshness())
```

<style>
.nea-mirror { max-width: none; margin: 0 0 1rem; }
.nea-mirror figcaption { font-size: 0.85rem; color: var(--theme-foreground-muted); margin-top: 0.25rem; }
</style>
