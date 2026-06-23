"use client";

import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { YearMetrics } from "@/lib/analysis";

const TIP = {
  contentStyle: { background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#e4e4e7" },
  itemStyle: { color: "#a1a1aa" },
};
const grid = "rgba(255,255,255,0.05)";
const axis = { stroke: "#52525b", fontSize: 11 };
const pctAxis = (v: number) => `${(v * 100).toFixed(0)}%`;
const pctTip = (v: number) => `${(v * 100).toFixed(1)}%`;

export function GrowthChart({ data }: { data: YearMetrics[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="label" {...axis} />
        <YAxis {...axis} />
        <Tooltip {...TIP} formatter={(v: number) => `₹${Math.round(v)} cr`} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="revenue" name="Revenue" fill="#34d399" radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="net_profit" name="Net Profit" fill="#60a5fa" radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function MarginChart({ data }: { data: YearMetrics[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="label" {...axis} />
        <YAxis {...axis} tickFormatter={pctAxis} />
        <Tooltip {...TIP} formatter={(v: number) => pctTip(v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="gross_margin" name="Gross" stroke="#34d399" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        <Line type="monotone" dataKey="op_margin" name="Operating" stroke="#fbbf24" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        <Line type="monotone" dataKey="net_margin" name="Net" stroke="#60a5fa" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ReturnsChart({ data }: { data: YearMetrics[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="label" {...axis} />
        <YAxis {...axis} tickFormatter={pctAxis} />
        <Tooltip {...TIP} formatter={(v: number) => pctTip(v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="roce" name="ROCE" stroke="#34d399" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        <Line type="monotone" dataKey="roe" name="ROE" stroke="#a78bfa" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

const SH_COLORS: Record<string, string> = {
  Promoter: "#34d399", FII: "#60a5fa", DII: "#fbbf24", Public: "#71717a",
};

export function ShareholdingPie({ latest }: { latest: { promoter_pct: number | null; fii_pct: number | null; dii_pct: number | null; public_pct: number | null } | null }) {
  if (!latest) return <p className="py-10 text-center text-xs text-zinc-600">No shareholding data.</p>;
  const data = [
    { name: "Promoter", value: latest.promoter_pct ?? 0 },
    { name: "FII", value: latest.fii_pct ?? 0 },
    { name: "DII", value: latest.dii_pct ?? 0 },
    { name: "Public", value: latest.public_pct ?? 0 },
  ].filter((d) => d.value > 0);
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={2}>
          {data.map((d) => <Cell key={d.name} fill={SH_COLORS[d.name]} stroke="#18181b" />)}
        </Pie>
        <Tooltip {...TIP} formatter={(v: number) => `${v.toFixed(1)}%`} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
