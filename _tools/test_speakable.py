# -*- coding: utf-8 -*-
'''Money is said as rupees - never dollars - in every voice note.

Founder, 30 Sep: "in english voice note summary, it's saying dollar instead of rupee, so make sure
this is not happening anywhere else."

    py -3.14 _tools/test_speakable.py
'''
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import biz_speakable as sp  # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail))


s = sp.speakable("Payments received: 2 (Rs.998.0)")
check("'Rs.998.0' becomes '998 rupees'", "998 rupees" in s and "Rs" not in s, s)
s = sp.speakable("Disputed ₹1,56,48,929 in total")
check("₹ with Indian commas becomes crore/lakh words",
      "1 crore 56 lakh 48 thousand 929 rupees" in s, s)
s = sp.speakable("Collected $998 today")
check("a stray $ is said as rupees, never dollars", "rupees" in s and "$" not in s and "dollar" not in s.lower(), s)
s = sp.speakable("Fee ₹588.82 (₹499 + GST)")
check("paise are said", "588 rupees 82 paise" in s and "499 rupees" in s, s)
s = sp.speakable("INR 2000 paid")
check("INR becomes rupees", "2 thousand rupees" in s, s)
s = sp.speakable("आज ₹1,00,000 मिले")
check("in Hindi it says रुपये and लाख", "1 लाख रुपये" in s, s)
s = sp.speakable("*Headline*\n- first point\n• second 🎉\n1. third")
check("Markdown, bullets and emoji are not read out",
      "*" not in s and "•" not in s and "🎉" not in s and "first point" in s, s)
s = sp.speakable("₹1")
check("one rupee is singular", s == "1 rupee", s)
check("small numbers stay as digits", sp.indian_words(999) == "999")
check("an exact lakh", sp.indian_words(100000) == "1 lakh")

src = open("biz_tts.py", encoding="utf-8").read()
body = src[src.index("async def cached_wav"):]
check("every voice note goes through the cleaner (biz_tts.cached_wav)",
      "biz_speakable.speakable(" in body.split("fp = CACHE_DIR")[0])

print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
