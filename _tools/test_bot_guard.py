# -*- coding: utf-8 -*-
'''How fast a linked phone may work the bot, and what gets written down.

Founder, 26 Sep 2026: *"we need to make bot highly secure from cybersecurity point of view"*.

The bot has had no rate limiting of any kind since it was written. Every HTTP route sits behind
slowapi; the bot is a long-polling loop, so none of that ever applied to it. A linked account -
which is a phone, and a phone can be borrowed, shared, stolen or left unlocked on a desk - could
ask the AI a thousand questions, pull a thousand files, or walk claim numbers one by one, and
nothing slowed it down or left a mark.

The part that is easy to write and easy to get backwards is which way each limit fails:
  - navigation fails OPEN, because a broken limiter must not take the bot down over menu taps;
  - anything that costs money, touches a medical document, or can be used to find out which
    claim numbers exist fails CLOSED.

Both directions are asserted here, because "it failed safe" is the kind of claim that is only
ever true until somebody checks.

    py -3.14 _tools/test_bot_guard.py
'''
import asyncio
import io
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite                     # noqa: E402
import biz_database as db            # noqa: E402
import biz_nidaan as nidaan          # noqa: E402
import biz_nidaan_bot_guard as g     # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="botguard-"), "t.db")
db.DB_PATH = DB
nidaan.DB_PATH = DB

ME = {"staff_id": 7, "name": "Test Staffer", "role": "team_member"}


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def main():
    await db.init_db()
    print("\nHow hard a phone may push\n")

    # ── the limits bite ─────────────────────────────────────────────────────
    g.reset_for_tests()
    count, per, _ = g.LIMITS["ai"]
    allowed = sum(1 for _ in range(count + 15) if g.allow(9, "ai")["ok"])
    check("the AI question limit stops at exactly its number", allowed == count,
          "%d allowed, limit is %d" % (allowed, count))
    r = g.allow(9, "ai")
    check("...and the refusal says how long to wait", not r["ok"] and r["retry_after"] > 0, r)
    check("...in words a person can read, not seconds-since-epoch",
          "minutes" in r["reason"] or "hours" in r["reason"] or "seconds" in r["reason"],
          r["reason"])
    check("...without accusing them of anything",
          not any(w in r["reason"].lower() for w in ("abuse", "blocked", "banned", "attack")),
          r["reason"])

    # ── one person's limit is not everybody's ───────────────────────────────
    check("a different person is unaffected", g.allow(10, "ai")["ok"])
    check("...and a different action is unaffected", g.allow(9, "nav")["ok"])

    # ── the window really is a window ───────────────────────────────────────
    g.reset_for_tests()
    g.LIMITS["probe"] = (2, 1, True)
    check("two allowed", g.allow(9, "probe")["ok"] and g.allow(9, "probe")["ok"])
    check("...third refused", not g.allow(9, "probe")["ok"])
    await asyncio.sleep(1.2)
    check("...and allowed again once the window has passed", g.allow(9, "probe")["ok"])
    del g.LIMITS["probe"]

    # ── an unknown action is not a free pass or a wall ──────────────────────
    check("an action with no limit set is allowed", g.allow(9, "something_new")["ok"])
    check("nobody at all is refused", not g.allow(None, "ai")["ok"])
    check("...and told to connect first, not told off",
          "connect" in g.allow(0, "upload")["reason"].lower())

    # ── and each kind fails the way it is supposed to ───────────────────────
    g.reset_for_tests()
    real = g._window
    g._window = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("guard is broken"))
    try:
        check("when the guard itself breaks, navigation still works (fails OPEN)",
              g.allow(9, "nav")["ok"])
        for action in ("ai", "upload", "claim", "write"):
            check("...but %-6s is refused (fails CLOSED)" % action,
                  not g.allow(9, action)["ok"])
    finally:
        g._window = real
    check("the guard works again afterwards", g.allow(9, "nav")["ok"])

    # ── files ───────────────────────────────────────────────────────────────
    check("an empty file is refused", not g.check_file("x.pdf", b"")["ok"])
    check("...and None is refused", not g.check_file("x.pdf", None)["ok"])
    check("an ordinary file is fine", g.check_file("x.pdf", b"%PDF-1.4 hello")["ok"])
    big = g.check_file("big.pdf", b"x" * (g.MAX_FILE_BYTES + 1))
    check("an oversized file is refused", not big["ok"])
    check("...and is told what to do instead", "portal" in big["reason"], big["reason"])

    # ── the trail ───────────────────────────────────────────────────────────
    await g.record(ME, "upload", claim_id=501, detail="2 files stored", allowed=True)
    await g.record(ME, "upload", claim_id=502, detail="not their claim", allowed=False)
    async with aiosqlite.connect(DB) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT action, target_id, detail, ip, actor_id FROM nidaan_audit_log "
            "WHERE action LIKE 'bot.%' ORDER BY log_id")).fetchall()]
    check("a successful upload is written down", any(r["action"] == "bot.upload" for r in rows), rows)
    check("a REFUSED one is written down too - an attempt is the interesting event",
          any(r["action"] == "bot.refused.upload" for r in rows), rows)
    check("...against the claim it was aimed at",
          {str(r["target_id"]) for r in rows} == {"501", "502"}, rows)
    check("...and marked as coming from Telegram, not from a browser",
          all(r["ip"] == "telegram" for r in rows), rows)
    check("...naming who did it", all(r["actor_id"] == 7 for r in rows), rows)

    # The audit must never be the reason an action fails.
    real_path = nidaan.DB_PATH
    nidaan.DB_PATH = "/nonexistent/dir/no.db"
    try:
        await g.record(ME, "upload", claim_id=1, detail="x")
        check("a broken audit does not raise into the caller", True)
    except Exception as e:  # noqa: BLE001
        check("a broken audit does not raise into the caller", False, e)
    finally:
        nidaan.DB_PATH = real_path

    # ── and it is actually WIRED. A limiter nobody calls is a limiter that does not exist,
    #    which is the same failure shape as a button that reaches nothing. ─────────────────
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(root, "biz_nidaan_telegram.py"), encoding="utf-8").read()
    ai = src.count('_guard.allow(staff.get("staff_id"), "ai")')
    print()
    check("the bot imports the guard", "import biz_nidaan_bot_guard as _guard" in src)
    check("the AI button is behind it", ai >= 1)
    check("...and so is a VOICE note, which spends the same Gemini money with no button pressed",
          ai >= 2, "%d 'ai' guard calls" % ai)
    check("claim lookups are behind it",
          src.count('_guard.allow(staff.get("staff_id"), "claim")') >= 2)
    check("the writes are behind it",
          src.count('_guard.allow(staff.get("staff_id"), "write")') >= 2)

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "menus stay up when the guard breaks; money, files and claims do not"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
