"""
Morviq AI — Stripe Subscription System
Tiers: Free | Subscriber $29/mo | Pro $79/mo

Setup:
1. pip install stripe
2. Add to .env:
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   STRIPE_PRICE_SUBSCRIBER=price_...
   STRIPE_PRICE_PRO=price_...
3. Create products in Stripe Dashboard, get price IDs
4. Set webhook endpoint: https://yourdomain.com/api/billing/webhook
   Events: customer.subscription.created/updated/deleted, checkout.session.completed
"""
import os
import logging
from datetime import datetime
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.auth      import get_current_user
from database.database import get_db
from database.models   import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["Billing"])

# ── Stripe config ─────────────────────────────────────────────────────────────
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PRICE_SUBSCRIBER= os.getenv("STRIPE_PRICE_SUBSCRIBER", "")
PRICE_PRO       = os.getenv("STRIPE_PRICE_PRO",        "")

PLANS = {
    "free": {
        "name":        "Free",
        "price":       0,
        "price_id":    None,
        "features": [
            "Full AI engine — paper trading only",
            "Social feed (15-min delay)",
            "Follow up to 10 traders",
            "IPO calendar & news",
            "Full performance dashboard",
        ],
        "limits": {
            "live_trading":   False,
            "copy_leaders":   0,
            "groups":         1,
            "ai_analyses":    10,   # per day
        },
    },
    "subscriber": {
        "name":        "Subscriber",
        "price":       29,
        "price_id":    PRICE_SUBSCRIBER,
        "features": [
            "Everything in Free",
            "Live real-money AI trading",
            "Real-time social feed",
            "Auto-copy up to 2 leaders",
            "Create 1 trading group",
            "IPO pre-listing alerts",
            "Priority support",
        ],
        "limits": {
            "live_trading":   True,
            "copy_leaders":   2,
            "groups":         1,
            "ai_analyses":    100,
        },
    },
    "pro": {
        "name":        "Pro",
        "price":       79,
        "price_id":    PRICE_PRO,
        "features": [
            "Everything in Subscriber",
            "Auto-copy up to 10 leaders",
            "Unlimited trading groups",
            "Become a copyable leader",
            "Advanced analytics & API",
            "Dedicated account manager",
            "Faster AI analysis (priority queue)",
        ],
        "limits": {
            "live_trading":   True,
            "copy_leaders":   10,
            "groups":         999,
            "ai_analyses":    999,
        },
    },
}


def get_user_plan(user: User) -> str:
    """Return the user's current plan tier. Admins always get Pro."""
    if getattr(user, "is_admin", False):
        return "pro"
    tier = getattr(user, "subscription_tier", "free") or "free"
    return tier if tier in PLANS else "free"


def require_plan(min_tier: str):
    """
    Dependency: gate a route behind a minimum subscription tier.
    Admins ALWAYS bypass — they have full access to everything.
    Usage: Depends(require_plan("subscriber"))
    """
    tier_order = {"free": 0, "subscriber": 1, "pro": 2}

    def _check(user: User = Depends(get_current_user)):
        # Admins bypass all restrictions
        if getattr(user, "is_admin", False):
            return user

        current = get_user_plan(user)
        if tier_order.get(current, 0) < tier_order.get(min_tier, 0):
            raise HTTPException(
                status_code=402,
                detail={
                    "error":       "subscription_required",
                    "message":     f"This feature requires the {min_tier.title()} plan.",
                    "upgrade_url": "/dashboard?tab=billing",
                    "required":    min_tier,
                    "current":     current,
                }
            )
        return user

    return _check


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans():
    """Public — return all available plans."""
    return [
        {
            "tier":     tier,
            "name":     plan["name"],
            "price":    plan["price"],
            "features": plan["features"],
            "limits":   plan["limits"],
        }
        for tier, plan in PLANS.items()
    ]


@router.get("/status")
async def billing_status(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Get current user's subscription status."""
    is_admin = getattr(user, "is_admin", False)
    tier     = get_user_plan(user)
    plan     = PLANS[tier]

    # Check for admin test mode override
    test_tier = getattr(user, "admin_test_tier", None)

    return {
        "tier":               tier,
        "plan_name":          plan["name"],
        "price":              plan["price"],
        "limits":             plan["limits"],
        "is_admin":           is_admin,
        "admin_full_access":  is_admin,
        "admin_test_tier":    test_tier,
        "stripe_customer_id": getattr(user, "stripe_customer_id", None),
        "subscription_id":    getattr(user, "stripe_subscription_id", None),
        "current_period_end": getattr(user, "subscription_period_end", None),
        "cancel_at_period_end": getattr(user, "subscription_cancel_at_period_end", False),
    }


class TestModeBody(BaseModel):
    tier: Optional[str] = None   # None = reset to real tier


@router.post("/admin/test-mode")
async def set_test_mode(
    body: TestModeBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Admin only — simulate being on a different billing tier."""
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Admin access required")

    valid_tiers = list(PLANS.keys()) + [None]
    if body.tier not in valid_tiers:
        raise HTTPException(400, f"Invalid tier. Must be one of: {list(PLANS.keys())}")

    # Store test tier on user record temporarily
    if hasattr(user, "admin_test_tier"):
        user.admin_test_tier = body.tier
        db.commit()

    action = f"Simulating tier: {body.tier}" if body.tier else "Reset to real tier"
    return {
        "status":     "ok",
        "action":     action,
        "real_tier":  getattr(user, "subscription_tier", "free"),
        "test_tier":  body.tier,
        "message":    f"Admin test mode: {action}",
    }


class CheckoutBody(BaseModel):
    tier:        str   # "subscriber" | "pro"
    success_url: str   = "/dashboard?tab=billing&success=1"
    cancel_url:  str   = "/dashboard?tab=billing"


@router.post("/checkout")
async def create_checkout(
    body: CheckoutBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Create a Stripe checkout session."""
    if not stripe.api_key:
        raise HTTPException(500, "Stripe not configured — add STRIPE_SECRET_KEY to .env")

    plan = PLANS.get(body.tier)
    if not plan or not plan["price_id"]:
        raise HTTPException(400, f"Invalid tier or price not configured: {body.tier}")

    # Get or create Stripe customer
    customer_id = getattr(user, "stripe_customer_id", None)
    if not customer_id:
        customer = stripe.Customer.create(
            email    = user.email,
            metadata = {"user_id": str(user.id), "platform": "morviq_ai"},
        )
        customer_id = customer.id
        user.stripe_customer_id = customer_id
        db.commit()

    # Create checkout session
    session = stripe.checkout.Session.create(
        customer              = customer_id,
        payment_method_types  = ["card"],
        line_items            = [{"price": plan["price_id"], "quantity": 1}],
        mode                  = "subscription",
        success_url           = body.success_url + "&session_id={CHECKOUT_SESSION_ID}",
        cancel_url            = body.cancel_url,
        metadata              = {
            "user_id":  str(user.id),
            "tier":     body.tier,
            "platform": "morviq_ai",
        },
        subscription_data     = {
            "metadata": {"user_id": str(user.id), "tier": body.tier}
        },
    )
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/portal")
async def customer_portal(
    user: User = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    """Create a Stripe Customer Portal session for managing subscription."""
    if not stripe.api_key:
        raise HTTPException(500, "Stripe not configured")

    customer_id = getattr(user, "stripe_customer_id", None)
    if not customer_id:
        raise HTTPException(400, "No subscription found")

    session = stripe.billing_portal.Session.create(
        customer   = customer_id,
        return_url = "/dashboard?tab=billing",
    )
    return {"portal_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe webhook handler.
    Configure in Stripe Dashboard → Webhooks → Add endpoint
    Events: checkout.session.completed, customer.subscription.updated,
            customer.subscription.deleted
    """
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(400, "Invalid webhook signature")
    else:
        import json
        event = json.loads(payload)
        logger.warning("Webhook received without signature verification — set STRIPE_WEBHOOK_SECRET")

    event_type = event["type"]
    logger.info(f"Stripe webhook: {event_type}")

    if event_type == "checkout.session.completed":
        session  = event["data"]["object"]
        user_id  = session.get("metadata", {}).get("user_id")
        tier     = session.get("metadata", {}).get("tier", "subscriber")
        sub_id   = session.get("subscription")

        if user_id:
            user = db.query(User).filter_by(id=int(user_id)).first()
            if user:
                user.subscription_tier           = tier
                user.stripe_subscription_id      = sub_id
                user.stripe_customer_id          = session.get("customer")
                db.commit()
                logger.info(f"User {user.email} upgraded to {tier}")

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        sub     = event["data"]["object"]
        cust_id = sub.get("customer")
        status  = sub.get("status")   # active, past_due, canceled, etc.
        tier    = sub.get("metadata", {}).get("tier", "subscriber")

        user = db.query(User).filter_by(stripe_customer_id=cust_id).first()
        if user:
            if status == "active":
                user.subscription_tier = tier
            elif status in ("canceled", "unpaid", "past_due"):
                user.subscription_tier = "free"

            period_end = sub.get("current_period_end")
            if period_end:
                user.subscription_period_end = datetime.fromtimestamp(period_end).isoformat()
            user.subscription_cancel_at_period_end = sub.get("cancel_at_period_end", False)
            user.stripe_subscription_id = sub.get("id")
            db.commit()
            logger.info(f"Subscription {status} for user {user.email} — tier: {user.subscription_tier}")

    elif event_type == "customer.subscription.deleted":
        sub     = event["data"]["object"]
        cust_id = sub.get("customer")
        user = db.query(User).filter_by(stripe_customer_id=cust_id).first()
        if user:
            user.subscription_tier = "free"
            user.stripe_subscription_id = None
            db.commit()
            logger.info(f"Subscription cancelled for {user.email} — downgraded to free")

    return {"received": True}