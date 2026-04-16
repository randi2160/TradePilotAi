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
    def __init__(self, paper: bool = True, api_key: str = None, api_secret: str = None,
                 system: bool = False):
        """
        Instantiate an Alpaca client.

        SECURITY: By default, callers MUST pass explicit credentials. We do NOT
        silently fall back to .env — doing so previously caused per-user
        endpoints to return the admin's portfolio to every unauthenticated
        user (data leak incident 2026-04-16).

        Only set `system=True` from trusted system-level code paths that have
        no per-user context (e.g. the market scanner scanning public gainers).
        """
        self.paper = paper
        if api_key and api_secret:
            key    = api_key
            secret = api_secret
        elif system:
            # Explicit system context — OK to use shared .env keys for
            # market-data-only operations. Never for account/positions.
            key    = config.ALPACA_API_KEY
            secret = config.ALPACA_SECRET_KEY
        else:
            raise ValueError(
                "AlpacaClient requires per-user credentials. "
                "Pass api_key/api_secret from the user's saved broker_creds, "
                "or set system=True for trusted system-level market-data paths."
            )
        self.api_key    = key
        self.secret_key = secret
        self.trading = TradingClient(
            api_key=key, secret_key=secret, paper=paper,
        )
        self.data = StockHistoricalDataClient(
            api_key=key, secret_key=secret,
        )
        # Crypto data client — for live prices and bars
        try:
            from alpaca.data import CryptoHistoricalDataClient
            self.crypto_data = CryptoHistoricalDataClient(
                api_key=key, secret_key=secret,
            )
        except Exception as e:
            self.crypto_data = None
            logger.warning(f"CryptoHistoricalDataClient unavailable: {e}")
        mode = "PAPER" if paper else "LIVE"
        logger.info(f"AlpacaClient ready ({mode}) key=...{key[-4:] if key else 'NONE'}")

    # ── Account ──────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        try:
            acct   = self.trading.get_account()
            equity = float(acct.equity)
            dt_count = int(getattr(acct, 'daytrade_count', 0))
            pdt_exempt = equity >= 25_000
            cash   = float(acct.cash)
            bp     = float(acct.buying_power)
            # non_marginable = settled cash not tied to open positions
            nmbp   = float(getattr(acct, 'non_marginable_buying_power', cash))
            dtbp   = float(getattr(acct, 'daytrading_buying_power', bp))
            return {
                "buying_power":                 bp,
                "non_marginable_buying_power":   nmbp,
                "daytrading_buying_power":       dtbp,
                "equity":                        equity,
                "cash":                          cash,
                "portfolio_value":               float(acct.portfolio_value),
                "pnl_today":                     equity - config.CAPITAL,
                "daytrade_count":                dt_count,
                "day_trades_remaining":          max(0, 3 - dt_count) if not pdt_exempt else 999,
                "is_pdt_exempt":                 pdt_exempt,
                "pattern_day_trader":            getattr(acct, 'pattern_day_trader', False),
                "account_multiplier":            2.0 if equity >= 2_000 else 1.0,
                "must_hold_overnight":           not pdt_exempt and dt_count >= 3,
                "pdt_warning":                   not pdt_exempt and dt_count >= 2,
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
        """
        Get OHLCV bars for crypto.

        Primary: Alpaca v1beta3 /crypto/us/bars — FREE on Basic tier, real-time,
        same feed the executor uses (eliminates scan-vs-fill price drift).
        Fallback: yfinance — 15-min delayed but covers edge cases when Alpaca
        returns empty (new listings, temporary outages).

        Binance has been removed entirely: AWS US IPs get HTTP 451 geo-blocked.
        """
        pair = symbol.upper()
        if "/" not in pair:
            pair = f"{pair}/USD"

        # ── Method 1: Alpaca v1beta3 (FREE, real-time, matches execution feed) ──
        import requests as _req
        try:
            api_key    = getattr(self, "api_key", None) or getattr(self, "key", "")
            secret_key = getattr(self, "secret_key", None) or getattr(self, "secret", "")
            if not api_key:
                import config as _cfg
                api_key, secret_key = _cfg.ALPACA_API_KEY, _cfg.ALPACA_SECRET_KEY
            tf_map = {"1Min": "1Min", "5Min": "5Min", "15Min": "15Min", "1Hour": "1Hour", "1Day": "1Day"}
            headers = {}
            if api_key and secret_key:
                headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
            resp = _req.get(
                "https://data.alpaca.markets/v1beta3/crypto/us/bars",
                params={"symbols": pair, "timeframe": tf_map.get(timeframe,"1Min"), "limit": limit, "sort": "asc"},
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                bars_data = resp.json().get("bars", {}).get(pair, [])
                if bars_data and len(bars_data) >= 3:
                    df = pd.DataFrame(bars_data).rename(
                        columns={"t":"timestamp","o":"open","h":"high","l":"low","c":"close","v":"volume"})
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df = df.set_index("timestamp")
                    available = [c for c in ["open","high","low","close","volume"] if c in df.columns]
                    if "close" in available and len(df) >= 3:
                        last_close = float(df["close"].iloc[-1])
                        logger.debug(f"Crypto bars {pair} via Alpaca: {len(df)} rows, last=${last_close:.4f}")
                        return df[available].copy()
            elif resp.status_code == 429:
                logger.warning(f"Alpaca crypto bars rate-limited for {pair} — falling back to yfinance")
            else:
                logger.debug(f"Alpaca crypto bars {pair}: HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"Alpaca crypto bars ({pair}): {e}")

        # ── Method 2: yfinance fallback (15-min delayed) ────────────────────────
        try:
            import yfinance as yf
            ticker_map = {
                "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "SOL/USD": "SOL-USD",
                "DOGE/USD": "DOGE-USD", "LINK/USD": "LINK-USD", "AAVE/USD": "AAVE-USD",
                "LTC/USD":  "LTC-USD",  "BCH/USD":  "BCH-USD",
                "XRP/USD":  "XRP-USD",  "SHIB/USD": "SHIB-USD",
            }
            interval_map = {"1Min": "1m", "5Min": "5m", "15Min": "15m", "1Hour": "60m", "1Day": "1d"}
            yf_sym   = ticker_map.get(pair, pair.replace("/", "-"))
            interval = interval_map.get(timeframe, "1m")
            period   = "1d" if interval in ("1m", "5m") else "5d"
            df = yf.download(yf_sym, period=period, interval=interval,
                             progress=False, auto_adjust=True)
            if df is not None and not df.empty and len(df) > 5:
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.droplevel(1, axis=1)
                df.columns = [c.lower() for c in df.columns]
                available = [c for c in ["open","high","low","close","volume"] if c in df.columns]
                if len(available) >= 4:
                    result = df[available].tail(limit).copy()
                    logger.info(f"Crypto bars {pair} via yfinance fallback: {len(result)} rows")
                    return result
        except ImportError:
            logger.warning("yfinance not installed — run: pip install yfinance")
        except Exception as e:
            logger.warning(f"yfinance fallback error ({pair}): {e}")

        return pd.DataFrame()

    def get_latest_crypto_price(self, symbol: str) -> float:
        """Get live crypto price from Alpaca crypto data API (real-time, not yfinance)."""
        base       = symbol.upper().replace("USD","").replace("/","").strip()
        alpaca_sym = f"{base}/USD"

        # Primary: Alpaca live crypto quote
        if self.crypto_data:
            try:
                from alpaca.data.requests import CryptoLatestQuoteRequest
                req   = CryptoLatestQuoteRequest(symbol_or_symbols=alpaca_sym)
                resp  = self.crypto_data.get_crypto_latest_quote(req)
                quote = resp.get(alpaca_sym)
                if quote:
                    bid = float(getattr(quote, "bid_price", 0) or 0)
                    ask = float(getattr(quote, "ask_price", 0) or 0)
                    if bid > 0 and ask > 0:
                        return round((bid + ask) / 2, 6)
                    if ask > 0: return round(ask, 6)
                    if bid > 0: return round(bid, 6)
            except Exception as e:
                logger.debug(f"Alpaca crypto quote {symbol}: {e}")

            # Fallback: Alpaca crypto bar (last 1-min close)
            try:
                from alpaca.data.requests import CryptoBarsRequest
                from alpaca.data.timeframe import TimeFrame
                req      = CryptoBarsRequest(symbol_or_symbols=alpaca_sym, timeframe=TimeFrame.Minute, limit=1)
                bars     = self.crypto_data.get_crypto_bars(req)
                bar_list = bars.get(alpaca_sym)
                if bar_list:
                    return float(bar_list[-1].close)
            except Exception as e:
                logger.debug(f"Alpaca crypto bar {symbol}: {e}")

        # Last resort: yfinance
        try:
            import yfinance as yf
            df = yf.download(f"{base}-USD", period="1d", interval="1m", progress=False, auto_adjust=True)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.droplevel(1, axis=1)
                df.columns = [c.lower() for c in df.columns]
                if "close" in df.columns:
                    return float(df["close"].iloc[-1])
        except Exception as e:
            logger.debug(f"yfinance fallback {symbol}: {e}")
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

    def _crypto_symbol(self, symbol: str) -> str:
        """Normalize crypto symbol for Alpaca trading API."""
        s = symbol.upper().replace("-", "/")
        if "/" not in s:
            s = f"{s}/USD"
        return s

    def _is_crypto(self, symbol: str) -> bool:
        CRYPTO = {"BTC","ETH","SOL","DOGE","LINK","AAVE","LTC","BCH","UNI","ADA","MATIC","XRP"}
        base = symbol.upper().split("/")[0].split("-")[0]
        return base in CRYPTO

    def place_market_order(self, symbol: str, qty: float, side: str) -> dict:
        try:
            is_crypto = self._is_crypto(symbol)
            sym = self._crypto_symbol(symbol) if is_crypto else symbol.upper()
            tif = TimeInForce.GTC if is_crypto else TimeInForce.DAY
            req = MarketOrderRequest(
                symbol        = sym,
                qty           = qty,
                side          = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
                time_in_force = tif,
            )
            order = self.trading.submit_order(req)
            logger.info(f"ORDER {side} {qty}x{sym} submitted ({order.id})")
            return {
                "id":     str(order.id),
                "symbol": sym,
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
        """Place bracket order. Falls back to market + separate stop for crypto."""
        is_crypto = self._is_crypto(symbol)
        sym = self._crypto_symbol(symbol) if is_crypto else symbol.upper()
        tif = TimeInForce.GTC if is_crypto else TimeInForce.DAY
        try:
            order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
            req = MarketOrderRequest(
                symbol        = sym,
                qty           = qty,
                side          = order_side,
                time_in_force = tif,
                order_class   = "bracket",
                take_profit   = {"limit_price": round(take_profit, 4)},
                stop_loss     = {"stop_price":  round(stop_loss,   4)},
            )
            order = self.trading.submit_order(req)
            logger.info(f"BRACKET {side} {qty}x{sym} | SL={stop_loss:.4f} TP={take_profit:.4f}")
            return {"id": str(order.id), "symbol": sym, "status": str(order.status)}
        except Exception as e:
            logger.warning(f"Bracket order failed, falling back to market: {e}")
            return self.place_market_order(sym, qty, side)

    def close_position(self, symbol: str) -> dict:
        """Close an entire position by symbol (market order).

        Routes stocks as plain uppercase tickers ("TSLA") and cryptos through
        `_crypto_symbol` ("BTC" → "BTC/USD"). Previously this used a broken
        "len <= 5 and no slash" heuristic that treated every stock ticker
        as crypto — so close_position("TSLA") tried "TSLA/USD" and then
        fell back to "TSLAUSD", both 404. That silently disabled the ladder's
        trail-exit/floor protection for all stock positions.
        """
        try:
            is_crypto = self._is_crypto(symbol)
            sym = self._crypto_symbol(symbol) if is_crypto else symbol.upper()
            result = self.trading.close_position(sym)
            logger.info(f"Closed position: {sym}")
            return {"status": "closed", "symbol": sym, "id": str(getattr(result, "id", ""))}
        except Exception as e:
            logger.error(f"close_position({symbol}): {e}")
            # Crypto-only fallback: try the dashless "BTCUSD" form a few older
            # Alpaca endpoints accept. Never apply to stocks — that's what
            # produced "TSLAUSD: symbol not found" spam in the old code.
            if self._is_crypto(symbol):
                try:
                    alt = symbol.replace("/", "").replace("-", "").upper()
                    if not alt.endswith("USD"):
                        alt += "USD"
                    result = self.trading.close_position(alt)
                    logger.info(f"Closed position (crypto alt): {alt}")
                    return {"status": "closed", "symbol": alt}
                except Exception as e2:
                    logger.error(f"close_position crypto-alt ({symbol}): {e2}")
                    return {"error": str(e2)}
            return {"error": str(e)}

    def get_open_orders(self) -> list:
        """Get all open orders."""
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums   import QueryOrderStatus
            req    = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self.trading.get_orders(filter=req)
            return [
                {
                    "id":          str(o.id),
                    "symbol":      str(o.symbol),
                    "side":        str(o.side),
                    "qty":         float(o.qty or 0),
                    "filled_qty":  float(o.filled_qty or 0),
                    "status":      str(o.status),
                    "order_type":  str(o.order_type),
                    "created_at":  str(o.created_at),
                }
                for o in orders
            ]
        except Exception as e:
            logger.error(f"get_open_orders: {e}")
            return []

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