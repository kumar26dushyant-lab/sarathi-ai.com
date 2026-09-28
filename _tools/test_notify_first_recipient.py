# -*- coding: utf-8 -*-
'''Every person on a notification list is told - including the first, and including a list of one.

29 Sep 2026. From 25 Sep, notify_staff_inapp recorded each person's bell with `telegram=_tg_ok`
BEFORE working out `_tg_ok` for them. The first person on every list got nothing (the error was
caught and logged), every one-person notice was lost, and everyone else got the PREVIOUS person's
Telegram setting. The founder is staff #1 - first on every list - and missed 85, his own
announcement and every payment alert among them.

What these checks defend:

  * a one-person notice is delivered;
  * the first person on a list is delivered to;
  * each person gets THEIR OWN Telegram decision, not the one before them;
  * a payment notice reaches the admins AND the staff it concerns - the claim's handler and the
    staff member whose referral brought the customer (founder, 29 Sep);
  * a branch Level-2 fee, whose notice IS the payment notice, says "Payment RECEIVED" first.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_notify_first_recipient.py
'''
import asyncio
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_root = tempfile.mkdtemp(prefix="notifyfirst_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_nidaan_notifications as nn               # noqa: E402
import biz_nidaan_notify_prefs as prefs             # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_staff (staff_id INTEGER PRIMARY KEY, name TEXT, role TEXT,
    email TEXT DEFAULT '', notify_email TEXT DEFAULT '', referral_code TEXT DEFAULT '',
    status TEXT DEFAULT 'active', deleted_at TIMESTAMP);
CREATE TABLE nidaan_claims (claim_id INTEGER PRIMARY KEY, assigned_to_staff_id INTEGER);
INSERT INTO nidaan_staff (staff_id, name, role) VALUES
    (1, 'Founder', 'super_admin'), (2, 'Admin Two', 'super_admin'),
    (5, 'Quiet One', 'sub_super_admin'), (7, 'Seven', 'sub_super_admin'),
    (30, 'Handler', 'team_member'), (31, 'Referrer', 'team_member'),
    (40, 'Bystander', 'team_member');
UPDATE nidaan_staff SET referral_code='ASHA31' WHERE staff_id=31;
INSERT INTO nidaan_claims (claim_id, assigned_to_staff_id) VALUES (77, 30);
"""

BELLS = []


async def f_record(**kw):
    BELLS.append({"to": kw.get("recipient_id"), "telegram": kw.get("telegram"),
                  "key": kw.get("event_key"), "subject": kw.get("subject")})
    return len(BELLS)


async def f_resolve(event_key, channel="email", staff_id=None, role="", claim_id=None):
    # Staff 5 has switched Telegram off; everyone else keeps it.
    if channel == "telegram":
        return {"send": staff_id != 5, "why": "test"}
    return {"send": False, "why": "test"}


async def f_email(**kw):
    return True


nn._record_notification = f_record
nn._send_email = f_email
prefs.resolve = f_resolve


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    print("\nEveryone on the list is told\n")

    BELLS.clear()
    n = await nn.notify_staff_inapp([30], "Task for you", "x", event_key="task.assigned")
    check("a ONE-person notice is delivered", n == 1 and [b["to"] for b in BELLS] == [30],
          (n, BELLS))
    check("...on Telegram too", BELLS and BELLS[0]["telegram"] is True, BELLS)

    BELLS.clear()
    n = await nn.notify_staff_inapp([1, 5, 7], "What's new", "x", event_key="ops.announcement")
    check("the FIRST person on a list is delivered to (staff #1, the founder)",
          [b["to"] for b in BELLS][:1] == [1] and n == 3, (n, BELLS))
    tg = {b["to"]: b["telegram"] for b in BELLS}
    check("each person gets THEIR OWN Telegram setting - 5 switched it off",
          tg == {1: True, 5: False, 7: True}, tg)

    print("\nPayments reach the admins and the staff they concern\n")

    BELLS.clear()
    await nn.on_payment_success("Claim review fee", 499, claim_id=77, ref_code="asha31")
    to = sorted(b["to"] for b in BELLS)
    check("every admin, the founder included", {1, 2, 5, 7} <= set(to), to)
    check("...the staff handling the claim", 30 in to, to)
    check("...and the staff whose referral brought the customer", 31 in to, to)
    check("...and nobody it does not concern", 40 not in to, to)
    check("...each once", len(to) == len(set(to)), to)
    check("...as a payment notice", BELLS and BELLS[0]["key"] == "payment.success"
          and "Payment RECEIVED" in BELLS[0]["subject"], BELLS[:1])

    print("\nA branch Level-2 fee says it is a payment\n")

    src = io.open("biz_nidaan_notifications.py", encoding="utf-8").read()
    body = src[src.index("async def on_branch_l2_paid"):]
    body = body[:body.index("\nasync def ", 10)]
    check("its title starts with Payment RECEIVED when a fee was paid",
          'f"🟢 Payment RECEIVED — Level-2 fee Rs.{fee}' in body, body[:200])

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
