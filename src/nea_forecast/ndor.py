"""NEA Nepal Daily Operational Report (NDOR): parse the 1-page PDF."""
import re
from datetime import date, time
from pathlib import Path

import pdfplumber

ENERGY_COLS = ["nea_gen_mwh", "nea_sub_gen_mwh", "ipp_gen_mwh", "import_mwh", "total_available_mwh",
               "export_mwh", "net_met_mwh", "interruption_mwh", "deficit_mwh", "requirement_mwh",
               "net_exchange_india_mwh"]
PEAK_COLS = ["peak_gen_mw", "peak_import_mw", "peak_availability_mw", "peak_export_mw", "peak_met_mw",
             "peak_interruption_mw", "peak_deficit_mw", "peak_demand_mw", "peak_net_exchange_india_mw"]

NUM = r"-?[\d,]+(?:\.\d+)?"
DATE_RE = re.compile(r"For Date:?\s*(\d{4})/(\d{2})/(\d{2})\s*\(\s*(\d{4})/(\d{2})/(\d{2})\s*\)")
ENERGY_RE = re.compile(rf"^{NUM}(?:\s+{NUM}){{10}}$", re.M)
PEAK_RE = re.compile(rf"^(\d{{1,2}}):(\d{{2}})((?:\s+{NUM}){{9}})$", re.M)


class ParseError(Exception): ...


def _nums(s: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(NUM, s)]


def parse_pdf(path: Path) -> dict:
    """Return one silver.nea_daily row (without source/source_url)."""
    with pdfplumber.open(path) as pdf:
        text = pdf.pages[0].extract_text() or ""
    d, e, p = DATE_RE.search(text), ENERGY_RE.search(text), PEAK_RE.search(text)
    if not (d and e and p):
        raise ParseError(f"{path}: date={bool(d)} energy={bool(e)} peak={bool(p)}")
    by, bm, bd, ay, am, ad = d.groups()
    row = {"date": date(int(ay), int(am), int(ad)), "bs_date": f"{by}-{bm}-{bd}",
           **dict(zip(ENERGY_COLS, _nums(e.group()))),
           "peak_time": time(int(p.group(1)), int(p.group(2))),
           **dict(zip(PEAK_COLS, _nums(p.group(3))))}
    row["qa_ok"] = qa_ok(row)
    return row


def check_balance(r: dict, tol: float = 2.0) -> bool:
    """Report's own arithmetic must hold (values are rounded, so allow tol)."""
    checks = [
        r["nea_gen_mwh"] + r["nea_sub_gen_mwh"] + r["ipp_gen_mwh"] + r["import_mwh"] - r["total_available_mwh"],
        r["total_available_mwh"] - r["export_mwh"] - r["net_met_mwh"],
        r["net_met_mwh"] + r["interruption_mwh"] + r["deficit_mwh"] - r["requirement_mwh"],
        r["peak_gen_mw"] + r["peak_import_mw"] - r["peak_availability_mw"],
        r["peak_met_mw"] + r["peak_interruption_mw"] + r["peak_deficit_mw"] - r["peak_demand_mw"],
    ]
    return all(abs(c) <= tol for c in checks)


def qa_ok(r: dict) -> bool:
    return check_balance(r) and r["requirement_mwh"] > 0
