# -*- coding: utf-8 -*-
"""Every notification the app can send must be in the register. Enforced, not hoped for.

Founder, 23 Sep: "notification setup from superadmin itself ... new notifications auto-registering"

"Auto-registering" has exactly one implementation that survives a busy week: the build fails when
somebody adds a notification and does not register it. A convention that relies on remembering is
the same convention that left 75 event keys scattered across 12 modules with nothing able to list
them - which is why nobody could see, the night of 23 Sep, that three separate paths were each
choosing their own cadence.

Checks:
  1. every event_key="..." in the code has a register entry
  2. every register entry corresponds to a real event_key in the code (no dead switches on a
     settings screen - a toggle that controls nothing is worse than no toggle)
  3. every entry has BOTH languages, non-empty and actually different from each other
  4. money, security and system-health events are LOCKED
  5. the register agrees with the routing policy about what exists
  6. describe() runs and returns one row per event

    py -3.13 deploy/verify-notify-registry.py
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import biz_nidaan_notify_registry as reg  # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  OK   " if ok else "  NO   ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("         " + str(detail))


# ── what the code actually sends ────────────────────────────────────────────
# Only the Python that does the sending. Deliberately not the verifiers or this file, which
# mention keys without sending them.
SKIP = {"deploy", "_tools", "uitest", "node_modules", "venv", ".git", "apk", "journeys"}
# The register itself only TALKS about event keys; it does not send any. Reading it back would
# make this check agree with itself, which is the failure mode of every verifier that greps.
SKIP_FILES = {"biz_nidaan_notify_registry.py"}
# A real key is word.word - at least two segments. The looser [a-z0-9_.]+ matched the literal
# "..." inside a docstring and reported it as an unregistered notification.
PAT = re.compile(r'event_key\s*=\s*["\']([a-z0-9_]+(?:\.[a-z0-9_]+)+)["\']')

in_code = set()
where = {}
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
    for f in files:
        if not f.endswith(".py") or f.startswith("test_") or f in SKIP_FILES:
            continue
        p = os.path.join(root, f)
        try:
            src = io.open(p, encoding="utf-8").read()
        except Exception:  # noqa: BLE001
            continue
        for m in PAT.finditer(src):
            in_code.add(m.group(1))
            where.setdefault(m.group(1), os.path.basename(p))

print("\nEvery notification, registered and switchable\n")
print("  %d event key(s) found in the code, %d registered\n" % (in_code and len(in_code) or 0,
                                                                len(reg.EVENTS)))

registered = reg.known_keys()

# 1 — nothing may send without being registered
unregistered = sorted(in_code - registered)
check("every notification the code sends is in the register", not unregistered,
      "\n         ".join("%s  (%s)" % (k, where.get(k, "?")) for k in unregistered))

# 2 — nothing may be registered that nothing sends
orphans = sorted(registered - in_code)
check("no register entry controls a notification that does not exist", not orphans, orphans)

# 3 — both languages, and really both
bad_lang = []
for e in reg.EVENTS:
    if not (e.get("en") or "").strip() or not (e.get("hi") or "").strip():
        bad_lang.append("%s: missing a language" % e["key"])
    elif e["en"].strip() == e["hi"].strip():
        bad_lang.append("%s: Hindi is a copy of the English" % e["key"])
    elif not re.search(r"[ऀ-ॿ]", e["hi"]):
        bad_lang.append("%s: 'Hindi' has no Devanagari in it" % e["key"])
check("every notification is named in BOTH languages", not bad_lang, bad_lang[:6])

check("every group is named in both languages too",
      all((g.get("en") or "").strip() and re.search(r"[ऀ-ॿ]", g.get("hi") or "")
          for g in reg.GROUPS.values()), list(reg.GROUPS))

# 4 — the ones that must never be silenceable
MUST_LOCK = ("payment.", "health.", "wa.line.", "radar.mailbox_down")
should_be_locked = [e["key"] for e in reg.EVENTS
                    if e["key"].startswith(MUST_LOCK) and not e["locked"]]
check("money, security and health notifications cannot be switched off",
      not should_be_locked, should_be_locked)

# A lock that is never explained is just a broken switch.
check("and the lock says why, in both languages",
      bool((reg.LOCK_REASON.get("en") or "").strip())
      and bool(re.search(r"[ऀ-ॿ]", reg.LOCK_REASON.get("hi") or "")),
      reg.LOCK_REASON)

# 5 — the register and the routing policy must agree about what exists
try:
    import biz_nidaan_notify_policy as pol
    policy_keys = set(getattr(pol, "TELEGRAM_ONLY_EVENTS", set()))
    unknown_to_reg = sorted(policy_keys - registered)
    check("every event the routing policy names is registered", not unknown_to_reg,
          unknown_to_reg)
except Exception as e:  # noqa: BLE001
    check("the routing policy could be read", False, e)

# 6 — and the thing the screen calls actually works
try:
    rows_en = reg.describe("en")
    rows_hi = reg.describe("hi")
    check("describe() returns one row per registered notification",
          len(rows_en) == len(reg.EVENTS), "%d rows for %d events" % (len(rows_en), len(reg.EVENTS)))
    check("...with a channel named for every one",
          all((r.get("channels") or "").strip() for r in rows_en))
    check("...and the Hindi call really returns Hindi",
          any(re.search(r"[ऀ-ॿ]", r["label"]) for r in rows_hi))
    check("...and never claims a locked event can be switched off",
          all(r["locked"] for r in rows_en if r["key"].startswith(MUST_LOCK)))
except Exception as e:  # noqa: BLE001
    check("describe() runs", False, e)

print("\n%d checked, %d wrong" % (13, FAILED))
sys.exit(1 if FAILED else 0)
