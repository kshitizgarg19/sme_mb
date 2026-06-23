import postgres from "postgres";

// Single pooled client, reused across hot reloads in dev (Next re-evaluates
// modules on every change — without this we'd leak connections).
const g = globalThis as unknown as { _sql?: ReturnType<typeof postgres> };

const url = process.env.DATABASE_URL ?? "";
const isLocal = url.includes("localhost") || url.includes("127.0.0.1");

export const sql =
  g._sql ??
  postgres(url, {
    // Serverless (Vercel) reuses few connections — keep the pool tiny in prod.
    // Cloud Postgres (Neon/Supabase) requires SSL; localhost does not.
    max: isLocal ? 5 : 1,
    idle_timeout: 20,
    ssl: isLocal ? false : "require",
  });

if (process.env.NODE_ENV !== "production") g._sql = sql;
