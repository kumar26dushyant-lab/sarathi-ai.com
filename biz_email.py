"""
Sarathi-AI Business — Email System
====================================
Transactional email via SMTP (Gmail App Password / any SMTP provider).

Templates:
  - Welcome / signup confirmation
  - OTP login code
  - Trial expiry reminder (3 days, 1 day, expired)
  - Payment receipt
  - Subscription cancelled
  - Password/account recovery
"""

import os
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger("sarathi.email")

# ── Configuration ────────────────────────────────────────────────────────────
SMTP_HOST = ""
SMTP_PORT = 587
SMTP_USER = ""
SMTP_PASSWORD = ""
FROM_NAME = "Sarathi-AI Business Technologies"
FROM_EMAIL = ""
FROM_NOREPLY = ""  # info@sarathi-ai.com — transactional/notifications
FROM_SUPPORT = ""  # support@sarathi-ai.com — support ticket communications
NIDAAN_FROM = ""   # noreply@nidaanpartner.com — Nidaan-branded (own-domain, DKIM-aligned)
# Separate Nidaan sending account (Workspace info@nidaanpartner.com) so Nidaan mail authenticates
# AS its own domain (SPF/DKIM aligned, inbox). Used ONLY for @nidaanpartner.com senders — Sarathi
# mail never touches this account. Additive: if unset, Nidaan mail uses the existing shared path.
NIDAAN_SMTP_HOST = ""
NIDAAN_SMTP_PORT = 465
NIDAAN_SMTP_USER = ""
NIDAAN_SMTP_PASSWORD = ""
_initialized = False

def _base_url() -> str:
    """Get the server base URL from environment."""
    return os.getenv("SERVER_URL", "https://sarathi-ai.com").rstrip("/")


def init_email():
    """Initialize email configuration from environment."""
    global SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, FROM_NOREPLY, FROM_SUPPORT, NIDAAN_FROM, _initialized
    global NIDAAN_SMTP_HOST, NIDAAN_SMTP_PORT, NIDAAN_SMTP_USER, NIDAAN_SMTP_PASSWORD

    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)
    FROM_NOREPLY = os.getenv("SMTP_FROM_NOREPLY", FROM_EMAIL)  # info@sarathi-ai.com
    FROM_SUPPORT = os.getenv("SMTP_FROM_SUPPORT", FROM_EMAIL)  # support@sarathi-ai.com
    # Nidaan emails should send from a domain we CONTROL (nidaanpartner.com) so
    # SPF/DKIM/DMARC align — sending "as" a gmail.com address lands in spam. Only
    # takes effect once that domain is authenticated in Brevo (else Brevo rejects
    # the unverified sender). Falls back to the generic noreply until configured.
    NIDAAN_FROM = os.getenv("NIDAAN_FROM_EMAIL", FROM_NOREPLY)
    # Dedicated Nidaan sending account (optional). When set, @nidaanpartner.com mail authenticates here.
    NIDAAN_SMTP_HOST = os.getenv("NIDAAN_SMTP_HOST", SMTP_HOST)
    NIDAAN_SMTP_PORT = int(os.getenv("NIDAAN_SMTP_PORT", "465"))
    NIDAAN_SMTP_USER = os.getenv("NIDAAN_SMTP_USER", "")
    NIDAAN_SMTP_PASSWORD = os.getenv("NIDAAN_SMTP_PASSWORD", "")
    if NIDAAN_SMTP_USER and NIDAAN_SMTP_PASSWORD:
        logger.info("✅ Nidaan email account ready (%s via %s:%d)",
                    NIDAAN_SMTP_USER, NIDAAN_SMTP_HOST, NIDAAN_SMTP_PORT)

    if SMTP_USER and SMTP_PASSWORD:
        _initialized = True
        logger.info("✅ Email system ready (noreply=%s, support=%s via %s:%d)",
                    FROM_NOREPLY, FROM_SUPPORT, SMTP_HOST, SMTP_PORT)
    else:
        _initialized = False
        logger.warning("⚠️  Email not configured — set SMTP_USER & SMTP_PASSWORD in biz.env")


def is_enabled() -> bool:
    return _initialized


# ── Send Email ───────────────────────────────────────────────────────────────

async def send_email(to_email: str, subject: str, html_body: str,
                     text_body: str = "", from_email: str = "",
                     from_name: str = "", reply_to: str = "",
                     delivery_critical: bool = False) -> bool:
    """Send transactional email. Prefers Resend HTTPS API when RESEND_API_KEY is
    set (proper DKIM-aligned deliverability), otherwise falls back to Gmail SMTP.
    Returns True on success.
    from_email: override sender address (defaults to FROM_NOREPLY).
    from_name: override sender display name.
    reply_to: override Reply-To header (defaults to noreply)."""
    if not _initialized:
        logger.warning("Email not sent (not configured): %s → %s", subject, to_email)
        return False

    sender_name = from_name or FROM_NAME
    # Nidaan-branded emails (OTP, claims, billing) send from the Nidaan own-domain
    # address when configured, so SPF/DKIM/DMARC align and they don't hit spam.
    _default_from = (NIDAAN_FROM if (NIDAAN_FROM and sender_name.startswith("Nidaan")) else FROM_NOREPLY)
    sender_email = from_email or _default_from

    # Allow comma/semicolon-separated recipients (e.g. NIDAAN_ADMIN_EMAIL with
    # multiple ops addresses). First address is the canonical "To".
    _recips = [e.strip() for e in (to_email or "").replace(";", ",").split(",") if e.strip()]
    to_email = _recips[0] if _recips else to_email

    # Prepare a text body for deliverability if not given (used by both paths)
    import re as _re
    plain = text_body
    if not plain:
        plain = _re.sub(r'<[^>]+>', '', html_body or "")
        plain = _re.sub(r'\s+', ' ', plain).strip()

    # Reply-To and unsubscribe default to THIS email's own sender address — never a
    # global fallback — so Nidaan mail replies to the Nidaan address and Sarathi mail to
    # the Sarathi address (a global FROM_NOREPLY/FROM_SUPPORT would leak one product's
    # address onto the other's mail).
    reply_addr = reply_to or sender_email
    unsubscribe_header = f"<mailto:{sender_email}?subject=Unsubscribe>"

    async def _smtp_send(acct_user: str = "", acct_pass: str = "",
                         acct_host: str = "", acct_port: int = 0) -> bool:
        """Send via SMTP using the given account (defaults to the shared SMTP_* account).
        Returns True on success; never raises."""
        _user = acct_user or SMTP_USER
        _pass = acct_pass or SMTP_PASSWORD
        _host = acct_host or SMTP_HOST
        _port = int(acct_port or SMTP_PORT)
        try:
            import aiosmtplib
            import uuid
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = ", ".join(_recips) if _recips else to_email
            msg["Subject"] = subject
            msg["Reply-To"] = reply_to or sender_email
            # Sender header: who actually sent (on behalf of From), for RFC-compliant clients.
            if _user and _user != sender_email:
                msg["Sender"] = f"{sender_name} <{_user}>"
            msg["MIME-Version"] = "1.0"
            msg["Message-ID"] = f"<{uuid.uuid4()}@sarathi-ai.com>"
            msg["List-Unsubscribe"] = f"<mailto:{FROM_SUPPORT or sender_email}?subject=Unsubscribe>"
            msg["X-Mailer"] = "Sarathi-AI CRM"
            msg.attach(MIMEText(plain, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            # Port 465 = implicit TLS; 587/others = STARTTLS. Many cloud hosts block 587
            # outbound, so 465 is the reliable path.
            _implicit_tls = (_port == 465)
            await aiosmtplib.send(
                msg, hostname=_host, port=_port,
                username=_user, password=_pass,
                use_tls=_implicit_tls, start_tls=(not _implicit_tls), timeout=30)
            logger.info("📧 SMTP ✓ '%s' → %s (from %s via %s)", subject, to_email, sender_email, _user)
            return True
        except Exception as e:
            logger.error("📧 SMTP failed: '%s' → %s: %s", subject, to_email, e)
            return False

    # Nidaan mail → send via the dedicated Nidaan Workspace account (info@nidaanpartner.com) when
    # configured, so From = authenticated user = the Nidaan domain (SPF/DKIM aligned → inbox).
    # STRICTLY ADDITIVE: only @nidaanpartner.com senders enter here, and only when the Nidaan creds
    # are set — Sarathi mail never touches this branch, so its path is unchanged. On failure it falls
    # through to the existing transports as backup.
    _is_nidaan_sender = (sender_email or "").lower().endswith("@nidaanpartner.com")
    # The Nidaan Workspace SMTP creds (info@nidaanpartner.com) are currently rejected by
    # Gmail (535 BadCredentials), which spammed the error log while Brevo silently delivered.
    # Brevo is DKIM-authenticated for nidaanpartner.com → inbox, so we default to Brevo-first
    # and only use this SMTP path when explicitly re-enabled (NIDAAN_SMTP_ENABLED=1) after the
    # Gmail app password is regenerated.
    _nidaan_smtp_on = os.getenv("NIDAAN_SMTP_ENABLED", "0") == "1"
    if _is_nidaan_sender and _nidaan_smtp_on and NIDAAN_SMTP_USER and NIDAAN_SMTP_PASSWORD:
        if await _smtp_send(NIDAAN_SMTP_USER, NIDAAN_SMTP_PASSWORD, NIDAAN_SMTP_HOST, NIDAAN_SMTP_PORT):
            return True

    # When the sender IS the authenticated Gmail SMTP account (Nidaan's
    # nidaanpartner@gmail.com), send DIRECTLY via Gmail FIRST: SPF/DKIM align so it lands
    # in the inbox (not spam) and there is no 300/day cap. The API transports below stay
    # as automatic fallback. Other senders (e.g. Sarathi) keep API-first, since this Gmail
    # account is not their authorized sender and SMTP would misalign their domain.
    _smtp_ready = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)
    _smtp_aligned = _smtp_ready and (sender_email or "").lower() == (SMTP_USER or "").lower()

    # DELIVERY-CRITICAL MAIL (login/verification codes) — arrival beats branding.
    # nidaanpartner.com publishes SPF "v=spf1 include:_spf.google.com ~all": it authorises GOOGLE
    # only. Anything sent through Brevo while claiming From: info@nidaanpartner.com therefore
    # fails SPF and Gmail files it as spam — which is exactly why signup codes were "never
    # received" even though every send logged Brevo ✓. Until Brevo is added to SPF/DKIM (see
    # NOTE below), send these through the authenticated Google account so the envelope aligns,
    # and put the branded address in Reply-To so replies still reach the team.
    #
    # NOTE FOR THE OWNER: once DNS has
    #     v=spf1 include:_spf.google.com include:spf.brevo.com ~all   (+ Brevo DKIM records)
    # this override stops being necessary and branded From works on every transport.
    if delivery_critical and _smtp_ready and not _smtp_aligned:
        _orig_sender = sender_email
        sender_email = SMTP_USER
        reply_addr = reply_addr or _orig_sender
        _smtp_aligned = True
        logger.info("📧 delivery-critical: sending as %s (SPF-aligned), reply-to %s",
                    sender_email, reply_addr)
    if _smtp_aligned and await _smtp_send():
        return True

    # ─── Path 1: Brevo (free 300/day, proper DKIM) — fallback for aligned senders ─
    brevo_key = os.getenv("BREVO_API_KEY", "").strip()
    if brevo_key:
        try:
            import httpx
            payload = {
                "sender": {"name": sender_name, "email": sender_email},
                "to": [{"email": e} for e in _recips] or [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_body,
                "textContent": plain,
                "replyTo": {"email": reply_addr} if reply_addr else None,
                "headers": {
                    "List-Unsubscribe": unsubscribe_header,
                    "X-Mailer": "Sarathi-AI CRM",
                },
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={"api-key": brevo_key,
                             "accept": "application/json",
                             "content-type": "application/json"},
                    json=payload,
                )
            if r.status_code in (200, 201, 202):
                logger.info("📧 Brevo ✓ '%s' → %s (from %s)", subject, to_email, sender_email)
                return True
            logger.error("📧 Brevo rejected (%d): %s", r.status_code, r.text[:200])
            # Fall through to SMTP on any transient failure
        except Exception as e:
            logger.error("📧 Brevo transport failed: %s — falling back to SMTP", e)

    # ─── Path 2: Resend HTTPS API (if customer prefers it) ──────────────
    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    if resend_key:
        try:
            import httpx
            from_header = f"{sender_name} <{sender_email}>"
            payload = {
                "from": from_header,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
                "text": plain,
                "reply_to": [reply_addr] if reply_addr else None,
                "headers": {
                    "List-Unsubscribe": unsubscribe_header,
                    "X-Mailer": "Sarathi-AI CRM",
                },
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {resend_key}",
                             "Content-Type": "application/json"},
                    json=payload,
                )
            if r.status_code in (200, 202):
                logger.info("📧 Resend ✓ '%s' → %s (from %s)", subject, to_email, sender_email)
                return True
            logger.error("📧 Resend rejected (%d): %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.error("📧 Resend transport failed: %s — falling back to SMTP", e)

    # ─── Gmail SMTP: fallback for non-aligned senders, or if the APIs had no key ──
    if _smtp_ready and not _smtp_aligned:
        if await _smtp_send():
            return True

    logger.error("📧 Email failed on all transports: '%s' → %s", subject, to_email)
    return False


async def send_support_email(to_email: str, subject: str, html_body: str,
                             text_body: str = "") -> bool:
    """Send email from support@sarathi-ai.com — for support ticket communications.
    Reply-To is set to support@ so customers can reply."""
    return await send_email(to_email, subject, html_body, text_body,
                            from_email=FROM_SUPPORT,
                            from_name="Sarathi-AI Support",
                            reply_to=FROM_SUPPORT)


# ── Base Template ────────────────────────────────────────────────────────────

def _wrap_template(title: str, content: str) -> str:
    """Wrap email content in a branded HTML template."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>
body{{margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif}}
.container{{max-width:600px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)}}
.header{{background:linear-gradient(135deg,#1a56db,#3b82f6);padding:32px 24px;text-align:center}}
.header h1{{color:#fff;margin:0;font-size:24px;letter-spacing:-0.5px}}
.header p{{color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px}}
.body{{padding:32px 24px}}
.body h2{{color:#1e293b;font-size:20px;margin:0 0 16px}}
.body p{{color:#475569;font-size:15px;line-height:1.7;margin:0 0 16px}}
.highlight{{background:#f8fafc;border-left:4px solid #1a56db;padding:16px 20px;border-radius:0 8px 8px 0;margin:20px 0}}
.highlight strong{{color:#1a56db}}
.btn{{display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#1a56db,#3b82f6);color:#fff!important;
  text-decoration:none;border-radius:10px;font-weight:600;font-size:15px;margin:8px 0}}
.btn-orange{{background:linear-gradient(135deg,#ea580c,#f97316)}}
.otp-code{{font-size:32px;font-weight:800;letter-spacing:8px;color:#1a56db;text-align:center;
  padding:20px;background:#f0f4ff;border-radius:12px;margin:20px 0}}
.footer{{background:#f8fafc;padding:20px 24px;text-align:center;border-top:1px solid #e2e8f0}}
.footer p{{color:#94a3b8;font-size:12px;margin:4px 0}}
</style></head>
<body><div class="container">
<div class="header">
  <img src="{_base_url()}/static/logo.png" alt="Sarathi-AI" style="max-width:180px;height:auto;margin-bottom:8px" />
  <p style="color:rgba(255,255,255,0.85);margin:4px 0 0;font-size:13px">AI-Powered Financial Advisor CRM</p>
</div>
<div class="body">
{content}
</div>
<div class="footer">
  <p>Sarathi-AI Business Technologies</p>
  <p style="font-size:11px;color:#94a3b8">Developed by GoLuQ.com Digital Consultant</p>
  <p><a href="mailto:support@sarathi-ai.com" style="color:#64748b">support@sarathi-ai.com</a> &bull; <a href="https://sarathi-ai.com" style="color:#64748b">sarathi-ai.com</a></p>
  <p style="margin-top:8px;font-size:11px;color:#94a3b8">This is an automated notification from Sarathi-AI. Please do not reply to this email.<br>If you need help, contact us at support@sarathi-ai.com</p>
</div>
</div></body></html>"""


def _wrap_nidaan_template(title: str, content: str) -> str:
    """Wrap email content in Nidaan Partner branded HTML template."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>
body{{margin:0;padding:0;background:#060f1e;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif}}
.container{{max-width:600px;margin:0 auto;background:#0c1a2e;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.4)}}
.header{{background:linear-gradient(135deg,#0e7490,#06b6d4);padding:28px 24px;text-align:center}}
.header-title{{color:#fff;margin:0;font-size:22px;font-weight:800;letter-spacing:-0.5px}}
.header-sub{{color:rgba(255,255,255,0.8);margin:6px 0 0;font-size:13px}}
.body{{padding:32px 24px}}
.body h2{{color:#22d3ee;font-size:20px;margin:0 0 16px}}
.body p{{color:#94a3b8;font-size:15px;line-height:1.7;margin:0 0 16px}}
.body strong{{color:#e2e8f0}}
.footer{{background:#060f1e;padding:20px 24px;text-align:center;border-top:1px solid rgba(255,255,255,0.07)}}
.footer p{{color:#475569;font-size:12px;margin:4px 0}}
.footer a{{color:#475569}}
</style></head>
<body><div class="container">
<div class="header">
  <div class="header-title">🛡️ Nidaan Partner</div>
  <div class="header-sub">Insurance Claim Dispute Management</div>
</div>
<div class="body">
{content}
</div>
<div class="footer">
  <p>NidaanPartner.com — Developed by GoLuQ.com Digital Consultant</p>
  <p><a href="mailto:support@nidaanpartner.com">support@nidaanpartner.com</a> &bull; <a href="https://nidaanpartner.com">nidaanpartner.com</a></p>
  <p style="margin-top:8px;font-size:11px;color:#334155">This is an automated notification. Do not reply to this email.</p>
</div>
</div></body></html>"""


# ── Email Templates ──────────────────────────────────────────────────────────

async def send_welcome(to_email: str, owner_name: str, firm_name: str, tenant_id: int) -> bool:
    """Send welcome email after signup."""
    content = f"""
<h2>Welcome to Sarathi-AI, {owner_name}! 🎉</h2>
<p>Your firm <strong>{firm_name}</strong> has been registered successfully.
   Your <strong>14-day free trial</strong> starts now — no credit card required.</p>
<div class="highlight">
  <p><strong>Your Account ID:</strong> {tenant_id}</p>
  <p><strong>Firm:</strong> {firm_name}</p>
  <p><strong>Plan:</strong> Free Trial (14 days)</p>
</div>
<p>Here's what you can do next:</p>
<p>1️⃣ Complete onboarding — connect your Telegram bot<br>
   2️⃣ Try our insurance calculators<br>
   3️⃣ Add your first client leads via Telegram</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/onboarding?tenant_id={tenant_id}" class="btn">Complete Onboarding →</a>
</p>
<p style="color:#94a3b8;font-size:13px;margin-top:24px">
  Need help? Reply to this email or visit our <a href="{_base_url()}/help">Help Guide</a>.
</p>"""
    return await send_email(to_email, f"Welcome to Sarathi-AI, {owner_name}!", _wrap_template("Welcome", content))


async def send_founding_welcome(to_email: str, owner_name: str, firm_name: str,
                                 tenant_id: int, founding_number: int = 0) -> bool:
    """Send enthusiastic welcome email for founding customers with 20% discount."""
    number_line = f"<p style='font-size:20px;font-weight:700;color:#f59e0b;margin:0'>Founding Customer #{founding_number}</p>" if founding_number else ""
    content = f"""
<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);padding:24px;border-radius:16px;color:#fff;text-align:center;margin-bottom:24px">
  <p style="font-size:28px;margin:0">🏆</p>
  <h2 style="color:#fbbf24;margin:8px 0 4px">Welcome, Founding Customer!</h2>
  {number_line}
</div>
<p>Hi {owner_name},</p>
<p>Congratulations! 🎉 You've joined <strong>Sarathi-AI</strong> as one of our exclusive <strong>Founding 500</strong> customers. This is a big deal — you're among the first to shape the future of insurance CRM in India.</p>
<div style="background:linear-gradient(135deg,#fef3c7,#fde68a);padding:16px 20px;border-radius:12px;margin:16px 0;border-left:4px solid #f59e0b">
  <p style="margin:0 0 8px;font-weight:700;color:#92400e">🎁 Your Founding Benefits:</p>
  <p style="margin:0 0 4px;color:#78350f">✅ <strong>20% discount</strong> on your first year of subscription</p>
  <p style="margin:0 0 4px;color:#78350f">✅ Priority support & feature requests</p>
  <p style="margin:0;color:#78350f">✅ Early access to new features</p>
</div>
<div class="highlight">
  <p><strong>Your Account ID:</strong> {tenant_id}</p>
  <p><strong>Firm:</strong> {firm_name}</p>
  <p><strong>Plan:</strong> Free Trial (14 days) + Founding Discount Locked 🔒</p>
</div>
<p>Here's what you can do next:</p>
<p>1️⃣ Complete onboarding — connect your Telegram bot<br>
   2️⃣ Try our insurance calculators<br>
   3️⃣ Add your first client leads via Telegram<br>
   4️⃣ Share your referral link & earn ₹40 per referral!</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/onboarding?tenant_id={tenant_id}" class="btn">Complete Onboarding →</a>
</p>
<p style="color:#94a3b8;font-size:13px;margin-top:24px">
  Need help? Reply to this email or visit our <a href="{_base_url()}/help">Help Guide</a>.
</p>"""
    return await send_email(to_email,
                            f"🏆 Welcome Founding Customer #{founding_number}! — Sarathi-AI",
                            _wrap_template("Founding Welcome", content))


async def send_otp_email(to_email: str, otp: str, owner_name: str = "") -> bool:
    """Send OTP login code via email."""
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    content = f"""
<h2>Your Login Code</h2>
<p>{greeting}</p>
<p>Use this one-time code to log in to your Sarathi-AI account:</p>
<div class="otp-code">{otp}</div>
<p>This code expires in <strong>10 minutes</strong>. Do not share it with anyone.</p>
<p style="color:#94a3b8;font-size:13px;margin-top:24px">
  If you didn't request this code, please ignore this email.
  Your account is safe.
</p>"""
    return await send_email(to_email, f"Sarathi-AI Login Code: {otp}", _wrap_template("Login Code", content))


async def send_nidaan_otp_email(to_email: str, otp: str, owner_name: str = "") -> bool:
    """Send OTP login code branded as Nidaan Partner."""
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    content = f"""
<h2>Your Nidaan Partner Login Code</h2>
<p>{greeting}</p>
<p>Use this one-time code to sign in to your <strong>Nidaan Partner</strong> account:</p>
<div style="background:#0e4863;color:#7dd3fc;letter-spacing:.35em;font-size:2.2rem;
  text-align:center;padding:1.4rem 1rem;border-radius:12px;font-weight:800;margin:1.5rem 0;
  font-family:monospace">{otp}</div>
<p>This code expires in <strong>10 minutes</strong>. Never share it with anyone.</p>
<p style="color:#64748b;font-size:13px;margin-top:24px">
  If you did not request this code, ignore this email — your account is safe.
</p>"""
    return await send_email(
        to_email,
        f"Nidaan Partner Login Code: {otp}",
        _wrap_nidaan_template("Nidaan Partner OTP", content),
        from_name="Nidaan Partner",
        from_email=NIDAAN_FROM or None,
        # A code that lands in spam is the same as no code at all — send this one on the
        # transport the domain actually authorises.
        delivery_critical=True,
    )


async def send_nidaan_branch_login_email(to_email: str, magic_url: str, otp: str = "",
                                         name: str = "", welcome: bool = False) -> bool:
    """Branch-portal login email: a big one-click login button (magic link) PLUS the OTP code
    as a fallback. `welcome=True` for the email sent when a branch login is first created.
    Sent as Nidaan Partner (info@nidaanpartner.com). Mobile-first single-column layout."""
    greeting = f"Hi {name}," if name else "Hi,"
    if welcome:
        title = "Your Nidaan Partner branch login is ready"
        intro = ("<p>Your branch portal has been set up. Tap the button below to log in "
                 "instantly — no password needed.</p>")
    else:
        title = "Log in to your Nidaan Partner branch portal"
        intro = ("<p>Tap the button below to log in to your branch portal instantly — "
                 "no password needed.</p>")
    button = f"""
<div style="text-align:center;margin:1.6rem 0">
  <a href="{magic_url}" style="display:inline-block;background:#0d9488;color:#ffffff;
    text-decoration:none;font-weight:700;font-size:1.05rem;padding:15px 36px;border-radius:12px">
    🔓 Log in to Branch Portal</a>
</div>
<p style="color:#64748b;font-size:13px;text-align:center;margin-top:-6px">
  This one-click link is valid for a short time and only for your branch.</p>"""
    otp_block = ""
    if otp:
        otp_block = f"""
<p style="margin-top:24px">Prefer to type it? Enter this one-time code on the login page:</p>
<div style="background:#0e4863;color:#7dd3fc;letter-spacing:.35em;font-size:2rem;
  text-align:center;padding:1.2rem 1rem;border-radius:12px;font-weight:800;margin:1rem 0;
  font-family:monospace">{otp}</div>
<p style="color:#64748b;font-size:13px">This code expires in <strong>10 minutes</strong>. Never share it.</p>"""
    content = f"""
<h2>{title}</h2>
<p>{greeting}</p>
{intro}
{button}
{otp_block}
<p style="color:#64748b;font-size:13px;margin-top:24px">
  You can always log in later at <strong>nidaanpartner.com/nidaan/branch</strong> using this email address.
  If you did not expect this email, you can safely ignore it.</p>"""
    subject = title if welcome else (f"Nidaan Partner Branch Login Code: {otp}" if otp else title)
    return await send_email(
        to_email,
        subject,
        _wrap_nidaan_template(title, content),
        from_name="Nidaan Partner",
        from_email=NIDAAN_FROM or None,
        # A login link/code in the spam folder locks a partner out of their own portal.
        delivery_critical=True,
    )


PLAN_FEATURES = {
    "silver":   {"label": "Silver",   "support": "Basic email support"},
    "gold":     {"label": "Gold",     "support": "Priority support"},
    "platinum": {"label": "Platinum", "support": "Dedicated case manager"},
}

async def send_nidaan_subscription_email(
    to_email: str,
    owner_name: str,
    plan: str,
    amount_paid: int,
    renewal_date: str,
) -> bool:
    """Send a subscription confirmation email with plan details and renewal date. Quota + billing
    cycle are derived from the LIVE plan config so they never drift (no hardcoded quarterly/quota)."""
    base_plan = str(plan or "").replace("_annual", "")
    info = PLAN_FEATURES.get(base_plan, {"label": base_plan.title() or "Plan", "support": "—"})
    # Real quota from the live limits — silver/gold = 3/month, platinum = 10/month, etc. NO "quarter".
    quota = "—"
    try:
        import biz_nidaan as _n
        _lim = _n.PLAN_LIMITS.get(plan) or _n.PLAN_LIMITS.get(base_plan) or {}
        _cpm = _lim.get("claims_per_month")
        quota = "Unlimited claims" if _cpm is None else f"{_cpm} claims / month"
    except Exception:
        pass
    info = {**info, "quota": quota}
    cycle_word = "year" if str(plan).endswith("_annual") else "month"
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    amount_str = f"₹{amount_paid:,}" if amount_paid else "—"
    content = f"""
<h2>🎉 Your {info['label']} Plan is Active!</h2>
<p>{greeting}</p>
<p>Thank you for subscribing to <strong>Nidaan Partner</strong>. Your payment was successful and your plan is now active.</p>

<div style="background:rgba(6,182,212,.12);border:1px solid rgba(6,182,212,.35);border-radius:12px;padding:1.25rem 1.5rem;margin:1.5rem 0">
  <p style="color:#22d3ee;font-size:1.1rem;font-weight:800;margin-bottom:.75rem">{info['label']} Plan</p>
  <table style="width:100%;font-size:.88rem;border-collapse:collapse">
    <tr><td style="color:#64748b;padding:.3rem 0;width:130px">Amount paid</td><td style="color:#e2e8f0;font-weight:700">{amount_str}</td></tr>
    <tr><td style="color:#64748b;padding:.3rem 0">Claims quota</td><td style="color:#e2e8f0">{info['quota']}</td></tr>
    <tr><td style="color:#64748b;padding:.3rem 0">Support</td><td style="color:#e2e8f0">{info['support']}</td></tr>
    <tr><td style="color:#64748b;padding:.3rem 0">Next renewal</td><td style="color:#e2e8f0;font-weight:700">{renewal_date}</td></tr>
  </table>
</div>

<p>You can now log in to your dashboard and start submitting insurance claim disputes.</p>
<p style="text-align:center;margin:1.5rem 0">
  <a href="https://nidaanpartner.com/nidaan/dashboard"
     style="display:inline-block;background:#06b6d4;color:#fff;padding:.75rem 2rem;
            border-radius:8px;font-weight:700;text-decoration:none">
    Go to Dashboard →
  </a>
</p>
<p style="color:#475569;font-size:.82rem">
  Your subscription auto-renews every {cycle_word}. You can manage or cancel your subscription
  at any time from the Profile section of your dashboard.
</p>"""
    return await send_email(
        to_email,
        f"Nidaan Partner — {info['label']} Plan Activated!",
        _wrap_nidaan_template("Subscription Activated", content),
        from_name="Nidaan Partner",
    )


async def send_nidaan_autopay_recovery_email(
    to_email: str,
    owner_name: str,
    plan: str = "",
    kind: str = "pending",   # 'pending' (mid-retry) | 'halted' (autopay stopped)
    recovery_url: str = "https://nidaanpartner.com/nidaan/dashboard",
) -> bool:
    """Tell a subscriber their auto-pay needs attention, with a one-tap recovery link — so a
    failed/pending recurring charge can be fixed by the customer during (or after) Razorpay's
    retry window instead of silently lapsing."""
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    if kind == "halted":
        title = "Action needed — your subscription auto-pay stopped"
        head = "⚠️ Your subscription auto-pay has stopped"
        body = ("<p>We tried to renew your <strong>Nidaan Partner</strong> subscription a few times, "
                "but the auto-pay didn't go through (often insufficient balance, an expired card, or "
                "a bank mandate that needs re-approval).</p>"
                "<p>To keep your plan active, please re-subscribe in one tap:</p>")
        cta = "Re-activate my plan →"
    else:
        title = "Your subscription payment is pending"
        head = "⏳ Your subscription payment is pending"
        body = ("<p>Your latest <strong>Nidaan Partner</strong> auto-pay is awaiting authorization "
                "(UPI mandate / bank approval). It usually clears within a few minutes.</p>"
                "<p>If it doesn't go through, you can authorize or update your payment method here:</p>")
        cta = "Authorize / update payment →"
    content = f"""
<h2>{head}</h2>
<p>{greeting}</p>
{body}
<p style="text-align:center;margin:1.5rem 0">
  <a href="{recovery_url}"
     style="display:inline-block;background:#06b6d4;color:#fff;padding:.75rem 2rem;
            border-radius:8px;font-weight:700;text-decoration:none">{cta}</a>
</p>
<p style="color:#475569;font-size:.82rem">Already sorted? You can ignore this message. Need help?
Reply to this email or use the chat on your dashboard.</p>"""
    return await send_email(
        to_email, f"Nidaan Partner — {title}",
        _wrap_nidaan_template("Auto-pay needs attention", content),
        from_name="Nidaan Partner",
    )


async def send_nidaan_new_claim_admin_email(
    admin_email: str,
    claim_id: int,
    advisor_name: str,
    advisor_email: str,
    insured_name: str,
    claim_type: str,
    insurer_name: str = "",
    disputed_amount: Optional[int] = None,
    notes: str = "",
) -> bool:
    """Notify admin when a new Nidaan claim is submitted."""
    amt_str = f"₹{disputed_amount:,}" if disputed_amount else "—"
    notes_section = ""
    if notes and notes.strip():
        notes_section = f"""
<div style="background:rgba(34,211,238,0.08);border-left:4px solid #22d3ee;padding:16px 20px;border-radius:0 8px 8px 0;margin:20px 0;color:#e2e8f0;font-size:14px">
  <strong style="color:#22d3ee">Agent notes:</strong><br>{notes.strip()}
</div>"""
    # Colours below are tuned for the DARK Nidaan email card: dim labels (#94a3b8),
    # bright values (#e2e8f0), subtle row dividers, cyan accent for the amount.
    content = f"""
<h2>New Claim Submitted — #{claim_id}</h2>
<p>A new claim has been submitted on <strong>Nidaan Partner</strong> and requires assignment.</p>
<table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px">
  <tr style="border-bottom:1px solid rgba(255,255,255,0.08)">
    <td style="padding:8px 0;color:#94a3b8;width:140px">Claim #</td>
    <td style="padding:8px 0;font-weight:700;color:#e2e8f0">#{claim_id}</td>
  </tr>
  <tr style="border-bottom:1px solid rgba(255,255,255,0.08)">
    <td style="padding:8px 0;color:#94a3b8">Advisor</td>
    <td style="padding:8px 0;color:#e2e8f0">{advisor_name} &lt;{advisor_email}&gt;</td>
  </tr>
  <tr style="border-bottom:1px solid rgba(255,255,255,0.08)">
    <td style="padding:8px 0;color:#94a3b8">Client</td>
    <td style="padding:8px 0;color:#e2e8f0">{insured_name}</td>
  </tr>
  <tr style="border-bottom:1px solid rgba(255,255,255,0.08)">
    <td style="padding:8px 0;color:#94a3b8">Type</td>
    <td style="padding:8px 0;color:#e2e8f0;text-transform:capitalize">{claim_type.replace('_',' ')}</td>
  </tr>
  <tr style="border-bottom:1px solid rgba(255,255,255,0.08)">
    <td style="padding:8px 0;color:#94a3b8">Insurer</td>
    <td style="padding:8px 0;color:#e2e8f0">{insurer_name or '—'}</td>
  </tr>
  <tr>
    <td style="padding:8px 0;color:#94a3b8">Disputed Amt</td>
    <td style="padding:8px 0;font-weight:700;color:#22d3ee">{amt_str}</td>
  </tr>
</table>
{notes_section}
<p style="text-align:center;margin-top:24px">
  <a href="https://nidaanpartner.com/nidaan/admin" style="display:inline-block;padding:13px 30px;background:linear-gradient(135deg,#0e7490,#06b6d4);color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px">Open Admin Panel →</a>
</p>"""
    subject = f"New Claim #{claim_id} — {insured_name} | Nidaan Partner"
    html = _wrap_nidaan_template("New Claim", content)
    # Item 2: send FROM the Nidaan sender (info@nidaanpartner.com) — from_name
    # starting with "Nidaan" selects NIDAAN_FROM in send_email().
    ok = await send_email(admin_email, subject, html, from_name="Nidaan Partner")
    # Copy to the shared Nidaan mailbox, consistent with other Nidaan flows.
    copy_to = os.getenv("NIDAAN_ADMIN_COPY", "nidaanpartner@gmail.com")
    if copy_to and copy_to.lower() != (admin_email or "").lower():
        try:
            await send_email(copy_to, subject, html, from_name="Nidaan Partner")
        except Exception:
            pass
    return ok


async def send_nidaan_claim_status_email(
    to_email: str,
    owner_name: str,
    claim_id: int,
    insured_name: str,
    claim_type: str,
    new_status: str,
    note: str = "",
) -> bool:
    """Notify a Nidaan advisor that their claim status has been updated."""
    STATUS_LABELS = {
        "intimated": "Intimated",
        "assigned": "Assigned to Legal Team",
        "in_review": "Under Review",
        "in_negotiation": "In Negotiation",
        "resolved_won": "Resolved — Won ✓",
        "resolved_lost": "Resolved — Lost",
        "closed": "Closed",
        "withdrawn": "Withdrawn",
    }
    STATUS_COLORS = {
        "intimated": "#d97706",
        "assigned": "#2563eb",
        "in_review": "#7c3aed",
        "in_negotiation": "#ea580c",
        "resolved_won": "#16a34a",
        "resolved_lost": "#dc2626",
        "closed": "#6b7280",
        "withdrawn": "#6b7280",
    }
    label = STATUS_LABELS.get(new_status, new_status.replace("_", " ").title())
    color = STATUS_COLORS.get(new_status, "#1a56db")
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    note_section = ""
    if note and note.strip():
        note_section = f"""
<div class="highlight">
  <strong>Note from our team:</strong><br>
  {note.strip()}
</div>"""
    content = f"""
<h2>Claim Status Update</h2>
<p>{greeting}</p>
<p>Your claim <strong>#{claim_id}</strong> for client <strong>{insured_name}</strong>
({claim_type.replace('_', ' ').title()}) has been updated:</p>
<div style="text-align:center;margin:24px 0">
  <span style="display:inline-block;padding:10px 24px;border-radius:20px;
    background:{color}1a;border:2px solid {color};color:{color};
    font-weight:700;font-size:1rem;letter-spacing:.03em">{label}</span>
</div>
{note_section}
<p>Log in to your dashboard to view the full status history and any documents.</p>
<p style="text-align:center;margin-top:24px">
  <a href="https://nidaanpartner.com/nidaan/dashboard" class="btn">View Dashboard</a>
</p>
<p style="color:#94a3b8;font-size:13px;margin-top:28px">
  If you have questions, reply to this email or contact us at
  <a href="mailto:support@nidaanpartner.com" style="color:#06b6d4">support@nidaanpartner.com</a>.
</p>"""
    subject = f"Claim #{claim_id} — {label} | Nidaan Partner"
    return await send_email(to_email, subject, _wrap_nidaan_template("Claim Status Update", content), from_name="Nidaan Partner")


async def send_nidaan_claim_assigned_staff_email(
    to_email: str,
    staff_name: str,
    claim_id: int,
    insured_name: str,
    claim_type: str,
    advisor_name: str = "",
    advisor_phone: str = "",
) -> bool:
    """Notify a Nidaan staff member (associate) that a claim has been assigned to them."""
    greeting = f"Hi {staff_name}," if staff_name else "Hi,"
    advisor_section = ""
    if advisor_name or advisor_phone:
        advisor_section = f"""
<div class="highlight">
  <strong>Advisor / Account Holder:</strong><br>
  {advisor_name}{(' &nbsp;|&nbsp; ' + advisor_phone) if advisor_phone else ''}
</div>"""
    content = f"""
<h2>New Claim Assigned to You</h2>
<p>{greeting}</p>
<p>A new claim has been assigned to you on <strong>Nidaan Partner</strong>. Please log in to the ops portal to review the details and take action.</p>
<div style="background:#0f2a4a;border:1px solid rgba(6,182,212,.3);border-radius:10px;padding:18px 22px;margin:18px 0">
  <div style="font-size:.75rem;font-weight:700;color:#06b6d4;letter-spacing:.08em;margin-bottom:10px">CLAIM DETAILS</div>
  <div style="color:#e2e8f0"><strong>Claim #:</strong> #{claim_id}</div>
  <div style="color:#e2e8f0;margin-top:6px"><strong>Claimant:</strong> {insured_name}</div>
  <div style="color:#e2e8f0;margin-top:6px"><strong>Type:</strong> {claim_type.replace('_', ' ').title()}</div>
</div>
{advisor_section}
<p>Please review all uploaded documents, update the claim status, and schedule any follow-ups as needed.</p>
<p style="text-align:center;margin-top:24px">
  <a href="https://nidaanpartner.com/nidaan/ops" class="btn">Open Ops Portal</a>
</p>
<p style="color:#94a3b8;font-size:13px;margin-top:28px">
  If you have questions, contact your team admin or reply to this email.
</p>"""
    subject = f"New Claim Assigned — #{claim_id} ({insured_name}) | Nidaan Ops"
    return await send_email(to_email, subject, _wrap_nidaan_template("Claim Assigned", content), from_name="Nidaan Ops")


async def send_trial_reminder(to_email: str, owner_name: str, firm_name: str,
                               days_left: int, tenant_id: int) -> bool:
    """Send trial expiry reminder."""
    if days_left <= 0:
        urgency = "expired"
        subject = f"⚠️ {firm_name} — Your Free Trial Has Expired"
        message = "Your 14-day free trial has expired. Your data is safe for now, but you'll lose access to all features."
        cta_text = "Subscribe Now — Keep Your Data"
        cta_class = "btn btn-orange"
    elif days_left == 1:
        urgency = "last_day"
        subject = f"⏰ {firm_name} — Last Day of Free Trial!"
        message = "Your free trial ends <strong>tomorrow</strong>! Subscribe now to keep all your data and continue growing your business."
        cta_text = "Subscribe Now"
        cta_class = "btn btn-orange"
    else:
        urgency = "reminder"
        subject = f"📅 {firm_name} — {days_left} Days Left in Free Trial"
        message = f"Your free trial ends in <strong>{days_left} days</strong>. You've been doing great — don't lose your progress!"
        cta_text = "View Plans & Subscribe"
        cta_class = "btn"

    content = f"""
<h2>Trial Reminder for {firm_name}</h2>
<p>Hi {owner_name},</p>
<p>{message}</p>
<div class="highlight">
  <p><strong>Plan:</strong> Free Trial</p>
  <p><strong>Days remaining:</strong> {max(0, days_left)}</p>
  <p><strong>Starting from:</strong> ₹199/month (Solo Advisor)</p>
</div>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/#pricing" class="{cta_class}">{cta_text} →</a>
</p>"""
    return await send_email(to_email, subject, _wrap_template("Trial Reminder", content))


async def send_payment_receipt(to_email: str, owner_name: str, firm_name: str,
                                plan_name: str, amount: str,
                                payment_id: str, next_due: str = "",
                                founding_discount: bool = False,
                                original_amount: str = "") -> bool:
    """Send payment confirmation receipt."""
    next_line = f"<p><strong>Next payment:</strong> {next_due}</p>" if next_due else ""

    if founding_discount and original_amount:
        discount_block = f"""
<div style="background:linear-gradient(135deg,#fef3c7,#fde68a);padding:16px 20px;border-radius:12px;margin:16px 0;border-left:4px solid #f59e0b">
  <p style="margin:0 0 6px;font-weight:700;color:#92400e">🏆 Founding Customer — 20% Discount Applied!</p>
  <p style="margin:0;color:#78350f">Original price: <s>{original_amount}</s> → You pay: <strong>{amount}</strong></p>
  <p style="margin:4px 0 0;font-size:13px;color:#92400e">This founding discount is locked in for your first year!</p>
</div>"""
        heading = "Payment Confirmed — Founding Customer! 🏆✅"
        intro = f"""Thank you for becoming a <strong>Sarathi-AI Founding Customer</strong>!
Your payment has been processed with your exclusive 20% founding discount."""
    else:
        discount_block = ""
        heading = "Payment Confirmed! ✅"
        intro = "Thank you for subscribing to Sarathi-AI! Your payment has been processed successfully."

    content = f"""
<h2>{heading}</h2>
<p>Hi {owner_name},</p>
<p>{intro}</p>
{discount_block}
<div class="highlight">
  <p><strong>Firm:</strong> {firm_name}</p>
  <p><strong>Plan:</strong> {plan_name}</p>
  <p><strong>Amount Paid:</strong> {amount}</p>
  <p><strong>Payment ID:</strong> {payment_id}</p>
  {next_line}
</div>
<p>Your subscription is now active. All features are unlocked!</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/dashboard" class="btn">Go to Dashboard →</a>
</p>"""
    subject_prefix = "🏆 " if founding_discount else ""
    return await send_email(to_email, f"{subject_prefix}Payment Receipt — {plan_name} — Sarathi-AI",
                            _wrap_template("Payment Receipt", content))


async def send_cancellation_confirmation(to_email: str, owner_name: str,
                                          firm_name: str, data_retained_until: str) -> bool:
    """Send subscription cancellation confirmation."""
    content = f"""
<h2>Subscription Cancelled</h2>
<p>Hi {owner_name},</p>
<p>Your subscription for <strong>{firm_name}</strong> has been cancelled as requested.</p>
<div class="highlight">
  <p><strong>Data retained until:</strong> {data_retained_until}</p>
  <p>After this date, your data will be permanently deleted.</p>
</div>
<p>We're sorry to see you go. If you change your mind, you can reactivate your subscription anytime
   before the data retention period ends.</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/#pricing" class="btn">Reactivate Subscription →</a>
</p>
<p style="color:#94a3b8;font-size:13px;margin-top:16px">
  If you have any feedback, please reply to this email. We value your input!
</p>"""
    return await send_email(to_email, f"Subscription Cancelled — {firm_name} — Sarathi-AI",
                            _wrap_template("Cancelled", content))


# ── New Billing & Affiliate Email Templates ──────────────────────────────────

async def send_payment_pending_email(to_email: str, owner_name: str,
                                      firm_name: str) -> bool:
    """Notify owner that payment is pending authorization (UPI mandate / bank)."""
    content = f"""
<h2>Payment Pending ⏳</h2>
<p>Hi {owner_name},</p>
<p>Your payment for <strong>{firm_name}</strong> is awaiting authorization
   (UPI mandate / bank approval).</p>
<div class="highlight">
  <p>This usually completes within a few minutes. No action needed from your side.</p>
</div>
<p>If the payment doesn't go through within 24 hours, please try again from your dashboard.</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/dashboard" class="btn btn-orange">Go to Dashboard →</a>
</p>"""
    return await send_email(to_email, f"⏳ Payment Pending — {firm_name}",
                            _wrap_template("Payment Pending", content))


async def send_payment_failed_email(to_email: str, owner_name: str,
                                     firm_name: str, error_reason: str) -> bool:
    """Notify owner that a payment attempt failed."""
    content = f"""
<h2>Payment Failed ❌</h2>
<p>Hi {owner_name},</p>
<p>We were unable to process the payment for <strong>{firm_name}</strong>.</p>
<div class="highlight">
  <p><strong>Reason:</strong> {error_reason}</p>
</div>
<p>Please update your payment method or try again to keep your account active.</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/dashboard" class="btn btn-orange">Retry Payment →</a>
</p>
<p style="color:#94a3b8;font-size:13px;margin-top:16px">
  If you continue to face issues, contact us at support@sarathi-ai.com.
</p>"""
    return await send_email(to_email, f"⚠️ Payment Failed — {firm_name}",
                            _wrap_template("Payment Failed", content))


async def send_account_deactivated(to_email: str, owner_name: str,
                                    firm_name: str, grace_days: int = 10) -> bool:
    """Notify owner that their account has been deactivated."""
    content = f"""
<h2>Account Deactivated</h2>
<p>Hi {owner_name},</p>
<p>Your Sarathi-AI account for <strong>{firm_name}</strong> has been deactivated
   due to an expired subscription.</p>
<div class="highlight">
  <p><strong>Grace Period:</strong> {grace_days} days</p>
  <p>Your data is safe during this period. Subscribe to restore access immediately.</p>
</div>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/#pricing" class="btn btn-orange">Reactivate Now →</a>
</p>
<p style="color:#94a3b8;font-size:13px;margin-top:16px">
  After the grace period, your data will be permanently deleted.
</p>"""
    return await send_email(to_email, f"⚠️ Account Deactivated — {firm_name}",
                            _wrap_template("Deactivated", content))


async def send_data_deletion_warning(to_email: str, owner_name: str,
                                      firm_name: str, days_left: int) -> bool:
    """Final warning before permanent data deletion."""
    content = f"""
<h2>⚠️ Data Deletion Warning</h2>
<p>Hi {owner_name},</p>
<p>Your data for <strong>{firm_name}</strong> will be <strong>permanently deleted
   in {days_left} day{'s' if days_left != 1 else ''}</strong>.</p>
<div class="highlight">
  <p><strong>This action is irreversible.</strong></p>
  <p>All client records, calculator reports, campaign history, and settings will be removed.</p>
</div>
<p>Subscribe now to save your data and restore full access.</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/#pricing" class="btn btn-orange">Subscribe & Save Data →</a>
</p>"""
    return await send_email(to_email, f"🚨 URGENT: Data Deletion in {days_left} Days — {firm_name}",
                            _wrap_template("Data Deletion Warning", content))


async def send_renewal_success(to_email: str, owner_name: str, firm_name: str,
                                plan_name: str, amount: str, next_date: str) -> bool:
    """Confirm successful subscription renewal."""
    content = f"""
<h2>Renewal Successful ✅</h2>
<p>Hi {owner_name},</p>
<p>Your subscription for <strong>{firm_name}</strong> has been renewed successfully.</p>
<div class="highlight">
  <p><strong>Plan:</strong> {plan_name}</p>
  <p><strong>Amount:</strong> {amount}</p>
  <p><strong>Next renewal:</strong> {next_date}</p>
</div>
<p>Thank you for continuing with Sarathi-AI! All features remain active.</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/dashboard" class="btn">Go to Dashboard →</a>
</p>"""
    return await send_email(to_email, f"Renewal Confirmed — {plan_name} — Sarathi-AI",
                            _wrap_template("Renewal", content))


async def send_affiliate_welcome(to_email: str, name: str, referral_code: str) -> bool:
    """Welcome email for newly verified affiliate partner."""
    referral_link = f"https://sarathi-ai.com/?ref={referral_code}"
    content = f"""
<h2>Welcome, Partner! 🤝</h2>
<p>Hi {name},</p>
<p>Congratulations! Your Sarathi-AI affiliate account has been verified and activated.</p>
<div class="highlight">
  <p><strong>Your Referral Code:</strong> {referral_code}</p>
  <p><strong>Your Referral Link:</strong></p>
  <p><a href="{referral_link}">{referral_link}</a></p>
</div>
<p>Share your referral link with financial advisors in your network.
   When they subscribe, you earn commission on every payment!</p>
<p><strong>How it works:</strong></p>
<p>1️⃣ Share your unique link with advisors<br>
   2️⃣ They sign up for a 14-day free trial<br>
   3️⃣ When they subscribe to a paid plan, you earn commission<br>
   4️⃣ Track everything on your affiliate dashboard</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/partner" class="btn">View Dashboard →</a>
</p>"""
    return await send_email(to_email, f"Welcome to Sarathi-AI Partner Program, {name}!",
                            _wrap_template("Partner Welcome", content))


async def send_affiliate_commission_earned(to_email: str, name: str,
                                           commission: float, plan: str,
                                           referred_name: str = "") -> bool:
    """Notify affiliate when a referral converts and commission is earned."""
    ref_display = f" ({referred_name})" if referred_name else ""
    content = f"""
<h2>Commission Earned! 💰</h2>
<p>Hi {name},</p>
<p>Great news! A referral{ref_display} has subscribed to the <strong>{plan.title()}</strong> plan.</p>
<div class="highlight">
  <p><strong>Commission Earned:</strong> ₹{commission:.2f}</p>
  <p><strong>Status:</strong> In cooling period (7 days)</p>
</div>
<p>Your commission will be available for payout after a 7-day verification period.
   Make sure your UPI/bank details are updated on your dashboard.</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/partner" class="btn">View Dashboard →</a>
</p>"""
    return await send_email(to_email, f"₹{commission:.2f} Commission Earned — Sarathi-AI",
                            _wrap_template("Commission Earned", content))


async def send_affiliate_payout_notification(to_email: str, name: str,
                                              amount: float, method: str,
                                              status: str) -> bool:
    """Notify affiliate about payout status (initiated/completed)."""
    if status == 'initiated':
        subject = f"Payout of ₹{amount:.2f} Initiated — Sarathi-AI"
        status_text = "Your payout has been initiated and will be processed shortly."
        emoji = "🚀"
    else:
        subject = f"₹{amount:.2f} Payout Completed — Sarathi-AI"
        status_text = "Your payout has been successfully processed!"
        emoji = "✅"

    content = f"""
<h2>Payout {status.title()} {emoji}</h2>
<p>Hi {name},</p>
<p>{status_text}</p>
<div class="highlight">
  <p><strong>Amount:</strong> ₹{amount:.2f}</p>
  <p><strong>Method:</strong> {method.upper()}</p>
  <p><strong>Status:</strong> {status.title()}</p>
</div>
<p>You can view your complete payout history on your affiliate dashboard.</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/partner" class="btn">View Dashboard →</a>
</p>"""
    return await send_email(to_email, subject,
                            _wrap_template(f"Payout {status.title()}", content))


async def send_support_ticket_notification(ticket_id: int, subject: str,
                                           description: str, category: str,
                                           priority: str, tenant_info: str = "") -> bool:
    """Notify admin about a new support ticket via email."""
    import html as html_mod
    admin_email = os.getenv("SUPPORT_ADMIN_EMAIL", "support@sarathi-ai.com")
    email_subject = f"🎫 New Ticket #{ticket_id}: {subject[:60]}"
    content = f"""
<h2>New Support Ticket 🎫</h2>
<div class="highlight">
  <p><strong>Ticket ID:</strong> #{ticket_id}</p>
  <p><strong>Subject:</strong> {html_mod.escape(subject)}</p>
  <p><strong>Category:</strong> {html_mod.escape(category)}</p>
  <p><strong>Priority:</strong> {html_mod.escape(priority)}</p>
  <p><strong>From:</strong> {html_mod.escape(tenant_info or 'Public visitor')}</p>
</div>
<h3>Description</h3>
<p style="background:#f8fafc;padding:14px;border-radius:8px;border-left:3px solid #0d9488">{html_mod.escape(description[:2000])}</p>
<p style="text-align:center;margin-top:24px">
  <a href="{_base_url()}/admin" class="btn">Open Admin Panel →</a>
</p>"""
    return await send_support_email(admin_email, email_subject,
                                    _wrap_template("Support Ticket", content))


# =============================================================================
#  SUBSCRIPTION RENEWAL REMINDERS
# =============================================================================

_NIDAAN_PLAN_PRICES = {
    "silver":          "₹500/month",
    "gold":            "₹1,000/month",
    "platinum":        "₹2,000/month",
    "silver_annual":   "₹5,000/year",
    "gold_annual":     "₹10,000/year",
    "platinum_annual": "₹20,000/year",
}

async def send_nidaan_renewal_reminder(
    to_email: str,
    owner_name: str,
    plan: str,
    days_left: int,
    renewal_date: str,
    renew_url: str = "https://nidaanpartner.com/nidaan/dashboard",
) -> bool:
    """Send renewal reminder 7 days or 1 day before Nidaan subscription expires."""
    info = PLAN_FEATURES.get(plan.replace("_annual", ""), {"label": plan.title(), "quota": "—", "support": "—"})
    price = _NIDAAN_PLAN_PRICES.get(plan, "—")
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    urgency = "⏰ Renewing Soon" if days_left > 1 else "🚨 Last Day!"
    content = f"""
<h2>{urgency} — Your Nidaan Partner subscription expires in {days_left} day{"s" if days_left != 1 else ""}.</h2>
<p>{greeting}</p>
<p>Your <strong>{info['label']} Plan</strong> is set to expire on <strong>{renewal_date}</strong>.</p>

<div style="background:rgba(6,182,212,.12);border:1px solid rgba(6,182,212,.35);border-radius:12px;padding:1.25rem 1.5rem;margin:1.5rem 0">
  <p style="color:#22d3ee;font-size:1.1rem;font-weight:800;margin-bottom:.75rem">{info['label']} Plan — {price}</p>
  <table style="width:100%;font-size:.88rem;border-collapse:collapse">
    <tr><td style="color:#64748b;padding:.3rem 0;width:130px">Claims quota</td><td style="color:#e2e8f0">{info['quota']}</td></tr>
    <tr><td style="color:#64748b;padding:.3rem 0">Support</td><td style="color:#e2e8f0">{info['support']}</td></tr>
    <tr><td style="color:#64748b;padding:.3rem 0">Expires on</td><td style="color:#f87171;font-weight:700">{renewal_date}</td></tr>
  </table>
</div>

<p>To continue without interruption, renew your subscription now from your dashboard.</p>
<p style="text-align:center;margin:1.5rem 0">
  <a href="{renew_url}"
     style="display:inline-block;background:#06b6d4;color:#fff;padding:.75rem 2rem;
            border-radius:8px;font-weight:700;text-decoration:none">
    Renew Subscription →
  </a>
</p>
<p style="color:#475569;font-size:.82rem">
  After expiry, your dashboard will be locked until you renew. All your claim history is safely preserved.
</p>"""
    subject = (f"Nidaan Partner — Your {info['label']} plan expires in {days_left} day{'s' if days_left != 1 else ''}")
    return await send_email(
        to_email, subject,
        _wrap_nidaan_template("Subscription Renewal Reminder", content),
        from_name="Nidaan Partner",
    )


async def send_nidaan_expired_email(
    to_email: str,
    owner_name: str,
    plan: str,
    renew_url: str = "https://nidaanpartner.com/nidaan/dashboard",
) -> bool:
    """Send email when Nidaan subscription has just expired."""
    info = PLAN_FEATURES.get(plan.replace("_annual", ""), {"label": plan.title(), "quota": "—", "support": "—"})
    price = _NIDAAN_PLAN_PRICES.get(plan, "—")
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    content = f"""
<h2>🔒 Your Nidaan Partner subscription has expired.</h2>
<p>{greeting}</p>
<p>Your <strong>{info['label']} Plan</strong> ({price}) has expired. Your dashboard has been locked, but your data and claim history are fully preserved.</p>

<div style="background:rgba(248,113,113,.12);border:1px solid rgba(248,113,113,.35);border-radius:12px;padding:1.25rem 1.5rem;margin:1.5rem 0">
  <p style="color:#fca5a5;font-size:.95rem;font-weight:700;margin-bottom:.5rem">What's locked:</p>
  <ul style="color:#cbd5e1;font-size:.88rem;margin:0;padding-left:1.25rem">
    <li>Submitting new claims</li>
    <li>Accessing claim status and documents</li>
    <li>Team member access</li>
  </ul>
</div>

<p>Renew now to restore full access immediately.</p>
<p style="text-align:center;margin:1.5rem 0">
  <a href="{renew_url}"
     style="display:inline-block;background:#06b6d4;color:#fff;padding:.75rem 2rem;
            border-radius:8px;font-weight:700;text-decoration:none">
    Renew Now →
  </a>
</p>
<p style="color:#475569;font-size:.82rem">
  Questions? Reply to this email or contact us at <a href="mailto:support@nidaanpartner.com" style="color:#06b6d4">support@nidaanpartner.com</a>.
</p>"""
    return await send_email(
        to_email,
        f"Nidaan Partner — Your {info['label']} plan has expired",
        _wrap_nidaan_template("Subscription Expired", content),
        from_name="Nidaan Partner",
    )


_SARATHI_PLAN_LABELS = {
    "individual": "Solo Advisor",
    "team":       "Team",
    "enterprise": "Enterprise",
    "solo":       "Solo Advisor",
}

async def send_sarathi_renewal_reminder(
    to_email: str,
    owner_name: str,
    firm_name: str,
    plan: str,
    days_left: int,
    renewal_date: str,
    renew_url: str = "",
) -> bool:
    """Send renewal reminder 7 days or 1 day before Sarathi CRM subscription expires."""
    plan_label = _SARATHI_PLAN_LABELS.get(plan, plan.title())
    if not renew_url:
        renew_url = f"{_base_url()}/dashboard#subscription"
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    urgency = "⏰ Renewing Soon" if days_left > 1 else "🚨 Last Day!"
    content = f"""
<h2>{urgency} — {firm_name}'s Sarathi-AI subscription expires in {days_left} day{"s" if days_left != 1 else ""}.</h2>
<p>{greeting}</p>
<p>Your <strong>{plan_label}</strong> plan for <strong>{firm_name}</strong> is set to expire on <strong>{renewal_date}</strong>.</p>

<div class="highlight">
  <p><strong>Plan:</strong> {plan_label}</p>
  <p><strong>Expires on:</strong> <span style="color:#ef4444">{renewal_date}</span></p>
</div>

<p>After expiry, your team will lose access to the AI assistant, reports, and client management tools.</p>
<p style="text-align:center;margin:1.5rem 0">
  <a href="{renew_url}" class="btn">Renew Subscription →</a>
</p>
<p style="color:#475569;font-size:.82rem">
  Need help? Reply to this email or contact <a href="mailto:support@sarathi-ai.com">support@sarathi-ai.com</a>.
</p>"""
    subject = f"Sarathi-AI — {firm_name}: subscription expires in {days_left} day{'s' if days_left != 1 else ''}"
    return await send_email(to_email, subject, _wrap_template("Subscription Renewal Reminder", content))


async def send_sarathi_expired_email(
    to_email: str,
    owner_name: str,
    firm_name: str,
    plan: str,
    renew_url: str = "",
) -> bool:
    """Send email when a paid Sarathi CRM subscription has just expired."""
    plan_label = _SARATHI_PLAN_LABELS.get(plan, plan.title())
    if not renew_url:
        renew_url = f"{_base_url()}/#pricing"
    greeting = f"Hi {owner_name}," if owner_name else "Hi,"
    content = f"""
<h2>🔒 {firm_name}'s Sarathi-AI subscription has expired.</h2>
<p>{greeting}</p>
<p>Your <strong>{plan_label}</strong> plan has expired. Your team's access to the AI assistant and client management tools has been paused.</p>
<p>All your client data, leads, policies, and reports are safely preserved.</p>

<p style="text-align:center;margin:1.5rem 0">
  <a href="{renew_url}" class="btn">Renew Subscription →</a>
</p>
<p style="color:#475569;font-size:.82rem">
  Questions? Reply to this email or contact <a href="mailto:support@sarathi-ai.com">support@sarathi-ai.com</a>.
</p>"""
    return await send_email(
        to_email,
        f"Sarathi-AI — {firm_name}: subscription expired",
        _wrap_template("Subscription Expired", content),
    )
