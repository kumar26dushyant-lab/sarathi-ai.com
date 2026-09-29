# -*- coding: utf-8 -*-
'''The splitter takes files one at a time and reads them in the background.

29 Sep: uploads took 45 to 247 seconds inside one request; Cloudflare cuts a request at 100 s and
nginx refuses more than 50 MB, so the staffer saw "Could not process the file(s)" for jobs that
had in fact finished - and 40 files of up to 30 MB could never be sent at all.

What these checks defend:

  * files are kept in the order they arrived, stored under a number - never under the sender's
    filename, which is attacker-controlled;
  * a job moves uploading -> reading -> ready | failed, and nothing else;
  * the batch reader is the SAME reader as the claim screen, and a failure ends in "failed" with
    words, never a job stuck on "reading";
  * the routes: size cap, type from the bytes, a virus scan that fails closed, the per-upload
    file limit (40 by default, never above 100, set only by a super-admin), and an interrupted
    read reported so it can be started again;
  * the old one-request upload is no longer what the screen uses.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_docsplit_batch.py
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

_root = tempfile.mkdtemp(prefix="dsbatch_")
os.environ["DOCSPLIT_TMP"] = os.path.join(_root, "docsplit")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

db.DB_PATH = os.path.join(_root, "t.db")

import biz_doc_splitter as split                    # noqa: E402
import biz_nidaan_doc_store as store                # noqa: E402

split.TMP_ROOT = os.environ["DOCSPLIT_TMP"]

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript("""
        CREATE TABLE nidaan_doc_jobs (job_id TEXT PRIMARY KEY, staff_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '', page_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, opened_at TIMESTAMP,
            archived_at TIMESTAMP, state TEXT NOT NULL DEFAULT 'ready',
            files_total INTEGER NOT NULL DEFAULT 0, files_done INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '', updated_at TIMESTAMP);
        """)
        await c.commit()

    print("\nFiles kept in order, under a number\n")
    job = split.new_job_dir()
    split.stage_file(job, 0, "../../etc/passwd", b"first")
    split.stage_file(job, 1, "Final Bill.pdf", b"second")
    split.stage_file(job, 2, "KYC.jpg", b"third")
    got = split.staged_files(job)
    check("three files, in the order they arrived",
          [b for _n, b in got] == [b"first", b"second", b"third"], got)
    check("...with their names kept as text", got[1][0] == "Final Bill.pdf", got)
    on_disk = sorted(os.listdir(os.path.join(split.TMP_ROOT, job, "in")))
    check("...stored under numbers - a hostile name never becomes a path",
          all(re.fullmatch(r"\d{3}\.(bin|name)", f) for f in on_disk)
          and not os.path.exists(os.path.join(_root, "etc")), on_disk)
    check("the count is right", split.staged_count(job) == 3)
    split.save_job_as(job, b"%PDF-1.4 merged")
    check("the merged PDF is saved under the same job", split.load_job(job) == b"%PDF-1.4 merged")

    print("\nA job's state\n")
    await store.create_job(job, 7, "Upload", 0)
    check("uploading", await store.set_state(job, "uploading", files_total=3))
    check("reading, with progress", await store.set_state(job, "reading", files_done=2,
                                                          message="Reading file 2 of 3"))
    row = await store.job_for(job, 7)
    check("...which the screen can show", row["state"] == "reading" and row["files_done"] == 2
          and row["message"] == "Reading file 2 of 3", row)
    check("a state that does not exist is refused", not await store.set_state(job, "deleted"))
    check("ready, with pages", await store.set_state(job, "ready", page_count=5))
    lst = await store.list_jobs(7)
    check("the open-files list carries the state", lst and lst[0]["state"] == "ready", lst)
    check("another person cannot see it", await store.job_for(job, 8) is None)

    print("\nThe routes\n")
    src = io.open("sarathi_biz.py", encoding="utf-8").read()

    def body(name):
        m = re.search(r"async def %s\(.*?(?=\n@app\.|\nclass |\nasync def (?!_prog|_merge))" % name,
                      src, re.S)
        return m.group(0) if m else ""
    f = body("ops_docsplit_batch_file")
    check("a file is refused above the size cap", "MAX_FILE_MB" in f and "len(data) > cap" in f)
    check("...its type comes from the BYTES", "_conv.kind_of(data)" in f)
    check("...it is virus-scanned, and refused when the scan says no", "_av.scan_bytes(data)" in f
          and "did not pass" in f)
    check("...and only while the batch is still taking files", '!= "uploading"' in f)
    check("...never more than the batch expects or the limit allows",
          'files_total' in f and "_docsplit_limit()" in f)
    b = body("ops_docsplit_batch")
    check("opening a batch checks the per-upload limit and the 3-open inbox",
          "_docsplit_limit()" in b and "room_for_a_job" in b)
    st = body("ops_docsplit_batch_start")
    check("reading can start again after an interruption", '("uploading", "failed")' in st)
    stt = body("ops_docsplit_status")
    check("a read that stopped moving is reported as interrupted", "_DS_STALE_MIN" in stt
          and '"failed"' in stt)
    rd = body("_docsplit_read_batch")
    check("the batch uses the SAME reader as the claim screen", "_brain.read_files(" in rd)
    check("...and any failure ends in 'failed' with words", rd.count('set_state(job, "failed"') >= 3)
    lim = body("_docsplit_limit")
    check("files per upload: 40 unless set, never above 100",
          "FILES_DEFAULT" in lim and "FILES_CEILING" in lim and split.FILES_DEFAULT == 40
          and split.FILES_CEILING == 100)
    check("only a super-admin sets the limit",
          '_require_staff(request, "super_admin")' in body("ops_docsplit_settings_save"))
    page = io.open("static/nidaan_ops.html", encoding="utf-8").read()
    check("the screen no longer uses the one-request upload",
          "/nidaan/ops/api/docsplit/upload'" not in page and "'/docsplit/batch'" in page)
    check("...it no longer says 'DOC/DOCX support coming' or 'up to 12 files'",
          "DOC/DOCX support coming" not in page and "up to 12 files" not in page)
    check("...and accepts Word, Excel and iPhone photos",
          all(x in page for x in (".docx", ".xlsx", ".heic")))

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
