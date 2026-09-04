"""
NidaanPartner — Email Update Radar (data + IMAP layer).

PHASE 1 (this file, initial): the mailbox VAULT + Test-Connection.
Each escalation customer hands over a dedicated Gmail (address + 16-char app-password). We store the
app-password ENCRYPTED AT REST (Fernet, key derived from EMAIL_VAULT_KEY or JWT_SECRET) and never
return it in any API response. `test_connection` verifies IMAP login without persisting anything new.

Later phases (poll + AI triage + flags + Tasks integration + silence + metrics) build on this table —
see PROJECT_MASTER_CONTEXT.md §A84. HARD RULE: the UI never names "IRDA/IRDAI/Lokpal"; those live only
in a founder-managed "priority senders" config.
"""
from __future__ import annotations

import os
import re
import base64
import hashlib
import asyncio
import logging
from typing import Optional

import aiosqlite
import biz_database as _db

logger = logging.getLogger("sarathi.radar")

DB_PATH = _db.DB_PATH

# Gmail defaults (editable per mailbox in the config drawer).
DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993


# ── Encryption at rest ───────────────────────────────────────────────────────
def _fernet():
    """Fernet cipher for app-passwords. Uses EMAIL_VAULT_KEY if set (rotate independently),
    else derives a stable key from JWT_SECRET with a radar-specific salt so it never collides
    with other Fernet users (e.g. the Telegram-CRM token vault)."""
    from cryptography.fernet import Fernet
    key = (os.getenv("EMAIL_VAULT_KEY") or "").strip()
    if not key:
        seed = (("nidaan-radar-vault::" + (os.getenv("JWT_SECRET") or "radar-fallback-seed"))).encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt((secret or "").encode()).decode()


def decrypt_secret(blob: str) -> str:
    return _fernet().decrypt((blob or "").encode()).decode()


def _mask_email(addr: str) -> str:
    addr = (addr or "").strip()
    if "@" not in addr:
        return addr
    local, _, domain = addr.partition("@")
    shown = local[:2] + "•••" if len(local) > 2 else (local[:1] + "•••")
    return f"{shown}@{domain}"


# ── IMAP connection test (blocking; call via asyncio.to_thread) ──────────────
def _imap_login_test(host: str, port: int, email: str, password: str) -> tuple[bool, str]:
    """Blocking IMAP SSL login + INBOX select. Returns (ok, status) where status is one of
    'ok' | 'auth_failed' | 'error:<detail>'. Never raises."""
    import imaplib
    M = None
    try:
        M = imaplib.IMAP4_SSL(host, int(port), timeout=15)
        M.login(email, password)
        typ, _ = M.select("INBOX", readonly=True)
        if typ != "OK":
            return (False, "error:could not open INBOX")
        return (True, "ok")
    except imaplib.IMAP4.error as e:
        # Bad credentials / app-password / IMAP disabled.
        return (False, "auth_failed")
    except Exception as e:  # noqa: BLE001 — network/DNS/TLS/timeout
        return (False, "error:" + str(e)[:180])
    finally:
        try:
            if M is not None:
                M.logout()
        except Exception:
            pass


async def test_connection(host: str, port: int, email: str, password: str) -> tuple[bool, str]:
    return await asyncio.to_thread(_imap_login_test, host or DEFAULT_IMAP_HOST,
                                   port or DEFAULT_IMAP_PORT, email, password)


# ── Mailbox CRUD ─────────────────────────────────────────────────────────────
async def list_mailboxes() -> list[dict]:
    """All configured mailboxes for the ops config table. NEVER returns the password —
    only a masked email + last sync status."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await conn.execute(
            """SELECT mailbox_id, label, account_id, email_address, imap_host, imap_port,
                      is_active, last_sync_status, last_sync_error, last_synced_at, pod,
                      pod_staff_ids, created_at
               FROM nidaan_radar_mailboxes ORDER BY label, email_address""")).fetchall()]
    for r in rows:
        r["email_masked"] = _mask_email(r.get("email_address"))
    return rows


async def get_mailbox(mailbox_id: int, *, with_secret: bool = False) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_radar_mailboxes WHERE mailbox_id=?", (mailbox_id,))).fetchone()
    if not row:
        return None
    d = dict(row)
    if not with_secret:
        d.pop("enc_password", None)
    return d


async def upsert_mailbox(*, mailbox_id: Optional[int], label: str, email_address: str,
                         app_password: str, imap_host: str, imap_port: int,
                         account_id: Optional[int], is_active: bool, pod: str,
                         pod_staff_ids: str, created_by: Optional[int]) -> int:
    """Create or update a mailbox. If app_password is blank on an update, the stored one is kept
    (so editing other fields doesn't require re-entering the secret). pod_staff_ids = comma list of
    staff_ids assigned to this case (first = primary assignee, rest = watchers)."""
    email_address = (email_address or "").strip().lower()
    pod_ids = ",".join(str(i) for i in _parse_ids(pod_staff_ids or ""))
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if mailbox_id:
            enc = None
            if (app_password or "").strip():
                enc = encrypt_secret(app_password.strip())
            sets = ["label=?", "email_address=?", "imap_host=?", "imap_port=?",
                    "account_id=?", "is_active=?", "pod=?", "pod_staff_ids=?",
                    "updated_at=CURRENT_TIMESTAMP"]
            params: list = [label, email_address, imap_host or DEFAULT_IMAP_HOST,
                            int(imap_port or DEFAULT_IMAP_PORT), account_id,
                            1 if is_active else 0, pod, pod_ids]
            if enc is not None:
                sets.append("enc_password=?")
                params.append(enc)
            params.append(mailbox_id)
            await conn.execute(
                f"UPDATE nidaan_radar_mailboxes SET {', '.join(sets)} WHERE mailbox_id=?", params)
            await conn.commit()
            return mailbox_id
        enc = encrypt_secret((app_password or "").strip())
        cur = await conn.execute(
            """INSERT INTO nidaan_radar_mailboxes
                 (label, email_address, enc_password, imap_host, imap_port, account_id,
                  is_active, pod, pod_staff_ids, created_by, consent_ack_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (label, email_address, enc, imap_host or DEFAULT_IMAP_HOST,
             int(imap_port or DEFAULT_IMAP_PORT), account_id, 1 if is_active else 0,
             pod, pod_ids, created_by))
        await conn.commit()
        return cur.lastrowid


async def delete_mailbox(mailbox_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "DELETE FROM nidaan_radar_mailboxes WHERE mailbox_id=?", (mailbox_id,))
        await conn.commit()
        return cur.rowcount > 0


async def set_sync_status(mailbox_id: int, status: str, error: str = "") -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_radar_mailboxes SET last_sync_status=?, last_sync_error=?, "
            "last_synced_at=CURRENT_TIMESTAMP WHERE mailbox_id=?",
            (status[:40], (error or "")[:300], mailbox_id))
        await conn.commit()


# A broken mailbox = we silently stop seeing that customer's authority mail. Alert super-admins after
# this many consecutive failed polls (re-alert at most daily until it recovers).
FAIL_ALERT_THRESHOLD = 3


async def _record_poll_failure(mailbox_id: int, status: str) -> None:
    """Record a failed poll, bump the consecutive-failure counter, and alert super-admins (all
    channels) once it crosses the threshold — so a dead mailbox never silently hides authority mail."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "UPDATE nidaan_radar_mailboxes SET last_sync_status=?, last_sync_error=?, "
            "last_synced_at=CURRENT_TIMESTAMP, fail_count=COALESCE(fail_count,0)+1 WHERE mailbox_id=?",
            (status.split(":")[0][:40], status[:300], mailbox_id))
        await conn.commit()
        row = await (await conn.execute(
            "SELECT label, email_address, fail_count, fail_alert_at FROM nidaan_radar_mailboxes "
            "WHERE mailbox_id=?", (mailbox_id,))).fetchone()
    if not row or (row["fail_count"] or 0) < FAIL_ALERT_THRESHOLD:
        return
    # Re-alert at most once per 24h until recovery (fail_alert_at is cleared on the next OK poll).
    import datetime as _dt
    recent = False
    if row["fail_alert_at"]:
        try:
            last = _dt.datetime.fromisoformat(str(row["fail_alert_at"]).replace("Z", ""))
            recent = (_dt.datetime.utcnow() - last).total_seconds() < 86400
        except Exception:
            recent = False
    if recent:
        return
    await _alert_mailbox_down(mailbox_id, dict(row), status)


async def _alert_mailbox_down(mailbox_id: int, row: dict, status: str) -> None:
    try:
        import biz_nidaan_notifications as _notif
        sa = await _notif._super_admin_staff()
        ids = [s["staff_id"] for s in sa]
        if not ids:
            return
        label = row.get("label") or _mask_email(row.get("email_address", "")) or f"#{mailbox_id}"
        subject = "📨 Email Updates: a customer mailbox is not syncing"
        body = (f"The mailbox “{label}” has failed {row.get('fail_count')} checks in a row "
                f"({(status or '').split(':')[0]}). Authority emails for this customer may be missed. "
                f"Please re-check its app password in Email Updates → Mailboxes.")
        await _notif.notify_staff_inapp(ids, subject, body, event_key="radar.mailbox_down", email=True)
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE nidaan_radar_mailboxes SET fail_alert_at=CURRENT_TIMESTAMP WHERE mailbox_id=?",
                (mailbox_id,))
            await conn.commit()
        logger.info("Radar mailbox-down alert sent: mailbox=%s label=%s", mailbox_id, label)
    except Exception as e:  # noqa: BLE001
        logger.warning("radar mailbox-down alert failed for %s: %s", mailbox_id, e)


async def keepalive_sweep(max_idle_days: int = 20) -> int:
    """Keep configured mailboxes ALIVE against provider inactivity policies: for each active
    app-password mailbox not touched in `max_idle_days`, do a light IMAP login (the activity signal
    Google/Yahoo count) and stamp last_keepalive_at. Healthy mailboxes (polled every ~15 min) never
    qualify, so this only re-pings dormant/paused ones — and naturally surfaces broken creds too.
    (Forwarding-only mailboxes have no stored password → we can't keep those alive; the customer must.)"""
    import datetime as _dt
    cutoff = (_dt.datetime.utcnow() - _dt.timedelta(days=max_idle_days))
    done = 0
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT mailbox_id, imap_host, imap_port, email_address, enc_password, "
            "last_synced_at, last_keepalive_at FROM nidaan_radar_mailboxes "
            "WHERE is_active=1 AND COALESCE(enc_password,'')<>''")).fetchall()
    for r in rows:
        # Skip if polled or kept-alive recently.
        def _recent(ts):
            if not ts:
                return False
            try:
                return _dt.datetime.fromisoformat(str(ts).replace("Z", "")) > cutoff
            except Exception:
                return False
        if _recent(r["last_synced_at"]) or _recent(r["last_keepalive_at"]):
            continue
        try:
            pw = decrypt_secret(r["enc_password"] or "")
        except Exception:
            continue
        ok, _msg = await asyncio.to_thread(_imap_login_test, r["imap_host"] or DEFAULT_IMAP_HOST,
                                           int(r["imap_port"] or DEFAULT_IMAP_PORT),
                                           r["email_address"], pw)
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE nidaan_radar_mailboxes SET last_keepalive_at=CURRENT_TIMESTAMP WHERE mailbox_id=?",
                (r["mailbox_id"],))
            await conn.commit()
        if not ok:
            await _record_poll_failure(r["mailbox_id"], "keepalive_login_failed")
        done += 1
    if done:
        logger.info("Radar keepalive: pinged %d dormant mailbox(es)", done)
    return done


async def test_mailbox(mailbox_id: int) -> tuple[bool, str]:
    """Test a STORED mailbox (decrypts its secret in-memory only), and record the result."""
    mb = await get_mailbox(mailbox_id, with_secret=True)
    if not mb:
        return (False, "not_found")
    try:
        pw = decrypt_secret(mb.get("enc_password") or "")
    except Exception:
        await set_sync_status(mailbox_id, "error", "decrypt_failed")
        return (False, "error:decrypt_failed")
    ok, status = await test_connection(mb.get("imap_host"), mb.get("imap_port"),
                                       mb.get("email_address"), pw)
    await set_sync_status(mailbox_id, "ok" if ok else status.split(":")[0], "" if ok else status)
    return (ok, status)


# ── Radar config (priority senders + silence threshold) ──────────────────────
async def get_config() -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT priority_senders, silence_days FROM nidaan_radar_config WHERE id=1")).fetchone()
        if not row:
            await conn.execute(
                "INSERT OR IGNORE INTO nidaan_radar_config (id, priority_senders, silence_days) "
                "VALUES (1,'',5)")
            await conn.commit()
            return {"priority_senders": "", "silence_days": 5}
        return dict(row)


async def set_config(priority_senders: str, silence_days: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO nidaan_radar_config (id, priority_senders, silence_days, updated_at) "
            "VALUES (1,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(id) DO UPDATE SET priority_senders=excluded.priority_senders, "
            "silence_days=excluded.silence_days, updated_at=CURRENT_TIMESTAMP",
            ((priority_senders or "")[:4000], max(1, min(int(silence_days or 5), 60))))
        await conn.commit()


def _parse_senders(blob: str) -> list[str]:
    import re as _re
    return [s.strip().lower() for s in _re.split(r"[,\n;]+", blob or "") if s.strip()]


def _is_priority_sender(from_addr: str, senders: list[str]) -> bool:
    fa = (from_addr or "").strip().lower()
    dom = fa.split("@")[-1] if "@" in fa else fa
    for s in senders:
        s = s.lstrip("@").strip()
        if not s:
            continue
        if fa == s or dom == s or dom.endswith("." + s):
            return True
    return False


def _decide_flag(triage: dict, priority_sender: bool) -> str:
    """🔴 red = act now · 🟡 amber = review · ⚪ green = auto-clear. Fail-safe: anything not clearly
    noise defaults to amber (a human looks) — never auto-clear on doubt."""
    cat = (triage.get("category") or "other").lower()
    pri = (triage.get("priority") or "normal").lower()
    if priority_sender or cat in ("authority", "legal", "court") or pri == "high":
        return "red"
    if cat in ("receipt", "marketing", "spam"):
        return "green"
    return "amber"


# ── Incremental IMAP fetch (blocking; call via asyncio.to_thread) ────────────
def _imap_fetch_new(host: str, port: int, email: str, password: str,
                    last_uid: int, limit: int = 25) -> tuple[list, int, str, bool]:
    """Fetch envelope + short snippet for messages with UID > last_uid. Returns
    (messages, highest_uid, status, is_baseline). On the FIRST poll (last_uid<=0) we only record the
    baseline UID and create NO items (don't flag years of pre-existing mail). Blocking; never raises."""
    import re as _re
    import imaplib
    import email as _email
    from email.utils import parsedate_to_datetime, parseaddr
    from email.header import make_header, decode_header
    M = None
    out: list = []
    try:
        M = imaplib.IMAP4_SSL(host or DEFAULT_IMAP_HOST, int(port or DEFAULT_IMAP_PORT), timeout=25)
        M.login(email, password)
        typ, _ = M.select("INBOX", readonly=True)
        if typ != "OK":
            return ([], last_uid, "error:inbox", False)
        typ, data = M.uid("search", None, "ALL")
        if typ != "OK":
            return ([], last_uid, "error:search", False)
        uids = [int(x) for x in (data[0].split() if data and data[0] else [])]
        if not uids:
            return ([], last_uid, "ok", False)
        high = max(uids)
        if last_uid <= 0:
            return ([], high, "ok", True)   # baseline only
        new_uids = sorted(u for u in uids if u > last_uid)[-limit:]
        for u in new_uids:
            try:
                typ, fdata = M.uid("fetch", str(u),
                                   "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)] BODY.PEEK[1]<0.700>)")
                if typ != "OK" or not fdata:
                    continue
                hdr_bytes, body_bytes = b"", b""
                for part in fdata:
                    if isinstance(part, tuple) and len(part) >= 2:
                        marker = (part[0] or b"").upper()
                        payload = part[1] or b""
                        if b"HEADER" in marker:
                            hdr_bytes = payload
                        elif b"BODY[1]" in marker:
                            body_bytes = payload
                        elif not hdr_bytes:
                            hdr_bytes = payload
                msg = _email.message_from_bytes(hdr_bytes)
                try:
                    subj = str(make_header(decode_header(msg.get("Subject", "") or "")))[:300]
                except Exception:
                    subj = (msg.get("Subject", "") or "")[:300]
                fname, faddr = parseaddr(msg.get("From", "") or "")
                try:
                    fname = str(make_header(decode_header(fname or "")))[:120]
                except Exception:
                    fname = (fname or "")[:120]
                mid = (msg.get("Message-ID", "") or "").strip()[:300]
                recv = None
                try:
                    dt = parsedate_to_datetime(msg.get("Date", ""))
                    if dt:
                        recv = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    recv = None
                try:
                    snip = body_bytes.decode("utf-8", "ignore")
                except Exception:
                    snip = ""
                snip = _re.sub(r"<[^>]+>", " ", snip)
                snip = _re.sub(r"\s+", " ", snip).strip()[:400]
                out.append({"uid": u, "message_id": mid, "from_addr": (faddr or "")[:160],
                            "from_name": fname, "subject": subj, "snippet": snip, "received_at": recv})
            except Exception:
                continue
        return (out, high, "ok", False)
    except imaplib.IMAP4.error:
        return ([], last_uid, "auth_failed", False)
    except Exception as e:  # noqa: BLE001
        return ([], last_uid, "error:" + str(e)[:150], False)
    finally:
        try:
            if M is not None:
                M.logout()
        except Exception:
            pass


# ── Poll: fetch → AI triage → store as radar items ───────────────────────────
async def poll_mailbox(mb: dict, senders: list[str]) -> int:
    """Poll ONE mailbox: fetch new mail, AI-triage each, store flagged items, advance last_uid."""
    import biz_ai as _ai
    mid = mb["mailbox_id"]
    try:
        pw = decrypt_secret(mb.get("enc_password") or "")
    except Exception:
        await set_sync_status(mid, "error", "decrypt_failed")
        return 0
    msgs, high_uid, status, _baseline = await asyncio.to_thread(
        _imap_fetch_new, mb.get("imap_host"), mb.get("imap_port"),
        mb.get("email_address"), pw, int(mb.get("last_uid") or 0), 25)
    if status != "ok":
        await _record_poll_failure(mid, status)
        return 0
    created = 0
    pending_tasks = []   # (item_id, flag, subject, summary, deeplink) for red/amber → Tasks module
    async with aiosqlite.connect(DB_PATH) as conn:
        for m in msgs:
            ps = _is_priority_sender(m["from_addr"], senders)
            triage = await _ai.radar_triage_email(m["from_addr"], m["subject"], m["snippet"])
            flag = _decide_flag(triage, ps)
            try:
                cur = await conn.execute(
                    """INSERT OR IGNORE INTO nidaan_radar_items
                         (mailbox_id, uid, message_id, from_addr, from_name, subject, snippet,
                          received_at, flag, category, priority_sender, deadline, needs_action,
                          ai_reason, ai_summary)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (mid, m["uid"], m["message_id"], m["from_addr"], m["from_name"], m["subject"],
                     m["snippet"], m["received_at"], flag, triage["category"], 1 if ps else 0,
                     triage["deadline"], 1 if triage["needs_response"] else 0,
                     triage["reason"], triage["summary"]))
                if cur.rowcount:
                    created += 1
                    if flag in ("red", "amber"):
                        pending_tasks.append((cur.lastrowid, flag, m["subject"] or "",
                                              triage["summary"] or "", gmail_deeplink(m["message_id"])))
            except Exception:
                pass
        await conn.execute(
            "UPDATE nidaan_radar_mailboxes SET last_uid=?, last_sync_status='ok', "
            "last_sync_error='', last_synced_at=CURRENT_TIMESTAMP, fail_count=0, fail_alert_at=NULL "
            "WHERE mailbox_id=?",
            (high_uid, mid))
        await conn.commit()
    # Create/append Tasks OUTSIDE the write connection (fresh conns + notifications). Sequential so
    # multiple new emails on one mailbox fold into a single open task.
    for (item_id, flag, subject, summary, deeplink) in pending_tasks:
        await ensure_task_for_item(mid, item_id, flag, subject, summary, deeplink)
    return created


async def poll_all_mailboxes() -> int:
    """Worker entry point: poll every active mailbox (staggered), triage + store new items."""
    cfg = await get_config()
    senders = _parse_senders(cfg.get("priority_senders") or "")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        mbs = [dict(r) for r in await (await conn.execute(
            "SELECT * FROM nidaan_radar_mailboxes WHERE is_active=1")).fetchall()]
    total = 0
    for mb in mbs:
        try:
            total += await poll_mailbox(mb, senders)
        except Exception as e:  # noqa: BLE001
            logger.warning("radar poll_mailbox %s failed: %s", mb.get("mailbox_id"), e)
        await asyncio.sleep(2)   # stagger — don't hammer Gmail
    if mbs:
        logger.info("Radar poll: %d mailbox(es), %d new item(s)", len(mbs), total)
    return total


# ── Read side (for the ops radar view) ───────────────────────────────────────
async def list_items(flag: str = "", limit: int = 120, bucket: str = "") -> list[dict]:
    where, params = [], []
    # Lifecycle buckets (the clean, non-messy view): act = unaddressed inbound needing a reply;
    # waiting = we replied, awaiting them; resolved = case marked done.
    if bucket == "act":
        where.append("i.status='new' AND i.flag IN ('red','amber')")
    elif bucket == "waiting":
        where.append("i.status='responded'")
    elif bucket == "resolved":
        where.append("i.status IN ('resolved','closed')")
    elif flag in ("red", "amber", "green"):
        where.append("i.flag=?")
        params.append(flag)
    q = ("SELECT i.*, m.label AS mailbox_label, m.email_address AS mailbox_email "
         "FROM nidaan_radar_items i JOIN nidaan_radar_mailboxes m ON m.mailbox_id=i.mailbox_id")
    if where:
        q += " WHERE " + " AND ".join(where)
    q += (" ORDER BY CASE i.flag WHEN 'red' THEN 0 WHEN 'amber' THEN 1 ELSE 2 END, "
          "i.received_at DESC, i.item_id DESC LIMIT ?")
    params.append(max(1, min(int(limit), 300)))
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await conn.execute(q, params)).fetchall()]
    for r in rows:
        r["mailbox_email_masked"] = _mask_email(r.pop("mailbox_email", ""))
    return rows


async def radar_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN flag='red' THEN 1 ELSE 0 END),0) AS red, "
            "COALESCE(SUM(CASE WHEN flag='amber' THEN 1 ELSE 0 END),0) AS amber, "
            "COALESCE(SUM(CASE WHEN date(created_at)=date('now') THEN 1 ELSE 0 END),0) AS today "
            "FROM nidaan_radar_items")).fetchone()
    return dict(row) if row else {"total": 0, "red": 0, "amber": 0, "today": 0}


# ── P3: Tasks integration ────────────────────────────────────────────────────
_TASK_CLOSED = ("done", "cancelled")


def _parse_ids(blob: str) -> list[int]:
    out = []
    for x in re.split(r"[,\s]+", blob or ""):
        x = x.strip()
        if x.isdigit():
            out.append(int(x))
    return out


def gmail_deeplink(message_id: str) -> str:
    mid = (message_id or "").strip().strip("<>")
    if not mid:
        return ""
    from urllib.parse import quote
    return "https://mail.google.com/mail/u/0/#search/" + quote("rfc822msgid:" + mid)


async def _link_item_task(item_id: int, task_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE nidaan_radar_items SET quick_task_id=? WHERE item_id=?",
                           (task_id, item_id))
        await conn.commit()


async def _set_open_task(mailbox_id: int, task_id: Optional[int]) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE nidaan_radar_mailboxes SET open_task_id=? WHERE mailbox_id=?",
                           (task_id, mailbox_id))
        await conn.commit()


async def ensure_task_for_item(mailbox_id: int, item_id: int, flag: str, subject: str,
                               summary: str, deeplink: str) -> None:
    """Create or update the mailbox's OPEN radar-task (Tasks module) for a red/amber item.
    One open task per mailbox = one per case: a new email on the same case appends a note + re-notifies
    (red pings all channels); once the task is done/cancelled the next email opens a fresh one
    (auto-reopen). Unassigned mailbox → no task (item still shows in the Radar view). Never raises."""
    try:
        import biz_nidaan as _nid
        import biz_nidaan_notifications as _nnot
        mb = await get_mailbox(mailbox_id)
        if not mb:
            return
        pod = _parse_ids(mb.get("pod_staff_ids") or "")
        if not pod:
            return  # unassigned — nothing to notify; item stays visible in Radar
        primary = pod[0]
        creator = mb.get("created_by") or primary
        prio = "high" if flag == "red" else "normal"
        # Is the mailbox's existing task still open?
        open_task_id = mb.get("open_task_id")
        task_open = False
        if open_task_id:
            try:
                qt = await _nid.get_quick_task(open_task_id)
                task_open = bool(qt and (qt.get("status") or "").lower() not in _TASK_CLOSED)
            except Exception:
                task_open = False
        if task_open:
            try:
                await _nid.add_quick_task_note(
                    quick_task_id=open_task_id, staff_id=creator,
                    note=f"📨 New update: {subject}\n{summary}" + (f"\nOpen in Gmail: {deeplink}" if deeplink else ""))
            except Exception:
                pass
            await _link_item_task(item_id, open_task_id)
            if flag == "red":   # re-ping the assignee on a fresh act-now update
                try:
                    qt = await _nid.get_quick_task(open_task_id)
                    if qt:
                        await _nnot.on_quick_task_assigned(qt)
                except Exception:
                    pass
            return
        # No open task → create one for this case.
        title = f"📨 {(mb.get('label') or _mask_email(mb.get('email_address')))}: {(subject or '(no subject)')[:80]}"
        desc = ((summary + "\n\n") if summary else "") + (f"Open in Gmail: {deeplink}" if deeplink else "")
        try:
            qid = await _nid.create_quick_task(
                title=title, description=desc, created_by_staff_id=creator,
                assigned_to_staff_id=primary, priority=prio, source="radar")
        except Exception as e:
            logger.warning("radar task create failed: %s", e)
            return
        rest = [s for s in pod[1:] if s and s != primary]
        if rest:
            try:
                await _nid.add_task_watchers(qid, rest, added_by=creator)
            except Exception:
                pass
        await _set_open_task(mailbox_id, qid)
        await _link_item_task(item_id, qid)
        try:
            qt = await _nid.get_quick_task(qid)
            if qt:
                await _nnot.on_quick_task_assigned(qt)
        except Exception as e:
            logger.warning("radar task notify failed: %s", e)
    except Exception as e:  # noqa: BLE001
        logger.warning("ensure_task_for_item error: %s", e)


# ── P4: silence 'Chase' detection + efficiency metrics ───────────────────────
def _older_than_days(ts, days: int, default: bool = False) -> bool:
    if not ts:
        return default
    from datetime import datetime, timedelta
    dt = None
    s = str(ts).replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:19] if fmt.endswith("%S") else s[:10], fmt)
            break
        except Exception:
            continue
    if dt is None:
        return default
    return (datetime.utcnow() - dt) >= timedelta(days=int(days))


async def run_silence_sweep() -> int:
    """For each active mailbox with an OPEN case, if no inbound update for silence_days days,
    raise a 🟡 'Chase' note on its task + re-notify (once per silence window). Never raises."""
    try:
        cfg = await get_config()
        days = int(cfg.get("silence_days") or 5)
        import biz_nidaan as _nid
        import biz_nidaan_notifications as _nnot
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            mbs = [dict(r) for r in await (await conn.execute(
                "SELECT * FROM nidaan_radar_mailboxes "
                "WHERE is_active=1 AND open_task_id IS NOT NULL")).fetchall()]
        chased = 0
        for mb in mbs:
            try:
                async with aiosqlite.connect(DB_PATH) as conn:
                    conn.row_factory = aiosqlite.Row
                    row = await (await conn.execute(
                        "SELECT MAX(received_at) AS last_in, MAX(created_at) AS last_seen "
                        "FROM nidaan_radar_items WHERE mailbox_id=?", (mb["mailbox_id"],))).fetchone()
                last = (row["last_in"] or row["last_seen"]) if row else None
                # only chase a case that's still open AND genuinely quiet AND not chased recently
                if not _older_than_days(last, days, default=False):
                    continue
                allow = (not mb.get("last_chase_at")) or _older_than_days(mb.get("last_chase_at"), days, default=True)
                if not allow:
                    continue
                qt = await _nid.get_quick_task(mb["open_task_id"])
                if not qt or (qt.get("status") or "").lower() in _TASK_CLOSED:
                    continue
                actor = mb.get("created_by") or qt.get("assigned_to_staff_id")
                try:
                    await _nid.add_quick_task_note(
                        quick_task_id=mb["open_task_id"], staff_id=actor,
                        note=f"🟡 Chase: no reply on this case for {days}+ days — consider following up.")
                except Exception:
                    pass
                try:
                    await _nnot.on_quick_task_assigned(qt)
                except Exception:
                    pass
                async with aiosqlite.connect(DB_PATH) as conn:
                    await conn.execute(
                        "UPDATE nidaan_radar_mailboxes SET last_chase_at=CURRENT_TIMESTAMP "
                        "WHERE mailbox_id=?", (mb["mailbox_id"],))
                    await conn.commit()
                chased += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("silence sweep mailbox %s: %s", mb.get("mailbox_id"), e)
        if chased:
            logger.info("Radar silence sweep: %d chase(s)", chased)
        return chased
    except Exception as e:  # noqa: BLE001
        logger.warning("run_silence_sweep error: %s", e)
        return 0


async def radar_metrics() -> dict:
    """Efficiency metrics — auto-triage rate is the 5→1 proof (share of mail auto-cleared)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        mb = dict(await (await conn.execute(
            "SELECT COUNT(*) AS active, "
            "COALESCE(SUM(CASE WHEN last_sync_status='ok' THEN 1 ELSE 0 END),0) AS ok "
            "FROM nidaan_radar_mailboxes WHERE is_active=1")).fetchone())
        it = dict(await (await conn.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN flag='red' THEN 1 ELSE 0 END),0) AS red, "
            "COALESCE(SUM(CASE WHEN flag='amber' THEN 1 ELSE 0 END),0) AS amber, "
            "COALESCE(SUM(CASE WHEN flag='green' THEN 1 ELSE 0 END),0) AS green, "
            "COALESCE(SUM(CASE WHEN status='new' AND flag IN ('red','amber') THEN 1 ELSE 0 END),0) AS act, "
            "COALESCE(SUM(CASE WHEN status='responded' THEN 1 ELSE 0 END),0) AS waiting, "
            "COALESCE(SUM(CASE WHEN status IN ('resolved','closed') THEN 1 ELSE 0 END),0) AS resolved, "
            "COALESCE(SUM(CASE WHEN date(created_at)=date('now') THEN 1 ELSE 0 END),0) AS today, "
            "COALESCE(SUM(CASE WHEN COALESCE(deadline,'')<>'' THEN 1 ELSE 0 END),0) AS with_deadline "
            "FROM nidaan_radar_items")).fetchone())
    total = it["total"] or 0
    return {"mailboxes_active": mb["active"], "mailboxes_ok": mb["ok"],
            "coverage_pct": round(mb["ok"] / mb["active"] * 100) if mb["active"] else 0,
            "total": total, "red": it["red"], "amber": it["amber"], "green": it["green"],
            "act": it["act"], "waiting": it["waiting"], "resolved": it["resolved"],
            "today": it["today"], "with_deadline": it["with_deadline"],
            "auto_triage_pct": round(it["green"] / total * 100) if total else 0}


# ── P5: read full email + reply-as-customer (SMTP) + lifecycle + purge ────────
def _smtp_host(imap_host: str) -> str:
    h = (imap_host or DEFAULT_IMAP_HOST).strip()
    return h.replace("imap.", "smtp.") if h.startswith("imap.") else h.replace("imap", "smtp")


def _imap_fetch_full(host: str, port: int, email: str, password: str, uid: int) -> Optional[dict]:
    """Fetch ONE full email by UID → {from, subject, date, message_id, body}. Blocking; never raises."""
    import imaplib
    import email as _email
    from email.header import make_header, decode_header
    M = None
    try:
        M = imaplib.IMAP4_SSL(host or DEFAULT_IMAP_HOST, int(port or DEFAULT_IMAP_PORT), timeout=25)
        M.login(email, password)
        M.select("INBOX", readonly=True)
        typ, data = M.uid("fetch", str(uid), "(RFC822)")
        if typ != "OK" or not data or not data[0]:
            return {"error": "not_found"}
        msg = _email.message_from_bytes(data[0][1])
        try:
            subj = str(make_header(decode_header(msg.get("Subject", "") or "")))
        except Exception:
            subj = msg.get("Subject", "") or ""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                    try:
                        body = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "ignore")
                        break
                    except Exception:
                        pass
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        try:
                            html = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "ignore")
                            body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
                            break
                        except Exception:
                            pass
        else:
            try:
                body = (msg.get_payload(decode=True) or b"").decode(msg.get_content_charset() or "utf-8", "ignore")
            except Exception:
                body = str(msg.get_payload())
        return {"from": msg.get("From", ""), "subject": subj, "date": msg.get("Date", ""),
                "message_id": (msg.get("Message-ID", "") or "").strip(), "body": (body or "").strip()[:20000]}
    except imaplib.IMAP4.error:
        return {"error": "auth_failed"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:150]}
    finally:
        try:
            if M is not None:
                M.logout()
        except Exception:
            pass


def _smtp_send(host: str, port: int, email: str, password: str, to_addr: str,
               subject: str, body: str, in_reply_to: str = "") -> tuple:
    """Send a reply FROM the customer's mailbox via SMTP. Blocking; returns (ok, err|message_id)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.utils import make_msgid, formatdate
    try:
        msg = MIMEText(body or "", "plain", "utf-8")
        msg["From"] = email
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        mid = make_msgid()
        msg["Message-ID"] = mid
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        s = smtplib.SMTP(host, int(port), timeout=25)
        s.starttls()
        s.login(email, password)
        s.sendmail(email, [to_addr], msg.as_string())
        s.quit()
        return (True, mid)
    except smtplib.SMTPAuthenticationError:
        return (False, "auth_failed")
    except Exception as e:  # noqa: BLE001
        return (False, str(e)[:150])


async def get_item(item_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT i.*, m.email_address, m.imap_host, m.imap_port, m.enc_password "
            "FROM nidaan_radar_items i JOIN nidaan_radar_mailboxes m ON m.mailbox_id=i.mailbox_id "
            "WHERE i.item_id=?", (item_id,))).fetchone()
    return dict(row) if row else None


async def read_full_email(item_id: int) -> dict:
    """Fetch the full email body for a radar item (live from the mailbox) — so staff read it in ops."""
    it = await get_item(item_id)
    if not it:
        return {"error": "not_found"}
    try:
        pw = decrypt_secret(it.get("enc_password") or "")
    except Exception:
        return {"error": "decrypt_failed"}
    res = await asyncio.to_thread(_imap_fetch_full, it.get("imap_host"), it.get("imap_port"),
                                  it.get("email_address"), pw, int(it.get("uid") or 0))
    return res or {"error": "fetch_failed"}


# ── Attachments → claim documents ────────────────────────────────────────────
# A forwarded claim email often carries the actual paperwork. We NEVER auto-file it: an
# attachment on the wrong claim is a privacy and data-integrity bug. Instead we extract the
# files, SUGGEST the claim we think it belongs to, and let a human confirm in one click.
_ATTACH_MAX_FILES = 10
_ATTACH_MAX_BYTES = 25 * 1024 * 1024      # per file
_ATTACH_SKIP_EXT = (".ics", ".vcf", ".p7s", ".asc")


def _imap_fetch_attachments(host: str, port: int, email: str, password: str, uid: int,
                            names_only: bool = False) -> list:
    """Real attachments on ONE email → [{name, size, data?}]. Blocking; never raises."""
    import imaplib
    import email as _email
    from email.header import make_header, decode_header
    M = None
    out: list = []
    try:
        M = imaplib.IMAP4_SSL(host or DEFAULT_IMAP_HOST, int(port or DEFAULT_IMAP_PORT), timeout=40)
        M.login(email, password)
        M.select("INBOX", readonly=True)
        typ, data = M.uid("fetch", str(uid), "(RFC822)")
        if typ != "OK" or not data or not data[0]:
            return []
        msg = _email.message_from_bytes(data[0][1])
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            fname = part.get_filename()
            disp = str(part.get("Content-Disposition") or "")
            # A real attachment: it has a filename, or is explicitly dispositioned as one.
            if not fname and "attachment" not in disp:
                continue
            try:
                fname = str(make_header(decode_header(fname))) if fname else "attachment"
            except Exception:
                fname = fname or "attachment"
            if fname.lower().endswith(_ATTACH_SKIP_EXT):
                continue
            payload = part.get_payload(decode=True) or b""
            if not payload or len(payload) > _ATTACH_MAX_BYTES:
                continue
            rec = {"name": fname[:160], "size": len(payload)}
            if not names_only:
                rec["data"] = payload
            out.append(rec)
            if len(out) >= _ATTACH_MAX_FILES:
                break
        return out
    except Exception as e:  # noqa: BLE001
        logger.info("attachment fetch failed uid=%s: %s", uid, e)
        return []
    finally:
        try:
            if M is not None:
                M.logout()
        except Exception:
            pass


async def _attachments(item_id: int, names_only: bool) -> tuple:
    """(item, [attachments]) or (None, []) — shared by the list + file calls."""
    it = await get_item(item_id)
    if not it:
        return None, []
    try:
        pw = decrypt_secret(it.get("enc_password") or "")
    except Exception:
        return it, []
    files = await asyncio.to_thread(
        _imap_fetch_attachments, it.get("imap_host"), it.get("imap_port"),
        it.get("email_address"), pw, int(it.get("uid") or 0), names_only)
    return it, files


async def suggest_claim(item: dict) -> Optional[dict]:
    """Best-effort guess of which claim an email belongs to — a SUGGESTION only, never applied
    automatically. Strongest signal first: an explicit NP-#### reference, then a sender address
    that matches a claim's own contacts."""
    hay = f"{item.get('subject') or ''} {item.get('snippet') or ''} {item.get('ai_summary') or ''}"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        m = re.search(r"\bNP[-\s]?(\d{1,6})\b", hay, re.I) or re.search(r"#(\d{2,6})\b", hay)
        if m:
            cid = int(m.group(1))
            r = await (await conn.execute(
                "SELECT claim_id, insured_name FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone()
            if r:
                r = dict(r)
                return {"claim_id": r["claim_id"], "label": f"NP-{r['claim_id']:04d} {r.get('insured_name') or ''}",
                        "reason": "claim number found in the email"}
        addr = (item.get("from_addr") or "").strip().lower()
        if addr and "@" in addr:
            r = await (await conn.execute(
                "SELECT claim_id, insured_name FROM nidaan_claims WHERE COALESCE(archived,0)=0 AND ("
                "LOWER(COALESCE(complainant_email,''))=? OR LOWER(COALESCE(insured_email,''))=?) "
                "ORDER BY claim_id DESC LIMIT 1", (addr, addr))).fetchone()
            if r:
                r = dict(r)
                return {"claim_id": r["claim_id"], "label": f"NP-{r['claim_id']:04d} {r.get('insured_name') or ''}",
                        "reason": "sender matches this claim's contact"}
    return None


async def list_attachments(item_id: int) -> dict:
    """Attachment names/sizes on this email + the claim we'd suggest filing them against."""
    it, files = await _attachments(item_id, names_only=True)
    if not it:
        return {"error": "not_found"}
    return {"attachments": files, "suggestion": await suggest_claim(it)}


async def file_attachments_to_claim(item_id: int, claim_id: int, by: str = "") -> dict:
    """Attach this email's files to a claim: normalise each to PDF and save it as a claim
    document. Human-confirmed only. Returns {ok, filed, skipped}."""
    it, files = await _attachments(item_id, names_only=False)
    if not it:
        return {"ok": False, "error": "not_found"}
    if not files:
        return {"ok": False, "error": "no_attachments"}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        c = await (await conn.execute(
            "SELECT claim_id, account_id FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    if not c:
        return {"ok": False, "error": "claim_not_found"}
    account_id = dict(c).get("account_id")
    import biz_doc_splitter as _split
    import biz_nidaan as _bn
    from pathlib import Path
    import uuid as _uuid
    docs_dir = Path(__file__).parent / "uploads" / "nidaan-docs"
    filed, skipped = 0, []
    for f in files:
        try:
            pdf, pages, _sk = _split.normalize_to_pdf([(f["name"], f["data"])])
            if not pdf or not pages:
                skipped.append(f["name"])
                continue
            docs_dir.mkdir(parents=True, exist_ok=True)
            stored = f"{_uuid.uuid4().hex}.pdf"
            (docs_dir / stored).write_bytes(pdf)
            await _bn.save_claim_document(
                account_id=account_id, stored_name=stored,
                original_name=f"NP-{claim_id}_{f['name']}"[:180], file_size=len(pdf),
                mime_type="application/pdf", claim_id=claim_id, source="email")
            filed += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("file attachment failed (%s → claim %s): %s", f.get("name"), claim_id, e)
            skipped.append(f.get("name") or "file")
    if filed:
        try:
            await _bn.record_claim_activity(
                claim_id, "email_attachment", channel="email", direction="in",
                actor=(by or "ops"),
                summary=f"Filed {filed} attachment(s) from the email \"{(it.get('subject') or '')[:60]}\"")
        except Exception:
            pass
    return {"ok": filed > 0, "filed": filed, "skipped": skipped}


async def send_reply(item_id: int, body: str, staff_id: Optional[int]) -> dict:
    """Reply to the sender of a radar item, FROM the customer's mailbox (SMTP). Records the send,
    moves the item to 'responded' (→ Waiting bucket). Returns {ok} or {error}."""
    it = await get_item(item_id)
    if not it:
        return {"ok": False, "error": "not_found"}
    to_addr = (it.get("from_addr") or "").strip()
    if not to_addr:
        return {"ok": False, "error": "no_recipient"}
    try:
        pw = decrypt_secret(it.get("enc_password") or "")
    except Exception:
        return {"ok": False, "error": "decrypt_failed"}
    subj = (it.get("subject") or "").strip()
    if subj and not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    ok, info = await asyncio.to_thread(
        _smtp_send, _smtp_host(it.get("imap_host")), 587, it.get("email_address"), pw,
        to_addr, subj or "(no subject)", body or "", (it.get("message_id") or ""))
    if not ok:
        return {"ok": False, "error": info}
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO nidaan_radar_sent (mailbox_id, item_id, to_addr, subject, body, message_id, sent_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (it["mailbox_id"], item_id, to_addr, subj, (body or "")[:8000], info, staff_id))
        await conn.execute("UPDATE nidaan_radar_items SET status='responded' WHERE item_id=?", (item_id,))
        await conn.commit()
    return {"ok": True}


async def set_item_status(item_id: int, status: str) -> bool:
    if status not in ("new", "responded", "resolved", "closed"):
        return False
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("UPDATE nidaan_radar_items SET status=? WHERE item_id=?",
                                 (status, item_id))
        await conn.commit()
        return cur.rowcount > 0


async def list_sent(mailbox_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await conn.execute(
            "SELECT sent_id, item_id, to_addr, subject, body, created_at FROM nidaan_radar_sent "
            "WHERE mailbox_id=? ORDER BY sent_id ASC", (mailbox_id,))).fetchall()]


async def purge_mailbox(mailbox_id: int) -> bool:
    """Disconnect + PURGE a mailbox once its case is decided — removes the mailbox (creds), all its
    radar items, and sent-reply records. Nothing is retained (founder's policy)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT mailbox_id FROM nidaan_radar_mailboxes WHERE mailbox_id=?", (mailbox_id,))).fetchone()
        if not row:
            return False
        await conn.execute("DELETE FROM nidaan_radar_items WHERE mailbox_id=?", (mailbox_id,))
        await conn.execute("DELETE FROM nidaan_radar_sent WHERE mailbox_id=?", (mailbox_id,))
        await conn.execute("DELETE FROM nidaan_radar_mailboxes WHERE mailbox_id=?", (mailbox_id,))
        await conn.commit()
    return True
