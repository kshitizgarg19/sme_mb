"""
Trendlyne integration (paid Pro data).

Unlocks the data free sources don't give for SME: which marquee/"superstar"
investors hold a stock (named, with %), detailed named shareholders, promoter
profiles, and deeper fundamentals (segments, forecasts, DVM scores).

Auth: Trendlyne's valuable data sits behind a Pro login. This client supports
either a **session cookie** (paste from a logged-in browser — safest, no
password stored) or an **API key** if you take their data/API product. Creds
come from env (`SME_TRENDLYNE_*`), gitignored — never hard-coded.

STATUS: infrastructure ready. The concrete endpoints/parsers are wired AFTER we
have access and inspect the real responses (same approach that got XTS + the NSE
SME endpoints right — explore live, then build to the actual shape).
"""
from __future__ import annotations

import logging
import os

from ..common.http import PoliteSession

log = logging.getLogger("smescanner.scrapers.trendlyne")
BASE = "https://trendlyne.com"


class TrendlyneClient:
    def __init__(self, cookie: str | None = None, api_key: str | None = None) -> None:
        self.cookie = cookie or os.getenv("SME_TRENDLYNE_COOKIE", "")
        self.api_key = api_key or os.getenv("SME_TRENDLYNE_API_KEY", "")
        self.s = PoliteSession(rate_per_host=0.4)
        if self.cookie:
            self.s._session.headers["Cookie"] = self.cookie
        if self.api_key:
            self.s._session.headers["Authorization"] = f"Bearer {self.api_key}"

    @property
    def configured(self) -> bool:
        return bool(self.cookie or self.api_key)

    def _get(self, path: str, **params):
        if not self.configured:
            raise RuntimeError("Trendlyne not configured — set SME_TRENDLYNE_COOKIE or _API_KEY")
        r = self.s.get(f"{BASE}{path}", params=params or None)
        r.raise_for_status()
        return r

    # --- to wire once we have access + see real responses -----------------
    def superstar_holders(self, symbol: str) -> list[dict]:
        """Marquee investors holding this stock (name, % held, change)."""
        raise NotImplementedError("wire after exploring Trendlyne Pro response shape")

    def named_shareholders(self, symbol: str) -> list[dict]:
        """Public shareholders >1% by name (from the detailed pattern)."""
        raise NotImplementedError("wire after exploring Trendlyne Pro response shape")

    def promoter_profile(self, symbol: str) -> dict:
        """Promoter / management names, background, holding & pledge history."""
        raise NotImplementedError("wire after exploring Trendlyne Pro response shape")

    def deep_fundamentals(self, symbol: str) -> dict:
        """Segments, forecasts, DVM scores, peer benchmarks."""
        raise NotImplementedError("wire after exploring Trendlyne Pro response shape")
