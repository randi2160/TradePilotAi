"""
Dual Engine API routes — start/stop/monitor both strategies.
Prefix: /api/dual
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth              import get_current_user
from database.database      import get_db
from database.models        import User
from strategy.dual_engine   import DualEngineManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dual", tags=["Dual Engine"])

# ── Singleton ─────────────────────────────────────────────────────────────────
_manager: Optional[DualEngineManager] = None

def get_manager() -> DualEngineManager:
    global _manager
    if _manager is None:
        _manager = DualEngineManager()
    return _manager


# ── Schemas ───────────────────────────────────────────────────────────────────

class InitBody(BaseModel):
    market_regime: str   = Field("unknown")
    sentiment:     float = Field(0.0)

class PauseBody(BaseModel):
    engine: str = Field(..., description="scalper | bounce | both")

class ResplitBody(BaseModel):
    market_regime: str   = "unknown"
    sentiment:     float = 0.0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start", summary="Initialize and start both engines with AI split")
async def start_dual(
    body: InitBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    import main as app_module
    bot_loop = getattr(app_module, 'bot_loop', None)

    if not bot_loop or not bot_loop.broker:
        raise HTTPException(400, "Start the main bot first — go to ⚙️ Bot tab and click Start Bot")

    mgr = get_manager()

    split = mgr.initialize(
        total_capital = user.capital,
        daily_goal    = user.daily_target_max,
        market_regime = body.market_regime,
        sentiment     = body.sentiment,
    )
    mgr.start_both()

    return {
        "status": "both engines started",
        "split":  split,
    }


@router.post("/stop", summary="Stop both engines")
async def stop_dual(user: User = Depends(get_current_user)):
    mgr = get_manager()
    mgr.stop_both("manual stop")
    return {"status": "both engines stopped"}


@router.post("/pause", summary="Pause or resume a specific engine")
async def pause_engine(body: PauseBody, user: User = Depends(get_current_user)):
    mgr = get_manager()
    if body.engine == "both":
        mgr.pause_engine("scalper")
        mgr.pause_engine("bounce")
    elif body.engine in ("scalper", "bounce"):
        mgr.pause_engine(body.engine)
    else:
        raise HTTPException(400, "engine must be 'scalper', 'bounce', or 'both'")
    return {"status": f"{body.engine} paused"}


@router.post("/resume", summary="Resume a paused engine")
async def resume_engine(body: PauseBody, user: User = Depends(get_current_user)):
    mgr = get_manager()
    if body.engine == "both":
        mgr.resume_engine("scalper")
        mgr.resume_engine("bounce")
    elif body.engine in ("scalper", "bounce"):
        mgr.resume_engine(body.engine)
    return {"status": f"{body.engine} resumed"}


@router.get("/summary", summary="Get live summary of both engines")
async def get_summary(user: User = Depends(get_current_user)):
    mgr = get_manager()
    return mgr.get_summary()


@router.post("/resplit", summary="Ask AI to recompute capital split")
async def resplit(body: ResplitBody, user: User = Depends(get_current_user)):
    mgr = get_manager()
    if not mgr.allocator:
        raise HTTPException(400, "Engines not initialized — start dual mode first")

    split = mgr.recompute_split(
        market_regime = body.market_regime,
        sentiment_score = body.sentiment,
    )
    return {"status": "split updated", "split": split}


@router.get("/split-history", summary="Get history of AI split decisions")
async def split_history(user: User = Depends(get_current_user)):
    mgr = get_manager()
    if not mgr.allocator:
        return []
    return mgr.allocator.get_history()


@router.get("/pnl-history", summary="Get P&L history for both engines")
async def pnl_history(user: User = Depends(get_current_user)):
    mgr = get_manager()
    return mgr._pnl_history[-100:]
