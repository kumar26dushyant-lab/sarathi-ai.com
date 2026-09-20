#!/usr/bin/env bash
# =============================================================================
#  Restrict 80/443 to Cloudflare only — the control that hides the origin.
# =============================================================================
#  Contabo has always done this (UFW: 80,443 ALLOW from each Cloudflare range,
#  and nothing else). It matters more than it looks: both live domains are
#  PROXIED by Cloudflare, so every real visitor arrives from a Cloudflare IP.
#  Anything connecting to the origin directly is bypassing the WAF, the rate
#  limits and the DDoS protection — and knows an IP it should not know.
#
#  A migration is exactly where a control like this gets lost, because nobody
#  wrote it down: it lives in the old server's firewall, not in the repo. This
#  script is that control, in the repo, idempotent, with an undo.
#
#  This box keeps the Oracle image's iptables rather than UFW (two firewall
#  managers writing the same tables is how you lock yourself out of a machine
#  in Mumbai), so the same policy is expressed in iptables/ip6tables here.
#
#  USAGE
#    sudo bash deploy/lock-origin-to-cloudflare.sh apply    # restrict to Cloudflare
#    sudo bash deploy/lock-origin-to-cloudflare.sh status   # show what is in force
#    sudo bash deploy/lock-origin-to-cloudflare.sh undo     # back to open 80/443
#
#  ORDER MATTERS, and this script enforces it: the Cloudflare ACCEPT rules are
#  added BEFORE the open rule is withdrawn, so there is never a moment where
#  legitimate traffic is refused. Port 22 is never touched.
#
#  RUN IT *AFTER* THE CUTOVER IS VERIFIED, not before — while the grey-cloud
#  new.* test hostnames are still in use, direct access is exactly what you need.
# =============================================================================
set -euo pipefail

ACTION="${1:-status}"
MARK="cf-origin-lock"
V4_URL="https://www.cloudflare.com/ips-v4"
V6_URL="https://www.cloudflare.com/ips-v6"

[[ $EUID -ne 0 ]] && { echo "Run with sudo."; exit 1; }

have_open_rule() { iptables -C INPUT -p tcp --dport 80 -m state --state NEW -j ACCEPT 2>/dev/null; }

status() {
  echo "── IPv4 ────────────────────────────────────────────────"
  iptables -S INPUT | grep -E 'dport (80|443)' | sed 's/^/  /' || echo "  (none)"
  echo "── IPv6 ────────────────────────────────────────────────"
  ip6tables -S INPUT 2>/dev/null | grep -E 'dport (80|443)' | sed 's/^/  /' || echo "  (none)"
  echo "── SSH (must always be present) ────────────────────────"
  iptables -S INPUT | grep -E 'dport 22' | sed 's/^/  /' || echo "  *** NO SSH RULE — DO NOT PROCEED ***"
}

apply() {
  local v4 v6 n=0
  v4=$(curl -fsS --max-time 20 "$V4_URL") || { echo "Could not fetch $V4_URL — refusing to guess."; exit 1; }
  v6=$(curl -fsS --max-time 20 "$V6_URL") || { echo "Could not fetch $V6_URL — refusing to guess."; exit 1; }
  # Sanity: Cloudflare publishes ~15 v4 and ~7 v6 ranges. A short list means a
  # truncated download, and applying it would lock out most of Cloudflare.
  [[ $(wc -l <<<"$v4") -lt 10 ]] && { echo "Only $(wc -l <<<"$v4") v4 ranges returned — refusing."; exit 1; }
  [[ $(wc -l <<<"$v6") -lt 5  ]] && { echo "Only $(wc -l <<<"$v6") v6 ranges returned — refusing."; exit 1; }

  echo "Adding Cloudflare ACCEPT rules first (no gap in service)…"
  while read -r cidr; do
    [[ -z "$cidr" ]] && continue
    for port in 80 443; do
      iptables -C INPUT -p tcp -s "$cidr" --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
        || iptables -I INPUT 4 -p tcp -s "$cidr" --dport "$port" -m state --state NEW -j ACCEPT -m comment --comment "$MARK"
    done
    n=$((n+1))
  done <<<"$v4"
  while read -r cidr; do
    [[ -z "$cidr" ]] && continue
    for port in 80 443; do
      ip6tables -C INPUT -p tcp -s "$cidr" --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
        || ip6tables -I INPUT 1 -p tcp -s "$cidr" --dport "$port" -m state --state NEW -j ACCEPT -m comment --comment "$MARK" 2>/dev/null || true
    done
  done <<<"$v6"
  echo "  $n IPv4 ranges + $(grep -c . <<<"$v6") IPv6 ranges allowed."

  echo "Withdrawing the open-to-the-world rules…"
  for port in 80 443; do
    while iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; do
      iptables -D INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT
    done
  done

  netfilter-persistent save >/dev/null 2>&1 && echo "  Persisted across reboot."
  echo; status
  echo
  echo "VERIFY NOW, from a machine that is NOT Cloudflare:"
  echo "  curl -m 10 http://<origin-ip>/        → should TIME OUT or refuse"
  echo "  curl -m 10 https://nidaanpartner.com/ → should still be 200 (via Cloudflare)"
}

undo() {
  echo "Restoring open 80/443 first, so nothing is cut off…"
  for port in 80 443; do
    iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
      || iptables -I INPUT 4 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
  done
  echo "Removing the Cloudflare-specific rules…"
  while iptables -S INPUT | grep -q -- "--comment $MARK"; do
    rule=$(iptables -S INPUT | grep -m1 -- "--comment $MARK" | sed 's/^-A /-D /')
    # shellcheck disable=SC2086
    iptables $rule
  done
  while ip6tables -S INPUT 2>/dev/null | grep -q -- "--comment $MARK"; do
    rule=$(ip6tables -S INPUT | grep -m1 -- "--comment $MARK" | sed 's/^-A /-D /')
    # shellcheck disable=SC2086
    ip6tables $rule
  done
  netfilter-persistent save >/dev/null 2>&1 && echo "  Persisted."
  echo; status
}

case "$ACTION" in
  apply)  apply ;;
  undo)   undo ;;
  status) status ;;
  *) echo "Usage: sudo bash $0 {apply|status|undo}"; exit 1 ;;
esac
