#!/bin/bash
# =============================================================================
#  Sarathi-AI — Pre-Resize Safety Backup
#  Run THIS SCRIPT on the server BEFORE stopping the VM in OCI Console.
#  Creates a full snapshot of DB + uploads + config.
#
#  Usage:  ssh -i key.pem ubuntu@YOUR_IP
#          sudo bash /opt/sarathi/deploy/pre-resize-backup.sh
# =============================================================================

set -euo pipefail

SARATHI_DIR="/opt/sarathi"
BACKUP_DIR="$SARATHI_DIR/backups/pre-resize"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "====================================================="
echo "  Sarathi-AI — Pre-Resize Backup ($TIMESTAMP)"
echo "====================================================="

mkdir -p "$BACKUP_DIR"
ARCHIVE="$BACKUP_DIR/pre_resize_${TIMESTAMP}.tar.gz"
TMP="/tmp/sarathi-pre-resize-${TIMESTAMP}"
mkdir -p "$TMP"

echo "[1/4] Backing up database (online backup)..."
sqlite3 "$SARATHI_DIR/sarathi_biz.db" ".backup '${TMP}/sarathi_biz.db'"
echo "      DB size: $(du -sh ${TMP}/sarathi_biz.db | cut -f1)"

echo "[2/4] Backing up biz.env (environment config)..."
cp "$SARATHI_DIR/biz.env" "$TMP/biz.env.bak"

echo "[3/4] Backing up uploads and generated files..."
for DIR in uploads generated_pdfs generated_videos; do
    SRC="$SARATHI_DIR/$DIR"
    [ -d "$SRC" ] && cp -r "$SRC" "$TMP/$DIR" && echo "      $DIR: $(du -sh $TMP/$DIR | cut -f1)"
done

echo "[4/4] Compressing archive..."
tar -czf "$ARCHIVE" -C /tmp "sarathi-pre-resize-${TIMESTAMP}"
rm -rf "$TMP"
echo "      Archive: $ARCHIVE ($(du -sh $ARCHIVE | cut -f1))"

echo ""
echo "====================================================="
echo "  Pre-resize backup COMPLETE"
echo "====================================================="
echo ""
echo "  Backup saved at: $ARCHIVE"
echo ""
echo "  NEXT STEPS:"
echo "  1. Note this backup location"
echo "  2. Go to OCI Console → Compute → Instances → sarathi-ai"
echo "  3. Click 'Stop' (wait for Stopped state)"
echo "  4. Click 'Edit shape' → VM.Standard.A1.Flex → 4 OCPU / 24 GB RAM"
echo "  5. Click 'Save changes'"
echo "  6. Click 'Start'"
echo "  7. SSH back in and run: sudo bash /opt/sarathi/deploy/post-resize-verify.sh"
echo ""
