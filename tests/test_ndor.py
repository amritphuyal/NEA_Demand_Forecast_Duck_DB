from datetime import date, time
from pathlib import Path

import pymupdf
import pytest

from nea_forecast.ndor import ENERGY_COLS, ParseError, check_balance, parse_pdf, qa_ok

FIX = Path(__file__).parent / "fixtures"


def text_pdf(path: Path, text: str) -> Path:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(path)
    return path


def test_parse_2081_09_27():
    r = parse_pdf(FIX / "NDOR_2081_09_27.pdf")
    assert r["date"] == date(2025, 1, 11) and r["bs_date"] == "2081-09-27"
    assert (r["nea_gen_mwh"], r["nea_sub_gen_mwh"], r["ipp_gen_mwh"], r["import_mwh"]) == (6251, 5017, 15623, 6845)
    assert (r["total_available_mwh"], r["export_mwh"], r["net_met_mwh"]) == (33735, 0, 33735)
    assert (r["interruption_mwh"], r["deficit_mwh"], r["requirement_mwh"], r["net_exchange_india_mwh"]) == (1700, 0, 35435, 6845)
    assert r["peak_time"] == time(17, 55)
    assert (r["peak_gen_mw"], r["peak_import_mw"], r["peak_availability_mw"], r["peak_export_mw"], r["peak_met_mw"]) == (1367, 211, 1578, 0, 1578)
    assert (r["peak_interruption_mw"], r["peak_deficit_mw"], r["peak_demand_mw"], r["peak_net_exchange_india_mw"]) == (350, 0, 1928, 211)
    assert r["qa_ok"] is True


def test_parse_oldest_layout():
    # header has no colon / spaces: "For Date 2080/01/01(2023/04/14)"
    r = parse_pdf(FIX / "NDOR_2080_01_01.pdf")
    assert r["date"] == date(2023, 4, 14) and r["bs_date"] == "2080-01-01"
    assert r["requirement_mwh"] == 32612 and r["peak_demand_mw"] == 1643
    assert check_balance(r)


def test_check_balance_flags_bad():
    r = parse_pdf(FIX / "NDOR_2081_09_27.pdf")
    r["import_mwh"] += 500
    assert not check_balance(r)


def test_all_zero_row_not_qa_ok():
    r = parse_pdf(FIX / "NDOR_2081_09_27.pdf")
    assert qa_ok({**r, **{k: 0 for k in ENERGY_COLS}}) is False


def test_garbage_raises(tmp_path):
    with pytest.raises(ParseError):
        parse_pdf(text_pdf(tmp_path / "x.pdf", "hello"))


# --- discovery + ingest ---------------------------------------------------
from nea_forecast import ndor
from nea_forecast.fetch import NotFound
from nea_forecast.lake import connect

LISTING = (FIX / "ndor_listing_p1.html").read_text()
GOOD = (FIX / "NDOR_2081_09_27.pdf").read_bytes()


def test_parse_listing():
    items = ndor.parse_listing(LISTING)
    assert len(items) == 10 and len({s for s, _ in items}) == 10
    assert all(u.startswith("https://transd.nea.org.np/detail/nepal-daily-operational-report-") for _, u in items)
    assert items[0][0] == "nepal-daily-operational-report-2081-09-27"  # page order, newest first


def test_parse_detail():
    html = '<a href="https://transd.nea.org.np/uploads/shares/Daily_op_reports/NDOR%202081_09_27%20rev1.pdf">Open</a>'
    assert ndor.parse_detail(html).endswith("rev1.pdf")


def test_pdf_url_from_slug():
    assert ndor.pdf_url("nepal-daily-operational-report-2081-09-27") == \
        "https://transd.nea.org.np/uploads/shares/Daily_op_reports/NDOR%202081_09_27.pdf"
    assert ndor.pdf_url("nepal-daily-operational-report-2081-09-27-rev1") is None


def test_discover_stops_at_known(monkeypatch):
    pages = {"1": LISTING, "2": ""}  # page 2 has nothing new -> stop, page 3 never fetched
    monkeypatch.setattr(ndor, "fetch_many", lambda urls, expect_pdf=False: [pages[u.rsplit("=", 1)[1]].encode() for u in urls[:2]])
    items = ndor.parse_listing(LISTING)
    known = {s for s, _ in items[3:]}
    assert [s for s, _ in ndor.discover(known)] == [s for s, _ in items[:3]]


def _stub(monkeypatch, tmp_path, items, bodies):
    monkeypatch.setattr(ndor, "discover", lambda known: [i for i in items if i[0] not in known])
    def fake_fetch(url, expect_pdf=False):
        if url not in bodies:
            raise NotFound(url)
        return bodies[url]
    monkeypatch.setattr(ndor, "fetch", fake_fetch)
    def fake_many(urls, expect_pdf=False):
        out = []
        for u in urls:
            try:
                out.append(fake_fetch(u, expect_pdf))
            except NotFound as e:
                out.append(e)
        return out
    monkeypatch.setattr(ndor, "fetch_many", fake_many)
    return connect(tmp_path)


def test_ingest_idempotent_and_parse_error_logged(tmp_path, monkeypatch):
    good, bad = "nepal-daily-operational-report-2081-09-27", "nepal-daily-operational-report-2081-09-26"
    bodies = {ndor.pdf_url(good): GOOD, ndor.pdf_url(bad): text_pdf(tmp_path / "g.pdf", "hello").read_bytes()}
    con = _stub(monkeypatch, tmp_path, [(good, "d1"), (bad, "d2")], bodies)
    assert ndor.ingest(con, tmp_path) == 1
    assert ndor.ingest(con, tmp_path) == 0
    assert con.execute("select count(*) from silver.nea_daily").fetchone()[0] == 1
    assert con.execute(f"select status from bronze.ingest_log where key='{bad}'").fetchone()[0] == "parse_error"
    assert (tmp_path / "raw/nea_ndor" / f"{good}.pdf").exists()


def test_rev1_replaces_same_date(tmp_path, monkeypatch):
    orig, rev = "nepal-daily-operational-report-2081-09-27", "nepal-daily-operational-report-2081-09-27-rev1"
    rev_pdf = "https://transd.nea.org.np/uploads/shares/Daily_op_reports/NDOR%202081_09_27%20rev1.pdf"
    bodies = {ndor.pdf_url(orig): GOOD, "detail-rev": f'<a href="{rev_pdf}">x</a>'.encode(), rev_pdf: GOOD}
    con = _stub(monkeypatch, tmp_path, [(rev, "detail-rev"), (orig, "detail-orig")], bodies)  # newest first
    assert ndor.ingest(con, tmp_path) == 2
    assert con.execute("select count(*), any_value(source_url) from silver.nea_daily").fetchone() == (1, rev_pdf)


def test_date_header_without_zero_padding():
    m = ndor.DATE_RE.search("For Date: 2080/01/4 ( 2023/05/1 )")
    assert m and m.groups() == ("2080", "01", "4", "2023", "05", "1")
