"""
Forensic & quality metrics — the analytical core.

Everything here is a *pure function* over normalized financial statements so it
is trivially unit-testable and identical whether called by the live scoring run
or the point-in-time backtest. No I/O, no DB, no globals.

Two data carriers:
  * ``FinancialSnapshot`` — one fiscal period's worth of statement line items.
  * ``PriceSnapshot``     — market data needed for valuation/Altman X4.

Missing inputs return ``None`` rather than raising, because SME disclosures are
patchy and a half-computed score is more honest than a crash. Callers decide how
to treat ``None`` (the scoring engine treats it as "unknown", never as zero).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Num = Optional[float]


# --------------------------------------------------------------------------- #
# Data carriers
# --------------------------------------------------------------------------- #
@dataclass
class FinancialSnapshot:
    """One fiscal period (annual unless noted). All values in the same unit
    (₹ crore is conventional for Indian filings, but the math is unit-agnostic).
    """

    period: str  # e.g. "FY2024"

    # P&L
    revenue: Num = None
    cogs: Num = None  # cost of goods sold
    gross_profit: Num = None
    ebit: Num = None
    ebitda: Num = None
    depreciation: Num = None
    interest: Num = None  # finance cost
    pbt: Num = None
    tax: Num = None
    net_income: Num = None  # PAT
    sga: Num = None  # selling, general & admin

    # Balance sheet
    total_assets: Num = None
    current_assets: Num = None
    cash: Num = None
    receivables: Num = None
    inventory: Num = None
    net_fixed_assets: Num = None  # PP&E net
    current_liabilities: Num = None
    total_liabilities: Num = None
    total_debt: Num = None  # short + long term borrowings
    long_term_debt: Num = None
    equity: Num = None  # shareholders' funds
    retained_earnings: Num = None

    # Cash flow
    operating_cash_flow: Num = None
    capex: Num = None  # positive number = cash spent

    # Capital structure
    shares_outstanding: Num = None

    @property
    def working_capital(self) -> Num:
        return _sub(self.current_assets, self.current_liabilities)

    @property
    def capital_employed(self) -> Num:
        # Total assets - current liabilities (standard ROCE denominator).
        ce = _sub(self.total_assets, self.current_liabilities)
        # Fallback when current liabilities aren't disclosed separately (Screener's
        # condensed balance sheet bundles them): Capital Employed ≈ Equity + Debt.
        if ce is None:
            return _add(self.equity, self.total_debt)
        return ce

    @property
    def free_cash_flow(self) -> Num:
        return _sub(self.operating_cash_flow, self.capex)


@dataclass
class PriceSnapshot:
    price: Num = None
    market_cap: Num = None  # same unit as financials
    shares_outstanding: Num = None


# --------------------------------------------------------------------------- #
# Safe arithmetic helpers — keep None-propagation in one place.
# --------------------------------------------------------------------------- #
def _div(a: Num, b: Num) -> Num:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _sub(a: Num, b: Num) -> Num:
    if a is None or b is None:
        return None
    return a - b


def _ratio(a: Num, b: Num) -> Num:
    """Like _div but guards tiny/negative denominators that make indices blow up
    (used by Beneish where dividing by ~0 receivables is meaningless)."""
    if a is None or b is None or abs(b) < 1e-9:
        return None
    return a / b


# --------------------------------------------------------------------------- #
# Growth
# --------------------------------------------------------------------------- #
def cagr(begin: Num, end: Num, years: int) -> Num:
    """Compound annual growth rate.

    Returns None when undefined. Sign-flips (begin<=0) are not meaningful as a
    geometric rate, so we return None rather than a misleading number — the
    scoring layer scores those cases via absolute turnaround flags instead.
    """
    if begin is None or end is None or years <= 0:
        return None
    if begin <= 0 or end <= 0:
        return None
    return (end / begin) ** (1.0 / years) - 1.0


def series_cagr(values: list[Num], years: int) -> Num:
    """CAGR across the first and last *valid* points of a series spanning
    ``years`` (e.g. 4 annual points -> 3-year CAGR)."""
    if not values:
        return None
    first = next((v for v in values if v is not None), None)
    last = next((v for v in reversed(values) if v is not None), None)
    return cagr(first, last, years)


# --------------------------------------------------------------------------- #
# Profitability & returns
# --------------------------------------------------------------------------- #
def roce(f: FinancialSnapshot) -> Num:
    """EBIT / Capital Employed."""
    return _div(f.ebit, f.capital_employed)


def roe(f: FinancialSnapshot) -> Num:
    return _div(f.net_income, f.equity)


def roa(f: FinancialSnapshot) -> Num:
    return _div(f.net_income, f.total_assets)


def operating_margin(f: FinancialSnapshot) -> Num:
    return _div(f.ebit, f.revenue)


def net_margin(f: FinancialSnapshot) -> Num:
    return _div(f.net_income, f.revenue)


def gross_margin(f: FinancialSnapshot) -> Num:
    gp = f.gross_profit
    if gp is None:
        gp = _sub(f.revenue, f.cogs)
    return _div(gp, f.revenue)


# --------------------------------------------------------------------------- #
# Balance-sheet strength
# --------------------------------------------------------------------------- #
def debt_to_equity(f: FinancialSnapshot) -> Num:
    return _div(f.total_debt, f.equity)


def interest_coverage(f: FinancialSnapshot) -> Num:
    if f.interest is None or f.interest == 0:
        # No interest cost: effectively infinite coverage if EBIT>0.
        return 999.0 if (f.ebit or 0) > 0 else None
    return _div(f.ebit, f.interest)


def current_ratio(f: FinancialSnapshot) -> Num:
    return _div(f.current_assets, f.current_liabilities)


# --------------------------------------------------------------------------- #
# Cash flow & capital efficiency
# --------------------------------------------------------------------------- #
def fcf_yield(f: FinancialSnapshot, p: PriceSnapshot) -> Num:
    return _div(f.free_cash_flow, p.market_cap)


def ocf_to_pat(f: FinancialSnapshot) -> Num:
    """Operating cash flow / net income. < 1 over time = earnings not converting
    to cash = a classic accrual red flag."""
    return _div(f.operating_cash_flow, f.net_income)


def asset_turnover(f: FinancialSnapshot) -> Num:
    return _div(f.revenue, f.total_assets)


def inventory_days(f: FinancialSnapshot) -> Num:
    base = f.cogs if f.cogs not in (None, 0) else f.revenue
    return _div(_mul(365, f.inventory), base)


def debtor_days(f: FinancialSnapshot) -> Num:
    return _div(_mul(365, f.receivables), f.revenue)


def payable_days(f: FinancialSnapshot, payables: Num) -> Num:
    base = f.cogs if f.cogs not in (None, 0) else f.revenue
    return _div(_mul(365, payables), base)


def cash_conversion_cycle(f: FinancialSnapshot, payables: Num = None) -> Num:
    dio = inventory_days(f)
    dso = debtor_days(f)
    dpo = payable_days(f, payables) if payables is not None else 0.0
    if dio is None or dso is None:
        return None
    return dio + dso - (dpo or 0.0)


def _mul(a: Num, b: Num) -> Num:
    if a is None or b is None:
        return None
    return a * b


# --------------------------------------------------------------------------- #
# Piotroski F-Score (0-9) — needs current + prior year.
# --------------------------------------------------------------------------- #
def piotroski_f_score(curr: FinancialSnapshot, prev: FinancialSnapshot) -> dict:
    """Returns {'score': int, 'signals': {name: 0/1/None}, 'available': n}.

    Nine binary tests across profitability, leverage/liquidity, and efficiency.
    Tests with missing inputs score None and are excluded from the total so a
    company with partial data is not unfairly penalised.
    """
    s: dict[str, Optional[int]] = {}

    roa_c, roa_p = roa(curr), roa(prev)
    cfo = curr.operating_cash_flow
    ta = curr.total_assets

    # Profitability
    s["roa_positive"] = _bin(roa_c, lambda x: x > 0)
    s["cfo_positive"] = _bin(cfo, lambda x: x > 0)
    s["roa_improved"] = _bin2(roa_c, roa_p, lambda a, b: a > b)
    # Accruals: CFO/TA > ROA  (cash earnings exceed accounting earnings)
    cfo_ta = _div(cfo, ta)
    s["accruals_ok"] = _bin2(cfo_ta, roa_c, lambda a, b: a > b)

    # Leverage, liquidity, dilution
    lt_lev_c = _div(curr.long_term_debt, curr.total_assets)
    lt_lev_p = _div(prev.long_term_debt, prev.total_assets)
    s["leverage_down"] = _bin2(lt_lev_c, lt_lev_p, lambda a, b: a < b)
    s["current_ratio_up"] = _bin2(
        current_ratio(curr), current_ratio(prev), lambda a, b: a > b
    )
    s["no_dilution"] = _bin2(
        curr.shares_outstanding, prev.shares_outstanding, lambda a, b: a <= b
    )

    # Operating efficiency
    s["gross_margin_up"] = _bin2(
        gross_margin(curr), gross_margin(prev), lambda a, b: a > b
    )
    s["asset_turnover_up"] = _bin2(
        asset_turnover(curr), asset_turnover(prev), lambda a, b: a > b
    )

    available = [v for v in s.values() if v is not None]
    return {
        "score": sum(available),
        "max_available": len(available),
        "signals": s,
    }


def _bin(x: Num, test) -> Optional[int]:
    if x is None:
        return None
    return 1 if test(x) else 0


def _bin2(a: Num, b: Num, test) -> Optional[int]:
    if a is None or b is None:
        return None
    return 1 if test(a, b) else 0


# --------------------------------------------------------------------------- #
# Altman Z-Score — bankruptcy/financial-distress predictor.
# --------------------------------------------------------------------------- #
def altman_z_score(f: FinancialSnapshot, p: PriceSnapshot) -> dict:
    """Original (1968) manufacturing model:

        Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

    X1 Working Capital / Total Assets
    X2 Retained Earnings / Total Assets
    X3 EBIT / Total Assets
    X4 Market Value of Equity / Total Liabilities
    X5 Sales / Total Assets

    Zones: Z>2.99 safe · 1.81–2.99 grey · <1.81 distress.

    For non-manufacturing / emerging-market SMEs the X4 market term dominates and
    can be noisy, so we also return ``z_double_prime`` (Altman EM model) which
    drops X5 and recalibrates — often more appropriate for asset-light SMEs.
    """
    ta = f.total_assets
    x1 = _div(f.working_capital, ta)
    x2 = _div(f.retained_earnings, ta)
    x3 = _div(f.ebit, ta)
    x4 = _div(p.market_cap, f.total_liabilities)
    x5 = _div(f.revenue, ta)

    z = None
    if None not in (x1, x2, x3, x4, x5):
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    # Altman Z'' (EM) — book-value version, no X5:
    # Z'' = 3.25 + 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4_book
    x4_book = _div(f.equity, f.total_liabilities)
    z_dprime = None
    if None not in (x1, x2, x3, x4_book):
        z_dprime = 3.25 + 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4_book

    return {
        "z_score": z,
        "z_double_prime": z_dprime,
        "zone": _altman_zone(z),
        "components": {"x1": x1, "x2": x2, "x3": x3, "x4": x4, "x5": x5},
    }


def _altman_zone(z: Num) -> Optional[str]:
    if z is None:
        return None
    if z > 2.99:
        return "safe"
    if z >= 1.81:
        return "grey"
    return "distress"


# --------------------------------------------------------------------------- #
# Beneish M-Score — earnings-manipulation detector.
# --------------------------------------------------------------------------- #
def beneish_m_score(curr: FinancialSnapshot, prev: FinancialSnapshot) -> dict:
    """Eight-variable model:

        M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
              + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    M > -1.78  => higher probability the company is manipulating earnings.

    Each index compares this year to last. Missing inputs collapse the relevant
    index to its neutral value (1.0, or 0.0 for the accrual term) and we report
    how many of the eight were actually computable so callers can judge
    reliability.
    """
    computed = 0

    # DSRI — Days' Sales in Receivables Index
    rec_rev_c = _ratio(curr.receivables, curr.revenue)
    rec_rev_p = _ratio(prev.receivables, prev.revenue)
    dsri, ok = _index(rec_rev_c, rec_rev_p)
    computed += ok

    # GMI — Gross Margin Index (prior/current; >1 means deteriorating margin)
    gm_c, gm_p = gross_margin(curr), gross_margin(prev)
    gmi, ok = _index(gm_p, gm_c)
    computed += ok

    # AQI — Asset Quality Index (non-current, non-PP&E assets / total assets)
    aq_c = _asset_quality(curr)
    aq_p = _asset_quality(prev)
    aqi, ok = _index(aq_c, aq_p)
    computed += ok

    # SGI — Sales Growth Index
    sgi, ok = _index(curr.revenue, prev.revenue)
    computed += ok

    # DEPI — Depreciation Index
    dep_rate_c = _ratio(curr.depreciation, _add(curr.depreciation, curr.net_fixed_assets))
    dep_rate_p = _ratio(prev.depreciation, _add(prev.depreciation, prev.net_fixed_assets))
    depi, ok = _index(dep_rate_p, dep_rate_c)
    computed += ok

    # SGAI — SG&A Index (SG&A/Sales current vs prior)
    sga_c = _ratio(curr.sga, curr.revenue)
    sga_p = _ratio(prev.sga, prev.revenue)
    sgai, ok = _index(sga_c, sga_p)
    computed += ok

    # LVGI — Leverage Index ((debt+CL)/TA current vs prior)
    lev_c = _ratio(_add(curr.total_debt, curr.current_liabilities), curr.total_assets)
    lev_p = _ratio(_add(prev.total_debt, prev.current_liabilities), prev.total_assets)
    lvgi, ok = _index(lev_c, lev_p)
    computed += ok

    # TATA — Total Accruals to Total Assets
    accruals = None
    if curr.net_income is not None and curr.operating_cash_flow is not None:
        accruals = curr.net_income - curr.operating_cash_flow
    tata = _ratio(accruals, curr.total_assets)
    if tata is not None:
        computed += 1
    tata = tata if tata is not None else 0.0

    m = (
        -4.84
        + 0.92 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )

    return {
        "m_score": m,
        "likely_manipulator": m > -1.78,
        "variables_computed": computed,  # out of 8; low = unreliable
        "components": {
            "DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi,
            "DEPI": depi, "SGAI": sgai, "TATA": tata, "LVGI": lvgi,
        },
    }


def _index(num: Num, den: Num, neutral: float = 1.0) -> tuple[float, int]:
    """Beneish index = num/den, falling back to a neutral 1.0 when uncomputable.
    Returns (value, computed_flag)."""
    v = _ratio(num, den)
    if v is None:
        return neutral, 0
    return v, 1


def _asset_quality(f: FinancialSnapshot) -> Num:
    """(Total assets - current assets - net PP&E) / total assets."""
    if f.total_assets is None:
        return None
    non_quality = f.total_assets
    for part in (f.current_assets, f.net_fixed_assets):
        if part is None:
            return None
        non_quality -= part
    return _div(non_quality, f.total_assets)


def _add(a: Num, b: Num) -> Num:
    if a is None or b is None:
        return None
    return a + b
