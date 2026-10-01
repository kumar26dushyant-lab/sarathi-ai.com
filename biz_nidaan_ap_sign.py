# -*- coding: utf-8 -*-
"""The Authorized Partner's name on every message about their claims (founder, 1 Oct 2026).

In Tier II/III towns and villages people trust the local person they know. So a claim that came to
us through an Authorized Partner (AP) - raised by them, or by someone who joined with their code or
their shared link - ends every message we send about it with that person's name:

    Rakesh Sharma, Authorized Partner of NidaanPartner.com, Pune (MH)

ONE rule, applied at the two transports (WhatsApp `_post`, email `send_email`), so no message
builder can forget it. Callers only say WHICH claim or account a customer message is about
(`about(...)`); on WhatsApp the claim on the contact is the fallback.

Never on: one-time codes (`unsigned()`), messages to staff or to the AP itself, staff My Business
claims (SP- codes are not APs), a disabled AP, or an AP with no person's name yet - then the usual
team sign-off stays, because half a signature is worse than none. Meta-approved WhatsApp templates
have fixed text and cannot carry it.
"""
import asyncio
import contextlib
import contextvars
import html as _html
import logging
import time
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.ap_sign")

# Indian states and union territories: the code shown in the signature, and the names for the form.
STATES = {
    "AN": ("Andaman and Nicobar Islands", "अंडमान और निकोबार द्वीप समूह"),
    "AP": ("Andhra Pradesh", "आंध्र प्रदेश"),
    "AR": ("Arunachal Pradesh", "अरुणाचल प्रदेश"),
    "AS": ("Assam", "असम"),
    "BR": ("Bihar", "बिहार"),
    "CH": ("Chandigarh", "चंडीगढ़"),
    "CG": ("Chhattisgarh", "छत्तीसगढ़"),
    "DD": ("Dadra and Nagar Haveli and Daman and Diu", "दादरा और नगर हवेली और दमन और दीव"),
    "DL": ("Delhi", "दिल्ली"),
    "GA": ("Goa", "गोवा"),
    "GJ": ("Gujarat", "गुजरात"),
    "HR": ("Haryana", "हरियाणा"),
    "HP": ("Himachal Pradesh", "हिमाचल प्रदेश"),
    "JK": ("Jammu and Kashmir", "जम्मू और कश्मीर"),
    "JH": ("Jharkhand", "झारखंड"),
    "KA": ("Karnataka", "कर्नाटक"),
    "KL": ("Kerala", "केरल"),
    "LA": ("Ladakh", "लद्दाख"),
    "LD": ("Lakshadweep", "लक्षद्वीप"),
    "MP": ("Madhya Pradesh", "मध्य प्रदेश"),
    "MH": ("Maharashtra", "महाराष्ट्र"),
    "MN": ("Manipur", "मणिपुर"),
    "ML": ("Meghalaya", "मेघालय"),
    "MZ": ("Mizoram", "मिज़ोरम"),
    "NL": ("Nagaland", "नागालैंड"),
    "OD": ("Odisha", "ओडिशा"),
    "PY": ("Puducherry", "पुडुचेरी"),
    "PB": ("Punjab", "पंजाब"),
    "RJ": ("Rajasthan", "राजस्थान"),
    "SK": ("Sikkim", "सिक्किम"),
    "TN": ("Tamil Nadu", "तमिलनाडु"),
    "TG": ("Telangana", "तेलंगाना"),
    "TR": ("Tripura", "त्रिपुरा"),
    "UP": ("Uttar Pradesh", "उत्तर प्रदेश"),
    "UK": ("Uttarakhand", "उत्तराखंड"),
    "WB": ("West Bengal", "पश्चिम बंगाल"),
}

PERSON_MAX = 80

# The team sign-offs a message may already end with. The AP line REPLACES the last one - a message
# signed twice reads as two different senders.
SIGNOFFS = tuple(sorted((
    "— Nidaan – The Legal Consultants LLP",
    "— Team NidaanPartner",
    "— NidaanPartner टीम",
    "— Team Nidaan Partner",
    "— Nidaan Partner Team",
    "— Nidaan Team",
    "— NidaanPartner",
), key=len, reverse=True))

_CTX: contextvars.ContextVar = contextvars.ContextVar("nidaan_ap_ctx", default=None)


@contextlib.contextmanager
def about(*, claim_id: Optional[int] = None, account_id: Optional[int] = None, lang: str = ""):
    """Customer messages sent inside this block are about this claim (or account)."""
    tok = _CTX.set({"claim_id": claim_id, "account_id": account_id, "lang": lang or ""})
    try:
        yield
    finally:
        _CTX.reset(tok)


@contextlib.contextmanager
def unsigned():
    """One-time codes and other messages that must carry nobody's name."""
    tok = _CTX.set({"off": True})
    try:
        yield
    finally:
        _CTX.reset(tok)


def current() -> Optional[dict]:
    return _CTX.get()


def task_for_account(account_id: Optional[int], coro):
    """Start a background send about this account (a welcome). A task copies the context at
    creation, so the marker set here travels with it."""
    with about(account_id=account_id):
        return asyncio.create_task(coro)


def clean_state(code: str) -> str:
    c = (code or "").strip().upper()
    return c if c in STATES else ""


def clean_person(name: str) -> str:
    return " ".join((name or "").split())[:PERSON_MAX]


_CACHE: dict = {}
_TTL_S = 60


def _forget() -> None:
    _CACHE.clear()


async def ap_for(*, claim_id: Optional[int] = None, account_id: Optional[int] = None) -> Optional[dict]:
    """The Authorized Partner a claim (or account) came through, if they may sign; else None.

    The claim's own code decides first (an AP-raised claim), then the account's referral code (a
    subscriber who joined with the AP's code or link). Whatever the first REAL AP code says is
    final - an AP that is disabled or has no person's name yet means no AP signature, not a
    fall-through to some other partner.
    """
    if claim_id:
        key = ("c", int(claim_id))
    elif account_id:
        key = ("a", int(account_id))
    else:
        return None
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _TTL_S:
        return hit[1]
    ap = None
    async with aiosqlite.connect(db.DB_PATH) as c:
        if claim_id:
            row = await (await c.execute(
                "SELECT COALESCE(c.branch_code,''), COALESCE(a.branch_code,'') FROM nidaan_claims c "
                "LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id WHERE c.claim_id=?",
                (int(claim_id),))).fetchone()
        else:
            row = await (await c.execute(
                "SELECT COALESCE(branch_code,'') FROM nidaan_accounts WHERE account_id=?",
                (int(account_id),))).fetchone()
        for code in (row or ()):
            code = (code or "").strip().upper()
            if not code or code.startswith("SP-"):      # SP- = a staff member's own business
                continue
            b = await (await c.execute(
                "SELECT branch_code, COALESCE(city,''), COALESCE(contact_person,''), COALESCE(state,''), "
                "COALESCE(contact_email,''), COALESCE(contact_phone,''), COALESCE(status,'') "
                "FROM nidaan_branches WHERE UPPER(branch_code)=?", (code,))).fetchone()
            if not b:
                continue                                 # not an AP code at all
            if b[6] == "active" and clean_person(b[2]):
                ap = {"code": b[0], "city": b[1].strip(), "person": clean_person(b[2]),
                      "state": clean_state(b[3]), "email": (b[4] or "").strip().lower(),
                      "phone": "".join(ch for ch in (b[5] or "") if ch.isdigit())[-10:]}
            break
    _CACHE[key] = (time.monotonic(), ap)
    return ap


def line(ap: dict, lang: str = "en") -> str:
    place = ap.get("city") or ""
    if ap.get("state"):
        place = (place + " (%s)" % ap["state"]).strip()
    tail = (", " + place) if place else ""
    if (lang or "").lower() == "hi":
        return "%s, NidaanPartner.com के अधिकृत पार्टनर%s" % (ap["person"], tail)
    return "%s, Authorized Partner of NidaanPartner.com%s" % (ap["person"], tail)


def sign_text(body: str, sig: str) -> str:
    """Plain text: the AP line replaces a trailing team sign-off, else it is added at the end."""
    if not sig or not body or sig in body:
        return body
    b = body.rstrip()
    for s in SIGNOFFS:
        if b.endswith(s):
            b = b[:-len(s)].rstrip()
            break
    return b + "\n\n— " + sig


def sign_html(body: str, sig: str) -> str:
    """HTML: replace the LAST team sign-off; else put the line before the email footer."""
    if not sig or not body:
        return body
    esc = _html.escape(sig)
    if esc in body or sig in body:
        return body
    for s in SIGNOFFS:
        for v in (s, s.replace("—", "&mdash;"), _html.escape(s)):
            i = body.rfind(v)
            if i >= 0:
                return body[:i] + "— " + esc + body[i + len(v):]
    block = '<p style="margin:16px 0 0">— %s</p>' % esc
    for marker in ('<div class="footer">', "</body>"):
        i = body.rfind(marker)
        if i >= 0:
            return body[:i] + block + "\n" + body[i:]
    return body + "\n" + block


def _lang(lang: str) -> str:
    return "hi" if (lang or "").lower() == "hi" else "en"


async def for_whatsapp(body: str, *, msisdn: str = "", claim_id: Optional[int] = None,
                       lang: str = "", cls: str = "") -> str:
    """Called by biz_nidaan_whatsapp._post for free text. Never raises."""
    try:
        ctx = current() or {}
        if ctx.get("off") or cls in ("business", "consent"):
            return body
        cid = ctx.get("claim_id") or claim_id
        aid = ctx.get("account_id")
        ap = await ap_for(claim_id=cid) if cid else (await ap_for(account_id=aid) if aid else None)
        if not ap:
            return body
        to = "".join(ch for ch in (msisdn or "") if ch.isdigit())[-10:]
        if to and ap.get("phone") and to == ap["phone"]:
            return body                                   # the AP itself, never its own name
        return sign_text(body, line(ap, _lang(ctx.get("lang") or lang)))
    except Exception as e:  # noqa: BLE001 - a signature must never stop a message
        logger.warning("AP signature skipped on WhatsApp: %s", e)
        return body


async def for_email(to_email: str, html_body: str, text_body: str = "") -> tuple:
    """Called by biz_email.send_email when a customer message says what it is about. Never raises."""
    try:
        ctx = current() or {}
        if ctx.get("off") or not (ctx.get("claim_id") or ctx.get("account_id")):
            return html_body, text_body
        ap = await (ap_for(claim_id=ctx["claim_id"]) if ctx.get("claim_id")
                    else ap_for(account_id=ctx["account_id"]))
        if not ap:
            return html_body, text_body
        to = (to_email or "").strip().lower()
        if (ap.get("email") and to == ap["email"]) or to.endswith("@house.nidaanpartner.internal"):
            return html_body, text_body
        sig = line(ap, _lang(ctx.get("lang") or "en"))
        return sign_html(html_body, sig), (sign_text(text_body, sig) if text_body else text_body)
    except Exception as e:  # noqa: BLE001
        logger.warning("AP signature skipped on email: %s", e)
        return html_body, text_body
