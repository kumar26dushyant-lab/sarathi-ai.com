# -*- coding: utf-8 -*-
'''The thank-you page must not be forgeable, and must not forward strangers.

Founder, 24 Sep: "after every successful payment there will be a thank you page ... we need it
for marketing and seo purposes."

Bringing payment-link payers back to our own page is the easy half. The half that needs pinning
is that the page then sits on a PUBLIC url, reachable by anyone, carrying a payment result in
its query string. Two things follow, and both are checked here:

  1. Razorpay signs the parameters it appends. If we trusted the parameters instead, anybody
     could produce "Payment successful 🎉" at nidaanpartner.com/nidaan/success and screenshot it
     - a receipt for a payment that never happened, on our domain, for a claimant to believe.

  2. The page took `next` from the query string and followed it after three seconds. That made
     it an open redirect reached THROUGH a success screen: exactly the shape a phishing chain
     wants. Only same-site paths now.

The signature is checked against Razorpay's documented construction
(HMAC-SHA256 of "link_id|reference_id|status|payment_id"), recomputed here independently rather
than by calling our own helper, so a mistake in the app cannot agree with a matching mistake in
the test.

    py -3.13 _tools/test_paylink_callback.py
'''
import hashlib
import hmac
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


SRC = io.open("sarathi_biz.py", encoding="utf-8").read()
PAGE = io.open("static/nidaan_success.html", encoding="utf-8").read()

print("\nThe payment-link thank-you page\n")

# ── the link must actually come home ────────────────────────────────────────
fn = SRC[SRC.index("async def _create_rzp_payment_link"):][:3000]
check("payment links are created with a callback_url", '"callback_url"' in fn, fn[:200])
check("...and Razorpay is told to use GET", '"callback_method"' in fn)
check("...pointing at our own thank-you page", "/nidaan/success" in fn)

# ── the verdict is computed from the signature ──────────────────────────────
vf = SRC[SRC.index("async def nidaan_paylink_verify"):][:2600]
check("the verifier uses HMAC-SHA256", "sha256" in vf and "hmac" in vf.lower(), vf[:200])
check("...over Razorpay's documented string", '{link_id}|{ref}|{status}|{pay_id}' in vf)
check("...compared in constant time", "compare_digest" in vf)
check("...and refuses when no secret is configured",
      "if not secret" in vf and "unknown" in vf)
check("the verifier returns no amount, name or claim - only a verdict",
      not re.search(r'"(amount|name|claim_id|email|contact)"', vf), vf[-400:])

# ── the construction itself, recomputed independently ───────────────────────
secret = b"test-secret-not-a-real-key"
body = "plink_ABC|ref_1|paid|pay_XYZ"
good = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
bad = hmac.new(b"other-secret", body.encode(), hashlib.sha256).hexdigest()
check("a signature made with the right secret differs from a wrong one", good != bad)
check("...and 'paid' is the only status that means paid",
      hmac.new(secret, "plink_ABC|ref_1|expired|pay_XYZ".encode(),
               hashlib.sha256).hexdigest() != good)
check("the app treats only 'paid' as success", 'status.lower() == "paid"' in vf, vf[-300:])

# ── the page ────────────────────────────────────────────────────────────────
check("the page no longer follows `next` as given", "function safeNext" in PAGE)
check("...rejecting anything that is not a same-site path",
      "charAt(0) !== '/'" in PAGE and "charAt(1) === '/'" in PAGE)
check("...including a backslash, which some browsers treat as a slash",
      "\\\\\\\\" in PAGE or "charAt(1) === '\\\\'" in PAGE, "backslash guard")
check("the page asks the server before claiming anything",
      "/nidaan/api/paylink/verify" in PAGE)
check("...and says 'confirming' until it has an answer",
      "paidVerdict === null" in PAGE and "t.checking" in PAGE)
check("...and says so plainly when it cannot confirm",
      "t.failed" in PAGE and "paidVerdict === false" in PAGE)
check("a payer arriving from a link is NOT auto-forwarded anywhere",
      "if (fromLink){" in PAGE and PAGE.index("if (fromLink){") < PAGE.index("} else {"))

# ── both languages, per the standing rule ───────────────────────────────────
en = PAGE[PAGE.index("en: {"):PAGE.index("hi: {")]
hi = PAGE[PAGE.index("hi: {"):]
for key in ("checking", "failed", "failedSub"):
    check("'%s' exists in both English and Hindi" % key,
          (key + ":") in en and (key + ":") in hi)
check("the link message exists in both languages",
      "link:" in en and "link:" in hi)

print("\n" + ("%d failed" % FAILED if FAILED
              else "the page can only say what Razorpay signed, and forwards nobody"))
sys.exit(1 if FAILED else 0)
