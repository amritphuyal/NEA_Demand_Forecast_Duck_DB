import httpx
import pytest

from nea_forecast import fetch as f


@pytest.fixture
def mock(monkeypatch):
    def install(handler):
        monkeypatch.setattr(f, "DELAY", 0)
        monkeypatch.setattr(f, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    return install


def test_is_blocked_f5():
    assert f.is_blocked(b"<html>Request Rejected ... support ID", "text/html")


def test_is_blocked_tspd():
    assert f.is_blocked(b"<script>window.TSPD_101='x'</script>", "text/html")


def test_pdf_not_blocked():
    assert not f.is_blocked(b"%PDF-1.7 ... Request Rejected", "application/pdf")


def test_fetch_rejects_non_pdf(mock):
    mock(lambda req: httpx.Response(200, html="<html>ok</html>"))
    with pytest.raises(f.FetchError):
        f.fetch("https://x.test/a.pdf", expect_pdf=True)


def test_fetch_404(mock):
    mock(lambda req: httpx.Response(404))
    with pytest.raises(f.NotFound):
        f.fetch("https://x.test/missing.pdf")


def test_fetch_forces_https(mock):
    seen = []
    mock(lambda req: seen.append(str(req.url)) or httpx.Response(200, content=b"%PDF-1.4"))
    assert f.fetch("http://x.test/a.pdf", expect_pdf=True) == b"%PDF-1.4"
    assert seen == ["https://x.test/a.pdf"]


def test_blocked_falls_back_to_browser(mock, monkeypatch):
    mock(lambda req: httpx.Response(200, html="<html>Request Rejected</html>"))
    monkeypatch.setattr(f, "fetch_browser", lambda url: b"%PDF-1.4 real")
    assert f.fetch("https://x.test/a.pdf", expect_pdf=True) == b"%PDF-1.4 real"
