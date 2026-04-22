"""
Strategy engine — orchestrates the full trading lifecycle for one symbol:
  scan → signal → size → enter → monitor → exit → record
"""
import logging
from datetime import datetime

import pytz

import config
from broker.alpaca_client      import AlpacaClient
from data.indicators           import add_all_indicators
from data.regime_detector      import RegimeDetector
from models.ensemble           import EnsembleModel
from strategy.daily_target     import DailyTargetTracker
from strategy.risk_manager     import DynamicRiskManager
from strategy.pdt_engine       import PDTComplianceEngine
from strategy.setup_classifier import SetupClassifier

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


class StrategyEngine:
    def __init__(
        self,
        broker: AlpacaClient,
        tracker: DailyTargetTracker,
        risk: DynamicRiskManager,
        ensemble: EnsembleModel,
        user_id: int = None,
    ):
        self.broker   = broker
        self.tracker  = tracker
        self.risk     = risk
        self.ensemble = ensemble
        self.pdt      = PDTComplianceEngine(broker)
        self.user_id  = user_id  # per-user trade ownership

        # AI setup analysis — enriches trades with quality score + regime awareness
        self.setup_classifier = SetupClassifier()
        self.regime_detector  = RegimeDetector()
        self._current_regime  = None       # refreshed every scan cycle
        self._regime_df       = None       # SPY bars for regime detection

        self._signals: dict[str, dict] = {}
        self._open:    dict[str, dict] = {}

    # ── Main scan ─────────────────────────────────────────────────────────────

    def _refresh_regime(self):
        """Refresh market regime from SPY bars (cached, only fetches every ~5 min)."""
        try:
            spy_df = self.broker.get_bars("SPY", timeframe="5Min", limit=100)
            if spy_df is not None and not spy_df.empty and len(spy_df) >= 30:
                self._regime_df      = spy_df
                self._current_regime = self.regime_detector.detect(spy_df)
                logger.debug(
                    f"Market regime: {self._current_regime.get('regime')} "
                    f"({self._current_regime.get('description','')})"
                )
        except Exception as e:
            logger.debug(f"Regime refresh: {e}")
        if self._current_regime is None:
            self._current_regime = self.regime_detector._default()

    def _classify_setup(self, symbol: str, df, signal: dict) -> dict:
        """Run setup classifier for quality scoring. Returns setup dict."""
        try:
            regime = self._current_regime or self.regime_detector._default()
            # Build VWAP info from indicators
            cur = df.iloc[-1]
            vwap_est = float(cur.get("ema_21", cur["close"]))  # EMA21 as VWAP proxy
            vwap_info = {
                "vwap":       vwap_est,
                "above_vwap": float(cur["close"]) > vwap_est,
                "reclaim":    float(cur["close"]) > vwap_est and float(df.iloc[-2]["close"]) <= vwap_est,
            }
            indicators = {
                "rsi":          float(cur.get("rsi", 50)),
                "macd_diff":    float(cur.get("macd_diff", 0)),
                "bb_pct":       float(cur.get("bb_pct", 0.5)),
                "volume_ratio": float(cur.get("volume_ratio", 1.0)),
                "atr":          float(cur.get("atr", 0)),
            }
            return self.setup_classifier.classify(df, symbol, regime, vwap_info, indicators)
        except Exception as e:
            logger.debug(f"Setup classify {symbol}: {e}")
            return {"setup_type": "unknown", "tradeable": True, "quality": 50}

    async def scan_symbol(self, symbol: str) -> dict:
        """
        Full cycle for one symbol: fetch → indicators → ensemble → setup classify → act.
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

        # ── 1b. Refresh market regime (once per scan cycle, cached) ───────────
        if self._current_regime is None:
            self._refresh_regime()

        # ── 2. Ensemble signal (PRESERVED — existing ML + technical layer) ────
        signal = self.ensemble.predict(df)
        signal["symbol"] = symbol
        signal["price"]  = float(df["close"].iloc[-1])

        # ── 2b. Setup classification (ADDITIVE — enriches signal, gates low-quality) ──
        setup = self._classify_setup(symbol, df, signal)
        signal["setup"]         = setup.get("setup_type", "unknown")
        signal["setup_quality"] = setup.get("quality", 0)
        signal["setup_tradeable"] = setup.get("tradeable", True)
        signal["regime"]        = (self._current_regime or {}).get("regime", "neutral")
        if setup.get("description"):
            signal.setdefault("reasons", []).append(setup["description"])

        self._signals[symbol] = signal

        # ── 3. Check existing position first (PRESERVED) ─────────────────────
        if symbol in self._open:
            await self._manage_open_position(symbol, signal)

        # ── 4. Entry logic (PRESERVED + setup quality gate added) ─────────────
        elif signal["signal"] in ("BUY", "SELL") and \
                signal["confidence"] >= config.MIN_CONFIDENCE_SCORE and \
                symbol not in self._open:

            # NEW: Block low-quality setups — but let high-confidence signals through
            # Setup quality < 50 AND ensemble confidence < 0.70 → skip
            # (high ML confidence can override a marginal setup)
            if not setup.get("tradeable", True) and signal["confidence"] < 0.70:
                logger.info(
                    f"⚠️  {symbol} {signal['signal']} blocked by setup filter: "
                    f"setup={setup.get('setup_type','?')} quality={setup.get('quality',0):.0f} "
                    f"issues={setup.get('quality_issues',[])} | "
                    f"conf={signal['confidence']:.2f} < 0.70 override threshold"
                )
                signal["action"] = "SETUP_BLOCKED"
            else:
                logger.info(
                    f"🎯 Entry candidate: {symbol} {signal['signal']} "
                    f"conf={signal['confidence']:.2f} price=${signal['price']:.2f} "
                    f"setup={setup.get('setup_type','?')} quality={setup.get('quality',0):.0f}"
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

        # ── Pre-trade floor gate (gain-protection enforcement) ────────────────
        # The protection service already REACTS to breaches by halting the bot
        # and closing everything, but until now nothing stopped us from opening
        # a trade that would CAUSE the breach. Compute worst-case loss against
        # the position's stop-loss; if that drops live equity below the user's
        # locked floor, refuse the entry entirely. Per-user — legacy system bot
        # (no user_id) retains old behaviour.
        if self.user_id:
            try:
                from database.database import SessionLocal as _FloorSL
                from services          import protection_service as _prot
                with _FloorSL() as _fdb:
                    _fs = _prot.get_or_create(_fdb, self.user_id)
                    if _fs.enabled and float(_fs.floor_value or 0) > 0:
                        _acct  = self.broker.get_account() or {}
                        _live  = float(_acct.get("equity", 0) or 0)
                        _stop  = float(sizing.get("stop_loss", 0) or 0)
                        _qty   = int(sizing.get("qty", 0) or 0)
                        # Long-only: worst-case dollar loss if the stop hits.
                        _risk = max(0.0, (price - _stop) * _qty) if _stop > 0 else 0.0
                        _worst_eq = _live - _risk
                        _floor    = float(_fs.floor_value or 0)
                        if _live > 0 and _worst_eq < _floor:
                            logger.warning(
                                f"🔒 Floor gate BLOCK {symbol}: "
                                f"equity ${_live:.2f}, stop-risk ${_risk:.2f}, "
                                f"worst-case ${_worst_eq:.2f} < floor ${_floor:.2f} "
                                f"(qty={_qty} entry=${price:.2f} stop=${_stop:.2f})"
                            )
                            return
            except Exception as _fg_e:
                # Never let a protection-check error block trading silently —
                # log loudly so we can tell if the gate is actually running.
                logger.warning(f"floor gate check failed for {symbol}: {_fg_e}")

        # ── Pre-flight buying power check — skip if insufficient cash ─────────
        # ── Pre-flight buying power check — skip if Alpaca will reject ──────────
        try:
            acct       = self.broker.get_account()
            dtbp       = float(acct.get("daytrading_buying_power", 0))
            order_cost = sizing["qty"] * price
            if dtbp == 0:
                logger.warning(
                    f"⚠️  Skipping {symbol} — Alpaca daytrading_buying_power=$0 "
                    f"(crypto positions holding cash). Retrying when crypto exits."
                )
                return
            if dtbp < order_cost:
                logger.warning(
                    f"⚠️  Skipping {symbol} — dtbp=${dtbp:.0f} < cost=${order_cost:.0f}"
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
                user_id       = self.user_id or 1,  # per-user; fallback 1 for legacy
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
