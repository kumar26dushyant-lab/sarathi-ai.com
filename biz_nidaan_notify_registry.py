# -*- coding: utf-8 -*-
"""Every notification this app can send, in one place, in both languages.

Founder, 23 Sep: "notification setup from superadmin itself ... new notifications auto-registering"
Founder, 24 Sep: "this is why I need an advanced notification controller settings, every time
you're doing something and another thing breaks/firing."

WHY THIS EXISTS. There are 75 event keys spread across 12 modules. Nothing listed them, so
nothing could show them, and nothing could turn one off. Every change to who-hears-what was a
code change, and the night of 23 Sep happened because three separate paths each decided their own
cadence with nobody able to see the whole picture. `notify_policy.summary()` even claims in its
docstring to be "surfaced in ops so the rules are visible, not folklore" - it was wired to
nothing at all.

WHAT THIS IS NOT. It is not a second copy of the routing rules. Whether an event emails is still
decided by biz_nidaan_notify_policy, and this module ASKS it - two sources of truth for the same
question is how the notify panel came to show green ticks that meant nothing. This file adds only
what the policy has no opinion on: what the event is in words a person recognises, who it is
about, and whether it may be switched off at all.

AUTO-REGISTRATION IS ENFORCED, NOT HOPED FOR. deploy/verify-notify-registry.py greps the codebase
for event_key="..." and fails the build when a key has no entry here. A new notification cannot
be added and quietly skip this file - which is the only version of "auto-registering" that
survives contact with a busy week.

LOCKED events cannot be silenced from the settings screen. Money, security and system health stay
on whatever anyone clicks: an off switch on "a customer paid and we have no record" is a footgun,
and the founder's standing rule is that an unexpected branch ends in "denied", not in "quiet".
"""
from __future__ import annotations

# Groups, in the order a person would look for them. The label is what the settings screen shows.
GROUPS = {
    "money":     {"en": "Payments & money",      "hi": "भुगतान और पैसा"},
    "claims":    {"en": "Claims",                "hi": "क्लेम"},
    "level2":    {"en": "Level-2 legal work",    "hi": "लेवल-2 कानूनी काम"},
    "tasks":     {"en": "Tasks",                 "hi": "काम (टास्क)"},
    "people":    {"en": "Staff & partners",      "hi": "स्टाफ़ और पार्टनर"},
    "customer":  {"en": "Customers & leads",     "hi": "ग्राहक और लीड"},
    "messaging": {"en": "WhatsApp, chat & email", "hi": "व्हाट्सऐप, चैट और ईमेल"},
    "system":    {"en": "System health",         "hi": "सिस्टम की सेहत"},
}


def _e(key, group, en, hi, who, locked=False):
    return {"key": key, "group": group, "en": en, "hi": hi, "who": who, "locked": locked}


# ── the register ─────────────────────────────────────────────────────────────
# `who` is written for a person reading the settings screen, not as a role name.
# `locked` means the switch is shown greyed out with the reason - see LOCK_REASON below.
EVENTS = [
    # ── money ────────────────────────────────────────────────────────────────
    _e("payment.success", "money", "A payment went through",
       "भुगतान सफल हुआ", "Super admins + whoever the payment belongs to", locked=True),
    _e("payment.failed", "money", "A payment failed",
       "भुगतान विफल हुआ", "Super admins + whoever tried to pay", locked=True),
    _e("payment.failed.ref", "money", "A failed payment was chased again",
       "विफल भुगतान के लिए दोबारा संपर्क किया गया", "Super admins", locked=True),
    _e("payment.link_paid", "money", "A shared payment link was paid",
       "साझा किए गए लिंक से भुगतान हुआ", "Super admins + the staff member who shared it", locked=True),
    _e("payment.recovered", "money", "We found a payment Razorpay never told us about, and recorded it",
       "Razorpay से छूटा भुगतान हमने ख़ुद दर्ज कर लिया", "Super admins", locked=True),
    _e("payment.guardian", "money", "The payment guardian found something wrong",
       "पेमेंट गार्जियन को कोई गड़बड़ी मिली", "Super admins", locked=True),
    _e("payment.guardian_ok", "money", "The payment problem is resolved",
       "भुगतान की समस्या हल हो गई", "The founder", locked=True),
    _e("payment.watchdog", "money", "The payment watchdog found an anomaly",
       "पेमेंट वॉचडॉग को असामान्य गतिविधि मिली", "Super admins", locked=True),
    _e("funnel.paid", "money", "Someone paid through the signup funnel",
       "साइनअप से भुगतान आया", "Super admins", locked=True),
    _e("funnel.pay_ready", "money", "Someone reached the payment step",
       "कोई भुगतान वाले चरण तक पहुँचा", "Super admins"),

    # ── claims ───────────────────────────────────────────────────────────────
    _e("claim.filed", "claims", "A new claim was filed", "नया क्लेम दर्ज हुआ",
       "The person who filed it"),
    _e("claim.filed.admin", "claims", "A new claim was filed — staff copy",
       "नया क्लेम दर्ज हुआ — स्टाफ़ के लिए", "Super admins"),
    _e("claim.assigned", "claims", "A claim was assigned to someone",
       "क्लेम किसी को सौंपा गया", "The person it was assigned to"),
    _e("claim.status", "claims", "A claim's status changed", "क्लेम की स्थिति बदली",
       "Everyone on the claim"),
    _e("claim.stage_changed", "claims", "A claim moved to a new stage",
       "क्लेम अगले चरण में गया", "Everyone on the claim"),
    _e("claim.involved", "claims", "You were added to a claim", "आपको क्लेम में जोड़ा गया",
       "The person added"),
    _e("claim.watch", "claims", "Something happened on a claim you follow",
       "जिस क्लेम को आप देख रहे हैं उसमें कुछ हुआ", "Everyone following the claim"),
    _e("claim_note.mention", "claims", "Someone tagged you in a note",
       "किसी ने नोट में आपको टैग किया", "The person tagged"),
    _e("claim.message", "claims", "A message on a claim", "क्लेम पर एक संदेश",
       "Everyone on the claim"),
    _e("claim.message.sub", "claims", "A message on a claim — subscriber copy",
       "क्लेम पर संदेश — सब्सक्राइबर के लिए", "The subscriber"),
    _e("claim.l2_queued", "claims", "A claim is queued for Level-2",
       "क्लेम लेवल-2 के लिए कतार में है", "Super admins"),
    _e("claim.l2_moved", "claims", "A claim moved into Level-2", "क्लेम लेवल-2 में गया",
       "Everyone on the claim"),
    _e("claim.review_delivered", "claims", "The review was delivered to the customer",
       "ग्राहक को रिव्यू भेज दिया गया", "Everyone on the claim"),
    _e("claim.no_documents", "claims", "A claim still has no documents",
       "क्लेम में अब तक कोई दस्तावेज़ नहीं", "Everyone on the claim"),
    _e("claim.wa_inbound", "claims", "The complainant replied on WhatsApp",
       "शिकायतकर्ता ने व्हाट्सऐप पर जवाब दिया", "Everyone on the claim"),
    _e("claimant.accepted", "claims", "The complainant accepted the authorisation",
       "शिकायतकर्ता ने अनुमति दे दी", "Everyone on the claim"),
    _e("document.received", "claims", "A document arrived", "दस्तावेज़ मिल गया",
       "Everyone on the claim"),
    _e("doc.call_due", "claims", "Time to call about missing documents",
       "छूटे दस्तावेज़ के लिए कॉल करने का समय", "The person handling the claim"),

    # ── level-2 ──────────────────────────────────────────────────────────────
    _e("case.assigned", "level2", "A case was assigned to you", "केस आपको सौंपा गया",
       "The person it was assigned to"),
    _e("case.change_request", "level2", "A change was requested on a case",
       "केस में बदलाव माँगा गया", "Everyone on the case"),
    _e("case.draft_query", "level2", "A question was raised on a draft",
       "ड्राफ़्ट पर सवाल उठाया गया", "Everyone on the case"),
    _e("case.draft_query_open", "level2", "A draft question is still unanswered",
       "ड्राफ़्ट का सवाल अब भी अनुत्तरित है", "Everyone on the case"),
    _e("case.draft_query_resolved", "level2", "A draft question was answered",
       "ड्राफ़्ट के सवाल का जवाब मिल गया", "Everyone on the case"),
    _e("case.query_reply", "level2", "Someone replied to a case question",
       "केस के सवाल का जवाब आया", "Everyone on the case"),
    _e("bucket.move", "level2", "A claim moved between buckets", "क्लेम एक बकेट से दूसरी में गया",
       "The team on duty for the new bucket"),
    _e("bucket.sent_back", "level2", "A claim was sent back", "क्लेम वापस भेजा गया",
       "Whoever handed it over"),
    _e("bucket.stale", "level2", "A claim has been sitting too long",
       "क्लेम बहुत समय से अटका है", "The team on duty for that bucket"),

    # ── tasks ────────────────────────────────────────────────────────────────
    _e("task.assigned", "tasks", "A task was assigned to you", "काम आपको सौंपा गया",
       "The person it was assigned to"),
    _e("task.status_changed", "tasks", "A task's status changed", "काम की स्थिति बदली",
       "Everyone on the task"),
    _e("task.approval_required", "tasks", "A task needs your approval",
       "काम को आपकी मंज़ूरी चाहिए", "The approver"),
    _e("task.qc_required", "tasks", "A task needs checking", "काम की जाँच बाक़ी है",
       "The checker"),
    _e("task.sla_overdue", "tasks", "A task is past its deadline", "काम की समय-सीमा निकल गई",
       "The person on it + their manager"),
    _e("quick_task.created", "tasks", "A new task was created", "नया काम बनाया गया",
       "Everyone on the task"),
    _e("quick_task.assigned", "tasks", "A task was assigned to you", "काम आपको सौंपा गया",
       "The person it was assigned to"),
    _e("quick_task.mention", "tasks", "Someone tagged you in a task",
       "किसी ने काम में आपको टैग किया", "The person tagged"),
    _e("quick_task.comment", "tasks", "A new comment on a task", "काम पर नई टिप्पणी",
       "Everyone on the task"),
    _e("quick_task.comment_ack", "tasks", "Your comment was acknowledged",
       "आपकी टिप्पणी पढ़ ली गई", "The person who commented"),
    _e("quick_task.status", "tasks", "A task's status changed", "काम की स्थिति बदली",
       "Everyone on the task"),
    _e("quick_task.request", "tasks", "Someone asked you for something",
       "किसी ने आपसे कुछ माँगा है", "The person asked"),
    _e("quick_task.approval", "tasks", "A request was approved or refused",
       "अनुरोध मंज़ूर या नामंज़ूर हुआ", "The person who asked"),
    _e("quick_task.approval_request", "tasks", "Something needs your approval",
       "किसी चीज़ को आपकी मंज़ूरी चाहिए", "The approver"),
    _e("crm.assigned", "tasks", "A lead was assigned to you", "लीड आपको सौंपी गई",
       "The person it was assigned to"),

    # ── people ───────────────────────────────────────────────────────────────
    _e("staff.welcome", "people", "A new staff member was welcomed",
       "नए स्टाफ़ का स्वागत संदेश", "The new staff member"),
    _e("leave.requested", "people", "Someone asked for leave", "किसी ने छुट्टी माँगी",
       "Their manager + super admins"),
    _e("leave.decided", "people", "A leave request was decided", "छुट्टी पर फ़ैसला हुआ",
       "The person who asked"),
    _e("cp.pending", "people", "A channel partner is waiting for approval",
       "चैनल पार्टनर मंज़ूरी का इंतज़ार कर रहा है", "Super admins"),
    _e("telegram.connect_reminder", "people", "A reminder to connect Telegram",
       "टेलीग्राम जोड़ने की याद", "Staff who have not linked yet"),
    _e("ops.announcement", "people", "An announcement to the team", "टीम के लिए घोषणा",
       "Whoever the announcement is sent to"),
    _e("account.signup", "people", "Somebody signed up", "किसी ने साइन अप किया",
       "Super admins"),

    # ── customers & leads ────────────────────────────────────────────────────
    _e("funnel.lead_filed", "customer", "A new lead came in", "नई लीड आई",
       "The lead"),
    _e("funnel.lead_filed.admin", "customer", "A new lead came in — staff copy",
       "नई लीड आई — स्टाफ़ के लिए", "Super admins"),
    _e("funnel.lead_deletion_notice", "customer", "A lead's data is about to be deleted",
       "लीड का डेटा जल्द हटाया जाएगा", "The lead"),
    _e("funnel.lead_data_purged", "customer", "A lead's data was deleted",
       "लीड का डेटा हटा दिया गया", "Super admins"),

    # ── messaging ────────────────────────────────────────────────────────────
    _e("wa.new_enquiry", "messaging", "A new WhatsApp enquiry", "व्हाट्सऐप पर नई पूछताछ",
       "The support team on duty"),
    _e("wa.doc_received", "messaging", "A document arrived on WhatsApp",
       "व्हाट्सऐप पर दस्तावेज़ आया", "Everyone on the claim"),
    _e("wa.line.down", "messaging", "A WhatsApp number stopped working",
       "व्हाट्सऐप नंबर बंद हो गया", "Super admins", locked=True),
    _e("wa.line.recovered", "messaging", "A WhatsApp number is working again",
       "व्हाट्सऐप नंबर फिर चालू है", "Super admins", locked=True),
    _e("support.escalated", "messaging", "A website chat needs a human",
       "वेबसाइट चैट को इंसान की ज़रूरत है", "The support team on duty"),
    _e("support.customer_reply", "messaging", "A customer replied in chat",
       "ग्राहक ने चैट में जवाब दिया", "The support team on duty"),
    _e("support.sla_escalation", "messaging", "A chat has waited too long",
       "चैट बहुत देर से इंतज़ार कर रही है", "The support team + super admins"),
    _e("conversation.unanswered", "messaging", "Somebody wrote in and got no answer",
       "किसी ने लिखा और जवाब नहीं मिला", "The support team on duty"),
    _e("conversation.unanswered.escalated", "messaging",
       "Somebody still has no answer after a reminder",
       "याद दिलाने के बाद भी जवाब नहीं मिला", "The support team + super admins"),
    _e("radar.mailbox_down", "messaging", "An email inbox stopped being readable",
       "ईमेल इनबॉक्स पढ़ा नहीं जा पा रहा", "Super admins", locked=True),

    # ── system ───────────────────────────────────────────────────────────────
    _e("health.alert", "system", "A health check found something critical",
       "हेल्थ चेक में गंभीर समस्या मिली", "Super admins", locked=True),
    _e("health.subsystem", "system", "A part of the system is down",
       "सिस्टम का एक हिस्सा बंद है", "Super admins", locked=True),
]

BY_KEY = {e["key"]: e for e in EVENTS}

LOCK_REASON = {
    "en": "Money, security and system health cannot be switched off.",
    "hi": "पैसा, सुरक्षा और सिस्टम की सेहत से जुड़ी सूचनाएँ बंद नहीं की जा सकतीं।",
}


def describe(lang: str = "en") -> list[dict]:
    """Every notification, with what it is and how it is currently routed.

    The routing is ASKED of biz_nidaan_notify_policy rather than restated here. A second copy of
    the email rules would drift from the first, which is exactly how the "who gets notified"
    panel came to show ticks that meant nothing.
    """
    try:
        import biz_nidaan_notify_policy as _pol
    except Exception:  # noqa: BLE001
        _pol = None
    lang = "hi" if str(lang).lower().startswith("hi") else "en"
    out = []
    for e in EVENTS:
        emails = None
        if _pol is not None:
            try:
                emails = bool(_pol.should_email(e["key"], role="team_member", involved=True))
            except Exception:  # noqa: BLE001
                emails = None
        out.append({
            "key": e["key"],
            "group": e["group"],
            "group_label": GROUPS.get(e["group"], {}).get(lang, e["group"]),
            "label": e[lang],
            "who": e["who"],
            "locked": e["locked"],
            # Telegram and the dashboard bell are never suppressed for staff - that is the
            # policy's own contract, asserted by deploy/verify-notify-routing.py.
            "channels": ("Telegram + bell" if emails is False
                         else ("Telegram + bell + email" if emails else "Telegram + bell")),
        })
    return sorted(out, key=lambda r: (r["group"], r["key"]))


def known_keys() -> set:
    return set(BY_KEY)
