import { sql } from "./db";

export type ScoreRow = {
  company_id: number;
  name: string;
  symbol: string | null;
  exchange: string;
  sector: string | null;
  total_score: number;
  band: string;
  rank_overall: number;
  market_cap: number | null;
  growth_score: number | null;
  profitability_score: number | null;
  balance_sheet_score: number | null;
  cash_flow_score: number | null;
  capital_eff_score: number | null;
  valuation_score: number | null;
  size_runway_score: number | null;
  forensic_trust: number | null;
};

const LATEST = sql`(SELECT max(as_of_date) FROM multibagger_scores)`;

export async function getLatestScores(): Promise<ScoreRow[]> {
  return sql<ScoreRow[]>`
    SELECT c.company_id,
           c.name,
           COALESCE(c.nse_symbol, c.bse_symbol, c.bse_scripcode) AS symbol,
           c.exchange, c.sector,
           s.total_score::float8         AS total_score,
           s.band, s.rank_overall,
           s.growth_score::float8        AS growth_score,
           s.profitability_score::float8 AS profitability_score,
           s.balance_sheet_score::float8 AS balance_sheet_score,
           s.cash_flow_score::float8     AS cash_flow_score,
           s.capital_eff_score::float8   AS capital_eff_score,
           s.valuation_score::float8     AS valuation_score,
           s.size_runway_score::float8   AS size_runway_score,
           s.forensic_trust::float8      AS forensic_trust,
           p.market_cap::float8          AS market_cap
    FROM multibagger_scores s
    JOIN companies c ON c.company_id = s.company_id
    LEFT JOIN LATERAL (
      SELECT market_cap FROM prices
      WHERE company_id = s.company_id ORDER BY trade_date DESC LIMIT 1
    ) p ON true
    WHERE s.as_of_date = ${LATEST}
    ORDER BY s.rank_overall
  `;
}

export type Stats = {
  as_of: string | null;
  total: number;
  band_a: number;
  band_b: number;
  band_c: number;
  band_d: number;
  universe: number;
  with_fundamentals: number;
};

export async function getStats(): Promise<Stats> {
  const [r] = await sql<Stats[]>`
    SELECT to_char(${LATEST}, 'DD Mon YYYY')               AS as_of,
           count(*)::int                                   AS total,
           count(*) FILTER (WHERE band LIKE 'A%')::int     AS band_a,
           count(*) FILTER (WHERE band LIKE 'B%')::int     AS band_b,
           count(*) FILTER (WHERE band LIKE 'C%')::int     AS band_c,
           count(*) FILTER (WHERE band LIKE 'D%')::int     AS band_d,
           (SELECT count(*) FROM companies)::int           AS universe,
           (SELECT count(DISTINCT company_id) FROM annual_results)::int AS with_fundamentals
    FROM multibagger_scores
    WHERE as_of_date = ${LATEST}
  `;
  return r ?? {
    as_of: null, total: 0, band_a: 0, band_b: 0, band_c: 0, band_d: 0,
    universe: 0, with_fundamentals: 0,
  };
}

export type RedFlagRow = {
  company_id: number;
  name: string;
  symbol: string | null;
  total_score: number;
  band: string;
  forensic_trust: number | null;
  piotroski: number | null;
  altman_z: number | null;
  beneish_m: number | null;
  ocf_to_pat: number | null;
};

export async function getRedFlags(): Promise<RedFlagRow[]> {
  return sql<RedFlagRow[]>`
    SELECT c.company_id, c.name,
           COALESCE(c.nse_symbol, c.bse_symbol) AS symbol,
           s.total_score::float8   AS total_score, s.band,
           s.forensic_trust::float8 AS forensic_trust,
           m.piotroski,
           m.altman_z::float8       AS altman_z,
           m.beneish_m::float8      AS beneish_m,
           m.ocf_to_pat::float8     AS ocf_to_pat
    FROM multibagger_scores s
    JOIN companies c ON c.company_id = s.company_id
    LEFT JOIN computed_metrics m
      ON m.company_id = s.company_id AND m.as_of_date = s.as_of_date
    WHERE s.as_of_date = ${LATEST}
      AND COALESCE(s.forensic_trust, 1) < 1.0
    ORDER BY s.forensic_trust ASC NULLS FIRST, s.total_score DESC
  `;
}

export async function getCompany(id: number) {
  const [company] = await sql`
    SELECT c.*,
           s.total_score::float8          AS total_score, s.band, s.rank_overall,
           s.growth_score::float8         AS growth_score,
           s.profitability_score::float8  AS profitability_score,
           s.balance_sheet_score::float8  AS balance_sheet_score,
           s.cash_flow_score::float8      AS cash_flow_score,
           s.management_score::float8     AS management_score,
           s.capital_eff_score::float8    AS capital_eff_score,
           s.valuation_score::float8      AS valuation_score,
           s.size_runway_score::float8    AS size_runway_score,
           s.forensic_trust::float8       AS forensic_trust,
           s.sub_scores, s.thesis, s.risks, s.red_flags, s.verdict
    FROM companies c
    LEFT JOIN multibagger_scores s
      ON s.company_id = c.company_id AND s.as_of_date = ${LATEST}
    WHERE c.company_id = ${id}
  `;
  if (!company) return null;

  const [metrics] = await sql`
    SELECT * FROM computed_metrics
    WHERE company_id = ${id} ORDER BY as_of_date DESC LIMIT 1
  `;
  const annual = await sql`
    SELECT fiscal_year,
           revenue::float8             AS revenue,
           cogs::float8                AS cogs,
           gross_profit::float8        AS gross_profit,
           ebit::float8                AS ebit,
           ebitda::float8              AS ebitda,
           depreciation::float8        AS depreciation,
           interest::float8            AS interest,
           pbt::float8                 AS pbt,
           tax::float8                 AS tax,
           net_profit::float8          AS net_profit,
           total_assets::float8        AS total_assets,
           current_assets::float8      AS current_assets,
           current_liabilities::float8 AS current_liabilities,
           receivables::float8         AS receivables,
           inventory::float8           AS inventory,
           net_fixed_assets::float8    AS net_fixed_assets,
           total_debt::float8          AS total_debt,
           total_liabilities::float8   AS total_liabilities,
           equity::float8              AS equity,
           operating_cash_flow::float8 AS operating_cash_flow,
           capex::float8               AS capex,
           shares_outstanding::float8  AS shares_outstanding
    FROM annual_results WHERE company_id = ${id} ORDER BY fiscal_year
  `;
  const [price] = await sql`
    SELECT close::float8 AS close, market_cap::float8 AS market_cap
    FROM prices WHERE company_id = ${id} ORDER BY trade_date DESC LIMIT 1
  `;
  const shareholding = await sql`
    SELECT to_char(period_end, 'Mon ''YY') AS period,
           period_end,
           promoter_pct::float8 AS promoter_pct,
           fii_pct::float8       AS fii_pct,
           dii_pct::float8       AS dii_pct,
           public_pct::float8    AS public_pct
    FROM shareholding WHERE company_id = ${id} ORDER BY period_end
  `;
  return { company, metrics: metrics ?? null, annual, price: price ?? null, shareholding };
}

export type Peer = {
  company_id: number; name: string; symbol: string | null;
  total_score: number; band: string; market_cap: number | null;
  roce: number | null; revenue_cagr_3y: number | null;
};

/** Sector/industry peers if we have a classification, else nearest-market-cap
 * names on the same exchange — always returns a usable comparison set. */
export async function getPeers(
  companyId: number, sector: string | null, industry: string | null,
  marketCap: number | null, exchange: string,
): Promise<{ basis: string; peers: Peer[] }> {
  const cat = sector || industry;
  const select = sql`
    SELECT c.company_id, c.name, COALESCE(c.nse_symbol, c.bse_symbol) AS symbol,
           s.total_score::float8 AS total_score, s.band,
           p.market_cap::float8  AS market_cap,
           m.roce::float8        AS roce,
           m.revenue_cagr_3y::float8 AS revenue_cagr_3y
    FROM multibagger_scores s
    JOIN companies c ON c.company_id = s.company_id
    LEFT JOIN LATERAL (SELECT market_cap FROM prices WHERE company_id = s.company_id
                       ORDER BY trade_date DESC LIMIT 1) p ON true
    LEFT JOIN computed_metrics m ON m.company_id = s.company_id AND m.as_of_date = s.as_of_date`;

  if (cat) {
    const peers = (await sql`
      ${select} WHERE s.as_of_date = ${LATEST}
        AND COALESCE(c.sector, c.industry) = ${cat}
        AND c.company_id <> ${companyId}
      ORDER BY s.total_score DESC LIMIT 8`) as Peer[];
    if (peers.length) return { basis: cat, peers };
  }
  if (marketCap) {
    const peers = (await sql`
      ${select} WHERE s.as_of_date = ${LATEST} AND c.exchange = ${exchange}
        AND c.company_id <> ${companyId}
      ORDER BY abs(COALESCE(p.market_cap, 0) - ${marketCap}) ASC LIMIT 8`) as Peer[];
    return { basis: "similar size", peers };
  }
  return { basis: "", peers: [] };
}
