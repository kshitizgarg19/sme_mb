"""Per-host token-bucket rate limiting.

Keeps a separate limiter per network host so a slow Screener crawl never
starves NSE requests and vice-versa. Thread-safe — the ETL pool can share one
limiter instance across workers hitting the same host.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse


class _Bucket:
    """A single host's minimum-interval gate."""

    def __init__(self, rate_per_sec: float) -> None:
        self.min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                time.sleep(self._next_allowed - now)
                now = time.monotonic()
            self._next_allowed = now + self.min_interval


class HostRateLimiter:
    """Lazily creates a bucket per host."""

    def __init__(self, default_rate_per_sec: float = 0.5) -> None:
        self.default_rate = default_rate_per_sec
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        # Host-specific overrides — NSE/BSE want it slower than a static CDN.
        self._overrides = {
            "www.nseindia.com": 0.4,
            "api.bseindia.com": 0.5,
            "www.bseindia.com": 0.5,
            "www.screener.in": 0.33,
            "www.chittorgarh.com": 0.5,
        }

    def _bucket_for(self, url: str) -> _Bucket:
        host = urlparse(url).netloc.lower()
        with self._lock:
            if host not in self._buckets:
                rate = self._overrides.get(host, self.default_rate)
                self._buckets[host] = _Bucket(rate)
            return self._buckets[host]

    def wait(self, url: str) -> None:
        self._bucket_for(url).wait()
