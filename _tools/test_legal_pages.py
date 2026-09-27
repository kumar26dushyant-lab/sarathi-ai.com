# -*- coding: utf-8 -*-
'''Each site serves its OWN privacy policy and terms.

Found 26 Sep 2026 during the DPDP assessment. `/privacy` and `/terms` had no host check, so

    https://nidaanpartner.com/privacy  ->  "Privacy Policy - Sarathi-AI Business Technologies"

A person on a legal-services site, about to hand over their medical records, was told a
DIFFERENT COMPANY decides what happens to their data. The correct Nidaan pages existed at
/nidaan/privacy the whole time. Nothing sent anyone there, and the obvious address won.

A privacy policy names the party accepting the legal obligation. Serving the wrong one is not a
broken link - it is a false statement about who is responsible, made to the people with the most
sensitive data in the system.

    py -3.13 _tools/test_legal_pages.py
'''
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = 0
src = io.open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


def body(route):
    i = src.index('@app.get("%s", response_class=HTMLResponse)' % route)
    return src[i:src.index("@app.get", i + 10)]


print("\nWhose policy does each site serve\n")

for route, nidaan_file, sarathi_file in (("/privacy", "nidaan_privacy.html", "privacy.html"),
                                         ("/terms", "nidaan_terms.html", "terms.html")):
    b = body(route)
    check("%-9s asks WHICH site is being served" % route, "_is_nidaan_host(request)" in b)
    # /privacy reaches its page through a helper that names the current Grievance Officer, so
    # the file may be one step away. Follow the call rather than requiring it inline - a check
    # that forbids refactoring is a check that gets deleted.
    reached = nidaan_file in b
    if not reached:
        m = re.search(r"return await (_\w+)\(request\)", b)
        if m and ("async def %s" % m.group(1)) in src:
            h = src[src.index("async def %s" % m.group(1)):]
            reached = nidaan_file in h[:3000]
    check("%-9s   -> Nidaan gets the Nidaan page" % route, reached, b[:200])
    check("%-9s   -> Sarathi still gets its own" % route, sarathi_file in b)
    check("%-9s   and the host check comes FIRST" % route,
          b.index("_is_nidaan_host") < b.index(sarathi_file),
          "the Sarathi file must not be reachable before the check")

# The pages themselves must not contradict each other about who the company is.
np = io.open(os.path.join(ROOT, "static", "nidaan_privacy.html"), encoding="utf-8").read()
sp = io.open(os.path.join(ROOT, "static", "privacy.html"), encoding="utf-8").read()
check("the Nidaan policy does not name the Sarathi entity",
      "Sarathi-AI Business Technologies" not in np)
check("...and it names an LLP as the data fiduciary", "LLP" in np)
check("...and gives somewhere to complain", re.search(r"[\w.+-]+@[\w.-]+", np) is not None)
check("the Sarathi policy does not name Nidaan either", "Nidaan" not in sp)

# ── the entity, the office, and who to write to ─────────────────────────────
print()
LLP = "Nidaan Legal India LLP"
MAIL = "enquiries@nidaanlegalindia.com"
nt = io.open(os.path.join(ROOT, "static", "nidaan_terms.html"), encoding="utf-8").read()
for name, page in (("privacy", np), ("terms", nt)):
    check("%-7s names the registered entity" % name, LLP in page)
    check("%-7s   and NOT the old one" % name, "The Legal Consultants LLP" not in page)
    check("%-7s   publishes the registered office" % name, "452009" in page)
    check("%-7s   and a phone number" % name, "95844 68804" in page)
    check("%-7s   routes legal contact to the LLP, not the product inbox" % name, MAIL in page)
    check("%-7s   says NidaanPartner is the technology wing" % name,
          "GoLuQ.com Digital Consultancy" in page)
check("privacy names a Grievance Officer route", "Grievance Officer" in np)
check("...with a response time somebody can be held to",
      "72 hours" in np and "30 days" in np)
check("terms names Indore as the jurisdiction", "Indore" in nt)

# A company name spelled two ways is not a name.
import glob
wrong = [os.path.basename(f) for f in glob.glob(os.path.join(ROOT, "static", "*.html"))
         if "The Legal Consultants LLP" in io.open(f, encoding="utf-8").read()]
check("no page anywhere still shows the old entity name", not wrong, wrong)
bad = [os.path.basename(f) for f in glob.glob(os.path.join(ROOT, "static", "*.html"))
       if re.search(r"Digital Consultant(?!cy)", io.open(f, encoding="utf-8").read())]
check("the developer is 'Digital Consultancy' on every page", not bad, bad)

print("\n" + ("%d failed" % FAILED if FAILED
              else "each site answers for itself, and the right company answers for Nidaan"))
sys.exit(1 if FAILED else 0)
