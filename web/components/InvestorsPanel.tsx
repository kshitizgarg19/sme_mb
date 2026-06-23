"use client";

import { useEffect, useState } from "react";
import { fetchBulkDealsFor, type BulkDeal } from "@/lib/live";

export function InvestorsPanel({
  companyId, nseSymbol, name,
}: {
  companyId: number; nseSymbol: string | null; name: string;
}) {
  const [deals, setDeals] = useState<BulkDeal[] | null>(null);
  useEffect(() => {
    let alive = true;
    fetchBulkDealsFor(companyId).then((d) => { if (alive) setDeals(d?.deals ?? []); });
    return () => { alive = false; };
  }, [companyId]);

  const sym = nseSymbol;
  const links = [
    sym && { label: "Shareholders (Screener)", href: `https://www.screener.in/company/${sym}/#shareholding` },
    sym && { label: "Annual reports & docs", href: `https://www.screener.in/company/${sym}/#documents` },
    { label: "Superstar holders (Trendlyne)", href: `https://trendlyne.com/equity/share-price-target/?q=${encodeURIComponent(name)}` },
    sym && { label: "Concalls (Trendlyne)", href: `https://trendlyne.com/research-reports/stock/?q=${encodeURIComponent(name)}` },
  ].filter(Boolean) as { label: string; href: string }[];

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <h2 className="mb-3 text-sm font-medium text-zinc-300">Promoters &amp; Investors</h2>

      <div className="mb-4">
        <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">Recent large transactions</div>
        {deals === null ? (
          <p className="text-xs text-zinc-600">Checking bulk/block deals…</p>
        ) : deals.length === 0 ? (
          <p className="text-xs text-zinc-600">No bulk/block deal in this stock in the latest session.</p>
        ) : (
          <ul className="space-y-1.5">
            {deals.map((d, i) => (
              <li key={i} className="flex items-center justify-between text-sm">
                <span className="text-zinc-300">{d.is_known_investor && "⭐ "}{d.client_name}</span>
                <span className={`tnum ${d.side === "BUY" ? "text-emerald-400" : "text-rose-400"}`}>
                  {d.side} {d.quantity?.toLocaleString("en-IN")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-zinc-800 pt-3">
        <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">
          Named promoters · shareholders · concalls
        </div>
        <div className="flex flex-wrap gap-2">
          {links.map((l) => (
            <a key={l.label} href={l.href} target="_blank" rel="noopener noreferrer"
              className="rounded-md border border-zinc-700 px-2 py-0.5 text-xs text-zinc-400 transition-colors hover:border-zinc-500 hover:text-zinc-100">
              {l.label} ↗
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
