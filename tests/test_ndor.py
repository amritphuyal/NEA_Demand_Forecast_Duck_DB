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
