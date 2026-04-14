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

logger = logging.getLogger(__name__)

# Full scan universe — used for momentum discovery (yfinance, not traded)
# Full universe — scanned via Binance every cycle
CRYPTO_UNIVERSE = [
    "BTC", "ETH", "SOL", "DOGE", "LINK", "AAVE",
    "LTC", "BCH", "AVAX", "XRP", "ADA", "DOT",
    "ATOM", "ALGO", "NEAR", "SAND", "MANA",
    "CRV", "SUSHI", "BAT", "ZEC", "DASH", "ETC",
    "SHIB", "FIL",
]

# Alpaca paper trading ONLY supports these crypto symbols
ALPACA_TRADEABLE = {
    "BTC", "ETH", "LTC", "BCH", "DOGE",
    "LINK", "AAVE", "SOL", "XRP", "SHIB",
}

# Import Binance scanner (fast, free, no auth)
try:
    from data.binance_scanner import scan_all_coins as _binance_scan, get_live_price as _binance_price
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    logger.warning("Binance scanner not available — falling back to yfinance")


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
        min_probability: float = 0.40,   # lowered from 0.60 — crypto is volatile enough
        stop_at_min_target: bool = False,
        max_positions:  int   = 2,
    ):
        self.broker          = broker
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
        self._user_id           = 1
        self._reporter          = None

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
        Trailing Profit Lock — keeps trading as long as market is good,
        but never gives back more than trail_pct of peak gains.

        How it works:
        - Once min target hit: lock floor at 97% of min target
        - As P&L grows BEYOND target: floor trails at 94% of peak
        - If P&L drops to floor → stop and protect all gains above floor
        - Never stop just because target is hit — only stop on drawdown
        """
        pnl = self.realized_pnl

        # First lock: hit minimum target
        if pnl >= self.target_min and self.locked_floor is None:
            self.locked_floor = round(self.target_min * 0.97, 2)   # 3% buffer
            logger.info(f"🔒 Profit lock activated at floor ${self.locked_floor:.2f} (hit min ${self.target_min})")

        # Trailing: continuously raise floor as P&L grows
        if self.locked_floor is not None and pnl > self.target_min:
            # Trail at 94% of current peak — tightens as we earn more
            trail_pct = 0.94 if pnl < self.target_desired * 1.5 else 0.96
            candidate_floor = round(pnl * trail_pct, 2)
            if candidate_floor > self.locked_floor:
                old_floor = self.locked_floor
                self.locked_floor = candidate_floor
                logger.info(
                    f"🔒 Floor raised: ${old_floor:.2f} → ${self.locked_floor:.2f} "
                    f"(P&L ${pnl:.2f}, protecting {trail_pct:.0%} of gains)"
                )

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

            # Composite score
            score = 0
            score += min(30, max(0, momentum * 5 + 15))        # momentum (0-30)
            score += min(20, vol_ratio * 10)                    # volume (0-20)
            score += 15 if trend_up else 0                      # trend (0-15)
            score += min(20, vol_score / 5)                     # volatility (0-20)
            score += 15 if exp_profit >= self.min_scalp_profit else 0  # profitability (0-15)

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
                "expected_move": round(expected_move, 6),
                "exp_profit":    round(exp_profit, 2),
                "valid":         probability >= self.min_probability and exp_profit > 0,
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

        # Stop must be at least 0.1% below entry (Alpaca minimum)
        min_stop_dist = max(price * 0.001, 0.01)
        stop_dist     = max(atr * 1.5, min_stop_dist)
        stop          = round(price - stop_dist, 6)
        target        = round(price + expected_move, 6)

        # Ensure stop < price - 0.01 (Alpaca bracket requirement)
        if price - stop < 0.01:
            stop = round(price - 0.01, 6)

        # Use up to 40% of available cash per trade
        max_spend = available * 0.40
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

        # Update profit lock
        self.check_profit_lock()
        if self.locked_floor is not None:
            self.state = EngineState.LOCKED_PROFIT

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
        # After 3 consecutive losses, tighten confidence requirement
        min_conf = self.min_probability
        if self.consecutive_losses >= 5:
            logger.info(f"⚠️  {self.consecutive_losses} consecutive losses — pausing 10 min")
            import time; time.sleep(600)
            self.consecutive_losses = 0
        elif self.consecutive_losses >= 3:
            min_conf = max(self.min_probability, 0.58)  # raise bar after 3 losses
            logger.info(f"⚠️  {self.consecutive_losses} losses in a row — raising confidence to {min_conf:.0%}")

        # Valid = meets confidence threshold (raised after loss streaks)
        valid_tradeable = [c for c in tradeable if c.get("valid") and
                          c.get("probability", c.get("confidence", 0) / 100) >= min_conf]

        if not valid_tradeable:
            # Only pick fallback if confidence streak is clean
            if self.consecutive_losses < 2:
                best_available = sorted(tradeable, key=lambda x: x["score"], reverse=True)[0]
                # Raise the fallback score bar too — don't trade noise
                if best_available.get("score", 0) >= 40:
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

            # Stop/target from ACTUAL fill price (not yfinance estimate)
            stop   = round(actual_price * 0.997, 6)   # 0.3% stop
            target = round(actual_price * 1.003, 6)   # 0.3% target
            logger.info(f"Fill: {ticker} @ ${actual_price:.4f} | stop=${stop:.4f} target=${target:.4f}")

            # Refresh account after fill
            self.state = EngineState.FUNDS_REFRESHING
            self.refresh_account()

            # Record position
            self.state = EngineState.POSITION_OPEN
            pos = CryptoPosition(
                symbol   = symbol,
                side     = "BUY",
                qty      = qty,
                entry    = best["price"],
                stop     = stop,
                target   = target,
                order_id = order_id,
            )
            self.open_positions[symbol] = pos
            self.trades_today += 1
            logger.info(f"✅ Crypto position: {symbol} qty={qty} entry=${best['price']:.4f} target=${target:.4f} stop=${stop:.4f}")

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
                    entry_price  = float(best["price"]),
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
                    _reporter.log_entry(ticker, "BUY", qty, float(best["price"]),
                                        float(stop), float(target), float(best.get("probability", 0)))
            except Exception as e:
                logger.warning(f"Crypto DB save error: {e}")

        except Exception as e:
            logger.error(f"CryptoEngine order error: {e}")
            self._last_error = str(e)
            self.state = EngineState.ERROR

        return self.status()

    async def _scan_candidates(self) -> List[dict]:
        import asyncio

        loop    = asyncio.get_event_loop()
        t0      = loop.time()

        if BINANCE_AVAILABLE:
            # Binance: ~200-400ms, real-time prices, no auth needed
            results  = await loop.run_in_executor(None, _binance_scan, CRYPTO_UNIVERSE)
            elapsed  = loop.time() - t0
            logger.info(f"🤖 Binance scan: {len(results)}/{len(CRYPTO_UNIVERSE)} coins in {elapsed:.1f}s")

            # Convert Binance results to engine candidate format
            candidates = []
            for r in results:
                try:
                    ticker = r["ticker"]
                    price  = r["price"]
                    # Build a minimal bars-compatible scored dict
                    # using score_crypto_candidate style output from Binance
                    scored = {
                        "symbol":      f"{ticker}/USD",
                        "ticker":      ticker,
                        "price":       price,
                        "score":       r.get("score", 0),
                        "probability": r.get("confidence", 50) / 100,
                        "momentum":    r.get("momentum", 0),
                        "vol_ratio":   r.get("vol_spike", 1),
                        "atr":         r.get("atr", price * 0.005),
                        "atr_pct":     r.get("atr", price * 0.005) / price * 100 if price > 0 else 0,
                        "trend_up":    r.get("momentum", 0) > 0,
                        "expected_move": r.get("atr", price * 0.005) * 1.5,
                        "exp_profit":  0.25,
                        "valid":       r.get("confidence", 0) >= self.min_probability * 100,
                        "entry":       r.get("entry", price),
                        "exit_target": r.get("exit_target", price),
                        "stop":        r.get("stop", price),
                        "change_24h":  r.get("change_24h", 0),
                        "source":      "binance",
                    }
                    candidates.append(scored)
                except Exception as e:
                    logger.debug(f"Binance result parse {r.get('ticker','?')}: {e}")

        else:
            # Fallback: yfinance batch (slower but no external dependency)
            import yfinance as yf
            import pandas as pd
            import numpy as np

            def _yf_batch():
                yf_syms = [f"{t}-USD" for t in CRYPTO_UNIVERSE]
                try:
                    df = yf.download(yf_syms, period="1d", interval="1m",
                                     progress=False, auto_adjust=True, group_by="ticker")
                    result = {}
                    for ticker in CRYPTO_UNIVERSE:
                        yf_sym = f"{ticker}-USD"
                        try:
                            if isinstance(df.columns, pd.MultiIndex):
                                if yf_sym not in df.columns.get_level_values(0):
                                    continue
                                sub = df[yf_sym].copy()
                            else:
                                sub = df.copy()
                            sub.columns = [c.lower() for c in sub.columns]
                            if "close" in sub.columns and len(sub) >= 5:
                                result[ticker] = sub
                        except Exception:
                            continue
                    return result
                except Exception as e:
                    logger.warning(f"yfinance fallback: {e}")
                    return {}

            bars_map = await loop.run_in_executor(None, _yf_batch)
            elapsed  = loop.time() - t0
            logger.info(f"🤖 yfinance fallback: {len(bars_map)}/{len(CRYPTO_UNIVERSE)} coins in {elapsed:.1f}s")

            candidates = []
            for ticker, bars in bars_map.items():
                try:
                    symbol = f"{ticker}/USD"
                    price  = float(bars["close"].iloc[-1])
                    scored = self.score_crypto_candidate(symbol, bars)
                    scored["ticker"] = ticker
                    scored["price"]  = price
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
                # Priority: Binance (fastest) → Alpaca quote → yfinance
                current_price = 0.0
                if BINANCE_AVAILABLE:
                    current_price = _binance_price(ticker)
                if current_price <= 0:
                    if hasattr(self.broker, "get_latest_crypto_price"):
                        current_price = self.broker.get_latest_crypto_price(ticker)
                    else:
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

        def _safe(v):
            """Convert numpy scalars to Python natives so FastAPI can JSON-encode them."""
            if isinstance(v, (_np.bool_, _np.bool8 if hasattr(_np, 'bool8') else _np.bool_)):
                return bool(v)
            if isinstance(v, (_np.integer,)):
                return int(v)
            if isinstance(v, (_np.floating,)):
                return float(v)
            return v

        bp_raw = float(self.last_account_state.get("non_marginable_buying_power",
                       self.last_account_state.get("cash", 0))) if self.last_account_state else 0.0
        budget = round(self.capital * self.crypto_alloc, 2)

        return {
            "state":             self.state.value,
            "realized_pnl":      round(self.realized_pnl, 2),
            "compounded_gains":  round(self.compounded_gains, 2),
            "locked_floor":      round(self.locked_floor, 2) if self.locked_floor else None,
            "remaining_to_min":  round(self.remaining_to_min(), 2),
            "remaining_to_desired": round(self.remaining_to_desired(), 2),
            "open_positions":    len(self.open_positions),
            "trades_today":      self.trades_today,
            "stop_reason":       self.stop_reason,
            "last_error":        self._last_error,
            "cycle":             self.cycle_count,
            "min_probability":   self.min_probability,
            "buying_power":      round(min(bp_raw, budget), 2) if bp_raw else budget,
            "crypto_budget":     budget,
            "scan_results": [
                {k: _safe(v) for k, v in s.items()}
                for s in self._scan_results
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