type Lens = { name: string; pass: boolean; why: string };
type Verdict = {
  verdict: string;
  tone: "good" | "mid" | "bad";
  headline: string;
  thesis: string[];
  risks: string[];
  lenses: Lens[];
  trust: number;
};

const TONE: Record<string, { box: string; badge: string }> = {
  good: { box: "border-emerald-500/30 bg-emerald-500/[0.04]", badge: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40" },
  mid: { box: "border-amber-500/30 bg-amber-500/[0.04]", badge: "bg-amber-500/15 text-amber-300 ring-amber-500/40" },
  bad: { box: "border-rose-500/30 bg-rose-500/[0.04]", badge: "bg-rose-500/15 text-rose-300 ring-rose-500/40" },
};

export function InvestorView({ v }: { v: Verdict | null }) {
  if (!v) return null;
  const t = TONE[v.tone] ?? TONE.mid;
  return (
    <section className={`rounded-xl border p-5 ${t.box}`}>
      <div className="mb-1 flex flex-wrap items-center gap-3">
        <span className={`rounded-md px-3 py-1 text-sm font-bold ring-1 ring-inset ${t.badge}`}>{v.verdict}</span>
        <span className="font-medium text-zinc-200">{v.headline}</span>
        <span className="ml-auto text-xs text-zinc-500">Investment Assessment</span>
      </div>

      <div className="mt-4 grid gap-5 md:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-emerald-400/80">Investment Thesis</h3>
          <ul className="space-y-1.5 text-sm text-zinc-300">
            {v.thesis.map((s, i) => (
              <li key={i} className="flex gap-2"><span className="text-emerald-500">▸</span><span>{s}</span></li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-rose-400/80">Risks</h3>
          <ul className="space-y-1.5 text-sm text-zinc-400">
            {v.risks.map((s, i) => (
              <li key={i} className="flex gap-2"><span className="text-rose-500">▸</span><span>{s}</span></li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2 border-t border-zinc-800 pt-4">
        {v.lenses.map((l, i) => (
          <div
            key={i}
            className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs ${
              l.pass ? "border-emerald-500/30 text-emerald-300" : "border-zinc-700 text-zinc-500"
            }`}
            title={l.why}
          >
            <span>{l.pass ? "✓" : "✗"}</span>
            <span className="font-medium">{l.name}</span>
            <span className="hidden text-zinc-500 sm:inline">— {l.why}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
