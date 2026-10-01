# -*- coding: utf-8 -*-
"""WhatsApp files nobody could match to a claim - kept, never lost, sorted by a person.

Until 30 Sep a file sent to our WhatsApp number from a number that is not a complainant on a
claim - a subscriber, an Authorized Partner, a staff member forwarding a customer's papers, a
stranger - was thrown away: staff got a bell saying a file had come, and there was no file.

Now every such file is downloaded, virus-scanned and KEPT here as "to sort", with who sent it.
A person with WhatsApp duty attaches it to the right claim (one tap) or sets it aside - never
deletes it.

Staff forwarding (founder, 1 Oct: "forwarding should be allowed from any staff number"): a staff
member's own number sends the customer's file with the claim number in the caption - "NP-1050" -
and it is filed on that claim straight away, IF that staff member may work on that claim (the
same rule as the claim screen). Anything else from a staff number goes to "to sort" like the rest.

Fails CLOSED: a file the virus scanner cannot clear is not stored - its Meta id is kept, so a
person can fetch it again, and staff are told. Files from strangers are the ones that need it most.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.wa.unsorted")
DB_PATH = db.DB_PATH
MAX_BYTES = 25 * 1024 * 1024
NP_RE = re.compile(r"\bNP[-\s#]?0*(\d{1,6})\b", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS nidaan_wa_unsorted (
    item_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    msisdn         TEXT NOT NULL,
    sender_role    TEXT NOT NULL DEFAULT '',
    sender_name    TEXT NOT NULL DEFAULT '',
    wamid          TEXT NOT NULL DEFAULT '',
    media_id       TEXT NOT NULL DEFAULT '',
    mime           TEXT NOT NULL DEFAULT '',
    filename       TEXT NOT NULL DEFAULT '',
    caption        TEXT NOT NULL DEFAULT '',
    stored_name    TEXT NOT NULL DEFAULT '',
    size           INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'to_sort',   -- to_sort | attached | set_aside | not_stored
    reason         TEXT NOT NULL DEFAULT '',
    claim_id       INTEGER,
    decided_by     INTEGER,
    decided_name   TEXT NOT NULL DEFAULT '',
    decided_at     TIMESTAMP,
    received_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_waunsorted_status ON nidaan_wa_unsorted(status, item_id);
"""


class SortError(Exception):
    """A refusal, in words the person can act on."""


def _ext(mime: str, filename: str) -> str:
    m = (mime or "").lower()
    if "pdf" in m:
        return ".pdf"
    if "png" in m:
        return ".png"
    if "jpe" in m or "jpg" in m:
        return ".jpg"
    f = (filename or "").lower()
    for e in (".pdf", ".png", ".jpg", ".jpeg"):
        if f.endswith(e):
            return ".jpg" if e == ".jpeg" else e
    return ".bin"


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9 ._()-]", "", (name or "").strip())[:90].strip(" .") or "document"


async def _conn():
    c = await aiosqlite.connect(DB_PATH)
    c.row_factory = aiosqlite.Row
    await c.executescript(SCHEMA)
    return c


async def _insert(**kw) -> int:
    c = await _conn()
    try:
        cols = ", ".join(kw)
        cur = await c.execute("INSERT INTO nidaan_wa_unsorted (%s) VALUES (%s)" % (
            cols, ",".join("?" * len(kw))), tuple(kw.values()))
        await c.commit()
        return cur.lastrowid
    finally:
        await c.close()


async def _download_and_scan(media_id: str) -> tuple[Optional[bytes], str, str]:
    """(bytes, mime, why_not). bytes is None when the file must not be stored."""
    import biz_nidaan_whatsapp as _wa
    dl = await _wa.download_media(media_id)
    if not dl.get("ok"):
        return None, "", "could not be downloaded from WhatsApp (%s)" % (dl.get("error") or "error")
    data = dl.get("content") or b""
    if len(data) > MAX_BYTES:
        return None, dl.get("mime") or "", "too large (over 25 MB)"
    try:
        import biz_av_scan as _av
        allowed, why = await _av.scan_bytes(data)
    except Exception as e:  # noqa: BLE001 - no verdict means not stored
        logger.error("virus scan unavailable for a WhatsApp file: %s", type(e).__name__)
        return None, dl.get("mime") or "", "the virus check could not run - not stored, ask again later"
    if not allowed:
        return None, dl.get("mime") or "", "refused by the virus check (%s)" % (why or "unsafe")
    return data, dl.get("mime") or "", ""


DAILY_PER_NUMBER = 30


async def _kept_today(msisdn: str) -> int:
    c = await _conn()
    try:
        r = await (await c.execute("SELECT COUNT(*) FROM nidaan_wa_unsorted WHERE msisdn=? AND stored_name<>'' "
                                   "AND received_at >= datetime('now','-1 day')", (msisdn,))).fetchone()
        return int(r[0]) if r else 0
    finally:
        await c.close()


async def keep(msisdn: str, media_id: str, mime: str, *, filename: str = "", caption: str = "",
               wamid: str = "", sender_role: str = "", sender_name: str = "") -> dict:
    """Keep a file nobody matched. Returns {item_id, status, reason}."""
    if await _kept_today(msisdn) >= DAILY_PER_NUMBER:
        # A number sending more than this in a day is not filing a claim; the Meta id is kept
        # so a person can still fetch any of them.
        why = "more than %d files from this number today - not stored" % DAILY_PER_NUMBER
        item = await _insert(msisdn=msisdn, sender_role=sender_role[:20], sender_name=sender_name[:80],
                             wamid=wamid[:120], media_id=media_id[:120], mime=(mime or "")[:80],
                             filename=_safe_name(filename), caption=(caption or "")[:300],
                             status="not_stored", reason=why)
        return {"item_id": item, "status": "not_stored", "reason": why}
    data, real_mime, why = await _download_and_scan(media_id)
    mime = real_mime or mime
    base = dict(msisdn=msisdn, sender_role=sender_role[:20], sender_name=sender_name[:80],
                wamid=wamid[:120], media_id=media_id[:120], mime=mime[:80],
                filename=_safe_name(filename), caption=(caption or "")[:300])
    if data is None:
        item = await _insert(**base, status="not_stored", reason=why[:200])
        return {"item_id": item, "status": "not_stored", "reason": why}
    from biz_nidaan_doc_intake import DOCS_DIR
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex + _ext(mime, filename)
    (DOCS_DIR / stored).write_bytes(data)
    item = await _insert(**base, stored_name=stored, size=len(data), status="to_sort")
    return {"item_id": item, "status": "to_sort", "reason": ""}


def claim_number(caption: str) -> int:
    m = NP_RE.search(caption or "")
    return int(m.group(1)) if m else 0


async def _attach_bytes(claim_id: int, name: str, data: bytes, source: str) -> dict:
    import biz_nidaan as _n
    import biz_nidaan_doc_intake as _intake
    claim = await _n.get_claim_with_account(int(claim_id))
    if not claim:
        raise SortError("NP-%s does not exist." % claim_id)
    res = await _intake.accept(int(claim_id), claim.get("account_id"), [(name, data)],
                               claim_type=claim.get("claim_type") or "", source=source)
    if not res.get("ok"):
        raise SortError("The file could not be opened as a document (%s)." % (res.get("error") or "unreadable"))
    return res


async def staff_forward(staff: dict, msisdn: str, media_id: str, mime: str, *, filename: str = "",
                        caption: str = "", wamid: str = "") -> dict:
    """A staff member forwarded a customer's file. With 'NP-1050' in the caption and the right to
    work on that claim, it is filed there; otherwise it waits in 'to sort'."""
    cid = claim_number(caption)
    who = staff.get("name") or "staff"
    if cid:
        import biz_nidaan_claim_authz as _authz
        ok = (await _authz.assert_claim_access(staff, cid)).get("allowed")
        if ok:
            data, real_mime, why = await _download_and_scan(media_id)
            if data is None:
                item = await _insert(msisdn=msisdn, sender_role="staff", sender_name=who[:80],
                                     wamid=wamid[:120], media_id=media_id[:120], mime=(real_mime or mime)[:80],
                                     filename=_safe_name(filename), caption=(caption or "")[:300],
                                     status="not_stored", reason=why[:200])
                return {"status": "not_stored", "reason": why, "item_id": item, "claim_id": cid}
            name = _safe_name(filename)
            if "." not in name:
                name += _ext(real_mime or mime, filename)
            try:
                await _attach_bytes(cid, name, data, "whatsapp_staff")
            except SortError as e:
                # Not a readable document (a voice note, a video): keep it to sort, never lose it.
                from biz_nidaan_doc_intake import DOCS_DIR
                DOCS_DIR.mkdir(parents=True, exist_ok=True)
                stored = uuid.uuid4().hex + _ext(real_mime or mime, filename)
                (DOCS_DIR / stored).write_bytes(data)
                item = await _insert(msisdn=msisdn, sender_role="staff", sender_name=who[:80],
                                     wamid=wamid[:120], media_id=media_id[:120], mime=(real_mime or mime)[:80],
                                     filename=name, caption=(caption or "")[:300], stored_name=stored,
                                     size=len(data), status="to_sort", reason=str(e)[:200])
                return {"status": "to_sort", "reason": str(e), "item_id": item, "claim_id": cid}
            try:
                import biz_nidaan as _n
                await _n.record_claim_activity(
                    cid, "doc_forwarded", channel="whatsapp", direction="in", actor=who[:80],
                    summary="%s forwarded a document on WhatsApp: %s" % (who, name))
            except Exception:  # noqa: BLE001
                pass
            return {"status": "attached", "claim_id": cid}
    res = await keep(msisdn, media_id, mime, filename=filename, caption=caption, wamid=wamid,
                     sender_role="staff", sender_name=who)
    res["claim_id"] = cid
    res["reason"] = res.get("reason") or ("you are not on NP-%s" % cid if cid else "no claim number in the caption")
    return res


async def attach(item_id: int, claim_id: int, *, staff: dict) -> dict:
    """A person files a kept file on a claim they may work on."""
    import biz_nidaan_claim_authz as _authz
    if not (await _authz.assert_claim_access(staff, int(claim_id))).get("allowed"):
        raise SortError("NP-%s was not found, or you are not on it." % claim_id)
    c = await _conn()
    try:
        r = await (await c.execute("SELECT * FROM nidaan_wa_unsorted WHERE item_id=?", (int(item_id),))).fetchone()
    finally:
        await c.close()
    if not r:
        raise SortError("That file is not in the list.")
    item = dict(r)
    if item["status"] != "to_sort" or not item["stored_name"]:
        raise SortError("That file has already been sorted.")
    from biz_nidaan_doc_intake import DOCS_DIR
    try:
        data = (DOCS_DIR / item["stored_name"]).read_bytes()
    except OSError:
        raise SortError("The stored file is missing - set it aside and ask them to send it again.")
    who = (staff.get("name") or "staff")[:80]
    # Claim the row FIRST: of two people pressing Attach at once, exactly one files it.
    c = await _conn()
    try:
        cur = await c.execute(
            "UPDATE nidaan_wa_unsorted SET status='attaching', claim_id=?, decided_by=?, decided_name=?, "
            "decided_at=CURRENT_TIMESTAMP WHERE item_id=? AND status='to_sort'",
            (int(claim_id), staff.get("staff_id"), who, int(item_id)))
        await c.commit()
    finally:
        await c.close()
    if cur.rowcount != 1:
        raise SortError("That file has already been sorted.")
    name = item["filename"] or "document"
    if "." not in name:
        name += _ext(item["mime"], "")
    try:
        await _attach_bytes(int(claim_id), name, data, "whatsapp")
    except Exception:
        c = await _conn()      # could not file it: back to the list, nothing lost
        try:
            await c.execute("UPDATE nidaan_wa_unsorted SET status='to_sort', claim_id=NULL WHERE item_id=?",
                            (int(item_id),))
            await c.commit()
        finally:
            await c.close()
        raise
    c = await _conn()
    try:
        cur = await c.execute("UPDATE nidaan_wa_unsorted SET status='attached' WHERE item_id=?",
                              (int(item_id),))
        await c.commit()
    finally:
        await c.close()
    try:
        import biz_nidaan as _n
        await _n.record_claim_activity(
            int(claim_id), "doc_sorted", channel="whatsapp", direction="in", actor=who,
            summary="%s filed a WhatsApp file from %s on this claim: %s" % (
                who, item["sender_name"] or ("…" + item["msisdn"][-4:]), name))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": cur.rowcount == 1, "claim_id": int(claim_id)}


async def set_aside(item_id: int, *, staff: dict, reason: str) -> dict:
    """Not for any claim (spam, a duplicate, a selfie). Kept - never deleted - with the reason."""
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise SortError("Say why, in a few words.")
    c = await _conn()
    try:
        cur = await c.execute(
            "UPDATE nidaan_wa_unsorted SET status='set_aside', reason=?, decided_by=?, decided_name=?, "
            "decided_at=CURRENT_TIMESTAMP WHERE item_id=? AND status IN ('to_sort','not_stored')",
            (reason[:200], staff.get("staff_id"), (staff.get("name") or "staff")[:80], int(item_id)))
        await c.commit()
    finally:
        await c.close()
    if cur.rowcount != 1:
        raise SortError("That file has already been sorted.")
    return {"ok": True}


async def listing(status: str = "to_sort", limit: int = 100) -> list[dict]:
    status = status if status in ("to_sort", "attached", "set_aside", "not_stored") else "to_sort"
    # "to sort" includes the files that could not be stored - a person has to see those too.
    wanted = ("to_sort", "not_stored") if status == "to_sort" else (status,)
    c = await _conn()
    try:
        return [dict(r) for r in await (await c.execute(
            "SELECT item_id, msisdn, sender_role, sender_name, mime, filename, caption, stored_name, size, "
            "status, reason, claim_id, decided_name, decided_at, received_at FROM nidaan_wa_unsorted "
            "WHERE status IN (%s) ORDER BY item_id DESC LIMIT ?" % ",".join("?" * len(wanted)),
            (*wanted, int(limit)))).fetchall()]
    finally:
        await c.close()


async def count_to_sort() -> int:
    c = await _conn()
    try:
        r = await (await c.execute("SELECT COUNT(*) FROM nidaan_wa_unsorted WHERE status IN "
                                   "('to_sort','not_stored')")).fetchone()
        return int(r[0]) if r else 0
    finally:
        await c.close()


async def staff_for(msisdn: str) -> Optional[dict]:
    """The ACTIVE staff member whose phone this is, or None."""
    last10 = "".join(ch for ch in (msisdn or "") if ch.isdigit())[-10:]
    if len(last10) != 10:
        return None
    c = await _conn()
    try:
        r = await (await c.execute(
            "SELECT staff_id, name, role FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
            "AND substr(REPLACE(REPLACE(COALESCE(phone,''),' ',''),'-',''), -10)=? LIMIT 1",
            (last10,))).fetchone()
        return dict(r) if r else None
    finally:
        await c.close()


def staff_reply(res: dict) -> str:
    cid = res.get("claim_id")
    if res.get("status") == "attached":
        return "\u2705 Filed on NP-%s. / NP-%s \u092a\u0930 \u0938\u0947\u0935 \u0939\u094b \u0917\u092f\u093e\u0964" % (cid, cid)
    if res.get("status") == "not_stored":
        return ("\u26a0\ufe0f Not saved: %s. Please send it again." % res.get("reason", ""))
    return ("\U0001f4ce Kept in Files to sort (%s). Open WhatsApp \u2192 Files to sort in ops to file it."
            % (res.get("reason") or "not filed"))


def sender_ack(*, staff: bool, lang: str = "hinglish") -> str:
    if staff:
        return ("\U0001f4ce Kept in Files to sort. To file it straight away, write the claim number in "
                "the caption, e.g. NP-1050.")
    return {
        "en": "\U0001f64f Thank you - we have received your file. Our team will add it to the right "
              "case and contact you if anything else is needed.",
        "hi": "\U0001f64f \u0927\u0928\u094d\u092f\u0935\u093e\u0926 - \u0906\u092a\u0915\u0940 \u092b\u093c\u093e\u0907\u0932 \u0939\u092e\u0947\u0902 \u092e\u093f\u0932 \u0917\u0908\u0964 \u0939\u092e\u093e\u0930\u0940 \u091f\u0940\u092e \u0907\u0938\u0947 \u0938\u0939\u0940 \u0915\u0947\u0938 \u092e\u0947\u0902 \u091c\u094b\u0921\u093c \u0926\u0947\u0917\u0940\u0964",
    }.get(lang, "\U0001f64f Dhanyavaad - aapki file humein mil gayi. Hamari team ise sahi case mein jod degi "
                "aur zaroorat hui to aapse sampark karegi.")


_NOTICE_AT: dict = {}


async def notice_due(msisdn: str, minutes: int = 30) -> bool:
    """One staff notice per sender per half hour: eight photos are one event."""
    import time as _t
    now = _t.monotonic()
    if now - _NOTICE_AT.get(msisdn, -1e9) < minutes * 60:
        return False
    _NOTICE_AT[msisdn] = now
    return True
