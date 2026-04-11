"""
Tradier Broker Adapter — implements same interface as AlpacaClient.
"""
import logging
from typing import Optional
import httpx
import pandas as pd

logger = logging.getLogger(__name__)

TRADIER_BASE  = "https://api.tradier.com/v1"
TRADIER_PAPER = "https://sandbox.tradier.com/v1"


class TradierClient:
    def __init__(self, access_token: str, account_id: str, sandbox: bool = False):
        self.token      = access_token
        self.account_id = account_id
        self.base_url   = TRADIER_PAPER if sandbox else TRADIER_BASE
        self._headers   = {
            "Authorization": f"Bearer {self.token}",
            "Accept":        "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        try:
            r = httpx.get(f"{self.base_url}{path}", headers=self._headers, params=params, timeout=10)
            return r.json() if r.status_code == 200 else {}
        except Exception as e:
            logger.error(f"Tradier GET {path}: {e}")
            return {}

    def get_account(self) -> dict:
        data = self._get(f"/accounts/{self.account_id}/balances")
        bal  = data.get("balances", {})
        return {
            "equity":        bal.get("total_equity", 0),
            "cash":          bal.get("cash", {}).get("cash_available", 0),
            "buying_power":  bal.get("margin", {}).get("stock_buying_power", bal.get("cash", {}).get("cash_available", 0)),
            "currency":      "USD",
        }

    def get_positions(self) -> list:
        data = self._get(f"/accounts/{self.account_id}/positions")
        pos  = data.get("positions", {}).get("position", [])
        if isinstance(pos, dict):
            pos = [pos]
        return [
            {
                "symbol":          p.get("symbol"),
                "qty":             abs(p.get("quantity", 0)),
                "side":            "long" if p.get("quantity", 0) > 0 else "short",
                "avg_entry":       p.get("cost_basis", 0) / abs(p.get("quantity", 1)),
                "current_price":   p.get("cost_basis", 0) / abs(p.get("quantity", 1)),
                "unrealized_pnl":  0,
            }
            for p in pos
        ]

    def place_market_order(self, symbol: str, qty: float, side: str) -> dict:
        try:
            r = httpx.post(
                f"{self.base_url}/accounts/{self.account_id}/orders",
                headers={**self._headers, "Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "class":    "equity",
                    "symbol":   symbol,
                    "side":     side.lower(),
                    "quantity": int(qty),
                    "type":     "market",
                    "duration": "day",
                },
                timeout=10,
            )
            data = r.json()
            order = data.get("order", {})
            if order.get("status") == "ok":
                return {"id": str(order.get("id")), "status": "submitted"}
            return {"error": str(data)}
        except Exception as e:
            return {"error": str(e)}

    def get_orders(self, limit: int = 50) -> list:
        data = self._get(f"/accounts/{self.account_id}/orders")
        orders = data.get("orders", {}).get("order", [])
        if isinstance(orders, dict):
            orders = [orders]
        return orders[:limit]

    def get_bars(self, symbol: str, timeframe: str = "5Min", limit: int = 200) -> pd.DataFrame:
        interval = "5min" if "5" in timeframe else "1min" if "1" in timeframe else "daily"
        data = self._get("/markets/history", {
            "symbol":   symbol,
            "interval": interval,
            "limit":    limit,
        })
        days = data.get("history", {}).get("day", [])
        if not days:
            return pd.DataFrame()
        df = pd.DataFrame(days)
        df["timestamp"] = pd.to_datetime(df.get("date", df.get("time")))
        df = df.rename(columns={"open":"open","high":"high","low":"low","close":"close","volume":"volume"})
        df = df.set_index("timestamp")
        return df

    def get_latest_price(self, symbol: str) -> float:
        data = self._get("/markets/quotes", {"symbols": symbol})
        quotes = data.get("quotes", {}).get("quote", {})
        if isinstance(quotes, list):
            quotes = quotes[0]
        return float(quotes.get("last", 0))

    def is_market_open(self) -> bool:
        data = self._get("/markets/clock")
        return data.get("clock", {}).get("state") == "open"

    def close_all_positions(self): pass
    def close_position(self, symbol: str) -> dict: return self.place_market_order(symbol, 1, "sell")
    def get_signals(self) -> list: return []
