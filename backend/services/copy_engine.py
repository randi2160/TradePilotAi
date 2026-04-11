"""
Copy Trading Engine — when a leader executes a trade,
this engine automatically mirrors it into all active copiers' accounts.

Flow:
  Leader trade executes → engine.py calls broadcast_trade()
  broadcast_trade() → triggers copy_engine.process_broadcast()
  copy_engine → finds all active CopyConfigs for this leader
  copy_engine → sizes position for each copier
  copy_engine → places order in copier's broker account
  copy_engine → logs CopyExecution record
  copy_engine → notifies copier
"""
import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session

from database.models import (
    CopyConfig, User, TradeBroadcast, Trade,
    SocialNotification, TraderProfile,
)

logger = logging.getLogger(__name__)


class CopyTradingEngine:
    def __init__(self, db: Session):
        self.db = db

    def process_broadcast(self, broadcast: TradeBroadcast, leader: User):
        """
        Called every time a leader's trade is broadcast.
        Finds all active copiers and mirrors the trade.
        """
        # Only copy BUY entries — not closes/stops (copier manages own exits)
        if broadcast.action not in ("BUY",):
            return

        if not broadcast.price or broadcast.price <= 0:
            return

        # Get all active copy configs for this leader
        configs = self.db.query(CopyConfig).filter(
            CopyConfig.leader_id == leader.id,
            CopyConfig.is_active  == True,
        ).all()

        if not configs:
            return

        logger.info(f"Copy engine: {len(configs)} copiers for {leader.email} → {broadcast.symbol}")

        for config in configs:
            try:
                self._execute_copy(broadcast, leader, config)
            except Exception as e:
                logger.error(f"Copy failed for config {config.id}: {e}")

    def _execute_copy(
        self,
        broadcast: TradeBroadcast,
        leader:    User,
        config:    CopyConfig,
    ):
        """Execute one copy trade for one follower."""
        follower = self.db.query(User).filter_by(id=config.follower_id).first()
        if not follower:
            return

        # Check follower's daily loss limit
        today_copies = self.db.query(Trade).filter(
            Trade.user_id   == follower.id,
            Trade.trade_date == str(date.today()),
            Trade.is_manual == False,
        ).all()

        daily_pnl = sum(t.pnl or 0 for t in today_copies if t.status == "closed")
        if daily_pnl <= -config.pause_after_loss:
            logger.info(f"Copy paused for {follower.email} — daily loss limit ${config.pause_after_loss} hit")
            self._notify(follower.id, "copy_paused",
                "Copy trading paused",
                f"Daily loss limit of ${config.pause_after_loss} reached. Copy trading paused for today.")
            return

        # Check max open copied positions
        open_copies = self.db.query(Trade).filter(
            Trade.user_id    == follower.id,
            Trade.status     == "open",
            Trade.is_manual  == False,
        ).count()

        if open_copies >= config.max_open:
            logger.info(f"Copy skipped for {follower.email} — max {config.max_open} open positions")
            return

        # Calculate position size for copier
        qty = self._calculate_size(broadcast, config, follower)
        if qty <= 0:
            logger.info(f"Copy skipped for {follower.email} — qty=0 (insufficient capital)")
            return

        # Get follower's broker
        broker = self._get_broker(follower)
        if not broker:
            logger.warning(f"No broker for follower {follower.email}")
            return

        # Place the order
        stop  = broadcast.stop_loss   if config.use_leader_stop else None
        target= broadcast.take_profit

        if stop and target:
            order = broker.place_bracket_order(
                symbol      = broadcast.symbol,
                qty         = qty,
                side        = "BUY",
                stop_loss   = stop,
                take_profit = target,
            )
        else:
            order = broker.place_market_order(broadcast.symbol, qty, "BUY")

        if "error" in order:
            logger.error(f"Copy order failed for {follower.email}: {order['error']}")
            return

        # Save copy trade to DB
        trade = Trade(
            user_id        = follower.id,
            symbol         = broadcast.symbol,
            side           = "BUY",
            qty            = qty,
            entry_price    = broadcast.price,
            stop_loss      = stop,
            take_profit    = target,
            confidence     = broadcast.confidence,
            position_value = round(qty * broadcast.price, 2),
            order_id       = order.get("id", ""),
            is_manual      = False,
            status         = "open",
            trade_date     = str(date.today()),
            opened_at      = datetime.utcnow(),
        )
        self.db.add(trade)

        # Update broadcast copy count
        broadcast.copies_count = (broadcast.copies_count or 0) + 1
        self.db.commit()

        # Notify follower
        leader_profile = self.db.query(TraderProfile).filter_by(user_id=leader.id).first()
        leader_name    = leader_profile.display_name if leader_profile else leader.email.split("@")[0]

        self._notify(
            follower.id,
            "copy_executed",
            f"Trade copied from {leader_name}",
            f"Auto-copied: BUY {qty} {broadcast.symbol} @ ${broadcast.price:.2f} | "
            f"SL ${stop:.2f}" if stop else f"Auto-copied: BUY {qty} {broadcast.symbol} @ ${broadcast.price:.2f}",
        )

        logger.info(
            f"✅ COPY: {follower.email} → {qty}x{broadcast.symbol} @ ${broadcast.price:.2f} "
            f"(mode={config.mode}, leader={leader.email})"
        )

    def _calculate_size(
        self,
        broadcast: TradeBroadcast,
        config:    CopyConfig,
        follower:  User,
    ) -> float:
        """Calculate how many shares the copier should buy."""
        price    = broadcast.price
        capital  = follower.capital or 5000.0

        if config.mode == "pct_of_leader":
            # Copy same % of capital as leader used
            leader_value = (broadcast.qty or 1) * price
            # Estimate leader's capital — use their profile or default
            leader_profile = self.db.query(TraderProfile).filter_by(
                user_id=broadcast.trader_id
            ).first()
            leader_capital = 5000.0  # default
            leader_pct     = leader_value / leader_capital if leader_capital > 0 else 0.1
            dollar_amount  = capital * leader_pct * (config.copy_pct / 100)

        elif config.mode == "pct_of_capital":
            # Use fixed % of copier's own capital
            dollar_amount = capital * (config.copy_pct / 100)

        elif config.mode == "fixed_dollar":
            dollar_amount = config.copy_pct  # copy_pct stores dollar amount in this mode

        else:
            dollar_amount = capital * 0.10  # default 10%

        # Apply max per trade cap
        dollar_amount = min(dollar_amount, config.max_per_trade)

        qty = dollar_amount / price if price > 0 else 0
        return max(round(qty, 0), 0)  # whole shares only

    def _get_broker(self, user: User):
        """Get broker instance for a user."""
        try:
            import json, config as cfg
            from broker.broker_factory import get_broker

            creds = {}
            try:
                creds = json.loads(user.broker_creds or "{}")
            except Exception:
                pass

            if not creds and user.alpaca_key:
                creds = {"api_key": user.alpaca_key, "api_secret": user.alpaca_secret}

            if not creds and cfg.ALPACA_API_KEY:
                creds = {"api_key": cfg.ALPACA_API_KEY, "api_secret": cfg.ALPACA_SECRET_KEY}

            if not creds:
                return None

            broker_type = user.broker_type or "alpaca_paper"
            if not user.broker_connected:
                broker_type = "alpaca_live" if cfg.ALPACA_MODE == "live" else "alpaca_paper"

            return get_broker(broker_type, creds)
        except Exception as e:
            logger.error(f"Could not get broker for {user.email}: {e}")
            return None

    def _notify(self, user_id: int, ntype: str, title: str, body: str):
        notif = SocialNotification(
            user_id    = user_id,
            type       = ntype,
            title      = title,
            body       = body,
            data       = {},
            is_read    = False,
            created_at = datetime.utcnow(),
        )
        self.db.add(notif)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

    # ── Management ──────────────────────────────────────────────────────────

    def get_copy_configs(self, follower_id: int) -> list:
        configs = self.db.query(CopyConfig).filter_by(follower_id=follower_id).all()
        result  = []
        for c in configs:
            leader  = self.db.query(User).filter_by(id=c.leader_id).first()
            profile = self.db.query(TraderProfile).filter_by(user_id=c.leader_id).first()
            result.append({
                "id":              c.id,
                "leader_id":       c.leader_id,
                "leader_name":     profile.display_name if profile else (leader.email.split("@")[0] if leader else "Unknown"),
                "leader_win_rate": profile.win_rate if profile else 0,
                "mode":            c.mode,
                "copy_pct":        c.copy_pct,
                "max_per_trade":   c.max_per_trade,
                "max_open":        c.max_open,
                "use_leader_stop": c.use_leader_stop,
                "pause_after_loss":c.pause_after_loss,
                "is_active":       c.is_active,
                "started_at":      c.started_at.isoformat() if c.started_at else "",
            })
        return result

    def start_copy(
        self,
        follower_id:     int,
        leader_id:       int,
        mode:            str   = "pct_of_capital",
        copy_pct:        float = 10.0,
        max_per_trade:   float = 500.0,
        max_open:        int   = 3,
        use_leader_stop: bool  = True,
        pause_after_loss:float = 100.0,
    ) -> dict:
        """Start copying a leader's trades."""
        # Validate leader has a profile
        profile = self.db.query(TraderProfile).filter_by(user_id=leader_id).first()
        if not profile:
            # Auto-create profile so they can be copied
            leader = self.db.query(User).filter_by(id=leader_id).first()
            if not leader:
                return {"error": "Leader not found"}
            profile = TraderProfile(
                user_id      = leader_id,
                display_name = leader.full_name or leader.email.split("@")[0],
                is_public    = True,
                is_copyable  = True,  # allow immediately for testing
            )
            self.db.add(profile)
            self.db.commit()

        # For testing: allow copying anyone with at least 1 trade
        # In production, uncomment the strict check below
        # if not profile.is_copyable:
        #     return {"error": f"Not copyable yet. Need 30+ days and 60%+ win rate"}

        # Check if already copying
        existing = self.db.query(CopyConfig).filter_by(
            follower_id=follower_id, leader_id=leader_id
        ).first()

        if existing:
            existing.is_active        = True
            existing.mode             = mode
            existing.copy_pct         = copy_pct
            existing.max_per_trade    = max_per_trade
            existing.max_open         = max_open
            existing.use_leader_stop  = use_leader_stop
            existing.pause_after_loss = pause_after_loss
            self.db.commit()
            return {"status": "updated", "config_id": existing.id}

        config = CopyConfig(
            follower_id      = follower_id,
            leader_id        = leader_id,
            mode             = mode,
            copy_pct         = copy_pct,
            max_per_trade    = max_per_trade,
            max_open         = max_open,
            use_leader_stop  = use_leader_stop,
            pause_after_loss = pause_after_loss,
            is_active        = True,
            started_at       = datetime.utcnow(),
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return {"status": "started", "config_id": config.id}

    def stop_copy(self, follower_id: int, leader_id: int) -> dict:
        config = self.db.query(CopyConfig).filter_by(
            follower_id=follower_id, leader_id=leader_id
        ).first()
        if config:
            config.is_active = False
            self.db.commit()
        return {"status": "stopped"}
