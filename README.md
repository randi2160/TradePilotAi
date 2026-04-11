# 📈 AutoTrader Pro

AI-powered automated stock trading bot with a live React dashboard.

**Capital:** $5,000 | **Daily Target:** $100–$250 | **Risk:** AI Dynamic

---

## 🚀 Quick Start

### Step 1 — Get Alpaca API Keys
1. Go to https://app.alpaca.markets
2. Left sidebar → **API**
3. Click **Generate New Key**
4. Copy your **API Key ID** and **Secret Key**

### Step 2 — Backend Setup
```bash
cd backend
cp .env.example .env
# Paste your keys into .env

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
# ✅ Backend running at http://localhost:8000
```

### Step 3 — Frontend Setup
```bash
cd frontend
npm install
npm run dev
# ✅ Dashboard at http://localhost:3000
```

### Step 4 — Start Trading
1. Open http://localhost:3000
2. Click the **⚙️ Bot** tab
3. Select **Paper** mode (recommended for testing)
4. Click **Start Bot**
5. Watch the dashboard for live signals and trades!

---

## 🏗️ Architecture

```
autotrader/
├── backend/
│   ├── main.py                  # FastAPI app (REST + WebSocket)
│   ├── config.py                # All settings
│   ├── requirements.txt
│   ├── .env.example
│   ├── broker/
│   │   └── alpaca_client.py     # Alpaca API wrapper
│   ├── data/
│   │   └── indicators.py        # RSI, MACD, BB, EMA, ATR, Stoch
│   ├── models/
│   │   └── ensemble.py          # GradientBoosting + RandomForest + Technical
│   ├── strategy/
│   │   ├── engine.py            # Trade lifecycle: scan→signal→enter→exit
│   │   ├── risk_manager.py      # Dynamic ATR-based position sizing
│   │   └── daily_target.py      # P&L tracker + kill-switch
│   └── scheduler/
│       └── bot_loop.py          # Main async trading loop
└── frontend/
    └── src/
        ├── App.jsx              # Main layout + tab navigation
        ├── components/
        │   ├── Dashboard.jsx    # P&L, progress, open positions
        │   ├── ChartView.jsx    # Candlestick chart + signal overlays
        │   ├── BotControls.jsx  # Start/Stop/Mode controls
        │   ├── TradeLog.jsx     # Trade history + CSV export
        │   └── Signals.jsx      # Live AI signal grid (all symbols)
        ├── hooks/
        │   └── useWebSocket.js  # Live data hook
        └── services/
            └── api.js           # REST API calls
```

---

## 🤖 AI Models

| Model | Role | Weight |
|---|---|---|
| Technical Indicators | RSI, MACD, BB, EMA cross, Stochastic | 40% |
| Gradient Boosting | Trained on historical bars | 35% |
| Random Forest | Trained on historical bars | 25% |

The ensemble combines all three into a single BUY/SELL/HOLD signal with confidence score.
ML models auto-train on startup using the last 1,000 bars of historical data.

---

## 🛡️ Safety Rules (always active)

- ✅ Bot stops when $250 max-target is hit
- ✅ Bot stops if daily loss exceeds $150
- ✅ No new trades after 3:30 PM ET
- ✅ All positions force-closed at 3:55 PM ET
- ✅ Max 3 open positions at any time
- ✅ Position size capped at 20% of capital

---

## ⚙️ Configuration (backend/.env)

```env
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_MODE=paper          # paper | live

CAPITAL=5000
DAILY_TARGET_MIN=100
DAILY_TARGET_MAX=250
MAX_DAILY_LOSS=150
```

---

## ⚠️ Disclaimer

This software is for educational purposes. Trading involves risk.
Always test thoroughly in paper mode before using real money.
Past performance does not guarantee future results.
