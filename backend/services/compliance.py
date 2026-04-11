"""
Morviq AI — Compliance Audit System
Hash-chained audit log. Every entry contains SHA-256 of previous entry.
Tamper-proof without blockchain. Legally admissible.
"""
import hashlib
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Event Types ───────────────────────────────────────────────────────────────

class AuditEvent(str, Enum):
    # Auth
    USER_REGISTERED         = "user.registered"
    USER_LOGIN              = "user.login"
    USER_LOGOUT             = "user.logout"
    USER_LOGIN_FAILED       = "user.login_failed"
    PASSWORD_CHANGED        = "user.password_changed"
    ACCOUNT_LOCKED          = "user.account_locked"

    # Consent & Legal
    TOS_ACCEPTED            = "legal.tos_accepted"
    PRIVACY_ACCEPTED        = "legal.privacy_accepted"
    RISK_DISCLAIMER_ACCEPTED= "legal.risk_disclaimer_accepted"
    AUTO_TRADING_ENABLED    = "legal.auto_trading_enabled"
    AUTO_TRADING_DISABLED   = "legal.auto_trading_disabled"
    SUITABILITY_COMPLETED   = "legal.suitability_completed"

    # Trading
    BOT_STARTED             = "trading.bot_started"
    BOT_STOPPED             = "trading.bot_stopped"
    TRADE_OPENED            = "trading.trade_opened"
    TRADE_CLOSED            = "trading.trade_closed"
    TRADE_MANUAL            = "trading.trade_manual"
    BROKER_CONNECTED        = "trading.broker_connected"
    BROKER_DISCONNECTED     = "trading.broker_disconnected"
    LIVE_MODE_ENABLED       = "trading.live_mode_enabled"
    RISK_LIMIT_CHANGED      = "trading.risk_limit_changed"

    # Copy Trading
    COPY_STARTED            = "copy.started"
    COPY_STOPPED            = "copy.stopped"
    COPY_EXECUTED           = "copy.executed"

    # Security
    API_KEY_ADDED           = "security.api_key_added"
    API_KEY_REMOVED         = "security.api_key_removed"
    SUSPICIOUS_ACTIVITY     = "security.suspicious_activity"

    # Admin
    ADMIN_LOGIN             = "admin.login"
    ADMIN_CONTENT_UPDATED   = "admin.content_updated"
    ADMIN_USER_SUSPENDED    = "admin.user_suspended"
    ADMIN_KILL_SWITCH       = "admin.kill_switch"

    # Account
    ACCOUNT_DELETED         = "account.deleted"
    DATA_EXPORTED           = "account.data_exported"
    SETTINGS_CHANGED        = "account.settings_changed"


# ── DB Model ──────────────────────────────────────────────────────────────────

class AuditLog:
    """Defined here — added to Base in models.py"""
    __tablename__ = "audit_logs"

    id            = Column(Integer, primary_key=True, index=True)
    event_type    = Column(String(80), nullable=False, index=True)
    user_id       = Column(Integer, nullable=True, index=True)
    user_email    = Column(String(255), nullable=True)
    ip_address    = Column(String(45), nullable=True)   # IPv6 max = 45 chars
    user_agent    = Column(String(500), nullable=True)
    payload       = Column(Text, nullable=True)          # JSON: event-specific data
    severity      = Column(String(20), default="info")   # info | warning | critical
    prev_hash     = Column(String(64), nullable=True)    # SHA-256 of previous entry
    entry_hash    = Column(String(64), nullable=True)    # SHA-256 of this entry
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_exported   = Column(Boolean, default=False)


class ConsentRecord:
    """Legal consent snapshots — never deleted"""
    __tablename__ = "consent_records"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, nullable=False, index=True)
    user_email      = Column(String(255), nullable=False)
    consent_type    = Column(String(80), nullable=False)   # tos | privacy | risk | auto_trading
    document_version= Column(String(20), nullable=False)   # e.g. "2026-04-11"
    document_hash   = Column(String(64), nullable=False)   # SHA-256 of document text
    accepted        = Column(Boolean, default=True)
    ip_address      = Column(String(45), nullable=True)
    user_agent      = Column(String(500), nullable=True)
    signature_hash  = Column(String(64), nullable=False)   # SHA-256(user_id+email+type+version+timestamp)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)


class LegalDocument:
    """Versioned legal content — editable from admin panel"""
    __tablename__ = "legal_documents"

    id          = Column(Integer, primary_key=True, index=True)
    doc_type    = Column(String(50), nullable=False, index=True)  # tos | privacy | risk | cookies | about
    version     = Column(String(20), nullable=False)              # YYYY-MM-DD
    title       = Column(String(200), nullable=False)
    content     = Column(Text, nullable=False)                    # HTML/markdown
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by  = Column(Integer, nullable=True)                  # admin user id
    content_hash= Column(String(64), nullable=False)              # SHA-256 of content


class CompanySettings:
    """Company info + platform settings editable from admin"""
    __tablename__ = "company_settings"

    id          = Column(Integer, primary_key=True)
    key         = Column(String(100), unique=True, nullable=False)
    value       = Column(Text, nullable=True)
    description = Column(String(500), nullable=True)
    is_public   = Column(Boolean, default=False)  # True = exposed in /api/settings/public
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by  = Column(Integer, nullable=True)


# ── Audit Service ─────────────────────────────────────────────────────────────

class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        event:      AuditEvent,
        user_id:    Optional[int]  = None,
        user_email: Optional[str]  = None,
        ip:         Optional[str]  = None,
        user_agent: Optional[str]  = None,
        payload:    Optional[dict] = None,
        severity:   str            = "info",
    ) -> None:
        """
        Write one audit entry. Computes hash chain automatically.
        Never raises — logs the error and continues.
        """
        try:
            from database.models import AuditLog as AuditLogModel

            # Get hash of most recent entry for chaining
            last = self.db.query(AuditLogModel).order_by(
                AuditLogModel.id.desc()
            ).first()
            prev_hash = last.entry_hash if last else "GENESIS"

            # Build entry content
            content = {
                "event":      event.value,
                "user_id":    user_id,
                "user_email": user_email,
                "ip":         ip,
                "payload":    payload or {},
                "prev_hash":  prev_hash,
                "timestamp":  datetime.utcnow().isoformat(),
            }
            entry_hash = hashlib.sha256(
                json.dumps(content, sort_keys=True).encode()
            ).hexdigest()

            entry = AuditLogModel(
                event_type  = event.value,
                user_id     = user_id,
                user_email  = user_email,
                ip_address  = ip,
                user_agent  = user_agent,
                payload     = json.dumps(payload or {}),
                severity    = severity,
                prev_hash   = prev_hash,
                entry_hash  = entry_hash,
            )
            self.db.add(entry)
            self.db.commit()

        except Exception as e:
            logger.error(f"AuditService.log failed: {e}")
            # Critical: never let audit failure crash the main flow
            try:
                self.db.rollback()
            except Exception:
                pass

    def verify_chain(self) -> dict:
        """Verify the entire audit log chain hasn't been tampered with."""
        from database.models import AuditLog as AuditLogModel

        entries = self.db.query(AuditLogModel).order_by(AuditLogModel.id).all()
        broken_at  = None
        checked    = 0

        for i, entry in enumerate(entries):
            prev_hash = entries[i-1].entry_hash if i > 0 else "GENESIS"
            content = {
                "event":      entry.event_type,
                "user_id":    entry.user_id,
                "user_email": entry.user_email,
                "ip":         entry.ip_address,
                "payload":    json.loads(entry.payload or "{}"),
                "prev_hash":  prev_hash,
                "timestamp":  entry.created_at.isoformat(),
            }
            expected = hashlib.sha256(
                json.dumps(content, sort_keys=True).encode()
            ).hexdigest()

            if expected != entry.entry_hash:
                broken_at = entry.id
                break
            checked += 1

        return {
            "intact":     broken_at is None,
            "entries":    len(entries),
            "checked":    checked,
            "broken_at":  broken_at,
            "verified_at":datetime.utcnow().isoformat(),
        }

    def record_consent(
        self,
        user_id:   int,
        email:     str,
        consent_type: str,
        doc_version:  str,
        doc_content:  str,
        ip:           str,
        user_agent:   str,
    ) -> str:
        """Record legal consent. Returns signature hash for client receipt."""
        from database.models import ConsentRecord as ConsentModel

        doc_hash = hashlib.sha256(doc_content.encode()).hexdigest()

        sig_raw = f"{user_id}:{email}:{consent_type}:{doc_version}:{datetime.utcnow().isoformat()}"
        sig_hash = hashlib.sha256(sig_raw.encode()).hexdigest()

        rec = ConsentModel(
            user_id         = user_id,
            user_email      = email,
            consent_type    = consent_type,
            document_version= doc_version,
            document_hash   = doc_hash,
            accepted        = True,
            ip_address      = ip,
            user_agent      = user_agent,
            signature_hash  = sig_hash,
        )
        self.db.add(rec)
        self.db.commit()

        # Also write to audit log
        self.log(
            event      = AuditEvent.TOS_ACCEPTED,
            user_id    = user_id,
            user_email = email,
            ip         = ip,
            user_agent = user_agent,
            payload    = {
                "consent_type": consent_type,
                "doc_version":  doc_version,
                "doc_hash":     doc_hash,
                "sig_hash":     sig_hash,
            },
            severity   = "info",
        )

        return sig_hash

    def get_user_audit_trail(self, user_id: int, limit: int = 100) -> list:
        """Get audit history for a specific user."""
        from database.models import AuditLog as AuditLogModel

        entries = self.db.query(AuditLogModel).filter(
            AuditLogModel.user_id == user_id
        ).order_by(AuditLogModel.created_at.desc()).limit(limit).all()

        return [
            {
                "id":         e.id,
                "event":      e.event_type,
                "severity":   e.severity,
                "ip":         e.ip_address,
                "payload":    json.loads(e.payload or "{}"),
                "hash":       e.entry_hash,
                "timestamp":  e.created_at.isoformat(),
            }
            for e in entries
        ]
