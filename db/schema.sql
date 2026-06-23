-- =====================================================================
-- SME Multibagger Scanner — PostgreSQL schema
-- =====================================================================
-- Conventions:
--   * money/financial line items: NUMERIC(20,2) in ₹ crore unless noted
--   * ratios/percentages:         NUMERIC(12,4)
--   * every scraped row carries source + as_of for provenance/point-in-time
--   * company_id is the universal FK; (exchange, symbol) and bse scripcode are
--     the natural keys we join external feeds on.
-- Idempotent: safe to re-run. Uses CREATE TABLE IF NOT EXISTS + upsert-friendly
-- unique constraints so the daily ETL can ON CONFLICT DO UPDATE.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- fuzzy name search in dashboard

-- ---------------------------------------------------------------------
-- companies — the master universe (NSE Emerge + BSE SME)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    company_id      BIGSERIAL PRIMARY KEY,
    isin            TEXT UNIQUE,                -- best cross-exchange join key
    nse_symbol      TEXT,
    bse_scripcode   TEXT,
    bse_symbol      TEXT,
    name            TEXT NOT NULL,
    exchange        TEXT NOT NULL,             -- NSE_EMERGE | BSE_SME | BOTH
    sector          TEXT,
    industry        TEXT,
    listing_date    DATE,
    face_value      NUMERIC(12,2),
    is_active       BOOLEAN DEFAULT TRUE,
    migrated_to_main BOOLEAN DEFAULT FALSE,    -- graduated SME->mainboard
    first_seen      DATE DEFAULT CURRENT_DATE,
    last_seen       DATE DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (exchange, nse_symbol),
    UNIQUE (exchange, bse_scripcode)
);
CREATE INDEX IF NOT EXISTS idx_companies_name_trgm ON companies USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_companies_active ON companies (is_active);

-- ---------------------------------------------------------------------
-- prices — daily close + market cap (point-in-time for backtest)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prices (
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    trade_date      DATE NOT NULL,
    close           NUMERIC(20,4),
    volume          BIGINT,
    market_cap      NUMERIC(20,2),
    shares_out      NUMERIC(20,2),
    source          TEXT,
    PRIMARY KEY (company_id, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices (trade_date);

-- ---------------------------------------------------------------------
-- quarterly_results
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quarterly_results (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    period_end      DATE NOT NULL,             -- quarter end e.g. 2024-03-31
    fiscal_label    TEXT,                      -- 'Q4FY24'
    is_consolidated BOOLEAN DEFAULT FALSE,
    revenue         NUMERIC(20,2),
    other_income    NUMERIC(20,2),
    ebitda          NUMERIC(20,2),
    ebit            NUMERIC(20,2),
    depreciation    NUMERIC(20,2),
    interest        NUMERIC(20,2),
    pbt             NUMERIC(20,2),
    tax             NUMERIC(20,2),
    net_profit      NUMERIC(20,2),
    eps             NUMERIC(12,4),
    op_margin       NUMERIC(12,4),
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, period_end, is_consolidated)
);
CREATE INDEX IF NOT EXISTS idx_qr_company ON quarterly_results (company_id, period_end);

-- ---------------------------------------------------------------------
-- annual_results — full P&L + balance sheet + cash flow per FY
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS annual_results (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    fiscal_year     INT NOT NULL,              -- 2024 = FY2023-24
    period_end      DATE,
    is_consolidated BOOLEAN DEFAULT FALSE,
    -- P&L
    revenue         NUMERIC(20,2),
    cogs            NUMERIC(20,2),
    gross_profit    NUMERIC(20,2),
    ebitda          NUMERIC(20,2),
    ebit            NUMERIC(20,2),
    depreciation    NUMERIC(20,2),
    interest        NUMERIC(20,2),
    pbt             NUMERIC(20,2),
    tax             NUMERIC(20,2),
    net_profit      NUMERIC(20,2),
    sga             NUMERIC(20,2),
    eps             NUMERIC(12,4),
    -- Balance sheet
    total_assets        NUMERIC(20,2),
    current_assets      NUMERIC(20,2),
    cash                NUMERIC(20,2),
    receivables         NUMERIC(20,2),
    inventory           NUMERIC(20,2),
    net_fixed_assets    NUMERIC(20,2),
    current_liabilities NUMERIC(20,2),
    total_liabilities   NUMERIC(20,2),
    total_debt          NUMERIC(20,2),
    long_term_debt      NUMERIC(20,2),
    equity              NUMERIC(20,2),
    reserves            NUMERIC(20,2),
    retained_earnings   NUMERIC(20,2),
    -- Cash flow
    operating_cash_flow NUMERIC(20,2),
    investing_cash_flow NUMERIC(20,2),
    financing_cash_flow NUMERIC(20,2),
    capex               NUMERIC(20,2),
    -- structure
    shares_outstanding  NUMERIC(20,2),
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, fiscal_year, is_consolidated)
);
CREATE INDEX IF NOT EXISTS idx_ar_company ON annual_results (company_id, fiscal_year);

-- ---------------------------------------------------------------------
-- shareholding — quarterly pattern + pledge
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shareholding (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    period_end      DATE NOT NULL,
    promoter_pct        NUMERIC(12,4),
    promoter_pledged_pct NUMERIC(12,4),        -- % of promoter holding pledged
    pledged_pct_of_total NUMERIC(12,4),
    fii_pct             NUMERIC(12,4),
    dii_pct             NUMERIC(12,4),
    public_pct          NUMERIC(12,4),
    govt_pct            NUMERIC(12,4),
    num_shareholders    BIGINT,
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, period_end)
);
CREATE INDEX IF NOT EXISTS idx_sh_company ON shareholding (company_id, period_end);

-- ---------------------------------------------------------------------
-- corporate_actions — bonus, split, rights, pref allotment, dividends
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corporate_actions (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    action_type     TEXT NOT NULL,             -- bonus|split|rights|pref_allotment|dividend|qip|buyback
    ex_date         DATE,
    record_date     DATE,
    announced_date  DATE,
    ratio           TEXT,                      -- '1:1', '10:1' etc.
    details         JSONB,
    is_dilutive     BOOLEAN,                   -- rights/pref/QIP = true
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now()
);
-- Expression in the uniqueness rule (COALESCE) requires a unique INDEX, not a
-- table-level UNIQUE constraint, which Postgres rejects for expressions.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_event
    ON corporate_actions (company_id, action_type, COALESCE(ex_date, announced_date));
CREATE INDEX IF NOT EXISTS idx_ca_company ON corporate_actions (company_id, action_type);

-- ---------------------------------------------------------------------
-- management_changes — resignations, auditor/ID changes, appointments
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS management_changes (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    change_type     TEXT NOT NULL,             -- auditor_change|director_resign|cfo_change|kmp_change
    person          TEXT,
    role            TEXT,
    is_resignation  BOOLEAN,
    is_red_flag     BOOLEAN DEFAULT FALSE,     -- auditor/ID resignation = true
    event_date      DATE,
    summary         TEXT,
    source_url      TEXT,
    as_of           TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mc_company ON management_changes (company_id, event_date);

-- ---------------------------------------------------------------------
-- announcements — raw corporate filings (with NLP classification)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS announcements (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    headline        TEXT,
    category        TEXT,                      -- result|order_win|capex|rating|board_meeting|...
    body            TEXT,
    pdf_url         TEXT,
    announced_at    TIMESTAMPTZ,
    sentiment       NUMERIC(6,3),              -- -1..1, optional
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, pdf_url, announced_at)
);
CREATE INDEX IF NOT EXISTS idx_ann_company ON announcements (company_id, announced_at);

-- ---------------------------------------------------------------------
-- annual_reports — downloaded PDFs + extracted narrative
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS annual_reports (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    fiscal_year     INT NOT NULL,
    pdf_url         TEXT,
    local_path      TEXT,
    extracted_text  TEXT,
    business_summary TEXT,                     -- LLM-generated, grounded
    segments        JSONB,
    capex_plans     TEXT,
    moat_notes      TEXT,
    customer_concentration TEXT,
    export_exposure TEXT,
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, fiscal_year)
);

-- ---------------------------------------------------------------------
-- bulk_deals / block_deals
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bulk_deals (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    deal_date       DATE NOT NULL,
    deal_type       TEXT,                      -- bulk|block
    client_name     TEXT,
    side            TEXT,                      -- BUY|SELL
    quantity        BIGINT,
    price           NUMERIC(20,4),
    exchange        TEXT,
    is_known_investor BOOLEAN DEFAULT FALSE,   -- matched against marquee-investor list
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, deal_date, client_name, side, quantity)
);
CREATE INDEX IF NOT EXISTS idx_bd_company ON bulk_deals (company_id, deal_date);
CREATE INDEX IF NOT EXISTS idx_bd_investor ON bulk_deals (is_known_investor) WHERE is_known_investor;

-- ---------------------------------------------------------------------
-- insider_trades — SAST/PIT promoter & designated-person dealings
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS insider_trades (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    person          TEXT,
    is_promoter     BOOLEAN,
    side            TEXT,                      -- BUY|SELL|PLEDGE|REVOKE
    quantity        BIGINT,
    value           NUMERIC(20,2),
    mode            TEXT,                      -- market|off-market|pledge
    trade_date      DATE,
    disclosed_date  DATE,
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, person, trade_date, side, quantity)
);
CREATE INDEX IF NOT EXISTS idx_it_company ON insider_trades (company_id, trade_date);

-- ---------------------------------------------------------------------
-- ratings — credit ratings + actions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ratings (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    agency          TEXT,                      -- CRISIL|ICRA|CARE|India Ratings|Acuite
    instrument      TEXT,
    rating          TEXT,
    outlook         TEXT,
    action          TEXT,                      -- assigned|upgrade|downgrade|reaffirm|withdraw
    rating_date     DATE,
    rationale_url   TEXT,
    source          TEXT,
    as_of           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (company_id, agency, instrument, rating_date)
);

-- ---------------------------------------------------------------------
-- computed_metrics — derived ratios cached per company per FY
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS computed_metrics (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    as_of_date      DATE NOT NULL,
    fiscal_year     INT,
    revenue_cagr_3y NUMERIC(12,4),
    revenue_cagr_5y NUMERIC(12,4),
    profit_cagr_3y  NUMERIC(12,4),
    profit_cagr_5y  NUMERIC(12,4),
    ocf_cagr_5y     NUMERIC(12,4),
    roce            NUMERIC(12,4),
    roe             NUMERIC(12,4),
    debt_to_equity  NUMERIC(12,4),
    interest_cover  NUMERIC(12,4),
    fcf_yield       NUMERIC(12,4),
    asset_turnover  NUMERIC(12,4),
    inventory_days  NUMERIC(12,4),
    debtor_days     NUMERIC(12,4),
    cash_conv_cycle NUMERIC(12,4),
    ocf_to_pat      NUMERIC(12,4),
    piotroski       INT,
    altman_z        NUMERIC(12,4),
    beneish_m       NUMERIC(12,4),
    raw             JSONB,                     -- full evidence dict
    UNIQUE (company_id, as_of_date)
);

-- ---------------------------------------------------------------------
-- multibagger_scores — the ranked output, history-preserving
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS multibagger_scores (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    as_of_date      DATE NOT NULL,
    total_score     NUMERIC(6,2),
    band            TEXT,                      -- A/B/C/D
    rank_overall    INT,
    -- sub-scores (0-100)
    growth_score        NUMERIC(6,2),
    profitability_score NUMERIC(6,2),
    balance_sheet_score NUMERIC(6,2),
    cash_flow_score     NUMERIC(6,2),
    management_score    NUMERIC(6,2),
    capital_eff_score   NUMERIC(6,2),
    valuation_score     NUMERIC(6,2),
    size_runway_score   NUMERIC(6,2),
    forensic_trust      NUMERIC(6,3),          -- 0-1 multiplier applied
    sub_scores      JSONB,                     -- full evidence for the UI/agent
    thesis          TEXT,                      -- AI-generated investment thesis
    risks           TEXT,
    red_flags       JSONB,
    UNIQUE (company_id, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_ms_date_rank ON multibagger_scores (as_of_date, rank_overall);
CREATE INDEX IF NOT EXISTS idx_ms_score ON multibagger_scores (as_of_date, total_score DESC);

-- ---------------------------------------------------------------------
-- scan_runs — pipeline audit log
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_date        DATE DEFAULT CURRENT_DATE,
    stage           TEXT,                      -- universe|scrape|metrics|score|ai
    status          TEXT,                      -- ok|partial|failed
    companies_seen  INT,
    companies_scored INT,
    notes           TEXT,
    started_at      TIMESTAMPTZ DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

-- ---------------------------------------------------------------------
-- Convenience view: latest score per company
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_latest_scores AS
SELECT DISTINCT ON (s.company_id)
    c.company_id, c.name, c.nse_symbol, c.bse_scripcode, c.exchange, c.sector,
    s.as_of_date, s.total_score, s.band, s.rank_overall, s.thesis
FROM multibagger_scores s
JOIN companies c ON c.company_id = s.company_id
ORDER BY s.company_id, s.as_of_date DESC;
