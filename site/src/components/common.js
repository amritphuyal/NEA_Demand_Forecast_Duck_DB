// SQL snippets shared by several pages (all run in the browser on the Parquet snapshot).
import {html} from "npm:htl";
import {manifest} from "./db.js";

// NEA report months are Bikram Sambat months: map each to the AD month it starts in (bs_day = 1)
export const DEMAND_MONTHLY = `
  SELECT date_trunc('month', c.date)::DATE AS month, r.national_demand AS gwh
  FROM report_monthly_balance r JOIN dim_calendar c ON c.fiscal_year = r.fy AND c.bs_month = r.bs_month AND c.bs_day = 1
  WHERE r.unit = 'GWh' AND r.national_demand IS NOT NULL`;

// India customs import, scaled to the NEA level (customs reads ~9% above NEA, see Models)
export const IMPORT_MONTHLY = `
  SELECT month, month_value / 1000 / 1.09 AS gwh FROM india_trade_monthly
  WHERE direction = 'nepal_import' AND measure = 'mwh'`;

export const LATEST_LIVE = `(SELECT max(run_id) FROM forecasts WHERE run_id LIKE 'live-%')`;

export async function freshness() {
  const m = await manifest;
  return html`<p class="muted small">Data snapshot exported from the lake on <b>${m.exported_at.replace("T", " ")}</b>
    · ${Object.keys(m.tables).length} tables · every chart is a live SQL query on that snapshot (see <a href="./sql">SQL explorer</a>).</p>`;
}
