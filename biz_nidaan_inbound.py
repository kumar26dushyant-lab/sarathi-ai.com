"""
biz_nidaan_inbound.py — Inbound handler for the 3 official Nidaan WhatsApp
numbers. Routes documents to claims, parses "reply with number" responses
for disambiguation, and logs every inbound to nidaan_messages.

Q5 routing logic:
  • 1 active claim   → auto-attach silently, send confirmation
  • 0 active claims  → reply asking to register first
  • 2+ active claims → ask subscriber to reply with claim number
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import aiosqlite

import biz_database as db
import biz_nidaan_notifications as nnot

logger = logging.getLogger("sarathi.nidaan.inbound")

# Storage for inbound documents (mirrors structure used in Phase 2 for marketing)
DOCS_DIR = Path(__file__).parent / "uploads" / "nidaan_docs"


def _norm10(p: str) -> str:
    digits = re.sub(r"[^0-9]", "", str(p or ""))
    return digits[-10:] if len(digits) >= 10 else ""


async def _find_account_by_phone(phone10: str) -> Optional[dict]:
    if not phone10:
        return None
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Match by last 10 digits — Nidaan account or its linked subscriber
        cur = await conn.execute("""
            SELECT * FROM nidaan_accounts
            WHERE SUBSTR(REPLACE(REPLACE(phone, '+',''),' ',''), -10) = ?
            LIMIT 1
        """, (phone10,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def _active_claims_for_account(account_id: int) -> list[dict]:
    """Active = not terminal stage 'closed'."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT claim_id, insured_name, claim_type, stage, created_at
            FROM nidaan_claims
            WHERE account_id = ? AND COALESCE(stage,'') != 'closed'
            ORDER BY created_at DESC
        """, (account_id,))
        return [dict(r) for r in await cur.fetchall()]


async def _save_inbound_message(*, claim_id: Optional[int], account_id: int,
                                 content: str, source_channel: str,
                                 source_wa_instance: str, source_wa_message_id: str,
                                 attachment_doc_id: Optional[int] = None) -> int:
    """Append to nidaan_messages thread (or unattached log if claim_id unknown)."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("""
            INSERT INTO nidaan_messages
              (claim_id, sender_type, sender_subscriber_id, content,
               attachment_doc_id, source_channel, source_wa_instance, source_wa_message_id)
            VALUES (?, 'subscriber', ?, ?, ?, ?, ?, ?)
        """, (claim_id if claim_id else 0, account_id, content,
              attachment_doc_id, source_channel, source_wa_instance, source_wa_message_id))
        await conn.commit()
        return cur.lastrowid


async def _save_document(*, claim_id: int, account_id: int,
                         filename: str, raw_bytes: bytes, mime_type: str,
                         source: str, source_wa_instance: str,
                         source_wa_message_id: str) -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    import hashlib
    sha = hashlib.sha256(raw_bytes).hexdigest()[:24]
    # Preserve extension if recognizable
    ext = ".bin"
    if "." in filename:
        cand = "." + filename.rsplit(".", 1)[-1].lower()
        if 2 <= len(cand) <= 6:
            ext = cand
    elif "/" in mime_type:
        sub = mime_type.rsplit("/", 1)[-1].split(";")[0]
        if sub:
            ext = "." + sub[:5]
    claim_dir = DOCS_DIR / str(claim_id)
    claim_dir.mkdir(parents=True, exist_ok=True)
    path = claim_dir / f"{sha}{ext}"
    path.write_bytes(raw_bytes)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("""
            INSERT INTO nidaan_documents
              (claim_id, uploaded_by_type, uploaded_by_id, original_filename,
               storage_path, mime_type, size_bytes, source,
               source_wa_instance, source_wa_message_id)
            VALUES (?, 'subscriber', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (claim_id, account_id, filename, str(path),
              mime_type, len(raw_bytes), source, source_wa_instance, source_wa_message_id))
        await conn.commit()
        return cur.lastrowid


async def _send_official_reply(*, instance: str, to_phone10: str, message: str):
    """Outbound to subscriber FROM the same official number we received on
    (so the conversation stays in one thread). Best-effort, swallows errors."""
    try:
        import biz_whatsapp_evolution as wa_evo
        jid = f"91{to_phone10}@s.whatsapp.net"
        await wa_evo.send_text(instance, jid, message, delay_ms=1200)
    except Exception as e:
        logger.warning("Nidaan official reply failed: %s", e)


def _detect_media(msg_payload: dict) -> Optional[dict]:
    """If the inbound contains media, return {kind, filename, mime}.
    Evolution surfaces these under msg.message.{imageMessage|documentMessage|
    audioMessage|videoMessage}. We accept any."""
    msg_body = (msg_payload or {}).get("message") or {}
    for kind in ("documentMessage", "imageMessage", "videoMessage",
                 "audioMessage"):
        if kind in msg_body and isinstance(msg_body[kind], dict):
            blob = msg_body[kind]
            return {
                "kind": kind,
                "filename": blob.get("fileName") or blob.get("title")
                            or f"wa_{kind.replace('Message','')}",
                "mime": blob.get("mimetype") or "application/octet-stream",
            }
    return None


# ═════════════════════════════════════════════════════════════════════════════
#  Pending-routing flow (for 2+ active claims)
# ═════════════════════════════════════════════════════════════════════════════
async def _open_pending_routing(*, account_id: int, wa_message_id: str,
                                source_wa_instance: str,
                                eligible_claim_ids: list[int]) -> int:
    expires = (datetime.utcnow() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("""
            INSERT INTO nidaan_pending_doc_routing
              (account_id, wa_message_id, source_wa_instance,
               eligible_claim_ids, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (account_id, wa_message_id, source_wa_instance,
              json.dumps(eligible_claim_ids), expires))
        await conn.commit()
        return cur.lastrowid


async def _consume_pending_routing(*, account_id: int) -> Optional[dict]:
    """Pop the most recent unresolved pending row (within 30 min)."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT * FROM nidaan_pending_doc_routing
            WHERE account_id = ?
              AND resolved_to_claim IS NULL
              AND expires_at > datetime('now')
            ORDER BY created_at DESC LIMIT 1
        """, (account_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def _resolve_pending(pending_id: int, claim_id: int):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_pending_doc_routing SET resolved_to_claim=? WHERE pending_id=?",
            (claim_id, pending_id))
        await conn.commit()


# ═════════════════════════════════════════════════════════════════════════════
#  Main entry — called from sarathi_biz webhook handler
# ═════════════════════════════════════════════════════════════════════════════
async def handle_official_inbound(*, instance_slot: int, evolution_instance: str,
                                  from_phone: str, from_me: bool,
                                  wa_message_id: str, text: str,
                                  msg_payload: dict, remote_jid: str):
    """Process an inbound on one of the 3 official Nidaan numbers.
    Always returns silently — failures are logged, never raised."""
    # Update instance health (heartbeat)
    try:
        await nnot.update_instance_health(instance_slot, state="open")
    except Exception:
        pass

    # Skip messages we sent (outbound echo)
    if from_me:
        return

    phone10 = _norm10(from_phone)
    if not phone10:
        return
    account = await _find_account_by_phone(phone10)
    if not account:
        # Unknown sender — politely direct them to register
        await _send_official_reply(
            instance=evolution_instance, to_phone10=phone10,
            message=("Hello! We don't see an active NidaanPartner.com account "
                     "with this number. Please register at https://nidaanpartner.com "
                     "or call us back to get started."))
        return

    account_id = account["account_id"]
    media = _detect_media(msg_payload)

    # Check if there's a pending doc-routing prompt from a recent send
    pending = await _consume_pending_routing(account_id=account_id)
    if pending and text:
        # Try to parse a digit reply
        m = re.search(r"\d+", text.strip())
        if m:
            chosen_idx = int(m.group(0))
            try:
                eligible = json.loads(pending["eligible_claim_ids"]) or []
            except Exception:
                eligible = []
            if 1 <= chosen_idx <= len(eligible):
                target_claim = eligible[chosen_idx - 1]
                await _resolve_pending(pending["pending_id"], target_claim)
                # Find the original wa_message_id media and download — but
                # in practice we'd ask the user to resend. Acknowledge selection.
                await _send_official_reply(
                    instance=evolution_instance, to_phone10=phone10,
                    message=(f"✓ Got it. Send the document again now and we'll attach "
                             f"it to your case #{target_claim}."))
                await _save_inbound_message(
                    claim_id=target_claim, account_id=account_id,
                    content=f"Subscriber selected case #{target_claim}",
                    source_channel="whatsapp",
                    source_wa_instance=evolution_instance,
                    source_wa_message_id=wa_message_id)
                return

    active = await _active_claims_for_account(account_id)

    # ── Media-bearing inbound ────────────────────────────────────────────────
    if media:
        if len(active) == 0:
            await _send_official_reply(
                instance=evolution_instance, to_phone10=phone10,
                message=("Thanks for the document, but we don't see any active case "
                         "for you yet. Please file a claim review first at "
                         "https://nidaanpartner.com/nidaan/dashboard and try again."))
            return
        if len(active) == 1:
            # Auto-attach silently
            target = active[0]
            try:
                import biz_whatsapp_evolution as wa_evo
                # Re-fetch the media bytes from Evolution
                key = {"id": wa_message_id, "remoteJid": remote_jid, "fromMe": False}
                raw_b64 = await wa_evo.get_media_base64(evolution_instance, key)
                import base64
                raw_bytes = base64.b64decode(raw_b64) if raw_b64 else b""
            except Exception as e:
                logger.warning("Media fetch failed: %s", e)
                raw_bytes = b""
            if not raw_bytes:
                await _send_official_reply(
                    instance=evolution_instance, to_phone10=phone10,
                    message="We received your file but couldn't download it — please try sending again.")
                return
            doc_id = await _save_document(
                claim_id=target["claim_id"], account_id=account_id,
                filename=media["filename"], raw_bytes=raw_bytes,
                mime_type=media["mime"], source="whatsapp",
                source_wa_instance=evolution_instance,
                source_wa_message_id=wa_message_id)
            await _save_inbound_message(
                claim_id=target["claim_id"], account_id=account_id,
                content=f"📎 {media['filename']}",
                attachment_doc_id=doc_id,
                source_channel="whatsapp",
                source_wa_instance=evolution_instance,
                source_wa_message_id=wa_message_id)
            await _send_official_reply(
                instance=evolution_instance, to_phone10=phone10,
                message=(f"✓ Got it — *{media['filename']}* attached to your "
                         f"case #{target['claim_id']}. We'll review and update you."))
            # Notify assigned associate(s)
            try:
                await nnot.on_document_received(claim_id=target["claim_id"],
                                                 doc_id=doc_id, source="whatsapp")
            except Exception:
                pass
            return
        # 2+ active claims — ask which one
        eligible_ids = [c["claim_id"] for c in active]
        await _open_pending_routing(
            account_id=account_id, wa_message_id=wa_message_id,
            source_wa_instance=evolution_instance,
            eligible_claim_ids=eligible_ids)
        lines = ["You have multiple open cases. Reply with the number for the right one:"]
        for i, c in enumerate(active, 1):
            lines.append(f"{i}. Case #{c['claim_id']} — {c['insured_name']} ({c['claim_type']})")
        lines.append("\nThen resend the document.")
        await _send_official_reply(
            instance=evolution_instance, to_phone10=phone10,
            message="\n".join(lines))
        return

    # ── Plain-text inbound (no media): log as thread message ────────────────
    target_claim_id = active[0]["claim_id"] if len(active) == 1 else None
    await _save_inbound_message(
        claim_id=target_claim_id, account_id=account_id,
        content=text or "(empty)",
        source_channel="whatsapp",
        source_wa_instance=evolution_instance,
        source_wa_message_id=wa_message_id)
    # For now, polite acknowledgement.  Phase 5 will add AI auto-reply.
    if text and len(active) > 0:
        await _send_official_reply(
            instance=evolution_instance, to_phone10=phone10,
            message=("Thanks for your message — our team will respond soon. "
                     "You can also reply on your dashboard at "
                     "https://nidaanpartner.com/nidaan/dashboard"))
