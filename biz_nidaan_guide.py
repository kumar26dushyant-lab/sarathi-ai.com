"""
NidaanPartner — single source of truth for the self-onboarding user guides.

One place holds the step-by-step content for every dashboard context. BOTH the in-app
voice/readable guide widget (via GET /nidaan/api/guide) AND the support chatbot (via
kb_text()) read from here — so a change here updates the guide and the bot together.

Contexts:
  subscriber — paid-plan advisor (claims included in the plan; no ₹499 per review)
  review     — one-time ₹499 review customer (retail / new)
  branch     — affiliate city branch portal
  staff      — Nidaan ops staff portal

Each step is {hi:{t,b}, en:{t,b}}. The subscriber greeting uses "{plan}" — the widget
substitutes the account's plan name client-side.
"""

GUIDE_CONTENT = {
    "subscriber": {
        "title": {"hi": "आपका गाइड", "en": "Your Guide"},
        "greeting": {
            "hi": "नमस्ते! यह आपका Nidaan डैशबोर्ड है। आपके पास सक्रिय {plan} प्लान है। मैं बताऊँगा कि इसका पूरा फ़ायदा कैसे उठाएँ — क्लेम भेजने से लेकर अपने मुफ़्त CRM तक।",
            "en": "Hello! This is your Nidaan dashboard. You have an active {plan} plan. Let me show you how to make the most of it — from submitting claims to your free CRM.",
        },
        "steps": [
            {"hi": {"t": "आपके प्लान में क्लेम शामिल हैं", "b": "आपके {plan} प्लान में हर महीने तय संख्या में क्लेम समीक्षा शामिल हैं। हर क्लेम पर अलग से ₹499 देने की ज़रूरत नहीं — बस क्लेम भेजते जाएँ।"},
             "en": {"t": "Your plan includes claim reviews", "b": "Your {plan} plan includes a set number of claim reviews every month. You do NOT pay ₹499 per review — just keep submitting claims."}},
            {"hi": {"t": "नया क्लेम भेजें", "b": "रिजेक्ट या कम भुगतान वाले क्लेम की जानकारी भरकर भेजें। हमारी कानूनी टीम उसकी समीक्षा करेगी।"},
             "en": {"t": "Submit a new claim", "b": "Fill in the details of a rejected or underpaid claim and submit it. Our legal team will review it."}},
            {"hi": {"t": "ज़रूरी दस्तावेज़ अपलोड करें", "b": "पॉलिसी और रिजेक्शन लेटर जैसे दस्तावेज़ लगाएँ, ताकि समीक्षा सही और तेज़ हो।"},
             "en": {"t": "Upload documents", "b": "Attach documents like the policy and rejection letter so the review is accurate and fast."}},
            {"hi": {"t": "क्लेम की स्थिति देखें", "b": "क्लेम सेक्शन में हर क्लेम की स्थिति और अगला कदम दिखता है।"},
             "en": {"t": "Track claim status", "b": "The Claims section shows each claim's status and the next step."}},
            {"hi": {"t": "समीक्षा का नतीजा पढ़ें", "b": "समीक्षा पूरी होने पर पता चलेगा कि क्लेम लड़ने लायक है या नहीं, और आगे क्या करें।"},
             "en": {"t": "Read the review findings", "b": "Once the review is done, you'll see whether the claim is worth fighting and what to do next."}},
            {"hi": {"t": "मुफ़्त Sarathi-AI CRM का इस्तेमाल करें", "b": "आपके प्लान के साथ Sarathi-AI.com CRM भी मुफ़्त मिलता है — अपने लीड्स, फॉलो-अप, रिन्यूअल और क्लाइंट्स को सिर्फ़ वॉइस नोट से मैनेज करें। इससे आपका पूरा बिज़नेस आसान हो जाता है।"},
             "en": {"t": "Use your free Sarathi-AI CRM", "b": "Your plan also includes the Sarathi-AI.com CRM free — manage your leads, follow-ups, renewals and clients with just voice notes. It makes running your whole business effortless."}},
            {"hi": {"t": "Nidaan के आधिकारिक नंबर सेव करें", "b": "हमारे आधिकारिक WhatsApp नंबर अपने फ़ोन में सेव करें, ताकि हर अपडेट समय पर मिले।"},
             "en": {"t": "Save Nidaan's official numbers", "b": "Save our official WhatsApp numbers in your phone so you get every update on time."}},
            {"hi": {"t": "प्रोफ़ाइल और सेटिंग्स", "b": "प्रोफ़ाइल में अपनी जानकारी अपडेट करें; सेटिंग्स में भाषा और अन्य विकल्प बदलें।"},
             "en": {"t": "Profile and settings", "b": "Update your details in Profile; change the language and other options in Settings."}},
            {"hi": {"t": "मदद चाहिए? हमसे बात करें", "b": "कोई सवाल हो तो चैट या सहायता से पूछें। हम मदद के लिए यहाँ हैं।"},
             "en": {"t": "Need help? Talk to us", "b": "For any question, use chat or support. We're here to help."}},
        ],
    },
    "review": {
        "title": {"hi": "आपका गाइड", "en": "Your Guide"},
        "greeting": {
            "hi": "नमस्ते! यह आपका Nidaan डैशबोर्ड है। यहाँ आप अपने रिजेक्ट या कम भुगतान वाले बीमा क्लेम की विशेषज्ञ समीक्षा करा सकते हैं। आइए शुरू करें।",
            "en": "Hello! This is your Nidaan dashboard. Here you can get an expert review of your rejected or underpaid insurance claim. Let's begin.",
        },
        "steps": [
            {"hi": {"t": "अपना क्लेम समीक्षा के लिए भेजें", "b": "क्लेम समीक्षा शुरू करें पर जाएँ और अपने रिजेक्ट या कम भुगतान वाले क्लेम की जानकारी भरें।"},
             "en": {"t": "Send your claim for review", "b": "Open Raise a Claim Review and fill in the details of your rejected or underpaid claim."}},
            {"hi": {"t": "ज़रूरी दस्तावेज़ अपलोड करें", "b": "पॉलिसी और रिजेक्शन लेटर जैसे दस्तावेज़ अपलोड करें।"},
             "en": {"t": "Upload your documents", "b": "Attach documents like your policy and the rejection letter."}},
            {"hi": {"t": "₹499 समीक्षा शुल्क का भुगतान करें", "b": "एक बार की समीक्षा के लिए ₹499 भरें (₹10 लाख से ऊपर के क्लेम पर ₹2000)। भुगतान के बाद समीक्षा शुरू हो जाती है।"},
             "en": {"t": "Pay the ₹499 review fee", "b": "Pay ₹499 for a one-time review (₹2000 if the disputed amount is above ₹10 lakh). The review begins once paid."}},
            {"hi": {"t": "क्लेम की स्थिति देखें", "b": "क्लेम सेक्शन में अपने क्लेम की स्थिति देखें।"},
             "en": {"t": "Track your claim status", "b": "See your claim's status in the Claims section."}},
            {"hi": {"t": "समीक्षा का नतीजा पढ़ें", "b": "समीक्षा पूरी होने पर बताया जाएगा कि क्लेम लड़ने लायक है या नहीं, और आगे क्या करें।"},
             "en": {"t": "Read the review findings", "b": "Once done, you'll learn whether the claim is worth fighting and what to do next."}},
            {"hi": {"t": "बार-बार क्लेम भेजते हैं? प्लान लें और CRM मुफ़्त पाएँ", "b": "अगर आप एडवाइज़र हैं और कई क्लेम भेजते हैं, तो सदस्यता प्लान लें — हर बार ₹499 देने से सस्ता, और साथ में Sarathi-AI.com CRM मुफ़्त मिलता है जिससे अपना पूरा बिज़नेस वॉइस से चलाएँ।"},
             "en": {"t": "Sending many claims? Take a plan, get the CRM free", "b": "If you're an advisor sending many claims, take a subscription plan — cheaper than ₹499 each time, and it includes the Sarathi-AI.com CRM free to run your whole business by voice."}},
            {"hi": {"t": "मदद चाहिए? हमसे बात करें", "b": "कोई सवाल हो तो चैट या सहायता से पूछें।"},
             "en": {"t": "Need help? Talk to us", "b": "For any question, use chat or support."}},
        ],
    },
    "branch": {
        "title": {"hi": "ब्रांच गाइड", "en": "Branch Guide"},
        "greeting": {
            "hi": "नमस्ते! यह आपका Nidaan ब्रांच डैशबोर्ड है। यहाँ से आप ग्राहकों के क्लेम दर्ज कर सकते हैं, एडवाइज़र जोड़ सकते हैं और अपनी कमाई देख सकते हैं। आइए समझते हैं।",
            "en": "Hello! This is your Nidaan branch dashboard. From here you can file customers' claims, bring in advisors, and see your earnings. Let me walk you through it.",
        },
        "steps": [
            {"hi": {"t": "ग्राहक के लिए क्लेम दर्ज करें", "b": "किसी वॉक-इन ग्राहक का रिजेक्ट या कम भुगतान वाला क्लेम यहाँ दर्ज करें। समीक्षा मुफ़्त है — शुल्क तभी लगता है जब केस Level-2 पर जाए।"},
             "en": {"t": "File a claim for a customer", "b": "Enter a walk-in customer's rejected or underpaid claim here. The review is free — a fee applies only if the case goes to Level-2."}},
            {"hi": {"t": "ज़रूरी दस्तावेज़ अपलोड करें", "b": "पॉलिसी और रिजेक्शन लेटर लगाएँ ताकि समीक्षा सही और तेज़ हो।"},
             "en": {"t": "Upload documents", "b": "Attach the policy and rejection letter so the review is accurate and fast."}},
            {"hi": {"t": "अपने दर्ज क्लेम और उनकी स्थिति देखें", "b": "आपने जो क्लेम दर्ज किए हैं, उनकी स्थिति और अगला कदम यहीं ट्रैक करें।"},
             "en": {"t": "Track your filed claims", "b": "Track the status and next step of the claims you've filed, right here."}},
            {"hi": {"t": "एडवाइज़र जोड़ें — अपना रेफ़रल लिंक शेयर करें", "b": "अपना रेफ़रल लिंक एडवाइज़र्स को भेजें। जब वे आपके लिंक से जुड़ते हैं और प्लान लेते हैं, तो आपको कमीशन मिलता है।"},
             "en": {"t": "Bring in advisors — share your referral link", "b": "Send your referral link to advisors. When they join through your link and take a plan, you earn commission."}},
            {"hi": {"t": "मुफ़्त Sarathi-AI CRM की पिच करें", "b": "जब आप किसी एडवाइज़र को Nidaan समझाएँ, यह ज़रूर बताएँ कि उन्हें मुफ़्त Sarathi-AI.com CRM भी मिलता है — जिससे वे अपने लीड्स, फॉलो-अप और क्लाइंट्स सिर्फ़ वॉइस से मैनेज करें। इससे ज़्यादा एडवाइज़र जुड़ेंगे, और आगे उन्हें Sarathi-AI के प्रीमियम AI फ़ीचर्स भी बेच पाएँगे।"},
             "en": {"t": "Pitch the free Sarathi-AI CRM", "b": "When you explain Nidaan to an advisor, always mention they also get the Sarathi-AI.com CRM free — to manage their leads, follow-ups and clients by voice. More advisors join, and later we can sell them Sarathi-AI's premium AI features too."}},
            {"hi": {"t": "अपनी कमाई और रिपोर्ट देखें", "b": "आपके जोड़े गए सब्सक्राइबर, दर्ज किए क्लेम और कमीशन का पूरा हिसाब यहाँ दिखता है।"},
             "en": {"t": "See your earnings and report", "b": "Your referred subscribers, filed claims and commission are all shown here."}},
            {"hi": {"t": "मदद चाहिए? हमसे बात करें", "b": "कोई भी सवाल हो तो सहायता से पूछें। हम आपकी मदद के लिए यहाँ हैं।"},
             "en": {"t": "Need help? Talk to us", "b": "For any question, use support. We're here to help you."}},
        ],
    },
    "staff": {
        "title": {"hi": "स्टाफ़ गाइड", "en": "Staff Guide"},
        "greeting": {
            "hi": "नमस्ते! यह आपका Nidaan ऑप्स डैशबोर्ड है। यहाँ से आप क्लेम, टास्क, ग्राहक और अपना खुद का बिज़नेस — सब संभाल सकते हैं। आइए मुख्य चीज़ें देखें।",
            "en": "Hello! This is your Nidaan ops dashboard. From here you handle claims, tasks, customers and your own business. Let me show you the main things.",
        },
        "steps": [
            {"hi": {"t": "ओवरव्यू से दिन शुरू करें", "b": "Overview में आपके पेंडिंग रिव्यू, टास्क और इस हफ़्ते के फॉलो-अप एक जगह दिखते हैं — यहीं से प्राथमिकता तय करें।"},
             "en": {"t": "Start your day at Overview", "b": "Overview shows your pending reviews, tasks and this week's follow-ups in one place — prioritise from here."}},
            {"hi": {"t": "क्लेम मैनेज करें", "b": "All Claims में किसी क्लेम को खोलें, टीम मेंबर को असाइन करें, स्थिति अपडेट करें और समीक्षा के नतीजे (findings) दर्ज करें। भुगतान वाले क्लेम पहले करें।"},
             "en": {"t": "Manage claims", "b": "In All Claims, open a claim, assign it to a team member, update its status, and deliver the review findings. Work paid claims first."}},
            {"hi": {"t": "₹499 रिव्यू पूरे करें", "b": "Pending Reviews में भुगतान किए गए ₹499 रिव्यू दिखते हैं — इनकी findings समय पर दें। (सभी भुगतान वाले रिव्यू अब All Claims और Search में भी मिलते हैं।)"},
             "en": {"t": "Complete ₹499 reviews", "b": "Pending Reviews lists the paid ₹499 reviews — deliver their findings on time. (Every paid review now also appears in All Claims + Search.)"}},
            {"hi": {"t": "टास्क और फॉलो-अप", "b": "अपने टास्क और फॉलो-अप ट्रैक करें और समय पर पूरे करें, ताकि कोई ग्राहक छूट न जाए।"},
             "en": {"t": "Tasks and follow-ups", "b": "Track and complete your tasks and follow-ups on time so no customer slips through."}},
            {"hi": {"t": "अकाउंट्स और भुगतान", "b": "Accounts में भुगतान का निशान देखें — 🟡 भुगतान बाकी / 🔴 ऑटो-पे फेल। ऑफ़लाइन/QR भुगतान के लिए 💰 Mark-paid (सुपर-एडमिन)। यह भी दिखता है कि ग्राहक को किसने रेफ़र किया।"},
             "en": {"t": "Accounts and payments", "b": "In Accounts see the payment flag — 🟡 pending / 🔴 auto-pay failed. Use 💰 Mark-paid for offline/QR payments (super-admin). You can also see who referred each customer."}},
            {"hi": {"t": "सपोर्ट चैट का जवाब दें", "b": "Support में ग्राहकों की चैट का जवाब दें। (लाइट मोड में मैसेज अब साफ़ पढ़े जा सकते हैं।)"},
             "en": {"t": "Reply to support chats", "b": "Answer customer chats in Support. (Messages are now clearly readable in Light mode.)"}},
            {"hi": {"t": "अपना बिज़नेस (My Business)", "b": "अपने रेफ़रल कोड से सब्सक्राइबर और ₹499 ग्राहक जोड़ें, खुद क्लेम दर्ज करें, और कमीशन कमाएँ। यहाँ आपके रेफ़र किए सब्सक्राइबर की सूची भी दिखती है।"},
             "en": {"t": "Your Business (My Business)", "b": "Use your referral code to bring in subscribers and ₹499 customers, raise claims yourself, and earn commission. Your referred subscribers are listed here too."}},
            {"hi": {"t": "ब्रांच मैनेज करें (सुपर-एडमिन)", "b": "ब्रांच बनाएँ और मैनेज करें। ब्रांच बनाते ही उन्हें अपने-आप एक-क्लिक लॉगिन लिंक ईमेल हो जाता है।"},
             "en": {"t": "Manage branches (super-admin)", "b": "Create and manage branches. Creating one auto-emails the branch a one-click login link."}},
            {"hi": {"t": "मदद चाहिए?", "b": "कोई सवाल हो तो ऑफ़िस के IT SPOC से पूछें।"},
             "en": {"t": "Need help?", "b": "For any question, reach out to the office IT SPOC."}},
        ],
    },
}


def get_context(ctx: str) -> dict:
    """Return the guide content for a context (falls back to subscriber)."""
    return GUIDE_CONTENT.get(ctx) or GUIDE_CONTENT["subscriber"]


def kb_text(lang: str = "en") -> str:
    """Flatten the guides into a compact HOW-TO block for the support chatbot's knowledge
    base, so 'how do I…' product questions answer from the same source as the in-app guides."""
    lang = "hi" if lang == "hi" else "en"
    labels = {"subscriber": ("Subscriber (paid plan)", "सब्सक्राइबर (प्लान)"),
              "review": ("One-time ₹499 review customer", "एक-बार ₹499 रिव्यू ग्राहक"),
              "branch": ("Branch portal", "ब्रांच पोर्टल"),
              "staff": ("Ops staff portal", "ऑप्स स्टाफ़ पोर्टल")}
    out = []
    for ctx, data in GUIDE_CONTENT.items():
        head = labels.get(ctx, (ctx, ctx))[1 if lang == "hi" else 0]
        lines = []
        for st in data["steps"]:
            seg = st[lang]
            lines.append(f"- {seg['t']}: {seg['b']}")
        out.append(f"## {head}\n" + "\n".join(lines))
    return "\n\n".join(out)
