from datetime import date

from nea_forecast.calendar import build_calendar
from nea_forecast.lake import connect, upsert
from nea_forecast.ndor import parse_pdf
from pathlib import Path


def test_calendar_known_dates():
    rows = {r["date"]: r for r in build_calendar(date(2025, 1, 1), date(2025, 1, 31))}
    r = rows[date(2025, 1, 11)]
    assert r["bs_date"] == "2081-09-27" and r["is_saturday"] is True
    assert r["season"] == "winter" and r["fiscal_year"] == "2081/82"


def test_fiscal_year_starts_shrawan():
    rows = {r["date"]: r for r in build_calendar(date(2024, 7, 15), date(2024, 7, 16))}
    assert rows[date(2024, 7, 15)]["fiscal_year"] == "2080/81"  # Asar end
    assert rows[date(2024, 7, 16)]["fiscal_year"] == "2081/82"  # 2081-04-01


def test_dashain_flagged():
    rows = build_calendar(date(2024, 10, 1), date(2024, 10, 31))
    assert any(r["is_holiday"] and "Dashami" in r["holiday_name"] for r in rows)


def test_gold_views_join(tmp_path):
    con = connect(tmp_path)
    upsert(con, "silver.dim_calendar", build_calendar(date(2025, 1, 1), date(2025, 1, 31)), ("date",))
    row = parse_pdf(Path(__file__).parent / "fixtures" / "NDOR_2081_09_27.pdf")
    upsert(con, "silver.nea_daily", [{**row, "source": "t", "source_url": "u"}], ("date",))
    upsert(con, "silver.weather_daily", [{"date": date(2025, 1, 11), "point": "kathmandu", "tmax_c": 18.0,
                                          "tmin_c": 2.0, "precip_mm": 0.0}], ("date", "point"))
    got = con.execute("select bs_date, peak_demand_mw, tmax_ktm from gold.daily_features where date='2025-01-11'").fetchone()
    assert got == ("2081-09-27", 1928, 18.0)
    m = con.execute("select days_reported, requirement_mwh, winter from gold.monthly_summary "
                    "where bs_year=2081 and bs_month=9").fetchone()
    assert m == (1, 35435, True)
