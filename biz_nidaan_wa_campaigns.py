"""
NidaanPartner — WhatsApp BULK CAMPAIGNS (superadmin).

Send an approved template (cold / business-initiated) or a free-form composer message (only to
contacts inside their 24h session) to a FILTERED audience of opted-in, non-stopped contacts.

Consent is always enforced: audience is `opted_in=1 AND status<>'stopped'`, and each send re-checks
the session/template gate exactly like biz_nidaan_wa_orchestrator.wa_journey. Per-send rows are
written to nidaan_wa_messages (via wa_flow.log_message inside the send layer); this module keeps the
campaign summary + running stats in nidaan_wa_campaigns.

Design notes:
- Campaign templates are expected to take a SINGLE {{1}} = first-name variable (welcome / intro_value
  style). We fill it best-effort from the contact's linked claim/account; unknown → a neutral greeting.
- Runs in the background (asyncio task) so a large audience never blocks the request. Small inter-send
  delay keeps us well under WhatsApp rate limits.
"""
from __future__ import annotations

import json
import asyncio
import logging
from typing import Optional

import aiosqlite

import biz_database as db
import biz_nidaan_whatsapp as _wa
import biz_nidaan_wa_flow as _flow
import biz_nidaan_wa_messages as _msg

logger = logging.getLogger("nidaan.wa.campaign")
DB_PATH = db.DB_PATH

_SEND_GAP_SECONDS = 0.4          # gentle pacing between sends
_LANG_MAP = {"hi": "hi", "en": "en", "hinglish": "en"}   # Meta template language code


def _audience_sql(filters: dict) -> tuple[str, list]:
    """Build the WHERE clause for the eligible audience. Consent is ALWAYS enforced."""
    where = ["opted_in=1", "COALESCE(status,'active')<>'stopped'"]
    params: list = []
    lang = (filters or {}).get("language") or "any"
    if lang in ("hi", "en", "hinglish"):
        where.append("COALESCE(language,'hinglish')=?")
        params.append(lang)
    seg = (filters or {}).get("segment") or "all"
    if seg == "has_claim":
        where.append("claim_id IS NOT NULL")
    elif seg == "no_claim":
        where.append("claim_id IS NULL")
    return " AND ".join(where), params


async def count_audience(filters: dict) -> int:
    sql, params = _audience_sql(filters)
    async with aiosqlite.connect(DB_PATH) as c:
        row = await (await c.execute(
            f"SELECT COUNT(*) FROM nidaan_wa_contacts WHERE {sql}", params)).fetchone()
    return int(row[0]) if row else 0


async def _list_audience(filters: dict) -> list[dict]:
    sql, params = _audience_sql(filters)
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = await (await c.execute(
            f"SELECT msisdn, claim_id, account_id, COALESCE(language,'hinglish') AS language "
            f"FROM nidaan_wa_contacts WHERE {sql}", params)).fetchall()
    return [dict(r) for r in rows]


async def _contact_name(claim_id: Optional[int], account_id: Optional[int]) -> str:
    """Best-effort first name for the {{1}} template variable."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            if claim_id:
                r = await (await c.execute(
                    "SELECT complainant_name, insured_name FROM nidaan_claims WHERE claim_id=?",
                    (claim_id,))).fetchone()
                if r:
                    nm = (dict(r).get("complainant_name") or dict(r).get("insured_name") or "").strip()
                    if nm:
                        return nm.split(" ")[0]
            if account_id:
                r = await (await c.execute(
                    "SELECT owner_name FROM nidaan_accounts WHERE account_id=?", (account_id,))).fetchone()
                if r:
                    nm = (dict(r).get("owner_name") or "").strip()
                    if nm:
                        return nm.split(" ")[0]
    except Exception:
        pass
    return ""


async def list_campaigns(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = await (await c.execute(
            "SELECT * FROM nidaan_wa_campaigns ORDER BY campaign_id DESC LIMIT ?",
            (max(1, min(int(limit or 30), 100)),))).fetchall()
    return [dict(r) for r in rows]


async def create_and_run(*, name: str, template_name: str, kind: str, lang: str,
                         filters: dict, by_id: Optional[int], by_name: str) -> dict:
    """Create the campaign row and launch the send in the background. Returns {campaign_id, total}."""
    if not _wa.is_configured():
        return {"ok": False, "error": "WhatsApp is not configured"}
    total = await count_audience(filters)
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute(
            "INSERT INTO nidaan_wa_campaigns (name, template_name, kind, lang, audience, status, "
            "total, created_by, created_by_name) VALUES (?,?,?,?,?,?,?,?,?)",
            ((name or "Campaign")[:120], (template_name or "").strip(), (kind or "").strip(),
             (lang or "hinglish"), json.dumps(filters or {}), "running", total, by_id, (by_name or "")[:80]))
        await c.commit()
        campaign_id = cur.lastrowid
    asyncio.create_task(_run_campaign(campaign_id, template_name, kind, lang, filters))
    return {"ok": True, "campaign_id": campaign_id, "total": total}


async def send_test(*, template_name: str, kind: str, lang: str, to: str) -> dict:
    """Send ONE message to a single number (the sender's own, to preview a campaign)."""
    if not _wa.is_configured():
        return {"ok": False, "error": "WhatsApp is not configured"}
    msisdn = _wa.normalize_msisdn(to)
    if not msisdn:
        return {"ok": False, "error": "Enter a valid mobile number"}
    return await _send_one(msisdn, None, None, template_name, kind, lang)


async def _send_one(msisdn: str, claim_id, account_id, template_name: str, kind: str, lang: str) -> dict:
    """One recipient: in-session → free-form composer; else approved template. Consent-safe."""
    name = await _contact_name(claim_id, account_id)
    ctx = {"name": name}
    try:
        if await _flow.in_session_window(msisdn):
            body = _msg.compose(kind or "intro_value", lang or "hinglish", ctx)
            res = await _wa.send_text(msisdn, body)
        elif template_name:
            comps = _wa.body_params(name or "ji")
            res = await _wa.send_template(msisdn, template_name, _LANG_MAP.get(lang or "hinglish", "en"), comps)
        else:
            return {"ok": False, "error": "needs_template"}
        return res if isinstance(res, dict) else {"ok": bool(res)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}


async def _run_campaign(campaign_id: int, template_name: str, kind: str, lang: str, filters: dict) -> None:
    audience = await _list_audience(filters)
    sent = failed = skipped = 0
    for contact in audience:
        msisdn = contact.get("msisdn")
        if not msisdn:
            continue
        res = await _send_one(msisdn, contact.get("claim_id"), contact.get("account_id"),
                              template_name, kind, lang)
        if res.get("ok"):
            sent += 1
        elif res.get("error") == "needs_template":
            skipped += 1
        else:
            failed += 1
        # Persist progress periodically so the panel shows a live count.
        if (sent + failed + skipped) % 10 == 0:
            await _update_stats(campaign_id, sent, failed, skipped, done=False)
        await asyncio.sleep(_SEND_GAP_SECONDS)
    await _update_stats(campaign_id, sent, failed, skipped, done=True)
    logger.info("wa campaign %s done: sent=%s failed=%s skipped=%s", campaign_id, sent, failed, skipped)


async def _update_stats(campaign_id: int, sent: int, failed: int, skipped: int, *, done: bool) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            if done:
                await c.execute(
                    "UPDATE nidaan_wa_campaigns SET sent=?, failed=?, skipped=?, status='done', "
                    "finished_at=CURRENT_TIMESTAMP WHERE campaign_id=?",
                    (sent, failed, skipped, campaign_id))
            else:
                await c.execute(
                    "UPDATE nidaan_wa_campaigns SET sent=?, failed=?, skipped=? WHERE campaign_id=?",
                    (sent, failed, skipped, campaign_id))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("campaign stats update failed: %s", e)
