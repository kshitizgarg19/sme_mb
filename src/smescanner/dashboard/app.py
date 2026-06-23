"""
Streamlit dashboard.  Run:  streamlit run src/smescanner/dashboard/app.py

Reads exclusively from Postgres (the ETL writes, the dashboard reads — clean
separation). Every panel degrades gracefully to an empty-state message when the
relevant table has no rows yet, so the app is runnable the moment the schema
exists, before the first scan completes.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run` executes this file directly, so `src/` isn't on the import
# path — add it so `import smescanner` resolves no matter how it's launched.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from smescanner.db.session import fetch_df

st.set_page_config(page_title="SME Multibagger Scanner", layout="wide",
                   page_icon="📈")


@st.cache_data(ttl=900)
def q(sql: str, **params) -> pd.DataFrame:
    try:
        return fetch_df(sql, **params)
    except Exception as exc:  # noqa: BLE001 — show the error, don't crash the app
        st.warning(f"Query failed (is the DB up / scanned?): {exc}")
        return pd.DataFrame()


st.title("📈 SME Multibagger Scanner")
st.caption("NSE Emerge + BSE SME · fundamentals-first · not a momentum/TA screen")

tabs = st.tabs([
    "🏆 Top Ranked", "🆕 New Entries", "📉 Falling Scores", "🟢 Promoter Buying",
    "🔁 Bulk Deals", "🚩 Red Flags", "📄 AR Summaries", "📊 Backtest",
])

# --- Top Ranked ----------------------------------------------------------
with tabs[0]:
    c1, c2, c3 = st.columns(3)
    min_score = c1.slider("Min score", 0, 100, 60)
    band = c2.multiselect("Band", ["A — high conviction", "B — watchlist",
                                   "C — monitor", "D — avoid / too early"],
                          default=["A — high conviction", "B — watchlist"])
    exch = c3.multiselect("Exchange", ["NSE_EMERGE", "BSE_SME", "BOTH"],
                          default=["NSE_EMERGE", "BSE_SME", "BOTH"])
    df = q(
        """
        SELECT c.name, c.nse_symbol, c.bse_scripcode, c.exchange, c.sector,
               s.total_score, s.band, s.rank_overall,
               s.growth_score, s.profitability_score, s.management_score,
               s.forensic_trust
        FROM multibagger_scores s
        JOIN companies c ON c.company_id = s.company_id
        WHERE s.as_of_date = (SELECT max(as_of_date) FROM multibagger_scores)
          AND s.total_score >= :min_score
        ORDER BY s.total_score DESC
        """,
        min_score=min_score,
    )
    if not df.empty:
        if band:
            df = df[df["band"].isin(band)]
        if exch:
            df = df[df["exchange"].isin(exch)]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", df.to_csv(index=False), "top_ranked.csv")
    else:
        st.info("No scores yet. Run the pipeline: `python scripts/run_pipeline.py`")

# --- New Entries ---------------------------------------------------------
with tabs[1]:
    st.subheader("New to the top 100 vs. last scan")
    df = q(
        """
        WITH latest AS (SELECT max(as_of_date) d FROM multibagger_scores),
        prev AS (SELECT max(as_of_date) d FROM multibagger_scores
                 WHERE as_of_date < (SELECT d FROM latest))
        SELECT c.name, c.nse_symbol, s.total_score, s.rank_overall
        FROM multibagger_scores s JOIN companies c ON c.company_id=s.company_id
        WHERE s.as_of_date=(SELECT d FROM latest) AND s.rank_overall<=100
          AND c.company_id NOT IN (
            SELECT company_id FROM multibagger_scores
            WHERE as_of_date=(SELECT d FROM prev) AND rank_overall<=100)
        ORDER BY s.rank_overall
        """
    )
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty \
        else st.info("Needs at least two scans to compute entries.")

# --- Falling Scores ------------------------------------------------------
with tabs[2]:
    st.subheader("Biggest score deteriorations (momentum of fundamentals)")
    df = q(
        """
        WITH latest AS (SELECT max(as_of_date) d FROM multibagger_scores),
        prev AS (SELECT max(as_of_date) d FROM multibagger_scores
                 WHERE as_of_date < (SELECT d FROM latest))
        SELECT c.name, c.nse_symbol, l.total_score AS now, p.total_score AS prev,
               (l.total_score - p.total_score) AS delta
        FROM multibagger_scores l
        JOIN multibagger_scores p ON p.company_id=l.company_id
          AND p.as_of_date=(SELECT d FROM prev)
        JOIN companies c ON c.company_id=l.company_id
        WHERE l.as_of_date=(SELECT d FROM latest)
        ORDER BY delta ASC LIMIT 30
        """
    )
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty \
        else st.info("Needs at least two scans.")

# --- Promoter Buying -----------------------------------------------------
with tabs[3]:
    st.subheader("Promoter / insider net buying (last 90 days)")
    df = q(
        """
        SELECT c.name, c.nse_symbol, i.person, i.side, i.quantity, i.value,
               i.trade_date
        FROM insider_trades i JOIN companies c ON c.company_id=i.company_id
        WHERE i.is_promoter AND i.side='BUY'
          AND i.trade_date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY i.value DESC NULLS LAST
        """
    )
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty \
        else st.info("No promoter buys recorded yet.")

# --- Bulk Deals ----------------------------------------------------------
with tabs[4]:
    st.subheader("Bulk/block deals — ⭐ marquee investors highlighted")
    only_marquee = st.checkbox("Only known investors", value=True)
    df = q(
        """
        SELECT c.name, b.client_name, b.side, b.quantity, b.price,
               b.deal_date, b.is_known_investor
        FROM bulk_deals b JOIN companies c ON c.company_id=b.company_id
        WHERE b.deal_date >= CURRENT_DATE - INTERVAL '180 days'
        ORDER BY b.deal_date DESC
        """
    )
    if not df.empty and only_marquee:
        df = df[df["is_known_investor"]]
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty \
        else st.info("No bulk deals recorded yet.")

# --- Red Flags -----------------------------------------------------------
with tabs[5]:
    st.subheader("Governance & forensic red flags")
    df = q(
        """
        SELECT c.name, c.nse_symbol, s.total_score, s.red_flags
        FROM multibagger_scores s JOIN companies c ON c.company_id=s.company_id
        WHERE s.as_of_date=(SELECT max(as_of_date) FROM multibagger_scores)
          AND jsonb_array_length(COALESCE(s.red_flags,'[]'::jsonb)) > 0
        ORDER BY jsonb_array_length(s.red_flags) DESC
        """
    )
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty \
        else st.info("No red flags recorded yet.")

# --- AR Summaries --------------------------------------------------------
with tabs[6]:
    st.subheader("Annual-report business summaries (LLM-extracted, grounded)")
    df = q(
        """
        SELECT c.name, a.fiscal_year, a.business_summary, a.capex_plans,
               a.export_exposure
        FROM annual_reports a JOIN companies c ON c.company_id=a.company_id
        WHERE a.business_summary IS NOT NULL
        ORDER BY a.fiscal_year DESC LIMIT 100
        """
    )
    if not df.empty:
        for _, r in df.iterrows():
            with st.expander(f"{r['name']} — FY{r['fiscal_year']}"):
                st.write(r["business_summary"])
                if r.get("capex_plans"):
                    st.caption(f"Capex: {r['capex_plans']}")
    else:
        st.info("No AR summaries yet.")

# --- Backtest ------------------------------------------------------------
with tabs[7]:
    st.subheader("Strategy backtest (top-20, annual rebalance)")
    st.caption("Populated by `python scripts/run_backtest.py` once price history exists.")
    df = q("SELECT * FROM scan_runs WHERE stage='backtest' ORDER BY started_at DESC LIMIT 1")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty \
        else st.info("Run the backtest to populate this tab.")
