"""
Backtesting engine — runs the indicator + ensemble strategy on historical
OHLCV data to estimate win rate, profit factor, and expected daily P&L
before risking real money.
"""
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

SLIPPAGE_PCT   = 0.0005
COMMISSION     = 0.0


class BacktestEngine:
    def __init__(self, capital: float = 5000.0):
        self.capital = capital

    def run(
        self,
        df:               pd.DataFrame,
        min_confidence:   float = 0.55,
        atr_stop_mult:    float = 2.0,
        atr_target_mult:  float = 5.0,
        risk_pct:         float = 0.01,
        max_positions:    int   = 3,
    ) -> dict:
        """
        Simulate the strategy on historical bars.
        df must have OHLCV + all indicator columns (from add_all_indicators).
        Returns full stats including trade log.
        """
        if len(df) < 100:
            return {"error": "Need at least 100 bars to backtest"}

        try:
            from data.indicators import get_signal_from_indicators
        except ImportError:
            return {"error": "Indicators module not available"}

        trades        = []
        equity        = self.capital
        equity_curve  = [equity]
        open_trade    = None

        for i in range(52, len(df)):
            window = df.iloc[:i+1]
            bar    = df.iloc[i]
            price  = float(bar["close"])
            atr    = float(bar.get("atr", price * 0.01))

            sig = get_signal_from_indicators(window)
            action = sig.get("signal", "HOLD")
            conf   = sig.get("confidence", 0)

            # ── Manage open trade ─────────────────────────────────────────────
            if open_trade:
                side   = open_trade["side"]
                entry  = open_trade["entry"]
                stop   = open_trade["stop"]
                target = open_trade["target"]
                high   = float(bar["high"])
                low    = float(bar["low"])

                hit_target = (side == "BUY"  and high >= target) or \
                             (side == "SELL" and low  <= target)
                hit_stop   = (side == "BUY"  and low  <= stop)   or \
                             (side == "SELL" and high >= stop)

                exit_price = None
                exit_reason = ""

                if hit_stop:
                    exit_price  = stop
                    exit_reason = "stop_loss"
                elif hit_target:
                    exit_price  = target
                    exit_reason = "take_profit"
                elif (side == "BUY"  and action == "SELL" and conf > 0.65) or \
                     (side == "SELL" and action == "BUY"  and conf > 0.65):
                    exit_price  = price
                    exit_reason = "signal_reversal"

                if exit_price:
                    qty = open_trade["qty"]
                    if side == "BUY":
                        pnl = (exit_price - entry) * qty
                    else:
                        pnl = (entry - exit_price) * qty
                    slip = exit_price * qty * SLIPPAGE_PCT
                    net  = pnl - slip - COMMISSION

                    equity += net
                    equity_curve.append(equity)

                    trades.append({
                        "entry_bar":   open_trade["bar"],
                        "exit_bar":    i,
                        "symbol":      "BACKTEST",
                        "side":        side,
                        "qty":         qty,
                        "entry_price": round(entry, 2),
                        "exit_price":  round(exit_price, 2),
                        "pnl":         round(pnl, 2),
                        "net_pnl":     round(net, 2),
                        "reason":      exit_reason,
                        "confidence":  open_trade["confidence"],
                        "duration_bars": i - open_trade["bar"],
                    })
                    open_trade = None

            # ── Entry ─────────────────────────────────────────────────────────
            elif action in ("BUY","SELL") and conf >= min_confidence and open_trade is None:
                risk_dollars = equity * risk_pct
                stop_dist    = atr * atr_stop_mult
                qty          = max(1, round(risk_dollars / stop_dist))
                max_qty      = int((equity * 0.20) / price)
                qty          = min(qty, max_qty)

                if side_sign := (1 if action == "BUY" else -1):
                    entry_slip = price * (1 + side_sign * SLIPPAGE_PCT)
                    open_trade = {
                        "bar":        i,
                        "side":       action,
                        "entry":      entry_slip,
                        "stop":       entry_slip - side_sign * stop_dist,
                        "target":     entry_slip + side_sign * stop_dist * atr_target_mult,
                        "qty":        qty,
                        "confidence": conf,
                    }

        # ── Stats ──────────────────────────────────────────────────────────────
        if not trades:
            return {
                "error": "No trades generated — try lowering min_confidence",
                "bars_tested": len(df),
                "min_confidence": min_confidence,
            }

        pnls    = [t["net_pnl"] for t in trades]
        wins    = [p for p in pnls if p > 0]
        losses  = [p for p in pnls if p < 0]

        total_pnl    = sum(pnls)
        win_rate     = len(wins) / len(pnls) * 100
        profit_factor = abs(sum(wins)/sum(losses)) if losses else 999

        # Max drawdown
        peak = self.capital
        max_dd = 0
        running = self.capital
        for p in pnls:
            running += p
            peak     = max(peak, running)
            dd       = (peak - running) / peak * 100
            max_dd   = max(max_dd, dd)

        # Expected value per trade
        avg_win  = sum(wins)  / len(wins)   if wins   else 0
        avg_loss = sum(losses)/ len(losses) if losses else 0
        ev       = (win_rate/100 * avg_win) + ((1-win_rate/100) * avg_loss)

        bars_per_day = 78  # 6.5 hours × 12 bars/hour for 5-min bars
        trading_days = len(df) / bars_per_day
        avg_trades_per_day = len(trades) / max(trading_days, 1)

        return {
            "summary": {
                "bars_tested":         len(df),
                "trading_days_est":    round(trading_days, 0),
                "total_trades":        len(trades),
                "win_rate_pct":        round(win_rate, 1),
                "profit_factor":       round(profit_factor, 2),
                "total_pnl":           round(total_pnl, 2),
                "total_return_pct":    round(total_pnl / self.capital * 100, 2),
                "avg_win":             round(avg_win, 2),
                "avg_loss":            round(avg_loss, 2),
                "expected_value":      round(ev, 2),
                "max_drawdown_pct":    round(max_dd, 2),
                "avg_trades_per_day":  round(avg_trades_per_day, 1),
                "est_daily_pnl":       round(ev * avg_trades_per_day, 2),
                "starting_capital":    self.capital,
                "ending_capital":      round(self.capital + total_pnl, 2),
                "min_confidence_used": min_confidence,
            },
            "trades":       trades[-50:],
            "equity_curve": equity_curve[::max(1, len(equity_curve)//100)],
            "verdict":      _verdict(win_rate, profit_factor, max_dd, ev),
        }


def _verdict(win_rate: float, pf: float, max_dd: float, ev: float) -> dict:
    if win_rate >= 55 and pf >= 1.5 and max_dd <= 15 and ev > 0:
        return {"grade": "A", "color": "#00d4aa", "text": "Strong strategy — consider live testing with small capital"}
    if win_rate >= 50 and pf >= 1.2 and ev > 0:
        return {"grade": "B", "color": "#f59e0b", "text": "Decent results — continue paper trading for more data"}
    if ev > 0:
        return {"grade": "C", "color": "#f97316", "text": "Marginal edge — needs more optimization before going live"}
    return {"grade": "D", "color": "#ef4444", "text": "Negative expected value — do not trade live with this setup"}
