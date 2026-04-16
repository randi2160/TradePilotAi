"""
Promote a user to admin in whichever database DATABASE_URL points at.
Works against either SQLite (dev) or Postgres (prod / AWS).

Usage (from /var/www/autotrader/backend on the AWS box):

    # Uses .env for DATABASE_URL, defaults email to khemlall.mangal@gmail.com
    python promote_admin.py

    # Explicit email
    python promote_admin.py khemlall.mangal@gmail.com

    # Revoke instead of grant
    python promote_admin.py khemlall.mangal@gmail.com --revoke

What it does
------------
1. Connects via SQLAlchemy (same engine the app uses), so it reads DATABASE_URL
   from .env just like main.py does.
2. Looks the user up by email (case-insensitive).
3. Sets is_admin = True (or False with --revoke) and commits.
4. Prints before/after state so you can see exactly what changed.
5. Never creates accounts — if the email doesn't exist it tells you to sign up
   through the web UI first (accounts should never be created server-side).
"""
from __future__ import annotations

import sys
from sqlalchemy import func

# Local package imports — run from the backend/ directory.
from database.database import SessionLocal, get_db_type, DATABASE_URL
from database.models   import User


DEFAULT_EMAIL = "khemlall.mangal@gmail.com"


def _mask(url: str) -> str:
    """Hide password in DATABASE_URL when printing."""
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host  = rest.split("@", 1)
    if ":" in creds:
        user, _pw = creds.split(":", 1)
        creds = f"{user}:***"
    return f"{scheme}://{creds}@{host}"


def promote(email: str, revoke: bool = False) -> int:
    target_flag = not revoke
    verb        = "Revoking" if revoke else "Promoting"

    print(f"Database: {get_db_type()}  —  {_mask(DATABASE_URL)}")
    print(f"{verb} {email} → is_admin={target_flag}")
    print("-" * 60)

    with SessionLocal() as db:
        # Case-insensitive email lookup — Postgres defaults to case-sensitive.
        user = (
            db.query(User)
              .filter(func.lower(User.email) == email.strip().lower())
              .first()
        )

        if not user:
            print(f"❌ No user found with email {email!r}")
            print("   Sign up through the web UI first, then re-run this script.")
            # List the few users that DO exist so typos are easy to catch.
            others = db.query(User.email).order_by(User.id.asc()).limit(10).all()
            if others:
                print("   Existing users (first 10):")
                for (e,) in others:
                    print(f"     - {e}")
            return 1

        before = {
            "id":                user.id,
            "email":             user.email,
            "is_admin":          bool(user.is_admin),
            "is_active":         bool(user.is_active),
            "subscription_tier": user.subscription_tier,
        }

        if bool(user.is_admin) == target_flag:
            print(f"✓ Already is_admin={target_flag}. Nothing to change.")
            for k, v in before.items():
                print(f"   {k:<18} {v}")
            return 0

        user.is_admin  = target_flag
        user.is_active = True  # belt & suspenders — don't leave admin disabled
        db.commit()
        db.refresh(user)

        print("Before:")
        for k, v in before.items():
            print(f"   {k:<18} {v}")
        print("After:")
        print(f"   id                 {user.id}")
        print(f"   email              {user.email}")
        print(f"   is_admin           {bool(user.is_admin)}")
        print(f"   is_active          {bool(user.is_active)}")
        print(f"   subscription_tier  {user.subscription_tier}")
        print()
        print(f"✅ Done. Log out and back in so the new claim ships in your JWT.")
        return 0


def main() -> int:
    args   = [a for a in sys.argv[1:] if a]
    revoke = "--revoke" in args
    args   = [a for a in args if a != "--revoke"]
    email  = args[0] if args else DEFAULT_EMAIL
    return promote(email, revoke=revoke)


if __name__ == "__main__":
    raise SystemExit(main())
