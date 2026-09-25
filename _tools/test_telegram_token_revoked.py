# -*- coding: utf-8 -*-
'''When Telegram stops accepting the token, somebody has to be told.

On 25 Sep 2026 the @NidaanOpsBot token was revoked in BotFather at about 18:30 IST. Telegram
answered every call with 401 Unauthorized from that moment. The polling loop caught the failure,
slept three seconds, and tried again - with no log line, no flag, and no change to what the ops
screen reported. It did that roughly six thousand times before the founder noticed the bot was
dead by trying to use it, and the Telegram settings screen was still calling it active.

The revoked token was the day's news. The bug is that the app could not say so.

So this checks the behaviour that was missing, not the token:
  - a 401 is recognised as "this will never work again", in each shape the API replies in;
  - a timeout is NOT, because that one really is worth retrying;
  - the loop writes down that delivery has stopped, and Telegram's own words for why;
  - it says it ONCE, rather than every three seconds for five hours;
  - it backs off, instead of hammering Telegram with a dead token;
  - and when the token works again it clears the flag, so the screen does not keep showing
    yesterday's failure.

    py -3.14 _tools/test_telegram_token_revoked.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import biz_database as db              # noqa: E402
import biz_nidaan as nidaan            # noqa: E402
import biz_nidaan_telegram as tg       # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="tgrevoke-"), "t.db")
db.DB_PATH = DB
nidaan.DB_PATH = DB

UNAUTHORIZED = {"ok": False, "error_code": 401, "description": "Unauthorized"}


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def main():
    await db.init_db()
    print("\nA token Telegram no longer accepts\n")

    # ── telling a dead token from a blip ────────────────────────────────────
    check("a 401 is an auth failure", tg._is_auth_error(UNAUTHORIZED))
    check("...however the reply is shaped",
          tg._is_auth_error({"ok": False, "error": "http_401"})
          and tg._is_auth_error({"ok": False, "description": "Unauthorized"})
          and tg._is_auth_error({"ok": False, "error_code": 403}))
    check("a timeout is NOT - that one is worth retrying",
          not tg._is_auth_error({"ok": False, "error": "timeout"}))
    check("nor is a conflict, which clears itself",
          not tg._is_auth_error({"ok": False, "error_code": 409,
                                 "description": "Conflict: terminated by other getUpdates"}))
    check("Telegram's own words are kept, for the screen to show",
          tg._err_text(UNAUTHORIZED) == "Unauthorized", tg._err_text(UNAUTHORIZED))

    # ── the loop, against a bot that has been revoked ───────────────────────
    await nidaan.set_ops_setting("telegram_bot_token", "8728919108:revoked-token-for-the-test")
    await nidaan.set_ops_setting("telegram_bot_username", "NidaanOpsBot")
    await nidaan.set_ops_setting("telegram_enabled", "1")
    await nidaan.set_ops_setting("telegram_poll_active", "1")   # what the screen believed

    calls = []
    real_call = tg._call

    async def fake_call(method, payload=None, token=None, timeout=None):
        calls.append(method)
        return dict(UNAUTHORIZED)

    tg._call = fake_call
    tg._publish_bot_commands = lambda *a, **k: asyncio.sleep(0)
    try:
        # Long enough for several passes if it were still spinning every three seconds.
        await asyncio.wait_for(tg.run_polling_loop(), timeout=12)
    except asyncio.TimeoutError:
        pass
    finally:
        tg._call = real_call

    check("delivery is recorded as stopped, not left saying 'active'",
          (await nidaan.get_ops_setting("telegram_poll_active", "")) == "0")
    why = await nidaan.get_ops_setting("telegram_last_error", "")
    check("...with Telegram's reason, so nobody has to guess", "Unauthorized" in why, why)
    check("...and when it happened",
          len(await nidaan.get_ops_setting("telegram_last_error_at", "")) >= 10)

    getupdates = [c for c in calls if c == "getUpdates"]
    check("it backs off instead of hammering Telegram with a dead token",
          len(getupdates) <= 2, "%d getUpdates in 12s" % len(getupdates))

    cfg = await tg.get_config()
    check("the ops screen is told the truth: configured, but not working",
          cfg["configured"] and not cfg["poll_active"] and "Unauthorized" in cfg["last_error"],
          cfg)

    # ── and recovery clears it ──────────────────────────────────────────────
    async def working_call(method, payload=None, token=None, timeout=None):
        if method == "getUpdates":
            return {"ok": True, "result": []}
        return {"ok": True, "result": {}}

    tg._call = working_call
    try:
        await asyncio.wait_for(tg.run_polling_loop(), timeout=4)
    except asyncio.TimeoutError:
        pass
    finally:
        tg._call = real_call

    cfg = await tg.get_config()
    check("a token that works again clears the failure from the screen",
          cfg["poll_active"] and not cfg["last_error"], cfg)

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "a revoked token is now something the app says out loud"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
