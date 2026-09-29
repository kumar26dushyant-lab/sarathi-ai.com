# -*- coding: utf-8 -*-
"""A call passing a keyword the function does not accept - found before it ships.

29 Sep 2026: on_claim_filed called dispatch(..., account_id=...). dispatch() has no such
parameter, so every claim a SUBSCRIBER filed raised TypeError at the first admin - inside a
fire-and-forget task, caught and logged - and the "new claim filed" alert reached nobody. Ten
times from 21 Sep, claims #239 and #240 among them. Python compiles it happily; nothing fails
until the line runs.

This reads every biz_*.py and sarathi_biz.py, learns the signature of every top-level function,
resolves `import biz_x as _y` aliases (including imports inside functions), and reports any call
`_y.func(kw=...)` or same-module `func(kw=...)` whose keyword the target does not accept.
Functions that take **kwargs accept anything and are skipped.

    py -3.13 deploy/verify-call-keywords.py
"""
import ast
import glob
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _params(fn) -> set:
    a = fn.args
    if a.kwarg:
        return None                     # **kwargs: accepts anything
    return {x.arg for x in a.args + a.kwonlyargs + getattr(a, "posonlyargs", [])}


def main() -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "biz_*.py"))) + [os.path.join(ROOT, "sarathi_biz.py")]
    trees, sigs = {}, {}
    for f in files:
        mod = os.path.splitext(os.path.basename(f))[0]
        try:
            tree = ast.parse(io.open(f, encoding="utf-8").read(), filename=f)
        except SyntaxError as e:
            print("%s: cannot parse (%s)" % (f, e))
            return 1
        trees[mod] = (f, tree)
        sigs[mod] = {n.name: _params(n) for n in tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    bad = []
    for mod, (f, tree) in trees.items():
        alias = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name in sigs:
                        alias[a.asname or a.name] = a.name
        for c in ast.walk(tree):
            if not isinstance(c, ast.Call) or not c.keywords:
                continue
            fn = c.func
            target = None
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) \
                    and fn.value.id in alias:
                target = (alias[fn.value.id], fn.attr)
            elif isinstance(fn, ast.Name) and fn.id in sigs[mod]:
                target = (mod, fn.id)
            if not target:
                continue
            params = sigs.get(target[0], {}).get(target[1], "missing")
            if params is None or params == "missing":
                continue
            for k in c.keywords:
                if k.arg and k.arg not in params:
                    bad.append("%s:%d  %s.%s() has no parameter %r"
                               % (os.path.relpath(f, ROOT), c.lineno, target[0], target[1], k.arg))
    for b in bad:
        print(b)
    print("\n%d file(s), %d problem(s)" % (len(files), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
