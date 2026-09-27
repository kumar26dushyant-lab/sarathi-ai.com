# -*- coding: utf-8 -*-
"""Which tables does each product actually TOUCH? The question stage 5 lives or dies on.

The earlier check asked whether any nidaan_* table has a FOREIGN KEY into a Sarathi table. Answer:
one. That was reassuring and it was the wrong question.

A product does not need a foreign key to depend on a table. It needs a query. Nidaan's CRM route
`crm_update_lead` writes to `leads` - a table with no nidaan_ prefix, no foreign key to anything
Nidaan owns, and every appearance of belonging to Sarathi. Split the database on the prefix and
that feature stops working, silently, on a table that looked safe to move.

So this asks what the code actually reads and writes, per product, by pulling table names out of
the SQL in every function each product's routes reach.

Names that BOTH products query are the real stage-5 problem: they must be copied, split by a
key, or kept in one place behind an API. That is a decision per table, and it cannot be made
from a prefix.

    py -3.13 deploy/table-crossings.py
"""
import ast
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURFACE = os.path.join(ROOT, "deploy", "split-surface.json")
OUT = os.path.join(ROOT, "deploy", "table-crossings.json")

_SQL = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-z_][a-z0-9_]*)", re.I)
# SQL keywords that follow FROM/JOIN and are not tables
_NOISE = {"select", "where", "set", "values", "as", "on", "and", "or", "by", "order",
          "group", "limit", "case", "when", "then", "else", "end", "null", "not", "in"}


# The only reliable filter: the real table list, read from the database itself. Without it the
# regex matches prose ("moved from here") and python imports ("from datetime import"), and an
# analysis that reports __future__ as a shared table is one nobody will read twice.
_REAL = set()
_tbl = os.path.join(ROOT, "deploy", "db-tables.txt")
if os.path.exists(_tbl):
    _REAL = {l.strip().lower() for l in io.open(_tbl, encoding="utf-8") if l.strip()}


def tables_in(text: str) -> set:
    found = {m.group(1).lower() for m in _SQL.finditer(text)
             if m.group(1).lower() not in _NOISE}
    return (found & _REAL) if _REAL else found


def main() -> int:
    surface = json.loads(io.open(SURFACE, encoding="utf-8").read())
    src = io.open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
    tree = ast.parse(src)

    bodies = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                bodies[n.name] = ast.unparse(n)
            except Exception:
                pass

    used = {}   # table -> set(products)
    for r in surface["routes"]:
        prod = r["product"]
        seen = set()
        for name in [r["func"]] + r["reaches"]:
            seen |= tables_in(bodies.get(name, ""))
        for t in seen:
            used.setdefault(t, set()).add(prod)

    # Modules each product owns contribute too.
    for f in sorted(os.listdir(ROOT)):
        if not f.endswith(".py"):
            continue
        prod = ("nidaan" if f.startswith(("biz_nidaan", "biz_claimshield"))
                else "sarathi" if f in ("biz_bot.py", "biz_reminders.py", "biz_nurture.py",
                                        "biz_tenant.py", "biz_sarathi_whatsapp.py",
                                        "biz_sarathi_tgcrm.py") else None)
        if not prod:
            continue
        for t in tables_in(io.open(os.path.join(ROOT, f), encoding="utf-8",
                                   errors="ignore").read()):
            used.setdefault(t, set()).add(prod)

    both = sorted(t for t, p in used.items() if "nidaan" in p and "sarathi" in p)
    n_only = sorted(t for t, p in used.items() if p == {"nidaan"})
    s_only = sorted(t for t, p in used.items() if p == {"sarathi"})

    print("\nWhich tables does each product touch\n")
    print("  nidaan only : %d" % len(n_only))
    print("  sarathi only: %d" % len(s_only))
    print("  BOTH        : %d   <- every one of these needs a decision for stage 5" % len(both))
    print()
    if both:
        print("  Touched by both products:\n")
        for t in both:
            prefix = "nidaan_" if t.startswith("nidaan_") else ""
            note = ("  (prefix says Nidaan)" if prefix else
                    "  <-- NO nidaan_ prefix: a prefix-based split would take it away")
            print("     %-34s%s" % (t, note))
    io.open(OUT, "w", encoding="utf-8", newline="").write(json.dumps(
        {"both": both, "nidaan_only": n_only, "sarathi_only": s_only}, indent=1))
    print("\nwrote %s" % OUT)
    return 0


sys.exit(main())
