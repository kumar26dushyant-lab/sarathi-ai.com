# =============================================================================
#  biz_nidaan.py — Nidaan Partner: The Legal Consultants LLP
#  Phase 1b skeleton — DB helpers, auth, claims, subscriptions
# =============================================================================
#
#  Architecture: plug-and-play.  No Sarathi tables are modified here.
#  The only join point is product_link(nidaan_account_id, sarathi_tenant_id).
#
#  Plans (MONTHLY or ANNUAL Razorpay subscriptions — no quarterly). Base prices; GST added on top.
#    silver   — ₹499/month  (1 user,  3 claims/month,  legal review, up to ₹5L/claim)
#    gold     — ₹999/month  (5 users, 3 claims/month,  + Sarathi bundle, up to ₹10L/claim)
#    platinum — ₹1999/month (unlimited users, 10 claims/month, + Sarathi bundle, up to ₹50L/claim)
#    (annual variants = ~10 months' price; quotas from PLAN_LIMITS/config, enforced PER MONTH.)
#
# =============================================================================

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, date, timedelta
from typing import Optional

import aiosqlite

import biz_platform_bridge as bridge  # Sarathi ⇄ Nidaan boundary (tenants/agents access)

logger = logging.getLogger("sarathi.nidaan")

DB_PATH = os.environ.get("DB_PATH", "sarathi_biz.db")

# ── Plan limits ───────────────────────────────────────────────────────────────
PLAN_LIMITS: dict[str, dict] = {
    # Monthly plans (billed monthly, cancel anytime). Caps: claims per 30-day window
    # (HARD-enforced in can_submit_claim) + max DISPUTED value per claim (`disputed_cap`,
    # SOFT — the claim form educates + nudges an upgrade, but doesn't hard-block).
    #   Silver   ₹500  · 3 claims/mo · ≤ ₹5L each  · 1 CRM seat
    #   Gold     ₹999  · 3 claims/mo · ≤ ₹10L each · 5 CRM seats
    #   Platinum ₹1999 · 10 claims/mo · ≤ ₹50L each · unlimited CRM seats
    "silver":          {"price": 500,   "max_users": 1,    "claims_per_month": 3,  "disputed_cap": 500000,   "sarathi_bundle": True},
    "gold":            {"price": 999,   "max_users": 5,    "claims_per_month": 3,  "disputed_cap": 1000000,  "sarathi_bundle": True},
    "platinum":        {"price": 1999,  "max_users": None, "claims_per_month": 10, "disputed_cap": 5000000,  "sarathi_bundle": True},
    # Annual variants — same claim allowance + caps, billed yearly (10× monthly = 2 months free)
    "silver_annual":   {"price": 5000,  "max_users": 1,    "claims_per_month": 3,  "disputed_cap": 500000,   "sarathi_bundle": True},
    "gold_annual":     {"price": 9990,  "max_users": 5,    "claims_per_month": 3,  "disputed_cap": 1000000,  "sarathi_bundle": True},
    "platinum_annual": {"price": 19990, "max_users": None, "claims_per_month": 10, "disputed_cap": 5000000,  "sarathi_bundle": True},
}

# ── Plan config (DB-backed, super-admin editable) ─────────────────────────────
# PLAN_LIMITS + NIDAAN_RAZORPAY_PLANS (below) are the SEED/defaults. Once seeded into
# nidaan_plans_config, THAT table is the single source of truth — editable from ops with
# no code changes. get_plans_config() reads it (cached); accessors below derive from it,
# with a safe fallback to the hardcoded defaults until the table is seeded.
_PLANS_CACHE: dict | None = None


async def seed_plans_config():
    """Create the plan-config table + seed it from the hardcoded defaults (once)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS nidaan_plans_config (
                plan_key TEXT PRIMARY KEY,
                label TEXT, tier TEXT, billing TEXT,
                price_paise INTEGER, claims_per_month INTEGER, disputed_cap INTEGER,
                max_users INTEGER, sarathi_bundle INTEGER DEFAULT 1,
                features TEXT DEFAULT '[]', badge TEXT DEFAULT '',
                razorpay_plan_id TEXT DEFAULT '', period TEXT, interval_n INTEGER DEFAULT 1,
                period_days INTEGER, active INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        # Default selling-point features per tier (the caps — claims/₹ — are rendered
        # separately from the cap fields, so these are the NON-cap bullets).
        DEFAULT_FEATURES = {
            "silver":   ["Sarathi-AI CRM (sarathi-ai.com) — FREE", "SMS status updates",
                         "Success fee only after resolution"],
            "gold":     ["Sarathi-AI CRM (sarathi-ai.com) — FREE", "Priority SMS + email updates",
                         "Success fee only after resolution"],
            "platinum": ["Sarathi-AI CRM (sarathi-ai.com) — FREE", "Priority SMS + email updates",
                         "Success fee only after resolution"],
        }
        cur = await conn.execute("SELECT COUNT(*) FROM nidaan_plans_config")
        if (await cur.fetchone())[0] > 0:
            # One-time backfill: the first seed stored empty features. Only touches rows
            # still at the empty '[]' default, so an admin's edited features are preserved.
            for tier, feats in DEFAULT_FEATURES.items():
                await conn.execute(
                    "UPDATE nidaan_plans_config SET features=? "
                    "WHERE tier=? AND (features IS NULL OR features='' OR features='[]')",
                    (json.dumps(feats), tier))
            await conn.commit()
            return
        order = {"silver": 1, "gold": 2, "platinum": 3,
                 "silver_annual": 4, "gold_annual": 5, "platinum_annual": 6}
        for key, lim in PLAN_LIMITS.items():
            rz = NIDAAN_RAZORPAY_PLANS.get(key, {})
            tier = key.replace("_annual", "")
            billing = "yearly" if key.endswith("_annual") else "monthly"
            await conn.execute(
                """INSERT OR IGNORE INTO nidaan_plans_config
                   (plan_key,label,tier,billing,price_paise,claims_per_month,disputed_cap,
                    max_users,sarathi_bundle,features,badge,period,interval_n,period_days,
                    active,sort_order)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, tier.capitalize(), tier, billing,
                 rz.get("amount_paise") or (lim.get("price", 0) * 100),
                 lim.get("claims_per_month"), lim.get("disputed_cap"), lim.get("max_users"),
                 1 if lim.get("sarathi_bundle") else 0,
                 json.dumps(DEFAULT_FEATURES.get(tier, [])),
                 "MOST POPULAR" if tier == "gold" else "",
                 rz.get("period", "monthly"), rz.get("interval", 1), rz.get("period_days"),
                 1, order.get(key, 99)))
        await conn.commit()
        logger.info("nidaan_plans_config seeded from defaults (%d plans)", len(PLAN_LIMITS))


# =============================================================================
#  CANONICAL CONTENT (single source of truth for business facts) — super-admin editable.
#  Both the chat KB and the homepage read from here → edit a fact once, it updates everywhere.
# =============================================================================
_CONTENT_CACHE: dict | None = None

DEFAULT_CONTENT = {
    "jurisdictions":     {"label": "Jurisdictions served",
        "en": "Madhya Pradesh, Chhattisgarh, Maharashtra, Rajasthan & Punjab",
        "hi": "मध्य प्रदेश, छत्तीसगढ़, महाराष्ट्र, राजस्थान और पंजाब"},
    "support_hours":     {"label": "Support hours",
        "en": "Monday–Friday, 10am–6pm IST",
        "hi": "सोमवार–शुक्रवार, सुबह 10 – शाम 6 IST"},
    "review_turnaround": {"label": "₹499 review turnaround",
        "en": "48–72 business hours",
        "hi": "48–72 कार्य घंटे"},
    "success_fee":       {"label": "Success-fee terms",
        "en": "Success fee applies only after your claim is resolved — discussed case-by-case.",
        "hi": "सफलता शुल्क केवल आपका क्लेम हल होने के बाद लागू होता है — केस के अनुसार तय।"},
    "resolution_stance": {"label": "Resolution stance",
        "en": "Resolution time depends on the complexity of each case — we always pursue the earliest possible resolution.",
        "hi": "समाधान का समय हर मामले की जटिलता पर निर्भर करता है — हम हमेशा जल्द से जल्द समाधान का प्रयास करते हैं।"},
    "refund_window":     {"label": "Refund window",
        "en": "The ₹499 review can be refunded within 2 hours of payment; after that it is non-refundable.",
        "hi": "₹499 समीक्षा भुगतान के 2 घंटे के भीतर वापस की जा सकती है; उसके बाद वापसी नहीं।"},
    "audience":          {"label": "Who it's for",
        "en": "For policyholders without an advisor, and for insurance advisors/agents.",
        "hi": "बिना सलाहकार वाले पॉलिसीधारकों और बीमा सलाहकारों/एजेंटों के लिए।"},
    "go_no_go":          {"label": "Go / no-go framing",
        "en": "We provide an expert review — a clear go/no-go on whether a claim can be fought. We never guarantee an outcome.",
        "hi": "हम विशेषज्ञ समीक्षा देते हैं — क्लेम लड़ा जा सकता है या नहीं, स्पष्ट go/no-go। हम कभी परिणाम की गारंटी नहीं देते।"},
}


async def seed_content_config():
    """Create + seed the canonical content table (once) from DEFAULT_CONTENT."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS nidaan_content (
            content_key TEXT PRIMARY KEY, label TEXT DEFAULT '',
            value_en TEXT DEFAULT '', value_hi TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        for key, d in DEFAULT_CONTENT.items():
            await conn.execute(
                "INSERT OR IGNORE INTO nidaan_content (content_key, label, value_en, value_hi) VALUES (?,?,?,?)",
                (key, d["label"], d["en"], d["hi"]))
        await conn.commit()


_CONTENT_CACHE_TS = 0.0
_CONTENT_TTL = 30.0   # seconds — bounds cross-worker staleness after an edit (2 web workers)


async def get_content(force: bool = False) -> dict:
    """All canonical facts as {key: {label, en, hi}} — cached with a short TTL so an edit on one
    worker propagates to the others within TTL. Falls back to DEFAULT_CONTENT."""
    global _CONTENT_CACHE, _CONTENT_CACHE_TS
    import time as _t
    if not force and _CONTENT_CACHE is not None and (_t.time() - _CONTENT_CACHE_TS) < _CONTENT_TTL:
        return _CONTENT_CACHE
    out: dict = {}
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            for r in await (await conn.execute(
                    "SELECT content_key, label, value_en, value_hi FROM nidaan_content")).fetchall():
                out[r["content_key"]] = {"label": r["label"], "en": r["value_en"], "hi": r["value_hi"]}
    except Exception:
        pass
    for key, d in DEFAULT_CONTENT.items():   # ensure every known key exists (fallback)
        out.setdefault(key, {"label": d["label"], "en": d["en"], "hi": d["hi"]})
    import time as _t
    _CONTENT_CACHE = out
    _CONTENT_CACHE_TS = _t.time()
    return out


def invalidate_content_cache():
    global _CONTENT_CACHE, _CONTENT_CACHE_TS
    _CONTENT_CACHE = None
    _CONTENT_CACHE_TS = 0.0


async def update_content(key: str, value_en: str, value_hi: str) -> dict:
    """Update one canonical fact (super-admin, enforced at route). Only known keys."""
    if key not in DEFAULT_CONTENT:
        raise ValueError("unknown_content_key")
    en = (value_en or "").strip()[:600]
    hi = (value_hi or "").strip()[:600]
    if not en:
        raise ValueError("value_en_required")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO nidaan_content (content_key, label, value_en, value_hi, updated_at)
               VALUES (?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(content_key) DO UPDATE SET value_en=excluded.value_en,
                   value_hi=excluded.value_hi, updated_at=CURRENT_TIMESTAMP""",
            (key, DEFAULT_CONTENT[key]["label"], en, hi))
        await conn.commit()
    invalidate_content_cache()
    return (await get_content(force=True)).get(key, {})


async def all_content() -> list[dict]:
    cfg = await get_content(force=True)
    return [{"key": k, "label": v["label"], "en": v["en"], "hi": v["hi"]} for k, v in cfg.items()]


async def public_content() -> dict:
    """{key: {en, hi}} for the homepage (both languages)."""
    cfg = await get_content()
    return {k: {"en": v["en"], "hi": v["hi"]} for k, v in cfg.items()}


# ── Go/no-go review templates (super-admin managed; picked at review delivery) ──
DEFAULT_REVIEW_TEMPLATES = [
    ("can_fight", "Standard — Can be challenged",
     "Based on our expert legal review of your claim documents, we find valid grounds to challenge "
     "the rejection/underpayment of your claim. Our legal team will contact you shortly to take "
     "your case forward. Please keep your policy and claim documents handy."),
    ("no_scope", "Standard — Settled / no scope",
     "Based on our expert legal review, your claim appears to have been dealt with in line with your "
     "policy terms, and we do not find sufficient grounds to challenge it further. We'll be glad to "
     "assist you with any future claims — thank you for trusting Nidaan Partner."),
]


async def seed_review_templates():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS nidaan_review_templates (
            template_id INTEGER PRIMARY KEY AUTOINCREMENT, outcome TEXT NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL, active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        n = (await (await conn.execute("SELECT COUNT(*) FROM nidaan_review_templates")).fetchone())[0]
        if n == 0:
            for i, (oc, title, body) in enumerate(DEFAULT_REVIEW_TEMPLATES):
                await conn.execute(
                    "INSERT INTO nidaan_review_templates (outcome,title,body,sort_order) VALUES (?,?,?,?)",
                    (oc, title, body, i))
            await conn.commit()


async def list_review_templates(outcome: Optional[str] = None, active_only: bool = True) -> list[dict]:
    where, params = [], []
    if outcome in ("can_fight", "no_scope"):
        where.append("outcome=?"); params.append(outcome)
    if active_only:
        where.append("active=1")
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            f"SELECT template_id, outcome, title, body, active, sort_order "
            f"FROM nidaan_review_templates {wsql} ORDER BY outcome, sort_order, template_id", params)).fetchall()
        return [dict(r) for r in rows]


async def create_review_template(outcome: str, title: str, body: str) -> Optional[int]:
    if outcome not in ("can_fight", "no_scope"):
        raise ValueError("bad_outcome")
    title = (title or "").strip()[:120]
    body = (body or "").strip()[:4000]
    if not title or not body:
        raise ValueError("title_and_body_required")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_review_templates (outcome,title,body) VALUES (?,?,?)",
            (outcome, title, body))
        await conn.commit()
        return cur.lastrowid


async def update_review_template(template_id: int, *, title: Optional[str] = None,
                                 body: Optional[str] = None, active: Optional[bool] = None) -> bool:
    sets, params = [], []
    if title is not None:
        t = title.strip()[:120]
        if not t:
            raise ValueError("title_required")
        sets.append("title=?"); params.append(t)
    if body is not None:
        b = body.strip()[:4000]
        if not b:
            raise ValueError("body_required")
        sets.append("body=?"); params.append(b)
    if active is not None:
        sets.append("active=?"); params.append(1 if active else 0)
    if not sets:
        return False
    params.append(template_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            f"UPDATE nidaan_review_templates SET {', '.join(sets)} WHERE template_id=?", params)
        await conn.commit()
        return cur.rowcount > 0


async def delete_review_template(template_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "DELETE FROM nidaan_review_templates WHERE template_id=?", (template_id,))
        await conn.commit()
        return cur.rowcount > 0


def content_facts_block(cfg: dict, lang: str = "en") -> str:
    """An authoritative facts block for the chat KB, built from the canonical content."""
    L = lang if lang in ("hi",) else "en"
    lines = []
    for key, v in (cfg or {}).items():
        val = v.get(L) or v.get("en") or ""
        if val:
            lines.append(f"- {v.get('label', key)}: {val}")
    return "\n".join(lines)


async def get_plans_config(force: bool = False) -> dict:
    """All plans as {plan_key: {...}} — cached. Single source of truth once seeded."""
    global _PLANS_CACHE
    if _PLANS_CACHE is not None and not force:
        return _PLANS_CACHE
    out: dict = {}
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT * FROM nidaan_plans_config")
            for r in await cur.fetchall():
                d = dict(r)
                try:
                    d["features"] = json.loads(d.get("features") or "[]")
                except Exception:
                    d["features"] = []
                out[d["plan_key"]] = d
    except Exception:
        out = {}
    _PLANS_CACHE = out
    return out


async def get_plan_cfg(plan_key: str) -> dict:
    return (await get_plans_config()).get(plan_key, {})


def invalidate_plans_cache():
    global _PLANS_CACHE
    _PLANS_CACHE = None


# Fields the super-admin editor may change. `price` is accepted in RUPEES and stored as
# price_paise. Because checkout uses one-time Razorpay ORDERS (amount set server-side at
# order creation from this config), a price change flows straight to NEW checkouts with no
# Razorpay-plan re-creation — and existing subscribers are grandfathered automatically
# (their subscription row already holds the amount Razorpay actually charged them).
_EDITABLE_PLAN_FIELDS = {"label", "price", "claims_per_month", "disputed_cap", "max_users",
                         "features", "badge", "active", "sort_order"}


async def update_plan_config(plan_key: str, fields: dict) -> dict:
    """Validated update of an EXISTING plan's config (super-admin only, enforced at the
    route). Whitelists fields, coerces + bounds-checks values, parameterizes the query, and
    invalidates the cache. Returns the updated plan. Raises ValueError on bad input."""
    cfg = await get_plans_config(force=True)
    if plan_key not in cfg:
        raise ValueError("unknown_plan")
    # Partial update: only NON-None fields change. Caps use -1 (or any negative) to mean
    # "unlimited" (stored NULL) — explicit, so an omitted field never flips a cap by accident.
    sets, vals = [], []
    for k, v in (fields or {}).items():
        if k not in _EDITABLE_PLAN_FIELDS or v is None:
            continue  # ignore non-editable keys + unset fields (defense in depth)
        if k in ("claims_per_month", "disputed_cap", "max_users"):
            cv = int(v)
            if cv < 0:
                cv = None  # -1 = unlimited
            elif cv > 1_000_000_000:
                raise ValueError(f"{k}_out_of_range")
            elif k == "max_users" and cv == 0:
                raise ValueError("max_users_min_1")
            sets.append(f"{k}=?"); vals.append(cv)
        elif k == "active":
            sets.append("active=?"); vals.append(1 if v in (True, 1, "1", "true", "on") else 0)
        elif k == "sort_order":
            sets.append("sort_order=?"); vals.append(max(0, min(999, int(v))))
        elif k == "price":
            pv = int(v)  # RUPEES from the editor → stored as paise
            if pv < 1:
                raise ValueError("price_min_1_rupee")
            if pv > 1_000_000:  # ₹10 lakh sanity ceiling
                raise ValueError("price_out_of_range")
            sets.append("price_paise=?"); vals.append(pv * 100)
        elif k == "label":
            s = str(v).strip()[:40]
            if not s:
                raise ValueError("label_required")
            sets.append("label=?"); vals.append(s)
        elif k == "badge":
            sets.append("badge=?"); vals.append(str(v).strip()[:30])
        elif k == "features":
            if not isinstance(v, list):
                raise ValueError("features_must_be_list")
            feats = [str(x).strip()[:120] for x in v if str(x).strip()][:12]
            sets.append("features=?"); vals.append(json.dumps(feats))
    if not sets:
        raise ValueError("nothing_to_update")
    sets.append("updated_at=CURRENT_TIMESTAMP")
    vals.append(plan_key)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE nidaan_plans_config SET {', '.join(sets)} WHERE plan_key=?", vals)
        await conn.commit()
    invalidate_plans_cache()
    return (await get_plans_config(force=True)).get(plan_key, {})


async def all_plans_config_full() -> list[dict]:
    """Every plan (all billing types, active + inactive) for the super-admin editor,
    ordered by sort_order. Includes price_paise + razorpay id (read-only for now)."""
    cfg = await get_plans_config(force=True)
    rows = sorted(cfg.values(), key=lambda p: (p.get("sort_order", 99), p.get("plan_key", "")))
    return rows


async def public_plans() -> list[dict]:
    """All ACTIVE plan tiers (monthly + yearly) for the pricing UI + disputed-amount cap
    nudge — read from the config table (falls back to PLAN_LIMITS monthly tiers until
    seeded). Each entry carries billing + price + display so the UI renders dynamically."""
    cfg = await get_plans_config()
    out = []
    if cfg:
        for key, p in cfg.items():
            if not p.get("active"):
                continue
            billing = p.get("billing", "monthly")
            price = round((p.get("price_paise") or 0) / 100)
            out.append({
                "plan": key, "label": p.get("label") or key.replace("_annual", "").capitalize(),
                "billing": billing, "price": price,
                "price_display": f"₹{price:,}/{'year' if billing == 'yearly' else 'month'}",
                "claims_per_month": p.get("claims_per_month"),
                "disputed_cap": p.get("disputed_cap"),
                "max_users": p.get("max_users"),
                "features": p.get("features", []), "badge": p.get("badge", ""),
                "sort_order": p.get("sort_order", 99),
            })
        out.sort(key=lambda x: x.get("sort_order", 99))
    else:  # fallback: config not seeded — monthly tiers from PLAN_LIMITS
        for key in ("silver", "gold", "platinum"):
            lim = PLAN_LIMITS.get(key, {})
            price = lim.get("price") or 0
            out.append({
                "plan": key, "label": key.capitalize(), "billing": "monthly",
                "price": price, "price_display": f"₹{price:,}/month",
                "claims_per_month": lim.get("claims_per_month"),
                "disputed_cap": lim.get("disputed_cap"), "max_users": lim.get("max_users"),
                "features": [], "badge": "MOST POPULAR" if key == "gold" else "",
                "sort_order": {"silver": 1, "gold": 2, "platinum": 3}.get(key, 9),
            })
    return out


CLAIM_STATUSES = (
    "intimated", "assigned", "in_review", "in_negotiation",
    "review_delivered",  # legal assessment delivered to customer (can_fight | no_scope)
    "resolved_won", "resolved_lost", "closed", "withdrawn",
)
REVIEW_OUTCOMES = ("can_fight", "no_scope")


# =============================================================================
#  DB HELPER
# =============================================================================

async def _db():
    """Yield an aiosqlite connection for Nidaan helpers."""
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn


# =============================================================================
#  ACCOUNT OPERATIONS
# =============================================================================

def _hash_password(password: str) -> str:
    """SHA-256 hash with a per-call salt. Returns 'salt$hash'."""
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == digest
    except Exception:
        return False


def normalize_phone(phone: str) -> str:
    """Reduce a phone to a bare 10-digit Indian mobile — strips +91 / 91 / leading 0,
    spaces, dashes, brackets. Returns '' if it doesn't look like a valid 10-digit mobile
    (must start 6-9). Used as the canonical stored form + the login/dedup key."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) > 10:
        digits = digits[-10:]          # drop 91 / 0 country/trunk prefix
    return digits if len(digits) == 10 and digits[0] in "6789" else ""


def _capname(s: str) -> str:
    """Normalize a person's name to UPPERCASE (trimmed, single-spaced) so names are stored
    consistently in caps across every form (claim / signup / ₹499 review / subscription).
    Blank stays blank. Applies to person names only — never email / policy / notes."""
    return " ".join((s or "").split()).upper()


async def create_account(
    owner_name: str,
    phone: str,
    password: str,
    email: str = "",
    firm_name: str = "",
    branch_code: str = "",
    utm_source: str = "",
    utm_medium: str = "",
    utm_campaign: str = "",
) -> Optional[int]:
    """Create a new Nidaan account. Mobile (phone) is the PRIMARY identity — required and
    unique. Email is OPTIONAL (stored NULL when blank; unique only when present). Returns
    account_id, or None on a duplicate mobile or email. branch_code attributes the sale to
    an affiliate city branch OR a staff referral code (validated by the caller; stored as-is).
    utm_* capture the marketing acquisition source for the analytics dashboard (all optional)."""
    owner_name = _capname(owner_name)   # #6: store names in caps
    pw_hash = _hash_password(password)
    em = (email or "").lower().strip() or None       # NULL when blank → email-less accounts don't collide
    ph = normalize_phone(phone) or (phone or "").strip()
    code = (branch_code or "").strip().upper()
    channel, _rc = await resolve_channel(code, utm_source)   # direct|staff|branch|campaign|marketing
    us, um, uc = (utm_source or "").strip(), (utm_medium or "").strip(), (utm_campaign or "").strip()
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cur = await conn.execute(
                """INSERT INTO nidaan_accounts
                   (owner_name, email, phone, password_hash, firm_name, branch_code,
                    source_channel, utm_source, utm_medium, utm_campaign)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (owner_name, em, ph, pw_hash, firm_name, code, channel, us, um, uc),
            )
            await conn.commit()
            new_id = cur.lastrowid
    except aiosqlite.IntegrityError as e:
        logger.warning("nidaan create_account: duplicate mobile/email (%s)", e)
        return None
    # Analytics: signup completed (channel-attributed). Best-effort, never blocks signup.
    await record_event("signup_completed", channel=channel, ref_code=code,
                       utm_source=us, utm_medium=um, utm_campaign=uc,
                       account_id=new_id, contact=ph or em or "")
    return new_id


# ── Affiliate branches (offline city vendors selling subscriptions) ──────────
# An account is "paid" for a branch if it has an active subscription, OR a per-claim
# review credit that progressed past pending_payment, OR a claim whose ₹499 review fee
# was paid directly (advisor-lead funnel — that path marks nidaan_claims.payment_status
# ='paid' and creates NO per_claim_purchase row, so it must be tested explicitly).
_BRANCH_PAID_EXISTS = (
    "(EXISTS(SELECT 1 FROM nidaan_subscriptions s "
    "        WHERE s.account_id=a.account_id AND s.status='active') "
    " OR EXISTS(SELECT 1 FROM nidaan_per_claim_purchase p "
    "           WHERE p.account_id=a.account_id "
    "             AND p.status NOT IN ('pending_payment','cancelled')) "
    " OR EXISTS(SELECT 1 FROM nidaan_claims c "
    "           WHERE c.account_id=a.account_id AND c.payment_status='paid'))"
)


async def list_branches(include_disabled: bool = True) -> list[dict]:
    """All branches with live signup / paid / unpaid counts + profit-share reconciliation.
    revenue = subscription rupees collected from attributed accounts (sum of amount_paid
    across their subscription rows); share = revenue × share_pct. Amounts are in RUPEES."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        where = "" if include_disabled else "WHERE b.status='active'"
        cur = await conn.execute(
            f"""SELECT b.branch_code, b.city, b.name, b.contact_email, b.contact_phone, b.status, b.created_at,
                       COALESCE(b.share_pct, 0) AS share_pct,
                       (SELECT COUNT(*) FROM nidaan_accounts a
                        WHERE UPPER(a.branch_code)=b.branch_code) AS ref_signups,
                       (SELECT COUNT(*) FROM nidaan_accounts a
                        WHERE UPPER(a.branch_code)=b.branch_code AND {_BRANCH_PAID_EXISTS}) AS ref_paid,
                       (SELECT COUNT(*) FROM nidaan_claims c
                        WHERE UPPER(COALESCE(c.branch_code,''))=b.branch_code AND c.origin='branch') AS raised_claims,
                       (SELECT COUNT(*) FROM nidaan_claims c
                        WHERE UPPER(COALESCE(c.branch_code,''))=b.branch_code AND c.origin='branch'
                          AND c.payment_status='paid') AS raised_paid,
                       (SELECT COALESCE(SUM(su.amount_paid), 0)
                          FROM nidaan_subscriptions su
                          JOIN nidaan_accounts a2 ON a2.account_id = su.account_id
                         WHERE UPPER(a2.branch_code)=b.branch_code) AS revenue
                FROM nidaan_branches b {where}
                ORDER BY b.city, b.branch_code""")
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        # A branch brings business two ways: (1) REFERRED subscriber accounts (their code
        # lands in nidaan_accounts.branch_code), and (2) claims they RAISE on behalf of a
        # walk-in customer (a house account, so the attribution is on the CLAIM.branch_code,
        # origin='branch'). Both count toward the branch's signups/paid/unpaid — otherwise a
        # branch that has only raised claims (the common early case) shows all-zeros.
        ref_signups = int(r.pop("ref_signups", 0) or 0)
        ref_paid = int(r.pop("ref_paid", 0) or 0)
        raised = int(r.pop("raised_claims", 0) or 0)
        raised_paid = int(r.pop("raised_paid", 0) or 0)
        r["ref_signups"] = ref_signups          # referred subscriber accounts
        r["raised_claims"] = raised             # claims raised by the branch
        r["signups"] = ref_signups + raised
        r["paid"] = ref_paid + raised_paid
        r["accounts"] = r["signups"]            # back-compat alias
        r["unpaid"] = max(0, r["signups"] - r["paid"])
        rev = int(r.get("revenue") or 0)
        pct = float(r.get("share_pct") or 0)
        r["revenue"] = rev                    # rupees (subscription revenue; review fees TBD)
        r["share"] = round(rev * pct / 100)   # rupees owed to the branch
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Staff-as-branch: every staffer is also a referrer with a personal code + commission.
# Their code lives in the SAME nidaan_accounts.branch_code slot as branch codes but is
# formatted "SP-XXXXXX" so it never collides with a branch code. Branch reconciliation
# (list_branches) only counts codes that JOIN a real nidaan_branches row, so staff
# referrals are invisible to branch stats and vice-versa — zero cross-contamination.
# ─────────────────────────────────────────────────────────────────────────────
import secrets as _secrets

_STAFF_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I,O,0,1 (Tier II/III legibility)


def _gen_staff_ref_code() -> str:
    return "SP-" + "".join(_secrets.choice(_STAFF_REF_ALPHABET) for _ in range(6))


async def ensure_staff_referral_codes() -> int:
    """Backfill a unique personal referral code for every staffer missing one.
    Idempotent — safe to call at startup and after create_staff. Returns count assigned.
    Uniqueness is checked against BOTH staff codes and branch codes so a staff code can
    never shadow a branch code in the shared branch_code attribution slot."""
    assigned = 0
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Existing codes (both namespaces) to guarantee global uniqueness.
        taken = set()
        for tbl, col in (("nidaan_staff", "referral_code"), ("nidaan_branches", "branch_code")):
            try:
                cur = await conn.execute(
                    f"SELECT {col} AS c FROM {tbl} WHERE {col} IS NOT NULL AND {col}<>''")
                for r in await cur.fetchall():
                    taken.add((r["c"] or "").upper())
            except Exception:
                pass
        cur = await conn.execute(
            "SELECT staff_id FROM nidaan_staff "
            "WHERE (referral_code IS NULL OR referral_code='') "
            "  AND COALESCE(deleted_at,'')=''")
        need = [r["staff_id"] for r in await cur.fetchall()]
        for sid in need:
            code = _gen_staff_ref_code()
            while code.upper() in taken:
                code = _gen_staff_ref_code()
            taken.add(code.upper())
            await conn.execute(
                "UPDATE nidaan_staff SET referral_code=? WHERE staff_id=?", (code, sid))
            assigned += 1
        if assigned:
            await conn.commit()
    return assigned


async def _staff_business_row(conn, r: dict) -> dict:
    """Given a staff row (with referral_code, commission_pct), attach live business
    stats computed off the shared branch_code attribution slot. RUPEES throughout."""
    code = (r.get("referral_code") or "").strip().upper()
    out = {
        "staff_id": r.get("staff_id"),
        "name": r.get("name", ""),
        "role": r.get("role", ""),
        "referral_code": r.get("referral_code") or "",
        "commission_pct": float(r.get("commission_pct") or 0),
        "signups": 0, "paid": 0, "unpaid": 0, "revenue": 0,
        "commission": 0, "claims": 0, "claims_raised": 0,
    }
    if not code:
        return out
    signups = (await (await conn.execute(
        "SELECT COUNT(*) FROM nidaan_accounts a WHERE UPPER(a.branch_code)=?",
        (code,))).fetchone())[0]
    paid = (await (await conn.execute(
        f"SELECT COUNT(*) FROM nidaan_accounts a "
        f"WHERE UPPER(a.branch_code)=? AND {_BRANCH_PAID_EXISTS}",
        (code,))).fetchone())[0]
    revenue = (await (await conn.execute(
        "SELECT COALESCE(SUM(su.amount_paid),0) FROM nidaan_subscriptions su "
        "JOIN nidaan_accounts a2 ON a2.account_id=su.account_id "
        "WHERE UPPER(a2.branch_code)=?", (code,))).fetchone())[0]
    # Claims from REFERRED customers (their own accounts carry this staff's code).
    claims = (await (await conn.execute(
        "SELECT COUNT(*) FROM nidaan_claims c "
        "JOIN nidaan_accounts a3 ON a3.account_id=c.account_id "
        "WHERE UPPER(a3.branch_code)=?", (code,))).fetchone())[0]
    # Claims the staffer RAISED themselves (branch-style, on the house account).
    claims_raised = (await (await conn.execute(
        "SELECT COUNT(*) FROM nidaan_claims c "
        "WHERE c.origin='branch' AND UPPER(c.branch_code)=?", (code,))).fetchone())[0]
    pct = float(r.get("commission_pct") or 0)
    out.update({
        "signups": int(signups or 0),
        "paid": int(paid or 0),
        "unpaid": max(0, int(signups or 0) - int(paid or 0)),
        "revenue": int(revenue or 0),
        "commission": round(int(revenue or 0) * pct / 100),
        "claims": int(claims or 0),
        "claims_raised": int(claims_raised or 0),
    })
    return out


async def get_referred_accounts(ref_code: str) -> list[dict]:
    """Accounts that joined via a referral code (staff SP-code OR branch code) — for the
    'My Business' subscriber list + branch reconciliation drill-down. Name + plan + paid + date."""
    code = (ref_code or "").strip().upper()
    if not code:
        return []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            f"""SELECT a.account_id, a.owner_name, a.created_at, s.plan AS plan,
                       CASE WHEN {_BRANCH_PAID_EXISTS} THEN 1 ELSE 0 END AS paid
                FROM nidaan_accounts a
                LEFT JOIN nidaan_subscriptions s ON s.account_id=a.account_id AND s.status='active'
                WHERE UPPER(a.branch_code)=? AND COALESCE(a.status,'')<>'deleted'
                ORDER BY a.created_at DESC""",
            (code,))
        return [dict(r) for r in await cur.fetchall()]


async def get_staff_business(staff_id: int) -> Optional[dict]:
    """One staffer's own referral business (for the 'Your Business' dashboard tab)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT staff_id, name, role, referral_code, commission_pct "
            "FROM nidaan_staff WHERE staff_id=?", (staff_id,))).fetchone()
        if not r:
            return None
        return await _staff_business_row(conn, dict(r))


async def list_staff_business(include_deleted: bool = False) -> list[dict]:
    """All staffers with their referral business stats (super-admin reconciliation)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        where = "" if include_deleted else "WHERE COALESCE(deleted_at,'')=''"
        cur = await conn.execute(
            f"SELECT staff_id, name, role, referral_code, commission_pct "
            f"FROM nidaan_staff {where} ORDER BY name")
        rows = [dict(r) for r in await cur.fetchall()]
        return [await _staff_business_row(conn, r) for r in rows]


async def set_staff_telegram_access(staff_id: int, allowed: bool) -> bool:
    """Super-admin: allow/deny a staffer's Telegram (link + one-tap login). Deny → password-only
    (for third-party staff). Existing linked devices are unlinked on deny for a clean cut-off."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_staff SET telegram_access=? WHERE staff_id=?",
            (1 if allowed else 0, staff_id))
        if not allowed:
            # Revoke existing links so denial takes effect immediately.
            await conn.execute("DELETE FROM nidaan_staff_telegram WHERE staff_id=?", (staff_id,))
            await conn.execute(
                "UPDATE nidaan_staff SET telegram_chat_id=NULL, telegram_username=NULL, "
                "telegram_linked_at=NULL WHERE staff_id=?", (staff_id,))
        await conn.commit()
        return cur.rowcount > 0


async def set_staff_commission(staff_id: int, pct: float) -> bool:
    """Super-admin: set a staffer's commission % (0–100). Mirrors update_branch(share_pct)."""
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return False
    pct = max(0.0, min(100.0, pct))
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_staff SET commission_pct=? WHERE staff_id=?", (pct, staff_id))
        await conn.commit()
        return cur.rowcount > 0


# Channel classification usable in SQL for BOTH new accounts (source_channel set at signup)
# and legacy accounts (derived from the branch_code slot). Keeps the analytics consistent
# across the migration boundary. `a` must be the nidaan_accounts alias.
_CHANNEL_CASE = (
    "CASE "
    "  WHEN COALESCE(a.source_channel,'')<>'' THEN a.source_channel "
    "  WHEN COALESCE(a.branch_code,'')='' THEN 'direct' "
    "  WHEN EXISTS(SELECT 1 FROM nidaan_staff s WHERE UPPER(s.referral_code)=UPPER(a.branch_code)) THEN 'staff' "
    "  WHEN EXISTS(SELECT 1 FROM nidaan_branches b WHERE b.branch_code=UPPER(a.branch_code)) THEN 'branch' "
    "  ELSE 'campaign' END"
)
_CHANNELS = ["direct", "staff", "branch", "campaign", "marketing"]


async def get_business_analytics(days: int = 30) -> dict:
    """Real-time acquisition analytics for the super-admin dashboard, segmented by channel.
    Acquisition metrics (signups/subscribers/one-time/revenue) are COHORT-based — accounts
    created in the window. Failures + abandonment come from the event log (event time).
    Amounts in RUPEES."""
    days = max(1, min(int(days or 30), 365))
    since = f"-{days} days"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # ── Acquisition by channel (cohort: accounts created in window) ──────────
        cur = await conn.execute(
            f"""SELECT {_CHANNEL_CASE} AS channel,
                       COUNT(*) AS signups,
                       SUM(CASE WHEN EXISTS(SELECT 1 FROM nidaan_subscriptions su
                                            WHERE su.account_id=a.account_id AND su.status='active')
                                THEN 1 ELSE 0 END) AS subscribers,
                       SUM(CASE WHEN EXISTS(SELECT 1 FROM nidaan_per_claim_purchase p
                                            WHERE p.account_id=a.account_id
                                              AND p.status NOT IN ('pending_payment','cancelled','failed','refunded'))
                                     OR EXISTS(SELECT 1 FROM nidaan_claims c
                                               WHERE c.account_id=a.account_id AND c.payment_status='paid')
                                THEN 1 ELSE 0 END) AS onetime
                FROM nidaan_accounts a
                WHERE a.created_at >= datetime('now', ?)
                  AND COALESCE(a.deleted_at,'')=''
                GROUP BY channel""",
            (since,))
        chan = {c: {"channel": c, "signups": 0, "subscribers": 0, "onetime": 0,
                    "revenue": 0, "abandoned": 0, "payment_failed": 0} for c in _CHANNELS}
        for r in await cur.fetchall():
            c = r["channel"] or "direct"
            chan.setdefault(c, {"channel": c, "signups": 0, "subscribers": 0, "onetime": 0,
                                "revenue": 0, "abandoned": 0, "payment_failed": 0})
            chan[c]["signups"] = int(r["signups"] or 0)
            chan[c]["subscribers"] = int(r["subscribers"] or 0)
            chan[c]["onetime"] = int(r["onetime"] or 0)

        # ── Revenue by channel (cohort accounts' subscription + per-claim payments) ──
        cur = await conn.execute(
            f"""SELECT {_CHANNEL_CASE} AS channel,
                       COALESCE((SELECT SUM(su.amount_paid) FROM nidaan_subscriptions su
                                 WHERE su.account_id=a.account_id),0)
                     + COALESCE((SELECT SUM(p.amount_paid) FROM nidaan_per_claim_purchase p
                                 WHERE p.account_id=a.account_id
                                   AND p.status NOT IN ('pending_payment','cancelled','failed','refunded')),0)
                     + COALESCE((SELECT SUM(c.review_fee_paid) FROM nidaan_claims c
                                 WHERE c.account_id=a.account_id AND c.payment_status='paid'
                                   AND NOT EXISTS(SELECT 1 FROM nidaan_per_claim_purchase p2
                                                  WHERE p2.linked_claim_id=c.claim_id)),0) AS rev
                FROM nidaan_accounts a
                WHERE a.created_at >= datetime('now', ?)
                  AND COALESCE(a.deleted_at,'')=''
                GROUP BY channel""",
            (since,))
        for r in await cur.fetchall():
            c = r["channel"] or "direct"
            if c in chan:
                chan[c]["revenue"] = int(r["rev"] or 0)

        # ── Abandonment by channel (event log) ──────────────────────────────────
        cur = await conn.execute(
            """SELECT channel, COUNT(*) AS n FROM nidaan_events
               WHERE event_type='abandoned' AND created_at >= datetime('now', ?)
               GROUP BY channel""", (since,))
        for r in await cur.fetchall():
            c = r["channel"] or "direct"
            if c in chan:
                chan[c]["abandoned"] = int(r["n"] or 0)

        # ── Payment failures (event log; channel usually unknown at webhook time) ──
        cur = await conn.execute(
            """SELECT channel, COUNT(*) AS n FROM nidaan_events
               WHERE event_type IN ('payment_failed','subscription_failed')
                 AND created_at >= datetime('now', ?) GROUP BY channel""", (since,))
        total_failed = 0
        for r in await cur.fetchall():
            c = r["channel"] or "direct"
            total_failed += int(r["n"] or 0)
            if c in chan:
                chan[c]["payment_failed"] = int(r["n"] or 0)

        # ── Abandoned one-time reviews (authoritative: stuck pending_payment in window) ──
        stuck_reviews = (await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_per_claim_purchase "
            "WHERE status='pending_payment' AND created_at >= datetime('now', ?)",
            (since,))).fetchone())[0]

        # ── Funnel (window): signup_started(events) → signups(accounts) → pay_opened(events) → paid ──
        def _evt_count(et):
            return conn.execute(
                "SELECT COUNT(*) FROM nidaan_events WHERE event_type=? AND created_at >= datetime('now', ?)",
                (et, since))
        signup_started = (await (await _evt_count("signup_started")).fetchone())[0]
        pay_opened     = (await (await _evt_count("pay_opened")).fetchone())[0]
        signups_total  = sum(chan[c]["signups"] for c in chan)
        subs_total     = sum(chan[c]["subscribers"] for c in chan)
        onetime_total  = sum(chan[c]["onetime"] for c in chan)
        revenue_total  = sum(chan[c]["revenue"] for c in chan)
        abandoned_total= sum(chan[c]["abandoned"] for c in chan)
        paid_total     = subs_total + onetime_total

        # ── Recent failures (for the follow-up stream) ──────────────────────────
        cur = await conn.execute(
            """SELECT created_at, event_type, purpose, amount_paise, reason, contact
               FROM nidaan_events
               WHERE event_type IN ('payment_failed','subscription_failed')
               ORDER BY event_id DESC LIMIT 25""")
        recent_failures = [{
            "at": r["created_at"], "type": r["event_type"], "purpose": r["purpose"] or "",
            "amount": int((r["amount_paise"] or 0)) // 100, "reason": r["reason"] or "",
            "contact": r["contact"] or ""
        } for r in await cur.fetchall()]

    return {
        "range_days": days,
        "totals": {
            "signups": signups_total, "subscribers": subs_total, "onetime": onetime_total,
            "revenue": revenue_total, "payment_failed": total_failed,
            "abandoned": abandoned_total, "stuck_reviews": int(stuck_reviews or 0),
        },
        "by_channel": [chan[c] for c in _CHANNELS if c in chan],
        "funnel": {
            "signup_started": int(signup_started or 0),
            "signups": signups_total,
            "pay_opened": int(pay_opened or 0),
            "paid": paid_total,
        },
        "recent_failures": recent_failures,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Business-analytics event spine. Every meaningful attempt/outcome is appended to
# nidaan_events so the super-admin dashboard can segment acquisition BY CHANNEL.
# resolve_channel() maps a raw ref code / utm to one of: direct|staff|branch|campaign|marketing.
# ─────────────────────────────────────────────────────────────────────────────
async def resolve_channel(ref_code: str = "", utm_source: str = "") -> tuple[str, str]:
    """Classify an acquisition. Returns (channel, normalized_ref_code).
    A ref code that matches a staff referral_code → 'staff'; a real branch → 'branch';
    any other non-empty code → 'campaign'; no code but a utm_source → 'marketing'; else 'direct'."""
    code = (ref_code or "").strip().upper()
    if code:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            s = await (await conn.execute(
                "SELECT 1 FROM nidaan_staff WHERE UPPER(referral_code)=? LIMIT 1", (code,))).fetchone()
            if s:
                return "staff", code
            b = await (await conn.execute(
                "SELECT 1 FROM nidaan_branches WHERE UPPER(branch_code)=? LIMIT 1", (code,))).fetchone()
            if b:
                return "branch", code
        return "campaign", code
    if (utm_source or "").strip():
        return "marketing", ""
    return "direct", ""


async def resolve_ref_info(code: str) -> dict:
    """Public-safe resolver for a referral code → {valid, type, name}. Used by the signup
    page to show 'Referred by ___' and lock the code so attribution can't be lost. Codes are
    random (staff) or short branch codes; only a friendly name is returned, nothing sensitive."""
    code = (code or "").strip().upper()
    out = {"valid": False, "type": "", "name": "", "code": code}
    if not code:
        return out
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        b = await (await conn.execute(
            "SELECT name, city FROM nidaan_branches WHERE UPPER(branch_code)=? AND status='active'",
            (code,))).fetchone()
        if b:
            out.update(valid=True, type="branch",
                       name=(b["name"] or b["city"] or "Branch"))
            return out
        s = await (await conn.execute(
            "SELECT name FROM nidaan_staff WHERE UPPER(referral_code)=? "
            "AND COALESCE(deleted_at,'')='' AND status='active'", (code,))).fetchone()
        if s:
            out.update(valid=True, type="staff", name=(s["name"] or "NidaanPartner advisor"))
            return out
    return out


async def record_event(event_type: str, *, channel: str = "", ref_code: str = "",
                       utm_source: str = "", utm_medium: str = "", utm_campaign: str = "",
                       account_id: Optional[int] = None, claim_id: Optional[int] = None,
                       amount_paise: Optional[int] = None, purpose: str = "", status: str = "",
                       reason: str = "", session_id: str = "", contact: str = "",
                       meta: str = "") -> None:
    """Append one analytics event (best-effort — never raises into the caller). If channel is
    blank it is derived from ref_code/utm_source via resolve_channel()."""
    try:
        if not channel:
            channel, ref_code = await resolve_channel(ref_code, utm_source)
        else:
            ref_code = (ref_code or "").strip().upper()
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                """INSERT INTO nidaan_events
                   (event_type, channel, ref_code, utm_source, utm_medium, utm_campaign,
                    account_id, claim_id, amount_paise, purpose, status, reason,
                    session_id, contact, meta)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event_type, channel or "direct", ref_code or "",
                 (utm_source or "").strip(), (utm_medium or "").strip(), (utm_campaign or "").strip(),
                 account_id, claim_id, amount_paise, purpose or "", status or "", reason or "",
                 (session_id or "").strip(), (contact or "").strip(), meta or ""))
            await conn.commit()
    except Exception as _ee:
        logger.warning("record_event(%s) failed: %s", event_type, _ee)


async def get_branch_unpaid_leads(branch_code: str) -> list[dict]:
    """Attributed accounts for a branch that haven't paid anything yet
    (with their pending ₹499 review, if they started one)."""
    code = (branch_code or "").strip().upper()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            f"""SELECT a.account_id, a.owner_name, a.email, a.phone, a.created_at,
                       p.purchase_id, p.claim_type, p.disputed_amount,
                       p.created_at AS review_started_at
                FROM nidaan_accounts a
                LEFT JOIN nidaan_per_claim_purchase p
                       ON p.account_id=a.account_id AND p.status='pending_payment'
                WHERE UPPER(a.branch_code)=? AND {_BRANCH_PAID_EXISTS} = 0
                ORDER BY a.created_at DESC""",
            (code,))
        return [dict(r) for r in await cur.fetchall()]


async def get_branch_leads_to_remind(min_age_hours: int = 24) -> list[dict]:
    """For the daily sweep: branch-attributed accounts that started a ₹499 review,
    are still unpaid past min_age_hours, and haven't been reminded yet. Includes
    the branch's contact email so the caller can notify it once."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            f"""SELECT a.account_id, a.owner_name, a.email, a.phone, a.branch_code,
                       b.contact_email AS branch_email, b.city AS branch_city, b.name AS branch_name,
                       p.claim_type, p.disputed_amount, p.created_at AS review_started_at
                FROM nidaan_accounts a
                JOIN nidaan_branches b ON b.branch_code = UPPER(a.branch_code)
                JOIN nidaan_per_claim_purchase p
                     ON p.account_id=a.account_id AND p.status='pending_payment'
                WHERE a.branch_code <> ''
                  AND a.branch_unpaid_reminded_at IS NULL
                  AND b.contact_email <> ''
                  AND p.created_at <= datetime('now', ?)
                  AND {_BRANCH_PAID_EXISTS} = 0
                GROUP BY a.account_id""",
            (f"-{int(min_age_hours)} hours",))
        return [dict(r) for r in await cur.fetchall()]


async def mark_branch_reminded(account_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_accounts SET branch_unpaid_reminded_at=CURRENT_TIMESTAMP WHERE account_id=?",
            (account_id,))
        await conn.commit()


async def get_branch(code: str) -> Optional[dict]:
    code = (code or "").strip().upper()
    if not code:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_branches WHERE branch_code=?", (code,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def is_valid_branch(code: str) -> bool:
    """True only if the code exists AND is active (strict validation)."""
    b = await get_branch(code)
    return bool(b and b.get("status") == "active")


async def is_valid_ref_code(code: str) -> bool:
    """True if the code is a valid ACTIVE branch OR an existing STAFF referral code.
    Referral attribution (branch_code slot) accepts both since staff-as-branch shipped —
    without this, a staff shareable link (SP-XXXXXX) is rejected at signup."""
    code = (code or "").strip().upper()
    if not code:
        return False
    if await is_valid_branch(code):
        return True
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM nidaan_staff WHERE UPPER(referral_code)=? "
            "AND COALESCE(deleted_at,'')='' LIMIT 1", (code,))).fetchone()
        return bool(row)


async def set_account_branch(account_id: int, code: str) -> bool:
    """Attribute an account to a branch/staff referral code — FIRST-TOUCH ONLY. Once an account
    has a referral code, it is LOCKED and can never be changed (prevents a subscriber or a later
    link from re-crediting a different referrer). Only fills a blank code."""
    code = (code or "").strip().upper()
    if not code:
        return False
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_accounts SET branch_code=? "
            "WHERE account_id=? AND COALESCE(NULLIF(branch_code,''),'')=''",
            (code, account_id))
        await conn.commit()
        return cur.rowcount > 0


async def reattribute_account(account_id: int, new_code: str, *, clear: bool = False) -> dict:
    """SUPER-ADMIN OVERRIDE of an account's referral attribution — bypasses the first-touch
    lock (set_account_branch only fills a blank). For CORRECTIONS only; always audited by the
    caller. `clear=True` resets to Direct (blank). Returns {ok, old_code, new_code, error?}.

    Note: a claim shows COALESCE(claim.branch_code, account.branch_code) — so a branch-origin
    claim with its OWN stamped code needs reattribute_claim() too; this fixes account-level."""
    code = "" if clear else (new_code or "").strip().upper()
    if not clear:
        if not code:
            return {"ok": False, "error": "Enter a referral code, or choose Clear (Direct)."}
        if not await is_valid_ref_code(code):
            return {"ok": False, "error": f"'{code}' is not a valid staff/branch referral code."}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT branch_code FROM nidaan_accounts WHERE account_id=?", (account_id,))).fetchone()
        if not row:
            return {"ok": False, "error": "Account not found."}
        old_code = (row["branch_code"] or "").strip().upper()
        await conn.execute("UPDATE nidaan_accounts SET branch_code=? WHERE account_id=?",
                           (code, account_id))
        await conn.commit()
    return {"ok": True, "old_code": old_code, "new_code": code}


async def reattribute_claim(claim_id: int, new_code: str, *, clear: bool = False) -> dict:
    """SUPER-ADMIN OVERRIDE of a single claim's OWN attribution code (nidaan_claims.branch_code),
    which takes precedence over the account code in the trail. `clear=True` → fall back to the
    account's attribution. Always audited by the caller. Returns {ok, old_code, new_code, error?}."""
    code = "" if clear else (new_code or "").strip().upper()
    if not clear:
        if not code:
            return {"ok": False, "error": "Enter a referral code, or choose Clear (use account)."}
        if not await is_valid_ref_code(code):
            return {"ok": False, "error": f"'{code}' is not a valid staff/branch referral code."}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT branch_code FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
        if not row:
            return {"ok": False, "error": "Claim not found."}
        old_code = (row["branch_code"] or "").strip().upper()
        await conn.execute("UPDATE nidaan_claims SET branch_code=? WHERE claim_id=?",
                           (code, claim_id))
        await conn.commit()
    return {"ok": True, "old_code": old_code, "new_code": code}


# ── Control-center activity trail ─────────────────────────────────────────────
async def log_activity(action: str, actor_type: str = "staff", actor_id=None,
                       actor_name: str = "", actor_role: str = "",
                       target_type: str = "", target_id="", detail: str = "",
                       ip: str = "") -> None:
    """Record a sensitive ops action. Never raises (best-effort)."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO nidaan_audit_log "
                "(actor_type,actor_id,actor_name,actor_role,action,target_type,target_id,detail,ip) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (actor_type, actor_id, actor_name, actor_role, action,
                 target_type, str(target_id) if target_id != "" else "", detail, ip))
            await conn.commit()
    except Exception as e:
        logger.warning("activity log failed (%s): %s", action, e)


async def get_activity_log(limit: int = 100, offset: int = 0, action: str = None,
                           target_type: str = None, search: str = None) -> list[dict]:
    """Filterable activity feed for the Control Center."""
    conds, params = [], []
    if action:
        conds.append("action = ?"); params.append(action)
    if target_type:
        conds.append("target_type = ?"); params.append(target_type)
    if search:
        conds.append("(actor_name LIKE ? OR detail LIKE ? OR action LIKE ? OR target_id LIKE ?)")
        like = f"%{search}%"; params.extend([like, like, like, like])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            f"SELECT * FROM nidaan_audit_log {where} ORDER BY created_at DESC, log_id DESC "
            "LIMIT ? OFFSET ?", params + [limit, offset])
        return [dict(r) for r in await cur.fetchall()]


async def create_branch(code: str, city: str, name: str = "", contact_email: str = "") -> dict:
    """Create a branch code. Returns {ok} or {error}."""
    code = (code or "").strip().upper()
    city = (city or "").strip()
    email = (contact_email or "").strip().lower()
    if not code or not city:
        return {"error": "Branch code and city are required."}
    if not re.match(r"^[A-Z0-9][A-Z0-9\-]{1,19}$", code):
        return {"error": "Code must be 2–20 chars: letters, digits, hyphens."}
    if email and "@" not in email:
        return {"error": "Contact email looks invalid."}
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO nidaan_branches (branch_code, city, name, contact_email) VALUES (?,?,?,?)",
                (code, city, (name or "").strip(), email))
            await conn.commit()
        return {"ok": True, "branch_code": code}
    except aiosqlite.IntegrityError:
        return {"error": f"Branch code '{code}' already exists."}


async def update_branch(code: str, status: Optional[str] = None,
                        contact_email: Optional[str] = None,
                        share_pct: Optional[float] = None,
                        contact_phone: Optional[str] = None) -> bool:
    """Update a branch's status, contact email, WhatsApp number, and/or profit-share %."""
    code = (code or "").strip().upper()
    sets, params = [], []
    if status is not None:
        sets.append("status=?")
        params.append(status if status in ("active", "disabled") else "active")
    if contact_email is not None:
        email = (contact_email or "").strip().lower()
        if email and "@" not in email:
            return False
        sets.append("contact_email=?")
        params.append(email)
    if contact_phone is not None:
        # Digits only; blank clears it. 10-digit Indian mobile (or with country code).
        ph = "".join(ch for ch in (contact_phone or "") if ch.isdigit())
        if ph and len(ph) < 10:
            return False
        sets.append("contact_phone=?")
        params.append(ph[-10:] if len(ph) == 10 else ph)
    if share_pct is not None:
        try:
            pct = float(share_pct)
        except (TypeError, ValueError):
            return False
        if pct < 0 or pct > 100:
            return False
        sets.append("share_pct=?")
        params.append(round(pct, 2))
    if not sets:
        return False
    params.append(code)
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            f"UPDATE nidaan_branches SET {', '.join(sets)} WHERE branch_code=?", params)
        await conn.commit()
        return cur.rowcount > 0


# Back-compat shim for the existing status-only endpoint.
async def set_branch_status(code: str, status: str) -> bool:
    return await update_branch(code, status=status)


async def get_account_by_email(email: str) -> Optional[dict]:
    em = (email or "").lower().strip()
    if not em:
        return None   # never match email-less accounts (email stored NULL) on a blank query
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_accounts WHERE email = ? AND status != 'suspended'",
            (em,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_account_by_phone(phone: str) -> Optional[dict]:
    """Look up an account by its 10-digit mobile (normalized). None if not found."""
    ph = normalize_phone(phone)
    if not ph:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_accounts WHERE phone = ? AND status != 'suspended'",
            (ph,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_account_by_id(account_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_accounts WHERE account_id=?",
            (account_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_per_claim_status(account_id: int) -> Optional[dict]:
    """Return entitlement summary for the customer dashboard.
    Returns dict with balance/purchased/history/pending, or None if no records.
    - balance: number of paid entitlements not yet consumed (linked_claim_id IS NULL)
    - purchased: total paid entitlements ever purchased
    - history: all non-cancelled paid purchases, newest first
    - pending: list of pending_payment purchases (awaiting payment)
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT purchase_id, status, linked_claim_id, claim_type, insured_name,
                      insurer_name, disputed_amount, brief_description, amount_paid,
                      created_at, findings_note, review_note
               FROM nidaan_per_claim_purchase
               WHERE account_id=? AND status != 'cancelled'
               ORDER BY purchase_id DESC""",
            (account_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        return None
    paid_rows = [r for r in rows if r["status"] != "pending_payment"]
    pending_rows = [r for r in rows if r["status"] == "pending_payment"]
    available = sum(1 for r in paid_rows if r["status"] == "paid" and r["linked_claim_id"] is None)
    return {
        "balance": available,
        "purchased": len(paid_rows),
        "history": paid_rows,
        "pending": pending_rows,
    }


async def create_review_signup(
    name: str,
    phone: str,
    email: str,
    claim_type: str,
    insurer_name: str = "",
    disputed_amount: Optional[int] = None,
    notes: str = "",
    intermediary_code: str = "",
    intermediary_name: str = "",
    ref_code: str = "",
) -> dict:
    """Direct-insured signup: find/create account and create a pending_payment purchase.
    Returns dict with account_id, purchase_id, is_new, temp_password (if new account).

    ref_code: branch/staff referral code from the entry link (e.g. SP-XXXXXX). Attributed to the
    account FIRST-TOUCH (locked) so the ₹499 review is credited to whoever referred it — fixing the
    leak where review-signups always showed as "Direct lead".

    intermediary_code / intermediary_name: as printed on the policy. Recommended
    for legal correspondence; collected at intake per IRDAI guidelines."""
    import secrets as _sec
    name = _capname(name)   # #6: store names in caps
    email = email.strip().lower()
    account = await get_account_by_email(email)
    is_new = False
    temp_password = None
    if account:
        account_id = account["account_id"]
    else:
        is_new = True
        temp_password = _sec.token_urlsafe(10)
        account_id = await create_account(
            owner_name=name.strip(),
            email=email,
            phone=phone.strip(),
            password=temp_password,
            firm_name="",
        )
    # Referral attribution (first-touch, locked): credit the referrer for this ₹499 review.
    _rc = (ref_code or "").strip().upper()
    if _rc and await is_valid_ref_code(_rc):
        await set_account_branch(account_id, _rc)
    _fee = await review_fee_for(disputed_amount)   # Item #4: tiered review fee
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_per_claim_purchase
               (advisor_name, advisor_phone, advisor_email,
                insured_name, insured_phone, insurer_name,
                claim_type, disputed_amount, brief_description,
                amount_paid, status, account_id,
                intermediary_code, intermediary_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_payment', ?, ?, ?)""",
            (name.strip(), phone.strip(), email,
             name.strip(), phone.strip(), insurer_name.strip(),
             claim_type, disputed_amount, notes.strip(), _fee, account_id,
             (intermediary_code or "").strip(), (intermediary_name or "").strip()),
        )
        await conn.commit()
        purchase_id = cur.lastrowid
    return {
        "account_id": account_id,
        "purchase_id": purchase_id,
        "is_new": is_new,
        "temp_password": temp_password,
    }


async def grant_admin_review_credit(account_id: int, name: str, phone: str,
                                    email: str = "", amount: int = 499, ref: str = "") -> int:
    """Create a PAID ₹499 review credit for an account (used by super-admin payment links).
    Shows in the account's per-claim purchases and counts toward d2c revenue. Returns purchase_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_per_claim_purchase
               (advisor_name, advisor_phone, advisor_email, insured_name, insured_phone,
                insurer_name, claim_type, disputed_amount, brief_description, amount_paid,
                status, account_id, razorpay_order_id, intermediary_code, intermediary_name)
               VALUES (?, ?, ?, ?, ?, '', '', NULL, 'Paid via payment link', ?, 'paid', ?, ?, '', '')""",
            (name, phone, email, name, phone, int(amount), account_id, ref))
        await conn.commit()
        return cur.lastrowid


async def get_account_id_by_phone(phone: str) -> Optional[int]:
    ph = "".join(ch for ch in (phone or "") if ch.isdigit())[-10:]
    if len(ph) != 10:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT account_id FROM nidaan_accounts WHERE phone=? ORDER BY account_id LIMIT 1",
            (ph,))).fetchone()
        return row[0] if row else None


async def create_account_google(
    owner_name: str,
    email: str,
    plan: str = "silver",
    firm_name: str = "",
    branch_code: str = "",
    utm_source: str = "",
    utm_medium: str = "",
    utm_campaign: str = "",
) -> Optional[int]:
    """Create a Nidaan account via Google Sign-In (no password).
    Stores an unguessable pw_hash so password login is permanently disabled for these accounts.
    Returns account_id or None on duplicate email. Carries referral/marketing attribution."""
    pw_hash = "google$" + secrets.token_hex(32)
    owner_name = _capname(owner_name)   # #6: store names in caps (parity with create_account)
    code = (branch_code or "").strip().upper()
    channel, _rc = await resolve_channel(code, utm_source)
    us, um, uc = (utm_source or "").strip(), (utm_medium or "").strip(), (utm_campaign or "").strip()
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cur = await conn.execute(
                """INSERT INTO nidaan_accounts
                   (owner_name, email, phone, password_hash, firm_name, branch_code,
                    source_channel, utm_source, utm_medium, utm_campaign)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (owner_name, email.lower().strip(), "", pw_hash, firm_name, code,
                 channel, us, um, uc),
            )
            await conn.commit()
            new_id = cur.lastrowid
    except aiosqlite.IntegrityError:
        logger.warning("nidaan create_account_google: duplicate email %s", email)
        return None
    await record_event("signup_completed", channel=channel, ref_code=code,
                       utm_source=us, utm_medium=um, utm_campaign=uc,
                       account_id=new_id, contact=email.lower().strip())
    return new_id


async def authenticate_account(identifier: str, password: str) -> Optional[dict]:
    """Return account dict if credentials valid, else None. `identifier` may be an email
    OR a 10-digit mobile — mobile is the primary login id, and email still works when the
    account has one."""
    ident = (identifier or "").strip()
    if "@" in ident:
        account = await get_account_by_email(ident)
    else:
        account = await get_account_by_phone(ident) or await get_account_by_email(ident)
    if not account:
        return None
    if not _verify_password(password, account.get("password_hash", "")):
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_accounts SET last_login_at = CURRENT_TIMESTAMP WHERE account_id = ?",
            (account["account_id"],),
        )
        await conn.commit()
    return account


async def update_account_password(account_id: int, new_password: str) -> bool:
    """Hash and store a new password for the given account."""
    new_hash = _hash_password(new_password)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_accounts SET password_hash = ? WHERE account_id = ?",
            (new_hash, account_id),
        )
        await conn.commit()
    return True


# =============================================================================
#  SUBSCRIPTION OPERATIONS
# =============================================================================

async def get_active_subscription(account_id: int) -> Optional[dict]:
    """Return the current active subscription for an account."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT * FROM nidaan_subscriptions
               WHERE account_id = ? AND status = 'active'
               ORDER BY started_at DESC LIMIT 1""",
            (account_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_subscription(
    account_id: int,
    plan: str,
    amount_paid: int,
    razorpay_subscription_id: str = "",
    period_days: int = 90,
    razorpay_payment_id: str = "",
    actor_id: str = "",
    actor_name: str = "",
    verify_method: str = "",
) -> int:
    """Record a new subscription. Returns sub_id.

    `razorpay_subscription_id` actually holds the Razorpay ORDER id for one-time
    payments (legacy column name). `razorpay_payment_id` is the actual payment
    id used for refunds via POST /payments/{payment_id}/refund.

    `actor_id`/`actor_name` are the REAL staff who triggered a manual mark-paid (so the
    unified ledger stays accountable even under impersonation). `verify_method` lets the
    caller state how the payment was confirmed (signature|api_fetch|webhook|manual); when
    blank it is inferred from the payment id.
    """
    if plan not in PLAN_LIMITS:
        raise ValueError(f"Unknown Nidaan plan: {plan}")
    period_end = datetime.utcnow() + timedelta(days=period_days)
    # We only offer MONTHLY or ANNUAL (no quarterly) — label from the period.
    _cycle = "annual" if period_days >= 350 else "monthly"
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_subscriptions SET status='cancelled', cancelled_at=CURRENT_TIMESTAMP "
            "WHERE account_id=? AND status='active'",
            (account_id,),
        )
        cur = await conn.execute(
            """INSERT INTO nidaan_subscriptions
               (account_id, plan, amount_paid, razorpay_subscription_id, razorpay_payment_id,
                current_period_end, billing_cycle)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (account_id, plan, amount_paid, razorpay_subscription_id, razorpay_payment_id,
             period_end.isoformat(), _cycle),
        )
        await conn.commit()
        sub_id = cur.lastrowid
    # ── Unified payment ledger (single source of truth for Revenue + trail) ──────
    # Every subscription activation funnels through here, so one record_payment call
    # covers order-pay, recurring-verify, webhook and manual mark-paid alike.
    try:
        _is_manual = (razorpay_payment_id or "").upper().startswith("MANUAL")
        _total_paise = int(round(float(amount_paid or 0) * 100))
        try:
            _base_paise = int((await get_plan_cfg(plan)).get("price_paise") or 0)
        except Exception:
            _base_paise = 0
        if not _base_paise or _base_paise > _total_paise:
            _base_paise = _total_paise
        # For manual there is no gateway payment id → build a stable synthetic dedup key.
        _dedup = (razorpay_payment_id or razorpay_subscription_id or "").strip()
        if _is_manual or not _dedup:
            _dedup = f"sub:{account_id}:{razorpay_payment_id or razorpay_subscription_id or sub_id}"
        await record_payment(
            source="subscription", total_paise=_total_paise, base_paise=_base_paise,
            dedup_key=_dedup, gateway=("manual" if _is_manual else "razorpay"),
            razorpay_payment_id=("" if _is_manual else (razorpay_payment_id or "")),
            razorpay_subscription_id=razorpay_subscription_id or "",
            account_id=account_id, plan=plan,
            verified=(not _is_manual),
            verify_method=(verify_method or ("manual" if _is_manual else
                           ("api_fetch" if razorpay_subscription_id else "signature"))),
            actor_id=actor_id, actor_name=actor_name,
            note=(razorpay_payment_id if _is_manual else ""))
    except Exception as _pe:
        logger.warning("record_payment (subscription) failed: %s", _pe)
    return sub_id


# =============================================================================
#  CLAIM QUOTA
# =============================================================================

async def get_active_per_claim_purchase(account_id: int) -> Optional[dict]:
    """Return the most recent paid per-claim purchase for this account, or None.
    Used to grant dashboard access and enforce the 1-claim limit for ₹499 users.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT * FROM nidaan_per_claim_purchase
               WHERE account_id=? AND status='paid'
               ORDER BY purchase_id DESC LIMIT 1""",
            (account_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


def business_hours_deadline(start: datetime, hours: int = 48) -> datetime:
    """`start` + `hours` of BUSINESS time, skipping Sat & Sun entirely.
    The clock only advances on weekdays (Mon–Fri), so a Friday-evening payment's
    48-business-hour SLA lands mid-week, not on the weekend. Hour-by-hour walk
    (≤ a few hundred iterations for 48h) — simple and exact."""
    cur = start
    remaining = max(0, int(hours))
    while remaining > 0:
        cur += timedelta(hours=1)
        if cur.weekday() < 5:  # Mon=0 … Fri=4 count; Sat/Sun skipped
            remaining -= 1
    return cur


async def can_submit_claim(account_id: int) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    Priority order:
      1. Active subscription (all tiers) — quota enforced per month.
      2. Per-claim purchase (status='paid', no linked_claim_id yet) — exactly 1 claim.
    """
    sub = await get_active_subscription(account_id)
    if sub:
        plan = sub["plan"]
        # Read the claim cap from the (super-admin editable) config; fall back to the
        # hardcoded default only if the config hasn't been seeded.
        _cfg = await get_plan_cfg(plan)
        limit = _cfg.get("claims_per_month") if _cfg else PLAN_LIMITS.get(plan, {}).get("claims_per_month")
        if limit is None:
            return True, "ok"  # platinum / unlimited

        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM nidaan_plan_quota WHERE account_id = ?", (account_id,)
            )
            quota = await cur.fetchone()

        window_start = date.today() - timedelta(days=30)  # monthly claim window
        if quota is None:
            return True, "ok"
        stored_start = date.fromisoformat(str(quota["current_window_start"]))
        if stored_start < window_start:
            return True, "ok"  # window has rolled over, reset on next insert
        if quota["claims_this_window"] >= limit:
            return False, f"quota_exceeded_{plan}"
        return True, "ok"

    # No subscription — check per-claim entitlement balance
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT COUNT(*) AS available FROM nidaan_per_claim_purchase
               WHERE account_id=? AND status='paid' AND linked_claim_id IS NULL""",
            (account_id,),
        )
        row = await cur.fetchone()
    available = row["available"] if row else 0
    if available > 0:
        return True, "ok_per_claim"
    # Check if they have any past purchases (so we can give a meaningful error)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT COUNT(*) AS cnt FROM nidaan_per_claim_purchase WHERE account_id=? AND status NOT IN ('pending_payment','cancelled')",
            (account_id,),
        )
        row = await cur.fetchone()
    if row and row["cnt"] > 0:
        return False, "per_claim_balance_exhausted"

    return False, "no_active_subscription"


async def _increment_quota(account_id: int, conn: aiosqlite.Connection):
    """Upsert the rolling 30-day quota counter (call inside the same connection as claim insert)."""
    today = date.today().isoformat()
    window_start = (date.today() - timedelta(days=30)).isoformat()  # monthly claim window
    cur = await conn.execute(
        "SELECT current_window_start, claims_this_window FROM nidaan_plan_quota WHERE account_id=?",
        (account_id,),
    )
    row = await cur.fetchone()
    if row is None or row[0] < window_start:
        await conn.execute(
            """INSERT INTO nidaan_plan_quota (account_id, current_window_start, claims_this_window, updated_at)
               VALUES (?, ?, 1, CURRENT_TIMESTAMP)
               ON CONFLICT(account_id) DO UPDATE SET
                 current_window_start=excluded.current_window_start,
                 claims_this_window=1,
                 updated_at=CURRENT_TIMESTAMP""",
            (account_id, today),
        )
    else:
        await conn.execute(
            "UPDATE nidaan_plan_quota SET claims_this_window=claims_this_window+1, "
            "updated_at=CURRENT_TIMESTAMP WHERE account_id=?",
            (account_id,),
        )


# =============================================================================
#  CLAIM OPERATIONS
# =============================================================================

async def get_or_create_branch_house_account(branch_code: str) -> int:
    """One lightweight 'house' account per branch — branch-raised claims (on behalf of a
    customer) attach here so they reuse the whole existing claim pipeline. Synthetic
    email/phone; branch_code is left BLANK on the account so house accounts never inflate
    affiliate signup/earnings stats (the CLAIM itself carries branch_code + origin='branch')."""
    code = (branch_code or "").strip().upper()
    house_email = f"branch.{code.lower()}@house.nidaanpartner.internal"
    # Phone is left BLANK — it's a phone field, not a label. The house account is keyed by
    # its synthetic email; the phone unique-index only applies WHERE phone != '' so blanks
    # never collide. (Earlier a "HOUSE-<code>" marker leaked into the visible phone field.)
    house_phone = ""
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT account_id FROM nidaan_accounts WHERE email=?", (house_email,))).fetchone()
        if row:
            return row[0]
        import secrets as _secrets
        pw = _hash_password(_secrets.token_hex(16))
        cur = await conn.execute(
            "INSERT INTO nidaan_accounts (owner_name, email, phone, password_hash, firm_name, branch_code) "
            "VALUES (?,?,?,?,?,?)",
            (f"Branch {code} — house account", house_email, house_phone, pw, "", ""))
        await conn.commit()
        return cur.lastrowid


NO_SCOPE_ARCHIVE_DAYS = 5  # no_scope claims stay visible this long, then auto-archive


def _parse_ts(v):
    """Tolerant timestamp parse (isoformat or 'YYYY-MM-DD HH:MM:SS'). None on failure."""
    if not v:
        return None
    s = str(v).strip().replace("T", " ")
    from datetime import datetime as _dt
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.strptime(s[:26] if "." in s else s[:19], fmt)
        except ValueError:
            continue
    return None


async def list_branch_claims(branch_code: str, limit: int = 100) -> list[dict]:
    """Claims a branch (or staff SP- code) has raised (origin='branch'), newest first, with
    review + L2 state. Adds an `archived` flag: a no_scope claim auto-archives once its review
    is older than NO_SCOPE_ARCHIVE_DAYS (kept forever, just moved to the Archived view)."""
    from datetime import datetime as _dt, timedelta as _td
    code = (branch_code or "").strip().upper()
    cutoff = _dt.now() - _td(days=NO_SCOPE_ARCHIVE_DAYS)
    # Charge policy is global; the per-claim AMOUNT is the homepage tier (by disputed amount).
    _charge = (await get_ops_setting("branch_charge_policy", "l2_only") or "l2_only") != "free"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT claim_id, insured_name, insured_phone, claim_type, insurer_name, "
            "       disputed_amount, status, review_outcome, l2_payment_status, l2_fee_paid, "
            "       review_delivered_at, created_at "
            "FROM nidaan_claims WHERE origin='branch' AND UPPER(branch_code)=? "
            "ORDER BY claim_id DESC LIMIT ?", (code, limit))).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            archived = False
            if d.get("review_outcome") == "no_scope" and d.get("l2_payment_status") != "paid":
                dt = _parse_ts(d.get("review_delivered_at"))
                archived = bool(dt and dt < cutoff)
            d["archived"] = archived
            # Per-claim tiered L2 fee (₹499 / ₹2000 by disputed amount) — what they'd pay at GO.
            d["l2_fee"] = (await review_fee_for(d.get("disputed_amount"))) if _charge else 0
            out.append(d)
        return out


async def branch_l2_pricing() -> dict:
    """Current Level-2 charging config for branch-raised claims (super-admin editable).
    fee = rupees; policy: 'l2_only'|'all_claims' both charge at the GO step, 'free' never charges."""
    fee = int((await get_ops_setting("branch_l2_fee", "499") or "499") or 0)
    policy = (await get_ops_setting("branch_charge_policy", "l2_only") or "l2_only")
    return {"fee": fee, "policy": policy, "charge_required": policy != "free" and fee > 0}


async def branch_l2_fee_for_claim(claim_id: int) -> dict:
    """SINGLE SOURCE OF TRUTH for a branch/staff retail claim's Level-2 fee. The amount is the
    SAME tiered review fee as the homepage — review_fee_for(disputed_amount): ₹499, or ₹2000 when
    the disputed amount exceeds the threshold — collected only at the GO (can_fight) step. Whether
    we charge at all is the super-admin policy ('free' never charges). Amount in RUPEES.
    Every branch/staff L2 pay/link/verify/webhook path MUST use this so the fee is identical."""
    policy = (await get_ops_setting("branch_charge_policy", "l2_only") or "l2_only")
    if policy == "free":
        return {"fee": 0, "policy": policy, "charge_required": False}
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT disputed_amount FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    disputed = row[0] if row else None
    fee = await review_fee_for(disputed)   # tiered ₹499 / ₹2000 (>threshold)
    return {"fee": int(fee), "policy": policy, "charge_required": int(fee) > 0}


async def mark_l2_paid(claim_id: int, branch_code: str, fee: int, payment_id: str) -> bool:
    """Record a branch's Level-2 fee payment (or a free advance) and queue the claim for
    the legal team. Guarded to the owning branch + a GO ('can_fight') review; idempotent."""
    code = (branch_code or "").strip().upper()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT review_outcome, l2_payment_status FROM nidaan_claims "
            "WHERE claim_id=? AND origin='branch' AND UPPER(branch_code)=?",
            (claim_id, code))).fetchone()
        if not row:
            return False
        if row["review_outcome"] != "can_fight":
            return False
        if row["l2_payment_status"] == "paid":
            return True  # idempotent — already queued
        await conn.execute(
            "UPDATE nidaan_claims SET l2_payment_status='paid', l2_fee_paid=?, "
            "l2_payment_id=?, l2_paid_at=CURRENT_TIMESTAMP, last_status_at=CURRENT_TIMESTAMP "
            "WHERE claim_id=?", (int(fee or 0), (payment_id or "")[:80], claim_id))
        note = (f"Branch L2 fee Rs.{int(fee)} paid — queued for legal" if fee
                else "Branch sent to Level-2 (no charge) — queued for legal")
        await conn.execute(
            "INSERT INTO nidaan_claim_status_log (claim_id, to_status, note, changed_by_type, changed_by_id) "
            "VALUES (?, 'l2_queued', ?, 'branch', 0)", (claim_id, note))
        await conn.commit()
    if fee:
        try:
            await record_gst(payment_id, "branch_l2", int(fee), claim_id=claim_id)
        except Exception as _ge:
            logger.warning("record_gst (branch_l2) failed: %s", _ge)
        # Unified ledger: L2 fee funnels through here from every path (branch verify,
        # ops verify, webhook, reconcile) — record once, idempotent on payment_id.
        try:
            _acct = None
            async with aiosqlite.connect(DB_PATH) as _c:
                _r = await (await _c.execute(
                    "SELECT account_id FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
                _acct = _r[0] if _r else None
            _l2total = (await charge_with_gst(int(fee)))["total_paise"]
            await record_payment(
                source="branch_l2", total_paise=_l2total, base_paise=int(fee) * 100,
                dedup_key=(payment_id or f"l2:{claim_id}"), razorpay_payment_id=(payment_id or ""),
                account_id=_acct, claim_id=claim_id, branch_code=code,
                verified=bool(payment_id), verify_method=("signature" if payment_id else "manual"),
                note="branch L2 acceptance fee")
        except Exception as _pe:
            logger.warning("record_payment (branch_l2) failed: %s", _pe)
    # Branch/staff L2 fee now paid on a reviewed-GO claim → auto-move to ClaimShield.
    try:
        import biz_claimshield as _cs
        import asyncio as _aio
        _aio.create_task(_cs.auto_send_if_eligible(claim_id))
    except Exception:
        pass
    return True


# ── Razorpay Payment Links (branch L2 share-links + super-admin generated) ────
async def record_payment_link(plink_id: str, short_url: str, purpose: str, amount_paise: int, *,
                              claim_id: Optional[int] = None, plan: Optional[str] = None,
                              account_id: Optional[int] = None, branch_code: Optional[str] = None,
                              customer_name: str = "", customer_phone: str = "",
                              customer_email: str = "", created_by_type: str = "",
                              created_by_id: str = "", description: str = "",
                              expire_by: Optional[int] = None) -> None:
    """Persist a generated Razorpay payment link so we can reconcile its webhook + show status."""
    customer_name = _capname(customer_name)   # #6: store names in caps
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT OR REPLACE INTO nidaan_payment_links
               (plink_id, short_url, purpose, amount_paise, claim_id, plan, account_id,
                branch_code, customer_name, customer_phone, customer_email, status,
                created_by_type, created_by_id, description, expire_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, 'created', ?,?,?,?)""",
            (plink_id, short_url, purpose, int(amount_paise), claim_id, plan, account_id,
             ((branch_code or "").upper() or None), customer_name, customer_phone, customer_email,
             created_by_type, str(created_by_id), description, expire_by))
        await conn.commit()


async def get_payment_link(plink_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_payment_links WHERE plink_id=?", (plink_id,))).fetchone()
        return dict(row) if row else None


async def mark_payment_link_paid(plink_id: str, razorpay_payment_id: str = "",
                                 account_id: Optional[int] = None) -> bool:
    """Flip a link to 'paid' (idempotent). Returns True only if THIS call did the flip."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "UPDATE nidaan_payment_links SET status='paid', razorpay_payment_id=?, "
            "paid_at=CURRENT_TIMESTAMP, account_id=COALESCE(?, account_id) "
            "WHERE plink_id=? AND status!='paid'",
            (razorpay_payment_id or "", account_id, plink_id))
        await conn.commit()
        flipped = cur.rowcount > 0
        row = await (await conn.execute(
            "SELECT purpose, amount_paise, claim_id, account_id, branch_code FROM "
            "nidaan_payment_links WHERE plink_id=?", (plink_id,))).fetchone()
    # Unified ledger: record ONLY standalone 'custom' links here. subscription/review499/l2
    # links materialise a sub/purchase/claim and are recorded via those funnels (no double-count).
    if flipped and row and (row["purpose"] or "") == "custom":
        try:
            await record_payment(
                source="payment_link", total_paise=int(row["amount_paise"] or 0),
                dedup_key=(razorpay_payment_id or plink_id), razorpay_payment_id=(razorpay_payment_id or ""),
                account_id=row["account_id"], claim_id=row["claim_id"],
                branch_code=(row["branch_code"] or ""), verified=bool(razorpay_payment_id),
                verify_method="webhook", note=f"custom payment link {plink_id}")
        except Exception as _pe:
            logger.warning("record_payment (custom link) failed %s: %s", plink_id, _pe)
    return flipped


async def set_payment_link_account(plink_id: str, account_id: int) -> None:
    """Link a payment-link row to the payer's account (safe to call after it's already paid)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_payment_links SET account_id=? WHERE plink_id=? AND (account_id IS NULL OR account_id='')",
            (account_id, plink_id))
        await conn.commit()


async def list_payment_links(limit: int = 100, created_by_type: str = "",
                             created_by_id: str = "") -> list[dict]:
    q = "SELECT * FROM nidaan_payment_links"
    conds, params = [], []
    if created_by_type:
        conds.append("created_by_type=?"); params.append(created_by_type)
    if created_by_id:
        conds.append("created_by_id=?"); params.append(str(created_by_id))
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY created_at DESC LIMIT ?"; params.append(int(limit))
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(q, params)).fetchall()
        return [dict(r) for r in rows]


async def submit_claim(
    account_id: int,
    user_id: Optional[int],
    claim_type: str,
    insured_name: str,
    insured_phone: str,
    insured_email: str = "",
    insurer_name: str = "",
    policy_no: str = "",
    disputed_amount: Optional[int] = None,
    claim_event_date: Optional[str] = None,
    policy_inception_date: Optional[str] = None,
    tpa_name: str = "",
    type_specific: Optional[dict] = None,
    notes_from_agent: str = "",
    intermediary_code: str = "",
    intermediary_name: str = "",
    branch_code: str = "",
    payment_status: str = "subscription",
    skip_eligibility: bool = False,
    origin: str = "",
    complainant_name: str = "",
    complainant_phone: str = "",
    complainant_email: str = "",
    complainant_role: str = "",
) -> tuple[Optional[int], str]:
    """
    Submit a new claim after quota check.
    Returns (claim_id, status_msg).
    For per-claim users, links the resulting claim_id back to their purchase.

    intermediary_code/intermediary_name: as printed on the policy. Required at
    intake for legal correspondence (IRDAI compliance).

    payment_status: 'unpaid_lead' | 'paid' | 'subscription' — the ₹499 funnel
        path. Persisted on the claim.
    skip_eligibility: when True (free-lead funnel) the quota/subscription
        eligibility check is skipped — a free submission is always allowed; the
        ₹499 is collected later. Quota increment + purchase-link below are
        naturally skipped too (no subscription, no purchase).
    """
    if not skip_eligibility:
        allowed, reason = await can_submit_claim(account_id)
        if not allowed:
            return None, reason

    insured_name = _capname(insured_name)   # #6: store names in caps
    type_specific_json = json.dumps(type_specific or {})
    # Complainant = presenter/contact who provides documents. Defaults to the insured (patient)
    # when the form doesn't distinguish, so existing callers keep working unchanged.
    complainant_name = _capname(complainant_name) or insured_name
    complainant_phone = (complainant_phone or "").strip() or insured_phone
    complainant_email = (complainant_email or "").strip() or insured_email
    complainant_role = (complainant_role or "").strip() or ("branch" if (origin or "") == "branch" else "self")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_claims
               (account_id, user_id, claim_type, insured_name, insured_phone,
                insured_email, insurer_name, policy_no, disputed_amount,
                claim_event_date, policy_inception_date, tpa_name, type_specific,
                notes_from_agent, intermediary_code, intermediary_name, branch_code, payment_status, origin,
                complainant_name, complainant_phone, complainant_email, complainant_role)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_id, user_id, claim_type, insured_name, insured_phone,
             insured_email, insurer_name, policy_no, disputed_amount,
             claim_event_date, (policy_inception_date or None), (tpa_name or "").strip(),
             type_specific_json, notes_from_agent,
             (intermediary_code or "").strip(), (intermediary_name or "").strip(),
             (branch_code or "").strip().upper(),
             payment_status, (origin or "").strip(),
             complainant_name, complainant_phone, complainant_email, complainant_role),
        )
        claim_id = cur.lastrowid
        await conn.execute(
            """INSERT INTO nidaan_claim_status_log
               (claim_id, to_status, note, changed_by_type, changed_by_id)
               VALUES (?, 'intimated', 'Claim submitted by advisor', 'advisor', ?)""",
            (claim_id, account_id),
        )
        # Quota: only increment for subscription users (per-claim users have 1-claim hard limit via linked_claim_id)
        sub = await get_active_subscription(account_id)
        if sub:
            await _increment_quota(account_id, conn)
        await conn.commit()

    # Per-claim users: link this claim back to their purchase (enforces the 1-claim limit server-side)
    purchase = await get_active_per_claim_purchase(account_id)
    if purchase and purchase["linked_claim_id"] is None:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE nidaan_per_claim_purchase SET linked_claim_id=? WHERE purchase_id=?",
                (claim_id, purchase["purchase_id"]),
            )
            await conn.commit()

    logger.info("nidaan claim %d submitted: account=%d type=%s", claim_id, account_id, claim_type)
    return claim_id, "ok"


async def ensure_claim_for_paid_purchase(purchase_id: int) -> Optional[int]:
    """Idempotently materialise a nidaan_claims row for a PAID D2C ₹499 review purchase.

    The D2C ₹499 funnel (product 'nidaan_review_999') only ever wrote a
    nidaan_per_claim_purchase row, so those paid reviews were visible in the
    "Pending Reviews" widget but NOT in the main claims workspace (All Claims /
    search / filters / assignment) — which read nidaan_claims. This converts a
    paid purchase into a real claim so BOTH ₹499 funnels land in one place.

    Safe to call repeatedly and from any payment path:
      • no-op if the purchase isn't paid,
      • no-op for a bare credit (super-admin grant with no intake details),
      • no-op if it was already converted (returns the existing claim_id).
    Returns the linked claim_id (existing or new), or None when nothing to do.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_per_claim_purchase WHERE purchase_id=?", (purchase_id,))).fetchone()
    if not row:
        return None
    p = dict(row)
    if p.get("status") != "paid":
        return None
    if p.get("linked_claim_id"):
        return p["linked_claim_id"]                     # already converted — idempotent
    # Bare credit (no intake details captured) → leave as an unconsumed entitlement.
    if not (p.get("claim_type") or p.get("insurer_name") or p.get("insured_name")):
        return None
    account_id = p.get("account_id")
    if not account_id:
        return None
    claim_id, msg = await submit_claim(
        account_id=account_id,
        user_id=None,
        claim_type=(p.get("claim_type") or "other"),
        insured_name=(p.get("insured_name") or p.get("advisor_name") or ""),
        insured_phone=(p.get("insured_phone") or p.get("advisor_phone") or ""),
        insured_email=(p.get("insured_email") or p.get("advisor_email") or ""),
        insurer_name=(p.get("insurer_name") or ""),
        policy_no=(p.get("policy_no") or ""),
        disputed_amount=p.get("disputed_amount"),
        notes_from_agent=(p.get("brief_description") or ""),
        intermediary_code=(p.get("intermediary_code") or ""),
        intermediary_name=(p.get("intermediary_name") or ""),
        payment_status="paid",
        skip_eligibility=True,                          # already paid — never gate on quota
        origin="d2c_review",
    )
    if not claim_id:
        logger.error("ensure_claim_for_paid_purchase: submit_claim failed purchase=%s msg=%s",
                     purchase_id, msg)
        return None
    # Pin the link to THIS purchase explicitly (submit_claim auto-links the most-recent
    # paid purchase; make it deterministic and record the conversion).
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_per_claim_purchase "
            "SET linked_claim_id=?, converted_to_claim_id=? WHERE purchase_id=?",
            (claim_id, claim_id, purchase_id))
        await conn.commit()
    logger.info("ensure_claim_for_paid_purchase: purchase=%s → claim=%s (account=%s)",
                purchase_id, claim_id, account_id)
    return claim_id


async def update_claim_status(
    claim_id: int,
    new_status: str,
    changed_by_type: str,
    changed_by_id: int,
    note: str = "",
) -> bool:
    """Update claim status and write a log entry."""
    if new_status not in CLAIM_STATUSES:
        raise ValueError(f"Invalid claim status: {new_status}")

    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT status FROM nidaan_claims WHERE claim_id = ?", (claim_id,)
        )
        row = await cur.fetchone()
        if not row:
            return False
        old_status = row[0]
        now = datetime.utcnow().isoformat()
        await conn.execute(
            "UPDATE nidaan_claims SET status=?, last_status_at=? WHERE claim_id=?",
            (new_status, now, claim_id),
        )
        if new_status in ("resolved_won", "resolved_lost", "closed", "withdrawn"):
            await conn.execute(
                "UPDATE nidaan_claims SET closed_at=? WHERE claim_id=?",
                (now, claim_id),
            )
        await conn.execute(
            """INSERT INTO nidaan_claim_status_log
               (claim_id, from_status, to_status, note, changed_by_type, changed_by_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (claim_id, old_status, new_status, note, changed_by_type, changed_by_id),
        )
        await conn.commit()
    return True


async def deliver_review(claim_id: int, outcome: str, findings: str,
                         changed_by_type: str, changed_by_id: int) -> bool:
    """Ops delivers the legal ASSESSMENT to the customer (NidaanPartner only does
    the review — fighting the claim is handled offline by the legal team).
    Sets status='review_delivered', records the outcome + the findings shared with
    the customer, and logs it. Caller fires on_report_ready for notifications."""
    if outcome not in REVIEW_OUTCOMES:
        raise ValueError(f"Invalid review outcome: {outcome}")
    findings = (findings or "").strip()
    if not findings:
        raise ValueError("findings (the assessment shared with the customer) is required")
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT status FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
        if not row:
            return False
        old_status = row[0]
        await conn.execute(
            "UPDATE nidaan_claims SET status='review_delivered', review_outcome=?, "
            "review_findings=?, review_delivered_at=?, last_status_at=? WHERE claim_id=?",
            (outcome, findings, now, now, claim_id))
        await conn.execute(
            "INSERT INTO nidaan_claim_status_log (claim_id, from_status, to_status, note, "
            "changed_by_type, changed_by_id) VALUES (?, ?, 'review_delivered', ?, ?, ?)",
            (claim_id, old_status, f"outcome={outcome}", changed_by_type, changed_by_id))
        await conn.commit()
    # Paid + reviewed-GO claims auto-move to ClaimShield (L2). Best-effort, non-blocking.
    if outcome == "can_fight":
        try:
            import biz_claimshield as _cs
            import asyncio as _aio
            _aio.create_task(_cs.auto_send_if_eligible(claim_id))
        except Exception:
            pass
    return True


async def get_claim_with_account(claim_id: int) -> Optional[dict]:
    """Fetch a single claim joined with its account email and owner_name."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT c.*, a.email, a.owner_name, a.phone AS advisor_phone
            FROM nidaan_claims c
            JOIN nidaan_accounts a ON a.account_id = c.account_id
            WHERE c.claim_id = ?
            """,
            (claim_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_claims(
    account_id: int,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List claims for an account, optionally filtered by status."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if status:
            cur = await conn.execute(
                "SELECT * FROM nidaan_claims WHERE account_id=? AND status=? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (account_id, status, limit, offset),
            )
        else:
            cur = await conn.execute(
                "SELECT * FROM nidaan_claims WHERE account_id=? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (account_id, limit, offset),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_claim_detail(claim_id: int, account_id: int) -> Optional[dict]:
    """Return a single claim (ownership-verified) plus its full status history."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Ownership check: claim must belong to this account
        cur = await conn.execute(
            "SELECT * FROM nidaan_claims WHERE claim_id=? AND account_id=?",
            (claim_id, account_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        claim = dict(row)
        log_cur = await conn.execute(
            "SELECT * FROM nidaan_claim_status_log WHERE claim_id=? ORDER BY changed_at ASC",
            (claim_id,),
        )
        claim["status_log"] = [dict(r) for r in await log_cur.fetchall()]
        return claim


# =============================================================================
#  ADMIN OPERATIONS
# =============================================================================

async def get_all_claims_admin(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Super-admin: list all claims across all accounts."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if status:
            cur = await conn.execute(
                "SELECT c.*, a.owner_name, a.firm_name FROM nidaan_claims c "
                "JOIN nidaan_accounts a ON c.account_id=a.account_id "
                "WHERE c.status=? ORDER BY c.created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        else:
            cur = await conn.execute(
                "SELECT c.*, a.owner_name, a.firm_name FROM nidaan_claims c "
                "JOIN nidaan_accounts a ON c.account_id=a.account_id "
                "ORDER BY c.created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def assign_claim(claim_id: int, admin_id: int, assigning_admin_id: int) -> bool:
    """Assign a claim to a legal team member."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claims SET assigned_to_legal_user_id=? WHERE claim_id=?",
            (admin_id, claim_id),
        )
        await conn.execute(
            """INSERT INTO nidaan_claim_status_log
               (claim_id, to_status, note, changed_by_type, changed_by_id)
               VALUES (?, 'assigned', 'Assigned to legal team', 'super_admin', ?)""",
            (claim_id, assigning_admin_id),
        )
        await conn.commit()
    return True


# =============================================================================
#  PRODUCT LINK (Sarathi ↔ Nidaan bridge)
# =============================================================================

async def link_to_sarathi(nidaan_account_id: int, sarathi_tenant_id: int, source: str = "nidaan_bundle") -> int:
    """Create or reactivate a product link. Returns link_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        # Deactivate any previous link for this nidaan account
        await conn.execute(
            "UPDATE product_link SET active=0, unlinked_at=CURRENT_TIMESTAMP "
            "WHERE nidaan_account_id=? AND active=1",
            (nidaan_account_id,),
        )
        cur = await conn.execute(
            """INSERT INTO product_link (nidaan_account_id, sarathi_tenant_id, source)
               VALUES (?, ?, ?)""",
            (nidaan_account_id, sarathi_tenant_id, source),
        )
        await conn.commit()
        return cur.lastrowid


async def get_sarathi_tenant_for_nidaan(nidaan_account_id: int) -> Optional[int]:
    """Return the linked sarathi_tenant_id, or None."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT sarathi_tenant_id FROM product_link "
            "WHERE nidaan_account_id=? AND active=1 LIMIT 1",
            (nidaan_account_id,),
        )
        row = await cur.fetchone()
        return row[0] if row else None


# =============================================================================
#  JWT HELPERS  (Nidaan-namespaced — cannot be used as Sarathi tokens)
# =============================================================================

import jwt as _jwt_lib


def _nidaan_secret() -> str:
    """Return a namespaced JWT secret so Sarathi tokens can't be used here."""
    base = os.environ.get("JWT_SECRET", "")
    if not base:
        base = "nidaan-fallback-secret-change-in-env"
        logger.warning("JWT_SECRET not set — Nidaan tokens use fallback secret")
    return base + ":nidaan"


def create_nidaan_token(account_id: int, email: str, plan: str = "") -> str:
    """Create a signed JWT for a Nidaan account session (valid 30 days)."""
    payload = {
        "typ": "nidaan",
        "sub": str(account_id),  # PyJWT v2.9+ requires sub to be a string
        "email": email,
        "plan": plan,
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(days=30)).timestamp()),
    }
    return _jwt_lib.encode(payload, _nidaan_secret(), algorithm="HS256")


def verify_nidaan_token(token: str) -> Optional[dict]:
    """Decode and verify a Nidaan JWT. Returns payload dict or None."""
    try:
        payload = _jwt_lib.decode(
            token, _nidaan_secret(), algorithms=["HS256"],
            options={"verify_sub": False}  # sub may be int (old tokens) or str (new)
        )
        if payload.get("typ") != "nidaan":
            return None
        # Normalise sub to int for all callers
        payload["sub"] = int(payload["sub"])
        return payload
    except Exception as e:
        logger.debug("Nidaan token verify failed: %s", e)
        return None


# ── Branch portal (affiliate self-service) ────────────────────────────────────
def create_branch_token(branch_code: str) -> str:
    """Signed JWT for a branch-portal session (7 days), scoped to ONE branch_code."""
    payload = {
        "typ": "nidaan_branch",
        "sub": (branch_code or "").strip().upper(),
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(days=7)).timestamp()),
    }
    return _jwt_lib.encode(payload, _nidaan_secret(), algorithm="HS256")


def verify_branch_token(token: str) -> Optional[str]:
    """Decode a branch-portal token → branch_code, or None if invalid/wrong type."""
    try:
        payload = _jwt_lib.decode(token, _nidaan_secret(), algorithms=["HS256"])
        if payload.get("typ") != "nidaan_branch":
            return None
        code = (payload.get("sub") or "").strip().upper()
        return code or None
    except Exception:
        return None


def create_branch_magic_token(branch_code: str, email: str, minutes: int = 20) -> str:
    """Short-lived, single-use-feel one-click login token for a branch (emailed as a link).
    Bound to BOTH the branch_code and the login email; the landing endpoint re-checks the
    branch is still active before issuing a real session. Kept separate typ so it can never
    be used as a session token."""
    # NOTE: use a real POSIX epoch (time.time()), NOT datetime.utcnow().timestamp() — the
    # latter is naive-local and shifts by the server's TZ offset (e.g. +0200 CEST), which
    # silently pre-expires short-lived tokens. Long-lived session tokens absorb the shift;
    # this one (minutes) cannot.
    now = int(time.time())
    payload = {
        "typ": "nidaan_branch_magic",
        "sub": (branch_code or "").strip().upper(),
        "email": (email or "").strip().lower(),
        "iat": now,
        "exp": now + max(1, int(minutes)) * 60,
    }
    return _jwt_lib.encode(payload, _nidaan_secret(), algorithm="HS256")


def verify_branch_magic_token(token: str) -> Optional[dict]:
    """Decode a branch magic-login token → {branch_code, email}, or None."""
    try:
        payload = _jwt_lib.decode(token, _nidaan_secret(), algorithms=["HS256"])
        if payload.get("typ") != "nidaan_branch_magic":
            return None
        code = (payload.get("sub") or "").strip().upper()
        email = (payload.get("email") or "").strip().lower()
        if not code:
            return None
        return {"branch_code": code, "email": email}
    except Exception:
        return None


async def get_branch_by_email(email: str) -> Optional[dict]:
    """Find an ACTIVE branch by its login/contact email (the @nidaanpartner.com address).
    Disabled branches cannot log in."""
    em = (email or "").strip().lower()
    if not em or "@" not in em:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_branches WHERE LOWER(contact_email)=? AND status='active'",
            (em,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_branch_reconciliation(branch_code: str) -> Optional[dict]:
    """One branch's reconciliation summary (revenue, share_pct, payout, counts)."""
    code = (branch_code or "").strip().upper()
    for b in await list_branches(include_disabled=True):
        if b["branch_code"] == code:
            return b
    return None


async def get_branch_attributed_accounts(branch_code: str) -> list[dict]:
    """Accounts attributed to a branch (name, MASKED mobile, signup date, paid flag, plan) —
    only what the branch needs to reconcile its commission. No customer claim details / PII
    beyond a masked mobile."""
    code = (branch_code or "").strip().upper()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            f"""SELECT a.account_id, a.owner_name, a.phone, a.created_at, s.plan AS plan,
                       {_BRANCH_PAID_EXISTS} AS is_paid
                FROM nidaan_accounts a
                LEFT JOIN nidaan_subscriptions s
                       ON s.account_id=a.account_id AND s.status='active'
                WHERE UPPER(a.branch_code)=?
                ORDER BY a.created_at DESC""",
            (code,))
        rows = [dict(r) for r in await cur.fetchall()]
    out = []
    for r in rows:
        ph = (r.get("phone") or "").strip()
        masked = ("•••• " + ph[-4:]) if len(ph) >= 4 else "—"
        out.append({
            "account_id": r.get("account_id"),
            "owner_name": r.get("owner_name") or "—",
            "mobile_masked": masked,
            "created_at": r.get("created_at"),
            "plan": r.get("plan"),
            "paid": bool(r.get("is_paid")),
        })
    return out


# ── Customer support chat (AI first-line + human handoff) ─────────────────────
# Support origin channels (single source of truth). Segments the chat inbox + analytics:
#   homepage=anon nidaanpartner.com visitor · subscriber=logged-in customer (plan derived
#   via account_id) · review=one-time review page · branch/staff=partner dashboards ·
#   web=legacy/fallback · whatsapp/email=other inbound rails.
SUPPORT_CHANNELS = ("web", "homepage", "subscriber", "review", "branch", "staff", "whatsapp", "email")


async def _ensure_support_extra_columns(conn) -> None:
    """Add the rating/session columns if they don't exist yet (ALTER-on-first-use is
    lazy, so SELECTs from ops analytics must guarantee the columns are present)."""
    for col, typ in (("rating", "INTEGER"), ("rated_at", "TIMESTAMP"), ("closed_at", "TIMESTAMP")):
        try:
            await conn.execute(f"ALTER TABLE nidaan_support_threads ADD COLUMN {col} {typ}")
        except Exception:
            pass


async def create_support_thread(name: str = "", contact: str = "",
                                account_id: Optional[int] = None,
                                channel: str = "web", lang: str = "") -> dict:
    """Start a support conversation. Returns {thread_id, thread_key}. thread_key is a
    per-thread secret the client must present to continue/read (enumeration-safe)."""
    key = secrets.token_urlsafe(24)
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_support_threads (thread_key, account_id, name, contact, channel, lang)
               VALUES (?,?,?,?,?,?)""",
            (key, account_id, (name or "").strip()[:80], (contact or "").strip()[:120],
             channel if channel in SUPPORT_CHANNELS else "web",
             lang if lang in ("en", "hi", "hinglish") else ""))
        await conn.commit()
        return {"thread_id": cur.lastrowid, "thread_key": key}


async def find_open_support_thread(*, account_id=None, contact: str = "",
                                   channel: str = "", max_age_hours: int = 720) -> Optional[dict]:
    """An existing OPEN thread for the SAME person, so one customer does not end up as several
    parallel conversations in the support inbox.

    SECURITY: this returns the thread_key, which is the per-thread secret that lets a client read
    the history. So we only ever match on an identity the caller has actually PROVEN —
    an authenticated account_id, or a WhatsApp msisdn (Meta verifies number possession). We do
    NOT match on a typed-in email/phone from an anonymous visitor, because that would let anyone
    who guesses a contact string read that person's conversation."""
    if not account_id and not (contact and channel == "whatsapp"):
        return None
    where, params = ["status IN ('ai','escalated')",
                     "last_at > datetime('now', ?)"], [f"-{int(max_age_hours)} hours"]
    if account_id:
        where.append("account_id=?")
        params.append(account_id)
    else:
        where.append("contact=? AND channel='whatsapp'")
        params.append(contact)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            f"SELECT * FROM nidaan_support_threads WHERE {' AND '.join(where)} "
            f"ORDER BY thread_id DESC LIMIT 1", params)).fetchone()
    return dict(row) if row else None


async def set_support_rating(thread_id: int, rating: int) -> None:
    """Record a 👍/👎 (1 / -1) on a support thread (adds the columns on first use)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_support_extra_columns(conn)
        await conn.execute(
            "UPDATE nidaan_support_threads SET rating=?, rated_at=datetime('now') WHERE thread_id=?",
            (1 if rating > 0 else -1, thread_id))
        await conn.commit()


async def close_support_session(thread_id: int) -> None:
    """End a support session (its thread) — files it to history. Adds the column on first use."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_support_extra_columns(conn)
        await conn.execute(
            "UPDATE nidaan_support_threads SET status='closed', closed_at=datetime('now') "
            "WHERE thread_id=? AND COALESCE(status,'') != 'closed'", (thread_id,))
        await conn.commit()


async def get_support_thread(thread_id: int, thread_key: str) -> Optional[dict]:
    """Fetch a thread only if the thread_key matches (constant-time)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_support_threads WHERE thread_id=?", (thread_id,))).fetchone()
    if not row:
        return None
    import hmac as _hmac
    if not _hmac.compare_digest(row["thread_key"] or "", thread_key or ""):
        return None
    return dict(row)


async def add_support_message(thread_id: int, sender_type: str, body: str) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_support_messages (thread_id, sender_type, body) VALUES (?,?,?)",
            (thread_id, sender_type if sender_type in ("customer", "ai", "staff") else "customer",
             (body or "")[:4000]))
        await conn.execute(
            "UPDATE nidaan_support_threads SET last_at=CURRENT_TIMESTAMP WHERE thread_id=?",
            (thread_id,))
        await conn.commit()
        return cur.lastrowid


async def get_support_messages(thread_id: int, limit: int = 200, after_id: int = 0) -> list[dict]:
    """Messages for a thread. `after_id` returns only messages with msg_id > after_id
    (used by the widget's realtime poll to fetch just the new ones)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT msg_id, sender_type, body, created_at FROM nidaan_support_messages "
            "WHERE thread_id=? AND msg_id>? ORDER BY msg_id ASC LIMIT ?",
            (thread_id, after_id, limit))).fetchall()
        return [dict(r) for r in rows]


async def set_support_status(thread_id: int, status: str) -> None:
    if status not in ("ai", "escalated", "closed"):
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_support_threads SET status=? WHERE thread_id=?", (status, thread_id))
        await conn.commit()


async def get_support_thread_for_nudge(thread_id: int) -> Optional[dict]:
    """Internal (no thread_key) — fields needed to decide + send a visitor-fallback nudge."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT thread_id, thread_key, account_id, name, contact, lang, "
            "sub_last_seen_msg_id, last_nudge_msg_id FROM nidaan_support_threads WHERE thread_id=?",
            (thread_id,))).fetchone()
        return dict(row) if row else None


async def set_support_nudged(thread_id: int, msg_id: int) -> None:
    """Record that we've emailed the visitor a reopen nudge for staff message `msg_id`."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_support_threads SET last_nudge_msg_id=? WHERE thread_id=?", (msg_id, thread_id))
        await conn.commit()


async def clear_support_sa_escalation(thread_id: int) -> None:
    """A staffer replied → clear the super-admin escalation flag so a later unanswered message
    can escalate again (notif cluster #2 idempotency)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_support_threads SET sa_escalated_at=NULL WHERE thread_id=?", (thread_id,))
        await conn.commit()


async def list_support_threads_ops(status: Optional[str] = None, channel: Optional[str] = None,
                                   limit: int = 150) -> list[dict]:
    """Ops support inbox: all threads (escalated first, newest activity first) with a preview.
    Optional status + channel filters (channel segments the inbox by origin)."""
    clauses, params = [], []
    if status in ("ai", "escalated", "closed"):
        clauses.append("t.status=?"); params.append(status)
    if channel in SUPPORT_CHANNELS:
        clauses.append("t.channel=?"); params.append(channel)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_support_extra_columns(conn)
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            f"""SELECT t.thread_id, t.name, t.contact, t.channel, t.status,
                       t.created_at, t.last_at, t.rating, t.closed_at,
                       (SELECT COUNT(*) FROM nidaan_support_messages m
                         WHERE m.thread_id=t.thread_id) AS msg_count,
                       (SELECT body FROM nidaan_support_messages m
                         WHERE m.thread_id=t.thread_id AND m.sender_type='customer'
                         ORDER BY m.msg_id DESC LIMIT 1) AS last_customer
                FROM nidaan_support_threads t {where}
                ORDER BY (t.status='escalated') DESC, t.last_at DESC LIMIT ?""",
            params + [limit])).fetchall()
        return [dict(r) for r in rows]


async def get_support_thread_meta(thread_id: int) -> Optional[dict]:
    """Thread row for ops (no key needed — staff-authed at the route)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_support_extra_columns(conn)
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT thread_id, name, contact, channel, status, created_at, last_at, rating, closed_at "
            "FROM nidaan_support_threads WHERE thread_id=?", (thread_id,))).fetchone()
        return dict(row) if row else None


async def support_analytics(days: int = 30) -> dict:
    """Support/chat analytics over the last `days` — overall + per-channel + plan-wise
    breakdown of subscriber chats, ratings (👍/👎) and escalation rate. Staff-only (route)."""
    days = max(1, min(int(days or 30), 365))
    since = f"-{days} days"
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_support_extra_columns(conn)
        conn.row_factory = aiosqlite.Row
        # Overall
        tot = await (await conn.execute(
            f"""SELECT COUNT(*) AS sessions,
                       SUM(CASE WHEN status='escalated' THEN 1 ELSE 0 END) AS escalated,
                       SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) AS closed,
                       SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) AS up,
                       SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END) AS down
                FROM nidaan_support_threads
                WHERE created_at >= datetime('now', ?)""", (since,))).fetchone()
        # Per channel
        by_ch = await (await conn.execute(
            f"""SELECT COALESCE(NULLIF(channel,''),'web') AS channel, COUNT(*) AS sessions,
                       SUM(CASE WHEN status='escalated' THEN 1 ELSE 0 END) AS escalated,
                       SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) AS up,
                       SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END) AS down
                FROM nidaan_support_threads
                WHERE created_at >= datetime('now', ?)
                GROUP BY COALESCE(NULLIF(channel,''),'web')
                ORDER BY sessions DESC""", (since,))).fetchall()
        # Subscriber chats broken down by the account's current plan (plan-wise).
        # Correlated subquery (not a JOIN) so an account with >1 active sub can't
        # multiply a thread's row.
        by_plan = await (await conn.execute(
            f"""SELECT COALESCE((SELECT s.plan FROM nidaan_subscriptions s
                                  WHERE s.account_id=t.account_id AND s.status='active'
                                  ORDER BY s.started_at DESC LIMIT 1), '(no plan)') AS plan,
                       COUNT(*) AS sessions,
                       SUM(CASE WHEN t.rating=1 THEN 1 ELSE 0 END) AS up,
                       SUM(CASE WHEN t.rating=-1 THEN 1 ELSE 0 END) AS down
                FROM nidaan_support_threads t
                WHERE t.channel='subscriber' AND t.created_at >= datetime('now', ?)
                GROUP BY plan
                ORDER BY sessions DESC""", (since,))).fetchall()
    d = dict(tot) if tot else {}
    sessions = d.get("sessions") or 0
    rated = (d.get("up") or 0) + (d.get("down") or 0)
    return {
        "days": days,
        "sessions": sessions,
        "escalated": d.get("escalated") or 0,
        "closed": d.get("closed") or 0,
        "up": d.get("up") or 0,
        "down": d.get("down") or 0,
        "rated": rated,
        "csat": (round(100 * (d.get("up") or 0) / rated) if rated else None),
        "escalation_rate": (round(100 * (d.get("escalated") or 0) / sessions) if sessions else 0),
        "by_channel": [dict(r) for r in by_ch],
        "by_plan": [dict(r) for r in by_plan],
    }


async def update_support_thread_contact(thread_id: int, name: str = "", contact: str = "") -> None:
    """Fill in a thread's name/contact (used when a visitor leaves details as a lead)."""
    sets, params = [], []
    if name:
        sets.append("name=?"); params.append(name.strip()[:80])
    if contact:
        sets.append("contact=?"); params.append(contact.strip()[:120])
    if not sets:
        return
    params.append(thread_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE nidaan_support_threads SET {', '.join(sets)} WHERE thread_id=?", params)
        await conn.commit()


# ── Support business hours (super-admin editable) ─────────────────────────────
_DEFAULT_BUSINESS_HOURS = {"days": [0, 1, 2, 3, 4], "start": "10:00", "end": "18:00"}  # Mon–Fri 10–6 IST


async def get_business_hours() -> dict:
    """Support business hours (IST). days = Python weekdays (Mon=0 … Sun=6)."""
    raw = await get_ops_setting("support_business_hours", "")
    if raw:
        try:
            d = json.loads(raw)
            days = [int(x) for x in d.get("days", _DEFAULT_BUSINESS_HOURS["days"]) if 0 <= int(x) <= 6]
            return {"days": days or _DEFAULT_BUSINESS_HOURS["days"],
                    "start": str(d.get("start", "10:00")), "end": str(d.get("end", "18:00"))}
        except Exception:
            pass
    return dict(_DEFAULT_BUSINESS_HOURS)


async def set_business_hours(days: list, start: str, end: str) -> dict:
    days = sorted({int(x) for x in days if 0 <= int(x) <= 6})
    if not days:
        raise ValueError("select_at_least_one_day")
    if not re.match(r"^\d{2}:\d{2}$", start or "") or not re.match(r"^\d{2}:\d{2}$", end or ""):
        raise ValueError("bad_time_format")
    if start >= end:
        raise ValueError("start_must_be_before_end")
    cfg = {"days": days, "start": start, "end": end}
    await set_ops_setting("support_business_hours", json.dumps(cfg))
    return cfg


def _now_ist() -> datetime:
    from datetime import timezone
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


async def is_within_business_hours() -> bool:
    cfg = await get_business_hours()
    now = _now_ist()
    if now.weekday() not in cfg["days"]:
        return False
    return cfg["start"] <= now.strftime("%H:%M") < cfg["end"]


# ── Support-rep duty roster ───────────────────────────────────────────────────
async def add_support_rep(staff_id: int, start_date: str, end_date: str,
                          created_by: Optional[int] = None) -> int:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date or "") or not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date or ""):
        raise ValueError("bad_date_format")
    if end_date < start_date:
        raise ValueError("end_before_start")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_support_reps (staff_id, start_date, end_date, created_by) VALUES (?,?,?,?)",
            (staff_id, start_date, end_date, created_by))
        await conn.commit()
        return cur.lastrowid


async def remove_support_rep(rep_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("DELETE FROM nidaan_support_reps WHERE rep_id=?", (rep_id,))
        await conn.commit()
        return cur.rowcount > 0


async def list_support_reps() -> list[dict]:
    """Roster rows with staff name + an on_duty flag (today within range, IST)."""
    today = _now_ist().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await conn.execute(
            """SELECT r.rep_id, r.staff_id, r.start_date, r.end_date, r.created_at,
                      s.name AS staff_name, s.role AS staff_role
               FROM nidaan_support_reps r
               LEFT JOIN nidaan_staff s ON s.staff_id = r.staff_id
               ORDER BY r.end_date DESC, r.start_date DESC""")).fetchall()]
    for r in rows:
        r["on_duty"] = (r["start_date"] <= today <= r["end_date"])
    return rows


async def on_duty_rep_ids() -> list[int]:
    """staff_ids on support duty right now (today within range, IST, active staff)."""
    today = _now_ist().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT DISTINCT r.staff_id FROM nidaan_support_reps r
               JOIN nidaan_staff s ON s.staff_id = r.staff_id
               WHERE r.start_date <= ? AND r.end_date >= ?
                 AND s.status='active' AND s.deleted_at IS NULL""",
            (today, today))).fetchall()
        return [r["staff_id"] for r in rows]


def create_pay_link_token(claim_id: int, account_id: int, hours: int = 72) -> str:
    """Short-lived, claim-bound token for the WhatsApp one-tap pay link.
    Purpose-scoped (typ='nidaan_paylink') so it can ONLY unlock paying this one
    claim — it is NOT a session token and grants no dashboard access by itself."""
    payload = {
        "typ": "nidaan_paylink",
        "sub": str(account_id),
        "cid": int(claim_id),
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(hours=hours)).timestamp()),
    }
    return _jwt_lib.encode(payload, _nidaan_secret(), algorithm="HS256")


def verify_pay_link_token(token: str, claim_id: int) -> Optional[dict]:
    """Verify a one-tap pay-link token AND that it is bound to claim_id.
    Returns {account_id, claim_id} or None."""
    try:
        payload = _jwt_lib.decode(
            token, _nidaan_secret(), algorithms=["HS256"],
            options={"verify_sub": False})
        if payload.get("typ") != "nidaan_paylink":
            return None
        if int(payload.get("cid", -1)) != int(claim_id):
            return None
        return {"account_id": int(payload["sub"]), "claim_id": int(payload["cid"])}
    except Exception as e:
        logger.debug("Nidaan pay-link token verify failed: %s", e)
        return None


# =============================================================================
#  REVIEW REQUESTS (₹499 per-claim, no subscription needed)
# =============================================================================

async def create_review_request(
    advisor_name: str,
    advisor_phone: str,
    advisor_email: str,
    insured_name: str,
    claim_type: str,
    insurer_name: str = "",
    disputed_amount: Optional[int] = None,
    notes: str = "",
    account_id: Optional[int] = None,
    intermediary_code: str = "",
    intermediary_name: str = "",
) -> int:
    """Save a ₹499 review request. Returns purchase_id.
    If account_id is provided, links the purchase so that account gets dashboard access.
    intermediary_code/intermediary_name: as printed on the policy."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_per_claim_purchase
               (advisor_name, advisor_phone, advisor_email,
                insured_name, insured_phone, insurer_name,
                claim_type, disputed_amount, brief_description,
                amount_paid, status, account_id,
                intermediary_code, intermediary_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 499, 'pending_payment', ?, ?, ?)""",
            (advisor_name, advisor_phone, advisor_email,
             insured_name, advisor_phone, insurer_name,
             claim_type, disputed_amount, notes, account_id,
             (intermediary_code or "").strip(), (intermediary_name or "").strip()),
        )
        await conn.commit()
        return cur.lastrowid


async def get_review_requests_admin(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Admin: list all ₹499 review requests with full account info."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        base = """
            SELECT p.*,
                   a.owner_name, a.email AS account_email, a.phone AS account_phone,
                   a.firm_name
            FROM nidaan_per_claim_purchase p
            LEFT JOIN nidaan_accounts a ON a.account_id = p.account_id
        """
        if status:
            cur = await conn.execute(
                base + " WHERE p.status=? ORDER BY p.created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        else:
            cur = await conn.execute(
                base + " ORDER BY p.created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(r) for r in await cur.fetchall()]


REVIEW_STATUSES = (
    "pending_payment", "paid", "in_review", "review_completed", "completed", "cancelled"
)


async def update_review_request_status(
    purchase_id: int,
    new_status: str,
    note: str = "",
    findings_note: Optional[str] = None,
) -> bool:
    """Staff/Admin: update status of a ₹499 review request.
    When transitioning to review_completed, findings_note is required.
    """
    if new_status not in REVIEW_STATUSES:
        raise ValueError(f"Invalid review status: {new_status}")
    if new_status == "review_completed" and not (note or findings_note):
        raise ValueError("findings_note is required when marking review as completed")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT purchase_id FROM nidaan_per_claim_purchase WHERE purchase_id=?",
            (purchase_id,),
        )
        if not await cur.fetchone():
            return False
        now = datetime.utcnow().isoformat()
        fn = findings_note or note  # fall back to note if findings_note not explicitly passed
        if new_status == "review_completed":
            await conn.execute(
                "UPDATE nidaan_per_claim_purchase "
                "SET status=?, findings_note=?, review_note=?, reviewed_at=? WHERE purchase_id=?",
                (new_status, fn, note, now, purchase_id),
            )
        elif note:
            await conn.execute(
                "UPDATE nidaan_per_claim_purchase "
                "SET status=?, review_note=?, reviewed_at=? WHERE purchase_id=?",
                (new_status, note, now, purchase_id),
            )
        else:
            await conn.execute(
                "UPDATE nidaan_per_claim_purchase "
                "SET status=?, reviewed_at=? WHERE purchase_id=?",
                (new_status, now, purchase_id),
            )
        await conn.commit()
    return True


# =============================================================================
#  ADMIN QUERIES
# =============================================================================

async def get_all_accounts_admin(limit: int = 200, offset: int = 0) -> list[dict]:
    """Admin: list all Nidaan accounts, classified by account_type with plan caps + usage.
      account_type: 'subscriber' (active sub) | 'per_claim' (paid ₹499, no sub) | 'lead'.
    Adds claims_used / claims_cap (None = unlimited) for the usage bar, disputed_cap, and
    per-claim balance. Caps come from the super-admin-editable plans config."""
    cfg = await get_plans_config()
    window_floor = (date.today() - timedelta(days=30)).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT a.*, s.plan, s.status AS sub_status, s.current_period_end,
                      q.claims_this_window, q.current_window_start,
                      rst.name AS ref_staff_name, rbr.name AS ref_branch_name,
                      (SELECT COUNT(*) FROM nidaan_per_claim_purchase p
                        WHERE p.account_id = a.account_id AND p.status = 'paid') AS per_claim_total,
                      (SELECT COUNT(*) FROM nidaan_per_claim_purchase p
                        WHERE p.account_id = a.account_id AND p.status = 'paid'
                          AND p.linked_claim_id IS NULL) AS per_claim_balance,
                      (SELECT COUNT(*) FROM nidaan_claims c
                        WHERE c.account_id = a.account_id AND c.payment_status = 'paid')
                        AS direct_paid_reviews,
                      (SELECT COUNT(*) FROM nidaan_payment_links pl
                        WHERE pl.account_id = a.account_id AND pl.status != 'paid')
                        AS unpaid_links
               FROM nidaan_accounts a
               LEFT JOIN nidaan_subscriptions s ON s.account_id = a.account_id
                   AND s.status = 'active'
               LEFT JOIN nidaan_plan_quota q ON q.account_id = a.account_id
               LEFT JOIN nidaan_staff rst ON UPPER(rst.referral_code)=UPPER(a.branch_code)
                   AND COALESCE(a.branch_code,'')<>''
               LEFT JOIN nidaan_branches rbr ON UPPER(rbr.branch_code)=UPPER(a.branch_code)
                   AND COALESCE(a.branch_code,'')<>''
               ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        plan = r.get("plan")
        if plan:
            r["account_type"] = "subscriber"
            pc = cfg.get(plan, {}) if cfg else {}
            r["claims_cap"] = pc.get("claims_per_month")   # None = unlimited
            r["disputed_cap"] = pc.get("disputed_cap")
            used = r.get("claims_this_window") or 0
            ws = r.get("current_window_start")
            if not ws or str(ws) < window_floor:
                used = 0                                    # window rolled over → resets on next claim
            r["claims_used"] = used
        else:
            # "Paid one-time" = a bought review CREDIT (per_claim_purchase) OR a claim
            # whose ₹499 review fee was paid directly (advisor-lead funnel — no purchase
            # row is created there). Without the second test, a customer who paid to
            # unlock a specific claim's review was wrongly shown as an unpaid 'lead'.
            _paid_reviews = (r.get("per_claim_total") or 0) + (r.get("direct_paid_reviews") or 0)
            r["account_type"] = "per_claim" if _paid_reviews > 0 else "lead"
            r["claims_cap"] = None
            r["disputed_cap"] = None
            r["claims_used"] = 0
        # Payment-status flag for the ops accounts list:
        #   paid       — has an active sub / paid review
        #   attempted  — a payment link was sent but not completed (red-flag)
        #   halted     — a recurring subscription charge failed (retries exhausted)
        #   none       — a lead with no payment attempt
        if r["account_type"] in ("subscriber", "per_claim"):
            r["pay_status"] = "paid"
        elif str(r.get("sub_status") or "") == "halted":
            r["pay_status"] = "halted"
        elif (r.get("unpaid_links") or 0) > 0:
            r["pay_status"] = "attempted"
        else:
            r["pay_status"] = "none"
        # Who referred this account? The code in branch_code is either a staff personal
        # code (SP-xxxxxx) or a real city branch — resolve to a human name so the ops
        # accounts list can show "Avi (SP-…)" / "BIAORA BRANCH (BIAORA-01)", not a bare code.
        if r.get("ref_staff_name"):
            r["ref_kind"] = "staff"
            r["ref_name"] = r["ref_staff_name"]
        elif r.get("branch_code") and r.get("ref_branch_name") is not None:
            r["ref_kind"] = "branch"
            r["ref_name"] = r["ref_branch_name"] or ""
        else:
            r["ref_kind"] = ""      # no code, or a legacy/unknown code
            r["ref_name"] = ""
    return rows


async def get_overview_widgets(staff_id: int, staff_role: str,
                                staff_email: str = "") -> dict:
    """Aggregated data for ops portal Overview widgets.
    Scope rules:
      - super_admin / sub_super_admin: everything
      - team_member: only claims/tasks/follow-ups assigned to them
      - refunds_needs_action surfaces ONLY to the platform owner.
    """
    is_admin = staff_role in ("super_admin", "sub_super_admin")
    is_owner = (staff_email or "").lower() == "dushyant@nidaanpartner.com"
    today_iso = datetime.utcnow().strftime("%Y-%m-%d")
    week_end = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Task pipeline — counts by status_slug.
        if is_admin:
            cur = await conn.execute(
                "SELECT t.status_slug, COUNT(*) AS cnt FROM nidaan_tasks t "
                "WHERE t.status_slug NOT IN ('completed','cancelled') "
                "GROUP BY t.status_slug ORDER BY cnt DESC")
        else:
            cur = await conn.execute(
                "SELECT t.status_slug, COUNT(*) AS cnt FROM nidaan_tasks t "
                "WHERE t.assigned_to_staff_id = ? "
                "AND t.status_slug NOT IN ('completed','cancelled') "
                "GROUP BY t.status_slug ORDER BY cnt DESC", (staff_id,))
        task_pipeline = [dict(r) for r in await cur.fetchall()]

        # 2. Pending reviews (₹499 ones awaiting findings, paid).
        cur = await conn.execute(
            "SELECT p.purchase_id, p.account_id, p.claim_type, p.insurer_name, "
            "       p.disputed_amount, p.amount_paid, p.status, p.created_at, "
            "       a.owner_name, a.email AS account_email "
            "FROM nidaan_per_claim_purchase p "
            "LEFT JOIN nidaan_accounts a ON a.account_id = p.account_id "
            "WHERE p.status IN ('paid','submitted','in_review') "
            "ORDER BY p.created_at ASC LIMIT 50")
        pending_reviews = [dict(r) for r in await cur.fetchall()]

        # 3. Follow-ups due this week (own for non-admin; everyone for admin).
        if is_admin:
            cur = await conn.execute(
                "SELECT f.followup_id, f.claim_id, f.staff_id, f.due_date, f.note, "
                "       c.insured_name, c.status AS claim_status, s.name AS staff_name "
                "FROM nidaan_followups f "
                "LEFT JOIN nidaan_claims c ON c.claim_id = f.claim_id "
                "LEFT JOIN nidaan_staff s ON s.staff_id = f.staff_id "
                "WHERE f.status='pending' AND f.due_date <= ? "
                "ORDER BY f.due_date ASC LIMIT 50", (week_end,))
        else:
            cur = await conn.execute(
                "SELECT f.followup_id, f.claim_id, f.staff_id, f.due_date, f.note, "
                "       c.insured_name, c.status AS claim_status, s.name AS staff_name "
                "FROM nidaan_followups f "
                "LEFT JOIN nidaan_claims c ON c.claim_id = f.claim_id "
                "LEFT JOIN nidaan_staff s ON s.staff_id = f.staff_id "
                "WHERE f.status='pending' AND f.due_date <= ? AND f.staff_id = ? "
                "ORDER BY f.due_date ASC LIMIT 50", (week_end, staff_id))
        followups = [dict(r) for r in await cur.fetchall()]
        for f in followups:
            f["overdue"] = bool(f.get("due_date") and f["due_date"] < today_iso)

        # 4. Overdue claims (any task on claim past SLA).
        if is_admin:
            cur = await conn.execute(
                "SELECT DISTINCT c.claim_id, c.insured_name, c.status, "
                "       c.insurer_name, c.disputed_amount, c.created_at, "
                "       c.assigned_to_staff_id, s.name AS staff_name "
                "FROM nidaan_claims c "
                "LEFT JOIN nidaan_tasks t ON t.claim_id = c.claim_id "
                "LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id "
                "WHERE c.status NOT IN ('resolved_won','resolved_lost','closed','withdrawn') "
                "  AND t.sla_due_at IS NOT NULL "
                "  AND t.sla_due_at < datetime('now') "
                "  AND t.status_slug NOT IN ('completed','cancelled') "
                "ORDER BY c.created_at DESC LIMIT 30")
        else:
            cur = await conn.execute(
                "SELECT DISTINCT c.claim_id, c.insured_name, c.status, "
                "       c.insurer_name, c.disputed_amount, c.created_at, "
                "       c.assigned_to_staff_id, s.name AS staff_name "
                "FROM nidaan_claims c "
                "INNER JOIN nidaan_tasks t ON t.claim_id = c.claim_id "
                "LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id "
                "WHERE c.status NOT IN ('resolved_won','resolved_lost','closed','withdrawn') "
                "  AND t.sla_due_at IS NOT NULL "
                "  AND t.sla_due_at < datetime('now') "
                "  AND t.status_slug NOT IN ('completed','cancelled') "
                "  AND (c.assigned_to_staff_id = ? OR t.assigned_to_staff_id = ?) "
                "ORDER BY c.created_at DESC LIMIT 30", (staff_id, staff_id))
        overdue_claims = [dict(r) for r in await cur.fetchall()]

        # 5. Refunds needing action — owner only (revenue/refunds are scoped to owner).
        refunds_needs_action = 0
        if is_owner:
            try:
                eligible = await find_eligible_unrefunded_cancellations(days=30)
                refunds_needs_action = len(eligible)
            except Exception:
                refunds_needs_action = 0

        # 6. Quick top-line numbers.
        # NOTE: only count claims whose account still exists, so these match the
        # All-Claims table (which inner-joins nidaan_accounts). Orphaned claims
        # left by a deleted account must not inflate the count.
        _live = ("EXISTS(SELECT 1 FROM nidaan_accounts a "
                 "WHERE a.account_id=nidaan_claims.account_id)")
        # Scope claim metrics by role: a team_member sees ONLY their assigned/involved claims
        # (same rule as get_claims_ops), never the whole office's numbers.
        if is_admin:
            _cscope, _csp = _live, []
        else:
            _cscope = (_live + " AND (nidaan_claims.assigned_to_staff_id=? OR EXISTS("
                       "SELECT 1 FROM nidaan_claim_assignees ca "
                       "WHERE ca.claim_id=nidaan_claims.claim_id AND ca.staff_id=?))")
            _csp = [staff_id, staff_id]
        total_claims = (await (await conn.execute(
            f"SELECT COUNT(*) FROM nidaan_claims WHERE {_cscope}", _csp)).fetchone())[0]
        open_claims = (await (await conn.execute(
            f"SELECT COUNT(*) FROM nidaan_claims WHERE {_cscope} AND status NOT IN "
            "('resolved_won','resolved_lost','closed','withdrawn')", _csp)).fetchone())[0]
        # Active subscriptions is an office-wide business metric → admins only.
        active_subs = (await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_subscriptions WHERE status='active'")).fetchone())[0] if is_admin else 0

        # 7. Claims by status — scoped to the viewer's claims (all for admins).
        cur = await conn.execute(
            f"SELECT status, COUNT(*) AS cnt FROM nidaan_claims WHERE {_cscope} "
            "GROUP BY status ORDER BY cnt DESC", _csp)
        claims_by_status = [dict(r) for r in await cur.fetchall()]

        # 8-10 are admin-only views: top accounts, workload, recent comments.
        top_accounts = []
        workload = []
        recent_comments = []

        if is_admin:
            # 8. Top accounts needing attention — ranked by overdue tasks, then
            # open tasks, then open claims. Only accounts with open work shown.
            cur = await conn.execute(
                "SELECT a.account_id, a.owner_name, a.email, "
                "       COUNT(DISTINCT CASE WHEN c.status NOT IN "
                "         ('resolved_won','resolved_lost','closed','withdrawn') "
                "         THEN c.claim_id END) AS open_claims, "
                "       COUNT(DISTINCT CASE WHEN t.status_slug NOT IN "
                "         ('completed','cancelled') THEN t.task_id END) AS open_tasks, "
                "       COUNT(DISTINCT CASE WHEN t.sla_due_at IS NOT NULL "
                "         AND t.sla_due_at < datetime('now') "
                "         AND t.status_slug NOT IN ('completed','cancelled') "
                "         THEN t.task_id END) AS overdue_tasks "
                "FROM nidaan_accounts a "
                "LEFT JOIN nidaan_claims c ON c.account_id = a.account_id "
                "LEFT JOIN nidaan_tasks t ON t.claim_id = c.claim_id "
                "GROUP BY a.account_id "
                "HAVING open_claims > 0 OR open_tasks > 0 "
                "ORDER BY overdue_tasks DESC, open_tasks DESC, open_claims DESC "
                "LIMIT 10")
            top_accounts = [dict(r) for r in await cur.fetchall()]

            # 9. Workload by active staff member — counts BOTH claim-tasks
            #    (nidaan_tasks) and office quick-tasks (nidaan_quick_tasks) so
            #    quick-tasks assigned to a staffer surface here too.
            cur = await conn.execute(
                "SELECT s.staff_id, s.name, s.role, "
                # claim-tasks open + overdue
                "  (SELECT COUNT(*) FROM nidaan_tasks t "
                "     WHERE t.assigned_to_staff_id = s.staff_id "
                "       AND t.status_slug NOT IN ('completed','cancelled')) "
                "  + (SELECT COUNT(*) FROM nidaan_quick_tasks q "
                "     WHERE q.assigned_to_staff_id = s.staff_id "
                "       AND q.deleted_at IS NULL "
                "       AND q.status NOT IN ('done','cancelled')) AS open_tasks, "
                "  (SELECT COUNT(*) FROM nidaan_tasks t "
                "     WHERE t.assigned_to_staff_id = s.staff_id "
                "       AND t.sla_due_at IS NOT NULL "
                "       AND t.sla_due_at < datetime('now') "
                "       AND t.status_slug NOT IN ('completed','cancelled')) "
                "  + (SELECT COUNT(*) FROM nidaan_quick_tasks q "
                "     WHERE q.assigned_to_staff_id = s.staff_id "
                "       AND q.deleted_at IS NULL "
                "       AND q.due_date IS NOT NULL "
                "       AND q.due_date < datetime('now') "
                "       AND q.status NOT IN ('done','cancelled')) AS overdue_tasks "
                "FROM nidaan_staff s "
                "WHERE s.status = 'active' "
                "GROUP BY s.staff_id "
                "ORDER BY open_tasks DESC")
            workload = [dict(r) for r in await cur.fetchall()]

            # 10. Recent comments — last 10 across task notes + claim notes.
            # Wrap UNION in a subquery so ORDER BY resolves against the outer column set.
            cur = await conn.execute(
                "SELECT * FROM ("
                "  SELECT 'task' AS source, tn.note_id AS id, tn.task_id, "
                "         t.claim_id, t.title AS task_title, "
                "         c.insured_name, tn.note, tn.created_at, "
                "         s.name AS staff_name, s.role AS staff_role "
                "  FROM nidaan_task_notes tn "
                "  LEFT JOIN nidaan_staff s ON s.staff_id = tn.staff_id "
                "  LEFT JOIN nidaan_tasks t ON t.task_id = tn.task_id "
                "  LEFT JOIN nidaan_claims c ON c.claim_id = t.claim_id "
                "  UNION ALL "
                "  SELECT 'claim' AS source, cn.note_id AS id, NULL AS task_id, "
                "         cn.claim_id, NULL AS task_title, "
                "         c.insured_name, cn.note, cn.created_at, "
                "         s.name AS staff_name, s.role AS staff_role "
                "  FROM nidaan_claim_notes cn "
                "  LEFT JOIN nidaan_staff s ON s.staff_id = cn.staff_id "
                "  LEFT JOIN nidaan_claims c ON c.claim_id = cn.claim_id"
                ") ORDER BY created_at DESC LIMIT 10")
            recent_comments = [dict(r) for r in await cur.fetchall()]

    return {
        "task_pipeline": task_pipeline,
        "pending_reviews": pending_reviews,
        "followups_due": followups,
        "overdue_claims": overdue_claims,
        "refunds_needs_action": refunds_needs_action,
        "claims_by_status": claims_by_status,
        "top_accounts": top_accounts,
        "workload": workload,
        "recent_comments": recent_comments,
        "totals": {
            "total_claims": total_claims,
            "open_claims": open_claims,
            "active_subscriptions": active_subs,
        },
    }


async def get_account_birds_eye(account_id: int) -> Optional[dict]:
    """Bird's-eye snapshot for an account drawer:
    profile + subscription history + per-claim purchases + claims (with open task
    counts) + recent activity timeline (status changes, payments, comments).
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        acct = await (await conn.execute(
            "SELECT * FROM nidaan_accounts WHERE account_id=?",
            (account_id,))).fetchone()
        if not acct:
            return None
        acct = dict(acct)

        subs = [dict(r) for r in await (await conn.execute(
            "SELECT sub_id, plan, billing_cycle, amount_paid, status, "
            "       started_at, current_period_end, cancelled_at, "
            "       razorpay_subscription_id, razorpay_payment_id "
            "FROM nidaan_subscriptions WHERE account_id=? ORDER BY started_at DESC",
            (account_id,))).fetchall()]

        purchases = [dict(r) for r in await (await conn.execute(
            "SELECT purchase_id, claim_type, insurer_name, disputed_amount, "
            "       amount_paid, status, created_at, reviewed_at, brief_description "
            "FROM nidaan_per_claim_purchase WHERE account_id=? ORDER BY created_at DESC",
            (account_id,))).fetchall()]

        refunds = [dict(r) for r in await (await conn.execute(
            "SELECT refund_id, sub_id, amount, status, reason, "
            "       razorpay_refund_id, requested_at, processed_at "
            "FROM nidaan_refunds WHERE account_id=? ORDER BY requested_at DESC",
            (account_id,))).fetchall()]

        claims = [dict(r) for r in await (await conn.execute(
            "SELECT c.claim_id, c.insured_name, c.insurer_name, c.claim_type, "
            "       c.disputed_amount, c.status, c.created_at, c.assigned_to_staff_id, "
            "       s.name AS assigned_staff_name, "
            "       (SELECT COUNT(*) FROM nidaan_tasks t "
            "        WHERE t.claim_id = c.claim_id "
            "          AND t.status_slug NOT IN ('completed','cancelled')) AS open_tasks "
            "FROM nidaan_claims c "
            "LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id "
            "WHERE c.account_id=? ORDER BY c.created_at DESC",
            (account_id,))).fetchall()]

        # Aggregate open tasks across all the account's claims.
        open_tasks = [dict(r) for r in await (await conn.execute(
            "SELECT t.task_id, t.claim_id, t.title, t.status_slug, t.priority, "
            "       t.sla_due_at, t.assigned_to_staff_id, s.name AS assignee_name "
            "FROM nidaan_tasks t "
            "INNER JOIN nidaan_claims c ON c.claim_id = t.claim_id "
            "LEFT JOIN nidaan_staff s ON s.staff_id = t.assigned_to_staff_id "
            "WHERE c.account_id=? AND t.status_slug NOT IN ('completed','cancelled') "
            "ORDER BY (t.sla_due_at IS NULL), t.sla_due_at ASC LIMIT 50",
            (account_id,))).fetchall()]

        # Last-activity timeline: claim status changes + claim notes + payments.
        timeline = []
        for r in await (await conn.execute(
            "SELECT l.changed_at AS ts, 'status' AS kind, "
            "       l.from_status, l.to_status, c.claim_id, c.insured_name, "
            "       CASE WHEN l.changed_by_type='staff' THEN s.name "
            "            ELSE l.changed_by_type END AS staff_name, "
            "       l.note AS detail "
            "FROM nidaan_claim_status_log l "
            "INNER JOIN nidaan_claims c ON c.claim_id = l.claim_id "
            "LEFT JOIN nidaan_staff s ON s.staff_id = l.changed_by_id "
            "WHERE c.account_id=? ORDER BY l.changed_at DESC LIMIT 30",
            (account_id,))).fetchall():
            timeline.append(dict(r))
        for r in await (await conn.execute(
            "SELECT n.created_at AS ts, 'note' AS kind, "
            "       NULL AS from_status, NULL AS to_status, "
            "       c.claim_id, c.insured_name, s.name AS staff_name, n.note AS detail "
            "FROM nidaan_claim_notes n "
            "INNER JOIN nidaan_claims c ON c.claim_id = n.claim_id "
            "LEFT JOIN nidaan_staff s ON s.staff_id = n.staff_id "
            "WHERE c.account_id=? ORDER BY n.created_at DESC LIMIT 30",
            (account_id,))).fetchall():
            timeline.append(dict(r))
        for r in await (await conn.execute(
            "SELECT s.started_at AS ts, 'payment' AS kind, "
            "       NULL AS from_status, s.status AS to_status, "
            "       NULL AS claim_id, NULL AS insured_name, "
            "       NULL AS staff_name, "
            "       (s.plan || ' · ₹' || s.amount_paid) AS detail "
            "FROM nidaan_subscriptions s WHERE s.account_id=?",
            (account_id,))).fetchall():
            timeline.append(dict(r))
        timeline.sort(key=lambda x: x.get("ts") or "", reverse=True)
        timeline = timeline[:30]

    # Bird's-eye summary metrics
    summary = {
        "total_claims": len(claims),
        "open_claims": sum(1 for c in claims if c["status"] not in
                            ("resolved_won","resolved_lost","closed","withdrawn")),
        "won_claims": sum(1 for c in claims if c["status"] == "resolved_won"),
        "lost_claims": sum(1 for c in claims if c["status"] == "resolved_lost"),
        "open_tasks": len(open_tasks),
        "current_sub": subs[0] if subs and subs[0]["status"] == "active" else None,
        "per_claim_balance": sum(1 for p in purchases
                                  if p["status"] in ("paid","submitted","in_review")),
        "lifetime_paid": sum(int(s.get("amount_paid") or 0) for s in subs)
                          + sum(int(p.get("amount_paid") or 0) for p in purchases),
        "lifetime_refunded": sum(int(r.get("amount") or 0) for r in refunds
                                  if r.get("status") == "processed"),
    }

    return {
        "account": acct,
        "summary": summary,
        "subscriptions": subs,
        "per_claim_purchases": purchases,
        "refunds": refunds,
        "claims": claims,
        "open_tasks": open_tasks,
        "timeline": timeline,
    }


async def get_office_analytics(days: int = 30) -> dict:
    """30-day operational analytics for SA/admin.
    Returns: closure rate, win rate, avg cycle time, daily new claims,
    by-stage counts, top closed_reason values, top assignees by closures.
    All queries scoped to the trailing `days` window where applicable.
    """
    days = max(1, min(int(days), 365))
    window_clause = f"datetime('now', '-{days} days')"

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Top-line: new claims, closed claims, win/loss, closure rate
        new_claims = (await (await conn.execute(
            f"SELECT COUNT(*) FROM nidaan_claims WHERE created_at >= {window_clause}"
        )).fetchone())[0]
        closed_total = (await (await conn.execute(
            f"SELECT COUNT(*) FROM nidaan_claims WHERE closed_at >= {window_clause} "
            "AND status IN ('resolved_won','resolved_lost','closed','withdrawn')"
        )).fetchone())[0]
        won = (await (await conn.execute(
            f"SELECT COUNT(*) FROM nidaan_claims WHERE closed_at >= {window_clause} "
            "AND status='resolved_won'"
        )).fetchone())[0]
        lost = (await (await conn.execute(
            f"SELECT COUNT(*) FROM nidaan_claims WHERE closed_at >= {window_clause} "
            "AND status='resolved_lost'"
        )).fetchone())[0]

        # 2. Average cycle time (days) for closed claims in window
        row = await (await conn.execute(
            f"SELECT AVG((julianday(closed_at) - julianday(created_at))) AS d "
            f"FROM nidaan_claims WHERE closed_at >= {window_clause} "
            "AND closed_at IS NOT NULL"
        )).fetchone()
        avg_cycle_days = round(float(row["d"]), 1) if row and row["d"] is not None else None

        # 3. Daily new claims trend (last `days` buckets, oldest → newest)
        cur = await conn.execute(
            f"SELECT date(created_at) AS d, COUNT(*) AS cnt FROM nidaan_claims "
            f"WHERE created_at >= {window_clause} "
            "GROUP BY date(created_at) ORDER BY d ASC")
        new_claims_by_day = [dict(r) for r in await cur.fetchall()]

        # 4. By-stage current snapshot (open claims only)
        cur = await conn.execute(
            "SELECT stage, COUNT(*) AS cnt FROM nidaan_claims "
            "WHERE status NOT IN ('resolved_won','resolved_lost','closed','withdrawn') "
            "GROUP BY stage ORDER BY cnt DESC")
        by_stage_open = [dict(r) for r in await cur.fetchall()]

        # 5. Top closed_reason values (window)
        cur = await conn.execute(
            f"SELECT closed_reason, COUNT(*) AS cnt FROM nidaan_claims "
            f"WHERE closed_at >= {window_clause} AND closed_reason IS NOT NULL "
            "AND closed_reason != '' GROUP BY closed_reason ORDER BY cnt DESC LIMIT 6")
        top_reasons = [dict(r) for r in await cur.fetchall()]

        # 6. Top assignees by claims closed in window
        cur = await conn.execute(
            f"SELECT s.staff_id, s.name, "
            "       COUNT(c.claim_id) AS closed, "
            "       SUM(CASE WHEN c.status='resolved_won' THEN 1 ELSE 0 END) AS won "
            "FROM nidaan_claims c "
            "INNER JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id "
            f"WHERE c.closed_at >= {window_clause} "
            "GROUP BY s.staff_id ORDER BY closed DESC LIMIT 6")
        top_assignees = [dict(r) for r in await cur.fetchall()]

    decided = won + lost  # ignore withdrawn/closed for win-rate denominator
    return {
        "window_days": days,
        "totals": {
            "new_claims": new_claims,
            "closed_total": closed_total,
            "won": won,
            "lost": lost,
            "closure_rate_pct": (round(closed_total / new_claims * 100, 1)
                                  if new_claims else None),
            "win_rate_pct": (round(won / decided * 100, 1) if decided else None),
            "avg_cycle_days": avg_cycle_days,
        },
        "new_claims_by_day": new_claims_by_day,
        "by_stage_open": by_stage_open,
        "top_reasons": top_reasons,
        "top_assignees": top_assignees,
    }


async def get_internal_escalations() -> dict:
    """Pending dual-approval queue + claims sitting in escalation stages.
    For each pending approval, reports whether admin / SA has acted so SA
    knows where it's stuck.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Pending dual approvals (Admin + SA both must approve).
        cur = await conn.execute(
            "SELECT a.approval_id, a.task_id, a.target_status_slug, "
            "       a.requested_by, a.admin_staff_id, a.admin_approved_at, a.admin_note, "
            "       a.sa_staff_id, a.sa_approved_at, a.sa_note, "
            "       a.created_at, "
            "       t.title AS task_title, t.claim_id, t.stage, "
            "       c.insured_name, "
            "       rs.name AS requested_by_name "
            "FROM nidaan_task_approvals a "
            "LEFT JOIN nidaan_tasks t ON t.task_id = a.task_id "
            "LEFT JOIN nidaan_claims c ON c.claim_id = t.claim_id "
            "LEFT JOIN nidaan_staff rs ON rs.staff_id = a.requested_by "
            "WHERE a.final_status = 'pending' "
            "ORDER BY a.created_at DESC LIMIT 30")
        pending = []
        for r in await cur.fetchall():
            d = dict(r)
            d["needs_admin"] = (d["admin_approved_at"] is None)
            d["needs_sa"] = (d["sa_approved_at"] is None)
            pending.append(d)

        # Claims sitting in escalation/ombudsman stages — visibility for SA.
        cur = await conn.execute(
            "SELECT c.claim_id, c.insured_name, c.insurer_name, c.stage, "
            "       c.status, c.disputed_amount, c.created_at, "
            "       s.name AS assigned_staff_name "
            "FROM nidaan_claims c "
            "LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id "
            "WHERE c.stage IN ('ombudsman','escalation') "
            "AND c.status NOT IN ('resolved_won','resolved_lost','closed','withdrawn') "
            "ORDER BY c.created_at DESC LIMIT 30")
        in_escalation = [dict(r) for r in await cur.fetchall()]

    return {
        "pending_approvals": pending,
        "in_escalation_stages": in_escalation,
    }


# =============================================================================
#  QUICK TASKS — lightweight personal/team to-dos (Phase 5+)
# =============================================================================

QUICK_TASK_PRIORITIES = {
    "low":    {"label":"Low",    "channels":[],                  "desc":"Whenever you can get to it — dashboard only, no notification."},
    "normal": {"label":"Normal", "channels":["email"],           "desc":"Standard work item — dashboard + email on assignment."},
    "high":   {"label":"High",   "channels":["email","wa"],      "desc":"Please prioritize — dashboard + email + WhatsApp nudge."},
    "urgent": {"label":"Urgent", "channels":["email","wa","top"],"desc":"Time-sensitive — all channels + pinned to top of assignee's Overview."},
}
QUICK_TASK_STATUSES = ("open", "in_progress", "done", "cancelled")


async def create_quick_task(*, title: str, created_by_staff_id: int,
                             assigned_to_staff_id: Optional[int] = None,
                             priority: str = "normal", claim_id: Optional[int] = None,
                             due_date: Optional[str] = None, description: str = "",
                             requires_approval: bool = False,
                             task_type: str = "assignment",
                             category_code: Optional[str] = None,
                             approver_staff_id: Optional[int] = None,
                             complainant_name: Optional[str] = None,
                             complainant_phone: Optional[str] = None,
                             source: Optional[str] = None) -> int:
    if priority not in QUICK_TASK_PRIORITIES:
        priority = "normal"
    if task_type not in ("assignment", "request"):
        task_type = "assignment"
    category_code = (category_code or "").strip().upper() or None
    approval_status = "pending" if requires_approval else "none"
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_quick_tasks "
            "(title, description, assigned_to_staff_id, created_by_staff_id, "
            " priority, claim_id, due_date, requires_approval, approval_status, task_type, "
            " category_code, approver_staff_id, complainant_name, complainant_phone) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title.strip(), description.strip(), assigned_to_staff_id,
             created_by_staff_id, priority, claim_id, due_date,
             1 if requires_approval else 0, approval_status, task_type,
             category_code, approver_staff_id,
             (complainant_name or "").strip() or None,
             (complainant_phone or "").strip() or None))
        qid = cur.lastrowid
        await _log_quick_task(conn, qid, "created",
                              to_value=str(assigned_to_staff_id) if assigned_to_staff_id else None,
                              changed_by=created_by_staff_id,
                              note="requires approval" if requires_approval else "", source=source)
        await conn.commit()
        return qid


# ── Task categories (admin-editable tags) ────────────────────────────────────
async def list_task_categories(include_inactive: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        clause = "" if include_inactive else " WHERE active=1"
        cur = await conn.execute(
            "SELECT category_id, code, label, color, sort_order, active, requires_complainant "
            "FROM nidaan_task_categories" + clause +
            " ORDER BY active DESC, sort_order ASC, label ASC")
        return [dict(r) for r in await cur.fetchall()]


async def category_requires_complainant(code: Optional[str]) -> bool:
    """True if the given category demands complainant name + mobile."""
    if not code:
        return False
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT requires_complainant FROM nidaan_task_categories WHERE code=?",
            (code.strip().upper(),))).fetchone()
        return bool(row and row[0])


async def create_task_category(*, code: str, label: str,
                                color: str = "#64748b", sort_order: int = 100) -> int:
    code = (code or "").strip().upper()
    label = (label or "").strip()
    if not code or not label:
        raise ValueError("code and label are required")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_task_categories (code,label,color,sort_order) "
            "VALUES (?,?,?,?)", (code, label, (color or "#64748b").strip(), int(sort_order)))
        await conn.commit()
        return cur.lastrowid


async def update_task_category(category_id: int, *, label: Optional[str] = None,
                                color: Optional[str] = None,
                                sort_order: Optional[int] = None,
                                active: Optional[bool] = None,
                                requires_complainant: Optional[bool] = None) -> bool:
    sets, params = [], []
    if label is not None:      sets.append("label=?");      params.append(label.strip())
    if color is not None:      sets.append("color=?");      params.append(color.strip())
    if sort_order is not None: sets.append("sort_order=?"); params.append(int(sort_order))
    if active is not None:     sets.append("active=?");     params.append(1 if active else 0)
    if requires_complainant is not None:
        sets.append("requires_complainant=?"); params.append(1 if requires_complainant else 0)
    if not sets:
        return False
    params.append(category_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_task_categories SET " + ", ".join(sets) +
            " WHERE category_id=?", params)
        await conn.commit()
    return True


async def deactivate_task_category(category_id: int) -> bool:
    """Soft-remove: hide from pickers/filters but keep the tag on historic tasks."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_task_categories SET active=0 WHERE category_id=?", (category_id,))
        await conn.commit()
    return True


_QT_EDITABLE_FIELDS = ("title", "description", "category_code", "due_date", "priority",
                       "complainant_name", "complainant_phone")


async def update_quick_task_fields(quick_task_id: int, fields: dict,
                                    changed_by: int, source: str = None) -> list[str]:
    """Edit a task's own content (title / description / category / due date /
    priority) — for fixing typos and mistakes after creation. Every change is written
    to the immutable task log. Returns the list of fields actually changed."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur_row = await (await conn.execute(
            "SELECT title, description, category_code, due_date, priority, "
            "       complainant_name, complainant_phone "
            "FROM nidaan_quick_tasks WHERE quick_task_id=?", (quick_task_id,))).fetchone()
        if not cur_row:
            return []
        current = dict(cur_row)
        sets, params, changed = [], [], []
        for k in _QT_EDITABLE_FIELDS:
            if k not in fields or fields[k] is None:
                continue
            new_val = fields[k]
            if k == "priority" and new_val not in QUICK_TASK_PRIORITIES:
                continue
            if k in ("title", "description") and isinstance(new_val, str):
                new_val = new_val.strip()
            if k == "category_code" and isinstance(new_val, str):
                new_val = new_val.strip().upper() or None
            if str(current.get(k) or "") == str(new_val or ""):
                continue  # no-op
            sets.append(f"{k}=?"); params.append(new_val); changed.append(k)
            await _log_quick_task(conn, quick_task_id, "edit",
                                  from_value=str(current.get(k) or "")[:120],
                                  to_value=str(new_val or "")[:120],
                                  changed_by=changed_by, note=k, source=source)
        if not sets:
            return []
        params.append(quick_task_id)
        await conn.execute(
            "UPDATE nidaan_quick_tasks SET " + ", ".join(sets) +
            ", updated_at = CURRENT_TIMESTAMP WHERE quick_task_id=?", params)
        await conn.commit()
        return changed


# ── Multiple attachments per comment ─────────────────────────────────────────
async def add_note_attachments(*, quick_task_id: int, note_id: Optional[int],
                                files: list[dict], uploaded_by: int) -> int:
    """files = [{'stored_name':…, 'original_name':…}, …]. Returns rows inserted."""
    if not files:
        return 0
    async with aiosqlite.connect(DB_PATH) as conn:
        for f in files:
            if not f.get("stored_name"):
                continue
            await conn.execute(
                "INSERT INTO nidaan_quick_task_attachments "
                "(quick_task_id, note_id, stored_name, original_name, uploaded_by) "
                "VALUES (?,?,?,?,?)",
                (quick_task_id, note_id, f["stored_name"], f.get("original_name"), uploaded_by))
        await conn.commit()
    return len(files)


async def list_note_attachments(quick_task_id: int) -> dict:
    """{note_id: [ {attachment_id, stored_name, original_name, uploaded_by, uploaded_at}, … ]}."""
    out: dict = {}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT attachment_id, note_id, stored_name, original_name, uploaded_by, uploaded_at "
            "FROM nidaan_quick_task_attachments "
            "WHERE quick_task_id=? ORDER BY attachment_id ASC", (quick_task_id,))).fetchall()
        for r in rows:
            out.setdefault(r["note_id"], []).append({
                "attachment_id": r["attachment_id"], "stored_name": r["stored_name"],
                "original_name": r["original_name"], "uploaded_by": r["uploaded_by"],
                "uploaded_at": r["uploaded_at"]})
    return out


# Window during which the uploader can delete their own attachment (after that: admin only).
ATTACHMENT_DELETE_WINDOW_SEC = 3600


async def delete_note_attachment(attachment_id: int, staff_id: int, is_admin: bool) -> Optional[dict]:
    """Delete a task-comment attachment. Allowed if the uploader within 1 hour, or an admin any
    time. Returns the deleted row (for disk cleanup) or None if not found. Raises PermissionError
    ('not_owner' | 'too_late') when the current staff may not delete it."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_quick_task_attachments WHERE attachment_id=?",
            (attachment_id,))).fetchone()
        if not row:
            return None
        row = dict(row)
        if not is_admin:
            if row.get("uploaded_by") != staff_id:
                raise PermissionError("not_owner")
            try:
                up = datetime.fromisoformat(str(row["uploaded_at"]).replace(" ", "T"))
                age = (datetime.utcnow() - up).total_seconds()
            except Exception:
                age = 0
            if age > ATTACHMENT_DELETE_WINDOW_SEC:
                raise PermissionError("too_late")
        await conn.execute(
            "DELETE FROM nidaan_quick_task_attachments WHERE attachment_id=?", (attachment_id,))
        # If this file also filled the legacy single-attachment columns on the note, clear them.
        await conn.execute(
            "UPDATE nidaan_quick_task_notes SET attachment_stored_name=NULL, "
            "attachment_original_name=NULL WHERE note_id=? AND attachment_stored_name=?",
            (row.get("note_id"), row.get("stored_name")))
        await conn.commit()
        return row


# ── Task collaboration: watchers / @mention participants / mute ──────────────
async def add_task_watchers(quick_task_id: int, staff_ids: list[int],
                             added_by: int, relation: str = "mentioned") -> list[int]:
    """Add staff as watchers/participants of a task. Returns the staff_ids that were
    NEWLY added (already-present watchers are skipped) so callers can notify only the
    freshly-tagged people."""
    newly: list[int] = []
    if not staff_ids:
        return newly
    async with aiosqlite.connect(DB_PATH) as conn:
        for sid in staff_ids:
            if not sid:
                continue
            cur = await conn.execute(
                "INSERT OR IGNORE INTO nidaan_quick_task_watchers "
                "(quick_task_id, staff_id, relation, added_by_staff_id) VALUES (?,?,?,?)",
                (quick_task_id, sid, relation, added_by))
            if cur.rowcount:
                newly.append(sid)
        await conn.commit()
    return newly


async def list_task_watchers(quick_task_id: int) -> list[dict]:
    """Explicitly-added watchers (mentioned participants) with name/role + mute."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT w.staff_id, w.relation, w.muted, w.added_by_staff_id, w.added_at, "
            "       s.name, s.role "
            "FROM nidaan_quick_task_watchers w "
            "LEFT JOIN nidaan_staff s ON s.staff_id = w.staff_id "
            "WHERE w.quick_task_id = ? ORDER BY w.added_at ASC", (quick_task_id,))).fetchall()
        return [dict(r) for r in rows]


async def set_task_watch_mute(quick_task_id: int, staff_id: int, muted: bool) -> bool:
    """Mute/unmute a task for one staffer. Creates a watcher row (relation='owner')
    if they weren't a mentioned participant — so the assignee/creator can mute too."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO nidaan_quick_task_watchers (quick_task_id, staff_id, relation, muted, added_by_staff_id) "
            "VALUES (?,?,'owner',?,?) "
            "ON CONFLICT(quick_task_id, staff_id) DO UPDATE SET muted=excluded.muted",
            (quick_task_id, staff_id, 1 if muted else 0, staff_id))
        await conn.commit()
    return True


async def is_task_participant(quick_task_id: int, staff_id: int) -> bool:
    """True if the staffer is the creator, assignee, or a watcher of the task."""
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM nidaan_quick_tasks "
            "WHERE quick_task_id=? AND (created_by_staff_id=? OR assigned_to_staff_id=?) "
            "UNION SELECT 1 FROM nidaan_quick_task_watchers "
            "WHERE quick_task_id=? AND staff_id=? LIMIT 1",
            (quick_task_id, staff_id, staff_id, quick_task_id, staff_id))).fetchone()
        return row is not None


async def get_task_participants(quick_task_id: int) -> list[dict]:
    """Everyone involved in a task — creator + assignee + mentioned watchers — unified
    with each person's mute state and contact details. Drives notification fan-out."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        task = await (await conn.execute(
            "SELECT created_by_staff_id, assigned_to_staff_id FROM nidaan_quick_tasks "
            "WHERE quick_task_id=?", (quick_task_id,))).fetchone()
        if not task:
            return []
        meta: dict[int, dict] = {}
        if task["created_by_staff_id"]:
            meta[task["created_by_staff_id"]] = {"relation": "creator", "muted": 0}
        if task["assigned_to_staff_id"]:
            meta.setdefault(task["assigned_to_staff_id"], {"relation": "assignee", "muted": 0})
        wrows = await (await conn.execute(
            "SELECT staff_id, relation, muted FROM nidaan_quick_task_watchers WHERE quick_task_id=?",
            (quick_task_id,))).fetchall()
        for w in wrows:
            prev = meta.get(w["staff_id"])
            # keep the creator/assignee label but carry the mute flag from the row
            rel = prev["relation"] if prev else w["relation"]
            meta[w["staff_id"]] = {"relation": rel, "muted": int(w["muted"])}
        if not meta:
            return []
        ph = ",".join("?" * len(meta))
        srows = await (await conn.execute(
            f"SELECT staff_id, name, role, phone, profile_pic, "
            f"       COALESCE(NULLIF(notify_email,''), email) AS email "
            f"FROM nidaan_staff WHERE staff_id IN ({ph}) "
            f"AND status='active' AND deleted_at IS NULL", list(meta.keys()))).fetchall()
        out = []
        for r in srows:
            m = meta.get(r["staff_id"], {})
            d = dict(r); d["relation"] = m.get("relation", "watcher"); d["muted"] = m.get("muted", 0)
            out.append(d)
        return out


async def set_quick_task_approval(quick_task_id: int, decision: str,
                                   changed_by: int, note: str = "", source: str = None) -> bool:
    """Approve or reject a quick task. decision: 'approved' | 'rejected'."""
    decision = (decision or "").lower()
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_quick_tasks SET approval_status=?, "
            "approved_by_staff_id=?, approved_at=CURRENT_TIMESTAMP "
            "WHERE quick_task_id=?", (decision, changed_by, quick_task_id))
        await _log_quick_task(conn, quick_task_id,
                              "approve" if decision == "approved" else "reject",
                              to_value=decision, changed_by=changed_by, note=note, source=source)
        await conn.commit()
    return True


async def get_quick_task(quick_task_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT q.*, "
            "       a.name AS assignee_name, a.role AS assignee_role, "
            "       a.phone AS assignee_phone, "
            "       COALESCE(NULLIF(a.notify_email,''), a.email) AS assignee_email, "
            "       cr.name AS creator_name, cr.role AS creator_role, "
            "       cr.phone AS creator_phone, "
            "       COALESCE(NULLIF(cr.notify_email,''), cr.email) AS creator_email, "
            "       c.insured_name "
            "FROM nidaan_quick_tasks q "
            "LEFT JOIN nidaan_staff a  ON a.staff_id = q.assigned_to_staff_id "
            "LEFT JOIN nidaan_staff cr ON cr.staff_id = q.created_by_staff_id "
            "LEFT JOIN nidaan_claims c ON c.claim_id = q.claim_id "
            "WHERE q.quick_task_id = ?", (quick_task_id,))).fetchone()
        return dict(row) if row else None


def _quick_task_order_sql(sort: Optional[str]) -> str:
    """ORDER BY clause for the task list. 'smart' (default) keeps active work on top
    then priority then newest; the rest are explicit user-chosen sorts."""
    smart = (" ORDER BY "
             "   CASE q.status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 0 ELSE 1 END, "
             "   CASE q.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
             "                   WHEN 'normal' THEN 2 ELSE 3 END, "
             "   q.created_at DESC")
    return {
        "smart":        smart,
        "id_desc":      " ORDER BY q.quick_task_id DESC",
        "id_asc":       " ORDER BY q.quick_task_id ASC",
        "updated":      " ORDER BY q.updated_at DESC, q.quick_task_id DESC",
        "created_desc": " ORDER BY q.created_at DESC, q.quick_task_id DESC",
        "created_asc":  " ORDER BY q.created_at ASC, q.quick_task_id ASC",
        "due":          " ORDER BY (q.due_date IS NULL), q.due_date ASC, q.quick_task_id DESC",
        "priority":     (" ORDER BY CASE q.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
                         "WHEN 'normal' THEN 2 ELSE 3 END, q.created_at DESC"),
    }.get((sort or "smart"), smart)


async def list_quick_tasks(*, status: Optional[str] = None,
                            assigned_to_staff_id: Optional[int] = None,
                            viewer_staff_id: Optional[int] = None,
                            claim_id: Optional[int] = None,
                            task_type: Optional[str] = None,
                            category_code: Optional[str] = None,
                            search: Optional[str] = None,
                            for_staff_id: Optional[int] = None,
                            overdue: bool = False,
                            pending_approval: bool = False,
                            include_done: bool = False,
                            include_deleted: bool = False,
                            sort: Optional[str] = None,
                            scope: Optional[str] = None,
                            scope_staff_id: Optional[int] = None,
                            limit: int = 100) -> list[dict]:
    """Flexible task query.
    - include_done=False (default): hides done/cancelled (the "open work" view).
    - include_done=True: every status (the registry view).
    - status=<one>: pins to exactly that status (overrides include_done).
    - include_deleted=True: also returns soft-deleted rows (admin audit only).
    - viewer_staff_id: associate scope — tasks assigned TO or created BY them.
    """
    where, params = [], []
    if not include_deleted:
        where.append("q.deleted_at IS NULL")
    if viewer_staff_id is not None:
        # Associates see tasks assigned TO / created BY them, PLUS tasks they've been
        # @mentioned into (collaboration participants).
        where.append("(q.assigned_to_staff_id = ? OR q.created_by_staff_id = ? "
                     "OR EXISTS (SELECT 1 FROM nidaan_quick_task_watchers w "
                     "WHERE w.quick_task_id = q.quick_task_id AND w.staff_id = ?))")
        params += [viewer_staff_id, viewer_staff_id, viewer_staff_id]
    if scope_staff_id is not None and scope in ("assigned_to_me", "created_by_me", "involved"):
        # Personalised dashboard slices.
        if scope == "assigned_to_me":
            where.append("q.assigned_to_staff_id = ?")
            params.append(scope_staff_id)
        elif scope == "created_by_me":
            where.append("q.created_by_staff_id = ?")
            params.append(scope_staff_id)
        else:  # involved: @mentioned in, but NOT mine by assignment/creation
            where.append("EXISTS (SELECT 1 FROM nidaan_quick_task_watchers w "
                         "WHERE w.quick_task_id = q.quick_task_id AND w.staff_id = ? "
                         "AND w.relation = 'mentioned') "
                         "AND COALESCE(q.assigned_to_staff_id,-1) != ? "
                         "AND COALESCE(q.created_by_staff_id,-1) != ?")
            params += [scope_staff_id, scope_staff_id, scope_staff_id]
    if status == "archived":
        # Archive = finished work (done + cancelled). Kept out of the working board so
        # the list doesn't grow forever, but always retrievable.
        where.append("q.status IN ('done','cancelled')")
    elif status:
        where.append("q.status = ?"); params.append(status)
    elif not include_done:
        where.append("q.status NOT IN ('done','cancelled')")
    if assigned_to_staff_id is not None:
        where.append("q.assigned_to_staff_id = ?"); params.append(assigned_to_staff_id)
    if claim_id is not None:
        where.append("q.claim_id = ?"); params.append(claim_id)
    if task_type in ("assignment", "request"):
        where.append("q.task_type = ?"); params.append(task_type)
    if category_code:
        where.append("q.category_code = ?"); params.append(category_code.strip().upper())
    if overdue:
        where.append("q.due_date IS NOT NULL AND q.due_date < datetime('now') "
                     "AND q.status NOT IN ('done','cancelled')")
    if pending_approval:
        where.append("q.requires_approval = 1 AND q.approval_status = 'pending'")
    if search:
        s = search.strip()
        like = f"%{s}%"
        # A bare number also matches the task's #id (e.g. searching "20" finds #20).
        if s.isdigit():
            where.append("(q.title LIKE ? OR q.description LIKE ? OR q.quick_task_id = ?)")
            params += [like, like, int(s)]
        else:
            where.append("(q.title LIKE ? OR q.description LIKE ?)")
            params += [like, like]
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    # Green-blink signal (A+B): for tasks that are the viewer's OWN (assigned to
    # or created by them), compute the latest activity time (created / newest
    # comment / newest status-log change) and the viewer's last "seen" time.
    # has_new (green blink) is computed in Python from these.
    if for_staff_id is not None:
        unseen_sql = (
            ", CASE WHEN (q.assigned_to_staff_id=? OR q.created_by_staff_id=?) THEN 1 ELSE 0 END AS mine "
            ", MAX(q.created_at, "
            "     COALESCE((SELECT MAX(created_at) FROM nidaan_quick_task_notes n WHERE n.quick_task_id=q.quick_task_id), q.created_at), "
            "     COALESCE((SELECT MAX(changed_at) FROM nidaan_quick_task_log lg WHERE lg.quick_task_id=q.quick_task_id), q.created_at)) AS last_activity "
            ", (SELECT seen_at FROM nidaan_quick_task_seen sv WHERE sv.quick_task_id=q.quick_task_id AND sv.staff_id=?) AS seen_at ")
        unseen_params = [for_staff_id, for_staff_id, for_staff_id]
    else:
        unseen_sql = ", 0 AS mine, q.created_at AS last_activity, NULL AS seen_at "
        unseen_params = []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT q.*, "
            "       a.name AS assignee_name, a.role AS assignee_role, a.profile_pic AS assignee_pic, "
            "       cr.name AS creator_name, cr.profile_pic AS creator_pic, "
            "       c.insured_name, "
            "       (SELECT COUNT(*) FROM nidaan_leave_requests lv "
            "          WHERE lv.staff_id = q.assigned_to_staff_id AND lv.status='approved' "
            "            AND date('now') BETWEEN date(lv.start_date) AND date(lv.end_date)) "
            "         AS assignee_on_leave "
            + unseen_sql +
            "FROM nidaan_quick_tasks q "
            "LEFT JOIN nidaan_staff a  ON a.staff_id = q.assigned_to_staff_id "
            "LEFT JOIN nidaan_staff cr ON cr.staff_id = q.created_by_staff_id "
            "LEFT JOIN nidaan_claims c ON c.claim_id = q.claim_id "
            + clause + _quick_task_order_sql(sort) + " LIMIT ?",
            unseen_params + params + [limit])
        rows = [dict(r) for r in await cur.fetchall()]
        # Green blink = a task with activity I haven't seen yet; gray once I open it.
        #   • MY tasks (assigned/created): blink on any unseen activity (incl. brand new).
        #   • OTHER tasks: blink only when there's activity NEWER than I last opened it
        #     (so we don't flood every never-opened task on first load).
        for r in rows:
            seen = r.get("seen_at")
            act = r.get("last_activity")
            new_since_seen = bool(seen and act and str(act) > str(seen))
            if r.get("mine"):
                r["has_new"] = 1 if (not seen or new_since_seen) else 0
            else:
                r["has_new"] = 1 if new_since_seen else 0
            r["unseen"] = r["has_new"]   # kept for existing frontend field
        return rows


async def quick_task_status_counts(*, assigned_to_staff_id: Optional[int] = None,
                                    viewer_staff_id: Optional[int] = None) -> dict:
    """Counts for the Tasks dashboard/registry (excludes soft-deleted).
    Includes per-status counts plus derived overdue + pending_approval."""
    where, params = ["deleted_at IS NULL"], []
    if assigned_to_staff_id is not None:
        where.append("assigned_to_staff_id = ?"); params.append(assigned_to_staff_id)
    if viewer_staff_id is not None:
        where.append("(assigned_to_staff_id = ? OR created_by_staff_id = ?)")
        params += [viewer_staff_id, viewer_staff_id]
    clause = " WHERE " + " AND ".join(where)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT status, COUNT(*) AS n FROM nidaan_quick_tasks"
            + clause + " GROUP BY status", params)
        rows = {r["status"]: r["n"] for r in await cur.fetchall()}
        # overdue: past due date and still open/in_progress
        overdue = (await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_quick_tasks" + clause +
            " AND due_date IS NOT NULL AND due_date < datetime('now') "
            "AND status NOT IN ('done','cancelled')", params)).fetchone())[0]
        # pending approval
        pending_appr = (await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_quick_tasks" + clause +
            " AND requires_approval = 1 AND approval_status = 'pending'",
            params)).fetchone())[0]
    rows["all"] = sum(rows.values())
    rows["active"] = rows.get("open", 0) + rows.get("in_progress", 0)
    rows["archived"] = rows.get("done", 0) + rows.get("cancelled", 0)
    rows["overdue"] = overdue
    rows["pending_approval"] = pending_appr
    return rows


async def _log_quick_task(conn, quick_task_id: int, action: str,
                          from_value: str = None, to_value: str = None,
                          changed_by: int = None, note: str = "",
                          source: str = None) -> None:
    """Append an immutable history row (uses an existing open connection).
    `source` records where the action came from: web | mobile-web | telegram."""
    await conn.execute(
        "INSERT INTO nidaan_quick_task_log "
        "(quick_task_id, action, from_value, to_value, changed_by_staff_id, note, source) "
        "VALUES (?,?,?,?,?,?,?)",
        (quick_task_id, action, from_value, to_value, changed_by, note or "", source))


async def update_quick_task_status(quick_task_id: int, status: str,
                                   changed_by: int = None, note: str = "",
                                   source: str = None) -> bool:
    if status not in QUICK_TASK_STATUSES:
        return False
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await (await conn.execute(
            "SELECT status, completed_at FROM nidaan_quick_tasks WHERE quick_task_id=?",
            (quick_task_id,))).fetchone()
        if not cur:
            return False
        prev = cur["status"]
        # Reopening a done/cancelled task → clear completed_at + flag the action.
        reopening = prev in ("done", "cancelled") and status in ("open", "in_progress")
        done_clause = ", completed_at = CURRENT_TIMESTAMP" if status == "done" else \
                      (", completed_at = NULL" if reopening else "")
        await conn.execute(
            f"UPDATE nidaan_quick_tasks SET status = ?, updated_at = CURRENT_TIMESTAMP{done_clause} "
            "WHERE quick_task_id = ?", (status, quick_task_id))
        await _log_quick_task(conn, quick_task_id,
                              "reopen" if reopening else "status",
                              from_value=prev, to_value=status,
                              changed_by=changed_by, note=note, source=source)
        await conn.commit()
    return True


async def reassign_quick_task(quick_task_id: int, assignee_staff_id: Optional[int],
                              changed_by: int = None, note: str = "",
                              source: str = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        prev = await (await conn.execute(
            "SELECT assigned_to_staff_id FROM nidaan_quick_tasks WHERE quick_task_id=?",
            (quick_task_id,))).fetchone()
        await conn.execute(
            "UPDATE nidaan_quick_tasks SET assigned_to_staff_id = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE quick_task_id = ?",
            (assignee_staff_id, quick_task_id))
        await _log_quick_task(conn, quick_task_id, "reassign",
                              from_value=str(prev["assigned_to_staff_id"]) if prev and prev["assigned_to_staff_id"] else None,
                              to_value=str(assignee_staff_id) if assignee_staff_id else None,
                              changed_by=changed_by, note=note, source=source)
        await conn.commit()
    return True


async def soft_delete_quick_task(quick_task_id: int, changed_by: int = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_quick_tasks SET deleted_at = CURRENT_TIMESTAMP "
            "WHERE quick_task_id = ? AND deleted_at IS NULL", (quick_task_id,))
        if cur.rowcount:
            await _log_quick_task(conn, quick_task_id, "delete", changed_by=changed_by)
        await conn.commit()
        return cur.rowcount > 0


async def get_quick_task_history(quick_task_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT l.*, s.name AS by_name FROM nidaan_quick_task_log l "
            "LEFT JOIN nidaan_staff s ON s.staff_id = l.changed_by_staff_id "
            "WHERE l.quick_task_id = ? ORDER BY l.changed_at ASC", (quick_task_id,))
        return [dict(r) for r in await cur.fetchall()]


async def merge_quick_tasks(retain_id: int, duplicate_id: int,
                            changed_by: int = None) -> dict:
    """Merge `duplicate_id` INTO `retain_id` (retain_id is kept). Moves the
    duplicate's comments onto the retained task, records the merge in BOTH
    timelines, and archives the duplicate with a pointer back. Returns a status
    dict. Raises ValueError on invalid input."""
    if retain_id == duplicate_id:
        raise ValueError("Cannot merge a task into itself")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = {r["quick_task_id"]: r for r in await (await conn.execute(
            "SELECT quick_task_id, title, deleted_at, merged_into FROM nidaan_quick_tasks "
            "WHERE quick_task_id IN (?, ?)", (retain_id, duplicate_id))).fetchall()}
        keep = rows.get(retain_id)
        dup = rows.get(duplicate_id)
        if not keep or not dup:
            raise ValueError("One or both tasks not found")
        if dup["deleted_at"] is not None:
            raise ValueError("The duplicate task is already deleted/merged")
        if keep["deleted_at"] is not None:
            raise ValueError("The task to retain is deleted")
        # Move the duplicate's comments onto the retained task.
        await conn.execute(
            "UPDATE nidaan_quick_task_notes SET quick_task_id = ? WHERE quick_task_id = ?",
            (retain_id, duplicate_id))
        # Record the merge in both timelines.
        await _log_quick_task(conn, retain_id, "merge", to_value=str(duplicate_id),
                              changed_by=changed_by,
                              note=f"Merged #{duplicate_id} \"{dup['title']}\" into this task")
        await _log_quick_task(conn, duplicate_id, "merge", to_value=str(retain_id),
                              changed_by=changed_by,
                              note=f"Merged into #{retain_id} \"{keep['title']}\"")
        # Archive the duplicate, pointing at the retained task.
        await conn.execute(
            "UPDATE nidaan_quick_tasks SET deleted_at = CURRENT_TIMESTAMP, "
            "merged_into = ?, status = 'cancelled' WHERE quick_task_id = ?",
            (retain_id, duplicate_id))
        await conn.commit()
    return {"retained": retain_id, "merged": duplicate_id}


# =============================================================================
#  LEAVE REQUESTS — staff apply → admin/SA approve; on-leave surfaces tasks
# =============================================================================

LEAVE_STATUSES = ("pending", "approved", "rejected", "cancelled")


async def create_leave_request(*, staff_id: int, start_date: str, end_date: str,
                                reason: str = "", leave_type: str = "full_day",
                                half_period: str = "", handover_notes: str = "",
                                cover_staff_id: Optional[int] = None,
                                start_time: str = "", end_time: str = "",
                                request_kind: str = "leave") -> int:
    if request_kind not in ("leave", "wfh"):
        request_kind = "leave"
    if leave_type not in ("full_day", "half_day"):
        leave_type = "full_day"
    if leave_type == "half_day":
        end_date = start_date               # a half-day is a single date
        if half_period not in ("first_half", "second_half"):
            half_period = "first_half"
    else:
        half_period = ""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_leave_requests "
            "(staff_id, start_date, end_date, reason, leave_type, half_period, "
            " handover_notes, cover_staff_id, start_time, end_time, request_kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (staff_id, start_date, end_date, (reason or "").strip(), leave_type,
             half_period, (handover_notes or "").strip(), cover_staff_id,
             (start_time or "").strip(), (end_time or "").strip(), request_kind))
        await conn.commit()
        return cur.lastrowid


async def list_upcoming_leaves(days: int = 30) -> list[dict]:
    """Approved leaves starting within the next `days` days (admin visibility)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT l.*, s.name AS staff_name, s.role AS staff_role, "
            "       cov.name AS cover_name, "
            "       (SELECT COUNT(*) FROM nidaan_quick_tasks q "
            "          WHERE q.assigned_to_staff_id = l.staff_id AND q.deleted_at IS NULL "
            "            AND q.status NOT IN ('done','cancelled')) AS open_tasks "
            "FROM nidaan_leave_requests l "
            "LEFT JOIN nidaan_staff s ON s.staff_id = l.staff_id "
            "LEFT JOIN nidaan_staff cov ON cov.staff_id = l.cover_staff_id "
            "WHERE l.status='approved' "
            "  AND date(l.end_date) >= date('now') "
            "  AND date(l.start_date) <= date('now', ?) "
            "ORDER BY l.start_date ASC", (f"+{int(days)} days",))
        return [dict(r) for r in await cur.fetchall()]


async def get_leave_request(leave_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT l.*, s.name AS staff_name, s.phone AS staff_phone, "
            "       COALESCE(NULLIF(s.notify_email,''), s.email) AS staff_email, "
            "       d.name AS decided_by_name, cov.name AS cover_name, "
            "       (SELECT COUNT(*) FROM nidaan_quick_tasks q "
            "          WHERE q.assigned_to_staff_id = l.staff_id AND q.deleted_at IS NULL "
            "            AND q.status NOT IN ('done','cancelled')) AS open_tasks "
            "FROM nidaan_leave_requests l "
            "LEFT JOIN nidaan_staff s ON s.staff_id = l.staff_id "
            "LEFT JOIN nidaan_staff d ON d.staff_id = l.decided_by_staff_id "
            "LEFT JOIN nidaan_staff cov ON cov.staff_id = l.cover_staff_id "
            "WHERE l.leave_id = ?", (leave_id,))).fetchone()
        return dict(row) if row else None


async def list_leave_requests(*, staff_id: Optional[int] = None,
                               status: Optional[str] = None,
                               limit: int = 100) -> list[dict]:
    where, params = [], []
    if staff_id is not None:
        where.append("l.staff_id = ?"); params.append(staff_id)
    if status:
        where.append("l.status = ?"); params.append(status)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT l.*, s.name AS staff_name, s.role AS staff_role, "
            "       d.name AS decided_by_name "
            "FROM nidaan_leave_requests l "
            "LEFT JOIN nidaan_staff s ON s.staff_id = l.staff_id "
            "LEFT JOIN nidaan_staff d ON d.staff_id = l.decided_by_staff_id "
            + clause +
            " ORDER BY (l.status='pending') DESC, l.start_date DESC LIMIT ?",
            params + [limit])
        return [dict(r) for r in await cur.fetchall()]


async def list_leave_history(*, date_from: Optional[str] = None,
                              date_to: Optional[str] = None,
                              staff_id: Optional[int] = None,
                              status: Optional[str] = None,
                              kind: Optional[str] = None,
                              limit: int = 5000) -> list[dict]:
    """Leave/WFH history for the super-admin report. A record matches the date
    window when its leave period OVERLAPS [date_from, date_to] (inclusive):
    start_date <= date_to AND end_date >= date_from. All filters are optional."""
    where, params = [], []
    if date_to:
        where.append("l.start_date <= ?"); params.append(date_to)
    if date_from:
        where.append("l.end_date >= ?"); params.append(date_from)
    if staff_id is not None:
        where.append("l.staff_id = ?"); params.append(staff_id)
    if status:
        where.append("l.status = ?"); params.append(status)
    if kind:
        where.append("COALESCE(l.request_kind,'leave') = ?"); params.append(kind)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT l.*, s.name AS staff_name, s.role AS staff_role, "
            "       d.name AS decided_by_name "
            "FROM nidaan_leave_requests l "
            "LEFT JOIN nidaan_staff s ON s.staff_id = l.staff_id "
            "LEFT JOIN nidaan_staff d ON d.staff_id = l.decided_by_staff_id "
            + clause +
            " ORDER BY l.start_date DESC, l.leave_id DESC LIMIT ?",
            params + [limit])
        return [dict(r) for r in await cur.fetchall()]


async def decide_leave_request(leave_id: int, decision: str, decided_by: int,
                                note: str = "") -> bool:
    """decision: 'approved' | 'rejected'."""
    decision = (decision or "").lower()
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_leave_requests SET status=?, decided_by_staff_id=?, "
            "decided_at=CURRENT_TIMESTAMP, decision_note=? "
            "WHERE leave_id=? AND status='pending'",
            (decision, decided_by, (note or "").strip(), leave_id))
        await conn.commit()
    return True


async def cancel_leave_request(leave_id: int, staff_id: int) -> bool:
    """A staffer withdraws their own still-pending request."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_leave_requests SET status='cancelled' "
            "WHERE leave_id=? AND staff_id=? AND status='pending'",
            (leave_id, staff_id))
        await conn.commit()
    return True


async def list_staff_on_leave_now() -> list[dict]:
    """Staff whose approved leave window includes today, with their open task count."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT l.leave_id, l.staff_id, l.start_date, l.end_date, l.reason, "
            "       l.leave_type, l.half_period, l.handover_notes, "
            "       COALESCE(l.request_kind,'leave') AS request_kind, "
            "       s.name AS staff_name, s.role AS staff_role, "
            "       cov.name AS cover_name, "
            "       (SELECT COUNT(*) FROM nidaan_quick_tasks q "
            "          WHERE q.assigned_to_staff_id = l.staff_id "
            "            AND q.deleted_at IS NULL "
            "            AND q.status NOT IN ('done','cancelled')) AS open_tasks "
            "FROM nidaan_leave_requests l "
            "LEFT JOIN nidaan_staff s ON s.staff_id = l.staff_id "
            "LEFT JOIN nidaan_staff cov ON cov.staff_id = l.cover_staff_id "
            "WHERE l.status='approved' "
            "  AND date('now') BETWEEN date(l.start_date) AND date(l.end_date) "
            "ORDER BY l.end_date ASC")
        return [dict(r) for r in await cur.fetchall()]


async def add_quick_task_note(*, quick_task_id: int, staff_id: int, note: str,
                                parent_note_id: Optional[int] = None,
                                attachment_stored_name: Optional[str] = None,
                                attachment_original_name: Optional[str] = None,
                                source: Optional[str] = None) -> int:
    # Flatten: a reply-to-a-reply becomes a reply to the original parent.
    if parent_note_id:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT parent_note_id, quick_task_id FROM nidaan_quick_task_notes "
                "WHERE note_id = ?", (parent_note_id,))).fetchone()
            if not row or row["quick_task_id"] != quick_task_id:
                parent_note_id = None
            elif row["parent_note_id"]:
                parent_note_id = row["parent_note_id"]
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_quick_task_notes "
            "(quick_task_id, staff_id, note, parent_note_id, attachment_stored_name, "
            " attachment_original_name, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (quick_task_id, staff_id, note.strip(), parent_note_id,
             attachment_stored_name, attachment_original_name, source))
        await conn.commit()
        return cur.lastrowid


async def set_note_translation(note_id: int, lang: str, translation: str) -> None:
    """Attach an auto English translation to a comment (non-destructive — the original
    note text is never touched). Shown as an aid on the English web dashboard."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_quick_task_notes SET note_lang=?, note_translation=? WHERE note_id=?",
            (lang, translation, note_id))
        await conn.commit()


async def list_quick_task_notes(quick_task_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT n.*, s.name AS staff_name, s.role AS staff_role, "
            "       ap.name AS approved_by_name "
            "FROM nidaan_quick_task_notes n "
            "LEFT JOIN nidaan_staff s  ON s.staff_id = n.staff_id "
            "LEFT JOIN nidaan_staff ap ON ap.staff_id = n.approved_by_staff_id "
            "WHERE n.quick_task_id = ? ORDER BY n.created_at ASC",
            (quick_task_id,))
        notes = [dict(r) for r in await cur.fetchall()]
        if not notes:
            return notes
        # Attach read-receipts (who read each comment, when) — excluding the author.
        rcur = await conn.execute(
            "SELECT r.note_id, r.read_at, s.name AS reader_name "
            "FROM nidaan_quick_task_note_reads r "
            "JOIN nidaan_quick_task_notes n ON n.note_id = r.note_id "
            "LEFT JOIN nidaan_staff s ON s.staff_id = r.staff_id "
            "WHERE n.quick_task_id = ? AND r.staff_id != n.staff_id "
            "ORDER BY r.read_at ASC", (quick_task_id,))
        reads: dict[int, list] = {}
        for rr in await rcur.fetchall():
            reads.setdefault(rr["note_id"], []).append(
                {"name": rr["reader_name"], "at": rr["read_at"]})
        for n in notes:
            n["reads"] = reads.get(n["note_id"], [])
        return notes


async def mark_quick_task_notes_read(quick_task_id: int, staff_id: int) -> None:
    """Mark every comment read + the TASK itself seen by `staff_id` (drives the
    green→gray blink). Called whenever the staffer opens the task."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO nidaan_quick_task_note_reads (note_id, staff_id) "
            "SELECT note_id, ? FROM nidaan_quick_task_notes "
            "WHERE quick_task_id = ? AND staff_id != ?",
            (staff_id, quick_task_id, staff_id))
        await conn.execute(
            "INSERT INTO nidaan_quick_task_seen (quick_task_id, staff_id, seen_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(quick_task_id, staff_id) DO UPDATE SET seen_at=CURRENT_TIMESTAMP",
            (quick_task_id, staff_id))
        await conn.commit()


async def set_quick_task_note_approval(note_id: int, approved_by: Optional[int]) -> bool:
    """Approve a comment (approved_by set) or clear approval (approved_by=None)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        if approved_by:
            await conn.execute(
                "UPDATE nidaan_quick_task_notes SET approved_by_staff_id=?, "
                "approved_at=CURRENT_TIMESTAMP WHERE note_id=?", (approved_by, note_id))
        else:
            await conn.execute(
                "UPDATE nidaan_quick_task_notes SET approved_by_staff_id=NULL, "
                "approved_at=NULL WHERE note_id=?", (note_id,))
        await conn.commit()
    return True


async def get_admin_stats() -> dict:
    """Admin: quick dashboard numbers."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        def _first(cur_result):
            return cur_result[0] if cur_result else 0

        total_accounts = _first(await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_accounts")).fetchone())
        active_subs = _first(await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_subscriptions WHERE status='active'")).fetchone())
        total_claims = _first(await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_claims")).fetchone())
        open_claims = _first(await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_claims WHERE status NOT IN "
            "('resolved_won','resolved_lost','closed','withdrawn')")).fetchone())
        pending_reviews = _first(await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_per_claim_purchase WHERE status='pending_payment'")).fetchone())

        plan_counts = {}
        cur = await conn.execute(
            "SELECT plan, COUNT(*) as cnt FROM nidaan_subscriptions "
            "WHERE status='active' GROUP BY plan"
        )
        for row in await cur.fetchall():
            plan_counts[row[0]] = row[1]

        return {
            "total_accounts": total_accounts,
            "active_subscriptions": active_subs,
            "total_claims": total_claims,
            "open_claims": open_claims,
            "pending_review_requests": pending_reviews,
            "plans": plan_counts,
        }


# =============================================================================
#  RAZORPAY SUBSCRIPTION (Nidaan-specific)
# =============================================================================

NIDAAN_RAZORPAY_PLANS = {
    # MONTHLY billing (period="monthly" interval=1). Annual is period="yearly"
    # interval=1 at ~10× monthly (2 months free). The "tag" is what we write to
    # each Razorpay Plan's notes.nidaan_plan — bumped to "_m1" so ensure_nidaan_plans
    # creates BRAND-NEW monthly plans instead of reusing the old ₹/quarter ones
    # (Razorpay plans are immutable). The dict KEY (silver/gold/...) stays the
    # internal plan id used everywhere else (checkout, DB, webhook), unchanged.
    "silver":          {"amount_paise": 50000,   "display": "₹500/month",    "period_days": 30,  "period": "monthly", "interval": 1, "tag": "silver_m1"},
    "gold":            {"amount_paise": 99900,   "display": "₹999/month",    "period_days": 30,  "period": "monthly", "interval": 1, "tag": "gold_m2"},
    "platinum":        {"amount_paise": 199900,  "display": "₹1,999/month",  "period_days": 30,  "period": "monthly", "interval": 1, "tag": "platinum_m2"},
    # Annual plans — recurring yearly, 10× monthly (2 months free)
    "silver_annual":   {"amount_paise": 500000,  "display": "₹5,000/year",   "period_days": 365, "period": "yearly",  "interval": 1, "tag": "silver_annual_m1"},
    "gold_annual":     {"amount_paise": 999000,  "display": "₹9,990/year",   "period_days": 365, "period": "yearly",  "interval": 1, "tag": "gold_annual_m2"},
    "platinum_annual": {"amount_paise": 1999000, "display": "₹19,990/year",  "period_days": 365, "period": "yearly",  "interval": 1, "tag": "platinum_annual_m2"},
}

# Cache: plan_key → razorpay_plan_id
_nidaan_plan_ids: dict[str, str] = {}


async def ensure_nidaan_plans(rzp_key_id: str, rzp_key_secret: str):
    """Create Razorpay plan objects for Nidaan if not already cached."""
    import httpx
    for plan_key, info in NIDAAN_RAZORPAY_PLANS.items():
        if plan_key in _nidaan_plan_ids:
            continue
        # The Razorpay-side identity is the versioned `tag` (falls back to the
        # plan key). Bumping the tag forces a fresh plan at the new price rather
        # than reusing an old immutable one.
        tag = info.get("tag", plan_key)
        # Try to find existing
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.razorpay.com/v1/plans?count=100",
                    auth=(rzp_key_id, rzp_key_secret), timeout=15.0,
                )
                for p in r.json().get("items", []):
                    notes = p.get("notes")
                    if isinstance(notes, dict) and notes.get("nidaan_plan") == tag:
                        _nidaan_plan_ids[plan_key] = p["id"]
                        break
        except Exception as e:
            logger.warning("Razorpay plan lookup failed for %s: %s", plan_key, e)
        if plan_key in _nidaan_plan_ids:
            continue
        # Create new plan
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.razorpay.com/v1/plans",
                    auth=(rzp_key_id, rzp_key_secret),
                    json={
                        "period": info["period"],
                        "interval": info["interval"],
                        "item": {
                            "name": f"Nidaan {plan_key.title()} Plan (Monthly)",
                            "amount": info["amount_paise"],
                            "currency": "INR",
                            "description": info["display"],
                        },
                        "notes": {
                            "nidaan_plan": tag,
                            "product": "nidaan",
                        },
                    },
                    timeout=15.0,
                )
                result = r.json()
                if "id" in result:
                    _nidaan_plan_ids[plan_key] = result["id"]
                    logger.info("Created Nidaan Razorpay plan %s (tag %s) → %s", plan_key, tag, result["id"])
        except Exception as e:
            logger.error("Failed to create Nidaan plan %s: %s", plan_key, e)


async def create_nidaan_razorpay_order(
    account_id: int,
    plan: str,
    rzp_key_id: str,
    rzp_key_secret: str,
    email: str,
    phone: str,
) -> dict:
    """
    Create a Razorpay ORDER (one-time payment) for a Nidaan quarterly plan.
    Orders support UPI, cards, wallets, net banking — all payment methods.
    We record 90-day access in our DB on successful payment verification.
    """
    import httpx
    info = NIDAAN_RAZORPAY_PLANS.get(plan)
    if not info:
        return {"error": f"Unknown plan: {plan}"}
    # Live price comes from the editable config table (single source of truth); fall back to
    # the hardcoded seed only until the table is seeded. This is the ONLY place the charge
    # amount is set, so an edited price applies to new checkouts immediately.
    cfg = await get_plan_cfg(plan)
    if cfg and not cfg.get("active"):
        return {"error": f"Plan not available: {plan}"}
    if cfg and cfg.get("price_paise"):
        amount_paise = int(cfg["price_paise"])
        _bill = cfg.get("billing", info.get("period", "monthly"))
        amount_display = f"₹{amount_paise // 100:,}/{'year' if _bill == 'yearly' else 'month'}"
    else:
        amount_paise = int(info["amount_paise"])
        amount_display = info["display"]
    # GST (exclusive): add tax on top when enabled. base_paise kept for the ledger.
    _base_paise = amount_paise
    _g = await charge_with_gst(amount_paise / 100)
    amount_paise = _g["total_paise"]
    try:
        import time
        receipt = f"nidaan_{account_id}_{plan}_{int(time.time())}"
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.razorpay.com/v1/orders",
                auth=(rzp_key_id, rzp_key_secret),
                json={
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": receipt[:40],   # Razorpay receipt max 40 chars
                    "payment_capture": 1,      # auto-capture authorized payments
                    "notes": {
                        "nidaan_account_id": str(account_id),
                        "nidaan_plan": plan,
                        "product": "nidaan",
                        "notify_email": email,
                    },
                },
                timeout=20.0,
            )
            result = r.json()
            if "id" not in result:
                err = result.get("error", {}).get("description", "Order creation failed")
                logger.error("Nidaan order creation failed: %s", result)
                return {"error": err}
            logger.info("Nidaan order created: account=%d plan=%s order=%s", account_id, plan, result["id"])
            return {
                "order_id": result["id"],
                "amount": amount_paise,
                "plan": plan,
                "amount_display": amount_display,
                "gst": {"enabled": _g["enabled"], "rate": _g["rate"],
                        "base": _base_paise // 100,
                        "gst": (amount_paise - _base_paise) // 100,
                        "total": amount_paise // 100},
                "razorpay_key_id": rzp_key_id,
            }
    except Exception as e:
        logger.error("Nidaan Razorpay order error: %s", e)
        return {"error": str(e)}


async def _provision_sarathi_bundle(nidaan_account_id: int, plan: str, period_days: int) -> None:
    """Find or create a Sarathi tenant for this Nidaan account, grant bundled access.
    Idempotent — safe to call on every activation/renewal.
    Maps Nidaan plan → Sarathi tier: silver→individual, gold→team, platinum→enterprise.
    """
    # Get the Nidaan account email to find/create matching Sarathi tenant
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT owner_name, email, phone, firm_name FROM nidaan_accounts WHERE account_id=?",
            (nidaan_account_id,),
        )
        account = await cur.fetchone()
    if not account:
        logger.warning("_provision_sarathi_bundle: nidaan account %d not found", nidaan_account_id)
        return

    email = account["email"]
    # Skip internal staff accounts — they don't get Sarathi bundles
    if email.lower().endswith("@nidaanpartner.com"):
        logger.info("_provision_sarathi_bundle: skipping staff email %s", email)
        return

    sarathi_plan_map = {
        "silver": "individual", "silver_annual": "individual",
        "gold": "team", "gold_annual": "team",
        "platinum": "enterprise", "platinum_annual": "enterprise",
    }
    sarathi_plan = sarathi_plan_map.get(plan, "individual")
    bundled_until = (date.today() + timedelta(days=period_days)).isoformat()

    # Find or create the Sarathi tenant (via the platform boundary — the only
    # module allowed to touch Sarathi's tenants/agents tables).
    tenant_id = await bridge.upsert_bundle_tenant(
        email=email,
        owner_name=account["owner_name"],
        firm_name=account["firm_name"],
        phone=account["phone"],
        sarathi_plan=sarathi_plan,
        bundled_until=bundled_until,
    )

    # Record the product link
    await link_to_sarathi(nidaan_account_id, tenant_id, source="nidaan_bundle")
    logger.info("✅ Sarathi bundle provisioned: nidaan_account=%d → sarathi_tenant=%d plan=%s until=%s",
                nidaan_account_id, tenant_id, sarathi_plan, bundled_until)


async def activate_from_order_payment(
    razorpay_order_id: str,
    nidaan_account_id: int,
    plan: str,
    amount_paise: int,
    razorpay_payment_id: str = "",
) -> bool:
    """Activate a Nidaan subscription from a one-time order payment. Idempotent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT sub_id FROM nidaan_subscriptions "
            "WHERE razorpay_subscription_id=? AND plan=?",
            (razorpay_order_id, plan),
        )
        existing = await cur.fetchone()
    if existing:
        logger.info("Nidaan order already activated: %s", razorpay_order_id)
        if razorpay_payment_id:
            async with aiosqlite.connect(DB_PATH) as conn:
                await conn.execute(
                    "UPDATE nidaan_subscriptions SET razorpay_payment_id=? "
                    "WHERE sub_id=? AND (razorpay_payment_id IS NULL OR razorpay_payment_id='')",
                    (razorpay_payment_id, existing[0]))
                await conn.commit()
        return True
    plan_info = NIDAAN_RAZORPAY_PLANS.get(plan, {})
    period_days = plan_info.get("period_days", 92)
    sub_id = await create_subscription(
        account_id=nidaan_account_id,
        plan=plan,
        amount_paid=amount_paise // 100,
        razorpay_subscription_id=razorpay_order_id,
        period_days=period_days,
        razorpay_payment_id=razorpay_payment_id,
    )
    logger.info("✅ Nidaan activated via order: account=%d plan=%s sub_id=%d amount=₹%d period_days=%d",
                nidaan_account_id, plan, sub_id, amount_paise // 100, period_days)

    # Provision Sarathi CRM access if the plan includes the bundle
    if PLAN_LIMITS.get(plan, {}).get("sarathi_bundle"):
        await _provision_sarathi_bundle(nidaan_account_id, plan, period_days)

    # GST ledger: record the tax collected on this subscription (no-op when GST off).
    try:
        _cfg = await get_plan_cfg(plan)
        _base = (int(_cfg["price_paise"]) / 100) if (_cfg and _cfg.get("price_paise")) \
            else (NIDAAN_RAZORPAY_PLANS.get(plan, {}).get("amount_paise", 0) / 100)
        await record_gst(razorpay_payment_id, "subscription", _base, account_id=nidaan_account_id)
    except Exception as _ge:
        logger.warning("record_gst (subscription) failed: %s", _ge)

    return True


async def create_nidaan_razorpay_subscription(
    account_id: int,
    plan: str,
    rzp_key_id: str,
    rzp_key_secret: str,
    email: str,
    phone: str,
) -> dict:
    """Kept for backwards compat. Use create_nidaan_razorpay_order instead."""
    return await create_nidaan_razorpay_order(
        account_id, plan, rzp_key_id, rzp_key_secret, email, phone
    )


async def create_nidaan_recurring_subscription(
    account_id: int,
    plan: str,
    rzp_key_id: str,
    rzp_key_secret: str,
    email: str,
    phone: str,
) -> dict:
    """
    Create a Razorpay recurring subscription for any Nidaan plan — quarterly
    (period=monthly interval=3) OR annual (period=yearly interval=1). Every
    subscription is recurring; only the ₹499 single review is a one-time order.
    Returns {subscription_id, razorpay_key_id, plan, amount_display, ...}
    """
    import httpx, time
    info = NIDAAN_RAZORPAY_PLANS.get(plan)
    if not info:
        return {"error": f"Unknown plan: {plan}"}

    # Base price = the SUPER-ADMIN-configured price (single source of truth:
    # nidaan_plans_config.price_paise — the same number shown on the pricing page). Falls back
    # to the hardcoded seed only if the plan has no DB config row yet. This is what makes a
    # price edited in the plans cockpit apply to EVERY new subscriber's autopay.
    _cfg = await get_plan_cfg(plan)
    _base_paise = int(_cfg.get("price_paise") or info["amount_paise"])

    # GST-versioned plan: when GST is on, use a DISTINCT Razorpay plan at the GST-inclusive
    # amount so existing non-GST autopay mandates are grandfathered.
    _gcfg = await gst_config()
    _amt_paise = (await charge_with_gst(_base_paise / 100))["total_paise"]
    _gsuf = ("_gst" + str(int(_gcfg["rate"]))) if _gcfg["enabled"] else ""
    # Version the Razorpay plan by the ACTUAL charged amount (…_a<paise>) so a price change
    # spins up a NEW Razorpay plan; existing subscribers stay on their old plan_id and keep
    # the amount their mandate authorised → automatic grandfathering.
    tag = info.get("tag", plan) + _gsuf + f"_a{_amt_paise}"
    _cache_key = plan + _gsuf + f"_a{_amt_paise}"
    razorpay_plan_id = _nidaan_plan_ids.get(_cache_key)
    if not razorpay_plan_id:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.razorpay.com/v1/plans?count=100",
                    auth=(rzp_key_id, rzp_key_secret), timeout=15.0,
                )
                for p in r.json().get("items", []):
                    _n = p.get("notes")
                    if isinstance(_n, dict) and _n.get("nidaan_plan") == tag:
                        razorpay_plan_id = p["id"]
                        _nidaan_plan_ids[_cache_key] = razorpay_plan_id
                        break
        except Exception as e:
            logger.warning("Nidaan plan lookup failed for %s: %s", plan, e)

    if not razorpay_plan_id:
        # Create the Razorpay plan now at the current (monthly/annual) price.
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.razorpay.com/v1/plans",
                    auth=(rzp_key_id, rzp_key_secret),
                    json={
                        "period": info["period"],
                        "interval": info["interval"],
                        "item": {
                            "name": f"Nidaan {plan.title()} Plan" + (" (incl. GST)" if _gsuf else ""),
                            "amount": _amt_paise,
                            "currency": "INR",
                            "description": info["display"] + (f" + {int(_gcfg['rate'])}% GST" if _gsuf else ""),
                        },
                        "notes": {"nidaan_plan": tag, "product": "nidaan"},
                    },
                    timeout=20.0,
                )
                res = r.json()
                if "id" in res:
                    razorpay_plan_id = res["id"]
                    _nidaan_plan_ids[_cache_key] = razorpay_plan_id
                else:
                    return {"error": res.get("error", {}).get("description", "Failed to create plan")}
        except Exception as e:
            return {"error": str(e)}

    # Create subscription
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.razorpay.com/v1/subscriptions",
                auth=(rzp_key_id, rzp_key_secret),
                json={
                    "plan_id": razorpay_plan_id,
                    # max billing cycles ≈ 10 years (annual=10, monthly=120)
                    "total_count": 10 if info["period"] == "yearly" else 120,
                    "quantity": 1,
                    "notify_info": {"notify_phone": phone, "notify_email": email},
                    "notes": {
                        "nidaan_account_id": str(account_id),
                        "nidaan_plan": plan,
                        "product": "nidaan",
                        "notify_email": email,
                    },
                },
                timeout=20.0,
            )
            result = r.json()
            if "id" not in result:
                err = result.get("error", {}).get("description", "Subscription creation failed")
                return {"error": err}
            logger.info("Nidaan recurring sub created: account=%d plan=%s sub=%s",
                        account_id, plan, result["id"])
            return {
                "subscription_id": result["id"],
                "plan": plan,
                "amount_display": (f"₹{_amt_paise // 100:,} (incl. {int(_gcfg['rate'])}% GST)" if _gsuf else f"₹{_base_paise // 100:,}"),
                "razorpay_key_id": rzp_key_id,
                "gst": {"enabled": _gcfg["enabled"], "rate": _gcfg["rate"],
                        "base": _base_paise // 100,
                        "gst": (_amt_paise - _base_paise) // 100,
                        "total": _amt_paise // 100},
            }
    except Exception as e:
        logger.error("Nidaan Razorpay subscription error: %s", e)
        return {"error": str(e)}


async def verify_nidaan_subscription_and_activate(
    account_id: int,
    plan: str,
    razorpay_payment_id: str,
    razorpay_subscription_id: str,
    razorpay_signature: str,
    rzp_key_secret: str,
) -> dict:
    """
    Verify Razorpay subscription payment for NidaanPartner and immediately activate.
    Subscription signature: HMAC-SHA256(payment_id + '|' + subscription_id)
    """
    import hmac as _hmac, hashlib as _hs
    msg = f"{razorpay_payment_id}|{razorpay_subscription_id}".encode()
    expected = _hmac.new(rzp_key_secret.encode(), msg, _hs.sha256).hexdigest()
    if not _hmac.compare_digest(expected, razorpay_signature):
        return {"error": "Invalid payment signature"}

    # Idempotency check
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT sub_id FROM nidaan_subscriptions "
            "WHERE razorpay_subscription_id=? AND plan=?",
            (razorpay_subscription_id, plan),
        )
        existing = await cur.fetchone()
    if existing:
        sub = await get_active_subscription(account_id)
        return {"status": "ok", "already_processed": True,
                "renewal_date": sub["current_period_end"][:10] if sub else ""}

    plan_info = NIDAAN_RAZORPAY_PLANS.get(plan, {})
    period_days = plan_info.get("period_days", 30)   # monthly/annual only — no quarterly default
    # Record the ACTUAL amount charged = GST-inclusive total from the SUPER-ADMIN price (single source
    # of truth), matching the Razorpay plan. Previously recorded the old round base (₹500) → the record
    # showed less than the customer really paid (₹588.82).
    _base_paise = int((await get_plan_cfg(plan)).get("price_paise") or plan_info.get("amount_paise", 0))
    _amt_paise = (await charge_with_gst(_base_paise / 100))["total_paise"]

    await create_subscription(
        account_id=account_id,
        plan=plan,
        amount_paid=int(round(_amt_paise / 100)),
        razorpay_subscription_id=razorpay_subscription_id,
        period_days=period_days,
    )
    logger.info("✅ Nidaan subscription verified & activated: account=%d plan=%s sub=%s payment=%s",
                account_id, plan, razorpay_subscription_id, razorpay_payment_id)

    if PLAN_LIMITS.get(plan, {}).get("sarathi_bundle"):
        await _provision_sarathi_bundle(account_id, plan, period_days)

    sub = await get_active_subscription(account_id)
    renewal_date = sub["current_period_end"][:10] if sub else ""
    return {"status": "ok", "plan": plan, "renewal_date": renewal_date}


async def activate_from_razorpay_webhook(
    razorpay_sub_id: str,
    nidaan_account_id: int,
    plan: str,
    amount_paise: int,
    razorpay_payment_id: str = "",
) -> bool:
    """Activate OR RENEW a Nidaan subscription from a Razorpay webhook.

    Both `subscription.activated` and `subscription.charged` land here. The FIRST charge creates
    the subscription; every LATER charge is a RENEWAL that must (a) extend current_period_end,
    (b) record GST and (c) write the payment to the unified ledger — previously the function
    returned early whenever the subscription row existed, so renewals silently did none of that
    (a paying customer would have looked expired and the renewal never reached Revenue).

    `record_payment` is the idempotency gate: it returns False when this exact charge was already
    recorded, so duplicate webhooks (and the activated+charged pair on the first payment) can
    never double-extend a period or double-count revenue."""
    # Live plan config is the source of truth for period/price; hardcoded seed is the fallback.
    try:
        _cfg = await get_plan_cfg(plan)
    except Exception:
        _cfg = None
    period_days = int((_cfg or {}).get("period_days") or 0) or \
        int(NIDAAN_RAZORPAY_PLANS.get(plan, {}).get("period_days", 30))
    _base_rs = (int(_cfg["price_paise"]) / 100) if (_cfg and _cfg.get("price_paise")) \
        else (NIDAAN_RAZORPAY_PLANS.get(plan, {}).get("amount_paise", 0) / 100)

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        _ex = await (await conn.execute(
            "SELECT sub_id, current_period_end FROM nidaan_subscriptions "
            "WHERE razorpay_subscription_id=? AND plan=?", (razorpay_sub_id, plan))).fetchone()
    existing = dict(_ex) if _ex else None

    # ── RENEWAL (the subscription already exists) ──────────────────────────────
    if existing:
        _key = (razorpay_payment_id or "").strip() or \
            f"subrenew:{razorpay_sub_id}:{existing.get('current_period_end') or ''}"
        fresh = await record_payment(
            source="subscription_renewal", total_paise=int(amount_paise or 0), dedup_key=_key,
            razorpay_payment_id=(razorpay_payment_id or ""), razorpay_subscription_id=razorpay_sub_id,
            account_id=nidaan_account_id, plan=plan, base_paise=int(_base_rs * 100),
            verified=True, verify_method="webhook", note="recurring subscription charge")
        if not fresh:
            logger.info("Nidaan sub renewal already processed (rzp_sub=%s)", razorpay_sub_id)
            return True
        # Extend from the LATER of now / current end, so an early webhook never shortens a period.
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE nidaan_subscriptions SET status='active', current_period_end = datetime("
                "  CASE WHEN COALESCE(current_period_end,'') > datetime('now') "
                "       THEN current_period_end ELSE datetime('now') END, ?) WHERE sub_id=?",
                (f"+{int(period_days)} days", existing["sub_id"]))
            await conn.commit()
        try:
            await record_gst(_key, "subscription_recurring", _base_rs, account_id=nidaan_account_id)
        except Exception as _ge:
            logger.warning("record_gst (recurring) failed: %s", _ge)
        if PLAN_LIMITS.get(plan, {}).get("sarathi_bundle"):
            try:
                await _provision_sarathi_bundle(nidaan_account_id, plan, period_days)
            except Exception as _be:
                logger.warning("bundle re-provision on renewal failed: %s", _be)
        logger.info("🔁 Nidaan sub RENEWED: account=%s plan=%s +%sd", nidaan_account_id, plan, period_days)
        return True

    # ── FIRST ACTIVATION ───────────────────────────────────────────────────────
    sub_id = await create_subscription(
        account_id=nidaan_account_id,
        plan=plan,
        amount_paid=amount_paise // 100,
        razorpay_subscription_id=razorpay_sub_id,
        period_days=period_days,
    )
    logger.info("✅ Nidaan sub activated: account=%d plan=%s sub_id=%d", nidaan_account_id, plan, sub_id)

    if PLAN_LIMITS.get(plan, {}).get("sarathi_bundle"):
        await _provision_sarathi_bundle(nidaan_account_id, plan, period_days)

    # Unified ledger (webhook is the durable fallback if the checkout path missed it; dedup-safe).
    try:
        await record_payment(
            source="subscription", total_paise=int(amount_paise or 0),
            dedup_key=(razorpay_payment_id or f"subactivate:{razorpay_sub_id}"),
            razorpay_payment_id=(razorpay_payment_id or ""), razorpay_subscription_id=razorpay_sub_id,
            account_id=nidaan_account_id, plan=plan, base_paise=int(_base_rs * 100),
            verified=True, verify_method="webhook", note="subscription activation")
    except Exception as _pe:
        logger.warning("record_payment (activation) failed: %s", _pe)

    # GST ledger: record tax for this charge (base from plan config; no-op if off).
    try:
        await record_gst(razorpay_sub_id, "subscription_recurring", _base_rs,
                         account_id=nidaan_account_id)
    except Exception as _ge:
        logger.warning("record_gst (activation) failed: %s", _ge)

    return True


async def cancel_nidaan_subscription(account_id: int) -> bool:
    """Mark all active subscriptions for an account as cancelled."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_subscriptions SET status='cancelled', cancelled_at=CURRENT_TIMESTAMP "
            "WHERE account_id=? AND status='active'",
            (account_id,),
        )
        await conn.commit()
    logger.info("Nidaan sub cancelled: account=%d", account_id)
    return True


# =============================================================================
#  DPDP — Right-to-erasure (user-requested account deletion)
# =============================================================================
def _deletion_grace_days() -> int:
    try:
        return max(0, int(os.getenv("NIDAAN_DELETION_GRACE_DAYS", "7")))
    except ValueError:
        return 7


async def request_account_deletion(account_id: int) -> dict:
    """DPDP right-to-erasure: the user asks to delete their account. Billing stops
    IMMEDIATELY (Razorpay subscription cancelled + local record + Sarathi bundle
    torn down); the account is soft-deleted ('deletion_pending') with a grace
    window for undo. A scheduled sweep hard-purges the PII after the grace."""
    sub = await get_active_subscription(account_id)
    rzp_sub = (sub or {}).get("razorpay_subscription_id", "") or ""
    if rzp_sub.startswith("sub_"):
        try:
            import httpx
            # Nidaan's own Razorpay account (falls back to shared keys until configured)
            kid = os.getenv("NIDAAN_RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_KEY_ID", "")
            ksec = os.getenv("NIDAAN_RAZORPAY_KEY_SECRET") or os.getenv("RAZORPAY_KEY_SECRET", "")
            if kid and ksec:
                async with httpx.AsyncClient() as c:
                    await c.post(f"https://api.razorpay.com/v1/subscriptions/{rzp_sub}/cancel",
                                 auth=(kid, ksec), json={"cancel_at_cycle_end": 0}, timeout=20)
        except Exception as e:
            logger.warning("Razorpay cancel during deletion failed (acct %d): %s", account_id, e)
    await cancel_nidaan_subscription(account_id)
    try:
        await apply_bundle_teardown(account_id, reason="account_deleted", grace_days=0)
    except Exception:
        pass
    grace = _deletion_grace_days()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_accounts SET status='deletion_pending', deletion_requested_at=CURRENT_TIMESTAMP "
            "WHERE account_id=? AND deleted_at IS NULL", (account_id,))
        await conn.commit()
    from datetime import datetime as _dt
    purge_on = (_dt.utcnow() + timedelta(days=grace)).strftime("%d %b %Y")
    logger.info("Account deletion requested: account=%d purge_on=%s", account_id, purge_on)
    return {"status": "deletion_pending", "purge_on": purge_on, "grace_days": grace}


async def cancel_account_deletion(account_id: int) -> bool:
    """Undo a pending deletion within the grace window (re-activate the account)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_accounts SET status='active', deletion_requested_at=NULL "
            "WHERE account_id=? AND status='deletion_pending' AND deleted_at IS NULL", (account_id,))
        await conn.commit()
        return cur.rowcount > 0


async def execute_account_erasure(account_id: int) -> dict:
    """Hard purge: delete the account's documents + all PII rows, anonymise the
    account row. KEEPS nidaan_subscriptions (financial record) — those reference
    only account_id, which now points at an anonymised shell."""
    from pathlib import Path as _Path
    async with aiosqlite.connect(DB_PATH) as conn:
        claim_ids = [r[0] for r in await (await conn.execute(
            "SELECT claim_id FROM nidaan_claims WHERE account_id=?", (account_id,))).fetchall()]
        doc_names = [r[0] for r in await (await conn.execute(
            "SELECT stored_name FROM nidaan_claim_documents WHERE account_id=?", (account_id,))).fetchall()]
    docs_dir = _Path(__file__).parent / "uploads" / "nidaan-docs"
    files_deleted = 0
    for n in doc_names:
        try:
            (docs_dir / n).unlink(missing_ok=True); files_deleted += 1
        except Exception:
            pass
    async with aiosqlite.connect(DB_PATH) as conn:
        for cid in claim_ids:
            for t in ("nidaan_claim_documents", "nidaan_claim_doc_checklist", "nidaan_claim_notes",
                      "nidaan_claim_status_log", "nidaan_tasks", "nidaan_notifications"):
                try:
                    await conn.execute(f"DELETE FROM {t} WHERE claim_id=?", (cid,))
                except Exception:
                    pass
        # account-level PII rows
        await conn.execute("DELETE FROM nidaan_claim_documents WHERE account_id=?", (account_id,))
        await conn.execute("DELETE FROM nidaan_subscriber_prefs WHERE account_id=?", (account_id,))
        try:
            await conn.execute("DELETE FROM nidaan_notifications WHERE recipient_type='subscriber' AND recipient_id=?", (account_id,))
        except Exception:
            pass
        await conn.execute("DELETE FROM nidaan_claims WHERE account_id=?", (account_id,))
        # anonymise the account (row kept for FK integrity with retained billing records)
        await conn.execute(
            "UPDATE nidaan_accounts SET owner_name='[deleted]', firm_name=NULL, "
            "email='deleted_'||account_id||'@deleted.invalid', phone='', password_hash=NULL, "
            "google_sub=NULL, notes=NULL, status='deleted', deleted_at=CURRENT_TIMESTAMP "
            "WHERE account_id=?", (account_id,))
        await conn.commit()
    logger.info("Account ERASED: account=%d (%d files, %d claims)", account_id, files_deleted, len(claim_ids))
    return {"erased": True, "files_deleted": files_deleted, "claims_deleted": len(claim_ids)}


async def run_account_erasure_sweep() -> int:
    """Daily: hard-purge accounts whose deletion grace window has elapsed."""
    grace = _deletion_grace_days()
    async with aiosqlite.connect(DB_PATH) as conn:
        due = [r[0] for r in await (await conn.execute(
            "SELECT account_id FROM nidaan_accounts WHERE status='deletion_pending' "
            "AND deleted_at IS NULL AND deletion_requested_at <= datetime('now', ?)",
            (f"-{grace} days",))).fetchall()]
    n = 0
    for aid in due:
        try:
            await execute_account_erasure(aid); n += 1
        except Exception as e:
            logger.warning("account erasure failed for %d: %s", aid, e)
    if n:
        logger.info("Account erasure sweep: %d account(s) purged", n)
    return n


# =============================================================================
#  B3 — BUNDLE TEARDOWN (one helper called from every Nidaan-cancel path)
# =============================================================================

async def apply_bundle_teardown(account_id: int,
                                 reason: str = "nidaan_cancelled",
                                 grace_days: int = 5) -> Optional[int]:
    """When a Nidaan subscription ends (cancel or refund), shorten the linked
    Sarathi tenant's `bundled_until` to today + grace_days. Idempotent: only
    shortens, never extends. Also marks `lifetime_trial_used=1` so the
    ex-bundle user can't restart a Sarathi free trial.

    Returns the affected Sarathi tenant_id (or None if no link / already
    shorter).
    """
    sarathi_tid = await get_sarathi_tenant_for_nidaan(account_id)
    if not sarathi_tid:
        return None
    grace_until = (date.today() + timedelta(days=int(grace_days))).isoformat()
    # Shorten the linked Sarathi tenant via the platform boundary.
    #   None  → tenant row missing;  False → skipped (already ≤ grace);  True → updated.
    res = await bridge.shorten_bundle_tenant(tenant_id=sarathi_tid, grace_until=grace_until)
    if res is None:
        return None
    if res:
        logger.info("Bundle teardown: tenant=%d → bundled_until=%s reason=%s",
                    sarathi_tid, grace_until, reason)
    return sarathi_tid


async def find_bundles_ending_in(days_from_now: int) -> list[dict]:
    """Scheduler source for T-4 / T-2 / T-0 nudges. Returns tenants whose
    bundled_until matches today + N days exactly (so each day's run hits a
    fresh cohort, no duplicates without external bookkeeping).
    """
    target = (date.today() + timedelta(days=int(days_from_now))).isoformat()
    # Query Sarathi's bundle tenants via the platform boundary.
    return await bridge.find_bundle_tenants_ending_on(target)


# =============================================================================
#  REFUNDS — Policy A: full refund if cancelled within 7 days AND zero claims
# =============================================================================

REFUND_WINDOW_DAYS = 7  # cancel within N days of subscription start
REFUND_REQUIRE_ZERO_USAGE = True  # only refund if account has filed no claims


async def _count_account_claims(account_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM nidaan_claims WHERE account_id=?", (account_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def check_refund_eligibility(sub_id: int) -> tuple[bool, str, dict]:
    """Return (eligible, reason, sub_dict). Policy A:
    - Subscription must exist and not already have a refund row.
    - Cancellation (or `now` if not yet cancelled) within REFUND_WINDOW_DAYS of started_at.
    - Account has filed zero claims.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_subscriptions WHERE sub_id=?", (sub_id,))).fetchone()
        if not row:
            return False, "subscription_not_found", {}
        sub = dict(row)
        existing = await (await conn.execute(
            "SELECT refund_id, status FROM nidaan_refunds WHERE sub_id=? "
            "AND status IN ('pending','processing','processed') LIMIT 1",
            (sub_id,))).fetchone()
        if existing:
            return False, f"refund_already_{existing['status']}", sub

    started = sub.get("started_at") or ""
    try:
        started_dt = datetime.fromisoformat(started.replace("Z", "").replace(" ", "T")[:19])
    except Exception:
        return False, "bad_started_at", sub
    age_days = (datetime.utcnow() - started_dt).days
    if age_days > REFUND_WINDOW_DAYS:
        return False, f"outside_window_{age_days}d", sub

    if REFUND_REQUIRE_ZERO_USAGE:
        claims = await _count_account_claims(sub["account_id"])
        if claims > 0:
            return False, f"has_{claims}_claims", sub

    return True, "eligible", sub


async def create_refund_row(
    sub_id: int,
    account_id: int,
    amount: int,
    razorpay_order_id: str = "",
    razorpay_payment_id: str = "",
    reason: str = "",
    requested_by_staff_id: Optional[int] = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_refunds
               (sub_id, account_id, amount, razorpay_order_id, razorpay_payment_id,
                reason, requested_by_staff_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sub_id, account_id, amount, razorpay_order_id, razorpay_payment_id,
             reason, requested_by_staff_id))
        await conn.commit()
        return cur.lastrowid


async def update_refund_status(refund_id: int, status: str, **fields) -> None:
    sets = ["status=?"]
    vals: list = [status]
    for k, v in fields.items():
        if k in ("razorpay_refund_id", "last_error", "razorpay_payment_id"):
            sets.append(f"{k}=?")
            vals.append(v)
    if status in ("processed", "failed"):
        sets.append("processed_at=CURRENT_TIMESTAMP")
    vals.append(refund_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE nidaan_refunds SET {', '.join(sets)} WHERE refund_id=?", vals)
        await conn.commit()


async def get_refund(refund_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_refunds WHERE refund_id=?", (refund_id,))).fetchone()
        return dict(row) if row else None


async def list_refunds(status: Optional[str] = None, limit: int = 200) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if status:
            cur = await conn.execute(
                "SELECT r.*, a.email AS account_email, a.owner_name "
                "FROM nidaan_refunds r LEFT JOIN nidaan_accounts a ON a.account_id=r.account_id "
                "WHERE r.status=? ORDER BY r.requested_at DESC LIMIT ?", (status, limit))
        else:
            cur = await conn.execute(
                "SELECT r.*, a.email AS account_email, a.owner_name "
                "FROM nidaan_refunds r LEFT JOIN nidaan_accounts a ON a.account_id=r.account_id "
                "ORDER BY r.requested_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]


async def find_payment_id_via_razorpay(order_id: str, rzp_key_id: str, rzp_secret: str) -> str:
    """Resolve the actual payment_id from a Razorpay order_id (used when our DB
    column is missing the payment_id — legacy rows before this refactor).
    """
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.razorpay.com/v1/orders/{order_id}/payments",
                auth=(rzp_key_id, rzp_secret), timeout=15.0)
            if r.status_code != 200:
                logger.warning("Razorpay orders/payments lookup failed: %s %s",
                               r.status_code, r.text[:200])
                return ""
            data = r.json()
            items = data.get("items", [])
            captured = [p for p in items if p.get("status") == "captured"]
            if captured:
                return captured[0].get("id", "")
            if items:
                return items[0].get("id", "")
    except Exception as e:
        logger.error("Razorpay payment lookup error for %s: %s", order_id, e)
    return ""


async def issue_razorpay_refund(payment_id: str, amount_paise: int,
                                 rzp_key_id: str, rzp_secret: str,
                                 notes: Optional[dict] = None) -> dict:
    """Call Razorpay POST /payments/{id}/refund. Returns dict with 'ok', 'refund_id', 'error'."""
    import httpx as _httpx
    body = {"amount": amount_paise, "speed": "normal"}
    if notes:
        body["notes"] = notes
    try:
        async with _httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
                auth=(rzp_key_id, rzp_secret),
                json=body, timeout=30.0)
        if r.status_code in (200, 201):
            d = r.json()
            return {"ok": True, "refund_id": d.get("id", ""), "status": d.get("status", "")}
        err = r.text[:500]
        logger.error("Razorpay refund failed payment=%s status=%s body=%s",
                     payment_id, r.status_code, err)
        return {"ok": False, "error": f"HTTP {r.status_code}: {err}"}
    except Exception as e:
        logger.exception("Razorpay refund exception payment=%s", payment_id)
        return {"ok": False, "error": str(e)}


async def find_eligible_unrefunded_cancellations(days: int = 30) -> list[dict]:
    """Nightly job source: cancelled subs in last N days that are policy-eligible
    but have no refund row (or refund row failed) — staff review queue."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT s.*, a.email AS account_email, a.owner_name,
                      (SELECT COUNT(*) FROM nidaan_claims c WHERE c.account_id=s.account_id) AS claim_count,
                      (SELECT status FROM nidaan_refunds r WHERE r.sub_id=s.sub_id
                          ORDER BY r.requested_at DESC LIMIT 1) AS last_refund_status
               FROM nidaan_subscriptions s
               LEFT JOIN nidaan_accounts a ON a.account_id=s.account_id
               WHERE s.status='cancelled'
                 AND s.started_at >= datetime('now', ?)
               ORDER BY s.started_at DESC""",
            (f'-{int(days)} days',))
        rows = [dict(r) for r in await cur.fetchall()]

    eligible = []
    for r in rows:
        if r.get("claim_count", 0) > 0:
            continue
        if r.get("last_refund_status") in ("processed", "processing", "pending"):
            continue
        try:
            started_dt = datetime.fromisoformat(
                str(r["started_at"]).replace("Z", "").replace(" ", "T")[:19])
        except Exception:
            continue
        if (datetime.utcnow() - started_dt).days <= REFUND_WINDOW_DAYS:
            eligible.append(r)
    return eligible


async def update_account_profile(account_id: int, owner_name: str = None,
                                  firm_name: str = None, phone: str = None,
                                  email: str = None) -> bool:
    """Update mutable profile fields on a Nidaan account. Email is UNIQUE — a clash is reported
    via ValueError so the caller can surface a clean message."""
    fields, vals = [], []
    if owner_name is not None:
        fields.append("owner_name=?"); vals.append(owner_name)
    if firm_name is not None:
        fields.append("firm_name=?"); vals.append(firm_name)
    if phone is not None:
        fields.append("phone=?"); vals.append(phone)
    if email is not None:
        fields.append("email=?"); vals.append((email or "").strip().lower() or None)
    if not fields:
        return False
    vals.append(account_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute(
                f"UPDATE nidaan_accounts SET {', '.join(fields)} WHERE account_id=?", vals
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            raise ValueError("That email is already used by another account.")
    return True


async def update_claim_info(claim_id: int, *, insured_name=None, insured_phone=None,
                            insured_email=None, claim_type=None, insurer_name=None,
                            policy_no=None, disputed_amount=None) -> bool:
    """Super-admin/admin edit of a claim's core details (name/phone/email/type/insurer/policy/
    disputed amount). Only the provided fields are changed. Names are stored uppercase."""
    fields, vals = [], []
    if insured_name is not None:
        fields.append("insured_name=?"); vals.append(_capname(insured_name))
    if insured_phone is not None:
        fields.append("insured_phone=?"); vals.append((insured_phone or "").strip())
    if insured_email is not None:
        fields.append("insured_email=?"); vals.append((insured_email or "").strip().lower())
    if claim_type is not None:
        fields.append("claim_type=?"); vals.append((claim_type or "").strip())
    if insurer_name is not None:
        fields.append("insurer_name=?"); vals.append((insurer_name or "").strip())
    if policy_no is not None:
        fields.append("policy_no=?"); vals.append((policy_no or "").strip())
    if disputed_amount is not None:
        try:
            vals.append(int(disputed_amount) if disputed_amount != "" else None)
            fields.append("disputed_amount=?")
        except (TypeError, ValueError):
            pass
    if not fields:
        return False
    vals.append(claim_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            f"UPDATE nidaan_claims SET {', '.join(fields)} WHERE claim_id=?", vals)
        await conn.commit()
        return cur.rowcount > 0


# =============================================================================
#  STAFF AUTH & MANAGEMENT  (super_admin / sub_super_admin / team_member)
# =============================================================================

STAFF_ROLES = ("super_admin", "sub_super_admin", "team_member")
STAFF_ROLE_RANK = {"team_member": 0, "sub_super_admin": 1, "super_admin": 2}
_STAFF_JWT_SUFFIX = ":nidaan_staff"


def role_rank(role: str) -> int:
    return STAFF_ROLE_RANK.get(role or "", 0)


def normalize_indian_mobile(p: str) -> Optional[str]:
    """Return a clean 10-digit Indian mobile, or None if invalid. Strips a
    recognised +91 / 0 prefix but never truncates an arbitrary long number
    (a malformed entry must be rejected, not silently mangled)."""
    digits = "".join(ch for ch in str(p or "") if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return None


# ── Ops settings (key-value office policy) ───────────────────────────────────
OPS_SETTING_DEFAULTS = {
    # Minimum role permitted to create a DIRECT assignment. Lower roles can
    # still raise an upward "request". Default 'team_member' = everyone creates.
    "task_create_min_role": "team_member",
    # ── Branch billing (Item 3) — super-admin editable, NOT hardcoded ──────
    # Fee (in ₹) a branch pays to move a claim to Level-2 legal.
    "branch_l2_fee": "499",
    # When to charge a branch: 'l2_only' (only when a claim is GO-to-L2),
    # 'all_claims' (every branch claim), or 'free' (never charge).
    "branch_charge_policy": "l2_only",
    # ── Tiered review fee (Item #4) — super-admin editable ──────────────────
    # Review fee is `review_fee_low` for disputes ≤ `review_fee_threshold`, else
    # `review_fee_high`. The paid fee is recorded on the claim and adjusted toward
    # legal fees if the review outcome is GO. All in ₹.
    "review_fee_low": "499",
    "review_fee_high": "2000",
    "review_fee_threshold": "1000000",   # ₹10 lakh
    # ── GST — super-admin editable; OFF until registration lands ────────────
    # gst_enabled: "0"|"1" master switch. gst_rate: % added on top (exclusive).
    # gst_home_state: our registered state — when set, intra-state = CGST+SGST,
    # else IGST; blank = collect flat GST + store customer state for later split.
    "gst_enabled": "0",
    "gst_rate": "18",
    "gst_home_state": "",
    # ── Claimant success fee (Nidaan The Legal Consultant) — super-admin editable ─
    # % of the amount RECOVERED from the insurer that we retain as our fee. Shown to the
    # claimant in the L2 consent card (dispute vs recovered, fee, + GST per gst_config)
    # and SNAPSHOT onto nidaan_claimant_portal at the moment of digital acceptance, so a
    # later % change never rewrites an already-accepted agreement (grandfathered).
    # ⚠️ The T&C wording itself is founder/counsel-owned (claimant_terms_version bumps it).
    "claimant_success_fee_pct": "15",
    "claimant_terms_version": "v1",
    # Master switch for AUTO-emailing the claimant their portal link when a claim reaches L2.
    # Default OFF — staff can still issue/copy/email a link manually; flip to "1" only when the
    # founder is happy to auto-contact real policyholders.
    "claimant_autosend_enabled": "0",
    # Phase 3 GATE: when ON (default), the AUTOMATIC push to ClaimShield waits until the claimant
    # has digitally ACCEPTED the success-fee authorization. The manual "Send to ClaimShield" button
    # always works regardless (ops override). Flip to "0" to let paid + reviewed-GO claims auto-send
    # without waiting for acceptance (the pre-Phase-3 behaviour).
    "claimshield_require_acceptance": "1",
    # MASTER switch for ClaimShield (L2 legal) routing. "0" = PAUSED — L2 claims stay in
    # NidaanPartner (no auto-send, and the manual push is refused). Set OFF Aug 2026 while the
    # robust in-house L2 doc-collection model is built; flip ON in Workflow Settings to resume.
    "claimshield_routing_enabled": "1",
    # Claimant WhatsApp doc-collection — DASHBOARD DEFAULTS (a claim can override each; claim
    # level wins when set). Times are IST 24h. cadence_hours = gap between reminders.
    "wa_doc_collection_enabled": "0",   # master switch (off until the Meta number is live)
    "wa_reminder_hour_ist": "11",       # send the daily nudge at ~11am IST
    "wa_cadence_hours": "24",           # once a day
    "wa_quiet_start_ist": "21",         # no sends 9pm…
    "wa_quiet_end_ist": "8",            # …until 8am
    "wa_escalate_days": "4",            # no progress this many days → escalate to subscriber+staff
    "wa_default_language": "hinglish",  # hinglish | hi | en
    "wa_lead_capture_enabled": "1",     # auto-record inbound unknown WhatsApp numbers as CRM leads
    "wa_journey_enabled": "1",          # live complainant journey (claim/payment WhatsApp alerts) master switch
    # T&C shown in the claimant consent card, in BOTH languages (Hindi-default audience). The
    # contracting entity is "Nidaan The Legal Consultant LLP" (the legal firm) — the success fee is
    # the LLP's and is SEPARATE from NidaanPartner.com (the platform/mediator). Super-admin/counsel
    # owned: edit in ops Content; bump claimant_terms_version on any change so old acceptances stay
    # pinned to the version agreed. Plain text / simple HTML.
    "claimant_terms_html": (
        "This engagement is between you (the policyholder / claimant) and Nidaan The Legal "
        "Consultant LLP (\"the Firm\"). The Firm will assist you in pursuing and, where possible, "
        "recovering your insurance claim.\n\n"
        "Fee: The Firm works purely on a success basis. A professional fee of 15% of the amount "
        "actually recovered from the insurer/authority, plus applicable GST, is payable to Nidaan "
        "The Legal Consultant LLP only upon successful recovery. If nothing is recovered, no fee is "
        "payable.\n\n"
        "This fee is payable to Nidaan The Legal Consultant LLP and is separate from any "
        "subscription or service of NidaanPartner.com.\n\n"
        "By accepting, you authorise the Firm to act on your behalf in this claim and confirm the "
        "details provided are correct. You may withdraw by written notice; fees already earned on "
        "amounts already recovered remain payable. This acceptance is recorded digitally with date "
        "and time."),
    "claimant_terms_html_hi": (
        "यह अनुबंध आपके (पॉलिसीधारक / दावेदार) और Nidaan The Legal Consultant LLP (\"फर्म\") के बीच है। "
        "फर्म आपके बीमा दावे को आगे बढ़ाने और, जहाँ संभव हो, वसूल कराने में आपकी सहायता करेगी।\n\n"
        "फीस: फर्म पूरी तरह सफलता के आधार पर काम करती है। बीमा कंपनी/प्राधिकरण से वास्तव में वसूल की गई "
        "राशि का 15% पेशेवर शुल्क, साथ में लागू GST, केवल सफल वसूली पर Nidaan The Legal Consultant LLP को "
        "देय होगा। यदि कुछ भी वसूल नहीं होता, तो कोई फीस देय नहीं है।\n\n"
        "यह फीस Nidaan The Legal Consultant LLP को देय है और NidaanPartner.com की किसी सदस्यता या सेवा से "
        "अलग है।\n\n"
        "स्वीकार करके, आप फर्म को इस दावे में अपनी ओर से कार्य करने के लिए अधिकृत करते हैं और पुष्टि करते हैं "
        "कि दी गई जानकारी सही है। आप लिखित सूचना देकर वापस ले सकते हैं; पहले वसूल हुई राशि पर अर्जित फीस देय "
        "रहेगी। यह स्वीकृति दिनांक व समय के साथ डिजिटल रूप से दर्ज की जाती है।"),
}


async def gst_config() -> dict:
    """Current GST config (super-admin editable). enabled=False → no GST anywhere."""
    enabled = (await get_ops_setting("gst_enabled", "0") or "0") == "1"
    try:
        rate = float(await get_ops_setting("gst_rate", "18") or "18")
    except (TypeError, ValueError):
        rate = 18.0
    home_state = (await get_ops_setting("gst_home_state", "") or "").strip()
    return {"enabled": enabled, "rate": rate, "home_state": home_state}


async def charge_with_gst(base_rupees: float, customer_state: str = "") -> dict:
    """Compute what to actually charge for a base fee, applying GST-exclusive on top when
    GST is enabled. Returns {total_paise, base, gst, total, breakup|None, enabled, rate}.
    When GST is off, total == base (fully backward-compatible)."""
    cfg = await gst_config()
    base = round(float(base_rupees or 0), 2)
    if not cfg["enabled"]:
        return {"total_paise": int(round(base * 100)), "base": base, "gst": 0.0,
                "total": base, "breakup": None, "enabled": False, "rate": 0.0}
    bk = gst_breakup(base, cfg["rate"], cfg["home_state"], customer_state)
    return {"total_paise": int(round(bk["total"] * 100)), "base": bk["base"], "gst": bk["gst"],
            "total": bk["total"], "breakup": bk, "enabled": True, "rate": cfg["rate"]}


async def record_gst(razorpay_payment_id: str, purpose: str, base_rupees: float,
                     customer_state: str = "", claim_id=None, account_id=None) -> None:
    """Write a GST ledger row for a paid transaction (idempotent per payment_id).
    Recomputes the breakup from current config so it matches what was charged."""
    cfg = await gst_config()
    if not cfg["enabled"]:
        return
    bk = gst_breakup(base_rupees, cfg["rate"], cfg["home_state"], customer_state)
    async with aiosqlite.connect(DB_PATH) as conn:
        if razorpay_payment_id:
            ex = await (await conn.execute(
                "SELECT 1 FROM nidaan_gst_ledger WHERE razorpay_payment_id=?",
                (razorpay_payment_id,))).fetchone()
            if ex:
                return
        await conn.execute(
            """INSERT INTO nidaan_gst_ledger
               (razorpay_payment_id, purpose, claim_id, account_id, base_amount, gst_amount,
                total_amount, cgst, sgst, igst, gst_rate, customer_state)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (razorpay_payment_id or "", purpose, claim_id, account_id, bk["base"], bk["gst"],
             bk["total"], bk["cgst"], bk["sgst"], bk["igst"], bk["rate"], customer_state or ""))
        await conn.commit()


async def record_payment(*, source: str, total_paise: int, dedup_key: str = "",
                         gateway: str = "razorpay", razorpay_payment_id: str = "",
                         razorpay_order_id: str = "", razorpay_subscription_id: str = "",
                         account_id=None, claim_id=None, branch_code: str = "", plan: str = "",
                         base_paise: int = 0, gst_paise: int = 0, verified: bool = False,
                         verify_method: str = "", status: str = "captured",
                         actor_id: str = "", actor_name: str = "", channel: str = "",
                         ref_code: str = "", note: str = "") -> bool:
    """Single source of truth for EVERY successful payment, whatever the source.

    Idempotent on dedup_key (defaults to razorpay_payment_id; callers with no gateway id
    MUST pass a stable synthetic dedup_key so retries/webhooks don't double-count). Returns
    True if a new ledger row was written, False if this payment was already recorded.

    Safe/additive: never raises into the caller's payment flow — a ledger hiccup must not
    break activation. base/gst are best-effort; if only total is known they can be 0."""
    try:
        _key = (dedup_key or razorpay_payment_id or "").strip()
        if not _key:
            # No gateway id and no explicit key → synthesize a stable one so we still
            # record, but flag it (helps reconciliation catch missing keys).
            _key = f"{source}:{gateway}:{account_id}:{claim_id}:{plan}:{int(total_paise)}"
        if base_paise and not gst_paise:
            gst_paise = max(0, int(total_paise) - int(base_paise))
        elif not base_paise and not gst_paise:
            base_paise = int(total_paise)  # unknown split → treat total as base
        async with aiosqlite.connect(DB_PATH) as conn:
            ex = await (await conn.execute(
                "SELECT 1 FROM nidaan_payments WHERE dedup_key=?", (_key,))).fetchone()
            if ex:
                return False
            await conn.execute(
                """INSERT INTO nidaan_payments
                   (dedup_key, source, gateway, razorpay_payment_id, razorpay_order_id,
                    razorpay_subscription_id, account_id, claim_id, branch_code, plan,
                    base_paise, gst_paise, total_paise, verified, verify_method, status,
                    actor_id, actor_name, channel, ref_code, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (_key, source, gateway, razorpay_payment_id or "", razorpay_order_id or "",
                 razorpay_subscription_id or "", account_id, claim_id, (branch_code or "").upper(),
                 plan or "", int(base_paise or 0), int(gst_paise or 0), int(total_paise or 0),
                 1 if verified else 0, verify_method or "", status or "captured",
                 actor_id or "", actor_name or "", channel or "", (ref_code or "").upper(), note or ""))
            await conn.commit()
        return True
    except Exception as e:
        try:
            print(f"[record_payment] WARN could not record {source} {dedup_key or razorpay_payment_id}: {e}")
        except Exception:
            pass
        return False


async def get_account_payments(account_id: int) -> list:
    """Full verified payment trail for one account (newest first) — for the account panel."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT * FROM nidaan_payments WHERE account_id=? ORDER BY created_at DESC""",
            (account_id,))).fetchall()
    return [dict(r) for r in rows]


async def get_claim_payments(claim_id: int) -> list:
    """Full payment trail for one claim (newest first) — for the claim panel."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT * FROM nidaan_payments WHERE claim_id=? ORDER BY created_at DESC""",
            (claim_id,))).fetchall()
    return [dict(r) for r in rows]


async def record_claim_activity(claim_id: int, kind: str, *, channel: str = "", direction: str = "",
                                actor: str = "", summary: str = "", meta: str = "") -> None:
    """Append one row to a claim's activity timeline (automation messages, customer responses,
    events). Never raises — a logging hiccup must not break the caller's flow."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                """INSERT INTO nidaan_claim_activity
                   (claim_id, kind, channel, direction, actor, summary, meta)
                   VALUES (?,?,?,?,?,?,?)""",
                (claim_id, kind, channel or "", direction or "", actor or "",
                 (summary or "")[:600], (meta or "")[:2000]))
            await conn.commit()
    except Exception as e:
        logger.warning("record_claim_activity failed claim=%s: %s", claim_id, e)


async def get_claim_activity(claim_id: int, limit: int = 200) -> list:
    """One chronological timeline for a claim — MERGES the explicit activity log, status changes,
    WhatsApp messages, and payments so the ops view shows everything that happened, newest first."""
    items = []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        for r in await (await conn.execute(
                "SELECT kind, channel, direction, actor, summary, meta, created_at "
                "FROM nidaan_claim_activity WHERE claim_id=? ORDER BY created_at DESC LIMIT ?",
                (claim_id, limit))).fetchall():
            d = dict(r); d["source"] = "activity"; items.append(d)
        for r in await (await conn.execute(
                "SELECT to_status, note, changed_by_type, changed_at FROM nidaan_claim_status_log "
                "WHERE claim_id=? ORDER BY changed_at DESC LIMIT ?", (claim_id, limit))).fetchall():
            items.append({"source": "status", "kind": "status", "channel": "system",
                          "actor": r["changed_by_type"] or "system",
                          "summary": (r["note"] or f"→ {r['to_status']}"), "created_at": r["changed_at"]})
        # WhatsApp messages (table may not exist on very old DBs — guard).
        try:
            for r in await (await conn.execute(
                    "SELECT direction, msg_type, template_name, body, status, created_at "
                    "FROM nidaan_wa_messages WHERE claim_id=? ORDER BY created_at DESC LIMIT ?",
                    (claim_id, limit))).fetchall():
                _b = r["body"] or (f"template: {r['template_name']}" if r["template_name"] else r["msg_type"])
                items.append({"source": "whatsapp", "kind": "wa_" + (r["direction"] or ""),
                              "channel": "whatsapp", "direction": r["direction"],
                              "actor": "claimant" if r["direction"] == "in" else "bot",
                              "summary": (_b or "")[:200], "created_at": r["created_at"]})
        except Exception:
            pass
        try:
            for r in await (await conn.execute(
                    "SELECT source, total_paise, verified, created_at FROM nidaan_payments "
                    "WHERE claim_id=? ORDER BY created_at DESC LIMIT ?", (claim_id, limit))).fetchall():
                items.append({"source": "payment", "kind": "payment", "channel": "system",
                              "actor": "system",
                              "summary": f"₹{int(r['total_paise'])/100:.2f} received ({r['source']})"
                                         + (" ✓" if r["verified"] else " · manual"),
                              "created_at": r["created_at"]})
        except Exception:
            pass
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return items[:limit]


async def get_payments_ledger(limit: int = 200, source: str = "", verified_only: bool = False) -> list:
    """Recent unified-ledger rows (newest first), for the super-admin Payments view."""
    q = "SELECT * FROM nidaan_payments"
    conds, args = [], []
    if source:
        conds.append("source=?"); args.append(source)
    if verified_only:
        conds.append("verified=1")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY created_at DESC LIMIT ?"; args.append(int(limit))
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(q, tuple(args))).fetchall()
    return [dict(r) for r in rows]


async def ledger_revenue_summary() -> dict:
    """Revenue rolled up from the unified ledger + a reconciliation against the legacy
    source-table formula, so the super-admin can SEE every rupee is tracked & consistent.
    Amounts in ₹. Refunded rows excluded from collected totals."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        by_source = [dict(r) for r in await (await conn.execute(
            """SELECT source, COUNT(*) n,
                      ROUND(SUM(total_paise)/100.0, 2) rupees,
                      SUM(verified) verified_n
               FROM nidaan_payments WHERE status!='refunded'
               GROUP BY source ORDER BY rupees DESC""")).fetchall()]
        led_total = (await (await conn.execute(
            "SELECT ROUND(COALESCE(SUM(total_paise),0)/100.0,2) FROM nidaan_payments "
            "WHERE status!='refunded'")).fetchone())[0]
        unverified = (await (await conn.execute(
            "SELECT ROUND(COALESCE(SUM(total_paise),0)/100.0,2) FROM nidaan_payments "
            "WHERE status!='refunded' AND verified=0")).fetchone())[0]
        # Legacy source-table formula (what the Revenue tab historically summed).
        legacy = (await (await conn.execute(
            """SELECT ROUND(
                 (SELECT COALESCE(SUM(amount_paid),0) FROM nidaan_subscriptions WHERE status IN ('active','cancelled'))
                +(SELECT COALESCE(SUM(amount_paid),0) FROM nidaan_per_claim_purchase WHERE status NOT IN ('failed','refunded','pending_payment'))
                +(SELECT COALESCE(SUM(amount_paise)/100.0,0) FROM nidaan_payment_links WHERE purpose='custom' AND status='paid')
               , 2)""")).fetchone())[0]
    return {
        "by_source": by_source,
        "ledger_total": led_total or 0,
        "unverified_total": unverified or 0,
        "legacy_total": legacy or 0,
        "reconciled": abs((led_total or 0) - (legacy or 0)) < 1.0,
        "delta": round((led_total or 0) - (legacy or 0), 2),
    }


def gst_breakup(base_rupees: float, rate: float, home_state: str = "", customer_state: str = "") -> dict:
    """GST-exclusive breakup: base + GST = total. If home_state is set and matches the
    customer's state → CGST+SGST (half each); else IGST. Amounts in ₹ (2-dp)."""
    base = round(float(base_rupees or 0), 2)
    gst = round(base * float(rate or 0) / 100.0, 2)
    total = round(base + gst, 2)
    intra = bool(home_state) and bool(customer_state) and \
        home_state.strip().lower() == customer_state.strip().lower()
    if intra:
        cgst = round(gst / 2, 2); sgst = round(gst - cgst, 2); igst = 0.0
    else:
        cgst = 0.0; sgst = 0.0; igst = gst
    return {"base": base, "gst": gst, "total": total,
            "cgst": cgst, "sgst": sgst, "igst": igst, "rate": float(rate or 0)}


async def review_fee_config() -> dict:
    """Current tiered review-fee config (super-admin editable)."""
    low = int((await get_ops_setting("review_fee_low", "499") or "499") or 499)
    high = int((await get_ops_setting("review_fee_high", "2000") or "2000") or 2000)
    threshold = int((await get_ops_setting("review_fee_threshold", "1000000") or "1000000") or 1000000)
    return {"low": low, "high": high, "threshold": threshold}


async def review_fee_for(disputed_amount: Optional[int]) -> int:
    """Review fee (₹) for a claim: high tier when disputed amount exceeds the threshold,
    else the low tier. Blank/unknown disputed amount → low tier."""
    cfg = await review_fee_config()
    try:
        amt = int(disputed_amount or 0)
    except (TypeError, ValueError):
        amt = 0
    return cfg["high"] if amt > cfg["threshold"] else cfg["low"]


async def get_ops_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT value FROM nidaan_ops_settings WHERE key=?", (key,))).fetchone()
        if row is not None:
            return row[0]
    return default if default is not None else OPS_SETTING_DEFAULTS.get(key)


async def get_all_ops_settings() -> dict:
    out = dict(OPS_SETTING_DEFAULTS)
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT key, value FROM nidaan_ops_settings")
        for k, v in await cur.fetchall():
            out[k] = v
    return out


async def set_ops_setting(key: str, value: str, updated_by: Optional[int] = None) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO nidaan_ops_settings (key, value, updated_by, updated_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP",
            (key, value, updated_by))
        await conn.commit()


# ── Our Offices (super-admin editable; shown on the homepage for BOTH advisor &
# policyholder views). Stored as a JSON list in the ops-settings KV. city is bilingual,
# addr is a single line (street addresses aren't translated). ──────────────────
DEFAULT_OFFICES = [
    {"city_en": "Indore — Registered Office", "city_hi": "इंदौर — पंजीकृत कार्यालय",
     "addr": "79-A, Dravid Nagar, Ranjit Hanuman Mandir Road, Indore – 452009"},
    {"city_en": "Indore — Office 2", "city_hi": "इंदौर — कार्यालय 2",
     "addr": "509, Girnar Plaza, MIG Square, Atal Dwar, Indore – 452010"},
    {"city_en": "Indore — Office 3 (Vijay Nagar)", "city_hi": "इंदौर — कार्यालय 3 (विजय नगर)",
     "addr": "401, Sanskar Apartment, Apollo Hospital Road, Scheme No. 54, Indore – 452010"},
    {"city_en": "Bhopal", "city_hi": "भोपाल",
     "addr": "244, BDA Complex – 7 No. Stop, Near SBI Bank, Shivaji Nagar, Bhopal – 462016"},
]


def _clean_office(o: dict) -> Optional[dict]:
    if not isinstance(o, dict):
        return None
    ce = (o.get("city_en") or "").strip()
    addr = (o.get("addr") or "").strip()
    if not ce and not addr:
        return None
    return {"city_en": ce[:120], "city_hi": (o.get("city_hi") or "").strip()[:120],
            "addr": addr[:300]}


async def get_offices() -> list[dict]:
    """The current office list — the saved custom list, or DEFAULT_OFFICES if never edited.
    An explicit empty saved list is respected (returns [])."""
    raw = await get_ops_setting("offices_json", "")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [c for c in (_clean_office(o) for o in data) if c]
        except Exception:
            pass
    return list(DEFAULT_OFFICES)


async def set_offices(offices: list, updated_by: Optional[int] = None) -> list[dict]:
    """Replace the whole office list (add/edit/delete via one save). Returns the cleaned list."""
    clean = [c for c in (_clean_office(o) for o in (offices or [])) if c]
    await set_ops_setting("offices_json", json.dumps(clean, ensure_ascii=False), updated_by)
    return clean


def _staff_jwt_secret() -> str:
    base = os.environ.get("JWT_SECRET", "change-me-in-production")
    return base + _STAFF_JWT_SUFFIX


def create_staff_token(staff_id: int, role: str, name: str,
                       imp_by_id=None, imp_by_name: str = "") -> str:
    import jwt as _jwt
    payload = {
        "sub": str(staff_id),
        "role": role,
        "name": name,
        "typ": "nidaan_staff",
        "iat": datetime.utcnow(),
    }
    # Staff-impersonation: keep the REAL super-admin on the token so their identity
    # can never be masked by the impersonated one (accountability for every action).
    if imp_by_id:
        payload["imp_by"] = {"id": int(imp_by_id), "name": (imp_by_name or "")[:80]}
    return _jwt.encode(payload, _staff_jwt_secret(), algorithm="HS256")


def verify_staff_token(token: str) -> Optional[dict]:
    """Return payload dict or None."""
    import jwt as _jwt
    try:
        payload = _jwt.decode(
            token,
            _staff_jwt_secret(),
            algorithms=["HS256"],
            options={"verify_sub": False},
        )
        if payload.get("typ") != "nidaan_staff":
            return None
        payload["staff_id"] = int(payload["sub"])
        return payload
    except Exception:
        return None


async def create_staff(
    name: str,
    email: str,
    password: str,
    role: str,
    phone: str = "",
    created_by: Optional[int] = None,
    notify_email: str = "",
) -> Optional[int]:
    """Create a staff account. Returns staff_id or None on duplicate email.
    phone is the internal notification number (WhatsApp + SMS routing).
    notify_email is the staffer's real/personal inbox for email notifications
    (login email may be @nidaanpartner.com without a real mailbox)."""
    if role not in STAFF_ROLES:
        raise ValueError(f"Invalid role: {role}")
    pw_hash = _hash_password(password)
    if (phone or "").strip():
        norm = normalize_indian_mobile(phone)
        if not norm:
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        phone = norm
    else:
        phone = ""
    notify_email = (notify_email or "").lower().strip()
    email = email.lower().strip()
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            # If this Login ID belongs to a SOFT-DELETED (archived) staffer,
            # reclaim that row as a fresh account — so recreating a deleted
            # staffer with the same Login ID works cleanly (the email UNIQUE
            # constraint would otherwise block it). An ACTIVE match is a real
            # duplicate → return None (409).
            existing = await (await conn.execute(
                "SELECT staff_id, deleted_at FROM nidaan_staff WHERE email=?",
                (email,))).fetchone()
            reclaimed_id = None
            if existing is not None:
                if existing["deleted_at"] is None:
                    return None  # active account already uses this Login ID
                sid = existing["staff_id"]
                await conn.execute(
                    "UPDATE nidaan_staff SET name=?, password_hash=?, role=?, "
                    "phone=?, notify_email=?, created_by=?, status='active', "
                    "deleted_at=NULL, last_login_at=NULL, saved_official_numbers_at=NULL, "
                    "created_at=CURRENT_TIMESTAMP WHERE staff_id=?",
                    (name, pw_hash, role, phone, notify_email, created_by, sid))
                await conn.commit()
                reclaimed_id = sid
            else:
                cur = await conn.execute(
                    """INSERT INTO nidaan_staff (name, email, password_hash, role, phone, notify_email, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, email, pw_hash, role, phone, notify_email, created_by),
                )
                await conn.commit()
                reclaimed_id = cur.lastrowid
        # Assign this staffer's personal referral code (own connection, after commit).
        await ensure_staff_referral_codes()
        return reclaimed_id
    except aiosqlite.IntegrityError:
        return None


async def authenticate_staff(email: str, password: str) -> Optional[dict]:
    """Return staff dict if credentials valid, else None."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_staff WHERE email=? AND status='active'",
            (email.lower().strip(),),
        )
        row = await cur.fetchone()
        if not row:
            return None
        staff = dict(row)
    if not _verify_password(password, staff.get("password_hash", "")):
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_staff SET last_login_at=CURRENT_TIMESTAMP WHERE staff_id=?",
            (staff["staff_id"],),
        )
        await conn.commit()
    return staff


async def set_staff_profile_pic(staff_id: int, stored_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE nidaan_staff SET profile_pic=? WHERE staff_id=?",
                           (stored_name, staff_id))
        await conn.commit()


async def get_staff_by_id(staff_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT staff_id,name,email,role,status,created_at,last_login_at,"
            "       phone,notify_email,saved_official_numbers_at,"
            "       comms_onboarded_at,telegram_chat_id,telegram_lang,profile_pic,"
            "       referral_code,commission_pct,COALESCE(telegram_access,1) AS telegram_access "
            "FROM nidaan_staff WHERE staff_id=?", (staff_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def mark_staff_saved_numbers(staff_id: int, phone: str = "") -> None:
    """Mark staff as having saved all 3 official numbers (gates first login modal)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        if phone:
            await conn.execute(
                "UPDATE nidaan_staff SET saved_official_numbers_at = CURRENT_TIMESTAMP, "
                "phone = ? WHERE staff_id = ?", (phone, staff_id))
        else:
            await conn.execute(
                "UPDATE nidaan_staff SET saved_official_numbers_at = CURRENT_TIMESTAMP "
                "WHERE staff_id = ?", (staff_id,))
        await conn.commit()


async def list_staff(include_inactive: bool = False) -> list[dict]:
    """Active roster (or active+inactive). Soft-deleted staff are never here —
    see list_deleted_staff() for the archive."""
    cols = ("staff_id,name,email,role,status,phone,notify_email,"
            "created_at,last_login_at,COALESCE(telegram_access,1) AS telegram_access")
    where = "deleted_at IS NULL" + ("" if include_inactive else " AND status='active'")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            f"SELECT {cols} FROM nidaan_staff WHERE {where} ORDER BY created_at DESC")
        return [dict(r) for r in await cur.fetchall()]


async def list_deleted_staff() -> list[dict]:
    """The archive — soft-deleted staff, restorable."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT staff_id,name,email,role,status,phone,notify_email,"
            "created_at,last_login_at,deleted_at "
            "FROM nidaan_staff WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")
        return [dict(r) for r in await cur.fetchall()]


async def _sever_staff_connections(conn, staff_id: int) -> None:
    """Cut every live link for an archived staffer so there is NO residual connection to
    either app: Telegram devices + legacy pointer + access flag, and web-push subscriptions.
    Combined with the status='active'/deleted_at filters on every notification + bot-auth
    query, this guarantees an archived staffer gets no notifications and can't use the bot."""
    for sql, args in (
        ("DELETE FROM nidaan_staff_telegram WHERE staff_id=?", (staff_id,)),
        ("UPDATE nidaan_staff SET telegram_chat_id=NULL, telegram_username=NULL, "
         "telegram_linked_at=NULL, telegram_access=0 WHERE staff_id=?", (staff_id,)),
        ("DELETE FROM nidaan_push_subscriptions WHERE staff_id=?", (staff_id,)),
    ):
        try:
            await conn.execute(sql, args)
        except Exception:
            pass   # optional tables/columns — never let cleanup block the archive


async def soft_delete_staff(staff_id: int) -> bool:
    """Archive a staffer (reversible). Super admins are protected. Also flips status to
    inactive so every existing status='active' query excludes them, and severs all
    Telegram/push connections (no notifications, no bot) — nothing lingers."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT role, deleted_at FROM nidaan_staff WHERE staff_id=?",
            (staff_id,))).fetchone()
        if not row:
            return False
        if row["role"] == "super_admin":
            raise ValueError("Super admins cannot be deleted")
        await conn.execute(
            "UPDATE nidaan_staff SET deleted_at=CURRENT_TIMESTAMP, status='inactive' "
            "WHERE staff_id=? AND deleted_at IS NULL", (staff_id,))
        await _sever_staff_connections(conn, staff_id)
        await conn.commit()
    return True


async def restore_staff(staff_id: int) -> bool:
    """Bring an archived staffer back (as inactive — admin re-activates explicitly)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_staff SET deleted_at=NULL, status='inactive' "
            "WHERE staff_id=? AND deleted_at IS NOT NULL", (staff_id,))
        await conn.commit()
    return True


async def delete_inactive_staff() -> int:
    """Bulk-archive every currently-inactive staffer except super admins, severing each
    one's Telegram/push connections too. Returns the number archived."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        ids = [r["staff_id"] for r in await (await conn.execute(
            "SELECT staff_id FROM nidaan_staff WHERE status='inactive' AND deleted_at IS NULL "
            "AND role != 'super_admin'")).fetchall()]
        for sid in ids:
            await conn.execute(
                "UPDATE nidaan_staff SET deleted_at=CURRENT_TIMESTAMP WHERE staff_id=?", (sid,))
            await _sever_staff_connections(conn, sid)
        await conn.commit()
        return len(ids)


async def update_staff(staff_id: int, name: str = None, role: str = None,
                       status: str = None, password: str = None,
                       phone: str = None, notify_email: str = None) -> bool:
    fields, vals = [], []
    if name is not None:
        fields.append("name=?"); vals.append(name)
    if role is not None:
        if role not in STAFF_ROLES:
            raise ValueError(f"Invalid role: {role}")
        fields.append("role=?"); vals.append(role)
    if status is not None:
        fields.append("status=?"); vals.append(status)
    if phone is not None:
        if (phone or "").strip():
            norm = normalize_indian_mobile(phone)
            if not norm:
                raise ValueError("Enter a valid 10-digit Indian mobile number")
            fields.append("phone=?"); vals.append(norm)
        else:
            fields.append("phone=?"); vals.append("")
    if notify_email is not None:
        fields.append("notify_email=?"); vals.append((notify_email or "").lower().strip())
    if password is not None:
        fields.append("password_hash=?"); vals.append(_hash_password(password))
    if not fields:
        return False
    vals.append(staff_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE nidaan_staff SET {', '.join(fields)} WHERE staff_id=?", vals
        )
        await conn.commit()
    return True


# =============================================================================
#  OPS: CLAIMS (with staff assignment & role-based filtering)
# =============================================================================

async def get_claims_ops(
    staff_id: int,
    role: str,
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
    claim_type: Optional[str] = None,
    search: Optional[str] = None,
    payment_status: Optional[str] = None,
    branch: Optional[str] = None,
    plan: Optional[str] = None,
    account_id: Optional[int] = None,
    review_outcome: Optional[str] = None,
    include_archived: bool = False,
    archived_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Fetch claims for ops portal. team_member sees only their assigned claims.
    Paid/subscription claims (active reviews with a running SLA) sort ABOVE
    unpaid leads — the review team works paid first; leads are the conversion
    pipeline. Filter payment_status='unpaid_lead' to see just the lead funnel."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        conditions = []
        params: list = []

        if role == "team_member":
            # primary OR additional assignee (grant-only)
            conditions.append("(c.assigned_to_staff_id=? OR EXISTS(SELECT 1 FROM "
                              "nidaan_claim_assignees ca WHERE ca.claim_id=c.claim_id AND ca.staff_id=?))")
            params.extend([staff_id, staff_id])
        elif assigned_to is not None:
            conditions.append("c.assigned_to_staff_id=?")
            params.append(assigned_to)

        # Manually-archived (test/garbage) claims are hidden from every working view by
        # default; the Archive view passes archived_only=True to see just them.
        if archived_only:
            conditions.append("COALESCE(c.archived,0)=1")
        elif not include_archived:
            conditions.append("COALESCE(c.archived,0)=0")
        if status:
            conditions.append("c.status=?")
            params.append(status)
        if review_outcome == "can_fight":
            # L2 bucket = every reviewed-GO claim still ACTIVE in the legal pipeline —
            # not just those parked at 'review_delivered'. Once a GO claim advances
            # (L2 paid → queued → assigned → in negotiation) it must STAY here until it
            # terminally closes, so branch/staff L2 claims track like retail. (Prev bug:
            # a paid+assigned branch L2 claim silently vanished from this bucket.)
            conditions.append(
                "c.review_outcome='can_fight' AND c.status NOT IN "
                "('closed','withdrawn','resolved_won','resolved_lost')")
        elif review_outcome:
            # Archived / other outcomes (e.g. no_scope) — as reviewed & delivered.
            conditions.append("c.review_outcome=? AND c.status='review_delivered'")
            params.append(review_outcome)
        if payment_status:
            conditions.append("c.payment_status=?")
            params.append(payment_status)
        if claim_type:
            conditions.append("c.claim_type=?")
            params.append(claim_type)
        if branch:
            # Branch-raised claims carry branch_code on the CLAIM (house account's is blank),
            # so match the claim's code first, then fall back to the account's.
            conditions.append("UPPER(COALESCE(NULLIF(c.branch_code,''), a.branch_code))=?")
            params.append(branch.strip().upper())
        if plan:
            conditions.append("sub.plan=?")
            params.append(plan)
        if account_id is not None:
            conditions.append("c.account_id=?")
            params.append(account_id)
        if search:
            conditions.append(
                "(c.insured_name LIKE ? OR c.insured_phone LIKE ? "
                "OR c.insurer_name LIKE ? OR c.policy_no LIKE ? "
                "OR a.owner_name LIKE ? OR a.firm_name LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like, like, like])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cur = await conn.execute(
            f"""SELECT c.*,
                    a.owner_name, a.firm_name, a.email AS advisor_email, a.phone AS advisor_phone,
                    COALESCE(NULLIF(c.branch_code,''), a.branch_code) AS branch_code,
                    sub.plan AS account_plan,
                    s.name AS assigned_staff_name,
                    rst.name AS ref_staff_name, rbr.name AS ref_branch_name,
                    COALESCE(NULLIF(c.branch_code,''), a.branch_code) AS ref_code,
                    (SELECT COUNT(*) FROM nidaan_followups f
                     WHERE f.claim_id = c.claim_id AND f.status = 'pending') AS pending_tasks,
                    (SELECT COUNT(*) FROM nidaan_claim_notes cn
                     WHERE cn.claim_id = c.claim_id AND cn.staff_id != ?
                       AND NOT EXISTS(SELECT 1 FROM nidaan_claim_note_reads r
                                      WHERE r.note_id = cn.note_id AND r.staff_id = ?)) AS unseen_notes,
                    cp.access_token AS portal_token, cp.activated_at AS portal_activated_at,
                    cp.consent_accepted_at AS consent_accepted_at, cp.consent_pushed_at AS consent_pushed_at,
                    CASE WHEN cp.claim_id IS NOT NULL THEN 1 ELSE 0 END AS portal_exists
               FROM nidaan_claims c
               JOIN nidaan_accounts a ON a.account_id = c.account_id
               LEFT JOIN nidaan_claimant_portal cp ON cp.claim_id = c.claim_id
               LEFT JOIN nidaan_subscriptions sub ON sub.account_id = a.account_id AND sub.status = 'active'
               LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id
               LEFT JOIN nidaan_staff rst ON UPPER(rst.referral_code)=UPPER(COALESCE(NULLIF(c.branch_code,''), a.branch_code))
                   AND COALESCE(NULLIF(c.branch_code,''), a.branch_code) <> ''
               LEFT JOIN nidaan_branches rbr ON UPPER(rbr.branch_code)=UPPER(COALESCE(NULLIF(c.branch_code,''), a.branch_code))
                   AND COALESCE(NULLIF(c.branch_code,''), a.branch_code) <> ''
               {where}
               ORDER BY c.created_at DESC, c.claim_id DESC
               LIMIT ? OFFSET ?""",
            [staff_id, staff_id] + params + [limit, offset],
        )
        rows = [dict(r) for r in await cur.fetchall()]
        # Resolve the attribution code → a human referrer (staff name / branch name), so the
        # L2 (and other) lists can show WHO brought/raised the claim, not just a code.
        for r in rows:
            if r.get("ref_staff_name"):
                r["ref_kind"], r["ref_name"] = "staff", r["ref_staff_name"]
            elif r.get("ref_branch_name"):
                r["ref_kind"], r["ref_name"] = "branch", r["ref_branch_name"]
            else:
                r["ref_kind"], r["ref_name"] = "", ""
            # Universal SOURCE label — how every claim came in + who's behind it (no blank trail).
            _origin = (r.get("origin") or "").strip()
            _pay = (r.get("payment_status") or "").strip()
            if r["ref_kind"] == "branch" or _origin == "branch":
                r["source_kind"] = "branch"
            elif r["ref_kind"] == "staff":
                r["source_kind"] = "staff"
            elif r.get("account_plan"):
                r["source_kind"] = "subscriber"
            elif _origin == "d2c_review" or _pay == "paid":
                r["source_kind"] = "review"
            else:
                r["source_kind"] = "direct"
            # Claimant portal + authorization trail (so the row shows it without opening the claim).
            r["portal_created"] = bool(r.get("portal_exists"))
            r["portal_opened"] = bool(r.get("portal_activated_at"))
            if r.get("consent_accepted_at"):
                r["authorization"] = "accepted"
            elif r.get("consent_pushed_at"):
                r["authorization"] = "pushed"
            elif r.get("portal_exists"):
                r["authorization"] = "portal_ready"
            else:
                r["authorization"] = "none"
        return rows


# ── Account de-duplication (detect + human-confirmed merge) ──────────────────
def _dedup_phone(p: str) -> str:
    d = "".join(ch for ch in (p or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else ""


def _dedup_email(e: str) -> str:
    e = (e or "").strip().lower()
    return e if "@" in e and "." in e else ""


def _dedup_name(n: str) -> str:
    import re as _re
    s = _re.sub(r'\b(mr|mrs|ms|dr|shri|smt|m/s|the)\b', ' ', (n or '').lower())
    return _re.sub(r'[^a-z0-9]+', ' ', s).strip()


async def find_duplicate_accounts(limit_groups: int = 100) -> list[dict]:
    """Groups of accounts that MIGHT be the same person. STRONG = a shared phone (last-10) or email;
    WEAK = same normalized name only (different phone & email). Never merges — only flags for review.
    Each account row carries claim_count + active plan so a human can judge which to keep."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        accts = [dict(r) for r in await (await conn.execute(
            "SELECT a.account_id, a.owner_name, a.firm_name, a.phone, a.email, a.branch_code, "
            "a.status, a.created_at, "
            "(SELECT COUNT(*) FROM nidaan_claims c WHERE c.account_id=a.account_id) AS claim_count, "
            "(SELECT s.plan FROM nidaan_subscriptions s "
            " WHERE s.account_id=a.account_id AND s.status='active' LIMIT 1) AS plan "
            "FROM nidaan_accounts a "
            "WHERE COALESCE(a.status,'') NOT IN ('merged','deleted')")).fetchall()]
    parent = {a["account_id"]: a["account_id"] for a in accts}

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(x, y):
        parent[_find(x)] = _find(y)

    phone_map, email_map = {}, {}
    for a in accts:
        aid = a["account_id"]
        ph, em = _dedup_phone(a["phone"]), _dedup_email(a["email"])
        if ph:
            if ph in phone_map:
                _union(aid, phone_map[ph])
            else:
                phone_map[ph] = aid
        if em:
            if em in email_map:
                _union(aid, email_map[em])
            else:
                email_map[em] = aid
    strong_groups, seen_strong = {}, set()
    for a in accts:
        strong_groups.setdefault(_find(a["account_id"]), []).append(a)
    out = []
    for members in strong_groups.values():
        if len(members) < 2:
            continue
        phones = [_dedup_phone(m["phone"]) for m in members if _dedup_phone(m["phone"])]
        emails = [_dedup_email(m["email"]) for m in members if _dedup_email(m["email"])]
        rs = []
        if any(phones.count(p) > 1 for p in set(phones)):
            rs.append("phone")
        if any(emails.count(e) > 1 for e in set(emails)):
            rs.append("email")
        out.append({"confidence": "strong", "reason": " + ".join(rs) or "phone/email",
                    "accounts": members})
        seen_strong.update(m["account_id"] for m in members)
    # Weak: same-name-only (accounts not already in a strong group).
    name_map = {}
    for a in accts:
        if a["account_id"] in seen_strong:
            continue
        nn = _dedup_name(a["owner_name"])
        if len(nn) >= 4:
            name_map.setdefault(nn, []).append(a)
    for members in name_map.values():
        if len(members) > 1:
            out.append({"confidence": "weak", "reason": "same name", "accounts": members})
    out.sort(key=lambda g: (0 if g["confidence"] == "strong" else 1, -len(g["accounts"])))
    return out[:limit_groups]


async def merge_accounts(keeper_id: int, duplicate_id: int) -> dict:
    """Human-confirmed merge: move the DUPLICATE's claims (+ ₹499 purchases) to the KEEPER and archive
    the duplicate (status='merged', merged_into=keeper). NEVER hard-deletes. Blocked if the duplicate
    has an active subscription (money-sensitive — handle those by hand). Returns {ok, moved_claims|error}."""
    if int(keeper_id) == int(duplicate_id):
        return {"ok": False, "error": "same_account"}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        k = await (await conn.execute(
            "SELECT account_id, status FROM nidaan_accounts WHERE account_id=?", (keeper_id,))).fetchone()
        d = await (await conn.execute(
            "SELECT account_id, status FROM nidaan_accounts WHERE account_id=?", (duplicate_id,))).fetchone()
        if not k or not d:
            return {"ok": False, "error": "not_found"}
        if (d["status"] or "") == "merged":
            return {"ok": False, "error": "already_merged"}
        dsub = await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_subscriptions WHERE account_id=? AND status='active'",
            (duplicate_id,))).fetchone()
        if dsub and dsub[0]:
            return {"ok": False, "error": "duplicate_has_active_subscription"}
        moved = (await conn.execute(
            "UPDATE nidaan_claims SET account_id=? WHERE account_id=?",
            (keeper_id, duplicate_id))).rowcount
        for _tbl in ("nidaan_per_claim_purchase",):
            try:
                await conn.execute(f"UPDATE {_tbl} SET account_id=? WHERE account_id=?",
                                   (keeper_id, duplicate_id))
            except Exception:
                pass
        await conn.execute(
            "UPDATE nidaan_accounts SET status='merged', merged_into=? WHERE account_id=?",
            (keeper_id, duplicate_id))
        await conn.commit()
    return {"ok": True, "moved_claims": moved}


async def assign_claim_to_staff(
    claim_id: int, staff_id: int, assigned_by_id: int, assigned_by_role: str
) -> bool:
    """Assign a claim to a staff member and log it."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT claim_id FROM nidaan_claims WHERE claim_id=?", (claim_id,)
        )
        if not await cur.fetchone():
            return False
        await conn.execute(
            "UPDATE nidaan_claims SET assigned_to_staff_id=?, status='assigned', "
            "last_status_at=CURRENT_TIMESTAMP WHERE claim_id=?",
            (staff_id, claim_id),
        )
        await conn.execute(
            """INSERT INTO nidaan_claim_status_log
               (claim_id, from_status, to_status, note, changed_by_type, changed_by_id)
               VALUES (?, NULL, 'assigned', 'Assigned to staff', ?, ?)""",
            (claim_id, assigned_by_role, assigned_by_id),
        )
        await conn.commit()
    return True


# ── Multi-assignee support (additive; assigned_to_staff_id stays the PRIMARY) ──
async def _ensure_claim_assignees_table(conn) -> None:
    await conn.execute("""CREATE TABLE IF NOT EXISTS nidaan_claim_assignees (
        claim_id INTEGER NOT NULL, staff_id INTEGER NOT NULL,
        assigned_by INTEGER, assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(claim_id, staff_id))""")


async def set_claim_assignees(claim_id: int, staff_ids: list[int],
                              assigned_by_id: int, assigned_by_role: str) -> bool:
    """Assign a claim to one or more staff. staff_ids[0] becomes the PRIMARY
    (assigned_to_staff_id — everything existing keeps working); ALL are recorded in
    nidaan_claim_assignees. Sets status='assigned' + logs. Returns True."""
    ids, seen = [], set()
    for s in staff_ids:
        try:
            s = int(s)
        except (TypeError, ValueError):
            continue
        if s and s not in seen:
            seen.add(s); ids.append(s)
    if not ids:
        return False
    async with aiosqlite.connect(DB_PATH) as conn:
        if not await (await conn.execute(
                "SELECT 1 FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone():
            return False
        await _ensure_claim_assignees_table(conn)
        await conn.execute(
            "UPDATE nidaan_claims SET assigned_to_staff_id=?, status='assigned', "
            "last_status_at=CURRENT_TIMESTAMP WHERE claim_id=?", (ids[0], claim_id))
        await conn.execute("DELETE FROM nidaan_claim_assignees WHERE claim_id=?", (claim_id,))
        for s in ids:
            await conn.execute(
                "INSERT OR IGNORE INTO nidaan_claim_assignees (claim_id, staff_id, assigned_by) "
                "VALUES (?,?,?)", (claim_id, s, assigned_by_id))
        await conn.execute(
            """INSERT INTO nidaan_claim_status_log
               (claim_id, from_status, to_status, note, changed_by_type, changed_by_id)
               VALUES (?, NULL, 'assigned', ?, ?, ?)""",
            (claim_id, f"Assigned to {len(ids)} staff" if len(ids) > 1 else "Assigned to staff",
             assigned_by_role, assigned_by_id))
        await conn.commit()
    return True


async def get_claim_assignees(claim_id: int) -> list[dict]:
    """All assignees (PRIMARY from assigned_to_staff_id + any extras), with names, deduped."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await _ensure_claim_assignees_table(conn)
        primary = await (await conn.execute(
            "SELECT assigned_to_staff_id FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
        ids = []
        if primary and primary["assigned_to_staff_id"]:
            ids.append(primary["assigned_to_staff_id"])
        for r in await (await conn.execute(
                "SELECT staff_id FROM nidaan_claim_assignees WHERE claim_id=? ORDER BY assigned_at",
                (claim_id,))).fetchall():
            if r["staff_id"] not in ids:
                ids.append(r["staff_id"])
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        rows = await (await conn.execute(
            f"SELECT staff_id, name, role FROM nidaan_staff WHERE staff_id IN ({ph})", ids)).fetchall()
        by_id = {r["staff_id"]: dict(r) for r in rows}
    return [{"staff_id": i, "name": by_id.get(i, {}).get("name", f"#{i}"),
             "role": by_id.get(i, {}).get("role", ""), "primary": (i == ids[0])} for i in ids]


async def is_claim_assignee(claim_id: int, staff_id: int) -> bool:
    """True if the staff is the primary assignee OR an additional assignee of the claim."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT assigned_to_staff_id FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
        if r and r["assigned_to_staff_id"] == staff_id:
            return True
        await _ensure_claim_assignees_table(conn)
        r2 = await (await conn.execute(
            "SELECT 1 FROM nidaan_claim_assignees WHERE claim_id=? AND staff_id=?",
            (claim_id, staff_id))).fetchone()
        return bool(r2)


# ── Claim auto-assignment (least-loaded), super-admin toggle ──────────────────
CLAIM_OPEN_STATUSES = ("intimated", "assigned", "in_review", "in_negotiation")


async def is_claim_auto_assign() -> bool:
    return (await get_ops_setting("claim_auto_assign", "0")) == "1"


async def set_claim_auto_assign(on: bool) -> None:
    await set_ops_setting("claim_auto_assign", "1" if on else "0")


async def get_claim_handler_pool() -> list[int]:
    """Active staff eligible to auto-receive claims — associates + sub-admins (not the owner).
    Falls back to any active staff if that set is empty."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT staff_id FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
            "AND role IN ('team_member','sub_super_admin') ORDER BY staff_id")).fetchall()
        ids = [r["staff_id"] for r in rows]
        if not ids:
            rows = await (await conn.execute(
                "SELECT staff_id FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
                "ORDER BY staff_id")).fetchall()
            ids = [r["staff_id"] for r in rows]
    return ids


async def auto_assign_claim(claim_id: int) -> Optional[int]:
    """Assign a claim to the least-loaded handler (fewest OPEN claims). No-op if already
    assigned or no handler exists. Returns the chosen staff_id or None."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        c = await (await conn.execute(
            "SELECT assigned_to_staff_id FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    if not c:
        return None
    if c["assigned_to_staff_id"]:
        return c["assigned_to_staff_id"]
    pool = await get_claim_handler_pool()
    if not pool:
        return None
    ph = ",".join("?" * len(pool))
    sph = ",".join("?" * len(CLAIM_OPEN_STATUSES))
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            f"SELECT assigned_to_staff_id AS sid, COUNT(*) AS n FROM nidaan_claims "
            f"WHERE assigned_to_staff_id IN ({ph}) AND status IN ({sph}) "
            f"GROUP BY assigned_to_staff_id", pool + list(CLAIM_OPEN_STATUSES))).fetchall()
    load = {sid: 0 for sid in pool}
    for r in rows:
        load[r["sid"]] = r["n"]
    chosen = min(pool, key=lambda s: (load.get(s, 0), pool.index(s)))   # least-loaded, stable ties
    ok = await assign_claim_to_staff(claim_id, chosen, assigned_by_id=0, assigned_by_role="system")
    return chosen if ok else None


# =============================================================================
#  OPS: NOTES
# =============================================================================

async def add_claim_note(claim_id: int, staff_id: int, note: str,
                          parent_note_id: Optional[int] = None,
                          source: Optional[str] = None) -> int:
    """Add an internal claim note. Returns note_id.

    Backward-compatible: existing 3-arg callers are unaffected. `parent_note_id`
    threads a reply (flattened one level, exactly like quick-task notes); `source`
    records where it originated ('web' | 'mobile-web' | …)."""
    if parent_note_id:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT parent_note_id, claim_id FROM nidaan_claim_notes WHERE note_id=?",
                (parent_note_id,))).fetchone()
            if not row or row["claim_id"] != claim_id:
                parent_note_id = None
            elif row["parent_note_id"]:
                parent_note_id = row["parent_note_id"]
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_claim_notes (claim_id, staff_id, note, parent_note_id, source) "
            "VALUES (?,?,?,?,?)",
            (claim_id, staff_id, note.strip(), parent_note_id, source),
        )
        await conn.commit()
        return cur.lastrowid


async def get_claim_notes(claim_id: int) -> list[dict]:
    """Claim internal notes, oldest first. Each note carries extra collaboration
    keys (reads / attachments / mentions) — additive, so old callers that only read
    note/staff_name keep working."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT n.*, s.name AS staff_name, s.role AS staff_role
               FROM nidaan_claim_notes n
               JOIN nidaan_staff s ON s.staff_id = n.staff_id
               WHERE n.claim_id=? ORDER BY n.created_at ASC""",
            (claim_id,),
        )
        notes = [dict(r) for r in await cur.fetchall()]
        if not notes:
            return notes
        # read-receipts (who read each note, excluding its author)
        rcur = await conn.execute(
            "SELECT r.note_id, r.read_at, s.name AS reader_name "
            "FROM nidaan_claim_note_reads r "
            "JOIN nidaan_claim_notes n ON n.note_id = r.note_id "
            "LEFT JOIN nidaan_staff s ON s.staff_id = r.staff_id "
            "WHERE n.claim_id=? AND r.staff_id != n.staff_id ORDER BY r.read_at ASC",
            (claim_id,))
        reads: dict[int, list] = {}
        for rr in await rcur.fetchall():
            reads.setdefault(rr["note_id"], []).append(
                {"name": rr["reader_name"], "at": rr["read_at"]})
        # attachments per note
        acur = await conn.execute(
            "SELECT attachment_id, note_id, stored_name, original_name, uploaded_by, uploaded_at "
            "FROM nidaan_claim_note_attachments WHERE claim_id=? ORDER BY attachment_id ASC",
            (claim_id,))
        atts: dict[int, list] = {}
        for a in await acur.fetchall():
            atts.setdefault(a["note_id"], []).append(dict(a))
        # @mentions per note
        mcur = await conn.execute(
            "SELECT m.note_id, m.staff_id, s.name AS staff_name "
            "FROM nidaan_claim_note_mentions m "
            "LEFT JOIN nidaan_staff s ON s.staff_id = m.staff_id "
            "WHERE m.claim_id=? ORDER BY m.staff_id", (claim_id,))
        mentions: dict[int, list] = {}
        for mm in await mcur.fetchall():
            mentions.setdefault(mm["note_id"], []).append(
                {"staff_id": mm["staff_id"], "name": mm["staff_name"]})
        for n in notes:
            n["reads"] = reads.get(n["note_id"], [])
            n["attachments"] = atts.get(n["note_id"], [])
            n["mentions"] = mentions.get(n["note_id"], [])
        return notes


# ── Claim-note collaboration helpers (1C-g.4c) — parallel to quick-task infra ──
async def add_claim_note_attachments(*, claim_id: int, note_id: Optional[int],
                                      files: list[dict], uploaded_by: int) -> int:
    """files = [{'stored_name':…, 'original_name':…}, …]. Returns rows inserted."""
    if not files:
        return 0
    async with aiosqlite.connect(DB_PATH) as conn:
        for f in files:
            if not f.get("stored_name"):
                continue
            await conn.execute(
                "INSERT INTO nidaan_claim_note_attachments "
                "(claim_id, note_id, stored_name, original_name, uploaded_by) VALUES (?,?,?,?,?)",
                (claim_id, note_id, f["stored_name"], f.get("original_name"), uploaded_by))
        await conn.commit()
    return len(files)


async def delete_claim_note_attachment(attachment_id: int, staff_id: int,
                                       is_admin: bool) -> Optional[dict]:
    """Delete a claim-note attachment. Uploader within ATTACHMENT_DELETE_WINDOW_SEC, or an
    admin any time. Returns the deleted row (for disk cleanup) or None. Raises PermissionError
    ('not_owner' | 'too_late')."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_claim_note_attachments WHERE attachment_id=?",
            (attachment_id,))).fetchone()
        if not row:
            return None
        row = dict(row)
        if not is_admin:
            if row.get("uploaded_by") != staff_id:
                raise PermissionError("not_owner")
            try:
                up = datetime.fromisoformat(str(row["uploaded_at"]).replace(" ", "T"))
                age = (datetime.utcnow() - up).total_seconds()
            except Exception:
                age = 0
            if age > ATTACHMENT_DELETE_WINDOW_SEC:
                raise PermissionError("too_late")
        await conn.execute(
            "DELETE FROM nidaan_claim_note_attachments WHERE attachment_id=?", (attachment_id,))
        await conn.commit()
        return row


async def set_claim_note_mentions(note_id: int, claim_id: int,
                                  staff_ids: list[int]) -> list[int]:
    """Record @mentions on a claim note. Returns the deduped staff_ids stored."""
    ids = [int(s) for s in dict.fromkeys(staff_ids or []) if s]
    if not ids:
        return []
    async with aiosqlite.connect(DB_PATH) as conn:
        for sid in ids:
            await conn.execute(
                "INSERT OR IGNORE INTO nidaan_claim_note_mentions (note_id, claim_id, staff_id) "
                "VALUES (?,?,?)", (note_id, claim_id, sid))
        await conn.commit()
    return ids


async def mark_claim_notes_read(claim_id: int, staff_id: int) -> None:
    """Mark every note on a claim read by staff_id (excluding their own) + record the
    claim-notes 'seen' timestamp. Called whenever the staffer opens the claim."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO nidaan_claim_note_reads (note_id, staff_id) "
            "SELECT note_id, ? FROM nidaan_claim_notes WHERE claim_id=? AND staff_id != ?",
            (staff_id, claim_id, staff_id))
        await conn.execute(
            "INSERT INTO nidaan_claim_note_seen (claim_id, staff_id, seen_at) "
            "VALUES (?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(claim_id, staff_id) DO UPDATE SET seen_at=CURRENT_TIMESTAMP",
            (claim_id, staff_id))
        await conn.commit()


async def delete_claim_note(note_id: int, staff_id: int, is_admin: bool) -> Optional[dict]:
    """Delete a claim note. Author within ATTACHMENT_DELETE_WINDOW_SEC, or an admin any time.
    Direct replies are promoted to top-level (parent_note_id→NULL) so nothing is lost; the
    note's own attachments/reads/mentions rows are removed. Returns {'attachments':[stored…]}
    for disk cleanup, or None if not found. Raises PermissionError ('not_owner' | 'too_late')."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT note_id, staff_id, created_at FROM nidaan_claim_notes WHERE note_id=?",
            (note_id,))).fetchone()
        if not row:
            return None
        row = dict(row)
        if not is_admin:
            if row.get("staff_id") != staff_id:
                raise PermissionError("not_owner")
            try:
                cr = datetime.fromisoformat(str(row["created_at"]).replace(" ", "T"))
                age = (datetime.utcnow() - cr).total_seconds()
            except Exception:
                age = 0
            if age > ATTACHMENT_DELETE_WINDOW_SEC:
                raise PermissionError("too_late")
        stored = [r["stored_name"] for r in await (await conn.execute(
            "SELECT stored_name FROM nidaan_claim_note_attachments WHERE note_id=?",
            (note_id,))).fetchall()]
        # promote direct replies so they aren't orphaned/hidden
        await conn.execute(
            "UPDATE nidaan_claim_notes SET parent_note_id=NULL WHERE parent_note_id=?", (note_id,))
        await conn.execute("DELETE FROM nidaan_claim_note_attachments WHERE note_id=?", (note_id,))
        await conn.execute("DELETE FROM nidaan_claim_note_reads WHERE note_id=?", (note_id,))
        await conn.execute("DELETE FROM nidaan_claim_note_mentions WHERE note_id=?", (note_id,))
        await conn.execute("DELETE FROM nidaan_claim_notes WHERE note_id=?", (note_id,))
        await conn.commit()
        return {"attachments": stored}


async def get_claim_mention_candidates(claim_id: int) -> list[dict]:
    """Staff who can be @mentioned on a claim: current assignees first, then other active
    staff. Returns [{staff_id, name, role, is_assignee}]."""
    assignees = {a["staff_id"] for a in await get_claim_assignees(claim_id)}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT staff_id, name, role FROM nidaan_staff WHERE status='active' ORDER BY name")).fetchall()
    out = [{"staff_id": r["staff_id"], "name": r["name"], "role": r["role"],
            "is_assignee": r["staff_id"] in assignees} for r in rows]
    out.sort(key=lambda x: (not x["is_assignee"], x["name"].lower()))
    return out


# ── Subscriber ⇄ ops messaging (per claim) ───────────────────────────────────
async def list_claim_messages(claim_id: int, limit: int = 200) -> list[dict]:
    """Full message thread for a claim (both directions), oldest first, with the
    staff member's name resolved for display."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT m.message_id, m.sender_type, m.sender_staff_id, m.content,
                      m.created_at, m.read_by_subscriber_at, m.read_by_staff_at,
                      m.attachment_doc_id,
                      d.original_name AS attachment_name, d.stored_name AS attachment_stored,
                      d.mime_type AS attachment_mime,
                      s.name AS staff_name
               FROM nidaan_messages m
               LEFT JOIN nidaan_staff s ON s.staff_id = m.sender_staff_id
               LEFT JOIN nidaan_claim_documents d ON d.doc_id = m.attachment_doc_id
               WHERE m.claim_id=? AND m.deleted_at IS NULL
               ORDER BY m.message_id ASC LIMIT ?""",
            (claim_id, limit))).fetchall()
        return [dict(r) for r in rows]


async def add_claim_message(claim_id: int, sender_type: str, content: str,
                            subscriber_id: Optional[int] = None,
                            staff_id: Optional[int] = None,
                            source_channel: str = "dashboard",
                            attachment_doc_id: Optional[int] = None) -> int:
    """Append a message to a claim thread. sender_type is 'subscriber' or 'staff'.
    attachment_doc_id links a nidaan_claim_documents row (optional file share)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_messages
                 (claim_id, sender_type, sender_subscriber_id, sender_staff_id,
                  content, source_channel, attachment_doc_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (claim_id, sender_type, subscriber_id, staff_id,
             (content or "").strip(), source_channel, attachment_doc_id))
        await conn.commit()
        return cur.lastrowid


# ── Claim collaboration: "involved" watchers + mute (mirrors task watchers) ──
async def add_claim_watchers(claim_id: int, staff_ids: list, added_by: int,
                             relation: str = "mentioned") -> list:
    """Add staff as watchers ("involved") of a claim. Returns the staff_ids NEWLY
    added (existing watchers skipped) so callers notify only the freshly-tagged."""
    newly = []
    if not staff_ids:
        return newly
    async with aiosqlite.connect(DB_PATH) as conn:
        for sid in staff_ids:
            if not sid:
                continue
            cur = await conn.execute(
                "INSERT OR IGNORE INTO nidaan_claim_watchers "
                "(claim_id, staff_id, relation, added_by_staff_id) VALUES (?,?,?,?)",
                (claim_id, int(sid), relation, added_by))
            if cur.rowcount:
                newly.append(int(sid))
        await conn.commit()
    return newly


async def list_claim_watchers(claim_id: int) -> list:
    """Involved staff on a claim with name/role + mute state."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT w.staff_id, w.relation, w.muted, w.added_by_staff_id, w.added_at, "
            "       s.name, s.role "
            "FROM nidaan_claim_watchers w "
            "LEFT JOIN nidaan_staff s ON s.staff_id = w.staff_id "
            "WHERE w.claim_id = ? ORDER BY w.added_at ASC", (claim_id,))).fetchall()
        return [dict(r) for r in rows]


async def set_claim_watch_mute(claim_id: int, staff_id: int, muted: bool) -> bool:
    """Mute/unmute a claim for one staffer. Creates a watcher row (relation='owner')
    if they weren't already involved — so an assignee can mute too."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO nidaan_claim_watchers (claim_id, staff_id, relation, muted, added_by_staff_id) "
            "VALUES (?,?,'owner',?,?) "
            "ON CONFLICT(claim_id, staff_id) DO UPDATE SET muted=excluded.muted",
            (claim_id, staff_id, 1 if muted else 0, staff_id))
        await conn.commit()
    return True


async def get_claim_watcher_ids(claim_id: int, exclude_staff_id: int = 0) -> list:
    """Non-muted watcher staff_ids for a claim (for notification fan-out), minus the actor."""
    async with aiosqlite.connect(DB_PATH) as conn:
        rows = await (await conn.execute(
            "SELECT staff_id FROM nidaan_claim_watchers "
            "WHERE claim_id=? AND muted=0 AND staff_id<>?",
            (claim_id, exclude_staff_id or 0))).fetchall()
        return [r[0] for r in rows]


async def unsend_claim_message(message_id: int, claim_id: int, staff_id: int) -> bool:
    """Unsend a STAFF message on a claim thread. Soft delete — the row is retained (this is a
    legal practice; the record of what was said must survive) and simply filtered out of the
    thread. A subscriber's own message is never removable by staff."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_messages SET deleted_at=CURRENT_TIMESTAMP, deleted_by_staff_id=? "
            "WHERE message_id=? AND claim_id=? AND sender_type='staff' AND deleted_at IS NULL",
            (staff_id, message_id, claim_id))
        await conn.commit()
        return cur.rowcount > 0


async def mark_messages_read(claim_id: int, by: str) -> None:
    """Mark the claim's messages read by 'subscriber' or 'staff'."""
    col = "read_by_subscriber_at" if by == "subscriber" else "read_by_staff_at"
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE nidaan_messages SET {col}=CURRENT_TIMESTAMP "
            f"WHERE claim_id=? AND {col} IS NULL", (claim_id,))
        await conn.commit()


async def count_unread_messages_for_subscriber(account_id: int) -> int:
    """How many staff→subscriber messages are unread across the subscriber's claims."""
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            """SELECT COUNT(*) FROM nidaan_messages m
               JOIN nidaan_claims c ON c.claim_id = m.claim_id
               WHERE c.account_id=? AND m.sender_type='staff'
                 AND m.read_by_subscriber_at IS NULL""", (account_id,))).fetchone()
        return row[0] if row else 0


async def unread_messages_by_claim(account_id: int) -> dict:
    """Per-claim count of unread ops→subscriber replies for a subscriber → {claim_id: count}.
    Powers the dashboard notification bell (which claim got a reply)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        rows = await (await conn.execute(
            """SELECT m.claim_id, COUNT(*) AS n FROM nidaan_messages m
               JOIN nidaan_claims c ON c.claim_id = m.claim_id
               WHERE c.account_id=? AND m.sender_type='staff'
                 AND m.read_by_subscriber_at IS NULL
               GROUP BY m.claim_id""", (account_id,))).fetchall()
        return {int(r[0]): int(r[1]) for r in rows}


async def mark_support_seen_by_subscriber(thread_id: int) -> None:
    """The logged-in customer's widget fetched this thread → mark all current messages seen
    (advance sub_last_seen_msg_id to the latest). Harmless for anonymous/guide threads."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """UPDATE nidaan_support_threads
               SET sub_last_seen_msg_id = COALESCE(
                   (SELECT MAX(msg_id) FROM nidaan_support_messages WHERE thread_id=?),
                   sub_last_seen_msg_id)
               WHERE thread_id=?""", (thread_id, thread_id))
        await conn.commit()


async def unread_support_by_thread(account_id: int) -> dict:
    """Per-thread count of UNSEEN staff replies for a logged-in subscriber → {thread_id: count}.
    Powers the dashboard chat-reply bell. Only human (staff) replies count; open/ongoing threads."""
    async with aiosqlite.connect(DB_PATH) as conn:
        rows = await (await conn.execute(
            """SELECT t.thread_id, COUNT(*) AS n
               FROM nidaan_support_messages m
               JOIN nidaan_support_threads t ON t.thread_id = m.thread_id
               WHERE t.account_id=? AND t.status!='closed'
                 AND m.sender_type='staff' AND m.msg_id > COALESCE(t.sub_last_seen_msg_id, 0)
               GROUP BY t.thread_id""", (account_id,))).fetchall()
        return {int(r[0]): int(r[1]) for r in rows}


# =============================================================================
#  OPS: FOLLOW-UPS
# =============================================================================

async def add_followup(claim_id: int, staff_id: int, due_date: str, note: str = "") -> int:
    """Schedule a follow-up. Returns followup_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_followups (claim_id, staff_id, due_date, note)
               VALUES (?,?,?,?)""",
            (claim_id, staff_id, due_date, note),
        )
        await conn.commit()
        return cur.lastrowid


async def complete_followup(followup_id: int, staff_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """UPDATE nidaan_followups SET status='done', completed_at=CURRENT_TIMESTAMP
               WHERE followup_id=? AND staff_id=?""",
            (followup_id, staff_id),
        )
        await conn.commit()
    return True


async def get_followups_for_staff(staff_id: int, status: str = "pending") -> list[dict]:
    """Get follow-ups due for a staff member."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT f.*, c.insured_name, c.claim_type, c.status AS claim_status
               FROM nidaan_followups f
               JOIN nidaan_claims c ON c.claim_id = f.claim_id
               WHERE f.staff_id=? AND f.status=?
               ORDER BY f.due_date ASC""",
            (staff_id, status),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_followups_for_claim(claim_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT f.*, s.name AS staff_name
               FROM nidaan_followups f
               JOIN nidaan_staff s ON s.staff_id = f.staff_id
               WHERE f.claim_id=? ORDER BY f.due_date ASC""",
            (claim_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def mark_overdue_followups() -> int:
    """Mark pending follow-ups past due date as overdue. Returns count updated."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """UPDATE nidaan_followups SET status='overdue'
               WHERE status='pending' AND due_date < DATE('now')"""
        )
        await conn.commit()
        return cur.rowcount


# =============================================================================
#  OPS: REVENUE (super_admin only)
# =============================================================================

REVENUE_SPLIT = {"ashwin": 80, "dushyant": 20}  # percentage


async def get_revenue_stats() -> dict:
    """Full revenue breakdown for super admin."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Total collected from subscriptions
        cur = await conn.execute(
            "SELECT COALESCE(SUM(amount_paid),0) FROM nidaan_subscriptions "
            "WHERE status IN ('active','cancelled')"
        )
        total_sub = (await cur.fetchone())[0]

        # Per-plan breakdown
        cur = await conn.execute(
            "SELECT plan, COUNT(*) as count, COALESCE(SUM(amount_paid),0) as revenue "
            "FROM nidaan_subscriptions WHERE status IN ('active','cancelled') "
            "GROUP BY plan"
        )
        by_plan = {r["plan"]: {"count": r["count"], "revenue": r["revenue"]}
                   for r in await cur.fetchall()}

        # Monthly trend (last 12 months)
        cur = await conn.execute(
            """SELECT strftime('%Y-%m', started_at) as month,
                      COUNT(*) as new_subs,
                      COALESCE(SUM(amount_paid),0) as revenue
               FROM nidaan_subscriptions
               WHERE started_at >= DATE('now','-12 months')
               GROUP BY month ORDER BY month ASC"""
        )
        monthly = [dict(r) for r in await cur.fetchall()]

        # Per-claim ₹499 revenue
        cur = await conn.execute(
            "SELECT COALESCE(SUM(amount_paid),0) FROM nidaan_per_claim_purchase "
            "WHERE status NOT IN ('failed','refunded','pending_payment')"
        )
        total_d2c = (await cur.fetchone())[0]

        # Custom-amount payment links (super-admin generated; not tied to a sub/per-claim row).
        # review499 links create a per_claim_purchase (in d2c above) and subscription links
        # create a subscription row (in total_sub above), so ONLY 'custom' is added here — no
        # double counting.
        cur = await conn.execute(
            "SELECT COALESCE(SUM(amount_paise),0) FROM nidaan_payment_links "
            "WHERE status='paid' AND purpose='custom'"
        )
        total_custom_link = (await cur.fetchone())[0] // 100

        # Active vs churned
        cur = await conn.execute(
            "SELECT status, COUNT(*) as cnt FROM nidaan_subscriptions GROUP BY status"
        )
        sub_by_status = {r["status"]: r["cnt"] for r in await cur.fetchall()}

        total_all = total_sub + total_d2c + total_custom_link
        return {
            "total_subscription_revenue": total_sub,
            "total_d2c_revenue": total_d2c,
            "total_custom_link_revenue": total_custom_link,
            "total_revenue": total_all,
            "by_plan": by_plan,
            "monthly_trend": monthly,
            "subscriptions_by_status": sub_by_status,
            "revenue_split": {
                "ashwin": {"pct": 80, "amount": round(total_all * 0.80)},
                "dushyant": {"pct": 20, "amount": round(total_all * 0.20)},
            },
        }


# =============================================================================
#  OPS: APP HEALTH (super_admin only)
# =============================================================================

async def get_app_health() -> dict:
    """Application health snapshot for super admin."""
    import time
    t0 = time.monotonic()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        def _c(row): return row[0] if row else 0

        tables = {}
        for tbl in [
            "nidaan_accounts", "nidaan_claims", "nidaan_subscriptions",
            "nidaan_staff", "nidaan_followups", "nidaan_claim_notes",
            "nidaan_per_claim_purchase", "nidaan_claim_status_log",
        ]:
            try:
                row = await (await conn.execute(f"SELECT COUNT(*) FROM {tbl}")).fetchone()
                tables[tbl] = _c(row)
            except Exception:
                tables[tbl] = -1

        # Claim status breakdown
        cur = await conn.execute(
            "SELECT status, COUNT(*) cnt FROM nidaan_claims GROUP BY status"
        )
        claims_by_status = {r["status"]: r["cnt"] for r in await cur.fetchall()}

        # Overdue followups
        cur = await conn.execute(
            "SELECT COUNT(*) FROM nidaan_followups WHERE status='overdue'"
        )
        overdue = _c(await cur.fetchone())

        # Unassigned open claims
        cur = await conn.execute(
            "SELECT COUNT(*) FROM nidaan_claims "
            "WHERE assigned_to_staff_id IS NULL "
            "AND status NOT IN ('resolved_won','resolved_lost','closed','withdrawn')"
        )
        unassigned = _c(await cur.fetchone())

        # Recent signups (last 7 days)
        cur = await conn.execute(
            "SELECT COUNT(*) FROM nidaan_accounts "
            "WHERE created_at >= DATE('now','-7 days')"
        )
        new_accounts_7d = _c(await cur.fetchone())

    db_latency_ms = round((time.monotonic() - t0) * 1000, 1)

    return {
        "db_latency_ms": db_latency_ms,
        "table_counts": tables,
        "claims_by_status": claims_by_status,
        "overdue_followups": overdue,
        "unassigned_open_claims": unassigned,
        "new_accounts_last_7d": new_accounts_7d,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# =============================================================================
#  OPS: IMPERSONATION (super_admin only)
# =============================================================================

async def impersonate_account(account_id: int) -> Optional[dict]:
    """Generate an advisor JWT for a given account_id (for troubleshooting).
    Returns dict with token, email, owner_name, plan, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT a.account_id, a.owner_name, a.email,
                      COALESCE(s.plan, 'free') AS plan
               FROM nidaan_accounts a
               LEFT JOIN nidaan_subscriptions s
                      ON s.account_id = a.account_id AND s.status = 'active'
               WHERE a.account_id = ?""",
            (account_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
    token = create_nidaan_token(int(row["account_id"]), row["email"], row["plan"])
    logger.warning(
        "IMPERSONATION: super_admin generated advisor token for account_id=%d email=%s plan=%s",
        account_id, row["email"], row["plan"],
    )
    return {"token": token, "email": row["email"], "owner_name": row["owner_name"], "plan": row["plan"]}


# =============================================================================
#  OPS: ADMIN ACCOUNT MANAGEMENT (super_admin only)
# =============================================================================

async def create_account_by_admin(
    owner_name: str,
    email: str,
    phone: str,
    firm_name: str = "",
    plan: str = "free",
) -> Optional[int]:
    """Create a new advisor account directly (no password — invite flow or set later)."""
    tmp_pw = secrets.token_hex(16)  # random unguessable password — admin must reset
    return await create_account(owner_name=owner_name, email=email, phone=phone,
                                password=tmp_pw, firm_name=firm_name)


async def admin_set_account_password(account_id: int, new_password: str) -> bool:
    return await update_account_password(account_id, new_password)


async def admin_update_account(
    account_id: int,
    owner_name: str = None,
    firm_name: str = None,
    phone: str = None,
    status: str = None,
) -> bool:
    fields, vals = [], []
    if owner_name is not None:
        fields.append("owner_name=?"); vals.append(owner_name)
    if firm_name is not None:
        fields.append("firm_name=?"); vals.append(firm_name)
    if phone is not None:
        fields.append("phone=?"); vals.append(phone)
    if status is not None:
        fields.append("status=?"); vals.append(status)
    if not fields:
        return False
    vals.append(account_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE nidaan_accounts SET {', '.join(fields)} WHERE account_id=?", vals
        )
        await conn.commit()
    return True


# =============================================================================
#  CLAIM DOCUMENTS
# =============================================================================

async def ensure_claim_documents_table() -> None:
    """Create nidaan_claim_documents table if it doesn't exist (safe to call on every boot)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS nidaan_claim_documents (
                doc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id    INTEGER NOT NULL,
                purchase_id   INTEGER,
                claim_id      INTEGER,
                stored_name   TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_size     INTEGER,
                mime_type     TEXT,
                uploaded_at   TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        # Who uploaded it: '' (legacy/staff/subscriber) | 'claimant' (policyholder via their portal).
        # Lets the claimant portal show ONLY the claimant's own uploads, never internal files.
        try:
            await conn.execute("ALTER TABLE nidaan_claim_documents ADD COLUMN source TEXT DEFAULT ''")
        except Exception:
            pass
        await conn.commit()


async def set_claims_archived(claim_ids: list, archived: bool, actor: str = "") -> int:
    """Archive (or restore) claims — super-admin/admin cleanup of test/garbage claims. Archived
    claims are hidden from every working view but never deleted (restorable). Returns the count
    updated. Idempotent."""
    ids = [int(c) for c in (claim_ids or []) if str(c).strip().isdigit()]
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    async with aiosqlite.connect(DB_PATH) as conn:
        if archived:
            cur = await conn.execute(
                f"UPDATE nidaan_claims SET archived=1, archived_at=CURRENT_TIMESTAMP, archived_by=? "
                f"WHERE claim_id IN ({ph}) AND COALESCE(archived,0)=0",
                tuple([actor or ""] + ids))
        else:
            cur = await conn.execute(
                f"UPDATE nidaan_claims SET archived=0, archived_at=NULL, archived_by='' "
                f"WHERE claim_id IN ({ph}) AND COALESCE(archived,0)=1",
                tuple(ids))
        await conn.commit()
        return cur.rowcount


async def save_claim_document(
    account_id: int,
    stored_name: str,
    original_name: str,
    file_size: int,
    mime_type: str,
    purchase_id: Optional[int] = None,
    claim_id: Optional[int] = None,
    source: str = "",
) -> int:
    """Record a newly uploaded document. Returns doc_id. `source`='claimant' marks a policyholder
    upload (via the claimant portal); default '' = legacy/staff/subscriber."""
    await ensure_claim_documents_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_claim_documents
               (account_id, purchase_id, claim_id, stored_name, original_name, file_size, mime_type, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_id, purchase_id, claim_id, stored_name, original_name, file_size, mime_type, source or ""),
        )
        await conn.commit()
        return cur.lastrowid


async def delete_claim_document(doc_id: int, *, account_id: Optional[int] = None,
                                claim_id: Optional[int] = None, purchase_id: Optional[int] = None,
                                allow_any: bool = False) -> Optional[str]:
    """Delete one claim/review document row, ownership-guarded. Returns the stored_name (so the
    caller can remove the file from disk) or None if not found / not permitted.
    - allow_any=True: ops staff (no ownership check).
    - else: the doc must match the given account_id / claim_id / purchase_id (whichever supplied)."""
    await ensure_claim_documents_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_claim_documents WHERE doc_id=?", (doc_id,))).fetchone()
        if not row:
            return None
        d = dict(row)
        if not allow_any:
            if account_id is not None and int(d.get("account_id") or 0) != int(account_id):
                return None
            if claim_id is not None and int(d.get("claim_id") or 0) != int(claim_id):
                return None
            if purchase_id is not None and int(d.get("purchase_id") or 0) != int(purchase_id):
                return None
        await conn.execute("DELETE FROM nidaan_claim_documents WHERE doc_id=?", (doc_id,))
        await conn.commit()
        return d.get("stored_name")


async def get_claim_documents(
    purchase_id: Optional[int] = None,
    claim_id: Optional[int] = None,
    account_id: Optional[int] = None,
) -> list[dict]:
    """Retrieve documents for a purchase or claim."""
    await ensure_claim_documents_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if purchase_id is not None:
            cur = await conn.execute(
                "SELECT * FROM nidaan_claim_documents WHERE purchase_id=? ORDER BY uploaded_at",
                (purchase_id,),
            )
        elif claim_id is not None:
            cur = await conn.execute(
                "SELECT * FROM nidaan_claim_documents WHERE claim_id=? ORDER BY uploaded_at",
                (claim_id,),
            )
        elif account_id is not None:
            cur = await conn.execute(
                "SELECT * FROM nidaan_claim_documents WHERE account_id=? ORDER BY uploaded_at DESC",
                (account_id,),
            )
        else:
            return []
        return [dict(r) for r in await cur.fetchall()]
