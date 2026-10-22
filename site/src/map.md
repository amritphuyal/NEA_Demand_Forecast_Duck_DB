---
toc: false
---


```js
import {q} from "./components/db.js";
import {freshness} from "./components/common.js";
import * as L from "npm:leaflet";
```

# Map: where the data comes from

```js
display(await freshness())
```

Every point that feeds the forecast:
- **weather points** (ERA5 temperature and rain)
- **river points** (GloFAS flow: three big basin outlets that make up the river index, plus five hydropower sites)
- **plants damaged by the 26 Aug 2026 flood** (sized by MW)

Click a point for its latest values; pick one below for its history.

```js
const pts = await q(`
  WITH w AS (SELECT point, arg_max(date, date) AS d, arg_max(tmax_c, date) AS tmax, arg_max(tmin_c, date) AS tmin FROM weather_daily GROUP BY 1),
       r AS (SELECT point, arg_max(date, date) AS d, arg_max(discharge_m3s, date) AS q FROM river_discharge_daily GROUP BY 1),
       clim AS (SELECT point, month(date) AS m, avg(discharge_m3s) AS q FROM river_discharge_daily WHERE year(date) BETWEEN 2010 AND 2022 GROUP BY 1, 2),
       f AS (SELECT f.point, avg(f.discharge_m3s / c.q - 1) AS anom FROM river_discharge_forecast f JOIN clim c ON c.point = f.point AND c.m = month(f.date)
             WHERE f.issued = (SELECT max(issued) FROM river_discharge_forecast) AND month(f.date) IN (1, 2, 3, 4) GROUP BY 1)
  SELECT p.*, w.d AS w_date, w.tmax, w.tmin, r.d AS r_date, r.q, f.anom
  FROM points p LEFT JOIN w ON w.point = p.id LEFT JOIN r ON r.point = p.id LEFT JOIN f ON f.point = p.id`);
const STYLE = {
  weather: {color: "#2ca02c", label: "Weather point"},
  river_basin: {color: "#1f4e9c", label: "River basin outlet (river index)"},
  river_plant: {color: "#5aa9e6", label: "River at hydropower site"},
  outage: {color: "#d62728", label: "Flood-damaged plant (approx. location)"}
};
const fmt = (x, d = 0) => x == null ? "–" : x.toLocaleString("en", {maximumFractionDigits: d});
```

```js
const div = display(document.createElement("div"));
div.style = "height: 600px; border-radius: 8px;";
const map = L.map(div, {scrollWheelZoom: false}).fitBounds([[26.35, 80.05], [30.45, 88.2]]);  // Nepal
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 13, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);
for (const p of pts) {
  const s = STYLE[p.kind];
  const mw = p.kind === "outage" ? parseFloat(p.detail) || 0 : 0;
  const body = p.kind === "weather" ? `Max ${fmt(p.tmax, 1)} °C, min ${fmt(p.tmin, 1)} °C on ${p.w_date?.toISOString().slice(0, 10)}`
    : p.kind.startsWith("river") ? `Flow ${fmt(p.q)} m³/s on ${p.r_date?.toISOString().slice(0, 10)}<br>Jan–Apr forecast vs normal: <b>${p.anom == null ? "–" : (p.anom > 0 ? "+" : "") + (100 * p.anom).toFixed(0) + "%"}</b>`
    : `${p.detail}<br><i>location approximate</i>`;
  L.circleMarker([p.lat, p.lon], {radius: p.kind === "outage" ? 5 + Math.sqrt(mw) : p.kind === "river_basin" ? 9 : 6,
    color: s.color, fillColor: s.color, fillOpacity: 0.65, weight: 1})
    .bindPopup(`<b>${p.id}</b><br><span style="color:${s.color}">${s.label}</span><br>${body}`).addTo(map);
}
const legend = L.control({position: "bottomright"});
legend.onAdd = () => Object.assign(document.createElement("div"), {
  className: "legend",
  innerHTML: Object.values(STYLE).map((s) => `<div><span style="background:${s.color}"></span>${s.label}</div>`).join("")
});
legend.addTo(map);
```

## A point's history

```js
const choice = view(Inputs.select(pts.filter((p) => p.kind !== "outage"), {label: "Point", format: (p) => `${p.id} (${STYLE[p.kind].label})`}));
```

```js
const series = choice.kind === "weather"
  ? await q(`SELECT date, tmax_c, tmin_c FROM weather_daily WHERE point = '${choice.id}' AND date >= current_date - INTERVAL 3 YEAR ORDER BY date`)
  : await q(`SELECT date, discharge_m3s AS q, NULL AS p25, NULL AS p75, 'observed' AS kind FROM river_discharge_daily WHERE point = '${choice.id}' AND date >= current_date - INTERVAL 3 YEAR
             UNION ALL SELECT date, discharge_m3s, p25, p75, 'forecast' FROM river_discharge_forecast WHERE point = '${choice.id}' AND issued = (SELECT max(issued) FROM river_discharge_forecast)
             ORDER BY date`);
```

```js
choice.kind === "weather"
  ? Plot.plot({title: `${choice.id}: daily temperature (°C), last 3 years`, width, height: 300, y: {grid: true, label: "°C"},
      marks: [Plot.lineY(series, {x: "date", y: "tmax_c", stroke: "#d62728", strokeWidth: 0.8}), Plot.lineY(series, {x: "date", y: "tmin_c", stroke: "#1f77b4", strokeWidth: 0.8})]})
  : Plot.plot({title: `${choice.id}: river flow (m³/s): observed + GloFAS forecast (band = ensemble p25–p75)`, width, height: 320, y: {grid: true, label: "m³/s", type: "log"},
      color: {legend: true}, marks: [
        Plot.areaY(series.filter((d) => d.kind === "forecast"), {x: "date", y1: "p25", y2: "p75", fill: "orange", fillOpacity: 0.25}),
        Plot.lineY(series, {x: "date", y: "q", stroke: "kind", strokeWidth: 1, tip: true})]})
```

## Flood-damaged plants (register)

```js
Inputs.table(await q(`SELECT plant, river, capacity_mw, status, kind, outage_start, expected_return, winter_energy_gwh, note FROM plant_outage ORDER BY capacity_mw DESC`), {rows: 12})
```

Sources and how they are used: see [Forecast](./forecast) and [Method](./method).

<style>
.legend { background: var(--theme-background); padding: 6px 10px; border-radius: 6px; font-size: 12px; line-height: 1.6; }
.legend span { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
</style>
