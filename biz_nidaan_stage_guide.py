"""
NidaanPartner — WHAT EACH BUCKET IS, in words a person can act on.

Staff came from a system where work lived in folders. They know "which folder is this in, and
what do I do with it". They do not know "stage", "blocker" or "flag", and they should not have to.

So every bucket explains itself in four short lines:
    what   — what this bucket actually is
    do     — what you do while a case sits here
    done   — how you know it is finished and can move on
    watch  — the thing that usually goes wrong here

Written for someone who is good at claims work and not at software, in both languages, because
the person doing document collection at 10am is not the person who reads English release notes.

Content only — no logic, no queries. Kept apart from the state machine so the wording can be
edited by anyone without going near the rules that move cases.
"""
from __future__ import annotations

STAGE_GUIDE = {
    "intake": {
        "en": {"what": "A new case has arrived and we are checking the basics.",
               "do": "Make sure we can reach this person: name, mobile, email, insurer, claim number and the rejection date.",
               "done": "Every detail is filled in, and the phone and email have been checked.",
               "watch": "A missing email is the one that hurts later - every insurer and Ombudsman letter goes there."},
        "hi": {"what": "नया केस आया है और हम बुनियादी जानकारी जाँच रहे हैं।",
               "do": "पक्का करें कि हम इस व्यक्ति तक पहुँच सकें: नाम, मोबाइल, ईमेल, बीमा कंपनी, क्लेम नंबर और रिजेक्शन की तारीख़।",
               "done": "सारी जानकारी भरी है, और फ़ोन व ईमेल जाँचे जा चुके हैं।",
               "watch": "ईमेल का न होना बाद में सबसे भारी पड़ता है - बीमा कंपनी और लोकपाल की हर चिट्ठी वहीं आती है।"},
    },
    "review": {
        "en": {"what": "An expert is deciding whether this claim can be fought.",
               "do": "Health cases go to a doctor, everything else to an advocate. Record the verdict on the case.",
               "done": "The verdict is on file - we can fight it, or honestly we cannot.",
               "watch": "A case sitting here more than a few days is a person waiting for an answer about their money."},
        "hi": {"what": "विशेषज्ञ तय कर रहे हैं कि यह क्लेम लड़ा जा सकता है या नहीं।",
               "do": "हेल्थ केस डॉक्टर के पास, बाक़ी सब वकील के पास। नतीजा केस पर दर्ज करें।",
               "done": "नतीजा दर्ज है - या तो हम लड़ सकते हैं, या ईमानदारी से नहीं लड़ सकते।",
               "watch": "यहाँ कुछ दिन से ज़्यादा अटका केस मतलब कोई व्यक्ति अपने पैसे का जवाब इंतज़ार कर रहा है।"},
    },
    "conversion": {
        "en": {"what": "We told them we can fight it. Now the work has to be paid for and started.",
               "do": "Explain what we found, what happens next, and what it costs. Then follow up until they decide.",
               "done": "The fee is settled and the case moves on - or they have clearly said no.",
               "watch": "This is where most cases go quiet. A phone call from whoever brought them works better than another message."},
        "hi": {"what": "हमने कह दिया कि केस लड़ा जा सकता है। अब काम की फ़ीस आनी है और शुरुआत होनी है।",
               "do": "बताइए हमें क्या मिला, आगे क्या होगा, और ख़र्च कितना है। फिर फ़ैसले तक फ़ॉलो-अप करें।",
               "done": "फ़ीस तय हो गई और केस आगे बढ़ा - या उन्होंने साफ़ मना कर दिया।",
               "watch": "यहीं सबसे ज़्यादा केस चुप हो जाते हैं। जो व्यक्ति केस लाया है उसका फ़ोन दूसरे मैसेज से ज़्यादा काम करता है।"},
    },
    "consolidation": {
        "en": {"what": "Getting permission and a working email before we speak to anyone on their behalf.",
               "do": "Take the signed authorisation, get the claim email created, and set the exact case category.",
               "done": "Authorisation signed, claim email working, category chosen.",
               "watch": "The category decides the whole document list. Getting it wrong means collecting the wrong papers for weeks."},
        "hi": {"what": "उनकी ओर से बात करने से पहले अनुमति और एक चालू ईमेल लेना।",
               "do": "हस्ताक्षरित अधिकार-पत्र लें, क्लेम का ईमेल बनवाएँ, और केस की सही श्रेणी चुनें।",
               "done": "अधिकार-पत्र साइन, क्लेम ईमेल चालू, श्रेणी चुनी हुई।",
               "watch": "श्रेणी से ही पूरी दस्तावेज़ सूची तय होती है। ग़लत हुई तो हफ़्तों ग़लत काग़ज़ इकट्ठे होंगे।"},
    },
    "documentation": {
        "en": {"what": "Collecting every paper this kind of case needs.",
               "do": "Ask for one document at a time. Check each one is the right paper and readable before accepting it.",
               "done": "Every required document is in, and the ones that must be originals have arrived by post.",
               "watch": "Hospitals refusing indoor case papers is common - we have a letter for that, send it instead of waiting."},
        "hi": {"what": "इस तरह के केस के लिए ज़रूरी हर काग़ज़ इकट्ठा करना।",
               "do": "एक बार में एक दस्तावेज़ माँगें। स्वीकार करने से पहले जाँचें कि सही काग़ज़ है और पढ़ा जा सकता है।",
               "done": "हर ज़रूरी दस्तावेज़ आ गया, और जो असली चाहिए वे डाक से पहुँच गए।",
               "watch": "अस्पताल का इनडोर केस पेपर देने से मना करना आम है - इसके लिए हमारा पत्र है, इंतज़ार की जगह उसे भेजें।"},
    },
    "drafting": {
        "en": {"what": "Writing the case up and getting it approved inside the office.",
               "do": "Prepare the gist, then the letter to the insurer. Send it for approval before anything goes out.",
               "done": "The draft is approved by the doctor or advocate who owns this type of case.",
               "watch": "Nothing leaves this office unapproved. A weak letter is harder to undo than a slow one."},
        "hi": {"what": "केस को लिखकर तैयार करना और दफ़्तर के अंदर मंज़ूरी लेना।",
               "do": "पहले सार, फिर बीमा कंपनी को पत्र। बाहर भेजने से पहले मंज़ूरी के लिए भेजें।",
               "done": "जिस विशेषज्ञ का यह विषय है, उन्होंने ड्राफ़्ट मंज़ूर कर दिया।",
               "watch": "बिना मंज़ूरी कुछ भी बाहर नहीं जाता। कमज़ोर पत्र सुधारना देर से भेजने से ज़्यादा मुश्किल है।"},
    },
    "representation": {
        "en": {"what": "The letter is with the insurer and the 30-day clock is running.",
               "do": "Record their acknowledgement. Send the reminders on day 10, 20 and 30 if they stay silent.",
               "done": "They settle it, or the 30 days run out and we escalate.",
               "watch": "If they raise a query the ball is back with US - answer it before their deadline, not ours."},
        "hi": {"what": "पत्र बीमा कंपनी के पास है और 30 दिन की गिनती चल रही है।",
               "do": "उनकी पावती दर्ज करें। चुप रहें तो 10वें, 20वें और 30वें दिन रिमाइंडर भेजें।",
               "done": "वे निपटारा कर दें, या 30 दिन पूरे हों और हम आगे बढ़ाएँ।",
               "watch": "अगर वे सवाल उठाएँ तो गेंद हमारे पाले में है - उनकी तारीख़ से पहले जवाब दें।"},
    },
    "escalation": {
        "en": {"what": "The insurer said no, or said nothing. Taking it above them.",
               "do": "Go to the grievance officer, and prepare the Ombudsman filing if that also fails.",
               "done": "Either they settle, or the Ombudsman complaint is registered.",
               "watch": "The one-year window from the rejection date is the hard limit. Check it before anything else."},
        "hi": {"what": "बीमा कंपनी ने मना कर दिया, या कुछ नहीं कहा। अब ऊपर ले जाना है।",
               "do": "शिकायत अधिकारी के पास जाएँ, और वहाँ भी न बने तो लोकपाल की तैयारी करें।",
               "done": "या तो वे निपटा दें, या लोकपाल में शिकायत दर्ज हो जाए।",
               "watch": "रिजेक्शन की तारीख़ से एक साल की सीमा सख़्त है। सबसे पहले वही जाँचें।"},
    },
    "lokpal": {
        "en": {"what": "The case is with the Insurance Ombudsman.",
               "do": "Keep the filing number on the case, answer every letter the same day, and prepare for the hearing.",
               "done": "An award or a dismissal has been received and recorded.",
               "watch": "Their deadlines are not negotiable. A missed reply can end the complaint."},
        "hi": {"what": "केस बीमा लोकपाल के पास है।",
               "do": "फ़ाइलिंग नंबर केस पर रखें, हर चिट्ठी का जवाब उसी दिन दें, और सुनवाई की तैयारी करें।",
               "done": "फ़ैसला या ख़ारिज होने की सूचना मिल गई और दर्ज हो गई।",
               "watch": "उनकी तारीख़ों में छूट नहीं मिलती। एक जवाब छूटा तो शिकायत ख़त्म हो सकती है।"},
    },
    "outcome": {
        "en": {"what": "A decision has come. Recording what it means for everyone.",
               "do": "Put the result and the awarded amount on the case, and tell the complainant yourself.",
               "done": "The result is recorded and the customer has been told by a person.",
               "watch": "Good news or bad, a person delivers it - never an automatic message."},
        "hi": {"what": "फ़ैसला आ गया है। अब दर्ज करना है कि इसका सबके लिए क्या मतलब है।",
               "do": "नतीजा और मिली राशि केस पर दर्ज करें, और शिकायतकर्ता को ख़ुद बताएँ।",
               "done": "नतीजा दर्ज है और ग्राहक को किसी व्यक्ति ने बता दिया है।",
               "watch": "ख़बर अच्छी हो या बुरी, इंसान बताता है - अपने आप जाने वाला मैसेज नहीं।"},
    },
    "settlement": {
        "en": {"what": "The money has to reach the customer, then our fee has to reach us.",
               "do": "Confirm the customer received their money, raise our fee, and pay whoever brought the case.",
               "done": "Customer paid, our fee received, every share settled.",
               "watch": "Once they have their money, chasing our fee gets harder every week. Start on day one."},
        "hi": {"what": "पैसा ग्राहक तक पहुँचना है, फिर हमारी फ़ीस हम तक।",
               "do": "पुष्टि करें कि ग्राहक को पैसा मिला, हमारी फ़ीस का बिल बनाएँ, और केस लाने वाले को हिस्सा दें।",
               "done": "ग्राहक को भुगतान, हमारी फ़ीस प्राप्त, हर हिस्सा चुकता।",
               "watch": "पैसा मिलने के बाद हर हफ़्ते फ़ीस वसूलना मुश्किल होता जाता है। पहले दिन से शुरू करें।"},
    },
    "closed": {
        "en": {"what": "Nothing is outstanding on this case.",
               "do": "Nothing. It stays on file so a returning customer is recognised.",
               "done": "-",
               "watch": "If a closed case gets a new message, it comes back to life - do not start a second one."},
        "hi": {"what": "इस केस पर कुछ बाक़ी नहीं है।",
               "do": "कुछ नहीं। रिकॉर्ड में रहता है ताकि लौटने वाला ग्राहक पहचाना जाए।",
               "done": "-",
               "watch": "बंद केस पर नया मैसेज आए तो वही फिर से चालू होता है - दूसरा केस न बनाएँ।"},
    },
}

# The two conversation duties are not case stages, but a person rostered onto them needs the
# same "what am I meant to do here" answer.
CHANNEL_GUIDE = {
    "support": {
        "en": {"what": "The chat box on our website, where visitors and customers write in.",
               "do": "Answer what the AI could not. Anything about a specific case needs the person verified first.",
               "done": "Nothing is waiting for a reply.",
               "watch": "One visitor is one conversation - do not start a new thread for someone who has written before."},
        "hi": {"what": "हमारी वेबसाइट का चैट बॉक्स, जहाँ आने वाले और ग्राहक लिखते हैं।",
               "do": "जो AI न कर सका उसका जवाब दें। किसी केस की बात के लिए पहले पहचान की पुष्टि ज़रूरी है।",
               "done": "कोई जवाब का इंतज़ार नहीं कर रहा।",
               "watch": "एक व्यक्ति = एक बातचीत - पहले लिख चुके व्यक्ति के लिए नया थ्रेड न खोलें।"},
    },
    "whatsapp": {
        "en": {"what": "Our WhatsApp number, where complainants send documents and ask questions.",
               "do": "Take over a chat when the AI cannot help. Check the badge before typing anything about a case.",
               "done": "Nothing is waiting for a reply and no chat is left half-answered.",
               "watch": "If a chat shows Not verified, share nothing about their claim until they send the code."},
        "hi": {"what": "हमारा WhatsApp नंबर, जहाँ शिकायतकर्ता दस्तावेज़ भेजते और सवाल पूछते हैं।",
               "do": "जहाँ AI मदद न कर सके, चैट अपने हाथ में लें। केस की बात लिखने से पहले बैज देखें।",
               "done": "कोई जवाब का इंतज़ार नहीं और कोई चैट अधूरी नहीं।",
               "watch": "चैट पर 'Not verified' दिखे तो कोड आने तक उनके क्लेम की कोई बात साझा न करें।"},
    },
}

# What a bucket is called on screen. Short, and the same word in the menu, the board and the rota.
DUTY_LABEL = {
    "support":        {"en": "Support chat",     "hi": "सपोर्ट चैट",        "icon": "🎧"},
    "whatsapp":       {"en": "WhatsApp inbox",   "hi": "WhatsApp इनबॉक्स",  "icon": "💬"},
    "intake":         {"en": "Intake",           "hi": "नया केस",           "icon": "📥"},
    "review":         {"en": "Review",           "hi": "समीक्षा",           "icon": "🔍"},
    "conversion":     {"en": "Conversion",       "hi": "फ़ीस और शुरुआत",     "icon": "💰"},
    "consolidation":  {"en": "Consolidation",    "hi": "अनुमति व ईमेल",      "icon": "📝"},
    "documentation":  {"en": "Documents",        "hi": "दस्तावेज़",          "icon": "📄"},
    "drafting":       {"en": "Drafting",         "hi": "ड्राफ़्टिंग",         "icon": "✍️"},
    "representation": {"en": "With the insurer", "hi": "बीमा कंपनी के पास",  "icon": "📮"},
    "escalation":     {"en": "Escalation",       "hi": "एस्केलेशन",         "icon": "⚖️"},
    "lokpal":         {"en": "Ombudsman",        "hi": "लोकपाल",            "icon": "🏛️"},
    "outcome":        {"en": "Outcome",          "hi": "नतीजा",             "icon": "🎯"},
    "settlement":     {"en": "Settlement",       "hi": "भुगतान",            "icon": "🏦"},
    "closed":         {"en": "Closed",           "hi": "बंद",               "icon": "✅"},
}


def guide(key: str, lang: str = "en") -> dict:
    """The four lines for one bucket. Falls back to English, then to empty."""
    g = STAGE_GUIDE.get(key) or CHANNEL_GUIDE.get(key) or {}
    return g.get(lang if lang in ("en", "hi") else "en") or g.get("en") or {}


def label(key: str, lang: str = "en") -> dict:
    """{icon, name} for one bucket, in the requested language."""
    d = DUTY_LABEL.get(key) or {}
    return {"icon": d.get("icon", "•"),
            "name": d.get(lang if lang in ("en", "hi") else "en") or d.get("en") or key}
