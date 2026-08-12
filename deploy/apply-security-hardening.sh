#!/usr/bin/env bash
# =============================================================================
#  apply-security-hardening.sh — one-shot security tightening (run as root)
# =============================================================================
#  1. Isolate staging's access log from fail2ban (gated login box must never ban)
#  2. Install fail2ban jail with an ignoreip whitelist (+ optional operator IP arg)
#  3. Clear all current bans + restart fail2ban
#  4. Verify prod secret posture: DEV_MODE off + Razorpay LIVE keys (no secrets printed)
#  5. nginx -t, reload, health-check
#
#  Usage:  bash deploy/apply-security-hardening.sh [YOUR_STATIC_IP]
#          (pass your office/home IP to whitelist it everywhere — optional)
# =============================================================================
set -euo pipefail
APP=/opt/sarathi
EXTRA_IP="${1:-}"
echo "=== $(date '+%F %T') security hardening starting ==="

# 1) Isolate the staging vhost's logs (surgical; keeps certbot's 443 block intact)
ST=/etc/nginx/sites-available/staging
if [ -f "$ST" ] && ! grep -q "staging_access.log" "$ST"; then
  cp -a "$ST" "$ST.bak.$(date +%s)"
  sed -i '/server_name staging\.nidaanpartner\.com/a\    access_log /var/log/nginx/staging_access.log;\n    error_log  /var/log/nginx/staging_error.log warn;' "$ST"
  echo "  ✓ staging vhost: isolated logs added (fail2ban no longer sees staging auth)"
else
  echo "  • staging vhost: already isolated or absent"
fi

# 2) fail2ban jail + filter (with ignoreip whitelist)
cp -a "$APP/deploy/fail2ban-sarathi.conf" /etc/fail2ban/jail.d/sarathi.conf
cp -a "$APP/deploy/fail2ban-filter-nginx-login.conf" /etc/fail2ban/filter.d/nginx-login.conf 2>/dev/null || true
if [ -n "$EXTRA_IP" ] && ! grep -q "$EXTRA_IP" /etc/fail2ban/jail.d/sarathi.conf; then
  sed -i "s#^ignoreip = 127.0.0.1/8 ::1#ignoreip = 127.0.0.1/8 ::1 $EXTRA_IP#" /etc/fail2ban/jail.d/sarathi.conf
  echo "  ✓ whitelisted operator IP $EXTRA_IP"
fi

# 3) nginx test + reload
nginx -t && systemctl reload nginx && echo "  ✓ nginx reloaded"

# 4) restart fail2ban + clear all current bans
systemctl restart fail2ban
sleep 2
fail2ban-client unban --all 2>/dev/null || true
echo "  ✓ fail2ban restarted + all bans cleared"
fail2ban-client status 2>/dev/null | sed 's/^/    /' || true

# 5) verify prod secret posture (values NEVER printed)
echo "=== prod secret posture ($APP/biz.env) ==="
val(){ grep -E "^$1=" "$APP/biz.env" 2>/dev/null | head -1 | cut -d= -f2-; }
DEV=$(val DEV_MODE | tr 'A-Z' 'a-z')
case "$DEV" in 1|true|yes) echo "  ⚠️  DEV_MODE is ON in prod — the 98765x test-OTP bypass is ACTIVE. Set DEV_MODE=0 !";; *) echo "  ✓ DEV_MODE off";; esac
for k in RAZORPAY_KEY_ID NIDAAN_RAZORPAY_KEY_ID; do
  case "$(val $k)" in
    rzp_live_*) echo "  ✓ $k is LIVE";;
    rzp_test_*) echo "  ⚠️  $k is a TEST key in PROD — payments won't really charge / test-mode OTP bypass";;
    "")         echo "  •  $k empty";;
    *)          echo "  ?  $k has an unexpected prefix — check it";;
  esac
done

# 6) health
echo "=== health ==="
for p in 8001 8002 8003; do printf "  :$p -> "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:$p/health || echo timeout; done
echo "=== $(date '+%F %T') hardening complete ==="
