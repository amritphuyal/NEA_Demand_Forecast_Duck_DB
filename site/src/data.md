---
toc: true
---

```js
import {q, manifest} from "./components/db.js";
import {DEMAND_MONTHLY, IMPORT_MONTHLY, freshness} from "./components/common.js";
```

# Data

```js
display(await freshness())
```

All data is collected by plain Python scrapers (no AI in the pipeline) into a DuckLake lakehouse (Parquet + DuckDB). The site reads a snapshot of it. Raw files are kept, so every number can be traced back to a PDF, JSON or spreadsheet.

## What's in the snapshot

```js
const m = await manifest;
display(Inputs.table(Object.entries(m.tables).map(([name, t]) => ({table: name, rows: t.rows, columns: t.columns.length, KB: Math.round(t.bytes / 1024), source: t.source})),
  {columns: ["table", "rows", "columns", "KB", "source"], width: {source: 420}}))
```

## Coverage: how far back each series goes

```js
const cov = await q(`
  SELECT 'NEA daily reports (NDOR)' AS series, min(date) AS first, max(date) AS last FROM nea_daily
  UNION ALL SELECT 'NEA homepage widget', min(first_seen)::DATE, max(first_seen)::DATE FROM nea_widget
  UNION ALL SELECT 'Weather (ERA5)', min(date), max(date) FROM weather_daily
  UNION ALL SELECT 'River flow (GloFAS)', min(date), max(date) FROM river_discharge_daily
  UNION ALL SELECT 'River-flow forecast', min(date), max(date) FROM river_discharge_forecast
  UNION ALL SELECT 'NEA monthly balance (reports)', min(month), max(month) FROM (${DEMAND_MONTHLY})
  UNION ALL SELECT 'India customs trade', min(month), max(month) FROM india_trade_monthly
  UNION ALL SELECT 'India power exchange (CERC)', min(month), max(month) FROM iex_cross_border_monthly
  UNION ALL SELECT 'Annual history (reports)', make_date(min(year), 1, 1), make_date(max(year), 12, 31) FROM annual_history`);
```

```js
Plot.plot({width, height: 300, marginLeft: 220, x: {grid: true, label: null}, y: {label: null},
  marks: [Plot.barX(cov, {y: "series", x1: "first", x2: "last", fill: "var(--nea-demand)", tip: true}), Plot.dot(cov, {y: "series", x: "last", fill: "var(--nea-demand)"}), Plot.ruleX([new Date()], {stroke: "var(--nea-import)", strokeDasharray: "4"})]})
```

The NEA daily reports stop in January 2025; NEA stopped publishing them. Daily figures resume from the NEA homepage widget (2026-10-25 →). Monthly and annual series fill the gap.

## Daily energy balance (NEA daily reports, 2023–2025)

```js
const daily = await q(`SELECT date, requirement_mwh / 1000 AS demand, (nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh) / 1000 AS generation,
  net_exchange_india_mwh / 1000 AS net_import FROM nea_daily WHERE qa_ok ORDER BY date`);
const long = daily.flatMap((d) => ["demand", "generation", "net_import"].map((k) => ({date: d.date, series: k, gwh: d[k]})));
```

```js
Plot.plot({title: "GWh per day: demand, domestic generation, net import from India (negative = export)", width, height: 340,
  y: {grid: true, label: "GWh / day"}, color: {legend: true}, marks: [Plot.ruleY([0]), Plot.lineY(long, {x: "date", y: "gwh", stroke: "series", strokeWidth: 1, tip: true})]})
```

## Monthly import: four independent sources

```js
const imp = await q(`
  WITH nd AS (SELECT date_trunc('month', date)::DATE AS month, sum(import_mwh) / 1000 AS gwh FROM nea_daily WHERE qa_ok GROUP BY 1 HAVING count(*) >= 25),
       rp AS (SELECT date_trunc('month', c.date)::DATE AS month, r.import AS gwh FROM report_monthly_balance r
              JOIN dim_calendar c ON c.fiscal_year = r.fy AND c.bs_month = r.bs_month AND c.bs_day = 1 WHERE r.unit = 'GWh' AND r.import IS NOT NULL),
       cu AS (SELECT month, month_value / 1000 AS gwh FROM india_trade_monthly WHERE direction = 'nepal_import' AND measure = 'mwh'),
       ix AS (SELECT month, sum(purchase_mu) AS gwh FROM iex_cross_border_monthly GROUP BY 1)
  SELECT month, 'NEA daily reports' AS source, gwh FROM nd UNION ALL SELECT month, 'NEA annual reports', gwh FROM rp
  UNION ALL SELECT month, 'India customs', gwh FROM cu WHERE month >= '2019-01-01' UNION ALL SELECT month, 'India power exchange (part of import)', gwh FROM ix
  ORDER BY month`);
```

```js
Plot.plot({width, height: 340, y: {grid: true, label: "GWh / month"}, color: {legend: true},
  marks: [Plot.lineY(imp, {x: "month", y: "gwh", stroke: "source", marker: "dot", strokeWidth: 1.2, tip: true})]})
```

The sources agree on the shape. Customs vs NEA daily reports: correlation 0.99, ratio 0.92. That's why customs (the longest and most current series) carries the monthly import model. NEA's annual reports use Nepali (Bikram Sambat) months, which start mid-way through an AD month, so their line is shifted about half a month.

## Annual history (NEA annual reports)

```js
const ann = await q(`SELECT year, total_gwh, national_peak_mw, import_gwh, 100 * import_gwh / total_gwh AS import_share FROM annual_history ORDER BY year`);
```

<div class="grid grid-cols-2">

```js
Plot.plot({title: "Annual energy (GWh)", width: width < 640 ? width : width / 2 - 8, height: 260, y: {grid: true}, x: {tickFormat: (y) => y % 2 ? "" : y, label: null},
  marks: [Plot.barY(ann, {x: "year", y: "total_gwh", fill: "var(--nea-demand)", tip: true})]})
```

```js
Plot.plot({title: "Import from India, % of annual energy", width: width < 640 ? width : width / 2 - 8, height: 260, y: {grid: true}, x: {tickFormat: (y) => y % 2 ? "" : y, label: null},
  marks: [Plot.barY(ann, {x: "year", y: "import_share", fill: "var(--nea-import)", tip: true})]})
```

</div>
