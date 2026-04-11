"""
VWAP (Volume Weighted Average Price) calculator.
VWAP = sum(price × volume) / sum(volume) — resets each trading day.
Institutional traders anchor to VWAP — price almost always returns to it.
"""
import numpy as np
import pandas as pd


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate intraday VWAP from OHLCV dataframe.
    Resets at the start of each trading day.
    """
    df = df.copy()
    df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3
    df["tp_volume"]     = df["typical_price"] * df["volume"]

    # Group by date to reset daily
    df["date"] = df.index.date if hasattr(df.index, 'date') else pd.to_datetime(df.index).date

    vwap_values = []
    for date, group in df.groupby("date"):
        cum_tp_vol = group["tp_volume"].cumsum()
        cum_vol    = group["volume"].cumsum()
        vwap       = cum_tp_vol / cum_vol.replace(0, np.nan)
        vwap_values.append(vwap)

    if vwap_values:
        return pd.concat(vwap_values).reindex(df.index)
    return pd.Series(index=df.index, dtype=float)


def get_vwap_signal(df: pd.DataFrame) -> dict:
    """
    Returns VWAP context for latest bar:
      - vwap value
      - price relative to VWAP (above/below/at)
      - distance % from VWAP
      - reclaim signal (price crossed above VWAP)
      - rejection signal (price failed at VWAP)
    """
    if len(df) < 5:
        return {"vwap": 0, "above_vwap": False, "distance_pct": 0}

    try:
        vwap   = calculate_vwap(df)
        df     = df.copy()
        df["vwap"] = vwap

        cur     = df.iloc[-1]
        prev    = df.iloc[-2]
        price   = float(cur["close"])
        v       = float(cur["vwap"]) if not pd.isna(cur["vwap"]) else price

        above       = price > v
        dist_pct    = round((price - v) / v * 100, 3) if v > 0 else 0

        # Reclaim: was below, now above
        prev_v      = float(prev["vwap"]) if not pd.isna(prev.get("vwap", float("nan"))) else v
        reclaim     = (prev["close"] < prev_v) and (price > v)
        rejection   = (prev["close"] > prev_v) and (price < v)

        return {
            "vwap":        round(v, 4),
            "price":       round(price, 4),
            "above_vwap":  above,
            "distance_pct": dist_pct,
            "reclaim":     reclaim,      # bullish signal
            "rejection":   rejection,    # bearish signal
            "at_vwap":     abs(dist_pct) < 0.15,  # within 0.15% = at VWAP
        }
    except Exception:
        return {"vwap": 0, "above_vwap": False, "distance_pct": 0}
