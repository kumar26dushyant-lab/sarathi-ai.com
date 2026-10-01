# Oracle Cloud Free Tier — Deployment Guide

## 🏗️ Architecture

```
Internet → Oracle Cloud VM (Free Tier)
           ├── Nginx (port 80/443) → reverse proxy
           │     ├── /static/* → served directly
           │     └── /* → proxy to :8001
           └── Sarathi-AI (port 8001) → Python/FastAPI + SQLite
```

## 🌐 Your Oracle Cloud Setup

| Item | Value |
|------|-------|
| VCN name | `sarathi-vcn` |
| VCN CIDR | `10.0.0.0/16` |
| Public subnet | `public subnet-sarathi-vcn` |
| Subnet IP | `10.0.0.236` |
| VM public IP | _(assigned by Oracle — visible on instance details page)_ |

## 📋 Prerequisites

| Item | Details |
|------|---------|
| Oracle Cloud account | Free tier — always-free eligible |
| VM shape | `VM.Standard.A1.Flex` (ARM) — 4 OCPU, 24 GB RAM (free) |
| OS | Ubuntu 22.04 or 24.04 (Canonical) |
| Domain | `sarathi-ai.com` (or your domain) with DNS access |
| SSH key | Generated for Oracle Cloud access |

## 🚀 Step-by-Step Deployment

### Step 1: Create Oracle Cloud VM (if not already done)

1. Login to [Oracle Cloud Console](https://cloud.oracle.com)
2. **Compute → Instances → Create Instance**
3. Settings:
   - **Name**: `sarathi-ai`
   - **Image**: Ubuntu 22.04 (Always Free eligible)
   - **Shape**: `VM.Standard.A1.Flex` — 1 OCPU, 6 GB RAM (free tier)
   - **Networking**: Select existing VCN `sarathi-vcn`, select `public subnet-sarathi-vcn (10.0.0.0/24)`, assign public IP
   - **SSH key**: Upload your public key
4. Click **Create**
5. Note the **Public IP** address (this is your external-facing IP, different from the private `10.0.0.236`)

### Step 2: Configure Oracle Cloud Security List

**Critical!** Oracle Cloud blocks ports by default even with iptables open.

1. Go to **Networking → Virtual Cloud Networks → sarathi-vcn**
2. Click **public subnet-sarathi-vcn → Security Lists → Default Security List**
3. Add **Ingress Rules**:
   - Source: `0.0.0.0/0`, Protocol: TCP, Port: **80** (HTTP)
   - Source: `0.0.0.0/0`, Protocol: TCP, Port: **443** (HTTPS)
   - Source: `0.0.0.0/0`, Protocol: TCP, Port: **8001** (direct access, optional)

### Step 3: SSH into the VM

```bash
# From your local machine (Git Bash, WSL, or PowerShell)
ssh -i ~/.ssh/oracle-key.pem ubuntu@YOUR_VM_IP
```

### Step 4: Run Server Setup Script

```bash
# If fresh VM (first time):
sudo mkdir -p /opt/sarathi
cd /opt/sarathi

# Upload the setup script first, then run:
sudo bash deploy/setup-server.sh
```

This script:
- Updates system packages
- Installs Python 3.12, Nginx, Certbot
- Creates `sarathi` user and `/opt/sarathi` directory
- Sets up Python virtual environment
- Installs systemd service
- Configures Nginx reverse proxy
- Opens firewall ports (80, 443, 8001)

### Step 5: Upload Code to Server

**Option A: Using SCP (from Windows/Git Bash)**

```bash
# Set variables
VM_IP="YOUR_VM_IP"
KEY="~/.ssh/oracle-key.pem"

# Create temp directory on server
ssh -i $KEY ubuntu@$VM_IP "mkdir -p /tmp/sarathi-upload"

# Upload Python files
scp -i $KEY *.py ubuntu@$VM_IP:/tmp/sarathi-upload/

# Upload static files
scp -i $KEY -r static/ ubuntu@$VM_IP:/tmp/sarathi-upload/static/

# Upload config files
scp -i $KEY biz_requirements.txt Dockerfile docker-compose.yml ubuntu@$VM_IP:/tmp/sarathi-upload/
scp -i $KEY -r deploy/ ubuntu@$VM_IP:/tmp/sarathi-upload/deploy/

# SSH in and move files
ssh -i $KEY ubuntu@$VM_IP << 'EOF'
sudo cp -r /tmp/sarathi-upload/*.py /opt/sarathi/
sudo cp -r /tmp/sarathi-upload/static/ /opt/sarathi/static/
sudo cp /tmp/sarathi-upload/biz_requirements.txt /opt/sarathi/
sudo cp -r /tmp/sarathi-upload/deploy/ /opt/sarathi/deploy/
sudo mkdir -p /opt/sarathi/generated_pdfs /opt/sarathi/gdrive_tokens
sudo chown -R sarathi:sarathi /opt/sarathi
rm -rf /tmp/sarathi-upload
EOF
```

**Option B: Using the deploy script**

```bash
bash deploy/push-update.sh YOUR_VM_IP
```

### Step 6: Configure Environment (biz.env)

```bash
ssh -i $KEY ubuntu@$VM_IP
sudo nano /opt/sarathi/biz.env
```

**Critical settings to update for production:**

```env
# Change to false for production
DEV_MODE=false

# Your actual domain (after DNS setup)
SERVER_URL=https://sarathi-ai.com

# Keep existing values for:
# TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, JWT_SECRET, ADMIN_API_KEY
# RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, SUPERADMIN_PHONES, etc.

# WhatsApp can stay as-is (API is disabled in code now)
```

### Step 7: Install Python Dependencies

```bash
sudo -u sarathi /opt/sarathi/venv/bin/pip install -r /opt/sarathi/biz_requirements.txt
```

### Step 8: Start the Service

```bash
# Install/update the systemd service
sudo cp /opt/sarathi/deploy/sarathi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sarathi
sudo systemctl start sarathi

# Check it's running
sudo systemctl status sarathi
sudo journalctl -u sarathi -f   # live logs
```

### Step 9: Configure DNS

Point your domain to the Oracle Cloud VM:

| Type | Name | Value |
|------|------|-------|
| A | `sarathi-ai.com` | `YOUR_VM_IP` |
| A | `www.sarathi-ai.com` | `YOUR_VM_IP` |

Wait for DNS to propagate (5-30 minutes).

### Step 10: Get SSL Certificate

```bash
sudo certbot --nginx -d sarathi-ai.com -d www.sarathi-ai.com
```

Certbot will:
- Generate free Let's Encrypt SSL certificate
- Auto-configure Nginx for HTTPS
- Set up auto-renewal (via systemd timer)

### Step 11: Verify Deployment

```bash
# From the server
curl http://localhost:8001/health

# From your local machine
curl https://sarathi-ai.com/health
```

Expected response: `{"status": "healthy", ...}`

## 🔄 Updating an Existing Deployment

Since you already have an older version deployed:

```bash
# 1. From your Windows machine, run the push-update script:
bash deploy/push-update.sh YOUR_VM_IP

# This automatically:
#   - Uploads new code
#   - Installs any new dependencies
#   - Restarts the service
#   - Shows service status
```

**Or manually:**

```bash
ssh -i ~/.ssh/oracle-key.pem ubuntu@YOUR_VM_IP

# Backup current DB before updating
sudo -u sarathi bash /opt/sarathi/deploy/backup.sh

# Upload new files (from local machine)
# Then on server:
sudo systemctl restart sarathi
sudo journalctl -u sarathi -f
```

## 📊 Oracle Cloud Free Tier Limits

| Resource | Free Tier Allowance | Sarathi-AI Usage |
|----------|-------------------|-----------------|
| Compute | 4 OCPU, 24 GB RAM (ARM) | ~1 OCPU, 2 GB RAM |
| Storage | 200 GB total block storage | ~10-20 GB |
| Network | 10 TB/month outbound | Minimal (<1 GB/month) |
| Always Free | Yes — never expires | ✅ Fits perfectly |

## 🛡️ Post-Deployment Checklist

- [ ] `DEV_MODE=false` in biz.env
- [ ] `SERVER_URL` points to actual domain
- [ ] SSL certificate active (https works)
- [ ] Firewall ports 80/443 open
- [ ] Telegram bot responds
- [ ] Health check returns 200
- [ ] Dashboard loads with login
- [ ] Calculator API works
- [ ] Payment flow works (Razorpay webhook URL matches domain)
- [ ] Daily backup cron job set up

## 🔧 Useful Commands

```bash
# Service management
sudo systemctl status sarathi          # Check status
sudo systemctl restart sarathi         # Restart
sudo journalctl -u sarathi -f          # Live logs
sudo journalctl -u sarathi --since "1 hour ago"  # Recent logs

# Database
sudo -u sarathi sqlite3 /opt/sarathi/sarathi_biz.db ".tables"
sudo -u sarathi bash /opt/sarathi/deploy/backup.sh

# Nginx
sudo nginx -t                          # Test config
sudo systemctl reload nginx            # Reload config
sudo tail -f /var/log/nginx/error.log  # Nginx errors

# SSL renewal (auto, but manual test)
sudo certbot renew --dry-run

# Disk usage
df -h
du -sh /opt/sarathi/*
```

## ⚠️ Razorpay Webhook URL

After deployment, update your Razorpay dashboard:

1. Go to [Razorpay Dashboard → Settings → Webhooks](https://dashboard.razorpay.com/app/webhooks)
2. Update webhook URL to: `https://sarathi-ai.com/api/payments/webhook`
3. Events to subscribe:
   - `payment.captured`
   - `subscription.activated`
   - `subscription.charged`
   - `subscription.cancelled`
   - `subscription.completed`
