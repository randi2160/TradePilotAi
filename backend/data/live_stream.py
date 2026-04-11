"""
Live data stream — connects to Alpaca's WebSocket feed and streams
real-time trades, quotes, and bars for all watched symbols.
Maintains a rolling in-memory snapshot of latest prices and 1-min bars.
"""
import asyncio
import json
import logging
import os
from collections import defaultdict, deque
from datetime import datetime
from typing import Callable, Optional

import websockets
import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

PAPER_WS  = "wss://stream.paper-api.alpaca.markets/v2/iex"
LIVE_WS   = "wss://stream.data.alpaca.markets/v2/iex"


class LiveDataStream:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.api_key    = api_key
        self.secret_key = secret_key
        self.url        = PAPER_WS if paper else LIVE_WS

        # Latest data per symbol
        self._prices:   dict[str, float]        = {}   # latest trade price
        self._quotes:   dict[str, dict]         = {}   # latest bid/ask
        self._bars:     dict[str, deque]        = defaultdict(lambda: deque(maxlen=30))  # rolling 1-min bars
        self._changes:  dict[str, float]        = {}   # % change from prev close
        self._volumes:  dict[str, int]          = defaultdict(int)

        self._subscribed: set[str]              = set()
        self._callbacks:  list[Callable]        = []   # called on every price update
        self._ws:         Optional[object]      = None
        self._running:    bool                  = False
        self._task:       Optional[asyncio.Task] = None

    # ── Public control ────────────────────────────────────────────────────────

    async def start(self, symbols: list[str]):
        if self._running:
            await self.update_symbols(symbols)
            return
        self._subscribed = set(s.upper() for s in symbols)
        self._running    = True
        self._task       = asyncio.create_task(self._connect_loop())
        logger.info(f"LiveDataStream starting — {len(self._subscribed)} symbols")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def update_symbols(self, symbols: list[str]):
        """Add/remove symbols while stream is running."""
        new_set = set(s.upper() for s in symbols)
        add     = new_set - self._subscribed
        remove  = self._subscribed - new_set
        self._subscribed = new_set

        if self._ws and (add or remove):
            if add:
                await self._ws.send(json.dumps({
                    "action": "subscribe",
                    "trades": list(add),
                    "quotes": list(add),
                    "bars":   list(add),
                }))
            if remove:
                await self._ws.send(json.dumps({
                    "action": "unsubscribe",
                    "trades": list(remove),
                    "quotes": list(remove),
                    "bars":   list(remove),
                }))

    def on_update(self, callback: Callable):
        """Register a callback that fires on every price update."""
        self._callbacks.append(callback)

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> float:
        return self._prices.get(symbol.upper(), 0.0)

    def get_quote(self, symbol: str) -> dict:
        return self._quotes.get(symbol.upper(), {})

    def get_bars(self, symbol: str) -> list:
        return list(self._bars[symbol.upper()])

    def get_change_pct(self, symbol: str) -> float:
        return self._changes.get(symbol.upper(), 0.0)

    def get_snapshot(self) -> dict:
        """Full current-state snapshot for all symbols."""
        now = datetime.now(ET).isoformat()
        out = {}
        for sym in self._subscribed:
            quote = self._quotes.get(sym, {})
            out[sym] = {
                "symbol":     sym,
                "price":      self._prices.get(sym, 0),
                "bid":        quote.get("bid", 0),
                "ask":        quote.get("ask", 0),
                "spread":     round(quote.get("ask", 0) - quote.get("bid", 0), 4),
                "change_pct": self._changes.get(sym, 0),
                "volume":     self._volumes.get(sym, 0),
                "bars_1min":  list(self._bars[sym])[-5:],  # last 5 bars
                "updated_at": now,
            }
        return out

    def get_top_movers(self, n: int = 5) -> dict:
        """Return biggest gainers and losers from live feed."""
        changes = [(sym, self._changes.get(sym, 0)) for sym in self._subscribed if sym in self._prices]
        changes.sort(key=lambda x: x[1], reverse=True)
        return {
            "gainers": [{"symbol": s, "change_pct": round(c, 2), "price": self._prices.get(s, 0)} for s, c in changes[:n] if c > 0],
            "losers":  [{"symbol": s, "change_pct": round(c, 2), "price": self._prices.get(s, 0)} for s, c in changes[-n:] if c < 0],
        }

    # ── WebSocket connection loop ──────────────────────────────────────────────

    async def _connect_loop(self):
        """Reconnects automatically on disconnect."""
        while self._running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stream error: {e} — reconnecting in 5s")
                await asyncio.sleep(5)

    async def _connect(self):
        async with websockets.connect(self.url, ping_interval=20) as ws:
            self._ws = ws
            logger.info(f"WebSocket connected: {self.url}")

            async for raw in ws:
                if not self._running:
                    break
                try:
                    messages = json.loads(raw)
                    for msg in (messages if isinstance(messages, list) else [messages]):
                        await self._handle(msg)
                except Exception as e:
                    logger.debug(f"Parse error: {e}")

    async def _handle(self, msg: dict):
        mtype = msg.get("T", "")

        # ── Auth / subscription ────────────────────────────────────────────────
        if mtype == "connected":
            await self._ws.send(json.dumps({
                "action": "auth",
                "key":    self.api_key,
                "secret": self.secret_key,
            }))

        elif mtype == "success" and msg.get("msg") == "authenticated":
            syms = list(self._subscribed)
            await self._ws.send(json.dumps({
                "action": "subscribe",
                "trades": syms,
                "quotes": syms,
                "bars":   syms,
            }))
            logger.info(f"Subscribed to {len(syms)} symbols")

        # ── Trade (last price) ─────────────────────────────────────────────────
        elif mtype == "t":
            sym   = msg.get("S", "")
            price = float(msg.get("p", 0))
            size  = int(msg.get("s", 0))
            if sym and price:
                self._prices[sym]  = price
                self._volumes[sym] = self._volumes.get(sym, 0) + size
                await self._fire_callbacks(sym, price)

        # ── Quote (bid/ask) ────────────────────────────────────────────────────
        elif mtype == "q":
            sym = msg.get("S", "")
            if sym:
                self._quotes[sym] = {
                    "bid":      float(msg.get("bp", 0)),
                    "ask":      float(msg.get("ap", 0)),
                    "bid_size": int(msg.get("bs", 0)),
                    "ask_size": int(msg.get("as", 0)),
                }

        # ── 1-min bar ─────────────────────────────────────────────────────────
        elif mtype == "b":
            sym = msg.get("S", "")
            if sym:
                bar = {
                    "time":   msg.get("t", ""),
                    "open":   float(msg.get("o", 0)),
                    "high":   float(msg.get("h", 0)),
                    "low":    float(msg.get("l", 0)),
                    "close":  float(msg.get("c", 0)),
                    "volume": int(msg.get("v", 0)),
                }
                self._bars[sym].append(bar)

                # Compute % change vs first bar of session
                bars = list(self._bars[sym])
                if len(bars) >= 2:
                    first_open = bars[0]["open"]
                    if first_open:
                        self._changes[sym] = round((bar["close"] - first_open) / first_open * 100, 3)

    async def _fire_callbacks(self, symbol: str, price: float):
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(symbol, price, self.get_snapshot())
                else:
                    cb(symbol, price, self.get_snapshot())
            except Exception as e:
                logger.error(f"Callback error: {e}")
