# -*- coding: utf-8 -*-
"""Sending a claim document from Telegram: look before you save.

Founder, 26 Sep 2026:
  *"if any staff wants to upload documents via telegram bot, they can do it from that bot itself
  they only need to mention correct claim number and upload document, our bot should validate for
  correct document and nudge staff for any incorrect, duplicate, or degrade quality doc/images,
  and take confirmation to save sharing the current claim document status (if already uploaded
  docs to avoid duplication and confusion)"*

THIS IS A SECOND DOOR ONTO AN EXISTING PIPELINE, NOT A SECOND PIPELINE. Everything that decides
what may be stored already exists in biz_nidaan_doc_intake.accept(): the virus scan (fail-closed),
the PDF normalisation, the checklist matching, the ticking off. A file arriving from Telegram goes
through exactly that, with source="telegram". Writing a second intake here is how the two quietly
start disagreeing about what is acceptable - and the one nobody is looking at is the one that
lets something through.

WHAT IS NEW is the step before it. The founder asked for a look before the save, and that is not
politeness - it is the whole point:

    download -> size gate -> normalise -> ASK WHAT IT IS -> show the claim's current state
             -> "you may already have this one" -> wait for a yes -> then, and only then, store

So the file is held, not stored, while the person decides. It is held in the doc-splitter's
existing temp-job store rather than a new one, and the claim id is re-authorised at the moment of
the save as well as at the moment of the ask - because between those two moments a staff member
can be unassigned, archived, or deleted, and the first check would be a memory of permission
rather than permission.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("nidaan.bot.docs")

# How sure the matcher has to be before we tell somebody "this is your discharge summary".
# Below this we say what it looks like and let the person decide, rather than asserting.
CONFIDENT = 0.70


async def claim_doc_status(claim_id: int, *, lang: str = "en") -> dict:
    """What this claim already has and still needs. {ok, claim, received:[], pending:[], text}

    Shown BEFORE anything is stored, which is the founder's "avoid duplication and confusion":
    most duplicates are not carelessness, they are somebody who cannot see what is already there.
    """
    import biz_nidaan as nidaan
    import biz_nidaan_doc_checklist as ck
    out = {"ok": False, "received": [], "pending": [], "text": "", "claim": None}
    try:
        claim = await nidaan.get_claim_with_account(claim_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("claim %s unreadable for doc status: %s", claim_id, e)
        claim = None
    if not claim:
        out["text"] = "No claim with that number."
        return out
    out["claim"] = claim
    try:
        docs = await ck.effective_docs(claim_id, claim.get("claim_type") or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("checklist unreadable for claim %s: %s", claim_id, e)
        out["text"] = "Could not read this claim's document list just now."
        return out

    for d in docs:
        row = d.get("row") or {}
        label = (d.get("hi") if lang == "hi" else d.get("en")) or d.get("key")
        (out["received"] if row.get("received") else out["pending"]).append(
            {"key": d["key"], "label": label, "required": bool(d.get("required"))})

    lines = ["\U0001f4cb *Claim #%s* — %s" % (claim_id, (claim.get("insured_name") or "")[:40])]
    if out["received"]:
        lines.append("\n✅ *Already with us (%d)*" % len(out["received"]))
        lines += ["   • " + d["label"] for d in out["received"][:12]]
        if len(out["received"]) > 12:
            lines.append("   …and %d more" % (len(out["received"]) - 12))
    else:
        lines.append("\n✅ Nothing received yet.")
    need = [d for d in out["pending"] if d["required"]]
    if need:
        lines.append("\n⏳ *Still needed (%d)*" % len(need))
        lines += ["   • " + d["label"] for d in need[:12]]
        if len(need) > 12:
            lines.append("   …and %d more" % (len(need) - 12))
    else:
        lines.append("\n⏳ Nothing outstanding.")
    out["text"] = "\n".join(lines)
    out["ok"] = True
    return out


async def inspect(claim_id: int, filename: str, data: bytes, *, lang: str = "en") -> dict:
    """Work out what this file is WITHOUT storing it. {ok, job, looks_like, key, label,
    confidence, legible, duplicate, warnings:[], text}

    Nothing here writes to the claim. The bytes go to the temp job store so the person can be
    asked first, and `job` is the handle that the confirm step turns into a real document.
    """
    import biz_doc_splitter as splitter
    import biz_nidaan as nidaan
    import biz_nidaan_doc_checklist as ck
    import biz_nidaan_doc_intake as intake

    out = {"ok": False, "job": "", "looks_like": "", "key": "", "label": "",
           "confidence": 0.0, "legible": True, "duplicate": None, "warnings": [], "text": ""}

    try:
        pdf, pages, notes = splitter.normalize_to_pdf([(filename, data)])
    except Exception as e:  # noqa: BLE001
        logger.info("could not read %s for claim %s: %s", (filename or "?")[:60], claim_id, e)
        out["text"] = ("Could not open that file. Please send it as a PDF or a clear photo.")
        return out
    if not pdf:
        out["text"] = "Could not open that file. Please send it as a PDF or a clear photo."
        return out

    claim = await nidaan.get_claim_with_account(claim_id)
    docs = await ck.effective_docs(claim_id, (claim or {}).get("claim_type") or "")
    received = {d["key"]: d for d in docs if (d.get("row") or {}).get("received")}
    candidates = [{"key": d["key"], "en": d.get("en") or d["key"]} for d in docs]

    try:
        m = await intake.match_document(pdf, candidates)
    except Exception as e:  # noqa: BLE001
        # The matcher failing must not block a real document. It fails OPEN as "unknown", and
        # the person is asked rather than refused - staff know what they are sending.
        logger.info("match failed for claim %s: %s", claim_id, e)
        m = {"key": "", "label": "", "confidence": 0.0, "looks_like": "", "legible": True}

    out["key"] = m.get("key") or ""
    out["confidence"] = float(m.get("confidence") or 0)
    out["looks_like"] = (m.get("looks_like") or "").strip()
    out["legible"] = bool(m.get("legible", True))
    lbl = ""
    if out["key"]:
        d = next((x for x in docs if x["key"] == out["key"]), None)
        if d:
            lbl = (d.get("hi") if lang == "hi" else d.get("en")) or out["key"]
    out["label"] = lbl

    # The three nudges the founder asked for, in his order.
    if out["key"] and out["key"] in received:
        out["duplicate"] = {"key": out["key"], "label": lbl}
        out["warnings"].append(
            "⚠️ *You may already have this one.* “%s” is already marked "
            "received on this claim." % lbl)
    if not out["legible"]:
        out["warnings"].append(
            "⚠️ *This looks hard to read.* If it is blurred or cut off, a clearer "
            "photo now saves a re-request later.")
    if not out["key"]:
        out["warnings"].append(
            "⚠️ *I could not match this to anything on the list.* It will be saved "
            "against the claim for a person to sort."
            + (" It looks like: %s." % out["looks_like"] if out["looks_like"] else ""))

    out["job"] = splitter.save_job(pdf)
    head = ("\U0001f4c4 *%s*" % lbl) if (lbl and out["confidence"] >= CONFIDENT) else (
        "\U0001f4c4 *Not sure what this is*" if not out["key"] else "\U0001f4c4 *Looks like: %s*" % lbl)
    parts = [head, "%d page(s)." % (pages or 1)]
    if notes:
        parts.append(" ".join(str(n) for n in notes[:2]))
    if out["warnings"]:
        parts.append("\n" + "\n".join(out["warnings"]))
    out["text"] = "\n".join(parts)
    out["ok"] = True
    return out


async def commit(staff: dict, claim_id: int, job: str) -> dict:
    """Store the held file against the claim, through the one intake everything else uses.

    The claim is RE-AUTHORISED here, not trusted from the inspect step. Between the two, a
    person can be unassigned from the claim, archived or deleted - and a check done a minute ago
    is a memory of permission, not permission.
    """
    # Authorisation FIRST, before anything heavy is even imported. Refusing somebody who is not
    # on this claim must not depend on a PDF library being importable - otherwise the refusal
    # path is only as reliable as an unrelated dependency, and the cheapest answer (no) becomes
    # the one most likely to fail.
    import biz_nidaan_bot_guard as guard
    import biz_nidaan_claim_authz as access

    ok = await access.assert_claim_access(staff, claim_id)
    if not ok["allowed"]:
        await guard.record(staff, "upload", claim_id=claim_id, allowed=False,
                           detail="refused at save: %s" % ok["basis"])
        return {"ok": False, "text": ok["reason"]}

    import biz_doc_splitter as splitter
    import biz_nidaan as nidaan
    import biz_nidaan_doc_intake as intake

    pdf = splitter.load_job(job or "")
    if not pdf:
        return {"ok": False,
                "text": "That upload has expired. Please send the document again."}

    claim = await nidaan.get_claim_with_account(claim_id)
    if not claim:
        return {"ok": False, "text": "No claim with that number."}

    res = await intake.accept(
        claim_id, claim.get("account_id"),
        [("telegram-upload.pdf", pdf)],
        claim_type=claim.get("claim_type") or "", source="telegram")

    stored = int(res.get("stored") or 0)
    ticked = res.get("ticked") or []
    rejected = res.get("rejected") or []
    await guard.record(staff, "upload", claim_id=claim_id, allowed=True,
                       detail="stored=%d ticked=%s rejected=%d"
                              % (stored, ",".join(t.get("key", "") for t in ticked) or "-",
                                 len(rejected)))
    if rejected:
        # accept() refuses fail-closed, e.g. the virus scanner would not give a verdict. Never
        # blame the person for our refusal.
        return {"ok": False,
                "text": ("That file could not be accepted. It has been reported — please "
                         "upload it on the portal, or ask an admin.")}
    if not stored:
        return {"ok": False, "text": "Nothing was saved. Please try sending it again."}

    lines = ["✅ *Saved to claim #%s.*" % claim_id]
    if ticked:
        lines.append("Ticked off: " + ", ".join((t.get("label") or t.get("key") or "")
                                                for t in ticked))
    pend = [p for p in (res.get("pending") or []) if p.get("required")]
    if pend:
        lines.append("\n⏳ Still needed: %d" % len(pend))
    return {"ok": True, "text": "\n".join(lines), "result": res}
