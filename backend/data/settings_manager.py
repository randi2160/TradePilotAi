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
            "capital":                    self.get_capital(),
            **self.get_targets(),
            "watchlist":                  self.get_watchlist(),
            "stop_new_trades_hour":       self._data.get("stop_new_trades_hour",  config.STOP_NEW_TRADES_HOUR),
            "stop_new_trades_minute":     self._data.get("stop_new_trades_minute", config.STOP_NEW_TRADES_MINUTE),
            "max_open_positions":         self._data.get("max_open_positions",     config.MAX_OPEN_POSITIONS),
            "engine_mode":                self._data.get("engine_mode",            "stocks_only"),
            "crypto_alloc_pct":           self._data.get("crypto_alloc_pct",       0.30),
            "after_hours_crypto_alloc_pct": self._data.get("after_hours_crypto_alloc_pct", 0.80),
            "crypto_strategy":            self._data.get("crypto_strategy", "scalp"),
            "score_threshold":            self._data.get("score_threshold", 55),
            "updated_at":                 self._data.get("updated_at", ""),
        }

    def set_engine_settings(self, stop_hour: int, stop_minute: int, max_positions: int,
                             engine_mode: str, crypto_alloc: float,
                             after_hours_crypto_alloc: float = 0.80,
                             crypto_strategy: str = "scalp"):
        self._data["stop_new_trades_hour"]        = stop_hour
        self._data["stop_new_trades_minute"]      = stop_minute
        self._data["max_open_positions"]          = max_positions
        self._data["engine_mode"]                 = engine_mode
        self._data["crypto_alloc_pct"]            = round(crypto_alloc, 2)
        self._data["after_hours_crypto_alloc_pct"] = round(min(1.0, max(0.50, after_hours_crypto_alloc)), 2)
        self._data["crypto_strategy"]             = crypto_strategy if crypto_strategy in ("scalp", "bounce") else "scalp"
        self._save()

    def get_after_hours_crypto_alloc(self) -> float:
        return float(self._data.get("after_hours_crypto_alloc_pct", 0.80))

    def get_score_threshold(self) -> int:
        """Minimum score (0-100) for a crypto candidate to be considered valid.
        Lower = more aggressive (more trades), higher = more conservative."""
        return int(self._data.get("score_threshold", 55))

    def set_score_threshold(self, value: int):
        value = max(15, min(85, int(value)))
        self._data["score_threshold"] = value
        self._save()
        logger.info(f"Score threshold updated to {value}")

    def get_profit_milestones(self) -> list:
        """
        Returns list of milestone dicts:
        [{threshold, floor_pct, size_pct, label}, ...]
        Sorted descending by threshold (highest first).
        """
        default = [
            {"threshold": 400, "floor_pct": 0.953, "size_pct": 0.00, "label": "🏆 $400 — Exits only"},
            {"threshold": 300, "floor_pct": 0.950, "size_pct": 0.40, "label": "🥇 $300 — 40% size"},
            {"threshold": 200, "floor_pct": 0.950, "size_pct": 0.50, "label": "🥈 $200 — 50% size"},
            {"threshold": 150, "floor_pct": 0.953, "size_pct": 0.60, "label": "🥉 $150 — 60% size"},
            {"threshold": 100, "floor_pct": 0.950, "size_pct": 0.75, "label": "✅ $100 — 75% size"},
        ]
        saved = self._data.get("profit_milestones", None)
        if saved and isinstance(saved, list) and len(saved) >= 2:
            return sorted(saved, key=lambda x: x["threshold"], reverse=True)
        return default

    def set_profit_milestones(self, milestones: list):
        """Save user-configured milestones."""
        # Validate each milestone
        validated = []
        for m in milestones:
            try:
                validated.append({
                    "threshold": float(m["threshold"]),
                    "floor_pct": float(m.get("floor_pct", 0.95)),
                    "size_pct":  float(m.get("size_pct", 0.5)),
                    "label":     str(m.get("label", f"${m['threshold']}")),
                })
            except Exception:
                continue
        if validated:
            self._data["profit_milestones"] = sorted(validated, key=lambda x: x["threshold"], reverse=True)
            self._save()