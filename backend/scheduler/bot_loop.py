"""
Bot loop v3
• Watchlist always synced from settings_manager (user's saved list)
• Dynamic mode truly scans market — user's custom symbols ADDED to the result
• Manual mode queues trades for approval
"""
import asyncio
import logging
from datetime import datetime

import pytz

import config
from broker.alpaca_client    import AlpacaClient
from data.dynamic_watchlist  import DynamicWatchlistBuilder
from data.settings_manager   import SettingsManager
from models.ensemble         import EnsembleModel
from strategy.daily_target   import DailyTargetTracker
from strategy.engine         import StrategyEngine
from strategy.risk_manager   import DynamicRiskManager

logger = logging.getLogger(__name__)
ET     = pytz.timezone("America/New_York")


class BotLoop:
    def __init__(self, tracker: DailyTargetTracker, user_id: int = None):
        self.tracker       = tracker
        self.status        = "stopped"
        self.mode          = "paper"
        self.trading_mode  = "auto"
        # Per-user ownership. None = legacy/system bot (.env admin fallback).
        self.user_id       = user_id

        self._wl_builder   = DynamicWatchlistBuilder()
        self._dynamic_mode = True  # Default ON — AI scans 100+ stocks for real movers

        # Always load from settings file so user changes persist
        self._settings     = SettingsManager()
        self.watchlist     = self._settings.get_watchlist()

        self.broker        = None
        self.risk          = DynamicRiskManager()
        self.ensemble      = EnsembleModel()
        self.engine        = None
        self._task         = None

        self._pending_trades: list = []
        self._unusual_volume: list = []
        # Cooldown: symbol → datetime when it becomes eligible again
        # After a trail exit / harvest close, block re-entry for 30 min
        self._cooldowns: dict = {}
        # Peak unrealized tracking for drawdown guard
        self._peak_unrealized: float = 0.0
        self._unrealized_pause_until: float = 0.0  # timestamp
        # HARD breach flag — once set, NO trading until manually restarted
        self._floor_breached: bool = False

    # ── Control ───────────────────────────────────────────────────────────────

    async def start(self, mode: str = "paper", trading_mode: str = "auto", user=None):
        """Start this user's bot.

        If `user` is provided, load their saved broker credentials and
        trade against their own Alpaca account. If `user` is None, the bot
        falls back to the .env admin creds (system=True) — this path is
        reserved for legacy or background system usage and its broker
        must never be surfaced to user-facing endpoints.

        Every step is timed + logged so stuck startups are easy to diagnose
        from pm2 logs. Look for lines prefixed with `bot.start[uid=N]`.
        """
        import time as _time
        uid_tag = f"uid={getattr(user, 'id', None)}"
        t_enter = _time.time()
        logger.info(
            f"bot.start[{uid_tag}] ▶ entry mode={mode} "
            f"trading_mode={trading_mode} current_status={self.status}"
        )

        if self.status == "running":
            logger.info(f"bot.start[{uid_tag}] already running — no-op")
            return
        # Clear breach flag on manual restart — user acknowledges the breach
        self._floor_breached = False
        # ALWAYS check equity vs floor at start time — if equity is below
        # the locked floor, reset the floor so the bot doesn't immediately
        # stop itself. The user pressing Start = acknowledging the situation.
        try:
            from database.database import SessionLocal as _SL2
            from services import protection_service
            with _SL2() as _breach_db:
                _uid = self.user_id or (user.id if user else None)
                if _uid:
                    settings = protection_service.get_or_create(_breach_db, _uid)
                    if settings.enabled and float(settings.floor_value or 0) > 0 and user:
                        # Build broker with user's creds to get live equity
                        from broker.broker_routes import _load_creds
                        _c = _load_creds(user)
                        if _c and _c.get("api_key"):
                            _tmp_broker = AlpacaClient(
                                api_key=_c["api_key"],
                                api_secret=_c.get("api_secret", ""),
                                paper=_c.get("paper", True)
                            )
                            _acct = _tmp_broker.get_account()
                            _eq = float(_acct.get("equity", 0))
                            _floor = float(settings.floor_value or 0)
                            if _eq > 0 and _eq < _floor:
                                new_floor = _eq * 0.99
                                logger.warning(
                                    f"bot.start[{uid_tag}] equity ${_eq:.2f} < floor ${_floor:.2f} "
                                    f"— resetting floor to ${new_floor:.2f}"
                                )
                                settings.floor_value = new_floor
                                _breach_db.commit()
                            else:
                                logger.info(
                                    f"bot.start[{uid_tag}] floor OK: equity ${_eq:.2f} >= floor ${_floor:.2f}"
                                )
        except Exception as e:
            logger.warning(f"bot.start[{uid_tag}] floor check at start failed: {e}")
        # Refresh watchlist from settings before starting
        self.watchlist    = self._settings.get_watchlist()
        self.mode         = mode
        self.trading_mode = trading_mode
        logger.info(
            f"bot.start[{uid_tag}] watchlist loaded "
            f"({len(self.watchlist)} syms) +{_time.time()-t_enter:.2f}s"
        )

        if user is not None:
            # Per-user bot: require explicit saved creds. No .env fallback.
            t0 = _time.time()
            from broker.broker_routes import _load_creds
            creds = _load_creds(user)
            logger.info(
                f"bot.start[{uid_tag}] creds loaded +{_time.time()-t0:.2f}s "
                f"(has_key={bool(creds and creds.get('api_key'))})"
            )
            if not creds or not creds.get("api_key"):
                raise ValueError(
                    "NO_BROKER: Connect your Alpaca account in the My Broker "
                    "tab before starting the bot."
                )
            t0 = _time.time()
            self.broker = AlpacaClient(
                paper      = (mode == "paper"),
                api_key    = creds["api_key"],
                api_secret = creds["api_secret"],
            )
            logger.info(
                f"bot.start[{uid_tag}] AlpacaClient constructed "
                f"+{_time.time()-t0:.2f}s"
            )
            # Scope tracker DB reads to this user's trades only
            try:
                self.tracker.user_id = user.id
            except Exception:
                pass
            self.user_id = user.id
        else:
            # Legacy/system bot — .env creds (admin-scoped). Do NOT surface
            # this broker to user endpoints.
            t0 = _time.time()
            self.broker = AlpacaClient(paper=(mode == "paper"), system=True)
            logger.info(
                f"bot.start[{uid_tag}] AlpacaClient (system) constructed "
                f"+{_time.time()-t0:.2f}s"
            )

        t0 = _time.time()
        self.engine       = StrategyEngine(self.broker, self.tracker, self.risk, self.ensemble, user_id=self.user_id)
        logger.info(
            f"bot.start[{uid_tag}] StrategyEngine constructed "
            f"+{_time.time()-t0:.2f}s"
        )
        self.status       = "running"

        # ── Enable dynamic watchlist scanning by default ──
        self._wl_builder.set_mode(self._dynamic_mode)
        self._wl_builder.set_manual_list(self.watchlist)
        logger.info(
            f"bot.start[{uid_tag}] Dynamic watchlist: {'ON (AI scans 100+ stocks)' if self._dynamic_mode else 'OFF (manual only)'}"
        )

        # ── Restore today's P&L from DB so restarts don't lose progress ──
        t0 = _time.time()
        self.tracker.load_from_db()
        logger.info(
            f"bot.start[{uid_tag}] tracker.load_from_db "
            f"+{_time.time()-t0:.2f}s realized=${self.tracker.realized_pnl:.2f}"
        )
        self.tracker.record_session_start()

        # ── Auto-enable profit protection so user never trades unprotected ──
        try:
            from database.database  import SessionLocal
            from services           import protection_service
            with SessionLocal() as db:
                ps = protection_service.get_or_create(db, self.user_id or 1)
                # Ensure protection + ladder are always ON at start
                if not ps.enabled:
                    ps.enabled = True
                if not ps.ladder_enabled:
                    ps.ladder_enabled = True
                if not ps.scaleout_enabled:
                    ps.scaleout_enabled = True
                db.commit()
                logger.info(
                    f"bot.start[{uid_tag}] Protection auto-enabled: "
                    f"floor=${float(ps.floor_value):.2f}, ladder=ON, scaleout=ON"
                )
        except Exception as e:
            logger.warning(f"bot.start[{uid_tag}] protection init: {e}")

        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"bot.start[{uid_tag}] ✅ READY total=+{_time.time()-t_enter:.2f}s | "
            f"Broker={mode.upper()} | Trading={trading_mode.upper()} | "
            f"Restored P&L=${self.tracker.realized_pnl:.2f} | "
            f"ML={'trained' if self.ensemble.is_trained else 'untrained (will train on first cycle)'} | "
            f"Watchlist={self.watchlist}"
        )

    async def stop(self):
        self.tracker.record_session_stop()
        self.status = "stopped"
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.engine:
            await self.engine.close_all_eod()
        # Finalize today's DailyPnL rows for any user with activity today
        try:
            from database.database  import SessionLocal
            from database.models    import Trade, DailyPnL
            from services           import daily_pnl_service as _dpnl
            from datetime           import date
            today_str = date.today().strftime("%Y-%m-%d")
            with SessionLocal() as db:
                # Collect user_ids that either traded today or already have a
                # row started for today — so we don't miss anyone.
                active_user_ids = {
                    uid for (uid,) in db.query(Trade.user_id)
                                        .filter(Trade.trade_date == today_str)
                                        .distinct().all()
                } | {
                    uid for (uid,) in db.query(DailyPnL.user_id)
                                        .filter(DailyPnL.trade_date == today_str)
                                        .distinct().all()
                }
                for uid in active_user_ids:
                    try:
                        _dpnl.finalize_day(db, uid, broker=self.broker)
                    except Exception as e:
                        logger.warning(f"finalize_day({uid}) skipped: {e}")
        except Exception as e:
            logger.warning(f"DailyPnL finalize-on-stop skipped: {e}")

    def set_trading_mode(self, mode: str):
        self.trading_mode = mode

    def set_watchlist_dynamic(self, enabled: bool):
        self._dynamic_mode = enabled
        self._wl_builder.set_mode(enabled)

    def refresh_watchlist(self):
        """Call this whenever user updates watchlist in settings."""
        self.watchlist = self._settings.get_watchlist()
        self._wl_builder.set_manual_list(self.watchlist)
        logger.info(f"Watchlist refreshed from settings: {self.watchlist}")

    def approve_pending_trade(self, symbol: str):
        trade = next((t for t in self._pending_trades if t["symbol"] == symbol), None)
        if trade and self.engine:
            asyncio.create_task(self.engine._enter(symbol, trade["signal"], None))
            self._pending_trades = [t for t in self._pending_trades if t["symbol"] != symbol]

    def reject_pending_trade(self, symbol: str):
        self._pending_trades = [t for t in self._pending_trades if t["symbol"] != symbol]

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _loop(self):
        try:
            await self._train_models()
        except Exception as e:
            logger.error(f"_loop: initial training failed (non-fatal): {e}")
        logger.info("_loop: entering main trading loop")
        last_train_day  = datetime.now(ET).date()
        last_wl_day     = None
        last_harvest_ts = 0.0   # unix timestamp of last harvest tick
        last_regime_ts  = 0.0   # unix timestamp of last regime refresh

        while self.status == "running":
            try:
                now = datetime.now(ET)

                # Daily retrain
                if now.date() != last_train_day and now.hour >= 9:
                    await self._train_models()
                    last_train_day = now.date()

                if not self.broker.is_market_open():
                    logger.debug("Market closed — sleeping 60s (bot still running)")
                    await asyncio.sleep(60)
                    continue

                # Refresh market regime every 5 minutes (SPY-based)
                import time as _regime_t
                if _regime_t.time() - last_regime_ts > 300:
                    last_regime_ts = _regime_t.time()
                    if self.engine:
                        self.engine._refresh_regime()
                        regime = (self.engine._current_regime or {}).get("regime", "?")
                        logger.info(f"📊 Market regime: {regime}")

                # Rebuild dynamic watchlist every 30 minutes
                if self._dynamic_mode and self._wl_builder.needs_rebuild():
                    await self._build_dynamic_watchlist()

                # Always sync manual watchlist from settings
                if not self._dynamic_mode:
                    self.watchlist = self._settings.get_watchlist()
                    self._wl_builder.set_manual_list(self.watchlist)

                # EOD flatten
                if now.hour == 15 and now.minute >= 55:
                    await self.engine.close_all_eod()
                    await asyncio.sleep(300)
                    continue

                self.engine.sync_positions()
                positions  = self.broker.get_positions()
                unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
                self.tracker.update_unrealized(unrealized)

                # ── HARD BREACH CHECK — runs EVERY iteration, not rate-limited ──
                # If floor was already breached, close everything and stop.
                if self._floor_breached:
                    logger.warning("🛑 Floor breach flag active — closing all + stopping")
                    try:
                        for p in positions:
                            sym = p.get("symbol", "")
                            if sym:
                                self.broker.close_position(sym)
                                logger.info(f"🛑 Breach close: {sym}")
                    except Exception as e:
                        logger.warning(f"breach close-all: {e}")
                    self.status = "stopped"
                    break

                # ── Profit protection (account-level floor + harvest + breach) ──
                # The snapshot ratchets the floor automatically; here we watch
                # live equity for breaches and periodically harvest oversized
                # unrealized winners into realized so they're permanently banked.
                try:
                    import time as _t
                    now_ts = _t.time()
                    if now_ts - last_harvest_ts > 15:   # every 15s for fast protection
                        last_harvest_ts = now_ts
                        await self._run_protection_tick(positions)
                except Exception as e:
                    logger.warning(f"protection tick failed: {e}")

                should_stop, reason = self.tracker.should_stop()
                if should_stop:
                    logger.info(f"Stop: {reason}")
                    await asyncio.sleep(300)
                    continue

                # Active watchlist: dynamic or user's saved list
                if self._dynamic_mode and self._wl_builder._dynamic_list:
                    active_wl = self._wl_builder.get_active_list()
                    # Always append user's custom symbols too
                    user_syms = self._settings.get_watchlist()
                    active_wl = list(dict.fromkeys(active_wl + user_syms))
                else:
                    active_wl = self._settings.get_watchlist()

                # Floor breach — do NOT scan for new trades
                if self._floor_breached:
                    break

                # Check if we're in a drawdown pause
                import time as _t2
                if _t2.time() < self._unrealized_pause_until:
                    logger.info("⏸️ Drawdown pause active — skipping new entries")
                    await asyncio.sleep(config.SCAN_INTERVAL)
                    continue

                for symbol in active_wl:
                    if self.status != "running":
                        break
                    # Skip symbols in cooldown (recently exited by protection)
                    if self._is_cooled_down(symbol):
                        continue
                    try:
                        sig = await self.engine.scan_symbol(symbol)

                        if sig.get("volume_ratio", 1) > 2.5:
                            self._add_unusual_volume(symbol, sig)

                        if (self.trading_mode == "manual" and
                                sig.get("signal") in ("BUY","SELL") and
                                sig.get("confidence", 0) >= config.MIN_CONFIDENCE_SCORE):
                            self._queue_pending(symbol, sig)

                    except Exception as e:
                        logger.error(f"scan({symbol}): {e}")

                await asyncio.sleep(config.SCAN_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(10)

        # If we get here, the loop exited — log it
        logger.warning(f"_loop exited — status={self.status}, floor_breached={self._floor_breached}")

    # ── Dynamic watchlist — truly market-driven ───────────────────────────────

    async def _build_dynamic_watchlist(self):
        """Rebuild watchlist from live market movers every 30 minutes."""
        try:
            from data.market_scanner import MarketScanner
            from data.news_scanner   import NewsScanner

            mkt  = MarketScanner()
            news = NewsScanner()

            logger.info("Rebuilding dynamic watchlist from live market...")
            mkt._last_scan = 0   # force fresh scan
            scan    = await mkt.scan()
            gainers = scan.get("gainers",    [])
            actives = scan.get("most_active",[])

            logger.info(f"Market: {len(gainers)} gainers, {len(actives)} actives")

            sigs      = self.engine.get_signals() if self.engine else []
            user_syms = self._settings.get_watchlist()
            all_syms  = list(dict.fromkeys(
                [g["symbol"] for g in gainers] +
                [a["symbol"] for a in actives] +
                user_syms
            ))[:30]

            try:
                sent = await news.scan_watchlist(all_syms)
            except Exception:
                sent = {}

            await self._wl_builder.build(scan, sent, sigs)
            logger.info(f"Dynamic watchlist: {self._wl_builder._dynamic_list[:10]}")
        except Exception as e:
            logger.error(f"dynamic_watchlist: {e}")
            self._wl_builder._dynamic_list = self._settings.get_watchlist()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _queue_pending(self, symbol: str, sig: dict):
        if symbol not in [t["symbol"] for t in self._pending_trades]:
            self._pending_trades.append({
                "symbol":    symbol,
                "signal":    sig,
                "queued_at": datetime.now(ET).isoformat(),
            })

    def _is_cooled_down(self, symbol: str) -> bool:
        """Check if a symbol is in cooldown (recently exited by ladder/harvest)."""
        until = self._cooldowns.get(symbol)
        if until and datetime.now(ET) < until:
            return True  # still cooling down
        if until:
            del self._cooldowns[symbol]  # expired, clean up
        return False

    def _set_cooldown(self, symbol: str, minutes: int = 30):
        """Block re-entry on a symbol for N minutes after protective exit."""
        from datetime import timedelta
        self._cooldowns[symbol] = datetime.now(ET) + timedelta(minutes=minutes)
        logger.info(f"🧊 Cooldown set: {symbol} blocked for {minutes}min")

    def _add_unusual_volume(self, symbol: str, sig: dict):
        if symbol not in [a["symbol"] for a in self._unusual_volume]:
            self._unusual_volume.append({
                "symbol":       symbol,
                "volume_ratio": sig.get("volume_ratio", 0),
                "signal":       sig.get("signal", "HOLD"),
                "confidence":   sig.get("confidence", 0),
                "price":        sig.get("price", 0),
                "timestamp":    datetime.now(ET).isoformat(),
            })
            self._unusual_volume = self._unusual_volume[-20:]

    async def _run_protection_tick(self, positions: list):
        """Run one protection cycle: harvest big winners + check floor breach.

        Runs at most once/minute (rate-limited by the caller). Safe against
        transient errors — never takes down the scan loop.
        """
        from database.database  import SessionLocal
        from services           import protection_service, ladder_service, daily_pnl_service

        user_id = self.user_id or 1  # per-user; fallback to 1 only for legacy system bot
        try:
            with SessionLocal() as db:
                # 1-pre) Snapshot + ratchet — MUST run in the bot tick itself,
                #        not only when the UI polls /dashboard/today. Previously
                #        the floor only ratcheted up when the user's browser
                #        happened to fetch the endpoint, so a closed winner
                #        at 11:30 wouldn't raise the floor until the next poll
                #        (or never, if the user wasn't watching). Now every
                #        15s protection tick re-computes compound realized
                #        and lifts the floor to its new milestone.
                try:
                    daily_pnl_service.snapshot_today(db, user_id, broker=self.broker)
                except Exception as _sn_e:
                    logger.warning(f"snapshot/ratchet in protection tick: {_sn_e}")

                # 1a) Ladder tick — per-position peak tracking, trail exits,
                #     partial scale-outs. Runs FIRST because it's more
                #     granular than harvest (trails fire before +8% threshold
                #     most of the time, and scale-outs preserve runners).
                try:
                    ladder_result = ladder_service.run_ladder_tick(db, user_id, self.broker)
                    for act in ladder_result.get("actions", []):
                        logger.info(
                            f"🪜 Ladder {act['action']}: {act['symbol']} — {act['reason']}"
                        )
                        # Set cooldown on exited symbols — wait for fresh momentum
                        if act["action"] in ("trail_exit", "scale_out"):
                            self._set_cooldown(act["symbol"], minutes=30)
                except Exception as e:
                    logger.warning(f"ladder_service.run_ladder_tick: {e}")

                # 1b) Harvest — coarse safety net for anything the ladder
                #     didn't catch (untracked manual positions, runaway winners
                #     above harvest_portfolio_cap, etc.)
                try:
                    result = protection_service.harvest_positions(db, user_id, self.broker)
                    harvested = result.get("harvested", [])
                    if harvested:
                        for h in harvested:
                            logger.info(f"🌾 Harvested {h['symbol']}: {h['reason']}")
                            self._set_cooldown(h["symbol"], minutes=30)
                except Exception as e:
                    logger.warning(f"harvest_positions: {e}")

                # 1c) Unrealized drawdown guard — if total floating P&L drops
                #     more than 40% from its peak, close the worst loser and
                #     pause new entries for 5 minutes.
                try:
                    import time as _t3
                    total_upnl = sum(
                        float(p.get("unrealized_pnl", 0) or 0) for p in positions
                    )
                    if total_upnl > self._peak_unrealized:
                        self._peak_unrealized = total_upnl
                    # Only guard when we've had meaningful gains (peak > $20)
                    if self._peak_unrealized > 20.0 and total_upnl > 0:
                        drawdown_pct = 1.0 - (total_upnl / self._peak_unrealized) if self._peak_unrealized > 0 else 0
                        if drawdown_pct >= 0.40:
                            logger.warning(
                                f"📉 Unrealized drawdown guard: peak ${self._peak_unrealized:.2f} "
                                f"→ now ${total_upnl:.2f} ({drawdown_pct*100:.0f}% drop). "
                                f"Closing worst loser + pausing 5min."
                            )
                            # Find and close the worst-performing position
                            worst = min(positions, key=lambda p: float(p.get("unrealized_pnl", 0) or 0))
                            worst_sym = worst.get("symbol", "")
                            if worst_sym and float(worst.get("unrealized_pnl", 0) or 0) < 0:
                                try:
                                    self.broker.close_position(worst_sym)
                                    logger.info(f"📉 Closed worst loser: {worst_sym}")
                                    self._set_cooldown(worst_sym, minutes=30)
                                except Exception as e:
                                    logger.warning(f"drawdown close {worst_sym}: {e}")
                            self._unrealized_pause_until = _t3.time() + 300  # 5 min pause
                            self._peak_unrealized = total_upnl  # reset peak to current
                except Exception as e:
                    logger.warning(f"unrealized drawdown guard: {e}")

                # 2) Snapshot + ratchet runs on the daily_pnl_service flow
                #    (called from main.py snapshot endpoints and finalize_day).
                #    Here we just read the current floor + live equity and see
                #    if we've breached.
                live_equity = 0.0
                try:
                    acct = self.broker.get_account() or {}
                    live_equity = float(acct.get("equity", 0) or 0)
                except Exception:
                    live_equity = 0.0

                if live_equity > 0:
                    breach = protection_service.check_breach(db, user_id, live_equity)
                    if breach.get("breached"):
                        logger.warning(
                            f"🛑🛑🛑 FLOOR BREACH: equity ${live_equity:.2f} < "
                            f"floor ${breach.get('floor_value', 0):.2f} "
                            f"(shortfall ${breach.get('shortfall', 0):.2f}) — "
                            f"action={breach.get('action')}"
                        )
                        # SET HARD FLAG IMMEDIATELY — stops all trading on next iteration
                        self._floor_breached = True
                        # Close all positions RIGHT NOW synchronously
                        try:
                            all_pos = self.broker.get_positions() or []
                            for p in all_pos:
                                sym = p.get("symbol", "")
                                if sym:
                                    try:
                                        self.broker.close_position(sym)
                                        logger.warning(f"🛑 Breach: closed {sym}")
                                    except Exception as e:
                                        logger.warning(f"🛑 Breach close {sym} failed: {e}")
                        except Exception as e:
                            logger.warning(f"🛑 Breach close-all failed: {e}")
                        # Stop the bot
                        self.status = "stopped"
                        logger.warning(
                            f"🛑 BOT STOPPED — floor breach. "
                            f"Equity ${live_equity:.2f} < floor ${breach.get('floor_value', 0):.2f}. "
                            f"All positions closed. Restart manually after review."
                        )
        except Exception as e:
            logger.warning(f"_run_protection_tick outer: {e}")

    def _stop_shim(self):
        """Returns an object with a synchronous `stop()` method that schedules
        our async stop() on the running event loop. Needed because the
        protection service calls bot_loop.stop() synchronously."""
        loop_self = self
        class _Shim:
            def stop(self_inner):
                try:
                    asyncio.create_task(loop_self.stop())
                except Exception:
                    loop_self.status = "stopped"
        return _Shim()

    async def _train_models(self):
        """Train ML ensemble on stock + crypto bars for better predictions."""
        from data.indicators import add_all_indicators
        trained = False
        try:
            # 1) Train on stock symbols (existing behavior)
            for symbol in (self._settings.get_watchlist() or config.DEFAULT_WATCHLIST)[:3]:
                if not self.broker:
                    break
                df = self.broker.get_bars(symbol, timeframe="5Min", limit=1000)
                if df.empty:
                    continue
                df = add_all_indicators(df)
                if self.ensemble.train(df):
                    logger.info(f"ML trained on stock {symbol} ✓")
                    trained = True
                    break
        except Exception as e:
            logger.error(f"Stock training: {e}")

        # 2) Also train on top crypto symbols so crypto engine gets ML signal
        try:
            crypto_train_symbols = ["BTC/USD", "ETH/USD"]
            for symbol in crypto_train_symbols:
                if not self.broker:
                    break
                df = self.broker.get_crypto_bars(symbol, timeframe="5Min", limit=1000)
                if df is None or df.empty:
                    continue
                df = add_all_indicators(df)
                if self.ensemble.train(df):
                    logger.info(f"ML trained on crypto {symbol} ✓")
                    trained = True
                    break
        except Exception as e:
            logger.error(f"Crypto training: {e}")

        if trained:
            logger.info(f"ML ensemble ready — is_trained={self.ensemble.is_trained}")
        else:
            logger.warning("ML training: no model trained this cycle (insufficient data)")

    def get_latest_signals(self) -> list:
        return self.engine.get_signals() if self.engine else []

    def get_live_summary(self) -> dict:
        stats     = self.tracker.stats()
        account   = self.broker.get_account() if self.broker else {}
        positions = self.broker.get_positions() if self.broker else []
        return {
            **stats,
            "bot_status":       self.status,
            "mode":             self.mode,
            "trading_mode":     self.trading_mode,
            "dynamic_watchlist": self._dynamic_mode,
            "market_regime":    (self.engine._current_regime or {}).get("regime", "unknown") if self.engine else "unknown",
            "regime_detail":    self.engine._current_regime if self.engine else None,
            "ml_trained":       self.ensemble.is_trained if self.ensemble else False,
            "account":          account,
            "positions":        positions,
            "signals":          self.get_latest_signals(),
            "pending_trades":   self._pending_trades,
            "unusual_volume":   self._unusual_volume[-10:],
            "active_watchlist": (
                self._wl_builder.get_active_list()
                if self._dynamic_mode and self._wl_builder._dynamic_list
                else self._settings.get_watchlist()
            ),
            "wl_scores": self._wl_builder.get_scores() if self._dynamic_mode else {},
        }