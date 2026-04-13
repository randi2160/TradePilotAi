"""
Strategy engine — orchestrates the full trading lifecycle for one symbol:
  scan → signal → size → enter → monitor → exit → record
"""
import logging
from datetime import datetime

import pytz

import config
from broker.alpaca_client  import AlpacaClient
from data.indicators       import add_all_indicators
from models.ensemble       import EnsembleModel
from strategy.daily_target import DailyTargetTracker
from strategy.risk_manager import DynamicRiskManager
from strategy.pdt_engine   import PDTComplianceEngine

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
        self.pdt      = PDTComplianceEngine(broker)

        self._signals: dict[str, dict] = {}
        self._open:    dict[str, dict] = {}

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
            logger.info(
                f"🎯 Entry candidate: {symbol} {signal['signal']} "
                f"conf={signal['confidence']:.2f} price=${signal['price']:.2f}"
            )
            await self._enter(symbol, signal, df)
        elif signal["signal"] in ("BUY", "SELL"):
            logger.debug(
                f"Signal {signal['signal']} {symbol} blocked: "
                f"conf={signal['confidence']:.2f} < {config.MIN_CONFIDENCE_SCORE} threshold"
                f"{' (already open)' if symbol in self._open else ''}"
            )

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

        # Only LONG positions for retail paper trading
        # Only LONG positions for retail paper trading
        if side != "BUY":
            logger.debug(f"Skipping {side} signal for {symbol} — only BUY (long) trades enabled")
            return

        # ── Pre-flight buying power check — skip if insufficient cash ─────────
        try:
            acct       = self.broker.get_account()
            nmbp       = float(acct.get("non_marginable_buying_power", 0))
            dtbp       = float(acct.get("daytrading_buying_power", 0))
            order_cost = sizing["qty"] * price
            effective_bp = nmbp if nmbp > 50 else dtbp
            if effective_bp < order_cost * 1.05:
                logger.warning(
                    f"⚠️  Skipping {symbol} — insufficient BP: "
                    f"need ${order_cost:.0f}, have ${effective_bp:.0f} "
                    f"(nmbp=${nmbp:.0f} dtbp=${dtbp:.0f})"
                )
                return
        except Exception as e:
            logger.debug(f"BP pre-check {symbol}: {e}")

        # ── PDT Compliance Check ──────────────────────────────────────────────

        # ── PDT Compliance Check ──────────────────────────────────────────────
        pdt_check = self.pdt.check_before_entry(symbol, sizing["qty"], price)
        if not pdt_check.get("allowed", False):
            logger.warning(f"PDT BLOCK: {symbol} — {pdt_check['reason']}")
            return

        if pdt_check.get("action") == "enter_hold_overnight":
            logger.warning(f"PDT OVERNIGHT: {symbol} — entering but MUST hold overnight: {pdt_check['reason']}")
            # Mark position as must-hold so exit engine won't close it today
            signal["pdt_hold_overnight"] = True

        if pdt_check.get("warning"):
            logger.warning(f"PDT WARNING: {symbol} — {pdt_check['reason']}")

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
            "db_id":       None,   # filled below
        }
        self.tracker.record_open(symbol, price, sizing["qty"], side)

        # ── Save opening trade to DB ──────────────────────────────────────
        try:
            from database.database import SessionLocal
            from database.models   import Trade as TradeModel
            from datetime import datetime as dt
            db    = SessionLocal()
            today = str(datetime.now(ET).date())
            t = TradeModel(
                user_id       = 1,   # default user; extend for multi-user
                symbol        = symbol,
                side          = side,
                qty           = sizing["qty"],
                entry_price   = price,
                stop_loss     = sizing["stop_loss"],
                take_profit   = sizing["take_profit"],
                confidence    = signal.get("confidence", 0),
                risk_dollars  = sizing.get("risk_dollars", 0),
                position_value= round(price * sizing["qty"], 2),
                order_id      = order.get("id", ""),
                status        = "open",
                trade_date    = today,
                opened_at     = dt.utcnow(),
            )
            db.add(t)
            db.commit()
            db.refresh(t)
            self._open[symbol]["db_id"] = t.id
            db.close()
            logger.info(f"DB: opened trade {symbol} id={t.id}")

            # Auto-broadcast to social feed
            try:
                from services.social_service import SocialService
                from database.database import SessionLocal as SL2
                db2  = SL2()
                from database.models import User as UserModel
                user = db2.query(UserModel).filter_by(id=1).first()
                if user:
                    svc = SocialService(db2)
                    reasons = signal.get("reasons", [])
                    reasoning = " · ".join(reasons[:3]) if reasons else f"Conf {signal.get('confidence',0):.0%} · {signal.get('setup','')}"
                    svc.broadcast_trade(user, t, "BUY", reasoning=reasoning)
                db2.close()
            except Exception as e:
                logger.debug(f"Social broadcast skipped: {e}")
        except Exception as e:
            logger.error(f"DB open_trade failed for {symbol}: {e}")

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
            # ── PDT Exit Check ────────────────────────────────────────────
            entry_date = str(pos.get("entry_date", ""))
            pdt_exit   = self.pdt.check_before_exit(symbol, entry_date)

            if not pdt_exit.get("allowed", True):
                logger.warning(f"PDT EXIT BLOCKED: {symbol} — {pdt_exit['reason']} — holding overnight")
                # Don't close — mark as hold overnight
                pos["pdt_hold_overnight"] = True
                return

            if pos.get("pdt_hold_overnight") and pdt_exit.get("is_day_trade"):
                logger.warning(f"PDT OVERNIGHT HOLD active for {symbol} — skipping intraday exit")
                return

            self.broker.close_position(symbol)
            trade = self.tracker.record_close(
                symbol     = symbol,
                exit_price = price,
                signal     = pos["signal"],
            )
            del self._open[symbol]
            logger.info(f"EXIT {symbol} @ {price:.2f} | {exit_reason} | PnL=${trade['pnl']:.2f}")

            # ── Persist closed trade to DB ────────────────────────────────
            try:
                from database.database import SessionLocal
                from database.models   import Trade as TradeModel
                from datetime import datetime as dt
                db       = SessionLocal()
                db_id    = pos.get("db_id")
                today    = str(datetime.now(ET).date())

                # Find by db_id first, fall back to symbol lookup
                if db_id:
                    open_trade = db.query(TradeModel).filter(
                        TradeModel.id == db_id
                    ).first()
                else:
                    open_trade = db.query(TradeModel).filter(
                        TradeModel.symbol == symbol,
                        TradeModel.status == "open",
                    ).order_by(TradeModel.opened_at.desc()).first()

                if open_trade:
                    open_trade.exit_price = price
                    open_trade.status     = "closed"
                    open_trade.closed_at  = dt.utcnow()
                    open_trade.pnl        = round(trade["pnl"], 2)
                    open_trade.pnl_pct    = round(trade.get("pnl_pct", 0), 2)
                    open_trade.trade_date = today
                    db.commit()
                    logger.info(f"DB: closed trade {symbol} pnl=${trade['pnl']:.2f}")

                    # Auto-broadcast close to social feed
                    try:
                        from services.social_service import SocialService
                        from database.models import User as UserModel
                        user = db.query(UserModel).filter_by(id=1).first()
                        if user:
                            action = "TARGET_HIT" if trade["pnl"] > 0 else "STOP_HIT"
                            SocialService(db).broadcast_trade(user, open_trade, action)
                    except Exception as be:
                        logger.debug(f"Social close broadcast skipped: {be}")
                else:
                    logger.warning(f"DB: no open trade found for {symbol} to close")
                db.close()
            except Exception as e:
                logger.error(f"DB close_trade failed for {symbol}: {e}")

    # ── End-of-day flat ───────────────────────────────────────────────────────

    async def close_all_eod(self):
        """Called at 15:55 ET to ensure we end the day flat."""
        for symbol in list(self._open.keys()):
            price = self.broker.get_latest_price(symbol)
            self.broker.close_position(symbol)
            trade = self.tracker.record_close(symbol, price)

            # Save to DB
            try:
                from database.database import SessionLocal
                from database.models   import Trade as TradeModel
                from datetime import datetime as dt
                db     = SessionLocal()
                db_id  = self._open[symbol].get("db_id")
                today  = str(datetime.now(ET).date())
                rec    = db.query(TradeModel).filter(
                    TradeModel.id == db_id if db_id else False
                ).first() or db.query(TradeModel).filter(
                    TradeModel.symbol == symbol,
                    TradeModel.status == "open",
                ).order_by(TradeModel.opened_at.desc()).first()
                if rec:
                    rec.exit_price = price
                    rec.status     = "closed"
                    rec.closed_at  = dt.utcnow()
                    rec.pnl        = round(trade.get("pnl", 0), 2)
                    rec.trade_date = today
                    db.commit()
                db.close()
            except Exception as e:
                logger.error(f"DB EOD close failed for {symbol}: {e}")

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
