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
    tgt = {k: clim[(k, _doy(d))] for k in WX}
    if weather == "actual":  # ex-post oracle: all target-day weather known
        if d not in wx:
            return None
        tgt = wx[d]
    elif weather == "q_actual":  # river flow known (backtest: actual = perfect forecast; live: GloFAS forecast)
        if d not in wx:
            return None
        tgt = {**tgt, "discharge_index": wx[d]["discharge_index"]}
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
RIDGE_FEATS = ["y_t", "y_mean7", "y_snaive", *[f"dow_{i}" for i in range(1, 7)], "holiday", "hdd", "cdd",
               "tmean_terai", "temp_anom_t", "temp_anom_7", "q_clim", "q_anom_t", "q_anom_7", "trend"]
LAMBDAS = (0.1, 1.0, 10.0, 100.0)


def fit_ridge(X: np.ndarray, y: np.ndarray, lam: float) -> tuple:
    """Closed-form ridge on standardised X: lstsq on [X; sqrt(lam) I] -> [y; 0]."""
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    A = np.vstack([(X - mu) / sd, math.sqrt(lam) * np.eye(X.shape[1])])
    b = np.concatenate([y - y.mean(), np.zeros(X.shape[1])])
    return mu, sd, np.linalg.lstsq(A, b, rcond=None)[0], y.mean()


def predict_ridge(fit: tuple, X: np.ndarray) -> np.ndarray:
    mu, sd, coef, y0 = fit
    return (X - mu) / sd @ coef + y0


def _xy(rows, feats):
    return np.array([[x[k] for k in feats] for x, _ in rows]), np.array([yv - x["y_t"] for x, yv in rows])


def ridge(train: list, test: list, feats: list[str] = RIDGE_FEATS) -> list[float]:
    """Target = change from today (y_{t+h} - y_t): shrinkage pulls toward the naive forecast, the strong
    baseline, not toward zero. Lambda picked on the last 60 training rows (time order), then refit on all."""
    X, y = _xy(train, feats)
    lam = 1.0
    if len(train) >= 180:
        v = 60
        lam = min(LAMBDAS, key=lambda L: np.abs(predict_ridge(fit_ridge(X[:-v], y[:-v], L), X[-v:]) - y[-v:]).mean())
    Xt = np.array([[x[k] for k in feats] for x in test])
    return list(predict_ridge(fit_ridge(X, y, lam), Xt) + Xt[:, feats.index("y_t")])


def dm_test(e1: list[float], e2: list[float], h: int) -> float:
    """Diebold-Mariano, absolute-error loss, Newey-West variance with h-1 lags; two-sided normal p-value."""
    d = np.abs(np.array(e1)) - np.abs(np.array(e2))
    n = len(d)
    if n < 3 or not d.any():
        return 1.0
    dc = d - d.mean()
    var = (dc @ dc + 2 * sum((1 - k / h) * (dc[k:] @ dc[:-k]) for k in range(1, h))) / n / n
    if var <= 0:
        var = (dc @ dc) / n / n
    if var == 0:  # constant non-zero loss difference: one model is always better
        return 0.0
    return math.erfc(abs(d.mean() / math.sqrt(var)) / math.sqrt(2))


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
                         "mae": sum(abs(y - p) for _, _, y, p in sel) / len(sel), "mape": mape, "n": len(sel),
                         "dm_p": None})
    return rows


LADDER = ["ridge", "lgbm"]  # complexity order above the baselines; each is tested against the one below
MARGIN, ALPHA = 0.05, 0.10  # a more complex model must be >5% better on winter MAE and DM p < 0.10


def select_one(mae: dict[str, float], p) -> str:
    """Climb the ladder from the best baseline; move up only on a >5% AND significant improvement."""
    best = min((m for m in BASELINES if m in mae), key=mae.get)
    for m in LADDER:
        if m in mae and mae[m] < (1 - MARGIN) * mae[best] and p(m, best) < ALPHA:
            best = m
    # then the simplest model within 5% of that one (blueprint rule): equal skill -> less complexity
    order = [*BASELINES, *LADDER]
    return next(m for m in order[:order.index(best) + 1] if m in mae and mae[m] <= (1 + MARGIN) * mae[best])


def select(rows: list[dict], errors: dict) -> dict[str, str]:
    """{'target|h': model} from winter MAE + DM test on winter errors (ex-ante run only)."""
    out = {}
    for t, h in sorted({(r["target"], r["horizon"]) for r in rows}):
        mae = {r["model"]: r["mae"] for r in rows if (r["target"], r["horizon"], r["season"]) == (t, h, "winter")}

        def p(a, b):
            ea, eb = ({e[0]: e[2] - e[3] for e in errors[(k, t, h)] if e[1].month in WINTER} for k in (a, b))
            common = sorted(ea.keys() & eb.keys())
            return dm_test([ea[o] for o in common], [eb[o] for o in common], h)
        out[f"{t}|{h}"] = select_one(mae, p)
    return out


def attach_dm(rows: list[dict], errors: dict) -> None:
    """dm_p on each ladder model's rows: Diebold-Mariano vs the next simpler model (the best baseline by
    winter MAE for the first rung), paired by origin, per season."""
    by = {(r["model"], r["target"], r["horizon"], r["season"]): r for r in rows}
    for t, h in {(r["target"], r["horizon"]) for r in rows}:
        prev = min((m for m in BASELINES if (m, t, h, "winter") in by), key=lambda m: by[(m, t, h, "winter")]["mae"])
        for m in LADDER:
            if (m, t, h) not in errors:
                continue
            for season in ("all", "winter"):
                err = lambda k: {e[0]: e[2] - e[3] for e in errors[(k, t, h)]  # noqa: E731
                                 if season == "all" or e[1].month in WINTER}
                a, b = err(prev), err(m)
                common = sorted(a.keys() & b.keys())
                if (m, t, h, season) in by:
                    by[(m, t, h, season)]["dm_p"] = dm_test([b[o] for o in common], [a[o] for o in common], h)
                    by[(m, t, h, season)]["dm_vs"] = prev
            prev = m


def lgbm(train: list, test: list) -> list[float]:
    """Gradient-boosted trees on the change from today (trees can't extrapolate a growing level).
    Settings fixed for small data before testing (docs/models/lightgbm.md)."""
    import lightgbm as lgb  # native API: the sklearn wrapper would pull in scikit-learn
    feats = RIDGE_FEATS + ["tmin_ktm"]
    X, y = _xy(train, feats)
    params = {"objective": "regression", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 10,
              "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "seed": 0, "verbose": -1,
              "num_threads": 1}  # tiny data: threads cost more than they save
    m = lgb.train(params, lgb.Dataset(X, y), num_boost_round=300)
    Xt = np.array([[x[k] for k in feats] for x in test])
    return list(m.predict(Xt) + Xt[:, 0])  # feats[0] = y_t


MODELS = {"ridge": ridge, "lgbm": lgbm}


def import_need_compare(errors: dict, chosen: dict, horizons: list[int] = HORIZONS) -> tuple[list[dict], dict]:
    """Import need (requirement - domestic generation) two ways: 'direct' = selected model on the need itself,
    'diff' = selected demand forecast - selected generation forecast. diff wins ties (it says why import moves)."""
    rows, pick = [], {}
    for h in horizons:
        sel = lambda t: errors[(chosen[f"{t}|{h}"], t, h)]  # noqa: E731
        r, g = ({e[0]: e for e in sel(t)} for t in ("requirement_mwh", "domestic_gen_mwh"))
        diff = [(o, r[o][1], r[o][2] - g[o][2], r[o][3] - g[o][3]) for o in sorted(r.keys() & g.keys())]
        errs = {("direct", "import_need_mwh", h): sel("import_need_mwh"), ("diff", "import_need_mwh", h): diff}
        rs = metrics(errs, "clim")
        w = {x["model"]: x for x in rs if x["season"] == "winter"}
        ea, eb = ({e[0]: e[2] - e[3] for e in errs[(k, "import_need_mwh", h)] if e[1].month in WINTER}
                  for k in ("direct", "diff"))
        common = sorted(ea.keys() & eb.keys())
        p = dm_test([ea[o] for o in common], [eb[o] for o in common], h)
        for x in rs:
            x["dm_p"], x["dm_vs"] = (p, "diff") if x["model"] == "direct" else (None, None)
        better = w["direct"]["mae"] < (1 - MARGIN) * w["diff"]["mae"] and p < ALPHA
        pick[h] = "direct" if better else "diff"
        rows += rs
    return rows, pick


def sensitivity(c: dict) -> str:
    """Ridge winter MAPE for demand under HDD/CDD thresholds +-3 degC: the fixed choice must not be tuned."""
    lines = ["  hdd_base cdd_base | " + " | ".join(f"req h={h}" for h in HORIZONS)]
    for hb, cb in ((12, 24), (15, 24), (18, 24), (15, 21), (15, 27)):
        rows, _ = backtest({**c, "hdd_base": hb, "cdd_base": cb}, {"ridge": ridge}, ["requirement_mwh"], HORIZONS, "clim")
        w = {r["horizon"]: r["mape"] for r in rows if r["season"] == "winter"}
        lines.append(f"  {hb:8} {cb:8} | " + " | ".join(f"{w[h]:8.2f}%" for h in HORIZONS))
    return "\n".join(lines)


def stability(c: dict) -> str:
    """Standardised ridge coefficients (h=1 demand) fitted on 2023 vs 2024 origins: same sign = stable."""
    rows = _rows(c, "requirement_mwh", 1, "clim")
    fits = {yr: fit_ridge(*_xy([(x, yv) for o, x, yv in rows if o.year == yr], RIDGE_FEATS), 1.0)[2]
            for yr in (2023, 2024)}
    lines = [f"  {'feature':12} {'2023':>8} {'2024':>8}  same sign"]
    for i, k in enumerate(RIDGE_FEATS):
        a, b = fits[2023][i], fits[2024][i]
        lines.append(f"  {k:12} {a:8.0f} {b:8.0f}  {'yes' if a * b > 0 or abs(a) + abs(b) < 50 else 'NO'}")
    return "\n".join(lines)


WINDOW, MIN_RES = 60, 30  # interval = quantiles of the last 60 known out-of-sample errors (need >= 30)


def interval(residuals: list[float]) -> tuple[float, float]:
    """Empirical 10% / 90% quantiles of residuals y - yhat: added to yhat they give P10 / P90."""
    return tuple(float(x) for x in np.quantile(residuals, [0.1, 0.9]))


def _bounds(es: list[tuple]) -> list[tuple]:
    """Per forecast: (origin, date, y, yhat, p10, p90) using only errors whose target date <= its origin
    (known at forecast time), last WINDOW of them. Forecasts without MIN_RES known errors get no interval."""
    known = sorted(es, key=lambda e: e[1])
    out = []
    for o, d, y, p in es:
        past = [e[2] - e[3] for e in known if e[1] <= o][-WINDOW:]
        if len(past) >= MIN_RES:
            lo, hi = interval(past)
            out.append((o, d, y, p, p + lo, p + hi))
    return out


def score_intervals(errors: dict) -> dict:
    """{(model, target, h, season): (coverage, mean pinball at 0.1 and 0.9, n)}."""
    pin = lambda q, y, b: q * (y - b) if y >= b else (1 - q) * (b - y)  # noqa: E731
    out = {}
    for (m, t, h), es in errors.items():
        b = _bounds(es)
        for season in ("all", "winter"):
            sel = [x for x in b if season == "all" or x[1].month in WINTER]
            if sel:
                out[(m, t, h, season)] = (sum(lo <= y <= hi for _, _, y, _, lo, hi in sel) / len(sel),
                                          sum(pin(0.1, y, lo) + pin(0.9, y, hi) for _, _, y, _, lo, hi in sel) / 2 / len(sel),
                                          len(sel))
    return out


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
    models, all_rows = {**BASELINES, **{m: MODELS[m] for m in LADDER}}, []
    for weather in ("clim", "actual", "q_actual"):
        t = time.time()
        print(f"▶ backtest ({weather}): {list(models)} x {len(TARGETS)} targets x {len(HORIZONS)} horizons", flush=True)
        rows, errors = backtest(c, models, TARGETS, HORIZONS, weather)
        attach_dm(rows, errors)
        if weather == "clim":  # selection uses ex-ante results only
            sc = score_intervals(errors)
            for r in rows:
                r["coverage"], r["pinball"] = sc.get((r["model"], r["target"], r["horizon"], r["season"]), (None, None, 0))[:2]
            chosen = select(rows, errors)
            fc_rows = [{"run_id": run_id, "model": m, "target": tg, "horizon": h, "origin": o, "date": d, "yhat": p,
                        "p10": lo, "p90": hi, "created_at": now}
                       for (m, tg, h), es in errors.items() if chosen.get(f"{tg}|{h}") == m
                       for o, d, _, p, lo, hi in _bounds(es)]
            upsert(con, "ml.forecasts", fc_rows, ("run_id", "model", "target", "origin", "date"))
            print(f"✔ intervals: {len(fc_rows)} backtest forecasts with P10/P90 saved; winter coverage of selected "
                  "models (target 80%):\n" + "\n".join(
                      f"  {k:30} {v:7} coverage {sc[(v, *k.split('|')[:1], int(k.split('|')[1]), 'winter')][0]:.0%}"
                      for k, v in chosen.items() if (v, k.split('|')[0], int(k.split('|')[1]), 'winter') in sc),
                  flush=True)
            need_rows, need_pick = import_need_compare(errors, chosen)
            rows += need_rows
            chosen.update({f"import_need_method|{h}": m for h, m in need_pick.items()})
            print("✔ import need, winter MAE direct vs diff (demand - generation):\n" + "\n".join(
                f"  h={r['horizon']:<2} direct {r['mae']:,.0f} vs diff "
                f"{next(x['mae'] for x in need_rows if (x['model'], x['horizon'], x['season']) == ('diff', r['horizon'], 'winter')):,.0f}"
                f"  DM p={r['dm_p']:.3f} -> {need_pick[r['horizon']]}"
                for r in need_rows if r["model"] == "direct" and r["season"] == "winter"), flush=True)
        all_rows += rows
        print(f"✔ backtest ({weather}) in {time.time() - t:.0f}s; winter MAE (MAPE):\n{_table(rows)}", flush=True)
        print("  Diebold-Mariano (winter), ladder model vs next simpler:\n" + "\n".join(
            f"  {r['target']:24} h={r['horizon']:<2} {r['model']} vs {r['dm_vs']}: p={r['dm_p']:.3f}"
            for r in sorted(rows, key=lambda r: (r["target"], r["horizon"]))
            if r["season"] == "winter" and r.get("dm_vs")), flush=True)
    t = time.time()
    print("▶ monthly winter outlook backtest (origins 31 Oct 2024, 2025)", flush=True)
    mf = monthly_frame(con)
    m_rows, m_err = monthly_backtest(mf)
    all_rows += m_rows
    chosen.update({f"{k}|monthly": v for k, v in select_monthly(m_err).items()})
    print(f"✔ monthly in {time.time() - t:.0f}s; MAE GWh (MAPE) by months ahead (1 = Nov):", flush=True)
    for target in ("demand_gwh", "import_gwh"):
        for name in MONTHLY_MODELS:
            cells = [next((f"{r['mae']:6.0f}" + (f" ({r['mape']:.1f}%)" if r["mape"] is not None else "")
                           for r in m_rows if (r["model"], r["target"], r["horizon"]) == (name, target, k)), "")
                     for k in range(1, WINTER_MONTHS + 1)]
            print(f"  {target:11} {name:13} " + " | ".join(f"{c:>15}" for c in cells), flush=True)
    for yr in (2024, 2025):
        sel = chosen["demand_gwh|monthly"]
        fc = {e[1]: e[3] for (n, tg, _), es in m_err.items() if n == sel and tg == "demand_gwh"
              for e in es if e[0].year == yr}
        print(f"  winter {yr}/{(yr + 1) % 100}:" + gdp_crosscheck(con, mf, fc)[1:], flush=True)
    print(f"  chart {chart_monthly(mf, m_err)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "selection.json").write_text(json.dumps(chosen, indent=1))
    print("✔ selection (winter MAE >5% better and DM p<0.10 to climb):\n" +
          "\n".join(f"  {k:30} {v}" for k, v in chosen.items()), flush=True)
    for fn in (sensitivity, stability):
        t = time.time()
        print(f"▶ {fn.__name__}: start", flush=True)
        print(f"✔ {fn.__name__} in {time.time() - t:.0f}s:\n{fn(c)}", flush=True)
    upsert(con, "ml.backtest_metrics", [{"run_id": run_id, "coverage": None, "pinball": None, "created_at": now,
                                         **{k: v for k, v in r.items() if k != "dm_vs"}} for r in all_rows],
           ("run_id", "model", "target", "horizon", "season", "weather"))
    print(f"✔ saved {len(all_rows)} metric rows as {run_id}; chart {chart_daily(all_rows)}", flush=True)
    return {"run_id": run_id, "rows": all_rows}


# ---------- monthly winter outlook ----------

CUSTOMS_TO_NEA = 1.09  # customs import / NEA report import over 53 months (EDA reconciliation)
WINTER_MONTHS = 6  # Nov..Apr = months ahead 1..6 from an end-October origin


def _add_months(m: date, k: int) -> date:
    i = m.year * 12 + m.month - 1 + k
    return date(i // 12, i % 12 + 1, 1)


def monthly_frame(con) -> dict:
    """AD-month series: demand GWh (NEA report, BS month -> AD month it starts in), import GWh (customs scaled
    to NEA level), discharge anomaly vs 2010-2022 same-month mean."""
    demand = dict(con.execute(
        "SELECT c.date, r.national_demand FROM gold.report_monthly_balance r JOIN silver.dim_calendar c "
        "ON c.fiscal_year = r.fy AND c.bs_month = r.bs_month AND c.bs_day = 1 "
        "WHERE r.unit = 'GWh' AND r.national_demand IS NOT NULL").fetchall())
    imp = {m: v / 1000 / CUSTOMS_TO_NEA for m, v in con.execute(
        "SELECT month, month_value FROM silver.india_trade_monthly "
        "WHERE direction = 'nepal_import' AND measure = 'mwh'").fetchall()}
    q = dict(con.execute("SELECT date_trunc('month', date)::DATE, avg(discharge_index) FROM gold.daily_features "
                         "WHERE discharge_index IS NOT NULL GROUP BY 1").fetchall())
    clim = {}
    for m, v in q.items():
        if CLIM_YEARS[0] <= m <= CLIM_YEARS[1]:
            clim.setdefault(m.month, []).append(v)
    clim_m = {k: sum(v) / len(v) for k, v in clim.items()}
    anom = {m: v / clim_m[m.month] - 1 for m, v in q.items()}
    exp = {m: v / 1000 / CUSTOMS_TO_NEA for m, v in con.execute(
        "SELECT month, month_value FROM silver.india_trade_monthly "
        "WHERE direction = 'nepal_export' AND measure = 'mwh'").fetchall()}
    return {"demand_gwh": {d.replace(day=1): v for d, v in demand.items()}, "import_gwh": imp, "q_anom": anom,
            "q_clim_month": clim_m, "export_gwh": exp}


# availability at an end-October origin: annual report covers the fiscal year to Ashadh (AD June label),
# customs lag ~2 months. Backtests use only what was published by then.
LAST_AVAILABLE = {"demand_gwh": 6, "import_gwh": 8}
LOG_TARGET = {"demand_gwh": True, "import_gwh": False}  # import ~0 in monsoon: no log, no growth ratio


def m_snaive_growth(s: dict, q, targets: list[date], log: bool) -> list[float]:
    """Same month last year (or two years back if missing) x (1 + median year-on-year growth of the last
    12 observed months). No growth for import (crosses ~0)."""
    last = max(s)
    yoy = [s[m] / s[_add_months(m, -12)] for m in s if m > _add_months(last, -12) and _add_months(m, -12) in s
           and s[_add_months(m, -12)]]
    g = sorted(yoy)[len(yoy) // 2] if yoy and log else 1.0
    out = []
    for t in targets:
        k = next(k for k in range(1, 6) if _add_months(t, -12 * k) in s)
        out.append(s[_add_months(t, -12 * k)] * g ** k)
    return out


def m_linear(s: dict, q, targets: list[date], log: bool) -> list[float]:
    """OLS: (log) y ~ trend + month dummies + discharge anomaly; future anomaly = last observed (persistence)."""
    q = q or {}
    ms = sorted(s)
    last_q = next((q[m] for m in sorted(q, reverse=True) if m <= ms[-1]), 0.0)
    row = lambda m, qa: [1.0, (m.year - 2020) * 12 + m.month] + [float(m.month == k) for k in range(2, 13)] + [qa]  # noqa: E731
    X = np.array([row(m, q.get(m, 0.0)) for m in ms])
    y = np.array([math.log(s[m]) if log else s[m] for m in ms])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    pred = np.array([row(t, q.get(t, last_q)) for t in targets]) @ beta  # forecast anomaly if given, else persistence
    return list(np.exp(pred) if log else pred)


def m_ets(s: dict, q, targets: list[date], log: bool) -> list[float]:
    """Holt-Winters (statsmodels): damped additive trend, additive 12-month season, on log y for demand.
    Gaps are filled by linear interpolation (ETS needs a regular series)."""
    import warnings
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    ms = sorted(s)
    grid = [ms[0]]
    while grid[-1] < ms[-1]:
        grid.append(_add_months(grid[-1], 1))
    ys = np.array([s.get(m, np.nan) for m in grid], dtype=float)
    ys = np.interp(np.arange(len(grid)), np.flatnonzero(~np.isnan(ys)), ys[~np.isnan(ys)])
    ys = np.log(ys) if log else ys
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # convergence chatter on short series
        fit = ExponentialSmoothing(ys, trend="add", damped_trend=True, seasonal="add",
                                   seasonal_periods=12).fit()
    steps = [(t.year - grid[-1].year) * 12 + t.month - grid[-1].month for t in targets]
    fc = fit.forecast(max(steps))
    out = np.array([fc[k - 1] for k in steps])
    return list(np.exp(out) if log else out)


def m_combo(s: dict, q, targets: list[date], log: bool) -> list[float]:
    """Equal-weight mean of the three (M4: combinations beat single methods)."""
    parts = [f(s, q, targets, log) for f in (m_snaive_growth, m_linear, m_ets)]
    return [sum(x) / len(x) for x in zip(*parts)]


MONTHLY_MODELS = {"snaive_growth": m_snaive_growth, "linear_m": m_linear, "ets": m_ets, "combo": m_combo}


def monthly_backtest(mf: dict, winters: tuple[int, ...] = (2024, 2025)) -> tuple[list[dict], dict]:
    """Origin = 31 Oct of each year; forecast Nov..Apr with data published by then. Errors keyed like daily."""
    errors = {}
    for target in ("demand_gwh", "import_gwh"):
        for yr in winters:
            s = {m: v for m, v in mf[target].items() if m <= date(yr, LAST_AVAILABLE[target], 1)}
            targets = [_add_months(date(yr, 10, 1), k) for k in range(1, WINTER_MONTHS + 1)]
            actual = [(t, mf[target].get(t)) for t in targets]
            q = {m: v for m, v in mf["q_anom"].items() if m <= date(yr, 10, 1)}  # no future flow in the backtest
            for name, f in MONTHLY_MODELS.items():
                preds = f(s, q, targets, LOG_TARGET[target])
                preds = preds if LOG_TARGET[target] else [max(0.0, x) for x in preds]  # gross import >= 0
                for k, ((t, y), p) in enumerate(zip(actual, preds), 1):
                    if y is not None:
                        errors.setdefault((name, target, k), []).append((date(yr, 10, 31), t, y, p))
    rows = []
    for (name, target, k), es in errors.items():
        mape = 100 * sum(abs(y - p) / abs(y) for _, _, y, p in es) / len(es) if LOG_TARGET[target] else None
        rows.append({"model": name, "target": target, "horizon": k, "season": "winter", "weather": "clim",
                     "mae": sum(abs(y - p) for _, _, y, p in es) / len(es), "mape": mape, "n": len(es), "dm_p": None})
    return rows, errors


def select_monthly(errors: dict) -> dict[str, str]:
    """Per target: a model is used only if it has the lowest MAE in every hold-out winter; else combo."""
    out = {}
    for target in ("demand_gwh", "import_gwh"):
        wins = {}
        for (name, t, _), es in errors.items():
            if t == target:
                for o, _, y, p in es:
                    wins.setdefault(o.year, {}).setdefault(name, []).append(abs(y - p))
        best = {yr: min(d, key=lambda n: sum(d[n]) / len(d[n])) for yr, d in wins.items()}
        out[target] = best[min(best)] if len(set(best.values())) == 1 else "combo"
    return out


def chart_monthly(mf: dict, errors: dict) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for ax, target in zip(axes, ("demand_gwh", "import_gwh")):
        lo = date(2023, 7, 1)
        act = sorted((m, v) for m, v in mf[target].items() if m >= lo)
        ax.plot(*zip(*act), color="black", lw=1.5, label="actual")
        for i, name in enumerate(MONTHLY_MODELS):
            for yr in sorted({e[0].year for es in errors.values() for e in es}):  # one line per winter
                pts = sorted({(e[1], e[3]) for (n, t, _), es in errors.items() if n == name and t == target
                              for e in es if e[0].year == yr})
                ax.plot(*zip(*pts), marker=".", lw=0.8, color=f"C{i}", label=name if yr == 2024 else None)
        ax.set(title=f"{target}: hold-out winters (origin 31 Oct)", ylabel="GWh / month")
        ax.legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, "backtest_monthly")


def gdp_crosscheck(con, mf: dict, forecast: dict[date, float]) -> str:
    """Winter demand total vs last winter x (1 + 2.6 x recent GDP growth); >10% apart is flagged."""
    g = con.execute("SELECT avg(v / lag_v - 1) FROM (SELECT value v, lag(value) OVER (ORDER BY year) lag_v, year "
                    "FROM silver.macro_yearly WHERE indicator = 'NY.GDP.MKTP.KD') WHERE year >= "
                    "(SELECT max(year) - 2 FROM silver.macro_yearly WHERE indicator = 'NY.GDP.MKTP.KD')").fetchone()[0]
    prev = [_add_months(m, -12) for m in forecast]
    if not all(p in mf["demand_gwh"] for p in prev):
        return "  gdp cross-check: previous winter incomplete, skipped"
    base = sum(mf["demand_gwh"][p] for p in prev) * (1 + 2.6 * g)
    fc = sum(forecast.values())
    gap = fc / base - 1
    return (f"  gdp cross-check: forecast winter {fc:,.0f} GWh vs GDP path {base:,.0f} GWh (GDP growth {g:.1%} x "
            f"elasticity 2.6): {gap:+.1%}{'  <-- FLAG >10%' if abs(gap) > 0.10 else ''}")


# ---------- live forecast ----------

MIN_LIVE_DAYS = 8  # consecutive daily rows ending yesterday: 7-day features + today


def _months_list(start: date, n: int) -> list[date]:
    return [_add_months(start, k) for k in range(n)]


def winter_months(today: date) -> list[date]:
    """Remaining months of the current or coming Nov-Apr winter, strictly after today's month."""
    start = date(today.year if today.month >= 5 else today.year - 1, 11, 1)
    return [m for m in _months_list(start, WINTER_MONTHS) if m > today.replace(day=1)]


def daily_ready(frame: dict, today: date) -> int:
    """Consecutive days with data ending yesterday."""
    n = 0
    while today - timedelta(n + 1) in frame:
        n += 1
    return n


def forecast(con, today: date | None = None) -> int:
    """Live run: monthly winter outlook always; daily 1-30 d only with >= 8 consecutive recent days."""
    today = today or date.today()
    run_id, now, rows = f"live-{today:%Y%m%d}", datetime.now(), []
    chosen = json.loads((OUT / "selection.json").read_text())

    t = time.time()
    print(f"▶ monthly outlook from {today}: start", flush=True)
    mf = monthly_frame(con)
    _, m_err = monthly_backtest(mf)  # hold-out residuals -> intervals (12 per target: indicative)
    months = winter_months(today)
    q_daily = river_forecast(con)
    q_live = dict(mf["q_anom"])
    for m in months:  # GloFAS monthly mean -> anomaly vs 2010-2022 (replaces persistence)
        v = [x for d, x in q_daily.items() if d.replace(day=1) == m]
        if len(v) >= 20:
            q_live[m] = sum(v) / len(v) / mf["q_clim_month"][m.month] - 1
    print("  river-flow forecast anomaly vs normal: " + ", ".join(
        f"{m:%b} {q_live[m]:+.0%}" for m in months if m in q_live), flush=True)
    for target in ("demand_gwh", "import_gwh"):
        name = chosen.get(f"{target}|monthly", "combo")
        s = mf[target]
        preds = MONTHLY_MODELS[name](s, q_live, months, LOG_TARGET[target])
        res = [e[2] - e[3] for (n, tg, _), es in m_err.items() if n == name and tg == target for e in es]
        lo, hi = interval(res)
        last = max(s)
        for m, p in zip(months, preds):
            p = p if LOG_TARGET[target] else max(0.0, p)
            rows.append({"run_id": run_id, "model": name, "target": target, "origin": today, "date": m,
                         "horizon": (m.year - last.year) * 12 + m.month - last.month, "yhat": p,
                         "p10": max(0.0, p + lo) if not LOG_TARGET[target] else p + lo, "p90": p + hi,
                         "created_at": now})
        print(f"  {target} ({name}, data to {last:%Y-%m}): " + ", ".join(
            f"{r['date']:%b %Y} {r['yhat']:,.0f} [{r['p10']:,.0f}-{r['p90']:,.0f}]"
            for r in rows if r["target"] == target), flush=True)
    fc = {r["date"]: r["yhat"] for r in rows if r["target"] == "demand_gwh"}
    print(gdp_crosscheck(con, mf, fc), flush=True)
    rows += outage_adjust(con, mf, [r for r in rows if r["target"] == "import_gwh"])
    print(f"✔ monthly outlook in {time.time() - t:.0f}s", flush=True)

    c = load(con)
    c["q_forecast"] = q_daily
    n = daily_ready(c["frame"], today)
    if n < MIN_LIVE_DAYS:
        print(f"  daily skipped: widget has {n} consecutive day(s) up to yesterday (need {MIN_LIVE_DAYS}); "
              "keep `nea ingest widget` running daily", flush=True)
    else:
        rows += _daily_live(c, chosen, today, run_id, now)
    upsert(con, "ml.forecasts", rows, ("run_id", "model", "target", "origin", "date"))
    print(f"✔ saved {len(rows)} forecasts as {run_id}; chart {chart_live(mf, rows, run_id)}", flush=True)
    return len(rows)


def _daily_live(c: dict, chosen: dict, today: date, run_id: str, now) -> list[dict]:
    """Selected model per target/horizon, trained on all history; interval from its backtest errors.
    ERA5 lags ~5 days: missing recent weather -> climatology (anomaly 0)."""
    t = time.time()
    origin = today - timedelta(1)
    for k in range(7):
        d = origin - timedelta(k)
        c["wx"].setdefault(d, {w: c["clim"][(w, _doy(d))] for w in WX})
    q_fc = c.get("q_forecast", {})
    for d, v in q_fc.items():  # future river flow from GloFAS; past days keep observed values
        if d > origin:
            c["wx"][d] = {"discharge_index": v}
    rows = []
    for target in ("requirement_mwh", "peak_demand_mw", "domestic_gen_mwh"):
        for h in HORIZONS:
            name = chosen[f"{target}|{h}"]
            fn = {**BASELINES, **MODELS}[name]
            # generation follows river flow: with a forecast, use the model trained on known flow
            mode = "q_actual" if target == "domestic_gen_mwh" and origin + timedelta(h) in q_fc else "clim"
            _, errs = backtest(c, {name: fn}, [target], [h], mode)
            hist = [(x, yv) for o, x, yv in _rows(c, target, h, mode) if o + timedelta(h) <= origin]
            x = features(c, origin, h, target, mode)
            if x is None:
                continue
            p = fn(hist, [x])[0]
            lo, hi = interval([e[2] - e[3] for e in errs[(name, target, h)]][-WINDOW:])
            rows.append({"run_id": run_id, "model": name, "target": target, "horizon": h, "origin": origin,
                         "date": origin + timedelta(h), "yhat": p, "p10": p + lo, "p90": p + hi, "created_at": now})
    by = {(r["target"], r["horizon"]): r for r in rows}
    for h in HORIZONS:  # import need = demand - generation (diff method, docs/models/import-need.md)
        if ("requirement_mwh", h) in by and ("domestic_gen_mwh", h) in by:
            r, g = by[("requirement_mwh", h)], by[("domestic_gen_mwh", h)]
            rows.append({**r, "model": "diff", "target": "import_need_mwh", "yhat": r["yhat"] - g["yhat"],
                         "p10": r["p10"] - g["p90"], "p90": r["p90"] - g["p10"]})  # ponytail: conservative bounds
    print(f"✔ daily forecast: {len(rows)} rows in {time.time() - t:.0f}s", flush=True)
    return rows


def chart_live(mf: dict, rows: list[dict], run_id: str) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for ax, target in zip(axes, ("demand_gwh", "import_gwh")):
        act = sorted((m, v) for m, v in mf[target].items() if m >= date(2023, 7, 1))
        ax.plot(*zip(*act), color="black", lw=1.2, label="actual")
        for i, name in enumerate(sorted({r["model"] for r in rows if r["target"] == target})):
            d, y, lo, hi = zip(*sorted((r["date"], r["yhat"], r["p10"], r["p90"])
                                       for r in rows if r["target"] == target and r["model"] == name))
            col = "C3" if name.endswith("+outage") else "C0"
            ax.plot(d, y, marker="o", color=col, label=name)
            ax.fill_between(d, lo, hi, color=col, alpha=0.15, label=f"{name} P10-P90")
        ax.set(title=f"{target}: winter outlook ({run_id})", ylabel="GWh / month")
        ax.legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, f"forecast_{run_id}")


def river_forecast(con) -> dict[date, float]:
    """Latest GloFAS issue: daily discharge_index (sum of the 3 basin points, ensemble mean)."""
    return dict(con.execute(
        "SELECT date, sum(discharge_m3s) FROM silver.river_discharge_forecast "
        "WHERE issued = (SELECT max(issued) FROM silver.river_discharge_forecast) "
        "AND point IN ('koshi_chatara', 'narayani_devghat', 'karnali_chisapani') GROUP BY date HAVING count(*) = 3"
    ).fetchall())


def outage_loss(outages: list[dict], factors: dict, m: date) -> tuple[float, float]:
    """(all, destroyed-only) GWh of domestic generation lost in month m: capacity x dry-season factor x hours,
    plus reservoir shortfall energy spread over Jan-Apr. History has no such outage, so models can't see it."""
    end = _add_months(m, 1)
    days = (end - m).days
    tot = des = 0.0
    for o in outages:
        if o["outage_start"] >= end or (o["expected_return"] and o["expected_return"] <= m):
            continue
        g = o["capacity_mw"] * factors.get(o["kind"], 0.0) * 24 * days / 1000
        if o["kind"] == "storage" and m.month in (1, 2, 3, 4):
            g += (o["winter_energy_gwh"] or 0.0) / 4
        tot += g
        des += g if o["status"] == "destroyed" else 0.0
    return tot, des


def outage_adjust(con, mf: dict, base: list[dict]) -> list[dict]:
    """Import + lost generation not covered by the month's usual export surplus (same month last year).
    yhat/P90 assume every listed outage lasts all winter; P10 assumes only destroyed plants stay out."""
    from nea_forecast.outages import OUTAGES_JSON
    factors = json.loads(OUTAGES_JSON.read_text())["dry_season_factor"]
    outs = [dict(zip(("capacity_mw", "kind", "status", "outage_start", "expected_return", "winter_energy_gwh"), r))
            for r in con.execute("SELECT capacity_mw, kind, status, outage_start, expected_return, winter_energy_gwh "
                                 "FROM silver.plant_outage").fetchall()]
    if not outs:
        print("  outage adjustment: no outages registered (nea ingest outages)", flush=True)
        return []
    out = []
    print("  flood/outage adjustment to import (GWh): month  lost-all  lost-destroyed  usual-export  base -> adjusted",
          flush=True)
    for r in base:
        m = r["date"]
        tot, des = outage_loss(outs, factors, m)
        exp = mf["export_gwh"].get(_add_months(m, -12), 0.0)
        add, add_lo = max(0.0, tot - exp), max(0.0, des - exp)
        out.append({**r, "model": f"{r['model']}+outage", "yhat": r["yhat"] + add, "p10": r["p10"] + add_lo,
                    "p90": r["p90"] + add})
        print(f"    {m:%b %Y} {tot:9,.0f} {des:15,.0f} {exp:13,.0f}   {r['yhat']:5,.0f} -> {r['yhat'] + add:,.0f}",
              flush=True)
    return out
