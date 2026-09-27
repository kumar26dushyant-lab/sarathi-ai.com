# -*- coding: utf-8 -*-
"""Build nidaan_app.py from sarathi_biz.py by REMOVING what is provably Sarathi's.

Stage 2, done the safe way round.

The tempting build is additive: collect Nidaan's routes and helpers and assemble a new file from
them. That requires me to be right about every dependency, and anything I miss is a NameError at
some call site, weeks later, on a path nobody exercised in testing.

So this is subtractive instead. Start from a byte-for-byte copy of the file that works today, and
delete only the top-level nodes that are PROVABLY Sarathi's - a Sarathi route, or a helper that
no Nidaan route can reach. Everything else stays, including the 883 names no route reaches at
all, because keeping something unused costs a few kilobytes and dropping something needed costs
a feature.

Source order is preserved exactly. That matters more than it looks: Python executes a module top
to bottom, so anything defined before its first use still is, and any module-level side effect
still happens in the same order it does today.

The live sarathi_biz.py is NOT touched. This writes a new file, beside it, to be tested before
anything is switched.

    py -3.13 deploy/extract-nidaan-app.py
"""
import ast
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sarathi_biz.py")
SURFACE = os.path.join(ROOT, "deploy", "split-surface.json")
OUT = os.path.join(ROOT, "nidaan_app.py")


def main() -> int:
    src = io.open(SRC, encoding="utf-8").read()
    lines = src.split("\n")
    tree = ast.parse(src)
    surface = json.loads(io.open(SURFACE, encoding="utf-8").read())

    sarathi_routes = {r["func"] for r in surface["routes"] if r["product"] == "sarathi"}
    nidaan_routes = {r["func"] for r in surface["routes"] if r["product"] == "nidaan"}
    shared_routes = {r["func"] for r in surface["routes"] if r["product"] == "shared"}
    only_sarathi = set(surface["only_sarathi"])

    # What a Nidaan or shared route can reach must never be dropped, whatever else says.
    protected = set()
    for r in surface["routes"]:
        if r["product"] in ("nidaan", "shared"):
            protected |= set(r["reaches"])
    protected |= nidaan_routes | shared_routes

    drop_names = (sarathi_routes | only_sarathi) - protected

    # Which top-level nodes those names correspond to, and their line spans.
    spans, dropped = [], []
    for n in tree.body:
        # ONLY functions and classes are ever dropped. Module-level constants stay, always.
        #
        # The first run dropped SERVER_URL and SERVER_PORT - classified Sarathi-only because no
        # Nidaan route reached them directly - and produced twelve undefined names in code that
        # does use them. The original file has zero. A constant costs bytes to keep and a
        # NameError to drop, so the trade is not close.
        name = None
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = n.name
        if not name or name not in drop_names:
            continue
        start = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])
        # take any comment block immediately above with it
        i = start - 2
        while i >= 0 and (lines[i].lstrip().startswith("#") or not lines[i].strip()):
            if lines[i].strip() and not lines[i].lstrip().startswith("#"):
                break
            i -= 1
        spans.append((i + 2, n.end_lineno))
        dropped.append(name)

    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    keep = []
    cut = set()
    for s, e in merged:
        cut |= set(range(s, e + 1))
    for i, line in enumerate(lines, 1):
        if i not in cut:
            keep.append(line)

    header = (
        '# -*- coding: utf-8 -*-\n'
        '# NidaanPartner.com - the application, on its own.\n'
        '#\n'
        '# Built from sarathi_biz.py by deploy/extract-nidaan-app.py, SUBTRACTIVELY: a copy of\n'
        '# the file that works today, with only the provably Sarathi-only definitions removed.\n'
        '# Source order is untouched, so every definition still precedes its use and every\n'
        '# module-level side effect still happens in the order it always did.\n'
        '#\n'
        '# Do not hand-edit while the split is in progress - re-run the extractor.\n')
    out = header + "\n".join(keep)

    # It must at least parse, and it must still contain every Nidaan route.
    try:
        newtree = ast.parse(out)
    except SyntaxError as e:
        print("!! the extracted file does not parse: line %s: %s" % (e.lineno, e.msg))
        print("   nothing written")
        return 1

    got = set()
    for n in ast.walk(newtree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                        and isinstance(d.func.value, ast.Name) and d.func.value.id == "app"):
                    got.add(n.name)
    missing = sorted((nidaan_routes | shared_routes) - got)
    if missing:
        print("!! %d Nidaan/shared route(s) did not survive: %s" % (len(missing), missing[:8]))
        print("   nothing written")
        return 1

    io.open(OUT, "w", encoding="utf-8", newline="").write(out)
    print("\nnidaan_app.py written\n")
    print("  lines  : %d  ->  %d   (%d removed)" % (len(lines), len(keep), len(lines) - len(keep)))
    print("  dropped: %d Sarathi-only definitions" % len(dropped))
    print("  kept   : every one of the %d Nidaan and %d shared routes"
          % (len(nidaan_routes), len(shared_routes)))
    print("  still present but unused: kept on purpose - dropping something needed costs a")
    print("  feature, keeping something unused costs a few kilobytes.")
    print("\n  sarathi_biz.py was NOT modified.")
    return 0


sys.exit(main())
