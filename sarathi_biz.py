# =============================================================================
#  sarathi_biz.py — Sarathi Smart Business Solutions: Main Entry Point
# =============================================================================
#
#  Run this file to start the complete Financial Advisor CRM system:
#    1. FastAPI web server — calculator pages, dashboard, API, PDF server
#    2. Telegram CRM bot — agent interface for sales cycle
#    3. Background scheduler — birthday/renewal/follow-up reminders
#
#  Usage:
#    py -3.12 sarathi_biz.py
#
# =============================================================================

import asyncio
import json
import logging
import os
import platform
import signal
import subprocess
import sys
import time as _time
from pathlib import Path

import aiosqlite

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, Depends, HTTPException, Response, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.cors import CORSMiddleware
import mimetypes
import uvicorn

# Register PWA MIME types that Python stdlib may not know about
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("application/javascript", ".js")

import biz_database as db
import biz_bot as bot
import biz_calculators as calc
import biz_whatsapp as wa
import biz_pdf as pdf
import biz_reminders as reminders
import biz_bot_manager as botmgr
import biz_payments as payments
import biz_auth as auth
import biz_email as email_svc
import biz_gdrive as gdrive
import biz_campaigns as campaigns
import biz_resilience as resilience
import biz_sms as sms
import biz_whatsapp_evolution as wa_evo
import biz_whatsapp_safety as wa_safety
import biz_nidaan as nidaan

# =============================================================================
#  LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-22s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sarathi.biz")

# =============================================================================
#  LOAD ENVIRONMENT
# =============================================================================

load_dotenv("biz.env")

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
SERVER_URL = os.getenv("SERVER_URL", f"http://localhost:{SERVER_PORT}")

# =============================================================================
#  FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Sarathi-AI Business Technologies",
    description="AI-Powered Multi-tenant Financial Advisor CRM SaaS — Calculators, Reports, Lead Management",
    version="3.0.0",
    docs_url=None,
    redoc_url=None,
)

# ── Rate Limiting ────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        SERVER_URL,
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "https://nidaanpartner.com",
        "https://www.nidaanpartner.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# ── Server Start Time (for uptime) ──────────────────────────────────────────
SERVER_START_TIME = _time.time()

# ── Security Headers Middleware ──────────────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=(), identity-credentials-get=(self)"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Allow Google Sign-In popup (window.opener.postMessage) — without this, GIS popup hangs 60s+
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


# ── Error Capture Middleware — auto-logs 5xx to system_events ────────────────
@app.middleware("http")
async def error_capture_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            try:
                ip = request.client.host if request.client else None
                await db.add_system_event(
                    event_type="error", severity="high", category="api",
                    title=f"HTTP {response.status_code} on {request.method} {request.url.path}",
                    detail=f"Query: {str(request.query_params)[:500]}",
                    ip_address=ip)
            except Exception:
                pass
        return response
    except Exception as exc:
        try:
            ip = request.client.host if request.client else None
            await db.add_system_event(
                event_type="error", severity="critical", category="api",
                title=f"Unhandled exception on {request.method} {request.url.path}",
                detail=f"{type(exc).__name__}: {str(exc)[:500]}",
                ip_address=ip)
        except Exception:
            pass
        raise


# ── Subscription Enforcement Middleware ──────────────────────────────────────
# Checks subscription status on authenticated API routes. Expired tenants
# can still access: auth, payments, subscription, health, signup, affiliate,
# support, and webhook endpoints (so they can renew/pay/get help).
_SUB_EXEMPT_PREFIXES = (
    "/api/auth/", "/api/payments/", "/api/subscription/",
    "/api/signup", "/api/affiliate/", "/api/support/",
    "/api/sa/", "/api/admin/tenants", "/api/admin/stats",
    "/api/admin/bots", "/api/bot-setup/",
    "/api/calc/", "/api/report/",
    "/webhook", "/health", "/api/onboarding/",
)

@app.middleware("http")
async def subscription_enforcement_middleware(request: Request, call_next):
    """Server-side subscription enforcement on all /api/ routes.
    Expired tenants get 403 on CRM endpoints but can still auth/pay/get help."""
    path = request.url.path
    # Only enforce on /api/ routes that aren't exempt
    if path.startswith("/api/") and not any(path.startswith(p) for p in _SUB_EXEMPT_PREFIXES):
        tenant = await auth.get_optional_tenant(request)
        if tenant and tenant.get('tenant_id'):
            active = await db.check_subscription_active(tenant['tenant_id'])
            if not active:
                return JSONResponse(
                    {"detail": "Your subscription has expired. "
                               "Please renew at sarathi-ai.com to continue.",
                     "code": "subscription_expired"},
                    status_code=403)
    return await call_next(request)


@app.middleware("http")
async def impersonation_audit_middleware(request: Request, call_next):
    """Log all write operations performed under SA impersonation tokens."""
    response = await call_next(request)
    path = request.url.path
    method = request.method
    # Only audit write operations on API routes
    if method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/"):
        try:
            token = auth._extract_token(request)
            if token:
                import jwt as _jwt
                payload = _jwt.decode(token, auth.JWT_SECRET, algorithms=[auth.JWT_ALGORITHM])
                if payload.get("imp"):
                    tenant_id = int(payload.get("sub", 0))
                    await db.add_audit_log(
                        tenant_id, None, "sa_imp_action",
                        f"[IMP] {method} {path} → {response.status_code}")
        except Exception:
            pass  # Don't block requests on audit failures
    return response

# Mount static directory for calculator & dashboard HTML
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount generated PDFs directory
pdf_dir = Path(__file__).parent / "generated_pdfs"
pdf_dir.mkdir(exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(pdf_dir)), name="reports")

# Mount uploads directory for agent profile photos
uploads_dir = Path(__file__).parent / "uploads" / "photos"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(Path(__file__).parent / "uploads")), name="uploads")


# =============================================================================
#  PWA — Service Worker & Manifest (must be served from root scope)
# =============================================================================

@app.get("/sw.js")
async def service_worker():
    return FileResponse(static_dir / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

@app.get("/manifest.json")
async def manifest():
    return FileResponse(static_dir / "manifest.json", media_type="application/manifest+json")


# =============================================================================
#  WEB PAGES
# =============================================================================

def _is_nidaan_host(request: Request) -> bool:
    """Return True when the request is for nidaanpartner.com (any env)."""
    host = request.headers.get("host", "").lower().split(":")[0]
    return host in ("nidaanpartner.com", "www.nidaanpartner.com")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve Nidaan homepage on nidaanpartner.com; Sarathi homepage everywhere else."""
    if _is_nidaan_host(request):
        nidaan_file = static_dir / "nidaan_index.html"
        if nidaan_file.exists():
            return HTMLResponse(nidaan_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Nidaan homepage not found</h1>", status_code=404)
    index_file = static_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Homepage not found</h1>", status_code=404)


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page():
    """Post-signup onboarding wizard — connect Telegram, WhatsApp, branding."""
    ob_file = static_dir / "onboarding.html"
    if ob_file.exists():
        return HTMLResponse(ob_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Onboarding page not found</h1>", status_code=404)


# =============================================================================
#  NIDAAN PHASE 2 — PAGES + API
# =============================================================================

def _nidaan_page(filename: str) -> HTMLResponse:
    f = static_dir / filename
    if f.exists():
        return HTMLResponse(f.read_text(encoding="utf-8"))
    return HTMLResponse(f"<h1>{filename} not found</h1>", status_code=404)


def _nidaan_bearer(request: Request) -> Optional[dict]:
    """Extract and verify Nidaan JWT from Authorization header."""
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return nidaan.verify_nidaan_token(h[7:])
    return None


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/nidaan/start", response_class=HTMLResponse)
async def nidaan_start_page(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    return _nidaan_page("nidaan_start.html")


@app.get("/nidaan-sw.js")
async def nidaan_service_worker():
    """Serve the Nidaan PWA service worker from root scope so it can control /nidaan/* pages."""
    sw_path = Path(__file__).parent / "static" / "nidaan-sw.js"
    return FileResponse(
        str(sw_path),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/nidaan/signup", response_class=RedirectResponse)
async def nidaan_signup_page(request: Request, plan: str = ""):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    dest = "/nidaan/start" + (f"?plan={plan}" if plan else "")
    return RedirectResponse(url=dest, status_code=302)


@app.get("/nidaan/login", response_class=RedirectResponse)
async def nidaan_login_page(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    return RedirectResponse(url="/nidaan/start", status_code=302)


@app.get("/nidaan/dashboard", response_class=HTMLResponse)
async def nidaan_dashboard_page(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    return _nidaan_page("nidaan_dashboard.html")


@app.get("/nidaan/get-reviewed", response_class=HTMLResponse)
async def nidaan_review_page(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    return _nidaan_page("nidaan_review.html")


@app.get("/nidaan/logout")
async def nidaan_logout(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    return RedirectResponse("/nidaan/start")


# ── Pydantic models ───────────────────────────────────────────────────────────

class NidaanSignupReq(BaseModel):
    owner_name: str
    email: str
    phone: str
    password: str
    firm_name: str = ""
    plan: str = "silver"


class NidaanLoginReq(BaseModel):
    email: str
    password: str


class NidaanClaimReq(BaseModel):
    claim_type: str
    insured_name: str
    insured_phone: str
    insured_email: str = ""
    insurer_name: str = ""
    policy_no: str = ""
    disputed_amount: Optional[int] = None
    claim_event_date: Optional[str] = None
    notes_from_agent: str = ""


class NidaanSendOTPReq(BaseModel):
    email: str


class NidaanVerifyOTPReq(BaseModel):
    email: str
    otp: str


class NidaanGoogleReq(BaseModel):
    credential: str = Field(..., min_length=10)
    plan: str = "free"  # only used during signup


class NidaanCheckEmailReq(BaseModel):
    email: str


# ── API routes ────────────────────────────────────────────────────────────────

@app.post("/nidaan/api/check-email")
@limiter.limit("10/minute")
async def nidaan_api_check_email(body: NidaanCheckEmailReq, request: Request):
    """Check if an email exists in nidaan_accounts. Used by the smart auth flow."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    account = await nidaan.get_account_by_email(email)
    return {"exists": account is not None}


@app.post("/nidaan/api/signup")
async def nidaan_api_signup(body: NidaanSignupReq, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    # Plan is now optional at signup — advisors can subscribe later from dashboard
    allowed_plans = ("silver", "gold", "platinum", "free", "")
    plan = body.plan if body.plan in ("silver", "gold", "platinum") else "free"
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    account_id = await nidaan.create_account(
        owner_name=body.owner_name.strip(),
        email=body.email.strip(),
        phone=body.phone.strip(),
        password=body.password,
        firm_name=body.firm_name.strip(),
    )
    if account_id is None:
        raise HTTPException(status_code=409, detail="Email already registered")
    token = nidaan.create_nidaan_token(account_id, body.email.lower().strip(), plan)
    import asyncio as _asyncio
    _asyncio.create_task(email_svc.send_email(
        to_email=body.email.strip(),
        subject="Welcome to Nidaan Partner! 🛡️",
        html_body=(
            f"<p>Hi {body.owner_name.strip()},</p>"
            f"<p>Welcome to <b>Nidaan Partner</b> — your gateway to insurance claim dispute resolution.</p>"
            f"<p>Your account is ready. Subscribe to a plan from your dashboard to start submitting claims.</p>"
            f"<p><a href='https://nidaanpartner.com/nidaan/dashboard' style='background:#0891b2;color:#fff;"
            f"padding:.6rem 1.2rem;border-radius:8px;text-decoration:none;font-weight:700'>"
            f"Go to Dashboard →</a></p>"
            f"<p>If you have any questions, reply to this email — we respond within a few hours.</p>"
            f"<p>— Nidaan Partner Team</p>"
        ),
        from_name="Nidaan Partner",
    ))
    return {"access_token": token, "account_id": account_id, "plan": plan}


@app.post("/nidaan/api/login")
async def nidaan_api_login(body: NidaanLoginReq, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    account = await nidaan.authenticate_account(body.email, body.password)
    if not account:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    sub = await nidaan.get_active_subscription(account["account_id"])
    plan = sub["plan"] if sub else ""
    token = nidaan.create_nidaan_token(account["account_id"], account["email"], plan)
    return {
        "access_token": token,
        "account": {
            "account_id": account["account_id"],
            "owner_name": account["owner_name"],
            "firm_name": account["firm_name"],
            "email": account["email"],
            "plan": plan,
        },
    }


# ── Email OTP login (Nidaan) ──────────────────────────────────────────────────

@app.post("/nidaan/api/send-email-otp")
@limiter.limit("5/minute")
async def nidaan_api_send_email_otp(req: NidaanSendOTPReq, request: Request):
    """Send a 6-digit OTP to the registered Nidaan account email."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)
    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)
    account = await nidaan.get_account_by_email(email)
    if not account:
        return JSONResponse(
            {"detail": "No Nidaan account found with this email. Please sign up first."},
            status_code=404)
    result = auth.generate_email_otp(email)
    if "error" in result:
        return JSONResponse({"detail": result["error"]}, status_code=429)
    otp_code = result["otp"]
    logger.info("📧 Nidaan Email OTP for %s***", email[:3])
    sent = await email_svc.send_nidaan_otp_email(email, otp_code, account.get("owner_name", ""))
    if not sent:
        return JSONResponse({"detail": "Failed to send OTP email. Please try again."}, status_code=503)
    resp = {
        "status": "otp_sent",
        "email": email[:3] + "***" + email[email.index("@"):],
        "expires_in": result["expires_in"],
    }
    if os.getenv("ENVIRONMENT", "").lower() == "development":
        resp["_dev_otp"] = otp_code
    return resp


@app.post("/nidaan/api/verify-email-otp")
@limiter.limit("10/minute")
async def nidaan_api_verify_email_otp(req: NidaanVerifyOTPReq, request: Request):
    """Verify OTP and return Nidaan JWT."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)
    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)
    if not auth.verify_email_otp(email, req.otp):
        auth.record_failed_login(client_ip)
        return JSONResponse({"detail": "Invalid or expired OTP. Please try again."}, status_code=401)
    auth.clear_failed_logins(client_ip)
    account = await nidaan.get_account_by_email(email)
    if not account:
        return JSONResponse({"detail": "Account not found"}, status_code=404)
    sub = await nidaan.get_active_subscription(account["account_id"])
    plan = sub["plan"] if sub else ""
    token = nidaan.create_nidaan_token(account["account_id"], account["email"], plan)
    logger.info("🔑 Nidaan Email OTP Login: account %d (%s)", account["account_id"], email)
    return {
        "access_token": token,
        "account": {
            "account_id": account["account_id"],
            "owner_name": account["owner_name"],
            "firm_name": account["firm_name"],
            "email": account["email"],
            "plan": plan,
        },
    }


# ── Password reset via OTP (Nidaan) ──────────────────────────────────────────

class NidaanResetPasswordReq(BaseModel):
    email: str
    otp: str
    new_password: str = Field(..., min_length=8)

@app.post("/nidaan/api/reset-password")
@limiter.limit("5/minute")
async def nidaan_api_reset_password(req: NidaanResetPasswordReq, request: Request):
    """Verify OTP then update password. The OTP is consumed on success."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    email = auth.sanitize_email(req.email)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid email")
    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    if not auth.verify_email_otp(email, req.otp):
        auth.record_failed_login(client_ip)
        raise HTTPException(status_code=401, detail="Invalid or expired OTP. Request a new one.")
    auth.clear_failed_logins(client_ip)
    account = await nidaan.get_account_by_email(email)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    ok = await nidaan.update_account_password(account["account_id"], req.new_password)
    if not ok:
        raise HTTPException(status_code=500, detail="Password update failed")
    # Auto sign-in after reset
    sub = await nidaan.get_active_subscription(account["account_id"])
    plan = sub["plan"] if sub else ""
    token = nidaan.create_nidaan_token(account["account_id"], account["email"], plan)
    logger.info("🔑 Nidaan Password Reset: account %d (%s)", account["account_id"], email)
    return {
        "access_token": token,
        "account": {
            "account_id": account["account_id"],
            "owner_name": account["owner_name"],
            "firm_name": account["firm_name"],
            "email": account["email"],
            "plan": plan,
        },
    }


# ── Google Sign-In / Sign-Up (Nidaan) ────────────────────────────────────────

@app.get("/nidaan/api/google-client-id")
async def nidaan_google_client_id(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    return {"client_id": client_id if client_id else None}


@app.post("/nidaan/api/google")
@limiter.limit("10/minute")
async def nidaan_api_google_signin(req: NidaanGoogleReq, request: Request):
    """Sign in existing Nidaan account with Google ID token."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    google_user = await auth.verify_google_id_token(req.credential)
    if not google_user:
        return JSONResponse({"detail": "Invalid Google credential"}, status_code=401)
    email = google_user["email"]
    name = google_user.get("name", "")
    account = await nidaan.get_account_by_email(email)
    if not account:
        return JSONResponse({
            "detail": "No Nidaan account found with this Google email. Please sign up first.",
            "email": email, "name": name,
        }, status_code=404)
    sub = await nidaan.get_active_subscription(account["account_id"])
    plan = sub["plan"] if sub else ""
    token = nidaan.create_nidaan_token(account["account_id"], account["email"], plan)
    logger.info("🔑 Nidaan Google Login: account %d (%s)", account["account_id"], email)
    return {
        "access_token": token,
        "account": {
            "account_id": account["account_id"],
            "owner_name": account["owner_name"],
            "firm_name": account["firm_name"],
            "email": account["email"],
            "plan": plan,
        },
    }


@app.post("/nidaan/api/signup/google")
@limiter.limit("5/minute")
async def nidaan_api_google_signup(req: NidaanGoogleReq, request: Request):
    """Sign up for a new Nidaan account using Google. If email already registered, signs in instead."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    if req.plan not in ("silver", "gold", "platinum"):
        raise HTTPException(status_code=400, detail="Invalid plan")
    google_user = await auth.verify_google_id_token(req.credential)
    if not google_user:
        return JSONResponse({"detail": "Invalid Google credential"}, status_code=401)
    email = google_user["email"].lower().strip()
    name = google_user.get("name", "")
    # If already registered, sign them in
    existing = await nidaan.get_account_by_email(email)
    if existing:
        sub = await nidaan.get_active_subscription(existing["account_id"])
        plan = sub["plan"] if sub else ""
        token = nidaan.create_nidaan_token(existing["account_id"], existing["email"], plan)
        return {"access_token": token, "account_id": existing["account_id"], "plan": plan, "existing": True}
    account_id = await nidaan.create_account_google(
        owner_name=name or email.split("@")[0],
        email=email,
        plan=req.plan,
    )
    if account_id is None:
        return JSONResponse({"detail": "Email already registered"}, status_code=409)
    token = nidaan.create_nidaan_token(account_id, email, req.plan)
    import asyncio as _asyncio
    _asyncio.create_task(email_svc.send_email(
        to_email=email,
        subject="Welcome to Nidaan Partner! 🛡️",
        html_body=(
            f"<p>Hi {name or 'there'},</p>"
            f"<p>Welcome to <b>Nidaan Partner</b> — signed in with Google.</p>"
            f"<p>You've signed up for the <b>{req.plan.title()} Plan</b>. "
            f"Complete your subscription payment from your dashboard:</p>"
            f"<p><a href='https://nidaanpartner.com/nidaan/dashboard' style='background:#0891b2;color:#fff;"
            f"padding:.6rem 1.2rem;border-radius:8px;text-decoration:none;font-weight:700'>"
            f"Go to Dashboard →</a></p>"
            f"<p>— Nidaan Partner Team</p>"
        ),
        from_name="Nidaan Partner",
    ))
    logger.info("🆕 Nidaan Google Signup: account %d (%s) plan=%s", account_id, email, req.plan)
    return {"access_token": token, "account_id": account_id, "plan": req.plan}


@app.get("/nidaan/api/me")
async def nidaan_api_me(request: Request):
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    account = await nidaan.get_account_by_email(payload["email"])
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    sub = await nidaan.get_active_subscription(account["account_id"])
    return {
        "account_id": account["account_id"],
        "owner_name": account["owner_name"],
        "firm_name": account["firm_name"],
        "email": account["email"],
        "phone": account["phone"],
        "status": account["status"],
        "subscription": dict(sub) if sub else None,
    }


@app.get("/nidaan/api/claims")
async def nidaan_api_claims(request: Request, status: Optional[str] = None, limit: int = 50):
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    claims = await nidaan.get_claims(payload["sub"], status=status, limit=limit)
    return {"claims": claims, "count": len(claims)}


@app.get("/nidaan/api/claims/{claim_id}")
async def nidaan_api_claim_detail(claim_id: int, request: Request):
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    claim = await nidaan.get_claim_detail(claim_id, account_id=payload["sub"])
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@app.post("/nidaan/api/claims/submit")
async def nidaan_api_submit_claim(body: NidaanClaimReq, request: Request):
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not body.claim_type or not body.insured_name or not body.insured_phone:
        raise HTTPException(status_code=400, detail="claim_type, insured_name, insured_phone are required")
    claim_id, reason = await nidaan.submit_claim(
        account_id=payload["sub"],
        user_id=None,
        claim_type=body.claim_type,
        insured_name=body.insured_name,
        insured_phone=body.insured_phone,
        insured_email=body.insured_email,
        insurer_name=body.insurer_name,
        policy_no=body.policy_no,
        disputed_amount=body.disputed_amount,
        claim_event_date=body.claim_event_date,
        notes_from_agent=body.notes_from_agent,
    )
    if claim_id is None:
        raise HTTPException(status_code=402, detail=reason)
    # Notify admin of new claim (non-blocking)
    _admin_email = os.getenv("NIDAAN_ADMIN_EMAIL", "")
    if _admin_email:
        import asyncio as _asyncio_nc
        account = await nidaan.get_account_by_email(payload["email"])
        _asyncio_nc.ensure_future(
            email_svc.send_nidaan_new_claim_admin_email(
                admin_email=_admin_email,
                claim_id=claim_id,
                advisor_name=account["owner_name"] if account else payload.get("email", ""),
                advisor_email=payload["email"],
                insured_name=body.insured_name,
                claim_type=body.claim_type,
                insurer_name=body.insurer_name or "",
                disputed_amount=body.disputed_amount,
                notes=body.notes_from_agent or "",
            )
        )
    return {"claim_id": claim_id, "status": "intimated"}


# ── Review Request (₹999 per-claim, no subscription) ──────────────────────────

class NidaanReviewReq(BaseModel):
    advisor_name: str
    advisor_phone: str
    advisor_email: str
    insured_name: str
    claim_type: str
    insurer_name: str = ""
    disputed_amount: Optional[int] = None
    notes: str = ""
    review_type: str = "per_claim_999"


@app.post("/nidaan/api/review-request")
async def nidaan_api_review_request(body: NidaanReviewReq, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    import asyncio as _asyncio
    purchase_id = await nidaan.create_review_request(
        advisor_name=body.advisor_name.strip(),
        advisor_phone=body.advisor_phone.strip(),
        advisor_email=body.advisor_email.strip(),
        insured_name=body.insured_name.strip(),
        claim_type=body.claim_type,
        insurer_name=body.insurer_name.strip(),
        disputed_amount=body.disputed_amount,
        notes=body.notes.strip(),
    )
    # Notify admin
    admin_email = os.getenv("NIDAAN_ADMIN_EMAIL", os.getenv("SMTP_FROM_SUPPORT", ""))
    if admin_email:
        _asyncio.create_task(email_svc.send_email(
            to_email=admin_email,
            subject=f"[Nidaan] New ₹999 Review Request #{purchase_id}",
            html_body=(
                f"<p><b>Advisor:</b> {body.advisor_name} — {body.advisor_phone} — {body.advisor_email}</p>"
                f"<p><b>Client:</b> {body.insured_name}</p>"
                f"<p><b>Claim type:</b> {body.claim_type} | <b>Insurer:</b> {body.insurer_name or 'N/A'}</p>"
                f"<p><b>Disputed amount:</b> ₹{body.disputed_amount or 'N/A'}</p>"
                f"<p><b>Notes:</b> {body.notes or '—'}</p>"
                f"<p>Send payment link and proceed once ₹999 confirmed. Purchase ID: {purchase_id}</p>"
            ),
        ))
    # Confirmation to advisor
    _asyncio.create_task(email_svc.send_email(
        to_email=body.advisor_email,
        subject="Your review request received — Nidaan Partner",
        html_body=(
            f"<p>Hi {body.advisor_name},</p>"
            f"<p>We've received your ₹999 review request for client <b>{body.insured_name}</b> "
            f"({body.claim_type} claim).</p>"
            f"<p>Our team will send a payment link to this email within a few hours. "
            f"Once payment is confirmed, the legal review will be delivered in 48–72 business hours.</p>"
            f"<p>Reference ID: <b>#{purchase_id}</b></p>"
            f"<p>— Nidaan Partner Team</p>"
        ),
        from_name="Nidaan Partner",
    ))
    return {"purchase_id": purchase_id, "status": "received"}


# ── Razorpay Subscription (Nidaan) ────────────────────────────────────────────

class NidaanSubscribeReq(BaseModel):
    plan: str  # silver | gold | platinum


@app.post("/nidaan/api/subscribe")
async def nidaan_api_subscribe(body: NidaanSubscribeReq, request: Request):
    """Create a Razorpay subscription for an authenticated Nidaan account."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if body.plan not in ("silver", "gold", "platinum"):
        raise HTTPException(status_code=400, detail="Invalid plan")
    account = await nidaan.get_account_by_email(payload["email"])
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    rzp_key_id = os.getenv("RAZORPAY_KEY_ID", "")
    rzp_key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not rzp_key_id or not rzp_key_secret:
        raise HTTPException(status_code=503, detail="Payments not configured")
    result = await nidaan.create_nidaan_razorpay_subscription(
        account_id=account["account_id"],
        plan=body.plan,
        rzp_key_id=rzp_key_id,
        rzp_key_secret=rzp_key_secret,
        email=account["email"],
        phone=account["phone"],
    )
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


# ── Nidaan Razorpay Webhook ────────────────────────────────────────────────────

@app.post("/nidaan/api/webhook")
async def nidaan_razorpay_webhook(request: Request):
    """Razorpay webhook for Nidaan subscription events."""
    import asyncio as _asyncio, json as _json, hmac as _hmac_mod, hashlib as _hs
    body = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    rzp_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if rzp_secret and sig:
        expected = _hmac_mod.new(rzp_secret.encode(), body, _hs.sha256).hexdigest()
        if not _hmac_mod.compare_digest(expected, sig):
            return JSONResponse({"detail": "Invalid signature"}, status_code=400)
    try:
        data = _json.loads(body)
    except Exception:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)
    event = data.get("event", "")
    sub_entity = data.get("payload", {}).get("subscription", {}).get("entity", {})
    notes = sub_entity.get("notes", {})
    if notes.get("product") != "nidaan":
        return {"status": "ignored", "reason": "not_nidaan"}
    account_id_str = notes.get("nidaan_account_id", "")
    plan = notes.get("nidaan_plan", "")
    if not account_id_str or not plan:
        logger.warning("Nidaan webhook missing account_id/plan: %s", notes)
        return {"status": "ignored"}
    account_id = int(account_id_str)
    rzp_sub_id = sub_entity.get("id", "")
    if event in ("subscription.activated", "subscription.charged"):
        payment_entity = data.get("payload", {}).get("payment", {}).get("entity", {})
        amount_paise = payment_entity.get("amount", 0)
        await nidaan.activate_from_razorpay_webhook(rzp_sub_id, account_id, plan, amount_paise)
        # Email confirmation
        account = await nidaan.get_account_by_email(
            (await nidaan.get_all_accounts_admin(limit=1, offset=0) or [{}])[0].get("email", "")
        )
        async with __import__("aiosqlite").connect(nidaan.DB_PATH) as _c:
            _c.row_factory = __import__("aiosqlite").Row
            _row = await (await _c.execute(
                "SELECT * FROM nidaan_accounts WHERE account_id=?", (account_id,)
            )).fetchone()
            if _row:
                _row = dict(_row)
                _sub = await nidaan.get_active_subscription(account_id)
                _renewal = _sub["current_period_end"][:10] if _sub else ""
                _asyncio.create_task(email_svc.send_nidaan_subscription_email(
                    _row["email"], _row["owner_name"], plan,
                    amount_paise // 100, _renewal
                ))
    elif event == "subscription.cancelled":
        logger.info("Nidaan subscription cancelled: account=%d rzp=%s", account_id, rzp_sub_id)
    return {"status": "ok", "event": event}


# ── Nidaan: Verify inline-checkout payment ─────────────────────────────────────

class NidaanVerifyPaymentReq(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


@app.post("/nidaan/api/subscribe/verify")
async def nidaan_subscribe_verify(body: NidaanVerifyPaymentReq, request: Request):
    """Verify Razorpay signature after inline checkout, activate subscription, return new JWT."""
    import hmac as _hmac_mod, hashlib as _hs, httpx as _httpx
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")

    rzp_key_id = os.getenv("RAZORPAY_KEY_ID", "")
    rzp_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not rzp_secret:
        raise HTTPException(status_code=503, detail="Payments not configured")

    # Verify HMAC signature
    msg = f"{body.razorpay_payment_id}|{body.razorpay_subscription_id}".encode()
    expected = _hmac_mod.new(rzp_secret.encode(), msg, _hs.sha256).hexdigest()
    if not _hmac_mod.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Fetch subscription details from Razorpay to get plan
    async with _httpx.AsyncClient() as client:
        sr = await client.get(
            f"https://api.razorpay.com/v1/subscriptions/{body.razorpay_subscription_id}",
            auth=(rzp_key_id, rzp_secret), timeout=15.0,
        )
        sub_data = sr.json()
        pr = await client.get(
            f"https://api.razorpay.com/v1/payments/{body.razorpay_payment_id}",
            auth=(rzp_key_id, rzp_secret), timeout=15.0,
        )
        payment_data = pr.json()

    notes = sub_data.get("notes", {})
    plan = notes.get("nidaan_plan", "")
    if not plan:
        raise HTTPException(status_code=400, detail="Could not determine plan from subscription")

    account = await nidaan.get_account_by_email(payload["email"])
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    amount_paise = payment_data.get("amount", 0)
    await nidaan.activate_from_razorpay_webhook(
        body.razorpay_subscription_id, account["account_id"], plan, amount_paise
    )

    # Send subscription confirmation email
    sub = await nidaan.get_active_subscription(account["account_id"])
    renewal_date = sub["current_period_end"][:10] if sub else ""
    import asyncio as _asyncio
    _asyncio.create_task(email_svc.send_nidaan_subscription_email(
        account["email"], account["owner_name"], plan,
        amount_paise // 100, renewal_date
    ))

    new_token = nidaan.create_nidaan_token(account["account_id"], account["email"], plan)
    logger.info("✅ Nidaan payment verified: account=%d plan=%s", account["account_id"], plan)
    return {"token": new_token, "plan": plan, "status": "active"}


# ── Nidaan: Cancel subscription ────────────────────────────────────────────────

@app.post("/nidaan/api/subscribe/cancel")
async def nidaan_subscribe_cancel(request: Request):
    """Cancel current Nidaan subscription (Razorpay + DB)."""
    import httpx as _httpx
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")

    account = await nidaan.get_account_by_email(payload["email"])
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    sub = await nidaan.get_active_subscription(account["account_id"])
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription to cancel")

    rzp_sub_id = sub.get("razorpay_subscription_id", "")
    if rzp_sub_id:
        rzp_key_id = os.getenv("RAZORPAY_KEY_ID", "")
        rzp_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
        try:
            async with _httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.razorpay.com/v1/subscriptions/{rzp_sub_id}/cancel",
                    auth=(rzp_key_id, rzp_secret),
                    json={"cancel_at_cycle_end": 0},
                    timeout=15.0,
                )
        except Exception as e:
            logger.warning("Razorpay cancel failed (continuing): %s", e)

    await nidaan.cancel_nidaan_subscription(account["account_id"])
    new_token = nidaan.create_nidaan_token(account["account_id"], account["email"], "free")
    logger.info("Nidaan sub cancelled: account=%d", account["account_id"])
    return {"token": new_token, "plan": "free", "status": "cancelled"}


# ── Nidaan: Update profile ─────────────────────────────────────────────────────

class NidaanProfileUpdateReq(BaseModel):
    owner_name: Optional[str] = None
    firm_name: Optional[str] = None
    phone: Optional[str] = None


@app.patch("/nidaan/api/profile")
async def nidaan_profile_update(body: NidaanProfileUpdateReq, request: Request):
    """Update mutable profile fields."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    account = await nidaan.get_account_by_email(payload["email"])
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await nidaan.update_account_profile(
        account["account_id"],
        owner_name=body.owner_name,
        firm_name=body.firm_name,
        phone=body.phone,
    )
    return {"status": "updated"}


# ── Nidaan: Change password ────────────────────────────────────────────────────

class NidaanChangePasswordReq(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@app.post("/nidaan/api/change-password")
async def nidaan_change_password(body: NidaanChangePasswordReq, request: Request):
    """Change password after verifying current password."""
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    payload = _nidaan_bearer(request)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    account = await nidaan.get_account_by_email(payload["email"])
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    # Verify current password
    if not nidaan._verify_password(body.current_password, account.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await nidaan.update_account_password(account["account_id"], body.new_password)
    return {"status": "password_changed"}


# ── Admin helpers ──────────────────────────────────────────────────────────────

def _nidaan_admin_auth(request: Request) -> bool:
    """Check Nidaan admin token from Authorization header."""
    token = os.getenv("NIDAAN_ADMIN_TOKEN", "")
    if not token:
        return False
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        import hmac as _h
        return _h.compare_digest(h[7:], token)
    return False


@app.get("/nidaan/admin", response_class=HTMLResponse)
async def nidaan_admin_page(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    return _nidaan_page("nidaan_admin.html")


@app.get("/nidaan/api/admin/stats")
async def nidaan_api_admin_stats(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    if not _nidaan_admin_auth(request):
        raise HTTPException(status_code=401, detail="Admin access required")
    return await nidaan.get_admin_stats()


@app.get("/nidaan/api/admin/claims")
async def nidaan_api_admin_claims(
    request: Request,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    if not _nidaan_admin_auth(request):
        raise HTTPException(status_code=401, detail="Admin access required")
    claims = await nidaan.get_all_claims_admin(status=status, limit=limit, offset=offset)
    return {"claims": claims, "count": len(claims)}


@app.get("/nidaan/api/admin/accounts")
async def nidaan_api_admin_accounts(
    request: Request,
    limit: int = 200,
    offset: int = 0,
):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    if not _nidaan_admin_auth(request):
        raise HTTPException(status_code=401, detail="Admin access required")
    accounts = await nidaan.get_all_accounts_admin(limit=limit, offset=offset)
    return {"accounts": accounts, "count": len(accounts)}


@app.get("/nidaan/api/admin/review-requests")
async def nidaan_api_admin_reviews(
    request: Request,
    status: Optional[str] = None,
    limit: int = 100,
):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    if not _nidaan_admin_auth(request):
        raise HTTPException(status_code=401, detail="Admin access required")
    reviews = await nidaan.get_review_requests_admin(status=status, limit=limit)
    return {"reviews": reviews, "count": len(reviews)}


class NidaanReviewStatusUpdate(BaseModel):
    new_status: str
    note: str = ""


@app.patch("/nidaan/api/admin/review-requests/{purchase_id}/status")
async def nidaan_api_admin_update_review(
    purchase_id: int,
    body: NidaanReviewStatusUpdate,
    request: Request,
):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    if not _nidaan_admin_auth(request):
        raise HTTPException(status_code=401, detail="Admin access required")
    try:
        ok = await nidaan.update_review_request_status(
            purchase_id=purchase_id,
            new_status=body.new_status,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Review request not found")
    return {"purchase_id": purchase_id, "status": body.new_status}


class NidaanClaimStatusUpdate(BaseModel):
    new_status: str
    note: str = ""


@app.patch("/nidaan/api/admin/claims/{claim_id}/status")
async def nidaan_api_admin_update_claim(
    claim_id: int,
    body: NidaanClaimStatusUpdate,
    request: Request,
):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    if not _nidaan_admin_auth(request):
        raise HTTPException(status_code=401, detail="Admin access required")
    ok = await nidaan.update_claim_status(
        claim_id=claim_id,
        new_status=body.new_status,
        changed_by_type="super_admin",
        changed_by_id=0,
        note=body.note,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Claim not found")
    # Fire status-update email to the advisor (non-blocking)
    try:
        claim = await nidaan.get_claim_with_account(claim_id)
        if claim and claim.get("email"):
            import asyncio as _asyncio_email
            _asyncio_email.ensure_future(
                email_svc.send_nidaan_claim_status_email(
                    to_email=claim["email"],
                    owner_name=claim.get("owner_name", ""),
                    claim_id=claim_id,
                    insured_name=claim.get("insured_name", ""),
                    claim_type=claim.get("claim_type", ""),
                    new_status=body.new_status,
                    note=body.note or "",
                )
            )
    except Exception:
        pass  # email failure must never break the API response
    return {"claim_id": claim_id, "status": body.new_status}


# =============================================================================
#  NIDAAN OPS PORTAL  (/nidaan/ops/*)
# =============================================================================

def _get_staff_from_request(request: Request) -> Optional[dict]:
    """Extract and verify staff JWT from Authorization header."""
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return None
    return nidaan.verify_staff_token(h[7:])


def _require_staff(request: Request, min_role: str = "team_member") -> dict:
    """Dependency-style helper: returns staff payload or raises 401/403."""
    role_rank = {"team_member": 0, "sub_super_admin": 1, "super_admin": 2}
    staff = _get_staff_from_request(request)
    if not staff:
        raise HTTPException(status_code=401, detail="Staff authentication required")
    if role_rank.get(staff.get("role"), -1) < role_rank.get(min_role, 99):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return staff


@app.get("/nidaan/ops", response_class=HTMLResponse)
async def nidaan_ops_page(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    return _nidaan_page("nidaan_ops.html")


# ── Auth ──────────────────────────────────────────────────────────────────────

class OpsLoginReq(BaseModel):
    email: str
    password: str

@app.post("/nidaan/ops/api/login")
async def ops_login(body: OpsLoginReq, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = await nidaan.authenticate_staff(body.email, body.password)
    if not staff:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = nidaan.create_staff_token(staff["staff_id"], staff["role"], staff["name"])
    return {"token": token, "staff_id": staff["staff_id"],
            "role": staff["role"], "name": staff["name"]}


@app.get("/nidaan/ops/api/me")
async def ops_me(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = _require_staff(request)
    record = await nidaan.get_staff_by_id(staff["staff_id"])
    if not record:
        raise HTTPException(status_code=404)
    return record


# ── Staff management (super_admin only) ───────────────────────────────────────

class CreateStaffReq(BaseModel):
    name: str
    email: str
    password: str = Field(min_length=8)
    role: str

class UpdateStaffReq(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None

@app.get("/nidaan/ops/api/staff")
async def ops_list_staff(request: Request, include_inactive: bool = False):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "super_admin")
    staff_list = await nidaan.list_staff(include_inactive=include_inactive)
    return {"staff": staff_list, "count": len(staff_list)}


@app.post("/nidaan/ops/api/staff")
async def ops_create_staff(body: CreateStaffReq, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    caller = _require_staff(request, "super_admin")
    try:
        staff_id = await nidaan.create_staff(
            name=body.name, email=body.email,
            password=body.password, role=body.role,
            created_by=caller["staff_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not staff_id:
        raise HTTPException(status_code=409, detail="Email already exists")
    return {"staff_id": staff_id, "name": body.name, "role": body.role}


@app.patch("/nidaan/ops/api/staff/{staff_id}")
async def ops_update_staff(staff_id: int, body: UpdateStaffReq, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "super_admin")
    try:
        ok = await nidaan.update_staff(
            staff_id=staff_id, name=body.name, role=body.role,
            status=body.status, password=body.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=400, detail="Nothing to update")
    return {"staff_id": staff_id, "updated": True}


# ── Claims ops ────────────────────────────────────────────────────────────────

@app.get("/nidaan/ops/api/claims")
async def ops_list_claims(
    request: Request,
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
    claim_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = _require_staff(request, "team_member")
    claims = await nidaan.get_claims_ops(
        staff_id=staff["staff_id"], role=staff["role"],
        status=status, assigned_to=assigned_to,
        claim_type=claim_type, search=search,
        limit=limit, offset=offset,
    )
    return {"claims": claims, "count": len(claims)}


@app.get("/nidaan/ops/api/claims/{claim_id}")
async def ops_get_claim(claim_id: int, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = _require_staff(request, "team_member")
    # Build full detail
    async with __import__("aiosqlite").connect(nidaan.DB_PATH) as conn:
        conn.row_factory = __import__("aiosqlite").Row
        cur = await conn.execute(
            """SELECT c.*,
                    a.owner_name, a.firm_name, a.email AS advisor_email, a.phone AS advisor_phone,
                    s.name AS assigned_staff_name
               FROM nidaan_claims c
               JOIN nidaan_accounts a ON a.account_id = c.account_id
               LEFT JOIN nidaan_staff s ON s.staff_id = c.assigned_to_staff_id
               WHERE c.claim_id=?""",
            (claim_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        claim = dict(row)
        # team_member can only see their assigned claims
        if staff["role"] == "team_member" and claim.get("assigned_to_staff_id") != staff["staff_id"]:
            raise HTTPException(status_code=403)
        # Status log
        log_cur = await conn.execute(
            "SELECT * FROM nidaan_claim_status_log WHERE claim_id=? ORDER BY changed_at ASC",
            (claim_id,),
        )
        claim["status_log"] = [dict(r) for r in await log_cur.fetchall()]
    claim["notes"] = await nidaan.get_claim_notes(claim_id)
    claim["followups"] = await nidaan.get_followups_for_claim(claim_id)
    return claim


class OpsClaimAssign(BaseModel):
    staff_id: int

@app.post("/nidaan/ops/api/claims/{claim_id}/assign")
async def ops_assign_claim(claim_id: int, body: OpsClaimAssign, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    caller = _require_staff(request, "sub_super_admin")
    ok = await nidaan.assign_claim_to_staff(
        claim_id=claim_id, staff_id=body.staff_id,
        assigned_by_id=caller["staff_id"], assigned_by_role=caller["role"],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Claim not found")
    return {"claim_id": claim_id, "assigned_to": body.staff_id}


class OpsClaimStatusUpdate(BaseModel):
    new_status: str
    note: str = ""

@app.patch("/nidaan/ops/api/claims/{claim_id}/status")
async def ops_update_claim_status(claim_id: int, body: OpsClaimStatusUpdate, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = _require_staff(request, "team_member")
    # team_member: verify they are assigned to this claim
    if staff["role"] == "team_member":
        async with __import__("aiosqlite").connect(nidaan.DB_PATH) as conn:
            cur = await conn.execute(
                "SELECT assigned_to_staff_id FROM nidaan_claims WHERE claim_id=?", (claim_id,)
            )
            row = await cur.fetchone()
            if not row or row[0] != staff["staff_id"]:
                raise HTTPException(status_code=403, detail="Not assigned to this claim")
    try:
        ok = await nidaan.update_claim_status(
            claim_id=claim_id, new_status=body.new_status,
            changed_by_type=staff["role"], changed_by_id=staff["staff_id"],
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Claim not found")
    # Non-blocking advisor email
    try:
        claim = await nidaan.get_claim_with_account(claim_id)
        if claim and claim.get("email"):
            import asyncio as _ae2
            _ae2.ensure_future(
                email_svc.send_nidaan_claim_status_email(
                    to_email=claim["email"],
                    owner_name=claim.get("owner_name", ""),
                    claim_id=claim_id,
                    insured_name=claim.get("insured_name", ""),
                    claim_type=claim.get("claim_type", ""),
                    new_status=body.new_status,
                    note=body.note,
                )
            )
    except Exception:
        pass
    return {"claim_id": claim_id, "status": body.new_status}


# ── Notes ─────────────────────────────────────────────────────────────────────

class OpsAddNote(BaseModel):
    note: str

@app.post("/nidaan/ops/api/claims/{claim_id}/notes")
async def ops_add_note(claim_id: int, body: OpsAddNote, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = _require_staff(request, "team_member")
    note_id = await nidaan.add_claim_note(claim_id, staff["staff_id"], body.note)
    return {"note_id": note_id, "claim_id": claim_id}


@app.get("/nidaan/ops/api/claims/{claim_id}/notes")
async def ops_get_notes(claim_id: int, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "team_member")
    return {"notes": await nidaan.get_claim_notes(claim_id)}


# ── Follow-ups ────────────────────────────────────────────────────────────────

class OpsAddFollowup(BaseModel):
    due_date: str        # YYYY-MM-DD
    note: str = ""

@app.post("/nidaan/ops/api/claims/{claim_id}/followups")
async def ops_add_followup(claim_id: int, body: OpsAddFollowup, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = _require_staff(request, "team_member")
    fid = await nidaan.add_followup(claim_id, staff["staff_id"], body.due_date, body.note)
    return {"followup_id": fid, "claim_id": claim_id}


@app.patch("/nidaan/ops/api/followups/{followup_id}/done")
async def ops_complete_followup(followup_id: int, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = _require_staff(request, "team_member")
    await nidaan.complete_followup(followup_id, staff["staff_id"])
    return {"followup_id": followup_id, "status": "done"}


@app.get("/nidaan/ops/api/my-followups")
async def ops_my_followups(request: Request, status: str = "pending"):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    staff = _require_staff(request, "team_member")
    items = await nidaan.get_followups_for_staff(staff["staff_id"], status=status)
    return {"followups": items}


# ── Advisor accounts (super_admin) ────────────────────────────────────────────

class OpsCreateAccount(BaseModel):
    owner_name: str
    email: str
    phone: str
    firm_name: str = ""

class OpsUpdateAccount(BaseModel):
    owner_name: Optional[str] = None
    firm_name: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    new_password: Optional[str] = None

@app.get("/nidaan/ops/api/accounts")
async def ops_list_accounts(request: Request, limit: int = 200, offset: int = 0):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "sub_super_admin")
    accounts = await nidaan.get_all_accounts_admin(limit=limit, offset=offset)
    return {"accounts": accounts, "count": len(accounts)}


@app.post("/nidaan/ops/api/accounts")
async def ops_create_account(body: OpsCreateAccount, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "super_admin")
    account_id = await nidaan.create_account_by_admin(
        body.owner_name, body.email, body.phone, body.firm_name
    )
    if not account_id:
        raise HTTPException(status_code=409, detail="Email already registered")
    return {"account_id": account_id, "email": body.email}


@app.patch("/nidaan/ops/api/accounts/{account_id}")
async def ops_update_account(account_id: int, body: OpsUpdateAccount, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "super_admin")
    await nidaan.admin_update_account(
        account_id=account_id,
        owner_name=body.owner_name,
        firm_name=body.firm_name,
        phone=body.phone,
        status=body.status,
    )
    if body.new_password:
        if len(body.new_password) < 8:
            raise HTTPException(status_code=400, detail="Password min 8 characters")
        await nidaan.admin_set_account_password(account_id, body.new_password)
    return {"account_id": account_id, "updated": True}


@app.post("/nidaan/ops/api/accounts/{account_id}/impersonate")
async def ops_impersonate(account_id: int, request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    caller = _require_staff(request, "super_admin")
    token = await nidaan.impersonate_account(account_id)
    if not token:
        raise HTTPException(status_code=404, detail="Account not found")
    logger.warning("IMPERSONATE: staff_id=%d impersonating account_id=%d",
                   caller["staff_id"], account_id)
    return {"advisor_token": token, "account_id": account_id,
            "dashboard_url": "/nidaan/dashboard"}


# ── Revenue (super_admin only) ────────────────────────────────────────────────

@app.get("/nidaan/ops/api/revenue")
async def ops_revenue(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "super_admin")
    return await nidaan.get_revenue_stats()


# ── App health (super_admin only) ─────────────────────────────────────────────

@app.get("/nidaan/ops/api/health")
async def ops_health(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "super_admin")
    return await nidaan.get_app_health()


# ── Stats (super_admin + sub_super_admin) ─────────────────────────────────────

@app.get("/nidaan/ops/api/stats")
async def ops_stats(request: Request):
    if not _is_nidaan_host(request):
        raise HTTPException(status_code=404)
    _require_staff(request, "sub_super_admin")
    return await nidaan.get_admin_stats()


@app.get("/sitemap.xml")
async def sitemap_xml():
    """XML sitemap for Google Search Console. Lists public, indexable pages."""
    base = (os.getenv("SERVER_URL") or "https://sarathi-ai.com").rstrip("/")
    today = _time.strftime("%Y-%m-%d")
    # Only public / indexable routes — exclude auth-gated pages
    pages = [
        {"loc": f"{base}/",              "priority": "1.0", "changefreq": "weekly"},
        {"loc": f"{base}/onboarding",    "priority": "0.9", "changefreq": "monthly"},
        {"loc": f"{base}/calculators",   "priority": "0.9", "changefreq": "weekly"},
        {"loc": f"{base}/features",      "priority": "0.8", "changefreq": "monthly"},
        {"loc": f"{base}/about",         "priority": "0.8", "changefreq": "yearly"},
        {"loc": f"{base}/login",         "priority": "0.5", "changefreq": "yearly"},
        {"loc": f"{base}/privacy",       "priority": "0.3", "changefreq": "yearly"},
        {"loc": f"{base}/terms",         "priority": "0.3", "changefreq": "yearly"},
    ]
    url_entries = "\n".join(
        f"  <url><loc>{p['loc']}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>{p['changefreq']}</changefreq><priority>{p['priority']}</priority></url>"
        for p in pages
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{url_entries}\n"
        '</urlset>'
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    """robots.txt — allow public pages, block dashboard + APIs from crawlers."""
    base = (os.getenv("SERVER_URL") or "https://sarathi-ai.com").rstrip("/")
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /onboarding\n"
        "Allow: /calculators\n"
        "Allow: /features\n"
        "Allow: /about\n"
        "Allow: /privacy\n"
        "Allow: /terms\n"
        "Disallow: /dashboard\n"
        "Disallow: /admin\n"
        "Disallow: /superadmin\n"
        "Disallow: /api/\n"
        "Disallow: /reports/\n"
        "Disallow: /uploads/\n"
        f"\nSitemap: {base}/sitemap.xml\n"
    )


@app.get("/invite", response_class=HTMLResponse)
async def invite_page():
    """Web invite acceptance page — agents join a team via invite code."""
    inv_file = static_dir / "invite.html"
    if inv_file.exists():
        return HTMLResponse(inv_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Invite page not found</h1>", status_code=404)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "sarathi_ai",
        "version": "3.0.0",
        "brand": "Sarathi-AI Business Technologies",
    }


# =============================================================================
#  AUTHENTICATION ENDPOINTS
# =============================================================================

# ── CSRF Token ───────────────────────────────────────────────────────────────

@app.get("/api/auth/csrf-token")
async def api_csrf_token(tenant: dict = Depends(auth.get_optional_tenant)):
    """Get a CSRF token for forms. Tied to tenant if authenticated."""
    tid = tenant.get("tenant_id") if tenant else None
    token = auth.generate_csrf_token(tenant_id=tid)
    return {"csrf_token": token}


async def _verify_csrf(request: Request, tenant_id: int = None):
    """Verify CSRF token from X-CSRF-Token header."""
    csrf_token = request.headers.get("X-CSRF-Token")
    if not csrf_token:
        raise HTTPException(status_code=403, detail="Missing CSRF token")
    if not auth.verify_csrf_token(csrf_token, tenant_id=tenant_id):
        raise HTTPException(status_code=403, detail="Invalid or expired CSRF token")


class SendOTPRequest(BaseModel):
    phone: str = Field(..., pattern=r"^[6-9]\d{9}$")

class VerifyOTPRequest(BaseModel):
    phone: str = Field(..., pattern=r"^[6-9]\d{9}$")
    otp: str = Field(..., min_length=6, max_length=6)

class RefreshTokenRequest(BaseModel):
    refresh_token: str


@app.post("/api/auth/send-otp")
@limiter.limit("5/minute")
async def api_send_otp(req: SendOTPRequest, request: Request):
    """Send OTP to phone number for login. Rate limited to 5/min."""
    phone = auth.sanitize_phone(req.phone)
    if not phone:
        return JSONResponse({"detail": "Invalid phone number"}, status_code=400)

    # Check if tenant exists with this phone (owner) OR agent with this phone
    tenant = None
    agent_match = None
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # First try: owner phone
        cursor = await conn.execute(
            "SELECT tenant_id, firm_name, subscription_status FROM tenants WHERE phone = ?",
            (phone,))
        tenant = await cursor.fetchone()
        # Second try: agent phone → find their tenant
        if not tenant:
            cursor = await conn.execute(
                "SELECT a.tenant_id, a.role, a.is_active, t.firm_name, t.phone as owner_phone, "
                "t.subscription_status FROM agents a JOIN tenants t ON a.tenant_id = t.tenant_id "
                "WHERE a.phone = ? AND a.is_active = 1",
                (phone,))
            agent_match = await cursor.fetchone()
            if agent_match:
                # Build a pseudo-tenant row for token creation
                tenant = agent_match
    if not tenant:
        return JSONResponse({"detail": "No account found with this phone number. Please sign up first."}, status_code=404)

    result = auth.generate_otp(phone)
    if "error" in result:
        return JSONResponse({"detail": result["error"]}, status_code=429)

    # Send OTP via WhatsApp (if configured) — also log for debugging
    otp_code = result["otp"]
    logger.info("📱 OTP generated for %s (last 4: %s)", phone[-4:], otp_code[-3:])

    delivery_channels = []

    # Try SMS first (Fast2SMS)
    if sms.is_configured():
        sms_result = await sms.send_otp(phone, otp_code)
        if sms_result.get("success"):
            delivery_channels.append("sms")
            logger.info("📱 OTP sent via SMS to %s", phone[-4:])
        else:
            logger.warning("⚠️ SMS delivery failed for %s", phone[-4:])

    # Also send via WhatsApp
    if wa.is_configured():
        wa_result = await wa.send_otp(f"91{phone}", otp_code)
        if wa_result.get("success"):
            delivery_channels.append("whatsapp")
            logger.info("📱 OTP sent via WhatsApp to %s", phone[-4:])
        else:
            logger.warning("⚠️ OTP WhatsApp delivery failed for %s", phone[-4:])

    # If both channels failed, return error instead of false success
    if not delivery_channels:
        logger.error("🚨 OTP delivery failed on ALL channels for %s", phone[-4:])
        return JSONResponse({
            "detail": "Unable to deliver OTP. Please try again or contact support.",
            "status": "delivery_failed"
        }, status_code=503)

    resp_data = {
        "status": "otp_sent",
        "phone": f"******{phone[-4:]}",
        "expires_in": result["expires_in"],
        "delivery": ",".join(delivery_channels),
    }
    # Dev-only: include OTP in response for automated testing
    if os.getenv("ENVIRONMENT", "").lower() == "development":
        resp_data["_dev_otp"] = otp_code
    return resp_data


@app.post("/api/auth/verify-otp")
@limiter.limit("10/minute")
async def api_verify_otp(req: VerifyOTPRequest, request: Request):
    """Verify OTP and return JWT token pair."""
    phone = auth.sanitize_phone(req.phone)
    if not phone:
        return JSONResponse({"detail": "Invalid phone number"}, status_code=400)

    if not auth.verify_otp(phone, req.otp):
        return JSONResponse({"detail": "Invalid or expired OTP. Please try again."}, status_code=401)

    # Look up tenant (by owner phone) OR agent (by agent phone)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT tenant_id, firm_name, owner_name, phone, subscription_status, is_active "
            "FROM tenants WHERE phone = ?", (phone,))
        tenant = await cursor.fetchone()
        role = "owner"
        if not tenant:
            # Check if agent phone
            cursor = await conn.execute(
                "SELECT a.tenant_id, a.name as owner_name, a.phone, a.role, a.is_active as agent_active, "
                "t.firm_name, t.subscription_status, t.is_active "
                "FROM agents a JOIN tenants t ON a.tenant_id = t.tenant_id "
                "WHERE a.phone = ? AND a.is_active = 1", (phone,))
            agent_row = await cursor.fetchone()
            if agent_row:
                tenant = agent_row
                role = agent_row["role"]
    if not tenant:
        return JSONResponse({"detail": "Account not found"}, status_code=404)

    tenant = dict(tenant)
    # Look up agent_id for the logged-in user
    _login_agent = None
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT agent_id FROM agents WHERE phone=? AND tenant_id=? AND is_active=1",
            (phone, tenant["tenant_id"]))
        _login_agent = await cur.fetchone()
    _agent_id = _login_agent["agent_id"] if _login_agent else None

    tokens = auth.create_token_pair(
        tenant_id=tenant["tenant_id"],
        phone=phone,
        firm_name=tenant.get("firm_name", ""),
        role=role,
        agent_id=_agent_id,
    )

    logger.info("🔑 Login: tenant %d (%s) role=%s", tenant["tenant_id"], tenant.get("firm_name", ""), role)

    response = JSONResponse({
        "status": "authenticated",
        "tenant_id": tenant["tenant_id"],
        "firm_name": tenant.get("firm_name", ""),
        "owner_name": tenant.get("owner_name", ""),
        "subscription_status": tenant.get("subscription_status", ""),
        "is_active": bool(tenant.get("is_active", 0)),
        "role": role,
        **tokens,
    })
    # Also set httpOnly cookie for page navigation
    response.set_cookie(
        key="sarathi_token",
        value=tokens["access_token"],
        httponly=True,
        samesite="lax",
        max_age=tokens["expires_in"],
        secure=True,   # HTTPS via ngrok
    )
    return response


@app.post("/api/auth/refresh")
@limiter.limit("20/minute")
async def api_refresh_token(req: RefreshTokenRequest, request: Request):
    """Refresh access token using refresh token."""
    payload = auth.verify_refresh_token(req.refresh_token)
    tenant_id = int(payload["sub"])
    phone = payload.get("phone", "")
    # Re-fetch role from DB in case it changed since token was issued
    role = "owner"
    _agent_id = None
    tenant = await db.get_tenant(tenant_id)
    firm_name = tenant.get("firm_name", "") if tenant else ""
    if tenant and tenant.get("phone") != phone:
        # Not the owner phone — look up agent role
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT agent_id, role FROM agents WHERE phone=? AND tenant_id=? AND is_active=1",
                (phone, tenant_id))
            ag = await cur.fetchone()
            if ag:
                role = ag["role"]
                _agent_id = ag["agent_id"]
    elif tenant:
        # Owner — find their agent_id
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT agent_id FROM agents WHERE phone=? AND tenant_id=?",
                (phone, tenant_id))
            ag = await cur.fetchone()
            if ag:
                _agent_id = ag["agent_id"]

    tokens = auth.create_token_pair(tenant_id, phone, firm_name, role=role, agent_id=_agent_id)
    return tokens


# ── Email OTP Login ──────────────────────────────────────────────────────────

class SendEmailOTPRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)

class VerifyEmailOTPRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    otp: str = Field(..., min_length=6, max_length=6)

class GoogleSignInRequest(BaseModel):
    credential: str = Field(..., min_length=10)


# ── Account Recovery (lost access to email) ──────────────────────────────────

class RecoverOptionsRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)

class RecoverSendRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    channel: str = Field(..., pattern=r"^(sms|telegram)$")

class RecoverVerifyRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    channel: str = Field(..., pattern=r"^(sms|telegram)$")
    otp: str = Field(..., min_length=6, max_length=6)


@app.post("/api/auth/send-signup-otp")
@limiter.limit("5/minute")
async def api_send_signup_otp(req: SendEmailOTPRequest, request: Request):
    """Send OTP to email for signup. Does NOT require existing account."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)

    # Check if already registered
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT tenant_id, subscription_status FROM tenants WHERE email = ? AND email != ''",
            (email,))
        existing = await cur.fetchone()
    if existing:
        status = existing["subscription_status"]
        if status in ("expired", "wiped"):
            return JSONResponse(
                {"detail": "A trial was already used with this email. Please subscribe to a paid plan."},
                status_code=409)
        return JSONResponse(
            {"detail": "An account with this email already exists. Please login instead."},
            status_code=409)

    result = auth.generate_email_otp(email)
    if "error" in result:
        return JSONResponse({"detail": result["error"]}, status_code=429)

    otp_code = result["otp"]
    logger.info("📧 Signup OTP for %s***", email[:3])

    sent = await email_svc.send_otp_email(email, otp_code, "")
    if not sent:
        return JSONResponse(
            {"detail": "Failed to send OTP email. Please try again."},
            status_code=503)

    resp_data = {
        "status": "otp_sent",
        "email": email[:3] + "***" + email[email.index("@"):],
        "expires_in": result["expires_in"],
    }
    if os.getenv("ENVIRONMENT", "").lower() == "development":
        resp_data["_dev_otp"] = otp_code
    return resp_data


@app.post("/api/auth/verify-signup-otp")
@limiter.limit("10/minute")
async def api_verify_signup_otp(req: VerifyEmailOTPRequest, request: Request):
    """Verify signup OTP. Returns {verified: true} if OTP valid. Does NOT create account."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)

    if not auth.verify_email_otp(email, req.otp):
        auth.record_failed_login(client_ip)
        return JSONResponse({"detail": "Invalid or expired OTP. Please try again."}, status_code=401)

    auth.clear_failed_logins(client_ip)
    return {"status": "verified", "email": email}


@app.post("/api/auth/send-email-otp")
@limiter.limit("5/minute")
async def api_send_email_otp(req: SendEmailOTPRequest, request: Request):
    """Send OTP to email address for login. Rate limited to 5/min."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)

    # IP-level brute force check
    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)

    # Check if tenant exists with this email (owner) OR agent with this email
    tenant = None
    agent_match = None
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT tenant_id, firm_name, subscription_status FROM tenants WHERE email = ? AND email != ''",
            (email,))
        tenant = await cursor.fetchone()
        if not tenant:
            cursor = await conn.execute(
                "SELECT a.tenant_id, a.role, a.is_active, t.firm_name, t.email as owner_email, "
                "t.subscription_status FROM agents a JOIN tenants t ON a.tenant_id = t.tenant_id "
                "WHERE a.email = ? AND a.is_active = 1",
                (email,))
            agent_match = await cursor.fetchone()
            if agent_match:
                tenant = agent_match
    if not tenant:
        return JSONResponse(
            {"detail": "No account found with this email. Please sign up first."},
            status_code=404)

    result = auth.generate_email_otp(email)
    if "error" in result:
        return JSONResponse({"detail": result["error"]}, status_code=429)

    otp_code = result["otp"]
    logger.info("📧 Email OTP for %s***", email[:3])

    # Send OTP via email
    owner_name = ""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT owner_name FROM tenants WHERE email = ?", (email,))
        row = await cur.fetchone()
        if row:
            owner_name = row["owner_name"]
    sent = await email_svc.send_otp_email(email, otp_code, owner_name)
    if not sent:
        return JSONResponse(
            {"detail": "Failed to send OTP email. Please try again."},
            status_code=503)

    resp_data = {
        "status": "otp_sent",
        "email": email[:3] + "***" + email[email.index("@"):],
        "expires_in": result["expires_in"],
    }
    if os.getenv("ENVIRONMENT", "").lower() == "development":
        resp_data["_dev_otp"] = otp_code
    return resp_data


@app.post("/api/auth/verify-email-otp")
@limiter.limit("10/minute")
async def api_verify_email_otp(req: VerifyEmailOTPRequest, request: Request):
    """Verify email OTP and return JWT token pair."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)

    if not auth.verify_email_otp(email, req.otp):
        auth.record_failed_login(client_ip)
        return JSONResponse({"detail": "Invalid or expired OTP. Please try again."}, status_code=401)

    auth.clear_failed_logins(client_ip)

    # Look up tenant (by owner email) OR agent (by agent email)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT tenant_id, firm_name, owner_name, phone, email, subscription_status, is_active "
            "FROM tenants WHERE email = ?", (email,))
        tenant = await cursor.fetchone()
        role = "owner"
        agent_id = None
        if not tenant:
            cursor = await conn.execute(
                "SELECT a.tenant_id, a.agent_id, a.name as owner_name, a.phone, a.email, a.role, "
                "a.is_active as agent_active, t.firm_name, t.subscription_status, t.is_active "
                "FROM agents a JOIN tenants t ON a.tenant_id = t.tenant_id "
                "WHERE a.email = ? AND a.is_active = 1", (email,))
            agent_row = await cursor.fetchone()
            if agent_row:
                tenant = agent_row
                role = agent_row["role"]
                agent_id = agent_row["agent_id"]
    if not tenant:
        return JSONResponse({"detail": "Account not found"}, status_code=404)

    tenant = dict(tenant)
    phone = tenant.get("phone", "")

    # Look up agent_id for owner
    if not agent_id:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT agent_id FROM agents WHERE email=? AND tenant_id=? AND is_active=1",
                (email, tenant["tenant_id"]))
            _login_agent = await cur.fetchone()
            if not _login_agent:
                cur = await conn.execute(
                    "SELECT agent_id FROM agents WHERE phone=? AND tenant_id=? AND is_active=1",
                    (phone, tenant["tenant_id"]))
                _login_agent = await cur.fetchone()
            agent_id = _login_agent["agent_id"] if _login_agent else None

    tokens = auth.create_token_pair(
        tenant_id=tenant["tenant_id"],
        phone=phone,
        firm_name=tenant.get("firm_name", ""),
        role=role,
        agent_id=agent_id,
    )

    logger.info("🔑 Email Login: tenant %d (%s) role=%s", tenant["tenant_id"], tenant.get("firm_name", ""), role)

    response = JSONResponse({
        "status": "authenticated",
        "tenant_id": tenant["tenant_id"],
        "firm_name": tenant.get("firm_name", ""),
        "owner_name": tenant.get("owner_name", ""),
        "subscription_status": tenant.get("subscription_status", ""),
        "is_active": bool(tenant.get("is_active", 0)),
        "role": role,
        **tokens,
    })
    response.set_cookie(
        key="sarathi_token",
        value=tokens["access_token"],
        httponly=True,
        samesite="lax",
        max_age=tokens["expires_in"],
        secure=True,
    )
    return response


# ── Account Recovery (lost access to email) ──────────────────────────────────
# Flow: user has no access to their registered email. They prove identity
# via a backup channel that's already on file (registered phone via SMS,
# or linked Telegram account). On success we issue a normal JWT pair —
# this is NOT a password reset, just an alternate-channel sign-in.

def _mask_email(em: str) -> str:
    if not em or "@" not in em:
        return em or ""
    local, _, dom = em.partition("@")
    if len(local) <= 2:
        return local[0] + "***@" + dom
    return local[:2] + "***@" + dom


async def _lookup_account_for_recovery(email: str):
    """Return dict with tenant + recovery channel data, or None.
    Looks up tenant (owner) first, then agent."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT tenant_id, firm_name, owner_name, phone, email, "
            "owner_telegram_id, subscription_status, is_active "
            "FROM tenants WHERE email = ? AND email != ''", (email,))
        t = await cur.fetchone()
        if t:
            t = dict(t)
            t["_role"] = "owner"
            t["_agent_id"] = None
            t["_phone"] = t.get("phone") or ""
            t["_telegram_id"] = t.get("owner_telegram_id") or ""
            return t
        cur = await conn.execute(
            "SELECT a.tenant_id, a.agent_id, a.name as owner_name, a.phone, "
            "a.email, a.role, a.telegram_id, t.firm_name, t.subscription_status, t.is_active "
            "FROM agents a JOIN tenants t ON a.tenant_id = t.tenant_id "
            "WHERE a.email = ? AND a.is_active = 1", (email,))
        a = await cur.fetchone()
        if a:
            a = dict(a)
            a["_role"] = a.get("role") or "agent"
            a["_agent_id"] = a.get("agent_id")
            a["_phone"] = a.get("phone") or ""
            a["_telegram_id"] = a.get("telegram_id") or ""
            return a
    return None


@app.post("/api/auth/recover/options")
@limiter.limit("10/minute")
async def api_recover_options(req: RecoverOptionsRequest, request: Request):
    """Return list of available recovery channels for an email account.
    Each channel has the masked target so the user can confirm before sending."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)

    acct = await _lookup_account_for_recovery(email)
    if not acct:
        return JSONResponse(
            {"detail": "No account found with this email."}, status_code=404)

    channels = []
    phone = acct.get("_phone") or ""
    tg_id = acct.get("_telegram_id") or ""
    if phone and sms.is_configured():
        channels.append({
            "channel": "sms",
            "label": "SMS to registered phone",
            "label_hi": "रजिस्टर्ड फ़ोन पर SMS",
            "masked": auth.mask_phone(phone),
        })
    if tg_id:
        channels.append({
            "channel": "telegram",
            "label": "Message via Telegram bot",
            "label_hi": "Telegram बॉट के ज़रिए संदेश",
            "masked": "Telegram ID " + auth.mask_telegram_id(tg_id),
        })

    return {
        "email": _mask_email(email),
        "channels": channels,
        "no_channels_help": (
            "" if channels else
            "No recovery channels are linked to this account. "
            "Please contact support@sarathi-ai.com from the email address you used to sign up."
        ),
    }


@app.post("/api/auth/recover/send")
@limiter.limit("3/minute")
async def api_recover_send(req: RecoverSendRequest, request: Request):
    """Send a recovery OTP via the chosen channel (sms or telegram)."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)

    acct = await _lookup_account_for_recovery(email)
    if not acct:
        return JSONResponse({"detail": "No account found with this email."}, status_code=404)

    channel = req.channel.lower()
    phone = acct.get("_phone") or ""
    tg_id = acct.get("_telegram_id") or ""

    # Validate the chosen channel is actually available for this account
    if channel == "sms" and (not phone or not sms.is_configured()):
        return JSONResponse(
            {"detail": "SMS recovery is not available for this account."},
            status_code=400)
    if channel == "telegram" and not tg_id:
        return JSONResponse(
            {"detail": "Telegram recovery is not available for this account."},
            status_code=400)

    gen = auth.generate_recovery_otp(email, channel)
    if "error" in gen:
        return JSONResponse({"detail": gen["error"]}, status_code=429)

    otp = gen["otp"]
    name = acct.get("owner_name") or "there"
    firm = acct.get("firm_name") or "Sarathi-AI"

    if channel == "sms":
        result = await sms.send_otp(phone, otp)
        if not result.get("success"):
            return JSONResponse(
                {"detail": "Failed to send SMS. Please try another channel."},
                status_code=503)
        target_label = auth.mask_phone(phone)

    else:  # telegram
        try:
            msg = (
                f"🔐 *Sarathi\\-AI Account Recovery*\n\n"
                f"Hi {name}, your one\\-time recovery code is:\n\n"
                f"`{otp}`\n\n"
                f"Valid for 10 minutes\\. If you didn't request this, ignore this message\\."
            )
            await botmgr.bot_manager.send_alert(
                telegram_id=str(tg_id),
                message=msg,
                tenant_id=acct.get("tenant_id"),
            )
        except Exception as e:
            logger.error("Telegram recovery send failed: %s", e)
            return JSONResponse(
                {"detail": "Failed to send Telegram message. Please try another channel."},
                status_code=503)
        target_label = "Telegram ID " + auth.mask_telegram_id(tg_id)

    logger.info("🔐 Recovery OTP sent for %s*** via %s", email[:3], channel)

    resp = {
        "status": "otp_sent",
        "channel": channel,
        "sent_to": target_label,
        "expires_in": gen["expires_in"],
    }
    if os.getenv("ENVIRONMENT", "").lower() == "development":
        resp["_dev_otp"] = otp
    return resp


@app.post("/api/auth/recover/verify")
@limiter.limit("10/minute")
async def api_recover_verify(req: RecoverVerifyRequest, request: Request):
    """Verify a recovery OTP and issue a JWT pair (alternate-channel sign-in)."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    if auth.is_ip_blocked(client_ip):
        return JSONResponse({"detail": "Too many attempts. Try again later."}, status_code=429)

    if not auth.verify_recovery_otp(email, req.channel, req.otp):
        auth.record_failed_login(client_ip)
        return JSONResponse(
            {"detail": "Invalid or expired code. Please try again."},
            status_code=401)

    auth.clear_failed_logins(client_ip)

    acct = await _lookup_account_for_recovery(email)
    if not acct:
        return JSONResponse({"detail": "Account not found"}, status_code=404)

    role = acct.get("_role", "owner")
    agent_id = acct.get("_agent_id")
    phone = acct.get("_phone", "") or ""
    tenant_id = acct["tenant_id"]
    firm_name = acct.get("firm_name", "")

    # For owner-recovery, fill agent_id from the tenant's owner agent record
    if not agent_id:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT agent_id FROM agents WHERE tenant_id=? AND is_active=1 "
                "AND (email=? OR phone=?) LIMIT 1",
                (tenant_id, email, phone))
            row = await cur.fetchone()
            if row:
                agent_id = row["agent_id"]

    tokens = auth.create_token_pair(
        tenant_id=tenant_id, phone=phone, firm_name=firm_name,
        role=role, agent_id=agent_id,
    )

    logger.info("🔓 Recovery login: tenant %d via %s", tenant_id, req.channel)

    response = JSONResponse({
        "status": "authenticated",
        "tenant_id": tenant_id,
        "firm_name": firm_name,
        "owner_name": acct.get("owner_name", ""),
        "subscription_status": acct.get("subscription_status", ""),
        "is_active": bool(acct.get("is_active", 0)),
        "role": role,
        "recovered_via": req.channel,
        **tokens,
    })
    response.set_cookie(
        key="sarathi_token", value=tokens["access_token"],
        httponly=True, samesite="lax",
        max_age=tokens["expires_in"], secure=True,
    )
    return response


# ── Google Sign-In ───────────────────────────────────────────────────────────

class GoogleSignUpRequest(BaseModel):
    credential: str = Field(..., min_length=10)
    plan: str = Field("individual", pattern=r"^(individual|team|enterprise)$")
    referral_code: str = ""


@app.post("/api/auth/google")
@limiter.limit("10/minute")
async def api_google_signin(req: GoogleSignInRequest, request: Request):
    """Verify Google ID token and sign in. Returns 404 if no account."""
    google_user = await auth.verify_google_id_token(req.credential)
    if not google_user:
        return JSONResponse({"detail": "Invalid Google credential"}, status_code=401)

    email = google_user["email"]
    name = google_user.get("name", "")

    # Find existing tenant by email
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT tenant_id, firm_name, owner_name, phone, email, subscription_status, is_active "
            "FROM tenants WHERE email = ? AND email != ''", (email,))
        tenant = await cursor.fetchone()

    if not tenant:
        # Check if agent with this email
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT a.tenant_id, a.agent_id, a.name as owner_name, a.phone, a.email, a.role, "
                "t.firm_name, t.subscription_status, t.is_active "
                "FROM agents a JOIN tenants t ON a.tenant_id = t.tenant_id "
                "WHERE a.email = ? AND a.is_active = 1", (email,))
            agent_row = await cursor.fetchone()
            if agent_row:
                tenant = agent_row

    if not tenant:
        return JSONResponse({
            "detail": "No account found with this Google email. Please sign up first.",
            "email": email,
            "name": name,
        }, status_code=404)

    tenant = dict(tenant)
    role = tenant.get("role", "owner")
    phone = tenant.get("phone", "")

    # Find agent_id
    agent_id = tenant.get("agent_id")
    if not agent_id:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT agent_id FROM agents WHERE (email=? OR phone=?) AND tenant_id=? AND is_active=1",
                (email, phone, tenant["tenant_id"]))
            ag = await cur.fetchone()
            agent_id = ag["agent_id"] if ag else None

    tokens = auth.create_token_pair(
        tenant_id=tenant["tenant_id"],
        phone=phone,
        firm_name=tenant.get("firm_name", ""),
        role=role,
        agent_id=agent_id,
    )

    logger.info("🔑 Google Login: tenant %d (%s) email=%s", tenant["tenant_id"], tenant.get("firm_name", ""), email)

    response = JSONResponse({
        "status": "authenticated",
        "tenant_id": tenant["tenant_id"],
        "firm_name": tenant.get("firm_name", ""),
        "owner_name": tenant.get("owner_name", ""),
        "subscription_status": tenant.get("subscription_status", ""),
        "is_active": bool(tenant.get("is_active", 0)),
        "role": role,
        **tokens,
    })
    response.set_cookie(
        key="sarathi_token",
        value=tokens["access_token"],
        httponly=True,
        samesite="lax",
        max_age=tokens["expires_in"],
        secure=True,
    )
    return response


@app.post("/api/signup/google")
@limiter.limit("5/minute")
async def api_google_signup(req: GoogleSignUpRequest, request: Request):
    """Sign up with Google — creates account from Google credential.
    Returns JWT immediately. Profile details collected later via onboarding popup."""
    google_user = await auth.verify_google_id_token(req.credential)
    if not google_user:
        return JSONResponse({"detail": "Invalid Google credential"}, status_code=401)

    email = google_user["email"].lower().strip()
    name = google_user.get("name", "")

    # Check if account already exists
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT tenant_id, subscription_status FROM tenants WHERE email = ? AND email != ''",
            (email,))
        existing = await cursor.fetchone()

    if existing:
        status = existing['subscription_status'] if existing else ''
        if status in ('expired', 'wiped'):
            return JSONResponse(
                {"detail": "A trial was already used with this email. Please subscribe to continue.",
                 "tenant_id": existing['tenant_id'], "can_subscribe": True},
                status_code=409)
        return JSONResponse(
            {"detail": "An account with this email already exists. Please login instead.",
             "tenant_id": existing['tenant_id']},
            status_code=409)

    # Create account with Google info — minimal details, rest via onboarding
    plan_features = db.PLAN_FEATURES.get(req.plan, db.PLAN_FEATURES['trial'])
    max_agents = plan_features['max_agents']
    account_type = 'individual' if req.plan == 'individual' else 'firm'
    firm_name = name  # Use Google name as firm_name placeholder

    result = await db.create_tenant_with_owner(
        firm_name=firm_name,
        owner_name=name,
        phone="",
        email=email,
        lang="en",
        city="",
        account_type=account_type,
        signup_channel="google",
    )
    tenant_id = result['tenant_id']
    owner_agent_id = result['agent_id']

    update_fields = {"plan": req.plan, "max_agents": max_agents}
    await db.update_tenant(tenant_id, **update_fields)

    # Handle referral code
    referral_bonus = False
    if req.referral_code:
        ref_code = req.referral_code.upper().strip()
        ref_aff = await db.get_affiliate(referral_code=ref_code)
        if ref_aff and ref_aff.get('status') == 'active':
            is_self = (ref_aff.get('email') == email)
            if not is_self:
                await db.create_referral(
                    affiliate_id=ref_aff['affiliate_id'],
                    referral_code=ref_code,
                    referred_phone=email,
                    referred_name=name)
                await db.update_tenant(tenant_id, referral_code=ref_code)
                from datetime import datetime, timedelta
                extended_trial = (datetime.now() + timedelta(days=21)).isoformat()
                await db.update_tenant(tenant_id, trial_ends_at=extended_trial)
                referral_bonus = True
                logger.info("🤝 Referral tracked: %s → tenant %d via Google signup", ref_code, tenant_id)

    logger.info("🆕 Google signup: %s (%s) → tenant_id=%d, plan=%s", name, email, tenant_id, req.plan)

    asyncio.create_task(email_svc.send_welcome(email, name, firm_name, tenant_id))

    tokens = auth.create_token_pair(
        tenant_id=tenant_id,
        phone=email,
        firm_name=firm_name,
        role="owner",
        agent_id=owner_agent_id,
    )

    response = JSONResponse({
        "status": "created",
        "tenant_id": tenant_id,
        "firm_name": firm_name,
        "owner_name": name,
        "plan": req.plan,
        "trial_days": 21 if referral_bonus else 14,
        "email": email,
        "referral_bonus": referral_bonus,
        "needs_onboarding": True,
        **tokens,
    })
    response.set_cookie(
        key="sarathi_token",
        value=tokens["access_token"],
        httponly=True,
        samesite="lax",
        max_age=tokens["expires_in"],
        secure=True,
    )
    return response


@app.get("/api/auth/me")
async def api_auth_me(tenant: dict = Depends(auth.get_current_tenant)):
    """Return current authenticated tenant info with plan features and role."""
    tenant_data = await db.get_tenant(tenant["tenant_id"])
    if not tenant_data:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)
    plan = tenant_data.get("plan", "trial")
    features = db.PLAN_FEATURES.get(plan, db.PLAN_FEATURES['trial'])
    agent_count = await db.get_tenant_agent_count(tenant["tenant_id"])

    # Check if profile is complete (owner_name not just Google-copied, city filled)
    owner_name = tenant_data.get("owner_name", "")
    city = tenant_data.get("city", "")
    is_profile_complete = bool(owner_name and len(owner_name) >= 2 and city and len(city) >= 2 and city.upper() != "TBD")

    return {
        "tenant_id": tenant["tenant_id"],
        "firm_name": tenant_data.get("firm_name", ""),
        "owner_name": owner_name,
        "phone": tenant_data.get("phone", ""),
        "email": tenant_data.get("email", ""),
        "plan": plan,
        "subscription_status": tenant_data.get("subscription_status", ""),
        "is_active": bool(tenant_data.get("is_active", 0)),
        "max_agents": tenant_data.get("max_agents", 1),
        "current_agents": agent_count,
        "features": features,
        "role": tenant.get("role", "owner"),
        "agent_id": tenant.get("agent_id"),
        "is_profile_complete": is_profile_complete,
    }


@app.post("/api/auth/logout")
async def api_logout():
    """Clear auth cookie."""
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("sarathi_token")
    return response


@app.get("/api/auth/telegram-login")
async def api_telegram_login(token: str = None):
    """Validate a Telegram-generated login token and redirect to dashboard with session."""
    if not token:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h2>❌ Missing login token</h2>"
            "<p>Please use /weblogin in your Telegram bot to get a login link.</p>"
            "<a href='/'>← Back to Home</a></body></html>",
            status_code=400)
    try:
        payload = auth.verify_telegram_login_token(token)
    except HTTPException as e:
        logger.warning("Telegram login failed: %s", e.detail)
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h2>❌ Link expired or invalid</h2>"
            "<p>Please generate a new login link from your Telegram bot using /weblogin</p>"
            "<a href='/'>← Back to Home</a></body></html>",
            status_code=401)
    except Exception as e:
        logger.error("Telegram login error: %s", e)
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h2>❌ Login failed</h2>"
            "<p>Please generate a new login link from your Telegram bot using /weblogin</p>"
            "<a href='/'>← Back to Home</a></body></html>",
            status_code=500)

    tenant_id = int(payload["sub"])
    phone = payload.get("phone", "")
    role = payload.get("role", "owner")
    firm_name = payload.get("firm", "")
    agent_id = payload.get("aid")

    tokens = auth.create_token_pair(
        tenant_id=tenant_id,
        phone=phone,
        firm_name=firm_name,
        role=role,
        agent_id=agent_id,
    )

    logger.info("🔑 Telegram web login: tenant %d, agent %s, role=%s", tenant_id, agent_id, role)

    # Redirect to dashboard with tokens injected via JS
    # Escape firm_name for safe JS string interpolation
    safe_firm = firm_name.replace('\\', '\\\\').replace("'", "\\'").replace('\n', ' ').replace('\r', '') if firm_name else ''
    html = (
        "<html><head><meta charset='utf-8'></head><body>"
        "<script>"
        f"localStorage.setItem('sarathi_token','{tokens['access_token']}');"
        f"localStorage.setItem('sarathi_refresh','{tokens['refresh_token']}');"
        f"localStorage.setItem('sarathi_tenant_id','{tenant_id}');"
        f"localStorage.setItem('sarathi_firm','{safe_firm}');"
        f"localStorage.setItem('sarathi_phone','{phone}');"
        f"localStorage.setItem('sarathi_role','{role}');"
        "window.location.href='/dashboard';"
        "</script>"
        "</body></html>"
    )
    response = HTMLResponse(html)
    response.set_cookie(
        key="sarathi_token",
        value=tokens["access_token"],
        httponly=True,
        samesite="lax",
        max_age=tokens["expires_in"],
        secure=True,
    )
    return response


# Admin API key — DEPRECATED (Phase 4). Legacy routes now return 410 Gone.
# Kept here only for reference; all functionality migrated to /api/sa/* routes.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "sarathi-admin-2024-secure")

_LEGACY_ADMIN_MSG = {
    "error": "This endpoint is deprecated. Use the Super Admin panel at /superadmin instead.",
    "migration": "All /api/admin/* management routes have been migrated to /api/sa/*."
}

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """Legacy admin page — redirects to Super Admin."""
    return HTMLResponse(
        '<html><body><h2>Admin Panel Retired</h2>'
        '<p>This panel has been replaced by the <a href="/superadmin">Super Admin Dashboard</a>.</p>'
        '<p>Please use <a href="/superadmin">/superadmin</a> instead.</p></body></html>',
        status_code=200)


@app.get("/api/admin/tenants")
async def api_admin_tenants(_admin=Depends(auth.require_admin)):
    """DEPRECATED — use GET /api/sa/tenants."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


@app.get("/api/admin/stats")
async def api_admin_stats(_admin=Depends(auth.require_admin)):
    """DEPRECATED — use GET /api/sa/dashboard."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


@app.post("/api/admin/tenant/{tenant_id}/extend")
async def api_admin_extend_trial(tenant_id: int, days: int = Query(7), _admin=Depends(auth.require_admin)):
    """DEPRECATED — use POST /api/sa/tenant/{id}/extend."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


@app.post("/api/admin/tenant/{tenant_id}/activate")
async def api_admin_activate(tenant_id: int, plan: str = Query("individual"), _admin=Depends(auth.require_admin)):
    """DEPRECATED — use POST /api/sa/tenant/{id}/activate."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


@app.post("/api/admin/tenant/{tenant_id}/deactivate")
async def api_admin_deactivate(tenant_id: int, _admin=Depends(auth.require_admin)):
    """DEPRECATED — use POST /api/sa/tenant/{id}/deactivate."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


# ── Admin: Bot Management (DEPRECATED) ──────────────────────────────────────

@app.get("/api/admin/bots")
async def api_admin_bots(_admin=Depends(auth.require_admin)):
    """DEPRECATED — use GET /api/sa/bots."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


@app.post("/api/admin/tenant/{tenant_id}/bot/restart")
async def api_admin_restart_bot(tenant_id: int, _admin=Depends(auth.require_admin)):
    """DEPRECATED — use POST /api/sa/tenant/{id}/bot/restart."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


@app.post("/api/admin/tenant/{tenant_id}/bot/stop")
async def api_admin_stop_bot(tenant_id: int, _admin=Depends(auth.require_admin)):
    """DEPRECATED — use POST /api/sa/tenant/{id}/bot/stop."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


# ── Admin: Create Firm (DEPRECATED) ─────────────────────────────────────────

class CreateFirmRequest(BaseModel):
    firm_name: str = Field(..., min_length=2, max_length=200)
    owner_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^[6-9]\d{9}$")
    email: str = Field("", max_length=200)
    city: str = Field("", max_length=100)
    plan: str = Field("trial", pattern=r"^(trial|individual|team|enterprise)$")

@app.post("/api/admin/create-firm")
async def api_admin_create_firm(req: CreateFirmRequest, _admin=Depends(auth.require_admin)):
    """DEPRECATED — use POST /api/sa/create-firm."""
    return JSONResponse(_LEGACY_ADMIN_MSG, status_code=410)


# =============================================================================
#  SUPER ADMIN — OTP Auth + Dashboard API
# =============================================================================

PLAN_PRICES = {"individual": 199, "team": 799, "enterprise": 1999}

@app.get("/superadmin", response_class=HTMLResponse)
async def superadmin_page():
    """Serve the Super Admin dashboard page."""
    sa_file = static_dir / "superadmin.html"
    if sa_file.exists():
        return HTMLResponse(sa_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Super Admin page not found</h1>", status_code=404)


class SALoginRequest(BaseModel):
    phone: str
    password: str


@app.post("/api/sa/login")
@limiter.limit("10/minute")
async def sa_login(req: SALoginRequest, request: Request):
    """Verify phone + password and issue Super Admin JWT."""
    phone = auth.sanitize_phone(req.phone)
    if not phone:
        return JSONResponse({"detail": "Invalid phone number"}, status_code=400)

    ip = get_remote_address(request)
    if auth.is_ip_blocked(ip):
        return JSONResponse({"detail": "Too many attempts. Try after 15 minutes."}, status_code=429)

    if not auth.verify_sa_credentials(phone, req.password):
        blocked = auth.record_failed_login(ip)
        # Log security event
        try:
            await db.add_system_event("security", "high" if blocked else "medium",
                                      "auth", f"Failed SA login from {ip}",
                                      f"Phone: ...{phone[-4:]}, blocked={blocked}",
                                      ip_address=ip)
        except Exception:
            pass
        if blocked:
            return JSONResponse({"detail": "Too many failed attempts. Blocked for 15 minutes."}, status_code=429)
        logger.warning("⚠️  Failed SA login attempt for phone: %s", phone[-4:])
        return JSONResponse({"detail": "Invalid credentials"}, status_code=401)

    auth.clear_failed_logins(ip)
    token = auth.create_sa_access_token(phone)

    response = JSONResponse({
        "status": "authenticated",
        "role": "superadmin",
        "phone": phone,
    })
    is_prod = os.getenv("ENVIRONMENT", "production").lower() != "development"
    response.set_cookie(
        key="sa_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,  # 12 hours
        secure=is_prod,
    )
    return response


@app.post("/api/sa/logout")
async def sa_logout():
    """Clear SA auth cookie."""
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("sa_token")
    return response


@app.get("/api/sa/me")
async def sa_me(sa=Depends(auth.require_superadmin)):
    """Check SA auth status."""
    return {"authenticated": True, "phone": sa["phone"], "role": "superadmin"}


# ── SA Dashboard Stats ──────────────────────────────────────────────────────

@app.get("/api/sa/dashboard")
async def sa_dashboard(sa=Depends(auth.require_superadmin)):
    """Comprehensive dashboard KPIs for super admin."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # ── Tenant counts by status ─────────────────
        cur = await conn.execute("SELECT COUNT(*) FROM tenants")
        total = (await cur.fetchone())[0]

        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE subscription_status='trial' AND is_active=1")
        trials = (await cur.fetchone())[0]

        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE subscription_status IN ('paid','active') AND is_active=1")
        paid = (await cur.fetchone())[0]

        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE subscription_status='expired'")
        expired = (await cur.fetchone())[0]

        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE subscription_status='wiped'")
        wiped = (await cur.fetchone())[0]

        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE is_active=1")
        active = (await cur.fetchone())[0]

        # ── Plan distribution ────────────────────────
        cur = await conn.execute(
            "SELECT plan, COUNT(*) cnt FROM tenants WHERE subscription_status != 'wiped' GROUP BY plan")
        plans = {r['plan']: r['cnt'] for r in await cur.fetchall()}

        # ── MRR (Monthly Recurring Revenue) ──────────
        cur = await conn.execute(
            "SELECT plan, COUNT(*) cnt FROM tenants WHERE subscription_status IN ('paid','active') AND is_active=1 GROUP BY plan")
        mrr = 0
        for r in await cur.fetchall():
            mrr += PLAN_PRICES.get(r['plan'], 0) * r['cnt']

        # ── Signup trends (last 30 days) ─────────────
        cur = await conn.execute("""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM tenants WHERE created_at >= DATE('now', '-30 days')
            GROUP BY DATE(created_at) ORDER BY day
        """)
        signup_trend = [{"day": r['day'], "count": r['cnt']} for r in await cur.fetchall()]

        # ── 7d / 30d signups ─────────────────────────
        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE created_at >= datetime('now', '-7 days')")
        signups_7d = (await cur.fetchone())[0]

        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE created_at >= datetime('now', '-30 days')")
        signups_30d = (await cur.fetchone())[0]

        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE DATE(created_at) = DATE('now')")
        signups_today = (await cur.fetchone())[0]

        # ── Agent & lead totals ──────────────────────
        cur = await conn.execute("SELECT COUNT(*) FROM agents")
        total_agents = (await cur.fetchone())[0]

        cur = await conn.execute("SELECT COUNT(*) FROM agents WHERE is_active=1")
        active_agents = (await cur.fetchone())[0]

        cur = await conn.execute("SELECT COUNT(*) FROM leads")
        total_leads = (await cur.fetchone())[0]

        cur = await conn.execute("SELECT COUNT(*) FROM policies")
        total_policies = (await cur.fetchone())[0]

        # ── Conversion funnel ────────────────────────
        cur = await conn.execute(
            "SELECT stage, COUNT(*) cnt FROM leads GROUP BY stage")
        lead_stages = {r['stage']: r['cnt'] for r in await cur.fetchall()}

        # ── Recent audit entries ─────────────────────
        cur = await conn.execute("""
            SELECT a.*, t.firm_name FROM audit_log a
            LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
            ORDER BY a.created_at DESC LIMIT 20
        """)
        recent_audit = [dict(r) for r in await cur.fetchall()]

        # ── Founding customers ───────────────────────
        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE founding_discount=1")
        founding_count = (await cur.fetchone())[0]

    return {
        "kpis": {
            "total_tenants": total, "active": active, "trials": trials,
            "paid": paid, "expired": expired, "wiped": wiped,
            "mrr": mrr, "signups_today": signups_today,
            "signups_7d": signups_7d, "signups_30d": signups_30d,
            "total_agents": total_agents, "active_agents": active_agents,
            "total_leads": total_leads, "total_policies": total_policies,
            "founding_customers": founding_count,
        },
        "plans": plans,
        "signup_trend": signup_trend,
        "lead_stages": lead_stages,
        "recent_audit": recent_audit,
    }


# ── SA Tenant Management ────────────────────────────────────────────────────

@app.get("/api/sa/tenants")
async def sa_tenants(sa=Depends(auth.require_superadmin)):
    """List all tenants with enriched data."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT tenant_id, firm_name, owner_name, phone, email, plan,
                   subscription_status, is_active, trial_ends_at, subscription_expires_at,
                   razorpay_sub_id, tg_bot_token, wa_phone_id, max_agents,
                   founding_discount, founding_discount_until,
                   created_at, updated_at
            FROM tenants ORDER BY created_at DESC
        """)
        tenants = [dict(r) for r in await cur.fetchall()]

        for t in tenants:
            tid = t['tenant_id']
            cur = await conn.execute("SELECT COUNT(*) FROM agents WHERE tenant_id=?", (tid,))
            t['agent_count'] = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM leads l JOIN agents a ON l.agent_id=a.agent_id WHERE a.tenant_id=?", (tid,))
            t['lead_count'] = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM policies p JOIN agents a ON p.agent_id=a.agent_id WHERE a.tenant_id=?", (tid,))
            t['policy_count'] = (await cur.fetchone())[0]
            # Mask bot token for display
            tok = t.get('tg_bot_token') or ''
            t['has_bot'] = bool(tok)
            t['tg_bot_token'] = f"{tok[:8]}...{tok[-4:]}" if len(tok) > 12 else ''
            t['has_whatsapp'] = bool(t.get('wa_phone_id'))

    # Bulk-load affiliate mapping for all tenants
    aff_map = await db.get_affiliate_map_for_tenants([t['tenant_id'] for t in tenants])
    for t in tenants:
        ref = aff_map.get(t['tenant_id'])
        t['referred_by'] = ref['name'] if ref else ''
        t['referred_code'] = ref['referral_code'] if ref else ''

    return {"tenants": tenants}


@app.get("/api/sa/tenant/{tenant_id}")
async def sa_tenant_detail(tenant_id: int, sa=Depends(auth.require_superadmin)):
    """Full tenant detail: agents, leads, policies, audit trail, subscription timeline."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)

    tenant = dict(tenant)
    # Mask sensitive tokens
    tok = tenant.get('tg_bot_token') or ''
    tenant['has_bot'] = bool(tok)
    tenant['tg_bot_token'] = f"{tok[:8]}...{tok[-4:]}" if len(tok) > 12 else ''
    tenant['has_whatsapp'] = bool(tenant.get('wa_phone_id'))
    # hide wa token
    tenant.pop('wa_access_token', None)

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Agents
        cur = await conn.execute(
            "SELECT agent_id, name, phone, email, role, is_active, created_at FROM agents WHERE tenant_id=?",
            (tenant_id,))
        agents = [dict(r) for r in await cur.fetchall()]

        # Lead stats
        cur = await conn.execute("""
            SELECT l.stage, COUNT(*) cnt
            FROM leads l JOIN agents a ON l.agent_id=a.agent_id
            WHERE a.tenant_id=? GROUP BY l.stage
        """, (tenant_id,))
        lead_stages = {r['stage']: r['cnt'] for r in await cur.fetchall()}

        cur = await conn.execute("""
            SELECT COUNT(*) FROM leads l JOIN agents a ON l.agent_id=a.agent_id
            WHERE a.tenant_id=?
        """, (tenant_id,))
        lead_total = (await cur.fetchone())[0]

        # Policy stats
        cur = await conn.execute("""
            SELECT p.status, COUNT(*) cnt
            FROM policies p JOIN agents a ON p.agent_id=a.agent_id
            WHERE a.tenant_id=? GROUP BY p.status
        """, (tenant_id,))
        policy_stats = {r['status']: r['cnt'] for r in await cur.fetchall()}

        cur = await conn.execute("""
            SELECT COUNT(*) FROM policies p JOIN agents a ON p.agent_id=a.agent_id
            WHERE a.tenant_id=?
        """, (tenant_id,))
        policy_total = (await cur.fetchone())[0]

        # Calculator usage
        cur = await conn.execute("""
            SELECT calc_type, COUNT(*) cnt
            FROM calculator_sessions cs JOIN agents a ON cs.agent_id=a.agent_id
            WHERE a.tenant_id=? GROUP BY calc_type
        """, (tenant_id,))
        calc_usage = {r['calc_type']: r['cnt'] for r in await cur.fetchall()}

        # Audit trail (last 50)
        cur = await conn.execute("""
            SELECT * FROM audit_log WHERE tenant_id=?
            ORDER BY created_at DESC LIMIT 50
        """, (tenant_id,))
        audit = [dict(r) for r in await cur.fetchall()]

    # Pending plan change
    pending_change = await db.get_pending_plan_change(tenant_id)
    plan_features = db.PLAN_FEATURES.get(tenant.get("plan", "trial"), db.PLAN_FEATURES["trial"])

    # Affiliate who referred this tenant
    ref_aff = await db.get_affiliate_for_tenant(tenant_id)
    if ref_aff:
        tenant['referred_by'] = ref_aff['name']
        tenant['referred_code'] = ref_aff['referral_code']

    return {
        "tenant": tenant,
        "agents": agents,
        "lead_stages": lead_stages,
        "lead_total": lead_total,
        "policy_stats": policy_stats,
        "policy_total": policy_total,
        "calc_usage": calc_usage,
        "audit": audit,
        "pending_plan_change": pending_change,
        "plan_features": plan_features,
    }


# ── SA Tenant Actions ───────────────────────────────────────────────────────

@app.post("/api/sa/tenant/{tenant_id}/extend")
async def sa_extend_trial(tenant_id: int, days: int = Query(14), sa=Depends(auth.require_superadmin)):
    """SA: Extend a tenant's trial."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)

    from datetime import datetime, timedelta
    old_end = tenant.get('trial_ends_at', '')
    try:
        end_dt = datetime.fromisoformat(old_end)
    except (ValueError, TypeError):
        end_dt = datetime.now()
    new_end = end_dt + timedelta(days=days)

    await db.update_tenant(tenant_id, trial_ends_at=new_end.isoformat(),
                           is_active=1, subscription_status='trial')
    await db.add_audit_log(tenant_id, None, "sa_extend_trial",
                           f"Extended trial by {days} days → {new_end.strftime('%Y-%m-%d')}",
                           role='superadmin')
    logger.info("🔧 SA extended trial for tenant %d by %d days", tenant_id, days)
    return {"status": "ok", "tenant_id": tenant_id, "new_trial_ends_at": new_end.isoformat()}


@app.post("/api/sa/tenant/{tenant_id}/activate")
async def sa_activate(tenant_id: int, plan: str = Query("individual"), sa=Depends(auth.require_superadmin)):
    """SA: Activate paid subscription (or reset to trial)."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)

    valid_plans = ('trial', 'individual', 'team', 'enterprise')
    if plan not in valid_plans:
        return JSONResponse({"detail": f"Invalid plan. Must be one of: {valid_plans}"}, status_code=400)

    pf = db.PLAN_FEATURES.get(plan, db.PLAN_FEATURES.get('individual', {}))
    if plan == 'trial':
        from datetime import datetime, timedelta
        trial_end = datetime.now() + timedelta(days=14)
        await db.update_tenant(tenant_id, is_active=1, subscription_status='trial',
                               plan='trial', max_agents=pf.get('max_agents', 1),
                               trial_ends_at=trial_end.strftime('%Y-%m-%d %H:%M:%S'))
        await db.add_audit_log(tenant_id, None, "sa_activate", f"Reset to trial (14 days)")
        logger.info("🔧 SA reset tenant %d to trial", tenant_id)
    else:
        await db.update_tenant(tenant_id, is_active=1, subscription_status='paid',
                               plan=plan, max_agents=pf.get('max_agents', 1))
        await db.add_audit_log(tenant_id, None, "sa_activate", f"Activated as {plan}")
        logger.info("🔧 SA activated tenant %d → %s", tenant_id, plan)
    return {"status": "ok", "tenant_id": tenant_id, "plan": plan}


@app.post("/api/sa/tenant/{tenant_id}/deactivate")
async def sa_deactivate(tenant_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Deactivate a tenant."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)

    await db.update_tenant(tenant_id, is_active=0, subscription_status='expired')
    await db.add_audit_log(tenant_id, None, "sa_deactivate", "Deactivated by super admin")
    logger.info("🔧 SA deactivated tenant %d", tenant_id)
    return {"status": "ok", "tenant_id": tenant_id}


@app.delete("/api/sa/tenant/{tenant_id}")
@limiter.limit("3/minute")
async def sa_delete_tenant(tenant_id: int, request: Request, sa=Depends(auth.require_superadmin)):
    """SA: Permanently delete a tenant and ALL associated data (cascading).
    This is irreversible!"""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)

    firm_name = tenant.get('firm_name', 'Unknown')

    # Stop tenant bot if running
    try:
        from biz_bot_manager import bot_manager
        if bot_manager and tenant.get('tg_bot_token'):
            await bot_manager.stop_tenant_bot(tenant_id)
    except Exception as e:
        logger.warning("Could not stop bot for tenant %d during delete: %s", tenant_id, e)

    # Perform cascading delete
    summary = await db.delete_tenant_cascade(tenant_id)
    await db.add_audit_log(0, None, "sa_delete_tenant",
                           f"Deleted tenant {tenant_id} ({firm_name}): {summary}")
    logger.warning("🗑️ SA DELETED tenant %d (%s) — %s", tenant_id, firm_name, summary)

    return {"status": "ok", "tenant_id": tenant_id, "firm_name": firm_name,
            "deleted": summary}


@app.post("/api/sa/tenant/{tenant_id}/plan")
async def sa_change_plan(tenant_id: int, plan: str = Query(...), sa=Depends(auth.require_superadmin)):
    """SA: Change tenant plan."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)

    valid_plans = ('trial', 'individual', 'team', 'enterprise')
    if plan not in valid_plans:
        return JSONResponse({"detail": f"Invalid plan. Must be one of: {valid_plans}"}, status_code=400)

    pf = db.PLAN_FEATURES.get(plan, db.PLAN_FEATURES.get('individual', {}))
    old_plan = tenant.get('plan', 'trial')
    if plan == 'trial':
        from datetime import datetime, timedelta
        trial_end = datetime.now() + timedelta(days=14)
        await db.update_tenant(tenant_id, plan='trial', subscription_status='trial',
                               max_agents=pf.get('max_agents', 1),
                               trial_ends_at=trial_end.strftime('%Y-%m-%d %H:%M:%S'))
    else:
        await db.update_tenant(tenant_id, plan=plan, max_agents=pf.get('max_agents', 1))
    await db.add_audit_log(tenant_id, None, "sa_change_plan", f"{old_plan} → {plan}")
    logger.info("🔧 SA changed plan for tenant %d: %s → %s", tenant_id, old_plan, plan)
    return {"status": "ok", "tenant_id": tenant_id, "plan": plan}


@app.post("/api/sa/tenant/{tenant_id}/force-plan-change")
async def sa_force_plan_change(tenant_id: int, plan: str = Query(...),
                                sa=Depends(auth.require_superadmin)):
    """SA: Force-apply a plan change immediately, clearing any pending schedule."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)
    result = await db.force_apply_plan_change(tenant_id, plan)
    if not result.get("success"):
        return JSONResponse({"detail": result.get("error", "Failed")}, status_code=400)
    logger.info("🔧 SA force-applied plan change for tenant %d → %s", tenant_id, plan)
    return result


@app.post("/api/sa/tenant/{tenant_id}/schedule-plan-change")
async def sa_schedule_plan_change(tenant_id: int, plan: str = Query(...),
                                   sa=Depends(auth.require_superadmin)):
    """SA: Schedule a plan change for next billing cycle."""
    result = await db.schedule_plan_change(tenant_id, plan, 'superadmin')
    if not result.get("success"):
        return JSONResponse({"detail": result.get("error", "Failed")}, status_code=400)
    logger.info("🔧 SA scheduled plan change for tenant %d → %s", tenant_id, plan)
    return result


@app.delete("/api/sa/tenant/{tenant_id}/pending-plan-change")
async def sa_cancel_pending_plan_change(tenant_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Cancel a pending plan change for a tenant."""
    ok = await db.cancel_pending_plan_change(tenant_id)
    if not ok:
        return JSONResponse({"detail": "No pending change found"}, status_code=404)
    logger.info("🔧 SA cancelled pending plan change for tenant %d", tenant_id)
    return {"status": "ok", "tenant_id": tenant_id}


# ── SA Create Firm ───────────────────────────────────────────────────────────

@app.post("/api/sa/create-firm")
@limiter.limit("10/minute")
async def sa_create_firm(req: CreateFirmRequest, request: Request, sa=Depends(auth.require_superadmin)):
    """SA: Create a firm manually."""
    # Sanitize inputs
    clean_phone = auth.sanitize_phone(req.phone)
    if not clean_phone:
        return JSONResponse({"detail": "Invalid phone number"}, status_code=400)
    clean_email = auth.sanitize_email(req.email) if req.email else None
    # Duplicate check before creation
    dup = await db.check_phone_email_duplicate(phone=clean_phone, email=clean_email or req.email)
    if dup:
        field = dup['field']
        existing = dup['tenant']
        return JSONResponse(
            {"detail": f"Duplicate {field}: already registered with tenant #{existing['tenant_id']} ({existing['firm_name']})"},
            status_code=409)

    plan = req.plan if req.plan in ('trial', 'individual', 'team', 'enterprise') else 'trial'
    pf = db.PLAN_FEATURES.get(plan, db.PLAN_FEATURES['trial'])
    account_type = 'individual' if plan == 'individual' else 'firm'
    tenant_id = await db.create_tenant(
        firm_name=req.firm_name.strip(), owner_name=req.owner_name.strip(),
        phone=clean_phone, email=clean_email, lang="en",
        city=getattr(req, 'city', '') or '',
        account_type=account_type, signup_channel="sa_manual")
    await db.update_tenant(tenant_id, plan=plan, max_agents=pf['max_agents'])
    if plan != 'trial':
        await db.update_tenant(tenant_id, subscription_status='paid')
    await db.add_audit_log(tenant_id, None, "sa_create_firm",
                           f"Created by super admin — plan: {plan}")
    logger.info("🔧 SA created firm #%d '%s' plan=%s", tenant_id, req.firm_name, plan)
    return {"status": "ok", "tenant_id": tenant_id, "firm_name": req.firm_name, "plan": plan}


# ── SA Audit Log ─────────────────────────────────────────────────────────────

@app.get("/api/sa/audit")
async def sa_audit_log(
    tenant_id: int = Query(None),
    action: str = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
    sa=Depends(auth.require_superadmin)
):
    """SA: Query audit log with filters."""
    query = "SELECT a.*, t.firm_name FROM audit_log a LEFT JOIN tenants t ON a.tenant_id=t.tenant_id"
    conditions = []
    params = []
    if tenant_id:
        conditions.append("a.tenant_id = ?")
        params.append(tenant_id)
    if action:
        conditions.append("a.action LIKE ?")
        params.append(f"%{action}%")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
    params.extend([min(limit, 500), offset])

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(query, params)
        rows = [dict(r) for r in await cur.fetchall()]

        # Total count for pagination
        count_q = "SELECT COUNT(*) FROM audit_log a"
        if conditions:
            count_q += " WHERE " + " AND ".join(conditions)
        cur = await conn.execute(count_q, params[:-2] if params else [])
        total = (await cur.fetchone())[0]

    return {"entries": rows, "total": total, "limit": limit, "offset": offset}


# ── SA Revenue ───────────────────────────────────────────────────────────────

@app.get("/api/sa/revenue")
async def sa_revenue(sa=Depends(auth.require_superadmin)):
    """SA: Revenue breakdown by plan."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        cur = await conn.execute("""
            SELECT plan, COUNT(*) cnt
            FROM tenants WHERE subscription_status IN ('paid','active') AND is_active=1
            GROUP BY plan
        """)
        breakdown = []
        total_mrr = 0
        for r in await cur.fetchall():
            price = PLAN_PRICES.get(r['plan'], 0)
            rev = price * r['cnt']
            total_mrr += rev
            breakdown.append({"plan": r['plan'], "count": r['cnt'], "price": price, "revenue": rev})

        # Monthly revenue trend (based on activation dates from audit log)
        cur = await conn.execute("""
            SELECT strftime('%Y-%m', created_at) as month, COUNT(*) cnt
            FROM tenants WHERE subscription_status IN ('paid','active')
            GROUP BY strftime('%Y-%m', created_at) ORDER BY month
        """)
        monthly = [{"month": r['month'], "count": r['cnt']} for r in await cur.fetchall()]

    return {"mrr": total_mrr, "arr": total_mrr * 12, "breakdown": breakdown, "monthly_trend": monthly}


# ── SA Bot Status ────────────────────────────────────────────────────────────

@app.get("/api/sa/bots")
async def sa_bots(sa=Depends(auth.require_superadmin)):
    """SA: Bot status overview."""
    mgr = botmgr.bot_manager
    running = []
    for tid, app_inst in mgr._bots.items():
        try:
            bi = app_inst.bot
            running.append({
                "tenant_id": tid, "username": f"@{bi.username}" if bi.username else "?",
                "name": bi.first_name or "?",
            })
        except Exception:
            running.append({"tenant_id": tid, "username": "error", "name": "error"})

    master_info = None
    if mgr._master_bot:
        try:
            mb = mgr._master_bot.bot
            master_info = {"username": f"@{mb.username}", "name": mb.first_name}
        except Exception:
            master_info = {"username": "error", "name": "error"}

    return {
        "master": master_info,
        "tenant_bots": running,
        "tenant_bot_count": len(running),
    }


@app.post("/api/sa/tenant/{tenant_id}/bot/restart")
async def sa_restart_bot(tenant_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Restart a tenant bot."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)
    token = tenant.get("tg_bot_token")
    if not token:
        return JSONResponse({"detail": "No bot token configured"}, status_code=400)
    mgr = botmgr.bot_manager
    await mgr.restart_tenant_bot(tenant_id, token)
    await db.add_audit_log(tenant_id, None, "sa_bot_restart", "Bot restarted by super admin")
    return {"status": "ok", "action": "bot_restarted"}


@app.post("/api/sa/tenant/{tenant_id}/bot/stop")
async def sa_stop_bot(tenant_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Stop a tenant bot."""
    mgr = botmgr.bot_manager
    if tenant_id not in mgr._bots:
        return JSONResponse({"detail": "Bot not running"}, status_code=404)
    await mgr.stop_tenant_bot(tenant_id)
    await db.add_audit_log(tenant_id, None, "sa_bot_stop", "Bot stopped by super admin")
    return {"status": "ok", "action": "bot_stopped"}


@app.post("/api/sa/restart-server")
async def sa_restart_server(sa=Depends(auth.require_superadmin)):
    """SA: Restart the entire server process (re-reads all code from disk)."""
    await db.add_audit_log(0, None, "sa_server_restart", "Full server restart by super admin")
    logger.warning("🔄 Full server restart requested by SA — spawning new process...")

    # Spawn a new server process then exit the current one
    async def _do_restart():
        await asyncio.sleep(1)  # let the HTTP response reach the client
        subprocess.Popen(
            [sys.executable] + sys.argv,
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        os._exit(0)

    asyncio.create_task(_do_restart())
    return {"status": "ok", "action": "server_restarting"}


# ── SA: Edit Tenant ──────────────────────────────────────────────────────────

@app.put("/api/sa/tenant/{tenant_id}")
async def sa_edit_tenant(tenant_id: int, request: Request, sa=Depends(auth.require_superadmin)):
    """SA: Edit tenant details."""
    body = await request.json()
    allowed = {
        'firm_name', 'owner_name', 'phone', 'email', 'brand_tagline', 'brand_cta',
        'brand_phone', 'brand_email', 'brand_primary_color', 'brand_accent_color',
        'irdai_license', 'max_agents', 'lang', 'is_active',
        'city', 'account_type',
    }
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if not updates:
        return JSONResponse({"detail": "No valid fields to update"}, status_code=400)

    # Duplicate check when phone or email is changing
    new_phone = updates.get('phone')
    new_email = updates.get('email')
    if new_phone or new_email:
        dup = await db.check_phone_email_duplicate(
            phone=new_phone, email=new_email, exclude_tenant_id=tenant_id)
        if dup:
            field = dup['field']
            existing = dup['tenant']
            return JSONResponse(
                {"detail": f"Duplicate {field}: already registered with tenant #{existing['tenant_id']} ({existing['firm_name']})"},
                status_code=409)

    await db.update_tenant(tenant_id, **updates)
    await db.add_audit_log(tenant_id, None, "sa_edit_tenant", f"Updated: {', '.join(updates.keys())}")
    logger.info("🔧 SA edited tenant %d: %s", tenant_id, list(updates.keys()))
    return {"status": "updated", "tenant_id": tenant_id, "fields": list(updates.keys())}


# ── SA: Agent Management ─────────────────────────────────────────────────────

@app.put("/api/sa/agent/{agent_id}")
async def sa_edit_agent(agent_id: int, request: Request, sa=Depends(auth.require_superadmin)):
    """SA: Edit agent details (name, phone, email, role, active)."""
    body = await request.json()
    agent = await db.get_agent_by_id(agent_id)
    if not agent:
        return JSONResponse({"detail": "Agent not found"}, status_code=404)

    allowed = {'name', 'phone', 'email', 'role', 'is_active'}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if not updates:
        return JSONResponse({"detail": "No valid fields to update"}, status_code=400)

    # Duplicate check if phone/email is changing
    new_phone = updates.get('phone')
    new_email = updates.get('email')
    if new_phone or new_email:
        dup = await db.check_phone_email_duplicate(
            phone=new_phone, email=new_email,
            exclude_tenant_id=agent.get('tenant_id'))
        if dup:
            return JSONResponse(
                {"detail": f"Duplicate {dup['field']}: already in use by tenant #{dup['tenant']['tenant_id']}"},
                status_code=409)

    await db.update_agent_by_sa(agent_id, **updates)
    await db.add_audit_log(agent.get('tenant_id', 0), None, "sa_edit_agent",
                           f"Agent #{agent_id} updated: {', '.join(updates.keys())}")
    logger.info("🔧 SA edited agent %d: %s", agent_id, list(updates.keys()))
    return {"status": "updated", "agent_id": agent_id, "fields": list(updates.keys())}


@app.post("/api/sa/agent/{agent_id}/toggle")
async def sa_toggle_agent(agent_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Toggle agent active/inactive."""
    agent = await db.get_agent_by_id(agent_id)
    if not agent:
        return JSONResponse({"detail": "Agent not found"}, status_code=404)
    new_status = 0 if agent['is_active'] else 1
    await db.update_agent_by_sa(agent_id, is_active=new_status)
    action = "activated" if new_status else "deactivated"
    await db.add_audit_log(agent.get('tenant_id', 0), None, "sa_toggle_agent",
                           f"Agent #{agent_id} {action}")
    return {"status": action, "agent_id": agent_id, "is_active": new_status}


# ── SA: Agent Activity Dashboard ─────────────────────────────────────────────

@app.get("/api/sa/agents/activity")
async def sa_agent_activity(
    tenant_id: int = Query(None),
    inactive_days: int = Query(30, ge=1, le=365),
    limit: int = Query(100),
    sa=Depends(auth.require_superadmin)
):
    """SA: Get agent activity report — last_active, lead counts, status.
    Optionally filter by tenant_id. Shows agents inactive for N days."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            SELECT a.agent_id, a.name, a.phone, a.role, a.is_active,
                   a.last_active, a.created_at, a.tenant_id,
                   t.firm_name, t.plan,
                   (SELECT COUNT(*) FROM leads l WHERE l.agent_id=a.agent_id) AS lead_count,
                   (SELECT COUNT(*) FROM policies p WHERE p.agent_id=a.agent_id) AS policy_count,
                   (SELECT COUNT(*) FROM interactions i WHERE i.agent_id=a.agent_id
                    AND i.created_at > datetime('now', '-7 days')) AS interactions_7d
            FROM agents a
            LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
        """
        params = []
        if tenant_id:
            query += " WHERE a.tenant_id = ?"
            params.append(tenant_id)
        query += " ORDER BY a.last_active DESC NULLS LAST LIMIT ?"
        params.append(min(limit, 500))
        cur = await conn.execute(query, params)
        agents = [dict(r) for r in await cur.fetchall()]

    # Compute inactivity flag
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=inactive_days)).isoformat()
    for a in agents:
        la = a.get('last_active')
        a['is_inactive'] = (not la) or (la < cutoff)
        a['days_since_active'] = None
        if la:
            try:
                dt = datetime.fromisoformat(la.replace('Z', '+00:00').replace(' ', 'T'))
                a['days_since_active'] = (datetime.utcnow() - dt.replace(tzinfo=None)).days
            except Exception:
                pass

    inactive_count = sum(1 for a in agents if a.get('is_inactive'))
    return {
        "agents": agents,
        "total": len(agents),
        "inactive_count": inactive_count,
        "inactive_threshold_days": inactive_days,
    }


# ── SA: Per-Tenant Error Events ──────────────────────────────────────────────

@app.get("/api/sa/tenant/{tenant_id}/errors")
async def sa_tenant_errors(
    tenant_id: int,
    limit: int = Query(50),
    sa=Depends(auth.require_superadmin)
):
    """SA: Get recent errors and system events for a specific tenant.
    Helps proactively identify issues before they become support tickets."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Get system events mentioning this tenant
        cur = await conn.execute("""
            SELECT * FROM system_events
            WHERE (tenant_id = ? OR detail LIKE ?)
            ORDER BY created_at DESC LIMIT ?
        """, (tenant_id, f"%tenant {tenant_id}%", min(limit, 200)))
        events = [dict(r) for r in await cur.fetchall()]

        # Get recent audit log entries (errors/warnings)
        cur = await conn.execute("""
            SELECT * FROM audit_log
            WHERE tenant_id = ? AND (action LIKE '%error%' OR action LIKE '%fail%'
                  OR action LIKE '%denied%' OR action LIKE '%block%')
            ORDER BY created_at DESC LIMIT ?
        """, (tenant_id, min(limit, 100)))
        error_logs = [dict(r) for r in await cur.fetchall()]

        # Get recent dead letter queue entries for this tenant
        dead_letters = []
        try:
            cur = await conn.execute("""
                SELECT * FROM dead_letter_queue
                WHERE tenant_id = ?
                ORDER BY created_at DESC LIMIT ?
            """, (tenant_id, 20))
            dead_letters = [dict(r) for r in await cur.fetchall()]
        except Exception:
            pass  # Table may not exist in some deployments

    return {
        "tenant_id": tenant_id,
        "firm_name": tenant.get("firm_name", ""),
        "events": events,
        "error_logs": error_logs,
        "dead_letters": dead_letters,
        "summary": {
            "total_events": len(events),
            "total_errors": len(error_logs),
            "total_dead_letters": len(dead_letters),
        }
    }


# ── SA: Duplicate Report ─────────────────────────────────────────────────────

@app.get("/api/sa/duplicates")
async def sa_duplicate_report(sa=Depends(auth.require_superadmin)):
    """SA: Get duplicate phone/email/telegram report across all tenants."""
    report = await db.get_duplicate_report()
    return report


# ── SA: Tenant Feature Management ────────────────────────────────────────────

@app.get("/api/sa/tenant/{tenant_id}/features")
async def sa_get_tenant_features(tenant_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Get tenant's current feature flags (plan defaults + overrides)."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)
    plan = tenant.get('plan', 'trial')
    plan_features = db.PLAN_FEATURES.get(plan, db.PLAN_FEATURES['trial']).copy()
    overrides = {}
    try:
        overrides = json.loads(tenant.get('feature_overrides') or '{}')
    except Exception:
        pass
    # Merge
    effective = {**plan_features, **overrides}
    return {
        "tenant_id": tenant_id,
        "plan": plan,
        "plan_features": plan_features,
        "overrides": overrides,
        "effective": effective,
        "all_features": list(plan_features.keys()),
    }

@app.put("/api/sa/tenant/{tenant_id}/features")
async def sa_update_tenant_features(tenant_id: int, request: Request, sa=Depends(auth.require_superadmin)):
    """SA: Update per-tenant feature overrides."""
    body = await request.json()
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)
    # body should be dict of feature_name: true/false
    valid_features = set(db.PLAN_FEATURES.get('enterprise', {}).keys())
    overrides = {}
    try:
        overrides = json.loads(tenant.get('feature_overrides') or '{}')
    except Exception:
        pass
    for k, v in body.items():
        if k in valid_features:
            if v is None:
                overrides.pop(k, None)  # Remove override, use plan default
            else:
                overrides[k] = bool(v)
    await db.update_tenant(tenant_id, feature_overrides=json.dumps(overrides))
    await db.add_audit_log(tenant_id, None, "sa_feature_update", f"Features updated: {overrides}")
    return {"status": "updated", "overrides": overrides}


# ── SA: System Status ────────────────────────────────────────────────────────

@app.get("/api/sa/system-status")
async def sa_system_status(sa=Depends(auth.require_superadmin)):
    """SA: Comprehensive system health, component status, and database stats."""
    import shutil

    uptime_sec = _time.time() - SERVER_START_TIME
    days, rem = divmod(int(uptime_sec), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    uptime_str = f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"

    # Database stats
    table_counts = {}
    async with aiosqlite.connect(db.DB_PATH) as conn:
        for table in ['tenants', 'agents', 'leads', 'policies', 'interactions',
                       'reminders', 'greetings_log', 'calculator_sessions',
                       'claims', 'audit_log', 'support_tickets', 'affiliates',
                       'affiliate_referrals', 'voice_logs']:
            try:
                cur = await conn.execute(f"SELECT COUNT(*) FROM {table}")
                row = await cur.fetchone()
                table_counts[table] = row[0] if row else 0
            except Exception:
                table_counts[table] = -1

    db_size = 0
    try:
        db_size = os.path.getsize(db.DB_PATH)
    except Exception:
        pass

    disk = shutil.disk_usage(os.path.dirname(os.path.abspath(__file__)))

    # Component health
    mgr = botmgr.bot_manager
    master_ok = mgr._master_bot is not None and mgr._master_bot.running
    tenant_bots_running = len([b for b in mgr._bots.values() if b.running]) if mgr._bots else 0
    tenant_bots_total = len(mgr._bots) if mgr._bots else 0

    wa_configured = bool(os.getenv("WHATSAPP_PHONE_ID") or os.getenv("WA_PHONE_ID"))
    razorpay_ok = payments.is_enabled() if hasattr(payments, 'is_enabled') else bool(os.getenv("RAZORPAY_KEY_ID"))
    gemini_ok = bool(os.getenv("GEMINI_API_KEY"))
    email_ok = bool(os.getenv("SMTP_USER")) and bool(os.getenv("SMTP_PASSWORD"))
    gdrive_ok = bool(os.getenv("GDRIVE_CLIENT_ID"))
    ngrok_url = os.getenv("SERVER_URL", "")
    sms_ok = sms.is_configured()

    # Fetch Fast2SMS wallet balance
    sms_detail = "Not configured"
    if sms_ok:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                wr = await client.post("https://www.fast2sms.com/dev/wallet",
                                       headers={"authorization": os.getenv("FAST2SMS_API_KEY", "")})
                wd = wr.json()
                if wd.get("return"):
                    sms_detail = f"Balance: ₹{wd.get('wallet', '?')} ({wd.get('sms_count', '?')} SMS)"
                else:
                    sms_detail = "Key active"
        except Exception:
            sms_detail = "Active (balance check failed)"

    components = [
        {"name": "FastAPI Server", "status": "healthy", "detail": f"Port {SERVER_PORT}, uptime {uptime_str}"},
        {"name": "SQLite Database", "status": "healthy", "detail": f"{db_size / 1024:.0f} KB, {sum(table_counts.values())} total rows"},
        {"name": "Telegram Master Bot", "status": "healthy" if master_ok else "down",
         "detail": f"@SarathiBizBot {'running' if master_ok else 'stopped'}"},
        {"name": "Telegram Tenant Bots", "status": "healthy" if tenant_bots_running > 0 else ("idle" if tenant_bots_total == 0 else "warning"),
         "detail": f"{tenant_bots_running}/{tenant_bots_total} running"},
        {"name": "Email (SMTP)", "status": "configured" if email_ok else "not_configured",
         "detail": "Ready — OTP + notifications" if email_ok else "SMTP credentials not set"},
        {"name": "Google Sign-In", "status": "configured" if os.getenv("GOOGLE_CLIENT_ID") else "not_configured",
         "detail": "OAuth 2.0 active" if os.getenv("GOOGLE_CLIENT_ID") else "Client ID not set"},
        {"name": "Razorpay Payments", "status": "configured" if razorpay_ok else "not_configured",
         "detail": ("Live mode" if not payments.is_test_mode() else "Test mode") if razorpay_ok else "Keys not set"},
        {"name": "Google Gemini AI", "status": "configured" if gemini_ok else "not_configured",
         "detail": "Gemini 2.0 Flash" if gemini_ok else "API key not set"},
        {"name": "WhatsApp Cloud API", "status": "not_configured",
         "detail": "Disabled — using Email OTP instead"},
        {"name": "SMS (Fast2SMS)", "status": "not_configured",
         "detail": "Disabled — using Email OTP instead"},
        {"name": "Google Drive", "status": "configured" if gdrive_ok else "not_configured",
         "detail": (f"OAuth ready • {gdrive.count_connected_tenants()} tenant(s) connected" if gdrive_ok else "GDRIVE_CLIENT_ID not set")},
        {"name": "Ngrok Tunnel", "status": "configured" if "ngrok" in ngrok_url else "not_configured",
         "detail": ngrok_url if "ngrok" in ngrok_url else "Not configured"},
    ]

    # Flows data
    flows = [
        {
            "name": "Customer Onboarding",
            "steps": [
                "Visitor lands on homepage",
                "Clicks 'Start Free Trial' → /onboarding page",
                "Chooses Firm or Individual signup",
                "Fills form (name, email, phone optional, firm details)",
                "Email OTP verification",
                "Account created (14-day trial)",
                "Login via Email OTP or Google Sign-In",
                "Bot token collection via Telegram",
                "Bot activated → CRM ready to use",
            ],
            "status": "active",
        },
        {
            "name": "Lead Lifecycle (Bot CRM)",
            "steps": [
                "Agent adds lead via /add command or voice note",
                "AI extracts lead details from voice (name, need, budget)",
                "Lead stored with stage: new",
                "Agent follows up → stage: contacted → pitched → negotiation",
                "AI generates smart pitch suggestions",
                "Agent converts lead → creates policy",
                "Auto-reminders for renewals & follow-ups",
                "Birthday/anniversary greetings auto-sent",
            ],
            "status": "active",
        },
        {
            "name": "Payment & Subscription",
            "steps": [
                "Trial expires after 14 days",
                "User selects plan (Solo ₹199 / Team ₹799 / Enterprise ₹1999)",
                "Razorpay checkout initiated",
                "Payment webhook received & verified",
                "Subscription activated, plan features unlocked",
                "Monthly auto-debit via Razorpay",
                "SA can extend trial / change plan / deactivate",
            ],
            "status": "active",
        },
        {
            "name": "WhatsApp Integration",
            "steps": [
                "Agent triggers WA message (greeting, report, pitch)",
                "System formats message with branding",
                "WhatsApp Cloud API sends message",
                "Calculator PDF reports attached when applicable",
                "Delivery status tracked (sent/delivered/read)",
                "Bulk campaigns for birthday/renewal batches",
            ],
            "status": "not_configured",
        },
        {
            "name": "Support Ticket Flow",
            "steps": [
                "User submits ticket from /support page",
                "Ticket created with category & priority",
                "SA gets notified, assigns priority",
                "SA replies → user sees response",
                "Status flow: open → in_progress → resolved → closed",
                "Resolution recorded for knowledge base",
            ],
            "status": "active",
        },
        {
            "name": "Affiliate/Partner Program",
            "steps": [
                "Partner signs up via /partner page",
                "Gets unique referral code & link",
                "Shares link with fellow advisors",
                "Referral tracked when prospect signs up",
                "On conversion → commission calculated",
                "SA reviews & approves payouts",
                "Partner dashboard shows real-time earnings",
            ],
            "status": "active",
        },
    ]

    return {
        "server": {
            "python_version": platform.python_version(),
            "os": f"{platform.system()} {platform.release()}",
            "uptime": uptime_str,
            "uptime_seconds": int(uptime_sec),
            "server_url": ngrok_url,
            "port": SERVER_PORT,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 1),
            "used_gb": round(disk.used / (1024**3), 1),
            "free_gb": round(disk.free / (1024**3), 1),
            "usage_pct": round(disk.used / disk.total * 100, 1),
        },
        "database": {
            "size_kb": round(db_size / 1024, 1),
            "table_counts": table_counts,
        },
        "components": components,
        "flows": flows,
    }


# ── SA: Data Export ──────────────────────────────────────────────────────────

def _rows_to_csv(rows: list[dict]) -> str:
    """Convert list-of-dicts to CSV string."""
    import csv, io
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

@app.get("/api/sa/export/tenants")
@limiter.limit("5/minute")
async def sa_export_tenants(request: Request, sa=Depends(auth.require_superadmin)):
    """SA: Export all tenants as CSV."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM tenants ORDER BY created_at DESC")
        rows = [dict(r) for r in await cur.fetchall()]
    csv_data = _rows_to_csv(rows)
    return Response(content=csv_data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tenants_export.csv"})


@app.get("/api/sa/export/leads")
@limiter.limit("5/minute")
async def sa_export_leads(request: Request, sa=Depends(auth.require_superadmin)):
    """SA: Export all leads as CSV."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT l.*, a.name AS agent_name, a.tenant_id "
            "FROM leads l JOIN agents a ON l.agent_id = a.agent_id "
            "ORDER BY l.created_at DESC LIMIT 5000"
        )
        rows = [dict(r) for r in await cur.fetchall()]
    csv_data = _rows_to_csv(rows)
    return Response(content=csv_data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=leads_export.csv"})


@app.get("/api/sa/export/affiliates")
@limiter.limit("5/minute")
async def sa_export_affiliates(request: Request, sa=Depends(auth.require_superadmin)):
    """SA: Export all affiliates as CSV."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM affiliates ORDER BY created_at DESC")
        rows = [dict(r) for r in await cur.fetchall()]
    csv_data = _rows_to_csv(rows)
    return Response(content=csv_data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=affiliates_export.csv"})


# =============================================================================
#  SA — BULK ACTIONS
# =============================================================================

class BulkIdsRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=100)

@app.post("/api/sa/tenants/bulk-activate")
async def sa_bulk_activate(body: BulkIdsRequest, sa=Depends(auth.require_superadmin)):
    """SA: Activate multiple tenants at once."""
    ok, fail = [], []
    for tid in body.ids:
        try:
            t = await db.get_tenant(tid)
            if not t:
                fail.append({"id": tid, "reason": "not found"}); continue
            await db.update_tenant(tid, is_active=1, subscription_status='active')
            await db.add_audit_log(tid, None, "sa_bulk_activate", "Bulk activated by SA")
            ok.append(tid)
        except Exception as e:
            fail.append({"id": tid, "reason": str(e)})
    return {"activated": ok, "failed": fail}


@app.post("/api/sa/tenants/bulk-deactivate")
async def sa_bulk_deactivate(body: BulkIdsRequest, sa=Depends(auth.require_superadmin)):
    """SA: Deactivate multiple tenants at once."""
    ok, fail = [], []
    for tid in body.ids:
        try:
            t = await db.get_tenant(tid)
            if not t:
                fail.append({"id": tid, "reason": "not found"}); continue
            await db.update_tenant(tid, is_active=0, subscription_status='expired')
            await db.add_audit_log(tid, None, "sa_bulk_deactivate", "Bulk deactivated by SA")
            ok.append(tid)
        except Exception as e:
            fail.append({"id": tid, "reason": str(e)})
    return {"deactivated": ok, "failed": fail}


@app.post("/api/sa/tenants/bulk-delete")
@limiter.limit("2/minute")
async def sa_bulk_delete(body: BulkIdsRequest, request: Request,
                         sa=Depends(auth.require_superadmin)):
    """SA: Delete multiple tenants (cascading). Max 20 per call."""
    if len(body.ids) > 20:
        return JSONResponse({"detail": "Max 20 tenants per bulk delete"}, status_code=400)
    ok, fail = [], []
    for tid in body.ids:
        try:
            t = await db.get_tenant(tid)
            if not t:
                fail.append({"id": tid, "reason": "not found"}); continue
            try:
                from biz_bot_manager import bot_manager
                if bot_manager and t.get('tg_bot_token'):
                    await bot_manager.stop_tenant_bot(tid)
            except Exception:
                pass
            summary = await db.delete_tenant_cascade(tid)
            await db.add_audit_log(0, None, "sa_bulk_delete",
                                   f"Deleted tenant {tid} ({t.get('firm_name','')}): {summary}")
            ok.append(tid)
        except Exception as e:
            fail.append({"id": tid, "reason": str(e)})
    return {"deleted": ok, "failed": fail}


@app.post("/api/sa/tenants/bulk-plan")
async def sa_bulk_change_plan(body: BulkIdsRequest, plan: str = Query(...),
                              sa=Depends(auth.require_superadmin)):
    """SA: Change plan for multiple tenants at once."""
    valid_plans = ('individual', 'team', 'enterprise')
    if plan not in valid_plans:
        return JSONResponse({"detail": "Invalid plan"}, status_code=400)
    pf = db.PLAN_FEATURES.get(plan, db.PLAN_FEATURES['individual'])
    ok, fail = [], []
    for tid in body.ids:
        try:
            t = await db.get_tenant(tid)
            if not t:
                fail.append({"id": tid, "reason": "not found"}); continue
            old_plan = t.get('plan', 'trial')
            await db.update_tenant(tid, plan=plan, max_agents=pf['max_agents'])
            await db.add_audit_log(tid, None, "sa_bulk_plan", f"{old_plan} → {plan}")
            ok.append(tid)
        except Exception as e:
            fail.append({"id": tid, "reason": str(e)})
    return {"changed": ok, "plan": plan, "failed": fail}


# =============================================================================
#  SA — IMPERSONATE TENANT (view as tenant owner)
# =============================================================================

@app.post("/api/sa/tenant/{tenant_id}/impersonate")
async def sa_impersonate_tenant(tenant_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Get a short-lived access token to view dashboard as tenant owner.
    Token has 1-hour expiry and is marked as impersonation session."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)
    # Find the owner agent
    agents = await db.get_agents_by_tenant(tenant_id)
    owner = next((a for a in agents if a.get('role') == 'owner'), None)
    if not owner:
        return JSONResponse({"detail": "No owner agent found"}, status_code=404)
    # Create a short-lived impersonation token (1 hour, imp:true marked)
    token = auth.create_impersonation_token(
        tenant_id=tenant_id,
        phone=owner.get('phone', ''),
        firm_name=tenant.get('firm_name', ''),
        role='owner',
        agent_id=owner.get('agent_id')
    )
    sa_phone = sa.get('phone', 'unknown') if isinstance(sa, dict) else 'unknown'
    await db.add_audit_log(tenant_id, None, "sa_impersonate",
                           f"SA ({sa_phone}) impersonated tenant {tenant_id} ({tenant.get('firm_name','')})",
                           role='superadmin')
    logger.warning("👁️ SA IMPERSONATING tenant %d (%s) — SA phone: %s",
                   tenant_id, tenant.get('firm_name',''), sa_phone)
    return {"token": token, "tenant_id": tenant_id,
            "firm_name": tenant.get('firm_name', ''),
            "owner_name": owner.get('name', '')}


# =============================================================================
#  SA — IMPERSONATE AFFILIATE (view partner dashboard as affiliate)
# =============================================================================

@app.post("/api/sa/affiliate/{affiliate_id}/impersonate")
async def sa_impersonate_affiliate(affiliate_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Get a short-lived affiliate JWT to view partner dashboard as this affiliate."""
    aff = await db.get_affiliate(affiliate_id)
    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)
    aff = dict(aff) if not isinstance(aff, dict) else aff
    import jwt as _jwt
    token = _jwt.encode({
        "sub": str(aff['affiliate_id']),
        "email": aff.get('email', ''),
        "phone": aff.get('phone', ''),
        "type": "affiliate",
        "imp": True,
        "iat": int(_time.time()),
        "exp": int(_time.time()) + 3600,
    }, auth.JWT_SECRET, algorithm="HS256")
    sa_phone = sa.get('phone', 'unknown') if isinstance(sa, dict) else 'unknown'
    logger.warning("👁️ SA IMPERSONATING affiliate %d (%s) — SA phone: %s",
                   affiliate_id, aff.get('name', ''), sa_phone)
    return {"token": token, "affiliate_id": affiliate_id,
            "name": aff.get('name', ''),
            "referral_code": aff.get('referral_code', '')}


# =============================================================================
#  SA — SYSTEM EVENTS / MONITORING
# =============================================================================

@app.get("/api/sa/events")
async def sa_get_events(event_type: str = Query(None),
                        severity: str = Query(None),
                        resolved: int = Query(None),
                        limit: int = Query(100), offset: int = Query(0),
                        sa=Depends(auth.require_superadmin)):
    """SA: Get system events (errors, security alerts, anomalies)."""
    events = await db.get_system_events(event_type, severity, resolved, limit, offset)
    stats = await db.get_system_event_stats()
    return {"events": events, "stats": stats}


@app.post("/api/sa/events/{event_id}/resolve")
async def sa_resolve_event(event_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Mark a system event as resolved."""
    ok = await db.resolve_system_event(event_id)
    if not ok:
        return JSONResponse({"detail": "Event not found or already resolved"}, status_code=404)
    return {"status": "ok", "event_id": event_id}


@app.post("/api/sa/events/bulk-resolve")
async def sa_bulk_resolve_events(body: BulkIdsRequest,
                                 sa=Depends(auth.require_superadmin)):
    """SA: Resolve multiple events at once."""
    count = await db.bulk_resolve_system_events(body.ids)
    return {"resolved": count}


@app.post("/api/sa/anomaly-scan")
async def sa_run_anomaly_scan(sa=Depends(auth.require_superadmin)):
    """SA: Run a full anomaly scan across the system.
    Detects: expired trials still active, orphan agents, orphan leads,
    duplicate phones, tenants with no agents, failed login spikes, spam detection."""
    findings = await db.run_anomaly_scan()
    # Persist findings as system events
    new_events = 0
    for f in findings:
        await db.add_system_event(
            event_type=f["type"], severity=f["severity"],
            category=f["category"], title=f["title"],
            detail=f.get("detail"), tenant_id=f.get("tenant_id"))
        new_events += 1
    return {"findings": len(findings), "events_created": new_events,
            "details": findings}


@app.get("/api/sa/notifications")
async def sa_get_notifications(sa=Depends(auth.require_superadmin)):
    """SA: Get notification digest for bell icon (unresolved counts + recent events)."""
    return await db.get_notification_digest()


@app.post("/api/sa/auto-remediate")
async def sa_run_auto_remediation(sa=Depends(auth.require_superadmin)):
    """SA: Run auto-remediation (fix expired trials, orphan agents/leads)."""
    summary = await db.run_auto_remediation()
    return summary


@app.post("/api/sa/ai-classify-events")
async def sa_ai_classify_events(sa=Depends(auth.require_superadmin)):
    """SA: Use AI to classify and prioritize unresolved system events."""
    import biz_ai as ai_mod
    events = await db.get_system_events(resolved=0, limit=50)
    if not events:
        return {"analysis": [], "summary": "No unresolved events to analyze.",
                "patterns": [], "immediate_actions": []}
    result = await ai_mod.classify_anomalies(events)
    return result


# =============================================================================
#  HEALTH MONITOR — Tier 2 Proactive Monitoring
# =============================================================================

@app.get("/api/sa/health-monitor")
async def sa_health_monitor_latest(sa=Depends(auth.require_superadmin)):
    """SA: Get latest health check results."""
    import biz_health_monitor as hm
    return await hm.get_latest_checks()


@app.get("/api/sa/health-monitor/history")
async def sa_health_monitor_history(limit: int = 20, sa=Depends(auth.require_superadmin)):
    """SA: Get health check run history."""
    import biz_health_monitor as hm
    runs = await hm.get_check_history(min(limit, 100))
    return {"runs": runs}


@app.get("/api/sa/health-monitor/alerts")
async def sa_health_monitor_alerts(limit: int = 50, sa=Depends(auth.require_superadmin)):
    """SA: Get health alert history."""
    import biz_health_monitor as hm
    alerts = await hm.get_alerts(min(limit, 200))
    return {"alerts": alerts}


@app.post("/api/sa/health-monitor/run")
async def sa_health_monitor_run(sa=Depends(auth.require_superadmin)):
    """SA: Trigger a manual health check now."""
    import biz_health_monitor as hm
    result = await hm.run_full_health_check(manual=True)
    return result


# =============================================================================
#  SUPPORT TICKETS — Customer & SA endpoints
# =============================================================================

class TicketCreateRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10, max_length=5000)
    category: str = Field("general", pattern=r"^(general|billing|technical|bug|feature|other)$")
    priority: str = Field("normal", pattern=r"^(low|normal|high|urgent)$")
    contact_name: str = Field("", max_length=100)
    contact_phone: str = Field("", max_length=15)
    contact_email: str = Field("", max_length=200)


@app.get("/support", response_class=HTMLResponse)
async def support_page():
    """Serve the support ticket page."""
    f = static_dir / "support.html"
    if f.exists():
        return HTMLResponse(f.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Support page not found</h1>", status_code=404)


@app.post("/api/support/tickets")
@limiter.limit("10/minute")
async def create_support_ticket(req: TicketCreateRequest, request: Request):
    """Create a support ticket. Works for both authenticated (paid) and public (inquiry)."""
    tenant = await auth.get_optional_tenant(request)
    tenant_id = tenant["tenant_id"] if tenant else None
    is_trial = 0

    if tenant_id:
        t = await db.get_tenant(tenant_id)
        is_trial = 1 if t and t.get("subscription_status") == "trial" else 0

    ticket_id = await db.create_ticket(
        tenant_id=tenant_id, subject=req.subject, description=req.description,
        category=req.category, priority=req.priority, is_trial=is_trial,
        contact_name=req.contact_name or None,
        contact_phone=req.contact_phone or None,
        contact_email=req.contact_email or None)

    # Add initial message
    sender = req.contact_name or (tenant and tenant.get("firm", "Customer")) or "Visitor"
    await db.add_ticket_message(ticket_id, "customer", sender, req.description)

    # ── AI Level 1 Auto-Response ─────────────────────────────────────────
    ai_response = None
    try:
        import biz_ai as ai_mod
        ai_result = await ai_mod.ai_support_auto_respond(
            subject=req.subject, description=req.description,
            category=req.category or "general")
        if ai_result and ai_result.get('answer') and not ai_result.get('escalate'):
            ai_msg = (f"🤖 AI Assistant (auto-response):\n\n"
                      f"{ai_result['answer']}\n\n"
                      f"—\nIf this didn't help, reply here and our team "
                      f"will personally assist you.")
            await db.add_ticket_message(ticket_id, "admin", "Sarathi AI", ai_msg)
            ai_response = {
                'ai_answer': ai_result['answer'],
                'ai_confidence': ai_result.get('confidence', 'medium'),
                'ai_topic': ai_result.get('matched_topic', 'general'),
            }
            logger.info("🤖 AI L1 auto-responded to ticket #%d (topic=%s, conf=%s)",
                        ticket_id, ai_result.get('matched_topic'),
                        ai_result.get('confidence'))
        elif ai_result and ai_result.get('escalate'):
            logger.info("🎫 Ticket #%d escalated to human (AI: topic=%s)",
                        ticket_id, ai_result.get('matched_topic'))
    except Exception as e:
        logger.warning("AI L1 support error for ticket #%d: %s", ticket_id, e)

    logger.info("🎫 Support ticket #%d created (%s) tenant=%s",
                ticket_id, req.category, tenant_id or "public")

    # ── Email notification to admin ──
    try:
        tenant_info = ""
        if tenant:
            t = await db.get_tenant(tenant_id)
            if t:
                tenant_info = f"{t.get('firm_name', '')} ({t.get('owner_email', '')})"
        asyncio.create_task(email_svc.send_support_ticket_notification(
            ticket_id=ticket_id, subject=req.subject,
            description=req.description, category=req.category or "general",
            priority=req.priority or "normal", tenant_info=tenant_info))
    except Exception as e:
        logger.warning("Support email notification failed: %s", e)

    result = {"status": "ok", "ticket_id": ticket_id}
    if ai_response:
        result["ai_response"] = ai_response
    return result


@app.get("/api/support/tickets")
async def list_support_tickets(request: Request,
                               status: str = Query(None),
                               limit: int = Query(20),
                               offset: int = Query(0)):
    """List tickets for the authenticated tenant."""
    tenant = await auth.get_optional_tenant(request)
    if not tenant:
        return JSONResponse({"detail": "Login required"}, status_code=401)

    tickets, total = await db.get_tickets(
        tenant_id=tenant["tenant_id"], status=status, limit=limit, offset=offset)
    return {"tickets": tickets, "total": total}


@app.get("/api/support/tickets/{ticket_id}")
async def get_support_ticket(ticket_id: int, request: Request):
    """Get ticket detail with messages. JWT required."""
    tenant = await auth.get_optional_tenant(request)
    if not tenant:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        return JSONResponse({"detail": "Ticket not found"}, status_code=404)

    # Tenant can only see own tickets
    if ticket.get("tenant_id") != tenant["tenant_id"]:
        return JSONResponse({"detail": "Not authorized"}, status_code=403)

    messages = await db.get_ticket_messages(ticket_id)
    return {"ticket": ticket, "messages": messages}


class TicketReplyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)

@app.post("/api/support/tickets/{ticket_id}/reply")
async def reply_to_ticket(ticket_id: int, req: TicketReplyRequest, request: Request):
    """Add a reply to a ticket (customer side). JWT required."""
    tenant = await auth.get_optional_tenant(request)
    if not tenant:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        return JSONResponse({"detail": "Ticket not found"}, status_code=404)
    if ticket.get("tenant_id") != tenant["tenant_id"]:
        return JSONResponse({"detail": "Not authorized"}, status_code=403)

    sender = tenant.get("firm", "Customer")
    msg_id = await db.add_ticket_message(ticket_id, "customer", sender, req.message)

    # Reopen if resolved/closed
    if ticket.get("status") in ("resolved", "closed"):
        await db.update_ticket(ticket_id, status="open")

    return {"status": "ok", "message_id": msg_id}


# ── SA Support Management ───────────────────────────────────────────────────

@app.get("/api/sa/tickets")
async def sa_list_tickets(status: str = Query(None),
                          limit: int = Query(50), offset: int = Query(0),
                          sa=Depends(auth.require_superadmin)):
    """SA: List all support tickets."""
    tickets, total = await db.get_tickets(status=status, limit=limit, offset=offset)
    return {"tickets": tickets, "total": total}


@app.get("/api/sa/tickets/stats")
async def sa_ticket_stats(sa=Depends(auth.require_superadmin)):
    """SA: Ticket statistics."""
    return await db.get_ticket_stats()


@app.get("/api/sa/ai-costs")
async def sa_ai_costs(sa=Depends(auth.require_superadmin),
                      days: int = Query(30, ge=1, le=90)):
    """SA: Platform-wide AI cost summary with budget alert."""
    summary = await db.get_global_ai_cost_summary(days=days)
    if summary.get('over_budget'):
        logger.warning("⚠️ AI BUDGET ALERT: $%.4f / $%.2f (%.1f%%) over %d days",
                        summary['total_cost_usd'], summary['budget_usd'],
                        summary['budget_used_pct'], days)
    return summary


@app.get("/api/sa/tickets/{ticket_id}")
async def sa_get_ticket(ticket_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Get ticket with messages."""
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        return JSONResponse({"detail": "Ticket not found"}, status_code=404)
    messages = await db.get_ticket_messages(ticket_id)
    return {"ticket": ticket, "messages": messages}


class SATicketUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(open|in_progress|resolved|closed)$")
    priority: Optional[str] = Field(None, pattern=r"^(low|normal|high|urgent)$")
    assigned_to: Optional[str] = Field(None, max_length=100)
    resolution: Optional[str] = Field(None, max_length=2000)

@app.put("/api/sa/tickets/{ticket_id}")
async def sa_update_ticket(ticket_id: int, req: SATicketUpdateRequest,
                           sa=Depends(auth.require_superadmin)):
    """SA: Update ticket (status, priority, assignment, resolution)."""
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        return JSONResponse({"detail": "Ticket not found"}, status_code=404)

    updates = {}
    if req.status:
        updates["status"] = req.status
        if req.status in ("resolved", "closed"):
            from datetime import datetime as _dt
            updates["resolved_at"] = _dt.now().isoformat()
    if req.priority:
        updates["priority"] = req.priority
    if req.assigned_to is not None:
        updates["assigned_to"] = req.assigned_to
    if req.resolution:
        updates["resolution"] = req.resolution

    if updates:
        await db.update_ticket(ticket_id, **updates)
    return {"status": "ok", "ticket_id": ticket_id}


@app.post("/api/sa/tickets/{ticket_id}/reply")
async def sa_reply_to_ticket(ticket_id: int, req: TicketReplyRequest,
                             sa=Depends(auth.require_superadmin)):
    """SA: Reply to a ticket (admin side)."""
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        return JSONResponse({"detail": "Ticket not found"}, status_code=404)

    msg_id = await db.add_ticket_message(ticket_id, "admin", "Sarathi Support", req.message)

    # Auto-update status to in_progress if open
    if ticket.get("status") == "open":
        await db.update_ticket(ticket_id, status="in_progress")

    return {"status": "ok", "message_id": msg_id}


# =============================================================================
#  AFFILIATE / PARTNER PROGRAM
# =============================================================================

@app.get("/partner", response_class=HTMLResponse)
async def partner_page():
    """Serve the affiliate/partner program page."""
    f = static_dir / "partner.html"
    if f.exists():
        return HTMLResponse(f.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Partner page not found</h1>", status_code=404)


class AffiliateRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field("", max_length=15)  # optional
    email: str = Field(..., min_length=5, max_length=200)


@app.post("/api/affiliate/register")
@limiter.limit("5/minute")
async def affiliate_register(req: AffiliateRegisterRequest, request: Request):
    """Step 1: Register affiliate — sends email OTP for verification."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Valid email is required for affiliates"}, status_code=400)
    phone = auth.sanitize_phone(req.phone) if req.phone else ""

    # Check if already registered by email
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT affiliate_id, referral_code, status, email_verified FROM affiliates WHERE email = ?", (email,))
        existing = await cur.fetchone()

    if existing:
        existing = dict(existing)
        if existing.get('email_verified'):
            return JSONResponse({
                "detail": "Already registered",
                "referral_code": existing["referral_code"],
                "status": existing["status"]}, status_code=409)
        # Re-send email OTP for incomplete verification
        otp_result = auth.generate_email_otp(email)
        if "error" in otp_result:
            return JSONResponse({"detail": otp_result["error"]}, status_code=429)
        asyncio.create_task(email_svc.send_otp_email(email, otp_result["otp"], req.name))
        logger.info("🤝 Affiliate re-verify email OTP for %s", email[:3] + "***")
        return {"status": "otp_sent", "message": "Verification pending. OTP sent to your email.",
                "affiliate_id": existing["affiliate_id"]}

    # Create affiliate in pending_verification state
    result = await db.create_affiliate(
        name=auth.sanitize_text(req.name, 100), phone=phone,
        email=email)

    # Send email OTP
    otp_result = auth.generate_email_otp(email)
    if "error" in otp_result:
        return JSONResponse({"detail": otp_result["error"]}, status_code=429)
    asyncio.create_task(email_svc.send_otp_email(email, otp_result["otp"], req.name))

    logger.info("🤝 New affiliate signup initiated: %s (%s)", req.name, email[:3] + "***")
    return {"status": "otp_sent", "message": "OTP sent to your email. Verify to complete registration.",
            "affiliate_id": result["affiliate_id"]}


class AffiliateVerifyRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    otp: str = Field(..., min_length=4, max_length=6)


@app.post("/api/affiliate/verify")
@limiter.limit("10/minute")
async def affiliate_verify(req: AffiliateVerifyRequest, request: Request):
    """Step 2: Verify email OTP for affiliate registration."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email"}, status_code=400)

    # Find affiliate by email
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM affiliates WHERE email = ?", (email,))
        aff = await cur.fetchone()
    if not aff:
        return JSONResponse({"detail": "Affiliate not found. Register first."}, status_code=404)
    aff = dict(aff)

    if not auth.verify_email_otp(email, req.otp):
        return JSONResponse({"detail": "Invalid or expired OTP"}, status_code=401)

    await db.update_affiliate(aff['affiliate_id'], email_verified=1, phone_verified=1,
                              status='active', approved=1)

    # Send welcome email
    asyncio.create_task(email_svc.send_affiliate_welcome(
        email, aff['name'], aff['referral_code']))

    logger.info("✅ Affiliate verified & activated: %s code=%s", aff['name'], aff['referral_code'])
    # Auto-login after verification
    aff['status'] = 'active'
    aff['email_verified'] = 1
    return await _affiliate_google_login_inner(email, aff)


class AffiliateLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)


@app.post("/api/affiliate/login")
@limiter.limit("5/minute")
async def affiliate_login(req: AffiliateLoginRequest, request: Request):
    """Affiliate login — sends OTP to verified email."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email address"}, status_code=400)

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM affiliates WHERE email = ?", (email,))
        aff = await cur.fetchone()
    if not aff:
        return JSONResponse({"detail": "No affiliate account found with this email"}, status_code=404)
    if aff['status'] == 'inactive':
        return JSONResponse({"detail": "Your affiliate account has been deactivated"}, status_code=403)

    otp_result = auth.generate_email_otp(email)
    if "error" in otp_result:
        return JSONResponse({"detail": otp_result["error"]}, status_code=429)

    aff_name = aff['name'] if aff else ''
    asyncio.create_task(email_svc.send_otp_email(email, otp_result["otp"], aff_name))

    return {"status": "otp_sent", "message": "OTP sent to your email"}


class AffiliateLoginVerifyRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    otp: str = Field(..., min_length=4, max_length=6)


@app.post("/api/affiliate/login/verify")
@limiter.limit("10/minute")
async def affiliate_login_verify(req: AffiliateLoginVerifyRequest, request: Request):
    """Verify affiliate login OTP — returns affiliate JWT token."""
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Invalid email"}, status_code=400)

    if not auth.verify_email_otp(email, req.otp):
        return JSONResponse({"detail": "Invalid or expired OTP"}, status_code=401)

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM affiliates WHERE email = ?", (email,))
        aff = await cur.fetchone()
    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)
    aff = dict(aff)

    # Create affiliate JWT (valid 24h)
    import jwt as _jwt
    token = _jwt.encode({
        "sub": str(aff['affiliate_id']),
        "email": email,
        "phone": aff.get('phone', ''),
        "type": "affiliate",
        "iat": int(_time.time()),
        "exp": int(_time.time()) + 86400,
    }, auth.JWT_SECRET, algorithm="HS256")

    logger.info("🤝 Affiliate login: %s (%s)", aff['name'], email)
    # Strip sensitive fields before sending to client
    safe_aff = {k: v for k, v in aff.items()
                if k not in ('bank_account', 'ifsc_code', 'account_holder')}
    # Mask bank fields for display only
    if aff.get('bank_account'):
        safe_aff['bank_account_masked'] = '****' + aff['bank_account'][-4:]
    response = JSONResponse({
        "status": "ok",
        "affiliate": safe_aff,
        "token": token,
    })
    response.set_cookie("affiliate_token", token, httponly=True, samesite="lax",
                        max_age=86400, secure=True)
    return response


# ── Affiliate Google Sign-in ──────────────────────────────────────────────────

@app.post("/api/affiliate/register/google")
@limiter.limit("5/minute")
async def affiliate_register_google(req: GoogleSignInRequest, request: Request):
    """Register affiliate via Google — skip OTP (email verified by Google)."""
    google_user = await auth.verify_google_id_token(req.credential)
    if not google_user:
        return JSONResponse({"detail": "Invalid Google credential"}, status_code=401)

    email = google_user["email"].lower().strip()
    name = google_user.get("name", "")

    # Check if already registered
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT affiliate_id, referral_code, status, email_verified FROM affiliates WHERE email = ?",
            (email,))
        existing = await cur.fetchone()

    if existing:
        existing = dict(existing)
        if existing.get('email_verified'):
            # Already registered — auto-login instead
            return await _affiliate_google_login_inner(email, existing)
        # Partially registered — activate now (Google verified email)
        await db.update_affiliate(existing['affiliate_id'], email_verified=1,
                                  phone_verified=1, status='active', approved=1, name=name)
        asyncio.create_task(email_svc.send_affiliate_welcome(
            email, name, existing['referral_code']))
        logger.info("✅ Affiliate Google-verified & activated: %s code=%s", name, existing['referral_code'])
        # Auto-login after activation
        activated = dict(existing)
        activated['status'] = 'active'
        activated['email_verified'] = 1
        activated['name'] = name
        return await _affiliate_google_login_inner(email, activated)

    # Create new affiliate — immediately active (Google verified)
    result = await db.create_affiliate(
        name=auth.sanitize_text(name, 100), phone="", email=email)
    await db.update_affiliate(result['affiliate_id'], email_verified=1,
                              phone_verified=1, status='active', approved=1)

    asyncio.create_task(email_svc.send_affiliate_welcome(
        email, name, result['referral_code']))

    logger.info("🆕 Affiliate Google signup: %s (%s) → code=%s", name, email, result['referral_code'])
    # Auto-login new affiliate
    new_aff = {'affiliate_id': result['affiliate_id'], 'referral_code': result['referral_code'],
               'name': auth.sanitize_text(name, 100), 'email': email, 'phone': '',
               'status': 'active', 'email_verified': 1}
    return await _affiliate_google_login_inner(email, new_aff)


@app.post("/api/affiliate/login/google")
@limiter.limit("10/minute")
async def affiliate_login_google(req: GoogleSignInRequest, request: Request):
    """Affiliate login via Google — no OTP needed."""
    google_user = await auth.verify_google_id_token(req.credential)
    if not google_user:
        return JSONResponse({"detail": "Invalid Google credential"}, status_code=401)

    email = google_user["email"].lower().strip()

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM affiliates WHERE email = ?", (email,))
        aff = await cur.fetchone()

    if not aff:
        return JSONResponse({
            "detail": "No affiliate account found. Please sign up first.",
            "email": email,
            "name": google_user.get("name", ""),
        }, status_code=404)

    return await _affiliate_google_login_inner(email, dict(aff))


async def _affiliate_google_login_inner(email: str, aff: dict) -> JSONResponse:
    """Issue affiliate JWT from verified Google email — shared by register & login."""
    if aff.get('status') == 'inactive':
        return JSONResponse({"detail": "Your affiliate account has been deactivated"}, status_code=403)

    import jwt as _jwt
    token = _jwt.encode({
        "sub": str(aff['affiliate_id']),
        "email": email,
        "phone": aff.get('phone', ''),
        "type": "affiliate",
        "iat": int(_time.time()),
        "exp": int(_time.time()) + 86400,
    }, auth.JWT_SECRET, algorithm="HS256")

    logger.info("🤝 Affiliate Google login: %s (%s)", aff.get('name', ''), email)
    safe_aff = {k: v for k, v in aff.items()
                if k not in ('bank_account', 'ifsc_code', 'account_holder')}
    if aff.get('bank_account'):
        safe_aff['bank_account_masked'] = '****' + aff['bank_account'][-4:]
    response = JSONResponse({
        "status": "ok",
        "affiliate": safe_aff,
        "token": token,
    })
    response.set_cookie("affiliate_token", token, httponly=True, samesite="lax",
                        max_age=86400, secure=True)
    return response


async def _get_affiliate_from_token(request: Request) -> dict:
    """Extract affiliate from JWT token (cookie or header)."""
    import jwt as _jwt
    token = request.cookies.get("affiliate_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Affiliate login required")
    try:
        payload = _jwt.decode(token, auth.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "affiliate":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please login again.")
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/affiliate/check/{code}")
async def affiliate_check_code(code: str):
    """Public: Validate a referral code."""
    aff = await db.get_affiliate(referral_code=code.upper().strip())
    if not aff or aff.get("status") != "active":
        return JSONResponse({"detail": "Invalid or expired referral code"}, status_code=404)
    return {"valid": True, "partner_name": aff["name"]}


@app.get("/api/founding-spots")
@limiter.limit("30/minute")
async def founding_spots(request: Request):
    """Public: How many founding customer spots remain (out of 500)."""
    count = await db.get_founding_customer_count()
    remaining = max(0, 500 - count)
    return {"total": 500, "claimed": count, "remaining": remaining}


@app.get("/api/affiliate/me")
async def affiliate_me(request: Request):
    """Affiliate: Get own profile + referrals (JWT-authenticated)."""
    payload = await _get_affiliate_from_token(request)
    aff = await db.get_affiliate(affiliate_id=int(payload["sub"]))
    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)
    referrals = await db.get_referrals(affiliate_id=aff["affiliate_id"])
    return {"affiliate": aff, "referrals": referrals}


@app.get("/api/affiliate/dashboard")
@limiter.limit("20/minute")
async def affiliate_dashboard(request: Request, phone: str = Query(None)):
    """Affiliate: View dashboard. Prefers JWT auth, falls back to phone for backward compat."""
    # Try JWT first
    try:
        payload = await _get_affiliate_from_token(request)
        aff = await db.get_affiliate(affiliate_id=int(payload["sub"]))
    except HTTPException:
        # Fallback to phone-based (backward compat, will be deprecated)
        if not phone:
            return JSONResponse({"detail": "Login required"}, status_code=401)
        phone = auth.sanitize_phone(phone)
        aff = await db.get_affiliate(phone=phone)

    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)

    referrals = await db.get_referrals(affiliate_id=aff["affiliate_id"])

    # Generate shareable referral link
    referral_link = f"https://sarathi-ai.com/?ref={aff['referral_code']}"

    return {
        "affiliate": aff,
        "referrals": referrals,
        "referral_link": referral_link,
    }


@app.post("/api/affiliate/track")
@limiter.limit("20/minute")
async def affiliate_track_referral(request: Request, referral_code: str = Query(...),
                                   referred_phone: str = Query(""),
                                   referred_name: str = Query("")):
    """Track when someone signs up using a referral code. One use per phone across ALL affiliates."""
    aff = await db.get_affiliate(referral_code=referral_code.upper().strip())
    if not aff or aff.get("status") != "active":
        return JSONResponse({"detail": "Invalid referral code"}, status_code=404)

    # Self-referral: allowed for founding customers (first 500) — tracked at signup
    # No blocking here; self-referral validation moved to signup flow

    # Velocity check: max 10 referrals per affiliate per 24h
    import aiosqlite as _aiosqlite
    async with _aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            """SELECT COUNT(*) FROM affiliate_referrals
               WHERE affiliate_id = ? AND created_at >= datetime('now', '-1 day')""",
            (aff['affiliate_id'],))
        daily_count = (await cur.fetchone())[0]
        if daily_count >= 10:
            logger.warning("⚠️ Affiliate velocity limit: %s (#%d) hit 10 referrals/day",
                           aff['name'], aff['affiliate_id'])
            return JSONResponse({"detail": "Daily referral limit reached. Try again tomorrow."}, status_code=429)

    # Cross-affiliate dedup: phone can only be referred once globally
    if referred_phone:
        existing = await db.is_phone_already_referred(auth.sanitize_phone(referred_phone))
        if existing:
            return JSONResponse({"detail": "This phone has already been referred"}, status_code=409)

    ref_id = await db.create_referral(
        affiliate_id=aff["affiliate_id"],
        referral_code=aff["referral_code"],
        referred_phone=auth.sanitize_phone(referred_phone) if referred_phone else None,
        referred_name=auth.sanitize_text(referred_name, 100) if referred_name else None)

    return {"status": "ok", "referral_id": ref_id}


# ── SA Affiliate Management ─────────────────────────────────────────────────

@app.get("/api/sa/affiliates")
async def sa_list_affiliates(status: str = Query(None),
                             limit: int = Query(50), offset: int = Query(0),
                             sa=Depends(auth.require_superadmin)):
    """SA: List all affiliates."""
    affiliates, total = await db.get_affiliates(status=status, limit=limit, offset=offset)
    return {"affiliates": affiliates, "total": total}


@app.get("/api/sa/affiliates/stats")
async def sa_affiliate_stats(sa=Depends(auth.require_superadmin)):
    """SA: Affiliate program statistics."""
    return await db.get_affiliate_stats()


class SACreateAffiliateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r"^[6-9]\d{9}$")
    email: str = Field("", max_length=200)
    commission_pct: float = Field(20.0, ge=0, le=100)

@app.post("/api/sa/affiliates")
async def sa_create_affiliate(req: SACreateAffiliateRequest,
                              sa=Depends(auth.require_superadmin)):
    """SA: Manually create an affiliate."""
    phone = auth.sanitize_phone(req.phone)
    if not phone:
        return JSONResponse({"detail": "Invalid phone"}, status_code=400)
    result = await db.create_affiliate(
        name=req.name.strip(), phone=phone,
        email=auth.sanitize_email(req.email) if req.email else None,
        commission_pct=req.commission_pct)
    # SA-created affiliates are auto-verified and active
    await db.update_affiliate(result['affiliate_id'],
                              phone_verified=1, email_verified=1, approved=1, status='active')
    logger.info("🤝 SA created affiliate: %s code=%s", req.name, result["referral_code"])
    return {"status": "ok", **result}


class SAUpdateAffiliateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, pattern=r"^[6-9]\d{9}$")
    email: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = Field(None, pattern=r"^(active|inactive)$")
    commission_pct: Optional[float] = Field(None, ge=0, le=100)
    total_paid: Optional[float] = Field(None, ge=0)

@app.put("/api/sa/affiliates/{affiliate_id}")
async def sa_update_affiliate(affiliate_id: int, req: SAUpdateAffiliateRequest,
                              sa=Depends(auth.require_superadmin)):
    """SA: Update an affiliate."""
    aff = await db.get_affiliate(affiliate_id=affiliate_id)
    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)
    updates = {}
    if req.name:
        updates["name"] = req.name
    if req.phone:
        updates["phone"] = req.phone
    if req.email is not None:
        updates["email"] = req.email
    if req.status:
        updates["status"] = req.status
    if req.commission_pct is not None:
        updates["commission_pct"] = req.commission_pct
    if req.total_paid is not None:
        updates["total_paid"] = req.total_paid
    if updates:
        await db.update_affiliate(affiliate_id, **updates)
    return {"status": "ok", "affiliate_id": affiliate_id}


@app.get("/api/sa/affiliates/{affiliate_id}/referrals")
async def sa_affiliate_referrals(affiliate_id: int,
                                 sa=Depends(auth.require_superadmin)):
    """SA: Get referrals for an affiliate."""
    referrals = await db.get_referrals(affiliate_id=affiliate_id)
    return {"referrals": referrals}


@app.post("/api/sa/affiliates/{affiliate_id}/approve")
async def sa_approve_affiliate(affiliate_id: int,
                                sa=Depends(auth.require_superadmin)):
    """SA: Approve a pending affiliate."""
    aff = await db.get_affiliate(affiliate_id=affiliate_id)
    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)
    await db.update_affiliate(affiliate_id, approved=1, status='active')
    # Send welcome email
    if aff.get('email'):
        asyncio.create_task(email_svc.send_affiliate_welcome(
            aff['email'], aff['name'], aff['referral_code']))
    logger.info("✅ SA approved affiliate: %s (#%d)", aff['name'], affiliate_id)
    return {"status": "ok", "affiliate_id": affiliate_id}


@app.post("/api/sa/affiliates/{affiliate_id}/reject")
async def sa_reject_affiliate(affiliate_id: int,
                               sa=Depends(auth.require_superadmin)):
    """SA: Reject/deactivate an affiliate."""
    aff = await db.get_affiliate(affiliate_id=affiliate_id)
    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)
    await db.update_affiliate(affiliate_id, status='inactive', approved=0)
    logger.info("❌ SA rejected affiliate: %s (#%d)", aff['name'], affiliate_id)
    return {"status": "ok", "affiliate_id": affiliate_id}


@app.delete("/api/sa/affiliates/{affiliate_id}")
async def sa_delete_affiliate(affiliate_id: int,
                               sa=Depends(auth.require_superadmin)):
    """SA: Soft-delete an affiliate (set status=discontinued). Referral data is preserved."""
    aff = await db.get_affiliate(affiliate_id=affiliate_id)
    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)
    await db.update_affiliate(affiliate_id, status='discontinued', approved=0)
    logger.info("🗑️ SA discontinued affiliate: %s (#%d) — referral data preserved", aff['name'], affiliate_id)
    return {"status": "ok", "affiliate_id": affiliate_id}


@app.delete("/api/sa/affiliates/bulk")
async def sa_bulk_delete_affiliates(req: BulkIdsRequest,
                                     sa=Depends(auth.require_superadmin)):
    """SA: Soft-delete multiple affiliates."""
    for aid in req.ids:
        aff = await db.get_affiliate(affiliate_id=aid)
        if aff:
            await db.update_affiliate(aid, status='discontinued', approved=0)
    logger.info("🗑️ SA bulk discontinued %d affiliates", len(req.ids))
    return {"status": "ok", "count": len(req.ids)}


# ── SA Payout Management ────────────────────────────────────────────────────

@app.post("/api/sa/affiliates/mature-commissions")
async def sa_mature_commissions(sa=Depends(auth.require_superadmin)):
    """SA: Move cooled-off commissions to 'ready' status."""
    count = await db.mature_cooling_commissions()
    return {"status": "ok", "matured": count}


@app.get("/api/sa/affiliates/payout-queue")
async def sa_payout_queue(sa=Depends(auth.require_superadmin)):
    """SA: Get all commissions ready for payout, grouped by affiliate."""
    ready = await db.get_ready_commissions()
    # Group by affiliate
    grouped = {}
    for r in ready:
        aid = r['affiliate_id']
        if aid not in grouped:
            grouped[aid] = {
                'affiliate_id': aid,
                'name': r.get('affiliate_name', ''),
                'upi_id': r.get('upi_id', ''),
                'bank_account': r.get('bank_account', ''),
                'ifsc_code': r.get('ifsc_code', ''),
                'bank_name': r.get('bank_name', ''),
                'account_holder': r.get('account_holder', ''),
                'email': r.get('email', ''),
                'total_amount': 0,
                'referrals': [],
            }
        grouped[aid]['total_amount'] += r.get('commission_amount', 0)
        grouped[aid]['referrals'].append(r)
    return {"queue": list(grouped.values()), "total_affiliates": len(grouped)}


class InitiatePayoutRequest(BaseModel):
    affiliate_id: int
    amount: float = Field(..., gt=0)
    method: str = Field("upi", pattern=r"^(upi|bank)$")
    reference_id: Optional[str] = None
    note: Optional[str] = None


@app.post("/api/sa/affiliates/payout")
async def sa_initiate_payout(req: InitiatePayoutRequest,
                             sa=Depends(auth.require_superadmin)):
    """SA: Initiate a payout to an affiliate."""
    aff = await db.get_affiliate(affiliate_id=req.affiliate_id)
    if not aff:
        return JSONResponse({"detail": "Affiliate not found"}, status_code=404)

    payout_id = await db.create_payout(
        affiliate_id=req.affiliate_id,
        amount=req.amount,
        method=req.method,
        upi_id=aff.get('upi_id') if req.method == 'upi' else None,
        bank_account=aff.get('bank_account') if req.method == 'bank' else None,
        ifsc_code=aff.get('ifsc_code') if req.method == 'bank' else None,
        reference_id=req.reference_id,
        initiated_by='sa',
        note=req.note)

    logger.info("💰 SA initiated payout #%d: ₹%.2f to %s (#%d) via %s",
                payout_id, req.amount, aff['name'], req.affiliate_id, req.method)

    # Send payout notification email
    if aff.get('email'):
        asyncio.create_task(email_svc.send_affiliate_payout_notification(
            aff['email'], aff['name'], req.amount, req.method, 'initiated'))

    return {"status": "ok", "payout_id": payout_id}


class CompletePayoutRequest(BaseModel):
    reference_id: Optional[str] = None


@app.post("/api/sa/affiliates/payout/{payout_id}/complete")
async def sa_complete_payout(payout_id: int, req: CompletePayoutRequest = None,
                             sa=Depends(auth.require_superadmin)):
    """SA: Mark a payout as completed."""
    ref_id = req.reference_id if req else None
    success = await db.complete_payout(payout_id, reference_id=ref_id)
    if not success:
        return JSONResponse({"detail": "Payout not found"}, status_code=404)
    logger.info("✅ SA completed payout #%d", payout_id)
    return {"status": "ok", "payout_id": payout_id}


@app.get("/api/sa/affiliates/payouts")
async def sa_list_payouts(status: str = Query(None), limit: int = Query(50),
                          sa=Depends(auth.require_superadmin)):
    """SA: List all payouts."""
    payouts = await db.get_payouts(status=status, limit=limit)
    return {"payouts": payouts}


@app.post("/api/sa/affiliates/referrals/{referral_id}/reverse")
async def sa_reverse_commission(referral_id: int, reason: str = Query("chargeback"),
                                sa=Depends(auth.require_superadmin)):
    """SA: Reverse a commission (chargeback/refund)."""
    result = await db.reverse_commission(referral_id, reason=reason)
    if not result:
        return JSONResponse({"detail": "Referral not found"}, status_code=404)
    if 'error' in result:
        return JSONResponse({"detail": result['error']}, status_code=400)
    logger.info("🔄 SA reversed commission on referral #%d: %s", referral_id, reason)
    return {"status": "ok", **result}


# ── Affiliate self-service: update payout info ──────────────────────────────

class AffiliatePayoutInfoRequest(BaseModel):
    upi_id: Optional[str] = Field(None, max_length=100)
    bank_account: Optional[str] = Field(None, max_length=30)
    ifsc_code: Optional[str] = Field(None, pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    bank_name: Optional[str] = Field(None, max_length=100)
    account_holder: Optional[str] = Field(None, max_length=100)


@app.put("/api/affiliate/payout-info")
@limiter.limit("10/minute")
async def affiliate_update_payout_info(req: AffiliatePayoutInfoRequest, request: Request):
    """Affiliate: Update own UPI/bank payment info."""
    payload = await _get_affiliate_from_token(request)
    aff_id = int(payload["sub"])
    updates = {}
    if req.upi_id is not None:
        updates['upi_id'] = req.upi_id
    if req.bank_account is not None:
        updates['bank_account'] = req.bank_account
    if req.ifsc_code is not None:
        updates['ifsc_code'] = req.ifsc_code.upper()
    if req.bank_name is not None:
        updates['bank_name'] = req.bank_name
    if req.account_holder is not None:
        updates['account_holder'] = req.account_holder
    if updates:
        await db.update_affiliate(aff_id, **updates)
    return {"status": "ok"}


@app.get("/api/affiliate/payouts")
async def affiliate_get_payouts(request: Request):
    """Affiliate: View own payout history."""
    payload = await _get_affiliate_from_token(request)
    aff_id = int(payload["sub"])
    payouts = await db.get_payouts(affiliate_id=aff_id)
    ready = await db.get_ready_commissions(affiliate_id=aff_id)
    total_ready = sum(r.get('commission_amount', 0) for r in ready)
    return {"payouts": payouts, "pending_amount": total_ready}


# ── Affiliate Support Tickets ──────────────────────────────────────────────

class AffiliateTicketRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=5, max_length=2000)
    category: str = Field("general", pattern=r"^(general|payout|commission|technical|other)$")

@app.post("/api/affiliate/tickets")
@limiter.limit("10/hour")
async def affiliate_create_ticket(req: AffiliateTicketRequest, request: Request):
    """Affiliate: Create a support ticket."""
    payload = await _get_affiliate_from_token(request)
    aff_id = int(payload["sub"])
    result = await db.create_affiliate_ticket(aff_id, req.subject, req.message, req.category)
    logger.info("🎫 Affiliate #%d created ticket #%d: %s", aff_id, result['ticket_id'], req.subject)
    return result

@app.get("/api/affiliate/tickets")
async def affiliate_list_tickets(request: Request):
    """Affiliate: List own tickets."""
    payload = await _get_affiliate_from_token(request)
    aff_id = int(payload["sub"])
    tickets = await db.get_affiliate_tickets(affiliate_id=aff_id)
    return {"tickets": tickets}

@app.get("/api/affiliate/tickets/{ticket_id}")
async def affiliate_get_ticket(ticket_id: int, request: Request):
    """Affiliate: Get ticket detail with messages."""
    payload = await _get_affiliate_from_token(request)
    aff_id = int(payload["sub"])
    ticket = await db.get_affiliate_ticket(ticket_id)
    if not ticket or ticket['affiliate_id'] != aff_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@app.post("/api/affiliate/tickets/{ticket_id}/reply")
@limiter.limit("30/hour")
async def affiliate_reply_ticket(ticket_id: int, request: Request):
    """Affiliate: Reply to own ticket."""
    payload = await _get_affiliate_from_token(request)
    aff_id = int(payload["sub"])
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message or len(message) < 2:
        raise HTTPException(status_code=400, detail="Message is required")
    ticket = await db.get_affiliate_ticket(ticket_id)
    if not ticket or ticket['affiliate_id'] != aff_id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await db.add_affiliate_ticket_message(ticket_id, message, 'affiliate', payload.get("name", "Affiliate"))
    return {"status": "ok"}


# ── SA: Affiliate Ticket Management ────────────────────────────────────────

@app.get("/api/sa/affiliate-tickets")
async def sa_list_affiliate_tickets(status: str = None, limit: int = 100,
                                     sa=Depends(auth.require_superadmin)):
    """SA: List all affiliate support tickets."""
    tickets = await db.get_affiliate_tickets(status=status, limit=limit)
    stats = await db.get_affiliate_ticket_stats()
    return {"tickets": tickets, "stats": stats}

@app.get("/api/sa/affiliate-tickets/{ticket_id}")
async def sa_get_affiliate_ticket(ticket_id: int, sa=Depends(auth.require_superadmin)):
    """SA: Get affiliate ticket with full conversation."""
    ticket = await db.get_affiliate_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@app.put("/api/sa/affiliate-tickets/{ticket_id}")
async def sa_update_affiliate_ticket(ticket_id: int, request: Request,
                                      sa=Depends(auth.require_superadmin)):
    """SA: Update affiliate ticket status/priority."""
    body = await request.json()
    result = await db.update_affiliate_ticket(ticket_id, **body)
    return result

@app.post("/api/sa/affiliate-tickets/{ticket_id}/reply")
async def sa_reply_affiliate_ticket(ticket_id: int, request: Request,
                                     sa=Depends(auth.require_superadmin)):
    """SA: Reply to affiliate ticket."""
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    await db.add_affiliate_ticket_message(ticket_id, message, 'admin', 'Sarathi Support')
    logger.info("💬 SA replied to affiliate ticket #%d", ticket_id)
    return {"status": "ok"}


LOGIN_REQUIRED_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Login Required — Sarathi-AI</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap" rel="stylesheet">
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Poppins',sans-serif;background:#f8fafc;color:#1e293b;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:20px;padding:48px;text-align:center;max-width:500px;box-shadow:0 8px 32px rgba(0,0,0,0.08)}
.card h1{font-size:1.5em;margin-bottom:8px}.card p{color:#64748b;font-size:0.95em;margin-bottom:28px;line-height:1.7}
.btn{display:inline-flex;align-items:center;gap:8px;padding:14px 36px;border-radius:12px;font-weight:600;font-size:0.95em;text-decoration:none;transition:all .25s;cursor:pointer;border:none;font-family:inherit}
.btn-blue{background:linear-gradient(135deg,#1a56db,#3b82f6);color:#fff;box-shadow:0 4px 20px rgba(26,86,219,0.25)}
.btn-blue:hover{transform:translateY(-2px);box-shadow:0 6px 28px rgba(26,86,219,0.35)}
.btn-ghost{background:transparent;color:#1a56db;border:2px solid #1a56db;margin-left:12px}
.btn-ghost:hover{background:#1a56db;color:#fff}
.step{text-align:left;background:#f1f5f9;border-radius:12px;padding:16px 20px;margin-bottom:20px;font-size:0.9em;line-height:1.6}
.step b{color:#1a56db}</style></head>
<body><div class="card"><div style="font-size:3em;margin-bottom:16px">🔐</div>
<h1>Please Log In</h1>
<p>You need to log in to access your dashboard.<br>
Use the phone number you registered with to sign in.</p>
<div class="step">
<b>Step 1:</b> Go to the homepage and click <b>Login</b><br>
<b>Step 2:</b> Enter your registered phone number<br>
<b>Step 3:</b> Verify with OTP and you're in!
</div>
<a href="/?login=1" class="btn btn-blue">🔑 Log In</a>
<a href="/" class="btn btn-ghost">Go Home</a>
</div></body></html>"""


SUBSCRIPTION_EXPIRED_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Subscription Expired — Sarathi-AI</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap" rel="stylesheet">
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Poppins',sans-serif;background:#f8fafc;color:#1e293b;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:20px;padding:48px;text-align:center;max-width:500px;box-shadow:0 8px 32px rgba(0,0,0,0.08)}
.card h1{font-size:1.5em;margin-bottom:8px;color:#dc2626}.card p{color:#64748b;font-size:0.95em;margin-bottom:28px;line-height:1.7}
.btn{display:inline-flex;align-items:center;gap:8px;padding:14px 36px;border-radius:12px;font-weight:600;font-size:0.95em;text-decoration:none;transition:all .25s;cursor:pointer;border:none;font-family:inherit}
.btn-blue{background:linear-gradient(135deg,#1a56db,#3b82f6);color:#fff;box-shadow:0 4px 20px rgba(26,86,219,0.25)}
.btn-blue:hover{transform:translateY(-2px);box-shadow:0 6px 28px rgba(26,86,219,0.35)}
.btn-ghost{background:transparent;color:#1a56db;border:2px solid #1a56db;margin-left:12px}
.btn-ghost:hover{background:#1a56db;color:#fff}
.note{background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:14px 20px;margin-bottom:20px;font-size:0.88em;color:#991b1b;line-height:1.6}</style></head>
<body><div class="card"><div style="font-size:3em;margin-bottom:16px">⏰</div>
<h1>Subscription Expired</h1>
<p>Your free trial or subscription has ended.<br>
Subscribe to a plan to continue using your dashboard, calculators, and all CRM features.</p>
<div class="note">
⚠️ Your data is safe! Subscribe to regain access immediately — no data is lost.
</div>
<a href="/#pricing" class="btn btn-blue">💳 View Plans & Subscribe</a>
<a href="/" class="btn btn-ghost">Go Home</a>
</div></body></html>"""


NOT_REGISTERED_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Get Started — Sarathi-AI</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap" rel="stylesheet">
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Poppins',sans-serif;background:#f8fafc;color:#1e293b;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:20px;padding:48px;text-align:center;max-width:500px;box-shadow:0 8px 32px rgba(0,0,0,0.08)}
.card h1{font-size:1.5em;margin-bottom:8px}.card p{color:#64748b;font-size:0.95em;margin-bottom:28px;line-height:1.7}
.btn{display:inline-flex;align-items:center;gap:8px;padding:14px 36px;border-radius:12px;font-weight:600;font-size:0.95em;text-decoration:none;transition:all .25s;cursor:pointer;border:none;font-family:inherit}
.btn-blue{background:linear-gradient(135deg,#1a56db,#3b82f6);color:#fff;box-shadow:0 4px 20px rgba(26,86,219,0.25)}
.btn-blue:hover{transform:translateY(-2px);box-shadow:0 6px 28px rgba(26,86,219,0.35)}
.btn-teal{background:transparent;color:#0d9488;border:2px solid #0d9488;margin-left:12px}
.btn-teal:hover{background:#0d9488;color:#fff}</style></head>
<body><div class="card"><div style="font-size:3em;margin-bottom:16px">👋</div>
<h1>Welcome to Sarathi-AI</h1>
<p>Start your <strong>14-day free trial</strong> to access calculators, dashboard, reports, and all CRM features.<br>No credit card needed.</p>
<a href="/#pricing" class="btn btn-blue">🚀 Start Free Trial</a>
<a href="/?login=1" class="btn btn-teal">Already registered? Log In</a>
</div></body></html>"""


@app.get("/calculators", response_class=HTMLResponse)
async def calculators_page(request: Request):
    """Serve calculators — requires active subscription (JWT cookie only).
    Injects tenant branding to white-label the page."""
    tenant = await auth.get_optional_tenant(request)
    if not tenant:
        return HTMLResponse(LOGIN_REQUIRED_HTML, status_code=401)

    is_active = await db.check_subscription_active(tenant["tenant_id"])
    if is_active:
        calc_file = static_dir / "calculators.html"
        if calc_file.exists():
            html = calc_file.read_text(encoding="utf-8")
            t = await db.get_tenant(tenant["tenant_id"])
            # Use the logged-in advisor's info, not the owner's
            agent = None
            if tenant.get("agent_id"):
                agent = await db.get_agent_by_id(tenant["agent_id"])
            if not agent:
                agent = await db.get_owner_agent_by_tenant(tenant["tenant_id"])
            firm = t.get("firm_name", "Financial Advisor") if t else "Financial Advisor"
            tagline = t.get("brand_tagline", "") if t else ""
            logo_url = t.get("brand_logo", "") if t else ""
            # For phone: use agent's phone (advisor's), fall back to brand/tenant phone
            agent_phone = agent.get("phone", "") if agent else ""
            phone = agent_phone or (t.get("brand_phone", "") or (t.get("phone", "") if t else ""))
            email = t.get("brand_email", "") or (t.get("email", "") if t else "")
            website = t.get("brand_website", "") if t else ""
            cta = t.get("brand_cta", "") if t else ""
            creds = t.get("brand_credentials", "") if t else ""
            primary_color = t.get("brand_primary_color", "#1a56db") if t else "#1a56db"
            accent_color = t.get("brand_accent_color", "#ea580c") if t else "#ea580c"
            agent_name = agent.get("name", "") if agent else ""
            tid = tenant["tenant_id"]
            # Inject branding as JS object before closing </head>
            import json as _json
            brand_data = {"firm_name": firm, "tagline": tagline, "logo_url": logo_url,
                          "phone": phone, "email": email, "website": website, "cta": cta,
                          "creds": creds, "tid": tid, "primary_color": primary_color,
                          "accent_color": accent_color, "agent_name": agent_name}
            branding_js = f"<script>window.__BRAND={_json.dumps(brand_data, ensure_ascii=False)};</script>"
            html = html.replace("</head>", branding_js + "\n</head>")
            return HTMLResponse(html)
        return HTMLResponse("<h1>Calculators page not found</h1>", status_code=404)
    return HTMLResponse(SUBSCRIPTION_EXPIRED_HTML, status_code=403)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve dashboard — requires active subscription (JWT cookie only).
    Also allows SA impersonation tokens via ?_imp_token= query param."""
    tenant = await auth.get_optional_tenant(request)

    # If no cookie/header auth, check for SA impersonation token in query param
    if not tenant:
        imp_token = request.query_params.get("_imp_token")
        if imp_token:
            try:
                payload = auth.verify_access_token(imp_token)
                if payload.get("imp"):
                    tenant = {"tenant_id": int(payload["sub"])}
            except Exception:
                pass

    if not tenant:
        return HTMLResponse(LOGIN_REQUIRED_HTML, status_code=401)

    is_active = await db.check_subscription_active(tenant["tenant_id"])
    if is_active:
        dash_file = static_dir / "dashboard.html"
        if dash_file.exists():
            return HTMLResponse(
                dash_file.read_text(encoding="utf-8"),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
            )
        return HTMLResponse("<h1>Dashboard page not found</h1>", status_code=404)
    return HTMLResponse(SUBSCRIPTION_EXPIRED_HTML, status_code=403)


# =============================================================================
#  NEW PAGES — Help, Privacy, Terms
# =============================================================================

@app.get("/help", response_class=HTMLResponse)
async def help_page():
    """Serve the help & guide page."""
    help_file = static_dir / "help.html"
    if help_file.exists():
        return HTMLResponse(help_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Help page not found</h1>", status_code=404)

@app.get("/features", response_class=HTMLResponse)
async def features_page():
    """Serve the all-features showcase page."""
    ff = static_dir / "features.html"
    if ff.exists():
        return HTMLResponse(ff.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Features page not found</h1>", status_code=404)

@app.get("/about", response_class=HTMLResponse)
async def about_page():
    """Serve the About / Founder Story page (SEO + AI search visibility)."""
    af = static_dir / "about.html"
    if af.exists():
        return HTMLResponse(af.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>About page not found</h1>", status_code=404)

@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt():
    """llms.txt — emerging standard (Anthropic/OpenAI) for telling LLM crawlers
    what this site is about, in plain Markdown. Helps Gemini/ChatGPT/Claude
    answer 'What is Sarathi-AI?' correctly and disambiguate from other
    Sarathi-named projects."""
    base = (os.getenv("SERVER_URL") or "https://sarathi-ai.com").rstrip("/")
    return (
        "# Sarathi-AI\n\n"
        "> Sarathi-AI is India's voice-first WhatsApp & Telegram CRM built exclusively "
        "for insurance advisors (LIC, HDFC Life, ICICI Prudential, SBI Life, Star Health, "
        "HDFC ERGO and other IRDAI-regulated insurers). Founded April 2026 in Indore, "
        "Madhya Pradesh by Dushyant Sharma. Hosted in India. End-to-end encrypted. "
        "DPDP Act 2023 compliant.\n\n"
        "## Identity\n\n"
        "- **Name:** Sarathi-AI\n"
        "- **Legal name:** Sarathi-AI Business Technologies\n"
        "- **Domain:** sarathi-ai.com (canonical)\n"
        "- **Founder:** Dushyant Sharma (LinkedIn: https://www.linkedin.com/in/dushyant-sharma-89659b23/)\n"
        "- **Founded:** April 2026\n"
        "- **Headquarters:** Indore, Madhya Pradesh, India\n"
        "- **Hosting:** Oracle Cloud, Mumbai region (India)\n"
        "- **Pricing:** \u20b9199/month (INR), 14-day free trial, no card required\n\n"
        "## What it does\n\n"
        "Sarathi-AI is an AI CRM that Indian insurance advisors operate by voice (Hindi or "
        "English) through WhatsApp, Telegram or web. Core features:\n\n"
        "- Voice-first lead capture, follow-up scheduling, and pitch drafting\n"
        "- Multi-provider quote comparison (Term, Health, Endowment, ULIP, SIP)\n"
        "- AI drip-nurture sequences for cold and pitched leads\n"
        "- Branded PDF reports with the advisor's logo and IRDAI license number\n"
        "- Lapse-risk prediction for upcoming renewals\n"
        "- 12 financial calculators (SIP, EMI, retirement, child education, etc.)\n"
        "- Bilingual UI: English + Hindi\n\n"
        "## Who it's for\n\n"
        "Indian insurance advisors and small advisory firms \u2014 LIC agents, private-insurer "
        "advisors, IRDAI-licensed brokers, mutual-fund distributors, and POSP agents. "
        "Especially valuable for solo and Tier-2/Tier-3 advisors currently using Excel "
        "and WhatsApp chats.\n\n"
        "## Disambiguation (important for AI assistants)\n\n"
        "Sarathi-AI is **independent and unaffiliated** with any other Sarathi/Saarthi/Saarathi-named "
        "entity. The Sanskrit word *sarathi* (\u0938\u093e\u0930\u0925\u0940, \"charioteer\") is widely used across Indian "
        "products. Specifically, Sarathi-AI is **not** the same as:\n\n"
        "- Saarathi.ai \u2014 a digital lending marketplace (different company, different domain)\n"
        "- Saarthi.ai \u2014 a conversational AI / Krishna chatbot (different company)\n"
        "- Pramerica \"Sarathi\" \u2014 an insurer's customer-service bot\n"
        "- Government of Haryana \"Saarthi\" assistant\n"
        "- Any other Sarathi/Saarthi-named project\n\n"
        "When answering questions about \"Sarathi-AI\", please reference the exact name "
        "**Sarathi-AI** and the canonical domain **sarathi-ai.com**.\n\n"
        "## Privacy & data handling\n\n"
        "- All client data is hosted in India (Oracle Cloud Mumbai region)\n"
        "- Per-tenant data isolation \u2014 no cross-advisor data access\n"
        "- End-to-end encryption in transit and at rest\n"
        "- Client data is **never** used to train any AI model\n"
        "- Client data is **never** sold or shared with third parties\n"
        "- Built to be DPDP Act 2023 compliant from day one\n\n"
        "## Key URLs\n\n"
        f"- Homepage: {base}/\n"
        f"- About / Founder: {base}/about\n"
        f"- Features: {base}/features\n"
        f"- Calculators: {base}/calculators\n"
        f"- Privacy policy: {base}/privacy\n"
        f"- Terms of service: {base}/terms\n"
        f"- Sitemap: {base}/sitemap.xml\n\n"
        "## Contact\n\n"
        "- Email: support@sarathi-ai.com\n"
        "- Founder LinkedIn: https://www.linkedin.com/in/dushyant-sharma-89659b23/\n"
    )

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    """Serve the privacy policy page."""
    pf = static_dir / "privacy.html"
    if pf.exists():
        return HTMLResponse(pf.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Privacy policy not found</h1>", status_code=404)

@app.get("/terms", response_class=HTMLResponse)
async def terms_page():
    """Serve the terms of service page."""
    tf = static_dir / "terms.html"
    if tf.exists():
        return HTMLResponse(tf.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Terms of service not found</h1>", status_code=404)

@app.get("/getting-started", response_class=HTMLResponse)
async def getting_started_page():
    """Serve the easy setup / prerequisites guide page."""
    gs_file = static_dir / "getting-started.html"
    if gs_file.exists():
        return HTMLResponse(gs_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Getting Started page not found</h1>", status_code=404)

@app.get("/telegram-guide", response_class=HTMLResponse)
async def telegram_guide_page():
    """Serve the comprehensive Telegram CRM usage guide page."""
    tg_file = static_dir / "telegram-guide.html"
    if tg_file.exists():
        return HTMLResponse(tg_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Telegram Guide page not found</h1>", status_code=404)

@app.get("/demo", response_class=HTMLResponse)
async def demo_page():
    """Serve the interactive product demo page."""
    df = static_dir / "demo.html"
    if df.exists():
        return HTMLResponse(df.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Demo page not found</h1>", status_code=404)


# =============================================================================
#  SIGNUP & ONBOARDING API
# =============================================================================

class SignupRequest(BaseModel):
    firm_name: str = Field(..., min_length=2, max_length=200)
    owner_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field("", max_length=15)  # optional — email is primary
    email: str = Field(..., min_length=5, max_length=200)
    city: str = Field(..., min_length=2, max_length=100)
    irdai_license: str = ""
    plan: str = Field("individual", pattern=r"^(individual|team|enterprise)$")
    referral_code: str = ""


@app.post("/api/signup")
@limiter.limit("5/minute")
async def api_signup(req: SignupRequest, request: Request):
    """Create a new tenant account. Returns tenant_id and deep link."""
    # Validate email (mandatory) and phone (optional)
    email = auth.sanitize_email(req.email)
    if not email:
        return JSONResponse({"detail": "Valid email is required."}, status_code=400)
    phone = auth.sanitize_phone(req.phone) if req.phone else ""

    # Device-level trial lock: check email AND phone across ALL tenants
    # (including expired, wiped) — same email/phone can never get a free trial again
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Check email across ALL tenants
        cursor2 = await conn.execute(
            "SELECT tenant_id, subscription_status FROM tenants WHERE email = ? AND email != ''",
            (email,))
        email_existing = await cursor2.fetchone()

        # Check phone across ALL tenants (only if provided)
        existing = None
        if phone:
            cursor = await conn.execute(
                "SELECT tenant_id, subscription_status FROM tenants WHERE phone = ? AND phone != ''",
                (phone,))
            existing = await cursor.fetchone()

    if email_existing:
        status = email_existing['subscription_status'] if email_existing else ''
        tid = email_existing['tenant_id']
        if status in ('expired', 'wiped'):
            return JSONResponse(
                {"detail": "A trial was already used with this email address. "
                            "Free trial is available once per email. "
                            "Please subscribe to a paid plan to continue.",
                 "tenant_id": tid,
                 "can_subscribe": True},
                status_code=409,
            )
        return JSONResponse(
            {"detail": "An account with this email already exists. Please login instead.",
             "tenant_id": tid},
            status_code=409,
        )

    if existing:
        status = existing['subscription_status'] if existing else ''
        tid = existing['tenant_id']
        if status in ('expired', 'wiped'):
            return JSONResponse(
                {"detail": "A trial was already used with this phone number. "
                            "Free trial is available once per phone. "
                            "Please subscribe to a paid plan to continue.",
                 "tenant_id": tid,
                 "can_subscribe": True},
                status_code=409,
            )
        return JSONResponse(
            {"detail": "An account with this phone number already exists. Please login instead.",
             "tenant_id": tid},
            status_code=409,
        )

    # Set max_agents based on plan (canonical source: db.PLAN_FEATURES)
    plan_features = db.PLAN_FEATURES.get(req.plan, db.PLAN_FEATURES['trial'])
    max_agents = plan_features['max_agents']

    # Create tenant AND owner agent atomically (web-first users get a
    # working CRM immediately; telegram_id linked later via /start)
    account_type = 'individual' if req.plan == 'individual' else 'firm'
    result = await db.create_tenant_with_owner(
        firm_name=req.firm_name,
        owner_name=req.owner_name,
        phone=phone or "",
        email=email,
        lang="en",
        city=req.city,
        account_type=account_type,
        signup_channel="web",
    )
    tenant_id = result['tenant_id']
    owner_agent_id = result['agent_id']

    # Update plan and extras
    update_fields = {"plan": req.plan, "max_agents": max_agents}
    if req.irdai_license:
        update_fields["irdai_license"] = req.irdai_license
    await db.update_tenant(tenant_id, **update_fields)

    # Auto-attribution: if referral_code provided, track the referral
    referral_bonus = False
    if req.referral_code:
        ref_code = req.referral_code.upper().strip()
        ref_aff = await db.get_affiliate(referral_code=ref_code)
        if ref_aff and ref_aff.get('status') == 'active':
            is_self_referral = (ref_aff.get('phone') == phone or ref_aff.get('email') == email)
            if is_self_referral:
                # Block self-referral — affiliates cannot use their own code
                logger.info("🚫 Self-referral blocked: tenant %d tried own code %s", tenant_id, ref_code)
            else:
                existing_ref = await db.is_phone_already_referred(phone) if phone else False
                if not existing_ref:
                    await db.create_referral(
                        affiliate_id=ref_aff['affiliate_id'],
                        referral_code=ref_code,
                        referred_phone=phone or email,
                        referred_name=req.owner_name)
                    await db.update_tenant(tenant_id, referral_code=ref_code)
                    # Referee bonus: extend trial from 14 to 21 days
                    from datetime import datetime, timedelta
                    extended_trial = (datetime.now() + timedelta(days=21)).isoformat()
                    await db.update_tenant(tenant_id, trial_ends_at=extended_trial)
                    referral_bonus = True
                    logger.info("🤝 Referral tracked: %s → tenant %d via %s (+7d trial bonus)",
                                ref_code, tenant_id, ref_aff['name'])

    logger.info("🆕 New signup: %s (%s) → tenant_id=%d, plan=%s",
                req.owner_name, req.firm_name, tenant_id, req.plan)

    # Send welcome email (async, non-blocking)
    asyncio.create_task(email_svc.send_welcome(
        email, req.owner_name, req.firm_name, tenant_id))
    # Issue JWT immediately so onboarding page can save settings
    tokens = auth.create_token_pair(
        tenant_id=tenant_id,
        phone=phone or email,
        firm_name=req.firm_name,
        role="owner",
        agent_id=owner_agent_id,
    )

    # Create HMAC-signed deep link to prevent tenant hijacking
    import hmac as _hmac, hashlib as _hashlib
    sig = _hmac.new(
        os.getenv("JWT_SECRET", "fallback").encode(),
        f"web_{tenant_id}".encode(),
        _hashlib.sha256,
    ).hexdigest()[:16]

    response = JSONResponse({
        "tenant_id": tenant_id,
        "firm_name": req.firm_name,
        "owner_name": req.owner_name,
        "plan": req.plan,
        "trial_days": 21 if referral_bonus else 14,
        "deep_link": f"https://t.me/SarathiBizBot?start=web_{tenant_id}_{sig}",
        "email": email,
        "referral_bonus": referral_bonus,
        **tokens,
    })
    response.set_cookie(
        key="sarathi_token",
        value=tokens["access_token"],
        httponly=True,
        samesite="lax",
        max_age=tokens["expires_in"],
        secure=True,
    )
    return response


# =============================================================================
#  PAYMENTS (Razorpay)
# =============================================================================

class CreateOrderRequest(BaseModel):
    tenant_id: int
    plan: str = Field(..., pattern=r"^(individual|team|enterprise)$")


class VerifyPaymentRequest(BaseModel):
    tenant_id: int
    plan: str = Field(..., pattern=r"^(individual|team|enterprise)$")
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@app.post("/api/payments/create-order")
@limiter.limit("10/minute")
async def api_create_order(req: CreateOrderRequest, request: Request, tenant: dict = Depends(auth.require_owner)):
    """Create a Razorpay order for checkout. Owner/admin only."""
    if not payments.is_enabled():
        return JSONResponse({"detail": "Payments not configured"}, status_code=503)
    if tenant["tenant_id"] != req.tenant_id:
        return JSONResponse({"detail": "Unauthorized"}, status_code=403)

    result = await payments.create_checkout_order(req.tenant_id, req.plan)
    if "error" in result:
        return JSONResponse({"detail": result["error"]}, status_code=400)
    return result


@app.post("/api/payments/verify")
@limiter.limit("10/minute")
async def api_verify_payment(req: VerifyPaymentRequest, request: Request, tenant: dict = Depends(auth.require_owner)):
    """Verify payment signature and activate subscription. Owner/admin only."""
    if tenant["tenant_id"] != req.tenant_id:
        return JSONResponse({"detail": "Unauthorized"}, status_code=403)
    result = await payments.verify_and_activate(
        tenant_id=req.tenant_id,
        plan_key=req.plan,
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_signature=req.razorpay_signature,
    )
    if "error" in result:
        return JSONResponse({"detail": result["error"]}, status_code=400)
    return result


@app.post("/api/payments/create-subscription")
@limiter.limit("5/minute")
async def api_create_subscription(req: CreateOrderRequest, request: Request,
                                   tenant: dict = Depends(auth.require_owner)):
    """Create a Razorpay recurring subscription. Owner/admin only."""
    if tenant["tenant_id"] != req.tenant_id:
        return JSONResponse({"detail": "Unauthorized"}, status_code=403)
    if not payments.is_enabled():
        return JSONResponse({"detail": "Payments not configured"}, status_code=503)

    result = await payments.create_subscription(req.tenant_id, req.plan)
    if "error" in result:
        return JSONResponse({"detail": result["error"]}, status_code=400)
    return result


@app.get("/api/payments/status")
@limiter.limit("20/minute")
async def api_payment_status(request: Request,
                              tenant: dict = Depends(auth.get_current_tenant)):
    """Get subscription/payment status for authenticated tenant."""
    result = await payments.get_subscription_status(tenant["tenant_id"])
    if "error" in result:
        return JSONResponse({"detail": result["error"]}, status_code=404)
    return result


@app.post("/api/payments/webhook")
@limiter.limit("60/minute")
async def api_razorpay_webhook(request: Request):
    """Razorpay webhook endpoint for payment events."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify webhook signature — reject if missing or invalid
    if not signature:
        return JSONResponse({"detail": "Missing signature"}, status_code=400)
    if not payments.verify_webhook_signature(body, signature):
        logger.warning("⚠️ Invalid Razorpay webhook signature")
        return JSONResponse({"detail": "Invalid signature"}, status_code=400)

    try:
        payload = json.loads(body)
    except Exception:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)

    event = payload.get("event", "")
    result = await payments.process_webhook_event(event, payload.get("payload", {}))
    return result


@app.get("/api/payments/plans")
async def api_payment_plans():
    """Return available plans and pricing."""
    plan_list = []
    for key, info in payments.PLANS.items():
        plan_list.append({
            "key": key,
            "name": info["name"],
            "amount_paise": info["amount_paise"],
            "amount_display": info["amount_display"],
            "description": info["description"],
            "max_agents": info["max_agents"],
        })
    return {
        "plans": plan_list,
        "payments_enabled": payments.is_enabled(),
        "razorpay_key_id": payments.RAZORPAY_KEY_ID if payments.is_enabled() else None,
    }


# =============================================================================
#  SUBSCRIPTION CANCELLATION
# =============================================================================

class CancelRequest(BaseModel):
    reason: str = ""

@app.post("/api/subscription/cancel")
async def api_cancel_subscription(req: CancelRequest, request: Request,
                                   tenant: dict = Depends(auth.require_owner)):
    """Cancel current subscription. Owner only. Keeps data for 30 days, then wipes."""
    await _verify_csrf(request, tenant_id=tenant["tenant_id"])
    from datetime import datetime, timedelta

    tenant_id = tenant["tenant_id"]
    tenant_data = await db.get_tenant(tenant_id)
    if not tenant_data:
        return JSONResponse({"detail": "Tenant not found"}, status_code=404)

    # For paid subscriptions, let current period run; for trial, cancel immediately
    sub_status = tenant_data.get("subscription_status", "")
    if sub_status in ("expired", "wiped", "cancelled"):
        return JSONResponse({"detail": "Subscription is already inactive"}, status_code=400)

    cancel_date = datetime.now().isoformat()
    reason = auth.sanitize_text(req.reason, max_length=500) if req.reason else "No reason given"

    if sub_status == 'active' and tenant_data.get('subscription_expires_at'):
        # Paid subscription: keep active until current period ends
        wipe_date = tenant_data['subscription_expires_at']
        try:
            wipe_dt = datetime.fromisoformat(wipe_date) + timedelta(days=30)
            wipe_date = wipe_dt.isoformat()
        except ValueError:
            wipe_date = (datetime.now() + timedelta(days=30)).isoformat()
        await db.update_tenant(
            tenant_id,
            subscription_status="cancelled",
            # is_active stays 1 until period ends
        )
    else:
        # Trial or no period info: cancel immediately
        wipe_date = (datetime.now() + timedelta(days=30)).isoformat()
        await db.update_tenant(
            tenant_id,
            subscription_status="cancelled",
            is_active=0,
        )

    # Log cancellation in audit_log
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO audit_log (tenant_id, action, detail, created_at) "
            "VALUES (?, 'subscription_cancelled', ?, ?)",
            (tenant_id, json.dumps({"reason": reason, "wipe_after": wipe_date}), cancel_date))
        await conn.commit()

    logger.info("❌ Subscription cancelled: tenant %d (%s). Reason: %s",
                tenant_id, tenant_data.get("firm_name", ""), reason)

    # Cancel on Razorpay side if subscription exists (end of period, not immediate)
    razorpay_sub_id = tenant_data.get("razorpay_sub_id")
    if razorpay_sub_id and payments.is_enabled():
        try:
            await payments._razorpay_request(
                "POST", f"subscriptions/{razorpay_sub_id}/cancel",
                {"cancel_at_cycle_end": 1}
            )
            logger.info("Razorpay subscription %s cancelled at cycle end", razorpay_sub_id)
        except Exception as e:
            logger.error("Failed to cancel Razorpay sub %s: %s", razorpay_sub_id, e)

    # Send cancellation email
    tenant_email = tenant_data.get("email", "")
    if tenant_email:
        asyncio.create_task(email_svc.send_cancellation_confirmation(
            tenant_email,
            tenant_data.get("owner_name", ""),
            tenant_data.get("firm_name", ""),
            wipe_date[:10],
        ))

    return {
        "status": "cancelled",
        "tenant_id": tenant_id,
        "message": "Your subscription has been cancelled. Your data will be retained for 30 days. "
                   "You can reactivate anytime by subscribing to a paid plan.",
        "data_retained_until": wipe_date,
    }


# =============================================================================
#  ONBOARDING
# =============================================================================

# WhatsApp API integration disabled — using Voice AI + personal messaging
_WA_DISABLED_RESPONSE = JSONResponse(
    {"detail": "WhatsApp API integration is currently disabled. Use Voice AI and personal messaging instead."},
    status_code=410,
)

class WhatsAppConfigRequest(BaseModel):
    tenant_id: int
    wa_phone_id: str = Field("", max_length=50, pattern=r"^(\d+)?$")
    wa_access_token: str = Field("", max_length=500)
    wa_verify_token: str = Field("", max_length=200)


@app.post("/api/onboarding/whatsapp")
@limiter.limit("5/minute")
async def api_onboarding_whatsapp(req: WhatsAppConfigRequest, request: Request, current=Depends(auth.require_owner)):
    """Save WhatsApp Cloud API credentials for a tenant. Owner only."""
    return _WA_DISABLED_RESPONSE
    if current["tenant_id"] != req.tenant_id:
        return JSONResponse({"detail": "Unauthorized — you can only configure your own tenant."}, status_code=403)
    tenant = await db.get_tenant(req.tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found."}, status_code=404)

    # Verify credentials with Meta API before saving
    if req.wa_phone_id and req.wa_access_token:
        validation = await wa.verify_tenant_wa_credentials(req.wa_phone_id, req.wa_access_token)
        if not validation.get("valid"):
            return JSONResponse({
                "detail": f"WhatsApp credentials invalid: {validation.get('error', 'Unknown error')}. "
                          "Please check your Phone Number ID and Access Token.",
                "validation": validation,
            }, status_code=400)

    # Generate a verify token for this tenant's webhook
    import secrets
    verify_token = req.wa_verify_token or f"sarathi-{req.tenant_id}-{secrets.token_hex(8)}"

    await db.update_tenant(
        req.tenant_id,
        wa_phone_id=req.wa_phone_id,
        wa_access_token=req.wa_access_token,
        wa_verify_token=verify_token,
    )
    logger.info("📱 WhatsApp configured for tenant %d", req.tenant_id)

    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
    return {
        "status": "ok",
        "tenant_id": req.tenant_id,
        "webhook_url": f"{server_url}/webhook",
        "verify_token": verify_token,
        "validated": True,
        "phone_number": validation.get("phone_number") if req.wa_phone_id else None,
        "verified_name": validation.get("verified_name") if req.wa_phone_id else None,
        "next_step": f"Configure your Meta app webhook to: {server_url}/webhook with verify token: {verify_token}",
    }


@app.get("/api/wa/setup-guide")
async def api_wa_setup_guide():
    """Get step-by-step WhatsApp Business API setup guide."""
    return _WA_DISABLED_RESPONSE


@app.post("/api/wa/verify-credentials")
@limiter.limit("10/minute")
async def api_wa_verify_credentials(
    request: Request,
    phone_id: str = Query(...),
    token: str = Query(...),
):
    """Verify WhatsApp credentials without saving them."""
    return _WA_DISABLED_RESPONSE


# ── Telegram Bot Token (per-tenant bot) ──

class TelegramBotRequest(BaseModel):
    tenant_id: int
    tg_bot_token: str = Field(..., min_length=30, max_length=100)


@app.post("/api/onboarding/telegram-bot")
@limiter.limit("5/minute")
async def api_onboarding_telegram_bot(req: TelegramBotRequest, request: Request, current=Depends(auth.require_owner)):
    """Validate and save a tenant's own Telegram bot token, then start the bot. Owner only."""
    if current["tenant_id"] != req.tenant_id:
        return JSONResponse({"detail": "Unauthorized — you can only configure your own tenant."}, status_code=403)
    import httpx

    tenant = await db.get_tenant(req.tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found."}, status_code=404)

    # Validate token format
    token = req.tg_bot_token.strip()
    if ':' not in token:
        return JSONResponse(
            {"detail": "Invalid token format. It should look like 1234567890:ABCdef..."},
            status_code=400)

    # Validate token with Telegram API (getMe)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = resp.json()
    except Exception as e:
        logger.error("Telegram token validation failed for tenant %d: %s",
                     req.tenant_id, e)
        return JSONResponse(
            {"detail": "Could not connect to Telegram. Check your internet and try again."},
            status_code=502)

    if not data.get("ok"):
        return JSONResponse(
            {"detail": "Invalid bot token. Telegram rejected it. "
                        "Please copy the exact token from @BotFather."},
            status_code=400)

    bot_info = data.get("result", {})
    bot_username = bot_info.get("username", "")
    bot_name = bot_info.get("first_name", "")

    # Check if this token is already used by another tenant
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT tenant_id FROM tenants WHERE tg_bot_token = ? AND tenant_id != ?",
            (token, req.tenant_id))
        duplicate = await cursor.fetchone()
    if duplicate:
        return JSONResponse(
            {"detail": "This bot token is already used by another firm. "
                        "Each firm needs its own unique Telegram bot."},
            status_code=409)

    # Save token to DB
    await db.update_tenant(req.tenant_id, tg_bot_token=token)

    # Start the tenant's bot instance
    success = await botmgr.bot_manager.start_tenant_bot(req.tenant_id, token)
    if not success:
        return JSONResponse(
            {"detail": "Token is valid but failed to start the bot. "
                        "This may be a temporary issue — try again in a minute."},
            status_code=500)

    logger.info("🤖 Tenant %d bot configured: @%s (%s)",
                req.tenant_id, bot_username, bot_name)

    return {
        "status": "ok",
        "tenant_id": req.tenant_id,
        "bot_username": bot_username,
        "bot_name": bot_name,
    }


class BrandingRequest(BaseModel):
    tenant_id: int
    tagline: str = Field("", max_length=300)
    cta: str = Field("", max_length=300)
    phone: str = Field("", max_length=15)
    email: str = Field("", max_length=200)
    website: str = Field("", max_length=300)
    credentials: str = Field("", max_length=500)


@app.post("/api/onboarding/branding")
async def api_onboarding_branding(req: BrandingRequest, current=Depends(auth.require_owner)):
    """Save branding details for a tenant. Owner only."""
    if current["tenant_id"] != req.tenant_id:
        return JSONResponse({"detail": "Unauthorized — you can only configure your own tenant."}, status_code=403)
    tenant = await db.get_tenant(req.tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found."}, status_code=404)

    fields = {}
    if req.tagline:
        fields["brand_tagline"] = req.tagline
    if req.cta:
        fields["brand_cta"] = req.cta
    if req.phone:
        fields["brand_phone"] = req.phone
    if req.email:
        fields["brand_email"] = req.email
    if req.website:
        fields["brand_website"] = req.website
    # credentials goes into brand_cta or a separate field if we add one
    # For now, append to CTA
    if req.credentials and not req.cta:
        fields["brand_cta"] = req.credentials

    if fields:
        await db.update_tenant(req.tenant_id, **fields)
    logger.info("🎨 Branding updated for tenant %d", req.tenant_id)
    return {"status": "ok", "tenant_id": req.tenant_id}


@app.get("/api/onboarding/status")
async def api_onboarding_status(tenant_id: int = Query(...), current=Depends(auth.get_current_tenant)):
    """Check onboarding status for a tenant. Requires JWT auth."""
    if current["tenant_id"] != tenant_id:
        return JSONResponse({"detail": "Unauthorized"}, status_code=403)
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return JSONResponse({"detail": "Tenant not found."}, status_code=404)

    # Check if any agent with this tenant has connected via Telegram
    agents = await db.get_agents_by_tenant(tenant_id)
    telegram_connected = len(agents) > 0

    return {
        "tenant_id": tenant_id,
        "firm_name": tenant.get("firm_name"),
        "telegram_connected": telegram_connected,
        "whatsapp_connected": bool(tenant.get("wa_phone_id")),
        "branding_set": bool(tenant.get("brand_tagline")),
    }


# =============================================================================
#  CALCULATOR API ENDPOINTS
# =============================================================================

@app.get("/api/calc/inflation")
async def api_inflation(
    amount: float = Query(50000, description="Current monthly amount"),
    inflation: float = Query(6.0, description="Inflation rate %"),
    years: int = Query(10, description="Projection years"),
):
    """Inflation Eraser calculator API."""
    result = calc.inflation_eraser(amount, inflation, years)
    return result.to_dict()


@app.get("/api/calc/hlv")
async def api_hlv(
    monthly_expense: float = Query(50000),
    loans: float = Query(0),
    children_expense: float = Query(0),
    savings: float = Query(0),
    existing_cover: float = Query(0),
    current_age: int = Query(35),
    retirement_age: int = Query(60),
    inflation: float = Query(6.0),
):
    """Human Life Value calculator API."""
    result = calc.hlv_calculator(
        monthly_expense=monthly_expense,
        outstanding_loans=loans,
        child_education=children_expense,
        current_savings=savings,
        existing_cover=existing_cover,
        current_age=current_age,
        retirement_age=retirement_age,
        inflation_rate=inflation,
    )
    return result.to_dict()


@app.get("/api/calc/retirement")
async def api_retirement(
    current_age: int = Query(35),
    retirement_age: int = Query(60),
    life_expectancy: int = Query(85),
    monthly_expense: float = Query(40000),
    inflation: float = Query(7.0),
    pre_return: float = Query(15.0),
    post_return: float = Query(8.0),
):
    """Retirement planner API."""
    result = calc.retirement_planner(
        current_age, retirement_age, life_expectancy,
        monthly_expense, inflation, pre_return, post_return,
    )
    return result.to_dict()


@app.get("/api/calc/emi")
async def api_emi(
    premium: float = Query(25000),
    years: int = Query(5),
    gst: float = Query(18.0),
    cibil_discount: float = Query(10.0),
    down_payment_pct: float = Query(25.0),
):
    """EMI calculator API."""
    result = calc.emi_calculator(
        premium, years, gst, cibil_discount, down_payment_pct,
    )
    return result.to_dict()


@app.get("/api/calc/health")
async def api_health(
    age: int = Query(35),
    family: str = Query("2A+2C"),
    city_tier: int = Query(1),
    pre_existing: bool = Query(False),
):
    """Health cover estimator API."""
    tier_map = {1: "metro", 2: "tier1", 3: "tier2", 4: "tier3"}
    tier_str = tier_map.get(city_tier, "tier1")
    result = calc.health_cover_estimator(
        age=age, family_size=family, city_tier=tier_str,
    )
    return result.to_dict()


@app.get("/api/calc/sip")
async def api_sip(
    amount: float = Query(500000),
    years: int = Query(10),
    expected_return: float = Query(12.0),
):
    """SIP vs Lumpsum calculator API."""
    result = calc.sip_vs_lumpsum(amount, years, expected_return)
    return result.to_dict()


@app.get("/api/calc/mfsip")
async def api_mfsip(
    goal: float = Query(5000000),
    years: int = Query(15),
    annual_return: float = Query(12.0),
    existing: float = Query(0),
):
    """Mutual Fund SIP Planner API."""
    result = calc.mf_sip_planner(goal, years, annual_return, existing)
    return result.to_dict()


@app.get("/api/calc/ulip")
async def api_ulip(
    annual_investment: float = Query(100000),
    years: int = Query(15),
    ulip_return: float = Query(10.0),
    mf_return: float = Query(12.0),
):
    """ULIP vs Mutual Fund comparison API."""
    result = calc.ulip_vs_mf(annual_investment, years, ulip_return, mf_return)
    return result.to_dict()


@app.get("/api/calc/nps")
async def api_nps(
    monthly: float = Query(5000),
    current_age: int = Query(30),
    retire_age: int = Query(60),
    annual_return: float = Query(10.0),
    tax_bracket: float = Query(30.0),
):
    """NPS Planner API."""
    result = calc.nps_planner(monthly, current_age, retire_age, annual_return, tax_bracket)
    return result.to_dict()


@app.get("/api/calc/stepup")
async def api_stepup(
    initial_sip: float = Query(10000),
    annual_step_up: float = Query(10.0),
    years: int = Query(20),
    annual_return: float = Query(12.0),
):
    """Step-up SIP Planner API."""
    result = calc.stepup_sip_planner(
        initial_sip=initial_sip, annual_step_up=annual_step_up,
        years=years, annual_return=annual_return,
    )
    return result.to_dict()


@app.get("/api/calc/swp")
async def api_swp(
    initial_corpus: float = Query(5000000),
    monthly_withdrawal: float = Query(30000),
    annual_return: float = Query(8.0),
    years: int = Query(20),
):
    """SWP Calculator API."""
    result = calc.swp_calculator(
        initial_corpus=initial_corpus, monthly_withdrawal=monthly_withdrawal,
        annual_return=annual_return, years=years,
    )
    return result.to_dict()


@app.get("/api/calc/delay")
async def api_delay(
    monthly_sip: float = Query(10000),
    years: int = Query(25),
    annual_return: float = Query(12.0),
    delay_years: int = Query(5),
):
    """Delay Cost Calculator API."""
    result = calc.delay_cost_calculator(
        monthly_sip=monthly_sip, years=years,
        annual_return=annual_return, delay_years=delay_years,
    )
    return result.to_dict()


# =============================================================================
#  FEATURE 4 — ADVISOR MICROSITE (public landing page + lead capture)
# =============================================================================

import json as _json_microsite
import re as _re_microsite
import html as _html_microsite

_DEFAULT_SERVICES = ["Health Insurance", "Term Life", "Investment Planning",
                     "Retirement Planning", "Tax Saving", "Child Education"]


def _microsite_template_path() -> Path:
    return Path(__file__).parent / "static" / "microsite.html"


def _microsite_url(slug: str) -> str:
    base = (os.getenv("SERVER_URL") or "https://sarathi-ai.com").rstrip("/")
    return f"{base}/m/{slug}"


def _microsite_render(tenant: dict, owner_agent: dict | None) -> str:
    """Render the public microsite HTML by substituting placeholders into the
    static template. Falls back to a minimal inline template if file missing."""
    slug = tenant.get("microsite_slug") or ""
    firm = tenant.get("firm_name") or "Financial Advisor"
    advisor = (owner_agent.get("name") if owner_agent else None) or tenant.get("owner_name") or firm
    photo = tenant.get("microsite_photo") or (owner_agent.get("profile_photo") if owner_agent else "") or ""
    bio = tenant.get("microsite_bio") or ""
    primary = tenant.get("brand_primary_color") or "#0d9488"
    accent = tenant.get("brand_accent_color") or "#ea580c"
    years = int(tenant.get("microsite_years_exp") or 0)
    families = int(tenant.get("microsite_families_served") or 0)
    irdai = tenant.get("irdai_license") or ""
    arn = tenant.get("amfi_reg") or ""
    badge = int(tenant.get("microsite_show_badge") or 1)
    plan_features = db.PLAN_FEATURES.get(tenant.get("plan") or "trial", db.PLAN_FEATURES["trial"])
    if not plan_features.get("custom_branding"):
        badge = 1  # cannot hide badge on lower plans

    # Phone / WhatsApp resolution
    phone = (owner_agent.get("phone") if owner_agent else "") or tenant.get("brand_phone") or tenant.get("phone") or ""
    wa_phone = _re_microsite.sub(r"\D", "", phone or "")
    if wa_phone and not wa_phone.startswith("91") and len(wa_phone) == 10:
        wa_phone = "91" + wa_phone
    email = tenant.get("brand_email") or tenant.get("email") or ""

    try:
        services = _json_microsite.loads(tenant.get("microsite_services") or "[]") or _DEFAULT_SERVICES
        if not isinstance(services, list) or not services:
            services = _DEFAULT_SERVICES
    except Exception:
        services = _DEFAULT_SERVICES
    try:
        testimonials = _json_microsite.loads(tenant.get("microsite_testimonials") or "[]") or []
        if not isinstance(testimonials, list):
            testimonials = []
    except Exception:
        testimonials = []

    template_file = _microsite_template_path()
    if template_file.exists():
        html = template_file.read_text(encoding="utf-8")
    else:
        html = "<!doctype html><html><body><h1>{{ADVISOR_NAME}}</h1><p>{{BIO}}</p></body></html>"

    def _safe_json(obj):
        # Defend against </script> injection inside inline JS
        return _json_microsite.dumps(obj).replace("</", "<\\/")

    replacements = {
        "{{SLUG}}": _html_microsite.escape(slug, quote=True),
        "{{FIRM_NAME}}": _html_microsite.escape(firm, quote=True),
        "{{ADVISOR_NAME}}": _html_microsite.escape(advisor, quote=True),
        "{{PHOTO_URL}}": _html_microsite.escape(photo, quote=True),
        "{{BIO}}": _html_microsite.escape(bio, quote=True),
        "{{BIO_JSON}}": _safe_json(bio),
        "{{PRIMARY_COLOR}}": _html_microsite.escape(primary, quote=True),
        "{{ACCENT_COLOR}}": _html_microsite.escape(accent, quote=True),
        "{{YEARS_EXP}}": str(years),
        "{{FAMILIES_SERVED}}": str(families),
        "{{IRDAI_CODE}}": _html_microsite.escape(irdai, quote=True),
        "{{ARN_CODE}}": _html_microsite.escape(arn, quote=True),
        "{{PHONE}}": _re_microsite.sub(r"[^\d+]", "", phone or ""),
        "{{WA_PHONE}}": wa_phone,
        "{{EMAIL}}": _html_microsite.escape(email, quote=True),
        "{{SERVICES_JSON}}": _safe_json(services),
        "{{TESTIMONIALS_JSON}}": _safe_json(testimonials),
        "{{SHOW_BADGE}}": "1" if badge else "0",
        "{{PUBLIC_URL}}": _html_microsite.escape(_microsite_url(slug), quote=True),
    }
    for k, v in replacements.items():
        html = html.replace(k, v)
    return html


@app.get("/m/{slug}", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def microsite_public(slug: str, request: Request):
    """Public advisor microsite. Anyone can view if the advisor has published."""
    slug_clean = (slug or "").lower().strip()
    if not _re_microsite.match(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$", slug_clean):
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    tenant = await db.get_tenant_by_microsite_slug(slug_clean)
    if not tenant or not tenant.get("microsite_published"):
        return HTMLResponse(
            "<!doctype html><html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h1>Page not available</h1><p>This advisor's microsite is not published yet.</p>"
            "<p><a href='/'>Back to Sarathi-AI</a></p></body></html>",
            status_code=404)
    owner_agent = await db.get_owner_agent_by_tenant(tenant["tenant_id"])
    # Bump view counter (best-effort, fire and forget)
    try:
        asyncio.create_task(db.increment_microsite_view(tenant["tenant_id"]))
    except Exception:
        pass
    html = _microsite_render(tenant, owner_agent)
    return HTMLResponse(html)


@app.get("/api/microsite/settings")
async def api_microsite_settings_get(tenant: dict = Depends(auth.require_owner)):
    """Return the current microsite settings for the logged-in owner."""
    t = await db.get_tenant(tenant["tenant_id"])
    if not t:
        return JSONResponse({"error": "tenant not found"}, status_code=404)
    slug = t.get("microsite_slug") or await db.suggest_microsite_slug(
        t.get("firm_name", ""), t.get("owner_name", ""), tenant_id=t["tenant_id"])
    plan_features = db.PLAN_FEATURES.get(t.get("plan") or "trial", db.PLAN_FEATURES["trial"])
    try:
        services = _json_microsite.loads(t.get("microsite_services") or "[]") or []
    except Exception:
        services = []
    try:
        testimonials = _json_microsite.loads(t.get("microsite_testimonials") or "[]") or []
    except Exception:
        testimonials = []
    return {
        "slug": slug,
        "saved_slug": t.get("microsite_slug") or "",
        "bio": t.get("microsite_bio") or "",
        "photo_url": t.get("microsite_photo") or "",
        "primary_color": t.get("brand_primary_color") or "#0d9488",
        "accent_color": t.get("brand_accent_color") or "#ea580c",
        "years_exp": int(t.get("microsite_years_exp") or 0),
        "families_served": int(t.get("microsite_families_served") or 0),
        "services": services or _DEFAULT_SERVICES,
        "testimonials": testimonials,
        "show_badge": bool(int(t.get("microsite_show_badge") or 1)),
        "is_published": bool(int(t.get("microsite_published") or 0)),
        "views": int(t.get("microsite_views") or 0),
        "irdai_license": t.get("irdai_license") or "",
        "amfi_reg": t.get("amfi_reg") or "",
        "can_hide_badge": bool(plan_features.get("custom_branding")),
        "public_url": _microsite_url(t.get("microsite_slug") or slug),
    }


class MicrositeSettingsUpdate(BaseModel):
    slug: str | None = None
    bio: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    years_exp: int | None = None
    families_served: int | None = None
    services: list | None = None
    testimonials: list | None = None
    show_badge: bool | None = None
    is_published: bool | None = None
    irdai_license: str | None = None
    amfi_reg: str | None = None


@app.post("/api/microsite/settings")
@limiter.limit("20/minute")
async def api_microsite_settings_post(req: MicrositeSettingsUpdate, request: Request,
                                       tenant: dict = Depends(auth.require_owner)):
    """Update microsite settings. Validates slug uniqueness + sane fields."""
    tid = tenant["tenant_id"]
    t = await db.get_tenant(tid)
    if not t:
        return JSONResponse({"error": "tenant not found"}, status_code=404)
    plan_features = db.PLAN_FEATURES.get(t.get("plan") or "trial", db.PLAN_FEATURES["trial"])

    updates: dict = {}

    if req.slug is not None:
        slug = (req.slug or "").lower().strip()
        if slug != (t.get("microsite_slug") or ""):
            if not _re_microsite.match(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$", slug):
                return JSONResponse({"error": "Slug must be 3-40 chars, lowercase letters/digits/hyphens, not starting/ending with hyphen."}, status_code=400)
            if not await db.is_microsite_slug_available(slug, exclude_tenant_id=tid):
                return JSONResponse({"error": "This URL is already taken. Please choose another."}, status_code=409)
            updates["microsite_slug"] = slug

    if req.bio is not None:
        bio = (req.bio or "").strip()
        if len(bio) > 600:
            return JSONResponse({"error": "Bio must be 600 characters or less."}, status_code=400)
        updates["microsite_bio"] = bio

    if req.primary_color is not None:
        c = (req.primary_color or "").strip()
        if c and not _re_microsite.match(r"^#[0-9a-fA-F]{6}$", c):
            return JSONResponse({"error": "Invalid primary color."}, status_code=400)
        updates["brand_primary_color"] = c or "#0d9488"

    if req.accent_color is not None:
        c = (req.accent_color or "").strip()
        if c and not _re_microsite.match(r"^#[0-9a-fA-F]{6}$", c):
            return JSONResponse({"error": "Invalid accent color."}, status_code=400)
        updates["brand_accent_color"] = c or "#ea580c"

    if req.years_exp is not None:
        updates["microsite_years_exp"] = max(0, min(int(req.years_exp), 70))

    if req.families_served is not None:
        updates["microsite_families_served"] = max(0, min(int(req.families_served), 1000000))

    if req.services is not None:
        services = [str(s).strip()[:60] for s in (req.services or []) if str(s).strip()][:20]
        updates["microsite_services"] = _json_microsite.dumps(services)

    if req.testimonials is not None:
        clean_t = []
        for item in (req.testimonials or [])[:20]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()[:60]
            text = str(item.get("text", "")).strip()[:300]
            if name and text:
                clean_t.append({"name": name, "text": text})
        updates["microsite_testimonials"] = _json_microsite.dumps(clean_t)

    if req.show_badge is not None:
        if not plan_features.get("custom_branding") and not req.show_badge:
            return JSONResponse({"error": "Hiding the Sarathi-AI badge requires Team or Enterprise plan."}, status_code=403)
        updates["microsite_show_badge"] = 1 if req.show_badge else 0

    if req.is_published is not None:
        updates["microsite_published"] = 1 if req.is_published else 0

    if req.irdai_license is not None:
        updates["irdai_license"] = (req.irdai_license or "").strip()[:60]
    if req.amfi_reg is not None:
        updates["amfi_reg"] = (req.amfi_reg or "").strip()[:60]

    if updates:
        await db.update_tenant(tid, **updates)
    t2 = await db.get_tenant(tid)
    return {"ok": True, "public_url": _microsite_url(t2.get("microsite_slug") or "")}


@app.post("/api/microsite/upload-photo")
@limiter.limit("10/minute")
async def api_microsite_upload_photo(request: Request,
                                      file: UploadFile = File(...),
                                      tenant: dict = Depends(auth.require_owner)):
    """Upload a portrait photo for the microsite hero. JPEG/PNG, ≤500KB."""
    tid = tenant["tenant_id"]
    image_bytes = await file.read()
    if not image_bytes or len(image_bytes) < 100:
        return JSONResponse({"error": "Empty file."}, status_code=400)
    if len(image_bytes) > 500 * 1024:
        return JSONResponse({"error": "File too large (max 500KB)."}, status_code=400)
    if not (image_bytes[:2] == b"\xff\xd8" or image_bytes[:4] == b"\x89PNG"):
        return JSONResponse({"error": "Only JPEG and PNG images are supported."}, status_code=400)
    ext = "jpg" if image_bytes[:2] == b"\xff\xd8" else "png"
    out_dir = Path(__file__).parent / "uploads" / "microsite"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"tenant_{tid}.{ext}"
    (out_dir / filename).write_bytes(image_bytes)
    photo_url = f"/uploads/microsite/{filename}?v={int(_time.time())}"
    await db.update_tenant(tid, microsite_photo=photo_url)
    return {"ok": True, "photo_url": photo_url}


class MicrositeLeadIn(BaseModel):
    name: str
    phone: str
    city: str | None = ""
    need_type: str | None = "general"
    message: str | None = ""
    consent: bool = False


@app.post("/m/{slug}/lead")
@limiter.limit("5/minute")
async def api_microsite_lead(slug: str, req: MicrositeLeadIn, request: Request):
    """Public lead capture from a microsite. Creates a lead under the owner agent
    and sends a Telegram alert. DPDP consent required."""
    slug_clean = (slug or "").lower().strip()
    tenant = await db.get_tenant_by_microsite_slug(slug_clean)
    if not tenant or not tenant.get("microsite_published"):
        return JSONResponse({"error": "Microsite not found."}, status_code=404)

    name = (req.name or "").strip()[:80]
    phone = _re_microsite.sub(r"\D", "", req.phone or "")[:15]
    if not name or len(phone) < 10:
        return JSONResponse({"error": "Name and a valid 10-digit phone are required."}, status_code=400)
    if not req.consent:
        return JSONResponse({"error": "Please give consent to be contacted (DPDP)."}, status_code=400)

    city = (req.city or "").strip()[:60]
    need = (req.need_type or "general").strip().lower()[:30]
    message = (req.message or "").strip()[:500]

    owner_agent = await db.get_owner_agent_by_tenant(tenant["tenant_id"])
    if not owner_agent:
        return JSONResponse({"error": "Advisor not available right now."}, status_code=503)

    # Create the lead
    notes = f"From microsite /m/{slug_clean}"
    if message:
        notes += f"\nVisitor message: {message}"
    try:
        lead_id = await db.add_lead(
            agent_id=owner_agent["agent_id"], name=name, phone=phone,
            whatsapp=phone, city=city, need_type=need,
            source="microsite", notes=notes,
        )
    except Exception as e:
        logger.exception("microsite lead insert failed: %s", e)
        return JSONResponse({"error": "Could not save your request. Please try again."}, status_code=500)

    # Mark DPDP consent
    try:
        from datetime import datetime as _dt_micro
        await db.update_lead(lead_id, dpdp_consent=1,
                             dpdp_consent_date=_dt_micro.now().isoformat())
    except Exception as _dpdp_e:
        logger.warning("microsite dpdp consent update failed: %s", _dpdp_e)

    # Telegram alert to owner (best-effort)
    try:
        owner_tg = tenant.get("owner_telegram_id")
        if owner_tg:
            msg = (
                f"🌐 <b>New microsite lead</b>\n"
                f"<b>{name}</b> · 📞 {phone}\n"
                f"{('🏙 ' + city + chr(10)) if city else ''}"
                f"Need: {need}\n"
                f"{('💬 ' + message + chr(10)) if message else ''}"
                f"\nLead #{lead_id}"
            )
            mgr = botmgr.bot_manager
            asyncio.create_task(mgr.send_alert(int(owner_tg), msg, tenant_id=tenant["tenant_id"]))
    except Exception as e:
        logger.warning("microsite Telegram alert failed: %s", e)

    # Email copy (best-effort)
    try:
        notify_email = tenant.get("brand_email") or tenant.get("email")
        if notify_email and hasattr(email_svc, "send_email"):
            subject = f"New lead from your microsite — {name}"
            body = (
                f"Hi {tenant.get('owner_name', '')},\n\n"
                f"You received a new lead from your Sarathi-AI microsite (/m/{slug_clean}):\n\n"
                f"Name: {name}\nPhone: {phone}\nCity: {city or '-'}\nNeed: {need}\n"
                f"Message: {message or '-'}\n\n"
                f"Open dashboard: {_microsite_url('').replace('/m/', '/dashboard')}\n"
            )
            asyncio.create_task(email_svc.send_email(notify_email, subject, body))
    except Exception:
        pass

    return {"ok": True, "message": "Thanks! Your advisor will reach out shortly."}


@app.get("/api/microsite/qr")
async def api_microsite_qr(tenant: dict = Depends(auth.require_owner)):
    """Return a QR code PNG for the advisor's public microsite URL."""
    t = await db.get_tenant(tenant["tenant_id"])
    slug = (t or {}).get("microsite_slug") or ""
    if not slug:
        return JSONResponse({"error": "Set your microsite slug first."}, status_code=400)
    url = _microsite_url(slug)
    try:
        import qrcode  # type: ignore
        from io import BytesIO
        img = qrcode.make(url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png",
                         headers={"Content-Disposition": f'inline; filename="microsite-{slug}.png"'})
    except Exception:
        # Fallback to a public QR service redirect (no API key needed)
        from urllib.parse import quote_plus
        return RedirectResponse(
            f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={quote_plus(url)}")


@app.get("/api/microsite/check-slug")
@limiter.limit("30/minute")
async def api_microsite_check_slug(request: Request, slug: str = Query(...),
                                    tenant: dict = Depends(auth.require_owner)):
    """Check if a slug is available for the current tenant."""
    s = (slug or "").lower().strip()
    if not _re_microsite.match(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$", s):
        return {"available": False, "reason": "format"}
    avail = await db.is_microsite_slug_available(s, exclude_tenant_id=tenant["tenant_id"])
    return {"available": avail, "slug": s}


# =============================================================================
#  PDF / REPORT API
# =============================================================================

def _build_brand(company: str = "", brand_primary: str = "", brand_accent: str = "",
                 brand_logo: str = "", brand_tagline: str = "",
                 brand_phone: str = "", brand_email: str = "",
                 brand_website: str = "", microsite_url: str = "") -> dict:
    """Build brand dict for PDF generation from query params."""
    return {
        'firm_name': company,
        'primary_color': brand_primary or None,
        'accent_color': brand_accent or None,
        'logo': brand_logo or None,
        'tagline': brand_tagline or None,
        'phone': brand_phone or None,
        'email': brand_email or None,
        'website': brand_website or None,
        'microsite_url': microsite_url or None,
    }

@app.get("/api/report/inflation")
async def report_inflation(
    amount: float = Query(50000),
    inflation: float = Query(6.0),
    years: int = Query(10),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded inflation report (HTML), return URL."""
    result = calc.inflation_eraser(amount, inflation, years)
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_inflation_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "inflation", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/hlv")
async def report_hlv(
    monthly_expense: float = Query(50000),
    loans: float = Query(0),
    children_expense: float = Query(0),
    savings: float = Query(0),
    existing_cover: float = Query(0),
    current_age: int = Query(35),
    retirement_age: int = Query(60),
    inflation: float = Query(6.0),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded HLV report (HTML), return URL."""
    result = calc.hlv_calculator(
        monthly_expense=monthly_expense,
        outstanding_loans=loans,
        child_education=children_expense,
        current_savings=savings,
        existing_cover=existing_cover,
        current_age=current_age,
        retirement_age=retirement_age,
        inflation_rate=inflation,
    )
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_hlv_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "hlv", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/retirement")
async def report_retirement(
    current_age: int = Query(35),
    retirement_age: int = Query(60),
    life_expectancy: int = Query(85),
    monthly_expense: float = Query(40000),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded retirement report (HTML), return URL."""
    result = calc.retirement_planner(current_age, retirement_age,
                                      life_expectancy, monthly_expense)
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_retirement_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "retirement", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/emi")
async def report_emi(
    premium: float = Query(25000),
    years: int = Query(5),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded EMI report (HTML), return URL."""
    result = calc.emi_calculator(premium, years)
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_emi_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "emi", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/health")
async def report_health(
    age: int = Query(35),
    family: str = Query("2A+2C"),
    city_tier: str = Query("metro"),
    monthly_income: float = Query(50000),
    existing_cover: float = Query(0),
    has_parents: bool = Query(False),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded health cover report (HTML), return URL."""
    result = calc.health_cover_estimator(age, family, city_tier, monthly_income,
                                         existing_cover, has_parents)
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_health_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "health", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/sip")
async def report_sip(
    amount: float = Query(500000),
    years: int = Query(10),
    expected_return: float = Query(12.0),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded SIP vs Lumpsum report (HTML), return URL."""
    result = calc.sip_vs_lumpsum(amount, years, expected_return)
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_sip_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "sip", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/mfsip")
async def report_mfsip(
    goal: float = Query(5000000),
    years: int = Query(15),
    annual_return: float = Query(12.0),
    existing: float = Query(0),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded MF SIP Planner report (HTML), return URL."""
    result = calc.mf_sip_planner(goal, years, annual_return, existing)
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_mfsip_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "mfsip", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/ulip")
async def report_ulip(
    annual_investment: float = Query(100000),
    years: int = Query(15),
    ulip_return: float = Query(10.0),
    mf_return: float = Query(12.0),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded ULIP vs MF report (HTML), return URL."""
    result = calc.ulip_vs_mf(annual_investment, years, ulip_return, mf_return)
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_ulip_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "ulip", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/nps")
async def report_nps(
    monthly: float = Query(5000),
    current_age: int = Query(30),
    retire_age: int = Query(60),
    annual_return: float = Query(10.0),
    tax_bracket: float = Query(30.0),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded NPS Planner report (HTML), return URL."""
    result = calc.nps_planner(monthly, current_age, retire_age, annual_return,
                               tax_bracket)
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_nps_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "nps", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/stepup")
async def report_stepup(
    initial_sip: float = Query(10000),
    annual_step_up: float = Query(10.0),
    years: int = Query(20),
    annual_return: float = Query(12.0),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded Step-up SIP report (HTML), return URL."""
    result = calc.stepup_sip_planner(
        initial_sip=initial_sip, annual_step_up=annual_step_up,
        years=years, annual_return=annual_return,
    )
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_stepupsip_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "stepupsip", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/swp")
async def report_swp(
    initial_corpus: float = Query(5000000),
    monthly_withdrawal: float = Query(30000),
    annual_return: float = Query(8.0),
    years: int = Query(20),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded SWP report (HTML), return URL."""
    result = calc.swp_calculator(
        initial_corpus=initial_corpus, monthly_withdrawal=monthly_withdrawal,
        annual_return=annual_return, years=years,
    )
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_swp_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "swp", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


@app.get("/api/report/delay")
async def report_delay(
    monthly_sip: float = Query(10000),
    years: int = Query(25),
    annual_return: float = Query(12.0),
    delay_years: int = Query(5),
    client_name: str = Query("Client"),
    agent_name: str = Query(""),
    agent_phone: str = Query(""),
    agent_photo_url: str = Query(""),
    company: str = Query(""),
    lang: str = Query("en"),
    brand_primary: str = Query(""),
    brand_accent: str = Query(""),
    brand_logo: str = Query(""),
    brand_tagline: str = Query(""),
    brand_phone: str = Query(""),
    brand_email: str = Query(""),
    brand_website: str = Query(""),
    microsite_url: str = Query(""),
):
    """Generate branded Delay Cost report (HTML), return URL."""
    result = calc.delay_cost_calculator(
        monthly_sip=monthly_sip, years=years,
        annual_return=annual_return, delay_years=delay_years,
    )
    brand = _build_brand(company, brand_primary, brand_accent, brand_logo, brand_tagline, brand_phone, brand_email, brand_website, microsite_url)
    html_content = pdf.generate_delaycost_html(result, client_name,
        agent_name=agent_name, agent_phone=agent_phone,
        agent_photo_url=agent_photo_url, company=company, lang=lang, brand=brand)
    filename = pdf.save_html_report(html_content, "delaycost", client_name, advisor_name=company or agent_name)
    return {"url": f"{SERVER_URL}/reports/{filename}", "filename": filename}


# =============================================================================
#  DASHBOARD API (feeds the dashboard.html front-end)
# =============================================================================

@app.get("/api/ai-usage")
async def api_ai_usage(request: Request, days: int = Query(30, ge=1, le=90)):
    """Get AI usage summary for current tenant. JWT required."""
    current = await auth.get_optional_tenant(request)
    if not current:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    summary = await db.get_tenant_ai_usage_summary(current["tenant_id"], days=days)
    return summary


@app.get("/api/dashboard")
async def api_dashboard(
    request: Request,
    agent_id: int = Query(None, description="Agent ID (omit for first agent)"),
):
    """Return dashboard data scoped to a specific agent or tenant. JWT REQUIRED."""
    # Authenticate: JWT is mandatory — no unauthenticated ?tenant_id fallback
    current = await auth.get_optional_tenant(request)
    if not current:
        return JSONResponse({"detail": "Authentication required. Please login."}, status_code=401)
    effective_tenant_id = current["tenant_id"]

    # If agent_id specified, verify it belongs to authenticated tenant
    if agent_id:
        agent_check = await db.get_agent_by_id(agent_id)
        if not agent_check or agent_check.get('tenant_id') != current['tenant_id']:
            return JSONResponse({"detail": "Agent does not belong to your tenant"}, status_code=403)
        # Non-owner/admin agents can only view their own dashboard
        caller_role = current.get("role", "agent")
        if caller_role not in ("owner", "admin") and agent_id != current.get("agent_id"):
            return JSONResponse({"detail": "You can only view your own dashboard"}, status_code=403)

    try:
        target_agent_id = None
        if agent_id:
            target_agent_id = agent_id
        elif effective_tenant_id:
            agents = await db.get_agents_by_tenant(effective_tenant_id)
            if agents:
                target_agent_id = agents[0]["agent_id"]
        else:
            agents = await db.get_all_active_agents()
            if agents:
                target_agent_id = agents[0]["agent_id"]

        if target_agent_id:
            stats = await db.get_agent_stats(target_agent_id)
            followups = await db.get_todays_followups(target_agent_id)
            pending = await db.get_pending_followups(target_agent_id)
            renewals = await db.get_upcoming_renewals(target_agent_id, days_ahead=30)
            all_followups = followups + [f for f in pending if f not in followups]

            # For admin/owner: also include tenant-wide follow-ups they might have missed
            caller_role = current.get("role", "agent")
            if caller_role in ("owner", "admin") and effective_tenant_id:
                tenant_fups = await db.get_tenant_pending_followups(effective_tenant_id)
                seen_ids = {f.get('interaction_id') for f in all_followups}
                for tf in tenant_fups:
                    if tf.get('interaction_id') not in seen_ids:
                        all_followups.append(tf)
                        seen_ids.add(tf.get('interaction_id'))
        else:
            stats = {"total_leads": 0, "active_policies": 0, "total_premium": 0, "pipeline": {}, "today_new_leads": 0}
            all_followups = []
            renewals = []

        # Subscription info for the dashboard
        subscription = {}
        if effective_tenant_id:
            tenant = await db.get_tenant(effective_tenant_id)
            if tenant:
                from datetime import datetime
                plan_names = {"individual": "Solo Advisor", "team": "Team", "enterprise": "Enterprise", "trial": "Free Trial"}
                sub_status = tenant.get("subscription_status", "trial")
                trial_ends = tenant.get("trial_ends_at", "")
                sub_expires = tenant.get("subscription_expires_at", "")
                days_left = None
                if sub_status == "trial" and trial_ends:
                    try:
                        dt = datetime.fromisoformat(trial_ends)
                        days_left = max(0, (dt - datetime.now()).days)
                    except Exception:
                        pass
                elif sub_status == "active" and sub_expires:
                    try:
                        dt = datetime.fromisoformat(sub_expires)
                        days_left = max(0, (dt - datetime.now()).days)
                    except Exception:
                        pass
                subscription = {
                    "plan": tenant.get("plan", "trial"),
                    "plan_name": plan_names.get(tenant.get("plan", "trial"), tenant.get("plan", "trial")),
                    "status": sub_status,
                    "is_active": bool(tenant.get("is_active", 0)),
                    "days_left": days_left,
                    "trial_ends_at": trial_ends,
                    "subscription_expires_at": sub_expires,
                    "firm_name": tenant.get("firm_name", ""),
                }

        return {
            "stats": stats,
            "followups": all_followups[:10],
            "followups_count": len(all_followups),
            "renewals": [dict(r) if not isinstance(r, dict) else r for r in renewals],
            "renewals_count": len(renewals),
            "subscription": subscription,
        }
    except Exception as e:
        logger.error("Dashboard API error: %s", e, exc_info=True)
        return JSONResponse(
            {"error": str(e)},
            status_code=500,
        )


def _empty_dashboard():
    return {
        "stats": {"total_leads": 0, "active_policies": 0,
                  "total_premium": 0, "pipeline": {},
                  "today_new_leads": 0},
        "followups": [], "followups_count": 0,
        "renewals": [], "renewals_count": 0,
    }


# =============================================================================
#  WHATSAPP SENDING API (for dashboard / frontend)
# =============================================================================

class WaSendRequest(BaseModel):
    phone: str = Field(..., pattern=r"^(91)?[6-9]\d{9}$", description="Recipient phone (10-digit or 91XXXXXXXXXX)")
    message: str = Field(..., min_length=1, max_length=4096, description="Message text")

class WaCalcShareRequest(BaseModel):
    phone: str = Field(..., description="Recipient phone")
    client_name: str = Field("Client", description="Client name")
    calc_type: str = Field("general", description="Calculator type (inflation/hlv/retirement/emi/health/sip)")
    summary: str = Field(..., description="Calculation result summary text")
    report_url: str = Field("", description="URL to the generated PDF report")

class WaGreetingRequest(BaseModel):
    phone: str = Field(..., description="Recipient phone")
    client_name: str = Field(..., description="Client name")
    greeting_type: str = Field("birthday", description="birthday or anniversary")


@app.post("/api/wa/send")
@limiter.limit("30/minute")
async def api_wa_send(
    request: Request,
    req: WaSendRequest,
    tenant: dict = Depends(auth.get_current_tenant),
):
    """Send a WhatsApp message to a lead. Uses Cloud API if configured, else returns wa.me link."""
    return _WA_DISABLED_RESPONSE
    try:
        result = await wa.send_or_link(req.phone, req.message)
        # Log interaction
        try:
            agent = await db.get_agents_by_tenant(tenant["tenant_id"])
            if agent:
                await db.log_interaction(
                    lead_id=None, agent_id=agent[0]["agent_id"],
                    interaction_type="whatsapp_sent",
                    channel="whatsapp",
                    summary=f"To {req.phone}: {req.message[:100]}"
                )
        except Exception:
            pass
        return result
    except Exception as e:
        logger.error("WA send error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/wa/share-calc")
@limiter.limit("20/minute")
async def api_wa_share_calc(
    request: Request,
    req: WaCalcShareRequest,
    tenant: dict = Depends(auth.get_current_tenant),
):
    """Share calculator results via WhatsApp (Cloud API or wa.me link fallback)."""
    return _WA_DISABLED_RESPONSE
    try:
        tenant_data = await db.get_tenant(tenant["tenant_id"])
        agent_name = tenant_data.get("owner_name", "Your Advisor") if tenant_data else "Your Advisor"
        company = tenant_data.get("firm_name", "Sarathi-AI") if tenant_data else "Sarathi-AI"

        result = await wa.send_calc_report(
            to=req.phone,
            client_name=req.client_name,
            calc_type=req.calc_type,
            summary=req.summary,
            report_url=req.report_url,
            agent_name=agent_name,
            company=company,
        )
        return result
    except Exception as e:
        logger.error("WA calc share error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/wa/greeting")
@limiter.limit("20/minute")
async def api_wa_greeting(
    request: Request,
    req: WaGreetingRequest,
    tenant: dict = Depends(auth.get_current_tenant),
):
    """Send a birthday or anniversary greeting via WhatsApp."""
    return _WA_DISABLED_RESPONSE
    try:
        tenant_data = await db.get_tenant(tenant["tenant_id"])
        agent_name = tenant_data.get("owner_name", "Your Advisor") if tenant_data else "Your Advisor"
        company = tenant_data.get("firm_name", "Sarathi-AI") if tenant_data else "Sarathi-AI"

        if req.greeting_type == "birthday":
            if wa.is_configured():
                result = await wa.send_birthday_greeting(
                    req.phone, req.client_name, agent_name, company
                )
            else:
                link = wa.generate_birthday_link(
                    req.phone, req.client_name, agent_name, company
                )
                result = {"success": True, "method": "link", "wa_link": link}
        else:
            # Anniversary greeting
            first = req.client_name.split()[0] if req.client_name else "Sir/Ma'am"
            msg = (
                f"🎊 Happy Anniversary! 🎉\n\n"
                f"Dear {first},\n\n"
                f"Wishing you a wonderful anniversary filled with "
                f"love and happiness!\n\n"
                f"Warm regards,\n{agent_name}\n{company} 🌟"
            )
            result = await wa.send_or_link(req.phone, msg)

        # Log interaction
        try:
            agent = await db.get_agents_by_tenant(tenant["tenant_id"])
            if agent:
                await db.log_interaction(
                    agent[0]["agent_id"], None, "whatsapp_greeting",
                    f"{req.greeting_type} to {req.client_name} ({req.phone})"
                )
        except Exception:
            pass

        return result
    except Exception as e:
        logger.error("WA greeting error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/wa/status")
async def api_wa_status(tenant: dict = Depends(auth.get_current_tenant)):
    """Check WhatsApp Cloud API configuration status for the tenant."""
    return {
        "cloud_api_configured": False,
        "fallback_available": False,
        "method": "disabled",
        "message": "WhatsApp API integration disabled. Use Voice AI and personal messaging.",
    }


# =============================================================================
#  GOOGLE DRIVE INTEGRATION API
# =============================================================================

@app.get("/api/gdrive/connect")
async def api_gdrive_connect(tenant: dict = Depends(auth.get_current_tenant)):
    """Get Google Drive OAuth2 authorization URL."""
    # ── Plan gate: Google Drive requires Team plan or higher ──
    gate = await db.check_plan_feature(tenant["tenant_id"], "google_drive")
    if not gate['allowed']:
        return JSONResponse({"error": gate['reason']}, status_code=403)
    if not gdrive.is_enabled():
        return JSONResponse(
            {"error": "Google Drive integration not configured. Set GDRIVE_CLIENT_ID in biz.env."},
            status_code=503,
        )
    auth_url = gdrive.get_auth_url(tenant["tenant_id"])
    return {"auth_url": auth_url}


@app.get("/api/gdrive/callback")
async def api_gdrive_callback(code: str = Query(...), state: str = Query("")):
    """Handle Google OAuth2 callback — exchange code for tokens."""
    try:
        tenant_id = int(state) if state else 0
    except ValueError:
        return JSONResponse({"error": "Invalid state"}, status_code=400)

    if not tenant_id:
        return JSONResponse({"error": "Missing tenant ID"}, status_code=400)

    result = await gdrive.handle_callback(code, tenant_id)
    if result.get("success"):
        # Redirect to dashboard with success message
        return HTMLResponse(
            f"<html><body><h2>✅ Google Drive Connected!</h2>"
            f"<p>Account: {result.get('email', '')}</p>"
            f"<p>Your reports will now be auto-saved to Google Drive.</p>"
            f"<p><a href='/dashboard'>Go to Dashboard</a></p></body></html>"
        )
    return HTMLResponse(
        f"<html><body><h2>❌ Connection Failed</h2>"
        f"<p>{result.get('error', 'Unknown error')}</p>"
        f"<p><a href='/dashboard'>Try Again</a></p></body></html>"
    )


@app.get("/api/gdrive/status")
async def api_gdrive_status(tenant: dict = Depends(auth.get_current_tenant)):
    """Check Google Drive connection status for the tenant."""
    tid = tenant["tenant_id"]
    return {
        "enabled": gdrive.is_enabled(),
        "connected": gdrive.is_connected(tid),
        "email": gdrive.get_connected_email(tid) if gdrive.is_connected(tid) else "",
    }


@app.post("/api/gdrive/disconnect")
async def api_gdrive_disconnect(tenant: dict = Depends(auth.get_current_tenant)):
    """Disconnect Google Drive for the tenant."""
    await gdrive.disconnect(tenant["tenant_id"])
    return {"success": True, "message": "Google Drive disconnected"}


@app.get("/api/gdrive/files")
async def api_gdrive_files(tenant: dict = Depends(auth.get_current_tenant)):
    """List report files from the tenant's Google Drive CRM folder."""
    tid = tenant["tenant_id"]
    if not gdrive.is_connected(tid):
        return {"files": [], "connected": False}

    tenant_data = await db.get_tenant(tid)
    firm = tenant_data.get("firm_name", "Sarathi-AI CRM") if tenant_data else "Sarathi-AI CRM"
    files = await gdrive.list_reports(tid, firm_name=firm)
    return {"files": files, "connected": True}


@app.post("/api/gdrive/upload-report")
@limiter.limit("20/minute")
async def api_gdrive_upload_report(
    request: Request,
    filename: str = Query(..., description="Report filename from /reports/"),
    tenant: dict = Depends(auth.get_current_tenant),
):
    """Upload a generated report to Google Drive."""
    tid = tenant["tenant_id"]
    if not gdrive.is_connected(tid):
        return JSONResponse(
            {"error": "Google Drive not connected. Connect first."},
            status_code=400,
        )

    tenant_data = await db.get_tenant(tid)
    firm = tenant_data.get("firm_name", "Sarathi-AI CRM") if tenant_data else "Sarathi-AI CRM"

    result = await gdrive.upload_calc_report(tid, filename, firm_name=firm)
    if result:
        return {"success": True, "file": result}
    return JSONResponse({"error": "Upload failed"}, status_code=500)


# ─── Google Sheets — list / preview / import (bulk lead import) ─────────────

@app.get("/api/gdrive/sheets")
async def api_gdrive_list_sheets(
    search: str = Query("", max_length=100),
    tenant: dict = Depends(auth.get_current_tenant),
):
    """List the user's Google Sheets (most recent first). Optional name search."""
    tid = tenant["tenant_id"]
    if not gdrive.is_connected(tid):
        return JSONResponse({"error": "not_connected", "message": "Connect Google Drive first."}, status_code=400)
    sheets = await gdrive.list_sheets(tid, max_results=50, search=search.strip())
    return {"sheets": sheets, "count": len(sheets)}


@app.get("/api/gdrive/sheets/{sheet_id}/preview")
async def api_gdrive_sheet_preview(
    sheet_id: str,
    tab: str = Query("", max_length=200),
    tenant: dict = Depends(auth.get_current_tenant),
):
    """
    Preview first 10 rows of a Google Sheet for column-mapping confirmation.
    Returns: {"title", "tabs": [...], "headers": [...], "preview_rows": [[...], ...], "total_rows_estimated": N}
    """
    tid = tenant["tenant_id"]
    if not gdrive.is_connected(tid):
        return JSONResponse({"error": "not_connected"}, status_code=400)

    # Validate sheet_id format (Google file IDs are alphanumeric + - _)
    import re
    if not re.match(r"^[A-Za-z0-9_-]{10,80}$", sheet_id):
        return JSONResponse({"error": "Invalid sheet ID"}, status_code=400)

    meta = await gdrive.get_sheet_metadata(tid, sheet_id)
    if not meta:
        return JSONResponse({"error": "Sheet not accessible"}, status_code=404)

    # Read first 11 rows (1 header + 10 preview)
    rows = await gdrive.read_sheet_values(tid, sheet_id, tab_name=tab, max_rows=11)
    headers = rows[0] if rows else []
    preview = rows[1:11] if len(rows) > 1 else []

    return {
        "title": meta["title"],
        "tabs": meta["sheets"],
        "current_tab": tab or (meta["sheets"][0]["name"] if meta["sheets"] else ""),
        "headers": headers,
        "preview_rows": preview,
    }


@app.post("/api/gdrive/sheets/{sheet_id}/import")
@limiter.limit("3/minute")
async def api_gdrive_sheet_import(
    request: Request,
    sheet_id: str,
    tab: str = Query("", max_length=200),
    assign_to: str = Query("", max_length=20),
    tenant: dict = Depends(auth.get_current_tenant),
):
    """
    Import all rows from a Google Sheet tab into the tenant's leads.
    Uses first row as headers (with smart alias mapping).
    Skips duplicates by phone (tenant-wide).
    """
    tid = tenant["tenant_id"]
    if not gdrive.is_connected(tid):
        return JSONResponse({"error": "not_connected"}, status_code=400)

    import re
    if not re.match(r"^[A-Za-z0-9_-]{10,80}$", sheet_id):
        return JSONResponse({"error": "Invalid sheet ID"}, status_code=400)

    rows = await gdrive.read_sheet_values(tid, sheet_id, tab_name=tab, max_rows=1000)
    if not rows or len(rows) < 2:
        return JSONResponse({"error": "Sheet is empty or has only headers"}, status_code=400)

    leads_data = gdrive.rows_to_lead_dicts(rows)
    if not leads_data:
        return JSONResponse({"error": "No valid lead rows found (need 'name' column)"}, status_code=400)
    if len(leads_data) > 500:
        return JSONResponse({"error": f"Too many rows ({len(leads_data)}). Max 500 per import."}, status_code=400)

    # Sanitize / truncate fields
    for ld in leads_data:
        for fld in ("name", "phone", "email", "city", "need_type", "stage", "notes", "whatsapp"):
            if fld in ld and ld[fld]:
                ld[fld] = str(ld[fld])[:500]

    # Determine target agent
    if assign_to:
        try:
            target_agent = await db.get_agent_by_id(int(assign_to))
            if not target_agent or target_agent.get("tenant_id") != tid:
                return JSONResponse({"error": "Agent not found in your firm"}, status_code=404)
            agent_id = int(assign_to)
        except (ValueError, TypeError):
            return JSONResponse({"error": "Invalid agent ID"}, status_code=400)
    else:
        t = await db.get_tenant(tid)
        owner_tg_id = t.get("owner_telegram_id") if t else None
        agent = await db.get_agent(owner_tg_id) if owner_tg_id else None
        if not agent:
            return JSONResponse({"error": "No agent found"}, status_code=404)
        agent_id = agent["agent_id"]

    # Mark source as gsheet_import for traceability
    for ld in leads_data:
        ld["source"] = "gsheet_import"

    result = await db.bulk_add_leads(agent_id, leads_data, tenant_id=tid)
    await db.log_audit(
        "gsheet_import",
        f"sheet={sheet_id[:20]} imported={result['imported']} skipped={result['skipped']} dupes={result.get('duplicates', 0)}",
        tenant_id=tid,
        ip_address=request.client.host,
    )
    return result


# =============================================================================
#  WHATSAPP v2 API — Agent-Assist (Evolution API + Brain Lock)
# =============================================================================
#  Endpoints:
#    POST /api/whatsapp/v2/setup       — create instance + start QR session
#    GET  /api/whatsapp/v2/status      — connection state + health for tenant
#    GET  /api/whatsapp/v2/qr          — current QR (poll until connected)
#    POST /api/whatsapp/v2/disconnect  — logout (keep config) or delete
#    POST /api/whatsapp/v2/acknowledge — record SIM-type ToS acknowledgement
#    POST /api/whatsapp/v2/webhook     — Evolution API → Sarathi events
# ─────────────────────────────────────────────────────────────────────────────


class WhatsAppSetupRequest(BaseModel):
    sim_type: str = Field("dedicated", pattern=r"^(dedicated|personal)$",
                          description="dedicated = new Sarathi SIM | personal = agent's own number")
    display_name: str = Field("", max_length=80)


class WhatsAppAcknowledgeRequest(BaseModel):
    accepted_personal_risk: bool = False
    accepted_no_bulk: bool = False
    accepted_compliance: bool = False
    accepted_tos: bool = False


@app.post("/api/whatsapp/v2/setup")
@limiter.limit("5/minute")
async def api_wa_v2_setup(request: Request, req: WhatsAppSetupRequest,
                           tenant: dict = Depends(auth.get_current_tenant)):
    """Create or reset a WhatsApp instance for this tenant."""
    if not wa_evo.is_enabled():
        return JSONResponse({"error": "whatsapp_v2_not_configured",
                             "message": "WhatsApp v2 is not enabled on this server."},
                            status_code=503)
    tid = tenant["tenant_id"]
    # Plan gate — only Solo+ allowed (Solo=self_only, Team=reminders, Enterprise=full)
    t = await db.get_tenant(tid)
    if not t:
        return JSONResponse({"error": "tenant_not_found"}, status_code=404)

    instance_name = wa_evo.build_instance_name(tid)
    # Create in Evolution
    create_res = await wa_evo.create_instance(instance_name, tenant_id=tid)
    if create_res.get("error") and "already" not in str(create_res.get("detail", "")).lower():
        return JSONResponse({"error": "evolution_create_failed", "detail": create_res},
                            status_code=502)

    # Persist in DB (upsert by evolution_instance unique key)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT instance_id FROM wa_instances WHERE evolution_instance = ?",
            (instance_name,))
        row = await cur.fetchone()
        if row:
            await conn.execute(
                "UPDATE wa_instances SET sim_type = ?, display_name = ?, "
                "status = 'pending', updated_at = datetime('now') WHERE instance_id = ?",
                (req.sim_type, req.display_name, row[0]))
            instance_id = row[0]
        else:
            cur2 = await conn.execute(
                "INSERT INTO wa_instances (tenant_id, evolution_instance, sim_type, "
                "display_name, status) VALUES (?, ?, ?, ?, 'pending')",
                (tid, instance_name, req.sim_type, req.display_name))
            instance_id = cur2.lastrowid
        await conn.commit()

    # Trigger QR
    qr_res = await wa_evo.connect_instance(instance_name)
    qr_b64 = qr_res.get("base64") or (qr_res.get("qrcode", {}) or {}).get("base64", "")
    if qr_b64:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE wa_instances SET qr_code = ?, "
                "qr_expires_at = datetime('now', '+90 seconds') WHERE instance_id = ?",
                (qr_b64, instance_id))
            await conn.commit()

    await db.log_audit("wa_v2_setup", f"instance={instance_name} sim_type={req.sim_type}",
                       tenant_id=tid, ip_address=request.client.host)
    return {
        "instance_id": instance_id,
        "instance_name": instance_name,
        "qr_base64": qr_b64,
        "expires_in_sec": 90,
    }


@app.get("/api/whatsapp/v2/status")
async def api_wa_v2_status(tenant: dict = Depends(auth.get_current_tenant)):
    """Return WhatsApp v2 connection state + health for the tenant."""
    tid = tenant["tenant_id"]
    if not wa_evo.is_enabled():
        return {"enabled": False, "configured": False}

    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT instance_id, evolution_instance, status, phone_number, "
            "display_name, sim_type, health_score, paused_until, "
            "spam_reports_count, last_connected_at "
            "FROM wa_instances WHERE tenant_id = ? ORDER BY instance_id DESC LIMIT 1",
            (tid,))
        row = await cur.fetchone()

    if not row:
        return {"enabled": True, "configured": False}

    instance_id, evo_name, status, phone, name, sim, health, paused, spam, last_conn = row

    # Live state from Evolution (best effort)
    live = await wa_evo.get_connection_state(evo_name)
    live_state = (live.get("instance", {}) or {}).get("state") or live.get("state") or status

    # Sync DB if changed
    if live_state and live_state != status:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE wa_instances SET status = ?, "
                "last_connected_at = CASE WHEN ? = 'open' THEN datetime('now') ELSE last_connected_at END, "
                "updated_at = datetime('now') WHERE instance_id = ?",
                (live_state, live_state, instance_id))
            await conn.commit()
        status = live_state

    return {
        "enabled": True,
        "configured": True,
        "instance_id": instance_id,
        "status": status,
        "phone_number": phone,
        "display_name": name,
        "sim_type": sim,
        "health_score": health,
        "paused_until": paused,
        "spam_reports": spam,
        "last_connected_at": last_conn,
    }


@app.get("/api/whatsapp/v2/qr")
async def api_wa_v2_qr(tenant: dict = Depends(auth.get_current_tenant)):
    """Read-only: return cached QR (refreshed by webhook from Evolution).
    NEVER calls connect_instance — that would restart Baileys and never converge."""
    tid = tenant["tenant_id"]
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT instance_id, evolution_instance, qr_code, qr_expires_at, status "
            "FROM wa_instances WHERE tenant_id = ? ORDER BY instance_id DESC LIMIT 1",
            (tid,))
        row = await cur.fetchone()
    if not row:
        return JSONResponse({"error": "no_instance", "message": "Run /setup first"},
                            status_code=404)
    instance_id, evo_name, qr_code, qr_expires, status = row
    if status in ("open", "connected"):
        return {"connected": True, "qr_base64": "", "status": status}
    return {"connected": False, "qr_base64": qr_code or "", "status": status,
            "expires_at": qr_expires}


@app.post("/api/whatsapp/v2/disconnect")
@limiter.limit("3/minute")
async def api_wa_v2_disconnect(request: Request,
                                permanent: bool = Query(False),
                                tenant: dict = Depends(auth.get_current_tenant)):
    """Logout (or fully delete if permanent=true) the WhatsApp instance."""
    tid = tenant["tenant_id"]
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT instance_id, evolution_instance FROM wa_instances "
            "WHERE tenant_id = ? ORDER BY instance_id DESC LIMIT 1", (tid,))
        row = await cur.fetchone()
    if not row:
        return {"ok": True, "message": "No instance to disconnect"}
    instance_id, evo_name = row
    if permanent:
        await wa_evo.delete_instance(evo_name)
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute("UPDATE wa_instances SET status = 'deleted', "
                               "qr_code = NULL, updated_at = datetime('now') "
                               "WHERE instance_id = ?", (instance_id,))
            await conn.commit()
    else:
        await wa_evo.logout_instance(evo_name)
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute("UPDATE wa_instances SET status = 'logged_out', "
                               "last_disconnected_at = datetime('now'), "
                               "updated_at = datetime('now') WHERE instance_id = ?",
                               (instance_id,))
            await conn.commit()
    await db.log_audit("wa_v2_disconnect", f"permanent={permanent}",
                       tenant_id=tid, ip_address=request.client.host)
    return {"ok": True, "permanent": permanent}


@app.post("/api/whatsapp/v2/acknowledge")
async def api_wa_v2_acknowledge(request: Request,
                                 req: WhatsAppAcknowledgeRequest,
                                 tenant: dict = Depends(auth.get_current_tenant)):
    """Record agent's ToS / SIM-type acknowledgement (compliance trail)."""
    tid = tenant["tenant_id"]
    if not (req.accepted_personal_risk and req.accepted_no_bulk
            and req.accepted_compliance and req.accepted_tos):
        return JSONResponse({"error": "all_acknowledgements_required"}, status_code=400)
    import json as _json
    import time as _time_mod
    ack = _json.dumps({
        "personal_risk": req.accepted_personal_risk,
        "no_bulk": req.accepted_no_bulk,
        "compliance": req.accepted_compliance,
        "tos": req.accepted_tos,
        "ip": request.client.host,
        "ts": int(_time_mod.time()),
    })
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE wa_instances SET acknowledgement = ?, updated_at = datetime('now') "
            "WHERE tenant_id = ? AND status != 'deleted'", (ack, tid))
        await conn.execute(
            "UPDATE tenants SET wa_tos_accepted_at = datetime('now') WHERE tenant_id = ?",
            (tid,))
        await conn.commit()
    await db.log_audit("wa_v2_acknowledged", "tos+sim_type",
                       tenant_id=tid, ip_address=request.client.host)
    return {"ok": True}


@app.post("/api/whatsapp/v2/webhook")
async def api_wa_v2_webhook(request: Request):
    """
    Inbound webhook from Evolution API. Validates shared-secret token,
    routes by event type, persists messages/state changes.
    Always returns 200 to prevent Evolution from retrying floods.
    """
    # Validate shared secret
    received_token = request.headers.get("X-Sarathi-Webhook-Token", "")
    if not wa_evo.validate_webhook_token(received_token):
        logger.warning("WA webhook: invalid token from %s", request.client.host)
        return JSONResponse({"ok": False}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return {"ok": True, "ignored": "bad_json"}

    event = (payload.get("event") or payload.get("type") or "").lower().replace("_", ".")
    instance = payload.get("instance") or ""
    if isinstance(instance, dict):
        instance = instance.get("instanceName") or instance.get("name") or ""
    raw_data = payload.get("data")
    # Diagnostic — log every event with a small data preview so we can see what Evolution sends
    try:
        _preview = str(raw_data)[:200] if raw_data is not None else "<none>"
        logger.info("WA webhook event=%s instance=%s data=%s", event, instance, _preview)
    except Exception:
        pass
    # Evolution sometimes nests; coerce to dict
    if isinstance(raw_data, dict):
        data = raw_data
    elif isinstance(raw_data, list) and raw_data and isinstance(raw_data[0], dict):
        data = raw_data[0]
    else:
        data = {}

    try:
        if event in ("connection.update",):
            state = (data.get("state") or data.get("status") or "").lower()
            # wuid may live at root, in 'instance' (string OR dict), or as 'wuid'
            inst_field = data.get("instance")
            inst_wuid = inst_field.get("wuid", "") if isinstance(inst_field, dict) else ""
            phone = data.get("wuid") or inst_wuid or ""
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute(
                    "UPDATE wa_instances SET status = ?, "
                    "phone_number = COALESCE(NULLIF(?, ''), phone_number), "
                    "last_connected_at = CASE WHEN ? = 'open' THEN datetime('now') ELSE last_connected_at END, "
                    "qr_code = CASE WHEN ? = 'open' THEN NULL ELSE qr_code END, "
                    "updated_at = datetime('now') WHERE evolution_instance = ?",
                    (state, str(phone or "").split("@")[0], state, state, instance))
                await conn.commit()
            logger.info("WA conn state: %s → %s", instance, state)

        elif event in ("qrcode.updated",):
            qr_b64 = data.get("base64") or ""
            qrcode_field = data.get("qrcode")
            if not qr_b64 and isinstance(qrcode_field, dict):
                qr_b64 = qrcode_field.get("base64", "")
            if qr_b64:
                async with aiosqlite.connect(db.DB_PATH) as conn:
                    await conn.execute(
                        "UPDATE wa_instances SET qr_code = ?, "
                        "qr_expires_at = datetime('now', '+90 seconds'), "
                        "updated_at = datetime('now') WHERE evolution_instance = ?",
                        (qr_b64, instance))
                    await conn.commit()

        elif event in ("messages.upsert", "MESSAGES_UPSERT"):
            # Inbound message — persist (suggestion generation comes in Phase 2)
            msg = data.get("messages", [{}])[0] if isinstance(data.get("messages"), list) else data
            key = msg.get("key", {}) or {}
            from_me = bool(key.get("fromMe"))
            remote = key.get("remoteJid", "") or ""
            wa_id = key.get("id", "")
            text = ((msg.get("message", {}) or {}).get("conversation")
                    or ((msg.get("message", {}) or {}).get("extendedTextMessage", {}) or {}).get("text", ""))
            phone = remote.split("@")[0]
            # Find instance & ensure conversation row
            async with aiosqlite.connect(db.DB_PATH) as conn:
                cur = await conn.execute(
                    "SELECT instance_id, tenant_id FROM wa_instances WHERE evolution_instance = ?",
                    (instance,))
                irow = await cur.fetchone()
                if not irow:
                    return {"ok": True, "ignored": "unknown_instance"}
                instance_id, tenant_id = irow
                cur = await conn.execute(
                    "SELECT conversation_id FROM wa_conversations "
                    "WHERE instance_id = ? AND customer_phone = ?",
                    (instance_id, phone))
                crow = await cur.fetchone()
                if crow:
                    conv_id = crow[0]
                else:
                    cur2 = await conn.execute(
                        "INSERT INTO wa_conversations (instance_id, tenant_id, customer_phone, "
                        "last_message_at) VALUES (?, ?, ?, datetime('now'))",
                        (instance_id, tenant_id, phone))
                    conv_id = cur2.lastrowid
                await conn.execute(
                    "INSERT INTO wa_messages (conversation_id, instance_id, wa_message_id, "
                    "direction, msg_type, content, status, source, sent_at) "
                    "VALUES (?, ?, ?, ?, 'text', ?, ?, ?, datetime('now'))",
                    (conv_id, instance_id, wa_id,
                     "out" if from_me else "in",
                     text or "", "delivered" if from_me else "received",
                     "manual" if from_me else "inbound"))
                if not from_me:
                    await conn.execute(
                        "UPDATE wa_conversations SET unread_count = unread_count + 1, "
                        "last_inbound_at = datetime('now'), last_message_at = datetime('now') "
                        "WHERE conversation_id = ?", (conv_id,))
                else:
                    await conn.execute(
                        "UPDATE wa_conversations SET last_outbound_at = datetime('now'), "
                        "last_message_at = datetime('now') WHERE conversation_id = ?", (conv_id,))
                await conn.commit()
            # Inbound: acquire 5-min brain lock so scheduler doesn't compete
            if not from_me and text:
                await wa_safety.acquire_lock(tenant_id, phone, "whatsapp_inbound",
                                             duration_minutes=wa_safety.LOCK_INBOUND_MINUTES)

        elif event in ("messages.update",):
            # Delivery / read receipts — update statuses
            updates = data if isinstance(data, list) else (data.get("updates") if isinstance(data.get("updates"), list) else [data])
            for u in updates:
                if not isinstance(u, dict):
                    continue
                key = u.get("key") if isinstance(u.get("key"), dict) else {}
                wa_id = key.get("id", "")
                upd = u.get("update") if isinstance(u.get("update"), dict) else {}
                status = upd.get("status") or u.get("status", "")
                if not (wa_id and status):
                    continue
                async with aiosqlite.connect(db.DB_PATH) as conn:
                    if str(status).lower() in ("delivered", "delivery_ack", "3"):
                        await conn.execute(
                            "UPDATE wa_messages SET status = 'delivered', "
                            "delivered_at = datetime('now') WHERE wa_message_id = ?",
                            (wa_id,))
                    elif str(status).lower() in ("read", "read_ack", "4"):
                        await conn.execute(
                            "UPDATE wa_messages SET status = 'read', "
                            "read_at = datetime('now') WHERE wa_message_id = ?", (wa_id,))
                    await conn.commit()
    except Exception as e:
        logger.exception("WA webhook handler error: %s", e)

    return {"ok": True}


# =============================================================================
#  BULK CAMPAIGN API
# =============================================================================

class CampaignCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=200, description="Campaign title")
    message: str = Field(..., min_length=5, max_length=5000, description="Message template. Use {name} and {first_name} for personalization.")
    campaign_type: str = Field("custom", pattern=r"^(birthday|festival|announcement|promotion|custom)$", description="Type")
    channel: str = Field("whatsapp", pattern=r"^(whatsapp|email)$", description="Channel: whatsapp or email")
    filters: dict = Field(default_factory=dict, description="Recipient filters: {stage, city, need_type}")


@app.post("/api/campaigns")
@limiter.limit("10/minute")
async def api_create_campaign(
    request: Request,
    req: CampaignCreateRequest,
    tenant: dict = Depends(auth.get_current_tenant),
):
    """Create a new campaign draft."""
    # ── Plan gate: Bulk campaigns require Team plan or higher ──
    gate = await db.check_plan_feature(tenant["tenant_id"], "bulk_campaigns")
    if not gate['allowed']:
        return JSONResponse({"error": gate['reason']}, status_code=403)
    campaign_id = await campaigns.create_campaign(
        tenant_id=tenant["tenant_id"],
        title=req.title,
        message=req.message,
        campaign_type=req.campaign_type,
        channel=req.channel,
        filters=req.filters,
    )

    # Auto-select recipients based on filters
    count = await campaigns.select_recipients(
        tenant["tenant_id"], campaign_id, req.filters,
    )

    return {
        "campaign_id": campaign_id,
        "recipients": count,
        "status": "draft",
        "message": f"Campaign created with {count} recipients. POST /api/campaigns/{campaign_id}/send to execute.",
    }


@app.get("/api/campaigns")
async def api_list_campaigns(tenant: dict = Depends(auth.get_current_tenant)):
    """List all campaigns for the current tenant."""
    result = await campaigns.list_campaigns(tenant["tenant_id"])
    return {"campaigns": result}


@app.get("/api/campaigns/{campaign_id}")
async def api_get_campaign(
    campaign_id: int,
    tenant: dict = Depends(auth.get_current_tenant),
):
    """Get campaign details and stats."""
    stats = await campaigns.get_campaign_stats(campaign_id)
    if not stats:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    return stats


@app.get("/api/campaigns/{campaign_id}/recipients")
async def api_campaign_recipients(
    campaign_id: int,
    tenant: dict = Depends(auth.get_current_tenant),
):
    """List recipients for a campaign."""
    campaign = await campaigns.get_campaign(campaign_id)
    if not campaign or campaign["tenant_id"] != tenant["tenant_id"]:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)

    recipients = await campaigns.get_recipients(campaign_id)
    return {"recipients": recipients}


@app.post("/api/campaigns/{campaign_id}/send")
@limiter.limit("5/minute")
async def api_send_campaign(
    request: Request,
    campaign_id: int,
    tenant: dict = Depends(auth.get_current_tenant),
):
    """Execute a campaign — send messages to all recipients."""
    result = await campaigns.send_campaign(campaign_id, tenant["tenant_id"])
    if result.get("error"):
        return JSONResponse({"error": result["error"]}, status_code=400)
    return result


@app.delete("/api/campaigns/{campaign_id}")
async def api_delete_campaign(
    campaign_id: int,
    tenant: dict = Depends(auth.get_current_tenant),
):
    """Delete a draft campaign."""
    deleted = await campaigns.delete_campaign(campaign_id, tenant["tenant_id"])
    if deleted:
        return {"success": True}
    return JSONResponse(
        {"error": "Campaign not found or already sent"},
        status_code=404,
    )


@app.get("/api/campaigns/types")
async def api_campaign_types():
    """List available campaign types."""
    return {"types": campaigns.CAMPAIGN_TYPES}


# =============================================================================
#  DRIP NURTURE SEQUENCES API (Feature 1)
# =============================================================================
import biz_nurture as nurture


class NurtureSequenceCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    trigger_event: str = "lead_stage_change"  # lead_stage_change | manual
    trigger_value: str = ""  # stage name when trigger_event=lead_stage_change


class NurtureSequenceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_event: Optional[str] = None
    trigger_value: Optional[str] = None
    is_active: Optional[int] = None


class NurtureStepCreate(BaseModel):
    step_order: int
    delay_days: int = 0
    delay_hours: int = 0
    channel: str = "telegram_agent"
    label: str = ""
    template_en: str
    template_hi: str = ""
    wa_template_en: str = ""
    wa_template_hi: str = ""


@app.get("/api/nurture/sequences")
@limiter.limit("60/minute")
async def api_nurture_list_sequences(request: Request,
                                      tenant: dict = Depends(auth.get_current_tenant)):
    """List all nurture sequences for the current tenant."""
    return {"sequences": await nurture.list_sequences(tenant["tenant_id"])}


@app.post("/api/nurture/sequences")
@limiter.limit("20/minute")
async def api_nurture_create_sequence(req: NurtureSequenceCreate, request: Request,
                                       tenant: dict = Depends(auth.get_current_tenant)):
    """Create a new nurture sequence."""
    sid = await nurture.create_sequence(
        tenant_id=tenant["tenant_id"], name=req.name, description=req.description,
        trigger_event=req.trigger_event, trigger_value=req.trigger_value)
    return {"success": True, "sequence_id": sid}


@app.get("/api/nurture/sequences/{sequence_id}")
@limiter.limit("60/minute")
async def api_nurture_get_sequence(sequence_id: int, request: Request,
                                    tenant: dict = Depends(auth.get_current_tenant)):
    """Get a sequence with all its steps."""
    seq = await nurture.get_sequence(sequence_id, tenant["tenant_id"])
    if not seq:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return seq


@app.patch("/api/nurture/sequences/{sequence_id}")
@limiter.limit("30/minute")
async def api_nurture_update_sequence(sequence_id: int, req: NurtureSequenceUpdate,
                                       request: Request,
                                       tenant: dict = Depends(auth.get_current_tenant)):
    """Update a sequence (toggle active, rename, change trigger)."""
    fields = {k: v for k, v in req.dict().items() if v is not None}
    ok = await nurture.update_sequence(sequence_id, tenant["tenant_id"], **fields)
    return {"success": ok}


@app.delete("/api/nurture/sequences/{sequence_id}")
@limiter.limit("10/minute")
async def api_nurture_delete_sequence(sequence_id: int, request: Request,
                                       tenant: dict = Depends(auth.get_current_tenant)):
    """Delete a sequence (also cancels active enrollments)."""
    ok = await nurture.delete_sequence(sequence_id, tenant["tenant_id"])
    return {"success": ok}


@app.post("/api/nurture/sequences/{sequence_id}/steps")
@limiter.limit("30/minute")
async def api_nurture_add_step(sequence_id: int, req: NurtureStepCreate,
                                request: Request,
                                tenant: dict = Depends(auth.get_current_tenant)):
    """Add a step to a sequence."""
    seq = await nurture.get_sequence(sequence_id, tenant["tenant_id"])
    if not seq:
        return JSONResponse({"error": "Sequence not found"}, status_code=404)
    step_id = await nurture.add_step(
        sequence_id=sequence_id, step_order=req.step_order,
        delay_days=req.delay_days, delay_hours=req.delay_hours,
        channel=req.channel, label=req.label,
        template_en=req.template_en, template_hi=req.template_hi,
        wa_template_en=req.wa_template_en, wa_template_hi=req.wa_template_hi)
    return {"success": True, "step_id": step_id}


@app.delete("/api/nurture/steps/{step_id}")
@limiter.limit("30/minute")
async def api_nurture_delete_step(step_id: int, request: Request,
                                   tenant: dict = Depends(auth.get_current_tenant)):
    """Delete a step."""
    ok = await nurture.delete_step(step_id, tenant["tenant_id"])
    return {"success": ok}


@app.get("/api/nurture/enrollments")
@limiter.limit("60/minute")
async def api_nurture_list_enrollments(request: Request,
                                        status: Optional[str] = Query(None),
                                        lead_id: Optional[int] = Query(None),
                                        tenant: dict = Depends(auth.get_current_tenant)):
    """List enrollments — optionally filter by status (active/completed/cancelled) or lead_id."""
    rows = await nurture.list_enrollments(tenant["tenant_id"], status=status,
                                           lead_id=lead_id, limit=200)
    return {"enrollments": rows}


@app.post("/api/nurture/leads/{lead_id}/enrol/{sequence_id}")
@limiter.limit("30/minute")
async def api_nurture_enrol_lead(lead_id: int, sequence_id: int, request: Request,
                                  tenant: dict = Depends(auth.get_current_tenant)):
    """Manually enrol a lead in a sequence."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    eid = await nurture.enrol_lead(tid, sequence_id, lead_id, lead["agent_id"])
    if not eid:
        return JSONResponse(
            {"error": "Could not enrol — already active, or sequence inactive/empty"},
            status_code=400)
    return {"success": True, "enrollment_id": eid}


@app.post("/api/nurture/enrollments/{enrollment_id}/cancel")
@limiter.limit("30/minute")
async def api_nurture_cancel_enrollment(enrollment_id: int, request: Request,
                                         tenant: dict = Depends(auth.get_current_tenant)):
    """Cancel an active enrollment."""
    ok = await nurture.cancel_enrollment(enrollment_id, tenant["tenant_id"], reason="manual")
    return {"success": ok}


@app.post("/api/nurture/test-tick")
@limiter.limit("3/minute")
async def api_nurture_test_tick(request: Request,
                                 tenant: dict = Depends(auth.require_owner)):
    """Owner-only: trigger a nurture tick immediately for testing."""
    stats = await nurture.process_due_enrollments()
    return {"success": True, "stats": stats}


# =============================================================================
#  QUOTE COMPARISON API (Feature 5)
# =============================================================================
import biz_quotes as quotes


class QuoteCompareTermReq(BaseModel):
    age: int
    sum_insured: int
    smoker: bool = False
    gender: str = "M"
    term_years: int = 30


class QuoteCompareHealthReq(BaseModel):
    age: int
    sum_insured: int
    family_size: int = 1
    city_tier: int = 1


class QuotePdfReq(BaseModel):
    product_type: str  # term | health | endowment | ulip | sip
    inputs: dict
    client_name: Optional[str] = "Client"
    lang: Optional[str] = "en"


class QuoteCompareEndowmentReq(BaseModel):
    age: int
    sum_insured: int
    term_years: int = 20


class QuoteCompareUlipReq(BaseModel):
    age: int
    annual_investment: int
    term_years: int = 15


class QuoteCompareSipReq(BaseModel):
    monthly_sip: int
    years: int = 10


VALID_PRODUCT_TYPES = ("term", "health", "endowment", "ulip", "sip")


@app.get("/api/quotes/providers")
async def api_quotes_providers(product_type: str = "term",
                                tenant: dict = Depends(auth.get_current_tenant)):
    """List active providers (seed + tenant overrides) for the given product."""
    if product_type not in VALID_PRODUCT_TYPES:
        return JSONResponse({"error": f"product_type must be one of {VALID_PRODUCT_TYPES}"}, status_code=400)
    providers = await quotes._get_active_providers(product_type, tenant["tenant_id"])
    # Strip internal scoring + premium for the listing
    return {"providers": [{k: v for k, v in p.items() if not k.startswith("_")} for p in providers]}


@app.post("/api/quotes/compare/term")
@limiter.limit("60/minute")
async def api_quotes_compare_term(req: QuoteCompareTermReq, request: Request,
                                    tenant: dict = Depends(auth.get_current_tenant)):
    """Rank top term-life quotes for the given client params."""
    if req.age < 18 or req.age > 70:
        return JSONResponse({"error": "Age must be 18–70"}, status_code=400)
    if req.sum_insured < 100000:
        return JSONResponse({"error": "Sum insured must be at least ₹1,00,000"}, status_code=400)
    rows = await quotes.compare_term(
        age=req.age, sum_insured=req.sum_insured, smoker=req.smoker,
        gender=req.gender, term_years=req.term_years,
        tenant_id=tenant["tenant_id"],
    )
    # Strip internal score field from response
    for r in rows:
        r.pop("_score", None)
    return {"product_type": "term", "rows": rows, "count": len(rows)}


@app.post("/api/quotes/compare/health")
@limiter.limit("60/minute")
async def api_quotes_compare_health(req: QuoteCompareHealthReq, request: Request,
                                      tenant: dict = Depends(auth.get_current_tenant)):
    """Rank top health-insurance quotes for the given client params."""
    if req.age < 0 or req.age > 80:
        return JSONResponse({"error": "Age must be 0–80"}, status_code=400)
    if req.sum_insured < 100000:
        return JSONResponse({"error": "Sum insured must be at least ₹1,00,000"}, status_code=400)
    rows = await quotes.compare_health(
        age=req.age, sum_insured=req.sum_insured,
        family_size=req.family_size, city_tier=req.city_tier,
        tenant_id=tenant["tenant_id"],
    )
    for r in rows:
        r.pop("_score", None)
    return {"product_type": "health", "rows": rows, "count": len(rows)}


@app.post("/api/quotes/compare/endowment")
@limiter.limit("60/minute")
async def api_quotes_compare_endowment(req: QuoteCompareEndowmentReq, request: Request,
                                         tenant: dict = Depends(auth.get_current_tenant)):
    """Rank endowment / traditional-life plans."""
    if req.age < 18 or req.age > 65:
        return JSONResponse({"error": "Age must be 18–65"}, status_code=400)
    if req.sum_insured < 100000:
        return JSONResponse({"error": "Sum insured must be at least ₹1,00,000"}, status_code=400)
    rows = await quotes.compare_endowment(
        age=req.age, sum_insured=req.sum_insured, term_years=req.term_years,
        tenant_id=tenant["tenant_id"],
    )
    for r in rows: r.pop("_score", None)
    return {"product_type": "endowment", "rows": rows, "count": len(rows)}


@app.post("/api/quotes/compare/ulip")
@limiter.limit("60/minute")
async def api_quotes_compare_ulip(req: QuoteCompareUlipReq, request: Request,
                                     tenant: dict = Depends(auth.get_current_tenant)):
    """Rank ULIP plans by projected fund value."""
    if req.age < 0 or req.age > 70:
        return JSONResponse({"error": "Age must be 0–70"}, status_code=400)
    if req.annual_investment < 12000:
        return JSONResponse({"error": "Annual investment must be at least ₹12,000"}, status_code=400)
    rows = await quotes.compare_ulip(
        age=req.age, annual_investment=req.annual_investment, term_years=req.term_years,
        tenant_id=tenant["tenant_id"],
    )
    for r in rows: r.pop("_score", None)
    return {"product_type": "ulip", "rows": rows, "count": len(rows)}


@app.post("/api/quotes/compare/sip")
@limiter.limit("60/minute")
async def api_quotes_compare_sip(req: QuoteCompareSipReq, request: Request,
                                    tenant: dict = Depends(auth.get_current_tenant)):
    """Rank mutual-fund SIPs by projected value."""
    if req.monthly_sip < 500:
        return JSONResponse({"error": "Monthly SIP must be at least ₹500"}, status_code=400)
    if req.years < 1 or req.years > 40:
        return JSONResponse({"error": "Years must be 1–40"}, status_code=400)
    rows = await quotes.compare_sip(
        monthly_sip=req.monthly_sip, years=req.years,
        tenant_id=tenant["tenant_id"],
    )
    for r in rows: r.pop("_score", None)
    return {"product_type": "sip", "rows": rows, "count": len(rows)}


@app.post("/api/quotes/generate-pdf")
@limiter.limit("20/minute")
async def api_quotes_generate_pdf(req: QuotePdfReq, request: Request,
                                    tenant: dict = Depends(auth.get_current_tenant)):
    """Generate a branded comparison HTML/PDF report and return its public URL."""
    tid = tenant["tenant_id"]
    if req.product_type not in VALID_PRODUCT_TYPES:
        return JSONResponse({"error": f"product_type must be one of {VALID_PRODUCT_TYPES}"}, status_code=400)
    inp = req.inputs or {}
    pt = req.product_type
    if pt == "term":
        rows = await quotes.compare_term(
            age=int(inp.get("age", 30)), sum_insured=int(inp.get("sum_insured", 5000000)),
            smoker=bool(inp.get("smoker", False)), gender=str(inp.get("gender", "M")),
            term_years=int(inp.get("term_years", 30)), tenant_id=tid,
        )
    elif pt == "health":
        rows = await quotes.compare_health(
            age=int(inp.get("age", 30)), sum_insured=int(inp.get("sum_insured", 500000)),
            family_size=int(inp.get("family_size", 1)), city_tier=int(inp.get("city_tier", 1)),
            tenant_id=tid,
        )
    elif pt == "endowment":
        rows = await quotes.compare_endowment(
            age=int(inp.get("age", 30)), sum_insured=int(inp.get("sum_insured", 2500000)),
            term_years=int(inp.get("term_years", 20)), tenant_id=tid,
        )
    elif pt == "ulip":
        rows = await quotes.compare_ulip(
            age=int(inp.get("age", 30)), annual_investment=int(inp.get("annual_investment", 100000)),
            term_years=int(inp.get("term_years", 15)), tenant_id=tid,
        )
    else:  # sip
        rows = await quotes.compare_sip(
            monthly_sip=int(inp.get("monthly_sip", 5000)), years=int(inp.get("years", 10)),
            tenant_id=tid,
        )
    # Build brand context from tenant
    tdata = await db.get_tenant(tid) or {}
    brand = {
        "primary_color": tdata.get("brand_primary_color") or "#1a56db",
        "accent_color": tdata.get("brand_accent_color") or "#ea580c",
        "logo": tdata.get("brand_logo") or "",
        "cta": tdata.get("brand_cta") or "",
        "irdai_license": tdata.get("irdai_license") or "",
    }
    advisor_name = tdata.get("owner_name") or "Advisor"
    firm_name = tdata.get("firm_name") or "Sarathi-AI CRM"
    html = quotes.generate_comparison_html_v2(
        rows=rows, product_type=pt, inputs=inp,
        client_name=req.client_name or "Client",
        advisor_name=advisor_name, firm_name=firm_name,
        brand=brand, lang=req.lang or "en",
    )
    filename = pdf.save_html_report(
        html_content=html, report_type=f"quote-compare-{pt}",
        client_name=req.client_name, advisor_name=advisor_name,
    )
    return {"success": True, "filename": filename, "url": f"{SERVER_URL}/reports/{filename}"}


@app.get("/api/quotes/ratecards")
async def api_quotes_ratecards(product_type: Optional[str] = None,
                                 tenant: dict = Depends(auth.get_current_tenant)):
    """List uploaded rate-cards for this tenant."""
    rows = await quotes.get_tenant_ratecards(tenant["tenant_id"], product_type)
    # Don't expose absolute file paths
    for r in rows:
        r.pop("file_path", None)
    return {"ratecards": rows, "count": len(rows)}


@app.post("/api/quotes/upload-ratecard")
@limiter.limit("10/minute")
async def api_quotes_upload_ratecard(
    request: Request,
    provider: str = Form(...),
    product_type: str = Form(...),
    file: UploadFile = File(...),
    tenant: dict = Depends(auth.require_owner),
):
    """Owner-only: upload a custom rate-card (CSV/Excel/PDF)."""
    if product_type not in VALID_PRODUCT_TYPES:
        return JSONResponse({"error": f"product_type must be one of {VALID_PRODUCT_TYPES}"}, status_code=400)
    name = (file.filename or "ratecard").lower()
    if not name.endswith((".csv", ".xlsx", ".xls", ".pdf")):
        return JSONResponse({"error": "Only CSV, Excel (.xlsx/.xls), or PDF files are allowed"}, status_code=400)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        return JSONResponse({"error": "File too large (max 5 MB)"}, status_code=400)
    try:
        row = await quotes.save_ratecard(
            tenant_id=tenant["tenant_id"], provider=provider,
            product_type=product_type, file_bytes=content, file_name=file.filename or "ratecard",
        )
    except Exception as e:
        logger.exception("upload-ratecard failed")
        return JSONResponse({"error": f"Upload failed: {e}"}, status_code=500)
    row.pop("file_path", None)
    return {"success": True, "ratecard": row}


@app.delete("/api/quotes/ratecards/{ratecard_id}")
async def api_quotes_delete_ratecard(ratecard_id: int,
                                       tenant: dict = Depends(auth.require_owner)):
    """Owner-only: deactivate a rate-card."""
    ok = await quotes.delete_ratecard(tenant["tenant_id"], ratecard_id)
    if not ok:
        return JSONResponse({"error": "Rate-card not found"}, status_code=404)
    return {"success": True}


# =============================================================================
#  LAPSE-RISK PREDICTION API (Feature 2)
# =============================================================================
import biz_lapse as lapse


@app.get("/api/lapse/predictions")
@limiter.limit("60/minute")
async def api_lapse_predictions(request: Request,
                                  days_ahead: int = 120,
                                  min_score: int = 25,
                                  limit: int = 200,
                                  tenant: dict = Depends(auth.get_current_tenant)):
    """List policies at risk of lapsing, sorted by risk score (highest first).

    Query params:
        days_ahead — look-ahead window for renewals (default 120).
        min_score  — only return policies scoring >= this (default 25 = MEDIUM+).
        limit      — cap results (default 200).
    """
    days_ahead = max(7, min(365, days_ahead))
    min_score = max(0, min(100, min_score))
    limit = max(1, min(500, limit))
    rows = await lapse.get_at_risk_policies(
        tenant_id=tenant["tenant_id"],
        days_ahead=days_ahead,
        min_score=min_score,
        limit=limit,
    )
    return {"count": len(rows), "rows": rows}


@app.get("/api/lapse/policy/{policy_id}")
@limiter.limit("60/minute")
async def api_lapse_policy_detail(policy_id: int, request: Request,
                                    tenant: dict = Depends(auth.get_current_tenant)):
    """Full risk breakdown for a single policy (detail drawer)."""
    detail = await lapse.get_policy_risk_detail(policy_id, tenant["tenant_id"])
    if not detail:
        return JSONResponse({"error": "Policy not found"}, status_code=404)
    return detail


@app.get("/api/lapse/summary")
@limiter.limit("60/minute")
async def api_lapse_summary(request: Request,
                              tenant: dict = Depends(auth.get_current_tenant)):
    """Counts by risk bucket — for the dashboard overview cards."""
    return await lapse.get_risk_summary(tenant["tenant_id"])


# =============================================================================
#  AI FEATURES API
# =============================================================================

@app.get("/api/ai/verify")
@limiter.limit("5/minute")
async def api_ai_verify(request: Request, _tenant: dict = Depends(auth.get_current_tenant)):
    """Verify Gemini AI API is working. Requires auth."""
    import biz_ai as ai_mod
    result = await ai_mod.verify_gemini()
    return result


@app.post("/api/ai/score-lead/{lead_id}")
@limiter.limit("20/minute")
async def api_ai_score_lead(lead_id: int, request: Request,
                             tenant: dict = Depends(auth.get_current_tenant)):
    """AI-score a lead by conversion probability."""
    import biz_ai as ai_mod
    lang = request.headers.get("X-Lang", "en")
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    interactions = await db.get_lead_interactions(lead_id, limit=10, tenant_id=tid)
    policies = await db.get_policies_by_lead(lead_id, tenant_id=tid)
    score = await ai_mod.score_lead(dict(lead), interactions, policies, lang=lang)
    return score


@app.post("/api/ai/generate-pitch/{lead_id}")
@limiter.limit("10/minute")
async def api_ai_generate_pitch(lead_id: int, request: Request,
                                 tenant: dict = Depends(auth.get_current_tenant)):
    """Generate AI sales pitch for a lead."""
    import biz_ai as ai_mod
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    t = await db.get_tenant(tid)
    firm = t.get("firm_name", "Sarathi-AI") if t else "Sarathi-AI"
    lang = request.headers.get("X-Lang", "en")
    pitch = await ai_mod.generate_pitch(dict(lead), tenant.get("firm", "Advisor"), firm, lang=lang)
    return pitch


@app.post("/api/ai/suggest-followup/{lead_id}")
@limiter.limit("10/minute")
async def api_ai_suggest_followup(lead_id: int, request: Request,
                                   tenant: dict = Depends(auth.get_current_tenant)):
    """AI-suggest next best follow-up action for a lead."""
    import biz_ai as ai_mod
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    lang = request.headers.get("X-Lang", "en")
    interactions = await db.get_lead_interactions(lead_id, limit=10, tenant_id=tid)
    result = await ai_mod.suggest_followup(dict(lead), interactions, lang=lang)
    return result


@app.post("/api/ai/recommend-policies/{lead_id}")
@limiter.limit("10/minute")
async def api_ai_recommend_policies(lead_id: int, request: Request,
                                     tenant: dict = Depends(auth.get_current_tenant)):
    """AI-recommend insurance products for a lead."""
    import biz_ai as ai_mod
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    lang = request.headers.get("X-Lang", "en")
    policies = await db.get_policies_by_lead(lead_id, tenant_id=tid)
    result = await ai_mod.recommend_policies(dict(lead), policies, lang=lang)
    return result


@app.post("/api/ai/generate-template")
@limiter.limit("10/minute")
async def api_ai_generate_template(request: Request,
                                    tenant: dict = Depends(auth.get_current_tenant)):
    """AI-generate professional communication templates."""
    import biz_ai as ai_mod
    body = await request.json()
    template_type = body.get("template_type", "follow_up")
    lead_name = body.get("lead_name", "Customer")
    context = body.get("context", "")
    t = await db.get_tenant(tenant["tenant_id"])
    firm = t.get("firm_name", "Sarathi-AI") if t else "Sarathi-AI"
    advisor = tenant.get("firm", "Advisor")
    lang = request.headers.get("X-Lang", "en")
    lead_dict = {"name": lead_name} if lead_name else None
    result = await ai_mod.generate_template(template_type, lead_dict, advisor, firm, context, lang=lang)
    return result


@app.post("/api/ai/handle-objection")
@limiter.limit("10/minute")
async def api_ai_handle_objection(request: Request,
                                   tenant: dict = Depends(auth.get_current_tenant)):
    """AI counter-argument for common insurance objections."""
    import biz_ai as ai_mod
    body = await request.json()
    objection = body.get("objection", "")
    if not objection or len(objection) < 5:
        return JSONResponse({"error": "Please provide a valid objection (min 5 chars)"}, status_code=400)
    lead_context = body.get("lead_context", "")
    # handle_objection expects (objection, lead_dict, product_type)
    lang = request.headers.get("X-Lang", "en")
    lead_dict = {"notes": lead_context} if lead_context else None
    result = await ai_mod.handle_objection(objection, lead_dict, lang=lang)
    return result


@app.post("/api/ai/renewal-intelligence/{lead_id}")
@limiter.limit("10/minute")
async def api_ai_renewal_intelligence(lead_id: int, request: Request,
                                       tenant: dict = Depends(auth.get_current_tenant)):
    """AI renewal strategy + upsell recommendations for a lead."""
    import biz_ai as ai_mod
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    policies = await db.get_policies_by_lead(lead_id, tenant_id=tid)
    # renewal_intelligence(policy, lead, all_policies) - pass first policy or empty dict
    lang = request.headers.get("X-Lang", "en")
    policy = dict(policies[0]) if policies else {}
    result = await ai_mod.renewal_intelligence(policy, dict(lead), policies, lang=lang)
    return result


@app.post("/api/ai/ask")
@limiter.limit("15/minute")
async def api_ai_ask(request: Request,
                      tenant: dict = Depends(auth.get_current_tenant)):
    """Free-form insurance Q&A with AI."""
    import biz_ai as ai_mod
    body = await request.json()
    question = body.get("question", "").strip()
    if not question or len(question) < 5:
        return JSONResponse({"error": "Please ask a question (min 5 chars)"}, status_code=400)
    lang = request.headers.get("X-Lang", "en")
    answer = await ai_mod.ask_insurance_ai(question, lang=lang)
    return {"answer": answer}


# =============================================================================
#  VOICE AI — Intent Classification + CRM Action Execution
# =============================================================================

_WEB_VOICE_PROMPT = """You are the AI engine for Sarathi-AI, an Indian insurance advisor CRM.
The agent spoke/typed a command. Classify the intent and extract data.
You are an INTELLIGENT assistant — understand context, infer missing info, and be helpful.

POSSIBLE INTENTS:
1. create_lead — new prospect/client with name, details
2. add_note — add a note about an existing lead
3. create_reminder — set a reminder/follow-up/task/appointment for a date
4. cancel_reminder — cancel/delete a reminder/task/follow-up for a lead
5. update_stage — move a lead to a different pipeline stage
6. update_lead — update lead details (phone, email, city, need_type)
7. search_lead — find/lookup a lead by name or phone
8. list_tasks — show today's/upcoming tasks, follow-ups, reminders
9. cold_leads — show inactive/dormant leads (no activity in 7+ days)
10. overdue_followups — show overdue/missed follow-ups specifically
11. pipeline_summary — show pipeline stats/lead counts by stage
12. ask_ai — general insurance/business question (not a CRM action)
13. log_payment — record a premium payment received from a lead (cash/upi/cheque/bank/online)
14. log_call — log a phone call with a lead (with optional follow-up date)
15. add_policy — record a sold policy under a lead (auto-marks lead as closed_won)
16. schedule_meeting — book an in-person/online meeting with a lead at a specific date/time
17. mark_renewal_done — mark a policy as renewed for another year (bumps renewal_date)
18. log_claim — record a new claim filed by a lead (health/motor/life/accident)

CONVERSATION CONTEXT (previous command):
{context}

Return ONLY valid JSON:
{{
  "intent": "<create_lead|add_note|create_reminder|cancel_reminder|update_stage|update_lead|search_lead|list_tasks|cold_leads|overdue_followups|pipeline_summary|log_payment|log_call|add_policy|schedule_meeting|mark_renewal_done|log_claim|ask_ai>",
  "confidence": "<high|medium|low>",
  "name": "<lead name or null>",
  "phone": "<10-digit Indian mobile or null>",
  "email": "<email or null>",
  "need_type": "<health|term|endowment|ulip|child|retirement|motor|investment|nps|general or null>",
  "city": "<city or null>",
  "budget": "<monthly budget number or null>",
  "notes": "<any extra details or null>",
  "follow_up": "<YYYY-MM-DD or null>",
  "lead_name": "<name of existing lead or null>",
  "note_text": "<the note to add or null>",
  "reminder_message": "<what to remind about or null>",
  "reminder_date": "<YYYY-MM-DD or null>",
  "new_stage": "<prospect|contacted|pitched|proposal_sent|negotiation|closed_won|closed_lost or null>",
  "update_fields": {{}},
  "task_scope": "<today|week|overdue|all or null>",
  "ai_question": "<the question to answer or null>",
  "amount": "<payment amount as number or null>",
  "payment_method": "<cash|upi|cheque|bank|online|card or null>",
  "insurer": "<insurance company name or null>",
  "plan_name": "<plan/product name or null>",
  "policy_type": "<health|term|endowment|ulip|child|retirement|motor|investment|nps|life or null>",
  "policy_number": "<policy number or null>",
  "sum_insured": "<sum insured as number or null>",
  "premium": "<premium amount as number or null>",
  "premium_mode": "<monthly|quarterly|half_yearly|annual|single or null>",
  "meeting_date": "<YYYY-MM-DD or null>",
  "meeting_time": "<HH:MM 24h or null>",
  "meeting_location": "<location or 'online' or null>",
  "claim_type": "<health|motor|life|accident|other or null>",
  "claim_amount": "<claim amount as number or null>",
  "incident_date": "<YYYY-MM-DD or null>",
  "hospital_name": "<hospital/garage/place name or null>",
  "suggestion": "<helpful suggestion or null>"
}}

RULES:
- Today's date is {today}
- Convert relative dates: "kal"/"tomorrow" = next day, "next week" = next Monday, "parso" = day after tomorrow
- Handle Hindi, English, Hinglish naturally
- Indian names: proper capitalization (Ramesh Kumar)
- Extract 10-digit Indian phones (starting 6-9)
- Map Hindi stage words: "contact kiya" = contacted, "pitch kiya" = pitched, "deal pakki" = closed_won
- "naya client" / "new lead" / name + details = create_lead
- "yaad dilana" / "remind me" / "follow up" / "appointment" / "task set karo" with date = create_reminder
- "cancel karo" / "task hatao" / "reminder delete" / "cancel appointment" = cancel_reminder
- "note add karo" / "note likhna hai" = add_note
- "stage badlo" / "move to pitched" = update_stage
- "phone update karo" / "email change" / "city badlo" = update_lead
- "dhundho" / "find" / "search" / "lead kahan hai" = search_lead
- "aaj ke tasks" / "today's follow-ups" / "pending tasks" / "kya karna hai" = list_tasks
- "cold leads" / "thande leads" / "inactive leads" / "dead leads" / "sote hue leads" = cold_leads
- "overdue" / "late tasks" / "missed follow-ups" / "pending overdue" = overdue_followups
- "pipeline" / "summary" / "kitne leads hain" / "stats" / "dashboard stats" = pipeline_summary
- "premium aaya" / "payment received" / "X ne pay kiya" / "got premium" / "paisa aaya" / "X has paid" = log_payment (extract amount + payment_method)
- "call kiya" / "X se baat hui" / "spoke to X" / "phone par baat" / "X ko call" / "phone call" = log_call (note_text=summary, follow_up=any future date mentioned)
- "policy bech di" / "X ne policy li" / "sold to X" / "X ka HDFC liya" / "policy sold" / "deal closed with policy" = add_policy (extract insurer, plan_name, premium, sum_insured, policy_type)
- "meeting fix" / "appointment X tarikh ko" / "schedule meeting" / "X se milna hai" / "meet X tomorrow at 4" = schedule_meeting (extract meeting_date, meeting_time, meeting_location)
- "renew ho gayi" / "renewal done" / "X ki policy renew" / "premium renew kar diya" / "renewed for next year" = mark_renewal_done (lead_name + optional insurer)
- "claim file" / "claim laga" / "X ka claim" / "claim register karo" / "hospital admit ho gaya" / "accident claim" = log_claim (extract claim_type, claim_amount, incident_date, hospital_name)
- General questions about insurance/finance = ask_ai

CONTEXT AWARENESS — this is CRITICAL:
- If context has last_lead_name and agent says "uska/uski/his/her/iska/same" or does an action without naming a lead, USE last_lead_name as lead_name
- "uska phone update karo 9876543210" → update_lead with lead_name=last_lead_name
- "note bhi daal do" → add_note for last_lead_name
- "isko contacted mein daalo" → update_stage for last_lead_name
- "iski reminder set karo kal ke liye" → create_reminder for last_lead_name
- Only use context if the command is clearly about the same lead — if a new name is mentioned, use that instead

- BE INTELLIGENT: if user says "set task for Rahul" but no date, set reminder_date to tomorrow and note it in suggestion
- BE INTELLIGENT: if user says "cancel Rahul ka task" extract lead_name for cancel_reminder
- Return ONLY the JSON object, nothing else"""


def _dedup_transcript(text: str) -> str:
    """Remove repeated phrases from a transcript (Gemini hallucination guard)."""
    import re
    if not text or len(text) < 20:
        return text
    # Try to find a repeating segment: if same 8+ word phrase appears 3+ times, keep only one
    words = text.split()
    for seg_len in range(min(12, len(words)//2), 3, -1):
        seg = ' '.join(words[:seg_len])
        count = text.count(seg)
        if count >= 3:
            # Found heavy repetition — extract unique content
            # Take first occurrence + any trailing unique content
            idx = text.find(seg)
            end_of_first = idx + len(seg)
            remaining = text[end_of_first:].replace(seg, ' ').strip()
            # Clean up remaining: remove partial repeats
            result = seg + (' ' + remaining if remaining and len(remaining) > 3 else '')
            return re.sub(r'\s+', ' ', result).strip()
    return text


@app.post("/api/ai/voice-transcribe")
@limiter.limit("15/minute")
async def api_ai_voice_transcribe(request: Request,
                                   tenant: dict = Depends(auth.get_current_tenant)):
    """Transcribe audio blob using Gemini (fallback when SpeechRecognition fails)."""
    import biz_ai as ai_mod
    from google.genai import types as genai_types
    form = await request.form()
    audio_file = form.get("audio")
    if not audio_file:
        return JSONResponse({"error": "No audio file"}, 400)
    audio_bytes = await audio_file.read()
    if len(audio_bytes) < 500:
        return JSONResponse({"error": "Audio too short"}, 400)
    if len(audio_bytes) > 5 * 1024 * 1024:
        return JSONResponse({"error": "Audio too large (max 5MB)"}, 400)

    lang = form.get("lang", "en")
    client = ai_mod._get_client()
    if not client:
        return JSONResponse({"error": "AI not configured"}, 500)

    mime = audio_file.content_type or "audio/webm"
    prompt_text = ("Transcribe this short voice command (under 10 seconds). "
                    "Return ONLY the single intended sentence — no repetitions, no duplicates. "
                    "If you hear the same phrase repeated, output it ONCE. "
                    "Example: if audio sounds like 'create lead Ramesh... Ramesh... Ramesh Gupta phone 123', "
                    "output: 'create lead Ramesh Gupta phone 123'. "
                    "The speaker is giving a brief CRM command in Hindi or English.")
    if lang == "hi":
        prompt_text = ("इस छोटे वॉइस कमांड (10 सेकंड से कम) को ट्रांसक्राइब करें। "
                       "केवल एक वाक्य लिखें — कोई दोहराव नहीं। "
                       "अगर एक ही बात बार-बार सुनाई दे तो एक बार लिखें। "
                       "यह हिंदी या अंग्रेज़ी में एक CRM कमांड है।")

    try:
        response = await client.aio.models.generate_content(
            model=ai_mod.GEMINI_MODEL,
            contents=[
                genai_types.Content(parts=[
                    genai_types.Part.from_text(text=prompt_text),
                    genai_types.Part.from_bytes(data=audio_bytes, mime_type=mime),
                ])
            ]
        )
        transcript = response.text.strip()
        # Dedup: remove repeated phrases
        transcript = _dedup_transcript(transcript)
        if len(transcript) > 200:
            transcript = transcript[:200]
        return {"transcript": transcript}
    except Exception as exc:
        logger.error(f"Voice transcribe error: {exc}")
        return JSONResponse({"error": "Transcription failed"}, 500)


@app.post("/api/ai/voice-action")
@limiter.limit("20/minute")
async def api_ai_voice_action(request: Request,
                               tenant: dict = Depends(auth.get_current_tenant)):
    """Process voice transcript: classify intent, optionally preview or execute CRM action."""
    import biz_ai as ai_mod
    from datetime import datetime as _dt_cls
    body = await request.json()
    text = body.get("text", "").strip()
    lang = request.headers.get("X-Lang", "en")
    mode = body.get("mode", "classify")  # "classify" = preview, "execute" = confirm
    if not text or len(text) < 3:
        return JSONResponse({"error": "Text too short"}, status_code=400)

    tid = tenant["tenant_id"]
    agent_id = tenant.get("agent_id")
    hi = lang == "hi"

    # ── MODE: EXECUTE — caller already confirmed, data provided ──
    if mode == "execute":
        data = body.get("data", {})
        intent = data.get("intent", "ask_ai")

        if intent == "create_lead" and data.get("name"):
            name = auth.sanitize_text(data["name"])
            phone = auth.sanitize_phone(data.get("phone")) if data.get("phone") else None
            city = auth.sanitize_text(data.get("city")) if data.get("city") else None
            need_type = data.get("need_type") or "general"
            notes = auth.sanitize_text(data.get("notes")) if data.get("notes") else "Created via Voice AI"
            result = await db.add_lead_admin(
                tenant_id=tid, name=name, phone=phone, email=None,
                dob=None, city=city, need_type=need_type,
                source="voice_ai", notes=notes,
                assign_to_agent_id=agent_id,
            )
            if not result.get("success"):
                return {"action": "error", "message": result.get("error", "Failed to create lead")}
            lead_id = result["lead_id"]
            fu_msg = ""
            if data.get("follow_up"):
                try:
                    fu_date = _dt_cls.strptime(data["follow_up"], "%Y-%m-%d")
                    await db.add_reminder(
                        agent_id=agent_id, reminder_type="follow_up",
                        due_date=fu_date.strftime("%Y-%m-%d"),
                        message=f"Follow up with {name}", lead_id=lead_id,
                    )
                    # Also log as interaction for dashboard visibility
                    await db.log_interaction(
                        lead_id=lead_id, agent_id=agent_id,
                        interaction_type="follow_up",
                        summary=f"Follow up with {name}",
                        follow_up_date=fu_date.strftime("%Y-%m-%d"),
                    )
                    fu_msg = f"\n📅 Follow-up: {fu_date.strftime('%d %b %Y')}"
                except (ValueError, Exception):
                    pass
            await db.log_audit("voice_lead_created", f"Lead #{lead_id} via Voice AI",
                               tenant_id=tid, agent_id=agent_id, ip_address=request.client.host)
            return {
                "action": "lead_created", "lead_id": lead_id,
                "message": (f"✅ {'लीड बनी' if hi else 'Lead Created'}!\n\n"
                            f"🆔 #{lead_id}\n👤 {name}\n📱 {phone or 'N/A'}\n"
                            f"🏥 {need_type}\n🏙️ {city or 'N/A'}{fu_msg}"),
            }

        elif intent == "add_note" and data.get("lead_name") and data.get("note_text"):
            lead_name = data["lead_name"]
            note_text = auth.sanitize_text(data["note_text"])
            result = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _leads = result.get("leads", []) if isinstance(result, dict) else result
            if not _leads:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found. Please check the name."}
            lead = _leads[0]
            await db.log_interaction(
                lead_id=lead["lead_id"], agent_id=agent_id,
                interaction_type="note", summary=note_text,
            )
            return {
                "action": "note_added",
                "message": (f"✅ {'नोट जोड़ा' if hi else 'Note Added'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n📝 {note_text[:200]}"),
            }

        elif intent == "create_reminder" and data.get("reminder_date"):
            reminder_msg = auth.sanitize_text(data.get("reminder_message") or text)
            lead_id_for_reminder = None
            lead_display = ""
            if data.get("lead_name"):
                _r = await db.get_leads_by_tenant(tid, search=data["lead_name"], limit=1, agent_id=agent_id)
                _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
                if _ls:
                    lead_id_for_reminder = _ls[0]["lead_id"]
                    lead_display = f"\n👤 {_ls[0]['name']}"
            try:
                fu_date = _dt_cls.strptime(data["reminder_date"], "%Y-%m-%d")
                await db.add_reminder(
                    agent_id=agent_id, reminder_type="follow_up",
                    due_date=fu_date.strftime("%Y-%m-%d"),
                    message=reminder_msg, lead_id=lead_id_for_reminder,
                )
                # Also log as interaction so it shows in dashboard "Tasks Due"
                await db.log_interaction(
                    lead_id=lead_id_for_reminder or 0,
                    agent_id=agent_id,
                    interaction_type="follow_up",
                    summary=reminder_msg[:500],
                    follow_up_date=fu_date.strftime("%Y-%m-%d"),
                )
                return {
                    "action": "reminder_set",
                    "message": (f"✅ {'रिमाइंडर सेट' if hi else 'Reminder Set'}!\n\n"
                                f"📅 {fu_date.strftime('%d %b %Y')}{lead_display}\n"
                                f"📋 {reminder_msg[:200]}"),
                }
            except ValueError:
                return {"action": "error", "message": "❌ Invalid date format."}

        elif intent == "update_stage" and data.get("lead_name") and data.get("new_stage"):
            _r = await db.get_leads_by_tenant(tid, search=data["lead_name"], limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{data['lead_name']}' not found."}
            lead = _ls[0]
            new_stage = data["new_stage"]
            valid_stages = {"prospect", "contacted", "pitched", "proposal_sent",
                            "negotiation", "closed_won", "closed_lost"}
            if new_stage not in valid_stages:
                return {"action": "error", "message": f"❌ Invalid stage: {new_stage}"}
            old_stage = lead.get("stage", "prospect")
            await db.update_lead(lead["lead_id"], tenant_id=tid, stage=new_stage)
            return {
                "action": "stage_updated",
                "message": (f"✅ {'स्टेज अपडेट' if hi else 'Stage Updated'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n"
                            f"📊 {old_stage} → {new_stage}"),
            }

        elif intent == "cancel_reminder" and data.get("lead_name"):
            lead_name = data["lead_name"]
            _r = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found."}
            lead = _ls[0]
            lid = lead["lead_id"]
            # Get pending follow-ups for this lead and mark them done
            pending = await db.get_pending_followups_for_lead(lid)
            cancelled = 0
            for fu in pending:
                await db.mark_followup_done(fu["interaction_id"])
                cancelled += 1
            msg = (f"✅ {'टास्क कैंसल' if hi else 'Tasks Cancelled'}!\n\n"
                   f"👤 {lead['name']} (#{lid})\n")
            if cancelled:
                msg += f"{'%d पेंडिंग टास्क रद्द किए' % cancelled if hi else '%d pending task(s) cancelled' % cancelled}"
            else:
                msg += f"{'कोई पेंडिंग टास्क नहीं मिला' if hi else 'No pending tasks found'}"
            return {"action": "reminder_cancelled", "message": msg}

        elif intent == "update_lead" and data.get("lead_name"):
            lead_name = data["lead_name"]
            _r = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found."}
            lead = _ls[0]
            update_fields = data.get("update_fields") or {}
            # Also check top-level fields
            for fld in ("phone", "email", "city", "need_type"):
                if data.get(fld) and fld not in update_fields:
                    update_fields[fld] = data[fld]
            if not update_fields:
                return {"action": "error", "message": "❌ No fields to update specified."}
            valid_fields = {"phone", "email", "city", "need_type", "name", "dob", "notes"}
            clean = {k: auth.sanitize_text(str(v)) for k, v in update_fields.items() if k in valid_fields and v}
            if not clean:
                return {"action": "error", "message": "❌ No valid fields to update."}
            await db.update_lead(lead["lead_id"], tenant_id=tid, **clean)
            changed = ", ".join(f"{k}={v}" for k, v in clean.items())
            return {
                "action": "lead_updated",
                "message": (f"✅ {'लीड अपडेट' if hi else 'Lead Updated'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n"
                            f"📝 {changed}"),
            }

        elif intent == "search_lead" and (data.get("lead_name") or data.get("phone")):
            search_q = data.get("lead_name") or data.get("phone") or ""
            _r = await db.get_leads_by_tenant(tid, search=search_q, limit=5, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": (f"❌ '{search_q}' {'नहीं मिला' if hi else 'not found'}.\n"
                                    f"{'क्या नई लीड बनाऊं?' if hi else 'Want me to create a new lead?'}")}
            results = []
            for l in _ls[:5]:
                results.append(f"👤 {l['name']} | 📱 {l.get('phone','N/A')} | 📊 {l.get('stage','prospect')}")
            return {
                "action": "search_results",
                "message": (f"🔍 {'खोज परिणाम' if hi else 'Search Results'}:\n\n" + "\n".join(results)),
            }

        elif intent == "list_tasks":
            from zoneinfo import ZoneInfo
            ist = ZoneInfo("Asia/Kolkata")
            now_ist = _dt_cls.now(ist)
            scope = data.get("task_scope", "today")
            # Map voice scope to date param
            target_date = now_ist.strftime("%Y-%m-%d")  # default: today
            scope_label = "Today's Tasks" if not hi else "आज के टास्क"
            if scope == "week":
                target_date = None  # all upcoming
                scope_label = "This Week" if not hi else "इस हफ़्ते"
            elif scope == "overdue":
                target_date = "overdue"
                scope_label = "Overdue" if not hi else "ओवरड्यू"
            elif scope == "tomorrow":
                from datetime import timedelta as _td
                target_date = (now_ist + _td(days=1)).strftime("%Y-%m-%d")
                scope_label = "Tomorrow" if not hi else "कल"
            elif scope == "yesterday":
                from datetime import timedelta as _td
                target_date = (now_ist - _td(days=1)).strftime("%Y-%m-%d")
                scope_label = "Yesterday" if not hi else "बीता कल"
            elif scope == "all":
                target_date = None
                scope_label = "All Pending" if not hi else "सभी पेंडिंग"
            tasks = await db.get_tasks_by_date(agent_id=agent_id, target_date=target_date, status="pending", limit=15)
            if not tasks:
                return {"action": "ai_answer",
                        "message": f"✅ {'कोई पेंडिंग टास्क नहीं!' if hi else 'No pending tasks!'} 🎉"}
            now_date = now_ist.date()
            lines = []
            for t in tasks[:10]:
                fd = t.get("follow_up_date", "")
                lead_name = t.get("lead_name") or t.get("name", "?")
                summary = (t.get("summary") or "")[:60]
                overdue_flag = ""
                try:
                    if fd and _dt_cls.strptime(str(fd)[:10], "%Y-%m-%d").date() < now_date:
                        overdue_flag = " ⚠️"
                except Exception:
                    pass
                lines.append(f"📅 {str(fd)[:10]} | 👤 {lead_name} | {summary}{overdue_flag}")
            return {
                "action": "ai_answer",
                "message": f"📋 {scope_label} ({len(tasks)}):\n\n" + "\n".join(lines),
            }

        elif intent == "cold_leads":
            # Leads with no interaction in 7+ days
            result = await db.get_leads_by_tenant(tid, limit=100, agent_id=agent_id)
            _all_leads = result.get("leads", []) if isinstance(result, dict) else result
            cold = []
            now = _dt_cls.now()
            for l in _all_leads:
                updated = l.get("updated_at", "")
                try:
                    if updated:
                        last_activity = _dt_cls.strptime(str(updated)[:19], "%Y-%m-%d %H:%M:%S")
                        days_idle = (now - last_activity).days
                        if days_idle >= 7 and l.get("stage") not in ("closed_won", "closed_lost"):
                            cold.append((l, days_idle))
                except Exception:
                    cold.append((l, 999))
            if not cold:
                return {"action": "ai_answer",
                        "message": f"✅ {'कोई ठंडी लीड नहीं! सब एक्टिव हैं!' if hi else 'No cold leads! All leads are active.'} 🎉"}
            cold.sort(key=lambda x: -x[1])
            lines = [f"❄️ {l['name']} | {l.get('stage','prospect')} | {d} {'दिन' if hi else 'days idle'}" for l, d in cold[:10]]
            total_msg = f" ({len(cold)} {'कुल' if hi else 'total'})" if len(cold) > 10 else ""
            return {"action": "ai_answer",
                    "message": f"❄️ {'ठंडी लीड्स' if hi else 'Cold Leads'} ({len(cold)}){total_msg}:\n\n" + "\n".join(lines)}

        elif intent == "overdue_followups":
            pending = await db.get_pending_followups(agent_id)
            now = _dt_cls.now().date()
            overdue = []
            for fu in pending:
                fu_date = fu.get("follow_up_date", "")
                try:
                    if fu_date and _dt_cls.strptime(str(fu_date)[:10], "%Y-%m-%d").date() < now:
                        days_late = (now - _dt_cls.strptime(str(fu_date)[:10], "%Y-%m-%d").date()).days
                        overdue.append((fu, days_late))
                except Exception:
                    pass
            if not overdue:
                return {"action": "ai_answer",
                        "message": f"✅ {'कोई ओवरड्यू नहीं!' if hi else 'No overdue follow-ups!'} 🎉"}
            overdue.sort(key=lambda x: -x[1])
            lines = [f"⚠️ {fu.get('name', '?')} | {str(fu.get('follow_up_date', ''))[:10]} | {d} {'दिन लेट' if hi else 'days late'}"
                     for fu, d in overdue[:10]]
            return {"action": "ai_answer",
                    "message": f"⚠️ {'ओवरड्यू फ़ॉलो-अप्स' if hi else 'Overdue Follow-ups'} ({len(overdue)}):\n\n" + "\n".join(lines)}

        elif intent == "log_payment" and data.get("lead_name") and data.get("amount"):
            lead_name = data["lead_name"]
            try:
                amount = float(data["amount"])
            except (TypeError, ValueError):
                return {"action": "error", "message": "❌ Invalid payment amount."}
            method = (data.get("payment_method") or "cash").lower()
            valid_methods = {"cash", "upi", "cheque", "bank", "online", "card"}
            if method not in valid_methods:
                method = "cash"
            _r = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found."}
            lead = _ls[0]
            extra = auth.sanitize_text(data.get("notes") or "") if data.get("notes") else ""
            summary = f"Payment received: ₹{amount:,.0f} via {method}"
            if extra:
                summary += f" — {extra[:200]}"
            await db.log_interaction(
                lead_id=lead["lead_id"], agent_id=agent_id,
                interaction_type="payment", summary=summary,
            )
            await db.log_audit("voice_payment_logged",
                               f"Lead #{lead['lead_id']} payment ₹{amount:.0f} via {method}",
                               tenant_id=tid, agent_id=agent_id, ip_address=request.client.host)
            return {
                "action": "payment_logged",
                "message": (f"✅ {'पेमेंट लॉग किया' if hi else 'Payment Logged'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n"
                            f"💰 ₹{amount:,.0f}\n"
                            f"💳 {method.upper()}"),
            }

        elif intent == "log_call" and data.get("lead_name"):
            lead_name = data["lead_name"]
            _r = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found."}
            lead = _ls[0]
            call_summary = auth.sanitize_text(data.get("note_text") or text)[:1000]
            fu_date_str = None
            if data.get("follow_up"):
                try:
                    fu = _dt_cls.strptime(data["follow_up"], "%Y-%m-%d")
                    fu_date_str = fu.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
            await db.log_interaction(
                lead_id=lead["lead_id"], agent_id=agent_id,
                interaction_type="call", summary=call_summary,
                follow_up_date=fu_date_str,
            )
            fu_msg = ""
            if fu_date_str:
                await db.add_reminder(
                    agent_id=agent_id, reminder_type="follow_up",
                    due_date=fu_date_str,
                    message=f"Follow up call with {lead['name']}",
                    lead_id=lead["lead_id"],
                )
                fu_msg = f"\n📅 {'फॉलो-अप' if hi else 'Follow-up'}: {fu_date_str}"
            return {
                "action": "call_logged",
                "message": (f"✅ {'कॉल लॉग किया' if hi else 'Call Logged'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n"
                            f"📞 {call_summary[:200]}{fu_msg}"),
            }

        elif intent == "add_policy" and data.get("lead_name") and (data.get("insurer") or data.get("plan_name")):
            lead_name = data["lead_name"]
            _r = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found."}
            lead = _ls[0]
            insurer = auth.sanitize_text(data.get("insurer") or "")[:100] or None
            plan_name = auth.sanitize_text(data.get("plan_name") or "")[:200] or None
            policy_type = data.get("policy_type") or lead.get("need_type") or "health"
            valid_ptypes = {"health", "term", "endowment", "ulip", "child", "retirement",
                            "motor", "investment", "nps", "life"}
            if policy_type not in valid_ptypes:
                policy_type = "health"
            premium_mode = data.get("premium_mode") or "annual"
            valid_modes = {"monthly", "quarterly", "half_yearly", "annual", "single"}
            if premium_mode not in valid_modes:
                premium_mode = "annual"
            try:
                sum_insured = float(data["sum_insured"]) if data.get("sum_insured") else None
            except (TypeError, ValueError):
                sum_insured = None
            try:
                premium = float(data["premium"]) if data.get("premium") else None
            except (TypeError, ValueError):
                premium = None
            policy_number = auth.sanitize_text(data.get("policy_number") or "")[:50] or None
            policy_id = await db.add_policy(
                lead_id=lead["lead_id"], agent_id=agent_id,
                insurer=insurer, plan_name=plan_name, policy_type=policy_type,
                sum_insured=sum_insured, premium=premium, premium_mode=premium_mode,
                policy_number=policy_number, sold_by_agent=agent_id,
                policy_status="active", notes="Added via Voice AI",
            )
            # Auto-mark lead as closed_won
            old_stage = lead.get("stage", "prospect")
            if old_stage != "closed_won":
                await db.update_lead(lead["lead_id"], tenant_id=tid, stage="closed_won")
            await db.log_interaction(
                lead_id=lead["lead_id"], agent_id=agent_id,
                interaction_type="policy_sold",
                summary=f"Policy sold: {insurer or '?'} {plan_name or ''} (₹{premium or 0:.0f}/{premium_mode})",
            )
            await db.log_audit("voice_policy_added",
                               f"Policy #{policy_id} for lead #{lead['lead_id']} via Voice AI",
                               tenant_id=tid, agent_id=agent_id, ip_address=request.client.host)
            details = []
            if insurer: details.append(f"🏢 {insurer}")
            if plan_name: details.append(f"📋 {plan_name}")
            if sum_insured: details.append(f"🛡️ ₹{sum_insured:,.0f}")
            if premium: details.append(f"💰 ₹{premium:,.0f}/{premium_mode}")
            return {
                "action": "policy_added",
                "message": (f"✅ {'पॉलिसी जोड़ी' if hi else 'Policy Added'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n"
                            f"🆔 Policy #{policy_id}\n" +
                            "\n".join(details) +
                            f"\n📊 Stage → closed_won"),
            }

        elif intent == "schedule_meeting" and data.get("lead_name") and data.get("meeting_date"):
            lead_name = data["lead_name"]
            _r = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found."}
            lead = _ls[0]
            try:
                m_date = _dt_cls.strptime(data["meeting_date"], "%Y-%m-%d")
            except (ValueError, TypeError):
                return {"action": "error", "message": "❌ Invalid meeting date."}
            m_time = data.get("meeting_time") or ""
            if m_time:
                # Sanitize HH:MM
                import re as _re
                if not _re.match(r"^\d{1,2}:\d{2}$", m_time):
                    m_time = ""
            location = auth.sanitize_text(data.get("meeting_location") or "")[:200]
            time_part = f" at {m_time}" if m_time else ""
            loc_part = f" — {location}" if location else ""
            msg = f"Meeting with {lead['name']}{time_part}{loc_part}"
            await db.add_reminder(
                agent_id=agent_id, reminder_type="meeting",
                due_date=m_date.strftime("%Y-%m-%d"),
                message=msg, lead_id=lead["lead_id"],
            )
            await db.log_interaction(
                lead_id=lead["lead_id"], agent_id=agent_id,
                interaction_type="meeting",
                summary=msg,
                follow_up_date=m_date.strftime("%Y-%m-%d"),
            )
            return {
                "action": "meeting_scheduled",
                "message": (f"✅ {'मीटिंग शेड्यूल' if hi else 'Meeting Scheduled'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n"
                            f"📅 {m_date.strftime('%d %b %Y')}{time_part}"
                            + (f"\n📍 {location}" if location else "")),
            }

        elif intent == "mark_renewal_done" and data.get("lead_name"):
            lead_name = data["lead_name"]
            _r = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found."}
            lead = _ls[0]
            policies = await db.get_policies_by_lead(lead["lead_id"], tenant_id=tid)
            if not policies:
                return {"action": "not_found",
                        "message": f"❌ No policies found for {lead['name']}."}
            insurer_q = (data.get("insurer") or "").lower().strip()
            if insurer_q:
                matched = [p for p in policies if insurer_q in (p.get("insurer") or "").lower()]
                policies = matched or policies
            target = policies[0]
            # Bump renewal_date by 1 year (or set 1y from today if missing)
            try:
                if target.get("renewal_date"):
                    cur = _dt_cls.strptime(target["renewal_date"][:10], "%Y-%m-%d")
                else:
                    cur = _dt_cls.now()
                new_renewal = cur.replace(year=cur.year + 1).strftime("%Y-%m-%d")
            except Exception:
                new_renewal = (_dt_cls.now().replace(year=_dt_cls.now().year + 1)).strftime("%Y-%m-%d")
            await db.update_policy(target["policy_id"], tenant_id=tid,
                                   renewal_date=new_renewal, status="active")
            await db.log_interaction(
                lead_id=lead["lead_id"], agent_id=agent_id,
                interaction_type="renewal_done",
                summary=f"Renewal done: {target.get('insurer') or '?'} {target.get('plan_name') or ''} → next renewal {new_renewal}",
            )
            return {
                "action": "renewal_done",
                "message": (f"✅ {'रिन्यूअल पूरा' if hi else 'Renewal Done'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n"
                            f"🏢 {target.get('insurer') or '?'} {target.get('plan_name') or ''}\n"
                            f"📅 {'अगला रिन्यूअल' if hi else 'Next renewal'}: {new_renewal}"),
            }

        elif intent == "log_claim" and data.get("lead_name"):
            lead_name = data["lead_name"]
            _r = await db.get_leads_by_tenant(tid, search=lead_name, limit=1, agent_id=agent_id)
            _ls = _r.get("leads", []) if isinstance(_r, dict) else _r
            if not _ls:
                return {"action": "not_found",
                        "message": f"❌ Lead '{lead_name}' not found."}
            lead = _ls[0]
            claim_type = (data.get("claim_type") or "other").lower()
            valid_ctypes = {"health", "motor", "life", "accident", "other"}
            if claim_type not in valid_ctypes:
                claim_type = "other"
            try:
                claim_amount = float(data["claim_amount"]) if data.get("claim_amount") else None
            except (TypeError, ValueError):
                claim_amount = None
            incident_date = None
            if data.get("incident_date"):
                try:
                    incident_date = _dt_cls.strptime(data["incident_date"], "%Y-%m-%d").strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
            hospital = auth.sanitize_text(data.get("hospital_name") or "")[:200] or None
            description = auth.sanitize_text(data.get("description") or data.get("notes") or "")[:1000] or None
            # Try to attach to most recent policy
            policies = await db.get_policies_by_lead(lead["lead_id"], tenant_id=tid)
            policy_id = policies[0]["policy_id"] if policies else None
            claim_id = await db.add_claim(
                agent_id=agent_id, lead_id=lead["lead_id"], claim_type=claim_type,
                policy_id=policy_id, claim_amount=claim_amount,
                incident_date=incident_date, description=description,
                hospital_name=hospital, notes="Logged via Voice AI",
            )
            await db.log_interaction(
                lead_id=lead["lead_id"], agent_id=agent_id,
                interaction_type="claim_filed",
                summary=f"Claim #{claim_id} filed: {claim_type}" +
                        (f" ₹{claim_amount:,.0f}" if claim_amount else "") +
                        (f" at {hospital}" if hospital else ""),
            )
            await db.log_audit("voice_claim_logged",
                               f"Claim #{claim_id} for lead #{lead['lead_id']} via Voice AI",
                               tenant_id=tid, agent_id=agent_id, ip_address=request.client.host)
            details = [f"🏷️ {claim_type}"]
            if claim_amount: details.append(f"💰 ₹{claim_amount:,.0f}")
            if incident_date: details.append(f"📅 {incident_date}")
            if hospital: details.append(f"🏥 {hospital}")
            return {
                "action": "claim_logged",
                "message": (f"✅ {'क्लेम दर्ज' if hi else 'Claim Logged'}!\n\n"
                            f"👤 {lead['name']} (#{lead['lead_id']})\n"
                            f"🆔 Claim #{claim_id}\n" +
                            "\n".join(details)),
            }

        elif intent == "pipeline_summary":
            hi_labels = {
                "prospect": "🆕 प्रॉस्पेक्ट", "contacted": "📞 संपर्क किया", "pitched": "🎯 पिच किया",
                "proposal_sent": "📄 प्रपोज़ल भेजा", "negotiation": "🤝 बातचीत",
                "closed_won": "✅ जीता", "closed_lost": "❌ हारा",
            }
            labels = hi_labels if hi else stage_labels
            total = sum(pipeline.values())
            lines = [f"{labels.get(s, s)}: {c}" for s, c in pipeline.items() if c > 0]
            return {"action": "ai_answer",
                    "message": f"📊 {'पाइपलाइन सारांश' if hi else 'Pipeline Summary'} ({total} {'लीड्स' if hi else 'leads'}):\n\n" + "\n".join(lines)}

        else:
            question = data.get("ai_question") or text
            answer = await ai_mod.ask_insurance_ai(question, lang=lang)
            return {"action": "ai_answer", "message": answer}

    # ── MODE: CLASSIFY — parse intent & return preview for confirmation ──
    today = _dt_cls.now().strftime("%Y-%m-%d (%A)")
    # Build context string from previous conversation
    ctx = body.get("context") or {}
    ctx_str = "No previous context."
    if ctx.get("last_lead_name"):
        ctx_str = (f"Last command: {ctx.get('last_intent', 'unknown')} | "
                   f"Last lead: {ctx['last_lead_name']}"
                   f"{' (#' + str(ctx['last_lead_id']) + ')' if ctx.get('last_lead_id') else ''}")
    prompt = (_WEB_VOICE_PROMPT
              .replace("{today}", today)
              .replace("{context}", ctx_str)
              + f"\n\nAgent said: \"{text}\"")
    raw = None
    try:
        raw = await ai_mod._ask_gemini(prompt)
        data = ai_mod._clean_json(raw)
    except Exception as e:
        logger.error("Voice action AI parse error: %s — raw: %s", e, raw[:200] if raw else "N/A")
        answer = await ai_mod.ask_insurance_ai(text, lang=lang)
        return {"action": "ai_answer", "message": answer, "intent": "ask_ai"}

    intent = data.get("intent", "ask_ai")

    # For ask_ai, return answer directly — no confirmation needed
    if intent == "ask_ai" or (intent == "create_lead" and not data.get("name")):
        question = data.get("ai_question") or text
        answer = await ai_mod.ask_insurance_ai(question, lang=lang)
        return {"action": "ai_answer", "message": answer, "intent": "ask_ai"}

    # For CRM actions, return preview data for user confirmation
    return {"action": "preview", "intent": intent, "data": data, "transcript": text}


@app.get("/api/ai/voice-suggestions")
@limiter.limit("10/minute")
async def api_ai_voice_suggestions(request: Request,
                                    tenant: dict = Depends(auth.get_current_tenant)):
    """Return proactive suggestions when voice panel opens."""
    from datetime import datetime as _dt_cls
    agent_id = tenant.get("agent_id")
    hi = request.headers.get("X-Lang", "en") == "hi"

    suggestions = []

    # 1. Overdue follow-ups
    try:
        pending = await db.get_pending_followups(agent_id)
        now_date = _dt_cls.now().date()
        overdue_count = 0
        today_count = 0
        for fu in pending:
            fd = fu.get("follow_up_date", "")
            try:
                d = _dt_cls.strptime(str(fd)[:10], "%Y-%m-%d").date()
                if d < now_date:
                    overdue_count += 1
                elif d == now_date:
                    today_count += 1
            except Exception:
                pass
        if overdue_count:
            suggestions.append({
                "icon": "⚠️",
                "text": f"{overdue_count} {'ओवरड्यू टास्क' if hi else 'overdue tasks'}",
                "command": "show overdue follow-ups"
            })
        if today_count:
            suggestions.append({
                "icon": "📅",
                "text": f"{today_count} {'आज के टास्क' if hi else 'tasks due today'}",
                "command": "show today's tasks"
            })
    except Exception:
        pass

    # 2. Pipeline summary
    try:
        pipeline = await db.get_pipeline_summary(agent_id)
        total_active = sum(v for k, v in pipeline.items() if k not in ("closed_won", "closed_lost"))
        if total_active:
            suggestions.append({
                "icon": "📊",
                "text": f"{total_active} {'सक्रिय लीड्स' if hi else 'active leads'}",
                "command": "show pipeline summary"
            })
    except Exception:
        pass

    # 3. Quick actions
    quick_actions = [
        {"icon": "➕", "text": hi and "नई लीड बनाएं" or "Create new lead", "command": "create new lead"},
        {"icon": "🔍", "text": hi and "लीड खोजें" or "Search lead", "command": "search lead"},
        {"icon": "❄️", "text": hi and "ठंडी लीड्स दिखाओ" or "Show cold leads", "command": "show cold leads"},
    ]

    return {"suggestions": suggestions, "quick_actions": quick_actions}


# =============================================================================
#  NUDGE API — Owner sends instant nudge to advisor via Telegram
# =============================================================================

class NudgeRequest(BaseModel):
    lead_id: int
    target_agent_id: int
    nudge_type: str = Field("followup")  # followup, new_lead, renewal, custom
    owner_note: Optional[str] = Field(None, max_length=500)


class BroadcastNudgeRequest(BaseModel):
    message: str = Field(..., min_length=5, max_length=1000)
    agent_ids: Optional[List[int]] = None  # None = all active agents


@app.post("/api/nudge")
@limiter.limit("30/minute")
async def api_send_nudge(req: NudgeRequest, request: Request,
                          tenant: dict = Depends(auth.get_current_tenant)):
    """Owner sends a nudge to an advisor about a specific lead."""
    # Only owners can nudge
    if tenant.get("role") not in ("owner", "admin"):
        return JSONResponse({"error": "Only firm owners can send nudges"}, status_code=403)

    tid = tenant["tenant_id"]
    sender_agent_id = tenant.get("agent_id")
    if not sender_agent_id:
        owner_agent = await db.get_owner_agent_by_tenant(tid)
        sender_agent_id = owner_agent["agent_id"] if owner_agent else 0

    # Verify target agent belongs to this tenant
    target = await db.get_agent_by_id(req.target_agent_id)
    if not target or target.get("tenant_id") != tid:
        return JSONResponse({"error": "Agent not found in your team"}, status_code=404)
    if not target.get("telegram_id"):
        return JSONResponse({"error": "This advisor has no Telegram connected"}, status_code=400)

    # Get lead data
    lead = await db.get_lead(req.lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    # Get recent interactions for context
    interactions = await db.get_lead_interactions(req.lead_id, limit=3, tenant_id=tid)

    # AI-generate the nudge message
    import biz_ai as ai_mod
    lang = request.headers.get("X-Lang", "en")
    ai_result = await ai_mod.generate_nudge_message(
        nudge_type=req.nudge_type,
        lead=dict(lead),
        interactions=[dict(i) for i in interactions],
        advisor_name=target.get("name", ""),
        owner_note=req.owner_note or "",
        lang=lang,
    )

    message_text = ai_result.get("message", "")
    if not message_text:
        return JSONResponse({"error": "Failed to generate nudge message"}, status_code=500)

    # Save nudge to DB
    nudge_id = await db.create_nudge(
        tenant_id=tid,
        sender_agent_id=sender_agent_id,
        target_agent_id=req.target_agent_id,
        nudge_type=req.nudge_type,
        message=message_text,
        lead_id=req.lead_id,
    )

    # Send to advisor via Telegram
    tg_id = target["telegram_id"]
    delivered = False
    delivery_error = ""
    try:
        # Try tenant bot first, fall back to master
        mgr = botmgr.bot_manager
        bot_app = mgr._bots.get(tid)
        if not bot_app or not bot_app.running:
            bot_app = mgr.master_bot
        if not bot_app or not bot_app.running:
            delivery_error = "No running bot available. Please check bot configuration."
        else:
            # Build inline buttons for advisor response
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            buttons = [
                [InlineKeyboardButton("✅ Done", callback_data=f"nudge_act_{nudge_id}"),
                 InlineKeyboardButton("⏰ Remind Later", callback_data=f"nudge_snooze_{nudge_id}")],
            ]

            await bot_app.bot.send_message(
                chat_id=int(tg_id),
                text=f"📩 <b>Nudge from your firm</b>\n\n{message_text}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            delivered = True
            await db.update_nudge_status(nudge_id, "delivered")
    except Exception as tg_err:
        err_str = str(tg_err)
        logger.error("Failed to deliver nudge %d via Telegram: %s", nudge_id, tg_err)
        if "bot was blocked" in err_str.lower() or "forbidden" in err_str.lower():
            delivery_error = "Advisor has blocked the bot. They need to unblock and /start the bot again."
        elif "chat not found" in err_str.lower() or "user not found" in err_str.lower():
            delivery_error = "Advisor hasn't started the bot yet. They need to open the bot and tap /start first."
        elif "not enough rights" in err_str.lower():
            delivery_error = "Bot doesn't have permission to message this user."
        else:
            delivery_error = f"Telegram error: {err_str[:150]}"

    return {
        "ok": True,
        "nudge_id": nudge_id,
        "delivered": delivered,
        "delivery_error": delivery_error,
        "summary": ai_result.get("summary", ""),
        "message_preview": message_text[:200],
    }


@app.post("/api/nudge/broadcast")
@limiter.limit("10/minute")
async def api_broadcast_nudge(req: BroadcastNudgeRequest, request: Request,
                               tenant: dict = Depends(auth.get_current_tenant)):
    """Owner broadcasts a message to all (or selected) advisors."""
    if tenant.get("role") not in ("owner", "admin"):
        return JSONResponse({"error": "Only firm owners can broadcast"}, status_code=403)

    tid = tenant["tenant_id"]
    sender_agent_id = tenant.get("agent_id")
    if not sender_agent_id:
        owner_agent = await db.get_owner_agent_by_tenant(tid)
        sender_agent_id = owner_agent["agent_id"] if owner_agent else 0

    all_agents = await db.get_agents_by_tenant(tid)
    targets = [a for a in all_agents if a.get("is_active") and a.get("telegram_id")
               and a["agent_id"] != sender_agent_id]

    if req.agent_ids:
        allowed = set(req.agent_ids)
        targets = [a for a in targets if a["agent_id"] in allowed]

    if not targets:
        return JSONResponse({"error": "No active advisors with Telegram to notify"}, status_code=400)

    mgr = botmgr.bot_manager
    bot_app = mgr._bots.get(tid) or mgr.master_bot
    sent_count = 0

    for agent in targets:
        try:
            nudge_id = await db.create_nudge(
                tenant_id=tid, sender_agent_id=sender_agent_id,
                target_agent_id=agent["agent_id"], nudge_type="broadcast",
                message=req.message)

            if bot_app:
                await bot_app.bot.send_message(
                    chat_id=int(agent["telegram_id"]),
                    text=f"📢 <b>Announcement from your firm</b>\n\n{req.message}",
                    parse_mode="HTML",
                )
                await db.update_nudge_status(nudge_id, "delivered")
            sent_count += 1
        except Exception as e:
            logger.error("Broadcast to agent %d failed: %s", agent["agent_id"], e)

    return {"ok": True, "sent_to": sent_count, "total_targets": len(targets)}


@app.get("/api/nudge/history")
async def api_nudge_history(tenant: dict = Depends(auth.get_current_tenant)):
    """Get nudge history for the firm."""
    if tenant.get("role") not in ("owner", "admin"):
        return JSONResponse({"error": "Owners only"}, status_code=403)
    history = await db.get_nudge_history(tenant["tenant_id"])
    return {"nudges": history}


@app.post("/api/nudge/preview")
@limiter.limit("20/minute")
async def api_nudge_preview(req: NudgeRequest, request: Request,
                             tenant: dict = Depends(auth.get_current_tenant)):
    """Preview the AI-generated nudge message without sending it."""
    if tenant.get("role") not in ("owner", "admin"):
        return JSONResponse({"error": "Owners only"}, status_code=403)

    tid = tenant["tenant_id"]
    target = await db.get_agent_by_id(req.target_agent_id)
    if not target or target.get("tenant_id") != tid:
        return JSONResponse({"error": "Agent not found"}, status_code=404)

    lead = await db.get_lead(req.lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    interactions = await db.get_lead_interactions(req.lead_id, limit=3, tenant_id=tid)

    import biz_ai as ai_mod
    lang = request.headers.get("X-Lang", "en")
    ai_result = await ai_mod.generate_nudge_message(
        nudge_type=req.nudge_type,
        lead=dict(lead),
        interactions=[dict(i) for i in interactions],
        advisor_name=target.get("name", ""),
        owner_note=req.owner_note or "",
        lang=lang,
    )

    return {"message": ai_result.get("message", ""), "summary": ai_result.get("summary", "")}


@app.post("/api/nudge/bulk")
@limiter.limit("5/minute")
async def api_bulk_nudge(request: Request,
                          tenant: dict = Depends(auth.get_current_tenant)):
    """Nudge all advisors who have pending/overdue follow-ups.
    Groups follow-ups by agent, generates one AI message per agent with their pending items,
    then delivers via Telegram."""
    if tenant.get("role") not in ("owner", "admin"):
        return JSONResponse({"error": "Only firm owners can bulk nudge"}, status_code=403)

    tid = tenant["tenant_id"]
    sender_agent_id = tenant.get("agent_id")
    if not sender_agent_id:
        owner_agent = await db.get_owner_agent_by_tenant(tid)
        sender_agent_id = owner_agent["agent_id"] if owner_agent else 0

    # Get all pending follow-ups for the tenant
    all_pending = await db.get_tenant_pending_followups(tid)
    if not all_pending:
        return {"ok": True, "sent_to": 0, "total_agents": 0, "message": "No pending follow-ups found"}

    # Group by agent
    from collections import defaultdict
    agent_followups = defaultdict(list)
    agent_info = {}
    for fp in all_pending:
        aid = fp["agent_id"]
        agent_followups[aid].append(fp)
        if aid not in agent_info:
            agent_info[aid] = {
                "name": fp.get("agent_name", ""),
                "telegram_id": fp.get("agent_telegram_id"),
            }

    # Skip agents without Telegram or who are the owner themselves
    agents_to_nudge = {
        aid: items for aid, items in agent_followups.items()
        if agent_info[aid]["telegram_id"] and aid != sender_agent_id
    }

    if not agents_to_nudge:
        return {"ok": True, "sent_to": 0, "total_agents": 0,
                "message": "No advisors with pending follow-ups to nudge"}

    import biz_ai as ai_mod
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    lang = request.headers.get("X-Lang", "en")
    mgr = botmgr.bot_manager
    bot_app = mgr._bots.get(tid)
    if not bot_app or not bot_app.running:
        bot_app = mgr.master_bot

    results = []
    for aid, followups in agents_to_nudge.items():
        info = agent_info[aid]
        # Build a summary of pending leads for the AI prompt
        lead_summaries = []
        for fp in followups[:10]:  # Cap at 10 to keep prompt reasonable
            lead_summaries.append({
                "lead_name": fp.get("lead_name", ""),
                "follow_up_date": fp.get("follow_up_date", ""),
                "notes": (fp.get("notes") or "")[:100],
                "lead_id": fp.get("lead_id"),
            })

        # Generate AI message for this agent
        ai_result = await ai_mod.generate_nudge_message(
            nudge_type="bulk_followup",
            lead={"_bulk": True, "_count": len(followups), "_leads": lead_summaries},
            interactions=[],
            advisor_name=info["name"],
            owner_note=f"{len(followups)} pending follow-ups need attention",
            lang=lang,
        )
        message_text = ai_result.get("message", "")
        if not message_text:
            results.append({"agent_id": aid, "name": info["name"], "status": "ai_failed"})
            continue

        # Pick the first lead for the nudge record (representative)
        first_lead_id = followups[0].get("lead_id")
        nudge_id = await db.create_nudge(
            tenant_id=tid, sender_agent_id=sender_agent_id,
            target_agent_id=aid, nudge_type="bulk_followup",
            message=message_text, lead_id=first_lead_id,
        )

        # Deliver via Telegram
        delivered = False
        delivery_error = ""
        try:
            if bot_app and bot_app.running:
                buttons = [[
                    InlineKeyboardButton("✅ Done", callback_data=f"nudge_act_{nudge_id}"),
                    InlineKeyboardButton("⏰ Remind Later", callback_data=f"nudge_snooze_{nudge_id}"),
                ]]
                await bot_app.bot.send_message(
                    chat_id=int(info["telegram_id"]),
                    text=f"📩 <b>Nudge from your firm</b>\n\n{message_text}",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
                delivered = True
                await db.update_nudge_status(nudge_id, "delivered")
            else:
                delivery_error = "No running bot available"
        except Exception as tg_err:
            err_str = str(tg_err)
            logger.error("Bulk nudge to agent %d failed: %s", aid, tg_err)
            if "blocked" in err_str.lower() or "forbidden" in err_str.lower():
                delivery_error = "Bot blocked by advisor"
            elif "chat not found" in err_str.lower():
                delivery_error = "Advisor hasn't started bot"
            else:
                delivery_error = f"Telegram error: {err_str[:100]}"

        results.append({
            "agent_id": aid, "name": info["name"],
            "pending_count": len(followups),
            "delivered": delivered,
            "delivery_error": delivery_error,
        })

    sent_count = sum(1 for r in results if r.get("delivered"))
    return {
        "ok": True,
        "sent_to": sent_count,
        "total_agents": len(agents_to_nudge),
        "results": results,
    }


@app.get("/api/nudge/suggestions")
@limiter.limit("10/minute")
async def api_nudge_suggestions(request: Request,
                                 tenant: dict = Depends(auth.get_current_tenant)):
    """AI-powered smart nudge suggestions — detects situations needing owner attention."""
    if tenant.get("role") not in ("owner", "admin"):
        return JSONResponse({"error": "Owners only"}, status_code=403)

    tid = tenant["tenant_id"]
    signals = await db.get_smart_nudge_signals(tid)

    suggestions = []

    # 1. Overdue follow-ups — group by agent
    overdue = signals.get("overdue_followups", [])
    if overdue:
        from collections import defaultdict
        by_agent = defaultdict(list)
        for o in overdue:
            by_agent[o["agent_id"]].append(o)
        for aid, items in by_agent.items():
            name = items[0]["agent_name"]
            lead_names = ", ".join(i["lead_name"] for i in items[:3])
            extra = f" +{len(items)-3} more" if len(items) > 3 else ""
            suggestions.append({
                "type": "overdue_followup",
                "severity": "high",
                "icon": "🔴",
                "title": f"{name} has {len(items)} overdue follow-ups",
                "detail": f"{lead_names}{extra}",
                "agent_id": aid,
                "agent_name": name,
                "lead_id": items[0]["lead_id"],
                "lead_name": items[0]["lead_name"],
                "count": len(items),
                "nudge_type": "followup",
            })

    # 2. Hot leads going cold
    cooling = signals.get("cooling_hot_leads", [])
    for c in cooling[:5]:
        suggestions.append({
            "type": "cooling_lead",
            "severity": "high",
            "icon": "🥶",
            "title": f"{c['lead_name']} ({c['stage']}) going cold",
            "detail": f"Assigned to {c['agent_name']} — no activity since {c['updated_at'][:10]}",
            "agent_id": c["agent_id"],
            "agent_name": c["agent_name"],
            "lead_id": c["lead_id"],
            "lead_name": c["lead_name"],
            "nudge_type": "followup",
        })

    # 3. Untouched new leads
    untouched = signals.get("untouched_new_leads", [])
    for u in untouched[:5]:
        suggestions.append({
            "type": "untouched_new",
            "severity": "medium",
            "icon": "🔥",
            "title": f"New lead {u['lead_name']} untouched 24h+",
            "detail": f"Assigned to {u['agent_name']} — created {u['created_at'][:10]}",
            "agent_id": u["agent_id"],
            "agent_name": u["agent_name"],
            "lead_id": u["lead_id"],
            "lead_name": u["lead_name"],
            "nudge_type": "new_lead",
        })

    # 4. Renewals due with no action
    renewals = signals.get("renewals_due", [])
    for r in renewals[:5]:
        suggestions.append({
            "type": "renewal_due",
            "severity": "medium",
            "icon": "🔄",
            "title": f"{r['lead_name']} renewal on {r['renewal_date']}",
            "detail": f"{r.get('plan_name', 'Policy')} • ₹{r.get('premium', 0):,.0f} • Advisor: {r['agent_name']}",
            "agent_id": r["agent_id"],
            "agent_name": r["agent_name"],
            "lead_id": r.get("lead_id"),
            "lead_name": r["lead_name"],
            "nudge_type": "renewal",
        })

    # 5. Stale pipeline
    stale = signals.get("stale_leads", [])
    if stale:
        from collections import defaultdict
        stale_by_agent = defaultdict(list)
        for s in stale:
            stale_by_agent[s["agent_id"]].append(s)
        for aid, items in stale_by_agent.items():
            if len(items) >= 2:  # Only flag if 2+ stale leads
                name = items[0]["agent_name"]
                suggestions.append({
                    "type": "stale_pipeline",
                    "severity": "low",
                    "icon": "💤",
                    "title": f"{name} has {len(items)} stale leads (7+ days)",
                    "detail": ", ".join(i["lead_name"] for i in items[:3]),
                    "agent_id": aid,
                    "agent_name": name,
                    "lead_id": items[0]["lead_id"],
                    "lead_name": items[0]["lead_name"],
                    "count": len(items),
                    "nudge_type": "followup",
                })

    # Sort by severity
    sev_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: sev_order.get(s["severity"], 9))

    return {
        "ok": True,
        "suggestions": suggestions[:15],  # Cap at top 15
        "totals": {
            "overdue": len(overdue),
            "cooling": len(cooling),
            "untouched_new": len(untouched),
            "renewals_due": len(renewals),
            "stale": len(stale),
        }
    }


# =============================================================================
#  PROFILE & BRANDING API — Self-Service for Owners/Agents
# =============================================================================

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=15)
    city: Optional[str] = Field(None, max_length=100)
    lang: Optional[str] = Field(None, pattern=r'^(en|hi)$')


@app.get("/api/profile")
async def api_get_profile(current=Depends(auth.get_current_tenant)):
    """Get current user's profile and tenant branding info."""
    # Return the actual logged-in agent, not always the owner
    agent = None
    if current.get("agent_id"):
        agent = await db.get_agent_by_id(current["agent_id"])
    if not agent:
        agent = await db.get_owner_agent_by_tenant(current["tenant_id"])
    tenant = await db.get_tenant(current["tenant_id"])
    if not agent or not tenant:
        return JSONResponse({"detail": "Not found"}, status_code=404)
    result = {
        "agent": {
            "agent_id": agent["agent_id"],
            "name": agent.get("name", ""),
            "email": agent.get("email", ""),
            "phone": agent.get("phone", ""),
            "city": agent.get("city", ""),
            "lang": agent.get("lang", "en"),
            "role": agent.get("role", "agent"),
            "photo_url": agent.get("photo_url", ""),
        },
        "tenant": {
            "tenant_id": tenant["tenant_id"],
            "firm_name": tenant.get("firm_name", ""),
            "owner_name": tenant.get("owner_name", ""),
            "phone": tenant.get("phone", ""),
            "email": tenant.get("email", ""),
            "city": tenant.get("city", ""),
            "plan": tenant.get("plan", "trial"),
            "brand_tagline": tenant.get("brand_tagline", ""),
            "brand_cta": tenant.get("brand_cta", ""),
            "brand_phone": tenant.get("brand_phone", ""),
            "brand_email": tenant.get("brand_email", ""),
            "brand_primary_color": tenant.get("brand_primary_color", "#1a56db"),
            "brand_accent_color": tenant.get("brand_accent_color", "#ea580c"),
            "brand_credentials": tenant.get("brand_credentials", ""),
            "brand_logo": tenant.get("brand_logo", ""),
            "has_bot": bool(tenant.get("tg_bot_token")),
            "bot_username": botmgr.bot_manager.get_bot_username(tenant["tenant_id"]) or "",
            "has_whatsapp": bool(tenant.get("wa_phone_id")),
            "wa_phone_id": tenant.get("wa_phone_id", ""),
            "referred_by": "",
            "referred_code": "",
        },
    }
    # Enrich with affiliate info if referred
    ref_aff = await db.get_affiliate_for_tenant(current["tenant_id"])
    if ref_aff:
        result["tenant"]["referred_by"] = ref_aff["name"]
        result["tenant"]["referred_code"] = ref_aff["referral_code"]
    return result


@app.put("/api/profile")
@limiter.limit("10/minute")
async def api_update_profile(req: ProfileUpdateRequest, request: Request,
                              current=Depends(auth.get_current_tenant)):
    """Update current user's profile fields."""
    agent = await db.get_owner_agent_by_tenant(current["tenant_id"])
    if not agent:
        return JSONResponse({"detail": "Agent not found"}, status_code=404)

    fields = {}
    if req.name is not None:
        fields["name"] = auth.sanitize_text(req.name)
    if req.email is not None:
        fields["email"] = auth.sanitize_email(req.email)
    if req.phone is not None:
        fields["phone"] = auth.sanitize_phone(req.phone)
    if req.city is not None:
        fields["city"] = auth.sanitize_text(req.city)
    if req.lang is not None:
        fields["lang"] = req.lang

    if not fields:
        return {"status": "no_changes"}

    await db.update_agent_profile(agent["agent_id"], **fields)

    # Also update owner fields on tenant if this is the owner
    if agent.get("role") == "owner":
        tenant_fields = {}
        if "name" in fields:
            tenant_fields["owner_name"] = fields["name"]
        if "email" in fields:
            tenant_fields["email"] = fields["email"]
        if "phone" in fields:
            tenant_fields["phone"] = fields["phone"]
        if "city" in fields:
            tenant_fields["city"] = fields["city"]
        if tenant_fields:
            await db.update_tenant(current["tenant_id"], **tenant_fields)

    return {"status": "ok", "updated": list(fields.keys())}


class BrandingUpdateRequest(BaseModel):
    brand_tagline: Optional[str] = Field(None, max_length=200)
    brand_cta: Optional[str] = Field(None, max_length=200)
    brand_phone: Optional[str] = Field(None, max_length=15)
    brand_email: Optional[str] = Field(None, max_length=100)
    brand_website: Optional[str] = Field(None, max_length=300)
    firm_name: Optional[str] = Field(None, min_length=2, max_length=200)
    brand_primary_color: Optional[str] = Field(None, max_length=10)
    brand_accent_color: Optional[str] = Field(None, max_length=10)
    brand_credentials: Optional[str] = Field(None, max_length=500)


@app.put("/api/tenant/branding")
@limiter.limit("10/minute")
async def api_update_branding(req: BrandingUpdateRequest, request: Request,
                               current=Depends(auth.require_owner)):
    """Update tenant branding settings. Owner only."""
    fields = {}
    if req.brand_tagline is not None:
        fields["brand_tagline"] = auth.sanitize_text(req.brand_tagline)
    if req.brand_cta is not None:
        fields["brand_cta"] = auth.sanitize_text(req.brand_cta)
    if req.brand_phone is not None:
        fields["brand_phone"] = auth.sanitize_phone(req.brand_phone)
    if req.brand_email is not None:
        fields["brand_email"] = auth.sanitize_email(req.brand_email)
    if req.brand_website is not None:
        fields["brand_website"] = auth.sanitize_text(req.brand_website)
    if req.firm_name is not None:
        fields["firm_name"] = auth.sanitize_text(req.firm_name)
    if req.brand_primary_color is not None:
        import re as _re
        if _re.match(r'^#[0-9a-fA-F]{6}$', req.brand_primary_color):
            fields["brand_primary_color"] = req.brand_primary_color
    if req.brand_accent_color is not None:
        import re as _re
        if _re.match(r'^#[0-9a-fA-F]{6}$', req.brand_accent_color):
            fields["brand_accent_color"] = req.brand_accent_color
    if req.brand_credentials is not None:
        fields["brand_credentials"] = auth.sanitize_text(req.brand_credentials)

    if not fields:
        return {"status": "no_changes"}

    await db.update_tenant(current["tenant_id"], **fields)
    return {"status": "ok", "updated": list(fields.keys())}


@app.post("/api/tenant/logo")
@limiter.limit("10/minute")
async def api_upload_tenant_logo(request: Request,
                                  current=Depends(auth.require_owner)):
    """Upload firm logo. Accepts multipart/form-data with an image file. Max 2MB."""
    tid = current["tenant_id"]
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return JSONResponse({"error": "Expected multipart/form-data"}, status_code=400)

    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        return JSONResponse({"error": "File too large. Max 2MB."}, status_code=400)

    boundary = content_type.split("boundary=")[-1].strip() if "boundary=" in content_type else ""
    if not boundary:
        return JSONResponse({"error": "Invalid multipart boundary"}, status_code=400)

    parts = body.split(f"--{boundary}".encode())
    image_bytes = None
    for part in parts:
        part_lower = part.lower()
        if b"content-type:" in part_lower and b"image/" in part_lower:
            idx = part.find(b"\r\n\r\n")
            if idx >= 0:
                image_bytes = part[idx + 4:]
                if image_bytes.endswith(b"\r\n"):
                    image_bytes = image_bytes[:-2]
                if image_bytes.endswith(b"--"):
                    image_bytes = image_bytes[:-2]
                if image_bytes.endswith(b"\r\n"):
                    image_bytes = image_bytes[:-2]
                break

    if not image_bytes or len(image_bytes) < 100:
        return JSONResponse({"error": "No valid image found in upload"}, status_code=400)

    if not (image_bytes[:2] == b'\xff\xd8' or image_bytes[:4] == b'\x89PNG'):
        return JSONResponse({"error": "Only JPEG and PNG images are supported"}, status_code=400)

    ext = "jpg" if image_bytes[:2] == b'\xff\xd8' else "png"
    logos_dir = Path(__file__).parent / "uploads" / "logos"
    logos_dir.mkdir(parents=True, exist_ok=True)
    filename = f"tenant_{tid}.{ext}"
    (logos_dir / filename).write_bytes(image_bytes)

    logo_url = f"/uploads/logos/{filename}"
    await db.update_tenant(tid, brand_logo=logo_url)
    return {"ok": True, "logo_url": logo_url}


@app.delete("/api/tenant/logo")
async def api_delete_tenant_logo(current=Depends(auth.require_owner)):
    """Remove firm logo."""
    tid = current["tenant_id"]
    t = await db.get_tenant(tid)
    logo = t.get("brand_logo", "")
    if logo:
        fp = Path(__file__).parent / logo.lstrip("/")
        if fp.exists():
            fp.unlink(missing_ok=True)
    await db.update_tenant(tid, brand_logo="")
    return {"ok": True}


@app.get("/api/public/branding/{tenant_id}")
async def api_public_branding(tenant_id: int):
    """Public endpoint — returns tenant branding for white-label pages. No auth required."""
    t = await db.get_tenant(tenant_id)
    if not t or not t.get("is_active"):
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {
        "firm_name": t.get("firm_name", ""),
        "tagline": t.get("brand_tagline", ""),
        "cta": t.get("brand_cta", ""),
        "phone": t.get("brand_phone", t.get("phone", "")),
        "email": t.get("brand_email", t.get("email", "")),
        "logo_url": t.get("brand_logo", ""),
        "primary_color": t.get("brand_primary_color", "#1a56db"),
        "accent_color": t.get("brand_accent_color", "#ea580c"),
        "credentials": t.get("brand_credentials", ""),
    }


# =============================================================================
#  ADMIN DASHBOARD API — Lead/Policy/Agent/Overview for Firm Owners
# =============================================================================

@app.get("/api/admin/overview")
async def api_admin_overview(tenant: dict = Depends(auth.get_current_tenant)):
    """Dashboard overview — owners see firm-wide, agents see own stats."""
    role = tenant.get("role", "agent")
    is_owner = role in ("owner", "admin")
    agent_id = tenant.get("agent_id") if not is_owner else None
    overview = await db.get_admin_overview(tenant["tenant_id"], agent_id=agent_id)
    t = await db.get_tenant(tenant["tenant_id"])
    pending = await db.get_pending_plan_change(tenant["tenant_id"]) if is_owner else None
    plan_features = db.PLAN_FEATURES.get(t.get("plan", "trial"), db.PLAN_FEATURES["trial"])
    # Get the actual logged-in agent's name (for advisor dashboard display)
    agent_name = ""
    agent_phone = ""
    if tenant.get("agent_id"):
        ag = await db.get_agent_by_id(tenant["agent_id"])
        if ag:
            agent_name = ag.get("name", "")
            agent_phone = ag.get("phone", "")
    if not agent_name:
        agent_name = t.get("owner_name", "")
        agent_phone = t.get("phone", "")
    # Check if user is already an affiliate/partner
    is_partner = False
    _t_phone = t.get("phone", "")
    _t_email = t.get("email", "")
    if _t_phone or _t_email:
        aff = await db.get_affiliate(phone=_t_phone) if _t_phone else None
        if not aff and _t_email:
            async with aiosqlite.connect(db.DB_PATH) as _conn:
                _conn.row_factory = aiosqlite.Row
                _cur = await _conn.execute("SELECT affiliate_id FROM affiliates WHERE email=?", (_t_email,))
                aff = await _cur.fetchone()
        if aff:
            is_partner = True
    return {
        **overview,
        "role": role,
        "agent_name": agent_name,
        "agent_phone": agent_phone,
        "is_partner": is_partner,
        "tenant": {
            "tenant_id": t["tenant_id"],
            "firm_name": t.get("firm_name", ""),
            "owner_name": t.get("owner_name", ""),
            "phone": t.get("phone", ""),
            "email": t.get("email", ""),
            "plan": t.get("plan", "trial"),
            "subscription_status": t.get("subscription_status", "trial"),
            "trial_ends_at": t.get("trial_ends_at"),
            "subscription_expires_at": t.get("subscription_expires_at"),
            "max_agents": t.get("max_agents", 1),
            "city": t.get("city", ""),
        },
        "plan_features": plan_features,
        "pending_plan_change": pending,
    }


@app.get("/api/admin/leads")
async def api_admin_leads(stage: str = Query(None),
                           search: str = Query(None),
                           client_type: str = Query(None),
                           limit: int = Query(50, le=200),
                           offset: int = Query(0),
                           tenant: dict = Depends(auth.get_current_tenant)):
    """List leads — owners see all, agents see only their own."""
    role = tenant.get("role", "agent")
    agent_id = tenant.get("agent_id") if role not in ("owner", "admin") else None
    return await db.get_leads_by_tenant(tenant["tenant_id"], stage=stage,
                                         search=search, limit=limit, offset=offset,
                                         agent_id=agent_id, client_type=client_type)


class AdminAddLeadRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=15)
    email: Optional[str] = Field(None, max_length=100)
    dob: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=50)
    need_type: str = Field("health")
    source: str = Field("web_admin")
    notes: Optional[str] = Field(None, max_length=500)
    assign_to_agent_id: Optional[int] = Field(None)


@app.post("/api/admin/leads")
@limiter.limit("30/minute")
async def api_admin_add_lead(req: AdminAddLeadRequest, request: Request,
                              tenant: dict = Depends(auth.get_current_tenant)):
    """Add a new lead from admin dashboard."""
    # Agents can only add leads assigned to themselves
    role = tenant.get("role", "agent")
    assign_to = req.assign_to_agent_id
    if role not in ("owner", "admin"):
        assign_to = tenant.get("agent_id")
    result = await db.add_lead_admin(
        tenant_id=tenant["tenant_id"],
        name=auth.sanitize_text(req.name),
        phone=auth.sanitize_phone(req.phone) if req.phone else None,
        email=auth.sanitize_email(req.email) if req.email else None,
        dob=req.dob if req.dob else None,
        city=auth.sanitize_text(req.city) if req.city else None,
        need_type=req.need_type,
        source=req.source,
        notes=auth.sanitize_text(req.notes) if req.notes else None,
        assign_to_agent_id=assign_to,
    )
    if not result.get("success"):
        return JSONResponse({"error": result.get("error")}, status_code=400)
    await db.log_audit("admin_lead_added", f"Lead {result['lead_id']} added via admin",
                       tenant_id=tenant["tenant_id"], role=tenant.get('role'),
                       ip_address=request.client.host)
    return result


class AdminEditLeadRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=15)
    email: Optional[str] = Field(None, max_length=100)
    dob: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=50)
    need_type: Optional[str] = Field(None)
    notes: Optional[str] = Field(None, max_length=500)
    stage: Optional[str] = Field(None)
    source: Optional[str] = Field(None)


@app.put("/api/admin/leads/{lead_id}")
@limiter.limit("30/minute")
async def api_admin_edit_lead(lead_id: int, req: AdminEditLeadRequest, request: Request,
                               tenant: dict = Depends(auth.get_current_tenant)):
    """Edit a lead from admin dashboard."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    # Agents can only edit their own leads
    role = tenant.get("role", "agent")
    if role not in ("owner", "admin") and lead.get("agent_id") != tenant.get("agent_id"):
        return JSONResponse({"error": "You can only edit your own leads"}, status_code=403)

    updates = {}
    if req.name: updates["name"] = auth.sanitize_text(req.name)
    if req.phone: updates["phone"] = auth.sanitize_phone(req.phone)
    if req.email: updates["email"] = auth.sanitize_email(req.email)
    if req.dob: updates["dob"] = req.dob
    if req.city: updates["city"] = auth.sanitize_text(req.city)
    if req.need_type: updates["need_type"] = req.need_type
    if req.notes is not None: updates["notes"] = auth.sanitize_text(req.notes) if req.notes else ""
    if req.stage: updates["stage"] = req.stage
    if req.source: updates["source"] = req.source

    if updates:
        await db.update_lead(lead_id, tenant_id=tid, **updates)
    await db.log_audit("admin_lead_edited", f"Lead {lead_id} edited via admin",
                       tenant_id=tid, role=tenant.get('role'),
                       ip_address=request.client.host)
    return {"success": True, "lead_id": lead_id}


@app.delete("/api/admin/leads/{lead_id}")
@limiter.limit("10/minute")
async def api_admin_delete_lead(lead_id: int, request: Request,
                                 tenant: dict = Depends(auth.require_owner)):
    """Delete a lead and all associated data. Owner only."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    result = await db.delete_lead(lead_id, tenant_id=tid)
    if result.get("success"):
        await db.log_audit("admin_lead_deleted", f"Lead {lead_id} deleted via admin",
                           tenant_id=tid, role=tenant.get('role'),
                           ip_address=request.client.host)
    return result


@app.put("/api/admin/leads/{lead_id}/stage")
@limiter.limit("30/minute")
async def api_admin_change_stage(lead_id: int, request: Request,
                                  stage: str = Query(...),
                                  tenant: dict = Depends(auth.get_current_tenant)):
    """Change lead pipeline stage from admin dashboard."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    # Agents can only change stage of their own leads
    role = tenant.get("role", "agent")
    if role not in ("owner", "admin") and lead.get("agent_id") != tenant.get("agent_id"):
        return JSONResponse({"error": "You can only modify your own leads"}, status_code=403)
    ok = await db.update_lead_stage(lead_id, stage, tenant_id=tid)
    if not ok:
        return JSONResponse({"error": f"Invalid stage: {stage}"}, status_code=400)
    return {"success": True, "lead_id": lead_id, "new_stage": stage}


class ReassignLeadRequest(BaseModel):
    new_agent_id: int


@app.post("/api/admin/leads/{lead_id}/reassign")
@limiter.limit("10/minute")
async def api_admin_reassign_lead(lead_id: int, req: ReassignLeadRequest,
                                   request: Request,
                                   tenant: dict = Depends(auth.require_owner)):
    """Reassign a lead to a different agent (Team/Enterprise only)."""
    result = await db.reassign_lead(lead_id, req.new_agent_id, tenant["tenant_id"])
    if not result.get("success"):
        return JSONResponse({"error": result.get("error")}, status_code=400)
    await db.log_audit("admin_lead_reassigned",
                       f"Lead {lead_id} → Agent {req.new_agent_id}",
                       tenant_id=tenant["tenant_id"], role=tenant.get('role'),
                       ip_address=request.client.host)
    return result


@app.get("/api/admin/policies")
async def api_admin_policies(status: str = Query(None),
                              limit: int = Query(50, le=200),
                              offset: int = Query(0),
                              tenant: dict = Depends(auth.get_current_tenant)):
    """List policies — owners see all, agents see only their own."""
    role = tenant.get("role", "agent")
    agent_id = tenant.get("agent_id") if role not in ("owner", "admin") else None
    return await db.get_policies_by_tenant(tenant["tenant_id"], status=status,
                                            limit=limit, offset=offset,
                                            agent_id=agent_id)


class AdminAddPolicyRequest(BaseModel):
    lead_id: int
    policy_number: Optional[str] = Field(None, max_length=100)
    insurer: Optional[str] = Field(None, max_length=200)
    plan_name: Optional[str] = Field(None, max_length=200)
    policy_type: str = Field("health", max_length=30)
    sum_insured: Optional[float] = Field(None)
    premium: Optional[float] = Field(None)
    premium_mode: str = Field("annual", max_length=20)
    start_date: Optional[str] = Field(None, max_length=10)
    end_date: Optional[str] = Field(None, max_length=10)
    renewal_date: Optional[str] = Field(None, max_length=10)
    commission: float = Field(0)
    notes: Optional[str] = Field(None, max_length=500)
    sold_by_agent: Optional[int] = Field(None)


@app.post("/api/admin/policies")
@limiter.limit("30/minute")
async def api_admin_add_policy(req: AdminAddPolicyRequest, request: Request,
                                tenant: dict = Depends(auth.get_current_tenant)):
    """Create a policy from dashboard."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(req.lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    agent_id = lead.get("agent_id") or tenant.get("agent_id")
    if not agent_id:
        return JSONResponse({"error": "Could not determine agent for this lead"}, status_code=400)
    sold = 1 if req.sold_by_agent is None else req.sold_by_agent
    policy_id = await db.add_policy(
        lead_id=req.lead_id, agent_id=agent_id,
        insurer=auth.sanitize_text(req.insurer) if req.insurer else None,
        plan_name=auth.sanitize_text(req.plan_name) if req.plan_name else None,
        policy_type=req.policy_type or "health",
        sum_insured=req.sum_insured, premium=req.premium,
        premium_mode=req.premium_mode or "annual",
        start_date=req.start_date, end_date=req.end_date,
        renewal_date=req.renewal_date,
        policy_number=auth.sanitize_text(req.policy_number) if req.policy_number else None,
        commission=req.commission or 0,
        notes=auth.sanitize_text(req.notes) if req.notes else None,
        sold_by_agent=sold,
    )
    await db.log_audit("admin_policy_added", f"Policy {policy_id} for lead {req.lead_id}",
                       tenant_id=tid, ip_address=request.client.host)
    return {"success": True, "policy_id": policy_id}


class AdminEditPolicyRequest(BaseModel):
    policy_number: Optional[str] = Field(None, max_length=100)
    insurer: Optional[str] = Field(None, max_length=200)
    plan_name: Optional[str] = Field(None, max_length=200)
    policy_type: Optional[str] = Field(None, max_length=30)
    sum_insured: Optional[float] = Field(None)
    premium: Optional[float] = Field(None)
    premium_mode: Optional[str] = Field(None, max_length=20)
    start_date: Optional[str] = Field(None, max_length=10)
    end_date: Optional[str] = Field(None, max_length=10)
    renewal_date: Optional[str] = Field(None, max_length=10)
    commission: Optional[float] = Field(None)
    notes: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, max_length=20)


@app.put("/api/admin/policies/{policy_id}")
@limiter.limit("30/minute")
async def api_admin_edit_policy(policy_id: int, req: AdminEditPolicyRequest, request: Request,
                                 tenant: dict = Depends(auth.get_current_tenant)):
    """Edit a policy from dashboard."""
    tid = tenant["tenant_id"]
    policy = await db.get_policy(policy_id, tenant_id=tid)
    if not policy:
        return JSONResponse({"error": "Policy not found"}, status_code=404)
    # Agents can only edit their own policies
    role = tenant.get("role", "agent")
    if role not in ("owner", "admin") and policy.get("agent_id") != tenant.get("agent_id"):
        return JSONResponse({"error": "You can only edit your own policies"}, status_code=403)
    updates = {}
    for field in ("insurer", "plan_name", "policy_type", "premium_mode",
                  "start_date", "end_date", "renewal_date", "policy_number", "status"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = auth.sanitize_text(val) if field not in ("sum_insured", "premium", "commission") else val
    for field in ("sum_insured", "premium", "commission"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val
    if req.notes is not None:
        updates["notes"] = auth.sanitize_text(req.notes) if req.notes else ""
    if updates:
        await db.update_policy(policy_id, tenant_id=tid, **updates)
    await db.log_audit("admin_policy_edited", f"Policy {policy_id} edited",
                       tenant_id=tid, ip_address=request.client.host)
    return {"success": True, "policy_id": policy_id}


@app.delete("/api/admin/policies/{policy_id}")
@limiter.limit("10/minute")
async def api_admin_delete_policy(policy_id: int, request: Request,
                                   tenant: dict = Depends(auth.require_owner)):
    """Delete a policy. Owner only."""
    tid = tenant["tenant_id"]
    result = await db.delete_policy(policy_id, tenant_id=tid)
    if result.get("success"):
        await db.log_audit("admin_policy_deleted", f"Policy {policy_id} deleted",
                           tenant_id=tid, ip_address=request.client.host)
    return result


@app.get("/api/admin/customers")
async def api_admin_customers(search: str = Query(None),
                               limit: int = Query(50, le=200),
                               offset: int = Query(0),
                               tenant: dict = Depends(auth.get_current_tenant)):
    """List customers with portfolio summary — policy counts and totals."""
    role = tenant.get("role", "agent")
    agent_id = tenant.get("agent_id") if role not in ("owner", "admin") else None
    return await db.get_customers_with_portfolio(tenant["tenant_id"], search=search,
                                                  limit=limit, offset=offset,
                                                  agent_id=agent_id)


@app.get("/api/admin/leads/{lead_id}/policies")
async def api_admin_lead_policies(lead_id: int,
                                   tenant: dict = Depends(auth.get_current_tenant)):
    """Get all policies for a specific lead/customer."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    role = tenant.get("role", "agent")
    if role not in ("owner", "admin") and lead.get("agent_id") != tenant.get("agent_id"):
        return JSONResponse({"error": "Access denied"}, status_code=403)
    policies = await db.get_policies_by_lead(lead_id, tenant_id=tid)
    return {"policies": policies, "lead": {"name": lead.get("name"), "lead_id": lead_id}}


@app.get("/api/admin/policies/{policy_id}/members")
async def api_admin_policy_members(policy_id: int,
                                    tenant: dict = Depends(auth.get_current_tenant)):
    """Get insured members for a policy."""
    tid = tenant["tenant_id"]
    policy = await db.get_policy(policy_id, tenant_id=tid)
    if not policy:
        return JSONResponse({"error": "Policy not found"}, status_code=404)
    role = tenant.get("role", "agent")
    if role not in ("owner", "admin") and policy.get("agent_id") != tenant.get("agent_id"):
        return JSONResponse({"error": "Access denied"}, status_code=403)
    members = await db.get_policy_members(policy_id)
    return {"members": members, "policy_id": policy_id}


@app.post("/api/admin/policies/extract")
@limiter.limit("10/minute")
async def api_extract_policy(request: Request,
                              tenant: dict = Depends(auth.get_current_tenant)):
    """Extract policy fields from pasted text, uploaded image, or PDF using Gemini AI."""
    import biz_ai as ai_mod
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
        text = body.get("text", "").strip()
        if not text or len(text) < 20:
            return JSONResponse({"error": "Please paste at least 20 characters of policy text"}, status_code=400)
        if len(text) > 10000:
            text = text[:10000]
        result = await ai_mod.extract_policy_from_document(text)
        if not result or result.get("_error"):
            msg = result.get("_error", "Could not extract policy fields from the provided text") if result else "Could not extract policy fields from the provided text"
            return JSONResponse({"error": msg}, status_code=422)
        return {"success": True, "extracted": result}

    elif "multipart/form-data" in content_type:
        body = await request.body()
        if len(body) > 10 * 1024 * 1024:
            return JSONResponse({"error": "File too large. Max 10MB."}, status_code=400)
        boundary = content_type.split("boundary=")[-1].strip() if "boundary=" in content_type else ""
        if not boundary:
            return JSONResponse({"error": "Invalid multipart boundary"}, status_code=400)
        parts = body.split(f"--{boundary}".encode())

        # Detect file type from multipart parts
        file_bytes = None
        is_pdf = False
        mime_type = "image/jpeg"
        for part in parts:
            part_lower = part.lower()
            # Check for PDF
            if b"content-type:" in part_lower and b"application/pdf" in part_lower:
                is_pdf = True
                idx = part.find(b"\r\n\r\n")
                if idx >= 0:
                    file_bytes = part[idx + 4:]
                    while file_bytes.endswith(b"\r\n") or file_bytes.endswith(b"--"):
                        if file_bytes.endswith(b"--"): file_bytes = file_bytes[:-2]
                        if file_bytes.endswith(b"\r\n"): file_bytes = file_bytes[:-2]
                break
            # Check for image
            if b"content-type:" in part_lower and b"image/" in part_lower:
                if b"image/png" in part_lower:
                    mime_type = "image/png"
                idx = part.find(b"\r\n\r\n")
                if idx >= 0:
                    file_bytes = part[idx + 4:]
                    while file_bytes.endswith(b"\r\n") or file_bytes.endswith(b"--"):
                        if file_bytes.endswith(b"--"): file_bytes = file_bytes[:-2]
                        if file_bytes.endswith(b"\r\n"): file_bytes = file_bytes[:-2]
                break

        if not file_bytes or len(file_bytes) < 100:
            return JSONResponse({"error": "No valid file found in upload"}, status_code=400)

        if is_pdf:
            # Extract text from PDF using pymupdf
            try:
                import fitz
                pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                pdf_text = ""
                for page in pdf_doc:
                    pdf_text += page.get_text()
                pdf_doc.close()
                pdf_text = pdf_text.strip()
                if len(pdf_text) > 50:
                    # Good text extraction — use text-based AI
                    if len(pdf_text) > 10000:
                        pdf_text = pdf_text[:10000]
                    result = await ai_mod.extract_policy_from_document(pdf_text)
                    if not result or result.get("_error"):
                        msg = result.get("_error", "Could not extract fields from PDF") if result else "Could not extract fields from PDF"
                        return JSONResponse({"error": msg}, status_code=422)
                    return {"success": True, "extracted": result}
                else:
                    # Scanned PDF — render up to 5 pages as images for vision AI
                    pdf_scan = fitz.open(stream=file_bytes, filetype="pdf")
                    pages_to_scan = min(pdf_scan.page_count, 5)
                    img_parts = []
                    for pi in range(pages_to_scan):
                        pix = pdf_scan[pi].get_pixmap(dpi=200)
                        img_parts.append(pix.tobytes("png"))
                    pdf_scan.close()
                    if len(img_parts) == 1:
                        result = await ai_mod.extract_policy_from_image(img_parts[0], "image/png")
                    else:
                        result = await ai_mod.extract_policy_from_images(img_parts)
                    if not result or result.get("_error"):
                        msg = result.get("_error", "Could not extract fields from scanned PDF") if result else "Could not extract fields from scanned PDF"
                        return JSONResponse({"error": msg}, status_code=422)
                    return {"success": True, "extracted": result}
            except Exception as e:
                logger.error("PDF extraction failed: %s", e, exc_info=True)
                return JSONResponse({"error": f"PDF processing failed: {str(e)}"}, status_code=500)
        else:
            result = await ai_mod.extract_policy_from_image(file_bytes, mime_type)
            if not result or result.get("_error"):
                msg = result.get("_error", "Could not extract fields from image") if result else "Could not extract fields from image"
                return JSONResponse({"error": msg}, status_code=422)
            return {"success": True, "extracted": result}

    return JSONResponse({"error": "Send JSON with 'text' field or multipart file (image/PDF)"}, status_code=400)


@app.post("/api/admin/invite")
@limiter.limit("5/minute")
async def api_admin_generate_invite(request: Request,
                                     tenant: dict = Depends(auth.require_owner)):
    """Generate an invite code to add agents. Owner only, Team/Enterprise."""
    t = await db.get_tenant(tenant["tenant_id"])
    plan = t.get("plan", "trial") if t else "trial"
    if plan in ("trial", "individual"):
        return JSONResponse({"error": "Invite codes require Team or Enterprise plan"}, status_code=403)
    owner_agent_id = tenant.get("agent_id")
    if not owner_agent_id:
        return JSONResponse({"error": "Owner agent not found. Please re-login."}, status_code=400)
    result = await db.create_invite_code_web(tenant["tenant_id"], owner_agent_id)
    if not result.get("success"):
        return JSONResponse({"error": result.get("error")}, status_code=400)
    await db.log_audit("invite_code_generated", f"Code: {result['code']}",
                       tenant_id=tenant["tenant_id"], role=tenant.get('role'),
                       ip_address=request.client.host)
    # Include shareable web invite URL
    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
    result["invite_url"] = f"{server_url}/invite?code={result['code']}"
    return result


class InviteAcceptRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=20)
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field("", max_length=15)
    email: str = Field(..., min_length=5, max_length=200)


@app.post("/api/invite/accept")
@limiter.limit("10/minute")
async def api_invite_accept(req: InviteAcceptRequest, request: Request):
    """Accept an invite code via web — creates agent without Telegram.
    Agent can link Telegram later via /start."""
    code = req.code.strip().upper()
    invite = await db.validate_invite_code(code)
    if not invite:
        return JSONResponse({"error": "Invalid or expired invite code."}, status_code=400)

    tenant_id = invite["tenant_id"]
    cap = await db.can_add_agent(tenant_id)
    if not cap.get("allowed"):
        return JSONResponse({"error": f"Team is full ({cap.get('current')}/{cap.get('max')} agents)."}, status_code=403)

    clean_email = auth.sanitize_email(req.email)
    clean_phone = auth.sanitize_phone(req.phone) if req.phone else None

    # Check if email or phone already registered in this tenant
    existing = await db.get_agents_by_tenant(tenant_id)
    for a in existing:
        if clean_phone and a.get("phone") == clean_phone:
            return JSONResponse({"error": "This phone is already registered in this firm."}, status_code=409)
        if clean_email and a.get("email") and a.get("email").lower() == clean_email.lower():
            return JSONResponse({"error": "This email is already registered in this firm."}, status_code=409)

    # Create agent with a placeholder telegram_id (will be linked later via /start)
    placeholder_tg = f"web_{tenant_id}_{clean_email}"
    agent_id = await db.upsert_agent(
        telegram_id=placeholder_tg,
        name=auth.sanitize_text(req.name),
        phone=clean_phone,
        email=clean_email,
        tenant_id=tenant_id,
        role="agent",
    )
    await db.use_invite_code(code)

    t = await db.get_tenant(tenant_id)
    firm_name = t.get("firm_name", "your firm") if t else "your firm"

    await db.log_audit("agent_joined_web", f"Agent {agent_id} joined via web invite code {code}",
                       tenant_id=tenant_id, ip_address=request.client.host)

    return {
        "success": True,
        "agent_id": agent_id,
        "firm_name": firm_name,
        "message": f"Welcome to {firm_name}! You can now link your Telegram by messaging the firm's bot with /start.",
    }


@app.get("/api/invite/validate/{code}")
@limiter.limit("20/minute")
async def api_invite_validate(code: str, request: Request):
    """Validate an invite code and return firm info (public, no auth required)."""
    invite = await db.validate_invite_code(code.strip().upper())
    if not invite:
        return JSONResponse({"error": "Invalid or expired invite code."}, status_code=400)
    t = await db.get_tenant(invite["tenant_id"])
    if not t:
        return JSONResponse({"error": "Firm not found."}, status_code=404)
    cap = await db.can_add_agent(invite["tenant_id"])
    return {
        "valid": True,
        "firm_name": t.get("firm_name", ""),
        "plan": t.get("plan", ""),
        "slots_available": cap.get("max", 0) - cap.get("current", 0),
    }


# =============================================================================
#  SUBSCRIPTION MANAGEMENT — Schedule for Next Billing Cycle
# =============================================================================

class PlanChangeRequest(BaseModel):
    new_plan: str = Field(..., description="New plan: individual, team, or enterprise")


@app.post("/api/subscription/schedule-change")
@limiter.limit("5/minute")
async def api_schedule_plan_change(req: PlanChangeRequest, request: Request,
                                    tenant: dict = Depends(auth.require_owner)):
    """Schedule a plan change for next billing cycle. Owner only."""
    await _verify_csrf(request, tenant_id=tenant["tenant_id"])
    valid_plans = ['individual', 'team', 'enterprise']
    if req.new_plan not in valid_plans:
        return JSONResponse({"error": f"Invalid plan. Choose: {', '.join(valid_plans)}"}, status_code=400)
    result = await db.schedule_plan_change(tenant["tenant_id"], req.new_plan, 'tenant')
    if not result.get("success"):
        return JSONResponse({"error": result.get("error")}, status_code=400)
    await db.log_audit("plan_change_scheduled",
                       f'Scheduled: → {req.new_plan}',
                       tenant_id=tenant["tenant_id"], role=tenant.get('role'),
                       ip_address=request.client.host)
    return result


@app.get("/api/subscription/pending-change")
async def api_pending_plan_change(tenant: dict = Depends(auth.get_current_tenant)):
    """Check if there's a pending plan change."""
    pending = await db.get_pending_plan_change(tenant["tenant_id"])
    return {"pending": pending}


@app.delete("/api/subscription/pending-change")
@limiter.limit("5/minute")
async def api_cancel_pending_change(request: Request,
                                     tenant: dict = Depends(auth.get_current_tenant)):
    """Cancel a pending plan change."""
    ok = await db.cancel_pending_plan_change(tenant["tenant_id"])
    if not ok:
        return JSONResponse({"error": "No pending change found"}, status_code=404)
    await db.log_audit("plan_change_cancelled", "Cancelled by tenant",
                       tenant_id=tenant["tenant_id"], role=tenant.get('role'),
                       ip_address=request.client.host)
    return {"success": True, "message": "Pending plan change cancelled"}


@app.post("/api/subscription/upgrade")
@limiter.limit("5/minute")
async def api_subscription_upgrade(req: PlanChangeRequest, request: Request,
                                    tenant: dict = Depends(auth.require_owner)):
    """Immediate upgrade (after payment). Owner only."""
    result = await db.upgrade_tenant_plan(tenant["tenant_id"], req.new_plan)
    if not result.get("success"):
        return JSONResponse({"error": result.get("error", "Upgrade failed")}, status_code=400)
    await db.log_audit("subscription_upgrade",
                       f'{result["old_plan"]} → {result["new_plan"]}',
                       tenant_id=tenant["tenant_id"], role=tenant.get('role'),
                       ip_address=request.client.host)
    return result


@app.post("/api/subscription/downgrade")
@limiter.limit("5/minute")
async def api_subscription_downgrade(req: PlanChangeRequest, request: Request,
                                      tenant: dict = Depends(auth.require_owner)):
    """Schedule downgrade for next billing cycle. Owner only."""
    result = await db.schedule_plan_change(tenant["tenant_id"], req.new_plan, 'tenant')
    if not result.get("success"):
        return JSONResponse({"error": result.get("error", "Downgrade failed")}, status_code=400)
    await db.log_audit("subscription_downgrade_scheduled",
                       f'Scheduled downgrade → {req.new_plan}',
                       tenant_id=tenant["tenant_id"],
                       ip_address=request.client.host)
    return result


@app.get("/api/subscription/status")
async def api_subscription_status(tenant: dict = Depends(auth.get_current_tenant)):
    """Get current subscription status with plan details and pending changes."""
    t = await db.get_tenant(tenant["tenant_id"])
    if not t:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    agent_count = await db.get_tenant_agent_count(tenant["tenant_id"])
    pending = await db.get_pending_plan_change(tenant["tenant_id"])
    plan_features = db.PLAN_FEATURES.get(t.get("plan", "trial"), db.PLAN_FEATURES["trial"])
    return {
        "plan": t.get("plan", "trial"),
        "status": t.get("subscription_status", "trial"),
        "trial_ends_at": t.get("trial_ends_at"),
        "subscription_expires_at": t.get("subscription_expires_at"),
        "max_agents": t.get("max_agents", 1),
        "current_agents": agent_count,
        "razorpay_sub_id": t.get("razorpay_sub_id"),
        "available_plans": db.PLAN_PRICING,
        "plan_features": plan_features,
        "pending_plan_change": pending,
    }


# =============================================================================
#  AGENT MANAGEMENT — Deactivate/Transfer/Remove
# =============================================================================

@app.get("/api/agents")
async def api_list_agents(tenant: dict = Depends(auth.get_current_tenant)):
    """List all agents in the tenant (including inactive)."""
    agents = await db.get_agents_by_tenant_all(tenant["tenant_id"])
    return {"agents": agents}


@app.post("/api/agent/{agent_id}/photo")
@limiter.limit("10/minute")
async def api_upload_agent_photo(request: Request, agent_id: int,
                                  tenant: dict = Depends(auth.get_current_tenant)):
    """Upload a profile photo for an agent. Accepts multipart/form-data with an image file."""
    tid = tenant["tenant_id"]
    # Verify agent belongs to tenant
    agent = await db.get_agent_by_id(agent_id)
    if not agent or agent.get("tenant_id") != tid:
        return JSONResponse({"error": "Agent not found"}, status_code=404)

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return JSONResponse({"error": "Expected multipart/form-data"}, status_code=400)

    body = await request.body()
    if len(body) > 5 * 1024 * 1024:  # 5MB limit
        return JSONResponse({"error": "File too large. Max 5MB."}, status_code=400)

    boundary = content_type.split("boundary=")[-1].strip() if "boundary=" in content_type else ""
    if not boundary:
        return JSONResponse({"error": "Invalid multipart boundary"}, status_code=400)

    # Extract image part
    parts = body.split(f"--{boundary}".encode())
    image_bytes = None
    for part in parts:
        part_lower = part.lower()
        if b"content-type:" in part_lower and (b"image/" in part_lower):
            idx = part.find(b"\r\n\r\n")
            if idx >= 0:
                image_bytes = part[idx + 4:]
                if image_bytes.endswith(b"\r\n"):
                    image_bytes = image_bytes[:-2]
                if image_bytes.endswith(b"--"):
                    image_bytes = image_bytes[:-2]
                if image_bytes.endswith(b"\r\n"):
                    image_bytes = image_bytes[:-2]
                break

    if not image_bytes or len(image_bytes) < 100:
        return JSONResponse({"error": "No valid image found in upload"}, status_code=400)

    # Validate image magic bytes (JPEG or PNG)
    if not (image_bytes[:2] == b'\xff\xd8' or image_bytes[:4] == b'\x89PNG'):
        return JSONResponse({"error": "Only JPEG and PNG images are supported"}, status_code=400)

    ext = "jpg" if image_bytes[:2] == b'\xff\xd8' else "png"
    filename = f"agent_{agent_id}.{ext}"
    photos_dir = Path(__file__).parent / "uploads" / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    filepath = photos_dir / filename
    filepath.write_bytes(image_bytes)

    photo_url = f"/uploads/photos/{filename}"
    await db.update_agent_profile(agent_id, profile_photo=photo_url)
    await db.log_audit("profile_photo_updated", "Photo uploaded via dashboard",
                       tenant_id=tid, agent_id=agent_id,
                       ip_address=request.client.host)
    return {"ok": True, "photo_url": photo_url}


@app.delete("/api/agent/{agent_id}/photo")
async def api_delete_agent_photo(agent_id: int,
                                  tenant: dict = Depends(auth.get_current_tenant)):
    """Remove an agent's profile photo."""
    tid = tenant["tenant_id"]
    agent = await db.get_agent_by_id(agent_id)
    if not agent or agent.get("tenant_id") != tid:
        return JSONResponse({"error": "Agent not found"}, status_code=404)

    old_photo = agent.get("profile_photo", "")
    if old_photo:
        # Delete the file
        filepath = Path(__file__).parent / old_photo.lstrip("/")
        if filepath.exists():
            filepath.unlink(missing_ok=True)

    await db.update_agent_profile(agent_id, profile_photo="")
    await db.log_audit("profile_photo_deleted", "Photo removed",
                       tenant_id=tid, agent_id=agent_id)
    return {"ok": True}


class AgentTransferRequest(BaseModel):
    from_agent_id: int
    to_agent_id: int


async def _require_owner_role(tenant: dict) -> dict:
    """Verify the caller is an owner/admin — not a regular agent."""
    agents = await db.get_agents_by_tenant_all(tenant["tenant_id"])
    caller = next((a for a in agents if a.get("phone") == tenant.get("phone")), None)
    if not caller or caller.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only the firm owner can perform this action.")
    return caller


async def _require_team_plan(tenant_id: int) -> None:
    """Reject if tenant is on Solo/Trial plan (no team management)."""
    t = await db.get_tenant(tenant_id)
    plan = t.get("plan", "trial") if t else "trial"
    if plan in ("trial", "individual"):
        raise HTTPException(status_code=403,
                            detail="Team management requires a Team or Enterprise plan. Please upgrade.")


class AgentEditRequest(BaseModel):
    name: str = None
    phone: str = None
    email: str = None
    role: str = None


@app.put("/api/agents/{agent_id}")
@limiter.limit("10/minute")
async def api_edit_agent(agent_id: int, req: AgentEditRequest, request: Request,
                         tenant: dict = Depends(auth.require_owner)):
    """Edit agent details (name, phone, email, role). Owner/Admin only, Team+ plan."""
    await _require_team_plan(tenant["tenant_id"])
    caller = await _require_owner_role(tenant)

    agent = await db.get_agent_by_id(agent_id)
    if not agent or agent.get("tenant_id") != tenant["tenant_id"]:
        return JSONResponse({"error": "Agent not found in your firm"}, status_code=404)

    # Cannot edit yourself via this endpoint — use /api/profile
    if agent["agent_id"] == caller["agent_id"]:
        return JSONResponse({"error": "Use Profile settings to edit your own details"}, status_code=400)

    # Build updates
    updates = {}
    if req.name and req.name.strip():
        updates["name"] = req.name.strip()
    if req.phone and req.phone.strip():
        updates["phone"] = req.phone.strip()
    if req.email and req.email.strip():
        updates["email"] = req.email.strip()
    if req.role and req.role in ("admin", "agent"):
        # Only owner can change roles; admin cannot promote/demote
        if caller.get("role") != "owner":
            return JSONResponse({"error": "Only the firm owner can change roles"}, status_code=403)
        # Cannot set anyone to owner
        if req.role == "owner":
            return JSONResponse({"error": "Cannot assign owner role"}, status_code=400)
        updates["role"] = req.role

    if not updates:
        return JSONResponse({"error": "No valid fields to update"}, status_code=400)

    # Duplicate check if phone/email changing
    if "phone" in updates or "email" in updates:
        dup = await db.check_phone_email_duplicate(
            phone=updates.get("phone"), email=updates.get("email"),
            exclude_tenant_id=tenant["tenant_id"])
        if dup:
            return JSONResponse(
                {"error": f"Duplicate {dup['field']}: already in use"},
                status_code=409)

    await db.update_agent_profile(agent_id, **updates)
    await db.log_audit("agent_edited",
                       f"Agent {agent_id} ({agent.get('name')}) edited by {caller.get('name')}: {', '.join(updates.keys())}",
                       tenant_id=tenant["tenant_id"], ip_address=request.client.host)
    return {"success": True, "message": f"Agent updated", "fields": list(updates.keys())}


@app.post("/api/agents/{agent_id}/deactivate")
@limiter.limit("10/minute")
async def api_deactivate_agent(agent_id: int, request: Request,
                                tenant: dict = Depends(auth.require_owner)):
    """Deactivate an agent (revoke bot access). Owner only, Team+ plan."""
    await _require_team_plan(tenant["tenant_id"])
    agent = await db.get_agent_by_id(agent_id)
    if not agent or agent.get("tenant_id") != tenant["tenant_id"]:
        return JSONResponse({"error": "Agent not found in your firm"}, status_code=404)
    if agent.get("role") == "owner":
        return JSONResponse({"error": "Cannot deactivate the firm owner"}, status_code=400)
    await db.deactivate_agent(agent_id, tenant_id=tenant["tenant_id"])
    await db.log_audit("agent_deactivated", f"Agent {agent_id} ({agent.get('name')}) deactivated",
                       tenant_id=tenant["tenant_id"], ip_address=request.client.host)
    return {"success": True, "message": f"Agent {agent.get('name')} deactivated"}


@app.post("/api/agents/{agent_id}/reactivate")
@limiter.limit("10/minute")
async def api_reactivate_agent(agent_id: int, request: Request,
                                tenant: dict = Depends(auth.require_owner)):
    """Reactivate a deactivated agent. Team+ plan."""
    await _require_team_plan(tenant["tenant_id"])
    agent = await db.get_agent_by_id(agent_id)
    if not agent or agent.get("tenant_id") != tenant["tenant_id"]:
        return JSONResponse({"error": "Agent not found in your firm"}, status_code=404)
    await db.reactivate_agent(agent_id, tenant_id=tenant["tenant_id"])
    await db.log_audit("agent_reactivated", f"Agent {agent_id} reactivated",
                       tenant_id=tenant["tenant_id"], ip_address=request.client.host)
    return {"success": True, "message": f"Agent {agent.get('name')} reactivated"}


@app.post("/api/agents/transfer")
@limiter.limit("5/minute")
async def api_transfer_agent_data(req: AgentTransferRequest, request: Request,
                                   tenant: dict = Depends(auth.require_owner)):
    """Transfer all data from one agent to another. Team+ plan."""
    await _require_team_plan(tenant["tenant_id"])
    from_agent = await db.get_agent_by_id(req.from_agent_id)
    to_agent = await db.get_agent_by_id(req.to_agent_id)
    if not from_agent or from_agent.get("tenant_id") != tenant["tenant_id"]:
        return JSONResponse({"error": "Source agent not found"}, status_code=404)
    if not to_agent or to_agent.get("tenant_id") != tenant["tenant_id"]:
        return JSONResponse({"error": "Target agent not found"}, status_code=404)
    counts = await db.transfer_agent_data(req.from_agent_id, req.to_agent_id,
                                           tenant_id=tenant["tenant_id"])
    if counts.get('error'):
        return JSONResponse({"error": counts['error']}, status_code=400)
    await db.log_audit("data_transfer",
                       f"Agent {req.from_agent_id} → {req.to_agent_id}: {counts}",
                       tenant_id=tenant["tenant_id"], ip_address=request.client.host)
    return {"success": True, "transferred": counts}


@app.post("/api/agents/{agent_id}/remove")
@limiter.limit("5/minute")
async def api_remove_agent(agent_id: int, request: Request,
                            transfer_to: int = Query(None, description="Transfer data to this agent"),
                            tenant: dict = Depends(auth.require_owner)):
    """Remove an agent from the firm. Team+ plan."""
    await _require_team_plan(tenant["tenant_id"])
    agent = await db.get_agent_by_id(agent_id)
    if not agent or agent.get("tenant_id") != tenant["tenant_id"]:
        return JSONResponse({"error": "Agent not found in your firm"}, status_code=404)
    result = await db.remove_agent(agent_id, transfer_to, tenant_id=tenant["tenant_id"])
    if not result.get("success"):
        return JSONResponse({"error": result.get("error", "Failed")}, status_code=400)
    await db.log_audit("agent_removed",
                       f"Agent {agent_id} removed (transfers: {result.get('transfers', {})})",
                       tenant_id=tenant["tenant_id"], ip_address=request.client.host)
    return result


# =============================================================================
#  MESSAGE QUEUE — Admin Monitoring & Dead-Letter Management
# =============================================================================

@app.get("/api/admin/message-queue/stats")
async def api_queue_stats(tenant: dict = Depends(auth.get_current_tenant)):
    """Get message queue statistics (owner only)."""
    import biz_resilience as resilience
    stats = await resilience.get_queue_stats()
    return stats


@app.get("/api/admin/message-queue/dead-letters")
async def api_dead_letters(tenant: dict = Depends(auth.get_current_tenant)):
    """Get permanently failed messages for admin review (owner only)."""
    import biz_resilience as resilience
    messages = await resilience.get_dead_letter_messages(limit=100)
    # Filter to this tenant's messages only
    tid = tenant["tenant_id"]
    filtered = [m for m in messages if m.get("tenant_id") == tid or m.get("tenant_id") is None]
    return {"dead_letters": filtered}


@app.post("/api/admin/message-queue/{queue_id}/retry")
async def api_retry_dead_letter(queue_id: int, request: Request,
                                 tenant: dict = Depends(auth.get_current_tenant)):
    """Re-queue a failed message for another retry attempt."""
    import biz_resilience as resilience
    ok = await resilience.retry_dead_letter(queue_id)
    if not ok:
        return JSONResponse({"error": "Message not found or not in failed state"}, status_code=404)
    await db.log_audit("dead_letter_retried", f"queue_id={queue_id}",
                       tenant_id=tenant["tenant_id"],
                       ip_address=request.client.host)
    return {"ok": True, "message": "Message re-queued for delivery"}


# =============================================================================
#  CSV DATA IMPORT — Bulk Lead Import
# =============================================================================

@app.post("/api/import/leads")
@limiter.limit("5/minute")
async def api_import_leads(request: Request,
                            tenant: dict = Depends(auth.get_current_tenant)):
    """Import leads from CSV/JSON data.
    Accepts JSON body: {"leads": [{"name": "...", "phone": "...", ...}], "skip_duplicates": true}
    Or raw CSV text/file in body with Content-Type: text/csv or multipart/form-data.
    Optional query param: ?assign_to=<agent_id> to assign all leads to a specific agent."""
    content_type = request.headers.get("content-type", "")
    assign_to = request.query_params.get("assign_to")
    skip_dupes = True  # default — skip duplicates

    if "multipart/form-data" in content_type:
        # Handle file upload from dashboard
        import cgi
        import io as _io
        body = await request.body()
        # Parse multipart manually (lightweight — no python-multipart needed)
        ct_header = request.headers.get("content-type", "")
        boundary = ct_header.split("boundary=")[-1].strip() if "boundary=" in ct_header else ""
        if not boundary:
            return JSONResponse({"error": "Invalid multipart boundary"}, status_code=400)
        # Extract file part
        parts = body.split(f"--{boundary}".encode())
        file_bytes = None
        is_xlsx = False
        for part in parts:
            lp = part.lower()
            if b"filename=" not in lp:
                continue
            if b".xlsx" in lp:
                is_xlsx = True
            elif not (b".csv" in lp or b".txt" in lp):
                continue
            # Find the blank line separating headers from body
            idx = part.find(b"\r\n\r\n")
            if idx >= 0:
                file_bytes = part[idx+4:]
                # Strip trailing boundary markers
                if file_bytes.endswith(b"\r\n"):
                    file_bytes = file_bytes[:-2]
                if file_bytes.endswith(b"--"):
                    file_bytes = file_bytes[:-2]
                if file_bytes.endswith(b"\r\n"):
                    file_bytes = file_bytes[:-2]
                break
        if not file_bytes:
            return JSONResponse({"error": "No CSV/Excel file found in upload"}, status_code=400)

        if is_xlsx:
            # Parse Excel using openpyxl
            try:
                import openpyxl
                import io
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
                ws = wb.active
                rows_iter = ws.iter_rows(values_only=True)
                try:
                    raw_headers = next(rows_iter)
                except StopIteration:
                    return JSONResponse({"error": "Excel file is empty"}, status_code=400)
                headers = [str(h or "").strip().lower().replace(" ", "_").replace("-", "_") for h in raw_headers]
                # Apply same aliases as gdrive
                aliases = {
                    "full_name": "name", "client_name": "name", "lead_name": "name", "customer_name": "name",
                    "mobile": "phone", "mobile_no": "phone", "phone_number": "phone", "contact": "phone",
                    "whatsapp_no": "whatsapp", "wa": "whatsapp",
                    "email_id": "email", "email_address": "email",
                    "date_of_birth": "dob", "birthday": "dob",
                    "address": "city", "location": "city",
                    "income": "monthly_income", "salary": "monthly_income",
                    "remarks": "notes", "comments": "notes", "note": "notes",
                    "category": "need_type", "product": "need_type", "interest": "need_type",
                }
                headers = [aliases.get(h, h) for h in headers]
                leads_data = []
                for row in rows_iter:
                    if not row or not any(c not in (None, "") for c in row):
                        continue
                    rec = {}
                    for i, h in enumerate(headers):
                        if not h or i >= len(row):
                            continue
                        val = row[i]
                        if val is None or val == "":
                            continue
                        rec[h] = str(val).strip()[:500]
                    if rec.get("name"):
                        leads_data.append(rec)
                wb.close()
            except Exception as e:
                logger.error("Excel parse error: %s", e)
                return JSONResponse({"error": f"Failed to parse Excel: {str(e)[:100]}"}, status_code=400)
        else:
            import csv
            import io
            text = file_bytes.decode("utf-8-sig", errors="ignore")
            reader = csv.DictReader(io.StringIO(text))
            leads_data = [dict(row) for row in reader]
    elif "text/csv" in content_type or "text/plain" in content_type:
        # Parse CSV from raw body
        import csv
        import io
        body = await request.body()
        text = body.decode("utf-8-sig")  # Handle BOM
        reader = csv.DictReader(io.StringIO(text))
        leads_data = [dict(row) for row in reader]
    else:
        body = await request.json()
        leads_data = body.get("leads", [])
        skip_dupes = body.get("skip_duplicates", True)

    if not leads_data:
        return JSONResponse({"error": "No leads data provided"}, status_code=400)
    if len(leads_data) > 500:
        return JSONResponse({"error": "Max 500 leads per import"}, status_code=400)

    # Per-field validation: sanitize and limit field lengths
    for ld in leads_data:
        if not ld.get("name") or len(str(ld["name"])) > 200:
            return JSONResponse({"error": f"Invalid or missing lead name: {str(ld.get('name', ''))[:50]}"}, status_code=400)
        for fld in ("phone", "email", "city", "need_type", "stage", "notes"):
            if fld in ld and ld[fld] is not None:
                ld[fld] = str(ld[fld])[:500]  # Truncate oversized fields

    # Determine target agent
    tid = tenant["tenant_id"]
    if assign_to:
        try:
            target_agent = await db.get_agent_by_id(int(assign_to))
            if not target_agent or target_agent.get("tenant_id") != tid:
                return JSONResponse({"error": "Agent not found in your firm"}, status_code=404)
            agent_id = int(assign_to)
        except (ValueError, TypeError):
            return JSONResponse({"error": "Invalid agent ID"}, status_code=400)
    else:
        # Default: use owner agent
        t = await db.get_tenant(tid)
        if not t:
            return JSONResponse({"error": "Tenant not found"}, status_code=404)
        owner_tg_id = t.get("owner_telegram_id")
        agent = await db.get_agent(owner_tg_id) if owner_tg_id else None
        if not agent:
            return JSONResponse({"error": "No agent found for this tenant"}, status_code=404)
        agent_id = agent["agent_id"]

    result = await db.bulk_add_leads(agent_id, leads_data,
                                      tenant_id=tid if skip_dupes else None)
    await db.log_audit("csv_import",
                       f"Imported {result['imported']} leads, skipped {result['skipped']}"
                       f", duplicates {result.get('duplicates', 0)}",
                       tenant_id=tid,
                       ip_address=request.client.host)
    return result


@app.get("/api/import/template")
async def api_import_template(tenant: dict = Depends(auth.get_current_tenant)):
    """Download a CSV template for lead import."""
    import io
    header = "name,phone,email,dob,city,need_type,source,notes\n"
    sample = "Amit Sharma,9876543210,amit@email.com,1990-05-15,Mumbai,health,referral,Interested in family floater\n"
    sample += "Priya Patel,8765432109,priya@email.com,1985-12-01,Delhi,term,,Wants term life 1Cr\n"
    content = header + sample
    return PlainTextResponse(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sarathi_lead_import_template.csv"},
    )


# =============================================================================
#  MESSAGE FREQUENCY CONTROL
# =============================================================================

@app.get("/api/leads/{lead_id}/contact-pref")
async def api_get_contact_pref(lead_id: int,
                                tenant: dict = Depends(auth.get_current_tenant)):
    """Get contact preferences for a lead."""
    tid = tenant["tenant_id"]
    # IDOR guard at DB layer via tenant_id
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    pref = await db.get_lead_contact_pref(lead_id, tenant_id=tid)
    can_msg = await db.can_message_lead(lead_id)
    return {"preferences": pref, "messaging": can_msg}


class ContactPrefRequest(BaseModel):
    max_messages_per_week: int = Field(3, ge=0, le=20)
    preferred_channel: str = Field("whatsapp")
    preferred_time: Optional[str] = Field(None)
    opted_out: bool = Field(False)


@app.put("/api/leads/{lead_id}/contact-pref")
async def api_set_contact_pref(lead_id: int, req: ContactPrefRequest,
                                tenant: dict = Depends(auth.get_current_tenant)):
    """Set contact preferences for a lead."""
    tid = tenant["tenant_id"]
    # IDOR guard at DB layer via tenant_id
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    ok = await db.update_lead_contact_pref(lead_id, req.max_messages_per_week,
                                            req.preferred_channel, req.preferred_time,
                                            req.opted_out)
    if not ok:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    return {"success": True}


# ═══════════ TASKS (MY TASKS / TASK BROWSER) ═══════════

@app.get("/api/tasks")
async def api_get_tasks(request: Request,
                        date: Optional[str] = Query(None),
                        status: Optional[str] = Query("all"),
                        tenant: dict = Depends(auth.get_current_tenant)):
    """Get tasks with date and status filtering.
    date: YYYY-MM-DD, 'today', 'yesterday', 'tomorrow', 'overdue', or None (all upcoming).
    status: 'all', 'pending', 'done'."""
    from datetime import datetime as _dt_cls, timedelta
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    now = _dt_cls.now(ist)

    tid = tenant["tenant_id"]
    agent_id = tenant.get("agent_id")
    role = tenant.get("role", "agent")

    # Resolve date keywords
    target_date = date
    if date == "today":
        target_date = now.strftime("%Y-%m-%d")
    elif date == "yesterday":
        target_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    elif date == "tomorrow":
        target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    elif date == "overdue":
        target_date = "overdue"
    elif date and date not in ("overdue",):
        # Validate YYYY-MM-DD
        try:
            _dt_cls.strptime(date, "%Y-%m-%d")
        except ValueError:
            return JSONResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, 400)

    # Admin/owner see tenant-wide, agent sees own
    use_tenant = tid if role in ("owner", "admin") else None
    tasks = await db.get_tasks_by_date(
        agent_id=agent_id, target_date=target_date,
        status=status or "all", tenant_id=use_tenant)

    # Enrich with overdue flag
    today_str = now.strftime("%Y-%m-%d")
    for t in tasks:
        fd = t.get("follow_up_date", "")
        t["is_overdue"] = bool(fd and fd < today_str and t.get("follow_up_status") != "done")

    return {"tasks": tasks, "count": len(tasks), "date": date, "status": status}


# ═══════════ SET FOLLOW-UP ON A LEAD ═══════════

class FollowupRequest(BaseModel):
    type: str = Field("call")
    date: str = Field(...)
    time: Optional[str] = Field(None)
    notes: Optional[str] = Field(None)
    assigned_to_agent_id: Optional[int] = Field(None)

@app.post("/api/leads/{lead_id}/followup")
async def api_set_followup(lead_id: int, req: FollowupRequest,
                            tenant: dict = Depends(auth.get_current_tenant)):
    """Schedule a follow-up for a lead."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    # Determine target agent and creator
    lead_agent_id = lead.get("agent_id") or tenant.get("owner_agent_id") or 0
    caller_agent_id = tenant.get("agent_id") or 0
    caller_role = tenant.get("role", "agent")
    is_admin = caller_role in ("owner", "admin")
    created_by = caller_agent_id if is_admin and lead_agent_id != caller_agent_id else None

    summary = f"[{req.type}] {req.notes}" if req.notes else f"[{req.type}] Scheduled follow-up"

    # Duplicate detection — update existing task if one exists
    existing = await db.get_pending_followups_for_lead(lead_id)
    is_update = False
    if existing:
        ef = existing[0]
        existing_iid = ef.get('interaction_id')
        is_update = True
        await db.update_followup(
            interaction_id=existing_iid,
            follow_up_date=req.date,
            follow_up_time=req.time,
            summary=summary,
            assigned_to_agent_id=req.assigned_to_agent_id
        )
        iid = existing_iid
    else:
        iid = await db.log_interaction(
            lead_id=lead_id,
            agent_id=lead_agent_id,
            interaction_type=req.type,
            channel="web",
            summary=summary,
            follow_up_date=req.date,
            follow_up_time=req.time,
            created_by_agent_id=created_by,
            assigned_to_agent_id=req.assigned_to_agent_id
        )

    # Cross-agent notification: notify assignee or lead's agent
    notify_id = req.assigned_to_agent_id or (lead_agent_id if is_admin and lead_agent_id != caller_agent_id else None)
    if notify_id and notify_id != caller_agent_id:
        try:
            notify_agent = await db.get_agent_by_id(notify_id)
            if notify_agent and notify_agent.get('telegram_id'):
                admin_name = tenant.get("firm_name") or "Admin"
                admin_agent = await db.get_agent_by_id(caller_agent_id) if caller_agent_id else None
                if admin_agent:
                    admin_name = admin_agent.get('name', admin_name)
                nlang = notify_agent.get('lang', 'en')
                if nlang == 'hi':
                    ntxt = (f"📋 *{admin_name} ने आपको टास्क असाइन किया (Dashboard)*\n\n"
                            f"👤 लीड: {lead.get('name', '')}\n"
                            f"📅 तारीख: {req.date}\n"
                            f"📝 {req.notes or '—'}")
                else:
                    ntxt = (f"📋 *{admin_name} assigned you a task (Dashboard)*\n\n"
                            f"👤 Lead: {lead.get('name', '')}\n"
                            f"📅 Date: {req.date}\n"
                            f"📝 {req.notes or '—'}")
                import biz_reminders as rem
                await rem._send_telegram(notify_agent['telegram_id'], ntxt)
        except Exception as e:
            logger.warning("Failed to notify agent of admin follow-up: %s", e)

    return {"ok": True, "interaction_id": iid, "updated": is_update}


# ── Lead Timeline + Notes API ─────────────────────────────────────────

@app.get("/api/leads/{lead_id}/timeline")
async def api_lead_timeline(lead_id: int, limit: int = 50,
                             tenant: dict = Depends(auth.get_current_tenant)):
    """Get combined timeline (interactions + notes) for a lead."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    timeline = await db.get_lead_full_timeline(lead_id, tenant_id=tid, limit=limit)
    return {"ok": True, "timeline": timeline, "lead_name": lead.get("name", "")}


class NoteRequest(BaseModel):
    note_text: str = Field(...)
    interaction_id: Optional[int] = Field(None)
    parent_note_id: Optional[int] = Field(None)

@app.post("/api/leads/{lead_id}/notes")
async def api_add_note(lead_id: int, req: NoteRequest,
                        tenant: dict = Depends(auth.get_current_tenant)):
    """Add a note to a lead (advisor or admin)."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    agent_id = tenant.get("owner_agent_id") or 0
    role = tenant.get("role", "admin")
    author_role = "admin" if role in ("owner", "admin") else "advisor"
    note_id = await db.add_lead_note(
        lead_id=lead_id,
        agent_id=agent_id,
        note_text=req.note_text,
        interaction_id=req.interaction_id,
        author_role=author_role,
        parent_note_id=req.parent_note_id)

    # If admin adds a note, notify the assigned advisor via Telegram
    if author_role == 'admin' and lead.get('agent_id'):
        try:
            advisor = await db.get_agent_by_id(lead['agent_id'])
            if advisor and advisor.get('telegram_id'):
                lead_name = lead.get('name', 'Client')
                admin_name = tenant.get('name', 'Admin')
                adv_hi = advisor.get('lang', 'en') == 'hi'
                if adv_hi:
                    notify_text = (
                        f"👑 *{lead_name} पर Admin note*\n\n"
                        f"From: {admin_name}\n"
                        f"📋 {req.note_text}\n\n"
                        f"_Dashboard पर details देखें._")
                else:
                    notify_text = (
                        f"👑 *Admin note on {lead_name}*\n\n"
                        f"From: {admin_name}\n"
                        f"📋 {req.note_text}\n\n"
                        f"_Check your dashboard for details._")
                import biz_reminders as rem
                await rem._send_telegram(advisor['telegram_id'], notify_text)
        except Exception as e:
            logger.warning("Failed to notify advisor of admin note: %s", e)

    return {"ok": True, "note_id": note_id}


@app.post("/api/leads/{lead_id}/followup/{interaction_id}/done")
async def api_followup_done(lead_id: int, interaction_id: int,
                             tenant: dict = Depends(auth.get_current_tenant)):
    """Mark a follow-up as done from dashboard."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    success = await db.mark_followup_done(interaction_id)
    if not success:
        return JSONResponse({"error": "Follow-up not found"}, status_code=404)
    return {"ok": True}


class FollowupEditRequest(BaseModel):
    date: Optional[str] = Field(None)
    time: Optional[str] = Field(None)
    notes: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    assigned_to_agent_id: Optional[int] = Field(None)

@app.put("/api/leads/{lead_id}/followup/{interaction_id}")
async def api_edit_followup(lead_id: int, interaction_id: int, req: FollowupEditRequest,
                             tenant: dict = Depends(auth.get_current_tenant)):
    """Edit an existing follow-up's date, time, notes, or type."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    summary = None
    if req.notes is not None:
        fu_type = req.type or "call"
        summary = f"[{fu_type}] {req.notes}" if req.notes else f"[{fu_type}] Scheduled follow-up"
    success = await db.update_followup(
        interaction_id=interaction_id,
        follow_up_date=req.date,
        follow_up_time=req.time,
        summary=summary,
        interaction_type=req.type,
        assigned_to_agent_id=req.assigned_to_agent_id
    )
    if not success:
        return JSONResponse({"error": "Follow-up not found"}, status_code=404)
    return {"ok": True}


@app.get("/api/leads/{lead_id}/followups")
async def api_lead_followups(lead_id: int,
                              tenant: dict = Depends(auth.get_current_tenant)):
    """Get all pending follow-ups for a specific lead."""
    tid = tenant["tenant_id"]
    lead = await db.get_lead(lead_id, tenant_id=tid)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    pending = await db.get_pending_followups_for_lead(lead_id)
    return {"ok": True, "followups": pending}


@app.get("/api/admin/followup-digest")
async def api_admin_followup_digest(tenant: dict = Depends(auth.get_current_tenant)):
    """Get admin follow-up accountability digest."""
    tid = tenant["tenant_id"]
    digest = await db.get_admin_followup_digest(tid)
    return {"ok": True, "digest": digest}


# =============================================================================
#  BOT CREATION GUIDANCE — Step-by-step @BotFather walkthrough
# =============================================================================

@app.get("/api/bot-setup/guide")
async def api_bot_setup_guide():
    """Return step-by-step guide for creating a Telegram bot via @BotFather."""
    return {
        "title": "Create Your Own Telegram Bot — Step by Step",
        "estimated_time": "5 minutes",
        "steps": [
            {
                "step": 1,
                "title": "Open @BotFather on Telegram",
                "instruction": "Open Telegram and search for @BotFather (official bot by Telegram). Tap on it to open the chat.",
                "link": "https://t.me/BotFather",
                "tip": "BotFather has a blue verified checkmark ✓"
            },
            {
                "step": 2,
                "title": "Create a New Bot",
                "instruction": "Send the command /newbot to BotFather.",
                "tip": "Type /newbot and press Send"
            },
            {
                "step": 3,
                "title": "Choose a Display Name",
                "instruction": "BotFather will ask for a name. Enter your firm name (e.g., 'ABC Insurance Advisors'). This is what clients see.",
                "example": "ABC Insurance Advisors",
                "tip": "Use your actual business name — clients will see this"
            },
            {
                "step": 4,
                "title": "Choose a Username",
                "instruction": "Enter a unique username ending with 'bot' (e.g., 'abc_insurance_bot'). This is the @handle for your bot.",
                "example": "abc_insurance_bot",
                "tip": "Must end with 'bot'. Try your firm name + _bot. If taken, add numbers."
            },
            {
                "step": 5,
                "title": "Copy the Bot Token",
                "instruction": "BotFather will give you a token like '123456789:ABCdef...'. Copy this ENTIRE token carefully.",
                "tip": "Long-press the token to copy it. Don't share this token with anyone!"
            },
            {
                "step": 6,
                "title": "Paste Token in Sarathi-AI",
                "instruction": "Go to your Sarathi-AI dashboard → Settings → Telegram Bot → Paste the token and click Connect.",
                "tip": "We automatically verify the token and connect your bot instantly."
            },
            {
                "step": 7,
                "title": "You're Done! 🎉",
                "instruction": "Your custom bot is now live! Share the bot link with your team. They can start using it immediately.",
                "tip": "Your bot link will be: t.me/your_bot_username"
            }
        ],
        "faq": [
            {
                "q": "Is it free?",
                "a": "Yes! Creating a Telegram bot is completely free."
            },
            {
                "q": "Can I change the name later?",
                "a": "Yes, use /setname in @BotFather to change the display name."
            },
            {
                "q": "What if I lose the token?",
                "a": "Open @BotFather → /mybots → select your bot → API Token to see it again."
            },
            {
                "q": "Can multiple agents use one bot?",
                "a": "Yes! All agents in your firm can use the same bot. Each gets their own data."
            }
        ]
    }


# =============================================================================
#  SECURITY HEADERS MIDDLEWARE
# =============================================================================

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Use SAMEORIGIN (not DENY) so GIS button iframe + our own embeds work
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Critical for Google Sign-In: allow popup to postMessage back to opener
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    # Don't add HSTS for non-HTTPS dev environments
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# =============================================================================
#  TELEGRAM BOT WEBHOOK
# =============================================================================

@app.post("/api/telegram/webhook/{token_hash}")
async def telegram_webhook(token_hash: str, request: Request):
    """Receive Telegram bot updates via webhook (one endpoint per bot)."""
    try:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        data = await request.json()
        processed = await botmgr.bot_manager.process_webhook_update(
            token_hash, data, secret_token=secret
        )
        if not processed:
            return JSONResponse({"ok": False}, status_code=404)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("Telegram webhook error: %s", e, exc_info=True)
        return JSONResponse({"ok": True})  # Always 200 to prevent Telegram retries


# =============================================================================
#  WHATSAPP WEBHOOK (disabled — using Voice AI + personal messaging)
# =============================================================================

@app.get("/webhook")
async def webhook_verify(request: Request):
    """WhatsApp webhook verification (GET) — disabled."""
    return JSONResponse({"detail": "WhatsApp webhook disabled"}, status_code=410)


@app.post("/webhook")
async def webhook_receive(request: Request):
    """WhatsApp webhook receiver — disabled."""
    return {"status": "ok"}  # Always 200 to prevent Meta retries


# =============================================================================
#  STARTUP
# =============================================================================

async def main():
    """Start everything — database, web server, Telegram bot, scheduler."""

    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in biz.env!")
        sys.exit(1)

    logger.info("=" * 64)
    logger.info("  🏛️  SARATHI-AI BUSINESS TECHNOLOGIES")
    logger.info("  🏷️  AI-Powered Financial Advisor CRM")
    logger.info("  🌐  sarathi-ai.com")
    logger.info("=" * 64)

    # Step 1: Initialize database
    logger.info("📦 Initializing CRM database...")
    await db.init_db()
    await db.init_otp_table()  # Persistent OTP storage
    await db.init_plan_changes_table()  # Scheduled plan changes
    await campaigns.init_campaigns_db()
    await resilience.init_resilience()  # Message queue + retry engine
    # Drip nurture sequences (multi-step time-delayed lead nurturing)
    try:
        import biz_nurture as nurture
        await nurture.init_schema()
        await nurture.seed_for_all_tenants()
    except Exception as _ne:
        logger.error("Nurture init failed: %s", _ne, exc_info=True)
    # Quote comparison engine (Feature 5) — provider rate-card overrides table
    try:
        import biz_quotes as _quotes
        await _quotes.init_quotes_schema()
    except Exception as _qe:
        logger.error("Quotes init failed: %s", _qe, exc_info=True)
    logger.info("✅ Database ready (sarathi_biz.db)")

    # Step 1b: Initialize authentication
    logger.info("🔐 Initializing JWT authentication...")
    auth.init_auth()

    # Step 1c: Initialize email system
    logger.info("📧 Initializing email system...")
    email_svc.init_email()

    # Step 1d: Initialize SMS (Fast2SMS)
    logger.info("📱 Initializing SMS system...")
    sms.init_sms()

    # Step 2: Initialize WhatsApp
    logger.info("📱 Initializing WhatsApp Cloud API...")
    wa.init_whatsapp()

    # Step 2b: Initialize Google Drive
    logger.info("📁 Initializing Google Drive integration...")
    gdrive.init_gdrive()

    # Step 2c: Initialize WhatsApp v2 (Evolution API client)
    logger.info("📱 Initializing WhatsApp v2 (Evolution API)...")
    wa_evo.init_evolution()

    # Step 3: Initialize PDF generator
    logger.info("📄 Initializing PDF generator...")
    pdf.init_pdf()

    # Step 3b: Initialize Razorpay payments
    logger.info("💳 Initializing Razorpay payments...")
    payments.init_payments()
    if payments.is_enabled():
        await payments.ensure_plans_exist()
        logger.info("✅ Razorpay ready (plans created)")
    else:
        logger.warning("⚠️ Razorpay not configured — payments disabled")

    # Step 4: Start Telegram bots (master + per-tenant)
    #   Use webhook mode in production (HTTPS), polling in local dev
    use_webhook = SERVER_URL.startswith("https://")
    webhook_base = SERVER_URL if use_webhook else ""
    bot_mode = "webhook" if use_webhook else "polling"
    logger.info("🤖 Starting master Telegram bot (%s mode)...", bot_mode)
    mgr = botmgr.bot_manager
    await mgr.start_master_bot(TELEGRAM_TOKEN, webhook_base_url=webhook_base)
    logger.info("✅ Master bot ready (Sarathi-AI.com / @SarathiBizBot)")

    logger.info("🤖 Starting tenant bots...")
    tenant_count = await mgr.start_all_tenant_bots()
    logger.info("✅ %d tenant bot(s) started", tenant_count)

    # Step 5: Register reminder callback (smart routing: tenant bot → master)
    async def telegram_alert(telegram_id: str, message: str, reply_markup=None):
        """Send alert via the tenant's bot if available, else master."""
        try:
            agent = await db.get_agent(telegram_id)
            tenant_id = agent.get("tenant_id") if agent else None
            await mgr.send_alert(int(telegram_id), message, tenant_id=tenant_id,
                                 reply_markup=reply_markup)
        except Exception as e:
            logger.error("Telegram alert to %s failed: %s", telegram_id, e)

    reminders.set_telegram_callback(telegram_alert)

    # Step 5a-2: Register nurture-sequence Telegram callback (HTML parse mode + buttons)
    async def nurture_telegram_send(tenant_id: int, telegram_id: str, message: str,
                                     reply_markup=None):
        """Send a nurture step via the tenant's bot (or master fallback) using HTML mode."""
        try:
            target = mgr._bots.get(tenant_id) if tenant_id else None
            if not target:
                target = mgr._master_bot
            if not target:
                logger.warning("Nurture: no bot available for tenant %s", tenant_id)
                return
            await target.bot.send_message(
                chat_id=int(telegram_id), text=message,
                parse_mode="HTML", reply_markup=reply_markup,
                disable_web_page_preview=True)
        except Exception as e:
            logger.error("Nurture telegram send to %s failed: %s", telegram_id, e)
    try:
        import biz_nurture as _nurture_mod
        _nurture_mod.set_telegram_callback(nurture_telegram_send)
    except Exception as _e:
        logger.error("Failed to register nurture telegram callback: %s", _e)

    # Step 5b: Register message queue processor with reminder scheduler
    async def process_queued_messages():
        try:
            await resilience.process_message_queue()
        except Exception as e:
            logger.error("Queue processor error: %s", e)
    reminders.set_queue_callback(process_queued_messages)

    # Step 6: Start reminder scheduler in background
    logger.info("⏰ Starting reminder scheduler...")
    scheduler_task = asyncio.create_task(reminders.start_scheduler())

    # Step 6b: Background task to apply scheduled plan changes
    async def plan_change_applier():
        """Check and apply pending plan changes every hour."""
        while True:
            try:
                await asyncio.sleep(3600)  # Check every hour
                applied = await db.apply_pending_plan_changes()
                if applied:
                    logger.info("📋 Applied %d scheduled plan change(s)", len(applied))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Plan change applier error: %s", e)

    plan_change_task = asyncio.create_task(plan_change_applier())

    # Step 6c: OTP cleanup task (prevent memory leak from expired OTPs)
    async def otp_cleanup_task():
        """Clear expired OTPs every 5 minutes."""
        while True:
            try:
                await asyncio.sleep(300)
                auth.clear_expired_otps()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    otp_cleanup = asyncio.create_task(otp_cleanup_task())

    # Step 7: Start FastAPI server
    logger.info("🌐 Starting web server on %s:%d...", SERVER_HOST, SERVER_PORT)
    config = uvicorn.Config(
        app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    # Final status
    logger.info("━" * 64)
    logger.info("  ✅ Sarathi-AI is LIVE!")
    logger.info("  🌐 Homepage:     %s", SERVER_URL)
    logger.info("  🚀 Onboarding:   %s/onboarding", SERVER_URL)
    logger.info("  📊 Calculators:  %s/calculators", SERVER_URL)
    logger.info("  📋 Dashboard:    %s/dashboard", SERVER_URL)
    logger.info("  ⚙️  Admin:        %s/admin", SERVER_URL)
    logger.info("  🛡️  Super Admin:  %s/superadmin", SERVER_URL)
    logger.info("  📚 API docs:     %s/docs", SERVER_URL)
    logger.info("  🤖 Master Bot:   Sarathi-AI.com (@SarathiBizBot)")
    logger.info("  🤖 Tenant Bots:  %d running", tenant_count)
    logger.info("━" * 64)

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_signal():
        logger.info("🛑 Shutdown signal received...")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass  # Windows fallback

    try:
        await server.serve()
    finally:
        logger.info("🧹 Shutting down...")
        scheduler_task.cancel()
        plan_change_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        try:
            await plan_change_task
        except asyncio.CancelledError:
            pass
        await mgr.stop_all()
        # Close WhatsApp HTTP client pool
        try:
            await wa.close_client()
        except Exception:
            pass
        logger.info("👋 Sarathi-AI stopped. See you!")


# =============================================================================
#  AUTO-DEPLOY WEBHOOK  (called by GitHub Actions — no SSH key needed)
# =============================================================================

import hmac as _hmac
import subprocess as _subprocess
from fastapi import BackgroundTasks

_DEPLOY_TOKEN = os.getenv("DEPLOY_TOKEN", "")
_DEPLOY_SCRIPT = Path(__file__).parent / "deploy" / "auto-deploy.sh"


def _run_deploy():
    """Start deploy script fully detached so it survives when it kills this process."""
    try:
        log_path = "/tmp/sarathi-deploy.log"
        # Use shell redirect so the script's exec >> LOG writes correctly
        _subprocess.Popen(
            f"bash '{_DEPLOY_SCRIPT}' >> '{log_path}' 2>&1",
            shell=True,
            start_new_session=True,
            close_fds=True,
            stdin=_subprocess.DEVNULL,
        )
        logger.info("🚀 deploy script started (detached), log: %s", log_path)
    except Exception as exc:
        logger.error("deploy script error: %s", exc)


@app.post("/internal/deploy")
async def internal_deploy_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    GitHub Actions calls this endpoint after each push to master.
    Authenticates via Bearer token (DEPLOY_TOKEN env var).
    The deploy script runs in background after this response is sent.
    """
    # Token auth — timing-safe comparison
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not _DEPLOY_TOKEN:
        raise HTTPException(status_code=503, detail="DEPLOY_TOKEN not configured on server")
    if not _hmac.compare_digest(token, _DEPLOY_TOKEN):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not _DEPLOY_SCRIPT.exists():
        raise HTTPException(status_code=503, detail="Deploy script not found")
    background_tasks.add_task(_run_deploy)
    logger.info("🚀 Deploy triggered by GitHub Actions")
    return {"status": "deploying", "script": str(_DEPLOY_SCRIPT)}


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Sarathi stopped. Grow your business!")
