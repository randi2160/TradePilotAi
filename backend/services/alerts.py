"""
Morviq AI — Trading Alert System
Generates entry/exit alerts from AI analysis for watched symbols.
Stores alerts in DB, serves to frontend with unread count badge.

Alert types:
- BUY_SIGNAL:   AI recommends entry
- SELL_SIGNAL:  AI recommends exit / short
- STOP_HIT:     Price approaching stop loss
- TARGET_HIT:   Price approaching profit target
- EARNINGS:     Earnings announcement upcoming
- VOLUME:       Unusual volume detected
"""
import json
import logging
from datetime   import datetime, timezone
from typing     import Optional, List

from fastapi    import APIRouter, Depends, HTTPException
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float
from sqlalchemy.orm import Session

from auth.auth         import get_current_user
from database.database import get_db
from database.models   import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


# ── DB Model (add to models.py) ───────────────────────────────────────────────
# class TradingAlert(Base):
#     __tablename__ = "trading_alerts"
#     ...
# (Added via migrate_db.py)


class AlertService:
    """Create, retrieve, and manage trading alerts."""

    def __init__(self, db: Session, user_id: int):
        self.db      = db
        self.user_id = user_id

    def create(
        self,
        symbol:      str,
        alert_type:  str,   # BUY_SIGNAL | SELL_SIGNAL | STOP_HIT | TARGET_HIT | VOLUME
        signal:      str,   # BUY | SELL | HOLD
        confidence:  int,
        price:       float,
        entry:       Optional[float] = None,
        exit_target: Optional[float] = None,
        stop:        Optional[float] = None,
        risk_reward: Optional[float] = None,
        reasoning:   str = "",
        indicators:  dict = None,
    ) -> Optional[dict]:
        """
        Create an alert. Deduplicates — won't create same alert for same symbol
        within the last interval window.
        """
        try:
            from database.models import TradingAlert

            # Check for duplicate within last 5 minutes
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(minutes=5)
            existing = self.db.query(TradingAlert).filter(
                TradingAlert.user_id   == self.user_id,
                TradingAlert.symbol    == symbol.upper(),
                TradingAlert.alert_type== alert_type,
                TradingAlert.created_at>= cutoff,
            ).first()

            if existing:
                return None  # Already alerted recently

            alert = TradingAlert(
                user_id     = self.user_id,
                symbol      = symbol.upper(),
                alert_type  = alert_type,
                signal      = signal,
                confidence  = confidence,
                price       = price,
                entry_price = entry,
                exit_price  = exit_target,
                stop_price  = stop,
                risk_reward = risk_reward,
                reasoning   = reasoning[:500],
                indicators  = json.dumps(indicators or {}),
                is_read     = False,
                created_at  = datetime.utcnow(),
            )
            self.db.add(alert)
            self.db.commit()
            self.db.refresh(alert)
            return self._to_dict(alert)

        except Exception as e:
            logger.error(f"AlertService.create error: {e}")
            try: self.db.rollback()
            except: pass
            return None

    def get_unread_count(self) -> int:
        try:
            from database.models import TradingAlert
            return self.db.query(TradingAlert).filter_by(
                user_id=self.user_id, is_read=False
            ).count()
        except Exception:
            return 0

    def get_alerts(self, limit: int = 50, unread_only: bool = False) -> List[dict]:
        try:
            from database.models import TradingAlert
            q = self.db.query(TradingAlert).filter_by(user_id=self.user_id)
            if unread_only:
                q = q.filter_by(is_read=False)
            alerts = q.order_by(TradingAlert.created_at.desc()).limit(limit).all()
            return [self._to_dict(a) for a in alerts]
        except Exception as e:
            logger.error(f"get_alerts error: {e}")
            return []

    def mark_read(self, alert_id: Optional[int] = None) -> int:
        """Mark one or all alerts as read. Returns count updated."""
        try:
            from database.models import TradingAlert
            q = self.db.query(TradingAlert).filter_by(user_id=self.user_id)
            if alert_id:
                q = q.filter_by(id=alert_id)
            else:
                q = q.filter_by(is_read=False)
            count = q.update({"is_read": True})
            self.db.commit()
            return count
        except Exception as e:
            logger.error(f"mark_read error: {e}")
            return 0

    def get_today_for_symbol(self, symbol: str) -> List[dict]:
        """Get all alerts for a specific symbol today."""
        try:
            from database.models import TradingAlert
            today = str(datetime.utcnow().date())
            alerts = self.db.query(TradingAlert).filter(
                TradingAlert.user_id == self.user_id,
                TradingAlert.symbol  == symbol.upper(),
            ).order_by(TradingAlert.created_at.desc()).all()
            return [self._to_dict(a) for a in alerts]
        except Exception:
            return []

    def _to_dict(self, a) -> dict:
        try:
            indicators = json.loads(a.indicators or "{}")
        except Exception:
            indicators = {}
        return {
            "id":          a.id,
            "symbol":      a.symbol,
            "alert_type":  a.alert_type,
            "signal":      a.signal,
            "confidence":  a.confidence,
            "price":       a.price,
            "entry":       a.entry_price,
            "exit":        a.exit_price,
            "stop":        a.stop_price,
            "risk_reward": a.risk_reward,
            "reasoning":   a.reasoning,
            "indicators":  indicators,
            "is_read":     a.is_read,
            "timestamp":   a.created_at.isoformat(),
        }


def maybe_create_alert(
    db:         Session,
    user_id:    int,
    symbol:     str,
    analysis:   dict,
    min_confidence: int = 65,
) -> Optional[dict]:
    """
    Called after every AI analysis. Creates an alert if signal is strong enough.
    """
    signal     = analysis.get("signal", "HOLD")
    confidence = analysis.get("confidence", 0)

    if signal == "HOLD" or confidence < min_confidence:
        return None

    alert_type = "BUY_SIGNAL" if signal == "BUY" else "SELL_SIGNAL"
    svc        = AlertService(db, user_id)

    return svc.create(
        symbol      = symbol,
        alert_type  = alert_type,
        signal      = signal,
        confidence  = confidence,
        price       = analysis.get("entry") or analysis.get("price") or 0,
        entry       = analysis.get("entry"),
        exit_target = analysis.get("exit"),
        stop        = analysis.get("stop"),
        risk_reward = float(analysis.get("risk_reward") or 0) or None,
        reasoning   = analysis.get("reasoning", ""),
        indicators  = analysis.get("indicators", {}),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/count")
async def alert_count(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Fast endpoint — just returns unread count for badge."""
    svc = AlertService(db, user.id)
    return {"unread": svc.get_unread_count()}


@router.get("")
async def get_alerts(
    limit:       int  = 50,
    unread_only: bool = False,
    user:        User    = Depends(get_current_user),
    db:          Session = Depends(get_db),
):
    svc = AlertService(db, user.id)
    return {
        "alerts": svc.get_alerts(limit=limit, unread_only=unread_only),
        "unread": svc.get_unread_count(),
    }


@router.get("/symbol/{symbol}")
async def symbol_alerts(
    symbol: str,
    user:   User    = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    """All alerts for a specific symbol today."""
    svc = AlertService(db, user.id)
    return {
        "symbol":  symbol.upper(),
        "alerts":  svc.get_today_for_symbol(symbol),
        "unread":  svc.get_unread_count(),
    }


@router.post("/read")
async def mark_all_read(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    svc   = AlertService(db, user.id)
    count = svc.mark_read()
    return {"marked_read": count}


@router.post("/read/{alert_id}")
async def mark_one_read(
    alert_id: int,
    user:     User    = Depends(get_current_user),
    db:       Session = Depends(get_db),
):
    svc = AlertService(db, user.id)
    svc.mark_read(alert_id)
    return {"ok": True}
