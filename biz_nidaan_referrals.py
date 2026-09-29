# -*- coding: utf-8 -*-
"""Claims from customers someone referred - for that staff member or Authorized Partner (AP).

Founder, 29 Sep: "Trivesh shared code and subscriber signed up and filed a claim for Uttam Singh,
but this claim is not visible to Trivesh (Team Member) login. can we ensure if any claim raised by
referred signup subscriber those claims should be visible to respective AP and staff on their
dashboard somewhere so that they can followup and/or provide required info if needed."

WHY IT WAS MISSING. A referral is recorded on the ACCOUNT (`nidaan_accounts.branch_code`, which
holds a branch code or a staff referral code). A claim the subscriber files later carries no code
of its own - claim #233 has an empty `branch_code`. A team member sees only claims they are
assigned to or mentioned on; an AP's claim list shows only claims the AP raised itself. The
referrer could reach it only by opening the account in My Business, and there it showed a raw
status and nothing else.

WHAT THIS GIVES THEM - and deliberately no more. The referrer brought the customer; they are not
handling the case. So they see what they need to follow up: the stage in the words the customer
sees, which documents are still missing, who at Nidaan is handling it, and when it last moved. No
policy number, no insured's phone, no legal notes, no documents. And one action: send information
to the team, which lands on the claim's remarks and reaches the handler. Nothing here opens the
claim itself - biz_nidaan_claim_authz is unchanged.

ONE SOURCE. The staff My Business tab and the AP dashboard both call `referred_claims()`, and
both notes go through `add_referrer_note()` - the ownership rule exists once.
"""
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.referrals")

NOTE_MAX = 1000


def _db() -> str:
    return db.DB_PATH


def _code(code: str) -> str:
    return (code or "").strip().upper()


# The one ownership rule: the claim carries the code, or the customer's account does.
_REFERRED_SQL = (
    "COALESCE(c.archived,0)=0 AND (UPPER(COALESCE(c.branch_code,''))=? "
    "OR UPPER(COALESCE(a.branch_code,''))=?)")


async def staff_code(staff_id: int) -> str:
    """The staffer's referral code - read from the database, never from the token."""
    try:
        async with aiosqlite.connect(_db()) as c:
            r = await (await c.execute(
                "SELECT referral_code FROM nidaan_staff WHERE staff_id=? AND status='active' "
                "AND deleted_at IS NULL", (int(staff_id),))).fetchone()
        return _code(r[0] if r else "")
    except Exception as e:  # noqa: BLE001
        logger.info("referral code unreadable for staff %s: %s", staff_id, e)
        return ""


async def referred_claims(code: str, *, exclude_raised_by_branch: bool = False,
                          limit: int = 200) -> list[dict]:
    """Every live claim from a customer this code referred, newest activity first.

    `exclude_raised_by_branch`: an AP already sees the claims it raised itself in its own list,
    so its referred list leaves those out rather than show them twice.
    """
    code = _code(code)
    if not code:
        return []
    import biz_nidaan_claimant as _cl
    import biz_nidaan_doc_checklist as _ck
    extra = " AND COALESCE(c.origin,'')<>'branch'" if exclude_raised_by_branch else ""
    async with aiosqlite.connect(_db()) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT c.claim_id, c.account_id, c.claim_type, c.insurer_name, c.status, "
            "c.pipeline_stage, c.origin, c.created_at, c.docs_complete_at, "
            "EXISTS(SELECT 1 FROM nidaan_claim_doc_checklist k WHERE k.claim_id=c.claim_id) "
            "AS has_checklist, "
            "COALESCE(c.last_status_at, c.created_at) AS updated_at, "
            "a.owner_name, s.name AS handler "
            "FROM nidaan_claims c "
            "LEFT JOIN nidaan_accounts a ON a.account_id = c.account_id "
            "LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id "
            "WHERE " + _REFERRED_SQL + extra +
            " ORDER BY COALESCE(c.last_status_at, c.created_at) DESC LIMIT ?",
            (code, code, int(limit)))).fetchall()]
    out = []
    for r in rows:
        # "Still missing" only where the claim is really collecting documents: it has its OWN
        # checklist and nobody has marked it complete. Without a checklist, pending_required_docs
        # falls back to the claim type's full template - on a review-stage claim that read
        # "7 missing" for papers nobody has asked for (checked live, 29 Sep: #207, #128), and a
        # referrer would have chased the customer for them.
        missing = []
        if r.get("has_checklist") and not r.get("docs_complete_at"):
            try:
                missing = [{"en": d.get("en") or d.get("key"), "hi": d.get("hi") or ""}
                           for d in await _ck.pending_required_docs(r["claim_id"],
                                                                    r.get("claim_type") or "")]
            except Exception as e:  # noqa: BLE001
                logger.info("pending docs unreadable for claim %s: %s", r["claim_id"], e)
        out.append({
            "claim_id": r["claim_id"],
            "customer": r.get("owner_name") or "",
            "claim_type": r.get("claim_type") or "",
            "insurer": r.get("insurer_name") or "",
            "stage": _cl.claimant_status_label(r.get("status") or ""),
            "legal": bool(r.get("pipeline_stage")),
            "raised_by_customer": (r.get("origin") or "") != "branch",
            "handler": r.get("handler") or "",
            "missing": missing,
            "updated_at": r.get("updated_at") or "",
        })
    return out


async def is_referred(code: str, claim_id: int) -> bool:
    code = _code(code)
    if not code:
        return False
    try:
        async with aiosqlite.connect(_db()) as c:
            r = await (await c.execute(
                "SELECT 1 FROM nidaan_claims c "
                "LEFT JOIN nidaan_accounts a ON a.account_id = c.account_id "
                "WHERE c.claim_id=? AND " + _REFERRED_SQL, (int(claim_id), code, code))).fetchone()
        return bool(r)
    except Exception as e:  # noqa: BLE001
        logger.info("referral check failed for claim %s: %s", claim_id, e)
        return False          # fail closed


async def add_referrer_note(code: str, claim_id: int, text: str, *, who: str) -> dict:
    """Information from the referrer, onto the claim's remarks, and to whoever handles it.

    Refuses a claim this code did not refer - the same answer as "no such claim", so the endpoint
    cannot be used to discover which claim numbers exist.
    """
    text = " ".join((text or "").split())[:NOTE_MAX]
    if len(text) < 2:
        return {"ok": False, "error": "Write what you want the team to know."}
    if not await is_referred(code, claim_id):
        return {"ok": False, "not_found": True}
    import biz_nidaan as _n
    await _n.record_claim_activity(
        claim_id, "referrer_note", channel="web", direction="in",
        actor=("%s (referrer)" % (who or code))[:80], summary=text[:400])
    await _tell_handler(claim_id, text, who or code)
    return {"ok": True}


async def _tell_handler(claim_id: int, text: str, who: str) -> None:
    """The claim's handler hears it; with nobody assigned, whoever is on duty, then the admins."""
    try:
        import biz_nidaan as _n
        import biz_nidaan_notifications as _nn
        async with aiosqlite.connect(_db()) as c:
            r = await (await c.execute(
                "SELECT assigned_to_staff_id, pipeline_stage FROM nidaan_claims WHERE claim_id=?",
                (int(claim_id),))).fetchone()
        ids = [r[0]] if r and r[0] else []
        if not ids and r and r[1]:
            try:
                ids = list(await _n.on_duty_rep_ids(r[1]))
            except Exception:  # noqa: BLE001
                ids = []
        if not ids:
            ids = [a["staff_id"] for a in await _nn._super_admin_staff()]
        if ids:
            await _nn.notify_staff_inapp(
                ids, "\U0001f4ac NP-%s — information from the referrer" % claim_id,
                "%s wrote:\n\n%s\n\nIt is on the claim's remarks." % (who, text),
                event_key="claim.referrer_note", email=False, claim_id=claim_id)
    except Exception as e:  # noqa: BLE001 - the note is saved either way
        logger.warning("referrer note alert failed for claim %s: %s", claim_id, e)
