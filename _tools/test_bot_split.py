# -*- coding: utf-8 -*-
'''The doc splitter in the bot: one stack in, named pieces back, nothing saved.

Founder, 26 Sep, choosing the careful option over the fast one: split the PDF, send the pieces
back to be checked, and let the person attach the ones they want through the upload flow. A
wrong split that had written itself onto a real claim is unpicked by hand.

So the property that matters is a NEGATIVE one, and negatives are what nobody tests: the split
path must not reach a claim at all. No intake, no checklist, no claim id. It is checked here by
reading the handler and asserting the absence, because "it does not do X" is exactly the claim
that quietly stops being true when somebody adds a helpful feature later.

    py -3.14 _tools/test_bot_split.py
'''
import ast
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILED = 0
src = io.open(os.path.join(ROOT, "biz_nidaan_telegram.py"), encoding="utf-8").read()
handler = src[src.index("async def _handle_split_file("):src.index("async def send_document(")]


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


print("\nSplitting a mixed PDF\n")

check("the menu offers it", '"callback_data": "ds:start"' in src)
check("it waits for a file", '"a": "split_wait"' in src)
check("...and a file sent while waiting goes to the splitter, not the claim flow",
      'pend.get("a") == "split_wait"' in src
      and src.index('pend.get("a") == "split_wait"')
      < src.index('if pend.get("a") not in ("doc_wait", "doc_confirm")'))

# The negative that is the whole design.
check("the split path never reaches the document intake", "intake.accept" not in handler)
check("...never ticks a checklist", "mark_doc_received" not in handler
      and "doc_checklist" not in handler)
check("...and never takes a claim id", "claim_id" not in handler)

check("a photo is refused - you cannot split a photo",
      "if not doc:" in handler and "ds_pdf_only" in handler)
check("...and so is a non-PDF file", '.lower().endswith(".pdf")' in handler)
check("the rate limit still applies, because this is a Gemini call every time",
      '_g.allow(staff.get("staff_id"), "upload")' in handler)
check("...and the size gate runs before the AI does",
      handler.index("check_file(fname, data)") < handler.index("splitter.segment("))
check("a single-document PDF is not split, it is explained",
      "len(docs) <= 1" in handler and "ds_one_only" in handler)
check("a failure says what to do instead, and does not crash the flow",
      "ds_failed" in handler and "except Exception" in handler)
check("the pieces come back named and numbered, not as 'document (1)'",
      "caption=" in handler and 'd.get("name")' in handler)
check("...with the page range, so a wrong split is obvious at a glance", "p%s-%s" in handler)
check("it is written down", '_g.record(staff, "split"' in handler)
check("...and it hands them straight to the upload flow afterwards",
      '"callback_data": "dc:start"' in handler)
check("the pending flow is cleared at the end, so they are not stuck waiting",
      '_set_pending(staff["staff_id"], None)' in handler)

# sendDocument is new surface: check it is not silently ignoring failures.
sd = src[src.index("async def send_document("):src.index("async def _download_file(")]
check("sending a file back reports success or failure rather than assuming",
      "return (bool(j.get(\"ok\"))" in sd)
check("...and only counts the ones that actually went", "if ok:" in handler
      and "sent += 1" in handler)

# Both languages, parsed rather than grepped.
d = None
for n in ast.walk(ast.parse(src)):
    if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "_BOT_TXT":
        d = ast.literal_eval(n.value)
new_keys = [k for k in d if k.startswith("ds_") or k == "b_split"]
check("every new word exists in both languages", len(new_keys) == 7
      and all(d[k].get("en") and d[k].get("hi") for k in new_keys), new_keys)
check("...and the Hindi is really Devanagari, not English copied across",
      all(any("ऀ" <= ch <= "ॿ" for ch in d[k]["hi"]) for k in new_keys))

print("\n" + ("%d failed" % FAILED if FAILED
              else "it separates, it names, it hands them back - and it touches no claim"))
sys.exit(1 if FAILED else 0)
