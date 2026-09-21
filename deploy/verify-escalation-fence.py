"""#10 — does Escalation actually refuse to go back to Live Cases, and does nothing else change?

Runs against a COPY with outbound disabled.
"""
import asyncio
import os
import shutil
import sys
import tempfile

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

LIVE = "/opt/sarathi/sarathi_biz.db"
dst = os.path.join(tempfile.mkdtemp(prefix="fence_"), "copy.db")
shutil.copy(LIVE, dst)
for e in ("-wal", "-shm"):
    if os.path.exists(LIVE + e):
        shutil.copy(LIVE + e, dst + e)
os.environ["DB_PATH"] = dst

OV = os.path.dirname(os.path.abspath(__file__))
sys.path = [q for q in sys.path if os.path.abspath(q) not in (OV, "/opt/sarathi")]
sys.path.insert(0, "/opt/sarathi")
sys.path.insert(0, OV)

import aiosqlite
import biz_database as db; db.DB_PATH = dst
import biz_nidaan as nidaan; nidaan.DB_PATH = dst
import biz_nidaan_buckets as bk; bk.DB_PATH = dst

print("  buckets module under test: %s" % bk.__file__)
for _n, _m in list(sys.modules.items()):
    if _n.startswith("biz_") and getattr(_m, "DB_PATH", None) == LIVE:
        _m.DB_PATH = dst
for _n, _m in list(sys.modules.items()):
    if getattr(_m, "DB_PATH", None) == LIVE:
        sys.exit("ABORT: %s still points at the LIVE database" % _n)

P = F = 0


def check(label, got, want):
    global P, F
    ok = got == want
    if ok:
        P += 1
    else:
        F += 1
    print(("  PASS  " if ok else "  FAIL  ") + label + ("" if ok else "   got=%r want=%r" % (got, want)))


async def put_in(cid, bucket, sub=""):
    async with aiosqlite.connect(dst) as c:
        await c.execute(
            "UPDATE nidaan_claims SET pipeline_stage=?, pipeline_sub=?, pipeline_stage_at=CURRENT_TIMESTAMP "
            "WHERE claim_id=?", (bucket, sub, cid))
        await c.commit()


async def where(cid):
    async with aiosqlite.connect(dst) as c:
        r = await (await c.execute(
            "SELECT pipeline_stage FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone()
    return r[0] if r else None


async def main():
    global P, F
    async with aiosqlite.connect(dst) as c:
        r = await (await c.execute(
            "SELECT claim_id FROM nidaan_claims WHERE COALESCE(archived,0)=0 "
            "ORDER BY claim_id DESC LIMIT 1")).fetchone()
    cid = r[0]
    print("\nUsing claim NP-%s on the copy\n" % cid)

    print("1. ESCALATION must not go back to Live Cases")
    await put_in(cid, "escalation", "escalated")
    res = await bk.move(cid, "live_cases", actor="Tester", actor_role="team_member")
    check("refused for ordinary staff", res.get("ok"), False)
    print("      reason: %s" % str(res.get("error"))[:96])
    check("and the claim did not move", await where(cid), "escalation")

    print("\n2. but a SUPER ADMIN can still pull it back")
    await put_in(cid, "escalation", "escalated")
    res = await bk.move(cid, "live_cases", reason="genuine reversal",
                              actor="Boss", actor_role="super_admin")
    check("allowed", res.get("ok"), True)
    check("and it moved", await where(cid), "live_cases")

    print("\n3. the ORIGINAL Pending Draft fence still holds")
    await put_in(cid, "pending_draft", "drafting")
    res = await bk.move(cid, "live_cases", actor="Tester", actor_role="team_member")
    check("still refused", res.get("ok"), False)

    print("\n4. and nothing else is fenced — Escalation still moves FORWARD")
    await put_in(cid, "escalation", "escalated")
    res = await bk.move(cid, "lokpal", reason="fields filled later",
                        actor="Tester", actor_role="team_member")
    check("escalation -> lokpal allowed", res.get("ok"), True)
    check("it moved", await where(cid), "lokpal")

    print("\n5. Live Cases -> Pending Draft (the normal path) is untouched")
    await put_in(cid, "live_cases", "")
    res = await bk.move(cid, "pending_draft", reason="fields filled later",
                        actor="Tester", actor_role="team_member")
    check("allowed", res.get("ok"), True)

    print("\n%d passed, %d failed" % (P, F))
    return 1 if F else 0


sys.exit(asyncio.run(main()))
