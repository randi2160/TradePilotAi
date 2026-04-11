"""
IPO Intelligence Service
- Fetches upcoming IPO calendar
- Tracks pre-IPO companies by name (no symbol yet)
- Monitors news for IPO-related stories
- Alerts when a tracked company gets a symbol
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Companies everyone is watching for IPO
WATCHED_PRE_IPO = [
    {"name": "OpenAI",        "sector": "AI/Tech",    "notes": "ChatGPT maker, rumored 2025-2026"},
    {"name": "Anthropic",     "sector": "AI/Tech",    "notes": "Claude AI maker, Series E funded"},
    {"name": "Starlink",      "sector": "Space/Tech", "notes": "SpaceX satellite internet division"},
    {"name": "Stripe",        "sector": "Fintech",    "notes": "Payments giant, multiple delay"},
    {"name": "Databricks",    "sector": "AI/Data",    "notes": "Data + AI platform"},
    {"name": "Klarna",        "sector": "Fintech",    "notes": "BNPL leader, filed S-1 2024"},
    {"name": "Discord",       "sector": "Social",     "notes": "Gaming/community platform"},
    {"name": "Reddit",        "sector": "Social",     "notes": "Listed March 2024 as RDDT"},
    {"name": "xAI",           "sector": "AI/Tech",    "notes": "Elon Musk's Grok AI"},
    {"name": "Shein",         "sector": "Retail",     "notes": "Fast fashion giant"},
]


class IPOService:
    def __init__(self):
        self._ipo_calendar: list = []
        self._ipo_news:     list = []
        self._last_fetch:   float = 0
        self._cache_mins:   int   = 60

    async def get_ipo_calendar(self) -> dict:
        """Get upcoming + recent IPOs from multiple sources."""
        import time
        now = time.time()
        if now - self._last_fetch < self._cache_mins * 60 and self._ipo_calendar:
            return self._build_response()

        await asyncio.gather(
            self._fetch_fmp_calendar(),
            self._fetch_nasdaq_calendar(),
            return_exceptions=True,
        )
        self._last_fetch = now
        return self._build_response()

    async def _fetch_fmp_calendar(self):
        """Financial Modeling Prep IPO calendar (free tier)."""
        try:
            today = datetime.now()
            from_d = today.strftime("%Y-%m-%d")
            to_d   = (today + timedelta(days=90)).strftime("%Y-%m-%d")

            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://financialmodelingprep.com/api/v3/ipo_calendar",
                    params={
                        "from":   from_d,
                        "to":     to_d,
                        "apikey": "demo",  # free demo key for basic data
                    }
                )
                if r.status_code == 200:
                    data = r.json()
                    for item in (data if isinstance(data, list) else []):
                        self._add_ipo({
                            "name":        item.get("company", ""),
                            "symbol":      item.get("symbol", ""),
                            "date":        item.get("date", ""),
                            "exchange":    item.get("exchange", ""),
                            "price_low":   item.get("priceRange", "").split("-")[0].strip() if "-" in str(item.get("priceRange", "")) else "",
                            "price_high":  item.get("priceRange", "").split("-")[-1].strip() if "-" in str(item.get("priceRange", "")) else "",
                            "shares":      item.get("shares", 0),
                            "source":      "fmp",
                        })
        except Exception as e:
            logger.debug(f"FMP IPO calendar: {e}")

    async def _fetch_nasdaq_calendar(self):
        """Nasdaq IPO calendar."""
        try:
            async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
                r = await client.get(
                    "https://api.nasdaq.com/api/ipo/alldata",
                    params={"type": "upcoming", "market": "nasdaq|nyse|amex"},
                )
                if r.status_code == 200:
                    data = r.json()
                    rows = data.get("data", {}).get("upcoming", {}).get("upcomingTable", {}).get("rows", [])
                    for row in rows[:20]:
                        self._add_ipo({
                            "name":     row.get("companyName", ""),
                            "symbol":   row.get("proposedTickerSymbol", ""),
                            "date":     row.get("expectedIpoDate", ""),
                            "exchange": row.get("exchange", ""),
                            "price_low":  row.get("proposedSharePrice", ""),
                            "price_high": "",
                            "source":   "nasdaq",
                        })
        except Exception as e:
            logger.debug(f"Nasdaq IPO: {e}")

    def _add_ipo(self, item: dict):
        """Add IPO to list, avoiding duplicates."""
        name = item.get("name", "").lower()
        sym  = item.get("symbol", "").upper()

        # Check if already in list
        for existing in self._ipo_calendar:
            if (sym and existing.get("symbol") == sym) or \
               (name and existing.get("name", "").lower() == name):
                # Update with new info
                existing.update({k: v for k, v in item.items() if v})
                return

        # Calculate days until IPO
        date_str = item.get("date", "")
        days_until = None
        is_past    = False
        try:
            ipo_date   = datetime.strptime(date_str, "%Y-%m-%d")
            days_until = (ipo_date - datetime.now()).days
            is_past    = days_until < 0
        except Exception:
            pass

        self._ipo_calendar.append({
            **item,
            "days_until": days_until,
            "is_past":    is_past,
            "hype_score": self._get_hype_score(item.get("name", "")),
        })

    def _get_hype_score(self, name: str) -> int:
        """Simple hype scoring based on known companies."""
        high_hype = ["openai", "anthropic", "starlink", "spacex", "stripe", "databricks"]
        med_hype  = ["klarna", "shein", "discord", "reddit", "instacart"]
        lower     = name.lower()
        if any(h in lower for h in high_hype): return 5
        if any(m in lower for m in med_hype):  return 3
        return 1

    def _build_response(self) -> dict:
        now   = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # Sort by date
        cal = sorted(self._ipo_calendar, key=lambda x: x.get("date", "") or "9999")

        upcoming = [i for i in cal if not i.get("is_past") and i.get("date")]
        recent   = [i for i in cal if i.get("is_past")][-10:]

        return {
            "upcoming":     upcoming[:20],
            "recent":       recent,
            "pre_ipo":      WATCHED_PRE_IPO,
            "total_upcoming": len(upcoming),
            "fetched_at":   now.isoformat(),
        }

    async def get_ipo_news(self, alpaca_key: str = "", alpaca_secret: str = "") -> list:
        """Fetch IPO-related news."""
        news = []
        keywords = ["IPO", "initial public offering", "OpenAI IPO", "Anthropic IPO",
                    "S-1 filing", "going public", "Starlink IPO", "Stripe IPO"]

        if not alpaca_key:
            alpaca_key    = os.getenv("ALPACA_API_KEY", "")
            alpaca_secret = os.getenv("ALPACA_SECRET_KEY", "")

        if not alpaca_key:
            return self._get_mock_news()

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://data.alpaca.markets/v1beta1/news",
                    headers={
                        "APCA-API-KEY-ID":     alpaca_key,
                        "APCA-API-SECRET-KEY": alpaca_secret,
                    },
                    params={
                        "limit": 20,
                        "sort":  "desc",
                        "keywords": "IPO",
                    }
                )
                if r.status_code == 200:
                    articles = r.json().get("news", [])
                    for a in articles:
                        news.append({
                            "title":      a.get("headline", ""),
                            "summary":    a.get("summary", ""),
                            "source":     a.get("source", ""),
                            "url":        a.get("url", ""),
                            "published":  a.get("created_at", ""),
                            "symbols":    a.get("symbols", []),
                        })
        except Exception as e:
            logger.debug(f"IPO news fetch: {e}")
            return self._get_mock_news()

        return news if news else self._get_mock_news()

    def _get_mock_news(self) -> list:
        """Return placeholder news when API unavailable."""
        return [
            {
                "title":   "OpenAI Considering IPO as Valuation Hits $157 Billion",
                "summary": "OpenAI is reportedly exploring an IPO following its latest funding round. CEO Sam Altman has not confirmed a timeline.",
                "source":  "Reuters",
                "url":     "https://reuters.com",
                "published": datetime.now().isoformat(),
                "symbols": [],
            },
            {
                "title":   "Anthropic Raises $4B from Google, IPO Speculation Grows",
                "summary": "Claude maker Anthropic has raised significant capital. Analysts speculate a 2026 IPO is possible.",
                "source":  "Bloomberg",
                "url":     "https://bloomberg.com",
                "published": datetime.now().isoformat(),
                "symbols": [],
            },
            {
                "title":   "SpaceX Starlink IPO Could Value Division at $150B",
                "summary": "Elon Musk has hinted at a potential Starlink IPO. The satellite internet business is profitable and growing.",
                "source":  "WSJ",
                "url":     "https://wsj.com",
                "published": datetime.now().isoformat(),
                "symbols": [],
            },
        ]

    async def check_symbol_available(self, company_name: str, alpaca_key: str = "") -> Optional[str]:
        """Check if a pre-IPO company has gotten a ticker symbol."""
        if not alpaca_key:
            alpaca_key    = os.getenv("ALPACA_API_KEY", "")
            alpaca_secret = os.getenv("ALPACA_SECRET_KEY", "")
        else:
            alpaca_secret = os.getenv("ALPACA_SECRET_KEY", "")

        # Common name → expected symbol mappings
        expected = {
            "openai":     ["OAIX", "OPAI"],
            "anthropic":  ["ANTH", "CLAI"],
            "starlink":   ["STLK", "SLNK"],
            "stripe":     ["STRP", "STRI"],
            "databricks": ["DBRK"],
            "klarna":     ["KLAR"],
        }

        name_lower = company_name.lower()
        candidates = []
        for key, syms in expected.items():
            if key in name_lower:
                candidates.extend(syms)

        if not candidates or not alpaca_key:
            return None

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                for sym in candidates:
                    r = await client.get(
                        f"https://data.alpaca.markets/v2/stocks/snapshots",
                        headers={
                            "APCA-API-KEY-ID":     alpaca_key,
                            "APCA-API-SECRET-KEY": alpaca_secret,
                        },
                        params={"symbols": sym, "feed": "iex"},
                    )
                    if r.status_code == 200 and sym in r.json():
                        logger.info(f"🎉 {company_name} now has symbol {sym}!")
                        return sym
        except Exception:
            pass

        return None
