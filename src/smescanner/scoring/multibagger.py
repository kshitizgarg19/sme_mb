"""
Multibagger composite score (0-100).

This is the opinionated layer. It does not chase price momentum; it ranks
businesses by the traits that historically *precede* a 5x-50x re-rating in
Indian small caps, the way Jhunjhunwala / Kedia / Kacholia describe their work:

  * Small base + long runway  (Kedia's SMILE: Small in size, Large in aspiration)
  * Durable high returns on capital  (Kacholia's niche category leaders)
  * Growth that is *funded by the business*, not by serial dilution
  * A promoter who is buying, unpledged, and not diluting minority holders
  * Clean books — earnings that turn into cash, no manipulation flags

Forensic safety is a **gate**, not a positive contributor: you cannot buy your
way to a high score with growth if the cash flows or the Beneish/Altman checks
say the numbers are suspect. A failing forensic profile caps the final score.

Each sub-score is 0-100 and independently interpretable. The composite is a
weighted blend (weights in config.py) with an explicit forensic penalty applied
last. Every sub-score returns its own *evidence* dict so the dashboard and the
AI agent can explain *why*, never just emit a number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..config import get_settings
from . import metrics as M
from .metrics import FinancialSnapshot, PriceSnapshot

Num = Optional[float]


@dataclass
class CompanyFinancials:
    """Everything the scorer needs for one company at one point in time."""

    symbol: str
    name: str
    years: list[FinancialSnapshot]  # oldest -> newest, ideally 5-6 points
    price: PriceSnapshot
    promoter_holding_pct: Num = None
    promoter_holding_pct_4q_ago: Num = None
    pledged_pct: Num = None
    promoter_net_buy_value: Num = None  # last 12m, from insider trades
    equity_dilution_events: int = 0  # rights/pref/QIP in last 3y
    sector: str | None = None
    sector_tailwind_score: Num = None  # 0-100, set by industry overlay

    @property
    def latest(self) -> FinancialSnapshot:
        return self.years[-1]

    @property
    def prev(self) -> Optional[FinancialSnapshot]:
        return self.years[-2] if len(self.years) >= 2 else None


# --------------------------------------------------------------------------- #
# Scoring primitives — map a raw metric onto 0-100 with a clamped linear ramp.
# --------------------------------------------------------------------------- #
def ramp(x: Num, lo: float, hi: float, *, invert: bool = False) -> Num:
    """Linear score: x<=lo -> 0, x>=hi -> 100 (or inverted)."""
    if x is None:
        return None
    if hi == lo:
        return 50.0
    t = (x - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return (1 - t) * 100 if invert else t * 100


def _avg(vals: list[Num]) -> Num:
    present = [v for v in vals if v is not None]
    return sum(present) / len(present) if present else None


# --------------------------------------------------------------------------- #
# Sub-scores
# --------------------------------------------------------------------------- #
def score_growth(c: CompanyFinancials) -> dict:
    rev = [y.revenue for y in c.years]
    pat = [y.net_income for y in c.years]
    ocf = [y.operating_cash_flow for y in c.years]
    n = len(c.years) - 1

    rev_cagr = M.series_cagr(rev, n)
    pat_cagr = M.series_cagr(pat, n)
    ocf_cagr = M.series_cagr(ocf, n)
    rev_3y = M.series_cagr(rev[-4:], 3) if len(rev) >= 4 else rev_cagr
    pat_3y = M.series_cagr(pat[-4:], 3) if len(pat) >= 4 else pat_cagr

    # 25% topline + 35% profit CAGR (3y) is "fast"; 50%+ is exceptional.
    parts = [
        ramp(rev_3y, 0.10, 0.30),
        ramp(pat_3y, 0.12, 0.40),
        ramp(ocf_cagr, 0.08, 0.30),
    ]
    return {
        "score": _avg(parts),
        "evidence": {
            "revenue_cagr_full": rev_cagr, "revenue_cagr_3y": rev_3y,
            "profit_cagr_full": pat_cagr, "profit_cagr_3y": pat_3y,
            "ocf_cagr": ocf_cagr,
        },
    }


def score_profitability(c: CompanyFinancials) -> dict:
    f = c.latest
    roce = M.roce(f)
    roe = M.roe(f)
    # 3-year average ROCE rewards consistency over a one-off spike.
    roce_hist = _avg([M.roce(y) for y in c.years[-3:]])
    parts = [
        ramp(roce_hist, 0.12, 0.30),  # >30% ROCE is elite for an SME
        ramp(roe, 0.12, 0.28),
        ramp(M.operating_margin(f), 0.08, 0.25),
    ]
    return {
        "score": _avg(parts),
        "evidence": {"roce": roce, "roce_3y_avg": roce_hist, "roe": roe,
                     "op_margin": M.operating_margin(f)},
    }


def score_balance_sheet(c: CompanyFinancials) -> dict:
    f = c.latest
    de = M.debt_to_equity(f)
    ic = M.interest_coverage(f)
    parts = [
        ramp(de, 0.1, 1.0, invert=True),  # lower D/E better; >1.0 -> 0
        ramp(ic, 2.0, 8.0),               # interest cover >8x is comfortable
        ramp(M.current_ratio(f), 1.0, 2.5),
    ]
    return {
        "score": _avg(parts),
        "evidence": {"debt_to_equity": de, "interest_coverage": ic,
                     "current_ratio": M.current_ratio(f)},
    }


def score_cash_flow(c: CompanyFinancials) -> dict:
    f = c.latest
    # OCF/PAT averaged over available years — the single best accrual check.
    conv = _avg([M.ocf_to_pat(y) for y in c.years[-3:]])
    fcfy = M.fcf_yield(f, c.price)
    # Count years with positive OCF — consistency matters more than one good year.
    pos_ocf = [y.operating_cash_flow for y in c.years if y.operating_cash_flow is not None]
    pos_frac = (sum(1 for v in pos_ocf if v > 0) / len(pos_ocf)) if pos_ocf else None
    parts = [
        ramp(conv, 0.6, 1.0),         # want PAT converting to cash
        ramp(fcfy, 0.0, 0.06),        # positive FCF yield is a bonus
        ramp(pos_frac, 0.5, 1.0),
    ]
    return {
        "score": _avg(parts),
        "evidence": {"ocf_to_pat_3y": conv, "fcf_yield": fcfy,
                     "positive_ocf_fraction": pos_frac},
    }


def score_management(c: CompanyFinancials) -> dict:
    """Promoter conviction & alignment. High promoter holding that is *rising*,
    unpledged, with net buying and no serial dilution."""
    holding = ramp(c.promoter_holding_pct, 40.0, 70.0)  # skin in the game
    trend = None
    if c.promoter_holding_pct is not None and c.promoter_holding_pct_4q_ago is not None:
        delta = c.promoter_holding_pct - c.promoter_holding_pct_4q_ago
        trend = ramp(delta, -2.0, 2.0)  # rising stake -> high
    pledge = ramp(c.pledged_pct, 0.0, 25.0, invert=True)  # any pledge is a knock
    buying = None
    if c.promoter_net_buy_value is not None:
        buying = 100.0 if c.promoter_net_buy_value > 0 else 40.0
    dilution = ramp(float(c.equity_dilution_events), 0.0, 3.0, invert=True)

    # Don't fabricate a score from the dilution default alone: if we have NO real
    # promoter/governance data (holding, pledge, buying all unknown), return None
    # so management is excluded from the composite rather than scored a fake 100.
    if all(x is None for x in (holding, trend, pledge, buying)):
        return {"score": None, "evidence": {"note": "no shareholding/insider data yet"}}

    parts = [holding, trend, pledge, buying, dilution]
    return {
        "score": _avg(parts),
        "evidence": {
            "promoter_holding": c.promoter_holding_pct,
            "holding_change_4q": (
                None if c.promoter_holding_pct is None
                or c.promoter_holding_pct_4q_ago is None
                else c.promoter_holding_pct - c.promoter_holding_pct_4q_ago
            ),
            "pledged_pct": c.pledged_pct,
            "promoter_net_buy": c.promoter_net_buy_value,
            "dilution_events_3y": c.equity_dilution_events,
        },
    }


def score_capital_efficiency(c: CompanyFinancials) -> dict:
    f = c.latest
    at = M.asset_turnover(f)
    ccc = M.cash_conversion_cycle(f)
    parts = [
        ramp(at, 0.6, 2.0),
        ramp(ccc, 30.0, 120.0, invert=True),  # tighter cycle better
    ]
    return {
        "score": _avg(parts),
        "evidence": {"asset_turnover": at, "cash_conversion_cycle": ccc,
                     "inventory_days": M.inventory_days(f),
                     "debtor_days": M.debtor_days(f)},
    }


def score_valuation(c: CompanyFinancials) -> dict:
    """Valuation *comfort*, not cheapness for its own sake. A reasonable PEG and
    not-absurd P/E leaves room for the re-rating; nosebleed multiples cap upside.
    """
    f = c.latest
    pe = M._div(c.price.market_cap, f.net_income)
    pat_cagr = M.series_cagr([y.net_income for y in c.years], len(c.years) - 1)
    peg = None
    if pe is not None and pat_cagr not in (None, 0) and pat_cagr > 0:
        peg = pe / (pat_cagr * 100)
    parts = [
        ramp(peg, 0.5, 2.0, invert=True),  # PEG<1 great, >2 expensive
        ramp(pe, 10.0, 45.0, invert=True),
    ]
    return {
        "score": _avg(parts),
        "evidence": {"pe": pe, "peg": peg, "earnings_cagr": pat_cagr},
    }


def score_size_runway(c: CompanyFinancials) -> dict:
    """Kedia SMILE: a small base with a large addressable runway has the most
    room to compound. We reward small market cap *and* small absolute revenue,
    then lean on the sector tailwind overlay for 'large aspiration'."""
    mcap = c.price.market_cap
    # SME multibaggers typically start sub-₹500cr mcap. Score peaks small.
    size = ramp(mcap, 1500.0, 100.0, invert=False) if mcap is not None else None
    # ramp inverted manually: small mcap -> high. Use direct invert ramp:
    size = ramp(mcap, 100.0, 1500.0, invert=True)
    rev = c.latest.revenue
    rev_room = ramp(rev, 50.0, 1000.0, invert=True)
    tail = c.sector_tailwind_score
    return {
        "score": _avg([size, rev_room, tail]),
        "evidence": {"market_cap": mcap, "latest_revenue": rev,
                     "sector_tailwind": tail},
    }


# --------------------------------------------------------------------------- #
# Forensic gate
# --------------------------------------------------------------------------- #
def forensic_assessment(c: CompanyFinancials) -> dict:
    """Returns a 0-1 'trust multiplier' plus the raw forensic scores. A clean
    book leaves the composite untouched; flags shave points off the top."""
    f, p = c.latest, c.prev
    out: dict = {"piotroski": None, "altman": None, "beneish": None}
    penalties = 0.0

    if p is not None:
        piotroski = M.piotroski_f_score(f, p)
        out["piotroski"] = piotroski
        if piotroski["max_available"] >= 6 and piotroski["score"] <= 3:
            penalties += 0.15  # weak fundamental quality

        beneish = M.beneish_m_score(f, p)
        out["beneish"] = beneish
        if beneish["variables_computed"] >= 5 and beneish["likely_manipulator"]:
            penalties += 0.25  # earnings-manipulation flag — heavy

    altman = M.altman_z_score(f, c.price)
    out["altman"] = altman
    if altman["zone"] == "distress":
        penalties += 0.20

    # Cash-conversion sanity: chronic OCF << PAT is its own forensic flag.
    conv = _avg([M.ocf_to_pat(y) for y in c.years[-3:]])
    if conv is not None and conv < 0.5:
        penalties += 0.15

    trust = max(0.0, 1.0 - min(penalties, 0.6))
    out["trust_multiplier"] = trust
    out["penalty_fraction"] = min(penalties, 0.6)
    return out


# --------------------------------------------------------------------------- #
# Composite
# --------------------------------------------------------------------------- #
@dataclass
class MultibaggerResult:
    symbol: str
    name: str
    total_score: float
    sub_scores: dict = field(default_factory=dict)
    forensic: dict = field(default_factory=dict)
    band: str = ""


def score_company(c: CompanyFinancials) -> MultibaggerResult:
    cfg = get_settings()
    subs = {
        "growth": score_growth(c),
        "profitability": score_profitability(c),
        "balance_sheet": score_balance_sheet(c),
        "cash_flow": score_cash_flow(c),
        "management": score_management(c),
        "capital_efficiency": score_capital_efficiency(c),
        "valuation": score_valuation(c),
        "size_runway": score_size_runway(c),
    }
    weights = {
        "growth": cfg.w_growth,
        "profitability": cfg.w_profitability,
        "balance_sheet": cfg.w_balance_sheet,
        "cash_flow": cfg.w_cash_flow,
        "management": cfg.w_management,
        "capital_efficiency": cfg.w_capital_efficiency,
        "valuation": cfg.w_valuation,
        "size_runway": cfg.w_size_runway,
    }

    # Re-normalise weights over only the sub-scores we could actually compute,
    # so a missing valuation field doesn't silently drag the score to zero.
    usable = {k: v["score"] for k, v in subs.items() if v["score"] is not None}
    wsum = sum(weights[k] for k in usable) or 1.0
    base = sum(usable[k] * weights[k] for k in usable) / wsum

    forensic = forensic_assessment(c)
    total = base * forensic["trust_multiplier"]

    return MultibaggerResult(
        symbol=c.symbol,
        name=c.name,
        total_score=round(total, 1),
        sub_scores=subs,
        forensic=forensic,
        band=_band(total),
    )


def _band(score: float) -> str:
    if score >= 75:
        return "A — high conviction"
    if score >= 60:
        return "B — watchlist"
    if score >= 45:
        return "C — monitor"
    return "D — avoid / too early"
