# -*- coding: utf-8 -*-
"""A local name read before it is first assigned - the bug that silenced notifications.

29 Sep 2026: notify_staff_inapp passed `telegram=_tg_ok` to the bell a few lines BEFORE `_tg_ok`
was worked out for that person. Python compiles that happily. At run time the first person on
every list raised UnboundLocalError - caught, logged, and nothing delivered - and everyone after
them got the previous person's Telegram decision. Every one-person notification was lost, and the
founder (staff #1, first on every list) missed 85 in four days, payment alerts among them.

verify-python-names.py cannot see this: the name IS defined in the function, just later. This
reads each function top to bottom and reports a local name whose first READ comes before its first
ASSIGNMENT in the source. Loop-carried values (`prev` used, then set at the end of the loop) are
a real pattern, so a name assigned before the loop that reads it is fine; only a name with no
assignment above its first read is reported.

    py -3.13 deploy/verify-use-before-assign.py            # every biz_*.py and sarathi_biz.py
    py -3.13 deploy/verify-use-before-assign.py FILE ...
"""
import ast
import glob
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Scope(ast.NodeVisitor):
    """Loads and stores of plain names in ONE function body, not descending into nested scopes."""

    def __init__(self):
        self.loads, self.stores = {}, {}
        self.declared = set()          # global / nonlocal
        self.seq = 0

    def _first(self, d, name, node):
        # Ordered by when the walk MEETS it, which follows evaluation order (see visit_IfExp),
        # not by text position. Kept: (order, line).
        self.seq += 1
        if name not in d:
            d[name] = (self.seq, node.lineno)

    def visit_Name(self, n):
        if isinstance(n.ctx, ast.Load):
            self._first(self.loads, n.id, n)
        else:
            self._first(self.stores, n.id, n)

    def visit_Global(self, n):
        self.declared.update(n.names)

    visit_Nonlocal = visit_Global

    def visit_AugAssign(self, n):
        # x += 1 reads x first; its target counts as a load at that point.
        if isinstance(n.target, ast.Name):
            self._first(self.loads, n.target.id, n.target)
            self._first(self.stores, n.target.id, n.target)
        self.visit(n.value)

    def visit_ExceptHandler(self, n):
        if n.name:
            self._first(self.stores, n.name, n)
        self.generic_visit(n)

    def visit_Import(self, n):
        for a in n.names:
            self._first(self.stores, (a.asname or a.name).split(".")[0], n)

    visit_ImportFrom = visit_Import

    def visit_Assign(self, n):
        # `x = f(x)` reads the right-hand side FIRST.
        self.visit(n.value)
        for t in n.targets:
            self.visit(t)

    def visit_AnnAssign(self, n):
        if n.value is not None:
            self.visit(n.value)
        self.visit(n.target)

    def visit_IfExp(self, n):
        # `a if (x := f()) else b` evaluates the TEST first, whatever the text order says.
        self.visit(n.test)
        self.visit(n.body)
        self.visit(n.orelse)

    def visit_NamedExpr(self, n):
        self.visit(n.value)
        self._first(self.stores, n.target.id, n.target)

    # Nested scopes are checked on their own.
    def visit_FunctionDef(self, n):
        self._first(self.stores, n.name, n)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, n):
        self._first(self.stores, n.name, n)

    def visit_Lambda(self, n):
        pass

    def _comp(self, n):
        pass           # comprehension variables live in their own scope

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _comp


def check_function(fn) -> list:
    sc = _Scope()
    args = fn.args
    params = {a.arg for a in args.args + args.kwonlyargs + getattr(args, "posonlyargs", [])}
    if args.vararg:
        params.add(args.vararg.arg)
    if args.kwarg:
        params.add(args.kwarg.arg)
    for stmt in fn.body:
        sc.visit(stmt)
    out = []
    for name, spos in sc.stores.items():
        if name in params or name in sc.declared:
            continue
        lpos = sc.loads.get(name)
        if lpos and lpos[0] < spos[0]:
            out.append((lpos[1], name, fn.name, spos[1]))
    return out


def check_file(path: str) -> list:
    try:
        tree = ast.parse(io.open(path, encoding="utf-8").read(), filename=path)
    except SyntaxError as e:
        return [(e.lineno or 0, "<syntax>", str(e), 0)]
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found += check_function(node)
    return found


def main(argv) -> int:
    files = argv[1:] or sorted(glob.glob(os.path.join(ROOT, "biz_*.py"))
                               + [os.path.join(ROOT, "sarathi_biz.py")])
    bad = 0
    for f in files:
        for line, name, fn, sline in check_file(f):
            bad += 1
            print("%s:%d  %s() reads %r before it is assigned (first assignment: line %d)"
                  % (os.path.relpath(f, ROOT), line, fn, name, sline))
    print("\n%d file(s), %d problem(s)" % (len(files), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
