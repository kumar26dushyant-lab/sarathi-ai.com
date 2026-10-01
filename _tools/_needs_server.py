# -*- coding: utf-8 -*-
"""A test that needs the live database says so, instead of failing as if the product were broken.

WHY THIS EXISTS. `_tools/test_*.py` held three different kinds of thing under one name:

  * tests of pure logic, which run anywhere;
  * tests that read a COPY of the live database, which only run on the server;
  * manual tools with subcommands, one of which deletes rows.

Run on a development machine, the second kind died with `no such table` or `no column named
policy_inception_date` - which reads exactly like a broken product. Eleven of them failed that way
for long enough that the whole sweep stopped meaning anything, and a sweep nobody believes is
where a real failure goes to hide. On 28 Sep the founder had to send a screenshot of a broken
claimant portal, because no check said anything was wrong.

So a test that needs the server now SKIPS with a sentence saying what it needs and where to run
it, and exits 0. Skipping is honest; failing for the wrong reason is not. The line is printed
loudly enough to read, because "this was not checked" has to stay visible - a silent skip is the
same lie in the other direction.
"""
import os
import sys

LIVE_DB = "/opt/sarathi/sarathi_biz.db"


def live_db_or_skip(what: str = "") -> str:
    """Return the path to the live database, or print why we are skipping and exit 0.

    `what` names what would have been checked, so the skip line says what is NOT being covered
    rather than just that something was not run.
    """
    if os.path.exists(LIVE_DB):
        return LIVE_DB
    name = os.path.basename(sys.argv[0]) or "this test"
    print("\n  SKIPPED  %s needs the live database (%s), which is not on this machine."
          % (name, LIVE_DB))
    if what:
        print("           Not checked here: %s" % what)
    print("           Run it on the server:\n"
          "             ssh ... 161.118.186.201\n"
          "             cd /opt/sarathi && sudo -u sarathi env NIDAAN_NO_OUTBOUND=1 \\\n"
          "                 PYTHONPATH=/opt/sarathi venv/bin/python _tools/%s\n" % name)
    sys.exit(0)


def manual_tool(usage: str) -> None:
    """For the scripts that are toolkits, not tests: print how to use them and exit 0.

    They take a subcommand, and one of them deletes accounts - so being swept up by a
    `test_*.py` loop and run with no arguments must end in a usage message, never an attempt.
    """
    print("\n  This is a MANUAL tool, not an automated test - nothing was run.\n")
    print(usage.rstrip() + "\n")
    sys.exit(0)
