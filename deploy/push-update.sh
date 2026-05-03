#!/bin/bash
# =============================================================================
#  Sarathi-AI — Quick Deploy / Update Script
# =============================================================================
#  Run this to deploy code updates to your Oracle Cloud server.
#
#  Usage (from your Windows machine):
#    bash deploy/push-update.sh YOUR_VM_IP
#
#  Or manually:
#    scp files → ssh → restart service
# =============================================================================

VM_IP="${1:?Usage: bash deploy/push-update.sh YOUR_VM_IP}"
KEY="${SSH_KEY:-~/.ssh/oracle-key.pem}"
REMOTE_USER="${REMOTE_USER:-ubuntu}"
APP_DIR="/opt/sarathi"

echo "============================================"
echo "  Deploying Sarathi-AI to $VM_IP"
echo "============================================"

# Files to upload (excluding test files, DB, cache)
echo "[1/4] Uploading code..."
scp -i "$KEY" -o StrictHostKeyChecking=no \
    *.py biz.env biz_requirements.txt \
    Dockerfile docker-compose.yml \
    "$REMOTE_USER@$VM_IP:/tmp/sarathi-update/"

echo "[2/4] Uploading static files..."
scp -i "$KEY" -r static/ "$REMOTE_USER@$VM_IP:/tmp/sarathi-update/static/"

echo "[3/4] Uploading deploy configs..."
scp -i "$KEY" -r deploy/ "$REMOTE_USER@$VM_IP:/tmp/sarathi-update/deploy/"

echo "[4/4] Installing on server..."
ssh -i "$KEY" "$REMOTE_USER@$VM_IP" << 'REMOTE_SCRIPT'
    set -e
    sudo cp -r /tmp/sarathi-update/*.py /opt/sarathi/
    sudo cp -r /tmp/sarathi-update/static/* /opt/sarathi/static/
    sudo cp /tmp/sarathi-update/biz_requirements.txt /opt/sarathi/
    sudo cp -r /tmp/sarathi-update/deploy/ /opt/sarathi/deploy/
    # Don't overwrite biz.env (has production secrets) unless forced
    # sudo cp /tmp/sarathi-update/biz.env /opt/sarathi/biz.env
    sudo chown -R sarathi:sarathi /opt/sarathi
    sudo -u sarathi /opt/sarathi/venv/bin/pip install -q -r /opt/sarathi/biz_requirements.txt
    sudo systemctl restart sarathi
    sleep 3
    echo ""
    echo "Service status:"
    sudo systemctl status sarathi --no-pager -l | head -20
    echo ""
    rm -rf /tmp/sarathi-update
REMOTE_SCRIPT

echo ""
echo "✅ Deployment complete!"
echo "   Check: curl https://sarathi-ai.com/health"
