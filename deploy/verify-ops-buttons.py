"""Would this button do anything if somebody pressed it?

An onclick attribute runs in the GLOBAL scope. If it names a handler that is not there - never
written, renamed, or declared inside another function - the browser throws a ReferenceError into
a console nobody has open and NOTHING HAPPENS. No window, no error on the page, nothing to say
why. That is the worst kind of broken: it looks like the person clicked wrong.

Run it on the ops page before shipping:

    python deploy/verify-ops-buttons.py static/nidaan_ops.html

WHAT THIS DOES NOT CATCH, and it matters: a handler that IS reachable and then dies on its first
line. That is what "pending draft button is not working" turned out to be on 21 Sep - l2Move()
tested `to !== 'escalation'` when its parameter is called `toKey`. `to` exists in four other
functions, so nothing page-wide notices; it is simply not in scope there. And because `&&` stops
at the first false, it only threw when the destination had more than one step - which is every
bucket except Live Cases, so every move into Pending Draft, Escalation and Lokpal quietly did
nothing for two days. Catching THAT needs a real JavaScript linter with scope analysis
(eslint's `no-undef`); a regex cannot do it honestly, and a check that reports two thousand
false names is a check people learn to skip.
"""
import io
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "static/nidaan_ops.html"
src = io.open(PATH, encoding="utf-8").read()

# ── what a click can actually reach ──────────────────────────────────────────
reachable = set(re.findall(r"(?m)^\s*(?:async\s+)?function\s+([A-Za-z0-9_$]+)", src))
reachable |= set(re.findall(r"(?m)^\s*(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=", src))
reachable |= set(re.findall(r"\bwindow\.([A-Za-z0-9_$]+)\s*=", src))
# Helpers the page loads from its own script files.
for m in re.finditer(r'<script[^>]*\bsrc=["\']([^"\']+)["\']', src):
    p = m.group(1).split("?")[0].lstrip("/")
    try:
        ext = io.open(p, encoding="utf-8").read()
    except OSError:
        continue
    reachable |= set(re.findall(r"(?m)^\s*(?:async\s+)?function\s+([A-Za-z0-9_$]+)", ext))
    reachable |= set(re.findall(r"\b(?:window|root|globalThis)\.([A-Za-z0-9_$]+)\s*=", ext))
reachable |= {
    "alert", "confirm", "prompt", "event", "window", "document", "console", "location",
    "history", "open", "close", "print", "setTimeout", "clearTimeout", "Number", "String",
    "Boolean", "Array", "Object", "JSON", "Math", "Date", "parseInt", "parseFloat",
    "encodeURIComponent", "decodeURIComponent", "fetch", "navigator", "localStorage",
    "sessionStorage", "if", "for", "while", "typeof", "new", "delete", "void", "return",
}

# ── every handler the page names, in an attribute or built into a string ─────
calls = {}


def note(name, pos):
    calls.setdefault(name, []).append(src.count("\n", 0, pos) + 1)


for m in re.finditer(r'on(?:click|change|input|submit|mousedown|blur|focus|keyup|keydown)\s*=\s*'
                     r'(["\'])(.*?)\1', src, re.S):
    # The arguments are often a sentence for the person - healthAction('reseed', 're-run config
    # seeds (idempotent...)'). Those words are prose, not calls, so the quoted parts go first.
    body = re.sub(r"'(?:\\.|[^'\\])*'", "''", m.group(2))
    # Not after a dot: "foo(" is a call on its own, ".slice(" is a method on something that
    # already exists and cannot fail this way.
    for name in re.findall(r"(?<![.\w$])([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", body):
        note(name, m.start())
for m in re.finditer(r"on(?:click|change|input|submit)=\\?[\"']\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
                     src):
    note(m.group(1), m.start())

missing = {n: sorted(set(ls)) for n, ls in calls.items() if n not in reachable}

print("%s: %d handlers named by the page" % (PATH, len(calls)))
for n in sorted(missing):
    ls = missing[n]
    print("  UNREACHABLE  %-26s line%s %s" % (n, "" if len(ls) == 1 else "s",
                                              ", ".join(str(x) for x in ls[:8])))

# A name defined twice at the top level silently clobbers the first: this page is one global
# scope, and last definition wins.
defs = re.findall(r"(?m)^\s*(?:async\s+)?function\s+([A-Za-z0-9_$]+)", src)
dupes = sorted({d for d in defs if defs.count(d) > 1})
for d in dupes:
    print("  DUPLICATE    %s is defined more than once - the last one wins" % d)

print("%d unreachable, %d duplicate" % (len(missing), len(dupes)))
sys.exit(1 if (missing or dupes) else 0)
