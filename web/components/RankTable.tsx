"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { ScoreRow } from "@/lib/queries";
import { fetchQuotes } from "@/lib/live";
import { Band, scoreColor } from "./Band";
import { crore, score } from "@/lib/format";

type SortKey =
  | "rank_overall" | "total_score" | "market_cap" | "growth_score"
  | "profitability_score" | "cash_flow_score" | "valuation_score" | "forensic_trust";

const BANDS = ["All", "A", "B", "C", "D"] as const;
const EXCH = ["All", "NSE_EMERGE", "BSE_SME"] as const;

export function RankTable({ rows }: { rows: ScoreRow[] }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [band, setBand] = useState<(typeof BANDS)[number]>("All");
  const [exch, setExch] = useState<(typeof EXCH)[number]>("All");
  const [live, setLive] = useState<Record<string, { ltp: number | null; volume: number | null }>>({});

  // Poll live price + daily volume for the listed names. Works on the local
  // dashboard (live service running); on the public/static site it stays "—".
  useEffect(() => {
    let on = true;
    const ids = rows.map((r) => r.company_id);
    const tick = async () => {
      const q = await fetchQuotes(ids);
      if (on) setLive(q as Record<string, { ltp: number | null; volume: number | null }>);
    };
    tick();
    const h = setInterval(tick, 10000);
    return () => { on = false; clearInterval(h); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [sortKey, setSortKey] = useState<SortKey>("rank_overall");
  const [asc, setAsc] = useState(true);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = rows.filter((r) => {
      if (band !== "All" && !(r.band ?? "").startsWith(band)) return false;
      if (exch !== "All" && r.exchange !== exch && r.exchange !== "BOTH") return false;
      if (needle) {
        const hay = `${r.name} ${r.symbol ?? ""} ${r.sector ?? ""}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
    out.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      const an = av === null || av === undefined ? -Infinity : Number(av);
      const bn = bv === null || bv === undefined ? -Infinity : Number(bv);
      return asc ? an - bn : bn - an;
    });
    return out;
  }, [rows, q, band, exch, sortKey, asc]);

  function sortBy(key: SortKey) {
    if (key === sortKey) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(key === "rank_overall"); // rank ascends by default; scores descend
    }
  }

  const Th = ({ k, children, className = "" }: { k: SortKey; children: React.ReactNode; className?: string }) => (
    <th
      onClick={() => sortBy(k)}
      className={`cursor-pointer select-none px-3 py-2 font-medium text-zinc-400 hover:text-zinc-200 ${className}`}
    >
      {children}
      {sortKey === k && <span className="ml-1 text-zinc-600">{asc ? "▲" : "▼"}</span>}
    </th>
  );

  return (
    <div>
      {/* controls */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name, symbol, sector…"
          className="w-64 rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-600"
        />
        <Segmented options={BANDS} value={band} onChange={setBand} />
        <Segmented options={EXCH} value={exch} onChange={setExch} labels={{ NSE_EMERGE: "NSE", BSE_SME: "BSE" }} />
        <span className="ml-auto text-xs text-zinc-500">{filtered.length} of {rows.length}</span>
      </div>

      {/* table */}
      <div className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="border-b border-zinc-800 bg-zinc-900/40 text-xs">
            <tr>
              <Th k="rank_overall" className="w-12">#</Th>
              <th className="px-3 py-2 font-medium text-zinc-400">Company</th>
              <Th k="market_cap" className="text-right">M.Cap</Th>
              <th className="px-3 py-2 text-right font-medium text-zinc-400">Price</th>
              <th className="px-3 py-2 text-right font-medium text-zinc-400">Vol</th>
              <Th k="total_score" className="text-right">Score</Th>
              <Th k="growth_score" className="hidden text-right md:table-cell">Growth</Th>
              <Th k="profitability_score" className="hidden text-right md:table-cell">Profit</Th>
              <Th k="cash_flow_score" className="hidden text-right lg:table-cell">Cash</Th>
              <Th k="valuation_score" className="hidden text-right lg:table-cell">Val</Th>
              <Th k="forensic_trust" className="hidden text-right sm:table-cell">Trust</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr
                key={r.company_id}
                onClick={() => router.push(`/company/${r.company_id}`)}
                className="cursor-pointer border-b border-zinc-800/60 transition-colors last:border-0 hover:bg-zinc-900/50"
              >
                <td className="tnum px-3 py-2.5 text-zinc-500">{r.rank_overall}</td>
                <td className="px-3 py-2.5">
                  <div className="font-medium text-zinc-100">{r.name}</div>
                  <div className="text-xs text-zinc-500">
                    {r.symbol ?? "—"} · {r.exchange === "NSE_EMERGE" ? "NSE" : r.exchange === "BSE_SME" ? "BSE" : r.exchange}
                    {r.sector ? ` · ${r.sector}` : ""}
                  </div>
                </td>
                <td className="tnum px-3 py-2.5 text-right text-zinc-300">{crore(r.market_cap)}</td>
                <td className="tnum px-3 py-2.5 text-right text-zinc-200">
                  {live[r.company_id]?.ltp != null ? `₹${live[r.company_id].ltp}` : "—"}
                </td>
                <td className="tnum px-3 py-2.5 text-right text-zinc-400">{vol(live[r.company_id]?.volume)}</td>
                <td className="px-3 py-2.5 text-right">
                  <span className={`tnum text-base font-semibold ${scoreColor(r.total_score)}`}>{score(r.total_score)}</span>
                  <span className="ml-2 align-middle"><Band band={r.band} /></span>
                </td>
                <Cell v={r.growth_score} className="hidden md:table-cell" />
                <Cell v={r.profitability_score} className="hidden md:table-cell" />
                <Cell v={r.cash_flow_score} className="hidden lg:table-cell" />
                <Cell v={r.valuation_score} className="hidden lg:table-cell" />
                <td className="tnum hidden px-3 py-2.5 text-right text-zinc-400 sm:table-cell">
                  {r.forensic_trust === null ? "—" : r.forensic_trust.toFixed(2)}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={11} className="px-3 py-10 text-center text-zinc-500">
                  No companies match. The scan may still be running — refresh in a bit.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Compact Indian volume: 83000 -> 83K, 250000 -> 2.5L, 12000000 -> 1.2Cr
function vol(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e7) return `${(v / 1e7).toFixed(1)}Cr`;
  if (v >= 1e5) return `${(v / 1e5).toFixed(1)}L`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(v);
}

function Cell({ v, className = "" }: { v: number | null; className?: string }) {
  const color = v === null ? "text-zinc-600" : v >= 70 ? "text-emerald-300/90" : v >= 45 ? "text-amber-300/90" : "text-rose-300/80";
  return <td className={`tnum px-3 py-2.5 text-right ${color} ${className}`}>{v === null ? "—" : v.toFixed(0)}</td>;
}

function Segmented<T extends string>({
  options, value, onChange, labels = {},
}: {
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
  labels?: Record<string, string>;
}) {
  return (
    <div className="flex rounded-lg border border-zinc-800 bg-zinc-900/60 p-0.5">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
            value === o ? "bg-zinc-700 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
          }`}
        >
          {labels[o] ?? o}
        </button>
      ))}
    </div>
  );
}
