#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# AutoTrader Pro — one-shot rollout for the AWS Lightsail box.
#
# What it does, in order:
#   1. Pulls the latest code from GitHub.
#   2. Re-installs Python deps inside the venv.
#   3. Builds the frontend and copies dist/ into place.
#   4. Runs Base.metadata.create_all() against the current DATABASE_URL — this
#      auto-creates any new columns/tables (ladder columns on trades, ladder
#      settings on protection_settings, etc.).
#   5. Promotes khemlall.mangal@gmail.com to is_admin=True in Postgres.
#   6. Restarts the API + bot via PM2 and prints status.
#
# Run from the repo root (/var/www/autotrader) after logging into the box:
#
#   cd /var/www/autotrader
#   chmod +x deploy/rollout.sh
#   ./deploy/rollout.sh
#
# Safe to run repeatedly — every step is idempotent.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ADMIN_EMAIL="${ADMIN_EMAIL:-khemlall.mangal@gmail.com}"
BRANCH="${BRANCH:-main}"

echo "════════════════════════════════════════════════════════════════════"
echo " AutoTrader Pro — rollout"
echo " Repo:    $REPO_ROOT"
echo " Branch:  $BRANCH"
echo " Admin:   $ADMIN_EMAIL"
echo "════════════════════════════════════════════════════════════════════"

# ── 1. Pull latest code ──────────────────────────────────────────────────────
echo ""
echo "▶ [1/6] git pull origin $BRANCH"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

# ── 2. Python deps ───────────────────────────────────────────────────────────
echo ""
echo "▶ [2/6] Installing Python deps"
if [ ! -d backend/venv ]; then
  python3.11 -m venv backend/venv
fi
# shellcheck disable=SC1091
source backend/venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# ── 3. Frontend build ────────────────────────────────────────────────────────
echo ""
echo "▶ [3/6] Building frontend"
pushd frontend >/dev/null
npm ci --no-audit --no-fund
npm run build
popd >/dev/null

# ── 4. DB migrations ─────────────────────────────────────────────────────────
# Two passes, because create_all() only creates MISSING tables — it never
# ALTERs existing ones. The ladder migration adds new columns to tables that
# already exist in prod.
echo ""
echo "▶ [4/6] Applying schema"
pushd backend >/dev/null
python - <<'PY'
from database.database import init_db, get_db_type, DATABASE_URL
def _mask(u):
    if "://" not in u or "@" not in u: return u
    s, r = u.split("://", 1); c, h = r.split("@", 1)
    if ":" in c: u2, _ = c.split(":", 1); c = f"{u2}:***"
    return f"{s}://{c}@{h}"
print(f"  DB: {get_db_type()}  —  {_mask(DATABASE_URL)}")
init_db()
print("  ✓ base schema up to date (missing tables created)")
PY
python migrate_ladder.py

# ── 5. Promote admin ─────────────────────────────────────────────────────────
echo ""
echo "▶ [5/6] Ensuring $ADMIN_EMAIL is admin"
python promote_admin.py "$ADMIN_EMAIL"
popd >/dev/null

# ── 6. Restart services ──────────────────────────────────────────────────────
echo ""
echo "▶ [6/6] Restarting PM2 services"
pm2 reload deploy/ecosystem.config.cjs --update-env || pm2 start deploy/ecosystem.config.cjs
pm2 save
pm2 status

echo ""
echo "✅ Rollout complete."
echo "   • Latest code pulled from $BRANCH"
echo "   • Schema migrated (ladder columns + settings present)"
echo "   • $ADMIN_EMAIL is admin"
echo "   • API + bot reloaded"
