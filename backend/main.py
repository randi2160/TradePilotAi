"""
AutoTrader Pro — FastAPI v4 (Production)
✅ JWT Authentication on all trading routes
✅ PostgreSQL persistence (trades, equity, watchlist)
✅ SendGrid email alerts
✅ Rate limiting
✅ PDT rule tracking
✅ Manual trade placement
✅ Backtesting endpoint
✅ Analytics & performance stats
✅ Swagger UI at /docs
"""
# ── Load .env FIRST — must be before all other imports ───────────────────────
import os
from dotenv import load_dotenv
load_dotenv()

# Guarantee SQLite if DATABASE_URL is missing or has placeholder
_db_url = os.environ.get("DATABASE_URL", "")
if not _db_url or "yourpassword" in _db_url or _db_url == "postgresql://autotrader:autotrader@localhost:5432/autotrader":
    os.environ["DATABASE_URL"] = "sqlite:///./autotrader.db"
    print("INFO: DATABASE_URL not set — using SQLite (autotrader.db)")

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from auth.auth       import get_current_user
from auth.routes     import router as auth_router
from strategy.bounce_routes import router as bounce_router
from strategy.dual_routes   import router as dual_router
from broker.broker_routes   import router as broker_router
try:
    from social.social_routes import router as social_router
    _has_social = True
    print("✅ Social routes loaded")
except Exception as e:
    social_router = None
    _has_social   = False
    print(f"⚠️  Social routes not loaded: {e}")

try:
    from services.copy_routes import router as copy_router
    _has_copy = True
    print("✅ Copy routes loaded")
except Exception as e:
    copy_router = None
    _has_copy   = False
    print(f"⚠️  Copy routes not loaded: {e}")

try:
    from services.ipo_routes import router as ipo_router
    _has_ipo = True
    print("✅ IPO routes loaded")
except Exception as e:
    ipo_router = None
    _has_ipo   = False
    print(f"⚠️  IPO routes not loaded: {e}")

try:
    from services.admin_routes import router as admin_router
    _has_admin = True
    print("✅ Admin routes loaded")
except Exception as e:
    admin_router = None
    _has_admin   = False
    print(f"⚠️  Admin routes not loaded: {e}")

try:
    from services.compliance_routes import router as compliance_router
    _has_compliance = True
    print("✅ Compliance routes loaded")
except Exception as e:
    compliance_router = None
    _has_compliance   = False
    print(f"⚠️  Compliance routes not loaded: {e}")

try:
    from services.billing import router as billing_router
    _has_billing = True
    print("✅ Billing routes loaded")
except Exception as e:
    billing_router = None
    _has_billing   = False
    print(f"⚠️  Billing routes not loaded: {e}")

try:
    from services.alerts import router as alerts_router
    _has_alerts = True
    print("✅ Alerts routes loaded")
except Exception as e:
    alerts_router = None
    _has_alerts   = False
    print(f"⚠️  Alerts routes not loaded: {e}")

try:
    from services.daily_advisor import router as daily_router
    _has_daily = True
    print("✅ Daily advisor routes loaded")
except Exception as e:
    daily_router = None
    _has_daily   = False
    print(f"⚠️  Daily advisor routes not loaded: {e}")
from data.ai_advisor      import AIAdvisor
from data.dynamic_watchlist import DynamicWatchlistBuilder
from data.market_scanner  import MarketScanner
from data.news_scanner    import NewsScanner
from data.settings_manager import SettingsManager
from database.database    import get_db, init_db, check_connection
from database.models      import User, Watchlist as WatchlistModel
from scheduler.bot_loop   import BotLoop
from services.alert_service import AlertService
from services.backtest      import BacktestEngine
from services.trade_service import TradeService, PDTTracker
from services.goal_engine   import GoalEngine
from services.daily_report  import DailyReporter
from strategy.daily_target  import DailyTargetTracker
import config

import logging.handlers as _log_handlers

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers= [
        logging.StreamHandler(),
        logging.FileHandler("autotrader.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Separate ERROR-only crash log — survives restarts, rotates at 5MB
_crash_handler = _log_handlers.RotatingFileHandler(
    "autotrader_errors.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
)
_crash_handler.setLevel(logging.ERROR)
_crash_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
logging.getLogger().addHandler(_crash_handler)

# Catch unhandled exceptions and write them to the crash log
import sys as _sys
def _log_unhandled(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        _sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("UNHANDLED EXCEPTION — SERVER CRASH", exc_info=(exc_type, exc_value, exc_tb))
_sys.excepthook = _log_unhandled

# ── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── Shared singletons (not per-user — bot runs as single instance) ────────────
settings     = SettingsManager()
tracker      = DailyTargetTracker(
    capital          = settings.get_capital(),
    daily_target_min = settings.get_targets()["daily_target_min"],
    daily_target_max = settings.get_targets()["daily_target_max"],
)
bot_loop           = BotLoop(tracker)
bot_loop.watchlist = settings.get_watchlist()

news_scanner = NewsScanner()
mkt_scanner  = MarketScanner()
ai_advisor   = AIAdvisor()
alert_svc    = AlertService()
goal_engine  = GoalEngine()
reporter     = DailyReporter()
ws_clients: List[WebSocket] = []


# ── Background tasks ──────────────────────────────────────────────────────────

async def equity_recorder():
    """Record portfolio equity every 5 minutes to DB."""
    while True:
        await asyncio.sleep(300)
        try:
            if bot_loop.broker:
                acct = bot_loop.broker.get_account()
                if acct:
                    settings.record_equity(acct.get("equity", settings.get_capital()))
        except Exception as e:
            logger.error(f"equity_recorder: {e}")

async def market_scan_loop():
    while True:
        try:
            await mkt_scanner.scan()
        except Exception as e:
            logger.error(f"market_scan_loop: {e}")
        await asyncio.sleep(60)

async def daily_summary_sender():
    """Send daily summary email at 4:05 PM ET every trading day."""
    import pytz
    ET = pytz.timezone("America/New_York")
    while True:
        now = datetime.now(ET)
        if now.hour == 16 and now.minute == 5 and now.weekday() < 5:
            try:
                stats = tracker.stats()
                logger.info("Daily summary triggered")
            except Exception as e:
                logger.error(f"daily_summary: {e}")
        await asyncio.sleep(60)


_crypto_running = False

async def crypto_engine_loop():
    """Background loop that runs crypto/hybrid engine cycles when activated."""
    global _hybrid_engine, _crypto_running
    logger.info("Crypto engine loop started (idle until activated)")
    while True:
        try:
            if _hybrid_engine is not None and _crypto_running:
                result = await _hybrid_engine.run_cycle()

                # Keep user context wired after lazy engine creation
                if (_hybrid_engine.crypto_engine and
                        not getattr(_hybrid_engine.crypto_engine, '_reporter', None)):
                    _hybrid_engine.crypto_engine._reporter = reporter

                state  = result.get("crypto", {})
                if isinstance(state, dict):
                    engine_state = state.get("state", "idle")

                    # Log crypto activity to the live feed
                    try:
                        if engine_state == "order_pending":
                            sym = state.get("last_symbol", "CRYPTO")
                            reporter.log("entry", sym, f"Crypto order submitted: {sym}", state)
                        elif engine_state == "ready_for_reentry":
                            sym = state.get("last_symbol", "CRYPTO")
                            pnl = state.get("realized_pnl", 0)
                            reporter.log("exit", sym, f"Crypto trade closed | P&L ${pnl:.2f}", state)
                        elif engine_state == "stopped_for_day":
                            reason = state.get("stop_reason", "Target reached")
                            reporter.log("system", "CRYPTO", f"Crypto engine stopped: {reason}", state)
                    except Exception:
                        pass

                    if engine_state == "stopped_for_day":
                        logger.info(f"Crypto engine stopped for day: {state.get('stop_reason')}")
                        _crypto_running = False
        except Exception as e:
            logger.error(f"crypto_engine_loop: {e}")
        await asyncio.sleep(15)   # 15s loop — data fetch takes 8-12s so real cycle ~20s total


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AutoTrader Pro v4 starting…")
    init_db()
    if not check_connection():
        logger.warning("⚠️  Database not reachable — running in file-only mode")

    # ── Startup: recover any open crypto positions from Alpaca ────────────────
    try:
        from broker.alpaca_client import AlpacaClient
        import config as _cfg
        if _cfg.ALPACA_API_KEY:
            _recovery_broker = AlpacaClient(
                paper=(_cfg.ALPACA_MODE != "live"),
                api_key=_cfg.ALPACA_API_KEY,
                api_secret=_cfg.ALPACA_SECRET_KEY,
            )
            positions = _recovery_broker.get_positions()
            crypto_syms = [p.get("symbol","") for p in positions
                           if "/" in str(p.get("symbol","")) or
                           any(c in str(p.get("symbol","")) for c in ["BTC","ETH","SOL","DOGE"])]
            if crypto_syms:
                logger.warning(
                    f"⚠️  Found {len(crypto_syms)} open crypto position(s) from previous session: "
                    f"{crypto_syms} — they remain open on Alpaca. "
                    f"Start the crypto engine to resume monitoring them."
                )
    except Exception as e:
        logger.debug(f"Startup position recovery check: {e}")

    asyncio.create_task(equity_recorder())
    asyncio.create_task(market_scan_loop())
    asyncio.create_task(daily_summary_sender())
    asyncio.create_task(crypto_engine_loop())

    yield

    # ── Shutdown: clean up everything ─────────────────────────────────────────
    logger.info("Shutting down — saving state…")

    # Stop stock bot cleanly
    try:
        await bot_loop.stop()
        logger.info("✅ Stock bot stopped cleanly")
    except Exception as e:
        logger.error(f"Stock bot stop error: {e}")

    # Stop crypto engine and log open positions
    global _hybrid_engine, _crypto_running
    _crypto_running = False
    if _hybrid_engine is not None:
        try:
            crypto_status = _hybrid_engine.get_status()
            crypto = crypto_status.get("crypto") or {}
            open_pos = crypto.get("open_position_list", [])
            if open_pos:
                logger.warning(
                    f"⚠️  SHUTDOWN WITH {len(open_pos)} OPEN CRYPTO POSITION(S): "
                    f"{[p['symbol'] for p in open_pos]} — "
                    f"These remain open on Alpaca. They will NOT be auto-closed. "
                    f"Monitor them manually or restart the engine."
                )
            else:
                logger.info("✅ Crypto engine stopped — no open positions")
        except Exception as e:
            logger.error(f"Crypto engine shutdown: {e}")

    # Write shutdown log entry to DB
    try:
        from database.database import SessionLocal
        from database.models   import AuditLog
        db = SessionLocal()
        db.add(AuditLog(
            user_id=1,
            action="SERVER_SHUTDOWN",
            details=f"Server shutdown at {datetime.now().isoformat()} | "
                    f"bot_status={bot_loop.status} | "
                    f"crypto_running={_crypto_running}",
        ))
        db.commit()
        db.close()
        logger.info("✅ Shutdown logged to DB")
    except Exception as e:
        logger.debug(f"Shutdown log: {e}")

    logger.info("Shutdown complete.")


# ── App ───────────────────────────────────────────────────────────────────────

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173"
).split(",")

app = FastAPI(
    title       = "AutoTrader Pro",
    description = "AI-powered automated stock trading — JWT secured, GPT-4 advisor, PostgreSQL backed",
    version     = "4.0.0",
    lifespan    = lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# Auth routes (no JWT required — login/register)
app.include_router(auth_router)
app.include_router(bounce_router)
app.include_router(dual_router)
app.include_router(broker_router)
if _has_social and social_router:
    app.include_router(social_router)
if _has_copy and copy_router:
    app.include_router(copy_router)
if _has_ipo and ipo_router:
    app.include_router(ipo_router)
if _has_admin and admin_router:
    app.include_router(admin_router)
if _has_compliance and compliance_router:
    app.include_router(compliance_router)
if _has_billing and billing_router:
    app.include_router(billing_router)
if _has_alerts and alerts_router:
    app.include_router(alerts_router)
if _has_daily and daily_router:
    app.include_router(daily_router)


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket (JWT via query param: /ws?token=xxx)
# ══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: Optional[str] = None):
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            try:
                summary = bot_loop.get_live_summary()
                summary["settings"] = settings.all()

                # Merge crypto engine P&L into the top-level summary
                global _hybrid_engine, _crypto_running
                if _hybrid_engine is not None and _crypto_running:
                    try:
                        crypto_status = _hybrid_engine.get_status()
                        crypto = crypto_status.get("crypto") or {}
                        crypto_pnl = float(crypto.get("realized_pnl", 0))
                        if crypto_pnl != 0:
                            # Add crypto P&L on top of stock P&L
                            summary["realized_pnl"] = round(
                                float(summary.get("realized_pnl", 0)) + crypto_pnl, 2
                            )
                            summary["total_pnl"] = round(
                                float(summary.get("total_pnl", 0)) + crypto_pnl, 2
                            )
                            summary["crypto_pnl"] = crypto_pnl
                            summary["trade_count"] = (
                                int(summary.get("trade_count", 0)) +
                                int(crypto.get("trades_today", 0))
                            )
                    except Exception:
                        pass

                await ws.send_json(summary)
            except Exception:
                break
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if ws in ws_clients:
            ws_clients.remove(ws)


# ══════════════════════════════════════════════════════════════════════════════
# Health check (public)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["System"])
async def health():
    return {
        "status":   "ok",
        "db":       check_connection(),
        "bot":      bot_loop.status,
        "version":  "4.0.0",
        "time":     datetime.utcnow().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Bot control (requires JWT)
# ══════════════════════════════════════════════════════════════════════════════

class BotStartBody(BaseModel):
    mode:         str = Field("paper", description="paper | live")
    trading_mode: str = Field("auto",  description="auto | manual")

@app.post("/api/bot/start",  tags=["Bot"])
async def start_bot(body: BotStartBody, user: User = Depends(get_current_user)):
    await bot_loop.start(mode=body.mode, trading_mode=body.trading_mode)
    return {"status": "started", "mode": body.mode, "trading_mode": body.trading_mode}

@app.post("/api/bot/stop",   tags=["Bot"])
async def stop_bot(user: User = Depends(get_current_user)):
    await bot_loop.stop()
    return {"status": "stopped"}

class EngineModeBody(BaseModel):
    mode:                    str   # stocks_only | crypto_only | hybrid
    crypto_alloc:            float = 0.30   # 0.0 – 1.0 (market hours)
    after_hours_crypto_alloc: float = 0.80  # 0.0 – 1.0 (after hours, default 80%)

_hybrid_engine = None

@app.post("/api/bot/engine-mode", tags=["Bot"])
async def set_engine_mode(body: EngineModeBody, user: User = Depends(get_current_user)):
    """Activate crypto or hybrid trading engine."""
    global _hybrid_engine, _crypto_running
    valid = ("stocks_only", "crypto_only", "hybrid")
    if body.mode not in valid:
        raise HTTPException(400, f"mode must be one of: {valid}")

    if body.mode == "stocks_only":
        _crypto_running  = False
        _hybrid_engine   = None
        settings.set_engine_settings(
            settings._data.get("stop_new_trades_hour", 15),
            settings._data.get("stop_new_trades_minute", 30),
            settings._data.get("max_open_positions", 3),
            "stocks_only", body.crypto_alloc,
        )
        return {"status": "stocks_only_active", "crypto_running": False,
                "message": "Crypto engine stopped. Stock engine continues normally."}

    # Get broker — priority: 1) bot_loop if running, 2) user saved keys, 3) .env fallback
    broker = bot_loop.broker
    if not broker:
        try:
            from broker.alpaca_client import AlpacaClient
            from broker.broker_routes import _load_creds
            import config as _cfg

            # _load_creds checks: 1) user saved keys, 2) legacy alpaca fields, 3) .env fallback
            creds = _load_creds(user)
            if not creds.get("api_key"):
                raise HTTPException(400,
                    "NO_BROKER: No Alpaca API keys found. Add them to your .env file "
                    "or connect your account in the My Broker tab.")

            mode   = getattr(user, "alpaca_mode", None) or getattr(_cfg, "ALPACA_MODE", "paper")
            broker = AlpacaClient(
                paper      = (mode != "live"),
                api_key    = creds["api_key"],
                api_secret = creds["api_secret"],
            )
            logger.info(f"Crypto engine broker ready (mode={mode})")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Broker connection failed: {e}. "
                "Go to My Broker tab and reconnect your Alpaca account.")

    try:
        from strategy.hybrid_engine import HybridEngine
        from strategy.crypto_engine import CryptoPosition, EngineState
        _hybrid_engine = HybridEngine(
            broker           = broker,
            settings         = settings,
            tracker          = tracker,
            stock_engine     = getattr(bot_loop, "engine", None),
            mode             = body.mode,
            crypto_alloc_pct = body.crypto_alloc,
        )
        _crypto_running = True
        # Wire in user context for DB saves and activity feed
        if _hybrid_engine.crypto_engine:
            _hybrid_engine.crypto_engine._user_id  = user.id
            _hybrid_engine.crypto_engine._reporter = reporter

        # Reconcile any existing open Alpaca crypto positions
        try:
            positions = broker.get_positions()
            crypto_positions = [p for p in positions
                if any(c in str(p.get("symbol","")).upper()
                       for c in ["BTC","ETH","SOL","DOGE","LINK","AAVE","LTC","BCH","XRP","SHIB"])]
            if crypto_positions:
                logger.warning(f"Reconciling {len(crypto_positions)} existing crypto positions: "
                    f"{[p.get('symbol') for p in crypto_positions]}")
                if _hybrid_engine.crypto_engine:
                    for p in crypto_positions:
                        sym_raw = str(p.get("symbol",""))
                        ticker  = sym_raw.replace("USD","").replace("/","")
                        symbol  = f"{ticker}/USD"
                        qty     = float(p.get("qty", 0))
                        entry   = float(p.get("avg_entry_price", p.get("current_price", 0)))
                        current = float(p.get("current_price", entry))
                        upnl    = float(p.get("unrealized_pl", 0))
                        pos = CryptoPosition(
                            symbol=symbol, side="BUY", qty=qty,
                            entry=entry, stop=entry*0.98, target=entry*1.02,
                        )
                        _hybrid_engine.crypto_engine.open_positions[symbol] = pos
                        logger.info(f"  Reconciled: {symbol} qty={qty} entry=${entry:.4f} upnl=${upnl:+.2f}")
                    _hybrid_engine.crypto_engine.state = EngineState.POSITION_OPEN
        except Exception as e:
            logger.error(f"Position reconciliation error: {e}")
        settings.set_engine_settings(
            settings._data.get("stop_new_trades_hour", 15),
            settings._data.get("stop_new_trades_minute", 30),
            settings._data.get("max_open_positions", 3),
            body.mode,
            body.crypto_alloc,
        )
        logger.info(f"Crypto/Hybrid engine STARTED: mode={body.mode} alloc={body.crypto_alloc:.0%}")
    except Exception as e:
        logger.error(f"Hybrid engine init: {e}")
        raise HTTPException(500, str(e))

    return {
        "status":        "started",
        "mode":          body.mode,
        "crypto_alloc":  body.crypto_alloc,
        "stock_alloc":   round(1.0 - body.crypto_alloc, 2),
        "crypto_running":True,
        "message":       f"{'Hybrid' if body.mode == 'hybrid' else 'Crypto'} engine activated — scanning every 30s",
    }


@app.post("/api/bot/engine-stop", tags=["Bot"])
async def stop_engine_mode(user: User = Depends(get_current_user)):
    """Stop the crypto/hybrid engine."""
    global _hybrid_engine, _crypto_running
    _crypto_running = False
    _hybrid_engine  = None
    return {"status": "stopped", "message": "Crypto engine stopped"}

@app.get("/api/bot/engine-status", tags=["Bot"])
async def get_engine_status(user: User = Depends(get_current_user)):
    """Get hybrid engine status including crypto engine state machine."""
    global _hybrid_engine, _crypto_running
    saved_mode = settings._data.get("engine_mode", "stocks_only")
    if _hybrid_engine is None:
        return {
            "mode":          saved_mode,
            "crypto_running":False,
            "hybrid":        None,
            "crypto":        None,
            "configured":    False,
            "message":       "Crypto engine not started. Use the Start Crypto button.",
        }
    status = _hybrid_engine.get_status()
    return {
        **status,
        "crypto_running": _crypto_running,
        "configured":     True,
    }

@app.post("/api/bot/crypto/cycle", tags=["Bot"])
async def run_crypto_cycle(user: User = Depends(get_current_user)):
    """Manually trigger one crypto engine cycle (for testing)."""
    global _hybrid_engine
    if _hybrid_engine is None:
        raise HTTPException(400, "Set engine mode first via /api/bot/engine-mode")
    result = await _hybrid_engine.run_cycle()
    return result

@app.get("/api/status",      tags=["Bot"])
async def get_status(user: User = Depends(get_current_user)):
    s = bot_loop.get_live_summary()
    s["settings"] = settings.all()
    return s

@app.post("/api/train",      tags=["Bot"])
async def retrain(user: User = Depends(get_current_user)):
    asyncio.create_task(bot_loop._train_models())
    return {"status": "training started"}

@app.post("/api/positions/close-all", tags=["Bot"])
async def close_all(user: User = Depends(get_current_user)):
    if bot_loop.broker:
        bot_loop.broker.close_all_positions()
        return {"status": "all positions closed"}
    raise HTTPException(404, "Bot not running")

class TradingModeBody(BaseModel):
    trading_mode: str

@app.put("/api/bot/trading-mode", tags=["Bot"])
async def set_trading_mode(body: TradingModeBody, user: User = Depends(get_current_user)):
    bot_loop.set_trading_mode(body.trading_mode)
    return {"trading_mode": body.trading_mode}

class WatchlistModeBody(BaseModel):
    dynamic: bool

@app.put("/api/bot/watchlist-mode", tags=["Bot"])
async def set_watchlist_mode(body: WatchlistModeBody, user: User = Depends(get_current_user)):
    bot_loop.set_watchlist_dynamic(body.dynamic)
    return {"dynamic_watchlist": body.dynamic}


# ══════════════════════════════════════════════════════════════════════════════
# Manual Trades
# ══════════════════════════════════════════════════════════════════════════════

class ManualTradeBody(BaseModel):
    symbol:      str
    side:        str   = Field(..., description="BUY | SELL")
    qty:         float = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)

@app.post("/api/trades/manual", tags=["Manual Trading"])
async def place_manual_trade(
    body: ManualTradeBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    if not bot_loop.broker:
        raise HTTPException(400, "Bot not started — start bot first to enable trading")

    # Place the actual order
    order = bot_loop.broker.place_market_order(body.symbol, body.qty, body.side)
    if "error" in order:
        raise HTTPException(400, f"Order failed: {order['error']}")

    # Persist to DB
    svc = TradeService(db, user.id)
    trade = svc.open_trade(
        symbol      = body.symbol,
        side        = body.side,
        qty         = body.qty,
        entry_price = body.entry_price,
        stop_loss   = body.entry_price * 0.98,
        take_profit = body.entry_price * 1.05,
        is_manual   = True,
        order_id    = order.get("id", ""),
    )

    # Auto-broadcast to social feed (if social module installed)
    if _has_social:
        try:
            from services.social_service import SocialService
            social = SocialService(db)
            social.broadcast_trade(user, trade, "BUY", reasoning="Manual trade")
        except Exception:
            pass

    # Email alert
    if user.email_alerts:
        asyncio.create_task(alert_svc.trade_opened(user.email, {
            "symbol": body.symbol, "side": body.side, "qty": body.qty,
            "entry_price": body.entry_price,
            "position_value": body.qty * body.entry_price,
        }))

    return {"status": "order placed", "order": order, "trade_id": trade.id}

@app.post("/api/trades/manual/close/{symbol}", tags=["Manual Trading"])
async def close_manual_trade(
    symbol: str,
    user:   User    = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    if not bot_loop.broker:
        raise HTTPException(400, "Bot not started")

    result = bot_loop.broker.close_position(symbol.upper())
    price  = bot_loop.broker.get_latest_price(symbol.upper())

    # Close in DB
    svc   = TradeService(db, user.id)
    trade = svc.get_trade_by_symbol(symbol.upper())
    if trade:
        closed = svc.close_trade(trade.id, price, reason="manual_close")
        if closed and user.email_alerts:
            asyncio.create_task(alert_svc.trade_closed(user.email, {
                "symbol":      closed.symbol,
                "side":        closed.side,
                "entry_price": closed.entry_price,
                "exit_price":  price,
                "qty":         closed.qty,
                "pnl":         closed.pnl or 0,
                "net_pnl":     closed.net_pnl or 0,
                "pnl_pct":     closed.pnl_pct or 0,
            }))

    return {"status": "closed", "symbol": symbol.upper(), "price": price}


# ══════════════════════════════════════════════════════════════════════════════
# Pending trades (manual mode)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/pending-trades",                    tags=["Manual Mode"])
async def get_pending(user: User = Depends(get_current_user)):
    return bot_loop._pending_trades

@app.post("/api/pending-trades/{symbol}/approve",  tags=["Manual Mode"])
async def approve(symbol: str, user: User = Depends(get_current_user)):
    bot_loop.approve_pending_trade(symbol.upper())
    return {"status": "approved", "symbol": symbol.upper()}

@app.post("/api/pending-trades/{symbol}/reject",   tags=["Manual Mode"])
async def reject(symbol: str, user: User = Depends(get_current_user)):
    bot_loop.reject_pending_trade(symbol.upper())
    return {"status": "rejected", "symbol": symbol.upper()}


# ══════════════════════════════════════════════════════════════════════════════
# Market Data
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/trades", tags=["Data"])
async def get_trades(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc    = TradeService(db, user.id)
    trades = svc.get_trades(limit=100)
    db_results = [
        {
            "id":            t.id,
            "symbol":        t.symbol,
            "side":          t.side,
            "qty":           t.qty,
            "entry_price":   t.entry_price,
            "exit_price":    t.exit_price,
            "stop_loss":     t.stop_loss,
            "take_profit":   t.take_profit,
            "pnl":           t.pnl,
            "net_pnl":       t.net_pnl,
            "pnl_pct":       t.pnl_pct,
            "position_value": t.position_value,
            "confidence":    t.confidence,
            "is_manual":     t.is_manual,
            "status":        t.status,
            "opened_at":     str(t.opened_at),
            "closed_at":     str(t.closed_at) if t.closed_at else None,
            "trade_date":    t.trade_date,
            "source":        "db",
        }
        for t in trades
    ]

    # Also pull today's filled Alpaca orders so crypto trades always show up
    alpaca_results = []
    try:
        broker = bot_loop.broker
        if not broker:
            from broker.alpaca_client import AlpacaClient
            from broker.broker_routes import _load_creds
            import config as _cfg
            creds = _load_creds(user)
            if creds.get("api_key"):
                mode   = getattr(user, "alpaca_mode", None) or getattr(_cfg, "ALPACA_MODE", "paper")
                broker = AlpacaClient(paper=(mode != "live"),
                                      api_key=creds["api_key"], api_secret=creds["api_secret"])
        if broker:
            from datetime import date
            today_str = str(date.today())
            try:
                raw_orders = broker.get_open_orders() + (
                    getattr(broker, "_filled_today", [])
                )
                # Get filled orders via direct API call
                try:
                    from alpaca.trading.requests import GetOrdersRequest
                    from alpaca.trading.enums   import QueryOrderStatus
                    req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=50,
                                          after=f"{today_str}T00:00:00Z")
                    raw_orders = broker.trading.get_orders(filter=req)
                except Exception:
                    raw_orders = []
            except Exception:
                raw_orders = []
            db_order_ids = set()  # don't duplicate DB records
            for o in raw_orders:
                try:
                    if str(getattr(o, "status", "")) != "filled":
                        continue
                    sym = str(getattr(o, "symbol", ""))
                    oid = str(getattr(o, "id", ""))
                    if oid in db_order_ids:
                        continue
                    filled_qty = float(getattr(o, "filled_qty", 0) or 0)
                    fill_price = float(getattr(o, "filled_avg_price", 0) or 0)
                    side       = str(getattr(o, "side", "buy")).upper()
                    filled_at  = str(getattr(o, "filled_at", "") or "")
                    pv         = round(filled_qty * fill_price, 2)
                    alpaca_results.append({
                        "id":            f"alpaca_{oid[:8]}",
                        "symbol":        sym,
                        "side":          side,
                        "qty":           filled_qty,
                        "entry_price":   fill_price if side == "BUY" else None,
                        "exit_price":    fill_price if side == "SELL" else None,
                        "pnl":           None,
                        "status":        "filled",
                        "position_value": pv,
                        "opened_at":     filled_at,
                        "closed_at":     filled_at if side == "SELL" else None,
                        "trade_date":    today_str,
                        "source":        "alpaca",
                    })
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"Alpaca order merge: {e}")

    # Merge — DB records take priority, Alpaca fills fill the gaps
    all_results = db_results + alpaca_results
    all_results.sort(key=lambda x: str(x.get("opened_at", "")), reverse=True)
    return all_results

@app.get("/api/signals",        tags=["Data"])
async def get_signals(user: User = Depends(get_current_user)):
    return bot_loop.get_latest_signals()

@app.get("/api/positions",      tags=["Data"])
async def get_positions(user: User = Depends(get_current_user)):
    return bot_loop.broker.get_positions() if bot_loop.broker else []

@app.get("/api/orders",         tags=["Data"])
async def get_orders(user: User = Depends(get_current_user)):
    return bot_loop.broker.get_orders(50) if bot_loop.broker else []

@app.get("/api/chart/{symbol}", tags=["Data"])
async def get_chart(symbol: str, timeframe: str = "5Min", limit: int = 200,
                    user: User = Depends(get_current_user)):
    if not bot_loop.broker:
        raise HTTPException(400, "Start bot first")
    df = bot_loop.broker.get_bars(symbol, timeframe, limit)
    if df.empty:
        return []
    df = df.reset_index()
    df["timestamp"] = df["timestamp"].astype(str)
    return df.to_dict(orient="records")

@app.get("/api/equity-history", tags=["Data"])
async def get_equity_history(hours: int = 24,
                              user: User = Depends(get_current_user),
                              db:   Session = Depends(get_db)):
    try:
        svc = TradeService(db, user.id)
        return svc.get_equity_history(hours)
    except Exception:
        return settings.get_equity_history(hours)


# ══════════════════════════════════════════════════════════════════════════════
# Analytics & Performance
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/analytics/performance", tags=["Analytics"])
async def get_performance(
    days: int     = 30,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    svc = TradeService(db, user.id)
    return svc.get_performance_summary(days)

@app.get("/api/analytics/today", tags=["Analytics"])
async def get_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = TradeService(db, user.id)
    return svc.get_today_stats()

@app.get("/api/analytics/pdt", tags=["Analytics"])
async def get_pdt(user: User = Depends(get_current_user)):
    """
    Full PDT compliance status from live Alpaca account.
    Returns daytrade_count, buying power, exempt status, and recommendations.
    """
    if not bot_loop.broker:
        # Try standalone client
        try:
            from broker.alpaca_client import AlpacaClient
            import config as _cfg
            _broker = AlpacaClient(_cfg.ALPACA_API_KEY,
                                   getattr(_cfg, 'ALPACA_SECRET_KEY', ''),
                                   getattr(_cfg, 'ALPACA_MODE', 'paper'))
        except Exception:
            return {"error": "Connect your broker to check PDT status"}
    else:
        _broker = bot_loop.broker

    try:
        from strategy.pdt_engine import PDTComplianceEngine
        pdt_engine = PDTComplianceEngine(_broker)
        summary    = pdt_engine.account_summary()

        # Add human-readable recommendations
        recs = []
        if summary["is_pdt_exempt"]:
            recs.append("✅ Your account is PDT exempt — trade freely")
        else:
            remaining = summary["day_trades_remaining"]
            if remaining == 0:
                recs.append("⛔ Day trade limit reached — all new entries must be held overnight")
                recs.append("💡 Consider crypto positions — not subject to PDT rules")
                recs.append("💡 Or add funds to bring equity above $25,000")
            elif remaining == 1:
                recs.append("⚠️ Only 1 day trade remaining — use it carefully")
                recs.append("💡 Consider holding existing positions overnight to reset tomorrow")
            else:
                recs.append(f"✅ {remaining} day trades available today")

            if summary["equity"] < 2000:
                recs.append("⚠️ Account under $2,000 — limited to 1x buying power (cash only)")
            elif summary["equity"] < 25000:
                recs.append(f"ℹ️ Account multiplier: {summary['account_multiplier']}x buying power")

        summary["recommendations"] = recs
        return summary

    except Exception as e:
        logger.error(f"PDT check error: {e}")
        # Fallback to basic account data
        acct = _broker.get_account()
        return {**acct, "error": str(e)}

@app.post("/api/analytics/backtest", tags=["Analytics"])
async def run_backtest(
    symbol: str   = "SPY",
    limit:  int   = 500,
    user:   User  = Depends(get_current_user),
):
    if not bot_loop.broker:
        raise HTTPException(400, "Start bot first to load market data")
    df = bot_loop.broker.get_bars(symbol, "5Min", limit)
    if df.empty:
        raise HTTPException(400, f"No data for {symbol}")
    from data.indicators import add_all_indicators
    df  = add_all_indicators(df)
    eng = BacktestEngine(capital=user.capital)
    return eng.run(df)


# ══════════════════════════════════════════════════════════════════════════════
# News & Sentiment
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/news/market",             tags=["News"])
async def market_news(limit: int = 20, user: User = Depends(get_current_user)):
    return await news_scanner.get_market_news(limit)

@app.get("/api/news/{symbol}",           tags=["News"])
async def symbol_news(symbol: str, limit: int = 10, user: User = Depends(get_current_user)):
    return await news_scanner.get_symbol_news(symbol.upper(), limit)

@app.get("/api/sentiment/{symbol}",      tags=["News"])
async def sentiment(symbol: str, user: User = Depends(get_current_user)):
    return await news_scanner.get_sentiment_signal(symbol.upper())

@app.get("/api/sentiment/watchlist/all", tags=["News"])
async def watchlist_sentiment(user: User = Depends(get_current_user)):
    return await news_scanner.scan_watchlist(settings.get_watchlist())


# ══════════════════════════════════════════════════════════════════════════════
# AI Advisor
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/ai/advice",         tags=["AI Advisor"])
async def get_advice(force: bool = False, user: User = Depends(get_current_user)):
    scan      = await mkt_scanner.scan()
    sentiment = await news_scanner.scan_watchlist(settings.get_watchlist())
    signals   = bot_loop.get_latest_signals()
    stats     = tracker.stats()
    positions = bot_loop.broker.get_positions() if bot_loop.broker else []
    return await ai_advisor.get_advice(scan, sentiment, signals, stats, positions, force=force)

@app.get("/api/ai/watchlist-suggest", tags=["AI Advisor"])
async def suggest_watchlist(user: User = Depends(get_current_user)):
    scan      = await mkt_scanner.scan()
    sentiment = await news_scanner.scan_watchlist(settings.get_watchlist())
    signals   = bot_loop.get_latest_signals()
    await bot_loop._wl_builder.build(scan, sentiment, signals)
    return bot_loop._wl_builder.get_scores()

@app.get("/api/ai/unusual-volume",    tags=["AI Advisor"])
async def unusual_volume(user: User = Depends(get_current_user)):
    return bot_loop._unusual_volume


# ══════════════════════════════════════════════════════════════════════════════
# Scanner
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/scanner/scan",    tags=["Scanner"])
async def run_scan(user: User = Depends(get_current_user)):
    return await mkt_scanner.scan()

@app.get("/api/scanner/search", tags=["Scanner"])
async def symbol_search(q: str = "", user: User = Depends(get_current_user)):
    """Live symbol autocomplete search."""
    q = q.upper().strip()
    if not q:
        return []
    SYMBOLS = [
        {"symbol":"AAPL","name":"Apple Inc."},{"symbol":"TSLA","name":"Tesla Inc."},
        {"symbol":"NVDA","name":"NVIDIA Corp."},{"symbol":"AMD","name":"Advanced Micro Devices"},
        {"symbol":"META","name":"Meta Platforms"},{"symbol":"AMZN","name":"Amazon.com"},
        {"symbol":"MSFT","name":"Microsoft Corp."},{"symbol":"GOOGL","name":"Alphabet Inc."},
        {"symbol":"SPY","name":"S&P 500 ETF"},{"symbol":"QQQ","name":"Nasdaq-100 ETF"},
        {"symbol":"NFLX","name":"Netflix Inc."},{"symbol":"DIS","name":"Walt Disney Co."},
        {"symbol":"BAC","name":"Bank of America"},{"symbol":"JPM","name":"JPMorgan Chase"},
        {"symbol":"UBER","name":"Uber Technologies"},{"symbol":"SHOP","name":"Shopify Inc."},
        {"symbol":"COIN","name":"Coinbase Global"},{"symbol":"PLTR","name":"Palantir Technologies"},
        {"symbol":"NIO","name":"NIO Inc."},{"symbol":"RIVN","name":"Rivian Automotive"},
        {"symbol":"LCID","name":"Lucid Group"},{"symbol":"GME","name":"GameStop Corp."},
        {"symbol":"AMC","name":"AMC Entertainment"},{"symbol":"SOFI","name":"SoFi Technologies"},
        {"symbol":"SMCI","name":"Super Micro Computer"},{"symbol":"ARM","name":"Arm Holdings"},
        {"symbol":"AVGO","name":"Broadcom Inc."},{"symbol":"INTC","name":"Intel Corp."},
        {"symbol":"MU","name":"Micron Technology"},{"symbol":"QCOM","name":"Qualcomm Inc."},
        {"symbol":"ORCL","name":"Oracle Corp."},{"symbol":"CRM","name":"Salesforce Inc."},
        {"symbol":"NOW","name":"ServiceNow Inc."},{"symbol":"SNOW","name":"Snowflake Inc."},
        {"symbol":"ROKU","name":"Roku Inc."},{"symbol":"PYPL","name":"PayPal Holdings"},
        {"symbol":"V","name":"Visa Inc."},{"symbol":"MA","name":"Mastercard Inc."},
        {"symbol":"GS","name":"Goldman Sachs"},{"symbol":"XOM","name":"Exxon Mobil"},
        {"symbol":"F","name":"Ford Motor Co."},{"symbol":"GM","name":"General Motors"},
        {"symbol":"BA","name":"Boeing Co."},{"symbol":"HOOD","name":"Robinhood Markets"},
        {"symbol":"BTC","name":"Bitcoin"},{"symbol":"ETH","name":"Ethereum"},
        {"symbol":"SOL","name":"Solana"},{"symbol":"DOGE","name":"Dogecoin"},
        {"symbol":"ADA","name":"Cardano"},{"symbol":"LINK","name":"Chainlink"},
        {"symbol":"BB","name":"BlackBerry Ltd."},{"symbol":"SPOT","name":"Spotify"},
        {"symbol":"SQ","name":"Block Inc."},{"symbol":"MS","name":"Morgan Stanley"},
        {"symbol":"CVX","name":"Chevron Corp."},{"symbol":"LMT","name":"Lockheed Martin"},
        {"symbol":"SNAP","name":"Snap Inc."},{"symbol":"RBLX","name":"Roblox Corp."},
        {"symbol":"ABNB","name":"Airbnb Inc."},{"symbol":"LYFT","name":"Lyft Inc."},
        {"symbol":"ZM","name":"Zoom Video"},{"symbol":"DOCU","name":"DocuSign Inc."},
    ]
    results = [s for s in SYMBOLS if s["symbol"].startswith(q) or q in s["name"].upper()]
    # Also allow any 1-5 char ticker as a valid entry
    if q and not results:
        results = [{"symbol": q, "name": f"${q} (custom)"}]
    return results[:10]

@app.get("/api/scanner/gainers", tags=["Scanner"])
async def gainers(n: int = 10, user: User = Depends(get_current_user)):
    return mkt_scanner.get_top_gainers(n)

@app.get("/api/scanner/losers",  tags=["Scanner"])
async def losers(n: int = 10, user: User = Depends(get_current_user)):
    return mkt_scanner.get_top_losers(n)

@app.get("/api/scanner/active",  tags=["Scanner"])
async def active(n: int = 10, user: User = Depends(get_current_user)):
    return mkt_scanner.get_most_active(n)


# ══════════════════════════════════════════════════════════════════════════════
# Settings & Watchlist
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/settings",              tags=["Settings"])
async def get_settings(user: User = Depends(get_current_user)):
    return {**settings.all(), "user": {"email": user.email, "capital": user.capital}}

class CapitalBody(BaseModel):
    capital: float = Field(..., gt=100, le=1_000_000)

@app.put("/api/settings/capital",      tags=["Settings"])
async def update_capital(body: CapitalBody,
                         user: User = Depends(get_current_user),
                         db:   Session = Depends(get_db)):
    settings.set_capital(body.capital)
    tracker.capital = body.capital
    user.capital    = body.capital
    db.commit()
    return {"capital": body.capital, "status": "updated"}

class TargetsBody(BaseModel):
    daily_target_min: float = Field(..., gt=0)
    daily_target_max: float = Field(..., gt=0)
    max_daily_loss:   float = Field(..., gt=0)

@app.put("/api/settings/targets",      tags=["Settings"])
async def update_targets(body: TargetsBody,
                         user: User = Depends(get_current_user),
                         db:   Session = Depends(get_db)):
    settings.set_targets(body.daily_target_min, body.daily_target_max, body.max_daily_loss)
    tracker.target_min      = body.daily_target_min
    tracker.target_max      = body.daily_target_max
    user.daily_target_min   = body.daily_target_min
    user.daily_target_max   = body.daily_target_max
    user.max_daily_loss     = body.max_daily_loss
    db.commit()
    return {**settings.get_targets(), "status": "updated"}


class EngineSettingsBody(BaseModel):
    stop_new_trades_hour:      int   = 15
    stop_new_trades_minute:    int   = 30
    max_open_positions:        int   = 3
    engine_mode:               str   = "stocks_only"
    crypto_alloc_pct:          float = 0.30
    after_hours_crypto_alloc_pct: float = 0.80   # 50%–100% after hours

@app.put("/api/settings/engine", tags=["Settings"])
async def update_engine_settings(
    body: EngineSettingsBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Save engine mode, trading hours, max positions, crypto allocation."""
    if body.engine_mode not in ("stocks_only", "crypto_only", "hybrid"):
        raise HTTPException(400, "engine_mode must be stocks_only | crypto_only | hybrid")
    if not (0 <= body.stop_new_trades_hour <= 23):
        raise HTTPException(400, "Invalid stop hour")
    if not (1 <= body.max_open_positions <= 10):
        raise HTTPException(400, "max_open_positions must be 1–10")
    if not (0.0 <= body.crypto_alloc_pct <= 1.0):
        raise HTTPException(400, "crypto_alloc_pct must be 0.0–1.0")
    if not (0.50 <= body.after_hours_crypto_alloc_pct <= 1.0):
        raise HTTPException(400, "after_hours_crypto_alloc_pct must be 0.50–1.0")

    settings.set_engine_settings(
        body.stop_new_trades_hour,
        body.stop_new_trades_minute,
        body.max_open_positions,
        body.engine_mode,
        body.crypto_alloc_pct,
        body.after_hours_crypto_alloc_pct,
    )

    # Update live hybrid engine if running
    global _hybrid_engine
    if _hybrid_engine:
        _hybrid_engine.crypto_alloc            = body.crypto_alloc_pct
        _hybrid_engine.after_hours_crypto_alloc = body.after_hours_crypto_alloc_pct
        logger.info(f"Live engine updated: market={body.crypto_alloc_pct:.0%} after-hours={body.after_hours_crypto_alloc_pct:.0%}")

    return {**settings.all(), "status": "engine_settings_saved"}

@app.get("/api/watchlist",              tags=["Watchlist"])
async def get_watchlist(user: User = Depends(get_current_user)):
    return {"watchlist": settings.get_watchlist()}

class WatchlistBody(BaseModel):
    symbols: List[str]

@app.put("/api/watchlist",              tags=["Watchlist"])
async def set_watchlist(body: WatchlistBody, user: User = Depends(get_current_user)):
    settings.set_watchlist(body.symbols)
    bot_loop.refresh_watchlist()   # sync immediately
    return {"watchlist": settings.get_watchlist()}

class SymbolBody(BaseModel):
    symbol: str

@app.post("/api/watchlist/add",         tags=["Watchlist"])
async def add_symbol(body: SymbolBody, user: User = Depends(get_current_user)):
    settings.add_symbol(body.symbol)
    try:
        bot_loop.refresh_watchlist()
    except Exception as e:
        logger.warning(f"refresh_watchlist failed (bot may not be running): {e}")
    wl = settings.get_watchlist()
    logger.info(f"Symbol {body.symbol.upper()} added. Watchlist now: {wl}")
    return {"watchlist": wl, "added": body.symbol.upper(), "status": "saved"}

@app.delete("/api/watchlist/{symbol}",  tags=["Watchlist"])
async def remove_symbol(symbol: str, user: User = Depends(get_current_user)):
    settings.remove_symbol(symbol)
    bot_loop.refresh_watchlist()   # sync immediately
    wl = settings.get_watchlist()
    logger.info(f"Symbol {symbol.upper()} removed. Watchlist now: {wl}")
    return {"watchlist": wl, "removed": symbol.upper()}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host    = "0.0.0.0",
        port    = 8000,
        reload  = False,
        workers = 1,
    )

# ══════════════════════════════════════════════════════════════════════════════
# Goals
# ══════════════════════════════════════════════════════════════════════════════

class GoalBody(BaseModel):
    monthly_goal:   float = Field(..., gt=0)
    capital:        float = Field(..., gt=100)
    risk_tolerance: str   = Field("moderate")

@app.post("/api/goals/set", tags=["Goals"])
async def set_goal(body: GoalBody, user: User = Depends(get_current_user)):
    plan = goal_engine.set_monthly_goal(body.monthly_goal, body.capital, body.risk_tolerance)
    # Auto-update daily targets
    settings.set_targets(plan["daily_target_min"], plan["daily_target_max"], body.capital * 0.03)
    tracker.target_min = plan["daily_target_min"]
    tracker.target_max = plan["daily_target_max"]
    return plan

@app.get("/api/goals/plan", tags=["Goals"])
async def get_plan(user: User = Depends(get_current_user)):
    return goal_engine.get_current_plan()

@app.get("/api/goals/monthly", tags=["Goals"])
async def monthly_summary(user: User = Depends(get_current_user)):
    return goal_engine.get_monthly_summary()

@app.get("/api/goals/history", tags=["Goals"])
async def goal_history(days: int = 30, user: User = Depends(get_current_user)):
    return goal_engine.get_all_daily_results(days)

@app.post("/api/goals/record-day", tags=["Goals"])
async def record_day(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc   = TradeService(db, user.id)
    today = svc.get_today_stats()
    result = goal_engine.record_daily_result(
        realized_pnl = today.get("realized_pnl", 0),
        trade_count  = today.get("trade_count",  0),
        win_count    = today.get("wins", 0),
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Daily Report & Activity
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/report/history", tags=["Reports"])
async def pnl_history(
    period: str   = "30d",   # 7d | 30d | 90d | all
    user:   User  = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    """
    Daily P&L history with compound running total.
    Returns list of days with trades, cumulative P&L, and per-trade breakdown.
    """
    from database.models import Trade
    from datetime import date, timedelta
    import math

    # Determine date range
    today = date.today()
    if period == "7d":
        since = today - timedelta(days=7)
    elif period == "30d":
        since = today - timedelta(days=30)
    elif period == "90d":
        since = today - timedelta(days=90)
    else:
        since = date(2020, 1, 1)  # all time

    trades = db.query(Trade).filter(
        Trade.user_id    == user.id,
        Trade.status     == "closed",
        Trade.trade_date >= str(since),
        Trade.pnl        != None,
    ).order_by(Trade.trade_date, Trade.closed_at).all()

    # Group by date
    from collections import defaultdict
    by_date = defaultdict(list)
    for t in trades:
        by_date[t.trade_date].append(t)

    # Build daily summary with running compound total
    days = []
    running_total = 0.0

    # Get all-time total before the window for accurate compound start
    prior_trades = db.query(Trade).filter(
        Trade.user_id   == user.id,
        Trade.status    == "closed",
        Trade.trade_date < str(since),
        Trade.pnl       != None,
    ).all()
    running_total = sum(t.pnl or 0 for t in prior_trades)

    for trade_date in sorted(by_date.keys()):
        day_trades = by_date[trade_date]
        day_pnl    = sum(t.pnl or 0 for t in day_trades)
        running_total += day_pnl
        wins   = sum(1 for t in day_trades if (t.pnl or 0) > 0)
        losses = sum(1 for t in day_trades if (t.pnl or 0) <= 0)

        days.append({
            "date":          trade_date,
            "day_pnl":       round(day_pnl, 2),
            "running_total": round(running_total, 2),
            "trades":        len(day_trades),
            "wins":          wins,
            "losses":        losses,
            "win_rate":      round(wins / len(day_trades) * 100, 1) if day_trades else 0,
            "best_trade":    round(max((t.pnl or 0) for t in day_trades), 2),
            "worst_trade":   round(min((t.pnl or 0) for t in day_trades), 2),
            "trade_list": [
                {
                    "id":        t.id,
                    "symbol":    t.symbol,
                    "side":      t.side,
                    "qty":       float(t.qty or 0),
                    "entry":     float(getattr(t, 'entry_price', 0) or 0),
                    "exit":      float(getattr(t, 'exit_price',  0) or 0),
                    "pnl":       round(float(t.pnl or 0), 2),
                    "running":   None,
                    "time":      str(getattr(t, 'closed_at', None) or getattr(t, 'opened_at', None) or ""),
                    "setup":     getattr(t, 'setup_type', '') or "",
                    "conf":      round(float(getattr(t, 'confidence', 0) or 0) * 100, 0),
                }
                for t in day_trades
            ],
        })

    # Fill per-trade running total within each day
    day_running = running_total - sum(d["day_pnl"] for d in days)
    for day in days:
        day_running += 0
        trade_running = day_running
        for t in day["trade_list"]:
            trade_running += t["pnl"]
            t["running"] = round(trade_running, 2)
        day_running = day["running_total"]

    # Summary stats
    all_pnl  = [t.pnl or 0 for t in trades]
    total_trades = len(all_pnl)

    return {
        "period":          period,
        "since":           str(since),
        "total_pnl":       round(sum(all_pnl), 2),
        "all_time_total":  round(running_total, 2),
        "total_trades":    total_trades,
        "winning_days":    sum(1 for d in days if d["day_pnl"] > 0),
        "losing_days":     sum(1 for d in days if d["day_pnl"] < 0),
        "best_day":        round(max((d["day_pnl"] for d in days), default=0), 2),
        "worst_day":       round(min((d["day_pnl"] for d in days), default=0), 2),
        "avg_day":         round(sum(d["day_pnl"] for d in days) / len(days), 2) if days else 0,
        "days":            days,
    }


@app.get("/api/report/today", tags=["Reports"])
async def daily_report(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """
    Always reads today's stats from DB so data survives restarts.
    Also includes live in-memory data if bot is running.
    """
    from database.models import Trade
    from datetime import date

    today = str(date.today())

    # Get closed trades from DB (persistent)
    db_trades = db.query(Trade).filter(
        Trade.user_id    == user.id,
        Trade.trade_date == today,
    ).all()

    closed = [t for t in db_trades if t.status == "closed" and t.pnl is not None]
    open_t = [t for t in db_trades if t.status == "open"]

    realized_pnl = round(sum(t.pnl or 0 for t in closed), 2)
    wins         = sum(1 for t in closed if (t.pnl or 0) > 0)
    losses       = sum(1 for t in closed if (t.pnl or 0) <= 0)
    win_rate     = round(wins / len(closed) * 100, 1) if closed else 0
    best_trade   = max((t.pnl or 0 for t in closed), default=0)
    worst_trade  = min((t.pnl or 0 for t in closed), default=0)

    # Live unrealized from bot if running
    unrealized = 0.0
    positions  = []
    if bot_loop.broker:
        positions  = bot_loop.broker.get_positions()
        unrealized = sum(float(p.get("unrealized_pnl", 0)) for p in positions)

    # Merge with in-memory tracker (might have trades not yet saved)
    mem_stats = tracker.stats()
    if mem_stats["realized_pnl"] > realized_pnl:
        realized_pnl = mem_stats["realized_pnl"]

    target_min = user.daily_target_min or config.DAILY_TARGET_MIN
    target_max = user.daily_target_max or config.DAILY_TARGET_MAX
    progress   = round(min(max(realized_pnl / target_min * 100, 0), 100), 1) if target_min > 0 else 0

    signals = bot_loop.get_latest_signals()
    plan    = goal_engine.get_current_plan()

    return {
        "date":            today,
        "summary": {
            "realized_pnl":   realized_pnl,
            "unrealized_pnl": round(unrealized, 2),
            "total_pnl":      round(realized_pnl + unrealized, 2),
            "total_trades":   len(closed),
            "open_positions": len(open_t),
            "wins":           wins,
            "losses":         losses,
            "win_rate":       win_rate,
            "best_trade":     round(best_trade, 2),
            "worst_trade":    round(worst_trade, 2),
            "target_min":     target_min,
            "target_max":     target_max,
            "progress_pct":   progress,
            "min_target_hit": realized_pnl >= target_min,
            "max_target_hit": realized_pnl >= target_max,
        },
        "trades": [
            {
                "symbol":      t.symbol,
                "side":        t.side,
                "qty":         t.qty,
                "entry_price": t.entry_price,
                "exit_price":  t.exit_price,
                "stop_loss":   t.stop_loss,
                "take_profit": t.take_profit,
                "pnl":         round(t.pnl or 0, 2),
                "pnl_pct":     round(t.pnl_pct or 0, 2),
                "status":      t.status,
                "opened_at":   t.opened_at.isoformat() if t.opened_at else "",
                "trade_date":  t.trade_date,
                "confidence":  t.confidence,
            }
            for t in sorted(db_trades, key=lambda x: x.opened_at or datetime.min, reverse=True)
        ],
        "positions": positions,
        "signals":   signals[:10],
        "goal":      plan,
        "session": {
            "bot_status":    bot_loop.status,
            "session_start": mem_stats.get("session_start"),
            "session_stop":  mem_stats.get("session_stop"),
            "db_loaded":     mem_stats.get("db_loaded", False),
        },
        "events": reporter.get_events(20),
    }

@app.get("/api/report/events", tags=["Reports"])
async def get_events(limit: int = 50, event_type: str = None,
                     user: User = Depends(get_current_user)):
    return reporter.get_events(limit, event_type)

@app.get("/api/report/live-activity", tags=["Reports"])
async def live_activity(user: User = Depends(get_current_user)):
    stats     = tracker.stats()
    positions = bot_loop.broker.get_positions() if bot_loop.broker else []
    signals   = bot_loop.get_latest_signals()
    return {
        "stats":     stats,
        "positions": positions,
        "signals":   signals,
        "events":    reporter.get_events(30),
        "bot_status": bot_loop.status,
        "active_watchlist": bot_loop.watchlist,
    }

# ══════════════════════════════════════════════════════════════════════════════
# Regime, VWAP, Setup Classifier
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/milestones", tags=["Strategy"])
async def get_milestones(user: User = Depends(get_current_user)):
    """Get user's profit milestone configuration."""
    return {"milestones": settings.get_profit_milestones()}

@app.put("/api/milestones", tags=["Strategy"])
async def set_milestones(
    body: dict,
    user: User = Depends(get_current_user),
):
    """Save user-configured profit milestones."""
    milestones = body.get("milestones", [])
    if not milestones or len(milestones) < 1:
        raise HTTPException(400, "At least 1 milestone required")
    settings.set_profit_milestones(milestones)
    # Apply to running engine immediately
    global _hybrid_engine
    if _hybrid_engine and _hybrid_engine.crypto_engine:
        _hybrid_engine.crypto_engine.set_milestones(settings.get_profit_milestones())
    return {"milestones": settings.get_profit_milestones(), "status": "saved"}


@app.get("/api/day-plan", tags=["Strategy"])
async def get_day_plan(user: User = Depends(get_current_user)):
    """Get today's smart capital allocation plan."""
    global _hybrid_engine
    if _hybrid_engine and _hybrid_engine.planner:
        return _hybrid_engine.planner.get_api_summary()
    # Build a standalone plan if hybrid engine not running
    try:
        from strategy.capital_planner import CapitalPlanner
        broker  = bot_loop.broker
        if not broker:
            raise HTTPException(400, "Start the bot first")
        planner = CapitalPlanner(settings, broker,
                                  getattr(user, "crypto_alloc", 0.30))
        return planner.get_api_summary()
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/regime", tags=["Analysis"])
async def get_regime(user: User = Depends(get_current_user)):
    """Get current market regime based on SPY analysis."""
    if not bot_loop.broker:
        raise HTTPException(400, "Start the bot first")
    try:
        from data.regime_detector import RegimeDetector
        from data.indicators       import add_all_indicators
        import numpy as np
        df = bot_loop.broker.get_bars("SPY", "5Min", 100)
        if df.empty:
            raise HTTPException(400, "No SPY data available")
        df = add_all_indicators(df)
        detector = RegimeDetector()
        result   = detector.detect(df)

        # Sanitize numpy types recursively
        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_clean(v) for v in obj]
            if isinstance(obj, (np.bool_, np.bool8 if hasattr(np, 'bool8') else np.bool_)):
                return bool(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        return _clean(result)
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/setup/{symbol}", tags=["Analysis"])
async def get_setup(symbol: str, user: User = Depends(get_current_user)):
    """Classify the current setup for a symbol."""
    if not bot_loop.broker:
        raise HTTPException(400, "Start the bot first")
    try:
        from data.regime_detector   import RegimeDetector
        from data.vwap              import get_vwap_signal
        from data.indicators        import add_all_indicators
        from strategy.setup_classifier import SetupClassifier

        df = bot_loop.broker.get_bars(symbol.upper(), "5Min", 100)
        if df.empty:
            raise HTTPException(400, f"No data for {symbol}")
        df   = add_all_indicators(df)
        spy  = bot_loop.broker.get_bars("SPY", "5Min", 100)
        spy  = add_all_indicators(spy) if not spy.empty else df

        regime   = RegimeDetector().detect(spy)
        vwap     = get_vwap_signal(df)
        last     = df.iloc[-1]
        indicators = {
            "rsi": float(last.get("rsi", 50)),
            "macd_diff": float(last.get("macd_diff", 0)),
            "bb_pct": float(last.get("bb_pct", 0.5)),
            "atr": float(last.get("atr", 0)),
            "volume_ratio": float(last.get("volume_ratio", 1.0)),
        }
        setup = SetupClassifier().classify(df, symbol.upper(), regime, vwap, indicators)
        return {**setup, "vwap_info": vwap, "regime": regime}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/rules/check/{symbol}", tags=["Analysis"])
async def check_rules(symbol: str, user: User = Depends(get_current_user)):
    """Run all hard rules for a symbol and return pass/fail details."""
    if not bot_loop.broker:
        raise HTTPException(400, "Start the bot first")
    try:
        from data.regime_detector      import RegimeDetector
        from data.vwap                 import get_vwap_signal
        from data.indicators           import add_all_indicators
        from strategy.setup_classifier import SetupClassifier
        from strategy.hard_rules       import HardRulesEngine

        df  = bot_loop.broker.get_bars(symbol.upper(), "5Min", 100)
        spy = bot_loop.broker.get_bars("SPY", "5Min", 100)
        if df.empty:
            raise HTTPException(400, f"No data for {symbol}")
        df  = add_all_indicators(df)
        spy = add_all_indicators(spy) if not spy.empty else df

        regime = RegimeDetector().detect(spy)
        vwap   = get_vwap_signal(df)
        last   = df.iloc[-1]
        price  = float(last["close"])
        indicators = {
            "rsi": float(last.get("rsi", 50)),
            "macd_diff": float(last.get("macd_diff", 0)),
            "bb_pct": float(last.get("bb_pct", 0.5)),
            "atr": float(last.get("atr", 0)),
            "volume_ratio": float(last.get("volume_ratio", 1.0)),
        }
        setup  = SetupClassifier().classify(df, symbol.upper(), regime, vwap, indicators)
        acct   = bot_loop.broker.get_account()
        equity = float(acct.get("equity", user.capital)) if acct else user.capital

        rules  = HardRulesEngine().check_all(
            symbol=symbol.upper(), price=price, setup=setup,
            vwap_info=vwap, regime=regime,
            daily_pnl=tracker.realized_pnl,
            capital=equity,
            open_positions=len(bot_loop.broker.get_positions()),
            daily_loss_limit=user.max_daily_loss,
        )
        return {**rules, "setup": setup, "regime": regime, "vwap": vwap}
    except Exception as e:
        raise HTTPException(500, str(e))

# ══════════════════════════════════════════════════════════════════════════════
# Dynamic Watchlist — manual rebuild trigger
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/watchlist/rebuild", tags=["Watchlist"])
async def rebuild_dynamic_watchlist(user: User = Depends(get_current_user)):
    """Force an immediate rebuild of the dynamic watchlist from live market data."""
    if not bot_loop.broker:
        raise HTTPException(400, "Start the bot first — needs live market data")
    try:
        await bot_loop._build_dynamic_watchlist()
        scores = bot_loop._wl_builder.get_scores()
        return {
            "status":    "rebuilt",
            "watchlist": bot_loop._wl_builder._dynamic_list,
            "built_at":  scores.get("built_at"),
            "scores":    scores.get("scores", {}),
            "total_scanned": scores.get("total_scanned", 0),
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/watchlist/scores", tags=["Watchlist"])
async def get_watchlist_scores(user: User = Depends(get_current_user)):
    """Get scores/reasons for why each stock was selected."""
    return bot_loop._wl_builder.get_scores()

# ══════════════════════════════════════════════════════════════════════════════
# Live Ticker — real-time prices for watchlist
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/ticker", tags=["Data"])
async def get_live_ticker(user: User = Depends(get_current_user)):
    """Get live prices for all watchlist symbols."""
    wl = settings.get_watchlist()
    if not wl:
        return {}
    try:
        prices = await mkt_scanner.get_live_prices(wl)
        return prices
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/ticker/{symbol}", tags=["Data"])
async def get_symbol_price(symbol: str, user: User = Depends(get_current_user)):
    """Get live price for a single symbol."""
    prices = await mkt_scanner.get_live_prices([symbol.upper()])
    return prices.get(symbol.upper(), {})

@app.get("/api/bot/active-watchlist", tags=["Bot"])
async def get_active_watchlist(user: User = Depends(get_current_user)):
    """Show exactly what stocks the bot is currently scanning."""
    if bot_loop._dynamic_mode and bot_loop._wl_builder._dynamic_list:
        active = bot_loop._wl_builder.get_active_list()
        scores = bot_loop._wl_builder.get_scores()
        return {
            "mode":     "dynamic",
            "watchlist": active,
            "scores":   scores.get("scores", {}),
            "built_at": scores.get("built_at", ""),
            "total_scanned": scores.get("total_scanned", 0),
            "manual_also_scanned": settings.get_watchlist(),
        }
    else:
        return {
            "mode":      "manual",
            "watchlist": settings.get_watchlist(),
            "scores":    {},
        }


# ── Symbol AI Strategy Engine ─────────────────────────────────────────────────

@app.post("/api/ai/symbol-sentiment", tags=["Analysis"])
async def ai_symbol_sentiment(
    body:    dict,
    request: Request,
    user:    User    = Depends(get_current_user),
    db:      Session = Depends(get_db),
):
    """
    Full AI analysis for a symbol: entry/exit strategy, indicators, sentiment.
    Results are cached per tier to control OpenAI costs.
    Admin-configurable refresh intervals per plan.
    """
    symbol = (body.get("symbol") or "").upper()
    if not symbol:
        raise HTTPException(400, "symbol required")

    is_admin = getattr(user, "is_admin", False)
    tier     = "admin" if is_admin else (getattr(user, "subscription_tier", "free") or "free")

    # ── Cache check — save OpenAI costs ──────────────────────────────────────
    try:
        from services.ai_cache import AIAnalysisCache, is_ai_enabled, get_refresh_interval
        cache = AIAnalysisCache(db)

        if not is_ai_enabled(db):
            raise HTTPException(503, "AI analysis is currently disabled by admin")

        cached = cache.get_cached(symbol, "sentiment", tier, is_admin=is_admin)
        if cached:
            logger.info(f"AI cache HIT: {symbol} for tier={tier} — age {cached.get('_cache_age_s')}s")
            return cached
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Cache check failed: {e} — proceeding to API call")
        cache = None

    try:
        from data.indicators        import add_all_indicators, score_symbol
        from data.regime_detector   import RegimeDetector
        from data.vwap              import get_vwap_signal

        if not bot_loop.broker:
            # Try standalone client
            try:
                from broker.alpaca_client import AlpacaClient
                import config as _cfg
                if _cfg.ALPACA_API_KEY:
                    _broker = AlpacaClient(_cfg.ALPACA_API_KEY,
                                           getattr(_cfg, 'ALPACA_SECRET_KEY', ''),
                                           getattr(_cfg, 'ALPACA_MODE', 'paper'))
                else:
                    raise Exception("No API key")
            except Exception:
                price = body.get("price") or 0
                change = body.get("change_pct") or 0
                return {
                    "symbol":    symbol,
                    "signal":    "HOLD",
                    "sentiment": "neutral",
                    "score":     50,
                    "confidence": 45,
                    "reasoning": "Connect your broker API keys to enable full live AI analysis with real chart data.",
                    "entry":     None, "exit": None, "stop": None, "risk_reward": None,
                    "indicators": {}, "key_levels": {},
                }
        else:
            _broker = bot_loop.broker

        # Get bars at multiple timeframes
        df1  = _broker.get_bars(symbol, "1Min",  50)
        df5  = _broker.get_bars(symbol, "5Min",  100)
        spy  = _broker.get_bars("SPY",  "5Min",  50)

        if df5.empty:
            raise HTTPException(400, f"No data for {symbol}")

        df5  = add_all_indicators(df5)
        df1  = add_all_indicators(df1) if not df1.empty else df5
        spy  = add_all_indicators(spy) if not spy.empty else df5

        regime  = RegimeDetector().detect(spy)
        vwap    = get_vwap_signal(df5)
        scored  = score_symbol(df5)
        last    = df5.iloc[-1]
        prev    = df5.iloc[-2] if len(df5) > 1 else last

        price   = float(last["close"])
        rsi     = float(last.get("rsi", 50))
        macd_d  = float(last.get("macd_diff", 0))
        bb_pct  = float(last.get("bb_pct", 0.5))
        bb_up   = float(last.get("bb_upper", price * 1.02))
        bb_low  = float(last.get("bb_lower", price * 0.98))
        bb_mid  = float(last.get("bb_mid",   price))
        vol     = float(last.get("volume",   0))
        avg_vol = float(df5["volume"].mean()) if "volume" in df5 else 1
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1

        # Build signal
        signal    = scored.get("signal", "HOLD")
        score     = scored.get("score", 50)
        reasons   = scored.get("reasons", [])
        confidence= min(90, max(30, abs(score - 50) * 2 + 40))

        # Entry / exit / stop calculation
        atr = float(df5["close"].diff().abs().rolling(14).mean().iloc[-1]) if len(df5) > 14 else price * 0.01

        if signal == "BUY":
            entry = round(price, 2)
            stop  = round(price - atr * 1.5, 2)
            exit_ = round(price + atr * 3.0, 2)
            sentiment = "bullish"
        elif signal == "SELL":
            entry = round(price, 2)
            stop  = round(price + atr * 1.5, 2)
            exit_ = round(price - atr * 3.0, 2)
            sentiment = "bearish"
        else:
            entry = None
            stop  = round(price - atr * 1.0, 2)
            exit_ = round(price + atr * 1.5, 2)
            sentiment = "neutral"

        rr = round(abs(exit_ - entry) / abs(stop - entry), 2) if entry and stop != entry else None

        # Plain-language reasoning
        parts = []
        if rsi < 30:   parts.append(f"RSI is deeply oversold at {rsi:.0f} — potential bounce zone")
        elif rsi > 70: parts.append(f"RSI is overbought at {rsi:.0f} — momentum may be fading")
        else:          parts.append(f"RSI at {rsi:.0f} is neutral")

        if macd_d > 0: parts.append("MACD is bullish — momentum favoring buyers")
        else:          parts.append("MACD is bearish — sellers have momentum")

        if bb_pct < 0.2:  parts.append("Price near lower Bollinger Band — potential mean-reversion buy")
        elif bb_pct > 0.8:parts.append("Price near upper Bollinger Band — extended, watch for pullback")

        if vol_ratio > 1.5: parts.append(f"Volume is {vol_ratio:.1f}x average — institutional activity detected")

        if vwap.get("signal") == "BUY":   parts.append("Price is above VWAP — bullish intraday bias")
        elif vwap.get("signal") == "SELL": parts.append("Price is below VWAP — bearish intraday bias")

        parts.append(f"Market regime: {regime.get('regime','unknown')}.")

        return {
            "symbol":     symbol,
            "signal":     signal,
            "sentiment":  sentiment,
            "score":      int(score),
            "confidence": int(confidence),
            "reasoning":  " ".join(parts),
            "reasons":    reasons,
            "entry":      entry,
            "exit":       exit_,
            "stop":       stop,
            "risk_reward":rr,
            "indicators": {
                "rsi":      round(rsi, 1),
                "macd_diff":round(macd_d, 4),
                "bb_pct":   round(bb_pct, 2),
                "bb_upper": round(bb_up, 2),
                "bb_lower": round(bb_low, 2),
                "bb_mid":   round(bb_mid, 2),
                "vol_ratio":round(vol_ratio, 2),
                "atr":      round(atr, 4),
            },
            "key_levels": {
                "support":    round(bb_low, 2),
                "resistance": round(bb_up,  2),
                "vwap":       round(vwap.get("vwap", price), 2),
            },
            "regime":    regime,
            "vwap":      vwap,
            "generated_at": str(df5.index[-1]) if hasattr(df5.index[-1], "isoformat") else "",
            "_cached":   False,
            "_tier":     tier,
        }

        # ── Store in cache ────────────────────────────────────────────────────
        try:
            if cache:
                cache.store(symbol, "sentiment", result, user_id=user.id)
        except Exception as ce:
            logger.warning(f"Cache store failed: {ce}")

        # ── Generate trade alert if strong signal ─────────────────────────────
        try:
            from services.alerts import maybe_create_alert
            from database.models import CompanySettings
            min_conf_setting = db.query(CompanySettings).filter_by(key="alert_confidence_min").first()
            min_conf = int(min_conf_setting.value) if min_conf_setting else 65
            maybe_create_alert(db, user.id, symbol, result, min_confidence=min_conf)
        except Exception as ae:
            logger.warning(f"Alert creation failed: {ae}")

        return result
        raise
    except Exception as e:
        logger.error(f"ai_symbol_sentiment({symbol}): {e}")
        raise HTTPException(500, str(e))


@app.get("/api/chart/{symbol}/bars", tags=["Data"])
async def get_symbol_bars(
    symbol:    str,
    timeframe: str = "5Min",
    limit:     int = 200,
    user:      User = Depends(get_current_user)
):
    """Get OHLCV bars for charting — works with or without bot running."""
    import pandas as pd
    from datetime import datetime, timezone, timedelta

    def _get_broker():
        if bot_loop.broker:
            return bot_loop.broker
        # Standalone client when bot not running
        try:
            from broker.alpaca_client import AlpacaClient
            import config
            if config.ALPACA_API_KEY:
                return AlpacaClient(config.ALPACA_API_KEY,
                                    getattr(config, 'ALPACA_SECRET_KEY', ''),
                                    getattr(config, 'ALPACA_MODE', 'paper'))
        except Exception:
            pass
        return None

    broker = _get_broker()
    if not broker:
        return []
    try:
        df = broker.get_bars(symbol.upper(), timeframe, limit)
        if df.empty:
            return []
        df = df.reset_index()
        out = []
        for _, row in df.iterrows():
            ts = row.get("timestamp", row.get("index", ""))
            try:
                t = int(pd.Timestamp(ts).timestamp())
            except:
                t = 0
            if t == 0:
                continue
            out.append({
                "time":   t,
                "open":   round(float(row.get("open",  0)), 4),
                "high":   round(float(row.get("high",  0)), 4),
                "low":    round(float(row.get("low",   0)), 4),
                "close":  round(float(row.get("close", 0)), 4),
                "volume": int(row.get("volume", 0)),
            })
        return out
    except Exception as e:
        logger.error(f"get_symbol_bars({symbol}): {e}")
        return []


# ── Trade Alerts ──────────────────────────────────────────────────────────────

@app.get("/api/alerts", tags=["Alerts"])
async def get_alerts(
    limit:  int  = 50,
    unread: bool = False,
    user:   User = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    """Get trade alerts for the current user."""
    from database.models import TradeAlert
    q = db.query(TradeAlert).filter_by(user_id=user.id)
    if unread:
        q = q.filter_by(is_read=False)
    alerts = q.order_by(TradeAlert.created_at.desc()).limit(limit).all()
    return [
        {
            "id":         a.id,
            "symbol":     a.symbol,
            "alert_type": a.alert_type,
            "signal":     a.signal,
            "price":      a.price,
            "target":     a.target,
            "stop":       a.stop,
            "confidence": a.confidence,
            "message":    a.message,
            "is_read":    a.is_read,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]


@app.get("/api/alerts/count", tags=["Alerts"])
async def get_alert_count(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Unread alert count — called frequently for the bell badge."""
    from database.models import TradeAlert
    count = db.query(TradeAlert).filter_by(user_id=user.id, is_read=False).count()
    return {"unread": count}


@app.post("/api/alerts/read", tags=["Alerts"])
async def mark_alerts_read(
    body: dict,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Mark one or all alerts as read."""
    from database.models import TradeAlert
    alert_id = body.get("id")
    if alert_id:
        db.query(TradeAlert).filter_by(id=alert_id, user_id=user.id).update({"is_read": True})
    else:
        db.query(TradeAlert).filter_by(user_id=user.id, is_read=False).update({"is_read": True})
    db.commit()
    return {"status": "ok"}


@app.get("/api/alerts/today", tags=["Alerts"])
async def get_today_alerts(
    symbol: str  = "",
    user:   User = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    """All alerts for today — used in the day summary panel."""
    from database.models import TradeAlert
    from datetime import date
    today_str = datetime.utcnow().date().isoformat()
    q = db.query(TradeAlert).filter(
        TradeAlert.user_id    == user.id,
        TradeAlert.created_at >= today_str,
    )
    if symbol:
        q = q.filter(TradeAlert.symbol == symbol.upper())
    alerts = q.order_by(TradeAlert.created_at.desc()).all()
    return [
        {
            "id":         a.id,
            "symbol":     a.symbol,
            "alert_type": a.alert_type,
            "signal":     a.signal,
            "price":      a.price,
            "target":     a.target,
            "stop":       a.stop,
            "confidence": a.confidence,
            "message":    a.message,
            "is_read":    a.is_read,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]


# ── AI Cache Config ───────────────────────────────────────────────────────────

@app.get("/api/ai/cache-status/{symbol}", tags=["Analysis"])
async def ai_cache_status(
    symbol: str,
    user:   User    = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    """How fresh is the cached AI analysis for this symbol + current tier."""
    from services.ai_cache import AIAnalysisCache, get_refresh_interval
    is_admin = getattr(user, "is_admin", False)
    tier     = "admin" if is_admin else (getattr(user, "subscription_tier", "free") or "free")
    cache    = AIAnalysisCache(db)
    status   = cache.get_cache_status(symbol.upper(), "sentiment", tier)
    return {
        **status,
        "tier":     tier,
        "is_admin": is_admin,
        "upgrade_for_realtime": not is_admin and tier == "free",
    }