from pathlib import Path

from nea_forecast import nea_docs
from nea_forecast.lake import connect

PDF = (Path(__file__).parent / "fixtures" / "NDOR_2081_09_27.pdf").read_bytes()
LISTING = """
<a href="https://nea.org.np/detail/annual-report-20252026">Annual Report 2025/2026</a>
<a href="https://nea.org.np/detail/annual-report-20252026">dup</a>
<a href="https://nea.org.np/detail/annual-report-20242025">Annual Report 2024/2025</a>
<a href="https://nea.org.np/detail/some-notice-about-tender">sidebar noise</a>
"""
DETAIL = '<a href="https://nea.org.np/uploads/annual/AR 2025.pdf">Open PDF</a><a href="https://nea.org.np/uploads/annual/AR 2025.pdf">Download</a>'


def test_parse_doc_listing_filters_and_dedupes():
    assert nea_docs.parse_doc_listing(LISTING, "annual-report") == [
        ("annual-report-20252026", "https://nea.org.np/detail/annual-report-20252026"),
        ("annual-report-20242025", "https://nea.org.np/detail/annual-report-20242025"),
    ]


def test_parse_pdf_links_dedupes_and_encodes():
    assert nea_docs.parse_pdf_links(DETAIL) == ["https://nea.org.np/uploads/annual/AR%202025.pdf"]


def test_ingest_category_writes_pdf_md_and_skips_known(tmp_path, monkeypatch):
    pages = {"https://x.test/list?page=1": LISTING, "https://x.test/list?page=2": ""}
    def fake_fetch(url, expect_pdf=False):
        if url in pages:
            return pages[url].encode()
        return PDF if url.endswith(".pdf") else DETAIL.encode()
    monkeypatch.setattr(nea_docs, "fetch", fake_fetch)
    con = connect(tmp_path)
    assert nea_docs.ingest_category(con, tmp_path, "annual", "https://x.test/list?page={page}", "annual-report") == 2
    assert nea_docs.ingest_category(con, tmp_path, "annual", "https://x.test/list?page={page}", "annual-report") == 0
    md = tmp_path / "raw/nea_docs/annual/annual-report-20252026.md"
    assert "Daily Operational Report" in md.read_text()
    assert con.execute("select count(*) from silver.nea_document").fetchone()[0] == 2
