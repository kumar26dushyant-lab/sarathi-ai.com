# -*- coding: utf-8 -*-
'''Every format a customer sends becomes pages - decided by the bytes; and a name is only a hint.

Founder, 29 Sep: "why we are saying DOC/DOCX support coming? why not we are covering all
formats?" and "if we receive documents like KYC doc is doc name but inside that PDF or Image there
are other two or more documents ... how doc splitter will identify and arrange?"

What these checks defend:

  * the type comes from the file's own BYTES, never its name - a PDF called "photo.jpg" is a PDF,
    and an HTML page called "bill.pdf" is nothing we read;
  * Word, Excel, OpenDocument, RTF and CSV go to the converter; a plain zip never does;
  * a file that cannot be converted is reported with a reason - never a crash, never silence;
  * a one-page file is what its name says; a longer one is CHECKED against its pages, and a
    "KYC" file whose pages are a bill and a discharge summary is MIXED - every page then read on
    its own, so each lands in the right set;
  * the claim screen and the standalone splitter use this one reader.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_doc_formats.py
'''
import asyncio
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import fitz                                         # noqa: E402
import biz_doc_convert as conv                      # noqa: E402
import biz_doc_splitter as split                    # noqa: E402
import biz_nidaan_doc_brain as brain                # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


def pdf_of(*page_texts):
    d = fitz.open()
    for t in page_texts:
        pg = d.new_page()
        y = 80
        for chunk in t.split("   "):
            pg.insert_text((60, y), chunk, fontsize=12)
            y += 22
    b = d.tobytes()
    d.close()
    return b


def zip_of(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, c in files.items():
            z.writestr(n, c)
    return buf.getvalue()


def png():
    d = fitz.open()
    pg = d.new_page(width=200, height=200)
    pg.insert_text((20, 100), "photo", fontsize=20)
    b = pg.get_pixmap().tobytes("png")
    d.close()
    return b


async def main():
    print("\nThe type comes from the bytes\n")
    P = pdf_of("POLICY SCHEDULE   sum insured")
    cases = [
        ("a PDF", P, "pdf"),
        ("a PDF with a few junk bytes first", b"\n\r " + P, "pdf"),
        ("a PNG photo", png(), "image"),
        ("a JPEG header", b"\xff\xd8\xff\xe0" + b"\x00" * 64, "image"),
        ("an iPhone HEIC photo", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64, "heic"),
        ("a Word .docx", zip_of({"[Content_Types].xml": "x", "word/document.xml": "x"}), "office"),
        ("an Excel .xlsx", zip_of({"[Content_Types].xml": "x", "xl/workbook.xml": "x"}), "office"),
        ("an OpenDocument text", zip_of({"mimetype": "application/vnd.oasis.opendocument.text"}), "office"),
        ("an old binary Word / Excel", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "office"),
        ("an RTF letter", b"{\\rtf1\\ansi hello}" + b" " * 20, "office"),
        ("a CSV bill summary", b"item,amount\nroom rent,4000\nmedicine,1200\n", "office"),
    ]
    for label, data, want in cases:
        k, _e = conv.kind_of(data)
        check("%-28s -> %s" % (label, want), k == want, k)
    for label, data in (("a plain zip", zip_of({"a.txt": "x"})),
                        ("an HTML page", b"<html><script>alert(1)</script></html>" + b" " * 8),
                        ("a video", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64),
                        ("random bytes", os.urandom(64))):
        k, _e = conv.kind_of(data)
        check("%-28s -> not a document" % label, k == "", k)
    check("the NAME does not decide: a PDF called photo.jpg is read as a PDF",
          split.normalize_to_pdf([("photo.jpg", P)])[1] == 1)

    print("\nConverting, and saying why when it cannot\n")
    pdf, kind, why = conv.to_pdf(png(), "x.png")
    check("a photo becomes one PDF page", pdf and fitz.open(stream=pdf, filetype="pdf").page_count == 1)
    real = conv.office_to_pdf
    conv.office_to_pdf = lambda data, ext, name="": None
    pdf, kind, why = conv.to_pdf(zip_of({"[Content_Types].xml": "x", "word/document.xml": "x"}), "a.docx")
    check("a Word file that cannot be converted is reported, with a reason",
          pdf is None and kind == "office" and why, (kind, why))
    conv.office_to_pdf = lambda data, ext, name="": pdf_of("FINAL BILL   total amount payable")
    got = split.normalize_with_spans([("bill.xlsx", zip_of({"[Content_Types].xml": "x", "xl/w.xml": "x"})),
                                      ("junk.bin", os.urandom(64)), ("policy.pdf", P)])
    check("an Excel file becomes pages, in order with the others",
          got[1] == 2 and [sp["name"] for sp in got[3]] == ["bill.xlsx", "policy.pdf"], got[1:])
    check("...and the unreadable one is named as skipped", got[2] == ["junk.bin"], got[2])
    conv.office_to_pdf = real

    print("\nA name is a hint, not a verdict\n")
    one = pdf_of("AADHAAR   Government of India   unique identification")
    r = await brain.identify_document(one, [], filename="KYC.pdf")
    check("a one-page file is what its name says", r["doc_type"] == "kyc" and not r["mixed"], r)
    bundle = pdf_of(
        "AADHAAR   Government of India   unique identification",
        "FINAL BILL   total amount payable   room rent   pharmacy   bill number",
        "DISCHARGE SUMMARY   date of admission   final diagnosis   treating doctor")
    r = await brain.identify_document(bundle, [], filename="KYC.pdf")
    check("a 'KYC' file whose pages are a bill and a discharge summary is MIXED",
          r["mixed"] and {"final_bill", "discharge"} & set(r.get("kinds") or []), r)
    same = pdf_of("FINAL BILL   total amount payable   room rent",
                  "FINAL BILL   continued   pharmacy   bill number")
    r = await brain.identify_document(same, [], filename="Hospital Bill.pdf")
    check("a named file whose pages agree stays as named", r["doc_type"] == "final_bill"
          and not r["mixed"], r)

    print("\nOne reader, page by page for a mixed file\n")
    seen = []

    async def prog(done, total):
        seen.append((done, total))
    pages, per_file = await brain.read_files([("KYC.pdf", bundle), ("policy.pdf", P),
                                              ("broken.pdf", b"%PDF-1.4 not really")], [],
                                             progress=prog)
    kyc = [p for p in pages if p["file_index"] == 0]
    check("every page of the mixed file is read on its own",
          [p["source"] for p in kyc] == ["page"] * 3, [p["source"] for p in kyc])
    check("...and lands as what it really is",
          [p["doc_type"] for p in kyc][1:] == ["final_bill", "discharge"],
          [p["doc_type"] for p in kyc])
    check("...and the file is flagged for a person", all(p["mixed"] for p in kyc))
    check("a plain file keeps one answer for all its pages",
          [p["doc_type"] for p in pages if p["file_index"] == 1] == ["policy"])
    check("a broken file is reported, not dropped", per_file[2]["unreadable"] is True, per_file[2])
    check("page numbers run on across files", [p["page"] for p in pages] == [1, 2, 3, 4])
    check("progress is reported after each file", seen[-1] == (3, 3) and len(seen) == 3, seen)

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
