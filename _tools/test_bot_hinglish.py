# -*- coding: utf-8 -*-
'''Three languages, and no half-translated screen.

Founder, 26 Sep: *"user choices, hindi, english, hinglish"*, and standing since long before:
everything switches with the selector, no leftover strings.

Hinglish here means Hindi words in ROMAN letters - "Claim ke document bhejein" - because that is
what most of the team types, and it needs no Devanagari keyboard. It is a third variant, not the
Hindi one transliterated by a machine and not English with a few Hindi words dropped in.

The checks that matter are the ones a partial translation would pass:
  - every key carries all three, so the selector can never leave a screen half-changed;
  - no Hinglish string contains Devanagari, which is what happens when somebody copies the Hindi
    entry across "for now";
  - no Hinglish string is simply the English one, which is what happens when somebody runs out
    of patience two-thirds of the way down;
  - the {placeholders} survive, because a lost {id} is a message that says "Task #" and nothing;
  - and a missing string falls back to ENGLISH, never to Devanagari: somebody who chose Hinglish
    because they cannot read that script must never be shown it.

    py -3.14 _tools/test_bot_hinglish.py
'''
import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILED = 0
src = io.open(os.path.join(ROOT, "biz_nidaan_telegram.py"), encoding="utf-8").read()
D = None
for n in ast.walk(ast.parse(src)):
    if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "_BOT_TXT":
        D = ast.literal_eval(n.value)

DEV = re.compile(r"[ऀ-ॿ]")


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


print("\nEnglish, Hindi, Hinglish\n")

check("there are strings at all", bool(D) and len(D) > 140, len(D or {}))
for lang in ("en", "hi", "hinglish"):
    missing = [k for k, v in D.items() if not (v.get(lang) or "").strip()]
    check("every one of the %d keys has %-8s" % (len(D), lang), not missing, missing[:6])

# The two ways a "finished" translation is quietly unfinished.
dev = [k for k, v in D.items() if DEV.search(v["hinglish"])]
check("no Hinglish string is secretly Devanagari copied across", not dev, dev[:6])
# Three are deliberately identical, and each has a reason. Named here rather than softening
# the rule, so the next person sees WHY - and so a fourth one has to be argued for.
SAME_ON_PURPOSE = {
    "menu_title",   # the product's name. NidaanPartner Ops is not translated into anything.
    "b_approve",    # "approve" and "reject" are the words the team already says out loud on
    "b_reject",     # the phone. "Sweekar" would be more Hindi and less understood.
}
same = [k for k, v in D.items()
        if v["hinglish"].strip() == v["en"].strip() and len(v["en"].strip()) > 12
        and k not in SAME_ON_PURPOSE]
check("no Hinglish string is just the English one left behind", not same, same[:6])
check("...and the deliberate exceptions really are still identical, not drifted",
      all(D[k]["hinglish"].strip() == D[k]["en"].strip() for k in SAME_ON_PURPOSE),
      [k for k in SAME_ON_PURPOSE if D[k]["hinglish"].strip() != D[k]["en"].strip()])
check("...and the Hindi is genuinely Devanagari, so it was not skipped either",
      sum(1 for v in D.values() if DEV.search(v["hi"])) > len(D) * 0.8)

# A lost placeholder is a message that says "Task #" and stops.
bad = []
for k, v in D.items():
    want = set(re.findall(r"\{(\w+)\}", v["en"]))
    for lang in ("hi", "hinglish"):
        if set(re.findall(r"\{(\w+)\}", v[lang])) != want:
            bad.append((k, lang))
check("every {placeholder} survives in all three", not bad, bad[:6])

# Markdown that opens and never closes eats the rest of the message.
odd = [(k, lang) for k, v in D.items() for lang in ("en", "hi", "hinglish")
       if v[lang].count("*") % 2]
check("no unclosed *bold* that would swallow the rest of a message", not odd, odd[:6])

# ── the machinery ───────────────────────────────────────────────────────────
print()
check("the bot declares all three", 'LANGS = ("en", "hi", "hinglish")' in src)
check("...spelled the way biz_nidaan_daily_summary already spells it",
      '"hinglish"' in io.open(os.path.join(ROOT, "biz_nidaan_daily_summary.py"),
                              encoding="utf-8").read())
check("...and LANGS is defined BEFORE anything uses it",
      src.index('LANGS = ("en", "hi", "hinglish")') < src.index("lang if lang in LANGS"))
check("an unknown language falls back to English, not to a script they may not read",
      'entry.get(lang if lang in LANGS else "en") or entry.get("en")' in src)
check("a staffer's stored language is validated on the way in",
      'lang = lang if lang in LANGS else "en"' in src)
check("the language button asks instead of toggling", '"lang:set:en"' in src
      and '"lang:set:hi"' in src and '"lang:set:hinglish"' in src)
check("...and refuses a language that is not one of the three",
      "if new_lang not in LANGS:" in src)
check("each language is named in its own script, so you can find yours",
      "Hinglish" in src and "हिंदी" in src)

# ── and the same setting on the web ─────────────────────────────────────────
biz = io.open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
ops = io.open(os.path.join(ROOT, "static", "nidaan_ops.html"), encoding="utf-8").read()
check("the profile endpoint accepts it too - one setting, every door",
      'pattern=r"^(en|hi|hinglish)$"' in biz)
check("...and the profile screen offers it", "setMyLanguage('hinglish')" in ops)

print("\n" + ("%d failed" % FAILED if FAILED
              else "all %d strings in three languages, and nothing half-switched" % len(D)))
sys.exit(1 if FAILED else 0)
