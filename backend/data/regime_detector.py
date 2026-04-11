"""
Market Regime Detector — classifies current market conditions into:
  • trending_up    — strong uptrend, momentum strategies work best
  • trending_down  — strong downtrend, short/fade strategies work best
  • choppy         — range-bound, mean reversion / bounce works best
  • breakout       — fresh breakout from consolidation
  • volatile       — high volatility, reduce size, widen stops
  • low_vol        — very low volatility, avoid scalping

Uses SPY as the market proxy.
"""
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RegimeDetector:

    def detect(self, df: pd.DataFrame) -> dict:
        """
        Classify market regime from SPY OHLCV bars.
        Returns regime label + confidence + recommended strategies.
        """
        if len(df) < 30:
            return self._default()

        try:
            closes  = df["close"].values
            highs   = df["high"].values
            lows    = df["low"].values
            volumes = df["volume"].values

            # ── Trend strength (ADX-like) ─────────────────────────────────────
            price_changes = np.diff(closes)
            trend_strength = abs(np.mean(price_changes[-20:])) / np.std(price_changes[-20:]) if np.std(price_changes[-20:]) > 0 else 0

            # ── Directional bias ──────────────────────────────────────────────
            ema_fast = self._ema(closes, 9)
            ema_slow = self._ema(closes, 21)
            ema_long = self._ema(closes, 50)

            cur_fast  = ema_fast[-1]
            cur_slow  = ema_slow[-1]
            cur_long  = ema_long[-1]
            cur_price = closes[-1]

            bullish_alignment = cur_fast > cur_slow > cur_long
            bearish_alignment = cur_fast < cur_slow < cur_long

            # ── Volatility (ATR / price) ───────────────────────────────────────
            trs     = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
                       for i in range(1, len(closes))]
            atr     = np.mean(trs[-14:])
            atr_pct = atr / cur_price * 100

            # ── Range check (high-low range vs ATR) ───────────────────────────
            recent_high = np.max(highs[-20:])
            recent_low  = np.min(lows[-20:])
            range_pct   = (recent_high - recent_low) / recent_low * 100

            # ── Volume trend ──────────────────────────────────────────────────
            vol_recent  = np.mean(volumes[-5:])
            vol_avg     = np.mean(volumes[-20:])
            vol_ratio   = vol_recent / vol_avg if vol_avg > 0 else 1

            # ── Price momentum (rate of change) ───────────────────────────────
            roc_5  = (closes[-1] - closes[-5])  / closes[-5]  * 100 if len(closes) >= 5  else 0
            roc_20 = (closes[-1] - closes[-20]) / closes[-20] * 100 if len(closes) >= 20 else 0

            # ── Classify ──────────────────────────────────────────────────────
            if atr_pct > 2.5:
                regime     = "volatile"
                confidence = 0.80
                strategies = ["reduce_size", "wider_stops", "avoid_scalp"]
                description = "High volatility — reduce position sizes, use wider stops"

            elif bullish_alignment and trend_strength > 1.0 and roc_5 > 0.3:
                regime     = "trending_up"
                confidence = min(0.5 + trend_strength * 0.1, 0.92)
                strategies = ["momentum_breakout", "pullback_long", "vwap_reclaim"]
                description = "Strong uptrend — buy breakouts and VWAP reclaims"

            elif bearish_alignment and trend_strength > 1.0 and roc_5 < -0.3:
                regime     = "trending_down"
                confidence = min(0.5 + trend_strength * 0.1, 0.92)
                strategies = ["fade_rips", "breakdown_short", "avoid_long"]
                description = "Strong downtrend — avoid longs, fade bounces"

            elif range_pct < 1.5 and trend_strength < 0.5:
                regime     = "choppy"
                confidence = 0.70
                strategies = ["mean_reversion", "range_scalp", "peak_bounce"]
                description = "Choppy/ranging — use mean reversion and bounce strategies"

            elif vol_ratio > 2.0 and atr_pct > 1.5:
                regime     = "breakout"
                confidence = 0.75
                strategies = ["momentum_breakout", "volume_surge_long"]
                description = "Potential breakout — high volume expansion, follow momentum"

            elif atr_pct < 0.5:
                regime     = "low_vol"
                confidence = 0.65
                strategies = ["avoid_scalp", "peak_bounce"]
                description = "Very low volatility — avoid scalping, wait for expansion"

            else:
                regime     = "neutral"
                confidence = 0.50
                strategies = ["momentum_breakout", "peak_bounce", "mean_reversion"]
                description = "Mixed conditions — use selective setups with strict filters"

            return {
                "regime":      regime,
                "confidence":  round(confidence, 2),
                "description": description,
                "strategies":  strategies,
                "metrics": {
                    "trend_strength":    round(float(trend_strength), 2),
                    "atr_pct":           round(float(atr_pct), 3),
                    "range_pct":         round(float(range_pct), 2),
                    "roc_5day":          round(float(roc_5), 2),
                    "roc_20day":         round(float(roc_20), 2),
                    "volume_ratio":      round(float(vol_ratio), 2),
                    "bullish_alignment": bullish_alignment,
                    "bearish_alignment": bearish_alignment,
                    "current_price":     round(float(cur_price), 2),
                    "ema9":              round(float(cur_fast), 2),
                    "ema21":             round(float(cur_slow), 2),
                    "ema50":             round(float(cur_long), 2),
                },
                "trade_advice": self._trade_advice(regime),
            }

        except Exception as e:
            logger.error(f"RegimeDetector error: {e}")
            return self._default()

    def _trade_advice(self, regime: str) -> dict:
        advice = {
            "trending_up":   {"size_mult": 1.0, "stop_mult": 1.0, "min_rr": 2.0, "trade": True,  "note": "Normal sizing, standard stops"},
            "trending_down": {"size_mult": 0.5, "stop_mult": 1.2, "min_rr": 2.0, "trade": True,  "note": "Half size on longs, wider stops"},
            "choppy":        {"size_mult": 0.7, "stop_mult": 0.8, "min_rr": 1.5, "trade": True,  "note": "Smaller size, tighter stops, shorter holds"},
            "breakout":      {"size_mult": 1.2, "stop_mult": 1.1, "min_rr": 2.5, "trade": True,  "note": "Slightly larger size, higher R:R required"},
            "volatile":      {"size_mult": 0.4, "stop_mult": 1.5, "min_rr": 3.0, "trade": True,  "note": "Very small size, wide stops, high R:R required"},
            "low_vol":       {"size_mult": 0.6, "stop_mult": 0.7, "min_rr": 1.5, "trade": True,  "note": "Reduced size, tight stops"},
            "neutral":       {"size_mult": 0.8, "stop_mult": 1.0, "min_rr": 2.0, "trade": True,  "note": "Conservative sizing"},
        }
        return advice.get(regime, advice["neutral"])

    @staticmethod
    def _ema(prices: np.ndarray, period: int) -> np.ndarray:
        alpha  = 2 / (period + 1)
        result = np.zeros_like(prices, dtype=float)
        result[0] = prices[0]
        for i in range(1, len(prices)):
            result[i] = alpha * prices[i] + (1 - alpha) * result[i-1]
        return result

    @staticmethod
    def _default() -> dict:
        return {
            "regime":      "neutral",
            "confidence":  0.50,
            "description": "Insufficient data for regime detection",
            "strategies":  ["momentum_breakout", "peak_bounce"],
            "metrics":     {},
            "trade_advice": {"size_mult": 0.8, "stop_mult": 1.0, "min_rr": 2.0, "trade": True, "note": "Default"},
        }
