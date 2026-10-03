"""Polite HTTP fetcher: httpx first, headless Chromium only when F5 bot protection blocks us."""
import time
from urllib.parse import urlsplit

import httpx

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36 "
      "nea-demand-forecast/0.1 (+research)")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}
DELAY = 2.0  # seconds between requests to the same host
RETRIES = 3
BLOCK_MARKERS = (b"Request Rejected", b"TSPD", b"blocked by our security policy")


class FetchError(Exception): ...
class NotFound(FetchError): ...
class Blocked(FetchError): ...


_client: httpx.Client | None = None
_last: dict[str, float] = {}
_browser = None  # (playwright, context, warmed hosts)


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
    head = body[:20000]
    return any(m in head for m in BLOCK_MARKERS)


def fetch(url: str, expect_pdf: bool = False) -> bytes:
    if url.startswith("http://"):
        url = "https://" + url[7:]
    host = urlsplit(url).netloc
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
            body = fetch_browser(url)
            if is_blocked(body, "text/html"):
                raise Blocked(url)
        elif r.status_code >= 400:
            raise FetchError(f"{url}: HTTP {r.status_code}")
        if expect_pdf and not body.startswith(b"%PDF"):
            raise FetchError(f"{url}: not a PDF")
        return body
    raise FetchError(url)


def fetch_browser(url: str) -> bytes:
    """Pass the JS challenge once per host with a real page load, then reuse its cookies."""
    global _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        ctx = pw.chromium.launch().new_context(user_agent=UA)
        _browser = (pw, ctx, set())
    _, ctx, warmed = _browser
    parts = urlsplit(url)
    if parts.netloc not in warmed:
        page = ctx.new_page()
        page.goto(f"{parts.scheme}://{parts.netloc}/", wait_until="networkidle", timeout=60000)
        page.close()
        warmed.add(parts.netloc)
    r = ctx.request.get(url, timeout=60000)
    if r.status == 404:
        raise NotFound(url)
    return r.body()
