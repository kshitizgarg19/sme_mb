"""
NSE corporate-data scrapers: announcements, shareholding, insider (PIT),
bulk/block deals. All go through NSEClient's cookie-gated ``api`` helper.

These endpoints power the management-quality and promoter-conviction signals:
  * corporates-pit       -> insider_trades (SEBI PIT disclosures)
  * historical/bulk-deals -> bulk_deals (cross-referenced w/ marquee investors)
  * corporate-shareholdings-patterns -> shareholding
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Optional

from ..common.http import NSEClient

log = logging.getLogger("smescanner.scrapers.nse_corp")
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"

# Marquee SME/small-cap investors — a bulk deal by one of these is a strong
# qualitative signal. Matched case-insensitively against the client name.
MARQUEE_INVESTORS = {
    "rakesh jhunjhunwala", "rekha jhunjhunwala", "vijay kishanlal kedia",
    "kedia securities", "ashish kacholia", "ashish dhawan", "mukul agrawal",
    "porinju", "dolly khanna", "rajeev thakkar", "sunil singhania",
    "ramesh damani", "nemish shah", "anil kumar goel",
}


class NSECorpScraper:
    def __init__(self, client: NSEClient | None = None) -> None:
        self.nse = client or NSEClient()

    def announcements(self, symbol: str, index: str = "sme") -> list[dict]:
        """SME companies live under index='sme' (NOT 'equities', which is
        mainboard and returns nothing for Emerge names)."""
        data = self.nse.api(
            "/api/corporate-announcements", referer=REF,
            index=index, symbol=symbol,
        )
        rows = data if isinstance(data, list) else data.get("data", [])
        return [{
            "headline": (r.get("attchmntText") or r.get("desc") or "").strip(),
            "category": (r.get("desc") or "").strip() or None,
            "body": r.get("attchmntText"),
            "pdf_url": r.get("attchmntFile") or None,
            "announced_at": r.get("an_dt") or r.get("sort_date"),
            "source": "nse",
        } for r in rows]

    def insider_trades(self, symbol: str) -> list[dict]:
        """SEBI PIT (Prohibition of Insider Trading) disclosures."""
        data = self.nse.api(
            "/api/corporates-pit", referer=REF,
            index="equities", symbol=symbol,
        )
        rows = data.get("data", []) if isinstance(data, dict) else data
        out = []
        for r in rows:
            acq = (r.get("acqMode") or "").lower()
            side = "BUY" if "acqui" in (r.get("tdpTransactionType") or "").lower() else "SELL"
            if "pledge" in acq:
                side = "PLEDGE"
            out.append({
                "person": r.get("acqName"),
                "is_promoter": "promoter" in (r.get("personCategory") or "").lower(),
                "side": side,
                "quantity": _i(r.get("secAcq")),
                "value": _f(r.get("secVal")),
                "mode": r.get("acqMode"),
                "trade_date": r.get("date") or r.get("acqfromDt"),
                "disclosed_date": r.get("intimDt"),
                "source": "nse",
            })
        return out

    # Static CSV archives — far more reliable than /api/historical/bulk-deals,
    # which NSE serves 503/captcha for. These hold the latest session's deals.
    BULK_CSV = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
    BLOCK_CSV = "https://nsearchives.nseindia.com/content/equities/block.csv"

    def bulk_block_deals(self) -> list[dict]:
        """Latest-session bulk + block deals from the CSV archive, marquee-flagged."""
        if not self.nse._bootstrapped:
            self.nse._bootstrap()
        out: list[dict] = []
        for url, dtype in [(self.BULK_CSV, "bulk"), (self.BLOCK_CSV, "block")]:
            try:
                r = self.nse.s.get(url)
                if r.status_code != 200 or len(r.content) < 50:
                    continue
                for row in csv.DictReader(io.StringIO(r.text)):
                    client = (row.get("Client Name") or "").strip()
                    out.append({
                        "deal_date": (row.get("Date") or "").strip(),
                        "symbol": (row.get("Symbol") or "").strip(),
                        "name": (row.get("Security Name") or "").strip(),
                        "client_name": client,
                        "side": "BUY" if (row.get("Buy/Sell") or "").upper().startswith("B") else "SELL",
                        "quantity": _i(row.get("Quantity Traded")),
                        "price": _f(row.get("Trade Price / Wght. Avg. Price")),
                        "deal_type": dtype,
                        "exchange": "NSE",
                        "is_known_investor": _is_marquee(client),
                        "source": "nse_csv",
                    })
            except Exception as exc:  # noqa: BLE001
                log.warning("bulk/block CSV %s: %s", dtype, exc)
        return out

    def shareholding(self, symbol: str) -> list[dict]:
        data = self.nse.api(
            "/api/corporate-shareholdings-patterns", referer=REF,
            index="equities", symbol=symbol,
        )
        rows = data.get("data", []) if isinstance(data, dict) else data
        return rows or []


def _is_marquee(name: str) -> bool:
    n = (name or "").lower()
    return any(inv in n for inv in MARQUEE_INVESTORS)


def _f(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _i(v) -> Optional[int]:
    f = _f(v)
    return int(f) if f is not None else None
