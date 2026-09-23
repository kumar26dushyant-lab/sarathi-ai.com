# -*- coding: utf-8 -*-
'''"Payment recovered" must be said once, to a decided audience, and never again.

Founder, 24 Sep 01:27, after the same message arrived twice six minutes apart:
"it's really irritating if these messages firing again and again to others too ... do control
notifications and do intelligently, do[n't] fire gun continuously from any notification channel
to anyone."

Two faults made it repeat. _recover_payment ignored activate_from_razorpay_webhook's return
value, so a charge that was ALREADY recorded ("dup" - nothing recovered) was announced anyway,
on every pass of a guardian that runs every five minutes. And nothing anywhere remembered having
spoken, so even a genuine repeat would have repeated the message.

The trap in fixing it: finding 7 raises "a payment nobody was told about" for any ledger row
without `announced_at`. Staying quiet WITHOUT stamping swaps a message that repeats every five
minutes for an alarm that repeats every five minutes - which is what fired 21 times on 23 Sep.
So silence has to be recorded as a decision. That is checked here too, because it is the part
that is easy to get right once and lose later.

Runs against a temporary copy of the schema. Nothing real is read or written, and
NIDAAN_NO_OUTBOUND is set before the module loads.

    py -3.13 _tools/test_recovery_once.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"          # belt: nothing may leave, whatever is stubbed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite  # noqa: E402

FAILED = 0
SENT: list = []


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


DB = os.path.join(tempfile.mkdtemp(prefix="payguard-"), "t.db")

SCHEMA = """
CREATE TABLE nidaan_payments (
  pay_id INTEGER PRIMARY KEY AUTOINCREMENT, razorpay_payment_id TEXT, source TEXT,
  total_paise INTEGER, account_id INTEGER, claim_id INTEGER, created_at TIMESTAMP,
  announced_at TIMESTAMP);
CREATE TABLE nidaan_notifications (
  notif_id INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT, subject TEXT, body TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


async def setup():
    async with aiosqlite.connect(DB) as c:
        await c.executescript(SCHEMA)
        for i, pid in enumerate(("pay_A", "pay_B", "pay_C", "pay_D", "pay_E"), start=1):
            await c.execute("INSERT INTO nidaan_payments (razorpay_payment_id, source, "
                            "total_paise, account_id, created_at) VALUES (?,?,?,?,"
                            "datetime('now','-1 hour'))", (pid, "subscription", 58882, 85))
        await c.commit()


import biz_nidaan_pay_guard as pg  # noqa: E402

pg.DB_PATH = DB


async def fake_notify(ids, subject, body, **kw):
    """Stands in for notify_staff_inapp AND records what a real one would have stored."""
    SENT.append({"ids": list(ids), "subject": subject, "body": body,
                 "event_key": kw.get("event_key"), "email": kw.get("email")})
    async with aiosqlite.connect(DB) as c:
        # ONE ROW PER RECIPIENT, as the real notify_staff_inapp does. Inserting a single row
        # would have let a quota that counts raw rows pass this test and fail in production.
        for _sid in ids:
            await c.execute("INSERT INTO nidaan_notifications (event_key, subject, body) "
                            "VALUES (?,?,?)", (kw.get("event_key"), subject, body))
        await c.commit()
    return len(ids)


class _Nnot:
    notify_staff_inapp = staticmethod(fake_notify)

    @staticmethod
    async def _super_admin_staff():
        return [{"staff_id": 1}, {"staff_id": 2}, {"staff_id": 3}]


sys.modules["biz_nidaan_notifications"] = _Nnot


async def self_test_stub():
    return True, "stubbed - no network in a test"


pg.webhook_self_test = self_test_stub


async def announced_at(pid):
    async with aiosqlite.connect(DB) as c:
        r = await (await c.execute("SELECT announced_at FROM nidaan_payments "
                                   "WHERE razorpay_payment_id=?", (pid,))).fetchone()
    return (r or [None])[0]


async def main():
    await setup()
    print("\nThe 'payment recovered' message\n")

    p = {"id": "pay_A", "amount": 58882, "method": "upi", "notes": {}}

    # ── once ────────────────────────────────────────────────────────────────
    await pg._announce_recovery(p, "a silver subscription (account 85)")
    check("the first recovery is announced", len(SENT) == 1, SENT)
    check("...to every super admin, not one person", SENT and SENT[0]["ids"] == [1, 2, 3], SENT)
    check("...never by email", SENT and SENT[0]["email"] is False, SENT)
    check("...and the ledger row is stamped", await announced_at("pay_A") is not None)

    # ── and never again, however many times the guardian passes ─────────────
    for _ in range(12):
        await pg._announce_recovery(p, "a silver subscription (account 85)")
    check("twelve more guardian passes say NOTHING", len(SENT) == 1,
          "%d messages for one payment" % len(SENT))

    # ── the ceiling ─────────────────────────────────────────────────────────
    for pid in ("pay_B", "pay_C", "pay_D", "pay_E"):
        await pg._announce_recovery({"id": pid, "amount": 58882, "method": "upi", "notes": {}},
                                    "a silver subscription (account 85)")
    check("the hourly ceiling holds at %d messages" % pg._RECOVERY_MAX_PER_HOUR,
          len(SENT) == pg._RECOVERY_MAX_PER_HOUR,
          "%d sent for 5 payments" % len(SENT))

    # ── the trap: silence must not become an alarm ──────────────────────────
    quiet = [pid for pid in ("pay_B", "pay_C", "pay_D", "pay_E")
             if not any(pid in s["body"] for s in SENT)]
    check("some payments were deliberately not announced", bool(quiet), quiet)
    stamps = [(pid, await announced_at(pid)) for pid in quiet]
    check("...and EVERY one of them is still stamped, so finding 7 stays silent",
          all(a is not None for _, a in stamps), stamps)

    # ── the body still carries what it needs to be deduped ──────────────────
    check("the message names the payment, which is how it is deduped",
          all("Payment: pay_" in s["body"] for s in SENT), [s["body"][-60:] for s in SENT])

    # ── failing closed ──────────────────────────────────────────────────────
    real = pg.DB_PATH
    pg.DB_PATH = "/nonexistent/dir/cannot.db"
    before = len(SENT)
    await pg._announce_recovery({"id": "pay_Z", "amount": 100, "method": "upi", "notes": {}}, "x")
    pg.DB_PATH = real
    check("when it cannot tell whether it already spoke, it stays quiet", len(SENT) == before,
          "it spoke anyway")

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "one message per payment, capped, and silence is recorded"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
