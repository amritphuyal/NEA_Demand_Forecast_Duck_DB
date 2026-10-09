import httpx
import pytest

from nea_forecast import fetch as f


@pytest.fixture
def mock(monkeypatch):
    def install(handler):
        monkeypatch.setattr(f, "DELAY", 0)
        monkeypatch.setattr(f, "BROWSER_DELAY", 0)
        monkeypatch.setattr(f, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    return install


def test_is_blocked_f5():
    assert f.is_blocked(b"<html>Request Rejected ... support ID", "text/html")


def test_is_blocked_tspd():
    assert f.is_blocked(b"<script>window.TSPD_101='x'</script>", "text/html")


def test_real_page_with_tspd_script_not_blocked():
    assert not f.is_blocked(b"<html><script>TSPD</script>" + b"x" * 30000, "text/html")


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
    monkeypatch.setattr(f, "_browser_hosts", set())
    monkeypatch.setattr(f, "fetch_browser", lambda url: b"%PDF-1.4 real")
    assert f.fetch("https://x.test/a.pdf", expect_pdf=True) == b"%PDF-1.4 real"


def test_blocked_host_sticks_to_browser(mock, monkeypatch):
    hits = []
    mock(lambda req: hits.append(1) or httpx.Response(200, html="<html>Request Rejected</html>"))
    monkeypatch.setattr(f, "_browser_hosts", set())
    monkeypatch.setattr(f, "fetch_browser", lambda url: b"%PDF-1.4 real")
    f.fetch("https://x.test/a.pdf")
    f.fetch("https://x.test/b.pdf")
    assert len(hits) == 1  # second call skips httpx, no extra flagged hits


def test_fetch_many_browser_batches(monkeypatch):
    monkeypatch.setattr(f, "BROWSER_DELAY", 0)
    monkeypatch.setattr(f, "_batch", 2)
    monkeypatch.setattr(f, "_browser_hosts", {"x.test"})
    calls = []
    def page_fetch(urls, reset=None):
        calls.append(urls)
        return [None if u.endswith("missing.pdf") else b"%PDF-1.4 " + u.encode() for u in urls]
    monkeypatch.setattr(f, "_page_fetch", page_fetch)
    out = f.fetch_many(["http://x.test/a.pdf", "https://x.test/missing.pdf", "https://x.test/c.pdf"], expect_pdf=True)
    assert [len(c) for c in calls] == [2, 1]  # batched
    assert out[0] == b"%PDF-1.4 https://x.test/a.pdf"
    assert isinstance(out[1], f.NotFound) and out[2].startswith(b"%PDF")


def test_fetch_many_backs_off_and_halves_batch(monkeypatch):
    monkeypatch.setattr(f, "BROWSER_DELAY", 0)
    monkeypatch.setattr(f, "BACKOFF", 0)
    monkeypatch.setattr(f, "_batch", 4)
    monkeypatch.setattr(f, "_browser_hosts", {"x.test"})
    rounds = []
    def page_fetch(urls, reset=None):
        if reset:
            rounds.append("reset")
            return []
        rounds.append(len(urls))
        if len(rounds) == 1:  # first round rejected by F5
            return [b"<html>Request Rejected</html>"] * len(urls)
        return [b"%PDF ok"] * len(urls)
    monkeypatch.setattr(f, "_page_fetch", page_fetch)
    out = f.fetch_many([f"https://x.test/{i}.pdf" for i in range(4)], expect_pdf=True)
    assert out == [b"%PDF ok"] * 4
    assert rounds == [4, "reset", 2, 2] and f._batch == 2


def test_fetch_many_gives_up_after_max_blocks(monkeypatch):
    monkeypatch.setattr(f, "BROWSER_DELAY", 0)
    monkeypatch.setattr(f, "BACKOFF", 0)
    monkeypatch.setattr(f, "_batch", 4)
    monkeypatch.setattr(f, "_browser_hosts", {"x.test"})
    monkeypatch.setattr(f, "_page_fetch", lambda urls, reset=None: [] if reset else [f.Blocked("429")] * len(urls))
    with pytest.raises(f.Blocked):
        f.fetch_many(["https://x.test/a.pdf"])


def test_fetch_many_relaunches_after_crash(monkeypatch):
    monkeypatch.setattr(f, "BROWSER_DELAY", 0)
    monkeypatch.setattr(f, "BACKOFF", 0)
    monkeypatch.setattr(f, "_batch", 2)
    monkeypatch.setattr(f, "_browser_hosts", {"x.test"})
    closed, calls = [], []
    monkeypatch.setattr(f, "_close_browser", lambda: closed.append(1))
    def page_fetch(urls, reset=None):
        calls.append(reset)
        if len(calls) == 1:
            raise RuntimeError("Target page, context or browser has been closed")
        return [] if reset else [b"%PDF ok"] * len(urls)
    monkeypatch.setattr(f, "_page_fetch", page_fetch)
    assert f.fetch_many(["https://x.test/a.pdf"], expect_pdf=True) == [b"%PDF ok"]
    assert closed == [1]
