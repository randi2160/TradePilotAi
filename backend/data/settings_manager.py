"""
User settings manager — persists capital, targets, watchlist, and
portfolio equity history to a local JSON file so settings survive restarts.
"""
import json
import logging
import os
from datetime import datetime

import config

logger   = logging.getLogger(__name__)
SETTINGS_FILE = "user_settings.json"


_DEFAULTS = {
    "capital":          config.CAPITAL,
    "daily_target_min": config.DAILY_TARGET_MIN,
    "daily_target_max": config.DAILY_TARGET_MAX,
    "max_daily_loss":   config.MAX_DAILY_LOSS,
    "watchlist":        list(config.DEFAULT_WATCHLIST),
    "equity_history":   [],    # [{time, value}, …]  — last 7 days, sampled every 5 min
    "updated_at":       "",
}


class SettingsManager:
    def __init__(self, path: str = SETTINGS_FILE):
        self.path = path
        self._data: dict = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self._data = {**_DEFAULTS, **json.load(f)}
                logger.info("User settings loaded ✓")
                return
            except Exception as e:
                logger.warning(f"Settings load error: {e}")
        self._data = dict(_DEFAULTS)
        self._save()

    def _save(self):
        self._data["updated_at"] = datetime.now().isoformat()
        try:
            with open(self.path, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error(f"Settings save error: {e}")

    # ── Capital & targets ─────────────────────────────────────────────────────

    def get_capital(self) -> float:
        return float(self._data.get("capital", config.CAPITAL))

    def set_capital(self, amount: float):
        if amount < 100:
            raise ValueError("Minimum capital is $100")
        if amount > 1_000_000:
            raise ValueError("Maximum capital is $1,000,000")
        self._data["capital"] = round(amount, 2)
        self._save()
        logger.info(f"Capital updated to ${amount:,.2f}")

    def get_targets(self) -> dict:
        return {
            "daily_target_min": self._data.get("daily_target_min", config.DAILY_TARGET_MIN),
            "daily_target_max": self._data.get("daily_target_max", config.DAILY_TARGET_MAX),
            "max_daily_loss":   self._data.get("max_daily_loss",   config.MAX_DAILY_LOSS),
        }

    def set_targets(self, target_min: float, target_max: float, max_loss: float):
        if target_min <= 0 or target_max <= 0:
            raise ValueError("Targets must be positive")
        if target_min >= target_max:
            raise ValueError("Min target must be less than max target")
        if max_loss <= 0:
            raise ValueError("Max loss must be positive")
        self._data["daily_target_min"] = round(target_min, 2)
        self._data["daily_target_max"] = round(target_max, 2)
        self._data["max_daily_loss"]   = round(max_loss, 2)
        self._save()

    # ── Watchlist ─────────────────────────────────────────────────────────────

    def get_watchlist(self) -> list:
        return list(self._data.get("watchlist", config.DEFAULT_WATCHLIST))

    def set_watchlist(self, symbols: list):
        clean = [s.upper().strip() for s in symbols if s.strip()]
        if not clean:
            raise ValueError("Watchlist cannot be empty")
        if len(clean) > 50:
            raise ValueError("Max 50 symbols allowed")
        self._data["watchlist"] = clean
        self._save()

    def add_symbol(self, symbol: str):
        sym = symbol.upper().strip()
        wl  = self.get_watchlist()
        if sym not in wl:
            wl.append(sym)
            self.set_watchlist(wl)

    def remove_symbol(self, symbol: str):
        sym = symbol.upper().strip()
        wl  = [s for s in self.get_watchlist() if s != sym]
        self.set_watchlist(wl)

    # ── Equity history (portfolio value over time) ────────────────────────────

    def record_equity(self, value: float):
        """Call every 5 minutes with current portfolio equity."""
        history = self._data.get("equity_history", [])
        history.append({
            "time":  datetime.now().isoformat(),
            "value": round(value, 2),
        })
        # Keep last 2,016 points = 7 days × 390 min/day × 1 sample/5 min
        self._data["equity_history"] = history[-2016:]
        self._save()

    def get_equity_history(self, hours: int = 24) -> list:
        """Return equity history for the last N hours."""
        from datetime import timedelta
        cutoff   = (datetime.now() - timedelta(hours=hours)).isoformat()
        history  = self._data.get("equity_history", [])
        filtered = [p for p in history if p["time"] >= cutoff]
        return filtered if filtered else history[-50:]   # always return something

    # ── Full settings snapshot ────────────────────────────────────────────────

    def all(self) -> dict:
        return {
            "capital":          self.get_capital(),
            **self.get_targets(),
            "watchlist":        self.get_watchlist(),
            "updated_at":       self._data.get("updated_at", ""),
        }
