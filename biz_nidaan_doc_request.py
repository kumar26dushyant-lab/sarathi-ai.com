"""
NidaanPartner — THE PENDING-DOCUMENT WINDOW.

One screen, one act: a staffer looks at what a claim is still missing, decides who to ask, and
pushes the ask out on WhatsApp and email. Everything here exists to make that act safe, because
it is the one place in the office where a member of staff sends a real customer a list of things
to go and find — and getting it wrong costs the customer a wasted trip.

Four rules carry the module.

1. THE LIST IS PER CLAIM, NOT PER TYPE. `biz_nidaan_doc_checklist` supplies the standard list for
   the claim type; a staffer adds whatever else this case needs and removes what it does not,
   and a removal always carries a reason. Nothing is deleted — a removed row keeps its reason,
   because "why did we stop asking for the FIR?" is a question somebody asks three months later.

2. WE TALK TO THE COMPLAINANT AND COPY EVERYBODY ELSE. The complainant is the person who has the
   documents. The subscriber, the branch, the channel partner and our own staff are copied so
   nobody has to ask us what is happening. Extra numbers and emails can be typed in, and taken
   back out. Every one of them is validated HERE, on the server, not only in the browser.

3. NOTHING GOES OUT UNCHECKED. `preview()` returns exactly what will be sent and to whom, with a
   checksum. `send()` refuses without that checksum. So "check again before you send" is not a
   dialog somebody learns to click through - the server will not send an ask the staffer has not
   actually looked at, and the row it writes records who looked.

4. NUDGING STOPS AND BECOMES A PHONE CALL. Three days, then three days again, and then we stop
   sending and ask a human to pick up the phone. Every nudge carries the line that matters to a
   person who has already sent everything: *if you have already shared all the documents, please
   ignore this message.*

Never raises into a caller: a notification that fails must not undo work that succeeded.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

import aiosqlite

import biz_database as db
import biz_nidaan as _n
import biz_nidaan_doc_checklist as _ck

logger = logging.getLogger("nidaan.docreq")
DB_PATH = db.DB_PATH

# The chase clock. Three days between nudges, and after this many we stop sending and ask a
# person to phone instead - a fourth identical WhatsApp is not persistence, it is noise.
NUDGE_GAP_DAYS = 3
MAX_NUDGES = 2

# The line that has to be in every automatic chase. Somebody who has already sent everything and
# gets nudged anyway concludes we are not reading what they send.
IGNORE_LINE_EN = ("If you have already shared all the required documents, please ignore this "
                  "message.")
IGNORE_LINE_HI = "यदि आप सभी ज़रूरी दस्तावेज़ भेज चुके हैं, तो इस संदेश को नज़रअंदाज़ करें।"


def _digits(v: str) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def valid_phone(v: str) -> str:
    """An Indian mobile or nothing. A number we cannot dial is worse than a blank, because a
    blank is visibly a gap and a wrong number looks like a delivered message."""
    d = _digits(v)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    if len(d) == 11 and d.startswith("0"):
        d = d[1:]
    return d if (len(d) == 10 and d[0] in "6789") else ""


def valid_email(v: str) -> str:
    v = (v or "").strip().lower()
    if "@" not in v or len(v) > 160:
        return ""
    local, _, dom = v.partition("@")
    if not local or "." not in dom or dom.startswith(".") or dom.endswith("."):
        return ""
    if any(ch.isspace() for ch in v) or ".." in v:
        return ""
    return v


async def _claim(claim_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT * FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    return dict(r) if r else None


# ── who the ask goes to ──────────────────────────────────────────────────────
async def recipients(claim_id: int) -> list[dict]:
    """Every channel this claim came through, with the contacts we hold for each.

    The complainant is the TO - they have the documents. Everyone else is a CC, so the branch or
    the partner who introduced the case is not left asking us what is happening. A party we
    cannot reach is still listed, with its gaps named, because an invisible gap is one nobody
    fixes.
    """
    out = []
    try:
        import biz_nidaan_claim_parties as _p
        for party in await _p.get_claim_parties(claim_id):
            role = party.get("role") or ""
            out.append({
                "role": role,
                "label": party.get("label") or role,
                "name": party.get("name") or "",
                "phone": valid_phone(party.get("phone")),
                "email": valid_email(party.get("email")),
                "missing": party.get("missing") or [],
                "kind": "to" if role == "complainant" else "cc",
                "source": "claim",
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("recipients failed for claim %s: %s", claim_id, e)
    return out


def _clean_extras(extras) -> tuple[list[dict], list[str]]:
    """Numbers and emails a staffer typed in. Returns the usable ones and a complaint about each
    one that is not, by position, so the window can point at the offending box."""
    ok, bad = [], []
    for i, x in enumerate(extras or []):
        if not isinstance(x, dict):
            continue
        name = (str(x.get("name") or "").strip())[:80]
        ph = valid_phone(x.get("phone"))
        em = valid_email(x.get("email"))
        raw_ph = (str(x.get("phone") or "")).strip()
        raw_em = (str(x.get("email") or "")).strip()
        if raw_ph and not ph:
            bad.append("%s is not a 10-digit Indian mobile." % raw_ph)
            continue
        if raw_em and not em:
            bad.append("%s is not a valid email address." % raw_em)
            continue
        if not ph and not em:
            bad.append("Row %d has neither a mobile nor an email." % (i + 1))
            continue
        ok.append({"role": "extra", "label": "Added by staff", "name": name, "phone": ph,
                   "email": em, "missing": [], "kind": "cc", "source": "typed"})
    return ok, bad


# ── the message ──────────────────────────────────────────────────────────────
async def _upload_link(claim_id: int) -> str:
    try:
        import biz_nidaan_claimant as _cl
        await _cl.ensure_portal(claim_id, with_token=True)
        p = await _cl.get_portal(claim_id)
        if p and p.get("access_token"):
            return "%s/nidaan/claim/magic?token=%s" % (_cl._public_base(), p["access_token"])
        return _cl._public_base()
    except Exception:
        return ""


# ── the one document that needs explaining ───────────────────────────────────
# Asking somebody for an email password is a big ask, and a bare line on a list reads like a
# phishing message. So whenever this document is asked for, the message says three things: it is
# a NEW account made only for this case, what we use it for, and that they can change the password
# or delete the account the moment the case is over. In their own language, because a person does
# not hand over a password in a language they half-read.
MAIL_ID_NOTE = {
    "en": ("About the email ID: please CREATE A NEW email account for this case — do not give us "
           "your personal one. We write to the insurance company and the authorities from it, and "
           "their replies come back to it, which is why we need the password. It is used for "
           "nothing else. When your case is over you can change the password or delete the "
           "account — it stays yours."),
    "hi": ("ईमेल आईडी के बारे में: कृपया इस केस के लिए एक नई ईमेल आईडी बनाइए — अपनी निजी आईडी मत दीजिए। "
           "हम इसी से बीमा कंपनी और अधिकारियों को पत्र भेजते हैं और उनके जवाब इसी पर आते हैं, इसीलिए "
           "पासवर्ड चाहिए। इसका और कोई उपयोग नहीं होता। केस पूरा होने पर आप पासवर्ड बदल सकते हैं या "
           "आईडी डिलीट कर सकते हैं — वह आपकी ही रहती है।"),
    "hinglish": ("Email ID ke baare mein: is case ke liye ek NAYI email ID banaiye — apni personal "
                 "ID mat dijiye. Hum isi se insurance company aur authorities ko likhte hain aur "
                 "unke jawab isi par aate hain, isliye password chahiye. Iska aur koi upyog nahi "
                 "hota. Case poora hone par aap password badal sakte hain ya ID delete kar sakte "
                 "hain — wo aapki hi rehti hai."),
}


async def _lang_for(claim_id: int, claim: dict) -> str:
    """Which language this complainant reads. Their WhatsApp contact remembers it; if we have
    never spoken, Hinglish is the house default."""
    phone = (claim.get("complainant_phone") or claim.get("insured_phone") or "").strip()
    if not phone:
        return "hinglish"
    try:
        import biz_nidaan_whatsapp as _w
        async with aiosqlite.connect(DB_PATH) as c:
            r = await (await c.execute("SELECT language FROM nidaan_wa_contacts WHERE msisdn=?",
                                       (_w.normalize_msisdn(phone),))).fetchone()
        return (r[0] if r and r[0] else "hinglish")
    except Exception:  # noqa: BLE001
        return "hinglish"


async def draft_message(claim_id: int, doc_keys: list[str], *, kind: str = "request",
                        note: str = "") -> str:
    """The wording that goes out, with the documents named. Staff can edit every word of it -
    this is the starting point, not the finished thing, because a template nobody can change is
    a template people work around."""
    claim = await _claim(claim_id) or {}
    ctype = claim.get("claim_type") or ""
    name = ((claim.get("complainant_name") or claim.get("insured_name") or "").strip()
            .split(" ") or [""])[0]
    docs = {d["key"]: d for d in await _ck.effective_docs(claim_id, ctype)}
    lang = await _lang_for(claim_id, claim)
    lines = []
    for k in doc_keys:
        d = docs.get(k)
        if d:
            # Hindi readers get the Hindi name of the document; everyone else the English one.
            lines.append("• %s" % ((d.get("hi") if lang == "hi" else None) or d.get("en") or k))
    link = await _upload_link(claim_id)

    head = ("Namaste %s \U0001f64f" % name) if name else "Namaste \U0001f64f"
    if kind == "rerequest":
        opening = ("We asked for a few documents on your claim NP-%s earlier. We still do not "
                   "have the ones below — could you please send them?" % claim_id)
    elif kind == "nudge":
        opening = ("A gentle reminder about your claim NP-%s. We are still waiting for:"
                   % claim_id)
    else:
        opening = ("To take your claim NP-%s forward we need the following document(s):"
                   % claim_id)

    body = [head, "", opening, ""] + lines
    # The email ID is the one ask that must explain itself, in the language they read.
    if "mail_credentials" in (doc_keys or []):
        body += ["", MAIL_ID_NOTE.get(lang, MAIL_ID_NOTE["hinglish"])]
    if (note or "").strip():
        body += ["", (note or "").strip()]
    if link:
        body += ["", "Send them here — it is the quickest way:", link]
    body += ["", "You can also reply to this message with a photo of each document."]
    if kind in ("nudge", "rerequest"):
        body += ["", IGNORE_LINE_EN, IGNORE_LINE_HI]
    body += ["", "— Team NidaanPartner"]
    return "\n".join(body)


# ── the pre-send check ───────────────────────────────────────────────────────
def _stamp(claim_id: int, doc_keys: list[str], message: str, people: list[dict],
           channels: list[str]) -> str:
    """A fingerprint of exactly what is about to go out. send() demands the one preview()
    produced, so a staffer cannot change the list or the wording after looking at it and have
    the change go out unseen."""
    payload = json.dumps({
        "c": int(claim_id),
        "d": sorted(doc_keys or []),
        "m": (message or "").strip(),
        "p": sorted("%s|%s|%s" % (p.get("kind"), p.get("phone", ""), p.get("email", ""))
                    for p in people),
        "ch": sorted(channels or []),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


async def preview(claim_id: int, *, doc_keys: list[str], message: str, extras=None,
                  exclude=None, channels=None) -> dict:
    """What will be sent, to whom, on which channel - and what is wrong with it.

    This is the "check again before you send" step. It returns problems as sentences a person can
    act on, and a `confirm` token that send() will insist on.
    """
    claim = await _claim(claim_id)
    if not claim:
        return {"ok": False, "error": "That claim does not exist."}
    # None means "you did not say", and both are sensible. An EMPTY list means the staffer
    # unticked both, which means do not send - answering that by sending on both would be the
    # exact surprise this whole screen exists to prevent.
    if channels is None:
        channels = ["whatsapp", "email"]
    channels = [c for c in channels if c in ("whatsapp", "email")]
    doc_keys = [k for k in (doc_keys or []) if k]
    exclude = set(exclude or [])

    people = [p for p in await recipients(claim_id)
              if ("%s:%s" % (p["role"], p["name"])) not in exclude and p["role"] not in exclude]
    typed, bad_extras = _clean_extras(extras)
    people += typed

    problems, warnings = list(bad_extras), []
    if not doc_keys:
        problems.append("No document is selected. Tick what you need before sending.")
    if not (message or "").strip():
        problems.append("The message is empty.")
    if not channels:
        problems.append("Pick at least one way to send it — WhatsApp or email.")

    # The whole point is reaching the complainant. Copying the branch while the complainant
    # themselves is unreachable is a send that looks successful and achieves nothing.
    to = [p for p in people if p["kind"] == "to"]
    reach_to = [p for p in to if (p["phone"] and "whatsapp" in channels)
                or (p["email"] and "email" in channels)]
    if not to:
        problems.append("Nobody is set as the person we are asking.")
    elif not reach_to:
        problems.append("We have no working %s for the complainant, so this ask would reach "
                        "nobody. Add one below, or fix it on the claim."
                        % (" or ".join(channels)))

    cc = [p for p in people if p["kind"] == "cc"]
    unreachable_cc = [p for p in cc if not p["phone"] and not p["email"]]
    for p in unreachable_cc:
        warnings.append("%s (%s) has no phone or email on file, so they will not be copied."
                        % (p["name"] or p["label"], p["label"]))

    # A document we already have, being asked for again, is how a customer loses confidence.
    ctype = claim.get("claim_type") or ""
    all_docs = await _ck.effective_docs(claim_id, ctype)
    docs_by_key = {d["key"]: d for d in all_docs}
    have = {d["key"] for d in all_docs if (d.get("row") or {}).get("received")}
    dup = [k for k in doc_keys if k in have]
    if dup:
        warnings.append("You are asking again for something we already have: %s."
                        % ", ".join((docs_by_key.get(k) or {}).get("en") or k for k in dup))

    # A document we are asking for that the message never mentions is a document the customer
    # will not know to send. The draft follows the ticked list on its own, but a hand-edited
    # message can drift - and the browser is not where this should be enforced.
    body = (message or "").lower()
    unnamed = []
    for k in doc_keys:
        d = docs_by_key.get(k)
        if d and (d.get("en") or "").lower() not in body:
            unnamed.append(d.get("en") or k)
    if unnamed:
        warnings.append("The message does not mention %s. They will not know to send %s."
                        % (", ".join(unnamed[:4]),
                           "it" if len(unnamed) == 1 else "them"))

    reach = []
    for p in people:
        ways = []
        if p["phone"] and "whatsapp" in channels:
            ways.append("WhatsApp %s" % p["phone"])
        if p["email"] and "email" in channels:
            ways.append(p["email"])
        reach.append({**p, "ways": ways})

    out = {"ok": not problems, "problems": problems, "warnings": warnings,
           "recipients": reach, "channels": channels, "doc_keys": doc_keys,
           "message": (message or "").strip(),
           "to_count": len([p for p in reach if p["kind"] == "to" and p["ways"]]),
           "cc_count": len([p for p in reach if p["kind"] == "cc" and p["ways"]])}
    if not problems:
        out["confirm"] = _stamp(claim_id, doc_keys, message, people, channels)
    return out


# ── sending ──────────────────────────────────────────────────────────────────
async def _wa(phone: str, text: str) -> tuple[bool, str]:
    """WhatsApp one number. STOP is always honoured; a cold contact outside the 24-hour window
    cannot be messaged freely, and saying so is more use than a silent failure."""
    try:
        import biz_nidaan_whatsapp as _w
        import biz_nidaan_wa_flow as _flow
        if not _w.is_configured():
            return False, "WhatsApp is not connected"
        msisdn = _w.normalize_msisdn(phone)
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT status FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
        if r and dict(r).get("status") == "stopped":
            return False, "they replied STOP"
        if not await _flow.in_session_window(msisdn):
            return False, "no open WhatsApp window (they must message us first)"
        await _w.send_text(msisdn, text)
        return True, ""
    except Exception as e:  # noqa: BLE001
        logger.info("doc-request whatsapp failed %s: %s", phone, e)
        return False, "send failed"


def _html(text: str, claim_id: int) -> str:
    esc = (str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return ('<div style="font-family:Arial,sans-serif;font-size:15px;color:#1a1a1a;'
            'line-height:1.65;white-space:pre-wrap">%s</div>' % esc)


async def _mail(email: str, subject: str, text: str, claim_id: int) -> tuple[bool, str]:
    try:
        import biz_email as _email
        ok = await _email.send_email(to_email=email, subject=subject,
                                     html_body=_html(text, claim_id),
                                     from_name="Nidaan Partner")
        return bool(ok), "" if ok else "send failed"
    except Exception as e:  # noqa: BLE001
        logger.info("doc-request email failed %s: %s", email, e)
        return False, "send failed"


async def send(claim_id: int, *, doc_keys: list[str], message: str, confirm: str,
               extras=None, exclude=None, channels=None, actor: str = "",
               actor_staff_id: Optional[int] = None, kind: str = "request") -> dict:
    """Push the ask. Refuses unless `confirm` matches what preview() showed, so nothing reaches a
    customer that a member of staff has not actually read back."""
    pv = await preview(claim_id, doc_keys=doc_keys, message=message, extras=extras,
                       exclude=exclude, channels=channels)
    if not pv.get("ok"):
        return {"ok": False, "error": (pv.get("problems") or ["Could not send."])[0],
                "problems": pv.get("problems") or []}
    if not confirm or confirm != pv.get("confirm"):
        return {"ok": False, "error": "This changed since you checked it. Look at it once more, "
                                      "then send.", "stale": True}

    subject = "[NidaanPartner] Documents needed for your claim NP-%s" % claim_id
    results = []
    for p in pv["recipients"]:
        row = {"role": p["role"], "name": p["name"] or p["label"], "kind": p["kind"],
               "whatsapp": "", "email": ""}
        if p["phone"] and "whatsapp" in pv["channels"]:
            ok, why = await _wa(p["phone"], message)
            row["whatsapp"] = "sent" if ok else (why or "failed")
        if p["email"] and "email" in pv["channels"]:
            ok, why = await _mail(p["email"], subject, message, claim_id)
            row["email"] = "sent" if ok else (why or "failed")
        results.append(row)

    delivered = sum(1 for r in results
                    if r["whatsapp"] == "sent" or r["email"] == "sent")
    reached_complainant = any(
        r["kind"] == "to" and (r["whatsapp"] == "sent" or r["email"] == "sent")
        for r in results)

    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute(
            "INSERT INTO nidaan_doc_requests (claim_id, doc_keys, message, channels, recipients, "
            "sent_by_staff_id, sent_by, kind, result) VALUES (?,?,?,?,?,?,?,?,?)",
            (int(claim_id), "\n".join(doc_keys), message, ",".join(pv["channels"]),
             json.dumps([{k: p[k] for k in ("role", "label", "name", "phone", "email", "kind")}
                         for p in pv["recipients"]], ensure_ascii=False),
             actor_staff_id, (actor or "")[:80], kind,
             json.dumps(results, ensure_ascii=False)))
        req_id = cur.lastrowid
        await c.commit()

    # The chase clock starts (or restarts) only when the person we are asking actually heard us.
    if reached_complainant:
        await _arm_chase(claim_id, reset=(kind != "nudge"))

    try:
        await _n.record_claim_activity(
            claim_id, "doc_request", channel=",".join(pv["channels"]), direction="out",
            actor=actor or "staff",
            summary="Asked for %d document(s) — %d recipient(s) reached%s"
                    % (len(doc_keys), delivered,
                       "" if reached_complainant else ", COMPLAINANT NOT REACHED"),
            meta=json.dumps({"req_id": req_id, "docs": doc_keys}, ensure_ascii=False))
    except Exception:
        pass

    return {"ok": True, "req_id": req_id, "delivered": delivered,
            "reached_complainant": reached_complainant, "results": results}


# ── the chase clock ──────────────────────────────────────────────────────────
async def _arm_chase(claim_id: int, *, reset: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as c:
        if reset:
            await c.execute(
                "INSERT INTO nidaan_doc_chase (claim_id, nudges, last_nudge_at, next_nudge_at, "
                "paused, call_due, updated_at) VALUES (?,0,datetime('now'),"
                "datetime('now', ?),0,0,datetime('now')) "
                "ON CONFLICT(claim_id) DO UPDATE SET nudges=0, last_nudge_at=datetime('now'), "
                "next_nudge_at=datetime('now', ?), paused=0, call_due=0, call_done_at=NULL, "
                "updated_at=datetime('now')",
                (int(claim_id), "+%d days" % NUDGE_GAP_DAYS, "+%d days" % NUDGE_GAP_DAYS))
        else:
            await c.execute(
                "UPDATE nidaan_doc_chase SET nudges=nudges+1, last_nudge_at=datetime('now'), "
                "next_nudge_at=datetime('now', ?), updated_at=datetime('now') WHERE claim_id=?",
                ("+%d days" % NUDGE_GAP_DAYS, int(claim_id)))
        await c.commit()


async def chase_state(claim_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT * FROM nidaan_doc_chase WHERE claim_id=?", (int(claim_id),))).fetchone()
    if not r:
        return {"armed": False, "nudges": 0, "call_due": False}
    d = dict(r)
    return {"armed": not d.get("paused"), "nudges": int(d.get("nudges") or 0),
            "last_nudge_at": d.get("last_nudge_at"), "next_nudge_at": d.get("next_nudge_at"),
            "paused": bool(d.get("paused")), "call_due": bool(d.get("call_due")),
            "call_done_at": d.get("call_done_at"), "call_by": d.get("call_by") or "",
            "call_note": d.get("call_note") or "",
            "max_nudges": MAX_NUDGES, "gap_days": NUDGE_GAP_DAYS}


async def pause_chase(claim_id: int, *, paused: bool, actor: str = "") -> dict:
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "INSERT INTO nidaan_doc_chase (claim_id, paused, updated_at) VALUES (?,?,datetime('now')) "
            "ON CONFLICT(claim_id) DO UPDATE SET paused=?, updated_at=datetime('now')",
            (int(claim_id), 1 if paused else 0, 1 if paused else 0))
        await c.commit()
    return {"ok": True}


async def log_call(claim_id: int, *, note: str, actor: str) -> dict:
    """The phone call happened. Recording it closes the chase - and the note is what the next
    person reads instead of calling the same customer again tomorrow."""
    note = (note or "").strip()
    if not note:
        return {"ok": False, "error": "Write down what they said."}
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "INSERT INTO nidaan_doc_chase (claim_id, call_due, call_done_at, call_by, call_note, "
            "updated_at) VALUES (?,0,datetime('now'),?,?,datetime('now')) "
            "ON CONFLICT(claim_id) DO UPDATE SET call_due=0, call_done_at=datetime('now'), "
            "call_by=?, call_note=?, updated_at=datetime('now')",
            (int(claim_id), (actor or "")[:80], note[:600], (actor or "")[:80], note[:600]))
        await c.commit()
    try:
        await _n.record_claim_activity(
            claim_id, "doc_call", channel="phone", direction="out", actor=actor or "staff",
            summary="Called about the pending documents", meta=json.dumps({"note": note[:300]}))
    except Exception:
        pass
    return {"ok": True}


async def due_nudges(limit: int = 50) -> list[int]:
    """Claims whose next nudge is due: still missing something, not paused, not already handed
    over to a phone call."""
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = await (await c.execute(
            "SELECT ch.claim_id FROM nidaan_doc_chase ch "
            "JOIN nidaan_claims cl ON cl.claim_id=ch.claim_id "
            "WHERE ch.paused=0 AND ch.call_due=0 AND ch.next_nudge_at IS NOT NULL "
            "AND ch.next_nudge_at <= datetime('now') AND COALESCE(cl.archived,0)=0 "
            "ORDER BY ch.next_nudge_at LIMIT ?", (int(limit),))).fetchall()
    return [int(dict(r)["claim_id"]) for r in rows]


async def auto_collection_on() -> bool:
    """Is AUTOMATIC document collection switched on globally?

    The founder's rule (17 Sep): the global switch governs what the system does BY ITSELF. It has
    no say over what a person deliberately set up on one claim - a staffer who has spoken to a
    complainant and scheduled a Sunday-morning reminder has made a decision, and a global default
    must not quietly override it. So this gates the automatic chase only; `start_for_claim` (a
    staffer pressing Start) and the scheduled reminders run regardless.

    Worth knowing: until today this setting was stored and read by the settings screen but never
    actually checked anywhere, so "OFF" held nothing back.
    """
    try:
        return str(await _n.get_ops_setting("wa_doc_collection_enabled", "0")) in ("1", "true", "True")
    except Exception:  # noqa: BLE001
        return False


async def run_chase() -> dict:
    """The worker pass. Nudges what is due; when a claim has had its nudges, stops sending and
    raises it as a phone call for the bucket's duty staff - which is where an automatic process
    should hand back to a person."""
    done = {"nudged": 0, "to_call": 0, "cleared": 0}
    if not await auto_collection_on():
        # Automatic chasing is off. Anything a person scheduled on a claim still goes - that is
        # the point of the claim-level setting winning.
        return done
    for claim_id in await due_nudges():
        try:
            claim = await _claim(claim_id)
            if not claim:
                continue
            pending = await _ck.pending_required_docs(claim_id, claim.get("claim_type") or "")
            if not pending:
                # Everything arrived. Stop chasing rather than leaving a live clock behind.
                async with aiosqlite.connect(DB_PATH) as c:
                    await c.execute("UPDATE nidaan_doc_chase SET paused=1, call_due=0, "
                                    "next_nudge_at=NULL, updated_at=datetime('now') "
                                    "WHERE claim_id=?", (claim_id,))
                    await c.commit()
                done["cleared"] += 1
                continue

            st = await chase_state(claim_id)
            if st["nudges"] >= MAX_NUDGES:
                async with aiosqlite.connect(DB_PATH) as c:
                    await c.execute("UPDATE nidaan_doc_chase SET call_due=1, next_nudge_at=NULL, "
                                    "updated_at=datetime('now') WHERE claim_id=?", (claim_id,))
                    await c.commit()
                await _flag_for_call(claim_id, claim, len(pending))
                done["to_call"] += 1
                continue

            keys = [d["key"] for d in pending]
            msg = await draft_message(claim_id, keys, kind="nudge")
            pv = await preview(claim_id, doc_keys=keys, message=msg,
                               channels=["whatsapp", "email"])
            if not pv.get("ok"):
                # We cannot reach them automatically, so a person has to. Do not keep retrying.
                async with aiosqlite.connect(DB_PATH) as c:
                    await c.execute("UPDATE nidaan_doc_chase SET call_due=1, next_nudge_at=NULL, "
                                    "updated_at=datetime('now') WHERE claim_id=?", (claim_id,))
                    await c.commit()
                await _flag_for_call(claim_id, claim, len(pending),
                                     why=(pv.get("problems") or [""])[0])
                done["to_call"] += 1
                continue
            r = await send(claim_id, doc_keys=keys, message=msg, confirm=pv["confirm"],
                           channels=["whatsapp", "email"], actor="automatic nudge", kind="nudge")
            if r.get("ok"):
                done["nudged"] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("chase failed for claim %s: %s", claim_id, e)
    return done


async def _flag_for_call(claim_id: int, claim: dict, pending_n: int, why: str = "") -> None:
    """Hand the claim back to a person, on the bell and on Telegram, once for this claim."""
    try:
        import biz_nidaan_notifications as _nnot
        ids = []
        try:
            stage = (claim.get("pipeline_stage") or "").strip()
            if stage:
                ids = list(await _n.on_duty_rep_ids(stage))
        except Exception:
            ids = []
        if not ids:
            try:
                ids = [a["staff_id"] for a in await _nnot._super_admin_staff()]
            except Exception:
                ids = []
        if not ids:
            return
        who = (claim.get("complainant_name") or claim.get("insured_name") or "").strip()
        phone = valid_phone(claim.get("complainant_phone") or claim.get("insured_phone"))
        body = ["We have nudged twice and %d document(s) are still missing." % pending_n]
        if why:
            body.append("Automatic reminders cannot get through: %s" % why)
        body += ["", "Please call:", "%s %s" % (who or "the complainant", phone or "(no number "
                                                "on file — find one first)"),
                 "", "Write down what they say on the claim afterwards."]
        await _nnot.notify_staff_inapp(
            ids, "\U0001f4de NP-%s — time to phone about the documents" % claim_id,
            "\n".join(body), event_key="doc.call_due", email=False, claim_id=claim_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("call flag failed for claim %s: %s", claim_id, e)


# ── what the window loads ────────────────────────────────────────────────────
async def window(claim_id: int) -> dict:
    """Everything the pending-document window needs, in one call."""
    claim = await _claim(claim_id)
    if not claim:
        return {"ok": False, "error": "That claim does not exist."}
    ctype = claim.get("claim_type") or ""
    docs = []
    for d in await _ck.effective_docs(claim_id, ctype):
        row = d.pop("row", None) or {}
        docs.append({"key": d["key"], "label": d.get("en") or d["key"],
                     "label_hi": d.get("hi") or "", "why": d.get("why") or d.get("why_en") or "",
                     "required": bool(row.get("required")) if row else bool(d.get("required")),
                     "conditional": bool(d.get("conditional")),
                     "custom": bool(d.get("custom")), "added_by": d.get("added_by") or "",
                     "received": bool(row.get("received")),
                     "received_via": row.get("received_via") or "",
                     "received_doc_id": row.get("received_doc_id")})
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        reqs = [dict(r) for r in await (await c.execute(
            "SELECT req_id, doc_keys, channels, sent_by, kind, result, created_at "
            "FROM nidaan_doc_requests WHERE claim_id=? ORDER BY req_id DESC LIMIT 8",
            (int(claim_id),))).fetchall()]
    for r in reqs:
        try:
            r["result"] = json.loads(r["result"] or "[]")
        except Exception:
            r["result"] = []
        r["doc_keys"] = [k for k in (r["doc_keys"] or "").split("\n") if k]

    return {
        "ok": True,
        "claim_id": claim_id,
        "claim_type": _ck.canonical_type(ctype),
        "claim_type_raw": ctype,
        "types": sorted(_ck.TEMPLATES.keys()),
        "complainant": (claim.get("complainant_name") or claim.get("insured_name") or ""),
        "docs": docs,
        "removed": await _ck.removed_docs(claim_id),
        "recipients": await recipients(claim_id),
        "chase": await chase_state(claim_id),
        "history": reqs,
    }


async def set_claim_type(claim_id: int, claim_type: str, *, actor: str) -> dict:
    """Correcting the claim type changes which documents the case needs, so the standard list is
    re-seeded. Nothing already received or already added by hand is touched."""
    ct = (claim_type or "").strip().lower()
    if ct not in _ck.TEMPLATES and ct not in _ck.ALIASES:
        return {"ok": False, "error": "That is not a claim type we have a document list for."}
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute("UPDATE nidaan_claims SET claim_type=? WHERE claim_id=?",
                        (ct, int(claim_id)))
        await c.commit()
    await _ck.seed_checklist_for_claim(claim_id, ct)
    try:
        await _n.record_claim_activity(
            claim_id, "claim_type", actor=actor or "staff",
            summary="Claim type corrected to %s — document list updated" % ct)
    except Exception:
        pass
    return {"ok": True, "claim_type": _ck.canonical_type(ct)}
