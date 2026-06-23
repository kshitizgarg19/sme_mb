#!/usr/bin/env python
"""
Strategy backtest runner: top-N, annual rebalance, from 2015.

Wires the pure ``backtest.engine`` to Postgres via two point-in-time loaders:
  * universe_asof(date)  -> CompanyFinancials built only from filings with
                            period_end + filing lag <= date (no look-ahead)
  * forward_return(sym, start, end) -> total return from prices

Requires populated ``prices`` + ``annual_results`` history. With sparse SME price
history the engine still runs on whatever names have data and reports coverage —
it never silently drops survivors. Writes a summary row to ``scan_runs``.
"""
from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smescanner.backtest.engine import run_backtest                # noqa: E402
from smescanner.db.session import fetch_df                          # noqa: E402
from smescanner.scoring.financial_quality import build_company_financials  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backtest")

# Rebalance 1 Sept each year so FY (31 Mar) statements are actually filed.
REBALANCE_DATES = [dt.date(y, 9, 1) for y in range(2015, dt.date.today().year + 1)]
FILING_LAG_DAYS = 180  # statements published ~within 6 months of FY end


def universe_asof(asof: dt.date):
    companies = fetch_df("SELECT * FROM companies")
    out = []
    for _, c in companies.iterrows():
        cid = int(c["company_id"])
        annual = fetch_df(
            "SELECT * FROM annual_results WHERE company_id=:cid "
            "AND period_end <= :cutoff ORDER BY fiscal_year",
            cid=cid, cutoff=(asof - dt.timedelta(days=FILING_LAG_DAYS)),
        ).to_dict("records")
        if len(annual) < 2:
            continue
        price = fetch_df(
            "SELECT * FROM prices WHERE company_id=:cid AND trade_date <= :asof "
            "ORDER BY trade_date DESC LIMIT 1", cid=cid, asof=asof,
        ).to_dict("records")
        out.append(build_company_financials(c.to_dict(), annual, price[0] if price else {}))
    log.info("as-of %s: %d scorable companies", asof, len(out))
    return out


def forward_return(symbol: str, start: dt.date, end: dt.date):
    rows = fetch_df(
        "SELECT p.trade_date, p.close FROM prices p JOIN companies c "
        "ON c.company_id=p.company_id WHERE (c.nse_symbol=:s OR c.bse_symbol=:s) "
        "AND p.trade_date IN ("
        "  (SELECT min(trade_date) FROM prices p2 JOIN companies c2 ON c2.company_id=p2.company_id "
        "   WHERE (c2.nse_symbol=:s OR c2.bse_symbol=:s) AND p2.trade_date>=:start),"
        "  (SELECT max(trade_date) FROM prices p3 JOIN companies c3 ON c3.company_id=p3.company_id "
        "   WHERE (c3.nse_symbol=:s OR c3.bse_symbol=:s) AND p3.trade_date<=:end))"
        " ORDER BY p.trade_date", s=symbol, start=start, end=end,
    )
    if len(rows) < 2:
        return None
    p0, p1 = rows.iloc[0]["close"], rows.iloc[-1]["close"]
    if not p0 or p0 <= 0:
        return None
    return p1 / p0 - 1.0


def main() -> None:
    result = run_backtest(REBALANCE_DATES, universe_asof, forward_return, top_n=20)
    s = result.summary()
    print("\n=== BACKTEST SUMMARY (top-20, annual) ===")
    print(f"  CAGR            : {None if s['cagr'] is None else f'{s['cagr']:.1%}'}")
    print(f"  Max drawdown    : {s['max_drawdown']:.1%}")
    print(f"  Hit ratio       : {None if s['hit_ratio'] is None else f'{s['hit_ratio']:.1%}'}")
    print(f"  Multibaggers    : {s['multibagger_counts']}")
    print(f"  Final equity    : {s['final_equity']}  (start 100)")


if __name__ == "__main__":
    main()
