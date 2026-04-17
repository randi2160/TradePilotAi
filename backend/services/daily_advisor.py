"""
Morviq AI — Smart Daily Trading Advisor

Handles:
1. User daily picks — symbols they want to trade today
2. AI market scan — finds best movers automatically
3. Portfolio optimizer — considers PDT, account balance, daily goal
4. Review/accept flow — logged to audit trail
5. AI vs User pick comparison — honest verdict
"""
import json
import logging
import os
from datetime   import datetime, timezone
from typing     import Optional, List

from fastapi    import APIRouter, Depends, HTTPException, Request
from pydantic   import BaseModel
from sqlalchemy.orm import Session

from auth.auth         import get_current_user
from database.database import get_db
from database.models   import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/daily", tags=["Daily Advisor"])

CRYPTO_SYMBOLS = {'BTC','ETH','LTC','BCH','LINK','AAVE','UNI','DOGE','SHIB','MATIC','SOL','ADA','XRP'}


# ── Helpers ───────────────────────────────────────────────────────────────────

def today() -> str:
    return str(datetime.now(timezone.utc).date())


def _get_setting(db: Session, key: str, default):
    try:
        from database.models import CompanySettings
        s = db.query(CompanySettings).filter_by(key=key).first()
        return s.value if s else default
    except Exception:
        return default


def _get_account_info(user: User, db: Session) -> dict:
    """Get live account info from Alpaca or fall back to user settings.

    SECURITY: per-user creds only — no .env fallback.
    """
    try:
        from broker.broker_routes import _get_broker_creds
        from broker.alpaca_client import AlpacaClient
        creds = _get_broker_creds(user)
        if creds and creds.get("api_key"):
            mode = getattr(user, "alpaca_mode", "paper")
            client = AlpacaClient(
                paper      = (mode != "live"),
                api_key    = creds["api_key"],
                api_secret = creds["api_secret"],
            )
            return client.get_account()
    except Exception as e:
        logger.warning(f"Account fetch failed: {e}")
    return {
        "equity":             getattr(user, "capital", 5000),
        "buying_power":       getattr(user, "capital", 5000),
        "daytrade_count":     0,
        "day_trades_remaining": 3,
        "is_pdt_exempt":      False,
    }


def _get_daily_goal(user: User) -> dict:
    target_min = getattr(user, "daily_target_min", None) or 100
    target_max = getattr(user, "daily_target_max", None) or 250
    target_min = float(target_min)
    target_max = float(target_max)
    return {"min": target_min, "max": target_max, "mid": (target_min + target_max) / 2}


# ── Portfolio Optimizer ───────────────────────────────────────────────────────

def optimize_portfolio(
    symbols:      List[str],
    analyses:     List[dict],
    account:      dict,
    goal:         dict,
    user:         User,
) -> dict:
    """
    Given AI analyses for multiple symbols, determine:
    - How much to allocate to each
    - How many trades to make
    - Which are highest priority
    - Whether PDT limits apply
    """
    buying_power     = account.get("buying_power", 5000)
    daytrade_remain  = account.get("day_trades_remaining", 3)
    is_pdt_exempt    = account.get("is_pdt_exempt", False)

    # Sort by AI score descending
    ranked = sorted(
        [a for a in analyses if a.get("signal") in ("BUY", "SELL")],
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    # PDT budget: how many day trades can we make?
    max_trades = 999 if is_pdt_exempt else daytrade_remain
    # Crypto is PDT exempt — add back
    crypto_count = sum(1 for s in symbols if s.upper() in CRYPTO_SYMBOLS)
    max_trades   = max_trades + crypto_count

    # Target per trade to hit daily goal
    target_per_trade = goal["mid"] / max(len(ranked), 1) if ranked else goal["mid"]

    # Allocate — risk max 15% per trade, min $200
    max_per_trade = min(buying_power * 0.15, buying_power / max(len(ranked), 1))
    max_per_trade = max(max_per_trade, 200)

    allocations = []
    total_allocated = 0
    for i, analysis in enumerate(ranked[:max_trades]):
        sym     = analysis.get("symbol", "")
        price   = float(analysis.get("entry") or analysis.get("price") or 1)
        is_crypto = sym.upper() in CRYPTO_SYMBOLS

        # Scale allocation by confidence
        conf_factor  = (analysis.get("confidence", 65) - 50) / 50  # 0–1
        alloc_amount = max_per_trade * (0.5 + conf_factor * 0.5)
        alloc_amount = min(alloc_amount, buying_power - total_allocated)
        if alloc_amount < 100:
            continue

        qty = max(1, int(alloc_amount / price)) if price > 0 else 1

        allocations.append({
            "rank":        i + 1,
            "symbol":      sym,
            "signal":      analysis.get("signal"),
            "confidence":  analysis.get("confidence", 0),
            "score":       analysis.get("score", 0),
            "entry":       analysis.get("entry"),
            "exit_target": analysis.get("exit"),
            "stop":        analysis.get("stop"),
            "risk_reward": analysis.get("risk_reward"),
            "suggested_qty":   qty,
            "suggested_alloc": round(alloc_amount, 2),
            "is_crypto":       is_crypto,
            "pdt_exempt":      is_pdt_exempt or is_crypto,
            "est_profit":      round(qty * (float(analysis.get("exit") or price) - price), 2) if analysis.get("exit") else None,
            "reasoning":       analysis.get("reasoning", ""),
        })
        total_allocated += alloc_amount

    return {
        "allocations":     allocations,
        "total_allocated": round(total_allocated, 2),
        "buying_power":    buying_power,
        "max_trades_today":max_trades,
        "daytrade_count":  account.get("daytrade_count", 0),
        "pdt_exempt":      is_pdt_exempt,
        "goal_min":        goal["min"],
        "goal_max":        goal["max"],
        "est_total_profit": round(sum(a.get("est_profit") or 0 for a in allocations), 2),
        "ranked_count":    len(allocations),
    }


# ── AI Analysis helper ─────────────────────────────────────────────────────────

async def _analyze_symbol(symbol: str, db: Session, user: User) -> dict:
    """Run AI/technical analysis for a symbol, using cache if available."""
    try:
        from services.ai_cache import AIAnalysisCache, get_refresh_interval
        is_admin = getattr(user, "is_admin", False)
        tier     = "admin" if is_admin else (getattr(user, "subscription_tier", "free") or "free")
        cache    = AIAnalysisCache(db)
        cached   = cache.get_cached(symbol, "sentiment", tier, is_admin=is_admin)
        if cached and cached.get("signal") in ("BUY","SELL"):
            cached["symbol"] = symbol
            return cached
    except Exception:
        pass

    # Technical analysis fallback — momentum + volume scoring
    try:
        import pandas as pd
        import numpy as np
        # Per-user broker lookup (the old `from scheduler.bot_loop import bot_loop`
        # no longer exists — bot_loop.py only exports the BotLoop class, not a
        # module-level singleton).
        import main as _app_module
        _bot = getattr(_app_module, "get_user_bot_if_exists", lambda uid: None)(user.id)
        broker = _bot.broker if _bot else None
        if not broker:
            raise Exception("No broker")

        bars = broker.get_bars(symbol, "5Min", 60)
        if bars is None or len(bars) < 20:
            raise Exception("No bars")

        closes  = bars["close"].values.astype(float)
        volumes = bars["volume"].values.astype(float)

        # Momentum
        momentum_5  = (closes[-1] - closes[-5])  / closes[-5]  * 100
        momentum_20 = (closes[-1] - closes[-20]) / closes[-20] * 100

        # Volume
        avg_vol   = np.mean(volumes[-20:])
        vol_spike = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

        # EMA trend
        def ema(arr, n):
            k = 2 / (n + 1); e = arr[0]
            for v in arr[1:]: e = v * k + e * (1 - k)
            return e

        ema8  = ema(closes[-30:], 8)
        ema21 = ema(closes[-30:], 21)
        trend_up = ema8 > ema21

        # ATR
        atr = float(np.mean(np.abs(np.diff(closes[-14:]))))
        price = float(closes[-1])

        # Signal
        bullish_score = 0
        if momentum_5  > 0.2:  bullish_score += 2
        if momentum_20 > 0.5:  bullish_score += 2
        if trend_up:            bullish_score += 2
        if vol_spike   > 1.5:   bullish_score += 2
        if momentum_5  < -0.2:  bullish_score -= 3
        if momentum_20 < -0.5:  bullish_score -= 3
        if not trend_up:        bullish_score -= 1

        if bullish_score >= 4:
            signal = "BUY"
            confidence = min(85, 60 + bullish_score * 3)
        elif bullish_score <= -3:
            signal = "SELL"
            confidence = min(80, 60 + abs(bullish_score) * 3)
        else:
            signal = "HOLD"
            confidence = 45

        entry  = round(price, 2)
        target = round(price * (1 + atr/price * 2), 2) if signal == "BUY" else round(price * (1 - atr/price * 2), 2)
        stop   = round(price * (1 - atr/price * 1.5), 2) if signal == "BUY" else round(price * (1 + atr/price * 1.5), 2)
        rr     = round(abs(target - entry) / abs(stop - entry), 2) if abs(stop - entry) > 0 else 1.0

        reasons = []
        if momentum_5  > 0: reasons.append(f"+{momentum_5:.2f}% 5-bar momentum")
        if momentum_20 > 0: reasons.append(f"+{momentum_20:.2f}% session momentum")
        if trend_up:        reasons.append("EMA8 > EMA21 uptrend")
        if vol_spike > 1.5: reasons.append(f"{vol_spike:.1f}x volume spike")

        return {
            "symbol":     symbol,
            "signal":     signal,
            "confidence": int(confidence),
            "score":      int(confidence),
            "entry":      entry,
            "exit":       target,
            "exit_target":target,
            "stop":       stop,
            "risk_reward":rr,
            "reasoning":  f"Technical: {', '.join(reasons) or 'neutral momentum'}. "
                          f"5m mom={momentum_5:+.2f}% 20-bar={momentum_20:+.2f}% vol={vol_spike:.1f}x",
        }
    except Exception as e:
        logger.debug(f"Technical analysis {symbol}: {e}")
        return {
            "symbol": symbol, "signal": "HOLD", "confidence": 45, "score": 45,
            "reasoning": "Unable to analyze — no market data available",
            "entry": None, "exit": None, "stop": None, "risk_reward": None,
        }


# ── Routes ────────────────────────────────────────────────────────────────────

class PickBody(BaseModel):
    symbol:  str
    note:    Optional[str] = None


class ReviewBody(BaseModel):
    action:  str            # reviewed | accepted | rejected
    notes:   Optional[str] = None


@router.get("/picks")
async def get_daily_picks(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Get user's pick list for today + their AI analyses."""
    from database.models import DailyUserPick, AIPickAnalysis
    picks   = db.query(DailyUserPick).filter_by(user_id=user.id, trade_date=today()).all()
    analyses= {a.symbol: a for a in db.query(AIPickAnalysis).filter_by(user_id=user.id, trade_date=today()).all()}

    result = []
    for p in picks:
        an = analyses.get(p.symbol)
        result.append({
            "id":         p.id,
            "symbol":     p.symbol,
            "note":       p.note,
            "added_at":   p.created_at.isoformat(),
            "analysis":   {
                "signal":       an.signal if an else None,
                "confidence":   an.confidence if an else None,
                "score":        an.score if an else None,
                "entry":        an.entry if an else None,
                "exit":         an.exit_target if an else None,
                "stop":         an.stop if an else None,
                "risk_reward":  an.risk_reward if an else None,
                "reasoning":    an.reasoning if an else None,
                "vs_ai_verdict":an.vs_ai_verdict if an else None,
                "full_report":  json.loads(an.full_report) if an and an.full_report else None,
                "analyzed_at":  an.created_at.isoformat() if an else None,
            } if an else None,
        })
    return {"date": today(), "picks": result, "count": len(result)}


@router.post("/picks")
async def add_pick(
    body: PickBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Add a symbol to today's personal pick list."""
    from database.models import DailyUserPick
    symbol = body.symbol.upper().strip()
    if not symbol:
        raise HTTPException(400, "Symbol required")

    # Check duplicate
    exists = db.query(DailyUserPick).filter_by(user_id=user.id, symbol=symbol, trade_date=today()).first()
    if exists:
        return {"status": "already_added", "symbol": symbol}

    pick = DailyUserPick(user_id=user.id, symbol=symbol, note=body.note, trade_date=today())
    db.add(pick)
    db.commit()
    return {"status": "added", "symbol": symbol}


@router.delete("/picks/{symbol}")
async def remove_pick(
    symbol: str,
    user:   User    = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    from database.models import DailyUserPick
    db.query(DailyUserPick).filter_by(user_id=user.id, symbol=symbol.upper(), trade_date=today()).delete()
    db.commit()
    return {"status": "removed", "symbol": symbol.upper()}


@router.post("/picks/{symbol}/analyze")
async def analyze_pick(
    symbol: str,
    user:   User    = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    """Run full AI analysis on a user's pick and save report."""
    from database.models import AIPickAnalysis
    symbol = symbol.upper()

    # Get cached analysis
    analysis = await _analyze_symbol(symbol, db, user)

    # Build vs-AI verdict
    ai_recs = db.query(__import__("database.models", fromlist=["AIRecommendation"]).AIRecommendation)\
                .filter_by(user_id=user.id, trade_date=today()).all()
    ai_symbols = [r.symbol for r in ai_recs]

    verdict = ""
    if symbol in ai_symbols:
        rec = next(r for r in ai_recs if r.symbol == symbol)
        verdict = f"✅ AI AGREES — This symbol is also in AI's top picks (Rank #{rec.rank}). Both analyses align: {analysis.get('signal', 'HOLD')} signal with {analysis.get('confidence',50)}% confidence. Strong conviction."
    elif analysis.get("signal") == "BUY" and analysis.get("confidence", 0) >= 70:
        verdict = f"🟡 USER PICK LOOKS GOOD — AI didn't surface this automatically but the analysis shows a solid {analysis.get('signal')} signal ({analysis.get('confidence')}% confidence). Could be a valid opportunity AI's scanner missed."
    elif analysis.get("signal") == "HOLD" or analysis.get("confidence", 0) < 60:
        verdict = f"⚠️ WEAK SETUP — AI confidence is only {analysis.get('confidence', 50)}% on ${symbol}. Consider waiting for a stronger signal or check AI's top picks for better opportunities today."
    else:
        verdict = f"🔴 CAUTION — AI shows a {analysis.get('signal')} signal for ${symbol}. Review carefully before committing capital."

    # Store analysis
    existing = db.query(AIPickAnalysis).filter_by(user_id=user.id, symbol=symbol, trade_date=today()).first()
    if existing:
        existing.signal      = analysis.get("signal")
        existing.confidence  = analysis.get("confidence")
        existing.score       = analysis.get("score")
        existing.entry       = analysis.get("entry")
        existing.exit_target = analysis.get("exit")
        existing.stop        = analysis.get("stop")
        existing.risk_reward = analysis.get("risk_reward")
        existing.reasoning   = analysis.get("reasoning", "")
        existing.vs_ai_verdict = verdict
        existing.full_report = json.dumps(analysis)
    else:
        record = AIPickAnalysis(
            user_id=user.id, symbol=symbol, trade_date=today(),
            signal=analysis.get("signal"), confidence=analysis.get("confidence"),
            score=analysis.get("score"), entry=analysis.get("entry"),
            exit_target=analysis.get("exit"), stop=analysis.get("stop"),
            risk_reward=analysis.get("risk_reward"), reasoning=analysis.get("reasoning",""),
            vs_ai_verdict=verdict, full_report=json.dumps(analysis),
        )
        db.add(record)
    db.commit()
    return {**analysis, "vs_ai_verdict": verdict, "symbol": symbol}


@router.get("/recommendations")
async def get_recommendations(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Get today's AI recommendations with review status."""
    from database.models import AIRecommendation
    recs = db.query(AIRecommendation).filter_by(user_id=user.id, trade_date=today())\
             .order_by(AIRecommendation.rank).all()
    pending = sum(1 for r in recs if r.status == "pending")
    return {
        "date":    today(),
        "pending": pending,
        "recs": [{
            "id":            r.id, "rank": r.rank, "symbol": r.symbol,
            "signal":        r.signal, "confidence": r.confidence, "score": r.score,
            "entry":         r.entry, "exit": r.exit_target, "stop": r.stop,
            "risk_reward":   r.risk_reward,
            "suggested_qty": r.suggested_qty, "suggested_alloc": r.suggested_alloc,
            "reasoning":     r.reasoning, "source": r.source, "status": r.status,
            "asset_type":    "crypto" if "crypto" in (r.source or "") or "/" in (r.symbol or "") else "stock",
            "eligible_for_auto": r.eligible_for_auto,
            "reviewed_at":   r.reviewed_at.isoformat() if r.reviewed_at else None,
            "accepted_at":   r.accepted_at.isoformat() if r.accepted_at else None,
            "created_at":    r.created_at.isoformat(),
        } for r in recs]
    }


@router.post("/recommendations/{rec_id}/review")
async def review_recommendation(
    rec_id: int,
    body:   ReviewBody,
    request:Request,
    user:   User    = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    """User reviews/accepts/rejects an AI recommendation — logged to audit."""
    from database.models import AIRecommendation, UserReviewLog
    rec = db.query(AIRecommendation).filter_by(id=rec_id, user_id=user.id).first()
    if not rec:
        raise HTTPException(404, "Recommendation not found")

    if body.action not in ("reviewed", "accepted", "rejected"):
        raise HTTPException(400, "action must be: reviewed | accepted | rejected")

    now = datetime.utcnow()
    rec.status      = body.action
    rec.reviewed_at = now
    if body.action == "accepted":
        rec.accepted_at          = now
        rec.eligible_for_auto    = True   # NOW eligible for auto-trading
    elif body.action == "rejected":
        rec.eligible_for_auto    = False

    # Audit log
    ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    log = UserReviewLog(
        user_id=user.id, recommendation_id=rec_id,
        symbol=rec.symbol, action=body.action, notes=body.notes,
        ip_address=ip,
    )
    db.add(log)
    db.commit()

    return {
        "status":            body.action,
        "symbol":            rec.symbol,
        "eligible_for_auto": rec.eligible_for_auto,
        "logged_at":         now.isoformat(),
        "message": {
            "accepted": f"✅ ${rec.symbol} accepted — now eligible for auto-trading. Entry at ${rec.entry}.",
            "rejected": f"❌ ${rec.symbol} rejected — will not be auto-traded.",
            "reviewed": f"👁 ${rec.symbol} marked as reviewed.",
        }.get(body.action, "")
    }


@router.post("/scan")
async def run_daily_scan(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """
    Full daily scan:
    - Stocks: scan market for top 10 movers (gainers + volume)
    - Crypto: scan top 25 coins for momentum
    - Score all by momentum, volatility, volume
    - Rank and save top picks as AI recommendations
    No hardcoded watchlist — pure momentum discovery.
    """
    from database.models import AIRecommendation
    import asyncio

    account  = _get_account_info(user, db)
    goal     = _get_daily_goal(user)
    min_conf = 50  # minimum confidence to show

    # ── Step 1: Dynamic stock candidates from live market scan ────────────────
    stock_candidates = []
    try:
        import main as _app_module
        # Use the app-level scanner singleton (already has cached scan data)
        _scanner = getattr(_app_module, "mkt_scanner", None)
        if _scanner:
            gainers = _scanner.get_top_gainers(10)
            actives = _scanner.get_most_active(10)
            seen = set()
            for sym in gainers + actives:
                s = sym if isinstance(sym, str) else sym.get("symbol", "")
                if s and s not in seen:
                    stock_candidates.append(s)
                    seen.add(s)
        if not stock_candidates:
            # Trigger a fresh scan if no cached data
            scan_result = await _scanner.scan() if _scanner else {}
            for sym in scan_result.get("gainers", [])[:10] + scan_result.get("most_active", [])[:10]:
                s = sym if isinstance(sym, str) else sym.get("symbol", "")
                if s and s not in set(stock_candidates):
                    stock_candidates.append(s)
    except Exception as e:
        logger.warning(f"Stock scanner error: {e}")

    # Fallback if broker not running
    if not stock_candidates:
        stock_candidates = ["SPY","QQQ","AAPL","TSLA","NVDA","AMD","META","AMZN","COIN","MSTR"]

    # ── Step 2: Dynamic crypto scan — use Alpaca-discovered pairs + extras ────
    try:
        from strategy.crypto_engine import ALPACA_TRADEABLE as _live_crypto
        CRYPTO_UNIVERSE = sorted(_live_crypto)
    except Exception:
        CRYPTO_UNIVERSE = [
            "BTC","ETH","SOL","DOGE","LINK","AAVE","LTC","BCH",
            "AVAX","XRP","ADA","DOT","ATOM","ALGO","NEAR","SHIB",
        ]

    def _score_crypto_momentum(ticker: str) -> dict:
        try:
            import yfinance as yf
            import numpy as np
            import pandas as pd
            df = yf.download(f"{ticker}-USD", period="1d", interval="5m",
                             progress=False, auto_adjust=True)
            if df is None or df.empty or len(df) < 10:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df = df.droplevel(1, axis=1)
            df.columns = [c.lower() for c in df.columns]
            if "close" not in df.columns:
                return None
            closes  = df["close"].dropna().values.astype(float)
            volumes = df["volume"].dropna().values.astype(float) if "volume" in df.columns else None

            price = float(closes[-1])
            n5    = min(12, len(closes) - 1)
            n20   = min(48, len(closes) - 1)
            mom5  = (closes[-1] - closes[-n5])  / closes[-n5]  * 100 if closes[-n5] > 0 else 0
            mom20 = (closes[-1] - closes[-n20]) / closes[-n20] * 100 if closes[-n20] > 0 else 0
            vol_spike = 1.0
            if volumes is not None and len(volumes) >= 20:
                avg = np.mean(volumes[-20:])
                vol_spike = min(5.0, float(volumes[-1]) / avg) if avg > 0 else 1.0
            atr  = float(np.mean(np.abs(np.diff(closes[-14:])))) if len(closes) >= 15 else price * 0.005
            score = abs(mom5) * 2 + abs(mom20) + vol_spike * 2

            # Signal
            bullish = 0
            if mom5  > 0.3:  bullish += 2
            if mom20 > 0.5:  bullish += 2
            if vol_spike > 1.5: bullish += 1
            if mom5  < -0.3: bullish -= 3
            if mom20 < -0.5: bullish -= 3

            if bullish >= 3:
                signal = "BUY"
                confidence = min(85, 55 + bullish * 5)
            elif bullish <= -3:
                signal = "SELL"
                confidence = min(80, 55 + abs(bullish) * 5)
            else:
                signal = "HOLD"
                confidence = 40

            entry  = round(price, 6)
            target = round(price * (1 + atr / price * 3), 6)
            stop   = round(price * (1 - atr / price * 2), 6)
            rr     = round((target - entry) / (entry - stop), 2) if entry > stop else 1.0

            return {
                "symbol":     f"{ticker}/USD",
                "ticker":     ticker,
                "asset_type": "crypto",
                "signal":     signal,
                "confidence": int(confidence),
                "score":      round(score, 2),
                "momentum":   round(mom5, 2),
                "vol_spike":  round(vol_spike, 2),
                "price":      price,
                "entry":      entry,
                "exit_target": target,
                "stop":       stop,
                "risk_reward": rr,
                "reasoning":  (
                    f"Crypto momentum: {mom5:+.2f}% (5m) {mom20:+.2f}% (session) | "
                    f"Vol spike {vol_spike:.1f}x | Score {score:.1f}"
                ),
            }
        except Exception as e:
            logger.debug(f"Crypto score {ticker}: {e}")
            return None

    # ── Step 2b: Crypto — ONE batch yfinance call for all 25 coins (no price mixing) ──
    loop = asyncio.get_event_loop()

    def _batch_score_all_crypto() -> list:
        import yfinance as yf
        import numpy as np
        import pandas as pd

        yf_syms = [f"{t}-USD" for t in CRYPTO_UNIVERSE]
        results = []
        try:
            df = yf.download(yf_syms, period="1d", interval="5m",
                             progress=False, auto_adjust=True, group_by="ticker")
            if df is None or df.empty:
                return []
        except Exception as e:
            logger.warning(f"Crypto batch download: {e}")
            return []

        for ticker in CRYPTO_UNIVERSE:
            yf_sym = f"{ticker}-USD"
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    lvl0 = df.columns.get_level_values(0)
                    if yf_sym not in lvl0:
                        continue
                    sub = df[yf_sym].copy()
                else:
                    sub = df.copy()

                sub.columns = [c.lower() for c in sub.columns]
                if "close" not in sub.columns:
                    continue
                closes  = sub["close"].dropna().values.astype(float)
                volumes = sub["volume"].dropna().values.astype(float) if "volume" in sub.columns else None

                if len(closes) < 10:
                    continue

                price = float(closes[-1])
                n5    = min(12, len(closes) - 1)
                n20   = min(48, len(closes) - 1)
                mom5  = (closes[-1] - closes[-n5])  / closes[-n5]  * 100 if closes[-n5] > 0 else 0
                mom20 = (closes[-1] - closes[-n20]) / closes[-n20] * 100 if closes[-n20] > 0 else 0

                vol_spike = 1.0
                if volumes is not None and len(volumes) >= 20:
                    avg = float(np.mean(volumes[-20:]))
                    vol_spike = min(5.0, float(volumes[-1]) / avg) if avg > 0 else 1.0

                atr = float(np.mean(np.abs(np.diff(closes[-14:])))) if len(closes) >= 15 else price * 0.005

                # Directional score — positive = bullish, negative = bearish
                score = mom5 * 2 + mom20 * 1.5 + (vol_spike - 1) * 2
                abs_score = abs(mom5) * 2 + abs(mom20) + vol_spike * 2

                # Signal thresholds — realistic for quiet overnight market
                if score >= 0.3 and mom5 >= 0:
                    signal = "BUY"
                    confidence = min(85, 55 + int(score * 8))
                elif score <= -0.3 and mom5 < 0:
                    signal = "SELL"
                    confidence = min(80, 55 + int(abs(score) * 8))
                else:
                    signal = "HOLD"
                    confidence = 40

                entry  = round(price, 6)
                target = round(price * (1 + atr / price * 3), 6) if signal == "BUY" else round(price * (1 - atr / price * 3), 6)
                stop   = round(price * (1 - atr / price * 2), 6) if signal == "BUY" else round(price * (1 + atr / price * 2), 6)
                rr     = round(abs(target - entry) / abs(entry - stop), 2) if abs(entry - stop) > 0 else 1.0

                results.append({
                    "symbol":     f"{ticker}/USD",
                    "ticker":     ticker,
                    "asset_type": "crypto",
                    "signal":     signal,
                    "confidence": int(confidence),
                    "score":      round(abs_score, 2),
                    "momentum":   round(mom5, 3),
                    "vol_spike":  round(vol_spike, 2),
                    "price":      round(price, 6),
                    "entry":      entry,
                    "exit_target": target,
                    "stop":       stop,
                    "risk_reward": rr,
                    "reasoning":  (
                        f"{ticker} | 5m: {mom5:+.2f}% | session: {mom20:+.2f}% | "
                        f"vol {vol_spike:.1f}x | price ${price:.4f}"
                    ),
                })
            except Exception as e:
                logger.debug(f"Crypto score {ticker}: {e}")

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    all_crypto = await loop.run_in_executor(None, _batch_score_all_crypto)
    crypto_picks = [r for r in all_crypto if r.get("signal") in ("BUY","SELL") and r.get("confidence",0) >= min_conf][:5]

    # If nothing clears threshold (very quiet market), show top 3 by score regardless
    if not crypto_picks and all_crypto:
        crypto_picks = sorted(all_crypto, key=lambda x: x["score"], reverse=True)[:3]
        for c in crypto_picks:
            c["confidence"] = max(c["confidence"], min_conf)

    logger.info(f"Crypto scan: {len(crypto_picks)} picks | top={all_crypto[0]['ticker'] if all_crypto else 'none'}")

    # ── Step 3: Stock analysis via yfinance (works 24/7, no broker needed) ───
    def _score_stock_momentum(sym: str) -> dict:
        import yfinance as yf
        import numpy as np
        try:
            df = yf.download(sym, period="5d", interval="5m", progress=False, auto_adjust=True)
            if df is None or df.empty or len(df) < 20:
                return None
            if hasattr(df.columns, "droplevel"):
                try: df = df.droplevel(1, axis=1)
                except Exception: pass
            df.columns = [c.lower() for c in df.columns]
            if "close" not in df.columns:
                return None
            closes  = df["close"].dropna().values.astype(float)
            volumes = df["volume"].dropna().values.astype(float) if "volume" in df.columns else None

            price = float(closes[-1])
            n5    = min(12, len(closes) - 1)
            n20   = min(48, len(closes) - 1)
            mom5  = (closes[-1] - closes[-n5])  / closes[-n5]  * 100 if closes[-n5] > 0 else 0
            mom20 = (closes[-1] - closes[-n20]) / closes[-n20] * 100 if closes[-n20] > 0 else 0

            vol_spike = 1.0
            if volumes is not None and len(volumes) >= 20:
                avg = float(np.mean(volumes[-20:]))
                vol_spike = min(5.0, float(volumes[-1]) / avg) if avg > 0 else 1.0

            def ema(arr, n):
                k = 2/(n+1); e = float(arr[0])
                for v in arr[1:]: e = float(v)*k + e*(1-k)
                return e

            ema8  = ema(closes[-30:], 8) if len(closes) >= 30 else closes[-1]
            ema21 = ema(closes[-30:], 21) if len(closes) >= 30 else closes[-1]
            trend_up = ema8 > ema21

            atr = float(np.mean(np.abs(np.diff(closes[-14:])))) if len(closes) >= 15 else price * 0.01

            # Score
            bullish = 0
            if mom5  > 0.3:   bullish += 2
            if mom20 > 0.5:   bullish += 2
            if trend_up:       bullish += 2
            if vol_spike > 1.5: bullish += 2
            if mom5  < -0.3:  bullish -= 3
            if mom20 < -0.5:  bullish -= 3
            if not trend_up:   bullish -= 1

            if bullish >= 3:
                signal = "BUY"
                confidence = min(88, 58 + bullish * 4)
            elif bullish <= -3:
                signal = "SELL"
                confidence = min(82, 58 + abs(bullish) * 4)
            else:
                signal = "HOLD"
                confidence = 40

            entry  = round(price, 2)
            target = round(price + atr * 3, 2) if signal == "BUY" else round(price - atr * 3, 2)
            stop   = round(price - atr * 2, 2) if signal == "BUY" else round(price + atr * 2, 2)
            rr     = round(abs(target - entry) / abs(entry - stop), 2) if abs(entry - stop) > 0 else 1.0

            reasons = []
            if mom5  > 0: reasons.append(f"{mom5:+.2f}% 5-bar")
            if mom20 > 0: reasons.append(f"{mom20:+.2f}% session")
            if trend_up:  reasons.append("uptrend")
            if vol_spike > 1.5: reasons.append(f"{vol_spike:.1f}x vol")

            return {
                "symbol": sym, "ticker": sym, "asset_type": "stock",
                "signal": signal, "confidence": int(confidence),
                "score":  round(abs(mom5) * 2 + abs(mom20) + vol_spike, 2),
                "entry": entry, "exit_target": target, "stop": stop,
                "risk_reward": rr,
                "reasoning": f"{sym}: {', '.join(reasons) or 'neutral'} | ${price:.2f}",
            }
        except Exception as e:
            logger.debug(f"Stock score {sym}: {e}")
            return None

    stock_tasks   = [loop.run_in_executor(None, _score_stock_momentum, s) for s in stock_candidates[:12]]
    stock_results = await asyncio.gather(*stock_tasks)
    stock_analyses = [r for r in stock_results if r and r.get("signal") in ("BUY","SELL") and r.get("confidence",0) >= min_conf]
    stock_picks = sorted(stock_analyses, key=lambda x: x.get("score",0), reverse=True)[:5]

    # Fallback: top 3 by score if nothing clears threshold
    if not stock_picks:
        all_stocks = [r for r in stock_results if r]
        stock_picks = sorted(all_stocks, key=lambda x: x.get("score",0), reverse=True)[:3]
        for s in stock_picks:
            s["confidence"] = max(s.get("confidence",0), min_conf)

    logger.info(f"Stock scan: {len(stock_picks)} picks from {len(stock_candidates)} candidates")

    # ── Step 4: Save all recommendations (stocks + crypto) ───────────────────
    db.query(AIRecommendation).filter_by(user_id=user.id, trade_date=today()).delete()
    db.commit()

    all_picks = stock_picks + crypto_picks
    # Re-rank by score across both asset types
    all_picks.sort(key=lambda x: x.get("confidence", 0) + x.get("score", 0) * 0.1, reverse=True)

    for rank, pick in enumerate(all_picks[:10], start=1):
        rec = AIRecommendation(
            user_id        = user.id,
            symbol         = pick["symbol"],
            rank           = rank,
            signal         = pick.get("signal","HOLD"),
            confidence     = pick.get("confidence", 50),
            score          = pick.get("score", 50),
            entry          = pick.get("entry") or pick.get("price"),
            exit_target    = pick.get("exit_target") or pick.get("exit"),
            stop           = pick.get("stop"),
            risk_reward    = pick.get("risk_reward"),
            suggested_qty  = 0,
            suggested_alloc= 0,
            reasoning      = pick.get("reasoning",""),
            source         = f"ai_scan_{pick.get('asset_type','stock')}",
            trade_date     = today(),
            status         = "pending",
        )
        db.add(rec)
    db.commit()

    return {
        "status":           "scanned",
        "date":             today(),
        "stocks_scanned":   len(stock_candidates),
        "crypto_scanned":   len(CRYPTO_UNIVERSE),
        "stock_picks":      len(stock_picks),
        "crypto_picks":     len(crypto_picks),
        "total_recommendations": len(all_picks[:10]),
    }


@router.get("/optimizer")
async def get_optimizer_status(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Current portfolio optimizer state — account + goal + trade budget."""
    account = _get_account_info(user, db) or {}
    goal    = _get_daily_goal(user)
    # Coerce every numeric field defensively — Alpaca can return None for
    # buying_power / daytrade_count while paper-restricted or during auth errors.
    def _f(key, default=0.0):
        v = account.get(key, default)
        try: return float(v) if v is not None else float(default)
        except Exception: return float(default)
    def _i(key, default=0):
        v = account.get(key, default)
        try: return int(v) if v is not None else int(default)
        except Exception: return int(default)

    buying_power = _f("buying_power", 0.0)
    dt_remain    = _i("day_trades_remaining", 3)
    pdt_exempt   = bool(account.get("is_pdt_exempt", False))
    return {
        "date":              today(),
        "account":           account,
        "goal":              goal,
        "trade_budget": {
            "max_day_trades":   999 if pdt_exempt else dt_remain,
            "pdt_exempt":       pdt_exempt,
            "buying_power":     buying_power,
            "per_trade_max":    round(buying_power * 0.15, 2),
            "crypto_exempt":    True,
            "daytrade_count":   _i("daytrade_count", 0),
        },
        "min_confidence":    int(_get_setting(db, "alert_confidence_min", 65)),
    }