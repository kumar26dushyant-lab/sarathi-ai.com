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
_initialized = False

def _base_url() -> str:
    """Get the server base URL from environment."""
    return os.getenv("SERVER_URL", "https://sarathi-ai.com").rstrip("/")


def init_email():
    """Initialize email configuration from environment."""
    global SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, FROM_NOREPLY, FROM_SUPPORT, _initialized

    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)
    FROM_NOREPLY = os.getenv("SMTP_FROM_NOREPLY", FROM_EMAIL)  # info@sarathi-ai.com
    FROM_SUPPORT = os.getenv("SMTP_FROM_SUPPORT", FROM_EMAIL)  # support@sarathi-ai.com

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
                     from_name: str = "", reply_to: str = "") -> bool:
    """Send an email via SMTP. Returns True on success.
    from_email: override sender address (defaults to FROM_NOREPLY).
    from_name: override sender display name.
    reply_to: override Reply-To header (defaults to noreply)."""
    if not _initialized:
        logger.warning("Email not sent (not configured): %s → %s", subject, to_email)
        return False

    sender_email = from_email or FROM_NOREPLY
    sender_name = from_name or FROM_NAME

    try:
        import aiosmtplib
        import uuid
        import re as _re

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Reply-To"] = reply_to or FROM_NOREPLY or sender_email
        # Sender header: tells RFC-compliant clients who actually sent (on behalf of From)
        if SMTP_USER and SMTP_USER != sender_email:
            msg["Sender"] = f"{sender_name} <{SMTP_USER}>"
        msg["MIME-Version"] = "1.0"
        msg["Message-ID"] = f"<{uuid.uuid4()}@sarathi-ai.com>"
        msg["List-Unsubscribe"] = f"<mailto:{FROM_SUPPORT or sender_email}?subject=Unsubscribe>"
        msg["X-Mailer"] = "Sarathi-AI CRM"

        # Always attach plain text part for deliverability
        if not text_body:
            text_body = _re.sub(r'<[^>]+>', '', html_body)
            text_body = _re.sub(r'\s+', ' ', text_body).strip()
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            use_tls=False,
            start_tls=True,
        )
        logger.info("📧 Email sent: '%s' → %s (from %s)", subject, to_email, sender_email)
        return True

    except Exception as e:
        logger.error("📧 Email failed: '%s' → %s: %s", subject, to_email, e)
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
  <p>Nidaan Partner — by Sarathi-AI Business Technologies</p>
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
<div class="highlight">
  <strong>Agent notes:</strong><br>{notes.strip()}
</div>"""
    content = f"""
<h2>New Claim Submitted — #{claim_id}</h2>
<p>A new claim has been submitted on <strong>Nidaan Partner</strong> and requires assignment.</p>
<table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px">
  <tr style="border-bottom:1px solid #e2e8f0">
    <td style="padding:8px 0;color:#64748b;width:140px">Claim #</td>
    <td style="padding:8px 0;font-weight:700;color:#1e293b">#{claim_id}</td>
  </tr>
  <tr style="border-bottom:1px solid #e2e8f0">
    <td style="padding:8px 0;color:#64748b">Advisor</td>
    <td style="padding:8px 0;color:#1e293b">{advisor_name} &lt;{advisor_email}&gt;</td>
  </tr>
  <tr style="border-bottom:1px solid #e2e8f0">
    <td style="padding:8px 0;color:#64748b">Client</td>
    <td style="padding:8px 0;color:#1e293b">{insured_name}</td>
  </tr>
  <tr style="border-bottom:1px solid #e2e8f0">
    <td style="padding:8px 0;color:#64748b">Type</td>
    <td style="padding:8px 0;color:#1e293b;text-transform:capitalize">{claim_type.replace('_',' ')}</td>
  </tr>
  <tr style="border-bottom:1px solid #e2e8f0">
    <td style="padding:8px 0;color:#64748b">Insurer</td>
    <td style="padding:8px 0;color:#1e293b">{insurer_name or '—'}</td>
  </tr>
  <tr>
    <td style="padding:8px 0;color:#64748b">Disputed Amt</td>
    <td style="padding:8px 0;font-weight:700;color:#1a56db">{amt_str}</td>
  </tr>
</table>
{notes_section}
<p style="text-align:center;margin-top:24px">
  <a href="https://nidaanpartner.com/nidaan/admin" class="btn">Open Admin Panel</a>
</p>"""
    return await send_email(
        admin_email,
        f"New Claim #{claim_id} — {insured_name} | Nidaan Partner",
        _wrap_nidaan_template("New Claim", content),
    )


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
