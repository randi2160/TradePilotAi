# AutoTrader Pro v4 — Complete Setup Guide

## ✅ What's Now Production Ready
- JWT Login / Signup / User Profiles
- PostgreSQL database (all trades, history persist)
- SendGrid email alerts (trade fills, targets, stop losses)
- Rate limiting (60 req/min per IP)
- CORS locked to your domain
- Bcrypt password hashing
- Per-trade cost breakdown (position value, risk $, slippage)
- Manual trade placement from UI
- Backtesting engine with grade (A/B/C/D)
- PDT rule tracker
- Performance dashboard (wins/losses, profit factor, P&L by symbol)
- PM2 process manager (auto-restart on crash)
- Nginx reverse proxy config
- AWS Lightsail deployment scripts
- Daily database backups

---

## 🖥️ Local Development Setup

### 1. Database (PostgreSQL)
```bash
# Install PostgreSQL locally or use Docker:
docker run -d \
  --name autotrader-db \
  -e POSTGRES_USER=autotrader \
  -e POSTGRES_PASSWORD=autotrader \
  -e POSTGRES_DB=autotrader \
  -p 5432:5432 \
  postgres:15

# OR use SQLite for quick local testing — change DATABASE_URL to:
# DATABASE_URL=sqlite:///./autotrader.db
```

### 2. Backend
```powershell
cd backend
cp .env.example .env
# Edit .env with your keys

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
# → http://localhost:8000
# → Swagger UI: http://localhost:8000/docs
```

### 3. Frontend
```powershell
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### 4. First Login
- Open http://localhost:3000
- Click "Create Account"
- Register with your email
- Go to Profile tab → add Alpaca API keys
- Go to Bot tab → Start Bot (Paper mode)

---

## ☁️ AWS Lightsail Production Deployment

### Step 1 — Create Lightsail Instance
1. Go to AWS Lightsail → Create Instance
2. Select: **Linux/Unix** → **Ubuntu 22.04**
3. Plan: **$10/month** (2GB RAM, 2 vCPU)
4. Name it: `autotrader-pro`
5. Open ports: **80, 443, 22** in the Firewall tab

### Step 2 — Run Setup Script
```bash
# SSH into your instance
ssh ubuntu@YOUR_IP

# Upload and run setup script
scp deploy/setup.sh ubuntu@YOUR_IP:~/
ssh ubuntu@YOUR_IP
chmod +x setup.sh && ./setup.sh
```

### Step 3 — Deploy Code
```bash
# On the server
cd /var/www/autotrader
git clone https://github.com/yourusername/autotrader .

# OR upload via SCP:
# scp -r ./autotrader ubuntu@YOUR_IP:/var/www/autotrader
```

### Step 4 — Configure Environment
```bash
cd /var/www/autotrader/backend
cp .env.example .env
nano .env   # Fill in all your keys

# Generate a strong JWT secret:
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Step 5 — Backend Setup
```bash
cd /var/www/autotrader/backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test it works:
python main.py &
curl http://localhost:8000/health
kill %1
```

### Step 6 — Frontend Build
```bash
cd /var/www/autotrader/frontend
npm install
npm run build
# Creates dist/ folder for Nginx to serve
```

### Step 7 — Nginx
```bash
sudo cp /var/www/autotrader/deploy/nginx.conf /etc/nginx/sites-available/autotrader
sudo ln -s /etc/nginx/sites-available/autotrader /etc/nginx/sites-enabled/
# Edit nginx.conf and replace yourdomain.com with your actual domain
sudo nano /etc/nginx/sites-available/autotrader
sudo nginx -t && sudo systemctl reload nginx
```

### Step 8 — SSL (HTTPS)
```bash
# Point your domain's DNS A record to your Lightsail IP first
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### Step 9 — PM2 Process Manager
```bash
sudo mkdir -p /var/log/autotrader
sudo chown ubuntu:ubuntu /var/log/autotrader

cd /var/www/autotrader
pm2 start deploy/ecosystem.config.cjs
pm2 save
pm2 startup   # follow the printed command to enable auto-start
```

### Step 10 — Database Backups
```bash
chmod +x /var/www/autotrader/deploy/backup.sh
# Add to crontab (runs daily at 2 AM):
crontab -e
# Add this line:
0 2 * * * /var/www/autotrader/deploy/backup.sh >> /var/log/autotrader/backup.log 2>&1
```

---

## 🔐 Security Checklist (before going live)

- [ ] JWT_SECRET_KEY is a random 64-char string (not the default)
- [ ] DATABASE_URL uses a strong password
- [ ] ALLOWED_ORIGINS is set to your domain only (not *)
- [ ] .env file is NOT in git (add to .gitignore)
- [ ] Lightsail firewall only allows ports 22, 80, 443
- [ ] SSL certificate installed (HTTPS)
- [ ] PM2 running and auto-restart enabled

---

## 📱 Monitoring

```bash
# View live logs
pm2 logs autotrader-api

# Check status
pm2 status

# Restart after code update
git pull && cd frontend && npm run build && pm2 restart autotrader-api

# Database backup now
./deploy/backup.sh
```

---

## 📊 Swagger UI
Once running, visit: `https://yourdomain.com/docs`
All 40+ endpoints documented and testable.

---

## ⚠️ Important Notes
- Start with PAPER mode — trade for 2-4 weeks before going live
- Check the Backtester (Performance tab) — need Grade A or B before live
- Watch PDT status — max 3 day trades per 5 days with < $25K
- Email alerts require a free SendGrid account at sendgrid.com
- OpenAI API key needed for GPT-4 advisor ($0.01-0.05 per analysis)
