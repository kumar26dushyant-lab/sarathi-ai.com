# -*- coding: utf-8 -*-
"""WHY IS THIS CLAIM WAITING? (founder, 1-2 Oct 2026)

"In L2 claim section, there is nothing surfacing why a claim is pending, what is needed, what's
missing ... multiple statuses can also be selected for multiple reasons ... make it simple."

Two kinds of reason, shown together as chips on every list and on the case sheet:

  * AUTOMATIC - what we already know, so nobody has to remember to tick it:
        Documents  (how many we have of how many, and - on the case sheet - which are missing)
        L2 fee unpaid
        Authorization sent, not accepted yet
  * TICKED by staff - one or several:
        Query - complainant · Reply - insurer · Our team · Other (in the staff member's own words)

A tick records who and when, so "days waiting" is real. Unticking CLEARS it - the row stays as
history, nothing is deleted.

DOCUMENTS PENDING (founder, 3 Oct: "the most important reason ... a box what all documents pending
automatic populate in that box and editable by staff"). One reason, two sources:
  * automatic while the claim's checklist has required papers missing - the box lists them;
  * staff can write their OWN list (papers the checklist does not name, or a fuller account of
    what is outstanding). Their list is kept with who and when, and shown instead of the
    automatic one. The automatic reason goes only when the papers are ticked received - the
    checklist stays the one truth about which papers we hold.

ONE ANSWER EVERYWHERE (3 Oct). The same reasons, chips and "Waiting on" filter on All Claims,
Level-2 Claims, every bucket, the entry queue and the case board; and the case board's "who owes
the next move" follows what staff ticked here unless somebody set it by hand.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.waits")

# key -> (English, Hindi). The order is the order staff see them in.
REASONS = {
    "docs_pending": ("Documents pending", "दस्तावेज़ बाकी"),
    "query_complainant": ("Query - complainant", "सवाल - शिकायतकर्ता"),
    "insurer_reply": ("Reply - insurer", "जवाब - बीमा कंपनी"),
    "our_team": ("Our team", "हमारी टीम"),
    "other": ("Other", "अन्य"),
}
AUTO = {
    "docs": ("Documents pending", "दस्तावेज़ बाकी"),
    "fee": ("L2 fee unpaid", "L2 फ़ीस बाकी"),
    "auth": ("Authorization not accepted yet", "अनुमति अभी स्वीकार नहीं"),
}
NOTE_MAX = 300
# Reasons that carry the staff member's own words, and how many characters each may hold. The
# documents list is longer: a claim can be short of ten papers.
NOTE_LIMITS = {"other": NOTE_MAX, "docs_pending": 1000}

# Who owes the next move, read from what staff ticked - for the case board. In order: the first
# ticked reason that names someone wins. "Other" names nobody, so it leaves the board's own answer.
WAIT_BLOCKER = (("query_complainant", "complainant"), ("docs_pending", "complainant"),
                ("insurer_reply", "insurer"), ("our_team", "internal"))

# The "Waiting on" filter - one list for every screen. "docs" matches the automatic documents
# reason AND a list staff wrote; "none" finds claims nobody has said anything about.
FILTERS = (
    ("docs", "Documents pending", "दस्तावेज़ बाकी"),
    ("fee", AUTO["fee"][0], AUTO["fee"][1]),
    ("auth", AUTO["auth"][0], AUTO["auth"][1]),
    ("query_complainant",) + REASONS["query_complainant"],
    ("insurer_reply",) + REASONS["insurer_reply"],
    ("our_team",) + REASONS["our_team"],
    ("other",) + REASONS["other"],
    ("none", "Nothing recorded", "कुछ दर्ज नहीं"),
)


def filter_choices() -> list:
    """[{key, label, label_hi}] for the "Waiting on" filter on every list."""
    return [{"key": k, "label": en, "label_hi": hi} for k, en, hi in FILTERS]


def matches(waits: list, key: str) -> bool:
    """Does a claim with these chips match the "Waiting on" filter `key`? Empty key = any."""
    key = (key or "").strip()
    if not key:
        return True
    have = {w.get("key") for w in (waits or [])}
    if key == "none":
        return not have
    if key == "docs":
        return bool(have & {"docs", "docs_pending"})
    return key in have


def blocker_from(keys) -> str:
    """The case board's "who owes the next move" implied by what staff ticked, or ''."""
    keys = set(keys or ())
    for k, who in WAIT_BLOCKER:
        if k in keys:
            return who
    return ""


async def _conn():
    c = await aiosqlite.connect(db.DB_PATH)
    c.row_factory = aiosqlite.Row
    await c.execute(
        "CREATE TABLE IF NOT EXISTS nidaan_claim_waits ("
        " wait_id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL,"
        " reason_key TEXT NOT NULL, note TEXT DEFAULT '',"
        " set_by TEXT DEFAULT '', set_by_id INTEGER, set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        " cleared_by TEXT DEFAULT '', cleared_at TIMESTAMP)")
    await c.execute("CREATE INDEX IF NOT EXISTS idx_claim_waits_open ON nidaan_claim_waits(claim_id, cleared_at)")
    return c


def _days(ts) -> int:
    from datetime import datetime
    try:
        t = datetime.strptime(str(ts)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
        return max(0, (datetime.utcnow() - t).days)
    except Exception:  # noqa: BLE001
        return 0


async def active_many(claim_ids: list) -> dict:
    """{claim_id: [{key, label, label_hi, note, by, at, days, auto: False}]} - what staff ticked."""
    ids = sorted({int(i) for i in claim_ids if i})
    if not ids:
        return {}
    c = await _conn()
    try:
        out: dict = {}
        ph = ",".join("?" * len(ids))
        for r in await (await c.execute(
                "SELECT * FROM nidaan_claim_waits WHERE cleared_at IS NULL AND claim_id IN (%s) "
                "ORDER BY wait_id" % ph, ids)).fetchall():
            en, hi = REASONS.get(r["reason_key"], (r["reason_key"], r["reason_key"]))
            out.setdefault(r["claim_id"], []).append(
                {"key": r["reason_key"], "label": en, "label_hi": hi, "note": r["note"] or "",
                 "by": r["set_by"] or "", "at": str(r["set_at"] or ""), "days": _days(r["set_at"]),
                 "auto": False})
        return out
    finally:
        await c.close()


async def auto_many(rows: list) -> dict:
    """{claim_id: [automatic reasons]} from the claim rows (need claim_id, review_outcome,
    l2_payment_status, payment_status) plus one checklist and one consent read for all of them."""
    ids = sorted({int(r["claim_id"]) for r in rows if r.get("claim_id")})
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    docs: dict = {}
    pushed: set = set()
    async with aiosqlite.connect(db.DB_PATH) as c:
        try:
            for cid, need, have in await (await c.execute(
                    "SELECT claim_id, SUM(CASE WHEN COALESCE(required,1)=1 THEN 1 ELSE 0 END), "
                    "SUM(CASE WHEN COALESCE(required,1)=1 AND COALESCE(received,0)=1 THEN 1 ELSE 0 END) "
                    "FROM nidaan_claim_doc_checklist WHERE claim_id IN (%s) AND removed_at IS NULL "
                    "GROUP BY claim_id" % ph, ids)).fetchall():
                docs[cid] = (int(have or 0), int(need or 0))
        except Exception as e:  # noqa: BLE001 - an older checklist without removed_at
            logger.info("waits: checklist read skipped: %s", e)
        try:
            pushed = {r[0] for r in await (await c.execute(
                "SELECT claim_id FROM nidaan_claimant_portal WHERE claim_id IN (%s) "
                "AND consent_pushed_at IS NOT NULL AND COALESCE(consent_accepted_at,'')=''" % ph,
                ids)).fetchall()}
        except Exception:  # noqa: BLE001
            pass
    import biz_nidaan_buckets as _bk
    out: dict = {}
    for r in rows:
        cid = int(r["claim_id"])
        lst = []
        have, need = docs.get(cid, (0, 0))
        if need and have < need:
            lst.append({"key": "docs", "label": "%s %d of %d" % (AUTO["docs"][0], have, need),
                        "label_hi": "%s %d / %d" % (AUTO["docs"][1], have, need), "auto": True})
        if (r.get("review_outcome") or "") == "can_fight" and not _bk.l2_fee_covered(r):
            lst.append({"key": "fee", "label": AUTO["fee"][0], "label_hi": AUTO["fee"][1], "auto": True})
        if cid in pushed:
            lst.append({"key": "auth", "label": AUTO["auth"][0], "label_hi": AUTO["auth"][1], "auto": True})
        if lst:
            out[cid] = lst
    return out


async def for_rows(rows: list) -> dict:
    """{claim_id: automatic + ticked reasons}, for a list screen."""
    ids = [r["claim_id"] for r in rows if r.get("claim_id")]
    auto = await auto_many(rows)
    manual = await active_many(ids)
    out: dict = {}
    for i in ids:
        a, m = list(auto.get(int(i), [])), list(manual.get(int(i), []))
        # One documents chip, not two: a list staff wrote replaces the automatic one, and keeps
        # the checklist's "x of y" beside it so the count is never lost.
        mdoc = next((x for x in m if x["key"] == "docs_pending"), None)
        adoc = next((x for x in a if x["key"] == "docs"), None)
        if mdoc and adoc:
            mdoc["progress"] = adoc["label"][len(AUTO["docs"][0]):].strip()
            a = [x for x in a if x is not adoc]
        if a or m:
            out[int(i)] = a + m
    return out


async def for_claim(claim_id: int) -> dict:
    """The case sheet's box: the automatic reasons (documents with what is MISSING by name) and
    what is ticked, plus the reasons that can be ticked."""
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        row = await (await c.execute(
            "SELECT claim_id, claim_type, review_outcome, l2_payment_status, payment_status "
            "FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    if not row:
        return {"ok": False}
    row = dict(row)
    auto = (await auto_many([row])).get(int(claim_id), [])
    missing = []
    try:
        import biz_nidaan_doc_checklist as _ck
        missing = [(d.get("en") or d.get("key")) for d in
                   await _ck.pending_required_docs(int(claim_id), row.get("claim_type") or "")]
    except Exception as e:  # noqa: BLE001
        logger.info("waits: missing docs skipped: %s", e)
    for a in auto:
        if a["key"] == "docs":
            a["missing"] = missing
    return {"ok": True, "auto": auto, "ticked": (await active_many([claim_id])).get(int(claim_id), []),
            # What the Documents pending box fills itself with: the checklist's missing papers.
            "docs_missing": missing,
            "note_limits": NOTE_LIMITS,
            "choices": [{"key": k, "label": v[0], "label_hi": v[1]} for k, v in REASONS.items()]}


def _clean_note(text: str, key: str) -> str:
    """One line for 'Other'; the documents list keeps its lines (one paper per line)."""
    lim = NOTE_LIMITS.get(key, NOTE_MAX)
    if key == "docs_pending":
        lines = [re.sub(r"[ \t]+", " ", ln).strip(" \t•-,") for ln in str(text or "").splitlines()]
        return "\n".join(ln for ln in lines if ln)[:lim]
    return re.sub(r"\s+", " ", text or "").strip()[:lim]


async def set_reasons(claim_id: int, keys: list, note: str, staff: dict,
                      notes: Optional[dict] = None) -> dict:
    """Make the ticked reasons exactly `keys`. New ticks are added; unticked ones are CLEARED
    (kept as history). 'Other' needs the staff member's own words; 'Documents pending' needs the
    list of papers. `notes` = {reason: words}; `note` alone still means the words for 'Other'."""
    keys = [k for k in dict.fromkeys(str(k) for k in (keys or []))]
    bad = [k for k in keys if k not in REASONS]
    if bad:
        return {"ok": False, "error": "Unknown reason: %s" % bad[0][:30]}
    notes = {str(k): v for k, v in (notes or {}).items() if str(k) in NOTE_LIMITS}
    if "other" not in notes:
        notes["other"] = note or ""
    words = {k: _clean_note(notes.get(k, ""), k) for k in NOTE_LIMITS}
    note = words["other"]
    if "other" in keys and len(note) < 3:
        return {"ok": False, "error": "Say why in your own words for 'Other'."}
    if "docs_pending" in keys and len(words["docs_pending"]) < 3:
        return {"ok": False, "error": "List the documents still pending."}
    who = (staff.get("name") or "staff")[:80]
    sid = staff.get("staff_id")
    c = await _conn()
    try:
        if not await (await c.execute("SELECT 1 FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone():
            return {"ok": False, "error": "Claim not found."}
        cur = {r["reason_key"]: dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_claim_waits WHERE claim_id=? AND cleared_at IS NULL", (int(claim_id),))).fetchall()}
        added, cleared = [], []
        for k, r in cur.items():
            # Changed words are a new entry: the old list stays as history of what was said when.
            if k not in keys or (k in NOTE_LIMITS and (r.get("note") or "") != words[k]):
                await c.execute("UPDATE nidaan_claim_waits SET cleared_at=CURRENT_TIMESTAMP, cleared_by=? "
                                "WHERE wait_id=?", (who, r["wait_id"]))
                cleared.append(k)
        for k in keys:
            if k not in cur or k in cleared:
                await c.execute("INSERT INTO nidaan_claim_waits (claim_id, reason_key, note, set_by, set_by_id) "
                                "VALUES (?,?,?,?,?)", (int(claim_id), k, words.get(k, ""), who, sid))
                added.append(k)
        await c.commit()
    finally:
        await c.close()
    if added or cleared:
        try:
            import biz_nidaan as _n
            said = ", ".join(REASONS[k][0] + ((": " + words[k].replace("\n", "; ")) if k in NOTE_LIMITS else "")
                             for k in keys) or "nothing"
            await _n.record_claim_activity(int(claim_id), "waiting_on", channel="system", actor=who,
                                           summary="Waiting on: %s" % said[:300])
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "added": added, "cleared": [k for k in cleared if k not in added]}
