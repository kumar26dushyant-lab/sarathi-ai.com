# -*- coding: utf-8 -*-
'''The authorization letter (founder, 1 Oct): letterhead with the firm's registered name, the
tentative fee calculation on the disputed amount frozen at acceptance, the complainant who signed -
and every letter accepted before this keeps exactly its old layout.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_authorization_letter.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBP = os.path.join(tempfile.mkdtemp(prefix="authletter_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import fitz                                         # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_claimant as cl                    # noqa: E402
cl.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:400])


def pdf_text(b: bytes) -> str:
    d = fitz.open(stream=b, filetype="pdf")
    return "\n".join(pg.get_text() for pg in d)


async def main():
    await db.init_db()
    await nid.set_ops_setting("gst_enabled", "1")
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'S','s@example.invalid','9000000001','x')")
        for cid in (71, 72):
            await c.execute(
                "INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                "insured_email, complainant_name, complainant_phone, complainant_email, disputed_amount, status) "
                "VALUES (?,1,'health','INSURED PERSON','9111111111','insured@example.invalid',"
                "'Complainant Person','9222222222','complainant@example.invalid',60000,'intimated')", (cid,))
        await c.commit()

    r = await cl.record_consent(71, ip="203.0.113.5", user_agent="test-agent")
    p = r["portal"]
    check("a new acceptance is a version-2 letter", int(p.get("consent_letter_version") or 0) == 2, p)
    check("the signer recorded is the COMPLAINANT, not the insured",
          p.get("consent_name") == "Complainant Person" and p.get("consent_phone") == "9222222222", p)
    check("the tentative calculation is frozen at acceptance (15% + 18% GST on Rs 60,000)",
          (p.get("consent_disputed_amount"), p.get("consent_fee_amount"), p.get("consent_gst_amount"),
           p.get("consent_total_fee"), p.get("consent_net_amount")) == (60000, 9000, 1620, 10620, 49380), p)

    b1 = await cl.build_consent_proof_pdf(71)
    t = pdf_text(b1)
    for want, label in (("Nidaan The Legal Consultants LLP", "the firm's registered name heads the letter"),
                        ("79/A, Ranjeet Hanuman Road", "the footer carries the registered office"),
                        ("enquiries@nidaanlegalindia.com", "...and the contact details"),
                        ("Complainant Person", "the complainant is named"),
                        ("Rs 60,000", "the disputed amount"), ("Rs 9,000", "our fee"), ("Rs 1,620", "GST"),
                        ("Rs 10,620", "the total fee"), ("Rs 49,380", "what they would receive"),
                        ("Page 1 of", "pages are numbered")):
        check("letter v2: " + label, want in t, t[:600])
    check("letter v2 never shows the insured as the signer", "INSURED PERSON" not in t)
    d = fitz.open(stream=b1, filetype="pdf")
    check("letter v2 carries the logo", any(pg.get_images() for pg in d))

    # the disputed amount changing later does not change a signed letter
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_claims SET disputed_amount=99999, complainant_name='Someone Else' "
                        "WHERE claim_id=71")
        await c.commit()
    t2 = pdf_text(await cl.build_consent_proof_pdf(71))
    check("downloading it again later gives the same letter (built only from the record)", t2 == t)

    # a letter accepted BEFORE today keeps its old layout
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_claimant_portal (claim_id, consent_accepted_at, consent_terms_version, "
                        "consent_fee_pct, consent_gst_pct, consent_name, consent_hash) "
                        "VALUES (72, '2026-09-15 12:00:00', 'v1', 15, 18, 'Old Signer', 'abc')")
        await c.commit()
    old = pdf_text(await cl.build_consent_proof_pdf(72))
    check("an earlier acceptance keeps its old layout (DIGITAL CONSENT RECORD, no fee table)",
          "DIGITAL CONSENT RECORD" in old and "Tentative fee calculation".upper() not in old.upper(), old[:300])

    for v, want in ((1000, "Rs 1,000"), (99, "Rs 99"), (123456.5, "Rs 1,23,456.50"), (10000000, "Rs 1,00,00,000")):
        check("rupees in Indian grouping: %s -> %s" % (v, want), cl._rs(v) == want, cl._rs(v))

    src = open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
    check("the thank-you after acceptance goes to the complainant first",
          "COALESCE(NULLIF(complainant_email,''), insured_email) AS insured_email" in src)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
