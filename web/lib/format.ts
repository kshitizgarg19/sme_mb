// Display helpers. Tolerant of null / string (postgres NUMERIC can arrive as
// string when not explicitly cast) so the UI never renders "NaN".
const n = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
};

export const score = (v: unknown): string => {
  const x = n(v);
  return x === null ? "—" : x.toFixed(1);
};

export const pct = (v: unknown, d = 1): string => {
  const x = n(v);
  return x === null ? "—" : `${(x * 100).toFixed(d)}%`;
};

export const ratio = (v: unknown, d = 2): string => {
  const x = n(v);
  return x === null ? "—" : x.toFixed(d);
};

// market caps / financials are stored in ₹ crore
export const crore = (v: unknown): string => {
  const x = n(v);
  if (x === null) return "—";
  if (Math.abs(x) >= 1000) return `₹${(x / 1000).toFixed(2)}k Cr`;
  return `₹${x.toFixed(0)} Cr`;
};

export const int = (v: unknown): string => {
  const x = n(v);
  return x === null ? "—" : Math.round(x).toLocaleString("en-IN");
};

export const toNum = n;
