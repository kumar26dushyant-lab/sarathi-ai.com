# -*- coding: utf-8 -*-
'''Sending a claim document from Telegram: look before you save.

Founder, 26 Sep 2026: the bot should take a claim number and a document, *"validate for correct
document and nudge staff for any incorrect, duplicate, or degrade quality doc/images, and take
confirmation to save sharing the current claim document status (if already uploaded docs to avoid
duplication and confusion)"*.

Two properties carry the whole design, and both are the kind that read fine and behave wrongly:

1. NOTHING IS STORED UNTIL SOMEBODY SAYS YES. inspect() looks, warns and holds; commit() writes.
   If inspect ever reached the intake, the confirmation step would be decoration.

2. THE CLAIM IS RE-AUTHORISED AT THE SAVE, not trusted from the look. Between the two moments a
   person can be unassigned, archived or deleted - and a check done a minute ago is a memory of
   permission, not permission. This is the one a reviewer nods at and never tests, so it is
   tested here by taking the access away between the two calls.

    py -3.14 _tools/test_bot_docs.py
'''
import asyncio
import io
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import biz_nidaan_bot_docs as bd     # noqa: E402
import biz_nidaan_claim_access as access  # noqa: E402

FAILED = 0
CLAIM = 700
ME = {"staff_id": 21, "name": "Field Staffer", "role": "team_member"}


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def main():
    print("\nLook before you save\n")

    src = io.open(os.path.join(ROOT, "biz_nidaan_bot_docs.py"), encoding="utf-8").read()

    # ── 1. it is a door onto the existing pipeline, not a second one ────────
    check("it stores through the ONE intake everything else uses",
          "intake.accept(" in src)
    check("...marked as coming from telegram, so the source is never guessed",
          'source="telegram"' in src)
    check("...and it does NOT reimplement storing, scanning or ticking",
          "_store(" not in src and "scan_bytes" not in src
          and "mark_doc_received" not in src)

    # ── 2. nothing is written by the looking step ───────────────────────────
    i_start = src.index("async def inspect(")
    i_body = src[i_start:src.index("async def commit(")]
    check("the LOOK step never calls the intake", "intake.accept(" not in i_body)
    check("...it only asks what the file is", "match_document(" in i_body)
    check("...and holds the bytes instead of storing them", "save_job(" in i_body)
    c_body = src[src.index("async def commit("):]
    check("the SAVE step is the only one that stores", "intake.accept(" in c_body)

    # ── 3. the three nudges he asked for, by name ───────────────────────────
    check("it nudges on a DUPLICATE", "already have this one" in i_body)
    check("it nudges on POOR QUALITY", "hard to read" in i_body and "legible" in i_body)
    check("it nudges when it CANNOT MATCH the document",
          "could not match this" in i_body)
    check("...and an unmatched file is still kept for a person, not thrown away",
          "for a person to sort" in i_body)

    # ── 4. the claim's current state is shown before any of it ──────────────
    s_body = src[src.index("async def claim_doc_status("):i_start]
    check("the status step lists what is already received", '"received"' in s_body)
    check("...and what is still needed", '"pending"' in s_body)
    check("...reading the same checklist the dashboard reads",
          "effective_docs(" in s_body)

    # ── 5. re-authorisation at the save. The one that matters most. ─────────
    check("commit() re-checks access at the moment of saving",
          "assert_claim_access(" in c_body)
    check("...and records the refusal", "allowed=False" in c_body)

    calls = {"n": 0}
    real = access.assert_claim_access

    async def revoked(staff, claim_id):
        calls["n"] += 1
        return {"allowed": False, "basis": access.BASIS_NONE,
                "reason": "That claim is not one of yours."}

    access.assert_claim_access = revoked
    try:
        r = await bd.commit(ME, CLAIM, "some-job-handle")
    finally:
        access.assert_claim_access = real
    check("a person unassigned between the look and the save cannot save",
          not r["ok"] and "not one of yours" in r["text"], r)
    check("...and access really was consulted at that moment", calls["n"] == 1, calls)

    # ── 6. an expired hold fails safely ─────────────────────────────────────
    async def allowed(staff, claim_id):
        return {"allowed": True, "basis": access.BASIS_ASSIGNED, "reason": "ok"}

    access.assert_claim_access = allowed
    try:
        r = await bd.commit(ME, CLAIM, "no-such-job-handle")
    finally:
        access.assert_claim_access = real
    check("an expired or unknown hold saves nothing", not r["ok"], r)
    check("...and says so in words a person can act on",
          "send the document again" in r["text"], r["text"])

    # ── 7. a refusal from the intake never blames the person ────────────────
    check("a refused file is reported without blaming whoever sent it",
          "reported" in c_body and "blame the person" in c_body)

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "it looks, it warns, it waits - and it re-asks who you are before it writes"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
