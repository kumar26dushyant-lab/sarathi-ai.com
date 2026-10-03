#!/usr/bin/env bash
# =============================================================================
#  Let nginx see the VISITOR, not Cloudflare (3 Oct 2026).
# =============================================================================
#  Every visitor reaches us through Cloudflare, so without this nginx sees a
#  Cloudflare edge address as the "client". The rate limits key on that address,
#  so everyone arriving through the same Cloudflare edge shares ONE allowance:
#  on 3 Oct at 14:34 IST the office's own ops screens got 503s for 15 seconds
#  because several staff on one edge counted as one visitor - while an attacker
#  is never limited on their own. The app logs saw Cloudflare too.
#
#  This tells nginx to trust Cloudflare's CF-Connecting-IP header - but ONLY
#  when the connection really comes from a Cloudflare range. That is safe here
#  because the origin accepts 80/443 from Cloudflare alone
#  (deploy/lock-origin-to-cloudflare.sh); nobody else can send us that header.
#
#  The ranges come from the same place as the origin lock, with the same checks.
#
#  USAGE
#    sudo bash deploy/nginx-cloudflare-real-ip.sh apply    # write, test, reload
#    sudo bash deploy/nginx-cloudflare-real-ip.sh status   # show what is in force
#    sudo bash deploy/nginx-cloudflare-real-ip.sh undo     # remove, test, reload
#
#  AFTER APPLYING, check: both sites 200 from outside; the nginx access log shows
#  visitor addresses, not 104.x/162.158.x/172.6x.x; no new 503s in the error log.
# =============================================================================
set -euo pipefail

ACTION="${1:-status}"
CONF="/etc/nginx/conf.d/cloudflare-real-ip.conf"
V4_URL="https://www.cloudflare.com/ips-v4"
V6_URL="https://www.cloudflare.com/ips-v6"

[[ $EUID -ne 0 ]] && { echo "Run with sudo."; exit 1; }

status() {
  if [[ -f "$CONF" ]]; then
    echo "In force: $CONF ($(grep -c set_real_ip_from "$CONF") ranges)"
    grep -E "real_ip_header" "$CONF" | sed 's/^/  /'
  else
    echo "Not in force: nginx sees Cloudflare's address as the client."
  fi
  grep -q "conf.d/\*.conf" /etc/nginx/nginx.conf && echo "nginx.conf includes conf.d: yes" \
    || echo "*** nginx.conf does NOT include conf.d - this file would be ignored ***"
}

apply() {
  local v4 v6 tmp
  grep -q "conf.d/\*.conf" /etc/nginx/nginx.conf || { echo "nginx.conf does not include conf.d - refusing."; exit 1; }
  v4=$(curl -fsS --max-time 20 "$V4_URL") || { echo "Could not fetch $V4_URL - refusing to guess."; exit 1; }
  v6=$(curl -fsS --max-time 20 "$V6_URL") || { echo "Could not fetch $V6_URL - refusing to guess."; exit 1; }
  # A short list means a truncated download: trusting part of Cloudflare would mislabel the rest.
  [[ $(grep -c . <<<"$v4") -lt 10 ]] && { echo "Only $(grep -c . <<<"$v4") v4 ranges - refusing."; exit 1; }
  [[ $(grep -c . <<<"$v6") -lt 5  ]] && { echo "Only $(grep -c . <<<"$v6") v6 ranges - refusing."; exit 1; }
  # Every line must look like an address range before it goes near nginx.
  if grep -vE '^[0-9a-fA-F:.]+/[0-9]{1,3}$' <<<"$(printf '%s\n%s\n' "$v4" "$v6" | grep .)" | grep -q .; then
    echo "Unexpected text in Cloudflare's list - refusing."; exit 1
  fi

  tmp=$(mktemp)
  {
    echo "# Written by deploy/nginx-cloudflare-real-ip.sh on $(date -u +%F). Do not edit by hand."
    echo "# Trust CF-Connecting-IP only from Cloudflare's own ranges (the origin accepts nobody else)."
    while read -r cidr; do [[ -n "$cidr" ]] && echo "set_real_ip_from $cidr;"; done <<<"$v4"
    while read -r cidr; do [[ -n "$cidr" ]] && echo "set_real_ip_from $cidr;"; done <<<"$v6"
    echo "real_ip_header CF-Connecting-IP;"
  } > "$tmp"

  local had_old=0
  [[ -f "$CONF" ]] && { cp -p "$CONF" "$CONF.prev"; had_old=1; }
  install -m 644 "$tmp" "$CONF"; rm -f "$tmp"
  if ! nginx -t 2>&1; then
    echo "nginx refused the new file - putting things back."
    if [[ $had_old == 1 ]]; then mv -f "$CONF.prev" "$CONF"; else rm -f "$CONF"; fi
    nginx -t && echo "Back as it was. Nothing was reloaded."
    exit 1
  fi
  systemctl reload nginx
  rm -f "$CONF.prev"
  echo "Applied and reloaded."; status
}

undo() {
  [[ -f "$CONF" ]] || { echo "Nothing to undo."; return; }
  mv -f "$CONF" "$CONF.removed"
  if nginx -t 2>&1; then
    systemctl reload nginx
    echo "Removed and reloaded (kept at $CONF.removed)."
  else
    mv -f "$CONF.removed" "$CONF"
    echo "nginx did not accept the change - left as it was."; exit 1
  fi
}

case "$ACTION" in
  apply)  apply ;;
  undo)   undo ;;
  status) status ;;
  *) echo "Usage: sudo bash $0 {apply|status|undo}"; exit 1 ;;
esac
