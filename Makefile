.PHONY: help install init-db universe scan resume dashboard test lint backtest
PY := python3

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## install deps (use a venv if you prefer to isolate from other projects)
	pip install -r requirements.txt

init-db:  ## create schema in the running Postgres
	$(PY) scripts/run_pipeline.py --init-db --stages universe

universe: ## refresh the SME universe only (~5s)
	$(PY) scripts/run_pipeline.py --stages universe

scan:     ## full daily pipeline (caffeinate: won't sleep mid-run)
	caffeinate -i $(PY) scripts/run_pipeline.py

resume:   ## resume an interrupted crawl — skips already-scraped companies
	caffeinate -i $(PY) scripts/run_pipeline.py --stages fundamentals,metrics,score --skip-existing

dashboard: ## launch the Streamlit dashboard on http://localhost:8501
	PYTHONPATH=src $(PY) -m streamlit run src/smescanner/dashboard/app.py --server.address localhost

backtest: ## run the strategy backtest
	$(PY) scripts/run_backtest.py

test:     ## run unit tests
	PYTHONPATH=src $(PY) -m pytest -q

lint:     ## ruff check
	$(PY) -m ruff check src tests
