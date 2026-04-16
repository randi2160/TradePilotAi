"""
Broker Management Routes — users connect their own broker accounts.
We store their API keys, they keep full control.
We are a SOFTWARE PLATFORM, not a broker or financial advisor.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth             import get_current_user
from database.database     import get_db
from database.models       import User
from broker.broker_factory import get_supported_brokers, get_broker
import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/broker", tags=["Broker Management"])


class ConnectBrokerBody(BaseModel):
    broker_type:  str
    credentials:  dict

class LiveModeBody(BaseModel):
    enable:       bool
    confirm_risk: bool = False
    confirm_real: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_creds(user: User) -> dict:
    """Load THIS user's saved broker creds — no cross-user fallback.

    The old code had a tier-3 .env fallback that caused every user without
    their own keys to see the admin's paper account. That was a data leak:
    new signups saw real positions, equity, and P&L from whoever owns the
    .env keys on the server. Now each user's dashboard is empty until they
    connect a broker through the My Broker tab.

    For system-level code paths that legitimately need shared market data
    (the market scanner, the recovery broker on boot), use `config.ALPACA_*`
    directly — those aren't user-scoped.
    """
    # 1. Saved JSON creds (primary path — set by POST /api/broker/connect)
    try:
        creds = json.loads(user.broker_creds or "{}")
        if creds and creds.get("api_key"):
            return creds
    except Exception:
        pass

    # 2. Legacy alpaca_key fields (users who connected before broker_creds existed)
    if user.alpaca_key and user.alpaca_secret:
        return {"api_key": user.alpaca_key, "api_secret": user.alpaca_secret}

    return {}


def _get_broker_creds(user: User) -> dict:
    """Public wrapper for _load_creds - used by other modules."""
    return _load_creds(user)


def _resolve_broker_type(user: User) -> str:
    """Determine broker type safely — handles NULL from old DB rows."""
    # If user explicitly connected a broker, use that
    if user.broker_connected and user.broker_type:
        return user.broker_type
    # Otherwise derive from .env ALPACA_MODE
    return "alpaca_live" if config.ALPACA_MODE == "live" else "alpaca_paper"


def _get_user_broker(user: User):
    creds = _load_creds(user)
    if not creds:
        raise HTTPException(400, "Connect your broker first — go to the My Broker tab and add your Alpaca API keys.")
    broker_type = _resolve_broker_type(user)
    try:
        return get_broker(broker_type, creds)
    except Exception as e:
        raise HTTPException(400, f"Broker connection failed: {str(e)[:300]}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/supported")
async def list_brokers():
    return get_supported_brokers()


@router.get("/status")
async def broker_status(user: User = Depends(get_current_user)):
    # Report honestly: connected only if THIS user saved credentials.
    # Previously we reported `connected=True` whenever the server had .env keys,
    # which masked the fact that the user was seeing the admin's portfolio.
    creds       = _load_creds(user)
    has_creds   = bool(creds)
    broker_type = _resolve_broker_type(user)
    return {
        "broker_type":     broker_type,
        "connected":       bool(user.broker_connected) and has_creds,
        "verified":        bool(user.broker_verified)  and has_creds,
        "live_mode":       bool(user.live_mode_enabled),
        "broker_name":     get_supported_brokers().get(broker_type, {}).get("name", broker_type),
        "has_credentials": has_creds,
        "using_env_keys":  False,   # deprecated: per-user isolation now enforced
        "env_mode":        None,
    }


@router.post("/connect")
async def connect_broker(
    body: ConnectBrokerBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    supported = get_supported_brokers()
    if body.broker_type not in supported:
        raise HTTPException(400, f"Unsupported broker: {body.broker_type}")

    # Verify credentials work
    try:
        broker = get_broker(body.broker_type, body.credentials)
        acct   = broker.get_account()
        if not acct:
            raise ValueError("Empty account response")
    except Exception as e:
        raise HTTPException(400, f"Connection failed — check your API keys: {str(e)[:200]}")

    # Save to DB
    user.broker_type      = body.broker_type
    user.broker_creds     = json.dumps(body.credentials)
    user.broker_connected = True
    user.broker_verified  = True
    user.alpaca_mode      = "live" if "live" in body.broker_type else "paper"
    if "alpaca" in body.broker_type:
        user.alpaca_key    = body.credentials.get("api_key", "")
        user.alpaca_secret = body.credentials.get("api_secret", "")
    db.commit()
    return {
        "status":      "connected",
        "broker_type": body.broker_type,
        "broker_name": supported[body.broker_type]["name"],
        "account":     acct,
        "message":     f"✅ Connected to {supported[body.broker_type]['name']}",
    }


@router.delete("/disconnect")
async def disconnect_broker(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.broker_type       = "alpaca_paper"
    user.broker_creds      = "{}"
    user.broker_connected  = False
    user.broker_verified   = False
    user.live_mode_enabled = False
    user.alpaca_key        = ""
    user.alpaca_secret     = ""
    db.commit()
    return {"status": "disconnected"}


@router.get("/account")
async def get_account(user: User = Depends(get_current_user)):
    """Get live account data — uses .env keys automatically if no manual connection."""
    broker = _get_user_broker(user)
    try:
        acct      = broker.get_account()
        positions = broker.get_positions()
        orders    = broker.get_orders(20)
        return {
            "account":   acct,
            "positions": positions,
            "orders":    orders,
            "broker":    _resolve_broker_type(user),
        }
    except Exception as e:
        raise HTTPException(500, f"Could not fetch account data: {str(e)[:200]}")


@router.get("/test")
async def test_connection(user: User = Depends(get_current_user)):
    try:
        broker = _get_user_broker(user)
        acct   = broker.get_account()
        return {
            "status":  "ok",
            "broker":  _resolve_broker_type(user),
            "equity":  acct.get("equity", 0),
            "cash":    acct.get("cash",   0),
            "message": "✅ Broker connection working",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@router.post("/live-mode")
async def toggle_live_mode(
    body: LiveModeBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    if body.enable:
        if not body.confirm_risk or not body.confirm_real:
            raise HTTPException(400, "You must check both confirmation boxes")
        if _resolve_broker_type(user) == "alpaca_paper":
            raise HTTPException(400, "Switch to a live broker account first")
        user.live_mode_enabled = True
        user.live_mode_at      = datetime.utcnow()
        db.commit()
        return {"live_mode": True, "message": "⚠️ LIVE TRADING ENABLED — real money at risk"}
    else:
        user.live_mode_enabled = False
        db.commit()
        return {"live_mode": False, "message": "Live trading disabled — paper mode active"}


@router.get("/funding")
async def funding_info(user: User = Depends(get_current_user)):
    broker_type = _resolve_broker_type(user)
    if "alpaca" in broker_type:
        return {
            "broker": "Alpaca",
            "deposit_url":  "https://app.alpaca.markets/dashboard/overview/transfers",
            "withdraw_url": "https://app.alpaca.markets/dashboard/overview/transfers",
            "dashboard_url":"https://app.alpaca.markets/dashboard/overview",
            "note": "All deposits and withdrawals are handled directly by Alpaca. AutoTrader Pro never touches your money.",
        }
    supported = get_supported_brokers()
    return {
        "broker":      broker_type,
        "signup_url":  supported.get(broker_type, {}).get("signup_url", ""),
        "note": "Please manage funding directly through your broker's platform.",
    }