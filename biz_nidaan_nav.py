# -*- coding: utf-8 -*-
"""Every option in the ops menu, as BLOCKS a person can arrange (founder, 1 Oct 2026).

"Share me a proper layout of superadmin for discussion ... an editable page block by block so that
I can share that page with Nidaan team to arrange it by their own ... once they finalize it we'll
review it and then finalize changes."

This module is the list the Layout Planner (/nidaan/ops/layout-planner) shows, and the list a saved
layout is checked against - a layout can only use blocks that exist. The ops menu itself is still
drawn by buildSidebar in static/nidaan_ops.html; deploy/verify-nav-blocks.py fails the build if the
two lists ever disagree, so the planner never offers a block the menu does not have (or misses one).

`group` is where the block sits TODAY. `what` is one plain sentence a team member can judge it by.
"""
import json
import re

# (block id = ops panel id, label, today's group key, what it is for)
BLOCKS = (
    ("tasks", "✅ Tasks", "work", "Your tasks and the team's: assign, follow up, approve."),
    ("docdesk", "📄 Waiting on documents", "work", "Claims waiting for papers from the complainant, and who is chasing them."),
    ("mybiz", "🚀 My Business", "work", "Your own referral business: your code, link, sign-ups and the claims you raised."),
    ("onbehalf", "🧾 Raise for a Subscriber", "work", "Raise a claim on behalf of an existing subscriber."),
    ("docsplit", "📄 Doc Splitter", "work", "Split a bundle of scanned pages into separate documents."),
    ("l2claims", "📥 L2 Claims - waiting for handover", "line", "Claims reviewed as worth fighting, waiting to be handed to Level-2."),
    ("l2", "⚖️ All open claims + the buckets", "line", "Every open claim on the line, bucket by bucket (Live Cases to Hold), with days in each."),
    ("claims", "📋 All Claims", "claims", "Every claim ever raised - search and filter."),
    ("overview", "📊 Claims Dashboard", "claims", "Counts and charts of claims by stage, type and insurer."),
    ("accounts", "👥 Accounts", "claims", "Subscribers and one-time customers, their plans and payments."),
    ("payfollow", "📞 Payment Follow-up", "claims", "People who reached a payment and did not finish - to call."),
    ("archived", "🗄️ Archived", "claims", "Archived claims - kept, never deleted."),
    ("whatsapp", "💬 WhatsApp", "talk", "The WhatsApp inbox, files to sort, and campaigns."),
    ("support", "🎧 Support chat", "talk", "Website and dashboard chats handed to a person."),
    ("radar", "📨 Email Updates", "talk", "Emails from insurers and authorities about our claims."),
    ("crm", "🎯 CRM", "talk", "Prospects and leads for sales and marketing."),
    ("branches", "🏢 Authorized Partners", "people", "Our partners in each city: details, login, referrals."),
    ("cp", "🤝 Channel Partners", "people", "Channel partners who bring claims to staff."),
    ("staff", "👤 Staff", "people", "Staff accounts, roles and duty."),
    ("leave", "🌴 Leave & WFH", "people", "Apply for and approve leave and work-from-home."),
    ("leavehistory", "📅 Leave History", "people", "Everyone's past leave."),
    ("analytics", "📊 Business Analytics", "insights", "Where customers come from, and where they drop off."),
    ("revenue", "💰 Revenue", "insights", "Money received, by source (owner only)."),
    ("settings", "⚙️ Workflow Settings", "settings", "Office hours, reminders, fees and other switches."),
    ("bdesign", "🧩 Bucket Designer", "settings", "Buckets, their steps and the fields each one records."),
    ("plans", "💳 Plans & Billing", "settings", "Subscription plans and prices."),
    ("content", "📝 Content", "settings", "Words on the website and the facts the chat bot uses."),
    ("telegram", "✈️ Telegram Bot", "settings", "Link your Telegram and set what it tells you."),
    ("health", "🖥️ App Health", "settings", "Is everything working - checks on real outcomes."),
    ("guide", "✨ All Features (Listen)", "settings", "Every feature explained, with audio."),
)

# Today's groups, in order (the planner starts from these; people may rename, add or empty them).
GROUPS = (
    ("work", "My work"),
    ("line", "⚖️ Consolidation"),
    ("claims", "Claims"),
    ("talk", "Customers & conversations"),
    ("people", "People"),
    ("insights", "Insights"),
    ("settings", "Settings & tools"),
)

BLOCK_IDS = tuple(b[0] for b in BLOCKS)
NOT_NEEDED = "not_needed"            # the bin: blocks a proposal says nobody needs
MAX_GROUPS = 15
NAME_MAX = 40
TITLE_MAX = 80
NOTE_MAX = 1000
JSON_MAX = 20000


def blocks() -> list:
    return [{"id": b[0], "label": b[1], "group": b[2], "what": b[3]} for b in BLOCKS]


def current_layout() -> dict:
    """Today's menu as a layout: [{name, blocks:[ids]}] plus the not-needed bin."""
    out = []
    for key, name in GROUPS:
        out.append({"name": name, "blocks": [b[0] for b in BLOCKS if b[2] == key]})
    return {"groups": out, "not_needed": []}


def clean_layout(raw) -> tuple:
    """(layout, error). A layout may only use blocks that exist, each exactly once, and every block
    must be placed somewhere (a group or 'not needed') - so nothing silently falls off the menu."""
    if isinstance(raw, str):
        if len(raw) > JSON_MAX:
            return None, "That layout is too large."
        try:
            raw = json.loads(raw)
        except ValueError:
            return None, "That layout could not be read."
    if not isinstance(raw, dict):
        return None, "That layout could not be read."
    groups = raw.get("groups")
    if not isinstance(groups, list) or not groups or len(groups) > MAX_GROUPS:
        return None, "A layout needs between 1 and %d groups." % MAX_GROUPS
    seen, out = set(), []
    for g in groups:
        if not isinstance(g, dict):
            return None, "That layout could not be read."
        name = re.sub(r"\s+", " ", str(g.get("name") or "")).strip()[:NAME_MAX]
        if not name:
            return None, "Every group needs a name."
        ids = g.get("blocks") or []
        if not isinstance(ids, list):
            return None, "That layout could not be read."
        clean = []
        for i in ids:
            i = str(i)
            if i not in BLOCK_IDS:
                return None, "Unknown block: %s" % i[:30]
            if i in seen:
                return None, "A block appears twice: %s" % i
            seen.add(i)
            clean.append(i)
        out.append({"name": name, "blocks": clean})
    bin_ids = []
    for i in raw.get("not_needed") or []:
        i = str(i)
        if i not in BLOCK_IDS or i in seen:
            return None, "Unknown or repeated block in 'not needed': %s" % i[:30]
        seen.add(i)
        bin_ids.append(i)
    missing = [i for i in BLOCK_IDS if i not in seen]
    if missing:
        return None, "Every block must be placed (missing: %s)." % ", ".join(missing[:5])
    return {"groups": out, "not_needed": bin_ids}, ""


# ── Saved layouts (proposals) ────────────────────────────────────────────────
# One row per person's layout. Nothing is ever deleted: a person withdraws theirs, and choosing
# one marks it - the others stay as the record of what the team suggested.
async def _conn():
    # Imported here, not at the top: the build check reads BLOCKS on a Python without aiosqlite.
    import aiosqlite
    import biz_database as _db
    c = await aiosqlite.connect(_db.DB_PATH)
    c.row_factory = aiosqlite.Row
    await c.execute(
        "CREATE TABLE IF NOT EXISTS nidaan_layout_proposals ("
        " proposal_id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " staff_id INTEGER NOT NULL, staff_name TEXT DEFAULT '',"
        " title TEXT NOT NULL, note TEXT DEFAULT '', layout_json TEXT NOT NULL,"
        " status TEXT DEFAULT 'proposed',"
        " chosen_by TEXT DEFAULT '', chosen_at TIMESTAMP,"
        " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    return c


async def proposals(viewer_id: int) -> list:
    c = await _conn()
    try:
        rows = [dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_layout_proposals WHERE status<>'withdrawn' "
            "ORDER BY (status='chosen') DESC, updated_at DESC LIMIT 100")).fetchall()]
    finally:
        await c.close()
    out = []
    for r in rows:
        try:
            lay = json.loads(r["layout_json"])
        except ValueError:
            continue
        out.append({"proposal_id": r["proposal_id"], "title": r["title"], "note": r["note"],
                    "staff_name": r["staff_name"], "status": r["status"], "updated_at": r["updated_at"],
                    "mine": int(r["staff_id"]) == int(viewer_id or 0), "layout": lay})
    return out


async def save_proposal(staff: dict, title: str, note: str, layout, proposal_id=None) -> dict:
    lay, err = clean_layout(layout)
    if err:
        return {"ok": False, "error": err}
    title = re.sub(r"\s+", " ", title or "").strip()[:TITLE_MAX]
    if not title:
        return {"ok": False, "error": "Give your layout a name."}
    note = (note or "").strip()[:NOTE_MAX]
    sid = int(staff.get("staff_id") or 0)
    if not sid:
        return {"ok": False, "error": "Sign in again."}
    blob = json.dumps(lay, ensure_ascii=False)
    c = await _conn()
    try:
        if proposal_id:
            # Only your own, and only while it is still a proposal - a chosen layout is the record.
            cur = await c.execute(
                "UPDATE nidaan_layout_proposals SET title=?, note=?, layout_json=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE proposal_id=? AND staff_id=? AND status='proposed'",
                (title, note, blob, int(proposal_id), sid))
            if cur.rowcount != 1:
                return {"ok": False, "error": "You can change only your own layout, before it is chosen."}
            pid = int(proposal_id)
        else:
            n = (await (await c.execute(
                "SELECT COUNT(*) FROM nidaan_layout_proposals WHERE staff_id=? AND status<>'withdrawn'",
                (sid,))).fetchone())[0]
            if n >= 5:
                return {"ok": False, "error": "You already have 5 layouts - change one of them instead."}
            cur = await c.execute(
                "INSERT INTO nidaan_layout_proposals (staff_id, staff_name, title, note, layout_json) "
                "VALUES (?,?,?,?,?)", (sid, (staff.get("name") or "")[:80], title, note, blob))
            pid = cur.lastrowid
        await c.commit()
    finally:
        await c.close()
    return {"ok": True, "proposal_id": pid}


async def choose(proposal_id: int, by: str) -> dict:
    c = await _conn()
    try:
        cur = await c.execute(
            "UPDATE nidaan_layout_proposals SET status='chosen', chosen_by=?, chosen_at=CURRENT_TIMESTAMP "
            "WHERE proposal_id=? AND status='proposed'", ((by or "")[:80], int(proposal_id)))
        if cur.rowcount != 1:
            return {"ok": False, "error": "That layout is not open to be chosen."}
        # One chosen layout at a time; an earlier choice goes back to being a proposal.
        await c.execute("UPDATE nidaan_layout_proposals SET status='proposed' "
                        "WHERE status='chosen' AND proposal_id<>?", (int(proposal_id),))
        await c.commit()
    finally:
        await c.close()
    return {"ok": True}
