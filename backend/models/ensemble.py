"""
Ensemble model — combines:
  1. Rule-based technical-indicator signal     (weight: 40 %)
  2. Gradient Boosting classifier              (weight: 35 %)
  3. Random Forest classifier                  (weight: 25 %)

Falls back gracefully to technical-only if ML models are not yet trained.
Call .train(df) on a sufficient bar history to activate ML layers.
"""
import logging
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from data.indicators import get_signal_from_indicators

logger = logging.getLogger(__name__)

# Features fed into both ML models
FEATURES = [
    "rsi", "macd", "macd_signal", "macd_diff",
    "bb_pct", "ema_9", "ema_21", "ema_50",
    "stoch_k", "stoch_d", "atr",
    "price_change_1", "price_change_5", "price_change_10",
    "volume_ratio", "ema_cross",
]

_GB_WEIGHT   = 0.35
_RF_WEIGHT   = 0.25
_TECH_WEIGHT = 0.40


class EnsembleModel:
    def __init__(self, model_dir: str = "models/saved"):
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
        self.gb: Pipeline | None = None
        self.rf: Pipeline | None = None
        self.is_trained = False
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        gb_p = os.path.join(self.model_dir, "gb.pkl")
        rf_p = os.path.join(self.model_dir, "rf.pkl")
        if os.path.exists(gb_p) and os.path.exists(rf_p):
            try:
                self.gb = joblib.load(gb_p)
                self.rf = joblib.load(rf_p)
                self.is_trained = True
                logger.info("ML models loaded from disk ✓")
            except Exception as e:
                logger.warning(f"Could not load saved models: {e}")

    def _save(self):
        joblib.dump(self.gb, os.path.join(self.model_dir, "gb.pkl"))
        joblib.dump(self.rf, os.path.join(self.model_dir, "rf.pkl"))

    # ── Training ──────────────────────────────────────────────────────────────

    def train(self, df: pd.DataFrame, lookahead: int = 5, threshold: float = 0.004) -> bool:
        """
        Label bars: 1 = price rises ≥ threshold over next `lookahead` bars.
        Requires ≥ 150 labelled rows after NaN-drop.
        """
        if len(df) < 200:
            logger.warning("Need ≥ 200 bars to train ML models")
            return False
        try:
            df = df.copy()
            df["_fut"] = df["close"].shift(-lookahead) / df["close"] - 1
            df["_lbl"] = (df["_fut"] > threshold).astype(int)
            df = df.dropna(subset=["_lbl"])

            feats = [f for f in FEATURES if f in df.columns]
            X, y = df[feats], df["_lbl"]
            if len(X) < 150:
                logger.warning("Not enough labelled rows after dropna")
                return False

            self.gb = Pipeline([
                ("sc", StandardScaler()),
                ("clf", GradientBoostingClassifier(
                    n_estimators=150, max_depth=4,
                    learning_rate=0.05, subsample=0.8,
                    random_state=42,
                )),
            ])
            self.rf = Pipeline([
                ("sc", StandardScaler()),
                ("clf", RandomForestClassifier(
                    n_estimators=150, max_depth=6,
                    min_samples_leaf=5, random_state=42,
                )),
            ])
            self.gb.fit(X, y)
            self.rf.fit(X, y)
            self._save()
            self.is_trained = True

            gb_acc = self.gb.score(X, y)
            rf_acc = self.rf.score(X, y)
            logger.info(f"Models trained on {len(X)} samples | GB acc={gb_acc:.2%} RF acc={rf_acc:.2%}")
            return True
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return False

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict(self, df: pd.DataFrame) -> dict:
        """Return ensemble signal + confidence for the latest bar."""
        tech = get_signal_from_indicators(df)

        if not self.is_trained or len(df) < 52:
            return self._wrap(tech, {}, tech)

        try:
            feats = [f for f in FEATURES if f in df.columns]
            X = df.iloc[-1:][feats].fillna(0)

            gb_p = float(self.gb.predict_proba(X)[0][1])   # P(bullish)
            rf_p = float(self.rf.predict_proba(X)[0][1])

            ml_info = {"gb_prob": round(gb_p, 3), "rf_prob": round(rf_p, 3)}
            return self._wrap(tech, ml_info, tech, gb_p=gb_p, rf_p=rf_p)

        except Exception as e:
            logger.warning(f"ML predict error: {e}")
            return self._wrap(tech, {}, tech)

    def _wrap(self, tech: dict, ml_info: dict, base: dict,
              gb_p: float = 0.5, rf_p: float = 0.5) -> dict:

        # Tech layer
        t_sig  = tech.get("signal", "HOLD")
        t_conf = tech.get("confidence", 0.0)
        t_buy  = t_conf if t_sig == "BUY"  else 0.0
        t_sell = t_conf if t_sig == "SELL" else 0.0

        if self.is_trained:
            ml_avg = (gb_p * _GB_WEIGHT + rf_p * _RF_WEIGHT) / (_GB_WEIGHT + _RF_WEIGHT)
            ml_buy  = ml_avg * (_GB_WEIGHT + _RF_WEIGHT)
            ml_sell = (1 - ml_avg) * (_GB_WEIGHT + _RF_WEIGHT)
        else:
            ml_buy = ml_sell = 0.0

        total_buy  = t_buy  * _TECH_WEIGHT + ml_buy
        total_sell = t_sell * _TECH_WEIGHT + ml_sell

        if total_buy > total_sell and total_buy > 0.28:
            signal, conf = "BUY",  round(min(total_buy,  0.99), 3)
        elif total_sell > total_buy and total_sell > 0.28:
            signal, conf = "SELL", round(min(total_sell, 0.99), 3)
        else:
            signal, conf = "HOLD", round(max(total_buy, total_sell), 3)

        return {
            "signal":     signal,
            "confidence": conf,
            "buy_score":  round(total_buy, 3),
            "sell_score": round(total_sell, 3),
            "reasons":    base.get("reasons", []),
            "rsi":        base.get("rsi", 50),
            "atr":        base.get("atr", 0),
            "volume_ratio": base.get("volume_ratio", 1.0),
            "ml_trained": self.is_trained,
            "breakdown": {
                "technical": t_sig,
                **ml_info,
            },
        }
