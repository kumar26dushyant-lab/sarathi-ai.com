# -*- coding: utf-8 -*-
'''One button asks every unconnected colleague to connect - and never posts a credential.

Founder, 26 Sep 2026, after creating @NidaanPartnerOpsBot to replace the deleted one:
  *"as soon as we put api key and click a button to push it to all staff manually, it should go
  to all staff to connect."*

Changing the bot clears every link by design (a chat_id only means something to the bot that
issued it), so all 23 people have to reconnect at once. That makes this message the only thing
standing between a working notification channel and a week of nobody being told anything.

The security line this holds, which is the reason the message reads the way it does: a connect
CODE is a bearer credential. Whoever opens it links THEIR Telegram to that staff account and
then receives that person's claim notifications. It lives 15 minutes and is single-use for
exactly that reason - which also makes it useless in an email nobody opens for an hour. So the
invite carries an ordinary portal link, signing in is the check, and the code is minted on the
page in front of the person it belongs to.

    py -3.14 _tools/test_telegram_invite_all.py
'''
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["NIDAAN_NO_OUTBOUND"] = "1"

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


def build_message():
    """Build the invite body exactly as the endpoint does, without importing the whole app.

    The body is a plain concatenation of literals in the source, so it is lifted out and
    evaluated. That keeps the check honest: it reads what will actually be sent, rather than a
    copy of it written here that could drift.
    """
    src = io.open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
    i = src.index("async def ops_telegram_remind_unlinked")
    blk = src[i:i + 4500]
    start = blk.index("    body = (")
    end = blk.index("\n    n = await nnot.notify_staff_inapp", start)
    expr = blk[start + len("    body = "):end]
    return eval(expr, {"link": "https://nidaanpartner.com/nidaan/ops?connect=telegram",  # noqa: S307
                       "bot_name": "NidaanPartnerOpsBot"})


print("\nAsking everyone to connect\n")
msg = build_message()
src = io.open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
ops = io.open(os.path.join(ROOT, "static", "nidaan_ops.html"), encoding="utf-8").read()

# ── it must not hand out a credential ───────────────────────────────────────
check("the invite carries NO connect code", "link_code" not in msg and "issue_link_code" not in msg)
check("...and nothing code-shaped rode along", not re.search(r"\b[A-Z0-9]{6,10}\b", msg),
      re.findall(r"\b[A-Z0-9]{6,10}\b", msg))
check("...and the endpoint never mints one", "issue_link_code" not in
      src[src.index("async def ops_telegram_remind_unlinked"):][:4500])
check("it carries a plain portal link instead",
      "/nidaan/ops?connect=telegram" in msg)

# ── it must be usable by the people who get it ──────────────────────────────
check("it is in English", "Connect Telegram to get your work updates" in msg)
check("...and in Hindi, really Devanagari and not a placeholder",
      len(re.findall(r"[ऀ-ॿ]", msg)) > 60,
      len(re.findall(r"[ऀ-ॿ]", msg)))
check("...and the Hindi gives the same three steps",
      msg.count("1.") == 2 and msg.count("2.") == 2 and msg.count("3.") == 2)
check("it names the bot people will actually see", "@NidaanPartnerOpsBot" in msg)
check("...twice, once per language", msg.count("@NidaanPartnerOpsBot") == 2)
check("it says what to press", "START" in msg)
check("the subject is bilingual too",
      'subject=("Connect your Telegram' in src and "\\u091f\\u0947\\u0932\\u0940" in src)

# ── the button, and the door it opens ───────────────────────────────────────
check("the panel has one button that does this", 'onclick="tgInviteAll()"' in ops)
check("...and the old vaguer one is gone", "tgRemind" not in ops)
check("it asks before sending to real people", "if (!confirm(msg)) return;" in ops)
check("...after saying how many, and who has no email",
      "pending-count" in ops and "unreachable" in ops)
check("the link lands people ON the connect card, not on a hunt for it",
      "connect === 'telegram'" in ops and "showPanel('telegram')" in ops)
check("...and the deep-link param is stripped, so a reload does not loop",
      "|| connect) {" in ops)
check("the whole send is written down in the audit trail",
      '"telegram.invite_all"' in src)
check("it is super-admin only", '_require_staff(request, "super_admin")' in
      src[src.index("async def ops_telegram_remind_unlinked"):][:1400])

print("\n" + ("%d failed" % FAILED if FAILED
              else "everyone gets asked, in both languages, and nobody is emailed a credential"))
sys.exit(1 if FAILED else 0)
