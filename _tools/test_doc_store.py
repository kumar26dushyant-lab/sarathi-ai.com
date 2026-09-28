# -*- coding: utf-8 -*-
'''Whose job is whose, and what the splitter has been taught.

Founder, 28 Sep 2026: three jobs per person, the oldest removed **only with permission**, and
learning that is **visible rules you can inspect and undo**.

What these checks defend:

  * a job belongs to somebody. The old splitter had no owner at all, so any staff member holding
    a job id could open any other staff member's upload - and an upload here is a stranger's
    hospital file;
  * "not yours" and "no such job" are indistinguishable, or the id becomes a way to find out
    whose files are on the server;
  * the fourth job does NOT quietly push out the first. It reports that the inbox is full and
    NAMES the one it would put away, and nothing moves until somebody says so;
  * nothing is ever deleted - closing a job and undoing a rule both archive, because "I closed
    the wrong one" has to be recoverable and "why was this filed as a policy copy?" has to stay
    answerable after the rule is turned off;
  * a rule too vague to be distinctive is refused, because a rule built from two common words
    would match half the file and mis-file it, which is worse than not learning at all;
  * and a stored rule beats the engine, which is the entire point of teaching it.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_doc_store.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_dbfile = os.path.join(tempfile.mkdtemp(prefix="docstore_"), "t.db")
db.DB_PATH = _dbfile

import biz_nidaan_doc_store as store                # noqa: E402
import biz_nidaan_doc_sets as sets                  # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_doc_jobs (
    job_id TEXT PRIMARY KEY, staff_id INTEGER NOT NULL, title TEXT NOT NULL DEFAULT '',
    page_count INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    opened_at TIMESTAMP, archived_at TIMESTAMP);
CREATE TABLE nidaan_doc_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT, doc_type TEXT NOT NULL,
    words TEXT NOT NULL DEFAULT '[]', taught_by TEXT NOT NULL DEFAULT '',
    taught_by_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    times_fired INTEGER NOT NULL DEFAULT 0, last_fired_at TIMESTAMP,
    archived_at TIMESTAMP, archived_by TEXT NOT NULL DEFAULT '');
"""

ASHA, RAVI, BOSS = 11, 22, 99


async def main():
    async with aiosqlite.connect(_dbfile) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    # ── jobs belong to somebody ──────────────────────────────────────────────
    print("\nA job belongs to the person who made it\n")

    await store.create_job("j1", ASHA, "Sharma bundle", 12)
    check("Asha can open her own job", bool(await store.job_for("j1", ASHA)))
    check("Ravi CANNOT open Asha's job", (await store.job_for("j1", RAVI)) is None)
    check("...and an admin can, as on every other screen",
          bool(await store.job_for("j1", RAVI, role="super_admin")))

    mine = await store.job_for("j1", RAVI)
    ghost = await store.job_for("no-such-job", RAVI)
    check("'not yours' and 'no such job' are indistinguishable", mine == ghost and mine is None)

    check("Asha's list has it", len(await store.list_jobs(ASHA)) == 1)
    check("Ravi's list does not", len(await store.list_jobs(RAVI)) == 0)

    # ── three at a time, and the fourth ASKS ─────────────────────────────────
    print("\nThe fourth job asks before anything is put away\n")

    await store.create_job("j2", ASHA, "Verma bundle", 4)
    await store.create_job("j3", ASHA, "Khan bundle", 30)
    room = await store.room_for_a_job(ASHA)
    check("three open is full", room["ok"] is False and room["reason"] == "full", room)
    check("...and it NAMES the one it would put away",
          (room.get("oldest") or {}).get("job_id") == "j1", room.get("oldest"))
    check("...but has not put anything away", len(await store.list_jobs(ASHA)) == 3)
    check("...and the oldest is still openable", bool(await store.job_for("j1", ASHA)))

    check("Ravi still has room - the limit is per person",
          (await store.room_for_a_job(RAVI))["ok"] is True)

    # Only now, because somebody pressed the button.
    check("Ravi cannot close Asha's job", (await store.archive_job("j1", RAVI)) is False)
    check("Asha can close her own", (await store.archive_job("j1", ASHA)) is True)
    check("...and then there is room again", (await store.room_for_a_job(ASHA))["ok"] is True)

    # ── nothing is deleted ───────────────────────────────────────────────────
    async with aiosqlite.connect(_dbfile) as c:
        rows = await (await c.execute("SELECT archived_at FROM nidaan_doc_jobs "
                                      "WHERE job_id='j1'")).fetchall()
    check("a closed job is ARCHIVED, not deleted", len(rows) == 1 and rows[0][0] is not None,
          rows)
    check("...and no longer opens", (await store.job_for("j1", ASHA)) is None)

    # ── rules ────────────────────────────────────────────────────────────────
    print("\nWhat the team teaches it\n")

    words = ["repudiated", "admissible", "intimation", "surveyor", "clause", "exclusion"]
    rid = await store.teach("rejection", words, "Asha", ASHA)
    check("a correction becomes a rule", rid > 0)
    check("a rule too vague to be distinctive is refused",
          (await store.teach("rejection", ["the", "and"], "Asha", ASHA)) == 0,
          "two common words would match half the file")
    check("a rule with no type is refused", (await store.teach("", words, "Asha")) == 0)

    live = await store.load_rules()
    check("the engine can load it", len(live) == 1 and live[0]["doc_type"] == "rejection", live)
    check("...and it carries WHO taught it", live[0]["taught_by"] == "Asha", live[0])
    check("...and readable words, not a hash",
          all(isinstance(w, str) and w.isalpha() for w in live[0]["words"]), live[0]["words"])

    # The point of all of it: a taught rule beats the engine's own reading.
    pages = [{"page": 1, "doc_type": "other", "confidence": 0.2,
              "words": ["repudiated", "admissible", "intimation", "surveyor", "policy"]}]
    out = sets.apply_rules(pages, live)
    check("a taught rule overrides the engine", out[0]["doc_type"] == "rejection", out[0])
    check("...and says who taught it, so staff know why", out[0].get("taught_by") == "Asha",
          out[0])
    check("...and remembers what it used to think", out[0].get("was") == "other", out[0])

    # ── undo ─────────────────────────────────────────────────────────────────
    print("\nAnd a person can disagree with it\n")

    check("a rule can be undone", (await store.undo_rule(rid, "Ravi")) is True)
    check("...so the engine stops applying it", len(await store.load_rules()) == 0)
    check("undoing it twice is not an error the second time",
          (await store.undo_rule(rid, "Ravi")) is False)

    archived = await store.list_rules(include_archived=True)
    check("...but the rule is still THERE, with who turned it off",
          len(archived) == 1 and archived[0]["archived_by"] == "Ravi", archived)
    check("...and who had taught it in the first place",
          archived[0]["taught_by"] == "Asha", archived[0])

    # ── counting what a rule actually does ───────────────────────────────────
    rid2 = await store.teach("discharge", ["admission", "diagnosis", "discharged", "treating",
                                           "summary"], "Ravi", RAVI)
    await store.note_fired([rid2])
    await store.note_fired([rid2])
    rules = await store.list_rules()
    fired = next((r for r in rules if r["rule_id"] == rid2), {})
    check("a rule counts how often it has actually fired", fired.get("times_fired") == 2, fired)

    # ── the unreadable cases ─────────────────────────────────────────────────
    print("\nWhen things are not as expected\n")

    async with aiosqlite.connect(_dbfile) as c:
        await c.execute("INSERT INTO nidaan_doc_rules (doc_type, words, taught_by) "
                        "VALUES ('policy','not json at all','X')")
        await c.commit()
    check("a rule we cannot parse is skipped, not crashed on",
          len(await store.load_rules()) == 1, await store.load_rules())

    db.DB_PATH = "/nonexistent/path/nope.db"
    check("an unreadable database gives NO rules rather than an error",
          (await store.load_rules()) == [])
    check("...and refuses to open a job rather than allowing one",
          (await store.job_for("j2", ASHA)) is None)
    db.DB_PATH = _dbfile

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
