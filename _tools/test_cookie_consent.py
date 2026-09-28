# -*- coding: utf-8 -*-
'''Cookie consent that actually gates, on both audiences' pages.

Founder, 28 Sep 2026: *"we need cookies policies and acceptance and all related stuffs like only
essential cookies, accept all cookies. the entire cookies acceptance mechanics on
Nidaanpartner.com both pages, advisor and policyholder both pages."*

The thing worth testing is not that a banner appears. It is that it CHANGES something. Until
today Google Analytics loaded the moment any public page opened - so a banner shown afterwards
would have been decoration over tracking that had already started, and every "we ask first" claim
on the policy page would have been false.

What these checks defend:

  * GA cannot start without permission, and cannot start merely because a banner exists - the
    gate is read from nidaan_ga.js itself;
  * the consent script loads BEFORE GA on every page that has GA, because a gate that loads
    second is not a gate;
  * refusing is offered as plainly as accepting, and neither is pre-ticked;
  * BOTH audiences are covered - the advisor pages and the policyholder's claim portal - and
    both can reach the policy and change their mind afterwards;
  * the policy page lists the cookies this application really sets, read out of the source
    rather than trusted. A policy naming cookies we do not use, or missing ones we do, is a
    false statement to a regulator;
  * and every word of it exists in English AND Hindi.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_cookie_consent.py
'''
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


def read(p):
    return io.open(p, encoding="utf-8").read()


CONSENT = read("static/nidaan_cookies.js")
GA = read("static/nidaan_ga.js")
POLICY = read("static/nidaan_cookies.html")

# ── 1. the gate is real ──────────────────────────────────────────────────────
print("\nAnalytics cannot start before permission\n")

check("GA asks the consent module before loading anything",
      "nidaanCookies" in GA and "allows('analytics')" in GA, GA[:200])
check("...and no consent module on the page means NO",
      re.search(r"return !!\(window\.nidaanCookies", GA) is not None)
# Indexed defensively: when the gate is missing there is no start() to find, and a test that
# dies on a ValueError reports two findings instead of all of them.
_gate_at = GA.find("function start()")
_tag_at = GA.find("googletagmanager.com")
check("...and the tag is only built inside the gated function",
      GA.count("googletagmanager.com") == 1 and _gate_at != -1 and _tag_at > _gate_at,
      "the script URL must not be reachable before the check")
check("accepting starts it without needing a reload",
      "nidaan-consent" in GA and "addEventListener" in GA)

# The consent module must treat "not answered" as refusal, never as permission.
check("an undecided visitor is not treated as consenting",
      re.search(r"if \(!c\) return false;", CONSENT) is not None, CONSENT[:0])
check("refusing later actually deletes the analytics cookies",
      "dropAnalyticsCookies" in CONSENT and "expires=Thu, 01 Jan 1970" in CONSENT)
check("an older stored answer does not count as an answer to this version",
      "v.v !== VERSION" in CONSENT)

# ── 2. refusing is as easy as accepting ──────────────────────────────────────
print("\nThe choice is a real one\n")

check("'Accept all' and 'Only essential' are both offered up front",
      "acceptAll" in CONSENT and "essentialOnly" in CONSENT)
check("...and neither optional group starts switched on",
      "wantAnalytics = !!(current && current.analytics)" in CONSENT,
      "an optional group must default to off for somebody who has not decided")
check("there is a way to choose in detail", "choose" in CONSENT and "ndck-grp" in CONSENT)
check("essential is shown as locked rather than silently missing",
      "locked" in CONSENT and "essentialWhy" in CONSENT)
check("consent can be withdrawn later",
      "open: function" in CONSENT and "onChange: function" in CONSENT,
      "the footer link calls nidaanCookies.open(); without it a yes could never be undone")
check("nothing in the banner is built from innerHTML with text",
      "textContent" in CONSENT and "innerHTML = t(" not in CONSENT)

# ── 3. both audiences ────────────────────────────────────────────────────────
print("\nBoth audiences are covered\n")

ADVISOR = ["nidaan_index.html", "nidaan_signup.html", "nidaan_login.html", "nidaan_about.html",
           "nidaan_start.html", "nidaan_review.html", "nidaan_dashboard.html",
           "nidaan_branch.html"]
POLICYHOLDER = ["nidaan_claim_portal.html"]

for name in ADVISOR + POLICYHOLDER:
    p = os.path.join("static", name)
    if not os.path.exists(p):
        check("%-26s exists" % name, False, "page missing")
        continue
    s = read(p)
    check("%-26s asks for consent" % name, "nidaan_cookies.js" in s)
    if "nidaan_ga.js" in s:
        # Order matters: GA reads window.nidaanCookies, which must already exist.
        check("%-26s loads the gate BEFORE analytics" % name,
              s.index("nidaan_cookies.js") < s.index("nidaan_ga.js"),
              "GA would run before the gate was defined")

check("the policyholder can reach the policy and change their mind",
      "renderCookieFoot" in read("static/nidaan_claim_portal.html")
      and "/nidaan/cookies" in read("static/nidaan_claim_portal.html"))
check("the advisor site links both from its footer",
      "/nidaan/cookies" in read("static/nidaan_index.html")
      and "nidaanCookies.open()" in read("static/nidaan_index.html"))

# ── 4. the policy tells the truth ────────────────────────────────────────────
print("\nThe policy page matches the cookies we really set\n")

APP = read("sarathi_biz.py")
real = set(re.findall(r'set_cookie\(\s*(?:key=)?["\']([a-z_]+)["\']', APP))
real |= set(re.findall(r'set_cookie\(\s*\n\s*["\']([a-z_]+)["\']', APP))
# The consent record itself is set by the browser, not the server, so it is added by hand.
real.add("nidaan_consent")

for name in sorted(real):
    check("policy names %-18s" % name, name in POLICY,
          "this application sets it, so the policy has to say so")

# And the reverse: nothing invented.
named = set(re.findall(r"<code>([a-z_]+)</code>", POLICY))
invented = named - real - {"_ga", "_gid"}
check("the policy invents no cookie we do not set", not invented, sorted(invented))

check("the route exists", '@app.get("/nidaan/cookies"' in APP)
check("...and is Nidaan-host only, like the other legal pages",
      "_is_nidaan_host" in APP[APP.index('@app.get("/nidaan/cookies"'):][:600])

# ── 5. both languages, everywhere ────────────────────────────────────────────
print("\nEnglish and Hindi\n")


def devanagari(s):
    return any("ऀ" <= ch <= "ॿ" for ch in s)


check("the banner has a full Hindi translation",
      devanagari(CONSENT) and CONSENT.count("acceptAll") >= 2,
      "every key needs a Hindi value, not just some")

# Keys sit indented six spaces inside each block. Matching loosely also catches the block names
# themselves ("en", "hi"), which are not translations of anything.
en_keys = set(re.findall(r"^      (\w+):",
                         CONSENT[CONSENT.index("en: {"):CONSENT.index("hi: {")], re.M))
hi_block = CONSENT[CONSENT.index("hi: {"):]
hi_keys = set(re.findall(r"^      (\w+):", hi_block[:hi_block.index("\n  };")], re.M))
missing = en_keys - hi_keys
check("no English string is left without a Hindi one", not missing, sorted(missing))

check("the policy page is bilingual", devanagari(POLICY) and 'class="hi"' in POLICY)
check("...and the language follows the rest of the site",
      "nidaan_lang" in POLICY and "claim_lang" in POLICY)

print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
sys.exit(1 if FAILED else 0)
