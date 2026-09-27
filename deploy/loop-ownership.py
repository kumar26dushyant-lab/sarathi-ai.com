# -*- coding: utf-8 -*-
"""Which product does each background loop belong to?

Stage 6, and the check that stopped me switching.

The web tier split cleanly because routes carry their product in the path. The WORKER does not:
main() starts 26 background loops in one function, and the subtractive extraction kept that
function in BOTH app files - no route reaches it, so nothing marked it as either product's.

Starting both workers as they stand would run every one of those loops TWICE. Two Telegram
pollers fighting over getUpdates, two payment guardians raising the same alert, two document
chase loops sending the same claimant the same WhatsApp message. The failure would not be a
crash; it would be duplicates going to real people.

So ownership is decided the same way it was for tables: by what the code TOUCHES. For each loop,
which modules does it import and which tables does it query, and which product do those belong
to.

    py -3.13 deploy/loop-ownership.py
"""
import ast
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sarathi_biz.py")
OUT = os.path.join(ROOT, "deploy", "loop-ownership.json")
TABLES = os.path.join(ROOT, "deploy", "db-tables.txt")

NIDAAN_MODS = ("biz_nidaan", "biz_claimshield")
SARATHI_MODS = ("biz_bot", "biz_reminders", "biz_nurture", "biz_tenant",
                "biz_sarathi_whatsapp", "biz_sarathi_tgcrm", "biz_bot_manager")

_SQL = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-z_][a-z0-9_]*)", re.I)
REAL = set()
if os.path.exists(TABLES):
    REAL = {l.strip().lower() for l in io.open(TABLES, encoding="utf-8") if l.strip()}


def main() -> int:
    src = io.open(SRC, encoding="utf-8").read()
    tree = ast.parse(src)

    bodies = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                bodies[n.name] = ast.unparse(n)
            except Exception:
                pass

    # What main() actually launches.
    main_body = bodies.get("main", "")
    loops = sorted(set(re.findall(r"create_task\((\w+)\(", main_body)))
    loops += sorted(set(re.findall(r"create_task\((\w+)\.(\w+)\(", main_body)) and [])
    extra = re.findall(r"create_task\((\w+\.\w+)\(", main_body)
    loops = sorted(set(loops) | set(extra))

    # A loop body usually just CALLS a helper. Judging it on its own text says nothing, which is
    # how fifteen of twenty-six came back "unclear" on the first run. So follow the calls: the
    # loop plus everything it reaches, two levels down, is what decides its owner.
    def reach(name, depth=2, seen=None):
        seen = seen or set()
        b = bodies.get(name, "")
        if not b or depth == 0 or name in seen:
            return b
        seen = seen | {name}
        out = [b]
        for callee in set(re.findall(r"\b(\w+)\s*\(", b)):
            if callee in bodies and callee not in seen:
                out.append(reach(callee, depth - 1, seen))
        return "\n".join(out)

    verdict = {}
    for name in loops:
        body = reach(name.split(".")[-1])
        if not body and "." in name:
            body = name  # a call into another module, judged by its module name
        mods = set(re.findall(r"\bimport\s+(biz_\w+)", body)) | set(
            re.findall(r"\bfrom\s+(biz_\w+)", body)) | set(re.findall(r"\b(biz_\w+)\.", body))
        if "." in name:
            mods.add("biz_" + name.split(".")[0].lstrip("_")) if not name.startswith("biz_") else None
            mods.add(name.split(".")[0])
        tabs = {m.group(1).lower() for m in _SQL.finditer(body)}
        if REAL:
            tabs &= REAL
        n_hits = [m for m in mods if m.startswith(NIDAAN_MODS)] + \
                 [t for t in tabs if t.startswith("nidaan_")]
        s_hits = [m for m in mods if m in SARATHI_MODS or m.startswith("biz_sarathi")] + \
                 [t for t in tabs if t in ("tenants", "agents", "leads", "policies")]
        if n_hits and not s_hits:
            who = "nidaan"
        elif s_hits and not n_hits:
            who = "sarathi"
        elif n_hits and s_hits:
            who = "BOTH"
        else:
            who = "unclear"
        verdict[name] = {"product": who, "modules": sorted(mods)[:6],
                         "tables": sorted(tabs)[:6], "has_body": bool(bodies.get(name.split(".")[-1]))}

    order = {"nidaan": 0, "sarathi": 1, "BOTH": 2, "unclear": 3}
    print("\n%d background loops started by main()\n" % len(loops))
    for who in ("nidaan", "sarathi", "BOTH", "unclear"):
        rows = [k for k in loops if verdict[k]["product"] == who]
        if not rows:
            continue
        label = {"nidaan": "NIDAAN - must run in exactly one worker",
                 "sarathi": "SARATHI",
                 "BOTH": "TOUCHES BOTH - needs a decision",
                 "unclear": "UNCLEAR - must be read before it moves"}[who]
        print("  %s (%d)" % (label, len(rows)))
        for k in rows:
            v = verdict[k]
            hint = ", ".join(v["modules"][:3]) or ", ".join(v["tables"][:3]) or "-"
            print("     %-28s %s" % (k, hint[:56]))
        print()

    io.open(OUT, "w", encoding="utf-8", newline="").write(
        json.dumps(verdict, indent=1, sort_keys=True))
    print("wrote %s" % OUT)
    unclear = [k for k in loops if verdict[k]["product"] in ("unclear", "BOTH")]
    if unclear:
        print("\n%d loop(s) cannot be assigned automatically. Nothing should start a second"
              % len(unclear))
        print("worker until each has been read - a loop that runs twice sends real people")
        print("duplicate messages, and that is not a crash anyone would see in a log.")
    return 0


sys.exit(main())
