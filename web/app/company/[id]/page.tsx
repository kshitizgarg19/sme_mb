import { notFound } from "next/navigation";
import Link from "next/link";
import { getCompany, getPeers } from "@/lib/queries";
import { Band, scoreColor } from "@/components/Band";
import { ScoreBar } from "@/components/ScoreBar";
import { LivePrice } from "@/components/LivePrice";
import { DepthLadder } from "@/components/DepthLadder";
import { LiveChart } from "@/components/LiveChart";
import { ShareholdingPanel } from "@/components/ShareholdingPanel";
import { PeersTable } from "@/components/PeersTable";
import { InvestorView } from "@/components/InvestorView";
import { NewsFeed } from "@/components/NewsFeed";
import { DeepAnalysis } from "@/components/DeepAnalysis";
import { InvestorsPanel } from "@/components/InvestorsPanel";
import { perYearMetrics, computeScenario, type AnnualRow } from "@/lib/analysis";
import { score, pct, ratio, crore, int, toNum } from "@/lib/format";

export const dynamic = "force-static";
export const dynamicParams = true; // non-prebuilt ids render on demand, then cache

// Pre-build the top-ranked companies into static HTML at build (instant loads);
// the long tail renders on first visit and is then cached (dynamicParams).
export async function generateStaticParams() {
  const { sql } = await import("@/lib/db");
  const rows = (await sql`
    SELECT company_id FROM multibagger_scores
    WHERE as_of_date = (SELECT max(as_of_date) FROM multibagger_scores)
    ORDER BY rank_overall LIMIT 120
  `) as { company_id: number }[];
  return rows.map((r) => ({ id: String(r.company_id) }));
}

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getCompany(Number(id));
  if (!data) notFound();

  const c = data.company as Record<string, unknown>;
  const m = (data.metrics ?? {}) as Record<string, unknown>;
  const raw = (m.raw ?? {}) as Record<string, unknown>;
  const altman = (raw.altman ?? {}) as Record<string, unknown>;
  const beneish = (raw.beneish ?? {}) as Record<string, unknown>;
  const piotroski = (raw.piotroski ?? {}) as Record<string, unknown>;

  const subs: { label: string; value: number | null }[] = [
    { label: "Growth", value: toNum(c.growth_score) },
    { label: "Profitability", value: toNum(c.profitability_score) },
    { label: "Balance sheet", value: toNum(c.balance_sheet_score) },
    { label: "Cash flow", value: toNum(c.cash_flow_score) },
    { label: "Management", value: toNum(c.management_score) },
    { label: "Capital efficiency", value: toNum(c.capital_eff_score) },
    { label: "Valuation", value: toNum(c.valuation_score) },
    { label: "Size / runway", value: toNum(c.size_runway_score) },
  ];

  const symbol = (c.nse_symbol || c.bse_symbol || c.bse_scripcode || "—") as string;
  const exch = c.exchange === "NSE_EMERGE" ? "NSE Emerge" : c.exchange === "BSE_SME" ? "BSE SME" : String(c.exchange);

  const links: { label: string; href: string }[] = [];
  if (c.nse_symbol) links.push({ label: "NSE", href: `https://www.nseindia.com/get-quotes/equity?symbol=${c.nse_symbol}` });
  if (c.bse_scripcode) links.push({ label: "BSE", href: `https://www.bseindia.com/stock-share-price/x/x/${c.bse_scripcode}/` });
  if (c.nse_symbol || c.bse_symbol) links.push({ label: "Screener", href: `https://www.screener.in/company/${c.nse_symbol || c.bse_symbol}/` });
  links.push({ label: "Trendlyne", href: `https://trendlyne.com/equity/share-price-target/?q=${encodeURIComponent(String(c.name))}` });

  const peers = await getPeers(
    Number(c.company_id),
    (c.sector as string) ?? null,
    (c.industry as string) ?? null,
    data.price?.market_cap ?? null,
    String(c.exchange),
  );

  // deep analysis: per-year ratios + valuation/scenario model
  const metrics = perYearMetrics(data.annual as unknown as AnnualRow[]);
  const valuation = computeScenario(
    metrics,
    { close: data.price?.close ?? null, market_cap: data.price?.market_cap ?? null },
    Number(c.forensic_trust ?? 1),
  );
  const shLatest = ((data.shareholding as unknown[]).at(-1) as never) ?? null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const subScores = (c.sub_scores ?? {}) as any;

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-zinc-500 hover:text-zinc-300">← Rankings</Link>

      {/* header */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">{String(c.name)}</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {symbol} · {exch}{c.sector ? ` · ${c.sector}` : ""}
            {c.rank_overall ? <> · rank #{int(c.rank_overall)}</> : null}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {links.map((l) => (
              <a key={l.label} href={l.href} target="_blank" rel="noopener noreferrer"
                className="rounded-md border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 transition-colors hover:border-zinc-500 hover:text-zinc-100">
                {l.label} ↗
              </a>
            ))}
          </div>
        </div>
        <div className="text-right">
          <div className={`tnum text-4xl font-bold ${scoreColor(toNum(c.total_score))}`}>{score(c.total_score)}</div>
          <div className="mt-1 flex items-center justify-end gap-2">
            <Band band={(c.band as string) ?? null} full />
            <span className="text-xs text-zinc-500">/ 100</span>
          </div>
        </div>
      </div>

      {/* Investor View — the grounded Jhunjhunwala/Kedia verdict */}
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <InvestorView v={c.verdict as any} />

      {/* LIVE (XTS) */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <LiveChart companyId={Number(c.company_id)} />
        </div>
        <div className="space-y-6">
          <LivePrice companyId={Number(c.company_id)} fallbackClose={data.price?.close ?? null} />
          <DepthLadder companyId={Number(c.company_id)} />
        </div>
      </div>

      {/* DEEP ANALYSIS — charts · year-by-year ratios · valuation · why-this-score */}
      <DeepAnalysis metrics={metrics} valuation={valuation} shareholdingLatest={shLatest} subScores={subScores} />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* sub-scores */}
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
          <h2 className="mb-4 text-sm font-medium text-zinc-300">Score breakdown</h2>
          <div className="space-y-2.5">
            {subs.map((s) => <ScoreBar key={s.label} label={s.label} value={s.value} />)}
          </div>
          <div className="mt-4 border-t border-zinc-800 pt-3 text-xs text-zinc-500">
            Forensic trust multiplier:{" "}
            <span className="tnum text-zinc-300">{c.forensic_trust === null || c.forensic_trust === undefined ? "—" : Number(c.forensic_trust).toFixed(2)}</span>
            {" "}— a clean book leaves the score untouched; flags shave points off the top.
          </div>
        </section>

        {/* forensic + key metrics */}
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
          <h2 className="mb-4 text-sm font-medium text-zinc-300">Forensic & quality</h2>
          <div className="grid grid-cols-3 gap-3">
            <Metric label="Piotroski F" value={m.piotroski != null ? `${int(m.piotroski)} / ${int((piotroski.max_available as number) ?? 9)}` : "—"}
              tone={tone(toNum(m.piotroski), 7, 4)} />
            <Metric label="Altman Z" value={ratio(m.altman_z)} sub={(altman.zone as string) ?? ""}
              tone={altman.zone === "safe" ? "good" : altman.zone === "distress" ? "bad" : "mid"} />
            <Metric label="Beneish M" value={ratio(m.beneish_m)} sub={beneish.likely_manipulator ? "flagged" : "clean"}
              tone={beneish.likely_manipulator ? "bad" : "good"} />
            <Metric label="ROCE" value={pct(m.roce)} tone={tone(toNum(m.roce), 0.2, 0.12)} />
            <Metric label="ROE" value={pct(m.roe)} tone={tone(toNum(m.roe), 0.18, 0.1)} />
            <Metric label="Debt / Equity" value={ratio(m.debt_to_equity)} tone={toneInv(toNum(m.debt_to_equity), 0.3, 1.0)} />
            <Metric label="Rev CAGR 3y" value={pct(m.revenue_cagr_3y)} tone={tone(toNum(m.revenue_cagr_3y), 0.25, 0.1)} />
            <Metric label="PAT CAGR 3y" value={pct(m.profit_cagr_3y)} tone={tone(toNum(m.profit_cagr_3y), 0.3, 0.12)} />
            <Metric label="OCF / PAT" value={ratio(m.ocf_to_pat)} tone={tone(toNum(m.ocf_to_pat), 0.8, 0.5)} />
          </div>
          <div className="mt-4 border-t border-zinc-800 pt-3 text-xs text-zinc-500">
            Market cap <span className="tnum text-zinc-300">{crore(data.price?.market_cap)}</span>
            {data.price?.close != null && <> · price <span className="tnum text-zinc-300">₹{int(data.price.close)}</span></>}
          </div>
        </section>
      </div>

      {/* shareholding + investors */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <ShareholdingPanel rows={data.shareholding as any} />
        <InvestorsPanel companyId={Number(c.company_id)} nseSymbol={(c.nse_symbol as string) ?? null} name={String(c.name)} />
      </div>
      <PeersTable basis={peers.basis} peers={peers.peers} />

      {/* news & filings */}
      <NewsFeed companyId={Number(c.company_id)} />

      {/* financials */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
        <h2 className="mb-4 text-sm font-medium text-zinc-300">Financials <span className="text-zinc-600">(₹ crore)</span></h2>
        {data.annual.length === 0 ? (
          <p className="text-sm text-zinc-500">No financials captured.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead className="text-xs text-zinc-500">
                <tr className="border-b border-zinc-800">
                  <th className="px-2 py-1.5 text-left font-medium">Metric</th>
                  {data.annual.map((y: Record<string, unknown>) => (
                    <th key={String(y.fiscal_year)} className="px-2 py-1.5 font-medium">FY{String(y.fiscal_year).slice(2)}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="tnum">
                <FinRow label="Revenue" rows={data.annual} k="revenue" />
                <FinRow label="EBIT" rows={data.annual} k="ebit" />
                <FinRow label="Net profit" rows={data.annual} k="net_profit" />
                <FinRow label="Op. cash flow" rows={data.annual} k="operating_cash_flow" />
                <FinRow label="Total debt" rows={data.annual} k="total_debt" />
                <FinRow label="Equity" rows={data.annual} k="equity" />
              </tbody>
            </table>
          </div>
        )}
      </section>

      {c.thesis ? (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
          <h2 className="mb-2 text-sm font-medium text-zinc-300">Investment thesis</h2>
          <p className="text-sm leading-relaxed text-zinc-400">{String(c.thesis)}</p>
        </section>
      ) : null}
    </div>
  );
}

function Metric({ label, value, sub, tone = "mid" }: { label: string; value: string; sub?: string; tone?: "good" | "mid" | "bad" }) {
  const color = tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-rose-300" : "text-zinc-200";
  return (
    <div className="rounded-lg border border-zinc-800/70 bg-zinc-950/40 px-3 py-2">
      <div className="text-[11px] text-zinc-500">{label}</div>
      <div className={`tnum text-lg font-semibold ${color}`}>{value}</div>
      {sub && <div className="text-[11px] text-zinc-600">{sub}</div>}
    </div>
  );
}

function FinRow({ label, rows, k }: { label: string; rows: Record<string, unknown>[]; k: string }) {
  return (
    <tr className="border-b border-zinc-800/50 last:border-0">
      <td className="px-2 py-1.5 text-left text-zinc-400">{label}</td>
      {rows.map((y, i) => (
        <td key={i} className="px-2 py-1.5 text-zinc-300">{y[k] == null ? "—" : int(y[k])}</td>
      ))}
    </tr>
  );
}

const tone = (v: number | null, good: number, bad: number): "good" | "mid" | "bad" =>
  v === null ? "mid" : v >= good ? "good" : v <= bad ? "bad" : "mid";
const toneInv = (v: number | null, good: number, bad: number): "good" | "mid" | "bad" =>
  v === null ? "mid" : v <= good ? "good" : v >= bad ? "bad" : "mid";
