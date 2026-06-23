"""
Hardened HTTP layer for Indian-market scraping.

The two exchanges are the hard part:

* **NSE** sits behind Akamai. A naked `requests.get` to any `/api/*` endpoint
  returns 401/403. The working pattern is: hit the HTML homepage first with a
  full browser header set to collect the `nsit`/`bm_sv` cookies, *then* call the
  JSON API with a matching `Referer`. Cookies expire, so we refresh on 401/403.
* **BSE** is friendlier (`api.bseindia.com`) but rate-limits aggressively and
  needs an `Origin`/`Referer` of `https://www.bseindia.com`.

Everything else (Screener, Chittorgarh, Trendlyne) is plain HTML with softer
protection — the same `PoliteSession` handles them with rotating user agents,
per-host rate limiting, exponential backoff, and on-disk response caching.

Design goals: one place to enforce politeness, one place to rotate identity,
zero per-scraper boilerplate.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .ratelimit import HostRateLimiter

log = logging.getLogger("smescanner.http")

# A small pool of real, current desktop user agents. Rotated per-session so a
# burst of requests does not all share one fingerprint.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Deliberately omit Brotli ('br'): requests/urllib3 don't decode it without
    # the optional brotli package, and NSE *will* serve br if offered — yielding
    # 200s with undecodable bodies. gzip/deflate are handled natively.
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


@dataclass
class PoliteSession:
    """A requests.Session wrapper that is polite by default.

    Per-host rate limiting, exponential backoff on 429/5xx, a browser-like
    fingerprint, and a configurable jitter so traffic does not look robotic.
    """

    rate_per_host: float = 0.5  # max requests/sec to any single host
    timeout: float = 30.0
    max_retries: int = 4
    jitter: tuple[float, float] = (0.4, 1.4)  # random sleep range (seconds)
    user_agent: str = field(default_factory=lambda: random.choice(USER_AGENTS))
    _session: requests.Session = field(init=False, repr=False)
    _limiter: HostRateLimiter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._session = requests.Session()
        self._limiter = HostRateLimiter(self.rate_per_host)

        retry = Retry(
            total=self.max_retries,
            connect=self.max_retries,
            read=self.max_retries,
            status=self.max_retries,
            backoff_factor=1.5,  # 0, 1.5, 3, 6, 12s
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update(BROWSER_HEADERS)
        self._session.headers["User-Agent"] = self.user_agent

    # -- core request -------------------------------------------------------
    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self._limiter.wait(url)
        kwargs.setdefault("timeout", self.timeout)
        lo, hi = self.jitter
        time.sleep(random.uniform(lo, hi))
        log.debug("%s %s", method, url)
        resp = self._session.request(method, url, **kwargs)
        return resp

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)

    @property
    def cookies(self) -> requests.cookies.RequestsCookieJar:
        return self._session.cookies

    def rotate_identity(self) -> None:
        """Swap user agent + clear cookies — use when a host starts blocking."""
        self.user_agent = random.choice(USER_AGENTS)
        self._session.headers["User-Agent"] = self.user_agent
        self._session.cookies.clear()


class NSEClient:
    """NSE access with the homepage-first cookie handshake.

    NSE's `/api/*` endpoints reject requests that lack the cookies set by the
    HTML site. We bootstrap once, attach an endpoint-appropriate Referer, and
    re-bootstrap automatically on a 401/403 (cookies rotate every few minutes).
    """

    BASE = "https://www.nseindia.com"

    def __init__(self, session: PoliteSession | None = None) -> None:
        self.s = session or PoliteSession(rate_per_host=0.4)
        self._bootstrapped = False

    def _bootstrap(self) -> None:
        # Visiting the homepage + the market-data landing page seeds the
        # Akamai cookies the API gateway checks for.
        self.s.get(self.BASE + "/")
        self.s.get(self.BASE + "/market-data/securities-available-for-trading")
        self._bootstrapped = True
        log.info("NSE session bootstrapped (%d cookies)", len(self.s.cookies))

    def api(self, path: str, referer: str | None = None, **params: Any) -> dict:
        if not self._bootstrapped:
            self._bootstrap()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": referer or (self.BASE + "/"),
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        url = self.BASE + path
        resp = self.s.get(url, headers=headers, params=params or None)
        if resp.status_code in (401, 403):
            log.warning("NSE %s -> %s, re-bootstrapping", path, resp.status_code)
            self.s.rotate_identity()
            self._bootstrapped = False
            self._bootstrap()
            resp = self.s.get(url, headers=headers, params=params or None)
        resp.raise_for_status()
        return resp.json()


class BSEClient:
    """BSE India API client (api.bseindia.com).

    BSE is REST-y and JSON-native but checks Origin/Referer and throttles. No
    cookie handshake required, just the right header set and gentle pacing.
    """

    API = "https://api.bseindia.com/BseIndiaAPI/api"
    SITE = "https://www.bseindia.com"

    def __init__(self, session: PoliteSession | None = None) -> None:
        self.s = session or PoliteSession(rate_per_host=0.5)

    def api(self, path: str, **params: Any) -> dict | list:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": self.SITE,
            "Referer": self.SITE + "/",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        url = f"{self.API}/{path.lstrip('/')}"
        resp = self.s.get(url, headers=headers, params=params or None)
        resp.raise_for_status()
        return resp.json()
