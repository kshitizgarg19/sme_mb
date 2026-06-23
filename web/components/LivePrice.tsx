"use client";

import { fetchQuote, usePoll } from "@/lib/live";

export function LivePrice({ companyId, fallbackClose }: { companyId: number; fallbackClose?: number | null }) {
  const { data, stale } = usePoll(() => fetchQuote(companyId), 3000);
  const ltp = data?.ltp ?? fallbackClose ?? null;
  const pct = data?.pct_change ?? null;
  const up = (pct ?? 0) >= 0;

  const fmt = (v: number | null | undefined, d = 2) =>
    v === null || v === undefined ? "—" : v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <div className="mb-3 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${data && !stale ? "animate-pulse bg-emerald-400" : "bg-zinc-600"}`} />
        <span className="text-xs font-medium tracking-wide text-zinc-400">
          {data ? "LIVE" : "LIVE — connecting"} <span className="text-zinc-600">· XTS</span>
        </span>
      </div>

      <div className="flex items-end gap-3">
        <span className="tnum text-4xl font-bold text-zinc-100">{ltp === null ? "—" : `₹${fmt(ltp)}`}</span>
        {pct !== null && (
          <span className={`tnum mb-1 text-lg font-semibold ${up ? "text-emerald-400" : "text-rose-400"}`}>
            {up ? "▲" : "▼"} {fmt(Math.abs(pct))}%
          </span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-4 gap-x-4 gap-y-2 text-sm">
        <Stat label="Open" v={fmt(data?.open)} />
        <Stat label="High" v={fmt(data?.high)} tone="up" />
        <Stat label="Low" v={fmt(data?.low)} tone="down" />
        <Stat label="Prev" v={fmt(data?.close)} />
        <Stat label="Bid" v={`${fmt(data?.bid)} × ${data?.bid_qty ?? "—"}`} tone="up" />
        <Stat label="Ask" v={`${fmt(data?.ask)} × ${data?.ask_qty ?? "—"}`} tone="down" />
        <Stat label="Volume" v={data?.volume != null ? data.volume.toLocaleString("en-IN") : "—"} span={2} />
      </div>
      {!data && (
        <p className="mt-3 text-xs text-zinc-600">
          No live tick yet — market may be closed, or the live service isn&apos;t running.
        </p>
      )}
    </div>
  );
}

function Stat({ label, v, tone, span = 1 }: { label: string; v: string; tone?: "up" | "down"; span?: number }) {
  const color = tone === "up" ? "text-emerald-300/90" : tone === "down" ? "text-rose-300/90" : "text-zinc-200";
  return (
    <div style={{ gridColumn: `span ${span}` }}>
      <div className="text-[11px] text-zinc-500">{label}</div>
      <div className={`tnum ${color}`}>{v}</div>
    </div>
  );
}
