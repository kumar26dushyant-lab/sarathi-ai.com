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
                      is_active, last_sync_status, last_sync_error, last_synced_at, pod, created_at
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
                         created_by: Optional[int]) -> int:
    """Create or update a mailbox. If app_password is blank on an update, the stored one is kept
    (so editing other fields doesn't require re-entering the secret)."""
    email_address = (email_address or "").strip().lower()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if mailbox_id:
            enc = None
            if (app_password or "").strip():
                enc = encrypt_secret(app_password.strip())
            sets = ["label=?", "email_address=?", "imap_host=?", "imap_port=?",
                    "account_id=?", "is_active=?", "pod=?", "updated_at=CURRENT_TIMESTAMP"]
            params: list = [label, email_address, imap_host or DEFAULT_IMAP_HOST,
                            int(imap_port or DEFAULT_IMAP_PORT), account_id, 1 if is_active else 0, pod]
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
                  is_active, pod, created_by)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (label, email_address, enc, imap_host or DEFAULT_IMAP_HOST,
             int(imap_port or DEFAULT_IMAP_PORT), account_id, 1 if is_active else 0, pod, created_by))
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
        await set_sync_status(mid, status.split(":")[0], status)
        return 0
    created = 0
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
            except Exception:
                pass
        await conn.execute(
            "UPDATE nidaan_radar_mailboxes SET last_uid=?, last_sync_status='ok', "
            "last_sync_error='', last_synced_at=CURRENT_TIMESTAMP WHERE mailbox_id=?",
            (high_uid, mid))
        await conn.commit()
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
async def list_items(flag: str = "", limit: int = 120) -> list[dict]:
    where, params = [], []
    if flag in ("red", "amber", "green"):
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
