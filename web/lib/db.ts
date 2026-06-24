import postgres from "postgres";

// Single pooled client, reused across hot reloads in dev (Next re-evaluates
// modules on every change — without this we'd leak connections).
const g = globalThis as unknown as { _sql?: ReturnType<typeof postgres> };

const url = process.env.DATABASE_URL ?? "";
const isLocal = url.includes("localhost") || url.includes("127.0.0.1");

export const sql =
  g._sql ??
  postgres(url, {
    // Small pool in prod (Neon's pooled endpoint multiplexes anyway); a few
    // connections speed up the static prerender at build time.
    // Cloud Postgres (Neon/Supabase) requires SSL; localhost does not.
    max: isLocal ? 5 : 3,
    idle_timeout: 20,
    ssl: isLocal ? false : "require",
  });

if (process.env.NODE_ENV !== "production") g._sql = sql;
