"use client";

import { useEffect, useRef, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_LIVE_URL || "http://127.0.0.1:8088";

export type Quote = {
  ltp: number | null; pct_change: number | null;
  open: number | null; high: number | null; low: number | null; close: number | null;
  volume: number | null;
  bid: number | null; bid_qty: number | null;
  ask: number | null; ask_qty: number | null;
  last_trade_unix?: number;
};
export type Level = { price: number; qty: number; orders: number };
export type Depth = { bids: Level[]; asks: Level[]; ltp: number | null };
export type Candle = { t: number; o: number; h: number; l: number; c: number; v: number };

async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${BASE}${path}`, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null; // service down / market closed — caller shows a fallback
  }
}

export type NewsItem = { headline: string; category: string | null; pdf_url: string | null; at: string | null };

export const fetchQuote = (id: number) => getJSON<Quote>(`/live/quote/${id}`);
export const fetchDepth = (id: number) => getJSON<Depth>(`/live/depth/${id}`);
export const fetchOhlc = (id: number, days = 180, compression = 86400) =>
  getJSON<{ candles: Candle[] }>(`/live/ohlc/${id}?days=${days}&compression=${compression}`);
export const fetchNews = (id: number) => getJSON<{ items: NewsItem[] }>(`/news/${id}`);

export type BulkDeal = {
  deal_date: string; symbol: string; name: string; client_name: string;
  side: string; quantity: number | null; price: number | null; deal_type: string;
  is_known_investor: boolean; in_sme_universe: boolean; company_id: number | null;
};
export const fetchBulkDeals = () => getJSON<{ deals: BulkDeal[] }>(`/bulk-deals`);
export const fetchBulkDealsFor = (id: number) => getJSON<{ deals: BulkDeal[] }>(`/bulk-deals/${id}`);

/** Poll a fetcher on an interval; returns latest value (null until first load). */
export function usePoll<T>(fetcher: () => Promise<T | null>, intervalMs: number): {
  data: T | null;
  stale: boolean;
} {
  const [data, setData] = useState<T | null>(null);
  const [stale, setStale] = useState(false);
  const saved = useRef(fetcher);
  saved.current = fetcher;

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const d = await saved.current();
      if (!alive) return;
      if (d === null) setStale(true);
      else {
        setData(d);
        setStale(false);
      }
    };
    tick();
    const h = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(h);
    };
  }, [intervalMs]);

  return { data, stale };
}
