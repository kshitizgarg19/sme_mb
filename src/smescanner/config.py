"""Central configuration, loaded from environment / .env.

All tunables (DB URL, LLM endpoint, scoring weights, scrape politeness) live
here so the scrapers, scoring engine, and dashboard share one source of truth.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
REPORTS_DIR = DATA_DIR / "reports"  # downloaded annual reports / concalls


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"), env_prefix="SME_", extra="ignore"
    )

    # --- database ---------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg2://sme:sme@localhost:5432/sme_scanner"
    )

    # --- scraping politeness ---------------------------------------------
    rate_per_host: float = 0.5
    http_timeout: float = 30.0
    max_retries: int = 4
    cache_ttl_hours: int = 12

    # --- local LLM (Ollama by default) -----------------------------------
    llm_provider: str = "ollama"  # ollama | none
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:14b-instruct"  # falls back to llama3.1:8b
    llm_fallback_model: str = "llama3.1:8b"
    llm_timeout: float = 180.0

    # --- universe ---------------------------------------------------------
    # When True we keep companies that have migrated from SME to the main board
    # flagged but in the universe (their track record is the most valuable
    # training signal for the backtest).
    keep_migrated_companies: bool = True

    # --- multibagger score weights (must sum to ~1.0) --------------------
    # These encode the investing philosophy. See scoring/multibagger.py.
    w_growth: float = 0.22
    w_profitability: float = 0.16
    w_balance_sheet: float = 0.12
    w_cash_flow: float = 0.12
    w_management: float = 0.14
    w_capital_efficiency: float = 0.08
    w_valuation: float = 0.08
    w_size_runway: float = 0.08

    # Forensic safety acts as a *gate/penalty*, not a positive weight.
    forensic_penalty_cap: float = 35.0  # max points a clean book can claw back

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider.lower() != "none"


@lru_cache
def get_settings() -> Settings:
    for d in (DATA_DIR, CACHE_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return Settings()
