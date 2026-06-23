"""
Management quality — governance red/green flags from filings & disclosures.

This complements ``multibagger.score_management`` (which scores the *numbers*:
holding, pledge, dilution) by surfacing *event* signals from corporate filings:
auditor resignations, independent-director exits, frequent related-party churn.
In SME land these qualitative flags are where most permanent capital loss comes
from, so they feed both a score and an explicit red-flag list for the dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ManagementSignals:
    company_id: int
    auditor_changes_2y: int = 0
    id_resignations_2y: int = 0          # independent director resignations
    cfo_changes_2y: int = 0
    pledge_pct: Optional[float] = None
    pledge_increased: bool = False
    dilution_events_3y: int = 0          # rights/pref/QIP
    promoter_holding_pct: Optional[float] = None
    promoter_holding_falling: bool = False
    promoter_net_buy_value: Optional[float] = None
    related_party_intensity: Optional[float] = None  # RPT / revenue if known


@dataclass
class ManagementAssessment:
    score: float
    red_flags: list[str] = field(default_factory=list)
    green_flags: list[str] = field(default_factory=list)


# Each red flag deducts; green flags add. Start neutral at 60, clamp 0-100.
def assess_management(s: ManagementSignals) -> ManagementAssessment:
    score = 60.0
    red: list[str] = []
    green: list[str] = []

    if s.auditor_changes_2y >= 1:
        score -= 20 * s.auditor_changes_2y
        red.append(f"Auditor changed {s.auditor_changes_2y}x in 2y — investigate cause")
    if s.id_resignations_2y >= 1:
        score -= 12 * s.id_resignations_2y
        red.append(f"{s.id_resignations_2y} independent director resignation(s) in 2y")
    if s.cfo_changes_2y >= 2:
        score -= 15
        red.append("CFO churn (>=2 in 2y) — financial-reporting instability")

    if s.pledge_pct:
        if s.pledge_pct > 25:
            score -= 25
            red.append(f"High promoter pledge: {s.pledge_pct:.0f}% of holding")
        elif s.pledge_pct > 0:
            score -= 8
            red.append(f"Some promoter pledge: {s.pledge_pct:.0f}%")
    if s.pledge_increased:
        score -= 8
        red.append("Promoter pledge rising QoQ")

    if s.dilution_events_3y >= 2:
        score -= 10 * (s.dilution_events_3y - 1)
        red.append(f"Serial equity dilution: {s.dilution_events_3y} raises in 3y")

    if s.promoter_holding_falling:
        score -= 10
        red.append("Promoter holding trending down")
    elif s.promoter_holding_pct and s.promoter_holding_pct >= 60:
        score += 8
        green.append(f"Strong promoter skin-in-game: {s.promoter_holding_pct:.0f}%")

    if s.promoter_net_buy_value and s.promoter_net_buy_value > 0:
        score += 12
        green.append("Promoter net buyer in the last 12 months")

    if s.related_party_intensity and s.related_party_intensity > 0.15:
        score -= 12
        red.append(f"Heavy related-party transactions (~{s.related_party_intensity:.0%} of revenue)")

    score = max(0.0, min(100.0, score))
    return ManagementAssessment(score=round(score, 1), red_flags=red, green_flags=green)
