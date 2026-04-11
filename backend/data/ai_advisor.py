"""
AI Advisor — feeds GPT-4 every piece of data we have and asks for
precise trade recommendations with entry, exit, probability, and reasoning.

Data fed to GPT-4:
  • Top gainers / losers / most active (market scanner)
  • News sentiment per symbol
  • Technical indicator signals (RSI, MACD, BB, EMA, ATR)
  • Ensemble ML signal + confidence
  • Unusual volume alerts
  • Current portfolio P&L and open positions
  • Daily target progress
  • Time of day / market conditions
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional

import httpx
import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_URL     = "https://api.openai.com/v1/chat/completions"

_SYSTEM_PROMPT = """You are an elite quantitative day trader AI with 20+ years of experience.
You analyze ALL available market data and give precise, actionable trade recommendations.

Your job:
1. Identify the 1-3 BEST trade opportunities for today from the data provided
2. For each trade: give exact entry price zone, stop loss, take profit, position size %, and probability
3. Explain the confluence of signals (technical + sentiment + volume + momentum)
4. Flag any high-risk conditions to avoid
5. Give a market regime assessment (trending, choppy, risk-on, risk-off)

Rules:
- Only recommend trades with 3+ confirming signals
- Always include risk/reward ratio (minimum 2:1)
- Be specific about WHEN to enter (e.g. "buy the first 5-min pullback above $185")
- Account for the user's daily profit target
- If market conditions are poor, say STAY OUT — capital preservation is paramount

Respond ONLY in valid JSON matching this exact structure:
{
  "market_regime": "trending_bullish | trending_bearish | choppy | risk_on | risk_off",
  "regime_explanation": "2-3 sentence market overview",
  "overall_stance": "aggressive | moderate | conservative | stay_out",
  "top_trades": [
    {
      "symbol": "AAPL",
      "action": "BUY | SELL | WAIT",
      "conviction": 85,
      "entry_zone": {"low": 184.50, "high": 185.20},
      "stop_loss": 182.00,
      "take_profit": 191.00,
      "risk_reward": 3.2,
      "position_size_pct": 15,
      "timeframe": "intraday | swing",
      "entry_trigger": "Buy first pullback to 9 EMA after 10 AM",
      "exit_trigger": "Exit if closes below VWAP or hits $191",
      "signals_confluence": ["RSI bouncing from 35", "MACD bullish cross", "Positive earnings news"],
      "risks": ["Broad market weakness could drag down", "Resistance at $187"],
      "probability_of_target": 72
    }
  ],
  "symbols_to_avoid": ["TSLA", "COIN"],
  "avoid_reasons": {"TSLA": "High volatility + bearish news", "COIN": "Crypto correlation risk"},
  "insider_signals": ["Unusual call options on NVDA expiring Friday", "Dark pool print on SPY at $485"],
  "key_levels_today": {"SPY": {"support": 480, "resistance": 487}, "QQQ": {"support": 395, "resistance": 402}},
  "risk_warning": "Optional: any systemic risk to flag today",
  "confidence_score": 78,
  "generated_at": "2024-01-15T09:45:00"
}"""


class AIAdvisor:
    def __init__(self):
        self._last_advice: Optional[dict] = None
        self._last_run:    str            = ""
        self._cache_ttl:   int            = 300   # 5 minutes

    # ── Main entry ────────────────────────────────────────────────────────────

    async def get_advice(
        self,
        market_scan:   dict,
        news_sentiment: dict,
        signals:       list,
        tracker_stats: dict,
        positions:     list,
        force:         bool = False,
    ) -> dict:
        """
        Build a rich market brief and ask GPT-4 for trade recommendations.
        Caches results for 5 minutes unless force=True.
        """
        if not OPENAI_API_KEY:
            return self._no_key_response()

        # Cache check
        now = datetime.now(ET).isoformat()
        if not force and self._last_advice and self._last_run:
            from datetime import datetime as dt
            try:
                diff = (dt.fromisoformat(now[:19]) - dt.fromisoformat(self._last_run[:19])).seconds
                if diff < self._cache_ttl:
                    return self._last_advice
            except Exception:
                pass

        brief = self._build_brief(market_scan, news_sentiment, signals, tracker_stats, positions)

        try:
            advice = await self._call_openai(brief)
            advice["data_brief"] = brief   # attach the raw brief for UI display
            self._last_advice = advice
            self._last_run    = now
            return advice
        except Exception as e:
            logger.error(f"AIAdvisor error: {e}")
            return {"error": str(e), "top_trades": [], "market_regime": "unknown"}

    # ── Data brief builder ────────────────────────────────────────────────────

    def _build_brief(
        self,
        market_scan:    dict,
        news_sentiment: dict,
        signals:        list,
        tracker_stats:  dict,
        positions:      list,
    ) -> str:
        now    = datetime.now(ET)
        lines  = []

        lines.append(f"=== MARKET BRIEF — {now.strftime('%A %B %d, %Y %I:%M %p ET')} ===\n")

        # Daily P&L context
        pnl     = tracker_stats.get("realized_pnl", 0)
        capital = tracker_stats.get("capital", 5000)
        t_min   = tracker_stats.get("target_min", 100)
        t_max   = tracker_stats.get("target_max", 250)
        lines.append(f"PORTFOLIO: Capital=${capital:,.0f} | Today P&L=${pnl:+.2f} | Target=${t_min}-${t_max}/day")
        lines.append(f"Progress: {tracker_stats.get('progress_pct',0):.0f}% toward min target")
        lines.append(f"Open positions: {len(positions)}")
        if positions:
            for p in positions:
                lines.append(f"  - {p.get('symbol')} {p.get('side')} {p.get('qty')} @ ${p.get('avg_entry',0):.2f} | UPnL=${p.get('unrealized_pnl',0):+.2f}")
        lines.append("")

        # Top movers
        gainers = market_scan.get("gainers", [])[:8]
        losers  = market_scan.get("losers",  [])[:5]
        actives = market_scan.get("most_active", [])[:5]

        if gainers:
            lines.append("TOP GAINERS TODAY:")
            for g in gainers:
                lines.append(f"  {g['symbol']:6} +{g['change_pct']:.1f}% @ ${g['price']:.2f} | Vol: {g['volume']:,}")

        if losers:
            lines.append("TOP LOSERS TODAY:")
            for g in losers:
                lines.append(f"  {g['symbol']:6} {g['change_pct']:.1f}% @ ${g['price']:.2f} | Vol: {g['volume']:,}")

        if actives:
            lines.append("MOST ACTIVE:")
            for g in actives:
                lines.append(f"  {g['symbol']:6} Vol: {g['volume']:,} | {g['change_pct']:+.1f}%")
        lines.append("")

        # News sentiment
        if news_sentiment:
            lines.append("NEWS SENTIMENT SCORES (-1 bearish → +1 bullish):")
            sorted_sent = sorted(news_sentiment.items(), key=lambda x: x[1].get("score", 0), reverse=True)
            for sym, sent in sorted_sent[:12]:
                score = sent.get("score", 0)
                label = sent.get("sentiment", "neutral")
                headlines = sent.get("headlines", [])
                lines.append(f"  {sym:6} [{score:+.2f}] {label.upper()}")
                if headlines:
                    lines.append(f"         \"{headlines[0][:80]}\"")
        lines.append("")

        # Technical signals
        if signals:
            lines.append("AI TECHNICAL SIGNALS:")
            actionable = [s for s in signals if s.get("signal") in ("BUY","SELL")]
            hold       = [s for s in signals if s.get("signal") == "HOLD"]
            for s in sorted(actionable, key=lambda x: x.get("confidence",0), reverse=True):
                lines.append(
                    f"  {s['symbol']:6} ▶ {s['signal']:4} conf={s.get('confidence',0):.0%} "
                    f"RSI={s.get('rsi',0):.0f} Vol×{s.get('volume_ratio',1):.1f} "
                    f"ATR={s.get('atr',0):.3f}"
                )
                if s.get("reasons"):
                    lines.append(f"         Signals: {', '.join(s['reasons'][:3])}")
            if hold:
                lines.append(f"  HOLD: {', '.join(s['symbol'] for s in hold)}")
        lines.append("")

        # Unusual volume alerts
        unusual = [s for s in signals if s.get("volume_ratio", 1) > 2.5]
        if unusual:
            lines.append("⚠️ UNUSUAL VOLUME ALERTS (>2.5× average):")
            for s in unusual:
                lines.append(f"  {s['symbol']} volume is {s['volume_ratio']:.1f}× normal — potential smart money activity")
        lines.append("")

        # ML model status
        ml_trained = any(s.get("ml_trained") for s in signals) if signals else False
        lines.append(f"ML MODELS: {'ACTIVE (trained on historical data)' if ml_trained else 'Warming up (technical-only mode)'}")
        lines.append(f"Market hours remaining: ~{max(0, 15*60+30 - (now.hour*60+now.minute))} minutes")
        lines.append("")
        lines.append(f"REQUEST: Analyze ALL data above. Identify 1-3 best day trades to hit our ${t_min}-${t_max} target today.")
        lines.append("Include precise entry zones, stop losses, take profits, and conviction scores.")

        return "\n".join(lines)

    # ── OpenAI call ───────────────────────────────────────────────────────────

    async def _call_openai(self, brief: str) -> dict:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type":  "application/json",
        }
        body = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": brief},
            ],
            "temperature":   0.2,
            "max_tokens":    2000,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(OPENAI_URL, headers=headers, json=body)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return json.loads(content)

    # ── Fallback ──────────────────────────────────────────────────────────────

    @staticmethod
    def _no_key_response() -> dict:
        return {
            "error":            "OpenAI API key not set",
            "setup":            "Add OPENAI_API_KEY=sk-... to your .env file",
            "top_trades":       [],
            "market_regime":    "unknown",
            "overall_stance":   "stay_out",
            "confidence_score": 0,
            "regime_explanation": "OpenAI key required for AI advisory. Add OPENAI_API_KEY to .env",
        }
