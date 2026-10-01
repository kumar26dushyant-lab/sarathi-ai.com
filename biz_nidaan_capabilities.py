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
    # ── WhatsApp inbox ───────────────────────────────────────────
    {
        "id": "wa_inbox",
        "en": {"t": "Read every WhatsApp chat in one place",
               "d": "Each customer is one conversation, not a row in a log. You can see whether "
                    "the AI or a person is replying, read exactly what the AI said, and take a "
                    "chat over yourself — the AI then stops replying until you hand it back."},
        "hi": {"t": "हर WhatsApp चैट एक जगह पढ़ें",
               "d": "हर ग्राहक की एक पूरी बातचीत दिखती है। आप देख सकते हैं कि AI जवाब दे रहा है या कोई व्यक्ति, "
                    "AI ने क्या कहा वह पढ़ सकते हैं, और चैट खुद संभाल सकते हैं — फिर AI जवाब देना बंद कर देता है।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
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
    {
        # Telegram → 📎 Send claim documents. Reuses the same intake as the web and
        # WhatsApp, so a document sent from a phone is checked exactly as strictly.
        "id": "telegram_doc_upload",
        "en": {"t": "Send claim documents from Telegram",
               "d": "Send the claim number, then the photo or PDF. The bot shows what the claim "
                    "already has, warns if it looks like a duplicate or is hard to read, and "
                    "waits for your yes before saving."},
        "hi": {"t": "टेलीग्राम से क्लेम के डॉक्यूमेंट भेजें",
               "d": "क्लेम नंबर भेजें, फिर फ़ोटो या PDF। बॉट बताएगा कि क्लेम "
                    "में क्या पहले से है, डुप्लिकेट या धुंधला होने पर चेताएगा, और "
                    "सेव करने से पहले आपसे पूछेगा।"},
        "telegram": True, "web": False, "min_role": "team_member",
    },
    {
        # Telegram → ✂️ Split a mixed PDF. Nothing is saved to a claim by this.
        "id": "telegram_doc_split",
        "en": {"t": "Split a mixed PDF on Telegram",
               "d": "Send one PDF holding several documents and the bot separates them, names "
                    "each one and sends them back to check. Nothing is saved to any claim."},
        "hi": {"t": "टेलीग्राम पर मिले-जुले PDF को अलग करें",
               "d": "एक PDF भेजें जिसमें कई डॉक्यूमेंट हों — बॉट उन्हें अलग करके, "
                    "नाम के साथ वापस भेजेगा। किसी क्लेम में कुछ सेव नहीं होता।"},
        "telegram": True, "web": False, "min_role": "team_member",
    },
    {
        # Telegram → 🌐 Bhasha, and the same setting on the web profile.
        "id": "telegram_language_choice",
        "en": {"t": "Use the bot in English, Hindi or Hinglish",
               "d": "Pick your language and every message changes with it — including "
                    "Hinglish, which is Hindi in Roman letters, so no Hindi keyboard is needed."},
        "hi": {"t": "बॉट को अंग्रेज़ी, हिंदी या हिंग्लिश में चलाएं",
               "d": "अपनी भाषा चुनिए — सारे मैसेज उसी में आएंगे। हिंग्लिश यानी "
                    "रोमन अक्षरों में हिंदी — हिंदी कीबोर्ड की ज़रूरत नहीं।"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        # ✈️ Telegram Bot → one button, everyone who has not connected yet is asked to.
        "id": "telegram_invite_all",
        "en": {"t": "Ask everyone to connect Telegram",
               "d": "One button tells every colleague who has not connected yet how to, on "
                    "their bell and by email, in English and Hindi. Needed after the bot changes."},
        "hi": {"t": "सबको टेलीग्राम जोड़ने को कहें",
               "d": "एक बटन से उन सब को सूचना जाती है जिन्होंने अभी टेलीग्राम "
                    "नहीं जोड़ा — घंटी और ईमेल पर, हिंदी और अंग्रेज़ी दोनों में।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        # Settings → 🔔 Notifications. The whole list, with a tickbox per job on every row.
        "id": "notification_control",
        "en": {"t": "Decide who is told what",
               "d": "Every message the system can send, in one list. Untick a box to stop it for "
                    "a whole job. Money, security and health cannot be switched off."},
        "hi": {"t": "तय करें किसे क्या सूचना जाए",
               "d": "सिस्टम जो भी मैसेज भेज सकता है, सब एक लिस्ट में। किसी रोल के लिए बंद करना हो "
                    "तो टिक हटा दें। पैसा, सुरक्षा और सिस्टम हेल्थ बंद नहीं हो सकते।"},
        "telegram": False, "web": True, "min_role": "super_admin",
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
        "en": {"t": "Work on claims, accounts and Authorized Partners",
               "d": "The full case records and customer information."},
        "hi": {"t": "क्लेम, अकाउंट और अधिकृत पार्टनर पर काम करें",
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
    # ── Claims & Level-2 (legal) ─────────────────────────────────────────
    {
        "id": "tg_find_claim",
        "en": {"t": "Find a claim from Telegram",
               "d": "Search any claim by number, customer name or phone — right in the bot.",
               "u": "On the move? Tap 🔎 Find a claim in the bot, type a name, and see its status instantly."},
        "hi": {"t": "टेलीग्राम से दावा खोजें",
               "d": "किसी भी दावे को नंबर, ग्राहक के नाम या फ़ोन से खोजें — बॉट में ही।",
               "u": "बाहर हैं? बॉट में 🔎 दावा खोजें दबाएँ, नाम लिखें, और तुरंत स्थिति देखें।"},
        "telegram": True, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "tg_my_numbers",
        "en": {"t": "See today's numbers from Telegram",
               "d": "A quick office snapshot in the bot: new claims today, open claims, L2 claims, your pending tasks.",
               "u": "Tap 📊 My numbers in the bot to see the day's key counts at a glance."},
        "hi": {"t": "टेलीग्राम से आज के आँकड़े देखें",
               "d": "बॉट में झटपट स्नैपशॉट: आज नए दावे, खुले दावे, L2 दावे, आपके पेंडिंग टास्क।",
               "u": "बॉट में 📊 मेरे आँकड़े दबाएँ और दिन के मुख्य आँकड़े एक नज़र में देखें।"},
        "telegram": True, "web": False, "min_role": "sub_super_admin",
    },
    {
        "id": "tg_claim_actions",
        "en": {"t": "Add a note or move a claim's stage from Telegram",
               "d": "From a claim in the bot, add an internal note or change its stage — with a confirm step.",
               "u": "Found a claim in the bot? Tap 💬 Add note or ➡️ Move stage — confirm, done, no laptop needed."},
        "hi": {"t": "टेलीग्राम से नोट जोड़ें या दावे का चरण बदलें",
               "d": "बॉट में किसी दावे से आंतरिक नोट जोड़ें या उसका चरण बदलें — पुष्टि के साथ।",
               "u": "बॉट में दावा मिला? 💬 नोट जोड़ें या ➡️ चरण बदलें दबाएँ — पुष्टि करें, हो गया, लैपटॉप की ज़रूरत नहीं।"},
        "telegram": True, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "deliver_review",
        "en": {"t": "Deliver a legal assessment to the customer",
               "d": "Share whether a claim can be challenged — the customer sees it on their dashboard.",
               "u": "After reviewing a rejection, pick an outcome, use a template, and send it in one tap."},
        "hi": {"t": "ग्राहक को कानूनी आकलन भेजें",
               "d": "बताएँ कि दावे को चुनौती दी जा सकती है या नहीं — ग्राहक को उसके डैशबोर्ड पर दिखता है।",
               "u": "रिजेक्शन देखने के बाद, नतीजा चुनें, टेम्पलेट लगाएँ और एक टैप में भेजें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "l2_claims",
        "en": {"t": "Level-2 (L2) Claims dashboard",
               "d": "All reviewed-GO claims ready for legal action, with fee + ClaimShield status.",
               "u": "See which claims are paid, send eligible ones to ClaimShield, and track their status."},
        "hi": {"t": "लेवल-2 (L2) क्लेम डैशबोर्ड",
               "d": "कानूनी कार्रवाई के लिए तैयार सभी दावे, फीस + ClaimShield स्थिति के साथ।",
               "u": "देखें कौन-से दावे भुगतान हो चुके हैं, पात्र दावे ClaimShield भेजें, और स्थिति ट्रैक करें।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "views_switch",
        "en": {"t": "Switch between Table, Board & Cards",
               "d": "See L2 claims as a table, a Kanban board (by stage), or mobile cards — your choice sticks.",
               "u": "On the phone, use the Board to drag your eye down stage-by-stage; on desktop, use columns."},
        "hi": {"t": "टेबल, बोर्ड और कार्ड्स में बदलें",
               "d": "L2 क्लेम को टेबल, कानबन बोर्ड (चरण अनुसार), या मोबाइल कार्ड्स में देखें — आपकी पसंद याद रहती है।",
               "u": "फ़ोन पर बोर्ड से चरण-दर-चरण देखें; डेस्कटॉप पर कॉलम इस्तेमाल करें।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "claimant_portal",
        "en": {"t": "Complainant Portal — the policyholder's own dashboard",
               "d": "Give the insured a private, Hindi-first page to track status, share documents, and accept fee terms.",
               "u": "When a claim reaches L2, open its Complainant Portal card and send the link — the customer uploads docs themselves."},
        "hi": {"t": "क्लेमेंट पोर्टल — पॉलिसीधारक का अपना डैशबोर्ड",
               "d": "बीमाधारक को एक निजी, हिंदी-प्रथम पेज दें — स्थिति देखें, दस्तावेज़ भेजें, फीस शर्तें स्वीकार करें।",
               "u": "दावा L2 पहुँचने पर उसका क्लेमेंट पोर्टल कार्ड खोलें और लिंक भेजें — ग्राहक खुद दस्तावेज़ अपलोड करता है।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    # ── Email Updates (radar) ────────────────────────────────────────────
    {
        "id": "email_updates",
        "en": {"t": "Email Updates — watch customer mailboxes",
               "d": "One screen watches all connected customer mailboxes; important emails are flagged, read & replied here.",
               "u": "Instead of logging into 100 Gmails, check 'Act now', read the email, and reply — without opening Gmail."},
        "hi": {"t": "ईमेल अपडेट्स — ग्राहक मेलबॉक्स पर नज़र",
               "d": "एक स्क्रीन सभी जुड़े ग्राहक मेलबॉक्स देखती है; ज़रूरी ईमेल फ़्लैग होते हैं, यहीं पढ़ें व जवाब दें।",
               "u": "100 Gmail खोलने के बजाय 'Act now' देखें, ईमेल पढ़ें और जवाब दें — Gmail खोले बिना।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    # ── Document Splitter ────────────────────────────────────────────────
    {
        "id": "email_radar_rules",
        "en": {"t": "Teach the radar what matters to you",
               "d": "Write your own rules in plain words \u2014 a sender, a word in the subject, or "
                    "anything in the mail. Whatever matches is raised as Act now, even if the AI "
                    "would have cleared it, and the row says which rule caught it.",
               "u": "Settings tab in Email Updates. Type one rule per line, e.g. subject: hearing."},
        "hi": {"t": "\u0930\u0921\u093e\u0930 \u0915\u094b \u0938\u093f\u0916\u093e\u090f\u0902 \u0915\u093f \u0906\u092a\u0915\u0947 \u0932\u093f\u090f \u0915\u094d\u092f\u093e \u091c\u093c\u0930\u0942\u0930\u0940 \u0939\u0948",
               "d": "\u0905\u092a\u0928\u0947 \u0928\u093f\u092f\u092e \u0938\u093e\u0926\u0947 \u0936\u092c\u094d\u0926\u094b\u0902 \u092e\u0947\u0902 \u0932\u093f\u0916\u093f\u090f \u2014 \u092d\u0947\u091c\u0928\u0947 \u0935\u093e\u0932\u093e, \u0938\u092c\u094d\u091c\u0947\u0915\u094d\u091f \u0915\u093e \u0915\u094b\u0908 \u0936\u092c\u094d\u0926, \u092f\u093e \u092e\u0947\u0932 \u092e\u0947\u0902 \u0915\u0941\u091b \u092d\u0940\u0964 \u092e\u0948\u091a \u0939\u094b\u0928\u0947 \u092a\u0930 \u0935\u0939 Act now \u092e\u0947\u0902 \u0906\u090f\u0917\u093e\u0964",
               "u": "Email Updates \u2192 Settings \u092e\u0947\u0902 \u090f\u0915 \u0932\u093e\u0907\u0928 \u092a\u0930 \u090f\u0915 \u0928\u093f\u092f\u092e\u0964"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "duty_roster_all_stages",
        "en": {"t": "Put someone on duty for any stage",
               "d": "The duty rota covers every bucket \u2014 Review, Conversion, Documents, Drafting, "
                    "With the insurer, Escalation, Ombudsman, Settlement \u2014 not just the two chat "
                    "channels. Whoever you roster sees that bucket under On duty today on Level-2 \u2192 Settlement.",
               "u": "Level-2 \u2192 Settlement \u2192 Set duty on any bucket, or Support \u2192 duty roster."},
        "hi": {"t": "\u0915\u093f\u0938\u0940 \u092d\u0940 \u0938\u094d\u091f\u0947\u091c \u0915\u0940 \u0921\u094d\u092f\u0942\u091f\u0940 \u0932\u0917\u093e\u090f\u0902",
               "d": "\u0921\u094d\u092f\u0942\u091f\u0940 \u0930\u094b\u0938\u094d\u091f\u0930 \u0905\u092c \u0939\u0930 \u092c\u0915\u0947\u091f \u0915\u0947 \u0932\u093f\u090f \u0939\u0948 \u2014 \u0938\u093f\u0930\u094d\u092b \u091a\u0948\u091f \u0915\u0947 \u0932\u093f\u090f \u0928\u0939\u0940\u0902\u0964 \u091c\u093f\u0938\u0947 \u0932\u0917\u093e\u090f\u0902\u0917\u0947 \u0909\u0938\u0947 Level-2 \u2192 Settlement \u092a\u0930 On duty today \u0926\u093f\u0916\u0947\u0917\u093e\u0964",
               "u": "Level-2 \u2192 Settlement \u2192 Set duty, \u092f\u093e Support \u2192 duty roster\u0964"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "doc_window",
        "en": {"t": "Ask a complainant for the documents we are missing",
               "d": "One screen: what the claim still needs, who the ask goes to, and the exact "
                    "words. The standard list comes from the claim type and you can add anything "
                    "else this case needs; removing something asks why, and your reason stays on "
                    "the claim. Documents that arrive turn green. Everyone involved \u2014 the "
                    "subscriber, the Authorized Partner, the channel partner \u2014 is copied, and you can "
                    "add or remove any mobile or email. Before it goes you read it back once, "
                    "and you are recorded as the person who sent it.",
               "u": "Level-2 \u2192 Settlement \u2192 click the document count on any row."},
        "hi": {"t": "\u0936\u093f\u0915\u093e\u092f\u0924\u0915\u0930\u094d\u0924\u093e \u0938\u0947 \u092c\u093e\u0915\u0940 \u0926\u0938\u094d\u0924\u093e\u0935\u0947\u091c\u093c \u092e\u093e\u0901\u0917\u0947\u0902",
               "d": "\u090f\u0915 \u0939\u0940 \u0938\u094d\u0915\u094d\u0930\u0940\u0928 \u092a\u0930: \u0915\u094d\u092f\u093e \u092c\u093e\u0915\u0940 \u0939\u0948, \u0915\u093f\u0938\u0947 \u092d\u0947\u091c\u0928\u093e \u0939\u0948, \u0914\u0930 \u0915\u094d\u092f\u093e \u0932\u093f\u0916\u0928\u093e \u0939\u0948\u0964 "
                    "\u0938\u094d\u091f\u0948\u0902\u0921\u0930\u094d\u0921 \u0932\u093f\u0938\u094d\u091f \u0915\u094d\u0932\u0947\u092e \u091f\u093e\u0907\u092a \u0938\u0947 \u0906\u0924\u0940 \u0939\u0948; \u0907\u0938 \u0915\u0947\u0938 \u0915\u094b \u091c\u094b \u0914\u0930 \u091a\u093e\u0939\u093f\u090f \u0935\u0939 \u091c\u094b\u0921\u093c \u0932\u0940\u091c\u093f\u090f\u0964 "
                    "\u0939\u091f\u093e\u0928\u0947 \u092a\u0930 \u0915\u093e\u0930\u0923 \u092a\u0942\u091b\u093e \u091c\u093e\u090f\u0917\u093e \u0914\u0930 \u0935\u0939 \u0915\u094d\u0932\u0947\u092e \u092a\u0930 \u0926\u0930\u094d\u091c \u0930\u0939\u0947\u0917\u093e\u0964 \u091c\u094b \u0906 \u0917\u092f\u093e \u0935\u0939 \u0939\u0930\u093e \u0939\u094b \u091c\u093e\u0924\u093e \u0939\u0948\u0964 "
                    "\u092d\u0947\u091c\u0928\u0947 \u0938\u0947 \u092a\u0939\u0932\u0947 \u090f\u0915 \u092c\u093e\u0930 \u092a\u0922\u093c\u0915\u0930 \u092a\u0941\u0937\u094d\u091f\u093f \u0915\u0930\u0928\u0940 \u0939\u094b\u0917\u0940, \u0914\u0930 \u092d\u0947\u091c\u0928\u0947 \u0935\u093e\u0932\u0947 \u0915\u093e \u0928\u093e\u092e \u0926\u0930\u094d\u091c \u0939\u094b\u0924\u093e \u0939\u0948\u0964",
               "u": "Level-2 \u2192 Settlement \u2192 \u0915\u093f\u0938\u0940 \u092d\u0940 \u0930\u094b \u092a\u0930 \u0921\u0949\u0915\u094d\u092f\u0942\u092e\u0947\u0902\u091f \u0915\u093e\u0909\u0902\u091f \u092a\u0930 \u0915\u094d\u0932\u093f\u0915 \u0915\u0930\u0947\u0902\u0964"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "doc_chase",
        "en": {"t": "Reminders that stop, and become a phone call",
               "d": "After an ask goes out we remind every three days \u2014 twice. Then we stop "
                    "sending and put it on your bell and Telegram to PHONE them, because a "
                    "fourth identical message is what makes somebody stop reading us "
                    "altogether. Every reminder says: if you have already shared all the "
                    "documents, please ignore this message. Write down what they said on the "
                    "call and the chase closes.",
               "u": "It runs by itself; the window shows the next reminder date."},
        "hi": {"t": "\u0930\u093f\u092e\u093e\u0907\u0902\u0921\u0930 \u0930\u0941\u0915\u0924\u0947 \u0939\u0948\u0902, \u092b\u093f\u0930 \u092b\u093c\u094b\u0928 \u0915\u0930\u0928\u093e \u0939\u094b\u0924\u093e \u0939\u0948",
               "d": "\u092e\u093e\u0901\u0917 \u092d\u0947\u091c\u0928\u0947 \u0915\u0947 \u092c\u093e\u0926 \u0939\u0930 \u0924\u0940\u0928 \u0926\u093f\u0928 \u092e\u0947\u0902 \u092f\u093e\u0926 \u0926\u093f\u0932\u093e\u0924\u0947 \u0939\u0948\u0902 \u2014 \u0938\u093f\u0930\u094d\u092b\u093c \u0926\u094b \u092c\u093e\u0930\u0964 \u0909\u0938\u0915\u0947 \u092c\u093e\u0926 \u092d\u0947\u091c\u0928\u093e \u092c\u0902\u0926 "
                    "\u0914\u0930 \u0906\u092a\u0915\u094b \u092c\u0947\u0932 \u0914\u0930 \u091f\u0947\u0932\u0940\u0917\u094d\u0930\u093e\u092e \u092a\u0930 \u092b\u093c\u094b\u0928 \u0915\u0930\u0928\u0947 \u0915\u094b \u0915\u0939\u093e \u091c\u093e\u090f\u0917\u093e \u2014 \u091a\u094c\u0925\u093e \u0935\u0948\u0938\u093e \u0939\u0940 \u092e\u0948\u0938\u0947\u091c \u0932\u094b\u0917\u094b\u0902 \u0938\u0947 "
                    "\u0939\u092e\u093e\u0930\u093e \u092a\u0922\u093c\u0928\u093e \u0939\u0940 \u091b\u0941\u0921\u093c\u093e \u0926\u0947\u0924\u093e \u0939\u0948\u0964 \u0939\u0930 \u0930\u093f\u092e\u093e\u0907\u0902\u0921\u0930 \u092e\u0947\u0902 \u0932\u093f\u0916\u093e \u0939\u094b\u0924\u093e \u0939\u0948: \u092f\u0926\u093f \u0906\u092a \u0938\u092d\u0940 \u0926\u0938\u094d\u0924\u093e\u0935\u0947\u091c\u093c "
                    "\u092d\u0947\u091c \u091a\u0941\u0915\u0947 \u0939\u0948\u0902 \u0924\u094b \u0907\u0938 \u0938\u0902\u0926\u0947\u0936 \u0915\u094b \u0928\u091c\u093c\u0930\u0905\u0902\u0926\u093e\u091c\u093c \u0915\u0930\u0947\u0902\u0964",
               "u": "\u092f\u0939 \u0916\u0941\u0926 \u091a\u0932\u0924\u093e \u0939\u0948; \u0905\u0917\u0932\u0940 \u0924\u093e\u0930\u0940\u0916\u093c \u0935\u093f\u0902\u0921\u094b \u092e\u0947\u0902 \u0926\u093f\u0916\u0924\u0940 \u0939\u0948\u0964"},
        "telegram": True, "web": True, "min_role": "team_member",
    },
    {
        "id": "bucket_designer",
        "en": {"t": "Change the Level-2 process yourself",
               "d": "Create a bucket, rename one, change how many days before it turns amber or "
                    "red, write what staff are told it is for, add or retire the steps inside it "
                    "and the fields captured in it, and open or close the usual next steps \u2014 "
                    "all without a release. Nothing is ever deleted while it holds work: a bucket "
                    "with claims refuses to be turned off, and a field somebody has already "
                    "answered is turned off instead, keeping every answer already recorded.",
               "u": "Bucket Designer \u2192 Change on any bucket."},
        "hi": {"t": "Level-2 प्रोसेस खुद बदलें",
               "d": "नया बकेट बनाएँ, नाम बदलें, कितने दिन बाद अंबर/रेड हो यह तय करें, स्टाफ़ को क्या बताना है "
                    "वह लिखें, अंदर के स्टेप और फ़ील्ड जोड़ें या बंद करें, और अगला कदम खोलें या हटाएँ \u2014 "
                    "बिना किसी रिलीज़ के। जिसमें काम पड़ा है वह कभी डिलीट नहीं होता: क्लेम वाला बकेट बंद "
                    "नहीं होगा, और जिस फ़ील्ड का जवाब भरा जा चुका है वह सिर्फ़ बंद होगा \u2014 जवाब सुरक्षित रहेंगे।",
               "u": "Bucket Designer \u2192 किसी बकेट पर Change।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "case_record",
        "en": {"t": "The case record: gist, drafts and case report",
               "d": "Open any Level-2 case and its record fills in as the case moves: the gist "
                    "(policy number and inception date included), the Initial Claim Assessment "
                    "Sheet, the Draft and the Lokpal Draft in two big boxes side by side, and "
                    "the Case Report that puts it all on one page. Click any document to read it "
                    "right there - PDFs and photos open in the page, nothing to download. "
                    "Full claim opens the claim in its own window, so the two sit side by side.",
               "u": "Consolidation → Open on any case."},
        "hi": {"t": "केस रिकॉर्ड: गिस्ट, ड्राफ़्ट और केस रिपोर्ट",
               "d": "Level-2 का कोई भी केस खोलिए - केस आगे बढ़ने के साथ उसका रिकॉर्ड भरता जाता है: गिस्ट "
                    "(पॉलिसी नंबर और पॉलिसी शुरू होने की तारीख के साथ), शुरुआती क्लेम आकलन शीट, Draft और "
                    "Lokpal Draft दो बड़े बॉक्स में साथ-साथ, और केस रिपोर्ट जिसमें सब एक पेज पर है। किसी भी "
                    "दस्तावेज़ पर क्लिक करें, वहीं पढ़ें - PDF और फ़ोटो पेज में ही खुलते हैं, डाउनलोड नहीं करना पड़ता। "
                    "Full claim क्लेम को अलग विंडो में खोलता है, ताकि दोनों साथ-साथ दिखें।",
               "u": "Consolidation → किसी भी केस पर Open।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "finished_work_locks",
        "en": {"t": "Finished work locks; ask for a change",
               "d": "Once a claim moves past a bucket, that bucket's work is locked, so nobody later "
                    "changes it by mistake. The gist stays open until the drafts are finished, then "
                    "locks with them. Only the three super admins can change locked work, and every "
                    "change is recorded. If something needs fixing, press Request a change: the super "
                    "admins are told at once and the request goes into the claim's remarks. When a claim "
                    "is sent back, it is flagged with who sent it and why, and that bucket's work opens "
                    "again. Nothing already recorded is erased.",
               "u": "Consolidation → open a case → Request a change on locked work."},
        "hi": {"t": "पूरा हुआ काम लॉक; बदलाव माँगें",
               "d": "क्लेम किसी बकेट से आगे बढ़ते ही उस बकेट का काम लॉक हो जाता है, ताकि बाद में कोई गलती से उसे न बदले। "
                    "गिस्ट ड्राफ़्ट पूरे होने तक खुला रहता है, फिर उनके साथ लॉक होता है। लॉक काम सिर्फ़ तीन सुपर एडमिन बदल "
                    "सकते हैं और हर बदलाव दर्ज होता है। कुछ ठीक करना हो तो Request a change दबाएँ: सुपर एडमिन को तुरंत "
                    "खबर जाती है और अनुरोध क्लेम के रिमार्क्स में दर्ज होता है। क्लेम वापस भेजा जाए तो उस पर लिखा आता है "
                    "कि किसने और क्यों भेजा, और उस बकेट का काम फिर खुल जाता है। पहले से दर्ज कुछ भी मिटता नहीं।",
               "u": "Consolidation → केस खोलें → लॉक काम पर Request a change।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "draft_query",
        "en": {"t": "Draft query: send a claim back, and make sure it is answered",
               "d": "In Pending Draft, the doctor or advocate can Raise a query: the claim goes back to "
                    "Live Cases marked DRAFT QUERY, at the top of the list, and Live Cases is told at "
                    "once. It is reminded every morning while open, and the super admins are told after "
                    "3 days. Live Cases presses Query resolved, picks the doctor or advocate, and it goes "
                    "back to them in Pending Draft.",
               "u": "Consolidation → Pending Draft → ❓ Query; Live Cases → ✅ Resolved."},
        "hi": {"t": "ड्राफ़्ट क्वेरी: क्लेम वापस भेजें, और जवाब पक्का करें",
               "d": "Pending Draft में डॉक्टर या एडवोकेट Raise a query दबा सकते हैं: क्लेम Live Cases में "
                    "DRAFT QUERY लिखकर सबसे ऊपर लौटता है और Live Cases को तुरंत खबर जाती है। खुली रहने तक हर "
                    "सुबह याद दिलाया जाता है, 3 दिन बाद सुपर एडमिन को भी। Live Cases Query resolved दबाकर "
                    "डॉक्टर/एडवोकेट चुनता है और क्लेम उन्हीं के पास Pending Draft में लौटता है।",
               "u": "Consolidation → Pending Draft → ❓ Query; Live Cases → ✅ Resolved।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "ask_complainant",
        "en": {"t": "Ask the complainant one thing",
               "d": "From any Level-2 case: call them, or send ONE query message on WhatsApp (our "
                    "approved message carrying your exact words) and email, copied by email to the "
                    "Authorized Partner or subscriber. A second message is refused while the first is unanswered, "
                    "so nobody is bombarded. When they reply on WhatsApp, the super admins and you are "
                    "told at once.",
               "u": "Consolidation → open a case → Contact the complainant."},
        "hi": {"t": "शिकायतकर्ता से एक बात पूछें",
               "d": "Level-2 के किसी भी केस से: कॉल करें, या WhatsApp पर एक क्वेरी संदेश भेजें (हमारा "
                    "मंज़ूर संदेश, आपके शब्दों के साथ) और ईमेल, जिसकी कॉपी अधिकृत पार्टनर/सब्सक्राइबर को ईमेल से जाती है। "
                    "पहले का जवाब आने तक दूसरा संदेश नहीं जाता। WhatsApp पर जवाब आते ही सुपर एडमिन और आपको खबर मिलती है।",
               "u": "Consolidation → केस खोलें → Contact the complainant।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "propose_channel_partner",
        "en": {"t": "Propose a Channel Partner",
               "d": "Any staff member can add a partner who sends us business \u2014 they are the "
                    "people who actually meet them. It waits as PENDING and cannot be put on a "
                    "claim until a super-admin approves it, and who approved it is recorded, "
                    "because this is a name commission gets paid against. You keep seeing your "
                    "own proposal while it waits.",
               "u": "Channel Partners \u2192 + Add partner."},
        "hi": {"t": "Channel Partner का नाम भेजें",
               "d": "जो पार्टनर हमें काम भेजते हैं, उनका नाम कोई भी स्टाफ़ जोड़ सकता है \u2014 मिलते तो वही हैं। "
                    "नाम PENDING रहेगा और सुपर-एडमिन की मंज़ूरी से पहले किसी क्लेम पर नहीं लगेगा, और किसने "
                    "मंज़ूरी दी यह दर्ज होता है, क्योंकि इसी नाम पर कमीशन जाता है। आपका भेजा नाम आपको दिखता रहेगा।",
               "u": "Channel Partners \u2192 + Add partner।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "l2_pipeline",
        "en": {"t": "Move a Level-2 case bucket by bucket",
               "d": "A paid, winnable case is handed over from L2 Claims, then moves "
                    "Live Cases \u2192 Pending Documents \u2192 Pending Draft \u2192 Reimbursement \u2192 "
                    "Escalation \u2192 Lokpal \u2192 Completed \u2192 Pending Payment \u2192 Finished. "
                    "Only cases whose Level-2 has been started appear in those buckets, and every "
                    "move \u2014 forward, back, or straight to any other bucket \u2014 needs a note "
                    "saying what is done and what is still pending.",
               "u": "Level-2 \u2192 Settlement \u2192 pick a bucket \u2192 Move."},
        "hi": {"t": "Level-2 केस को बकेट-दर-बकेट आगे बढ़ाएँ",
               "d": "फ़ीस मिली और केस मज़बूत है \u2014 तब L2 Claims से हैंडओवर होकर केस पाइपलाइन में आता है "
                    "और एक-एक बकेट आगे बढ़ता है। बकेट में सिर्फ़ वही केस दिखते हैं जिनका Level-2 शुरू हो "
                    "चुका है, और हर मूव पर \u2014 आगे, पीछे, या किसी भी बकेट में \u2014 कमेंट ज़रूरी है।",
               "u": "Level-2 \u2192 Settlement \u2192 बकेट चुनें \u2192 Move।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "cover_a_bucket",
        "en": {"t": "Know when a bucket has nobody to work it",
               "d": "Level-2 \u2192 Settlement names any bucket with work waiting and nobody who will actually be "
                    "there \u2014 including the case where the rota shows a name but that person is "
                    "on leave today, or goes on leave within a fortnight.",
               "u": "Level-2 \u2192 Settlement \u2192 Today strip \u2192 not covered \u2192 Set duty."},
        "hi": {"t": "जानें कि किस बकेट पर कोई मौजूद नहीं",
               "d": "Level-2 \u2192 Settlement बताता है कि किस बकेट में काम है पर करने वाला कोई नहीं \u2014 उस हालत में भी "
                    "जब रोस्टर में नाम है पर वह व्यक्ति आज छुट्टी पर है।",
               "u": "Level-2 \u2192 Settlement \u2192 Today \u2192 not covered \u2192 ड्यूटी लगाएँ।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "raise_for_subscriber",
        "en": {"t": "Raise a claim for a subscriber who rings up",
               "d": "For a subscriber who will not use the dashboard. The claim goes onto their "
                    "account and uses their own quota, and permanently records which staff member "
                    "actually raised it.",
               "u": "Work \u2192 Raise for a Subscriber."},
        "hi": {"t": "फ़ोन करने वाले सब्सक्राइबर के लिए क्लेम दर्ज करें",
               "d": "जो सब्सक्राइबर डैशबोर्ड इस्तेमाल नहीं करते, उनके लिए। क्लेम उन्हीं के खाते और कोटे में "
                    "जाता है, और रिकॉर्ड रहता है कि किस स्टाफ़ ने दर्ज किया।",
               "u": "Work \u2192 Raise for a Subscriber।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    {
        "id": "doc_splitter",
        "en": {"t": "Document Splitter",
               "d": "Upload up to 40 files at once (30 MB each) - PDFs, photos including iPhone HEIC, Word and Excel. They are read on our own server (no AI, nothing leaves) in the background while you get on with other work; a file holding several documents is read page by page. You check each page before sending to authorities.",
               "u": "Choose the files; watch the count; leave the page if you like - you get a notice when it is ready. Check each page, then download the set."},
        "hi": {"t": "डॉक्यूमेंट स्प्लिटर",
               "d": "ग्राहक की मिली-जुली फ़ाइल अपलोड करें; पेज हमारे अपने सर्वर पर पढ़े जाते हैं (कोई AI नहीं, कुछ बाहर नहीं जाता) और अलग-अलग दस्तावेज़ों में बाँटे जाते हैं — भेजने से पहले आप जाँचते हैं।",
               "u": "एक बड़ी PDF में डिस्चार्ज + बिल + रिपोर्ट? अपलोड करें, हर पेज जाँचें, और अलग PDF एक्सपोर्ट करें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "claim_doc_sets",
        "en": {"t": "Ready-to-send sets, on the claim itself",
               "d": "The documents already on a claim are read (on our server, no AI) and arranged into three PDFs: CIO documents, everything merged, and the claim set. A document we are not sure about is named and held for a person. Change what any page is, or press \u201cDon't send\u201d to keep a page out of every set \u2014 it stays listed, and the remark says who. The download is always exactly what the screen shows \u2014 as one PDF, or one PDF per document in a zip (claim form, discharge summary, final bill...).",
               "u": "Open a claim \u2192 Documents \u2192 Ready to send \u2192 One PDF, or Each document (zip). \u201cArrange this claim automatically\u201d is off unless you turn it on."},
        "hi": {"t": "भेजने के लिए तैयार सेट, क्लेम पर ही",
               "d": "क्लेम पर पहले से मौजूद दस्तावेज़ हमारे सर्वर पर पढ़े जाते हैं (कोई AI नहीं) और तीन PDF में लगाए जाते हैं: CIO दस्तावेज़, सब एक साथ, और क्लेम सेट। जिस दस्तावेज़ पर भरोसा नहीं, उसका नाम लिखकर इंसान के लिए रोका जाता है। किसी भी पेज को बदलिए, या \u201cDon't send\u201d दबाकर पेज को हर सेट से बाहर रखिए \u2014 वह सूची में दिखता रहता है, और रिमार्क में लिखा होता है किसने किया। डाउनलोड हमेशा वही होता है जो स्क्रीन पर है \u2014 एक PDF में, या हर दस्तावेज़ की अलग PDF एक zip में (क्लेम फ़ॉर्म, डिस्चार्ज समरी, फ़ाइनल बिल...)।",
               "u": "क्लेम खोलें \u2192 Documents \u2192 Ready to send। \u201cArrange this claim automatically\u201d तब तक बंद है जब तक आप चालू न करें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    # ── Business Analytics ───────────────────────────────────────────────
    {
        "id": "analytics",
        "en": {"t": "Business Analytics",
               "d": "Channel attribution, funnels and where claims/leads drop off.",
               "u": "See which branches/advisors bring the most business and where customers abandon."},
        "hi": {"t": "बिज़नेस एनालिटिक्स",
               "d": "चैनल एट्रिब्यूशन, फ़नल और कहाँ दावे/लीड छूटते हैं।",
               "u": "देखें कौन-से अधिकृत पार्टनर/सलाहकार सबसे ज़्यादा बिज़नेस लाते हैं और ग्राहक कहाँ छोड़ते हैं।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    # ── Content ──────────────────────────────────────────────────────────
    {
        "id": "content_editor",
        "en": {"t": "Content & Complainant Terms",
               "d": "Edit homepage facts, offices, and the complainant fee % + Terms (Nidaan The Legal Consultants LLP).",
               "u": "Change a business fact once — the website and chat assistant both update. Set the success-fee terms here."},
        "hi": {"t": "कंटेंट व क्लेमेंट शर्तें",
               "d": "होमपेज तथ्य, कार्यालय, और क्लेमेंट फीस % + शर्तें (Nidaan The Legal Consultants LLP) संपादित करें।",
               "u": "एक बार तथ्य बदलें — वेबसाइट और चैट असिस्टेंट दोनों अपडेट। सक्सेस-फीस शर्तें यहीं तय करें।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    # ══ SUBSCRIBER / ADVISOR DASHBOARD (nidaanpartner.com/dashboard) ══════════
    # audience="subscriber" → shown on the advisor's own dashboard, NOT the staff ops guide.
    {
        "id": "sub_raise_claim", "audience": ["subscriber"],
        "en": {"t": "Raise a claim for your client",
               "d": "Submit a rejected/short-settled insurance claim to our legal team.",
               "u": "Client's claim was denied? Enter the details here and we take it forward."},
        "hi": {"t": "अपने ग्राहक का दावा दर्ज करें",
               "d": "अस्वीकृत/कम-निपटाए बीमा दावे को हमारी कानूनी टीम को भेजें।",
               "u": "ग्राहक का दावा अस्वीकार हुआ? यहाँ विवरण भरें, आगे हम संभालते हैं।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "sub_track_status", "audience": ["subscriber"],
        "en": {"t": "Track claim status live",
               "d": "See each claim's current stage and history, updated as we work.",
               "u": "Open a claim any time to see exactly where it has reached."},
        "hi": {"t": "दावे की स्थिति लाइव देखें",
               "d": "हर दावे का मौजूदा चरण व इतिहास देखें, जैसे-जैसे हम काम करते हैं।",
               "u": "किसी भी समय दावा खोलकर देखें कि वह कहाँ तक पहुँचा।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "sub_docs", "audience": ["subscriber"],
        "en": {"t": "Share documents",
               "d": "Upload policy, rejection letter, bills and reports for a claim.",
               "u": "Snap a photo or attach a PDF — our team gets it instantly."},
        "hi": {"t": "दस्तावेज़ साझा करें",
               "d": "किसी दावे के लिए पॉलिसी, रिजेक्शन लेटर, बिल व रिपोर्ट अपलोड करें।",
               "u": "फ़ोटो खींचें या PDF लगाएँ — हमारी टीम को तुरंत मिल जाता है।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "sub_review", "audience": ["subscriber"],
        "en": {"t": "Get a legal assessment (₹499)",
               "d": "Our legal team reviews whether a claim can be challenged and tells you.",
               "u": "Unsure if a rejection is worth fighting? Get a paid expert review first."},
        "hi": {"t": "कानूनी आकलन पाएँ (₹499)",
               "d": "हमारी कानूनी टीम बताती है कि दावे को चुनौती दी जा सकती है या नहीं।",
               "u": "पक्का नहीं कि लड़ना ठीक है? पहले विशेषज्ञ समीक्षा लें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "sub_messages", "audience": ["subscriber"],
        "en": {"t": "Message our team",
               "d": "Chat with our associates on any claim — replies come to your dashboard.",
               "u": "Have a question on a case? Send a message right on that claim."},
        "hi": {"t": "हमारी टीम को संदेश भेजें",
               "d": "किसी भी दावे पर हमारे सहयोगियों से बात करें — जवाब डैशबोर्ड पर आते हैं।",
               "u": "किसी केस पर सवाल? उसी दावे पर संदेश भेजें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "sub_notifications", "audience": ["subscriber"],
        "en": {"t": "Updates on every channel",
               "d": "Get claim updates by dashboard, email and WhatsApp — never miss a step.",
               "u": "We reach out the moment something needs you or a claim moves."},
        "hi": {"t": "हर चैनल पर अपडेट",
               "d": "दावे के अपडेट डैशबोर्ड, ईमेल व WhatsApp पर पाएँ — कोई कदम न छूटे।",
               "u": "जैसे ही कुछ ज़रूरी हो या दावा आगे बढ़े, हम आपको बताते हैं।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    # ══ BRANCH / AFFILIATE PORTAL (nidaanpartner.com/nidaan/branch) ═══════════
    {
        "id": "br_raise_claim", "audience": ["branch"],
        "en": {"t": "Raise a claim for a policyholder",
               "d": "Submit a rejected claim on behalf of a client you brought in.",
               "u": "Your client's claim was denied? Enter it here and our legal team takes over."},
        "hi": {"t": "पॉलिसीधारक का दावा दर्ज करें",
               "d": "अपने लाए ग्राहक की ओर से अस्वीकृत दावा भेजें।",
               "u": "ग्राहक का दावा अस्वीकार हुआ? यहाँ दर्ज करें, आगे हमारी कानूनी टीम संभालती है।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "br_track", "audience": ["branch"],
        "en": {"t": "Track your claims & their status",
               "d": "See every claim you raised and where it has reached, including Level-2.",
               "u": "Open any claim to check its current stage any time."},
        "hi": {"t": "अपने दावे व उनकी स्थिति देखें",
               "d": "आपके भेजे हर दावे की स्थिति देखें, Level-2 सहित।",
               "u": "किसी भी समय दावा खोलकर उसका मौजूदा चरण देखें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "br_docs", "audience": ["branch"],
        "en": {"t": "Upload documents for a claim",
               "d": "Attach the rejection letter, policy and bills for a claim you raised.",
               "u": "Snap a photo of the rejection letter and upload it right on the claim."},
        "hi": {"t": "दावे के लिए दस्तावेज़ अपलोड करें",
               "d": "अपने भेजे दावे के लिए रिजेक्शन लेटर, पॉलिसी व बिल लगाएँ।",
               "u": "रिजेक्शन लेटर की फ़ोटो खींचकर सीधे दावे पर अपलोड करें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "br_earnings", "audience": ["branch"],
        "en": {"t": "See your earnings & referrals",
               "d": "Track the business you referred, your share % and payouts.",
               "u": "Check how much you've earned and which accounts are attributed to you."},
        "hi": {"t": "अपनी कमाई व रेफ़रल देखें",
               "d": "आपके लाए बिज़नेस, आपका हिस्सा % और भुगतान देखें।",
               "u": "देखें आपने कितना कमाया और कौन-से अकाउंट आपके नाम हैं।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "br_share", "audience": ["branch"],
        "en": {"t": "Share your referral link",
               "d": "Invite advisors/clients with your own link so business is credited to you.",
               "u": "Send your link on WhatsApp — anyone who signs up is tagged to your Authorized Partner code."},
        "hi": {"t": "अपना रेफ़रल लिंक साझा करें",
               "d": "अपने लिंक से सलाहकार/ग्राहक जोड़ें ताकि बिज़नेस आपके नाम दर्ज हो।",
               "u": "अपना लिंक WhatsApp पर भेजें — जो भी जुड़ता है वह आपके अधिकृत पार्टनर कोड से टैग होता है।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    # ── Money, attribution & records (Aug 2026) ───────────────────────────────
    {
        "id": "payment_ledger",
        "en": {"t": "Payment Ledger (every payment, one trail)",
               "d": "Revenue shows one line per payment — subscription, ₹499 review, L2 fee, link or manual — with a ✅ reconciled banner and who recorded manual/offline ones.",
               "u": "Open Revenue → Payment Ledger to see every rupee, verified vs manual, reconciled to the tables."},
        "hi": {"t": "पेमेंट लेजर (हर पेमेंट, एक ट्रेल)",
               "d": "Revenue में हर पेमेंट की एक लाइन — सब्सक्रिप्शन, ₹499 रिव्यू, L2 फीस, लिंक या मैनुअल — ✅ रिकंसाइल बैनर के साथ, और मैनुअल किसने दर्ज किया।",
               "u": "Revenue → पेमेंट लेजर खोलें — हर रुपया, वेरिफाइड बनाम मैनुअल, टेबल से मिलान।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "reattribute_referral",
        "en": {"t": "Fix a referral attribution",
               "d": "Correct who gets credit for an account or a single claim (overrides the locked first-touch). Audited with your name.",
               "u": "Accounts → 🏷️ on a row, or a claim's 'Referred by → Fix', to set the right staff/Authorized Partner code or mark Direct."},
        "hi": {"t": "रेफ़रल एट्रिब्यूशन ठीक करें",
               "d": "किसी अकाउंट या क्लेम का सही श्रेय तय करें (लॉक्ड फर्स्ट-टच को बदलता है)। आपके नाम से लॉग होता है।",
               "u": "Accounts में पंक्ति पर 🏷️, या क्लेम के 'Referred by → Fix' से सही स्टाफ/अधिकृत पार्टनर कोड सेट करें या Direct करें।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "archive_claims",
        "en": {"t": "Archive test / garbage claims",
               "d": "Move test or junk claims out of every working view (restorable, never deleted). Keeps All Claims / L2 clean.",
               "u": "All Claims (Table) → tick claims → 'Archive selected'; view/restore them under '🗄️ Archived claims'."},
        "hi": {"t": "टेस्ट / फालतू क्लेम आर्काइव करें",
               "d": "टेस्ट या बेकार क्लेम को सभी वर्किंग व्यू से हटाएँ (वापस लाया जा सकता है, कभी डिलीट नहीं)।",
               "u": "All Claims (टेबल) → क्लेम चुनें → 'Archive selected'; '🗄️ Archived claims' में देखें/रिस्टोर करें।"},
        "telegram": False, "web": True, "min_role": "sub_super_admin",
    },
    # Documents & money-watching (Sep 2026)
    {
        "id": "wa_message_limits",
        "en": {"t": "How often we message a complainant (and their way out)",
               "d": "We start at most 2 WhatsApp messages a day and 5 a week with one person. Your own typed replies are never limited, and neither is the bot answering inside a chat they started. Anyone can reply STOP to stop updates and START to get them back; a held message is written on the claim so nothing goes missing.",
               "u": "Before you write, the query screen says STOPPED → no WhatsApp, or how many messages are left today and this week."},
        "hi": {"t": "\u0939\u092e \u0936\u093f\u0915\u093e\u092f\u0924\u0915\u0930\u094d\u0924\u093e \u0915\u094b \u0915\u093f\u0924\u0928\u0940 \u092c\u093e\u0930 \u092e\u0948\u0938\u0947\u091c \u0915\u0930\u0924\u0947 \u0939\u0948\u0902 (\u0914\u0930 \u0909\u0928\u0915\u093e \u092c\u0902\u0926 \u0915\u0930\u0928\u0947 \u0915\u093e \u0930\u093e\u0938\u094d\u0924\u093e)",
               "d": "\u0939\u092e \u0916\u0941\u0926 \u0938\u0947 \u090f\u0915 \u0935\u094d\u092f\u0915\u094d\u0924\u093f \u0915\u094b \u0926\u093f\u0928 \u092e\u0947\u0902 \u091c\u093c\u094d\u092f\u093e\u0926\u093e \u0938\u0947 \u091c\u093c\u094d\u092f\u093e\u0926\u093e 2 \u0914\u0930 \u0939\u092b\u093c\u094d\u0924\u0947 \u092e\u0947\u0902 5 WhatsApp \u092e\u0948\u0938\u0947\u091c \u092d\u0947\u091c\u0924\u0947 \u0939\u0948\u0902\u0964 \u0906\u092a\u0915\u0947 \u0905\u092a\u0928\u0947 \u091c\u0935\u093e\u092c \u092a\u0930 \u0915\u094b\u0908 \u0938\u0940\u092e\u093e \u0928\u0939\u0940\u0902, \u0914\u0930 \u0928 \u0939\u0940 \u0909\u0938 \u091a\u0948\u091f \u092a\u0930 \u091c\u094b \u0909\u0928\u094d\u0939\u094b\u0902\u0928\u0947 \u0936\u0941\u0930\u0942 \u0915\u0940 \u0939\u094b\u0964 \u0915\u094b\u0908 \u092d\u0940 STOP \u092d\u0947\u091c\u0915\u0930 \u0905\u092a\u0921\u0947\u091f \u092c\u0902\u0926 \u0915\u0930 \u0938\u0915\u0924\u093e \u0939\u0948 \u0914\u0930 START \u0938\u0947 \u0926\u094b\u092c\u093e\u0930\u093e \u091a\u093e\u0932\u0942\u0964",
               "u": "\u0932\u093f\u0916\u0928\u0947 \u0938\u0947 \u092a\u0939\u0932\u0947 \u0938\u094d\u0915\u094d\u0930\u0940\u0928 \u092c\u0924\u093e\u0924\u0940 \u0939\u0948: STOPPED → WhatsApp \u0928\u0939\u0940\u0902, \u092f\u093e \u0906\u091c \u0914\u0930 \u0907\u0938 \u0939\u092b\u093c\u094d\u0924\u0947 \u0915\u093f\u0924\u0928\u0947 \u092e\u0948\u0938\u0947\u091c \u092c\u091a\u0947 \u0939\u0948\u0902\u0964"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "portal_identity",
        "en": {"t": "The complainant proves who they are before their page opens",
               "d": "The portal link no longer opens a claim by itself. It asks the complainant to confirm their identity: a 6-digit code goes to the number or email already on the claim, and only that opens the page or accepts the fee terms. To look at what they see, use Enter on the claim \u2014 it gives you a 20-minute read-only preview, and it can never accept on their behalf.",
               "u": "All Claims \u2192 a claim row \u2192 enter \u2197 for the staff preview. Complainants get the code themselves."},
        "hi": {"t": "\u0936\u093f\u0915\u093e\u092f\u0924\u0915\u0930\u094d\u0924\u093e \u092a\u0939\u0932\u0947 \u0905\u092a\u0928\u0940 \u092a\u0939\u091a\u093e\u0928 \u0938\u093e\u092c\u093f\u0924 \u0915\u0930\u0924\u093e \u0939\u0948",
               "d": "\u092a\u094b\u0930\u094d\u091f\u0932 \u0932\u093f\u0902\u0915 \u0905\u092c \u0905\u092a\u0928\u0947 \u0906\u092a \u0915\u094d\u0932\u0947\u092e \u0928\u0939\u0940\u0902 \u0916\u094b\u0932\u0924\u093e\u0964 6 \u0905\u0902\u0915\u094b\u0902 \u0915\u093e \u0915\u094b\u0921 \u0909\u0938\u0940 \u0928\u0902\u092c\u0930 \u092f\u093e \u0908\u092e\u0947\u0932 \u092a\u0930 \u091c\u093e\u0924\u093e \u0939\u0948 \u091c\u094b \u0915\u094d\u0932\u0947\u092e \u092a\u0930 \u0926\u0930\u094d\u091c \u0939\u0948, \u0914\u0930 \u0909\u0938\u0940 \u0938\u0947 \u092a\u0947\u091c \u0916\u0941\u0932\u0924\u093e \u0939\u0948 \u092f\u093e \u092b\u0940\u0938 \u0936\u0930\u094d\u0924\u0947\u0902 \u0938\u094d\u0935\u0940\u0915\u093e\u0930 \u0939\u094b\u0924\u0940 \u0939\u0948\u0902\u0964 \u0938\u094d\u091f\u093e\u092b\u093c → 20 \u092e\u093f\u0928\u091f \u0915\u093e \u0938\u093f\u0930\u094d\u092b\u093c-\u0926\u0947\u0916\u0928\u0947 \u0935\u093e\u0932\u093e \u092a\u094d\u0930\u0940\u0935\u094d\u092f\u0942\u0964",
               "u": "All Claims \u2192 \u0915\u094d\u0932\u0947\u092e \u092a\u0902\u0915\u094d\u0924\u093f \u2192 enter \u2197 \u0938\u0947 \u0938\u094d\u091f\u093e\u092b\u093c \u092a\u094d\u0930\u0940\u0935\u094d\u092f\u0942\u0964"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "wa_scheduled_reminder",
        "en": {"t": "Remind a complainant when they can actually answer",
               "d": "Pick the moment \u2014 a Sunday morning, an evening, whatever you know about this person \u2014 and we ask for the missing documents then. Once, every week, or every few days. It stops by itself when the documents are in, and after the number of tries you set.",
               "u": "Open a claim \u2192 Documents \u2192 \u23f0 Remind them at a better time. Pause or cancel it there too. When it goes out you get a message on the bell and Telegram \u2014 and if it could not reach them, \u201cplease call\u201d with the number. Past WhatsApp's 24-hour window the approved reminder goes instead."},
        "hi": {"t": "\u0936\u093f\u0915\u093e\u092f\u0924\u0915\u0930\u094d\u0924\u093e \u0915\u094b \u0938\u0939\u0940 \u0938\u092e\u092f \u092a\u0930 \u092f\u093e\u0926 \u0926\u093f\u0932\u093e\u0907\u090f",
               "d": "\u0938\u092e\u092f \u0906\u092a \u091a\u0941\u0928\u093f\u090f \u2014 \u0930\u0935\u093f\u0935\u093e\u0930 \u0938\u0941\u092c\u0939, \u0936\u093e\u092e, \u091c\u094b \u0906\u092a \u0909\u0938 \u0935\u094d\u092f\u0915\u094d\u0924\u093f \u0915\u0947 \u092c\u093e\u0930\u0947 \u092e\u0947\u0902 \u091c\u093e\u0928\u0924\u0947 \u0939\u0948\u0902 \u2014 \u0914\u0930 \u0939\u092e \u0909\u0938\u0940 \u0938\u092e\u092f \u092c\u093e\u0915\u0940 \u0926\u0938\u094d\u0924\u093e\u0935\u0947\u091c\u093c \u092e\u093e\u0901\u0917\u0924\u0947 \u0939\u0948\u0902\u0964 \u090f\u0915 \u092c\u093e\u0930, \u0939\u0930 \u0939\u092b\u093c\u094d\u0924\u0947, \u092f\u093e \u0915\u0941\u091b \u0926\u093f\u0928\u094b\u0902 \u092e\u0947\u0902\u0964 \u0926\u0938\u094d\u0924\u093e\u0935\u0947\u091c\u093c \u0906\u0924\u0947 \u0939\u0940 \u092f\u0939 \u0916\u0941\u0926 \u092c\u0902\u0926 \u0939\u094b \u091c\u093e\u0924\u093e \u0939\u0948\u0964",
               "u": "\u0915\u094d\u0932\u0947\u092e \u0916\u094b\u0932\u0947\u0902 \u2192 Documents \u2192 \u23f0 Remind them at a better time\u0964"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "referred_claims",
        "en": {"t": "Claims from customers you referred",
               "d": "Staff and Authorized Partners see every claim filed by a customer who joined with their code \u2014 stage in the customer's own words, which documents are still missing, and who at Nidaan is handling it. \u201cSend information to the team\u201d puts a note on the claim and tells the handler.",
               "u": "Staff: \U0001f680 My Business \u2192 Claims from customers you referred. AP: your dashboard, the same heading."},
        "hi": {"t": "आपके रेफ़र किए ग्राहकों के क्लेम",
               "d": "स्टाफ़ और अधिकृत पार्टनर (AP) अपने कोड से जुड़े ग्राहक का हर क्लेम देखते हैं \u2014 ग्राहक के शब्दों में स्थिति, कौन से दस्तावेज़ बाकी हैं, और Nidaan में कौन देख रहा है। \u201cटीम को जानकारी भेजें\u201d से क्लेम पर नोट लगता है और देखने वाले को सूचना जाती है।",
               "u": "स्टाफ़: \U0001f680 My Business \u2192 आपके रेफ़र किए ग्राहकों के क्लेम। AP: आपका डैशबोर्ड, वही शीर्षक।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "wa_files_to_sort",
        "en": {"t": "WhatsApp files from any number are kept - and staff can forward a customer's papers",
               "d": "A file sent to our WhatsApp from a number that is not on a claim (a subscriber, a partner, a stranger) used to be lost. Now it is virus-checked and kept in WhatsApp - Files to sort, with who sent it, until a person attaches it to the right claim or sets it aside. A staff member can forward a customer's papers from their own number: write the claim number in the caption (e.g. NP-123) and it is filed on that claim straight away, if you are on that claim.",
               "u": "WhatsApp screen - Files to sort - Open, type the claim number, Attach. To forward: send the file to our WhatsApp number with NP-123 in the caption."},
        "hi": {"t": "किसी भी नंबर से आई WhatsApp फ़ाइलें सुरक्षित - और स्टाफ़ ग्राहक के काग़ज़ फ़ॉरवर्ड कर सकते हैं",
               "d": "जो फ़ाइल किसी ऐसे नंबर से हमारे WhatsApp पर आती थी जो किसी क्लेम पर नहीं है (सब्सक्राइबर, पार्टनर, कोई अनजान), वह खो जाती थी। अब वह वायरस-जाँच के बाद WhatsApp - Files to sort में, भेजने वाले के नाम के साथ, रखी जाती है, जब तक कोई उसे सही क्लेम पर न लगा दे या कारण लिखकर अलग न रख दे। स्टाफ़ अपने नंबर से ग्राहक के काग़ज़ भेज सकते हैं: कैप्शन में क्लेम नंबर लिखिये (जैसे NP-123), और अगर आप उस क्लेम पर हैं तो फ़ाइल तुरंत उसी क्लेम पर लग जाएगी।",
               "u": "WhatsApp स्क्रीन - Files to sort - Open, क्लेम नंबर लिखें, Attach। फ़ॉरवर्ड करने के लिए: फ़ाइल हमारे WhatsApp नंबर पर भेजें, कैप्शन में NP-123 लिखें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "office_hours_bot",
        "en": {"t": "Customers waiting on chat or WhatsApp are told our office hours",
               "d": "Whenever a customer is waiting for a person - at night, or in office hours before anyone picks it up - the website, dashboard and WhatsApp bot tell them our office hours (from the Customer Support setting) and when someone will reach out, at most three times, then stay quiet. Staff get at most two Telegram reminders per waiting chat, in office hours only. Your reply restarts the count.",
               "u": "Answer waiting chats from WhatsApp Automation or Customer Support. Office hours are set on the Customer Support screen."},
        "hi": {"t": "चैट या WhatsApp पर इंतज़ार करते ग्राहक को ऑफ़िस का समय बताया जाता है",
               "d": "जब भी कोई ग्राहक किसी व्यक्ति का इंतज़ार कर रहा हो - रात में, या ऑफ़िस समय में जवाब मिलने से पहले - वेबसाइट, डैशबोर्ड और WhatsApp का बॉट उसे हमारे ऑफ़िस का समय (Customer Support सेटिंग से) और कब संपर्क होगा, बताता है - ज़्यादा से ज़्यादा तीन बार, फिर चुप। स्टाफ़ को हर इंतज़ार करती चैट के लिए ज़्यादा से ज़्यादा दो टेलीग्राम याद, सिर्फ़ ऑफ़िस समय में। आपका जवाब गिनती फिर से शुरू करता है।",
               "u": "इंतज़ार करती चैट का जवाब WhatsApp Automation या Customer Support से दीजिये। ऑफ़िस का समय Customer Support स्क्रीन पर तय होता है।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "evening_summary",
        "en": {"t": "Every evening, your day on Telegram - text and a voice note",
               "d": "At 8 pm each person gets their own summary: the claims they worked on and which bucket each sits in, the claims they moved (from where to where), what they did and their tasks - in their own language, with a voice note. Super-admins also get the team's day: bucket by bucket, every move and who made it, who worked on what, who recorded nothing, who is on leave. Money is always read out as rupees. A day with nothing recorded sends nothing.",
               "u": "Nothing to do - it comes by itself. Choose your language in the Telegram bot. It only shows what you recorded on the claims, so record your work there."},
        "hi": {"t": "हर शाम आपका दिन टेलीग्राम पर - लिखकर और आवाज़ में",
               "d": "रात 8 बजे हर व्यक्ति को अपना सार मिलता है: किन क्लेम पर काम किया और वे किस बकेट में हैं, कौन-से क्लेम कहाँ से कहाँ भेजे, क्या काम किया और टास्क - अपनी भाषा में, आवाज़ के साथ। सुपर-एडमिन को पूरी टीम का दिन भी मिलता है: हर बकेट, हर मूव और किसने किया, किसने किस पर काम किया, किसका कुछ दर्ज नहीं, कौन छुट्टी पर है। रकम हमेशा रुपये में बोली जाती है। जिस दिन कुछ दर्ज न हो, कुछ नहीं आता।",
               "u": "कुछ करना नहीं है - यह अपने आप आता है। भाषा टेलीग्राम बॉट में चुनें। इसमें वही दिखता है जो आपने क्लेम पर दर्ज किया, इसलिए अपना काम वहीं दर्ज करें।"},
        "telegram": True, "web": False, "min_role": "team_member",
    },
    {
        "id": "claim_cp_change",
        "en": {"t": "Add or remove a Channel Partner on an existing claim - with approval",
               "d": "Forgot to choose the Channel Partner when you raised a My Business claim? Ask for it on the claim, with a reason; a super-admin approves or rejects, and only then does the claim change. Removing one works the same way. Every step is on the claim's timeline and you are told the answer.",
               "u": "Open the claim - Where this claim came from - Channel Partner - Ask to add (or Ask to remove). Super-admins approve or reject in the same place."},
        "hi": {"t": "मौजूदा क्लेम पर चैनल पार्टनर जोड़ें या हटाएँ - मंज़ूरी के साथ",
               "d": "My Business क्लेम दर्ज करते समय चैनल पार्टनर चुनना भूल गए? क्लेम पर कारण के साथ अनुरोध करें; सुपर-एडमिन मंज़ूर या अस्वीकार करते हैं, तभी क्लेम बदलता है। हटाना भी ऐसे ही होता है। हर कदम क्लेम की टाइमलाइन पर दर्ज होता है और आपको जवाब बताया जाता है।",
               "u": "क्लेम खोलें - Where this claim came from - Channel Partner - Ask to add (या Ask to remove)। सुपर-एडमिन वहीं मंज़ूर या अस्वीकार करते हैं।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "payment_daily_check",
        "en": {"t": "Every morning: yesterday's payments checked against Razorpay",
               "d": "At 9 am the super admins get one message: what Razorpay captured yesterday, what is in our books, and \u201call match\u201d \u2014 or exactly which payment is missing or differs. It reads only; the Payment Guardian still recovers a missing payment on its own.",
               "u": "Nothing to do. It arrives on Telegram and the bell each morning."},
        "hi": {"t": "हर सुबह: कल के भुगतान Razorpay से मिलाए जाते हैं",
               "d": "सुबह 9 बजे सुपर एडमिन को एक संदेश: कल Razorpay पर क्या आया, हमारे खाते में क्या है, और \u201cसब मिलता है\u201d \u2014 या ठीक कौन सा भुगतान छूटा या अलग है। यह सिर्फ़ पढ़ता है; छूटा भुगतान Payment Guardian ख़ुद दर्ज करता है।",
               "u": "कुछ करने की ज़रूरत नहीं। हर सुबह Telegram और घंटी पर आता है।"},
        "telegram": True, "web": False, "min_role": "super_admin",
    },
    {
        "id": "contact_proof",
        "en": {"t": "A complainant's email and mobile show verified only when proven",
               "d": "Verified means THIS address was proven - a code entered, a link clicked, a WhatsApp message from the number - with how and when. Change an email or mobile and it is unverified at once: the old contact is cut off, the change is recorded old to new, and a confirmation goes to the new one. On the claim page the complainant is asked to confirm their email before authorising.",
               "u": "Open a claim - see Email and Contact mobile. Not verified? Press Send confirmation. Handlers get a daily Telegram list of unconfirmed contacts."},
        "hi": {"t": "शिकायतकर्ता का ईमेल और मोबाइल तभी वेरिफ़ाइड दिखता है जब साबित हो",
               "d": "वेरिफ़ाइड का मतलब है कि यही पता साबित हुआ - कोड डाला, लिंक दबाया, या उस नंबर से WhatsApp आया - कैसे और कब, दोनों दिखते हैं। ईमेल या मोबाइल बदलते ही वह अनवेरिफ़ाइड हो जाता है: पुराना संपर्क कट जाता है, बदलाव पुराने से नए तक दर्ज होता है, और नए पर पुष्टि भेजी जाती है। क्लेम पेज पर शिकायतकर्ता से अनुमति देने से पहले ईमेल कन्फ़र्म करने को कहा जाता है।",
               "u": "क्लेम खोलें - Email और Contact mobile देखें। वेरिफ़ाइड नहीं? Send confirmation दबाइए। हैंडलर को रोज़ Telegram पर बिना-कन्फ़र्म संपर्कों की सूची मिलती है।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "doc_followup_record",
        "en": {"t": "Follow-up so far \u2014 who chased the documents, and what to do next",
               "d": "Every ask, booked reminder, call and automatic-reminder switch on a claim, with who did it and when \u2014 and one line saying what to do next. It says plainly when automatic reminders are off, so nobody waits for a reminder that will never go.",
               "u": "Open a claim \u2192 Documents \u2192 top of the checklist. Read it before you chase."},
        "hi": {"t": "Follow-up so far \u2014 किसने दस्तावेज़ माँगे, और अब क्या करना है",
               "d": "क्लेम पर हर माँग, तय रिमाइंडर, कॉल और ऑटोमैटिक रिमाइंडर का चालू/बंद होना \u2014 किसने और कब \u2014 और एक लाइन कि अब क्या करना है। ऑटोमैटिक रिमाइंडर बंद हों तो साफ़ बताता है, ताकि कोई ऐसे रिमाइंडर का इंतज़ार न करे जो जाएगा ही नहीं।",
               "u": "क्लेम खोलें \u2192 Documents \u2192 चेकलिस्ट के ऊपर। याद दिलाने से पहले पढ़िये।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "wa_remind_time_by_complainant",
        "en": {"t": "The complainant picks when to be reminded",
               "d": "When the WhatsApp bot asks for a document it adds: busy? tell me when to remind you. They write it their way \u2014 \u201ckal shaam 7 baje\u201d, \u201cSunday 10am\u201d, \u201cरविवार सुबह\u201d \u2014 the bot says the time back and books it only after their yes. Unclear twice and your team takes over. Nothing leaves our server to read it.",
               "u": "Off until a super-admin turns it on: WhatsApp \u2192 Doc-collection defaults \u2192 Complainant picks reminder time. The booked reminder shows on the claim like any other."},
        "hi": {"t": "दावेदार ख़ुद चुने कब याद दिलाना है",
               "d": "WhatsApp बॉट दस्तावेज़ माँगते समय जोड़ता है: अभी व्यस्त हैं? बताइए कब याद दिलाऊँ। वे अपने तरीके से लिखते हैं \u2014 \u201cकल शाम 7 बजे\u201d, \u201cSunday 10am\u201d \u2014 बॉट समय दोहराता है और उनकी \u201cहाँ\u201d के बाद ही तय करता है। दो बार साफ़ न हो तो आपकी टीम संभालती है। इसे पढ़ने के लिए कुछ भी हमारे सर्वर से बाहर नहीं जाता।",
               "u": "जब तक सुपर-एडमिन चालू न करे, बंद: WhatsApp \u2192 Doc-collection defaults \u2192 Complainant picks reminder time। तय हुआ रिमाइंडर क्लेम पर बाक़ी रिमाइंडर की तरह दिखता है।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "claim_documents",
        "en": {"t": "Open a claim's documents without downloading them",
               "d": "Click a document and read it in the page — PDFs, photos and Word letters. Rename anything badly named (IMG_2231 → 'Discharge summary'), or remove a wrong one — which reopens the checklist line it answered, so we ask for the right one. Any file except video, up to 25 MB, virus-scanned before it is stored.",
               "u": "Open a claim → Documents → click a file to read it, or ✏️ to rename it. Download is still one click away."},
        "hi": {"t": "क्लेम के दस्तावेज़ बिना डाउनलोड किए खोलें",
               "d": "दस्तावेज़ पर क्लिक करें और पेज में ही पढ़ें — PDF, फोटो और Word पत्र। ग़लत नाम वाली फाइल का नाम बदलें (IMG_2231 → 'डिस्चार्ज समरी'), वह क्लेम पर दर्ज हो जाता है। वीडियो छोड़कर हर तरह की फाइल, 25 MB तक, स्टोर करने से पहले वायरस जाँच।",
               "u": "क्लेम खोलें → Documents → पढ़ने के लिए फाइल पर क्लिक करें, या नाम बदलने के लिए ✏️। डाउनलोड अब भी एक क्लिक दूर है।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "payment_guardian",
        "en": {"t": "Payment Guardian (watches every rupee, day and night)",
               "d": "Checks the payment machinery every few minutes — money taken but no claim unlocked, a payment nobody was told about, a double charge, a subscription that did not start, the bank going quiet. Anything wrong reaches super-admins on Telegram and repeats every 10 minutes until one of them presses Seen; if it is still wrong 2 hours later it comes back.",
               "u": "Revenue → 🛡️ Payment Guardian shows what is open and who has seen it."},
        "hi": {"t": "पेमेंट गार्जियन (हर रुपये पर 24 घंटे नज़र)",
               "d": "हर कुछ मिनट में पेमेंट सिस्टम की जाँच — पैसा आया पर क्लेम नहीं खुला, पेमेंट जिसकी किसी को ख़बर नहीं हुई, दोहरा चार्ज, सब्सक्रिप्शन शुरू नहीं हुआ, बैंक से जवाब बंद। गड़बड़ी सुपर-एडमिन को Telegram पर जाती है और हर 10 मिनट दोहराती है जब तक कोई 'देख लिया' न दबाए; 2 घंटे बाद भी ठीक न हो तो फिर आती है।",
               "u": "Revenue → 🛡️ Payment Guardian में खुली समस्याएँ और किसने देखा, दोनों दिखते हैं।"},
        "telegram": True, "web": True, "min_role": "super_admin",
    },
    {
        "id": "claim_activity",
        "en": {"t": "Claim activity timeline",
               "d": "One trail per claim — status changes, payments, WhatsApp messages and every automation nudge + customer reply — so a claim reads like a human managed it.",
               "u": "Open a claim to see its full chronological activity."},
        "hi": {"t": "क्लेम एक्टिविटी टाइमलाइन",
               "d": "हर क्लेम की एक ट्रेल — स्टेटस बदलाव, पेमेंट, WhatsApp संदेश और हर ऑटोमेशन रिमाइंडर + ग्राहक का जवाब।",
               "u": "किसी क्लेम को खोलें और उसकी पूरी क्रमवार एक्टिविटी देखें।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
    {
        "id": "health_ways_in",
        "en": {"t": "See whether people can actually log in",
               "d": "App Health now reports each way into the system — Authorized Partner, subscriber, staff and the complainant portal — and says what is broken and why. It judges delivery on the codes we actually sent in the last 24 hours, not on whether the settings look right, because on 17 Sep every setting was right and no Authorized Partner received a single code. An Authorized Partner with no email and no mobile is named, so it can be fixed. 'Test login delivery' sends a real login email down the same path to your own address and tells you which route carried it.",
               "u": "App Health → 🔑 Ways in — logins. A failing row links to the screen that holds the missing detail."},
        "hi": {"t": "देखें कि लोग सचमुच लॉगिन कर पा रहे हैं या नहीं",
               "d": "App Health अब हर लॉगिन रास्ते की हालत बताता है — अधिकृत पार्टनर, सब्सक्राइबर, स्टाफ़ और शिकायतकर्ता पोर्टल — और यह भी कि क्या टूटा है और क्यों। पिछले 24 घंटे में भेजे गए असली कोड के आधार पर फ़ैसला होता है, सेटिंग देखकर नहीं, क्योंकि 17 सितंबर को सेटिंग सही थी और किसी अधिकृत पार्टनर को एक भी कोड नहीं मिला। जिस अधिकृत पार्टनर के पास न ईमेल है न मोबाइल, उसका नाम दिखता है। 'Test login delivery' उसी रास्ते से आपके अपने पते पर असली ईमेल भेजकर बताता है कि वह किस रूट से गया।",
               "u": "App Health → 🔑 Ways in — logins। जो पंक्ति लाल है, वह उसी स्क्रीन पर ले जाती है जहाँ कमी भरनी है।"},
        "telegram": False, "web": True, "min_role": "super_admin",
    },
    {
        "id": "br_login_whatsapp", "audience": ["branch"],
        "en": {"t": "Log in with a WhatsApp code if email is not reaching you",
               "d": "The login page has two buttons. If the email code is not arriving, ask for it on WhatsApp instead — the same code, a different road. It reaches you straight away, with a button to copy the code; you do not have to message us first. The one thing we need is your mobile number on file, so please give it to the office if we do not have it.",
               "u": "Authorized Partner portal login → type your Authorized Partner email → 'Send it on WhatsApp instead'."},
        "hi": {"t": "ईमेल न पहुँचे तो WhatsApp कोड से लॉगिन करें",
               "d": "लॉगिन पेज पर दो बटन हैं। अगर ईमेल कोड नहीं आ रहा, तो वही कोड WhatsApp पर मँगाइए — रास्ता अलग, कोड वही। कोड सीधे आ जाता है और उसे कॉपी करने का बटन भी मिलता है; पहले हमें कोई मैसेज भेजने की ज़रूरत नहीं। बस आपका मोबाइल नंबर हमारे पास दर्ज होना चाहिए — न हो तो ऑफ़िस को बता दीजिए।",
               "u": "अधिकृत पार्टनर पोर्टल लॉगिन → अपना अधिकृत पार्टनर ईमेल लिखें → 'Send it on WhatsApp instead'।"},
        "telegram": False, "web": True, "min_role": "team_member",
    },
]


def _allowed(role: str, cap: dict) -> bool:
    return ROLE_RANK.get(role, -1) >= ROLE_RANK.get(cap.get("min_role", "team_member"), 99)


def _aud(cap: dict) -> list:
    """Which dashboards a capability belongs to. Defaults to staff/ops (the original audience)."""
    return cap.get("audience", ["staff"])


def features_for(audience: str, lang: str = "en", plan: str = "") -> list:
    """Flat feature list for a NON-staff dashboard (subscriber/branch/claimant), plan-gated.
    Each entry: {id, title, detail, use}. `plan` filters entries that declare a `plans` list."""
    lang = "hi" if str(lang).lower().startswith("hi") else "en"
    out = []
    for c in CAPABILITIES:
        if audience not in _aud(c):
            continue
        plans = c.get("plans")
        if plans and plan and plan not in plans:
            continue
        body = c.get(lang) or c["en"]
        out.append({"id": c["id"], "title": body["t"], "detail": body["d"], "use": body.get("u", "")})
    return out


def speech_text_for(audience: str, lang: str = "en", plan: str = "") -> str:
    """Narration for a non-staff dashboard's feature list (same entries as features_for)."""
    feats = features_for(audience, lang, plan)
    hi = str(lang).lower().startswith("hi")
    if hi:
        parts = ["नमस्ते। यहाँ बताया गया है कि आप अपने डैशबोर्ड पर क्या-क्या कर सकते हैं।"]
        parts += [f"{i}. {c['title']}। {c['detail']} {c.get('use','')}".strip() for i, c in enumerate(feats, 1)]
        parts.append("कोई भी सवाल हो तो हमारी टीम से संपर्क करें।")
    else:
        parts = ["Hello. Here is what you can do on your dashboard."]
        parts += [f"{i}. {c['title']}. {c['detail']} {c.get('use','')}".strip() for i, c in enumerate(feats, 1)]
        parts.append("If you have any question, contact our team.")
    import biz_speakable   # the browser's own voice reads this too - rupees, never dollars
    return biz_speakable.speakable(" ".join(parts))


def build_guide(role: str, lang: str = "en") -> dict:
    """Role-filtered STAFF guide, split by WHERE each thing can be done."""
    lang = "hi" if str(lang).lower().startswith("hi") else "en"
    caps = [c for c in CAPABILITIES if "staff" in _aud(c) and _allowed(role, c)]
    def _fmt(c):
        body = c.get(lang) or c["en"]
        return {"id": c["id"], "title": body["t"], "detail": body["d"], "use": body.get("u", "")}
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
        parts += [f"{i}. {c['title']}। {c['detail']} {c.get('use','')}".strip() for i, c in enumerate(g["telegram"], 1)]
        parts.append("अब वे काम जो सिर्फ़ वेब पोर्टल या ऐप से होते हैं।")
        parts += [f"{i}. {c['title']}। {c['detail']} {c.get('use','')}".strip() for i, c in enumerate(g["web_only"], 1)]
        parts.append("बस इतना ही। कोई भी सवाल हो तो टेलीग्राम पर सीधे पूछ सकते हैं।")
    else:
        parts = [f"Hello. You are a {role_label[0]}. Here is what you can do.",
                 "First, the things you can do from the Telegram bot."]
        parts += [f"{i}. {c['title']}. {c['detail']} {c.get('use','')}".strip() for i, c in enumerate(g["telegram"], 1)]
        parts.append("Now, the things that can only be done in the web portal or the installed app.")
        parts += [f"{i}. {c['title']}. {c['detail']} {c.get('use','')}".strip() for i, c in enumerate(g["web_only"], 1)]
        parts.append("That's everything. If you have a question, just ask the bot on Telegram.")
    import biz_speakable   # the browser's own voice reads this too - rupees, never dollars
    return biz_speakable.speakable(" ".join(parts))


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
