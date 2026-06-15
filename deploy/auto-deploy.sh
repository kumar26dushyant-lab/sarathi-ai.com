#!/usr/bin/env bash
# =============================================================================
#  auto-deploy.sh — ROLLING (zero-downtime) deploy. Called by /internal/deploy.
# =============================================================================
#  IMPORTANT: this file is the canonical deploy script. The deploy does
#  `git reset --hard`, so whatever lives here in the repo is what runs — keep it
#  rolling (an earlier pkill-all version caused a both-down 502).
#
#  It is launched via sarathi-deploy.service (its OWN cgroup) so the rolling
#  web-instance restarts can't kill this script mid-roll. Sequence: pull →
#  syntax-check → migrate ONCE → restart worker → rolling-restart web@1 then
#  web@2, each gated on /health, so >=1 web instance is always serving → no 502.
#
#  Needs passwordless systemctl for the units (see /etc/sudoers.d/sarathi-deploy).
# =============================================================================
set -euo pipefail
APP_DIR=/opt/sarathi
cd "$APP_DIR"

echo "=== $(date '+%F %T') Rolling deploy starting ==="

git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
git -C "$APP_DIR" fetch origin master
git -C "$APP_DIR" reset --hard origin/master
echo "Code: $(git -C "$APP_DIR" log --oneline -1)"

# Syntax gate — abort BEFORE touching any running process if the code is broken.
"$APP_DIR/venv/bin/python" -c "
import ast
ast.parse(open('$APP_DIR/sarathi_biz.py', encoding='utf-8').read())
print('Syntax OK')
"

# Idempotent DB migration — run ONCE, before restarting anything.
"$APP_DIR/venv/bin/python" -c "
import asyncio, os, sys
os.chdir('$APP_DIR'); sys.path.insert(0, '$APP_DIR')
from biz_database import init_db
asyncio.run(init_db())
print('DB OK')
"

health() { curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$1/health" 2>/dev/null || echo 000; }
wait_health() {
    local port="$1"
    for _ in $(seq 1 40); do
        [ "$(health "$port")" = "200" ] && { echo "  ✓ port $port healthy"; return 0; }
        sleep 1
    done
    echo "  ✗ port $port NEVER became healthy — aborting (other instance still serving)"; return 1
}

# 1) Worker (bots + scheduler). Brief, NOT user-facing — public HTTP unaffected.
echo "Restarting worker (singletons)…"
sudo -n systemctl restart sarathi-worker || echo "  (worker restart non-zero — check journal)"

# 2) Rolling restart of the web tier. One at a time, health-gated → no 502.
for inst in 1 2; do
    port=$((8000 + inst))
    echo "Rolling web@$inst (port $port)…"
    sudo -n systemctl restart "sarathi-web@$inst"
    wait_health "$port" || exit 1
done

echo "=== $(date '+%F %T') Rolling deploy complete ==="

# deploy-automation self-test: 20260615T192415Z
