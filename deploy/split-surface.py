# -*- coding: utf-8 -*-
"""Where does the cut actually run through sarathi_biz.py?

Stage 2 of the split, and the part that has to come before any code moves.

`sarathi_biz.py` is 30,029 lines holding both products. Moving 357 Sarathi routes out of it
sounds like a file operation. It is not: every route leans on module-level helpers - `_require_
staff`, `_is_nidaan_host`, `charge_with_gst`, a hundred others - and a route that moves while its
helper stays behind does NOT fail at import. It fails when somebody calls it, which could be
weeks later, on a payment path.

So this maps the real dependency surface before anything moves:

  * every module-level name defined in the file (function, class, constant)
  * for every route, which of those names it actually uses
  * and therefore which names are used ONLY by Nidaan, ONLY by Sarathi, or by BOTH

The last group is the answer. Those are the shared core that has to be lifted into a common
module FIRST, before either product's routes can move anywhere. Everything else can follow its
product.

    py -3.13 deploy/split-surface.py
    py -3.13 deploy/split-surface.py --list-shared      # the core, named
"""
import ast
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sarathi_biz.py")
OUT = os.path.join(ROOT, "deploy", "split-surface.json")


def product_of(path: str) -> str:
    if path.startswith("/nidaan"):
        return "nidaan"
    if path.startswith(("/api", "/tenant", "/agent")):
        return "sarathi"
    return "shared"


class Names(ast.NodeVisitor):
    """Every bare name used inside a node - what this function reaches for."""

    def __init__(self):
        self.used = set()

    def visit_Name(self, n):
        self.used.add(n.id)

    def visit_Attribute(self, n):
        self.generic_visit(n)


def main() -> int:
    src = io.open(SRC, encoding="utf-8").read()
    tree = ast.parse(src)

    # What this module defines at the top level.
    defined = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined[n.name] = n
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    defined[t.id] = n
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            defined[n.target.id] = n

    # Which routes exist, and what each reaches for.
    routes = []
    for n in tree.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        paths = []
        for d in n.decorator_list:
            if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and isinstance(d.func.value, ast.Name) and d.func.value.id == "app"
                    and d.args and isinstance(d.args[0], ast.Constant)):
                paths.append(d.args[0].value)
        if not paths:
            continue
        v = Names()
        v.visit(n)
        routes.append({"func": n.name, "paths": paths,
                       "product": product_of(paths[0]),
                       "uses": sorted(v.used & set(defined))})

    # Walk the helper graph: a helper a route uses may use others.
    cache = {}

    def closure(name, seen=None):
        seen = seen or set()
        if name in cache:
            return cache[name]
        if name in seen or name not in defined:
            return set()
        seen = seen | {name}
        v = Names()
        v.visit(defined[name])
        out = set()
        for u in v.used & set(defined):
            if u == name:
                continue
            out.add(u)
            out |= closure(u, seen)
        if not (seen - {name}):
            cache[name] = out
        return out

    users = {}
    for r in routes:
        reach = set(r["uses"])
        for u in list(r["uses"]):
            reach |= closure(u)
        r["reaches"] = sorted(reach)
        for name in reach:
            users.setdefault(name, set()).add(r["product"])

    counts = {}
    for r in routes:
        counts[r["product"]] = counts.get(r["product"], 0) + 1

    only_n = sorted(k for k, v in users.items() if v == {"nidaan"})
    only_s = sorted(k for k, v in users.items() if v == {"sarathi"})
    both = sorted(k for k, v in users.items() if len(v) > 1)
    unused = sorted(set(defined) - set(users))

    print("\nsarathi_biz.py - where the cut runs\n")
    print("  routes            : %d   (nidaan %d, sarathi %d, shared %d)"
          % (len(routes), counts.get("nidaan", 0), counts.get("sarathi", 0),
             counts.get("shared", 0)))
    print("  top-level names   : %d" % len(defined))
    print()
    print("  used ONLY by nidaan routes   : %4d  -> move with Nidaan (they stay put)" % len(only_n))
    print("  used ONLY by sarathi routes  : %4d  -> move with Sarathi" % len(only_s))
    print("  used by BOTH                 : %4d  <- THE SHARED CORE, lift out first" % len(both))
    print("  not reached by any route     : %4d  -> workers, startup, dead" % len(unused))
    print()
    if both:
        share = 100.0 * len(both) / max(1, len(both) + len(only_n) + len(only_s))
        print("  %.0f%% of what routes touch is shared. That is the real size of stage 2." % share)

    if "--list-shared" in sys.argv:
        print("\n  THE SHARED CORE - every one of these must exist for both apps:\n")
        for i in range(0, len(both), 3):
            print("     " + "".join("%-34s" % x for x in both[i:i + 3]))

    io.open(OUT, "w", encoding="utf-8", newline="").write(json.dumps(
        {"routes": routes, "only_nidaan": only_n, "only_sarathi": only_s,
         "shared_core": both, "unreached": unused}, indent=1, sort_keys=True))
    print("\nwrote %s" % OUT)
    return 0


sys.exit(main())
