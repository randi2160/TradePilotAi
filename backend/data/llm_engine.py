"""
Real-Time LLM Decision Engine

Flow:
  1. LiveDataStream pushes every price tick
  2. Engine accumulates ticks into a rolling context window
  3. Every N seconds (configurable), sends full context to GPT-4
  4. GPT-4 responds with: action (BUY/SELL/HOLD/EXIT), urgency, confidence, reasoning
  5. Engine fires callbacks so bot_loop can act immediately

GPT-4 receives:
  • Live bid/ask spread + last 5 price ticks
  • 5-min bar history (OHLCV)
  • Technical indicator snapshot (RSI, MACD, ATR, volume ratio)
  • News sentiment score for that symbol
  • Current open position status
  • Portfolio P&L vs daily target
  • Market-wide context (SPY trend, VIX proxy)
"""
import asyncio
import json
import logging
import os
from collections import defaultdict, deque
from datetime import datetime
from typing import Callable, Optional

import httpx
import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_URL     = "https://api.openai.com/v1/chat/completions"

_SYSTEM = """You are a real-time algorithmic trading AI. You receive a live market brief 
for a single stock every 30 seconds and must decide: BUY, SELL, HOLD, or EXIT.

You think like an elite day trader:
- Momentum and volume are your primary signals
- News sentiment shifts your bias
- Spread > 0.10% = bad fill risk, reduce size or skip
- Never chase — wait for a pullback entry
- Protect capital first, profit second

Respond ONLY in this exact JSON format (no markdown, no extra text):
{
  "action": "BUY | SELL | HOLD | EXIT",
  "urgency": "immediate | wait_for_pullback | watch_only",
  "confidence": 0-100,
  "entry_price": null or float,
  "stop_loss": null or float,
  "take_profit": null or float,
  "position_size_pct": 5-20,
  "reasoning": "1-2 sentence explanation",
  "risk_flag": null or "high_spread | low_volume | news_risk | overextended | near_resistance",
  "time_in_trade": "scalp_5min | intraday | avoid"
}"""


class RealTimeLLMEngine:
    def __init__(self, call_interval: int = 30):
        """
        call_interval: how often (seconds) to query GPT-4 per symbol.
        Lower = faster decisions but more API cost.
        """
        self.call_interval = call_interval
        self._decisions:   dict[str, dict]         = {}     # latest decision per symbol
        self._tick_buffer: dict[str, deque]        = defaultdict(lambda: deque(maxlen=20))
        self._callbacks:   list[Callable]          = []
        self._last_call:   dict[str, float]        = {}
        self._running:     bool                    = False
        self._queue:       asyncio.Queue           = asyncio.Queue()
        self._task:        Optional[asyncio.Task]  = None
        self._context:     dict                    = {}     # shared context (sentiment, SPY, etc.)

    # ── Control ───────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._task    = asyncio.create_task(self._worker())
        logger.info("RealTimeLLMEngine started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    def on_decision(self, callback: Callable):
        """Register callback fired when GPT-4 makes a decision."""
        self._callbacks.append(callback)

    def set_context(self, context: dict):
        """Update shared context (portfolio P&L, sentiment, SPY trend, etc.)"""
        self._context = context

    # ── Live price feed handler ───────────────────────────────────────────────

    async def on_price_tick(self, symbol: str, price: float, snapshot: dict):
        """Called by LiveDataStream on every trade tick."""
        self._tick_buffer[symbol].append({
            "price": price,
            "time":  datetime.now(ET).strftime("%H:%M:%S"),
        })

        # Queue a GPT-4 call if enough time has passed
        now = datetime.now().timestamp()
        last = self._last_call.get(symbol, 0)
        if now - last >= self.call_interval:
            self._last_call[symbol] = now
            sym_snapshot = snapshot.get(symbol, {})
            await self._queue.put((symbol, sym_snapshot, dict(self._context)))

    # ── Worker — processes queue and calls GPT-4 ─────────────────────────────

    async def _worker(self):
        while self._running:
            try:
                symbol, snap, ctx = await asyncio.wait_for(self._queue.get(), timeout=5.0)
                decision = await self._call_gpt4(symbol, snap, ctx)
                if decision:
                    decision["symbol"]     = symbol
                    decision["timestamp"]  = datetime.now(ET).isoformat()
                    decision["live_price"] = snap.get("price", 0)
                    self._decisions[symbol] = decision
                    await self._fire(symbol, decision)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"LLM worker error: {e}")
                await asyncio.sleep(2)

    # ── GPT-4 call ────────────────────────────────────────────────────────────

    async def _call_gpt4(self, symbol: str, snap: dict, ctx: dict) -> Optional[dict]:
        if not OPENAI_API_KEY:
            return None

        brief = self._build_brief(symbol, snap, ctx)

        try:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type":  "application/json",
            }
            body = {
                "model":           "gpt-4o",
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": brief},
                ],
                "temperature":     0.1,
                "max_tokens":      300,
                "response_format": {"type": "json_object"},
            }
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(OPENAI_URL, headers=headers, json=body)
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                decision = json.loads(content)
                logger.info(
                    f"LLM [{symbol}] → {decision.get('action')} "
                    f"conf={decision.get('confidence')}% | {decision.get('reasoning','')[:60]}"
                )
                return decision
        except Exception as e:
            logger.warning(f"GPT-4 call failed for {symbol}: {e}")
            return None

    # ── Brief builder ─────────────────────────────────────────────────────────

    def _build_brief(self, symbol: str, snap: dict, ctx: dict) -> str:
        now   = datetime.now(ET).strftime("%I:%M:%S %p ET")
        ticks = list(self._tick_buffer[symbol])
        bars  = snap.get("bars_1min", [])

        lines = [f"=== LIVE BRIEF: {symbol} @ {now} ==="]

        # Live price action
        price  = snap.get("price", 0)
        bid    = snap.get("bid",   0)
        ask    = snap.get("ask",   0)
        spread = snap.get("spread", 0)
        spread_pct = (spread / price * 100) if price else 0

        lines.append(f"PRICE: ${price:.2f} | Bid: ${bid:.2f} | Ask: ${ask:.2f} | Spread: {spread_pct:.3f}%")
        lines.append(f"Change today: {snap.get('change_pct', 0):+.2f}% | Volume: {snap.get('volume', 0):,}")

        # Last 10 ticks (price momentum)
        if ticks:
            prices = [t["price"] for t in ticks[-10:]]
            direction = "▲ RISING" if prices[-1] > prices[0] else "▼ FALLING" if prices[-1] < prices[0] else "→ FLAT"
            tick_range = max(prices) - min(prices)
            lines.append(f"Tick momentum: {direction} | Last 10-tick range: ${tick_range:.3f}")
            lines.append(f"Prices: {' → '.join(f'${p:.2f}' for p in prices[-5:])}")

        # 1-min bars
        if bars:
            lines.append(f"\nLAST {len(bars)} 1-MIN BARS:")
            for b in bars[-5:]:
                body   = abs(b.get("close",0) - b.get("open",0))
                candle = "🟢" if b.get("close",0) >= b.get("open",0) else "🔴"
                lines.append(
                    f"  {candle} O:{b.get('open',0):.2f} H:{b.get('high',0):.2f} "
                    f"L:{b.get('low',0):.2f} C:{b.get('close',0):.2f} "
                    f"V:{b.get('volume',0):,} Body:${body:.3f}"
                )

        # Technical signals from context
        signals = ctx.get("signals", [])
        sig     = next((s for s in signals if s.get("symbol") == symbol), None)
        if sig:
            lines.append(f"\nTECHNICAL INDICATORS:")
            lines.append(f"  AI Signal: {sig.get('signal','?')} | Confidence: {sig.get('confidence',0):.0%}")
            lines.append(f"  RSI: {sig.get('rsi',0):.1f} | ATR: {sig.get('atr',0):.4f} | Vol Ratio: {sig.get('volume_ratio',1):.1f}×")
            if sig.get("reasons"):
                lines.append(f"  Signals: {', '.join(sig['reasons'][:4])}")

        # News sentiment
        sentiment = ctx.get("sentiment", {}).get(symbol, {})
        if sentiment:
            lines.append(f"\nNEWS SENTIMENT: {sentiment.get('sentiment','neutral').upper()} (score: {sentiment.get('score',0):+.2f})")
            headlines = sentiment.get("headlines", [])
            if headlines:
                lines.append(f"  Latest: \"{headlines[0][:80]}\"")

        # Market context (SPY)
        spy_snap = ctx.get("spy", {})
        if spy_snap:
            lines.append(f"\nMARKET (SPY): ${spy_snap.get('price',0):.2f} | {spy_snap.get('change_pct',0):+.2f}%")

        # Portfolio context
        pnl      = ctx.get("realized_pnl", 0)
        target   = ctx.get("target_max", 250)
        capital  = ctx.get("capital", 5000)
        open_pos = ctx.get("open_positions", 0)
        lines.append(f"\nPORTFOLIO: P&L today ${pnl:+.2f} | Target ${target} | Capital ${capital:,} | Open positions: {open_pos}")

        # Open position in this symbol?
        positions = ctx.get("positions", [])
        pos = next((p for p in positions if p.get("symbol") == symbol), None)
        if pos:
            lines.append(f"CURRENT POSITION: {pos.get('side','').upper()} {pos.get('qty')} @ ${pos.get('avg_entry',0):.2f} | UPnL: ${pos.get('unrealized_pnl',0):+.2f}")
        else:
            lines.append("CURRENT POSITION: None — considering entry")

        lines.append(f"\nDecide: BUY, SELL, HOLD, or EXIT for {symbol}?")

        return "\n".join(lines)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    async def _fire(self, symbol: str, decision: dict):
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(symbol, decision)
                else:
                    cb(symbol, decision)
            except Exception as e:
                logger.error(f"Decision callback error: {e}")

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_decisions(self) -> list:
        return [
            {**v, "symbol": k}
            for k, v in self._decisions.items()
            if v.get("action") != "HOLD"
        ]

    def get_all_decisions(self) -> dict:
        return dict(self._decisions)

    def get_decision(self, symbol: str) -> Optional[dict]:
        return self._decisions.get(symbol.upper())
