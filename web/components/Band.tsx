const STYLES: Record<string, string> = {
  A: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  B: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  C: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  D: "bg-zinc-500/15 text-zinc-400 ring-zinc-500/30",
};

export function Band({ band, full = false }: { band: string | null; full?: boolean }) {
  const letter = band?.[0] ?? "—";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        STYLES[letter] ?? STYLES.D
      }`}
    >
      {full ? band ?? "—" : letter}
    </span>
  );
}

export function scoreColor(v: number | null): string {
  if (v === null || Number.isNaN(v)) return "text-zinc-500";
  if (v >= 75) return "text-emerald-300";
  if (v >= 60) return "text-sky-300";
  if (v >= 45) return "text-amber-300";
  return "text-zinc-400";
}
