# Architecture

## 1. Design principles

1. **Fundamentals first.** No price/volume momentum, no chart patterns. Every
   point of the score traces to a business fact (CAGR, ROCE, cash conversion,
   promoter behaviour, forensic flag).
2. **Provenance everywhere.** Every scraped row carries `source` + `as_of`. The
   backtest is point-in-time: a score on date *D* uses only filings published on
   or before *D*. No look-ahead.
3. **Pure scoring core.** `scoring/metrics.py` and `scoring/multibagger.py` are
   pure functions over plain dataclasses — identical whether driven by the live
   DB or a backtest fixture, and unit-tested against hand-computed values.
4. **Degrade, never crash.** A broken endpoint, a missing line item, or an
   offline LLM reduces coverage/quality; it never aborts the pipeline. Missing
   inputs yield `None` (treated as "unknown", never silently as zero).
5. **Free sources first.** Paid feeds are optional drop-in upgrades behind the
   same scraper interfaces.

## 2. Component map

```
                          ┌─────────────────────────────────────────┐
                          │              SCHEDULER (cron)            │
                          │        run_pipeline.py  (daily)          │
                          └───────────────┬─────────────────────────┘
                                          │
        ┌───────────────┬─────────────────┼──────────────────┬───────────────┐
        ▼               ▼                 ▼                  ▼               ▼
 ┌────────────┐  ┌────────────┐    ┌────────────┐    ┌────────────┐   ┌────────────┐
 │  UNIVERSE  │  │  SCRAPERS  │    │   METRICS  │    │  SCORING   │   │ AI AGENT   │
 │ nse_emerge │  │ screener   │    │ metrics.py │    │ multibagger│   │ llm(Ollama)│
 │ bse_sme    │  │ nse_corp   │    │ forensic   │    │ mgmt/biz   │   │ report_rdr │
 │ builder    │  │ bse_corp   │    │ (Piotroski │    │ quality    │   │ agent      │
 └─────┬──────┘  └─────┬──────┘    │  Altman/   │    └─────┬──────┘   └─────┬──────┘
       │               │           │  Beneish)  │          │                │
       │               │           └─────┬──────┘          │                │
       ▼               ▼                 ▼                  ▼                ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                          PostgreSQL  (schema.sql)                              │
 │  companies · prices · annual/quarterly_results · shareholding · corp_actions  │
 │  announcements · annual_reports · bulk_deals · insider_trades · ratings       │
 │  computed_metrics · multibagger_scores · scan_runs                            │
 └──────────────────────────────────────┬───────────────────────────────────────┘
                                         ▼
                          ┌──────────────────────────────┐
                          │   Streamlit dashboard (read)  │
                          │  Top Ranked · New Entries ·   │
                          │  Falling Scores · Promoter Buy│
                          │  Bulk Deals · Red Flags · AR  │
                          └──────────────────────────────┘
```

The HTTP layer (`common/http.py`) sits under every scraper: per-host token-bucket
rate limiting, exponential backoff, rotating browser fingerprints, and the
NSE cookie handshake / BSE header set.

## 3. Data flow (one daily run)

| # | Stage | Input | Output table | Idempotent key |
|---|-------|-------|--------------|----------------|
| 1 | `universe` | NSE SME bhavcopy/index, BSE list-of-scrips | `companies` | `isin` / `(exchange,symbol)` |
| 2 | `fundamentals` | Screener (BSE fallback) | `annual_results`, `quarterly_results` | `(company_id, fiscal_year, is_consolidated)` |
| 3 | `corporate` | NSE/BSE corp APIs | `announcements`, `shareholding`, `insider_trades`, `bulk_deals`, `corporate_actions`, `ratings` | per-table natural key |
| 4 | `metrics` | `annual_results` + `prices` | `computed_metrics` | `(company_id, as_of_date)` |
| 5 | `score` | `computed_metrics` + `shareholding` + `insider_trades` | `multibagger_scores` (ranked) | `(company_id, as_of_date)` |
| 6 | `ai` | scores + `annual_reports` | `multibagger_scores.thesis/risks/red_flags`, `annual_reports.business_summary` | — |

Each stage is independently re-runnable (`--stages`). Failures are logged to
`scan_runs` and the pipeline continues, so one dead source never blocks a scan.

## 4. The scoring model

Composite 0–100 = weighted blend of eight sub-scores, then multiplied by a
**forensic trust multiplier** (0–1). Forensic safety is a *gate*, not a positive
weight: growth cannot outscore manipulation flags.

| Sub-score | Weight | Captures | Investor lens |
|-----------|-------:|----------|---------------|
| Growth | 0.22 | Revenue/PAT/OCF CAGR (3y & 5y) | "the runway" |
| Profitability | 0.16 | ROCE (3y avg), ROE, margins | Kacholia: durable high ROCE |
| Balance sheet | 0.12 | D/E, interest cover, current ratio | survive the downturn |
| Cash flow | 0.12 | OCF/PAT conversion, FCF yield | earnings → cash |
| Management | 0.14 | Promoter holding/trend, pledge, dilution, buying | Kedia: "right management" |
| Capital efficiency | 0.08 | Asset turnover, cash-conversion cycle | capital-light scaling |
| Valuation | 0.08 | PEG, P/E vs growth | room to re-rate |
| Size / runway | 0.08 | Small mcap + small base × sector tailwind | Kedia SMILE |

Forensic penalty inputs: Piotroski ≤3 (−0.15), Beneish manipulator flag (−0.25),
Altman distress (−0.20), chronic OCF<50% of PAT (−0.15); capped so trust ≥ 0.4.

Weights live in `config.py` / `.env` — tune them without touching code, and the
backtest tells you whether your tuning would have worked.

## 5. Why these legends' processes map to code

- **Vijay Kedia — SMILE**: *Small in size* → `size_runway` rewards small mcap and
  small absolute revenue; *Large in aspiration / market potential* → sector
  tailwind overlay + capacity-expansion flag from the annual report.
- **Ashish Kacholia — niche category leaders**: high & durable ROCE, healthy gross
  margin (pricing power) → `profitability` + `business_quality`.
- **Rakesh Jhunjhunwala — quality + longevity + management**: low debt, cash
  conversion, promoter conviction → `balance_sheet` + `cash_flow` + `management`.
- **Porinju — governance-aware contrarian**: red-flag tracker + forensic gate keep
  cheap-but-broken names out of band A.

## 6. Technology choices

| Concern | Choice | Why |
|--------|--------|-----|
| Store | PostgreSQL 16 | JSONB for evidence blobs, `pg_trgm` for name search, upserts |
| ORM | SQLAlchemy Core + `schema.sql` | one DDL source of truth, no model drift |
| Scrape | requests + bs4/lxml + pandas | no headless browser needed; all endpoints are HTML/JSON |
| LLM | Ollama (Qwen 2.5 / Llama 3.1) | local, free, private; HTTP not SDK = swappable |
| UI | Streamlit | fastest path to an analyst-usable dashboard |
| Schedule | cron / APScheduler | trivial daily trigger |

See [DATA_SOURCES.md](DATA_SOURCES.md) for the per-source collection plan and
[DEPLOYMENT.md](DEPLOYMENT.md) to run it.
```
