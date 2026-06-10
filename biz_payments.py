# =============================================================================
#  biz_payments.py — Sarathi-AI: Razorpay Payment & Subscription Engine
# =============================================================================
#
#  Handles:
#    - Razorpay subscription plan creation (idempotent)
#    - Checkout session generation
#    - Webhook verification & processing
#    - Auto-activation on successful payment
#    - Subscription status sync
#
# =============================================================================

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import re

import httpx
from fastapi.responses import JSONResponse

import biz_database as db
import biz_email as email_svc

logger = logging.getLogger("sarathi.payments")


async def _notify_payment_email(email: str, email_coro):
    """Send payment email with error logging (used as create_task target)."""
    try:
        result = await email_coro
        if not result:
            logger.warning("📧 Payment email not sent (returned False)")
    except Exception as e:
        logger.error("📧 Payment email failed: %s", e)


def _escape_md_v2(text: str) -> str:
    """Escape text for Telegram MarkdownV2."""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', str(text))


async def _notify_payment_success(tid: int, plan_key: str, amount_paise: int = 0,
                                   payment_id: str = "", expires: str = "",
                                   founding_discount: bool = False,
                                   original_amount: int = 0):
    """Send payment success notification via Telegram + Email."""
    tenant = await db.get_tenant(tid)
    if not tenant:
        return
    plan_info = PLANS.get(plan_key, {})
    plan_name = plan_info.get("name", plan_key)
    amount_str = f"₹{amount_paise / 100:,.0f}" if amount_paise else plan_info.get("amount_display", "")
    firm = tenant.get("firm_name", "")
    owner = tenant.get("owner_name", "")
    next_due = ""
    if expires:
        try:
            next_due = datetime.fromisoformat(expires).strftime("%d %b %Y")
        except ValueError:
            next_due = expires

    # Telegram notification
    owner_tg = tenant.get("owner_telegram_id")
    if owner_tg:
        from biz_reminders import _send_telegram
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        founding_line = ""
        if founding_discount:
            founding_line = "\n🏆 *Founding Customer — 20% Discount Applied\\!*\n"
        msg = (
            "✅ *Payment Successful\\!*\n\n"
            f"Plan: *{_escape_md_v2(plan_name)}*\n"
            f"Amount: *{_escape_md_v2(amount_str)}*\n"
            f"{founding_line}"
            f"Firm: {_escape_md_v2(firm)}\n"
        )
        if next_due:
            msg += f"Next billing: {_escape_md_v2(next_due)}\n"
        msg += "\n🎉 All features are now unlocked\\!"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Dashboard", url=f"{SERVER_URL}/dashboard")]
        ])
        try:
            await _send_telegram(owner_tg, msg, reply_markup=kb)
        except Exception as e:
            logger.error("Failed to send payment success Telegram: %s", e)

    # Email receipt
    email = tenant.get("email")
    if email:
        import asyncio
        original_str = f"₹{original_amount / 100:,.0f}" if original_amount else ""
        asyncio.create_task(_notify_payment_email(email,
            email_svc.send_payment_receipt(
                email, owner, firm, plan_name, amount_str,
                payment_id or "—", next_due,
                founding_discount=founding_discount,
                original_amount=original_str)))

# =============================================================================
#  CONFIG
# =============================================================================

RAZORPAY_KEY_ID = ""
RAZORPAY_KEY_SECRET = ""
SERVER_URL = ""
TEST_MODE = False  # Auto-detected from rzp_test_ key prefix

# Plan definitions: plan_key → {name, amount_paise, period, interval, max_agents, period_days}
# NOTE: max_agents is admin-inclusive (admin + advisor seats)
# period_days: how many days of access this payment grants (30 for monthly, 365 for annual)
PLANS = {
    "individual": {
        "name": "Solo Advisor",
        "amount_paise": 19900,       # ₹199/mo
        "amount_display": "₹199/mo",
        "period": "monthly",
        "interval": 1,
        "max_agents": 1,
        "period_days": 30,
        "description": "1 Advisor · Unlimited Leads · Full CRM",
    },
    "team": {
        "name": "Team",
        "amount_paise": 79900,       # ₹799/mo
        "amount_display": "₹799/mo",
        "period": "monthly",
        "interval": 1,
        "max_agents": 6,
        "period_days": 30,
        "description": "Admin + 5 Advisors · WhatsApp · Custom Branding",
    },
    "enterprise": {
        "name": "Enterprise",
        "amount_paise": 199900,      # ₹1,999/mo
        "amount_display": "₹1,999/mo",
        "period": "monthly",
        "interval": 1,
        "max_agents": 26,
        "period_days": 30,
        "description": "Admin + 25 Advisors · API · Dedicated Support",
    },
    # Annual plans — ~17% savings vs 12 monthly payments
    "individual_annual": {
        "name": "Solo Advisor (Annual)",
        "amount_paise": 199000,      # ₹1,990/yr (saves ~₹400 vs 12×₹199)
        "amount_display": "₹1,990/yr",
        "period": "yearly",
        "interval": 1,
        "max_agents": 1,
        "period_days": 365,
        "description": "1 Advisor · Unlimited Leads · Full CRM · Best Value",
    },
    "team_annual": {
        "name": "Team (Annual)",
        "amount_paise": 799000,      # ₹7,990/yr (saves ~₹1,600 vs 12×₹799)
        "amount_display": "₹7,990/yr",
        "period": "yearly",
        "interval": 1,
        "max_agents": 6,
        "period_days": 365,
        "description": "Admin + 5 Advisors · WhatsApp · Custom Branding · Best Value",
    },
    "enterprise_annual": {
        "name": "Enterprise (Annual)",
        "amount_paise": 1999000,     # ₹19,990/yr (saves ~₹4,000 vs 12×₹1,999)
        "amount_display": "₹19,990/yr",
        "period": "yearly",
        "interval": 1,
        "max_agents": 26,
        "period_days": 365,
        "description": "Admin + 25 Advisors · API · Dedicated Support · Best Value",
    },
}

# Razorpay Plan IDs (populated at startup or first use)
_razorpay_plan_ids: dict = {}  # plan_key → razorpay_plan_id


def init_payments():
    """Load Razorpay credentials from env."""
    global RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, SERVER_URL, TEST_MODE
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
    SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
    TEST_MODE = RAZORPAY_KEY_ID.startswith("rzp_test_")

    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        logger.warning("⚠️ Razorpay credentials not set — payments disabled")
        return False

    mode = "TEST" if TEST_MODE else "LIVE"
    logger.info("💳 Razorpay initialized [%s] (key: %s...)", mode, RAZORPAY_KEY_ID[:12])
    return True


def is_test_mode() -> bool:
    """Check if running with Razorpay test keys."""
    return TEST_MODE


def is_enabled() -> bool:
    """Check if payments are configured."""
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


# =============================================================================
#  RAZORPAY API HELPERS
# =============================================================================

async def _razorpay_request(method: str, endpoint: str,
                            data: dict = None) -> dict:
    """Make an authenticated request to Razorpay API."""
    url = f"https://api.razorpay.com/v1/{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method, url,
            json=data,
            auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            timeout=30.0,
        )
        result = resp.json()
        if resp.status_code >= 400:
            logger.error("Razorpay API error [%s %s]: %s",
                         method, endpoint, result)
        return result


# =============================================================================
#  PLAN MANAGEMENT
# =============================================================================

async def ensure_plans_exist():
    """Create Razorpay Plans if they don't exist. Idempotent."""
    if not is_enabled():
        return

    for plan_key, plan_info in PLANS.items():
        # Check if we already have this plan cached
        if plan_key in _razorpay_plan_ids:
            continue

        # Try to find existing plan by listing
        existing = await _find_existing_plan(plan_key, plan_info)
        if existing:
            _razorpay_plan_ids[plan_key] = existing
            logger.info("📋 Found existing Razorpay plan: %s → %s",
                        plan_key, existing)
            continue

        # Create new plan
        result = await _razorpay_request("POST", "plans", {
            "period": plan_info["period"],
            "interval": plan_info["interval"],
            "item": {
                "name": f"Sarathi-AI {plan_info['name']}",
                "amount": plan_info["amount_paise"],
                "currency": "INR",
                "description": plan_info["description"],
            },
            "notes": {
                "plan_key": plan_key,
                "product": "sarathi-ai-crm",
            },
        })

        if "id" in result:
            _razorpay_plan_ids[plan_key] = result["id"]
            logger.info("✅ Created Razorpay plan: %s → %s",
                        plan_key, result["id"])
        else:
            logger.error("❌ Failed to create plan %s: %s", plan_key, result)


async def _find_existing_plan(plan_key: str, plan_info: dict) -> Optional[str]:
    """Look for an existing Razorpay plan matching our config."""
    try:
        result = await _razorpay_request("GET", "plans?count=50")
        items = result.get("items", []) if isinstance(result, dict) else result if isinstance(result, list) else []
        for p in items:
            item = p.get("item", {})
            notes = p.get("notes", {})
            # Match by notes.plan_key or by name+amount
            if notes.get("plan_key") == plan_key:
                return p["id"]
            if (item.get("amount") == plan_info["amount_paise"] and
                    f"Sarathi-AI {plan_info['name']}" in item.get("name", "")):
                return p["id"]
    except Exception as e:
        logger.error("Error finding plans: %s", e)
    return None


def get_plan_id(plan_key: str) -> Optional[str]:
    """Get the Razorpay Plan ID for a given plan key."""
    return _razorpay_plan_ids.get(plan_key)


# =============================================================================
#  SUBSCRIPTION CREATION
# =============================================================================

async def create_subscription(tenant_id: int, plan_key: str) -> dict:
    """
    Create a Razorpay Subscription for a tenant.
    Returns {subscription_id, short_url, ...} on success.
    """
    if not is_enabled():
        return {"error": "Payments not configured"}

    plan_id = get_plan_id(plan_key)
    if not plan_id:
        # Try to ensure plans exist first
        await ensure_plans_exist()
        plan_id = get_plan_id(plan_key)
        if not plan_id:
            return {"error": f"Plan '{plan_key}' not found in Razorpay"}

    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}

    # Create subscription
    result = await _razorpay_request("POST", "subscriptions", {
        "plan_id": plan_id,
        "total_count": 120,  # max billing cycles (10 years)
        "quantity": 1,
        "notes": {
            "tenant_id": str(tenant_id),
            "firm_name": tenant.get("firm_name", ""),
            "plan_key": plan_key,
            "product": "sarathi-ai-crm",
        },
        "notify_info": {
            "notify_phone": tenant.get("phone", ""),
            "notify_email": tenant.get("email", ""),
        },
    })

    if "id" not in result:
        return {"error": result.get("error", {}).get("description", "Failed to create subscription")}

    sub_id = result["id"]
    short_url = result.get("short_url", "")

    # Save subscription ID to DB
    await db.update_tenant(tenant_id, razorpay_sub_id=sub_id)

    logger.info("💳 Subscription created: tenant=%d plan=%s sub=%s",
                tenant_id, plan_key, sub_id)

    return {
        "subscription_id": sub_id,
        "short_url": short_url,
        "plan_key": plan_key,
        "plan_name": PLANS[plan_key]["name"],
        "amount": PLANS[plan_key]["amount_display"],
        "razorpay_key_id": RAZORPAY_KEY_ID,
    }


# =============================================================================
#  CHECKOUT ORDER (one-time payment alternative)
# =============================================================================

async def create_checkout_order(tenant_id: int, plan_key: str) -> dict:
    """
    Create a Razorpay Order for checkout.
    This is used for the inline checkout flow (Razorpay Checkout.js).
    Applies founding customer discount (20% off) if eligible.
    """
    if not is_enabled():
        return {"error": "Payments not configured"}

    plan_info = PLANS.get(plan_key)
    if not plan_info:
        return {"error": f"Unknown plan: {plan_key}"}

    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}

    # Founding customer discount: 20% off for first year
    amount_paise = plan_info["amount_paise"]
    founding_discount = False
    if tenant.get("founding_discount") == 1:
        discount_until = tenant.get("founding_discount_until", "")
        if discount_until:
            try:
                from datetime import datetime
                if datetime.fromisoformat(discount_until) > datetime.now():
                    amount_paise = int(amount_paise * 0.80)  # 20% off
                    founding_discount = True
                    logger.info("🏆 Founding discount applied: tenant=%d plan=%s ₹%d→₹%d",
                                tenant_id, plan_key, plan_info["amount_paise"]/100, amount_paise/100)
            except ValueError:
                pass

    # Create a Razorpay order
    result = await _razorpay_request("POST", "orders", {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"sarathi_t{tenant_id}_{plan_key}",
        "notes": {
            "tenant_id": str(tenant_id),
            "firm_name": tenant.get("firm_name", ""),
            "plan_key": plan_key,
            "product": "sarathi-ai-crm",
            "founding_discount": "yes" if founding_discount else "no",
        },
    })

    if "id" not in result:
        return {"error": result.get("error", {}).get("description",
                                                      "Failed to create order")}

    return {
        "order_id": result["id"],
        "amount": amount_paise,
        "currency": "INR",
        "plan_key": plan_key,
        "plan_name": plan_info["name"],
        "amount_display": f"₹{amount_paise // 100:,}",
        "original_amount": plan_info["amount_paise"],
        "original_display": plan_info["amount_display"],
        "founding_discount": founding_discount,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "tenant_id": tenant_id,
        "firm_name": tenant.get("firm_name", ""),
        "email": tenant.get("email", ""),
        "phone": tenant.get("phone", ""),
    }


# =============================================================================
#  WEBHOOK VERIFICATION & PROCESSING
# =============================================================================

def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify Razorpay webhook signature using HMAC-SHA256.

    Razorpay webhook signatures are computed with a per-webhook secret that
    is configured separately from the API key secret in the Razorpay
    Dashboard (Settings → Webhooks → Active webhook → Secret).

    Resolution order:
      1. RAZORPAY_WEBHOOK_SECRET (preferred, separate secret per Razorpay docs)
      2. RAZORPAY_KEY_SECRET (legacy fallback; only works if Dashboard's
         webhook secret was set to match the API key secret)
    Either secret can sign successfully; we accept the first match.
    """
    if not signature:
        return False
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
    candidates = []
    if webhook_secret:
        candidates.append(webhook_secret)
    if RAZORPAY_KEY_SECRET and RAZORPAY_KEY_SECRET != webhook_secret:
        candidates.append(RAZORPAY_KEY_SECRET)
    for secret in candidates:
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            return True
    return False


def verify_payment_signature(order_id: str, payment_id: str,
                             signature: str) -> bool:
    """Verify Razorpay payment signature (for Checkout.js flow).

    B5: Removed the literal `test_bypass` shortcut — too risky in production
    even with TEST_MODE detection (a misconfigured TEST key in prod would let
    anyone activate a paid plan for free). All payments must now present a
    valid HMAC signature.
    """
    if not RAZORPAY_KEY_SECRET:
        return False
    if not signature or not order_id or not payment_id:
        return False
    message = f"{order_id}|{payment_id}"
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_subscription_signature(payment_id: str, subscription_id: str,
                                   signature: str) -> bool:
    """Verify Razorpay subscription payment signature.
    Razorpay signs: HMAC-SHA256(payment_id + '|' + subscription_id).
    B5: Removed the literal `test_bypass` shortcut (see verify_payment_signature)."""
    if not RAZORPAY_KEY_SECRET:
        return False
    message = f"{payment_id}|{subscription_id}"
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def verify_subscription_and_activate(tenant_id: int, plan_key: str,
                                            razorpay_payment_id: str,
                                            razorpay_subscription_id: str,
                                            razorpay_signature: str) -> dict:
    """
    Verify Razorpay subscription payment and immediately activate the tenant.
    Called after the user completes subscription checkout — provides instant activation
    while the async webhook (subscription.activated) serves as a durable safety net.
    """
    valid = verify_subscription_signature(
        razorpay_payment_id, razorpay_subscription_id, razorpay_signature
    )
    if not valid:
        logger.warning("❌ Invalid subscription signature for tenant %d", tenant_id)
        return {"error": "Invalid payment signature", "verified": False}

    # Idempotency: skip if already processed (prevents race with webhook)
    if await db.is_payment_processed(razorpay_payment_id):
        logger.info("🔄 Subscription payment %s already processed — skipping duplicate",
                    razorpay_payment_id)
        tenant = await db.get_tenant(tenant_id)
        return {
            "status": "ok", "verified": True,
            "tenant_id": tenant_id,
            "plan": tenant.get("plan", plan_key) if tenant else plan_key,
            "expires": tenant.get("subscription_expires_at", "") if tenant else "",
            "already_processed": True,
        }

    plan_info = PLANS.get(plan_key, {})
    period_days = plan_info.get("period_days", 30)
    max_agents = plan_info.get("max_agents", 1)
    expected_amount = plan_info.get("amount_paise", 0)

    # Founding discount
    founding_discount = False
    tenant = await db.get_tenant(tenant_id)
    if tenant and tenant.get("founding_discount") == 1:
        fd_until = tenant.get("founding_discount_until", "")
        if fd_until:
            try:
                if datetime.fromisoformat(fd_until) > datetime.now():
                    founding_discount = True
                    expected_amount = int(expected_amount * 0.80)
            except ValueError:
                pass

    # Server-side verify: confirm payment status with Razorpay API
    try:
        rz_payment = await _razorpay_request("GET", f"payments/{razorpay_payment_id}")
        rz_status = rz_payment.get("status")
        if rz_status not in ("captured", "authorized"):
            logger.warning("❌ Subscription payment %s status is '%s'",
                           razorpay_payment_id, rz_status)
            return {"error": f"Payment not completed (status: {rz_status})", "verified": False}
    except Exception as e:
        logger.error("Razorpay payment fetch failed for %s: %s", razorpay_payment_id, e)
        # Signature was valid — proceed with activation (Razorpay API may be momentarily down)

    # Record atomically before activating
    inserted = await db.record_payment_processed(
        razorpay_payment_id, tenant_id, plan_key, "subscription_frontend", expected_amount
    )
    if not inserted:
        tenant = await db.get_tenant(tenant_id)
        return {
            "status": "ok", "verified": True, "tenant_id": tenant_id,
            "plan": plan_key, "already_processed": True,
            "expires": tenant.get("subscription_expires_at", "") if tenant else "",
        }

    # Smart expiry: extend from trial end if still in trial
    tenant = await db.get_tenant(tenant_id)
    now = datetime.now()
    trial_end_str = tenant.get("trial_ends_at") if tenant else None
    if trial_end_str:
        try:
            trial_end = datetime.fromisoformat(trial_end_str)
            expires = (max(trial_end, now) + timedelta(days=period_days)).isoformat()
        except ValueError:
            expires = (now + timedelta(days=period_days)).isoformat()
    else:
        expires = (now + timedelta(days=period_days)).isoformat()

    await db.update_tenant(
        tenant_id,
        is_active=1,
        plan=plan_key,
        subscription_status="active",
        subscription_expires_at=expires,
        trial_ends_at=None,
        max_agents=max_agents,
        razorpay_sub_id=razorpay_subscription_id,
    )

    logger.info("✅ Subscription verified & activated: tenant=%d plan=%s sub=%s payment=%s",
                tenant_id, plan_key, razorpay_subscription_id, razorpay_payment_id)

    await db.add_system_event(
        "info", "low", "payment",
        f"Subscription ₹{expected_amount/100:,.0f} for {plan_key}",
        f"tenant={tenant_id} payment={razorpay_payment_id} sub={razorpay_subscription_id} founding={founding_discount}",
        tenant_id=tenant_id)

    # Auto-commission
    try:
        import asyncio
        conv = await db.process_payment_commission(tenant_id, plan_key, razorpay_payment_id, expected_amount)
        if conv and conv.get("commission") and conv.get("affiliate_email"):
            from biz_email import send_affiliate_commission_earned
            asyncio.create_task(send_affiliate_commission_earned(
                conv["affiliate_email"], conv["affiliate_name"],
                conv["commission"], plan_key,
                tenant.get("owner_name", "") if tenant else ""))
    except Exception as e:
        logger.error("Commission error for tenant %d: %s", tenant_id, e)

    original_amount = plan_info.get("amount_paise", 0)
    await _notify_payment_success(tenant_id, plan_key, expected_amount,
                                   razorpay_payment_id, expires,
                                   founding_discount=founding_discount,
                                   original_amount=original_amount)

    return {
        "status": "ok",
        "verified": True,
        "tenant_id": tenant_id,
        "plan": plan_key,
        "expires": expires,
        "subscription_id": razorpay_subscription_id,
    }


async def process_webhook_event(event: str, payload: dict) -> dict:
    """
    Process a Razorpay webhook event.
    Handles: subscription.activated, subscription.charged,
             payment.captured, subscription.cancelled, etc.
    """
    logger.info("📨 Razorpay webhook: %s", event)

    handlers = {
        "subscription.activated": _handle_subscription_activated,
        "subscription.charged": _handle_subscription_charged,
        "subscription.completed": _handle_subscription_completed,
        "subscription.cancelled": _handle_subscription_cancelled,
        "subscription.halted": _handle_subscription_halted,
        "subscription.pending": _handle_subscription_pending,
        "payment.captured": _handle_payment_captured,
        "payment.failed": _handle_payment_failed,
        # B2: Sarathi refund webhook handlers
        "refund.processed": _handle_refund_processed,
        "refund.failed": _handle_refund_failed,
        "refund.created": _handle_refund_processed,  # treat as in-progress
    }

    handler = handlers.get(event)
    if handler:
        return await handler(payload)
    else:
        logger.debug("Unhandled webhook event: %s", event)
        return {"status": "ignored", "event": event}


async def _handle_subscription_activated(payload: dict) -> dict:
    """Subscription started — activate the tenant."""
    sub = payload.get("subscription", {}).get("entity", {})
    return await _activate_tenant_from_sub(sub, "subscription_activated")


async def _handle_subscription_charged(payload: dict) -> dict:
    """Recurring payment received — extend the subscription."""
    sub = payload.get("subscription", {}).get("entity", {})
    return await _activate_tenant_from_sub(sub, "subscription_charged")


async def _handle_subscription_completed(payload: dict) -> dict:
    """All billing cycles complete — deactivate and mark expired."""
    sub = payload.get("subscription", {}).get("entity", {})
    notes = sub.get("notes", {})
    tenant_id = notes.get("tenant_id")
    if tenant_id:
        tid = int(tenant_id)
        await db.update_tenant(
            tid,
            is_active=0,
            subscription_status='expired',
        )
        logger.info("📋 Subscription completed for tenant %d — marked expired", tid)
        # Notify owner
        tenant = await db.get_tenant(tid)
        if tenant:
            if tenant.get('owner_telegram_id'):
                from biz_reminders import _send_telegram
                msg = (
                    "📋 *Subscription Completed*\n\n"
                    f"All billing cycles for *{_escape_md_v2(tenant.get('firm_name', ''))}* "
                    "have been completed\\.\n\n"
                    "Your account is now inactive\\. "
                    "To continue using Sarathi, please resubscribe with /subscribe\\."
                )
                try:
                    await _send_telegram(tenant['owner_telegram_id'], msg)
                except Exception as e:
                    logger.error("Failed to send completed notification: %s", e)
            if tenant.get('email'):
                import asyncio
                asyncio.create_task(_notify_payment_email(tenant['email'],
                    email_svc.send_account_deactivated(
                        tenant['email'], tenant.get('owner_name', ''),
                        tenant.get('firm_name', 'Your firm'))))
    return {"status": "ok", "event": "subscription.completed"}


async def _handle_subscription_cancelled(payload: dict) -> dict:
    """Subscription cancelled — mark as expiring, notify owner."""
    sub = payload.get("subscription", {}).get("entity", {})
    notes = sub.get("notes", {})
    tenant_id = notes.get("tenant_id")
    if tenant_id:
        tid = int(tenant_id)
        # Don't immediately deactivate; let it run until current period ends
        current_end = sub.get("current_end")
        if current_end:
            expires_at = datetime.fromtimestamp(current_end).isoformat()
            await db.update_tenant(tid, subscription_expires_at=expires_at)
            logger.info("⚠️ Subscription cancelled for tenant %d, expires %s",
                        tid, expires_at)
            # Notify owner with end date
            tenant = await db.get_tenant(tid)
            if tenant and tenant.get('owner_telegram_id'):
                from biz_reminders import _send_telegram
                end_date = datetime.fromtimestamp(current_end).strftime('%d %b %Y')
                msg = (
                    "⚠️ *Subscription Cancelled*\n\n"
                    f"Your subscription for *{_escape_md_v2(tenant.get('firm_name', ''))}* "
                    "has been cancelled\\.\n\n"
                    f"📅 Your access continues until *{_escape_md_v2(end_date)}*\\.\n\n"
                    "You can resubscribe anytime with /subscribe\\."
                )
                try:
                    await _send_telegram(tenant['owner_telegram_id'], msg)
                except Exception as e:
                    logger.error("Failed to send cancel notification: %s", e)
            if tenant.get('email'):
                import asyncio
                asyncio.create_task(_notify_payment_email(tenant['email'],
                    email_svc.send_cancellation_confirmation(
                        tenant['email'], tenant.get('owner_name', ''),
                        tenant.get('firm_name', ''),
                        datetime.fromtimestamp(current_end).strftime('%d %b %Y'))))
        return {"status": "ok", "action": "marked_expiring", "tenant_id": tid}
    return {"status": "ok", "event": "subscription.cancelled"}


async def _handle_subscription_halted(payload: dict) -> dict:
    """Payment failed repeatedly — subscription halted. Notify owner."""
    sub = payload.get("subscription", {}).get("entity", {})
    notes = sub.get("notes", {})
    tenant_id = notes.get("tenant_id")
    if tenant_id:
        tid = int(tenant_id)
        await db.update_tenant(tid, subscription_status="payment_failed")
        logger.warning("🚨 Subscription halted for tenant %d — payment failed",
                       tid)
        # Notify owner
        tenant = await db.get_tenant(tid)
        if tenant and tenant.get('owner_telegram_id'):
            from biz_reminders import _send_telegram
            msg = (
                "🚨 *Subscription Halted*\n\n"
                f"Your subscription for *{_escape_md_v2(tenant.get('firm_name', ''))}* "
                "has been halted due to repeated payment failures\\.\n\n"
                "⚠️ Your account will be deactivated soon unless payment is resolved\\.\n"
                "Please update your payment method or contact support\\.\n\n"
                "Use /subscribe to update payment\\."
            )
            try:
                await _send_telegram(tenant['owner_telegram_id'], msg)
            except Exception as e:
                logger.error("Failed to send halted notification: %s", e)
            # Also send email
            if tenant.get('email'):
                import asyncio
                asyncio.create_task(_notify_payment_email(tenant['email'],
                    email_svc.send_payment_failed_email(
                        tenant['email'], tenant.get('owner_name', ''),
                        tenant.get('firm_name', ''),
                        "Subscription halted — repeated payment failures")))
        return {"status": "ok", "action": "halted", "tenant_id": tid}
    return {"status": "ok", "event": "subscription.halted"}


async def _handle_subscription_pending(payload: dict) -> dict:
    """Payment pending (UPI mandate, etc.) — notify owner."""
    sub = payload.get("subscription", {}).get("entity", {})
    notes = sub.get("notes", {})
    tenant_id = notes.get("tenant_id")
    logger.info("⏳ Subscription pending for tenant %s — waiting for payment authorization", tenant_id)
    if tenant_id:
        tid = int(tenant_id)
        tenant = await db.get_tenant(tid)
        if tenant and tenant.get('owner_telegram_id'):
            from biz_reminders import _send_telegram
            msg = (
                "⏳ *Payment Pending*\n\n"
                "Your payment is awaiting authorization "
                "\\(UPI mandate / bank approval\\)\\.\n\n"
                "This usually completes within a few minutes\\. "
                "If it doesn't go through, please try again with /subscribe\\."
            )
            try:
                await _send_telegram(tenant['owner_telegram_id'], msg)
            except Exception as e:
                logger.error("Failed to send pending notification: %s", e)
        if tenant and tenant.get('email'):
            import asyncio
            asyncio.create_task(_notify_payment_email(tenant['email'],
                email_svc.send_payment_pending_email(
                    tenant['email'], tenant.get('owner_name', ''),
                    tenant.get('firm_name', ''))))
    return {"status": "ok", "event": "subscription.pending"}


async def _handle_payment_captured(payload: dict) -> dict:
    """One-time payment captured (Order/Checkout flow). Idempotent."""
    payment = payload.get("payment", {}).get("entity", {})
    notes = payment.get("notes", {})
    tenant_id = notes.get("tenant_id")
    plan_key = notes.get("plan_key")
    payment_id = payment.get("id", "")

    if not tenant_id or not plan_key:
        logger.error("❌ Webhook payment.captured missing tenant_id/plan_key in notes: %s", notes)
        await db.add_system_event(
            "warning", "high", "payment",
            "Webhook payload missing tenant_id/plan_key",
            f"payment_id={payment_id} notes={notes}")
        return JSONResponse({"detail": "Missing tenant_id/plan_key in notes"}, status_code=400)

    tid = int(tenant_id)

    # Idempotency: skip if already processed (prevents race with frontend verify)
    if await db.is_payment_processed(payment_id):
        logger.info("🔄 Payment %s already processed — skipping duplicate (webhook)", payment_id)
        return {"status": "ok", "event": "payment.captured", "action": "already_processed"}

    # Record as processed BEFORE activation (atomic guard)
    amount_paise = payment.get("amount", 0)
    inserted = await db.record_payment_processed(
        payment_id, tid, plan_key, "webhook", amount_paise)
    if not inserted:
        logger.info("🔄 Payment %s processed by concurrent request — skipping", payment_id)
        return {"status": "ok", "event": "payment.captured", "action": "already_processed"}

    plan_info = PLANS.get(plan_key, {})
    max_agents = plan_info.get("max_agents", 1)
    period_days = plan_info.get("period_days", 30)

    # Smart expiry: if still in trial, start billing from trial end
    tenant = await db.get_tenant(tid)
    trial_end_str = tenant.get('trial_ends_at') if tenant else None
    now = datetime.now()
    if trial_end_str:
        try:
            trial_end = datetime.fromisoformat(trial_end_str)
            if trial_end > now:
                expires = (trial_end + timedelta(days=period_days)).isoformat()
            else:
                expires = (now + timedelta(days=period_days)).isoformat()
        except ValueError:
            expires = (now + timedelta(days=period_days)).isoformat()
    else:
        expires = (now + timedelta(days=period_days)).isoformat()

    await db.update_tenant(
        tid,
        is_active=1,
        plan=plan_key,
        subscription_status="active",
        subscription_expires_at=expires,
        trial_ends_at=None,
        max_agents=max_agents,
    )

    logger.info("✅ Payment captured (webhook): tenant=%d plan=%s amount=₹%s",
                tid, plan_key, amount_paise / 100)

    # Log payment event
    await db.add_system_event(
        "info", "low", "payment",
        f"Payment ₹{amount_paise/100:,.0f} captured for {plan_key}",
        f"tenant={tid} payment={payment_id} source=webhook",
        tenant_id=tid)

    # Auto-commission: record affiliate commission (recurring on every payment)
    try:
        import asyncio
        tenant = await db.get_tenant(tid)
        conv = await db.process_payment_commission(tid, plan_key, payment_id, amount_paise)
        if conv and conv.get('commission'):
            from biz_email import send_affiliate_commission_earned
            if conv.get('affiliate_email'):
                asyncio.create_task(send_affiliate_commission_earned(
                    conv['affiliate_email'], conv['affiliate_name'],
                    conv['commission'], plan_key,
                    tenant.get('owner_name', '') if tenant else ''))
    except Exception as e:
        logger.error("Commission recording error for tenant %d: %s", tid, e)

    # Notify owner: Telegram + email receipt
    is_founding = bool(tenant and tenant.get('founding_discount'))
    original_paise = PLANS.get(plan_key, {}).get("amount_paise", 0)
    await _notify_payment_success(
        tid, plan_key, amount_paise,
        payment_id, expires,
        founding_discount=is_founding,
        original_amount=original_paise)

    return {
        "status": "ok",
        "action": "activated",
        "tenant_id": tid,
        "plan": plan_key,
        "expires": expires,
    }


async def _handle_payment_failed(payload: dict) -> dict:
    """Payment failed — notify tenant owner."""
    payment = payload.get("payment", {}).get("entity", {})
    notes = payment.get("notes", {})
    tenant_id = notes.get("tenant_id")
    error_desc = payment.get("error_description", "unknown error")
    logger.warning("❌ Payment failed for tenant %s: %s", tenant_id, error_desc)

    # Log payment failure event
    tid_int = int(tenant_id) if tenant_id else None
    await db.add_system_event(
        "warning", "medium", "payment",
        f"Payment failed: {error_desc[:100]}",
        f"tenant={tenant_id} payment={payment.get('id', '')}",
        tenant_id=tid_int)

    if tenant_id:
        tid = int(tenant_id)
        tenant = await db.get_tenant(tid)
        if tenant:
            owner_tg = tenant.get('owner_telegram_id')
            if owner_tg:
                from biz_reminders import _send_telegram
                fail_msg = (
                    "❌ *Payment Failed*\n\n"
                    f"Your payment for *{_escape_md_v2(tenant.get('firm_name', 'your account'))}* "
                    "could not be processed\\.\n\n"
                    f"Reason: {_escape_md_v2(error_desc)}\n\n"
                    "💳 Please try again with a different payment method "
                    "or contact support\\.\n"
                    "Use /subscribe to retry\\."
                )
                try:
                    await _send_telegram(owner_tg, fail_msg)
                except Exception as e:
                    logger.error("Failed to send payment failure notification: %s", e)

            # Also send email notification
            if tenant.get('email'):
                import asyncio
                asyncio.create_task(_notify_payment_email(tenant['email'],
                    email_svc.send_payment_failed_email(
                        tenant['email'], tenant.get('owner_name', ''),
                        tenant.get('firm_name', ''), error_desc)))

    return {"status": "ok", "event": "payment.failed"}


async def _activate_tenant_from_sub(sub: dict, event_type: str) -> dict:
    """Activate/extend a tenant based on subscription data. Idempotent."""
    notes = sub.get("notes", {})
    tenant_id = notes.get("tenant_id")
    plan_key = notes.get("plan_key", "individual")

    if not tenant_id:
        logger.warning("%s but no tenant_id in notes", event_type)
        return {"status": "ok", "event": event_type, "action": "no_tenant"}

    tid = int(tenant_id)
    payment_id = sub.get("payment_id") or sub.get("id", "")

    # Idempotency guard
    if payment_id and await db.is_payment_processed(payment_id):
        logger.info("🔄 Subscription payment %s already processed — skipping duplicate", payment_id)
        return {"status": "ok", "event": event_type, "action": "already_processed"}

    if payment_id:
        amount_paise = sub.get("plan", {}).get("item", {}).get("amount", 0) if isinstance(sub.get("plan"), dict) else 0
        inserted = await db.record_payment_processed(
            payment_id, tid, plan_key, f"webhook_{event_type}", amount_paise)
        if not inserted:
            return {"status": "ok", "event": event_type, "action": "already_processed"}

    plan_info = PLANS.get(plan_key, {})
    max_agents = plan_info.get("max_agents", 1)

    # Set expiry from Razorpay's current_end timestamp
    current_end = sub.get("current_end")
    if current_end:
        expires = datetime.fromtimestamp(current_end).isoformat()
    else:
        expires = (datetime.now() + timedelta(days=33)).isoformat()

    await db.update_tenant(
        tid,
        is_active=1,
        plan=plan_key,
        subscription_status="active",
        subscription_expires_at=expires,
        trial_ends_at=None,
        razorpay_sub_id=sub.get("id", ""),
        max_agents=max_agents,
    )

    logger.info("✅ %s: tenant=%d plan=%s expires=%s",
                event_type, tid, plan_key, expires)

    # Log payment event
    sub_amount = sub.get("plan", {}).get("item", {}).get("amount", 0) if isinstance(sub.get("plan"), dict) else 0
    await db.add_system_event(
        "info", "low", "payment",
        f"Subscription {event_type} for {plan_key}",
        f"tenant={tid} payment={payment_id} source=webhook amount=₹{sub_amount/100:,.0f}",
        tenant_id=tid)

    # Auto-commission: record affiliate commission (recurring on every payment)
    try:
        import asyncio
        tenant = await db.get_tenant(tid)
        sub_amount_paise = sub.get("plan", {}).get("item", {}).get("amount", 0) if isinstance(sub.get("plan"), dict) else 0
        conv = await db.process_payment_commission(tid, plan_key, payment_id, sub_amount_paise)
        if conv and conv.get('commission'):
            from biz_email import send_affiliate_commission_earned
            if conv.get('affiliate_email'):
                asyncio.create_task(send_affiliate_commission_earned(
                    conv['affiliate_email'], conv['affiliate_name'],
                    conv['commission'], plan_key,
                    tenant.get('owner_name', '') if tenant else ''))
    except Exception as e:
        logger.error("Commission recording error for tenant %d: %s", tid, e)

    # Notify owner: Telegram + email receipt
    notify_amount = sub.get("plan", {}).get("item", {}).get("amount", 0) if isinstance(sub.get("plan"), dict) else 0
    tenant_for_notify = await db.get_tenant(tid)
    is_founding_sub = bool(tenant_for_notify and tenant_for_notify.get('founding_discount'))
    original_sub_paise = plan_info.get("amount_paise", 0)
    await _notify_payment_success(tid, plan_key, notify_amount, payment_id, expires,
                                   founding_discount=is_founding_sub,
                                   original_amount=original_sub_paise)

    return {
        "status": "ok",
        "action": "activated",
        "tenant_id": tid,
        "plan": plan_key,
        "expires": expires,
    }


# =============================================================================
#  PAYMENT VERIFICATION (for Checkout.js callback)
# =============================================================================

async def activate_from_api_verified_payment(
    tenant_id: int, plan_key: str,
    order_id: str, payment_id: str, amount_paise: int,
) -> dict:
    """Activate tenant when payment confirmed via Razorpay API (no HMAC needed).
    Used by the UPI recovery endpoint — HMAC signature is unavailable when the
    browser loses context during UPI app-switch.  Server-to-server API verification
    replaces HMAC here.  Fully idempotent — safe to call multiple times.
    """
    if await db.is_payment_processed(payment_id):
        logger.info("🔄 Payment %s already activated — recovery no-op", payment_id)
        tenant = await db.get_tenant(tenant_id)
        return {"status": "ok", "already_activated": True,
                "plan": tenant.get("plan", plan_key) if tenant else plan_key}

    plan_info = PLANS.get(plan_key, {})
    max_agents = plan_info.get("max_agents", 1)
    period_days = plan_info.get("period_days", 30)

    inserted = await db.record_payment_processed(
        payment_id, tenant_id, plan_key, "recovery_api_verified", amount_paise
    )
    if not inserted:
        tenant = await db.get_tenant(tenant_id)
        return {"status": "ok", "already_activated": True,
                "plan": tenant.get("plan", plan_key) if tenant else plan_key}

    tenant = await db.get_tenant(tenant_id)
    trial_end_str = tenant.get("trial_ends_at") if tenant else None
    now = datetime.now()
    if trial_end_str:
        try:
            trial_end = datetime.fromisoformat(trial_end_str)
            expires = ((trial_end if trial_end > now else now) + timedelta(days=period_days)).isoformat()
        except ValueError:
            expires = (now + timedelta(days=period_days)).isoformat()
    else:
        expires = (now + timedelta(days=period_days)).isoformat()

    await db.update_tenant(
        tenant_id,
        is_active=1, plan=plan_key, subscription_status="active",
        subscription_expires_at=expires, trial_ends_at=None, max_agents=max_agents,
    )
    logger.info("✅ Recovery-activated: tenant=%d plan=%s payment=%s order=%s",
                tenant_id, plan_key, payment_id, order_id)
    return {"status": "ok", "activated": True, "plan": plan_key, "expires": expires}


async def verify_and_activate(tenant_id: int, plan_key: str,
                              razorpay_order_id: str,
                              razorpay_payment_id: str,
                              razorpay_signature: str) -> dict:
    """
    Verify payment from Razorpay Checkout.js and activate the tenant.
    Called after successful client-side checkout.
    Includes: signature check, server-side Razorpay verification, idempotency guard.
    """
    # Verify signature
    valid = verify_payment_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    )
    if not valid:
        logger.warning("❌ Invalid payment signature for tenant %d", tenant_id)
        return {"error": "Invalid payment signature", "verified": False}

    # Idempotency: skip if already processed (prevents race with webhook)
    if await db.is_payment_processed(razorpay_payment_id):
        logger.info("🔄 Payment %s already processed — skipping duplicate (frontend)",
                    razorpay_payment_id)
        tenant = await db.get_tenant(tenant_id)
        return {
            "status": "ok", "verified": True,
            "tenant_id": tenant_id, "plan": tenant.get('plan', plan_key) if tenant else plan_key,
            "expires": tenant.get('subscription_expires_at', '') if tenant else '',
            "already_processed": True,
        }

    plan_info = PLANS.get(plan_key, {})
    expected_amount = plan_info.get("amount_paise", 0)

    # Check founding discount — adjust expected amount for founding customers
    founding_discount = False
    tenant = await db.get_tenant(tenant_id)
    if tenant and tenant.get("founding_discount") == 1:
        fd_until = tenant.get("founding_discount_until", "")
        if fd_until:
            try:
                if datetime.fromisoformat(fd_until) > datetime.now():
                    founding_discount = True
                    expected_amount = int(expected_amount * 0.80)
            except ValueError:
                pass

    # Server-side verification: fetch payment from Razorpay API
    try:
        rz_payment = await _razorpay_request("GET", f"payments/{razorpay_payment_id}")
        rz_status = rz_payment.get("status")
        rz_amount = rz_payment.get("amount", 0)
        rz_order = rz_payment.get("order_id", "")

        if rz_status not in ("captured", "authorized"):
            logger.warning("❌ Payment %s status is '%s', not captured",
                           razorpay_payment_id, rz_status)
            return {"error": f"Payment not completed (status: {rz_status})", "verified": False}

        if rz_order and rz_order != razorpay_order_id:
            logger.warning("❌ Payment order mismatch: expected %s, got %s",
                           razorpay_order_id, rz_order)
            return {"error": "Payment order mismatch", "verified": False}

        if expected_amount and rz_amount != expected_amount:
            logger.warning("❌ Amount mismatch for tenant %d: expected %d, got %d (founding=%s)",
                           tenant_id, expected_amount, rz_amount, founding_discount)
            await db.add_system_event(
                "security", "critical", "payment",
                f"Amount mismatch: tenant {tenant_id}",
                f"Expected ₹{expected_amount/100}, Razorpay returned ₹{rz_amount/100}, founding={founding_discount}",
                tenant_id=tenant_id)
            return {"error": "Payment amount mismatch", "verified": False}
    except Exception as e:
        logger.error("Razorpay payment fetch failed for %s: %s", razorpay_payment_id, e)
        # Signature was valid — proceed with activation anyway (Razorpay API may be down)

    # Record as processed BEFORE activation (atomic idempotency)
    inserted = await db.record_payment_processed(
        razorpay_payment_id, tenant_id, plan_key, "frontend_verify", expected_amount)
    if not inserted:
        # Another concurrent request processed it between our check and insert
        logger.info("🔄 Payment %s processed by another request — skipping", razorpay_payment_id)
        tenant = await db.get_tenant(tenant_id)
        return {"status": "ok", "verified": True, "tenant_id": tenant_id,
                "plan": plan_key, "already_processed": True,
                "expires": tenant.get('subscription_expires_at', '') if tenant else ''}

    max_agents = plan_info.get("max_agents", 1)
    period_days = plan_info.get("period_days", 30)

    # Smart expiry: if still in trial, start billing from trial end
    tenant = await db.get_tenant(tenant_id)
    trial_end_str = tenant.get('trial_ends_at') if tenant else None
    now = datetime.now()
    if trial_end_str:
        try:
            trial_end = datetime.fromisoformat(trial_end_str)
            if trial_end > now:
                expires = (trial_end + timedelta(days=period_days)).isoformat()
            else:
                expires = (now + timedelta(days=period_days)).isoformat()
        except ValueError:
            expires = (now + timedelta(days=period_days)).isoformat()
    else:
        expires = (now + timedelta(days=period_days)).isoformat()

    await db.update_tenant(
        tenant_id,
        is_active=1,
        plan=plan_key,
        subscription_status="active",
        subscription_expires_at=expires,
        trial_ends_at=None,
        max_agents=max_agents,
    )

    logger.info("✅ Payment verified & activated: tenant=%d plan=%s payment=%s founding=%s period_days=%d",
                tenant_id, plan_key, razorpay_payment_id, founding_discount, period_days)

    # Log payment event
    discount_note = " (founding 20% discount)" if founding_discount else ""
    await db.add_system_event(
        "info", "low", "payment",
        f"Payment ₹{expected_amount/100:,.0f}{discount_note} for {plan_key}",
        f"tenant={tenant_id} payment={razorpay_payment_id} source=frontend founding={founding_discount}",
        tenant_id=tenant_id)

    # Auto-commission: record affiliate commission (recurring on every payment)
    try:
        import asyncio
        tenant = await db.get_tenant(tenant_id)
        conv = await db.process_payment_commission(tenant_id, plan_key, razorpay_payment_id, expected_amount)
        if conv and conv.get('commission'):
            from biz_email import send_affiliate_commission_earned
            if conv.get('affiliate_email'):
                asyncio.create_task(send_affiliate_commission_earned(
                    conv['affiliate_email'], conv['affiliate_name'],
                    conv['commission'], plan_key,
                    tenant.get('owner_name', '') if tenant else ''))
    except Exception as e:
        logger.error("Commission recording error for tenant %d: %s", tenant_id, e)

    # Notify owner: Telegram + email receipt
    original_amount = plan_info.get("amount_paise", 0)
    await _notify_payment_success(tenant_id, plan_key, expected_amount,
                                   razorpay_payment_id, expires,
                                   founding_discount=founding_discount,
                                   original_amount=original_amount)

    return {
        "status": "ok",
        "verified": True,
        "tenant_id": tenant_id,
        "plan": plan_key,
        "expires": expires,
    }


# =============================================================================
#  SUBSCRIPTION STATUS CHECK
# =============================================================================

async def get_subscription_status(tenant_id: int) -> dict:
    """Get subscription status for a tenant."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}

    sub_id = tenant.get("razorpay_sub_id")
    plan = tenant.get("plan", "trial")
    status = tenant.get("subscription_status", "trial")
    expires = tenant.get("subscription_expires_at")

    result = {
        "tenant_id": tenant_id,
        "plan": plan,
        "plan_name": PLANS.get(plan, {}).get("name", plan),
        "subscription_status": status,
        "expires_at": expires,
        "razorpay_sub_id": sub_id,
        "is_active": bool(tenant.get("is_active", 0)),
    }

    # If there's a Razorpay subscription, fetch live status
    if sub_id and is_enabled():
        try:
            live = await _razorpay_request("GET", f"subscriptions/{sub_id}")
            result["razorpay_status"] = live.get("status")
            result["current_start"] = live.get("current_start")
            result["current_end"] = live.get("current_end")
        except Exception as e:
            logger.error("Error fetching subscription %s: %s", sub_id, e)

    return result


async def _handle_refund_processed(payload: dict) -> dict:
    """Razorpay confirmed our refund. Mark the sarathi_refunds row as processed
    AND fire B4 auto-clawback if there's an affiliate referral on the tenant."""
    refund_entity = (payload.get("refund") or {}).get("entity") or {}
    rzp_refund_id = refund_entity.get("id", "")
    rzp_payment_id = refund_entity.get("payment_id", "")
    if not rzp_refund_id and not rzp_payment_id:
        return {"status": "ignored", "reason": "no_ids"}
    import biz_database as _db
    import aiosqlite as _sql
    async with _sql.connect(_db.DB_PATH) as conn:
        conn.row_factory = _sql.Row
        row = await (await conn.execute(
            "SELECT refund_id, tenant_id FROM sarathi_refunds "
            "WHERE razorpay_refund_id=? "
            "OR (razorpay_payment_id=? AND (razorpay_refund_id IS NULL OR razorpay_refund_id=''))",
            (rzp_refund_id, rzp_payment_id))).fetchone()
    if row:
        await update_sarathi_refund_status(row["refund_id"], "processed",
                                            razorpay_refund_id=rzp_refund_id)
        logger.info("✓ Sarathi refund webhook → processed: refund_id=%d rzp=%s",
                    row["refund_id"], rzp_refund_id)
        # B4: auto-clawback affiliate commission (idempotent — if already
        # reversed/clawback_owed from the cancel-endpoint path, this is a no-op).
        try:
            cb = await _db.auto_clawback_for_refund(
                row["tenant_id"], reason=f"webhook_refund_id={row['refund_id']}")
            if cb:
                logger.info("Affiliate clawback (webhook) tenant=%d action=%s amount=₹%s",
                            row["tenant_id"], cb.get("action"), cb.get("amount"))
        except Exception as cbe:
            logger.error("Affiliate webhook clawback failed: %s", cbe)
        return {"status": "ok", "refund_id": row["refund_id"]}
    return {"status": "unmatched", "rzp_refund_id": rzp_refund_id}


async def _handle_refund_failed(payload: dict) -> dict:
    """Razorpay reported refund failure. Mark the sarathi_refunds row as failed."""
    refund_entity = (payload.get("refund") or {}).get("entity") or {}
    rzp_refund_id = refund_entity.get("id", "")
    rzp_payment_id = refund_entity.get("payment_id", "")
    err = refund_entity.get("error_description") or refund_entity.get("error_reason") or "unknown"
    import biz_database as _db
    import aiosqlite as _sql
    async with _sql.connect(_db.DB_PATH) as conn:
        conn.row_factory = _sql.Row
        row = await (await conn.execute(
            "SELECT refund_id FROM sarathi_refunds WHERE razorpay_refund_id=? "
            "OR razorpay_payment_id=? ORDER BY requested_at DESC LIMIT 1",
            (rzp_refund_id, rzp_payment_id))).fetchone()
    if row:
        await update_sarathi_refund_status(row["refund_id"], "failed",
                                            razorpay_refund_id=rzp_refund_id,
                                            last_error=str(err)[:500])
        logger.warning("⚠️ Sarathi refund webhook → failed: refund_id=%d err=%s",
                       row["refund_id"], err)
        return {"status": "ok", "refund_id": row["refund_id"]}
    return {"status": "unmatched", "rzp_refund_id": rzp_refund_id}


# =============================================================================
#  SARATHI REFUNDS — Policy A: full refund if cancelled within 7 days AND
#                              tenant has < 5 leads (i.e. essentially unused)
# =============================================================================

SARATHI_REFUND_WINDOW_DAYS = 7
SARATHI_REFUND_LEAD_THRESHOLD = 5  # < this = "no meaningful usage"


async def _count_tenant_leads(tenant_id: int) -> int:
    """Count leads belonging to a tenant. Leads are linked to agents,
    which are linked to tenants — so we count via the agents JOIN."""
    import biz_database as _db
    import aiosqlite as _sql
    async with _sql.connect(_db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM leads l "
            "INNER JOIN agents a ON a.agent_id = l.agent_id "
            "WHERE a.tenant_id = ?", (tenant_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def find_latest_paid_payment_for_tenant(tenant_id: int) -> Optional[dict]:
    """Most recent successfully-processed Razorpay payment for a tenant.
    Used as the source-of-truth for what to refund against."""
    import biz_database as _db
    import aiosqlite as _sql
    async with _sql.connect(_db.DB_PATH) as conn:
        conn.row_factory = _sql.Row
        cur = await conn.execute(
            "SELECT razorpay_payment_id, plan_key, source, amount_paise, "
            "       processed_at "
            "FROM processed_payments "
            "WHERE tenant_id = ? AND amount_paise > 0 "
            "ORDER BY processed_at DESC LIMIT 1", (tenant_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def check_sarathi_refund_eligibility(tenant_id: int,
                                            payment_id: str = ""
                                            ) -> tuple[bool, str, dict]:
    """Return (eligible, reason, payment_dict). Policy A:
      - Tenant has a processed payment in the last SARATHI_REFUND_WINDOW_DAYS
      - Tenant has < SARATHI_REFUND_LEAD_THRESHOLD leads (essentially unused)
      - No existing pending/processing/processed refund row already
    """
    import biz_database as _db
    import aiosqlite as _sql
    import datetime as _dt
    async with _sql.connect(_db.DB_PATH) as conn:
        conn.row_factory = _sql.Row
        existing = await (await conn.execute(
            "SELECT refund_id, status FROM sarathi_refunds "
            "WHERE tenant_id = ? AND status IN ('pending','processing','processed') "
            "LIMIT 1", (tenant_id,))).fetchone()
        if existing:
            return False, f"refund_already_{existing['status']}", {}
        if payment_id:
            row = await (await conn.execute(
                "SELECT razorpay_payment_id, plan_key, source, amount_paise, processed_at "
                "FROM processed_payments WHERE razorpay_payment_id = ? AND tenant_id = ?",
                (payment_id, tenant_id))).fetchone()
        else:
            row = await (await conn.execute(
                "SELECT razorpay_payment_id, plan_key, source, amount_paise, processed_at "
                "FROM processed_payments WHERE tenant_id = ? AND amount_paise > 0 "
                "ORDER BY processed_at DESC LIMIT 1", (tenant_id,))).fetchone()
        if not row:
            return False, "no_payment_found", {}
        payment = dict(row)

    # Window check
    try:
        proc_at = _dt.datetime.fromisoformat(str(payment["processed_at"]).replace("Z","").replace(" ","T")[:19])
    except Exception:
        return False, "bad_processed_at", payment
    age_days = (_dt.datetime.utcnow() - proc_at).days
    if age_days > SARATHI_REFUND_WINDOW_DAYS:
        return False, f"outside_window_{age_days}d", payment

    # Usage check
    leads = await _count_tenant_leads(tenant_id)
    if leads >= SARATHI_REFUND_LEAD_THRESHOLD:
        return False, f"has_{leads}_leads", payment
    return True, "eligible", payment


async def create_sarathi_refund_row(*, tenant_id: int, amount: int,
                                     razorpay_payment_id: str = "",
                                     razorpay_order_id: str = "",
                                     reason: str = "",
                                     initiated_by: str = "tenant") -> int:
    import biz_database as _db
    import aiosqlite as _sql
    async with _sql.connect(_db.DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO sarathi_refunds "
            "(tenant_id, amount, razorpay_payment_id, razorpay_order_id, reason, initiated_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, amount, razorpay_payment_id, razorpay_order_id,
             reason, initiated_by))
        await conn.commit()
        return cur.lastrowid


async def update_sarathi_refund_status(refund_id: int, status: str, **fields) -> None:
    import biz_database as _db
    import aiosqlite as _sql
    sets, vals = ["status=?"], [status]
    for k, v in fields.items():
        if k in ("razorpay_refund_id", "last_error"):
            sets.append(f"{k}=?"); vals.append(v)
    if status in ("processed", "failed"):
        sets.append("processed_at=CURRENT_TIMESTAMP")
    vals.append(refund_id)
    async with _sql.connect(_db.DB_PATH) as conn:
        await conn.execute(
            f"UPDATE sarathi_refunds SET {', '.join(sets)} WHERE refund_id=?", vals)
        await conn.commit()


async def get_sarathi_refund(refund_id: int) -> Optional[dict]:
    import biz_database as _db
    import aiosqlite as _sql
    async with _sql.connect(_db.DB_PATH) as conn:
        conn.row_factory = _sql.Row
        row = await (await conn.execute(
            "SELECT * FROM sarathi_refunds WHERE refund_id=?", (refund_id,))).fetchone()
        return dict(row) if row else None


async def list_sarathi_refunds(status: Optional[str] = None,
                                limit: int = 200) -> list[dict]:
    import biz_database as _db
    import aiosqlite as _sql
    async with _sql.connect(_db.DB_PATH) as conn:
        conn.row_factory = _sql.Row
        if status:
            cur = await conn.execute(
                "SELECT r.*, t.firm_name, t.email, t.owner_name "
                "FROM sarathi_refunds r LEFT JOIN tenants t ON t.tenant_id=r.tenant_id "
                "WHERE r.status=? ORDER BY r.requested_at DESC LIMIT ?", (status, limit))
        else:
            cur = await conn.execute(
                "SELECT r.*, t.firm_name, t.email, t.owner_name "
                "FROM sarathi_refunds r LEFT JOIN tenants t ON t.tenant_id=r.tenant_id "
                "ORDER BY r.requested_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]


async def issue_razorpay_refund_for_sarathi(payment_id: str, amount_paise: int,
                                              notes: Optional[dict] = None) -> dict:
    """Wrapper around Razorpay's POST /payments/{id}/refund.
    Returns dict with 'ok', 'refund_id', 'status', or 'error'."""
    import httpx as _httpx
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        return {"ok": False, "error": "razorpay_not_configured"}
    body = {"amount": amount_paise, "speed": "normal"}
    if notes:
        body["notes"] = notes
    try:
        async with _httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
                auth=(key_id, key_secret), json=body, timeout=30.0)
        if r.status_code in (200, 201):
            d = r.json()
            return {"ok": True, "refund_id": d.get("id", ""),
                    "status": d.get("status", "")}
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:500]}"}
    except Exception as e:
        logger.exception("Razorpay refund call failed payment=%s", payment_id)
        return {"ok": False, "error": str(e)}


async def find_sarathi_eligible_unrefunded(days: int = 30) -> list[dict]:
    """Reconciliation source: tenants whose recent payment qualifies for refund
    but no refund row exists yet. Used by scheduler nudge for SA review."""
    import biz_database as _db
    import aiosqlite as _sql
    import datetime as _dt
    cutoff = (_dt.datetime.utcnow() - _dt.timedelta(days=days)).isoformat()
    async with _sql.connect(_db.DB_PATH) as conn:
        conn.row_factory = _sql.Row
        cur = await conn.execute(
            f"""SELECT t.tenant_id, t.firm_name, t.email, t.subscription_status,
                       p.razorpay_payment_id, p.amount_paise, p.processed_at,
                       (SELECT COUNT(*) FROM leads l
                          INNER JOIN agents a ON a.agent_id = l.agent_id
                          WHERE a.tenant_id = t.tenant_id) AS lead_count,
                       (SELECT status FROM sarathi_refunds sr WHERE sr.tenant_id = t.tenant_id
                          ORDER BY sr.requested_at DESC LIMIT 1) AS last_refund_status
                FROM tenants t
                INNER JOIN processed_payments p ON p.tenant_id = t.tenant_id
                WHERE t.subscription_status = 'cancelled'
                  AND p.amount_paise > 0
                  AND p.processed_at >= ?
                ORDER BY p.processed_at DESC""",
            (cutoff,))
        rows = [dict(r) for r in await cur.fetchall()]

    eligible = []
    now = _dt.datetime.utcnow()
    for r in rows:
        if (r.get("lead_count") or 0) >= SARATHI_REFUND_LEAD_THRESHOLD:
            continue
        if r.get("last_refund_status") in ("pending", "processing", "processed"):
            continue
        try:
            pa = _dt.datetime.fromisoformat(str(r["processed_at"]).replace(" ","T")[:19])
        except Exception:
            continue
        if (now - pa).days <= SARATHI_REFUND_WINDOW_DAYS:
            eligible.append(r)
    return eligible
