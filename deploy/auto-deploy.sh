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
#
# EVERY UNIT THAT SERVES A LIVE SITE. Since the split on 27 Sep each domain has its own app, and
# this loop still rolled only sarathi-web@1/2 (8001/8002) - the old combined app, which no longer
# answers for either domain. So a deploy pulled the new code, restarted nothing anybody was using,
# and printed "complete". The claimant portal stayed broken for two days partly because of it, and
# the fix on 28 Sep had to be rolled by hand.
#
#   nidaan-web@N       8031/8032   nidaanpartner.com   (nidaan_app.py)
#   sarathi-new-web@N  8021/8022   sarathi-ai.com      (sarathi_app.py)
#   sarathi-web@N      8001/8002   the old combined app, kept as a rollback
#
# A unit that is not installed is SKIPPED WITH A LINE SAYING SO, never silently: during a
# migration the set changes, and "I did not roll that one" has to be visible in the log or this
# whole class of fault comes straight back.
roll() {
    local unit_prefix="$1" base_port="$2" label="$3"
    if ! systemctl list-unit-files | grep -q "^${unit_prefix}@"; then
        echo "  - ${label}: no ${unit_prefix}@ unit installed, skipping"
        return 0
    fi
    for inst in 1 2; do
        local unit="${unit_prefix}@${inst}" port=$((base_port + inst))
        if ! systemctl is-enabled --quiet "$unit" 2>/dev/null            && ! systemctl is-active --quiet "$unit" 2>/dev/null; then
            echo "  - $unit is neither enabled nor running, skipping"
            continue
        fi
        echo "Rolling $unit (port $port)…"
        if ! sudo -n systemctl restart "$unit"; then
            # The deploy user is granted each unit BY NAME in /etc/sudoers.d/sarathi-deploy.
            # A unit added later is not in that list, and the restart fails with a password
            # prompt. Fail loudly with the fix rather than cryptically: a deploy that cannot
            # load the code must stop, but it should say exactly why.
            echo "  !! not allowed to restart $unit."
            echo "     Add it to /etc/sudoers.d/sarathi-deploy (validate with: visudo -c -f <file>):"
            echo "       /usr/bin/systemctl restart $unit"
            exit 1
        fi
        wait_health "$port" || exit 1
    done
}

roll nidaan-web      8030 "nidaanpartner.com"
roll sarathi-new-web 8020 "sarathi-ai.com"
roll sarathi-web     8000 "old combined app (rollback)"

echo "=== $(date '+%F %T') Rolling deploy complete ==="

# deploy-automation self-test: 20260615T192415Z
