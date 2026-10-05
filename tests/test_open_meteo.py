import json
from datetime import date
from pathlib import Path

from nea_forecast import open_meteo as om
from nea_forecast.lake import connect, upsert

FIX = Path(__file__).parent / "fixtures"
WEATHER = {"temperature_2m_max": "tmax_c", "temperature_2m_min": "tmin_c", "precipitation_sum": "precip_mm"}


def test_parse_daily_skips_null_tail():
    rows = om.parse_daily(json.loads((FIX / "om_archive.json").read_text()), "ktm", WEATHER)
    assert [r["date"] for r in rows] == [date(2025, 1, 1), date(2025, 1, 2)]
    assert rows[1] == {"date": date(2025, 1, 2), "point": "ktm", "tmax_c": 16.4, "tmin_c": 0.8, "precip_mm": 0.3}


def test_parse_flood():
    rows = om.parse_daily(json.loads((FIX / "om_flood.json").read_text()), "trishuli", {"river_discharge": "discharge_m3s"})
    assert rows == [{"date": date(2025, 1, 1), "point": "trishuli", "discharge_m3s": 42.5}]


def test_start_date_overlap(tmp_path):
    con = connect(tmp_path)
    assert om.start_date(con, "silver.weather_daily", "ktm") == date(2010, 1, 1)
    upsert(con, "silver.weather_daily", [{"date": date(2025, 1, 20), "point": "ktm", "tmax_c": 1.0,
                                          "tmin_c": 0.0, "precip_mm": 0.0}], ("date", "point"))
    assert om.start_date(con, "silver.weather_daily", "ktm") == date(2025, 1, 10)


def test_ingest_weather(tmp_path, monkeypatch):
    body = (FIX / "om_archive.json").read_bytes()
    monkeypatch.setattr(om, "fetch", lambda url: body)
    con = connect(tmp_path)
    n = om.ingest_weather(con, tmp_path)
    assert n == 2 * len(om.load_sources()["open_meteo_weather"]["points"])
    assert con.execute("select count(distinct point) from silver.weather_daily").fetchone()[0] == 6
    assert any((tmp_path / "raw/open_meteo/weather").iterdir())
