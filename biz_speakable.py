# -*- coding: utf-8 -*-
"""Text a voice can read aloud - Indian money said as rupees, never dollars.

Founder, 30 Sep: the English voice note said "dollar" instead of rupee. The daily summary handed a
text voice engine "Rs.998.0" (or "₹998", or a "$998" the writing model had invented) with no
Indian context, and an unlocalised English voice read the symbol as dollars.

Every NidaanPartner amount is in Indian rupees, so this module rewrites every money form it can
find - ₹, Rs, Rs., INR, and a bare $ - into words the voice cannot get wrong, in the Indian system:
"₹1,56,48,929" -> "1 crore 56 lakh 48 thousand 929 rupees" (Hindi: "... रुपये"). It also strips
the Markdown, bullets and emoji that voices otherwise read out or stumble on.

biz_tts.cached_wav calls this for every synthesis, so a new voice feature gets it without asking.
"""
from __future__ import annotations

import re

_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_MONEY = [
    re.compile(r"₹\s*" + _NUM),
    re.compile(r"\bINR\s*" + _NUM, re.I),
    re.compile(r"\bRs\.?\s*" + _NUM, re.I),
    re.compile(r"\$\s*" + _NUM),
    re.compile(_NUM + r"\s*(?:rupees?|rs\.?|INR)\b", re.I),
]
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍⭐⭕⌚-⏿]")


def _is_hindi(text: str) -> bool:
    return bool(re.search("[ऀ-ॿ]", text or ""))


def indian_words(n: int, hindi: bool = False) -> str:
    """12345678 -> '1 crore 23 lakh 45 thousand 678' (digits kept inside each group - every voice
    reads 23 or 678 correctly; it is the grouping that goes wrong)."""
    n = int(n)
    if n < 1000:
        return str(n)
    names = (("करोड़", "लाख", "हज़ार") if hindi else ("crore", "lakh", "thousand"))
    parts = []
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, rest = divmod(n, 1000)
    if crore:
        parts.append("%s %s" % (indian_words(crore, hindi), names[0]))
    if lakh:
        parts.append("%d %s" % (lakh, names[1]))
    if thousand:
        parts.append("%d %s" % (thousand, names[2]))
    if rest:
        parts.append(str(rest))
    return " ".join(parts)


def money_words(amount: str, hindi: bool = False) -> str:
    """'1,56,48,929' / '588.82' / '998.0' -> spoken rupees (and paise)."""
    raw = (amount or "").replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return amount
    rupees = int(val)
    paise = int(round((val - rupees) * 100))
    if paise == 100:
        rupees, paise = rupees + 1, 0
    word = "रुपये" if hindi else ("rupee" if rupees == 1 else "rupees")
    out = "%s %s" % (indian_words(rupees, hindi), word)
    if paise:
        out += " %d %s" % (paise, "पैसे" if hindi else "paise")
    return out


def speakable(text: str) -> str:
    """The same message, safe to read aloud."""
    t = text or ""
    hindi = _is_hindi(t)
    for rx in _MONEY:
        t = rx.sub(lambda m: money_words(m.group(1), hindi), t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[*_`#>|]+", "", t)                         # Markdown marks
    t = re.sub(r"(?m)^\s*(?:[-•·]|\d+[.)])\s+", "", t)      # bullets and list numbers
    t = re.sub(r"https?://\S+", "", t)                       # links are never read out
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()
