import Link from "next/link";
import type { Peer } from "@/lib/queries";
import { Band, scoreColor } from "./Band";
import { crore, score, pct } from "@/lib/format";

export function PeersTable({ basis, peers }: { basis: string; peers: Peer[] }) {
  if (!peers.length) return null;
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <h2 className="mb-3 text-sm font-medium text-zinc-300">
        Peers <span className="text-zinc-600">· {basis}</span>
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-zinc-500">
            <tr className="border-b border-zinc-800">
              <th className="px-2 py-1.5 font-medium">Company</th>
              <th className="px-2 py-1.5 text-right font-medium">Score</th>
              <th className="px-2 py-1.5 text-right font-medium">M.Cap</th>
              <th className="px-2 py-1.5 text-right font-medium">ROCE</th>
              <th className="px-2 py-1.5 text-right font-medium">Rev CAGR</th>
            </tr>
          </thead>
          <tbody>
            {peers.map((p) => (
              <tr key={p.company_id} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-900/50">
                <td className="px-2 py-2">
                  <Link href={`/company/${p.company_id}`} className="font-medium text-zinc-200 hover:text-emerald-300">
                    {p.name}
                  </Link>
                  <span className="ml-1 text-xs text-zinc-600">{p.symbol ?? ""}</span>
                </td>
                <td className="px-2 py-2 text-right">
                  <span className={`tnum font-semibold ${scoreColor(p.total_score)}`}>{score(p.total_score)}</span>
                  <span className="ml-1.5 align-middle"><Band band={p.band} /></span>
                </td>
                <td className="tnum px-2 py-2 text-right text-zinc-300">{crore(p.market_cap)}</td>
                <td className="tnum px-2 py-2 text-right text-zinc-400">{pct(p.roce)}</td>
                <td className="tnum px-2 py-2 text-right text-zinc-400">{pct(p.revenue_cagr_3y)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
