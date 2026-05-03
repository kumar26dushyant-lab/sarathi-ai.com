# =============================================================================
#  biz_whatsapp.py — Sarathi-AI Business Technologies: WhatsApp Cloud API Integration
# =============================================================================
#
#  Multi-tenant WhatsApp Cloud API:
#    - Global (master) WA creds for platform-level messages (OTP, alerts)
#    - Per-tenant WA creds for each firm's customer messages
#    - Incoming message routing: webhook → match tenant → match lead → reply
#    - OTP delivery via WhatsApp
#    - Fallback wa.me links when Cloud API not configured
#
# =============================================================================

import httpx
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("sarathi.whatsapp")

# WhatsApp Cloud API base URL
WA_API_BASE = "https://graph.facebook.com/v21.0"

# Global (master) credentials — for platform-level messages
_phone_id: str = ""
_access_token: str = ""

# Shared HTTP client for connection pooling
_http_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    """Get or create shared httpx client with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=30,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _http_client


async def close_client():
    """Close the shared HTTP client. Call at shutdown."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def init_whatsapp():
    """Initialize global WhatsApp credentials from environment."""
    global _phone_id, _access_token
    _phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
    _access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    if _phone_id and _access_token:
        logger.info("WhatsApp Cloud API initialized (Phone ID: %s...)", _phone_id[:6])
    else:
        logger.warning("WhatsApp credentials not configured — messaging disabled")


def is_configured() -> bool:
    """Check if global WhatsApp is properly configured."""
    return bool(_phone_id and _access_token)


def is_tenant_configured(tenant: dict) -> bool:
    """Check if a specific tenant has their own WhatsApp configured."""
    return bool(tenant.get("wa_phone_id") and tenant.get("wa_access_token"))


# =============================================================================
#  CORE MESSAGING
# =============================================================================

async def send_text(to: str, message: str) -> dict:
    """
    Send a plain text message via WhatsApp.

    Args:
        to: Recipient phone number with country code (e.g., '919876543210')
        message: Message text (supports basic formatting: *bold*, _italic_)
    """
    if not is_configured():
        logger.warning("WhatsApp not configured — skipping message to %s", to)
        return {"error": "not_configured"}

    # Ensure phone number has country code
    to = _normalize_phone(to)

    url = f"{WA_API_BASE}/{_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }

    try:
        client = _get_client()
        resp = await client.post(url, headers=headers, json=payload)
        data = resp.json()
        if resp.status_code == 200:
            msg_id = data.get("messages", [{}])[0].get("id", "unknown")
            logger.info("WhatsApp sent to %s (msg_id: %s)", to, msg_id)
            return {"success": True, "message_id": msg_id}
        else:
            logger.error("WhatsApp send failed: %s", data)
            return {"error": data}
    except (httpx.TimeoutException, httpx.ConnectError, ConnectionError,
            TimeoutError, OSError) as e:
        logger.warning("WhatsApp network error (retryable): %s", e)
        return {"error": str(e), "retryable": True}
    except Exception as e:
        logger.error("WhatsApp send error: %s", e)
        return {"error": str(e)}


async def send_document(to: str, document_url: str, filename: str,
                        caption: str = None) -> dict:
    """
    Send a document (PDF) via WhatsApp.

    Args:
        to: Recipient phone number
        document_url: Public URL of the document
        filename: Display filename
        caption: Optional caption text
    """
    if not is_configured():
        return {"error": "not_configured"}

    to = _normalize_phone(to)
    url = f"{WA_API_BASE}/{_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {
            "link": document_url,
            "filename": filename,
        }
    }
    if caption:
        payload["document"]["caption"] = caption

    try:
        client = _get_client()
        resp = await client.post(url, headers=headers, json=payload)
        data = resp.json()
        if resp.status_code == 200:
            logger.info("WhatsApp document sent to %s", to)
            return {"success": True}
        else:
            logger.error("WhatsApp document failed: %s", data)
            return {"error": data}
    except (httpx.TimeoutException, httpx.ConnectError, ConnectionError,
            TimeoutError, OSError) as e:
        logger.warning("WhatsApp document network error: %s", e)
        return {"error": str(e), "retryable": True}
    except Exception as e:
        logger.error("WhatsApp document error: %s", e)
        return {"error": str(e)}


async def send_image(to: str, image_url: str, caption: str = None) -> dict:
    """Send an image via WhatsApp."""
    if not is_configured():
        return {"error": "not_configured"}

    to = _normalize_phone(to)
    url = f"{WA_API_BASE}/{_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {"link": image_url}
    }
    if caption:
        payload["image"]["caption"] = caption

    try:
        client = _get_client()
        resp = await client.post(url, headers=headers, json=payload)
        data = resp.json()
        if resp.status_code == 200:
            logger.info("WhatsApp image sent to %s", to)
            return {"success": True}
        else:
            return {"error": data}
    except (httpx.TimeoutException, httpx.ConnectError, ConnectionError,
            TimeoutError, OSError) as e:
        return {"error": str(e), "retryable": True}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
#  GREETING MESSAGES
# =============================================================================

async def send_birthday_greeting(to: str, client_name: str,
                                 agent_name: str = "Your Advisor",
                                 company: str = "Sarathi-AI",
                                 tagline: str = "AI-Powered Financial Advisor CRM",
                                 compliance_footer: str = "") -> dict:
    """Send a personalized birthday greeting."""
    first_name = client_name.split()[0] if client_name else "Sir/Ma'am"
    message = (
        f"🎂 *Happy Birthday, {first_name}!* 🎉\n\n"
        f"Wishing you a wonderful year filled with good health, "
        f"happiness, and prosperity!\n\n"
        f"May this special day bring you all the joy you deserve. "
        f"Remember, the best gift you can give yourself is "
        f"*financial security* for your loved ones. 🛡️\n\n"
        f"Warm wishes,\n"
        f"*{agent_name}*\n"
        f"_{company}_\n"
        f"_{tagline}_ 🌟"
    )
    if compliance_footer:
        message += f"\n\n_{compliance_footer}_"
    return await send_text(to, message)


async def send_anniversary_greeting(to: str, client_name: str,
                                    agent_name: str = "Your Advisor",
                                    company: str = "Sarathi-AI",
                                    tagline: str = "AI-Powered Financial Advisor CRM",
                                    compliance_footer: str = "") -> dict:
    """Send a personalized anniversary greeting."""
    first_name = client_name.split()[0] if client_name else "Sir/Ma'am"
    message = (
        f"💍 *Happy Anniversary, {first_name}!* 🎊\n\n"
        f"Congratulations on another beautiful year together! "
        f"May your bond grow stronger with each passing year.\n\n"
        f"A family that plans together, stays protected together. "
        f"Let's ensure your family's future is always secure. 🏠\n\n"
        f"Best wishes,\n"
        f"*{agent_name}*\n"
        f"_{company}_\n"
        f"_{tagline}_ 🌟"
    )
    if compliance_footer:
        message += f"\n\n_{compliance_footer}_"
    return await send_text(to, message)


# =============================================================================
#  REMINDER MESSAGES
# =============================================================================

async def send_renewal_reminder(to: str, client_name: str, policy_number: str,
                                renewal_date: str, days_left: int,
                                agent_name: str = "Your Advisor",
                                agent_phone: str = "",
                                company: str = "Sarathi-AI",
                                cta: str = "Secure Your Future Today",
                                compliance_footer: str = "") -> dict:
    """Send a policy renewal reminder."""
    first_name = client_name.split()[0] if client_name else "Sir/Ma'am"
    urgency = "🔴" if days_left <= 7 else "🟡" if days_left <= 15 else "🟢"
    message = (
        f"{urgency} *Policy Renewal Reminder*\n\n"
        f"Dear *{first_name}*,\n\n"
        f"Your policy (#{policy_number}) is due for renewal.\n"
        f"📅 Renewal Date: *{renewal_date}*\n"
        f"⏰ Days Left: *{days_left} days*\n\n"
    )
    if days_left <= 7:
        message += (
            f"⚠️ *Urgent:* Please renew immediately to avoid a break "
            f"in coverage. A gap can lead to waiting period reset!\n\n"
        )
    contact_line = f"Call/WhatsApp me at *{agent_phone}*." if agent_phone else "Reach out to me for help."
    message += (
        f"I can help you renew in just 5 minutes. "
        f"{contact_line}\n\n"
        f"*{agent_name}*\n"
        f"_{company}_\n"
        f"_{cta}_ 🛡️"
    )
    if compliance_footer:
        message += f"\n\n_{compliance_footer}_"
    return await send_text(to, message)


async def send_premium_due_reminder(to: str, client_name: str,
                                    premium_amount: float,
                                    due_date: str, days_left: int,
                                    agent_name: str = "Your Advisor",
                                    agent_phone: str = "",
                                    company: str = "Sarathi-AI") -> dict:
    """Send a premium due reminder."""
    first_name = client_name.split()[0] if client_name else "Sir/Ma'am"
    contact_line = f"Call *{agent_phone}* 📞" if agent_phone else f"Contact *{agent_name}* 📞"
    message = (
        f"💳 *Premium Due Reminder*\n\n"
        f"Dear *{first_name}*,\n\n"
        f"Your premium of *₹{premium_amount:,.0f}* is due on *{due_date}*.\n"
        f"⏰ *{days_left} days remaining*\n\n"
        f"💡 Pay on time to keep your coverage active.\n"
        f"EMI option available if needed.\n\n"
        f"Need help? {contact_line}"
    )
    return await send_text(to, message)


async def send_pitch_summary(to: str, client_name: str, calc_type: str,
                             summary_text: str, pdf_url: str = None,
                             agent_name: str = "Your Advisor",
                             company: str = "Sarathi-AI",
                             tagline: str = "AI-Powered Financial Advisor CRM") -> dict:
    """Send calculator pitch summary to client."""
    first_name = client_name.split()[0] if client_name else "Sir/Ma'am"
    footer = f"Prepared by: *{agent_name}*"
    if company and company != agent_name:
        footer += f"\n_{company}_"
    footer += f"\n_{tagline}_ 🛡️"
    report_line = f"\n\n📎 View detailed report: {pdf_url}" if pdf_url else ""
    message = (
        f"📊 *Financial Analysis for {first_name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{summary_text}\n\n"
        f"{footer}"
        f"{report_line}"
    )
    result = await send_text(to, message)

    if result.get('success'):
        # Send PDF if available
        if pdf_url:
            await send_document(
                to, pdf_url,
                f"Financial_Analysis_{first_name}.pdf",
                f"Detailed analysis prepared for {first_name}"
            )
        return result

    # API failed — fallback to wa.me link
    logger.warning("WhatsApp API failed for pitch, falling back to link: %s",
                   result.get('error', 'unknown'))
    link = generate_calc_share_link(
        to, first_name, calc_type, summary_text,
        pdf_url or "", agent_name, company
    )
    return {"success": True, "method": "link", "wa_link": link}


# =============================================================================
#  WEBHOOK HANDLER (for incoming WhatsApp messages)
# =============================================================================

def parse_webhook(body: dict) -> Optional[dict]:
    """
    Parse incoming WhatsApp webhook payload.
    Returns dict with: from_number, message_text, message_type, timestamp
    """
    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return None

        msg = messages[0]
        return {
            "from_number": msg.get("from", ""),
            "message_type": msg.get("type", "text"),
            "message_text": msg.get("text", {}).get("body", ""),
            "timestamp": msg.get("timestamp", ""),
            "message_id": msg.get("id", ""),
            "name": value.get("contacts", [{}])[0].get("profile", {}).get("name", ""),
        }
    except (IndexError, KeyError, TypeError):
        return None


# =============================================================================
#  HELPERS
# =============================================================================

def _normalize_phone(phone: str) -> str:
    """Normalize phone number to international format (91XXXXXXXXXX)."""
    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if len(phone) == 10:
        phone = "91" + phone
    return phone


# =============================================================================
#  WHATSAPP WEB LINK FALLBACK (for non-Cloud-API users)
# =============================================================================

def generate_wa_link(phone: str, message: str) -> str:
    """Generate a wa.me link for click-to-send (fallback when Cloud API not configured)."""
    import urllib.parse
    phone = _normalize_phone(phone)
    encoded = urllib.parse.quote(message)
    return f"https://wa.me/{phone}?text={encoded}"


def generate_birthday_link(phone: str, client_name: str,
                            agent_name: str = "Your Advisor",
                            company: str = "Sarathi-AI") -> str:
    """Generate WhatsApp birthday greeting link."""
    first_name = client_name.split()[0] if client_name else "Sir/Ma'am"
    msg = (
        f"🎂 Happy Birthday, {first_name}! 🎉\n\n"
        f"Wishing you a wonderful year filled with good health, "
        f"happiness, and prosperity!\n\n"
        f"Warm wishes,\n{agent_name}\n{company} 🌟"
    )
    return generate_wa_link(phone, msg)


def generate_calc_share_link(phone: str, client_name: str, calc_type: str,
                              summary: str, report_url: str = "",
                              agent_name: str = "Your Advisor",
                              company: str = "Sarathi-AI") -> str:
    """Generate WhatsApp link for sharing calculator results."""
    first_name = client_name.split()[0] if client_name else "Sir/Ma'am"
    msg = (
        f"📊 Financial Analysis for {first_name}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"{summary}\n\n"
    )
    if report_url:
        msg += f"📎 View detailed report: {report_url}\n\n"
    msg += f"Prepared by: {agent_name}\n{company} 🛡️"
    return generate_wa_link(phone, msg)


async def send_or_link(to: str, message: str) -> dict:
    """
    Smart sender: uses Cloud API if configured, otherwise returns wa.me link.
    Auto-fallback to link if API call fails (expired token, network error).
    """
    if is_configured():
        result = await send_text(to, message)
        if result.get('success'):
            return result
        logger.warning("WhatsApp API failed, falling back to wa.me link: %s",
                       result.get('error', 'unknown'))
    link = generate_wa_link(to, message)
    return {"success": True, "method": "link", "wa_link": link}


async def send_calc_report(to: str, client_name: str, calc_type: str,
                            summary: str, report_url: str = "",
                            agent_name: str = "Your Advisor",
                            company: str = "Sarathi-AI") -> dict:
    """
    Send calculator report via WhatsApp.
    Uses Cloud API if available; otherwise returns click-to-send link.
    """
    first_name = client_name.split()[0] if client_name else "Sir/Ma'am"
    report_line = f"\n\n📎 View detailed report: {report_url}" if report_url else ""
    text_msg = (
        f"📊 *Financial Analysis for {first_name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{summary}\n\n"
        f"Prepared by: *{agent_name}*\n"
        f"_{company}_ 🛡️"
        f"{report_line}"
    )

    if is_configured():
        # Send text message
        result = await send_text(to, text_msg)
        if result.get('success'):
            # Send PDF document if available
            if report_url:
                await send_document(
                    to, report_url,
                    f"Financial_Analysis_{first_name}.pdf",
                    f"Detailed analysis prepared for {first_name}"
                )
            return result
        # API failed (expired token, network error) — auto-fallback to link
        logger.warning("WhatsApp API failed, falling back to wa.me link: %s",
                       result.get('error', 'unknown'))

    # Fallback to click-to-send link
    link = generate_calc_share_link(
        to, client_name, calc_type, summary,
        report_url, agent_name, company
    )
    return {"success": True, "method": "link", "wa_link": link}


# =============================================================================
#  MULTI-TENANT WHATSAPP — Send using tenant's own credentials
# =============================================================================

async def send_text_for_tenant(tenant: dict, to: str, message: str) -> dict:
    """
    Send a WhatsApp message using a specific tenant's credentials.
    Falls back to global creds if tenant has no WA config.
    Falls back to wa.me link if neither is configured.
    """
    phone_id = tenant.get("wa_phone_id", "")
    token = tenant.get("wa_access_token", "")

    if not phone_id or not token:
        # Tenant has no WA config — try global
        if is_configured():
            return await send_text(to, message)
        else:
            link = generate_wa_link(to, message)
            return {"success": True, "method": "link", "wa_link": link}

    to = _normalize_phone(to)
    url = f"{WA_API_BASE}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }

    try:
        client = _get_client()
        resp = await client.post(url, headers=headers, json=payload)
        data = resp.json()
        if resp.status_code == 200:
            msg_id = data.get("messages", [{}])[0].get("id", "unknown")
            logger.info("WA(tenant %s) sent to %s (msg_id: %s)",
                        tenant.get("tenant_id"), to, msg_id)
            return {"success": True, "message_id": msg_id}
        else:
            logger.error("WA(tenant %s) send failed: %s",
                         tenant.get("tenant_id"), data)
            return {"error": data}
    except (httpx.TimeoutException, httpx.ConnectError, ConnectionError,
            TimeoutError, OSError) as e:
        logger.warning("WA(tenant %s) network error: %s", tenant.get("tenant_id"), e)
        return {"error": str(e), "retryable": True}
    except Exception as e:
        logger.error("WA(tenant %s) send error: %s", tenant.get("tenant_id"), e)
        return {"error": str(e)}


async def verify_tenant_wa_credentials(phone_id: str, access_token: str) -> dict:
    """Test if tenant's WhatsApp credentials are valid by calling the API."""
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        check_url = f"{WA_API_BASE}/{phone_id}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(check_url, headers=headers)
            data = resp.json()
            if resp.status_code == 200:
                return {
                    "valid": True,
                    "phone_number": data.get("display_phone_number", ""),
                    "verified_name": data.get("verified_name", ""),
                    "quality_rating": data.get("quality_rating", ""),
                }
            else:
                error = data.get("error", {})
                return {
                    "valid": False,
                    "error": error.get("message", "Invalid credentials"),
                    "error_code": error.get("code", 0),
                }
    except Exception as e:
        return {"valid": False, "error": str(e)}


# =============================================================================
#  OTP DELIVERY via WhatsApp
# =============================================================================

async def send_otp(to: str, otp: str) -> dict:
    """Send OTP to a phone number via WhatsApp (platform-level)."""
    message = (
        f"🔐 *Sarathi-AI Login OTP*\n\n"
        f"Your one-time password is: *{otp}*\n\n"
        f"⏰ Valid for 10 minutes.\n"
        f"⚠️ Do not share this code with anyone.\n\n"
        f"_If you didn't request this, please ignore._"
    )
    return await send_text(to, message)


# =============================================================================
#  INCOMING MESSAGE PROCESSING — Route incoming WA messages to tenants
# =============================================================================

async def process_incoming_message(message: dict) -> dict:
    """
    Process an incoming WhatsApp message:
    1. Match the sender's phone to a lead in the database
    2. Log the interaction
    3. Notify the agent via Telegram
    4. Send auto-acknowledgement to the customer
    """
    import aiosqlite
    import biz_database as db_mod

    from_number = message.get("from_number", "")
    text = message.get("message_text", "")
    msg_type = message.get("message_type", "text")
    sender_name = message.get("name", "")

    if not from_number:
        return {"status": "skipped", "reason": "no_from_number"}

    # Normalize phone for lookup
    phone_clean = from_number.replace("+", "").strip()
    phone_10 = phone_clean[2:] if phone_clean.startswith("91") and len(phone_clean) == 12 else phone_clean

    result = {"status": "processed", "from": from_number}

    try:
        async with aiosqlite.connect(db_mod.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """SELECT l.lead_id, l.name, l.agent_id, a.telegram_user_id,
                          a.name as agent_name, a.tenant_id,
                          t.firm_name, t.wa_phone_id, t.wa_access_token
                   FROM leads l
                   JOIN agents a ON l.agent_id = a.agent_id
                   JOIN tenants t ON a.tenant_id = t.tenant_id
                   WHERE l.phone IN (?, ?, ?)
                   AND a.is_active = 1 AND t.is_active = 1
                   LIMIT 1""",
                (phone_clean, phone_10, f"91{phone_10}"))
            lead_row = await cursor.fetchone()

        if lead_row:
            lead = dict(lead_row)
            result.update({
                "lead_id": lead["lead_id"],
                "lead_name": lead["name"],
                "agent_id": lead["agent_id"],
                "tenant_id": lead["tenant_id"],
            })

            # Log the interaction
            await db_mod.log_interaction(
                lead_id=lead["lead_id"],
                agent_id=lead["agent_id"],
                interaction_type="whatsapp_received",
                channel="whatsapp",
                summary=f"From {sender_name or from_number}: {text[:200]}")

            # Build Telegram notification for the agent
            tg_user_id = lead.get("telegram_user_id")
            if tg_user_id:
                result["notify_agent"] = {
                    "telegram_user_id": tg_user_id,
                    "message": (
                        f"💬 <b>WhatsApp message from {lead['name']}</b>\n"
                        f"📱 {from_number}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"{text[:500] if text else f'[{msg_type}]'}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"<i>Reply via /wa {lead['lead_id']} &lt;your message&gt;</i>"
                    ),
                }

            # Auto-acknowledge to the customer
            if lead.get("wa_phone_id") and lead.get("wa_access_token"):
                ack_msg = (
                    f"✅ Thanks {sender_name or 'there'}! Your message has been "
                    f"received by *{lead.get('agent_name', 'your advisor')}* "
                    f"at _{lead.get('firm_name', 'our firm')}_.\n\n"
                    f"We'll get back to you shortly! 🙏"
                )
                tenant_dict = {
                    "tenant_id": lead["tenant_id"],
                    "wa_phone_id": lead["wa_phone_id"],
                    "wa_access_token": lead["wa_access_token"],
                }
                await send_text_for_tenant(tenant_dict, from_number, ack_msg)
        else:
            result["status"] = "unmatched"
            result["reason"] = "Phone not linked to any lead"
            logger.info("WA message from unknown number %s: %s",
                        from_number, text[:50])

    except Exception as e:
        logger.error("Error processing incoming WA message: %s", e)
        result["status"] = "error"
        result["error"] = str(e)

    return result


# =============================================================================
#  WHATSAPP SETUP GUIDE
# =============================================================================

def get_wa_setup_guide() -> dict:
    """Return a comprehensive WhatsApp Business API setup guide."""
    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
    return {
        "title": "WhatsApp Business Integration — Setup Guide",
        "estimated_time": "15–20 minutes",
        "prerequisites": [
            "A Facebook Business account (business.facebook.com)",
            "A phone number NOT already registered on WhatsApp",
            "Your firm name & business details",
        ],
        "steps": [
            {
                "step": 1,
                "title": "Create a Meta Developer Account",
                "instructions": [
                    "Go to developers.facebook.com",
                    "Click 'Get Started' and log in with your Facebook account",
                    "Accept the Meta developer terms",
                ],
                "url": "https://developers.facebook.com/",
            },
            {
                "step": 2,
                "title": "Create a Meta App",
                "instructions": [
                    "In the Meta Developer Dashboard, click 'Create App'",
                    "Choose 'Business' app type",
                    "Name it something like 'My Insurance WhatsApp'",
                    "Pick your Facebook Business account",
                ],
            },
            {
                "step": 3,
                "title": "Add WhatsApp to Your App",
                "instructions": [
                    "In your app dashboard, find 'WhatsApp' and click 'Set Up'",
                    "You'll see a test phone number (free) — use this for testing",
                    "Note down the 'Phone Number ID' (under API Setup)",
                    "Note down the 'Temporary Access Token' (valid 24h)",
                ],
            },
            {
                "step": 4,
                "title": "Generate a Permanent Token",
                "instructions": [
                    "Go to Business Settings → System Users",
                    "Create a system user (Admin role)",
                    "Click 'Generate Token' → select your WhatsApp app",
                    "Select permissions: whatsapp_business_messaging, whatsapp_business_management",
                    "Copy the token — this is your permanent access token",
                ],
                "url": "https://business.facebook.com/settings/system-users",
            },
            {
                "step": 5,
                "title": "Add Your Phone Number (Production)",
                "instructions": [
                    "In WhatsApp API Setup, click 'Add Phone Number'",
                    "Enter your business phone number",
                    "Verify via SMS or voice call",
                    "Update 'Phone Number ID' in Sarathi-AI settings",
                ],
                "note": "Skip for testing — the test number works fine",
            },
            {
                "step": 6,
                "title": "Configure Webhook (Incoming Messages)",
                "instructions": [
                    "In your Meta app → WhatsApp → Configuration",
                    f"Set Webhook URL to: {server_url}/webhook",
                    "Set Verify Token to the value shown in your Sarathi-AI WhatsApp settings",
                    "Subscribe to the 'messages' webhook field",
                ],
                "note": "This enables two-way communication",
            },
            {
                "step": 7,
                "title": "Enter Credentials in Sarathi-AI",
                "instructions": [
                    "Go to your Sarathi-AI Dashboard → Settings → WhatsApp",
                    "Enter your Phone Number ID",
                    "Enter your Permanent Access Token",
                    "Click 'Verify & Save'",
                    "Send a test message to confirm!",
                ],
            },
        ],
        "troubleshooting": [
            {"issue": "Messages not sending",
             "fix": "Check if your access token is expired. Temp tokens last 24h."},
            {"issue": "Webhook not receiving messages",
             "fix": "Verify webhook URL is correct and server is accessible."},
            {"issue": "Message failed to send",
             "fix": "24h messaging window — customer must message you first."},
            {"issue": "Rate limited",
             "fix": "Test accounts allow ~250 msgs/day. Get verified for higher."},
        ],
    }
