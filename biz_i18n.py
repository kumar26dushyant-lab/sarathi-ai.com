# =============================================================================
#  biz_i18n.py — Sarathi-AI Business Technologies: Internationalisation (Phase 1)
# =============================================================================
#
#  Bilingual message strings — English + Hindi.
#  Usage:  from biz_i18n import t
#          msg = t(lang, "welcome_back", name="Rajesh")
#
# =============================================================================

LANGUAGES = {"en": "English", "hi": "हिन्दी"}
DEFAULT_LANG = "en"

# ── Master string table ──────────────────────────────────────────────────────
_S = {

    # ── Onboarding ──────────────────────────────────────────────────────────
    "welcome_back": {
        "en": (
            "👋 Welcome back, <b>{name}</b>!\n\n"
            "Use /help to see all commands.\n"
            "Use /dashboard for your business overview."
        ),
        "hi": (
            "👋 वापस स्वागत है, <b>{name}</b>!\n\n"
            "सभी कमांड देखने के लिए /help दबाएं।\n"
            "व्यापार ओवरव्यू के लिए /dashboard दबाएं।"
        ),
    },
    "welcome_new": {
        "en": (
            "🙏 <b>Welcome to Sarathi-AI Business Technologies!</b>\n\n"
            "<i>AI-Powered CRM for Financial Advisors</i> 🛡️\n\n"
            "Let's set up your agent profile.\n"
            "What is your <b>full name</b>?"
        ),
        "hi": (
            "🙏 <b>सारथी बिज़नेस सूट में आपका स्वागत है!</b>\n\n"
            "<i>सुरक्षा से समृद्धि तक</i> 🛡️\n\n"
            "आइए आपकी एजेंट प्रोफ़ाइल बनाते हैं।\n"
            "आपका <b>पूरा नाम</b> क्या है?"
        ),
    },
    "ask_phone": {
        "en": "📱 <b>Step 3a — Phone Number</b>\n\nEnter your <b>10-digit mobile number</b>:",
        "hi": "📱 <b>स्टेप 3a — फ़ोन नंबर</b>\n\nअपना <b>10 अंकों का मोबाइल नंबर</b> दर्ज करें:",
    },
    "ask_email": {
        "en": "📧 <b>Step 3b — Email Address</b>\n\nEnter your <b>email address</b>:\n<i>(Required for account recovery & notifications)</i>",
        "hi": "📧 <b>स्टेप 3b — ईमेल</b>\n\nअपना <b>ईमेल पता</b> दर्ज करें:\n<i>(अकाउंट रिकवरी और सूचनाओं के लिए ज़रूरी)</i>",
    },
    "invalid_phone": {
        "en": (
            "❌ Please enter a valid <b>10-digit Indian mobile number</b>.\n"
            "Example: 9876543210"
        ),
        "hi": (
            "❌ कृपया एक वैध <b>10 अंकों का भारतीय मोबाइल नंबर</b> दर्ज करें।\n"
            "उदाहरण: 9876543210"
        ),
    },
    "invalid_phone_skip": {
        "en": (
            "❌ Please enter a valid <b>10-digit Indian mobile number</b>.\n"
            "Example: 9876543210  (or /skip)"
        ),
        "hi": (
            "❌ कृपया एक वैध <b>10 अंकों का भारतीय मोबाइल नंबर</b> दर्ज करें।\n"
            "उदाहरण: 9876543210  (या /skip)"
        ),
    },
    "registration_done": {
        "en": (
            "✅ <b>Registration Complete!</b>\n\n"
            "👤 Name: {name}\n📱 Phone: {phone}\n🆔 Agent ID: {agent_id}\n\n"
            "You're all set! Use /help to see commands.\n"
            "Start adding leads with /addlead 🎯"
        ),
        "hi": (
            "✅ <b>रजिस्ट्रेशन पूरा हुआ!</b>\n\n"
            "👤 नाम: {name}\n📱 फ़ोन: {phone}\n🆔 एजेंट ID: {agent_id}\n\n"
            "आप तैयार हैं! कमांड देखने के लिए /help दबाएं।\n"
            "लीड जोड़ने के लिए /addlead दबाएं 🎯"
        ),
    },

    # ── Add Lead ────────────────────────────────────────────────────────────
    "addlead_title": {
        "en": "🎯 <b>Add New Lead</b>\n\nWhat is the prospect's <b>full name</b>?",
        "hi": "🎯 <b>नई लीड जोड़ें</b>\n\nग्राहक का <b>पूरा नाम</b> क्या है?",
    },
    "ask_lead_phone": {
        "en": "📱 <b>Phone number</b> (10-digit mobile):",
        "hi": "📱 <b>फ़ोन नंबर</b> (10 अंकों का मोबाइल):",
    },
    "ask_lead_email": {
        "en": "📧 <b>Email address</b>? (or /skip)",
        "hi": "📧 <b>ईमेल</b>? (या /skip)",
    },
    "invalid_email": {
        "en": "❌ Invalid email format. Please enter a valid email (e.g., name@example.com)",
        "hi": "❌ अमान्य ईमेल। कृपया सही ईमेल दर्ज करें (जैसे name@example.com)",
    },
    "invalid_dob": {
        "en": "❌ Invalid format. Please enter Date of Birth as <b>DD-MM-YYYY</b>",
        "hi": "❌ अमान्य प्रारूप। कृपया जन्मतिथि <b>DD-MM-YYYY</b> में दर्ज करें",
    },
    "ask_dob": {
        "en": "🎂 <b>Date of Birth</b> (DD-MM-YYYY):",
        "hi": "🎂 <b>जन्मतिथि</b> (DD-MM-YYYY):",
    },
    "ask_anniversary": {
        "en": "💍 <b>Anniversary date</b>? (DD-MM-YYYY or /skip)",
        "hi": "💍 <b>सालगिरह</b>? (DD-MM-YYYY या /skip)",
    },
    "ask_city": {
        "en": "🏙️ <b>City</b>? (or /skip)",
        "hi": "🏙️ <b>शहर</b>? (या /skip)",
    },
    "ask_needs": {
        "en": (
            "📋 <b>What does the prospect need?</b>\n"
            "<i>Tap all that apply, then press ✅ Done</i>"
        ),
        "hi": (
            "📋 <b>ग्राहक को क्या चाहिए?</b>\n"
            "<i>सभी चुनें, फिर ✅ Done दबाएं</i>"
        ),
    },
    "needs_selected": {
        "en": "✅ Needs: <b>{label}</b>\n\n📝 Any <b>notes</b>? (or /skip)",
        "hi": "✅ ज़रूरतें: <b>{label}</b>\n\n📝 कोई <b>नोट</b>? (या /skip)",
    },
    "lead_added": {
        "en": (
            "✅ <b>Lead Added Successfully!</b>\n\n"
            "🆔 Lead ID: {lead_id}\n👤 Name: {name}\n"
            "📱 Phone: {phone}\n📋 Need: {need}\n📊 Stage: Prospect\n\n"
            "<b>Quick Actions:</b>"
        ),
        "hi": (
            "✅ <b>लीड सफलतापूर्वक जोड़ी गई!</b>\n\n"
            "🆔 लीड ID: {lead_id}\n👤 नाम: {name}\n"
            "📱 फ़ोन: {phone}\n📋 ज़रूरत: {need}\n📊 स्टेज: Prospect\n\n"
            "<b>त्वरित कार्रवाई:</b>"
        ),
    },

    # ── Pipeline ────────────────────────────────────────────────────────────
    "pipeline_title": {
        "en": "📊 <b>Sales Pipeline</b>\n━━━━━━━━━━━━━━━━━━\n",
        "hi": "📊 <b>सेल्स पाइपलाइन</b>\n━━━━━━━━━━━━━━━━━━\n",
    },

    # ── Follow-up ──────────────────────────────────────────────────────────
    "followup_title": {
        "en": "📝 <b>Log Follow-up</b>\n\nSelect a lead:",
        "hi": "📝 <b>फॉलो-अप लॉग करें</b>\n\nलीड चुनें:",
    },
    "followup_type_ask": {
        "en": "📝 <b>Log Interaction: {name}</b>\n\nWhat type of interaction?",
        "hi": "📝 <b>इंटरैक्शन लॉग: {name}</b>\n\nकिस प्रकार का इंटरैक्शन?",
    },
    "followup_notes_ask": {
        "en": "✅ Type: <b>{type}</b>\n\n📝 Brief summary of the interaction?",
        "hi": "✅ प्रकार: <b>{type}</b>\n\n📝 इंटरैक्शन का संक्षिप्त विवरण?",
    },
    "followup_date_ask": {
        "en": "📅 <b>Next follow-up date?</b> (DD-MM-YYYY or /skip for no follow-up)",
        "hi": "📅 <b>अगली फॉलो-अप तारीख?</b> (DD-MM-YYYY या /skip)",
    },
    "followup_done": {
        "en": (
            "✅ <b>Interaction Logged!</b>\n\n"
            "👤 {name}\n📋 Type: {type}\n📝 {notes}{follow_msg}"
        ),
        "hi": (
            "✅ <b>इंटरैक्शन लॉग हो गया!</b>\n\n"
            "👤 {name}\n📋 प्रकार: {type}\n📝 {notes}{follow_msg}"
        ),
    },

    # ── Convert Stage ──────────────────────────────────────────────────────
    "convert_title": {
        "en": (
            "🔄 <b>Move Lead: {name}</b>\n"
            "Current Stage: {stage_emoji} {stage}\n\n"
            "Select new stage:"
        ),
        "hi": (
            "🔄 <b>लीड स्टेज बदलें: {name}</b>\n"
            "वर्तमान: {stage_emoji} {stage}\n\n"
            "नई स्टेज चुनें:"
        ),
    },
    "stage_updated": {
        "en": "✅ <b>Stage Updated!</b>\n\n👤 {name}\n📊 New Stage: {stage_emoji} {stage}",
        "hi": "✅ <b>स्टेज अपडेट!</b>\n\n👤 {name}\n📊 नई स्टेज: {stage_emoji} {stage}",
    },

    # ── Calculator ─────────────────────────────────────────────────────────
    "calc_title": {
        "en": (
            "📊 <b>Financial Calculators</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Choose a calculator below for a quick result,\n"
            "or use these <b>interactive web links</b> to share\n"
            "with your clients:\n\n"
        ),
        "hi": (
            "📊 <b>वित्तीय कैलकुलेटर</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "नीचे कैलकुलेटर चुनें या\nये <b>वेब लिंक</b> ग्राहकों को शेयर करें:\n\n"
        ),
    },

    # ── WhatsApp ───────────────────────────────────────────────────────────
    "wa_sent": {
        "en": "✅ WhatsApp sent to <b>{name}</b> ({phone})",
        "hi": "✅ <b>{name}</b> ({phone}) को WhatsApp भेजा गया",
    },
    "wa_failed": {
        "en": "❌ WhatsApp failed: {error}",
        "hi": "❌ WhatsApp विफल: {error}",
    },
    "wa_no_phone": {
        "en": "❌ No phone number for this lead",
        "hi": "❌ इस लीड का फ़ोन नंबर नहीं है",
    },

    # ── WA Calc Share ──────────────────────────────────────────────────────
    "wacalc_title": {
        "en": (
            "📊 <b>Share Calculator Report</b>\n\n"
            "Send financial analysis to <b>{name}</b>'s "
            "WhatsApp ({phone})\n\nSelect calculator:"
        ),
        "hi": (
            "📊 <b>कैलकुलेटर रिपोर्ट भेजें</b>\n\n"
            "<b>{name}</b> के WhatsApp ({phone}) पर\n"
            "वित्तीय विश्लेषण भेजें\n\nकैलकुलेटर चुनें:"
        ),
    },
    "wacalc_sent": {
        "en": (
            "✅ <b>Calculator Report Sent!</b>\n\n"
            "📊 Type: {calc_type}\n"
            "👤 To: {name} ({phone})\n"
            "{report_line}\n"
            "Also logged as an interaction."
        ),
        "hi": (
            "✅ <b>कैलकुलेटर रिपोर्ट भेजी गई!</b>\n\n"
            "📊 प्रकार: {calc_type}\n"
            "👤 को: {name} ({phone})\n"
            "{report_line}\n"
            "इंटरैक्शन भी लॉग किया गया।"
        ),
    },

    # ── WA Dashboard / Portfolio ───────────────────────────────────────────
    "wadash_sent": {
        "en": "✅ <b>Portfolio summary sent to {name}</b> ({phone}) on WhatsApp",
        "hi": "✅ <b>पोर्टफोलियो सारांश {name}</b> ({phone}) को WhatsApp पर भेजा गया",
    },
    "wadash_no_data": {
        "en": "ℹ️ No policies found for <b>{name}</b>. Add one with /policy {lead_id}",
        "hi": "ℹ️ <b>{name}</b> के लिए कोई पॉलिसी नहीं मिली। /policy {lead_id} से जोड़ें",
    },

    # ── Dashboard ──────────────────────────────────────────────────────────
    "dashboard_title": {
        "en": "📊 <b>Business Dashboard</b>\n━━━━━━━━━━━━━━━━━━",
        "hi": "📊 <b>व्यापार डैशबोर्ड</b>\n━━━━━━━━━━━━━━━━━━",
    },

    # ── Language ───────────────────────────────────────────────────────────
    "lang_ask": {
        "en": "🌐 Current language: <b>English</b>\n\nSelect your preferred language:",
        "hi": "🌐 वर्तमान भाषा: <b>हिन्दी</b>\n\nअपनी पसंदीदा भाषा चुनें:",
    },
    "lang_changed_en": {
        "en": "✅ Language changed to <b>English</b> 🇬🇧",
        "hi": "✅ Language changed to <b>English</b> 🇬🇧",
    },
    "lang_changed_hi": {
        "en": "✅ भाषा <b>हिन्दी</b> में बदल दी गई 🇮🇳",
        "hi": "✅ भाषा <b>हिन्दी</b> में बदल दी गई 🇮🇳",
    },

    # ── Errors ─────────────────────────────────────────────────────────────
    "access_denied": {
        "en": "⛔ Access denied. Contact admin to get authorized.",
        "hi": "⛔ पहुँच अस्वीकृत। एडमिन से संपर्क करें।",
    },
    "not_registered": {
        "en": "⚠️ You haven't registered yet. Use /start to set up your profile.",
        "hi": "⚠️ आपने अभी तक रजिस्टर नहीं किया। /start से प्रोफ़ाइल बनाएं।",
    },
    "lead_not_found": {
        "en": "❌ Lead not found",
        "hi": "❌ लीड नहीं मिली",
    },
    "invalid_id": {
        "en": "❌ Invalid lead ID",
        "hi": "❌ अमान्य लीड ID",
    },
    "invalid_date": {
        "en": "❌ Invalid format. Use DD-MM-YYYY or /skip",
        "hi": "❌ अमान्य प्रारूप। DD-MM-YYYY या /skip इस्तेमाल करें",
    },
    "cancelled": {
        "en": "❌ Cancelled.",
        "hi": "❌ रद्द कर दिया।",
    },
    "no_leads": {
        "en": "No leads yet. Add one with /addlead",
        "hi": "अभी कोई लीड नहीं है। /addlead से जोड़ें",
    },

    # ── Help ───────────────────────────────────────────────────────────────
    "help_text": {
        "en": (
            "📚 <b>Sarathi-AI Business Technologies — Commands</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 <b>Lead Management:</b>\n"
            "  /addlead — Add new prospect\n"
            "  /leads — List/search leads\n"
            "  /leads name — Search by name\n"
            "  /lead id — View lead full details\n"
            "  /pipeline — Sales pipeline view\n\n"
            "🎙️ <b>Voice-to-Action:</b>\n"
            "  Send any voice note → auto-creates lead!\n"
            "  <i>Just record and send — AI does the rest</i>\n\n"
            "📞 <b>Sales Cycle:</b>\n"
            "  /followup id — Log interaction\n"
            "  /convert id — Move to next stage\n"
            "  /policy id — Record sold policy\n\n"
            "🏥 <b>Claims Helper:</b>\n"
            "  /claim — Start a new claim\n"
            "  /claims — View all claims\n"
            "  /claimstatus id — Claim details + documents\n\n"
            "📊 <b>Calculators:</b>\n"
            "  /calc — Financial calculators\n"
            "  /wacalc id — Send calculator report to client's WhatsApp\n"
            "  <i>(Inflation, HLV, Retirement, EMI, Health, SIP)</i>\n\n"
            "🔄 <b>Reminders &amp; Communication:</b>\n"
            "  /renewals — Upcoming renewals\n"
            "  /greet id — Send greeting\n"
            "  /wa id msg — WhatsApp message\n"
            "  /wadash id — Send portfolio to client's WhatsApp\n\n"
            "📈 <b>Reports:</b>\n"
            "  /dashboard — Business dashboard\n\n"
            "⚙️ <b>Settings:</b>\n"
            "  /editprofile — Edit your name/phone/email\n"
            "  /editlead id — Edit lead details\n"
            "  /lang — Change language (English / हिन्दी)\n\n"
            "ℹ️ /help — This message\n\n"
            "<i>Sarathi-AI Business Technologies</i> 🛡️"
        ),
        "hi": (
            "📚 <b>सारथी बिज़नेस सूट — कमांड</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 <b>लीड प्रबंधन:</b>\n"
            "  /addlead — नई लीड जोड़ें\n"
            "  /leads — लीड देखें/खोजें\n"
            "  /leads नाम — नाम से खोजें\n"
            "  /lead id — लीड विवरण देखें\n"
            "  /pipeline — सेल्स पाइपलाइन\n\n"
            "🎙️ <b>वॉइस-टू-एक्शन:</b>\n"
            "  कोई भी वॉइस नोट भेजें → ऑटो लीड बनेगी!\n"
            "  <i>बस रिकॉर्ड करें और भेजें — AI बाकी करेगा</i>\n\n"
            "📞 <b>सेल्स साइकल:</b>\n"
            "  /followup id — इंटरैक्शन लॉग करें\n"
            "  /convert id — स्टेज बदलें\n"
            "  /policy id — पॉलिसी दर्ज करें\n\n"
            "🏥 <b>क्लेम सहायक:</b>\n"
            "  /claim — नया क्लेम शुरू करें\n"
            "  /claims — सभी क्लेम देखें\n"
            "  /claimstatus id — क्लेम विवरण + दस्तावेज़\n\n"
            "📊 <b>कैलकुलेटर:</b>\n"
            "  /calc — वित्तीय कैलकुलेटर\n"
            "  /wacalc id — ग्राहक के WhatsApp पर कैलकुलेटर रिपोर्ट भेजें\n"
            "  <i>(इन्फ्लेशन, HLV, रिटायरमेंट, EMI, हेल्थ, SIP)</i>\n\n"
            "🔄 <b>रिमाइंडर और संवाद:</b>\n"
            "  /renewals — आगामी नवीनीकरण\n"
            "  /greet id — अभिवादन भेजें\n"
            "  /wa id संदेश — WhatsApp संदेश\n"
            "  /wadash id — ग्राहक को पोर्टफोलियो WhatsApp पर भेजें\n\n"
            "📈 <b>रिपोर्ट:</b>\n"
            "  /dashboard — व्यापार डैशबोर्ड\n\n"
            "⚙️ <b>सेटिंग्स:</b>\n"
            "  /editprofile — अपना नाम/फ़ोन/ईमेल बदलें\n"
            "  /editlead id — लीड विवरण बदलें\n"
            "  /lang — भाषा बदलें (English / हिन्दी)\n\n"
            "ℹ️ /help — यह संदेश\n\n"
            "<i>सुरक्षा से समृद्धि तक</i> 🛡️"
        ),
    },

    # ── Email Templates ────────────────────────────────────────────────────
    "email_welcome_subject": {
        "en": "Welcome to Sarathi-AI Business Technologies!",
        "hi": "Sarathi-AI बिज़नेस टेक्नोलॉजीज में आपका स्वागत है!",
    },
    "email_welcome_body": {
        "en": (
            "Dear {name},\n\n"
            "Welcome to Sarathi-AI! Your 14-day free trial is now active.\n"
            "Your Tenant ID: {tenant_id}\n\n"
            "Next steps:\n"
            "1. Create your Telegram CRM bot\n"
            "2. Add your first lead\n"
            "3. Start growing your business!\n\n"
            "Visit: sarathi-ai.com/getting-started\n\n"
            "Best regards,\nTeam Sarathi-AI"
        ),
        "hi": (
            "प्रिय {name},\n\n"
            "Sarathi-AI में आपका स्वागत है! आपका 14 दिन का फ्री ट्रायल शुरू हो गया है।\n"
            "आपका Tenant ID: {tenant_id}\n\n"
            "अगले कदम:\n"
            "1. अपना Telegram CRM बोट बनाएं\n"
            "2. पहली लीड जोड़ें\n"
            "3. अपना व्यवसाय बढ़ाना शुरू करें!\n\n"
            "जाएं: sarathi-ai.com/getting-started\n\n"
            "शुभकामनाएं,\nटीम Sarathi-AI"
        ),
    },
    "email_renewal_subject": {
        "en": "Policy Renewal Reminder — {client_name}",
        "hi": "पॉलिसी रिन्यूअल रिमाइंडर — {client_name}",
    },
    "email_renewal_body": {
        "en": (
            "Dear {advisor_name},\n\n"
            "This is a reminder that your client {client_name}'s policy "
            "is due for renewal on {date}.\n\n"
            "Premium: {premium}\n"
            "Policy: {policy_type}\n\n"
            "Please follow up to ensure timely renewal.\n\n"
            "Best regards,\nSarathi-AI"
        ),
        "hi": (
            "प्रिय {advisor_name},\n\n"
            "यह रिमाइंडर है कि आपके ग्राहक {client_name} की पॉलिसी "
            "{date} को रिन्यूअल के लिए है।\n\n"
            "प्रीमियम: {premium}\n"
            "पॉलिसी: {policy_type}\n\n"
            "कृपया समय पर रिन्यूअल सुनिश्चित करें।\n\n"
            "शुभकामनाएं,\nSarathi-AI"
        ),
    },

    # ── Campaign Messages ──────────────────────────────────────────────────
    "campaign_birthday": {
        "en": (
            "🎂 Happy Birthday, {name}! 🎉\n\n"
            "Wishing you a wonderful year ahead filled with "
            "health, happiness and prosperity!\n\n"
            "Your trusted insurance advisor,\n{advisor_name}"
        ),
        "hi": (
            "🎂 जन्मदिन मुबारक, {name}! 🎉\n\n"
            "आपको स्वास्थ्य, खुशी और समृद्धि से भरा "
            "शानदार वर्ष की शुभकामनाएं!\n\n"
            "आपके विश्वसनीय बीमा सलाहकार,\n{advisor_name}"
        ),
    },
    "campaign_anniversary": {
        "en": (
            "💍 Happy Anniversary, {name}! 🎊\n\n"
            "Wishing you and your family many more years of "
            "togetherness and joy!\n\n"
            "Warm regards,\n{advisor_name}"
        ),
        "hi": (
            "💍 सालगिरह मुबारक, {name}! 🎊\n\n"
            "आपको और आपके परिवार को एकजुटता और खुशी के "
            "और कई वर्षों की शुभकामनाएं!\n\n"
            "शुभकामनाएं,\n{advisor_name}"
        ),
    },
    "campaign_renewal_reminder": {
        "en": (
            "🔔 Renewal Reminder\n\n"
            "Dear {name},\n"
            "Your {policy_type} policy is due for renewal on {date}.\n"
            "Premium: ₹{premium}\n\n"
            "Would you like to continue with the same coverage or "
            "explore better options? Reply YES to discuss.\n\n"
            "Regards,\n{advisor_name}"
        ),
        "hi": (
            "🔔 रिन्यूअल रिमाइंडर\n\n"
            "प्रिय {name},\n"
            "आपकी {policy_type} पॉलिसी {date} को रिन्यूअल के लिए है।\n"
            "प्रीमियम: ₹{premium}\n\n"
            "क्या आप समान कवरेज जारी रखना चाहते हैं या "
            "बेहतर विकल्प देखना चाहते हैं? चर्चा के लिए YES रिप्लाई करें।\n\n"
            "शुभकामनाएं,\n{advisor_name}"
        ),
    },
    "campaign_festival": {
        "en": (
            "🪔 Happy {festival}! 🎉\n\n"
            "Wishing you and your family a joyful and prosperous "
            "{festival}!\n\n"
            "May this festive season bring you good health and happiness.\n\n"
            "Warm regards,\n{advisor_name}\n{firm_name}"
        ),
        "hi": (
            "🪔 {festival} की शुभकामनाएं! 🎉\n\n"
            "आपको और आपके परिवार को {festival} की "
            "ढेर सारी शुभकामनाएं!\n\n"
            "यह त्योहार आपको स्वास्थ्य और खुशी दे।\n\n"
            "शुभकामनाएं,\n{advisor_name}\n{firm_name}"
        ),
    },

    # ── WhatsApp Greetings ─────────────────────────────────────────────────
    "wa_birthday_greeting": {
        "en": (
            "🎂 Happy Birthday, {name}! 🎉\n\n"
            "Wishing you a wonderful year ahead!\n\n"
            "Your trusted advisor,\n{advisor_name} — {firm_name}"
        ),
        "hi": (
            "🎂 जन्मदिन मुबारक, {name}! 🎉\n\n"
            "आपको शानदार वर्ष की शुभकामनाएं!\n\n"
            "आपके विश्वसनीय सलाहकार,\n{advisor_name} — {firm_name}"
        ),
    },
    "wa_anniversary_greeting": {
        "en": (
            "💍 Happy Anniversary, {name}! 🎊\n\n"
            "Wishing you many happy returns!\n\n"
            "Warm regards,\n{advisor_name} — {firm_name}"
        ),
        "hi": (
            "💍 सालगिरह मुबारक, {name}! 🎊\n\n"
            "आपको बहुत-बहुत शुभकामनाएं!\n\n"
            "शुभकामनाएं,\n{advisor_name} — {firm_name}"
        ),
    },

    # ── API Response Messages ──────────────────────────────────────────────
    "signup_success": {
        "en": "Account created successfully! Your 14-day free trial is active.",
        "hi": "अकाउंट सफलतापूर्वक बनाया गया! आपका 14 दिन का फ्री ट्रायल शुरू है।",
    },
    "payment_success": {
        "en": "Payment successful! Your subscription is now active.",
        "hi": "पेमेंट सफल! आपका सब्सक्रिप्शन अब सक्रिय है।",
    },
    "login_otp_sent": {
        "en": "OTP sent to your phone number.",
        "hi": "आपके फ़ोन नंबर पर OTP भेजा गया।",
    },
    "login_success": {
        "en": "Login successful!",
        "hi": "लॉगिन सफल!",
    },
    "logout_success": {
        "en": "Logged out successfully.",
        "hi": "सफलतापूर्वक लॉगआउट हो गया।",
    },

    # ══════════════════════════════════════════════════════════════════════
    #  PHASE 14 — EXPANDED i18n (170+ new strings for full Hindi coverage)
    # ══════════════════════════════════════════════════════════════════════

    # ── Rate Limiting / Auth ────────────────────────────────────────────
    "rate_limited": {
        "en": "⏳ Too many requests. Please wait a moment and try again.",
        "hi": "⏳ बहुत ज़्यादा अनुरोध। कृपया कुछ देर प्रतीक्षा करें।",
    },
    "not_registered_yet": {
        "en": "⚠️ You're not registered yet.\nUse /start to create your profile.",
        "hi": "⚠️ आप अभी तक रजिस्टर्ड नहीं हैं।\n/start से प्रोफ़ाइल बनाएं।",
    },
    "account_deactivated": {
        "en": "⚠️ Your account has been deactivated.\nContact the firm owner to re-activate.",
        "hi": "⚠️ आपका अकाउंट निष्क्रिय कर दिया गया है।\nफिर से एक्टिवेट करने के लिए फर्म मालिक से संपर्क करें।",
    },
    "subscription_expired": {
        "en": "⚠️ Your subscription has expired.\nAsk the firm owner to renew at sarathi-ai.com",
        "hi": "⚠️ आपका सब्सक्रिप्शन समाप्त हो गया है।\nफर्म मालिक से sarathi-ai.com पर रिन्यू करवाएं।",
    },
    "wrong_firm_bot": {
        "en": "⚠️ You're not registered with this firm's bot.\nUse your own firm's bot or /start on the main @SarathiBizBot.",
        "hi": "⚠️ आप इस फर्म के बोट पर रजिस्टर्ड नहीं हैं।\nअपने फर्म का बोट या @SarathiBizBot पर /start करें।",
    },
    "feature_locked": {
        "en": "🔒 *Feature Locked*\n\n{reason}\n\nUse /plans to view available plans.",
        "hi": "🔒 *फ़ीचर लॉक*\n\n{reason}\n\n/plans से उपलब्ध प्लान देखें।",
    },
    "owner_only": {
        "en": "🔒 This command is for firm owners only.",
        "hi": "🔒 यह कमांड केवल फर्म मालिकों के लिए है।",
    },
    "superadmin_only": {
        "en": "🔒 Super-admin access only.",
        "hi": "🔒 केवल सुपर-एडमिन एक्सेस।",
    },

    # ── Onboarding Extended ─────────────────────────────────────────────
    "otp_sent": {
        "en": "📲 <b>OTP Sent!</b>\n\nA 6-digit verification code has been sent to your WhatsApp number <b>+91 {phone}</b>.\n\nPlease enter the OTP below:\n<i>(Valid for 10 minutes)</i>",
        "hi": "📲 <b>OTP भेजा गया!</b>\n\nआपके WhatsApp नंबर <b>+91 {phone}</b> पर 6 अंकों का कोड भेजा गया है।\n\nकृपया नीचे OTP दर्ज करें:\n<i>(10 मिनट तक वैध)</i>",
    },
    "invalid_otp": {
        "en": "❌ Please enter a valid <b>6-digit OTP</b>.\nCheck your WhatsApp for the verification code.",
        "hi": "❌ कृपया वैध <b>6 अंकों का OTP</b> दर्ज करें।\nअपना WhatsApp चेक करें।",
    },
    "otp_failed": {
        "en": "❌ <b>Invalid or expired OTP.</b>\n\nPlease try again, or type your phone number again to get a new OTP.\nYou can also type /cancel to abort.",
        "hi": "❌ <b>अमान्य या समाप्त OTP।</b>\n\nकृपया दोबारा प्रयास करें, या नया OTP पाने के लिए अपना फ़ोन नंबर फिर से टाइप करें।\nरद्द करने के लिए /cancel।",
    },
    "phone_verified": {
        "en": "✅ <b>Phone verified!</b>",
        "hi": "✅ <b>फ़ोन सत्यापित!</b>",
    },
    "email_otp_sent": {
        "en": "📧 We've sent a <b>6-digit OTP</b> to <b>{email}</b>\n\nPlease enter the code to verify your email.\n⏳ Code expires in 10 minutes.",
        "hi": "📧 हमने <b>{email}</b> पर <b>6 अंकों का OTP</b> भेजा है\n\nकृपया ईमेल सत्यापित करने के लिए कोड दर्ज करें।\n⏳ कोड 10 मिनट में समाप्त होगा।",
    },
    "invalid_email_otp": {
        "en": "❌ Please enter the <b>6-digit code</b> sent to your email.\nOnly digits, no spaces.",
        "hi": "❌ कृपया ईमेल पर भेजा गया <b>6 अंकों का कोड</b> दर्ज करें।\nकेवल अंक, बिना स्पेस।",
    },
    "email_verified": {
        "en": "✅ Email verified!",
        "hi": "✅ ईमेल सत्यापित!",
    },
    "email_otp_failed": {
        "en": "❌ Invalid or expired OTP. Please try again.\n\n💡 Check your spam/junk folder. Enter /cancel to start over.",
        "hi": "❌ अमान्य या समाप्त OTP। कृपया दोबारा प्रयास करें।\n\n💡 स्पैम/जंक फ़ोल्डर चेक करें। /cancel से शुरू करें।",
    },
    "ask_city_onboard": {
        "en": "📍 Almost done! What <b>city</b> are you based in?\n\n💡 Example: <b>Mumbai</b>, <b>Delhi</b>, <b>Indore</b>",
        "hi": "📍 लगभग हो गया! आप किस <b>शहर</b> में हैं?\n\n💡 उदाहरण: <b>मुंबई</b>, <b>दिल्ली</b>, <b>इंदौर</b>",
    },
    "invalid_city": {
        "en": "❌ City must be 2-100 characters. Please enter your city name.\n\n💡 Example: <b>Mumbai</b>, <b>New Delhi</b>, <b>Bengaluru</b>",
        "hi": "❌ शहर का नाम 2-100 अक्षर का होना चाहिए।\n\n💡 उदाहरण: <b>मुंबई</b>, <b>नई दिल्ली</b>, <b>बेंगलुरु</b>",
    },
    "invalid_city_chars": {
        "en": "❌ City name should contain only letters, spaces and hyphens.\n\n💡 Example: <b>Mumbai</b>, <b>New Delhi</b>",
        "hi": "❌ शहर के नाम में केवल अक्षर, स्पेस और हाइफ़न होने चाहिए।\n\n💡 उदाहरण: <b>मुंबई</b>, <b>नई दिल्ली</b>",
    },
    "phone_already_registered": {
        "en": "❌ This phone number is already registered with an active account.\n\nIf this is your number, use /start on your existing bot, or ask your firm owner for an invite code.",
        "hi": "❌ यह फ़ोन नंबर पहले से एक सक्रिय अकाउंट पर रजिस्टर्ड है।\n\nयदि यह आपका नंबर है, तो अपने बोट पर /start करें या फर्म मालिक से इनवाइट कोड मांगें।",
    },
    "phone_trial_used": {
        "en": "❌ A trial was already used with this phone number.\n\nFree trial is available <b>once per phone</b>.\nTo reactivate, please subscribe at:\n🌐 <b>sarathi-ai.com</b> → Choose a plan",
        "hi": "❌ इस फ़ोन नंबर से पहले ही ट्रायल लिया जा चुका है।\n\nफ्री ट्रायल <b>प्रति फ़ोन एक बार</b> उपलब्ध है।\nफिर से एक्टिवेट करने के लिए:\n🌐 <b>sarathi-ai.com</b> → प्लान चुनें",
    },
    "email_already_registered": {
        "en": "❌ This email is already registered with an active account.\n\nUse /start on your existing bot, or try a different email.",
        "hi": "❌ यह ईमेल पहले से एक सक्रिय अकाउंट पर रजिस्टर्ड है।\n\nअपने बोट पर /start करें या दूसरा ईमेल प्रयोग करें।",
    },
    "email_trial_used": {
        "en": "❌ A trial was already used with this email.\n\nFree trial is available <b>once per email</b>.\nTo reactivate, visit 🌐 <b>sarathi-ai.com</b> to subscribe.",
        "hi": "❌ इस ईमेल से पहले ही ट्रायल लिया जा चुका है।\n\nफ्री ट्रायल <b>प्रति ईमेल एक बार</b> उपलब्ध है।\nसब्सक्राइब करने के लिए 🌐 <b>sarathi-ai.com</b> जाएं।",
    },
    "firm_name_invalid": {
        "en": "❌ Firm name must be 2-200 characters. Please try again.",
        "hi": "❌ फर्म का नाम 2-200 अक्षर का होना चाहिए। कृपया दोबारा प्रयास करें।",
    },
    "name_invalid": {
        "en": "❌ Name must be 2-100 characters. Please enter your full name.",
        "hi": "❌ नाम 2-100 अक्षर का होना चाहिए। कृपया अपना पूरा नाम दर्ज करें।",
    },
    "name_need_full": {
        "en": "✏️ Please enter your <b>full name</b> (first name + last name).\n\n💡 Example: <b>Rajesh Sharma</b> or <b>Priya Gupta</b>\n\n<i>Middle name is optional — just first + last is enough.</i>",
        "hi": "✏️ कृपया अपना <b>पूरा नाम</b> दर्ज करें (पहला नाम + उपनाम)।\n\n💡 उदाहरण: <b>राजेश शर्मा</b> या <b>प्रिया गुप्ता</b>\n\n<i>मध्य नाम वैकल्पिक है।</i>",
    },

    # ── Invite / Team ───────────────────────────────────────────────────
    "invite_invalid": {
        "en": "❌ Invalid or expired invite code.\nPlease check with your firm owner and try again.\n\nOr use /start to register a new firm.",
        "hi": "❌ अमान्य या समाप्त इनवाइट कोड।\nकृपया अपने फर्म मालिक से जांचें और दोबारा प्रयास करें।\n\nया नई फर्म रजिस्टर करने के लिए /start करें।",
    },
    "team_full": {
        "en": "⚠️ <b>Team is full</b>\n\n{reason}\n\nAsk your firm owner to upgrade the plan, then try again.",
        "hi": "⚠️ <b>टीम भरी हुई है</b>\n\n{reason}\n\nफर्म मालिक से प्लान अपग्रेड करवाएं, फिर दोबारा प्रयास करें।",
    },
    "invite_valid": {
        "en": "✅ Invite code valid!\nYou're joining: <b>{firm}</b>\n\nWhat is your <b>full name</b>?",
        "hi": "✅ इनवाइट कोड वैध!\nआप इसमें शामिल हो रहे हैं: <b>{firm}</b>\n\nआपका <b>पूरा नाम</b> क्या है?",
    },

    # ── Policy Recording ────────────────────────────────────────────────
    "policy_title": {
        "en": "📋 <b>Record Policy for {name}</b>\n\nInsurer name? (e.g., LIC, HDFC, ICICI Prudential)",
        "hi": "📋 <b>{name} के लिए पॉलिसी दर्ज करें</b>\n\nबीमा कंपनी का नाम? (जैसे LIC, HDFC, ICICI Prudential)",
    },
    "policy_plan_ask": {
        "en": "📋 Plan name?",
        "hi": "📋 प्लान का नाम?",
    },
    "policy_si_ask": {
        "en": "💰 Sum Insured (in ₹)?",
        "hi": "💰 बीमा राशि (₹ में)?",
    },
    "policy_premium_ask": {
        "en": "💳 Annual Premium (in ₹)?",
        "hi": "💳 वार्षिक प्रीमियम (₹ में)?",
    },
    "policy_start_ask": {
        "en": "📅 Policy start date? (DD-MM-YYYY)",
        "hi": "📅 पॉलिसी शुरू होने की तारीख? (DD-MM-YYYY)",
    },
    "policy_renewal_ask": {
        "en": "🔄 Renewal date? (DD-MM-YYYY)",
        "hi": "🔄 रिन्यूअल तारीख? (DD-MM-YYYY)",
    },
    "policy_recorded": {
        "en": "✅ <b>Policy Recorded!</b> 🎉",
        "hi": "✅ <b>पॉलिसी दर्ज हो गई!</b> 🎉",
    },
    "si_invalid": {
        "en": "❌ Sum Insured must be positive.",
        "hi": "❌ बीमा राशि सकारात्मक होनी चाहिए।",
    },
    "si_too_high": {
        "en": "❌ Amount seems too high (max ₹100 Crore).",
        "hi": "❌ राशि बहुत अधिक लगती है (अधिकतम ₹100 करोड़)।",
    },
    "premium_invalid": {
        "en": "❌ Premium must be positive.",
        "hi": "❌ प्रीमियम सकारात्मक होना चाहिए।",
    },
    "premium_too_high": {
        "en": "❌ Amount seems too high (max ₹10 Crore).",
        "hi": "❌ राशि बहुत अधिक लगती है (अधिकतम ₹10 करोड़)।",
    },
    "enter_valid_number": {
        "en": "❌ Enter a valid number (e.g., {example})",
        "hi": "❌ वैध संख्या दर्ज करें (जैसे {example})",
    },
    "invalid_date_format": {
        "en": "❌ Use DD-MM-YYYY format",
        "hi": "❌ DD-MM-YYYY प्रारूप इस्तेमाल करें",
    },
    "renewal_before_start": {
        "en": "❌ Renewal date must be after the start date.",
        "hi": "❌ रिन्यूअल तारीख शुरू होने की तारीख के बाद होनी चाहिए।",
    },

    # ── Claims ──────────────────────────────────────────────────────────
    "claims_title": {
        "en": "🏥 <b>Claims Helper</b>",
        "hi": "🏥 <b>क्लेम सहायक</b>",
    },
    "claim_desc_ask": {
        "en": "⚠️ Please provide a brief description of the claim.",
        "hi": "⚠️ कृपया क्लेम का संक्षिप्त विवरण दें।",
    },
    "claim_hospital_ask": {
        "en": "🏥 Hospital Name?\n\nProvide the hospital/provider name (or /skip)",
        "hi": "🏥 अस्पताल का नाम?\n\nअस्पताल/प्रदाता का नाम दें (या /skip)",
    },
    "claim_cancelled": {
        "en": "🗑️ Claim cancelled.",
        "hi": "🗑️ क्लेम रद्द।",
    },
    "no_claims": {
        "en": "📭 No claims found.",
        "hi": "📭 कोई क्लेम नहीं मिला।",
    },
    "claim_not_found": {
        "en": "❌ Claim not found.",
        "hi": "❌ क्लेम नहीं मिला।",
    },
    "claim_no_leads": {
        "en": "📭 No leads found. Add leads first with /addlead",
        "hi": "📭 कोई लीड नहीं मिली। पहले /addlead से लीड जोड़ें",
    },
    "claim_select_client": {
        "en": "Select the client who needs to file a claim:",
        "hi": "वह क्लाइंट चुनें जिसका क्लेम दाखिल करना है:",
    },
    "claim_select_policy": {
        "en": "Select the policy for this claim:",
        "hi": "इस क्लेम के लिए पॉलिसी चुनें:",
    },
    "claim_no_policy_btn": {
        "en": "⚡ No policy / New claim",
        "hi": "⚡ बिना पॉलिसी / नया क्लेम",
    },
    "claim_what_type": {
        "en": "What type of claim?",
        "hi": "किस प्रकार का क्लेम?",
    },
    "claim_type_health": {
        "en": "🏥 Health / Mediclaim",
        "hi": "🏥 स्वास्थ्य / मेडिक्लेम",
    },
    "claim_type_term": {
        "en": "🛡️ Term Life / Death",
        "hi": "🛡️ टर्म लाइफ / मृत्यु",
    },
    "claim_type_motor": {
        "en": "🚗 Motor / Accident",
        "hi": "🚗 मोटर / दुर्घटना",
    },
    "claim_type_general": {
        "en": "📦 Other / General",
        "hi": "📦 अन्य / सामान्य",
    },
    "claim_type_health_short": {
        "en": "🏥 Health",
        "hi": "🏥 स्वास्थ्य",
    },
    "claim_type_term_short": {
        "en": "🛡️ Term Life",
        "hi": "🛡️ टर्म लाइफ",
    },
    "claim_type_motor_short": {
        "en": "🚗 Motor",
        "hi": "🚗 मोटर",
    },
    "claim_type_general_short": {
        "en": "📦 General",
        "hi": "📦 सामान्य",
    },
    "claim_docs_required": {
        "en": "📋 Documents Required:",
        "hi": "📋 आवश्यक दस्तावेज़:",
    },
    "claim_share_checklist": {
        "en": "💡 <i>Share this checklist with your client!</i>",
        "hi": "💡 <i>यह चेकलिस्ट अपने क्लाइंट को भेजें!</i>",
    },
    "claim_describe_now": {
        "en": "Now describe the claim briefly:",
        "hi": "अब क्लेम का संक्षिप्त विवरण दें:",
    },
    "claim_describe_hint": {
        "en": "<i>(What happened? When? Approximate amount?)</i>",
        "hi": "<i>(क्या हुआ? कब? अनुमानित राशि?)</i>",
    },
    "claim_desc_too_short": {
        "en": "⚠️ Please provide a brief description (at least 5 characters).",
        "hi": "⚠️ कृपया संक्षिप्त विवरण दें (कम से कम 5 अक्षर)।",
    },
    "claim_hospital_name": {
        "en": "🏥 <b>Hospital Name?</b>\n\nEnter the hospital/clinic name (or type <b>skip</b>):",
        "hi": "🏥 <b>अस्पताल का नाम?</b>\n\nअस्पताल/क्लिनिक का नाम दें (या <b>skip</b> लिखें):",
    },
    "claim_summary_title": {
        "en": "🏥 <b>Claim Summary</b>",
        "hi": "🏥 <b>क्लेम सारांश</b>",
    },
    "claim_client_label": {
        "en": "Client",
        "hi": "क्लाइंट",
    },
    "claim_type_label": {
        "en": "Type",
        "hi": "प्रकार",
    },
    "claim_desc_label": {
        "en": "Description",
        "hi": "विवरण",
    },
    "claim_hospital_label": {
        "en": "Hospital",
        "hi": "अस्पताल",
    },
    "claim_submit_q": {
        "en": "Submit this claim?",
        "hi": "क्या यह क्लेम जमा करें?",
    },
    "claim_submit_btn": {
        "en": "✅ Submit Claim",
        "hi": "✅ क्लेम जमा करें",
    },
    "claim_cancel_btn": {
        "en": "❌ Cancel",
        "hi": "❌ रद्द करें",
    },
    "claim_agent_not_found": {
        "en": "❌ Agent not found.",
        "hi": "❌ एजेंट नहीं मिला।",
    },
    "claim_initiated": {
        "en": "✅ <b>Claim Initiated!</b>",
        "hi": "✅ <b>क्लेम शुरू हो गया!</b>",
    },
    "claim_doc_checklist": {
        "en": "📋 <b>Document Checklist:</b> {count} items",
        "hi": "📋 <b>दस्तावेज़ चेकलिस्ट:</b> {count} आइटम",
    },
    "claim_status_initiated": {
        "en": "📊 <b>Status:</b> Initiated",
        "hi": "📊 <b>स्थिति:</b> शुरू",
    },
    "claim_use_claims": {
        "en": "Use /claims to view all claims.",
        "hi": "/claims से सभी क्लेम देखें।",
    },
    "claim_use_claimstatus": {
        "en": "Use /claimstatus {id} to check status.",
        "hi": "/claimstatus {id} से स्थिति देखें।",
    },
    "claims_your_title": {
        "en": "🏥 <b>Your Claims</b>",
        "hi": "🏥 <b>आपके क्लेम</b>",
    },
    "claim_lead_not_found": {
        "en": "❌ Lead not found.",
        "hi": "❌ लीड नहीं मिली।",
    },
    "claim_details_title": {
        "en": "🏥 <b>Claim #{id} — Details</b>",
        "hi": "🏥 <b>क्लेम #{id} — विवरण</b>",
    },
    "claim_insurer_label": {
        "en": "Insurer",
        "hi": "बीमाकर्ता",
    },
    "claim_policy_label": {
        "en": "Policy",
        "hi": "पॉलिसी",
    },
    "claim_details_label": {
        "en": "Details",
        "hi": "विवरण",
    },
    "claim_created_label": {
        "en": "📅 Created",
        "hi": "📅 बनाया गया",
    },
    "claimstatus_usage": {
        "en": "Usage: /claimstatus &lt;claim_id&gt;\nExample: /claimstatus 1",
        "hi": "उपयोग: /claimstatus &lt;claim_id&gt;\nउदाहरण: /claimstatus 1",
    },
    "claim_policy_count": {
        "en": "{count} {word}",
        "hi": "{count} पॉलिसी",
    },
    "claim_status_map": {
        "en": "initiated|documents_pending|submitted|under_review|approved|rejected|settled",
        "hi": "शुरू|दस्तावेज़ लंबित|जमा|समीक्षा में|स्वीकृत|अस्वीकृत|निपटाया",
    },
    "claim_status_label": {
        "en": "Status",
        "hi": "स्थिति",
    },

    # ── Edit Profile / Lead ─────────────────────────────────────────────
    "settings_title": {
        "en": "⚙️ <b>Settings</b>",
        "hi": "⚙️ <b>सेटिंग्स</b>",
    },
    "edit_profile_title": {
        "en": "✏️ <b>Edit Profile</b>",
        "hi": "✏️ <b>प्रोफ़ाइल संपादित करें</b>",
    },
    "field_updated": {
        "en": "✅ {field} updated to: <b>{value}</b>",
        "hi": "✅ {field} अपडेट किया गया: <b>{value}</b>",
    },
    "photo_updated": {
        "en": "✅ Profile photo updated! 📸",
        "hi": "✅ प्रोफ़ाइल फ़ोटो अपडेट हो गई! 📸",
    },
    "photo_failed": {
        "en": "❌ Failed to save photo. Please try again.",
        "hi": "❌ फ़ोटो सेव करने में विफल। कृपया दोबारा प्रयास करें।",
    },
    "lead_not_found_access": {
        "en": "❌ Lead not found or access denied.",
        "hi": "❌ लीड नहीं मिली या एक्सेस अस्वीकार।",
    },
    "invalid_phone_edit": {
        "en": "❌ Invalid phone number.",
        "hi": "❌ अमान्य फ़ोन नंबर।",
    },
    "invalid_email_edit": {
        "en": "❌ Invalid email format.",
        "hi": "❌ अमान्य ईमेल प्रारूप।",
    },
    "dob_future": {
        "en": "❌ Date cannot be in the future.",
        "hi": "❌ तारीख भविष्य में नहीं हो सकती।",
    },
    "invalid_year": {
        "en": "❌ Invalid year.",
        "hi": "❌ अमान्य वर्ष।",
    },

    # ── Voice / AI ──────────────────────────────────────────────────────
    "ai_not_configured": {
        "en": "❌ AI service not configured.",
        "hi": "❌ AI सेवा कॉन्फ़िगर नहीं है।",
    },
    "voice_too_long": {
        "en": "⚠️ Voice note too long (max 2 minutes). Please record a shorter message.",
        "hi": "⚠️ वॉइस नोट बहुत लंबा (अधिकतम 2 मिनट)। कृपया छोटा संदेश रिकॉर्ड करें।",
    },
    "voice_processing": {
        "en": "🎙️ Processing your voice note...",
        "hi": "🎙️ आपका वॉइस नोट प्रोसेस हो रहा है...",
    },
    "voice_discarded": {
        "en": "🗑️ Voice note discarded.",
        "hi": "🗑️ वॉइस नोट हटा दिया।",
    },
    "ai_tools_locked": {
        "en": "🔒 AI Tools require the Team plan or higher.\nUpgrade at sarathi-ai.com to unlock.",
        "hi": "🔒 AI टूल्स के लिए Team प्लान या उच्चतर चाहिए।\nअनलॉक करने के लिए sarathi-ai.com पर अपग्रेड करें।",
    },
    "ai_analyzing": {
        "en": "🎯 AI is analyzing your lead(s)...",
        "hi": "🎯 AI आपकी लीड(ओं) का विश्लेषण कर रहा है...",
    },
    "ai_crafting_pitch": {
        "en": "💡 AI is crafting a personalized pitch...",
        "hi": "💡 AI व्यक्तिगत पिच तैयार कर रहा है...",
    },
    "ai_objection_handling": {
        "en": "🛡️ AI is preparing counter-arguments...",
        "hi": "🛡️ AI प्रति-तर्क तैयार कर रहा है...",
    },
    "csv_processing": {
        "en": "📥 Processing CSV file for lead import...",
        "hi": "📥 लीड इम्पोर्ट के लिए CSV फ़ाइल प्रोसेस हो रही है...",
    },

    # ── Calculator Bot ──────────────────────────────────────────────────
    "calc_select_prompt": {
        "en": "🧮 <b>Financial Calculators</b>\n\nSelect a calculator:",
        "hi": "🧮 <b>वित्तीय कैलकुलेटर</b>\n\nकैलकुलेटर चुनें:",
    },
    "calc_cancelled": {
        "en": "👋 Calculator cancelled. Use the menu below to continue.",
        "hi": "👋 कैलकुलेटर रद्द। जारी रखने के लिए नीचे मेनू इस्तेमाल करें।",
    },
    "calc_unknown": {
        "en": "❌ Unknown calculator.",
        "hi": "❌ अज्ञात कैलकुलेटर।",
    },
    "no_result_to_share": {
        "en": "❌ No result to share.",
        "hi": "❌ शेयर करने के लिए कोई परिणाम नहीं।",
    },

    # ── WhatsApp Share ──────────────────────────────────────────────────
    "wa_share_ready": {
        "en": "✅ <b>WhatsApp Share Link Ready!</b>",
        "hi": "✅ <b>WhatsApp शेयर लिंक तैयार!</b>",
    },
    "no_renewals_due": {
        "en": "✅ No renewals due in the next 60 days. 🎉",
        "hi": "✅ अगले 60 दिनों में कोई रिन्यूअल नहीं। 🎉",
    },
    "no_phone_for_lead": {
        "en": "❌ No phone number for this lead.",
        "hi": "❌ इस लीड का फ़ोन नंबर नहीं है।",
    },
    "greeting_title": {
        "en": "💌 Send Greeting to <b>{name}</b>",
        "hi": "💌 <b>{name}</b> को अभिवादन भेजें",
    },

    # ── Navigation / Menu ───────────────────────────────────────────────
    "tap_to_start": {
        "en": "👇 Tap a button below to get started!",
        "hi": "👇 शुरू करने के लिए नीचे बटन दबाएं!",
    },
    "menu_interrupted": {
        "en": "⚠️ You tapped a menu button while entering data.\nComplete this step first, or tap below to cancel:",
        "hi": "⚠️ आपने डेटा दर्ज करते समय मेनू बटन दबाया।\nपहले यह स्टेप पूरा करें, या रद्द करने के लिए नीचे दबाएं:",
    },
    "conv_timeout": {
        "en": "⏰ Conversation timed out due to inactivity.\nType /start to begin again.",
        "hi": "⏰ निष्क्रियता के कारण बातचीत समाप्त हो गई।\nदोबारा शुरू करने के लिए /start टाइप करें।",
    },
    "conv_cancelled": {
        "en": "👋 Cancelled. Use the menu below to start fresh.",
        "hi": "👋 रद्द कर दिया। मेनू से नए सिरे से शुरू करें।",
    },
    "register_first": {
        "en": "👋 Please register first — type /start",
        "hi": "👋 कृपया पहले रजिस्टर करें — /start टाइप करें",
    },
    "unknown_input": {
        "en": "🤔 I didn't understand that. Use /help for commands or tap menu buttons.",
        "hi": "🤔 मुझे समझ नहीं आया। कमांड के लिए /help या मेनू बटन दबाएं।",
    },
    "text_only": {
        "en": "⚠️ I can only process text messages right now. Please type your response.",
        "hi": "⚠️ मैं अभी केवल टेक्स्ट मैसेज प्रोसेस कर सकता हूं। कृपया अपना जवाब टाइप करें।",
    },
    "only_text_in_conv": {
        "en": "⚠️ You're in the middle of a conversation. Please enter the requested information or type /cancel.",
        "hi": "⚠️ आप बातचीत के बीच में हैं। कृपया मांगी गई जानकारी दर्ज करें या /cancel टाइप करें।",
    },
    "team_manage_owner_only": {
        "en": "⚠️ Only firm owners/admins can manage the team.",
        "hi": "⚠️ केवल फर्म मालिक/एडमिन टीम प्रबंधन कर सकते हैं।",
    },
    "wa_config_owner_only": {
        "en": "🔒 Only firm owners can configure WhatsApp integration.",
        "hi": "🔒 केवल फर्म मालिक WhatsApp इंटीग्रेशन कॉन्फ़िगर कर सकते हैं।",
    },

    # ── Usage hints ─────────────────────────────────────────────────────
    "usage_lead": {
        "en": "Usage: /lead <lead_id>",
        "hi": "उपयोग: /lead <lead_id>",
    },
    "usage_convert": {
        "en": "Usage: /convert <lead_id>",
        "hi": "उपयोग: /convert <lead_id>",
    },
    "usage_policy": {
        "en": "Usage: /policy <lead_id>",
        "hi": "उपयोग: /policy <lead_id>",
    },
    "usage_wa": {
        "en": "Usage: /wa <lead_id> <message>",
        "hi": "उपयोग: /wa <lead_id> <संदेश>",
    },
    "usage_greet": {
        "en": "Usage: /greet <lead_id>",
        "hi": "उपयोग: /greet <lead_id>",
    },
    "usage_wacalc": {
        "en": "Usage: /wacalc <lead_id>",
        "hi": "उपयोग: /wacalc <lead_id>",
    },
    "usage_wadash": {
        "en": "Usage: /wadash <lead_id>",
        "hi": "उपयोग: /wadash <lead_id>",
    },
    "usage_claimstatus": {
        "en": "Usage: /claimstatus <claim_id>",
        "hi": "उपयोग: /claimstatus <claim_id>",
    },

    # ── Lead add notes ──────────────────────────────────────────────────
    "ask_notes": {
        "en": "📝 Any notes? (or /skip)",
        "hi": "📝 कोई नोट? (या /skip)",
    },
    "lead_addition_cancelled": {
        "en": "❌ Lead addition cancelled.",
        "hi": "❌ लीड जोड़ना रद्द।",
    },
    "duplicate_detected": {
        "en": "⚠️ <b>Duplicate Detected!</b>",
        "hi": "⚠️ <b>डुप्लिकेट मिला!</b>",
    },

    # ── Plans ───────────────────────────────────────────────────────────
    "plans_title": {
        "en": "💎 <b>Sarathi-AI Plans</b>",
        "hi": "💎 <b>सारथी-AI प्लान</b>",
    },
    "trial_info": {
        "en": (
            "🎉 <b>You're on a 14-day FREE trial!</b>\n\n"
            "During your trial you get full access to:\n"
            "• Lead management & pipeline tracking\n"
            "• WhatsApp greetings & calculators\n"
            "• Policy tracking & renewal reminders\n"
            "• PDF reports & dashboard\n\n"
            "📋 <b>Plans after trial:</b>\n"
            "├ 🧑 Solo Advisor — ₹199/mo (1 agent)\n"
            "├ 👥 Team — ₹799/mo (up to 5 agents)\n"
            "└ 🏢 Enterprise — ₹1,999/mo (up to 25 agents)\n\n"
            "💳 Upgrade anytime at <b>sarathi-ai.com</b>\n"
            "or use /plans to see details.\n\n"
            "⏰ We'll remind you before your trial ends. Enjoy! 🚀"
        ),
        "hi": (
            "🎉 <b>आप 14 दिन के फ्री ट्रायल पर हैं!</b>\n\n"
            "ट्रायल में आपको पूरी एक्सेस मिलेगी:\n"
            "• लीड प्रबंधन & पाइपलाइन ट्रैकिंग\n"
            "• WhatsApp अभिवादन & कैलकुलेटर\n"
            "• पॉलिसी ट्रैकिंग & रिन्यूअल रिमाइंडर\n"
            "• PDF रिपोर्ट & डैशबोर्ड\n\n"
            "📋 <b>ट्रायल के बाद प्लान:</b>\n"
            "├ 🧑 सोलो एडवाइज़र — ₹199/माह (1 एजेंट)\n"
            "├ 👥 टीम — ₹799/माह (5 एजेंट तक)\n"
            "└ 🏢 एंटरप्राइज़ — ₹1,999/माह (25 एजेंट तक)\n\n"
            "💳 किसी भी समय <b>sarathi-ai.com</b> पर अपग्रेड करें\n"
            "या विवरण के लिए /plans दबाएं।\n\n"
            "⏰ ट्रायल समाप्त होने से पहले हम आपको याद दिलाएंगे। आनंद लें! 🚀"
        ),
    },

    # ── Misc ────────────────────────────────────────────────────────────
    "no_leads_found": {
        "en": "📭 No leads found. Add your first lead with /addlead",
        "hi": "📭 कोई लीड नहीं मिली। /addlead से पहली लीड जोड़ें",
    },
    "policy_not_found": {
        "en": "❌ Policy not found.",
        "hi": "❌ पॉलिसी नहीं मिली।",
    },
    "agent_not_found": {
        "en": "❌ Agent not found.",
        "hi": "❌ एजेंट नहीं मिला।",
    },
    "need_select_one": {
        "en": "Please select at least one need",
        "hi": "कृपया कम से कम एक ज़रूरत चुनें",
    },
    "all_filled": {
        "en": "✅ All details are already filled!",
        "hi": "✅ सभी विवरण पहले से भरे हुए हैं!",
    },
    "enter_valid_phone": {
        "en": "📱 Please enter a 10-digit phone number (e.g., 9876543210):",
        "hi": "📱 कृपया 10 अंकों का फ़ोन नंबर दर्ज करें (जैसे 9876543210):",
    },
    "provide_lead_id": {
        "en": "❌ Please provide a lead ID.",
        "hi": "❌ कृपया एक लीड ID प्रदान करें।",
    },
    "invalid_need_type": {
        "en": "❌ Invalid need type.",
        "hi": "❌ अमान्य ज़रूरत प्रकार।",
    },

    # ── Help Command Sections ───────────────────────────────────────────
    "help_header": {
        "en": "📚 <b>Sarathi-AI — Commands</b>\n━━━━━━━━━━━━━━━━━━",
        "hi": "📚 <b>सारथी-AI — कमांड</b>\n━━━━━━━━━━━━━━━━━━",
    },
    "help_lead_mgmt": {
        "en": (
            "🎯 <b>Lead Management:</b>\n"
            "  /addlead — Add new prospect\n"
            "  /leads — List/search leads\n"
            "  /lead <i>id</i> — View lead details\n"
            "  /pipeline — Sales pipeline"
        ),
        "hi": (
            "🎯 <b>लीड प्रबंधन:</b>\n"
            "  /addlead — नई संभावना जोड़ें\n"
            "  /leads — लीड की सूची/खोज\n"
            "  /lead <i>id</i> — लीड विवरण देखें\n"
            "  /pipeline — सेल्स पाइपलाइन"
        ),
    },
    "help_voice": {
        "en": "🎙️ <b>Voice-to-Action:</b>\n  Send a voice note → auto-creates lead!",
        "hi": "🎙️ <b>वॉइस-टू-एक्शन:</b>\n  वॉइस नोट भेजें → ऑटो लीड बनें!",
    },
    "help_sales": {
        "en": (
            "📞 <b>Sales Cycle:</b>\n"
            "  /followup <i>id</i> — Log interaction\n"
            "  /convert <i>id</i> — Move to next stage\n"
            "  /policy <i>id</i> — Record sold policy\n"
            "  /scan — 📸 AI scan policy photo/PDF"
        ),
        "hi": (
            "📞 <b>सेल्स साइकल:</b>\n"
            "  /followup <i>id</i> — इंटरैक्शन लॉग करें\n"
            "  /convert <i>id</i> — अगले स्टेज में ले जाएं\n"
            "  /policy <i>id</i> — बेची गई पॉलिसी दर्ज करें\n"
            "  /scan — 📸 AI पॉलिसी फोटो/PDF स्कैन"
        ),
    },
    "help_claims": {
        "en": (
            "🏥 <b>Claims:</b>\n"
            "  /claim — New claim  |  /claims — All claims\n"
            "  /claimstatus <i>id</i> — Claim details"
        ),
        "hi": (
            "🏥 <b>क्लेम:</b>\n"
            "  /claim — नया क्लेम  |  /claims — सभी क्लेम\n"
            "  /claimstatus <i>id</i> — क्लेम विवरण"
        ),
    },
    "help_calc": {
        "en": "📊 <b>Calculators:</b>\n  /calc — Financial calculators",
        "hi": "📊 <b>कैलकुलेटर:</b>\n  /calc — वित्तीय कैलकुलेटर",
    },
    "help_wa_calc": {
        "en": "  /wacalc <i>id</i> — Send calc to client WhatsApp",
        "hi": "  /wacalc <i>id</i> — क्लाइंट WhatsApp पर कैल्क भेजें",
    },
    "help_wa_section": {
        "en": (
            "📱 <b>WhatsApp:</b>\n"
            "  /wa <i>id msg</i> — Message client\n"
            "  /wadash <i>id</i> — Send portfolio via WhatsApp"
        ),
        "hi": (
            "📱 <b>WhatsApp:</b>\n"
            "  /wa <i>id msg</i> — क्लाइंट को मैसेज\n"
            "  /wadash <i>id</i> — WhatsApp से पोर्टफ़ोलियो भेजें"
        ),
    },
    "help_reminders": {
        "en": (
            "🔄 <b>Reminders:</b>\n"
            "  /renewals — Upcoming renewals\n"
            "  /greet <i>id</i> — Send greeting"
        ),
        "hi": (
            "🔄 <b>रिमाइंडर:</b>\n"
            "  /renewals — आगामी रिन्यूअल\n"
            "  /greet <i>id</i> — अभिवादन भेजें"
        ),
    },
    "help_dashboard": {
        "en": "📈 /dashboard — Business dashboard",
        "hi": "📈 /dashboard — बिज़नेस डैशबोर्ड",
    },
    "help_ai_active": {
        "en": "🤖 /ai — AI Tools (scoring, pitch, insights)",
        "hi": "🤖 /ai — AI टूल्स (स्कोरिंग, पिच, इनसाइट्स)",
    },
    "help_ai_locked": {
        "en": "🤖 /ai — AI Tools 🔒 <i>(Team plan+)</i>",
        "hi": "🤖 /ai — AI टूल्स 🔒 <i>(Team प्लान+)</i>",
    },
    "help_plans": {
        "en": "💳 /plans — Subscription plans",
        "hi": "💳 /plans — सब्सक्रिप्शन प्लान",
    },
    "help_owner": {
        "en": (
            "👑 <b>Owner Commands:</b>\n"
            "  /team — Manage agents\n"
            "  /settings — Firm settings\n"
            "  /wasetup — WhatsApp integration\n"
            "  /createbot — Create your own bot"
        ),
        "hi": (
            "👑 <b>मालिक कमांड:</b>\n"
            "  /team — एजेंट प्रबंधन\n"
            "  /settings — फर्म सेटिंग्स\n"
            "  /wasetup — WhatsApp इंटीग्रेशन\n"
            "  /createbot — अपना बोट बनाएं"
        ),
    },
    "help_footer": {
        "en": (
            "⚙️ /editprofile — Edit profile\n"
            "  /editlead <i>id</i> — Edit lead\n"
            "  /lang — Language (EN/HI)\n\n"
            "🔊 /listenhelp — Audio help (voice notes)\n"
            "ℹ️ /help — This message"
        ),
        "hi": (
            "⚙️ /editprofile — प्रोफ़ाइल संपादित करें\n"
            "  /editlead <i>id</i> — लीड संपादित करें\n"
            "  /lang — भाषा (EN/HI)\n\n"
            "🔊 /listenhelp — ऑडियो हेल्प (वॉइस नोट)\n"
            "ℹ️ /help — यह संदेश"
        ),
    },
    "help_plan_role": {
        "en": "<i>Plan: {plan} | Role: {role}</i>",
        "hi": "<i>प्लान: {plan} | भूमिका: {role}</i>",
    },

    # ── Onboarding — welcome / identity ────────────────────────────────
    "bot_not_configured": {
        "en": "⚠️ This bot is not configured correctly.",
        "hi": "⚠️ यह बोट सही से कॉन्फ़िगर नहीं है।",
    },
    "invalid_signup_link": {
        "en": "⚠️ Invalid or expired signup link.\nPlease sign up again at sarathi-ai.com",
        "hi": "⚠️ अमान्य या एक्सपायर्ड साइनअप लिंक।\nकृपया sarathi-ai.com पर दोबारा साइनअप करें।",
    },
    "different_firm": {
        "en": "⚠️ You're registered with a different firm.\nEach agent can only be linked to one firm at a time.",
        "hi": "⚠️ आप एक अलग फर्म से रजिस्टर्ड हैं।\nएक एजेंट एक समय में केवल एक फर्म से जुड़ सकता है।",
    },
    "welcome_linked": {
        "en": "🎉 <b>Welcome, {name}!</b>\n\nYour Telegram is now linked to <b>{firm}</b>.\nYou're all set! 🚀",
        "hi": "🎉 <b>स्वागत है, {name}!</b>\n\nआपका Telegram <b>{firm}</b> से लिंक हो गया।\nआप तैयार हैं! 🚀",
    },
    "welcome_linked_setup_bot": {
        "en": "🎉 <b>Welcome, {name}!</b>\n\nYour Telegram is now linked to <b>{firm}</b>.\nYour account is ready! ✅\n\nNow let's connect your own CRM bot 👇",
        "hi": "🎉 <b>स्वागत है, {name}!</b>\n\nआपका Telegram <b>{firm}</b> से लिंक हो गया।\nअकाउंट तैयार! ✅\n\nअब अपना CRM बोट कनेक्ट करें 👇",
    },
    "resume_onboarding": {
        "en": "👋 Welcome back! Let's finish setting up your profile.\nWe left off at: <b>{step}</b>",
        "hi": "👋 वापस स्वागत है! प्रोफ़ाइल सेटअप पूरा करें।\nहम यहाँ रुके थे: <b>{step}</b>",
    },
    "welcome_master_bot": {
        "en": (
            "🙏 <b>Welcome to Sarathi-AI.com!</b>\n\n"
            "India's AI-Powered Business CRM — manage leads, clients,\n"
            "follow-ups & more from Telegram + Web.\n\n"
            "🛡️ <i>Data Security First. Human Trust Always.</i>\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>First, choose your preferred language:</b>"
        ),
        "hi": (
            "🙏 <b>सारथी-AI.com में आपका स्वागत है!</b>\n\n"
            "भारत का AI-पावर्ड बिज़नेस CRM — लीड, क्लाइंट,\n"
            "फ़ॉलो-अप सब Telegram + Web से।\n\n"
            "🛡️ <i>डेटा सुरक्षा पहले। विश्वास हमेशा।</i>\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>पहले अपनी पसंदीदा भाषा चुनें:</b>"
        ),
    },
    "welcome_back_setup_bot": {
        "en": (
            "👋 <b>Welcome back, {name}!</b>\n\n"
            "🏢 Firm: <b>{firm}</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ You haven't connected your own bot yet.\n\n"
            "This is the <b>Sarathi-AI.com master bot</b> — "
            "it's for registration and setup only.\n\n"
            "To use the <b>full CRM suite</b> (leads, pipeline, "
            "calculators, team management, etc.), you need "
            "your own bot.\n"
            "━━━━━━━━━━━━━━━━━━"
        ),
        "hi": (
            "👋 <b>वापस स्वागत है, {name}!</b>\n\n"
            "🏢 फर्म: <b>{firm}</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ आपने अभी तक अपना बोट कनेक्ट नहीं किया।\n\n"
            "यह <b>Sarathi-AI.com मास्टर बोट</b> है — "
            "यह केवल रजिस्ट्रेशन और सेटअप के लिए है।\n\n"
            "<b>पूरा CRM</b> (लीड, पाइपलाइन, "
            "कैलकुलेटर, टीम) के लिए "
            "अपना बोट कनेक्ट करें।\n"
            "━━━━━━━━━━━━━━━━━━"
        ),
    },
    "welcome_tenant_join": {
        "en": (
            "👋 <b>Welcome to {firm}!</b>\n\n"
            "To join this team, you need an <b>invite code</b> "
            "from the firm owner.\n\n"
            "Ask your team lead for the invite code and tap below:"
        ),
        "hi": (
            "👋 <b>{firm} में स्वागत है!</b>\n\n"
            "इस टीम में शामिल होने के लिए फर्म मालिक से "
            "<b>इनवाइट कोड</b> चाहिए।\n\n"
            "अपने टीम लीडर से कोड लें और नीचे टैप करें:"
        ),
    },
    "welcome_tenant_found": {
        "en": (
            "🎉 <b>Welcome to {firm}!</b>\n\n"
            "We found your registered profile:\n"
            "{profile}\n\n"
            "Is this you?"
        ),
        "hi": (
            "🎉 <b>{firm} में स्वागत है!</b>\n\n"
            "आपकी रजिस्टर्ड प्रोफ़ाइल:\n"
            "{profile}\n\n"
            "क्या यह आप हैं?"
        ),
    },
    "lang_set_en": {
        "en": "✅ Language: <b>English</b>\n\nNow let's get started:",
        "hi": "✅ Language: <b>English</b>\n\nNow let's get started:",
    },
    "lang_set_hi": {
        "en": "✅ भाषा: <b>हिन्दी</b>\n\nआइए शुरू करते हैं:",
        "hi": "✅ भाषा: <b>हिन्दी</b>\n\nआइए शुरू करते हैं:",
    },
    "account_exists": {
        "en": "❌ <b>Account Already Exists</b>\n\nYou already have a Sarathi-AI account linked to this Telegram.\nUse /help to see available commands.",
        "hi": "❌ <b>अकाउंट पहले से है</b>\n\nआपके Telegram से पहले से Sarathi-AI अकाउंट लिंक है।\n/help से कमांड देखें।",
    },
    "trial_already_used": {
        "en": "❌ <b>Trial Already Used</b>\n\nA free trial was already used from this Telegram.\nContact support@sarathi-ai.com for help.",
        "hi": "❌ <b>ट्रायल पहले ही इस्तेमाल हो चुका</b>\n\nइस Telegram से पहले ही फ्री ट्रायल ले लिया गया है।\nsupport@sarathi-ai.com पर संपर्क करें।",
    },
    "step_firm_name": {
        "en": "🏢 <b>Step 1 of 3 — Firm / Practice Name</b>\n\nWhat is the name of your business, firm, or practice?",
        "hi": "🏢 <b>स्टेप 1/3 — फर्म/प्रैक्टिस का नाम</b>\n\nआपकी फर्म/बिज़नेस का नाम क्या है?",
    },
    "step_your_name": {
        "en": "👤 <b>Step 1 of 3 — Your Name</b>\n\nWhat is your full name?",
        "hi": "👤 <b>स्टेप 1/3 — आपका नाम</b>\n\nआपका पूरा नाम क्या है?",
    },
    "step_join_team": {
        "en": "🔗 <b>Join a Team</b>\n\nEnter the <b>invite code</b> from your firm owner:",
        "hi": "🔗 <b>टीम से जुड़ें</b>\n\nफर्म मालिक से मिला <b>इनवाइट कोड</b> दर्ज करें:",
    },
    "identity_confirmed": {
        "en": "✅ <b>Identity Confirmed!</b>\n\nWelcome aboard, <b>{name}</b>!",
        "hi": "✅ <b>पहचान पुष्ट!</b>\n\nस्वागत है, <b>{name}</b>!",
    },
    "tap_to_start_msg": {
        "en": "👇 Tap a button below to get started!",
        "hi": "👇 शुरू करने के लिए नीचे बटन टैप करें!",
    },
    "something_wrong_retry": {
        "en": "⚠️ Something went wrong. Please type /start to retry.",
        "hi": "⚠️ कुछ गलत हुआ। /start करके दोबारा प्रयास करें।",
    },
    "invite_join_prompt": {
        "en": "👋 To join <b>{firm}</b> as an agent,\nenter the <b>invite code</b>:",
        "hi": "👋 <b>{firm}</b> में एजेंट के रूप में जुड़ने के लिए\n<b>इनवाइट कोड</b> दर्ज करें:",
    },
    "invite_code_invalid": {
        "en": "❌ Invalid or expired invite code.\nCheck with your firm owner and try again.",
        "hi": "❌ अमान्य या एक्सपायर्ड इनवाइट कोड।\nफर्म मालिक से चेक करें।",
    },
    "team_full_msg": {
        "en": "⚠️ <b>Team is full</b>\n\nYour firm's plan limit has been reached.\nAsk your firm owner to upgrade the plan.",
        "hi": "⚠️ <b>टीम भर गई है</b>\n\nफर्म की प्लान लिमिट पूरी हो गई।\nफर्म मालिक से प्लान अपग्रेड करवाएं।",
    },
    "step_your_name_2": {
        "en": "👤 <b>Step 2 of 3 — Your Name</b>\n\nEnter your <b>full name</b> (first name + last name):",
        "hi": "👤 <b>स्टेप 2/3 — आपका नाम</b>\n\n<b>पूरा नाम</b> दर्ज करें (पहला + अंतिम नाम):",
    },
    "enter_full_name": {
        "en": "✏️ Please enter your <b>full name</b> (first name + last name).\n\n",
        "hi": "✏️ कृपया <b>पूरा नाम</b> (पहला + अंतिम नाम) दर्ज करें।\n\n",
    },
    "ask_city_step": {
        "en": "📍 Almost done! What <b>city</b> are you based in?\n\n<i>(Type your city or /skip)</i>",
        "hi": "📍 लगभग हो गया! आप किस <b>शहर</b> में हैं?\n\n<i>(शहर का नाम टाइप करें या /skip)</i>",
    },
    "trial_info_msg": {
        "en": "🎉 <b>You're on a 14-day FREE trial!</b>\n\nIncludes:\n✅ Unlimited leads\n✅ All calculators\n✅ AI tools\n✅ WhatsApp sharing\n✅ Client reports\n\nUse /help to see all commands.",
        "hi": "🎉 <b>14 दिन का फ्री ट्रायल!</b>\n\nशामिल है:\n✅ अनलिमिटेड लीड\n✅ सभी कैलकुलेटर\n✅ AI टूल्स\n✅ WhatsApp शेयरिंग\n✅ क्लाइंट रिपोर्ट\n\n/help से सभी कमांड देखें।",
    },
    "connect_bot_warning": {
        "en": "⚠️ <b>IMPORTANT: Connect Your Own Bot</b>\n\nThis is the Sarathi-AI.com <b>master bot</b>.\nTo use all CRM features, connect your own Telegram bot.\n\nUse /createbot for step-by-step guide.",
        "hi": "⚠️ <b>ज़रूरी: अपना बोट कनेक्ट करें</b>\n\nयह Sarathi-AI.com का <b>मास्टर बोट</b> है।\nसभी CRM फ़ीचर्स के लिए अपना Telegram बोट कनेक्ट करें।\n\n/createbot से गाइड देखें।",
    },
    "bot_skip_later": {
        "en": "👍 No problem! You can connect your bot anytime from:\n• /createbot — Step-by-step guide\n• /settings → Bot Configuration",
        "hi": "👍 कोई बात नहीं! बोट कभी भी कनेक्ट कर सकते हैं:\n• /createbot — गाइड\n• /settings → बोट सेटिंग",
    },
    "bot_token_paste": {
        "en": "🤖 <b>Paste Your Bot Token</b>\n\nPaste the token you copied from BotFather:",
        "hi": "🤖 <b>बोट टोकन पेस्ट करें</b>\n\nBotFather से कॉपी किया गया टोकन पेस्ट करें:",
    },
    "bot_token_invalid_format": {
        "en": "❌ That doesn't look like a valid bot token.\n\nA valid token looks like:\n<code>123456789:ABCdefGHI-jklMNOpqrSTUvwx</code>\n\nPlease try again or /cancel.",
        "hi": "❌ यह सही बोट टोकन नहीं लग रहा।\n\nसही टोकन ऐसा दिखता है:\n<code>123456789:ABCdefGHI-jklMNOpqrSTUvwx</code>\n\nदोबारा करें या /cancel।",
    },
    "bot_token_invalid": {
        "en": "❌ This token is invalid or the bot doesn't exist.\nPlease check and try again.",
        "hi": "❌ यह टोकन अमान्य है या बोट मौजूद नहीं।\nकृपया चेक करके दोबारा करें।",
    },
    "bot_connected_success": {
        "en": "✅ <b>Bot Connected Successfully!</b>\n\n🤖 Bot: @{bot_username}\n\nYour CRM is now live! Use /help in your new bot.",
        "hi": "✅ <b>बोट कनेक्ट हो गया!</b>\n\n🤖 बोट: @{bot_username}\n\nआपका CRM अब लाइव है! अपने नए बोट में /help करें।",
    },
    "menu_while_adding": {
        "en": "⚠️ You tapped a menu button while adding a lead.\nPlease complete the current step or /cancel.",
        "hi": "⚠️ लीड जोड़ते समय मेन्यू बटन टैप किया।\nकृपया मौजूदा स्टेप पूरा करें या /cancel।",
    },
    "dob_future_err": {
        "en": "❌ DOB cannot be in the future. Try again (DD-MM-YYYY).",
        "hi": "❌ जन्मतिथि भविष्य में नहीं हो सकती। दोबारा करें (DD-MM-YYYY)।",
    },
    "anniversary_future_err": {
        "en": "❌ Anniversary cannot be in the future. Try again or /skip.",
        "hi": "❌ सालगिरह भविष्य में नहीं हो सकती। दोबारा करें या /skip।",
    },
    "followup_date_invalid": {
        "en": "❌ Invalid format. Use DD-MM-YYYY or /skip",
        "hi": "❌ गलत फ़ॉर्मैट। DD-MM-YYYY या /skip",
    },
    "detail_name": {"en": "👤 Name", "hi": "👤 नाम"},
    "detail_phone": {"en": "📱 Phone", "hi": "📱 फ़ोन"},
    "detail_whatsapp": {"en": "💬 WhatsApp", "hi": "💬 WhatsApp"},
    "detail_email": {"en": "📧 Email", "hi": "📧 ईमेल"},
    "detail_dob": {"en": "🎂 DOB", "hi": "🎂 जन्मतिथि"},
    "detail_anniversary": {"en": "💍 Anniversary", "hi": "💍 सालगिरह"},
    "detail_city": {"en": "📍 City", "hi": "📍 शहर"},
    "detail_need": {"en": "📋 Need", "hi": "📋 ज़रूरत"},
    "detail_stage": {"en": "📊 Stage", "hi": "📊 स्टेज"},
    "detail_added": {"en": "📅 Added", "hi": "📅 जोड़ा"},
    "detail_notes": {"en": "📝 Notes", "hi": "📝 नोट्स"},
    "detail_interactions": {"en": "🔄 Recent Interactions", "hi": "🔄 हाल की बातचीत"},
    "detail_no_interactions": {"en": "No interactions logged yet", "hi": "अभी तक कोई बातचीत दर्ज नहीं"},
    "detail_policies": {"en": "🛡️ Policies", "hi": "🛡️ पॉलिसी"},
    "detail_no_policies": {"en": "No policies yet", "hi": "अभी तक कोई पॉलिसी नहीं"},
    "detail_greetings": {"en": "💌 Greetings Sent", "hi": "💌 भेजी गई शुभकामनाएं"},
    "lead_detail_header": {"en": "📋 <b>Lead Detail:</b>", "hi": "📋 <b>लीड विवरण:</b>"},
    "greet_select_type": {
        "en": "💌 <b>Send Greeting to {name}</b>\nSelect type:",
        "hi": "💌 <b>{name} को शुभकामना भेजें</b>\nप्रकार चुनें:",
    },
    "greet_sending": {"en": "Sending greeting...", "hi": "शुभकामना भेज रहे हैं..."},
    "greet_sent": {
        "en": "✅ {gtype} greeting sent to {name}!",
        "hi": "✅ {name} को {gtype} शुभकामना भेजी!",
    },
    "greet_failed": {
        "en": "❌ Failed to send: {error}",
        "hi": "❌ भेजने में विफल: {error}",
    },
    "no_renewals": {
        "en": "✅ No renewals due in the next 60 days. All clear!",
        "hi": "✅ अगले 60 दिनों में कोई रिन्यूअल नहीं। सब ठीक!",
    },
    "settings_header": {"en": "⚙️ <b>Settings</b>", "hi": "⚙️ <b>सेटिंग्स</b>"},
    "select_language": {
        "en": "🌐 Select your preferred language:",
        "hi": "🌐 अपनी पसंदीदा भाषा चुनें:",
    },
    "send_profile_photo": {
        "en": "📸 <b>Send me your profile photo</b>\n\nSend a clear photo. It will appear on client reports.\nOr /cancel to go back.",
        "hi": "📸 <b>प्रोफ़ाइल फ़ोटो भेजें</b>\n\nएक साफ़ फ़ोटो भेजें। यह क्लाइंट रिपोर्ट पर दिखेगी।\nया /cancel।",
    },
    "wa_share_prompt": {
        "en": "📱 <b>Share on WhatsApp</b>\n\nEnter the client's phone number (10-digit):",
        "hi": "📱 <b>WhatsApp पर शेयर करें</b>\n\nक्लाइंट का फ़ोन नंबर दर्ज करें (10 अंक):",
    },
    "wa_invalid_phone": {
        "en": "❌ Invalid phone number. Please enter a 10-digit number.",
        "hi": "❌ अमान्य फ़ोन नंबर। कृपया 10 अंकों का नंबर दर्ज करें।",
    },
    "conv_in_progress": {
        "en": "⚠️ You're in the middle of a conversation.\n\nType /cancel to abort, or continue entering data.",
        "hi": "⚠️ आप बातचीत के बीच में हैं।\n\n/cancel से रद्द करें, या डेटा दर्ज करना जारी रखें।",
    },
    "only_text_now": {
        "en": "⚠️ I can only process <b>text messages</b> right now.\n\nPlease type your response or /cancel.",
        "hi": "⚠️ अभी केवल <b>टेक्स्ट संदेश</b> प्रोसेस हो सकते हैं।\n\nकृपया टाइप करें या /cancel।",
    },
    "conv_entering_data": {
        "en": "⚠️ You're in the middle of entering data.\nPlease complete the step or /cancel.",
        "hi": "⚠️ आप डेटा दर्ज कर रहे हैं।\nकृपया स्टेप पूरा करें या /cancel।",
    },
    "didnt_understand": {
        "en": "🤔 I didn't understand that.\nUse /help to see available commands.",
        "hi": "🤔 मैं समझ नहीं पाया।\n/help से उपलब्ध कमांड देखें।",
    },
    "register_first_start": {
        "en": "👋 Please register first — type /start",
        "hi": "👋 पहले रजिस्टर करें — /start टाइप करें",
    },
    "welcome_get_started": {
        "en": "👋 Welcome! Use /start to get started.",
        "hi": "👋 स्वागत है! /start से शुरू करें।",
    },
    "error_try_again": {
        "en": "⚠️ Something went wrong. Try again.",
        "hi": "⚠️ कुछ गलत हुआ। दोबारा कोशिश करें।",
    },
    "ai_tools_header": {
        "en": "🤖 <b>AI Sales Intelligence</b>\n\nPowered by Gemini AI. Choose a tool:",
        "hi": "🤖 <b>AI सेल्स इंटेलिजेंस</b>\n\nGemini AI द्वारा संचालित। टूल चुनें:",
    },
    "ai_no_leads": {
        "en": "📭 No leads yet. Add a lead first with ➕ Add Lead.",
        "hi": "📭 अभी कोई लीड नहीं। पहले ➕ लीड जोड़ें।",
    },
    "ai_thinking": {
        "en": "💬 <i>Thinking...</i>",
        "hi": "💬 <i>सोच रहा हूँ...</i>",
    },
    "claims_no_leads": {
        "en": "📭 No leads found. Add leads first with /addlead",
        "hi": "📭 कोई लीड नहीं मिली। /addlead से लीड जोड़ें।",
    },
    "claim_cancelled_msg": {
        "en": "🗑️ Claim cancelled.",
        "hi": "🗑️ क्लेम रद्द।",
    },
    "no_claims_msg": {
        "en": "📭 No claims found. Use /claim to start a new claim.",
        "hi": "📭 कोई क्लेम नहीं मिला। /claim से नया क्लेम शुरू करें।",
    },
    "agent_deactivated_msg": {
        "en": "❌ <b>{name}</b> has been deactivated.",
        "hi": "❌ <b>{name}</b> निष्क्रिय कर दिया गया।",
    },
    "agent_reactivated_msg": {
        "en": "✅ <b>{name}</b> has been reactivated.",
        "hi": "✅ <b>{name}</b> पुनः सक्रिय किया गया।",
    },
    "no_agents_to_transfer": {
        "en": "❌ No active agents to transfer to.",
        "hi": "❌ ट्रांसफर के लिए कोई सक्रिय एजेंट नहीं।",
    },
    "voice_processing_msg": {
        "en": "🎙️ Processing your voice note...",
        "hi": "🎙️ आपकी वॉइस नोट प्रोसेस हो रही है...",
    },
    "voice_no_data": {
        "en": "⚠️ No voice data found. Please try again.",
        "hi": "⚠️ वॉइस डेटा नहीं मिला। दोबारा कोशिश करें।",
    },
    "voice_discarded_msg": {
        "en": "🗑️ Voice note discarded.",
        "hi": "🗑️ वॉइस नोट हटाई गई।",
    },
    "payment_register_first": {
        "en": "⚠️ Please /start first to register.",
        "hi": "⚠️ पहले /start से रजिस्टर करें।",
    },

    # ── Voice-First CRM ────────────────────────────────────────────────────
    "voice_wait_slow": {
        "en": "🎙️ Processing your voice note... This might take a few seconds on slow network. Please wait! ⏳",
        "hi": "🎙️ वॉइस नोट प्रोसेस हो रही है... धीमे नेटवर्क पर थोड़ा समय लग सकता है। कृपया रुकें! ⏳",
    },
    "voice_network_retry": {
        "en": "⚠️ Network hiccup! Retrying your voice note... Hold on! 🔄",
        "hi": "⚠️ नेटवर्क में दिक्कत! दोबारा कोशिश कर रहे हैं... रुकिए! 🔄",
    },
    "voice_failed_retry": {
        "en": "❌ Couldn't process your voice note. Please try again — send a new voice message. 🎤",
        "hi": "❌ वॉइस नोट प्रोसेस नहीं हो पाई। दोबारा भेजें — एक नया वॉइस मैसेज रिकॉर्ड करें। 🎤",
    },
    "voice_meeting_logged": {
        "en": ("✅ <b>Meeting Logged!</b>\n\n"
               "👤 Lead: <b>{name}</b> (#{lead_id})\n"
               "📝 {summary}\n"
               "{followup}"
               "\n🎙️ <i>Logged via voice note</i>"),
        "hi": ("✅ <b>मीटिंग लॉग हो गई!</b>\n\n"
               "👤 लीड: <b>{name}</b> (#{lead_id})\n"
               "📝 {summary}\n"
               "{followup}"
               "\n🎙️ <i>वॉइस नोट से लॉग किया</i>"),
    },
    "voice_stage_updated": {
        "en": ("✅ <b>Stage Updated!</b>\n\n"
               "👤 Lead: <b>{name}</b> (#{lead_id})\n"
               "📊 Stage: {old_stage} → <b>{new_stage}</b>\n"
               "\n🎙️ <i>Updated via voice note</i>"),
        "hi": ("✅ <b>स्टेज अपडेट!</b>\n\n"
               "👤 लीड: <b>{name}</b> (#{lead_id})\n"
               "📊 स्टेज: {old_stage} → <b>{new_stage}</b>\n"
               "\n🎙️ <i>वॉइस नोट से अपडेट किया</i>"),
    },
    "voice_reminder_set": {
        "en": ("✅ <b>Reminder Set!</b>\n\n"
               "⏰ {message}\n"
               "📅 Due: <b>{due_date}</b>\n"
               "{lead_info}"
               "\n🎙️ <i>Created via voice note</i>"),
        "hi": ("✅ <b>रिमाइंडर सेट!</b>\n\n"
               "⏰ {message}\n"
               "📅 तिथि: <b>{due_date}</b>\n"
               "{lead_info}"
               "\n🎙️ <i>वॉइस नोट से बनाया</i>"),
    },
    "voice_note_added": {
        "en": ("✅ <b>Note Added!</b>\n\n"
               "👤 Lead: <b>{name}</b> (#{lead_id})\n"
               "📋 {note}\n"
               "\n🎙️ <i>Added via voice note</i>"),
        "hi": ("✅ <b>नोट जोड़ दिया!</b>\n\n"
               "👤 लीड: <b>{name}</b> (#{lead_id})\n"
               "📋 {note}\n"
               "\n🎙️ <i>वॉइस नोट से जोड़ा</i>"),
    },
    "voice_lead_not_found": {
        "en": "⚠️ Couldn't find the lead you mentioned. Please check the name and try again. 🔍",
        "hi": "⚠️ आपने जिस लीड का नाम लिया वो नहीं मिली। नाम जांचें और दोबारा कोशिश करें। 🔍",
    },
    "voice_abuse_warning": {
        "en": ("⚠️ <b>Content Warning</b>\n\n"
               "Your message contains inappropriate language. "
               "This is warning <b>{count}/5</b>.\n\n"
               "⛔ 3 warnings → 24-hour block\n"
               "⛔ 5 warnings → permanent block\n\n"
               "Please keep communication professional and respectful."),
        "hi": ("⚠️ <b>चेतावनी</b>\n\n"
               "आपके मैसेज में अनुचित भाषा है। "
               "यह चेतावनी <b>{count}/5</b> है।\n\n"
               "⛔ 3 चेतावनी → 24 घंटे ब्लॉक\n"
               "⛔ 5 चेतावनी → स्थायी ब्लॉक\n\n"
               "कृपया सम्मानजनक भाषा का उपयोग करें।"),
    },
    "voice_blocked": {
        "en": "🚫 Your account is temporarily blocked due to repeated content violations. Please contact support.",
        "hi": "🚫 बार-बार अनुचित भाषा के कारण आपका अकाउंट अस्थायी रूप से ब्लॉक है। सपोर्ट से संपर्क करें।",
    },

    # ── Just Talk Mode ────────────────────────────────────────────────
    "just_talk_thinking": {
        "en": "🧠 Understanding your message...",
        "hi": "🧠 आपका मैसेज समझ रहा हूँ...",
    },
    "just_talk_welcome": {
        "en": ("💬 <b>Just Talk Mode</b> — I'm listening!\n\n"
               "Type anything naturally and I'll understand:\n\n"
               "📝 <i>\"Naya client aaya Ramesh, health insurance chahiye\"</i>\n"
               "→ I'll create a lead\n\n"
               "📞 <i>\"Aaj Priya se mila, retirement plan samjhaya\"</i>\n"
               "→ I'll log the meeting\n\n"
               "⏰ <i>\"Kal Sharma ji ko call karna hai\"</i>\n"
               "→ I'll set a reminder\n\n"
               "❓ <i>\"Term insurance ka claim process kya hai?\"</i>\n"
               "→ I'll answer your question\n\n"
               "🎙️ Or just send a <b>voice note</b> — I understand that too!"),
        "hi": ("💬 <b>बस बोलो मोड</b> — मैं सुन रहा हूँ!\n\n"
               "कुछ भी टाइप करें, मैं समझ जाऊंगा:\n\n"
               "📝 <i>\"नया क्लाइंट आया रमेश, हेल्थ इंश्योरेंस चाहिए\"</i>\n"
               "→ लीड बना दूंगा\n\n"
               "📞 <i>\"आज प्रिया से मिला, रिटायरमेंट प्लान समझाया\"</i>\n"
               "→ मीटिंग लॉग कर दूंगा\n\n"
               "⏰ <i>\"कल शर्मा जी को कॉल करना है\"</i>\n"
               "→ रिमाइंडर सेट कर दूंगा\n\n"
               "❓ <i>\"टर्म इंश्योरेंस का क्लेम प्रोसेस क्या है?\"</i>\n"
               "→ जवाब दे दूंगा\n\n"
               "🎙️ या बस <b>वॉइस नोट</b> भेजो — वो भी समझता हूँ!"),
    },

    # ── Stuck Detection & Guidance ────────────────────────────────────
    "stuck_help": {
        "en": ("🤔 <b>Looks like you might need help!</b>\n\n"
               "Here's what you can do:\n\n"
               "📝 <b>Add a lead</b> — tap ➕ Add Lead\n"
               "📊 <b>View pipeline</b> — tap 📊 Pipeline\n"
               "📋 <b>See your leads</b> — tap 📋 My Leads\n"
               "🧮 <b>Run a calculator</b> — tap 🧮 Calculator\n"
               "💬 <b>Just type naturally</b> — e.g. \"New client Ramesh, wants health insurance\"\n"
               "🎙️ <b>Send a voice note</b> — I'll transcribe & act on it\n\n"
               "👇 Use the menu buttons below, or just type what you need!"),
        "hi": ("🤔 <b>लगता है आपको मदद चाहिए!</b>\n\n"
               "आप ये कर सकते हैं:\n\n"
               "📝 <b>लीड जोड़ें</b> — ➕ लीड जोड़ें बटन दबाएं\n"
               "📊 <b>पाइपलाइन देखें</b> — 📊 पाइपलाइन बटन दबाएं\n"
               "📋 <b>अपनी लीड्स देखें</b> — 📋 मेरी लीड्स दबाएं\n"
               "🧮 <b>कैलकुलेटर</b> — 🧮 कैलकुलेटर बटन दबाएं\n"
               "💬 <b>बस टाइप करें</b> — \"नया क्लाइंट रमेश, हेल्थ इंश्योरेंस चाहिए\"\n"
               "🎙️ <b>वॉइस नोट भेजें</b> — मैं सुनकर काम करूंगा\n\n"
               "👇 नीचे मेनू बटन इस्तेमाल करें, या जो चाहिए बस लिखें!"),
    },

    # ── AI Quota ──────────────────────────────────────────────────────
    "ai_quota_reached": {
        "en": ("⚠️ <b>Daily AI limit reached</b>\n\n"
               "You've used <b>{used}/{limit}</b> AI calls today.\n"
               "Your quota resets at midnight.\n\n"
               "💡 You can still use the menu buttons for all CRM features — "
               "leads, pipeline, follow-ups, calculators all work without AI."),
        "hi": ("⚠️ <b>आज का AI लिमिट पूरा हो गया</b>\n\n"
               "आज <b>{used}/{limit}</b> AI कॉल्स इस्तेमाल हो चुकी हैं।\n"
               "कोटा रात 12 बजे रीसेट होगा।\n\n"
               "💡 आप मेनू बटन से सभी CRM फीचर्स इस्तेमाल कर सकते हैं — "
               "लीड्स, पाइपलाइन, फॉलो-अप, कैलकुलेटर सब बिना AI के चलेंगे।"),
    },

    # ── Admin Test Mode ───────────────────────────────────────────────
    "admin_test_mode_info": {
        "en": ("👁 <b>Preview Agent View</b>\n\n"
               "As the firm owner, you already have <b>full access</b> — "
               "everything an agent can do, you can do too.\n\n"
               "To test the <b>agent experience</b> realistically:\n\n"
               "1️⃣ Create a second Telegram account (second SIM/phone)\n"
               "2️⃣ Generate an <b>Invite Code</b> from Settings → Team\n"
               "3️⃣ Open your bot on that second account\n"
               "4️⃣ Press /start → 'I have an Invite Code'\n"
               "5️⃣ Enter the invite code\n\n"
               "This gives you a true agent-level view:\n"
               "✅ Agent menu (no team management)\n"
               "✅ Lead access scoped to that agent\n"
               "✅ Same voice/text AI features\n\n"
               "<i>💡 Your owner account stays safe — this is a separate test account.</i>"),
        "hi": ("👁 <b>एजेंट व्यू प्रीव्यू</b>\n\n"
               "फर्म ओनर होने पर आपके पास <b>पूरा एक्सेस</b> है — "
               "जो एजेंट कर सकता है, वो सब आप भी कर सकते हैं।\n\n"
               "<b>एजेंट अनुभव</b> टेस्ट करने के लिए:\n\n"
               "1️⃣ दूसरा Telegram अकाउंट बनाएं (दूसरा SIM/फोन)\n"
               "2️⃣ Settings → Team से <b>Invite Code</b> बनाएं\n"
               "3️⃣ दूसरे अकाउंट पर अपना बोट खोलें\n"
               "4️⃣ /start दबाएं → 'I have an Invite Code'\n"
               "5️⃣ कोड डालें\n\n"
               "इससे आपको असली एजेंट-लेवल व्यू मिलेगा:\n"
               "✅ एजेंट मेनू (टीम मैनेजमेंट नहीं)\n"
               "✅ उस एजेंट की लीड्स\n"
               "✅ वही वॉइस/टेक्स्ट AI फीचर्स\n\n"
               "<i>💡 आपका ओनर अकाउंट सुरक्षित रहेगा — यह अलग टेस्ट अकाउंट है।</i>"),
    },
    "owner_only_feature": {
        "en": "ℹ️ This feature is available for firm owners only.",
        "hi": "ℹ️ यह फीचर केवल फर्म ओनर के लिए उपलब्ध है।",
    },

    # ── Task Management ──────────────────────────────────────────────────
    "nav_tasks": {
        "en": "Tasks",
        "hi": "टास्क",
    },
    "bnav_tasks": {
        "en": "Tasks",
        "hi": "टास्क",
    },
    "tt_tasks": {
        "en": "Tasks",
        "hi": "टास्क",
    },
    "task_today": {
        "en": "Today",
        "hi": "आज",
    },
    "task_yesterday": {
        "en": "Yesterday",
        "hi": "बीता कल",
    },
    "task_tomorrow": {
        "en": "Tomorrow",
        "hi": "कल",
    },
    "task_overdue": {
        "en": "Overdue",
        "hi": "ओवरड्यू",
    },
    "task_all": {
        "en": "All",
        "hi": "सभी",
    },
    "task_pending": {
        "en": "Pending",
        "hi": "पेंडिंग",
    },
    "task_done": {
        "en": "Done",
        "hi": "पूरा",
    },
    "task_status_all": {
        "en": "All Status",
        "hi": "सभी स्टेटस",
    },
    "task_empty": {
        "en": "No tasks found for this filter.",
        "hi": "इस फ़िल्टर में कोई टास्क नहीं मिला।",
    },
    "task_mark_done_confirm": {
        "en": "Mark this task as done?",
        "hi": "इस टास्क को पूरा मार्क करें?",
    },
    "task_snooze_prompt": {
        "en": "Snooze to:\n1 = +1 hour\n2 = Tomorrow\nOr enter date (YYYY-MM-DD)",
        "hi": "स्नूज़ करें:\n1 = +1 घंटा\n2 = कल\nया तारीख दें (YYYY-MM-DD)",
    },
    "task_summary_total": {
        "en": "Total: {count}",
        "hi": "कुल: {count}",
    },
    "task_summary_pending": {
        "en": "Pending: {count}",
        "hi": "पेंडिंग: {count}",
    },
    "task_summary_overdue": {
        "en": "Overdue: {count}",
        "hi": "ओवरड्यू: {count}",
    },
    "task_summary_done": {
        "en": "Done: {count}",
        "hi": "पूरा: {count}",
    },
}


# ── Public API ────────────────────────────────────────────────────────────────

def t(lang: str, key: str, **kwargs) -> str:
    """
    Get a translated string.

    Falls back: requested lang → English → raw key.
    Substitutes {placeholders} from kwargs.
    """
    entry = _S.get(key)
    if not entry:
        return f"[{key}]"
    text = entry.get(lang) or entry.get("en", f"[{key}]")
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass  # gracefully skip missing placeholders
    return text


def available_languages() -> dict:
    """Return dict of language code → display name."""
    return dict(LANGUAGES)
