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
        check("health has 5 docs", len(ck.doc_template_for("health")), 5)
        check("health required count = 4 (1 conditional)",
              sum(1 for d in ck.doc_template_for("health") if d["required"]), 4)

        # ── label lookup + hindi ──
        check("label en", ck.label("discharge_summary", "health", "en"),
              "Discharge Summary / Discharge Documents")
        check("label hi non-empty", bool(ck.label("discharge_summary", "health", "hi")), True)
        check("label mr falls back to en",
              ck.label("discharge_summary", "health", "mr"),
              "Discharge Summary / Discharge Documents")

        # ── seed + pending ──
        n = await ck.seed_checklist_for_claim(100, "health")
        check("seeded 5 rows", n, 5)
        # idempotent
        await ck.seed_checklist_for_claim(100, "health")
        pend = await ck.pending_required_docs(100, "health")
        check("pending = 4 required (conditional excluded)", len(pend), 4)
        check("conditional prior_medical NOT in pending",
              "prior_medical" in [d["key"] for d in pend], False)

        st = await ck.checklist_status(100, "health")
        check("status not complete initially", st["complete"], False)
        check("required_total 4", st["required_total"], 4)
        check("received_required 0", st["received_required"], 0)

        # ── receive docs one by one (cross-channel) ──
        await ck.mark_doc_received(100, "rejection_letter", via=ck.VIA_DASHBOARD, doc_id=1)
        await ck.mark_doc_received(100, "policy_document", via=ck.VIA_WHATSAPP, doc_id=2)
        pend = await ck.pending_required_docs(100, "health")
        check("after 2 received, 2 pending", len(pend), 2)

        await ck.mark_doc_received(100, "discharge_summary", via=ck.VIA_WHATSAPP, doc_id=3)
        await ck.mark_doc_received(100, "itemized_bills", via=ck.VIA_DASHBOARD, doc_id=4)
        st = await ck.checklist_status(100, "health")
        check("all required in -> complete", st["complete"], True)
        check("received_required 4", st["received_required"], 4)
        pend = await ck.pending_required_docs(100, "health")
        check("pending now empty (pay-gate opens)", len(pend), 0)

        # ── conditional toggle: reviewer marks prior_medical required ──
        await ck.set_doc_required(100, "prior_medical", True)
        # need to seed that row first (it was seeded with required=0); seed inserted it
        st = await ck.checklist_status(100, "health")
        check("after making conditional required, not complete", st["complete"], False)
        pend = await ck.pending_required_docs(100, "health")
        check("prior_medical now pending", "prior_medical" in [d["key"] for d in pend], True)

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
