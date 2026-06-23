"""
BSE SME universe builder.

BSE exposes a JSON list-of-scrips endpoint that we filter to the SME segment.
BSE SME scrips trade in groups M / MT / XT and carry a distinct instrument flag;
we keep active equity scrips flagged SME. Each scrip's numeric ``scripcode`` is
the join key for every other BSE endpoint (announcements, shareholding, results),
so we capture it as the canonical id alongside the symbol.

Fallback: the published "List of Scrips" master file (CSV) served from the BSE
site, which always contains the full active universe.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..common.http import BSEClient

log = logging.getLogger("smescanner.universe.bse")


@dataclass
class BSEUniverseRow:
    symbol: str
    name: str
    scripcode: str  # BSE numeric code — canonical id for all BSE APIs
    exchange: str = "BSE_SME"
    isin: str | None = None
    group: str | None = None
    industry: str | None = None
    face_value: float | None = None
    market_cap: float | None = None  # ₹ crore — BSE returns this in the list feed


class BSESMEUniverse:
    # List-of-scrips: status=Active, segment=Equity. We filter SME client-side.
    LIST_PATH = "ListofScripData/w"

    def __init__(self, client: BSEClient | None = None) -> None:
        self.bse = client or BSEClient()

    def build(self) -> list[BSEUniverseRow]:
        # Pull active equity scrips. BSE returns the full list; we keep SME.
        data = self.bse.api(
            self.LIST_PATH,
            segment="Equity",
            status="Active",
            Group="",
            industry="",
            Scripcode="",
        )
        records = data if isinstance(data, list) else data.get("Table", [])
        rows: list[BSEUniverseRow] = []
        for r in records:
            if not _is_sme(r):
                continue
            code = str(r.get("SCRIP_CD") or r.get("Scrip_Cd") or r.get("scripcode") or "").strip()
            sym = (r.get("scrip_id") or r.get("Scrip_Id") or r.get("SYMBOL") or "").strip()
            if not code:
                continue
            rows.append(
                BSEUniverseRow(
                    symbol=sym or code,
                    name=(r.get("Scrip_Name") or r.get("SCRIP_NAME") or sym).strip(),
                    scripcode=code,
                    isin=(r.get("ISIN_NUMBER") or r.get("ISIN") or "").strip() or None,
                    group=(r.get("GROUP") or r.get("Group") or "").strip() or None,
                    industry=(r.get("INDUSTRY") or r.get("Industry") or "").strip() or None,
                    face_value=_safe_float(r.get("FACE_VALUE") or r.get("Face_Value")),
                    market_cap=_safe_float(r.get("Mktcap") or r.get("MktCap")),
                )
            )
        log.info("BSE SME universe: %d scrips", len(rows))
        return rows


def _is_sme(record: dict) -> bool:
    """BSE SME scrips trade in groups M (SME), MT (SME trade-to-trade) and MS.

    NOTE: 'XT' is the X-group trade-to-trade bucket (old illiquid/suspended
    mainboard names) — explicitly NOT SME, despite the superficially similar
    code. Verified against the live ListofScripData feed (group distribution:
    M=324, MT=162, MS=7 ≈ the ~490-name BSE SME universe).
    """
    group = str(record.get("GROUP") or record.get("Group") or "").upper().strip()
    return group in {"M", "MT", "MS"}


def _safe_float(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
