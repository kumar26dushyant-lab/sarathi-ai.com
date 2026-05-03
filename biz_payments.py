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

# Plan definitions: plan_key → {name, amount_paise, period, interval, max_agents}
# NOTE: max_agents is admin-inclusive (admin + advisor seats)
PLANS = {
    "individual": {
        "name": "Solo Advisor",
        "amount_paise": 19900,       # ₹199
        "amount_display": "₹199/mo",
        "period": "monthly",
        "interval": 1,
        "max_agents": 1,
        "description": "1 Advisor · Unlimited Leads · Full CRM",
    },
    "team": {
        "name": "Team",
        "amount_paise": 79900,       # ₹799
        "amount_display": "₹799/mo",
        "period": "monthly",
        "interval": 1,
        "max_agents": 6,
        "description": "Admin + 5 Advisors · WhatsApp · Custom Branding",
    },
    "enterprise": {
        "name": "Enterprise",
        "amount_paise": 199900,      # ₹1,999
        "amount_display": "₹1,999/mo",
        "period": "monthly",
        "interval": 1,
        "max_agents": 26,
        "description": "Admin + 25 Advisors · API · Dedicated Support",
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
    """Verify Razorpay webhook signature using HMAC-SHA256."""
    if not RAZORPAY_KEY_SECRET:
        return False
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_payment_signature(order_id: str, payment_id: str,
                             signature: str) -> bool:
    """Verify Razorpay payment signature (for Checkout.js flow).
    In TEST mode with empty/dummy signature, auto-accepts for development."""
    if TEST_MODE and signature == "test_bypass":
        logger.info("🧪 TEST MODE: bypassing payment signature verification")
        return True
    if not RAZORPAY_KEY_SECRET:
        return False
    message = f"{order_id}|{payment_id}"
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


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

    # Smart expiry: if still in trial, start billing from trial end
    tenant = await db.get_tenant(tid)
    trial_end_str = tenant.get('trial_ends_at') if tenant else None
    now = datetime.now()
    if trial_end_str:
        try:
            trial_end = datetime.fromisoformat(trial_end_str)
            if trial_end > now:
                expires = (trial_end + timedelta(days=30)).isoformat()
            else:
                expires = (now + timedelta(days=30)).isoformat()
        except ValueError:
            expires = (now + timedelta(days=30)).isoformat()
    else:
        expires = (now + timedelta(days=30)).isoformat()

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

    # Smart expiry: if still in trial, start billing from trial end
    tenant = await db.get_tenant(tenant_id)
    trial_end_str = tenant.get('trial_ends_at') if tenant else None
    now = datetime.now()
    if trial_end_str:
        try:
            trial_end = datetime.fromisoformat(trial_end_str)
            if trial_end > now:
                expires = (trial_end + timedelta(days=30)).isoformat()
            else:
                expires = (now + timedelta(days=30)).isoformat()
        except ValueError:
            expires = (now + timedelta(days=30)).isoformat()
    else:
        expires = (now + timedelta(days=30)).isoformat()

    await db.update_tenant(
        tenant_id,
        is_active=1,
        plan=plan_key,
        subscription_status="active",
        subscription_expires_at=expires,
        trial_ends_at=None,
        max_agents=max_agents,
    )

    logger.info("✅ Payment verified & activated: tenant=%d plan=%s payment=%s founding=%s",
                tenant_id, plan_key, razorpay_payment_id, founding_discount)

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
