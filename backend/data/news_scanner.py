"""
News sentiment scanner — fetches real market news via Alpaca News API
and scores each headline using keyword-weighted sentiment analysis.
Falls back to zero-score gracefully if API is unavailable.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import httpx

import config

logger = logging.getLogger(__name__)

# ── Sentiment keyword banks ───────────────────────────────────────────────────
BULLISH_WORDS = {
    # Strong positive (weight 1.0)
    "beats":1.0,"beat":1.0,"record":1.0,"surge":1.0,"soars":1.0,"breakout":1.0,
    "upgraded":1.0,"buy":1.0,"outperform":1.0,"bullish":1.0,"rally":1.0,
    "breakthrough":1.0,"acquisition":1.0,"partnership":1.0,"profit":0.9,
    # Medium positive (weight 0.6)
    "growth":0.6,"expands":0.6,"rises":0.6,"gains":0.6,"positive":0.6,
    "strong":0.6,"higher":0.6,"increase":0.6,"optimistic":0.6,"opportunity":0.6,
    "launches":0.6,"innovative":0.6,"revenue":0.5,"demand":0.5,
    # Mild positive (weight 0.3)
    "stable":0.3,"steady":0.3,"recovers":0.3,"rebounds":0.3,"improves":0.3,
}

BEARISH_WORDS = {
    # Strong negative (weight 1.0)
    "misses":1.0,"miss":1.0,"crash":1.0,"plunge":1.0,"downgrade":1.0,
    "sell":1.0,"underperform":1.0,"bearish":1.0,"collapse":1.0,"fraud":1.0,
    "lawsuit":1.0,"bankruptcy":1.0,"recall":1.0,"scandal":1.0,"default":1.0,
    # Medium negative (weight 0.6)
    "falls":0.6,"drops":0.6,"decline":0.6,"loss":0.6,"cuts":0.6,
    "warning":0.6,"risk":0.6,"concern":0.6,"disappoints":0.6,"weak":0.6,
    "layoffs":0.6,"slowdown":0.6,"debt":0.5,"inflation":0.5,
    # Mild negative (weight 0.3)
    "cautious":0.3,"uncertainty":0.3,"challenges":0.3,"pressure":0.3,
}


class NewsScanner:
    def __init__(self):
        self._cache: dict[str, list] = {}          # symbol → list of scored articles
        self._global_cache: list     = []           # market-wide news
        self._last_fetch: dict       = {}
        self._cache_ttl              = 300          # seconds

        self._base_url = "https://data.alpaca.markets/v1beta1/news"
        self._headers  = {
            "APCA-API-KEY-ID":     config.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
        }

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_symbol_news(self, symbol: str, limit: int = 10) -> list:
        """Fetch and score news for a single symbol."""
        now = datetime.now().timestamp()
        if symbol in self._cache and (now - self._last_fetch.get(symbol, 0)) < self._cache_ttl:
            return self._cache[symbol]

        articles = await self._fetch(symbol, limit)
        scored   = [self._score(a) for a in articles]
        self._cache[symbol]       = scored
        self._last_fetch[symbol]  = now
        return scored

    async def get_market_news(self, limit: int = 20) -> list:
        """Fetch broad market / SPY news."""
        now = datetime.now().timestamp()
        if self._global_cache and (now - self._last_fetch.get("_global", 0)) < self._cache_ttl:
            return self._global_cache

        articles = await self._fetch(None, limit)
        scored   = [self._score(a) for a in articles]
        self._global_cache          = scored
        self._last_fetch["_global"] = now
        return scored

    async def get_sentiment_signal(self, symbol: str) -> dict:
        """
        Returns aggregated sentiment score for a symbol:
          score  > +0.2  → bullish
          score  < -0.2  → bearish
          else          → neutral
        """
        articles = await self.get_symbol_news(symbol, limit=5)
        if not articles:
            return {"symbol": symbol, "sentiment": "neutral", "score": 0.0, "articles": 0}

        avg   = sum(a["score"] for a in articles) / len(articles)
        label = "bullish" if avg > 0.2 else "bearish" if avg < -0.2 else "neutral"
        return {
            "symbol":    symbol,
            "sentiment": label,
            "score":     round(avg, 3),
            "articles":  len(articles),
            "headlines": [a["headline"] for a in articles[:3]],
        }

    async def scan_watchlist(self, symbols: list) -> dict:
        """Return sentiment map for all symbols in watchlist."""
        tasks   = [self.get_sentiment_signal(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out     = {}
        for sym, res in zip(symbols, results):
            if isinstance(res, Exception):
                out[sym] = {"symbol": sym, "sentiment": "neutral", "score": 0.0}
            else:
                out[sym] = res
        return out

    # ── Fetch ─────────────────────────────────────────────────────────────────

    async def _fetch(self, symbol: Optional[str], limit: int) -> list:
        params = {
            "limit":  limit,
            "sort":   "desc",
            "start":  (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        }
        if symbol:
            params["symbols"] = symbol

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self._base_url, headers=self._headers, params=params)
                if resp.status_code != 200:
                    logger.warning(f"News API {resp.status_code}: {resp.text[:200]}")
                    return []
                data = resp.json()
                return data.get("news", [])
        except Exception as e:
            logger.warning(f"News fetch error: {e}")
            return []

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score(self, article: dict) -> dict:
        headline = (article.get("headline") or "").lower()
        summary  = (article.get("summary")  or "").lower()
        text     = f"{headline} {summary}"
        words    = text.split()

        bull = sum(BULLISH_WORDS.get(w, 0) for w in words)
        bear = sum(BEARISH_WORDS.get(w, 0) for w in words)

        raw_score = (bull - bear) / max(len(words) / 10, 1)
        score     = max(-1.0, min(1.0, raw_score))

        return {
            "headline":  article.get("headline", ""),
            "summary":   (article.get("summary") or "")[:200],
            "url":       article.get("url", ""),
            "source":    article.get("source", ""),
            "symbols":   article.get("symbols", []),
            "score":     round(score, 3),
            "sentiment": "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral",
            "published": article.get("created_at", ""),
        }
