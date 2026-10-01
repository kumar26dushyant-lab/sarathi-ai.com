# -*- coding: utf-8 -*-
'''Screen opens are counted so a tab is retired on evidence (founder, 1 Oct).

    PYTHONPATH=. py -3.14 _tools/test_ui_usage.py
'''
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import biz_nidaan_usage as use  # noqa: E402
use.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="use_"), "t.db")
FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail))


async def main():
    for sid, panel in ((1, "tasks"), (1, "tasks"), (2, "tasks"), (2, "l2")):
        await use.opened(sid, panel)
    check("a bad screen name is refused", not await use.opened(1, "x'; drop table--"))
    check("no staff id, no count", not await use.opened(0, "tasks"))
    rep = {r["panel"]: r for r in await use.report(14)}
    check("opens and people per screen", rep["tasks"]["opens"] == 3 and rep["tasks"]["people"] == 2, rep)
    check("an unopened screen simply is not in the report", "revenue" not in rep, rep)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
