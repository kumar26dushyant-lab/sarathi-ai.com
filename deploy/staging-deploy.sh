#!/usr/bin/env bash
# =============================================================================
#  staging-deploy.sh — deploy the STAGING environment (isolated, port 8003)
# =============================================================================
#  Staging is a parallel install at /opt/sarathi-staging on the `staging`
#  branch. It is WEB-ONLY (no worker → no bot/scheduler), uses its OWN DB
#  (sarathi_staging.db via SARATHI_DB_PATH) and its OWN neutralized biz.env
#  (no live Razorpay / SMTP / WhatsApp / Telegram / push keys), so nothing on
#  staging can charge money or message real people.
#
#  Sequence: pull origin/staging → syntax-check → migrate the STAGING db once →
#  restart the single staging web unit, gated on /health (port 8003).
# =============================================================================
set -euo pipefail
APP_DIR=/opt/sarathi-staging
PORT=8003
cd "$APP_DIR"

echo "=== $(date '+%F %T') STAGING deploy starting ==="

git -C "$APP_DIR" fetch origin staging
git -C "$APP_DIR" reset --hard origin/staging
echo "Code: $(git -C "$APP_DIR" log --oneline -1)"

# Interpreter is shared with prod (identical deps); only the app dir differs.
PY=/opt/sarathi/venv/bin/python

# Syntax gate — abort before touching the running staging process.
"$PY" -c "import ast; ast.parse(open('$APP_DIR/sarathi_biz.py', encoding='utf-8').read()); print('Syntax OK')"

# Idempotent migration against the STAGING db (env from the staging unit file).
set -a; . "$APP_DIR/biz.env"; set +a
"$PY" -c "
import asyncio, os, sys
os.chdir('$APP_DIR'); sys.path.insert(0, '$APP_DIR')
from biz_database import init_db
asyncio.run(init_db())
print('Staging DB OK:', os.getenv('SARATHI_DB_PATH'))
"

echo "Restarting staging web (port $PORT)…"
sudo systemctl restart sarathi-web-staging
for _ in $(seq 1 40); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" 2>/dev/null || echo 000)
    [ "$code" = "200" ] && { echo "  ✓ staging healthy on $PORT"; break; }
    sleep 1
done
echo "=== $(date '+%F %T') STAGING deploy complete ==="
