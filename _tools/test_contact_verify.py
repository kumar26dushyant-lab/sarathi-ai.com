# -*- coding: utf-8 -*-
'''A complainant's email / mobile is "verified" only when THAT address was proven.

Founder, 1 Oct - claim 174 (Mukesh Tak): the email was wrong and showed "verified"; corrected, it
still showed "verified". Found: opening the claim page marked the EMAIL verified even when the
complainant proved who they were by WhatsApp (40 of 65 "verified" claims), and the flag was not
tied to the address, so a correction kept it.

What these checks defend:

  * a proof belongs to an exact address: change it and it is unverified; change back and it counts;
  * a WhatsApp code proves the PHONE, an emailed code the EMAIL - never the other one;
  * a change cuts everything tied to the old contact (live codes, the claim link, the old
    WhatsApp number's link to the claim), is written old -> new (masked), and asks the new one;
  * a confirmation proves nothing if the contact changed after it was sent;
  * a message arriving from a claim's number proves that number; a replied code confirms it;
  * the carry-over keeps only what the old flag really proved, and nothing edited since;
  * the daily nudge reaches the handler, once a day, and skips what is already on its way;
  * the routes: formats checked, only real changes logged, the complainant's own session (never a
    staff preview) for the claim page.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_contact_verify.py
'''
import asyncio
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
os.environ.setdefault("WA_VERIFY_PEPPER", "test-pepper-not-a-secret")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_root = tempfile.mkdtemp(prefix="contact_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_nidaan as nid                            # noqa: E402
import biz_nidaan_contact_verify as cv              # noqa: E402
import biz_nidaan_claimant as cl                    # noqa: E402
import biz_nidaan_notifications as nn               # noqa: E402

nid.DB_PATH = db.DB_PATH

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_claims (claim_id INTEGER PRIMARY KEY, account_id INTEGER,
    complainant_name TEXT DEFAULT '', insured_name TEXT DEFAULT '',
    complainant_email TEXT DEFAULT '', insured_email TEXT DEFAULT '',
    complainant_phone TEXT DEFAULT '', insured_phone TEXT DEFAULT '',
    assigned_to_staff_id INTEGER, archived INTEGER DEFAULT 0, status TEXT DEFAULT 'intimated',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP, last_status_at TEXT, pipeline_stage TEXT,
    insured_email_verified INTEGER DEFAULT 0, insured_email_verified_at TEXT);
CREATE TABLE nidaan_contact_verifications (vid INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER,
    account_id INTEGER, kind TEXT NOT NULL, value TEXT NOT NULL, method TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '', verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_contact_confirm (cid INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL,
    kind TEXT NOT NULL, value TEXT NOT NULL, code_hash TEXT NOT NULL DEFAULT '',
    token_hash TEXT NOT NULL DEFAULT '', sent_by TEXT NOT NULL DEFAULT '',
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP NOT NULL, used_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE nidaan_claim_verify (vid INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL,
    channel TEXT DEFAULT '', sent_to TEXT DEFAULT '', code_hash TEXT NOT NULL, attempts INTEGER DEFAULT 0,
    consumed INTEGER DEFAULT 0, expires_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_wa_contacts (msisdn TEXT PRIMARY KEY, claim_id INTEGER);
CREATE TABLE nidaan_claim_activity (act_id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL,
    kind TEXT NOT NULL, channel TEXT DEFAULT '', direction TEXT DEFAULT '', actor TEXT DEFAULT '',
    summary TEXT DEFAULT '', meta TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_audit_log (log_id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, target_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_ops_settings (key TEXT PRIMARY KEY, value TEXT, updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
INSERT INTO nidaan_claims (claim_id, account_id, complainant_name, complainant_email, complainant_phone,
    assigned_to_staff_id) VALUES (174, 50, 'MUKESH TAK', 'tak4091@gmail.com', '9876543355', 23);
"""

SENT, TOLD, ROTATED = [], [], []


async def f_email(claim, value, token, base_url, code=""):
    SENT.append(("email", value, token, code))
    return {"ok": True, "why": ""}


async def f_phone(claim, value, code):
    SENT.append(("phone", value, "", code))
    return {"ok": True, "why": ""}


async def f_rotate(cid):
    ROTATED.append(cid)
    return "new-token"


async def f_notify(ids, subject, body, event_key="", email=True, **kw):
    TOLD.append({"ids": list(ids), "subject": subject, "body": body, "key": event_key})
    return len(ids)


async def f_admins():
    return [{"staff_id": 1}]


cv._send_email = f_email
cv._send_phone = f_phone
cl.rotate_token = f_rotate
nn.notify_staff_inapp = f_notify
nn._super_admin_staff = f_admins


async def q(sql, *a):
    async with aiosqlite.connect(db.DB_PATH) as c:
        cur = await c.execute(sql, a)
        rows = await cur.fetchall()
        await c.commit()
        return rows


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    print("\nA proof belongs to an exact address\n")
    claim = await cv._claim(174)
    st = await cv.status(claim)
    check("nothing proven yet: both unverified", not st["email"]["verified"] and not st["phone"]["verified"], st)
    await cv.record("phone", "9876543355", "portal_whatsapp_code", claim_id=174)
    st = await cv.status(claim)
    check("a WhatsApp code proves the PHONE", st["phone"]["verified"], st["phone"])
    check("...and NOT the email - claim 174's bug", not st["email"]["verified"], st["email"])
    await cv.record("email", "tak4091@gmail.com", "portal_email_code", claim_id=174)
    await q("UPDATE nidaan_claims SET complainant_email='mukesh.tak@gmail.com' WHERE claim_id=174")
    st = await cv.status(await cv._claim(174))
    check("a corrected email is UNverified at once", not st["email"]["verified"], st["email"])
    await q("UPDATE nidaan_claims SET complainant_email='tak4091@gmail.com' WHERE claim_id=174")
    check("changing back to the proven address counts again",
          (await cv.status(await cv._claim(174)))["email"]["verified"])
    check("the proof says how, in words",
          "code" in (await cv.status(await cv._claim(174)))["email"]["how"])

    print("\nWhen a contact changes\n")
    await q("INSERT INTO nidaan_claim_verify (claim_id, channel, code_hash) VALUES (174, 'email', 'x')")
    await q("INSERT INTO nidaan_wa_contacts VALUES ('919876543355', 174)")
    await q("UPDATE nidaan_claims SET complainant_email='mukesh.tak@gmail.com', "
            "complainant_phone='9000011111' WHERE claim_id=174")
    SENT.clear()
    res = await cv.on_change(174, {"email": ("tak4091@gmail.com", "mukesh.tak@gmail.com"),
                                   "phone": ("9876543355", "9000011111")}, actor="Priya")
    live = await q("SELECT COUNT(*) FROM nidaan_claim_verify WHERE claim_id=174 AND consumed=0")
    check("a code already sent to the old contact is dead", live[0][0] == 0, live)
    check("the claim link is replaced", ROTATED == [174], ROTATED)
    link = await q("SELECT claim_id FROM nidaan_wa_contacts WHERE msisdn='919876543355'")
    check("the old WhatsApp number is no longer linked to the claim", link[0][0] is None, link)
    acts = [r[0] for r in await q("SELECT summary FROM nidaan_claim_activity WHERE kind='contact_change'")]
    check("the change is on the timeline, old -> new, masked",
          any("ta•••1@gmail.com" in a and "mu•••" in a for a in acts) and not any("tak4091" in a for a in acts), acts)
    check("a confirmation goes to the NEW email and the NEW mobile at once",
          {(k, v) for k, v, _t, _c in SENT} == {("email", "mukesh.tak@gmail.com"), ("phone", "9000011111")}, SENT)

    print("\nConfirming\n")
    token = next(t for k, v, t, c in SENT if k == "email")
    code_e = next(c for k, v, t, c in SENT if k == "email")
    code_p = next(c for k, v, t, c in SENT if k == "phone")
    check("a wrong emailed code proves nothing",
          not (await cv.confirm_email_code(174, "000000"))["ok"])
    check("the right emailed code proves the email",
          (await cv.confirm_email_code(174, code_e))["ok"]
          and (await cv.status(await cv._claim(174)))["email"]["verified"])
    check("a code replied from ANOTHER number confirms nothing",
          await cv.confirm_whatsapp_reply("919999999999", code_p) is None)
    check("the code replied from the new number confirms it",
          await cv.confirm_whatsapp_reply("919000011111", code_p) == 174
          and (await cv.status(await cv._claim(174)))["phone"]["verified"])

    print("\nA link clicked after the email changed proves nothing\n")
    await q("INSERT INTO nidaan_claims (claim_id, account_id, complainant_email, complainant_phone) "
            "VALUES (201, 60, 'a@x.com', '9111111111')")
    SENT.clear()
    await cv.send_confirm(201, "email")
    tok = SENT[-1][2]
    await q("UPDATE nidaan_claims SET complainant_email='b@x.com' WHERE claim_id=201")
    r = await cv.confirm_link(tok)
    check("the link is refused as 'changed'", r.get("changed") and not r.get("ok"), r)
    check("...and b@x.com is still unverified", not (await cv.status(await cv._claim(201)))["email"]["verified"])
    check("a made-up token is refused", not (await cv.confirm_link("nope"))["ok"])

    print("\nNobody is flooded\n")
    for _ in range(4):
        last = await cv.send_confirm(201, "email")
    check("at most 3 confirmations a day per contact", not last["ok"] and "3" in last["why"], last)

    print("\nA message from the number proves the number\n")
    await q("INSERT INTO nidaan_claims (claim_id, complainant_phone) VALUES (202, '9222222222')")
    await q("INSERT INTO nidaan_claims (claim_id, complainant_phone, archived) VALUES (203, '9222222222', 1)")
    n = await cv.note_inbound("919222222222")
    check("an open claim with that mobile is now proven", n == 1
          and (await cv.status(await cv._claim(202)))["phone"]["verified"], n)
    check("an archived one is left alone", not (await cv.status(await cv._claim(203)))["phone"]["verified"])

    print("\nThe carry-over keeps only what was really proven\n")
    await q("INSERT INTO nidaan_claims (claim_id, complainant_email, complainant_phone, insured_email_verified, "
            "insured_email_verified_at) VALUES (301, 'w@x.com', '9300000001', 1, '2026-09-20 10:00:00'), "
            "(302, 'e@x.com', '9300000002', 1, '2026-09-20 10:00:00'), "
            "(303, 'l@x.com', '9300000003', 1, '2026-09-01 10:00:00'), "
            "(304, 'z@x.com', '9300000004', 1, '2026-09-20 10:00:00')")
    await q("INSERT INTO nidaan_claim_activity (claim_id, kind, summary, created_at) VALUES "
            "(301, 'portal_open', 'Complainant confirmed their identity by whatsapp', '2026-09-20 10:00:00'), "
            "(302, 'portal_open', 'Complainant confirmed their identity by email', '2026-09-20 10:00:00'), "
            "(304, 'portal_open', 'Complainant confirmed their identity by email', '2026-09-20 10:00:00')")
    await q("INSERT INTO nidaan_audit_log (action, target_id, created_at) VALUES "
            "('claim.info_edit', '304', '2026-09-25 10:00:00')")
    done = await cv.carry_over_legacy()
    s301 = await cv.status(await cv._claim(301))
    check("a WhatsApp sign-in carries over as the PHONE, not the email",
          s301["phone"]["verified"] and not s301["email"]["verified"], s301)
    check("an email-code sign-in carries over as the email",
          (await cv.status(await cv._claim(302)))["email"]["verified"])
    s303 = await cv.status(await cv._claim(303))
    check("the link era carries over as the email, labelled as the older method",
          s303["email"]["verified"] and "before codes" in s303["email"]["how"], s303["email"])
    check("a claim edited after its proof carries NOTHING",
          not (await cv.status(await cv._claim(304)))["email"]["verified"] and done["skipped_edited"] >= 1, done)

    print("\nThe daily nudge\n")
    TOLD.clear()
    await q("INSERT INTO nidaan_claims (claim_id, complainant_email, assigned_to_staff_id) "
            "VALUES (401, 'n@x.com', 23)")
    r = await cv.nudge_unverified("2026-10-01")
    mine = [t for t in TOLD if t["ids"] == [23]]
    check("the handler hears about their claim", mine and "NP-401" in mine[0]["body"], TOLD)
    check("...as a bell + Telegram notice", mine and mine[0]["key"] == "contact.unverified")
    l201 = [ln for t in TOLD for ln in t["body"].splitlines() if ln.startswith("NP-201 ")]
    check("...and not about a contact a confirmation just went to (201's email; its mobile yes)",
          l201 and "email" not in l201[0] and "mobile" in l201[0], l201)
    r2 = await cv.nudge_unverified("2026-10-01")
    check("once a day", r2.get("skipped"), r2)

    print("\nThe routes\n")
    src = io.open("sarathi_biz.py", encoding="utf-8").read()

    def body(name):
        m = re.search(r"async def %s\(.*?(?=\n@app\.|\nclass |\nasync def (?!_prog))" % name, src, re.S)
        return m.group(0) if m else ""
    vc = body("nidaan_claim_verify_check")
    check("a claim-page sign-in records the channel it USED",
          '== "email"' in vc and '"portal_email_code"' in vc and '"portal_whatsapp_code"' in vc)
    check("opening the page no longer marks the email verified",
          "insured_email_verified=1" not in io.open("biz_nidaan_claimant.py", encoding="utf-8").read())
    ed = body("ops_update_claim_info")
    check("the edit checks formats", "sanitize_email" in ed and "10-digit" in ed)
    check("...logs only what really changed", "saved with no change" in ed and "_cv.mask" in ed)
    check("...and hands a contact change to the one rule", "_cv.on_change(" in ed)
    for name in ("nidaan_claim_email_code", "nidaan_claim_email_check", "nidaan_claim_email_change",
                 "nidaan_claim_email_skip"):
        check("%-26s needs the complainant's own session" % name, "_claimant_live_ctx(request)" in body(name))
    check("...which a staff preview cannot use", 'ctx.get("preview")' in body("_claimant_live_ctx"))
    cc = body("ops_claim_contact_confirm")
    check("staff 'Send confirmation' checks access to the claim", "assert_claim_access" in cc)

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
