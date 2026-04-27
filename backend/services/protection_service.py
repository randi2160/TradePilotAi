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
        # One-time migration: tighten legacy defaults for existing users.
        # We only migrate values that match an OLDER default exactly — never
        # overwrite a user's deliberately-chosen tuning. Each block bumps a
        # single field if it's still at its prior default.
        migrated = False
        if float(row.lock_pct or 0) < 0.85 and float(row.lock_pct or 0) == 0.70:
            row.lock_pct = 0.90
            migrated = True
        if float(row.milestone_size or 0) >= 100.0:
            row.milestone_size = 50.0
            migrated = True
        if float(row.time_decay_hours or 0) >= 4.0:
            row.time_decay_hours = 3.0
            migrated = True
        if not row.ladder_enabled:
            row.ladder_enabled = True
            migrated = True
        if not row.scaleout_enabled:
            row.scaleout_enabled = True
            migrated = True
        # Intra-milestone harvest — was 0.30 / $15, now 0.15 / $5 so the
        # trigger arms earlier and gives back less of the peak.
        if float(row.intra_lock_pct or 0) == 0.30:
            row.intra_lock_pct = 0.15
            migrated = True
        if float(row.min_intra_gain or 0) == 15.0:
            row.min_intra_gain = 5.0
            migrated = True
        if migrated:
            db.commit()
            db.refresh(row)
            logger.info(f"⬆️ Protection settings migrated for user {user_id} — tighter defaults applied")
        return row

    # First time — capture current capital as the initial floor
    user = db.query(User).filter(User.id == user_id).one_or_none()
    base = float(user.capital) if user and user.capital else 5000.0

    row = ProtectionSettings(
        user_id         = user_id,
        enabled         = True,
        floor_value     = base,
        initial_capital = base,
        milestone_size  = 50.0,       # ratchet every $50 (more frequent protection)
        lock_pct        = 0.90,       # lock 90% of gains (strict protection)
        harvest_position_pct  = 0.08,
        harvest_portfolio_cap = 500.0,
        breach_action   = "halt_close",
        # Ladder — always on by default
        ladder_enabled       = True,
        scaleout_enabled     = True,
        scaleout_milestones  = [0.03, 0.05, 0.08, 0.12],  # scale out earlier + more often
        scaleout_fraction    = 0.25,
        concentration_pct    = 0.30,
        time_decay_hours     = 3.0,   # tighten sooner (was 4h)
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
        # Intra-milestone trailing harvest
        "intra_lock_pct",
        "min_intra_gain",
        # Recovery-mode risk tuning
        "recovery_size_mult",
        "recovery_stop_mult",
        "recovery_conf_boost",
        "recovery_budget",
        # Entry filters
        "min_stock_conf",
        "min_crypto_conf",
        "min_rr",
        "max_total_positions",
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

    # Intra-milestone + recovery clamps. Defensive because these come from a
    # user-editable form and silly values would make the trigger math weird.
    try:
        row.intra_lock_pct = max(0.0, min(0.95, float(row.intra_lock_pct or 0.30)))
    except Exception:
        row.intra_lock_pct = 0.30
    try:
        row.min_intra_gain = max(1.0, float(row.min_intra_gain or 15.0))
    except Exception:
        row.min_intra_gain = 15.0
    try:
        row.recovery_size_mult = max(0.05, min(1.5, float(row.recovery_size_mult or 0.60)))
    except Exception:
        row.recovery_size_mult = 0.60
    try:
        row.recovery_stop_mult = max(0.25, min(2.0, float(row.recovery_stop_mult or 0.75)))
    except Exception:
        row.recovery_stop_mult = 0.75
    try:
        row.recovery_conf_boost = max(0.0, min(0.50, float(row.recovery_conf_boost or 0.05)))
    except Exception:
        row.recovery_conf_boost = 0.05
    try:
        row.recovery_budget = max(1.0, float(row.recovery_budget or 20.0))
    except Exception:
        row.recovery_budget = 20.0

    # Entry-filter clamps. Confidence values are fractions (0-1).
    try:
        row.min_stock_conf  = max(0.0, min(0.99, float(row.min_stock_conf  or 0.55)))
    except Exception:
        row.min_stock_conf  = 0.55
    try:
        row.min_crypto_conf = max(0.0, min(0.99, float(row.min_crypto_conf or 0.55)))
    except Exception:
        row.min_crypto_conf = 0.55
    try:
        row.min_rr = max(0.5, min(10.0, float(row.min_rr or 1.5)))
    except Exception:
        row.min_rr = 1.5
    try:
        row.max_total_positions = max(1, min(50, int(row.max_total_positions or 6)))
    except Exception:
        row.max_total_positions = 6

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
        # Reset the intra-milestone peak tracker — a ratchet means we've just
        # banked gains and the next giveback calculation should start from
        # the new floor, not the old peak.
        settings.peak_equity_since_ratchet = None
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
# Intra-milestone trailing harvest — protect partial progress
# ═══════════════════════════════════════════════════════════════════════════════

def update_peak_equity(db: Session, user_id: int, live_equity: float) -> float:
    """Track the highest equity seen since the last floor ratchet. Called every
    protection tick. Returns the (possibly updated) peak."""
    if live_equity is None or live_equity <= 0:
        return 0.0
    settings = get_or_create(db, user_id)
    cur_peak = float(settings.peak_equity_since_ratchet or 0.0)
    # Seed peak on first read — use the greater of live equity and current floor
    # so the initial trigger calculation can't ever bank negative "progress".
    if cur_peak <= 0:
        seed = max(float(live_equity), float(settings.floor_value or 0.0))
        settings.peak_equity_since_ratchet = seed
        db.commit()
        return seed
    if float(live_equity) > cur_peak:
        settings.peak_equity_since_ratchet = float(live_equity)
        db.commit()
        return float(live_equity)
    return cur_peak


def compute_dynamic_trigger(settings: ProtectionSettings) -> Optional[float]:
    """Pure function: the equity level at which we harvest to lock intra-gains.

        trigger = peak − (peak − floor) × intra_lock_pct

    Returns None when there's no meaningful peak above floor yet (don't arm)."""
    peak  = float(settings.peak_equity_since_ratchet or 0.0)
    floor = float(settings.floor_value or 0.0)
    gain_above_floor = peak - floor
    min_gain = float(settings.min_intra_gain or 0.0)
    if gain_above_floor <= min_gain:
        return None
    giveback_pct = max(0.0, min(1.0, float(settings.intra_lock_pct or 0.0)))
    return peak - gain_above_floor * giveback_pct


def should_intra_harvest(settings: ProtectionSettings, live_equity: float) -> dict:
    """Check whether live_equity has fallen below the dynamic trigger, meaning
    we should book unrealized gains now before they evaporate back to the
    ratcheted floor. Returns {armed, triggered, trigger, peak, gain_above_floor}."""
    if not settings.enabled:
        return {"armed": False, "triggered": False}
    trigger = compute_dynamic_trigger(settings)
    peak    = float(settings.peak_equity_since_ratchet or 0.0)
    floor   = float(settings.floor_value or 0.0)
    if trigger is None:
        return {
            "armed":     False,
            "triggered": False,
            "peak":      peak,
            "floor":     floor,
            "gain_above_floor": peak - floor,
        }
    triggered = float(live_equity or 0.0) < trigger
    return {
        "armed":     True,
        "triggered": triggered,
        "trigger":   trigger,
        "peak":      peak,
        "floor":     floor,
        "live":      float(live_equity or 0.0),
        "gain_above_floor": peak - floor,
    }


def run_intra_harvest(db: Session, user_id: int, broker) -> dict:
    """Close WINNING positions to realize whatever gains exist right now, before
    they slip away. Losers are deliberately left alone — they have stop-loss
    orders and might still recover; force-closing them here would just convert
    floating losses into realized losses, which defeats the whole point.

    Previously this closed every position indiscriminately (booking losses)
    and skipped crypto entirely (useless for a crypto-heavy portfolio). Now
    it handles both asset classes and filters to unrealized_pnl > 0.

    Returns {closed, skipped_losers, errors}."""
    if broker is None:
        return {"closed": [], "error": "no_broker"}

    closed:           list[str] = []
    skipped_losers:   list[str] = []
    errs:             list[str] = []
    try:
        positions = broker.get_positions() or []
    except Exception as e:
        return {"closed": [], "error": f"get_positions failed: {e}"}

    for p in positions:
        sym = p.get("symbol") or p.get("asset_id")
        if not sym:
            continue
        # Normalize unrealized P&L — some fields are named differently across
        # Alpaca REST vs the normalized client wrapper.
        upnl_raw = (p.get("unrealized_pnl")
                    or p.get("unrealized_pl")
                    or 0)
        try:
            upnl = float(upnl_raw or 0)
        except Exception:
            upnl = 0.0
        if upnl <= 0:
            skipped_losers.append(f"{sym} (${upnl:.2f})")
            continue
        try:
            broker.close_position(sym)
            closed.append(f"{sym} (+${upnl:.2f})")
        except Exception as e:
            errs.append(f"{sym}: {e}")

    settings = get_or_create(db, user_id)
    settings.last_harvest_at = datetime.utcnow()
    db.commit()

    logger.warning(
        f"🌾 INTRA-HARVEST for user {user_id}: "
        f"closed {len(closed)} winner(s) {closed}, "
        f"left {len(skipped_losers)} loser(s) to their stops {skipped_losers}"
        f"{(' errs=' + str(errs)) if errs else ''}"
    )
    return {"closed": closed, "skipped_losers": skipped_losers, "errors": errs}


# ═══════════════════════════════════════════════════════════════════════════════
# Recovery mode — equity below sacred base
# ═══════════════════════════════════════════════════════════════════════════════

def is_in_recovery_mode(settings: ProtectionSettings, live_equity: float) -> bool:
    """Recovery mode is strictly: equity < initial_capital (the sacred base).

    Used in two places:
      1) bot_loop breach handler — skip the hard halt so we can climb back.
      2) engine._enter / risk_manager — tighter sizing, stops, confidence.

    Note we do NOT enter recovery just because equity < floor — that's a
    real breach (floor is above base means locked gains are being given back,
    which deserves the halt). Recovery is only when we're below the sacred
    foundation entirely.
    """
    if not settings.enabled:
        return False
    base = float(settings.initial_capital or 0.0)
    live = float(live_equity or 0.0)
    return live > 0 and live < base


# ═══════════════════════════════════════════════════════════════════════════════
# Breach detection + response
# ═══════════════════════════════════════════════════════════════════════════════

def check_breach(db: Session, user_id: int, live_equity: float) -> dict:
    """Compare live equity to the locked floor. If below, return breach details
    so the caller can decide what to do (halt, close, alert).

    Recovery-mode carve-out: if equity is below the sacred base AND no gains
    are locked above base (floor == initial_capital), we do NOT flag a breach.
    That state is "recovery mode" — bot keeps trading with tighter risk so it
    can climb back above base. Halting would guarantee we never recover.
    """
    settings = get_or_create(db, user_id)
    if not settings.enabled:
        return {"breached": False, "reason": "protection_disabled"}

    floor = float(settings.floor_value or 0.0)
    base  = float(settings.initial_capital or 0.0)
    live  = float(live_equity or 0.0)

    # Recovery carve-out — no locked gains above base, equity below base.
    if live > 0 and live < base and floor <= base + 0.01:
        return {
            "breached":      False,
            "recovery_mode": True,
            "floor_value":   floor,
            "base":          base,
            "live_equity":   live,
            "shortfall":     base - live,
        }

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
