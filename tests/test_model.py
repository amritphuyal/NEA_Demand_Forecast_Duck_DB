import math
from datetime import date, timedelta

import pytest

from nea_forecast import model

T = "requirement_mwh"


def ctx(n=400, start=date(2023, 6, 1), y=lambda i, d: 1000.0 + 100 * (d.weekday() == 5)):
    """Synthetic context: n days of one target, flat weather equal to climatology."""
    days = [start + timedelta(i) for i in range(n)]
    clim = {(c, k): v for k in range(1, 367) for c, v in
            (("tmean_ktm", 10.0), ("tmean_terai", 20.0), ("tmin_ktm", 3.0), ("discharge_index", 500.0))}
    return {"frame": {d: {T: y(i, d)} for i, d in enumerate(days)},
            "cal": {d: (d.weekday(), False) for d in days + [days[-1] + timedelta(i) for i in range(1, 40)]},
            "wx": {d: {"tmean_ktm": 10.0, "tmean_terai": 20.0, "tmin_ktm": 3.0, "discharge_index": 500.0} for d in days},
            "clim": clim, "hdd_base": 15.0, "cdd_base": 24.0}


def test_features_no_leakage():
    c = ctx()
    o = date(2024, 1, 10)
    before = model.features(c, o, 7, T)
    for d in list(c["frame"]):
        if d > o:
            c["frame"][d][T] = -1.0
            c["wx"][d]["tmean_terai"] = 99.0
    assert model.features(c, o, 7, T) == before


def test_snaive_respects_horizon():
    c = ctx(y=lambda i, d: float(i))
    o = date(2024, 1, 10)
    for h, back in ((1, 6), (7, 0), (14, 0), (30, 5)):
        assert model.features(c, o, h, T)["y_snaive"] == c["frame"][o - timedelta(back)][T]


def test_missing_lag_returns_none():
    c = ctx()
    o = date(2024, 1, 10)
    del c["frame"][o - timedelta(3)]  # inside the 7-day mean
    assert model.features(c, o, 1, T) is None


def test_wma30_weights():
    c = ctx(y=lambda i, d: float(i))
    o = date(2024, 1, 10)
    ys = [c["frame"][o - timedelta(i)][T] for i in range(30)]
    w = [30 - i for i in range(30)]
    assert model.features(c, o, 1, T)["y_wma30"] == pytest.approx(sum(a * b for a, b in zip(w, ys)) / sum(w))


def test_backtest_weekly_series_snaive_mae_zero():
    c = ctx()
    metrics, errors = model.backtest(c, {"snaive": model.BASELINES["snaive"]}, [T], [1, 7], "clim", date(2024, 3, 1))
    assert {(m["horizon"], m["season"]): m["mae"] for m in metrics if m["model"] == "snaive"}[(7, "all")] == 0
    assert all(m["mape"] is not None for m in metrics)


def test_fit_ridge_recovers_coefficients():
    import numpy as np
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 2))
    y = 3 * X[:, 0] - 2 * X[:, 1] + 5
    fit = model.fit_ridge(X, y, 1e-6)
    assert model.predict_ridge(fit, np.array([[1.0, 1.0], [0.0, 0.0]])) == pytest.approx([6.0, 5.0], rel=0.01)


def test_dm_test():
    import numpy as np
    e = list(np.random.default_rng(1).normal(size=200))
    assert model.dm_test(e, e, 1) == 1.0
    assert model.dm_test(e, [2 * x for x in e], 7) < 0.01


def test_select_needs_margin_and_significance():
    base = {"naive": 100.0, "snaive": 120.0}
    assert model.select_one({**base, "ridge": 97.0}, lambda a, b: 0.01) == "naive"  # 3% better: not enough
    assert model.select_one({**base, "ridge": 90.0}, lambda a, b: 0.01) == "ridge"
    assert model.select_one({**base, "ridge": 90.0}, lambda a, b: 0.4) == "naive"  # better but not significant
    assert model.select_one({**base, "ridge": 90.0, "lgbm": 88.0}, lambda a, b: 0.01) == "ridge"  # lgbm < 5% over ridge


def test_select_prefers_simpler_model_of_equal_skill():
    # ridge alone not significant vs naive, lgbm is; ridge within 5% of lgbm -> ridge
    p = lambda a, b: 0.01 if a == "lgbm" else 0.4  # noqa: E731
    assert model.select_one({"naive": 100.0, "ridge": 62.0, "lgbm": 61.6}, p) == "ridge"
    assert model.select_one({"naive": 100.0, "ridge": 70.0, "lgbm": 60.0}, p) == "lgbm"
