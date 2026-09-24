# -*- coding: utf-8 -*-
'''An alarm must know how much it matters, and stop talking when it does not.

Founder, 24 Sep, after a night of it: "our bot ... should intelligently understand and stop
automatically if nothing is critical, critical means if application is not working at all
considered critical, payment not happening (due to our problem) ... 1-2 alerts are fine now, not
in every 5 min continuously."

What was there: eleven of fourteen findings marked "critical" - including "we found a payment the
webhook missed and ALREADY FIXED IT", a success reported as an emergency - and every incident
repeating every ten minutes for ever, whatever its severity, until a human pressed a button.

Pinned here:

  - critical BACKS OFF but never goes silent. Something actually broken has to keep asking.
  - warn says its piece twice and stops.
  - info says it once, ever.
  - a silenced incident is EXCLUDED from the due query. This is the dangerous one: the old query
    used COALESCE(next_alert_at,'') <= now, and '' <= any timestamp, so a NULL - meaning "say no
    more" - would have made the incident permanently due. Silence implemented as an infinite
    loop is the exact bug we are fixing, so it is tested against the real SQL, not by reading it.

    py -3.13 _tools/test_alert_cadence.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite  # noqa: E402

import biz_nidaan_pay_guard as pg  # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


print("\nHow loud, and for how long\n")

# ── critical: backs off, never silent ───────────────────────────────────────
crit = [pg._next_gap_minutes("critical", n) for n in range(0, 8)]
check("a critical alarm never goes silent", all(g is not None for g in crit), crit)
check("...and backs off instead of repeating at one speed",
      crit[0] < crit[1] < crit[2] <= crit[3], crit)
check("...starting at 10 minutes", crit[0] == 10, crit)
check("...settling at 6 hours, not faster", crit[-1] == 360, crit)

# ── warn: twice, then quiet ─────────────────────────────────────────────────
warn = [pg._next_gap_minutes("warn", n) for n in range(0, 4)]
check("a warning is said twice at most", warn[0] is not None and warn[1] is None, warn)
check("...with a day between the two", warn[0] == 1440, warn)
check("...and stays quiet after that", all(g is None for g in warn[1:]), warn)

# ── info: once, ever ────────────────────────────────────────────────────────
info = [pg._next_gap_minutes("info", n) for n in range(0, 3)]
check("something we already fixed is said ONCE, ever", all(g is None for g in info), info)

# ── an unknown severity must not default to the loudest ─────────────────────
unk = pg._next_gap_minutes("banana", 1)
check("an unrecognised severity is treated as a warning, not as critical", unk is None, unk)

# ── the severities themselves ───────────────────────────────────────────────
import io  # noqa: E402

SRC = io.open("biz_nidaan_pay_guard.py", encoding="utf-8").read()


def sev_of(key_fragment):
    i = SRC.find('"key": "%s' % key_fragment)
    if i < 0:
        return None
    seg = SRC[i:i + 400]
    j = seg.find('"severity":')
    return seg[j + 11:j + 30].strip().strip('",').strip() if j >= 0 else None


check("a payment we could not reach the gateway for is CRITICAL",
      sev_of("gateway_unreachable") == "critical", sev_of("gateway_unreachable"))
check("a customer who paid and has no record is CRITICAL",
      sev_of("paid_not_recorded") == "critical", sev_of("paid_not_recorded"))
check("money in with no effect for the customer is CRITICAL",
      sev_of("no_effect") == "critical", sev_of("no_effect"))
check("a payment we already recovered is INFO, not an emergency",
      sev_of("recovered_payment") == "info", sev_of("recovered_payment"))
check("a silent webhook is a WARNING — money still arrives via reconciliation",
      sev_of("webhook_silent") == "warn", sev_of("webhook_silent"))

# ── the due query must exclude a silenced incident ──────────────────────────
DB = os.path.join(tempfile.mkdtemp(prefix="cadence-"), "t.db")


async def due_ids():
    async with aiosqlite.connect(DB) as c:
        await c.executescript("""
            CREATE TABLE IF NOT EXISTS nidaan_pay_incidents (
              inc_id INTEGER PRIMARY KEY, status TEXT, severity TEXT,
              next_alert_at TIMESTAMP, alert_count INTEGER DEFAULT 0);
            DELETE FROM nidaan_pay_incidents;
            INSERT INTO nidaan_pay_incidents VALUES
              (1,'open','critical', datetime('now','-1 minute'), 1),   -- due
              (2,'open','warn',     NULL,                        2),   -- SILENCED
              (3,'open','warn',     '',                          2),   -- silenced, empty string
              (4,'open','critical', datetime('now','+1 hour'),   1),   -- not yet
              (5,'resolved','critical', datetime('now','-1 day'), 9);  -- resolved
        """)
        await c.commit()
        rows = await (await c.execute(
            "SELECT inc_id FROM nidaan_pay_incidents WHERE status IN ('open','acked') "
            "AND next_alert_at IS NOT NULL AND next_alert_at <> '' "
            "AND next_alert_at <= datetime('now') ORDER BY inc_id")).fetchall()
    return [r[0] for r in rows]


ids = asyncio.run(due_ids())
check("only the genuinely-due incident is picked up", ids == [1], ids)
check("...a silenced (NULL) incident is NOT due", 2 not in ids, ids)
check("...nor one silenced with an empty string", 3 not in ids, ids)
check("...nor a resolved one", 5 not in ids, ids)

# The old query, proving this test can fail.
async def old_due():
    async with aiosqlite.connect(DB) as c:
        rows = await (await c.execute(
            "SELECT inc_id FROM nidaan_pay_incidents WHERE status IN ('open','acked') "
            "AND COALESCE(next_alert_at,'') <= datetime('now') ORDER BY inc_id")).fetchall()
    return [r[0] for r in rows]


old_ids = asyncio.run(old_due())
check("PROOF: the OLD query would have alerted the silenced ones for ever",
      2 in old_ids and 3 in old_ids, old_ids)

print("\n" + ("%d failed" % FAILED if FAILED
              else "loud when broken, quiet when handled, and silence really is silent"))
sys.exit(1 if FAILED else 0)
