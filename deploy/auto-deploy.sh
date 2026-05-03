#!/usr/bin/env bash
# =============================================================================
#  auto-deploy.sh — Called by /internal/deploy webhook after each git push
#  Runs as the ubuntu user (no sudo needed for git since ubuntu owns /opt/sarathi)
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

# Restart service (ubuntu has NOPASSWD sudo on Oracle Cloud)
sudo systemctl restart sarathi
sleep 8
sudo systemctl is-active sarathi | tee -a "$LOG"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') Deploy complete ===" | tee -a "$LOG"
