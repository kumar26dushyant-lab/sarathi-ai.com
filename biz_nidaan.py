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
import re
import secrets
from datetime import datetime, date, timedelta
from typing import Optional

import aiosqlite

import biz_platform_bridge as bridge  # Sarathi ⇄ Nidaan boundary (tenants/agents access)

logger = logging.getLogger("sarathi.nidaan")

DB_PATH = os.environ.get("DB_PATH", "sarathi_biz.db")

# ── Plan limits ───────────────────────────────────────────────────────────────
PLAN_LIMITS: dict[str, dict] = {
    # Monthly plans: Silver 3 claims/mo (≤₹5L each), Gold 10 claims/mo (≤₹10L),
    # Platinum unlimited (≤₹50L). Claim quota window is 30 days (see can_submit_claim).
    "silver":          {"max_users": 1,    "claims_per_month": 3,    "sarathi_bundle": True},
    "gold":            {"max_users": 5,    "claims_per_month": 10,   "sarathi_bundle": True},
    "platinum":        {"max_users": None, "claims_per_month": None, "sarathi_bundle": True},
    # Annual variants — same monthly claim allowance, billed yearly
    "silver_annual":   {"max_users": 1,    "claims_per_month": 3,    "sarathi_bundle": True},
    "gold_annual":     {"max_users": 5,    "claims_per_month": 10,   "sarathi_bundle": True},
    "platinum_annual": {"max_users": None, "claims_per_month": None, "sarathi_bundle": True},
}

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


async def create_account(
    owner_name: str,
    email: str,
    phone: str,
    password: str,
    firm_name: str = "",
    branch_code: str = "",
) -> Optional[int]:
    """Create a new Nidaan account. Returns account_id or None on duplicate email.
    branch_code attributes the sale to an affiliate city branch (already validated
    by the caller; stored as-is)."""
    pw_hash = _hash_password(password)
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cur = await conn.execute(
                """INSERT INTO nidaan_accounts
                   (owner_name, email, phone, password_hash, firm_name, branch_code)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (owner_name, email.lower().strip(), phone, pw_hash, firm_name,
                 (branch_code or "").strip().upper()),
            )
            await conn.commit()
            return cur.lastrowid
    except aiosqlite.IntegrityError:
        logger.warning("nidaan create_account: duplicate email %s", email)
        return None


# ── Affiliate branches (offline city vendors selling subscriptions) ──────────
# An account is "paid" for a branch if it has an active subscription OR a
# per-claim review that progressed past pending_payment (i.e. they actually paid).
_BRANCH_PAID_EXISTS = (
    "(EXISTS(SELECT 1 FROM nidaan_subscriptions s "
    "        WHERE s.account_id=a.account_id AND s.status='active') "
    " OR EXISTS(SELECT 1 FROM nidaan_per_claim_purchase p "
    "           WHERE p.account_id=a.account_id "
    "             AND p.status NOT IN ('pending_payment','cancelled')))"
)


async def list_branches(include_disabled: bool = True) -> list[dict]:
    """All branches with live signup / paid / unpaid attribution counts."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        where = "" if include_disabled else "WHERE b.status='active'"
        cur = await conn.execute(
            f"""SELECT b.branch_code, b.city, b.name, b.contact_email, b.status, b.created_at,
                       (SELECT COUNT(*) FROM nidaan_accounts a
                        WHERE UPPER(a.branch_code)=b.branch_code) AS signups,
                       (SELECT COUNT(*) FROM nidaan_accounts a
                        WHERE UPPER(a.branch_code)=b.branch_code AND {_BRANCH_PAID_EXISTS}) AS paid
                FROM nidaan_branches b {where}
                ORDER BY b.city, b.branch_code""")
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["accounts"] = r.get("signups", 0)   # back-compat alias
        r["unpaid"] = max(0, int(r.get("signups", 0)) - int(r.get("paid", 0)))
    return rows


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


async def set_account_branch(account_id: int, code: str) -> bool:
    """Attribute an account to a branch (used when the code is supplied on the
    claim form rather than at signup). Caller should ensure the code is valid."""
    code = (code or "").strip().upper()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_accounts SET branch_code=? WHERE account_id=?", (code, account_id))
        await conn.commit()
        return cur.rowcount > 0


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
                        contact_email: Optional[str] = None) -> bool:
    """Update a branch's status and/or contact email."""
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
      1. Active subscription (all tiers) — quota enforced per quarter.
      2. Per-claim purchase (status='paid', no linked_claim_id yet) — exactly 1 claim.
    """
    sub = await get_active_subscription(account_id)
    if sub:
        plan = sub["plan"]
        limit = PLAN_LIMITS.get(plan, {}).get("claims_per_month")
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
    payment_status: str = "subscription",
    skip_eligibility: bool = False,
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

    type_specific_json = json.dumps(type_specific or {})
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_claims
               (account_id, user_id, claim_type, insured_name, insured_phone,
                insured_email, insurer_name, policy_no, disputed_amount,
                claim_event_date, policy_inception_date, tpa_name, type_specific,
                notes_from_agent, intermediary_code, intermediary_name, payment_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_id, user_id, claim_type, insured_name, insured_phone,
             insured_email, insurer_name, policy_no, disputed_amount,
             claim_event_date, (policy_inception_date or None), (tpa_name or "").strip(),
             type_specific_json, notes_from_agent,
             (intermediary_code or "").strip(), (intermediary_name or "").strip(),
             payment_status),
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

        # 6. Quick top-line numbers.
        # NOTE: only count claims whose account still exists, so these match the
        # All-Claims table (which inner-joins nidaan_accounts). Orphaned claims
        # left by a deleted account must not inflate the count.
        _live = ("EXISTS(SELECT 1 FROM nidaan_accounts a "
                 "WHERE a.account_id=nidaan_claims.account_id)")
        total_claims = (await (await conn.execute(
            f"SELECT COUNT(*) FROM nidaan_claims WHERE {_live}")).fetchone())[0]
        open_claims = (await (await conn.execute(
            f"SELECT COUNT(*) FROM nidaan_claims WHERE {_live} AND status NOT IN "
            "('resolved_won','resolved_lost','closed','withdrawn')")).fetchone())[0]
        active_subs = (await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_subscriptions WHERE status='active'")).fetchone())[0]

        # 7. Claims by status (everyone — small dataset, useful for all roles).
        cur = await conn.execute(
            f"SELECT status, COUNT(*) AS cnt FROM nidaan_claims WHERE {_live} "
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
                             complainant_phone: Optional[str] = None) -> int:
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
                              note="requires approval" if requires_approval else "")
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
                                    changed_by: int) -> list[str]:
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
                                  changed_by=changed_by, note=k)
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
    """{note_id: [ {stored_name, original_name}, … ]} for a task's comments."""
    out: dict = {}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT note_id, stored_name, original_name FROM nidaan_quick_task_attachments "
            "WHERE quick_task_id=? ORDER BY attachment_id ASC", (quick_task_id,))).fetchall()
        for r in rows:
            out.setdefault(r["note_id"], []).append(
                {"stored_name": r["stored_name"], "original_name": r["original_name"]})
    return out


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
            f"SELECT staff_id, name, role, phone, "
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
                                   changed_by: int, note: str = "") -> bool:
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
                              to_value=decision, changed_by=changed_by, note=note)
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
    if status:
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
            "       a.name AS assignee_name, a.role AS assignee_role, "
            "       cr.name AS creator_name, "
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
    rows["overdue"] = overdue
    rows["pending_approval"] = pending_appr
    return rows


async def _log_quick_task(conn, quick_task_id: int, action: str,
                          from_value: str = None, to_value: str = None,
                          changed_by: int = None, note: str = "") -> None:
    """Append an immutable history row (uses an existing open connection)."""
    await conn.execute(
        "INSERT INTO nidaan_quick_task_log "
        "(quick_task_id, action, from_value, to_value, changed_by_staff_id, note) "
        "VALUES (?,?,?,?,?,?)",
        (quick_task_id, action, from_value, to_value, changed_by, note or ""))


async def update_quick_task_status(quick_task_id: int, status: str,
                                   changed_by: int = None, note: str = "") -> bool:
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
                              changed_by=changed_by, note=note)
        await conn.commit()
    return True


async def reassign_quick_task(quick_task_id: int, assignee_staff_id: Optional[int],
                              changed_by: int = None, note: str = "") -> bool:
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
                              changed_by=changed_by, note=note)
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
                                start_time: str = "", end_time: str = "") -> int:
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
            " handover_notes, cover_staff_id, start_time, end_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (staff_id, start_date, end_date, (reason or "").strip(), leave_type,
             half_period, (handover_notes or "").strip(), cover_staff_id,
             (start_time or "").strip(), (end_time or "").strip()))
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
                                attachment_original_name: Optional[str] = None) -> int:
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
            " attachment_original_name) VALUES (?, ?, ?, ?, ?, ?)",
            (quick_task_id, staff_id, note.strip(), parent_note_id,
             attachment_stored_name, attachment_original_name))
        await conn.commit()
        return cur.lastrowid


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
    "gold":            {"amount_paise": 100000,  "display": "₹1,000/month",  "period_days": 30,  "period": "monthly", "interval": 1, "tag": "gold_m1"},
    "platinum":        {"amount_paise": 200000,  "display": "₹2,000/month",  "period_days": 30,  "period": "monthly", "interval": 1, "tag": "platinum_m1"},
    # Annual plans — recurring yearly, 10× monthly (2 months free)
    "silver_annual":   {"amount_paise": 500000,  "display": "₹5,000/year",   "period_days": 365, "period": "yearly",  "interval": 1, "tag": "silver_annual_m1"},
    "gold_annual":     {"amount_paise": 1000000, "display": "₹10,000/year",  "period_days": 365, "period": "yearly",  "interval": 1, "tag": "gold_annual_m1"},
    "platinum_annual": {"amount_paise": 2000000, "display": "₹20,000/year",  "period_days": 365, "period": "yearly",  "interval": 1, "tag": "platinum_annual_m1"},
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

    # Ensure Razorpay plan exists for this plan key (matched by the versioned tag).
    tag = info.get("tag", plan)
    razorpay_plan_id = _nidaan_plan_ids.get(plan)
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
                        _nidaan_plan_ids[plan] = razorpay_plan_id
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
                            "name": f"Nidaan {plan.title()} Plan",
                            "amount": info["amount_paise"],
                            "currency": "INR",
                            "description": info["display"],
                        },
                        "notes": {"nidaan_plan": tag, "product": "nidaan"},
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
            kid = os.getenv("RAZORPAY_KEY_ID", ""); ksec = os.getenv("RAZORPAY_KEY_SECRET", "")
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
}


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
                return sid
            cur = await conn.execute(
                """INSERT INTO nidaan_staff (name, email, password_hash, role, phone, notify_email, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, email, pw_hash, role, phone, notify_email, created_by),
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
            "       phone,notify_email,saved_official_numbers_at "
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
            "created_at,last_login_at")
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


async def soft_delete_staff(staff_id: int) -> bool:
    """Archive a staffer (reversible). Super admins are protected. Also flips
    status to inactive so every existing status='active' query excludes them."""
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
    """Bulk-archive every currently-inactive staffer except super admins.
    Returns the number archived."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_staff SET deleted_at=CURRENT_TIMESTAMP "
            "WHERE status='inactive' AND deleted_at IS NULL AND role != 'super_admin'")
        await conn.commit()
        return cur.rowcount


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
            conditions.append("c.assigned_to_staff_id=?")
            params.append(staff_id)
        elif assigned_to is not None:
            conditions.append("c.assigned_to_staff_id=?")
            params.append(assigned_to)

        if status:
            conditions.append("c.status=?")
            params.append(status)
        if payment_status:
            conditions.append("c.payment_status=?")
            params.append(payment_status)
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
                    a.branch_code,
                    s.name AS assigned_staff_name,
                    (SELECT COUNT(*) FROM nidaan_followups f
                     WHERE f.claim_id = c.claim_id AND f.status = 'pending') AS pending_tasks
               FROM nidaan_claims c
               JOIN nidaan_accounts a ON a.account_id = c.account_id
               LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id
               {where}
               ORDER BY (c.payment_status='unpaid_lead') ASC, c.created_at DESC
               LIMIT ? OFFSET ?""",
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


# ── Subscriber ⇄ ops messaging (per claim) ───────────────────────────────────
async def list_claim_messages(claim_id: int, limit: int = 200) -> list[dict]:
    """Full message thread for a claim (both directions), oldest first, with the
    staff member's name resolved for display."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT m.message_id, m.sender_type, m.sender_staff_id, m.content,
                      m.created_at, m.read_by_subscriber_at, m.read_by_staff_at,
                      s.name AS staff_name
               FROM nidaan_messages m
               LEFT JOIN nidaan_staff s ON s.staff_id = m.sender_staff_id
               WHERE m.claim_id=? ORDER BY m.message_id ASC LIMIT ?""",
            (claim_id, limit))).fetchall()
        return [dict(r) for r in rows]


async def add_claim_message(claim_id: int, sender_type: str, content: str,
                            subscriber_id: Optional[int] = None,
                            staff_id: Optional[int] = None,
                            source_channel: str = "dashboard") -> int:
    """Append a message to a claim thread. sender_type is 'subscriber' or 'staff'."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_messages
                 (claim_id, sender_type, sender_subscriber_id, sender_staff_id,
                  content, source_channel)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (claim_id, sender_type, subscriber_id, staff_id, content.strip(), source_channel))
        await conn.commit()
        return cur.lastrowid


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
