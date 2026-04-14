"""
Binance Public Market Scanner — No API key required.
Uses Binance's public REST API to get real-time crypto momentum data.
Much faster than yfinance batch download (200ms vs 1.5s).

Endpoints used (all free, no auth):
  GET /api/v3/ticker/24hr       — 24h stats for all symbols
  GET /api/v3/klines            — OHLCV candles for momentum scoring
"""
import logging
import time
import requests
from typing import Optional

logger = logging.getLogger(__name__)

BINANCE_BASE = "https://api.binance.com"

# Map our tickers to Binance symbols
BINANCE_MAP = {
    "BTC":  "BTCUSDT",  "ETH":  "ETHUSDT",  "SOL":  "SOLUSDT",
    "DOGE": "DOGEUSDT", "LINK": "LINKUSDT",  "AAVE": "AAVEUSDT",
    "LTC":  "LTCUSDT",  "BCH":  "BCHUSDT",   "AVAX": "AVAXUSDT",
    "XRP":  "XRPUSDT",  "ADA":  "ADAUSDT",   "DOT":  "DOTUSDT",
    "ATOM": "ATOMUSDT", "ALGO": "ALGOUSDT",  "NEAR": "NEARUSDT",
    "SAND": "SANDUSDT", "MANA": "MANAUSDT",  "CRV":  "CRVUSDT",
    "SUSHI":"SUSHIUSDT","BAT":  "BATUSDT",   "ZEC":  "ZECUSDT",
    "DASH": "DASHUSDT", "ETC":  "ETCUSDT",   "FIL":  "FILUSDT",
    "SHIB": "SHIBUSDT",
}

# Reverse map: BTCUSDT → BTC
REVERSE_MAP = {v: k for k, v in BINANCE_MAP.items()}

# Alpaca paper-tradeable subset
ALPACA_TRADEABLE = {
    "BTC", "ETH", "LTC", "BCH", "DOGE",
    "LINK", "AAVE", "SOL", "XRP", "SHIB",
}

_session = requests.Session()
_session.headers.update({"User-Agent": "MorviqAI/1.0"})

_ticker_cache: dict = {}
_ticker_cache_ts: float = 0
TICKER_CACHE_TTL = 10  # seconds
BINANCE_BLOCKED  = False  # set True on 451 geo-block (AWS US server restriction)


def get_all_24h_tickers() -> dict:
    """
    Fetch 24h stats for ALL crypto tickers in one call.
    Returns {ticker: {price, change_pct, volume_usdt, quote_volume}}
    Cached for 10 seconds. Returns {} immediately if geo-blocked (451).
    """
    global _ticker_cache, _ticker_cache_ts, BINANCE_BLOCKED

    if BINANCE_BLOCKED:
        return {}  # Don't retry — AWS US servers are geo-blocked by Binance

    now = time.time()
    if now - _ticker_cache_ts < TICKER_CACHE_TTL and _ticker_cache:
        return _ticker_cache

    try:
        resp = _session.get(
            f"{BINANCE_BASE}/api/v3/ticker/24hr",
            timeout=3,
        )
        if resp.status_code == 451:
            logger.warning("Binance 451 geo-block detected — AWS US servers are restricted. Switching to yfinance permanently.")
            BINANCE_BLOCKED = True
            return {}
        resp.raise_for_status()
        raw = resp.json()

        result = {}
        our_symbols = set(BINANCE_MAP.values())
        for item in raw:
            sym = item.get("symbol", "")
            if sym not in our_symbols:
                continue
            ticker = REVERSE_MAP.get(sym)
            if not ticker:
                continue
            try:
                result[ticker] = {
                    "symbol":       sym,
                    "price":        float(item["lastPrice"]),
                    "change_pct":   float(item["priceChangePercent"]),  # 24h %
                    "volume_usdt":  float(item["quoteVolume"]),         # USD volume
                    "high_24h":     float(item["highPrice"]),
                    "low_24h":      float(item["lowPrice"]),
                    "open_24h":     float(item["openPrice"]),
                    "count":        int(item.get("count", 0)),          # trade count
                }
            except Exception:
                continue

        _ticker_cache    = result
        _ticker_cache_ts = now
        logger.debug(f"Binance 24h tickers fetched: {len(result)} coins")
        return result

    except Exception as e:
        logger.warning(f"Binance 24h fetch failed: {e} — falling back to cache")
        return _ticker_cache or {}


def get_klines(ticker: str, interval: str = "1m", limit: int = 50) -> list:
    """
    Fetch OHLCV candles for a single ticker.
    Returns list of [open, high, low, close, volume] as floats.
    interval: 1m, 3m, 5m, 15m, 1h
    """
    sym = BINANCE_MAP.get(ticker.upper())
    if not sym:
        return []
    try:
        resp = _session.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={"symbol": sym, "interval": interval, "limit": limit},
            timeout=3,
        )
        resp.raise_for_status()
        raw = resp.json()
        # Each candle: [open_time, open, high, low, close, volume, ...]
        return [
            [float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])]
            for c in raw
        ]
    except Exception as e:
        logger.debug(f"Binance klines {ticker}: {e}")
        return []


def score_momentum(ticker: str, tickers_24h: dict) -> dict:
    """
    Score a coin's momentum using:
    1. 24h price change %
    2. Volume relative to market
    3. Short-term candle momentum (5m)
    Returns scored dict ready for ranking.
    """
    import numpy as np

    stats = tickers_24h.get(ticker, {})
    if not stats:
        return {"ticker": ticker, "score": 0, "valid": False, "price": 0}

    price      = stats["price"]
    change_24h = stats["change_pct"]       # 24h %
    vol_usdt   = stats["volume_usdt"]      # dollar volume
    high_24h   = stats["high_24h"]
    low_24h    = stats["low_24h"]
    open_24h   = stats["open_24h"]

    # --- Short-term candles for momentum scoring ---
    candles = get_klines(ticker, interval="5m", limit=20)
    if len(candles) >= 5:
        closes  = np.array([c[3] for c in candles])
        volumes = np.array([c[4] for c in candles])

        # 5-bar momentum
        mom5  = (closes[-1] - closes[-5]) / closes[-5] * 100 if closes[-5] > 0 else 0
        # 20-bar momentum
        mom20 = (closes[-1] - closes[0])  / closes[0]  * 100 if closes[0]  > 0 else 0
        # Volume spike vs 10-bar average
        avg_vol   = float(np.mean(volumes[-10:])) if len(volumes) >= 10 else 1
        vol_spike = min(5.0, float(volumes[-1]) / avg_vol) if avg_vol > 0 else 1.0
        # ATR
        atr = float(np.mean(np.abs(np.diff(closes[-14:])))) if len(closes) >= 15 else price * 0.005
    else:
        # Fall back to 24h data only
        mom5    = change_24h / 8  # rough 3h proxy
        mom20   = change_24h
        vol_spike = 1.0
        atr     = (high_24h - low_24h) / 20 if high_24h > low_24h else price * 0.005

    # --- Directional score ---
    score = abs(mom5) * 3 + abs(mom20) * 1 + (vol_spike - 1) * 2

    # --- Signal ---
    bullish = 0
    if mom5  > 0.2:  bullish += 2
    if mom20 > 0.5:  bullish += 2
    if vol_spike > 1.5: bullish += 1
    if mom5  < -0.2: bullish -= 3
    if mom20 < -0.5: bullish -= 2

    if bullish >= 3:
        signal     = "BUY"
        confidence = min(88, 55 + bullish * 5)
    elif bullish <= -3:
        signal     = "SELL"
        confidence = min(82, 55 + abs(bullish) * 5)
    else:
        signal     = "HOLD"
        confidence = 40

    entry  = round(price, 8)
    target = round(price * (1 + atr / price * 3), 8) if signal == "BUY" else round(price * (1 - atr / price * 3), 8)
    stop   = round(price * (1 - atr / price * 2), 8) if signal == "BUY" else round(price * (1 + atr / price * 2), 8)

    return {
        "ticker":      ticker,
        "symbol":      f"{ticker}/USD",
        "price":       price,
        "score":       round(score, 2),
        "momentum":    round(mom5, 3),
        "change_24h":  round(change_24h, 3),
        "vol_spike":   round(vol_spike, 2),
        "vol_usdt":    round(vol_usdt, 0),
        "atr":         round(atr, 8),
        "signal":      signal,
        "confidence":  int(confidence),
        "valid":       confidence >= 40 and score > 0,
        "entry":       entry,
        "exit_target": target,
        "stop":        stop,
        "tradeable":   ticker in ALPACA_TRADEABLE,
    }


def scan_all_coins(universe: list) -> list:
    """
    Scan all coins in universe using Binance data.
    Returns list sorted by score descending.
    ~200-400ms total (vs 1.5s+ with yfinance batch).
    """
    # One call gets 24h stats for all coins simultaneously
    tickers_24h = get_all_24h_tickers()
    if not tickers_24h:
        logger.warning("Binance scan: no 24h data available")
        return []

    results = []
    for ticker in universe:
        try:
            scored = score_momentum(ticker, tickers_24h)
            results.append(scored)
        except Exception as e:
            logger.debug(f"Score {ticker}: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    logger.info(
        f"Binance scan: {len(results)} coins | "
        f"top={results[0]['ticker']} score={results[0]['score']:.1f} "
        f"${results[0]['price']:.4f}" if results else "no results"
    )
    return results


def get_live_price(ticker: str) -> float:
    """
    Get single live price from Binance (very fast, <50ms).
    Used for position monitoring between scan cycles.
    """
    sym = BINANCE_MAP.get(ticker.upper())
    if not sym:
        return 0.0
    try:
        resp = _session.get(
            f"{BINANCE_BASE}/api/v3/ticker/price",
            params={"symbol": sym},
            timeout=2,
        )
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception as e:
        logger.debug(f"Binance price {ticker}: {e}")
        return 0.0