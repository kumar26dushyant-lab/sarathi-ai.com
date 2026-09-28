# -*- coding: utf-8 -*-
'''Nobody's upload disappears on a timer any more.

Until 28 Sep every call to save_job() ran a sweep that deleted any job folder older than six
hours - no owner, no record, nobody asked. The folder holds a working copy of a real claimant's
hospital file, so a staff member who came back after lunch found their work gone and no trace of
why. Founder: turn it off.

What these checks defend:

  * saving a new job removes NOTHING, however old the others are. That is the whole change, and
    it is the one a future "just tidy up the temp dir" commit would undo;
  * reclaimable() only ever REPORTS. A screen can show what could be freed; it cannot free it;
  * discard_job_file() refuses a LIVE job even when asked directly - it re-checks the archive
    state itself rather than trusting whoever called it, because a stale screen or a mistyped id
    must not be able to take somebody's evidence;
  * a folder with no job row at all is listed, not assumed to be rubbish. Those are jobs from
    before jobs had owners, and the one time that assumption is wrong it is a real case.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_job_files.py
'''
import asyncio
import io as _io
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                     # noqa: E402
import biz_database as db                            # noqa: E402

_root = tempfile.mkdtemp(prefix="jobfiles_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_doc_splitter as split                     # noqa: E402
split.TMP_ROOT = os.path.join(_root, "docsplit")

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
"""


def age_folder(job, seconds):
    """Make a job folder look old, so a time-based sweep would have taken it."""
    d = os.path.join(split.TMP_ROOT, job)
    old = time.time() - seconds
    for f in os.listdir(d):
        os.utime(os.path.join(d, f), (old, old))
    os.utime(d, (old, old))


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    print("\nSaving a job removes nothing\n")

    old_job = split.save_job(b"%PDF-1.4\nold but somebody is still working on it\n")
    age_folder(old_job, 48 * 3600)                   # two days - well past the old six hours
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute("INSERT INTO nidaan_doc_jobs (job_id, staff_id) VALUES (?,1)", (old_job,))
        await c.commit()

    # The action that used to trigger the sweep.
    new_job = split.save_job(b"%PDF-1.4\nsomebody else's upload\n")

    check("a two-day-old job survives a new upload", split.load_job(old_job) is not None,
          "this is the deletion the founder asked to be turned off")
    check("...and the new one is there too", split.load_job(new_job) is not None)
    check("the old sweep is gone from the module", not hasattr(split, "_cleanup_old"))

    print("\nWhat could be freed is only ever REPORTED\n")

    # old_job is live; new_job has no row at all; make a third that is properly archived.
    done_job = split.save_job(b"%PDF-1.4\nfinished with\n")
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute("INSERT INTO nidaan_doc_jobs (job_id, staff_id, archived_at) "
                        "VALUES (?,1,CURRENT_TIMESTAMP)", (done_job,))
        await c.commit()

    rec = await split.reclaimable()
    names = {r["job"] for r in rec}
    check("a live job is NOT offered up", old_job not in names, sorted(names))
    check("an archived job is offered", done_job in names, sorted(names))
    check("a folder with no job row is listed, not assumed to be rubbish", new_job in names,
          sorted(names))
    check("...and says WHY, so a person can judge",
          all(r.get("why") for r in rec), rec)
    check("...and how much it would free", all(isinstance(r.get("bytes"), int) for r in rec), rec)
    check("reporting removed nothing at all",
          split.load_job(old_job) is not None and split.load_job(done_job) is not None)

    print("\nRemoving one is deliberate, and refuses a live job\n")

    check("a LIVE job cannot be discarded, even asked directly",
          (await split.discard_job_file(old_job)) is False)
    check("...and its file is still there", split.load_job(old_job) is not None,
          "the check must be real, not just a False return")

    check("an archived job can be discarded", (await split.discard_job_file(done_job)) is True)
    check("...and then it is gone", split.load_job(done_job) is None)
    check("discarding it twice is not an error the second time",
          (await split.discard_job_file(done_job)) is False)

    # A path that tries to climb out of the working directory must not reach anything.
    outside = os.path.join(_root, "not_a_job")
    os.makedirs(outside, exist_ok=True)
    _io.open(os.path.join(outside, "keep.txt"), "w").write("x")
    await split.discard_job_file("../not_a_job")
    check("a job id cannot point outside the working directory",
          os.path.exists(os.path.join(outside, "keep.txt")))

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
