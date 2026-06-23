"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart, CandlestickSeries, ColorType,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";
import { fetchOhlc } from "@/lib/live";

const RANGES = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
];

export function LiveChart({ companyId }: { companyId: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [range, setRange] = useState(RANGES[1]);
  const [empty, setEmpty] = useState(false);

  // create the chart once
  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "inherit",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)", timeVisible: false },
    });
    seriesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: "#34d399", downColor: "#fb7185", borderVisible: false,
      wickUpColor: "#34d399", wickDownColor: "#fb7185",
    });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // (re)load data when company or range changes
  useEffect(() => {
    let alive = true;
    (async () => {
      const res = await fetchOhlc(companyId, range.days, 86400);
      if (!alive || !seriesRef.current) return;
      const seen = new Set<number>();
      const data = (res?.candles ?? [])
        .filter((c) => c.o && c.h && c.l && c.c)
        .sort((a, b) => a.t - b.t)
        .filter((c) => (seen.has(c.t) ? false : (seen.add(c.t), true)))
        .map((c) => ({ time: c.t as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c }));
      setEmpty(data.length === 0);
      seriesRef.current.setData(data);
      chartRef.current?.timeScale().fitContent();
    })();
    return () => { alive = false; };
  }, [companyId, range]);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-300">
          Price chart <span className="text-zinc-600">· daily · XTS</span>
        </h2>
        <div className="flex rounded-lg border border-zinc-800 bg-zinc-900/60 p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => setRange(r)}
              className={`rounded-md px-2 py-0.5 text-xs transition-colors ${
                range.label === r.label ? "bg-zinc-700 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={ref} className="h-[320px] w-full" />
      {empty && <p className="mt-2 text-xs text-zinc-600">No candles returned for this range.</p>}
    </div>
  );
}
