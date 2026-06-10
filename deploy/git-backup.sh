#!/bin/bash
# =============================================================================
#  Sarathi-AI — GitHub Code Backup Script
#  Pushes the latest code to the private GitHub repo every 6 hours.
#  Run via systemd timer (see git-backup.timer).
#
#  One-time setup on the server:
#    git config --global user.email "kumar26.dushyant@gmail.com"
#    git config --global user.name "Sarathi Server"
#    git remote set-url origin https://<GITHUB_PAT>@github.com/kumar26dushyant-lab/sarathi-ai.com.git
#    git remote -v   # verify
# =============================================================================

set -euo pipefail

SARATHI_DIR="/opt/sarathi"
LOG_FILE="$SARATHI_DIR/logs/git-backup.log"
GITHUB_REPO="https://github.com/kumar26dushyant-lab/sarathi-ai.com.git"

mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

cd "$SARATHI_DIR"

# Verify this is a git repo (initialise if not)
if [ ! -d ".git" ]; then
    log "Initialising git repo in $SARATHI_DIR..."
    git init
    git remote add origin "$GITHUB_REPO" 2>/dev/null || git remote set-url origin "$GITHUB_REPO"
fi

# Make sure the remote URL uses the PAT stored in the env (set via biz.env or environment)
if [ -n "${GITHUB_PAT:-}" ]; then
    AUTHED_URL="https://${GITHUB_PAT}@github.com/kumar26dushyant-lab/sarathi-ai.com.git"
    git remote set-url origin "$AUTHED_URL" 2>/dev/null || true
fi

log "=== Git backup started ==="

# Stage everything (respects .gitignore — DB and .env are excluded)
git add -A

# Only commit if there are actual changes
if git diff --cached --quiet; then
    log "No changes to commit — skipping push"
    exit 0
fi

COMMIT_MSG="auto-backup: $(date '+%Y-%m-%d %H:%M') [server]"
git commit -m "$COMMIT_MSG"

# Push — retry once on transient failure
if ! git push origin master 2>>"$LOG_FILE"; then
    log "Push failed, retrying in 30s..."
    sleep 30
    git push origin master 2>>"$LOG_FILE"
fi

log "=== Git backup pushed: $COMMIT_MSG ==="
