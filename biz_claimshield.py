#  biz_claimshield.py — Nidaan Partner ↔ ClaimShield.in (Level-2 legal) integration
#  ---------------------------------------------------------------------------------
#  Isolated, additive module. Nothing here touches existing claim flows except the
#  status it records against a claim (additive columns). Two directions:
#    OUTBOUND  Nidaan → ClaimShield : create a case (we send our case ref + minimal
#              data). ClaimShield stores our ref and works the case. (Wired later,
#              once ClaimShield shares the exact create-case endpoint/spec.)
#    INBOUND   ClaimShield → Nidaan : on any progress they POST our case ref + their
#              raw status to our webhook; we map it to a friendly, bilingual bucket
#              and show it on the customer's dashboard. (Built + self-testable now.)
#
#  De-duplication is OURS to own (ClaimShield does not dedupe): a case is sent at most
#  once (guarded by claimshield_case_id / claimshield_sent_at).

import json
import logging
from typing import Optional

import aiosqlite

import biz_nidaan as _n  # for DB_PATH + ops-setting helpers (single source of truth)

logger = logging.getLogger("biz_claimshield")

DB_PATH = _n.DB_PATH

# ── Status mapping ────────────────────────────────────────────────────────────
# ClaimShield's ~40 internal statuses → 14 customer-facing buckets (their suggested
# mapping). Raw keys are matched case-insensitively. We SHOW the bucket, but also
# store the raw status for ops/debugging. Bucket labels are editable later via ops
# settings; these are the defaults.
_RAW_TO_BUCKET = {
    "new case": "registered", "nidaan partner case": "registered",
    "pending doc": "docs_pending", "draft query": "docs_pending",
    "pending draft": "docs_pending", "draft generated": "docs_pending",
    "medical query": "docs_pending", "in medical": "docs_pending",
    "pending approval": "under_review", "referred to senior": "under_review",
    "approved": "approved",
    "waiting for customer approval": "awaiting_authorization",
    "rejected": "not_approved", "reject reconsideration": "not_approved",
    "live": "case_active", "legal generated": "case_active",
    "legal notice": "case_active", "court petition": "case_active",
    "escalation pending": "escalated_insurer", "escalation query": "escalated_insurer",
    "escalated": "escalated_insurer",
    "lokpal pending": "ombudsman", "lokpal registered": "ombudsman",
    "annexure5 pending": "ombudsman", "annexure5 replied": "ombudsman",
    "annexure 6 pending": "ombudsman", "annexure 6 replied": "ombudsman",
    "hearing": "ombudsman",
    "reimbursement": "reimbursement", "reimbursement pending": "reimbursement",
    "reimbursement query": "reimbursement",
    "pending payment": "fee_pending",
    "settlement completed": "settlement", "reimbursement settlement": "settlement",
    "disputed payment": "settlement", "part payment": "settlement",
    "hold return": "settlement",
    "completed": "completed", "case closed": "completed",
    "cp payment pending": "completed",
    "hold": "on_hold",
}

# Bucket → friendly labels (Tier II/III simple wording, EN / HI / Hinglish).
_BUCKET_LABELS = {
    "registered":            {"en": "Case Registered",         "hi": "केस दर्ज हुआ",              "hinglish": "Case register ho gaya"},
    "docs_pending":          {"en": "Documents Pending",       "hi": "दस्तावेज़ बाकी हैं",         "hinglish": "Documents pending hain"},
    "under_review":          {"en": "Under Review",            "hi": "समीक्षा जारी है",           "hinglish": "Review ho raha hai"},
    "approved":              {"en": "Approved",                "hi": "स्वीकृत",                   "hinglish": "Approve ho gaya"},
    "awaiting_authorization":{"en": "Awaiting Your Approval",  "hi": "आपकी मंज़ूरी बाकी है",       "hinglish": "Aapki approval baaki hai"},
    "not_approved":          {"en": "Not Approved",            "hi": "स्वीकृत नहीं हुआ",           "hinglish": "Approve nahi hua"},
    "case_active":           {"en": "Case Active (Legal)",     "hi": "केस सक्रिय (कानूनी)",        "hinglish": "Case active hai (legal)"},
    "escalated_insurer":     {"en": "Escalated to Insurer",    "hi": "बीमा कंपनी को भेजा गया",     "hinglish": "Insurer ko escalate kiya"},
    "ombudsman":             {"en": "With Insurance Ombudsman","hi": "बीमा लोकपाल के पास",         "hinglish": "Insurance Ombudsman ke paas"},
    "reimbursement":         {"en": "Reimbursement in Process","hi": "भुगतान की प्रक्रिया जारी",   "hinglish": "Reimbursement process me hai"},
    "fee_pending":           {"en": "Fee Payment Pending",     "hi": "शुल्क भुगतान बाकी है",       "hinglish": "Fee payment baaki hai"},
    "settlement":            {"en": "Settlement in Progress",  "hi": "निपटान जारी है",            "hinglish": "Settlement chal raha hai"},
    "completed":             {"en": "Case Completed",          "hi": "केस पूरा हुआ",              "hinglish": "Case complete ho gaya"},
    "on_hold":               {"en": "On Hold",                 "hi": "रोका गया है",               "hinglish": "Hold par hai"},
    # Fallback for any status ClaimShield adds later that we haven't mapped yet.
    "unknown":               {"en": "In Progress",             "hi": "प्रक्रिया जारी है",         "hinglish": "Process me hai"},
}


def map_status(raw: str) -> dict:
    """Map a ClaimShield raw status → {bucket, labels{en,hi,hinglish}}. Unknown raw
    statuses fall back to 'unknown' (shown as a safe 'In Progress') so a new status on
    their side never breaks the customer's dashboard."""
    key = (raw or "").strip().lower()
    bucket = _RAW_TO_BUCKET.get(key, "unknown")
    return {"bucket": bucket, "labels": _BUCKET_LABELS[bucket]}


def all_buckets() -> dict:
    """The full bucket→labels map (for the ops mapping/reference view)."""
    return dict(_BUCKET_LABELS)


# ── Schema (additive, ALTER-on-first-use — never blocks on an existing DB) ─────
async def _ensure_schema(conn) -> None:
    for col, typ in (
        ("claimshield_case_id", "TEXT"),
        ("claimshield_status_raw", "TEXT"),
        ("claimshield_bucket", "TEXT"),
        ("claimshield_status_at", "TIMESTAMP"),
        ("claimshield_sent_at", "TIMESTAMP"),
        ("claimshield_sent_by", "TEXT"),      # ops person who pushed it (accountability)
    ):
        try:
            await conn.execute(f"ALTER TABLE nidaan_claims ADD COLUMN {col} {typ}")
        except Exception:
            pass
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS nidaan_claimshield_log (
               log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
               claim_id     INTEGER NOT NULL,
               raw_status   TEXT,
               bucket       TEXT,
               source       TEXT,          -- 'claimshield' | 'ops' | 'system'
               created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )""")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cs_log_claim ON nidaan_claimshield_log(claim_id)")


def parse_case_ref(case_ref) -> Optional[int]:
    """Turn whatever ClaimShield sends back as our reference into a claim_id.
    Accepts a plain number (45) or a string like 'NIDAAN-045' / '#45'."""
    if case_ref is None:
        return None
    s = str(case_ref).strip()
    if s.isdigit():
        return int(s)
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else None


# ── INBOUND: record a status pushed by ClaimShield ────────────────────────────
async def record_status_update(case_ref, raw_status: str, source: str = "claimshield",
                               cs_case_ref: str = "") -> dict:
    """Persist a status ClaimShield pushed for our case. ClaimShield maps to customer-safe
    statuses on THEIR side, so we display their text AS-IS (the bucket map is only a
    best-effort category/fallback). Matches by our claim id (Nidaanpartnercasenumber) OR their
    caseReferenceNumber. If ClaimShield includes their caseReferenceNumber (cs_case_ref), we
    STORE/correct it on the claim — so a stale reference self-heals from their own status pushes.
    Idempotent: a repeat of the same status just refreshes the timestamp."""
    m = map_status(raw_status)
    bucket = m["bucket"]
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_schema(conn)
        conn.row_factory = aiosqlite.Row
        # Match on our Nidaan claim id first; fall back to their caseReferenceNumber.
        claim_id = parse_case_ref(case_ref)
        row = None
        if claim_id:
            row = await (await conn.execute(
                "SELECT claim_id, claimshield_status_raw FROM nidaan_claims WHERE claim_id=?",
                (claim_id,))).fetchone()
        if not row and case_ref is not None:
            row = await (await conn.execute(
                "SELECT claim_id, claimshield_status_raw FROM nidaan_claims "
                "WHERE claimshield_case_id=?", (str(case_ref).strip(),))).fetchone()
        if not row:
            return {"ok": False, "error": "claim_not_found", "claim_id": claim_id}
        claim_id = row["claim_id"]
        prev_raw = (row["claimshield_status_raw"] or "")
        changed = (prev_raw.strip().lower() != (raw_status or "").strip().lower())
        # Self-heal the ClaimShield reference from their own push (only overwrite with a real value).
        _csref = (str(cs_case_ref).strip() if cs_case_ref else "")
        if _csref:
            await conn.execute(
                "UPDATE nidaan_claims SET claimshield_case_id=? WHERE claim_id=?",
                (_csref, claim_id))
        await conn.execute(
            "UPDATE nidaan_claims SET claimshield_status_raw=?, claimshield_bucket=?, "
            "claimshield_status_at=CURRENT_TIMESTAMP WHERE claim_id=?",
            ((raw_status or "").strip(), bucket, claim_id))
        if changed:
            await conn.execute(
                "INSERT INTO nidaan_claimshield_log (claim_id, raw_status, bucket, source) "
                "VALUES (?, ?, ?, ?)", (claim_id, (raw_status or "").strip(), bucket, source))
        await conn.commit()
    return {"ok": True, "claim_id": claim_id, "bucket": bucket,
            "labels": m["labels"], "changed": changed}


async def get_claimshield_state(claim_id: int) -> Optional[dict]:
    """Current ClaimShield status + full timeline for a claim (customer/ops display)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_schema(conn)
        conn.row_factory = aiosqlite.Row
        c = await (await conn.execute(
            "SELECT claimshield_case_id, claimshield_status_raw, claimshield_bucket, "
            "claimshield_status_at, claimshield_sent_at FROM nidaan_claims WHERE claim_id=?",
            (claim_id,))).fetchone()
        if not c:
            return None
        bucket = c["claimshield_bucket"]
        logs = [dict(r) for r in await (await conn.execute(
            "SELECT raw_status, bucket, created_at FROM nidaan_claimshield_log "
            "WHERE claim_id=? ORDER BY log_id ASC", (claim_id,))).fetchall()]
    return {
        "case_id": c["claimshield_case_id"],
        "sent": bool(c["claimshield_sent_at"]),
        # ClaimShield sends customer-safe text → show it AS-IS; bucket is best-effort only.
        "display": c["claimshield_status_raw"],
        "bucket": bucket,
        "status_at": c["claimshield_status_at"],
        "timeline": [{"status": l["raw_status"], "bucket": l["bucket"],
                      "at": l["created_at"]} for l in logs],
    }


# ── OUTBOUND: create a case at ClaimShield (SCAFFOLD — awaiting their exact spec) ─
def is_configured() -> bool:
    """True only when the ClaimShield endpoint + key are present. Until then, and
    until the exact create-case spec is known, outbound stays inert."""
    import os
    return bool(os.getenv("CLAIMSHIELD_API_BASE") and os.getenv("CLAIMSHIELD_API_KEY"))


async def mark_case_sent(claim_id: int, claimshield_case_id: str = "", sent_by: str = "") -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_schema(conn)
        await conn.execute(
            "UPDATE nidaan_claims SET claimshield_sent_at=CURRENT_TIMESTAMP, "
            "claimshield_case_id=COALESCE(NULLIF(?,''), claimshield_case_id), "
            "claimshield_sent_by=COALESCE(NULLIF(?,''), claimshield_sent_by) WHERE claim_id=?",
            (claimshield_case_id or "", (sent_by or "").strip()[:80], claim_id))
        await conn.commit()


async def already_sent(claim_id: int) -> bool:
    """Idempotency guard — never create the same case twice (ClaimShield doesn't dedupe)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_schema(conn)
        row = await (await conn.execute(
            "SELECT claimshield_sent_at, claimshield_case_id FROM nidaan_claims WHERE claim_id=?",
            (claim_id,))).fetchone()
    return bool(row and (row[0] or row[1]))

async def create_case(claim_id: int, reason: str = "", sent_by: str = "") -> dict:
    """Create a case at ClaimShield for a Nidaan claim. Sends ONLY name/mobile/amount +
    our case number (their spec). Idempotent — never sends twice (they don't dedupe).
    `reason` is the staff justification for the L2 move — recorded on the timeline.
    `sent_by` is the ops person's name — stored for accountability (shown in L2 dashboard).
    Returns {ok, already?, case_id?, error?}.

    Spec (ClaimShield, Aug 15):
      POST {base}/api/partnercreatecase   header x-api-key: <key>
      body {patientName, patientMobile, claimAmount, Nidaanpartnercasenumber}
      resp {message:"success", caseReferenceNumber:<int>}
    """
    import os
    import httpx
    # Canonical host is non-www; www.claimshield.in 307-redirects (which would drop the
    # POST body / risk forwarding the api-key), so default to the canonical host.
    base = os.getenv("CLAIMSHIELD_API_BASE", "https://claimshield.in").rstrip("/")
    key = os.getenv("CLAIMSHIELD_API_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "not_configured"}
    if await already_sent(claim_id):
        return {"ok": True, "already": True}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        c = await (await conn.execute(
            "SELECT claim_id, insured_name, insured_phone, disputed_amount, "
            "       review_outcome, l2_payment_status, payment_status "
            "FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    if not c:
        return {"ok": False, "error": "claim_not_found"}
    # GUARD: only a reviewed-GO ('can_fight') claim can go to L2. Payment is NOT required
    # here — a super-admin may MANUALLY override-send a still-due claim (their name is
    # recorded for accountability). PAID claims are auto-sent via auto_send_if_eligible().
    if c["review_outcome"] != "can_fight":
        return {"ok": False, "error": "not_eligible",
                "detail": f"review_outcome={c['review_outcome']} — only reviewed-GO claims go to L2"}
    payload = {
        "patientName": (c["insured_name"] or "").strip(),
        "patientMobile": "".join(ch for ch in (c["insured_phone"] or "") if ch.isdigit())[-10:],
        "claimAmount": str(int(c["disputed_amount"] or 0)),
        "Nidaanpartnercasenumber": str(claim_id),
    }
    try:
        async with httpx.AsyncClient(timeout=25.0) as cl:
            r = await cl.post(f"{base}/api/partnercreatecase", json=payload,
                              headers={"x-api-key": key, "Content-Type": "application/json"})
        data = r.json() if r.content else {}
    except Exception as e:
        logger.warning("claimshield create_case network error claim=%s: %s", claim_id, e)
        return {"ok": False, "error": "network"}
    if r.status_code == 200 and str(data.get("message", "")).strip().lower() == "success":
        cs_ref = str(data.get("caseReferenceNumber", "") or "")
        await mark_case_sent(claim_id, cs_ref, sent_by=sent_by)
        # Claim just entered L2 → open the claimant's direct portal + greet them (flag-gated,
        # best-effort, never blocks the L2 move). Covers both auto and manual-push paths.
        try:
            import asyncio as _aio
            import biz_nidaan_claimant as _cl
            _aio.create_task(_cl.on_claim_reached_l2(claim_id))
        except Exception:
            pass
        _by = (f" by {sent_by.strip()}" if sent_by and sent_by.strip() else "")
        _note = "Sent to ClaimShield" + _by + (f" — {reason.strip()[:400]}" if reason and reason.strip() else "")
        async with aiosqlite.connect(DB_PATH) as conn:
            await _ensure_schema(conn)
            await conn.execute(
                "INSERT INTO nidaan_claimshield_log (claim_id, raw_status, bucket, source) "
                "VALUES (?, ?, ?, ?)", (claim_id, _note, "registered", "ops"))
            await conn.commit()
        return {"ok": True, "case_id": cs_ref}
    logger.warning("claimshield create_case rejected claim=%s status=%s body=%s",
                   claim_id, r.status_code, str(data)[:300])
    return {"ok": False, "error": "rejected", "status_code": r.status_code, "detail": str(data)[:200]}


def _claim_is_paid(row) -> bool:
    """Paid for L2 = branch/staff L2 fee paid, OR retail ₹499 review paid, OR subscriber."""
    return (row["l2_payment_status"] == "paid") or (row["payment_status"] in ("paid", "subscription"))


async def auto_send_if_eligible(claim_id: int) -> dict:
    """Owner rule: a PAID + reviewed-GO claim moves to ClaimShield AUTOMATICALLY (no
    manual button). Called from the payment/review state-changes. Idempotent, flag-gated
    (ops setting 'claimshield_auto_send', default ON), and best-effort — never blocks the
    caller. sent_by is stamped as an auto action (distinct from a person's manual push)."""
    # MASTER routing switch — when paused, L2 stays in NidaanPartner (no auto, no manual).
    try:
        master = await _n.get_ops_setting("claimshield_routing_enabled", "1")
    except Exception:
        master = "1"
    if str(master).strip().lower() not in ("1", "true", "on", "yes"):
        return {"ok": False, "error": "routing_paused"}
    try:
        flag = await _n.get_ops_setting("claimshield_auto_send", "1")
    except Exception:
        flag = "1"
    if str(flag).strip().lower() not in ("1", "true", "on", "yes"):
        return {"ok": False, "error": "auto_send_off"}
    if not is_configured():
        return {"ok": False, "error": "not_configured"}
    if await already_sent(claim_id):
        return {"ok": True, "already": True}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        c = await (await conn.execute(
            "SELECT review_outcome, l2_payment_status, payment_status "
            "FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    if not c or c["review_outcome"] != "can_fight" or not _claim_is_paid(c):
        return {"ok": False, "error": "not_eligible_auto"}
    # Phase 3 GATE: auto-send waits for the claimant's authorization acceptance (founder
    # decision). The MANUAL "send to ClaimShield" button calls create_case() directly and
    # deliberately bypasses this gate, so ops can still push a case without acceptance.
    try:
        gate = await _n.get_ops_setting("claimshield_require_acceptance", "1")
    except Exception:
        gate = "1"
    if str(gate).strip().lower() in ("1", "true", "on", "yes"):
        try:
            import biz_nidaan_claimant as _cl
            st = await _cl.portal_state(claim_id)
            if not st.get("consent_accepted"):
                # Not accepted yet → don't send. Make sure the claimant has been asked to
                # authorize (idempotent: ensures the portal + greeting/magic-link email).
                try:
                    await _cl.on_claim_reached_l2(claim_id)
                except Exception:
                    pass
                return {"ok": False, "error": "awaiting_acceptance"}
        except Exception as _ge:
            # If the acceptance check itself fails, be conservative and do NOT auto-send.
            return {"ok": False, "error": "acceptance_check_failed"}
    return await create_case(claim_id, reason="Auto — payment + claimant authorization",
                             sent_by="Auto (payment + authorization)")
