"""
Dynamic Watchlist Builder v2
When dynamic mode is ON:
  1. Pulls TOP GAINERS + MOST ACTIVE from Alpaca market scanner (live)
  2. Scores each by momentum, volume, sentiment, technical setup
  3. Returns the TRUE best movers of TODAY — not a hardcoded list
  4. Refreshes every 30 minutes during market hours
  5. User's manually added symbols are ALWAYS included
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import pytz

import config

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


class DynamicWatchlistBuilder:
    def __init__(self):
        self._dynamic_list:  list  = []
        self._scores:        dict  = {}
        self._last_built:    str   = ""
        self._last_built_ts: float = 0
        self._is_dynamic:    bool  = False
        self._manual_list:   list  = list(config.DEFAULT_WATCHLIST)
        self._refresh_mins:  int   = 30   # rebuild every 30 minutes

    def set_mode(self, dynamic: bool):
        self._is_dynamic = dynamic
        if dynamic:
            self._last_built_ts = 0   # force rebuild on next call
        logger.info(f"Watchlist mode: {'DYNAMIC (live market movers)' if dynamic else 'MANUAL'}")

    def set_manual_list(self, symbols: list):
        self._manual_list = [s.upper() for s in symbols if s.strip()]

    def get_active_list(self) -> list:
        """Return the active watchlist — dynamic or manual."""
        if self._is_dynamic and self._dynamic_list:
            # Always include manual symbols too
            combined = list(dict.fromkeys(self._dynamic_list + self._manual_list))
            return combined[:25]
        return self._manual_list

    def needs_rebuild(self) -> bool:
        """True if dynamic list should be rebuilt."""
        if not self._is_dynamic:
            return False
        if not self._dynamic_list:
            return True
        elapsed = (datetime.now().timestamp() - self._last_built_ts) / 60
        return elapsed >= self._refresh_mins

    async def build(
        self,
        market_scan:    dict,
        news_sentiment: dict,
        signals:        list,
    ) -> list:
        """
        Build watchlist from LIVE market data.
        Scores stocks across: momentum, volume, sentiment, technical.
        """
        logger.info("Building dynamic watchlist from live market data...")

        gainers  = market_scan.get("gainers",      [])
        actives  = market_scan.get("most_active",  [])
        losers   = market_scan.get("losers",       [])

        if not gainers and not actives:
            logger.warning("No market scan data — falling back to manual list")
            self._dynamic_list = list(self._manual_list)
            return self._dynamic_list

        # Build candidate universe from live market data
        candidate_map = {}

        for g in gainers:
            sym = g.get("symbol", "")
            if not sym or len(sym) > 5:
                continue
            candidate_map[sym] = {
                "symbol":     sym,
                "price":      g.get("price", 0),
                "change_pct": g.get("change_pct", 0),
                "volume":     g.get("volume", 0),
                "high":       g.get("high", 0),
                "low":        g.get("low", 0),
                "source":     "gainer",
                "score":      0.0,
                "flags":      [],
            }

        for a in actives:
            sym = a.get("symbol", "")
            if not sym or len(sym) > 5:
                continue
            if sym not in candidate_map:
                candidate_map[sym] = {
                    "symbol":     sym,
                    "price":      a.get("price", 0),
                    "change_pct": a.get("change_pct", 0),
                    "volume":     a.get("volume", 0),
                    "source":     "active",
                    "score":      0.0,
                    "flags":      [],
                }
            else:
                candidate_map[sym]["source"] = "gainer+active"

        # Always add manual symbols to candidates
        for sym in self._manual_list:
            if sym not in candidate_map:
                candidate_map[sym] = {
                    "symbol": sym, "price": 0, "change_pct": 0,
                    "volume": 0, "source": "manual", "score": 0.0, "flags": ["👤 Manual"],
                }

        signal_map = {s.get("symbol"): s for s in (signals or [])}

        # Score each candidate
        for sym, data in candidate_map.items():
            score  = 0.0
            flags  = list(data.get("flags", []))
            pct    = data.get("change_pct", 0)
            vol    = data.get("volume", 0)
            price  = data.get("price", 0)
            source = data.get("source", "")

            # 1. Price change momentum (sweet spot: +2% to +15%)
            if 2.0 <= pct <= 15.0:
                score += min(pct * 2.5, 35)
                flags.append(f"🔥 +{pct:.1f}% gainer")
            elif pct > 15.0:
                score += 15  # overextended — still interesting but less
                flags.append(f"⚡ +{pct:.1f}% extended")
            elif -8.0 <= pct <= -2.0:
                score += 10  # potential reversal
                flags.append(f"↩️ {pct:.1f}% reversal watch")

            # 2. Volume (favor liquid stocks)
            if vol > 5_000_000:
                score += 20
                flags.append(f"📊 {vol/1e6:.0f}M vol")
            elif vol > 1_000_000:
                score += 12
            elif vol < 200_000:
                score -= 20  # too illiquid
                flags.append("⚠️ Low volume")

            # 3. Price filter (avoid penny stocks and very expensive stocks)
            if price < 1.0:
                score -= 30
                flags.append("❌ Penny stock")
            elif price > 2000:
                score -= 10  # hard to size with $5K capital

            # 4. News sentiment boost
            sent = news_sentiment.get(sym, {})
            sent_score = sent.get("score", 0)
            articles   = sent.get("articles", 0)
            if sent_score > 0.3 and articles >= 2:
                score += 20
                flags.append(f"📰 Bullish news ({sent_score:+.2f})")
            elif sent_score > 0.1:
                score += 8
            elif sent_score < -0.3 and articles >= 2:
                score -= 15
                flags.append("📰 Bearish news")

            # 5. Technical signal boost
            sig = signal_map.get(sym, {})
            if sig:
                conf = sig.get("confidence", 0)
                if sig.get("signal") in ("BUY", "SELL") and conf >= 0.55:
                    score += conf * 25
                    flags.append(f"🤖 {sig['signal']} signal {conf:.0%}")
                vol_ratio = sig.get("volume_ratio", 1.0)
                if vol_ratio > 2.5:
                    score += 10
                    flags.append(f"⚡ Vol {vol_ratio:.1f}× surge")

            # 6. Source bonus (already in top gainers AND most active = very interesting)
            if "gainer+active" in source:
                score += 15
                flags.append("🌟 Top gainer + most active")

            # 7. Manual symbol bonus (always prioritize user's choices)
            if "manual" in source:
                score += 30
                flags.append("👤 User watchlist")

            data["score"] = round(score, 1)
            data["flags"] = flags

        # Sort by score
        ranked = sorted(
            [v for v in candidate_map.values() if v["score"] > -10],
            key=lambda x: x["score"],
            reverse=True,
        )

        # Pick top 15, always keep manual symbols
        top_syms    = [d["symbol"] for d in ranked[:15]]
        manual_syms = [s for s in self._manual_list if s not in top_syms]
        final       = list(dict.fromkeys(top_syms + manual_syms))[:20]

        self._dynamic_list  = final
        self._scores        = {d["symbol"]: d for d in ranked}
        self._last_built    = datetime.now(ET).strftime("%I:%M %p ET")
        self._last_built_ts = datetime.now().timestamp()

        logger.info(
            f"Dynamic watchlist: {final[:10]}... "
            f"({len(final)} total, {len(gainers)} gainers + {len(actives)} actives scanned)"
        )
        return final

    def get_scores(self) -> dict:
        return {
            "watchlist":   self._dynamic_list,
            "scores":      {k: {
                "score":      v.get("score", 0),
                "change_pct": v.get("change_pct", 0),
                "volume":     v.get("volume", 0),
                "flags":      v.get("flags", []),
                "source":     v.get("source", ""),
            } for k, v in self._scores.items()},
            "built_at":    self._last_built,
            "is_dynamic":  self._is_dynamic,
            "manual_list": self._manual_list,
            "total_scanned": len(self._scores),
        }
