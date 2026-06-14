#!/usr/bin/env bash
# =============================================================================
#  auto-deploy-zerodowntime.sh — rolling deploy for the blue-green architecture
# =============================================================================
#  Replaces the old pkill-and-restart auto-deploy.sh once the worker + web units
#  and nginx upstream are in place (see deploy/ZERO_DOWNTIME_DEPLOY.md).
#
#  Sequence: pull → syntax-check → migrate ONCE → restart worker (background,
#  non-user-facing) → rolling-restart web@1 then web@2, each gated on /health.
#  At every instant ≥1 web instance is serving, so nginx never returns 502.
#
#  Needs passwordless systemctl for these units (sudoers snippet in the runbook).
# =============================================================================
set -euo pipefail
APP_DIR=/opt/sarathi
cd "$APP_DIR"

echo "=== $(date '+%F %T') Zero-downtime deploy starting ==="

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

# 1) Worker (bots + scheduler). Brief, NOT user-facing — public HTTP is unaffected.
echo "Restarting worker (singletons)…"
sudo systemctl restart sarathi-worker || echo "  (worker restart returned non-zero — check journal)"

# 2) Rolling restart of the web tier. One at a time, health-gated.
for inst in 1 2; do
    port=$((8000 + inst))
    echo "Rolling web@$inst (port $port)…"
    sudo systemctl restart "sarathi-web@$inst"
    wait_health "$port" || exit 1
done

echo "=== $(date '+%F %T') Zero-downtime deploy complete ==="
