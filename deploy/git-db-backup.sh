#!/usr/bin/env bash
# Off-server ENCRYPTED DB backup → private repo kumar26dushyant-lab/sarathi-db-backups.
# Hot sqlite .backup → gzip → AES-256-CBC (pbkdf2, iter 200000, key from biz.env
# BACKUP_ENC_PASSPHRASE) → one overwritten blob sarathi_biz.db.gz.enc → commit + push.
# Runs as root via git-db-backup.service (git-db-backup.timer, 02:30 daily).
#
# NOTE: this file is now TRACKED IN GIT. It used to be a server-only (untracked) file and
# a deploy's `git clean` deleted it on 2026-07-22, silently breaking off-server backups
# for a day. Keeping it in the repo means a deploy restores it instead of removing it.
#
# Restore:  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
#             -in sarathi_biz.db.gz.enc -pass pass:PASSPHRASE | gunzip > sarathi_biz.db
set -euo pipefail

APP=/opt/sarathi
REPO="$APP/db-backup-repo"
DB="$APP/sarathi_biz.db"
KEY=/root/.ssh/id_backup_repo
REMOTE="git@github.com:kumar26dushyant-lab/sarathi-db-backups.git"
export GIT_SSH_COMMAND="ssh -i $KEY -o StrictHostKeyChecking=no"

PP=$(grep -m1 '^BACKUP_ENC_PASSPHRASE=' "$APP/biz.env" | cut -d= -f2- | tr -d "\r\n \t\"'")
if [ -z "${PP:-}" ]; then
  echo "ERROR: BACKUP_ENC_PASSPHRASE not set in $APP/biz.env" >&2
  exit 1
fi

# Ensure the backup-repo clone exists.
if [ ! -d "$REPO/.git" ]; then
  git clone "$REMOTE" "$REPO"
fi
cd "$REPO"
git pull --ff-only 2>/dev/null || true

# Consistent hot snapshot → gzip → AES-256 encrypt (overwrite the single blob).
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
sqlite3 "$DB" ".backup '$TMP'"
gzip -c "$TMP" | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
  -pass "pass:$PP" -out "$REPO/sarathi_biz.db.gz.enc"

git add sarathi_biz.db.gz.enc
git -c user.name="sarathi-backup" -c user.email="backup@nidaanpartner.com" \
    commit -q -m "db backup $(date -u +%Y%m%d_%H%M%S)"
git push -q origin HEAD
echo "off-server encrypted backup pushed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
