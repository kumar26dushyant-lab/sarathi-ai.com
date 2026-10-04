#!/bin/bash
# =============================================================================
#  Sarathi-AI / NidaanPartner — nightly backup (rewritten 3 Oct 2026)
# =============================================================================
#  WHAT, AND WHY IT CHANGED
#  It used to tar EVERYTHING every night (1.9 GB), keep seven on this disk
#  (14 GB of 45) and upload each one whole to the off-site bucket (12.4 GiB of
#  a 20 GB allowance). Both were filling with copies of files that never
#  change. Now:
#
#   1. DATABASE  - an online sqlite backup, integrity-checked, gzipped; seven
#                  kept here, and an encrypted copy off-site every night.
#   2. FILES     - a dated snapshot here (rsync --link-dest): a file that has
#                  not changed is shared with yesterday's snapshot, so seven
#                  days cost one copy plus what changed. Seven kept.
#   3. OFF-SITE  - deploy/offsite_files.py: each document goes once, AES-256-GCM
#                  encrypted; a changed file is a new version; nothing off-site
#                  is overwritten or deleted. Then a random sample is downloaded,
#                  decrypted and compared - a backup that cannot be restored is
#                  not a backup.
#
#  The old full archives (sarathi_backup_*.tar.gz here, *.tar.gz.gpg off-site)
#  age out under the same 7-day rule they always had - only those names.
#
#  Settings from biz.env: BACKUP_ENC_PASSPHRASE, BACKUP_RCLONE_REMOTE.
#  A failure exits non-zero so the unit shows as failed and App Health sees it.
# =============================================================================

set -euo pipefail

# BACKUP_REHEARSAL_DIR: a throwaway copy of the layout, for rehearsing this script end to end on
# the real machine without touching the live app. Never set in biz.env.
SARATHI_DIR="${BACKUP_REHEARSAL_DIR:-/opt/sarathi}"
BACKUP_DIR="$SARATHI_DIR/backups"
DB_PATH="$SARATHI_DIR/sarathi_biz.db"
LOG_FILE="$SARATHI_DIR/logs/backup.log"
PY="${BACKUP_PY:-/opt/sarathi/venv/bin/python}"
TOOL="/opt/sarathi/deploy/offsite_files.py"
if [ -n "${BACKUP_REHEARSAL_DIR:-}" ]; then TOOL="${BACKUP_TOOL:-$TOOL}"; fi
KEEP=7
MIN_FREE_MB=3072     # stop before filling the disk the app needs to run

mkdir -p "$BACKUP_DIR/db" "$BACKUP_DIR/files" "$BACKUP_DIR/offsite" "$(dirname "$LOG_FILE")"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

# One run at a time.
exec 9>"$BACKUP_DIR/.backup.lock"
flock -n 9 || { log "Another backup is running - stopping."; exit 0; }

TS=$(date +%Y%m%d_%H%M%S)
FAILED=0
log "=== Backup started: $TS ==="

FREE_MB=$(df -Pm "$BACKUP_DIR" | awk 'NR==2{print $4}')
if [ "${FREE_MB:-0}" -lt "$MIN_FREE_MB" ]; then
    log "ONLY ${FREE_MB} MB FREE - not writing a local backup (need ${MIN_FREE_MB}). Off-site still runs."
    LOCAL_OK=0
else
    LOCAL_OK=1
fi

# ── 1. Database ─────────────────────────────────────────────────────────────
DB_GZ="$BACKUP_DIR/db/sarathi_biz_${TS}.db.gz"
TMP_DB=$(mktemp "$BACKUP_DIR/.db_${TS}_XXXX")
sqlite3 "$DB_PATH" ".backup '${TMP_DB}'"
if [ "$(sqlite3 "$TMP_DB" 'PRAGMA quick_check;' 2>&1)" != "ok" ]; then
    log "DATABASE COPY FAILED ITS INTEGRITY CHECK - not kept."
    rm -f "$TMP_DB"; FAILED=1
else
    gzip -9 -c "$TMP_DB" > "${DB_GZ}.part" && mv "${DB_GZ}.part" "$DB_GZ"   # smallest gzip makes
    rm -f "$TMP_DB"
    log "[1/3] Database: $(du -h "$DB_GZ" | cut -f1) ($(basename "$DB_GZ"))"
fi

# ── 2. Files: a dated snapshot sharing unchanged files with the last one ────
if [ "$LOCAL_OK" = 1 ]; then
    SNAP="$BACKUP_DIR/files/$TS"
    LAST=$( { ls -1d "$BACKUP_DIR"/files/20*_* 2>/dev/null || true; } | { grep -v '\.partial$' || true; } | tail -1)
    mkdir -p "$SNAP.partial"
    for DIR in uploads generated_pdfs generated_videos; do
        [ -d "$SARATHI_DIR/$DIR" ] || continue
        if [ -n "$LAST" ] && [ -d "$LAST/$DIR" ]; then
            rsync -a --link-dest="$LAST/$DIR" "$SARATHI_DIR/$DIR/" "$SNAP.partial/$DIR/"
        else
            rsync -a "$SARATHI_DIR/$DIR/" "$SNAP.partial/$DIR/"
        fi
    done
    # The same paper attached to two claims is two files (10% of the space, measured 4 Oct). Inside
    # this BACKUP copy only - never the live uploads - identical files become one, linked twice.
    if command -v hardlink >/dev/null 2>&1; then
        hardlink -q -c "$SNAP.partial" >/dev/null 2>&1 || log "NOTE: de-duplicating the snapshot did not finish - it is still a complete copy"
    fi
    mv "$SNAP.partial" "$SNAP"
    log "[2/3] Files snapshot: $(basename "$SNAP") ($(du -sh "$SNAP" | cut -f1) on its own; unchanged files are shared)"
fi

# ── 3. Off-site ─────────────────────────────────────────────────────────────
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ] && [ -n "${BACKUP_ENC_PASSPHRASE:-}" ]; then
    export BACKUP_RCLONE_REMOTE BACKUP_ENC_PASSPHRASE SARATHI_DIR
    OFF="ok"
    if [ -f "$DB_GZ" ]; then
        "$PY" "$TOOL" db "$DB_GZ" >>"$LOG_FILE" 2>&1 || { log "OFFSITE DATABASE COPY FAILED"; OFF="failed"; }
    else
        OFF="failed"
    fi
    "$PY" "$TOOL" push >>"$LOG_FILE" 2>&1 || { log "OFFSITE FILE COPY FAILED"; OFF="failed"; }
    "$PY" "$TOOL" verify --sample 10 >>"$LOG_FILE" 2>&1 || { log "OFFSITE VERIFY FAILED"; OFF="failed"; }
    if [ "$OFF" = "failed" ]; then FAILED=1; fi
    log "[3/3] Off-site: $OFF (database, new files, sample restored and compared)"
    # The old whole-archive copies age out as before - ONLY that name pattern, top level.
    rclone delete --min-age "${KEEP}d" --max-depth 1 --include "sarathi_backup_*.tar.gz.gpg" \
        "$BACKUP_RCLONE_REMOTE" >>"$LOG_FILE" 2>&1 || log "NOTE: pruning the old off-site archives failed"
else
    log "OFF-SITE NOT CONFIGURED (BACKUP_RCLONE_REMOTE / BACKUP_ENC_PASSPHRASE) - this is a failed backup."
    FAILED=1
fi

# ── Prune: our own dated backups only, the newest $KEEP of each kind stay ───
{ ls -1 "$BACKUP_DIR"/db/sarathi_biz_*.db.gz 2>/dev/null || true; } | sort | head -n -"$KEEP" | while read -r f; do rm -f "$f"; done
{ ls -1d "$BACKUP_DIR"/files/20*_* 2>/dev/null || true; } | { grep -v '\.partial$' || true; } | sort | head -n -"$KEEP" \
    | while read -r d; do rm -rf "$d"; done
# A snapshot interrupted part-way is unfinished scratch, never a backup.
find "$BACKUP_DIR/files" -maxdepth 1 -name '*.partial' -mmin +720 -exec rm -rf {} + 2>/dev/null || true
# The old full archives: the same 7-day rule as always.
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -name "sarathi_backup_*.tar.gz" -mtime +${KEEP} -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then log "Old full archives aged out: $DELETED"; fi

log "Disk: $(df -Ph "$BACKUP_DIR" | awk 'NR==2{print $4" free of "$2}'); backups use $(du -sh "$BACKUP_DIR" | cut -f1)"
if [ "$FAILED" = 1 ]; then
    log "=== Backup FINISHED WITH FAILURES ==="
    exit 1
fi
log "=== Backup complete ==="
