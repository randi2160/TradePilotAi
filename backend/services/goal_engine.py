"""
Goal Engine — user sets a monthly profit goal, AI calculates
the optimal daily target, tracks progress, and adjusts dynamically.

Features:
  • Monthly goal → daily target calculation
  • Trading day awareness (excludes weekends/holidays)
  • Catch-up logic (missed days increase remaining daily targets)
  • Progress tracking per day
  • End-of-day report generation
"""
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

GOALS_FILE = "trading_goals.json"

# US market holidays 2025-2026 (approximate)
MARKET_HOLIDAYS = {
    "2025-01-01","2025-01-20","2025-02-17","2025-04-18",
    "2025-05-26","2025-06-19","2025-07-04","2025-09-01",
    "2025-11-27","2025-12-25",
    "2026-01-01","2026-01-19","2026-02-16","2026-04-03",
    "2026-05-25","2026-06-19","2026-07-03","2026-09-07",
    "2026-11-26","2026-12-25",
}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and str(d) not in MARKET_HOLIDAYS


def trading_days_in_month(year: int, month: int) -> list:
    days = []
    d = date(year, month, 1)
    while d.month == month:
        if is_trading_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def trading_days_remaining(from_date: date, year: int, month: int) -> list:
    all_days = trading_days_in_month(year, month)
    return [d for d in all_days if d >= from_date]


class GoalEngine:
    def __init__(self):
        self._data = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if os.path.exists(GOALS_FILE):
            try:
                with open(GOALS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "monthly_goal":   0.0,
            "capital":        5000.0,
            "risk_tolerance": "moderate",
            "goals_history":  [],
            "daily_results":  {},
        }

    def _save(self):
        self._data["updated_at"] = datetime.now().isoformat()
        with open(GOALS_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    # ── Goal setting ──────────────────────────────────────────────────────────

    def set_monthly_goal(
        self,
        monthly_goal:   float,
        capital:        float,
        risk_tolerance: str = "moderate",
    ) -> dict:
        today = date.today()
        remaining_days = trading_days_remaining(today, today.year, today.month)
        total_days     = trading_days_in_month(today.year, today.month)

        # How much have we made so far this month?
        month_key     = today.strftime("%Y-%m")
        earned_so_far = sum(
            v.get("realized_pnl", 0)
            for k, v in self._data.get("daily_results", {}).items()
            if k.startswith(month_key)
        )

        remaining_goal = max(0, monthly_goal - earned_so_far)
        days_left      = len(remaining_days)

        if days_left == 0:
            daily_target = 0.0
        else:
            base_daily = remaining_goal / days_left

            # Risk multiplier
            risk_mult = {"conservative": 0.85, "moderate": 1.0, "aggressive": 1.20}.get(risk_tolerance, 1.0)
            daily_target = base_daily * risk_mult

        # Required daily % return
        daily_pct = (daily_target / capital * 100) if capital > 0 else 0

        # Realistic assessment
        if daily_pct > 5:
            warning = "⚠️ This goal requires >5% daily return — very aggressive. Consider extending timeline."
        elif daily_pct > 2:
            warning = "📊 This goal requires 2-5% daily return — achievable but requires consistent execution."
        elif daily_pct > 0.5:
            warning = "✅ This goal requires <2% daily return — realistic with good signals."
        else:
            warning = "🟢 Very conservative goal — easily achievable."

        result = {
            "monthly_goal":     monthly_goal,
            "capital":          capital,
            "risk_tolerance":   risk_tolerance,
            "earned_so_far":    round(earned_so_far, 2),
            "remaining_goal":   round(remaining_goal, 2),
            "total_trading_days": len(total_days),
            "days_elapsed":     len(total_days) - days_left,
            "days_remaining":   days_left,
            "daily_target":     round(daily_target, 2),
            "daily_target_min": round(daily_target * 0.7, 2),
            "daily_target_max": round(daily_target * 1.3, 2),
            "daily_pct_required": round(daily_pct, 2),
            "warning":          warning,
            "month":            today.strftime("%B %Y"),
            "remaining_days_list": [str(d) for d in remaining_days[:10]],
        }

        self._data["monthly_goal"]   = monthly_goal
        self._data["capital"]        = capital
        self._data["risk_tolerance"] = risk_tolerance
        self._data["current_plan"]   = result
        self._save()
        return result

    def get_current_plan(self) -> dict:
        return self._data.get("current_plan", {})

    def get_monthly_goal(self) -> float:
        return float(self._data.get("monthly_goal", 0))

    def get_daily_targets(self) -> dict:
        plan = self.get_current_plan()
        return {
            "daily_target":     plan.get("daily_target", 0),
            "daily_target_min": plan.get("daily_target_min", 0),
            "daily_target_max": plan.get("daily_target_max", 0),
        }

    # ── Daily result recording ────────────────────────────────────────────────

    def record_daily_result(
        self,
        realized_pnl:   float,
        trade_count:    int,
        win_count:      int,
        notes:          str = "",
    ) -> dict:
        today = str(date.today())
        result = {
            "date":          today,
            "realized_pnl":  round(realized_pnl, 2),
            "trade_count":   trade_count,
            "win_count":     win_count,
            "loss_count":    trade_count - win_count,
            "win_rate":      round(win_count / trade_count * 100, 1) if trade_count else 0,
            "daily_target":  self.get_current_plan().get("daily_target", 0),
            "hit_target":    realized_pnl >= self.get_current_plan().get("daily_target_min", 0),
            "notes":         notes,
            "recorded_at":   datetime.now().isoformat(),
        }
        if "daily_results" not in self._data:
            self._data["daily_results"] = {}
        self._data["daily_results"][today] = result
        self._save()
        return result

    # ── Monthly summary ───────────────────────────────────────────────────────

    def get_monthly_summary(self, year: int = None, month: int = None) -> dict:
        today = date.today()
        year  = year  or today.year
        month = month or today.month
        key   = f"{year}-{month:02d}"

        daily = {
            k: v for k, v in self._data.get("daily_results", {}).items()
            if k.startswith(key)
        }

        total_pnl   = sum(v.get("realized_pnl", 0) for v in daily.values())
        total_trades= sum(v.get("trade_count",   0) for v in daily.values())
        total_wins  = sum(v.get("win_count",     0) for v in daily.values())
        days_traded = len(daily)
        days_hit    = sum(1 for v in daily.values() if v.get("hit_target"))
        monthly_goal= self.get_monthly_goal()
        progress_pct= round(total_pnl / monthly_goal * 100, 1) if monthly_goal > 0 else 0

        return {
            "month":          f"{year}-{month:02d}",
            "monthly_goal":   monthly_goal,
            "total_pnl":      round(total_pnl, 2),
            "progress_pct":   progress_pct,
            "days_traded":    days_traded,
            "days_hit_target": days_hit,
            "target_hit_rate": round(days_hit / days_traded * 100, 1) if days_traded else 0,
            "total_trades":   total_trades,
            "total_wins":     total_wins,
            "win_rate":       round(total_wins / total_trades * 100, 1) if total_trades else 0,
            "daily_breakdown": sorted(daily.values(), key=lambda x: x["date"], reverse=True),
            "on_track":       progress_pct >= (today.day / 21 * 100),  # rough calendar progress
        }

    def get_all_daily_results(self, days: int = 30) -> list:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        results = [
            v for k, v in self._data.get("daily_results", {}).items()
            if k >= cutoff
        ]
        return sorted(results, key=lambda x: x["date"], reverse=True)
