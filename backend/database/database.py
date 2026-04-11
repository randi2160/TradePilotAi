import logging
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from database.models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./autotrader.db")

# Force SQLite if postgres connection string has no real credentials
if "postgresql" in DATABASE_URL and ("yourpassword" in DATABASE_URL or DATABASE_URL == "postgresql://autotrader:yourpassword@localhost:5432/autotrader"):
    DATABASE_URL = "sqlite:///./autotrader.db"
    logger.warning("PostgreSQL not configured — falling back to SQLite")

_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    except Exception as e:
        logger.warning(f"PostgreSQL failed ({e}) — falling back to SQLite")
        DATABASE_URL = "sqlite:///./autotrader.db"
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info(f"Database ready ✓ ({DATABASE_URL[:30]}...)")
    except Exception as e:
        logger.error(f"Database init error: {e}")
        raise


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB connection check failed: {e}")
        return False
