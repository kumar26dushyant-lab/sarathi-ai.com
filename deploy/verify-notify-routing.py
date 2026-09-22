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
  - and it only ever narrows STAFF email. A subscriber or complainant is never touched, which is
    the entire point of doing it.

    py -3.13 deploy/verify-notify-routing.py
"""
import ast
import io
import sys

NOTIF = io.open("biz_nidaan_notifications.py", encoding="utf-8").read()

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

print("\nBoth send paths ask the policy\n")
check("notify_staff_inapp asks", "_pol.should_email(event_key, role=" in NOTIF)
check("dispatch asks too (this is the one that never did)",
      "_pol.should_email(event_key, role=await _staff_role(recipient_id))" in NOTIF)

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

print("\n%d checked, %d wrong" % (P + F, F))
sys.exit(1 if F else 0)
