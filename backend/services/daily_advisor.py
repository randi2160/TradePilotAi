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
    """Get live account info from Alpaca or fall back to user settings."""
    try:
        from broker.broker_routes import _get_broker_creds
        from broker.alpaca_client import AlpacaClient
        import config
        creds = _get_broker_creds(user, db)
        if creds:
            client = AlpacaClient(creds["api_key"], creds["api_secret"],
                                  getattr(user, "alpaca_mode", "paper"))
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
    """Run AI sentiment analysis for a symbol, using cache."""
    try:
        from services.ai_cache import AIAnalysisCache, get_refresh_interval
        is_admin = getattr(user, "is_admin", False)
        tier     = "admin" if is_admin else (getattr(user, "subscription_tier", "free") or "free")
        cache    = AIAnalysisCache(db)
        cached   = cache.get_cached(symbol, "sentiment", tier, is_admin=is_admin)
        if cached:
            cached["symbol"] = symbol
            return cached
    except Exception:
        pass

    # No cache — do a lightweight fallback (full analysis called from /api/ai/symbol-sentiment)
    return {
        "symbol":     symbol,
        "signal":     "HOLD",
        "confidence": 50,
        "score":      50,
        "reasoning":  f"Run AI analysis on ${symbol} to get full entry/exit guidance.",
        "entry":      None, "exit": None, "stop": None, "risk_reward": None,
        "_needs_analysis": True,
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
    Full daily scan: scan market → analyze top movers → optimize portfolio
    → store as ranked AI recommendations.
    Admin can force a fresh scan anytime.
    """
    from database.models import AIRecommendation

    # Get account state
    account = _get_account_info(user, db)
    goal    = _get_daily_goal(user)
    min_conf= int(_get_setting(db, "alert_confidence_min", 65))

    # Get top movers from scanner
    candidates = []
    try:
        from scheduler.bot_loop import bot_loop
        if bot_loop.broker:
            from data.market_scanner import MarketScanner
            scanner = MarketScanner(bot_loop.broker)
            gainers = scanner.get_top_gainers(limit=10)
            actives = scanner.get_most_active(limit=10)
            seen    = set()
            for sym in gainers + actives:
                s = sym if isinstance(sym, str) else sym.get("symbol", "")
                if s and s not in seen:
                    candidates.append(s)
                    seen.add(s)
    except Exception as e:
        logger.warning(f"Scanner error: {e}")

    # Include user's daily picks in analysis
    from database.models import DailyUserPick
    user_picks = [p.symbol for p in db.query(DailyUserPick).filter_by(user_id=user.id, trade_date=today()).all()]
    for sym in user_picks:
        if sym not in candidates:
            candidates.append(sym)

    # Fallback watchlist
    if not candidates:
        try:
            from data.settings_manager import SettingsManager
            sm  = SettingsManager()
            candidates = sm.get_watchlist()[:10]
        except Exception:
            candidates = ["SPY","QQQ","AAPL","TSLA","NVDA","AMD","META","AMZN"]

    # Analyze each candidate
    analyses = []
    for sym in candidates[:15]:
        try:
            result = await _analyze_symbol(sym, db, user)
            result["symbol"] = sym
            if result.get("confidence", 0) >= min_conf and result.get("signal") in ("BUY","SELL"):
                analyses.append(result)
        except Exception as e:
            logger.warning(f"Analysis failed for {sym}: {e}")

    # Optimize portfolio
    optimized = optimize_portfolio(candidates[:15], analyses, account, goal, user)

    # Save recommendations
    db.query(AIRecommendation).filter_by(user_id=user.id, trade_date=today()).delete()
    db.commit()

    for alloc in optimized["allocations"][:5]:
        rec = AIRecommendation(
            user_id=user.id, symbol=alloc["symbol"], rank=alloc["rank"],
            signal=alloc["signal"], confidence=alloc["confidence"],
            score=alloc["score"], entry=alloc["entry"],
            exit_target=alloc["exit_target"], stop=alloc["stop"],
            risk_reward=alloc["risk_reward"], suggested_qty=alloc["suggested_qty"],
            suggested_alloc=alloc["suggested_alloc"], reasoning=alloc["reasoning"],
            source="ai_scan", trade_date=today(), status="pending",
        )
        db.add(rec)
    db.commit()

    return {
        "status":          "scanned",
        "date":            today(),
        "candidates_scanned": len(candidates),
        "recommendations": len(optimized["allocations"]),
        "optimizer":       optimized,
        "account":         account,
        "goal":            goal,
    }


@router.get("/optimizer")
async def get_optimizer_status(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Current portfolio optimizer state — account + goal + trade budget."""
    account = _get_account_info(user, db)
    goal    = _get_daily_goal(user)
    dt_remain = account.get("day_trades_remaining", 3)
    pdt_exempt = account.get("is_pdt_exempt", False)
    return {
        "date":              today(),
        "account":           account,
        "goal":              goal,
        "trade_budget": {
            "max_day_trades":   999 if pdt_exempt else dt_remain,
            "pdt_exempt":       pdt_exempt,
            "buying_power":     account.get("buying_power", 0),
            "per_trade_max":    round(account.get("buying_power", 0) * 0.15, 2),
            "crypto_exempt":    True,
            "daytrade_count":   account.get("daytrade_count", 0),
        },
        "min_confidence":    int(_get_setting(db, "alert_confidence_min", 65)),
    }