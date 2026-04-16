"""
Morviq AI — Hybrid Trading Engine

Manages simultaneous stock + crypto trading.
AI decides capital split based on:
- Current market regime
- Time of day (crypto 24/7, stocks only during hours)
- User's daily P&L progress
- PDT remaining trades
- Momentum in each asset class

Modes:
  stocks_only  - only stock engine (default for stock-hours)
  crypto_only  - only crypto engine (overnight / PDT limited)
  hybrid       - both engines running with AI-determined split

Capital allocation:
  min_crypto_pct: 0.10  (10% floor)
  max_crypto_pct: 0.60  (60% ceiling)
  AI adjusts within this range based on signals
"""
import asyncio
import logging
from datetime   import datetime, timezone
from typing     import Optional

import pytz

from strategy.crypto_engine import CryptoEngine, EngineState as CryptoState

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


class HybridEngine:

    def __init__(
        self,
        broker,
        settings,        # SettingsManager instance
        tracker,         # DailyTargetTracker instance
        stock_engine,    # existing StrategyEngine
        mode: str = "hybrid",   # stocks_only | crypto_only | hybrid
        crypto_alloc_pct: float = 0.30,
        user_id: int = None,
        ensemble = None,  # EnsembleModel — shared ML layer for crypto+stocks
    ):
        self.broker        = broker
        self.user_id       = user_id  # per-user trade ownership
        self.settings      = settings
        self.tracker       = tracker
        self.stock_engine  = stock_engine
        self.mode          = mode
        self.crypto_alloc  = crypto_alloc_pct
        self.ensemble      = ensemble  # passed to crypto engine for ML scoring

        self.crypto_engine: Optional[CryptoEngine] = None
        self._running      = False
        self.ai_split_log  = []

        # After-hours crypto allocation (user-configurable, default 80%)
        try:
            self.after_hours_crypto_alloc = float(
                settings.get_after_hours_crypto_alloc()
                if hasattr(settings, 'get_after_hours_crypto_alloc') else 0.80
            )
        except Exception:
            self.after_hours_crypto_alloc = 0.80

        # Smart capital planner
        try:
            from strategy.capital_planner import CapitalPlanner
            self.planner = CapitalPlanner(settings, broker, crypto_alloc_pct)
        except Exception as e:
            self.planner = None
            logger.warning(f"CapitalPlanner unavailable: {e}")

    def _get_targets(self) -> dict:
        t = self.settings.get_targets()
        return {
            "min":     t["daily_target_min"],
            "desired": (t["daily_target_min"] + t["daily_target_max"]) / 2,
            "stretch": t["daily_target_max"],
            "loss":    t["max_daily_loss"],
        }

    def _is_stock_hours(self) -> bool:
        now = datetime.now(ET)
        h   = now.hour + now.minute / 60
        return 9.583 <= h <= 15.5  # 9:35 AM – 3:30 PM ET

    def _is_market_day(self) -> bool:
        """True if today is a trading day — weekday + not a US market holiday."""
        now = datetime.now(ET)
        if now.weekday() >= 5:
            return False
        try:
            from alpaca.trading.requests import GetCalendarRequest
            today_str = now.strftime("%Y-%m-%d")
            req = GetCalendarRequest(start=today_str, end=today_str)
            cal = self.broker.trading.get_calendar(req)
            return len(cal) > 0
        except Exception:
            return True  # fallback: trust weekday check

    def _time_to_close_min(self) -> float:
        now   = datetime.now(ET)
        close = now.replace(hour=15, minute=30, second=0)
        return max(0, (close - now).total_seconds() / 60)

    def ai_decide_split(self, account: dict) -> dict:
        """
        Smart allocation:
        - Market hours on trading day → user's configured split (e.g. 30/70)
        - After hours / weekend / holiday → expanded crypto (e.g. 80-100%)
        - Auto-resets before market open on next trading day
        """
        targets        = self._get_targets()
        realized       = self.tracker.realized_pnl if self.tracker else 0
        pnl_progress   = realized / targets.get("min", 150) if targets.get("min", 0) > 0 else 0
        pdt_remaining  = account.get("day_trades_remaining", 3)
        pdt_exempt     = account.get("is_pdt_exempt", False)
        is_hours       = self._is_stock_hours()
        is_trading_day = self._is_market_day()
        mins_to_close  = self._time_to_close_min()

        try:
            configured_capital = self.settings.get_capital()
        except Exception:
            configured_capital = 5000

        user_crypto_pct = self.crypto_alloc              # market hours % (e.g. 0.30)
        ah_crypto_pct   = self.after_hours_crypto_alloc  # after hours % (e.g. 0.80)

        reason = []

        if is_hours and is_trading_day:
            # Market hours on a trading day — respect configured split
            effective_crypto_pct = user_crypto_pct
            reason.append(f"Market hours — {user_crypto_pct:.0%} crypto / {1-user_crypto_pct:.0%} stocks")
            if pdt_remaining <= 1 and not pdt_exempt:
                reason.append(f"PDT limit ({pdt_remaining} left)")
            if mins_to_close < 30:
                reason.append(f"{mins_to_close:.0f}m to close")
            if pnl_progress >= 1.0:
                reason.append("Target hit — protecting gains")
        else:
            # After hours / weekend / holiday — expand crypto budget
            effective_crypto_pct = ah_crypto_pct
            now = datetime.now(ET)
            if now.weekday() >= 5:
                reason.append(f"Weekend — crypto at {ah_crypto_pct:.0%} (24/7)")
            elif not is_trading_day:
                reason.append(f"Market holiday — crypto at {ah_crypto_pct:.0%} (24/7)")
            else:
                reason.append(f"After hours — crypto expanded {user_crypto_pct:.0%} → {ah_crypto_pct:.0%}")
            reason.append("Stocks idle — full crypto budget active")

        effective_crypto_pct = round(min(1.0, max(0.0, effective_crypto_pct)), 2)
        crypto_budget = round(configured_capital * effective_crypto_pct, 2)
        stock_budget  = round(configured_capital * (1 - user_crypto_pct), 2)

        logger.info(
            f"Budget: crypto=${crypto_budget} ({effective_crypto_pct:.0%}) "
            f"stocks=${stock_budget if is_hours else 0} — "
            f"{'; '.join(reason)}"
        )

        decision = {
            "crypto_pct":          effective_crypto_pct,
            "stock_pct":           round(1 - user_crypto_pct, 2),
            "crypto_capital":      crypto_budget,
            "stock_capital":       stock_budget,
            "market_hours_alloc":  user_crypto_pct,
            "after_hours_alloc":   ah_crypto_pct,
            "reason":              "; ".join(reason),
            "pdt_remaining":       pdt_remaining,
            "pdt_exempt":          pdt_exempt,
            "market_hours":        is_hours,
            "is_trading_day":      is_trading_day,
            "decided_at":          datetime.now(timezone.utc).isoformat(),
        }
        self.ai_split_log.append(decision)
        if len(self.ai_split_log) > 50:
            self.ai_split_log = self.ai_split_log[-50:]
        return decision

    def init_crypto_engine(self, account: dict, split: dict) -> CryptoEngine:
        """Create/update crypto engine with fresh account state."""
        targets = self._get_targets()
        # Use configured capital from settings, NOT Alpaca's full paper equity
        configured_capital = self.settings.get_capital() if hasattr(self.settings, 'get_capital') else 5000
        engine  = CryptoEngine(
            broker            = self.broker,
            target_min        = targets["min"],
            target_desired    = targets["desired"],
            target_stretch    = targets["stretch"],
            max_daily_loss    = targets["loss"],
            capital           = configured_capital,
            crypto_alloc      = split["crypto_pct"],
            min_scalp_profit  = 5,
            compound_mode     = True,
            min_probability   = 0.55,
            max_positions     = 2,
            user_id           = self.user_id,
            ensemble          = self.ensemble,
        )
        # Apply user-configured milestones
        try:
            milestones = self.settings.get_profit_milestones()
            engine.set_milestones(milestones)
            logger.info(f"Milestones loaded: {[m['threshold'] for m in milestones]}")
        except Exception as e:
            logger.warning(f"Milestone load: {e}")
        return engine

    async def run_cycle(self) -> dict:
        """One hybrid engine cycle."""
        try:
            acct      = self.broker.get_account()
            split     = self.ai_decide_split(acct)
            is_hours  = self._is_stock_hours()
            dtbp      = float(acct.get("daytrading_buying_power", 0))
            has_open_crypto = (
                self.crypto_engine is not None and
                len(getattr(self.crypto_engine, "open_positions", {})) > 0
            )

            results = {
                "mode":     self.mode,
                "split":    split,
                "crypto":   None,
                "stocks":   None,
            }

            # During market hours: if crypto is holding positions and dtbp=0,
            # pause new crypto entries to free cash for stocks
            crypto_paused = False
            if is_hours and dtbp == 0 and has_open_crypto:
                logger.info(
                    "⏸  Market hours + dtbp=$0 — crypto holding positions. "
                    "Monitoring exits only (no new crypto entries until cash frees)"
                )
                crypto_paused = True

            # Run crypto engine
            if self.mode in ("crypto_only", "hybrid"):
                if self.crypto_engine is None or self.crypto_engine.state == CryptoState.STOPPED:
                    if not (is_hours and crypto_paused):
                        self.crypto_engine = self.init_crypto_engine(acct, split)
                        # Apply planner's crypto budget
                        if self.planner and self.crypto_engine:
                            plan = self.planner.get_or_create_plan()
                            self.crypto_engine.allocated_capital = plan.crypto_budget
                            logger.info(
                                f"📋 Plan: crypto=${plan.crypto_budget} "
                                f"stocks=${plan.stock_budget} | "
                                f"target=${plan.daily_target_min}–${plan.daily_target_max} | "
                                f"per-trade crypto=${plan.crypto_per_trade} stocks=${plan.stock_per_trade}"
                            )
                else:
                    configured    = self.settings.get_capital() if hasattr(self.settings, 'get_capital') else 5000
                    crypto_budget = round(configured * self.crypto_alloc, 2)
                    self.crypto_engine.allocated_capital = crypto_budget
                    self.crypto_engine.capital           = configured
                    self.crypto_engine.crypto_alloc      = self.crypto_alloc
                    self.crypto_engine.compounded_gains  = max(0, self.crypto_engine.compounded_gains)

                    if crypto_paused:
                        # Only manage exits — don't scan for new entries
                        await self.crypto_engine._manage_positions()
                        results["crypto"] = self.crypto_engine.status()
                    else:
                        results["crypto"] = await self.crypto_engine.run_cycle()

            return results

        except Exception as e:
            logger.error(f"HybridEngine.run_cycle: {e}")
            return {"mode": self.mode, "error": str(e)}

    def get_status(self) -> dict:
        crypto_status = self.crypto_engine.status() if self.crypto_engine else None
        plan_summary  = self.planner.get_api_summary() if self.planner else None
        return {
            "mode":          self.mode,
            "crypto_alloc":  self.crypto_alloc,
            "is_stock_hours":self._is_stock_hours(),
            "mins_to_close": round(self._time_to_close_min(), 1),
            "crypto":        crypto_status,
            "ai_split_log":  self.ai_split_log[-5:],
            "day_plan":      plan_summary,
        }

    def set_mode(self, mode: str):
        assert mode in ("stocks_only", "crypto_only", "hybrid")
        self.mode = mode
        logger.info(f"HybridEngine mode set to: {mode}")

    def reset_crypto(self):
        """Reset crypto engine for new day."""
        self.crypto_engine = None
        logger.info("Crypto engine reset")