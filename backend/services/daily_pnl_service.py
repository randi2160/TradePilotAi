"""
Daily P&L snapshotting + compound tracking.

Design notes:
  - Realized P&L comes from the `trades` table (sum of net_pnl for trades with
    trade_date == today, status='closed'). This is authoritative for what the
    bot actually booked.
  - Unrealized P&L + equity come from the live Alpaca account via the broker
    client. This catches movement on still-open positions and matches what the
    user sees on Alpaca directly.
  - We upsert a `DailyPnL` row keyed on (user_id, trade_date). The first
    snapshot of the day records `starting_equity` from Alpaca; subsequent
    snapshots update `ending_equity` etc.
  - `compound_total` = sum of realized_pnl across all prior finalized days +
    today's realized. This is what the "Since start" label shows.

This module is import-safe: it does not require an active bot loop or broker
connection. If Alpaca is unreachable, the snapshot degrades to DB-only numbers.
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import DailyPnL, Trade, User

logger = logging.getLogger(__name__)


def _today_str() -> str:
    # Use local date; trades table uses the same format (YYYY-MM-DD).
    return date.today().strftime("%Y-%m-%d")


def _realized_today(db: Session, user_id: int, day: str) -> tuple[float, int, int, int]:
    """Return (realized_pnl, trade_count, win_count, loss_count) for a given day."""
    rows = (
        db.query(Trade)
          .filter(Trade.user_id == user_id,
                  Trade.trade_date == day,
                  Trade.status == "closed")
          .all()
    )
    realized    = 0.0
    trade_count = len(rows)
    win_count   = 0
    loss_count  = 0
    for t in rows:
        pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0.0))
        realized += pnl
        if pnl > 0:
            win_count += 1
        elif pnl < 0:
            loss_count += 1
    return realized, trade_count, win_count, loss_count


def _compound_before(db: Session, user_id: int, day: str) -> float:
    """Sum of realized_pnl from every DailyPnL row strictly before `day`."""
    total = (
        db.query(func.coalesce(func.sum(DailyPnL.realized_pnl), 0.0))
          .filter(DailyPnL.user_id == user_id,
                  DailyPnL.trade_date < day)
          .scalar()
    )
    return float(total or 0.0)


def ratchet_tick(db: Session, user_id: int) -> dict:
    """Fast-path floor ratchet — DB only, no broker HTTP.

    The full `snapshot_today()` calls Alpaca twice (account + positions) which
    blocks the asyncio event loop for ~500-700ms per call. When this runs on
    a 15-second bot tick the cumulative freeze makes API requests feel sluggish.

    For floor ratcheting we only need `compound_total` — the running sum of
    realized gains — which is entirely derivable from the DB:
        compound_total = _compound_before(today) + _realized_today(today)

    Returns the ratchet_floor result. Safe to call on every tick.
    """
    from services import protection_service  # local import to avoid cycle
    day       = _today_str()
    realized, _, _, _ = _realized_today(db, user_id, day)
    prior     = _compound_before(db, user_id, day)
    compound  = prior + float(realized or 0.0)
    return protection_service.ratchet_floor(db, user_id, compound)


def snapshot_today(db: Session, user_id: int, broker=None) -> DailyPnL:
    """
    Upsert today's DailyPnL row for `user_id`. Safe to call repeatedly —
    each call refreshes the live numbers. Returns the persisted row.

    `broker`: optional AlpacaClient instance. If None, we still record realized
    numbers from the DB but leave equity/unrealized at their last known value.
    """
    day = _today_str()

    row = (
        db.query(DailyPnL)
          .filter(DailyPnL.user_id == user_id,
                  DailyPnL.trade_date == day)
          .one_or_none()
    )

    first_snapshot = row is None
    if first_snapshot:
        row = DailyPnL(user_id=user_id, trade_date=day)
        db.add(row)

    # Realized from DB (authoritative for booked trades)
    realized, tc, wc, lc = _realized_today(db, user_id, day)
    row.realized_pnl = realized
    row.trade_count  = tc
    row.win_count    = wc
    row.loss_count   = lc

    # Equity + unrealized from Alpaca (when available)
    if broker is not None:
        try:
            acct = broker.get_account() or {}
            equity = float(acct.get("equity", 0) or 0)
            if equity > 0:
                if first_snapshot or (row.starting_equity or 0) == 0:
                    row.starting_equity = equity
                row.ending_equity       = equity
                row.alpaca_cash         = float(acct.get("cash", 0) or 0)
                row.alpaca_buying_power = float(acct.get("buying_power", 0) or 0)
        except Exception as e:
            logger.warning(f"snapshot_today: broker.get_account failed: {e}")

        try:
            positions = broker.get_positions() or []
            row.unrealized_pnl = sum(float(p.get("unrealized_pnl", 0) or 0)
                                     for p in positions)
        except Exception as e:
            logger.warning(f"snapshot_today: broker.get_positions failed: {e}")
            row.unrealized_pnl = row.unrealized_pnl or 0.0

    row.total_pnl = (row.realized_pnl or 0.0) + (row.unrealized_pnl or 0.0)

    # Compound running total (all prior days' realized + today's realized)
    prior = _compound_before(db, user_id, day)
    row.compound_total = prior + (row.realized_pnl or 0.0)

    # Compound % vs. starting capital. Primary: User.capital column. Fallback:
    # legacy user_settings.json (older installs stored capital there, not on the
    # User row). Without this fallback, compound_pct renders as 0% on the UI.
    try:
        user = db.query(User).filter(User.id == user_id).one_or_none()
        base = float(user.capital) if user and user.capital else 0.0
        if base <= 0:
            try:
                import json, os
                settings_path = os.path.join(os.path.dirname(__file__), "..", "user_settings.json")
                if os.path.exists(settings_path):
                    with open(settings_path, "r") as f:
                        base = float(json.load(f).get("capital", 0) or 0)
            except Exception:
                pass
        if base <= 0:
            base = 5000.0  # last-resort default to avoid div-by-zero
        row.compound_pct = (row.compound_total / base * 100.0)
    except Exception:
        row.compound_pct = 0.0

    db.commit()
    db.refresh(row)

    # --- Protection: ratchet the account-level floor on every snapshot ------
    # Monotonic — floor only ever goes UP. This locks in `lock_pct` of every
    # $milestone_size of compound realized as permanent, unlosable capital.
    try:
        from services import protection_service
        protection_service.ratchet_floor(db, user_id, float(row.compound_total or 0.0))
    except Exception as e:
        logger.warning(f"snapshot_today: ratchet_floor failed: {e}")

    return row


def finalize_day(db: Session, user_id: int, broker=None, day: Optional[str] = None) -> DailyPnL:
    """Mark a day's row as finalized. Called when the bot stops for the day or
    at market close. Runs a final snapshot first."""
    day = day or _today_str()
    row = snapshot_today(db, user_id, broker=broker) if day == _today_str() else (
        db.query(DailyPnL)
          .filter(DailyPnL.user_id == user_id, DailyPnL.trade_date == day)
          .one_or_none()
    )
    if row is not None and not row.is_finalized:
        row.is_finalized = True
        row.finalized_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return row


def get_today(db: Session, user_id: int, broker=None, refresh: bool = True) -> dict:
    """Return today's snapshot as a dict, refreshing from broker if asked."""
    if refresh:
        row = snapshot_today(db, user_id, broker=broker)
    else:
        day = _today_str()
        row = (
            db.query(DailyPnL)
              .filter(DailyPnL.user_id == user_id, DailyPnL.trade_date == day)
              .one_or_none()
        )
        if row is None:
            # No snapshot yet — materialize one.
            row = snapshot_today(db, user_id, broker=broker)
    return _row_to_dict(row)


def get_history(db: Session, user_id: int, days: int = 30) -> list[dict]:
    """Return recent daily rows, oldest first, for charting."""
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = (
        db.query(DailyPnL)
          .filter(DailyPnL.user_id == user_id,
                  DailyPnL.trade_date >= cutoff)
          .order_by(DailyPnL.trade_date.asc())
          .all()
    )
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: DailyPnL) -> dict:
    if row is None:
        return {}
    win_rate = 0.0
    if (row.trade_count or 0) > 0:
        win_rate = round((row.win_count / row.trade_count) * 100, 2)
    return {
        "trade_date":          row.trade_date,
        "starting_equity":     float(row.starting_equity or 0),
        "ending_equity":       float(row.ending_equity or 0),
        "alpaca_cash":         float(row.alpaca_cash or 0),
        "alpaca_buying_power": float(row.alpaca_buying_power or 0),
        "realized_pnl":        float(row.realized_pnl or 0),
        "unrealized_pnl":      float(row.unrealized_pnl or 0),
        "total_pnl":           float(row.total_pnl or 0),
        "compound_total":      float(row.compound_total or 0),
        "compound_pct":        float(row.compound_pct or 0),
        "trade_count":         int(row.trade_count or 0),
        "win_count":           int(row.win_count or 0),
        "loss_count":          int(row.loss_count or 0),
        "win_rate":            win_rate,
        "is_finalized":        bool(row.is_finalized),
        "finalized_at":        row.finalized_at.isoformat() if row.finalized_at else None,
        "updated_at":          row.updated_at.isoformat() if row.updated_at else None,
    }
