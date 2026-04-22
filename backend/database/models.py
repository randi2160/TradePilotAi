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

    # ── Per-user engine / isolation settings ─────────────────────────
    watchlist_json    = Column(Text,    default="")       # JSON array of symbols
    engine_mode       = Column(String(20), default="stocks_only")  # stocks_only|crypto_only|hybrid
    crypto_alloc_pct  = Column(Float,   default=0.30)
    after_hours_crypto_alloc_pct = Column(Float, default=0.80)
    crypto_strategy   = Column(String(10), default="scalp")
    score_threshold   = Column(Integer, default=55)
    stop_new_trades_hour   = Column(Integer, default=15)
    stop_new_trades_minute = Column(Integer, default=30)
    max_open_positions     = Column(Integer, default=3)

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

    # Subscription
    subscription_tier              = Column(String(20), default="free")
    stripe_customer_id             = Column(String(100), nullable=True)
    stripe_subscription_id         = Column(String(100), nullable=True)
    subscription_period_end        = Column(String(50),  nullable=True)
    subscription_cancel_at_period_end = Column(Boolean, default=False)

    # Admin test mode — simulate a different billing tier
    admin_test_tier                = Column(String(20), nullable=True)
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

    # ── Ladder protection (per-position trailing + scale-out) ──────────────────
    # Tracks the highest unrealized gain each position has ever seen so we can
    # trail from the peak instead of the current price. Updated live by
    # services.ladder_service every protection tick while status=='open'.
    original_qty         = Column(Float,    nullable=True)   # qty at entry, before any scale-outs
    peak_price           = Column(Float,    nullable=True)   # highest price seen since open (for LONG)
    peak_unrealized_pct  = Column(Float,    default=0.0)     # highest gain % reached (0.10 = +10%)
    peak_unrealized_pnl  = Column(Float,    default=0.0)     # highest $ gain reached
    trail_stop_pct       = Column(Float,    nullable=True)   # computed trail (as gain %) — closes below this
    last_peak_at         = Column(DateTime, nullable=True)   # last time we made a new high
    scaled_out_pct       = Column(Float,    default=0.0)     # fraction of original_qty already scaled out (0.0-1.0)
    scaleout_levels_hit  = Column(JSON,     default=list)    # list of milestone % already triggered e.g. [0.05, 0.10]

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


class DailyPnL(Base):
    """
    One row per (user_id, trade_date). Persists day-over-day performance so the
    dashboard can show compound running totals and today's delta without having
    to re-sum trades every page load.

    Populated by services.daily_pnl_service:
      - upserted live during the trading day (every ~30s or after each fill)
      - finalized at end of session when the bot stops or at market close
    """
    __tablename__ = "daily_pnl"

    id                 = Column(Integer, primary_key=True, index=True)
    user_id            = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    trade_date         = Column(String(10), nullable=False, index=True)   # YYYY-MM-DD (local trading day)

    # Equity snapshots — both DB-derived and Alpaca-derived, stored separately
    starting_equity    = Column(Float,   default=0.0)   # Alpaca equity at first snapshot of the day
    ending_equity      = Column(Float,   default=0.0)   # Alpaca equity at latest / end-of-day snapshot
    alpaca_cash        = Column(Float,   default=0.0)   # Alpaca cash balance at snapshot time
    alpaca_buying_power= Column(Float,   default=0.0)

    # P&L breakdown
    realized_pnl       = Column(Float,   default=0.0)   # sum(net_pnl) for trades closed today
    unrealized_pnl     = Column(Float,   default=0.0)   # sum(unrealized_pl) across open positions at snapshot time
    total_pnl          = Column(Float,   default=0.0)   # realized + unrealized (convenience)

    # Compound tracking — running cumulative totals since day 1 of this user
    compound_total     = Column(Float,   default=0.0)   # cumulative realized since account start
    compound_pct       = Column(Float,   default=0.0)   # cumulative return % vs. starting capital

    # Activity counters
    trade_count        = Column(Integer, default=0)
    win_count          = Column(Integer, default=0)
    loss_count         = Column(Integer, default=0)

    # State
    is_finalized       = Column(Boolean, default=False) # True once the day is closed out
    finalized_at       = Column(DateTime, nullable=True)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at         = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_daily_pnl_user_date", "user_id", "trade_date", unique=True),
    )


class ProtectionSettings(Base):
    """
    Account-level gain-protection rules for a user.

    Three layers work together to keep profits:

      1) INTRADAY floor (handled in strategy/daily_target.py + crypto_engine.py)
         — protects today's floating profit within a single session.

      2) HARVEST rule (this table + protection_service.harvest_positions)
         — converts large unrealized winners into realized so they count toward
         compound and push the account floor up. Without this, a $1,500
         unrealized day could evaporate and never raise the account floor.

      3) ACCOUNT floor (this table + protection_service.ratchet_floor)
         — monotonic floor that climbs as compound_total grows. If live equity
         ever drops below it, the breach_action fires (halt / close / alert).

    One row per user. Auto-created on first access with sensible defaults.
    """
    __tablename__ = "protection_settings"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    enabled     = Column(Boolean, default=True)

    # Account floor config
    floor_value           = Column(Float, default=5000.0)  # current locked floor (monotonic)
    initial_capital       = Column(Float, default=5000.0)  # snapshot of base at init — "never below this"
    milestone_size        = Column(Float, default=50.0)    # raise floor every $50 of compound gain (tighter)
    lock_pct              = Column(Float, default=0.90)    # % of each milestone permanently locked (strict)

    # Harvest config
    harvest_position_pct  = Column(Float, default=0.08)    # force-close a position at this unrealized gain
    harvest_portfolio_cap = Column(Float, default=500.0)   # or when total unrealized exceeds this

    # Ladder config — per-position trailing + scale-out
    # Tiers are hardcoded in services/ladder_service.LADDER_TIERS. These flags
    # just toggle whether the ladder runs at all, and the scale-out fractions.
    ladder_enabled        = Column(Boolean, default=True)
    scaleout_enabled      = Column(Boolean, default=True)
    scaleout_milestones   = Column(JSON,    default=lambda: [0.03, 0.05, 0.08, 0.12])  # scale out earlier
    scaleout_fraction     = Column(Float,   default=0.25)   # sell 25% of original qty at each milestone
    concentration_pct     = Column(Float,   default=0.30)   # bump tier when a position > 30% of equity
    time_decay_hours      = Column(Float,   default=3.0)    # bump tier if no new peak for 3h (tighter)

    # Breach behavior
    breach_action         = Column(String(20), default="halt_close")  # halt_close|halt_only|alert_only

    # State tracking
    last_ratchet_at       = Column(DateTime, nullable=True)
    last_breach_at        = Column(DateTime, nullable=True)
    last_harvest_at       = Column(DateTime, nullable=True)
    peak_compound         = Column(Float, default=0.0)     # high-water mark of compound_total

    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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


class AIAnalysisResult(Base):
    """Cached AI analysis results — avoids redundant OpenAI calls."""
    __tablename__ = "ai_analysis_results"

    id            = Column(Integer, primary_key=True, index=True)
    cache_key     = Column(String(200), unique=True, nullable=False, index=True)
    symbol        = Column(String(20),  nullable=False, index=True)
    analysis_type = Column(String(50),  nullable=False, default="sentiment")
    result_json   = Column(Text,        nullable=False)
    user_id       = Column(Integer,     nullable=True)
    created_at    = Column(DateTime,    default=datetime.utcnow, nullable=False, index=True)


class TradeAlert(Base):
    """Entry/exit alerts for watched symbols — shown in alert bell."""
    __tablename__ = "trade_alerts"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, nullable=False, index=True)
    symbol      = Column(String(20),  nullable=False)
    alert_type  = Column(String(30),  nullable=False)  # entry | exit | warning | info
    signal      = Column(String(10),  nullable=True)   # BUY | SELL | HOLD
    price       = Column(Float,       nullable=True)
    target      = Column(Float,       nullable=True)
    stop        = Column(Float,       nullable=True)
    confidence  = Column(Integer,     nullable=True)
    message     = Column(String(500), nullable=False)
    is_read     = Column(Boolean,     default=False)
    created_at  = Column(DateTime,    default=datetime.utcnow, index=True)


class TradingAlert(Base):
    """Full AI-generated entry/exit alerts with all analysis data."""
    __tablename__ = "trading_alerts"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, nullable=False, index=True)
    symbol      = Column(String(20),   nullable=False, index=True)
    alert_type  = Column(String(30),   nullable=False)  # BUY_SIGNAL | SELL_SIGNAL | STOP_HIT | TARGET_HIT | VOLUME
    signal      = Column(String(10),   nullable=True)   # BUY | SELL | HOLD
    confidence  = Column(Integer,      nullable=True)
    price       = Column(Float,        nullable=True)
    entry_price = Column(Float,        nullable=True)
    exit_price  = Column(Float,        nullable=True)
    stop_price  = Column(Float,        nullable=True)
    risk_reward = Column(Float,        nullable=True)
    reasoning   = Column(String(500),  nullable=True)
    indicators  = Column(Text,         nullable=True)   # JSON
    is_read     = Column(Boolean,      default=False)
    created_at  = Column(DateTime,     default=datetime.utcnow, index=True)


class DailyUserPick(Base):
    """Stocks user wants to invest in today — their personal daily list."""
    __tablename__ = "daily_user_picks"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, nullable=False, index=True)
    symbol      = Column(String(20), nullable=False)
    note        = Column(String(200), nullable=True)   # user's personal note
    trade_date  = Column(String(10), nullable=False)   # YYYY-MM-DD
    created_at  = Column(DateTime, default=datetime.utcnow)


class AIRecommendation(Base):
    """AI-generated trade suggestions for the day — shown on dashboard."""
    __tablename__ = "ai_recommendations"
    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, nullable=False, index=True)
    symbol         = Column(String(20), nullable=False)
    rank           = Column(Integer, nullable=False)   # 1, 2, 3 — numbered suggestions
    signal         = Column(String(10), nullable=False)  # BUY | SELL | HOLD
    confidence     = Column(Integer, nullable=True)
    score          = Column(Float, nullable=True)
    entry          = Column(Float, nullable=True)
    exit_target    = Column(Float, nullable=True)
    stop           = Column(Float, nullable=True)
    risk_reward    = Column(Float, nullable=True)
    suggested_qty  = Column(Integer, nullable=True)
    suggested_alloc= Column(Float, nullable=True)   # $ amount to allocate
    reasoning      = Column(Text, nullable=True)
    source         = Column(String(20), default="ai")  # ai | scanner | news
    trade_date     = Column(String(10), nullable=False)
    # Review flow
    status         = Column(String(20), default="pending")  # pending | reviewed | accepted | rejected
    reviewed_at    = Column(DateTime, nullable=True)
    accepted_at    = Column(DateTime, nullable=True)
    eligible_for_auto = Column(Boolean, default=False)  # only True after user accepts
    created_at     = Column(DateTime, default=datetime.utcnow, index=True)


class AIPickAnalysis(Base):
    """Detailed AI analysis result for a user's daily pick symbol."""
    __tablename__ = "ai_pick_analyses"
    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, nullable=False, index=True)
    symbol         = Column(String(20), nullable=False)
    trade_date     = Column(String(10), nullable=False)
    signal         = Column(String(10), nullable=True)
    confidence     = Column(Integer, nullable=True)
    score          = Column(Float, nullable=True)
    entry          = Column(Float, nullable=True)
    exit_target    = Column(Float, nullable=True)
    stop           = Column(Float, nullable=True)
    risk_reward    = Column(Float, nullable=True)
    reasoning      = Column(Text, nullable=True)
    vs_ai_verdict  = Column(Text, nullable=True)   # honest comparison text
    full_report    = Column(Text, nullable=True)   # JSON full analysis
    created_at     = Column(DateTime, default=datetime.utcnow)


class UserReviewLog(Base):
    """Audit log of user reviewing and accepting AI suggestions."""
    __tablename__ = "user_review_logs"
    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, nullable=False, index=True)
    recommendation_id = Column(Integer, nullable=True)
    symbol          = Column(String(20), nullable=False)
    action          = Column(String(20), nullable=False)  # reviewed | accepted | rejected
    notes           = Column(String(300), nullable=True)
    ip_address      = Column(String(50), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow, index=True)