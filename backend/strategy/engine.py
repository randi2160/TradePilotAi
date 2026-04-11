"""
Strategy engine — orchestrates the full trading lifecycle for one symbol:
  scan → signal → size → enter → monitor → exit → record
"""
import logging
from datetime import datetime

import pytz

import config
from broker.alpaca_client import AlpacaClient
from data.indicators import add_all_indicators
from models.ensemble import EnsembleModel
from strategy.daily_target import DailyTargetTracker
from strategy.risk_manager import DynamicRiskManager

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


class StrategyEngine:
    def __init__(
        self,
        broker: AlpacaClient,
        tracker: DailyTargetTracker,
        risk: DynamicRiskManager,
        ensemble: EnsembleModel,
    ):
        self.broker   = broker
        self.tracker  = tracker
        self.risk     = risk
        self.ensemble = ensemble

        self._signals: dict[str, dict] = {}   # latest signal per symbol
        self._open:    dict[str, dict] = {}   # open positions we opened

    # ── Main scan ─────────────────────────────────────────────────────────────

    async def scan_symbol(self, symbol: str) -> dict:
        """
        Full cycle for one symbol: fetch → indicators → ensemble → act.
        Returns the signal dict (enriched with action taken).
        """
        stop, stop_reason = self.tracker.should_stop()
        if stop:
            return {"symbol": symbol, "signal": "HALTED", "reason": stop_reason}

        if not self._trading_hours_ok():
            return {"symbol": symbol, "signal": "WAIT", "reason": "Outside trading window"}

        # ── 1. Market data + indicators ───────────────────────────────────────
        df = self.broker.get_bars(symbol, timeframe="5Min", limit=200)
        if df.empty or len(df) < 52:
            return {"symbol": symbol, "signal": "HOLD", "reason": "Insufficient data"}

        df = add_all_indicators(df)
        if df.empty:
            return {"symbol": symbol, "signal": "HOLD", "reason": "Indicator calc failed"}

        # ── 2. Ensemble signal ────────────────────────────────────────────────
        signal = self.ensemble.predict(df)
        signal["symbol"] = symbol
        signal["price"]  = float(df["close"].iloc[-1])
        self._signals[symbol] = signal

        # ── 3. Check existing position first ─────────────────────────────────
        if symbol in self._open:
            await self._manage_open_position(symbol, signal)

        # ── 4. Entry logic ────────────────────────────────────────────────────
        elif signal["signal"] in ("BUY", "SELL") and \
                signal["confidence"] >= config.MIN_CONFIDENCE_SCORE and \
                symbol not in self._open:
            await self._enter(symbol, signal, df)

        return signal

    # ── Entry ─────────────────────────────────────────────────────────────────

    async def _enter(self, symbol: str, signal: dict, df):
        price = signal["price"]
        atr   = signal.get("atr", 0)

        sizing = self.risk.size_position(
            symbol       = symbol,
            price        = price,
            atr          = atr,
            confidence   = signal["confidence"],
            current_pnl  = self.tracker.realized_pnl,
            target_min   = self.tracker.target_min,
            target_max   = self.tracker.target_max,
            open_positions = len(self._open),
        )

        if sizing["qty"] == 0:
            logger.info(f"Entry blocked for {symbol}: {sizing['reason']}")
            return

        side = signal["signal"]   # "BUY" or "SELL"

        # IMPORTANT: Only take LONG positions for retail paper trading
        # Short selling requires margin approval and is disabled by default
        if side != "BUY":
            logger.debug(f"Skipping {side} signal for {symbol} — only BUY (long) trades enabled")
            return

        order = self.broker.place_bracket_order(
            symbol      = symbol,
            qty         = sizing["qty"],
            side        = side,
            stop_loss   = sizing["stop_loss"],
            take_profit = sizing["take_profit"],
        )

        if "error" in order:
            logger.error(f"Order failed for {symbol}: {order['error']}")
            return

        self._open[symbol] = {
            "symbol":      symbol,
            "side":        side,
            "qty":         sizing["qty"],
            "avg_entry":   price,
            "stop_loss":   sizing["stop_loss"],
            "take_profit": sizing["take_profit"],
            "signal":      signal,
            "order_id":    order.get("id"),
        }
        self.tracker.record_open(symbol, price, sizing["qty"], side)
        logger.info(
            f"ENTER {side} {sizing['qty']}x{symbol} @ {price:.2f} | "
            f"SL={sizing['stop_loss']} TP={sizing['take_profit']} | "
            f"conf={signal['confidence']:.2f}"
        )

    # ── Position management ───────────────────────────────────────────────────

    async def _manage_open_position(self, symbol: str, signal: dict):
        pos   = self._open[symbol]
        price = self.broker.get_latest_price(symbol)
        if price == 0:
            return

        exit_flag, exit_reason = self.risk.should_exit(
            position      = pos,
            current_price = price,
            signal        = signal,
        )

        if exit_flag:
            self.broker.close_position(symbol)
            trade = self.tracker.record_close(
                symbol     = symbol,
                exit_price = price,
                signal     = pos["signal"],
            )
            del self._open[symbol]
            logger.info(f"EXIT {symbol} @ {price:.2f} | {exit_reason} | PnL=${trade['pnl']:.2f}")

    # ── End-of-day flat ───────────────────────────────────────────────────────

    async def close_all_eod(self):
        """Called at 15:55 ET to ensure we end the day flat."""
        for symbol in list(self._open.keys()):
            price = self.broker.get_latest_price(symbol)
            self.broker.close_position(symbol)
            self.tracker.record_close(symbol, price)
            del self._open[symbol]
            logger.info(f"EOD close: {symbol} @ {price:.2f}")

    # ── Sync positions with broker ────────────────────────────────────────────

    def sync_positions(self):
        """Reconcile our internal open dict with broker's actual positions."""
        broker_positions = {p["symbol"] for p in self.broker.get_positions()}
        for symbol in list(self._open.keys()):
            if symbol not in broker_positions:
                logger.warning(f"Position {symbol} no longer at broker — removing from tracking")
                del self._open[symbol]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_signals(self) -> list:
        return list(self._signals.values())

    def get_open_positions(self) -> list:
        return list(self._open.values())

    @staticmethod
    def _trading_hours_ok() -> bool:
        now = datetime.now(ET)
        h, m = now.hour, now.minute
        # Only trade 9:31 – 15:29 ET
        if (h == 9  and m < 31):  return False
        if (h == 15 and m >= 30): return False
        if h < 9 or h >= 16:     return False
        return True
