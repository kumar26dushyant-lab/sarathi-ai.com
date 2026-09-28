"""Unit test for biz_nidaan_doc_checklist — the ₹499 funnel checklist engine.

Temp DB, no prod data. Run on server:
  cd /opt/sarathi && PYTHONPATH=/opt/sarathi /opt/sarathi/venv/bin/python /tmp/test_doc_checklist.py
"""
import asyncio
import os
import tempfile
import aiosqlite

import biz_database as db
import biz_nidaan_doc_checklist as ck

passed = failed = 0


def check(name, got, want):
    global passed, failed
    ok = got == want
    passed += ok
    failed += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got!r} want={want!r}")


async def _setup(path):
    async with aiosqlite.connect(path) as conn:
        await conn.execute("""
            CREATE TABLE nidaan_claim_doc_checklist (
                claim_id INTEGER NOT NULL, doc_key TEXT NOT NULL,
                required INTEGER DEFAULT 1, conditional INTEGER DEFAULT 0,
                received INTEGER DEFAULT 0, received_via TEXT, received_doc_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (claim_id, doc_key))""")
        # The checklist joins to the documents table to show a received document's real filename
        # (biz_nidaan_doc_checklist, "SELECT doc_id, original_name FROM nidaan_claim_documents").
        # The fixture did not have it, so this test failed on a missing table rather than on
        # anything it was written to check. Columns copied from production, not invented - a
        # fixture that disagrees with the real schema tests a database nobody runs.
        await conn.execute("""
            CREATE TABLE nidaan_claim_documents (
                doc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id    INTEGER NOT NULL,
                purchase_id   INTEGER,
                claim_id      INTEGER,
                stored_name   TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_size     INTEGER,
                mime_type     TEXT,
                uploaded_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                source        TEXT DEFAULT '',
                submitted_at  TEXT)""")
        await conn.commit()


async def main():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    db.DB_PATH = path
    try:
        await _setup(path)

        # ── template resolution + aliases ──
        check("home aliases to property", ck.canonical_type("home"), "property")
        check("mediclaim aliases to health", ck.canonical_type("mediclaim"), "health")
        check("unknown -> other", ck.canonical_type("zzz"), "other")
        # Seven required, plus other_docs which is optional. Written out on purpose: asking
        # doc_template_for() what to expect would agree with it on the day one goes missing.
        check("health has 8 docs", len(ck.doc_template_for("health")), 8)
        check("health required count = 7 (other_docs optional)",
              sum(1 for d in ck.doc_template_for("health") if d["required"]), 7)

        # ── label lookup + hindi ──
        check("label en", ck.label("discharge_summary", "health", "en"),
              "Discharge Summary / Discharge Documents")
        check("label hi non-empty", bool(ck.label("discharge_summary", "health", "hi")), True)
        check("label mr falls back to en",
              ck.label("discharge_summary", "health", "mr"),
              "Discharge Summary / Discharge Documents")

        # ── seed + pending ──
        n = await ck.seed_checklist_for_claim(100, "health")
        check("seeded 8 rows", n, 8)
        # idempotent
        await ck.seed_checklist_for_claim(100, "health")
        pend = await ck.pending_required_docs(100, "health")
        check("pending = 7 required (other_docs excluded)", len(pend), 7)
        check("optional other_docs NOT in pending",
              "other_docs" in [d["key"] for d in pend], False)

        st = await ck.checklist_status(100, "health")
        check("status not complete initially", st["complete"], False)
        check("required_total 7", st["required_total"], 7)
        check("received_required 0", st["received_required"], 0)

        # ── receive docs one by one (cross-channel) ──
        await ck.mark_doc_received(100, "rejection_letter", via=ck.VIA_DASHBOARD, doc_id=1)
        await ck.mark_doc_received(100, "policy_document", via=ck.VIA_WHATSAPP, doc_id=2)
        pend = await ck.pending_required_docs(100, "health")
        check("after 2 received, 5 pending", len(pend), 5)

        # The rest of them, one by one, across both channels.
        for i, key in enumerate(("discharge_summary", "itemized_bills", "claim_form", "kyc",
                                 "mail_credentials"), start=3):
            await ck.mark_doc_received(100, key,
                                       via=(ck.VIA_WHATSAPP if i % 2 else ck.VIA_DASHBOARD),
                                       doc_id=i)
        st = await ck.checklist_status(100, "health")
        check("all required in -> complete", st["complete"], True)
        check("received_required 7", st["received_required"], 7)
        pend = await ck.pending_required_docs(100, "health")
        check("pending now empty (pay-gate opens)", len(pend), 0)

        # Completing the REQUIRED list is what opens the gate - the optional one stays outstanding
        # and must not hold the claim up. This is the check that would catch other_docs quietly
        # becoming required.
        check("...even though the optional document never arrived",
              (await ck.checklist_status(100, "health"))["complete"], True)

        # ── making an optional document required puts it back in the way ──
        await ck.set_doc_required(100, "other_docs", True)
        st = await ck.checklist_status(100, "health")
        check("after making the optional one required, not complete", st["complete"], False)
        pend = await ck.pending_required_docs(100, "health")
        check("...and it is now pending", "other_docs" in [d["key"] for d in pend], True)

        # ── other type fallback ──
        await ck.seed_checklist_for_claim(200, "spaceship")  # unknown -> other
        st = await ck.checklist_status(200, "spaceship")
        check("unknown type seeds 'other' (3 docs)", st["required_total"], 3)

        # ── motor ──
        await ck.seed_checklist_for_claim(300, "motor")
        pend = await ck.pending_required_docs(300, "motor")
        check("motor required (surveyor is conditional) = 5", len(pend), 5)

        print(f"\n{'='*52}\n  {passed} passed, {failed} failed\n{'='*52}")
        return failed
    finally:
        os.unlink(path)


if __name__ == "__main__":
    raise SystemExit(1 if asyncio.run(main()) else 0)
