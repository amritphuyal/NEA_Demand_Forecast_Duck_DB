// One in-browser DuckDB over the Parquet snapshot exported from the lake (`nea export`).
// DuckDB-WASM comes from jsDelivr: its .wasm files (35-40 MB) exceed Cloudflare's 25 MiB per-file limit,
// so self-hosting (Framework's built-in DuckDBClient) can't deploy. Version pinned.
import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm";
import {FileAttachment} from "observablehq:stdlib";

// static FileAttachment calls: Framework copies (and fingerprints) exactly these files into the site
const FILES = {
  daily_features: FileAttachment("../data/daily_features.parquet"),
  monthly_summary: FileAttachment("../data/monthly_summary.parquet"),
  annual_history: FileAttachment("../data/annual_history.parquet"),
  report_monthly_balance: FileAttachment("../data/report_monthly_balance.parquet"),
  nea_daily: FileAttachment("../data/nea_daily.parquet"),
  nea_widget: FileAttachment("../data/nea_widget.parquet"),
  weather_daily: FileAttachment("../data/weather_daily.parquet"),
  river_discharge_daily: FileAttachment("../data/river_discharge_daily.parquet"),
  river_discharge_forecast: FileAttachment("../data/river_discharge_forecast.parquet"),
  plant_outage: FileAttachment("../data/plant_outage.parquet"),
  india_trade_monthly: FileAttachment("../data/india_trade_monthly.parquet"),
  iex_cross_border_monthly: FileAttachment("../data/iex_cross_border_monthly.parquet"),
  macro_yearly: FileAttachment("../data/macro_yearly.parquet"),
  report_monthly: FileAttachment("../data/report_monthly.parquet"),
  report_annual: FileAttachment("../data/report_annual.parquet"),
  dim_calendar: FileAttachment("../data/dim_calendar.parquet"),
  ingest_log: FileAttachment("../data/ingest_log.parquet"),
  backtest_metrics: FileAttachment("../data/backtest_metrics.parquet"),
  forecasts: FileAttachment("../data/forecasts.parquet"),
  points: FileAttachment("../data/points.parquet")
};
export const manifest = FileAttachment("../data/manifest.json").json();
export const TABLES = Object.keys(FILES);

let conn;
async function connect() {
  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  const url = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], {type: "text/javascript"}));
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(url));
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(url);
  const c = await db.connect();
  for (const [name, file] of Object.entries(FILES)) {
    await db.registerFileURL(`${name}.parquet`, new URL(file.href, location.href).href, duckdb.DuckDBDataProtocol.HTTP, false);
    await c.query(`CREATE VIEW ${name} AS SELECT * FROM '${name}.parquet'`);
  }
  return c;
}

// Plain JS rows: BIGINT -> Number, DATE/TIMESTAMP -> Date (so Plot and Inputs.table read them directly)
function toRows(table) {
  const dates = new Set(table.schema.fields.filter((f) => /^(Date|Timestamp)/.test(String(f.type))).map((f) => f.name));
  return table.toArray().map((r) => {
    const o = r.toJSON();
    for (const k in o) {
      if (typeof o[k] === "bigint") o[k] = Number(o[k]);
      else if (dates.has(k) && o[k] != null) o[k] = new Date(o[k]);
    }
    return o;
  });
}

/** Run SQL on the snapshot; resolves to an array of row objects. */
export async function q(sql) {
  conn ??= connect();
  return toRows(await (await conn).query(sql));
}
