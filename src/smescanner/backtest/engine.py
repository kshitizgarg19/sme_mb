"""
Backtest: would the scanner's top-N have worked?

Methodology (survivorship- and look-ahead-aware):
  * Rebalance annually after results season (default 1 Sept, so FY data is
    actually published — using a 31 Mar FY-end before it is filed is look-ahead).
  * At each rebalance, score every company using ONLY statements with a filing
    date <= rebalance date (point-in-time), then equal-weight the top N.
  * Hold to the next rebalance; a name that delists/gets acquired is marked with
    its last traded price (no silent survivorship drop).

Outputs: equity curve, CAGR, max drawdown, annual hit ratio, and the count of
2x / 5x / 10x names — the metric that actually matters for a multibagger strategy.

Data is supplied via two callables so this module is pure and unit-testable, and
identical whether fed from Postgres or a CSV fixture:
  * ``universe_asof(date) -> list[CompanyFinancials]`` (point-in-time)
  * ``forward_return(symbol, start, end) -> float`` (total return over hold)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from ..scoring.multibagger import CompanyFinancials, score_company

log = logging.getLogger("smescanner.backtest")


@dataclass
class Holding:
    symbol: str
    name: str
    score: float
    ret: Optional[float] = None  # total return over the holding period


@dataclass
class RebalancePeriod:
    start: date
    end: date
    holdings: list[Holding] = field(default_factory=list)

    @property
    def period_return(self) -> Optional[float]:
        rets = [h.ret for h in self.holdings if h.ret is not None]
        return sum(rets) / len(rets) if rets else None  # equal weight


@dataclass
class BacktestResult:
    periods: list[RebalancePeriod]
    equity_curve: list[tuple[date, float]]

    @property
    def cagr(self) -> Optional[float]:
        if len(self.equity_curve) < 2:
            return None
        (d0, v0), (d1, v1) = self.equity_curve[0], self.equity_curve[-1]
        years = (d1 - d0).days / 365.25
        if years <= 0 or v0 <= 0 or v1 <= 0:
            return None
        return (v1 / v0) ** (1 / years) - 1

    @property
    def max_drawdown(self) -> float:
        peak = -1e18
        mdd = 0.0
        for _, v in self.equity_curve:
            peak = max(peak, v)
            if peak > 0:
                mdd = min(mdd, v / peak - 1)
        return mdd

    @property
    def hit_ratio(self) -> Optional[float]:
        wins = total = 0
        for p in self.periods:
            for h in p.holdings:
                if h.ret is None:
                    continue
                total += 1
                if h.ret > 0:
                    wins += 1
        return wins / total if total else None

    def multibagger_counts(self) -> dict[str, int]:
        counts = {"2x": 0, "5x": 0, "10x": 0}
        for p in self.periods:
            for h in p.holdings:
                if h.ret is None:
                    continue
                if h.ret >= 9.0:
                    counts["10x"] += 1
                if h.ret >= 4.0:
                    counts["5x"] += 1
                if h.ret >= 1.0:
                    counts["2x"] += 1
        return counts

    def summary(self) -> dict:
        return {
            "cagr": self.cagr,
            "max_drawdown": self.max_drawdown,
            "hit_ratio": self.hit_ratio,
            "multibagger_counts": self.multibagger_counts(),
            "periods": len(self.periods),
            "final_equity": self.equity_curve[-1][1] if self.equity_curve else None,
        }


def run_backtest(
    rebalance_dates: list[date],
    universe_asof: Callable[[date], list[CompanyFinancials]],
    forward_return: Callable[[str, date, date], Optional[float]],
    top_n: int = 20,
    start_equity: float = 100.0,
) -> BacktestResult:
    periods: list[RebalancePeriod] = []
    equity = start_equity
    curve: list[tuple[date, float]] = [(rebalance_dates[0], equity)]

    for start, end in zip(rebalance_dates, rebalance_dates[1:]):
        universe = universe_asof(start)
        ranked = sorted(
            (score_company(c) for c in universe),
            key=lambda r: r.total_score, reverse=True,
        )[:top_n]

        period = RebalancePeriod(start=start, end=end)
        for r in ranked:
            ret = forward_return(r.symbol, start, end)
            period.holdings.append(Holding(symbol=r.symbol, name=r.name,
                                           score=r.total_score, ret=ret))
        pr = period.period_return
        if pr is not None:
            equity *= (1 + pr)
        periods.append(period)
        curve.append((end, equity))
        log.info("Rebalance %s: %d names, period return %.1f%%",
                 start, len(period.holdings), (pr or 0) * 100)

    return BacktestResult(periods=periods, equity_curve=curve)
