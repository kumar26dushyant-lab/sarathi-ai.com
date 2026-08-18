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
