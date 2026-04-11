"""
SQLAlchemy database models — all persistent data lives here.
Tables: users, trades, equity_history, signals, alerts, watchlists
"""
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON, Index
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(255), default="")
    phone           = Column(String(30),  default="")
    avatar_initials = Column(String(4),   default="")

    # Trading config per user
    capital          = Column(Float, default=5000.0)
    daily_target_min = Column(Float, default=100.0)
    daily_target_max = Column(Float, default=250.0)
    max_daily_loss   = Column(Float, default=150.0)
    risk_profile     = Column(String(20), default="moderate")

    # Broker — multi-broker support
    broker_type      = Column(String(30),  default="alpaca_paper")  # alpaca_paper|alpaca_live|ibkr|tradier
    alpaca_key       = Column(String(500), default="")   # encrypted in production
    alpaca_secret    = Column(String(500), default="")
    alpaca_mode      = Column(String(10),  default="paper")
    # Generic broker credentials (JSON blob, encrypted)
    broker_creds     = Column(Text,       default="{}")  # JSON: {"api_key":"...","api_secret":"..."}
    broker_connected = Column(Boolean,    default=False)
    broker_verified  = Column(Boolean,    default=False)
    live_mode_enabled= Column(Boolean,    default=False)  # must pass safety check to enable
    live_mode_at     = Column(DateTime,   nullable=True)

    # Preferences
    email_alerts     = Column(Boolean, default=True)
    trading_mode     = Column(String(10), default="auto")
    dynamic_watchlist = Column(Boolean,  default=False)

    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    last_login       = Column(DateTime, nullable=True)

    # Relationships
    trades         = relationship("Trade",         back_populates="user", cascade="all, delete")
    equity_history = relationship("EquityHistory", back_populates="user", cascade="all, delete")
    watchlist      = relationship("Watchlist",     back_populates="user", cascade="all, delete", uselist=False)
    alerts         = relationship("Alert",         back_populates="user", cascade="all, delete")


class Trade(Base):
    __tablename__ = "trades"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Core trade data
    symbol          = Column(String(10),  nullable=False, index=True)
    side            = Column(String(4),   nullable=False)   # BUY | SELL
    qty             = Column(Float,       nullable=False)
    entry_price     = Column(Float,       nullable=False)
    exit_price      = Column(Float,       nullable=True)
    stop_loss       = Column(Float,       nullable=True)
    take_profit     = Column(Float,       nullable=True)

    # P&L
    pnl             = Column(Float,       nullable=True)
    pnl_pct         = Column(Float,       nullable=True)
    commission      = Column(Float,       default=0.0)
    slippage        = Column(Float,       default=0.0)
    net_pnl         = Column(Float,       nullable=True)   # pnl - commission - slippage

    # Position sizing
    position_value  = Column(Float,       nullable=True)   # qty × entry_price
    risk_dollars    = Column(Float,       nullable=True)   # dollars at risk
    risk_pct        = Column(Float,       nullable=True)   # % of capital at risk

    # AI context
    confidence      = Column(Float,       nullable=True)
    signal_reasons  = Column(JSON,        nullable=True)
    ai_advice       = Column(Text,        nullable=True)
    ml_trained      = Column(Boolean,     default=False)

    # Status
    status          = Column(String(20),  default="open")  # open | closed | cancelled
    order_id        = Column(String(100), nullable=True)
    is_manual       = Column(Boolean,     default=False)

    # Timestamps
    opened_at       = Column(DateTime,    default=datetime.utcnow, index=True)
    closed_at       = Column(DateTime,    nullable=True)
    trade_date      = Column(String(10),  nullable=True)   # YYYY-MM-DD for daily grouping

    user            = relationship("User", back_populates="trades")

    __table_args__ = (
        Index("ix_trades_user_date", "user_id", "trade_date"),
    )


class EquityHistory(Base):
    __tablename__ = "equity_history"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    value      = Column(Float,   nullable=False)
    cash       = Column(Float,   nullable=True)
    pnl_today  = Column(Float,   nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="equity_history")


class Watchlist(Base):
    __tablename__ = "watchlists"

    id       = Column(Integer, primary_key=True)
    user_id  = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    symbols  = Column(JSON, default=list)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="watchlist")


class Alert(Base):
    __tablename__ = "alerts"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    alert_type = Column(String(50),  nullable=False)   # trade_filled, target_hit, stop_loss, etc.
    subject    = Column(String(255), nullable=False)
    body       = Column(Text,        nullable=False)
    sent       = Column(Boolean,     default=False)
    sent_at    = Column(DateTime,    nullable=True)
    created_at = Column(DateTime,    default=datetime.utcnow)

    user = relationship("User", back_populates="alerts")


class Signal(Base):
    __tablename__ = "signals"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol     = Column(String(10),  nullable=False)
    signal     = Column(String(10),  nullable=False)
    confidence = Column(Float,       nullable=True)
    rsi        = Column(Float,       nullable=True)
    atr        = Column(Float,       nullable=True)
    price      = Column(Float,       nullable=True)
    reasons    = Column(JSON,        nullable=True)
    acted_on   = Column(Boolean,     default=False)
    created_at = Column(DateTime,    default=datetime.utcnow, index=True)
