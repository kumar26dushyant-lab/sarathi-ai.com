# -*- coding: utf-8 -*-
"""One list of claim statuses, agreed by every screen that shows one.

`review_delivered` is the status 115 of our claims are in - the majority - and on 22 Sep 2026 it
appeared in NO dropdown, NO pill stylesheet and NO board column list. It had been added to the
server's tuple and to nothing else, so it rendered as a bare lowercase word and the founder read
it as a colour bug. It was not a colour bug. It was four hand-kept copies of one list.

So the list is checked here instead of remembered:

  - biz_nidaan.CLAIM_STATUS_PICKLIST is the source. Every key in it must be accepted by
    CLAIM_STATUSES, or the server would refuse a status its own screens offer.
  - nidaan_ops.html's CLAIM_STATUS_LIST must match it exactly, key for key and in order.
  - every status, offered or retired, must have a pill rule on both screens that show pills -
    otherwise it renders unstyled, which is the bug this file exists for.
  - no pill may carry a literal colour. A hex works in one mode and washes out in the other;
    that is the founder's standing rule and it is how .s-in_negotiation came to be invisible in
    light mode.
  - the subscriber dashboard must label every status in BOTH languages. A word that does not
    switch with the language selector is the leftover string he has asked twice not to ship.

    py -3.13 deploy/verify-claim-statuses.py
"""
import glob
import io
import os
import re
import sys

OPS = io.open("static/nidaan_ops.html", encoding="utf-8").read()
DASH = io.open("static/nidaan_dashboard.html", encoding="utf-8").read()
# The pill colours live here now - one set for both screens, rather than a copy each.
DESIGN = io.open("static/nidaan_design.css", encoding="utf-8").read()

# Read biz_nidaan as TEXT, not by importing it. Importing drags in aiosqlite and a database
# connection, which a checker that only compares two lists has no business needing - and the
# check would then only run on a machine with the app's dependencies installed.
import ast  # noqa: E402

_SRC = ast.parse(io.open("biz_nidaan.py", encoding="utf-8").read())


def _const(name):
    for node in _SRC.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


class nidaan:  # noqa: N801  - stands in for the module, same attribute names
    CLAIM_STATUSES = _const("CLAIM_STATUSES") or ()
    CLAIM_STATUS_PICKLIST = _const("CLAIM_STATUS_PICKLIST") or ()
    CLAIM_STATUS_RETIRED = _const("CLAIM_STATUS_RETIRED") or ()

P = F = 0


def check(label, ok, detail=""):
    global P, F
    if ok:
        P += 1
        print("  OK   " + label)
    else:
        F += 1
        print("  NO   " + label + (("\n         " + str(detail)) if detail else ""))


def js_list(src, name):
    """Pull ['key','Label'] pairs out of a JS array literal by name."""
    m = re.search(r"const %s = \[(.*?)\n\];" % re.escape(name), src, re.S)
    if not m:
        return None
    return re.findall(r"\['([a-z_]+)'\s*,\s*'([^']*)'\]", m.group(1))


print("\nOne list of claim statuses, agreed everywhere\n")

PICK = list(nidaan.CLAIM_STATUS_PICKLIST)
RETIRED = list(nidaan.CLAIM_STATUS_RETIRED)
check("the server has a picklist to be the source of (%d statuses)" % len(PICK), len(PICK) >= 5)

# Offering a status the server would refuse is a dropdown that throws when used.
unknown = [k for k, _ in PICK if k not in nidaan.CLAIM_STATUSES]
check("every offered status is one the server accepts", not unknown, unknown)
unknown_r = [k for k in RETIRED if k not in nidaan.CLAIM_STATUSES]
check("every retired status is still accepted", not unknown_r, unknown_r)

ops_list = js_list(OPS, "CLAIM_STATUS_LIST")
check("the ops page has its list", ops_list is not None)
if ops_list is not None:
    check("the ops page offers exactly the server's statuses, in order",
          [k for k, _ in ops_list] == [k for k, _ in PICK],
          "page: %s\n         server: %s" % ([k for k, _ in ops_list], [k for k, _ in PICK]))
    check("and the same words for them",
          [l for _, l in ops_list] == [l for _, l in PICK],
          "page: %s" % [l for _, l in ops_list])

ops_retired = js_list(OPS, "CLAIM_STATUS_RETIRED")
check("the ops page knows the retired ones too",
      ops_retired is not None and sorted(k for k, _ in ops_retired) == sorted(RETIRED),
      ops_retired)

# A status with no pill rule renders as a bare word. That is the whole bug.
ALL = [k for k, _ in PICK] + RETIRED
# A selector may be grouped - `.s-closed,.s-withdrawn{...}` - so the name is followed by a comma
# as often as by a brace. Looking only for the brace reported a rule that was there.
missing = [k for k in ALL
           if not re.search(r"\.s-" + re.escape(k) + r"\b\s*[,{]", DESIGN)]
check("every status has a pill rule in the shared stylesheet", not missing, missing)

# One set of rules only helps the pages that load it, at the version that carries it. Cloudflare
# holds /static for seven days, so a page still asking for an old ?v= shows the old colours to
# every browser that has been there before - shipped and invisible.
ver = re.findall(r"nidaan_design\.css\?v=(\d+)", OPS + DASH)
pages = sorted(glob.glob("static/nidaan_*.html"))
stale = []
for f in pages:
    src = io.open(f, encoding="utf-8").read()
    if "nidaan_design.css" not in src:
        continue
    for v in re.findall(r"nidaan_design\.css\?v=(\d+)", src):
        if not ver or v != ver[0]:
            stale.append("%s -> ?v=%s" % (os.path.basename(f), v))
check("every page asks for the same stylesheet version", not stale, stale)

# No page may keep a private copy - that is how the two screens drifted apart in the first place.
dup = [n for n, src in (("ops", OPS), ("dashboard", DASH))
       if re.search(r"\.s-intimated\b\s*[,{]", src)]
check("no page keeps its own copy of the pill colours", not dup, dup)

# A literal colour reads in one mode and washes out in the other.
for name, src in (("ops", OPS), ("dashboard", DASH), ("shared stylesheet", DESIGN)):
    bad = []
    for k in ALL:
        for m in re.finditer(r"\.s-%s\b[^{}\n]*\{([^}]*)\}" % k, src):
            for lit in re.findall(r"color:\s*(#[0-9a-fA-F]{3,8})", m.group(1)):
                bad.append("%s -> %s" % (k, lit))
    check("%s: no pill carries a literal colour" % name, not bad, bad)

# Both languages, or it is a leftover string.
en = re.search(r"const STATUS_LABELS = \{(.*?)\};", DASH, re.S)
hi = re.search(r"const STATUS_LABELS_HI = \{(.*?)\};", DASH, re.S)
check("the dashboard has both label sets", bool(en and hi))
if en and hi:
    miss_en = [k for k, _ in PICK if not re.search(r"\b%s\s*:" % k, en.group(1))]
    miss_hi = [k for k, _ in PICK if not re.search(r"\b%s\s*:" % k, hi.group(1))]
    check("every offered status has an English label", not miss_en, miss_en)
    check("every offered status has a Hindi label", not miss_hi, miss_hi)

# A case must not fall through to "intake" just because its status is new.
STATE = io.open("biz_nidaan_case_state.py", encoding="utf-8").read()
check("a raised query waits on the customer, not on us",
      'elif status == "review_query":' in STATE and 'stage, blocker = "review", "complainant"' in STATE)
check("an answered query comes back to us",
      '"review_query_resolved",\n                    "review_delivered"' in STATE
      or '"review_query_resolved"' in STATE)

print("\n%d checked, %d wrong" % (P + F, F))
sys.exit(1 if F else 0)
