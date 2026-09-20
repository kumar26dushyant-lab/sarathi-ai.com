"""Does every path that stores an inbound file actually refuse a virus?

Runs against a COPY with outbound disabled. EICAR is the standard harmless test string every
scanner recognises - no real malware is involved.
"""
import asyncio
import os
import shutil
import sys
import tempfile

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

LIVE = "/opt/sarathi/sarathi_biz.db"
dst = os.path.join(tempfile.mkdtemp(prefix="av_"), "copy.db")
shutil.copy(LIVE, dst)
for e in ("-wal", "-shm"):
    if os.path.exists(LIVE + e):
        shutil.copy(LIVE + e, dst + e)
os.environ["DB_PATH"] = dst
# Writable docs dir for the test, so a storage failure can never be mistaken for a scan refusal -
# the first run "passed" the infected case because the write failed on permissions, which is
# exactly the false pass this line removes.
_docs = os.path.join(os.path.dirname(dst), "uploads", "nidaan-docs")
os.makedirs(_docs, exist_ok=True)
os.environ["NIDAAN_DOCS_DIR"] = _docs

# The overlay MUST beat the deployed tree. sys.path.insert(0, "/opt/sarathi") after PYTHONPATH
# put the DEPLOYED module first, so the first run tested code without the change in it.
OV = os.path.dirname(os.path.abspath(__file__))
sys.path = [q for q in sys.path if os.path.abspath(q) not in (OV, "/opt/sarathi")]
sys.path.insert(0, "/opt/sarathi")
sys.path.insert(0, OV)

import aiosqlite
import biz_database as db; db.DB_PATH = dst
import biz_nidaan as nidaan; nidaan.DB_PATH = dst
import biz_av_scan as av
import biz_nidaan_doc_intake as intake

# Say WHICH copy is under test, always. When checking a change before it ships, set
# AV_REQUIRE_OVERLAY=1 and this refuses to run against the deployed tree - the first version of
# this test silently exercised the deployed module and reported a pass for code that did not
# contain the fix.
print("  intake module under test: %s" % intake.__file__)
if os.environ.get("AV_REQUIRE_OVERLAY") == "1" and not intake.__file__.startswith(OV):
    sys.exit("ABORT: loaded the DEPLOYED doc_intake, not the overlay - this test would be meaningless")

for _n, _m in list(sys.modules.items()):
    if _n.startswith("biz_") and getattr(_m, "DB_PATH", None) == LIVE:
        _m.DB_PATH = dst
for _n, _m in list(sys.modules.items()):
    if getattr(_m, "DB_PATH", None) == LIVE:
        sys.exit("ABORT: %s still points at the LIVE database" % _n)

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
CLEAN_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
             b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
             b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
             b"trailer<</Root 1 0 R>>\n%%EOF\n")

P = F = 0


def check(label, got, want):
    global P, F
    ok = got == want
    if ok:
        P += 1
    else:
        F += 1
    print(("  PASS  " if ok else "  FAIL  ") + label + ("" if ok else "   got=%r want=%r" % (got, want)))


async def main():
    global P, F
    print("\n1. THE SCANNER ITSELF")
    ok, why = await av.scan_bytes(CLEAN_PDF)
    check("a clean PDF is allowed", ok, True)
    ok, why = await av.scan_bytes(EICAR)
    check("EICAR is refused", ok, False)
    print("      reason: %s" % why)
    check("clamd is reachable", await av.available(), True)

    async with aiosqlite.connect(dst) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, account_id, COALESCE(claim_type,'health') AS t FROM nidaan_claims "
            "WHERE COALESCE(archived,0)=0 ORDER BY claim_id DESC LIMIT 1")).fetchone()
    claim = dict(r)
    print("\n2. WHATSAPP INTAKE  (claim NP-%s)" % claim["claim_id"])

    async def count_docs():
        async with aiosqlite.connect(dst) as c:
            return (await (await c.execute(
                "SELECT COUNT(*) FROM nidaan_claim_documents WHERE claim_id=?",
                (claim["claim_id"],))).fetchone())[0]

    before = await count_docs()
    res = await intake.accept(claim["claim_id"], claim["account_id"],
                              [("nasty.pdf", EICAR)], claim_type=claim["t"], source="whatsapp")
    after = await count_docs()
    check("an infected WhatsApp file stores NOTHING", after - before, 0)
    check("and it is reported for staff", len(res.get("rejected") or []), 1)
    print("      rejected: %s" % (res.get("rejected") or []))
    print("      notes:    %s" % (res.get("notes") or []))

    before = await count_docs()
    res = await intake.accept(claim["claim_id"], claim["account_id"],
                              [("good.pdf", CLEAN_PDF)], claim_type=claim["t"], source="whatsapp")
    after = await count_docs()
    check("a clean WhatsApp file still gets through", after - before >= 1, True)
    check("and nothing was rejected", len(res.get("rejected") or []), 0)

    print("\n3. MIXED BATCH — one bad file must not sink the good ones")
    before = await count_docs()
    res = await intake.accept(claim["claim_id"], claim["account_id"],
                              [("ok1.pdf", CLEAN_PDF), ("nasty.pdf", EICAR)],
                              claim_type=claim["t"], source="whatsapp")
    after = await count_docs()
    check("the clean file was still stored", after - before >= 1, True)
    check("the infected one was rejected", len(res.get("rejected") or []), 1)

    print("\n%d passed, %d failed" % (P, F))
    return 1 if F else 0


sys.exit(asyncio.run(main()))
