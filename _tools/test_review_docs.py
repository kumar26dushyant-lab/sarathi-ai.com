# -*- coding: utf-8 -*-
'''Rs 499 review documents reach the claim the review becomes.

Found 30 Sep: the files uploaded with a website review stayed on the PURCHASE. When the paid
review became a claim, the claim screen, the subscriber and the complainant saw no documents, and
the "arrived with no documents" alarm fired on it. A file uploaded after conversion was stranded
the same way.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_review_docs.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="rvd_"), "t.db")
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


async def doc_claim(doc_id):
    async with aiosqlite.connect(DBP) as c:
        return (await (await c.execute("SELECT claim_id FROM nidaan_claim_documents WHERE doc_id=?",
                                       (doc_id,))).fetchone())[0]


async def main():
    await db.init_db()
    await nid.ensure_claim_documents_table()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'Buyer','b@example.invalid','9000000000','x')")
        await c.execute("INSERT INTO nidaan_per_claim_purchase (purchase_id, account_id, status, amount_paid, claim_type, "
                        "insurer_name, insured_name, insured_phone) VALUES (50,1,'paid',588,'health','Star Health',"
                        "'RAM KUMAR','9000000001')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                        "status) VALUES (900,1,'health','OTHER','9000000002','intimated')")
        await c.commit()
    before = await nid.save_claim_document(account_id=1, stored_name="a.pdf", original_name="rejection.pdf",
                                           file_size=10, mime_type="application/pdf", purchase_id=50)
    elsewhere = await nid.save_claim_document(account_id=1, stored_name="b.pdf", original_name="x.pdf",
                                              file_size=10, mime_type="application/pdf", purchase_id=50,
                                              claim_id=900)
    check("before conversion the file sits on the purchase", not await doc_claim(before))
    cid = await nid.ensure_claim_for_paid_purchase(50)
    check("the paid review becomes a claim", bool(cid), cid)
    check("...and the file uploaded with the review is now on that claim", await doc_claim(before) == cid,
          await doc_claim(before))
    check("...a file already on another claim is NOT moved", await doc_claim(elsewhere) == 900)
    after = await nid.save_claim_document(account_id=1, stored_name="c.pdf", original_name="bill.pdf",
                                          file_size=10, mime_type="application/pdf", purchase_id=50)
    check("a file uploaded to the review AFTER conversion lands on the claim", await doc_claim(after) == cid)
    again = await nid.ensure_claim_for_paid_purchase(50)
    check("converting again changes nothing (idempotent)", again == cid)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
