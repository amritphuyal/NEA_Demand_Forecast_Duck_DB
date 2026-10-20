"""Phase 2 EDA: one function per question -> dict of numbers (every stat with its n) + a PNG.
Read-only on the lake. `nea eda` runs them all and writes data/eda/summary.json."""
import json
import time
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
    Working days only so weekends/holidays don't blur it. ponytail: no detrending; demand growth over the
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


QUESTIONS = [seasonality, temperature]


def run(con, out: Path = Path("data/eda")) -> dict:
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
