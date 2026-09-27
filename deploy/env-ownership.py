# -*- coding: utf-8 -*-
"""Which product owns which environment variable - decided by who READS it.

Stage 1 of the split. The tempting way to do this is by name: NIDAAN_* is Nidaan's, the rest is
shared. That is a guess, and it is wrong in both directions - GEMINI_API_KEY has no prefix and is
read by both, while some prefixed ones are read by neither any more.

So this asks the code. For every variable, which modules reference it, and which product do those
modules belong to. A variable read only by Nidaan modules is Nidaan's. One read by both is
genuinely shared and has to be duplicated, not divided.

The variable NAMES come from the server; no value is ever read, printed or stored by this script.

    py -3.13 deploy/env-ownership.py                 # classify
    py -3.13 deploy/env-ownership.py --check         # fail if an unclassified var appears
"""
import fnmatch
import glob
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = os.path.join(ROOT, "deploy", "env-names.txt")
OUT = os.path.join(ROOT, "deploy", "env-ownership.json")

# A module belongs to a product by what it is FOR, not only by its name.
SARATHI_MODULES = {"biz_bot.py", "biz_reminders.py", "biz_nurture.py", "biz_tenant.py",
                   "biz_sarathi_whatsapp.py", "biz_sarathi_tgcrm.py"}


def product_of(fname: str) -> str:
    b = os.path.basename(fname)
    if os.sep + "deploy" + os.sep in fname or fname.startswith("deploy" + os.sep):
        return "shared"   # deploy tooling serves both until the deploys themselves split
    if b.startswith("biz_nidaan") or b.startswith("biz_claimshield"):
        return "nidaan"
    if b in SARATHI_MODULES or b.startswith("biz_sarathi"):
        return "sarathi"
    return "shared"


def main() -> int:
    if not os.path.exists(NAMES):
        print("Missing %s - put the variable NAMES (one per line) there first." % NAMES)
        return 1
    want = [l.strip() for l in io.open(NAMES, encoding="utf-8") if l.strip()
            and not l.startswith("#")]

    # Where is each one read?
    #
    # NOT just root-level Python. The first run of this script called BACKUP_ENC_PASSPHRASE
    # "dead", because it is read by a SHELL SCRIPT in deploy/ - and a variable wrongly called
    # dead is one somebody drops, which would have silently ended the off-site encrypted
    # backups. Scan everything that can read an environment: python anywhere, shell scripts,
    # systemd units, and the deploy tooling.
    src = {}
    pats = ("*.py", "*.sh", "*.service", "*.timer", "*.env*", "*.mjs", "*.js", "*.yml", "*.yaml")
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in
                   (".git", "node_modules", "venv", "__pycache__", "apk", "uitest")]
        for fn in files:
            if not any(fnmatch.fnmatch(fn, pt) for pt in pats):
                continue
            f = os.path.join(base, fn)
            try:
                src[f] = io.open(f, encoding="utf-8", errors="ignore").read()
            except Exception:
                pass

    owners, where = {}, {}
    for v in want:
        # Quoted (python) OR bare with a word boundary (shell: $VAR, ${VAR}, VAR=).
        pat = re.compile(r"[\"']%s[\"']|\$\{?%s\b|\b%s=" % tuple([re.escape(v)] * 3))
        files = sorted(os.path.relpath(f, ROOT) for f, s in src.items() if pat.search(s))
        where[v] = files
        prods = {product_of(f) for f in files}
        if not files:
            owners[v] = "unused"
        elif prods == {"nidaan"}:
            owners[v] = "nidaan"
        elif prods == {"sarathi"}:
            owners[v] = "sarathi"
        elif prods == {"shared"}:
            # Read only by shared modules - which product actually needs it is decided by the
            # name, and where the name does not say, it is shared. Never guessed silently.
            owners[v] = "nidaan" if v.startswith(("NIDAAN_", "WA_NIDAAN_", "CLAIMSHIELD_")) else (
                "sarathi" if v.startswith("SARATHI_") else "shared")
        else:
            owners[v] = "shared"

    if "--check" in sys.argv and os.path.exists(OUT):
        was = json.loads(io.open(OUT, encoding="utf-8").read())
        new = sorted(set(owners) - set(was["owners"]))
        gone = sorted(set(was["owners"]) - set(owners))
        if new:
            print("!! %d NEW variable(s) nobody has classified: %s" % (len(new), ", ".join(new)))
            print("   A new secret that lands in the wrong app's env is how a key leaks across")
            print("   the boundary we are building. Classify it, then re-run without --check.")
            return 1
        if gone:
            print("-- %d variable(s) no longer present: %s" % (len(gone), ", ".join(gone)))
        print("every variable is classified")
        return 0

    counts = {}
    for v, o in owners.items():
        counts[o] = counts.get(o, 0) + 1
    print("\n%d variables\n" % len(owners))
    for o in ("nidaan", "sarathi", "shared", "unused"):
        if not counts.get(o):
            continue
        print("  %s (%d)" % (o.upper(), counts[o]))
        for v in sorted(k for k, x in owners.items() if x == o):
            rd = where[v]
            note = ("read by %d module(s)" % len(rd)) if rd else "READ BY NOTHING - dead?"
            print("     %-34s %s" % (v, note))
        print()

    print("  SHARED means genuinely duplicated into both env files, not divided:")
    print("  a secret both products need is a secret both products keep.\n")
    io.open(OUT, "w", encoding="utf-8", newline="").write(
        json.dumps({"owners": owners, "where": where}, indent=1, sort_keys=True))
    print("wrote %s" % OUT)
    return 0


sys.exit(main())
