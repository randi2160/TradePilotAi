"""
Profit protection — account-level gain preservation.

Philosophy
----------
Your $5,000 initial capital is sacred. As the bot books realized gains, we
permanently lock in a percentage of each gain milestone so they can never be
lost, even if future trades go wrong. Floating (unrealized) gains that grow
large enough get "harvested" — force-closed into realized so they count toward
compound and push the floor up.

This complements the existing intraday trailing-floor in
strategy/daily_target.py (which protects within-session gains). Together:

    intraday floor   → protects TODAY's floating profit
    harvest rule     → converts big floaters into permanent realized
    account floor    → protects ALL-TIME realized, ratchets up forever
"""
from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import ProtectionSettings, User, DailyPnL

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Settings access — auto-create on first read
# ═══════════════════════════════════════════════════════════════════════════════

def get_or_create(db: Session, user_id: int) -> ProtectionSettings:
    """Return the user's protection settings, materializing them with sensible
    defaults if they don't yet exist. Initial floor = user's configured capital.
    """
    row = (
        db.query(ProtectionSettings)
          .filter(ProtectionSettings.user_id == user_id)
          .one_or_none()
    )
    if row:
        return row

    # First time — capture current capital as the initial floor
    user = db.query(User).filter(User.id == user_id).one_or_none()
    base = float(user.capital) if user and user.capital else 5000.0

    row = ProtectionSettings(
        user_id         = user_id,
        enabled         = True,
        floor_value     = base,
        initial_capital = base,
        milestone_size  = 100.0,
        lock_pct        = 0.70,
        harvest_position_pct  = 0.08,
        harvest_portfolio_cap = 500.0,
        breach_action   = "halt_close",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(f"ProtectionSettings initialized for user {user_id} (base floor ${base:.2f})")
    return row


def update_settings(db: Session, user_id: int, updates: dict) -> ProtectionSettings:
    """Update a subset of fields. Immutable fields (floor_value, peak_compound,
    last_*_at, initial_capital) are rejected unless explicitly allowed."""
    row = get_or_create(db, user_id)

    allowed = {
        "enabled",
        "milestone_size",
        "lock_pct",
        "harvest_position_pct",
        "harvest_portfolio_cap",
        "breach_action",
        # Ladder (per-position trail + scale-out)
        "ladder_enabled",
        "scaleout_enabled",
        "scaleout_milestones",
        "scaleout_fraction",
        "concentration_pct",
        "time_decay_hours",
    }
    for k, v in (updates or {}).items():
        if k in allowed and v is not None:
            setattr(row, k, v)

    # Sanity clamps
    row.milestone_size        = max(10.0,   float(row.milestone_size))
    row.lock_pct              = max(0.0, min(1.0, float(row.lock_pct)))
    row.harvest_position_pct  = max(0.0, min(2.0, float(row.harvest_position_pct)))  # allow up to 200%
    row.harvest_portfolio_cap = max(0.0,   float(row.harvest_portfolio_cap))
    if row.breach_action not in {"halt_close", "halt_only", "alert_only"}:
        row.breach_action = "halt_close"

    # Ladder clamps
    try:
        row.scaleout_fraction = max(0.0, min(1.0, float(row.scaleout_fraction or 0.25)))
    except Exception:
        row.scaleout_fraction = 0.25
    try:
        row.concentration_pct = max(0.0, min(1.0, float(row.concentration_pct or 0.30)))
    except Exception:
        row.concentration_pct = 0.30
    try:
        row.time_decay_hours  = max(0.0, float(row.time_decay_hours or 4.0))
    except Exception:
        row.time_decay_hours  = 4.0
    # Milestones: list of floats in (0, 1], sorted ascending, deduped
    try:
        raw_ms = list(row.scaleout_milestones or [0.05, 0.10, 0.15])
        clean  = sorted({round(float(x), 4) for x in raw_ms if 0 < float(x) <= 1.0})
        row.scaleout_milestones = clean or [0.05, 0.10, 0.15]
    except Exception:
        row.scaleout_milestones = [0.05, 0.10, 0.15]

    db.commit()
    db.refresh(row)
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# Floor math + ratchet
# ═══════════════════════════════════════════════════════════════════════════════

def compute_target_floor(settings: ProtectionSettings, compound_total: float) -> float:
    """Pure function: given compound realized, return what the floor *should*
    be — the highest multiple of `milestone_size` that doesn't exceed
    initial_capital + lock_pct * compound_total.
    Never returns less than initial_capital.
    """
    if compound_total <= 0:
        return float(settings.initial_capital or 0.0)

    raw = float(settings.initial_capital or 0.0) + float(settings.lock_pct or 0.0) * compound_total
    milestone = max(10.0, float(settings.milestone_size or 100.0))

    # Round floor *down* to milestone boundary — we lock conservatively
    stepped = math.floor((raw - settings.initial_capital) / milestone) * milestone + settings.initial_capital
    return max(stepped, float(settings.initial_capital or 0.0))


def ratchet_floor(db: Session, user_id: int, compound_total: float) -> dict:
    """Call after each snapshot — if compound_total has reached a new milestone,
    raise the floor. Floor is monotonic (never decreases).
    Returns {floor_value, raised_by, milestone_hit}."""
    settings = get_or_create(db, user_id)
    if not settings.enabled:
        return {"floor_value": float(settings.floor_value), "raised_by": 0.0, "milestone_hit": False}

    target = compute_target_floor(settings, compound_total)
    current = float(settings.floor_value or 0.0)

    if target > current:
        raised_by = target - current
        settings.floor_value     = target
        settings.last_ratchet_at = datetime.utcnow()
        if compound_total > (settings.peak_compound or 0.0):
            settings.peak_compound = compound_total
        db.commit()
        db.refresh(settings)
        logger.info(
            f"🔒 Floor ratcheted for user {user_id}: "
            f"${current:.2f} → ${target:.2f} (+${raised_by:.2f}) "
            f"at compound ${compound_total:.2f}"
        )
        return {"floor_value": target, "raised_by": raised_by, "milestone_hit": True}

    # Still update peak tracking even when floor unchanged
    if compound_total > (settings.peak_compound or 0.0):
        settings.peak_compound = compound_total
        db.commit()

    return {"floor_value": current, "raised_by": 0.0, "milestone_hit": False}


# ═══════════════════════════════════════════════════════════════════════════════
# Breach detection + response
# ═══════════════════════════════════════════════════════════════════════════════

def check_breach(db: Session, user_id: int, live_equity: float) -> dict:
    """Compare live equity to the locked floor. If below, return breach details
    so the caller can decide what to do (halt, close, alert)."""
    settings = get_or_create(db, user_id)
    if not settings.enabled:
        return {"breached": False, "reason": "protection_disabled"}

    floor = float(settings.floor_value or 0.0)
    live  = float(live_equity or 0.0)

    if live < floor:
        # Only record a *new* breach if we haven't recently — prevents spam
        now = datetime.utcnow()
        recent = settings.last_breach_at and (now - settings.last_breach_at).total_seconds() < 60
        if not recent:
            settings.last_breach_at = now
            db.commit()
        return {
            "breached":     True,
            "floor_value":  floor,
            "live_equity":  live,
            "shortfall":    floor - live,
            "action":       settings.breach_action,
        }

    return {"breached": False, "floor_value": floor, "live_equity": live}


def execute_breach_response(db: Session, user_id: int, broker, bot_loop=None) -> dict:
    """Called when check_breach returned breached=True. Executes the configured
    action. `broker` is an AlpacaClient; `bot_loop` is the app's bot_loop module.

    Returns a summary dict describing what was done.
    """
    settings = get_or_create(db, user_id)
    action = settings.breach_action
    result = {"action": action, "halted": False, "closed_positions": [], "alerted": True}

    try:
        if action in ("halt_close", "halt_only") and bot_loop is not None:
            if hasattr(bot_loop, "stop"):
                bot_loop.stop()
                result["halted"] = True
                logger.warning(f"🛑 Bot halted for user {user_id} — floor breach")

        if action == "halt_close" and broker is not None:
            try:
                positions = broker.get_positions() or []
                for p in positions:
                    sym = p.get("symbol") or p.get("asset_id")
                    if sym:
                        try:
                            broker.close_position(sym)
                            result["closed_positions"].append(sym)
                        except Exception as e:
                            logger.warning(f"breach close failed for {sym}: {e}")
            except Exception as e:
                logger.error(f"breach position-fetch failed: {e}")
    except Exception as e:
        logger.error(f"execute_breach_response error: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Harvest rule — convert big unrealized winners into realized
# ═══════════════════════════════════════════════════════════════════════════════

def should_harvest(settings: ProtectionSettings, positions: list) -> list[dict]:
    """Inspect open positions against the harvest thresholds. Returns a list of
    positions that should be force-closed, ordered by urgency (biggest unrealized
    first). Does NOT execute — returns intent for the caller to act on.
    """
    if not settings.enabled:
        return []

    harvest_list: list[dict] = []
    total_unrealized = 0.0

    # Normalize positions
    normalized = []
    for p in positions or []:
        try:
            symbol = p.get("symbol") or p.get("asset_id") or ""
            qty    = float(p.get("qty") or p.get("quantity") or 0)
            entry  = float(p.get("avg_entry_price") or p.get("entry") or 0)
            upnl   = float(p.get("unrealized_pnl") or p.get("unrealized_pl") or 0)
            pct    = float(p.get("unrealized_pct") or p.get("unrealized_plpc") or 0)
            # Some clients report pct as a fraction (0.08), others as 8.0 — normalize
            if abs(pct) > 2.0:
                pct = pct / 100.0
            if pct == 0 and entry > 0 and qty != 0:
                pct = upnl / (entry * abs(qty))
            normalized.append({
                "symbol": symbol, "qty": qty, "entry": entry,
                "unrealized_pnl": upnl, "unrealized_pct": pct,
                "raw": p,
            })
            total_unrealized += upnl
        except Exception:
            continue

    # Sort by unrealized P&L descending — we harvest the biggest winners
    normalized.sort(key=lambda x: x["unrealized_pnl"], reverse=True)

    pos_threshold = float(settings.harvest_position_pct or 0)
    cap_threshold = float(settings.harvest_portfolio_cap or 0)

    # Rule 1: per-position — any single winner above the pct threshold
    for item in normalized:
        if item["unrealized_pct"] >= pos_threshold and item["unrealized_pnl"] > 0:
            harvest_list.append({
                "symbol": item["symbol"],
                "reason": f"position +{item['unrealized_pct']*100:.1f}% ≥ {pos_threshold*100:.1f}% threshold",
                "unrealized_pnl": item["unrealized_pnl"],
            })

    # Rule 2: portfolio-level — total unrealized exceeds cap → close biggest winner
    if total_unrealized > cap_threshold > 0:
        top = normalized[0] if normalized else None
        if top and top["unrealized_pnl"] > 0:
            already = any(h["symbol"] == top["symbol"] for h in harvest_list)
            if not already:
                harvest_list.append({
                    "symbol": top["symbol"],
                    "reason": f"portfolio unrealized ${total_unrealized:.2f} > ${cap_threshold:.2f} cap",
                    "unrealized_pnl": top["unrealized_pnl"],
                })

    return harvest_list


def harvest_positions(db: Session, user_id: int, broker) -> dict:
    """Execute the harvest rule. Closes winners that meet threshold — book the
    gain into realized. Called periodically from the bot loop. Returns summary."""
    settings = get_or_create(db, user_id)
    if not settings.enabled or broker is None:
        return {"harvested": [], "reason": "disabled_or_no_broker"}

    try:
        positions = broker.get_positions() or []
    except Exception as e:
        logger.warning(f"harvest: get_positions failed: {e}")
        return {"harvested": [], "error": str(e)}

    intents = should_harvest(settings, positions)
    if not intents:
        return {"harvested": [], "reason": "no_winners_over_threshold"}

    harvested = []
    for intent in intents:
        sym = intent["symbol"]
        try:
            broker.close_position(sym)
            harvested.append(intent)
            logger.info(f"💰 Harvested {sym} for user {user_id} — {intent['reason']}")
        except Exception as e:
            logger.warning(f"harvest close failed for {sym}: {e}")

    if harvested:
        settings.last_harvest_at = datetime.utcnow()
        db.commit()

    return {"harvested": harvested}


# ═══════════════════════════════════════════════════════════════════════════════
# Status summary — for UI
# ═══════════════════════════════════════════════════════════════════════════════

def get_status(db: Session, user_id: int, live_equity: Optional[float] = None) -> dict:
    """One-shot status packet for the dashboard badge and banner."""
    settings = get_or_create(db, user_id)

    # Pull latest compound from today's DailyPnL if available
    today_row = (
        db.query(DailyPnL)
          .filter(DailyPnL.user_id == user_id)
          .order_by(DailyPnL.trade_date.desc())
          .first()
    )
    compound = float(today_row.compound_total) if today_row else 0.0
    unrealized = float(today_row.unrealized_pnl) if today_row else 0.0

    # What the floor *should* be given current compound — shows user how far
    # they are from the next milestone
    target = compute_target_floor(settings, compound)
    next_milestone = target + float(settings.milestone_size or 100.0)
    gain_to_next = (next_milestone - settings.initial_capital) / float(settings.lock_pct or 1.0) - compound
    gain_to_next = max(0.0, gain_to_next)

    breached = False
    if live_equity is not None and settings.enabled:
        breached = live_equity < float(settings.floor_value or 0.0)

    return {
        "enabled":               bool(settings.enabled),
        "floor_value":           float(settings.floor_value or 0.0),
        "initial_capital":       float(settings.initial_capital or 0.0),
        "milestone_size":        float(settings.milestone_size or 100.0),
        "lock_pct":              float(settings.lock_pct or 0.0),
        "harvest_position_pct":  float(settings.harvest_position_pct or 0.0),
        "harvest_portfolio_cap": float(settings.harvest_portfolio_cap or 0.0),
        "breach_action":         settings.breach_action,
        "peak_compound":         float(settings.peak_compound or 0.0),
        "current_compound":      compound,
        "current_unrealized":    unrealized,
        "gain_to_next_milestone": gain_to_next,
        "live_equity":           live_equity,
        "breached":              breached,
        "last_ratchet_at":       settings.last_ratchet_at.isoformat() if settings.last_ratchet_at else None,
        "last_breach_at":        settings.last_breach_at.isoformat() if settings.last_breach_at else None,
        "last_harvest_at":       settings.last_harvest_at.isoformat() if settings.last_harvest_at else None,
    }
