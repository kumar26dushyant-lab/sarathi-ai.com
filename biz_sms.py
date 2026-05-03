"""
Sarathi-AI Business — SMS OTP Module (Fast2SMS)
=================================================
Budget-friendly SMS OTP delivery via Fast2SMS (India).

Fast2SMS OTP Route:
  - No DLT registration required
  - ~15 paise per SMS
  - Dedicated OTP API with auto-generated template
  - Sign up at https://www.fast2sms.com and get API key

Environment variables:
  FAST2SMS_API_KEY  — your Fast2SMS API authorization key
"""

import os
import logging
import httpx

logger = logging.getLogger("sarathi.sms")

# ── Configuration ────────────────────────────────────────────────────────────
_api_key: str = ""
_initialized: bool = False
_API_URL = "https://www.fast2sms.com/dev/bulkV2"


def init_sms():
    """Initialize SMS configuration from environment."""
    global _api_key, _initialized

    _api_key = os.getenv("FAST2SMS_API_KEY", "").strip()
    if _api_key:
        _initialized = True
        logger.info("✅ SMS (Fast2SMS) ready")
    else:
        _initialized = False
        logger.warning("⚠️  SMS not configured — set FAST2SMS_API_KEY in biz.env")


def is_configured() -> bool:
    return _initialized


async def send_otp(phone: str, otp: str) -> dict:
    """
    Send OTP via Fast2SMS OTP route.
    phone: 10-digit Indian mobile (no country code)
    otp:   6-digit OTP string
    Returns: {"success": True/False, "detail": str}
    """
    if not _initialized:
        logger.warning("SMS not sent (not configured) → %s", phone[-4:])
        return {"success": False, "detail": "SMS not configured"}

    # Strip country code if present
    phone = phone.lstrip("+").lstrip("91") if len(phone) > 10 else phone
    if len(phone) != 10:
        return {"success": False, "detail": "Invalid phone number"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _API_URL,
                params={
                    "authorization": _api_key,
                    "route": "otp",
                    "variables_values": otp,
                    "flash": "0",
                    "numbers": phone,
                },
            )
            data = resp.json()

        if resp.status_code == 200 and data.get("return"):
            logger.info("📱 SMS OTP sent to %s via Fast2SMS", phone[-4:])
            return {"success": True, "detail": "SMS sent"}
        else:
            msg = data.get("message", str(data))
            logger.error("📱 SMS failed for %s: %s", phone[-4:], msg)
            return {"success": False, "detail": msg}

    except Exception as e:
        logger.error("📱 SMS error for %s: %s", phone[-4:], e)
        return {"success": False, "detail": str(e)}
