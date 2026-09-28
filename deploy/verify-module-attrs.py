# -*- coding: utf-8 -*-
"""Every `module.name` a route calls must actually exist on that module.

THE FAULT THIS EXISTS FOR. On 26 Sep a new module was written as `biz_nidaan_claim_access.py` -
a name already used by the module that verifies a complainant by sending a code to the number on
their claim. It did not shadow the old one, it REPLACED it. `channels`, `start`, `check`,
`SESSION_MIN` and `PREVIEW_MIN` stopped existing, and for two days every claimant who opened
their link got HTTP 500 and read "this link is invalid or has expired".

Nothing caught it. Not pyflakes (the attribute is on an imported module, resolved at runtime).
Not the route census (the route still existed). Not the tests (none of them opened the portal).
Not the app starting up (the import is inside the handler, so the failure waits for a claimant).
It took a screenshot from the founder.

So: import every `biz_*` module, walk every `import X as Y` inside every function in the app
files, and check that each `Y.attr` referenced there is really on X. Cheap, and it turns a silent
two-day outage into a failed check before the commit.

Runs on 3.13, like the other verifiers - modules that need aiosqlite/httpx are reported as
unimportable rather than silently skipped, so the gap is visible instead of pretended away.

    py -3.13 deploy/verify-module-attrs.py
"""
import ast
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# The files that hold routes. sarathi_biz.py is the source of truth; the two built apps are
# checked as well, because a bad build is exactly as broken as a bad source.
APPS = ["sarathi_biz.py", "nidaan_app.py", "sarathi_app.py"]

FAILED = 0
UNIMPORTABLE = []


def fail(msg, detail=""):
    global FAILED
    FAILED += 1
    print("  FAIL  " + msg)
    if detail:
        print("          " + detail)


def module_attrs(name: str):
    """What does this module really export? None if it cannot be imported here."""
    try:
        mod = __import__(name)
    except Exception as e:  # noqa: BLE001
        UNIMPORTABLE.append("%s (%s)" % (name, type(e).__name__))
        return None
    return set(dir(mod))


class Uses(ast.NodeVisitor):
    """Collect (module, alias, attribute, line) for every aliased biz_* import in a function.

    Only LOCAL imports - `import biz_x as _y` inside a handler - which is this codebase's house
    style for route helpers, and precisely where the failure hides: a module-level import would
    at least have broken at startup.
    """

    def __init__(self):
        self.found = []

    def visit_FunctionDef(self, node):
        self._scan(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self._scan(node)
        self.generic_visit(node)

    def _scan(self, fn):
        alias_to_mod = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.startswith("biz_") and a.asname:
                        alias_to_mod[a.asname] = a.name
        if not alias_to_mod:
            return
        for n in ast.walk(fn):
            if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                    and n.value.id in alias_to_mod):
                self.found.append((alias_to_mod[n.value.id], n.value.id, n.attr,
                                   getattr(n, "lineno", 0), fn.name))


print("\nEvery module attribute a route reaches for\n")

cache = {}
checked = 0
for app in APPS:
    path = os.path.join(ROOT, app)
    if not os.path.exists(path):
        continue
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    u = Uses()
    u.visit(tree)
    missing = 0
    for mod, alias, attr, line, fn in u.found:
        if mod not in cache:
            cache[mod] = module_attrs(mod)
        have = cache[mod]
        if have is None:
            continue                      # reported once, at the end
        checked += 1
        if attr not in have:
            missing += 1
            fail("%s:%d  %s.%s does not exist on %s" % (app, line, alias, attr, mod),
                 "in %s()" % fn)
    if not missing:
        print("  PASS  %-16s every attribute reached for is really there" % app)

print("\n  %d attribute reference(s) checked across %d module(s)" % (checked, len(cache)))
if UNIMPORTABLE:
    # NOT silent. A module this check could not load is a hole in the check, and saying so is the
    # difference between "nothing is wrong" and "I did not look".
    print("\n  NOT CHECKED - these modules would not import on this interpreter:")
    for m in sorted(set(UNIMPORTABLE)):
        print("     " + m)

print("\n%s\n" % ("OK - nothing reaches for a name that is not there" if not FAILED
                  else "%d BROKEN REFERENCE(S)" % FAILED))
sys.exit(1 if FAILED else 0)
