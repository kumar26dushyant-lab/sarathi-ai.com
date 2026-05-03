#!/usr/bin/env bash
# =============================================================================
#  auto-deploy.sh — Called by /internal/deploy webhook after each git push
#  Runs as the sarathi service user (sudoers allows: systemctl restart sarathi)
# =============================================================================
set -euo pipefail

APP_DIR=/opt/sarathi
LOG=/tmp/sarathi-deploy.log

echo "=== $(date '+%Y-%m-%d %H:%M:%S') Deploy started ===" | tee -a "$LOG"

# Pull latest code
git -C "$APP_DIR" fetch origin master              2>&1 | tee -a "$LOG"
git -C "$APP_DIR" reset --hard origin/master       2>&1 | tee -a "$LOG"
echo "Deployed: $(git -C $APP_DIR log --oneline -1)" | tee -a "$LOG"

# Syntax check
"$APP_DIR/venv/bin/python" -c "
import ast
with open('$APP_DIR/sarathi_biz.py', encoding='utf-8') as f:
    ast.parse(f.read())
print('Syntax OK')
" 2>&1 | tee -a "$LOG"

# DB migration (idempotent)
"$APP_DIR/venv/bin/python" -c "
import asyncio, sys
sys.path.insert(0, '$APP_DIR')
from biz_database import init_db
asyncio.run(init_db())
print('DB OK')
" 2>&1 | tee -a "$LOG"

# Kill the current process — systemd will auto-restart it
echo "Restarting sarathi service..." | tee -a "$LOG"
pkill -SIGTERM -f "python.*sarathi_biz" 2>/dev/null || true

# Poll until the app comes back online
echo "Waiting for service to restart..." | tee -a "$LOG"
for i in 1 2 3 4 5 6 7 8; do
    CODE=$(curl -sk -o /dev/null -w '%{http_code}' https://sarathi-ai.com/ 2>/dev/null || echo "000")
    if [ "$CODE" = "200" ]; then
        echo "Service UP after restart (HTTP $CODE)" | tee -a "$LOG"
        break
    fi
    echo "Attempt $i: HTTP $CODE, waiting 5s..." | tee -a "$LOG"
    sleep 5
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') Deploy complete ===" | tee -a "$LOG"
