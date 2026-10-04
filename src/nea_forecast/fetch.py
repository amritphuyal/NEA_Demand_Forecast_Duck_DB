"""Polite HTTP fetcher: httpx first, real Chrome (Playwright) only when F5 bot protection blocks us."""
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
BROWSER_DELAY = 6.0  # + up to 66% jitter; F5 flags fast navigation
BLOCK_MARKERS = (b"Request Rejected", b"blocked by our security policy")
# F5 injects its TSPD script into real pages too; only a small TSPD page is the challenge itself
CHALLENGE_MAX = 20000
# Headed real Chrome passes F5 fingerprinting; NEA_HEADLESS=1 for unattended cron (may get blocked).
HEADLESS = os.environ.get("NEA_HEADLESS") == "1"
PROFILE = Path("data/browser-profile")  # persistent cookies across runs


class FetchError(Exception): ...
class NotFound(FetchError): ...
class Blocked(FetchError): ...


_client: httpx.Client | None = None
_last: dict[str, float] = {}
_browser = None  # (playwright, context, page)
_browser_hosts: set[str] = set()  # hosts that blocked httpx: go straight to browser


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


def fetch(url: str, expect_pdf: bool = False) -> bytes:
    if url.startswith("http://"):
        url = "https://" + url[7:]
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


def _browser_fetch(host: str, url: str) -> bytes:
    _last[host] = _last.get(host, 0) + BROWSER_DELAY - DELAY + random.uniform(0, BROWSER_DELAY * 0.66)
    _throttle(host)
    return fetch_browser(url)


def _check(url: str, body: bytes, expect_pdf: bool) -> bytes:
    if is_blocked(body, "text/html"):
        raise Blocked(url)
    if expect_pdf and not body.startswith(b"%PDF"):
        raise FetchError(f"{url}: not a PDF")
    return body


def fetch_browser(url: str) -> bytes:
    """HTML: real page navigation (runs F5's JS check). Binary: in-page fetch() from the same
    origin, so F5's patched fetch attaches its tokens."""
    global _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=HEADLESS,
            # F5 rejects pages when navigator.webdriver / automation flags are visible
            ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"])
        _browser = (pw, ctx, ctx.pages[0] if ctx.pages else ctx.new_page())
    page = _browser[2]
    parts = urlsplit(url)
    if not url.lower().endswith(".pdf"):
        page.goto(url, wait_until="networkidle", timeout=90000)
        for _ in range(20):  # challenge page reloads itself once solved
            html = page.content().encode()
            if not is_blocked(html, "text/html"):
                break
            page.wait_for_timeout(1000)
        return html
    if not page.url.startswith(f"{parts.scheme}://{parts.netloc}"):
        page.goto(f"{parts.scheme}://{parts.netloc}/", wait_until="networkidle", timeout=90000)
    data = page.evaluate("""async u => {
        const r = await fetch(u, {credentials: 'include'});
        if (r.status === 404) return null;
        return Array.from(new Uint8Array(await r.arrayBuffer()));
    }""", url)
    if data is None:
        raise NotFound(url)
    return bytes(data)
