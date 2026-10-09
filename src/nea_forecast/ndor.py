"""NEA Nepal Daily Operational Report (NDOR): discover on transd, download, parse, load."""
import hashlib
import re
from datetime import date, time
from pathlib import Path

import pdfplumber

from nea_forecast.fetch import BATCH, Blocked, FetchError, NotFound, fetch, fetch_many
from nea_forecast.lake import log, seen, upsert

SOURCE = "nea_ndor"
LISTING_URL = "https://transd.nea.org.np/en/category/daily-operational-reports-1?page={}"
PDF_URL = "https://transd.nea.org.np/uploads/shares/Daily_op_reports/NDOR%20{}_{}_{}.pdf"
LISTING_RE = re.compile(r'href="(https?://transd\.nea\.org\.np/detail/(nepal-daily-operational-report-[\w-]+))"')
DETAIL_PDF_RE = re.compile(r'href="([^"]*Daily_op_reports/[^"]*\.pdf)"', re.I)
SLUG_DATE_RE = re.compile(r"-(\d{4})-(\d{2})-(\d{2})$")

ENERGY_COLS = ["nea_gen_mwh", "nea_sub_gen_mwh", "ipp_gen_mwh", "import_mwh", "total_available_mwh",
               "export_mwh", "net_met_mwh", "interruption_mwh", "deficit_mwh", "requirement_mwh",
               "net_exchange_india_mwh"]
PEAK_COLS = ["peak_gen_mw", "peak_import_mw", "peak_availability_mw", "peak_export_mw", "peak_met_mw",
             "peak_interruption_mw", "peak_deficit_mw", "peak_demand_mw", "peak_net_exchange_india_mw"]

NUM = r"-?[\d,]+(?:\.\d+)?"
DATE_RE = re.compile(r"For Date:?\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*\(\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*\)")
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
    row = {"date": date(int(ay), int(am), int(ad)), "bs_date": f"{by}-{int(bm):02d}-{int(bd):02d}",
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


def parse_listing(html: str) -> list[tuple[str, str]]:
    """(slug, detail_url) in page order, deduped (sidebar repeats posts)."""
    out = {}
    for url, slug in LISTING_RE.findall(html):
        out.setdefault(slug, "https://" + url.split("://", 1)[1])
    return list(out.items())


def parse_detail(html: str) -> str:
    m = DETAIL_PDF_RE.search(html)
    if not m:
        raise ParseError("no NDOR pdf link on detail page")
    return m.group(1).replace(" ", "%20")


def pdf_url(slug: str) -> str | None:
    """Plain slugs map straight to the PDF; odd ones (rev1 etc.) need the detail page."""
    m = SLUG_DATE_RE.search(slug)
    return PDF_URL.format(*m.groups()) if m else None


def discover(known: set[str], max_pages: int = 80) -> list[tuple[str, str]]:
    """Unseen posts, newest first. Stops at the first page with nothing new: ingest runs
    oldest-first, so already-done posts are always the tail of the listing."""
    out = []
    for start in range(1, max_pages + 1, BATCH):
        pages = list(range(start, min(start + BATCH, max_pages + 1)))
        for page, body in zip(pages, fetch_many([LISTING_URL.format(p) for p in pages])):
            if isinstance(body, Exception):
                raise body
            new = [i for i in parse_listing(body.decode("utf-8", "replace")) if i[0] not in known]
            out += new
            print(f"  listing page {page}: {len(new)} new ({len(out)} total)", flush=True)
            if not new:
                return out
    return out


def _download_detail(detail_url: str) -> tuple[str, bytes]:
    url = parse_detail(fetch(detail_url).decode("utf-8", "replace"))
    return url, fetch(url, expect_pdf=True)


def ingest(con, root: Path = Path("data")) -> int:
    raw = Path(root) / "raw" / SOURCE
    raw.mkdir(parents=True, exist_ok=True)
    todo = list(reversed(discover(seen(con, SOURCE))))  # oldest first: newest rev wins
    n = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        direct = [s for s, _ in chunk if pdf_url(s) and not (raw / f"{s}.pdf").exists()]
        got = dict(zip(direct, fetch_many([pdf_url(s) for s in direct], expect_pdf=True)))
        for slug, detail_url in chunk:
            path = raw / f"{slug}.pdf"
            url = pdf_url(slug) or detail_url
            if not path.exists():
                body = got.get(slug)
                try:
                    if body is None or isinstance(body, NotFound):  # odd slug or moved file: detail page
                        url, body = _download_detail(detail_url)
                    elif isinstance(body, Exception):
                        raise body
                except NotFound:
                    log(con, SOURCE, slug, url, "not_found")
                    continue
                except Blocked:
                    raise  # stop the run: more hits only deepen the block
                except (FetchError, ParseError) as e:
                    print(f"  {slug}: {e}")
                    log(con, SOURCE, slug, url, "fetch_error")
                    continue
                path.write_bytes(body)
            try:
                row = parse_pdf(path)
            except ParseError as e:
                print(f"  {slug}: {e}")
                log(con, SOURCE, slug, url, "parse_error")
                continue
            upsert(con, "silver.nea_daily", [{**row, "source": "transd", "source_url": url}], ("date",))
            log(con, SOURCE, slug, url, "ok", hashlib.sha256(path.read_bytes()).hexdigest())
            n += 1
            print(f"  {slug}: {row['date']} qa_ok={row['qa_ok']}", flush=True)
    return n
