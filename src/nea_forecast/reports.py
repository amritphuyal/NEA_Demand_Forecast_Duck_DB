"""Pull month-wise tables + annual LDC summary out of NEA report Markdown (pymupdf4llm output).

Generic on purpose: any Markdown table whose header row or first column names Nepali months becomes
long rows (doc, fy, table, title, series, bs_month, value). Picking series (IMPORT, PEAK DEMAND, ...)
happens in SQL. Charts (e.g. Kulekhani reservoir level) are images: not extractable without OCR.
"""
import re
from pathlib import Path

from nea_forecast.lake import upsert

# BS month number: Baishakh = 1 .. Chaitra = 12 (fiscal year starts Shrawan = 4)
MONTHS = {
    1: ("baishakh", "baisakh", "baisak", "baishak"), 2: ("jestha", "jeth"), 3: ("ashadh", "ashar", "asar", "ashad", "asadh"),
    4: ("shrawan", "srawan", "saun"), 5: ("bhadra", "bhadau"), 6: ("ashwin", "aswin", "asoj"), 7: ("kartik",),
    8: ("mangsir", "mangshir", "marga"), 9: ("poush", "paush", "push"), 10: ("magh",), 11: ("falgun", "phalgun"),
    12: ("chaitra", "chait"),
}
NUM_RE = re.compile(r"^-?[\d,]*\.?\d+$")
LDC_RE = re.compile(r"(annual\s+(?:system|national)\s+(?:peak|energy)\s+demand)\W*\|\W*([\d,.]+)\s*(MW|GWh)"
                    r"(?:\W*\|\W*(\d{4}-\d{2}-\d{2}))?", re.I)


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"~~|\*\*|</?u>|</?mark>|<br>", " ", cell)).strip()


def month_of(cell: str) -> int | None:
    c = cell.lower().strip(" .")
    for n, names in MONTHS.items():
        if any(c == x or c.startswith(x + " ") for x in names):
            return n
    return None


def num(cell: str) -> float | None:
    c = cell.replace(" ", "")
    return float(c.replace(",", "")) if NUM_RE.match(c) else None


def fy_from_key(key: str) -> str | None:
    """FY (BS) a report covers, from its slug: 20252026 / 202526 / 2025 (published -> previous FY) / 207980."""
    m = re.search(r"(20\d\d)(\d{2}|\d{4})?(?!\d)", key)
    if not m:
        return None
    y = int(m.group(1))
    if y >= 2070:  # already BS, e.g. 207980
        return f"{y}/{(y + 1) % 100:02d}"
    start = y if m.group(2) else y - 1
    return f"{start + 57}/{(start + 58) % 100:02d}"


def _tables(md: str):
    """(title, rows of cleaned cells) for each Markdown table; title = nearest heading-ish line above."""
    lines, i = md.splitlines(), 0
    while i < len(lines):
        if not lines[i].startswith("|"):
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].startswith("|"):
            j += 1
        above = [clean(x).strip("# ") for x in lines[max(0, i - 6):i] if clean(x).strip("# ")]
        rows = [[clean(c) for c in re.sub(r"^\||\|$", "", ln.strip()).split("|")] for ln in lines[i:j]  # keep empty edge cells
                if not re.fullmatch(r"[|\-\s:]+", ln)]
        yield (above[-1][:200] if above else ""), rows
        i = j


def month_tables(md: str, doc_key: str, fy: str | None) -> list[dict]:
    out = []
    for t, (title, rows) in enumerate(_tables(md)):
        # months across a header row
        hdr = next((r for r in rows if sum(month_of(c) is not None for c in r) >= 10), None)
        if hdr:
            cols = {k: month_of(c) for k, c in enumerate(hdr) if month_of(c)}
            for r in rows:
                label = next((c for c in r if c and num(c) is None and month_of(c) is None), "")
                for k, m in cols.items():
                    v = num(r[k]) if k < len(r) and label else None
                    if v is not None:
                        out.append({"doc_key": doc_key, "fy": fy, "table_no": t, "title": title,
                                    "series": label, "bs_month": m, "value": v})
            continue
        # months down the first column
        month_rows = [r for r in rows if r and month_of(r[0])]
        if len(month_rows) >= 2 and rows:
            head = rows[0]
            for r in month_rows:
                for k in range(1, min(len(r), len(head))):
                    v = num(r[k])
                    if v is not None and head[k]:
                        out.append({"doc_key": doc_key, "fy": fy, "table_no": t, "title": title,
                                    "series": head[k], "bs_month": month_of(r[0]), "value": v})
    return out


def ldc_summary(md: str, doc_key: str, fy: str | None) -> list[dict]:
    return [{"doc_key": doc_key, "fy": fy, "metric": re.sub(r"\s+", " ", m[1]).lower(),
             "value": float(m[2].replace(",", "")), "unit": m[3], "date_bs": m[4]}
            for m in LDC_RE.finditer(clean(md).replace("| |", "|"))]


def ingest(con, root: Path = Path("data")) -> int:
    """Re-parse every report Markdown (seconds; idempotent)."""
    n = 0
    for md_path in sorted((Path(root) / "raw" / "nea_docs").glob("*/*.md")):
        key, md = md_path.stem, md_path.read_text()
        fy = fy_from_key(key)
        n += upsert(con, "silver.report_monthly", month_tables(md, key, fy), ("doc_key", "table_no", "series", "bs_month"))
        upsert(con, "silver.report_annual", ldc_summary(md, key, fy), ("doc_key", "metric"))
    return n


def search(pattern: str, root: Path = Path("data")) -> None:
    rx = re.compile(pattern, re.I)
    for md_path in sorted((Path(root) / "raw" / "nea_docs").glob("*/*.md")):
        for i, line in enumerate(md_path.read_text().splitlines(), 1):
            if rx.search(line):
                print(f"{md_path}:{i}: {clean(line)[:200]}")
