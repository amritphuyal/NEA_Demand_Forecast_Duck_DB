"""OCR for the few NEA balance tables printed as images (RapidOCR: PaddleOCR models on ONNX, CPU).

Picked over OnnxTR (same digits, ~10x slower: 313 s vs 29 s per page) and Tesseract (needs a system
package, weaker on tables). OCR output is never trusted blindly: a month is kept only if the table's
own arithmetic holds (sources ~ system demand, sources ~ national + export, national + export = system;
whichever identities the table obeys in most months must hold in that month).
"""
import json
import re
import time
from pathlib import Path

import pymupdf

from nea_forecast.lake import log, seen, upsert

TITLE_RE = re.compile(r"(capacity|energy)\s+balance\s*(?:\((?:mw|gwh)\)|in\s+(?:mw|gwh))?\s*(?:in|of)\s+fy", re.I)
FY_RE = re.compile(r"FY\s*(\d{4})/(\d{2})")
FY_MONTHS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]  # table columns run Shrawan .. Ashadh (+ average)
# OCR sometimes drops the space between decimals: "1754.081814.65" -> 1754.08, 1814.65
NUM_RE = re.compile(r"\d[\d,]*\.\d{2}|\d[\d,]*")  # NEA tables use 0 or 2 decimals
SOURCES = ["IPP", "NEA SUBSIDIARY", "NEA ROR & PROR", "IMPORT", "STORAGE", "SOLAR", "THERMAL", "INTERRUPTION"]
LABELS = [("NEA SUBSIDIARY", r"SUBSID"), ("NEA ROR & PROR", r"ROR"), ("NEA SUBSIDIARY", r"^NEA$"), ("IPP", r"\bIPP"), ("IMPORT", r"IMPORT"),
          ("STORAGE", r"STORAGE"), ("SOLAR", r"SOLAR"), ("THERMAL", r"THERMAL"), ("INTERRUPTION", r"INTERRUP"),
          ("MONTHLY NATIONAL {} DEMAND", r"NATIONAL"), ("MONTHLY SYSTEM {} DEMAND", r"SYSTEM"), ("EXPORT", r"EXPORT")]


def find_pages(pdf: Path) -> list[tuple[int, str]]:
    """(page, title) of titled balance tables. OCR'd even when text exists: some reports' text layer
    jumbles the columns (FY 2077/78, 2078/79); the arithmetic check decides what is kept."""
    out = []
    for page in pymupdf.open(pdf):
        text = page.get_text()
        m = TITLE_RE.search(text)
        if m:
            out.append((page.number, re.sub(r"\s+", " ", text[m.start():m.start() + 60]).strip()))
    return out


def run_ocr(pdf: Path, page_no: int, cache: Path) -> list[tuple]:
    """(x, y, height, text) boxes; cached as JSON because OCR is ~30 s per page."""
    f = cache / f"{pdf.stem}_p{page_no}.json"
    if f.exists():
        return [tuple(b) for b in json.loads(f.read_text())]
    from rapidocr_onnxruntime import RapidOCR  # lazy: model load is slow
    img = pymupdf.open(pdf)[page_no].get_pixmap(dpi=200).tobytes("png")
    res, _ = RapidOCR()(img)
    out = [(b[0][0], (b[0][1] + b[2][1]) / 2, b[2][1] - b[0][1], t) for b, t, _ in (res or [])]
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def rows(boxes: list[tuple]) -> list[list[str]]:
    """Group boxes into text rows: a new row starts when y jumps by more than ~0.6 box height."""
    out, cur, cur_y = [], [], None
    for x, y, h, t in sorted(boxes, key=lambda b: b[1]):
        if cur and y - cur_y > 0.6 * h:
            out.append([tok for _, tok in sorted(cur)])
            cur = []
        if not cur:
            cur_y = y
        cur += [(x + i * 1e-3, tok) for i, tok in enumerate(t.split())]
    if cur:
        out.append([tok for _, tok in sorted(cur)])
    return out


def balance(text_rows: list[list[str]], unit: str) -> tuple[dict[str, list[float]], list[bool]]:
    """Series (12 FY-ordered months) by canonical label + per-month validity. Rows whose label OCR lost
    are named by arithmetic: the one equal to the sum of sources is system demand, the other national."""
    kind = "PEAK" if unit == "MW" else "ENERGY"
    nat_k, sys_k = f"MONTHLY NATIONAL {kind} DEMAND", f"MONTHLY SYSTEM {kind} DEMAND"
    tol = 5 if unit == "MW" else 2
    series, unlabeled = {}, []
    for r in text_rows:
        r = [p for t in r for p in re.split(r"(?<=[^\d\s,.])(?=\d)", t)]  # "NEAROR&PROR290.92" -> label, number
        nums = [float(x.replace(",", "")) for t in r if t[:1].isdigit() for x in NUM_RE.findall(t)]
        label = " ".join(t for t in r if not t[:1].isdigit()).upper()
        if len(nums) < 12:
            continue
        name = next((n.format(kind) for n, rx in LABELS if re.search(rx, label)), None)
        if name:
            series.setdefault(name, nums[:12])
        else:
            unlabeled.append(nums[:12])
    src = [s for s in SOURCES if s in series]
    src_sum = [sum(series[s][i] for s in src) for i in range(12)]
    for vals in unlabeled:
        is_sys = sum(abs(vals[i] - src_sum[i]) <= tol for i in range(12)) >= 6
        key = sys_k if is_sys and sys_k not in series else nat_k if nat_k not in series else None
        if key:
            series[key] = vals
    nat, exp, sys_ = series.get(nat_k), series.get("EXPORT"), series.get(sys_k)
    # NEA rounds GWh source rows: allow 1.5% there; demand rows themselves add up exactly
    src_tol = (lambda v: tol) if unit == "MW" else (lambda v: max(tol, 0.015 * v))
    checks = []  # identities this table actually obeys (most months); each then must hold every month
    if src and sys_:
        checks.append(lambda i: abs(src_sum[i] - sys_[i]) <= src_tol(sys_[i]))
    if src and nat and exp:
        checks.append(lambda i: abs(src_sum[i] - nat[i] - exp[i]) <= src_tol(nat[i] + exp[i]))
    if sys_ and nat and exp:
        checks.append(lambda i: abs(nat[i] + exp[i] - sys_[i]) <= tol)
    checks = [c for c in checks if sum(map(c, range(12))) >= 9] or checks[:1]
    ok = [bool(checks) and all(c(i) for c in checks) for i in range(12)]
    return series, ok


def records(series: dict, ok: list[bool], doc_key: str, fy: str, page_no: int, title: str) -> list[dict]:
    return [{"doc_key": doc_key, "fy": fy, "table_no": 10000 + page_no, "title": f"OCR: {title}",
             "series": name, "bs_month": FY_MONTHS[i], "value": vals[i]}
            for name, vals in series.items() for i in range(12) if ok[i]]


def ingest(con, root: Path = Path("data")) -> int:
    from nea_forecast.reports import fy_from_key
    n, cache = 0, Path(root) / "raw" / "nea_docs" / "ocr"
    done = seen(con, "ocr")  # to redo after changing OCR logic: DELETE FROM bronze.ingest_log WHERE source='ocr'
    pdfs = [p for p in sorted((Path(root) / "raw" / "nea_docs" / "annual").glob("*.pdf")) if p.stem not in done]
    print(f"  ocr: {len(pdfs)} new report(s) to scan, {len(done)} already done", flush=True)
    for pdf in pdfs:
        for page_no, title in find_pages(pdf):
            unit = "GWh" if title.lower().startswith("energy") else "MW"  # NEA mislabels one energy table "(MW)"
            m = FY_RE.search(title)
            fy = f"{m[1]}/{m[2]}" if m else fy_from_key(pdf.stem)
            t = time.time()
            cached = (cache / f"{pdf.stem}_p{page_no}.json").exists()
            series, ok = balance(rows(run_ocr(pdf, page_no, cache)), unit)
            recs = records(series, ok, pdf.stem, fy, page_no, title)
            upsert(con, "silver.report_monthly", recs, ("doc_key", "table_no", "series", "bs_month"))
            n += len(recs)
            bad = [FY_MONTHS[i] for i in range(12) if not ok[i]]
            print(f"  ocr {pdf.stem} p{page_no} FY {fy} {unit}: {len(series)} series, {sum(ok)}/12 months valid"
                  f"{f' (rejected BS months {bad})' if bad else ''}, {len(recs)} rows, "
                  f"{'cached' if cached else f'{time.time() - t:.0f}s'}", flush=True)
        log(con, "ocr", pdf.stem, str(pdf), "ok")
    return n
