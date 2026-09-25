# -*- coding: utf-8 -*-
"""What the WhatsApp bot may say, and how much anyone may throw at it.

The founder's charter, 23–25 Sep 2026, in his own words:

  * *"only verified phone numbers of complainant should be provided claim/case related info and
    communication and only restricted to document collection if anything is pending, but we
    should not provide info when it moves to consolidation"*
  * *"after consolidation we also have questions/queries and it can be to complianant so those
    communication should not be restricted"*
  * *"if complianant or any other involved party ... anyone ask claim related details we should
    not be sharing, only if our team initiate discussion for details and talk then should be
    getting response but should not be providing details"*
  * *"if human is handling then everything should normal and leave it to human"*
  * *"for bot we need to be very careful what info is going out, how scammers, fraudsters can be
    deal with, anomalies detection unnecessary attachment bombardment, bot attack, etc. needs to
    be very strong as foundation"*

TWO QUESTIONS, ANSWERED IN ONE PLACE
  1. `stance()`  — what may this conversation receive right now?
  2. `flood()`   — is this number behaving like a person, or like an attack?

Both live here rather than scattered through the orchestrator, because a rule that exists in
three places is a rule that will disagree with itself. The orchestrator asks; this decides.

WHAT THIS DELIBERATELY DOES NOT DO
  It never decides whether somebody is verified — that is biz_nidaan_wa_auth, on a code we email
  to the address already on the account. This module takes verification as an input and decides
  what a verified person may hear, which is a different and smaller question.

  It also never gags a HUMAN. Every rule here binds the bot. When a staff member has taken the
  conversation the orchestrator has already returned long before anything here is consulted.

FAIL CLOSED. Every unknown — a claim that cannot be read, a database that will not answer, a
stage nobody recognised — resolves to the most restrictive stance. A bot that says nothing costs
one handoff; a bot that says the wrong thing about somebody's medical claim cannot be undone.
"""
from __future__ import annotations

import logging

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.wa.charter")

DB_PATH = db.DB_PATH

# ── what the bot may do, most open first ─────────────────────────────────────
# DOCS       guided document collection. The claim still needs papers, so asking for the next one
#            and accepting it is the whole conversation.
# ANSWER_ASK the claim has moved past collection, but WE asked them something and are waiting.
#            Their answer is welcome. Nothing about the claim's state goes back.
# QUIET      acknowledge, and put a person on it. No claim detail at all.
STANCE_DOCS = "docs"
STANCE_ANSWER_ASK = "answer_ask"
STANCE_QUIET = "quiet"

# How much traffic from one number stops looking like a person.
#
# Set from what real document collection looks like rather than from a round number: a
# complainant sending a rejection letter, two bills and a discharge summary, with a sentence
# between each, is perhaps a dozen messages in a busy ten minutes. Past that it is a script, a
# stuck client resending, or somebody having a go at us.
FLOOD_MSGS_PER_10MIN = 20
FLOOD_MSGS_PER_HOUR = 60
# Attachments are the expensive kind of flood: each one is stored, virus-scanned and read by a
# model. A real claim has perhaps twenty papers across its whole life.
FLOOD_MEDIA_PER_HOUR = 25
FLOOD_MEDIA_PER_DAY = 60


async def _one(sql: str, params: tuple, default=0):
    """A single scalar, or `default` if the database will not answer.

    Deliberately swallowing: a counting query that fails must not take the conversation down with
    it. The caller treats `default` as the safe direction for its own question.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            row = await (await c.execute(sql, params)).fetchone()
        return (row[0] if row and row[0] is not None else default)
    except Exception as e:  # noqa: BLE001
        logger.warning("charter count failed (%s): %s", sql.split()[3] if len(sql.split()) > 3 else "?", e)
        return default


async def stance(claim_id: int | None, *, verified: bool) -> dict:
    """What may this conversation receive right now?

    Returns {stance, reason, may_send_docs, may_reveal_detail}. `may_reveal_detail` is always
    False: no stance in this charter lets the bot narrate a claim's state. It is returned
    explicitly so a future caller has to decide to ignore it rather than forget it exists.
    """
    base = {"may_reveal_detail": False}

    # An unverified number is a stranger, whatever our records say about it. Numbers are recycled
    # and phones are shared, and what sits behind a match is somebody else's medical claim.
    if not verified:
        return dict(base, stance=STANCE_QUIET, may_send_docs=False,
                    reason="not verified — a matching number is a candidate, not a person")

    if not claim_id:
        return dict(base, stance=STANCE_QUIET, may_send_docs=False,
                    reason="verified, but this number is not on a claim")

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            row = await (await c.execute(
                "SELECT claim_id, COALESCE(pipeline_stage,'') stage, COALESCE(status,'') status, "
                "COALESCE(claim_type,'') claim_type, cq_at, cq_reply_at "
                "FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
            if not row:
                return dict(base, stance=STANCE_QUIET, may_send_docs=False,
                            reason="claim not found")
            claim = dict(row)
        # ASKED, not re-derived. pending_required_docs() is the single source the pay-gate and
        # the document asks already use, and it knows things a COUNT(*) here would not: what the
        # template requires, what a reviewer added or removed, what is merely conditional.
        # Counting rows myself would have been a second definition of "still needed", drifting
        # from the first the next time somebody edits a checklist.
        import biz_nidaan_doc_checklist as _dc
        pending = len(await _dc.pending_required_docs(int(claim_id), claim["claim_type"]))
    except Exception as e:  # noqa: BLE001
        # FAIL CLOSED. Not knowing the stage is not permission to talk about the claim.
        logger.warning("charter could not read claim %s (%s) — staying quiet", claim_id, e)
        return dict(base, stance=STANCE_QUIET, may_send_docs=False,
                    reason="could not read the claim")

    # Are we waiting on an answer we asked for? That is the one thing the founder carved out:
    # "after consolidation we also have questions/queries ... those communication should not be
    # restricted". WE started it, so their reply is expected and welcome.
    waiting_on_them = bool(claim.get("cq_at")) and not claim.get("cq_reply_at")

    # PAST COLLECTION. Once a claim is in the Level-2 line the bot stops being a document
    # collector, and nothing about the claim goes out over WhatsApp.
    if claim["stage"]:
        if waiting_on_them:
            return dict(base, stance=STANCE_ANSWER_ASK, may_send_docs=True,
                        reason="in Level-2, and we asked them something")
        return dict(base, stance=STANCE_QUIET, may_send_docs=False,
                    reason="in Level-2 — a person handles this claim now")

    # STILL COLLECTING.
    if pending:
        return dict(base, stance=STANCE_DOCS, may_send_docs=True,
                    reason="%d document(s) still needed" % pending)
    if waiting_on_them:
        return dict(base, stance=STANCE_ANSWER_ASK, may_send_docs=True,
                    reason="we asked them something")
    return dict(base, stance=STANCE_QUIET, may_send_docs=False,
                reason="nothing outstanding from them")


async def flood(msisdn: str, *, is_media: bool = False) -> dict:
    """Is this number behaving like a person?

    Returns {ok, reason, counts}. `ok=False` means stop replying — not stop RECEIVING. Anything
    they send is still logged and still reaches the staff who need to see it; what stops is the
    bot answering, because an automatic reply is exactly what makes flooding worth doing.

    Fails OPEN, unlike stance(): if the counts cannot be read, a real complainant sending their
    documents must not be stonewalled by a database hiccup. The cost of being wrong here is some
    wasted replies; the cost of being wrong in stance() is a leak.
    """
    d10 = "".join(ch for ch in (msisdn or "") if ch.isdigit())[-10:]
    if not d10:
        return {"ok": True, "reason": "", "counts": {}}

    like = "%" + d10
    ten = await _one(
        "SELECT COUNT(*) FROM nidaan_wa_messages WHERE direction='in' AND msisdn LIKE ? "
        "AND created_at > datetime('now','-10 minutes')", (like,))
    hour = await _one(
        "SELECT COUNT(*) FROM nidaan_wa_messages WHERE direction='in' AND msisdn LIKE ? "
        "AND created_at > datetime('now','-1 hour')", (like,))
    counts = {"ten_min": ten, "hour": hour}

    if is_media:
        # `msg_type` is whatever WhatsApp called it; anything not plain text carries a file.
        counts["media_hour"] = await _one(
            "SELECT COUNT(*) FROM nidaan_wa_messages WHERE direction='in' AND msisdn LIKE ? "
            "AND COALESCE(msg_type,'text') <> 'text' AND created_at > datetime('now','-1 hour')",
            (like,))
        counts["media_day"] = await _one(
            "SELECT COUNT(*) FROM nidaan_wa_messages WHERE direction='in' AND msisdn LIKE ? "
            "AND COALESCE(msg_type,'text') <> 'text' AND created_at > datetime('now','-1 day')",
            (like,))
        if counts["media_hour"] > FLOOD_MEDIA_PER_HOUR:
            return {"ok": False, "counts": counts,
                    "reason": "%d attachments in an hour" % counts["media_hour"]}
        if counts["media_day"] > FLOOD_MEDIA_PER_DAY:
            return {"ok": False, "counts": counts,
                    "reason": "%d attachments in a day" % counts["media_day"]}

    if ten > FLOOD_MSGS_PER_10MIN:
        return {"ok": False, "counts": counts, "reason": "%d messages in ten minutes" % ten}
    if hour > FLOOD_MSGS_PER_HOUR:
        return {"ok": False, "counts": counts, "reason": "%d messages in an hour" % hour}
    return {"ok": True, "reason": "", "counts": counts}
