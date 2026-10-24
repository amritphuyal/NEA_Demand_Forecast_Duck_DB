"""Phase 2 EDA: one function per question -> dict of numbers (every stat with its n) + a PNG.
Read-only on the lake. `nea eda` runs them all and writes data/eda/summary.json."""
import json
import time
from datetime import timedelta
from statistics import correlation
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # files only, no display
import matplotlib.pyplot as plt  # noqa: E402

DAILY = "gold.daily_features WHERE qa_ok"  # all-zero NDOR days are qa_ok = false


def _save(fig, out: Path | None, name: str) -> str | None:
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        fig.savefig(out / f"{name}.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return str(out / f"{name}.png") if out is not None else None


def _rows(con, sql: str, params=()) -> list[dict]:
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _r(x, k=2):
    return None if x is None else round(x, k)


def seasonality(con, out: Path | None) -> dict:
    """Weekday / BS-month profile, holiday dip (holiday vs non-holiday days of the same BS month), winter vs summer."""
    dow = dict(con.execute(f"SELECT dow, round(avg(requirement_mwh)) FROM {DAILY} GROUP BY 1 ORDER BY 1").fetchall())
    month = dict(con.execute(f"SELECT bs_month, round(avg(requirement_mwh)) FROM {DAILY} GROUP BY 1 ORDER BY 1").fetchall())
    dip, n_months = con.execute(f"""
        SELECT avg(h / nh - 1) * 100, count(*) FROM (
            SELECT avg(requirement_mwh) FILTER (is_holiday) h, avg(requirement_mwh) FILTER (NOT is_holiday) nh
            FROM {DAILY} GROUP BY bs_year, bs_month) WHERE h IS NOT NULL AND nh IS NOT NULL""").fetchone()
    seasons = {r.pop("season"): r for r in _rows(con, f"""
        SELECT season, round(avg(requirement_mwh)) requirement_mwh, round(avg(peak_demand_mw)) peak_demand_mw,
               round(avg(net_exchange_india_mwh)) net_exchange_india_mwh, count(*) n FROM {DAILY} GROUP BY 1""")}
    n = con.execute(f"SELECT count(*) FROM {DAILY}").fetchone()[0]

    s = _rows(con, f"SELECT date, requirement_mwh, net_exchange_india_mwh, season FROM {DAILY} ORDER BY date")
    fig, (a, b) = plt.subplots(2, 1, figsize=(11, 7))
    d = [x["date"] for x in s]
    a.plot(d, [x["requirement_mwh"] for x in s], lw=0.8, label="requirement MWh")
    a.plot(d, [x["net_exchange_india_mwh"] for x in s], lw=0.8, label="net import from India MWh")
    a.fill_between(d, 0, 1, where=[x["season"] == "winter" for x in s], transform=a.get_xaxis_transform(),
                   alpha=0.12, color="steelblue", label="winter (Nov-Apr)")
    a.set_title("Daily demand and India import")
    a.legend(fontsize=8)
    b.bar([str(k) for k in month], list(month.values()))
    b.set_title("Mean daily requirement (MWh) by BS month (1 = Baishakh)")
    fig.tight_layout()
    return {"n": n, "dow": dow, "bs_month": month, "holiday_dip_pct": _r(dip, 1), "holiday_months": n_months,
            "winter_vs_summer": seasons, "chart": _save(fig, out, "seasonality")}


def temperature(con, out: Path | None) -> dict:
    """Heating (winter, Kathmandu night low) and cooling (summer, Terai mean) effect on daily requirement.
    Working days only so weekends/holidays don't blur it. Simplification: no detrending; demand growth over the
    2 years is small next to the seasonal swing within one winter."""
    res, sql = {}, f"FROM {DAILY} AND NOT is_saturday AND NOT is_holiday AND season = ?"
    for season, col, key in (("winter", "tmin_ktm", "ktm"), ("summer", "tmean_terai", "terai")):
        c, sl, n = con.execute(f"SELECT corr(requirement_mwh, {col}), regr_slope(requirement_mwh, {col}), "
                               f"count({col}) {sql}", [season]).fetchone()
        res[season] = {f"corr_{key}": _r(c), f"slope_{key}": _r(sl, 0), "n": n, "low_n": n < 30,
                       "unit": f"MWh per degC of {col}"}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, (season, col) in zip(axes, (("winter", "tmin_ktm"), ("summer", "tmean_terai"))):
        pts = con.execute(f"SELECT {col}, requirement_mwh {sql} AND {col} IS NOT NULL", [season]).fetchall()
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=6)
        ax.set(title=f"{season}: requirement vs {col}", xlabel="degC", ylabel="MWh/day")
    fig.tight_layout()
    res["chart"] = _save(fig, out, "temperature")
    return res


def _lag_curve(con, y: str, x: str, max_lag: int) -> list[tuple]:
    """corr(y(t), x(t-k)) for k = 0..max_lag, matched by date: NDOR gaps don't shift the lag.
    In Python: the same self-join in SQL trips a DuckDB 2.0 internal error (dictionary cache)."""
    ys = dict(con.execute(f"SELECT date, {y} FROM {DAILY} AND {y} IS NOT NULL").fetchall())
    xs = dict(con.execute(f"SELECT date, {x} FROM gold.daily_features WHERE {x} IS NOT NULL").fetchall())
    out = []
    for k in range(max_lag + 1):
        pairs = [(v, xs[d - timedelta(k)]) for d, v in ys.items() if d - timedelta(k) in xs]
        c = correlation(*zip(*pairs)) if len(pairs) > 2 else None
        out.append((k, c, len(pairs)))
    return out


def discharge_lag(con, out: Path | None, max_lag: int = 30) -> dict:
    """How many days after river flow moves does domestic generation (up) and India import (down) follow?"""
    gen = "nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh"
    cg = _lag_curve(con, gen, "discharge_index", max_lag)
    ci = _lag_curve(con, "net_exchange_india_mwh", "discharge_index", max_lag)
    best = lambda c, f: dict(zip(("best_lag", "corr", "n"), f(c, key=lambda t: t[1] or 0, default=(None, None, 0))))  # noqa: E731
    res = {"gen": best(cg, max), "import": best(ci, min),
           "basins_gen": {q: best(_lag_curve(con, gen, q, max_lag), max)["best_lag"]
                          for q in ("q_narayani", "q_koshi", "q_karnali")},
           "curve": {k: (_r(a), _r(b)) for (k, a, _), (_, b, _) in zip(cg, ci)}}
    for k in ("gen", "import"):
        res[k]["corr"] = _r(res[k]["corr"])
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot([c[0] for c in cg], [c[1] for c in cg], label="domestic generation")
    ax.plot([c[0] for c in ci], [c[1] for c in ci], label="net import from India")
    ax.axhline(0, color="grey", lw=0.5)
    ax.set(title="Correlation with discharge_index k days earlier", xlabel="lag k (days)", ylabel="corr")
    ax.legend()
    res["chart"] = _save(fig, out, "discharge_lag")
    return res


def growth(con, out: Path | None) -> dict:
    """Annual trend: energy and peak CAGR, GDP elasticity of energy (log-log slope), import share per year.
    One series (the reports' multi-year chart) so years stay comparable."""
    a = _rows(con, "SELECT year, total_gwh, national_peak_mw, import_gwh, gdp_usd_2015 FROM gold.annual_history "
                   "WHERE total_gwh > 0 ORDER BY year")
    cagr = lambda k: (_r(((a[-1][k] / a[0][k]) ** (1 / (a[-1]["year"] - a[0]["year"])) - 1) * 100)  # noqa: E731
                      if len(a) > 1 and a[0][k] and a[-1][k] else None)
    el, r2, n_gdp = con.execute("SELECT regr_slope(ln(total_gwh), ln(gdp_usd_2015)), regr_r2(ln(total_gwh), "
                                "ln(gdp_usd_2015)), count(gdp_usd_2015) FROM gold.annual_history "
                                "WHERE total_gwh > 0 AND gdp_usd_2015 > 0").fetchone()
    share = {x["year"]: _r(100 * (x["import_gwh"] or 0) / x["total_gwh"], 1) for x in a}
    fig, (ax, bx) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    ys = [x["year"] for x in a]
    ax.plot(ys, [x["total_gwh"] for x in a], marker="o", label="energy GWh")
    ax2 = ax.twinx()
    ax2.plot(ys, [x["national_peak_mw"] for x in a], marker="s", color="tab:orange", label="national peak MW")
    ax.set_title("Annual energy (GWh, left) and national peak (MW, right)")
    bx.bar(ys, list(share.values()))
    bx.set_title("Import from India, % of annual energy")
    fig.tight_layout()
    return {"n": len(a), "years": [ys[0], ys[-1]] if ys else None, "low_n": len(a) < 12,
            "energy_cagr_pct": cagr("total_gwh"), "peak_cagr_pct": cagr("national_peak_mw"),
            "gdp_elasticity": _r(el), "gdp_r2": _r(r2), "n_gdp": n_gdp, "import_share_pct": share,
            "chart": _save(fig, out, "growth")}


SOURCES = ("ndor", "report", "customs", "iex")


def monthly_import(con) -> list[dict]:
    """Nepal import from India per AD month, GWh, one column per source (None = no data).
    report: NEA annual-report balance; a BS month goes to the AD month it starts in (consistent half-month shift)."""
    q = {
        "ndor": f"SELECT date_trunc('month', date)::DATE, sum(import_mwh) / 1000 FROM {DAILY} "
                "GROUP BY 1 HAVING count(import_mwh) >= 25",  # partial months would read low
        "report": "SELECT c.date, r.import FROM gold.report_monthly_balance r JOIN silver.dim_calendar c "
                  "ON c.fiscal_year = r.fy AND c.bs_month = r.bs_month AND c.bs_day = 1 "
                  "WHERE r.unit = 'GWh' AND r.import IS NOT NULL",
        "customs": "SELECT month, month_value / 1000 FROM silver.india_trade_monthly "
                   "WHERE direction = 'nepal_import' AND measure = 'mwh'",  # TKW = MWh
        "iex": "SELECT month, sum(purchase_mu) FROM silver.iex_cross_border_monthly GROUP BY 1",  # MU = GWh
    }
    data = {k: {d.replace(day=1): v for d, v in con.execute(sql).fetchall()} for k, sql in q.items()}
    months = sorted(set().union(*data.values()))
    return [{"month": m, **{k: data[k].get(m) for k in SOURCES}} for m in months]


def reconcile(con, out: Path | None) -> dict:
    """How far apart are the four import series? Reference = NEA's own monthly report figure."""
    rows = monthly_import(con)

    def cmp(a: str, b: str) -> dict:
        pr = [(r[a], r[b]) for r in rows if r[a] is not None and r[b] is not None]
        n = len(pr)
        sb = sum(y for _, y in pr)
        return {"n": n, "low_n": n < 12, "ratio": _r(sum(x for x, _ in pr) / sb) if sb else None,
                "corr": _r(correlation(*zip(*pr))) if n > 2 else None,
                # WAPE, not MAPE: monsoon months import ~0, so per-month % errors explode
                "wape_pct": _r(100 * sum(abs(x - y) for x, y in pr) / sb, 1) if sb else None}

    cov = {k: (lambda ms: [ms[0], ms[-1], len(ms)] if ms else None)([r["month"] for r in rows if r[k] is not None])
           for k in SOURCES}
    fig, ax = plt.subplots(figsize=(11, 4))
    for k in SOURCES:
        pts = [(r["month"], r[k]) for r in rows if r[k] is not None]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker=".", lw=1, label=k)
    ax.set(title="Monthly import from India by source (GWh)", ylabel="GWh")
    ax.legend()
    return {"coverage": cov, "vs_report": {k: cmp(k, "report") for k in ("ndor", "customs", "iex")},
            "customs_vs_ndor": cmp("customs", "ndor"), "chart": _save(fig, out, "import_sources")}


def gaps(con, out: Path | None) -> dict:
    """Coverage per series: first, last, n, expected; NDOR missing dates and the longest run of them."""
    have = [d for (d,) in con.execute("SELECT date FROM silver.nea_daily ORDER BY 1").fetchall()]
    missing, longest = [], 0
    for a, b in zip(have, have[1:]):
        gap = (b - a).days - 1
        missing += [a + timedelta(i + 1) for i in range(gap)]
        longest = max(longest, gap)
    res = {"nea_daily": {"first": have[0] if have else None, "last": have[-1] if have else None, "n": len(have),
                         "missing": len(missing), "longest_gap_days": longest, "missing_dates": missing}}
    span_rows = {"weather_daily": "SELECT min(date), max(date), count(DISTINCT date) FROM silver.weather_daily",
                 "river_discharge_daily": "SELECT min(date), max(date), count(DISTINCT date) FROM silver.river_discharge_daily",
                 "nea_widget": "SELECT min(first_seen)::DATE, max(first_seen)::DATE, count(*) FROM silver.nea_widget"}
    for k, sql in span_rows.items():
        f, l_, n = con.execute(sql).fetchone()
        res[k] = {"first": f, "last": l_, "n": n, "expected": (l_ - f).days + 1 if f else 0}
    for k, (f, l_, n) in ((k, v) for k, v in reconcile(con, None)["coverage"].items() if v):
        res[f"import_{k}_monthly"] = {"first": f, "last": l_, "n": n,
                                      "expected": (l_.year - f.year) * 12 + l_.month - f.month + 1}
    y = con.execute("SELECT min(year), max(year), count(*) FROM gold.annual_history").fetchone()
    res["annual_history"] = {"first": y[0], "last": y[1], "n": y[2], "expected": y[1] - y[0] + 1 if y[0] else 0}
    fig, ax = plt.subplots(figsize=(10, 4))
    bars = [(k, v["first"], v["last"]) for k, v in res.items() if k != "annual_history" and v["first"]]
    for i, (k, f, l_) in enumerate(bars):
        ax.hlines(i, f, l_, lw=8)
    ax.set_yticks(range(len(bars)), [b[0] for b in bars])
    ax.set_title("Data coverage by series")
    fig.tight_layout()
    res["chart"] = _save(fig, out, "coverage")
    return res


QUESTIONS = [seasonality, temperature, discharge_lag, growth, reconcile, gaps]


def run(con, out: Path = Path("docs/eda")) -> dict:  # committed: docs/eda-findings.md embeds the charts
    res, failed, t0 = {}, [], time.time()
    for q in QUESTIONS:
        name, t = q.__name__, time.time()
        print(f"▶ {name}: start", flush=True)
        try:
            res[name] = r = q(con, out)
        except Exception as e:  # one broken question must not hide the others
            print(f"✖ {name}: FAILED after {time.time() - t:.1f}s: {type(e).__name__}: {e}", flush=True)
            res[name], failed = {"error": f"{type(e).__name__}: {e}"}, failed + [name]
            continue
        print(f"✔ {name}: done in {time.time() - t:.1f}s -> {r.get('chart')}", flush=True)
        print(json.dumps(r, indent=1, default=str), flush=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"== eda done in {time.time() - t0:.0f}s -> {out / 'summary.json'}; failed: {failed or 'none'}", flush=True)
    return res
