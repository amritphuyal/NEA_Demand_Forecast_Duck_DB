import json
import struct

import duckdb

from nea_forecast import findings

# Stand-in queries with the same column names as queries/*.sql, so the runner and charts run without a lake
FAKE = {
    "f1_export_vs_winter_import": "SELECT * FROM (VALUES ('2081/82', 12, 2381.0, 1187.0, 1710.0, 14065.0), ('2082/83', 12, 3939.0, 913.0, 1122.0, 15140.0))"
                                  " t(fy, months, export_gwh_year, import_gwh_poush_chaitra, import_gwh_year, demand_gwh_year)",
    "f2_gen_vs_demand_monthly": "SELECT * FROM (VALUES (DATE '2024-02-01', 28, 33.5, 18.6, 12.9, 0.0, 56.0), (DATE '2024-07-01', 31, 39.6, 54.9, 0.0, 15.5, 139.0))"
                                " t(month, days, demand_gwh_per_day, domestic_gen_gwh_per_day, import_gwh_per_day, export_gwh_per_day, domestic_gen_pct_of_demand)",
    "f3_evening_peak_by_season": "SELECT * FROM (VALUES ('winter', 265, 1775.0, 1370.0, 225.0, 180.0, 12.3, 9.7), ('summer', 343, 1814.0, 1669.0, 68.0, 77.0, 3.8, 4.1))"
                                 " t(season, days, peak_demand_mw, domestic_mw, import_mw, not_supplied_mw, import_pct_of_peak, not_supplied_pct_of_peak)",
    "f4_peak_hour": "SELECT * FROM (VALUES (17, 110), (18, 209), (19, 289)) t(peak_hour, days)",
}


def test_run_writes_findings_and_video_sized_charts(tmp_path):
    q = tmp_path / "queries"
    q.mkdir()
    for name, sql in FAKE.items():
        (q / f"{name}.sql").write_text(sql)
    res = findings.run(duckdb.connect(), out=tmp_path / "assets", queries=q)
    saved = json.loads((tmp_path / "assets" / "findings.json").read_text())
    assert saved["f1_export_vs_winter_import"]["rows"][1]["export_gwh_year"] == 3939.0 == res["f1_export_vs_winter_import"]["rows"][1]["export_gwh_year"]
    pngs = sorted((tmp_path / "assets").glob("*.png"))
    assert len(pngs) == 3
    for p in pngs:  # PNG header: width and height at bytes 16-24
        assert struct.unpack(">II", p.read_bytes()[16:24]) == (1920, 1080)
