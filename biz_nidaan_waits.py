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
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.waits")

# key -> (English, Hindi)
REASONS = {
    "query_complainant": ("Query - complainant", "सवाल - शिकायतकर्ता"),
    "insurer_reply": ("Reply - insurer", "जवाब - बीमा कंपनी"),
    "our_team": ("Our team", "हमारी टीम"),
    "other": ("Other", "अन्य"),
}
AUTO = {
    "docs": ("Documents", "दस्तावेज़"),
    "fee": ("L2 fee unpaid", "L2 फ़ीस बाकी"),
    "auth": ("Authorization not accepted yet", "अनुमति अभी स्वीकार नहीं"),
}
NOTE_MAX = 300


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
    return {int(i): auto.get(int(i), []) + manual.get(int(i), []) for i in ids
            if auto.get(int(i)) or manual.get(int(i))}


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
            "choices": [{"key": k, "label": v[0], "label_hi": v[1]} for k, v in REASONS.items()]}


async def set_reasons(claim_id: int, keys: list, note: str, staff: dict) -> dict:
    """Make the ticked reasons exactly `keys`. New ticks are added; unticked ones are CLEARED
    (kept as history). 'Other' needs the staff member's own words."""
    keys = [k for k in dict.fromkeys(str(k) for k in (keys or []))]
    bad = [k for k in keys if k not in REASONS]
    if bad:
        return {"ok": False, "error": "Unknown reason: %s" % bad[0][:30]}
    note = re.sub(r"\s+", " ", note or "").strip()[:NOTE_MAX]
    if "other" in keys and len(note) < 3:
        return {"ok": False, "error": "Say why in your own words for 'Other'."}
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
            if k not in keys or (k == "other" and (r.get("note") or "") != note):
                await c.execute("UPDATE nidaan_claim_waits SET cleared_at=CURRENT_TIMESTAMP, cleared_by=? "
                                "WHERE wait_id=?", (who, r["wait_id"]))
                cleared.append(k)
        for k in keys:
            if k not in cur or k in cleared:
                await c.execute("INSERT INTO nidaan_claim_waits (claim_id, reason_key, note, set_by, set_by_id) "
                                "VALUES (?,?,?,?,?)", (int(claim_id), k, note if k == "other" else "", who, sid))
                added.append(k)
        await c.commit()
    finally:
        await c.close()
    if added or cleared:
        try:
            import biz_nidaan as _n
            words = ", ".join(REASONS[k][0] + ((": " + note) if k == "other" else "") for k in keys) or "nothing"
            await _n.record_claim_activity(int(claim_id), "waiting_on", channel="system", actor=who,
                                           summary="Waiting on: %s" % words[:300])
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "added": added, "cleared": [k for k in cleared if k not in added]}
