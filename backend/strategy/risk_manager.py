"""
Dynamic risk manager — sizes every position using ATR volatility, ensemble
confidence, current P&L vs daily target, and a hard daily-loss kill-switch.
No fixed percentages: the AI adapts stake size to market conditions.
"""
import logging

import config

logger = logging.getLogger(__name__)


class DynamicRiskManager:
    def __init__(self):
        self.capital         = config.CAPITAL
        self.max_pos_pct     = config.MAX_POSITION_PCT
        self.daily_loss_lim  = config.MAX_DAILY_LOSS
        self.atr_stop_mult   = config.ATR_STOP_MULTIPLIER
        self.atr_target_mult = config.ATR_TARGET_MULTIPLIER

    # ── Position sizing ───────────────────────────────────────────────────────

    def size_position(
        self,
        symbol: str,
        price: float,
        atr: float,
        confidence: float,
        current_pnl: float,
        target_min: float,
        target_max: float,
        open_positions: int = 0,
    ) -> dict:
        """
        Returns qty, stop_loss, take_profit, risk_pct.
        Returns qty=0 when risk conditions block the trade.
        """
        # ── Kill-switch: daily loss exceeded ─────────────────────────────────
        if current_pnl <= -self.daily_loss_lim:
            return self._block("Daily loss limit reached", price, atr)

        # ── Kill-switch: max target already hit ──────────────────────────────
        if current_pnl >= target_max:
            return self._block("Daily max-target already hit", price, atr)

        # ── Too many open positions ───────────────────────────────────────────
        if open_positions >= config.MAX_OPEN_POSITIONS:
            return self._block(f"Max {config.MAX_OPEN_POSITIONS} open positions reached", price, atr)

        # ── Dynamic base risk: 0.8 % – 1.8 % of capital per trade ────────────
        #   • More confident  → bigger stake
        #   • Closer to target → reduce risk (protect gains)
        progress = current_pnl / target_min if target_min > 0 else 0
        conf_mult = 0.5 + confidence          # 0.55 conf → 1.05×  |  0.9 conf → 1.4×
        prot_mult = max(0.4, 1.0 - progress * 0.6)  # shrinks toward 0.4 as we approach target

        base_risk_pct = 0.010                 # 1 % base
        risk_pct      = base_risk_pct * conf_mult * prot_mult
        risk_dollars  = self.capital * risk_pct

        # ── ATR-based stop distance ───────────────────────────────────────────
        if atr > 0:
            stop_dist = atr * self.atr_stop_mult
        else:
            stop_dist = price * 0.012         # fallback: 1.2 %

        # Shares = risk_dollars / stop_distance
        raw_shares = risk_dollars / stop_dist

        # Cap at max position size
        max_value  = self.capital * self.max_pos_pct
        max_shares = max_value / price

        # Also cap by actual available buying power from broker
        try:
            from scheduler.bot_loop import bot_loop
            if bot_loop.broker:
                acct = bot_loop.broker.get_account()
                dtbp = float(acct.get("daytrading_buying_power", 0) or 0)
                nmbp = float(acct.get("non_marginable_buying_power", 0) or 0)
                avail = dtbp if dtbp > 100 else nmbp
                avail = min(avail, self.capital)  # never exceed configured capital
                if avail > 10:
                    bp_shares = (avail * 0.40) / price  # use max 40% of available per trade
                    max_shares = min(max_shares, bp_shares)
        except Exception:
            pass

        # Apply capital planner's per-trade stock budget (T+1 settlement aware)
        try:
            from main import _hybrid_engine
            if _hybrid_engine and _hybrid_engine.planner:
                plan = _hybrid_engine.planner.get_or_create_plan()
                should_stop, stop_reason = plan.should_stop_trading()
                if should_stop:
                    return self._block(f"Day plan: {stop_reason}", price, atr)
                planner_max = plan.stock_per_trade / price
                max_shares  = min(max_shares, planner_max)
                if plan.remaining_stock_budget() < price:
                    return self._block(
                        f"Stock budget depleted — "
                        f"${plan.stock_deployed:.0f} of ${plan.stock_budget:.0f} used (T+1 locked)",
                        price, atr
                    )
        except Exception:
            pass

        shares = max(1, round(min(raw_shares, max_shares)))

        stop_loss   = round(price - stop_dist, 2)
        take_profit = round(price + stop_dist * self.atr_target_mult, 2)

        logger.info(
            f"SIZE {symbol}: qty={shares} | price={price:.2f} | "
            f"SL={stop_loss} TP={take_profit} | risk={risk_pct*100:.2f}%"
        )
        return {
            "qty":           shares,
            "position_value": round(shares * price, 2),
            "risk_pct":      round(risk_pct * 100, 2),
            "stop_loss":     stop_loss,
            "take_profit":   take_profit,
            "atr":           round(atr, 4),
            "stop_dist":     round(stop_dist, 4),
            "reason":        "ok",
        }

    # ── Exit logic ────────────────────────────────────────────────────────────

    def should_exit(self, position: dict, current_price: float, signal: dict) -> tuple[bool, str]:
        """
        Returns (should_exit, reason).
        Checks: hard stop-loss, take-profit, signal reversal, EOD flat.
        """
        entry = position.get("avg_entry", 0)
        qty   = position.get("qty", 0)
        side  = position.get("side", "long")
        atr   = signal.get("atr", 0) or (entry * 0.01)

        if entry <= 0 or qty <= 0:
            return False, ""

        if side == "long":
            pnl_pct = (current_price - entry) / entry
            stop     = entry - atr * self.atr_stop_mult
            target   = entry + atr * self.atr_target_mult
        else:                                  # short position
            pnl_pct = (entry - current_price) / entry
            stop     = entry + atr * self.atr_stop_mult
            target   = entry - atr * self.atr_target_mult

        # Hard stop-loss
        if (side == "long"  and current_price <= stop) or \
           (side == "short" and current_price >= stop):
            return True, f"Stop-loss hit ({pnl_pct*100:.1f}%)"

        # Take-profit
        if (side == "long"  and current_price >= target) or \
           (side == "short" and current_price <= target):
            return True, f"Take-profit hit (+{pnl_pct*100:.1f}%)"

        # Signal reversal with high confidence
        sig  = signal.get("signal", "HOLD")
        conf = signal.get("confidence", 0)
        if side == "long"  and sig == "SELL" and conf > 0.65:
            return True, "Signal reversed to SELL"
        if side == "short" and sig == "BUY"  and conf > 0.65:
            return True, "Signal reversed to BUY"

        return False, ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _block(reason: str, price: float, atr: float) -> dict:
        logger.warning(f"Trade blocked: {reason}")
        return {
            "qty":           0,
            "position_value": 0,
            "risk_pct":      0,
            "stop_loss":     price - atr * 2,
            "take_profit":   price + atr * 5,
            "atr":           round(atr, 4),
            "stop_dist":     0,
            "reason":        reason,
        }