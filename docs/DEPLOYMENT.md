# Deployment Guide

## Local (recommended for development)

```bash
# 1. clone + install
make install               # venv + pip install -r requirements.txt
cp .env.example .env       # adjust DB URL / LLM model if needed

# 2. bring up Postgres + Ollama
make up                    # docker compose up -d
docker exec -it sme_ollama ollama pull qwen2.5:14b-instruct   # or llama3.1:8b

# 3. create schema
make init-db

# 4. first scan (universe -> fundamentals -> metrics -> score)
. .venv/bin/activate
python scripts/run_pipeline.py --init-db        # full run

# 5. dashboard
make dashboard             # http://localhost:8501
```

No GPU? Use `llama3.1:8b` (CPU-friendly) or set `SME_LLM_PROVIDER=none` to run
fully without an LLM — scoring is unaffected; only the narrative notes/AR
summaries fall back to templated text.

## Scheduling the daily update

**cron** (markets close ~15:30 IST; run after EOD data settles, ~21:00 IST):
```cron
0 21 * * 1-5  cd /opt/sme-scanner && .venv/bin/python scripts/run_pipeline.py >> data/scan.log 2>&1
```

**APScheduler** alternative (keeps everything in one process):
```python
from apscheduler.schedulers.blocking import BlockingScheduler
from scripts.run_pipeline import main
sched = BlockingScheduler(timezone="Asia/Kolkata")
sched.add_job(main, "cron", day_of_week="mon-fri", hour=21)
sched.start()
```

Split heavy stages across the evening if you like:
`--stages universe,fundamentals` at 21:00, `--stages corporate,metrics,score,ai`
at 22:30.

## Production notes

- **Resilience.** Stages are idempotent and isolated; a failed source is logged
  to `scan_runs` and skipped. Re-run a single stage with `--stages`.
- **Backups.** `pg_dump sme_scanner` nightly; the DB *is* the product.
- **Scaling scrapes.** The HTTP layer is thread-safe (per-host buckets). For the
  ~1,200-name fundamentals pass, a `ThreadPoolExecutor(max_workers=4–6)` keeps you
  polite while finishing in ~15–20 min. Do **not** parallelise NSE aggressively —
  one cookie session, low concurrency.
- **Proxies.** If a host hardens, set `HTTPS_PROXY` to a rotating residential
  pool; `PoliteSession` honours the standard env vars.
- **Cloud.** Any small VM (2 vCPU / 4 GB) runs the scan + Postgres. Add a GPU box
  only if you want the 14B LLM to summarise the whole universe nightly; otherwise
  summarise on-demand for the top-N from the dashboard.

## Health checks

```bash
python scripts/run_pipeline.py --stages universe   # should upsert ~1,000+ rows
psql $DBURL -c "select count(*) from companies;"
psql $DBURL -c "select name,total_score,band from v_latest_scores order by total_score desc limit 20;"
pytest -q                                           # forensic math regression
```
