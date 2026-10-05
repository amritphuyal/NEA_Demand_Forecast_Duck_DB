from datetime import datetime
from pathlib import Path

from nea_forecast import dhm
from nea_forecast.lake import connect

HTML = (Path(__file__).parent / "fixtures" / "dhm_river_watch.html").read_text()


def test_parse_river_watch_skips_null_level():
    rows = dhm.parse_river_watch(HTML)
    assert len(rows) == 1
    r = rows[0]
    assert (r["station_id"], r["level_m"], r["warning_level"]) == (101, 2.31, 5.5)
    assert r["observed_at"] == datetime(2026, 10, 25, 10, 15)


def test_ingest_dedupes_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(dhm, "fetch", lambda url: HTML.encode())
    con = connect(tmp_path)
    dhm.ingest(con, tmp_path)
    dhm.ingest(con, tmp_path)
    assert con.execute("select count(*) from silver.river_level_obs").fetchone()[0] == 1
