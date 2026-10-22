---
toc: false
---

```js
import {q, manifest, TABLES} from "./components/db.js";
import {freshness} from "./components/common.js";
```

# SQL explorer

```js
display(await freshness())
```

Query the same data the charts use, with full DuckDB SQL. It runs entirely in your browser on a read-only snapshot, so nothing you type can change anything. Pick an example or write your own, then press **Run**.

```js
const EXAMPLES = new Map([
  ["Winter outlook: base vs flood-adjusted import", `SELECT model, target, date, round(yhat) AS yhat, round(p10) AS p10, round(p90) AS p90
FROM forecasts
WHERE run_id = (SELECT max(run_id) FROM forecasts WHERE run_id LIKE 'live-%')
ORDER BY target, model, date`],
  ["Average winter vs summer day", `SELECT season, round(avg(requirement_mwh)) AS demand_mwh,
       round(avg(net_exchange_india_mwh)) AS net_import_mwh, count(*) AS days
FROM daily_features WHERE qa_ok GROUP BY season`],
  ["Best model per target and horizon (winter MAE)", `SELECT target, horizon, arg_min(model, mae) AS best_model, round(min(mae)) AS mae
FROM backtest_metrics WHERE season = 'winter' AND weather = 'clim'
GROUP BY ALL ORDER BY ALL`],
  ["Monthly import from India customs (GWh)", `SELECT month, round(month_value / 1000) AS gwh
FROM india_trade_monthly
WHERE direction = 'nepal_import' AND measure = 'mwh'
ORDER BY month`],
  ["Flood-damaged plants", `SELECT plant, capacity_mw, status, note FROM plant_outage ORDER BY capacity_mw DESC`],
  ["River flow this month vs the same month in past years", `SELECT year(date) AS year, round(avg(discharge_index)) AS river_index
FROM daily_features
WHERE month(date) = month(current_date) AND discharge_index IS NOT NULL
GROUP BY 1 ORDER BY 1`],
  ["Coldest Kathmandu nights since 2010", `SELECT date, point, tmin_c FROM weather_daily
WHERE point = 'kathmandu' ORDER BY tmin_c LIMIT 10`]
]);
const example = view(Inputs.select(EXAMPLES, {label: "Example"}));
```

```js
const sql = view(Inputs.textarea({value: example, rows: 8, width: "100%", submit: "Run", spellcheck: false, monospace: true}));
```

```js
const result = await q(sql).then((rows) => ({rows})).catch((e) => ({error: e.message}));
```

```js
result.error
  ? display(htl.html`<div class="warning" style="white-space: pre-wrap"><b>Query error</b><br>${result.error}</div>`)
  : display(htl.html`<p class="small">${result.rows.length.toLocaleString()} row(s)</p>`), display(Inputs.table(result.rows ?? [], {rows: 15}))
```

```js
// quick chart: x = first date/number column, y = numeric columns
const cols = result.rows?.length ? Object.keys(result.rows[0]) : [];
const xcol = cols.find((c) => result.rows[0][c] instanceof Date) ?? cols.find((c) => typeof result.rows[0][c] === "number");
const ycols = cols.filter((c) => c !== xcol && typeof result.rows[0][c] === "number");
const strcols = cols.filter((c) => c !== xcol && typeof result.rows[0][c] === "string");
const series = strcols.length ? (d) => strcols.map((c) => d[c]).join(" · ") : undefined;  // one line per text-column combination
display(xcol && ycols.length && result.rows.length > 1
  ? Plot.plot({title: `Quick chart: ${ycols[0]} by ${xcol}${strcols.length ? ", per " + strcols.join(" · ") : ""}`, width, height: 280, y: {grid: true}, color: {legend: !!series},
      marks: [Plot.lineY(result.rows, {x: xcol, y: ycols[0], stroke: series, marker: result.rows.length < 60 ? "dot" : null, tip: true})]})
  : htl.html`<p class="small muted">(A quick chart appears when the result has a date or number column plus a numeric column.)</p>`)
```

## Tables

```js
const m = await manifest;
display(Inputs.table(TABLES.map((t) => ({table: t, rows: m.tables[t]?.rows, columns: m.tables[t]?.columns.join(", ")})), {rows: 25, width: {table: 190, columns: 700}}))
```

What each table means is in the repository's `docs/lake.md`. Tip: `DESCRIBE daily_features` shows column types, and `SUMMARIZE weather_daily` profiles a table.

<style>.small { font-size: 0.85rem; } .muted { color: var(--theme-foreground-muted); }</style>
