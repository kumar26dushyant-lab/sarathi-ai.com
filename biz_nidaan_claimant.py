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
    version = (await _nidaan.get_ops_setting("claimant_terms_version", "v1-draft") or "v1-draft").strip()
    terms_html = await _nidaan.get_ops_setting("claimant_terms_html", "") or ""
    return {
        "fee_pct": fee_pct,
        "gst_enabled": bool(gst.get("enabled")),
        "gst_pct": float(gst.get("rate") or 18.0) if gst.get("enabled") else 0.0,
        "terms_version": version,
        "terms_html": terms_html,
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
            "       c.status AS claim_status, c.stage AS claim_stage, c.disputed_amount "
            "FROM nidaan_claimant_portal p JOIN nidaan_claims c ON c.claim_id=p.claim_id "
            "WHERE p.access_token=?", (token,))).fetchone()
    return dict(row) if row else None


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
    """Stamp the first time the claimant actually opened their portal (only sets once)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claimant_portal SET activated_at=CURRENT_TIMESTAMP "
            "WHERE claim_id=? AND activated_at IS NULL", (claim_id,))
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


async def record_consent(claim_id: int, ip: str = "") -> dict:
    """Digital acceptance of the success-fee terms. Snapshots the % + GST + T&C version that apply
    RIGHT NOW so a later config change never alters an accepted agreement (grandfathered).
    Idempotent: if already accepted, returns the existing record unchanged."""
    existing = await get_portal(claim_id)
    if existing and existing.get("consent_accepted_at"):
        return {"ok": True, "already": True, "portal": existing}
    cfg = await fee_config()
    await ensure_portal(claim_id, with_token=False)  # make sure a row exists
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claimant_portal SET consent_accepted_at=CURRENT_TIMESTAMP, "
            "consent_terms_version=?, consent_fee_pct=?, consent_gst_pct=?, consent_ip=? "
            "WHERE claim_id=?",
            (cfg["terms_version"], cfg["fee_pct"], cfg["gst_pct"], (ip or "")[:64], claim_id))
        await conn.commit()
    logger.info("Claimant consent recorded: claim=%s fee=%s%% gst=%s%% ver=%s",
                claim_id, cfg["fee_pct"], cfg["gst_pct"], cfg["terms_version"])
    return {"ok": True, "already": False, "portal": await get_portal(claim_id)}


async def portal_state(claim_id: int) -> dict:
    """Consolidated state for the ops L2 claim view: does a portal exist, has the claimant opened
    it, have they accepted the fee terms, how many times we sent the link. Never raises."""
    p = await get_portal(claim_id)
    cfg = await fee_config()
    if not p:
        return {"exists": False, "activated": False, "consent_accepted": False,
                "link_sent_count": 0, "current_fee_pct": cfg["fee_pct"],
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
        "link_sent_count": p.get("link_sent_count") or 0,
        "link_sent_at": p.get("link_sent_at"),
        "current_fee_pct": cfg["fee_pct"],
        "current_gst_pct": cfg["gst_pct"],
        "terms_version": cfg["terms_version"],
    }
