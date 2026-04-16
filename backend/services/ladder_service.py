"""
Ladder Service — per-position trailing stops + partial scale-out.

What this solves
----------------
The existing harvest rule (services/protection_service.harvest_positions) is
all-or-nothing: when a position hits +8% it closes the whole thing, capping
upside. It also has no memory of peak gain, so when HOOD rides to +13% then
drifts to +11%, nothing catches the give-back.

The Ladder fixes both:

  1. PEAK TRACKING — every tick we stamp the highest unrealized gain each
     open position has ever seen. Persisted on the Trade row so a restart
     doesn't wipe the peak.

  2. TRAIL TIERS — the trail stop is a function of the peak gain. A position
     at peak +11% locks in ~+8% (75% of peak). Under the trail stop → close.
     Above → hold and let it ride.

  3. SCALE-OUT — at +5/+10/+15 milestones we sell 25% of the ORIGINAL qty
     (not current). This banks profit incrementally while keeping a runner
     for real breakouts.

  4. CONCENTRATION & TIME GUARDS — tighten the trail when a single position
     is too big (>30% of equity) or has stopped making new highs for >4h.

Called every ~60 seconds from scheduler/bot_loop via protection_service's
tick machinery. Does NOT interfere with harvest_positions — they run in
sequence and the ladder takes effect first (ladder trail triggers a close
before harvest's 8% threshold usually does).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Trade, ProtectionSettings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Ladder tiers — (peak_gain_threshold, trail_fraction_of_peak)
# ═══════════════════════════════════════════════════════════════════════════════
# Interpretation: if peak gain has reached the first column, trail stop sits
# at (peak_gain × second_column). Evaluated top-down; first match wins.
# Example: peak +11.23% → matches row (0.10, 0.75) → trail at 11.23 × 0.75 = +8.42%
#
# Breakeven rows use 0.0 to mean "trail at entry price" (lock no loss).
# Rows with trail_frac = None mean "no trail yet — use initial stop_loss only".
LADDER_TIERS = [
    # (peak_gain_floor, trail_fraction_of_peak, label)
    (0.15, 0.85, "tier5_runner"),       # peak >=15% → lock 85%
    (0.10, 0.75, "tier4_breakout"),     # peak >=10% → lock 75%
    (0.07, 0.65, "tier3_strong"),       # peak  >=7% → lock 65%
    (0.04, 0.50, "tier2_building"),     # peak  >=4% → lock 50%
    (0.02, 0.00, "tier1_breakeven"),    # peak  >=2% → trail at entry
    (0.00, None, "tier0_inactive"),     # peak   <2% → no trail, initial stop rules
]


def _tier_for_peak(peak_gain_pct: float) -> tuple:
    """Return (floor, frac, label) for a given peak gain. peak_gain_pct is a
    fraction (0.10 = +10%)."""
    for floor, frac, label in LADDER_TIERS:
        if peak_gain_pct >= floor:
            return (floor, frac, label)
    return LADDER_TIERS[-1]


def _bump_tier(current_idx: int) -> int:
    """Shift one tier more aggressive (lower index = tighter trail).
    Used by concentration and time-decay guards."""
    return max(0, current_idx - 1)


def _tier_index(peak_gain_pct: float) -> int:
    for i, (floor, frac, label) in enumerate(LADDER_TIERS):
        if peak_gain_pct >= floor:
            return i
    return len(LADDER_TIERS) - 1


# ═══════════════════════════════════════════════════════════════════════════════
# Math primitives
# ═══════════════════════════════════════════════════════════════════════════════

def compute_trail_stop_pct(
    peak_gain_pct: float,
    *,
    tier_bumps: int = 0,
) -> Optional[float]:
    """
    Given a peak gain % and optional aggressiveness bumps, return the trail
    stop expressed as a gain % (fraction). None means no trail yet — rely on
    initial stop_loss.

    Example: peak +11.23% (0.1123), no bumps → tier4_breakout (0.75) →
             trail at 0.1123 * 0.75 = 0.0842 (+8.42%)
    """
    idx = _tier_index(peak_gain_pct)
    idx = max(0, idx - tier_bumps)
    floor, frac, label = LADDER_TIERS[idx]
    if frac is None:
        return None
    return peak_gain_pct * frac


def current_unrealized_pct(trade: Trade, current_price: float) -> float:
    """Unrealized gain as a fraction. Positive for winning LONG, negative for losing.
    Handles SHORT as inverse."""
    if not trade.entry_price or trade.entry_price <= 0 or current_price <= 0:
        return 0.0
    side = (trade.side or "BUY").upper()
    if side in ("SELL", "SHORT"):
        return (trade.entry_price - current_price) / trade.entry_price
    return (current_price - trade.entry_price) / trade.entry_price


# ═══════════════════════════════════════════════════════════════════════════════
# State updates — mutates the Trade row
# ═══════════════════════════════════════════════════════════════════════════════

def update_peak(trade: Trade, current_price: float, current_qty: float) -> bool:
    """Update peak fields if we have a new high. Returns True if a new peak
    was set. Called every protection tick."""
    # Initialize original_qty the first time we see the trade
    if trade.original_qty is None or trade.original_qty <= 0:
        trade.original_qty = float(current_qty or trade.qty or 0)

    gain_pct = current_unrealized_pct(trade, current_price)
    # $ gain at current qty (scaled-out positions have lower qty)
    gain_pnl = (current_price - trade.entry_price) * current_qty if (trade.side or "BUY").upper() == "BUY" \
               else (trade.entry_price - current_price) * current_qty

    new_peak = False
    if gain_pct > float(trade.peak_unrealized_pct or 0.0):
        trade.peak_unrealized_pct = float(gain_pct)
        trade.peak_price = float(current_price)
        trade.last_peak_at = datetime.utcnow()
        new_peak = True
    if gain_pnl > float(trade.peak_unrealized_pnl or 0.0):
        trade.peak_unrealized_pnl = float(gain_pnl)
        if not new_peak:
            # peak $ advanced without peak % advancing (shouldn't happen often,
            # but can if qty was adjusted). Stamp time anyway.
            trade.last_peak_at = datetime.utcnow()

    return new_peak


# ═══════════════════════════════════════════════════════════════════════════════
# Decision helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _tier_bumps(
    trade: Trade,
    position_value: float,
    total_equity: float,
    settings: ProtectionSettings,
) -> int:
    """Concentration + time-decay guards. Returns how many tiers tighter we
    should be for this position right now."""
    bumps = 0

    # Concentration: single position taking too much of the book → tighten
    if total_equity > 0:
        conc_ratio = position_value / total_equity
        if conc_ratio >= float(settings.concentration_pct or 0.30):
            bumps += 1

    # Time decay: no new peak for N hours → we're probably fading, tighten
    if trade.last_peak_at:
        stale = datetime.utcnow() - trade.last_peak_at
        if stale >= timedelta(hours=float(settings.time_decay_hours or 4.0)):
            bumps += 1

    # Cap at 1 bump total — stacking is too aggressive
    return min(1, bumps)


def decide_action(
    trade: Trade,
    current_price: float,
    current_qty: float,
    total_equity: float,
    settings: ProtectionSettings,
) -> dict:
    """
    Decide what to do with this position right now. Pure function — does NOT
    execute or mutate. Returns an action dict:

        {"action": "hold" | "trail_exit" | "scale_out",
         "symbol": str,
         "qty": float (only for scale_out),
         "reason": str,
         "tier": str,
         "trail_pct": float | None,
         "current_pct": float,
         "peak_pct": float}
    """
    side = (trade.side or "BUY").upper()
    if side in ("SELL", "SHORT"):
        # TODO: short trailing uses inverted tiers. For now just hold and let
        # the existing stop_loss handle shorts.
        return {"action": "hold", "symbol": trade.symbol, "reason": "short_not_supported_yet"}

    current_pct = current_unrealized_pct(trade, current_price)
    peak_pct    = max(float(trade.peak_unrealized_pct or 0.0), current_pct)

    position_value = abs(current_qty * current_price)
    bumps = _tier_bumps(trade, position_value, total_equity, settings)

    idx = _tier_index(peak_pct)
    idx = max(0, idx - bumps)
    floor, frac, label = LADDER_TIERS[idx]

    trail_pct = None if frac is None else peak_pct * frac

    # ── 1. Scale-out milestone check (runs BEFORE trail exit so a milestone
    #       crossover doesn't get masked by a trail breach at the same tick) ──
    if settings.scaleout_enabled and settings.scaleout_milestones:
        levels_hit = list(trade.scaleout_levels_hit or [])
        for milestone in settings.scaleout_milestones:
            m = float(milestone)
            if peak_pct >= m and m not in levels_hit:
                # Don't scale-out on a position we've already scaled past
                fraction = float(settings.scaleout_fraction or 0.25)
                orig_qty = float(trade.original_qty or current_qty)
                scale_qty = round(orig_qty * fraction, 6)
                # Don't try to sell more than we have
                scale_qty = min(scale_qty, current_qty)
                if scale_qty > 0:
                    return {
                        "action":       "scale_out",
                        "symbol":       trade.symbol,
                        "qty":          scale_qty,
                        "milestone":    m,
                        "reason":       f"milestone +{m*100:.0f}% hit — sell {fraction*100:.0f}% of original",
                        "tier":         label,
                        "trail_pct":    trail_pct,
                        "current_pct":  current_pct,
                        "peak_pct":     peak_pct,
                    }

    # ── 2. Trail stop check — current gain has dropped below the trail ────
    if trail_pct is not None and current_pct < trail_pct:
        protected = peak_pct - (peak_pct - trail_pct)  # = trail_pct
        # Only fire if we actually have a meaningful trail (prevents noise
        # at +0.01% peaks where trail is ~0 and just oscillates)
        if peak_pct >= LADDER_TIERS[-2][0]:   # peak >= 2% (tier1 floor)
            return {
                "action":       "trail_exit",
                "symbol":       trade.symbol,
                "qty":          current_qty,
                "reason":       f"peak +{peak_pct*100:.2f}% → trail +{trail_pct*100:.2f}% "
                                f"breached (now +{current_pct*100:.2f}%)",
                "tier":         label,
                "trail_pct":    trail_pct,
                "current_pct":  current_pct,
                "peak_pct":     peak_pct,
                "locked_pnl":   float(trade.peak_unrealized_pnl or 0.0) * frac if frac else 0.0,
            }

    # ── 3. Hold ─────────────────────────────────────────────────────────────
    return {
        "action":       "hold",
        "symbol":       trade.symbol,
        "reason":       f"in tier {label}",
        "tier":         label,
        "trail_pct":    trail_pct,
        "current_pct":  current_pct,
        "peak_pct":     peak_pct,
        "tier_bumps":   bumps,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrator — called from bot loop
# ═══════════════════════════════════════════════════════════════════════════════

def run_ladder_tick(
    db: Session,
    user_id: int,
    broker,
) -> dict:
    """
    Top-level tick. Matches broker positions → open Trade rows, updates peaks,
    decides action per position, executes trail_exit (full close) or
    scale_out (partial close).

    Returns a summary dict suitable for the activity feed and API.
    """
    settings = (
        db.query(ProtectionSettings)
          .filter(ProtectionSettings.user_id == user_id)
          .first()
    )
    if not settings or not settings.enabled or not settings.ladder_enabled:
        return {"status": "disabled", "actions": []}

    try:
        positions = broker.get_positions() or []
    except Exception as e:
        logger.warning(f"ladder tick: get_positions failed: {e}")
        return {"status": "error", "error": str(e), "actions": []}

    # Total equity for concentration math — try account first, fall back to
    # sum of position market values.
    try:
        acct = broker.get_account() or {}
        total_equity = float(acct.get("equity") or 0.0)
    except Exception:
        total_equity = sum(abs(float(p.get("qty", 0)) * float(p.get("current_price") or p.get("avg_entry_price") or 0)) for p in positions)

    # Index open trades by symbol (most recent per symbol wins)
    open_trades = (
        db.query(Trade)
          .filter(Trade.user_id == user_id, Trade.status == "open")
          .order_by(Trade.opened_at.desc())
          .all()
    )
    trades_by_sym: dict[str, Trade] = {}
    for t in open_trades:
        if t.symbol not in trades_by_sym:
            trades_by_sym[t.symbol] = t

    actions: list[dict] = []
    summary_rows: list[dict] = []

    for p in positions:
        sym = (p.get("symbol") or "").upper()
        if not sym:
            continue
        # Broker crypto symbols might be like "BTCUSD" while Trade.symbol is "BTC" —
        # try both lookups
        trade = trades_by_sym.get(sym) or trades_by_sym.get(sym.replace("USD", ""))
        if not trade:
            continue  # manual position or untracked — ladder skips

        try:
            current_price = float(p.get("current_price") or p.get("market_price") or 0)
            current_qty   = abs(float(p.get("qty") or 0))
            if current_price <= 0 or current_qty <= 0:
                continue

            # 1. Update peak (may raise a new high)
            new_peak = update_peak(trade, current_price, current_qty)

            # 2. Decide action
            decision = decide_action(trade, current_price, current_qty, total_equity, settings)

            # 3. Persist any state changes (peak, trail)
            if decision.get("trail_pct") is not None:
                trade.trail_stop_pct = float(decision["trail_pct"])
            db.add(trade)

            summary_rows.append({
                "symbol":      trade.symbol,
                "current_pct": decision.get("current_pct", 0),
                "peak_pct":    decision.get("peak_pct", 0),
                "trail_pct":   decision.get("trail_pct"),
                "tier":        decision.get("tier", ""),
                "action":      decision["action"],
            })

            # 4. Execute if needed
            if decision["action"] == "trail_exit":
                try:
                    res = broker.close_position(trade.symbol)
                    if "error" in res:
                        logger.warning(f"ladder trail_exit failed for {trade.symbol}: {res['error']}")
                    else:
                        actions.append(decision)
                        logger.info(
                            f"🪜 Ladder trail exit: {trade.symbol} | "
                            f"peak +{decision['peak_pct']*100:.2f}% → "
                            f"now +{decision['current_pct']*100:.2f}% (trail +{decision['trail_pct']*100:.2f}%)"
                        )
                except Exception as e:
                    logger.warning(f"ladder trail_exit execute {trade.symbol}: {e}")

            elif decision["action"] == "scale_out":
                try:
                    res = broker.place_market_order(trade.symbol, decision["qty"], "SELL")
                    if "error" in res:
                        logger.warning(f"ladder scale_out failed for {trade.symbol}: {res['error']}")
                    else:
                        # Record the milestone as hit so we don't re-fire it
                        levels = list(trade.scaleout_levels_hit or [])
                        levels.append(float(decision["milestone"]))
                        trade.scaleout_levels_hit = levels
                        # Track total scale-out progress
                        orig = float(trade.original_qty or decision["qty"])
                        trade.scaled_out_pct = min(
                            1.0,
                            float(trade.scaled_out_pct or 0.0) + (decision["qty"] / orig if orig > 0 else 0.0)
                        )
                        db.add(trade)
                        actions.append(decision)
                        logger.info(
                            f"🪜 Ladder scale-out: {trade.symbol} | "
                            f"sold {decision['qty']:.4f} at milestone +{decision['milestone']*100:.0f}% "
                            f"(peak +{decision['peak_pct']*100:.2f}%)"
                        )
                except Exception as e:
                    logger.warning(f"ladder scale_out execute {trade.symbol}: {e}")

        except Exception as e:
            logger.warning(f"ladder tick {sym}: {e}")
            continue

    try:
        db.commit()
    except Exception as e:
        logger.warning(f"ladder tick commit: {e}")
        db.rollback()

    return {
        "status":   "ok",
        "actions":  actions,
        "rows":     summary_rows,
        "checked":  len(summary_rows),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Status summary — for UI
# ═══════════════════════════════════════════════════════════════════════════════

def get_ladder_status(db: Session, user_id: int, broker) -> dict:
    """Snapshot of every open position's ladder state for the dashboard.
    Does NOT execute — pure read."""
    settings = (
        db.query(ProtectionSettings)
          .filter(ProtectionSettings.user_id == user_id)
          .first()
    )
    if not settings:
        return {"enabled": False, "positions": []}

    try:
        positions = broker.get_positions() or []
    except Exception as e:
        return {"enabled": bool(settings.ladder_enabled), "positions": [], "error": str(e)}

    try:
        acct = broker.get_account() or {}
        total_equity = float(acct.get("equity") or 0.0)
    except Exception:
        total_equity = 0.0

    open_trades = (
        db.query(Trade)
          .filter(Trade.user_id == user_id, Trade.status == "open")
          .order_by(Trade.opened_at.desc())
          .all()
    )
    trades_by_sym: dict[str, Trade] = {}
    for t in open_trades:
        if t.symbol not in trades_by_sym:
            trades_by_sym[t.symbol] = t

    rows = []
    total_protected = 0.0
    total_unrealized = 0.0

    for p in positions:
        sym = (p.get("symbol") or "").upper()
        trade = trades_by_sym.get(sym) or trades_by_sym.get(sym.replace("USD", ""))
        if not trade:
            continue
        try:
            current_price = float(p.get("current_price") or p.get("market_price") or 0)
            current_qty   = abs(float(p.get("qty") or 0))
            current_pct   = current_unrealized_pct(trade, current_price)
            peak_pct      = max(float(trade.peak_unrealized_pct or 0.0), current_pct)

            position_value = abs(current_qty * current_price)
            bumps = _tier_bumps(trade, position_value, total_equity, settings)
            idx = max(0, _tier_index(peak_pct) - bumps)
            floor, frac, label = LADDER_TIERS[idx]
            trail_pct = None if frac is None else peak_pct * frac

            # Protected $ = (trail_pct * entry_price * qty) if trail active, else 0
            protected_dollars = 0.0
            if trail_pct is not None:
                protected_dollars = trail_pct * float(trade.entry_price or 0) * current_qty

            upnl = float(p.get("unrealized_pnl") or p.get("unrealized_pl") or 0)
            total_unrealized += upnl
            total_protected  += max(0.0, protected_dollars)

            rows.append({
                "symbol":         trade.symbol,
                "qty":            current_qty,
                "entry":          float(trade.entry_price or 0),
                "current":        current_price,
                "current_pct":    current_pct,
                "peak_pct":       peak_pct,
                "trail_pct":      trail_pct,
                "tier":           label,
                "tier_bumps":     bumps,
                "levels_hit":     list(trade.scaleout_levels_hit or []),
                "scaled_out_pct": float(trade.scaled_out_pct or 0.0),
                "protected_usd":  round(protected_dollars, 2),
                "unrealized_usd": round(upnl, 2),
                "last_peak_at":   trade.last_peak_at.isoformat() if trade.last_peak_at else None,
            })
        except Exception as e:
            logger.debug(f"ladder status {sym}: {e}")
            continue

    return {
        "enabled":           bool(settings.ladder_enabled),
        "scaleout_enabled":  bool(settings.scaleout_enabled),
        "scaleout_levels":   list(settings.scaleout_milestones or []),
        "scaleout_fraction": float(settings.scaleout_fraction or 0.25),
        "positions":         rows,
        "total_unrealized":  round(total_unrealized, 2),
        "total_protected":   round(total_protected, 2),
        "protection_ratio":  round(total_protected / total_unrealized, 3) if total_unrealized > 0 else 0.0,
    }
