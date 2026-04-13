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
    ):
        self.broker        = broker
        self.settings      = settings
        self.tracker       = tracker
        self.stock_engine  = stock_engine
        self.mode          = mode
        self.crypto_alloc  = crypto_alloc_pct

        self.crypto_engine: Optional[CryptoEngine] = None
        self._running      = False
        self.ai_split_log  = []   # history of AI split decisions

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

    def _time_to_close_min(self) -> float:
        now   = datetime.now(ET)
        close = now.replace(hour=15, minute=30, second=0)
        return max(0, (close - now).total_seconds() / 60)

    def ai_decide_split(self, account: dict) -> dict:
        """
        AI decisions respect user's configured allocation — never override it.
        User sets max crypto% (e.g. 30%). AI only adjusts reason/label.
        """
        targets       = self._get_targets()
        realized      = self.tracker.realized_pnl if self.tracker else 0
        pnl_progress  = realized / targets["min"] if targets["min"] > 0 else 0
        pdt_remaining = account.get("day_trades_remaining", 3)
        pdt_exempt    = account.get("is_pdt_exempt", False)
        is_hours      = self._is_stock_hours()
        mins_to_close = self._time_to_close_min()

        # ALWAYS use user's configured allocation — never the Alpaca equity
        configured_capital = self.settings.get_capital() if hasattr(self.settings, 'get_capital') else 5000
        user_crypto_pct    = self.crypto_alloc            # e.g. 0.30 = user set 30%
        crypto_budget      = round(configured_capital * user_crypto_pct, 2)
        stock_budget       = round(configured_capital * (1 - user_crypto_pct), 2)

        reason = []
        if not is_hours:
            reason.append("Market closed — crypto active 24/7")
        else:
            if not pdt_exempt and pdt_remaining <= 1:
                reason.append(f"PDT limit ({pdt_remaining} left)")
            if mins_to_close < 30:
                reason.append(f"{mins_to_close:.0f}m to close")
            if pnl_progress < 0.3:
                reason.append("Behind target")
            elif pnl_progress >= 1.0:
                reason.append("Target hit — protecting gains")

        logger.info(
            f"Budget: crypto=${crypto_budget} ({user_crypto_pct:.0%}) "
            f"stocks=${stock_budget} ({1-user_crypto_pct:.0%}) — "
            f"{'; '.join(reason) or 'Base allocation'}"
        )

        decision = {
            "crypto_pct":     round(user_crypto_pct, 2),
            "stock_pct":      round(1 - user_crypto_pct, 2),
            "crypto_capital": crypto_budget,
            "stock_capital":  stock_budget,
            "reason":         "; ".join(reason) or "Base allocation",
            "pdt_remaining":  pdt_remaining,
            "pdt_exempt":     pdt_exempt,
            "market_hours":   is_hours,
            "decided_at":     datetime.now(timezone.utc).isoformat(),
        }
        self.ai_split_log.append(decision)
        if len(self.ai_split_log) > 50:
            self.ai_split_log = self.ai_split_log[-50:]

        logger.info(f"AI split: crypto={user_crypto_pct:.0%} stocks={1-user_crypto_pct:.0%} — {decision['reason']}")
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
            min_scalp_profit  = 5,    # $5 min per scalp — realistic for small budget
            compound_mode     = True,
            min_probability   = 0.40, # lowered threshold — matches crypto_engine default
            max_positions     = 2,
        )
        return engine

    async def run_cycle(self) -> dict:
        """One hybrid engine cycle."""
        try:
            # Get live account
            acct  = self.broker.get_account()
            split = self.ai_decide_split(acct)

            results = {
                "mode":     self.mode,
                "split":    split,
                "crypto":   None,
                "stocks":   None,
            }

            # Crypto engine
            if self.mode in ("crypto_only", "hybrid"):
                if self.crypto_engine is None or self.crypto_engine.state == CryptoState.STOPPED:
                    self.crypto_engine = self.init_crypto_engine(acct, split)
                else:
                    # Always use USER's configured budget — never the dynamic AI split %
                    configured   = self.settings.get_capital() if hasattr(self.settings, 'get_capital') else 5000
                    crypto_budget = round(configured * self.crypto_alloc, 2)
                    self.crypto_engine.allocated_capital = crypto_budget
                    self.crypto_engine.capital           = configured
                    self.crypto_engine.crypto_alloc      = self.crypto_alloc
                    self.crypto_engine.compounded_gains  = max(0, self.crypto_engine.compounded_gains)

                results["crypto"] = await self.crypto_engine.run_cycle()

            return results

        except Exception as e:
            logger.error(f"HybridEngine.run_cycle: {e}")
            return {"mode": self.mode, "error": str(e)}

    def get_status(self) -> dict:
        crypto_status = self.crypto_engine.status() if self.crypto_engine else None
        return {
            "mode":          self.mode,
            "crypto_alloc":  self.crypto_alloc,
            "is_stock_hours":self._is_stock_hours(),
            "mins_to_close": round(self._time_to_close_min(), 1),
            "crypto":        crypto_status,
            "ai_split_log":  self.ai_split_log[-5:],
        }

    def set_mode(self, mode: str):
        assert mode in ("stocks_only", "crypto_only", "hybrid")
        self.mode = mode
        logger.info(f"HybridEngine mode set to: {mode}")

    def reset_crypto(self):
        """Reset crypto engine for new day."""
        self.crypto_engine = None
        logger.info("Crypto engine reset")