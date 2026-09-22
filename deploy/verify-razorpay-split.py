"""The two products must never take money into the same Razorpay account by accident.

NidaanPartner.com and Sarathi-AI.com settle to different banks through different Razorpay
accounts. In the code that is one rule: a Nidaan endpoint reads the keys through
`_nidaan_rzp_id()` / `_nidaan_rzp_secret()`, and nothing else. Sarathi's `biz_payments.py` reads
`RAZORPAY_*` and nothing else.

The rule is easy to break by copying a working endpoint, and breaking it is silent - the payment
succeeds, the money simply arrives in the other company's account. So it is checked, here, and
re-checkable by anybody:

    py -3.13 deploy/verify-razorpay-split.py

Exits non-zero the moment the two sides start mixing.
"""
import io
import re
import sys

SERVER = io.open("sarathi_biz.py", encoding="utf-8").read()
NIDAAN = io.open("biz_nidaan.py", encoding="utf-8").read()
GUARD = io.open("biz_nidaan_pay_guard.py", encoding="utf-8").read()
DASH = io.open("static/nidaan_dashboard.html", encoding="utf-8").read()

P = F = 0


def check(label, ok, detail=""):
    global P, F
    if ok:
        P += 1
        print("  OK   " + label)
    else:
        F += 1
        print("  NO   " + label + (("\n         " + detail) if detail else ""))


print("\nNidaan and Sarathi keep separate Razorpay accounts\n")

# ── 1. every bare RAZORPAY_KEY_ID in the server file is accounted for ────────
# Nidaan endpoints must go through the helper. The few legitimate Sarathi readers are named,
# because an unexplained new one is exactly the mistake this file exists to catch.
bare = []
for i, line in enumerate(SERVER.splitlines(), 1):
    if "RAZORPAY_KEY_ID" not in line and "RAZORPAY_KEY_SECRET" not in line:
        continue
    if line.lstrip().startswith("#"):
        continue          # a comment naming the variable is not a read
    if "NIDAAN_RAZORPAY" in line:
        continue          # the helper, and the health check, read both deliberately
    if "payments.RAZORPAY_KEY_ID" in line:
        continue          # Sarathi's own module, by name
    if re.match(r"_srz(_id)?\s*=", line.strip()):
        continue          # the comparison that RAISES the alarm about sharing an account
    bare.append((i, line.strip()))

# What remains must be Sarathi-only routes. /api/payments/check-order is one: it recovers a
# SARATHI order after a UPI context loss, and is called only from Sarathi's dashboard.
unexplained = [(i, t) for i, t in bare
               if "check-order" not in SERVER[max(0, SERVER.find(t) - 1200):SERVER.find(t)]
               and "is_enabled" not in t and "_chk(" not in t]
check("no unexplained bare RAZORPAY_* read in the server file",
      not unexplained,
      "; ".join("line %d: %s" % (i, t[:70]) for i, t in unexplained))

# ── 2. every Nidaan money route goes through the helper ──────────────────────
# Find the routes, then confirm the body that follows reaches for the helper rather than os.getenv.
routes = re.findall(r'@app\.(?:get|post)\("(/nidaan/[^"]*(?:pay|subscribe|payment|refund)[^"]*)"',
                    SERVER)
check("Nidaan money routes exist to check (%d found)" % len(routes), len(routes) >= 5)

leaks = []
for m in re.finditer(r'@app\.(?:get|post)\("(/nidaan/[^"]*)"', SERVER):
    start = m.end()
    body = SERVER[start:start + 3000]
    nxt = body.find("\n@app.")
    if nxt > 0:
        body = body[:nxt]
    if not re.search(r'os\.getenv\(\s*"RAZORPAY_KEY_(ID|SECRET)"', body):
        continue
    # A route that reads BOTH is comparing them - that is the health page saying whether the
    # two products have started sharing an account. Paying with one is the thing to catch.
    if "NIDAAN_RAZORPAY_KEY_ID" in body:
        continue
    leaks.append(m.group(1))
check("no Nidaan route reads Sarathi's keys directly",
      not leaks, ", ".join(leaks))

# ── 3. the modules Nidaan owns ───────────────────────────────────────────────
check("biz_nidaan.py prefers Nidaan's own keys",
      'os.getenv("NIDAAN_RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_KEY_ID", "")' in NIDAAN)
check("the payment guard prefers Nidaan's own keys",
      'os.getenv("NIDAAN_RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_KEY_ID", "")' in GUARD)

# ── 4. A. the fallback is no longer silent ───────────────────────────────────
print("\nA. sharing an account by accident is visible\n")
check("the ops health page checks NIDAAN's key, not Sarathi's",
      '_nrz = os.getenv("NIDAAN_RAZORPAY_KEY_ID", "").strip()' in SERVER
      and "Running on Sarathi's Razorpay account" in SERVER)
check("startup says which account Nidaan is on",
      "Nidaan Razorpay is FALLING BACK to Sarathi's account" in SERVER)

# ── 5. B + C. nobody is left with no way to pay ──────────────────────────────
print("\nB + C. a subscriber the checkout sheet fails still has a way through\n")
check("the subscription's hosted page is kept",
      '"short_url": result.get("short_url", "")' in NIDAAN)
check("the dashboard is handed it",
      "const _payUrl = data.short_url || '';" in DASH)
check("it is offered when they close the sheet",
      DASH.count("_subPayFallback(msg, _payUrl, isHi)") >= 3)
check("and in both languages",
      "Payment page did not open?" in DASH
      and "पेमेंट पेज नहीं खुला?" in DASH)
# Both modes: a hardcoded dark background with themed text goes dark-on-dark in light mode.
check("the box takes its colours from the theme, not from one mode",
      "var(--nd-bg-surface)" in DASH.split("_subPayFallback")[1][:900]
      and not re.search(r"background:#[0-9a-fA-F]{3,6}", DASH.split("_subPayFallback")[1][:900]))

print("\n%d checked, %d wrong" % (P + F, F))
sys.exit(1 if F else 0)
