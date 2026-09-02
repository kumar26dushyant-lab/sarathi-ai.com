"""
NidaanPartner claimant-WhatsApp MESSAGE COMPOSER — the bilingual copy for every doc-collection
event. Pure functions (no I/O), so they're testable without the live number and drop straight
into the Phase 1 orchestrator once the Meta number is connected.

Languages: 'hinglish' (default) | 'hi' | 'en'. Hinglish is Roman-script Hindi — the most
comfortable register for most Tier II/III claimants on WhatsApp.

Every composer takes a `ctx` dict and returns a ready-to-send string. Keep them warm, human,
short, and specific — this is the "feels like a person is managing it" layer.
"""
from __future__ import annotations

from typing import Optional

BRAND = "NidaanPartner"
_SIGN = {"hinglish": f"\n\n— Team {BRAND}", "hi": f"\n\n— {BRAND} टीम", "en": f"\n\n— Team {BRAND}"}


def _lang(l: Optional[str]) -> str:
    l = (l or "hinglish").strip().lower()
    return l if l in ("hinglish", "hi", "en") else "hinglish"


def _reg(ctx: dict) -> str:
    """Registration number shown to the claimant — e.g. NP-77."""
    return ctx.get("reg_no") or (f"NP-{ctx.get('claim_id')}" if ctx.get("claim_id") else "")


def welcome(ctx: dict, lang: str = "hinglish") -> str:
    l = _lang(lang); name = ctx.get("name") or ""
    hi_ = {
        "hinglish": (f"Namaste {name} 🙏\n{BRAND} me aapka swagat hai. Hum aapke insurance claim me "
                     f"aapki madad karenge. Yahi number save kar lein — saare updates isi par milenge."),
        "hi": (f"नमस्ते {name} 🙏\n{BRAND} में आपका स्वागत है। हम आपके इंश्योरेंस क्लेम में आपकी मदद करेंगे। "
               f"कृपया यही नंबर सेव कर लें — सभी अपडेट यहीं मिलेंगे।"),
        "en": (f"Hello {name} 🙏\nWelcome to {BRAND}. We'll help you with your insurance claim. "
               f"Please save this number — all your updates come here."),
    }[l]
    return hi_ + _SIGN[l]


def claim_registered(ctx: dict, lang: str = "hinglish") -> str:
    """To the claimant. (Subscriber/branch/staff get their own dispatch via the notify engine.)"""
    l = _lang(lang); reg = _reg(ctx); insured = ctx.get("insured_name") or ""
    hi_ = {
        "hinglish": (f"✅ Aapka claim register ho gaya hai.\nRegistration No: *{reg}*\n"
                     f"Insured: {insured}\nHamari team ise review kar rahi hai — hum aapko har step par "
                     f"update karenge. Koi bhi sawaal ho to yahin reply karein."),
        "hi": (f"✅ आपका क्लेम रजिस्टर हो गया है।\nरजिस्ट्रेशन नं.: *{reg}*\nबीमाधारक: {insured}\n"
               f"हमारी टीम इसकी समीक्षा कर रही है — हम आपको हर चरण पर अपडेट करेंगे। कोई सवाल हो तो यहीं जवाब दें।"),
        "en": (f"✅ Your claim is registered.\nRegistration No: *{reg}*\nInsured: {insured}\n"
               f"Our team is reviewing it — we'll update you at every step. Reply here with any question."),
    }[l]
    return hi_ + _SIGN[l]


def thank_you_payment(ctx: dict, lang: str = "hinglish") -> str:
    l = _lang(lang); reg = _reg(ctx); amt = ctx.get("amount")
    amt_s = f" ₹{amt}" if amt else ""
    hi_ = {
        "hinglish": (f"Dhanyavaad 🙏 Aapka payment{amt_s} mil gaya hai (claim *{reg}*). "
                     f"Ab hamari legal team aapke claim par kaam shuru kar rahi hai. Aap nishchint rahein — "
                     f"hum poori tarah aapke saath hain."),
        "hi": (f"धन्यवाद 🙏 आपका भुगतान{amt_s} प्राप्त हो गया है (क्लेम *{reg}*)। अब हमारी लीगल टीम आपके क्लेम पर "
               f"काम शुरू कर रही है। आप निश्चिंत रहें — हम पूरी तरह आपके साथ हैं।"),
        "en": (f"Thank you 🙏 We've received your payment{amt_s} (claim *{reg}*). Our legal team is now "
               f"starting work on your claim. Please be assured — we're fully with you."),
    }[l]
    return hi_ + _SIGN[l]


def intro_value(ctx: dict, lang: str = "hinglish") -> str:
    """Warm, emotionally-connecting intro after welcome — what NidaanPartner does + a gentle ask.
    Built to build trust and convert. Kept human, not salesy."""
    l = _lang(lang); name = ctx.get("name") or ""
    hi_ = {
        "hinglish": (f"{name}, hum samajhte hain — jab mehnat ki kamai se liya insurance claim reject ya "
                     f"kam ho jaata hai, to bahut takleef hoti hai. 😔\n\n*NidaanPartner* aapke jaise logon "
                     f"ke liye hi bana hai — hamari legal team aapke reject/underpaid claim ko ladti hai, "
                     f"documents se lekar company se baat tak, sab hum sambhalte hain.\n\nAap bas itna "
                     f"bataiye — aapka claim kis cheez ka hai aur kya problem aayi? Hum aage ka raasta "
                     f"batayenge. Rejection ka matlab ant nahi — aapke claim me abhi dum baaki hai. 💪"),
        "hi": (f"{name}, हम समझते हैं — मेहनत की कमाई से लिया इंश्योरेंस क्लेम जब रिजेक्ट या कम हो जाता है, "
               f"तो बहुत तकलीफ़ होती है। 😔\n\n*NidaanPartner* आप जैसे लोगों के लिए ही बना है — हमारी लीगल टीम "
               f"आपके रिजेक्ट/कम भुगतान वाले क्लेम को लड़ती है; दस्तावेज़ से लेकर कंपनी से बात तक सब हम संभालते हैं।\n\n"
               f"आप बस इतना बताइए — आपका क्लेम किस चीज़ का है और क्या दिक्कत आई? रिजेक्शन का मतलब अंत नहीं — "
               f"आपके क्लेम में अभी दम बाकी है। 💪"),
        "en": (f"{name}, we understand — when a hard-earned insurance claim is rejected or underpaid, it "
               f"really hurts. 😔\n\n*NidaanPartner* exists for people like you — our legal team fights your "
               f"rejected/underpaid claim end to end, from documents to dealing with the company.\n\nJust "
               f"tell us — what is your claim for, and what went wrong? We'll show you the way forward. A "
               f"rejection isn't the end — your claim still has a fighting chance. 💪"),
    }[l]
    return hi_ + _SIGN[l]


def payment_failed(ctx: dict, lang: str = "hinglish") -> str:
    l = _lang(lang)
    hi_ = {
        "hinglish": ("Aapka payment poora nahi ho paaya — aapse koi paisa nahi kata. 🙏 Koi baat nahi, "
                     "dobara try karein ya humein yahin bataayein, hum madad kar denge."),
        "hi": ("आपका भुगतान पूरा नहीं हो पाया — आपसे कोई पैसा नहीं कटा। 🙏 कोई बात नहीं, दोबारा कोशिश करें या "
               "हमें यहीं बताएं, हम मदद कर देंगे।"),
        "en": ("Your payment didn't go through — you were NOT charged. 🙏 No worries, please try again or "
               "tell us here and we'll help."),
    }[l]
    return hi_ + _SIGN[l]


def doc_reminder(ctx: dict, lang: str = "hinglish") -> str:
    """Ask for ONE specific next document, with progress."""
    l = _lang(lang); doc = ctx.get("doc_label") or ""; done = ctx.get("done", 0); total = ctx.get("total", 0)
    prog = f" ({done}/{total})" if total else ""
    hi_ = {
        "hinglish": (f"Aapke claim ko aage badhane ke liye humein *{doc}* chahiye{prog}.\n"
                     f"Kripya iski saaf photo ya PDF yahin bhej dein. Bas ek document ek baar — main "
                     f"aapko batata rahunga aage kya chahiye. 🙏"),
        "hi": (f"आपके क्लेम को आगे बढ़ाने के लिए हमें *{doc}* चाहिए{prog}।\nकृपया इसकी साफ़ फोटो या PDF यहीं भेजें। "
               f"एक बार में एक दस्तावेज़ — मैं आपको बताता रहूँगा आगे क्या चाहिए। 🙏"),
        "en": (f"To move your claim forward we need *{doc}*{prog}.\nPlease send a clear photo or PDF here. "
               f"One document at a time — I'll guide you on what's next. 🙏"),
    }[l]
    return hi_ + _SIGN[l]


def doc_received_ok(ctx: dict, lang: str = "hinglish") -> str:
    l = _lang(lang); doc = ctx.get("doc_label") or ""; nxt = ctx.get("next_label")
    nxt_line = {
        "hinglish": (f"\nAb kripya *{nxt}* bhejein." if nxt else "\nAur zaroorat padi to main bataunga."),
        "hi": (f"\nअब कृपया *{nxt}* भेजें।" if nxt else "\nआगे ज़रूरत होगी तो मैं बताऊँगा।"),
        "en": (f"\nNow please send *{nxt}*." if nxt else "\nI'll let you know if anything else is needed."),
    }[l]
    head = {"hinglish": f"✅ *{doc}* mil gaya, dhanyavaad!",
            "hi": f"✅ *{doc}* मिल गया, धन्यवाद!",
            "en": f"✅ Got *{doc}*, thank you!"}[l]
    return head + nxt_line + _SIGN[l]


def doc_wrong(ctx: dict, lang: str = "hinglish") -> str:
    """The claimant sent the wrong document (asked for X, sent Y)."""
    l = _lang(lang); want = ctx.get("doc_label") or ""; got = ctx.get("looks_like") or ""
    got_s = {"hinglish": f" (yeh {got} lag raha hai)", "hi": f" (यह {got} लग रहा है)", "en": f" (this looks like {got})"}[l] if got else ""
    hi_ = {
        "hinglish": (f"Yeh document{got_s} sahi nahi lag raha. Humein *{want}* chahiye. "
                     f"Kripya sahi document ki saaf photo bhejein. 🙏"),
        "hi": (f"यह दस्तावेज़{got_s} सही नहीं लग रहा। हमें *{want}* चाहिए। कृपया सही दस्तावेज़ की साफ़ फोटो भेजें। 🙏"),
        "en": (f"This document{got_s} doesn't look right. We need *{want}*. Please send a clear photo of the correct one. 🙏"),
    }[l]
    return hi_ + _SIGN[l]


def doc_quality(ctx: dict, lang: str = "hinglish") -> str:
    """The document is the right one but unreadable (blurry/cropped/dark)."""
    l = _lang(lang); doc = ctx.get("doc_label") or ""; reason = ctx.get("reason") or ""
    r = {"hinglish": f" ({reason})", "hi": f" ({reason})", "en": f" ({reason})"}[l] if reason else ""
    hi_ = {
        "hinglish": (f"*{doc}* thodi saaf nahi aayi{r}. Kripya achhi roshni me, poora page frame me "
                     f"lekar dobara photo bhejein — taaki hum ise sahi se padh sakein. 🙏"),
        "hi": (f"*{doc}* ठीक से साफ़ नहीं आई{r}। कृपया अच्छी रोशनी में, पूरा पेज फ्रेम में लेकर दोबारा फोटो भेजें — "
               f"ताकि हम इसे सही से पढ़ सकें। 🙏"),
        "en": (f"*{doc}* didn't come through clearly{r}. Please retake it in good light with the full page "
               f"in frame, so we can read it properly. 🙏"),
    }[l]
    return hi_ + _SIGN[l]


def docs_complete(ctx: dict, lang: str = "hinglish") -> str:
    l = _lang(lang); reg = _reg(ctx)
    hi_ = {
        "hinglish": (f"🎉 Bahut khoob! Aapke claim *{reg}* ke saare documents mil gaye hain. "
                     f"Ab hamari legal team ispar kaam karegi aur aapko aage update milega. Dhanyavaad 🙏"),
        "hi": (f"🎉 बहुत बढ़िया! आपके क्लेम *{reg}* के सभी दस्तावेज़ मिल गए हैं। अब हमारी लीगल टीम इस पर काम करेगी "
               f"और आपको आगे अपडेट मिलेगा। धन्यवाद 🙏"),
        "en": (f"🎉 Wonderful! We've received all documents for your claim *{reg}*. Our legal team will now "
               f"work on it and keep you updated. Thank you 🙏"),
    }[l]
    return hi_ + _SIGN[l]


# Dispatch table so the orchestrator can call compose(kind, lang, ctx) generically.
_COMPOSERS = {
    "welcome": welcome, "intro_value": intro_value, "claim_registered": claim_registered,
    "thank_you_payment": thank_you_payment, "payment_failed": payment_failed,
    "doc_reminder": doc_reminder, "doc_received_ok": doc_received_ok, "doc_wrong": doc_wrong,
    "doc_quality": doc_quality, "docs_complete": docs_complete,
}


def compose(kind: str, lang: str, ctx: dict) -> str:
    fn = _COMPOSERS.get(kind)
    return fn(ctx or {}, lang) if fn else ""
