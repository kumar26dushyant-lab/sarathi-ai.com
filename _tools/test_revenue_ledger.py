"""Revenue must equal the ledger, to the rupee, on real data.

Before 23 Sep 2026 the screen showed Rs 29,257 while nidaan_payments held Rs 80,488 - 36% - and
nobody could see that, because nothing compared the two. This runs the REAL get_revenue_stats()
against a copy of the live database and checks it against the ledger computed independently in
SQL here. If the two ever drift apart again, this fails.

    NIDAAN_NO_OUTBOUND=1 python3 _tools/test_revenue_ledger.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

LIVE = "/opt/sarathi/sarathi_biz.db"
db_path = os.path.join(tempfile.mkdtemp(prefix="rev_"), "copy.db")
shutil.copy(LIVE, db_path)
for e in ("-wal", "-shm"):
    if os.path.exists(LIVE + e):
        shutil.copy(LIVE + e, db_path + e)

os.environ["DB_PATH"] = db_path
OV = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(OV)
sys.path = [q for q in sys.path if os.path.abspath(q) not in (OV, "/opt/sarathi")]
sys.path.insert(0, "/opt/sarathi")
sys.path.insert(0, ROOT)

import aiosqlite                                    # noqa: E402
import biz_database as _db; _db.DB_PATH = db_path   # noqa: E402,E702
import biz_nidaan as n; n.DB_PATH = db_path         # noqa: E402,E702

assert n.__file__.startswith(ROOT), "ABORT: testing the DEPLOYED module, not the change"

P = F = 0


def same(label, got, want):
    global P, F
    if got == want:
        P += 1
        print("  PASS  %-52s %s" % (label, got))
    else:
        F += 1
        print("  FAIL  %s\n          got:  %r\n          want: %r" % (label, got, want))


def check(label, ok, detail=""):
    global P, F
    if ok:
        P += 1
        print("  PASS  " + label)
    else:
        F += 1
        print("  FAIL  " + label + (("  " + str(detail)) if detail else ""))


W = "COALESCE(status,'') NOT IN ('refunded','duplicate','failed')"


async def ledp(expr, extra=""):
    """The ledger in PAISE - no rounding anywhere in the comparison."""
    async with aiosqlite.connect(db_path) as c:
        r = await (await c.execute(
            "SELECT COALESCE(SUM(%s),0) FROM nidaan_payments WHERE %s %s" % (expr, W, extra)
        )).fetchone()
    return r[0] or 0


async def led(expr, extra=""):
    async with aiosqlite.connect(db_path) as c:
        r = await (await c.execute(
            "SELECT COALESCE(SUM(%s),0) FROM nidaan_payments WHERE %s %s" % (expr, W, extra)
        )).fetchone()
    return (r[0] or 0) // 100


async def main():
    stats = await n.get_revenue_stats()

    print("\nThe headline equals the ledger\n")
    same("collected to date", stats["total_revenue"], await led("total_paise"))
    same("of which GST (not ours)", stats["gst_collected"], await led("gst_paise"))
    same("ours, before GST", stats["net_of_gst"], await led("base_paise"))
    check("GST + net adds back up to the total",
          stats["gst_collected"] + stats["net_of_gst"] == stats["total_revenue"])

    print("\nEvery slice, and the slices add up\n")
    same("subscriptions + renewals", stats["total_subscription_revenue"],
         await led("total_paise", "AND source IN ('subscription','subscription_renewal')"))
    same("branch Level-2 fees", stats["total_l2_revenue"],
         await led("total_paise", "AND source='branch_l2'"))
    same("₹499 reviews", stats["total_d2c_revenue"],
         await led("total_paise", "AND source='per_claim_review'"))
    same("custom payment links", stats["total_custom_link_revenue"],
         await led("total_paise", "AND source='payment_link'"))
    # Each slice is rounded on its own and GST makes fractional rupees, so four rounded numbers
    # can add up to a rupee or two under the rounded total. That is arithmetic, not a leak - the
    # EXACT figure is checked in paise just below, and that is what reconciliation uses.
    slices = (stats["total_subscription_revenue"] + stats["total_l2_revenue"]
              + stats["total_d2c_revenue"] + stats["total_custom_link_revenue"])
    check("the four slices add to the total, within rounding (%s vs %s)"
          % (slices, stats["total_revenue"]),
          0 <= stats["total_revenue"] - slices <= 4)
    same("and in PAISE it is exact, to the paisa", stats["total_revenue_paise"],
         await ledp("total_paise"))

    print("\nThe things that were being dropped are in it now\n")
    async with aiosqlite.connect(db_path) as c:
        exp = (await (await c.execute(
            "SELECT COALESCE(SUM(amount_paid),0) FROM nidaan_subscriptions "
            "WHERE status='expired'")).fetchone())[0] or 0
    check("expired subscriptions are money too (₹%s of them existed)" % "{:,}".format(exp),
          stats["total_revenue"] >= exp)
    check("branch Level-2 has its own line and is not zero", stats["total_l2_revenue"] > 0)

    print("\nThe split is configurable, and defaults to what the screen did before\n")
    sp = stats["revenue_split"]
    check("it has shares, not two hardcoded names", isinstance(sp.get("shares"), list))
    same("the basis defaults to the whole collected amount", sp["basis"], "collected")
    same("and is applied to it", sp["basis_amount"], stats["total_revenue"])
    pct = sum(float(x["pct"]) for x in sp["shares"])
    same("the percentages still add to 100", pct, 100.0)
    same("the amounts add to the basis",
         sum(x["amount"] for x in sp["shares"]), stats["total_revenue"])

    print("\nA changed configuration is honoured\n")
    import json
    await n.set_ops_setting(n.REVENUE_SPLIT_SETTING, json.dumps(
        {"basis": "net_of_gst",
         "shares": [{"key": "a", "name": "Ashwin", "pct": 60},
                    {"key": "d", "name": "Dushyant", "pct": 30},
                    {"key": "r", "name": "Reserve", "pct": 10}]}))
    s2 = await n.get_revenue_stats()
    same("three shares now", len(s2["revenue_split"]["shares"]), 3)
    same("and the basis moved to ex-GST", s2["revenue_split"]["basis_amount"], s2["net_of_gst"])
    same("headline revenue did NOT move", s2["total_revenue"], stats["total_revenue"])

    print("\nA broken configuration falls back rather than hiding the money\n")
    await n.set_ops_setting(n.REVENUE_SPLIT_SETTING, "{not json at all")
    s3 = await n.get_revenue_stats()
    same("the default split is used", len(s3["revenue_split"]["shares"]), 2)
    same("and revenue is still right", s3["total_revenue"], stats["total_revenue"])

    print("\n%d passed, %d failed" % (P, F))
    return 1 if F else 0


sys.exit(asyncio.run(main()))
