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
    is_admin         = Column(Boolean, default=False)
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


# ══════════════════════════════════════════════════════════════════════════════
# SOCIAL TRADING PLATFORM — Phase 1
# ══════════════════════════════════════════════════════════════════════════════

class TraderProfile(Base):
    __tablename__ = "trader_profiles"

    id               = Column(Integer, primary_key=True)
    user_id          = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    display_name     = Column(String(50),  default="")
    bio              = Column(Text,        default="")
    avatar_url       = Column(String(500), default="")
    is_public        = Column(Boolean,     default=True)
    is_copyable      = Column(Boolean,     default=False)  # must earn this
    min_copy_tier    = Column(String(20),  default="subscriber")

    # Auto-calculated performance
    total_trades     = Column(Integer, default=0)
    win_rate         = Column(Float,   default=0.0)
    avg_profit       = Column(Float,   default=0.0)
    total_pnl        = Column(Float,   default=0.0)
    max_drawdown     = Column(Float,   default=0.0)
    days_tracked     = Column(Integer, default=0)
    followers_count  = Column(Integer, default=0)
    following_count  = Column(Integer, default=0)

    # Subscription
    subscription_tier = Column(String(20), default="free")  # free|subscriber|pro
    subscription_at   = Column(DateTime,   nullable=True)

    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TradeBroadcast(Base):
    """Every bot trade automatically broadcasts to the social feed."""
    __tablename__ = "trade_broadcasts"

    id              = Column(Integer, primary_key=True, index=True)
    trader_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    trade_id        = Column(Integer, ForeignKey("trades.id"), nullable=True)

    # Trade snapshot
    symbol          = Column(String(10),   nullable=False, index=True)
    action          = Column(String(20),   nullable=False)  # BUY|SELL|STOP_HIT|TARGET_HIT|CLOSED
    qty             = Column(Float,        default=0)
    price           = Column(Float,        default=0)
    stop_loss       = Column(Float,        nullable=True)
    take_profit     = Column(Float,        nullable=True)
    confidence      = Column(Float,        default=0)
    setup_type      = Column(String(50),   default="")
    reasoning       = Column(Text,         default="")

    # Result (filled when trade closes)
    pnl             = Column(Float,        nullable=True)
    pnl_pct         = Column(Float,        nullable=True)
    duration_mins   = Column(Integer,      nullable=True)
    is_winner       = Column(Boolean,      nullable=True)

    # Visibility
    visibility      = Column(String(20),   default="public")  # public|followers|subscribers|private

    # Social engagement
    likes           = Column(Integer,      default=0)
    copies_count    = Column(Integer,      default=0)
    comments_count  = Column(Integer,      default=0)

    created_at      = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Follow(Base):
    __tablename__ = "follows"

    id           = Column(Integer, primary_key=True)
    follower_id  = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    leader_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    notify_trades = Column(Boolean, default=True)
    tier         = Column(String(20), default="free")
    created_at   = Column(DateTime,   default=datetime.utcnow)


class BroadcastLike(Base):
    __tablename__ = "broadcast_likes"
    id           = Column(Integer, primary_key=True)
    broadcast_id = Column(Integer, ForeignKey("trade_broadcasts.id"), nullable=False)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)


class BroadcastComment(Base):
    __tablename__ = "broadcast_comments"
    id           = Column(Integer, primary_key=True)
    broadcast_id = Column(Integer, ForeignKey("trade_broadcasts.id"), nullable=False, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    content      = Column(Text, nullable=False)
    is_flagged   = Column(Boolean, default=False)
    is_removed   = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow)


class SymbolChatMessage(Base):
    """Chat room per stock symbol — like StockTwits."""
    __tablename__ = "symbol_chat"

    id          = Column(Integer, primary_key=True, index=True)
    symbol      = Column(String(10), nullable=False, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    content     = Column(Text,    nullable=False)
    sentiment   = Column(String(10), default="neutral")  # bullish|bearish|neutral
    likes       = Column(Integer, default=0)
    is_flagged  = Column(Boolean, default=False)
    is_removed  = Column(Boolean, default=False)
    strike_reason = Column(String(200), default="")
    created_at  = Column(DateTime, default=datetime.utcnow, index=True)


class Group(Base):
    __tablename__ = "groups"

    id               = Column(Integer, primary_key=True)
    name             = Column(String(100), unique=True, nullable=False)
    description      = Column(Text, default="")
    creator_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_public        = Column(Boolean, default=True)
    invite_only      = Column(Boolean, default=False)
    category         = Column(String(30), default="general")  # momentum|swing|options|crypto|general
    rules            = Column(Text, default="")
    terms            = Column(Text, default="")
    min_win_rate     = Column(Float, nullable=True)
    member_count     = Column(Integer, default=1)
    trade_count      = Column(Integer, default=0)
    win_rate         = Column(Float, default=0.0)
    profanity_level  = Column(String(10), default="medium")  # low|medium|strict
    created_at       = Column(DateTime, default=datetime.utcnow)


class GroupMember(Base):
    __tablename__ = "group_members"

    id         = Column(Integer, primary_key=True)
    group_id   = Column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    role       = Column(String(20), default="member")  # owner|admin|mod|member
    joined_at  = Column(DateTime, default=datetime.utcnow)
    is_banned  = Column(Boolean, default=False)
    strikes    = Column(Integer, default=0)


class GroupPost(Base):
    __tablename__ = "group_posts"

    id           = Column(Integer, primary_key=True, index=True)
    group_id     = Column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    broadcast_id = Column(Integer, ForeignKey("trade_broadcasts.id"), nullable=True)
    symbol       = Column(String(10), nullable=True, index=True)
    content      = Column(Text, nullable=False)
    sentiment    = Column(String(10), default="neutral")
    is_pinned    = Column(Boolean, default=False)
    is_flagged   = Column(Boolean, default=False)
    is_removed   = Column(Boolean, default=False)
    likes        = Column(Integer, default=0)
    replies      = Column(Integer, default=0)
    created_at   = Column(DateTime, default=datetime.utcnow, index=True)


class ModerationAction(Base):
    __tablename__ = "moderation_actions"

    id             = Column(Integer, primary_key=True)
    group_id       = Column(Integer, ForeignKey("groups.id"), nullable=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    admin_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    action         = Column(String(20), nullable=False)  # warn|mute|temp_ban|perm_ban|remove_post
    reason         = Column(Text, default="")
    duration_hours = Column(Integer, nullable=True)  # null = permanent
    expires_at     = Column(DateTime, nullable=True)
    is_appealed    = Column(Boolean, default=False)
    appeal_status  = Column(String(20), default="none")  # none|pending|approved|rejected
    created_at     = Column(DateTime, default=datetime.utcnow)


class CopyConfig(Base):
    __tablename__ = "copy_configs"

    id              = Column(Integer, primary_key=True)
    follower_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    leader_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    mode            = Column(String(30), default="pct_of_capital")  # pct_of_leader|pct_of_capital|fixed_dollar
    copy_pct        = Column(Float, default=50.0)
    max_per_trade   = Column(Float, default=500.0)
    max_open        = Column(Integer, default=3)
    use_leader_stop = Column(Boolean, default=True)
    pause_after_loss= Column(Float, default=100.0)
    is_active       = Column(Boolean, default=True)
    started_at      = Column(DateTime, default=datetime.utcnow)


class SocialNotification(Base):
    __tablename__ = "social_notifications"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type         = Column(String(50), nullable=False)  # trade_broadcast|copy|follow|comment|ban
    title        = Column(String(200), default="")
    body         = Column(Text, default="")
    data         = Column(JSON, default={})
    is_read      = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow, index=True)


# ── Compliance & Admin Models ─────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id            = Column(Integer, primary_key=True, index=True)
    event_type    = Column(String(80), nullable=False, index=True)
    user_id       = Column(Integer, nullable=True, index=True)
    user_email    = Column(String(255), nullable=True)
    ip_address    = Column(String(45), nullable=True)
    user_agent    = Column(String(500), nullable=True)
    payload       = Column(Text, nullable=True)
    severity      = Column(String(20), default="info")
    prev_hash     = Column(String(64), nullable=True)
    entry_hash    = Column(String(64), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    is_exported   = Column(Boolean, default=False)


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, nullable=False, index=True)
    user_email       = Column(String(255), nullable=False)
    consent_type     = Column(String(80), nullable=False)
    document_version = Column(String(20), nullable=False)
    document_hash    = Column(String(64), nullable=False)
    accepted         = Column(Boolean, default=True)
    ip_address       = Column(String(45), nullable=True)
    user_agent       = Column(String(500), nullable=True)
    signature_hash   = Column(String(64), nullable=False)
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id             = Column(Integer, primary_key=True, index=True)
    doc_type       = Column(String(50), nullable=False, index=True)
    version        = Column(String(20), nullable=False)
    title          = Column(String(200), nullable=False)
    slug           = Column(String(100), nullable=True)   # e.g. "terms-of-service"
    content        = Column(Text, nullable=False)
    is_active      = Column(Boolean, default=True)
    show_in_footer = Column(Boolean, default=False)       # appears in site footer
    show_in_nav    = Column(Boolean, default=False)       # appears in top navigation
    show_in_signup = Column(Boolean, default=False)       # shown during user signup/onboarding
    footer_order   = Column(Integer, default=0)           # sort order in footer
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by     = Column(Integer, nullable=True)
    content_hash   = Column(String(64), nullable=False, default="")


class CompanySettings(Base):
    __tablename__ = "company_settings"

    id          = Column(Integer, primary_key=True)
    key         = Column(String(100), unique=True, nullable=False, index=True)
    value       = Column(Text, nullable=True)
    description = Column(String(500), nullable=True)
    is_public   = Column(Boolean, default=False)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by  = Column(Integer, nullable=True)