# -*- coding: utf-8 -*-
'''"Seen" and "stop telling me" are different things, and an acknowledgement must not last for ever.

Founder, 25 Sep, showing a 03:00 Telegram message about a bounced payment he had acknowledged at
19:27: *"there has to be a button also to stop these notifications on telegram and on dashboard
bell icon, one more below seen I am on it."*

TWO FAULTS behind that one screenshot.

1. THERE WAS NO WAY TO SAY "STOP". Only "Seen — I'm on it", which buys time and nothing else.
2. AN ACKED INCIDENT NUDGED EVERY TWO HOURS FOR EVER. _alert_due set `+2h` unconditionally for
   anything acknowledged, ignoring severity. So tapping Seen on a warning committed you to being
   reminded about it all night — the exact opposite of what tapping it means.

What is pinned here:
  - mute silences WITHOUT closing: the incident stays open, listed and counted. Going quiet must
    never look like going away.
  - it is recorded against a name. Silence nobody owns is how a real problem goes missing.
  - a muted incident is not picked up by the due query.
  - re-raising a STILL-TRUE finding does NOT unmute it. The guardian re-raises every five
    minutes, so unmuting there would make the button undo itself. A RESOLVED incident
    coming back does unmute: that is genuinely new.
  - an acked warning says its piece and stops; an acked CRITICAL still comes back, because
    something genuinely broken has to keep asking.

    py -3.13 _tools/test_incident_mute.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite                   # noqa: E402
import biz_database as db          # noqa: E402
import biz_nidaan_pay_guard as pg  # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="mute-"), "t.db")
db.DB_PATH = DB
pg.DB_PATH = DB


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def mk(key, severity, status="open"):
    async with aiosqlite.connect(DB) as c:
        await c.execute(
            "INSERT INTO nidaan_pay_incidents (key, check_name, severity, title, detail, "
            "first_seen, last_seen, status, alert_count, next_alert_at) "
            "VALUES (?,?,?,?,'',datetime('now'),datetime('now'),?,1,datetime('now','-1 minute'))",
            (key, "test", severity, "A test incident", status))
        await c.commit()
        r = await (await c.execute("SELECT inc_id FROM nidaan_pay_incidents WHERE key=?",
                                   (key,))).fetchone()
    return r[0]


async def row(inc_id):
    async with aiosqlite.connect(DB) as c:
        c.row_factory = aiosqlite.Row
        return dict(await (await c.execute(
            "SELECT * FROM nidaan_pay_incidents WHERE inc_id=?", (inc_id,))).fetchone())


async def due_ids():
    """The alerter's own query."""
    async with aiosqlite.connect(DB) as c:
        rows = await (await c.execute(
            "SELECT inc_id FROM nidaan_pay_incidents WHERE status IN ('open','acked') "
            "AND next_alert_at IS NOT NULL AND next_alert_at <> '' "
            "AND next_alert_at <= datetime('now') ORDER BY inc_id")).fetchall()
    return [r[0] for r in rows]


async def main():
    await db.init_db()
    print("\nSeen, and stop\n")

    a = await mk("bounced_payment:pay_X", "warn")
    check("an unmuted incident is due", a in await due_ids(), await due_ids())

    res = await pg.mute(a, 1, "Dushyant Sharma")
    check("mute reports success", res.get("ok"), res)
    r = await row(a)
    check("...and it stops being due", a not in await due_ids(), await due_ids())
    check("...WITHOUT being closed - still open and countable", r["status"] == "open", r["status"])
    check("...and it is still on the list Payment Health reads",
          any(x["inc_id"] == a for x in await pg.open_incidents()), "missing from open_incidents")
    check("...recorded against a name", r["muted_by_name"] == "Dushyant Sharma", r["muted_by_name"])
    check("...with when", bool(r["muted_at"]), r["muted_at"])

    # THE POINT OF MUTE. The guardian re-raises a still-true finding every five minutes, so if
    # that unmuted, the button would undo itself before anybody put their phone down.
    await pg._sync([{"key": "bounced_payment:pay_X", "check": "test", "severity": "warn",
                     "title": "A test incident", "detail": "still true"}], {"test"})
    check("re-raising a STILL-TRUE finding does not unmute it",
          (await row(a))["next_alert_at"] is None, (await row(a))["next_alert_at"])
    check("...and the silence still has its owner", (await row(a))["muted_by_name"] == "Dushyant Sharma")

    # But the problem going away and COMING BACK is new information.
    async with aiosqlite.connect(DB) as c:
        await c.execute("UPDATE nidaan_pay_incidents SET status='resolved', "
                        "resolved_at=datetime('now') WHERE inc_id=?", (a,))
        await c.commit()
    await pg._sync([{"key": "bounced_payment:pay_X", "check": "test", "severity": "warn",
                     "title": "A test incident", "detail": "it is back"}], {"test"})
    r2 = await row(a)
    check("a RESOLVED incident coming back speaks again", r2["next_alert_at"] is not None,
          r2["next_alert_at"])
    check("...and is no longer marked silenced", not r2["muted_at"], r2["muted_at"])

    # Muting something already resolved is a no-op, not an error.
    b = await mk("resolved_one", "warn", status="resolved")
    res = await pg.mute(b, 1, "X")
    check("muting a resolved incident is harmless", res.get("already") == "resolved", res)
    check("a missing incident says so", (await pg.mute(999999, 1, "X")).get("ok") is False)

    # ── the 03:00 bug ───────────────────────────────────────────────────────
    warn_gaps = [pg._next_gap_minutes("warn", n) for n in (1, 2, 3)]
    check("an acknowledged WARNING eventually stops",
          any(g is None for g in warn_gaps), warn_gaps)
    crit_gaps = [pg._next_gap_minutes("critical", n) for n in (1, 5, 50)]
    check("an acknowledged CRITICAL never stops", all(g is not None for g in crit_gaps),
          crit_gaps)

    import io
    src = io.open("biz_nidaan_pay_guard.py", encoding="utf-8").read()
    acked = src[src.index('if inc["status"] == "acked":'):]
    acked = acked[:acked.index("else:")]
    check("the acked branch asks the severity instead of always saying +2h",
          "_next_gap_minutes" in acked, acked[:200])
    check("...and can set no next alert at all", "next_alert_at=NULL" in acked)

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "stop means stop, and seen does not mean all night"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
