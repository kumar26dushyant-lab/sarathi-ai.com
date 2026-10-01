# -*- coding: utf-8 -*-
"""The Sarathi app carries no NidaanPartner route.

1 Oct: the split surface had not been regenerated since 30 Sep, so `extract-app.py --sarathi`
kept every Nidaan route added since inside sarathi_app.py. They checked the host and answered 404
there - but a route in the wrong product is how a gate eventually goes missing. Regenerate with
`npm run gen:apps` (surface first, then both apps); this check fails if one slips through.

    py -3.13 deploy/verify-split-leak.py
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = io.open(os.path.join(ROOT, "sarathi_app.py"), encoding="utf-8").read()
leaks = re.findall(r'@app\.(?:get|post|put|patch|delete)\(\s*"(/nidaan/[^"]*)"', src)
print(("  OK   " if not leaks else "  NO   ") + "sarathi_app.py has no /nidaan/ route (%d found)" % len(leaks))
for p in leaks[:20]:
    print("         " + p)
sys.exit(1 if leaks else 0)
