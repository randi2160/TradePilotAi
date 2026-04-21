"""
SQLAlchemy database setup with PostgreSQL support
"""
import logging
import os
from dotenv import load_dotenv  # ← ADD THIS LINE
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

# Load environment variables from .env file
load_dotenv()

# Import Base first
from database.models import Base

# CRITICAL: Import all models so SQLAlchemy registers them
from database.models import (
    User, Trade, EquityHistory, DailyPnL, ProtectionSettings, Watchlist, Alert, Signal,
    TraderProfile, TradeBroadcast, Follow, BroadcastLike, BroadcastComment,
    SymbolChatMessage, Group, GroupMember, GroupPost, ModerationAction,
    CopyConfig, SocialNotification, AuditLog, ConsentRecord, LegalDocument,
    CompanySettings, AIAnalysisResult, TradeAlert, TradingAlert,
    DailyUserPick, AIRecommendation, AIPickAnalysis, UserReviewLog
)

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./autotrader.db")

# Detect database type
_is_sqlite = DATABASE_URL.startswith("sqlite")
_is_postgres = DATABASE_URL.startswith("postgresql")

# Create engine based on database type
if _is_sqlite:
    logger.info("Using SQLite database")
    # NullPool creates a new connection per request — safe for multi-threaded FastAPI + background tasks
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )

    # Enable WAL mode for better concurrent read/write performance
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=10000")
        cursor.close()

elif _is_postgres:
    logger.info("Using PostgreSQL database")
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,  # Set to True for SQL query logging
        )
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection successful ✓")
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        logger.warning("Falling back to SQLite")
        DATABASE_URL = "sqlite:///./autotrader.db"
        _is_sqlite = True
        _is_postgres = False
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
else:
    logger.error(f"Unsupported DATABASE_URL: {DATABASE_URL}")
    raise ValueError("DATABASE_URL must start with 'sqlite://' or 'postgresql://'")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _add_missing_columns():
    """Add new columns to existing tables — SQLAlchemy create_all won't do this."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return  # tables haven't been created yet
    existing = {c["name"] for c in inspector.get_columns("users")}
    new_cols = {
        "watchlist_json":              "TEXT DEFAULT ''",
        "engine_mode":                 "VARCHAR(20) DEFAULT 'stocks_only'",
        "crypto_alloc_pct":            "FLOAT DEFAULT 0.30",
        "after_hours_crypto_alloc_pct":"FLOAT DEFAULT 0.80",
        "crypto_strategy":             "VARCHAR(10) DEFAULT 'scalp'",
        "score_threshold":             "INTEGER DEFAULT 55",
        "stop_new_trades_hour":        "INTEGER DEFAULT 15",
        "stop_new_trades_minute":      "INTEGER DEFAULT 30",
        "max_open_positions":          "INTEGER DEFAULT 3",
    }
    with engine.begin() as conn:
        for col, typedef in new_cols.items():
            if col not in existing:
                try:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typedef}"))
                    logger.info(f"  + users.{col} added")
                except Exception as e:
                    logger.debug(f"  users.{col}: {e}")

def init_db():
    """Initialize database - create all tables if they don't exist"""
    try:
        Base.metadata.create_all(bind=engine)
        _add_missing_columns()
        db_type = "PostgreSQL" if _is_postgres else "SQLite"
        logger.info(f"Database ready ✓ ({db_type}: {DATABASE_URL[:50]}...)")
    except Exception as e:
        logger.error(f"Database init error: {e}")
        raise


def get_db() -> Session:
    """Dependency for FastAPI routes to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> bool:
    """Check if database connection is alive"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB connection check failed: {e}")
        return False


def get_db_type() -> str:
    """Return current database type"""
    return "postgresql" if _is_postgres else "sqlite"