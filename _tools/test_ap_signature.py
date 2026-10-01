# -*- coding: utf-8 -*-
'''The Authorized Partner's name on every message about their claims (founder, 1 Oct).

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_ap_signature.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBP = os.path.join(tempfile.mkdtemp(prefix="apsign_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_ap_sign as aps                    # noqa: E402
import biz_email as mail                            # noqa: E402
import biz_nidaan_notifications as nn               # noqa: E402

FAILED = 0
LINE = "Rakesh Sharma, Authorized Partner of NidaanPartner.com, Pune (MH)"


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def sql(q, *a):
    async with aiosqlite.connect(DBP) as c:
        await c.execute(q, a)
        await c.commit()


async def main():
    await db.init_db()
    r = await nid.create_branch("PUN-09", "Pune", "Pune office", "pune.ap@example.invalid",
                                contact_person="  Rakesh   Sharma ", state="mh")
    check("an AP is created with the person's name and state", r.get("ok"), r)
    check("a state not on the list is refused",
          "error" in await nid.create_branch("XX-01", "Town", contact_person="A", state="ZZ"))
    await nid.update_branch("PUN-09", contact_phone="9800000009")
    await nid.create_branch("IDR-07", "Indore", contact_person="", state="MP")      # no person yet
    await nid.create_branch("BPL-03", "Bhopal", contact_person="Off Person", state="MP")
    await nid.update_branch("BPL-03", status="disabled")
    for aid, code in ((1, ""), (2, "PUN-09"), (3, "SP-ABC123"), (4, "IDR-07"), (5, "BPL-03")):
        await sql("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash, branch_code) "
                  "VALUES (?, 'A', ?, ?, 'x', ?)", aid, "a%d@example.invalid" % aid, "90000000%02d" % aid, code)
    claims = {10: (1, "PUN-09"),     # raised by the AP
              20: (2, ""),           # a subscriber who joined with the AP's code / link
              30: (3, "SP-ABC123"),  # a staff member's My Business claim
              40: (4, ""),           # AP with no person's name yet
              50: (5, ""),           # AP disabled
              60: (1, "")}           # a direct claim, no AP
    for cid, (aid, code) in claims.items():
        await sql("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, status, "
                  "branch_code) VALUES (?,?,'health','X','9000000001','intimated',?)", cid, aid, code)

    body = "Your claim is registered.\n\n— Team NidaanPartner"
    s10 = await aps.for_whatsapp(body, claim_id=10)
    check("AP-raised claim: WhatsApp ends with the AP line", s10.endswith("— " + LINE), s10)
    check("...which REPLACES the team sign-off (one sender, not two)", "Team NidaanPartner" not in s10, s10)
    check("AP-referred subscriber's claim (code or shared link): signed too",
          (await aps.for_whatsapp(body, claim_id=20)).endswith(LINE))
    for cid, why in ((30, "a staff My Business claim (SP- code)"), (40, "an AP with no person's name yet"),
                     (50, "a disabled AP"), (60, "a direct claim")):
        check("never signed: %s" % why, await aps.for_whatsapp(body, claim_id=cid) == body)
    hi = await aps.for_whatsapp("आपका क्लेम दर्ज हुआ।\n\n— NidaanPartner टीम", claim_id=10, lang="hi")
    check("Hindi: the line in Hindi, the Hindi team sign-off replaced",
          hi.endswith("— Rakesh Sharma, NidaanPartner.com के अधिकृत पार्टनर, Pune (MH)") and "टीम" not in hi, hi)
    check("never to staff or the AP itself (business class)",
          await aps.for_whatsapp(body, claim_id=10, cls="business") == body)
    check("never to the AP's own WhatsApp number",
          await aps.for_whatsapp(body, msisdn="919800000009", claim_id=10) == body)
    with aps.unsigned():
        check("a one-time code is never signed, even about an AP's claim",
              await aps.for_whatsapp("Your code is 123456", claim_id=10) == "Your code is 123456")

    # the OTP sender really runs unsigned: its WhatsApp fallback sees the marker
    import biz_nidaan_claim_access as acc
    import biz_nidaan_whatsapp as wa
    seen = []

    async def no_template(*a, **k):
        return {"ok": False}

    async def text(to, b):
        seen.append(await aps.for_whatsapp(b, msisdn=to, claim_id=10))
        return {"ok": True}
    real = (wa.send_auth_code, wa.send_text)
    wa.send_auth_code, wa.send_text = no_template, text
    try:
        await acc._send("whatsapp", "919811111111", "654321", {"insured_name": "X"}, "en")
    finally:
        wa.send_auth_code, wa.send_text = real
    check("claim_access._send (login code) runs unsigned on its free-text fallback",
          seen and LINE not in seen[0], seen)

    # email
    html = "<p>Hello</p><p>— Nidaan – The Legal Consultants LLP</p>"
    with aps.about(claim_id=10):
        h, t = await aps.for_email("complainant@example.invalid", html, "Hello\n\n— Team NidaanPartner")
    check("email: the AP line replaces the LLP sign-off in the HTML", LINE in h and "Legal Consultants" not in h, h)
    check("email: and in the text part", t.endswith(LINE), t)
    with aps.about(claim_id=10):
        same = await aps.for_email("pune.ap@example.invalid", html, "")
    check("email: never to the AP's own inbox", same[0] == html)
    h2, _ = await aps.for_email("x@example.invalid", html, "")
    check("email: nothing is signed unless the sender says which claim it is about", h2 == html)
    wrapped = mail._wrap_nidaan_template("T", "<p>Hi</p>")
    with aps.about(claim_id=20):
        h3, _ = await aps.for_email("c@example.invalid", wrapped, "")
    check("email without a sign-off: the line goes just above the footer",
          h3.index(LINE) < h3.index('<div class="footer">'), h3[-400:])
    out = {}
    ok = await mail.send_email("branch.pun-09@house.nidaanpartner.internal", "s", "<p>x</p>", transport_out=out)
    check("no email is ever sent to an AP house account's made-up address",
          ok is False and "house" in (out.get("error") or ""), out)

    # the notification hub marks customer emails (and only those) with their claim
    marks = []

    async def capture(**k):
        marks.append((k["to_email"], aps.current()))
        return True, ""
    real_send = nn._send_email
    nn._send_email = capture
    try:
        await nn.dispatch(event_key="claim.status_changed", recipient_type=nn.RECIPIENT_SUBSCRIBER,
                          recipient_email="sub@example.invalid", subject="s", body="b", claim_id=10,
                          force_email=True)
        await nn.dispatch(event_key="claim.status_changed", recipient_type=nn.RECIPIENT_STAFF, recipient_id=1,
                          recipient_email="staff@example.invalid", subject="s", body="b", claim_id=10,
                          force_email=True)
    finally:
        nn._send_email = real_send
    sub = [m for e, m in marks if e == "sub@example.invalid"]
    stf = [m for e, m in marks if e == "staff@example.invalid"]
    check("dispatch: a customer email carries its claim", sub and (sub[0] or {}).get("claim_id") == 10, marks)
    check("dispatch: a staff email does not", not stf or not (stf[0] or {}).get("claim_id"), marks)

    # a welcome started as a background task still knows whose code they joined with
    async def probe():
        return aps.current()
    got = await aps.task_for_account(2, probe())
    check("a welcome email sent in the background still knows the account", (got or {}).get("account_id") == 2, got)
    check("...and the account's AP signs it", await aps.ap_for(account_id=2) is not None)

    # editing the AP takes effect on the next message
    await nid.update_branch("PUN-09", contact_person="Rakesh K. Sharma")
    check("an edited name is used at once (cache cleared)",
          "Rakesh K. Sharma, Authorized Partner" in await aps.for_whatsapp(body, claim_id=10))

    src = open(os.path.join(ROOT, "biz_nidaan_whatsapp.py"), encoding="utf-8").read()
    i_sig, i_foot = src.find("_aps.for_whatsapp("), src.find('if _g.get("footer") and payload.get("type") == "text"')
    check("WhatsApp's one send point signs, before the STOP line", 0 < i_sig < i_foot)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
