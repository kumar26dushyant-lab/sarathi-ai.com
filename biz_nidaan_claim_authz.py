# -*- coding: utf-8 -*-
"""May this STAFF MEMBER touch this claim? One answer, in one place.

NAMED authz, NOT access, and the distinction cost two days of a broken portal. On 26 Sep this
module was written as biz_nidaan_claim_access.py - a name already taken by the module that
verifies a COMPLAINANT by sending a code to the number on their claim. It did not shadow that
module; it replaced it, and every claimant who opened their link was told "this link is invalid
or has expired" until 28 Sep. Two questions that sound alike:

    biz_nidaan_claim_access   IS THIS THE COMPLAINANT?  - a code to the phone/email on the claim
    biz_nidaan_claim_authz    MAY THIS STAFFER SEE IT?  - assigned, mentioned, or an admin

Same claim, opposite sides of the counter. Keep them apart.

Founder, 26 Sep 2026, on letting staff attach documents to a claim from Telegram:
  *"we need to make bot highly secure from cybersecurity point of view"*
and, standing:
  *"whatever we are fixing, building, changing ... make foundation strong for app to work
  flawlessly without bugs, without data loss, without security issues."*

Until now nothing in this codebase answered that question. The web screens and the bot each
decided for themselves, by role, and a claim id was never checked against the person holding it.
That was survivable while every route into a claim was a browser someone had signed into. It
stops being survivable the moment a claim can be reached from a chat app on a phone that may be
borrowed, shared or lost, and a document can be attached to a real case by typing a number.

THE RULE, decided with the founder on 26 Sep:
  - a **team member** reaches only the claims they are on - assigned to it, or named in a note
    on it. Someone else's claim answers "that claim is not yours", and answers it the same way
    whether the claim exists or not, so the bot cannot be used to find out which numbers are real.
  - an **admin or super admin** reaches any claim, exactly as they already do on the web. This
    module does not quietly narrow that: an authorisation rule that disagrees with itself
    depending on the door you came through is worse than a permissive one, because nobody can
    say what it does. If that should tighten, it tightens here, once, for every caller.

AND IT FAILS CLOSED. If the claim cannot be read, if the tables will not answer, if anything at
all is unexpected - the answer is no. That is the opposite of biz_nidaan_notify_prefs, which
fails towards *sending*, and the difference is deliberate: the worst case of a wrong "yes" here
is a stranger's medical records; the worst case there is a noisy phone.
"""
from __future__ import annotations

import logging

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.claim.authz")

# Roles that reach every claim, as they already do on every web screen.
ORG_WIDE_ROLES = ("super_admin", "sub_super_admin")

# Why access was granted or refused. Returned so a caller can log it and a screen can explain it.
BASIS_ROLE = "role"            # an admin, org-wide
BASIS_ASSIGNED = "assigned"    # explicitly put on this claim
BASIS_MENTIONED = "mentioned"  # named in a note on this claim
BASIS_NONE = "not_on_claim"
BASIS_NO_CLAIM = "no_such_claim"
BASIS_ERROR = "unreadable"


def _db() -> str:
    """Asked for at the moment it is needed, never remembered from import time - tests and the
    journey runner repoint `db.DB_PATH` after this module is already imported."""
    return db.DB_PATH


async def claim_access(staff_id: int | None, claim_id: int | None, *,
                       role: str = "") -> dict:
    """Return {allowed, basis, reason} for this person against this claim.

    `reason` is written to be shown to the person, and deliberately says the same thing for
    "not your claim" and "no such claim": otherwise the difference between the two answers is a
    way to enumerate which claim numbers exist.
    """
    deny = {"allowed": False, "basis": BASIS_NONE,
            "reason": "That claim is not one of yours."}

    try:
        sid = int(staff_id or 0)
        cid = int(claim_id or 0)
    except (TypeError, ValueError):
        return deny
    if sid <= 0 or cid <= 0:
        return deny

    if (role or "") in ORG_WIDE_ROLES:
        # Still confirm the claim exists, so an admin gets "no such claim" rather than a flow
        # that carries on against nothing.
        try:
            async with aiosqlite.connect(_db()) as c:
                row = await (await c.execute(
                    "SELECT 1 FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone()
        except Exception as e:  # noqa: BLE001
            logger.warning("claim access unreadable for claim %s: %s", cid, e)
            return {"allowed": False, "basis": BASIS_ERROR,
                    "reason": "Could not check that claim just now. Try again."}
        if not row:
            return {"allowed": False, "basis": BASIS_NO_CLAIM,
                    "reason": "No claim with that number."}
        return {"allowed": True, "basis": BASIS_ROLE,
                "reason": "Allowed: you are an admin."}

    try:
        async with aiosqlite.connect(_db()) as c:
            row = await (await c.execute(
                "SELECT 1 FROM nidaan_claim_assignees WHERE claim_id=? AND staff_id=?",
                (cid, sid))).fetchone()
            if row:
                return {"allowed": True, "basis": BASIS_ASSIGNED,
                        "reason": "Allowed: this claim is assigned to you."}
            row = await (await c.execute(
                "SELECT 1 FROM nidaan_claim_note_mentions "
                "WHERE claim_id=? AND staff_id=? LIMIT 1",
                (cid, sid))).fetchone()
            if row:
                return {"allowed": True, "basis": BASIS_MENTIONED,
                        "reason": "Allowed: you were named on this claim."}
    except Exception as e:  # noqa: BLE001
        # FAIL CLOSED. See the module note - a wrong yes here is somebody else's medical file.
        logger.warning("claim access unreadable for staff %s claim %s: %s", sid, cid, e)
        return {"allowed": False, "basis": BASIS_ERROR,
                "reason": "Could not check that claim just now. Try again."}

    return deny


async def assert_claim_access(staff: dict | None, claim_id: int | None) -> dict:
    """Convenience for callers that hold a staff row: same answer, one argument."""
    staff = staff or {}
    return await claim_access(staff.get("staff_id"), claim_id,
                              role=(staff.get("role") or ""))


async def my_claim_ids(staff_id: int, *, limit: int = 200) -> list[int]:
    """The claims a team member is on - for showing someone their own list rather than making
    them remember numbers. Admins are not served from here; they have the search screens."""
    try:
        async with aiosqlite.connect(_db()) as c:
            rows = await (await c.execute(
                "SELECT claim_id FROM nidaan_claim_assignees WHERE staff_id=? "
                "ORDER BY assigned_at DESC LIMIT ?", (int(staff_id), int(limit)))).fetchall()
            return [r[0] for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("could not list claims for staff %s: %s", staff_id, e)
        return []
