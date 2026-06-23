"""
Bridge: raw DB rows -> FinancialSnapshot list -> cached computed_metrics row.

Keeps the messy mapping from exchange/Screener field names to the clean
``FinancialSnapshot`` carrier in one place, so ``metrics.py`` and
``multibagger.py`` stay pure and statement-shape-agnostic.
"""
from __future__ import annotations

from typing import Any, Optional

from . import metrics as M
from .metrics import FinancialSnapshot, PriceSnapshot
from .multibagger import CompanyFinancials


def snapshot_from_annual(row: dict) -> FinancialSnapshot:
    """Map an ``annual_results`` row dict to a FinancialSnapshot."""
    g = row.get
    return FinancialSnapshot(
        period=f"FY{g('fiscal_year')}",
        revenue=g("revenue"), cogs=g("cogs"), gross_profit=g("gross_profit"),
        ebit=g("ebit"), ebitda=g("ebitda"), depreciation=g("depreciation"),
        interest=g("interest"), pbt=g("pbt"), tax=g("tax"),
        net_income=g("net_profit"), sga=g("sga"),
        total_assets=g("total_assets"), current_assets=g("current_assets"),
        cash=g("cash"), receivables=g("receivables"), inventory=g("inventory"),
        net_fixed_assets=g("net_fixed_assets"),
        current_liabilities=g("current_liabilities"),
        total_liabilities=g("total_liabilities"),
        total_debt=g("total_debt"), long_term_debt=g("long_term_debt"),
        equity=g("equity"), retained_earnings=g("retained_earnings"),
        operating_cash_flow=g("operating_cash_flow"), capex=g("capex"),
        shares_outstanding=g("shares_outstanding"),
    )


def build_company_financials(
    company: dict,
    annual_rows: list[dict],
    price: dict,
    shareholding: Optional[list[dict]] = None,
    insider_net_buy: Optional[float] = None,
    dilution_events: int = 0,
    sector_tailwind: Optional[float] = None,
) -> CompanyFinancials:
    years = [snapshot_from_annual(r) for r in sorted(annual_rows, key=lambda r: r["fiscal_year"])]
    p = PriceSnapshot(
        price=price.get("close"),
        market_cap=price.get("market_cap"),
        shares_outstanding=price.get("shares_out"),  # DB col 'shares_out'
    )

    hold_now = hold_4q = pledge = None
    if shareholding:
        sh = sorted(shareholding, key=lambda r: r["period_end"])
        hold_now = sh[-1].get("promoter_pct")
        pledge = sh[-1].get("pledged_pct_of_total")
        if len(sh) >= 5:
            hold_4q = sh[-5].get("promoter_pct")

    return CompanyFinancials(
        symbol=company.get("nse_symbol") or company.get("bse_symbol") or str(company.get("company_id")),
        name=company.get("name", ""),
        years=years,
        price=p,
        promoter_holding_pct=hold_now,
        promoter_holding_pct_4q_ago=hold_4q,
        pledged_pct=pledge,
        promoter_net_buy_value=insider_net_buy,
        equity_dilution_events=dilution_events,
        sector=company.get("sector"),
        sector_tailwind_score=sector_tailwind,
    )


def compute_metrics_record(cf: CompanyFinancials, as_of_date: str) -> dict[str, Any]:
    """Produce a ``computed_metrics`` row for caching/inspection."""
    years = cf.years
    f = cf.latest
    prev = cf.prev
    rev = [y.revenue for y in years]
    pat = [y.net_income for y in years]
    ocf = [y.operating_cash_flow for y in years]

    piotroski = M.piotroski_f_score(f, prev) if prev else None
    beneish = M.beneish_m_score(f, prev) if prev else None
    altman = M.altman_z_score(f, cf.price)

    return {
        "company_id": None,  # filled by caller
        "as_of_date": as_of_date,
        "fiscal_year": _fy(f.period),
        "revenue_cagr_3y": M.series_cagr(rev[-4:], 3) if len(rev) >= 4 else None,
        "revenue_cagr_5y": M.series_cagr(rev[-6:], 5) if len(rev) >= 6 else None,
        "profit_cagr_3y": M.series_cagr(pat[-4:], 3) if len(pat) >= 4 else None,
        "profit_cagr_5y": M.series_cagr(pat[-6:], 5) if len(pat) >= 6 else None,
        "ocf_cagr_5y": M.series_cagr(ocf[-6:], 5) if len(ocf) >= 6 else None,
        "roce": M.roce(f),
        "roe": M.roe(f),
        "debt_to_equity": M.debt_to_equity(f),
        "interest_cover": M.interest_coverage(f),
        "fcf_yield": M.fcf_yield(f, cf.price),
        "asset_turnover": M.asset_turnover(f),
        "inventory_days": M.inventory_days(f),
        "debtor_days": M.debtor_days(f),
        "cash_conv_cycle": M.cash_conversion_cycle(f),
        "ocf_to_pat": M.ocf_to_pat(f),
        "piotroski": piotroski["score"] if piotroski else None,
        "altman_z": altman["z_score"],
        "beneish_m": beneish["m_score"] if beneish else None,
        "raw": {
            "piotroski": piotroski, "altman": altman, "beneish": beneish,
        },
    }


def _fy(period_label: str) -> Optional[int]:
    digits = "".join(ch for ch in period_label if ch.isdigit())
    return int(digits) if digits else None
