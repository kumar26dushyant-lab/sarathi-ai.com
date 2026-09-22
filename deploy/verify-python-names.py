# -*- coding: utf-8 -*-
"""Does every name this Python uses exist AT THE POINT IT IS USED?

Same question `deploy/verify-page-js.mjs` asks of the pages, here for the same reason. On 20-23
Sep the payment guardian emailed the founder "No Razorpay webhook has reached us in 24 hours" 44
times a day while webhooks were arriving and being processed normally. The cause was one line:

    try:
        await nidaan.set_ops_setting("razorpay_webhook_last_at",
                                     datetime.utcnow().strftime(...))
    except Exception:
        pass

`datetime` is not a name in that function, and not a module-level name in that file either -
every other use in sarathi_biz.py imports it locally and aliased. So it raised NameError, the
bare `except` swallowed it, the timestamp was never written, and a guardian reading that frozen
timestamp concluded the webhook was dead. Code that looks right, runs, and does nothing.

SCOPE IS THE WHOLE POINT. The first version of this file asked "is this name bound anywhere in
the file", which answered YES - because eight OTHER functions do `from datetime import datetime`
inside themselves. A name bound in one function does not exist in another, and a check that
cannot tell the difference would have passed the very bug it was written for. It was run against
the broken file before being trusted, and it failed to catch it; this version does.

It checks one thing and has no opinions about anything else. A linter that also complains about
spacing is a linter people switch off.

    py -3.13 deploy/verify-python-names.py [file.py ...]

Exits non-zero if anything is reported.
"""
import ast
import builtins
import io
import sys
from pathlib import Path

RUNTIME_GLOBALS = {"__file__", "__name__", "__doc__", "__package__", "__builtins__", "__spec__",
                   "__loader__", "__path__", "__annotations__", "__debug__", "__class__"}
BUILTINS = set(dir(builtins)) | RUNTIME_GLOBALS


class Scope:
    __slots__ = ("kind", "parent", "names", "problems")

    def __init__(self, kind, parent=None):
        self.kind = kind          # module | function | class | comp
        self.parent = parent
        self.names = set()

    def resolve(self, name):
        """Python's own lookup: own scope, then enclosing FUNCTION scopes, then module.

        A class body is skipped on the way OUT - a method cannot see its class's attributes as
        bare names, which is a real rule and one this must not paper over.
        """
        s, first = self, True
        while s is not None:
            if name in s.names and (first or s.kind != "class"):
                return True
            first = False
            s = s.parent
        return name in BUILTINS


def _targets(node, into):
    """Names bound by an assignment/for/with/comprehension target."""
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            into.add(n.id)


def _params(args, into):
    for group in (args.posonlyargs, args.args, args.kwonlyargs):
        for a in group:
            into.add(a.arg)
    if args.vararg:
        into.add(args.vararg.arg)
    if args.kwarg:
        into.add(args.kwarg.arg)


SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
               ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)


def _walk_own_scope(node):
    """This node and everything under it, STOPPING at a nested scope boundary.

    ast.walk() descends into everything, which is how the first two versions of this file
    convinced themselves that `datetime` was a module-level name: eight other functions import it
    inside themselves. A nested def's NAME binds in the enclosing scope; nothing in its body does.

    The boundary test has to apply to the node itself, not only to its children - a module body
    is a list of function definitions, and walking INTO them was the whole mistake.
    """
    if isinstance(node, SCOPE_NODES):
        yield node               # its own name binds here; its body does not
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_own_scope(child)


def collect(body, scope):
    """Every name BOUND directly in this scope. Does not descend into nested scopes' bodies -
    those bind in their own - but does take the nested def/class NAME, which binds here."""
    for node in body:
        for n in _walk_own_scope(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope.names.add(n.name)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    scope.names.add((a.asname or a.name).split(".")[0])
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    scope.names.add(a.asname or a.name)
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    _targets(t, scope.names)
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                _targets(n.target, scope.names)
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                _targets(n.target, scope.names)
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for item in n.items:
                    if item.optional_vars is not None:
                        _targets(item.optional_vars, scope.names)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                scope.names.add(n.name)
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                scope.names.update(n.names)
            elif isinstance(n, ast.comprehension):
                _targets(n.target, scope.names)


class Checker:
    """Walks scopes, reporting a Load of a name the scope chain cannot supply."""

    def __init__(self):
        self.problems = []      # (line, name)
        self.seen = set()

    def module(self, tree):
        s = Scope("module")
        collect(tree.body, s)
        self.block(tree.body, s)

    def block(self, body, scope):
        for node in body:
            self.node(node, scope)

    def node(self, node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Decorators and defaults are evaluated in the ENCLOSING scope.
            for d in node.decorator_list:
                self.expr(d, scope)
            for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x]:
                self.expr(d, scope)
            inner = Scope("function", scope)
            _params(node.args, inner.names)
            collect(node.body, inner)
            self.block(node.body, inner)
            return
        if isinstance(node, ast.ClassDef):
            for d in node.decorator_list:
                self.expr(d, scope)
            for b in node.bases:
                self.expr(b, scope)
            inner = Scope("class", scope)
            collect(node.body, inner)
            self.block(node.body, inner)
            return
        for child in ast.iter_child_nodes(node):
            self.node(child, scope) if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else self.expr(
                child, scope)

    def expr(self, node, scope):
        if node is None:
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self.node(node, scope)
            return
        if isinstance(node, ast.Lambda):
            inner = Scope("function", scope)
            _params(node.args, inner.names)
            self.expr(node.body, inner)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            inner = Scope("comp", scope)
            for gen in node.generators:
                _targets(gen.target, inner.names)
            # The FIRST iterable is evaluated in the enclosing scope; the rest inside.
            for i, gen in enumerate(node.generators):
                self.expr(gen.iter, scope if i == 0 else inner)
                for cond in gen.ifs:
                    self.expr(cond, inner)
            for part in (getattr(node, "elt", None), getattr(node, "key", None),
                         getattr(node, "value", None)):
                self.expr(part, inner)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if not scope.resolve(node.id) and node.id not in self.seen:
                self.seen.add(node.id)
                self.problems.append((node.lineno, node.id))
            return
        for child in ast.iter_child_nodes(node):
            self.expr(child, scope)


def check_file(path):
    try:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
    except SyntaxError as e:
        return [(e.lineno or 0, "(syntax error) " + str(e))]
    c = Checker()
    c.module(tree)
    return sorted(c.problems)


def main():
    args = sys.argv[1:]
    files = ([Path(a) for a in args] if args else
             sorted(p for p in Path(".").glob("*.py") if not p.name.startswith("_")))
    problems = 0
    for f in files:
        rows = check_file(f)
        if rows:
            print("\n%s:" % f)
            for line, name in rows:
                print("  line %-7d %s  is not defined here" % (line, name))
            problems += len(rows)
        else:
            print("%-34s ok" % (str(f) + ":"))
    print("\n%d problem(s)" % problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
