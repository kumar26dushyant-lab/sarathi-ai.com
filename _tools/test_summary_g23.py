# -*- coding: utf-8 -*-
'''The 8 pm summary, 2 Oct (founder):
  G2 - the voice note reads the WHOLE summary (it stopped at ~48 s: a short separate script, cut
       at 1,500 characters) and long text goes out in several messages, never cut;
  G3 - a save that changed nothing is not work; blockers on our side are listed with who owns
       each - NOBODY first; "worth a look" flags counts that grew without a claim moving, never
       for super-admins and never on test claims.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_summary_g23.py
'''
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import biz_tts                          # noqa: E402
import biz_nidaan_daily_summary as ds   # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    # ── G2: the whole text, split - never cut ──
    long_text = "\n".join("• NP-%d: Live Cases → Pending Draft · documents uploaded 3 · gist written" % i
                          for i in range(300))
    parts = ds._split_message(long_text)
    check("a long summary goes out as several messages, each under Telegram's limit",
          len(parts) > 1 and all(len(p) <= 3900 for p in parts), [len(p) for p in parts])
    check("...and not one line is lost", "\n".join(parts) == long_text)

    pieces = biz_tts._chunks(long_text)
    check("the voice reads it in pieces of at most 1,200 characters", all(len(p) <= 1200 for p in pieces),
          max(len(p) for p in pieces))
    check("...covering every line", sum(p.count("NP-") for p in pieces) == 300)

    calls = []

    async def fake(text, voice="Kore", model=""):
        calls.append(text)
        return biz_tts._pcm_to_wav(b"\x01\x00" * 100)
    real = biz_tts.cached_wav
    biz_tts.cached_wav = fake
    try:
        wav = await biz_tts.long_wav(long_text)
        check("every piece is spoken and joined into ONE recording",
              wav and len(wav) == 44 + 200 * len(pieces) and len(calls) == len(pieces), (len(wav or b""), len(calls)))

        async def flaky(text, voice="Kore", model=""):
            return None if "NP-150" in text else biz_tts._pcm_to_wav(b"\x01\x00" * 10)
        biz_tts.cached_wav = flaky
        check("if a piece cannot be spoken, there is no half voice note", await biz_tts.long_wav(long_text) is None)
    finally:
        biz_tts.cached_wav = real

    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "biz_nidaan_daily_summary.py"), encoding="utf-8").read()
    check("the voice note is the message itself (not a short separate script)",
          '"kind": "team", "text": text, "voice": text' in src and '"voice": own})' in src)
    check("...and nothing is cut at 1,500 characters any more", "text[:1500]" not in src)

    # ── G3: a save that changed nothing is not work ──
    day = {"staff": [{"staff_id": 3, "name": "Ravi", "role": "team_member"},
                     {"staff_id": 1, "name": "Founder", "role": "super_admin"}],
           "audit": [{"actor_id": 3, "action": "claim.gist", "target_type": "claim", "target_id": "71"},
                     {"actor_id": 3, "action": "claim.gist", "target_type": "claim", "target_id": "72"}],
           "gist_changed": {(72, "ravi")}, "moves": [], "notes": [], "acts": [], "claims": {}}
    people = ds.per_person(day)
    me = people[3]
    check("a gist save that changed something counts as work", 72 in me["claim_ids"])
    check("...one that changed nothing does not", 71 not in me["claim_ids"] and me["empty_saves"] == 1,
          (me["claim_ids"], me["empty_saves"]))

    # ── G3: worth a look ──
    day = {"staff": [{"staff_id": 3, "name": "Ravi", "role": "team_member"},
                     {"staff_id": 1, "name": "Founder", "role": "super_admin"}],
           "audit": [{"actor_id": 3, "action": "claim.info_edit", "target_type": "claim", "target_id": str(c)}
                     for c in (81, 82, 83)]
                    + [{"actor_id": 1, "action": "claim.info_edit", "target_type": "claim", "target_id": str(c)}
                       for c in (81, 82, 83)],
           "audit_prev": [{"actor_id": 3, "action": "claim.info_edit", "target_type": "claim", "target_id": str(c)}
                          for c in (81, 82, 83)]
                         + [{"actor_id": 1, "action": "claim.info_edit", "target_type": "claim", "target_id": str(c)}
                            for c in (81, 82, 83)],
           "gist_changed": set(), "notes": [], "acts": [], "claims": {}, "test_claims": {99},
           "moves_prev": [{"staff_id": 3, "claim_id": 84, "from_key": "live_cases", "to_key": "pending_draft"}],
           "moves": [{"staff_id": 3, "claim_id": 84, "from_key": "pending_draft", "to_key": "live_cases"},
                     {"staff_id": 3, "claim_id": 86, "from_key": "live_cases", "to_key": "hold", "kind": "park"},
                     {"staff_id": 3, "claim_id": 86, "from_key": "hold", "to_key": "live_cases", "kind": "resume"},
                     {"staff_id": 3, "claim_id": 99, "from_key": "a", "to_key": "b"},
                     {"staff_id": 3, "claim_id": 99, "from_key": "b", "to_key": "a"}],
           "status_flips": [{"claim_id": 85, "from_status": "in_review", "to_status": "review_query", "changed_by_id": 3},
                            {"claim_id": 85, "from_status": "review_query", "to_status": "in_review", "changed_by_id": 3}]}
    people = ds.per_person(day)
    people[3]["empty_saves"] = 4
    flags = ds.padding(day, people)
    why = " | ".join(flags.get(3, []))
    check("saves that changed nothing are flagged", "4 saves that changed nothing" in why, why)
    check("the same claims edited yesterday and today with no progress are flagged",
          "edited yesterday and again today" in why, why)
    check("a claim moved there and straight back is flagged", "NP-84 moved" in why, why)
    check("a status changed and changed back is flagged", "NP-85 status changed and changed back" in why, why)
    check("a test claim is never flagged", "NP-99" not in why, why)
    check("a park and its resume is not 'there and straight back' (review, 2 Oct)", "NP-86" not in why, why)
    check("a super-admin is never flagged", 1 not in flags, flags.get(1))

    # ── G3: blockers - nobody's first, owners named ──
    day.update({"claims_new": 0, "payments_n": 0, "payments_rs": 0, "snapshot": {}, "bucket_order": [],
                "buckets": {}, "on_leave": set(), "overdue_tasks": 0, "l2_unassigned": 0,
                "tasks_done": {}, "tasks_over": {}, "padding": flags,
                "blockers": {"items": [{"claim_id": 87, "who": "SAWAN", "stage": "escalation",
                                        "flags": ["stalled"], "age": 9, "owners": set()},
                                       {"claim_id": 65, "who": "PADAM", "stage": "escalation",
                                        "flags": ["docs_short"], "age": 8, "owners": {3}}],
                             "total": 2, "unowned": 1, "by_flag": {"stalled": 1, "docs_short": 1}}})
    txt = ds.team_text(day, people, {3: "Ravi", 1: "Founder"}, "en", "02 Oct 2026")
    check("blockers on our side are listed with how many have NOBODY", "Blockers on our side* (2; 1 with NOBODY" in txt, txt[-600:])
    check("...a claim with nobody on it says so", "NP-87 SAWAN" in txt and "owner: ⚠️ NOBODY" in txt, txt[-600:])
    check("...a claim with an owner names them", "NP-65 PADAM" in txt and "owner: Ravi" in txt)
    check("...with the focus areas", "Focus:" in txt)
    check("worth-a-look names the person and why", "Worth a look" in txt and "• Ravi —" in txt)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
