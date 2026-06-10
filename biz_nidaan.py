# =============================================================================
#  biz_nidaan.py — Nidaan Partner: The Legal Consultants LLP
#  Phase 1b skeleton — DB helpers, auth, claims, subscriptions
# =============================================================================
#
#  Architecture: plug-and-play.  No Sarathi tables are modified here.
#  The only join point is product_link(nidaan_account_id, sarathi_tenant_id).
#
#  Plans (quarterly Razorpay subscriptions):
#    silver   — ₹1 500/quarter  (1 user,  10 claims/quarter, legal review)
#    gold     — ₹3 000/quarter  (5 users, 25 claims/quarter + Sarathi bundle)
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
    "silver":          {"max_users": 1,    "claims_per_quarter": 10,  "sarathi_bundle": True},
    "gold":            {"max_users": 5,    "claims_per_quarter": 25,  "sarathi_bundle": True},
    "platinum":        {"max_users": None, "claims_per_quarter": None, "sarathi_bundle": True},
    # Annual variants — same limits, different billing period
    "silver_annual":   {"max_users": 1,    "claims_per_quarter": 10,  "sarathi_bundle": True},
    "gold_annual":     {"max_users": 5,    "claims_per_quarter": 25,  "sarathi_bundle": True},
    "platinum_annual": {"max_users": None, "claims_per_quarter": None, "sarathi_bundle": True},
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
) -> dict:
    """Direct-insured signup: find/create account and create a pending_payment purchase.
    Returns dict with account_id, purchase_id, is_new, temp_password (if new account).

    intermediary_code / intermediary_name: as printed on the policy. Recommended
    for legal correspondence; collected at intake per IRDAI guidelines."""
    import secrets as _sec
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
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_per_claim_purchase
               (advisor_name, advisor_phone, advisor_email,
                insured_name, insured_phone, insurer_name,
                claim_type, disputed_amount, brief_description,
                amount_paid, status, account_id,
                intermediary_code, intermediary_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 499, 'pending_payment', ?, ?, ?)""",
            (name.strip(), phone.strip(), email,
             name.strip(), phone.strip(), insurer_name.strip(),
             claim_type, disputed_amount, notes.strip(), account_id,
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
    razorpay_payment_id: str = "",
) -> int:
    """Record a new subscription. Returns sub_id.

    `razorpay_subscription_id` actually holds the Razorpay ORDER id for one-time
    payments (legacy column name). `razorpay_payment_id` is the actual payment
    id used for refunds via POST /payments/{payment_id}/refund.
    """
    if plan not in PLAN_LIMITS:
        raise ValueError(f"Unknown Nidaan plan: {plan}")
    period_end = datetime.utcnow() + timedelta(days=period_days)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_subscriptions SET status='cancelled', cancelled_at=CURRENT_TIMESTAMP "
            "WHERE account_id=? AND status='active'",
            (account_id,),
        )
        cur = await conn.execute(
            """INSERT INTO nidaan_subscriptions
               (account_id, plan, amount_paid, razorpay_subscription_id, razorpay_payment_id,
                current_period_end)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, plan, amount_paid, razorpay_subscription_id, razorpay_payment_id,
             period_end.isoformat()),
        )
        await conn.commit()
        return cur.lastrowid


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


async def can_submit_claim(account_id: int) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    Priority order:
      1. Active subscription (all tiers) — quota enforced per quarter.
      2. Per-claim purchase (status='paid', no linked_claim_id yet) — exactly 1 claim.
    """
    sub = await get_active_subscription(account_id)
    if sub:
        plan = sub["plan"]
        limit = PLAN_LIMITS.get(plan, {}).get("claims_per_quarter")
        if limit is None:
            return True, "ok"  # platinum / unlimited

        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM nidaan_plan_quota WHERE account_id = ?", (account_id,)
            )
            quota = await cur.fetchone()

        window_start = date.today() - timedelta(days=90)  # quarter = 90 days
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
    """Upsert the rolling 90-day quota counter (call inside the same connection as claim insert)."""
    today = date.today().isoformat()
    window_start = (date.today() - timedelta(days=90)).isoformat()  # quarter = 90 days
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
    intermediary_code: str = "",
    intermediary_name: str = "",
) -> tuple[Optional[int], str]:
    """
    Submit a new claim after quota check.
    Returns (claim_id, status_msg).
    For per-claim users, links the resulting claim_id back to their purchase.

    intermediary_code/intermediary_name: as printed on the policy. Required at
    intake for legal correspondence (IRDAI compliance).
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
                claim_event_date, type_specific, notes_from_agent,
                intermediary_code, intermediary_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_id, user_id, claim_type, insured_name, insured_phone,
             insured_email, insurer_name, policy_no, disputed_amount,
             claim_event_date, type_specific_json, notes_from_agent,
             (intermediary_code or "").strip(), (intermediary_name or "").strip()),
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

        # 6. Quick top-line numbers
        total_claims = (await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_claims")).fetchone())[0]
        open_claims = (await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_claims WHERE status NOT IN "
            "('resolved_won','resolved_lost','closed','withdrawn')")).fetchone())[0]
        active_subs = (await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_subscriptions WHERE status='active'")).fetchone())[0]

        # 7. Claims by status (everyone — small dataset, useful for all roles).
        cur = await conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM nidaan_claims "
            "GROUP BY status ORDER BY cnt DESC")
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

            # 9. Workload by active staff member.
            cur = await conn.execute(
                "SELECT s.staff_id, s.name, s.role, "
                "       COUNT(CASE WHEN t.status_slug NOT IN "
                "         ('completed','cancelled') THEN 1 END) AS open_tasks, "
                "       COUNT(CASE WHEN t.sla_due_at IS NOT NULL "
                "         AND t.sla_due_at < datetime('now') "
                "         AND t.status_slug NOT IN ('completed','cancelled') "
                "         THEN 1 END) AS overdue_tasks "
                "FROM nidaan_staff s "
                "LEFT JOIN nidaan_tasks t ON t.assigned_to_staff_id = s.staff_id "
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
                             due_date: Optional[str] = None, description: str = "") -> int:
    if priority not in QUICK_TASK_PRIORITIES:
        priority = "normal"
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_quick_tasks "
            "(title, description, assigned_to_staff_id, created_by_staff_id, "
            " priority, claim_id, due_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title.strip(), description.strip(), assigned_to_staff_id,
             created_by_staff_id, priority, claim_id, due_date))
        await conn.commit()
        return cur.lastrowid


async def get_quick_task(quick_task_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT q.*, "
            "       a.name AS assignee_name, a.role AS assignee_role, "
            "       a.phone AS assignee_phone, a.email AS assignee_email, "
            "       cr.name AS creator_name, cr.role AS creator_role, "
            "       c.insured_name "
            "FROM nidaan_quick_tasks q "
            "LEFT JOIN nidaan_staff a  ON a.staff_id = q.assigned_to_staff_id "
            "LEFT JOIN nidaan_staff cr ON cr.staff_id = q.created_by_staff_id "
            "LEFT JOIN nidaan_claims c ON c.claim_id = q.claim_id "
            "WHERE q.quick_task_id = ?", (quick_task_id,))).fetchone()
        return dict(row) if row else None


async def list_quick_tasks(*, status: Optional[str] = None,
                            assigned_to_staff_id: Optional[int] = None,
                            claim_id: Optional[int] = None,
                            include_done: bool = False,
                            limit: int = 100) -> list[dict]:
    where, params = [], []
    if status:
        where.append("q.status = ?"); params.append(status)
    elif not include_done:
        where.append("q.status NOT IN ('done','cancelled')")
    if assigned_to_staff_id is not None:
        where.append("q.assigned_to_staff_id = ?"); params.append(assigned_to_staff_id)
    if claim_id is not None:
        where.append("q.claim_id = ?"); params.append(claim_id)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT q.*, "
            "       a.name AS assignee_name, a.role AS assignee_role, "
            "       cr.name AS creator_name, "
            "       c.insured_name "
            "FROM nidaan_quick_tasks q "
            "LEFT JOIN nidaan_staff a  ON a.staff_id = q.assigned_to_staff_id "
            "LEFT JOIN nidaan_staff cr ON cr.staff_id = q.created_by_staff_id "
            "LEFT JOIN nidaan_claims c ON c.claim_id = q.claim_id "
            + clause +
            " ORDER BY "
            "   CASE q.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
            "                   WHEN 'normal' THEN 2 ELSE 3 END, "
            "   q.created_at DESC LIMIT ?", params + [limit])
        return [dict(r) for r in await cur.fetchall()]


async def update_quick_task_status(quick_task_id: int, status: str) -> bool:
    if status not in QUICK_TASK_STATUSES:
        return False
    done_clause = ", completed_at = CURRENT_TIMESTAMP" if status == "done" else ""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE nidaan_quick_tasks SET status = ?, "
            f"updated_at = CURRENT_TIMESTAMP{done_clause} "
            "WHERE quick_task_id = ?", (status, quick_task_id))
        await conn.commit()
    return True


async def reassign_quick_task(quick_task_id: int, assignee_staff_id: Optional[int]) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_quick_tasks SET assigned_to_staff_id = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE quick_task_id = ?",
            (assignee_staff_id, quick_task_id))
        await conn.commit()
    return True


async def add_quick_task_note(*, quick_task_id: int, staff_id: int, note: str,
                                parent_note_id: Optional[int] = None) -> int:
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
            "(quick_task_id, staff_id, note, parent_note_id) VALUES (?, ?, ?, ?)",
            (quick_task_id, staff_id, note.strip(), parent_note_id))
        await conn.commit()
        return cur.lastrowid


async def list_quick_task_notes(quick_task_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT n.*, s.name AS staff_name, s.role AS staff_role "
            "FROM nidaan_quick_task_notes n "
            "LEFT JOIN nidaan_staff s ON s.staff_id = n.staff_id "
            "WHERE n.quick_task_id = ? ORDER BY n.created_at ASC",
            (quick_task_id,))
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
    "silver":          {"amount_paise": 150000,  "display": "₹1,500/quarter",  "period_days": 92},
    "gold":            {"amount_paise": 300000,  "display": "₹3,000/quarter",  "period_days": 92},
    "platinum":        {"amount_paise": 600000,  "display": "₹6,000/quarter",  "period_days": 92},
    # Annual plans — ~10% savings vs 4 quarters
    "silver_annual":   {"amount_paise": 540000,  "display": "₹5,400/year",     "period_days": 365},
    "gold_annual":     {"amount_paise": 1080000, "display": "₹10,800/year",    "period_days": 365},
    "platinum_annual": {"amount_paise": 2160000, "display": "₹21,600/year",    "period_days": 365},
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
    try:
        import time
        receipt = f"nidaan_{account_id}_{plan}_{int(time.time())}"
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.razorpay.com/v1/orders",
                auth=(rzp_key_id, rzp_key_secret),
                json={
                    "amount": info["amount_paise"],
                    "currency": "INR",
                    "receipt": receipt[:40],   # Razorpay receipt max 40 chars
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
                "amount": info["amount_paise"],
                "plan": plan,
                "amount_display": info["display"],
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

    # Find or create Sarathi tenant by email
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT tenant_id FROM tenants WHERE email=? LIMIT 1", (email,)
        )
        row = await cur.fetchone()
        if row:
            tenant_id = row["tenant_id"]
            # Update plan + source + expiry + reactivate (covers expired/trial tenants)
            await conn.execute(
                """UPDATE tenants
                   SET plan=?, plan_source='nidaan_bundle', bundled_until=?,
                       subscription_status='active', updated_at=CURRENT_TIMESTAMP
                   WHERE tenant_id=?""",
                (sarathi_plan, bundled_until, tenant_id),
            )
        else:
            # Create a new Sarathi tenant (they'll login via magic link from Nidaan dashboard)
            cur2 = await conn.execute(
                """INSERT INTO tenants
                       (owner_name, firm_name, email, phone,
                        plan, plan_source, bundled_until, subscription_status)
                   VALUES (?, ?, ?, ?, ?, 'nidaan_bundle', ?, 'active')""",
                (account["owner_name"], account["firm_name"] or "", email,
                 account["phone"] or "", sarathi_plan, bundled_until),
            )
            tenant_id = cur2.lastrowid
            # Create owner agent so the tenant is usable immediately on first login
            tg_placeholder = f"web_{tenant_id}"
            await conn.execute(
                """INSERT INTO agents
                       (tenant_id, telegram_id, name, phone, email, role, lang)
                   VALUES (?, ?, ?, ?, ?, 'owner', 'en')""",
                (tenant_id, tg_placeholder, account["owner_name"],
                 account["phone"] or "", email),
            )
        await conn.commit()

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
    Create a Razorpay recurring subscription for quarterly Nidaan plans.
    Annual plans are not supported here — use create_nidaan_razorpay_order for those.
    Returns {subscription_id, razorpay_key_id, plan, amount_display, ...}
    """
    import httpx, time
    if plan.endswith("_annual"):
        return {"error": "Annual plans use one-time payment. Use create_nidaan_razorpay_order."}

    info = NIDAAN_RAZORPAY_PLANS.get(plan)
    if not info:
        return {"error": f"Unknown plan: {plan}"}

    # Ensure Razorpay plan exists for this plan key
    razorpay_plan_id = _nidaan_plan_ids.get(plan)
    if not razorpay_plan_id:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.razorpay.com/v1/plans?count=100",
                    auth=(rzp_key_id, rzp_key_secret), timeout=15.0,
                )
                for p in r.json().get("items", []):
                    if p.get("notes", {}).get("nidaan_plan") == plan:
                        razorpay_plan_id = p["id"]
                        _nidaan_plan_ids[plan] = razorpay_plan_id
                        break
        except Exception as e:
            logger.warning("Nidaan plan lookup failed for %s: %s", plan, e)

    if not razorpay_plan_id:
        # Create the Razorpay plan now
        rzp_period = "quarterly"
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.razorpay.com/v1/plans",
                    auth=(rzp_key_id, rzp_key_secret),
                    json={
                        "period": rzp_period,
                        "interval": 1,
                        "item": {
                            "name": f"Nidaan {plan.title()} Plan",
                            "amount": info["amount_paise"],
                            "currency": "INR",
                            "description": info["display"],
                        },
                        "notes": {"nidaan_plan": plan, "product": "nidaan"},
                    },
                    timeout=20.0,
                )
                res = r.json()
                if "id" in res:
                    razorpay_plan_id = res["id"]
                    _nidaan_plan_ids[plan] = razorpay_plan_id
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
                    "total_count": 40,  # up to 10 years of quarters
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
                "amount_display": info["display"],
                "razorpay_key_id": rzp_key_id,
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
    period_days = plan_info.get("period_days", 92)
    amount_paise = plan_info.get("amount_paise", 0)

    await create_subscription(
        account_id=account_id,
        plan=plan,
        amount_paid=amount_paise // 100,
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
    plan_info = NIDAAN_RAZORPAY_PLANS.get(plan, {})
    period_days = plan_info.get("period_days", 92)
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
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT bundled_until, plan_source FROM tenants WHERE tenant_id=?",
            (sarathi_tid,))).fetchone()
        if not row:
            return None
        cur_bu = (row["bundled_until"] or "")
        # Only shorten — never extend. If the existing grace is already
        # shorter than the new one, leave it alone.
        if cur_bu and cur_bu <= grace_until:
            return sarathi_tid
        await conn.execute(
            """UPDATE tenants
               SET bundled_until=?, lifetime_trial_used=1,
                   updated_at=CURRENT_TIMESTAMP
               WHERE tenant_id=? AND plan_source='nidaan_bundle'""",
            (grace_until, sarathi_tid))
        await conn.commit()
    logger.info("Bundle teardown: tenant=%d → bundled_until=%s reason=%s",
                sarathi_tid, grace_until, reason)
    return sarathi_tid


async def find_bundles_ending_in(days_from_now: int) -> list[dict]:
    """Scheduler source for T-4 / T-2 / T-0 nudges. Returns tenants whose
    bundled_until matches today + N days exactly (so each day's run hits a
    fresh cohort, no duplicates without external bookkeeping).
    """
    target = (date.today() + timedelta(days=int(days_from_now))).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT tenant_id, firm_name, owner_name, email, phone, plan, "
            "       bundled_until "
            "FROM tenants WHERE plan_source='nidaan_bundle' "
            "AND date(bundled_until) = ?", (target,))
        return [dict(r) for r in await cur.fetchall()]


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


# =============================================================================
#  STAFF AUTH & MANAGEMENT  (super_admin / sub_super_admin / team_member)
# =============================================================================

STAFF_ROLES = ("super_admin", "sub_super_admin", "team_member")
_STAFF_JWT_SUFFIX = ":nidaan_staff"


def _staff_jwt_secret() -> str:
    base = os.environ.get("JWT_SECRET", "change-me-in-production")
    return base + _STAFF_JWT_SUFFIX


def create_staff_token(staff_id: int, role: str, name: str) -> str:
    import jwt as _jwt
    payload = {
        "sub": str(staff_id),
        "role": role,
        "name": name,
        "typ": "nidaan_staff",
        "iat": datetime.utcnow(),
    }
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
    created_by: Optional[int] = None,
) -> Optional[int]:
    """Create a staff account. Returns staff_id or None on duplicate email."""
    if role not in STAFF_ROLES:
        raise ValueError(f"Invalid role: {role}")
    pw_hash = _hash_password(password)
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cur = await conn.execute(
                """INSERT INTO nidaan_staff (name, email, password_hash, role, created_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, email.lower().strip(), pw_hash, role, created_by),
            )
            await conn.commit()
            return cur.lastrowid
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


async def get_staff_by_id(staff_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT staff_id,name,email,role,status,created_at,last_login_at,"
            "       phone,saved_official_numbers_at "
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
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if include_inactive:
            cur = await conn.execute(
                "SELECT staff_id,name,email,role,status,created_at,last_login_at "
                "FROM nidaan_staff ORDER BY created_at DESC"
            )
        else:
            cur = await conn.execute(
                "SELECT staff_id,name,email,role,status,created_at,last_login_at "
                "FROM nidaan_staff WHERE status='active' ORDER BY created_at DESC"
            )
        return [dict(r) for r in await cur.fetchall()]


async def update_staff(staff_id: int, name: str = None, role: str = None,
                       status: str = None, password: str = None) -> bool:
    fields, vals = [], []
    if name is not None:
        fields.append("name=?"); vals.append(name)
    if role is not None:
        if role not in STAFF_ROLES:
            raise ValueError(f"Invalid role: {role}")
        fields.append("role=?"); vals.append(role)
    if status is not None:
        fields.append("status=?"); vals.append(status)
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
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Fetch claims for ops portal. team_member sees only their assigned claims."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        conditions = []
        params: list = []

        if role == "team_member":
            conditions.append("c.assigned_to_staff_id=?")
            params.append(staff_id)
        elif assigned_to is not None:
            conditions.append("c.assigned_to_staff_id=?")
            params.append(assigned_to)

        if status:
            conditions.append("c.status=?")
            params.append(status)
        if claim_type:
            conditions.append("c.claim_type=?")
            params.append(claim_type)
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
                    s.name AS assigned_staff_name
               FROM nidaan_claims c
               JOIN nidaan_accounts a ON a.account_id = c.account_id
               LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id
               {where}
               ORDER BY c.created_at DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        )
        return [dict(r) for r in await cur.fetchall()]


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


# =============================================================================
#  OPS: NOTES
# =============================================================================

async def add_claim_note(claim_id: int, staff_id: int, note: str) -> int:
    """Add an internal note. Returns note_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_claim_notes (claim_id, staff_id, note) VALUES (?,?,?)",
            (claim_id, staff_id, note),
        )
        await conn.commit()
        return cur.lastrowid


async def get_claim_notes(claim_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT n.*, s.name AS staff_name, s.role AS staff_role
               FROM nidaan_claim_notes n
               JOIN nidaan_staff s ON s.staff_id = n.staff_id
               WHERE n.claim_id=? ORDER BY n.created_at ASC""",
            (claim_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


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

        # Active vs churned
        cur = await conn.execute(
            "SELECT status, COUNT(*) as cnt FROM nidaan_subscriptions GROUP BY status"
        )
        sub_by_status = {r["status"]: r["cnt"] for r in await cur.fetchall()}

        total_all = total_sub + total_d2c
        return {
            "total_subscription_revenue": total_sub,
            "total_d2c_revenue": total_d2c,
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
    return await create_account(owner_name, email, phone, tmp_pw, firm_name)


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
        await conn.commit()


async def save_claim_document(
    account_id: int,
    stored_name: str,
    original_name: str,
    file_size: int,
    mime_type: str,
    purchase_id: Optional[int] = None,
    claim_id: Optional[int] = None,
) -> int:
    """Record a newly uploaded document. Returns doc_id."""
    await ensure_claim_documents_table()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_claim_documents
               (account_id, purchase_id, claim_id, stored_name, original_name, file_size, mime_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (account_id, purchase_id, claim_id, stored_name, original_name, file_size, mime_type),
        )
        await conn.commit()
        return cur.lastrowid


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
