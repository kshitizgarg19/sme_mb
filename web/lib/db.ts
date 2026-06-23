import postgres from "postgres";

// Single pooled client, reused across hot reloads in dev (Next re-evaluates
// modules on every change — without this we'd leak connections).
const g = globalThis as unknown as { _sql?: ReturnType<typeof postgres> };

export const sql =
  g._sql ??
  postgres(process.env.DATABASE_URL!, {
    max: 5,
    idle_timeout: 20,
    // NUMERIC -> JS number where we don't cast in SQL; we mostly ::float8 cast.
  });

if (process.env.NODE_ENV !== "production") g._sql = sql;
