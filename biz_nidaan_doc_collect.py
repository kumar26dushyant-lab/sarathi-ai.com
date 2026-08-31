"""
NidaanPartner in-house L2 DOCUMENT-COLLECTION engine.

One engine, two arms — EMAIL (live now, SMTP configured) and WhatsApp (wires in once the Meta
number is live). Both read the SAME document checklist (`biz_nidaan_doc_checklist`) so they never
duplicate and stay in sync with the claimant dashboard. Every nudge is recorded on the claim
timeline (`record_claim_activity`). Never raises to the caller.
"""
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

import biz_database as db
import biz_nidaan as _n
import biz_nidaan_doc_checklist as _ck
import biz_nidaan_claimant as _cl

logger = logging.getLogger("nidaan.doccollect")
DB_PATH = db.DB_PATH


def contact_status(claim: dict) -> dict:
    """Is the claimant reachable for nudging? email drives the email arm, phone the WhatsApp arm."""
    email = (claim.get("insured_email") or "").strip()
    phone = (claim.get("insured_phone") or "").strip()
    return {"email_ok": bool(email and "@" in email), "phone_ok": len(_digits(phone)) >= 10,
            "ready": bool(email and "@" in email) or len(_digits(phone)) >= 10}


def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


async def _claim(claim_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT claim_id, insured_name, insured_email, insured_phone, claim_type, account_id, "
            "comm_lang FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    return dict(r) if r else None


async def send_email_reminder(claim_id: int, *, by: str = "system") -> dict:
    """Email the claimant the still-pending documents + the secure upload link. Gated on a valid
    claimant email; no-ops (returns a reason) when nothing is pending. Records the nudge."""
    claim = await _claim(claim_id)
    if not claim:
        return {"ok": False, "error": "claim_not_found"}
    email = (claim.get("insured_email") or "").strip()
    if not (email and "@" in email):
        return {"ok": False, "error": "no_email"}   # gate: fill the claimant email first
    ctype = claim.get("claim_type") or ""
    pending = await _ck.pending_required_docs(claim_id, ctype)
    total = len(_ck.doc_template_for(ctype)) or 0
    done = max(0, total - len(pending))
    if not pending:
        return {"ok": False, "error": "no_pending", "done": done, "total": total}
    # Secure upload link (provisions the claimant portal + magic token on first use).
    try:
        await _cl.ensure_portal(claim_id, with_token=True)
        p = await _cl.get_portal(claim_id)
        link = f"{_cl._public_base()}/nidaan/claim/magic?token={p.get('access_token')}" if p and p.get("access_token") else _cl._public_base()
    except Exception:
        link = _cl._public_base()
    name = (claim.get("insured_name") or "").split(" ")[0]
    reg = f"NP-{claim_id}"
    # Pending list — bilingual, one line each (label + why).
    li_en = "".join(f"<li><b>{_esc(d.get('en',''))}</b> — <span style='color:#555'>{_esc(d.get('why_en',''))}</span></li>" for d in pending)
    li_hi = "".join(f"<li><b>{_esc(d.get('hi', d.get('en','')))}</b></li>" for d in pending)
    subject = f"[NidaanPartner] {len(pending)} document(s) needed for your claim {reg}"
    html = f"""
      <div style="font-family:Arial,sans-serif;font-size:15px;color:#1a1a1a;line-height:1.6">
        <p>Namaste {_esc(name)} 🙏</p>
        <p>To move your claim <b>{reg}</b> forward, we still need the following document(s)
           ({done} of {total} done):</p>
        <ul>{li_en}</ul>
        <p style="margin:1rem 0"><a href="{_esc(link)}"
           style="background:#0d7a68;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:700">
           📎 Upload your documents here</a></p>
        <hr style="border:none;border-top:1px solid #eee;margin:1.2rem 0">
        <p style="color:#444">नमस्ते {_esc(name)} 🙏<br>
           आपके क्लेम <b>{reg}</b> को आगे बढ़ाने के लिए हमें ये दस्तावेज़ चाहिए:</p>
        <ul style="color:#444">{li_hi}</ul>
        <p style="color:#444">कृपया ऊपर दिए लिंक से अपलोड करें। एक बार सभी दस्तावेज़ मिलते ही हमारी टीम
           आपके क्लेम पर काम शुरू कर देगी।</p>
        <p style="color:#888;font-size:13px">— Team NidaanPartner</p>
      </div>"""
    try:
        import biz_email as _email
        ok = await _email.send_email(to_email=email, subject=subject, html_body=html,
                                     from_name="Nidaan Partner")
    except Exception as e:
        logger.warning("doc reminder email failed claim=%s: %s", claim_id, e)
        ok = False
    try:
        await _n.record_claim_activity(
            claim_id, "doc_reminder", channel="email", direction="out", actor=by,
            summary=(f"Emailed {len(pending)} pending doc(s) to claimant ({done}/{total} done)"
                     if ok else "Doc-reminder email attempted (send failed)"),
            meta=f'{{"pending":{len(pending)},"ok":{str(ok).lower()}}}')
    except Exception:
        pass
    return {"ok": bool(ok), "pending": len(pending), "done": done, "total": total, "email": email}


def _esc(s: str) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
