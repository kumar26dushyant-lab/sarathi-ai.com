# -*- coding: utf-8 -*-
'''A WhatsApp file that matches no claim is KEPT and sorted by a person - never dropped.

Founder, 1 Oct: forwarding allowed from any staff number; "if someone send or forward documents
to our nidaanpartner whatsapp ... right documents attach to right claim". Until now a file from a
number that is not a complainant was thrown away.

What these checks defend:
  * an unmatched file is downloaded, virus-checked and kept "to sort", with who sent it;
  * a file the virus check refuses - or cannot check at all - is NOT stored (fail closed);
  * a staff member's forward with "NP-123" in the caption is filed on that claim only if they may
    work on it; otherwise it waits to be sorted;
  * a person attaches a kept file to a claim they may work on, once; or sets it aside with a
    reason - nothing is deleted;
  * the whole path from the webhook: the sender is thanked once, staff told once.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_unsorted.py
'''
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
ROOT = tempfile.mkdtemp(prefix="unsorted_")
DBP = os.path.join(ROOT, "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_doc_intake as intake              # noqa: E402
intake.DOCS_DIR = Path(ROOT) / "docs"
import biz_nidaan_wa_unsorted as srt                # noqa: E402
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_wa_orchestrator as orch           # noqa: E402
import biz_nidaan_claim_authz as authz              # noqa: E402
import biz_av_scan as av                            # noqa: E402
import biz_nidaan_notifications as nn               # noqa: E402
srt.DB_PATH = flow.DB_PATH = orch.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def row(item_id):
    async with aiosqlite.connect(DBP) as c:
        c.row_factory = aiosqlite.Row
        return dict(await (await c.execute("SELECT * FROM nidaan_wa_unsorted WHERE item_id=?", (item_id,))).fetchone())


async def main():
    await db.init_db()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status, phone) "
                        "VALUES (7,'Marketing Ravi','r@example.invalid','x','team_member','active','9811100011')")
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status, phone, deleted_at) "
                        "VALUES (8,'Gone','g@example.invalid','x','team_member','inactive','9811100012','2026-09-01')")
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'ACME','a@example.invalid','9000000000','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, status) "
                        "VALUES (123,1,'health','X','9000000001','review_delivered')")
        await c.commit()

    verdict = {"v": (True, "")}

    async def dl(media_id):
        return {"ok": True, "content": b"%PDF-1.4 " + media_id.encode(), "mime": "application/pdf"}

    async def scan(data):
        if verdict["v"] == "boom":
            raise RuntimeError("clamd not running")
        return verdict["v"]
    orch._wa.download_media = dl
    av.scan_bytes = scan
    filed = []

    async def accept(claim_id, account_id, files, **kw):
        filed.append((claim_id, files[0][0], kw.get("source")))
        return {"ok": True, "stored": 1}
    intake.accept = accept

    # ── keeping ─────────────────────────────────────────────────────────
    k = await srt.keep("919999900001", "M1", "application/pdf", filename="bill.pdf", caption="my claim papers",
                       sender_role="subscriber", sender_name="Uttam")
    r1 = await row(k["item_id"])
    check("an unmatched file is kept to sort, with who sent it",
          r1["status"] == "to_sort" and r1["sender_name"] == "Uttam" and r1["stored_name"]
          and (intake.DOCS_DIR / r1["stored_name"]).exists(), r1)
    verdict["v"] = (False, "Eicar-Test-Signature")
    k2 = await srt.keep("919999900001", "M2", "application/pdf", filename="bad.pdf")
    r2 = await row(k2["item_id"])
    check("a file the virus check refuses is NOT stored", r2["status"] == "not_stored" and not r2["stored_name"]
          and "virus" in r2["reason"], r2)
    verdict["v"] = "boom"
    k3 = await srt.keep("919999900001", "M3", "application/pdf", filename="x.pdf")
    r3 = await row(k3["item_id"])
    check("...and nor is one the virus check could not run on (fail closed)",
          r3["status"] == "not_stored" and not r3["stored_name"], r3)
    verdict["v"] = (True, "")

    # ── staff forwards ──────────────────────────────────────────────────
    check("a staff member is recognised by their number", (await srt.staff_for("919811100011") or {}).get("staff_id") == 7)
    check("an archived staff member is not", await srt.staff_for("919811100012") is None)
    access = {"ok": True}

    async def may(staff, cid):
        return {"allowed": access["ok"] and cid == 123}
    authz.assert_claim_access = may
    ravi = await srt.staff_for("919811100011")
    f = await srt.staff_forward(ravi, "919811100011", "M4", "application/pdf",
                                filename="DISCHARGE SUMMARY.pdf", caption="NP-123 discharge")
    check("a staff forward captioned NP-123 is filed on NP-123", f["status"] == "attached"
          and filed[-1][:2] == (123, "DISCHARGE SUMMARY.pdf") and filed[-1][2] == "whatsapp_staff", (f, filed))
    access["ok"] = False
    f2 = await srt.staff_forward(ravi, "919811100011", "M5", "application/pdf", filename="y.pdf",
                                 caption="NP-123")
    check("...but not if they may not work on it - it waits to be sorted",
          f2["status"] == "to_sort" and "not on NP-123" in f2["reason"], f2)
    check("the claim number is read from the caption in its usual forms",
          [srt.claim_number(x) for x in ("NP-0123 bills", "np 45", "#NP123", "no number")] == [123, 45, 123, 0])

    # ── sorting by a person ─────────────────────────────────────────────
    access["ok"] = True
    staff = {"staff_id": 3, "role": "team_member", "name": "Suhana"}
    try:
        await srt.attach(k["item_id"], 999, staff=staff)
        check("attaching to a claim you are not on is refused", False)
    except srt.SortError:
        check("attaching to a claim you are not on is refused", True)
    a = await srt.attach(k["item_id"], 123, staff=staff)
    check("a person attaches a kept file to the claim", a["ok"] and filed[-1][0] == 123 and
          (await row(k["item_id"]))["status"] == "attached", (a, filed[-1]))
    try:
        await srt.attach(k["item_id"], 123, staff=staff)
        check("...only once", False)
    except srt.SortError:
        check("...only once", True)
    try:
        await srt.set_aside(f2["item_id"], staff=staff, reason="")
        check("setting aside needs a reason", False)
    except srt.SortError:
        check("setting aside needs a reason", True)
    await srt.set_aside(f2["item_id"], staff=staff, reason="duplicate of the discharge summary")
    ra = await row(f2["item_id"])
    check("...and with one it is set aside - the row and the file are kept",
          ra["status"] == "set_aside" and (intake.DOCS_DIR / ra["stored_name"]).exists(), ra)

    # ── the whole path from the webhook ─────────────────────────────────
    sent, told = [], []

    async def send_text(to, body):
        sent.append((to, body))
        return {"ok": True}

    async def notify(ids, subject, body, **kw):
        told.append(subject)
        return 1

    async def ids():
        return [1]
    flow.wa.send_text = send_text
    nn.notify_staff_inapp = notify
    flow._admin_ids = ids
    before = await srt.count_to_sort()
    for i in range(3):
        await flow.handle_inbound_payload({"entry": [{"changes": [{"value": {"messages": [
            {"from": "917000011111", "id": "wf%d" % i, "type": "document",
             "document": {"id": "MF%d" % i, "mime_type": "application/pdf", "filename": "page%d.pdf" % i}}]}}]}]})
    check("three files from an unknown number are all kept", await srt.count_to_sort() == before + 3)
    check("...the sender is thanked once, not three times", len([s for s in sent if s[0] == "917000011111"]) == 1, sent)
    check("...and staff are told once", len(told) == 1, told)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
