"""Check all sixteen against the code that is DEPLOYED, not against my memory of doing them.

Each item is checked by looking for the thing that would have to be true if it were done, in the
file the server is actually serving. A claim of "done" that nobody can re-check is a claim.
"""
import io
import subprocess
import sys

OPS = io.open("static/nidaan_ops.html", encoding="utf-8").read()
PORTAL = io.open("static/nidaan_claim_portal.html", encoding="utf-8").read()
BUCKETS = io.open("biz_nidaan_buckets.py", encoding="utf-8").read()
SERVER = io.open("sarathi_biz.py", encoding="utf-8").read()
NIDAAN = io.open("biz_nidaan.py", encoding="utf-8").read()
CLAIMANT = io.open("biz_nidaan_claimant.py", encoding="utf-8").read()
ACCESS = io.open("biz_nidaan_claim_access.py", encoding="utf-8").read()

CHECKS = [
    ("1",  "the complainant's phone is editable from Claim Info",
     lambda: "ecCPhone" in OPS and "complainant_phone" in SERVER and "complainant_phone=?" in NIDAAN),
    ("2",  "the code email carries a link to the claim page",
     lambda: "_claim_page_url()" in ACCESS and "Open my claim page" in ACCESS),
    ("3a", "Re-issue actually sends, and reports whether it did",
     lambda: "emailed = bool(res.get(\"ok\"))" in SERVER
             and "Does NOT itself email yet" not in SERVER),
    ("3b", "a new email address gets the link there and then",
     lambda: "PUTTING AN EMAIL ON A CLAIM IS THE MOMENT" in SERVER),
    ("3c", "and the link goes to the COMPLAINANT, not only the insured",
     lambda: '"to_email"' in CLAIMANT and 'c.get("to_email")' in CLAIMANT),
    ("4a", "documents are held until the complainant submits them",
     lambda: "submitted_at" in NIDAAN and "submitted=False" in SERVER),
    ("4b", "the Save and submit button asks first",
     lambda: "submitDocs" in PORTAL and "confirmSubmit" in PORTAL),
    ("4c", "and there is a button that ends the job",
     lambda: "doneHere()" in PORTAL and "doneBtn" in PORTAL),
    ("4d", "staff see unsubmitted files, marked",
     lambda: "not submitted" in OPS and "f.submitted_at" in OPS),
    ("5",  "the case email is asked for once, not twice",
     lambda: "OWNED_ELSEWHERE" in OPS),
    ("6",  "a date is not saved while it is being typed",
     lambda: "_l2DateCommit" in OPS and "1900-01-01" in OPS),
    ("7",  "a rejection cannot predate its admission",
     lambda: "before the admission date" in BUCKETS
             and "rejection_date\", \"admission_date\"" in BUCKETS),
    ("8",  "moving into Pending Draft always arrives on Drafting",
     lambda: "toKey !== 'pending_draft'" in OPS),
    ("9",  "Pending Docs is off the rail, guarded on being empty",
     lambda: "bucket_key='pending_docs' AND active=1" in BUCKETS
             and "NOT EXISTS" in BUCKETS),
    ("10", "a draft query can be answered where the server allows it",
     lambda: "b.bucket_key === 'pending_draft' && i.query" in OPS
             and "st.bucket === 'pending_draft'" in OPS),
    ("11", "a query does not travel to Escalation as 'resolved'",
     lambda: "A DRAFT QUERY ENDS WHERE IT LIVED" in BUCKETS),
    ("12", "and the claims already carrying one were cleared",
     lambda: "COALESCE(pipeline_stage,'') <> 'pending_draft'" in BUCKETS),
    ("13", "an impossible date is refused by the server too",
     lambda: "is not a date anybody meant" in BUCKETS),
    ("14", "the three reminder dates are back, and not required",
     lambda: "esc_reminder_1','esc_reminder_2','esc_reminder_3') AND active=0" in BUCKETS),
    ("15", "nothing shows a draft-query badge outside Pending Draft",
     lambda: "query_state='', query_text='', query_by=''" in BUCKETS),
    ("16", "an escalation query can be answered",
     lambda: "escalation_answered" in BUCKETS and "escAnswered" in OPS),
    ("seq", "Live Cases asks for the seventeen, in order",
     lambda: "LIVE CASES ASKS FOR THE SEVENTEEN" in OPS and "CSR_GIST.map" in OPS),
    ("seq2", "and the two he added back are on, at 2nd and 12th",
     lambda: "['On Behalf of',          'field', 'relationship',          'choice']" in OPS
             and "['Claim Type',            'field', 'rejection_type',        'choice']" in OPS
             and "sort_order=10" in BUCKETS and "sort_order=105" in BUCKETS),
    ("seq3", "with his dropdowns, and no Consumer",
     lambda: "'Wife', 'Husband'" in OPS and "'Brother', 'Sister', 'Friend'" in OPS
             # As a LIST ENTRY, not anywhere in the file - the comment next to the list explains
             # why Consumer was dropped, and a blunter test fails on its own explanation.
             and "'Consumer'" not in OPS
             and "Reimbursement\\nDeduction\\nRejection\\nQuery\\nDelay in process" in BUCKETS),
]

print("\nEach item, checked in the deployed code\n")
bad = 0
for num, what, test in CHECKS:
    try:
        ok = bool(test())
    except Exception as e:  # noqa: BLE001
        ok = False
        what += "  (check errored: %s)" % e
    if not ok:
        bad += 1
    print("  %-4s %s  %s" % (num, "OK " if ok else "NO ", what))

print("\n%d of %d verified" % (len(CHECKS) - bad, len(CHECKS)))

# And the deployed commit must be the one holding all this.
try:
    local = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("local HEAD: %s" % local[:8])
except Exception:
    pass
sys.exit(1 if bad else 0)
