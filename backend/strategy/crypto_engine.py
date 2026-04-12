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

CRYPTO_PAIRS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD",
    "LINK/USD", "AAVE/USD", "LTC/USD", "BCH/USD",
]
CRYPTO_TICKERS = ["BTC","ETH","SOL","DOGE","LINK","AAVE","LTC","BCH"]


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
        self.symbol    = symbol
        self.side      = side
        self.qty       = qty
        self.entry     = entry
        self.stop      = stop
        self.target    = target
        self.order_id  = order_id
        self.opened_at = datetime.now(timezone.utc)
        self.exit_order_id = None

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
        min_scalp_profit: float = 15,   # min $ per scalp
        max_scalp_hold_min: int = 15,   # max hold before forced exit
        max_risk_pct:   float = 0.005,  # 0.5% risk per trade
        compound_mode:  bool  = True,
        min_probability: float = 0.60,
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
        self.locked_floor       = None       # set once min target hit
        self.open_positions: Dict[str, CryptoPosition] = {}
        self.compounded_gains   = 0.0
        self.stop_reason        = None
        self._last_error        = None
        self.last_account_state = {}
        self.cycle_count        = 0
        self.last_refresh       = 0
        self.trades_today       = 0
        self._scan_results      = []   # last scan scores for UI display

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
        """Crypto must use non_marginable_buying_power = settled_cash - pending_fills."""
        acct = self.refresh_account()
        # Prefer explicit field, fall back to cash
        nmbp = acct.get("non_marginable_buying_power") or acct.get("cash", 0)
        return float(nmbp)

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

            # Expected move (1 ATR target)
            expected_move = atr * 1.5
            # Can we hit min_scalp_profit with reasonable position?
            max_size  = self.get_non_marginable_buying_power() * 0.3
            if max_size <= 0:
                max_size = self.allocated_capital * 0.3
            units     = max_size / price
            exp_profit = units * expected_move

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
        Result is minimum of: target-based, risk-based, buying-power-based.
        """
        price         = candidate.get("price", 0)
        atr           = candidate.get("atr",   price * 0.005)
        if price <= 0:
            return {"qty": 0, "reason": "Invalid price"}

        # Refresh buying power (never use stale)
        nbp           = self.get_non_marginable_buying_power()
        available     = min(nbp, self.allocated_capital + self.compounded_gains)

        # 1. Target-based: units needed to hit next scalp goal
        expected_move = candidate.get("expected_move", atr * 1.5)
        if expected_move <= 0:
            expected_move = price * 0.01
        target_units  = self.min_scalp_profit / expected_move if expected_move > 0 else 0

        # 2. Risk-based: max loss = max_risk_pct of capital
        stop_dist     = atr * 1.5
        max_risk_usd  = self.capital * self.max_risk_pct
        risk_units    = max_risk_usd / stop_dist if stop_dist > 0 else 0

        # 3. Buying-power-based: 30% of available per trade
        bp_units      = (available * 0.30) / price if price > 0 else 0

        # 4. Min of all constraints
        qty           = min(target_units, risk_units, bp_units)
        qty           = max(0.001, round(qty, 6))   # min 0.001 units for crypto

        cost          = qty * price
        exp_profit    = qty * expected_move
        stop          = round(price - stop_dist, 6)
        target        = round(price + expected_move, 6)

        # Reject if cost exceeds buying power
        if cost > nbp:
            return {"qty": 0, "reason": f"Cost ${cost:.2f} > buying power ${nbp:.2f}"}

        if exp_profit < self.min_scalp_profit * 0.5:
            return {"qty": 0, "reason": f"Expected profit ${exp_profit:.2f} too low"}

        return {
            "qty":          qty,
            "cost":         round(cost, 2),
            "stop":         stop,
            "target":       target,
            "stop_dist":    round(stop_dist, 6),
            "exp_profit":   round(exp_profit, 2),
            "reason":       "sized",
            "breakdown": {
                "target_based": round(target_units, 6),
                "risk_based":   round(risk_units, 6),
                "bp_based":     round(bp_units, 6),
                "final":        qty,
                "available_bp": round(nbp, 2),
            }
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
        valid         = [c for c in candidates if c.get("valid")]

        # Store scan results for dashboard visibility
        self._scan_results = [
            {
                "symbol": c.get("symbol",""),
                "score":  round(c.get("score", 0), 0),
                "prob":   round(c.get("probability", 0) * 100, 0),
                "valid":  c.get("valid", False),
                "price":  c.get("price", 0),
                "momentum": round(c.get("momentum", 0), 2),
            }
            for c in candidates[:8]
        ]

        if not valid:
            self.state = EngineState.IDLE
            return self.status()

        # Best candidate
        self.state    = EngineState.CANDIDATE_RANKED
        best          = sorted(valid, key=lambda x: x["score"], reverse=True)[0]

        # Size it
        self.state    = EngineState.SIZING
        sizing        = self.calculate_size(best)
        if sizing["qty"] <= 0:
            logger.info(f"Sizing rejected: {sizing.get('reason')}")
            self.state = EngineState.IDLE
            return self.status()

        # Place order
        self.state    = EngineState.ORDER_PENDING
        symbol        = best["symbol"]
        qty           = sizing["qty"]
        stop          = sizing["stop"]
        target        = sizing["target"]

        try:
            # Use broker's place_order which handles the correct Alpaca request format
            ticker = symbol.split("/")[0]  # "BTC/USD" → "BTC"
            order  = self.broker.place_bracket_order(
                symbol      = ticker,
                qty         = qty,
                side        = "BUY",
                stop_loss   = sizing["stop"],
                take_profit = sizing["target"],
            )
            if "error" in order:
                logger.error(f"Crypto order failed: {order['error']}")
                self._last_error = order["error"]
                self.state = EngineState.IDLE
                return self.status()

            order_id = order.get("id", "")
            logger.info(f"Crypto order placed: {ticker} qty={qty} @ market")

            # Wait for fill
            filled = self.wait_for_fill(order_id, timeout=20)
            if not filled:
                logger.warning(f"Order {order_id} not filled in time")
                self.state = EngineState.IDLE
                return self.status()

            # Refresh account after fill
            self.state = EngineState.FUNDS_REFRESHING
            acct       = self.refresh_account()

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

        except Exception as e:
            logger.error(f"CryptoEngine order error: {e}")
            self._last_error = str(e)
            self.state = EngineState.ERROR

        return self.status()

    async def _scan_candidates(self) -> List[dict]:
        candidates = []
        for ticker in CRYPTO_TICKERS[:6]:
            try:
                symbol = f"{ticker}/USD"
                # Try crypto bars, fall back to stock bars call with crypto symbol
                bars = None
                try:
                    bars = self.broker.get_crypto_bars(ticker, "1Min", 50)
                except Exception:
                    pass
                if bars is None or len(bars) == 0:
                    bars = self.broker.get_bars(ticker, "1Min", 50)
                if bars is not None and len(bars) > 10:
                    scored = self.score_crypto_candidate(symbol, bars)
                    scored["ticker"] = ticker
                    candidates.append(scored)
                    logger.debug(f"Scored {ticker}: {scored.get('score',0):.0f}")
            except Exception as e:
                logger.warning(f"Scan {ticker}: {e}")
                self._last_error = f"Scan {ticker}: {e}"
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    async def _manage_positions(self):
        """Check exits for all open positions."""
        for sym, pos in list(self.open_positions.items()):
            ticker = sym.split("/")[0]
            try:
                # Use crypto price method
                if hasattr(self.broker, "get_latest_crypto_price"):
                    current_price = self.broker.get_latest_crypto_price(ticker)
                else:
                    current_price = self.broker.get_latest_price(ticker)
                if current_price <= 0:
                    continue

                upnl    = pos.unrealized_pnl(current_price)
                held_min= (datetime.now(timezone.utc) - pos.opened_at).total_seconds() / 60
                should_exit = False
                exit_reason = ""

                # Target hit
                if current_price >= pos.target:
                    should_exit = True
                    exit_reason = f"Target hit ${pos.target:.4f}"

                # Stop hit
                elif current_price <= pos.stop:
                    should_exit = True
                    exit_reason = f"Stop hit ${pos.stop:.4f}"

                # Time stop
                elif held_min >= self.max_scalp_hold_min:
                    should_exit = True
                    exit_reason = f"Time stop ({held_min:.0f}m)"

                if should_exit:
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

            del self.open_positions[sym]
            self.state = EngineState.READY_FOR_REENTRY
            logger.info(f"Exit {sym}: {reason} | P&L ${pnl:+.2f} | Total ${self.realized_pnl:.2f}")

        except Exception as e:
            logger.error(f"Exit position {sym}: {e}")

    def status(self) -> dict:
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
            "scan_results":      self._scan_results,
            "open_position_list": [
                {
                    "symbol": sym,
                    "qty":    pos.qty,
                    "entry":  pos.entry,
                    "stop":   pos.stop,
                    "target": pos.target,
                    "side":   pos.side,
                }
                for sym, pos in self.open_positions.items()
            ],
            "buying_power": self.last_account_state.get("non_marginable_buying_power",
                             self.last_account_state.get("cash", 0)),
        }