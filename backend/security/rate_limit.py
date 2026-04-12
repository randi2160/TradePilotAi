"""
Morviq AI — Rate Limiting
Protects against brute force and abuse using in-memory counters.
For production, use Redis instead of in-memory for multi-process.
"""
import time
import logging
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter.
    Tracks requests per IP per endpoint group.
    """
    def __init__(self):
        # { (ip, group): [(timestamp, count)] }
        self._windows: Dict[Tuple, list] = defaultdict(list)
        self._blocked: Dict[str, float]  = {}  # ip → blocked_until

    def _clean(self, key: tuple, window_seconds: int):
        now = time.time()
        self._windows[key] = [
            ts for ts in self._windows[key]
            if now - ts < window_seconds
        ]

    def check(
        self,
        ip:              str,
        group:           str,
        limit:           int,
        window_seconds:  int,
        block_seconds:   int = 0,
    ) -> bool:
        """
        Returns True if allowed, False if rate limited.
        Raises HTTPException 429 if blocked.
        """
        now = time.time()

        # Check if IP is blocked
        if ip in self._blocked:
            if now < self._blocked[ip]:
                retry_after = int(self._blocked[ip] - now)
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many attempts. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
            else:
                del self._blocked[ip]

        key = (ip, group)
        self._clean(key, window_seconds)
        count = len(self._windows[key])

        if count >= limit:
            if block_seconds > 0:
                self._blocked[ip] = now + block_seconds
                logger.warning(f"Rate limit exceeded: {ip} on {group} — blocked for {block_seconds}s")
            return False

        self._windows[key].append(now)
        return True

    def reset(self, ip: str, group: str):
        """Call after successful auth to reset failed attempt counter."""
        key = (ip, group)
        self._windows[key] = []
        if ip in self._blocked:
            del self._blocked[ip]


# Global rate limiter instance
_limiter = RateLimiter()


def get_ip(request: Request) -> str:
    return (
        request.headers.get("X-Real-IP") or
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
        request.client.host or
        "unknown"
    )


# ── Rate limit decorators / helpers ──────────────────────────────────────────

def rate_limit_auth(request: Request):
    """
    Auth endpoints: 5 attempts per 15 minutes per IP.
    Block for 15 minutes after exceeded.
    """
    ip = get_ip(request)
    allowed = _limiter.check(
        ip             = ip,
        group          = "auth",
        limit          = 5,
        window_seconds = 900,    # 15 minutes
        block_seconds  = 900,    # block for 15 minutes
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait 15 minutes before trying again.",
            headers={"Retry-After": "900"},
        )


def rate_limit_trading(request: Request):
    """
    Order endpoints: 100 orders per minute per IP.
    """
    ip = get_ip(request)
    allowed = _limiter.check(
        ip             = ip,
        group          = "trading",
        limit          = 100,
        window_seconds = 60,
        block_seconds  = 60,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Order rate limit exceeded. Maximum 100 orders per minute.",
            headers={"Retry-After": "60"},
        )


def rate_limit_api(request: Request, limit: int = 300, window: int = 60):
    """
    General API endpoints: 300 requests per minute.
    """
    ip = get_ip(request)
    allowed = _limiter.check(
        ip             = ip,
        group          = "api",
        limit          = limit,
        window_seconds = window,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {limit} requests per {window} seconds.",
            headers={"Retry-After": str(window)},
        )


def reset_auth_limit(request: Request):
    """Call this after successful login to reset failed attempts."""
    _limiter.reset(get_ip(request), "auth")


def get_rate_limit_status(ip: str) -> dict:
    """Admin: get rate limit status for an IP."""
    return {
        "ip":        ip,
        "auth":      len(_limiter._windows.get((ip, "auth"), [])),
        "trading":   len(_limiter._windows.get((ip, "trading"), [])),
        "api":       len(_limiter._windows.get((ip, "api"), [])),
        "blocked":   ip in _limiter._blocked,
        "blocked_until": _limiter._blocked.get(ip),
    }
