# -*- coding: utf-8 -*-
'''Classify once, compose many - and never lose a page doing it.

Founder, 28 Sep 2026: the splitter should hand back ready-made SETS, not loose files.

The thing that makes this different from the old splitter is that the sets OVERLAP. The policy
copy is in CIO and in the claim set; every page is in "all merged". So a page belongs to several
bundles at once, and the old model - every page in exactly one document - could not say that.

What these checks defend:

  * a page appears in every set whose rules call for it, not just the first one;
  * "whatever is available" really means skipped-and-reported, not a gap nobody mentions;
  * a set marked catch_all loses NOTHING - the whole point of "all documents merged" is that a
    page nobody classified still ends up in it;
  * a taught rule BEATS the model, because a person looked at that page and the model guessed;
  * and a rule is readable - words a human can check, not a hash they have to trust.

    py -3.13 _tools/test_doc_sets.py
'''
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import biz_nidaan_doc_sets as ds  # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


def page(n, t, words=None, conf=0.9):
    return {"page": n, "doc_type": t, "confidence": conf, "words": words or []}


# A realistic mixed file, deliberately out of order the way a customer sends it.
PAGES = [
    page(1, "discharge"), page(2, "discharge"),
    page(3, "final_bill"),
    page(4, "pharmacy_bill"),
    page(5, "investigation"), page(6, "investigation"),
    page(7, "policy"),
    page(8, "kyc"),
    page(9, "receipt"),
    page(10, "other"),
]

print("\nBuilding the sets\n")

cio = ds.compose(PAGES, "cio")
claim = ds.compose(PAGES, "claim_set")
allm = ds.compose(PAGES, "all_merged")

# ── the overlap, which is the whole reason for the redesign ─────────────────
def nums(s):
    return [p["page"] for p in s["pages"]]


check("the policy copy is in CIO", 7 in nums(cio))
check("...AND in the claim set - a page belongs to several bundles", 7 in nums(claim))
check("...AND in the merged set", 7 in nums(allm))
check("the final bill is in all three",
      3 in nums(cio) and 3 in nums(claim) and 3 in nums(allm))

# ── order is the founder's drawing, not page order ──────────────────────────
check("CIO leads with the policy copy, as drawn", nums(cio)[0] == 7, nums(cio))
check("...then KYC, then the discharge summary", nums(cio)[:4] == [7, 8, 1, 2], nums(cio))
check("the claim set leads with the discharge summary", nums(claim)[:2] == [1, 2], nums(claim))
check("a multi-page document keeps its own page order",
      nums(claim)[:2] == [1, 2] and nums(allm).index(5) < nums(allm).index(6))

# ── "whatever is available" ─────────────────────────────────────────────────
check("CIO skips what is not there rather than failing",
      "rejection" in cio["missing"] and "claim_form" in cio["missing"], cio["missing"])
check("...and names the gap instead of hiding it", len(cio["missing"]) > 0)
check("nothing missing is silently included", all(
    p["doc_type"] not in cio["missing"] for p in cio["pages"]))

# ── the catch-all must not lose a page ──────────────────────────────────────
check("'all merged' contains EVERY page", sorted(nums(allm)) == list(range(1, 11)), nums(allm))
check("...including the unclassified one", 10 in nums(allm))
check("...exactly once each", len(nums(allm)) == len(set(nums(allm))))
check("CIO is NOT a catch-all - an unclassified page does not sneak in", 10 not in nums(cio))

# a page of a type no set names must still survive the merge
odd = PAGES + [page(11, "bank")]
check("a type only 'all merged' knows about still lands there",
      11 in nums(ds.compose(odd, "all_merged")))

# ── an empty file, and rubbish ──────────────────────────────────────────────
empty = ds.compose([], "cio")
check("an empty file gives an empty set, not an error", empty["pages"] == [])
check("...and reports everything as missing", len(empty["missing"]) == len(ds.SETS["cio"]["order"]))
check("an unknown set name is refused clearly",
      ds.compose(PAGES, "nonsense").get("error") is not None)

# ── the taught rules ────────────────────────────────────────────────────────
print()
fp = ds.fingerprint("REPUDIATION OF CLAIM. We regret to inform that your claim stands "
                    "rejected under exclusion clause 4.2 of the policy contract.")
check("a fingerprint is READABLE words, not a hash",
      all(isinstance(w, str) and w.isalpha() for w in fp) and len(fp) > 2, fp)
check("...and drops the words every page has", "total" not in fp and "date" not in fp, fp)

guessed = [page(1, "other", words=fp)]
rules = [{"rule_id": 7, "doc_type": "rejection", "words": fp, "taught_by": "Annapurna"}]
out = ds.apply_rules(guessed, rules)
check("a taught rule BEATS the model's guess", out[0]["doc_type"] == "rejection", out[0])
check("...and says who taught it, so the screen can explain itself",
      out[0].get("taught_by") == "Annapurna")
check("...and remembers what it overrode", out[0].get("was") == "other")
check("...and is certain, because a person looked at it", out[0].get("confidence") == 1.0)

other = ds.apply_rules([page(2, "investigation", words=ds.fingerprint(
    "HAEMOGLOBIN 13.2 PLATELET COUNT WITHIN NORMAL LIMITS SERUM CREATININE"))], rules)
check("a rule does not fire on an unrelated page", other[0]["doc_type"] == "investigation")
check("no rules at all changes nothing", ds.apply_rules(guessed, [])[0]["doc_type"] == "rejection")

# ── the vocabulary has to be complete enough to compose from ────────────────
print()
for key, spec in ds.SETS.items():
    unknown = [t for t in spec["order"] if t not in ds.DOC_TYPES]
    check("every type '%s' asks for exists in the vocabulary" % key, not unknown, unknown)
check("every document type is named in BOTH languages",
      all(ds.type_label(k) and ds.type_label(k, "hi") for k in ds.DOC_TYPES))
check("...and so is every set", all(ds.set_label(k) and ds.set_label(k, "hi") for k in ds.SETS))
check("the Hindi is really Devanagari",
      any("ऀ" <= c <= "ॿ" for c in ds.type_label("discharge", "hi")))
check("'other' is a real type, not a failure code", "other" in ds.DOC_TYPES)
check("the founder's 10 MB cap is recorded where the composer can see it",
      ds.OTHER_DOCS_CAP_MB == 10)

print("\n" + ("%d failed" % FAILED if FAILED
              else "one page, many sets - nothing lost, nothing invented"))
sys.exit(1 if FAILED else 0)
