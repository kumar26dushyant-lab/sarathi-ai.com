"""
NidaanPartner WhatsApp — WHO IS THIS, AND WHAT MAY THEY BE TOLD.

WhatsApp guarantees the message genuinely came from that number (Meta verifies possession), so a
number that matches our records is an authenticated identity — the same factor an SMS OTP proves,
without the friction. That lets the bot actually SERVE people instead of dead-ending into "our
team will contact you".

Roles we resolve, in priority order:
  complainant — the number on a claim (they may hear about THEIR claims)
  subscriber  — an account holder (their plan + the claims filed under it)
  branch      — a branch / My-Business partner (their branch's book, in aggregate)
  staff       — internal; politely redirected to the Telegram office bot
  unknown     — a prospect; sales/marketing flow, never any claim data

WHAT WE DISCLOSE is deliberately narrower than what we know. `safe_context()` returns a
customer-support view: friendly stage wording, what we need next, and nothing that would be
careless to put in writing — no internal notes, no staff names, no legal opinion, no settlement
figures, and no blunt "your claim has no basis". Sensitive turns are flagged `handoff_only` so a
human takes them.
"""
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.wa.identity")
DB_PATH = db.DB_PATH

# Internal status → what we actually say to a customer. Deliberately reassuring but honest;
# outcomes that need care (won/lost/no-scope) are never delivered by the bot.
_STAGE_SAY = {
    "intimated": "received — our team is going through the documents",
    "assigned": "with a case handler now",
    "in_review": "under expert review right now",
    "in_negotiation": "being actively pursued with the insurer",
    "review_delivered": "reviewed — our team is taking the next step",
    "resolved_won": "__sensitive__",
    "resolved_lost": "__sensitive__",
    "closed": "__sensitive__",
    "withdrawn": "__sensitive__",
}


def _d10(v: str) -> str:
    d = "".join(ch for ch in (v or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else ""


def friendly_stage(claim: dict) -> str:
    """Customer-facing wording for a claim's position. '__sensitive__' means a human must say it."""
    st = (claim.get("status") or "").lower()
    ro = (claim.get("review_outcome") or "").lower()
    if ro == "no_scope":
        return "__sensitive__"
    say = _STAGE_SAY.get(st, "with our team")
    if say == "__sensitive__":
        return "__sensitive__"
    if ro == "can_fight" and st not in ("in_negotiation",):
        return "reviewed — our legal team is taking it forward"
    return say


async def resolve(msisdn: str) -> dict:
    """Identify the person behind this WhatsApp number. Never raises."""
    out = {"role": "unknown", "name": "", "verified": False,
           "account_id": None, "branch_code": "", "staff_id": None, "claim_ids": []}
    d10 = _d10(msisdn)
    if not d10:
        return out
    like = f"%{d10}"
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            # 1) Complainant on a claim (their own number on the case).
            rows = await (await c.execute(
                "SELECT claim_id, complainant_name, insured_name FROM nidaan_claims "
                "WHERE COALESCE(archived,0)=0 AND ("
                "  REPLACE(REPLACE(COALESCE(complainant_phone,''),' ',''),'-','') LIKE ? OR "
                "  REPLACE(REPLACE(COALESCE(insured_phone,''),' ',''),'-','') LIKE ?) "
                "ORDER BY claim_id DESC LIMIT 10", (like, like))).fetchall()
            if rows:
                rs = [dict(r) for r in rows]
                out.update(role="complainant", verified=True,
                           name=(rs[0].get("complainant_name") or rs[0].get("insured_name") or ""),
                           claim_ids=[r["claim_id"] for r in rs])
                return out
            # 2) Subscriber (account holder).
            a = await (await c.execute(
                "SELECT account_id, owner_name FROM nidaan_accounts "
                "WHERE deleted_at IS NULL AND REPLACE(REPLACE(COALESCE(phone,''),' ',''),'-','') LIKE ? "
                "LIMIT 1", (like,))).fetchone()
            if a:
                a = dict(a)
                out.update(role="subscriber", verified=True, name=a.get("owner_name") or "",
                           account_id=a.get("account_id"))
                return out
            # 3) Branch / My-Business partner.
            b = await (await c.execute(
                "SELECT branch_code, name FROM nidaan_branches "
                "WHERE REPLACE(REPLACE(COALESCE(contact_phone,''),' ',''),'-','') LIKE ? LIMIT 1",
                (like,))).fetchone()
            if b:
                b = dict(b)
                out.update(role="branch", verified=True, name=b.get("name") or b.get("branch_code"),
                           branch_code=b.get("branch_code"))
                return out
            # 4) Internal staff — they work from the Telegram office bot, not here.
            s = await (await c.execute(
                "SELECT staff_id, name FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
                "AND REPLACE(REPLACE(COALESCE(phone,''),' ',''),'-','') LIKE ? LIMIT 1", (like,))).fetchone()
            if s:
                s = dict(s)
                out.update(role="staff", verified=True, name=s.get("name") or "",
                           staff_id=s.get("staff_id"))
    except Exception as e:  # noqa: BLE001
        logger.warning("wa identity resolve failed for %s: %s", msisdn, e)
    return out


async def safe_context(identity: dict) -> dict:
    """The support-desk view of this person: {text, handoff_only}.

    `text` is what the assistant may draw on. `handoff_only` means the situation needs a human
    (a decided outcome, a no-scope review) and the bot must not narrate it."""
    role = identity.get("role")
    try:
        if role == "complainant":
            return await _ctx_complainant(identity)
        if role == "subscriber":
            return await _ctx_subscriber(identity)
        if role == "branch":
            return await _ctx_branch(identity)
        if role == "staff":
            return {"text": ("This is one of our own staff members. Tell them warmly that the full "
                             "office — tasks, claims, approvals — runs on the NidaanPartner Telegram "
                             "bot, and to use that instead of WhatsApp."), "handoff_only": False}
    except Exception as e:  # noqa: BLE001
        logger.warning("safe_context failed (%s): %s", role, e)
    return {"text": "", "handoff_only": False}


async def _ctx_complainant(identity: dict) -> dict:
    ids = identity.get("claim_ids") or []
    if not ids:
        return {"text": "", "handoff_only": False}
    q = ",".join("?" * len(ids))
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            f"SELECT claim_id, insured_name, claim_type, status, review_outcome, l2_payment_status, "
            f"payment_status FROM nidaan_claims WHERE claim_id IN ({q})", ids)).fetchall()]
    lines, sensitive = [], False
    for r in rows:
        stage = friendly_stage(r)
        if stage == "__sensitive__":
            sensitive = True
            lines.append(f"- Claim NP-{r['claim_id']:04d} ({r.get('claim_type') or 'claim'} for "
                         f"{r.get('insured_name') or 'the insured'}): there is an important update a "
                         f"team member must explain personally.")
            continue
        pend = await _pending_docs(r["claim_id"], r.get("claim_type") or "")
        need = (f" We are still waiting for {pend} document(s) from them." if pend else
                " All the documents we asked for have been received.")
        lines.append(f"- Claim NP-{r['claim_id']:04d} ({r.get('claim_type') or 'claim'} for "
                     f"{r.get('insured_name') or 'the insured'}): {stage}.{need}")
    return {"text": ("This is a VERIFIED customer of ours. Their case position, in support "
                     "language:\n" + "\n".join(lines)), "handoff_only": sensitive}


async def _pending_docs(claim_id: int, claim_type: str) -> int:
    try:
        import biz_nidaan_doc_checklist as _ck
        return len(await _ck.pending_required_docs(claim_id, claim_type) or [])
    except Exception:
        return 0


async def _ctx_subscriber(identity: dict) -> dict:
    aid = identity.get("account_id")
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        sub = await (await c.execute(
            "SELECT plan, status, substr(current_period_end,1,10) AS period_end FROM nidaan_subscriptions "
            "WHERE account_id=? AND status='active' ORDER BY sub_id DESC LIMIT 1", (aid,))).fetchone()
        claims = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, insured_name, claim_type, status, review_outcome FROM nidaan_claims "
            "WHERE account_id=? AND COALESCE(archived,0)=0 ORDER BY claim_id DESC LIMIT 12",
            (aid,))).fetchall()]
    parts = []
    if sub:
        s = dict(sub)
        parts.append(f"Their plan: {s.get('plan','').title()} — active, valid until {s.get('period_end') or 'the current period end'}.")
    else:
        parts.append("They do not have an active subscription right now.")
    sensitive = False
    if claims:
        parts.append(f"Claims filed under their account ({len(claims)}):")
        for r in claims:
            stage = friendly_stage(r)
            if stage == "__sensitive__":
                sensitive = True
                stage = "has an important update a team member must explain personally"
            parts.append(f"- NP-{r['claim_id']:04d} for {r.get('insured_name') or 'their customer'} "
                         f"({r.get('claim_type') or 'claim'}): {stage}.")
    else:
        parts.append("No claims have been filed under their account yet.")
    return {"text": "This is a VERIFIED subscriber of ours. What they may be told:\n" + "\n".join(parts),
            "handoff_only": sensitive}


async def _ctx_branch(identity: dict) -> dict:
    code = (identity.get("branch_code") or "").upper()
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, insured_name, claim_type, status, review_outcome, payment_status "
            "FROM nidaan_claims WHERE UPPER(COALESCE(branch_code,''))=? AND COALESCE(archived,0)=0 "
            "ORDER BY claim_id DESC LIMIT 15", (code,))).fetchall()]
        signups = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_accounts WHERE UPPER(COALESCE(branch_code,''))=? "
            "AND deleted_at IS NULL", (code,))).fetchone()
    unpaid = sum(1 for r in rows if (r.get("payment_status") or "") == "unpaid_lead")
    parts = [f"This is our VERIFIED partner branch {identity.get('name') or code} (code {code}).",
             f"They have {signups[0] if signups else 0} signup(s) and {len(rows)} active claim(s), "
             f"of which {unpaid} are still unpaid leads."]
    sensitive = False
    for r in rows[:10]:
        stage = friendly_stage(r)
        if stage == "__sensitive__":
            sensitive = True
            stage = "has an important update our team must discuss with them"
        parts.append(f"- NP-{r['claim_id']:04d} {r.get('insured_name') or ''} "
                     f"({r.get('claim_type') or 'claim'}): {stage}.")
    return {"text": "\n".join(parts), "handoff_only": sensitive}
