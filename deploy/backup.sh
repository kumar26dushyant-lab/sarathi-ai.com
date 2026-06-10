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

# ── Prune old backups ───────────────────────────────────────────────────────
DELETED=$(find "$BACKUP_DIR" -name "sarathi_backup_*.tar.gz" -mtime +${KEEP_DAYS} -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && log "Pruned $DELETED backup(s) older than ${KEEP_DAYS} days"

log "=== Backup complete ==="
echo "$ARCHIVE"
