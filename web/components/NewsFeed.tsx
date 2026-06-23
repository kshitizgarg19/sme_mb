"use client";

import { useEffect, useState } from "react";
import { fetchNews, type NewsItem } from "@/lib/live";

export function NewsFeed({ companyId }: { companyId: number }) {
  const [items, setItems] = useState<NewsItem[] | null>(null);

  useEffect(() => {
    let alive = true;
    setItems(null);
    fetchNews(companyId).then((d) => {
      if (alive) setItems(d?.items ?? []);
    });
    return () => {
      alive = false;
    };
  }, [companyId]);

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <h2 className="mb-3 text-sm font-medium text-zinc-300">
        News &amp; filings <span className="text-zinc-600">· NSE corporate announcements</span>
      </h2>

      {items === null ? (
        <p className="text-xs text-zinc-600">Loading announcements…</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-zinc-600">No recent announcements (or service offline).</p>
      ) : (
        <ul className="max-h-96 space-y-2 overflow-y-auto pr-1">
          {items.map((n, i) => (
            <li key={i} className="border-b border-zinc-800/50 pb-2 last:border-0">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm leading-snug text-zinc-300">{n.headline}</p>
                {n.pdf_url && (
                  <a href={n.pdf_url} target="_blank" rel="noopener noreferrer"
                    className="shrink-0 rounded border border-zinc-700 px-1.5 py-0.5 text-[11px] text-zinc-400 transition-colors hover:border-emerald-500/40 hover:text-emerald-300">
                    PDF ↗
                  </a>
                )}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[11px] text-zinc-500">
                {n.category && <span className="rounded bg-zinc-800 px-1.5 py-0.5">{n.category}</span>}
                <span>{n.at}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
