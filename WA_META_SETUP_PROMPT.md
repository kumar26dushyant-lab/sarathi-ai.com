# Meta WhatsApp Template Setup — Handoff Prompt

> Paste everything below the line into your Claude extension (the one with browser/Meta access).
> It sets up 6 message templates on the NidaanPartner WhatsApp Business Account in Meta.

---

## TASK: Create 6 WhatsApp message templates in Meta Business Manager

You are helping set up WhatsApp message templates for the **NidaanPartner** WhatsApp Business Account (WABA). Create each template below in **Meta Business Manager → WhatsApp Manager → Message templates → Create template**. Add the English version first, then add the **Hindi** language variant under the SAME template name.

**Account details**
- Business: NidaanPartner (insurance-claim legal support)
- WABA display number: +91 91836 86384
- WABA ID: 1695397392252786
- Phone Number ID: 1251678818039212

**Rules for every template**
- Use the exact **template name** given (lowercase + underscores).
- Use the exact **category** given (UTILITY or MARKETING). Category affects approval + pricing — do not change it.
- Variables are positional: `{{1}}`, `{{2}}`, `{{3}}`. Provide the **sample values** listed (Meta requires samples to approve).
- Body text is given verbatim for English and Hindi. Keep the emoji and the `— NidaanPartner` sign-off.
- No header/footer/buttons needed unless noted. Language codes: English = `en`, Hindi = `hi`.
- After submitting, report back each template's **name + approval status**.

---

### 1. Template `np_claim_registered` — UTILITY

**English (en)** — samples: {{1}}=Rajesh, {{2}}=NP-0093, {{3}}=Suresh Kumar
```
Namaste {{1}} 🙏

Your claim has been registered with NidaanPartner (Ref #{{2}}). Our team is now reviewing the details for {{3}}.

We will guide you at every step. You can reply to this chat any time with questions or documents.

— NidaanPartner
```

**Hindi (hi)** — samples: {{1}}=Rajesh, {{2}}=NP-0093, {{3}}=Suresh Kumar
```
नमस्ते {{1}} 🙏

आपका क्लेम NidaanPartner में दर्ज हो गया है (Ref #{{2}})। हमारी टीम अब {{3}} के लिए विवरण की समीक्षा कर रही है।

हम हर कदम पर आपका मार्गदर्शन करेंगे। किसी भी सवाल या दस्तावेज़ के लिए आप इसी चैट पर जवाब दे सकते हैं।

— NidaanPartner
```

---

### 2. Template `np_welcome` — UTILITY

**English (en)** — samples: {{1}}=Rajesh
```
Namaste {{1}} 🙏

This is the official WhatsApp of NidaanPartner — your support partner for rejected or disputed insurance claims. Please save this number so our updates always reach you safely.

We're here to help. Reply here any time.

— NidaanPartner
```

**Hindi (hi)** — samples: {{1}}=Rajesh
```
नमस्ते {{1}} 🙏

यह NidaanPartner का आधिकारिक WhatsApp है — अस्वीकृत या विवादित इंश्योरेंस क्लेम में आपका सहायता-साथी। कृपया यह नंबर सेव कर लें ताकि हमारे अपडेट आप तक सुरक्षित पहुँचें।

हम आपकी मदद के लिए हैं। कभी भी यहाँ जवाब दें।

— NidaanPartner
```

---

### 3. Template `np_intro_value` — MARKETING

**English (en)** — samples: {{1}}=Rajesh
```
{{1}}, a rejected insurance claim is not the end. 💪

When a claim you paid for honestly gets rejected, it feels unfair — and most people give up because the process feels too complex. NidaanPartner stands with people like you: we review your case, tell you the real way forward, and fight for what is rightfully yours.

Reply YES and we'll show you your next step. Reply STOP to opt out.

— NidaanPartner
```

**Hindi (hi)** — samples: {{1}}=Rajesh
```
{{1}}, इंश्योरेंस क्लेम रिजेक्ट होना अंत नहीं है। 💪

जब मेहनत की कमाई से लिया गया क्लेम रिजेक्ट होता है, तो यह अन्याय जैसा लगता है — और प्रक्रिया जटिल लगने से ज़्यादातर लोग हार मान लेते हैं। NidaanPartner आप जैसे लोगों के साथ खड़ा है: हम आपका केस देखते हैं, आगे का सही रास्ता बताते हैं, और आपके हक़ के लिए लड़ते हैं।

आगे का कदम जानने के लिए YES लिखें। ऑप्ट-आउट के लिए STOP लिखें।

— NidaanPartner
```

---

### 4. Template `np_payment_thanks` — UTILITY

**English (en)** — samples: {{1}}=Rajesh, {{2}}=499, {{3}}=NP-0093
```
Thank you {{1}}! ✅

Your payment of ₹{{2}} is confirmed (Ref #{{3}}). Your review has started — we'll keep you updated here and on your dashboard.

— NidaanPartner
```

**Hindi (hi)** — samples: {{1}}=Rajesh, {{2}}=499, {{3}}=NP-0093
```
धन्यवाद {{1}}! ✅

आपका ₹{{2}} का भुगतान मिल गया (Ref #{{3}})। आपकी समीक्षा शुरू हो गई है — हम आपको यहीं और आपके डैशबोर्ड पर अपडेट देते रहेंगे।

— NidaanPartner
```

---

### 5. Template `np_payment_failed` — UTILITY

**English (en)** — samples: {{1}}=Rajesh
```
{{1}}, your payment did not go through — and no money was deducted from you. ✅

You can safely try again from your dashboard whenever you're ready. If any amount was debited, it will auto-refund within 5-7 days.

Need help? Just reply here.

— NidaanPartner
```

**Hindi (hi)** — samples: {{1}}=Rajesh
```
{{1}}, आपका भुगतान पूरा नहीं हो पाया — और आपसे कोई पैसा नहीं कटा। ✅

जब आप तैयार हों, अपने डैशबोर्ड से दोबारा सुरक्षित रूप से कोशिश कर सकते हैं। अगर कोई राशि कटी है, तो वह 5-7 दिनों में अपने आप वापस आ जाएगी।

मदद चाहिए? बस यहाँ जवाब दें।

— NidaanPartner
```

---

### 6. Template `np_doc_reminder` — UTILITY

**English (en)** — samples: {{1}}=Rajesh, {{2}}=NP-0093, {{3}}=policy document
```
Namaste {{1}} 🙏

To move your claim (Ref #{{2}}) forward, we still need: {{3}}.

Please reply to this chat with a clear photo or PDF. We'll take care of the rest.

— NidaanPartner
```

**Hindi (hi)** — samples: {{1}}=Rajesh, {{2}}=NP-0093, {{3}}=policy document
```
नमस्ते {{1}} 🙏

आपके क्लेम (Ref #{{2}}) को आगे बढ़ाने के लिए हमें अभी चाहिए: {{3}}।

कृपया इसी चैट पर एक साफ़ फोटो या PDF भेजें। बाकी हम संभाल लेंगे।

— NidaanPartner
```

---

## After creation
Report each template's name and status (In review / Approved / Rejected). If Meta rejects any, note the reason so the wording can be adjusted. Once approved, the developer will map the approved names into the app's `JOURNEY_TEMPLATES` config to switch on business-initiated (cold-start) sends.
