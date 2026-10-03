# -*- coding: utf-8 -*-
"""ONE DOCUMENT LIMIT AT EVERY DOOR (founder, 3 Oct 2026: "100 MB each doc").

Through the real routes of the real app, and the WhatsApp / Telegram / email doors:
  * a 30 MB file - refused at 25 MB until today - is accepted; one over 100 MB is refused, saying
    the limit; several files too big for one request are refused as a batch, saying how to send them
  * the old one-request splitter (no virus scan, unused since 29 Sep) is closed
  * WhatsApp: a file Meta says is too big is NOT fetched, and the person is told the real reason
  * Telegram: a file over Telegram's own 20 MB is caught on the declared size, pointing to the website
  * email: an attachment over the limit is listed as too large - it used to vanish silently

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_limits.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
TMP = tempfile.mkdtemp(prefix="limits_")
DBP = os.path.join(TMP, "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_limits as L                       # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


def pdf(n_bytes):
    head = b"%PDF-1.4\n1 0 obj<<>>endobj\n"
    return head + b"0" * max(0, n_bytes - len(head) - 6) + b"\n%%EOF"


async def main():
    print("\n-- the numbers --")
    check("100 MB a document, 104 MB a request - under Cloudflare's measured 104,857,600",
          L.DOC_MAX_BYTES == 100_000_000 and L.REQUEST_MAX_BYTES == 104_000_000 < 104_857_600 - 512 * 1024)
    check("the scanner takes more than a document, so nothing we accept is unscannable",
          L.SCAN_MAX_BYTES > L.DOC_MAX_BYTES)

    import httpx
    os.environ.setdefault("NIDAAN_JWT_SECRET", "test-only-not-a-secret")
    import nidaan_app as app_mod
    import biz_av_scan

    async def _clean(_b, **k):
        return True, ""
    biz_av_scan.scan_bytes = _clean                 # no clamd here; the scanner has its own checks
    app_mod._NIDAAN_DOCS_DIR = __import__("pathlib").Path(TMP)
    app_mod.nidaan.DB_PATH = DBP
    await db.init_db()
    await nid.ensure_claim_documents_table()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash, status) "
                        "VALUES (1,'A','a@example.invalid','9000000001','x','active')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, status) "
                        "VALUES (7,1,'health','X','9000000007','intimated')")
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status) "
                        "VALUES (5,'Ravi','ravi@example.invalid','x','super_admin','active')")
        await c.commit()
    staff = {"Authorization": "Bearer " + nid.create_staff_token(5, "super_admin", "Ravi")}

    print("\n-- staff attach a document --")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_mod.app),
                                 base_url="https://nidaanpartner.com", timeout=120) as cl:
        url = "/nidaan/ops/api/claims/7/documents/upload"
        r = await cl.post(url, headers=staff, files={"files": ("big-scan.pdf", pdf(30_000_000), "application/pdf")})
        check("a 30 MB scan is accepted (it was refused at 25 MB)", r.status_code == 200, (r.status_code, r.text[:200]))
        r = await cl.post(url, headers=staff, files={"files": ("huge.pdf", pdf(101_000_000), "application/pdf")})
        check("a 101 MB file is refused, saying the limit", r.status_code == 413 and "100 MB" in r.text,
              (r.status_code, r.text[:200]))
        r = await cl.post(url, headers=staff, files=[("files", ("a.pdf", pdf(60_000_000), "application/pdf")),
                                                      ("files", ("b.pdf", pdf(60_000_000), "application/pdf"))])
        check("two 60 MB files in ONE request are refused as a batch, saying how much at a time",
              r.status_code == 413 and "104 MB" in r.text, (r.status_code, r.text[:200]))
        r = await cl.post("/nidaan/ops/api/docsplit/upload", headers=staff,
                          files={"files": ("a.pdf", pdf(1000), "application/pdf")})
        check("the old one-request splitter (no virus scan) is closed", r.status_code == 410, (r.status_code, r.text[:120]))

    print("\n-- WhatsApp --")
    import biz_nidaan_wa_unsorted as unsorted
    import biz_nidaan_whatsapp as wa

    async def _too_big(_mid):
        return {"ok": False, "error": "too_large", "size": 120_000_000}
    real = wa.download_media
    wa.download_media = _too_big
    data, _mime, why = await unsorted._download_and_scan("m1")
    check("a file Meta says is too big is not stored, and says why in plain words",
          data is None and "too large" in why and "100 MB" in why, why)
    wa.download_media = real

    # download_media itself: the size Meta declares is read BEFORE the file is fetched.
    fetched = []

    class _Resp:
        def __init__(self, status, payload=None, content=b""):
            self.status_code, self._p, self.content = status, payload, content or b"{}"

        def json(self):
            return self._p or {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            if url.endswith("/m2"):
                return _Resp(200, {"url": "https://cdn.example.invalid/m2", "file_size": 150_000_000})
            fetched.append(url)
            return _Resp(200, content=b"x" * 10)
    wa_is_conf, wa_tok, wa_httpx = wa.is_configured, wa._token, wa.httpx.AsyncClient
    wa.is_configured, wa._token = (lambda: True), (lambda: "t")
    wa.httpx.AsyncClient = _Client
    try:
        res = await wa.download_media("m2")
    finally:
        wa.is_configured, wa._token, wa.httpx.AsyncClient = wa_is_conf, wa_tok, wa_httpx
    check("...and the 150 MB file is never pulled into memory", res.get("error") == "too_large" and not fetched,
          (res, fetched))

    print("\n-- Telegram --")
    import biz_nidaan_bot_guard as g
    r = g.check_size(25 * L.MB)
    check("over Telegram's own 20 MB: refused before downloading, pointing to the website's 100 MB",
          not r["ok"] and "website" in r["reason"] and "100" in r["reason"], r)
    check("a normal file passes; an unknown size is left to the real check",
          g.check_size(5 * L.MB)["ok"] and g.check_size(0)["ok"])

    print("\n-- email --")
    import biz_nidaan_radar as radar
    radar.DB_PATH = DBP

    async def _atts(item_id, names_only):
        return {"item_id": item_id}, [{"name": "huge-scan.pdf", "size": 130_000_000, "too_big": True}]
    radar._attachments = _atts
    out = await radar.file_attachments_to_claim(1, 7, by="Ravi")
    check("an attachment over the limit is named as too large - it used to vanish",
          "huge-scan.pdf (too large)" in (out.get("skipped") or []), out)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
