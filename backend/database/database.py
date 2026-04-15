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
    User, Trade, EquityHistory, Watchlist, Alert, Signal,
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


def init_db():
    """Initialize database - create all tables if they don't exist"""
    try:
        Base.metadata.create_all(bind=engine)
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