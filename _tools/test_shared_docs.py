# -*- coding: utf-8 -*-
'''A signed-in staff member can open a shared document. A stranger cannot.

Founder, 29 Sep, opening nidaanpartner.com/sop-documents while signed in to ops: *"sop page is
not working"* - he got the share-link refusal.

THE CAUSE, and it had been true since the first shared document. `_get_staff_from_request` reads
ONLY the `Authorization: Bearer` header. The ops token lives in localStorage and is attached by
JavaScript on API calls, so a browser opening a page in a tab sends nothing - a signed-in staff
member looked exactly like a stranger. The docstring promised "or directly for a signed-in staff
session" the whole time, which is the part that makes this worth a test: the code SAID it worked.

What these checks defend:

  * without a key the route serves a LOADER, not a refusal - the loader uses the token already on
    this origin;
  * the gate did not move to the browser. The content endpoint checks the token on the server,
    and refuses an unknown document;
  * the token is never put in the URL, where it would reach logs, history and referrer headers;
  * a read is recorded for a signed-in person on BOTH paths, and never for the share key, where
    there is no honest name to attach;
  * and the refusal a stranger sees still tells them what to do.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_shared_docs.py
'''
import ast
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SRC = io.open("sarathi_biz.py", encoding="utf-8").read()


def body_of(name):
    m = re.search(r"async def %s\(.*?(?=\n@app\.|\nasync def |\ndef )" % name, SRC, re.S)
    return m.group(0) if m else ""


# ── the loader ───────────────────────────────────────────────────────────────
print("\nWhat a browser gets without a share key\n")

i = SRC.index("_DOC_LOADER_HTML = ")
seg = SRC[i:]
loader = ast.parse(seg[:seg.index("\n\n\n@app.get")]).body[0].value.value

check("there is a loader at all", len(loader) > 300)
check("it reads the ops token already on this origin",
      "localStorage.getItem(\"nidaan_ops_token\")" in loader, loader[:120])
check("...and sends it as a header, never in the URL",
      '"Authorization": "Bearer " + t' in loader
      and not re.search(r"\?k=\"\s*\+\s*t|token=\"\s*\+\s*t", loader),
      "a token in a URL reaches logs, history and referrer headers")
check("...to the authenticated content endpoint",
      "/nidaan/ops/api/doc/" in loader)
check("no token means the stranger message, not a broken page",
      "if (!t) { refuse(); return; }" in loader)
check("a refused fetch also shows it", loader.count("refuse()") >= 3, loader.count("refuse()"))
check("the message tells them what to do",
      "sign in to ops" in loader and "?k=" in loader)

served = body_of("_serve_shared_doc")
check("the route serves the loader instead of a 403",
      "_DOC_LOADER_HTML" in served and "status_code=200" in served, served[-300:])

# ── the gate did NOT move into the browser ───────────────────────────────────
print("\nWhere the decision is actually made\n")

content = body_of("ops_doc_content")
check("the content endpoint exists", bool(content))
check("...and requires a staff session on the SERVER",
      "_require_staff(request)" in content,
      "the loader is convenience; this is the gate")
check("...and refuses a document that is not in the registry",
      "if slug not in _DOC_KEYS" in content)
check("...and is Nidaan-host only", "_is_nidaan_host(request)" in content)
check("...and cannot be reached with a share key instead",
      "k" not in re.findall(r"async def ops_doc_content\(([^)]*)\)", SRC)[0],
      "the key path is separate; this one is staff-only")

# ── who read it ──────────────────────────────────────────────────────────────
print("\nRecording who read it\n")

check("a read is recorded on the staff path",
      'doc.read' in content and "_actor_label" in content)
check("...and on the share-key path too, when the reader is signed in",
      'doc.read' in served)
check("...but never with an invented name",
      "_get_staff_from_request(request)" in served and "if _who:" in served,
      "somebody on the share key is not signed in - there is no honest name")

readers = body_of("ops_doc_readers")
check("there is a way to see who has read what", bool(readers))
check("...restricted to admins", '_require_staff(request, "sub_super_admin")' in readers)
check("...reading the real audit columns",
      "target_id" in readers and "entity_id" not in readers,
      "the audit table has target_id; entity_id would silently return nothing")

print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
sys.exit(1 if FAILED else 0)
