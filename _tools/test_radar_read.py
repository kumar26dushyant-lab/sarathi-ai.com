# -*- coding: utf-8 -*-
'''The radar finds authority mail from the sender and the words, with no model.

Founder, 28 Sep: *"email radar should read all forwarded email and find if anything comes from
bima lokpal govt. authorities and show us, simple"* - and *"with no AI but some key words,
domains, email language understanding"*.

Measured against what the radar had actually collected: 58 emails, 8 red, 44 amber, 6 green, and
NOT ONE from an authority. 51 of the 58 were our own notifications and Google account mail, every
one of them put in front of staff as something to review. That is why nobody could read it.

What these checks defend:

  * THE FORWARDED SENDER. When somebody forwards a letter by hand the From: header is the
    colleague who pressed forward - the authority is inside the body. Judging by the header alone
    misses exactly the mail this feature exists for, which is what the old code did;
  * a known authority domain is certain, and a lookalike domain is not it;
  * our own mail and service notices are CLEARED, not queued - they were 88% of the noise;
  * anything unrecognised is AMBER, never green. Clearing on doubt is how the one letter that
    mattered gets missed;
  * a founder priority sender still overrides everything, direct or forwarded;
  * and every verdict carries a sentence a staff member can read, which is the whole reason for
    doing this with lists rather than a model.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_radar_read.py
'''
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import biz_nidaan_radar_read as rr   # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


# ── a letter forwarded by hand ───────────────────────────────────────────────
print("\nA Lokpal letter, forwarded by a colleague\n")

FWD_BODY = """---------- Forwarded message ---------
From: Insurance Ombudsman Bhopal <bimalokpal.bhopal@cioins.co.in>
Date: Mon, 28 Sep 2026 at 11:04
Subject: Complaint registration number BHP-G-051-2526-0412
To: <cs@nidaanpartner.com>

Dear Sir/Madam, your complaint has been registered. A personal hearing is scheduled.
"""

v = rr.read_email("asha@nidaanpartner.com", "Asha", "Fwd: Complaint registration", FWD_BODY)
check("the real sender is read out of the forwarded block",
      v["origin"] == "bimalokpal.bhopal@cioins.co.in", v["origin"])
check("...so it is flagged red", v["flag"] == "red", v)
check("...as an authority", v["category"] == "authority", v)
check("...and says why, readably", "cioins.co.in" in v["why"], v["why"])
check("...and is marked as needing somebody", v["needs_action"] is True)

# The old code judged the From: header only. That header is our own domain, so it would have been
# cleared as internal - the exact letter the feature exists for, filed as noise.
own = rr._matches(rr._domain("asha@nidaanpartner.com"), rr.OWN_DOMAINS)
check("...even though the From: header is our own domain", bool(own),
      "judging by the header alone would have cleared this")

# ── straight from an authority ───────────────────────────────────────────────
print("\nStraight from an authority\n")

for addr, who in (("bimalokpal.bhopal@cioins.co.in", "Ombudsman"),
                  ("grievance@irdai.gov.in", "IRDAI"),
                  ("noreply@policyholder.gov.in", "Bima Bharosa"),
                  ("registry@ecourts.gov.in", "court")):
    v = rr.read_email(addr, who, "Regarding your complaint", "Please find attached.")
    check("%-34s is an authority" % addr, v["flag"] == "red" and v["category"] == "authority", v)

# A lookalike must not pass as the real thing.
for bad in ("noreply@cioins.co.in.phish.example", "billing@notgov.in", "x@mygov.in.co"):
    v = rr.read_email(bad, "X", "hello", "nothing here")
    check("%-34s is NOT an authority" % bad, v["flag"] != "red", v)

# ── the words, when the domain says nothing ──────────────────────────────────
print("\nWhen the sender is unknown but the words are not\n")

v = rr.read_email("someone@randomhost.com", "", "Bima Lokpal hearing on 12 October", "")
check("a strong phrase alone is enough",
      v["flag"] == "red" and "bima lokpal" in v["why"].lower(), v)

v = rr.read_email("someone@randomhost.com", "", "Your complaint number and hearing date", "")
check("two weak phrases together are enough", v["flag"] == "red", v)

v = rr.read_email("someone@randomhost.com", "", "Award ceremony invitation", "")
check("one weak phrase on its own is NOT", v["flag"] == "amber", v)
check("...but it is still put in front of somebody", v["needs_action"] is True, v)

# ── the noise that was 88% of the radar ──────────────────────────────────────
print("\nThe noise that filled the radar\n")

v = rr.read_email("no-reply@nidaanpartner.com", "NidaanPartner", "New claim registered", "x")
check("our own notification is cleared", v["flag"] == "green" and v["category"] == "internal", v)

v = rr.read_email("no-reply@accounts.google.com", "Google", "Security alert", "x")
check("a Google account notice is cleared", v["flag"] == "green", v)

v = rr.read_email("billing@email.openai.com", "OpenAI", "Your receipt", "x")
check("a service receipt is cleared", v["flag"] == "green", v)

# But our own address must NOT clear a letter forwarded through it.
v = rr.read_email("asha@nidaanpartner.com", "Asha", "Fwd: hearing", FWD_BODY)
check("our own address does NOT clear a forwarded authority letter", v["flag"] == "red", v)

# ── never clear on doubt ─────────────────────────────────────────────────────
print("\nWhen nothing is recognised\n")

v = rr.read_email("someone@unknown-insurer.example", "", "Regarding policy", "Some text")
check("an unrecognised sender is amber, not green", v["flag"] == "amber", v)
check("...and says plainly that nobody recognised it", "recognised" in v["why"], v["why"])

for bad in (None, "", "not-an-address"):
    v = rr.read_email(bad, None, None, None)
    check("a malformed email does not crash and is not cleared",
          v["flag"] in ("amber", "red"), v)

# ── the founder's list still wins ────────────────────────────────────────────
print("\nThe priority list is an instruction\n")

v = rr.read_email("clerk@someinsurer.co.in", "", "Routine", "nothing",
                  priority_senders=["someinsurer.co.in"])
check("a listed domain is red whatever else was decided", v["flag"] == "red", v)
check("...and says it came from the list", "priority list" in v["why"], v["why"])

v = rr.read_email("asha@nidaanpartner.com", "Asha", "Fwd:", FWD_BODY,
                  priority_senders=["cioins.co.in"])
check("a listed domain works on the forwarded sender too", v["flag"] == "red", v)

# ── no model, anywhere on this path ──────────────────────────────────────────
print("\nNothing on this path can reach a model\n")

src = io.open("biz_nidaan_radar_read.py", encoding="utf-8").read()

# The IMPORTS, not a word search. "openai.com" appears here as a domain we SILENCE, and a search
# for the bare word failed on it - which would have pushed me to weaken the module to satisfy the
# test. What actually matters is that this file cannot reach anything: it imports `re` and
# nothing else, so there is no client to call and no socket to open.
import ast as _ast
tree = _ast.parse(src)
imported = set()
for node in _ast.walk(tree):
    if isinstance(node, _ast.Import):
        imported |= {a.name.split(".")[0] for a in node.names}
    elif isinstance(node, _ast.ImportFrom) and node.module:
        imported.add(node.module.split(".")[0])
check("the reader imports nothing but the standard regex module",
      imported <= {"re", "__future__"}, sorted(imported))
check("...so there is no client, no key and no socket in it",
      not any(w in src for w in ("biz_ai", "gemini", "GEMINI", "httpx", "requests(",
                                 "generativelanguage", "api_key", "API_KEY")),
      "a domain named in the silence list is not a call")

radar = io.open("biz_nidaan_radar.py", encoding="utf-8").read()
poll = radar[radar.index("async def poll_mailbox("):]
poll = poll[:poll.index("async def poll_all_mailboxes(")]
check("the poll no longer calls the model", "radar_triage_email" not in poll, poll[:200])
check("...and reads on this server instead", "_read.read_email(" in poll)
check("...and only a red item becomes a task",
      'if flag == "red":' in poll,
      "amber used to as well - 44 notices about our own email became 44 jobs")

print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
sys.exit(1 if FAILED else 0)
