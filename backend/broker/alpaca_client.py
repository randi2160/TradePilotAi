"""
Alpaca brokerage client — handles both paper and live trading.
All order execution, account queries, and market data go through here.
"""
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
try:
    from alpaca.data.requests import CryptoBarsRequest, CryptoLatestQuoteRequest
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

import config

logger = logging.getLogger(__name__)

_TF_MAP = {
    "1Min":  TimeFrame(1,  TimeFrameUnit.Minute),
    "5Min":  TimeFrame(5,  TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1,  TimeFrameUnit.Hour),
    "1Day":  TimeFrame(1,  TimeFrameUnit.Day),
}


class AlpacaClient:
    def __init__(self, paper: bool = True, api_key: str = None, api_secret: str = None):
        self.paper = paper
        # Use passed credentials or fall back to .env
        key    = api_key    or config.ALPACA_API_KEY
        secret = api_secret or config.ALPACA_SECRET_KEY
        self.trading = TradingClient(
            api_key=key, secret_key=secret, paper=paper,
        )
        self.data = StockHistoricalDataClient(
            api_key=key, secret_key=secret,
        )
        mode = "PAPER" if paper else "LIVE"
        logger.info(f"AlpacaClient ready ({mode}) key=...{key[-4:] if key else 'NONE'}")

    # ── Account ──────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        try:
            acct   = self.trading.get_account()
            equity = float(acct.equity)
            dt_count = int(getattr(acct, 'daytrade_count', 0))
            pdt_exempt = equity >= 25_000
            return {
                "buying_power":         float(acct.buying_power),
                "equity":               equity,
                "cash":                 float(acct.cash),
                "portfolio_value":      float(acct.portfolio_value),
                "pnl_today":            equity - config.CAPITAL,
                "daytrade_count":       dt_count,
                "day_trades_remaining": max(0, 3 - dt_count) if not pdt_exempt else 999,
                "is_pdt_exempt":        pdt_exempt,
                "pattern_day_trader":   getattr(acct, 'pattern_day_trader', False),
                "account_multiplier":   2.0 if equity >= 2_000 else 1.0,
                "must_hold_overnight":  not pdt_exempt and dt_count >= 3,
                "pdt_warning":          not pdt_exempt and dt_count >= 2,
            }
        except Exception as e:
            logger.error(f"get_account error: {e}")
            return {}

    def is_market_open(self) -> bool:
        try:
            clock = self.trading.get_clock()
            is_open = clock.is_open
            if not is_open:
                next_open = clock.next_open
                logger.debug(f"Market closed — next open: {next_open}")
            return is_open
        except Exception as e:
            logger.warning(f"is_market_open error: {e} — assuming open to continue")
            # Don't block the bot on API errors — check time locally instead
            import pytz
            from datetime import datetime
            et  = pytz.timezone("America/New_York")
            now = datetime.now(et)
            h, m, wd = now.hour, now.minute, now.weekday()
            if wd >= 5:   return False   # weekend
            if h < 9 or h >= 16: return False
            if h == 9 and m < 30: return False
            return True

    # ── Market Data ───────────────────────────────────────────────────────────

    def get_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 300) -> pd.DataFrame:
        # Route to crypto if symbol looks like crypto
        symbol_up = symbol.upper().replace("-", "/")
        is_crypto = "/" in symbol_up or symbol_up in {
            "BTC","ETH","SOL","DOGE","LINK","LTC","BCH","AAVE","UNI","ADA"
        }
        if is_crypto:
            return self.get_crypto_bars(symbol_up.split("/")[0], timeframe, limit)
        try:
            tf  = _TF_MAP.get(timeframe, _TF_MAP["1Min"])
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=datetime.now(timezone.utc) - timedelta(days=7),
                limit=limit,
            )
            bars = self.data.get_stock_bars(req)
            df   = bars.df
            if isinstance(df.index, pd.MultiIndex):
                df = df.xs(symbol, level=0)
            df.index = pd.to_datetime(df.index)
            return df[["open", "high", "low", "close", "volume"]].copy()
        except Exception as e:
            logger.error(f"get_bars({symbol}) error: {e}")
            return pd.DataFrame()

    def get_crypto_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 300) -> pd.DataFrame:
        """Get OHLCV bars for crypto using stock bars endpoint with crypto symbol."""
        try:
            tf  = _TF_MAP.get(timeframe, _TF_MAP["1Min"])
            req = StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=tf,
                start=datetime.now(timezone.utc) - timedelta(days=2),
                limit=limit,
            )
            bars = self.data.get_stock_bars(req)
            df   = bars.df
            if isinstance(df.index, pd.MultiIndex):
                df = df.xs(symbol.upper(), level=0)
            df.index = pd.to_datetime(df.index)
            # Normalize column names (Alpaca sometimes uses different cases)
            df.columns = [c.lower() for c in df.columns]
            available = [c for c in ["open","high","low","close","volume"] if c in df.columns]
            if len(available) < 3:
                return pd.DataFrame()
            return df[available].copy()
        except Exception as e:
            logger.debug(f"get_crypto_bars({symbol}): {e}")
            return pd.DataFrame()

    def get_latest_crypto_price(self, symbol: str) -> float:
        """Get latest price for a crypto symbol."""
        if not _HAS_CRYPTO:
            return 0.0
        try:
            from alpaca.data import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoLatestQuoteRequest
            pair   = symbol.upper()
            if "/" not in pair:
                pair = f"{pair}/USD"
            client = CryptoHistoricalDataClient()
            req    = CryptoLatestQuoteRequest(symbol_or_symbols=pair)
            quote  = client.get_crypto_latest_quote(req)
            q      = quote[pair]
            return float((q.ask_price + q.bid_price) / 2) if q.ask_price else float(q.bid_price)
        except Exception as e:
            logger.debug(f"get_latest_crypto_price({symbol}): {e}")
            return 0.0

    def get_latest_price(self, symbol: str) -> float:
        try:
            req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            q = self.data.get_stock_latest_quote(req)
            bid = float(q[symbol].bid_price)
            ask = float(q[symbol].ask_price)
            return round((bid + ask) / 2, 4)
        except Exception as e:
            logger.error(f"get_latest_price({symbol}) error: {e}")
            return 0.0

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_market_order(self, symbol: str, qty: float, side: str) -> dict:
        try:
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = self.trading.submit_order(req)
            logger.info(f"ORDER {side} {qty}x{symbol} submitted ({order.id})")
            return {
                "id":     str(order.id),
                "symbol": symbol,
                "qty":    qty,
                "side":   side,
                "status": str(order.status),
            }
        except Exception as e:
            logger.error(f"place_market_order error: {e}")
            return {"error": str(e)}

    def place_bracket_order(
        self, symbol: str, qty: float, side: str,
        stop_loss: float, take_profit: float,
    ) -> dict:
        """Place a bracket (entry + stop + target) order in one shot."""
        try:
            order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.models import OrderClass, TakeProfitRequest, StopLossRequest

            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                order_class="bracket",
                take_profit={"limit_price": round(take_profit, 2)},
                stop_loss={"stop_price": round(stop_loss, 2)},
            )
            order = self.trading.submit_order(req)
            logger.info(f"BRACKET {side} {qty}x{symbol} | SL={stop_loss} TP={take_profit}")
            return {"id": str(order.id), "symbol": symbol, "status": str(order.status)}
        except Exception as e:
            # Fall back to simple market order if bracket fails
            logger.warning(f"Bracket order failed, falling back to market: {e}")
            return self.place_market_order(symbol, qty, side)

    def close_position(self, symbol: str) -> dict:
        try:
            self.trading.close_position(symbol)
            logger.info(f"Position {symbol} closed")
            return {"status": "closed", "symbol": symbol}
        except Exception as e:
            logger.error(f"close_position({symbol}) error: {e}")
            return {"error": str(e)}

    def close_all_positions(self):
        try:
            self.trading.close_all_positions(cancel_orders=True)
            logger.info("All positions closed")
        except Exception as e:
            logger.error(f"close_all_positions error: {e}")

    # ── Positions & Orders ────────────────────────────────────────────────────

    def get_positions(self) -> list:
        try:
            result = []
            for p in self.trading.get_all_positions():
                # Normalize side — Alpaca returns PositionSide enum
                raw_side = str(p.side).lower()
                side     = "short" if "short" in raw_side else "long"
                qty      = abs(float(p.qty))
                result.append({
                    "symbol":         p.symbol,
                    "qty":            qty,
                    "avg_entry":      float(p.avg_entry_price),
                    "current_price":  float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "unrealized_pct": float(p.unrealized_plpc),  # already decimal e.g. 0.023
                    "market_value":   float(p.market_value),
                    "side":           side,
                })
            return result
        except Exception as e:
            logger.error(f"get_positions error: {e}")
            return []

    def get_orders(self, limit: int = 50) -> list:
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
            result = []
            for o in self.trading.get_orders(req):
                # Normalize enum strings e.g. "OrderSide.BUY" → "BUY"
                side   = str(o.side).split(".")[-1].upper()
                status = str(o.status).split(".")[-1].upper()
                result.append({
                    "id":               str(o.id),
                    "symbol":           o.symbol,
                    "qty":              float(o.qty or 0),
                    "filled_qty":       float(o.filled_qty or 0),
                    "side":             side,
                    "status":           status,
                    "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
                    "created_at":       str(o.created_at),
                })
            return result
        except Exception as e:
            logger.error(f"get_orders error: {e}")
            return []