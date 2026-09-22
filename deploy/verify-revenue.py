# -*- coding: utf-8 -*-
"""Does the Revenue screen agree with the payment ledger? Read-only, and safe to run on live.

On 23 Sep 2026 it did not, and not by a little: Revenue showed **Rs 29,257** while
nidaan_payments held **Rs 80,488** - about 36% of the money actually recorded.

The cause was not a wrong sum. It was TWO separate accounts of the same money. nidaan_payments
is the ledger: one idempotent row per payment, whatever channel it came through. Revenue never
read it - it added up three older tables instead, and each one misses a different slice:

  * branch Level-2 fees appear in NONE of the three                     (Rs 22,963 / 39 payments)
  * `status IN ('active','cancelled')` drops EXPIRED subscriptions      (Rs 14,034 / 9 subs)
    - money already collected does not stop having been collected when a plan lapses, so this
      made Revenue FALL over time, which is backwards
  * 12 x Rs499 reviews are in the ledger, 2 rows exist in the purchase table

Founder's definition, 23 Sep: total revenue is COLLECTED TO DATE - everything that ever came in,
including subscriptions that have since expired - and branch L2 belongs in it.

Fixed the same day: Revenue now reads the ledger, and _tools/test_revenue_ledger.py checks
that the two agree to the paisa on real data.

What this script is FOR now: the three legacy tables still drive other screens, and they
are still drifting from the ledger - 11 of 12 Rs499 reviews have no purchase row at all.
That is a data gap worth watching even though the money is counted correctly. A number
nobody can re-derive is a number nobody should trust, least of all about money.

    py -3.13 deploy/verify-revenue.py /path/to/sarathi_biz.db

Exits non-zero only if the LEDGER ITSELF is unsound - duplicate dedup keys, i.e. not one row per
payment. That is the one condition that would make the revenue figure wrong again.
"""
import sqlite3
import sys

# Not "verified only": a manually marked payment is still money in the bank. What is excluded is
# money that came back out, or a row we already know is a duplicate of another.
LEDGER_WHERE = "COALESCE(status,'') NOT IN ('refunded','duplicate','failed')"


def q1(c, sql, args=()):
    r = c.execute(sql, args).fetchone()
    return (r[0] if r and r[0] is not None else 0)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    c = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)

    print("\nTHE LEDGER - nidaan_payments, one row per payment\n")
    rows = c.execute(
        "SELECT COALESCE(NULLIF(source,''),'(blank)'), COUNT(*), SUM(total_paise) "
        "FROM nidaan_payments WHERE %s GROUP BY 1 ORDER BY 3 DESC" % LEDGER_WHERE).fetchall()
    ledger = 0
    for src, n, paise in rows:
        print("  %-24s %4d payments   Rs %s" % (src, n, "{:,}".format((paise or 0) // 100)))
        ledger += (paise or 0)
    ledger //= 100
    print("  %-24s %4s              Rs %s" % ("TOTAL COLLECTED", "", "{:,}".format(ledger)))

    print("\nWHAT THE REVENUE SCREEN ADDS UP INSTEAD\n")
    subs = q1(c, "SELECT SUM(amount_paid) FROM nidaan_subscriptions "
                 "WHERE status IN ('active','cancelled')")
    d2c = q1(c, "SELECT SUM(amount_paid) FROM nidaan_per_claim_purchase "
                "WHERE status NOT IN ('failed','refunded','pending_payment')")
    link = q1(c, "SELECT SUM(amount_paise) FROM nidaan_payment_links "
                 "WHERE status='paid' AND purpose='custom'") // 100
    shown = subs + d2c + link
    print("  %-24s Rs %s" % ("subscriptions", "{:,}".format(subs)))
    print("  %-24s Rs %s" % ("per-claim reviews", "{:,}".format(d2c)))
    print("  %-24s Rs %s" % ("custom payment links", "{:,}".format(link)))
    print("  %-24s Rs %s" % ("TOTAL SHOWN", "{:,}".format(shown)))

    gap = ledger - shown
    print("\nTHE DIFFERENCE: Rs %s  (the screen shows %.0f%% of the ledger)\n"
          % ("{:,}".format(gap), (shown * 100.0 / ledger) if ledger else 0))

    # Each slice, named, so the gap is explained rather than just reported.
    l2 = q1(c, "SELECT SUM(total_paise) FROM nidaan_payments "
               "WHERE source='branch_l2' AND %s" % LEDGER_WHERE) // 100
    expired = q1(c, "SELECT SUM(amount_paid) FROM nidaan_subscriptions WHERE status='expired'")
    renew = q1(c, "SELECT SUM(total_paise) FROM nidaan_payments "
                  "WHERE source='subscription_renewal' AND %s" % LEDGER_WHERE) // 100
    rev_led = q1(c, "SELECT SUM(total_paise) FROM nidaan_payments "
                    "WHERE source='per_claim_review' AND %s" % LEDGER_WHERE) // 100
    print("  %-46s Rs %s" % ("branch Level-2 fees, counted nowhere", "{:,}".format(l2)))
    print("  %-46s Rs %s" % ("EXPIRED subscriptions, dropped by the filter",
                             "{:,}".format(expired)))
    print("  %-46s Rs %s" % ("renewals the ledger has", "{:,}".format(renew)))
    print("  %-46s Rs %s" % ("reviews: ledger %s vs purchase table %s"
                             % ("{:,}".format(rev_led), "{:,}".format(d2c)),
                             "{:,}".format(rev_led - d2c)))
    print("  (these overlap and do not add to the gap exactly - GST sits in the ledger's")
    print("   total_paise and not always in the older tables' amount_paid)")

    print("\nIS THE LEDGER ITSELF SOUND?\n")
    n = q1(c, "SELECT COUNT(*) FROM nidaan_payments WHERE %s" % LEDGER_WHERE)
    dedup = q1(c, "SELECT COUNT(DISTINCT dedup_key) FROM nidaan_payments WHERE %s" % LEDGER_WHERE)
    blank = q1(c, "SELECT COUNT(*) FROM nidaan_payments WHERE %s "
                  "AND COALESCE(razorpay_payment_id,'')=''" % LEDGER_WHERE)
    print("  %-46s %d" % ("rows", n))
    print("  %-46s %d" % ("distinct dedup keys (must equal rows)", dedup))
    print("  %-46s %d" % ("rows with NO Razorpay payment id", blank))
    if blank:
        print("     ^ manual / marked-paid rows. Real money, but not provable from Razorpay -")
        print("       these are the ones to spot-check against the Razorpay dashboard before")
        print("       treating the ledger as the single source of truth.")

    ok = dedup == n
    if not ok:
        print("\n  !! the ledger has duplicate dedup keys - it is NOT one row per payment")

    print("\nWHAT THIS MEANS NOW\n")
    print("  Since 23 Sep the Revenue screen reads the LEDGER, so the left-hand figures above")
    print("  are what it shows. The right-hand ones are what the three legacy tables still")
    print("  hold, and that gap is no longer a revenue bug - it is a DATA gap worth watching:")
    print("    * 11 of 12 Rs499 reviews have no row in nidaan_per_claim_purchase at all")
    print("    * branch Level-2 fees were never written to any of the three")
    print("  Those tables still drive other screens, so the drift matters even though the")
    print("  money is counted correctly now.")
    print("\n  Exits non-zero only if the LEDGER ITSELF is unsound - that is the one thing")
    print("  that would make the revenue figure wrong again.\n")
    print("%s\n" % ("The ledger is one row per payment."
                    if ok else "!! The ledger has duplicate dedup keys."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
