"""
Morviq AI — Admin Panel Routes /api/admin
Requires is_admin=True on the User model.
All admin actions are logged to audit trail.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth         import get_current_user
from database.database import get_db
from database.models   import User, Trade, AuditLog, ConsentRecord, LegalDocument, CompanySettings
from services.compliance import AuditService, AuditEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ── Admin Auth Guard ──────────────────────────────────────────────────────────

def require_admin(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Admin access required")
    return user


def get_ip(request: Request) -> str:
    return request.headers.get("X-Real-IP") or request.client.host or "unknown"


# ── Dashboard Stats ───────────────────────────────────────────────────────────

@router.get("/dashboard")
async def admin_dashboard(
    admin: User   = Depends(require_admin),
    db:    Session = Depends(get_db),
):
    """Admin overview stats."""
    total_users   = db.query(User).count()
    active_users  = db.query(User).filter(User.is_active == True).count()
    total_trades  = db.query(Trade).count()
    today         = str(datetime.utcnow().date())
    trades_today  = db.query(Trade).filter(Trade.trade_date == today).count()
    try:
        live_users = db.query(User).filter(User.live_mode_enabled == True).count()
    except Exception:
        live_users = 0

    recent_logs = db.query(AuditLog).filter(
        AuditLog.severity.in_(["warning", "critical"])
    ).order_by(AuditLog.created_at.desc()).limit(10).all()

    return {
        "users":        {"total": total_users, "active": active_users, "live": live_users},
        "trades":       {"total": total_trades, "today": trades_today},
        "recent_alerts":[
            {
                "event":     l.event_type,
                "user_id":   l.user_id,
                "ip":        l.ip_address,
                "severity":  l.severity,
                "timestamp": l.created_at.isoformat(),
            }
            for l in recent_logs
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── User Management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    skip:   int  = 0,
    limit:  int  = 50,
    search: str  = "",
    admin:  User = Depends(require_admin),
    db:     Session = Depends(get_db),
):
    q = db.query(User)
    if search:
        q = q.filter(User.email.ilike(f"%{search}%"))
    users = q.offset(skip).limit(limit).all()
    total = q.count()

    return {
        "total": total,
        "users": [
            {
                "id":           u.id,
                "email":        u.email,
                "full_name":    getattr(u, "full_name", ""),
                "is_active":    u.is_active,
                "is_admin":     getattr(u, "is_admin", False),
                "capital":      u.capital,
                "subscription": getattr(u, "subscription_tier", "free"),
                "live_mode":    getattr(u, "live_mode_enabled", False),
                "created_at":   u.created_at.isoformat() if u.created_at else "",
                "last_login":   u.last_login.isoformat() if getattr(u, "last_login", None) else None,
            }
            for u in users
        ],
    }


class UserActionBody(BaseModel):
    action: str  # suspend | unsuspend | make_admin | remove_admin | reset_password


@router.post("/users/{user_id}/action")
async def user_action(
    user_id: int,
    body:    UserActionBody,
    request: Request,
    admin:   User    = Depends(require_admin),
    db:      Session = Depends(get_db),
):
    target = db.query(User).filter_by(id=user_id).first()
    if not target:
        raise HTTPException(404, "User not found")

    audit = AuditService(db)

    if body.action == "suspend":
        target.is_active = False
        db.commit()
        audit.log(AuditEvent.ADMIN_USER_SUSPENDED, admin.id, admin.email,
                  get_ip(request), payload={"target_user_id": user_id, "action": "suspend"}, severity="warning")
        return {"status": "suspended", "user_id": user_id}

    elif body.action == "unsuspend":
        target.is_active = True
        db.commit()
        audit.log(AuditEvent.ADMIN_USER_SUSPENDED, admin.id, admin.email,
                  get_ip(request), payload={"target_user_id": user_id, "action": "unsuspend"})
        return {"status": "unsuspended", "user_id": user_id}

    elif body.action == "make_admin":
        if hasattr(target, "is_admin"):
            target.is_admin = True
            db.commit()
        audit.log(AuditEvent.ADMIN_CONTENT_UPDATED, admin.id, admin.email,
                  get_ip(request), payload={"target_user_id": user_id, "action": "make_admin"}, severity="warning")
        return {"status": "made_admin", "user_id": user_id}

    raise HTTPException(400, f"Unknown action: {body.action}")


@router.get("/users/{user_id}/audit")
async def user_audit_trail(
    user_id: int,
    limit:   int  = 100,
    admin:   User = Depends(require_admin),
    db:      Session = Depends(get_db),
):
    """Get full audit trail for a specific user."""
    audit = AuditService(db)
    return audit.get_user_audit_trail(user_id, limit)


@router.get("/users/{user_id}/consents")
async def user_consents(
    user_id: int,
    admin:   User = Depends(require_admin),
    db:      Session = Depends(get_db),
):
    """Get all consent records for a user — legal evidence."""
    recs = db.query(ConsentRecord).filter_by(user_id=user_id).order_by(
        ConsentRecord.created_at.desc()
    ).all()

    return [
        {
            "id":             r.id,
            "consent_type":   r.consent_type,
            "doc_version":    r.document_version,
            "doc_hash":       r.document_hash,
            "sig_hash":       r.signature_hash,
            "ip":             r.ip_address,
            "accepted":       r.accepted,
            "timestamp":      r.created_at.isoformat(),
        }
        for r in recs
    ]


# ── Audit Log Management ──────────────────────────────────────────────────────

@router.get("/audit-logs")
async def audit_logs(
    skip:     int  = 0,
    limit:    int  = 100,
    severity: str  = "",
    event:    str  = "",
    admin:    User = Depends(require_admin),
    db:       Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if severity:
        q = q.filter(AuditLog.severity == severity)
    if event:
        q = q.filter(AuditLog.event_type.ilike(f"%{event}%"))
    total = q.count()
    logs  = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "logs": [
            {
                "id":        l.id,
                "event":     l.event_type,
                "user_id":   l.user_id,
                "user_email":l.user_email,
                "ip":        l.ip_address,
                "severity":  l.severity,
                "payload":   json.loads(l.payload or "{}"),
                "hash":      l.entry_hash,
                "prev_hash": l.prev_hash,
                "timestamp": l.created_at.isoformat(),
            }
            for l in logs
        ],
    }


@router.get("/audit-logs/verify")
async def verify_audit_chain(
    admin: User    = Depends(require_admin),
    db:    Session = Depends(get_db),
):
    """Verify the audit log hash chain hasn't been tampered with."""
    audit = AuditService(db)
    return audit.verify_chain()


# ── Legal Documents ───────────────────────────────────────────────────────────

@router.get("/legal")
async def list_legal_docs(
    admin: User    = Depends(require_admin),
    db:    Session = Depends(get_db),
):
    docs = db.query(LegalDocument).order_by(
        LegalDocument.doc_type, LegalDocument.created_at.desc()
    ).all()

    return [
        {
            "id":           d.id,
            "doc_type":     d.doc_type,
            "version":      d.version,
            "title":        d.title,
            "is_active":    d.is_active,
            "content_hash": d.content_hash,
            "updated_at":   d.updated_at.isoformat() if d.updated_at else "",
            "content":      d.content,
        }
        for d in docs
    ]


class LegalDocBody(BaseModel):
    doc_type:       str = Field(..., description="tos | privacy | risk | cookies | about")
    title:          str
    content:        str = Field(..., description="HTML content of the legal document")
    version:        Optional[str] = None
    slug:           Optional[str] = None
    show_in_footer: bool = False
    show_in_nav:    bool = False
    show_in_signup: bool = False
    footer_order:   int  = 0


@router.post("/legal")
async def create_legal_doc(
    body:    LegalDocBody,
    request: Request,
    admin:   User    = Depends(require_admin),
    db:      Session = Depends(get_db),
):
    """Create or update a legal document. Old version stays in history."""
    db.query(LegalDocument).filter_by(doc_type=body.doc_type, is_active=True).update(
        {"is_active": False}
    )

    version      = body.version or datetime.utcnow().strftime("%Y-%m-%d")
    content_hash = hashlib.sha256(body.content.encode()).hexdigest()

    # Auto-generate slug if not provided
    slug = body.slug or body.title.lower().replace(" ", "-").replace("'", "")

    doc = LegalDocument(
        doc_type       = body.doc_type,
        version        = version,
        title          = body.title,
        slug           = slug,
        content        = body.content,
        is_active      = True,
        show_in_footer = body.show_in_footer,
        show_in_nav    = body.show_in_nav,
        show_in_signup = body.show_in_signup,
        footer_order   = body.footer_order,
        content_hash   = content_hash,
        updated_by     = admin.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    AuditService(db).log(
        AuditEvent.ADMIN_CONTENT_UPDATED, admin.id, admin.email,
        get_ip(request),
        payload={"doc_type": body.doc_type, "version": version,
                 "footer": body.show_in_footer, "nav": body.show_in_nav, "signup": body.show_in_signup},
    )
    return {"id": doc.id, "version": version, "content_hash": content_hash, "status": "published"}


@router.patch("/legal/{doc_id}/visibility")
async def update_visibility(
    doc_id:  int,
    body:    dict,
    request: Request,
    admin:   User    = Depends(require_admin),
    db:      Session = Depends(get_db),
):
    """Update visibility of an existing active document without creating a new version."""
    doc = db.query(LegalDocument).filter_by(id=doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if "show_in_footer" in body: doc.show_in_footer = body["show_in_footer"]
    if "show_in_nav"    in body: doc.show_in_nav    = body["show_in_nav"]
    if "show_in_signup" in body: doc.show_in_signup = body["show_in_signup"]
    if "footer_order"   in body: doc.footer_order   = body["footer_order"]
    db.commit()
    AuditService(db).log(AuditEvent.ADMIN_CONTENT_UPDATED, admin.id, admin.email,
                         get_ip(request), payload={"doc_id": doc_id, "visibility": body})
    return {"status": "updated"}


@router.get("/legal/{doc_type}/active")
async def get_active_doc(
    doc_type: str,
    db:       Session = Depends(get_db),
):
    """Public — get currently active version of a legal doc."""
    doc = db.query(LegalDocument).filter_by(doc_type=doc_type, is_active=True).first()
    if not doc:
        raise HTTPException(404, f"No active {doc_type} document found")
    return {
        "doc_type":      doc.doc_type,
        "version":       doc.version,
        "title":         doc.title,
        "slug":          doc.slug,
        "content":       doc.content,
        "content_hash":  doc.content_hash,
        "show_in_footer":doc.show_in_footer,
        "show_in_nav":   doc.show_in_nav,
        "show_in_signup":doc.show_in_signup,
        "updated_at":    doc.updated_at.isoformat() if doc.updated_at else "",
    }


@router.get("/legal/public/navigation")
async def get_nav_docs(db: Session = Depends(get_db)):
    """Public — get all docs marked for footer or nav (used by frontend to build links)."""
    docs = db.query(LegalDocument).filter(
        LegalDocument.is_active == True,
    ).order_by(LegalDocument.footer_order).all()

    return {
        "footer": [
            {"title": d.title, "doc_type": d.doc_type, "slug": d.slug}
            for d in docs if d.show_in_footer
        ],
        "nav": [
            {"title": d.title, "doc_type": d.doc_type, "slug": d.slug}
            for d in docs if d.show_in_nav
        ],
        "signup": [
            {"title": d.title, "doc_type": d.doc_type, "slug": d.slug}
            for d in docs if d.show_in_signup
        ],
    }


# ── Company Settings ──────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(
    admin: User    = Depends(require_admin),
    db:    Session = Depends(get_db),
):
    settings = db.query(CompanySettings).all()
    return {s.key: {"value": s.value, "description": s.description, "is_public": s.is_public} for s in settings}


class SettingBody(BaseModel):
    value:       str
    description: Optional[str] = None
    is_public:   bool = False


@router.put("/settings/{key}")
async def update_setting(
    key:     str,
    body:    SettingBody,
    request: Request,
    admin:   User    = Depends(require_admin),
    db:      Session = Depends(get_db),
):
    setting = db.query(CompanySettings).filter_by(key=key).first()
    if setting:
        setting.value       = body.value
        setting.is_public   = body.is_public
        if body.description:
            setting.description = body.description
        setting.updated_by  = admin.id
    else:
        setting = CompanySettings(
            key=key, value=body.value,
            description=body.description or "",
            is_public=body.is_public,
            updated_by=admin.id,
        )
        db.add(setting)
    db.commit()

    AuditService(db).log(
        AuditEvent.ADMIN_CONTENT_UPDATED, admin.id, admin.email,
        get_ip(request), payload={"setting_key": key, "new_value": body.value[:100]},
    )
    return {"key": key, "status": "updated"}


@router.get("/settings/public")
async def public_settings(db: Session = Depends(get_db)):
    """No auth — public company settings (company name, support email, etc.)"""
    settings = db.query(CompanySettings).filter_by(is_public=True).all()
    return {s.key: s.value for s in settings}


# ── Kill Switch ───────────────────────────────────────────────────────────────

@router.post("/kill-switch")
async def global_kill_switch(
    request: Request,
    admin:   User    = Depends(require_admin),
    db:      Session = Depends(get_db),
):
    """
    Emergency: halt ALL trading across all users.
    Sets a global flag. Bot loop checks this flag every cycle.
    """
    setting = db.query(CompanySettings).filter_by(key="global_trading_halted").first()
    if setting:
        setting.value = "true"
        setting.updated_by = admin.id
    else:
        db.add(CompanySettings(key="global_trading_halted", value="true",
                               description="Emergency trading halt", updated_by=admin.id))
    db.commit()

    AuditService(db).log(
        AuditEvent.ADMIN_KILL_SWITCH, admin.id, admin.email,
        get_ip(request), payload={"action": "HALT_ALL"}, severity="critical",
    )

    logger.critical(f"KILL SWITCH ACTIVATED by admin {admin.email}")
    return {"status": "ALL_TRADING_HALTED", "activated_by": admin.email, "at": datetime.utcnow().isoformat()}


@router.post("/kill-switch/release")
async def release_kill_switch(
    request: Request,
    admin:   User    = Depends(require_admin),
    db:      Session = Depends(get_db),
):
    setting = db.query(CompanySettings).filter_by(key="global_trading_halted").first()
    if setting:
        setting.value = "false"
        setting.updated_by = admin.id
        db.commit()
    AuditService(db).log(
        AuditEvent.ADMIN_KILL_SWITCH, admin.id, admin.email,
        get_ip(request), payload={"action": "RELEASE"}, severity="warning",
    )
    return {"status": "trading_resumed", "released_by": admin.email}


# ── Platform Stats for Admin ──────────────────────────────────────────────────

@router.get("/stats/trading")
async def trading_stats(
    days:  int  = 7,
    admin: User = Depends(require_admin),
    db:    Session = Depends(get_db),
):
    from datetime import date
    results = []
    for i in range(days):
        d = (datetime.utcnow() - timedelta(days=i)).date()
        day_str = str(d)
        trades  = db.query(Trade).filter(Trade.trade_date == day_str).all()
        pnl     = sum(t.pnl or 0 for t in trades if t.status == "closed")
        results.append({
            "date":    day_str,
            "trades":  len(trades),
            "pnl":     round(pnl, 2),
            "winners": sum(1 for t in trades if (t.pnl or 0) > 0),
            "losers":  sum(1 for t in trades if (t.pnl or 0) < 0),
        })
    return results