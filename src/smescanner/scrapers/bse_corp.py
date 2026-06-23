"""
BSE corporate-data scrapers: announcements, shareholding, results.

All keyed on the numeric BSE ``scripcode`` captured by the universe builder.
BSE's JSON endpoints are stable and require only the BSEClient header set.
Dates are DD/MM/YYYY or YYYYMMDD depending on endpoint — handled per call.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..common.http import BSEClient

log = logging.getLogger("smescanner.scrapers.bse_corp")


class BSECorpScraper:
    def __init__(self, client: BSEClient | None = None) -> None:
        self.bse = client or BSEClient()

    # -- announcements -----------------------------------------------------
    def announcements(self, scripcode: str, from_yyyymmdd: str, to_yyyymmdd: str) -> list[dict]:
        """Corporate announcements for a scrip in a date window.

        Endpoint: AnnGetData/w. Returns rows with HEADLINE, NEWSSUB, CATEGORYNAME,
        NEWS_DT, ATTACHMENTNAME (PDF). VERIFY param names against live on first run.
        """
        data = self.bse.api(
            "AnnGetData/w",
            pageno=1,
            strCat="-1",
            strPrevDate=from_yyyymmdd,
            strToDate=to_yyyymmdd,
            strScrip=scripcode,
            strSearch="P",
            strType="C",
        )
        table = data.get("Table", []) if isinstance(data, dict) else []
        out = []
        for r in table:
            pdf = r.get("ATTACHMENTNAME")
            out.append({
                "headline": r.get("HEADLINE") or r.get("NEWSSUB"),
                "category": r.get("CATEGORYNAME") or r.get("SUBCATNAME"),
                "body": r.get("NEWSSUB"),
                "pdf_url": (f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{pdf}"
                            if pdf else None),
                "announced_at": r.get("NEWS_DT"),
                "source": "bse",
            })
        log.info("BSE announcements %s: %d", scripcode, len(out))
        return out

    # -- shareholding pattern ---------------------------------------------
    def shareholding(self, scripcode: str) -> list[dict]:
        """Quarterly shareholding pattern incl. promoter % and pledge.

        Endpoint: ShareHoldingPattern style. We normalise promoter / pledge /
        FII / DII / public. VERIFY exact endpoint & keys on first run.
        """
        try:
            data = self.bse.api("ShpPromoterNGroup/w", scripcode=scripcode)
        except Exception as exc:  # noqa: BLE001
            log.warning("BSE shareholding %s failed: %s", scripcode, exc)
            return []
        rows = data.get("Table", []) if isinstance(data, dict) else (data or [])
        out = []
        for r in rows:
            out.append({
                "period_end": r.get("QTR_END") or r.get("AsOnDate"),
                "promoter_pct": _f(r.get("PromoterAndGroup") or r.get("Promoter")),
                "pledged_pct_of_total": _f(r.get("PledgePercentage") or r.get("Pledged")),
                "fii_pct": _f(r.get("FII")),
                "dii_pct": _f(r.get("DII")),
                "public_pct": _f(r.get("Public")),
                "source": "bse",
            })
        return out

    # -- quarterly / annual results ---------------------------------------
    def financial_results(self, scripcode: str) -> list[dict]:
        """BSE financial-results feed (period-wise). Used as a cross-check /
        fallback to Screener so we are not single-sourced on fundamentals."""
        try:
            data = self.bse.api("CompanySearchData/w", scripcode=scripcode)
        except Exception as exc:  # noqa: BLE001
            log.warning("BSE results %s failed: %s", scripcode, exc)
            return []
        return data.get("Table", []) if isinstance(data, dict) else []


def _f(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
