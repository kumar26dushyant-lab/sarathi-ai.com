# -*- coding: utf-8 -*-
"""The splitter's memory: whose job is whose, and what the team has taught it.

Founder, 28 Sep 2026, on how the splitter should work:
  * three sets, built for you, rather than loose files;
  * learning that is **visible rules you can inspect and undo**, not a model that changes its
    mind for reasons nobody can see;
  * an inbox of **three jobs per person**, and the oldest is removed **only with permission**;
  * *"make it simplify and staff to use it rather multiple automations keep staff confused"*.

THREE THINGS THIS FIXES ABOUT THE OLD SPLITTER.

1. A JOB HAD NO OWNER. Anybody holding a job id could open anybody's upload - and an upload here
   is a stranger's hospital file. Jobs now belong to the staff member who made them, and
   `job_for()` fails CLOSED: not yours reads exactly like does not exist, so the id cannot be
   used to find out whose files are on the server.

2. JOBS WERE DELETED ON A TIMER. Six hours after upload the working file was removed, silently,
   whether or not anybody had finished with it. Nothing here deletes. A fourth job asks
   permission to put the oldest away, and "putting away" sets `archived_at`.

3. NOTHING WAS REMEMBERED. Every correction a staff member made was thrown away, so the splitter
   was exactly as wrong on Tuesday as it had been on Monday. A correction now becomes a rule -
   a handful of readable words and the name of who taught it - and a rule always beats the
   engine's own reading, because a person looked at that page and the engine guessed.

RULES ARE WORDS, NOT A SCORE. `biz_nidaan_doc_sets.fingerprint` keeps the distinctive words of
the page, so the rule screen can say *"filed as a rejection letter when at least 4 of these 8
words appear, taught by Asha on 12 October"* - a sentence that is true, and that somebody can
disagree with. A similarity score would be tidier and unarguable, which is the problem.
"""
from __future__ import annotations

import json
import logging

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.doc.store")

# Three at a time, per person. Not a technical limit - a working one. Somebody with nine open
# jobs has lost track of which is which, and the founder asked for three.
MAX_JOBS = 3

# Roles that may open any job, exactly as they may open any claim. Same list as
# biz_nidaan_claim_authz, and for the same reason: a rule that disagrees with itself depending on
# the door you came through is worse than a permissive one.
ORG_WIDE_ROLES = ("super_admin", "sub_super_admin")


def _db() -> str:
    # Resolved at call time, never snapshotted at import - a module that caches DB_PATH keeps
    # writing to the old database after a test repoints it, and passes while proving nothing.
    return db.DB_PATH


# ── jobs ─────────────────────────────────────────────────────────────────────
async def list_jobs(staff_id: int) -> list:
    """This person's open jobs, newest first. Never anybody else's."""
    got = await _list_jobs_or_none(staff_id)
    return got if got is not None else []


async def _list_jobs_or_none(staff_id: int):
    """As list_jobs, but None when the list could not be read - so a check can fail CLOSED."""
    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            rows = await (await c.execute(
                # rowid breaks the tie. created_at has one-second resolution, so three uploads
                # in the same second sort arbitrarily - and the caller takes the LAST row as the
                # oldest, so an arbitrary order meant offering to put away the newest job.
                "SELECT job_id, title, page_count, created_at, opened_at, state, files_total, "
                "files_done, message FROM nidaan_doc_jobs WHERE staff_id=? AND archived_at IS NULL "
                "ORDER BY created_at DESC, rowid DESC", (int(staff_id),))).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("could not list jobs for staff %s: %s", staff_id, e)
        return None


async def room_for_a_job(staff_id: int) -> dict:
    """Is there room for another? If not, name the one we would put away - and ASK.

    Returns {"ok": True} or {"ok": False, "reason": "full", "oldest": {...}, "limit": 3}.

    It does NOT archive anything. The founder was explicit that the oldest goes only with
    permission, so the decision belongs to a screen where somebody presses a button, not to the
    function that noticed the list was full.
    """
    jobs = await _list_jobs_or_none(staff_id)
    if jobs is None:
        # Unreadable is NOT "empty": treating it as room would let the limit be passed whenever
        # the table cannot be read. Refuse, and say why.
        return {"ok": False, "reason": "unavailable", "limit": MAX_JOBS, "open": 0, "oldest": {}}
    if len(jobs) < MAX_JOBS:
        return {"ok": True, "open": len(jobs), "limit": MAX_JOBS}
    return {"ok": False, "reason": "full", "limit": MAX_JOBS,
            "open": len(jobs), "oldest": jobs[-1]}


async def create_job(job_id: str, staff_id: int, title: str, page_count: int) -> bool:
    """Record a job against the person who made it. The PDF itself stays on disk.

    The caller checks `room_for_a_job` first. This does not enforce the limit a second time:
    two checks of one rule is how they drift apart, and the one that matters is the one with a
    person in front of it.
    """
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.execute(
                "INSERT INTO nidaan_doc_jobs (job_id, staff_id, title, page_count) "
                "VALUES (?,?,?,?)",
                (str(job_id), int(staff_id), (title or "")[:120], int(page_count or 0)))
            await c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("could not record job %s: %s", job_id, e)
        return False


async def set_state(job_id: str, state: str, *, files_total=None, files_done=None,
                    message=None, page_count=None, title=None) -> bool:
    """Move a job along: uploading -> reading -> ready | failed. Never deletes anything."""
    if state not in ("uploading", "reading", "ready", "failed"):
        return False
    sets, args = ["state=?", "updated_at=CURRENT_TIMESTAMP"], [state]
    for col, val in (("files_total", files_total), ("files_done", files_done),
                     ("message", message), ("page_count", page_count), ("title", title)):
        if val is not None:
            sets.append("%s=?" % col)
            args.append(val if not isinstance(val, str) else val[:300])
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.execute("UPDATE nidaan_doc_jobs SET %s WHERE job_id=?" % ", ".join(sets),
                            args + [str(job_id)])
            await c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("could not move job %s to %s: %s", job_id, state, e)
        return False


async def job_for(job_id: str, staff_id: int, role: str = "") -> dict | None:
    """The job, if this person may open it. FAILS CLOSED, and says nothing either way.

    A job that is not yours and a job that does not exist return the same None, so the id cannot
    be used to learn whose uploads are on the server - the same rule as claim ids and task ids.
    """
    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            row = await (await c.execute(
                "SELECT * FROM nidaan_doc_jobs WHERE job_id=? AND archived_at IS NULL",
                (str(job_id),))).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("could not read job %s: %s", job_id, e)
        return None                      # unreadable is refused, like every other check here
    if not row:
        return None
    r = dict(row)
    if r.get("staff_id") == int(staff_id) or (role or "") in ORG_WIDE_ROLES:
        return r
    return None


async def touch_job(job_id: str) -> None:
    """Remember when it was last opened, so the inbox can show the stale one first."""
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.execute("UPDATE nidaan_doc_jobs SET opened_at=CURRENT_TIMESTAMP "
                            "WHERE job_id=?", (str(job_id),))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("could not touch job %s: %s", job_id, e)


async def archive_job(job_id: str, staff_id: int, role: str = "") -> bool:
    """Put a job away. Only ever called because somebody pressed a button saying so.

    Archived, not deleted: the working PDF is a copy of a real claimant's documents, and
    "I closed the wrong one" has to be recoverable.
    """
    if not await job_for(job_id, staff_id, role):
        return False                     # not yours, or not there - same answer
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.execute("UPDATE nidaan_doc_jobs SET archived_at=CURRENT_TIMESTAMP "
                            "WHERE job_id=? AND archived_at IS NULL", (str(job_id),))
            await c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("could not archive job %s: %s", job_id, e)
        return False


# ── rules ────────────────────────────────────────────────────────────────────
async def load_rules(limit: int = 500) -> list:
    """Every live rule, in the shape biz_nidaan_doc_sets.apply_rules expects.

    Fails to an EMPTY list, never an exception: no rules means the engine's own reading stands,
    and a splitter that still works is worth more than one that refuses because a table is
    missing. This is what biz_doc_splitter._learned_rules() reaches for.
    """
    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            rows = await (await c.execute(
                "SELECT rule_id, doc_type, words, taught_by FROM nidaan_doc_rules "
                "WHERE archived_at IS NULL ORDER BY rule_id DESC LIMIT ?",
                (int(limit),))).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.info("no rules available (%s) - the engine's own reading stands", e)
        return []
    out = []
    for r in rows:
        d = dict(r)
        try:
            words = json.loads(d.get("words") or "[]")
        except Exception:  # noqa: BLE001
            continue                     # a rule we cannot read is a rule we do not apply
        if not isinstance(words, list) or not words:
            continue
        out.append({"rule_id": d["rule_id"], "doc_type": d["doc_type"],
                    "words": [str(w) for w in words][:12], "taught_by": d.get("taught_by") or ""})
    return out


async def teach(doc_type: str, words: list, taught_by: str, taught_by_id=None) -> int:
    """Remember a correction somebody made. Returns the rule id, or 0.

    Refuses a rule with too few words to be distinctive. Four words is what rule_matches needs to
    fire; a rule built from two would match half the file and quietly mis-file it, which is worse
    than not learning at all.
    """
    words = [str(w).lower() for w in (words or []) if str(w).strip()][:12]
    if not doc_type or len(words) < 4:
        return 0
    try:
        async with aiosqlite.connect(_db()) as c:
            cur = await c.execute(
                "INSERT INTO nidaan_doc_rules (doc_type, words, taught_by, taught_by_id) "
                "VALUES (?,?,?,?)",
                (str(doc_type), json.dumps(words, ensure_ascii=False),
                 (taught_by or "")[:80], taught_by_id))
            await c.commit()
            return int(cur.lastrowid or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("could not store a rule: %s", e)
        return 0


async def list_rules(include_archived: bool = False, limit: int = 200) -> list:
    """What the splitter has been taught, for the screen where a person can disagree with it."""
    q = ("SELECT rule_id, doc_type, words, taught_by, created_at, times_fired, last_fired_at, "
         "archived_at, archived_by FROM nidaan_doc_rules ")
    if not include_archived:
        q += "WHERE archived_at IS NULL "
    q += "ORDER BY rule_id DESC LIMIT ?"
    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            rows = await (await c.execute(q, (int(limit),))).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("could not list rules: %s", e)
        return []
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["words"] = json.loads(d.get("words") or "[]")
        except Exception:  # noqa: BLE001
            d["words"] = []
        out.append(d)
    return out


async def undo_rule(rule_id: int, by: str) -> bool:
    """Turn a rule off. ARCHIVED, not deleted.

    "Why was this page filed as a policy copy?" has to stay answerable after somebody turns the
    rule off, or the next person re-teaches the same wrong thing.
    """
    try:
        async with aiosqlite.connect(_db()) as c:
            cur = await c.execute(
                "UPDATE nidaan_doc_rules SET archived_at=CURRENT_TIMESTAMP, archived_by=? "
                "WHERE rule_id=? AND archived_at IS NULL", ((by or "")[:80], int(rule_id)))
            await c.commit()
            return cur.rowcount > 0
    except Exception as e:  # noqa: BLE001
        logger.warning("could not undo rule %s: %s", rule_id, e)
        return False


async def note_fired(rule_ids: list) -> None:
    """Count what a rule actually does, so the rule screen can show it earning its place.

    A rule that has never fired is either harmless or wrong, and either way somebody should be
    able to see that rather than guess.
    """
    ids = [int(i) for i in (rule_ids or []) if str(i).isdigit() or isinstance(i, int)]
    if not ids:
        return
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.executemany(
                "UPDATE nidaan_doc_rules SET times_fired=times_fired+1, "
                "last_fired_at=CURRENT_TIMESTAMP WHERE rule_id=?", [(i,) for i in ids])
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("could not record rule firings: %s", e)
