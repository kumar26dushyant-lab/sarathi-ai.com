"""E2E test for the 'Review delivered' flow (legal assessment delivery).

Covers: deliver_review (both outcomes) sets status/outcome/findings + logs;
validation (bad outcome, empty findings); on_report_ready records the customer
notification (dashboard channel always written). Self-cleaning.

Run on the server:
  cd /opt/sarathi && PYTHONPATH=/opt/sarathi venv/bin/python _tools/test_review_delivered.py
"""
import asyncio, sys
import aiosqlite
try:
    from dotenv import load_dotenv; load_dotenv("/opt/sarathi/biz.env")
except Exception:
    pass
import biz_database as db
import biz_nidaan as nidaan
import biz_nidaan_notifications as nnot

EMAIL = "_review_delivered_test@example.invalid"


async def _claim(cid, col):
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(f"SELECT {col} FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone()
        return r[col] if r else None


async def _notif(cid, ev):
    async with aiosqlite.connect(db.DB_PATH) as c:
        r = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_notifications WHERE claim_id=? AND event_key=? AND channel='dashboard'",
            (cid, ev))).fetchone()
        return r[0]


async def run():
    res = []
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute("DELETE FROM nidaan_accounts WHERE email=?", (EMAIL,))
        cur = await c.execute("INSERT INTO nidaan_accounts(owner_name,email,phone,status) "
                              "VALUES('RD Test',?,'9000003000','active')", (EMAIL,))
        acc = cur.lastrowid; await c.commit()
    cid, _ = await nidaan.submit_claim(account_id=acc, user_id=None, claim_type="health",
        insured_name="RD Insured", insured_phone="9000003001", disputed_amount=500000,
        payment_status="paid", skip_eligibility=True)

    # validation
    try:
        await nidaan.deliver_review(cid, "bogus", "x", "system", 0); res.append(("rejects bad outcome", False))
    except ValueError: res.append(("rejects bad outcome", True))
    try:
        await nidaan.deliver_review(cid, "can_fight", "  ", "system", 0); res.append(("rejects empty findings", False))
    except ValueError: res.append(("rejects empty findings", True))

    # deliver — can_fight
    ok = await nidaan.deliver_review(cid, "can_fight", "Rejection letter is invalid; policy clause X applies. Strong basis to challenge.", "super_admin", 1)
    res.append(("deliver_review ok", ok))
    res.append(("status -> review_delivered", (await _claim(cid, "status")) == "review_delivered"))
    res.append(("outcome stored", (await _claim(cid, "review_outcome")) == "can_fight"))
    res.append(("findings stored", bool(await _claim(cid, "review_findings"))))
    res.append(("delivered_at set", bool(await _claim(cid, "review_delivered_at"))))
    async with aiosqlite.connect(db.DB_PATH) as c:
        n = (await (await c.execute("SELECT COUNT(*) FROM nidaan_claim_status_log WHERE claim_id=? AND to_status='review_delivered'", (cid,))).fetchone())[0]
    res.append(("status log entry written", n == 1))

    # notification (can_fight)
    await nnot.on_report_ready(cid)
    res.append(("customer notified (can_fight)", await _notif(cid, "claim.review_delivered") == 1))
    async with aiosqlite.connect(db.DB_PATH) as c:
        body = (await (await c.execute("SELECT body FROM nidaan_notifications WHERE claim_id=? AND event_key='claim.review_delivered' AND channel='dashboard' ORDER BY notif_id DESC LIMIT 1", (cid,))).fetchone() or [""])[0]
    res.append(("can_fight msg mentions legal team", "legal team" in (body or "").lower()))

    # switch to no_scope + notify
    await nidaan.deliver_review(cid, "no_scope", "Claim was settled per policy terms; no grounds to challenge.", "super_admin", 1)
    await nnot.on_report_ready(cid)
    async with aiosqlite.connect(db.DB_PATH) as c:
        body2 = (await (await c.execute("SELECT body FROM nidaan_notifications WHERE claim_id=? AND event_key='claim.review_delivered' AND channel='dashboard' ORDER BY notif_id DESC LIMIT 1", (cid,))).fetchone() or [""])[0]
    res.append(("no_scope msg says no strong basis", "no strong basis" in (body2 or "").lower() or "settled fairly" in (body2 or "").lower()))

    # cleanup
    async with aiosqlite.connect(db.DB_PATH) as c:
        for t in ("nidaan_notifications","nidaan_claim_status_log","nidaan_claim_doc_checklist","nidaan_claims"):
            try: await c.execute(f"DELETE FROM {t} WHERE claim_id=?", (cid,))
            except Exception: pass
        await c.execute("DELETE FROM nidaan_accounts WHERE account_id=?", (acc,)); await c.commit()

    p = sum(1 for _, ok in res if ok)
    for n, ok in res: print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    print(f"\nRESULT: {p}/{len(res)} " + ("PASS" if p == len(res) else "FAIL"))
    return p == len(res)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
