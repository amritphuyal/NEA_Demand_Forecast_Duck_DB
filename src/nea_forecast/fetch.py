"""Polite HTTP fetcher: httpx first, real Chrome (Playwright) only when F5 bot protection blocks us."""
import base64
import os
import random
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36 "
      "nea-demand-forecast/0.1 (+research)")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}
DELAY = 2.0  # seconds between requests to the same host
RETRIES = 3
BROWSER_DELAY = 2.0  # + up to 66% jitter between browser rounds (measured: 20 PDFs/round in ~1 s)
BATCH = int(os.environ.get("NEA_BATCH", 20))  # parallel in-page fetches per browser round
BACKOFF = 30.0  # seconds after a blocked round; doubles each consecutive block
MAX_BLOCKS = 4  # consecutive blocked rounds before giving up (re-run resumes)
BLOCK_MARKERS = (b"Request Rejected", b"blocked by our security policy")
# F5 injects its TSPD script into real pages too; only a small TSPD page is the challenge itself
CHALLENGE_MAX = 20000
# Real Chrome with automation flags masked passes F5 headless too; NEA_HEADED=1 shows the window.
HEADLESS = os.environ.get("NEA_HEADED") != "1"
PROFILE = Path("data/browser-profile")  # persistent cookies across runs


class FetchError(Exception): ...
class NotFound(FetchError): ...
class Blocked(FetchError): ...


_client: httpx.Client | None = None
_last: dict[str, float] = {}
_browser = None  # (playwright, context, page)
_browser_hosts: set[str] = set()  # hosts that blocked httpx: go straight to browser
_batch = BATCH  # halves after each block, stays reduced for the rest of the run


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True)
    return _client


def _throttle(host: str) -> None:
    wait = _last.get(host, 0) + DELAY - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.monotonic()


def is_blocked(body: bytes, content_type: str) -> bool:
    if body.startswith(b"%PDF") or "html" not in content_type:
        return False
    head = body[:CHALLENGE_MAX]
    return any(m in head for m in BLOCK_MARKERS) or (len(body) < CHALLENGE_MAX and b"TSPD" in body)


def _https(url: str) -> str:
    return "https://" + url[7:] if url.startswith("http://") else url


def fetch(url: str, expect_pdf: bool = False) -> bytes:
    url = _https(url)
    host = urlsplit(url).netloc
    if host in _browser_hosts:
        return _check(url, _browser_fetch(host, url), expect_pdf)
    for attempt in range(RETRIES):
        _throttle(host)
        try:
            r = _get_client().get(url)
        except httpx.TransportError as e:
            if attempt == RETRIES - 1:
                raise FetchError(f"{url}: {e}") from e
            time.sleep(2 ** attempt * DELAY)
            continue
        if r.status_code == 404:
            raise NotFound(url)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == RETRIES - 1:
                raise FetchError(f"{url}: HTTP {r.status_code}")
            time.sleep(2 ** attempt * DELAY)
            continue
        body = r.content
        if is_blocked(body, r.headers.get("content-type", "")):
            _browser_hosts.add(host)
            return _check(url, _browser_fetch(host, url), expect_pdf)
        if r.status_code >= 400:
            raise FetchError(f"{url}: HTTP {r.status_code}")
        return _check(url, body, expect_pdf)
    raise FetchError(url)


def _browser_throttle(host: str) -> None:
    _last[host] = _last.get(host, 0) + BROWSER_DELAY - DELAY + random.uniform(0, BROWSER_DELAY * 0.66)
    _throttle(host)


def _browser_fetch(host: str, url: str) -> bytes:
    _browser_throttle(host)
    return fetch_browser(url)


def _check(url: str, body: bytes, expect_pdf: bool) -> bytes:
    if is_blocked(body, "text/html"):
        raise Blocked(url)
    if expect_pdf and not body.startswith(b"%PDF"):
        raise FetchError(f"{url}: not a PDF")
    return body


def _safe(fn, *args):
    try:
        return fn(*args)
    except FetchError as e:
        return e


def fetch_many(urls: list[str], expect_pdf: bool = False) -> list[bytes | FetchError]:
    """Same as fetch() per url, errors returned in place. Browser hosts: _batch parallel in-page
    fetches per throttled round. Blocked round -> back off, halve batch, re-solve challenge, retry."""
    global _batch
    out, i, blocks = [], 0, 0
    while i < len(urls):
        chunk = [_https(u) for u in urls[i:i + _batch]]
        host = urlsplit(chunk[0]).netloc
        if host not in _browser_hosts:  # first call discovers the block; httpx hosts aren't the bottleneck
            out += [_safe(fetch, u, expect_pdf) for u in chunk]
            i += len(chunk)
            continue
        _browser_throttle(host)
        try:
            res = [r if isinstance(r, FetchError) else NotFound(u) if r is None else _safe(_check, u, r, expect_pdf)
                   for u, r in zip(chunk, _page_fetch(chunk))]
        except Exception as e:  # page/browser closed or crashed: relaunch Chrome, treat like a block
            _close_browser()
            res = [Blocked(f"{host}: {e}")]
        if any(isinstance(r, Blocked) for r in res):
            blocks += 1
            if blocks > MAX_BLOCKS:
                raise Blocked(f"{host}: still blocked after {MAX_BLOCKS} backoffs")
            wait = BACKOFF * 2 ** (blocks - 1)
            _batch = max(1, _batch // 2)
            print(f"  {host} blocked: backoff {wait:.0f}s, batch -> {_batch}", flush=True)
            time.sleep(wait)
            _page_fetch([], reset=host)
            continue
        blocks = 0
        out += res
        i += len(chunk)
    return out


def _close_browser() -> None:
    global _browser
    if _browser:
        try:
            _browser[1].close()
            _browser[0].stop()
        except Exception:
            pass  # already dead
    _browser = None


def _page():
    global _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=HEADLESS,
            # F5 rejects pages when navigator.webdriver / automation flags are visible
            ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"])
        _browser = (pw, ctx, ctx.pages[0] if ctx.pages else ctx.new_page())
    return _browser[2]


def _page_fetch(urls: list[str], reset: str | None = None) -> list[bytes | None | FetchError]:
    """Parallel fetch() inside the page (same origin), so F5's patched fetch attaches its tokens.
    Per url: bytes, None (404), or Blocked (429/5xx) / FetchError (network). reset=host re-solves
    the challenge with a real navigation."""
    page = _page()
    host = reset or urlsplit(urls[0]).netloc
    if reset or not page.url.startswith(f"https://{host}"):
        page.goto(f"https://{host}/", wait_until="networkidle", timeout=90000)
    if not urls:
        return []
    datas = page.evaluate("""async urls => Promise.all(urls.map(async u => {
        try {
            const r = await fetch(u, {credentials: 'include'});
            if (r.status === 404) return null;
            if (r.status === 429 || r.status >= 500) return 'BLOCKED:' + r.status;
            const blob = await r.blob();  // base64 data URL: cheap transfer even for 50 MB reports
            return await new Promise(ok => { const f = new FileReader(); f.onload = () => ok(f.result); f.readAsDataURL(blob); });
        } catch (e) { return 'ERR:' + e; }
    }))""", urls)
    out = []
    for u, d in zip(urls, datas):
        if d is None or d.startswith("data:"):
            out.append(d and base64.b64decode(d.split(",", 1)[1]))
        else:
            out.append(Blocked(f"{u}: {d}") if d.startswith("BLOCKED") else FetchError(f"{u}: {d}"))
    return out


def fetch_browser(url: str) -> bytes:
    """HTML: real page navigation (runs F5's JS check). Binary: in-page fetch()."""
    if not url.lower().endswith(".pdf"):
        page = _page()
        page.goto(url, wait_until="networkidle", timeout=90000)
        for _ in range(20):  # challenge page reloads itself once solved
            html = page.content().encode()
            if not is_blocked(html, "text/html"):
                break
            page.wait_for_timeout(1000)
        return html
    body = _page_fetch([url])[0]
    if body is None:
        raise NotFound(url)
    if isinstance(body, FetchError):
        raise body
    return body
