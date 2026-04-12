"""
migrate_db.py — Run this to add missing columns to existing database.
Safe to run multiple times — skips columns that already exist.

Usage: python migrate_db.py
"""
import sqlite3
import os

DB_PATH = "autotrader.db"

# All columns that should exist on the users table
# Format: (column_name, column_definition)
USER_COLUMNS = [
    ("phone",              "TEXT DEFAULT ''"),
    ("avatar_initials",    "TEXT DEFAULT ''"),
    ("risk_profile",       "TEXT DEFAULT 'moderate'"),
    ("broker_type",        "TEXT DEFAULT 'alpaca_paper'"),
    ("alpaca_key",         "TEXT DEFAULT ''"),
    ("alpaca_secret",      "TEXT DEFAULT ''"),
    ("alpaca_mode",        "TEXT DEFAULT 'paper'"),
    ("broker_creds",       "TEXT DEFAULT '{}'"),
    ("broker_connected",   "INTEGER DEFAULT 0"),
    ("broker_verified",    "INTEGER DEFAULT 0"),
    ("live_mode_enabled",  "INTEGER DEFAULT 0"),
    ("live_mode_at",       "TIMESTAMP"),
    ("email_alerts",       "INTEGER DEFAULT 1"),
    ("trading_mode",       "TEXT DEFAULT 'auto'"),
    ("dynamic_watchlist",  "INTEGER DEFAULT 0"),
    ("last_login",         "TIMESTAMP"),
    ("daily_target_min",   "REAL DEFAULT 100.0"),
    ("daily_target_max",   "REAL DEFAULT 250.0"),
    ("max_daily_loss",     "REAL DEFAULT 150.0"),
    ("subscription_tier",  "TEXT DEFAULT 'free'"),
]

TRADE_COLUMNS = [
    ("net_pnl",       "REAL"),
    ("commission",    "REAL DEFAULT 0.0"),
    ("slippage",      "REAL DEFAULT 0.0"),
    ("pnl_pct",       "REAL"),
    ("risk_dollars",  "REAL DEFAULT 0.0"),
    ("risk_pct",      "REAL DEFAULT 0.0"),
    ("position_value","REAL DEFAULT 0.0"),
    ("order_id",      "TEXT DEFAULT ''"),
    ("is_manual",     "INTEGER DEFAULT 0"),
    ("trade_date",    "TEXT DEFAULT ''"),
    ("opened_at",     "TIMESTAMP"),
    ("closed_at",     "TIMESTAMP"),
    ("signal_reasons","JSON DEFAULT '[]'"),
    ("setup_type",    "TEXT DEFAULT ''"),
    ("confidence",    "REAL DEFAULT 0.0"),
    ("stop_loss",     "REAL"),
    ("take_profit",   "REAL"),
]


def get_existing_columns(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"❌ {DB_PATH} not found — run python main.py first to create it")
        return

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"📦 Migrating {DB_PATH}...")

    # Migrate users table
    existing = get_existing_columns(cursor, "users")
    added = 0
    for col, defn in USER_COLUMNS:
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {defn}")
                print(f"  ✅ users.{col} added")
                added += 1
            except Exception as e:
                print(f"  ⚠️  users.{col}: {e}")
        else:
            print(f"  ✓  users.{col} already exists")

    # Migrate trades table
    if "trades" in [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
        existing = get_existing_columns(cursor, "trades")
        for col, defn in TRADE_COLUMNS:
            if col not in existing:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {defn}")
                    print(f"  ✅ trades.{col} added")
                    added += 1
                except Exception as e:
                    print(f"  ⚠️  trades.{col}: {e}")

    conn.commit()
    conn.close()

    print(f"\n✅ Migration complete — {added} columns added")
    print("Restart your backend now: python main.py")


if __name__ == "__main__":
    migrate()

# Compliance tables
USER_COMPLIANCE_COLUMNS = [
    ("is_admin", "INTEGER DEFAULT 0"),
    ("last_login", "TIMESTAMP"),
    ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ("mfa_enabled", "INTEGER DEFAULT 0"),
    ("failed_login_attempts", "INTEGER DEFAULT 0"),
    ("locked_until", "TIMESTAMP"),
]

def migrate_compliance():
    if not os.path.exists(DB_PATH):
        print(f"❌ {DB_PATH} not found")
        return
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print("📦 Migrating compliance columns...")
    existing = get_existing_columns(cursor, "users")
    for col, defn in USER_COMPLIANCE_COLUMNS:
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {defn}")
                print(f"  ✅ users.{col} added")
            except Exception as e:
                print(f"  ⚠️  users.{col}: {e}")
    conn.commit()
    conn.close()
    print("✅ Compliance migration done")

if __name__ == "__main__":
    migrate()
    migrate_compliance()

LEGAL_DOC_COLUMNS = [
    ("slug",           "TEXT DEFAULT ''"),
    ("show_in_footer", "INTEGER DEFAULT 0"),
    ("show_in_nav",    "INTEGER DEFAULT 0"),
    ("show_in_signup", "INTEGER DEFAULT 0"),
    ("footer_order",   "INTEGER DEFAULT 0"),
]

def migrate_legal_docs():
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "legal_documents" not in tables:
        print("legal_documents table not yet created — run Base.metadata.create_all first")
        conn.close()
        return
    print("📦 Migrating legal_documents columns...")
    existing = get_existing_columns(cursor, "legal_documents")
    for col, defn in LEGAL_DOC_COLUMNS:
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE legal_documents ADD COLUMN {col} {defn}")
                print(f"  ✅ legal_documents.{col} added")
            except Exception as e:
                print(f"  ⚠️  {col}: {e}")
        else:
            print(f"  ✓  legal_documents.{col} already exists")
    conn.commit()
    conn.close()
    print("✅ Legal docs migration done")

if __name__ == "__main__":
    migrate()
    migrate_compliance()
    migrate_legal_docs()