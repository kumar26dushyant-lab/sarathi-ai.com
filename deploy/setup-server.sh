#!/bin/bash
# =============================================================================
#  Sarathi-AI — Oracle Cloud Server Setup Script
# =============================================================================
#  Run this ONCE on a fresh Ubuntu 22.04/24.04 Oracle Cloud VM.
#
#  Usage:
#    chmod +x deploy/setup-server.sh
#    sudo bash deploy/setup-server.sh
#
#  After running this script:
#    1. Upload your code:  scp -i key.pem -r ./* ubuntu@YOUR_IP:/opt/sarathi/
#    2. Update biz.env:    SERVER_URL=https://sarathi-ai.com
#    3. Start service:     sudo systemctl start sarathi
#    4. Get SSL cert:      sudo certbot --nginx -d sarathi-ai.com
# =============================================================================

set -e

echo "============================================"
echo "  Sarathi-AI Server Setup — Oracle Cloud"
echo "============================================"

# ── 1. System update ──
echo ""
echo "[1/7] Updating system packages..."
apt-get update -y && apt-get upgrade -y

# ── 2. Install required packages ──
echo ""
echo "[2/7] Installing Python 3.12, Nginx, Certbot..."
apt-get install -y \
    python3.12 python3.12-venv python3.12-dev \
    nginx certbot python3-certbot-nginx \
    git curl wget unzip htop \
    gcc libffi-dev

# If python3.12 not available (older Ubuntu), use deadsnakes PPA
if ! command -v python3.12 &> /dev/null; then
    echo "Adding deadsnakes PPA for Python 3.12..."
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y python3.12 python3.12-venv python3.12-dev
fi

# ── 3. Create sarathi user and directory ──
echo ""
echo "[3/7] Creating sarathi user and /opt/sarathi..."
useradd --system --shell /bin/bash --home /opt/sarathi --create-home sarathi 2>/dev/null || true
mkdir -p /opt/sarathi/static /opt/sarathi/generated_pdfs /opt/sarathi/gdrive_tokens
chown -R sarathi:sarathi /opt/sarathi

# ── 4. Create Python virtual environment ──
echo ""
echo "[4/7] Creating Python virtual environment..."
sudo -u sarathi python3.12 -m venv /opt/sarathi/venv
sudo -u sarathi /opt/sarathi/venv/bin/pip install --upgrade pip

# ── 5. Install systemd service ──
echo ""
echo "[5/7] Installing systemd service..."
if [ -f /opt/sarathi/deploy/sarathi.service ]; then
    cp /opt/sarathi/deploy/sarathi.service /etc/systemd/system/sarathi.service
else
    echo "WARNING: sarathi.service not found. Copy it manually later."
fi
systemctl daemon-reload
systemctl enable sarathi 2>/dev/null || true

# ── 6. Install Nginx config ──
echo ""
echo "[6/7] Configuring Nginx..."
if [ -f /opt/sarathi/deploy/nginx-sarathi.conf ]; then
    cp /opt/sarathi/deploy/nginx-sarathi.conf /etc/nginx/sites-available/sarathi
    ln -sf /etc/nginx/sites-available/sarathi /etc/nginx/sites-enabled/sarathi
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
else
    echo "WARNING: nginx-sarathi.conf not found. Copy it manually later."
fi

# ── 7. Configure Oracle Cloud iptables (CRITICAL!) ──
echo ""
echo "[7/7] Opening firewall ports (80, 443, 8001)..."
# Oracle Cloud uses iptables rules that BLOCK ports even if Security List allows them
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8001 -j ACCEPT
netfilter-persistent save 2>/dev/null || iptables-save > /etc/iptables/rules.v4 2>/dev/null || true

echo ""
echo "============================================"
echo "  ✅ Server setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "  1. Upload your code to the server:"
echo "     scp -i ~/.ssh/oracle-key.pem -r * ubuntu@YOUR_VM_IP:/tmp/sarathi/"
echo "     ssh -i ~/.ssh/oracle-key.pem ubuntu@YOUR_VM_IP"
echo "     sudo cp -r /tmp/sarathi/* /opt/sarathi/"
echo "     sudo chown -R sarathi:sarathi /opt/sarathi"
echo ""
echo "  2. Install Python dependencies:"
echo "     sudo -u sarathi /opt/sarathi/venv/bin/pip install -r /opt/sarathi/biz_requirements.txt"
echo ""
echo "  3. Update biz.env:"
echo "     sudo nano /opt/sarathi/biz.env"
echo "     → Change SERVER_URL=https://sarathi-ai.com"
echo ""
echo "  4. Point DNS: sarathi-ai.com → YOUR_VM_IP (A record)"
echo ""
echo "  5. Start the service:"
echo "     sudo systemctl start sarathi"
echo "     sudo journalctl -u sarathi -f    # watch logs"
echo ""
echo "  6. Get SSL certificate (after DNS propagates):"
echo "     sudo certbot --nginx -d sarathi-ai.com -d www.sarathi-ai.com"
echo ""
echo "  7. Verify:"
echo "     curl https://sarathi-ai.com/health"
echo ""
