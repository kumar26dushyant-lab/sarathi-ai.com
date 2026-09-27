# -*- coding: utf-8 -*-
"""Which SHARED functions reach into Sarathi code, and can a Nidaan path ever get there?

Found while computing what NidaanPartner needs to run. Shared modules - biz_database,
biz_payments, biz_marketing - import Sarathi modules LAZILY, inside function bodies. At import
time they look independent. At run time they are not.

A lazy import is not a safe import. It is a dependency that has been moved from where you would
see it to where you would not, and it fails on the day the function is called - which, after the
split, is the day a Nidaan code path reaches a function that needs a module Nidaan no longer
ships.

So this names, for every shared module, the exact FUNCTIONS that reach into Sarathi - so each one
can be checked against whether Nidaan calls it, rather than assumed harmless because nothing
broke at import.

    py -3.13 deploy/lazy-crossings.py
"""
import ast
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "deploy", "lazy-crossings.json")

SARATHI = {"biz_bot", "biz_reminders", "biz_nurture", "biz_tenant",
           "biz_sarathi_whatsapp", "biz_sarathi_tgcrm", "biz_bot_manager"}


def nidaan_owned(fname: str) -> bool:
    return fname.startswith(("biz_nidaan", "biz_claimshield"))


def main() -> int:
    files = sorted(f for f in os.listdir(ROOT) if f.endswith(".py"))
    crossings = {}     # file -> {func: [sarathi modules]}
    for f in files:
        if f.startswith("_") or f in ("sarathi_biz.py",):
            continue
        try:
            tree = ast.parse(io.open(os.path.join(ROOT, f), encoding="utf-8",
                                     errors="ignore").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            hits = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Import):
                    for a in n.names:
                        if a.name.split(".")[0] in SARATHI:
                            hits.add(a.name.split(".")[0])
                elif isinstance(n, ast.ImportFrom) and n.module:
                    if n.module.split(".")[0] in SARATHI:
                        hits.add(n.module.split(".")[0])
            if hits:
                crossings.setdefault(f, {})[node.name] = sorted(hits)

    # Does anything Nidaan owns call these functions by name?
    nidaan_src = ""
    for f in files:
        if nidaan_owned(f):
            nidaan_src += io.open(os.path.join(ROOT, f), encoding="utf-8",
                                  errors="ignore").read()

    print("\nShared functions that reach into Sarathi code\n")
    risky, safe = [], []
    for f, funcs in sorted(crossings.items()):
        for fn, mods in sorted(funcs.items()):
            called = ("%s(" % fn) in nidaan_src
            (risky if called else safe).append((f, fn, mods, called))

    if risky:
        print("  !! CALLED BY NIDAAN CODE - these must be resolved before Nidaan ships alone:\n")
        for f, fn, mods, _ in risky:
            print("     %-26s %-34s needs %s" % (f, fn + "()", ", ".join(mods)))
        print()
    else:
        print("  No Nidaan module calls any of them by name.\n")

    print("  Reach into Sarathi but are NOT called from Nidaan code (%d):\n" % len(safe))
    for f, fn, mods, _ in safe[:28]:
        print("     %-26s %-34s needs %s" % (f, fn + "()", ", ".join(mods)))
    if len(safe) > 28:
        print("     ...and %d more" % (len(safe) - 28))

    print("\n  NOTE: 'not called by name' is good evidence, not proof - a call could be")
    print("  indirect, through sarathi_biz.py, or by getattr. Each one still gets a guard")
    print("  that fails loudly rather than silently when the module is absent.")

    io.open(OUT, "w", encoding="utf-8", newline="").write(json.dumps(
        {"risky": [[f, fn, m] for f, fn, m, _ in risky],
         "safe": [[f, fn, m] for f, fn, m, _ in safe]}, indent=1, sort_keys=True))
    print("\nwrote %s" % OUT)
    return 1 if risky else 0


sys.exit(main())
