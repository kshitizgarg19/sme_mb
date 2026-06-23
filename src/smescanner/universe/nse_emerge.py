"""
NSE Emerge universe builder.

Coverage strategy (most-complete first, with fallback):

1. **SME bhavcopy** — the daily SME trade report lists *every* symbol that
   traded on Emerge that day. This is ground truth for the full universe.
   Reading the last few sessions and unioning the symbols handles thinly-traded
   names that skip a day.
2. **SME Emerge index constituents** (`/api/equity-stockIndices`) — a reliable
   JSON endpoint, but only the index-eligible subset. Used as a fallback /
   cross-check when the archive is unreachable.

Each symbol is enriched with a quote lookup to capture ISIN, face value, listing
date, and the current market cap that the size/runway score needs.

NOTE: NSE occasionally renames archive paths. Endpoints marked ``# VERIFY`` should
be confirmed against the live site on first run; the fallback chain means a single
broken path degrades coverage rather than breaking the pipeline.
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass

from ..common.http import NSEClient

log = logging.getLogger("smescanner.universe.nse")


@dataclass
class UniverseRow:
    symbol: str
    name: str
    exchange: str  # "NSE_EMERGE"
    isin: str | None = None
    series: str | None = None  # SM | ST (SME and SME trade-to-trade)
    market_cap: float | None = None
    face_value: float | None = None
    listing_date: str | None = None
    last_price: float | None = None  # from the live feed, for the prices table


class NSEEmergeUniverse:
    # Verified primary: the Emerge market-watch live feed returns the full SME
    # universe (~530 names, series SM/ST) with last-traded prices. Confirmed
    # live 2026-06-23. (The /api/equity-stockIndices?index=... index endpoint
    # does NOT serve an SME index — it 404s — so we don't use it.)
    EMERGE_PATH = "/api/live-analysis-emerge"
    REF = "https://www.nseindia.com/market-data/emerge-market-watch"
    # Daily SME bhavcopy archive (zip of CSV) — alternative for historical days.
    # VERIFY the live path/format against the archive before relying on it.
    BHAVCOPY_TMPL = "https://nsearchives.nseindia.com/archives/sme/bhavcopy/sme{ddmmyy}.csv.zip"

    def __init__(self, client: NSEClient | None = None) -> None:
        self.nse = client or NSEClient()

    # -- primary: live Emerge market watch --------------------------------
    def from_live(self) -> list[UniverseRow]:
        """Full traded SME universe with last price. No company name/ISIN in this
        payload — symbol is the key; name/ISIN are enriched later (quote lookup
        or BSE cross-match)."""
        data = self.nse.api(self.EMERGE_PATH, referer=self.REF)
        rows: list[UniverseRow] = []
        for item in data.get("data", []):
            sym = item.get("symbol")
            if not sym:
                continue
            rows.append(
                UniverseRow(
                    symbol=sym,
                    name=sym,  # enriched later
                    exchange="NSE_EMERGE",
                    series=item.get("series"),
                    last_price=_safe_float(item.get("lastPrice")),
                )
            )
        log.info("NSE Emerge live feed: %d symbols", len(rows))
        return rows

    # -- fallback: parse a recent SME bhavcopy ----------------------------
    def from_bhavcopy(self, ddmmyy: str) -> list[UniverseRow]:
        url = self.BHAVCOPY_TMPL.format(ddmmyy=ddmmyy)
        resp = self.nse.s.get(url)
        resp.raise_for_status()
        rows: list[UniverseRow] = []
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            name = zf.namelist()[0]
            text = zf.read(name).decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        for r in reader:
            sym = (r.get("SYMBOL") or r.get("TckrSymb") or "").strip()
            if not sym:
                continue
            rows.append(
                UniverseRow(
                    symbol=sym,
                    name=(r.get("SECURITY") or sym).strip(),
                    exchange="NSE_EMERGE",
                    isin=(r.get("ISIN") or r.get("ISIN_CODE") or "").strip() or None,
                    series=(r.get("SERIES") or "SM").strip(),
                )
            )
        log.info("NSE SME bhavcopy %s: %d symbols", ddmmyy, len(rows))
        return rows

    def build(self, recent_sessions: list[str] | None = None) -> list[UniverseRow]:
        """Live Emerge feed is the verified primary; bhavcopy is an optional
        historical supplement (pass ``recent_sessions`` as DDMMYY strings).
        """
        by_symbol: dict[str, UniverseRow] = {}
        try:
            for row in self.from_live():
                by_symbol[row.symbol] = row
        except Exception as exc:  # noqa: BLE001 — degrade to bhavcopy
            log.warning("Live Emerge feed failed (%s); trying bhavcopy", exc)

        for ddmmyy in recent_sessions or []:
            try:
                for row in self.from_bhavcopy(ddmmyy):
                    by_symbol.setdefault(row.symbol, row)
            except Exception as exc:  # noqa: BLE001 — degrade gracefully
                log.warning("SME bhavcopy %s failed: %s", ddmmyy, exc)
        return list(by_symbol.values())


def _safe_float(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
