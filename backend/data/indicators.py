"""
Technical indicators — calculates RSI, MACD, Bollinger Bands, EMA crossovers,
ATR, Stochastic, and OBV, then converts them into a rule-based trading signal.
"""
import numpy as np
import pandas as pd

try:
    from ta.trend import MACD, EMAIndicator
    from ta.momentum import RSIIndicator, StochasticOscillator
    from ta.volatility import BollingerBands, AverageTrueRange
    from ta.volume import OnBalanceVolumeIndicator
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False

import logging
logger = logging.getLogger(__name__)


# ── Indicator calculation ──────────────────────────────────────────────────────

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 52 or not _TA_AVAILABLE:
        return df

    df = df.copy()
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # RSI
    df["rsi"] = RSIIndicator(close=c, window=14).rsi()

    # MACD
    _macd = MACD(close=c, window_slow=26, window_fast=12, window_sign=9)
    df["macd"]        = _macd.macd()
    df["macd_signal"] = _macd.macd_signal()
    df["macd_diff"]   = _macd.macd_diff()

    # Bollinger Bands
    _bb = BollingerBands(close=c, window=20, window_dev=2)
    df["bb_upper"] = _bb.bollinger_hband()
    df["bb_lower"] = _bb.bollinger_lband()
    df["bb_mid"]   = _bb.bollinger_mavg()
    df["bb_pct"]   = _bb.bollinger_pband()   # 0 = lower, 1 = upper

    # EMAs
    df["ema_9"]  = EMAIndicator(close=c, window=9).ema_indicator()
    df["ema_21"] = EMAIndicator(close=c, window=21).ema_indicator()
    df["ema_50"] = EMAIndicator(close=c, window=50).ema_indicator()

    # ATR
    df["atr"] = AverageTrueRange(high=h, low=l, close=c, window=14).average_true_range()

    # Stochastic
    _stoch = StochasticOscillator(high=h, low=l, close=c, window=14, smooth_window=3)
    df["stoch_k"] = _stoch.stoch()
    df["stoch_d"] = _stoch.stoch_signal()

    # OBV
    df["obv"] = OnBalanceVolumeIndicator(close=c, volume=v).on_balance_volume()

    # Price momentum
    df["price_change_1"]  = c.pct_change(1)
    df["price_change_5"]  = c.pct_change(5)
    df["price_change_10"] = c.pct_change(10)

    # Volume
    df["volume_ma"]    = v.rolling(20).mean()
    df["volume_ratio"] = v / df["volume_ma"].replace(0, np.nan)

    # EMA cross direction: +1 bullish, -1 bearish
    df["ema_cross"]        = np.where(df["ema_9"] > df["ema_21"], 1, -1)
    df["ema_cross_change"] = df["ema_cross"].diff()

    return df.dropna()


# ── Rule-based signal ─────────────────────────────────────────────────────────

def get_signal_from_indicators(df: pd.DataFrame) -> dict:
    """
    Converts indicator values into BUY / SELL / HOLD with a 0-1 confidence score.
    """
    if len(df) < 5:
        return {"signal": "HOLD", "confidence": 0.0, "reasons": ["Insufficient data"]}

    cur  = df.iloc[-1]
    prev = df.iloc[-2]
    reasons = []

    buy_votes  = []   # list of (label, weight)
    sell_votes = []

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi = cur.get("rsi", 50)
    if   rsi < 28:  buy_votes.append(("RSI deeply oversold", 0.90)); reasons.append(f"RSI oversold {rsi:.1f}")
    elif rsi < 38:  buy_votes.append(("RSI oversold",        0.55)); reasons.append(f"RSI weak {rsi:.1f}")
    elif rsi > 72:  sell_votes.append(("RSI deeply overbought", 0.90)); reasons.append(f"RSI overbought {rsi:.1f}")
    elif rsi > 62:  sell_votes.append(("RSI overbought",        0.55)); reasons.append(f"RSI elevated {rsi:.1f}")

    # ── MACD crossover ────────────────────────────────────────────────────────
    md, pmd = cur.get("macd_diff", 0), prev.get("macd_diff", 0)
    if   md > 0 and pmd <= 0: buy_votes.append(("MACD bullish cross", 0.90));  reasons.append("MACD bullish crossover")
    elif md < 0 and pmd >= 0: sell_votes.append(("MACD bearish cross", 0.90)); reasons.append("MACD bearish crossover")
    elif md > 0:              buy_votes.append(("MACD positive", 0.35))
    elif md < 0:              sell_votes.append(("MACD negative", 0.35))

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb = cur.get("bb_pct", 0.5)
    if   bb < 0.05: buy_votes.append(("BB lower-band touch", 0.80));  reasons.append("Price at lower Bollinger Band")
    elif bb > 0.95: sell_votes.append(("BB upper-band touch", 0.80)); reasons.append("Price at upper Bollinger Band")

    # ── EMA crossover ─────────────────────────────────────────────────────────
    ecc = cur.get("ema_cross_change", 0)
    if   ecc ==  2: buy_votes.append(("EMA9 crossed above EMA21", 0.85));  reasons.append("EMA9 crossed above EMA21")
    elif ecc == -2: sell_votes.append(("EMA9 crossed below EMA21", 0.85)); reasons.append("EMA9 crossed below EMA21")
    elif cur.get("ema_cross", 0) ==  1: buy_votes.append(("Bullish EMA trend",  0.30))
    elif cur.get("ema_cross", 0) == -1: sell_votes.append(("Bearish EMA trend", 0.30))

    # ── Stochastic ────────────────────────────────────────────────────────────
    sk, sd = cur.get("stoch_k", 50), cur.get("stoch_d", 50)
    if   sk < 20 and sd < 20: buy_votes.append(("Stochastic oversold",   0.70)); reasons.append(f"Stoch oversold {sk:.0f}")
    elif sk > 80 and sd > 80: sell_votes.append(("Stochastic overbought", 0.70)); reasons.append(f"Stoch overbought {sk:.0f}")

    # ── Volume confirmation multiplier ────────────────────────────────────────
    vol_ratio = cur.get("volume_ratio", 1.0)
    vol_mult  = 1.25 if vol_ratio > 1.5 else 1.0

    total = len(buy_votes) + len(sell_votes) or 1
    buy_conf  = (sum(w for _, w in buy_votes)  * vol_mult) / total
    sell_conf = (sum(w for _, w in sell_votes) * vol_mult) / total

    base = {
        "rsi":          round(rsi, 1),
        "macd_diff":    round(md, 4),
        "bb_pct":       round(bb, 3),
        "volume_ratio": round(vol_ratio, 2),
        "atr":          round(cur.get("atr", 0), 4),
        "reasons":      reasons,
    }

    if buy_conf > sell_conf and buy_conf > 0.30:
        return {**base, "signal": "BUY",  "confidence": round(min(buy_conf,  0.99), 3)}
    if sell_conf > buy_conf and sell_conf > 0.30:
        return {**base, "signal": "SELL", "confidence": round(min(sell_conf, 0.99), 3)}
    return     {**base, "signal": "HOLD", "confidence": round(max(buy_conf, sell_conf), 3)}
