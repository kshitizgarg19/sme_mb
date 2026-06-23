"""
Unit tests for the forensic/quality math.

Fixtures use hand-computed expected values (see comments) so a regression in any
formula is caught immediately. These tests have NO external dependencies — they
exercise ``smescanner.scoring.metrics`` in isolation (no DB, no network, no LLM),
so `pytest tests/test_metrics.py` runs on a bare checkout.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from smescanner.scoring import metrics as M
from smescanner.scoring.metrics import FinancialSnapshot, PriceSnapshot


# A clean, improving growth company across two years.
PREV = FinancialSnapshot(
    period="FY2023", revenue=100, cogs=60, gross_profit=40, ebit=18,
    depreciation=5, interest=2, net_income=12, sga=10,
    total_assets=120, current_assets=60, cash=10, receivables=20, inventory=15,
    net_fixed_assets=40, current_liabilities=30, total_liabilities=50,
    total_debt=25, long_term_debt=15, equity=70, retained_earnings=40,
    operating_cash_flow=15, capex=8, shares_outstanding=10,
)
CURR = FinancialSnapshot(
    period="FY2024", revenue=130, cogs=75, gross_profit=55, ebit=26,
    depreciation=6, interest=2, net_income=18, sga=12,
    total_assets=140, current_assets=72, cash=15, receivables=24, inventory=17,
    net_fixed_assets=45, current_liabilities=32, total_liabilities=52,
    total_debt=22, long_term_debt=12, equity=88, retained_earnings=58,
    operating_cash_flow=22, capex=9, shares_outstanding=10,
)
PRICE = PriceSnapshot(price=20.0, market_cap=200.0, shares_outstanding=10)


def test_cagr_basic():
    assert M.cagr(100, 200, 3) == pytest.approx(2 ** (1 / 3) - 1, abs=1e-6)
    assert M.cagr(0, 200, 3) is None          # undefined base
    assert M.cagr(100, -50, 3) is None        # sign flip not a geometric rate


def test_series_cagr_skips_gaps():
    assert M.series_cagr([100, None, 200], 2) == pytest.approx(2 ** 0.5 - 1, abs=1e-6)


def test_core_ratios():
    assert M.roce(CURR) == pytest.approx(26 / (140 - 32), abs=1e-6)
    assert M.roe(CURR) == pytest.approx(18 / 88, abs=1e-6)
    assert M.debt_to_equity(CURR) == pytest.approx(22 / 88, abs=1e-6)
    assert M.interest_coverage(CURR) == pytest.approx(26 / 2, abs=1e-6)
    assert M.ocf_to_pat(CURR) == pytest.approx(22 / 18, abs=1e-6)


def test_piotroski_perfect_nine():
    # Every one of the 9 signals improves YoY in this fixture.
    res = M.piotroski_f_score(CURR, PREV)
    assert res["max_available"] == 9
    assert res["score"] == 9, res["signals"]


def test_altman_safe_zone():
    res = M.altman_z_score(CURR, PRICE)
    # Hand-computed Z ≈ 4.77 -> safe
    assert res["z_score"] == pytest.approx(4.77, abs=0.05)
    assert res["zone"] == "safe"


def test_beneish_clean_company_not_flagged():
    res = M.beneish_m_score(CURR, PREV)
    # Hand-computed M ≈ -2.39 (< -1.78 threshold) -> not a manipulator
    assert res["m_score"] == pytest.approx(-2.39, abs=0.06)
    assert res["likely_manipulator"] is False
    assert res["variables_computed"] == 8


def test_missing_data_returns_none_not_crash():
    empty = FinancialSnapshot(period="FY2024")
    assert M.roce(empty) is None
    assert M.altman_z_score(empty, PriceSnapshot())["z_score"] is None
    # Piotroski still returns a structure, just with fewer available signals.
    res = M.piotroski_f_score(empty, empty)
    assert res["max_available"] <= 9
