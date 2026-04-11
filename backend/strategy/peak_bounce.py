"""
Peak Bounce Strategy Engine
═══════════════════════════
Detects repeating peak/valley patterns in stock price, calculates
optimal position size to hit a profit target per bounce, and manages
the full auto-execute ladder (buy dip → sell peak → re-enter → repeat).

Key concepts:
  • Peak   = local price high (resistance zone)
  • Valley = local price low  (support zone)
  • Bounce = price travel from valley back to peak
  • Ladder = sequence of bounces toward daily goal
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Execution cost model ──────────────────────────────────────────────────────
SLIPPAGE_PCT   = 0.0005   # 0.05% per side (realistic for liquid stocks)
COMMISSION     = 0.0      # Alpaca is commission-free
TOTAL_COST_PCT = SLIPPAGE_PCT * 2  # round-trip

# ── Time window presets ───────────────────────────────────────────────────────
WINDOWS = {
    "30min":   {"bars": 6,   "label": "30 min (scalp)",        "min_bounces": 2},
    "1hour":   {"bars": 12,  "label": "1 hour (short swing)",  "min_bounces": 2},
    "2hour":   {"bars": 24,  "label": "2 hours (recommended)", "min_bounces": 3},
    "4hour":   {"bars": 48,  "label": "4 hours (half day)",    "min_bounces": 2},
    "fullday": {"bars": 78,  "label": "Full day",              "min_bounces": 3},
}
DEFAULT_WINDOW = "2hour"


@dataclass
class BouncePattern:
    symbol:           str
    window:           str
    avg_peak:         float
    avg_valley:       float
    bounce_height:    float       # avg_peak - avg_valley
    bounce_pct:       float       # bounce_height / avg_valley * 100
    success_rate:     float       # % of times price returned to peak
    avg_recovery_min: float       # avg minutes to recover from valley to peak
    consistency:      float       # 0-1 score (how repeatable the pattern is)
    volume_confirmed: bool        # is volume supporting the pattern?
    pattern_strength: float       # combined score 0-100
    peaks:            list = field(default_factory=list)
    valleys:          list = field(default_factory=list)
    last_updated:     str  = ""
    current_price:    float = 0.0
    near_valley:      bool  = False
    near_peak:        bool  = False
    atr:              float = 0.0


@dataclass
class BouncePosition:
    symbol:         str
    entry_price:    float
    exit_target:    float
    stop_loss:      float
    shares:         int
    position_value: float
    target_profit:  float
    execution_cost: float
    net_profit_est: float
    min_margin_pct: float
    round_number:   int
    entered_at:     str = ""
    status:         str = "pending"   # pending | open | closed | failed


@dataclass
class ProfitLadder:
    daily_goal:       float
    bounce_target:    float           # profit per bounce
    total_bounces_needed: int
    completed_rounds: list = field(default_factory=list)
    current_round:    int  = 0
    total_captured:   float = 0.0
    remaining:        float = 0.0
    is_complete:      bool  = False
    ai_calculated:    bool  = False   # was bounce_target AI-calculated?
    calculation_note: str   = ""


class PeakBounceEngine:
    def __init__(self, capital: float, daily_goal: float):
        self.capital    = capital
        self.daily_goal = daily_goal
        self._patterns: dict[str, BouncePattern] = {}
        self._positions: dict[str, BouncePosition] = {}
        self._ladders:   dict[str, ProfitLadder]  = {}

    # ══════════════════════════════════════════════════════════════════════════
    # PATTERN DETECTION
    # ══════════════════════════════════════════════════════════════════════════

    def analyze_pattern(
        self,
        df:     pd.DataFrame,
        symbol: str,
        window: str = DEFAULT_WINDOW,
    ) -> Optional[BouncePattern]:
        """
        Detect peak/valley pattern in OHLCV data.
        Returns None if no reliable pattern found.
        """
        if df.empty or len(df) < 10:
            return None

        cfg        = WINDOWS.get(window, WINDOWS[DEFAULT_WINDOW])
        lookback   = min(cfg["bars"], len(df))
        df_window  = df.tail(lookback).copy()
        prices     = df_window["close"].values
        highs      = df_window["high"].values
        lows       = df_window["low"].values
        volumes    = df_window["volume"].values

        # ── Find local peaks and valleys ─────────────────────────────────────
        peaks   = self._find_extrema(highs,  order=2, find_peaks=True)
        valleys = self._find_extrema(lows,   order=2, find_peaks=False)

        if len(peaks) < 2 or len(valleys) < 2:
            logger.debug(f"{symbol}: Not enough peaks/valleys ({len(peaks)}p {len(valleys)}v)")
            return None

        peak_prices   = highs[peaks]
        valley_prices = lows[valleys]

        # ── Basic stats ───────────────────────────────────────────────────────
        avg_peak   = float(np.mean(peak_prices))
        avg_valley = float(np.mean(valley_prices))
        bounce_h   = avg_peak - avg_valley

        if bounce_h <= 0 or avg_valley <= 0:
            return None

        bounce_pct = bounce_h / avg_valley * 100

        # Must have meaningful bounce (> 0.3% to cover execution costs)
        if bounce_pct < 0.3:
            logger.debug(f"{symbol}: Bounce too small ({bounce_pct:.2f}%)")
            return None

        # ── Consistency score ─────────────────────────────────────────────────
        # How tight are the peaks around the average?
        peak_std   = float(np.std(peak_prices))   / avg_peak   if avg_peak   > 0 else 1
        valley_std = float(np.std(valley_prices)) / avg_valley if avg_valley > 0 else 1
        consistency = max(0.0, 1.0 - (peak_std + valley_std) * 5)

        # ── Success rate (did price return to peak after each valley?) ────────
        success_count = 0
        total_pairs   = 0
        recovery_times = []

        for v_idx in valleys:
            # Find next peak after this valley
            next_peaks = [p for p in peaks if p > v_idx]
            if not next_peaks:
                continue
            next_peak = next_peaks[0]
            total_pairs += 1
            if highs[next_peak] >= avg_peak * 0.97:   # within 3% of avg peak
                success_count += 1
                recovery_times.append(next_peak - v_idx)

        success_rate    = success_count / max(total_pairs, 1)
        avg_recovery    = float(np.mean(recovery_times)) * 5 if recovery_times else 30  # in minutes (5min bars)

        # ── Volume confirmation ───────────────────────────────────────────────
        avg_volume    = float(np.mean(volumes))
        recent_volume = float(np.mean(volumes[-3:]))
        vol_confirmed = recent_volume >= avg_volume * 0.8

        # ── ATR ───────────────────────────────────────────────────────────────
        atr = self._calc_atr(df_window)

        # ── Overall pattern strength (0-100) ──────────────────────────────────
        strength = (
            success_rate     * 35 +   # most important
            consistency      * 25 +
            min(bounce_pct / 2, 1) * 20 +
            (1.0 if vol_confirmed else 0.5) * 20
        )

        # ── Current price context ─────────────────────────────────────────────
        current = float(prices[-1])
        near_valley = current <= avg_valley * 1.005   # within 0.5% of valley
        near_peak   = current >= avg_peak   * 0.995   # within 0.5% of peak

        pattern = BouncePattern(
            symbol           = symbol,
            window           = window,
            avg_peak         = round(avg_peak,   2),
            avg_valley       = round(avg_valley, 2),
            bounce_height    = round(bounce_h,   2),
            bounce_pct       = round(bounce_pct, 3),
            success_rate     = round(success_rate, 3),
            avg_recovery_min = round(avg_recovery, 1),
            consistency      = round(consistency,  3),
            volume_confirmed = vol_confirmed,
            pattern_strength = round(strength, 1),
            peaks            = peak_prices.tolist(),
            valleys          = valley_prices.tolist(),
            last_updated     = datetime.now().isoformat(),
            current_price    = round(current, 2),
            near_valley      = near_valley,
            near_peak        = near_peak,
            atr              = round(atr, 4),
        )
        self._patterns[symbol] = pattern
        return pattern

    # ══════════════════════════════════════════════════════════════════════════
    # POSITION SIZING
    # ══════════════════════════════════════════════════════════════════════════

    def calculate_position(
        self,
        pattern:       BouncePattern,
        bounce_target: Optional[float] = None,   # None = AI calculates
        round_number:  int = 1,
    ) -> Optional[BouncePosition]:
        """
        Calculate exact shares and prices to hit the bounce target profit.
        If bounce_target is None, AI calculates the optimal amount.
        """
        valley = pattern.avg_valley
        peak   = pattern.avg_peak
        bounce = pattern.bounce_height

        # ── Execution cost per share (round-trip) ─────────────────────────────
        exec_cost_per_share = valley * TOTAL_COST_PCT

        # Net profit per share after costs
        net_per_share = bounce - exec_cost_per_share
        if net_per_share <= 0:
            logger.warning(f"{pattern.symbol}: Bounce too small after costs")
            return None

        # ── AI-calculated bounce target ───────────────────────────────────────
        ai_calculated = bounce_target is None
        if ai_calculated:
            bounce_target = self._ai_optimal_bounce(
                capital       = self.capital,
                daily_goal    = self.daily_goal,
                net_per_share = net_per_share,
                valley_price  = valley,
                success_rate  = pattern.success_rate,
                round_number  = round_number,
            )

        # ── Shares needed ────────────────────────────────────────────────────
        shares_needed = int(np.ceil(bounce_target / net_per_share))

        # Cap at 20% of capital per position
        max_shares    = int((self.capital * 0.20) / valley)
        shares        = min(shares_needed, max_shares)

        if shares < 1:
            return None

        position_value  = round(shares * valley, 2)
        execution_cost  = round(position_value * TOTAL_COST_PCT, 2)
        net_profit_est  = round(shares * net_per_share, 2)
        min_margin_pct  = round((exec_cost_per_share / valley) * 100 + 0.1, 3)

        # Entry: valley + small confirmation buffer (don't chase)
        entry_price  = round(valley + (pattern.atr * 0.1), 2)
        # Exit: peak - small buffer (don't be greedy, ensure fill)
        exit_target  = round(peak - (pattern.atr * 0.15), 2)
        # Stop: valley - 0.5 ATR
        stop_loss    = round(valley - (pattern.atr * 0.5), 2)

        return BouncePosition(
            symbol         = pattern.symbol,
            entry_price    = entry_price,
            exit_target    = exit_target,
            stop_loss      = stop_loss,
            shares         = shares,
            position_value = position_value,
            target_profit  = bounce_target,
            execution_cost = execution_cost,
            net_profit_est = net_profit_est,
            min_margin_pct = min_margin_pct,
            round_number   = round_number,
            entered_at     = datetime.now().isoformat(),
        )

    def _ai_optimal_bounce(
        self,
        capital:       float,
        daily_goal:    float,
        net_per_share: float,
        valley_price:  float,
        success_rate:  float,
        round_number:  int,
    ) -> float:
        """
        Calculate the optimal bounce target dynamically.
        Starts conservative, increases as we approach daily goal.

        Logic:
        - Aim for 8-15 bounces per day
        - Adjust for success rate (lower success = smaller target per bounce)
        - Reduce position size as goal approaches (protect gains)
        """
        target_bounces = 10                         # aim for ~10 rounds/day
        base_target    = daily_goal / target_bounces

        # Adjust for success rate
        confidence_mult = 0.5 + (success_rate * 0.5)   # 0.5× to 1.0×
        adjusted        = base_target * confidence_mult

        # Conservative early rounds, more aggressive mid-day
        round_mult = min(1.0 + (round_number - 1) * 0.05, 1.3)

        # Cap at 30% of daily goal per bounce
        cap = daily_goal * 0.30

        return round(min(adjusted * round_mult, cap), 2)

    # ══════════════════════════════════════════════════════════════════════════
    # PROFIT LADDER
    # ══════════════════════════════════════════════════════════════════════════

    def create_ladder(
        self,
        symbol:        str,
        daily_goal:    float,
        bounce_target: Optional[float] = None,
        pattern:       Optional[BouncePattern] = None,
    ) -> ProfitLadder:
        ai_calc = bounce_target is None
        if ai_calc and pattern:
            # Use AI calculation for first round
            pos = self.calculate_position(pattern, None, 1)
            bounce_target = pos.target_profit if pos else daily_goal / 10

        if not bounce_target or bounce_target <= 0:
            bounce_target = daily_goal / 10

        bounces_needed = int(np.ceil(daily_goal / bounce_target))

        note = (
            f"AI calculated ${bounce_target:.2f}/bounce "
            f"({bounces_needed} rounds to hit ${daily_goal:.0f} goal)"
            if ai_calc else
            f"Manual: ${bounce_target:.2f}/bounce "
            f"({bounces_needed} rounds needed)"
        )

        ladder = ProfitLadder(
            daily_goal           = daily_goal,
            bounce_target        = bounce_target,
            total_bounces_needed = bounces_needed,
            remaining            = daily_goal,
            ai_calculated        = ai_calc,
            calculation_note     = note,
        )
        self._ladders[symbol] = ladder
        return ladder

    def record_bounce_result(self, symbol: str, actual_profit: float) -> ProfitLadder:
        ladder = self._ladders.get(symbol)
        if not ladder:
            return None

        ladder.current_round   += 1
        ladder.total_captured  += actual_profit
        ladder.remaining        = max(0, ladder.daily_goal - ladder.total_captured)
        ladder.is_complete      = ladder.total_captured >= ladder.daily_goal

        ladder.completed_rounds.append({
            "round":         ladder.current_round,
            "profit":        round(actual_profit, 2),
            "cumulative":    round(ladder.total_captured, 2),
            "remaining":     round(ladder.remaining, 2),
            "timestamp":     datetime.now().isoformat(),
        })

        logger.info(
            f"[LADDER] {symbol} Round {ladder.current_round}: "
            f"+${actual_profit:.2f} | Total: ${ladder.total_captured:.2f} "
            f"/ ${ladder.daily_goal:.2f}"
        )
        return ladder

    # ══════════════════════════════════════════════════════════════════════════
    # ENTRY SIGNAL
    # ══════════════════════════════════════════════════════════════════════════

    def should_enter(
        self,
        pattern:   BouncePattern,
        df:        pd.DataFrame,
        sentiment: dict = None,
    ) -> tuple[bool, str, float]:
        """
        Returns (should_enter, reason, confidence_0_to_1).
        All conditions must pass for entry.
        """
        reasons = []
        score   = 0.0

        # 1. Pattern strength
        if pattern.pattern_strength < 45:
            return False, f"Pattern too weak ({pattern.pattern_strength:.0f}/100)", 0.0

        score += pattern.pattern_strength / 100 * 0.30

        # 2. Price near valley
        if not pattern.near_valley:
            return False, "Price not near valley — wait for dip", 0.0

        score += 0.25
        reasons.append("Price at valley support")

        # 3. Volume confirmation
        if pattern.volume_confirmed:
            score += 0.15
            reasons.append("Volume confirmed")
        else:
            reasons.append("⚠️ Low volume")

        # 4. Success rate
        if pattern.success_rate >= 0.65:
            score += 0.20
            reasons.append(f"High success rate ({pattern.success_rate:.0%})")
        elif pattern.success_rate >= 0.50:
            score += 0.10
            reasons.append(f"Moderate success rate ({pattern.success_rate:.0%})")
        else:
            return False, f"Low success rate ({pattern.success_rate:.0%})", 0.0

        # 5. News sentiment (optional boost)
        if sentiment:
            sent_score = sentiment.get("score", 0)
            if sent_score > 0.2:
                score += 0.10
                reasons.append("Bullish news sentiment")
            elif sent_score < -0.3:
                return False, "Bearish news — skip this bounce", 0.0

        # 6. Time of day (avoid first 15 min and last 30 min)
        now  = datetime.now()
        hour = now.hour + now.minute / 60
        if hour < 9.75 or hour > 15.5:
            return False, "Outside safe trading hours", 0.0

        confidence = round(min(score, 1.0), 3)
        return True, " | ".join(reasons), confidence

    # ══════════════════════════════════════════════════════════════════════════
    # STOCK SELECTION (AI-assisted)
    # ══════════════════════════════════════════════════════════════════════════

    def score_stocks_for_bounce(
        self,
        patterns:   dict[str, BouncePattern],
        sentiments: dict,
        gainers:    list,
    ) -> list[dict]:
        """
        Score all analyzed stocks and return ranked list
        for the best bounce candidates today.
        """
        scored = []

        for symbol, pattern in patterns.items():
            if pattern is None:
                continue

            score = 0.0
            flags = []

            # Pattern quality
            score += pattern.pattern_strength * 0.40

            # Success rate
            score += pattern.success_rate * 30

            # Bounce size (bigger = more potential profit)
            score += min(pattern.bounce_pct * 5, 20)

            # Sentiment boost
            sent = sentiments.get(symbol, {})
            sent_score = sent.get("score", 0)
            if sent_score > 0.2:
                score += 10
                flags.append("📰 Bullish news")
            elif sent_score < -0.2:
                score -= 15
                flags.append("⚠️ Bearish news")

            # Is it a top gainer? (momentum)
            gainer_syms = [g.get("symbol") for g in gainers]
            if symbol in gainer_syms:
                score += 8
                flags.append("🔥 Top gainer")

            # Volume
            if pattern.volume_confirmed:
                score += 5
                flags.append("📊 High volume")

            scored.append({
                "symbol":          symbol,
                "score":           round(score, 1),
                "pattern_strength": pattern.pattern_strength,
                "bounce_pct":      pattern.bounce_pct,
                "success_rate":    pattern.success_rate,
                "near_valley":     pattern.near_valley,
                "flags":           flags,
                "recommended":     score >= 60 and pattern.near_valley,
            })

        return sorted(scored, key=lambda x: x["score"], reverse=True)

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _find_extrema(prices: np.ndarray, order: int = 2, find_peaks: bool = True) -> np.ndarray:
        """Find local peaks or valleys using rolling window comparison."""
        indices = []
        for i in range(order, len(prices) - order):
            window = prices[i-order:i+order+1]
            if find_peaks:
                if prices[i] == np.max(window):
                    indices.append(i)
            else:
                if prices[i] == np.min(window):
                    indices.append(i)
        return np.array(indices)

    @staticmethod
    def _calc_atr(df: pd.DataFrame, period: int = 14) -> float:
        try:
            high  = df["high"].values
            low   = df["low"].values
            close = df["close"].values
            trs   = [max(high[i]-low[i],
                         abs(high[i]-close[i-1]),
                         abs(low[i]-close[i-1]))
                     for i in range(1, len(close))]
            return float(np.mean(trs[-period:])) if trs else 0.0
        except Exception:
            return 0.0

    def get_pattern(self, symbol: str) -> Optional[BouncePattern]:
        return self._patterns.get(symbol)

    def get_ladder(self, symbol: str) -> Optional[ProfitLadder]:
        return self._ladders.get(symbol)

    def get_all_patterns(self) -> dict:
        return {
            sym: {
                "symbol":           p.symbol,
                "window":           p.window,
                "avg_peak":         p.avg_peak,
                "avg_valley":       p.avg_valley,
                "bounce_height":    p.bounce_height,
                "bounce_pct":       p.bounce_pct,
                "success_rate":     p.success_rate,
                "avg_recovery_min": p.avg_recovery_min,
                "consistency":      p.consistency,
                "volume_confirmed": p.volume_confirmed,
                "pattern_strength": p.pattern_strength,
                "current_price":    p.current_price,
                "near_valley":      p.near_valley,
                "near_peak":        p.near_peak,
                "last_updated":     p.last_updated,
            }
            for sym, p in self._patterns.items()
            if p is not None
        }
