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

// the three basin outlets that make up gold.daily_features.discharge_index
export const BASINS = `'koshi_chatara', 'narayani_devghat', 'karnali_chisapani'`;

// chart colours (CSS variables from theme.css, so they follow light/dark mode)
export const OCHRE = "#c28a12";
export const COLOR = {
  naive: "var(--theme-foreground-faint)", snaive: "var(--theme-foreground-fainter)", wma30: "var(--theme-foreground-muted)",
  ridge: "var(--nea-demand)", lgbm: OCHRE,
  combo: "var(--nea-demand)", ets: OCHRE, linear_m: "var(--theme-foreground-muted)", snaive_growth: "var(--theme-foreground-faint)",
  clim: "var(--nea-demand)", q_actual: "var(--nea-river)", actual: OCHRE
};
export const colors = (domain) => ({domain, range: domain.map((k) => COLOR[k])});

export const LATEST_LIVE = `(SELECT max(run_id) FROM forecasts WHERE run_id LIKE 'live-%')`;

export async function freshness() {
  const m = await manifest;
  const at = new Date(m.exported_at);
  return html`<p class="muted small">Snapshot of ${Object.keys(m.tables).length} tables, exported ${at.toLocaleString("en-GB", {day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"})}.
    Every chart is a SQL query on it; run your own in the <a href="./sql">SQL explorer</a>.</p>`;
}
