# -*- coding: utf-8 -*-
'''Who wants to hear what — and which setting wins when two of them disagree.

Founder, 25 Sep, answering the two questions this module was waiting on:
  *"per event per role and per event per specific user involved, of course claim level settings
  will take precedence."*
And the reason, which is the real specification:
  *"just so I should not depend on notification thing on you every time to do code changes until
  anything breaks."*

A precedence chain is exactly the kind of code that reads correctly and behaves wrongly, because
every level looks right in isolation and only the ORDER is the feature. So each level is set
against a level below it and the winner is asserted, rather than each being tested alone.

The other half is what must NOT be switchable, and which way each failure falls:
  - money, security and system health are locked. A switch against one is STORED (the person set
    it, hiding that is how a screen starts lying) and IGNORED, and the resolver says which.
  - the dashboard bell is never silenced. Turning it off would delete the record of having been
    told rather than stop an interruption - quiet versus blind.
  - an unreadable preferences table FAILS TOWARDS BEING TOLD. The failure people notice is
    noise; the failure that costs money is the message that never came.

    py -3.13 _tools/test_notify_prefs.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import biz_database as db            # noqa: E402
import biz_nidaan_notify_prefs as np  # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="nprefs-"), "t.db")
db.DB_PATH = DB          # the prefs module asks for this at call time, so nothing else to set

EV = "claim.status"          # an ordinary, switchable event
LOCKED = "payment.failed"    # money


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def main():
    await db.init_db()
    print("\nWho wants to hear what\n")

    # ── nothing set ─────────────────────────────────────────────────────────
    r = await np.resolve(EV, channel="telegram", staff_id=5, role="team_member")
    check("with no setting at all, it is sent", r["send"], r)
    check("...and says so plainly", "no setting" in r["why"], r["why"])

    # ── role ────────────────────────────────────────────────────────────────
    await np.set_pref(scope="role", role="team_member", event_key=EV,
                      channel="telegram", enabled=False, updated_by="D")
    r = await np.resolve(EV, channel="telegram", staff_id=5, role="team_member")
    check("a ROLE switch turns it off for that role", not r["send"], r)
    check("...and names the role in the reason", "team_member" in r["why"], r["why"])
    r = await np.resolve(EV, channel="telegram", staff_id=5, role="super_admin")
    check("...and leaves other roles alone", r["send"], r)
    r = await np.resolve("claim.assigned", channel="telegram", staff_id=5, role="team_member")
    check("...and other events alone", r["send"], r)
    r = await np.resolve(EV, channel="email", staff_id=5, role="team_member")
    check("...and other channels alone", r["send"] or "no setting" in r["why"], r)

    # ── user beats role ─────────────────────────────────────────────────────
    await np.set_pref(scope="user", staff_id=5, event_key=EV, channel="telegram",
                      enabled=True, updated_by="D")
    r = await np.resolve(EV, channel="telegram", staff_id=5, role="team_member")
    check("a USER switch beats the role switch", r["send"], r)
    check("...and says it was their own setting", "your own setting" in r["why"], r["why"])
    r = await np.resolve(EV, channel="telegram", staff_id=6, role="team_member")
    check("...for that person only", not r["send"], r)

    # ── claim beats user ────────────────────────────────────────────────────
    await np.set_pref(scope="claim_user", staff_id=5, claim_id=200, event_key=EV,
                      channel="telegram", enabled=False, updated_by="D")
    r = await np.resolve(EV, channel="telegram", staff_id=5, role="team_member", claim_id=200)
    check("a CLAIM switch beats the user switch", not r["send"], r)
    check("...and says which claim it came from", "this claim" in r["why"], r["why"])
    r = await np.resolve(EV, channel="telegram", staff_id=5, role="team_member", claim_id=201)
    check("...on that claim only", r["send"], r)

    # ── an exact event beats a catch-all, at the same level ─────────────────
    await np.set_pref(scope="user", staff_id=7, event_key="*", channel="*",
                      enabled=False, updated_by="D")
    r = await np.resolve(EV, channel="telegram", staff_id=7, role="team_member")
    check("a '*' switch covers every event", not r["send"], r)
    await np.set_pref(scope="user", staff_id=7, event_key=EV, channel="telegram",
                      enabled=True, updated_by="D")
    r = await np.resolve(EV, channel="telegram", staff_id=7, role="team_member")
    check("...and an exact event beats it", r["send"], r)
    r = await np.resolve("claim.assigned", channel="telegram", staff_id=7, role="team_member")
    check("...while everything else stays off", not r["send"], r)

    # ── frequency ───────────────────────────────────────────────────────────
    await np.set_pref(scope="user", staff_id=8, event_key=EV, channel="telegram",
                      enabled=True, frequency=np.FREQ_DAILY, updated_by="D")
    r = await np.resolve(EV, channel="telegram", staff_id=8, role="team_member")
    check("'daily' still sends, but says so", r["send"] and r["frequency"] == np.FREQ_DAILY, r)
    await np.set_pref(scope="user", staff_id=8, event_key=EV, channel="telegram",
                      enabled=True, frequency=np.FREQ_OFF, updated_by="D")
    r = await np.resolve(EV, channel="telegram", staff_id=8, role="team_member")
    check("'off' means off even with enabled=1", not r["send"], r)

    # ── what nobody may switch off ──────────────────────────────────────────
    res = await np.set_pref(scope="user", staff_id=5, event_key=LOCKED, channel="telegram",
                            enabled=False, updated_by="D")
    check("a switch against a locked event is accepted, not refused", res["ok"], res)
    check("...and says plainly that it will not take effect",
          "cannot be switched off" in (res.get("ignored_because") or ""), res)
    r = await np.resolve(LOCKED, channel="telegram", staff_id=5, role="team_member")
    check("...and the money event is still sent", r["send"] and r["locked"], r)

    # ── the bell is never silenced ──────────────────────────────────────────
    await np.set_pref(scope="user", staff_id=5, event_key="*", channel="*",
                      enabled=False, updated_by="D")
    r = await np.resolve(EV, channel="bell", staff_id=5, role="team_member")
    check("the dashboard bell is never switched off", r["send"], r)
    check("...and says why", "always records" in r["why"], r["why"])

    # ── clearing falls back down the chain ──────────────────────────────────
    await np.clear_pref(scope="claim_user", staff_id=5, claim_id=200, event_key=EV,
                        channel="telegram")
    r = await np.resolve(EV, channel="telegram", staff_id=5, role="team_member", claim_id=200)
    check("clearing a claim switch falls back to the user's",
          "your own setting" in r["why"], r["why"])

    # ── bad input is refused, not stored ────────────────────────────────────
    check("an unknown scope is refused",
          not (await np.set_pref(scope="nonsense", event_key=EV))["ok"])
    check("an unknown frequency is refused",
          not (await np.set_pref(scope="user", staff_id=1, event_key=EV,
                                 frequency="sometimes"))["ok"])
    check("a role switch with no role is refused",
          not (await np.set_pref(scope="role", event_key=EV))["ok"])
    check("a claim switch with no claim is refused",
          not (await np.set_pref(scope="claim_user", staff_id=1, event_key=EV))["ok"])

    # ── fail towards being told ─────────────────────────────────────────────
    real = db.DB_PATH
    db.DB_PATH = "/nonexistent/dir/no.db"
    r = await np.resolve(EV, channel="telegram", staff_id=5, role="team_member")
    db.DB_PATH = real
    check("an unreadable table does NOT silence a notification", r["send"], r)

    # ── and the switches are visible ────────────────────────────────────────
    rows = await np.list_prefs(staff_id=5)
    check("the switches somebody set can be listed back", len(rows) >= 1, len(rows))

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "claim beats user beats role, and money cannot be switched off"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
