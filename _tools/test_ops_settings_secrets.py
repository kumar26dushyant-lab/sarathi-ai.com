# -*- coding: utf-8 -*-
'''The settings table holds policy AND credentials. Only one of those may reach a browser.

Found 26 Sep 2026, while working out how the @NidaanOpsBot token stopped working.

`nidaan_ops_settings` stores the live Telegram bot token beside things like the branch fee and
the GST rate. `get_all_ops_settings()` returned the whole table, and five endpoints hand that
straight to the client - including `GET /nidaan/ops/api/ops-settings`, which any staff member
may call, and which the ops page fetches whenever somebody opens the Tasks panel. It needs one
value from there: `task_create_min_role`.

So the live bot token was being delivered into the browser of all 23 active staff, routinely,
for as long as that code existed. A bot token is total control of the bot: read everything staff
send it, and send anything to all 21 linked people as the bot.

The fix is in the accessor rather than in the endpoints, because the next endpoint has not been
written yet. These checks hold that line:
  - a credential never comes out of get_all_ops_settings();
  - the app can still READ it by name, or the bot stops working for a different reason;
  - a secret nobody has thought of yet is caught by its NAME, not by a list somebody must update;
  - and a timestamp that merely contains a scary word is NOT withheld, because a filter that
    eats real settings gets switched off by the next person in a hurry.

    py -3.14 _tools/test_ops_settings_secrets.py
'''
import asyncio
import io
import os
import re
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import biz_database as db      # noqa: E402
import biz_nidaan as nidaan    # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="opssec-"), "t.db")
db.DB_PATH = DB
nidaan.DB_PATH = DB

FAKE_TOKEN = "8728919108:this-is-not-a-real-token-for-the-test"


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def main():
    await db.init_db()
    print("\nWhat may leave the settings table\n")

    await nidaan.set_ops_setting("telegram_bot_token", FAKE_TOKEN)
    await nidaan.set_ops_setting("doc_share_key", "share-key-abcdefghijklmnop")
    await nidaan.set_ops_setting("telegram_webhook_set_at", "2026-09-26 00:00:00")
    await nidaan.set_ops_setting("branch_l2_fee", "499")
    # A credential nobody has invented yet, to prove the rule is about names, not a list.
    await nidaan.set_ops_setting("whatsapp_api_key", "wa-secret-value-1234567890")

    allset = await nidaan.get_all_ops_settings()
    blob = repr(allset)

    check("the bot token is not in what the browser gets",
          "telegram_bot_token" not in allset and FAKE_TOKEN not in blob)
    check("...nor its value under any other key", "8728919108:" not in blob)
    check("the document share key is not either", "doc_share_key" not in allset)
    check("a secret nobody listed is caught by its name", "whatsapp_api_key" not in allset,
          [k for k in allset if "api_key" in k])

    check("ordinary policy still comes through", allset.get("branch_l2_fee") == "499")
    check("...and so does a timestamp that merely sounds alarming",
          allset.get("telegram_webhook_set_at") == "2026-09-26 00:00:00",
          allset.get("telegram_webhook_set_at"))
    check("...and the defaults are still there",
          allset.get("task_create_min_role") in ("team_member", "sub_super_admin", "super_admin"))

    check("the app can still READ the token by name - the bot must keep working",
          (await nidaan.get_ops_setting("telegram_bot_token", "")) == FAKE_TOKEN)
    check("...and a server-side caller can ask for everything, explicitly",
          (await nidaan.get_all_ops_settings(include_secrets=True)).get(
              "telegram_bot_token") == FAKE_TOKEN)

    check("the classifier says which is which",
          nidaan.is_secret_ops_key("telegram_bot_token")
          and nidaan.is_secret_ops_key("SOME_PASSWORD")
          and not nidaan.is_secret_ops_key("branch_l2_fee")
          and not nidaan.is_secret_ops_key("telegram_webhook_set_at"))

    # ── and no endpoint may ask for the secrets back ────────────────────────
    src = io.open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
    check("no endpoint asks for settings WITH the credentials",
          "get_all_ops_settings(include_secrets=True)" not in src
          and not re.search(r"get_all_ops_settings\(\s*True", src))

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "policy leaves the settings table; credentials do not"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
