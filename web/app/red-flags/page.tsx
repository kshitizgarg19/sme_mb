import Link from "next/link";
import { getRedFlags } from "@/lib/queries";
import { score, ratio, int } from "@/lib/format";

export const dynamic = "force-static";

export default async function RedFlagsPage() {
  const rows = await getRedFlags();

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Red Flags</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Companies the forensic gate penalised (trust &lt; 1.0) — weak Piotroski, Altman distress,
          a Beneish manipulation flag, or earnings not converting to cash. These cap the final score.
        </p>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-10 text-center text-sm text-zinc-500">
          No forensic penalties in the latest scan (or scoring hasn&apos;t run yet).
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/40 text-xs text-zinc-400">
              <tr>
                <th className="px-3 py-2 font-medium">Company</th>
                <th className="px-3 py-2 text-right font-medium">Score</th>
                <th className="px-3 py-2 text-right font-medium">Trust</th>
                <th className="px-3 py-2 text-right font-medium">Piotroski</th>
                <th className="px-3 py-2 text-right font-medium">Altman Z</th>
                <th className="px-3 py-2 text-right font-medium">Beneish M</th>
                <th className="px-3 py-2 text-right font-medium">OCF/PAT</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.company_id} className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-900/50">
                  <td className="px-3 py-2.5">
                    <Link href={`/company/${r.company_id}`} className="font-medium text-zinc-100 hover:text-emerald-300">
                      {r.name}
                    </Link>
                    <div className="text-xs text-zinc-500">{r.symbol ?? "—"}</div>
                  </td>
                  <td className="tnum px-3 py-2.5 text-right text-zinc-300">{score(r.total_score)}</td>
                  <td className="tnum px-3 py-2.5 text-right text-rose-300">{r.forensic_trust === null ? "—" : r.forensic_trust.toFixed(2)}</td>
                  <td className="tnum px-3 py-2.5 text-right text-zinc-400">{r.piotroski == null ? "—" : int(r.piotroski)}</td>
                  <td className="tnum px-3 py-2.5 text-right text-zinc-400">{ratio(r.altman_z)}</td>
                  <td className={`tnum px-3 py-2.5 text-right ${r.beneish_m != null && r.beneish_m > -1.78 ? "text-rose-300" : "text-zinc-400"}`}>{ratio(r.beneish_m)}</td>
                  <td className={`tnum px-3 py-2.5 text-right ${r.ocf_to_pat != null && r.ocf_to_pat < 0.5 ? "text-rose-300" : "text-zinc-400"}`}>{ratio(r.ocf_to_pat)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
