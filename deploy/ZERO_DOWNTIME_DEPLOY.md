# Zero-Downtime Deploy — Runbook

> Goal: eliminate the ~30–60s **502 on every deploy** (both nidaanpartner.com
> and sarathi-ai.com) caused by restarting the single app process — the HTTP
> port isn't bound again until all the slow startup (esp. `start_all_tenant_bots`)
> finishes.

## The design (why it works)

The app has **in-process singletons** that must run exactly once — Telegram
master + tenant bots (one `getUpdates` poller per token, else 409 conflicts) and
the reminder scheduler (else reminders/SLA fire N times). So we can't just run
N copies. Instead we split by role (the app reads `APP_ROLE`, already deployed):

| Tier | Unit | Role | Port | In nginx pool? | Runs bots/scheduler? |
|------|------|------|------|----------------|----------------------|
| Worker | `sarathi-worker` | `worker` | 8100 | No (background only) | **Yes** (the singletons) |
| Web ×2 | `sarathi-web@1/2` | `web` | 8001/8002 | Yes (ip_hash) | No |

nginx load-balances the two web instances with `ip_hash` (sticky — needed because
OTP/CSRF live in process memory). The deploy script **rolling-restarts** web@1
then web@2, each gated on `/health`, so ≥1 web instance is always serving → no 502.
The worker restarts once (brief, non-user-facing; bots are resilient pollers).

`APP_ROLE` defaults to `full` (legacy single-process behaviour), so nothing
changes until you complete the cutover below.

---

## One-time cutover (ordered — avoids 502 AND double-bots)

Run as a sudo-capable user on the server. **Do the steps in this order** — the
old `sarathi.service` keeps the bots until the very end, so we never have two bot
pollers at once.

> **Host gotcha (learned in the live cutover, 2026-06-14):** on this box the app
> already runs on **port 8001** (`SERVER_PORT=8001` in `biz.env`), and systemd
> here lets `EnvironmentFile=` (biz.env) WIN over `Environment=`. So you can't set
> the per-instance port with `Environment=SERVER_PORT=…` — biz.env clobbers it.
> The units instead read the port from a **later** `EnvironmentFile`. Create them:
> ```bash
> sudo mkdir -p /etc/sarathi
> echo 'SERVER_PORT=8001' | sudo tee /etc/sarathi/sarathi-web-1.env
> echo 'SERVER_PORT=8002' | sudo tee /etc/sarathi/sarathi-web-2.env
> echo 'SERVER_PORT=8100' | sudo tee /etc/sarathi/sarathi-worker.env
> ```
> Also: never put an nginx backup inside `sites-enabled/` — the `*` include loads
> it as a second config (duplicate-zone error). Back up to `/root/nginx-backups/`.
> Because the live app holds 8001, bring up **web@2 first**, switch nginx to the
> pool, THEN swap the old service for web@1 + worker (sequence below).

### 1. Install the units (+ the port env files above)
```bash
cd /opt/sarathi
sudo cp deploy/sarathi-worker.service /etc/systemd/system/
sudo cp deploy/sarathi-web@.service   /etc/systemd/system/
sudo systemctl daemon-reload
```

### 2. Start the WEB tier (no bots → no conflict with the still-running old service)
```bash
sudo systemctl enable --now sarathi-web@1 sarathi-web@2
# verify both are healthy on their own ports:
curl -s -o /dev/null -w 'web@1 %{http_code}\n' http://127.0.0.1:8001/health
curl -s -o /dev/null -w 'web@2 %{http_code}\n' http://127.0.0.1:8002/health   # expect 200 200
```

### 3. Point nginx at the pool
- Add the `upstream sarathi_app {…}` block from
  `deploy/nginx-upstream-zerodowntime.conf` to the `http{}` context of your site
  config (the hardened conf is `deploy/nginx-sarathi-hardened.conf`).
- Change every `proxy_pass http://127.0.0.1:8000;` → `proxy_pass http://sarathi_app;`
  and add the `proxy_next_upstream …` lines (see the snippet in that file).
```bash
sudo nginx -t && sudo systemctl reload nginx
```
- Verify public traffic now flows through the web tier:
```bash
curl -sk -o /dev/null -w '%{http_code}\n' https://sarathi-ai.com/
curl -sk -o /dev/null -w '%{http_code}\n' https://nidaanpartner.com/        # expect 200 200
```

### 4. Hand the singletons to the worker (old service OFF first → no double bots)
```bash
sudo systemctl stop sarathi          # stops old bots + scheduler (port 8000 freed)
sudo systemctl disable sarathi       # don't let it come back on reboot
sudo systemctl enable --now sarathi-worker
curl -s -o /dev/null -w 'worker %{http_code}\n' http://127.0.0.1:8100/health  # expect 200
```
Telegram bots have a few-seconds gap here (old stopped → worker started). That's
fine — public HTTP stayed up the whole time via the web tier.

### 5. Passwordless systemctl for the deploy webhook (runs as `sarathi`)
```bash
echo 'sarathi ALL=(root) NOPASSWD: /usr/bin/systemctl restart sarathi-worker, /usr/bin/systemctl restart sarathi-web@1, /usr/bin/systemctl restart sarathi-web@2' \
  | sudo tee /etc/sudoers.d/sarathi-deploy
sudo visudo -cf /etc/sudoers.d/sarathi-deploy   # syntax check
```

### 6. Deploy mechanism — rolling script + dedicated oneshot unit
`deploy/auto-deploy.sh` in the repo **is** the rolling script now (the deploy does
`git reset --hard`, so a pkill-all version here would come back and cause a 502 —
keep it rolling). Two things make the **webhook** path zero-downtime:

1. **Run it in its own cgroup.** The webhook handler lives inside a web instance,
   so running the script directly puts it in that instance's cgroup — and
   `systemctl restart sarathi-web@N` (KillMode=control-group) kills the deploy
   mid-roll. So `_run_deploy` triggers a **oneshot unit** instead:
   ```bash
   sudo cp deploy/sarathi-deploy.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo touch /var/log/sarathi-deploy.log && sudo chown sarathi:sarathi /var/log/sarathi-deploy.log
   ```
2. **Sudoers** must allow the `sarathi` user to start it + restart the units:
   ```
   sarathi ALL=(root) NOPASSWD: /usr/bin/systemctl restart sarathi-worker, \
     /usr/bin/systemctl restart sarathi-web@1, /usr/bin/systemctl restart sarathi-web@2, \
     /usr/bin/systemctl start sarathi-deploy.service, \
     /usr/bin/systemctl start --no-block sarathi-deploy.service
   ```
The webhook now does `sudo -n systemctl start --no-block sarathi-deploy.service`
→ the deploy runs in its own cgroup → the rolling web restarts can't kill it.
Verified live: oneshot deploy completes (~35s), each web instance health-gated,
both sites stay up.

---

## Verify it (do this on the NEXT deploy)

In one terminal, hammer the live site once a second; in another, trigger a deploy
(push to master). You should see an unbroken stream of `200` — no `502`.
```bash
while true; do curl -sk -o /dev/null -w '%{http_code} ' https://sarathi-ai.com/; sleep 1; done
```

---

## Rollback (if anything misbehaves)
```bash
sudo systemctl disable --now sarathi-web@1 sarathi-web@2 sarathi-worker
sudo systemctl enable --now sarathi             # back to the single full process
# revert nginx proxy_pass to http://127.0.0.1:8000 and: sudo nginx -t && sudo systemctl reload nginx
cp /opt/sarathi/deploy/auto-deploy.legacy.sh /opt/sarathi/deploy/auto-deploy.sh
```

---

## Notes / caveats
- **SQLite under 3 processes:** writes now come from worker + 2 web instances.
  Ensure WAL mode + a `busy_timeout` (the app should already set these). Occasional
  lock contention is handled by retry/busy_timeout; if it ever becomes a problem
  the real fix is Postgres (separate, larger migration).
- **In-memory OTP/CSRF + ip_hash:** a client mid-OTP whose web instance restarts
  during a deploy may need to re-request the code (rare, deploy-window only).
  Moving these stores to the DB removes the caveat and lets us drop ip_hash.
- **Memory:** worker (full bots) + 2 light web instances. The web instances skip
  tenant bots, so they're lean. Watch `systemctl status` memory after cutover.
