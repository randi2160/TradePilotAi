"""
Copy Trading Routes — /api/copy
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from auth.auth         import get_current_user
from database.database import get_db
from database.models   import User, TraderProfile, Trade
from services.copy_engine import CopyTradingEngine

router = APIRouter(prefix="/api/copy", tags=["Copy Trading"])


class StartCopyBody(BaseModel):
    leader_id:        int
    mode:             str   = Field("pct_of_capital", description="pct_of_capital|pct_of_leader|fixed_dollar")
    copy_pct:         float = Field(10.0,  description="% of capital or fixed $ depending on mode")
    max_per_trade:    float = Field(500.0, description="Max $ per single copied trade")
    max_open:         int   = Field(3,     description="Max simultaneous copied positions")
    use_leader_stop:  bool  = True
    pause_after_loss: float = Field(100.0, description="Pause copying if daily loss exceeds this $")


@router.get("/my-configs", summary="Get my active copy configs")
async def get_my_configs(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    engine = CopyTradingEngine(db)
    return engine.get_copy_configs(user.id)


@router.post("/start", summary="Start copying a leader")
async def start_copy(
    body: StartCopyBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    if body.leader_id == user.id:
        raise HTTPException(400, "Cannot copy yourself")

    engine = CopyTradingEngine(db)
    result = engine.start_copy(
        follower_id      = user.id,
        leader_id        = body.leader_id,
        mode             = body.mode,
        copy_pct         = body.copy_pct,
        max_per_trade    = body.max_per_trade,
        max_open         = body.max_open,
        use_leader_stop  = body.use_leader_stop,
        pause_after_loss = body.pause_after_loss,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.delete("/stop/{leader_id}", summary="Stop copying a leader")
async def stop_copy(
    leader_id: int,
    user:      User    = Depends(get_current_user),
    db:        Session = Depends(get_db),
):
    engine = CopyTradingEngine(db)
    return engine.stop_copy(user.id, leader_id)


@router.get("/leaders", summary="Get copyable traders with stats")
async def get_copyable_leaders(
    db:   Session = Depends(get_db),
    user: User    = Depends(get_current_user),
):
    """Returns traders available for copy trading."""
    # Get all public profiles (relaxed for testing — production will filter is_copyable=True)
    profiles = db.query(TraderProfile).filter(
        TraderProfile.is_public == True,
        TraderProfile.user_id   != user.id,  # exclude self
    ).order_by(TraderProfile.win_rate.desc()).limit(20).all()

    # If no profiles, create one for yourself so you can test copying
    if not profiles:
        # Return empty with helpful message
        return []

    result = []
    for p in profiles:
        leader = db.query(User).filter_by(id=p.user_id).first()
        if not leader:
            continue
        recent = db.query(Trade).filter(
            Trade.user_id == p.user_id,
            Trade.status  == "closed",
        ).order_by(Trade.opened_at.desc()).limit(20).all()
        recent_pnl = sum(t.pnl or 0 for t in recent)
        result.append({
            "user_id":       p.user_id,
            "display_name":  p.display_name or leader.email.split("@")[0],
            "bio":           p.bio,
            "win_rate":      p.win_rate,
            "total_trades":  p.total_trades,
            "total_pnl":     p.total_pnl,
            "avg_profit":    p.avg_profit,
            "max_drawdown":  p.max_drawdown,
            "days_tracked":  p.days_tracked,
            "followers":     p.followers_count,
            "recent_pnl_20": round(recent_pnl, 2),
            "is_copyable":   p.is_copyable or True,  # allow all for testing
            "min_copy_tier": p.min_copy_tier,
        })
    return result


@router.get("/performance/{leader_id}", summary="Get detailed copy performance for a leader")
async def leader_performance(
    leader_id: int,
    db:        Session = Depends(get_db),
    user:      User    = Depends(get_current_user),
):
    profile = db.query(TraderProfile).filter_by(user_id=leader_id).first()
    if not profile:
        raise HTTPException(404, "Leader not found")

    trades = db.query(Trade).filter(
        Trade.user_id == leader_id,
        Trade.status  == "closed",
    ).order_by(Trade.opened_at.desc()).limit(50).all()

    wins   = [t for t in trades if (t.pnl or 0) > 0]
    losses = [t for t in trades if (t.pnl or 0) <= 0]

    return {
        "profile": {
            "display_name": profile.display_name,
            "win_rate":     profile.win_rate,
            "total_trades": profile.total_trades,
            "total_pnl":    profile.total_pnl,
            "avg_profit":   profile.avg_profit,
            "days_tracked": profile.days_tracked,
        },
        "recent_trades": [
            {
                "symbol":     t.symbol,
                "side":       t.side,
                "pnl":        round(t.pnl or 0, 2),
                "pnl_pct":    round(t.pnl_pct or 0, 2),
                "confidence": t.confidence,
                "trade_date": t.trade_date,
            }
            for t in trades[:20]
        ],
        "summary": {
            "total_wins":      len(wins),
            "total_losses":    len(losses),
            "avg_win":         round(sum(t.pnl or 0 for t in wins)   / len(wins)   if wins   else 0, 2),
            "avg_loss":        round(sum(t.pnl or 0 for t in losses) / len(losses) if losses else 0, 2),
            "best_trade":      round(max((t.pnl or 0 for t in trades), default=0), 2),
            "worst_trade":     round(min((t.pnl or 0 for t in trades), default=0), 2),
        }
    }
