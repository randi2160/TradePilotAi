"""
Morviq AI — PDT (Pattern Day Trader) Compliance Engine

What this does:
- Queries Alpaca account BEFORE every trade
- Enforces daytrade_count < 3 limit for accounts under $25k
- Blocks 4th day trade automatically
- Switches to overnight-hold strategy when limit reached
- Logs every PDT check to audit trail
- Handles account multiplier / buying power correctly

Rules enforced:
1. If equity >= 25,000 → PDT rules don't apply → trade freely
2. If daytrade_count >= 3 → block same-day close → hold overnight
3. If account < 2,000 → 1x buying power only
4. If account 2,000–25,000 → 2x buying power (margin)
5. Crypto positions → exempt from PDT rules
"""

import logging
from datetime import datetime, timezone
from typing   import Optional

logger = logging.getLogger(__name__)

# Symbols exempt from PDT (crypto on Alpaca)
CRYPTO_SYMBOLS = {
    'BTC', 'ETH', 'LTC', 'BCH', 'LINK', 'AAVE', 'UNI',
    'BAT', 'CRV', 'GRT', 'MKR', 'MATIC', 'SHIB', 'DOGE',
    'BTCUSD', 'ETHUSD', 'LTCUSD',
}

PDT_DAYTRADE_LIMIT    = 3      # Max day trades in a 5-trading-day period
PDT_EQUITY_THRESHOLD  = 25_000 # Below this → PDT rules apply
MIN_BUYING_POWER      = 2_000  # Below this → 1x only


class PDTStatus:
    """Snapshot of account PDT state at a moment in time."""
    def __init__(
        self,
        equity:           float,
        daytrade_count:   int,
        buying_power:     float,
        pattern_day_trader: bool,
        cash:             float,
    ):
        self.equity            = equity
        self.daytrade_count    = daytrade_count
        self.buying_power      = buying_power
        self.pattern_day_trader= pattern_day_trader
        self.cash              = cash
        self.is_pdt_exempt     = equity >= PDT_EQUITY_THRESHOLD
        self.trades_remaining  = max(0, PDT_DAYTRADE_LIMIT - daytrade_count) if not self.is_pdt_exempt else 999
        self.account_multiplier= 2.0 if equity >= MIN_BUYING_POWER else 1.0
        self.checked_at        = datetime.now(timezone.utc).isoformat()

    @property
    def can_day_trade(self) -> bool:
        """True if a new day trade is allowed right now."""
        if self.is_pdt_exempt:
            return True
        return self.daytrade_count < PDT_DAYTRADE_LIMIT

    @property
    def must_hold_overnight(self) -> bool:
        """True if new entries must be held until next trading day."""
        return not self.is_pdt_exempt and self.daytrade_count >= PDT_DAYTRADE_LIMIT

    def summary(self) -> str:
        if self.is_pdt_exempt:
            return f"PDT exempt (equity ${self.equity:,.0f} ≥ $25k) — trade freely"
        remaining = PDT_DAYTRADE_LIMIT - self.daytrade_count
        if remaining <= 0:
            return f"⚠️ PDT LIMIT REACHED ({self.daytrade_count}/3 day trades used) — holding overnight only"
        return f"PDT: {self.daytrade_count}/3 day trades used · {remaining} remaining today"


class PDTComplianceEngine:
    """
    Call check_before_entry() before every trade.
    Call check_before_exit() before closing a position same day.
    """

    def __init__(self, broker):
        self.broker  = broker
        self._cached: Optional[PDTStatus] = None
        self._cache_ts: Optional[datetime] = None
        self._cache_ttl = 30  # seconds

    def get_status(self, force_refresh: bool = False) -> PDTStatus:
        """Get current PDT status from Alpaca account."""
        now = datetime.now(timezone.utc)

        # Use cache if fresh
        if (not force_refresh and self._cached and self._cache_ts
                and (now - self._cache_ts).total_seconds() < self._cache_ttl):
            return self._cached

        try:
            acct = self.broker.trading.get_account()

            status = PDTStatus(
                equity            = float(acct.equity),
                daytrade_count    = int(getattr(acct, 'daytrade_count', 0)),
                buying_power      = float(acct.buying_power),
                pattern_day_trader= getattr(acct, 'pattern_day_trader', False),
                cash              = float(acct.cash),
            )
            self._cached   = status
            self._cache_ts = now
            logger.info(f"PDT check: {status.summary()}")
            return status

        except Exception as e:
            logger.error(f"PDTComplianceEngine.get_status error: {e}")
            # Safe default — assume restricted
            return PDTStatus(
                equity=0, daytrade_count=3,
                buying_power=0, pattern_day_trader=False, cash=0
            )

    def check_before_entry(self, symbol: str, qty: int, price: float) -> dict:
        """
        Call this before placing any BUY order.
        Returns: { allowed: bool, reason: str, action: str, status: PDTStatus }
        """
        symbol = symbol.upper()

        # Crypto is PDT exempt
        if symbol in CRYPTO_SYMBOLS or '/' in symbol:
            return {
                "allowed": True,
                "reason":  "Crypto — PDT rules do not apply",
                "action":  "trade_normally",
                "pdt_exempt": True,
            }

        status = self.get_status()

        if status.is_pdt_exempt:
            return {
                "allowed":    True,
                "reason":     f"Account equity ${status.equity:,.0f} ≥ $25k — PDT exempt",
                "action":     "trade_normally",
                "pdt_exempt": True,
                "status":     status,
            }

        # Check buying power
        order_value = qty * price
        if order_value > status.buying_power:
            return {
                "allowed": False,
                "reason":  f"Insufficient buying power: need ${order_value:,.2f}, have ${status.buying_power:,.2f}",
                "action":  "reduce_size_or_skip",
                "status":  status,
            }

        # PDT limit check
        if status.must_hold_overnight:
            return {
                "allowed": True,  # CAN enter — just can't exit same day
                "reason":  f"PDT limit reached ({status.daytrade_count}/3). Entry allowed but must hold overnight.",
                "action":  "enter_hold_overnight",
                "warning": True,
                "status":  status,
            }

        if status.trades_remaining == 1:
            logger.warning(f"⚠️ Only 1 day trade remaining for today. Use carefully.")
            return {
                "allowed":  True,
                "reason":   f"1 day trade remaining — last one for today",
                "action":   "trade_with_caution",
                "warning":  True,
                "status":   status,
            }

        return {
            "allowed": True,
            "reason":  f"{status.trades_remaining} day trades remaining",
            "action":  "trade_normally",
            "status":  status,
        }

    def check_before_exit(self, symbol: str, entry_date: str) -> dict:
        """
        Call this before closing a position.
        If closing today would count as a day trade, check if allowed.
        """
        symbol = symbol.upper()

        if symbol in CRYPTO_SYMBOLS:
            return {"allowed": True, "reason": "Crypto — no PDT restriction", "is_day_trade": False}

        today = str(datetime.now(timezone.utc).date())
        is_day_trade = entry_date == today

        if not is_day_trade:
            return {"allowed": True, "reason": "Not a day trade — entered a different day", "is_day_trade": False}

        status = self.get_status()

        if status.is_pdt_exempt:
            return {"allowed": True, "reason": "PDT exempt", "is_day_trade": True}

        if status.daytrade_count >= PDT_DAYTRADE_LIMIT:
            return {
                "allowed":      False,
                "reason":       f"⛔ Closing would trigger day trade #{status.daytrade_count + 1} — PDT VIOLATION. Must hold overnight.",
                "is_day_trade": True,
                "action":       "hold_overnight",
                "status":       status,
            }

        return {
            "allowed":      True,
            "reason":       f"Day trade #{status.daytrade_count + 1} of 3 allowed",
            "is_day_trade": True,
            "status":       status,
        }

    def get_safe_position_size(self, price: float, max_pct: float = 0.1) -> int:
        """
        Calculate max safe qty based on buying power and PDT status.
        max_pct: fraction of buying power to use per trade (default 10%)
        """
        status = self.get_status()
        if price <= 0:
            return 0

        # Use less buying power if nearing PDT limit
        multiplier = 1.0
        if not status.is_pdt_exempt:
            if status.daytrade_count >= 2:
                multiplier = 0.5  # Reduce size when near limit
            elif status.daytrade_count >= 1:
                multiplier = 0.75

        available   = status.buying_power * max_pct * multiplier
        qty         = int(available / price)
        return max(0, qty)

    def account_summary(self) -> dict:
        """Full account status for display in dashboard."""
        status = self.get_status(force_refresh=True)
        return {
            "equity":             status.equity,
            "buying_power":       status.buying_power,
            "cash":               status.cash,
            "daytrade_count":     status.daytrade_count,
            "day_trades_remaining": status.trades_remaining,
            "is_pdt_exempt":      status.is_pdt_exempt,
            "must_hold_overnight":status.must_hold_overnight,
            "pattern_day_trader": status.pattern_day_trader,
            "account_multiplier": status.account_multiplier,
            "can_day_trade":      status.can_day_trade,
            "summary":            status.summary(),
            "checked_at":         status.checked_at,
        }
