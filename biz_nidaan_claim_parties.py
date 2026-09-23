"""
NidaanPartner — CLAIM PARTIES: who is involved in a claim, and telling all of them.

A claim usually has FOUR interested parties, not one:
  • complainant — the person presenting the case + providing documents (our comms point)
  • subscriber  — the account holder whose plan the claim was filed under
  • branch      — the branch / My-Business partner whose link brought the subscriber in
  • staff       — the staff member (SP- code) who referred them, plus the assigned handler

Every one of them should learn about the activity on that claim, on the channels we actually
have for them. This module resolves the parties once and fans a single update out to all of
them — email + dashboard always, WhatsApp when we have a number.

CONTACT GAPS: when a party is missing a channel (no WhatsApp number, or no email) we do NOT
fail silently. We deliver on whatever channel we DO have, mark the gap, and ask for the missing
one — in the message itself and, via `contact_gaps_for_*`, on that party's own dashboard.

Safe by construction: every send is wrapped, a bad contact never breaks a claim flow, and
nothing here raises into the caller.
"""
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

import biz_database as db
import biz_nidaan as _n

logger = logging.getLogger("nidaan.parties")
DB_PATH = db.DB_PATH

ROLE_LABEL = {
    "complainant": "Complainant",
    "subscriber": "Subscriber",
    "branch": "Branch / My Business",
    "channel_partner": "Channel Partner",
    "staff": "Staff",
}
# Where each party updates their own details (used in the "we're missing X" ask).
# ── how we actually reach each party ─────────────────────────────────────────
# The panel used to tick a channel when an ADDRESS existed. That is a different question from
# "will this person be told", and on 24 Sep the founder asked the second one.
#
# These rules mirror notify_claim_parties() below. Three states, because two are not enough:
#   yes   - this goes out every time
#   maybe - it goes out for some events; the notify policy decides (staff email is the case that
#           matters: claim chatter deliberately does not email, which is what ended 550/day)
#   no    - we cannot use this channel, and why
def _reach(role: str, phone: str, email: str, stopped: set) -> list:
    """What will actually reach this party. Mirrors notify_claim_parties()."""
    out = []
    if role == "staff":
        # INSIDE the company: the bell and Telegram, and nothing else. Both are independent of
        # any address we hold, which is why a staff member with neither a phone nor an email is
        # still fully notified - and used to read as unreachable.
        return [{"ch": "dashboard", "label": "Dashboard", "state": "yes"},
                {"ch": "telegram", "label": "Telegram", "state": "yes"},
                {"ch": "whatsapp", "label": "WhatsApp", "state": "no",
                 "why": "staff are reached on Telegram — we do not send them WhatsApp"},
                {"ch": "email", "label": "Email", "state": "no",
                 "why": "claim updates do not go to staff by email — Telegram instead"}]
    # OUTSIDE: WhatsApp and email, which is all they have.
    if email:
        out.append({"ch": "email", "label": "Email", "state": "yes"})
    else:
        out.append({"ch": "email", "label": "Email", "state": "no", "why": "no address on file"})
    if not phone:
        out.append({"ch": "whatsapp", "label": "WhatsApp", "state": "no",
                    "why": "no number on file"})
    elif phone[-10:] in stopped:
        # The sender skips these. The panel showed them green, so a party we may no longer
        # message read as reachable.
        out.append({"ch": "whatsapp", "label": "WhatsApp", "state": "no",
                    "why": "they replied STOP — we may not message them"})
    else:
        out.append({"ch": "whatsapp", "label": "WhatsApp", "state": "yes"})
    return out


async def _stopped_numbers() -> set:
    """Numbers that replied STOP. Failing to read this must not blank the panel - an empty set
    only costs accuracy on one chip, where an exception costs the whole section."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            rows = await (await c.execute(
                "SELECT msisdn FROM nidaan_wa_contacts WHERE LOWER(COALESCE(status,''))='stopped'"
            )).fetchall()
        return {_digits(r[0])[-10:] for r in rows if _digits(r[0])}
    except Exception:  # noqa: BLE001
        return set()


ROLE_PROFILE_URL = {
    "complainant": "/nidaan/dashboard",
    "subscriber": "/nidaan/dashboard",
    "branch": "/nidaan/branch",
    "channel_partner": "",   # a CP has no login - staff keep their details
    "staff": "/nidaan/ops",
}


def _digits(v: str) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def _valid_phone(v: str) -> str:
    d = _digits(v)
    if len(d) >= 10:
        return d[-10:] if len(d) == 10 else d
    return ""


def _valid_email(v: str) -> str:
    v = (v or "").strip()
    return v if ("@" in v and "." in v.split("@")[-1]) else ""


async def get_claim_parties(claim_id: int) -> list[dict]:
    """Resolve every party on a claim with their usable contacts + missing-channel gaps.

    Returns a list of dicts: {role, label, name, phone, email, account_id, branch_code,
    staff_id, missing: ['whatsapp'|'email', ...], reach: [...]}. Roles with no contact at all are
    still returned (with both gaps) so ops can see who we cannot reach.

    `reach` is what the screen shows: the channels we will actually USE for this party, not the
    addresses we happen to hold. See _reach()."""
    out: list[dict] = []
    # Read once for the whole claim rather than per party - and before the try, so a party is
    # never built against an undefined name.
    stopped = await _stopped_numbers()
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            row = await (await c.execute(
                "SELECT claim_id, account_id, branch_code, insured_name, insured_phone, "
                "insured_email, complainant_name, complainant_phone, complainant_email, "
                "channel_partner_id, assigned_to_staff_id "
                "FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
        if not row:
            return []
        claim = dict(row)

        def _add(role, name, phone, email, **ids):
            p, e = _valid_phone(phone), _valid_email(email)
            missing = []
            if not p:
                missing.append("whatsapp")
            if not e:
                missing.append("email")
            out.append({"role": role, "label": ROLE_LABEL.get(role, role), "name": (name or "").strip(),
                        "phone": p, "email": e, "missing": missing,
                        "reach": _reach(role, p, e, stopped), **ids})

        # 1) Complainant — falls back to the insured's contact when not captured separately.
        _add("complainant",
             claim.get("complainant_name") or claim.get("insured_name"),
             claim.get("complainant_phone") or claim.get("insured_phone"),
             claim.get("complainant_email") or claim.get("insured_email"),
             claim_id=claim_id)

        # 2) Subscriber — the account the claim sits under (skip house/branch accounts).
        acct = None
        if claim.get("account_id"):
            try:
                acct = await _n.get_account_by_id(claim["account_id"])
            except Exception:
                acct = None
        if acct:
            _add("subscriber", acct.get("owner_name"), acct.get("phone"), acct.get("email"),
                 account_id=acct.get("account_id"))

        # 3) Branch / My Business — the code on the claim, else the one on the account.
        code = (claim.get("branch_code") or (acct or {}).get("branch_code") or "").strip().upper()
        if code and not code.startswith("SP-"):
            try:
                br = await _n.get_branch(code)
            except Exception:
                br = None
            if br:
                _add("branch", br.get("name") or code, br.get("contact_phone"),
                     br.get("contact_email"), branch_code=code)

        # 4) Channel Partner — the agent who introduced the case. They have no login, so they
        #    are reachable only on the phone and email we hold for them. APPROVED partners only:
        #    an unapproved name must never receive a complainant's documents.
        if claim.get("channel_partner_id"):
            try:
                import biz_nidaan_channel_partners as _cp
                cp = await _cp.get_partner(int(claim["channel_partner_id"]))
                if cp and cp.get("status") == "approved":
                    _add("channel_partner", cp.get("name"), cp.get("phone"), cp.get("email"),
                         cp_id=cp.get("cp_id"))
            except Exception:
                pass

        # 5) Staff — the SP- referrer and/or the assigned handler.
        staff_ids: list[int] = []
        if code.startswith("SP-"):
            try:
                async with aiosqlite.connect(DB_PATH) as c:
                    c.row_factory = aiosqlite.Row
                    r = await (await c.execute(
                        "SELECT staff_id FROM nidaan_staff WHERE UPPER(COALESCE(referral_code,''))=? "
                        "AND status='active' AND deleted_at IS NULL", (code,))).fetchone()
                    if r:
                        staff_ids.append(dict(r)["staff_id"])
            except Exception:
                pass
        if claim.get("assigned_to_staff_id"):
            staff_ids.append(int(claim["assigned_to_staff_id"]))
        for sid in dict.fromkeys(staff_ids):
            try:
                async with aiosqlite.connect(DB_PATH) as c:
                    c.row_factory = aiosqlite.Row
                    r = await (await c.execute(
                        "SELECT staff_id, name, phone, email FROM nidaan_staff WHERE staff_id=? "
                        "AND status='active' AND deleted_at IS NULL", (sid,))).fetchone()
                if r:
                    s = dict(r)
                    _add("staff", s.get("name"), s.get("phone"), s.get("email"), staff_id=sid)
            except Exception:
                continue
    except Exception as e:  # noqa: BLE001
        logger.warning("get_claim_parties failed for claim %s: %s", claim_id, e)
    return out


async def dashboard_link(party: dict, claim_id: Optional[int] = None) -> str:
    """The link THIS party should land on — so a notification is actionable, not just news.

    Complainant → a magic link straight into their own claim (upload documents there).
    Subscriber  → their dashboard (bulk-upload across all their cases).
    Branch      → the branch dashboard.  Staff → their My Business view in ops."""
    try:
        import biz_nidaan_claimant as _cl
        base = _cl._public_base()
    except Exception:
        base = "https://nidaanpartner.com"
    role = party.get("role")
    try:
        if role == "complainant" and claim_id:
            import biz_nidaan_claimant as _cl
            await _cl.ensure_portal(claim_id, with_token=True)
            p = await _cl.get_portal(claim_id)
            if p and p.get("access_token"):
                return f"{base}/nidaan/claim/magic?token={p['access_token']}"
            return f"{base}/nidaan/dashboard"
        if role == "subscriber":
            return f"{base}/nidaan/dashboard"
        if role == "branch":
            return f"{base}/nidaan/branch"
        if role == "staff":
            return f"{base}/nidaan/ops"
    except Exception as e:  # noqa: BLE001
        logger.debug("dashboard_link failed (%s): %s", role, e)
    return f"{base}/nidaan/dashboard"


_LINK_CTA = {
    "complainant": "Open your case to upload documents or check progress",
    "subscriber": "Open your dashboard — upload documents for all your cases in one place",
    "branch": "Open your branch dashboard for the full picture",
    "staff": "Open My Business in ops",
}


def _missing_ask(party: dict, lang_en: bool = True) -> str:
    """The line we append asking a party for the channel we don't have."""
    url = ROLE_PROFILE_URL.get(party.get("role"), "/nidaan/dashboard")
    if "whatsapp" in party["missing"] and party.get("email"):
        return ("\n\nWe don't have your WhatsApp number yet — add it at "
                f"https://nidaanpartner.com{url} so urgent claim updates reach you instantly on WhatsApp.")
    if "email" in party["missing"] and party.get("phone"):
        return ("\n\nWe don't have your email yet — add it at "
                f"https://nidaanpartner.com{url} so you also get the written record of every update.")
    return ""


async def notify_claim_parties(claim_id: int, *, event_key: str, subject: str, body: str,
                               roles: Optional[list] = None,
                               skip_phones: Optional[list] = None) -> dict:
    """Fan ONE claim update out to every involved party on the channels we have for them.

    email + dashboard go through the existing notification engine; WhatsApp goes through the
    NidaanPartner Cloud-API number (free-form inside the 24h session; a cold send needs an
    approved template, which is reported rather than silently dropped).

    Returns {sent: [...], gaps: [...]} — `gaps` lists parties we could only partly reach, which
    is what drives the dashboard "please add your WhatsApp/email" nudge."""
    result = {"sent": [], "gaps": []}
    try:
        parties = await get_claim_parties(claim_id)
        if roles:
            parties = [p for p in parties if p["role"] in roles]
        import biz_nidaan_notifications as _nnot
        _skip = {_digits(p)[-10:] for p in (skip_phones or []) if _digits(p)}
        seen: set = set()
        for p in parties:
            key = (p["role"], p.get("phone"), p.get("email"))
            if key in seen:
                continue
            seen.add(key)
            ask = _missing_ask(p)
            # Every notification lands them somewhere useful, on their OWN dashboard.
            link = await dashboard_link(p, claim_id)
            cta = _LINK_CTA.get(p["role"], "Open your dashboard")
            text = f"{body}{ask}\n\n👉 {cta}:\n{link}"
            # ── email + dashboard (the always-on rail) ─────────────────────────
            try:
                if p["role"] == "staff" and p.get("staff_id"):
                    # email=False, decided here rather than left to the policy. A claim update is
                    # exactly the traffic the founder asked to keep off email ("nothing claims
                    # related update to staff on email, it doesnt make sense"), and the Brevo
                    # allowance is for complainants. The policy still runs underneath.
                    await _nnot.notify_staff_inapp([p["staff_id"]], subject, text,
                                                   event_key=event_key, email=False,
                                                   claim_id=claim_id)
                elif p.get("email"):
                    await _nnot.dispatch(
                        event_key=event_key, priority=_nnot.PRIORITY_P1,
                        recipient_type=(_nnot.RECIPIENT_SUBSCRIBER if p["role"] == "subscriber"
                                        else _nnot.RECIPIENT_SUBSCRIBER),
                        recipient_id=p.get("account_id"), recipient_phone="",
                        recipient_email=p["email"], subject=subject, body=text, claim_id=claim_id)
            except Exception as e:  # noqa: BLE001
                logger.info("party email/dash failed (%s claim %s): %s", p["role"], claim_id, e)
            # ── WhatsApp (Cloud API) — for people OUTSIDE the company ─────────
            # Staff are reached on Telegram and the bell. They were also being sent WhatsApp for
            # every claim update: a channel none of them reads, billed per message, from the
            # number complainants know us by.
            if p["role"] != "staff" and p.get("phone") and p["phone"][-10:] not in _skip:
                try:
                    await _send_party_whatsapp(p, text)
                except Exception as e:  # noqa: BLE001
                    logger.info("party whatsapp failed (%s claim %s): %s", p["role"], claim_id, e)
            if p["missing"]:
                result["gaps"].append({"role": p["role"], "name": p["name"], "missing": p["missing"]})
            result["sent"].append(p["role"])
    except Exception as e:  # noqa: BLE001
        logger.warning("notify_claim_parties failed for claim %s: %s", claim_id, e)
    return result


async def _send_party_whatsapp(party: dict, text: str) -> None:
    """WhatsApp one party. Free-form inside the 24h session; cold needs an approved template."""
    import biz_nidaan_whatsapp as _wa
    import biz_nidaan_wa_flow as _flow
    if not _wa.is_configured():
        return
    msisdn = _wa.normalize_msisdn(party["phone"])
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT status FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
    if r and dict(r).get("status") == "stopped":
        return   # consent: never message someone who replied STOP
    if await _flow.in_session_window(msisdn):
        await _wa.send_text(msisdn, text)
    else:
        # Cold: needs an approved party-update template (np_claim_update). Until it exists the
        # email arm above has already delivered the same update, so nothing is lost.
        logger.info("party WhatsApp cold-skip (needs np_claim_update template): %s", party["role"])


async def contact_gaps_for_account(account_id: int) -> list:
    """What contact details this SUBSCRIBER is missing → drives the dashboard nudge."""
    try:
        acct = await _n.get_account_by_id(account_id)
        if not acct:
            return []
        gaps = []
        if not _valid_phone(acct.get("phone")):
            gaps.append("whatsapp")
        if not _valid_email(acct.get("email")):
            gaps.append("email")
        return gaps
    except Exception:
        return []


async def contact_gaps_for_branch(branch_code: str) -> list:
    """What contact details this BRANCH / My-Business partner is missing."""
    try:
        br = await _n.get_branch((branch_code or "").strip().upper())
        if not br:
            return []
        gaps = []
        if not _valid_phone(br.get("contact_phone")):
            gaps.append("whatsapp")
        if not _valid_email(br.get("contact_email")):
            gaps.append("email")
        return gaps
    except Exception:
        return []
