"""
Crypto Bounce Analyzer — observation-only mode that studies price patterns
to find bounce/mean-reversion opportunities in crypto.

This does NOT execute trades. It analyzes price windows, identifies
spike/dip patterns, calculates statistical edges, and optionally asks
an LLM for entry/exit recommendations.

Math approach:
  1. Bollinger Band envelope — mean ± 2σ over rolling window
  2. Local min/max detection — support/resistance from price pivots
  3. Bounce frequency — how often price touches support and bounces
  4. Spike magnitude — average size of moves from mean to extreme
  5. Mean reversion speed — how fast price returns to mean after spike
  6. Continuation probability — does the trend persist or revert?
  7. Optimal window — which timeframe shows the cleanest patterns?

Output: analysis dict per coin with confidence score + LLM recommendation.
"""
import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class BounceAnalyzer:
    """Analyze crypto price patterns for bounce/mean-reversion setups."""

    def __init__(self):
        self._cache: dict = {}
        self._last_analysis: dict = {}

    async def analyze_all(self, broker, symbols: list, use_llm: bool = True) -> dict:
        """
        Run bounce analysis on all given crypto symbols.
        Returns a dict keyed by ticker with analysis + LLM recommendation.
        """
        import asyncio

        results = {}
        loop = asyncio.get_event_loop()

        # Fetch bars in parallel
        def _fetch(ticker):
            try:
                bars = broker.get_crypto_bars(ticker, "1Min", 300)
                if bars is not None and len(bars) >= 30:
                    return (ticker, bars)
            except Exception:
                pass
            return (ticker, None)

        tasks = [loop.run_in_executor(None, _fetch, t) for t in symbols]
        fetched = await asyncio.gather(*tasks)

        for ticker, bars in fetched:
            if bars is None:
                continue
            try:
                analysis = self._analyze_coin(ticker, bars)
                if analysis:
                    results[ticker] = analysis
            except Exception as e:
                logger.debug(f"BounceAnalyzer {ticker}: {e}")

        # Sort by bounce_score descending
        sorted_results = dict(
            sorted(results.items(),
                   key=lambda x: x[1].get("bounce_score", 0),
                   reverse=True)
        )

        # LLM analysis on top candidates
        if use_llm and sorted_results:
            top_coins = list(sorted_results.keys())[:5]
            llm_recs = await self._get_llm_recommendations(
                {k: sorted_results[k] for k in top_coins}
            )
            for ticker, rec in llm_recs.items():
                if ticker in sorted_results:
                    sorted_results[ticker]["llm_recommendation"] = rec

        self._last_analysis = sorted_results
        return sorted_results

    def _analyze_coin(self, ticker: str, df: pd.DataFrame) -> Optional[dict]:
        """Full statistical analysis of one coin's price action."""
        closes = df["close"].values.astype(float)
        highs  = df["high"].values.astype(float) if "high" in df.columns else closes
        lows   = df["low"].values.astype(float) if "low" in df.columns else closes
        volumes = df["volume"].values.astype(float) if "volume" in df.columns else np.ones(len(closes))

        price = float(closes[-1])
        n = len(closes)
        if n < 30 or price <= 0:
            return None

        # ── 1. Multi-window Bollinger analysis ────────────────────────────
        windows = {}
        for period, label in [(20, "20min"), (60, "1hr"), (120, "2hr")]:
            if n >= period:
                window_data = closes[-period:]
                mean  = float(np.mean(window_data))
                std   = float(np.std(window_data))
                upper = mean + 2 * std
                lower = mean - 2 * std

                # Where is price relative to bands? 0=lower, 0.5=mean, 1=upper
                band_pos = (price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
                band_pos = max(0, min(1, band_pos))

                # Volatility as % of price
                vol_pct = (std / mean * 100) if mean > 0 else 0

                windows[label] = {
                    "mean":      round(mean, 6),
                    "std":       round(std, 6),
                    "upper":     round(upper, 6),
                    "lower":     round(lower, 6),
                    "band_pos":  round(band_pos, 3),
                    "vol_pct":   round(vol_pct, 3),
                    "period":    period,
                }

        # ── 2. Support/Resistance from local pivots ───────────────────────
        supports, resistances = self._find_pivots(closes, lows, highs)

        # Nearest support and resistance
        nearest_support    = max([s for s in supports if s < price], default=None)
        nearest_resistance = min([r for r in resistances if r > price], default=None)

        dist_to_support    = ((price - nearest_support) / price * 100) if nearest_support else None
        dist_to_resistance = ((nearest_resistance - price) / price * 100) if nearest_resistance else None

        # ── 3. Bounce detection — count touches of lower band that bounced ─
        bounce_stats = self._count_bounces(closes, lows, highs)

        # ── 4. Spike analysis — magnitude and frequency ───────────────────
        spike_stats = self._analyze_spikes(closes)

        # ── 5. Mean reversion speed — how fast price returns to mean ──────
        reversion_stats = self._mean_reversion_speed(closes)

        # ── 6. Trend vs range classification ──────────────────────────────
        trend_stats = self._classify_trend(closes)

        # ── 7. Volume profile at bounces ──────────────────────────────────
        vol_at_bounces = self._volume_at_bounces(closes, volumes, lows)

        # ── 8. Calculate overall bounce score (0-100) ─────────────────────
        bounce_score = self._calculate_bounce_score(
            windows, bounce_stats, spike_stats, reversion_stats,
            trend_stats, vol_at_bounces, dist_to_support
        )

        # ── 9. Entry/exit zones ───────────────────────────────────────────
        entry_exit = self._suggest_entry_exit(
            price, windows, nearest_support, nearest_resistance,
            bounce_stats, spike_stats
        )

        return {
            "ticker":           ticker,
            "price":            round(price, 6),
            "bounce_score":     round(bounce_score, 1),
            "confidence":       round(min(bounce_score / 100, 0.95), 2),
            "windows":          windows,
            "supports":         [round(s, 6) for s in sorted(supports)[-3:]],
            "resistances":      [round(r, 6) for r in sorted(resistances)[:3]],
            "nearest_support":  round(nearest_support, 6) if nearest_support else None,
            "nearest_resistance": round(nearest_resistance, 6) if nearest_resistance else None,
            "dist_to_support_pct":   round(dist_to_support, 3) if dist_to_support else None,
            "dist_to_resistance_pct": round(dist_to_resistance, 3) if dist_to_resistance else None,
            "bounce_stats":     bounce_stats,
            "spike_stats":      spike_stats,
            "reversion_stats":  reversion_stats,
            "trend":            trend_stats,
            "vol_at_bounces":   vol_at_bounces,
            "entry_exit":       entry_exit,
            "analysis_time":    datetime.now(timezone.utc).isoformat(),
        }

    # ── Statistical helpers ──────────────────────────────────────────────────

    def _find_pivots(self, closes, lows, highs, lookback=5):
        """Find local min (support) and max (resistance) using pivot point detection."""
        supports = []
        resistances = []
        n = len(closes)
        for i in range(lookback, n - lookback):
            # Local minimum — support
            if lows[i] == min(lows[i-lookback:i+lookback+1]):
                supports.append(float(lows[i]))
            # Local maximum — resistance
            if highs[i] == max(highs[i-lookback:i+lookback+1]):
                resistances.append(float(highs[i]))

        # Cluster nearby levels (within 0.3% of each other)
        supports    = self._cluster_levels(supports, threshold_pct=0.3)
        resistances = self._cluster_levels(resistances, threshold_pct=0.3)
        return supports, resistances

    @staticmethod
    def _cluster_levels(levels, threshold_pct=0.3):
        """Cluster nearby price levels into single support/resistance zones."""
        if not levels:
            return []
        levels = sorted(levels)
        clusters = []
        current_cluster = [levels[0]]
        for i in range(1, len(levels)):
            if (levels[i] - current_cluster[-1]) / current_cluster[-1] * 100 < threshold_pct:
                current_cluster.append(levels[i])
            else:
                clusters.append(float(np.mean(current_cluster)))
                current_cluster = [levels[i]]
        clusters.append(float(np.mean(current_cluster)))
        return clusters

    def _count_bounces(self, closes, lows, highs):
        """Count how many times price touched the lower zone and bounced back."""
        n = len(closes)
        if n < 30:
            return {"count": 0, "avg_bounce_pct": 0, "avg_bounce_bars": 0}

        mean = float(np.mean(closes[-60:] if n >= 60 else closes))
        std  = float(np.std(closes[-60:] if n >= 60 else closes))
        lower_zone = mean - 1.5 * std  # slightly inside lower band

        bounces = []
        i = 0
        while i < n - 5:
            if lows[i] <= lower_zone:
                # Found a touch — look for bounce
                touch_price = float(lows[i])
                max_after = float(np.max(closes[i:min(i+20, n)]))
                bounce_pct = (max_after - touch_price) / touch_price * 100
                bars_to_max = int(np.argmax(closes[i:min(i+20, n)]))
                if bounce_pct > 0.1:  # minimum 0.1% bounce
                    bounces.append({
                        "touch_price": touch_price,
                        "bounce_pct":  round(bounce_pct, 3),
                        "bars_to_peak": bars_to_max,
                    })
                i += max(bars_to_max, 3)  # skip past this bounce
            else:
                i += 1

        avg_bounce = float(np.mean([b["bounce_pct"] for b in bounces])) if bounces else 0
        avg_bars   = float(np.mean([b["bars_to_peak"] for b in bounces])) if bounces else 0

        return {
            "count":           len(bounces),
            "avg_bounce_pct":  round(avg_bounce, 3),
            "avg_bounce_bars": round(avg_bars, 1),
            "lower_zone":      round(lower_zone, 6),
            "bounces":         bounces[-5:],  # last 5 bounces for display
        }

    def _analyze_spikes(self, closes):
        """Analyze spike magnitude and frequency."""
        n = len(closes)
        if n < 20:
            return {"avg_spike_pct": 0, "spike_freq": 0, "max_spike_pct": 0}

        returns = np.diff(closes) / closes[:-1] * 100
        mean_ret = float(np.mean(returns))
        std_ret  = float(np.std(returns))

        # Spikes = returns > 2 standard deviations
        threshold = abs(mean_ret) + 2 * std_ret
        spikes = [float(r) for r in returns if abs(r) > threshold]

        avg_spike = float(np.mean([abs(s) for s in spikes])) if spikes else 0
        max_spike = float(max([abs(s) for s in spikes])) if spikes else 0
        freq      = len(spikes) / n * 100  # spikes per 100 bars

        return {
            "avg_spike_pct": round(avg_spike, 3),
            "max_spike_pct": round(max_spike, 3),
            "spike_freq":    round(freq, 1),
            "spike_count":   len(spikes),
            "return_std":    round(std_ret, 4),
        }

    def _mean_reversion_speed(self, closes):
        """How fast does price return to the mean after deviating?"""
        n = len(closes)
        if n < 40:
            return {"avg_reversion_bars": 0, "reversion_pct": 0}

        mean = float(np.mean(closes))
        std  = float(np.std(closes))
        if std == 0:
            return {"avg_reversion_bars": 0, "reversion_pct": 0}

        # Find points where price is >1.5σ from mean, measure bars to return within 0.5σ
        reversion_bars = []
        i = 0
        while i < n - 5:
            deviation = (closes[i] - mean) / std
            if abs(deviation) > 1.5:
                # Count bars until price returns within 0.5σ of mean
                for j in range(i + 1, min(i + 30, n)):
                    if abs((closes[j] - mean) / std) < 0.5:
                        reversion_bars.append(j - i)
                        i = j
                        break
                else:
                    i += 1
            else:
                i += 1

        avg_bars = float(np.mean(reversion_bars)) if reversion_bars else 0
        reversion_pct = len(reversion_bars) / max(1, n // 10) * 100  # % of deviations that revert

        return {
            "avg_reversion_bars": round(avg_bars, 1),
            "reversion_count":    len(reversion_bars),
            "reversion_pct":      round(reversion_pct, 1),
        }

    def _classify_trend(self, closes):
        """Is this coin trending or ranging? Ranging = better for bounces."""
        n = len(closes)
        if n < 30:
            return {"type": "unknown", "strength": 0}

        # Linear regression slope
        x = np.arange(n)
        slope, intercept = np.polyfit(x, closes, 1)
        predicted = slope * x + intercept
        residuals = closes - predicted

        # R² — high = trending, low = ranging/noisy
        ss_res = float(np.sum(residuals ** 2))
        ss_tot = float(np.sum((closes - np.mean(closes)) ** 2))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # ADX-like strength
        price_changes = np.diff(closes)
        trend_strength = abs(np.mean(price_changes[-20:])) / np.std(price_changes[-20:]) if np.std(price_changes[-20:]) > 0 else 0

        # Range ratio: how much of the time is price within 1σ of mean?
        mean = np.mean(closes)
        std  = np.std(closes)
        in_range = sum(1 for c in closes if abs(c - mean) < std) / n * 100

        if r_squared > 0.7 and trend_strength > 1.0:
            trend_type = "trending"
        elif r_squared < 0.3 and in_range > 60:
            trend_type = "ranging"  # best for bounce strategy
        else:
            trend_type = "mixed"

        slope_pct = (slope / closes[0] * 100 * n) if closes[0] > 0 else 0

        return {
            "type":           trend_type,
            "r_squared":      round(r_squared, 3),
            "trend_strength": round(float(trend_strength), 2),
            "slope_pct":      round(slope_pct, 3),  # total % change implied by trend
            "in_range_pct":   round(in_range, 1),
            "direction":      "up" if slope > 0 else "down",
        }

    def _volume_at_bounces(self, closes, volumes, lows):
        """Is volume higher at bounce points? That confirms institutional buying."""
        n = len(closes)
        if n < 30:
            return {"vol_surge_at_bounce": False, "avg_bounce_vol_ratio": 1.0}

        mean_price = float(np.mean(closes))
        std_price  = float(np.std(closes))
        lower_zone = mean_price - 1.5 * std_price

        avg_vol = float(np.mean(volumes)) if np.mean(volumes) > 0 else 1.0
        bounce_vols = []

        for i in range(n):
            if lows[i] <= lower_zone:
                bounce_vols.append(float(volumes[i]))

        avg_bounce_vol = float(np.mean(bounce_vols)) if bounce_vols else avg_vol
        ratio = avg_bounce_vol / avg_vol if avg_vol > 0 else 1.0

        return {
            "vol_surge_at_bounce": ratio > 1.5,
            "avg_bounce_vol_ratio": round(ratio, 2),
            "bounce_vol_samples":   len(bounce_vols),
        }

    def _calculate_bounce_score(self, windows, bounce_stats, spike_stats,
                                 reversion_stats, trend_stats, vol_at_bounces,
                                 dist_to_support):
        """
        Composite score 0-100 rating how good this coin is for bounce trading.
        Higher = better bounce opportunity right now.
        """
        score = 0

        # 1. Ranging market = good for bounces (0-20 pts)
        if trend_stats.get("type") == "ranging":
            score += 20
        elif trend_stats.get("type") == "mixed":
            score += 10
        # Trending = bad for bounces

        # 2. Price near lower band = setup forming (0-20 pts)
        w = windows.get("1hr", windows.get("20min", {}))
        band_pos = w.get("band_pos", 0.5)
        if band_pos < 0.15:
            score += 20  # very near lower band
        elif band_pos < 0.30:
            score += 12
        elif band_pos < 0.40:
            score += 5

        # 3. Historical bounce count = proven pattern (0-15 pts)
        bounce_count = bounce_stats.get("count", 0)
        score += min(15, bounce_count * 3)

        # 4. Average bounce size = profit potential (0-15 pts)
        avg_bounce = bounce_stats.get("avg_bounce_pct", 0)
        if avg_bounce > 1.0:
            score += 15
        elif avg_bounce > 0.5:
            score += 10
        elif avg_bounce > 0.2:
            score += 5

        # 5. Mean reversion speed = quick exits (0-10 pts)
        avg_rev = reversion_stats.get("avg_reversion_bars", 99)
        if avg_rev > 0 and avg_rev < 10:
            score += 10
        elif avg_rev < 20:
            score += 5

        # 6. Volume confirmation at bounces (0-10 pts)
        if vol_at_bounces.get("vol_surge_at_bounce"):
            score += 10
        elif vol_at_bounces.get("avg_bounce_vol_ratio", 1) > 1.2:
            score += 5

        # 7. Close to support = immediate opportunity (0-10 pts)
        if dist_to_support is not None:
            if dist_to_support < 0.3:
                score += 10  # very close to support
            elif dist_to_support < 0.8:
                score += 5

        return min(100, score)

    def _suggest_entry_exit(self, price, windows, nearest_support,
                            nearest_resistance, bounce_stats, spike_stats):
        """Calculate mathematical entry/exit zones based on analysis."""
        w = windows.get("1hr", windows.get("20min", {}))
        mean  = w.get("mean", price)
        lower = w.get("lower", price * 0.99)
        upper = w.get("upper", price * 1.01)
        std   = w.get("std", price * 0.005)

        avg_bounce = bounce_stats.get("avg_bounce_pct", 0.3)

        # Entry zone: between lower band and lower band - 0.5σ
        entry_ideal = lower
        entry_limit = lower - 0.5 * std  # max dip before it's a breakdown

        # Stop: below entry limit (breakdown = exit)
        stop = entry_limit - 0.3 * std

        # Target: mean (conservative) or upper band (aggressive)
        target_conservative = mean
        target_aggressive   = min(upper, mean + 1.5 * std)

        # Risk/Reward
        risk   = abs(entry_ideal - stop) if entry_ideal > stop else price * 0.005
        reward = abs(target_conservative - entry_ideal) if target_conservative > entry_ideal else price * 0.003
        rr     = reward / risk if risk > 0 else 0

        return {
            "entry_zone": {
                "ideal":  round(entry_ideal, 6),
                "limit":  round(entry_limit, 6),
                "current_price": round(price, 6),
                "dist_to_entry_pct": round((price - entry_ideal) / price * 100, 3),
            },
            "stop":              round(stop, 6),
            "target_conservative": round(target_conservative, 6),
            "target_aggressive":  round(target_aggressive, 6),
            "risk_reward":        round(rr, 2),
            "est_profit_pct":     round(avg_bounce, 3),
            "est_hold_bars":      round(bounce_stats.get("avg_bounce_bars", 10), 0),
        }

    # ── LLM Integration ──────────────────────────────────────────────────────

    async def _get_llm_recommendations(self, analyses: dict) -> dict:
        """Ask GPT-4 to evaluate bounce setups and recommend entry/exit."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return {t: {"action": "NO_LLM", "note": "OpenAI key not configured"}
                    for t in analyses}

        # Build a concise brief for the LLM
        brief_lines = []
        for ticker, a in analyses.items():
            trend = a.get("trend", {})
            bounce = a.get("bounce_stats", {})
            entry = a.get("entry_exit", {})
            w = a.get("windows", {}).get("1hr", {})
            brief_lines.append(
                f"{ticker}: ${a['price']:.4f} | "
                f"bounce_score={a['bounce_score']:.0f}/100 | "
                f"trend={trend.get('type','?')} r²={trend.get('r_squared',0):.2f} | "
                f"bounces={bounce.get('count',0)} avg_bounce={bounce.get('avg_bounce_pct',0):.2f}% | "
                f"band_pos={w.get('band_pos',0.5):.2f} vol%={w.get('vol_pct',0):.2f}% | "
                f"R:R={entry.get('risk_reward',0):.1f} | "
                f"support=${a.get('nearest_support','?')} resistance=${a.get('nearest_resistance','?')}"
            )

        prompt = f"""You are a crypto scalping analyst. Analyze these coins for BOUNCE/MEAN-REVERSION setups.
For each coin, recommend: BUY_BOUNCE, WAIT, or SKIP.

Current data (1-minute bars, last 5 hours):
{chr(10).join(brief_lines)}

For each coin respond in this exact format (one line per coin):
TICKER|ACTION|CONFIDENCE|ENTRY|STOP|TARGET|REASONING

Rules:
- Only recommend BUY_BOUNCE if bounce_score >= 50 AND trend is ranging/mixed
- CONFIDENCE must be 0.0-1.0 (only >= 0.65 is tradeable)
- ENTRY/STOP/TARGET are price levels
- Keep REASONING under 20 words
- If no good setup, say WAIT or SKIP with reason"""

        try:
            import httpx
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 500,
                    },
                )
                if resp.status_code != 200:
                    logger.warning(f"LLM bounce analysis: HTTP {resp.status_code}")
                    return {}

                text = resp.json()["choices"][0]["message"]["content"].strip()
                return self._parse_llm_response(text)

        except Exception as e:
            logger.error(f"LLM bounce analysis error: {e}")
            return {}

    @staticmethod
    def _parse_llm_response(text: str) -> dict:
        """Parse LLM response into structured recommendations."""
        recs = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4:
                continue
            ticker = parts[0].upper().replace("/USD", "").replace("USD", "")
            try:
                recs[ticker] = {
                    "action":     parts[1],
                    "confidence": float(parts[2]) if len(parts) > 2 else 0,
                    "entry":      parts[3] if len(parts) > 3 else None,
                    "stop":       parts[4] if len(parts) > 4 else None,
                    "target":     parts[5] if len(parts) > 5 else None,
                    "reasoning":  parts[6] if len(parts) > 6 else "",
                }
            except (ValueError, IndexError):
                recs[ticker] = {"action": parts[1] if len(parts) > 1 else "SKIP",
                                "reasoning": " ".join(parts[2:])}
        return recs

    def get_last_analysis(self) -> dict:
        """Return cached last analysis."""
        return self._last_analysis
