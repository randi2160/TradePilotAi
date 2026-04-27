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
from strategy.orb_engine       import ORBEngine
from data.news_scanner         import NewsScanner

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

        # Opening Range Breakout — additive strategy. Records 9:30-9:45 ET
        # opening range per symbol, generates BUY signals on breakout above
        # the range high with volume confirmation. Fused with ensemble below;
        # never replaces it.
        self.orb = ORBEngine()

        # News sentiment scanner — keyword-based (no LLM cost), 300s cache,
        # graceful fallback to neutral on any error. Used as a small
        # confidence modifier on signals; never blocks a trade by itself.
        self.news = NewsScanner()

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

        # ── 2c. ORB fusion (ADDITIVE — never replaces ensemble) ──────────────
        # During the opening-range window we feed each scan's bars into the
        # ORB tracker so it can build the 9:30-9:45 high/low. After 9:45 it
        # stops accepting new bars and finalizes the range. Between 9:45 and
        # 11:00 ET, we ask ORB if this symbol is breaking out — if it is,
        # we fuse the result with the ensemble:
        #   - ensemble BUY    + ORB BUY  → confidence boosted to max of both
        #                                  + setup is forced tradeable
        #                                  + reason annotated for the trade log
        #   - ensemble HOLD   + ORB BUY  → upgrade to BUY only if ensemble
        #                                  conf is at least 0.50 (don't trade
        #                                  on ORB alone when ML is bearish)
        #   - ensemble SELL   + ORB BUY  → ignore ORB; ML conviction wins
        # If ORB throws or returns None, this whole block is a no-op and the
        # existing ensemble/setup flow runs unchanged.
        try:
            if self.orb.is_active():
                if self.orb.in_recording_window():
                    self.orb.update_range(symbol, df)
                else:
                    self.orb.finalize_if_due(symbol)
                    orb_sig = self.orb.check_breakout(symbol, df)
                    if orb_sig:
                        ens_signal = signal.get("signal", "HOLD")
                        ens_conf   = float(signal.get("confidence", 0) or 0)
                        if ens_signal == "BUY":
                            signal["confidence"] = max(ens_conf, orb_sig["confidence"])
                            signal["setup_tradeable"] = True
                            signal.setdefault("reasons", []).extend(orb_sig.get("reasons", []))
                            signal["orb_breakout"] = True
                            logger.info(f"🚀 ORB+Ensemble BUY confirm {symbol}: "
                                        f"conf={signal['confidence']:.2f} "
                                        f"orb_high=${orb_sig['orb_high']:.2f}")
                        elif ens_signal == "HOLD" and ens_conf >= 0.50:
                            signal["signal"]     = "BUY"
                            signal["confidence"] = orb_sig["confidence"]
                            signal["setup_tradeable"] = True
                            signal.setdefault("reasons", []).extend(orb_sig.get("reasons", []))
                            signal["orb_breakout"] = True
                            logger.info(f"🚀 ORB-only BUY {symbol}: ensemble HOLD@{ens_conf:.2f} "
                                        f"upgraded to BUY@{orb_sig['confidence']:.2f}")
                        # ensemble SELL → ignore ORB silently (no log spam)
        except Exception as _orb_e:
            logger.debug(f"ORB fusion {symbol}: {_orb_e}")

        # ── 2d. News sentiment fusion (ADDITIVE — confidence modifier only) ─
        # Reads aggregated keyword sentiment from data/news_scanner.py — uses
        # Alpaca's news API + a static bullish/bearish word bank. No LLM cost.
        # 300-second per-symbol cache, async-safe, returns neutral on any
        # failure. We apply the result as a SMALL confidence nudge:
        #   bullish news (+score >  0.2) and BUY signal  → +0.05 boost
        #   bearish news (-score < -0.2) and BUY signal  → -0.10 penalty
        #   bullish news and SELL signal                  → -0.10 penalty
        #   bearish news and SELL signal                  → +0.05 boost
        # Capped at ±0.10 total. We never veto a trade purely on sentiment —
        # the goal is to tilt the existing ensemble decision by a fraction
        # when the news flow agrees or disagrees, not to override the model.
        try:
            sent = await self.news.get_sentiment_signal(symbol)
            label = sent.get("sentiment", "neutral")
            score = float(sent.get("score", 0) or 0)
            n_art = int(sent.get("articles", 0) or 0)
            sig_dir = signal.get("signal", "HOLD")
            if n_art > 0 and sig_dir in ("BUY", "SELL"):
                delta = 0.0
                if label == "bullish":
                    delta = 0.05 if sig_dir == "BUY" else -0.10
                elif label == "bearish":
                    delta = -0.10 if sig_dir == "BUY" else 0.05
                if delta != 0.0:
                    old_conf = float(signal.get("confidence", 0) or 0)
                    new_conf = max(0.0, min(0.99, old_conf + delta))
                    signal["confidence"]   = new_conf
                    signal["news_score"]   = score
                    signal["news_label"]   = label
                    signal["news_articles"] = n_art
                    signal.setdefault("reasons", []).append(
                        f"News {label} ({n_art} articles, score {score:+.2f}) "
                        f"→ conf {old_conf:.2f}→{new_conf:.2f}"
                    )
        except Exception as _news_e:
            logger.debug(f"News fusion {symbol}: {_news_e}")

        self._signals[symbol] = signal

        # ── 3. Check existing position first (PRESERVED) ─────────────────────
        if symbol in self._open:
            await self._manage_open_position(symbol, signal)

        # ── 4. Entry logic (PRESERVED + setup quality gate added) ─────────────
        elif signal["signal"] in ("BUY", "SELL") and \
                signal["confidence"] >= config.MIN_CONFIDENCE_SCORE and \
                symbol not in self._open:

            # Block low-quality setups — but let moderately-confident signals
            # through. Previously the override threshold was 0.70 which blocked
            # most valid setups (ensemble typically reports 0.55-0.65). With
            # the downstream R:R gate (1.5 min), portfolio position cap, and
            # intra-harvest protection in place, the setup filter doesn't need
            # to be this strict — it was doing redundant gating. Dropped to
            # 0.60 so setups at 0.60+ confidence can override a "no_trade"
            # classification and reach the sizer (where R:R still gates them).
            _SETUP_OVERRIDE = 0.60
            if not setup.get("tradeable", True) and signal["confidence"] < _SETUP_OVERRIDE:
                logger.info(
                    f"⚠️  {symbol} {signal['signal']} blocked by setup filter: "
                    f"setup={setup.get('setup_type','?')} quality={setup.get('quality',0):.0f} "
                    f"issues={setup.get('quality_issues',[])} | "
                    f"conf={signal['confidence']:.2f} < {_SETUP_OVERRIDE:.2f} override threshold"
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

        # ── Read protection settings up-front ─────────────────────────────────
        # Grab everything we need in one query: recovery flags, floor values,
        # AND the user-configurable entry filters (min_stock_conf, min_rr,
        # max_total_positions) so we don't round-trip the DB multiple times.
        _recovery_mode     = False
        _rec_size_mult     = 1.0
        _rec_stop_mult     = 1.0
        _rec_conf_boost    = 0.0
        _rec_budget        = 0.0
        _protection_ready  = False
        _live_equity       = 0.0
        _settings_snapshot = None
        _min_stock_conf    = float(config.MIN_CONFIDENCE_SCORE)
        _min_rr            = 1.5
        _max_total_positions = 6
        if self.user_id:
            try:
                from database.database import SessionLocal as _PSL
                from services          import protection_service as _prot_svc
                with _PSL() as _pdb:
                    _s = _prot_svc.get_or_create(_pdb, self.user_id)
                    if _s.enabled:
                        _acct = self.broker.get_account() or {}
                        _live_equity = float(_acct.get("equity", 0) or 0)
                        _recovery_mode  = _prot_svc.is_in_recovery_mode(_s, _live_equity)
                        _rec_size_mult  = float(_s.recovery_size_mult  or 0.60)
                        _rec_stop_mult  = float(_s.recovery_stop_mult  or 0.75)
                        _rec_conf_boost = float(_s.recovery_conf_boost or 0.05)
                        _rec_budget     = float(_s.recovery_budget     or 20.0)
                        # Entry filters — the STRICTER of config.MIN_CONFIDENCE_SCORE
                        # and user's per-asset knob wins, so lowering the user
                        # knob never relaxes the global floor.
                        _min_stock_conf = max(
                            float(config.MIN_CONFIDENCE_SCORE),
                            float(_s.min_stock_conf or 0.55),
                        )
                        _min_rr              = float(_s.min_rr or 1.5)
                        _max_total_positions = int(_s.max_total_positions or 6)
                        _settings_snapshot = {
                            "floor_value":     float(_s.floor_value     or 0.0),
                            "initial_capital": float(_s.initial_capital or 0.0),
                        }
                        _protection_ready = True
            except Exception as _ps_e:
                logger.warning(f"protection snapshot for {symbol}: {_ps_e}")

        # ── Stock confidence gate (Fix #1) ────────────────────────────────────
        # scan_symbol already checks config.MIN_CONFIDENCE_SCORE; we re-check
        # here with the user's potentially-stricter knob, plus recovery boost.
        _required_conf = _min_stock_conf
        if _recovery_mode and _rec_conf_boost > 0:
            _required_conf += _rec_conf_boost
        if float(signal.get("confidence", 0) or 0) < _required_conf:
            logger.info(
                f"🚫 Stock conf gate block {symbol}: "
                f"conf {signal['confidence']:.2f} < required {_required_conf:.2f}"
                f"{' (recovery boost applied)' if _recovery_mode else ''}"
            )
            return

        # ── Portfolio-wide position cap (Fix #3) ─────────────────────────────
        # Combined stocks + crypto count — guards against 3 stocks + 3 crypto
        # blowing past a user-set cap of 5 total.
        if _protection_ready:
            try:
                _all_pos = self.broker.get_positions() or []
                if len(_all_pos) >= _max_total_positions:
                    logger.info(
                        f"🚫 Portfolio cap reached: {len(_all_pos)} open positions "
                        f">= max_total_positions={_max_total_positions}. "
                        f"Skipping {symbol} entry."
                    )
                    return
            except Exception as _cap_e:
                logger.debug(f"total-position cap check: {_cap_e}")

        # Note: recovery-mode confidence boost is already folded into
        # _required_conf by the stock confidence gate above — no separate
        # recovery check needed here.

        sizing = self.risk.size_position(
            symbol       = symbol,
            price        = price,
            atr          = atr,
            confidence   = signal["confidence"],
            current_pnl  = self.tracker.realized_pnl,
            target_min   = self.tracker.target_min,
            target_max   = self.tracker.target_max,
            open_positions = len(self._open),
            recovery_mode      = _recovery_mode,
            recovery_size_mult = _rec_size_mult,
            recovery_stop_mult = _rec_stop_mult,
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

        # ── Minimum R:R gate (Fix #4) ────────────────────────────────────────
        # (take_profit - price) / (price - stop_loss) must clear min_rr. This
        # single filter would have skipped about half of yesterday's losers —
        # many had stops wider than targets (R:R < 1) which is a guaranteed
        # losing expectation even at a 60% hit rate.
        _tp = float(sizing.get("take_profit", 0) or 0)
        _sl = float(sizing.get("stop_loss",   0) or 0)
        _reward = _tp - price
        _risk   = price - _sl
        if _risk > 0 and _reward > 0:
            _rr = _reward / _risk
            if _rr < _min_rr:
                logger.info(
                    f"🚫 Stock R:R gate block {symbol}: "
                    f"reward ${_reward:.2f} / risk ${_risk:.2f} = {_rr:.2f} "
                    f"< {_min_rr:.2f} required"
                )
                return

        # ── Pre-trade floor gate (gain-protection enforcement) ────────────────
        # Uses the settings snapshot we already loaded above. Worst-case loss
        # = (price − stop_loss) × qty for a long.
        #
        # Normal mode: refuse the trade if worst-case equity would drop below
        # the locked floor.
        #
        # Recovery mode: comparing against the floor is a lockup — we're
        # already below it by definition. Instead compare against
        # (live_equity − recovery_budget): each trade can risk at most
        # `recovery_budget` dollars of further drawdown. This keeps the bot
        # trading toward base while capping blast radius per trade.
        if _protection_ready and _settings_snapshot and _live_equity > 0:
            _stop = float(sizing.get("stop_loss", 0) or 0)
            _qty  = int(sizing.get("qty", 0) or 0)
            _risk = max(0.0, (price - _stop) * _qty) if _stop > 0 else 0.0
            _worst_eq = _live_equity - _risk
            _floor    = _settings_snapshot["floor_value"]
            if _recovery_mode:
                _limit = _live_equity - _rec_budget
                if _worst_eq < _limit:
                    logger.warning(
                        f"🔧 Recovery gate BLOCK {symbol}: worst-case "
                        f"${_worst_eq:.2f} < allowed ${_limit:.2f} "
                        f"(equity ${_live_equity:.2f} − budget ${_rec_budget:.2f}). "
                        f"stop-risk=${_risk:.2f} qty={_qty}"
                    )
                    return
            else:
                if _worst_eq < _floor:
                    logger.warning(
                        f"🔒 Floor gate BLOCK {symbol}: "
                        f"equity ${_live_equity:.2f}, stop-risk ${_risk:.2f}, "
                        f"worst-case ${_worst_eq:.2f} < floor ${_floor:.2f} "
                        f"(qty={_qty} entry=${price:.2f} stop=${_stop:.2f})"
                    )
                    return

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
