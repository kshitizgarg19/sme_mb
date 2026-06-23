"use client";

import { fetchDepth, usePoll, type Level } from "@/lib/live";

export function DepthLadder({ companyId }: { companyId: number }) {
  const { data } = usePoll(() => fetchDepth(companyId), 2500);
  const bids = data?.bids ?? [];
  const asks = data?.asks ?? [];
  const maxQty = Math.max(1, ...bids.map((b) => b.qty || 0), ...asks.map((a) => a.qty || 0));
  const totBid = bids.reduce((s, b) => s + (b.qty || 0), 0);
  const totAsk = asks.reduce((s, a) => s + (a.qty || 0), 0);
  const hasDepth = totBid > 0 || totAsk > 0;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <h2 className="mb-3 text-sm font-medium text-zinc-300">Market depth</h2>
      {!hasDepth ? (
        <p className="text-xs text-zinc-600">
          No live depth — market is closed (NSE trades 9:15–15:30 IST). Last-session price shown above.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <Side levels={bids} side="bid" maxQty={maxQty} />
          <Side levels={asks} side="ask" maxQty={maxQty} />
        </div>
      )}
      {(totBid > 0 || totAsk > 0) && (
        <div className="mt-3 flex justify-between border-t border-zinc-800 pt-2 text-xs">
          <span className="text-emerald-400/80">Σ bid {totBid.toLocaleString("en-IN")}</span>
          <span className="text-rose-400/80">Σ ask {totAsk.toLocaleString("en-IN")}</span>
        </div>
      )}
    </div>
  );
}

function Side({ levels, side, maxQty }: { levels: Level[]; side: "bid" | "ask"; maxQty: number }) {
  const bar = side === "bid" ? "bg-emerald-500/15" : "bg-rose-500/15";
  const price = side === "bid" ? "text-emerald-300" : "text-rose-300";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[11px] text-zinc-500">
        <span>{side === "bid" ? "Bid" : "Ask"}</span>
        <span>Qty</span>
      </div>
      {levels.map((l, i) => (
        <div key={i} className="relative flex justify-between overflow-hidden rounded px-1.5 py-0.5 text-xs">
          <div
            className={`absolute inset-y-0 ${side === "bid" ? "right-0" : "left-0"} ${bar}`}
            style={{ width: `${Math.min(100, ((l.qty || 0) / maxQty) * 100)}%` }}
          />
          <span className={`tnum relative ${price}`}>{l.price?.toLocaleString("en-IN") ?? "—"}</span>
          <span className="tnum relative text-zinc-300">{l.qty?.toLocaleString("en-IN") ?? "—"}</span>
        </div>
      ))}
    </div>
  );
}
