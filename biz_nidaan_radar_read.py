# -*- coding: utf-8 -*-
"""Is this email from an authority? Decided here, from the sender and the words.

Founder, 28 Sep 2026, on what the radar is for:
  *"we are waiting for authorities to respond and as soon as authorities respond those email will
  forward to CS and NP mail boxes... email radar should read all forwarded email and find if
  anything comes from bima lokpal govt. authorities and show us, simple."*

and on how:
  *"we need to make email radar also with no AI but some key words, domains, email language
  understanding bot can fulfil this requirement."*

WHY KEYWORDS BEAT A MODEL HERE, rather than merely being more compliant. Authority mail is the
most patterned mail this firm receives: it comes from a handful of known domains and repeats the
same dozen phrases - complaint registration number, personal hearing, Annexure VI-A, award. A
domain list answers "is this the Ombudsman" with certainty; a general model answers it with a
guess, and cannot tell you why. The radar had been triaging with a model and marked 44 of 58
emails "amber - a human looks", which is the same as saying nothing.

It is also the only version that is honest about privacy. The alternative sends the sender,
subject and 600 characters of body - about identified claimants, from statutory bodies - to a
third party outside India, for a job that a list does better.

FAIL-SAFE, IN ONE DIRECTION ONLY. Anything unrecognised is AMBER: a person looks. Only mail we
positively recognise as our own or as a service notification is cleared, because clearing on
doubt is how the one letter that mattered gets missed.

THE FORWARDED SENDER IS THE REAL SENDER. When a staff member forwards a letter by hand, the
From: header is the staff member - the authority's address is inside the body. Judging by the
header alone would therefore miss exactly the mail this feature exists for. Both are read.
"""
from __future__ import annotations

import re

# ── who counts as an authority ───────────────────────────────────────────────
# Domain suffixes. Matched on the DOMAIN, so a lookalike display name cannot fake one, and
# "gov.in" also covers every state and department beneath it.
AUTHORITY_DOMAINS = (
    "cioins.co.in",            # Council for Insurance Ombudsmen - the Bima Lokpal offices
    "bimalokpal.org",
    "irdai.gov.in",
    "irda.gov.in",
    "policyholder.gov.in",     # IRDAI's Bima Bharosa grievance portal
    "consumerhelpline.gov.in",
    "jagograhakjago.gov.in",
    "gov.in",
    "nic.in",
    "ecourts.gov.in",
    "sci.gov.in",
)

# Phrases that mark authority correspondence. Two weights: a STRONG phrase names the body or its
# paperwork and is enough on its own; a WEAK one is ordinary English that only counts alongside
# another signal, or "hearing" would flag every meeting invitation in the building.
STRONG_PHRASES = (
    "bima lokpal", "insurance ombudsman", "council for insurance ombudsmen",
    "ombudsman", "irdai", "bima bharosa", "annexure vi-a", "annexure vi a",
    "grievance redressal officer", "consumer disputes redressal",
    "complaint registration number", "complaint registration no",
)
WEAK_PHRASES = (
    "personal hearing", "hearing date", "award", "grievance", "token number",
    "complaint number", "complaint no", "registered your complaint", "case number",
)

# Mail that is definitely not what the radar is for. Our own systems, and the service
# notifications every mailbox collects. These were 51 of the first 58 items.
OWN_DOMAINS = ("nidaanpartner.com", "sarathi-ai.com", "nidaanlegalindia.com")
SERVICE_DOMAINS = (
    "google.com", "accounts.google.com", "mail.google.com", "googlemail.com",
    "openai.com", "email.openai.com", "microsoft.com", "apple.com",
    "razorpay.com", "github.com", "atlassian.com", "zoom.us",
)

# ── reading the forwarded sender out of the body ─────────────────────────────
# Gmail, Outlook and most clients write one of these when somebody forwards by hand. The address
# is taken from the FIRST such block: a chain of forwards puts the original letter deepest, and
# the first block is the one nearest the top, which is the message being forwarded to us.
_FWD_FROM = re.compile(
    r"(?:^|\n)\s*(?:from|de|von)\s*:\s*(?P<rest>[^\n]{0,200})", re.I)
_ADDR = re.compile(r"[\w.+-]+@[\w.-]+\.\w{2,}")


def forwarded_sender(body: str) -> str:
    """The address in the forwarded 'From:' line, or "" if there is none.

    Only looks at the first 4000 characters: the block we want sits at the top of the body, and
    reading further only risks picking up an address from a signature or an older quote.
    """
    text = (body or "")[:4000]
    for m in _FWD_FROM.finditer(text):
        found = _ADDR.search(m.group("rest") or "")
        if found:
            return found.group(0).strip().lower()
    return ""


def _domain(addr: str) -> str:
    a = (addr or "").strip().lower()
    return a.split("@")[-1] if "@" in a else ""


def _matches(domain: str, suffixes) -> str:
    """The suffix this domain falls under, or "". Matched on a boundary, so 'notgov.in' is not
    'gov.in' and a lookalike domain cannot slip through on a substring."""
    d = (domain or "").strip().lower().rstrip(".")
    for s in suffixes:
        if d == s or d.endswith("." + s):
            return s
    return ""


def _phrases_in(text: str) -> tuple:
    t = (text or "").lower()
    strong = [p for p in STRONG_PHRASES if p in t]
    weak = [p for p in WEAK_PHRASES if p in t]
    return strong, weak


def read_email(from_addr: str, from_name: str, subject: str, body: str,
               priority_senders=None) -> dict:
    """What is this email, and should anybody look at it?

    Returns {origin, category, flag, why, needs_action}.

      category  authority · insurer_or_other · internal · service
      flag      red   an authority wrote to us, or the founder listed this sender
                amber nobody recognised it - a person looks
                green our own mail, or a service notification

    `why` is a sentence a staff member can read on the screen. That is the point of doing this
    with lists: the radar can say "from cioins.co.in, the Insurance Ombudsman" instead of
    "the model thought so".
    """
    header_addr = (from_addr or "").strip().lower()
    fwd = forwarded_sender(body)
    # The forwarded sender wins when there is one - on a hand-forwarded letter the header is the
    # colleague who pressed forward, and the authority is inside.
    origin = fwd or header_addr
    hay = " ".join([subject or "", body or "", from_name or ""])

    # A sender the founder listed is an instruction, not a hint. Checked against BOTH addresses,
    # so listing an authority works whether the letter arrives direct or forwarded.
    for s in (priority_senders or []):
        s = (s or "").lstrip("@").strip().lower()
        if not s:
            continue
        for addr in (origin, header_addr):
            if addr == s or _domain(addr) == s or _domain(addr).endswith("." + s):
                return {"origin": origin, "category": "authority", "flag": "red",
                        "why": "%s is on your priority list" % (_domain(addr) or addr),
                        "needs_action": True}

    auth = _matches(_domain(origin), AUTHORITY_DOMAINS)
    if auth:
        return {"origin": origin, "category": "authority", "flag": "red",
                "why": "sent from %s%s" % (auth, " (forwarded)" if fwd else ""),
                "needs_action": True}

    strong, weak = _phrases_in(hay)
    if strong:
        return {"origin": origin, "category": "authority", "flag": "red",
                "why": "mentions “%s”" % strong[0], "needs_action": True}
    if len(weak) >= 2:
        return {"origin": origin, "category": "authority", "flag": "red",
                "why": "mentions “%s” and “%s”" % (weak[0], weak[1]),
                "needs_action": True}

    # Only now the quiet ones. Checked AFTER the authority tests on purpose: a letter forwarded
    # from one of our own addresses must still be judged on what is inside it.
    own = _matches(_domain(header_addr), OWN_DOMAINS)
    if own and not fwd:
        return {"origin": origin, "category": "internal", "flag": "green",
                "why": "our own system (%s)" % own, "needs_action": False}
    svc = _matches(_domain(origin), SERVICE_DOMAINS)
    if svc:
        return {"origin": origin, "category": "service", "flag": "green",
                "why": "a service notification from %s" % svc, "needs_action": False}

    if weak:
        return {"origin": origin, "category": "insurer_or_other", "flag": "amber",
                "why": "mentions “%s” — worth a look" % weak[0], "needs_action": True}
    return {"origin": origin, "category": "insurer_or_other", "flag": "amber",
            "why": "nobody recognised this sender — please check", "needs_action": True}
