"""
Market Scanner v3 — uses Alpaca snapshots (which works) instead of
the broken screener endpoint to find true top movers of the day.

Strategy: scan a broad universe of 100+ stocks, find the real movers.
"""
import asyncio
import logging
import time
from typing import Optional

import httpx
import config

logger = logging.getLogger(__name__)

# Broad scan universe — S&P 500 sample + popular momentum stocks
BROAD_UNIVERSE = [
    # Mega cap tech
    "AAPL","MSFT","NVDA","META","GOOGL","AMZN","TSLA","AMD","AVGO","INTC",
    # High momentum / retail favorites
    "COIN","MSTR","PLTR","SOFI","HOOD","RBLX","UPST","DKNG","RIVN","LCID",
    # ETFs
    "SPY","QQQ","IWM","TQQQ","SQQQ","UVXY","SPXL",
    # Finance
    "JPM","GS","BAC","MS","C","WFC","V","MA",
    # Healthcare/biotech
    "UNH","JNJ","PFE","MRNA","ABBV","LLY","GILD",
    # Consumer
    "NFLX","DIS","SBUX","MCD","NKE","COST","WMT","TGT",
    # Energy
    "XOM","CVX","OXY","SLB","BP",
    # Other momentum
    "SNOW","CRWD","ZS","PANW","NET","DDOG","MDB","ABNB","UBER","LYFT",
    "ARM","SMCI","DELL","HPQ","IBM","ORCL","SAP","ADBE","CRM","NOW",
    "ROKU","SNAP","PINS","MTCH","SPOT","TTD","TRADE","SE","MELI",
    # Popular options stocks
    "GME","AMC","BBBY","CLOV","WKHS","XPEV","NIO","LI","BABA","JD",
]
BROAD_UNIVERSE = list(dict.fromkeys(BROAD_UNIVERSE))  # dedupe


class MarketScanner:
    def __init__(self):
        self._gainers:     list  = []
        self._losers:      list  = []
        self._most_active: list  = []
        self._all_snaps:   dict  = {}
        self._last_scan:   float = 0
        self._cache_secs:  int   = 60   # cache 1 minute

    async def scan(self) -> dict:
        """Scan broad universe for top movers using snapshots endpoint."""
        now = time.time()
        if now - self._last_scan < self._cache_secs and self._gainers:
            return self._result()

        try:
            snaps = await self._fetch_snapshots(BROAD_UNIVERSE)
            if not snaps:
                logger.warning("No snapshot data returned")
                return self._result()

            scored = []
            for sym, data in snaps.items():
                try:
                    dp  = data.get("dailyBar", {})
                    lp  = data.get("latestTrade", {})
                    lq  = data.get("latestQuote", {})
                    prev = data.get("prevDailyBar", {})

                    price  = float(lp.get("p", dp.get("c", 0)))
                    prev_c = float(prev.get("c", price))
                    vol    = int(dp.get("v", 0))
                    high   = float(dp.get("h", price))
                    low    = float(dp.get("l", price))

                    if price <= 0 or prev_c <= 0:
                        continue

                    chg_pct = (price - prev_c) / prev_c * 100

                    scored.append({
                        "symbol":     sym,
                        "price":      round(price, 2),
                        "change_pct": round(chg_pct, 2),
                        "volume":     vol,
                        "high":       round(high, 2),
                        "low":        round(low, 2),
                        "prev_close": round(prev_c, 2),
                        "dollar_vol": round(price * vol, 0),
                    })
                except Exception:
                    continue

            if not scored:
                return self._result()

            # Sort by different criteria
            gainers     = sorted([s for s in scored if s["change_pct"] > 0],
                                  key=lambda x: x["change_pct"], reverse=True)
            losers      = sorted([s for s in scored if s["change_pct"] < 0],
                                  key=lambda x: x["change_pct"])
            most_active = sorted(scored, key=lambda x: x["volume"], reverse=True)

            self._gainers     = gainers[:20]
            self._losers      = losers[:10]
            self._most_active = most_active[:20]
            self._all_snaps   = {s["symbol"]: s for s in scored}
            self._last_scan   = now

            logger.info(
                f"Market scan: {len(self._gainers)} gainers, "
                f"{len(self._losers)} losers, "
                f"top gainer: {gainers[0]['symbol']} +{gainers[0]['change_pct']:.1f}%"
                if gainers else "Market scan: no movers"
            )

        except Exception as e:
            logger.error(f"MarketScanner.scan: {e}")

        return self._result()

    async def get_live_prices(self, symbols: list) -> dict:
        """Get current prices for a list of symbols — for live ticker."""
        if not symbols:
            return {}
        try:
            snaps = await self._fetch_snapshots(symbols)
            result = {}
            for sym, data in snaps.items():
                try:
                    lp   = data.get("latestTrade", {})
                    dp   = data.get("dailyBar", {})
                    prev = data.get("prevDailyBar", {})
                    price    = float(lp.get("p", dp.get("c", 0)))
                    prev_c   = float(prev.get("c", price))
                    chg_pct  = (price - prev_c) / prev_c * 100 if prev_c > 0 else 0
                    result[sym] = {
                        "price":      round(price, 2),
                        "change_pct": round(chg_pct, 2),
                        "change_$":   round(price - prev_c, 2),
                        "volume":     int(dp.get("v", 0)),
                        "high":       round(float(dp.get("h", price)), 2),
                        "low":        round(float(dp.get("l", price)), 2),
                    }
                except Exception:
                    pass
            return result
        except Exception as e:
            logger.error(f"get_live_prices: {e}")
            return {}

    async def _fetch_snapshots(self, symbols: list) -> dict:
        """Fetch Alpaca snapshots for a list of symbols in batches of 50."""
        headers = {
            "APCA-API-KEY-ID":     config.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
        }
        all_data = {}
        batches  = [symbols[i:i+50] for i in range(0, len(symbols), 50)]

        async with httpx.AsyncClient(timeout=15) as client:
            for batch in batches:
                try:
                    r = await client.get(
                        "https://data.alpaca.markets/v2/stocks/snapshots",
                        headers=headers,
                        params={"symbols": ",".join(batch), "feed": "iex"},
                    )
                    if r.status_code == 200:
                        all_data.update(r.json())
                    else:
                        logger.warning(f"Snapshot batch returned {r.status_code}")
                except Exception as e:
                    logger.error(f"Snapshot batch error: {e}")

        return all_data

    def _result(self) -> dict:
        return {
            "gainers":     self._gainers,
            "losers":      self._losers,
            "most_active": self._most_active,
            "total_scanned": len(self._all_snaps),
        }

    def get_top_gainers(self, n=10) -> list: return self._gainers[:n]
    def get_top_losers(self, n=10)  -> list: return self._losers[:n]
    def get_most_active(self, n=10) -> list: return self._most_active[:n]
    def get_snapshot(self, sym: str) -> dict: return self._all_snaps.get(sym, {})
