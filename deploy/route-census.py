# -*- coding: utf-8 -*-
"""Every route this app serves, written down - so one can never quietly stop existing.

Stage 0 of separating the two products. Founder, 27 Sep: NidaanPartner is live and critical,
Sarathi has no active users. So the split will be done by extracting SARATHI and leaving Nidaan
where it stands - but either way, 854 routes are about to be moved around, and the failure that
matters is not a crash.

A route that disappears does not error at deploy. It is simply gone, and nothing says so. You
find out when somebody says "the button does nothing" - possibly weeks later, possibly on a
payment path. That is invisible to every test that only checks what exists.

So this writes down what exists NOW, and afterwards compares. Missing is failure. New is fine.
Changed method or changed auth on an existing path is failure, because a route that stops
requiring a login is worse than one that disappeared.

    py -3.13 deploy/route-census.py --save      # before you touch anything
    py -3.13 deploy/route-census.py             # after every stage - and in the pre-commit set
"""
import hashlib
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS = os.path.join(ROOT, "deploy", "route-census.json")

# Files that may declare routes. A second app file appears here the day stage 2 lands.
SOURCES = ["sarathi_biz.py", "nidaan_app.py", "sarathi_app.py"]

# KNOWN BLIND SPOT, recorded rather than left to be discovered.
#
# This reads decorators, so it sees only routes declared with @app.get/@app.post. Routes
# registered in a LOOP are invisible to it - the shared-document pages (/bucket-flow,
# /claims-view, /doc-collect and the rest of _DOC_KEYS) are registered that way, and the
# extracted app proved it by having 9 routes this census does not know about.
#
# So: a dynamically registered route disappearing would NOT be caught here. Until that is
# fixed, the live check after each stage is what covers them - ask the running app for its
# route table, do not ask the source.

_DEC = re.compile(r"@app\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']")


def _guard_of(body: str) -> str:
    """What this route demands of a caller - recorded so a gate cannot quietly go missing."""
    bits = []
    if "_is_nidaan_host" in body:
        bits.append("nidaan-host")
    m = re.search(r'_require_staff\(request,\s*[\"\'](\w+)[\"\']', body)
    if m:
        bits.append("staff:" + m.group(1))
    elif "_require_staff(request)" in body:
        bits.append("staff:any")
    if "_require_admin" in body:
        bits.append("admin")
    if "limiter.limit" in body:
        bits.append("rate-limited")
    return ",".join(bits) or "open"


def collect() -> dict:
    out = {}
    for src in SOURCES:
        p = os.path.join(ROOT, src)
        if not os.path.exists(p):
            continue
        s = io.open(p, encoding="utf-8").read()
        for m in _DEC.finditer(s):
            method, path = m.group(1).upper(), m.group(2)
            # the decorator plus the function under it, up to the next decorator
            nxt = s.find("\n@app.", m.end())
            body = s[m.end():nxt if nxt > 0 else m.end() + 3000]
            fn = re.search(r"\n\s*async def (\w+)|\n\s*def (\w+)", body)
            out["%s %s" % (method, path)] = {
                "file": src,
                "func": (fn.group(1) or fn.group(2)) if fn else "?",
                "guard": _guard_of(body),
            }
    return out


def product(path: str) -> str:
    if path.startswith("/nidaan"):
        return "nidaan"
    if path.startswith("/api") or path.startswith("/tenant") or path.startswith("/agent"):
        return "sarathi"
    return "shared"


def main() -> int:
    now = collect()
    save = "--save" in sys.argv
    counts = {}
    for k in now:
        counts[product(k.split(" ", 1)[1])] = counts.get(product(k.split(" ", 1)[1]), 0) + 1

    if save or not os.path.exists(CENSUS):
        io.open(CENSUS, "w", encoding="utf-8", newline="").write(
            json.dumps(now, indent=1, sort_keys=True))
        print("\nWrote the census: %d routes" % len(now))
        for k in sorted(counts):
            print("   %-8s %d" % (k, counts[k]))
        print("\n%s" % CENSUS)
        print("\nThis is the 'before'. Run it again after every stage.")
        return 0

    was = json.loads(io.open(CENSUS, encoding="utf-8").read())
    gone = sorted(set(was) - set(now))
    added = sorted(set(now) - set(was))
    changed = sorted(k for k in set(was) & set(now)
                     if was[k]["guard"] != now[k]["guard"])

    print("\nRoutes: %d before, %d now" % (len(was), len(now)))
    for k in sorted(counts):
        print("   %-8s %d" % (k, counts[k]))

    bad = 0
    if gone:
        print("\n  !! %d ROUTE(S) NO LONGER EXIST - this is the failure that hides:" % len(gone))
        for k in gone[:25]:
            print("       %-52s was %s in %s" % (k, was[k]["guard"], was[k]["file"]))
        bad += len(gone)
    if changed:
        print("\n  !! %d ROUTE(S) CHANGED WHAT THEY DEMAND OF A CALLER:" % len(changed))
        for k in changed[:25]:
            print("       %-46s %s -> %s" % (k, was[k]["guard"], now[k]["guard"]))
        bad += len(changed)
    if added:
        print("\n  -- %d new route(s) - fine, listed so nothing appears unnoticed:" % len(added))
        for k in added[:15]:
            print("       %-52s %s" % (k, now[k]["guard"]))

    print("\n" + ("%d problem(s) - a route was lost or its gate moved" % bad if bad
                  else "every route still exists and still demands what it did"))
    return 1 if bad else 0


sys.exit(main())
