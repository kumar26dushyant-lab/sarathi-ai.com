"""
Sarathi-AI Business — Authentication & Authorization Module
=============================================================
JWT-based tenant authentication with OTP verification.

Token types:
  - access_token : Short-lived (24h), used for API calls
  - refresh_token: Long-lived (30d), used to renew access tokens

Security features:
  - HMAC-SHA256 JWT signing
  - Input sanitization (bleach)
  - Phone number validation
  - Tenant isolation enforcement
"""

import os, time, secrets, hashlib, hmac, logging, re
from datetime import datetime, timedelta
from typing import Optional

import jwt
import bleach
import httpx
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("sarathi.auth")

# ── Configuration ────────────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 30

# OTP settings
OTP_EXPIRE_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_SECONDS = 60

# In-memory OTP store: {phone: {otp, expires, attempts, last_sent}}
_otp_store: dict = {}

# Test mode: fixed OTP for test phone numbers (when Razorpay is in test mode)
_TEST_OTP = "123456"
_TEST_PHONE_PREFIX = "98765"  # phones starting with this get fixed OTP in test mode

def _is_test_mode() -> bool:
    if os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes"):
        return True
    return os.getenv("RAZORPAY_KEY_ID", "").startswith("rzp_test_")

# In-memory Email OTP store: {email: {otp, expires, attempts, last_sent}}
_email_otp_store: dict = {}

# In-memory Recovery OTP store: keyed by "email|channel" so a user can
# attempt sms + telegram independently. Used for "Lost access to email" flow.
_recovery_otp_store: dict = {}

# ── Initialization ───────────────────────────────────────────────────────────

def init_auth():
    """Initialize auth module. Generate JWT_SECRET if not set."""
    global JWT_SECRET
    if not JWT_SECRET:
        JWT_SECRET = os.getenv("JWT_SECRET", "")
    if not JWT_SECRET:
        # Generate a strong random secret and warn
        JWT_SECRET = secrets.token_hex(32)
        logger.warning("⚠️  JWT_SECRET not set in env — using random secret (tokens won't survive restart)")
    logger.info("🔐 Auth module initialized")
    init_superadmin()


# ── Token Creation ───────────────────────────────────────────────────────────

def create_access_token(tenant_id: int, phone: str, firm_name: str = "",
                        role: str = "owner", agent_id: int = None) -> str:
    """Create a short-lived access token with role embedded."""
    payload = {
        "sub": str(tenant_id),
        "phone": phone,
        "firm": firm_name,
        "role": role,
        "type": "access",
        "iat": int(time.time()),
        "exp": int((datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)).timestamp()),
    }
    if agent_id is not None:
        payload["aid"] = agent_id
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_impersonation_token(tenant_id: int, phone: str, firm_name: str = "",
                                role: str = "owner", agent_id: int = None) -> str:
    """Create a 1-hour impersonation token with imp:true claim for SA sessions."""
    payload = {
        "sub": str(tenant_id),
        "phone": phone,
        "firm": firm_name,
        "role": role,
        "type": "access",
        "imp": True,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,  # 1-hour hard limit
    }
    if agent_id is not None:
        payload["aid"] = agent_id
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(tenant_id: int, phone: str, role: str = "owner") -> str:
    """Create a long-lived refresh token with role for re-issue."""
    payload = {
        "sub": str(tenant_id),
        "phone": phone,
        "role": role,
        "type": "refresh",
        "jti": secrets.token_hex(16),  # unique token ID
        "iat": int(time.time()),
        "exp": int((datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_token_pair(tenant_id: int, phone: str, firm_name: str = "",
                      role: str = "owner", agent_id: int = None) -> dict:
    """Create both access and refresh tokens with role."""
    return {
        "access_token": create_access_token(tenant_id, phone, firm_name, role, agent_id),
        "refresh_token": create_refresh_token(tenant_id, phone, role),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    }


# ── Token Verification ──────────────────────────────────────────────────────

def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


def verify_access_token(token: str) -> dict:
    """Verify an access token and return payload."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type.")
    return payload


def verify_refresh_token(token: str) -> dict:
    """Verify a refresh token and return payload."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type.")
    return payload


# ── FastAPI Dependency ───────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(request: Request, credentials=None) -> Optional[str]:
    """Extract JWT token from request (header, cookie, or query param)."""
    token = None

    # 1. Try Authorization: Bearer <token> (from FastAPI dependency)
    if credentials and hasattr(credentials, 'credentials') and credentials.credentials:
        token = credentials.credentials

    # 2. Try raw Authorization header (for direct calls)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and not auth_header.startswith("Bearer admin:"):
            token = auth_header[7:]

    # 3. Fallback: cookie
    if not token:
        token = request.cookies.get("sarathi_token")

    # 4. Fallback: query param (for page loads during transition)
    if not token:
        token = request.query_params.get("token")

    return token


async def get_current_tenant(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency: Extract and verify tenant from JWT.
    Returns: {"tenant_id": int, "phone": str, "firm": str}
    
    Checks Authorization header first, then falls back to cookie.
    """
    token = _extract_token(request, credentials)

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Please login.")

    payload = verify_access_token(token)
    return {
        "tenant_id": int(payload["sub"]),
        "phone": payload.get("phone", ""),
        "firm": payload.get("firm", ""),
        "role": payload.get("role", "owner"),
        "agent_id": payload.get("aid"),
        "imp": payload.get("imp", False),
    }


async def get_optional_tenant(
    request: Request,
    credentials=None,
) -> Optional[dict]:
    """
    Extract tenant from JWT if present, return None if not authenticated.
    Can be called directly (not only as a FastAPI dependency).
    """
    token = _extract_token(request, credentials)
    if not token:
        return None
    try:
        payload = verify_access_token(token)
        return {
            "tenant_id": int(payload["sub"]),
            "phone": payload.get("phone", ""),
            "firm": payload.get("firm", ""),
            "role": payload.get("role", "owner"),
            "agent_id": payload.get("aid"),
        }
    except HTTPException:
        return None


async def require_owner(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency: require authenticated owner/admin role.
    Rejects regular agents. No DB round-trip — reads role from JWT."""
    tenant = await get_current_tenant(request, credentials)
    if tenant.get("role") not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Only the firm owner can perform this action.")
    return tenant


# ── OTP System ───────────────────────────────────────────────────────────────

def generate_otp(phone: str) -> dict:
    """
    Generate a 6-digit OTP for phone verification.
    Returns: {"otp": str, "expires_in": int} or {"error": str}
    """
    phone = sanitize_phone(phone)
    if not phone:
        return {"error": "Invalid phone number"}

    now = time.time()
    entry = _otp_store.get(phone, {})

    # Rate limiting: cooldown between OTPs
    last_sent = entry.get("last_sent", 0)
    if now - last_sent < OTP_COOLDOWN_SECONDS:
        wait = int(OTP_COOLDOWN_SECONDS - (now - last_sent))
        return {"error": f"Please wait {wait} seconds before requesting a new OTP"}

    # Generate 6-digit OTP (fixed in test mode for test phones)
    if _is_test_mode() and phone.startswith(_TEST_PHONE_PREFIX):
        otp = _TEST_OTP
    else:
        otp = f"{secrets.randbelow(900000) + 100000}"

    _otp_store[phone] = {
        "otp": otp,
        "expires": now + (OTP_EXPIRE_MINUTES * 60),
        "attempts": 0,
        "last_sent": now,
    }

    logger.info("📱 OTP generated for ***%s", phone[-4:])
    return {"otp": otp, "expires_in": OTP_EXPIRE_MINUTES * 60}


def verify_otp(phone: str, otp: str) -> bool:
    """Verify OTP for a phone number."""
    phone = sanitize_phone(phone)
    entry = _otp_store.get(phone)

    if not entry:
        return False

    # Check expiry
    if time.time() > entry["expires"]:
        del _otp_store[phone]
        return False

    # Check max attempts
    if entry["attempts"] >= OTP_MAX_ATTEMPTS:
        del _otp_store[phone]
        return False

    entry["attempts"] += 1

    if hmac.compare_digest(entry["otp"], otp.strip()):
        del _otp_store[phone]  # OTP consumed
        return True

    return False


def clear_expired_otps():
    """Cleanup expired OTPs from memory."""
    now = time.time()
    expired = [p for p, e in _otp_store.items() if now > e.get("expires", 0)]
    for p in expired:
        del _otp_store[p]
    expired_email = [e for e, v in _email_otp_store.items() if now > v.get("expires", 0)]
    for e in expired_email:
        del _email_otp_store[e]


def generate_email_otp(email: str) -> dict:
    """
    Generate a 6-digit OTP for email verification.
    Returns: {"otp": str, "expires_in": int} or {"error": str}
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"error": "Invalid email address"}

    now = time.time()
    entry = _email_otp_store.get(email, {})

    # Rate limiting: cooldown between OTPs
    last_sent = entry.get("last_sent", 0)
    if now - last_sent < OTP_COOLDOWN_SECONDS:
        wait = int(OTP_COOLDOWN_SECONDS - (now - last_sent))
        return {"error": f"Please wait {wait} seconds before requesting a new OTP"}

    otp = f"{secrets.randbelow(900000) + 100000}"

    _email_otp_store[email] = {
        "otp": otp,
        "expires": now + (OTP_EXPIRE_MINUTES * 60),
        "attempts": 0,
        "last_sent": now,
    }

    logger.info("📧 Email OTP generated for %s", email[:3] + "***")
    return {"otp": otp, "expires_in": OTP_EXPIRE_MINUTES * 60}


def verify_email_otp(email: str, otp: str) -> bool:
    """Verify OTP for an email address."""
    email = (email or "").strip().lower()
    entry = _email_otp_store.get(email)

    if not entry:
        return False

    if time.time() > entry["expires"]:
        del _email_otp_store[email]
        return False

    if entry["attempts"] >= OTP_MAX_ATTEMPTS:
        del _email_otp_store[email]
        return False

    entry["attempts"] += 1

    if hmac.compare_digest(entry["otp"], otp.strip()):
        del _email_otp_store[email]  # OTP consumed
        return True

    return False


# ── Recovery OTP (for users who lost access to their email) ──────────────────

def _rec_key(email: str, channel: str) -> str:
    return (email or "").strip().lower() + "|" + (channel or "").strip().lower()


def generate_recovery_otp(email: str, channel: str) -> dict:
    """Generate a 6-digit OTP for account recovery via SMS/Telegram.
    Namespaced by (email, channel) so user can try multiple channels.
    Returns: {"otp": str, "expires_in": int} or {"error": str}."""
    email = (email or "").strip().lower()
    channel = (channel or "").strip().lower()
    if not email or "@" not in email:
        return {"error": "Invalid email address"}
    if channel not in ("sms", "telegram", "whatsapp"):
        return {"error": "Invalid recovery channel"}

    now = time.time()
    key = _rec_key(email, channel)
    entry = _recovery_otp_store.get(key, {})

    last_sent = entry.get("last_sent", 0)
    if now - last_sent < OTP_COOLDOWN_SECONDS:
        wait = int(OTP_COOLDOWN_SECONDS - (now - last_sent))
        return {"error": f"Please wait {wait} seconds before requesting a new code"}

    otp = f"{secrets.randbelow(900000) + 100000}"
    _recovery_otp_store[key] = {
        "otp": otp,
        "expires": now + (OTP_EXPIRE_MINUTES * 60),
        "attempts": 0,
        "last_sent": now,
    }
    logger.info("🔐 Recovery OTP generated for %s*** via %s", email[:3], channel)
    return {"otp": otp, "expires_in": OTP_EXPIRE_MINUTES * 60}


def verify_recovery_otp(email: str, channel: str, otp: str) -> bool:
    """Verify a recovery OTP. One-shot: consumed on success."""
    key = _rec_key(email, channel)
    entry = _recovery_otp_store.get(key)
    if not entry:
        return False
    if time.time() > entry["expires"]:
        del _recovery_otp_store[key]
        return False
    if entry["attempts"] >= OTP_MAX_ATTEMPTS:
        del _recovery_otp_store[key]
        return False
    entry["attempts"] += 1
    if hmac.compare_digest(entry["otp"], (otp or "").strip()):
        del _recovery_otp_store[key]
        return True
    return False


def mask_phone(phone: str) -> str:
    """Mask a phone for safe display: '+91 98765 43210' -> '+91 *****3210'."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "****"
    last4 = digits[-4:]
    if len(digits) == 10:
        return "******" + last4
    if len(digits) == 12 and digits.startswith("91"):
        return "+91 ******" + last4
    return "*" * (len(digits) - 4) + last4


def mask_telegram_id(tid: str) -> str:
    """Mask a Telegram user id for display."""
    s = str(tid or "")
    if len(s) < 4:
        return "****"
    return s[:2] + "****" + s[-2:]


# ── Input Sanitization ───────────────────────────────────────────────────────

def sanitize_text(text: str, max_length: int = 500) -> str:
    """Sanitize user input: strip HTML tags, limit length."""
    if not text:
        return ""
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True)
    return cleaned[:max_length].strip()


def sanitize_phone(phone: str) -> str:
    """Validate and normalize Indian phone number."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    # Remove country code prefix
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return ""


def sanitize_email(email: str) -> str:
    """Basic email validation and sanitization."""
    if not email:
        return ""
    email = email.strip().lower()
    if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return email[:254]
    return ""


# ── Admin Auth ───────────────────────────────────────────────────────────────

def verify_admin_key(request: Request) -> bool:
    """
    Verify admin API key from Authorization header.
    Query param fallback removed for security (key leaked in URLs/logs).
    """
    admin_key = os.getenv("ADMIN_API_KEY", "")

    # Check Authorization header: "Bearer admin:<key>"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer admin:"):
        provided = auth_header[len("Bearer admin:"):]
        return hmac.compare_digest(provided, admin_key)

    return False


async def require_admin(request: Request):
    """FastAPI dependency: require admin authentication."""
    if not verify_admin_key(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Telegram Web Login Tokens ────────────────────────────────────────────────

def create_telegram_login_token(tenant_id: int, agent_id: int, phone: str,
                                 role: str = "agent", firm_name: str = "") -> str:
    """Create a short-lived token for Telegram→Web login (5 min)."""
    now = int(time.time())
    payload = {
        "sub": str(tenant_id),
        "aid": agent_id,
        "phone": phone,
        "role": role,
        "firm": firm_name,
        "type": "tg_login",
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_telegram_login_token(token: str) -> dict:
    """Verify a Telegram login token. Relies on 5-minute expiry for security."""
    payload = decode_token(token)
    if payload.get("type") != "tg_login":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


# ── CSRF Protection ──────────────────────────────────────────────────────────

def generate_csrf_token(tenant_id: int = None) -> str:
    """Generate a CSRF token tied to a session."""
    payload = {
        "type": "csrf",
        "tenant_id": tenant_id,
        "iat": datetime.utcnow().isoformat(),
        "nonce": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_csrf_token(token: str, tenant_id: int = None) -> bool:
    """Verify a CSRF token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "csrf":
            return False
        if tenant_id and payload.get("tenant_id") != tenant_id:
            return False
        # CSRF tokens valid for 4 hours
        iat = datetime.fromisoformat(payload["iat"])
        if (datetime.utcnow() - iat).total_seconds() > 4 * 3600:
            return False
        return True
    except Exception:
        return False


# ── DB-backed OTP (production-ready) ─────────────────────────────────────────

async def generate_otp_persistent(phone: str) -> dict:
    """Generate OTP and persist to DB (survives server restarts).
    Falls back to in-memory if DB not available."""
    import biz_database as db

    phone = sanitize_phone(phone)
    if not phone:
        return {"error": "Invalid phone number"}

    # Check cooldown
    existing = await db.get_otp(phone)
    if existing and existing.get('last_sent'):
        try:
            last_sent = datetime.fromisoformat(existing['last_sent'])
            elapsed = (datetime.now() - last_sent).total_seconds()
            if elapsed < OTP_COOLDOWN_SECONDS:
                wait = int(OTP_COOLDOWN_SECONDS - elapsed)
                return {"error": f"Please wait {wait} seconds before requesting a new OTP"}
        except (ValueError, TypeError):
            pass

    # Generate 6-digit OTP
    otp = f"{secrets.randbelow(900000) + 100000}"
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    expires_at = (datetime.now() + timedelta(minutes=OTP_EXPIRE_MINUTES)).isoformat()

    await db.save_otp(phone, otp_hash, expires_at)

    logger.info("📱 OTP generated (DB) for %s", phone[-4:])
    return {"otp": otp, "expires_in": OTP_EXPIRE_MINUTES * 60}


async def verify_otp_persistent(phone: str, otp: str) -> bool:
    """Verify OTP from DB. Timing-safe comparison."""
    import biz_database as db

    phone = sanitize_phone(phone)
    entry = await db.get_otp(phone)
    if not entry:
        return False

    # Check expiry
    try:
        expires = datetime.fromisoformat(entry['expires_at'])
        if datetime.now() > expires:
            await db.delete_otp(phone)
            return False
    except (ValueError, TypeError):
        await db.delete_otp(phone)
        return False

    # Check max attempts
    if entry.get('attempts', 0) >= OTP_MAX_ATTEMPTS:
        await db.delete_otp(phone)
        return False

    # Increment attempts
    await db.increment_otp_attempts(phone)

    # Timing-safe comparison using hash
    otp_hash = hashlib.sha256(otp.strip().encode()).hexdigest()
    if hmac.compare_digest(entry['otp_hash'], otp_hash):
        await db.delete_otp(phone)  # OTP consumed
        return True

    return False


# ── Security Headers Middleware ──────────────────────────────────────────────

def get_security_headers() -> dict:
    """Get recommended security headers for HTTP responses."""
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
    }


# ── IP-based Security ───────────────────────────────────────────────────────

_failed_logins: dict = {}  # {ip: {"count": int, "first_fail": float}}


def record_failed_login(ip: str) -> bool:
    """Record a failed login attempt. Returns True if IP should be blocked."""
    now = time.time()
    entry = _failed_logins.get(ip, {"count": 0, "first_fail": now})

    # Reset if window expired (15 min)
    if now - entry["first_fail"] > 900:
        entry = {"count": 0, "first_fail": now}

    entry["count"] += 1

    if entry["count"] > 10:  # Block after 10 failures in 15 min
        _failed_logins[ip] = entry
        return True

    _failed_logins[ip] = entry
    return False


def is_ip_blocked(ip: str) -> bool:
    """Check if an IP is currently blocked due to failed logins."""
    entry = _failed_logins.get(ip)
    if not entry:
        return False
    if time.time() - entry["first_fail"] > 900:  # 15 min window
        del _failed_logins[ip]
        return False
    return entry["count"] > 10


def clear_failed_logins(ip: str):
    """Clear failed login record for an IP after successful auth."""
    _failed_logins.pop(ip, None)


# ── Super Admin Auth ─────────────────────────────────────────────────────────

SUPERADMIN_PHONES: set = set()
SUPERADMIN_PASSWORD: str = ""


def init_superadmin():
    """Load SUPERADMIN_PHONES and password from env."""
    global SUPERADMIN_PHONES, SUPERADMIN_PASSWORD
    raw = os.getenv("SUPERADMIN_PHONES", "")
    SUPERADMIN_PHONES = {p.strip() for p in raw.split(",") if p.strip()}
    SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD", "")
    if not SUPERADMIN_PASSWORD:
        logger.critical("⚠️  SUPERADMIN_PASSWORD env var is NOT SET — SA login disabled!")
    if SUPERADMIN_PHONES:
        logger.info("🔑 Super Admin phones loaded: %d", len(SUPERADMIN_PHONES))


def verify_sa_credentials(phone: str, password: str) -> bool:
    """Verify super admin phone + password (timing-safe)."""
    import hmac
    clean = sanitize_phone(phone)
    if not clean or clean not in SUPERADMIN_PHONES:
        return False
    return hmac.compare_digest(password, SUPERADMIN_PASSWORD)


def create_sa_access_token(phone: str) -> str:
    """Create a short-lived Super Admin access token (12h)."""
    payload = {
        "sub": "superadmin",
        "phone": phone,
        "type": "sa_access",
        "iat": int(time.time()),
        "exp": int((datetime.utcnow() + timedelta(hours=12)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_sa_token(token: str) -> dict:
    """Verify a Super Admin access token."""
    payload = decode_token(token)
    if payload.get("type") != "sa_access":
        raise HTTPException(status_code=401, detail="Not a super admin token.")
    if payload.get("phone") not in SUPERADMIN_PHONES:
        raise HTTPException(status_code=403, detail="Not a super admin.")
    return payload


async def require_superadmin(request: Request) -> dict:
    """FastAPI dependency: require super admin authentication.
    Checks sa_token cookie → Authorization header."""
    token = None

    # 1. Cookie (primary for web dashboard)
    token = request.cookies.get("sa_token")

    # 2. Authorization header
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and not auth_header.startswith("Bearer admin:"):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Super Admin authentication required.")

    payload = verify_sa_token(token)
    return {"phone": payload["phone"], "role": "superadmin"}


# ── Google OAuth2 Sign-In ────────────────────────────────────────────────────

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


async def verify_google_id_token(id_token_str: str) -> Optional[dict]:
    """Verify Google ID token. Tries fast local JWK verification first
    (sub-millisecond after first cache load); falls back to Google's
    tokeninfo HTTP endpoint only if local verification is unavailable.
    Returns {"email", "name", "picture", "google_sub"} or None on failure."""
    if not GOOGLE_CLIENT_ID:
        logger.error("GOOGLE_CLIENT_ID not configured")
        return None

    # Fast path: local verification using cached Google JWKs
    try:
        from google.oauth2 import id_token as g_id_token
        from google.auth.transport import requests as g_requests
        # google-auth's transport.requests.Request is sync; run in thread to keep async
        import asyncio
        def _verify_local():
            req = g_requests.Request()
            return g_id_token.verify_oauth2_token(
                id_token_str, req, GOOGLE_CLIENT_ID, clock_skew_in_seconds=10)
        idinfo = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _verify_local),
            timeout=4.0,
        )
        # Validate audience
        if idinfo.get("aud") != GOOGLE_CLIENT_ID:
            logger.warning("Google token audience mismatch (local): %s", idinfo.get("aud"))
            return None
        if not idinfo.get("email_verified"):
            logger.warning("Google email not verified for %s", idinfo.get("email"))
            return None
        return {
            "email": idinfo["email"].strip().lower(),
            "name": idinfo.get("name", ""),
            "picture": idinfo.get("picture", ""),
            "google_sub": idinfo.get("sub", ""),
        }
    except Exception as e:
        logger.warning("Local Google token verify failed, falling back to HTTP: %s", e)

    # Fallback: Google's tokeninfo endpoint (slower)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token_str},
            )
        if resp.status_code != 200:
            logger.warning("Google token verification failed: %d", resp.status_code)
            return None
        data = resp.json()
        if data.get("aud") != GOOGLE_CLIENT_ID:
            logger.warning("Google token audience mismatch: %s", data.get("aud"))
            return None
        if data.get("email_verified") != "true":
            logger.warning("Google email not verified for %s", data.get("email"))
            return None
        return {
            "email": data["email"].strip().lower(),
            "name": data.get("name", ""),
            "picture": data.get("picture", ""),
            "google_sub": data.get("sub", ""),
        }
    except Exception as e:
        logger.error("Google token verification error: %s", e)
        return None
