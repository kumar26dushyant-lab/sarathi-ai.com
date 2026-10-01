# -*- coding: utf-8 -*-
'''A team member can only open, edit, comment on or mark won the CRM leads they own or created.

Found 1 Oct: the lead LIST was filtered by owner, but the record routes were not - any team member
could read or change any lead by guessing its number (CLAUDE.md rule 3: authorisation on the
record id). The web app needs FastAPI, so this reads the routes' source and runs the rule itself.

    py -3.14 _tools/test_crm_authz.py
'''
import asyncio
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + str(detail))


def route(path_re):
    m = re.search(r'@app\.\w+\("' + path_re + r'"\)\n(?:@[^\n]*\n)*async def (\w+)', SRC)
    if not m:
        return ""
    body = SRC[m.start():]
    return body[:body.index("\n@app.", 10)]


for name, rx in (("open", r"/nidaan/ops/api/crm/leads/\{lead_id\}"),
                 ("comment", r"/nidaan/ops/api/crm/leads/\{lead_id\}/comment"),
                 ("mark won", r"/nidaan/ops/api/crm/leads/\{lead_id\}/convert")):
    body = route(rx)
    check("%s a lead: checks who is asking first" % name, "_crm_lead_for(staff, lead_id)" in body, body[:200])
patch = SRC[SRC.index('@app.patch("/nidaan/ops/api/crm/leads/{lead_id}")'):]
patch = patch[:patch.index("\n@app.", 10)]
check("edit a lead: checks who is asking first", "_crm_lead_for(staff, lead_id)" in patch)

# run the rule itself, lifted out of the app
fn = SRC[SRC.index("async def _crm_lead_for("):]
fn = fn[:fn.index("\n\n\n")]


class HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        self.status_code = status_code


LEAD = {"lead_id": 7, "owner_staff_id": 11, "created_by_staff_id": 12}


class _Crm:
    @staticmethod
    async def get_lead(lid):
        return dict(LEAD) if lid == 7 else None


sys.modules["biz_nidaan_crm"] = _Crm
ns = {"HTTPException": HTTPException}
exec(fn, ns)


async def who(staff, lid=7):
    try:
        await ns["_crm_lead_for"](staff, lid)
        return "ok"
    except HTTPException as e:
        return e.status_code


async def main():
    check("the owner may", await who({"staff_id": 11, "role": "team_member"}) == "ok")
    check("whoever created it may", await who({"staff_id": 12, "role": "team_member"}) == "ok")
    check("another team member may not - and sees 'not found', not 'forbidden'",
          await who({"staff_id": 99, "role": "team_member"}) == 404)
    check("an admin may", await who({"staff_id": 99, "role": "sub_super_admin"}) == "ok")
    check("no such lead is the same 404", await who({"staff_id": 11, "role": "team_member"}, 8) == 404)

asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
