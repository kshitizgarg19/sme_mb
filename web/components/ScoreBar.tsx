export function ScoreBar({ label, value }: { label: string; value: number | null }) {
  const v = value === null || Number.isNaN(value) ? null : Math.max(0, Math.min(100, value));
  const color =
    v === null ? "bg-zinc-700" : v >= 70 ? "bg-emerald-500" : v >= 45 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="flex items-center gap-3">
      <span className="w-36 shrink-0 text-xs text-zinc-400">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-800">
        {v !== null && <div className={`h-full rounded-full ${color}`} style={{ width: `${v}%` }} />}
      </div>
      <span className="tnum w-9 shrink-0 text-right text-xs text-zinc-300">
        {v === null ? "—" : v.toFixed(0)}
      </span>
    </div>
  );
}
