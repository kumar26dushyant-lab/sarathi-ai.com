# -*- coding: utf-8 -*-
"""One document limit, everywhere (3 Oct 2026).

Fails the build if:
  * static/nidaan_limits.js and biz_nidaan_limits.py disagree on a number;
  * the scanner ceiling is not above the document limit (a file the scanner cannot finish is
    refused, so the app would promise what it cannot do);
  * a document door still carries its own size number instead of reading biz_nidaan_limits /
    NidaanLimits - the "25 MB in ten places" that let a file pass one door and fail the next;
  * a Nidaan page that uploads documents does not load nidaan_limits.js.

    py -3.13 deploy/verify-limits.py
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")   # the messages carry Hindi; a Windows console is cp1252
except Exception:  # noqa: BLE001
    pass
import biz_nidaan_limits as L  # noqa: E402

bad = []
js = io.open(os.path.join(ROOT, "static", "nidaan_limits.js"), encoding="utf-8").read()


def js_num(name):
    m = re.search(name + r"\s*:\s*(\d+)\s*(\*\s*MB)?", js)
    if not m:
        return None
    return int(m.group(1)) * (L.MB_DEC if m.group(2) else 1)


for name, want in (("docMaxMB", L.DOC_MAX_MB), ("docMaxBytes", L.DOC_MAX_BYTES),
                   ("requestMaxBytes", L.REQUEST_MAX_BYTES)):
    got = js_num(name)
    if got != want:
        bad.append("nidaan_limits.js %s = %r, server says %r" % (name, got, want))
if not (L.SCAN_MAX_BYTES > L.DOC_MAX_BYTES and L.REQUEST_MAX_BYTES >= L.DOC_MAX_BYTES):
    bad.append("the scanner / request ceilings must sit above the document limit")
if L.REQUEST_MAX_BYTES >= 100 * L.MB_DEC:
    bad.append("a request at or over 100 MB is refused by Cloudflare")

# Document doors that must read the shared limit, not carry their own number.
DOORS = {
    "sarathi_biz.py": [r"_MAX_DOC_SIZE\s*=\s*\d", r"_MAX_UPLOAD_BATCH_BYTES\s*=\s*\d",
                       r"len\(b\)\s*>\s*30\s*\*\s*1024"],
    "biz_doc_splitter.py": [r"MAX_FILE_MB\s*=\s*\d"],
    "biz_nidaan_wa_unsorted.py": [r"MAX_BYTES\s*=\s*\d"],
    "biz_av_scan.py": [r"_MAX_SCAN_BYTES\s*=\s*\d"],
    "biz_nidaan_doc_intake.py": [r"MAX_MEMBER_BYTES\s*=\s*\d"],
    "biz_nidaan_radar.py": [r"_ATTACH_MAX_BYTES\s*=\s*\d"],
    "biz_nidaan_bot_guard.py": [r"MAX_FILE_BYTES\s*=\s*\d"],
    "biz_nidaan_capabilities.py": [r"up to 25 MB", r"25 MB तक", r"\(30 MB each\)"],
}
for f, pats in DOORS.items():
    t = io.open(os.path.join(ROOT, f), encoding="utf-8").read()
    for p in pats:
        if re.search(p, t):
            bad.append("%s still sets its own size: /%s/" % (f, p))

# Pages: no hard-coded document size hints or checks; and the limits file is loaded where used.
PAGE_JS = ["nidaan_intake.js", "nidaan_partner_claims.js"]
for f in sorted(glob.glob(os.path.join(ROOT, "static", "nidaan_*.html"))) + [os.path.join(ROOT, "static", x) for x in PAGE_JS]:
    t = io.open(f, encoding="utf-8").read()
    n = os.path.basename(f)
    for p in (r"(?<![\w.])(10|25|30)\s*MB(?! तक में)", r"(25|30)\s*MB तक", r"(25|30)MB",
              r"size\s*>\s*(25|30)\s*\*\s*1024\s*\*\s*1024", r"_MBC_MAXSIZE\s*=\s*\d", r"_MBC_BATCH_BYTES\s*=\s*\d"):
        if re.search(p, t):
            bad.append("%s carries its own document size (/%s/) - use NidaanLimits" % (n, p))
    # A number written into the page as a placeholder must BE the limit.
    for m in re.finditer(r"data-nd-docmax>(\d+)<", t):
        if int(m.group(1)) != L.DOC_MAX_MB:
            bad.append("%s says %s MB where the limit is %d" % (n, m.group(1), L.DOC_MAX_MB))
    uses = ("NidaanLimits" in t or "/static/nidaan_intake.js" in t or "/static/nidaan_partner_claims.js" in t)
    if uses and n.endswith(".html") and "/static/nidaan_limits.js" not in t:
        bad.append("%s uploads documents but does not load /static/nidaan_limits.js" % n)

for b in bad:
    print("  FAIL ", b)
print("  OK   one document limit everywhere: %d MB (scanner %d MB, request %d MB)"
      % (L.DOC_MAX_MB, L.SCAN_MAX_BYTES // L.MB, L.REQUEST_MAX_BYTES // L.MB_DEC) if not bad
      else "%d problem(s)" % len(bad))
sys.exit(1 if bad else 0)
