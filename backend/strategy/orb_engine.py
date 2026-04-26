"""
Opening Range Breakout (ORB) — additive strategy module.

What it does
------------
The first 15 minutes of the regular session (9:30–9:45 ET) tend to set the
day's playable range. When price breaks above that range later in the morning
on confirming volume, it's one of the highest-probability long setups in
intraday trading. This module:

  1. Records the high/low of each symbol from 9:30–9:45 ET (the "opening
     range") into an in-memory cache.
  2. Between 9:45 and 11:00 ET, watches for a breakout above the range high
     accompanied by volume ≥ 1.5× the recent average.
  3. Returns a signal dict that the main engine can fuse with its ensemble
     output — ORB never replaces the ensemble decision, it boosts confidence
     when both agree, or stands as an independent BUY when the ensemble is
     ambivalent (HOLD with ≥ 0.50 conf).

Why a separate module
---------------------
We're explicitly NOT touching strategy/engine.py's ensemble or setup classifier.
This file is purely additive: the engine asks ORB "anything for this symbol?"
and either uses it or ignores it. If ORB throws or returns None, the existing
flow runs unchanged.

Time window logic uses pytz so DST is handled — no hardcoded UTC offset like
the frontend used to do.
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime
from typing import Optional

import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

# Window definitions (NYSE regular hours: open 9:30, close 16:00)
RANGE_START = dtime(9, 30)   # ← begin recording opening range
RANGE_END   = dtime(9, 45)   # ← range complete; breakouts can fire after
SCAN_END    = dtime(11, 0)   # ← stop generating new ORB entries (mid-day chop)

# Tunable thresholds — kept conservative so ORB only fires on clear setups.
VOLUME_MULTIPLE   = 1.5     # breakout candle volume must be ≥ this × recent avg
RSI_FLOOR         = 50      # below 50 = no momentum confirmation
RSI_CEILING       = 75      # above 75 = overextended, late-to-the-party
MIN_RANGE_PCT     = 0.0015  # range must be at least 0.15% of price (filter dead stocks)
ORB_BASE_CONFIDENCE = 0.62  # confidence assigned when a clean breakout fires


def _now_et() -> datetime:
    return datetime.now(ET)


def _et_time_now() -> dtime:
    return _now_et().time()


class ORBEngine:
    """One instance per StrategyEngine. Holds the per-symbol opening ranges
    accumulated during the 9:30-9:45 window and answers breakout queries."""

    def __init__(self):
        # symbol -> {"high": float, "low": float, "date": str, "completed": bool}
        self._ranges: dict[str, dict] = {}
        self._last_log_date: str = ""

    # ── Public API the main engine calls ─────────────────────────────────────

    def is_active(self) -> bool:
        """True between 9:30 and 11:00 ET on weekdays. The engine can call
        this once per scan cycle as a cheap gate before doing any per-symbol
        work."""
        now = _now_et()
        if now.weekday() >= 5:           # Saturday/Sunday
            return False
        t = now.time()
        return RANGE_START <= t < SCAN_END

    def in_recording_window(self) -> bool:
        return RANGE_START <= _et_time_now() < RANGE_END

    def in_breakout_window(self) -> bool:
        return RANGE_END <= _et_time_now() < SCAN_END

    def update_range(self, symbol: str, df) -> None:
        """Record the bar at the current time into this symbol's opening range.
        df is a pandas DataFrame with at least 'high' and 'low' columns,
        indexed by timestamp. Last row = most recent bar.

        Idempotent and cheap: every call just stretches the running min/max.
        Resets at midnight ET so a new trading day starts fresh."""
        if df is None or df.empty:
            return
        if not self.in_recording_window():
            return

        try:
            cur = df.iloc[-1]
            today_str = _now_et().strftime("%Y-%m-%d")
            entry = self._ranges.get(symbol)
            # New day or first time seeing this symbol → reset
            if entry is None or entry.get("date") != today_str:
                entry = {
                    "high":      float(cur["high"]),
                    "low":       float(cur["low"]),
                    "date":      today_str,
                    "completed": False,
                }
            else:
                entry["high"] = max(entry["high"], float(cur["high"]))
                entry["low"]  = min(entry["low"],  float(cur["low"]))
            self._ranges[symbol] = entry
        except Exception as e:
            logger.debug(f"ORB update_range {symbol}: {e}")

    def finalize_if_due(self, symbol: str) -> None:
        """Call once after 9:45 ET to mark the range complete. Safe to call
        repeatedly. We use this so breakout detection only fires on a settled
        range, not while it's still expanding."""
        entry = self._ranges.get(symbol)
        if entry is None:
            return
        if entry.get("completed"):
            return
        if _et_time_now() >= RANGE_END:
            entry["completed"] = True
            self._ranges[symbol] = entry
            # Single info log per day per symbol to keep noise low
            today = entry.get("date", "")
            if today != self._last_log_date:
                logger.info(
                    f"ORB range finalized: {symbol} "
                    f"high=${entry['high']:.2f} low=${entry['low']:.2f}"
                )

    def check_breakout(self, symbol: str, df) -> Optional[dict]:
        """Return an ORB signal dict if `symbol` is breaking above its
        finalized opening range right now with volume + momentum confirmation.
        Otherwise None.

        Output shape mirrors what ensemble.predict() returns so the caller
        can treat it like any other signal:
            {"signal": "BUY", "confidence": 0.62, "atr": …, "reasons": [...]}
        """
        if df is None or df.empty:
            return None
        if not self.in_breakout_window():
            return None

        entry = self._ranges.get(symbol)
        if entry is None or not entry.get("completed"):
            return None
        # Stale entry from yesterday? Bail.
        if entry.get("date") != _now_et().strftime("%Y-%m-%d"):
            return None

        try:
            cur       = df.iloc[-1]
            close     = float(cur["close"])
            range_hi  = float(entry["high"])
            range_lo  = float(entry["low"])
        except Exception as e:
            logger.debug(f"ORB check_breakout {symbol}: bar read failed: {e}")
            return None

        # Filter out dead-range stocks — if the opening range is tiny, the
        # "breakout" is meaningless noise.
        rng_pct = (range_hi - range_lo) / max(close, 0.01)
        if rng_pct < MIN_RANGE_PCT:
            return None

        # Must actually be ABOVE the range high (we go long-only)
        if close <= range_hi:
            return None

        # Volume confirmation — pull volume_ratio if the indicator pipeline
        # already added it; otherwise compute a quick ratio against last 20
        # bars so ORB still works on dataframes that skipped indicators.
        vol_ratio = float(cur.get("volume_ratio", 0) or 0)
        if vol_ratio <= 0 and "volume" in df.columns and len(df) >= 21:
            try:
                avg_vol = float(df["volume"].iloc[-21:-1].mean())
                if avg_vol > 0:
                    vol_ratio = float(cur["volume"]) / avg_vol
            except Exception:
                vol_ratio = 0
        if vol_ratio < VOLUME_MULTIPLE:
            return None

        # RSI sanity — the breakout should have momentum but not be exhausted.
        rsi = float(cur.get("rsi", 50) or 50)
        if rsi < RSI_FLOOR or rsi > RSI_CEILING:
            return None

        atr = float(cur.get("atr", 0) or 0)
        return {
            "signal":     "BUY",
            "confidence": ORB_BASE_CONFIDENCE,
            "price":      close,
            "atr":        atr,
            "orb":        True,
            "orb_high":   range_hi,
            "orb_low":    range_lo,
            "reasons": [
                f"ORB breakout {range_hi:.2f}→{close:.2f} on {vol_ratio:.1f}× vol, RSI={rsi:.0f}"
            ],
        }
