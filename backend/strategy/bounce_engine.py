"""
Morviq AI — Crypto Bounce Trade Engine

Automated bounce/mean-reversion trading for crypto. Uses BounceAnalyzer
for statistical analysis + LLM recommendations, then executes trades
when confidence thresholds are met.

Entry criteria (ALL must be true):
  - bounce_score >= 60
  - LLM action == BUY_BOUNCE
  - LLM confidence >= 0.65
  - trend is ranging or mixed (not trending)
  - price within 1% of the analyzer's entry zone

Position sizing:
  - Scales with confidence: 65% conf → 50% of max size, 90% conf → 100%
  - Hard cap at configured crypto budget

Exit rules:
  - Trailing stop (same logic as CryptoEngine)
  - Target hit (conservative target from analyzer)
  - Time stop (configurable, default 30 min — bounces are slower than scalps)
  - Floor breach from daily loss limit
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

from strategy.bounce_analyzer import BounceAnalyzer
from strategy.crypto_engine import (
    CryptoPosition,
    EngineState,
    ALPACA_TRADEABLE,
    CRYPTO_UNIVERSE,
)

logger = logging.getLogger(__name__)


class BounceTradeEngine:
    """
    Automated bounce trader. Wraps BounceAnalyzer + trade execution.
    Drop-in replacement for CryptoEngine — same status()/run_cycle() interface
    so HybridEngine can swap between them.
    """

    # ── Thresholds ────────────────────────────────────────────────────────────
    MIN_BOUNCE_SCORE   = 60       # minimum bounce_score to consider
    MIN_LLM_CONFIDENCE = 0.65     # minimum LLM confidence to trade
    MAX_ENTRY_DIST_PCT = 1.5      # max % above ideal entry zone to still buy
    MAX_HOLD_MIN       = 30       # bounce trades hold longer than scalps
    SCAN_INTERVAL_SEC  = 120      # re-analyze every 2 min (analyzer is heavier than scalp scan)

    def __init__(
        self,
        broker,
        target_min:     float = 150,
        target_desired: float = 200,
        target_stretch: float = 250,
        max_daily_loss: float = 100,
        capital:        float = 5000,
        crypto_alloc:   float = 0.30,
        max_positions:  int   = 2,
        user_id:        int   = None,
    ):
        self.broker          = broker
        self.target_min      = target_min
        self.target_desired  = target_desired
        self.target_stretch  = target_stretch
        self.max_daily_loss  = max_daily_loss
        self.capital         = capital
        self.crypto_alloc    = crypto_alloc
        self.allocated_capital = capital * crypto_alloc
        self.max_positions   = max_positions

        # Analysis engine (reuse existing BounceAnalyzer)
        self.analyzer = BounceAnalyzer()

        # State — mirror CryptoEngine interface
        self.state              = EngineState.IDLE
        self.realized_pnl       = 0.0
        self.locked_floor       = None
        self.open_positions: Dict[str, CryptoPosition] = {}
        self.compounded_gains   = 0.0
        self.stop_reason        = None
        self._last_error        = None
        self.last_account_state = {}
        self.cycle_count        = 0
        self.last_refresh       = 0
        self.trades_today       = 0
        self._scan_results      = []
        self._user_id           = user_id or 1
        self._reporter          = None
        self._last_scan_time    = 0
        self._last_analysis     = {}

        # Milestone / profit lock (same as CryptoEngine)
        self.milestone_size_pct = 1.0
        self.milestone_label    = ""
        self._milestones = [
            {"threshold": 400, "floor_pct": 0.953, "size_pct": 0.00, "label": "🏆 $400 — Exits only"},
            {"threshold": 300, "floor_pct": 0.950, "size_pct": 0.40, "label": "🥇 $300 — 40% size"},
            {"threshold": 200, "floor_pct": 0.950, "size_pct": 0.50, "label": "🥈 $200 — 50% size"},
            {"threshold": 150, "floor_pct": 0.953, "size_pct": 0.60, "label": "🥉 $150 — 60% size"},
            {"threshold": 100, "floor_pct": 0.950, "size_pct": 0.75, "label": "✅ $100 — 75% size"},
        ]

        # Self-learning (mirror CryptoEngine)
        self.coin_stats: Dict[str, dict] = {}
        self.consecutive_losses  = 0
        self.last_trade_was_loss = False

    def set_milestones(self, milestones: list):
        if milestones:
            self._milestones = sorted(milestones, key=lambda x: x["threshold"], reverse=True)

    # ── Account helpers (same as CryptoEngine) ────────────────────────────────

    def refresh_account(self) -> dict:
        try:
            acct = self.broker.get_account()
            self.last_account_state = acct
            self.last_refresh = time.time()
            return acct
        except Exception as e:
            logger.error(f"BounceEngine.refresh_account: {e}")
            return self.last_account_state

    def get_non_marginable_buying_power(self) -> float:
        acct   = self.refresh_account()
        nmbp   = float(acct.get("non_marginable_buying_power") or acct.get("cash", 0))
        budget = self.capital * self.crypto_alloc
        open_cost = sum(pos.qty * pos.entry for pos in self.open_positions.values())
        return round(max(0, min(nmbp, budget) - open_cost), 2)

    def wait_for_fill(self, order_id: str, timeout: int = 30) -> bool:
        for _ in range(timeout):
            try:
                order = self.broker.trading.get_order_by_id(order_id)
                if order.status == "filled":
                    return True
                if order.status in ("cancelled", "rejected", "expired"):
                    return False
            except Exception:
                pass
            time.sleep(1)
        return False

    # ── P&L / stop checks ─────────────────────────────────────────────────────

    def remaining_to_min(self)     -> float: return max(0, self.target_min - self.realized_pnl)
    def remaining_to_desired(self) -> float: return max(0, self.target_desired - self.realized_pnl)
    def remaining_to_stretch(self) -> float: return max(0, self.target_stretch - self.realized_pnl)

    def check_profit_lock(self):
        pnl = self.realized_pnl
        for m in self._milestones:
            threshold = m["threshold"]
            floor_pct = m.get("floor_pct", 0.95)
            size_pct  = m.get("size_pct", 0.5)
            label     = m.get("label", f"${threshold}")
            if pnl >= threshold:
                new_floor = round(threshold * floor_pct, 2)
                if self.locked_floor is None or new_floor > self.locked_floor:
                    self.locked_floor      = new_floor
                    self.milestone_size_pct = size_pct
                    self.milestone_label    = label
                    logger.info(f"🎯 BOUNCE MILESTONE: {label} | floor=${new_floor}")
                break
        # Continuous trailing
        if self.locked_floor is not None and pnl > (self.locked_floor / 0.95):
            candidate = round(pnl * 0.95, 2)
            if candidate > self.locked_floor:
                self.locked_floor = candidate

    def get_size_multiplier(self) -> float:
        return getattr(self, 'milestone_size_pct', 1.0)

    def is_exits_only_mode(self) -> bool:
        return getattr(self, 'milestone_size_pct', 1.0) == 0.0

    def should_stop(self) -> Optional[str]:
        pnl = self.realized_pnl
        if pnl <= -self.max_daily_loss:
            return f"Max daily loss reached: ${pnl:.2f}"
        if self.locked_floor is not None and pnl < self.locked_floor:
            return f"Trailing floor triggered — P&L ${pnl:.2f} < floor ${self.locked_floor:.2f}"
        nbp = self.get_non_marginable_buying_power()
        if nbp < 50:
            return f"Buying power too low: ${nbp:.2f}"
        return None

    # ── Self-learning ─────────────────────────────────────────────────────────

    def _update_coin_stats(self, ticker: str, pnl: float):
        if ticker not in self.coin_stats:
            self.coin_stats[ticker] = {
                "wins": 0, "losses": 0, "total_pnl": 0.0,
                "loss_streak": 0, "skip_until": 0,
            }
        s = self.coin_stats[ticker]
        s["total_pnl"] += pnl
        if pnl > 0:
            s["wins"] += 1
            s["loss_streak"] = 0
            self.consecutive_losses = 0
            self.last_trade_was_loss = False
        else:
            s["losses"] += 1
            s["loss_streak"] += 1
            self.consecutive_losses += 1
            self.last_trade_was_loss = True
            if s["loss_streak"] >= 2:
                cooldown_min = min(60, s["loss_streak"] * 10)
                s["skip_until"] = time.time() + cooldown_min * 60
                logger.info(f"🧠 Bounce {ticker}: {s['loss_streak']}-loss streak — cooling {cooldown_min}m")

    # ── Confidence-scaled position sizing ─────────────────────────────────────

    def calculate_bounce_size(self, analysis: dict, llm_rec: dict) -> dict:
        """
        Size a bounce trade based on confidence.
        Higher confidence → bigger position (linear scale 50%-100% of max).
        """
        price = analysis.get("price", 0)
        if price <= 0:
            return {"qty": 0, "reason": "Invalid price"}

        available = self.get_non_marginable_buying_power()
        if available < 10:
            return {"qty": 0, "reason": f"Insufficient cash: ${available:.2f}"}

        entry_exit = analysis.get("entry_exit", {})
        stop_price   = entry_exit.get("stop", price * 0.995)
        target_price = entry_exit.get("target_conservative", price * 1.005)

        stop_dist = abs(price - stop_price)
        if stop_dist < price * 0.001:
            stop_dist = price * 0.003  # minimum 0.3% stop

        # Confidence scaling: 0.65 → 50% of max, 1.0 → 100% of max
        confidence  = float(llm_rec.get("confidence", 0.65))
        conf_scale  = 0.5 + (confidence - 0.65) / (1.0 - 0.65) * 0.5
        conf_scale  = max(0.5, min(1.0, conf_scale))

        # Milestone reduction
        size_mult = self.get_size_multiplier()

        # Max spend: 40% of available × confidence × milestone
        max_spend = available * 0.40 * conf_scale * size_mult
        bp_units  = max_spend / price if price > 0 else 0

        # Risk-based: max 0.5% of capital per trade
        max_risk_usd = self.capital * 0.005
        risk_units   = max_risk_usd / stop_dist if stop_dist > 0 else 0

        qty  = min(bp_units, risk_units)
        qty  = max(0.01, round(qty, 4))
        cost = qty * price

        if cost > available:
            qty  = round((available * 0.95) / price, 4)
            cost = qty * price

        if cost > available:
            return {"qty": 0, "reason": f"Cost ${cost:.2f} > available ${available:.2f}"}

        expected_pnl = qty * abs(target_price - price)
        if expected_pnl < 0.10:
            return {"qty": 0, "reason": f"Expected profit ${expected_pnl:.2f} too low"}

        logger.info(
            f"  Bounce sized {analysis['ticker']}: qty={qty:.4f} "
            f"cost=${cost:.2f} conf={confidence:.0%}→scale={conf_scale:.0%} "
            f"stop=${stop_price:.4f} target=${target_price:.4f}"
        )

        return {
            "qty":        qty,
            "cost":       round(cost, 2),
            "stop":       round(stop_price, 6),
            "target":     round(target_price, 6),
            "stop_dist":  round(stop_dist, 6),
            "exp_profit": round(expected_pnl, 2),
            "conf_scale": round(conf_scale, 2),
            "reason":     "sized",
        }

    # ── Main cycle ────────────────────────────────────────────────────────────

    async def run_cycle(self) -> dict:
        """One full bounce trading cycle."""
        self.cycle_count += 1

        if self.state == EngineState.ERROR:
            self.state = EngineState.IDLE

        # Check stops
        stop_reason = self.should_stop()
        if stop_reason:
            self.state       = EngineState.STOPPED
            self.stop_reason = stop_reason
            logger.info(f"BounceEngine STOPPED: {stop_reason}")
            return self.status()

        # Manage open positions first
        await self._manage_positions()

        # Skip scan if at max positions
        if len(self.open_positions) >= self.max_positions:
            return self.status()

        # Profit lock check
        self.check_profit_lock()

        if self.is_exits_only_mode():
            await self._manage_positions()
            return self.status()

        # Rate-limit analysis (every SCAN_INTERVAL_SEC)
        now = time.time()
        if now - self._last_scan_time < self.SCAN_INTERVAL_SEC and self._last_analysis:
            # Use cached analysis, just check for entries
            pass
        else:
            # Run full bounce analysis
            self.state = EngineState.SCANNING
            try:
                self._last_analysis = await self.analyzer.analyze_all(
                    self.broker, list(ALPACA_TRADEABLE), use_llm=True
                )
                self._last_scan_time = now
                logger.info(f"🔄 Bounce scan complete: {len(self._last_analysis)} coins analyzed")
            except Exception as e:
                logger.error(f"Bounce scan error: {e}")
                self.state = EngineState.IDLE
                return self.status()

        # Build scan results for UI
        self._scan_results = [
            {
                "symbol":       f"{t}/USD",
                "score":        round(a.get("bounce_score", 0), 0),
                "prob":         round(a.get("confidence", 0) * 100, 0),
                "valid":        self._is_actionable(a),
                "price":        a.get("price", 0),
                "momentum":     0,  # bounce doesn't use momentum the same way
            }
            for t, a in list(self._last_analysis.items())[:8]
        ]

        # Find actionable setups
        already_held = set(sym.split("/")[0] for sym in self.open_positions)
        actionable = []
        for ticker, analysis in self._last_analysis.items():
            if ticker in already_held:
                continue
            if self._is_actionable(analysis):
                actionable.append((ticker, analysis))

        if not actionable:
            self.state = EngineState.IDLE
            return self.status()

        # Sort by bounce_score descending, trade the best one
        actionable.sort(key=lambda x: x[1]["bounce_score"], reverse=True)
        ticker, analysis = actionable[0]
        llm_rec = analysis.get("llm_recommendation", {})

        logger.info(
            f"🎯 Bounce trade: {ticker} score={analysis['bounce_score']:.0f} "
            f"LLM={llm_rec.get('action')} conf={llm_rec.get('confidence', 0):.0%}"
        )

        # Size it
        self.state = EngineState.SIZING
        sizing = self.calculate_bounce_size(analysis, llm_rec)
        if sizing["qty"] <= 0:
            logger.info(f"Bounce sizing rejected: {sizing.get('reason')}")
            self.state = EngineState.IDLE
            return self.status()

        # Execute
        await self._execute_entry(ticker, analysis, llm_rec, sizing)
        return self.status()

    def _is_actionable(self, analysis: dict) -> bool:
        """Check if a bounce analysis meets all entry criteria."""
        score = analysis.get("bounce_score", 0)
        if score < self.MIN_BOUNCE_SCORE:
            return False

        trend_type = analysis.get("trend", {}).get("type", "unknown")
        if trend_type == "trending":
            return False  # don't fight the trend

        llm = analysis.get("llm_recommendation", {})
        if llm.get("action") != "BUY_BOUNCE":
            return False
        if float(llm.get("confidence", 0)) < self.MIN_LLM_CONFIDENCE:
            return False

        # Price near entry zone
        entry_exit = analysis.get("entry_exit", {})
        dist = entry_exit.get("entry_zone", {}).get("dist_to_entry_pct", 99)
        if dist > self.MAX_ENTRY_DIST_PCT:
            return False

        # Check cooldown
        ticker = analysis.get("ticker", "")
        s = self.coin_stats.get(ticker, {})
        if time.time() < s.get("skip_until", 0):
            return False

        return True

    # ── Trade execution ───────────────────────────────────────────────────────

    async def _execute_entry(self, ticker: str, analysis: dict,
                              llm_rec: dict, sizing: dict):
        """Place a bounce buy order."""
        self.state = EngineState.ORDER_PENDING
        symbol     = f"{ticker}/USD"
        qty        = sizing["qty"]

        try:
            order = self.broker.place_market_order(ticker, qty, "BUY")
            if "error" in order:
                logger.error(f"Bounce order failed: {order['error']}")
                self._last_error = order["error"]
                self.state = EngineState.IDLE
                return

            order_id = order.get("id", "")
            logger.info(f"Bounce market order: {ticker} qty={qty}")

            filled = self.wait_for_fill(order_id, timeout=20)
            if not filled:
                logger.warning(f"Bounce order {order_id} not filled")
                self.state = EngineState.IDLE
                return

            # Get fill price
            actual_price = analysis["price"]
            try:
                order_obj = self.broker.trading.get_order_by_id(order_id)
                if order_obj.filled_avg_price:
                    actual_price = float(order_obj.filled_avg_price)
            except Exception:
                pass

            # Use analyzer's stop/target, anchored to fill price
            entry_exit = analysis.get("entry_exit", {})
            stop_dist  = abs(actual_price - entry_exit.get("stop", actual_price * 0.997))
            if stop_dist < actual_price * 0.001:
                stop_dist = actual_price * 0.003

            target_dist = abs(entry_exit.get("target_conservative", actual_price * 1.005) - analysis["price"])
            if target_dist < actual_price * 0.001:
                target_dist = actual_price * 0.005

            stop   = round(actual_price - stop_dist, 6)
            target = round(actual_price + target_dist, 6)

            logger.info(
                f"Bounce fill: {ticker} @ ${actual_price:.4f} | "
                f"stop=${stop:.4f} target=${target:.4f} R:R={(target_dist/stop_dist):.2f}"
            )

            # Refresh account
            self.state = EngineState.FUNDS_REFRESHING
            self.refresh_account()

            # Record position
            self.state = EngineState.POSITION_OPEN
            pos = CryptoPosition(
                symbol=symbol, side="BUY", qty=qty,
                entry=actual_price, stop=stop, target=target,
                order_id=order_id,
            )
            self.open_positions[symbol] = pos
            self.trades_today += 1

            logger.info(
                f"✅ Bounce position: {symbol} qty={qty} "
                f"entry=${actual_price:.4f} stop=${stop:.4f} target=${target:.4f}"
            )

            # Save to DB + activity feed
            self._save_open_trade(ticker, pos, analysis, llm_rec)

        except Exception as e:
            logger.error(f"BounceEngine order error: {e}")
            self._last_error = str(e)
            self.state = EngineState.ERROR

    def _save_open_trade(self, ticker, pos, analysis, llm_rec):
        try:
            from database.database import SessionLocal
            from services.trade_service import TradeService
            db      = SessionLocal()
            svc     = TradeService(db=db, user_id=self._user_id)
            db_trade = svc.open_trade(
                symbol       = ticker,
                side         = "BUY",
                qty          = pos.qty,
                entry_price  = float(pos.entry),
                stop_loss    = float(pos.stop),
                take_profit  = float(pos.target),
                confidence   = float(llm_rec.get("confidence", 0)),
                signal_reasons = [
                    f"Bounce trade | score={analysis.get('bounce_score',0):.0f} "
                    f"| {llm_rec.get('reasoning','')}"
                ],
                order_id     = pos.order_id,
            )
            pos.db_trade_id = db_trade.id
            db.close()
            _reporter = getattr(self, '_reporter', None)
            if _reporter:
                _reporter.log_entry(ticker, "BUY", pos.qty, float(pos.entry),
                                    float(pos.stop), float(pos.target),
                                    float(llm_rec.get("confidence", 0)))
        except Exception as e:
            logger.warning(f"Bounce DB save error: {e}")

    # ── Position management (same trailing stop logic as CryptoEngine) ────────

    async def _manage_positions(self):
        for sym, pos in list(self.open_positions.items()):
            ticker = sym.split("/")[0]
            try:
                current_price = 0.0
                if hasattr(self.broker, "get_latest_crypto_price"):
                    current_price = self.broker.get_latest_crypto_price(ticker)
                if current_price <= 0:
                    current_price = self.broker.get_latest_price(ticker)
                if current_price <= 0:
                    continue

                upnl     = pos.unrealized_pnl(current_price)
                held_min = (datetime.now(timezone.utc) - pos.opened_at).total_seconds() / 60

                # Update trailing stop
                pos.update_trailing_stop(current_price)

                should_exit = False
                exit_reason = ""

                if current_price <= pos.trail_stop and pos.profit_locked:
                    should_exit = True
                    exit_reason = f"Trailing stop ${pos.trail_stop:.4f} | P&L ${upnl:+.2f}"
                elif current_price <= pos.stop and not pos.profit_locked:
                    should_exit = True
                    exit_reason = f"Stop loss ${pos.stop:.4f} | P&L ${upnl:+.2f}"
                elif current_price >= pos.target:
                    should_exit = True
                    exit_reason = f"Target hit ${pos.target:.4f} | P&L ${upnl:+.2f} ✅"
                elif held_min >= self.MAX_HOLD_MIN:
                    should_exit = True
                    exit_reason = f"Time stop {held_min:.0f}m | P&L ${upnl:+.2f}"

                if should_exit:
                    logger.info(f"🚪 Bounce exit {sym}: {exit_reason}")
                    await self._exit_position(sym, pos, current_price, exit_reason)

            except Exception as e:
                logger.error(f"Bounce manage {sym}: {e}")

    async def _exit_position(self, sym: str, pos: CryptoPosition,
                              price: float, reason: str):
        self.state = EngineState.EXIT_PENDING
        ticker     = sym.split("/")[0]
        try:
            self.broker.close_position(ticker)

            self.state = EngineState.FUNDS_REFRESHING
            self.refresh_account()

            pnl = pos.unrealized_pnl(price)
            self.realized_pnl += pnl
            if pnl > 0:
                self.compounded_gains += pnl

            self._update_coin_stats(ticker, pnl)
            del self.open_positions[sym]
            self.state = EngineState.READY_FOR_REENTRY
            logger.info(f"Bounce exit {sym}: {reason} | P&L ${pnl:+.2f} | Total ${self.realized_pnl:.2f}")

            # Save to DB
            try:
                from database.database import SessionLocal
                from services.trade_service import TradeService
                db  = SessionLocal()
                svc = TradeService(db=db, user_id=self._user_id)
                trade_id = getattr(pos, "db_trade_id", None)
                if trade_id:
                    svc.close_trade(trade_id=trade_id, exit_price=price, reason=reason)
                else:
                    from database.models import Trade
                    from datetime import date as _date
                    t = Trade(
                        user_id=self._user_id, symbol=ticker, side="BUY",
                        qty=pos.qty, entry_price=pos.entry, exit_price=price,
                        pnl=round(pnl, 2), net_pnl=round(pnl, 2),
                        status="closed", trade_date=str(_date.today()),
                        opened_at=pos.opened_at, setup_type="crypto_bounce",
                    )
                    db.add(t)
                    db.commit()
                db.close()
                _reporter = getattr(self, '_reporter', None)
                if _reporter:
                    _reporter.log_exit(ticker, "BUY", pos.qty,
                                       pos.entry, price, pnl, reason)
            except Exception as e:
                logger.warning(f"Bounce DB close error: {e}")

        except Exception as e:
            logger.error(f"Bounce exit {sym}: {e}")

    # ── Status (same shape as CryptoEngine for UI compatibility) ──────────────

    def status(self) -> dict:
        import math

        bp_raw = float(self.last_account_state.get("non_marginable_buying_power",
                       self.last_account_state.get("cash", 0))) if self.last_account_state else 0.0
        budget = round(self.capital * self.crypto_alloc, 2)

        coin_summary = {}
        for ticker, s in self.coin_stats.items():
            total = s["wins"] + s["losses"]
            coin_summary[ticker] = {
                "wins":       s["wins"],
                "losses":     s["losses"],
                "win_rate":   round(s["wins"] / total * 100, 1) if total > 0 else 0,
                "total_pnl":  round(s["total_pnl"], 2),
                "loss_streak": s["loss_streak"],
            }

        return {
            "engine_type":       "bounce",
            "state":             self.state.value,
            "realized_pnl":      round(self.realized_pnl, 2),
            "compounded_gains":  round(self.compounded_gains, 2),
            "locked_floor":      round(self.locked_floor, 2) if self.locked_floor else None,
            "milestone_size_pct": self.milestone_size_pct,
            "milestone_label":   self.milestone_label,
            "exits_only_mode":   self.is_exits_only_mode(),
            "remaining_to_min":  round(self.remaining_to_min(), 2),
            "remaining_to_desired": round(self.remaining_to_desired(), 2),
            "open_positions":    len(self.open_positions),
            "trades_today":      self.trades_today,
            "stop_reason":       self.stop_reason,
            "last_error":        self._last_error,
            "cycle":             self.cycle_count,
            "consecutive_losses": self.consecutive_losses,
            "buying_power":      round(min(bp_raw, budget), 2) if bp_raw else budget,
            "crypto_budget":     budget,
            "coin_stats":        coin_summary,
            "scan_results":      self._scan_results,
            "open_position_list": [
                {
                    "symbol": sym, "qty": float(pos.qty),
                    "entry": float(pos.entry), "stop": float(pos.stop),
                    "target": float(pos.target), "side": str(pos.side),
                }
                for sym, pos in self.open_positions.items()
            ],
        }
