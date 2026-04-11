#!/bin/bash
# AutoTrader Pro — AWS Lightsail Setup Script
# Run this ONCE on a fresh Ubuntu 22.04 Lightsail instance
# Usage: chmod +x setup.sh && ./setup.sh

set -e
echo "🚀 AutoTrader Pro — AWS Lightsail Setup"
echo "========================================"

# ── System updates ─────────────────────────────────────────────────────────────
echo "📦 Updating system..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl nginx certbot python3-certbot-nginx ufw

# ── Python 3.11 ───────────────────────────────────────────────────────────────
echo "🐍 Installing Python..."
sudo apt install -y python3.11 python3.11-venv python3-pip

# ── Node.js 20 ────────────────────────────────────────────────────────────────
echo "📦 Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# ── PM2 ───────────────────────────────────────────────────────────────────────
echo "⚙️ Installing PM2..."
sudo npm install -g pm2

# ── PostgreSQL ────────────────────────────────────────────────────────────────
echo "🗄️ Installing PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database and user
echo "Creating database..."
sudo -u postgres psql << 'EOSQL'
CREATE USER autotrader WITH PASSWORD 'ChangeMeStrong123!';
CREATE DATABASE autotrader OWNER autotrader;
GRANT ALL PRIVILEGES ON DATABASE autotrader TO autotrader;
EOSQL

# ── Firewall ──────────────────────────────────────────────────────────────────
echo "🔒 Configuring firewall..."
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

# ── App directory ─────────────────────────────────────────────────────────────
echo "📁 Setting up app directory..."
sudo mkdir -p /var/www/autotrader
sudo chown $USER:$USER /var/www/autotrader

echo ""
echo "✅ System setup complete!"
echo ""
echo "Next steps:"
echo "  1. Upload your code: git clone your-repo /var/www/autotrader"
echo "  2. Run: cd /var/www/autotrader && ./deploy/deploy.sh"
echo "  3. Configure Nginx: sudo cp deploy/nginx.conf /etc/nginx/sites-available/autotrader"
echo "  4. Set up SSL: sudo certbot --nginx -d yourdomain.com"
