"""
Setup Classifier — categorizes each trade opportunity into a strategy bucket.
Different setups need different entry/exit logic.

Setup types:
  • momentum_breakout   — fresh high, volume surge, above VWAP
  • pullback_long       — uptrend pullback to support/VWAP, bounce entry
  • range_scalp         — tight range, buy support / sell resistance
  • mean_reversion      — oversold/overbought extreme, fade the move
  • vwap_reclaim        — price reclaims VWAP after being below (bullish)
  • failed_breakout     — breakout that rejected, fade back through level
  • no_trade            — conditions don't meet any setup criteria
"""
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SetupClassifier:

    def classify(
        self,
        df:          pd.DataFrame,
        symbol:      str,
        regime:      dict,
        vwap_info:   dict,
        indicators:  dict,
    ) -> dict:
        """
        Classify the current setup for a symbol.
        Returns setup type, quality score, and specific entry/exit rules.
        """
        if len(df) < 20:
            return self._no_trade("Insufficient data")

        closes  = df["close"].values
        highs   = df["high"].values
        lows    = df["low"].values
        volumes = df["volume"].values

        price       = float(closes[-1])
        vwap        = vwap_info.get("vwap", price)
        above_vwap  = vwap_info.get("above_vwap", False)
        reclaim     = vwap_info.get("reclaim", False)
        rsi         = indicators.get("rsi", 50)
        vol_ratio   = indicators.get("volume_ratio", 1.0)
        atr         = indicators.get("atr", price * 0.01)
        macd_diff   = indicators.get("macd_diff", 0)
        bb_pct      = indicators.get("bb_pct", 0.5)

        # Spread estimate (last bar high-low vs price)
        spread_pct = (highs[-1] - lows[-1]) / price * 100

        # Recent high breakout
        recent_high_20 = float(np.max(highs[-20:-1]))
        recent_low_20  = float(np.min(lows[-20:-1]))
        breaking_out   = price > recent_high_20 * 1.002
        breaking_down  = price < recent_low_20  * 0.998

        # Volume surge
        avg_vol      = float(np.mean(volumes[-20:]))
        vol_surge    = vol_ratio >= 2.0
        strong_surge = vol_ratio >= 3.0

        # Momentum
        roc_3 = (closes[-1] - closes[-4]) / closes[-4] * 100 if len(closes) >= 4 else 0

        # Range tightness (consolidation)
        range_5   = (np.max(highs[-5:]) - np.min(lows[-5:])) / price * 100
        tight_range = range_5 < 0.8

        regime_name = regime.get("regime", "neutral")
        regime_mult = regime.get("trade_advice", {}).get("size_mult", 0.8)
        min_rr      = regime.get("trade_advice", {}).get("min_rr", 2.0)

        # ── Hard quality filters (always required) ────────────────────────────
        quality_issues = []
        if spread_pct > 0.5:
            quality_issues.append(f"Spread too wide ({spread_pct:.2f}%)")
        if vol_ratio < 1.2:
            quality_issues.append(f"Low relative volume ({vol_ratio:.1f}×)")
        if atr / price * 100 < 0.1:
            quality_issues.append("ATR too small — not enough movement")

        # ── Classify setup ────────────────────────────────────────────────────

        # 1. Momentum Breakout
        if breaking_out and vol_surge and above_vwap and roc_3 > 0.5:
            quality = min(60 + (vol_ratio - 2) * 10 + (roc_3 * 5), 95)
            return self._setup(
                setup_type   = "momentum_breakout",
                symbol       = symbol,
                quality      = quality,
                quality_issues = quality_issues,
                description  = f"Breaking out above {recent_high_20:.2f} with {vol_ratio:.1f}× volume above VWAP",
                entry_rule   = "Buy on confirmation close above breakout level — do NOT chase",
                stop_rule    = f"Stop below breakout level or ${price - atr * 1.5:.2f}",
                target_rule  = f"Target 2-3× ATR above entry — min R:R {min_rr}:1",
                size_mult    = regime_mult * (1.1 if strong_surge else 1.0),
                min_rr       = min_rr,
                regime       = regime_name,
                indicators   = indicators,
                vwap         = vwap,
            )

        # 2. VWAP Reclaim (strong bullish)
        if reclaim and vol_ratio >= 1.5 and rsi < 65:
            quality = 65 + min(vol_ratio * 5, 20)
            return self._setup(
                setup_type   = "vwap_reclaim",
                symbol       = symbol,
                quality      = quality,
                quality_issues = quality_issues,
                description  = f"Price reclaimed VWAP at ${vwap:.2f} with volume confirmation",
                entry_rule   = "Enter on first candle close above VWAP",
                stop_rule    = f"Stop below VWAP (${vwap:.2f}) — exit immediately if rejected",
                target_rule  = f"Target previous high or 2× ATR above — min R:R {min_rr}:1",
                size_mult    = regime_mult * 0.9,
                min_rr       = min_rr,
                regime       = regime_name,
                indicators   = indicators,
                vwap         = vwap,
            )

        # 3. Pullback Long (trend continuation)
        if above_vwap and rsi < 45 and rsi > 25 and macd_diff > -0.05 and regime_name in ("trending_up", "neutral"):
            quality = 55 + (45 - rsi) * 0.5
            return self._setup(
                setup_type   = "pullback_long",
                symbol       = symbol,
                quality      = quality,
                quality_issues = quality_issues,
                description  = f"Pullback to support above VWAP — RSI {rsi:.0f} showing oversold",
                entry_rule   = "Enter when RSI turns up or price shows first green candle",
                stop_rule    = f"Stop below recent swing low or VWAP (${vwap:.2f})",
                target_rule  = f"Target prior high — min R:R {min_rr}:1",
                size_mult    = regime_mult,
                min_rr       = min_rr,
                regime       = regime_name,
                indicators   = indicators,
                vwap         = vwap,
            )

        # 4. Mean Reversion (extreme RSI)
        if rsi < 25 and bb_pct < 0.05:
            quality = 60 + (25 - rsi) * 1.5
            return self._setup(
                setup_type   = "mean_reversion",
                symbol       = symbol,
                quality      = quality,
                quality_issues = quality_issues,
                description  = f"Extreme oversold — RSI {rsi:.0f} at lower Bollinger Band",
                entry_rule   = "Wait for first green candle confirmation before entry",
                stop_rule    = f"Stop below current low — tight stop, small size",
                target_rule  = f"Target VWAP (${vwap:.2f}) or mid-Bollinger — quick exit",
                size_mult    = regime_mult * 0.7,   # smaller size for mean reversion
                min_rr       = max(min_rr - 0.5, 1.5),
                regime       = regime_name,
                indicators   = indicators,
                vwap         = vwap,
            )

        # 5. Range Scalp (choppy market)
        if tight_range and regime_name in ("choppy", "low_vol") and abs(rsi - 50) > 10:
            quality = 50 + abs(rsi - 50) * 0.5
            direction = "LONG near range support" if rsi < 50 else "SHORT near range resistance"
            return self._setup(
                setup_type   = "range_scalp",
                symbol       = symbol,
                quality      = quality,
                quality_issues = quality_issues,
                description  = f"Tight range consolidation — {direction}",
                entry_rule   = f"{direction} — only trade the edges of the range",
                stop_rule    = "Stop just outside the range — if range breaks, exit immediately",
                target_rule  = "Target opposite side of range — quick profits, no holding",
                size_mult    = regime_mult * 0.6,
                min_rr       = 1.5,
                regime       = regime_name,
                indicators   = indicators,
                vwap         = vwap,
            )

        # 6. Peak Bounce (our existing strategy)
        if bb_pct < 0.15 and rsi < 40 and vol_ratio >= 1.3:
            quality = 50 + (40 - rsi) * 0.8
            return self._setup(
                setup_type   = "peak_bounce",
                symbol       = symbol,
                quality      = quality,
                quality_issues = quality_issues,
                description  = f"Near lower Bollinger Band — potential bounce entry",
                entry_rule   = "Wait for price to stop falling — first sign of buyers",
                stop_rule    = f"Stop ${atr * 0.5:.2f} below entry — tight",
                target_rule  = f"Target mid-Bollinger or VWAP (${vwap:.2f})",
                size_mult    = regime_mult * 0.8,
                min_rr       = 1.5,
                regime       = regime_name,
                indicators   = indicators,
                vwap         = vwap,
            )

        return self._no_trade(
            f"No clear setup — RSI:{rsi:.0f} Vol:{vol_ratio:.1f}× "
            f"{'Above' if above_vwap else 'Below'} VWAP"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _setup(
        setup_type, symbol, quality, quality_issues,
        description, entry_rule, stop_rule, target_rule,
        size_mult, min_rr, regime, indicators, vwap,
    ) -> dict:
        # Penalize quality for issues
        penalized = max(quality - len(quality_issues) * 10, 20)
        tradeable = penalized >= 50 and len(quality_issues) == 0

        return {
            "setup_type":     setup_type,
            "symbol":         symbol,
            "quality":        round(penalized, 1),
            "quality_issues": quality_issues,
            "tradeable":      tradeable,
            "description":    description,
            "entry_rule":     entry_rule,
            "stop_rule":      stop_rule,
            "target_rule":    target_rule,
            "size_mult":      round(size_mult, 2),
            "min_rr":         min_rr,
            "regime":         regime,
            "vwap":           round(vwap, 4),
            "rsi":            round(indicators.get("rsi", 50), 1),
            "volume_ratio":   round(indicators.get("volume_ratio", 1.0), 2),
        }

    @staticmethod
    def _no_trade(reason: str) -> dict:
        return {
            "setup_type":     "no_trade",
            "tradeable":      False,
            "quality":        0,
            "description":    reason,
            "quality_issues": [reason],
        }
