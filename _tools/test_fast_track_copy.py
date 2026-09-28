# -*- coding: utf-8 -*-
'''The document-collection wording: fast-track, and in the language the complainant reads.

Founder, 29 Sep:
  * not "we can move your case the same day" but "your case will be fast-tracked in our internal
    processes if you follow the correct and suggested steps for sending documents";
  * "if a Hindi user sees English communication they won't follow the process".

What these checks defend:

  * the fast-track line is on every document ask the BOT sends, and on the one STAFF send - from
    ONE copy, so the two can never tell a complainant different things;
  * it is about OUR internal process - never a promise about the insurer or the outcome;
  * the staff's ask is written in the reader's language, not English with Hindi document names;
  * and the pre-send check no longer warns "the message does not mention X" on every Hindi ask,
    which it did because it only looked for the English name.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_fast_track_copy.py
'''
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import biz_nidaan_wa_messages as m                  # noqa: E402
import biz_nidaan_doc_request as dr                 # noqa: E402
import biz_nidaan_doc_checklist as ck               # noqa: E402

FAILED = 0
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


LANGS = ("hinglish", "hi", "en")
CTX = {"doc_label": "X", "done": 1, "total": 4, "looks_like": "Y"}


async def main():
    print("\nThe bot's own messages\n")
    for l in LANGS:
        check("%-8s the ask carries the fast-track line" % l,
              m.FAST_TRACK[l] in m.compose("doc_reminder", l, CTX))
        for kind in ("doc_wrong", "doc_quality"):
            check("%-8s %-11s encourages instead of blaming" % (l, kind),
                  m.FAST_TRACK_RESEND[l] in m.compose(kind, l, CTX))
    for l in LANGS:
        for line in (m.FAST_TRACK[l], m.FAST_TRACK_RESEND[l]):
            check("%-8s it is about OUR internal process" % l,
                  ("internal" in line) or ("अंदरूनी" in line), line)
            check("%-8s and promises nothing about the insurer or the result" % l,
                  not re.search(r"insurer|insurance company|guarantee|approved|बीमा कंपनी|गारंटी|"
                                r"same day|isi din|उसी दिन", line, re.I), line)
    check("the Hindi lines are in Hindi",
          DEVANAGARI.search(m.FAST_TRACK["hi"]) and DEVANAGARI.search(m.FAST_TRACK_RESEND["hi"]))
    check("the Hinglish lines are in Roman script, as Hinglish readers read",
          not DEVANAGARI.search(m.FAST_TRACK["hinglish"]))

    print("\nThe ask staff send, in the reader's language\n")

    async def f_claim(cid):
        return {"claim_id": cid, "complainant_name": "Ram Kumar", "claim_type": "health"}

    async def f_docs(cid, ctype):
        return [{"key": "discharge", "en": "Discharge summary", "hi": "डिस्चार्ज समरी", "row": {}},
                {"key": "final_bill", "en": "Final bill", "hi": "फ़ाइनल बिल", "row": {}}]

    async def f_link(cid):
        return "https://example.invalid/upload"

    lang_now = {"v": "hi"}

    async def f_lang(cid, claim):
        return lang_now["v"]

    dr._claim = f_claim
    dr._upload_link = f_link
    dr._lang_for = f_lang
    ck.effective_docs = f_docs

    msgs = {}
    for l in LANGS:
        lang_now["v"] = l
        msgs[l] = await dr.draft_message(9, ["discharge", "final_bill"], kind="request")

    hi = msgs["hi"]
    first_lines = "\n".join(hi.split("\n")[:3])
    check("a Hindi reader's ask OPENS in Hindi", DEVANAGARI.search(first_lines)
          and "To take your claim" not in hi, first_lines)
    check("...names the documents in Hindi", "डिस्चार्ज समरी" in hi)
    check("...and the link line and sign-off are Hindi too",
          "Send them here" not in hi and "— NidaanPartner टीम" in hi, hi[-200:])
    check("the Hinglish ask is Hinglish", "aage badhane" in msgs["hinglish"], msgs["hinglish"][:200])
    check("the English ask is unchanged in meaning",
          "To take your claim NP-9 forward" in msgs["en"], msgs["en"][:200])
    for l in LANGS:
        check("%-8s the staff ask carries the SAME fast-track line as the bot" % l,
              m.FAST_TRACK[l] in msgs[l])
    for kind in ("nudge", "rerequest"):
        lang_now["v"] = "hi"
        t = await dr.draft_message(9, ["discharge"], kind=kind)
        check("a Hindi %-9s is Hindi from the first line" % kind,
              DEVANAGARI.search(t.split("\n")[2]), t.split("\n")[2])

    print("\nThe pre-send check reads Hindi names\n")

    async def f_recipients(cid):
        return [{"role": "complainant", "label": "Complainant", "name": "Ram",
                 "phone": "9000000000", "email": "", "missing": [], "kind": "to",
                 "source": "claim"}]

    dr.recipients = f_recipients
    pv = await dr.preview(9, doc_keys=["discharge", "final_bill"], message=hi,
                          channels=["whatsapp"])
    check("a Hindi ask naming the documents in Hindi is NOT told it forgot them",
          not any("does not mention" in w for w in pv.get("warnings") or []),
          pv.get("warnings"))
    pv = await dr.preview(9, doc_keys=["discharge", "final_bill"], message="please send papers",
                          channels=["whatsapp"])
    check("...while a message that names nothing still IS warned",
          any("does not mention" in w for w in pv.get("warnings") or []), pv.get("warnings"))

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
