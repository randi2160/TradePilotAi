"""
Morviq AI — Crypto Trading Engine

Features:
- Works backward from user's daily target (min/desired/stretch)
- Repeated crypto scalping with compounding
- State machine: Idle → Scanning → Sizing → OrderPending → PositionOpen
  → ExitPending → FundsRefreshing → ReadyForReentry → LockedProfitMode → StoppedForDay
- Checks non_marginable_buying_power AFTER every fill (never assumes funds are free)
- No PDT rules (crypto exempt)
- 24/7 trading (no market hours restriction)
- Profit locking: once min target hit, floor is set and never given back
"""
import asyncio
import logging
import time
from datetime   import datetime, timezone
from enum       import Enum
from typing     import Optional, List, Dict

from data.indicators import add_all_indicators

logger = logging.getLogger(__name__)

# Known Alpaca-tradeable crypto (fallback if dynamic fetch fails).
# This list is expanded at startup by _discover_alpaca_crypto().
ALPACA_TRADEABLE = {
    "BTC", "ETH", "LTC", "BCH", "DOGE",
    "LINK", "AAVE", "SOL", "XRP", "SHIB",
}

# Extended universe — coins that Alpaca has supported historically.
# _discover_alpaca_crypto() probes these + any new ones Alpaca adds.
_EXTENDED_CANDIDATES = [
    "BTC", "ETH", "LTC", "BCH", "DOGE", "LINK", "AAVE", "SOL", "XRP", "SHIB",
    "UNI", "SUSHI", "CRV", "MKR", "COMP", "GRT", "BAT", "YFI", "SNX",
    "AVAX", "MATIC", "DOT", "ATOM", "ALGO", "NEAR", "FIL", "ETC",
    "ADA", "MANA", "SAND", "APE", "LDO", "OP", "ARB", "PEPE", "WIF",
    "FET", "RNDR", "INJ", "TIA", "SEI", "SUI", "JUP", "BONK",
]

def _discover_alpaca_crypto() -> set:
    """Probe Alpaca to find all currently tradeable crypto pairs.
    Runs once at import time — adds ~2s to startup but gives us the full list."""
    global ALPACA_TRADEABLE
    try:
        import requests as _req
        import config
        headers = {
            "APCA-API-KEY-ID": config.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
        }
        # Fetch snapshots for all candidates — Alpaca returns data only for valid pairs
        symbols = ",".join(f"{t}/USD" for t in _EXTENDED_CANDIDATES)
        resp = _req.get(
            "https://data.alpaca.markets/v1beta3/crypto/us/snapshots",
            params={"symbols": symbols},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            found = set()
            for pair in resp.json().get("snapshots", {}).keys():
                ticker = pair.replace("/USD", "").replace("USD", "")
                if ticker:
                    found.add(ticker)
            if len(found) >= 5:  # sanity check — don't replace with near-empty set
                ALPACA_TRADEABLE = found
                logger.info(f"Discovered {len(found)} Alpaca crypto pairs: {sorted(found)}")
                return found
    except Exception as e:
        logger.warning(f"Crypto discovery failed (using {len(ALPACA_TRADEABLE)} known): {e}")
    return ALPACA_TRADEABLE

# Run discovery at import time
ALPACA_TRADEABLE = _discover_alpaca_crypto()
CRYPTO_UNIVERSE  = sorted(ALPACA_TRADEABLE)

# Binance scanner was removed: AWS US IPs get HTTP 451 geo-blocked.
# All crypto data now flows through Alpaca v1beta3 (broker.get_crypto_bars),
# which is free on the Basic tier and matches the execution feed.


class EngineState(Enum):
    IDLE              = "idle"
    SCANNING          = "scanning"
    CANDIDATE_RANKED  = "candidate_ranked"
    SIZING            = "sizing"
    ORDER_PENDING     = "order_pending"
    POSITION_OPEN     = "position_open"
    EXIT_PENDING      = "exit_pending"
    FUNDS_REFRESHING  = "funds_refreshing"
    READY_FOR_REENTRY = "ready_for_reentry"
    LOCKED_PROFIT     = "locked_profit_mode"
    STOPPED           = "stopped_for_day"
    ERROR             = "error"


class CryptoPosition:
    def __init__(self, symbol, side, qty, entry, stop, target, order_id=None):
        self.symbol        = symbol
        self.side          = side
        self.qty           = qty
        self.entry         = entry
        self.stop          = stop          # initial stop — gets raised as price climbs
        self.target        = target        # initial target
        self.order_id      = order_id
        self.opened_at     = datetime.now(timezone.utc)
        self.exit_order_id = None
        self.db_trade_id   = None
        # Trailing stop tracking
        self.peak_price    = entry         # highest price seen since entry
        self.trail_stop    = stop          # current trailing stop — rises with peak
        self.profit_locked = False         # True once we're in profit-protection mode

    def update_trailing_stop(self, current_price: float) -> bool:
        """
        Update trailing stop as price moves up.
        Returns True if stop was raised (for logging).

        Tiers:
          - Price up 0.3% from entry  → stop to break-even (entry)
          - Price up 0.5%             → trail at 60% of gain
          - Price up 1.0%             → trail at 70% of gain
          - Price up 2.0%+            → trail at 80% of gain (lock most profit)
        """
        if current_price <= self.peak_price:
            return False  # price not at new high, no update needed

        self.peak_price = current_price
        gain_pct = (current_price - self.entry) / self.entry * 100

        if gain_pct >= 2.0:
            # Up 2%+ — lock in 80% of gains
            new_stop = self.entry + (current_price - self.entry) * 0.80
            trail_label = "80% trail (2%+ gain)"
        elif gain_pct >= 1.0:
            # Up 1% — lock in 70% of gains
            new_stop = self.entry + (current_price - self.entry) * 0.70
            trail_label = "70% trail (1%+ gain)"
        elif gain_pct >= 0.5:
            # Up 0.5% — lock in 60% of gains
            new_stop = self.entry + (current_price - self.entry) * 0.60
            trail_label = "60% trail (0.5%+ gain)"
        elif gain_pct >= 0.3:
            # Up 0.3% — at least break even
            new_stop = self.entry * 1.001  # tiny buffer above entry
            trail_label = "break-even stop"
        else:
            return False  # not enough gain yet to move stop

        # Never move stop down
        if new_stop > self.trail_stop:
            self.trail_stop    = round(new_stop, 6)
            self.stop          = self.trail_stop   # keep stop in sync
            self.profit_locked = True
            return True
        return False

    def unrealized_pnl(self, current_price: float) -> float:
        if self.side == "BUY":
            return (current_price - self.entry) * self.qty
        return (self.entry - current_price) * self.qty


class CryptoEngine:
    """
    Goal-based crypto scalping engine.
    Initialize with user settings, then call run_cycle() repeatedly.
    """

    def __init__(
        self,
        broker,
        target_min:     float = 150,
        target_desired: float = 200,
        target_stretch: float = 250,
        max_daily_loss: float = 100,
        capital:        float = 5000,
        crypto_alloc:   float = 0.30,   # fraction of capital for crypto
        min_scalp_profit: float = 5,    # min $ per scalp (realistic for $2K budget)
        max_scalp_hold_min: int = 15,   # max hold before forced exit
        max_risk_pct:   float = 0.005,  # 0.5% risk per trade
        compound_mode:  bool  = True,
        min_probability: float = 0.55,   # minimum edge — below 55% is coin-flip territory after fees
        stop_at_min_target: bool = False,
        max_positions:  int   = 2,
        user_id:        int   = None,
        ensemble              = None,   # EnsembleModel — ML layer (optional)
    ):
        self.broker          = broker
        self.ensemble        = ensemble  # ML predictions boost/penalize heuristic score
        self.target_min      = target_min
        self.target_desired  = target_desired
        self.target_stretch  = target_stretch
        self.max_daily_loss  = max_daily_loss
        self.capital         = capital
        self.crypto_alloc    = crypto_alloc
        self.allocated_capital = capital * crypto_alloc

        self.min_scalp_profit    = min_scalp_profit
        self.max_scalp_hold_min  = max_scalp_hold_min
        self.max_risk_pct        = max_risk_pct
        self.compound_mode       = compound_mode
        self.min_probability     = min_probability
        self.stop_at_min_target  = stop_at_min_target
        self.max_positions       = max_positions

        # State
        self.state              = EngineState.IDLE
        self.realized_pnl       = 0.0
        self.locked_floor       = None
        self.open_positions: Dict[str, CryptoPosition] = {}
        self.compounded_gains   = 0.0
        self.stop_reason        = None
        self._last_error        = None
        self.last_account_state = {}
        self.cycle_count        = 0
        self.last_refresh       = 0
        self.trades_today       = 0
        self._scan_results      = []
        self._user_id           = user_id or 1  # per-user; fallback 1 for legacy
        self._reporter          = None

        # Milestone profit protection
        self.milestone_size_pct = 1.0   # starts at 100%, reduces as milestones hit
        self.milestone_label    = ""    # current milestone label for UI
        # Default milestones — overridden by set_milestones() from settings
        self._milestones = [
            {"threshold": 400, "floor_pct": 0.953, "size_pct": 0.00, "label": "🏆 $400 — Exits only"},
            {"threshold": 300, "floor_pct": 0.950, "size_pct": 0.40, "label": "🥇 $300 — 40% size"},
            {"threshold": 200, "floor_pct": 0.950, "size_pct": 0.50, "label": "🥈 $200 — 50% size"},
            {"threshold": 150, "floor_pct": 0.953, "size_pct": 0.60, "label": "🥉 $150 — 60% size"},
            {"threshold": 100, "floor_pct": 0.950, "size_pct": 0.75, "label": "✅ $100 — 75% size"},
        ]

    def set_milestones(self, milestones: list):
        """Update milestones from user settings."""
        if milestones:
            self._milestones = sorted(milestones, key=lambda x: x["threshold"], reverse=True)
            logger.info(f"Milestones configured: {[m['threshold'] for m in self._milestones]}")

        # ── Self-learning: track per-coin performance ─────────────────────
        # {ticker: {wins, losses, total_pnl, last_loss_time, skip_until}}
        self.coin_stats: Dict[str, dict] = {}
        self.consecutive_losses  = 0   # global loss streak
        self.last_trade_was_loss = False

        # Coins that are structurally bad for scalping (too cheap = spread kills profit)
        # Price threshold: skip coins under $1.00 — spread too large relative to move
        self.MIN_COIN_PRICE = 1.00

        # Skip DOGE/XRP for scalping — price too low, spread eats all profit
        # User can override in settings but these are bad actors from the data
        self.SKIP_FOR_SCALPING = {"DOGE", "SHIB"}  # penny coins — spread = loss

    # ── Account state ─────────────────────────────────────────────────────────

    def refresh_account(self) -> dict:
        """Always read live account state. Never use stale cache."""
        try:
            acct = self.broker.get_account()
            self.last_account_state = acct
            self.last_refresh = time.time()
            return acct
        except Exception as e:
            logger.error(f"CryptoEngine.refresh_account: {e}")
            return self.last_account_state

    def get_non_marginable_buying_power(self) -> float:
        """
        Return available cash for crypto trading.
        STRICTLY capped at configured crypto budget to never interfere with stock trading.
        """
        acct   = self.refresh_account()
        # Use non_marginable_buying_power (settled cash only)
        nmbp   = float(acct.get("non_marginable_buying_power") or acct.get("cash", 0))
        # Hard cap at configured crypto budget — NEVER exceed this
        budget = self.capital * self.crypto_alloc
        # Also account for already-open positions
        open_cost = sum(
            pos.qty * pos.entry
            for pos in self.open_positions.values()
        )
        available = max(0, min(nmbp, budget) - open_cost)
        return round(available, 2)

    def wait_for_fill(self, order_id: str, timeout: int = 30) -> bool:
        """Poll until order is filled or timeout. Returns True if filled."""
        for _ in range(timeout):
            try:
                order = self.broker.trading.get_order_by_id(order_id)
                if order.status == "filled":
                    return True
                if order.status in ("cancelled", "rejected", "expired"):
                    logger.warning(f"Order {order_id} {order.status}")
                    return False
            except Exception:
                pass
            time.sleep(1)
        return False

    # ── P&L tracking ──────────────────────────────────────────────────────────

    def remaining_to_min(self)     -> float: return max(0, self.target_min     - self.realized_pnl)
    def remaining_to_desired(self) -> float: return max(0, self.target_desired - self.realized_pnl)
    def remaining_to_stretch(self) -> float: return max(0, self.target_stretch - self.realized_pnl)

    def check_profit_lock(self):
        """
        Milestone-Based Profit Protection System.

        Milestones:  $100 → $150 → $200 → $300 → $400
        At each milestone:
          1. Set a hard floor (95% of milestone) — never give back more than 5%
          2. Reduce position size for new trades
          3. Keep trading but with smaller size
          4. If P&L drops below floor → close everything, lock profit, done

        Size reduction schedule:
          $0–$100:  normal size (100%)
          $100+:    75% size
          $150+:    60% size
          $200+:    50% size
          $300+:    40% size
          $400+:    STOP new entries (only manage open positions)
        """
        pnl = self.realized_pnl

        # Use user-configured milestones (set via UI, defaulting to built-in thresholds)
        for m in self._milestones:
            threshold = m["threshold"]
            floor_pct = m.get("floor_pct", 0.95)
            size_pct  = m.get("size_pct", 0.5)
            label     = m.get("label", f"${threshold} milestone")
            if pnl >= threshold:
                new_floor = round(threshold * floor_pct, 2)

                # Announce milestone if newly hit
                if self.locked_floor is None or new_floor > self.locked_floor:
                    old_floor = self.locked_floor or 0
                    self.locked_floor      = new_floor
                    self.milestone_size_pct = size_pct
                    self.milestone_label   = label

                    logger.info(
                        f"\n{'='*55}\n"
                        f"🎯 MILESTONE HIT: {label}\n"
                        f"   P&L: ${pnl:.2f} | Floor: ${new_floor:.2f} | "
                        f"Size: {size_pct:.0%}\n"
                        f"   Previous floor: ${old_floor:.2f}\n"
                        f"{'='*55}"
                    )

                    # Notify activity feed
                    _rep = getattr(self, '_reporter', None)
                    if _rep:
                        _rep.log("milestone", "PORTFOLIO",
                                 f"🎯 {label} — floor=${new_floor} size={size_pct:.0%}",
                                 {"pnl": pnl, "floor": new_floor, "size_pct": size_pct})
                break  # Only apply highest milestone

        # Trailing floor: also raise floor if P&L grows ABOVE current milestone
        # (continuous trailing between milestones)
        if self.locked_floor is not None and pnl > (self.locked_floor / 0.95):
            # Trail at 95% continuously
            candidate = round(pnl * 0.95, 2)
            if candidate > self.locked_floor:
                old = self.locked_floor
                self.locked_floor = candidate
                logger.info(f"🔒 Trailing floor raised: ${old:.2f} → ${self.locked_floor:.2f} (P&L ${pnl:.2f})")

    def get_size_multiplier(self) -> float:
        """Returns position size multiplier based on current milestone."""
        return getattr(self, 'milestone_size_pct', 1.0)

    def is_exits_only_mode(self) -> bool:
        """True when we've hit the top milestone and should only manage exits."""
        return getattr(self, 'milestone_size_pct', 1.0) == 0.0

    # ── Self-learning: per-coin performance tracking ──────────────────────────

    def _update_coin_stats(self, ticker: str, pnl: float):
        """Record trade result and learn from it."""
        import time
        if ticker not in self.coin_stats:
            self.coin_stats[ticker] = {
                "wins": 0, "losses": 0, "total_pnl": 0.0,
                "loss_streak": 0, "skip_until": 0,
            }
        s = self.coin_stats[ticker]
        s["total_pnl"] += pnl
        if pnl > 0:
            s["wins"]        += 1
            s["loss_streak"]  = 0
            self.consecutive_losses  = 0
            self.last_trade_was_loss = False
        else:
            s["losses"]      += 1
            s["loss_streak"] += 1
            self.consecutive_losses  += 1
            self.last_trade_was_loss  = True

            # Cooldown after consecutive losses on same coin
            if s["loss_streak"] >= 2:
                # 10 min cooldown per extra loss, max 60 min
                cooldown_min = min(60, s["loss_streak"] * 10)
                s["skip_until"] = time.time() + cooldown_min * 60
                logger.info(
                    f"🧠 Learning: {ticker} on {s['loss_streak']}-loss streak — "
                    f"cooling down {cooldown_min}min"
                )

        total = s["wins"] + s["losses"]
        win_rate = s["wins"] / total * 100 if total > 0 else 0
        logger.info(
            f"🧠 {ticker} stats: {s['wins']}W/{s['losses']}L "
            f"({win_rate:.0f}% WR) | streak={s['loss_streak']} | "
            f"pnl=${s['total_pnl']:+.2f}"
        )

    def _should_skip_coin(self, ticker: str, price: float) -> tuple:
        """
        Returns (skip: bool, reason: str).
        Filters out coins that are structurally bad or on cooldown.
        """
        import time

        # Skip penny coins — spread eats profit
        if ticker in self.SKIP_FOR_SCALPING:
            return True, f"{ticker} skipped — penny coin, spread kills profit"

        # Skip coins below price threshold
        if price < self.MIN_COIN_PRICE:
            return True, f"{ticker} @ ${price:.4f} too cheap — spread risk"

        # Skip BTC with tiny position — fees dominate
        if ticker == "BTC" and self.allocated_capital * 0.40 / price < 0.005:
            return True, f"BTC position too small for capital — skip"

        # Check cooldown from consecutive losses
        s = self.coin_stats.get(ticker, {})
        skip_until = s.get("skip_until", 0)
        if time.time() < skip_until:
            remaining = int((skip_until - time.time()) / 60)
            return True, f"{ticker} cooling down — {remaining}min left after loss streak"

        # Check overall win rate — if < 30% after 5+ trades, reduce to low priority
        total = s.get("wins", 0) + s.get("losses", 0)
        if total >= 5:
            wr = s.get("wins", 0) / total
            if wr < 0.30:
                return True, f"{ticker} win rate {wr:.0%} too low — skipping today"

        return False, ""

    def should_stop(self) -> Optional[str]:
        """Check all stop conditions."""
        pnl = self.realized_pnl

        if pnl <= -self.max_daily_loss:
            return f"Max daily loss reached: ${pnl:.2f}"

        # Only stop on floor breach — NOT on hitting target (keep trading!)
        if self.locked_floor is not None and pnl < self.locked_floor:
            return (
                f"Trailing floor triggered — P&L ${pnl:.2f} dropped below "
                f"floor ${self.locked_floor:.2f}. Gains protected ✅"
            )

        # Hard stop only if explicitly configured
        if self.stop_at_min_target and pnl >= self.target_stretch:
            return f"Stretch target ${self.target_stretch} hit and stop_at_target enabled"

        nbp = self.get_non_marginable_buying_power()
        if nbp < 50:
            return f"Buying power too low: ${nbp:.2f}"

        return None

    # ── Candidate scoring ──────────────────────────────────────────────────────

    def score_crypto_candidate(self, symbol: str, bars) -> dict:
        """Score a crypto candidate 0–100. Higher = better setup."""
        if bars is None or len(bars) < 20:
            return {"symbol": symbol, "score": 0, "valid": False}

        try:
            import pandas as pd
            import numpy as np

            closes  = bars["close"].values
            highs   = bars["high"].values
            lows    = bars["low"].values
            volumes = bars["volume"].values

            price    = float(closes[-1])
            atr      = float(np.mean(np.abs(np.diff(closes[-14:]))))
            if atr == 0:
                atr = price * 0.005

            # Momentum (last 5 bars vs prior 5)
            momentum = (closes[-1] - closes[-6]) / closes[-6] * 100

            # Volume ratio
            avg_vol  = float(np.mean(volumes[-20:]))
            vol_ratio= float(volumes[-1]) / avg_vol if avg_vol > 0 else 1.0

            # Trend (EMA8 vs EMA21)
            def ema(arr, n):
                k = 2 / (n + 1)
                e = arr[0]
                for v in arr[1:]:
                    e = v * k + e * (1 - k)
                return e

            ema8  = ema(closes[-30:], 8)
            ema21 = ema(closes[-30:], 21)
            trend_up = ema8 > ema21

            # Volatility score (moderate = good for scalping)
            atr_pct    = atr / price * 100
            vol_score  = min(100, max(0, (atr_pct - 0.3) / 1.5 * 100)) if atr_pct < 2 else 100 - (atr_pct - 2) * 20

            # Expected move (1.5 ATR target)
            expected_move = atr * 1.5
            # Use configured crypto budget for position sizing during scan
            # (live buying power checked again at actual order time)
            scan_capital  = self.allocated_capital if self.allocated_capital > 0 else self.capital * self.crypto_alloc
            max_size      = scan_capital * 0.3
            units         = max_size / price if price > 0 else 0
            exp_profit    = units * expected_move

            # ── Trend strength: EMA slope + higher-lows detection ──────
            # A flat/declining 8-bar EMA slope means the short-term trend
            # is dead or bearish — no business going long.
            ema8_prev  = ema(closes[-31:-1], 8) if len(closes) > 31 else ema8
            ema_slope  = (ema8 - ema8_prev) / ema8_prev * 100 if ema8_prev > 0 else 0.0
            # Count lower-lows in last 5 bars (classic downtrend signal)
            lower_lows = sum(1 for i in range(-4, 0) if lows[i] < lows[i-1])

            # ── Hard gate: do NOT buy into a clear downtrend ───────────
            # If EMA8 < EMA21 AND momentum is negative AND we see 3+ lower
            # lows in the last 5 bars, this is a falling knife. Mark invalid.
            downtrend = (not trend_up) and (momentum < 0) and (lower_lows >= 2)

            # Composite score
            score = 0
            score += min(30, max(0, momentum * 5 + 15))        # momentum (0-30)
            score += min(20, vol_ratio * 10)                    # volume (0-20)
            score += 20 if trend_up else 0                      # trend (0-20) — weighted MORE
            score += min(15, vol_score / 6.67)                  # volatility (0-15)
            score += 15 if exp_profit >= self.min_scalp_profit else 0  # profitability (0-15)

            # Penalize downtrend and negative momentum harder
            if not trend_up:
                score -= 10
            if momentum < -0.5:
                score -= 10  # falling fast — extra penalty

            # ── ML Ensemble boost/penalty (±15 points) ────────────────
            ml_signal   = None
            ml_prob     = None
            ml_trained  = False
            if self.ensemble and self.ensemble.is_trained and len(bars) >= 52:
                try:
                    df_ml = add_all_indicators(bars.copy())
                    if not df_ml.empty:
                        pred       = self.ensemble.predict(df_ml)
                        ml_signal  = pred.get("signal", "HOLD")
                        ml_prob    = pred.get("confidence", 0.5)
                        ml_trained = pred.get("ml_trained", False)
                        # BUY signal with high confidence → boost up to +15
                        if ml_signal == "BUY" and ml_prob >= 0.5:
                            ml_boost = min(15, (ml_prob - 0.5) * 30)  # 0.5→0, 1.0→+15
                            score += ml_boost
                            logger.debug(f"ML {symbol}: BUY conf={ml_prob:.2f} → +{ml_boost:.1f}")
                        # SELL signal → penalize up to -15
                        elif ml_signal == "SELL" and ml_prob >= 0.5:
                            ml_penalty = min(15, (ml_prob - 0.5) * 30)
                            score -= ml_penalty
                            logger.debug(f"ML {symbol}: SELL conf={ml_prob:.2f} → -{ml_penalty:.1f}")
                        # HOLD or low-conf → no change
                except Exception as e:
                    logger.debug(f"ML score_crypto {symbol}: {e}")

            score = max(0, score)

            # Probability estimate
            probability = min(0.95, max(0.3, score / 100))

            return {
                "symbol":        symbol,
                "price":         price,
                "score":         round(score, 1),
                "probability":   round(probability, 3),
                "momentum":      round(momentum, 3),
                "vol_ratio":     round(vol_ratio, 2),
                "atr":           round(atr, 6),
                "atr_pct":       round(atr_pct, 3),
                "trend_up":      trend_up,
                "ema_slope":     round(ema_slope, 3),
                "lower_lows":    lower_lows,
                "downtrend":     downtrend,
                "expected_move": round(expected_move, 6),
                "exp_profit":    round(exp_profit, 2),
                "ml_signal":     ml_signal,
                "ml_confidence": ml_prob,
                "ml_trained":    ml_trained,
                # HARD GATE: invalid if downtrend OR below confidence threshold
                "valid":         (not downtrend) and probability >= self.min_probability and exp_profit > 0,
            }

        except Exception as e:
            logger.error(f"score_crypto_candidate {symbol}: {e}")
            return {"symbol": symbol, "score": 0, "valid": False}

    # ── Position sizing ────────────────────────────────────────────────────────

    def calculate_size(self, candidate: dict) -> dict:
        """
        Work backward from target to find position size.
        Uses actual available cash, not configured budget.
        """
        price = candidate.get("price", 0)
        atr   = candidate.get("atr", price * 0.005)
        if price <= 0:
            return {"qty": 0, "reason": "Invalid price"}

        # Always use LIVE buying power — what's actually free right now
        nbp       = self.get_non_marginable_buying_power()
        available = nbp  # don't add compounded_gains — cash is cash

        if available < 10:
            return {"qty": 0, "reason": f"Insufficient cash: ${available:.2f} available"}

        expected_move = candidate.get("expected_move", atr * 1.5)
        if expected_move <= 0:
            expected_move = price * 0.005

        # Stop at 2× ATR — wider than old 1.5× to avoid noise stopouts.
        # BTC can easily move 1.5× ATR on a random 1-min candle; 2× gives
        # breathing room while still capping risk.
        min_stop_dist = max(price * 0.002, 0.01)  # minimum 0.2% (was 0.1%)
        stop_dist     = max(atr * 2.0, min_stop_dist)
        stop          = round(price - stop_dist, 6)
        target        = round(price + expected_move, 6)

        # Ensure stop < price - 0.01 (Alpaca bracket requirement)
        if price - stop < 0.01:
            stop = round(price - 0.01, 6)

        # Use up to 40% of available cash per trade, reduced by milestone multiplier
        size_mult = self.get_size_multiplier()
        max_spend = available * 0.40 * size_mult
        if size_mult < 1.0:
            logger.info(f"  📉 Milestone size reduction: {size_mult:.0%} of normal")
        bp_units  = max_spend / price if price > 0 else 0

        # Risk-based: max 0.5% of configured capital
        max_risk_usd = self.capital * self.max_risk_pct
        risk_units   = max_risk_usd / stop_dist if stop_dist > 0 else 0

        # Target-based: units to hit min profit
        target_units = self.min_scalp_profit / expected_move if expected_move > 0 else 0

        qty  = min(target_units, risk_units, bp_units)
        qty  = max(0.01, round(qty, 4))
        cost = qty * price

        # Hard check: can't spend more than available
        if cost > available:
            qty  = round((available * 0.95) / price, 4)  # 95% of available
            cost = qty * price

        if cost > available:
            return {"qty": 0, "reason": f"Cost ${cost:.2f} > available ${available:.2f}"}

        exp_profit = qty * expected_move

        if exp_profit < 0.10:
            return {"qty": 0, "reason": f"Expected profit ${exp_profit:.2f} too low"}

        logger.info(
            f"  Sized {candidate.get('symbol')}: qty={qty:.4f} "
            f"cost=${cost:.2f} exp_profit=${exp_profit:.2f} "
            f"stop=${stop:.4f}(-{stop_dist:.4f}) target=${target:.4f} "
            f"avail=${available:.2f}"
        )

        return {
            "qty":        qty,
            "cost":       round(cost, 2),
            "stop":       stop,
            "target":     target,
            "stop_dist":  round(stop_dist, 6),
            "exp_profit": round(exp_profit, 2),
            "reason":     "sized",
        }

    # ── Main cycle ─────────────────────────────────────────────────────────────

    async def run_cycle(self) -> dict:
        """
        One full trading cycle. Call this in a loop.
        Returns status dict with current state.
        """
        self.cycle_count += 1

        # Reset error state so we keep retrying
        if self.state == EngineState.ERROR:
            self.state = EngineState.IDLE

        # Check stop conditions first
        stop_reason = self.should_stop()
        if stop_reason:
            self.state       = EngineState.STOPPED
            self.stop_reason = stop_reason
            logger.info(f"CryptoEngine STOPPED: {stop_reason}")
            return self.status()

        # Manage open positions
        await self._manage_positions()

        # Skip scanning if max positions reached
        if len(self.open_positions) >= self.max_positions:
            return self.status()

        # Update profit lock and check milestones
        self.check_profit_lock()
        self.state = EngineState.LOCKED_PROFIT if self.locked_floor else self.state

        # EXITS ONLY MODE — hit top milestone, protect all gains
        if self.is_exits_only_mode():
            logger.info(
                f"🏆 EXITS ONLY — P&L ${self.realized_pnl:.2f} above top milestone. "
                f"Managing {len(self.open_positions)} open positions, no new entries."
            )
            await self._manage_positions()
            return self.status()

        # Scan and score
        self.state    = EngineState.SCANNING
        candidates    = await self._scan_candidates()

        # Store scan results — convert numpy types to Python native for JSON serialization
        self._scan_results = [
            {
                "symbol":   str(c.get("symbol", "")),
                "score":    float(round(c.get("score", 0), 0)),
                "prob":     float(round(c.get("probability", 0) * 100, 0)),
                "valid":    bool(c.get("valid", False)),
                "price":    float(c.get("price", 0)),
                "momentum": float(round(c.get("momentum", 0), 2)),
            }
            for c in candidates[:8]
        ]

        if not candidates:
            self.state = EngineState.IDLE
            return self.status()

        # Filter to Alpaca-tradeable coins
        tradeable = [c for c in candidates if c.get("ticker", "") in ALPACA_TRADEABLE]

        # Filter out already-held symbols
        already_held = set(sym.split("/")[0] for sym in self.open_positions)
        tradeable = [c for c in tradeable if c.get("ticker") not in already_held]

        if not tradeable:
            logger.info(f"All tradeable candidates already held: {already_held} — waiting for exit")
            self.state = EngineState.POSITION_OPEN
            return self.status()

        # ── Self-learning filter: skip bad coins and penny coins ──────────
        filtered = []
        for c in tradeable:
            skip, reason = self._should_skip_coin(c.get("ticker",""), c.get("price", 0))
            if skip:
                logger.info(f"  🚫 {c.get('ticker')}: {reason}")
            else:
                filtered.append(c)
        tradeable = filtered if filtered else tradeable  # fallback if all filtered

        # ── Global loss streak guard ──────────────────────────────────────
        # After consecutive losses, tighten confidence requirement progressively
        min_conf = self.min_probability
        if self.consecutive_losses >= 5:
            logger.info(f"⚠️  {self.consecutive_losses} consecutive losses — pausing 15 min to let market settle")
            import time; time.sleep(900)
            self.consecutive_losses = 0
        elif self.consecutive_losses >= 3:
            min_conf = max(self.min_probability, 0.65)  # 65% bar after 3 losses — don't trade noise
            logger.info(f"⚠️  {self.consecutive_losses} losses in a row — raising confidence to {min_conf:.0%}")
        elif self.consecutive_losses >= 2:
            min_conf = max(self.min_probability, 0.60)
            logger.info(f"⚠️  {self.consecutive_losses} losses — raising confidence to {min_conf:.0%}")

        # Valid = meets confidence threshold (raised after loss streaks)
        valid_tradeable = [c for c in tradeable if c.get("valid") and
                          c.get("probability", c.get("confidence", 0) / 100) >= min_conf]

        if not valid_tradeable:
            # Only pick fallback if confidence streak is clean
            if self.consecutive_losses < 2:
                best_available = sorted(tradeable, key=lambda x: x["score"], reverse=True)[0]
                # Raise the fallback score bar — 60+ means real setup, not noise
                if best_available.get("score", 0) >= 60:
                    logger.info(
                        f"🎯 No coin meets threshold — trading best available: "
                        f"{best_available.get('ticker')} score={best_available.get('score',0):.0f}"
                    )
                    valid_tradeable = [best_available]
                else:
                    logger.info("Market quiet — no quality setup, sitting out")
                    self.state = EngineState.IDLE
                    return self.status()
            else:
                logger.info(f"Loss streak {self.consecutive_losses} — waiting for high-quality setup only")
                self.state = EngineState.IDLE
                return self.status()

        # Best tradeable candidate
        self.state = EngineState.CANDIDATE_RANKED
        best       = sorted(valid_tradeable, key=lambda x: x["score"], reverse=True)[0]
        logger.info(f"🎯 Trading {best.get('symbol')} score={best.get('score',0):.0f}")

        # Size it
        self.state    = EngineState.SIZING
        sizing        = self.calculate_size(best)
        if sizing["qty"] <= 0:
            logger.info(f"Sizing rejected: {sizing.get('reason')}")
            self.state = EngineState.IDLE
            return self.status()

        # Place order — market only, software-managed stop/target
        self.state = EngineState.ORDER_PENDING
        symbol     = best["symbol"]
        qty        = sizing["qty"]
        ticker     = symbol.split("/")[0]

        try:
            # Simple market order — bracket fails due to yfinance/Alpaca price gap
            order = self.broker.place_market_order(ticker, qty, "BUY")
            if "error" in order:
                logger.error(f"Crypto order failed: {order['error']}")
                self._last_error = order["error"]
                self.state = EngineState.IDLE
                return self.status()

            order_id = order.get("id", "")
            logger.info(f"Crypto market order placed: {ticker} qty={qty}")

            # Wait for fill
            filled = self.wait_for_fill(order_id, timeout=20)
            if not filled:
                logger.warning(f"Order {order_id} not filled in time")
                self.state = EngineState.IDLE
                return self.status()

            # Get actual fill price from Alpaca
            actual_price = best["price"]
            try:
                order_obj = self.broker.trading.get_order_by_id(order_id)
                if order_obj.filled_avg_price:
                    actual_price = float(order_obj.filled_avg_price)
            except Exception:
                pass

            # Stop/target anchored to ACTUAL fill price but using the ATR-based
            # distances the scanner produced. Previously we forced a symmetric
            # ±0.3% bracket here, which ignored the scanner's expected_move and
            # capped winners while letting losers run to 0.3% — asymmetric loss
            # profile. Now honor sizing["stop_dist"] and candidate["expected_move"].
            stop_dist     = float(sizing.get("stop_dist") or 0.0)
            expected_move = float(best.get("expected_move") or 0.0)

            # Fallbacks if either is missing/zero
            if stop_dist <= 0:
                stop_dist = max(actual_price * 0.003, 0.01)
            if expected_move <= 0:
                expected_move = stop_dist * 1.5

            # Alpaca minimum: stop at least 0.1% or $0.01 below entry
            min_stop_dist = max(actual_price * 0.001, 0.01)
            stop_dist     = max(stop_dist, min_stop_dist)

            stop   = round(actual_price - stop_dist, 6)
            target = round(actual_price + expected_move, 6)
            rr     = (expected_move / stop_dist) if stop_dist > 0 else 0
            logger.info(
                f"Fill: {ticker} @ ${actual_price:.4f} | "
                f"stop=${stop:.4f} (-{stop_dist:.4f}) "
                f"target=${target:.4f} (+{expected_move:.4f}) "
                f"R:R={rr:.2f}"
            )

            # Refresh account after fill
            self.state = EngineState.FUNDS_REFRESHING
            self.refresh_account()

            # Record position — use actual_price (fill), NOT best["price"]
            # (scanner cache). best["price"] was the market price when the
            # scanner ranked this coin — could be minutes stale by the time
            # the order fills. actual_price is from Alpaca's filled_avg_price.
            self.state = EngineState.POSITION_OPEN
            pos = CryptoPosition(
                symbol   = symbol,
                side     = "BUY",
                qty      = qty,
                entry    = actual_price,
                stop     = stop,
                target   = target,
                order_id = order_id,
            )
            self.open_positions[symbol] = pos
            self.trades_today += 1
            logger.info(f"✅ Crypto position: {symbol} qty={qty} entry=${actual_price:.4f} target=${target:.4f} stop=${stop:.4f}")

            # ── Save to database + activity feed ─────────────────────────
            try:
                from database.database import SessionLocal
                from services.trade_service import TradeService
                from services.daily_report  import DailyReporter
                db      = SessionLocal()
                svc     = TradeService(db=db, user_id=self._user_id)
                db_trade = svc.open_trade(
                    symbol       = ticker,
                    side         = "BUY",
                    qty          = qty,
                    entry_price  = float(actual_price),
                    stop_loss    = float(stop),
                    take_profit  = float(target),
                    confidence   = float(best.get("probability", 0)),
                    signal_reasons = [f"Crypto scalp | score={best.get('score',0):.0f}"],
                    order_id     = order_id,
                )
                pos.db_trade_id = db_trade.id
                db.close()
                # Log to activity feed
                _reporter = getattr(self, '_reporter', None)
                if _reporter:
                    _reporter.log_entry(ticker, "BUY", qty, float(actual_price),
                                        float(stop), float(target), float(best.get("probability", 0)))
            except Exception as e:
                logger.warning(f"Crypto DB save error: {e}")

        except Exception as e:
            logger.error(f"CryptoEngine order error: {e}")
            self._last_error = str(e)
            self.state = EngineState.ERROR

        return self.status()

    async def _scan_candidates(self) -> List[dict]:
        """
        Scan the tradeable universe for momentum setups.

        Primary: Alpaca v1beta3 /crypto/us/bars — FREE, real-time, same feed
        the executor uses. Parallel fetch across the universe (10 coins).
        Fallback: yfinance batch — only used if Alpaca returns nothing for a
        coin (e.g., transient outage). 15-min delayed but keeps us scanning.

        Binance was removed: AWS US IPs get HTTP 451 geo-blocked and the
        retries added latency for no benefit.
        """
        import asyncio, math, pandas as pd

        loop = asyncio.get_event_loop()
        t0   = loop.time()

        # ── Primary: Alpaca parallel fetch ─────────────────────────────────────
        def _fetch_one(ticker: str):
            try:
                bars = self.broker.get_crypto_bars(ticker, "1Min", 60)
                if bars is None or bars.empty or len(bars) < 10:
                    return (ticker, None)
                return (ticker, bars)
            except Exception as e:
                logger.debug(f"  Alpaca fetch {ticker}: {e}")
                return (ticker, None)

        # Run all fetches in parallel via the thread pool (I/O bound HTTP calls)
        tasks   = [loop.run_in_executor(None, _fetch_one, t) for t in CRYPTO_UNIVERSE]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        bars_map = {t: b for (t, b) in results if b is not None}
        alpaca_hits = len(bars_map)
        elapsed     = loop.time() - t0
        logger.info(f"🤖 Alpaca crypto scan: {alpaca_hits}/{len(CRYPTO_UNIVERSE)} coins in {elapsed:.1f}s")

        # ── Fallback: yfinance batch for any coins Alpaca missed ───────────────
        missing = [t for t in CRYPTO_UNIVERSE if t not in bars_map]
        if missing:
            def _yf_batch():
                try:
                    import yfinance as yf
                    yf_syms = [f"{t}-USD" for t in missing]
                    df = yf.download(yf_syms, period="1d", interval="1m",
                                     progress=False, auto_adjust=True, group_by="ticker")
                    fallback = {}
                    for ticker in missing:
                        yf_sym = f"{ticker}-USD"
                        try:
                            if isinstance(df.columns, pd.MultiIndex):
                                lvl0 = df.columns.get_level_values(0)
                                if yf_sym not in lvl0:
                                    continue
                                sub = df[yf_sym].copy()
                            else:
                                sub = df.copy() if len(missing) == 1 else None
                                if sub is None:
                                    continue
                            sub.columns = [c.lower() for c in sub.columns]
                            if "close" not in sub.columns:
                                continue
                            sub = sub.dropna(subset=["close"])
                            if len(sub) < 10:
                                continue
                            last_price = float(sub["close"].iloc[-1])
                            if math.isnan(last_price) or last_price <= 0 or math.isinf(last_price):
                                continue
                            fallback[ticker] = sub
                        except Exception:
                            continue
                    return fallback
                except Exception as e:
                    logger.debug(f"yfinance fallback batch: {e}")
                    return {}

            yf_map = await loop.run_in_executor(None, _yf_batch)
            if yf_map:
                logger.info(f"🔁 yfinance fallback recovered {len(yf_map)}/{len(missing)} coins")
                bars_map.update(yf_map)

        # ── Score every coin we have bars for ──────────────────────────────────
        candidates: List[dict] = []
        for ticker, bars in bars_map.items():
            try:
                symbol = f"{ticker}/USD"
                price  = float(bars["close"].iloc[-1])
                if math.isnan(price) or price <= 0:
                    continue
                scored = self.score_crypto_candidate(symbol, bars)
                scored["ticker"] = ticker
                scored["price"]  = price
                scored["source"] = "alpaca" if ticker in {t for (t, b) in results if b is not None} else "yfinance"
                candidates.append(scored)
            except Exception as e:
                logger.debug(f"  Score {ticker}: {e}")

        candidates.sort(key=lambda x: x["score"], reverse=True)

        # Log top 8 movers (all coins, for visibility)
        for c in candidates[:8]:
            tradeable = "✓" if c["ticker"] in ALPACA_TRADEABLE else "✗"
            logger.info(f"  {tradeable} {c['ticker']}: score={c.get('score',0):.0f} valid={c.get('valid')} ${c.get('price',0):.4f}")

        if candidates:
            best = candidates[0]
            logger.info(f"✅ Best overall: {best.get('symbol')} score={best.get('score',0):.0f}")

            # Log top 3 to activity feed — sanitize all values first
            _rep = getattr(self, '_reporter', None)
            if _rep:
                top3 = candidates[:3]
                summary = " | ".join(
                    f"{'✓' if c['ticker'] in ALPACA_TRADEABLE else '✗'}{c['ticker']} "
                    f"${float(c.get('price',0)):.4f} score={int(c.get('score',0))}"
                    for c in top3
                )
                _rep.log("scan", str(best.get("ticker","CRYPTO")),
                         f"🤖 Crypto scan: {summary}",
                         {
                             "top_coin":       str(best.get("symbol","")),
                             "score":          int(best.get("score", 0)),
                             "valid":          bool(best.get("valid", False)),
                             "coins_scanned":  int(len(candidates)),
                             "tradeable_valid": int(len([c for c in candidates
                                                  if c.get("valid") and c["ticker"] in ALPACA_TRADEABLE]))
                         })
        else:
            logger.warning("⚠️  0 candidates — batch fetch returned no data")
        return candidates

    async def _manage_positions(self):
        """Check exits for all open positions using trailing stops."""
        for sym, pos in list(self.open_positions.items()):
            ticker = sym.split("/")[0]
            try:
                # Priority: Alpaca crypto quote → Alpaca stock-style quote fallback
                current_price = 0.0
                if hasattr(self.broker, "get_latest_crypto_price"):
                    current_price = self.broker.get_latest_crypto_price(ticker)
                if current_price <= 0:
                    current_price = self.broker.get_latest_price(ticker)
                if current_price <= 0:
                    continue

                upnl     = pos.unrealized_pnl(current_price)
                upnl_pct = (current_price - pos.entry) / pos.entry * 100
                held_min = (datetime.now(timezone.utc) - pos.opened_at).total_seconds() / 60

                # Update trailing stop — raises floor as price climbs
                stop_raised = pos.update_trailing_stop(current_price)
                if stop_raised:
                    locked_pnl = pos.unrealized_pnl(pos.trail_stop)
                    logger.info(
                        f"🔒 Trail stop raised: {sym} | "
                        f"price=${current_price:.4f} peak=${pos.peak_price:.4f} | "
                        f"new stop=${pos.trail_stop:.4f} | "
                        f"locked P&L=${locked_pnl:+.2f}"
                    )

                should_exit = False
                exit_reason = ""

                # 1. Trailing stop hit (price dropped from peak)
                if current_price <= pos.trail_stop and pos.profit_locked:
                    should_exit = True
                    exit_reason = (
                        f"Trailing stop hit ${pos.trail_stop:.4f} | "
                        f"peak was ${pos.peak_price:.4f} | "
                        f"P&L ${upnl:+.2f}"
                    )

                # 2. Initial stop hit (before profit lock kicks in)
                elif current_price <= pos.stop and not pos.profit_locked:
                    should_exit = True
                    exit_reason = f"Stop loss hit ${pos.stop:.4f} | P&L ${upnl:+.2f}"

                # 3. Target hit — take profit and look for re-entry
                elif current_price >= pos.target:
                    should_exit = True
                    exit_reason = f"Target hit ${pos.target:.4f} | P&L ${upnl:+.2f} ✅"

                # 4. Time stop — don't hold longer than max_scalp_hold_min
                elif held_min >= self.max_scalp_hold_min:
                    should_exit = True
                    exit_reason = f"Time stop {held_min:.0f}m | P&L ${upnl:+.2f}"

                else:
                    # Still in trade — log status every ~5 min
                    if int(held_min) % 5 == 0 and held_min > 0:
                        lock_str = f" | 🔒 stop=${pos.trail_stop:.4f}" if pos.profit_locked else ""
                        logger.info(
                            f"  📈 {sym}: ${current_price:.4f} | "
                            f"P&L ${upnl:+.2f} ({upnl_pct:+.2f}%) | "
                            f"held {held_min:.0f}m{lock_str}"
                        )

                if should_exit:
                    logger.info(f"🚪 Exiting {sym}: {exit_reason}")
                    await self._exit_position(sym, pos, current_price, exit_reason)

            except Exception as e:
                logger.error(f"Manage position {sym}: {e}")

    async def _exit_position(self, sym: str, pos: CryptoPosition, price: float, reason: str):
        """Exit a position, wait for fill, then refresh account."""
        self.state = EngineState.EXIT_PENDING
        ticker     = sym.split("/")[0]
        try:
            self.broker.close_position(ticker)
            filled = True  # close_position is synchronous

            # CRITICAL: refresh account after sell, before any re-entry
            self.state = EngineState.FUNDS_REFRESHING
            self.refresh_account()

            pnl = pos.unrealized_pnl(price)
            self.realized_pnl += pnl

            if self.compound_mode and pnl > 0:
                self.compounded_gains += pnl

            # ── Self-learning: record result for this coin ────────────────
            self._update_coin_stats(ticker, pnl)

            del self.open_positions[sym]
            self.state = EngineState.READY_FOR_REENTRY
            logger.info(f"Exit {sym}: {reason} | P&L ${pnl:+.2f} | Total ${self.realized_pnl:.2f}")

            # ── Save closed trade to DB + activity feed ───────────────────
            try:
                from database.database import SessionLocal
                from services.trade_service import TradeService
                db = SessionLocal()
                svc = TradeService(db=db, user_id=self._user_id)
                trade_id = getattr(pos, "db_trade_id", None)
                if trade_id:
                    svc.close_trade(trade_id=trade_id, exit_price=price, reason=reason)
                else:
                    # No open trade record — just log a closed one directly
                    from database.models import Trade
                    from datetime import date as _date
                    t = Trade(
                        user_id     = self._user_id,
                        symbol      = sym.split("/")[0],
                        side        = "BUY",
                        qty         = pos.qty,
                        entry_price = pos.entry,
                        exit_price  = price,
                        pnl         = round(pnl, 2),
                        net_pnl     = round(pnl, 2),
                        status      = "closed",
                        trade_date  = str(_date.today()),
                        opened_at   = pos.opened_at,
                        setup_type  = "crypto_scalp",
                    )
                    db.add(t)
                    db.commit()
                db.close()
                _reporter = getattr(self, '_reporter', None)
                if _reporter:
                    _reporter.log_exit(sym.split("/")[0], "BUY", pos.qty,
                                       pos.entry, price, pnl, reason)
            except Exception as e:
                logger.warning(f"Crypto DB close error: {e}")

        except Exception as e:
            logger.error(f"Exit position {sym}: {e}")

    def status(self) -> dict:
        import numpy as _np
        import math

        def _safe(v):
            """Convert numpy scalars and NaN/Inf to JSON-safe values."""
            if isinstance(v, (_np.bool_, _np.bool8 if hasattr(_np, 'bool8') else _np.bool_)):
                return bool(v)
            if isinstance(v, _np.integer):
                return int(v)
            if isinstance(v, _np.floating):
                v = float(v)
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return 0.0
            return v

        def _safe_round(v, n=2):
            try:
                f = float(v)
                if math.isnan(f) or math.isinf(f):
                    return 0.0
                return round(f, n)
            except Exception:
                return 0.0

        bp_raw = float(self.last_account_state.get("non_marginable_buying_power",
                       self.last_account_state.get("cash", 0))) if self.last_account_state else 0.0
        budget = round(self.capital * self.crypto_alloc, 2)

        # Build coin stats summary for UI
        coin_summary = {}
        for ticker, s in self.coin_stats.items():
            total = s["wins"] + s["losses"]
            coin_summary[ticker] = {
                "wins":       s["wins"],
                "losses":     s["losses"],
                "win_rate":   round(s["wins"] / total * 100, 1) if total > 0 else 0,
                "total_pnl":  _safe_round(s["total_pnl"]),
                "loss_streak": s["loss_streak"],
            }

        return {
            "state":             self.state.value,
            "realized_pnl":      _safe_round(self.realized_pnl),
            "compounded_gains":  _safe_round(self.compounded_gains),
            "locked_floor":      _safe_round(self.locked_floor) if self.locked_floor else None,
            "milestone_size_pct": self.milestone_size_pct,
            "milestone_label":   self.milestone_label,
            "exits_only_mode":   self.is_exits_only_mode(),
            "remaining_to_min":  _safe_round(self.remaining_to_min()),
            "remaining_to_desired": _safe_round(self.remaining_to_desired()),
            "open_positions":    len(self.open_positions),
            "trades_today":      self.trades_today,
            "stop_reason":       self.stop_reason,
            "last_error":        self._last_error,
            "cycle":             self.cycle_count,
            "min_probability":   self.min_probability,
            "consecutive_losses": self.consecutive_losses,
            "buying_power":      _safe_round(min(bp_raw, budget)) if bp_raw else budget,
            "crypto_budget":     budget,
            "coin_stats":        coin_summary,
            "scan_results": [
                {k: _safe(v) for k, v in s.items()}
                for s in self._scan_results
                if _safe(s.get("price", 0)) > 0  # skip NaN price entries
            ],
            "open_position_list": [
                {
                    "symbol": sym,
                    "qty":    float(pos.qty),
                    "entry":  float(pos.entry),
                    "stop":   float(pos.stop),
                    "target": float(pos.target),
                    "side":   str(pos.side),
                }
                for sym, pos in self.open_positions.items()
            ],
        }