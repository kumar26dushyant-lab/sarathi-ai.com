#!/usr/bin/env bash
# =============================================================================
#  auto-deploy.sh — Called by /internal/deploy webhook after each git push
#  Runs as the sarathi service user. All output goes to LOG.
# =============================================================================
set -euo pipefail

APP_DIR=/opt/sarathi
LOG=/tmp/sarathi-deploy.log

# Redirect all stdout+stderr to the log file from now on
exec >> "$LOG" 2>&1

echo "=== $(date '+%Y-%m-%d %H:%M:%S') Deploy started ==="

# Must cd to app dir so relative paths (e.g. DB file) resolve correctly
cd "$APP_DIR"

# Pull latest code
git -C "$APP_DIR" fetch origin master
git -C "$APP_DIR" reset --hard origin/master
echo "Deployed: $(git -C "$APP_DIR" log --oneline -1)"

# Syntax check
"$APP_DIR/venv/bin/python" -c "
import ast
with open('$APP_DIR/sarathi_biz.py', encoding='utf-8') as f:
    ast.parse(f.read())
print('Syntax OK')
"

# DB migration (idempotent) — run from APP_DIR so DB path resolves
"$APP_DIR/venv/bin/python" -c "
import asyncio, sys, os
os.chdir('$APP_DIR')
sys.path.insert(0, '$APP_DIR')
from biz_database import init_db
asyncio.run(init_db())
print('DB OK')
"

# Kill the current process — systemd will auto-restart it
echo "Sending SIGTERM to sarathi process (systemd will restart)..."
pkill -SIGTERM -f "python.*sarathi_biz" || true

# Poll until the app comes back online
echo "Waiting for service to come back..."
for i in 1 2 3 4 5 6 7 8; do
    CODE=$(curl -sk -o /dev/null -w '%{http_code}' https://sarathi-ai.com/ 2>/dev/null || echo "000")
    if [ "$CODE" = "200" ]; then
        echo "Service UP (HTTP $CODE)"
        break
    fi
    echo "Attempt $i: HTTP $CODE, waiting 5s..."
    sleep 5
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') Deploy complete ==="
