type SH = {
  period: string;
  promoter_pct: number | null;
  fii_pct: number | null;
  dii_pct: number | null;
  public_pct: number | null;
};

const p1 = (v: number | null) => (v === null || Number.isNaN(v) ? "—" : `${v.toFixed(1)}%`);

export function ShareholdingPanel({ rows }: { rows: SH[] }) {
  if (!rows.length) {
    return (
      <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
        <h2 className="mb-2 text-sm font-medium text-zinc-300">Shareholding</h2>
        <p className="text-xs text-zinc-600">No shareholding captured yet for this name.</p>
      </section>
    );
  }
  const latest = rows[rows.length - 1];
  const first = rows[0];
  const delta = (latest.promoter_pct ?? 0) - (first.promoter_pct ?? 0);
  const maxP = Math.max(...rows.map((r) => r.promoter_pct ?? 0), 1);
  const rising = delta >= 0;

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-300">
          Shareholding <span className="text-zinc-600">· promoter trend</span>
        </h2>
        <span className={`text-xs ${rising ? "text-emerald-400" : "text-rose-400"}`}>
          promoter {rising ? "▲" : "▼"} {Math.abs(delta).toFixed(1)} over {rows.length}q
        </span>
      </div>

      {/* promoter % bars over quarters */}
      <div className="flex h-24 items-end gap-1">
        {rows.map((r, i) => {
          const h = ((r.promoter_pct ?? 0) / maxP) * 100;
          const last = i === rows.length - 1;
          return (
            <div key={i} className="flex flex-1 flex-col items-center gap-1" title={`${r.period}: ${p1(r.promoter_pct)}`}>
              <div className={`w-full rounded-t ${last ? "bg-emerald-400" : "bg-emerald-500/50"}`} style={{ height: `${h}%` }} />
              <span className="text-[9px] text-zinc-600">{r.period.replace(/ ?'?\d\d$/, "")}</span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 grid grid-cols-4 gap-2 border-t border-zinc-800 pt-3 text-sm">
        <Cell label="Promoter" v={p1(latest.promoter_pct)} strong />
        <Cell label="FII" v={p1(latest.fii_pct)} />
        <Cell label="DII" v={p1(latest.dii_pct)} />
        <Cell label="Public" v={p1(latest.public_pct)} />
      </div>
    </section>
  );
}

function Cell({ label, v, strong }: { label: string; v: string; strong?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-zinc-500">{label}</div>
      <div className={`tnum ${strong ? "text-emerald-300" : "text-zinc-200"}`}>{v}</div>
    </div>
  );
}
