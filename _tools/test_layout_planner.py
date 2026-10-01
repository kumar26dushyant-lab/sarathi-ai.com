# -*- coding: utf-8 -*-
'''The Layout Planner (founder, 1 Oct): the team arranges the ops menu block by block, saves it
under their name, and a super admin chooses one.

  - a layout may only use real blocks, each once, and must place every block (nothing silently
    falls off the menu);
  - you change only your own, and only before it is chosen;
  - choosing one marks it; nothing is deleted.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_layout_planner.py
'''
import asyncio
import copy
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DBP = os.path.join(tempfile.mkdtemp(prefix="planner_"), "t.db")
import biz_database as db        # noqa: E402
db.DB_PATH = DBP
import biz_nidaan_nav as nav     # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    base = nav.current_layout()
    lay, err = nav.clean_layout(base)
    check("today's menu is a valid layout", lay and not err, err)

    bad = copy.deepcopy(base); bad["groups"][0]["blocks"].append("made_up")
    check("an unknown block is refused", nav.clean_layout(bad)[1].startswith("Unknown block"))
    dup = copy.deepcopy(base); dup["groups"][1]["blocks"].append(base["groups"][0]["blocks"][0])
    check("a block placed twice is refused", "twice" in nav.clean_layout(dup)[1])
    lost = copy.deepcopy(base); lost["groups"][0]["blocks"].pop()
    check("a layout that loses a block is refused", "must be placed" in nav.clean_layout(lost)[1])
    binned = copy.deepcopy(base); binned["not_needed"].append(binned["groups"][0]["blocks"].pop())
    check("moving a block to 'Not needed' is fine", not nav.clean_layout(binned)[1])
    check("a layout as text that is not JSON is refused", nav.clean_layout("{oops")[1] != "")

    ravi, sita = {"staff_id": 3, "name": "Ravi"}, {"staff_id": 4, "name": "Sita"}
    r1 = await nav.save_proposal(ravi, "Ravi's menu", "", binned)
    check("a team member saves their layout", r1.get("ok"), r1)
    r2 = await nav.save_proposal(sita, "Sita edits Ravi's", "", base, proposal_id=r1["proposal_id"])
    check("nobody can change someone else's layout", not r2.get("ok"), r2)
    r3 = await nav.save_proposal(ravi, "Ravi's menu v2", "tidier", base, proposal_id=r1["proposal_id"])
    check("...but the owner can", r3.get("ok"), r3)
    seen = await nav.proposals(4)
    check("everyone sees everyone's layouts, marked whose", len(seen) == 1 and not seen[0]["mine"]
          and seen[0]["staff_name"] == "Ravi", seen)

    c = await nav.choose(r1["proposal_id"], "Founder")
    check("a layout can be chosen", c.get("ok"), c)
    r4 = await nav.save_proposal(ravi, "change after choice", "", base, proposal_id=r1["proposal_id"])
    check("a chosen layout is the record - it cannot be changed", not r4.get("ok"), r4)
    s2 = await nav.save_proposal(sita, "Sita's", "", base)
    await nav.choose(s2["proposal_id"], "Founder")
    rows = await nav.proposals(1)
    chosen = [p for p in rows if p["status"] == "chosen"]
    check("one chosen at a time; the earlier one is kept, not deleted",
          len(chosen) == 1 and chosen[0]["proposal_id"] == s2["proposal_id"] and len(rows) == 2, rows)
    for i in range(6):                     # the sixth is refused
        last = await nav.save_proposal({"staff_id": 9, "name": "Busy"}, "n%d" % i, "", base)
    check("at most 5 layouts per person", not last.get("ok"), last)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
