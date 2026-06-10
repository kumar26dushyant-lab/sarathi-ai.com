#!/bin/bash
# =============================================================================
#  Sarathi-AI — Fresh Server Setup (Contabo / Ubuntu 24.04 VPS x86_64)
#  Run as root on the new server after copying code.
#
#  Usage:
#    1. Copy code to server (from Windows):
#       scp -r C:\sarathi-business root@<SERVER_IP>:/tmp/sarathi-deploy
#
#    2. SSH in and run:
#       ssh root@<SERVER_IP>
#       bash /tmp/sarathi-deploy/deploy/setup-contabo.sh
#
#  Takes ~5-10 minutes on first run.
# =============================================================================

set -euo pipefail

APP_DIR="/opt/sarathi"
APP_USER="sarathi"
DEPLOY_SRC="/tmp/sarathi-deploy"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[$(date +%H:%M:%S)] ✔ $*${NC}"; }
warn() { echo -e "${YELLOW}[WARN] $*${NC}"; }
err()  { echo -e "${RED}[ERROR] $*${NC}"; exit 1; }
step() { echo -e "\n${GREEN}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

[[ $EUID -ne 0 ]] && err "Run as root: bash $0"
[[ ! -d "$DEPLOY_SRC" ]] && err "Source not found at $DEPLOY_SRC. Run: scp -r C:\\sarathi-business root@SERVER:/tmp/sarathi-deploy"

SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Sarathi-AI — Server Setup (Contabo/Ubuntu)     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. System update ───────────────────────────────────────────────────────
step "1/9  System update"
apt-get update -y && apt-get upgrade -y
log "System packages updated"

# ── 2. Install dependencies ────────────────────────────────────────────────
step "2/9  Installing packages"
apt-get install -y \
    python3.12 python3.12-venv python3.12-dev \
    nginx certbot python3-certbot-nginx \
    ufw fail2ban \
    unattended-upgrades apt-listchanges \
    sqlite3 \
    ffmpeg \
    python3-numpy \
    fonts-liberation fonts-dejavu-core \
    git curl wget htop \
    iptables-persistent
log "All packages installed"

# ── 3. Create sarathi user ─────────────────────────────────────────────────
step "3/9  Creating sarathi user"
if ! id -u $APP_USER &>/dev/null; then
    useradd -r -m -d $APP_DIR -s /bin/bash $APP_USER
    log "User $APP_USER created"
else
    log "User $APP_USER already exists"
fi

# ── 4. Install application files ──────────────────────────────────────────
step "4/9  Installing application"
mkdir -p $APP_DIR
cp -r $DEPLOY_SRC/. $APP_DIR/
mkdir -p $APP_DIR/{uploads,generated_pdfs,generated_videos,backups,logs}
chown -R $APP_USER:$APP_USER $APP_DIR
chmod 750 $APP_DIR
chmod +x $APP_DIR/deploy/*.sh 2>/dev/null || true
log "Application files installed to $APP_DIR"

# ── 5. Python virtualenv + pip install ────────────────────────────────────
step "5/9  Python environment"
if [[ ! -d "$APP_DIR/venv" ]]; then
    python3.12 -m venv $APP_DIR/venv
fi
$APP_DIR/venv/bin/pip install --upgrade pip wheel --quiet
$APP_DIR/venv/bin/pip install -r $APP_DIR/biz_requirements.txt --quiet
chown -R $APP_USER:$APP_USER $APP_DIR/venv
log "Python venv ready ($(${APP_DIR}/venv/bin/python --version))"

# ── 6. biz.env template ────────────────────────────────────────────────────
step "6/9  Environment file"
if [[ ! -f "$APP_DIR/biz.env" ]]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > $APP_DIR/biz.env << ENVEOF
# ── Sarathi-AI Production Environment ────────────────────────────────────────
# Fill in ALL CHANGE_ME values before starting the service.

# App
SECRET_KEY=${SECRET}
BASE_URL=https://sarathi-ai.com
PORT=8001

# Telegram
TELEGRAM_BOT_TOKEN=CHANGE_ME

# Google Gemini
GEMINI_API_KEY=CHANGE_ME

# Google OAuth
GOOGLE_CLIENT_ID=CHANGE_ME
GOOGLE_CLIENT_SECRET=CHANGE_ME

# Razorpay
RAZORPAY_KEY_ID=CHANGE_ME
RAZORPAY_KEY_SECRET=CHANGE_ME
RAZORPAY_WEBHOOK_SECRET=CHANGE_ME

# Email (SMTP — use Gmail App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=CHANGE_ME@gmail.com
SMTP_PASS=CHANGE_ME
SMTP_FROM=noreply@sarathi-ai.com

# Evolution API (WhatsApp — existing Hetzner server)
EVOLUTION_API_URL=http://5.223.64.25:8080
EVOLUTION_API_KEY=CHANGE_ME

# GitHub backup
GITHUB_PAT=CHANGE_ME

# Nidaan
NIDAAN_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ENVEOF
    chmod 600 $APP_DIR/biz.env
    chown $APP_USER:$APP_USER $APP_DIR/biz.env
    warn "biz.env created — edit it before starting the service:"
    warn "  nano $APP_DIR/biz.env"
else
    log "biz.env already exists — keeping existing values"
fi

# ── 7. Systemd service ─────────────────────────────────────────────────────
step "7/9  Systemd service"
cp $APP_DIR/deploy/sarathi.service /etc/systemd/system/sarathi.service
systemctl daemon-reload
systemctl enable sarathi
log "Service installed and enabled (not started — edit biz.env first)"

# ── 8. Nginx ───────────────────────────────────────────────────────────────
step "8/9  Nginx"
rm -f /etc/nginx/sites-enabled/default

# Install config with SSL lines commented out (certbot adds them later)
cp $APP_DIR/deploy/nginx-sarathi-hardened.conf /etc/nginx/sites-available/sarathi

# Comment SSL-only lines — nginx can't start without certs yet
sed -i \
    -e 's|^\(\s*ssl_certificate\b\)|    # \1|' \
    -e 's|^\(\s*ssl_certificate_key\b\)|    # \1|' \
    -e 's|^\(\s*include.*letsencrypt\)|    # \1|' \
    -e 's|^\(\s*ssl_dhparam\)|    # \1|' \
    /etc/nginx/sites-available/sarathi

# Temporarily change HTTPS listen to plain HTTP so nginx starts
sed -i 's/listen 443 ssl http2;/listen 443;/' /etc/nginx/sites-available/sarathi
sed -i 's/listen \[::\]:443 ssl http2;/listen [::]:443;/' /etc/nginx/sites-available/sarathi

ln -sf /etc/nginx/sites-available/sarathi /etc/nginx/sites-enabled/sarathi
mkdir -p /var/www/certbot

nginx -t && systemctl enable nginx && systemctl restart nginx
log "Nginx running"

# ── 9. Security hardening ──────────────────────────────────────────────────
step "9/9  Security hardening"

# UFW
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
log "UFW: only 22/80/443 open"

# SSH — keep root key access (Contabo uses root), disable password
SSHD_CFG="/etc/ssh/sshd_config"
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD_CFG"
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' "$SSHD_CFG"
sed -i 's/^#*LoginGraceTime.*/LoginGraceTime 30/' "$SSHD_CFG"
grep -q "^ClientAliveInterval" "$SSHD_CFG" || echo -e "ClientAliveInterval 1800\nClientAliveCountMax 1" >> "$SSHD_CFG"
sshd -t && systemctl reload sshd
log "SSH: key-only, password disabled"

# fail2ban
cp $APP_DIR/deploy/fail2ban-sarathi.conf /etc/fail2ban/jail.d/sarathi.conf
cat > /etc/fail2ban/jail.local << 'F2B'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd
F2B
systemctl enable fail2ban && systemctl restart fail2ban
log "fail2ban enabled"

# Auto security updates
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'AU'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
AU
systemctl enable unattended-upgrades
log "Auto security updates enabled"

# Backup timers
cp $APP_DIR/deploy/backup-db.service  /etc/systemd/system/
cp $APP_DIR/deploy/backup-db.timer    /etc/systemd/system/
cp $APP_DIR/deploy/git-backup.service /etc/systemd/system/
cp $APP_DIR/deploy/git-backup.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now backup-db.timer
systemctl enable --now git-backup.timer
log "Backup timers enabled"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   ✅ Setup complete!                                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Server IP: $SERVER_IP"
echo ""
echo "NEXT STEPS (in order):"
echo ""
echo "  1. Fill in all credentials:"
echo "     nano $APP_DIR/biz.env"
echo ""
echo "  2. Restore DB from Oracle backup (if migrating):"
echo "     bash $APP_DIR/deploy/migrate-to-contabo.sh"
echo ""
echo "  3. Start the app and verify:"
echo "     systemctl start sarathi"
echo "     journalctl -u sarathi -f"
echo "     curl http://localhost:8001/health"
echo ""
echo "  4. Update Cloudflare DNS — set A records to: $SERVER_IP"
echo "     sarathi-ai.com    → $SERVER_IP"
echo "     www.sarathi-ai.com → $SERVER_IP"
echo "     nidaanpartner.com  → $SERVER_IP"
echo "     www.nidaanpartner.com → $SERVER_IP"
echo ""
echo "  5. Get SSL certificate (after DNS propagates ~5 min):"
echo "     certbot --nginx -d sarathi-ai.com -d www.sarathi-ai.com \\"
echo "             -d nidaanpartner.com -d www.nidaanpartner.com"
echo ""
echo "  6. Reload nginx after certbot:"
echo "     systemctl reload nginx"
echo ""
