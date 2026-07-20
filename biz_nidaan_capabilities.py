"""
biz_nidaan_capabilities.py — ONE source of truth for "what can I do, and where?"
─────────────────────────────────────────────────────────────────────────────
Everything staff-facing that explains the product is generated from the list in
this file:

  • the web/PWA guide panel ("What I can do")
  • the Telegram bot's ❓ Help
  • the spoken guide (English + Hindi), which is read aloud from this same text

That is deliberate. A hand-written help page drifts the moment a feature is
added, changed or removed, and then the guide contradicts the product. Here,
adding a capability (or flipping `telegram` / `web` / `min_role`) updates the
web guide, the bot help and the audio narration together — they cannot disagree.

WHEN YOU CHANGE A FEATURE, CHANGE ITS ENTRY HERE IN THE SAME COMMIT.

Each capability:
  id        stable key
  en / hi   {"t": short title, "d": one-line explanation} in both languages
  telegram  can it be done from the Telegram bot?
  web       can it be done from the web portal / installed app?
  min_role  lowest role that may use it (team_member < sub_super_admin < super_admin)
"""
from __future__ import annotations

ROLE_RANK = {"team_member": 0, "sub_super_admin": 1, "super_admin": 2}

CAPABILITIES: list[dict] = [
    # ── Everyday task work ────────────────────────────────────────────────
    {
        "id": "tasks_pending_with_me",
        "en": {"t": "See tasks pending with you",
               "d": "Your own work queue — everything assigned to you."},
        "hi": {"t": "अपने पेंडिंग टास्क देखें",
               "d": "जो भी काम आपको सौंपा गया है, वह सब यहाँ दिखता है।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        "id": "tasks_assigned_by_me",
        "en": {"t": "See tasks you assigned to others",
               "d": "Track what you handed over and where it has reached."},
        "hi": {"t": "आपने जो टास्क दूसरों को दिए",
               "d": "आपने जो काम सौंपा है, उसकी स्थिति यहाँ देखें।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        "id": "tasks_involved",
        "en": {"t": "See tasks you were tagged into",
               "d": "Work where a colleague pulled you in with @mention."},
        "hi": {"t": "जिन टास्क में आपको टैग किया गया",
               "d": "जहाँ किसी साथी ने @mention करके आपको जोड़ा है।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        "id": "tasks_archived",
        "en": {"t": "Open the archive of finished tasks",
               "d": "Completed and cancelled work, kept out of your daily list."},
        "hi": {"t": "पूरे हो चुके टास्क का आर्काइव",
               "d": "पूरे और रद्द किए गए काम, रोज़ की लिस्ट से अलग।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        "id": "task_status_change",
        "en": {"t": "Start, complete or reopen a task",
               "d": "Move your task forward. Only the assignee or an admin can."},
        "hi": {"t": "टास्क शुरू करें, पूरा करें या दोबारा खोलें",
               "d": "सिर्फ़ जिसे टास्क सौंपा गया है या एडमिन ही बदल सकते हैं।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        "id": "task_comment",
        "en": {"t": "Add a comment on a task",
               "d": "Everyone involved in that task is notified automatically."},
        "hi": {"t": "टास्क पर कमेंट करें",
               "d": "उस टास्क से जुड़े सभी लोगों को अपने आप सूचना चली जाती है।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        "id": "ask_ai",
        "en": {"t": "Ask the AI about your work",
               "d": "Plain-language questions like 'what is pending with me?'. It only sees what you are allowed to see."},
        "hi": {"t": "AI से अपने काम के बारे में पूछें",
               "d": "जैसे 'मेरे पास क्या पेंडिंग है?'। AI को सिर्फ़ वही दिखता है जो आपको देखने की अनुमति है।"},
        "telegram": True, "web": False, "min_role": "team_member",
    },
    {
        "id": "notifications",
        "en": {"t": "Get instant notifications",
               "d": "Task assigned, tagged, commented or approved — on Telegram and in the app."},
        "hi": {"t": "तुरंत नोटिफिकेशन पाएँ",
               "d": "टास्क मिलने, टैग होने, कमेंट या अप्रूवल पर — टेलीग्राम और ऐप दोनों पर।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    # ── Leave / WFH ───────────────────────────────────────────────────────
    {
        "id": "apply_leave",
        "en": {"t": "Apply for leave",
               "d": "Send a leave request; your admins are notified for approval."},
        "hi": {"t": "छुट्टी के लिए आवेदन करें",
               "d": "छुट्टी की रिक्वेस्ट भेजें; एडमिन को अप्रूवल के लिए सूचना जाती है।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        "id": "apply_wfh",
        "en": {"t": "Apply to work from home",
               "d": "Same as leave — request it and an admin approves."},
        "hi": {"t": "वर्क फ्रॉम होम के लिए आवेदन करें",
               "d": "छुट्टी की तरह ही — रिक्वेस्ट भेजें, एडमिन अप्रूव करेंगे।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    # ── Admin ─────────────────────────────────────────────────────────────
    {
        "id": "approve_tasks",
        "en": {"t": "Approve or reject tasks",
               "d": "Decide the tasks that name you as approver."},
        "hi": {"t": "टास्क अप्रूव या रिजेक्ट करें",
               "d": "जिन टास्क में आपको अप्रूवर बनाया गया है, उन पर निर्णय लें।"},
        "telegram": True, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "broadcast",
        "en": {"t": "Broadcast a message to all staff",
               "d": "Goes to everyone's notification bell at once."},
        "hi": {"t": "सभी स्टाफ को संदेश भेजें",
               "d": "एक साथ सबकी नोटिफिकेशन बेल पर पहुँचता है।"},
        "telegram": True, "web": True, "min_role": "super_admin",
    },
    # ── Web / installed app only ──────────────────────────────────────────
    {
        "id": "create_task",
        "en": {"t": "Create a new task",
               "d": "With category, due date, priority, attachments and people to involve."},
        "hi": {"t": "नया टास्क बनाएँ",
               "d": "कैटेगरी, ड्यू डेट, प्राथमिकता, फाइलें और जुड़े लोगों के साथ।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "attach_files",
        "en": {"t": "Attach files to a task or comment",
               "d": "Up to 10 documents or photos at a time."},
        "hi": {"t": "टास्क या कमेंट में फाइल लगाएँ",
               "d": "एक बार में 10 तक दस्तावेज़ या फोटो।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "mention_people",
        "id_note": "collaboration",
        "en": {"t": "Tag colleagues into a task (@mention)",
               "d": "They get access, get notified, and can work on it with you."},
        "hi": {"t": "साथियों को टास्क में टैग करें (@mention)",
               "d": "उन्हें एक्सेस और सूचना मिलती है, और वे साथ काम कर सकते हैं।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "mute_task",
        "en": {"t": "Mute a busy task",
               "d": "Stop notifications for a task you are done with, without losing access."},
        "hi": {"t": "व्यस्त टास्क को म्यूट करें",
               "d": "जिस टास्क में आपका काम पूरा है, उसकी सूचनाएँ बंद करें — एक्सेस बना रहेगा।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "edit_task",
        "en": {"t": "Edit a task you created",
               "d": "Fix the title, description, category, due date or priority. Every change is logged."},
        "hi": {"t": "अपना बनाया टास्क एडिट करें",
               "d": "टाइटल, विवरण, कैटेगरी, ड्यू डेट या प्राथमिकता ठीक करें। हर बदलाव रिकॉर्ड होता है।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "leave_approvals",
        "en": {"t": "Approve leave and WFH requests",
               "d": "Review your team's requests and decide."},
        "hi": {"t": "छुट्टी और WFH रिक्वेस्ट अप्रूव करें",
               "d": "अपनी टीम की रिक्वेस्ट देखें और निर्णय लें।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "reassign_task",
        "en": {"t": "Reassign, merge or delete tasks",
               "d": "Move work to someone else or clean up duplicates."},
        "hi": {"t": "टास्क री-असाइन, मर्ज या डिलीट करें",
               "d": "काम किसी और को दें या डुप्लीकेट हटाएँ।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "claims_accounts",
        "en": {"t": "Work on claims, accounts and branches",
               "d": "The full case records and customer information."},
        "hi": {"t": "क्लेम, अकाउंट और ब्रांच पर काम करें",
               "d": "पूरे केस रिकॉर्ड और ग्राहक जानकारी।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "manage_categories",
        "en": {"t": "Manage task categories",
               "d": "Add, rename or retire categories, and set which ones need complainant details."},
        "hi": {"t": "टास्क कैटेगरी मैनेज करें",
               "d": "कैटेगरी जोड़ें, नाम बदलें या हटाएँ, और तय करें किसमें शिकायतकर्ता की जानकारी ज़रूरी है।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "manage_staff",
        "en": {"t": "Manage staff and permissions",
               "d": "Add people, set roles, and control who can assign tasks."},
        "hi": {"t": "स्टाफ और अनुमतियाँ मैनेज करें",
               "d": "लोगों को जोड़ें, भूमिकाएँ तय करें, और तय करें कौन टास्क सौंप सकता है।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "system_health",
        "en": {"t": "See revenue, app health and settings",
               "d": "Business numbers and system status."},
        "hi": {"t": "रेवेन्यू, ऐप हेल्थ और सेटिंग्स देखें",
               "d": "व्यापार के आंकड़े और सिस्टम की स्थिति।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "connect_telegram",
        "en": {"t": "Connect your Telegram",
               "d": "One tap in the portal links the bot to you — do this once."},
        "hi": {"t": "अपना टेलीग्राम कनेक्ट करें",
               "d": "पोर्टल में एक टैप से बॉट आपसे जुड़ जाता है — यह एक बार करना है।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
]


def _allowed(role: str, cap: dict) -> bool:
    return ROLE_RANK.get(role, -1) >= ROLE_RANK.get(cap.get("min_role", "team_member"), 99)


def build_guide(role: str, lang: str = "en") -> dict:
    """Role-filtered guide, split by WHERE each thing can be done."""
    lang = "hi" if str(lang).lower().startswith("hi") else "en"
    caps = [c for c in CAPABILITIES if _allowed(role, c)]
    def _fmt(c):
        body = c.get(lang) or c["en"]
        return {"id": c["id"], "title": body["t"], "detail": body["d"]}
    return {
        "role": role,
        "lang": lang,
        "telegram": [_fmt(c) for c in caps if c["telegram"]],
        "web_only": [_fmt(c) for c in caps if not c["telegram"] and c["web"]],
        "counts": {
            "telegram": sum(1 for c in caps if c["telegram"]),
            "web_only": sum(1 for c in caps if not c["telegram"] and c["web"]),
        },
    }


def speech_text(role: str, lang: str = "en") -> str:
    """The narration read aloud. Generated from the SAME entries as the on-screen
    guide, so the audio can never describe a feature that no longer exists."""
    g = build_guide(role, lang)
    hi = g["lang"] == "hi"
    role_label = {"team_member": ("team member", "टीम मेंबर"),
                  "sub_super_admin": ("admin", "एडमिन"),
                  "super_admin": ("super admin", "सुपर एडमिन")}.get(role, ("staff", "स्टाफ"))
    if hi:
        parts = [f"नमस्ते। आप {role_label[1]} हैं। सुनिए आप क्या-क्या कर सकते हैं।",
                 "पहले, टेलीग्राम बॉट से आप ये काम कर सकते हैं।"]
        parts += [f"{i}. {c['title']}। {c['detail']}" for i, c in enumerate(g["telegram"], 1)]
        parts.append("अब वे काम जो सिर्फ़ वेब पोर्टल या ऐप से होते हैं।")
        parts += [f"{i}. {c['title']}। {c['detail']}" for i, c in enumerate(g["web_only"], 1)]
        parts.append("बस इतना ही। कोई भी सवाल हो तो टेलीग्राम पर सीधे पूछ सकते हैं।")
    else:
        parts = [f"Hello. You are a {role_label[0]}. Here is what you can do.",
                 "First, the things you can do from the Telegram bot."]
        parts += [f"{i}. {c['title']}. {c['detail']}" for i, c in enumerate(g["telegram"], 1)]
        parts.append("Now, the things that can only be done in the web portal or the installed app.")
        parts += [f"{i}. {c['title']}. {c['detail']}" for i, c in enumerate(g["web_only"], 1)]
        parts.append("That's everything. If you have a question, just ask the bot on Telegram.")
    return " ".join(parts)


def telegram_help_text(role: str, lang: str = "en") -> str:
    """❓ Help inside the bot — same registry, Telegram formatting."""
    g = build_guide(role, lang)
    hi = g["lang"] == "hi"
    lines = ["*❓ " + ("आप क्या कर सकते हैं" if hi else "What you can do") + "*",
             "\n" + ("✅ *यहाँ टेलीग्राम पर:*" if hi else "✅ *Here in Telegram:*")]
    lines += [f"• {c['title']}" for c in g["telegram"]]
    lines.append("\n" + ("🌐 *सिर्फ़ वेब पोर्टल / ऐप पर:*" if hi else "🌐 *Only in the web portal / app:*"))
    lines += [f"• {c['title']}" for c in g["web_only"]]
    lines.append("\n" + ("_पूरी जानकारी और ऑडियो गाइड पोर्टल में 'How to use' में है।_"
                         if hi else
                         "_Full guide with audio is in the portal under 'How to use'._"))
    return "\n".join(lines)
