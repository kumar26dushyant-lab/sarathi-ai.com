#!/bin/bash
# =============================================================================
#  Sarathi-AI — Enhanced Backup Script
#  Backs up: SQLite DB + uploads/ + generated_pdfs/ + generated_videos/
#  Keeps 7 local daily copies. Run via systemd timer (see backup-db.timer).
# =============================================================================

set -euo pipefail

SARATHI_DIR="/opt/sarathi"
BACKUP_DIR="$SARATHI_DIR/backups"
DB_PATH="$SARATHI_DIR/sarathi_biz.db"
LOG_FILE="$SARATHI_DIR/logs/backup.log"
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="sarathi_backup_${TIMESTAMP}"
BACKUP_TMP="/tmp/${BACKUP_NAME}"
mkdir -p "$BACKUP_TMP"

log "=== Backup started: $TIMESTAMP ==="

# ── 1. SQLite DB (online backup — safe while app is running) ────────────────
log "[1/3] Backing up database..."
sqlite3 "$DB_PATH" ".backup '${BACKUP_TMP}/sarathi_biz.db'"
DB_SIZE=$(du -sh "${BACKUP_TMP}/sarathi_biz.db" | cut -f1)
log "      DB size: $DB_SIZE"

# ── 2. Uploads + media directories ─────────────────────────────────────────
log "[2/3] Backing up uploads and generated files..."
for DIR in uploads generated_pdfs generated_videos; do
    SRC="$SARATHI_DIR/$DIR"
    if [ -d "$SRC" ]; then
        cp -r "$SRC" "$BACKUP_TMP/$DIR"
        SIZE=$(du -sh "$BACKUP_TMP/$DIR" | cut -f1)
        log "      $DIR: $SIZE"
    fi
done

# ── 3. Compress everything ──────────────────────────────────────────────────
log "[3/3] Compressing..."
ARCHIVE="$BACKUP_DIR/${BACKUP_NAME}.tar.gz"
tar -czf "$ARCHIVE" -C /tmp "$BACKUP_NAME"
rm -rf "$BACKUP_TMP"
ARCHIVE_SIZE=$(du -sh "$ARCHIVE" | cut -f1)
log "      Archive: $ARCHIVE ($ARCHIVE_SIZE)"

# ── 4. OFFSITE copy (encrypted) — survives total server/disk loss ───────────
# The local backups above live on the SAME disk as the DB. For real DR, push an
# ENCRYPTED copy offsite. Configure in biz.env (sourced by the service):
#   BACKUP_GPG_PASSPHRASE  — symmetric encryption key (store it somewhere safe!)
#   BACKUP_RCLONE_REMOTE   — e.g. "b2:my-bucket/sarathi" (run `rclone config` first)
# Backups contain customer documents (PII) → encryption is mandatory (DPDP).
if [ -n "${BACKUP_GPG_PASSPHRASE:-}" ] && [ -n "${BACKUP_RCLONE_REMOTE:-}" ] \
   && command -v gpg >/dev/null && command -v rclone >/dev/null; then
    ENC="${ARCHIVE}.gpg"
    if gpg --batch --yes --passphrase "$BACKUP_GPG_PASSPHRASE" \
           --cipher-algo AES256 -c -o "$ENC" "$ARCHIVE" 2>>"$LOG_FILE"; then
        if rclone copy "$ENC" "$BACKUP_RCLONE_REMOTE" 2>>"$LOG_FILE"; then
            log "      Offsite ✓ $(basename "$ENC") → $BACKUP_RCLONE_REMOTE"
        else
            log "      ⚠️ Offsite rclone FAILED — check $LOG_FILE"
        fi
        rm -f "$ENC"
    else
        log "      ⚠️ Offsite gpg encryption FAILED"
    fi
else
    log "      (offsite skipped — set BACKUP_GPG_PASSPHRASE + BACKUP_RCLONE_REMOTE + install gpg/rclone)"
fi

# ── Prune old backups ───────────────────────────────────────────────────────
DELETED=$(find "$BACKUP_DIR" -name "sarathi_backup_*.tar.gz" -mtime +${KEEP_DAYS} -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && log "Pruned $DELETED backup(s) older than ${KEEP_DAYS} days"

log "=== Backup complete ==="
echo "$ARCHIVE"
