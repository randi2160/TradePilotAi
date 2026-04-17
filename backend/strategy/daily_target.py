"""
Tracks daily realized and unrealized P&L against the $100-$250 target.
- Persists to DB so restarts don't lose today's progress
- Resets automatically at midnight (new trading day)
- Records session start/stop timestamps
"""
import logging
from datetime import date, datetime
from typing import Optional

import config

logger = logging.getLogger(__name__)


class DailyTargetTracker:
    def __init__(
        self,
        capital:          float = config.CAPITAL,
        daily_target_min: float = config.DAILY_TARGET_MIN,
        daily_target_max: float = config.DAILY_TARGET_MAX,
        max_daily_loss:   float = config.MAX_DAILY_LOSS,
        user_id:          Optional[int] = None,
    ):
        self.capital          = capital
        self.target_min       = daily_target_min
        self.target_max       = daily_target_max
        self.max_daily_loss   = max_daily_loss
        # Per-user scoping for DB reads. When set, load_from_db filters
        # trades by this user_id so each user's bot tracks only its own P&L.
        self.user_id          = user_id
        self._today           = date.today()
        self.realized_pnl     = 0.0
        self.unrealized_pnl   = 0.0
        self._trades: list    = []
        self._entry_prices: dict = {}
        self._session_start: Optional[datetime] = None
        self._session_stop:  Optional[datetime] = None
        self._db_loaded       = False
        # Trailing profit lock
        self.locked_floor: Optional[float] = None
        self.peak_pnl: float = 0.0

    def load_from_db(self, db_session=None):
        """
        Load today's closed trades from DB on startup so restarts
        don't lose P&L history. Call this once when bot starts.
        """
        if db_session is None:
            try:
                from database.database import SessionLocal
                db_session = SessionLocal()
                close_after = True
            except Exception as e:
                logger.error(f"Could not connect to DB for PnL restore: {e}")
                return
        else:
            close_after = False

        try:
            from database.models import Trade
            today = str(date.today())
            q = db_session.query(Trade).filter(
                Trade.trade_date == today,
                Trade.status     == "closed",
                Trade.pnl        != None,
            )
            # Per-user scoping — only restore THIS bot's trades.
            if self.user_id is not None:
                q = q.filter(Trade.user_id == self.user_id)
            trades = q.all()

            self.realized_pnl = round(sum(t.pnl or 0 for t in trades), 2)
            self._trades = [
                {
                    "id":          t.id,
                    "symbol":      t.symbol,
                    "side":        t.side,
                    "qty":         t.qty,
                    "entry_price": t.entry_price or 0,
                    "exit_price":  t.exit_price  or 0,
                    "pnl":         round(t.pnl or 0, 2),
                    "pnl_pct":     round(t.pnl_pct or 0, 2),
                    "cumulative_pnl": 0,
                    "confidence":  t.confidence or 0,
                    "timestamp":   t.opened_at.isoformat() if t.opened_at else "",
                }
                for t in trades
            ]
            self._db_loaded = True
            logger.info(
                f"Restored today's P&L from DB: ${self.realized_pnl:.2f} "
                f"({len(self._trades)} closed trades)"
            )
        except Exception as e:
            logger.error(f"Failed to load P&L from DB: {e}")
        finally:
            if close_after:
                try: db_session.close()
                except: pass

    # ── Day-reset guard ────────────────────────────────────────────────────────

    def _guard(self):
        today = date.today()
        if today != self._today:
            self._today         = today
            self.realized_pnl   = 0.0
            self.unrealized_pnl = 0.0
            self._trades        = []
            self._entry_prices  = {}
            self._db_loaded     = False
            logger.info("New trading day — P&L reset ✓")

    # ── Session tracking ───────────────────────────────────────────────────────

    def record_session_start(self):
        self._session_start = datetime.now()
        logger.info(f"Bot session started: {self._session_start.strftime('%Y-%m-%d %H:%M:%S')}")

    def record_session_stop(self):
        self._session_stop = datetime.now()
        duration = ""
        if self._session_start:
            secs = int((self._session_stop - self._session_start).total_seconds())
            duration = f" (ran {secs//3600}h {(secs%3600)//60}m)"
        logger.info(
            f"Bot session stopped: {self._session_stop.strftime('%Y-%m-%d %H:%M:%S')}{duration} "
            f"| Today's P&L: ${self.realized_pnl:.2f}"
        )

    # ── Trade recording ────────────────────────────────────────────────────────

    def record_open(self, symbol: str, entry_price: float, qty: float, side: str):
        self._guard()
        self._entry_prices[symbol] = {"price": entry_price, "qty": qty, "side": side}

    def record_close(
        self,
        symbol:    str,
        exit_price: float,
        qty:       Optional[float] = None,
        signal:    Optional[dict]  = None,
    ) -> dict:
        self._guard()
        info  = self._entry_prices.pop(symbol, {})
        entry = info.get("price", exit_price)
        q     = qty or info.get("qty", 1)
        side  = info.get("side", "BUY")

        pnl = (exit_price - entry) * q if side == "BUY" else (entry - exit_price) * q
        self.realized_pnl += pnl

        trade = {
            "id":             len(self._trades) + 1,
            "symbol":         symbol,
            "side":           side,
            "qty":            q,
            "entry_price":    round(entry, 2),
            "exit_price":     round(exit_price, 2),
            "pnl":            round(pnl, 2),
            "pnl_pct":        round(pnl / (entry * q) * 100, 2) if entry > 0 else 0,
            "cumulative_pnl": round(self.realized_pnl, 2),
            "confidence":     (signal or {}).get("confidence", 0),
            "reasons":        (signal or {}).get("reasons", []),
            "timestamp":      datetime.now().isoformat(),
        }
        self._trades.append(trade)
        emoji = "✅" if pnl > 0 else "❌"
        logger.info(f"{emoji} {symbol} closed | PnL=${pnl:.2f} | Day total=${self.realized_pnl:.2f}")
        # Update trailing profit lock after every close
        self.update_trailing_lock()
        return trade

    def update_unrealized(self, total_unrealized_pnl: float):
        self._guard()
        self.unrealized_pnl = total_unrealized_pnl

    # ── Queries ────────────────────────────────────────────────────────────────

    def total_pnl(self) -> float:
        self._guard()
        return round(self.realized_pnl + self.unrealized_pnl, 2)

    def is_min_target_hit(self) -> bool:
        return self.realized_pnl >= self.target_min

    def is_max_target_hit(self) -> bool:
        return self.realized_pnl >= self.target_max

    def update_trailing_lock(self):
        """
        Call after each trade close. Raises the profit floor as gains grow.
        Never stops just because target is hit — only stops on drawdown to floor.
        """
        pnl = self.realized_pnl

        # Track peak
        if pnl > self.peak_pnl:
            self.peak_pnl = pnl

        # Activate floor once min target is hit
        if pnl >= self.target_min and self.locked_floor is None:
            self.locked_floor = round(self.target_min * 0.97, 2)
            logger.info(f"🔒 Stock profit lock activated: floor ${self.locked_floor:.2f}")

        # Trail upward — floor rises as P&L grows, never drops
        if self.locked_floor is not None and pnl > self.target_min:
            trail_pct = 0.94 if pnl < self.target_max * 1.5 else 0.96
            candidate = round(pnl * trail_pct, 2)
            if candidate > self.locked_floor:
                old = self.locked_floor
                self.locked_floor = candidate
                logger.info(
                    f"🔒 Stock floor raised: ${old:.2f} → ${self.locked_floor:.2f} "
                    f"(trailing {int(trail_pct*100)}% of ${pnl:.2f})"
                )

    def should_stop(self) -> tuple[bool, str]:
        self._guard()
        pnl = self.realized_pnl
        max_loss = self.max_daily_loss

        # Hard loss limit
        if pnl <= -max_loss:
            return True, f"Daily loss limit hit (${pnl:.2f})"

        # Trailing floor breach — protect locked gains
        if self.locked_floor is not None and pnl < self.locked_floor:
            return True, (
                f"Trailing floor triggered — P&L ${pnl:.2f} dropped to "
                f"floor ${self.locked_floor:.2f}. Gains protected ✅"
            )

        # No longer stop at max_target — keep trading while market is good
        # The trailing floor handles protection automatically
        return False, ""

    def progress_pct(self) -> float:
        if self.target_min <= 0:
            return 0.0
        return round(min(max(self.realized_pnl / self.target_min * 100, 0), 100), 1)

    def win_rate(self) -> float:
        if not self._trades:
            return 0.0
        wins = sum(1 for t in self._trades if t["pnl"] > 0)
        return round(wins / len(self._trades) * 100, 1)

    def stats(self) -> dict:
        self._guard()
        wins   = sum(1 for t in self._trades if t["pnl"] > 0)
        losses = sum(1 for t in self._trades if t["pnl"] <= 0)
        return {
            "date":             str(self._today),
            "capital":          self.capital,
            "realized_pnl":     round(self.realized_pnl, 2),
            "unrealized_pnl":   round(self.unrealized_pnl, 2),
            "total_pnl":        self.total_pnl(),
            "target_min":       self.target_min,
            "target_max":       self.target_max,
            "max_daily_loss":   self.max_daily_loss,
            "progress_pct":     self.progress_pct(),
            "min_target_hit":   self.is_min_target_hit(),
            "max_target_hit":   self.is_max_target_hit(),
            "locked_floor":     self.locked_floor,
            "peak_pnl":         round(self.peak_pnl, 2),
            "trade_count":      len(self._trades),
            "wins":             wins,
            "losses":           losses,
            "win_rate":         self.win_rate(),
            "session_start":    self._session_start.isoformat() if self._session_start else None,
            "session_stop":     self._session_stop.isoformat()  if self._session_stop  else None,
            "db_loaded":        self._db_loaded,
        }

    def recent_trades(self, n: int = 20) -> list:
        return list(reversed(self._trades[-n:]))

    def all_trades(self) -> list:
        return list(reversed(self._trades))