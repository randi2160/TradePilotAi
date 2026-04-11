"""
Peak Bounce API routes — all endpoints for the bounce strategy.
Prefix: /api/bounce
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth           import get_current_user
from database.database   import get_db
from database.models     import User
from strategy.peak_bounce import PeakBounceEngine, WINDOWS, DEFAULT_WINDOW

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bounce", tags=["Peak Bounce Strategy"])

# ── Singleton engine (shared, reset daily) ────────────────────────────────────
_engine: Optional[PeakBounceEngine] = None

def get_engine(user: User) -> PeakBounceEngine:
    global _engine
    if _engine is None or _engine.capital != user.capital:
        _engine = PeakBounceEngine(
            capital    = user.capital,
            daily_goal = user.daily_target_max,
        )
    return _engine


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    symbol: str
    window: str = Field(DEFAULT_WINDOW, description="30min|1hour|2hour|4hour|fullday")

class LadderRequest(BaseModel):
    symbol:        str
    bounce_target: Optional[float] = Field(None, description="None = AI calculates")

class BounceSettingsBody(BaseModel):
    symbol:        str
    bounce_target: Optional[float] = None
    window:        str             = DEFAULT_WINDOW
    auto_execute:  bool            = True
    use_ai_stocks: bool            = True
    manual_stocks: list            = []


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/windows", summary="Get all available time windows")
async def get_windows(user: User = Depends(get_current_user)):
    return {
        "windows":        WINDOWS,
        "default":        DEFAULT_WINDOW,
        "default_reason": "2-hour window gives the best balance of pattern reliability and intraday opportunity",
    }


@router.post("/analyze", summary="Analyze peak/valley pattern for a stock")
async def analyze(
    body: AnalyzeRequest,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    import main as _app_module
    bot_loop = getattr(_app_module, "bot_loop", None)
    if not bot_loop.broker:
        raise HTTPException(400, "Start the bot first to load market data")

    engine = get_engine(user)
    symbol = body.symbol.upper()
    window = body.window if body.window in WINDOWS else DEFAULT_WINDOW

    # Get bar data
    bars_needed = WINDOWS[window]["bars"] + 20
    df = bot_loop.broker.get_bars(symbol, timeframe="5Min", limit=bars_needed)
    if df.empty:
        raise HTTPException(400, f"No market data for {symbol}")

    from data.indicators import add_all_indicators
    df = add_all_indicators(df)

    pattern = engine.analyze_pattern(df, symbol, window)
    if not pattern:
        return {
            "symbol":  symbol,
            "found":   False,
            "message": f"No reliable bounce pattern found for {symbol} in the {WINDOWS[window]['label']} window. Try a different window or stock.",
        }

    # Calculate position for current pattern
    position = engine.calculate_position(pattern, bounce_target=None, round_number=1)

    # Check entry signal
    should_enter, reason, confidence = engine.should_enter(pattern, df)

    return {
        "found":           True,
        "symbol":          symbol,
        "window":          window,
        "window_label":    WINDOWS[window]["label"],
        "pattern": {
            "avg_peak":         pattern.avg_peak,
            "avg_valley":       pattern.avg_valley,
            "bounce_height":    pattern.bounce_height,
            "bounce_pct":       pattern.bounce_pct,
            "success_rate":     pattern.success_rate,
            "avg_recovery_min": pattern.avg_recovery_min,
            "consistency":      pattern.consistency,
            "volume_confirmed": pattern.volume_confirmed,
            "pattern_strength": pattern.pattern_strength,
            "current_price":    pattern.current_price,
            "near_valley":      pattern.near_valley,
            "near_peak":        pattern.near_peak,
        },
        "position": {
            "shares":          position.shares          if position else 0,
            "entry_price":     position.entry_price     if position else 0,
            "exit_target":     position.exit_target     if position else 0,
            "stop_loss":       position.stop_loss       if position else 0,
            "position_value":  position.position_value  if position else 0,
            "target_profit":   position.target_profit   if position else 0,
            "execution_cost":  position.execution_cost  if position else 0,
            "net_profit_est":  position.net_profit_est  if position else 0,
            "min_margin_pct":  position.min_margin_pct  if position else 0,
        } if position else None,
        "entry_signal": {
            "should_enter": should_enter,
            "reason":       reason,
            "confidence":   confidence,
        },
    }


@router.post("/ladder/create", summary="Create a profit ladder for a symbol")
async def create_ladder(
    body: LadderRequest,
    user: User = Depends(get_current_user),
):
    engine  = get_engine(user)
    pattern = engine.get_pattern(body.symbol.upper())

    ladder = engine.create_ladder(
        symbol        = body.symbol.upper(),
        daily_goal    = user.daily_target_max,
        bounce_target = body.bounce_target,
        pattern       = pattern,
    )

    return {
        "symbol":               body.symbol.upper(),
        "daily_goal":           ladder.daily_goal,
        "bounce_target":        ladder.bounce_target,
        "total_bounces_needed": ladder.total_bounces_needed,
        "ai_calculated":        ladder.ai_calculated,
        "calculation_note":     ladder.calculation_note,
        "status":               "created",
    }


@router.get("/ladder/{symbol}", summary="Get current ladder progress")
async def get_ladder(symbol: str, user: User = Depends(get_current_user)):
    engine = get_engine(user)
    ladder = engine.get_ladder(symbol.upper())
    if not ladder:
        raise HTTPException(404, f"No ladder found for {symbol} — create one first")

    return {
        "symbol":               symbol.upper(),
        "daily_goal":           ladder.daily_goal,
        "bounce_target":        ladder.bounce_target,
        "total_bounces_needed": ladder.total_bounces_needed,
        "current_round":        ladder.current_round,
        "total_captured":       ladder.total_captured,
        "remaining":            ladder.remaining,
        "progress_pct":         round(ladder.total_captured / ladder.daily_goal * 100, 1),
        "is_complete":          ladder.is_complete,
        "completed_rounds":     ladder.completed_rounds,
        "ai_calculated":        ladder.ai_calculated,
        "calculation_note":     ladder.calculation_note,
    }


@router.get("/scan", summary="AI scans all stocks and ranks best bounce candidates")
async def scan_bounce_candidates(
    window: str = DEFAULT_WINDOW,
    user:   User = Depends(get_current_user),
):
    import main as _m; bot_loop = getattr(_m, "bot_loop", None)
    from data.market_scanner import MarketScanner
    from data.news_scanner   import NewsScanner
    import config

    engine = get_engine(user)
    mkt    = MarketScanner()
    news   = NewsScanner()

    # Get market data (works without bot)
    try:
        scan_result = await mkt.scan()
        gainers     = scan_result.get("gainers", [])
    except Exception:
        gainers     = []
        scan_result = {}

    # Build symbol list — use watchlist if bot running, else defaults
    try:
        watchlist = bot_loop.watchlist if bot_loop else list(config.DEFAULT_WATCHLIST)
    except Exception:
        watchlist = list(config.DEFAULT_WATCHLIST)

    gainer_syms = [g["symbol"] for g in gainers[:10]]
    all_syms    = list(dict.fromkeys(watchlist + gainer_syms))[:20]

    # Get sentiment
    try:
        sentiments = await news.scan_watchlist(all_syms)
    except Exception:
        sentiments = {}

    # Analyze patterns — only if bot/broker available
    results = []
    if bot_loop and bot_loop.broker:
        for symbol in all_syms:
            try:
                bars = WINDOWS.get(window, WINDOWS[DEFAULT_WINDOW])["bars"] + 20
                df   = bot_loop.broker.get_bars(symbol, "5Min", limit=bars)
                if df.empty:
                    continue
                from data.indicators import add_all_indicators
                df      = add_all_indicators(df)
                pattern = engine.analyze_pattern(df, symbol, window)
                if pattern and pattern.pattern_strength >= 30:
                    results.append(pattern)
            except Exception as e:
                logger.debug(f"scan {symbol}: {e}")
    else:
        return {
            "window":       window,
            "window_label": WINDOWS.get(window, {}).get("label", window),
            "scanned":      0,
            "found":        0,
            "candidates":   [],
            "best_pick":    None,
            "message":      "Start the bot first to enable pattern scanning. Go to the ⚙️ Bot tab and click Start Bot.",
        }

    # Score and rank
    pattern_dict = {p.symbol: p for p in results}
    ranked = engine.score_stocks_for_bounce(pattern_dict, sentiments, gainers)

    return {
        "window":       window,
        "window_label": WINDOWS.get(window, {}).get("label", window),
        "scanned":      len(all_syms),
        "found":        len(results),
        "candidates":   ranked[:10],
        "best_pick":    ranked[0] if ranked else None,
    }


@router.get("/patterns", summary="Get all currently analyzed patterns")
async def get_patterns(user: User = Depends(get_current_user)):
    engine = get_engine(user)
    return engine.get_all_patterns()


@router.get("/calculate", summary="Calculate optimal position size")
async def calculate_position(
    symbol:        str,
    bounce_target: Optional[float] = None,
    user:          User = Depends(get_current_user),
):
    engine  = get_engine(user)
    pattern = engine.get_pattern(symbol.upper())
    if not pattern:
        raise HTTPException(404, f"Analyze {symbol} first")

    pos = engine.calculate_position(
        pattern       = pattern,
        bounce_target = bounce_target,
        round_number  = 1,
    )
    if not pos:
        raise HTTPException(400, "Bounce too small to trade profitably after costs")

    return {
        "symbol":          pos.symbol,
        "shares":          pos.shares,
        "entry_price":     pos.entry_price,
        "exit_target":     pos.exit_target,
        "stop_loss":       pos.stop_loss,
        "position_value":  pos.position_value,
        "target_profit":   pos.target_profit,
        "execution_cost":  pos.execution_cost,
        "net_profit_est":  pos.net_profit_est,
        "min_margin_pct":  pos.min_margin_pct,
        "ai_calculated":   bounce_target is None,
        "math_breakdown": {
            "bounce_height_gross":    pattern.bounce_height,
            "slippage_cost_per_share": round(pos.entry_price * 0.001, 4),
            "net_per_share":          round(pattern.bounce_height - pos.entry_price * 0.001, 4),
            "shares_needed_formula":  f"${pos.target_profit:.2f} target ÷ ${round(pattern.bounce_height - pos.entry_price*0.001,4):.4f} net/share = {pos.shares} shares",
            "position_pct_of_capital": round(pos.position_value / user.capital * 100, 1),
        },
    }
