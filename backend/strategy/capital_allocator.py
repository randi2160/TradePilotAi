"""
Capital Allocator — AI decides the optimal split between
AI Scalper and Peak Bounce strategies based on:
  • Current market regime (trending vs choppy)
  • Recent win rates of each strategy
  • Volatility (ATR) of top symbols
  • Time of day (bounce works better midday, scalp works at open)
  • News sentiment (strong sentiment → favor scalper)
  • Pattern strength of bounce candidates
"""
import logging
from datetime import datetime
from typing import Optional

import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


class CapitalAllocator:
    def __init__(self, total_capital: float, daily_goal: float):
        self.total_capital  = total_capital
        self.daily_goal     = daily_goal
        self.scalper_pct    = 0.60   # default 60/40 before AI runs
        self.bounce_pct     = 0.40
        self._last_split    = {}
        self._history: list = []     # track split decisions over time

    # ── AI Split Decision ─────────────────────────────────────────────────────

    def compute_split(
        self,
        scalper_stats:   dict,
        bounce_stats:    dict,
        market_regime:   str  = "unknown",
        sentiment_score: float = 0.0,
        volatility:      float = 0.0,
        top_bounce_strength: float = 0.0,
    ) -> dict:
        """
        Compute optimal capital split using weighted scoring.
        Returns allocation for both strategies.
        """
        now  = datetime.now(ET)
        hour = now.hour + now.minute / 60

        scalper_score = 50.0   # base
        bounce_score  = 50.0

        reasons = []

        # ── 1. Time of day ────────────────────────────────────────────────────
        # Scalper: best at open (9:30-11) and close (14:30-15:30)
        # Bounce:  best midday (11-14) when patterns stabilize
        if 9.5 <= hour <= 11.0:
            scalper_score += 20
            bounce_score  -= 10
            reasons.append("Open session → favor scalper")
        elif 11.0 <= hour <= 14.0:
            bounce_score  += 20
            scalper_score -= 5
            reasons.append("Midday → favor bounce patterns")
        elif 14.5 <= hour <= 15.5:
            scalper_score += 15
            bounce_score  -= 5
            reasons.append("Power hour → favor scalper")
        elif hour > 15.5:
            scalper_score -= 20
            bounce_score  -= 20
            reasons.append("Late session → reduce both")

        # ── 2. Market regime ──────────────────────────────────────────────────
        if market_regime in ("trending_bullish", "trending_bearish"):
            scalper_score += 15
            reasons.append(f"Trending market → scalper edge")
        elif market_regime == "choppy":
            bounce_score  += 20
            scalper_score -= 10
            reasons.append("Choppy market → bounce patterns reliable")
        elif market_regime == "risk_off":
            scalper_score -= 15
            bounce_score  -= 10
            reasons.append("Risk-off → reduce exposure")

        # ── 3. Recent win rates ───────────────────────────────────────────────
        scalper_wr = scalper_stats.get("win_rate", 50)
        bounce_wr  = bounce_stats.get("success_rate", 50) * 100

        if scalper_wr > bounce_wr + 15:
            scalper_score += 15
            reasons.append(f"Scalper outperforming ({scalper_wr:.0f}% vs {bounce_wr:.0f}%)")
        elif bounce_wr > scalper_wr + 15:
            bounce_score  += 15
            reasons.append(f"Bounce outperforming ({bounce_wr:.0f}% vs {scalper_wr:.0f}%)")

        # ── 4. Today's P&L (protect winning strategy) ─────────────────────────
        scalper_pnl = scalper_stats.get("realized_pnl", 0)
        bounce_pnl  = bounce_stats.get("total_captured", 0)
        total_pnl   = scalper_pnl + bounce_pnl

        # If one is losing, reduce its allocation
        if scalper_pnl < -self.total_capital * 0.01:
            scalper_score -= 20
            reasons.append("Scalper losing today — reducing allocation")
        if bounce_pnl < -self.total_capital * 0.01:
            bounce_score  -= 20
            reasons.append("Bounce losing today — reducing allocation")

        # ── 5. News sentiment ─────────────────────────────────────────────────
        if sentiment_score > 0.3:
            scalper_score += 10
            reasons.append("Strong bullish sentiment → scalper boost")
        elif sentiment_score < -0.2:
            scalper_score -= 10
            bounce_score  -= 5
            reasons.append("Bearish sentiment → reduce both")

        # ── 6. Bounce pattern strength ────────────────────────────────────────
        if top_bounce_strength >= 70:
            bounce_score  += 15
            reasons.append(f"Strong bounce pattern available ({top_bounce_strength:.0f}/100)")
        elif top_bounce_strength < 40:
            bounce_score  -= 10
            reasons.append("No strong bounce patterns — reduce bounce")

        # ── 7. Volatility ─────────────────────────────────────────────────────
        if volatility > 0.02:    # high vol > 2%
            scalper_score += 10
            reasons.append("High volatility → scalper advantage")
        elif volatility < 0.005:  # very low vol
            bounce_score  += 10
            reasons.append("Low volatility → bounce patterns stable")

        # ── Normalize to percentages ──────────────────────────────────────────
        total = scalper_score + bounce_score
        if total <= 0:
            scalper_pct = 0.50
            bounce_pct  = 0.50
        else:
            scalper_pct = scalper_score / total
            bounce_pct  = bounce_score  / total

        # Clamp: neither strategy gets less than 25% or more than 75%
        scalper_pct = max(0.25, min(0.75, scalper_pct))
        bounce_pct  = 1.0 - scalper_pct

        self.scalper_pct = round(scalper_pct, 3)
        self.bounce_pct  = round(bounce_pct,  3)

        result = self._build_result(reasons, scalper_score, bounce_score)
        self._last_split = result
        self._history.append({**result, "timestamp": datetime.now().isoformat()})
        self._history = self._history[-48:]   # keep last 48 decisions

        logger.info(
            f"Capital split: Scalper {self.scalper_pct:.0%} "
            f"/ Bounce {self.bounce_pct:.0%} | {reasons[0] if reasons else ''}"
        )
        return result

    def _build_result(self, reasons, scalper_score, bounce_score) -> dict:
        scalper_cap = round(self.total_capital * self.scalper_pct, 2)
        bounce_cap  = round(self.total_capital * self.bounce_pct,  2)
        s_goal = round(self.daily_goal * self.scalper_pct, 2)
        b_goal = round(self.daily_goal * self.bounce_pct,  2)

        return {
            "total_capital":    self.total_capital,
            "daily_goal":       self.daily_goal,
            "scalper": {
                "capital":      scalper_cap,
                "pct":          round(self.scalper_pct * 100, 1),
                "daily_target": s_goal,
                "loss_limit":   round(scalper_cap * 0.03, 2),  # 3% max loss
                "score":        round(scalper_score, 1),
            },
            "bounce": {
                "capital":      bounce_cap,
                "pct":          round(self.bounce_pct * 100, 1),
                "daily_target": b_goal,
                "loss_limit":   round(bounce_cap * 0.03, 2),
                "score":        round(bounce_score, 1),
            },
            "reasons":          reasons,
            "computed_at":      datetime.now(ET).isoformat(),
        }

    # ── Public accessors ──────────────────────────────────────────────────────

    def get_scalper_capital(self)  -> float:
        return round(self.total_capital * self.scalper_pct, 2)

    def get_bounce_capital(self)   -> float:
        return round(self.total_capital * self.bounce_pct, 2)

    def get_current_split(self)    -> dict:
        return self._last_split or self._build_result(["Default split"], 60, 40)

    def get_history(self)          -> list:
        return list(reversed(self._history[-10:]))

    def force_split(self, scalper_pct: float):
        """Manually override the split."""
        self.scalper_pct = max(0.25, min(0.75, scalper_pct))
        self.bounce_pct  = 1.0 - self.scalper_pct
        logger.info(f"Split manually overridden: {self.scalper_pct:.0%}/{self.bounce_pct:.0%}")
