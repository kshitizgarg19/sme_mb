"""Database engine, schema bootstrap, and upsert helpers.

``schema.sql`` is the single source of truth for DDL — we execute it rather than
mirror 150 columns in ORM classes that would silently drift. For reads/writes we
use SQLAlchemy Core with the Postgres ``ON CONFLICT`` upsert so the daily ETL is
idempotent (re-running a day overwrites, never duplicates).
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import Engine, MetaData, Table, create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import ROOT, get_settings

log = logging.getLogger("smescanner.db")
_engine: Engine | None = None
_metadata = MetaData()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url, pool_pre_ping=True, future=True
        )
    return _engine


def init_db(schema_path: Path | None = None) -> None:
    """Run schema.sql (idempotent). Call once on setup / in migrations."""
    path = schema_path or (ROOT / "db" / "schema.sql")
    sql = path.read_text(encoding="utf-8")
    eng = get_engine()
    with eng.begin() as conn:
        # psycopg can execute a multi-statement script in one go.
        conn.exec_driver_sql(sql)
    log.info("Schema applied from %s", path)


def _reflect(table: str) -> Table:
    if table not in _metadata.tables:
        Table(table, _metadata, autoload_with=get_engine())
    return _metadata.tables[table]


def upsert(table: str, rows: Sequence[dict], conflict_cols: Iterable[str]) -> int:
    """Bulk INSERT ... ON CONFLICT (conflict_cols) DO UPDATE.

    Updates every non-conflict column with the incoming value. Returns rowcount.
    """
    rows = [r for r in rows if r]
    if not rows:
        return 0
    tbl = _reflect(table)
    valid = {c.name for c in tbl.columns}
    # (1) keep only real columns — scrapers carry derived keys (Screener's
    #     _expenses, equity_capital, …); (2) scrub NaN/inf, invalid in PG numerics
    #     and JSON (e.g. a Beneish index that divided by zero).
    rows = [_sanitize({k: v for k, v in r.items() if k in valid}) for r in rows]
    # (3) homogenise keys across the batch: a multi-row INSERT requires every row
    #     to carry the *same* columns, but Screener legitimately reports different
    #     line items per fiscal year. Union the keys, filling gaps with None.
    all_keys = sorted(set().union(*(r.keys() for r in rows)))
    rows = [{k: r.get(k) for k in all_keys} for r in rows]
    conflict_cols = list(conflict_cols)
    # Only ON CONFLICT-update columns we actually supplied — never clobber an
    # existing value with NULL just because this batch didn't include that field.
    update_cols = [k for k in all_keys if k not in conflict_cols]
    eng = get_engine()
    total = 0
    with eng.begin() as conn:
        for chunk in _chunks(rows, 500):  # chunk to bound parameter counts
            stmt = pg_insert(tbl).values(chunk)
            if update_cols:
                stmt = stmt.on_conflict_do_update(
                    index_elements=conflict_cols,
                    set_={c: stmt.excluded[c] for c in update_cols},
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
            res = conn.execute(stmt)
            total += res.rowcount or 0
    return total


def _sanitize(v: Any) -> Any:
    """Recursively replace NaN/inf (invalid in PG numerics and JSON) with None."""
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, dict):
        return {k: _sanitize(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_sanitize(x) for x in v]
    return v


def fetch_df(query: str, **params):
    """Run a query and return a pandas DataFrame (used by the dashboard)."""
    import pandas as pd

    with get_engine().connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


def _chunks(seq: Sequence[dict], n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
