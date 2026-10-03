# -*- coding: utf-8 -*-
"""Every Nidaan page that talks to the server loads the shared one-tap guard.

Founder, 2 Oct: "it's very basic thing to prevent multiple click/tap on a button, why you're
missing everytime creating a feature". Remembering per button failed, so it is not remembered: a
page that makes a request (fetch / XHR / checkout / Google sign-in) without
/static/nidaan_onetap.js fails this check, and the build with it.

    py -3.13 deploy/verify-onetap.py
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TALKS = re.compile(r"\bfetch\(|\bAPI\(|\bapi\(|XMLHttpRequest|Razorpay|accounts\.google")
bad = []
pages = sorted(glob.glob(os.path.join(ROOT, "static", "nidaan_*.html")))
for f in pages:
    t = io.open(f, encoding="utf-8").read()
    if TALKS.search(t) and "/static/nidaan_onetap.js" not in t:
        bad.append(os.path.basename(f))
guard = io.open(os.path.join(ROOT, "static", "nidaan_onetap.js"), encoding="utf-8").read()
# The last two keep file pickers and tick boxes working: without them the guard swallows the
# click a <label> sends on to its control (the Doc Splitter's dead "Choose file(s)", 3 Oct).
for must in ("addEventListener('click'", "XMLHttpRequest.prototype.send", "window.fetch = function", ".nd-working",
             "btn.tagName === 'LABEL'", "select, textarea, option"):
    if must not in guard:
        bad.append("nidaan_onetap.js lost: " + must)
for b in bad:
    print("  FAIL ", b)
print("  OK   every page that talks to the server loads the one-tap guard (%d pages)" % len(pages) if not bad
      else "%d problem(s)" % len(bad))
sys.exit(1 if bad else 0)
