#!/usr/bin/env python3
"""
content_guard.py — fails the build if RETIRED Nidaan content phrases reappear anywhere in the
customer-facing surfaces (marketing pages + the chat knowledge base).

The problem it solves: a business fact often lives in many places (homepage EN + HI, About page,
FAQ, chat KB…). When we change a fact, it's easy to miss a copy. This guard is the safety net — it
scans every customer-facing surface and FAILS (exit 1) if a phrase we've deliberately retired shows
up again, printing exactly where. Run it before deploy (wired into .github/workflows/deploy.yml).

To retire a new phrase: add a (regex, reason) row to BANNED below. Keep it tight to avoid false
positives — only phrases we never want in customer-facing content.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files scanned = the LIVE customer-facing MARKETING surfaces + the AI chat knowledge base, i.e.
# where a retired phrase would be a marketing CLAIM. Intentionally NOT scanned:
#  - nidaan_ops.html / nidaan_dashboard.html: "Ombudsman" there is a FUNCTIONAL claim-status /
#    workflow stage (a real filing forum), not a marketing claim.
#  - nidaan_index_sample.html: a private WIP preview, not live.
# (Revisit this scope if the owner decides process/status labels must also drop "Ombudsman".)
SCAN = [
    "biz_ai.py",                    # chat KB (_NIDAAN_SUPPORT_KB)
    "static/nidaan_index.html",     # live homepage
    "static/nidaan_about.html",     # About page
    "static/nidaan_start.html",     # signup + claim-submit page (customer-facing)
]

# (pattern, human reason). Case-insensitive. Owner rule (Jul 27): the words IRDA/IRDAI, DPDP,
# Lokpal, Ombudsman must NOT appear in customer-facing content → use "(govt) competent authority" /
# "applicable data-protection law". Keep tight to avoid false positives.
BANNED = [
    (r"ombudsman",              'retired — use "competent authority"'),
    (r"लोकपाल",                  'retired — use "सक्षम प्राधिकरण"'),
    (r"\bIRDAI?\b",             'retired — do not name the regulator; use "competent authority"'),
    (r"\bDPDP\b",               'retired — use "applicable data-protection law"'),
    (r"\bLokpal\b",             'retired — use "competent authority"'),
    (r"5\s*[-–]\s*6\s*(months|mo|माह|महीने|महीना)", 'retired — resolution is complexity-based, no fixed timeline'),
    (r"average\s+resolution",   'retired — no average-resolution claim (complexity-based)'),
    (r"avg\.?\s*resolution",    'retired — no average-resolution claim'),
    (r"औसत\s*समाधान",           'retired — no average-resolution claim'),
]

# Lines containing any of these are skipped (none needed now — the solicitation line was removed).
ALLOW_LINE_CONTAINS: list[str] = []

_compiled = [(re.compile(p, re.IGNORECASE), why) for p, why in BANNED]


def _scan_lines(rel: str, text: str):
    """Return [(lineno, line)] to check. For biz_ai.py we scan ONLY the Nidaan customer-facing
    knowledge base constant (_NIDAAN_SUPPORT_KB) — the rest of that file (e.g. the Sarathi
    insurance-advisor AI) legitimately references regulators and is out of scope."""
    lines = text.splitlines()
    if rel.replace("\\", "/").endswith("biz_ai.py"):
        out, capture = [], False
        for i, ln in enumerate(lines, 1):
            if not capture:
                if "_NIDAAN_SUPPORT_KB" in ln and '"""' in ln:
                    capture = True
                continue
            if '"""' in ln:
                break
            out.append((i, ln))
        return out
    return list(enumerate(lines, 1))


def main() -> int:
    hits = []
    for rel in SCAN:
        fp = ROOT / rel
        if not fp.exists():
            continue
        for i, line in _scan_lines(rel, fp.read_text(encoding="utf-8")):
            if any(a in line for a in ALLOW_LINE_CONTAINS):
                continue
            for rx, why in _compiled:
                if rx.search(line):
                    hits.append((rel, i, rx.pattern, why, line.strip()[:120]))
    if hits:
        print("[FAIL] content_guard: retired phrase(s) found in customer-facing content:\n")
        for rel, i, pat, why, snippet in hits:
            print(f"  {rel}:{i}  [{pat}] - {why}")
            try:
                print(f"       ... {snippet}")
            except Exception:
                pass
        print(f"\n{len(hits)} issue(s). Update ALL copies (pages EN+HI + chat KB), then re-run.")
        return 1
    print(f"[OK] content_guard: {len(SCAN)} surfaces clean - no retired phrases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
