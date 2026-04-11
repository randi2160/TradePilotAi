"""
Dual Engine Manager — runs AI Scalper and Peak Bounce simultaneously,
tracks P&L for each independently, enforces per-engine loss limits,
and stops both when the combined daily goal is hit.
"""
import asyncio
import logging
from datetime import datetime, date
from typing import Optional

import pytz

from strategy.capital_allocator import CapitalAllocator
from strategy.peak_bounce       import PeakBounceEngine, DEFAULT_WINDOW

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


class EngineStats:
    """Tracks live stats for one engine."""
    def __init__(self, name: str, capital: float, daily_target: float, loss_limit: float):
        self.name          = name
        self.capital       = capital
        self.daily_target  = daily_target
        self.loss_limit    = loss_limit
        self.realized_pnl  = 0.0
        self.unrealized_pnl = 0.0
        self.trade_count   = 0
        self.win_count     = 0
        self.trades: list  = []
        self.status        = "idle"     # idle | running | paused | stopped
        self.stop_reason   = ""
        self.last_trade    = ""
        self.started_at    = ""

    @property
    def total_pnl(self)  -> float:
        return round(self.realized_pnl + self.unrealized_pnl, 2)

    @property
    def win_rate(self)   -> float:
        return round(self.win_count / self.trade_count * 100, 1) if self.trade_count else 0.0

    @property
    def progress_pct(self) -> float:
        return round(min(self.realized_pnl / self.daily_target * 100, 100), 1) if self.daily_target > 0 else 0.0

    @property
    def is_target_hit(self) -> bool:
        return self.realized_pnl >= self.daily_target

    @property
    def is_loss_limit_hit(self) -> bool:
        return self.realized_pnl <= -self.loss_limit

    def record_trade(self, symbol: str, pnl: float, side: str):
        self.realized_pnl += pnl
        self.trade_count  += 1
        if pnl > 0:
            self.win_count += 1
        self.trades.append({
            "symbol":     symbol,
            "pnl":        round(pnl, 2),
            "side":       side,
            "cumulative": round(self.realized_pnl, 2),
            "timestamp":  datetime.now(ET).isoformat(),
        })
        self.last_trade = f"{side} {symbol} {'+'if pnl>=0 else ''}${pnl:.2f}"
        self.trades     = self.trades[-50:]

    def to_dict(self) -> dict:
        return {
            "name":           self.name,
            "capital":        self.capital,
            "daily_target":   self.daily_target,
            "loss_limit":     self.loss_limit,
            "realized_pnl":   round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_pnl":      self.total_pnl,
            "trade_count":    self.trade_count,
            "win_count":      self.win_count,
            "win_rate":       self.win_rate,
            "progress_pct":   self.progress_pct,
            "is_target_hit":  self.is_target_hit,
            "is_loss_limit":  self.is_loss_limit_hit,
            "status":         self.status,
            "stop_reason":    self.stop_reason,
            "last_trade":     self.last_trade,
            "recent_trades":  list(reversed(self.trades[-5:])),
        }


class DualEngineManager:
    def __init__(self):
        self.allocator:    Optional[CapitalAllocator] = None
        self.scalper:      Optional[EngineStats]      = None
        self.bounce:       Optional[EngineStats]      = None
        self.bounce_engine: Optional[PeakBounceEngine] = None

        self._running      = False
        self._today        = str(date.today())
        self._pnl_history: list = []   # [{time, scalper, bounce, total}]

    # ── Initialization ────────────────────────────────────────────────────────

    def initialize(
        self,
        total_capital: float,
        daily_goal:    float,
        market_regime: str   = "unknown",
        sentiment:     float = 0.0,
        scalper_stats: dict  = None,
        bounce_stats:  dict  = None,
    ):
        self.allocator = CapitalAllocator(total_capital, daily_goal)

        # AI computes the split
        split = self.allocator.compute_split(
            scalper_stats        = scalper_stats or {},
            bounce_stats         = bounce_stats  or {},
            market_regime        = market_regime,
            sentiment_score      = sentiment,
        )

        s = split["scalper"]
        b = split["bounce"]

        self.scalper = EngineStats(
            name         = "AI Scalper",
            capital      = s["capital"],
            daily_target = s["daily_target"],
            loss_limit   = s["loss_limit"],
        )
        self.bounce = EngineStats(
            name         = "Peak Bounce",
            capital      = b["capital"],
            daily_target = b["daily_target"],
            loss_limit   = b["loss_limit"],
        )
        self.bounce_engine = PeakBounceEngine(b["capital"], b["daily_target"])

        logger.info(
            f"Dual Engine initialized | "
            f"Scalper: ${s['capital']} ({s['pct']}%) | "
            f"Bounce: ${b['capital']} ({b['pct']}%)"
        )
        return split

    # ── Control ───────────────────────────────────────────────────────────────

    def start_both(self):
        if not self.scalper or not self.bounce:
            raise ValueError("Initialize engines first")
        self.scalper.status = "running"
        self.bounce.status  = "running"
        self.scalper.started_at = datetime.now(ET).isoformat()
        self.bounce.started_at  = datetime.now(ET).isoformat()
        self._running = True
        logger.info("Both engines started")

    def pause_engine(self, engine: str):
        target = self.scalper if engine == "scalper" else self.bounce
        if target:
            target.status = "paused"
            logger.info(f"{engine} paused")

    def resume_engine(self, engine: str):
        target = self.scalper if engine == "scalper" else self.bounce
        if target and target.status == "paused":
            target.status = "running"
            logger.info(f"{engine} resumed")

    def stop_engine(self, engine: str, reason: str = "manual"):
        target = self.scalper if engine == "scalper" else self.bounce
        if target:
            target.status      = "stopped"
            target.stop_reason = reason
            logger.info(f"{engine} stopped: {reason}")

    def stop_both(self, reason: str = "manual"):
        self.stop_engine("scalper", reason)
        self.stop_engine("bounce",  reason)
        self._running = False

    # ── P&L recording ─────────────────────────────────────────────────────────

    def record_scalper_trade(self, symbol: str, pnl: float, side: str):
        if not self.scalper:
            return
        self.scalper.record_trade(symbol, pnl, side)
        self._check_limits("scalper")
        self._snapshot_pnl()

    def record_bounce_trade(self, symbol: str, pnl: float, side: str = "BUY"):
        if not self.bounce:
            return
        self.bounce.record_trade(symbol, pnl, side)
        self._check_limits("bounce")
        self._snapshot_pnl()

    def update_unrealized(self, scalper_unrealized: float, bounce_unrealized: float):
        if self.scalper:
            self.scalper.unrealized_pnl = scalper_unrealized
        if self.bounce:
            self.bounce.unrealized_pnl  = bounce_unrealized

    def _check_limits(self, engine: str):
        target = self.scalper if engine == "scalper" else self.bounce
        if not target:
            return

        if target.is_target_hit:
            self.stop_engine(engine, f"Daily target hit (+${target.realized_pnl:.2f})")

        if target.is_loss_limit_hit:
            self.stop_engine(engine, f"Loss limit hit (${target.realized_pnl:.2f})")

        # Check combined goal
        combined = (self.scalper.realized_pnl if self.scalper else 0) + \
                   (self.bounce.realized_pnl  if self.bounce  else 0)
        if self.allocator and combined >= self.allocator.daily_goal:
            self.stop_both(f"Combined daily goal hit (+${combined:.2f})")

    def _snapshot_pnl(self):
        self._pnl_history.append({
            "time":    datetime.now(ET).isoformat(),
            "scalper": self.scalper.realized_pnl if self.scalper else 0,
            "bounce":  self.bounce.realized_pnl  if self.bounce  else 0,
            "total":   (self.scalper.realized_pnl if self.scalper else 0) +
                       (self.bounce.realized_pnl  if self.bounce  else 0),
        })
        self._pnl_history = self._pnl_history[-200:]

    # ── Re-split ──────────────────────────────────────────────────────────────

    def recompute_split(self, **kwargs) -> dict:
        """Re-ask AI for optimal split mid-day."""
        if not self.allocator:
            return {}
        was_running_s = self.scalper.status == "running" if self.scalper else False
        was_running_b = self.bounce.status  == "running" if self.bounce  else False

        split = self.allocator.compute_split(
            scalper_stats = self.scalper.to_dict() if self.scalper else {},
            bounce_stats  = {"success_rate": 0.6,
                             "total_captured": self.bounce.realized_pnl if self.bounce else 0},
            **kwargs,
        )
        # Update capital for each engine going forward
        if self.scalper:
            self.scalper.capital      = split["scalper"]["capital"]
            self.scalper.daily_target = split["scalper"]["daily_target"]
            self.scalper.loss_limit   = split["scalper"]["loss_limit"]
        if self.bounce:
            self.bounce.capital       = split["bounce"]["capital"]
            self.bounce.daily_target  = split["bounce"]["daily_target"]
            self.bounce.loss_limit    = split["bounce"]["loss_limit"]

        return split

    # ── Summary ───────────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        scalper_pnl = self.scalper.realized_pnl if self.scalper else 0
        bounce_pnl  = self.bounce.realized_pnl  if self.bounce  else 0
        total_pnl   = scalper_pnl + bounce_pnl
        total_goal  = self.allocator.daily_goal if self.allocator else 250

        return {
            "initialized":    self.allocator is not None,
            "total_capital":  self.allocator.total_capital if self.allocator else 0,
            "total_pnl":      round(total_pnl, 2),
            "total_goal":     total_goal,
            "progress_pct":   round(min(total_pnl / total_goal * 100, 100), 1) if total_goal else 0,
            "both_stopped":   not self._running,
            "scalper":        self.scalper.to_dict() if self.scalper else None,
            "bounce":         self.bounce.to_dict()  if self.bounce  else None,
            "split":          self.allocator.get_current_split() if self.allocator else {},
            "pnl_history":    self._pnl_history[-50:],
        }

    def is_engine_active(self, engine: str) -> bool:
        target = self.scalper if engine == "scalper" else self.bounce
        return target is not None and target.status == "running"
