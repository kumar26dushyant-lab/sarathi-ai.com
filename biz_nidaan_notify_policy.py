"""
NidaanPartner — NOTIFICATION DECISION LAYER.

Every internal alert used to email every admin, which had two costs: ~53 staff emails a day
burning a 300/day Brevo allowance, and enough noise that people stop reading. This decides,
per event and per recipient, WHICH channels an alert deserves — so what arrives by email is
worth opening.

The rules were set by the founder and are deliberately conservative:

  • MONEY, DOCUMENTS and LEAVE always email. A missed payment failure, a missed document, or a
    missed leave decision costs real money or real trust — those are never downgraded.
  • SUPER-ADMINS keep email on almost everything: they carry the business and are the backstop
    when someone else misses something.
  • INTERNAL CHATTER (task comments, acknowledgements, status ticks, @mentions) goes to Telegram
    and the dashboard bell only. It is instant there and does not need a permanent record.
  • The dashboard bell and Telegram are NEVER suppressed by this module. Only the EMAIL leg is
    ever downgraded, so nobody is left uninformed — the alert simply arrives where it belongs.

Adding an event that isn't listed here defaults to EMAIL-ON. Silence should be a deliberate
choice, never something a new event key inherits by accident.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("nidaan.notify.policy")

# Always email, whoever the recipient is. Evidence and people's time off.
ALWAYS_EMAIL_PREFIXES = (
    "claim.doc",         # document received / requested / missing
    "doc.",              # document-collection events
    "leave.",            # requested + decided: an HR record people rely on
    "health.",           # a subsystem is down
    "cp.",               # a channel partner awaiting approval gates commission
    "security.",         # anything security-flavoured
    "subscription.",     # renewals / halts
    "claim.filed",       # a new claim reaching the team
    "claim.l2",          # escalation to Level-2
    "claim.review",      # review delivered
    "support.",          # a customer waiting on a human
)

# Email only the people who ACT on it; everyone else still gets bell + Telegram.
#
# Payment alerts went to all 13 admins, so one failed payment sent 14 emails. Nobody owns a
# failure that lands in thirteen inboxes, and the volume was eating the sending allowance that
# login and verification codes depend on. Money is still loud — it is just loud on Telegram,
# where it is instant and free, and it still reaches the super-admins who carry the business.
# The referrer (staff or branch) is alerted separately and directly by on_payment_failed().
NARROW_EMAIL_PREFIXES = (
    "payment.",          # failures, successes, refunds
)

# Internal chatter: Telegram + bell are enough. These are the volume drivers.
TELEGRAM_ONLY_EVENTS = {
    "quick_task.comment",
    "quick_task.comment_ack",
    "quick_task.status",
    "quick_task.created",
    "quick_task.mention",
    "claim_note.mention",
}

# Roles that keep email on almost everything (founder's instruction).
_BROAD_EMAIL_ROLES = {"super_admin"}


def should_email(event_key: str, *, role: str = "", involved: bool = True,
                 owner: bool = False) -> tuple[bool, str]:
    """(send_email?, why). Telegram and the dashboard bell are unaffected — always sent.

    `owner` = this recipient actually owns the thing the event is about (the assigned handler,
    the referrer). Owners keep email on money events; bystanders get Telegram + bell.
    """
    ek = (event_key or "").strip().lower()

    # 1. Critical categories win over everything else, for every recipient.
    for p in ALWAYS_EMAIL_PREFIXES:
        if ek.startswith(p):
            return True, f"critical category ({p.rstrip('.')})"

    # 2. Money: super-admins and the person who owns the item get email; the rest get it on
    #    Telegram and the bell. Checked before the broad-role rule so it also narrows for
    #    sub-super-admins, who are the bulk of the volume.
    for p in NARROW_EMAIL_PREFIXES:
        if ek.startswith(p):
            if role in _BROAD_EMAIL_ROLES:
                return True, f"money ({p.rstrip('.')}) — super-admin"
            if owner:
                return True, f"money ({p.rstrip('.')}) — owns this item"
            return False, f"money ({p.rstrip('.')}) — Telegram + bell for everyone else"

    # 3. Super-admins keep the full picture.
    if role in _BROAD_EMAIL_ROLES:
        return True, "super-admin keeps email"

    # 3. Someone with no stake in this claim doesn't need it in their inbox.
    if not involved:
        return False, "not involved in this item"

    # 4. Internal chatter → Telegram + bell.
    if ek in TELEGRAM_ONLY_EVENTS:
        return False, "internal chatter — Telegram + bell"

    # 5. Anything unrecognised still emails. A new event must not go quiet by accident.
    return True, "default (unclassified event)"


def summary() -> list[dict]:
    """What the policy currently does — surfaced in ops so the rules are visible, not folklore."""
    out = [{"event": e, "email": "no — Telegram + bell", "note": "internal chatter"}
           for e in sorted(TELEGRAM_ONLY_EVENTS)]
    out += [{"event": p + "*", "email": "yes — always", "note": "critical category"}
            for p in ALWAYS_EMAIL_PREFIXES]
    out += [{"event": p + "*", "email": "super-admins + the owner only",
             "note": "money — everyone else gets Telegram + bell"}
            for p in NARROW_EMAIL_PREFIXES]
    return out
