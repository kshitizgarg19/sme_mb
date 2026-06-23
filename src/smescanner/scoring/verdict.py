"""
Investor brain — a grounded Buy/Watch/Avoid verdict in the frame of the
investors Kshitiz named (Jhunjhunwala, Kedia, Kacholia, Porinju).

This is deliberately NOT an LLM. Every sentence ties to a computed number from
the scoring engine, so it can't hallucinate a fact. It reads the sub-score
*evidence* dicts + the forensic gate and emits:

  * a verdict tier (BUY / ACCUMULATE / MONITOR / AVOID) with a one-line headline
  * thesis bullets — why it's interesting, each anchored to a figure
  * risk bullets — what could go wrong, each anchored to a figure/flag
  * three "lenses" — the legends' explicit checklists, each pass/fail with a reason

The output is stored as JSON on ``multibagger_scores.verdict`` and rendered as the
"Investor View" card at the top of a company page.
"""
from __future__ import annotations

from typing import Optional

from .multibagger import CompanyFinancials, MultibaggerResult


def _pct(v: Optional[float], d: int = 0) -> str:
    return "—" if v is None else f"{v * 100:.{d}f}%"


def _g(sub: dict, key: str, field: str):
    return (sub.get(key, {}).get("evidence", {}) or {}).get(field)


def _s(sub: dict, key: str) -> float:
    v = sub.get(key, {}).get("score")
    return v if v is not None else 0.0


def generate_verdict(cf: CompanyFinancials, r: MultibaggerResult) -> dict:
    sub = r.sub_scores
    f = cf.latest
    trust = r.forensic.get("trust_multiplier", 1.0) or 1.0
    band = (r.band or "D")[0]

    # ---- verdict tier (forensic gate can veto a good band) ----------------
    if trust < 0.7:
        verdict, tone = "AVOID", "bad"
        headline = "Forensic / governance concerns cap conviction"
    elif band == "A":
        verdict, tone = "BUY", "good"
        headline = "High-conviction multibagger candidate"
    elif band == "B":
        verdict, tone = "ACCUMULATE", "good"
        headline = "Strong franchise — build a position on dips"
    elif band == "C":
        verdict, tone = "MONITOR", "mid"
        headline = "Improving, but the proof isn't complete yet"
    else:
        verdict, tone = "AVOID", "bad"
        headline = "Too early — quality / runway not established"

    # ---- thesis (why interesting) ----------------------------------------
    thesis: list[str] = []
    pat3 = _g(sub, "growth", "profit_cagr_3y")
    rev3 = _g(sub, "growth", "revenue_cagr_3y")
    if pat3 and pat3 > 0.25 and f.revenue:
        thesis.append(f"Profit compounding {_pct(pat3)} (3y) on a small ₹{f.revenue:.0f} cr base — the long runway Kedia hunts for")
    elif rev3 and rev3 > 0.20:
        thesis.append(f"Revenue growing {_pct(rev3)} (3y) — scaling fast off a small base")
    roce_avg = _g(sub, "profitability", "roce_3y_avg")
    if roce_avg and roce_avg > 0.20:
        thesis.append(f"3-year average ROCE {_pct(roce_avg)} — capital-efficient, the hallmark Kacholia looks for in niche leaders")
    conv = _g(sub, "cash_flow", "ocf_to_pat_3y")
    if conv and conv >= 0.8:
        thesis.append(f"Earnings convert to cash (OCF/PAT {conv:.2f}) — clean accruals, not paper profits")
    de = _g(sub, "balance_sheet", "debt_to_equity")
    if de is not None and de < 0.4:
        thesis.append(f"Lightly levered (D/E {de:.2f}) — growth funded by the business, not debt")
    hold = _g(sub, "management", "promoter_holding")
    chg = _g(sub, "management", "holding_change_4q")
    if hold and hold >= 55:
        msg = f"Promoter holds {hold:.0f}%"
        if chg and chg > 0:
            msg += f" and added {chg:.1f}pp recently — rising skin in the game"
        elif not _g(sub, "management", "pledged_pct"):
            msg += ", unpledged — aligned with minority holders"
        thesis.append(msg)
    peg = _g(sub, "valuation", "peg")
    if peg and 0 < peg < 1.2:
        thesis.append(f"PEG ~{peg:.2f} — growth not yet priced in, re-rating room")
    if not thesis:
        thesis.append("No standout strengths yet — the numbers don't make a multibagger case at this stage")

    # ---- risks -----------------------------------------------------------
    risks: list[str] = []
    fr = r.forensic
    if (fr.get("beneish") or {}).get("likely_manipulator"):
        risks.append("Beneish M-Score flags possible earnings manipulation — verify cash flows before trusting profits")
    if (fr.get("altman") or {}).get("zone") == "distress":
        risks.append("Altman Z-Score in the distress zone — balance-sheet stress")
    pio = fr.get("piotroski") or {}
    if pio.get("max_available", 0) >= 6 and pio.get("score", 9) <= 3:
        risks.append(f"Weak Piotroski F-Score ({pio.get('score')}/{pio.get('max_available')}) — fundamental quality deteriorating")
    if conv is not None and conv < 0.5:
        risks.append(f"Poor cash conversion (OCF/PAT {conv:.2f}) — profits aren't turning into cash")
    pledge = _g(sub, "management", "pledged_pct")
    if pledge and pledge > 0:
        risks.append(f"Promoter pledge {pledge:.0f}% — a forced-sale and governance risk")
    dil = _g(sub, "management", "dilution_events_3y")
    if dil and dil >= 2:
        risks.append(f"Serial equity dilution ({dil} raises in 3y) — minority holders getting diluted")
    if de is not None and de > 1.0:
        risks.append(f"High leverage (D/E {de:.2f}) — vulnerable in a downturn")
    if chg is not None and chg < -1:
        risks.append(f"Promoter holding fell {abs(chg):.1f}pp — watch why insiders are trimming")
    if _s(sub, "valuation") < 35:
        risks.append("Rich valuation leaves little margin of safety")
    if not risks:
        risks.append("No automated red flags — but SME liquidity is thin; size positions accordingly")

    # ---- legend lenses ---------------------------------------------------
    lenses = [_kedia(cf, r), _kacholia(cf, r), _jhunjhunwala(cf, r)]

    return {
        "verdict": verdict, "tone": tone, "headline": headline,
        "thesis": thesis, "risks": risks, "lenses": lenses,
        "trust": round(trust, 2),
    }


def _kedia(cf: CompanyFinancials, r: MultibaggerResult) -> dict:
    """SMILE: Small in size, Large in aspiration / market potential."""
    mcap = cf.price.market_cap
    tail = cf.sector_tailwind_score or 55
    growth = _s(r.sub_scores, "growth")
    small = mcap is not None and mcap < 1000
    aspiration = tail >= 70 or growth >= 70
    why = []
    if mcap is not None:
        why.append(f"₹{mcap:.0f} cr base" if small else f"₹{mcap:.0f} cr — less room to 10x")
    why.append("large runway" if aspiration else "modest growth runway")
    return {"name": "Kedia · SMILE", "pass": bool(small and aspiration), "why": ", ".join(why)}


def _kacholia(cf: CompanyFinancials, r: MultibaggerResult) -> dict:
    """Niche category leader: durable, high return on capital."""
    roce_avg = _g(r.sub_scores, "profitability", "roce_3y_avg")
    ok = bool(roce_avg and roce_avg > 0.20)
    if roce_avg is None:
        why = "ROCE not available in the data"
    else:
        why = f"3y ROCE {_pct(roce_avg)} — " + ("durable, capital-light" if ok else "returns not yet elite")
    return {"name": "Kacholia · niche leader", "pass": ok, "why": why}


def _jhunjhunwala(cf: CompanyFinancials, r: MultibaggerResult) -> dict:
    """Quality + low debt + cash generation + trustworthy management."""
    de = _g(r.sub_scores, "balance_sheet", "debt_to_equity")
    cash_ok = _s(r.sub_scores, "cash_flow") >= 60
    mgmt_ok = _s(r.sub_scores, "management") >= 60
    low_debt = de is not None and de < 0.5
    ok = bool(low_debt and cash_ok and mgmt_ok)
    parts = []
    parts.append("low debt" if low_debt else "leverage a concern")
    parts.append("cash-generative" if cash_ok else "weak cash conversion")
    parts.append("aligned promoter" if mgmt_ok else "management unproven/weak")
    return {"name": "Jhunjhunwala · quality", "pass": ok, "why": ", ".join(parts)}
