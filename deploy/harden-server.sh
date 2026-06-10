#!/bin/bash
# =============================================================================
#  Sarathi-AI — Server Hardening Script
#  Run ONCE on a fresh or existing Oracle Cloud Ubuntu 24.04 VM.
#  Safe to re-run — all steps are idempotent.
#
#  Usage:  sudo bash deploy/harden-server.sh
# =============================================================================

set -euo pipefail

echo "============================================"
echo "  Sarathi-AI — Server Hardening"
echo "============================================"

# ── 1. System packages up to date ─────────────────────────────────────────
echo ""
echo "[1/8] Updating system packages..."
apt-get update -y && apt-get upgrade -y

# ── 2. Install security tools ─────────────────────────────────────────────
echo ""
echo "[2/8] Installing UFW, fail2ban, unattended-upgrades, ffmpeg..."
apt-get install -y \
    ufw fail2ban \
    unattended-upgrades apt-listchanges \
    iptables-persistent netfilter-persistent \
    sqlite3 \
    ffmpeg \
    python3-numpy \
    fonts-liberation fonts-dejavu-core

# ── 3. UFW firewall ────────────────────────────────────────────────────────
echo ""
echo "[3/8] Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh                  # 22/tcp
ufw allow 80/tcp               # HTTP (nginx)
ufw allow 443/tcp              # HTTPS (nginx)
# 8001 is internal only — NOT exposed to the internet
# ufw deny 8001/tcp  (already denied by default)
ufw --force enable
ufw status verbose

# ── 4. SSH hardening ──────────────────────────────────────────────────────
echo ""
echo "[4/8] Hardening SSH..."
SSHD_CFG="/etc/ssh/sshd_config"
# Disable password auth — key-only access
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD_CFG"
sed -i 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$SSHD_CFG"
# Disable root login
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CFG"
# Only allow the ubuntu user + sarathi user
if ! grep -q "^AllowUsers" "$SSHD_CFG"; then
    echo "AllowUsers ubuntu sarathi" >> "$SSHD_CFG"
fi
# Reduce login grace time
sed -i 's/^#*LoginGraceTime.*/LoginGraceTime 30/' "$SSHD_CFG"
# Idle timeout (30 minutes)
if ! grep -q "^ClientAliveInterval" "$SSHD_CFG"; then
    echo "ClientAliveInterval 1800" >> "$SSHD_CFG"
    echo "ClientAliveCountMax 1" >> "$SSHD_CFG"
fi
sshd -t && systemctl reload sshd
echo "SSH hardened (key-only, root login disabled)"

# ── 5. fail2ban ───────────────────────────────────────────────────────────
echo ""
echo "[5/8] Configuring fail2ban..."

# Copy our custom jail config
cp /opt/sarathi/deploy/fail2ban-sarathi.conf /etc/fail2ban/jail.d/sarathi.conf

# Ensure fail2ban is using the right backend
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd
EOF

systemctl enable fail2ban
systemctl restart fail2ban
echo "fail2ban configured"

# ── 6. Automatic security updates ────────────────────────────────────────
echo ""
echo "[6/8] Enabling automatic security updates..."
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
EOF

cat > /etc/apt/apt.conf.d/50unattended-upgrades << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF

systemctl enable unattended-upgrades
echo "Automatic security updates enabled"

# ── 7. Install + enable backup timers ─────────────────────────────────────
echo ""
echo "[7/8] Installing systemd backup timers..."
cp /opt/sarathi/deploy/backup-db.service /etc/systemd/system/
cp /opt/sarathi/deploy/backup-db.timer   /etc/systemd/system/
cp /opt/sarathi/deploy/git-backup.service /etc/systemd/system/
cp /opt/sarathi/deploy/git-backup.timer   /etc/systemd/system/
chmod +x /opt/sarathi/deploy/backup.sh
chmod +x /opt/sarathi/deploy/git-backup.sh
systemctl daemon-reload
systemctl enable --now backup-db.timer
systemctl enable --now git-backup.timer
systemctl list-timers --all | grep -E "backup|sarathi"

# ── 8. Install hardened nginx config ──────────────────────────────────────
echo ""
echo "[8/8] Installing hardened nginx config..."
cp /opt/sarathi/deploy/nginx-sarathi-hardened.conf /etc/nginx/sites-available/sarathi
nginx -t && systemctl reload nginx
echo "Nginx hardened config loaded"

echo ""
echo "============================================"
echo "  Hardening complete!"
echo "============================================"
echo ""
echo "Post-hardening checklist:"
echo "  ✅ UFW firewall: only 22/80/443 open"
echo "  ✅ SSH: key-only, no root login"
echo "  ✅ fail2ban: SSH + nginx brute-force protection"
echo "  ✅ Automatic security updates enabled"
echo "  ✅ DB backup timer: daily at 02:00"
echo "  ✅ GitHub backup timer: every 6 hours"
echo "  ✅ Nginx: rate limiting + security headers"
echo ""
echo "Remember to:"
echo "  1. Add GITHUB_PAT to /opt/sarathi/biz.env"
echo "  2. Add DMARC/SPF records in Cloudflare (see deploy/DMARC_DNS_RECORDS.md)"
echo "  3. Run: sudo -u sarathi bash /opt/sarathi/deploy/backup.sh  (test backup)"
echo "  4. Run: sudo -u sarathi bash /opt/sarathi/deploy/git-backup.sh  (test push)"
