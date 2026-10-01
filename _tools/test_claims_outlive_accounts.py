# -*- coding: utf-8 -*-
'''Deleting an account is not deleting its claims (founder, 1 Oct 2026: "claims will always be in
our archived until I say to delete"). And the unpaid-lead document purge is off unless he turns
it on - so no "your documents will be deleted" notice goes out either.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_claims_outlive_accounts.py
'''
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
ROOT = tempfile.mkdtemp(prefix="keepclaims_")
DBP = os.path.join(ROOT, "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_retention as ret                  # noqa: E402
ret._DOCS_DIR = Path(ROOT) / "docs"

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def one(q, *a):
    async with aiosqlite.connect(DBP) as c:
        r = await (await c.execute(q, a)).fetchone()
        return r[0] if r else None


async def main():
    await db.init_db()
    await nid.ensure_claim_documents_table()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (5,'Leaving Subscriber','leave@example.invalid','9000000005','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, status, "
                        "payment_status, created_at) VALUES (51,5,'health','KEEP ME','9000000051','review_delivered',"
                        "'unpaid_lead', datetime('now','-40 days'))")
        await c.commit()
    ret._DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (ret._DOCS_DIR / "keep.pdf").write_bytes(b"%PDF-1.4 keep")
    await nid.save_claim_document(account_id=5, stored_name="keep.pdf", original_name="bill.pdf", file_size=13,
                                  mime_type="application/pdf", claim_id=51)
    await nid.save_claim_document(account_id=5, stored_name="auth.pdf", original_name="authorization.pdf",
                                  file_size=1, mime_type="application/pdf", claim_id=51, source="authorization")

    # the unpaid-lead purge is OFF by default: nothing deleted, nobody told it will be
    r = await ret.run_lead_retention()
    check("the 30-day lead purge is off by default", r.get("off") is True, r)
    check("...the lead's documents are still there",
          await one("SELECT COUNT(*) FROM nidaan_claim_documents WHERE claim_id=51") == 2)
    check("...no deletion notice was stamped", not await one("SELECT lead_notice_at FROM nidaan_claims WHERE claim_id=51"))

    # deleting the account keeps the claim, archived, with everything on it
    nid.cancel_nidaan_subscription = (lambda *_a, **_k: asyncio.sleep(0))
    out = await nid.execute_account_erasure(5)
    check("the account is anonymised", await one("SELECT owner_name FROM nidaan_accounts WHERE account_id=5") == "[deleted]")
    check("its claim is KEPT, archived",
          await one("SELECT COUNT(*) FROM nidaan_claims WHERE claim_id=51 AND archived=1") == 1, out)
    check("...with every document and the signed authorization",
          await one("SELECT COUNT(*) FROM nidaan_claim_documents WHERE claim_id=51") == 2)
    check("...and the file on disk", (ret._DOCS_DIR / "keep.pdf").exists())
    check("the result says claims were archived, none deleted",
          out.get("claims_archived") == 1 and out.get("claims_deleted") == 0, out)
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "biz_nidaan.py"),
               encoding="utf-8").read()
    body = src[src.index("async def execute_account_erasure"):]
    body = body[:body.index("\nasync def ")]
    check("account erasure contains no DELETE of claims or their documents",
          "DELETE FROM nidaan_claims" not in body and "DELETE FROM nidaan_claim_documents" not in body
          and "unlink" not in body)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
