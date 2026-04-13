"""
Morviq AI — Smart Capital Planner

Implements goal-based capital allocation:
1. Read daily target ($150 min → $278 max)
2. Check what cash is ACTUALLY available (settled)
3. Plan how many trades needed to hit target
4. Allocate per-trade size to reach target without burning all capital
5. Set profit ceiling + hard stop to protect gains

Settlement Rules (Alpaca):
  Crypto: INSTANT — sell today, buy again immediately
  Stocks: T+1    — sell today, cash available TOMORROW
  → Crypto can recycle capital all day
  → Stocks: once deployed, that cash is locked until next day
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


@dataclass
class TradePlan:
    """One trade plan: how much to risk and what to expect."""
    asset_type:     str     # "crypto" | "stock"
    symbol:         str
    direction:      str     # "BUY" | "SELL"
    entry:          float
    target:         float
    stop:           float
    position_size:  float   # dollar amount to deploy
    qty:            float   # units
    expected_profit: float
    expected_loss:  float
    risk_reward:    float
    confidence:     float
    reasoning:      str


@dataclass
class DayPlan:
    """Full day capital plan."""
    date:                str
    daily_target_min:    float
    daily_target_max:    float
    hard_stop_loss:      float      # max we can lose today

    # What we actually have
    total_settled_cash:  float      # money we can spend RIGHT NOW
    crypto_budget:       float      # portion for crypto
    stock_budget:        float      # portion for stocks

    # Per-trade sizing
    crypto_per_trade:    float      # how much per crypto scalp
    stock_per_trade:     float      # how much per stock trade
    max_crypto_trades:   int        # trades to hit target
    max_stock_trades:    int        # trades to hit target (limited by T+1)

    # Guard rails
    profit_floor:        float      # once we hit this, protect it
    profit_ceiling:      float      # stop new trades above this
    current_pnl:         float = 0.0
    trades_taken:        int = 0

    # State
    crypto_deployed:     float = 0.0
    stock_deployed:      float = 0.0

    def remaining_crypto_budget(self) -> float:
        return max(0, self.crypto_budget - self.crypto_deployed)

    def remaining_stock_budget(self) -> float:
        return max(0, self.stock_budget - self.stock_deployed)

    def should_stop_trading(self) -> tuple:
        """Returns (should_stop, reason)."""
        # Hard stop: too much loss
        if self.current_pnl <= -self.hard_stop_loss:
            return True, f"Hard stop: lost ${abs(self.current_pnl):.2f} of ${self.hard_stop_loss:.2f} limit"

        # Profit ceiling: riding profit, set new floor
        if self.current_pnl >= self.profit_ceiling:
            return True, f"Profit ceiling hit: +${self.current_pnl:.2f} ≥ ${self.profit_ceiling:.2f} max"

        return False, ""

    def profit_floor_triggered(self) -> bool:
        """True if we built up profit then fell back below floor."""
        return (self.profit_floor > 0 and
                self.current_pnl > 0 and
                self.current_pnl < self.profit_floor)

    def summary(self) -> dict:
        return {
            "date":                self.date,
            "target_min":          self.daily_target_min,
            "target_max":          self.daily_target_max,
            "hard_stop":           self.hard_stop_loss,
            "total_settled_cash":  self.total_settled_cash,
            "crypto_budget":       self.crypto_budget,
            "stock_budget":        self.stock_budget,
            "crypto_per_trade":    self.crypto_per_trade,
            "stock_per_trade":     self.stock_per_trade,
            "max_crypto_trades":   self.max_crypto_trades,
            "max_stock_trades":    self.max_stock_trades,
            "profit_floor":        self.profit_floor,
            "profit_ceiling":      self.profit_ceiling,
            "current_pnl":         round(self.current_pnl, 2),
            "trades_taken":        self.trades_taken,
            "crypto_deployed":     round(self.crypto_deployed, 2),
            "stock_deployed":      round(self.stock_deployed, 2),
            "remaining_crypto":    round(self.remaining_crypto_budget(), 2),
            "remaining_stock":     round(self.remaining_stock_budget(), 2),
            "pct_to_target":       round(self.current_pnl / self.daily_target_min * 100, 1) if self.daily_target_min > 0 else 0,
        }


class CapitalPlanner:
    """
    Smart capital planner that works backward from the daily target.

    Strategy:
    1. Know your target ($150 min)
    2. Know what's settled and available RIGHT NOW
    3. Crypto: can recycle capital all day (instant settlement)
       → Use smaller per-trade size, more trades
    4. Stocks: capital locked until tomorrow after sell
       → Use calculated size to hit target in fewer trades
    5. Once target hit: set floor, reduce trade size, protect gains
    6. Hard stop if loss exceeds threshold
    """

    def __init__(
        self,
        settings,           # SettingsManager
        broker,             # AlpacaClient
        crypto_alloc: float = 0.30,  # % of capital for crypto
    ):
        self.settings      = settings
        self.broker        = broker
        self.crypto_alloc  = crypto_alloc
        self._plan: Optional[DayPlan] = None
        self._plan_date    = ""

    def get_or_create_plan(self) -> DayPlan:
        """Get today's plan, creating if needed."""
        today = str(datetime.now(ET).date())
        if self._plan and self._plan_date == today:
            return self._plan
        self._plan      = self._build_plan()
        self._plan_date = today
        return self._plan

    def _build_plan(self) -> DayPlan:
        """Build today's capital plan from scratch."""
        today = str(datetime.now(ET).date())

        # 1. Get targets from settings
        try:
            t = self.settings.get_targets()
            target_min = float(t.get("daily_target_min", 150))
            target_max = float(t.get("daily_target_max", 278))
            hard_stop  = float(t.get("max_daily_loss", 50))
            capital    = float(self.settings.get_capital())
        except Exception:
            target_min, target_max, hard_stop, capital = 150, 278, 50, 5000

        # 2. Get ACTUAL settled cash from Alpaca
        try:
            acct = self.broker.get_account()
            # non_marginable_buying_power = settled cash available NOW
            nmbp  = float(acct.get("non_marginable_buying_power", capital))
            dtbp  = float(acct.get("daytrading_buying_power", 0))
            cash  = float(acct.get("cash", capital))
        except Exception:
            nmbp, dtbp, cash = capital, 0, capital

        # Settled cash = what we can actually spend
        # For day trading stocks: use dtbp (includes intraday margin)
        # For crypto: use nmbp (settled cash only — no margin for crypto)
        settled_for_crypto = min(nmbp, capital * self.crypto_alloc)
        settled_for_stocks = min(
            dtbp if dtbp > 100 else nmbp,
            capital * (1 - self.crypto_alloc)
        )
        total_settled = settled_for_crypto + settled_for_stocks

        # 3. Calculate per-trade sizes
        # ── CRYPTO: instant settlement, can recycle ──────────────────────
        # Target avg win per crypto scalp = 0.5% of position
        # How many scalps needed? target_min / avg_win_per_scalp
        # Keep each trade small so we have capital for multiple attempts
        avg_crypto_win_pct = 0.004   # 0.4% average win (conservative)
        crypto_per_trade   = min(
            settled_for_crypto * 0.40,      # 40% of crypto budget per trade
            target_min / avg_crypto_win_pct / 4  # size to hit target in ~4 scalps
        )
        crypto_per_trade = max(50, round(crypto_per_trade, 2))

        # How many crypto trades can we do? (budget / per_trade, can recycle)
        # Crypto can recycle so theoretical max is high, cap at 20
        max_crypto_trades = min(20, int(settled_for_crypto / crypto_per_trade * 3))

        # ── STOCKS: T+1 settlement, capital locked after trade ───────────
        # Much more careful — once deployed, can't reuse today
        # Need to hit target in 2-3 stock trades MAX
        avg_stock_win_pct  = 0.015   # 1.5% average win on stock scalps
        stock_per_trade    = min(
            settled_for_stocks * 0.35,      # 35% of stock budget per trade
            target_min / avg_stock_win_pct / 2  # size to hit target in ~2 trades
        )
        stock_per_trade = max(200, round(stock_per_trade, 2))

        # Stock trades are limited — capital doesn't recycle
        max_stock_trades = max(1, int(settled_for_stocks / stock_per_trade))

        # 4. Profit floors and ceilings
        profit_floor   = round(target_min * 0.97, 2)  # 97% of min target
        profit_ceiling = round(target_max * 1.10, 2)  # 10% above max target

        plan = DayPlan(
            date             = today,
            daily_target_min = target_min,
            daily_target_max = target_max,
            hard_stop_loss   = hard_stop,
            total_settled_cash = round(total_settled, 2),
            crypto_budget    = round(settled_for_crypto, 2),
            stock_budget     = round(settled_for_stocks, 2),
            crypto_per_trade = round(crypto_per_trade, 2),
            stock_per_trade  = round(stock_per_trade, 2),
            max_crypto_trades = max_crypto_trades,
            max_stock_trades  = max_stock_trades,
            profit_floor     = profit_floor,
            profit_ceiling   = profit_ceiling,
        )

        logger.info(
            f"\n{'='*60}\n"
            f"📋 DAY PLAN — {today}\n"
            f"  Target: ${target_min}–${target_max} | Stop: -${hard_stop}\n"
            f"  Settled cash: ${total_settled:.0f}\n"
            f"    Crypto: ${settled_for_crypto:.0f} (instant settlement)\n"
            f"    Stocks: ${settled_for_stocks:.0f} (T+1 — locked after sell)\n"
            f"  Per trade:\n"
            f"    Crypto: ${crypto_per_trade:.0f} × {max_crypto_trades} scalps max\n"
            f"    Stocks: ${stock_per_trade:.0f} × {max_stock_trades} trades max\n"
            f"  Guards: floor=${profit_floor} | ceiling=${profit_ceiling}\n"
            f"{'='*60}"
        )

        return plan

    def get_crypto_position_size(self, current_pnl: float) -> float:
        """
        Return how much to deploy on next crypto trade.
        Reduces size as we approach target (protect gains).
        """
        plan = self.get_or_create_plan()
        plan.current_pnl = current_pnl

        remaining_to_target = plan.daily_target_min - current_pnl
        base_size = plan.crypto_per_trade

        if current_pnl >= plan.daily_target_min:
            # Hit target — use 25% of normal size (just maintaining, not chasing)
            return round(base_size * 0.25, 2)
        elif current_pnl >= plan.daily_target_min * 0.8:
            # 80% there — tighten up, use 60% size
            return round(base_size * 0.60, 2)
        elif current_pnl < 0:
            # In the red — be more conservative, use 75% size
            return round(base_size * 0.75, 2)

        return round(min(base_size, plan.remaining_crypto_budget()), 2)

    def get_stock_position_size(self, current_pnl: float) -> float:
        """
        Return how much to deploy on next stock trade.
        Very conservative — T+1 means we can't get this money back today.
        """
        plan = self.get_or_create_plan()
        plan.current_pnl = current_pnl

        if plan.stock_deployed >= plan.stock_budget * 0.95:
            return 0  # Already deployed all stock budget

        remaining_to_target = max(0, plan.daily_target_min - current_pnl)
        base_size = plan.stock_per_trade

        if current_pnl >= plan.daily_target_min:
            # Target hit — don't deploy more stock capital today
            return 0
        elif current_pnl >= plan.daily_target_min * 0.7:
            # Close to target — smaller stock trade
            return round(base_size * 0.5, 2)

        return round(min(base_size, plan.remaining_stock_budget()), 2)

    def record_trade_opened(self, asset_type: str, size: float):
        plan = self.get_or_create_plan()
        if asset_type == "crypto":
            plan.crypto_deployed += size
        else:
            plan.stock_deployed += size
        plan.trades_taken += 1

    def record_trade_closed(self, asset_type: str, size: float, pnl: float):
        plan = self.get_or_create_plan()
        plan.current_pnl += pnl
        if asset_type == "crypto":
            # Crypto: capital returns immediately
            plan.crypto_deployed = max(0, plan.crypto_deployed - size)
        # Stocks: capital does NOT return (T+1 settlement)

    def get_api_summary(self) -> dict:
        """For dashboard API."""
        plan = self.get_or_create_plan()
        stop, stop_reason = plan.should_stop_trading()
        return {
            **plan.summary(),
            "should_stop":   stop,
            "stop_reason":   stop_reason,
            "floor_triggered": plan.profit_floor_triggered(),
        }
