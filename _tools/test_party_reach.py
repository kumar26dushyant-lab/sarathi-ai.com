# -*- coding: utf-8 -*-
""""Who gets notified" must say how we REACH people, not what addresses we hold.

Founder, 24 Sep: "are we notifying everyone whom we are marking green on notifications?"

He was right to ask. The tick was `!!phone` / `!!email`, and three things followed from that:

  - a staff member with no phone and no email showed two red chips and read as UNREACHABLE,
    while being notified on the dashboard bell and on Telegram every single time;
  - staff email showed a flat green, though the notify policy deliberately does not email claim
    notes and comments - the change that took us from 550 emails a day to a handful;
  - a number that had replied STOP showed green, though the sender skips it.

Each of those is pinned below. Pure function, no database.

    py -3.13 _tools/test_party_reach.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import biz_nidaan_claim_parties as cp  # noqa: E402

FAILED = 0
PHONE, EMAIL, STOPPED = "919876543210", "a@b.com", {"9876543210"}


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


def state(reach, ch):
    for c in reach:
        if c["ch"] == ch:
            return c["state"]
    return None


def why(reach, ch):
    for c in reach:
        if c["ch"] == ch:
            return c.get("why", "")
    return ""


print("\nWhat the notify panel is allowed to claim\n")

# ── the one that read as unreachable ────────────────────────────────────────
bare = cp._reach("staff", "", "", set())
check("a staffer with NO phone and NO email is still reached on the dashboard",
      state(bare, "dashboard") == "yes", bare)
check("...and on Telegram", state(bare, "telegram") == "yes", bare)
check("...so the row can never read as 'we cannot reach this person'",
      any(c["state"] == "yes" for c in bare), bare)

# ── staff email is conditional, and says why ────────────────────────────────
st = cp._reach("staff", PHONE, EMAIL, set())
check("staff email is 'maybe', not a flat green", state(st, "email") == "maybe", st)
check("...and names the policy that decides",
      "policy" in why(st, "email").lower() and "telegram" in why(st, "email").lower(),
      why(st, "email"))

# ── an outsider's email is unconditional ────────────────────────────────────
comp = cp._reach("complainant", PHONE, EMAIL, set())
check("a complainant's email IS unconditional", state(comp, "email") == "yes", comp)
check("a complainant gets no dashboard/Telegram chip — they have neither",
      state(comp, "dashboard") is None and state(comp, "telegram") is None, comp)

# ── STOP ────────────────────────────────────────────────────────────────────
stop = cp._reach("complainant", PHONE, EMAIL, STOPPED)
check("a number that replied STOP is NOT green", state(stop, "whatsapp") == "no", stop)
check("...and says so in words a person can act on",
      "stop" in why(stop, "whatsapp").lower(), why(stop, "whatsapp"))
check("...while their email is untouched by it", state(stop, "email") == "yes", stop)

# ── missing details still read as missing ───────────────────────────────────
none = cp._reach("complainant", "", "", set())
check("no number on file still reads as no WhatsApp", state(none, "whatsapp") == "no", none)
check("no address on file still reads as no email", state(none, "email") == "no", none)

# ── every chip is renderable ────────────────────────────────────────────────
ok = True
for role in ("staff", "complainant", "subscriber", "branch", "channel_partner"):
    for ph in ("", PHONE):
        for em in ("", EMAIL):
            for sk in (set(), STOPPED):
                for c in cp._reach(role, ph, em, sk):
                    if not c.get("ch") or not c.get("label") or c.get("state") not in (
                            "yes", "maybe", "no"):
                        ok = False
check("every role/contact combination yields chips the screen can draw", ok)

print("\n" + ("%d failed" % FAILED if FAILED else "the panel can only claim what we actually do"))
sys.exit(1 if FAILED else 0)
