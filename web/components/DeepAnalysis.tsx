"use client";

import { GrowthChart, MarginChart, ReturnsChart, ShareholdingPie } from "./AnalysisCharts";
import type { YearMetrics, ValuationModel } from "@/lib/analysis";

const pct = (v: number | null, d = 1) => (v === null || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(d)}%`);
const num = (v: number | null, d = 2) => (v === null || Number.isNaN(v) ? "—" : v.toFixed(d));
const rup = (v: number | null) => (v === null ? "—" : `₹${Math.round(v).toLocaleString("en-IN")}`);
const cr = (v: number | null) => (v === null ? "—" : Math.abs(v) >= 1000 ? `₹${(v / 1000).toFixed(1)}k cr` : `₹${Math.round(v)} cr`);

type SubScores = Record<string, { score: number | null; evidence: Record<string, unknown> }>;

export function DeepAnalysis({
  metrics, valuation, shareholdingLatest, subScores,
}: {
  metrics: YearMetrics[];
  valuation: ValuationModel;
  shareholdingLatest: { promoter_pct: number | null; fii_pct: number | null; dii_pct: number | null; public_pct: number | null } | null;
  subScores: SubScores;
}) {
  // Everything stacked on one scroll — no tabs (user wants it all on screen).
  return (
    <div className="space-y-6">
      <Section title="Charts">
        <Charts metrics={metrics} sh={shareholdingLatest} />
      </Section>
      <Section title="Financial Ratios" subtitle="full ratio history by fiscal year">
        <Ratios metrics={metrics} />
      </Section>
      <Section title="Valuation & Scenario Analysis" subtitle="upside · risk · time horizon · entry / exit">
        <Valuation v={valuation} />
      </Section>
      <Section title="Score Rationale" subtitle="the drivers behind every sub-score">
        <Why subScores={subScores} />
      </Section>
    </div>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <h2 className="mb-4 text-sm font-medium text-zinc-300">
        {title}
        {subtitle && <span className="text-zinc-600"> · {subtitle}</span>}
      </h2>
      {children}
    </section>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-zinc-800/70 bg-zinc-950/30 p-3">
      <h3 className="mb-2 text-xs font-medium text-zinc-400">{title}</h3>
      {children}
    </div>
  );
}

function Charts({ metrics, sh }: { metrics: YearMetrics[]; sh: any }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Revenue & Net Profit (₹ cr)"><GrowthChart data={metrics} /></Panel>
      <Panel title="Margins"><MarginChart data={metrics} /></Panel>
      <Panel title="Returns — ROCE & ROE"><ReturnsChart data={metrics} /></Panel>
      <Panel title="Shareholding (latest)"><ShareholdingPie latest={sh} /></Panel>
    </div>
  );
}

const ROWS: { label: string; key: keyof YearMetrics; fmt: (v: number | null) => string }[] = [
  { label: "Revenue", key: "revenue", fmt: cr },
  { label: "Net profit", key: "net_profit", fmt: cr },
  { label: "EBITDA", key: "ebitda", fmt: cr },
  { label: "Op. cash flow", key: "ocf", fmt: cr },
  { label: "Revenue growth", key: "rev_growth", fmt: (v) => pct(v, 0) },
  { label: "Profit growth", key: "pat_growth", fmt: (v) => pct(v, 0) },
  { label: "Gross margin", key: "gross_margin", fmt: (v) => pct(v) },
  { label: "Operating margin", key: "op_margin", fmt: (v) => pct(v) },
  { label: "Net margin", key: "net_margin", fmt: (v) => pct(v) },
  { label: "ROCE", key: "roce", fmt: (v) => pct(v) },
  { label: "ROE", key: "roe", fmt: (v) => pct(v) },
  { label: "ROA", key: "roa", fmt: (v) => pct(v) },
  { label: "Debt / Equity", key: "debt_to_equity", fmt: (v) => num(v) },
  { label: "Interest cover", key: "interest_cover", fmt: (v) => num(v, 1) },
  { label: "Asset turnover", key: "asset_turnover", fmt: (v) => num(v) },
  { label: "OCF / PAT", key: "ocf_to_pat", fmt: (v) => num(v) },
];

function Ratios({ metrics }: { metrics: YearMetrics[] }) {
  if (!metrics.length) return <p className="text-sm text-zinc-500">No financials.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-right text-sm">
        <thead className="text-xs text-zinc-500">
          <tr className="border-b border-zinc-800">
            <th className="px-2 py-1.5 text-left font-medium">Metric</th>
            {metrics.map((m) => <th key={m.fy} className="px-2 py-1.5 font-medium">{m.label}</th>)}
          </tr>
        </thead>
        <tbody className="tnum">
          {ROWS.map((row) => (
            <tr key={row.label} className="border-b border-zinc-800/40 last:border-0">
              <td className="px-2 py-1.5 text-left text-zinc-400">{row.label}</td>
              {metrics.map((m) => <td key={m.fy} className="px-2 py-1.5 text-zinc-300">{row.fmt(m[row.key] as number | null)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Valuation({ v }: { v: ValuationModel }) {
  const tone: Record<string, string> = { Bear: "border-rose-500/30", Base: "border-sky-500/30", Bull: "border-emerald-500/30" };
  const utone = (u: number | null) => (u === null ? "text-zinc-400" : u > 1 ? "text-emerald-300" : u > 0 ? "text-sky-300" : "text-rose-300");
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <Kv k="Current price" v={rup(v.currentPrice)} />
        <Kv k="P/E" v={num(v.pe, 1)} />
        <Kv k="Hist. PAT CAGR" v={pct(v.histPatCagr, 0)} />
        <Kv k="Horizon" v={`${v.horizon} yrs`} />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {v.scenarios.map((s) => (
          <div key={s.name} className={`rounded-lg border bg-zinc-950/30 p-3 ${tone[s.name]}`}>
            <div className="mb-1 text-sm font-semibold text-zinc-200">{s.name} case</div>
            <div className={`tnum text-2xl font-bold ${utone(s.upside)}`}>{s.upside === null ? "—" : `${s.upside >= 0 ? "+" : ""}${(s.upside * 100).toFixed(0)}%`}</div>
            <div className="mt-1 text-xs text-zinc-500">target {rup(s.targetPrice)} · {s.cagr === null ? "—" : `${(s.cagr * 100).toFixed(0)}%/yr`}</div>
            <div className="mt-2 text-[11px] text-zinc-600">assumes {(s.growth * 100).toFixed(0)}% PAT growth · exit P/E {s.exitPE.toFixed(0)}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-zinc-800/70 bg-zinc-950/30 p-3">
          <div className="text-xs text-zinc-500">Risk level</div>
          <div className="text-lg font-semibold text-amber-300">{v.risk.level}</div>
          <ul className="mt-1 space-y-0.5 text-xs text-zinc-500">
            {v.risk.reasons.map((r, i) => <li key={i}>· {r}</li>)}
          </ul>
        </div>
        <div className="rounded-lg border border-zinc-800/70 bg-zinc-950/30 p-3 text-sm">
          <div className="mb-1"><span className="text-zinc-500">Accumulate zone: </span><span className="tnum text-emerald-300">{v.buyZone ? `${rup(v.buyZone[0])} – ${rup(v.buyZone[1])}` : "—"}</span></div>
          <div><span className="text-zinc-500">Base-case target (sell): </span><span className="tnum text-sky-300">{rup(v.sellTarget)}</span></div>
          <p className="mt-2 text-[11px] text-zinc-600">Earnings-growth × exit-multiple model. A framework, not a price prediction — size for SME liquidity and do your own diligence.</p>
        </div>
      </div>
    </div>
  );
}

const EV_LABELS: Record<string, string> = {
  revenue_cagr_3y: "Revenue CAGR 3y", profit_cagr_3y: "Profit CAGR 3y", ocf_cagr: "OCF CAGR",
  roce: "ROCE", roce_3y_avg: "ROCE 3y avg", roe: "ROE", op_margin: "Op margin",
  debt_to_equity: "Debt/Equity", interest_coverage: "Interest cover", current_ratio: "Current ratio",
  ocf_to_pat_3y: "OCF/PAT 3y", fcf_yield: "FCF yield", positive_ocf_fraction: "Positive-OCF years",
  promoter_holding: "Promoter holding", holding_change_4q: "Holding Δ (4q)", pledged_pct: "Pledged %",
  promoter_net_buy: "Promoter net buy", dilution_events_3y: "Dilutions (3y)",
  asset_turnover: "Asset turnover", cash_conversion_cycle: "Cash conv. cycle (days)",
  inventory_days: "Inventory days", debtor_days: "Debtor days",
  pe: "P/E", peg: "PEG", earnings_cagr: "Earnings CAGR",
  market_cap: "Market cap (cr)", latest_revenue: "Revenue (cr)", sector_tailwind: "Sector tailwind",
};
const SUB_LABELS: Record<string, string> = {
  growth: "Growth", profitability: "Profitability", balance_sheet: "Balance sheet",
  cash_flow: "Cash flow", management: "Management", capital_efficiency: "Capital efficiency",
  valuation: "Valuation", size_runway: "Size / runway",
};
function fmtEv(k: string, v: unknown): string {
  if (v === null || v === undefined) return "n/a";
  if (typeof v !== "number") return String(v);
  if (/cagr|margin|roce|roe|yield|holding|pledg|tailwind|fraction|change/i.test(k)) return `${(v * 100).toFixed(1)}%`;
  if (/market_cap|revenue/i.test(k)) return `₹${Math.round(v)} cr`;
  return v.toFixed(2);
}

function Why({ subScores }: { subScores: SubScores }) {
  const keys = Object.keys(SUB_LABELS).filter((k) => subScores[k]);
  return (
    <div className="space-y-3">
      <p className="text-xs text-zinc-500">Every sub-score, and the exact metrics that drove it.</p>
      {keys.map((k) => {
        const s = subScores[k];
        const sc = s.score;
        const verdict = sc === null ? "no data" : sc >= 70 ? "strong" : sc >= 45 ? "adequate" : "weak";
        const color = sc === null ? "text-zinc-500" : sc >= 70 ? "text-emerald-300" : sc >= 45 ? "text-amber-300" : "text-rose-300";
        return (
          <div key={k} className="rounded-lg border border-zinc-800/70 bg-zinc-950/30 p-3">
            <div className="mb-1.5 flex items-center gap-3">
              <span className="font-medium text-zinc-200">{SUB_LABELS[k]}</span>
              <span className={`tnum text-sm font-semibold ${color}`}>{sc === null ? "—" : sc.toFixed(0)}</span>
              <span className={`text-xs ${color}`}>({verdict})</span>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
              {Object.entries(s.evidence || {}).map(([ek, ev]) => (
                <span key={ek}><span className="text-zinc-600">{EV_LABELS[ek] ?? ek}:</span> <span className="tnum text-zinc-300">{fmtEv(ek, ev)}</span></span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return <div><span className="text-zinc-500">{k}: </span><span className="tnum text-zinc-200">{v}</span></div>;
}
