"""India's customs trade stats (Ministry of Commerce TradeStat), HS 27160000 'Electrical Energy', Nepal row.
India's export to Nepal = Nepal import; India's import from Nepal = Nepal export. Monthly, 2018 -> ~2 months
ago: fills the Jan 2025+ gap left by NEA's daily reports. Customs booking months are lumpy, so the
Indian-FY-to-date total (Apr..month) is stored too; quantity unit TKW = MWh."""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx

from nea_forecast.fetch import HEADERS
from nea_forecast.lake import upsert

BASE = "https://tradestat.commerce.gov.in/meidb/commodity_wise_all_countries_{}"
# direction -> (page, form field prefix)
PAGES = {"nepal_import": ("export", "cwacex"), "nepal_export": ("import", "cwacim")}
MEASURES = {"mwh": "2", "inr_crore": "3"}
START = date(2018, 1, 1)
RECHECK_DAYS = 120  # India revises recent months ("R")
WORKERS = 6  # parallel queries; each worker has its own session (form tokens are per session, single use)
MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _today() -> date:
    return date.today()


def _cells(row_html: str) -> list[str]:
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)]


def parse(html: str, direction: str, measure: str) -> list[dict]:
    """Two monthly points (same month, previous and current year) from one result table."""
    rows = [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)]
    header = next((r for r in rows if "Country" in r), None)
    months = [date(int(m[2]), MON[m[1]], 1) for c in (header or []) if (m := re.match(r"([A-Z][a-z]{2})-(\d{4})", c))]
    if len(months) < 2 or not any(r and r[0].isdigit() for r in rows):
        return []  # month not published yet
    nep = next((r for r in rows if "NEPAL" in r), None)
    nums = [float(c.replace(",", "")) for c in nep[2:] if re.fullmatch(r"-?[\d,.]+", c)] if nep else []
    # Nepal row: month(prev), month(cur), growth, cum(prev), cum(cur), growth
    vals = (nums[0], nums[1], nums[3], nums[4]) if len(nums) >= 5 else (0, 0, 0, 0)
    return [{"month": months[k], "direction": direction, "measure": measure,
             "month_value": vals[k], "fy_cum_value": vals[k + 2]} for k in (0, 1)]


def months_to_query(stored: set[date], today: date, start: date | None = None) -> list[date]:
    """Months missing from the store, plus recent ones (revisions); never future months."""
    out, m = [], start or START
    while m <= today:
        if m not in stored or m >= today - timedelta(days=RECHECK_DAYS):
            out.append(m)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out


def query(client: httpx.Client, direction: str, measure: str, m: date) -> str:
    page, p = PAGES[direction]
    url = BASE.format(page)
    for attempt in range(3):
        try:
            token = re.search(r'name="_token"\s+value="([^"]+)"', client.get(url).text).group(1)  # one POST per token
            r = client.post(url, data={"_token": token, f"{p}HSCODE": "27160000", f"{p}Month": str(m.month),
                                       f"{p}Year": str(m.year), f"{p}ReportVal": MEASURES[measure], f"{p}ReportYear": "1"})
            r.raise_for_status()
            return r.text
        except (httpx.HTTPError, AttributeError):
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


_local = threading.local()


def _query_threaded(args: tuple) -> tuple:
    direction, measure, m = args
    if not hasattr(_local, "client"):
        _local.client = httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True)
    try:
        return args, query(_local.client, direction, measure, m), None
    except Exception as e:  # reported per month, run continues
        return args, None, e


def ingest(con, root: Path = Path("data")) -> int:
    raw = Path(root) / "raw" / "india_trade"
    raw.mkdir(parents=True, exist_ok=True)
    jobs = []
    for direction in PAGES:
        for measure in MEASURES:
            stored = {r[0] for r in con.execute("SELECT month FROM silver.india_trade_monthly WHERE direction = ? "
                                                "AND measure = ?", [direction, measure]).fetchall()}
            todo = months_to_query(stored, _today())
            # a query for month M+1y also returns M (previous-year column): skip M when M+1y is queried anyway
            recent, planned = _today() - timedelta(days=RECHECK_DAYS), set(todo)
            todo = [m for m in todo if m >= recent or date(m.year + 1, m.month, 1) not in planned]
            print(f"  india trade {direction} {measure}: {len(todo)} quer(ies)", flush=True)
            jobs += [(direction, measure, m) for m in todo]
    n, done, rows = 0, 0, []
    with ThreadPoolExecutor(WORKERS) as ex:
        for (direction, measure, m), html, err in ex.map(_query_threaded, jobs):
            done += 1
            if err:
                print(f"    {direction} {measure} {m:%Y-%m}: FAILED {type(err).__name__}: {err}", flush=True)
                continue
            (raw / f"{direction}_{measure}_{m:%Y_%m}.html").write_text(html)
            got = parse(html, direction, measure)
            rows += got
            if got:
                print(f"    [{done}/{len(jobs)}] {direction} {measure} {m:%Y-%m}: {got[-1]['month_value']:,.0f} "
                      f"(FY-to-date {got[-1]['fy_cum_value']:,.0f})", flush=True)
            else:
                print(f"    [{done}/{len(jobs)}] {direction} {measure} {m:%Y-%m}: not published yet", flush=True)
            if len(rows) >= 100:  # batch lake writes (main thread only)
                n += upsert(con, "silver.india_trade_monthly", rows, ("month", "direction", "measure"))
                rows = []
    n += upsert(con, "silver.india_trade_monthly", rows, ("month", "direction", "measure"))
    return n
