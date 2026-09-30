# -*- coding: utf-8 -*-
'''A brand-new database gets every column a live one has.

CLAUDE.md: "Check the fresh-install path. Six columns were added by ALTER before their table was
created - production was fine and only a restore would have broken." On 30 Sep it had happened
again: five columns (duty roster, support chat, task history) existed on the live database and
silently did not on a fresh one, so duty lookups failed with "no such column: r.duty".

This builds a database from nothing with init_db() and checks that every column any
"ALTER TABLE x ADD COLUMN y" in biz_database.py adds is really there.

    py -3.14 _tools/test_fresh_install.py
'''
import asyncio
import os
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DBP = os.path.join(tempfile.mkdtemp(prefix="fresh_"), "f.db")
os.environ["DB_PATH"] = DBP
import biz_database as db  # noqa: E402
db.DB_PATH = DBP

asyncio.run(db.init_db())
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "biz_database.py"),
           encoding="utf-8").read()
c = sqlite3.connect(DBP)
wanted = re.findall(r"ALTER TABLE (\w+) ADD COLUMN (\w+)", src)
missing = []
for t, col in wanted:
    cols = {r[1] for r in c.execute("PRAGMA table_info(%s)" % t)}
    if col not in cols:
        missing.append("%s.%s%s" % (t, col, "" if cols else " (table missing)"))
ok = len(wanted) > 50 and not missing
print(("  PASS  " if len(wanted) > 50 else "  FAIL  ") + "the scan found the migrations (%d)" % len(wanted))
print(("  PASS  " if not missing else "  FAIL  ") + "every added column exists on a fresh database")
for m in missing:
    print("           missing: " + m)
print("\n%s" % ("all passed" if ok else "failed"))
sys.exit(0 if ok else 1)
