"""Phase 3 forecasting: features, models, rolling-origin backtest, selection, intervals, live forecast.
Approach and defence: docs/models/README.md. One function per job; results go to ml.* and docs/model/."""
import json
import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from nea_forecast.lake import upsert  # noqa: E402

TARGETS = ["requirement_mwh", "peak_demand_mw", "domestic_gen_mwh", "net_exchange_india_mwh", "import_need_mwh"]
PCT_TARGETS = {"requirement_mwh", "peak_demand_mw", "domestic_gen_mwh"}  # the others cross zero: MAE only
HORIZONS = [1, 7, 14, 30]
WINTER = {11, 12, 1, 2, 3, 4}
BT_START = date(2024, 5, 1)  # first backtest origin: ~1 year of training before it
CLIM_YEARS = (date(2010, 1, 1), date(2022, 12, 31))  # before any NDOR target: no leakage via climatology
WX = ("tmean_ktm", "tmean_terai", "tmin_ktm", "discharge_index")
OUT = Path("docs/model")


# ---------- data ----------

def load(con) -> dict:
    """Everything the models read, as plain dicts keyed by date (lags by date: gaps never shift)."""
    frame = {}
    for d, req, peak, gen, ex in con.execute(
            "SELECT date, requirement_mwh, peak_demand_mw, nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh, "
            "net_exchange_india_mwh FROM gold.daily_features WHERE qa_ok").fetchall():
        frame[d] = {"requirement_mwh": req, "peak_demand_mw": peak, "domestic_gen_mwh": gen,
                    "net_exchange_india_mwh": ex, "import_need_mwh": req - gen}
    # NEA homepage widget (same definitions as NDOR, verified 2026-10-26); figures are the previous day
    for d, req, peak, gen, ex in con.execute(
            "SELECT first_seen::DATE - 1, last(national_energy_demand_mwh ORDER BY first_seen), "
            "last(national_peak_mw ORDER BY first_seen), last(nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh "
            "ORDER BY first_seen), last(import_mwh - export_mwh ORDER BY first_seen) "
            "FROM silver.nea_widget GROUP BY 1").fetchall():
        frame.setdefault(d, {"requirement_mwh": req, "peak_demand_mw": peak, "domestic_gen_mwh": gen,
                             "net_exchange_india_mwh": ex, "import_need_mwh": req - gen})
    cal = {d: (dow, hol) for d, dow, hol in con.execute(
        "SELECT date, dow, is_holiday FROM silver.dim_calendar").fetchall()}
    wx = {d: dict(zip(WX, v)) for d, *v in con.execute(
        "SELECT date, (tmax_ktm + tmin_ktm) / 2, tmean_terai, tmin_ktm, discharge_index FROM gold.daily_features "
        "WHERE tmean_terai IS NOT NULL AND discharge_index IS NOT NULL").fetchall()}
    return {"frame": frame, "cal": cal, "wx": wx, "clim": climatology(wx), "hdd_base": 15.0, "cdd_base": 24.0}


def climatology(wx: dict) -> dict:
    """(column, day of year) -> 2010-2022 mean, 7-day centred smoothing."""
    sums = {}
    for d, row in wx.items():
        if CLIM_YEARS[0] <= d <= CLIM_YEARS[1]:
            for c in WX:
                if row[c] is not None:
                    for k in range(-3, 4):
                        key = (c, (_doy(d) + k - 1) % 366 + 1)
                        s = sums.setdefault(key, [0.0, 0])
                        s[0] += row[c]
                        s[1] += 1
    return {k: s / n for k, (s, n) in sums.items()}


def _doy(d: date) -> int:
    return d.timetuple().tm_yday


# ---------- features ----------

def features(c: dict, origin: date, h: int, target: str, weather: str = "clim") -> dict | None:
    """Features for forecasting target at origin + h, using data <= origin only (target-day weather from
    climatology unless weather='actual', the ex-post oracle). None if a needed lag is missing."""
    f, wx, clim, d = c["frame"], c["wx"], c["clim"], origin + timedelta(h)
    y = lambda day: f.get(day, {}).get(target)  # noqa: E731
    past7 = [y(origin - timedelta(i)) for i in range(7)]
    snaive = y(d - timedelta(7 * -(-h // 7)))
    obs = [wx.get(origin - timedelta(i)) for i in range(7)]
    if None in past7 or snaive is None or None in obs or d not in c["cal"]:
        return None
    w30 = [(30 - i, y(origin - timedelta(i))) for i in range(30)]
    w30 = [(w, v) for w, v in w30 if v is not None]
    if weather == "actual":
        if d not in wx:
            return None
        tgt = wx[d]
    else:
        tgt = {k: clim[(k, _doy(d))] for k in WX}
    anom = lambda k, row, day: row[k] - clim[(k, _doy(day))]  # noqa: E731
    dow, hol = c["cal"][d]
    return {"y_t": past7[0], "y_mean7": sum(past7) / 7, "y_snaive": snaive,
            "y_wma30": sum(w * v for w, v in w30) / sum(w for w, _ in w30),
            **{f"dow_{i}": float(dow == i) for i in range(1, 7)}, "holiday": float(bool(hol)),
            "hdd": max(0.0, c["hdd_base"] - tgt["tmean_ktm"]), "cdd": max(0.0, tgt["tmean_terai"] - c["cdd_base"]),
            "tmean_terai": tgt["tmean_terai"], "tmin_ktm": tgt["tmin_ktm"],
            "temp_anom_t": anom("tmean_terai", obs[0], origin),
            "temp_anom_7": sum(anom("tmean_terai", o, origin - timedelta(i)) for i, o in enumerate(obs)) / 7,
            "q_clim": tgt["discharge_index"], "q_anom_t": anom("discharge_index", obs[0], origin),
            "q_anom_7": sum(anom("discharge_index", o, origin - timedelta(i)) for i, o in enumerate(obs)) / 7,
            "trend": float((origin - date(2023, 1, 1)).days)}


# ---------- models: (train [(feat, y)], test [feat]) -> [yhat] ----------

def _baseline(key):
    return lambda train, test: [x[key] for x in test]


BASELINES = {"naive": _baseline("y_t"), "snaive": _baseline("y_snaive"), "wma30": _baseline("y_wma30")}


# ---------- backtest ----------

def _rows(c: dict, target: str, h: int, weather: str) -> list[tuple]:
    out = []
    for o in sorted(c["frame"]):
        x = features(c, o, h, target, weather)
        yv = c["frame"].get(o + timedelta(h), {}).get(target)
        if x is not None and yv is not None:
            out.append((o, x, yv))
    return out


def backtest(c: dict, models: dict, targets: list[str], horizons: list[int], weather: str,
             start: date = BT_START, refit_days: int = 7) -> tuple[list[dict], dict]:
    """Rolling origin: every origin >= start is forecast by a model trained only on targets dated <= the
    origin. Models refit every 7 origins, trained as of the first one (ponytail: daily refit = 7x the cost).
    Returns metric rows and errors {(model, target, h): [(origin, date, y, yhat)]}."""
    errors = {}
    for target in targets:
        for h in horizons:
            rows = _rows(c, target, h, weather)
            test = [r for r in rows if r[0] >= start]
            for name, fn in models.items():
                out = []
                for i in range(0, len(test), refit_days):
                    chunk = test[i:i + refit_days]  # trained once, at the chunk's first origin
                    train = [(x, yv) for o, x, yv in rows if o + timedelta(h) <= chunk[0][0]]
                    preds = fn(train, [x for _, x, _ in chunk])
                    out += [(o, o + timedelta(h), yv, p) for (o, _, yv), p in zip(chunk, preds)]
                errors[(name, target, h)] = out
    return metrics(errors, weather), errors


def metrics(errors: dict, weather: str) -> list[dict]:
    rows = []
    for (name, target, h), es in errors.items():
        for season in ("all", "winter"):
            sel = [e for e in es if season == "all" or e[1].month in WINTER]
            if not sel:
                continue
            mape = (100 * sum(abs(y - p) / abs(y) for _, _, y, p in sel if y) / len(sel)
                    if target in PCT_TARGETS else None)
            rows.append({"model": name, "target": target, "horizon": h, "season": season, "weather": weather,
                         "mae": sum(abs(y - p) for _, _, y, p in sel) / len(sel), "mape": mape, "n": len(sel)})
    return rows


def _save(fig, name: str) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return str(OUT / f"{name}.png")


def _table(rows: list[dict], season: str = "winter") -> str:
    """Printable winter MAE (MAPE%) table: one line per target/model, one column per horizon."""
    lines, keys = [], sorted({(r["target"], r["model"]) for r in rows if r["season"] == season})
    for t, m in keys:
        cells = []
        for h in HORIZONS:
            r = next((r for r in rows if (r["target"], r["model"], r["horizon"], r["season"]) == (t, m, h, season)), None)
            cells.append("" if r is None else f"{r['mae']:,.0f}" + (f" ({r['mape']:.1f}%)" if r["mape"] is not None else ""))
        lines.append(f"  {t:24} {m:8} " + " | ".join(f"{x:>16}" for x in cells))
    return "\n".join([f"  {'target':24} {'model':8} " + " | ".join(f"{'h=' + str(h):>16}" for h in HORIZONS)] + lines)


def chart_daily(rows: list[dict]) -> str:
    fig, axes = plt.subplots(1, len(TARGETS), figsize=(4 * len(TARGETS), 3.5), sharex=True)
    for ax, t in zip(axes, TARGETS):
        for m in sorted({r["model"] for r in rows}):
            pts = sorted((r["horizon"], r["mae"]) for r in rows
                         if r["target"] == t and r["model"] == m and r["season"] == "winter" and r["weather"] == "clim")
            if pts:
                ax.plot(*zip(*pts), marker="o", label=m)
        ax.set(title=t, xlabel="horizon (days)", ylabel="winter MAE")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, "backtest_daily")


def run_backtest(con) -> dict:
    run_id, now = f"bt-{datetime.now():%Y%m%d-%H%M%S}", datetime.now()
    t = time.time()
    print("▶ load: start", flush=True)
    c = load(con)
    print(f"✔ load: {len(c['frame'])} days, weather {len(c['wx'])} days in {time.time() - t:.1f}s", flush=True)
    models, all_rows = dict(BASELINES), []
    for weather in ("clim", "actual"):
        t = time.time()
        print(f"▶ backtest ({weather}): {len(models)} models x {len(TARGETS)} targets x {len(HORIZONS)} horizons", flush=True)
        rows, _ = backtest(c, models, TARGETS, HORIZONS, weather)
        all_rows += rows
        print(f"✔ backtest ({weather}) in {time.time() - t:.0f}s; winter MAE (MAPE):\n{_table(rows)}", flush=True)
    upsert(con, "ml.backtest_metrics", [{"run_id": run_id, "coverage": None, "pinball": None, "dm_p": None,
                                         "created_at": now, **r} for r in all_rows],
           ("run_id", "model", "target", "horizon", "season", "weather"))
    print(f"✔ saved {len(all_rows)} metric rows as {run_id}; chart {chart_daily(all_rows)}", flush=True)
    return {"run_id": run_id, "rows": all_rows}
