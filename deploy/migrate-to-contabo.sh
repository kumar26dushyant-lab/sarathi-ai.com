#!/bin/bash
# =============================================================================
#  Sarathi-AI — Restore Oracle backup onto Contabo
#  Run on the Contabo server AFTER setup-contabo.sh completes.
#
#  The backup tar.gz must already be at /tmp/sarathi-backup.tar.gz
#  (copied there from Windows via scp before running this script)
#
#  Usage:
#    On Contabo server:  bash /opt/sarathi/deploy/migrate-to-contabo.sh
# =============================================================================

set -euo pipefail

APP_DIR="/opt/sarathi"
APP_USER="sarathi"
BACKUP_FILE="/tmp/sarathi-backup.tar.gz"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[$(date +%H:%M:%S)] ✔ $*${NC}"; }
warn() { echo -e "${YELLOW}[WARN] $*${NC}"; }
err()  { echo -e "${RED}[ERROR] $*${NC}"; exit 1; }

[[ $EUID -ne 0 ]] && err "Run as root"
[[ ! -f "$BACKUP_FILE" ]] && err "Backup not found at $BACKUP_FILE\nCopy it first:\n  scp -i <key> ubuntu@140.238.246.0:/tmp/sarathi-migration-*.tar.gz C:\\Users\\imdus\\Downloads\\\n  scp C:\\Users\\imdus\\Downloads\\sarathi-migration-*.tar.gz root@CONTABO_IP:/tmp/sarathi-backup.tar.gz"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Sarathi-AI — Oracle → Contabo Migration        ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Stop service before touching DB
log "Stopping sarathi service..."
systemctl stop sarathi 2>/dev/null || true

# Backup current state (safety)
log "Backing up current state..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p $APP_DIR/backups
[[ -f "$APP_DIR/sarathi_biz.db" ]] && cp $APP_DIR/sarathi_biz.db $APP_DIR/backups/pre-migration-${TIMESTAMP}.db
[[ -f "$APP_DIR/biz.env" ]]        && cp $APP_DIR/biz.env        $APP_DIR/backups/biz.env.${TIMESTAMP}.bak

# Extract backup
log "Extracting backup from Oracle..."
EXTRACT_DIR="/tmp/sarathi-restore-${TIMESTAMP}"
mkdir -p "$EXTRACT_DIR"
tar xzf "$BACKUP_FILE" -C "$EXTRACT_DIR"

# Show what's in the backup
echo ""
echo "Contents of backup:"
ls -lh "$EXTRACT_DIR/"
echo ""

# Restore DB
if [[ -f "$EXTRACT_DIR/sarathi_biz.db" ]]; then
    cp "$EXTRACT_DIR/sarathi_biz.db" "$APP_DIR/sarathi_biz.db"
    chown $APP_USER:$APP_USER "$APP_DIR/sarathi_biz.db"
    chmod 640 "$APP_DIR/sarathi_biz.db"
    log "Database restored ($(du -sh $APP_DIR/sarathi_biz.db | cut -f1))"
else
    warn "No sarathi_biz.db found in backup — starting with fresh database"
fi

# Restore uploads
if [[ -d "$EXTRACT_DIR/uploads" ]]; then
    cp -r "$EXTRACT_DIR/uploads/." "$APP_DIR/uploads/"
    chown -R $APP_USER:$APP_USER "$APP_DIR/uploads/"
    log "Uploads restored ($(du -sh $APP_DIR/uploads | cut -f1))"
else
    warn "No uploads directory in backup"
fi

# Restore generated_pdfs
if [[ -d "$EXTRACT_DIR/generated_pdfs" ]]; then
    cp -r "$EXTRACT_DIR/generated_pdfs/." "$APP_DIR/generated_pdfs/"
    chown -R $APP_USER:$APP_USER "$APP_DIR/generated_pdfs/"
    log "Generated PDFs restored"
fi

# Restore biz.env — but warn to review it
if [[ -f "$EXTRACT_DIR/biz.env" ]]; then
    warn "biz.env found in backup — NOT overwriting (you may have already configured it)"
    warn "Review and merge manually if needed:"
    warn "  diff $APP_DIR/biz.env $EXTRACT_DIR/biz.env"
fi

# Cleanup
rm -rf "$EXTRACT_DIR"
log "Cleanup done"

# Restart service
log "Starting sarathi service..."
systemctl start sarathi
sleep 3

# Health check
if systemctl is-active --quiet sarathi; then
    log "Service is running"
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health 2>/dev/null || echo "000")
    if [[ "$HTTP" == "200" ]]; then
        log "Health check passed (HTTP 200)"
    else
        warn "Health check returned HTTP $HTTP — check logs: journalctl -u sarathi -f"
    fi
else
    err "Service failed to start — check: journalctl -u sarathi -n 50"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   ✅ Migration complete!                                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Quick checks:"
echo "  journalctl -u sarathi -f          # live logs"
echo "  curl http://localhost:8001/health  # app health"
echo "  systemctl status sarathi           # service status"
echo ""
