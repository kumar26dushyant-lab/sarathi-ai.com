"""
NidaanPartner — Claimant Portal (the policyholder's own view of their claim).

WHY: branches / staff / subscribers RAISE claims, but they are only mediators. The insured /
claimant / policyholder is the one who owns the information (documents, facts) and who our fee
agreement is actually with. So once a claim reaches L2 (ClaimShield) we open a direct line to the
CLAIMANT — a dashboard to track status, share documents, and give digital consent to the
success-fee terms — while keeping the mediator in the loop (CC/visibility).

ONE dashboard, TWO entry paths (endpoint uniformity):
  • mediated claim        → a magic-link (access_token) provisions the dashboard on first click
                            (link IS the login; OTP/Google only for re-entry).
  • direct ₹499 claimant  → already signed up + has a dashboard; access_token stays NULL and the
                            consent simply appears as an action-card inside their existing dashboard.

This module is the safe, additive FOUNDATION (identity/token/consent/fee state). It does NOT send
emails, enforce anything, or wire live triggers yet — those land in the next increment, after the
success-fee T&C copy is vetted by counsel (founder-owned).
"""
from __future__ import annotations

import secrets
import logging
from typing import Optional

import aiosqlite
import biz_database as _db
import biz_nidaan as _nidaan

logger = logging.getLogger("sarathi.claimant")

DB_PATH = _db.DB_PATH


def _gen_token() -> str:
    """Opaque, unguessable, URL-safe magic-link token (revocable by rotating)."""
    return secrets.token_urlsafe(32)


# ── Fee / GST config (super-admin editable; snapshotted at acceptance) ────────
async def fee_config() -> dict:
    """The success-fee terms to DISPLAY today: our % of recovered amount + GST (per the shared
    gst_config, so GST only shows once registration is switched on) + the current T&C version."""
    try:
        fee_pct = float(await _nidaan.get_ops_setting("claimant_success_fee_pct", "15") or "15")
    except (TypeError, ValueError):
        fee_pct = 15.0
    gst = await _nidaan.gst_config()
    # NOTE: pass NO explicit default so get_ops_setting falls back to OPS_SETTING_DEFAULTS
    # (passing "" would suppress that fallback and return empty terms).
    version = (await _nidaan.get_ops_setting("claimant_terms_version") or "v1").strip()
    terms_html = await _nidaan.get_ops_setting("claimant_terms_html") or ""
    terms_html_hi = await _nidaan.get_ops_setting("claimant_terms_html_hi") or ""
    return {
        "fee_pct": fee_pct,
        "gst_enabled": bool(gst.get("enabled")),
        "gst_pct": float(gst.get("rate") or 18.0) if gst.get("enabled") else 0.0,
        "terms_version": version,
        "terms_html": terms_html,
        "terms_html_hi": terms_html_hi,
    }


def compute_fee(recovered_amount: float, fee_pct: float, gst_pct: float) -> dict:
    """Line-item breakdown shown in the consent card: fee on the RECOVERED amount, then GST on the
    fee. Returns rupee figures (rounded) so the claimant sees exactly what they're accepting."""
    recovered = max(0.0, float(recovered_amount or 0))
    fee = round(recovered * fee_pct / 100.0, 2)
    gst = round(fee * gst_pct / 100.0, 2) if gst_pct else 0.0
    return {
        "recovered_amount": round(recovered, 2),
        "fee_pct": fee_pct, "fee_amount": fee,
        "gst_pct": gst_pct, "gst_amount": gst,
        "total_our_fee": round(fee + gst, 2),
        "net_to_claimant": round(recovered - fee - gst, 2),
    }


# ── Portal lifecycle ─────────────────────────────────────────────────────────
async def ensure_portal(claim_id: int, with_token: bool = True) -> dict:
    """Get-or-create the claimant portal row for a claim. `with_token` mints a magic-link token
    (mediated path); pass False for direct ₹499 claimants who log in to their own account.
    Idempotent — never rotates an existing token here."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_claimant_portal WHERE claim_id=?", (claim_id,))).fetchone()
        if row:
            return dict(row)
        token = _gen_token() if with_token else None
        await conn.execute(
            "INSERT INTO nidaan_claimant_portal (claim_id, access_token, token_created_at) "
            "VALUES (?, ?, CASE WHEN ? IS NULL THEN NULL ELSE CURRENT_TIMESTAMP END)",
            (claim_id, token, token))
        await conn.commit()
        row = await (await conn.execute(
            "SELECT * FROM nidaan_claimant_portal WHERE claim_id=?", (claim_id,))).fetchone()
        return dict(row)


async def get_portal(claim_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_claimant_portal WHERE claim_id=?", (claim_id,))).fetchone()
    return dict(row) if row else None


async def get_portal_by_token(token: str) -> Optional[dict]:
    """Resolve a magic-link token → portal row joined with the claim summary (for the claimant's
    dashboard). Returns None for an unknown/blank/revoked token."""
    token = (token or "").strip()
    if not token:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT p.*, c.insured_name, c.insured_email, c.insured_phone, c.claim_type, "
            "       c.status AS claim_status, c.stage AS claim_stage, c.disputed_amount, "
            "       c.review_outcome "
            "FROM nidaan_claimant_portal p JOIN nidaan_claims c ON c.claim_id=p.claim_id "
            "WHERE p.access_token=?", (token,))).fetchone()
    return dict(row) if row else None


async def claim_is_l2(claim_id: int) -> bool:
    """A claim is 'at L2' (legal action authorized) once it's reviewed-GO. Until then the claimant
    dashboard shows NOTHING about fees — only after L2 do we ask for authorization."""
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT review_outcome FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    return bool(row and (row[0] == "can_fight"))


async def mark_pushed(claim_id: int, staff_name: str) -> None:
    """Record that a staffer pushed the fee authorization to the claimant (name + timestamp)."""
    await ensure_portal(claim_id, with_token=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claimant_portal SET consent_pushed_by=?, consent_pushed_at=CURRENT_TIMESTAMP "
            "WHERE claim_id=?", ((staff_name or "")[:120], claim_id))
        await conn.commit()


async def rotate_token(claim_id: int) -> Optional[str]:
    """Issue a fresh magic-link token (invalidates the old one). Used if a link may have leaked or
    the claimant needs a new link. Returns the new token, or None if no portal exists."""
    token = _gen_token()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_claimant_portal SET access_token=?, token_created_at=CURRENT_TIMESTAMP "
            "WHERE claim_id=?", (token, claim_id))
        await conn.commit()
        return token if cur.rowcount > 0 else None


async def mark_activated(claim_id: int) -> None:
    """Stamp the first time the claimant actually opened their portal (only sets once).

    Opening the L2 magic-link proves control of the inbox we emailed → this is ALSO how the
    claimant's email gets VERIFIED (Phase 2: email+mobile mandatory at creation, verified via
    the magic-link, no OTP for mediated claims). Staff-inspect opens (?staff=1) never call this."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claimant_portal SET activated_at=CURRENT_TIMESTAMP "
            "WHERE claim_id=? AND activated_at IS NULL", (claim_id,))
        await conn.execute(
            "UPDATE nidaan_claims SET insured_email_verified=1, "
            "insured_email_verified_at=CURRENT_TIMESTAMP "
            "WHERE claim_id=? AND COALESCE(insured_email_verified,0)=0", (claim_id,))
        await conn.commit()


async def mark_link_sent(claim_id: int) -> None:
    """Record that we (re)sent the greeting/portal link — powers the manual 're-send' button on the
    L2 claim and the 'link sent N times' visibility in ops."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claimant_portal "
            "SET link_sent_at=CURRENT_TIMESTAMP, link_sent_count=COALESCE(link_sent_count,0)+1 "
            "WHERE claim_id=?", (claim_id,))
        await conn.commit()


async def record_consent(claim_id: int, ip: str = "", user_agent: str = "") -> dict:
    """Digital acceptance of the success-fee terms. Snapshots the % + GST + T&C VERSION and the exact
    TERMS TEXT (EN+HI) that applied RIGHT NOW, plus the device (user-agent), the claimant's name, the
    IP and a SHA-256 integrity hash over the whole record — so a later config change never alters an
    accepted agreement (grandfathered) and the downloadable proof is tamper-evident.
    Idempotent: if already accepted, returns the existing record unchanged."""
    import hashlib
    from datetime import datetime, timezone, timedelta
    existing = await get_portal(claim_id)
    if existing and existing.get("consent_accepted_at"):
        return {"ok": True, "already": True, "portal": existing}
    cfg = await fee_config()
    contact = await _claim_contact(claim_id)
    name = (contact or {}).get("insured_name") or ""
    # The exact wording shown to the claimant (both languages), pinned for the record.
    snapshot = (("ENGLISH\n" + (cfg.get("terms_html") or "")).strip()
                + "\n\n————————————————\n\nहिंदी\n" + (cfg.get("terms_html_hi") or "")).strip()
    ist = timezone(timedelta(hours=5, minutes=30))
    accepted_at = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    canonical = "|".join([str(claim_id), name, cfg["terms_version"], str(cfg["fee_pct"]),
                          str(cfg["gst_pct"]), accepted_at, (ip or ""), snapshot])
    chash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    await ensure_portal(claim_id, with_token=False)  # make sure a row exists
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claimant_portal SET consent_accepted_at=?, "
            "consent_terms_version=?, consent_fee_pct=?, consent_gst_pct=?, consent_ip=?, "
            "consent_terms_snapshot=?, consent_user_agent=?, consent_name=?, consent_hash=? "
            "WHERE claim_id=?",
            (accepted_at, cfg["terms_version"], cfg["fee_pct"], cfg["gst_pct"], (ip or "")[:64],
             snapshot, (user_agent or "")[:400], name[:120], chash, claim_id))
        await conn.commit()
    logger.info("Claimant consent recorded: claim=%s fee=%s%% gst=%s%% ver=%s hash=%s",
                claim_id, cfg["fee_pct"], cfg["gst_pct"], cfg["terms_version"], chash[:12])
    return {"ok": True, "already": False, "portal": await get_portal(claim_id)}


# ── Claimant-facing status timeline + their own documents ────────────────────
# Customer-friendly labels (internal statuses are never shown raw to the policyholder).
_CLAIMANT_STATUS_LABELS = {
    "intimated": "Claim received", "assigned": "Assigned to our team",
    "in_review": "Under review", "in_negotiation": "In negotiation with the insurer",
    "resolved_won": "Resolved in your favour", "resolved_lost": "Closed",
    "closed": "Closed", "withdrawn": "Withdrawn",
    "review_delivered": "Assessment shared",
}


def claimant_status_label(status: str) -> str:
    s = (status or "").strip().lower()
    return _CLAIMANT_STATUS_LABELS.get(s, (s or "In progress").replace("_", " ").title())


async def claim_timeline(claim_id: int) -> list[dict]:
    """The claim's status progression as a friendly, INTERNAL-NOTE-FREE timeline for the claimant.
    (Notes on status changes are staff-facing and deliberately omitted here.)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT to_status, changed_at FROM nidaan_claim_status_log "
            "WHERE claim_id=? AND COALESCE(to_status,'')<>'' ORDER BY changed_at ASC, log_id ASC",
            (claim_id,))).fetchall()
    out = []
    for r in rows:
        out.append({"label": claimant_status_label(r["to_status"]), "at": r["changed_at"]})
    return out


async def list_claimant_docs(claim_id: int) -> list[dict]:
    """Documents the CLAIMANT uploaded via their portal (never internal files)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT doc_id, stored_name, original_name, file_size, uploaded_at "
            "FROM nidaan_claim_documents WHERE claim_id=? AND source='claimant' "
            "ORDER BY doc_id DESC", (claim_id,))).fetchall()
    return [dict(r) for r in rows]


# ── L2 trigger: greet the claimant + open their portal + notify everyone ──────
def _public_base() -> str:
    import os
    return os.getenv("NIDAAN_PUBLIC_BASE", "https://nidaanpartner.com").rstrip("/")


async def autosend_enabled() -> bool:
    v = await _nidaan.get_ops_setting("claimant_autosend_enabled", "0")
    return str(v).strip().lower() in ("1", "true", "on", "yes")


def _greeting_email_html(name: str, link: str) -> str:
    """Bilingual (Hindi + English), reassuring greeting — NO fee calculation (that lives only on the
    dashboard). Explains who we are, that it's safe, and EXACTLY what happens when they tap."""
    nm = (name or "").strip() or "जी"
    return (
        f"<p style='color:#e2e8f0;font-size:16px'>नमस्ते {nm},</p>"
        "<p>NidaanPartner की ओर से — आपके बीमा दावे में आपकी मदद के लिए हमारी टीम काम कर रही है। "
        "आपके दावे की पूरी जानकारी एक ही जगह देखने के लिए हमने आपके लिए एक <strong>निजी, सुरक्षित पेज</strong> बनाया है।</p>"
        "<p>नीचे दिए बटन पर टैप करने से <strong>सिर्फ़ आपका दावा डैशबोर्ड खुलेगा</strong> — वहाँ आप अपने दावे की स्थिति देख सकते हैं, "
        "ज़रूरी दस्तावेज़ भेज सकते हैं, और आगे की बातचीत कर सकते हैं। इससे आपसे कोई पैसा नहीं लिया जाता।</p>"
        f"<p style='text-align:center;margin:26px 0'><a href='{link}' "
        "style='background:#0d7a68;color:#fff;padding:14px 26px;border-radius:10px;text-decoration:none;font-weight:700;font-size:16px'>"
        "अपना दावा डैशबोर्ड खोलें / Open my claim dashboard</a></p>"
        "<hr style='border:none;border-top:1px solid rgba(255,255,255,0.1);margin:22px 0'>"
        f"<p style='color:#e2e8f0'>Hello {nm},</p>"
        "<p>This is NidaanPartner — our team is working to help you with your insurance claim. We've created a "
        "<strong>private, secure page</strong> for you to see everything about your claim in one place.</p>"
        "<p>Tapping the button above simply <strong>opens your claim dashboard</strong>, where you can track your "
        "claim status, share the documents we need, and stay in touch. It does not charge you anything.</p>"
        "<p style='color:#64748b;font-size:13px'>If the button doesn't work, copy this link into your browser:<br>"
        f"<span style='color:#22d3ee'>{link}</span></p>")


async def _claim_contact(claim_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT claim_id, insured_name, insured_email, account_id FROM nidaan_claims "
            "WHERE claim_id=?", (claim_id,))).fetchone()
    return dict(row) if row else None


async def send_greeting_email(claim_id: int, force: bool = False) -> dict:
    """Open the claimant portal + email the policyholder their link (bilingual, no calc). Auto path
    is gated by `claimant_autosend_enabled`; `force=True` (manual staff action) bypasses the gate.
    Best-effort: never raises. Also pings involved staff on all channels (mediator stays in loop)."""
    if not force and not await autosend_enabled():
        return {"ok": False, "reason": "autosend_off"}
    c = await _claim_contact(claim_id)
    if not c:
        return {"ok": False, "reason": "claim_not_found"}
    email = (c.get("insured_email") or "").strip()
    if not email:
        return {"ok": False, "reason": "no_claimant_email"}
    p = await ensure_portal(claim_id, with_token=True)
    link = f"{_public_base()}/nidaan/claim/magic?token={p.get('access_token')}"
    sent = False
    try:
        import biz_email as _mail
        html = _mail._wrap_nidaan_template("Your claim dashboard", _greeting_email_html(c.get("insured_name") or "", link))
        sent = await _mail.send_email(
            email, "आपका दावा डैशबोर्ड · Your claim dashboard — NidaanPartner", html,
            from_name="Nidaan Partner")
    except Exception as e:  # noqa: BLE001
        logger.warning("claimant greeting email failed claim=%s: %s", claim_id, e)
    if sent:
        await mark_link_sent(claim_id)
    # All-channel heads-up to involved staff (assignees + watchers) — keeps the mediator's ops team
    # in the loop. Best-effort; never blocks.
    try:
        import biz_nidaan_notifications as _notif
        await _notif.notify_claim_watchers(
            claim_id,
            "Claimant portal link sent",
            f"The claimant dashboard link was sent to {c.get('insured_name') or 'the policyholder'} "
            f"({email}) for claim #{claim_id}.",
            event_key="claim.watch")
    except Exception as e:  # noqa: BLE001
        logger.info("claimant portal staff-notify skipped claim=%s: %s", claim_id, e)
    return {"ok": bool(sent), "sent": sent, "link": link}


async def on_claim_reached_l2(claim_id: int) -> dict:
    """Called (best-effort, fire-and-forget) when a claim enters L2/ClaimShield. Auto path — honours
    the claimant_autosend_enabled switch."""
    try:
        return await send_greeting_email(claim_id, force=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("on_claim_reached_l2 failed claim=%s: %s", claim_id, e)
        return {"ok": False, "reason": "error"}


def _wrap_lines(text: str, maxchars: int = 92) -> list:
    out = []
    for para in (text or "").split("\n"):
        if not para.strip():
            out.append("")
            continue
        line = ""
        for w in para.split(" "):
            if len(line) + len(w) + 1 <= maxchars:
                line = (line + " " + w).strip()
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


async def build_consent_proof_pdf(claim_id: int) -> Optional[bytes]:
    """A downloadable, tamper-evident PDF of the claimant's digital acceptance — for the super-admin
    to retain as proof (auditable before authorities). English layout (fitz core fonts don't render
    Devanagari); the FULL bilingual terms text is covered by the integrity hash + kept in the DB.
    Returns None if there's no recorded consent."""
    import fitz  # PyMuPDF
    p = await get_portal(claim_id)
    if not p or not p.get("consent_accepted_at"):
        return None
    contact = await _claim_contact(claim_id) or {}
    snap = p.get("consent_terms_snapshot") or ""
    en_terms = snap.split("————")[0].replace("ENGLISH", "", 1).strip() if snap else ""
    from datetime import datetime, timezone, timedelta
    gen_at = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S IST")
    gst = p.get("consent_gst_pct") or 0
    lines = []
    lines.append(("DIGITAL CONSENT RECORD", 15, True))
    lines.append(("Nidaan The Legal Consultant LLP", 11, True))
    lines.append(("", 10, False))
    lines.append(("Electronically generated record of the claimant's digital acceptance of the "
                  "engagement & success-fee terms, produced by NidaanPartner.com.", 9, False))
    lines.append(("", 10, False))
    lines.append(("CLAIM", 11, True))
    lines.append((f"Claim ID: #{claim_id}", 10, False))
    lines.append((f"Claimant name: {contact.get('insured_name') or p.get('consent_name') or '-'}", 10, False))
    lines.append((f"Phone: {contact.get('insured_phone') or '-'}    Email: {contact.get('insured_email') or '-'}", 10, False))
    lines.append(("", 10, False))
    lines.append(("ACCEPTANCE", 11, True))
    lines.append((f"Accepted (IST): {p.get('consent_accepted_at')}", 10, False))
    lines.append((f"Terms version: {p.get('consent_terms_version') or '-'}", 10, False))
    lines.append((f"Success fee: {p.get('consent_fee_pct')}% of amount recovered"
                  + (f" + {gst}% GST" if gst else "") + " (payable to Nidaan The Legal Consultant LLP)", 10, False))
    lines.append((f"IP address: {p.get('consent_ip') or '-'}", 10, False))
    lines.append((f"Device: {p.get('consent_user_agent') or '-'}", 8, False))
    lines.append((f"Integrity hash (SHA-256): {p.get('consent_hash') or '-'}", 8, False))
    lines.append(("", 10, False))
    lines.append(("TERMS AS PRESENTED AND ACCEPTED", 11, True))
    lines.append(("(English text of record. The terms were also shown in Hindi on screen; the full "
                  "bilingual text is covered by the integrity hash above and retained on file.)", 8, False))
    lines.append(("", 6, False))
    for ln in _wrap_lines(en_terms, 96):
        lines.append((ln, 10, False))
    lines.append(("", 10, False))
    lines.append(("This record and its SHA-256 hash are retained by NidaanPartner; any change to the "
                  "recorded fields would change the hash. A certificate under Section 65B of the Indian "
                  "Evidence Act may be issued on request for evidentiary use.", 8, False))
    lines.append((f"Generated: {gen_at}", 8, False))

    doc = fitz.open()
    W, H, margin = 595, 842, 54
    page = doc.new_page(width=W, height=H)
    y = margin
    for text, size, bold in lines:
        for sub in (_wrap_lines(text, 96) if text else [""]):
            if y > H - margin:
                page = doc.new_page(width=W, height=H)
                y = margin
            if sub:
                page.insert_text((margin, y), sub, fontsize=size,
                                 fontname=("hebo" if bold else "helv"), color=(0.08, 0.13, 0.11))
            y += size + 5
    out = doc.tobytes()
    doc.close()
    return out


async def portal_state(claim_id: int) -> dict:
    """Consolidated state for the ops L2 claim view: does a portal exist, has the claimant opened
    it, have they accepted the fee terms, how many times we sent the link. Never raises."""
    p = await get_portal(claim_id)
    cfg = await fee_config()
    if not p:
        return {"exists": False, "activated": False, "consent_accepted": False,
                "link_sent_count": 0, "is_l2": await claim_is_l2(claim_id),
                "current_fee_pct": cfg["fee_pct"],
                "current_gst_pct": cfg["gst_pct"], "terms_version": cfg["terms_version"]}
    return {
        "exists": True,
        "has_link": bool(p.get("access_token")),
        "activated": bool(p.get("activated_at")),
        "activated_at": p.get("activated_at"),
        "consent_accepted": bool(p.get("consent_accepted_at")),
        "consent_accepted_at": p.get("consent_accepted_at"),
        "consent_fee_pct": p.get("consent_fee_pct"),
        "consent_gst_pct": p.get("consent_gst_pct"),
        "consent_terms_version": p.get("consent_terms_version"),
        "pushed_by": p.get("consent_pushed_by") or "",
        "pushed_at": p.get("consent_pushed_at"),
        "link_sent_count": p.get("link_sent_count") or 0,
        "link_sent_at": p.get("link_sent_at"),
        "is_l2": await claim_is_l2(claim_id),
        "current_fee_pct": cfg["fee_pct"],
        "current_gst_pct": cfg["gst_pct"],
        "terms_version": cfg["terms_version"],
    }
