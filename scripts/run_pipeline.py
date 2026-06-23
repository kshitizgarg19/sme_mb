#!/usr/bin/env python
"""
Daily pipeline orchestrator.

Stages (each independently re-runnable / idempotent):
  1. universe   — refresh NSE Emerge + BSE SME company master
  2. fundamentals — scrape Screener (+ BSE fallback) into annual/quarterly_results
  3. corporate  — announcements, shareholding, insider, bulk deals
  4. metrics    — compute forensic ratios -> computed_metrics
  5. score      — multibagger composite -> multibagger_scores (ranked)
  6. ai         — research notes + AR summaries (if local LLM available)

Run all:        python scripts/run_pipeline.py
Run a subset:   python scripts/run_pipeline.py --stages universe,fundamentals
Schedule daily: see docs/DEPLOYMENT.md (cron / APScheduler).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make src importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smescanner.db.session import fetch_df, get_engine, init_db, upsert  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("pipeline")

ALL_STAGES = ["universe", "fundamentals", "corporate", "metrics", "score", "ai"]
LIMIT: int | None = None  # optional cap on companies scraped (for fast test runs)
SKIP_EXISTING: bool = False  # resume: skip companies that already have fundamentals


def stage_universe() -> None:
    from smescanner.universe.builder import refresh_universe
    n = refresh_universe()
    log.info("universe: %d companies upserted", n)


def stage_fundamentals() -> None:
    import datetime as dt
    import re
    from smescanner.scrapers.screener import ScreenerScraper

    def money(s):  # '₹ 635 Cr.' -> 635.0 ; '₹ 430' -> 430.0
        if not s:
            return None
        m = re.search(r"-?[\d.]+", str(s).replace(",", ""))
        return float(m.group()) if m else None

    scraper = ScreenerScraper()
    today = dt.date.today().isoformat()
    # Prioritise names that carry an NSE symbol — best Screener coverage — so a
    # capped test run gets a high hit rate. A full (uncapped) run covers all.
    where = "WHERE is_active"
    if SKIP_EXISTING:  # resume an interrupted crawl without redoing finished work
        where += " AND company_id NOT IN (SELECT DISTINCT company_id FROM annual_results)"
    sql = (f"SELECT company_id, nse_symbol, bse_symbol, bse_scripcode "
           f"FROM companies {where} ORDER BY (nse_symbol IS NULL), company_id")
    if LIMIT:
        sql += f" LIMIT {int(LIMIT)}"
    companies = fetch_df(sql)
    hits, total = 0, len(companies)
    for i, (_, c) in enumerate(companies.iterrows(), 1):
        # Prefer a ticker symbol; raw BSE scripcodes don't resolve on Screener.
        symbol = c["nse_symbol"] or c["bse_symbol"]
        if not symbol:
            continue
        try:
            data = scraper.fetch(str(symbol))
            if not data or not data["annual"]:
                continue
            cid = int(c["company_id"])
            rows = [{**r, "company_id": cid} for r in data["annual"]]
            upsert("annual_results", rows,
                   conflict_cols=["company_id", "fiscal_year", "is_consolidated"])
            # Capture market cap + price from Screener's header so scoring has a
            # valuation without a separate price feed.
            ratios = data.get("ratios", {})
            mcap = money(ratios.get("Market Cap"))
            price = money(ratios.get("Current Price"))
            if mcap or price:
                upsert("prices", [{"company_id": cid, "trade_date": today,
                                   "close": price, "market_cap": mcap, "source": "screener"}],
                       conflict_cols=["company_id", "trade_date"])
            sh_rows = [{**r, "company_id": cid} for r in data.get("shareholding", [])]
            if sh_rows:
                upsert("shareholding", sh_rows, conflict_cols=["company_id", "period_end"])
            hits += 1
        except Exception:  # noqa: BLE001 — one company must never abort the crawl
            log.warning("fundamentals: %s failed (skipping)", symbol)
        if i % 50 == 0:
            log.info("fundamentals progress: %d/%d processed, %d hits", i, total, hits)
    log.info("fundamentals: %d/%d companies returned data", hits, total)


def stage_corporate() -> None:
    """Announcements, shareholding, insider, bulk deals. Left as wiring points —
    each scraper module is implemented; connect to your trading-day calendar."""
    log.info("corporate: wire NSE/BSE corp scrapers to the date calendar")


def stage_metrics() -> None:
    from smescanner.scoring.financial_quality import (
        build_company_financials, compute_metrics_record)
    import datetime as dt
    today = dt.date.today().isoformat()
    companies = fetch_df("SELECT * FROM companies WHERE is_active")
    done = 0
    for _, c in companies.iterrows():
        try:
            cid = int(c["company_id"])
            annual = fetch_df(
                "SELECT * FROM annual_results WHERE company_id=:cid ORDER BY fiscal_year",
                cid=cid,
            ).to_dict("records")
            if len(annual) < 2:
                continue
            price = fetch_df(
                "SELECT * FROM prices WHERE company_id=:cid ORDER BY trade_date DESC LIMIT 1",
                cid=cid,
            ).to_dict("records")
            cf = build_company_financials(c.to_dict(), annual, price[0] if price else {})
            rec = compute_metrics_record(cf, today)
            rec["company_id"] = cid
            upsert("computed_metrics", [rec], conflict_cols=["company_id", "as_of_date"])
            done += 1
        except Exception:  # noqa: BLE001 — skip the bad row, keep the run alive
            log.warning("metrics: company %s failed (skipping)", c.get("company_id"))
    log.info("metrics: computed for %d companies", done)


def stage_score() -> None:
    from smescanner.scoring.financial_quality import build_company_financials
    from smescanner.scoring.multibagger import score_company
    from smescanner.scoring.verdict import generate_verdict
    import datetime as dt
    today = dt.date.today().isoformat()
    companies = fetch_df("SELECT * FROM companies WHERE is_active")
    results = []
    for _, c in companies.iterrows():
        try:
            cid = int(c["company_id"])
            annual = fetch_df(
                "SELECT * FROM annual_results WHERE company_id=:cid ORDER BY fiscal_year",
                cid=cid,
            ).to_dict("records")
            if len(annual) < 2:
                continue
            price = fetch_df(
                "SELECT * FROM prices WHERE company_id=:cid ORDER BY trade_date DESC LIMIT 1",
                cid=cid,
            ).to_dict("records")
            sh = fetch_df(
                "SELECT * FROM shareholding WHERE company_id=:cid ORDER BY period_end",
                cid=cid,
            ).to_dict("records")
            cf = build_company_financials(c.to_dict(), annual, price[0] if price else {}, sh)
            r = score_company(cf)
            results.append((cid, r, generate_verdict(cf, r)))
        except Exception:  # noqa: BLE001 — skip the bad row, keep ranking the rest
            log.warning("score: company %s failed (skipping)", c.get("company_id"))

    results.sort(key=lambda t: t[1].total_score, reverse=True)
    rows = []
    for rank, (cid, r, v) in enumerate(results, start=1):
        rows.append({
            "company_id": cid, "as_of_date": today, "verdict": v, "sub_scores": r.sub_scores,
            "total_score": r.total_score, "band": r.band, "rank_overall": rank,
            "growth_score": r.sub_scores["growth"]["score"],
            "profitability_score": r.sub_scores["profitability"]["score"],
            "balance_sheet_score": r.sub_scores["balance_sheet"]["score"],
            "cash_flow_score": r.sub_scores["cash_flow"]["score"],
            "management_score": r.sub_scores["management"]["score"],
            "capital_eff_score": r.sub_scores["capital_efficiency"]["score"],
            "valuation_score": r.sub_scores["valuation"]["score"],
            "size_runway_score": r.sub_scores["size_runway"]["score"],
            "forensic_trust": r.forensic.get("trust_multiplier"),
        })
    upsert("multibagger_scores", rows, conflict_cols=["company_id", "as_of_date"])
    log.info("score: ranked %d companies", len(rows))


def stage_ai() -> None:
    log.info("ai: wire ResearchAgent over today's top-N to fill thesis/risks")


STAGE_FN = {
    "universe": stage_universe, "fundamentals": stage_fundamentals,
    "corporate": stage_corporate, "metrics": stage_metrics,
    "score": stage_score, "ai": stage_ai,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default=",".join(ALL_STAGES))
    ap.add_argument("--init-db", action="store_true", help="apply schema first")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap companies scraped in fundamentals (fast test runs)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="resume: skip companies that already have fundamentals")
    args = ap.parse_args()

    global LIMIT, SKIP_EXISTING
    LIMIT = args.limit
    SKIP_EXISTING = args.skip_existing

    get_engine()  # fail fast if DB unreachable
    if args.init_db:
        init_db()

    for stage in args.stages.split(","):
        stage = stage.strip()
        if stage not in STAGE_FN:
            log.warning("unknown stage %s", stage)
            continue
        log.info("=== stage: %s ===", stage)
        try:
            STAGE_FN[stage]()
        except Exception:  # noqa: BLE001
            log.exception("stage %s failed (continuing)", stage)


if __name__ == "__main__":
    main()
