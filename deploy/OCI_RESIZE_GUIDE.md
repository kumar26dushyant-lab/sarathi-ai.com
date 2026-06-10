# Oracle Cloud A1.Flex Resize — Step-by-Step Guide
# Upgrading from 1 OCPU / 6 GB → 4 OCPU / 24 GB (still FREE tier)

## Why this upgrade
Your VM was created with 1 OCPU / 6 GB RAM. Oracle's free tier actually gives you
4 OCPU + 24 GB RAM total for A1.Flex — you're leaving free resources on the table.
The upgrade also enables ffmpeg video generation (needs 2-4 GB RAM headroom).

---

## Total time: ~10 minutes. Zero data loss.

---

## Step 1: Pre-resize backup (2 minutes)

SSH into your server and run the backup first:

```bash
ssh -i ~/.ssh/ssh-key-2026-03-03.key ubuntu@140.238.246.0

sudo bash /opt/sarathi/deploy/pre-resize-backup.sh
```

This creates a timestamped backup at `/opt/sarathi/backups/pre-resize/`. Note the filename.

---

## Step 2: Stop the VM in OCI Console (2 minutes)

1. Open: https://cloud.oracle.com
2. Log in with your Oracle Cloud account
3. Go to: **Compute → Instances**
4. Click on your instance named `sarathi-ai` (or whatever you named it)
5. Click the **Stop** button (top of the page)
6. In the dialog: select **"Gracefully stop"** → click **Stop instance**
7. Wait until the status shows **STOPPED** (takes 1-2 minutes)

---

## Step 3: Change the shape (2 minutes)

While still on the instance details page (status = STOPPED):

1. Click **"Edit"** next to "Shape" (or look for "Change shape" button)
2. Shape series: **Ampere** (ARM-based)
3. Shape name: **VM.Standard.A1.Flex**
4. Set **OCPU count: 4**
5. Set **Memory (GB): 24**
6. Click **"Save changes"**

---

## Step 4: Start the VM (1 minute)

1. Click the **Start** button
2. Wait until status shows **RUNNING** (takes 1-2 minutes)
3. The **same public IP (140.238.246.0)** is preserved — no DNS changes needed

---

## Step 5: Verify everything works (2 minutes)

SSH back in (same IP, same key):

```bash
ssh -i ~/.ssh/ssh-key-2026-03-03.key ubuntu@140.238.246.0

sudo bash /opt/sarathi/deploy/post-resize-verify.sh
```

Expected output:
```
✅ CPU: 4 cores (ARM64 A1.Flex)
✅ RAM: 24 GB
✅ Architecture: aarch64
✅ sarathi.service: active
✅ MemoryMax bumped to 8G
✅ Health check: HTTP 200
```

---

## Step 6: Install new dependencies for video generation

After the resize, install ffmpeg and the Python packages needed for marketing studio:

```bash
# ffmpeg (video generation)
sudo apt-get install -y ffmpeg fonts-liberation fonts-dejavu-core python3-numpy

# Activate sarathi venv and install/upgrade packages
sudo -u sarathi /opt/sarathi/venv/bin/pip install \
    Pillow numpy \
    "pillow>=10.0.0"

# Verify ffmpeg works
ffmpeg -version | head -2
```

---

## Step 7: Run server hardening (first time only)

If you haven't run the hardening script yet:

```bash
sudo bash /opt/sarathi/deploy/harden-server.sh
```

This installs: UFW firewall, fail2ban, backup timers, hardened nginx.

---

## Troubleshooting

**VM won't start after shape change?**
- Oracle might say "out of capacity" for A1.Flex 4 OCPU in your region
- If so, try 2 OCPU / 12 GB first — still much better than 1 OCPU / 6 GB
- Or try a different availability domain in OCI Console

**Service not responding after restart?**
```bash
sudo journalctl -u sarathi -n 100
sudo systemctl restart sarathi
```

**App starts but video generation fails?**
```bash
# Test ffmpeg directly
ffmpeg -f lavfi -i testsrc=duration=1:size=720x720:rate=1 /tmp/test.mp4
# If this fails, reinstall:
sudo apt-get remove --purge ffmpeg
sudo apt-get install -y ffmpeg
```

---

## OCI CLI alternative (if you prefer terminal over web UI)

If you have OCI CLI installed locally:

```bash
# Get instance OCID first (from OCI Console → Instance Details → OCID)
INSTANCE_OCID="ocid1.instance.oc1.xxx.your-instance-id"

# Stop instance
oci compute instance action --action STOP --instance-id $INSTANCE_OCID

# Wait for stopped state
oci compute instance get --instance-id $INSTANCE_OCID --query 'data."lifecycle-state"'

# Update shape
oci compute instance update \
    --instance-id $INSTANCE_OCID \
    --shape VM.Standard.A1.Flex \
    --shape-config '{"ocpus": 4, "memoryInGBs": 24}'

# Start instance
oci compute instance action --action START --instance-id $INSTANCE_OCID
```
