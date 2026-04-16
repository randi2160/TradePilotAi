"""
Dual Engine API routes — start/stop/monitor both strategies.
Prefix: /api/dual

Per-user isolation
------------------
Each user gets their OWN DualEngineManager keyed by user_id, stored in
`_managers`. Start/stop/summary/etc. only touch the caller's manager, so
user A starting dual mode never flips user B's dashboard to "running".

The "main bot running" prerequisite is also scoped to the caller —
we consult the per-user bot registry in main.py (via `get_user_bot_if_exists`),
not the pre-refactor `app_module.bot_loop` singleton (which no longer exists).
"""
import logging
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth              import get_current_user
from database.database      import get_db
from database.models        import User
from strategy.dual_engine   import DualEngineManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dual", tags=["Dual Engine"])

# ── Per-user registry ─────────────────────────────────────────────────────────
_managers: Dict[int, DualEngineManager] = {}

def get_manager(user_id: int) -> DualEngineManager:
    """Fetch-or-create THIS user's dual engine manager."""
    if user_id not in _managers:
        _managers[user_id] = DualEngineManager()
    return _managers[user_id]

def get_manager_if_exists(user_id: int) -> Optional[DualEngineManager]:
    """Return this user's manager only if they've already initialized one."""
    return _managers.get(user_id)

def _user_bot_running(user_id: int) -> bool:
    """True iff THIS user's main stock bot is started with a broker attached.

    Uses the per-user bot registry from main.py. Falls back to False if the
    lookup fails (e.g. main.py not importable yet at startup).
    """
    try:
        import main as app_module
        fn = getattr(app_module, "get_user_bot_if_exists", None)
        if fn is None:
            return False
        bot = fn(user_id)
        return bool(bot and bot.broker and bot.status == "running")
    except Exception as e:
        logger.warning(f"_user_bot_running lookup failed: {e}")
        return False


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
    import time as _t
    t0 = _t.time()
    logger.info(f"╔══ DUAL ENGINE START [uid={user.id}] ═══════════════════════════")

    # Per-user prerequisite: THIS user's main stock bot must be running.
    if not _user_bot_running(user.id):
        logger.warning(f"║  Main bot not running for user {user.id} — aborting dual start")
        raise HTTPException(
            400,
            "Start the main bot first — go to ⚙️ Bot tab and click Start Bot",
        )
    logger.info(f"║  [1] Main bot check passed ({_t.time()-t0:.2f}s)")

    mgr = get_manager(user.id)

    t2 = _t.time()
    split = mgr.initialize(
        total_capital = user.capital,
        daily_goal    = user.daily_target_max,
        market_regime = body.market_regime,
        sentiment     = body.sentiment,
    )
    logger.info(
        f"║  [2] AI split computed ({_t.time()-t2:.2f}s) | "
        f"capital=${user.capital} goal=${user.daily_target_max} "
        f"scalper={split.get('scalper',{}).get('pct',0)}% "
        f"bounce={split.get('bounce',{}).get('pct',0)}%"
    )

    mgr.start_both()
    logger.info(f"╚══ DUAL ENGINE READY in {_t.time()-t0:.2f}s ═════════════════════════")

    return {
        "status": "both engines started",
        "split":  split,
    }


@router.post("/stop", summary="Stop both engines")
async def stop_dual(user: User = Depends(get_current_user)):
    mgr = get_manager_if_exists(user.id)
    if mgr is None:
        return {"status": "already stopped"}
    mgr.stop_both("manual stop")
    return {"status": "both engines stopped"}


@router.post("/pause", summary="Pause or resume a specific engine")
async def pause_engine(body: PauseBody, user: User = Depends(get_current_user)):
    mgr = get_manager_if_exists(user.id)
    if mgr is None:
        raise HTTPException(400, "Dual engine not started for this user")
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
    mgr = get_manager_if_exists(user.id)
    if mgr is None:
        raise HTTPException(400, "Dual engine not started for this user")
    if body.engine == "both":
        mgr.resume_engine("scalper")
        mgr.resume_engine("bounce")
    elif body.engine in ("scalper", "bounce"):
        mgr.resume_engine(body.engine)
    return {"status": f"{body.engine} resumed"}


@router.get("/summary", summary="Get live summary of both engines")
async def get_summary(user: User = Depends(get_current_user)):
    """Summary for THIS user's dual engine only.

    Users who have never started dual mode get an empty-but-well-shaped
    summary so the UI doesn't crash and — critically — doesn't pick up
    another user's state.
    """
    mgr = get_manager_if_exists(user.id)
    if mgr is None:
        return {
            "initialized": False,
            "running":     False,
            "scalper":     None,
            "bounce":      None,
            "split":       None,
        }
    return mgr.get_summary()


@router.post("/resplit", summary="Ask AI to recompute capital split")
async def resplit(body: ResplitBody, user: User = Depends(get_current_user)):
    mgr = get_manager_if_exists(user.id)
    if mgr is None or not mgr.allocator:
        raise HTTPException(400, "Engines not initialized — start dual mode first")

    split = mgr.recompute_split(
        market_regime = body.market_regime,
        sentiment_score = body.sentiment,
    )
    return {"status": "split updated", "split": split}


@router.get("/split-history", summary="Get history of AI split decisions")
async def split_history(user: User = Depends(get_current_user)):
    mgr = get_manager_if_exists(user.id)
    if mgr is None or not mgr.allocator:
        return []
    return mgr.allocator.get_history()


@router.get("/pnl-history", summary="Get P&L history for both engines")
async def pnl_history(user: User = Depends(get_current_user)):
    mgr = get_manager_if_exists(user.id)
    if mgr is None:
        return []
    return mgr._pnl_history[-100:]
