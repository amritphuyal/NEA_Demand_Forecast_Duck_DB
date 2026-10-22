import json
from datetime import date

from nea_forecast import export
from nea_forecast.calendar import build_calendar
from nea_forecast.lake import connect, upsert


def test_export_writes_parquet_and_manifest(tmp_path):
    con = connect(tmp_path / "lake")
    upsert(con, "silver.dim_calendar", build_calendar(date(2025, 1, 1), date(2025, 1, 10)), ("date",))
    m = export.export(con, tmp_path / "out")
    assert m["tables"]["dim_calendar"]["rows"] == 10 and (tmp_path / "out" / "dim_calendar.parquet").exists()
    assert m["tables"]["forecasts"]["rows"] == 0  # empty tables still export (schema for the site)
    pts = m["tables"]["points"]
    assert pts["rows"] > 10 and "approx" in pts["columns"]
    assert json.loads((tmp_path / "out" / "manifest.json").read_text())["exported_at"]
