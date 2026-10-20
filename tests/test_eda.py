import math
from datetime import date, timedelta

import pytest

from nea_forecast import eda
from nea_forecast.calendar import build_calendar
from nea_forecast.lake import connect, upsert


def lake(tmp_path, start: date, end: date, days: list[dict] = ()):
    """Synthetic lake: calendar for the span + the given nea_daily rows (unset columns null, qa_ok true)."""
    con = connect(tmp_path)
    upsert(con, "silver.dim_calendar", build_calendar(start, end), ("date",))
    cols = [c[0] for c in con.execute("DESCRIBE silver.nea_daily").fetchall()]
    if days:
        upsert(con, "silver.nea_daily", [{**dict.fromkeys(cols), "qa_ok": True, **d} for d in days], ("date",))
    return con


def span(start: date, n: int) -> list[date]:
    return [start + timedelta(i) for i in range(n)]


def test_seasonality_holiday_dip_and_qa_filter(tmp_path):
    cal = {r["date"]: r for r in build_calendar(date(2025, 1, 1), date(2025, 1, 31))}
    hol = {d for d, r in cal.items() if r["is_holiday"]}
    assert hol, "fixture month needs a holiday"
    bad = next(d for d in cal if d not in hol)
    days = [{"date": d, "requirement_mwh": 800.0 if d in hol else 1000.0} for d in cal if d != bad]
    days.append({"date": bad, "requirement_mwh": 0.0, "qa_ok": False})
    r = eda.seasonality(lake(tmp_path, date(2025, 1, 1), date(2025, 1, 31), days), None)
    assert r["holiday_dip_pct"] == pytest.approx(-20, abs=0.5)
    assert r["n"] == 30
    assert r["winter_vs_summer"]["winter"]["requirement_mwh"] > 900
