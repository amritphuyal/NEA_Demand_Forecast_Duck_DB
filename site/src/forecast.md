---
toc: true
---

```js
import {q} from "./components/db.js";
import {LATEST_LIVE, freshness} from "./components/common.js";
```

# Forecast: winter 2026/27

```js
display(await freshness())
```

```js
const fc = await q(`SELECT run_id, model, target, date, yhat, p10, p90 FROM forecasts WHERE run_id = ${LATEST_LIVE} ORDER BY target, model, date`);
const run = fc[0]?.run_id ?? "none";
const pivot = [...new Set(fc.filter((d) => d.target.endsWith("_gwh")).map((d) => +d.date))].map((t) => {
  const r = (m, tg) => fc.find((d) => +d.date === t && d.model === m && d.target === tg);
  const dm = r("combo", "demand_gwh"), base = r("combo", "import_gwh"), adj = r("combo+outage", "import_gwh");
  return {month: new Date(t), demand: dm?.yhat, demand_range: dm && `${dm.p10.toFixed(0)}–${dm.p90.toFixed(0)}`,
          import_models_only: base?.yhat, import_with_flood: adj?.yhat, import_range: adj && `${adj.p10.toFixed(0)}–${adj.p90.toFixed(0)}`};
});
```

Latest run: **${run}**. Monthly figures are in GWh.

```js
Inputs.table(pivot, {format: {month: (d) => d.toLocaleString("en", {month: "short", year: "numeric", timeZone: "UTC"}),
  demand: (x) => x?.toFixed(0), import_models_only: (x) => x?.toFixed(0), import_with_flood: (x) => x?.toFixed(0)},
  header: {month: "Month", demand: "Demand", demand_range: "Demand P10–P90", import_models_only: "Import, models only", import_with_flood: "Import with flood losses", import_range: "Import P10–P90"},
  layout: "auto", select: false})
```

**Read the "import with flood losses" column.** It adds the generation lost in the 26 Aug 2026 flood; the models alone can't know about it. In November the loss only cuts exports (Nepal usually exports about 490 GWh that month). From January, every lost GWh becomes import.

## River-flow forecast (GloFAS)

```js
const rf = await q(`
  WITH f AS (SELECT date, sum(discharge_m3s) AS mean, sum(p25) AS p25, sum(p75) AS p75 FROM river_discharge_forecast
             WHERE issued = (SELECT max(issued) FROM river_discharge_forecast) AND point IN ('koshi_chatara', 'narayani_devghat', 'karnali_chisapani')
             GROUP BY date HAVING count(*) = 3),
       c AS (SELECT dayofyear(date) AS doy, avg(discharge_index) AS normal FROM daily_features WHERE year(date) BETWEEN 2010 AND 2022 GROUP BY 1)
  SELECT f.*, c.normal FROM f JOIN c ON c.doy = dayofyear(f.date) ORDER BY date`);
const anom = await q(`
  WITH f AS (SELECT date_trunc('month', date)::DATE AS month, sum(discharge_m3s) / count(DISTINCT point) * 3 AS q FROM river_discharge_forecast
             WHERE issued = (SELECT max(issued) FROM river_discharge_forecast) AND point IN ('koshi_chatara', 'narayani_devghat', 'karnali_chisapani') GROUP BY 1, date),
       m AS (SELECT month, avg(q) AS q, count(*) AS days FROM f GROUP BY 1),
       c AS (SELECT month(date) AS mo, avg(discharge_index) AS normal FROM daily_features WHERE year(date) BETWEEN 2010 AND 2022 GROUP BY 1)
  SELECT month, 100 * (q / normal - 1) AS pct FROM m JOIN c ON c.mo = month(m.month) WHERE days >= 20 ORDER BY month`);
```

<div class="grid grid-cols-2">

```js
Plot.plot({title: "River index (3 basins), m³/s: forecast vs 2010–2022 normal", width: width < 640 ? width : width / 2 - 8, height: 280, y: {grid: true, type: "log"}, color: {legend: true, domain: ["forecast (ensemble mean)", "normal"], range: ["var(--nea-river)", "var(--theme-foreground-muted)"]},
  marks: [Plot.areaY(rf, {x: "date", y1: "p25", y2: "p75", fill: "var(--nea-river)", fillOpacity: 0.25}),
    Plot.lineY(rf, {x: "date", y: "normal", stroke: () => "normal", strokeDasharray: "4"}), Plot.lineY(rf, {x: "date", y: "mean", stroke: () => "forecast (ensemble mean)", tip: true})]})
```

```js
Plot.plot({title: "Monthly flow vs normal (%)", width: width < 640 ? width : width / 2 - 8, height: 280, y: {grid: true, label: "%"},
  x: {label: null, domain: anom.map((d) => d.month.toLocaleString("en", {month: "short", year: "2-digit", timeZone: "UTC"}))},
  marks: [Plot.barY(anom, {x: (d) => d.month.toLocaleString("en", {month: "short", year: "2-digit", timeZone: "UTC"}), y: "pct", fill: (d) => d.pct < 0 ? "var(--nea-import)" : "var(--nea-demand)", tip: true}), Plot.ruleY([0])]})
```

</div>

A drier late winter means less run-of-river output from January, which adds to the flood losses.

## Flood losses used in the forecast

```js
const out = await q(`SELECT plant, capacity_mw, replace(status, '_', ' ') AS status, expected_return, winter_energy_gwh, note, source_url FROM plant_outage ORDER BY capacity_mw DESC`);
display(Inputs.table(out, {rows: 12, select: false,
  header: {plant: "Plant", capacity_mw: "MW", status: "Status", expected_return: "Back (expected)", winter_energy_gwh: "Storage lost (GWh)", note: "Note", source_url: "Sources"},
  format: {expected_return: (d) => d ?? "not known", winter_energy_gwh: (x) => x ?? "", source_url: (s) => htl.html`${s.split(" ").map((u, i) => htl.html`<a href=${u} target=_blank>[${i + 1}]</a> `)}`},
  width: {plant: 220, note: 300}}))
```

- **Lost generation per month** = MW × 0.35 (the dry-season output of run-of-river plants) × hours, plus Kulekhani's reduced storage (about 22 GWh, spread over Jan–Apr).
- **The range:** the top of the range assumes the ~230 MW cut off by destroyed lines stays out all winter; the bottom assumes it reconnects.
- **Updates:** when NEA restores plants, the register is updated and the forecast re-run.

## Daily forecasts (1–30 days)

```js
const daily = fc.filter((d) => !d.target.endsWith("_gwh"));
display(daily.length ? Inputs.table(daily) : htl.html`<p><i>Not yet available.</i> Daily forecasts need 8 consecutive days of data from the NEA homepage widget, which collection started on 2026-10-25. They will appear here automatically after the next export.</p>`)
```
