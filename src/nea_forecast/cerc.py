"""CERC monthly short-term market report (Excel): Nepal's buying/selling on India's power exchange (IEX
day-ahead / real-time markets) with prices. 'Purchase' = Nepal import, 'Sale' = Nepal export.
Monthly, Excel from 2023, ~6-month lag. Read with DuckDB's excel extension (no openpyxl)."""
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import quote

import duckdb

from nea_forecast.fetch import FetchError, fetch
from nea_forecast.lake import log, seen, upsert

INDEX = "https://www.cercind.gov.in/report_MM-{}.html"
FIRST_YEAR = 2023  # earlier years are PDF-only
MONTHS = {m: i for i, m in enumerate(["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                                       "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], 1)}
MARKETS = {"DAY AHEAD": "DAM", "REAL TIME": "RTM", "TERM AHEAD": "TAM", "GREEN": "GDAM"}


def xlsx_links(html: str) -> list[str]:
    return ["https://www.cercind.gov.in/" + quote(h) for h in re.findall(r'href="([^"]+\.xlsx)"', html, re.I)]


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_rows(rows: list[list], url: str) -> list[dict]:
    """Nepal row under every 'CROSS BORDER TRADE THROUGH <market> ..., <MONTH> <YEAR>' title."""
    out, cur = [], None
    for r in rows:
        cells = [str(c).strip() for c in r if c not in (None, "")]
        if not cells:
            continue
        title = cells[0].upper()
        if "CROSS BORDER TRADE" in title:
            m = re.search(r"([A-Z]+)\s*,?\s*(\d{4})\s*$", title)
            market = next((v for k, v in MARKETS.items() if k in title), None)
            cur = (date(int(m[2]), MONTHS[m[1]], 1), market) if m and m[1] in MONTHS and market else None
        elif cur and len(cells) >= 2 and cells[1].lower() == "nepal":
            v = [_num(x) for x in cells[2:7]] + [None] * 5
            out.append({"month": cur[0], "market": cur[1], "sale_mu": v[0], "purchase_mu": v[1], "net_mu": v[2],
                        "sale_price": v[3], "purchase_price": v[4], "source_url": url})
    return out


def read_xlsx(path: Path) -> list[list]:
    sheets = re.findall(r'<sheet name="([^"]+)"', zipfile.ZipFile(path).read("xl/workbook.xml").decode())
    con = duckdb.connect()
    con.execute("INSTALL excel; LOAD excel")
    rows = []
    for s in sheets:
        try:  # explicit range: merged title rows otherwise hide the other columns
            rows += con.execute("SELECT * FROM read_xlsx(?, sheet=?, header=false, all_varchar=true, range='A1:L80')",
                                [str(path), s]).fetchall()
        except duckdb.Error:
            continue  # chart-only / odd sheets
    return [list(r) for r in rows]


def _download_parse(args: tuple) -> tuple:
    url, path = args
    try:
        if not path.exists():
            path.write_bytes(fetch(url))
        return url, parse_rows(read_xlsx(path), url), None
    except (FetchError, zipfile.BadZipFile) as e:
        return url, None, e


def ingest(con, root: Path = Path("data")) -> int:
    raw = Path(root) / "raw" / "cerc"
    raw.mkdir(parents=True, exist_ok=True)
    done, jobs = seen(con, "cerc"), []
    for year in range(FIRST_YEAR, date.today().year + 1):
        links = [u for u in xlsx_links(fetch(INDEX.format(year)).decode("utf-8", "replace")) if u not in done]
        print(f"  cerc {year}: {len(links)} new report(s)", flush=True)
        jobs += [(u, raw / Path(u).name.replace("%20", "_")) for u in links]
    n = 0
    with ThreadPoolExecutor(6) as ex:  # Excel parsing dominates; downloads share fetch()'s polite per-host pacing
        for url, rows, err in ex.map(_download_parse, jobs):
            if err:
                print(f"    {url}: {err}", flush=True)
                log(con, "cerc", url, url, "fetch_error")
                continue
            n += upsert(con, "silver.iex_cross_border_monthly", rows, ("month", "market"))
            log(con, "cerc", url, url, "ok")
            print(f"    {Path(url).name.replace('%20', ' ')}: " + ", ".join(
                f"{r['month']:%Y-%m} {r['market']} buy {r['purchase_mu']:.1f} sell {r['sale_mu']:.1f} MU" for r in rows), flush=True)
    return n
