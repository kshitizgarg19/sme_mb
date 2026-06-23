# SME Multibagger Scanner

A **fundamentals-first** screener that ranks every NSE Emerge and BSE SME stock by
the probability of becoming a 5x–50x multibagger over 3–10 years. It replicates,
in code, how investors like **Vijay Kedia, Ashish Kacholia, Rakesh Jhunjhunwala
and Porinju Veliyath** actually research small caps — quality, growth, capital
efficiency, promoter conviction, clean books — using only **publicly disclosed**
data.

> Not a momentum scanner. Not a TA scanner. No chart patterns. Every score traces
> to a business fact.

## What it does

- **Universe** — auto-discovers *all* NSE Emerge + BSE SME names daily (no manual
  selection) and keeps the master in sync.
- **Forensic financial engine** — Revenue/PAT/OCF CAGR (3y & 5y), ROCE, ROE, D/E,
  interest cover, FCF yield, working-capital efficiency, cash-conversion cycle,
  **Piotroski F-Score, Altman Z-Score, Beneish M-Score** (all unit-tested against
  hand-computed values).
- **Management engine** — promoter holding trend, pledge, dilution, auditor/ID
  resignations, related-party intensity, promoter/insider buying → a governance
  score + explicit red-flag list.
- **Business engine** — reads annual reports (local LLM) for moat, segments,
  capex, customer/supplier concentration, export exposure.
- **Multibagger score (0–100)** — weighted blend with a **forensic gate** so
  growth can't outscore manipulation flags. Ranked across the whole universe.
- **AI research agent** — local Qwen/Llama writes a grounded thesis, growth
  drivers, risks and red flags per company (no chatbot, no invented numbers).
- **Backtest** — top-20, annual rebalance, point-in-time from 2015: CAGR, max
  drawdown, hit ratio, multibagger count.
- **Dashboard** — Streamlit: Top Ranked · New Entries · Falling Scores · Promoter
  Buying · Bulk Deals (marquee-investor flagged) · Red Flags · AR Summaries.

## Quickstart

```bash
make install && cp .env.example .env
make up                                   # Postgres + Ollama (docker)
docker exec -it sme_ollama ollama pull qwen2.5:14b-instruct
. .venv/bin/activate
python scripts/run_pipeline.py --init-db  # universe -> fundamentals -> metrics -> score
make dashboard                            # http://localhost:8501
```

No GPU / no LLM? Set `SME_LLM_PROVIDER=none` — scoring is unaffected, narratives
become templated. Full guide: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Layout

```
db/schema.sql            # 14-table Postgres schema (single source of truth)
docs/                    # ARCHITECTURE · DATA_SOURCES · DEPLOYMENT
src/smescanner/
  common/http.py         # NSE cookie handshake, BSE headers, rate-limit, retry
  universe/              # nse_emerge · bse_sme · builder (daily auto-update)
  scrapers/              # screener · nse_corp · bse_corp
  scoring/
    metrics.py           # forensic math — pure, tested
    multibagger.py       # composite 0-100 + forensic gate
    management_quality.py · business_quality.py · financial_quality.py
  ai/                    # llm (Ollama) · agent · report_reader
  backtest/engine.py     # point-in-time top-N simulation
  dashboard/app.py       # Streamlit
scripts/run_pipeline.py  # daily orchestrator (--stages, --init-db)
scripts/run_backtest.py
tests/test_metrics.py    # hand-computed forensic assertions
```

## Status

The analytical core (forensic metrics + composite scorer) is implemented and
**verified** (`pytest tests/`). Scrapers and the DB/ETL spine are implemented;
endpoints marked `# VERIFY` should be confirmed against the live exchange sites on
first run (the fallback chain degrades gracefully if a path was renamed). See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3 for the stage-by-stage data flow.

## Disclaimer

Research tooling, **not investment advice**. SME stocks are illiquid and
high-risk. Always do your own primary diligence; treat the score as a screen, not
a signal to buy.
