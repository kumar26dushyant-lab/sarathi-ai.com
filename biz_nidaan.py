# =============================================================================
#  biz_nidaan.py — Nidaan Partner: The Legal Consultants LLP
#  Phase 1b skeleton — DB helpers, auth, claims, subscriptions
# =============================================================================
#
#  Architecture: plug-and-play.  No Sarathi tables are modified here.
#  The only join point is product_link(nidaan_account_id, sarathi_tenant_id).
#
#  Plans (quarterly Razorpay subscriptions):
#    silver   — ₹1 500/quarter  (1 user,  10 claims/30 days, legal review)
#    gold     — ₹3 000/quarter  (5 users, 25 claims/30 days + Sarathi bundle)
#    platinum — ₹6 000/quarter  (unlimited users/claims + Sarathi bundle)
#
# =============================================================================

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, date, timedelta
from typing import Optional

import aiosqlite

logger = logging.getLogger("sarathi.nidaan")

DB_PATH = os.environ.get("DB_PATH", "sarathi_biz.db")

# ── Plan limits ───────────────────────────────────────────────────────────────
PLAN_LIMITS: dict[str, dict] = {
    "silver":   {"max_users": 1,   "claims_per_30d": 10,  "sarathi_bundle": False},
    "gold":     {"max_users": 5,   "claims_per_30d": 25,  "sarathi_bundle": True},
    "platinum": {"max_users": None, "claims_per_30d": None, "sarathi_bundle": True},
}

CLAIM_STATUSES = (
    "intimated", "assigned", "in_review", "in_negotiation",
    "resolved_won", "resolved_lost", "closed", "withdrawn",
)


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


async def create_account(
    owner_name: str,
    email: str,
    phone: str,
    password: str,
    firm_name: str = "",
) -> Optional[int]:
    """Create a new Nidaan account. Returns account_id or None on duplicate email."""
    pw_hash = _hash_password(password)
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cur = await conn.execute(
                """INSERT INTO nidaan_accounts
                   (owner_name, email, phone, password_hash, firm_name)
                   VALUES (?, ?, ?, ?, ?)""",
                (owner_name, email.lower().strip(), phone, pw_hash, firm_name),
            )
            await conn.commit()
            return cur.lastrowid
    except aiosqlite.IntegrityError:
        logger.warning("nidaan create_account: duplicate email %s", email)
        return None


async def get_account_by_email(email: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_accounts WHERE email = ? AND status != 'suspended'",
            (email.lower().strip(),),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_account_google(
    owner_name: str,
    email: str,
    plan: str = "silver",
    firm_name: str = "",
) -> Optional[int]:
    """Create a Nidaan account via Google Sign-In (no password).
    Stores an unguessable pw_hash so password login is permanently disabled for these accounts.
    Returns account_id or None on duplicate email."""
    pw_hash = "google$" + secrets.token_hex(32)
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cur = await conn.execute(
                """INSERT INTO nidaan_accounts
                   (owner_name, email, phone, password_hash, firm_name)
                   VALUES (?, ?, ?, ?, ?)""",
                (owner_name, email.lower().strip(), "", pw_hash, firm_name),
            )
            await conn.commit()
            return cur.lastrowid
    except aiosqlite.IntegrityError:
        logger.warning("nidaan create_account_google: duplicate email %s", email)
        return None


async def authenticate_account(email: str, password: str) -> Optional[dict]:
    """Return account dict if credentials valid, else None."""
    account = await get_account_by_email(email)
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
) -> int:
    """Record a new subscription. Returns sub_id."""
    if plan not in PLAN_LIMITS:
        raise ValueError(f"Unknown Nidaan plan: {plan}")
    period_end = datetime.utcnow() + timedelta(days=period_days)
    async with aiosqlite.connect(DB_PATH) as conn:
        # Cancel any previous active sub first
        await conn.execute(
            "UPDATE nidaan_subscriptions SET status='cancelled' "
            "WHERE account_id=? AND status='active'",
            (account_id,),
        )
        cur = await conn.execute(
            """INSERT INTO nidaan_subscriptions
               (account_id, plan, amount_paid, razorpay_subscription_id, current_period_end)
               VALUES (?, ?, ?, ?, ?)""",
            (account_id, plan, amount_paid, razorpay_subscription_id,
             period_end.isoformat()),
        )
        await conn.commit()
        return cur.lastrowid


# =============================================================================
#  CLAIM QUOTA
# =============================================================================

async def can_submit_claim(account_id: int) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    Checks rolling 30-day quota against plan limits.
    Platinum always allowed.
    """
    sub = await get_active_subscription(account_id)
    if not sub:
        return False, "no_active_subscription"

    plan = sub["plan"]
    limit = PLAN_LIMITS[plan]["claims_per_30d"]
    if limit is None:
        return True, "ok"  # platinum

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_plan_quota WHERE account_id = ?", (account_id,)
        )
        quota = await cur.fetchone()

    window_start = date.today() - timedelta(days=30)

    if quota is None:
        return True, "ok"  # no quota row yet → 0 claims

    stored_start = date.fromisoformat(str(quota["current_window_start"]))
    if stored_start < window_start:
        return True, "ok"  # window has rolled, reset on next insert

    if quota["claims_this_window"] >= limit:
        return False, f"quota_exceeded_{plan}"

    return True, "ok"


async def _increment_quota(account_id: int, conn: aiosqlite.Connection):
    """Upsert the rolling quota counter (call inside the same connection as claim insert)."""
    today = date.today().isoformat()
    window_start = (date.today() - timedelta(days=30)).isoformat()
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
    type_specific: Optional[dict] = None,
    notes_from_agent: str = "",
) -> tuple[Optional[int], str]:
    """
    Submit a new claim after quota check.
    Returns (claim_id, status_msg).
    """
    allowed, reason = await can_submit_claim(account_id)
    if not allowed:
        return None, reason

    type_specific_json = json.dumps(type_specific or {})
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_claims
               (account_id, user_id, claim_type, insured_name, insured_phone,
                insured_email, insurer_name, policy_no, disputed_amount,
                claim_event_date, type_specific, notes_from_agent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_id, user_id, claim_type, insured_name, insured_phone,
             insured_email, insurer_name, policy_no, disputed_amount,
             claim_event_date, type_specific_json, notes_from_agent),
        )
        claim_id = cur.lastrowid
        await conn.execute(
            """INSERT INTO nidaan_claim_status_log
               (claim_id, to_status, note, changed_by_type, changed_by_id)
               VALUES (?, 'intimated', 'Claim submitted by advisor', 'advisor', ?)""",
            (claim_id, account_id),
        )
        await _increment_quota(account_id, conn)
        await conn.commit()

    logger.info("nidaan claim %d submitted: account=%d type=%s", claim_id, account_id, claim_type)
    return claim_id, "ok"


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


# =============================================================================
#  REVIEW REQUESTS (₹999 per-claim, no subscription needed)
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
) -> int:
    """Save a ₹999 review request. Returns purchase_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_per_claim_purchase
               (advisor_name, advisor_phone, advisor_email,
                insured_name, insured_phone, insurer_name,
                claim_type, disputed_amount, brief_description,
                amount_paid, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 999, 'pending_payment')""",
            (advisor_name, advisor_phone, advisor_email,
             insured_name, advisor_phone, insurer_name,
             claim_type, disputed_amount, notes),
        )
        await conn.commit()
        return cur.lastrowid


async def get_review_requests_admin(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Admin: list all ₹999 review requests."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if status:
            cur = await conn.execute(
                "SELECT * FROM nidaan_per_claim_purchase WHERE status=? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        else:
            cur = await conn.execute(
                "SELECT * FROM nidaan_per_claim_purchase "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(r) for r in await cur.fetchall()]


REVIEW_STATUSES = (
    "pending_payment", "paid", "in_review", "completed", "cancelled"
)


async def update_review_request_status(
    purchase_id: int,
    new_status: str,
    note: str = "",
) -> bool:
    """Admin: update status (and optional note) of a ₹999 review request."""
    if new_status not in REVIEW_STATUSES:
        raise ValueError(f"Invalid review status: {new_status}")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT purchase_id FROM nidaan_per_claim_purchase WHERE purchase_id=?",
            (purchase_id,),
        )
        if not await cur.fetchone():
            return False
        now = datetime.utcnow().isoformat()
        if note:
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
    """Admin: list all Nidaan accounts with their active plan."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT a.*, s.plan, s.status AS sub_status, s.current_period_end
               FROM nidaan_accounts a
               LEFT JOIN nidaan_subscriptions s ON s.account_id = a.account_id
                   AND s.status = 'active'
               ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]


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
    "silver":   {"amount_paise": 150000, "display": "₹1,500/quarter", "interval": 3},
    "gold":     {"amount_paise": 300000, "display": "₹3,000/quarter", "interval": 3},
    "platinum": {"amount_paise": 600000, "display": "₹6,000/quarter", "interval": 3},
}

# Cache: plan_key → razorpay_plan_id
_nidaan_plan_ids: dict[str, str] = {}


async def ensure_nidaan_plans(rzp_key_id: str, rzp_key_secret: str):
    """Create Razorpay plan objects for Nidaan if not already cached."""
    import httpx
    for plan_key, info in NIDAAN_RAZORPAY_PLANS.items():
        if plan_key in _nidaan_plan_ids:
            continue
        # Try to find existing
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.razorpay.com/v1/plans?count=100",
                    auth=(rzp_key_id, rzp_key_secret), timeout=15.0,
                )
                for p in r.json().get("items", []):
                    notes = p.get("notes", {})
                    if notes.get("nidaan_plan") == plan_key:
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
                        "period": "monthly",
                        "interval": info["interval"],
                        "item": {
                            "name": f"Nidaan {plan_key.title()} Plan",
                            "amount": info["amount_paise"],
                            "currency": "INR",
                            "description": info["display"],
                        },
                        "notes": {
                            "nidaan_plan": plan_key,
                            "product": "nidaan",
                        },
                    },
                    timeout=15.0,
                )
                result = r.json()
                if "id" in result:
                    _nidaan_plan_ids[plan_key] = result["id"]
                    logger.info("Created Nidaan Razorpay plan %s → %s", plan_key, result["id"])
        except Exception as e:
            logger.error("Failed to create Nidaan plan %s: %s", plan_key, e)


async def create_nidaan_razorpay_subscription(
    account_id: int,
    plan: str,
    rzp_key_id: str,
    rzp_key_secret: str,
    email: str,
    phone: str,
) -> dict:
    """Create a Razorpay subscription for a Nidaan account. Returns sub details."""
    import httpx
    await ensure_nidaan_plans(rzp_key_id, rzp_key_secret)
    plan_id = _nidaan_plan_ids.get(plan)
    if not plan_id:
        return {"error": f"Plan '{plan}' not available in Razorpay"}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.razorpay.com/v1/subscriptions",
                auth=(rzp_key_id, rzp_key_secret),
                json={
                    "plan_id": plan_id,
                    "total_count": 40,  # 10 years
                    "quantity": 1,
                    "notes": {
                        "nidaan_account_id": str(account_id),
                        "nidaan_plan": plan,
                        "product": "nidaan",
                    },
                    "notify_info": {
                        "notify_phone": phone,
                        "notify_email": email,
                    },
                },
                timeout=20.0,
            )
            result = r.json()
            if "id" not in result:
                return {"error": result.get("error", {}).get("description", "Failed")}
            return {
                "subscription_id": result["id"],
                "short_url": result.get("short_url", ""),
                "plan": plan,
                "amount_display": NIDAAN_RAZORPAY_PLANS[plan]["display"],
                "razorpay_key_id": rzp_key_id,
            }
    except Exception as e:
        logger.error("Nidaan Razorpay subscription error: %s", e)
        return {"error": str(e)}


async def activate_from_razorpay_webhook(
    razorpay_sub_id: str,
    nidaan_account_id: int,
    plan: str,
    amount_paise: int,
) -> bool:
    """Activate / renew a Nidaan subscription from Razorpay webhook. Idempotent."""
    # Check not already recorded
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT sub_id FROM nidaan_subscriptions "
            "WHERE razorpay_subscription_id=? AND plan=?",
            (razorpay_sub_id, plan),
        )
        existing = await cur.fetchone()
    if existing:
        logger.info("Nidaan sub already recorded for rzp_sub %s", razorpay_sub_id)
        return True
    sub_id = await create_subscription(
        account_id=nidaan_account_id,
        plan=plan,
        amount_paid=amount_paise // 100,
        razorpay_subscription_id=razorpay_sub_id,
        period_days=92,
    )
    logger.info("✅ Nidaan sub activated: account=%d plan=%s sub_id=%d", nidaan_account_id, plan, sub_id)
    return True


async def cancel_nidaan_subscription(account_id: int) -> bool:
    """Mark all active subscriptions for an account as cancelled."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_subscriptions SET status='cancelled' "
            "WHERE account_id=? AND status='active'",
            (account_id,),
        )
        await conn.commit()
    logger.info("Nidaan sub cancelled: account=%d", account_id)
    return True


async def update_account_profile(account_id: int, owner_name: str = None,
                                  firm_name: str = None, phone: str = None) -> bool:
    """Update mutable profile fields on a Nidaan account."""
    fields, vals = [], []
    if owner_name is not None:
        fields.append("owner_name=?"); vals.append(owner_name)
    if firm_name is not None:
        fields.append("firm_name=?"); vals.append(firm_name)
    if phone is not None:
        fields.append("phone=?"); vals.append(phone)
    if not fields:
        return False
    vals.append(account_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE nidaan_accounts SET {', '.join(fields)} WHERE account_id=?", vals
        )
        await conn.commit()
    return True
