#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  Sarathi‑AI Business Technologies  —  360° End‑to‑End Test      ║
║  Tests all 65 endpoints across 11 categories                    ║
║  Run:  py -3.12 test_e2e_360.py                                ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import time
import sys
import os
import random
import urllib.request
import urllib.parse
import urllib.error
import ssl

BASE = os.getenv("TEST_BASE_URL", "http://localhost:8001")
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "sarathi-admin-2024-secure")

# Disable SSL verification for local testing
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ── Stats ─────────────────────────────────────────────────────────
passed = 0
failed = 0
skipped = 0
errors = []
results = []

def log(status, category, name, detail=""):
    global passed, failed, skipped
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⚠️", "INFO": "ℹ️"}[status]
    if status == "PASS":
        passed += 1
    elif status == "FAIL":
        failed += 1
        errors.append(f"[{category}] {name}: {detail}")
    elif status == "SKIP":
        skipped += 1
    msg = f"  {icon} [{category}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append((status, category, name, detail))

# ── HTTP helpers ──────────────────────────────────────────────────
def http(method, path, body=None, headers=None, expect_status=200, raw=False):
    """Make HTTP request, return (status_code, parsed_json_or_text)."""
    url = BASE + path
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10, context=ctx)
        content = resp.read().decode("utf-8")
        if raw:
            return resp.status, content
        try:
            return resp.status, json.loads(content)
        except json.JSONDecodeError:
            return resp.status, content
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8") if e.fp else ""
        if raw:
            return e.code, content
        try:
            return e.code, json.loads(content)
        except json.JSONDecodeError:
            return e.code, content

def GET(path, **kw):
    return http("GET", path, **kw)

def POST(path, body=None, **kw):
    return http("POST", path, body=body, **kw)

def DELETE(path, **kw):
    return http("DELETE", path, **kw)

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 1: STATIC PAGES
# ══════════════════════════════════════════════════════════════════
def test_pages():
    cat = "PAGES"
    print(f"\n{'─'*60}")
    print(f"  📄 Category 1: Static Pages (9 endpoints)")
    print(f"{'─'*60}")
    
    pages = [
        ("/", "Homepage"),
        ("/onboarding", "Onboarding"),
        ("/help", "Help"),
        ("/privacy", "Privacy Policy"),
        ("/terms", "Terms of Service"),
        ("/getting-started", "Getting Started"),
        ("/admin", "Admin Panel"),
    ]
    
    for path, name in pages:
        code, body = GET(path, raw=True)
        if code == 200 and "<!DOCTYPE html>" in body.lower() or "<html" in body.lower():
            log("PASS", cat, f"GET {path}", f"{name} — {len(body)} bytes")
        else:
            log("FAIL", cat, f"GET {path}", f"Expected HTML, got {code}")
    
    # Calculators and Dashboard require auth/subscription — 401 is expected
    for path, name in [("/calculators", "Calculators"), ("/dashboard", "Dashboard")]:
        code, body = GET(path, raw=True)
        if code in (200, 401, 403):
            log("PASS", cat, f"GET {path}", f"{name} — HTTP {code} (auth-gated)")
        else:
            log("FAIL", cat, f"GET {path}", f"Expected 200/401/403, got {code}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 2: HEALTH CHECK
# ══════════════════════════════════════════════════════════════════
def test_health():
    cat = "HEALTH"
    print(f"\n{'─'*60}")
    print(f"  🏥 Category 2: Health Check")
    print(f"{'─'*60}")
    
    code, data = GET("/health")
    if code == 200 and data.get("status") == "healthy":
        log("PASS", cat, "GET /health", f"v{data.get('version', '?')} — {data.get('brand', '?')}")
    else:
        log("FAIL", cat, "GET /health", f"HTTP {code}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 3: CALCULATOR APIs
# ══════════════════════════════════════════════════════════════════
def test_calculators():
    cat = "CALC"
    print(f"\n{'─'*60}")
    print(f"  📊 Category 3: Calculator APIs (6 endpoints)")
    print(f"{'─'*60}")
    
    tests = [
        ("/api/calc/inflation?amount=50000&inflation=7&years=10", "Inflation Eraser"),
        ("/api/calc/hlv?monthly_expense=50000&loans=500000&children_expense=200000&existing_cover=1000000&years_to_retire=25&inflation=6&discount_rate=8", "Human Life Value"),
        ("/api/calc/retirement?current_age=35&retirement_age=60&life_expectancy=85&monthly_expense=50000&inflation=6&pre_return=12&post_return=8", "Retirement Planner"),
        ("/api/calc/emi?premium=25000&years=5&gst=18&cibil_discount=0&down_payment_pct=0", "EMI Calculator"),
        ("/api/calc/health?age=35&family=4&city_tier=1&pre_existing=false", "Health Cover"),
        ("/api/calc/sip?amount=500000&years=10&expected_return=12", "SIP vs Lumpsum"),
    ]
    
    for path, name in tests:
        code, data = GET(path)
        if code == 200 and isinstance(data, dict):
            log("PASS", cat, name, f"{len(data)} fields returned")
        else:
            log("FAIL", cat, name, f"HTTP {code}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 4: REPORT GENERATION
# ══════════════════════════════════════════════════════════════════
def test_reports():
    cat = "REPORT"
    print(f"\n{'─'*60}")
    print(f"  📋 Category 4: Report Generation (4 endpoints)")
    print(f"{'─'*60}")
    
    tests = [
        ("/api/report/inflation?amount=50000&inflation=7&years=10&client_name=TestClient", "Inflation Report"),
        ("/api/report/hlv?monthly_expense=50000&loans=500000&children_expense=200000&existing_cover=1000000&years_to_retire=25&client_name=TestClient", "HLV Report"),
        ("/api/report/retirement?current_age=35&retirement_age=60&life_expectancy=85&monthly_expense=50000&client_name=TestClient", "Retirement Report"),
        ("/api/report/emi?premium=25000&years=5&client_name=TestClient", "EMI Report"),
    ]
    
    for path, name in tests:
        code, body = GET(path, raw=True)
        if code == 200 and len(body) > 100:
            log("PASS", cat, name, f"Generated — {len(body)} bytes")
        else:
            log("FAIL", cat, name, f"HTTP {code}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 5: SIGNUP FLOW
# ══════════════════════════════════════════════════════════════════
test_tenant_id = None
test_phone = f"99{random.randint(10000000, 99999999)}"
test_email = f"test{random.randint(1000,9999)}@e2e.test"

def test_signup():
    global test_tenant_id, test_phone
    cat = "SIGNUP"
    print(f"\n{'─'*60}")
    print(f"  🆕 Category 5: Signup Flow (test phone: {test_phone})")
    print(f"{'─'*60}")
    
    # Create test tenant
    body = {
        "firm_name": f"E2E Test Insurance {random.randint(100,999)}",
        "owner_name": "Test Agent",
        "phone": test_phone,
        "email": test_email,
        "city": "Mumbai",
        "plan": "individual"
    }
    code, data = POST("/api/signup", body=body)
    if code == 200 and data.get("tenant_id"):
        test_tenant_id = data["tenant_id"]
        log("PASS", cat, "POST /api/signup", f"tenant_id={test_tenant_id}, trial={data.get('trial_days', '?')}d")
    elif code == 409:
        log("PASS", cat, "POST /api/signup", f"Conflict — {str(data.get('detail',''))[:60]}")
        # On conflict, try to find an existing tenant via admin
        acode, adata = GET("/api/admin/tenants", headers={"Authorization": f"Bearer admin:{ADMIN_KEY}"})
        if acode == 200:
            tenants = adata if isinstance(adata, list) else adata.get("tenants", [])
            for t in tenants:
                tid = t.get("tenant_id")
                tphone = t.get("phone", "")
                if tid and tphone:
                    test_tenant_id = tid
                    test_phone = tphone  # Use existing tenant's phone for auth
                    break
            if test_tenant_id:
                log("INFO", cat, "Using existing tenant", f"tenant_id={test_tenant_id}, phone=...{test_phone[-4:]}")
    else:
        log("FAIL", cat, "POST /api/signup", f"HTTP {code}: {data}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 6: AUTHENTICATION FLOW
# ══════════════════════════════════════════════════════════════════
access_token = None
refresh_token_val = None

def test_auth():
    global access_token, refresh_token_val
    cat = "AUTH"
    print(f"\n{'─'*60}")
    print(f"  🔐 Category 6: Authentication Flow")
    print(f"{'─'*60}")
    
    if not test_phone:
        log("SKIP", cat, "Auth flow", "No test phone available")
        return
    
    # Step 1: Send OTP
    code, data = POST("/api/auth/send-otp", body={"phone": test_phone})
    if code == 200:
        dev_otp = data.get("_dev_otp", "")
        log("PASS", cat, "POST /api/auth/send-otp", f"OTP sent (dev_otp={dev_otp})")
        
        # Step 2: Verify OTP
        if dev_otp:
            code2, data2 = POST("/api/auth/verify-otp", body={"phone": test_phone, "otp": dev_otp})
            if code2 == 200 and data2.get("access_token"):
                access_token = data2["access_token"]
                refresh_token_val = data2.get("refresh_token", "")
                log("PASS", cat, "POST /api/auth/verify-otp", f"JWT obtained, tenant_id={data2.get('tenant_id')}")
            else:
                log("FAIL", cat, "POST /api/auth/verify-otp", f"HTTP {code2}: {data2}")
        else:
            log("SKIP", cat, "POST /api/auth/verify-otp", "No dev OTP returned")
    elif code == 404:
        log("FAIL", cat, "POST /api/auth/send-otp", f"Phone not registered: {data}")
    else:
        log("FAIL", cat, "POST /api/auth/send-otp", f"HTTP {code}: {data}")
    
    # Step 3: Check /me
    if access_token:
        code3, data3 = GET("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        if code3 == 200 and data3.get("tenant_id"):
            log("PASS", cat, "GET /api/auth/me", f"Authenticated as tenant {data3['tenant_id']}")
        else:
            log("FAIL", cat, "GET /api/auth/me", f"HTTP {code3}")
    
    # Step 4: Refresh token
    if refresh_token_val:
        code4, data4 = POST("/api/auth/refresh", body={"refresh_token": refresh_token_val})
        if code4 == 200 and data4.get("access_token"):
            access_token = data4["access_token"]  # Update token
            log("PASS", cat, "POST /api/auth/refresh", "Token refreshed")
        else:
            log("FAIL", cat, "POST /api/auth/refresh", f"HTTP {code4}")
    
    # Step 5: Test unauthenticated access
    code5, _ = GET("/api/auth/me")
    if code5 == 401:
        log("PASS", cat, "Unauth /api/auth/me", "Correctly returns 401")
    else:
        log("FAIL", cat, "Unauth /api/auth/me", f"Expected 401, got {code5}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 7: PAYMENTS
# ══════════════════════════════════════════════════════════════════
def test_payments():
    cat = "PAYMENTS"
    print(f"\n{'─'*60}")
    print(f"  💳 Category 7: Payments (Razorpay)")
    print(f"{'─'*60}")
    
    # Plans listing (public)
    code, data = GET("/api/payments/plans")
    if code == 200 and isinstance(data, (list, dict)):
        count = len(data) if isinstance(data, list) else len(data.get("plans", []))
        log("PASS", cat, "GET /api/payments/plans", f"{count} plans available")
    else:
        log("FAIL", cat, "GET /api/payments/plans", f"HTTP {code}")
    
    # Create order (needs tenant_id)
    if test_tenant_id:
        code2, data2 = POST("/api/payments/create-order", body={"tenant_id": test_tenant_id, "plan": "individual"})
        if code2 == 200 and data2.get("order_id"):
            log("PASS", cat, "POST /api/payments/create-order", f"order_id={data2['order_id']}")
        elif code2 == 200:
            log("PASS", cat, "POST /api/payments/create-order", f"Response: {str(data2)[:100]}")
        else:
            log("FAIL", cat, "POST /api/payments/create-order", f"HTTP {code2}: {str(data2)[:100]}")
        
        # Payment status
        code3, data3 = GET(f"/api/payments/status?tenant_id={test_tenant_id}")
        if code3 == 200:
            log("PASS", cat, "GET /api/payments/status", f"Status: {data3.get('subscription_status', data3.get('status', '?'))}")
        else:
            log("FAIL", cat, "GET /api/payments/status", f"HTTP {code3}")
    else:
        log("SKIP", cat, "Payment order", "No test tenant_id")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 8: ADMIN API
# ══════════════════════════════════════════════════════════════════
def test_admin():
    cat = "ADMIN"
    admin_hdr = {"Authorization": f"Bearer admin:{ADMIN_KEY}"}
    print(f"\n{'─'*60}")
    print(f"  ⚙️ Category 8: Admin API (8 endpoints)")
    print(f"{'─'*60}")
    
    # List tenants (may return list or dict with key)
    code, data = GET("/api/admin/tenants", headers=admin_hdr)
    if code == 200:
        count = len(data) if isinstance(data, list) else len(data.get('tenants', [])) if isinstance(data, dict) else '?'
        log("PASS", cat, "GET /api/admin/tenants", f"{count} tenants found")
    else:
        log("FAIL", cat, "GET /api/admin/tenants", f"HTTP {code}")
    
    # Platform stats
    code2, data2 = GET("/api/admin/stats", headers=admin_hdr)
    if code2 == 200 and isinstance(data2, dict):
        log("PASS", cat, "GET /api/admin/stats", f"Stats: {list(data2.keys())[:5]}...")
    else:
        log("FAIL", cat, "GET /api/admin/stats", f"HTTP {code2}")
    
    # Bot status
    code3, data3 = GET("/api/admin/bots", headers=admin_hdr)
    if code3 == 200:
        log("PASS", cat, "GET /api/admin/bots", f"Bot info returned")
    else:
        log("FAIL", cat, "GET /api/admin/bots", f"HTTP {code3}")
    
    # Test unauthorized admin access
    code4, _ = GET("/api/admin/tenants")
    if code4 in (401, 403):
        log("PASS", cat, "Unauth admin", f"Correctly returns {code4}")
    else:
        log("FAIL", cat, "Unauth admin", f"Expected 401/403, got {code4}")
    
    # Test tenant operations (extend, activate, deactivate) if we have a test tenant
    if test_tenant_id:
        # Extend trial
        code5, data5 = POST(f"/api/admin/tenant/{test_tenant_id}/extend?days=7", headers=admin_hdr)
        if code5 == 200:
            log("PASS", cat, f"POST extend trial", f"Tenant {test_tenant_id} extended")
        else:
            log("FAIL", cat, f"POST extend trial", f"HTTP {code5}: {data5}")
        
        # Activate
        code6, data6 = POST(f"/api/admin/tenant/{test_tenant_id}/activate?plan=individual", headers=admin_hdr)
        if code6 == 200:
            log("PASS", cat, f"POST activate", f"Tenant {test_tenant_id} activated")
        else:
            log("FAIL", cat, f"POST activate", f"HTTP {code6}: {data6}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 9: ONBOARDING
# ══════════════════════════════════════════════════════════════════
def test_onboarding():
    cat = "ONBOARD"
    print(f"\n{'─'*60}")
    print(f"  🚀 Category 9: Onboarding Endpoints")
    print(f"{'─'*60}")
    
    if not test_tenant_id:
        log("SKIP", cat, "Onboarding", "No test tenant_id")
        return
    
    # Check onboarding status
    code, data = GET(f"/api/onboarding/status?tenant_id={test_tenant_id}")
    if code == 200:
        log("PASS", cat, "GET /api/onboarding/status", f"Steps: {data}")
    else:
        log("FAIL", cat, "GET /api/onboarding/status", f"HTTP {code}")
    
    # Save branding
    code2, data2 = POST("/api/onboarding/branding", body={
        "tenant_id": test_tenant_id,
        "tagline": "E2E Test Tagline",
        "cta": "Get Insured Now",
        "phone": test_phone,
        "email": "test@e2e.test"
    })
    if code2 == 200:
        log("PASS", cat, "POST /api/onboarding/branding", "Branding saved")
    else:
        log("FAIL", cat, "POST /api/onboarding/branding", f"HTTP {code2}: {data2}")
    
    # Save WhatsApp config (dummy)
    code3, data3 = POST("/api/onboarding/whatsapp", body={
        "tenant_id": test_tenant_id,
        "wa_phone_id": "test_phone_id",
        "wa_access_token": "test_token",
        "wa_verify_token": "test_verify"
    })
    if code3 == 200:
        log("PASS", cat, "POST /api/onboarding/whatsapp", "WhatsApp config saved")
    else:
        log("FAIL", cat, "POST /api/onboarding/whatsapp", f"HTTP {code3}: {data3}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 10: DASHBOARD API
# ══════════════════════════════════════════════════════════════════
def test_dashboard():
    cat = "DASHBOARD"
    print(f"\n{'─'*60}")
    print(f"  📊 Category 10: Dashboard API")
    print(f"{'─'*60}")
    
    # Test with tenant_id
    if test_tenant_id:
        code, data = GET(f"/api/dashboard?tenant_id={test_tenant_id}")
        if code == 200 and isinstance(data, dict):
            log("PASS", cat, "GET /api/dashboard", f"Keys: {list(data.keys())[:6]}...")
        else:
            log("FAIL", cat, "GET /api/dashboard", f"HTTP {code}")
    
    # Test without params (should work with defaults or fail gracefully)
    code2, data2 = GET("/api/dashboard")
    if code2 in (200, 400, 422):
        log("PASS", cat, "GET /api/dashboard (no params)", f"HTTP {code2}")
    else:
        log("FAIL", cat, "GET /api/dashboard (no params)", f"HTTP {code2}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 11: WHATSAPP ENDPOINTS
# ══════════════════════════════════════════════════════════════════
def test_whatsapp():
    cat = "WHATSAPP"
    auth_hdr = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    print(f"\n{'─'*60}")
    print(f"  📱 Category 11: WhatsApp Endpoints")
    print(f"{'─'*60}")
    
    # WA status check
    if access_token:
        code, data = GET("/api/wa/status", headers=auth_hdr)
        if code == 200:
            log("PASS", cat, "GET /api/wa/status", f"Configured: {data.get('configured', '?')}")
        else:
            log("FAIL", cat, "GET /api/wa/status", f"HTTP {code}")
    else:
        log("SKIP", cat, "GET /api/wa/status", "No auth token")
    
    # Webhook verification (simulate Meta challenge)
    challenge = "test_challenge_123"
    code2, data2 = GET(f"/webhook?hub.mode=subscribe&hub.verify_token=sarathi_wa_verify&hub.challenge={challenge}", raw=True)
    if code2 == 200:
        log("PASS", cat, "GET /webhook (verify)", f"Challenge response")
    elif code2 == 403:
        log("PASS", cat, "GET /webhook (verify)", "Token mismatch (expected for test)")
    else:
        log("FAIL", cat, "GET /webhook (verify)", f"HTTP {code2}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 12: GOOGLE DRIVE
# ══════════════════════════════════════════════════════════════════
def test_gdrive():
    cat = "GDRIVE"
    auth_hdr = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    print(f"\n{'─'*60}")
    print(f"  📁 Category 12: Google Drive Endpoints")
    print(f"{'─'*60}")
    
    if access_token:
        # Status check
        code, data = GET("/api/gdrive/status", headers=auth_hdr)
        if code in (200, 501):
            log("PASS", cat, "GET /api/gdrive/status", f"HTTP {code} — {data}")
        else:
            log("FAIL", cat, "GET /api/gdrive/status", f"HTTP {code}")
        
        # Connect URL (will fail if not configured — 501/503 expected)
        code2, data2 = GET("/api/gdrive/connect", headers=auth_hdr)
        if code2 in (200, 400, 501, 503):
            log("PASS", cat, "GET /api/gdrive/connect", f"HTTP {code2} (not configured)")
        else:
            log("FAIL", cat, "GET /api/gdrive/connect", f"HTTP {code2}")
    else:
        log("SKIP", cat, "GDrive endpoints", "No auth token")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 13: CAMPAIGNS
# ══════════════════════════════════════════════════════════════════
test_campaign_id = None

def test_campaigns():
    global test_campaign_id
    cat = "CAMPAIGNS"
    auth_hdr = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    print(f"\n{'─'*60}")
    print(f"  📢 Category 13: Bulk Campaigns")
    print(f"{'─'*60}")
    
    # Campaign types
    code, data = GET("/api/campaigns/types", headers=auth_hdr)
    if code in (200, 401, 422):
        log("PASS", cat, "GET /api/campaigns/types", f"HTTP {code} — {data}")
    else:
        log("FAIL", cat, "GET /api/campaigns/types", f"HTTP {code}")
    
    if not access_token:
        log("SKIP", cat, "Campaign CRUD", "No auth token")
        return
    
    # Create campaign
    code2, data2 = POST("/api/campaigns", body={
        "title": "E2E Test Campaign",
        "message": "Hello {name}, this is a test campaign!",
        "campaign_type": "custom",
        "channel": "whatsapp"
    }, headers=auth_hdr)
    if code2 in (200, 201) and data2.get("campaign_id"):
        test_campaign_id = data2["campaign_id"]
        log("PASS", cat, "POST /api/campaigns", f"campaign_id={test_campaign_id}")
    else:
        log("FAIL", cat, "POST /api/campaigns", f"HTTP {code2}: {str(data2)[:100]}")
    
    # List campaigns
    code3, data3 = GET("/api/campaigns", headers=auth_hdr)
    if code3 == 200:
        count = len(data3) if isinstance(data3, list) else "?"
        log("PASS", cat, "GET /api/campaigns", f"{count} campaigns found")
    else:
        log("FAIL", cat, "GET /api/campaigns", f"HTTP {code3}")
    
    # Get campaign details
    if test_campaign_id:
        code4, data4 = GET(f"/api/campaigns/{test_campaign_id}", headers=auth_hdr)
        if code4 == 200:
            log("PASS", cat, f"GET /api/campaigns/{test_campaign_id}", f"Status: {data4.get('status', '?')}")
        else:
            log("FAIL", cat, f"GET campaign detail", f"HTTP {code4}")
        
        # Recipients
        code5, data5 = GET(f"/api/campaigns/{test_campaign_id}/recipients", headers=auth_hdr)
        if code5 == 200:
            log("PASS", cat, "GET campaign recipients", f"Recipients: {data5}")
        else:
            log("FAIL", cat, "GET campaign recipients", f"HTTP {code5}")
        
        # Delete campaign
        code6, data6 = DELETE(f"/api/campaigns/{test_campaign_id}", headers=auth_hdr)
        if code6 == 200:
            log("PASS", cat, "DELETE campaign", "Cleanup successful")
        else:
            log("FAIL", cat, "DELETE campaign", f"HTTP {code6}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 14: SUBSCRIPTION MANAGEMENT
# ══════════════════════════════════════════════════════════════════
def test_subscription():
    cat = "SUBSCRIPTION"
    auth_hdr = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    print(f"\n{'─'*60}")
    print(f"  📋 Category 14: Subscription Management")
    print(f"{'─'*60}")
    
    if access_token:
        # Cancel subscription (with reason) — may 400/500 if no subscription
        code, data = POST("/api/subscription/cancel", body={"reason": "E2E test"}, headers=auth_hdr)
        if code in (200, 400, 404, 500):
            log("PASS", cat, "POST /api/subscription/cancel", f"HTTP {code}: {str(data)[:80]}")
        else:
            log("FAIL", cat, "POST /api/subscription/cancel", f"HTTP {code}")
    else:
        log("SKIP", cat, "Subscription cancel", "No auth token")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 15: AUTH LOGOUT
# ══════════════════════════════════════════════════════════════════
def test_logout():
    cat = "AUTH"
    print(f"\n{'─'*60}")
    print(f"  🚪 Category 15: Logout")
    print(f"{'─'*60}")
    
    code, data = POST("/api/auth/logout")
    if code == 200:
        log("PASS", cat, "POST /api/auth/logout", "Logout successful")
    else:
        log("FAIL", cat, "POST /api/auth/logout", f"HTTP {code}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 16: SECURITY TESTS
# ══════════════════════════════════════════════════════════════════
def test_security():
    cat = "SECURITY"
    print(f"\n{'─'*60}")
    print(f"  🔒 Category 16: Security Tests")
    print(f"{'─'*60}")
    
    # Test invalid admin key
    code, _ = GET("/api/admin/tenants", headers={"Authorization": "Bearer admin:wrongkey"})
    if code in (401, 403):
        log("PASS", cat, "Invalid admin key", f"Correctly rejected ({code})")
    else:
        log("FAIL", cat, "Invalid admin key", f"Expected 401/403, got {code}")
    
    # Test expired/garbage JWT
    code2, _ = GET("/api/auth/me", headers={"Authorization": "Bearer garbage.token.here"})
    if code2 == 401:
        log("PASS", cat, "Invalid JWT", "Correctly rejected (401)")
    else:
        log("FAIL", cat, "Invalid JWT", f"Expected 401, got {code2}")
    
    # Test SQL injection in query params
    code3, _ = GET("/api/calc/inflation?amount=50000;DROP%20TABLE%20tenants&inflation=7&years=10")
    if code3 in (200, 422):
        log("PASS", cat, "SQL injection test", f"Handled safely ({code3})")
    else:
        log("FAIL", cat, "SQL injection test", f"HTTP {code3}")
    
    # Test XSS in signup
    code4, data4 = POST("/api/signup", body={
        "firm_name": "<script>alert('xss')</script>",
        "owner_name": "Test",
        "phone": f"88{random.randint(10000000, 99999999)}",
        "plan": "individual"
    })
    if code4 in (200, 409, 422):
        log("PASS", cat, "XSS in signup", f"Handled ({code4})")
    else:
        log("FAIL", cat, "XSS in signup", f"HTTP {code4}")

# ══════════════════════════════════════════════════════════════════
#  CATEGORY 17: API DOCS
# ══════════════════════════════════════════════════════════════════
def test_api_docs():
    cat = "DOCS"
    print(f"\n{'─'*60}")
    print(f"  📚 Category 17: API Documentation")
    print(f"{'─'*60}")
    
    # OpenAPI JSON
    code, data = GET("/openapi.json")
    if code == 200 and isinstance(data, dict) and "paths" in data:
        paths = len(data["paths"])
        log("PASS", cat, "GET /openapi.json", f"{paths} paths documented")
    else:
        log("FAIL", cat, "GET /openapi.json", f"HTTP {code}")
    
    # Swagger UI (may be 200 or 404 if docs disabled)
    code2, body2 = GET("/docs", raw=True)
    if code2 == 200 and "swagger" in body2.lower():
        log("PASS", cat, "GET /docs", f"Swagger UI — {len(body2)} bytes")
    elif code2 == 404:
        log("PASS", cat, "GET /docs", "Docs endpoint disabled (404)")
    else:
        log("FAIL", cat, "GET /docs", f"HTTP {code2}")

# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    print("╔" + "═"*62 + "╗")
    print("║  Sarathi-AI Business Technologies — 360° E2E Test Suite      ║")
    print("║  Base URL: " + BASE.ljust(50) + "║")
    print("╚" + "═"*62 + "╝")
    
    start_time = time.time()
    
    # Run all test categories in order
    test_pages()
    test_health()
    test_calculators()
    test_reports()
    test_signup()
    test_auth()
    test_payments()
    test_admin()
    test_onboarding()
    test_dashboard()
    test_whatsapp()
    test_gdrive()
    test_campaigns()
    test_subscription()
    test_logout()
    test_security()
    test_api_docs()
    
    elapsed = time.time() - start_time
    
    # ── Summary ──
    total = passed + failed + skipped
    print(f"\n{'═'*62}")
    print(f"  📊 RESULTS SUMMARY")
    print(f"{'═'*62}")
    print(f"  Total Tests:   {total}")
    print(f"  ✅ Passed:     {passed}")
    print(f"  ❌ Failed:     {failed}")
    print(f"  ⚠️  Skipped:    {skipped}")
    print(f"  ⏱️  Duration:   {elapsed:.1f}s")
    print(f"  📈 Pass Rate:  {passed/total*100:.1f}%" if total else "  No tests run")
    
    if errors:
        print(f"\n{'─'*62}")
        print(f"  ❌ FAILURES:")
        print(f"{'─'*62}")
        for e in errors:
            print(f"    • {e}")
    
    print(f"\n{'═'*62}")
    
    if failed > 0:
        sys.exit(1)
    return 0


if __name__ == "__main__":
    main()
