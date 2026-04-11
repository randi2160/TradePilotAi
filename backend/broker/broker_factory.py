"""
Broker Factory — returns the correct broker adapter for a user.
Supports: Alpaca (paper + live), Interactive Brokers, Tradier.
Users bring their own API keys. We never store credentials in plaintext.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_BROKERS = {
    "alpaca_paper": {
        "name":        "Alpaca (Paper Trading)",
        "description": "Free paper trading — practice with virtual money",
        "signup_url":  "https://app.alpaca.markets/signup",
        "docs_url":    "https://docs.alpaca.markets/reference/authentication-2",
        "fields":      ["api_key", "api_secret"],
        "commission":  "Free",
        "min_account": "$0",
        "features":    ["stocks", "paper_trading", "fractional"],
        "live":        False,
    },
    "alpaca_live": {
        "name":        "Alpaca (Live Trading)",
        "description": "Real money trading via Alpaca Markets",
        "signup_url":  "https://app.alpaca.markets/signup",
        "docs_url":    "https://docs.alpaca.markets/reference/authentication-2",
        "fields":      ["api_key", "api_secret"],
        "commission":  "$0/trade",
        "min_account": "$0 (PDT requires $25K for day trading)",
        "features":    ["stocks", "live_trading", "fractional", "options"],
        "live":        True,
    },
    "ibkr": {
        "name":        "Interactive Brokers",
        "description": "Professional-grade broker with global markets",
        "signup_url":  "https://www.interactivebrokers.com/en/trading/ibkr-lite.php",
        "docs_url":    "https://interactivebrokers.github.io/tws-api/",
        "fields":      ["client_id", "port", "host"],
        "commission":  "$0-$0.005/share",
        "min_account": "$0 (Lite) / $10K (Pro)",
        "features":    ["stocks", "options", "futures", "forex", "international"],
        "live":        True,
        "note":        "Requires TWS or IB Gateway running locally",
    },
    "tradier": {
        "name":        "Tradier",
        "description": "Developer-friendly broker with good API",
        "signup_url":  "https://brokerage.tradier.com/",
        "docs_url":    "https://documentation.tradier.com/",
        "fields":      ["access_token", "account_id"],
        "commission":  "$0/trade (Brokerage plan)",
        "min_account": "$0",
        "features":    ["stocks", "options", "live_trading"],
        "live":        True,
    },
}


def get_broker(broker_type: str, credentials: dict):
    """
    Returns the correct broker adapter instance for a user.
    All adapters implement the same interface as AlpacaClient.
    """
    if broker_type in ("alpaca_paper", "alpaca_live"):
        from broker.alpaca_client import AlpacaClient
        return AlpacaClient(
            paper      = (broker_type == "alpaca_paper"),
            api_key    = credentials.get("api_key"),
            api_secret = credentials.get("api_secret"),
        )
    elif broker_type == "tradier":
        from broker.tradier_client import TradierClient
        return TradierClient(
            access_token = credentials.get("access_token"),
            account_id   = credentials.get("account_id"),
        )
    elif broker_type == "ibkr":
        from broker.ibkr_client import IBKRClient
        return IBKRClient(
            host      = credentials.get("host", "127.0.0.1"),
            port      = int(credentials.get("port", 7497)),
            client_id = int(credentials.get("client_id", 1)),
        )
    else:
        raise ValueError(f"Unsupported broker: {broker_type}")


def get_supported_brokers() -> dict:
    return SUPPORTED_BROKERS