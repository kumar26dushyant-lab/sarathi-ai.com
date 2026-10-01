# -*- coding: utf-8 -*-
'''A complainant's signed authorization can never be removed - by staff, a subscriber or the
complainant themselves - while ordinary documents still can (1 Oct review: any team member, and
the complainant from their own page, could hard-delete the only proof of consent).

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_protected_documents.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="protdoc_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    await db.init_db()
    await nid.ensure_claim_documents_table()
    auth = await nid.save_claim_document(account_id=1, stored_name="a.pdf", original_name="authorization.pdf",
                                         file_size=1, mime_type="application/pdf", claim_id=7, source="authorization")
    plain = await nid.save_claim_document(account_id=1, stored_name="b.pdf", original_name="bill.pdf",
                                          file_size=1, mime_type="application/pdf", claim_id=7)
    for who, kw in (("staff (allow_any)", {"claim_id": 7, "allow_any": True}),
                    ("the complainant (claim-scoped)", {"claim_id": 7}),
                    ("the subscriber (account-scoped)", {"account_id": 1, "claim_id": 7})):
        try:
            r = await nid.delete_claim_document(auth, **kw)
            check("%s cannot remove a signed authorization" % who, False, r)
        except nid.ProtectedDocument:
            check("%s cannot remove a signed authorization" % who, True)
    async with aiosqlite.connect(DBP) as c:
        left = (await (await c.execute("SELECT COUNT(*) FROM nidaan_claim_documents WHERE doc_id=?", (auth,))).fetchone())[0]
    check("...and the record is still there", left == 1, left)
    check("an ordinary document can still be removed (wrong file sent)",
          await nid.delete_claim_document(plain, claim_id=7, allow_any=True) == "b.pdf")
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sarathi_biz.py"),
               encoding="utf-8").read()
    check("every delete route answers the refusal in words (one app-level handler)",
          "app.add_exception_handler(nidaan.ProtectedDocument" in src)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
