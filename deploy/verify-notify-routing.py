# -*- coding: utf-8 -*-
"""Internal notices go to Telegram and the bell. Email is kept for customers.

Founder, 22 Sep: "comments should also be going in telegram and web notifications, not email.
email notifications ... we can save for customer/complainant facing."

Measured on the live server before changing anything: 550 emails in 24 hours, every real event
copied to all 16 admins, because `dispatch()` decided email by asking "did WhatsApp work?" - and
for staff WhatsApp is effectively never up. biz_nidaan_notify_policy had classed this chatter as
Telegram-and-bell since the day it was written; it was wired into notify_staff_inapp and never
into dispatch, which is the path the chatter actually takes.

This checks the decisions, not the wiring, because the decisions are the thing that can go wrong
quietly:

  - every event on the founder's list is Telegram + bell, FOR EVERY ROLE including super-admin;
  - money, documents, leave, health and security still email - none of those were in his list
    and a quiet one costs real money or real trust;
  - the two ways a notification is sent both ask the policy;
  - it only ever narrows STAFF email. A subscriber or complainant is never touched, which is
    the entire point of doing it;
  - and the tickboxes the founder now has on the settings screen reach a real endpoint. A
    control that renders, accepts a click and changes nothing looks identical to one that works,
    so every link in that chain is checked on its own.

    py -3.13 deploy/verify-notify-routing.py
"""
import ast
import io
import sys

NOTIF = io.open("biz_nidaan_notifications.py", encoding="utf-8").read()
PREFS = io.open("biz_nidaan_notify_prefs.py", encoding="utf-8").read()

# Read the policy as source: importing it is fine, but reading keeps this runnable anywhere.
sys.path.insert(0, ".")
import biz_nidaan_notify_policy as pol  # noqa: E402

P = F = 0


def check(label, ok, detail=""):
    global P, F
    if ok:
        P += 1
        print("  OK   " + label)
    else:
        F += 1
        print("  NO   " + label + (("\n         " + str(detail)) if detail else ""))


ROLES = ("super_admin", "sub_super_admin", "team_member", "")

# What the founder listed, in his words, mapped to the keys that carry them.
HIS_LIST = {
    "claim movement":    ("bucket.move", "bucket.sent_back"),
    "assignment":        ("claim.assigned", "case.assigned", "quick_task.assigned",
                          "task.assigned", "crm.assigned"),
    "tagging":           ("claim_note.mention", "quick_task.mention"),
    "comments":          ("claim.watch", "quick_task.comment"),
    "comments updated":  ("quick_task.comment_ack",),
    "status changes":    ("claim.status", "claim.stage_changed", "quick_task.status",
                          "task.status_changed"),
}

print("\nEverything the founder listed reaches staff WITHOUT an email\n")
for what, keys in HIS_LIST.items():
    bad = []
    for k in keys:
        for r in ROLES:
            ok, why = pol.should_email(k, role=r)
            if ok:
                bad.append("%s / %s -> %s" % (k, r or "(no role)", why))
    check("%-17s (%s)" % (what, ", ".join(keys)), not bad, "; ".join(bad))

print("\nA super-admin is not an exception - that was the biggest single source\n")
for k in ("quick_task.comment", "claim_note.mention", "bucket.move", "claim.watch"):
    ok, why = pol.should_email(k, role="super_admin")
    check("super-admin gets %s on Telegram, not email" % k, not ok, why)

print("\nWhat must still email, because a quiet one costs money or trust\n")
MUST = [("payment.failed", "super_admin"), ("claim.doc_missing", "team_member"),
        ("doc.call_due", "team_member"), ("leave.requested", "team_member"),
        ("leave.decided", "team_member"), ("health.subsystem", "team_member"),
        ("security.login", "team_member"), ("support.escalated", "team_member"),
        ("claim.filed", "team_member"), ("claim.l2", "team_member"),
        ("subscription.halted", "team_member"), ("cp.pending", "team_member")]
for k, r in MUST:
    ok, why = pol.should_email(k, role=r)
    check("%-22s still emails (%s)" % (k, r), ok, why)

print("\nAn event nobody has classified still emails - silence is never inherited\n")
ok, why = pol.should_email("something.brand_new", role="team_member")
check("an unknown key emails", ok, why)

print("\nBoth send paths ask before sending\n")
# They now ask biz_nidaan_notify_prefs, which falls through to THIS policy when nobody has set a
# switch (founder, 25 Sep: per event per role, per event per user, claim level wins). The
# property being protected is unchanged and slightly stronger — a send path that consults nothing
# is still the bug — so the check follows the new chain rather than being dropped.
check("notify_staff_inapp asks", 'resolve(event_key, channel="email"' in NOTIF)
check("dispatch asks too (this is the one that never did)",
      'resolve(event_key, channel="email", staff_id=recipient_id' in NOTIF)
check("Telegram can be switched off as well, which it never could",
      'resolve(event_key, channel="telegram"' in NOTIF)
check("...and the resolver still ends at THIS policy when nobody has an opinion",
      "should_email(ek, role=role, involved=involved, owner=owner)" in PREFS)
check("...and the dashboard bell is never switchable",
      "the dashboard bell always records it" in PREFS)

print("\nAnd it only ever narrows STAFF - customers are the reason for doing this\n")
tree = ast.parse(NOTIF)
guard_ok = False
for node in ast.walk(tree):
    if isinstance(node, ast.If):
        src = ast.unparse(node.test) if hasattr(ast, "unparse") else ""
        if "should_email" in src and "RECIPIENT_STAFF" in src and "recipient_type" in src:
            guard_ok = True
check("the policy call in dispatch is behind a recipient_type == staff test", guard_ok)
check("a subscriber's email is decided by the old rule alone",
      "recipient_type == RECIPIENT_STAFF and recipient_id" in NOTIF)

print("\nThe bell and Telegram are never suppressed by any of this\n")
# The sentence wraps in the source, so whitespace is flattened before looking for it.
_doc = " ".join((pol.__doc__ or "").split()).lower()
check("the policy's own contract still says so",
      "only the email leg is ever downgraded" in _doc
      and "never suppressed by this module" in _doc)
check("the dashboard record is written before the email leg is decided",
      NOTIF.index("channel=CHANNEL_DASHBOARD") < NOTIF.index("should_email = (priority"))

print("\nAnd the switches on the settings screen are wired to something real\n")
# The dead-button class, which has cost this project twice: a control that renders, accepts a
# click and reaches nothing. Each link in the chain is checked separately, because any one of
# them missing looks identical on screen - a tickbox that ticks.
OPS = io.open("static/nidaan_ops.html", encoding="utf-8").read()
BIZ = io.open("sarathi_biz.py", encoding="utf-8").read()
check("each notification row draws a tickbox per job", 'onchange="npToggle(' in OPS)
_roles_block = OPS.split("const _NP_ROLES = [")[1].split("];")[0] if "const _NP_ROLES = [" in OPS else ""
check("...for all three jobs, not just one",
      all(r in _roles_block for r in ("super_admin", "sub_super_admin", "team_member")),
      _roles_block[:120])
check("...and the tickbox posts to the preferences endpoint",
      "API('/notifications/prefs', {method: 'POST'" in OPS)
check("...which exists, at the top level",
      '\n@app.post("/nidaan/ops/api/notifications/prefs")' in BIZ)
check("...is super-admin only, because this is everyone else's attention",
      '_require_staff(request, "super_admin")' in BIZ.split(
          '@app.post("/nidaan/ops/api/notifications/prefs")')[1][:900])
check("...and is written down in the audit trail", '"notify.pref_set"' in BIZ)
check("the screen is told what is already set, not just what the code does",
      '"prefs": await _prefs_safe()' in BIZ and "_npPrefs = d.prefs" in OPS)
check("a locked event draws no tickbox at all - nothing to click that cannot take effect",
      "if (e.locked){" in OPS and "\U0001f512</td>" in OPS)
check("...and the old 'not live yet' note is gone, so the screen is not describing last week",
      "The switches are not live yet" not in OPS)
check("a refused save puts the tickbox back", "el.checked = !on;" in OPS)
# 'daily' is stored but nothing drains a digest yet, so it must not appear as a choice. The day
# somebody builds the digest, this check is the reminder that the screen can now offer it.
_toggle = OPS.split("async function npToggle")[1].split("window.npToggle")[0]
check("the screen does not offer 'daily' while nothing holds a digest",
      "'daily'" not in _toggle and "frequency" not in NOTIF)

print("\n%d checked, %d wrong" % (P + F, F))
sys.exit(1 if F else 0)
