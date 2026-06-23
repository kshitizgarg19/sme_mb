// Pure analysis engine — institutional-style. Computes every key ratio per
// fiscal year from raw statements, plus a transparent valuation/scenario model
// (the "kitna badh sakta · risk · time · kab becho" answer). No I/O; usable
// server- or client-side.

export type AnnualRow = {
  fiscal_year: number;
  revenue: number | null; cogs: number | null; gross_profit: number | null;
  ebit: number | null; ebitda: number | null; depreciation: number | null; interest: number | null;
  pbt: number | null; tax: number | null; net_profit: number | null;
  total_assets: number | null; current_assets: number | null; current_liabilities: number | null;
  receivables: number | null; inventory: number | null; net_fixed_assets: number | null;
  total_debt: number | null; total_liabilities: number | null; equity: number | null;
  operating_cash_flow: number | null; capex: number | null; shares_outstanding: number | null;
};

const n = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
};
const div = (a: number | null, b: number | null) => (a === null || b === null || b === 0 ? null : a / b);
function cagr(first: number | null, last: number | null, years: number) {
  if (first === null || last === null || first <= 0 || last <= 0 || years <= 0) return null;
  return (last / first) ** (1 / years) - 1;
}

export type YearMetrics = {
  fy: number; label: string;
  revenue: number | null; net_profit: number | null; ebitda: number | null; ocf: number | null;
  gross_margin: number | null; op_margin: number | null; net_margin: number | null;
  roce: number | null; roe: number | null; roa: number | null;
  debt_to_equity: number | null; interest_cover: number | null;
  asset_turnover: number | null; ocf_to_pat: number | null;
  rev_growth: number | null; pat_growth: number | null;
};

export function perYearMetrics(rowsRaw: AnnualRow[]): YearMetrics[] {
  const rows = [...rowsRaw]
    .map((r) => ({ ...r, fiscal_year: Number(r.fiscal_year) }))
    .sort((a, b) => a.fiscal_year - b.fiscal_year);
  return rows.map((r, i) => {
    const prev = i > 0 ? rows[i - 1] : null;
    const rev = n(r.revenue);
    const gp = n(r.gross_profit) ?? (rev !== null && n(r.cogs) !== null ? rev - (n(r.cogs) as number) : null);
    // Capital employed = TA − current liabilities; fall back to Equity + Debt
    // when current liabilities aren't broken out (Screener's condensed BS).
    const ta = n(r.total_assets), cl = n(r.current_liabilities);
    const eq = n(r.equity), td = n(r.total_debt);
    const capEmp = ta !== null && cl !== null ? ta - cl
      : eq !== null && td !== null ? eq + td : null;
    const pat = n(r.net_profit);
    return {
      fy: r.fiscal_year, label: `FY${String(r.fiscal_year).slice(2)}`,
      revenue: rev, net_profit: pat, ebitda: n(r.ebitda), ocf: n(r.operating_cash_flow),
      gross_margin: div(gp, rev),
      op_margin: div(n(r.ebit), rev),
      net_margin: div(pat, rev),
      roce: div(n(r.ebit), capEmp),
      roe: div(pat, n(r.equity)),
      roa: div(pat, n(r.total_assets)),
      debt_to_equity: div(n(r.total_debt), n(r.equity)),
      interest_cover: n(r.interest) ? div(n(r.ebit), n(r.interest)) : null,
      asset_turnover: div(rev, n(r.total_assets)),
      ocf_to_pat: div(n(r.operating_cash_flow), pat),
      rev_growth: prev ? div((rev ?? 0) - (n(prev.revenue) ?? 0), n(prev.revenue)) : null,
      pat_growth: prev && n(prev.net_profit) && (n(prev.net_profit) as number) > 0
        ? div((pat ?? 0) - (n(prev.net_profit) as number), n(prev.net_profit)) : null,
    };
  });
}

export type Scenario = {
  name: "Bear" | "Base" | "Bull";
  growth: number; exitPE: number;
  targetPrice: number | null; upside: number | null; cagr: number | null;
};

export type ValuationModel = {
  currentPrice: number | null; pe: number | null; horizon: number;
  histPatCagr: number | null;
  scenarios: Scenario[];
  risk: { level: string; score: number; reasons: string[] };
  buyZone: [number, number] | null;
  sellTarget: number | null;
};

/** Earnings-growth × exit-multiple model — how big-cap PMs frame expected return.
 * Projects PAT forward at a (capped) growth rate, applies a re-rated/de-rated
 * exit P/E, and converts the implied market-cap change into price upside + CAGR. */
export function computeScenario(
  metrics: YearMetrics[],
  price: { close: number | null; market_cap: number | null },
  forensicTrust: number,
): ValuationModel {
  const ys = metrics.filter((m) => m.net_profit !== null);
  const latest = ys[ys.length - 1];
  const patNow = latest?.net_profit ?? null;
  const mcap = n(price.market_cap);
  const cur = n(price.close);
  const pe = mcap !== null && patNow !== null && patNow > 0 ? mcap / patNow : null;

  const histG = ys.length >= 4
    ? cagr(ys[ys.length - 4].net_profit, latest.net_profit, 3)
    : ys.length >= 2 ? cagr(ys[0].net_profit, latest.net_profit, ys.length - 1) : null;
  const g = histG ?? 0.15;
  const horizon = 4;
  const basePE = pe !== null ? Math.max(12, Math.min(35, pe)) : 18;

  // Scenario-specific growth caps so a hyper-growth base (e.g. 150% CAGR) still
  // yields a genuinely conservative bear case (growth normalises), not three
  // identical cap-pinned scenarios.
  const mk = (name: Scenario["name"], gMult: number, peMult: number, gCap: number): Scenario => {
    const growth = Math.max(0.03, Math.min(gCap, g * gMult));
    const exitPE = Math.max(8, Math.min(45, basePE * peMult));
    if (patNow === null || mcap === null || cur === null || patNow <= 0) {
      return { name, growth, exitPE, targetPrice: null, upside: null, cagr: null };
    }
    const projPat = patNow * (1 + growth) ** horizon;
    const targetMcap = projPat * exitPE;
    return {
      name, growth, exitPE,
      targetPrice: cur * (targetMcap / mcap),
      upside: targetMcap / mcap - 1,
      cagr: (targetMcap / mcap) ** (1 / horizon) - 1,
    };
  };
  const scenarios = [mk("Bear", 0.4, 0.65, 0.18), mk("Base", 0.85, 1.0, 0.30), mk("Bull", 1.2, 1.3, 0.45)];

  // risk scoring
  const reasons: string[] = [];
  let rs = 0;
  if (forensicTrust < 1) { reasons.push("forensic gate penalty applied"); rs += 2; }
  const de = latest?.debt_to_equity ?? null;
  if (de !== null && de > 1) { reasons.push(`high leverage (D/E ${de.toFixed(1)})`); rs += 2; }
  if (mcap !== null && mcap < 150) { reasons.push("micro-cap — thin liquidity, high impact cost"); rs += 2; }
  else if (mcap !== null && mcap < 400) { reasons.push("small-cap — limited liquidity"); rs += 1; }
  if (pe !== null && pe > 40) { reasons.push(`rich valuation (P/E ${pe.toFixed(0)})`); rs += 1; }
  if (ys.length < 4) { reasons.push("short track record (<4 yrs filed)"); rs += 1; }
  const level = rs >= 5 ? "High" : rs >= 3 ? "Moderate-High" : rs >= 1 ? "Moderate" : "Lower (still an SME)";
  if (!reasons.length) reasons.push("clean book, reasonable size & valuation — but SME liquidity always applies");

  return {
    currentPrice: cur, pe, horizon, histPatCagr: histG,
    scenarios, risk: { level, score: rs, reasons },
    buyZone: cur !== null ? [cur * 0.9, cur * 1.02] : null,
    sellTarget: scenarios[1].targetPrice,
  };
}
