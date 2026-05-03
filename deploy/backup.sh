#!/bin/bash
# =============================================================================
#  Sarathi-AI — Daily Backup Script (SQLite → local compressed backup)
# =============================================================================
#  Add to crontab: sudo crontab -u sarathi -e
#  0 2 * * * /opt/sarathi/deploy/backup.sh
# =============================================================================

BACKUP_DIR="/opt/sarathi/backups"
DB_PATH="/opt/sarathi/sarathi_biz.db"
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

# Create timestamped backup using SQLite's .backup (safe for running DB)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/sarathi_biz_${TIMESTAMP}.db"

# Use SQLite's online backup API (safe even while app is running)
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Compress
gzip "$BACKUP_FILE"

# Remove backups older than KEEP_DAYS
find "$BACKUP_DIR" -name "*.db.gz" -mtime +$KEEP_DAYS -delete

echo "$(date): Backup created: ${BACKUP_FILE}.gz ($(du -h "${BACKUP_FILE}.gz" | cut -f1))"
