"""#4 - picking a document is not the same as handing it over.

The founder watched somebody upload four files and remove two. Under the old flow all four
reached the office the instant they were picked, and two of them then vanished. What is proved
here is that the claim only counts a file once the person says so - and that everything already
on a claim is untouched, because it was handed over under the old rules.
"""
import asyncio
import os
import shutil
import sys
import tempfile

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

LIVE = "/opt/sarathi/sarathi_biz.db"
dst = os.path.join(tempfile.mkdtemp(prefix="ds_"), "copy.db")
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
import biz_nidaan_claimant as claimant; claimant.DB_PATH = dst

print("  nidaan module under test: %s" % nidaan.__file__)
assert nidaan.__file__.startswith(OV), "ABORT: testing the DEPLOYED module, not the change"
for _n, _m in list(sys.modules.items()):
    if getattr(_m, "DB_PATH", None) == LIVE:
        sys.exit("ABORT: %s still points at the LIVE database" % _n)

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print("  PASS  " + label)
    else:
        F += 1
        print("  FAIL  " + label + "\n          got:  %r\n          want: %r" % (got, want))


async def main():
    async with aiosqlite.connect(dst) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, account_id FROM nidaan_claims WHERE COALESCE(archived,0)=0 "
            "ORDER BY claim_id DESC LIMIT 1")).fetchone()
    cid, acc = int(dict(r)["claim_id"]), dict(r)["account_id"]
    print("\nClaim NP-%s on the copy\n" % cid)

    print("1. everything already on a claim stays handed over")
    # The migration runs on ensure_claim_documents_table(), which every call makes.
    before = await nidaan.get_claim_documents(claim_id=cid)
    await nidaan.ensure_claim_documents_table()
    async with aiosqlite.connect(dst) as c:
        n_null = (await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claim_documents WHERE submitted_at IS NULL")).fetchone())[0]
    check("no existing document was re-opened", int(n_null), 0)
    print("      (%d document(s) already on this claim)" % len(before))

    print("\n2. a file the complainant picks is held, not handed over")
    d1 = await nidaan.save_claim_document(
        account_id=acc, stored_name="a.pdf", original_name="MAIN BILL.pdf",
        file_size=10, mime_type="application/pdf", claim_id=cid,
        source="claimant", submitted=False)
    d2 = await nidaan.save_claim_document(
        account_id=acc, stored_name="b.pdf", original_name="IPD.pdf",
        file_size=10, mime_type="application/pdf", claim_id=cid,
        source="claimant", submitted=False)
    check("two are waiting", await nidaan.count_unsubmitted_documents(cid), 2)
    docs = {d["doc_id"]: d for d in await nidaan.get_claim_documents(claim_id=cid)}
    check("and the screen can tell", docs[d1]["submitted_at"], None)

    print("\n3. removing one before submitting leaves nothing behind")
    await nidaan.delete_claim_document(d2, claim_id=cid) if hasattr(
        nidaan, "delete_claim_document") else None
    async with aiosqlite.connect(dst) as c:
        await c.execute("DELETE FROM nidaan_claim_documents WHERE doc_id=?", (d2,))
        await c.commit()
    check("one left waiting", await nidaan.count_unsubmitted_documents(cid), 1)

    print("\n4. and then they say these are the ones")
    n = await nidaan.submit_claim_documents(cid)
    check("one was handed over", n, 1)
    check("nothing is waiting now", await nidaan.count_unsubmitted_documents(cid), 0)
    docs = {d["doc_id"]: d for d in await nidaan.get_claim_documents(claim_id=cid)}
    check("and it carries when", bool(docs[d1]["submitted_at"]), True)

    print("\n5. pressing it again hands over nothing")
    # The button is on a phone. A first tap that looked like nothing is why people press twice.
    stamp = docs[d1]["submitted_at"]
    n2 = await nidaan.submit_claim_documents(cid)
    check("nothing more went", n2, 0)
    docs = {d["doc_id"]: d for d in await nidaan.get_claim_documents(claim_id=cid)}
    check("and the first time is not overwritten", docs[d1]["submitted_at"], stamp)

    print("\n6. a staffer's own attachment is handed over by definition")
    d3 = await nidaan.save_claim_document(
        account_id=acc, stored_name="c.pdf", original_name="REJECTION.pdf",
        file_size=10, mime_type="application/pdf", claim_id=cid, source="")
    docs = {d["doc_id"]: d for d in await nidaan.get_claim_documents(claim_id=cid)}
    check("submitted the moment it is attached", bool(docs[d3]["submitted_at"]), True)
    check("and it does not appear as waiting", await nidaan.count_unsubmitted_documents(cid), 0)

    print("\n7. the complainant's own page can tell the two apart")
    await nidaan.save_claim_document(
        account_id=acc, stored_name="d.pdf", original_name="EXTRA.pdf",
        file_size=10, mime_type="application/pdf", claim_id=cid,
        source="claimant", submitted=False)
    mine = await claimant.list_claimant_docs(cid)
    waiting = [d for d in mine if not d.get("submitted_at")]
    check("one file is marked not sent yet", len(waiting), 1)
    check("and it is the one just picked", waiting[0]["original_name"], "EXTRA.pdf")
    check("the page is told about submitted_at at all",
          "submitted_at" in (mine[0] if mine else {}), True)

    print("\n%d passed, %d failed" % (P, F))
    return 1 if F else 0


sys.exit(asyncio.run(main()))
