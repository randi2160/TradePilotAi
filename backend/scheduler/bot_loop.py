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
    def __init__(self, tracker: DailyTargetTracker):
        self.tracker       = tracker
        self.status        = "stopped"
        self.mode          = "paper"
        self.trading_mode  = "auto"

        self._wl_builder   = DynamicWatchlistBuilder()
        self._dynamic_mode = False

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

    # ── Control ───────────────────────────────────────────────────────────────

    async def start(self, mode: str = "paper", trading_mode: str = "auto"):
        if self.status == "running":
            return
        # Refresh watchlist from settings before starting
        self.watchlist    = self._settings.get_watchlist()
        self.mode         = mode
        self.trading_mode = trading_mode
        self.broker       = AlpacaClient(paper=(mode == "paper"))
        self.engine       = StrategyEngine(self.broker, self.tracker, self.risk, self.ensemble)
        self.status       = "running"

        # ── Restore today's P&L from DB so restarts don't lose progress ──
        self.tracker.load_from_db()
        self.tracker.record_session_start()

        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"Bot | Broker={mode.upper()} | Trading={trading_mode.upper()} | "
            f"Restored P&L=${self.tracker.realized_pnl:.2f} | Watchlist={self.watchlist}"
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
        await self._train_models()
        last_train_day = datetime.now(ET).date()
        last_wl_day    = None

        while self.status == "running":
            try:
                now = datetime.now(ET)

                # Daily retrain
                if now.date() != last_train_day and now.hour >= 9:
                    await self._train_models()
                    last_train_day = now.date()

                if not self.broker.is_market_open():
                    await asyncio.sleep(60)
                    continue

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

                for symbol in active_wl:
                    if self.status != "running":
                        break
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

    async def _train_models(self):
        try:
            for symbol in (self._settings.get_watchlist() or config.DEFAULT_WATCHLIST)[:3]:
                if not self.broker:
                    break
                df = self.broker.get_bars(symbol, timeframe="5Min", limit=1000)
                if df.empty:
                    continue
                from data.indicators import add_all_indicators
                df = add_all_indicators(df)
                if self.ensemble.train(df):
                    logger.info(f"ML trained on {symbol} ✓")
                    break
        except Exception as e:
            logger.error(f"Training: {e}")

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