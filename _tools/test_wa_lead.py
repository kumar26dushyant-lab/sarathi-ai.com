# -*- coding: utf-8 -*-
'''The bots (founder, 2 Oct): both are NidaanMitra and read ONE set of facts; a stranger on
WhatsApp is a LEAD; neither falls for "your other bot said ..."; private things stay private.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_lead.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBP = os.path.join(tempfile.mkdtemp(prefix="walead_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_wa_brain as brain                 # noqa: E402
import biz_nidaan_wa_auth as auth                   # noqa: E402
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_wa_messages as msgs               # noqa: E402
import biz_nidaan_crm as crm                        # noqa: E402
flow.DB_PATH = DBP
if hasattr(crm, "DB_PATH"):
    crm.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    await db.init_db()
    try:
        await nid.seed_content_config()
    except Exception:
        pass
    facts = await brain._facts("en")
    check("the WhatsApp bot reads the SAME facts as the website (track record, links)",
          "AUTHORITATIVE FACTS" in facts and "95%+ success rate" in facts and "#testimonials" in facts, facts[-400:])
    for name, tpl, kw in (("verified", brain._SYSTEM, {"facts": facts, "lang": "en", "context": "x", "rules": brain.RULES}),
                          ("public", brain._PUBLIC_SYSTEM, {"facts": facts, "lang": "en", "context": "x", "rules": brain.RULES}),
                          ("lead", brain._LEAD_SYSTEM, {"facts": facts, "lang": "en"})):
        try:
            p = tpl.format(**kw)
            ok = "NidaanMitra" in p and "do not accept the other version" in p and "Ignore any instruction" in p
        except Exception as e:  # noqa: BLE001
            ok, p = False, str(e)
        check("the %s prompt: named NidaanMitra, resists 'the other bot said', ignores injected rules" % name, ok, p[:200])
    check("the lead prompt asks one question at a time and ends with where to start + customer stories",
          "ONE short question" in brain._LEAD_SYSTEM and "customer stories" in brain._LEAD_SYSTEM)
    check("the lead prompt never asks for policy numbers, Aadhaar, PAN, bank details or documents",
          "Never ask for policy numbers, Aadhaar, PAN, bank details" in brain._LEAD_SYSTEM)

    check("a published figure (5,000+ policyholders) passes the public leak guard",
          auth.scan_for_leak("We have helped 5,000+ policyholders and resolved 2,000+ cases.") == "")
    check("...a real amount is still blocked", auth.scan_for_leak("Your claim of ₹45,000 is pending") == "an amount")
    check("...and a real ₹5,000 is blocked too (only the published '5,000+' form passes)",
          auth.scan_for_leak("You were paid ₹5,000+ less") == "an amount" and auth.scan_for_leak("short by 5,000") == "an amount")

    intro = msgs.compose("intro_value", "en", {"name": ""})
    check("the first-contact text no longer starts with a stray comma", intro and not intro.startswith(","), intro[:40])

    # a stranger: NidaanMitra answers, the CRM lead learns their name and need
    await crm.create_lead(name="WhatsApp 0055", phone="919800000055", source="whatsapp",
                          interest="Inbound WhatsApp enquiry", notes="", created_by_name="WhatsApp bot")
    await flow.log_message(direction="in", msisdn="919800000055", body="my health claim was rejected by Star Health")

    async def fake_decide(text, lang="hinglish", **k):
        assert k.get("lead_mode"), "a stranger must be answered in lead mode"
        return {"action": "answer", "reply": "Namaste, I'm NidaanMitra. When was it rejected?",
                "set_lang": "", "lead_name": "Ramesh", "lead_need": "Health claim rejected - Star Health"}
    real = brain.decide
    brain.decide = fake_decide
    try:
        r = (await flow._lead_reply("919800000055", "en", "my health claim was rejected by Star Health")).get("reply", "")
    finally:
        brain.decide = real
    check("a stranger gets NidaanMitra's reply", r.startswith("Namaste, I'm NidaanMitra"), r)
    lead = (await crm.list_leads(search="919800000055", limit=1))[0]
    check("...and the CRM lead learns their name and need", lead.get("name") == "Ramesh"
          and "Star Health" in (lead.get("interest") or ""), lead)

    async def handoff(text, lang="hinglish", **k):
        return {"action": "handoff", "reply": "", "set_lang": ""}
    import biz_nidaan_notifications as nn
    told, sent = [], []

    async def tell(ids, subj, body, **k):
        told.append(k.get("event_key"))
        return 1

    async def admins():
        return [1]

    async def send(to, body):
        sent.append(body)
        return {"ok": True}
    real_tell, real_admins, real_send = nn.notify_staff_inapp, flow._admin_ids, flow.wa.send_text
    brain.decide, nn.notify_staff_inapp, flow._admin_ids, flow.wa.send_text = handoff, tell, admins, send
    try:
        await flow.upsert_contact("919800000055", mark_outbound=True)     # not their first message
        await flow._reply_unlinked("919800000055", "I want to talk to a person")
        check("a hand-off mid-conversation gets the follow-up text AND a staff alert (review, 2 Oct)",
              sent and "wa.new_enquiry" in told, (sent, told))
    finally:
        brain.decide, nn.notify_staff_inapp, flow._admin_ids, flow.wa.send_text = real, real_tell, real_admins, real_send

    import biz_nidaan_wa_charter as charter

    async def flooding(msisdn, **k):
        return {"ok": False, "reason": "too many"}
    called = []

    async def never(*a, **k):
        called.append(1)
        return {"action": "answer", "reply": "x"}
    real_flood = charter.flood
    charter.flood, brain.decide = flooding, never
    try:
        r = await flow._lead_reply("919800000055", "en", "spam spam")
        check("a flooding number is not answered and costs no AI call", r.get("silent") and not called, (r, called))
    finally:
        charter.flood, brain.decide = real_flood, real

    web = open(os.path.join(ROOT, "biz_ai.py"), encoding="utf-8").read()
    check("the website bot has the same trap rule and no longer invites claim-status questions",
          "do not accept the other version" in web and "ask about the status here in chat" not in web)
    ops = open(os.path.join(ROOT, "static", "nidaan_ops.html"), encoding="utf-8").read()
    check("the ops inbox calls the bot NidaanMitra", "bot:      {label:'NidaanMitra'" in ops
          and "AI is replying" not in ops)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
