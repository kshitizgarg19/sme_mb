import { getLatestScores, getStats } from "@/lib/queries";
import { StatCards } from "@/components/StatCards";
import { RankTable } from "@/components/RankTable";

// Always read fresh from Postgres — the Python pipeline updates it on each scan.
export const dynamic = "force-dynamic";

export default async function Home() {
  const [rows, stats] = await Promise.all([getLatestScores(), getStats()]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Multibagger Rankings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every NSE Emerge &amp; BSE SME stock, scored 0–100 on growth, returns on capital,
          balance-sheet strength, cash conversion and a forensic gate (Piotroski · Altman · Beneish).
        </p>
      </div>

      <StatCards stats={stats} />

      {rows.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-10 text-center text-sm text-zinc-500">
          No scores yet. Run the pipeline: <code className="text-zinc-300">python scripts/run_pipeline.py</code>
        </div>
      ) : (
        <RankTable rows={rows} />
      )}
    </div>
  );
}
