"""
Research agent — turns computed numbers into a grounded investment note.

Design principle (per the brief): NOT a chatbot. The agent is a deterministic
report generator whose only freedom is *prose*. Every number it cites is passed
in from the scoring engine; the prompt forbids inventing figures. If the LLM is
unavailable it falls back to a fully templated note so output is never blank.

Produces the spec's required sections: Investment Thesis, Growth Drivers, Risks,
Red Flags, and a plain-English business summary.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .llm import LocalLLM
from ..scoring.multibagger import MultibaggerResult

log = logging.getLogger("smescanner.ai.agent")

SYSTEM = (
    "You are a sceptical Indian small-cap equity analyst in the tradition of "
    "Vijay Kedia and Ashish Kacholia. You write tight, concrete, number-anchored "
    "notes for a professional investor. Rules: (1) cite ONLY the figures provided "
    "to you — never invent numbers; (2) no hype, no buzzwords, no 'leverages "
    "synergies'; (3) if a metric is missing, say so; (4) lead with the bear case "
    "on anything that looks too good. Output plain prose, no markdown headers."
)


@dataclass
class ResearchNote:
    thesis: str
    growth_drivers: str
    risks: str
    red_flags: list[str]
    business_summary: str


class ResearchAgent:
    def __init__(self, llm: LocalLLM | None = None) -> None:
        self.llm = llm or LocalLLM()

    def write_note(self, result: MultibaggerResult,
                   business_summary: str | None = None,
                   extra_context: dict | None = None) -> ResearchNote:
        facts = self._facts_block(result, extra_context or {})
        red_flags = self._extract_red_flags(result)

        if not self.llm.available():
            return self._templated(result, facts, red_flags, business_summary)

        thesis = self.llm.complete(
            f"{facts}\n\nWrite a 4-6 sentence investment thesis: why this SME "
            f"could compound 5-50x over 3-10 years, grounded strictly in the "
            f"facts above. End with the single biggest reason it might NOT.",
            system=SYSTEM,
        )
        drivers = self.llm.complete(
            f"{facts}\n\nList the 3 most credible growth drivers as short "
            f"bullet sentences, each tied to a specific number above.",
            system=SYSTEM,
        )
        risks = self.llm.complete(
            f"{facts}\n\nList the 3 most material risks for a long-term holder, "
            f"each tied to a specific number or flag above.",
            system=SYSTEM,
        )
        return ResearchNote(
            thesis=thesis or "",
            growth_drivers=drivers or "",
            risks=risks or "",
            red_flags=red_flags,
            business_summary=business_summary or "",
        )

    # -- helpers -----------------------------------------------------------
    def _facts_block(self, r: MultibaggerResult, extra: dict) -> str:
        s = r.sub_scores
        ev = {k: v.get("evidence", {}) for k, v in s.items()}
        lines = [
            f"Company: {r.name} ({r.symbol})",
            f"Multibagger score: {r.total_score}/100 (band {r.band})",
            f"Sub-scores: " + ", ".join(
                f"{k}={v['score']:.0f}" for k, v in s.items() if v.get("score") is not None
            ),
            f"Growth: {_fmt(ev['growth'])}",
            f"Profitability: {_fmt(ev['profitability'])}",
            f"Balance sheet: {_fmt(ev['balance_sheet'])}",
            f"Cash flow: {_fmt(ev['cash_flow'])}",
            f"Management: {_fmt(ev['management'])}",
            f"Valuation: {_fmt(ev['valuation'])}",
            f"Forensic trust multiplier: {r.forensic.get('trust_multiplier')}",
        ]
        if r.forensic.get("altman"):
            lines.append(f"Altman Z zone: {r.forensic['altman'].get('zone')}")
        if r.forensic.get("beneish"):
            lines.append(f"Beneish manipulator flag: {r.forensic['beneish'].get('likely_manipulator')}")
        for k, v in extra.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)

    def _extract_red_flags(self, r: MultibaggerResult) -> list[str]:
        flags = []
        f = r.forensic
        if (f.get("beneish") or {}).get("likely_manipulator"):
            flags.append("Beneish M-Score flags possible earnings manipulation")
        if (f.get("altman") or {}).get("zone") == "distress":
            flags.append("Altman Z-Score in financial-distress zone")
        pio = f.get("piotroski") or {}
        if pio.get("max_available", 0) >= 6 and pio.get("score", 9) <= 3:
            flags.append(f"Weak Piotroski F-Score ({pio.get('score')}/{pio.get('max_available')})")
        mgmt = r.sub_scores.get("management", {}).get("evidence", {})
        if (mgmt.get("pledged_pct") or 0) > 25:
            flags.append(f"High promoter pledge ({mgmt['pledged_pct']:.0f}%)")
        if (mgmt.get("dilution_events_3y") or 0) >= 2:
            flags.append(f"Serial dilution ({mgmt['dilution_events_3y']} raises in 3y)")
        cf = r.sub_scores.get("cash_flow", {}).get("evidence", {})
        if (cf.get("ocf_to_pat_3y") or 1) < 0.5:
            flags.append("Poor cash conversion (OCF < 50% of PAT)")
        return flags

    def _templated(self, r, facts, red_flags, business_summary) -> ResearchNote:
        band = r.band
        thesis = (
            f"{r.name} scores {r.total_score}/100 ({band}). "
            "Thesis (templated — local LLM offline): the composite reflects the "
            "weighted blend of growth, returns on capital, balance-sheet strength, "
            "cash conversion and promoter conviction shown below. Treat as a "
            "screening signal, not a recommendation."
        )
        return ResearchNote(
            thesis=thesis,
            growth_drivers=facts,
            risks="; ".join(red_flags) or "No automated red flags; do primary diligence.",
            red_flags=red_flags,
            business_summary=business_summary or "",
        )


def _fmt(evidence: dict) -> str:
    parts = []
    for k, v in evidence.items():
        if v is None:
            continue
        if isinstance(v, float):
            parts.append(f"{k}={v:.2f}")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts) or "n/a"
