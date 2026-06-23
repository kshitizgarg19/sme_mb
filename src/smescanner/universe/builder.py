"""Universe orchestration: pull both exchanges, dedupe by ISIN, upsert.

Run daily. A company listed on both NSE Emerge and BSE SME (rare for SME, common
after migration) is merged into one row keyed on ISIN, retaining both the NSE
symbol and BSE scripcode so downstream scrapers can use whichever feed is richer.
"""
from __future__ import annotations

import logging

from ..db.session import upsert
from .bse_sme import BSESMEUniverse
from .nse_emerge import NSEEmergeUniverse

log = logging.getLogger("smescanner.universe")


def refresh_universe(nse_sessions: list[str] | None = None) -> int:
    nse_rows = NSEEmergeUniverse().build(recent_sessions=nse_sessions)
    bse_rows = BSESMEUniverse().build()

    merged: dict[str, dict] = {}  # keyed by ISIN, falling back to symbol/code

    for r in nse_rows:
        key = r.isin or f"NSE:{r.symbol}"
        merged.setdefault(key, {})
        merged[key].update(
            isin=r.isin, nse_symbol=r.symbol, name=r.name,
            exchange="NSE_EMERGE", face_value=r.face_value,
            listing_date=r.listing_date,
        )

    for r in bse_rows:
        key = r.isin or f"BSE:{r.scripcode}"
        row = merged.get(key)
        if row is None:
            merged[key] = dict(
                isin=r.isin, bse_scripcode=r.scripcode, bse_symbol=r.symbol,
                name=r.name, exchange="BSE_SME", industry=r.industry,
                face_value=r.face_value,
            )
        else:
            # present on both exchanges
            row.update(bse_scripcode=r.scripcode, bse_symbol=r.symbol,
                       exchange="BOTH", industry=row.get("industry") or r.industry)

    records = list(merged.values())
    # Upsert keyed on ISIN where present; rows without ISIN fall back to the
    # exchange-native unique constraints handled in two passes.
    with_isin = [r for r in records if r.get("isin")]
    without_isin = [r for r in records if not r.get("isin")]

    n = 0
    if with_isin:
        n += upsert("companies", with_isin, conflict_cols=["isin"])
    for r in without_isin:
        if r.get("nse_symbol"):
            n += upsert("companies", [r], conflict_cols=["exchange", "nse_symbol"])
        elif r.get("bse_scripcode"):
            n += upsert("companies", [r], conflict_cols=["exchange", "bse_scripcode"])

    log.info("Universe refreshed: %d NSE + %d BSE -> %d unique companies",
             len(nse_rows), len(bse_rows), len(records))
    return n
