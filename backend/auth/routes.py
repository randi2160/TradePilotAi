"""
Auth routes — register, login, profile management.
All routes prefixed with /api/auth
"""
import logging
import time as _time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from auth.auth import (
    create_access_token, hash_password,
    verify_password, get_current_user,
)
from database.database import get_db
from database.models import User, Watchlist
import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    email:     str = Field(..., description="Valid email address")
    password:  str = Field(..., min_length=8, description="Min 8 characters")
    full_name: str = Field("", description="Display name")
    phone:     str = Field("", description="Phone for future SMS alerts")

class LoginBody(BaseModel):
    email:    str
    password: str

class ProfileUpdate(BaseModel):
    full_name:        Optional[str]  = None
    phone:            Optional[str]  = None
    capital:          Optional[float] = Field(None, gt=100, le=1_000_000)
    daily_target_min: Optional[float] = Field(None, gt=0)
    daily_target_max: Optional[float] = Field(None, gt=0)
    max_daily_loss:   Optional[float] = Field(None, gt=0)
    risk_profile:     Optional[str]  = None
    email_alerts:     Optional[bool] = None
    alpaca_key:       Optional[str]  = None
    alpaca_secret:    Optional[str]  = None
    alpaca_mode:      Optional[str]  = None

class ChangePasswordBody(BaseModel):
    current_password: str
    new_password:     str = Field(..., min_length=8)

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         dict


def _user_dict(user: User) -> dict:
    return {
        "id":               user.id,
        "email":            user.email,
        "full_name":        user.full_name,
        "phone":            user.phone,
        "avatar_initials":  user.avatar_initials or (user.full_name[:2].upper() if user.full_name else user.email[:2].upper()),
        "capital":          user.capital,
        "daily_target_min": user.daily_target_min,
        "daily_target_max": user.daily_target_max,
        "max_daily_loss":   user.max_daily_loss,
        "risk_profile":     user.risk_profile,
        "email_alerts":     user.email_alerts,
        "trading_mode":     user.trading_mode,
        "alpaca_mode":      user.alpaca_mode,
        "has_alpaca_keys":  bool(user.alpaca_key),
        "is_admin":         bool(user.is_admin),
        "subscription_tier": user.subscription_tier or "free",
        "created_at":       str(user.created_at),
        "last_login":       str(user.last_login) if user.last_login else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, summary="Create a new account")
async def register(body: RegisterBody, db: Session = Depends(get_db)):
    # Check duplicate
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email           = body.email.lower().strip(),
        hashed_password = hash_password(body.password),
        full_name       = body.full_name.strip(),
        phone           = body.phone.strip(),
        avatar_initials = body.full_name[:2].upper() if body.full_name else body.email[:2].upper(),
        capital          = config.CAPITAL,
        daily_target_min = config.DAILY_TARGET_MIN,
        daily_target_max = config.DAILY_TARGET_MAX,
        max_daily_loss   = config.MAX_DAILY_LOSS,
    )
    db.add(user)
    db.flush()

    # Create default watchlist
    wl = Watchlist(user_id=user.id, symbols=list(config.DEFAULT_WATCHLIST))
    db.add(wl)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}


@router.post("/login", response_model=TokenResponse, summary="Login and get JWT token")
async def login(body: LoginBody, db: Session = Depends(get_db)):
    """Login with per-step timing so slow logins can be diagnosed in pm2 logs.

    Logs the duration of the User lookup, bcrypt verify, last_login commit, and
    JWT mint. Look for `login[email=...]` lines in pm2 logs when login feels slow.
    """
    t_enter = _time.time()
    email_norm = body.email.lower().strip()
    tag = f"login[email={email_norm}]"
    logger.info(f"{tag} ▶ entry")

    try:
        t0 = _time.time()
        user = db.query(User).filter(User.email == email_norm).first()
        logger.info(f"{tag} user lookup +{_time.time()-t0:.3f}s (found={bool(user)})")

        if not user:
            logger.warning(f"{tag} ◀ 401 no-such-user total=+{_time.time()-t_enter:.3f}s")
            raise HTTPException(status_code=401, detail="Invalid email or password")

        t0 = _time.time()
        pw_ok = verify_password(body.password, user.hashed_password)
        logger.info(f"{tag} bcrypt verify +{_time.time()-t0:.3f}s (ok={pw_ok})")

        if not pw_ok:
            logger.warning(f"{tag} ◀ 401 bad-password total=+{_time.time()-t_enter:.3f}s")
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user.is_active:
            logger.warning(f"{tag} ◀ 403 inactive total=+{_time.time()-t_enter:.3f}s")
            raise HTTPException(status_code=403, detail="Account disabled")

        t0 = _time.time()
        user.last_login = datetime.utcnow()
        db.commit()
        logger.info(f"{tag} last_login commit +{_time.time()-t0:.3f}s")

        t0 = _time.time()
        token = create_access_token({"sub": user.email})
        logger.info(f"{tag} jwt mint +{_time.time()-t0:.3f}s")

        logger.info(f"{tag} ◀ 200 OK total=+{_time.time()-t_enter:.3f}s uid={user.id}")
        return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"{tag} UNEXPECTED total=+{_time.time()-t_enter:.3f}s")
        raise HTTPException(status_code=500, detail="Login failed")


@router.get("/me", summary="Get current user profile")
async def get_me(current_user: User = Depends(get_current_user)):
    return _user_dict(current_user)


@router.put("/profile", summary="Update user profile and trading settings")
async def update_profile(
    body:         ProfileUpdate,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    update_data = body.dict(exclude_none=True)

    # Validate targets
    t_min = update_data.get("daily_target_min", current_user.daily_target_min)
    t_max = update_data.get("daily_target_max", current_user.daily_target_max)
    if t_min >= t_max:
        raise HTTPException(400, "Min target must be less than max target")

    for field, value in update_data.items():
        setattr(current_user, field, value)

    # Update avatar initials if name changed
    if "full_name" in update_data and update_data["full_name"]:
        current_user.avatar_initials = update_data["full_name"][:2].upper()

    db.commit()
    db.refresh(current_user)
    return {"status": "updated", "user": _user_dict(current_user)}


@router.put("/change-password", summary="Change password")
async def change_password(
    body:         ChangePasswordBody,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")

    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"status": "password changed"}


@router.delete("/account", summary="Deactivate account")
async def deactivate_account(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    current_user.is_active = False
    db.commit()
    return {"status": "account deactivated"}
