# -*- coding: utf-8 -*-
'''A splitter job is not readable just because you are staff.

Until 28 Sep the four docsplit routes asked only "are you signed in as staff?" and three of them
then loaded a job by id. So any staff member could read any other staff member's uploaded
documents - and an upload here is a stranger's hospital file, often the whole bundle.

The ids are random, which is not the same as authorised. Ids reach logs, browser history,
screenshots and pasted messages; "hard to guess" has never been a permission model. This is the
same fault claim ids had before biz_nidaan_claim_authz, fixed the same way.

Read from the SOURCE rather than by starting a server, for the same reason as the other route
checks in this repo: the guard has to be visible at the route. A test that drives HTTP would pass
just as happily with the authorisation buried three calls deep, where the next person deletes it
without realising what it was.

What these checks defend:

  * every route that loads a job resolves it through the owner check, not by id alone;
  * the staff gate stays WRITTEN AT THE ROUTE. Hiding it inside the helper made the route census
    read these routes as having no staff gate at all, which is how a hole becomes invisible;
  * refusal is 404, never 403 - a 403 confirms the id is real and belongs to somebody, turning
    the endpoint into a way to find out whose uploads exist;
  * upload asks before pushing anybody's fourth job out;
  * closing a job archives it, and nothing in these routes deletes.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_docsplit_routes.py
'''
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = 0


def _safe(text) -> str:
    """Printable on a Windows console too.

    The details here are snippets of source, which contain arrows and rupee signs. On a cp1252
    console printing one raises UnicodeEncodeError and kills the run - so a failing test reported
    three findings and then died, which is the shape that has hidden real faults twice today.
    """
    s = str(text)
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return s.encode(enc, "replace").decode(enc, "replace")
    except Exception:  # noqa: BLE001
        return s.encode("ascii", "replace").decode("ascii")


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + _safe(detail))


APPS = ["sarathi_biz.py", "nidaan_app.py"]


def route_body(src, verb, path):
    """The text of one route handler, up to the next decorator."""
    pat = r'@app\.%s\("%s"\)(.*?)(?=\n@app\.)' % (verb, re.escape(path))
    m = re.search(pat, src, re.S)
    return m.group(1) if m else ""


LOADERS = [
    ("get", "/nidaan/ops/api/docsplit/{job}/thumb/{page}"),
    ("post", "/nidaan/ops/api/docsplit/{job}/export"),
    ("get", "/nidaan/ops/api/docsplit/{job}/pdf"),
]

for app in APPS:
    if not os.path.exists(app):
        continue
    src = io.open(app, encoding="utf-8").read()
    print("\n%s\n" % app)

    for verb, path in LOADERS:
        body = route_body(src, verb, path)
        name = path.split("/")[-1]
        check("%-12s resolves the job through the owner check" % name,
              "_docsplit_job(" in body, body[:160] or "ROUTE NOT FOUND")
        check("%-12s still writes its staff gate at the route" % name,
              "_require_staff(request)" in body,
              "the route census cannot see a gate hidden inside a helper")
        # Both positions must be REAL. find() returns -1 when absent, and -1 < anything, so the
        # obvious ordering test passed happily on a route with no check at all.
        at_check = body.find("_docsplit_job(")
        at_load = body.find("docsplit.load_job(")
        check("%-12s does not load by id alone" % name,
              at_check >= 0 and at_load >= 0 and at_check < at_load,
              "check at %d, load at %d - the check must exist AND come first"
              % (at_check, at_load))

    # The helper itself: refusal is 404, and it takes a staff row, not a request.
    m = re.search(r"async def _docsplit_job\(job: str, staff: dict\)(.*?)(?=\n@app\.|\nasync def )",
                  src, re.S)
    helper = m.group(1) if m else ""
    check("the owner check exists and takes a staff row", bool(helper))
    # The status CODE, not the number anywhere: the docstring explains why 403 is wrong, and
    # matching on a bare "403" failed on the sentence saying not to use it.
    check("...and refuses with 404, never 403",
          "status_code=404" in helper and "status_code=403" not in helper, helper[-200:])
    check("...and asks biz_nidaan_doc_store, which fails closed",
          "biz_nidaan_doc_store" in helper and "job_for(" in helper)

    up = route_body(src, "post", "/nidaan/ops/api/docsplit/upload")
    check("upload asks before pushing a fourth job out",
          "room_for_a_job" in up and "inbox_full" in up, up[:160] or "NOT FOUND")
    check("...and records who the job belongs to", "create_job(" in up)
    check("...and does not archive anything itself", "archive_job" not in up,
          "the oldest goes only when somebody presses a button")

    # A rule changes what EVERY staff member sees on every future file, so teaching one is an
    # admin decision. The route census cannot see this: the route's own guard is still staff:any
    # (correcting a page is anybody's work) and the restriction is a condition inside. Without
    # this check it would be unguarded in practice the moment somebody tidied the line away.
    rt = route_body(src, "post", "/nidaan/ops/api/docsplit/{job}/retype")
    check("teaching a rule is admin-only",
          "body.teach and" in rt and "sub_super_admin" in rt,
          "any staff member could otherwise make a rule for the whole team")
    check("...while correcting a page stays open to anyone",
          "_require_staff(request)" in rt,
          "the correction is their own work on their own job")

    close = route_body(src, "post", "/nidaan/ops/api/docsplit/{job}/close")
    check("closing a job archives it", "archive_job(" in close, close[:160] or "NOT FOUND")
    check("...and is written down in the ops audit", "_ops_audit" in close)

    inbox = route_body(src, "get", "/nidaan/ops/api/docsplit/jobs")
    check("the inbox lists only this person's jobs",
          "list_jobs(staff" in inbox.replace('"', "").replace("'", ""),
          inbox[:160] or "NOT FOUND")

    # Nothing in the splitter routes may delete.
    for verb, path in LOADERS + [("post", "/nidaan/ops/api/docsplit/upload"),
                                 ("post", "/nidaan/ops/api/docsplit/{job}/close")]:
        b = route_body(src, verb, path)
        if "discard_job_file" in b or re.search(r"\bos\.remove\b|\bshutil\.rmtree\b", b):
            check("%s %s deletes nothing" % (verb.upper(), path), False, "found a removal")
    check("no splitter route removes files", True)

print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
sys.exit(1 if FAILED else 0)
