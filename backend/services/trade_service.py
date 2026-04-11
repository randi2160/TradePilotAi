"""
Trade service — persists all trades, signals, and equity snapshots to PostgreSQL.
Also handles manual trade placement and PDT rule tracking.
"""
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import Trade, EquityHistory, Signal, Watchlist

logger = logging.getLogger(__name__)

# Estimated commission per trade (Alpaca is free but model slippage)
SLIPPAGE_PCT = 0.0005   # 0.05% per side


class TradeService:
    def __init__(self, db: Session, user_id: int):
        self.db      = db
        self.user_id = user_id

    # ── Trade lifecycle ───────────────────────────────────────────────────────

    def open_trade(
        self,
        symbol:         str,
        side:           str,
        qty:            float,
        entry_price:    float,
        stop_loss:      float,
        take_profit:    float,
        confidence:     float     = 0.0,
        signal_reasons: list      = None,
        risk_dollars:   float     = 0.0,
        risk_pct:       float     = 0.0,
        order_id:       str       = "",
        is_manual:      bool      = False,
    ) -> Trade:
        position_value = round(qty * entry_price, 2)
        slippage       = round(position_value * SLIPPAGE_PCT, 2)

        trade = Trade(
            user_id        = self.user_id,
            symbol         = symbol.upper(),
            side           = side.upper(),
            qty            = qty,
            entry_price    = entry_price,
            stop_loss      = stop_loss,
            take_profit    = take_profit,
            confidence     = confidence,
            signal_reasons = signal_reasons or [],
            risk_dollars   = risk_dollars,
            risk_pct       = risk_pct,
            position_value = position_value,
            slippage       = slippage,
            order_id       = order_id,
            is_manual      = is_manual,
            status         = "open",
            trade_date     = str(date.today()),
            opened_at      = datetime.utcnow(),
        )
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        logger.info(f"Trade opened: {side} {qty}×{symbol} @ ${entry_price} [DB id={trade.id}]")
        return trade

    def close_trade(
        self,
        trade_id:    int,
        exit_price:  float,
        reason:      str = "",
    ) -> Optional[Trade]:
        trade = self.db.query(Trade).filter(
            Trade.id == trade_id, Trade.user_id == self.user_id
        ).first()

        if not trade or trade.status != "open":
            return None

        trade.exit_price = exit_price
        trade.closed_at  = datetime.utcnow()
        trade.status     = "closed"

        if trade.side == "BUY":
            gross_pnl = (exit_price - trade.entry_price) * trade.qty
        else:
            gross_pnl = (trade.entry_price - exit_price) * trade.qty

        commission      = 0.0   # Alpaca is commission-free
        slippage_exit   = round(exit_price * trade.qty * SLIPPAGE_PCT, 2)
        net_pnl         = gross_pnl - commission - slippage_exit - (trade.slippage or 0)

        trade.pnl        = round(gross_pnl, 2)
        trade.net_pnl    = round(net_pnl, 2)
        trade.commission = commission
        trade.pnl_pct    = round(gross_pnl / (trade.entry_price * trade.qty) * 100, 2) if trade.entry_price else 0

        self.db.commit()
        self.db.refresh(trade)
        logger.info(f"Trade closed: {trade.symbol} @ ${exit_price} | PnL=${gross_pnl:.2f}")
        return trade

    def get_open_trades(self) -> list:
        return self.db.query(Trade).filter(
            Trade.user_id == self.user_id,
            Trade.status  == "open",
        ).all()

    def get_trade_by_symbol(self, symbol: str) -> Optional[Trade]:
        return self.db.query(Trade).filter(
            Trade.user_id == self.user_id,
            Trade.symbol  == symbol.upper(),
            Trade.status  == "open",
        ).first()

    # ── History & stats ───────────────────────────────────────────────────────

    def get_trades(self, limit: int = 100, trade_date: str = None) -> list:
        q = self.db.query(Trade).filter(Trade.user_id == self.user_id)
        if trade_date:
            q = q.filter(Trade.trade_date == trade_date)
        return q.order_by(Trade.opened_at.desc()).limit(limit).all()

    def get_today_stats(self) -> dict:
        today  = str(date.today())
        trades = self.db.query(Trade).filter(
            Trade.user_id   == self.user_id,
            Trade.trade_date == today,
            Trade.status    == "closed",
        ).all()

        realized_pnl = sum(t.pnl or 0 for t in trades)
        wins         = [t for t in trades if (t.pnl or 0) > 0]
        losses       = [t for t in trades if (t.pnl or 0) < 0]

        return {
            "date":           today,
            "trade_count":    len(trades),
            "realized_pnl":   round(realized_pnl, 2),
            "wins":           len(wins),
            "losses":         len(losses),
            "win_rate":       round(len(wins)/len(trades)*100, 1) if trades else 0,
            "avg_win":        round(sum(t.pnl for t in wins)/len(wins), 2) if wins else 0,
            "avg_loss":       round(sum(t.pnl for t in losses)/len(losses), 2) if losses else 0,
            "best_trade":     max((t.pnl or 0 for t in trades), default=0),
            "worst_trade":    min((t.pnl or 0 for t in trades), default=0),
            "total_volume":   round(sum((t.position_value or 0) for t in trades), 2),
        }

    def get_performance_summary(self, days: int = 30) -> dict:
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(days=days)
        trades = self.db.query(Trade).filter(
            Trade.user_id  == self.user_id,
            Trade.status   == "closed",
            Trade.opened_at >= since,
        ).all()

        if not trades:
            return {"days": days, "trades": 0}

        pnls  = [t.pnl or 0 for t in trades]
        wins  = [p for p in pnls if p > 0]
        losses= [p for p in pnls if p < 0]

        # P&L by symbol
        by_symbol = {}
        for t in trades:
            by_symbol.setdefault(t.symbol, []).append(t.pnl or 0)
        symbol_pnl = {sym: round(sum(pnls_), 2) for sym, pnls_ in by_symbol.items()}

        return {
            "days":            days,
            "total_trades":    len(trades),
            "total_pnl":       round(sum(pnls), 2),
            "win_rate":        round(len(wins)/len(pnls)*100, 1),
            "avg_win":         round(sum(wins)/len(wins), 2)   if wins   else 0,
            "avg_loss":        round(sum(losses)/len(losses), 2) if losses else 0,
            "profit_factor":   round(sum(wins)/abs(sum(losses)), 2) if losses else 999,
            "best_day_pnl":    round(max(pnls), 2),
            "worst_day_pnl":   round(min(pnls), 2),
            "pnl_by_symbol":   symbol_pnl,
            "manual_trades":   sum(1 for t in trades if t.is_manual),
            "ai_trades":       sum(1 for t in trades if not t.is_manual),
        }

    # ── Equity history ─────────────────────────────────────────────────────────

    def record_equity(self, value: float, cash: float = 0, pnl_today: float = 0):
        snap = EquityHistory(
            user_id    = self.user_id,
            value      = round(value, 2),
            cash       = round(cash, 2),
            pnl_today  = round(pnl_today, 2),
            recorded_at = datetime.utcnow(),
        )
        self.db.add(snap)
        self.db.commit()

    def get_equity_history(self, hours: int = 24) -> list:
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(hours=hours)
        rows  = self.db.query(EquityHistory).filter(
            EquityHistory.user_id    == self.user_id,
            EquityHistory.recorded_at >= since,
        ).order_by(EquityHistory.recorded_at).all()
        return [
            {"time": r.recorded_at.isoformat(), "value": r.value, "pnl_today": r.pnl_today}
            for r in rows
        ]

    # ── Watchlist (DB-backed) ──────────────────────────────────────────────────

    def get_watchlist(self) -> list:
        wl = self.db.query(Watchlist).filter(Watchlist.user_id == self.user_id).first()
        return wl.symbols if wl else []

    def set_watchlist(self, symbols: list):
        wl = self.db.query(Watchlist).filter(Watchlist.user_id == self.user_id).first()
        if wl:
            wl.symbols = [s.upper() for s in symbols]
        else:
            self.db.add(Watchlist(user_id=self.user_id, symbols=[s.upper() for s in symbols]))
        self.db.commit()


# ── PDT Rule Tracker ──────────────────────────────────────────────────────────

class PDTTracker:
    """
    Pattern Day Trader protection — warns if approaching 4 day trades
    in a rolling 5-business-day window with < $25,000 equity.
    """
    def __init__(self, db: Session, user_id: int, equity: float):
        self.db      = db
        self.user_id = user_id
        self.equity  = equity

    def check(self) -> dict:
        if self.equity >= 25_000:
            return {"pdt_risk": False, "message": "Equity ≥ $25K — PDT rule does not apply"}

        from datetime import timedelta
        since  = datetime.utcnow() - timedelta(days=5)
        trades = self.db.query(Trade).filter(
            Trade.user_id  == self.user_id,
            Trade.status   == "closed",
            Trade.opened_at >= since,
            Trade.is_manual == False,
        ).all()

        # Count opening day trades (round-trip same day)
        day_trade_count = sum(
            1 for t in trades
            if t.opened_at and t.closed_at and
               t.opened_at.date() == t.closed_at.date()
        )

        remaining = max(0, 3 - day_trade_count)
        warning   = day_trade_count >= 3

        return {
            "pdt_risk":        warning,
            "day_trades_used": day_trade_count,
            "day_trades_left": remaining,
            "equity":          self.equity,
            "pdt_threshold":   25_000,
            "message":         (
                f"⚠️ PDT WARNING: {day_trade_count}/3 day trades used this week!"
                if warning else
                f"{day_trade_count}/3 day trades used — {remaining} remaining"
            ),
        }
