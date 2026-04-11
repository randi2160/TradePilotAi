import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_MODE       = os.getenv("ALPACA_MODE", "paper")
PAPER_URL         = "https://paper-api.alpaca.markets"
LIVE_URL          = "https://api.alpaca.markets"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL",   "gpt-4o")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./autotrader.db")

JWT_SECRET_KEY     = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM      = os.getenv("JWT_ALGORITHM",  "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
ALERT_FROM_EMAIL = os.getenv("ALERT_FROM_EMAIL", "alerts@autotrader.local")

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173"
).split(",")

CAPITAL          = float(os.getenv("CAPITAL",          "5000"))
DAILY_TARGET_MIN = float(os.getenv("DAILY_TARGET_MIN", "100"))
DAILY_TARGET_MAX = float(os.getenv("DAILY_TARGET_MAX", "250"))
MAX_DAILY_LOSS   = float(os.getenv("MAX_DAILY_LOSS",   "150"))

DEFAULT_WATCHLIST = [
    "AAPL","MSFT","NVDA","TSLA","AMD",
    "SPY","QQQ","AMZN","META","GOOGL",
    "NFLX","COIN","MSTR","PLTR","SOFI",
]

MAX_POSITION_PCT       = 0.20
MIN_CONFIDENCE_SCORE   = 0.55
MAX_OPEN_POSITIONS     = 3
ATR_STOP_MULTIPLIER    = 2.0
ATR_TARGET_MULTIPLIER  = 5.0

SCAN_INTERVAL     = 30
LLM_CALL_INTERVAL = 30

STOP_NEW_TRADES_HOUR   = 15
STOP_NEW_TRADES_MINUTE = 30
