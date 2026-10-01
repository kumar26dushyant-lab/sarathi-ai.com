# -*- coding: utf-8 -*-
'''The complainant's case-email password (1 Oct review of a founder screenshot):
  - it never rides along in an ordinary page load - not even a super admin's; "Show it" (one
    audited request) is the only way to see it;
  - only super admins / sub-super admins may change it through the API (the page hid the pencil,
    the API did not); the complainant's own WhatsApp capture still saves it;
  - once captured from WhatsApp, the chat copy of that message no longer holds it.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_case_secret.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import aiosqlite                  # noqa: E402
import biz_nidaan_buckets as bk   # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="secret-"), "t.db")
bk.DB_PATH = DB


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    import biz_database as db
    import biz_nidaan as n
    db.DB_PATH = DB
    n.DB_PATH = DB
    await db.init_db()
    await bk.ensure_seeded()
    async with aiosqlite.connect(DB) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone) VALUES (1,'A','a@b.com','9000000000')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                        "pipeline_stage, status) VALUES (31,1,'health','X','9000000001','escalation','in_review')")
        await c.commit()

    r = await bk.set_field(31, "case_email_password", "Secret#123", actor="complainant (WhatsApp)")
    check("the complainant's WhatsApp capture (no staff role) still saves it", r.get("ok"), r)
    r = await bk.set_field(31, "case_email_password", "Changed#1", actor="t", role="team_member")
    check("a team member cannot change it through the API", not r.get("ok"), r)
    r = await bk.set_field(31, "case_email_password", "Changed#2", actor="t", role="sub_super_admin")
    check("a sub-super admin can", r.get("ok"), r)
    vals = await bk.claim_fields(31)
    for role in ("super_admin", "sub_super_admin", "team_member"):
        shown = bk.mask_secrets(vals, role).get("case_email_password")
        check("an ordinary page load gives %s dots, never the password" % role, shown == bk.MASK, shown)

    src = open(os.path.join(ROOT, "biz_nidaan_wa_orchestrator.py"), encoding="utf-8").read()
    check("a captured password is taken out of the chat copy of the message",
          "UPDATE nidaan_wa_messages SET body=REPLACE(body, ?, '••••••••')" in src)
    ops = open(os.path.join(ROOT, "static", "nidaan_ops.html"), encoding="utf-8").read()
    check("'Show it' fills the case email card it sits on", "_l2Case.st.values[key] = d.value" in ops)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
