# -*- coding: utf-8 -*-
'''A named Grievance Officer, changeable without a deploy - and safely.

DPDP expects a PERSON named on the privacy policy, not a role. Founder, 27 Sep: keep it
editable from ops so the name can be updated when people change.

Two things are being protected here and only one of them is obvious:

  1. the page must never print "Grievance Officer:" with nothing after it. An empty name reads
     as a vacant role, which under DPDP is a worse public statement than naming the office.
  2. THE NAME IS RENDERED INTO A PUBLIC PAGE. A super admin typing a script tag into a settings
     field would put it on the privacy policy of a site that holds medical records. It is
     escaped, and that is asserted - not assumed because the person typing is trusted.

    py -3.13 _tools/test_grievance_officer.py
'''
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILED = 0
biz = io.open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
nid = io.open(os.path.join(ROOT, "biz_nidaan.py"), encoding="utf-8").read()
helper = biz[biz.index("async def _nidaan_privacy_with_officer"):
             biz.index('@app.get("/privacy"')]
setter = biz[biz.index("async def ops_grievance_set"):]


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


print("\nNaming the Grievance Officer\n")

check("the name is a setting, not baked into the page",
      '"grievance_officer_name": ""' in nid)
check("...with the LLP's own contact as the default, so it is never contactless",
      "enquiries@nidaanlegalindia.com" in nid)

check("the published page is rendered with whoever is named now", "get_ops_setting" in helper)
check("...read at SERVE time, so a change shows without a deploy",
      "nidaan_privacy.html" in helper and "read_text" in helper)
check("an empty name falls back to naming the office, never prints blank",
      "if name else" in helper and "Grievance Officer</b>, Nidaan Legal India LLP" in helper)
check("a failure to read the setting still serves the page",
      "except Exception" in helper)

# The one that matters and is easy to skip.
check("THE NAME IS ESCAPED before it reaches the public page",
      "html_escape(name)" in helper)
check("...and so are the email and phone",
      "html_escape(mail)" in helper and "html_escape(phone)" in helper)

check("only a super admin may name somebody",
      '_require_staff(request, "super_admin")' in setter[:600])
check("...the email is sanity-checked", '"@" not in email' in setter)
check("...and every change is in the audit trail",
      '"grievance_officer.set"' in setter)
check("...naming who was named, and by whom",
      "named %s" in setter or "named %s <%s>" in setter)
check("the response says where it will show up", 'shown_on' in setter)

check("a super admin can read back who is named now",
      '@app.get("/nidaan/ops/api/grievance-officer")' in biz)
check("the response times are still promised on the page",
      "72 hours" in helper and "30 days" in helper)

print("\n" + ("%d failed" % FAILED if FAILED
              else "a person can be named, changed without a deploy, and cannot inject a page"))
sys.exit(1 if FAILED else 0)
