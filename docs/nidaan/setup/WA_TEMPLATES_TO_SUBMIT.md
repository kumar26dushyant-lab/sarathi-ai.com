# WhatsApp Templates to Submit in Meta — NidaanPartner

> **Why this exists:** business-initiated WhatsApp messages (a message we send when the
> customer has NOT written to us in the last 24 h) can ONLY go out as a **pre-approved
> template**. Free-form text works only inside the 24-hour session after the customer
> replies. Every journey message below is business-initiated, so each needs an approved
> template before it can deliver.
>
> **What to do:** in Meta Business Manager → WhatsApp Manager → **Message templates** →
> Create template, paste each block below (English first; add the Hindi language variant
> under the SAME template name). After a template is APPROVED, put its exact name into
> `JOURNEY_TEMPLATES` in `biz_nidaan_wa_orchestrator.py` (and the doc-collection map) — the
> code already sends the free-form version in-session and falls back to these templates when
> cold. Nothing else needs to change.
>
> WABA: **+91 91836 86384** · Phone Number ID `1251678818039212` · WABA ID `1695397392252786`

---

## How the code uses these

| Journey event (composer `kind`) | Template name to create | Category | Fires when |
|---|---|---|---|
| `claim_registered` | `np_claim_registered` | UTILITY | A claim is raised for the complainant (branch/subscriber/ops) |
| `welcome` | `np_welcome` | UTILITY | First time a complainant number lands in our DB |
| `intro_value` | `np_intro_value` | MARKETING | Warm value message, opt-in nudge (promotional) |
| `thank_you_payment` | `np_payment_thanks` | UTILITY | A payment succeeds (₹499 / L2 / subscription) |
| `payment_failed` | `np_payment_failed` | UTILITY | A payment attempt fails or is declined |
| `doc_reminder` | `np_doc_reminder` | UTILITY | A required document is still pending |

> **Category matters for approval & pricing.** UTILITY = transactional (post-purchase, account
> updates) — cheaper, approves easily. MARKETING = promotional — needs opt-in, priced higher.
> Keep `intro_value` the only MARKETING template; everything else is UTILITY.

---

## Variables convention

Meta uses positional variables `{{1}}`, `{{2}}`… Keep the order below EXACTLY — the code fills
them positionally. Provide a sample value for each (Meta requires samples to approve).

---

## 1. `np_claim_registered` — UTILITY

**English**
```
Namaste {{1}} 🙏

Your claim has been registered with NidaanPartner (Ref #{{2}}). Our team is now
reviewing the details for {{3}}.

We will guide you at every step. You can reply to this chat any time with questions
or documents.

— NidaanPartner
```
Samples: `{{1}}` = Rajesh · `{{2}}` = NP-0093 · `{{3}}` = Suresh Kumar

**Hindi**
```
नमस्ते {{1}} 🙏

आपका क्लेम NidaanPartner में दर्ज हो गया है (Ref #{{2}})। हमारी टीम अब {{3}} के लिए
विवरण की समीक्षा कर रही है।

हम हर कदम पर आपका मार्गदर्शन करेंगे। किसी भी सवाल या दस्तावेज़ के लिए आप इसी चैट पर
जवाब दे सकते हैं।

— NidaanPartner
```

---

## 2. `np_welcome` — UTILITY

**English**
```
Namaste {{1}} 🙏

This is the official WhatsApp of NidaanPartner — your support partner for rejected
or disputed insurance claims. Please save this number so our updates always reach
you safely.

We're here to help. Reply here any time.

— NidaanPartner
```
Samples: `{{1}}` = Rajesh

**Hindi**
```
नमस्ते {{1}} 🙏

यह NidaanPartner का आधिकारिक WhatsApp है — अस्वीकृत या विवादित इंश्योरेंस क्लेम में
आपका सहायता-साथी। कृपया यह नंबर सेव कर लें ताकि हमारे अपडेट आप तक सुरक्षित पहुँचें।

हम आपकी मदद के लिए हैं। कभी भी यहाँ जवाब दें।

— NidaanPartner
```

---

## 3. `np_intro_value` — MARKETING

**English**
```
{{1}}, a rejected insurance claim is not the end. 💪

When a claim you paid for honestly gets rejected, it feels unfair — and most people
give up because the process feels too complex. NidaanPartner stands with people like
you: we review your case, tell you the real way forward, and fight for what is
rightfully yours.

Reply YES and we'll show you your next step. Reply STOP to opt out.

— NidaanPartner
```
Samples: `{{1}}` = Rajesh

**Hindi**
```
{{1}}, इंश्योरेंस क्लेम रिजेक्ट होना अंत नहीं है। 💪

जब मेहनत की कमाई से लिया गया क्लेम रिजेक्ट होता है, तो यह अन्याय जैसा लगता है — और
प्रक्रिया जटिल लगने से ज़्यादातर लोग हार मान लेते हैं। NidaanPartner आप जैसे लोगों के
साथ खड़ा है: हम आपका केस देखते हैं, आगे का सही रास्ता बताते हैं, और आपके हक़ के लिए
लड़ते हैं।

आगे का कदम जानने के लिए YES लिखें। ऑप्ट-आउट के लिए STOP लिखें।

— NidaanPartner
```

---

## 4. `np_payment_thanks` — UTILITY

**English**
```
Thank you {{1}}! ✅

Your payment of ₹{{2}} is confirmed (Ref #{{3}}). Your review has started — we'll
keep you updated here and on your dashboard.

— NidaanPartner
```
Samples: `{{1}}` = Rajesh · `{{2}}` = 499 · `{{3}}` = NP-0093

**Hindi**
```
धन्यवाद {{1}}! ✅

आपका ₹{{2}} का भुगतान मिल गया (Ref #{{3}})। आपकी समीक्षा शुरू हो गई है — हम आपको यहीं
और आपके डैशबोर्ड पर अपडेट देते रहेंगे।

— NidaanPartner
```

---

## 5. `np_payment_failed` — UTILITY

**English**
```
{{1}}, your payment did not go through — and no money was deducted from you. ✅

You can safely try again from your dashboard whenever you're ready. If any amount
was debited, it will auto-refund within 5-7 days.

Need help? Just reply here.

— NidaanPartner
```
Samples: `{{1}}` = Rajesh

**Hindi**
```
{{1}}, आपका भुगतान पूरा नहीं हो पाया — और आपसे कोई पैसा नहीं कटा। ✅

जब आप तैयार हों, अपने डैशबोर्ड से दोबारा सुरक्षित रूप से कोशिश कर सकते हैं। अगर कोई
राशि कटी है, तो वह 5-7 दिनों में अपने आप वापस आ जाएगी।

मदद चाहिए? बस यहाँ जवाब दें।

— NidaanPartner
```

---

## 6. `np_doc_reminder` — UTILITY

**English**
```
Namaste {{1}} 🙏

To move your claim (Ref #{{2}}) forward, we still need: {{3}}.

Please reply to this chat with a clear photo or PDF. We'll take care of the rest.

— NidaanPartner
```
Samples: `{{1}}` = Rajesh · `{{2}}` = NP-0093 · `{{3}}` = policy document

**Hindi**
```
नमस्ते {{1}} 🙏

आपके क्लेम (Ref #{{2}}) को आगे बढ़ाने के लिए हमें अभी चाहिए: {{3}}।

कृपया इसी चैट पर एक साफ़ फोटो या PDF भेजें। बाकी हम संभाल लेंगे।

— NidaanPartner
```

---

## After approval — flip the switch

1. Copy each APPROVED template's exact name.
2. Edit `JOURNEY_TEMPLATES` in `biz_nidaan_wa_orchestrator.py`:
   ```python
   JOURNEY_TEMPLATES = {
       "welcome": "np_welcome",
       "intro_value": "np_intro_value",
       "claim_registered": "np_claim_registered",
       "thank_you_payment": "np_payment_thanks",
       "payment_failed": "np_payment_failed",
   }
   ```
3. Deploy. Cold-start journey messages now deliver automatically; in-session messages
   already use the richer free-form composer text.

> Until then: journey events still fire, log to the claim timeline as
> "queued — needs approved template", and any message sent WITHIN the 24-hour session
> window (i.e. after the complainant writes to us) already delivers as free-form text.
