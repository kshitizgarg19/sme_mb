"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fetchBulkDeals, type BulkDeal } from "@/lib/live";

export function BulkDealsTable() {
  const [deals, setDeals] = useState<BulkDeal[] | null>(null);
  const [scope, setScope] = useState<"All" | "SME only" | "Marquee">("SME only");
  const [side, setSide] = useState<"All" | "BUY" | "SELL">("All");

  useEffect(() => {
    let alive = true;
    fetchBulkDeals().then((d) => { if (alive) setDeals(d?.deals ?? []); });
    return () => { alive = false; };
  }, []);

  const rows = useMemo(() => {
    if (!deals) return [];
    return deals.filter((d) => {
      if (scope === "SME only" && !d.in_sme_universe) return false;
      if (scope === "Marquee" && !d.is_known_investor) return false;
      if (side !== "All" && d.side !== side) return false;
      return true;
    });
  }, [deals, scope, side]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Seg options={["SME only", "Marquee", "All"]} value={scope} onChange={setScope} />
        <Seg options={["All", "BUY", "SELL"]} value={side} onChange={setSide} />
        <span className="ml-auto text-xs text-zinc-500">
          {deals === null ? "loading…" : `${rows.length} deals · latest NSE session`}
        </span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-800 bg-zinc-900/40 text-xs text-zinc-400">
            <tr>
              <th className="px-3 py-2 font-medium">Stock</th>
              <th className="px-3 py-2 font-medium">Client</th>
              <th className="px-3 py-2 text-center font-medium">Side</th>
              <th className="px-3 py-2 text-right font-medium">Qty</th>
              <th className="px-3 py-2 text-right font-medium">Price</th>
              <th className="px-3 py-2 font-medium">Type</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d, i) => (
              <tr key={i} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-900/40">
                <td className="px-3 py-2">
                  {d.company_id ? (
                    <Link href={`/company/${d.company_id}`} className="font-medium text-zinc-100 hover:text-emerald-300">{d.symbol}</Link>
                  ) : <span className="font-medium text-zinc-300">{d.symbol}</span>}
                  {d.in_sme_universe && <span className="ml-1.5 rounded bg-emerald-500/15 px-1 py-0.5 text-[10px] text-emerald-300">SME</span>}
                </td>
                <td className="px-3 py-2 text-zinc-300">
                  {d.is_known_investor && <span className="mr-1" title="Marquee investor">⭐</span>}
                  {d.client_name}
                </td>
                <td className={`px-3 py-2 text-center font-medium ${d.side === "BUY" ? "text-emerald-400" : "text-rose-400"}`}>{d.side}</td>
                <td className="tnum px-3 py-2 text-right text-zinc-300">{d.quantity?.toLocaleString("en-IN") ?? "—"}</td>
                <td className="tnum px-3 py-2 text-right text-zinc-400">{d.price ? `₹${d.price.toFixed(1)}` : "—"}</td>
                <td className="px-3 py-2 text-xs text-zinc-500">{d.deal_type}</td>
              </tr>
            ))}
            {deals !== null && rows.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-10 text-center text-zinc-500">No deals match (no marquee/SME activity in the latest session).</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Seg<T extends string>({ options, value, onChange }: { options: readonly T[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex rounded-lg border border-zinc-800 bg-zinc-900/60 p-0.5">
      {options.map((o) => (
        <button key={o} onClick={() => onChange(o)}
          className={`rounded-md px-2.5 py-1 text-xs transition-colors ${value === o ? "bg-zinc-700 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"}`}>
          {o}
        </button>
      ))}
    </div>
  );
}
