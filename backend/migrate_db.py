"""
migrate_db.py — Run this to create/update all database tables.
Safe to run multiple times — skips columns/tables that already exist.

Usage: python migrate_db.py
"""
import sqlite3
import os

DB_PATH = "autotrader.db"

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
    ("is_admin",                  "INTEGER DEFAULT 0"),
    ("created_at",                "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ("mfa_enabled",               "INTEGER DEFAULT 0"),
    ("failed_login_attempts",     "INTEGER DEFAULT 0"),
    ("locked_until",              "TIMESTAMP"),
    ("stripe_customer_id",                "TEXT DEFAULT ''"),
    ("stripe_subscription_id",            "TEXT DEFAULT ''"),
    ("subscription_period_end",           "TEXT DEFAULT ''"),
    ("subscription_cancel_at_period_end", "INTEGER DEFAULT 0"),
    ("admin_test_tier",           "TEXT DEFAULT NULL"),
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

LEGAL_DOC_COLUMNS = [
    ("slug",           "TEXT DEFAULT ''"),
    ("show_in_footer", "INTEGER DEFAULT 0"),
    ("show_in_nav",    "INTEGER DEFAULT 0"),
    ("show_in_signup", "INTEGER DEFAULT 0"),
    ("footer_order",   "INTEGER DEFAULT 0"),
]


def get_existing_columns(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def get_existing_tables(cursor):
    return [r[0] for r in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found — run python main.py first")
        return
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print("Migrating users table...")
    existing = get_existing_columns(cursor, "users")
    added = 0
    for col, defn in USER_COLUMNS:
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {defn}")
                print(f"  + users.{col}")
                added += 1
            except Exception as e:
                print(f"  ! users.{col}: {e}")

    tables = get_existing_tables(cursor)
    if "trades" in tables:
        print("Migrating trades table...")
        existing = get_existing_columns(cursor, "trades")
        for col, defn in TRADE_COLUMNS:
            if col not in existing:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {defn}")
                    print(f"  + trades.{col}")
                    added += 1
                except Exception as e:
                    print(f"  ! trades.{col}: {e}")

    conn.commit()
    conn.close()
    print(f"Core migration done — {added} columns added")


def migrate_legal_docs():
    if not os.path.exists(DB_PATH):
        return
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    tables = get_existing_tables(cursor)
    if "legal_documents" not in tables:
        conn.close()
        return
    print("Migrating legal_documents...")
    existing = get_existing_columns(cursor, "legal_documents")
    for col, defn in LEGAL_DOC_COLUMNS:
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE legal_documents ADD COLUMN {col} {defn}")
                print(f"  + legal_documents.{col}")
            except Exception as e:
                print(f"  ! {col}: {e}")
    conn.commit()
    conn.close()


def migrate_ai_cache():
    print("Creating AI cache / alert tables via SQLAlchemy...")
    try:
        from database.database import engine
        from database.models   import Base
        Base.metadata.create_all(bind=engine)
        print("  + All SQLAlchemy tables created/verified")
    except Exception as e:
        print(f"  ! SQLAlchemy create_all: {e}")

    print("Seeding AI settings...")
    try:
        from database.database import SessionLocal
        from database.models   import CompanySettings
        db = SessionLocal()
        defaults = [
            ("ai_enabled",            "true",  "Global AI analysis on/off",               False),
            ("ai_refresh_free",       "900",   "Free tier AI refresh interval (seconds)",  True),
            ("ai_refresh_subscriber", "60",    "Subscriber AI refresh interval (seconds)", True),
            ("ai_refresh_pro",        "0",     "Pro tier AI refresh interval (seconds)",   True),
            ("ai_refresh_admin",      "0",     "Admin AI refresh interval (seconds)",      False),
            ("alerts_enabled",        "true",  "Trading alert system on/off",              False),
            ("alert_confidence_min",  "65",    "Min AI confidence to trigger alert",       False),
        ]
        for key, val, desc, public in defaults:
            existing = db.query(CompanySettings).filter_by(key=key).first()
            if not existing:
                db.add(CompanySettings(key=key, value=val, description=desc, is_public=public))
                print(f"  + Setting '{key}' = {val}")
        db.commit()
        db.close()
    except Exception as e:
        print(f"  ! Settings seed: {e}")


def migrate_trading_alerts():
    if not os.path.exists(DB_PATH):
        return
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    tables = get_existing_tables(cursor)
    if "trading_alerts" not in tables:
        print("Creating trading_alerts table...")
        cursor.execute("""
            CREATE TABLE trading_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                symbol      TEXT NOT NULL,
                alert_type  TEXT NOT NULL,
                signal      TEXT,
                confidence  INTEGER,
                price       REAL,
                entry_price REAL,
                exit_price  REAL,
                stop_price  REAL,
                risk_reward REAL,
                reasoning   TEXT,
                indicators  TEXT,
                is_read     INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_trading_alerts_user ON trading_alerts(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_trading_alerts_symbol ON trading_alerts(symbol)")
        print("  + trading_alerts created")
    conn.commit()
    conn.close()


def migrate_daily_advisor():
    if not os.path.exists(DB_PATH):
        return
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    tables = get_existing_tables(cursor)

    new_tables = {
        "daily_user_picks": """CREATE TABLE daily_user_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL, note TEXT, trade_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        "ai_recommendations": """CREATE TABLE ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL, rank INTEGER NOT NULL, signal TEXT,
            confidence INTEGER, score REAL, entry REAL, exit_target REAL,
            stop REAL, risk_reward REAL, suggested_qty INTEGER, suggested_alloc REAL,
            reasoning TEXT, source TEXT DEFAULT 'ai', trade_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending', reviewed_at TIMESTAMP, accepted_at TIMESTAMP,
            eligible_for_auto INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        "ai_pick_analyses": """CREATE TABLE ai_pick_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL, trade_date TEXT NOT NULL, signal TEXT,
            confidence INTEGER, score REAL, entry REAL, exit_target REAL,
            stop REAL, risk_reward REAL, reasoning TEXT, vs_ai_verdict TEXT,
            full_report TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        "user_review_logs": """CREATE TABLE user_review_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            recommendation_id INTEGER, symbol TEXT NOT NULL, action TEXT NOT NULL,
            notes TEXT, ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    }

    print("Migrating daily advisor tables...")
    for tbl, sql in new_tables.items():
        if tbl not in tables:
            cursor.execute(sql)
            print(f"  + {tbl} created")

    conn.commit()
    conn.close()


def migrate_user_isolation():
    """Add per-user settings columns so users don't share a global config."""
    if not os.path.exists(DB_PATH):
        return
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    new_columns = {
        "watchlist_json":              "TEXT DEFAULT ''",
        "engine_mode":                 "TEXT DEFAULT 'stocks_only'",
        "crypto_alloc_pct":            "REAL DEFAULT 0.30",
        "after_hours_crypto_alloc_pct":"REAL DEFAULT 0.80",
        "crypto_strategy":             "TEXT DEFAULT 'scalp'",
        "score_threshold":             "INTEGER DEFAULT 55",
        "stop_new_trades_hour":        "INTEGER DEFAULT 15",
        "stop_new_trades_minute":      "INTEGER DEFAULT 30",
        "max_open_positions":          "INTEGER DEFAULT 3",
    }

    cursor.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in cursor.fetchall()}

    for col, typedef in new_columns.items():
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
                print(f"  + users.{col} added")
            except Exception as e:
                print(f"  ! users.{col}: {e}")

    conn.commit()
    conn.close()


# ── ONE entry point — runs everything in order ───────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("Morviq AI — Database Migration")
    print("=" * 50)

    migrate()
    migrate_legal_docs()
    migrate_ai_cache()
    migrate_trading_alerts()
    migrate_daily_advisor()
    migrate_user_isolation()

    print("=" * 50)
    print("All migrations complete!")
    print("Next: python main.py")
    print("=" * 50)