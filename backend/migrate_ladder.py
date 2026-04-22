"""
migrate_ladder.py — add the ladder columns (per-position trail + scale-out)
to an existing database.

Why this exists
---------------
SQLAlchemy's Base.metadata.create_all() only CREATES missing tables — it never
ALTERs an existing table to add new columns. The ladder work added 8 columns to
`trades` and 6 columns to `protection_settings`, and on databases that already
have those tables the ORM will now emit queries that reference columns Postgres
doesn't know about ("column trades.original_qty does not exist").

This script closes that gap. It uses the app's own engine so it works against
whatever DATABASE_URL is set — Postgres in prod, SQLite locally — and is safe
to run repeatedly.

Usage
-----
    cd backend
    python migrate_ladder.py

On both Postgres and SQLite it:
  • Inspects the live schema to see which ladder columns already exist.
  • Issues `ALTER TABLE … ADD COLUMN …` only for the missing ones.
  • Prints a tidy summary.
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from database.database import engine, get_db_type, DATABASE_URL


# ── Column specs — (name, postgres_type, sqlite_type, default_sql) ───────────
# Keep these in lockstep with database/models.py.
TRADE_LADDER_COLUMNS = [
    # name,                  postgres,                    sqlite,                      default
    ("original_qty",         "DOUBLE PRECISION",          "REAL",                      None),
    ("peak_price",           "DOUBLE PRECISION",          "REAL",                      None),
    ("peak_unrealized_pct",  "DOUBLE PRECISION",          "REAL",                      "0"),
    ("peak_unrealized_pnl",  "DOUBLE PRECISION",          "REAL",                      "0"),
    ("trail_stop_pct",       "DOUBLE PRECISION",          "REAL",                      None),
    ("last_peak_at",         "TIMESTAMP",                 "TIMESTAMP",                 None),
    ("scaled_out_pct",       "DOUBLE PRECISION",          "REAL",                      "0"),
    ("scaleout_levels_hit",  "JSONB",                     "JSON",                      "'[]'"),
]

PROTECTION_LADDER_COLUMNS = [
    ("ladder_enabled",             "BOOLEAN",          "INTEGER",  "TRUE"),
    ("scaleout_enabled",           "BOOLEAN",          "INTEGER",  "TRUE"),
    ("scaleout_milestones",        "JSONB",            "JSON",     "'[0.05, 0.10, 0.15]'"),
    ("scaleout_fraction",          "DOUBLE PRECISION", "REAL",     "0.25"),
    ("concentration_pct",          "DOUBLE PRECISION", "REAL",     "0.30"),
    ("time_decay_hours",           "DOUBLE PRECISION", "REAL",     "4.0"),
    # ── Intra-milestone trailing harvest + recovery mode ────────────────────
    # Added in the gain-preservation upgrade: floor protection now also
    # captures partial progress between milestones, and the bot runs in a
    # special recovery mode when equity dips below the sacred base.
    ("intra_lock_pct",             "DOUBLE PRECISION", "REAL",     "0.30"),
    ("min_intra_gain",             "DOUBLE PRECISION", "REAL",     "15.0"),
    ("peak_equity_since_ratchet",  "DOUBLE PRECISION", "REAL",     None),
    ("recovery_size_mult",         "DOUBLE PRECISION", "REAL",     "0.60"),
    ("recovery_stop_mult",         "DOUBLE PRECISION", "REAL",     "0.75"),
    ("recovery_conf_boost",        "DOUBLE PRECISION", "REAL",     "0.05"),
    ("recovery_budget",            "DOUBLE PRECISION", "REAL",     "20.0"),
]


def _mask(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host  = rest.split("@", 1)
    if ":" in creds:
        user, _pw = creds.split(":", 1)
        creds = f"{user}:***"
    return f"{scheme}://{creds}@{host}"


def _existing_columns(inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except Exception:
        return set()


def _column_sql(table: str, col: str, col_type: str, default: str | None) -> str:
    """Build an ALTER TABLE … ADD COLUMN statement.

    We deliberately do NOT use IF NOT EXISTS — Postgres supports it from 9.6
    but SQLite doesn't. The caller checks column existence first and only
    calls us when the column is truly missing.
    """
    parts = [f'ALTER TABLE {table} ADD COLUMN {col} {col_type}']
    if default is not None:
        parts.append(f"DEFAULT {default}")
    return " ".join(parts)


def _add_missing(conn, inspector, table: str, cols, dialect: str) -> int:
    """Add any of the `cols` that aren't already on `table`. Returns count added."""
    if table not in inspector.get_table_names():
        print(f"  ! table {table!r} does not exist — skipping (run init_db first)")
        return 0

    existing = _existing_columns(inspector, table)
    added = 0
    for name, pg_type, sqlite_type, default in cols:
        if name in existing:
            continue
        col_type = pg_type if dialect == "postgresql" else sqlite_type
        ddl      = _column_sql(table, name, col_type, default)
        try:
            conn.execute(text(ddl))
            print(f"  + {table}.{name}")
            added += 1
        except Exception as e:
            print(f"  ! {table}.{name}: {e}")
    return added


def migrate() -> int:
    dialect = engine.dialect.name   # 'postgresql' or 'sqlite'
    print("=" * 62)
    print(" Ladder migration")
    print(f" DB:      {get_db_type()}  —  {_mask(DATABASE_URL)}")
    print(f" Dialect: {dialect}")
    print("=" * 62)

    inspector = inspect(engine)
    total = 0

    with engine.begin() as conn:            # transactional — rolls back on error
        # Refresh inspector inside the transaction so we see the live schema.
        inspector = inspect(conn)

        print("Migrating trades…")
        total += _add_missing(conn, inspector, "trades",
                              TRADE_LADDER_COLUMNS, dialect)

        # protection_settings may not exist yet on very old DBs.
        print("Migrating protection_settings…")
        total += _add_missing(conn, inspector, "protection_settings",
                              PROTECTION_LADDER_COLUMNS, dialect)

    print("-" * 62)
    print(f"✓ Ladder migration complete — {total} column(s) added.")
    print("  (Re-run any time; already-present columns are skipped.)")
    return total


if __name__ == "__main__":
    migrate()
