"""End-to-end test for ₹499 funnel Step 4 — WhatsApp/email parity handlers.

Exercises the three funnel notification handlers against the live DB and asserts
the dashboard-channel notification rows + message bodies (dashboard row is ALWAYS
written by dispatch(), so this passes without a live WhatsApp instance or SMTP).
Also round-trips the one-tap pay-link token.

Run on the server (sources biz.env via python-dotenv):
  cd /opt/sarathi && PYTHONPATH=/opt/sarathi venv/bin/python _tools/test_step4_funnel_wa.py
"""
import asyncio
import os
import sys
import aiosqlite

try:
    from dotenv import load_dotenv
    load_dotenv("/opt/sarathi/biz.env")
except Exception:
    pass

import biz_database as db
import biz_nidaan as nidaan
import biz_nidaan_doc_checklist as ck
import biz_nidaan_notifications as nnot

EMAIL = "_step4_funnel_wa@example.invalid"


async def _notif_rows(claim_id, event_key):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT * FROM nidaan_notifications WHERE claim_id=? AND event_key=? AND channel='dashboard'",
            (claim_id, event_key))).fetchall()
        return [dict(r) for r in rows]


async def run():
    results = []

    # ── setup: throwaway account + free unpaid_lead claim ────────────────────
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM nidaan_accounts WHERE email=?", (EMAIL,))
        cur = await conn.execute(
            "INSERT INTO nidaan_accounts(owner_name,firm_name,email,phone,status) "
            "VALUES('Step4 WA Test','',?,'9000000777','active')", (EMAIL,))
        acc = cur.lastrowid
        await conn.commit()

    cid, _ = await nidaan.submit_claim(
        account_id=acc, user_id=None, claim_type="health",
        insured_name="WA Test", insured_phone="9000000888",
        disputed_amount=400000, payment_status="unpaid_lead", skip_eligibility=True)
    await ck.seed_checklist_for_claim(cid, "health")

    # language + consent, exactly as the submit endpoint does
    await nnot.set_comm_lang(acc, "hi")
    await nnot.set_subscriber_pref(acc, wa_opt_in=True)
    prefs = await nnot.get_subscriber_prefs(acc)
    results.append(("comm_lang persisted = hi", prefs.get("comm_lang") == "hi"))
    results.append(("wa_opt_in persisted = 1", int(prefs.get("wa_opt_in")) == 1))

    # ── 1) lead filed → doc-chase ────────────────────────────────────────────
    await nnot.on_lead_filed(cid, acc)
    rows = await _notif_rows(cid, "funnel.lead_filed")
    body = rows[0]["body"] if rows else ""
    results.append(("lead_filed notification recorded", len(rows) == 1))
    results.append(("lead_filed body lists a pending doc",
                    "•" in body and ("Discharge" in body or "Policy" in body or "पॉलिसी" in body or "अस्पताल" in body or "बिल" in body)))
    results.append(("lead_filed body is Hindi", "नमस्ते" in body))

    # ── 2) complete docs → pay-gate ready (one-tap link) ─────────────────────
    for d in await ck.pending_required_docs(cid, "health"):
        await ck.mark_doc_received(cid, d["key"], via=ck.VIA_DASHBOARD, doc_id=None)
    await nnot.on_funnel_pay_ready(cid, acc)
    rows = await _notif_rows(cid, "funnel.pay_ready")
    body = rows[0]["body"] if rows else ""
    results.append(("pay_ready notification recorded", len(rows) == 1))
    results.append(("pay_ready body has one-tap link", f"/nidaan/pay/{cid}" in body))
    results.append(("pay_ready body shows disputed ₹4,00,000", "4,00,000" in body))

    # idempotency: a second call must NOT add another row
    await nnot.on_funnel_pay_ready(cid, acc)
    rows2 = await _notif_rows(cid, "funnel.pay_ready")
    results.append(("pay_ready is idempotent (still 1 row)", len(rows2) == 1))

    # ── 3) pay-link token round-trips + is claim-bound ───────────────────────
    tok = nidaan.create_pay_link_token(cid, acc)
    ok_info = nidaan.verify_pay_link_token(tok, cid)
    results.append(("pay-link token verifies for its claim",
                    bool(ok_info) and ok_info["account_id"] == acc and ok_info["claim_id"] == cid))
    results.append(("pay-link token REJECTED for a different claim",
                    nidaan.verify_pay_link_token(tok, cid + 99) is None))
    results.append(("pay-link token REJECTED if a session token is passed",
                    nidaan.verify_pay_link_token(nidaan.create_nidaan_token(acc, EMAIL, ""), cid) is None))

    # ── 4) paid → confirmation ───────────────────────────────────────────────
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("UPDATE nidaan_claims SET payment_status='paid' WHERE claim_id=?", (cid,))
        await conn.commit()
    await nnot.on_funnel_paid(cid, acc, "2026-06-16T12:00:00")
    rows = await _notif_rows(cid, "funnel.paid")
    body = rows[0]["body"] if rows else ""
    results.append(("paid notification recorded", len(rows) == 1))
    results.append(("paid body mentions 48 business hours (hi)", "48" in body))

    # pay-gate must NOT fire once paid
    await nnot.on_funnel_pay_ready(cid, acc)
    results.append(("pay_ready suppressed after paid",
                    len(await _notif_rows(cid, "funnel.pay_ready")) == 1))

    # ── cleanup ──────────────────────────────────────────────────────────────
    async with aiosqlite.connect(db.DB_PATH) as conn:
        for tbl in ("nidaan_notifications", "nidaan_claim_doc_checklist",
                    "nidaan_claim_status_log", "nidaan_tasks", "nidaan_claims"):
            try:
                await conn.execute(f"DELETE FROM {tbl} WHERE claim_id=?", (cid,))
            except Exception:
                pass
        await conn.execute("DELETE FROM nidaan_subscriber_prefs WHERE account_id=?", (acc,))
        await conn.execute("DELETE FROM nidaan_accounts WHERE account_id=?", (acc,))
        await conn.commit()

    # ── report ───────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\nRESULT: {passed}/{len(results)} " + ("PASS" if passed == len(results) else "FAIL"))
    return passed == len(results)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
