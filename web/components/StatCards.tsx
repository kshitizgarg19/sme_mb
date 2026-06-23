import type { Stats } from "@/lib/queries";

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="tnum mt-1 text-2xl font-semibold text-zinc-100">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

export function StatCards({ stats }: { stats: Stats }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <Card label="SME universe" value={stats.universe.toLocaleString("en-IN")} sub="NSE Emerge + BSE SME" />
      <Card label="Scored" value={stats.total.toLocaleString("en-IN")} sub={`${stats.with_fundamentals} with fundamentals`} />
      <Card label="Band A" value={String(stats.band_a)} sub="high conviction" />
      <Card label="Band B" value={String(stats.band_b)} sub="watchlist" />
      <Card label="As of" value={stats.as_of ?? "—"} sub="latest scan" />
    </div>
  );
}
