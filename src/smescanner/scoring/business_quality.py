"""
Business quality — moat, scalability & concentration from the annual report.

The narrative fields are extracted by ``ai/report_reader.py`` (local LLM over the
MD&A / management-discussion sections) and stored on ``annual_reports``. Here we
turn those structured extractions plus a sector-tailwind overlay into a 0-100
business-quality score. Deliberately rule-based and explainable — no black box.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BusinessSignals:
    company_id: int
    gross_margin: Optional[float] = None       # proxy for pricing power
    gross_margin_stable: Optional[bool] = None
    roce_3y_avg: Optional[float] = None        # durable returns => moat
    revenue_cagr_3y: Optional[float] = None
    has_capacity_expansion: bool = False
    has_export_revenue: bool = False
    export_pct: Optional[float] = None
    top_customer_pct: Optional[float] = None   # concentration risk
    top_supplier_pct: Optional[float] = None
    addressable_market_large: Optional[bool] = None
    sector_tailwind: Optional[float] = None     # 0-100 overlay


@dataclass
class BusinessAssessment:
    score: float
    notes: list[str] = field(default_factory=list)


# Sector tailwind defaults — a starting overlay, refine from your own thesis.
# These are *priors*, not predictions: structural multi-year tailwinds in India.
SECTOR_TAILWIND = {
    "defence": 90, "electronics manufacturing": 88, " ems": 88,
    "renewable energy": 82, "specialty chemicals": 80, "capital goods": 78,
    "railways": 80, "power": 75, "infrastructure": 72, "pharma api": 75,
    "auto ancillary": 70, "fintech": 68, "it services": 60, "textiles": 55,
    "real estate": 55, "fmcg": 60, "trading": 35, "ngeneric commodity": 30,
}


def sector_tailwind_score(sector: Optional[str]) -> float:
    if not sector:
        return 55.0  # neutral prior
    key = sector.lower().strip()
    for k, v in SECTOR_TAILWIND.items():
        if k.strip() in key or key in k.strip():
            return float(v)
    return 55.0


def assess_business(s: BusinessSignals) -> BusinessAssessment:
    parts: list[float] = []
    notes: list[str] = []

    # Pricing power / moat via gross margin & durable ROCE
    if s.gross_margin is not None:
        gm = max(0.0, min(100.0, (s.gross_margin - 0.10) / (0.45 - 0.10) * 100))
        parts.append(gm)
        if s.gross_margin > 0.35:
            notes.append(f"Healthy gross margin ({s.gross_margin:.0%}) suggests pricing power")
    if s.roce_3y_avg is not None:
        rc = max(0.0, min(100.0, (s.roce_3y_avg - 0.10) / (0.30 - 0.10) * 100))
        parts.append(rc)
        if s.roce_3y_avg > 0.25:
            notes.append("Sustained high ROCE — capital-light, moat-like economics")

    # Scalability
    if s.has_capacity_expansion:
        parts.append(80.0)
        notes.append("Capacity expansion / capex underway — runway for growth")
    if s.addressable_market_large:
        parts.append(85.0)
        notes.append("Large addressable market (Kedia 'large aspiration')")

    # Diversification / concentration penalties
    if s.top_customer_pct is not None:
        conc = max(0.0, 100 - s.top_customer_pct)  # 50% customer -> 50 score
        parts.append(conc)
        if s.top_customer_pct > 40:
            notes.append(f"Customer concentration risk: top client ~{s.top_customer_pct:.0f}%")
    if s.export_pct:
        parts.append(min(100.0, 50 + s.export_pct))  # export exposure a mild plus
        notes.append(f"Export exposure ~{s.export_pct:.0f}% — global TAM, FX upside")

    if s.sector_tailwind is not None:
        parts.append(s.sector_tailwind)

    score = sum(parts) / len(parts) if parts else None
    return BusinessAssessment(
        score=round(score, 1) if score is not None else 0.0,
        notes=notes,
    )
