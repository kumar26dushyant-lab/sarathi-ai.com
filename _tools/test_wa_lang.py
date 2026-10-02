# -*- coding: utf-8 -*-
"""WHATSAPP IN THE PERSON'S LANGUAGE, RECORDED IN ENGLISH (founder, 2 Oct 2026).

  * every message that is not English gets an English copy next to the original;
  * one that is English is marked so, and is not translated again;
  * when the AI is down nothing breaks - the message waits and fill_missing() does it later;
  * a staff reply sent in their language keeps the staff member's own words as the record;
  * the bot accepts Marathi, Punjabi and the other languages - and the fixed lines fall back to
    the closest one a reader of that language reads, never to something unreadable.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_lang.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="walang_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_wa_lang as wl                     # noqa: E402
import biz_nidaan_whatsapp as wa                    # noqa: E402
import biz_nidaan_wa_brain as brain                 # noqa: E402
import biz_nidaan_wa_messages as msgs               # noqa: E402
import biz_nidaan_wa_guard as guard                 # noqa: E402
flow.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def row(rid):
    async with aiosqlite.connect(DBP) as c:
        return await (await c.execute("SELECT lang, body_en FROM nidaan_wa_messages WHERE wam_row_id=?",
                                      (rid,))).fetchone()


async def last_id():
    async with aiosqlite.connect(DBP) as c:
        return (await (await c.execute("SELECT MAX(wam_row_id) FROM nidaan_wa_messages")).fetchone())[0]


async def main():
    await db.init_db()
    calls = []
    ai_up = {"on": True}

    async def fake_ai(prompt):
        calls.append(prompt)
        if not ai_up["on"]:
            return None
        if "माझा" in prompt:
            return {"lang": "mr", "en": "My claim was rejected"}
        if "Hello" in prompt:
            return {"lang": "en", "en": ""}
        return {"lang": "hinglish", "en": "translated"}
    wl._ai = fake_ai

    print("\n-- an English copy for the team --")
    await flow.log_message(direction="in", msisdn="919876543210", body="माझा क्लेम नाकारला")
    await asyncio.sleep(0.2)
    r = await row(await last_id())
    check("a Marathi message gets its English copy and its language", r == ("mr", "My claim was rejected"), r)
    await flow.log_message(direction="in", msisdn="919876543210", body="Hello, any update?")
    await asyncio.sleep(0.2)
    r = await row(await last_id())
    check("an English message is marked English - nothing to translate", r == ("en", ""), r)

    ai_up["on"] = False
    await flow.log_message(direction="in", msisdn="919876543210", body="kab tak hoga")
    await asyncio.sleep(0.2)
    rid = await last_id()
    r = await row(rid)
    check("the AI is down: the message is kept, waiting for its copy (nothing breaks)", r[1] is None, r)
    ai_up["on"] = True
    n = await wl.fill_missing()
    r = await row(rid)
    check("...and the catch-up gives it one later", n == 1 and r == ("hinglish", "translated"), (n, r))

    print("\n-- a staff reply in their language --")
    before = len(calls)
    with wa.sending_as("human", "Ravi", "5"), wa.english_record("Please send the discharge summary", "mr"):
        await wa._log_outbound({"to": "919876543210", "type": "text", "text": {"body": "कृपया डिस्चार्ज समरी पाठवा"}},
                               {"ok": True, "message_id": "wamid.1"})
    await asyncio.sleep(0.2)
    r = await row(await last_id())
    check("the staff member's own English is the record, with the language it went in",
          r == ("mr", "Please send the discharge summary"), r)
    async with aiosqlite.connect(DBP) as c:
        src = (await (await c.execute("SELECT en_src FROM nidaan_wa_messages WHERE wam_row_id=?",
                                      (await last_id(),))).fetchone())[0]
    check("...marked as the staff member's words, not a machine translation", src == "staff", src)
    check("...and it is NOT machine-translated again", len(calls) == before, calls[before:])

    print("\n-- what never goes to the translator --")
    before = len(calls)
    await flow.log_message(direction="in", msisdn="919876543210", body="482913")
    await flow.log_message(direction="out", msisdn="919876543210", body="482913 is your verification code.",
                           template_name="np_login_code", sender="system")
    await flow.log_message(direction="out", msisdn="919876543210", body="Namaste, your claim is registered",
                           sender="journey")
    await asyncio.sleep(0.2)
    check("a code, a template and a fixed journey message are never sent to the AI", len(calls) == before,
          calls[before:])

    print("\n-- languages --")
    check("Marathi and Gujarati fall back to the Hindi lines, Punjabi to Hinglish, Tamil to English",
          (wl.base("mr"), wl.base("gu"), wl.base("pa"), wl.base("ta"), wl.base("hi"), wl.base("")) ==
          ("hi", "hi", "hinglish", "en", "hi", "hinglish"))
    check("the journey messages follow that fallback", msgs._lang("mr") == "hi" and msgs._lang("ta") == "en")
    check("the STOP line is never missing, whatever the language",
          all(guard.footer_text(c) for c in ("mr", "pa", "ta", "xx", "")))
    check("the bot's fixed lines exist in Marathi and Punjabi",
          "मी" in brain.handoff_text("mr") and "ਮੈਂ" in brain.handoff_text("pa") and brain.handoff_text("ta"))
    check("a language the bot names is accepted; a made-up one is not", wl.norm("PA") == "pa" and wl.norm("klingon") == "")
    check("typing 'marathi' switches the language", flow._LANG_WORDS.get("marathi") == "mr")

    print("\n" + ("all passed" if not FAILED else f"{FAILED} failed"))
    sys.exit(1 if FAILED else 0)


asyncio.run(main())
