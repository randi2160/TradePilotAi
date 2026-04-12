"""
Morviq AI — Compliance Routes /api/compliance
Handles consent recording, suitability questionnaire, and compliance status.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.auth            import get_current_user
from database.database    import get_db
from database.models      import User, ConsentRecord
from services.compliance  import AuditService, AuditEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/compliance", tags=["Compliance"])


def get_ip(request: Request) -> str:
    return request.headers.get("X-Real-IP") or request.client.host or "unknown"

def get_ua(request: Request) -> str:
    return request.headers.get("User-Agent", "")[:500]


# ── Consent Recording ─────────────────────────────────────────────────────────

class ConsentBody(BaseModel):
    consent_type:     str   # risk_disclosure | terms_of_service | auto_trading | privacy
    document_version: str   = "2026-04-11"
    accepted:         bool  = True


@router.post("/consent")
async def record_consent(
    body:    ConsentBody,
    request: Request,
    user:    User    = Depends(get_current_user),
    db:      Session = Depends(get_db),
):
    """Record a user's consent to a legal document. Returns signature hash."""
    audit = AuditService(db)

    # Get the document content for hashing
    doc_content = f"Morviq AI {body.consent_type} v{body.document_version}"
    try:
        from database.models import LegalDocument
        doc = db.query(LegalDocument).filter_by(
            doc_type=body.consent_type.replace("_", ""),
            is_active=True
        ).first()
        if doc:
            doc_content = doc.content
    except Exception:
        pass

    sig_hash = audit.record_consent(
        user_id      = user.id,
        email        = user.email,
        consent_type = body.consent_type,
        doc_version  = body.document_version,
        doc_content  = doc_content,
        ip           = get_ip(request),
        user_agent   = get_ua(request),
    )

    # Log specific event type
    event_map = {
        "risk_disclosure": AuditEvent.RISK_DISCLAIMER_ACCEPTED,
        "terms_of_service": AuditEvent.TOS_ACCEPTED,
        "auto_trading":    AuditEvent.AUTO_TRADING_ENABLED,
        "privacy":         AuditEvent.PRIVACY_ACCEPTED,
    }
    event = event_map.get(body.consent_type, AuditEvent.TOS_ACCEPTED)
    audit.log(event, user.id, user.email, get_ip(request), get_ua(request),
              payload={"consent_type": body.consent_type, "version": body.document_version, "sig": sig_hash})

    return {
        "recorded":       True,
        "consent_type":   body.consent_type,
        "version":        body.document_version,
        "signature_hash": sig_hash,
        "timestamp":      datetime.utcnow().isoformat(),
    }


# ── Suitability ───────────────────────────────────────────────────────────────

class SuitabilityBody(BaseModel):
    experience:     str
    income:         str
    net_worth:      str
    risk_tolerance: str
    loss_capacity:  str
    objective:      str


@router.post("/suitability")
async def record_suitability(
    body:    SuitabilityBody,
    request: Request,
    user:    User    = Depends(get_current_user),
    db:      Session = Depends(get_db),
):
    """Record suitability questionnaire responses."""
    # Block if they said they can't afford any losses
    if body.loss_capacity == "none":
        AuditService(db).log(
            AuditEvent.SUITABILITY_COMPLETED, user.id, user.email,
            get_ip(request), get_ua(request),
            payload={"result": "WARNING — cannot afford losses", **body.dict()},
            severity="warning",
        )

    AuditService(db).log(
        AuditEvent.SUITABILITY_COMPLETED, user.id, user.email,
        get_ip(request), get_ua(request),
        payload=body.dict(),
    )

    # Save to user profile if column exists
    try:
        if hasattr(user, "risk_profile"):
            user.risk_profile = body.risk_tolerance
            db.commit()
    except Exception:
        pass

    return {
        "recorded":  True,
        "timestamp": datetime.utcnow().isoformat(),
        "result":    "suitable" if body.loss_capacity != "none" else "caution",
    }


# ── Compliance Status ─────────────────────────────────────────────────────────

@router.get("/status")
async def compliance_status(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Check what consents the user has completed."""
    required = ["risk_disclosure", "terms_of_service", "auto_trading"]
    completed = {}

    for ct in required:
        rec = db.query(ConsentRecord).filter_by(
            user_id=user.id, consent_type=ct, accepted=True
        ).order_by(ConsentRecord.created_at.desc()).first()
        completed[ct] = {
            "done":      rec is not None,
            "version":   rec.document_version if rec else None,
            "timestamp": rec.created_at.isoformat() if rec else None,
            "sig_hash":  rec.signature_hash if rec else None,
        }

    suitability_done = db.query(ConsentRecord).filter_by(
        user_id=user.id, consent_type="suitability"
    ).first() is not None

    all_done = all(v["done"] for v in completed.values())

    return {
        "onboarding_complete": all_done,
        "suitability_done":    suitability_done,
        "consents":            completed,
        "can_live_trade":      all_done,
    }


@router.get("/my-records")
async def my_consent_records(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Get user's own consent history."""
    records = db.query(ConsentRecord).filter_by(user_id=user.id).order_by(
        ConsentRecord.created_at.desc()
    ).all()

    return [
        {
            "consent_type":   r.consent_type,
            "version":        r.document_version,
            "accepted":       r.accepted,
            "signature_hash": r.signature_hash,
            "ip":             r.ip_address[:8] + "***",
            "timestamp":      r.created_at.isoformat(),
        }
        for r in records
    ]


class AutoTradingEnabledBody(BaseModel):
    daily_loss_limit: float = 150.0
    max_trade_size:   float = 500.0
    sig_hash:         str   = ""


@router.post("/auto-trading-enabled")
async def record_auto_trading_enabled(
    body:    AutoTradingEnabledBody,
    request: Request,
    user:    User    = Depends(get_current_user),
    db:      Session = Depends(get_db),
):
    """
    Called the moment a user enables auto-trading.
    Records a distinct audit event with their chosen limits.
    This is separate from the consent record — it marks the MODE being turned ON.
    """
    audit = AuditService(db)
    audit.log(
        event      = AuditEvent.AUTO_TRADING_ENABLED,
        user_id    = user.id,
        user_email = user.email,
        ip         = get_ip(request),
        user_agent = get_ua(request),
        payload    = {
            "daily_loss_limit": body.daily_loss_limit,
            "max_trade_size":   body.max_trade_size,
            "consent_sig":      body.sig_hash,
            "mode":             "AUTO_TRADING_ENABLED",
            "broker":           getattr(user, "broker_type", "unknown"),
            "capital":          getattr(user, "capital", 0),
        },
        severity   = "warning",  # warning so it shows in alerts
    )

    # Also save a consent record specifically for this moment
    import hashlib
    doc_content = f"auto_trading_enabled:{user.id}:{body.daily_loss_limit}:{body.max_trade_size}"
    sig = hashlib.sha256(doc_content.encode()).hexdigest()
    rec = ConsentRecord(
        user_id          = user.id,
        user_email       = user.email,
        consent_type     = "auto_trading_mode_on",
        document_version = datetime.utcnow().strftime("%Y-%m-%d"),
        document_hash    = hashlib.sha256(b"auto_trading_mode").hexdigest(),
        accepted         = True,
        ip_address       = get_ip(request),
        user_agent       = get_ua(request),
        signature_hash   = sig,
    )
    db.add(rec)
    db.commit()

    return {
        "recorded":        True,
        "mode":            "AUTO_TRADING_ENABLED",
        "daily_loss_limit":body.daily_loss_limit,
        "max_trade_size":  body.max_trade_size,
        "signature":       sig,
        "timestamp":       datetime.utcnow().isoformat(),
    }