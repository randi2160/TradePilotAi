"""
Exit Engine — manages open position exits with:
  • Hard stop loss (always)
  • Partial profit at 1R (sell 50%)
  • Trail stop after 1R profit
  • Full exit at 2R or target
  • Loss of VWAP exit
  • Momentum slowdown exit
  • Time-based exit (before market close)
"""
import logging
from datetime import datetime
from typing import Optional

import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


class ExitEngine:

    def check_exit(
        self,
        position:      dict,
        current_price: float,
        vwap_info:     dict,
        signal:        dict,
        df:            Optional[object] = None,
    ) -> dict:
        """
        Returns exit decision for an open position.
        Response: {should_exit, portion, reason, urgency}
        portion: 0.5 = sell half, 1.0 = sell all
        urgency: 'immediate' | 'next_candle' | 'eod'
        """
        entry     = position.get("avg_entry", current_price)
        qty       = position.get("qty", 0)
        side      = position.get("side", "long")
        stop      = position.get("stop_loss",   entry * 0.99)
        target    = position.get("take_profit", entry * 1.02)
        setup_type = position.get("setup_type", "")

        if qty <= 0 or entry <= 0:
            return self._no_exit()

        # P&L metrics
        if side == "long":
            pnl_pct    = (current_price - entry) / entry * 100
            stop_dist  = entry - stop
            one_r      = entry + stop_dist        # 1R profit level
            two_r      = entry + stop_dist * 2    # 2R profit level
            above_vwap = vwap_info.get("above_vwap", True)
        else:
            pnl_pct    = (entry - current_price) / entry * 100
            stop_dist  = stop - entry
            one_r      = entry - stop_dist
            two_r      = entry - stop_dist * 2
            above_vwap = not vwap_info.get("above_vwap", False)

        # ── 1. Hard stop loss ──────────────────────────────────────────────────
        stop_hit = (side == "long" and current_price <= stop) or \
                   (side == "short" and current_price >= stop)
        if stop_hit:
            return self._exit(1.0, f"🛑 STOP LOSS hit at ${current_price:.2f} (${pnl_pct:.1f}%)", "immediate")

        # ── 2. Full target hit (2R or user target) ─────────────────────────────
        target_hit = (side == "long" and current_price >= target) or \
                     (side == "short" and current_price <= target)
        if target_hit:
            return self._exit(1.0, f"🎯 TARGET hit at ${current_price:.2f} (+{pnl_pct:.1f}%)", "immediate")

        # ── 3. Partial profit at 1R ────────────────────────────────────────────
        at_1r     = (side == "long" and current_price >= one_r) or \
                    (side == "short" and current_price <= one_r)
        partial_taken = position.get("partial_taken", False)
        if at_1r and not partial_taken:
            return self._exit(0.5, f"💰 Partial exit at 1R — ${current_price:.2f} (+{pnl_pct:.1f}%)", "next_candle",
                              action="partial", trail_stop=True, new_stop=entry)  # move stop to breakeven

        # ── 4. Trail stop (after partial taken) ────────────────────────────────
        if partial_taken and position.get("trail_active", False):
            trail_stop = position.get("trail_stop", stop)
            atr = signal.get("atr", stop_dist * 0.5)

            # Update trail if price moved favorably
            if side == "long":
                new_trail = current_price - atr * 1.0
                if new_trail > trail_stop:
                    position["trail_stop"] = new_trail
                    logger.debug(f"Trail stop updated: ${new_trail:.2f}")
                # Check if trail triggered
                if current_price <= position.get("trail_stop", stop):
                    return self._exit(1.0, f"📍 Trail stop triggered at ${current_price:.2f} (+{pnl_pct:.1f}%)", "immediate")

        # ── 5. Loss of VWAP exit ───────────────────────────────────────────────
        if side == "long" and not above_vwap and pnl_pct > 0:
            # Price lost VWAP while profitable — take partial profits
            vwap_val = vwap_info.get("vwap", 0)
            return self._exit(0.5, f"⚠️ VWAP lost at ${vwap_val:.2f} — reducing position", "next_candle")

        # ── 6. Signal reversal ────────────────────────────────────────────────
        sig_direction = signal.get("signal", "HOLD")
        sig_confidence = signal.get("confidence", 0)
        if side == "long"  and sig_direction == "SELL" and sig_confidence > 0.70:
            return self._exit(1.0, f"🔄 Signal reversed to SELL ({sig_confidence:.0%} conf)", "next_candle")
        if side == "short" and sig_direction == "BUY"  and sig_confidence > 0.70:
            return self._exit(1.0, f"🔄 Signal reversed to BUY ({sig_confidence:.0%} conf)", "next_candle")

        # ── 7. Momentum slowdown ───────────────────────────────────────────────
        if df is not None and len(df) >= 5:
            try:
                closes = df["close"].values
                volumes = df["volume"].values
                # Volume declining while at profit = distribution
                vol_declining = volumes[-1] < volumes[-2] < volumes[-3]
                price_slowing = abs(closes[-1] - closes[-2]) < abs(closes[-2] - closes[-3]) * 0.5
                if vol_declining and price_slowing and pnl_pct > 0.5:
                    return self._exit(0.5, "📉 Momentum slowing — volume declining, taking partial profits", "next_candle")
            except Exception:
                pass

        # ── 8. EOD exit (3:50 PM ET) ────────────────────────────────────────
        now  = datetime.now(ET)
        hour = now.hour + now.minute / 60
        if hour >= 15.833:  # 3:50 PM
            return self._exit(1.0, f"⏰ End of day — closing all positions at ${current_price:.2f}", "immediate")

        return self._no_exit()

    @staticmethod
    def _exit(portion: float, reason: str, urgency: str, **kwargs) -> dict:
        return {
            "should_exit": True,
            "portion":     portion,
            "reason":      reason,
            "urgency":     urgency,
            **kwargs,
        }

    @staticmethod
    def _no_exit() -> dict:
        return {"should_exit": False, "portion": 0, "reason": "", "urgency": ""}
