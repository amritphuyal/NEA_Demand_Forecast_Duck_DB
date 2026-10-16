"""NEA monthly / yearly / annual reports: archive PDFs + Markdown copies. Tables parsed in Phase 2."""
import hashlib
import re
from pathlib import Path

import pymupdf4llm

from nea_forecast import load_sources
from nea_forecast.fetch import Blocked, FetchError, NotFound, fetch
from nea_forecast.lake import log, seen, upsert

# source id -> (raw sub-folder, slug keyword that filters out sidebar/other posts)
CATEGORIES = {
    "nea_monthly_reports": ("monthly", "monthly"),
    "nea_yearly_reports": ("yearly", "yearly"),
    "nea_annual_reports": ("annual", "annual-report"),
}
PDF_RE = re.compile(r'href="([^"]+\.pdf)"', re.I)


def parse_doc_listing(html: str, keyword: str) -> list[tuple[str, str]]:
    pat = re.compile(rf'href="(https?://[^"/]+/detail/([\w-]*{re.escape(keyword)}[\w-]*))"')
    out = {}
    for url, slug in pat.findall(html):
        out.setdefault(slug, "https://" + url.split("://", 1)[1])
    return list(out.items())


def parse_pdf_links(html: str) -> list[str]:
    return list(dict.fromkeys(u.replace(" ", "%20") for u in PDF_RE.findall(html)))


def ingest_category(con, root: Path, folder: str, listing_url: str, keyword: str, max_pages: int = 20) -> int:
    source = f"nea_docs_{folder}"
    known, todo = seen(con, source), []
    for page in range(1, max_pages + 1):
        queued = known | {s for s, _ in todo}  # some listings ignore ?page= and repeat page 1
        new = [i for i in parse_doc_listing(fetch(listing_url.format(page=page)).decode("utf-8", "replace"), keyword)
               if i[0] not in queued]
        todo += new
        if not new:
            break
    raw = Path(root) / "raw" / "nea_docs" / folder
    raw.mkdir(parents=True, exist_ok=True)
    n = 0
    for slug, detail_url in todo:
        try:
            links = parse_pdf_links(fetch(detail_url).decode("utf-8", "replace"))
            rows = []
            for i, url in enumerate(links):
                key = slug if i == 0 else f"{slug}-{i}"
                pdf = raw / f"{key}.pdf"
                if not pdf.exists():
                    pdf.write_bytes(fetch(url, expect_pdf=True))
                md = pdf.with_suffix(".md")
                md.write_text(pymupdf4llm.to_markdown(str(pdf)))
                rows.append({"key": key, "category": folder, "title": slug, "published": None,
                             "pdf_path": str(pdf), "md_path": str(md), "source_url": url})
        except Blocked:
            raise
        except (FetchError, ValueError, RuntimeError) as e:  # pymupdf raises RuntimeError on broken PDFs
            print(f"  {slug}: {e}")
            log(con, source, slug, detail_url, "not_found" if isinstance(e, NotFound) else "fetch_error")
            continue
        upsert(con, "silver.nea_document", rows, ("key",))
        log(con, source, slug, detail_url, "ok", hashlib.sha256("".join(r["source_url"] for r in rows).encode()).hexdigest())
        n += 1
        print(f"  {folder}/{slug}: {len(rows)} pdf")
    return n


def ingest(con, root: Path = Path("data")) -> int:
    src = load_sources()
    return sum(ingest_category(con, root, folder, src[sid]["urls"]["listing"], kw)
               for sid, (folder, kw) in CATEGORIES.items())
