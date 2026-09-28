# -*- coding: utf-8 -*-
"""Exactly which files does NidaanPartner need to run? Follow the imports and find out.

The plan said: edit sarathi_biz.py to remove Sarathi's 357 routes, leaving Nidaan behind.

That is backwards for the same reason the first draft was backwards. To remove Sarathi's routes
I must EDIT the 30,029-line file that is serving live claims and payments right now. The census
would catch a route that vanished, but it would catch it after the edit, and the founder's one
hard requirement is that NidaanPartner does not break.

So: do not edit the live file at all. BUILD THE NEW APP BESIDE IT, by copying only what Nidaan
needs into a new folder, verify it serves identically, and only then switch. The live app runs
untouched throughout, and if the extraction is wrong we find out in testing rather than in
production. That is the same copy-verify-switch rule already agreed for the 1.5 GB of documents,
applied to the code.

This script works out what "only what Nidaan needs" actually means, by following imports from the
Nidaan entry points rather than by trusting filenames. A file named for neither product that
Nidaan imports is a file Nidaan needs.

    py -3.13 deploy/nidaan-closure.py
"""
import ast
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "deploy", "nidaan-closure.json")

# Where Nidaan starts. sarathi_biz.py is deliberately absent - it is the file being split, and
# what Nidaan needs FROM it is the 462 routes plus 251 helpers that split-surface.py identified.
ENTRY = [
    "biz_nidaan.py", "biz_nidaan_telegram.py", "biz_nidaan_notifications.py",
    "biz_nidaan_pay_guard.py", "biz_nidaan_bot_docs.py", "biz_nidaan_bot_guard.py",
    "biz_nidaan_claim_access.py", "biz_nidaan_claim_authz.py", "biz_nidaan_doc_intake.py", "biz_nidaan_doc_checklist.py",
    "biz_claimshield.py", "biz_database.py",
]

SARATHI_ONLY = {"biz_bot.py", "biz_reminders.py", "biz_nurture.py", "biz_tenant.py",
                "biz_sarathi_whatsapp.py", "biz_sarathi_tgcrm.py"}


def imports_of(path: str) -> set:
    try:
        tree = ast.parse(io.open(path, encoding="utf-8", errors="ignore").read())
    except Exception:
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.add(a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module.split(".")[0])
    return out


def main() -> int:
    local = {f[:-3]: f for f in os.listdir(ROOT) if f.endswith(".py")}
    seen, queue = set(), [e for e in ENTRY if os.path.exists(os.path.join(ROOT, e))]
    edges = {}
    while queue:
        f = queue.pop()
        if f in seen:
            continue
        seen.add(f)
        mods = imports_of(os.path.join(ROOT, f))
        here = sorted(local[m] for m in mods if m in local)
        edges[f] = here
        for h in here:
            if h not in seen:
                queue.append(h)

    all_py = set(local.values())
    needed = sorted(seen)
    unneeded = sorted(all_py - seen)
    sarathi_pulled = sorted(SARATHI_ONLY & seen)

    print("\nWhat NidaanPartner actually needs\n")
    print("  python files in the repo : %d" % len(all_py))
    print("  reachable from Nidaan    : %d" % len(needed))
    print("  NOT needed by Nidaan     : %d" % len(unneeded))
    print()
    if sarathi_pulled:
        print("  !! Nidaan pulls in Sarathi-only modules - each needs a decision:")
        for f in sarathi_pulled:
            who = sorted(k for k, v in edges.items() if f in v)
            print("     %-30s imported by %s" % (f, ", ".join(who)))
        print()
    else:
        print("  Nidaan pulls in NO Sarathi-only module.")
        print()

    # Shared-by-name files that Nidaan needs - these get copied, not shared.
    shared = [f for f in needed
              if not f.startswith(("biz_nidaan", "biz_claimshield"))]
    print("  Files named for neither product that Nidaan needs (%d):" % len(shared))
    for i in range(0, len(shared), 3):
        print("     " + "".join("%-30s" % x for x in shared[i:i + 3]))
    print()
    print("  Not needed by Nidaan - these stay with Sarathi (%d):" % len(unneeded))
    for i in range(0, min(len(unneeded), 30), 3):
        print("     " + "".join("%-30s" % x for x in unneeded[i:i + 3]))
    if len(unneeded) > 30:
        print("     ...and %d more" % (len(unneeded) - 30))

    io.open(OUT, "w", encoding="utf-8", newline="").write(json.dumps(
        {"needed": needed, "unneeded": unneeded, "edges": edges,
         "sarathi_pulled": sarathi_pulled}, indent=1, sort_keys=True))
    print("\nwrote %s" % OUT)
    return 0


sys.exit(main())
