#!/bin/bash
# =============================================================================
#  Sarathi-AI — Post-Resize Verification Script
#  Run AFTER the OCI shape change is complete and VM has restarted.
#  Verifies all services, installs ffmpeg if missing, bumps MemoryMax.
#
#  Usage:  sudo bash /opt/sarathi/deploy/post-resize-verify.sh
# =============================================================================

set -euo pipefail

SARATHI_DIR="/opt/sarathi"
OK=0
FAIL=0
WARN=0

pass()  { echo "  ✅ $*"; ((OK++))   || true; }
fail()  { echo "  ❌ $*"; ((FAIL++)) || true; }
warn()  { echo "  ⚠️  $*"; ((WARN++)) || true; }

echo "====================================================="
echo "  Sarathi-AI — Post-Resize Verification"
echo "  $(date)"
echo "====================================================="

# ── Hardware ──────────────────────────────────────────────────────────────
echo ""
echo "[Hardware]"
CPUS=$(nproc)
RAM_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)
ARCH=$(uname -m)
[ "$CPUS" -ge 4 ]     && pass "CPU: ${CPUS} cores (ARM64 A1.Flex)" || warn "CPU: ${CPUS} cores (expected 4)"
[ "$RAM_GB" -ge 20 ]  && pass "RAM: ${RAM_GB} GB" || warn "RAM: ${RAM_GB} GB (expected ~24 GB)"
[ "$ARCH" = "aarch64" ] && pass "Architecture: aarch64 (ARM64)" || fail "Architecture: $ARCH"
DISK_FREE=$(df -BG /opt | awk 'NR==2 {print $4}' | tr -d 'G')
[ "$DISK_FREE" -ge 20 ] && pass "Disk free: ${DISK_FREE} GB" || warn "Disk free: ${DISK_FREE} GB (low)"

# ── Python ────────────────────────────────────────────────────────────────
echo ""
echo "[Python]"
PYTHON="$SARATHI_DIR/venv/bin/python"
if [ -f "$PYTHON" ]; then
    PY_VER=$($PYTHON --version 2>&1)
    [[ "$PY_VER" == *"3.12"* ]] && pass "$PY_VER" || warn "$PY_VER (expected 3.12)"
else
    fail "venv Python not found at $PYTHON"
fi

# Key packages
for PKG in fastapi aiosqlite pillow numpy; do
    $PYTHON -c "import $PKG" 2>/dev/null && pass "import $PKG OK" || fail "import $PKG FAILED"
done

# ── ffmpeg ────────────────────────────────────────────────────────────────
echo ""
echo "[ffmpeg — video generation]"
if command -v ffmpeg &>/dev/null; then
    FFMPEG_VER=$(ffmpeg -version 2>&1 | head -1)
    pass "$FFMPEG_VER"
    # Check ARM codec support
    ffmpeg -codecs 2>&1 | grep -q "libx264" && pass "libx264 codec available" || warn "libx264 not found — install: apt-get install ffmpeg"
else
    warn "ffmpeg not installed — installing now..."
    apt-get install -y ffmpeg
    command -v ffmpeg && pass "ffmpeg installed" || fail "ffmpeg install failed"
fi

# ── Sarathi service ───────────────────────────────────────────────────────
echo ""
echo "[Sarathi service]"
systemctl is-active sarathi &>/dev/null && pass "sarathi.service: active" || fail "sarathi.service: NOT running"
systemctl is-enabled sarathi &>/dev/null && pass "sarathi.service: enabled (auto-start)" || warn "sarathi.service: not enabled"

# ── MemoryMax update ──────────────────────────────────────────────────────
echo ""
echo "[Service resource limits]"
SERVICE_FILE="/etc/systemd/system/sarathi.service"
CURRENT_MEM=$(grep MemoryMax "$SERVICE_FILE" 2>/dev/null | head -1 || echo "not set")
if echo "$CURRENT_MEM" | grep -qE "800M|1G"; then
    echo "  Bumping MemoryMax from $CURRENT_MEM → 8G for video generation..."
    sed -i 's/^MemoryMax=.*/MemoryMax=8G/' "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl restart sarathi
    pass "MemoryMax bumped to 8G"
else
    pass "MemoryMax: $CURRENT_MEM"
fi

# ── Nginx ────────────────────────────────────────────────────────────────
echo ""
echo "[Nginx]"
systemctl is-active nginx &>/dev/null && pass "nginx: active" || fail "nginx: NOT running"
nginx -t 2>&1 | grep -q "successful" && pass "nginx config: OK" || fail "nginx config: INVALID"

# ── fail2ban + UFW ────────────────────────────────────────────────────────
echo ""
echo "[Security services]"
systemctl is-active fail2ban &>/dev/null && pass "fail2ban: active" || warn "fail2ban: not running"
ufw status | grep -q "Status: active" && pass "UFW: active" || warn "UFW: not active"

# ── Backup timers ─────────────────────────────────────────────────────────
echo ""
echo "[Backup timers]"
systemctl is-active backup-db.timer &>/dev/null && pass "backup-db.timer: active" || warn "backup-db.timer: not active (run harden-server.sh)"
systemctl is-active git-backup.timer &>/dev/null && pass "git-backup.timer: active" || warn "git-backup.timer: not active"

# ── App health check ──────────────────────────────────────────────────────
echo ""
echo "[App health]"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health 2>/dev/null || echo "000")
[ "$HTTP_CODE" = "200" ] && pass "Health check: HTTP 200" || fail "Health check: HTTP $HTTP_CODE"

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "====================================================="
echo "  Results: $OK passed, $FAIL failed, $WARN warnings"
echo "====================================================="

if [ "$FAIL" -gt 0 ]; then
    echo "  ❌ ISSUES FOUND — check the failures above"
    echo "     Run: sudo journalctl -u sarathi -n 50"
    exit 1
else
    echo "  ✅ Resize verification passed!"
    echo ""
    echo "  Your A1.Flex VM is fully operational."
    echo "  Resources: $(nproc) OCPUs, ${RAM_GB} GB RAM"
fi
