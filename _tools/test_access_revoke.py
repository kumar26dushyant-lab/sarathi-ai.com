# -*- coding: utf-8 -*-
'''Access ends when the account ends - on the next request, not when a token runs out.

Founder, 30 Sep: "if anyone not paid or cancelled their subscription, their access should be
revoked... once access changed or any user of nidaanpartner.com deleted or disabled they should
not have access for anything."

What was found and what these checks defend:

  * a subscriber token was checked for its signature only, so a suspended or erased account kept
    the dashboard for up to 30 days - now the account row is read on every request;
  * deletion_pending is still let in: it is the grace window in which they can undo the deletion;
  * an unknown status is refused (allowlist, fail closed);
  * a disabled Authorized Partner kept its portal for up to 7 days - now refused at once;
  * a database that cannot be read means "no", and that "no" is not cached;
  * staff: the same, where it used to let everyone in on a read error;
  * Cancel on the dashboard stopped nothing at Razorpay, so the next month's charge went through
    and switched the plan back on - cancel now stops the autopay, and if Razorpay will not confirm,
    the super admins are told;
  * the deletion path uses the same stop (once, not twice), and ops' erase stops billing too;
  * WhatsApp does not recognise a suspended account or a disabled partner as one.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_access_revoke.py
'''
import asyncio
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

_root = tempfile.mkdtemp(prefix="revoke_")
DBP = os.path.join(_root, "t.db")
os.environ["DB_PATH"] = DBP

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_wa_identity as wid                # noqa: E402
wid.DB_PATH = DBP
import biz_nidaan_notifications as nn               # noqa: E402
import biz_nidaan_access as acc                   # noqa: E402
acc.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


def fresh():
    acc.clear()


def fn_source(src, name):
    """The body of one top-level function in a source file."""
    i = src.index("\ndef %s(" % name)
    j = src.find("\ndef ", i + 5)
    k = src.find("\nasync def ", i + 5)
    ends = [x for x in (j, k) if x != -1]
    return src[i:min(ends) if ends else len(src)]


async def main():
    await db.init_db()
    async with aiosqlite.connect(DBP) as c:
        for aid, status, deleted, phone in ((1, "active", None, "9000000001"),
                                            (2, "suspended", None, "9000000002"),
                                            (3, "deleted", "2026-09-01", "9000000003"),
                                            (4, "deletion_pending", None, "9000000004"),
                                            (5, "merged", None, "9000000005")):
            await c.execute("INSERT INTO nidaan_accounts (account_id, email, owner_name, phone, "
                            "status, deleted_at, password_hash) VALUES (?,?,?,?,?,?,'x')",
                            (aid, "a%d@example.invalid" % aid, "Owner %d" % aid, phone, status, deleted))
        await c.execute("INSERT INTO nidaan_branches (branch_code, city, name, status, contact_phone, "
                        "contact_email) VALUES ('GOOD-01','Indore','Good','active','9100000001','g@example.invalid')")
        await c.execute("INSERT INTO nidaan_branches (branch_code, city, name, status, contact_phone, "
                        "contact_email) VALUES ('OFF-01','Indore','Off','disabled','9100000002','o@example.invalid')")
        await c.execute("INSERT INTO nidaan_subscriptions (account_id, plan, status, razorpay_subscription_id, "
                        "amount_paid) VALUES (1,'silver','active','sub_TESTONE',999)")
        await c.commit()

    # ── subscriber accounts ───────────────────────────────────────────────
    fresh()
    check("an active subscriber is let in", acc.still_open("acct", 1))
    check("a suspended account is refused", not acc.still_open("acct", 2))
    check("an erased account is refused", not acc.still_open("acct", 3))
    check("deletion_pending is let in (they can still undo it)", acc.still_open("acct", 4))
    check("an unknown status ('merged') is refused", not acc.still_open("acct", 5))
    check("an account that does not exist is refused", not acc.still_open("acct", 99))

    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_accounts SET status='suspended' WHERE account_id=1")
        await c.commit()
    check("within the 30 s window the old answer stands (the cache is real)", acc.still_open("acct", 1))
    fresh()
    check("an account suspended after login is out once the window passes",
          not acc.still_open("acct", 1))
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_accounts SET status='active' WHERE account_id=1")
        await c.commit()
    fresh()

    # ── Authorized Partners and staff ─────────────────────────────────────
    check("an active Authorized Partner is let in", acc.still_open("branch", "GOOD-01"))
    check("...whatever case the code arrives in", acc.still_open("branch", "good-01"))
    check("a disabled Authorized Partner is refused", not acc.still_open("branch", "OFF-01"))
    check("an unknown partner code is refused", not acc.still_open("branch", "NOPE-01"))
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status) VALUES (11,'On','on@example.invalid','x','team_member','active')")
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status, deleted_at) "
                        "VALUES (12,'Gone','gone@example.invalid','x','team_member','inactive','2026-09-01')")
        await c.commit()
    check("an active staff member is let in", acc.still_open("staff", 11))
    check("an archived staff member is refused", not acc.still_open("staff", 12))
    check("an empty key is refused", not acc.still_open("acct", "") and not acc.still_open("branch", None))
    check("an unknown kind is refused", not acc.still_open("admin", 1))

    # ── an unreadable database means no, and the no is not remembered ─────
    fresh()
    acc.DB_PATH = os.path.join(_root, "missing-dir", "no.db")
    check("an unreadable database refuses the subscriber", not acc.still_open("acct", 4))
    check("an unreadable database refuses the partner", not acc.still_open("branch", "GOOD-01"))
    check("an unreadable database refuses staff", not acc.still_open("staff", 11))
    acc.DB_PATH = DBP
    check("...and the refusal was not cached - the next request is let in", acc.still_open("acct", 4))

    # ── staff who are out hear nothing - Telegram and phone push ──────────
    import biz_nidaan_telegram as tg
    tg.db.DB_PATH = DBP
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status) "
                        "VALUES (13,'Paused','p@example.invalid','x','team_member','inactive')")
        for sid, chat in ((11, "5001"), (13, "5003")):
            await c.execute("INSERT INTO nidaan_staff_telegram (staff_id, chat_id) VALUES (?,?)", (sid, chat))
        await c.commit()
    sent = []

    async def fake_send(chat, text, buttons=None):
        sent.append(chat)
        return True, ""

    async def on():
        return True
    real_send, real_on = tg.send_message, tg.is_enabled
    tg.send_message, tg.is_enabled = fake_send, on
    ok_active = await tg.notify_staff(11, "hello")
    ok_paused = await tg.notify_staff(13, "hello")
    tg.send_message, tg.is_enabled = real_send, real_on
    check("an active staffer's linked Telegram gets the message", ok_active[0] and "5001" in sent, sent)
    check("an inactive (not archived) staffer's Telegram gets nothing", "5003" not in sent and not ok_paused[0],
          (sent, ok_paused))
    nsrc = io.open("biz_nidaan_notifications.py", encoding="utf-8").read()
    psrc = nsrc[nsrc.index("async def push_to_staff"):]
    psrc = psrc[:psrc.index("\nasync def ", 10)]
    check("phone push reaches only active staff", "s.status='active' AND s.deleted_at IS NULL" in psrc)

    # ── every login helper actually asks ──────────────────────────────────
    for path in ("sarathi_biz.py", "nidaan_app.py"):
        src = io.open(path, encoding="utf-8").read().replace("\r\n", "\n")
        check("%s: the subscriber token is checked against the account" % path,
              '_row_still_open("acct"' in fn_source(src, "_nidaan_bearer"))
        check("%s: the partner token is checked against the partner" % path,
              '_row_still_open("branch"' in fn_source(src, "_branch_bearer"))
        check("%s: the staff check is the same one" % path,
              '_row_still_open("staff"' in fn_source(src, "_staff_still_active"))
        check("%s: and that one place is biz_nidaan_access" % path,
              "_acc.still_open(kind, key)" in fn_source(src, "_row_still_open"))

    # ── cancel stops the autopay, once, and says so if it cannot ──────────
    calls, alerts = [], []
    real_stop, real_alert = nid.stop_razorpay_autopay, nn.notify_staff_inapp

    async def fake_alert(ids, title, body, **kw):
        alerts.append((title, kw.get("event_key")))

    async def fake_admins():
        return [{"staff_id": 7}]
    real_admins = nn._super_admin_staff
    nn.notify_staff_inapp, nn._super_admin_staff = fake_alert, fake_admins

    async def stop_fails(s):
        calls.append(s)
        return False
    nid.stop_razorpay_autopay = stop_fails
    await nid.cancel_nidaan_subscription(1)
    async with aiosqlite.connect(DBP) as c:
        st = (await (await c.execute("SELECT status FROM nidaan_subscriptions WHERE account_id=1")).fetchone())[0]
    check("cancel asks Razorpay to stop the autopay", calls == ["sub_TESTONE"], calls)
    check("our record is cancelled either way, as the customer asked", st == "cancelled", st)
    check("when Razorpay will not confirm, the super admins are told",
          any(k == "payment.autopay_stop_failed" for _, k in alerts), alerts)
    check("that event is in the notification registry",
          "payment.autopay_stop_failed" in open("biz_nidaan_notify_registry.py", encoding="utf-8").read())

    # the deletion path: one stop per plan, not a second private copy of the call
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_subscriptions (account_id, plan, status, razorpay_subscription_id, "
                        "amount_paid) VALUES (4,'gold','active','sub_TESTFOUR',1999)")
        await c.commit()
    calls.clear(); alerts.clear()

    async def stop_ok(s):
        calls.append(s)
        return True
    nid.stop_razorpay_autopay = stop_ok
    await nid.request_account_deletion(4)
    check("deleting an account stops its autopay exactly once", calls == ["sub_TESTFOUR"], calls)
    check("...and a confirmed stop raises no alarm", not alerts, alerts)
    src = open("biz_nidaan.py", encoding="utf-8").read()
    check("only one place in the code calls Razorpay's subscription cancel",
          src.count("/subscriptions/{rzp_sub}/cancel") == 1, src.count("/subscriptions/{rzp_sub}/cancel"))
    body = src[src.index("async def execute_account_erasure"):]
    body = body[:body.index("\nasync def ")]
    check("ops' hard erase cancels the plan first", "await cancel_nidaan_subscription(account_id)" in body)

    nid.stop_razorpay_autopay, nn.notify_staff_inapp, nn._super_admin_staff = real_stop, real_alert, real_admins
    check("under NIDAAN_NO_OUTBOUND the real stop never calls Razorpay",
          (await nid.stop_razorpay_autopay("sub_X")) is True,      # NO_OUTBOUND: never calls out
          "NIDAAN_NO_OUTBOUND must short-circuit")

    # ── WhatsApp does not recognise closed accounts ───────────────────────
    r = await wid.resolve("919000000001")
    check("WhatsApp recognises an active subscriber", r.get("role") == "subscriber", r)
    r = await wid.resolve("919000000002")
    check("WhatsApp does not recognise a suspended account as a subscriber", r.get("role") != "subscriber", r)
    r = await wid.resolve("919100000002")
    check("WhatsApp does not recognise a disabled partner as a partner", r.get("role") != "branch", r)
    r = await wid.resolve("919100000001")
    check("WhatsApp recognises an active partner", r.get("role") == "branch", r)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
