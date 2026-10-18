import re
from datetime import date
from pathlib import Path

from nea_forecast import india_trade
from nea_forecast.lake import connect

TBL = (Path(__file__).parent / "fixtures" / "tradestat_export_2025_01.html").read_text()


def test_parse_nepal_row_gives_two_years():
    rows = india_trade.parse(TBL, "nepal_import", "mwh")
    assert rows == [
        {"month": date(2024, 1, 1), "direction": "nepal_import", "measure": "mwh", "month_value": 271790, "fy_cum_value": 1063580},
        {"month": date(2025, 1, 1), "direction": "nepal_import", "measure": "mwh", "month_value": 252020, "fy_cum_value": 961250},
    ]


def test_no_nepal_row_means_zero_but_empty_table_means_unpublished():
    no_nepal = TBL.replace("NEPAL", "MALDIVES")
    assert [r["month_value"] for r in india_trade.parse(no_nepal, "nepal_import", "mwh")] == [0, 0]
    assert india_trade.parse("<table><tr><th>S.No.</th></tr></table>", "nepal_import", "mwh") == []


def test_months_to_query_skips_stored_but_rechecks_recent():
    stored = {date(2025, 1, 1), date(2024, 1, 1), date(2026, 8, 1)}
    todo = india_trade.months_to_query(stored, today=date(2026, 10, 25), start=date(2024, 1, 1))
    assert date(2025, 1, 1) not in todo and date(2024, 2, 1) in todo
    assert date(2026, 8, 1) in todo and date(2026, 10, 1) in todo and date(2026, 11, 1) not in todo


def test_ingest(tmp_path, monkeypatch):
    monkeypatch.setattr(india_trade, "query", lambda client, direction, measure, m: TBL)
    monkeypatch.setattr(india_trade, "WORKERS", 2)
    monkeypatch.setattr(india_trade, "START", date(2025, 1, 1))
    monkeypatch.setattr(india_trade, "_today", lambda: date(2025, 1, 20))
    monkeypatch.setattr(india_trade.time, "sleep", lambda s: None)
    con = connect(tmp_path)
    india_trade.ingest(con, tmp_path)
    got = con.execute("select count(*), count(distinct month) from silver.india_trade_monthly").fetchone()
    assert got == (8, 2)  # 2 months x 2 directions x 2 measures


def test_ingest_skips_month_covered_by_next_year_query(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(india_trade, "query", lambda client, d, ms, m: asked.append(m) or TBL)
    monkeypatch.setattr(india_trade, "START", date(2024, 1, 1))
    monkeypatch.setattr(india_trade, "_today", lambda: date(2025, 1, 20))
    monkeypatch.setattr(india_trade, "PAGES", {"nepal_import": ("export", "cwacex")})
    monkeypatch.setattr(india_trade, "MEASURES", {"mwh": "2"})
    india_trade.ingest(connect(tmp_path), tmp_path)
    assert date(2024, 1, 1) not in asked and date(2025, 1, 1) in asked  # Jan 2025 query returns Jan 2024 too
    assert date(2024, 2, 1) in asked  # Feb 2025 doesn't exist yet -> Feb 2024 asked directly


def test_unpublished_month_keeps_only_previous_year(monkeypatch):
    monkeypatch.setattr(india_trade, "_today", lambda: date(2025, 2, 20))
    tbl = TBL.replace("252,020", "0").replace("961,250", "0")
    tbl = re.sub(r"855,359\.00", "0.00", tbl)  # Total for the current month = 0 -> unpublished
    got = india_trade.parse(tbl, "nepal_import", "mwh")
    assert [r["month"] for r in got] == [date(2024, 1, 1)]


def test_old_all_zero_month_is_kept_as_data(monkeypatch):
    monkeypatch.setattr(india_trade, "_today", lambda: date(2026, 10, 25))
    tbl = re.sub(r"855,359\.00", "0.00", TBL.replace("252,020", "0"))
    assert [r["month_value"] for r in india_trade.parse(tbl, "nepal_import", "mwh")] == [271790, 0]


def test_dash_growth_keeps_column_positions():
    rows = [["S.No.", "Country", "Feb-2017 (R)", "Feb-2018 (R)", "%Growth", "Apr-Feb2017 (R)", "Apr-Feb2018 (R)", "%Growth"],
            ["2", "NEPAL", "231,000", "0", "-", "1,789,640", "1,820,020", "2"],
            ["", "Total", "598,000.00", "0.00", "-", "5,794,715.00", "5,871,690.00", "1.33"]]
    got = india_trade.parse_rows(rows, "nepal_import", "mwh")
    assert [(r["month_value"], r["fy_cum_value"]) for r in got] == [(231000, 1789640), (0, 1820020)]


def test_fresh_backfill_reaches_old_years(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(india_trade, "query", lambda client, d, ms, m: asked.append(m) or TBL)
    monkeypatch.setattr(india_trade, "START", date(2018, 1, 1))
    monkeypatch.setattr(india_trade, "_today", lambda: date(2026, 10, 25))
    monkeypatch.setattr(india_trade, "PAGES", {"nepal_import": ("export", "cwacex")})
    monkeypatch.setattr(india_trade, "MEASURES", {"mwh": "2"})
    india_trade.ingest(connect(tmp_path), tmp_path)
    covered = {m for a in asked for m in (a, date(a.year - 1, a.month, 1))}
    assert date(2018, 3, 1) in covered and date(2021, 6, 1) in covered
    assert len(asked) < 70  # ~half of 106 months
