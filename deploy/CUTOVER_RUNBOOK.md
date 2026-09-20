# Cutover runbook — Contabo → Oracle Mumbai

**Status: not yet executed.** Nothing in this document has been run against production.

| | |
|---|---|
| **From** | Contabo `84.247.172.252` · x86_64 · Europe/Berlin |
| **To** | Oracle `nidaanpartner-mumbai-01` · `161.118.186.201` · ap-mumbai-1 · **aarch64** · Europe/Berlin |
| **Moving** | nidaanpartner.com **and** sarathi-ai.com (one app, two products, host-routed) |
| **Expected window** | 15–25 minutes, of which ~5 is user-visible |
| **Rollback** | one Cloudflare A-record change — **but see "When rollback stops being clean"** |

---

## The one thing to understand before starting

Both live domains are **proxied by Cloudflare** (orange cloud). Visitors never resolve the origin;
they hit Cloudflare's edge, which forwards to whatever origin IP the A record names. So:

* The cutover is **not** a DNS propagation event. Changing the origin A record takes effect at
  Cloudflare in seconds. No TTL to wait out, no split-brain across resolvers.
* The rollback is the same change in reverse, and equally fast.

This is why the plan is safe. It is also why the **order** below matters: everything is verified
*before* the record changes, because the record change is the only irreversible-ish step.

### When rollback stops being clean

Flipping back is instant **until the first real write lands in the new database.** After that,
rolling back to Contabo silently discards whatever staff and complainants did in between.

Practically: rollback is free for the first minute or two, cheap for the first ten, and after that
the honest option is to fix forward. Everything below is arranged so that the risky step happens
last, on a system already proven by every earlier step.

---

## Preconditions — all must be true, checked the day before

- [ ] `https://new.nidaanpartner.com` serves **Nidaan** and `https://new.sarathi-ai.com` serves
      **Sarathi**, both over valid TLS. *(Verified 20 Sep.)*
- [ ] Journeys: **20 passed, 0 failed** on the Oracle box against a copy of the live DB.
- [ ] A rolling deploy on the Oracle box produces **zero** non-200 responses. *(Verified: 180/180.)*
- [ ] `backup-db.timer` armed and proven by a real run. *(Verified 20 Sep.)*
- [ ] `git-db-backup` units installed, write deploy key added, **one successful push proven**.
- [ ] Real `biz.env` prepared, `sarathi:sarathi`, mode `600`, all 74 keys.
- [ ] Uploads pre-staged in `/opt/sarathi/.stage` (not web-reachable).
- [ ] Contabo left **running and paid** — it is the rollback.

> If any box is unticked, stop. A migration with an unticked precondition is a migration that
> discovers the missing piece at the worst moment.

---

## Step 1 — Freeze writes (Contabo)

```bash
ssh root@84.247.172.252
systemctl stop sarathi-web@1 sarathi-web@2 sarathi-worker
systemctl is-active sarathi-web@1 sarathi-web@2 sarathi-worker   # expect: inactive ×3
```

From here the sites are down. **This is the start of the user-visible window.**

*Why stop rather than sync live:* SQLite with WAL can be copied hot, but the worker writes on
timers. A five-minute freeze is cheaper than an hour spent proving nothing was lost.

**Rollback:** `systemctl start sarathi-worker sarathi-web@1 sarathi-web@2`. Nothing else changed yet.

## Step 2 — Final data sync (Contabo → Oracle)

```bash
# Consistent DB snapshot — never copy a live .db file directly
sqlite3 /opt/sarathi/sarathi_biz.db ".backup '/tmp/cutover.db'"
ls -lh /tmp/cutover.db                                  # sanity: ~20MB

RS="ssh -i /root/.ssh/id_migrate -o StrictHostKeyChecking=no"
rsync -az -e "$RS" /tmp/cutover.db ubuntu@161.118.186.201:/opt/sarathi/.stage/
# Delta only — the bulk was pre-staged, so this should be seconds
rsync -az --stats -e "$RS" /opt/sarathi/uploads /opt/sarathi/generated_pdfs /opt/sarathi/apk \
      ubuntu@161.118.186.201:/opt/sarathi/.stage/
shred -u /tmp/cutover.db
```

**Verify:** row counts must match exactly.

```bash
sqlite3 /opt/sarathi/sarathi_biz.db "SELECT COUNT(*) FROM nidaan_claims;"   # note it
```

**Rollback:** nothing on Contabo was modified. Start the services again.

## Step 3 — Put the data in place (Oracle)

```bash
ssh -i ~/.ssh/id_nidaan_oracle ubuntu@161.118.186.201
sudo systemctl stop sarathi-web@1 sarathi-web@2 sarathi-worker

sudo mv /opt/sarathi/.stage/cutover.db /opt/sarathi/sarathi_biz.db
sudo rm -f /opt/sarathi/sarathi_biz.db-wal /opt/sarathi/sarathi_biz.db-shm
for d in uploads generated_pdfs apk; do
  sudo rm -rf "/opt/sarathi/$d"
  sudo mv "/opt/sarathi/.stage/$d" "/opt/sarathi/$d"
done
sudo chown -R sarathi:sarathi /opt/sarathi/sarathi_biz.db /opt/sarathi/uploads \
     /opt/sarathi/generated_pdfs /opt/sarathi/apk

# Row count must equal what Contabo reported in Step 2
sudo -u sarathi sqlite3 /opt/sarathi/sarathi_biz.db "SELECT COUNT(*) FROM nidaan_claims;"
```

## Step 4 — Real secrets (Oracle)

```bash
# Place the real biz.env. NEVER via a world-readable path, never committed anywhere.
sudo install -o sarathi -g sarathi -m 600 /path/to/real-biz.env /opt/sarathi/biz.env
ls -l /opt/sarathi/biz.env        # must read: -rw------- sarathi sarathi
grep -c '^[A-Z0-9_]*=' /opt/sarathi/biz.env   # expect 74
```

**The ownership line is not a formality** — `biz.env` owned by root has 502'd both sites before.

## Step 5 — Start, and prove it before anyone sees it

```bash
sudo systemctl start sarathi-worker && sleep 8
sudo systemctl start sarathi-web@1 sarathi-web@2 && sleep 12
systemctl is-active sarathi-worker sarathi-web@1 sarathi-web@2   # active ×3

for p in 8001 8002; do curl -s -o /dev/null -w "$p: %{http_code}\n" http://127.0.0.1:$p/health; done

# The real proof: journeys against the REAL data, outbound disabled
cd /opt/sarathi && NIDAAN_NO_OUTBOUND=1 ./venv/bin/python -m journeys.run --quiet
#   → expect: 20 passed  0 failed
```

Then, still on the test hostnames (production is still Contabo, still stopped):

```bash
curl -s https://new.nidaanpartner.com/ | grep -o '<title>[^<]*'   # Nidaan
curl -s https://new.sarathi-ai.com/   | grep -o '<title>[^<]*'   # Sarathi-AI
```

**Rollback:** still free. Start Contabo, walk away, nothing external has changed.

## Step 6 — Remove the test-only Host pin

`/etc/nginx/sites-available/np-sarathi` currently pins `proxy_set_header Host` per block, because
the test hostnames are not the ones the app recognises. With the real domains arriving, that pin
becomes wrong — and would make **sarathi-ai.com serve Nidaan**.

```bash
sudo sed -i 's/proxy_set_header Host nidaanpartner.com;/proxy_set_header Host $host;/g;
             s/proxy_set_header Host sarathi-ai.com;/proxy_set_header Host $host;/g' \
     /etc/nginx/sites-available/np-sarathi
sudo sed -i 's/server_name new.nidaanpartner.com;/server_name nidaanpartner.com www.nidaanpartner.com new.nidaanpartner.com;/;
             s/server_name new.sarathi-ai.com;/server_name sarathi-ai.com www.sarathi-ai.com new.sarathi-ai.com;/' \
     /etc/nginx/sites-available/np-sarathi
sudo nginx -t && sudo systemctl reload nginx
```

Certificates for the real domains: copy from Contabo (`/etc/letsencrypt/`) or re-issue. Keep the
`new.*` names in `server_name` for now — they are how you verify without the DNS change.

**Verify before moving on** — send the real Host by hand:

```bash
curl -s --resolve nidaanpartner.com:443:127.0.0.1 https://nidaanpartner.com/ | grep -o '<title>[^<]*'
curl -s --resolve sarathi-ai.com:443:127.0.0.1   https://sarathi-ai.com/   | grep -o '<title>[^<]*'
```

Each must return **its own** product. This is the step that catches a wrong-product bug before a
customer does.

## Step 7 — The flip (Cloudflare · browser)

For **each** of nidaanpartner.com and sarathi-ai.com:

1. Cloudflare → the domain → **DNS → Records**
2. Edit the root `A` record (and `www` if it is an A record)
3. Change the IPv4 from `84.247.172.252` to **`161.118.186.201`**
4. **Leave proxy status as Proxied (orange).** Do not change it.
5. Save.

> **Note the old value before changing it.** The rollback is typing `84.247.172.252` back in.

## Step 8 — Verify production, both products

```bash
for u in https://nidaanpartner.com/ https://nidaanpartner.com/nidaan/ops \
         https://sarathi-ai.com/ https://sarathi-ai.com/superadmin; do
  echo "$u → $(curl -s -m 15 "$u" | grep -o '<title>[^<]*' | head -1)"
done
```

Expected: Nidaan, Nidaan Ops, Sarathi-AI, Cockpit — **each serving its own product.**

Then the things DNS does not carry by itself:

- [ ] **Log in** to `/nidaan/ops` as a real staff member — session, not just a 200.
- [ ] **Razorpay** — dashboard shows the webhook delivering (or send a test event).
- [ ] **WhatsApp Cloud** — inbound webhook reaches the new origin.
- [ ] **Email Radar** — `journalctl -u sarathi-worker | grep -i radar` shows a poll within 15 min.
- [ ] **Telegram** — bot answers.
- [ ] **A real login code** — the one path that has failed twice before. Send one, receive it.

## Step 9 — Close the door

Only once Step 8 is fully green:

```bash
sudo bash /opt/sarathi/deploy/lock-origin-to-cloudflare.sh apply
sudo bash /opt/sarathi/deploy/lock-origin-to-cloudflare.sh status
```

Then confirm from a non-Cloudflare machine that `http://161.118.186.201/` **times out**, while
`https://nidaanpartner.com/` still answers 200.

> This restores the control Contabo has had all along. Skipping it leaves the origin exposed to
> the whole internet, bypassing the WAF — and nobody would notice until it mattered.

## Step 10 — Leave Contabo alone

Do **not** cancel it. Keep it running and paid for **2–4 weeks**:

- It is the rollback for anything discovered late.
- Its backups keep running.
- Cancel only after a full billing and reminder cycle has passed cleanly on Oracle.

---

## Rollback procedure

1. Cloudflare → both domains → A record back to **`84.247.172.252`**, still proxied.
2. `ssh root@84.247.172.252 && systemctl start sarathi-worker sarathi-web@1 sarathi-web@2`
3. Verify both products answer.

Total: **two to three minutes.** Remember the caveat at the top — anything written on Oracle since
the flip does not come back. If that window is more than a few minutes old, take a snapshot of the
Oracle DB first so nothing is lost while you decide:

```bash
sudo -u sarathi sqlite3 /opt/sarathi/sarathi_biz.db ".backup '/opt/sarathi/backups/rollback-$(date +%s).db'"
```

---

## After cutover — the cleanup that is easy to forget

- [ ] Remove the `new.nidaanpartner.com` and `new.sarathi-ai.com` DNS records.
- [ ] Remove their certificates: `sudo certbot delete --cert-name new.nidaanpartner.com` (and the other).
- [ ] Drop the `new.*` names from `server_name`.
- [ ] Remove the temporary migration key: `/root/.ssh/id_migrate` on Contabo, and its line in
      `~/.ssh/authorized_keys` on Oracle.
- [ ] Delete `/opt/sarathi/.stage`.
- [ ] Confirm `backup-db` and `git-db-backup` have each run **on the new box** and produced output.
