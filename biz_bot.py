# =============================================================================
#  biz_bot.py — Sarathi-AI Business Technologies: Telegram CRM Bot
# =============================================================================
#
#  Multi-tenant agent-facing Telegram bot for the complete sales cycle.
#  Features:
#    - Dynamic auth (DB-based, no hardcoded user IDs)
#    - Persistent tap-friendly button menus (ReplyKeyboardMarkup)
#    - Fallback mechanics (resume incomplete reg, duplicate detection)
#    - Multi-agent per tenant, invite code system
#    - Bilingual (English / Hindi)
#
#  Commands mapped to button menus — agents tap, not type.
#
# =============================================================================

import asyncio
import html as html_mod
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from google import genai
from google.genai import types as genai_types

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton,
)
from telegram.ext import (
    Application, ApplicationHandlerStop, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

import biz_database as db
import biz_calculators as calc
import biz_whatsapp as wa
import biz_pdf as pdf
import biz_i18n as i18n
import biz_ai as ai
import biz_auth as auth_mod
import biz_email as email_mod
import biz_resilience as resilience

logger = logging.getLogger("sarathi.bot")

# Conversation states
(ONBOARD_CHOICE, ONBOARD_FIRM, ONBOARD_NAME, ONBOARD_PHONE, ONBOARD_EMAIL,
 ONBOARD_INVITE, ONBOARD_BOT_TOKEN, ONBOARD_LANG, ONBOARD_VERIFY_OTP,
 LEAD_NAME, LEAD_PHONE, LEAD_PHONE_CONFIRM, LEAD_DOB, LEAD_ANNIVERSARY,
 LEAD_CITY, LEAD_NEED, LEAD_NEED_DONE, LEAD_NOTES, LEAD_EMAIL,
 FOLLOWUP_LEAD, FOLLOWUP_TYPE, FOLLOWUP_NOTES, FOLLOWUP_DATE,
 CONVERT_LEAD, CONVERT_STAGE,
 POLICY_LEAD, POLICY_INSURER, POLICY_PLAN, POLICY_TYPE, POLICY_SI,
 POLICY_PREMIUM, POLICY_START, POLICY_RENEWAL,
 CALC_TYPE, CALC_INPUT, CALC_RESULT,
 WA_LEAD, WA_MESSAGE,
 GREET_LEAD, GREET_TYPE,
 SEARCH_QUERY,
 EDITPROFILE_CHOICE, EDITPROFILE_VALUE,
 EDITLEAD_ID, EDITLEAD_FIELD, EDITLEAD_VALUE,
 CLAIM_LEAD, CLAIM_POLICY, CLAIM_TYPE,
 CLAIM_DESC, CLAIM_HOSPITAL, CLAIM_CONFIRM,
 ONBOARD_VERIFY_EMAIL_OTP, ONBOARD_CITY,
 ONBOARD_LINK_WEB, ONBOARD_LINK_WEB_OTP,
 TEAM_EDIT_FIELD, TEAM_EDIT_VALUE,
 LOGIN_PHONE, LOGIN_OTP,
 SCAN_WAIT, SCAN_CONFIRM, SCAN_CLIENT,
 SCAN_ASK_MISSING, SCAN_SOLD_BY, POLICY_MODE) = range(66)

# Conversation timeout: 30 minutes of inactivity auto-cancels
CONV_TIMEOUT = 30 * 60  # seconds

# Super Admin phone numbers (comma-separated) — platform owner control
# Loaded lazily because biz_bot is imported before load_dotenv("biz.env") runs
_SUPERADMIN_PHONES_CACHE = None

def _get_sa_phones():
    global _SUPERADMIN_PHONES_CACHE
    if _SUPERADMIN_PHONES_CACHE is None:
        _SUPERADMIN_PHONES_CACHE = set(
            p.strip() for p in os.getenv("SUPERADMIN_PHONES", "").split(",") if p.strip()
        )
    return _SUPERADMIN_PHONES_CACHE

# Keep module-level name for backward compatibility in checks
class _SAPhones:
    """Lazy proxy for SUPERADMIN_PHONES so env is read after load_dotenv."""
    def __contains__(self, item):
        return item in _get_sa_phones()
    def __iter__(self):
        return iter(_get_sa_phones())
    def __repr__(self):
        return repr(_get_sa_phones())
    def __bool__(self):
        return bool(_get_sa_phones())

SUPERADMIN_PHONES = _SAPhones()

# Super Admin OTP session store: {phone: {"ts": timestamp, "tg_id": str}}
# Session valid for 1 hour; SA must re-authenticate after timeout
_sa_sessions = {}
SA_SESSION_TIMEOUT = 3600  # 1 hour in seconds

# Agent session expiry: 24 hours — forces re-OTP to confirm phone holder
AGENT_SESSION_TIMEOUT = 24 * 3600  # 24 hours in seconds

# ---------- Gemini AI client for Voice-to-Action ----------
_gemini_client = None

def _get_gemini():
    """Lazy-init Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        key = os.getenv("GEMINI_API_KEY")
        if key:
            _gemini_client = genai.Client(api_key=key)
            logger.info("Gemini AI client initialized for Voice-to-Action")
    return _gemini_client


# ── Voice context tracking ────────────────────────────────────────────────

def _track_voice_context(context, *, intent: str, lead_id=None, lead_name=None,
                         calc_type=None, extra=None):
    """Track what just happened so the next voice note has context."""
    if context is None:
        return
    history = context.user_data.get('voice_history') or []
    entry = {
        'intent': intent,
        'ts': time.time(),
    }
    if lead_id:
        entry['lead_id'] = lead_id
        entry['lead_name'] = lead_name or ''
        # Also update quick-access last_lead
        context.user_data['last_lead'] = {
            'lead_id': lead_id, 'name': lead_name or '', 'ts': time.time()
        }
    if calc_type:
        entry['calc_type'] = calc_type
    if extra:
        entry.update(extra)
    history.append(entry)
    # Keep last 5 actions only
    context.user_data['voice_history'] = history[-5:]


def _build_voice_context_block(context) -> str:
    """Build a context block to inject into the Gemini prompt."""
    history = context.user_data.get('voice_history') or []
    last_lead = context.user_data.get('last_lead')
    last_calc = context.user_data.get('last_calc_type')

    if not history and not last_lead and not last_calc:
        return ""

    lines = ["\n\nRECENT CONTEXT (what the agent just did — use to resolve pronouns like 'uska', 'isko', 'that lead', 'share it'):"]

    now = time.time()
    for entry in reversed(history):
        age_sec = now - entry.get('ts', 0)
        if age_sec > 600:  # Skip entries older than 10 min
            continue
        age_str = f"{int(age_sec//60)}m ago" if age_sec >= 60 else "just now"
        intent = entry.get('intent', '?')
        parts = [f"- [{age_str}] {intent}"]
        if entry.get('lead_name'):
            parts.append(f"lead: {entry['lead_name']} (#{entry.get('lead_id','')})")
        if entry.get('calc_type'):
            parts.append(f"calculator: {entry['calc_type']}")
        if entry.get('extra_info'):
            parts.append(entry['extra_info'])
        lines.append(" | ".join(parts))

    if last_lead and (now - last_lead.get('ts', 0)) < 600:
        lines.append(f"LAST LEAD REFERENCED: {last_lead.get('name','')} (#{last_lead.get('lead_id','')})")

    if last_calc:
        lines.append(f"LAST CALCULATOR USED: {last_calc}")

    lines.append("If the agent says 'uska/iska/that lead/uss client ka/share it/bhej do/send it' — they likely mean the lead or entity above.")
    lines.append("If the agent says 'edit karo/update karo/phone add karo' without a name — use LAST LEAD REFERENCED.")
    return "\n".join(lines)


_VOICE_PROMPT = """You are an AI assistant for Sarathi-AI, an Indian insurance advisor CRM.
The agent just sent a voice note. They might want to do ANY of these actions:

1. CREATE LEAD — mentioned a new prospect/client with name, phone, details
2. LOG MEETING — talked about meeting someone, what they discussed, outcome
3. UPDATE STAGE — wants to move a lead to a different pipeline stage
4. CREATE REMINDER — wants to set a reminder/follow-up for a specific date
5. ADD NOTE — wants to add a note/observation about an existing lead
6. LIST LEADS — wants to see their lead list or search a specific lead by name
7. SHOW PIPELINE — wants to see their pipeline summary / sales funnel status
8. SHOW DASHBOARD — wants to see business stats / today's numbers / overview
9. SHOW RENEWALS — wants to check upcoming policy renewals
10. SHOW TODAY — wants to know what they have today (follow-ups, birthdays, tasks)
11. SETUP FOLLOWUP — wants to schedule a follow-up with a specific lead
12. SEND WHATSAPP — wants to send a WhatsApp message to a lead
13. SEND GREETING — wants to send birthday/anniversary/thank you/festival greeting to a lead
14. EDIT LEAD — wants to update a lead's details (phone, email, city, etc.)
15. ASK AI — asking a general insurance/finance/business question (not a CRM action)
16. AI LEAD SCORE — wants AI to score/rank their leads
17. AI PITCH — wants AI to generate a sales pitch for a specific lead
18. AI FOLLOWUP SUGGEST — wants AI to suggest next best action for a lead
19. AI RECOMMEND — wants AI to recommend policies for a lead
20. OPEN CALCULATOR — wants to open/see the calculator menu
21. SELECT CALCULATOR — wants to open a SPECIFIC calculator (e.g. "SIP calculator chalao")
22. CALC COMPUTE — wants to CALCULATE with specific numbers. May include all params in one go (e.g. "calculate SIP for 10000 monthly, 20 years, 12% return") and optionally send result to a lead
23. SEND CALC RESULT — wants to SEND/SHARE/FORWARD a previously calculated result to a lead (e.g. "Ramesh ko bhej do", "send to Rajesh", "share it with client"). Use this when NO calculator name or numbers are mentioned, just sending/sharing intent with a lead name.
24. SHOW TEAM — wants to see their team members, team stats, manage team (e.g. "meri team dikhao", "show my team", "team members")
25. SHOW PLANS — wants to see subscription plans, pricing, current plan status (e.g. "plans dikhao", "show plans", "pricing")
26. SHOW SETTINGS — wants to open settings menu (e.g. "settings kholiye", "show settings", "open settings")
27. SA PANEL — super admin wants to open the admin panel (e.g. "admin panel", "SA panel", "super admin")
28. CONFIRM ACTION — agent is confirming/approving a previously shown action (e.g. "yes", "haan", "create karo", "ban do", "confirm", "yes create lead", "ok proceed", "theek hai"). This is NOT a new action — they are saying YES to something already shown.
29. LOG PAYMENT — record a premium payment received from a lead (cash/upi/cheque/bank/online/card) e.g. "Ramesh ne 25000 UPI se pay kar diya", "got 18000 from Suresh in cash"
30. LOG CALL — log a phone call with a lead with optional follow-up date e.g. "Spoke to Priya, she'll decide by Friday", "Aakash se baat hui, kal phir call karna hai"
31. ADD POLICY — record a sold policy under a lead (auto-marks lead closed_won) e.g. "Sold HDFC term plan to Rajesh, premium 15000 annual", "Mehta ko LIC Jeevan Anand bech di"
32. SCHEDULE MEETING — book an in-person/online meeting with a lead at a specific date/time e.g. "Schedule meeting with Suresh tomorrow 4pm at his office"
33. MARK RENEWAL DONE — mark a policy as renewed e.g. "Renewal done for Sharma's HDFC policy", "Verma ki star health policy renew ho gayi"
34. LOG CLAIM — record a new claim filed by a lead e.g. "Mr Kumar filed claim for accident at Apollo Hospital, amount 50000", "Gupta ka health claim laga"
35. GENERAL — just a random comment, unclear intent

TASK: Transcribe the voice note, detect the INTENT, and extract relevant data.

Return ONLY valid JSON (no markdown, no backticks):
{
  "transcript": "<full transcription — preserve the natural conversational tone>",
  "intent": "<one of: create_lead, log_meeting, update_stage, create_reminder, add_note, list_leads, show_pipeline, show_dashboard, show_renewals, show_today, setup_followup, send_whatsapp, send_greeting, edit_lead, ask_ai, ai_lead_score, ai_pitch, ai_followup_suggest, ai_recommend, open_calculator, select_calculator, calc_compute, send_calc_result, show_team, show_plans, show_settings, sa_panel, confirm_action, log_payment, log_call, add_policy, schedule_meeting, mark_renewal_done, log_claim, general>",
  "confidence": "<high, medium, or low — how sure you are about the intent>",
  "language_detected": "<en, hi, or hinglish>",
  "has_abuse": false,

  // For create_lead:
  "name": "<lead name or null>",
  "phone": "<10-digit Indian mobile or null>",
  "need_type": "<health/term/endowment/ulip/child/retirement/motor/investment/nps/general or null>",
  "city": "<city or null>",
  "budget": "<monthly budget number or null>",

  // For log_meeting / update_stage / add_note / setup_followup / send_whatsapp / send_greeting / edit_lead / ai_pitch / ai_followup_suggest / ai_recommend:
  "lead_name": "<name of existing lead mentioned, or null>",
  "lead_phone": "<phone of existing lead if mentioned, or null>",

  // For log_meeting:
  "meeting_summary": "<what was discussed, key points, outcome — keep it conversational>",
  "meeting_channel": "<in_person/phone/video/whatsapp or null>",

  // For update_stage:
  "new_stage": "<prospect/contacted/pitched/proposal_sent/negotiation/closed_won/closed_lost or null>",

  // For create_reminder / setup_followup:
  "reminder_message": "<what to remind about>",
  "reminder_date": "<YYYY-MM-DD>",
  "reminder_time": "<HH:MM in 24hr IST format, e.g. 16:00 for 4 PM, or null if not mentioned>",
  "task_assignee": "<name of person to assign the task to, or 'self' if for themselves, or null>",

  // For add_note:
  "note_text": "<the note to add>",

  // For list_leads:
  "search_query": "<name or phone to search for, or null for all leads>",

  // For send_whatsapp:
  "wa_message": "<the message to send via WhatsApp, or null>",

  // For send_greeting:
  "greeting_type": "<birthday/anniversary/thank_you/festival or null>",

  // For edit_lead:
  "edit_field": "<name/phone/email/city/need_type/notes or null>",
  "edit_value": "<new value for the field, or null>",

  // For ask_ai:
  "ai_question": "<the question to answer>",

  // For select_calculator / calc_compute:
  "calc_type": "<inflation/hlv/retirement/emi/health/sip/mfsip/ulip/nps/stepupsip/swp/delaycost or null>",

  // For calc_compute — extract ALL mentioned numeric parameters:
  "calc_params": {
    // Inflation: amount (monthly expense), rate (inflation %), years
    // HLV: monthly_expense, loans, children, existing_cover
    // Retirement: current_age, retire_age, life_exp, monthly_expense, inflation, pre_return, post_return
    // EMI: premium (annual), years, gst (%), cibil_disc (%), down_pct (%)
    // Health: age, family (1A/2A/2A+1C/2A+2C/2A+3C), city (metro/tier1/tier2/rural), income, existing
    // SIP: amount, years, return_rate (%)
    // MF SIP: goal, years, return_rate (%), existing
    // ULIP: annual_inv, years, ulip_return (%), mf_return (%)
    // NPS: monthly, current_age, retire_age, return_rate (%), tax_bracket (%)
    // Only include params mentioned in the voice note. Use null for unmentioned params.
  },
  "send_to_lead": "<lead name to send result to, or null>",

  // Shared:
  "follow_up": "<YYYY-MM-DD if a follow-up date is mentioned, else null>",
  "notes": "<any extra details or context>",

  // For log_payment:
  "amount": "<payment amount as number or null>",
  "payment_method": "<cash/upi/cheque/bank/online/card or null>",

  // For add_policy:
  "insurer": "<insurance company name or null>",
  "plan_name": "<plan/product name or null>",
  "policy_type": "<health/term/endowment/ulip/child/retirement/motor/investment/nps/life or null>",
  "policy_number": "<policy number or null>",
  "sum_insured": "<sum insured as number or null>",
  "premium": "<premium amount as number or null>",
  "premium_mode": "<monthly/quarterly/half_yearly/annual/single or null>",

  // For schedule_meeting:
  "meeting_date": "<YYYY-MM-DD or null>",
  "meeting_time": "<HH:MM 24h or null>",
  "meeting_location": "<location or 'online' or null>",

  // For log_claim:
  "claim_type": "<health/motor/life/accident/other or null>",
  "claim_amount": "<claim amount as number or null>",
  "incident_date": "<YYYY-MM-DD or null>",
  "hospital_name": "<hospital/garage/place name or null>"
}

RULES:
- Today's date is """ + datetime.now().strftime('%Y-%m-%d (%A)') + """
- Convert relative dates: "kal" / "tomorrow" → next day, "Friday" / "shukravar" → nearest future Friday
- "agle hafte" / "next week" → next Monday, "mahine baad" / "next month" → 1st of next month
- Convert time references: "4 baje" / "4pm" / "dopahar 4" → 16:00, "subah 10" / "10 AM" → 10:00, "sham 6" → 18:00
- All times should be in IST (India Standard Time) 24-hour format
- IMPORTANT: For setup_followup and create_reminder intents, ALWAYS extract reminder_time if ANY time is mentioned. Even partial mentions like "4 baje", "at 4", "tomorrow 4 pm", "sham ko" (→ 18:00) MUST populate reminder_time. Never leave it null if a time was spoken.
- Task assignment: If the speaker says "for me" / "I will" / "mujhe" / "mere liye" / "main karunga", set task_assignee="self". If they mention another person's name like "Rahul ko assign karo" / "tell Rahul to", set task_assignee to that person's name. Otherwise leave null.
- The audio will be in Hindi, English, or Hinglish (mixed). Handle ALL naturally.
- Detect INTENT from context:
  - "Ramesh ji se mila aaj" → log_meeting
  - "naya client aaya" → create_lead
  - "meri leads dikhao" / "show my leads" / "lead list" → list_leads
  - "Ramesh ka detail dikhao" / "search Ramesh" → list_leads (with search_query)
  - "pipeline dikhao" / "funnel kya hai" / "show pipeline" → show_pipeline
  - "dashboard dikhao" / "stats batao" / "how am I doing" → show_dashboard
  - "renewals dikhao" / "koi renewal aane wala hai" → show_renewals
  - "aaj kya hai" / "today ka kya plan" / "what do I have today" → show_today
  - "Rajesh ko kal follow up karna hai" / "setup followup with Rajesh" → setup_followup
  - "Ramesh ko WhatsApp bhejo" / "send message to Rajesh" → send_whatsapp
  - "Ramesh ko birthday wish bhejo" → send_greeting (greeting_type=birthday)
  - "Ramesh ka phone number change karo" → edit_lead
  - "best term plan kya hai" / "what insurance for 30 year old" → ask_ai
  - "lead scoring karo" / "score my leads" → ai_lead_score
  - "Rajesh ke liye pitch banao" → ai_pitch
  - "Rajesh ke saath kya karna chahiye" → ai_followup_suggest
  - "Rajesh ko kaunsi policy recommend karu" → ai_recommend
  - "calculator dikhao" / "open calculator" / "calculators" → open_calculator
  - "SIP calculator open karo" / "EMI calculator chalao" → select_calculator (calc_type=sip/emi)
  - "inflation calculator" / "retirement planner open karo" → select_calculator
  - "calculate SIP 10000 monthly 20 years 12 percent return" → calc_compute (calc_type=sip, extract params)
  - "EMI calculate karo 50000 premium 5 saal 18% GST" → calc_compute (calc_type=emi, extract params)
  - "retirement plan banao age 35 retire 60 80 saal life 50000 expense" → calc_compute
  - "inflation calculator — 50000 monthly 7% for 15 years" → calc_compute (calc_type=inflation)
  - "SIP calculate karo aur Rajesh ko bhej do" → calc_compute with send_to_lead=Rajesh
  - "HLV calculate 75000 expense 20 lakh loan 10 lakh children 5 lakh cover" → calc_compute
  - "Ramesh ko bhej do" / "result share karo Rajesh ko" / "send to client" → send_calc_result (with send_to_lead=Ramesh/Rajesh)
  - "ye result Pandey ji ko bhejiye" / "share this with Suresh" → send_calc_result
  - When agent mentions BOTH calculator type AND numbers → calc_compute (extract all params)
  - When agent ONLY mentions calculator name without numbers → select_calculator
  - When agent just says "calculator" without specifying which → open_calculator
  - When agent says "send/bhej/share" + lead name WITHOUT mentioning any calculator or numbers → send_calc_result
  - "meri team dikhao" / "show my team" / "team members batao" → show_team
  - "plans dikhao" / "show plans" / "pricing" / "kaunsa plan hai" → show_plans
  - "settings kholiye" / "show settings" / "open settings" → show_settings
  - "admin panel" / "SA panel" / "super admin panel" → sa_panel
  - "Ramesh ne 25000 pay kiya" / "got premium of 18000 from Suresh" / "X paid via UPI" / "paisa aaya" → log_payment (extract amount + payment_method)
  - "Spoke to Priya by Friday" / "Aakash se baat hui kal call karna" / "phone par baat hui" → log_call (set lead_name, note_text=summary, follow_up if date mentioned). NOTE: if user mentions a clear MEETING (in person), prefer log_meeting; for phone calls prefer log_call
  - "Sold HDFC Click 2 Protect to Rajesh premium 15000 annual" / "Mehta ko LIC bech di" / "policy sold" → add_policy (extract insurer, plan_name, policy_type, sum_insured, premium, premium_mode)
  - "Schedule meeting with Suresh tomorrow 4pm at office" / "Patel se parso 3 baje milna hai online" → schedule_meeting (extract meeting_date, meeting_time, meeting_location). NOTE: this is for a FUTURE meeting; for a meeting that already happened, use log_meeting
  - "Renewal done for Sharma's HDFC policy" / "Verma ki policy renew ho gayi" → mark_renewal_done (lead_name + optional insurer)
  - "Mr Kumar filed claim at Apollo Hospital amount 50000" / "Gupta ka health claim laga AIIMS mein" / "accident claim register" → log_claim (extract claim_type, claim_amount, incident_date, hospital_name)
  - Convert Hindi numbers: "das hazaar" → 10000, "pachas hazaar" → 50000, "bees saal" → 20
  - "lakh" = 100000, "crore" = 10000000
- For Indian names, preserve proper capitalization (Ramesh Kumar, not ramesh kumar)
- Extract Indian phone numbers (10 digits starting with 6-9)
- If someone says "stage badlo" / "move to pitched" → update_stage
- If someone says "yaad dilana" / "remind me" → create_reminder
- "has_abuse" = true ONLY if voice contains profanity, slurs, hate speech, threats, or derogatory language
- "confidence" scoring: high = clear intent with enough data to act, medium = intent is likely but some data is missing or ambiguous, low = unclear what the agent wants
- CONTEXT RESOLUTION: If the agent uses pronouns like "uska", "isko", "that lead", "uss client ka", "share it", "bhej do", "send it" — check the RECENT CONTEXT section below the prompt to resolve which lead/entity they mean. Fill in lead_name/lead_phone from context if the agent doesn't repeat the name.
- Map Hindi stage words: "contact kiya" → contacted, "pitch kiya" → pitched, "proposal bheja" → proposal_sent, "deal pakki" → closed_won, "deal nahi hua" → closed_lost
- Return ONLY the JSON object, nothing else"""

# ---------- "Just Talk" text-to-action prompt ----------
_JUST_TALK_PROMPT = """You are the AI engine for Sarathi-AI, an Indian insurance advisor CRM.
The agent just typed a natural language message instead of using bot commands.
Understand what they want and extract the intent + data.

POSSIBLE INTENTS:
1. CREATE LEAD — mentions a new prospect/client (name, phone, details)
2. LOG MEETING — describes a meeting they had with someone
3. UPDATE STAGE — wants to change a lead's pipeline stage
4. CREATE REMINDER — wants to set a reminder/follow-up for a date
5. ADD NOTE — wants to add a note about an existing lead
6. ASK_AI — asking a general insurance/business question (not an action)
7. OPEN CALCULATOR — wants to see the calculator menu (e.g. "calculator dikhao", "open calculator")
8. SELECT CALCULATOR — wants to open a specific calculator (e.g. "SIP calculator open karo")
9. CALC COMPUTE — wants to calculate with specific numbers (e.g. "calculate SIP 10000 monthly 20 years 12% return")
10. SEND CALC RESULT — wants to send/share a previously calculated result to a lead (e.g. "Ramesh ko bhej do", "send to client")
11. SHOW TEAM — wants to see team members, team stats (e.g. "meri team dikhao", "show my team")
12. SHOW PLANS — wants to see subscription plans, pricing (e.g. "plans dikhao", "show plans")
13. SHOW SETTINGS — wants to open settings (e.g. "settings kholiye", "open settings")
14. SA PANEL — super admin panel access (e.g. "admin panel", "SA panel")
15. LOG PAYMENT — record a premium payment received (e.g. "Ramesh ne 25000 pay kiya", "got premium 18000 cash")
16. LOG CALL — log a phone call with a lead (e.g. "spoke to Priya, decide by Friday")
17. ADD POLICY — record a sold policy (e.g. "Sold HDFC term to Rajesh, premium 15000 annual")
18. SCHEDULE MEETING — book a future meeting (e.g. "Meeting with Suresh tomorrow 4pm")
19. MARK RENEWAL DONE — mark a policy as renewed (e.g. "Renewal done for Sharma's HDFC")
20. LOG CLAIM — record a new claim filed (e.g. "Mr Kumar claim at Apollo 50000")
21. GENERAL — unclear, random chat, or greeting

AGENT'S MESSAGE: "{message}"

Return ONLY valid JSON:
{{
  "transcript": "<the original message, cleaned up>",
  "intent": "<one of: create_lead, log_meeting, update_stage, create_reminder, add_note, ask_ai, open_calculator, select_calculator, calc_compute, send_calc_result, show_team, show_plans, show_settings, sa_panel, log_payment, log_call, add_policy, schedule_meeting, mark_renewal_done, log_claim, general>",
  "language_detected": "<en, hi, or hinglish>",
  "has_abuse": false,
  "confidence": "<high, medium, or low>",

  "name": "<lead name or null>",
  "phone": "<10-digit Indian mobile or null>",
  "need_type": "<health/term/endowment/ulip/child/retirement/motor/investment/nps/general or null>",
  "city": "<city or null>",
  "budget": "<monthly budget number or null>",

  "lead_name": "<name of existing lead mentioned, or null>",
  "lead_phone": "<phone of existing lead if mentioned, or null>",

  "meeting_summary": "<meeting details or null>",
  "meeting_channel": "<in_person/phone/video/whatsapp or null>",

  "new_stage": "<prospect/contacted/pitched/proposal_sent/negotiation/closed_won/closed_lost or null>",

  "reminder_message": "<what to remind about or null>",
  "reminder_date": "<YYYY-MM-DD or null>",

  "note_text": "<the note or null>",

  "ai_question": "<the question to answer, if ask_ai intent, or null>",

  "calc_type": "<inflation/hlv/retirement/emi/health/sip/mfsip/ulip/nps/stepupsip/swp/delaycost or null — for calculator intents>",
  "calc_params": {{}},
  "send_to_lead": "<lead name to send calc result to, or null>",

  "follow_up": "<YYYY-MM-DD if mentioned, else null>",
  "notes": "<any extra details>",

  "amount": "<payment amount or null>",
  "payment_method": "<cash/upi/cheque/bank/online/card or null>",
  "insurer": "<insurer or null>",
  "plan_name": "<plan name or null>",
  "policy_type": "<health/term/endowment/ulip/child/retirement/motor/investment/nps/life or null>",
  "policy_number": "<policy number or null>",
  "sum_insured": "<sum insured or null>",
  "premium": "<premium or null>",
  "premium_mode": "<monthly/quarterly/half_yearly/annual/single or null>",
  "meeting_date": "<YYYY-MM-DD or null>",
  "meeting_time": "<HH:MM 24h or null>",
  "meeting_location": "<location or null>",
  "claim_type": "<health/motor/life/accident/other or null>",
  "claim_amount": "<claim amount or null>",
  "incident_date": "<YYYY-MM-DD or null>",
  "hospital_name": "<hospital/place or null>"
}}

RULES:
- "Ramesh ne 25000 pay kiya" / "got premium 18000 cash" / "paisa aaya" → log_payment (extract amount + payment_method)
- "spoke to Priya by Friday" / "phone par baat hui" → log_call (lead_name + note_text + optional follow_up)
- "Sold HDFC Click 2 Protect to Rajesh, premium 15000 annual" / "Mehta ko LIC bech di" → add_policy
- "Meeting with Suresh tomorrow 4pm at office" / "kal 3 baje milna hai" (FUTURE) → schedule_meeting
- "Renewal done for Sharma's HDFC" / "Verma policy renew ho gayi" → mark_renewal_done
- "Mr Kumar claim at Apollo 50000" / "accident claim laga" → log_claim
- Today's date is {today}
- Convert relative dates: "kal"/"tomorrow" → next day, "Friday"/"shukravar" → nearest future Friday
- "agle hafte"/"next week" → next Monday, "mahine baad"/"next month" → 1st of next month
- Messages may be Hindi, English, or Hinglish. Handle ALL naturally.
- Detect INTENT from context — e.g. "Ramesh ji se mila aaj" → log_meeting, "naya client aaya" → create_lead
- If message is a question about insurance/sales/products → ask_ai
- If message is just "hi", "hello", greeting, or casual → general
- "calculator", "calc", "calculators dikhao" → open_calculator
- "SIP calculator", "EMI calculator open karo", "inflation calculator" → select_calculator (set calc_type)
- "calculate SIP 10000 monthly 20 years 12% return" → calc_compute (extract calc_type + calc_params)
- When both calculator type AND numbers mentioned → calc_compute; only name → select_calculator; just "calculator" → open_calculator
- "Ramesh ko bhej do" / "share with client" / "result send karo" → send_calc_result (set send_to_lead)
- When agent says send/bhej/share + lead name WITHOUT calculator name or numbers → send_calc_result
- "meri team dikhao" / "show my team" / "team members" → show_team
- "plans dikhao" / "show plans" / "pricing" → show_plans
- "settings kholiye" / "show settings" / "open settings" → show_settings
- "admin panel" / "SA panel" / "super admin" → sa_panel
- For Indian names, preserve proper capitalization
- Extract Indian phone numbers (10 digits starting with 6-9)
- Map Hindi stage words: "contact kiya" → contacted, "pitch kiya" → pitched, "proposal bheja" → proposal_sent
- "has_abuse" = true ONLY for profanity, slurs, threats, or derogatory language
- "confidence": "high" = clearly one intent, "medium" = likely but ambiguous, "low" = unclear
- Return ONLY the JSON object, nothing else"""

# ---------- Claims document checklists (bilingual) ----------
_CLAIM_DOCS = {
    "en": {
        "health": [
            "📋 Duly filled & signed Claim Form",
            "🏥 Hospital Discharge Summary",
            "💊 All medical bills & receipts (original)",
            "🧪 Investigation reports (blood, X-ray, MRI, etc.)",
            "💳 Pre-auth letter (if cashless claim)",
            "🪪 Policy copy & ID proof (Aadhaar/PAN)",
            "🏦 Cancelled cheque / bank details",
            "📄 Doctor's prescription & case papers",
        ],
        "term": [
            "📋 Duly filled Death Claim Form",
            "⚰️ Death Certificate (original/attested)",
            "👮 FIR / Postmortem Report (if applicable)",
            "🪪 Policy copy & nominee's ID proof",
            "🏦 Nominee's cancelled cheque / bank details",
            "📄 Last medical records of deceased",
            "🏥 Hospital records (if death in hospital)",
        ],
        "motor": [
            "📋 Duly filled Motor Claim Form",
            "🚗 RC copy (Registration Certificate)",
            "🪪 Driving License of driver at time of accident",
            "👮 FIR / Police report (for theft/third-party)",
            "📸 Photos of damage (before repair)",
            "🔧 Repair estimate from authorized garage",
            "🧾 Original repair bills & payment receipts",
            "📄 Policy copy",
        ],
        "general": [
            "📋 Duly filled Claim Form",
            "🪪 Policy copy & ID proof",
            "📄 Supporting documents for the claim",
            "🏦 Cancelled cheque / bank details",
            "📸 Photos/evidence of loss or damage",
            "📝 Detailed description of the incident",
        ],
    },
    "hi": {
        "health": [
            "📋 विधिवत भरा और हस्ताक्षरित क्लेम फॉर्म",
            "🏥 अस्पताल डिस्चार्ज सारांश",
            "💊 सभी मेडिकल बिल और रसीदें (मूल)",
            "🧪 जांच रिपोर्ट (ब्लड, एक्स-रे, MRI आदि)",
            "💳 प्री-ऑथ लेटर (कैशलेस क्लेम के लिए)",
            "🪪 पॉलिसी कॉपी और पहचान पत्र (आधार/PAN)",
            "🏦 कैंसल चेक / बैंक विवरण",
            "📄 डॉक्टर का प्रिस्क्रिप्शन और केस पेपर",
        ],
        "term": [
            "📋 विधिवत भरा मृत्यु क्लेम फॉर्म",
            "⚰️ मृत्यु प्रमाण पत्र (मूल/प्रमाणित)",
            "👮 FIR / पोस्टमार्टम रिपोर्ट (यदि लागू हो)",
            "🪪 पॉलिसी कॉपी और नॉमिनी का पहचान पत्र",
            "🏦 नॉमिनी का कैंसल चेक / बैंक विवरण",
            "📄 मृतक के अंतिम मेडिकल रिकॉर्ड",
            "🏥 अस्पताल रिकॉर्ड (यदि अस्पताल में मृत्यु)",
        ],
        "motor": [
            "📋 विधिवत भरा मोटर क्लेम फॉर्म",
            "🚗 RC कॉपी (रजिस्ट्रेशन सर्टिफिकेट)",
            "🪪 दुर्घटना समय ड्राइवर का ड्राइविंग लाइसेंस",
            "👮 FIR / पुलिस रिपोर्ट (चोरी/थर्ड-पार्टी के लिए)",
            "📸 नुकसान की फोटो (मरम्मत से पहले)",
            "🔧 अधिकृत गैराज से मरम्मत अनुमान",
            "🧾 मूल मरम्मत बिल और भुगतान रसीदें",
            "📄 पॉलिसी कॉपी",
        ],
        "general": [
            "📋 विधिवत भरा क्लेम फॉर्म",
            "🪪 पॉलिसी कॉपी और पहचान पत्र",
            "📄 क्लेम के लिए सहायक दस्तावेज़",
            "🏦 कैंसल चेक / बैंक विवरण",
            "📸 नुकसान की फोटो/सबूत",
            "📝 घटना का विस्तृत विवरण",
        ],
    },
}

def _get_claim_docs(claim_type: str, lang: str = 'en') -> list:
    """Get claim documents for a type in the given language."""
    lang_docs = _CLAIM_DOCS.get(lang, _CLAIM_DOCS['en'])
    return lang_docs.get(claim_type, lang_docs['general'])

# ---------- per-user rate limiter (in-memory) ----------
_user_cmd_timestamps: dict[str, list[float]] = {}  # {user_id: [ts, ...]}
_RATE_LIMIT_MAX = 30   # max commands per window
_RATE_LIMIT_WINDOW = 60  # window in seconds

def _rate_limited(user_id: str) -> bool:
    """Return True if user has exceeded the per-user bot command rate limit."""
    now = time.time()
    times = _user_cmd_timestamps.get(user_id, [])
    # Prune old entries outside the window
    times = [t for t in times if now - t < _RATE_LIMIT_WINDOW]
    if len(times) >= _RATE_LIMIT_MAX:
        _user_cmd_timestamps[user_id] = times
        return True
    times.append(now)
    _user_cmd_timestamps[user_id] = times
    return False

# ---------- validation helpers ----------
_PHONE_RE = re.compile(r'^[6-9]\d{9}$')  # Indian 10-digit mobile

def _valid_phone(text: str) -> str | None:
    """Return cleaned 10-digit phone or None if invalid."""
    digits = re.sub(r'[\s\-\+]', '', text)
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]  # strip country code
    if digits.startswith('0') and len(digits) == 11:
        digits = digits[1:]  # strip leading 0
    return digits if _PHONE_RE.match(digits) else None


_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

def _valid_email(text: str) -> str | None:
    """Return lowercased email or None if invalid."""
    email = text.strip().lower()
    return email if _EMAIL_RE.match(email) else None


# Set of known persistent-menu button labels (EN + HI) for detecting
# accidental menu taps during conversation flows.
_MENU_LABELS_ALL = {
    "➕ Add Lead", "➕ लीड जोड़ें",
    "📊 Pipeline", "📊 पाइपलाइन",
    "📋 Leads", "📋 लीड्स",
    "📋 My Leads", "📋 मेरी लीड्स",
    "📞 Follow-up", "📞 फॉलो-अप",
    "🧮 Calculator", "🧮 कैलकुलेटर",
    "🔄 Renewals", "🔄 रिन्यूअल",
    "🤖 AI Tools", "🤖 AI टूल्स",
    "📈 Dashboard", "📈 डैशबोर्ड",
    "⚙️ Settings", "⚙️ सेटिंग्स",
    "👥 Team", "👥 टीम",
    "🌐 Language", "🌐 भाषा बदलें",
    "🤝 Partner & Earn", "🤝 पार्टनर और कमाएं",
}
_MENU_LABELS_NORM = {lbl.translate(str.maketrans("", "", "\ufe0e\ufe0f"))
                     for lbl in _MENU_LABELS_ALL}
_MENU_BUTTONS = _MENU_LABELS_ALL | _MENU_LABELS_NORM

def _is_menu_button(text: str) -> bool:
    """Return True if text matches a known persistent-menu button label."""
    return text.strip().translate(str.maketrans("", "", "\ufe0e\ufe0f")) in _MENU_BUTTONS


# =============================================================================
#  PERSISTENT BUTTON MENU
# =============================================================================

# Helper: variation-selector-safe button text filter
_VS_TABLE = str.maketrans("", "", "\ufe0e\ufe0f")

def _btn_filter(*labels):
    """Create a MessageFilter matching any of the given button labels,
    stripping Unicode variation selectors (U+FE0E/U+FE0F) for robustness."""
    normed = {lbl.translate(_VS_TABLE) for lbl in labels}

    class _BtnFilter(filters.MessageFilter):
        def filter(self, message):
            if not message.text:
                return False
            return message.text.strip().translate(_VS_TABLE) in normed

    return _BtnFilter()


def _main_menu_keyboard(lang: str = "en", role: str = "agent", plan: str = "trial", agent: dict = None) -> ReplyKeyboardMarkup:
    """Build the compact persistent keyboard (Hybrid Approach C).
    Shows only 3 most-used buttons + ☰ Menu for everything else.
    Owner/Admin: Add Lead | Pipeline | ☰ Menu
    Agent:       Add Lead | My Leads | ☰ Menu"""
    if agent:
        role = agent.get('role', 'agent')
        plan = agent.get('_plan', agent.get('plan', 'trial'))
    is_owner = role in ('owner', 'admin')

    if lang == "hi":
        if is_owner:
            keyboard = [[KeyboardButton("➕ लीड जोड़ें"), KeyboardButton("📊 पाइपलाइन"), KeyboardButton("☰ मेनू")]]
        else:
            keyboard = [[KeyboardButton("➕ लीड जोड़ें"), KeyboardButton("📋 मेरी लीड्स"), KeyboardButton("☰ मेनू")]]
    else:
        if is_owner:
            keyboard = [[KeyboardButton("➕ Add Lead"), KeyboardButton("📊 Pipeline"), KeyboardButton("☰ Menu")]]
        else:
            keyboard = [[KeyboardButton("➕ Add Lead"), KeyboardButton("📋 My Leads"), KeyboardButton("☰ Menu")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True,
                                is_persistent=True)


def _full_menu_inline(lang: str = "en", role: str = "agent", plan: str = "trial") -> InlineKeyboardMarkup:
    """Build the expanded inline menu shown when user taps ☰ Menu.
    Role & plan-aware: agents see fewer options, solo plan hides team features."""
    is_owner = role in ('owner', 'admin')
    has_team = plan in ('team', 'enterprise')
    has_enterprise = plan == 'enterprise'

    if lang == "hi":
        keyboard = [
            [InlineKeyboardButton("📋 लीड्स", callback_data="menu_leads"),
             InlineKeyboardButton("📞 फॉलो-अप", callback_data="menu_followup")],
            [InlineKeyboardButton("✅ मेरे टास्क", callback_data="menu_mytasks"),
             InlineKeyboardButton("🔄 रिन्यूअल", callback_data="menu_renewals")],
            [InlineKeyboardButton("🧮 कैलकुलेटर", callback_data="menu_calc"),
             InlineKeyboardButton("📈 डैशबोर्ड", callback_data="menu_dashboard")],
            [InlineKeyboardButton("⚙️ सेटिंग्स", callback_data="menu_settings")],
        ]
        keyboard.append([InlineKeyboardButton("🤖 AI टूल्स", callback_data="menu_ai"),
                         InlineKeyboardButton("📸 स्कैन", callback_data="menu_scan")])
        if is_owner and has_team:
            keyboard.append([InlineKeyboardButton("👥 टीम", callback_data="menu_team"),
                             InlineKeyboardButton("💳 प्लान्स", callback_data="menu_plans")])
        elif is_owner:
            keyboard.append([InlineKeyboardButton("💳 प्लान्स", callback_data="menu_plans")])
        if is_owner and has_enterprise:
            keyboard.append([InlineKeyboardButton("🛡️ एडमिन कंट्रोल", callback_data="menu_admin")])
        keyboard.append([InlineKeyboardButton("🤝 पार्टनर और कमाएं", callback_data="menu_partner")])
        keyboard.append([InlineKeyboardButton("🌐 भाषा बदलें", callback_data="menu_lang"),
                         InlineKeyboardButton("❓ मदद", callback_data="menu_help")])
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Leads", callback_data="menu_leads"),
             InlineKeyboardButton("📞 Follow-up", callback_data="menu_followup")],
            [InlineKeyboardButton("✅ My Tasks", callback_data="menu_mytasks"),
             InlineKeyboardButton("🔄 Renewals", callback_data="menu_renewals")],
            [InlineKeyboardButton("🧮 Calculator", callback_data="menu_calc"),
             InlineKeyboardButton("📈 Dashboard", callback_data="menu_dashboard")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")],
        ]
        keyboard.append([InlineKeyboardButton("🤖 AI Tools", callback_data="menu_ai"),
                         InlineKeyboardButton("📸 Scan", callback_data="menu_scan")])
        if is_owner and has_team:
            keyboard.append([InlineKeyboardButton("👥 Team", callback_data="menu_team"),
                             InlineKeyboardButton("💳 Plans", callback_data="menu_plans")])
        elif is_owner:
            keyboard.append([InlineKeyboardButton("💳 Plans", callback_data="menu_plans")])
        if is_owner and has_enterprise:
            keyboard.append([InlineKeyboardButton("🛡️ Admin Controls", callback_data="menu_admin")])
        keyboard.append([InlineKeyboardButton("🤝 Partner & Earn", callback_data="menu_partner")])
        keyboard.append([InlineKeyboardButton("🌐 Language", callback_data="menu_lang"),
                         InlineKeyboardButton("❓ Help", callback_data="menu_help")])
    return InlineKeyboardMarkup(keyboard)


def _settings_keyboard(lang: str = "en", role: str = "agent", plan: str = "trial") -> InlineKeyboardMarkup:
    """Build the settings inline keyboard (role & plan aware)."""
    is_owner = role in ('owner', 'admin')
    has_team = plan in ('team', 'enterprise')

    if lang == "hi":
        keyboard = [
            [InlineKeyboardButton("✏️ प्रोफ़ाइल संपादित करें", callback_data="settings_editprofile")],
            [InlineKeyboardButton("🌐 Language / भाषा", callback_data="settings_lang")],
            [InlineKeyboardButton("🌐 वेब लॉगिन", callback_data="settings_weblogin")],
        ]
        if is_owner and has_team:
            keyboard.append([InlineKeyboardButton("👥 टीम / एजेंट आमंत्रित करें", callback_data="settings_team")])
            keyboard.append([InlineKeyboardButton("👁 एजेंट व्यू प्रीव्यू", callback_data="settings_testmode")])
        keyboard.append([InlineKeyboardButton("📊 AI उपयोग", callback_data="settings_ai_usage")])
        keyboard.append([InlineKeyboardButton("🔓 लॉगआउट", callback_data="settings_logout")])
        keyboard.append([InlineKeyboardButton("ℹ️ मदद", callback_data="settings_help")])
    else:
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Profile", callback_data="settings_editprofile")],
            [InlineKeyboardButton("🌐 Language / भाषा", callback_data="settings_lang")],
            [InlineKeyboardButton("🌐 Web Login", callback_data="settings_weblogin")],
        ]
        if is_owner and has_team:
            keyboard.append([InlineKeyboardButton("👥 Team / Invite Agent", callback_data="settings_team")])
            keyboard.append([InlineKeyboardButton("👁 Preview Agent View", callback_data="settings_testmode")])
        keyboard.append([InlineKeyboardButton("📊 AI Usage", callback_data="settings_ai_usage")])
        keyboard.append([InlineKeyboardButton("🔓 Logout", callback_data="settings_logout")])
        keyboard.append([InlineKeyboardButton("ℹ️ Help", callback_data="settings_help")])
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
#  SECURITY — Dynamic DB-based auth (no hardcoded user IDs)
# =============================================================================

def _start_session(context):
    """Mark session start time for 24hr expiry tracking."""
    context.user_data['_session_start'] = time.time()

def registered(func):
    """Decorator: require agent to be registered in DB.
    If not registered, prompt /start. No hardcoded user lists."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        _lang = context.user_data.get('lang', 'en')
        # Determine reply target: callback query or direct message
        _msg = update.message
        if _msg is None and update.callback_query:
            _msg = update.callback_query.message
        # Per-user rate limiting
        if _rate_limited(user_id):
            if _msg:
                await _msg.reply_text(i18n.t(_lang, "rate_limited"))
            return ConversationHandler.END
        agent = await db.get_agent(user_id)
        if not agent:
            if _msg:
                await _msg.reply_text(
                    i18n.t(_lang, "not_registered_yet"),
                    reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        # Check agent is active (not deactivated by owner)
        if not agent.get('is_active', 1):
            _lang = agent.get('lang', _lang)
            if _msg:
                await _msg.reply_text(
                    i18n.t(_lang, "account_deactivated"),
                    reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        # 24-hour session expiry: force re-OTP if session expired
        session_start = context.user_data.get('_session_start', 0)
        if session_start and (time.time() - session_start) > AGENT_SESSION_TIMEOUT:
            context.user_data.clear()
            _lang = agent.get('lang', _lang)
            if _msg:
                await _msg.reply_text(
                    "🔐 <b>Session expired</b> (24 hours)\n\n"
                    "For security, please verify your identity.\n"
                    "Type /start to login again with OTP.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        # Touch activity timestamp (non-blocking)
        try:
            if agent.get('agent_id'):
                asyncio.get_event_loop().create_task(
                    db.touch_agent_activity(agent['agent_id']))
        except Exception:
            pass
        # Check subscription is active
        if agent.get('tenant_id'):
            active = await db.check_subscription_active(agent['tenant_id'])
            if not active:
                _lang = agent.get('lang', _lang)
                if _msg:
                    await _msg.reply_text(
                        i18n.t(_lang, "subscription_expired"),
                        reply_markup=ReplyKeyboardRemove())
                return ConversationHandler.END
        # Tenant isolation: if this is a per-tenant bot, verify agent belongs
        bot_tenant_id = context.bot_data.get('_tenant_id')
        if bot_tenant_id and agent.get('tenant_id') != bot_tenant_id:
            _lang = agent.get('lang', _lang)
            if _msg:
                await _msg.reply_text(
                    i18n.t(_lang, "wrong_firm_bot"),
                    reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        # Inject plan into agent dict for downstream use (menu, feature gates)
        if agent.get('tenant_id'):
            _t = await db.get_tenant(agent['tenant_id'])
            agent['_plan'] = _t.get('plan', 'trial') if _t else 'trial'
        else:
            agent['_plan'] = 'trial'
        context.user_data['_agent'] = agent

        # ── Master bot lightweight mode ──
        # On the platform master bot, only allow basic commands for regular users.
        # Full CRM features are only available on tenant-specific bots,
        # except for superadmin who needs monitoring access.
        _is_master_bot = context.bot_data.get('_is_master', True)
        _bot_tid = context.bot_data.get('_tenant_id')
        if _is_master_bot and not _bot_tid:
            _is_sa = agent.get('phone', '') in SUPERADMIN_PHONES
            if not _is_sa:
                _allowed_on_master = {
                    'cmd_help', 'cmd_weblogin', 'cmd_lang', 'cmd_settings',
                    'cmd_cancel', 'cmd_logout', 'cmd_leave', 'cmd_refresh',
                    'cmd_createbot', 'cmd_wasetup', '_handle_bot_token',
                    'cmd_listenhelp', 'cmd_plans', 'cmd_ai',
                }
                if func.__name__ not in _allowed_on_master:
                    _lang = agent.get('lang', 'en')
                    _own_bot_name = ''
                    try:
                        _tdata = await db.get_tenant(agent.get('tenant_id'))
                        if _tdata and _tdata.get('tg_bot_token'):
                            from telegram import Bot as _TmpBot
                            _tb_info = await _TmpBot(token=_tdata['tg_bot_token']).get_me()
                            _own_bot_name = _tb_info.username or ''
                    except Exception:
                        pass
                    if _own_bot_name:
                        _redirect_msg = (
                            f"🤖 This is the <b>Sarathi-AI</b> platform bot.\n\n"
                            f"👉 Use your CRM bot <b>@{_own_bot_name}</b> for leads, "
                            f"pipeline, calculators & all CRM features."
                        )
                    else:
                        _redirect_msg = (
                            "🤖 This is the <b>Sarathi-AI</b> platform bot.\n\n"
                            "ℹ️ Connect your own bot with /createbot to access all CRM features."
                        )
                    if _msg:
                        await _msg.reply_text(_redirect_msg, parse_mode=ParseMode.HTML)
                    return ConversationHandler.END

        return await func(update, context)
    return wrapper


async def _check_plan(update: Update, agent: dict, feature: str) -> bool:
    """Check if agent's tenant plan allows a feature.  Returns True if allowed.
    If not allowed, sends upgrade prompt and returns False."""
    tid = agent.get('tenant_id')
    if not tid:
        return True  # no tenant = trial, allow basic features
    result = await db.check_plan_feature(tid, feature)
    if not result.get('allowed'):
        _lang = agent.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(_lang, "feature_locked",
                   reason=result.get('reason', 'Upgrade your plan to access this feature.')),
            parse_mode=ParseMode.MARKDOWN)
        return False
    return True


def owner_only(func):
    """Decorator: restrict command to firm owner/admin role only."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        agent = context.user_data.get('_agent')
        if not agent:
            agent = await db.get_agent(str(update.effective_user.id))
        if not agent or agent.get('role') not in ('owner', 'admin'):
            _lang = context.user_data.get('lang', 'en')
            await update.message.reply_text(i18n.t(_lang, "owner_only"))
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


def superadmin_only(func):
    """Decorator: restrict to platform super-admin (checks phone vs SUPERADMIN_PHONES + OTP session)."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        agent = await db.get_agent(user_id)
        if not agent or agent.get('phone', '') not in SUPERADMIN_PHONES:
            _lang = context.user_data.get('lang', 'en')
            await update.message.reply_text(i18n.t(_lang, "superadmin_only"))
            return
        # Check SA OTP session
        phone = agent.get('phone', '')
        sa_session = _sa_sessions.get(phone)
        if not sa_session or (time.time() - sa_session['ts']) > SA_SESSION_TIMEOUT:
            _sa_sessions.pop(phone, None)
            # Send OTP for SA login
            import biz_auth as auth
            otp_result = auth.generate_otp(phone)
            if otp_result.get("error"):
                await update.message.reply_text(
                    "❌ Error generating OTP. Please try again later.")
                return
            context.user_data['_sa_otp_pending'] = True
            context.user_data['_sa_phone'] = phone
            context.user_data['_sa_otp_attempts'] = 0
            masked = f"{phone[:3]}****{phone[-3:]}" if len(phone) >= 6 else phone
            dev_mode = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes")
            if dev_mode:
                await update.message.reply_text(
                    f"🔐 <b>Super Admin Authentication Required</b>\n\n"
                    f"📱 Phone: <b>{masked}</b>\n"
                    f"🔑 OTP: <code>{otp_result['otp']}</code>\n\n"
                    f"Enter the OTP to access SA panel:\n"
                    f"<i>Session valid for 1 hour after login.</i>\n"
                    f"Type 'cancel' to abort.",
                    parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(
                    f"🔐 <b>Super Admin Authentication Required</b>\n\n"
                    f"📱 OTP sent to <b>{masked}</b>\n"
                    f"Please enter the 6-digit OTP to access SA panel:\n\n"
                    f"<i>Session valid for 1 hour after login.</i>\n"
                    f"Type 'cancel' to abort.",
                    parse_mode=ParseMode.HTML)
            return
        # Session active — refresh timestamp
        sa_session['ts'] = time.time()
        return await func(update, context)
    return wrapper


# =============================================================================
#  /start — ONBOARDING (Multi-tenant: New Firm or Join via Invite)
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome + registration check. No auth decorator — open to all."""
    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)

    # Determine if this is a per-tenant bot or the master bot
    bot_tenant_id = context.bot_data.get('_tenant_id')
    is_master = context.bot_data.get('_is_master', True)

    # ── Handle web signup deep link: /start web_{tenant_id}_{sig} ──
    if context.args and context.args[0].startswith("web_"):
        parts = context.args[0].split("_")  # ["web", "<tid>", "<sig>"]
        web_tenant_id = None
        sig_valid = False
        try:
            web_tenant_id = int(parts[1])
            # Verify HMAC signature to prevent tenant hijacking
            if len(parts) >= 3:
                import hmac as _hmac, hashlib as _hashlib
                expected_sig = _hmac.new(
                    os.getenv("JWT_SECRET", "fallback").encode(),
                    f"web_{web_tenant_id}".encode(),
                    _hashlib.sha256,
                ).hexdigest()[:16]
                sig_valid = _hmac.compare_digest(parts[2], expected_sig)
            else:
                sig_valid = False  # Legacy unsigned links rejected
        except (ValueError, IndexError):
            web_tenant_id = None

        if web_tenant_id and sig_valid:
            tenant = await db.get_tenant(web_tenant_id)
            if tenant and not agent:
                # ── Cross-channel: auto-link if web owner agent exists ──
                existing_owner = await db.get_owner_agent_by_tenant(web_tenant_id)
                if existing_owner and existing_owner.get('name') and existing_owner.get('phone'):
                    # All data exists from web signup — auto-link, no questions
                    linked = await db.link_agent_telegram(existing_owner['phone'], user_id)
                    agent_id = linked['agent_id'] if linked else None
                    if not agent_id:
                        agent_id = await db.upsert_agent(
                            telegram_id=user_id, name=existing_owner['name'],
                            phone=existing_owner['phone'],
                            email=existing_owner.get('email', ''),
                            tenant_id=web_tenant_id, role='owner')
                    await db.update_tenant(web_tenant_id, owner_telegram_id=user_id)
                    await db.log_audit("web_deeplink_auto_linked",
                                      f"Firm: {tenant['firm_name']}",
                                      tenant_id=web_tenant_id, agent_id=agent_id)
                    _start_session(context)
                    lang = existing_owner.get('lang', 'en')
                    has_own_bot = tenant.get('tg_bot_token')
                    is_master = context.bot_data.get('_is_master', True)
                    if is_master and not has_own_bot:
                        # Show bot connection guide on master bot
                        context.user_data['_onboard_tenant_id'] = web_tenant_id
                        await update.message.reply_text(
                            i18n.t(lang, "welcome_linked_setup_bot",
                                   name=h(existing_owner['name']),
                                   firm=h(tenant['firm_name'])),
                            parse_mode=ParseMode.HTML)
                        return await _show_bot_guide_prompt(update, context, is_new=True)
                    else:
                        await update.message.reply_text(
                            i18n.t(lang, "welcome_linked",
                                   name=h(existing_owner['name']),
                                   firm=h(tenant['firm_name'])),
                            parse_mode=ParseMode.HTML,
                            reply_markup=_main_menu_keyboard(lang))
                        return ConversationHandler.END
                # Fallback: owner data incomplete — ask only missing fields
                context.user_data['tenant_id'] = web_tenant_id
                context.user_data['firm_name'] = tenant['firm_name']
                context.user_data['role'] = 'owner'
                context.user_data['web_signup'] = True
                await db.update_tenant(web_tenant_id, owner_telegram_id=user_id)
                return await _resume_from_missing_fields(
                    update, context, tenant, existing_owner)
            elif tenant and agent:
                # Already registered — just greet
                lang = agent.get('lang', 'en')
                _start_session(context)
                await update.message.reply_text(
                    i18n.t(lang, "welcome_back", name=h(agent['name'])),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_main_menu_keyboard(lang),
                )
                return ConversationHandler.END
        elif web_tenant_id and not sig_valid:
            _lang = context.user_data.get('lang', 'en')
            await update.message.reply_text(i18n.t(_lang, "invalid_signup_link"))
            return ConversationHandler.END

    # ── Per-tenant bot: auto-scope to this tenant ──
    if bot_tenant_id and not is_master:
        tenant = await db.get_tenant(bot_tenant_id)
        if not tenant:
            await update.message.reply_text(i18n.t('en', "bot_not_configured"))
            return ConversationHandler.END

        if agent:
            # Check if agent has been deactivated
            if not agent.get('is_active', 1):
                await update.message.reply_text(
                    "🚫 <b>Account Deactivated</b>\n\n"
                    "Your access to this bot has been revoked by your firm admin.\n"
                    "Contact your firm owner if you believe this is an error.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=ReplyKeyboardRemove())
                return ConversationHandler.END
            # Already registered — verify they belong to this tenant
            if agent.get('tenant_id') == bot_tenant_id:
                lang = agent.get('lang', 'en')
                _start_session(context)
                await update.message.reply_text(
                    i18n.t(lang, "welcome_back", name=h(agent['name'])),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_main_menu_keyboard(lang),
                )
                return ConversationHandler.END
            else:
                _lang = agent.get('lang', 'en')
                await update.message.reply_text(
                    i18n.t(_lang, "different_firm"),
                    reply_markup=ReplyKeyboardRemove())
                return ConversationHandler.END

        # New user on a per-tenant bot — decide: owner or agent
        # Check if tenant already has an owner linked
        owner_tg_id = tenant.get('owner_telegram_id')
        if not owner_tg_id or owner_tg_id == user_id:
            # ── Cross-channel: check if owner registered via web ──
            existing_owner = await db.get_owner_agent_by_tenant(bot_tenant_id)
            if existing_owner and existing_owner.get('name') and existing_owner.get('phone'):
                # Owner data exists from web signup — confirm identity, don't re-ask
                context.user_data['tenant_id'] = bot_tenant_id
                context.user_data['firm_name'] = tenant['firm_name']
                context.user_data['role'] = 'owner'
                context.user_data['web_signup'] = True
                context.user_data['_web_owner'] = dict(existing_owner)

                name = existing_owner['name']
                phone = existing_owner['phone']
                masked_phone = (f"{phone[:3]}****{phone[-3:]}"
                                if len(phone) >= 6 else phone)
                email = existing_owner.get('email', '')
                masked_email = ""
                if email and '@' in email:
                    masked_email = f"{email[:3]}***{email[email.index('@'):]}"

                profile_text = (f"👤 Name: <b>{h(name)}</b>\n"
                                f"📱 Phone: <b>{masked_phone}</b>")
                if masked_email:
                    profile_text += f"\n📧 Email: <b>{masked_email}</b>"

                keyboard = [
                    [InlineKeyboardButton(
                        "✅ Yes, that's me!",
                        callback_data="onboard_confirm_yes")],
                    [InlineKeyboardButton(
                        "👥 No, I want to join as agent",
                        callback_data="onboard_confirm_agent")],
                ]
                await update.message.reply_text(
                    i18n.t('en', "welcome_tenant_found",
                           firm=h(tenant['firm_name']),
                           profile=profile_text),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML)
                return ONBOARD_CHOICE

            # No web owner or data incomplete — smart resume
            context.user_data['tenant_id'] = bot_tenant_id
            context.user_data['firm_name'] = tenant['firm_name']
            context.user_data['role'] = 'owner'
            context.user_data['web_signup'] = True
            await db.update_tenant(bot_tenant_id, owner_telegram_id=user_id)
            return await _resume_from_missing_fields(
                update, context, tenant, existing_owner)
        else:
            # Joining as agent — phone OTP login (or invite code fallback)
            context.user_data['_pending_tenant_id'] = bot_tenant_id
            context.user_data['_login_tenant_id'] = bot_tenant_id
            keyboard = [
                [InlineKeyboardButton("� Login with Email",
                                      callback_data="onboard_login_phone")],
                [InlineKeyboardButton("🔗 I have an Invite Code",
                                      callback_data="onboard_invite")],
            ]
            await update.message.reply_text(
                f"👋 <b>Welcome to {h(tenant['firm_name'])}!</b>\n\n"
                f"If you already have an account, tap <b>Login with Email</b> "
                f"to verify your identity.\n\n"
                f"New here? Ask your firm owner for an invite code.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML)
            return ONBOARD_CHOICE

    # ── Master bot: existing flow ──
    if agent:
        # Already registered — check if onboarding was incomplete
        if agent.get('onboarding_step'):
            step = agent['onboarding_step']
            lang = agent.get('lang', 'en')
            await update.message.reply_text(
                i18n.t(lang, "resume_onboarding", step=step),
                parse_mode=ParseMode.HTML)
            if step == 'phone':
                return ONBOARD_PHONE
            elif step == 'email':
                return ONBOARD_EMAIL
            elif step == 'firm':
                return ONBOARD_FIRM
            else:
                return ONBOARD_NAME

        lang = agent.get('lang', 'en')

        # Check if this is the master bot and user hasn't connected their own bot
        tenant = await db.get_tenant(agent.get('tenant_id'))
        firm = tenant['firm_name'] if tenant else agent.get('firm_name', '')
        has_own_bot = tenant and tenant.get('tg_bot_token')

        if is_master and not has_own_bot and agent.get('role') in ('owner', 'admin'):
            # Master bot + no connected bot = show guided setup (guide first)
            context.user_data['_onboard_tenant_id'] = agent.get('tenant_id')
            _start_session(context)
            await update.message.reply_text(
                i18n.t(lang, "welcome_back_setup_bot",
                       name=h(agent['name']), firm=h(firm)),
                parse_mode=ParseMode.HTML)
            return await _show_bot_guide_prompt(update, context, is_new=False)

        if is_master:
            # Master bot — don't show CRM buttons, guide to their own bot
            tenant = await db.get_tenant(agent.get('tenant_id')) if not tenant else tenant
            bot_username = ''
            if tenant and tenant.get('tg_bot_token'):
                try:
                    from telegram import Bot as _Bot
                    _b = _Bot(token=tenant['tg_bot_token'])
                    _bi = await _b.get_me()
                    bot_username = _bi.username or ''
                except Exception:
                    pass
            _start_session(context)
            if bot_username:
                await update.message.reply_text(
                    i18n.t(lang, "welcome_back", name=h(agent['name']))
                    + f"\n\n👉 Your CRM bot: @{bot_username}\nUse that bot for leads, pipeline, calculators & more.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=ReplyKeyboardRemove(),
                )
            else:
                await update.message.reply_text(
                    i18n.t(lang, "welcome_back", name=h(agent['name']))
                    + "\n\nℹ️ Connect your own bot with /createbot to access CRM features.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=ReplyKeyboardRemove(),
                )
            return ConversationHandler.END

        # Tenant bot — show full CRM menu
        _start_session(context)
        await update.message.reply_text(
            i18n.t(lang, "welcome_back", name=h(agent['name'])),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_menu_keyboard(lang),
        )
        return ConversationHandler.END

    # New user on master bot — ask language first
    lang_keyboard = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="onboard_lang_en"),
         InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="onboard_lang_hi")],
    ]
    await update.message.reply_text(
        i18n.t('en', "welcome_master_bot"),
        reply_markup=InlineKeyboardMarkup(lang_keyboard),
        parse_mode=ParseMode.HTML,
    )
    return ONBOARD_LANG


# ─────────────────────────────────────────────────────────
#  Cross-channel helpers: resume + bot guide
# ─────────────────────────────────────────────────────────

async def _resume_from_missing_fields(update, context, tenant, existing_owner):
    """Detect which fields are already populated and skip to the first missing one.
    Used for cross-channel resume (web→telegram or partial registrations)."""
    firm = tenant['firm_name']
    if existing_owner and existing_owner.get('name'):
        context.user_data['agent_name'] = existing_owner['name']
        if existing_owner.get('phone'):
            context.user_data['agent_phone'] = existing_owner['phone']
            if existing_owner.get('email'):
                context.user_data['agent_email'] = existing_owner['email']
                # Only city might be missing
                city = tenant.get('city', '')
                if city:
                    context.user_data['agent_city'] = city
                    # Everything filled — just complete registration
                    return await _complete_registration(update, context)
                await update.message.reply_text(
                    f"🎉 <b>Welcome to {h(firm)}!</b>\n\n"
                    f"Almost done! What <b>city</b> are you based in?\n\n"
                    f"💡 Example: <b>Mumbai</b>, <b>Delhi</b>, <b>Indore</b>",
                    parse_mode=ParseMode.HTML)
                return ONBOARD_CITY
            # Email missing
            lang = context.user_data.get('lang', 'en')
            await update.message.reply_text(
                f"🎉 <b>Welcome to {h(firm)}!</b>\n\n"
                + i18n.t(lang, "ask_email"),
                parse_mode=ParseMode.HTML)
            return ONBOARD_EMAIL
        # Phone missing
        lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(
            f"🎉 <b>Welcome to {h(firm)}!</b>\n\n"
            + i18n.t(lang, "ask_phone"),
            parse_mode=ParseMode.HTML)
        return ONBOARD_PHONE
    # Nothing filled — start from name
    await update.message.reply_text(
        f"🎉 <b>Welcome to {h(firm)}!</b>\n\n"
        f"You're setting up as the <b>firm owner</b>.\n"
        f"Let's complete your profile.\n\n"
        f"What is your <b>full name</b>?",
        parse_mode=ParseMode.HTML)
    return ONBOARD_NAME


async def _show_bot_guide_prompt(update, context, is_new=True):
    """Show BotFather step-by-step guide FIRST, then offer token input.
    Guide is shown upfront so user sees it before being asked for the token."""
    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
    bot_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 I have my token — Connect Now",
                              callback_data="onboard_bottoken_yes")],
        [InlineKeyboardButton("⏭️ Skip — I'll do it later",
                              callback_data="onboard_bottoken_skip")],
        [InlineKeyboardButton("🌐 Use Web Dashboard Instead",
                              url=f"{server_url}/onboarding")],
    ])
    guide_text = (
        "📖 <b>How to Create Your Own Telegram Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Step 1:</b> Open @BotFather\n"
        "• Search for <b>@BotFather</b> in Telegram\n"
        "• It's Telegram's official bot for creating bots ✅\n\n"
        "<b>Step 2:</b> Create a new bot\n"
        "• Send <code>/newbot</code> to @BotFather\n"
        "• Choose a <b>display name</b>\n"
        "  (e.g., \"Acme Financial Advisors\")\n"
        "• Choose a <b>username</b> ending in 'bot'\n"
        "  (e.g., <code>AcmeAdvisorsBot</code>)\n\n"
        "<b>Step 3:</b> Copy the token\n"
        "• BotFather will give you a message like:\n"
        "  <code>123456789:ABCdefGHI-jklMNOpqrSTUvwx</code>\n"
        "• <b>Copy this entire token</b>\n\n"
        "<b>Step 4:</b> Come back here\n"
        "• Tap \"Connect Now\" below\n"
        "• Paste the token\n"
        "• Done! Your CRM bot is ready ✅\n\n"
        "⏱️ Total time: <b>~2 minutes</b>\n\n"
        "👇 <b>When you have the token, tap below:</b>"
    )
    # Use reply_text if it's a message update, else we need to send new msg
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        await msg.reply_text(guide_text, parse_mode=ParseMode.HTML,
                             reply_markup=bot_kb,
                             disable_web_page_preview=True)
    return ONBOARD_BOT_TOKEN


async def onboard_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection during onboarding."""
    query = update.callback_query
    await query.answer()

    lang = "hi" if query.data == "onboard_lang_hi" else "en"
    context.user_data['lang'] = lang

    # Now show account type selection in chosen language
    if lang == "hi":
        keyboard = [
            [InlineKeyboardButton("🏢 अपनी फर्म रजिस्टर करें",
                                  callback_data="onboard_firm")],
            [InlineKeyboardButton("👤 मैं व्यक्तिगत सलाहकार हूं",
                                  callback_data="onboard_individual")],
            [InlineKeyboardButton("🔗 मेरे पास इनवाइट कोड है",
                                  callback_data="onboard_invite")],
            [InlineKeyboardButton("🌐 मैंने वेब पर रजिस्टर किया है",
                                  callback_data="onboard_link_web")],
        ]
        await query.edit_message_text(
            "✅ भाषा: <b>हिन्दी</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📋 <b>सेटअप (3 चरण):</b>\n"
            "  चरण 1️⃣  अकाउंट टाइप चुनें\n"
            "  चरण 2️⃣  अपनी जानकारी दर्ज करें\n"
            "  चरण 3️⃣  अपना बिज़नेस मैनेज करें!\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "👇 <b>शुरू करने के लिए नीचे टैप करें:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🏢 Register my Firm",
                                  callback_data="onboard_firm")],
            [InlineKeyboardButton("👤 I'm an Individual Advisor",
                                  callback_data="onboard_individual")],
            [InlineKeyboardButton("🔗 I have an Invite Code",
                                  callback_data="onboard_invite")],
            [InlineKeyboardButton("🌐 I registered on Web",
                                  callback_data="onboard_link_web")],
        ]
        await query.edit_message_text(
            "✅ Language: <b>English</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📋 <b>Quick Setup (3 steps):</b>\n"
            "  Step 1️⃣  Choose your account type\n"
            "  Step 2️⃣  Enter your details\n"
            "  Step 3️⃣  Start managing your business!\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "👇 <b>Tap a button below to begin:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
    return ONBOARD_CHOICE


async def onboard_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle firm / individual / invite code selection."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)

    if query.data in ("onboard_firm", "onboard_individual"):
        # ── One Telegram Account = One Trial restriction ──
        existing = await db.find_tenant_by_telegram_id(user_id)
        if existing:
            status = existing.get('subscription_status', '')
            firm = existing.get('firm_name', 'Unknown')
            tid = existing.get('tenant_id', 0)
            if status in ('active', 'trial', 'paid'):
                await query.edit_message_text(
                    f"❌ <b>Account Already Exists</b>\n\n"
                    f"Your Telegram account is already linked to:\n"
                    f"🏢 <b>{h(firm)}</b> (#{tid})\n\n"
                    f"Each Telegram account can register only <b>one firm</b>.\n"
                    f"Use /start to access your existing firm.",
                    parse_mode=ParseMode.HTML)
                return ConversationHandler.END
            elif status in ('expired', 'wiped', 'cancelled'):
                await query.edit_message_text(
                    f"❌ <b>Trial Already Used</b>\n\n"
                    f"A free trial was already used with this Telegram account "
                    f"(Firm: <b>{h(firm)}</b>).\n\n"
                    f"Free trial is available <b>once per Telegram account</b>.\n"
                    f"To reactivate, visit 🌐 <b>sarathi-ai.com</b> to subscribe.",
                    parse_mode=ParseMode.HTML)
                return ConversationHandler.END

    if query.data == "onboard_firm":
        context.user_data['account_type'] = 'firm'
        await query.edit_message_text(
            "🏢 <b>Step 1 of 3 — Firm / Practice Name</b>\n\n"
            "What is your <b>firm name</b>?\n\n"
            "💡 Example: \"Krishna Financial Advisory\" or \"Sharma & Associates\"",
            parse_mode=ParseMode.HTML)
        return ONBOARD_FIRM
    elif query.data == "onboard_individual":
        context.user_data['account_type'] = 'individual'
        context.user_data['role'] = 'owner'
        await query.edit_message_text(
            "👤 <b>Step 1 of 3 — Your Name</b>\n\n"
            "What is your <b>full name</b> (first + last)?\n\n"
            "💡 Example: <b>Rajesh Sharma</b> or <b>Priya Gupta</b>\n\n"
            "<i>This will also be used as your practice name.</i>",
            parse_mode=ParseMode.HTML)
        return ONBOARD_NAME
    elif query.data == "onboard_invite":
        await query.edit_message_text(
            "🔗 <b>Join a Team</b>\n\n"
            "Please enter the <b>invite code</b> shared by your firm owner.\n\n"
            "💡 Ask your team lead — they can find it under ⚙️ Settings → Team.",
            parse_mode=ParseMode.HTML)
        return ONBOARD_INVITE

    elif query.data == "onboard_login_phone":
        # OTP-based login for existing agents on tenant bot (now email-based)
        await query.edit_message_text(
            "📧 <b>Login with Email</b>\n\n"
            "Enter the <b>email address</b> registered with your account:\n\n"
            "💡 Example: <b>name@example.com</b>",
            parse_mode=ParseMode.HTML)
        return LOGIN_PHONE

    elif query.data == "onboard_link_web":
        lang = context.user_data.get('lang', 'en')
        if lang == 'hi':
            await query.edit_message_text(
                "🌐 <b>वेब अकाउंट लिंक करें</b>\n\n"
                "कृपया वो <b>फ़ोन नंबर</b> दर्ज करें जिससे आपने वेब पर रजिस्टर किया था:\n\n"
                "💡 10 अंकों का मोबाइल नंबर (जैसे <b>9876543210</b>)",
                parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(
                "🌐 <b>Link Your Web Account</b>\n\n"
                "Please enter the <b>phone number</b> you used to register on the web:\n\n"
                "💡 10-digit mobile number (e.g. <b>9876543210</b>)",
                parse_mode=ParseMode.HTML)
        return ONBOARD_LINK_WEB

    elif query.data == "onboard_confirm_yes":
        # ── Cross-channel: web-registered owner confirmed identity ──
        # Now requires OTP verification for security
        import biz_auth as auth
        web_owner = context.user_data.get('_web_owner', {})
        tenant_id = context.user_data.get('tenant_id')
        if web_owner and tenant_id and web_owner.get('phone'):
            phone = web_owner['phone']
            lang = web_owner.get('lang', 'en')
            hi = lang == 'hi'
            # Store link data for the OTP handler to use
            context.user_data['_link_phone'] = phone
            context.user_data['_link_tenant_id'] = tenant_id
            context.user_data['_link_firm_name'] = context.user_data.get('firm_name', '')
            context.user_data['_otp_attempts'] = 0
            # Send OTP
            otp_result = auth.generate_otp(phone)
            if otp_result.get("error"):
                await query.edit_message_text(
                    f"❌ {'OTP भेजने में त्रुटि। कृपया बाद में पुनः प्रयास करें।' if hi else 'Error sending OTP. Please try again later.'}",
                    parse_mode=ParseMode.HTML)
                return ConversationHandler.END
            masked = f"{phone[:3]}****{phone[-3:]}" if len(phone) >= 6 else phone
            # In dev mode, show OTP directly
            dev_mode = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes")
            if dev_mode:
                await query.edit_message_text(
                    f"🔐 {'पहचान सत्यापित करें' if hi else 'Verify your identity'}\n\n"
                    f"📱 {'फ़ोन' if hi else 'Phone'}: <b>{masked}</b>\n"
                    f"🔑 OTP: <code>{otp_result['otp']}</code>\n\n"
                    f"{'कृपया OTP दर्ज करें:' if hi else 'Please enter the OTP:'}\n"
                    f"{'रद्द करने के लिए /cancel टाइप करें' if hi else 'Type /cancel to abort'}",
                    parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text(
                    f"🔐 {'पहचान सत्यापित करने के लिए OTP भेजा गया' if hi else 'OTP sent to verify your identity'}\n\n"
                    f"📱 {'फ़ोन' if hi else 'Phone'}: <b>{masked}</b>\n"
                    f"{'कृपया 6 अंकों का OTP दर्ज करें:' if hi else 'Please enter the 6-digit OTP:'}\n"
                    f"{'रद्द करने के लिए /cancel टाइप करें' if hi else 'Type /cancel to abort'}",
                    parse_mode=ParseMode.HTML)
            return ONBOARD_LINK_WEB_OTP
        await query.edit_message_text(i18n.t('en', "something_wrong_retry"))
        return ConversationHandler.END

    elif query.data == "onboard_confirm_agent":
        # ── User is NOT the owner — redirect to invite code flow ──
        tenant_id = context.user_data.get('tenant_id')
        context.user_data['_pending_tenant_id'] = tenant_id
        firm = context.user_data.get('firm_name', 'this firm')
        keyboard = [
            [InlineKeyboardButton("🔗 I have an Invite Code",
                                  callback_data="onboard_invite")],
        ]
        await query.edit_message_text(
            i18n.t('en', "invite_join_prompt", firm=h(firm)),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)
        return ONBOARD_CHOICE


async def onboard_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle invite code validation."""
    code = update.message.text.strip().upper()
    invite = await db.validate_invite_code(code)
    if not invite:
        _lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(_lang, "invite_code_invalid"))
        return ONBOARD_INVITE

    # ── Plan limit check: can this tenant add another agent? ──
    cap = await db.can_add_agent(invite['tenant_id'])
    if not cap['allowed']:
        _lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(_lang, "team_full_msg"),
            parse_mode=ParseMode.HTML)
        return ONBOARD_INVITE

    # Valid invite — store tenant_id for later
    context.user_data['tenant_id'] = invite['tenant_id']
    context.user_data['invite_code'] = code
    context.user_data['role'] = 'agent'
    tenant = await db.get_tenant(invite['tenant_id'])
    context.user_data['firm_name'] = tenant['firm_name'] if tenant else 'Unknown'

    await update.message.reply_text(
        f"✅ Invite code valid!\n"
        f"You're joining: <b>{h(context.user_data['firm_name'])}</b>\n\n"
        f"What is your <b>full name</b>?",
        parse_mode=ParseMode.HTML)
    return ONBOARD_NAME


async def onboard_firm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive firm name for new tenant registration."""
    firm = update.message.text.strip()
    if len(firm) < 2 or len(firm) > 200:
        _lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(i18n.t(_lang, "firm_name_invalid"))
        return ONBOARD_FIRM
    context.user_data['firm_name'] = firm
    context.user_data['role'] = 'owner'
    _lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(
        i18n.t(_lang, "step_your_name_2"),
        parse_mode=ParseMode.HTML)
    return ONBOARD_NAME


async def onboard_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive agent name — must have at least first + last name."""
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 100:
        _lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(i18n.t(_lang, "name_invalid"))
        return ONBOARD_NAME
    # Require at least two words (first name + last name)
    words = [w for w in name.split() if len(w) >= 1]
    if len(words) < 2:
        _lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(_lang, "enter_full_name"),
            parse_mode=ParseMode.HTML)
        return ONBOARD_NAME
    context.user_data['agent_name'] = name
    # For individual registration, firm name = owner's name
    if context.user_data.get('account_type') == 'individual':
        context.user_data['firm_name'] = name
        context.user_data['role'] = 'owner'
    user_id = str(update.effective_user.id)
    # Save progress so user can resume if they drop off
    await db.update_agent_onboarding(user_id, 'phone')
    lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(i18n.t(lang, "ask_phone"),
                                   parse_mode=ParseMode.HTML)
    return ONBOARD_PHONE


async def onboard_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive agent phone — with cross-tenant duplicate blocking."""
    raw = update.message.text.strip()
    phone = _valid_phone(raw)
    if not phone:
        lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(lang, "invalid_phone"),
            parse_mode=ParseMode.HTML)
        return ONBOARD_PHONE

    # ── Cross-tenant duplicate check (blocks re-trial abuse) ──
    role = context.user_data.get('role', 'agent')
    tenant_id = context.user_data.get('tenant_id')
    if role == 'owner' and not context.user_data.get('web_signup'):
        existing = await db.find_tenant_by_phone_or_email(phone=phone)
        if existing:
            status = existing.get('subscription_status', '')
            if status in ('active', 'trial'):
                await update.message.reply_text(
                    "❌ This phone number is already registered with an active account.\n\n"
                    "If this is your number, use /start on your existing bot, "
                    "or ask your firm owner for an invite code.",
                    parse_mode=ParseMode.HTML)
                return ONBOARD_PHONE
            elif status in ('expired', 'wiped', 'cancelled'):
                await update.message.reply_text(
                    "❌ A trial was already used with this phone number.\n\n"
                    "Free trial is available <b>once per phone</b>.\n"
                    "To reactivate, please subscribe at:\n"
                    "🌐 <b>sarathi-ai.com</b> → Choose a plan",
                    parse_mode=ParseMode.HTML)
                return ONBOARD_PHONE

    # ── One-phone-one-firm: agents can only be active in one firm at a time ──
    if role == 'agent' and tenant_id:
        avail = await db.check_agent_phone_available(phone, exclude_tenant_id=tenant_id)
        if not avail['available']:
            other_firm = avail['existing_agent'].get('firm_name', 'another firm')
            await update.message.reply_text(
                f"❌ <b>Phone already in use</b>\n\n"
                f"This number is registered with <b>{h(other_firm)}</b>.\n\n"
                f"An advisor can only be active in one firm at a time.\n"
                f"Please ask your current firm admin to deactivate your profile first, "
                f"or use a different phone number.\n\n"
                f"Type /cancel to abort.",
                parse_mode=ParseMode.HTML)
            return ONBOARD_PHONE

    context.user_data['agent_phone'] = phone
    lang = context.user_data.get('lang', 'en')

    # Phone collected — move to email (email OTP verification happens there)
    await update.message.reply_text(i18n.t(lang, "ask_email"),
                                   parse_mode=ParseMode.HTML)
    return ONBOARD_EMAIL


async def onboard_verify_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify the OTP sent to the agent's WhatsApp during onboarding."""
    raw = update.message.text.strip()
    phone = context.user_data.get('otp_phone', '')
    lang = context.user_data.get('lang', 'en')

    # Validate format: must be 6 digits
    if not re.match(r'^\d{6}$', raw):
        await update.message.reply_text(
            "❌ Please enter a valid <b>6-digit OTP</b>.\n\n"
            "Check your WhatsApp for the verification code.",
            parse_mode=ParseMode.HTML)
        return ONBOARD_VERIFY_OTP

    if auth_mod.verify_otp(phone, raw):
        context.user_data['phone_verified'] = True
        await update.message.reply_text(
            "✅ <b>Phone verified!</b>\n\n"
            + i18n.t(lang, "ask_email"),
            parse_mode=ParseMode.HTML)
        return ONBOARD_EMAIL
    else:
        # OTP failed — allow retry or resend
        await update.message.reply_text(
            "❌ <b>Invalid or expired OTP.</b>\n\n"
            "Please try again, or type your phone number again to get a new OTP.\n"
            "You can also type /cancel to abort.",
            parse_mode=ParseMode.HTML)
        return ONBOARD_VERIFY_OTP


# ─────────────────────────────────────────────────────────
#  OTP Login flow (existing agents linking Telegram)
# ─────────────────────────────────────────────────────────

async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive email for OTP login on tenant bot."""
    raw = update.message.text.strip().lower()
    email = _valid_email(raw)
    if not email:
        await update.message.reply_text(
            "❌ Invalid email. Please enter a valid email address.\n"
            "💡 Example: <b>name@example.com</b>",
            parse_mode=ParseMode.HTML)
        return LOGIN_PHONE

    tenant_id = context.user_data.get('_login_tenant_id') or \
                context.user_data.get('_pending_tenant_id')
    if not tenant_id:
        await update.message.reply_text(
            "❌ Session expired. Please type /start to try again.")
        return ConversationHandler.END

    # Check if agent with this email exists in this tenant
    agent = await db.get_agent_by_email_tenant(email, tenant_id)
    if not agent:
        await update.message.reply_text(
            "❌ <b>No account found</b> with this email in this firm.\n\n"
            "Make sure your firm owner has added you to the team.\n"
            "Or tap /start to try again.",
            parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # Generate and send email OTP
    otp_result = auth_mod.generate_email_otp(email)
    if otp_result.get("error"):
        await update.message.reply_text(
            f"⚠️ {otp_result['error']}\nPlease try again.",
            parse_mode=ParseMode.HTML)
        return LOGIN_PHONE

    otp_sent = False
    if email_mod.is_enabled():
        name = agent.get('name', '')
        otp_sent = await email_mod.send_otp_email(email, otp_result["otp"],
                                                    owner_name=name)

    context.user_data['_login_email'] = email
    context.user_data['_login_agent_id'] = agent['agent_id']
    context.user_data['_login_otp_attempts'] = 0

    if otp_sent:
        masked = email[:3] + "•••" + email[email.index('@'):]
        await update.message.reply_text(
            f"📧 <b>OTP Sent!</b>\n\n"
            f"A 6-digit code has been sent to <b>{masked}</b>.\n\n"
            f"Enter the OTP below:\n"
            f"<i>(Valid for 10 minutes)</i>\n"
            f"Type /cancel to abort",
            parse_mode=ParseMode.HTML)
    else:
        dev_mode = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes")
        if dev_mode:
            await update.message.reply_text(
                f"📧 <b>OTP Generated (Dev Mode)</b>\n\n"
                f"Your OTP is: <code>{otp_result['otp']}</code>\n\n"
                f"Enter it below to login:\n"
                f"Type /cancel to abort",
                parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(
                f"📧 <b>OTP Generated</b>\n\n"
                f"A 6-digit code has been generated for your email.\n\n"
                f"Enter the OTP below:\n"
                f"<i>(Valid for 10 minutes)</i>\n"
                f"Type /cancel to abort",
                parse_mode=ParseMode.HTML)
    return LOGIN_OTP


async def login_verify_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify email OTP and link Telegram ID to existing agent."""
    raw = update.message.text.strip()
    email = context.user_data.get('_login_email', '')

    if not re.match(r'^\d{6}$', raw):
        await update.message.reply_text(
            "❌ Please enter a valid <b>6-digit OTP</b>.\n"
            "Type /cancel to abort.",
            parse_mode=ParseMode.HTML)
        return LOGIN_OTP

    # Max attempts guard
    attempts = context.user_data.get('_login_otp_attempts', 0) + 1
    context.user_data['_login_otp_attempts'] = attempts
    if attempts > 5:
        await update.message.reply_text(
            "❌ Too many failed attempts. Please type /start to try again.")
        context.user_data.clear()
        return ConversationHandler.END

    if not auth_mod.verify_email_otp(email, raw):
        remaining = 5 - attempts
        await update.message.reply_text(
            f"❌ <b>Invalid or expired OTP.</b>\n\n"
            f"Please try again ({remaining} attempts left), or type /start to restart.",
            parse_mode=ParseMode.HTML)
        return LOGIN_OTP

    # OTP verified — link Telegram ID to agent
    user_id = str(update.effective_user.id)
    linked = await db.link_agent_telegram_by_email(email, user_id)
    if not linked:
        # Fallback: direct DB update for agents with logout/unknown placeholders
        import aiosqlite
        try:
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute(
                    "UPDATE agents SET telegram_id = ?, updated_at = datetime('now') "
                    "WHERE LOWER(email) = LOWER(?) AND is_active = 1",
                    (user_id, email))
                await conn.commit()
                linked = True
                logger.info("Direct-linked telegram %s to email %s (login fallback)",
                            user_id, email)
        except Exception as e:
            logger.error("Login fallback link failed: %s", e)
    if linked:
        agent = await db.get_agent(user_id)
        lang = agent.get('lang', 'en') if agent else 'en'
        name = agent.get('name', '') if agent else ''
        tenant = await db.get_tenant(agent['tenant_id']) if agent else None
        firm = tenant['firm_name'] if tenant else ''
        await db.log_audit("otp_login_linked",
                          f"Agent {name} linked via email OTP",
                          tenant_id=agent.get('tenant_id'),
                          agent_id=agent.get('agent_id'))
        _start_session(context)
        await update.message.reply_text(
            f"✅ <b>Login successful!</b>\n\n"
            f"Welcome, <b>{h(name)}</b>! 🎉\n"
            f"🏢 {h(firm)}\n\n"
            f"You're all set. Use the menu below to get started.",
            parse_mode=ParseMode.HTML,
            reply_markup=_main_menu_keyboard(lang, agent=agent))
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Could not link your account. The email may already "
            "be linked to another Telegram account.\n\n"
            "Contact your firm owner for help, or type /start to try again.",
            parse_mode=ParseMode.HTML)
        return ConversationHandler.END


async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unlink Telegram ID from agent account. Allows re-login or account switching."""
    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)

    if not agent:
        await update.message.reply_text(
            "ℹ️ You're not logged in. Use /start to login.",
            reply_markup=ReplyKeyboardRemove())
        return

    name = agent.get('name', '')
    lang = agent.get('lang', 'en')

    # Unlink telegram_id
    success = await db.unlink_agent_telegram(user_id)
    if success:
        await db.log_audit("logout",
                          f"Agent {name} unlinked Telegram",
                          tenant_id=agent.get('tenant_id'),
                          agent_id=agent.get('agent_id'))
        context.user_data.clear()
        await update.message.reply_text(
            f"👋 <b>Logged out successfully!</b>\n\n"
            f"Your Telegram is no longer linked to <b>{h(name)}</b>.\n\n"
            f"Use /start to login again with any account.",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text(
            "⚠️ Logout failed. Please try again.",
            parse_mode=ParseMode.HTML)


async def cmd_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agent self-exit from a firm. Notifies admin and deactivates account.
    Owners cannot leave (they own the subscription)."""
    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)

    if not agent:
        await update.message.reply_text(
            "ℹ️ You're not registered. Use /start to get started.",
            reply_markup=ReplyKeyboardRemove())
        return

    if agent.get('role') == 'owner':
        await update.message.reply_text(
            "❌ <b>Owners cannot leave their own firm.</b>\n\n"
            "As the firm owner, you manage the subscription.\n"
            "Use /logout to temporarily unlink your Telegram, or\n"
            "contact Sarathi-AI support to close your account.",
            parse_mode=ParseMode.HTML)
        return

    name = agent.get('name', '')
    tenant_id = agent.get('tenant_id')
    tenant = await db.get_tenant(tenant_id) if tenant_id else None
    firm = tenant['firm_name'] if tenant else 'your firm'

    # Deactivate agent (full — unlinks telegram, sets is_active=0)
    await db.deactivate_agent_full(agent['agent_id'], tenant_id=tenant_id,
                                    reason='self_leave')
    context.user_data.clear()

    await update.message.reply_text(
        f"👋 <b>You've left {h(firm)}</b>\n\n"
        f"Your account has been deactivated and Telegram unlinked.\n"
        f"Your data (leads, policies) is preserved for your firm.\n\n"
        f"If you want to join another firm, you can now register fresh\n"
        f"with any Sarathi-AI configured bot.",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove())

    # Notify firm owner/admin
    if tenant_id:
        try:
            import aiosqlite
            async with aiosqlite.connect(db.DB_PATH) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute(
                    "SELECT telegram_id, lang FROM agents "
                    "WHERE tenant_id = ? AND role IN ('owner','admin') AND is_active = 1",
                    (tenant_id,))
                admins = [dict(r) for r in await cur.fetchall()]
            for admin in admins:
                admin_tg = admin.get('telegram_id', '')
                if admin_tg and not admin_tg.startswith(('web_', 'logout_', '__')):
                    try:
                        await context.bot.send_message(
                            chat_id=int(admin_tg),
                            text=f"⚠️ <b>Agent Left</b>\n\n"
                                 f"<b>{h(name)}</b> has left your firm.\n"
                                 f"Their data is preserved. Use /team to review or transfer their leads.",
                            parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Leave notification error: %s", e)


async def onboard_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive agent email, validate, check duplicates, then send email OTP."""
    raw = update.message.text.strip()
    # Email is mandatory — validate format
    email = _valid_email(raw)
    if not email:
        await update.message.reply_text(
            "❌ Invalid email format. Please enter a valid email address\n"
            "(e.g., name@example.com)",
            parse_mode=ParseMode.HTML)
        return ONBOARD_EMAIL

    # ── Cross-tenant email duplicate check ──
    role = context.user_data.get('role', 'agent')
    if email and role == 'owner' and not context.user_data.get('web_signup'):
        existing = await db.find_tenant_by_phone_or_email(email=email)
        if existing:
            status = existing.get('subscription_status', '')
            if status in ('active', 'trial'):
                await update.message.reply_text(
                    "❌ This email is already registered with an active account.\n\n"
                    "Use /start on your existing bot, or try a different email.",
                    parse_mode=ParseMode.HTML)
                return ONBOARD_EMAIL
            elif status in ('expired', 'wiped', 'cancelled'):
                await update.message.reply_text(
                    "❌ A trial was already used with this email.\n\n"
                    "Free trial is available <b>once per email</b>.\n"
                    "To reactivate, visit 🌐 <b>sarathi-ai.com</b> to subscribe.",
                    parse_mode=ParseMode.HTML)
                return ONBOARD_EMAIL

    context.user_data['agent_email'] = email

    # ── Email OTP verification (if email system configured) ──
    if email_mod.is_enabled():
        otp_result = auth_mod.generate_email_otp(email)
        if otp_result.get("otp"):
            name = context.user_data.get('agent_name', '')
            send_ok = await email_mod.send_otp_email(email, otp_result["otp"],
                                                      owner_name=name)
            if send_ok:
                context.user_data['otp_email'] = email
                await update.message.reply_text(
                    f"📧 We've sent a <b>6-digit OTP</b> to <b>{h(email)}</b>\n\n"
                    "Please enter the code to verify your email.\n"
                    "⏳ Code expires in 10 minutes.",
                    parse_mode=ParseMode.HTML)
                return ONBOARD_VERIFY_EMAIL_OTP
            else:
                logger.warning("Email OTP send failed for %s — skipping verification", email)
        else:
            logger.warning("Email OTP generation failed for %s: %s — skipping",
                           email, otp_result.get("error", ""))

    # Fallback: skip email OTP if email not configured or send failed
    await update.message.reply_text(
        "📍 Almost done! What <b>city</b> are you based in?\n\n"
        "💡 Example: <b>Mumbai</b>, <b>Delhi</b>, <b>Indore</b>",
        parse_mode=ParseMode.HTML)
    return ONBOARD_CITY


async def onboard_verify_email_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify the email OTP during onboarding."""
    raw = update.message.text.strip()
    email = context.user_data.get('otp_email', '')
    lang = context.user_data.get('lang', 'en')

    if not re.match(r'^\d{6}$', raw):
        await update.message.reply_text(
            "❌ Please enter the <b>6-digit code</b> sent to your email.\n"
            "Only digits, no spaces.",
            parse_mode=ParseMode.HTML)
        return ONBOARD_VERIFY_EMAIL_OTP

    if auth_mod.verify_email_otp(email, raw):
        context.user_data['email_verified'] = True
        await update.message.reply_text(
            "✅ Email verified!\n\n"
            "📍 Almost done! What <b>city</b> are you based in?\n\n"
            "💡 Example: <b>Mumbai</b>, <b>Delhi</b>, <b>Indore</b>",
            parse_mode=ParseMode.HTML)
        return ONBOARD_CITY
    else:
        await update.message.reply_text(
            "❌ Invalid or expired OTP. Please try again.\n\n"
            "💡 Check your spam/junk folder. Enter /cancel to start over.",
            parse_mode=ParseMode.HTML)
        return ONBOARD_VERIFY_EMAIL_OTP


async def onboard_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive agent city during onboarding (matches web signup field)."""
    raw = update.message.text.strip()
    # Validate: 2-100 chars, letters/spaces/hyphens only
    if len(raw) < 2 or len(raw) > 100:
        await update.message.reply_text(
            "❌ City must be 2-100 characters. Please enter your city name.\n\n"
            "💡 Example: <b>Mumbai</b>, <b>New Delhi</b>, <b>Bengaluru</b>",
            parse_mode=ParseMode.HTML)
        return ONBOARD_CITY
    if not re.match(r'^[A-Za-z\s\-\.]+$', raw):
        await update.message.reply_text(
            "❌ City name should contain only letters, spaces and hyphens.\n\n"
            "💡 Example: <b>Mumbai</b>, <b>New Delhi</b>",
            parse_mode=ParseMode.HTML)
        return ONBOARD_CITY
    context.user_data['agent_city'] = raw.title()  # Normalize: "mumbai" → "Mumbai"
    return await _complete_registration(update, context)


async def _complete_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete agent/owner registration after email (and optional OTP) verification."""
    email = context.user_data.get('agent_email', '')
    user_id = str(update.effective_user.id)
    name = context.user_data.get('agent_name', 'Agent')
    phone = context.user_data.get('agent_phone', '')
    firm = context.user_data.get('firm_name', 'My Firm')
    city = context.user_data.get('agent_city', '')
    role = context.user_data.get('role', 'agent')

    if role == 'owner' and context.user_data.get('web_signup'):
        # Web signup — tenant already created, link Telegram to existing agent record
        tenant_id = context.user_data.get('tenant_id', 0)
        linked = await db.link_agent_telegram(phone, user_id)
        agent_id = linked['agent_id'] if linked else None
        if not agent_id:
            # Fallback: if link failed (agent not found by phone), upsert as before
            agent_id = await db.upsert_agent(
                telegram_id=user_id, name=name, phone=phone,
                email=email, tenant_id=tenant_id, role='owner')
        await db.update_tenant(tenant_id, owner_telegram_id=
                               str(update.effective_user.id))
        await db.log_audit("web_signup_connected", f"Firm: {firm}",
                           tenant_id=tenant_id, agent_id=agent_id)
        extra = (f"\n🏢 Firm: {h(firm)}"
                 f"\n👑 Role: Owner (via web signup)"
                 f"\n\n💡 Use ⚙️ Settings → Team to invite other agents.")
    elif role == 'owner':
        # Create new tenant first
        acct_type = context.user_data.get('account_type', 'firm')
        tenant_id = await db.create_tenant(
            firm_name=firm, owner_name=name, phone=phone,
            email=email, owner_telegram_id=user_id,
            account_type=acct_type, signup_channel='telegram',
            city=city)
        # Create agent as owner
        agent_id = await db.upsert_agent(
            telegram_id=user_id, name=name, phone=phone,
            email=email, tenant_id=tenant_id, role='owner')
        # Log audit
        await db.log_audit("tenant_created", f"{'Individual' if acct_type == 'individual' else 'Firm'}: {firm}",
                           tenant_id=tenant_id, agent_id=agent_id)
        if acct_type == 'individual':
            extra = (f"\n👤 Practice: {h(firm)}"
                     f"\n👑 Role: Individual Advisor")
        else:
            extra = (f"\n🏢 Firm: {h(firm)}"
                     f"\n👑 Role: Firm Owner"
                     f"\n\n💡 Use ⚙️ Settings → Team to invite your agents.")
    else:
        # Joining existing tenant via invite
        tenant_id = context.user_data.get('tenant_id', 0)
        invite_code = context.user_data.get('invite_code')
        # ── Final plan limit check (safety net) ──
        cap = await db.can_add_agent(tenant_id)
        if not cap['allowed']:
            await update.message.reply_text(
                f"⚠️ <b>Cannot join — team is full</b>\n\n"
                f"{cap['reason']}\n\n"
                f"Ask the firm owner to upgrade, then /start again.",
                parse_mode=ParseMode.HTML)
            context.user_data.clear()
            return ConversationHandler.END
        agent_id = await db.upsert_agent(
            telegram_id=user_id, name=name, phone=phone,
            email=email, tenant_id=tenant_id, role='agent')
        if invite_code:
            await db.use_invite_code(invite_code)
        await db.log_audit("agent_joined", f"Via invite: {invite_code}",
                           tenant_id=tenant_id, agent_id=agent_id)
        extra = (f"\n🏢 Firm: {h(firm)}"
                 f"\n👤 Role: Agent")

    # Mark onboarding complete
    await db.update_agent_onboarding(user_id, None)

    # Use the language chosen during onboarding (or default to English)
    chosen_lang = context.user_data.get('lang', 'en')
    # Save the chosen language to the agent record
    try:
        await db.update_agent_lang(agent_id, chosen_lang)
    except Exception:
        pass  # Non-critical — default is 'en'

    await update.message.reply_text(
        i18n.t(chosen_lang, "registration_done",
               name=h(name), phone=h(phone), agent_id=agent_id)
        + extra,
        parse_mode=ParseMode.HTML,
    )

    # ── Determine if user is on master bot vs their own tenant bot ──
    is_master = context.bot_data.get('_is_master', True)

    # ── Plan awareness: show trial info + plan options to new owners ──
    if role == 'owner' and not context.user_data.get('web_signup'):
        await update.message.reply_text(
            "🎉 <b>You're on a 14-day FREE trial!</b>\n\n"
            "During your trial you get full access to:\n"
            "• Lead management & pipeline tracking\n"
            "• WhatsApp greetings & calculators\n"
            "• Policy tracking & renewal reminders\n"
            "• PDF reports & dashboard\n\n"
            "📋 <b>Plans after trial:</b>\n"
            "├ 🧑 Solo Advisor — ₹199/mo (1 advisor)\n"
            "├ 👥 Team — ₹799/mo (Admin + 5 advisors)\n"
            "└ 🏢 Enterprise — ₹1,999/mo (Admin + 25 advisors)\n\n"
            "💳 Upgrade anytime at <b>sarathi-ai.com</b>\n"
            "or use /plans to see details.\n\n"
            "⏰ We'll remind you before your trial ends. Enjoy! 🚀",
            parse_mode=ParseMode.HTML)

    # ── Master bot: show guided setup (guide FIRST) instead of full CRM menu ──
    if is_master and role == 'owner' and not context.user_data.get('web_signup'):
        context.user_data['_onboard_tenant_id'] = tenant_id
        await update.message.reply_text(
            i18n.t(chosen_lang, "connect_bot_warning"),
            parse_mode=ParseMode.HTML)
        return await _show_bot_guide_prompt(update, context, is_new=True)

    # ── Tenant bot or web-signup: show full CRM menu ──
    await update.message.reply_text(
        i18n.t(chosen_lang, "tap_to_start_msg"),
        parse_mode=ParseMode.HTML,
        reply_markup=_main_menu_keyboard(chosen_lang),
    )

    context.user_data.clear()
    return ConversationHandler.END


async def onboard_bot_token_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot token yes/skip/guide selection after registration."""
    query = update.callback_query
    await query.answer()

    if query.data == "onboard_bottoken_skip":
        server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
        await query.edit_message_text(
            "👍 No problem! You can connect your bot anytime from:\n"
            f"• 🌐 Web dashboard: {server_url}/dashboard\n"
            "• Or come back here and send /start\n\n"
            "⚠️ <b>Remember:</b> The full CRM (leads, pipeline, "
            "calculators) will only work on YOUR own bot.\n"
            "This master bot is for registration only.\n\n"
            "Enjoy your trial! 🚀",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True)
        context.user_data.clear()
        return ConversationHandler.END

    if query.data == "onboard_botguide":
        # Show detailed step-by-step guide
        bot_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 I have my token — Connect Now",
                                  callback_data="onboard_bottoken_yes")],
            [InlineKeyboardButton("⏭️ I'll do it later",
                                  callback_data="onboard_bottoken_skip")],
        ])
        await query.edit_message_text(
            "📖 <b>How to Create Your Own Telegram Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Step 1:</b> Open @BotFather\n"
            "• Search for <b>@BotFather</b> in Telegram\n"
            "• It's the official Telegram bot for creating bots\n"
            "• Look for the ✅ verified badge\n\n"
            "<b>Step 2:</b> Create a new bot\n"
            "• Send <code>/newbot</code> to @BotFather\n"
            "• Choose a <b>display name</b> (e.g., \"Sonal Financial Advisors\")\n"
            "• Choose a <b>username</b> ending in 'bot'\n"
            "  (e.g., <code>SonalAdvisorsBot</code>)\n\n"
            "<b>Step 3:</b> Copy the token\n"
            "• BotFather will give you a message like:\n"
            "  <code>123456789:ABCdefGHI-jklMNOpqrSTUvwx</code>\n"
            "• <b>Copy this entire token</b>\n\n"
            "<b>Step 4:</b> Come back here\n"
            "• Tap \"Connect Now\" below\n"
            "• Paste the token\n"
            "• Done! Your CRM bot is ready ✅\n\n"
            "⏱️ Total time: <b>~2 minutes</b>\n\n"
            "👇 <b>Ready?</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=bot_kb,
        )
        return ONBOARD_BOT_TOKEN

    # User wants to connect their bot
    await query.edit_message_text(
        "🤖 <b>Paste Your Bot Token</b>\n\n"
        "Open @BotFather → find your bot → copy the token.\n"
        "It looks like: <code>123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>\n\n"
        "📋 Paste it below:",
        parse_mode=ParseMode.HTML)
    return ONBOARD_BOT_TOKEN


async def onboard_bot_token_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate a bot token during onboarding."""
    token = update.message.text.strip()

    # Basic format check: number:alphanumeric
    import re
    if not re.match(r'^\d+:[A-Za-z0-9_-]{30,}$', token):
        lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(lang, "bot_token_invalid_format"),
            parse_mode=ParseMode.HTML)
        return ONBOARD_BOT_TOKEN

    # Validate token by calling Telegram getMe
    from telegram import Bot
    try:
        test_bot = Bot(token=token)
        bot_info = await test_bot.get_me()
    except Exception:
        lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(lang, "bot_token_invalid"))
        return ONBOARD_BOT_TOKEN

    # Token is valid — save to tenant
    tenant_id = context.user_data.get('_onboard_tenant_id')
    if tenant_id:
        await db.update_tenant(tenant_id, tg_bot_token=token)
        await db.log_audit("bot_token_connected",
                           f"@{bot_info.username} via onboarding",
                           tenant_id=tenant_id)

    lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(
        i18n.t(lang, "bot_connected_success", bot_username=bot_info.username),
        parse_mode=ParseMode.HTML)

    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  ONBOARD: Link Web Account — Phone + OTP verification
# =============================================================================

async def onboard_link_web_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive phone number for web account linking."""
    import re as _re
    import aiosqlite
    phone = update.message.text.strip().replace(" ", "").replace("-", "")
    # Remove +91 prefix if present
    if phone.startswith("+91"):
        phone = phone[3:]
    elif phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]

    if not _re.match(r'^[6-9]\d{9}$', phone):
        lang = context.user_data.get('lang', 'en')
        if lang == 'hi':
            await update.message.reply_text("❌ अमान्य फ़ोन नंबर। कृपया 10 अंकों का मोबाइल नंबर दर्ज करें:")
        else:
            await update.message.reply_text("❌ Invalid phone number. Please enter a 10-digit Indian mobile number:")
        return ONBOARD_LINK_WEB

    # Look up tenant by owner phone
    import biz_auth as auth
    tenant = None
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tenants WHERE phone = ? AND is_active = 1", (phone,))
        row = await cursor.fetchone()
        if row:
            tenant = dict(row)

    if not tenant:
        lang = context.user_data.get('lang', 'en')
        if lang == 'hi':
            await update.message.reply_text(
                "❌ इस फ़ोन नंबर से कोई वेब अकाउंट नहीं मिला।\n\n"
                "कृपया वो नंबर डालें जिससे आपने sarathi-ai.com पर साइनअप किया था, या /start दबाएं।")
        else:
            await update.message.reply_text(
                "❌ No web account found with this phone number.\n\n"
                "Please enter the phone you used to sign up at sarathi-ai.com, or press /start to go back.")
        return ONBOARD_LINK_WEB

    # Send OTP
    otp_result = auth.generate_otp(phone)
    if otp_result.get("error"):
        await update.message.reply_text(f"⚠️ {otp_result['error']}")
        return ONBOARD_LINK_WEB

    context.user_data['_link_phone'] = phone
    context.user_data['_link_tenant_id'] = tenant['tenant_id']
    context.user_data['_link_firm_name'] = tenant.get('firm_name', '')
    context.user_data['_otp_attempts'] = 0

    lang = context.user_data.get('lang', 'en')
    firm = tenant.get('firm_name', '')
    dev_mode = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes")
    if dev_mode:
        await update.message.reply_text(
            f"✅ {'मिला' if lang == 'hi' else 'Found'} <b>{h(firm)}</b>!\n\n"
            f"🔑 OTP: <code>{otp_result['otp']}</code>\n\n"
            f"{'कृपया OTP दर्ज करें:' if lang == 'hi' else 'Please enter the OTP:'}\n"
            f"{'रद्द करने के लिए /cancel टाइप करें' if lang == 'hi' else 'Type /cancel to abort'}",
            parse_mode=ParseMode.HTML)
    elif lang == 'hi':
        await update.message.reply_text(
            f"✅ <b>{h(firm)}</b> मिला!\n\n"
            f"📱 <b>{phone}</b> पर OTP भेजा गया है।\n"
            f"कृपया 6 अंकों का OTP दर्ज करें:\n"
            f"रद्द करने के लिए /cancel टाइप करें",
            parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            f"✅ Found <b>{h(firm)}</b>!\n\n"
            f"📱 OTP sent to <b>{phone}</b>.\n"
            f"Please enter the 6-digit OTP:\n"
            f"Type /cancel to abort",
            parse_mode=ParseMode.HTML)
    return ONBOARD_LINK_WEB_OTP


async def onboard_link_web_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify OTP and link web account to this Telegram user."""
    import biz_auth as auth
    otp = update.message.text.strip()
    phone = context.user_data.get('_link_phone', '')
    tenant_id = context.user_data.get('_link_tenant_id')
    firm_name = context.user_data.get('_link_firm_name', '')
    lang = context.user_data.get('lang', 'en')

    # Max attempts guard
    attempts = context.user_data.get('_otp_attempts', 0) + 1
    context.user_data['_otp_attempts'] = attempts
    if attempts > 5:
        if lang == 'hi':
            await update.message.reply_text(
                "❌ बहुत अधिक प्रयास। कृपया /start से दोबारा शुरू करें।")
        else:
            await update.message.reply_text(
                "❌ Too many attempts. Please type /start to try again.")
        context.user_data.clear()
        return ConversationHandler.END

    if not auth.verify_otp(phone, otp):
        remaining = 5 - attempts
        if lang == 'hi':
            await update.message.reply_text(
                f"❌ गलत OTP। कृपया फिर से प्रयास करें ({remaining} प्रयास शेष)\n"
                f"रद्द करने के लिए /cancel टाइप करें")
        else:
            await update.message.reply_text(
                f"❌ Invalid OTP. Please try again ({remaining} attempts left)\n"
                f"Type /cancel to abort")
        return ONBOARD_LINK_WEB_OTP

    # OTP verified! Link the Telegram account
    user_id = str(update.effective_user.id)

    # Find or create the agent link
    linked = await db.link_agent_telegram(phone, user_id)
    if not linked:
        # Fallback: direct DB update for agents with logout/unknown placeholders
        import aiosqlite
        try:
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute(
                    "UPDATE agents SET telegram_id = ?, updated_at = datetime('now') "
                    "WHERE phone = ? AND is_active = 1",
                    (user_id, phone))
                await conn.commit()
                linked = True
                logger.info("Direct-linked telegram %s to phone %s (fallback)",
                            user_id, phone[-4:])
        except Exception as e:
            logger.error("Fallback link failed: %s", e)
            linked = False

    if not linked:
        if lang == 'hi':
            await update.message.reply_text(
                "❌ अकाउंट लिंक करने में समस्या। कृपया /start से दोबारा प्रयास करें।")
        else:
            await update.message.reply_text(
                "❌ Could not link your account. Please type /start to try again.")
        context.user_data.clear()
        return ConversationHandler.END

    await db.update_tenant(tenant_id, owner_telegram_id=user_id)
    await db.log_audit("web_account_linked_via_telegram",
                       f"Phone: {phone}, Telegram: {user_id}",
                       tenant_id=tenant_id)
    _start_session(context)

    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
    if lang == 'hi':
        await update.message.reply_text(
            f"🎉 <b>सफलतापूर्वक लिंक हो गया!</b>\n\n"
            f"🏢 <b>{h(firm_name)}</b>\n"
            f"📱 फ़ोन: {phone}\n"
            f"✅ टेलीग्राम अकाउंट लिंक हो गया!\n\n"
            f"अब आप /start दबाकर बॉट मेनू से CRM चला सकते हैं।\n\n"
            f"🤖 अपना खुद का बॉट बनाने के लिए:\n"
            f"<b>Dashboard → Profile → Connect Bot</b>\n"
            f"🌐 {server_url}/dashboard",
            parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            f"🎉 <b>Successfully Linked!</b>\n\n"
            f"🏢 <b>{h(firm_name)}</b>\n"
            f"📱 Phone: {phone}\n"
            f"✅ Telegram account linked!\n\n"
            f"Press /start to access your CRM via bot menu.\n\n"
            f"🤖 To set up your own Telegram bot:\n"
            f"<b>Dashboard → Profile → Connect Bot</b>\n"
            f"🌐 {server_url}/dashboard",
            parse_mode=ParseMode.HTML)

    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  /addlead — ADD NEW LEAD (with duplicate detection)
# =============================================================================

@registered
async def cmd_addlead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the add-lead flow."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return ConversationHandler.END
    lang = agent.get('lang', 'en')
    context.user_data['lang'] = lang

    await update.message.reply_text(
        i18n.t(lang, "addlead_title"),
        parse_mode=ParseMode.HTML,
    )
    return LEAD_NAME


async def lead_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    # Reject menu button taps during conversation
    if _is_menu_button(name):
        hint = ("⚠️ आपने लीड जोड़ते समय मेन्यू बटन दबाया।\n"
                 "कृपया <b>नाम</b> दर्ज करें, या /cancel दबाएं।") if lang == 'hi' else (
                 "⚠️ You tapped a menu button while adding a lead.\n"
                 "Please type the <b>prospect's full name</b>, or /cancel to exit.")
        await update.message.reply_text(hint,
            parse_mode=ParseMode.HTML,
            reply_markup=_conv_recovery_keyboard(lang))
        return LEAD_NAME
    if len(name) < 2 or len(name) > 100:
        await update.message.reply_text(
            "\u274c Name must be 2-100 characters. Please enter the lead's full name.")
        return LEAD_NAME
    context.user_data['lead_name'] = name
    lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(
        i18n.t(lang, "ask_lead_phone"),
        parse_mode=ParseMode.HTML)
    return LEAD_PHONE


async def lead_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    # Reject menu button taps
    if _is_menu_button(text):
        hint = ("⚠️ आपने लीड जोड़ते समय मेन्यू बटन दबाया।\n"
                 "कृपया <b>फ़ोन नंबर</b> दर्ज करें, या /cancel दबाएं।") if lang == 'hi' else (
                 "⚠️ You tapped a menu button while adding a lead.\n"
                 "Please enter the <b>phone number</b>, or /cancel to exit.")
        await update.message.reply_text(hint,
            parse_mode=ParseMode.HTML,
            reply_markup=_conv_recovery_keyboard(lang))
        return LEAD_PHONE
    # Phone is mandatory — validate
    phone = _valid_phone(text)
    if not phone:
        await update.message.reply_text(
            i18n.t(lang, "invalid_phone"),
            parse_mode=ParseMode.HTML)
        return LEAD_PHONE
    context.user_data['lead_phone'] = phone

    # ── Duplicate detection ──
    agent = await _get_agent(update)
    if agent:
        # Check within this agent's leads
        dup = await db.find_duplicate_lead(agent['agent_id'], phone)
        if dup:
            keyboard = [
                [InlineKeyboardButton("👤 View Existing Lead",
                                      callback_data=f"leadview_{dup['lead_id']}")],
                [InlineKeyboardButton("➕ Add Anyway (different person)",
                                      callback_data="dup_continue")],
                [InlineKeyboardButton("❌ Cancel",
                                      callback_data="dup_cancel")],
            ]
            await update.message.reply_text(
                f"⚠️ <b>Duplicate Detected!</b>\n\n"
                f"A lead with phone <b>{h(phone)}</b> already exists:\n"
                f"👤 <b>#{dup['lead_id']}</b> {h(dup['name'])}\n"
                f"📊 Stage: {h(dup['stage'])}\n\n"
                f"What would you like to do?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML)
            return LEAD_PHONE_CONFIRM
        # Also check tenant-wide
        tenant_dup = await db.find_duplicate_lead_tenant(
            agent.get('tenant_id', 0), phone)
        if tenant_dup and tenant_dup['agent_id'] != agent['agent_id']:
            await update.message.reply_text(
                f"ℹ️ Note: This phone is already a lead of "
                f"<b>{h(tenant_dup.get('agent_name', 'another agent'))}</b> "
                f"in your firm. Proceeding to add under your name.",
                parse_mode=ParseMode.HTML)

    await update.message.reply_text(
        i18n.t(lang, "ask_dob"),
        parse_mode=ParseMode.HTML)
    return LEAD_DOB


async def lead_phone_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle duplicate detection buttons."""
    query = update.callback_query
    await query.answer()

    if query.data == "dup_cancel":
        await query.edit_message_text("❌ Lead addition cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    elif query.data == "dup_continue":
        lang = context.user_data.get('lang', 'en')
        await query.edit_message_text(
            "✅ Continuing with new lead.\n\n"
            + i18n.t(lang, "ask_dob"),
            parse_mode=ParseMode.HTML)
        return LEAD_DOB
    elif query.data.startswith("leadview_"):
        # View existing lead — end conversation
        await query.edit_message_text("Use /lead to view the existing lead details.")
        context.user_data.clear()
        return ConversationHandler.END
    return LEAD_PHONE_CONFIRM


async def lead_dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    # Reject menu button taps
    if _is_menu_button(text):
        hint = ("⚠️ आपने लीड जोड़ते समय मेन्यू बटन दबाया।\n"
                 "कृपया <b>जन्म तिथि</b> (DD-MM-YYYY) दर्ज करें, या /cancel दबाएं।") if lang == 'hi' else (
                 "⚠️ You tapped a menu button while adding a lead.\n"
                 "Please enter the <b>Date of Birth</b> (DD-MM-YYYY), or /cancel to exit.")
        await update.message.reply_text(hint,
            parse_mode=ParseMode.HTML,
            reply_markup=_conv_recovery_keyboard(lang))
        return LEAD_DOB
    # DOB is mandatory
    try:
        dt = _parse_date(text)
        if dt > datetime.now():
            await update.message.reply_text(
                "❌ DOB cannot be in the future. Try again (DD-MM-YYYY).")
            return LEAD_DOB
        if dt.year < 1900:
            await update.message.reply_text(
                "❌ Invalid year. Try again (DD-MM-YYYY).")
            return LEAD_DOB
        context.user_data['lead_dob'] = dt.isoformat()
    except ValueError:
        await update.message.reply_text(i18n.t(lang, "invalid_dob"),
                                        parse_mode=ParseMode.HTML)
        return LEAD_DOB
    await update.message.reply_text(
        i18n.t(lang, "ask_anniversary"),
        parse_mode=ParseMode.HTML)
    return LEAD_ANNIVERSARY


async def lead_anniversary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    if text == '/skip':
        context.user_data['lead_anniversary'] = None
    else:
        try:
            dt = _parse_date(text)
            if dt > datetime.now():
                await update.message.reply_text(
                    "\u274c Anniversary cannot be in the future. Try again or /skip.")
                return LEAD_ANNIVERSARY
            if dt.year < 1900:
                await update.message.reply_text(
                    "\u274c Invalid year. Try again or /skip.")
                return LEAD_ANNIVERSARY
            context.user_data['lead_anniversary'] = dt.isoformat()
        except ValueError:
            await update.message.reply_text(i18n.t(lang, "invalid_date"))
            return LEAD_ANNIVERSARY
    await update.message.reply_text(
        i18n.t(lang, "ask_city"),
        parse_mode=ParseMode.HTML)
    return LEAD_CITY


async def lead_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['lead_city'] = None if text == '/skip' else text
    lang = context.user_data.get('lang', 'en')

    context.user_data['lead_needs'] = []  # multi-select list
    keyboard = _needs_keyboard([])
    await update.message.reply_text(
        i18n.t(lang, "ask_needs"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return LEAD_NEED


async def lead_need_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "need_done":
        # Finished selecting needs
        await query.answer()
        selected = context.user_data.get('lead_needs', [])
        if not selected:
            await query.answer("Please select at least one need", show_alert=True)
            return LEAD_NEED
        label = ", ".join(selected)
        context.user_data['lead_need'] = label
        lang = context.user_data.get('lang', 'en')
        await query.edit_message_text(
            i18n.t(lang, "needs_selected", label=h(label))
            + "\n\n" + i18n.t(lang, "ask_lead_email"),
            parse_mode=ParseMode.HTML)
        return LEAD_EMAIL

    # Toggle a need on/off
    need = data.replace("need_", "")
    selected = context.user_data.get('lead_needs', [])
    if need in selected:
        selected.remove(need)
    else:
        selected.append(need)
    context.user_data['lead_needs'] = selected

    keyboard = _needs_keyboard(selected)
    await query.answer(f"{'Added' if need in selected else 'Removed'}: {need}")
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(keyboard))
    return LEAD_NEED


async def lead_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive lead email (optional — /skip allowed)."""
    text = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    if text == '/skip':
        context.user_data['lead_email'] = None
    else:
        email = _valid_email(text)
        if not email:
            await update.message.reply_text(
                i18n.t(lang, "invalid_email") + "\n<i>(or /skip)</i>",
                parse_mode=ParseMode.HTML)
            return LEAD_EMAIL
        context.user_data['lead_email'] = email
    await update.message.reply_text(
        i18n.t(lang, "ask_notes"),
        parse_mode=ParseMode.HTML)
    return LEAD_NOTES


async def lead_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    notes = None if text == '/skip' else text

    agent = await _get_agent(update)
    if not agent:
        return ConversationHandler.END

    # Save lead
    lead_id = await db.add_lead(
        agent_id=agent['agent_id'],
        name=context.user_data.get('lead_name', 'Unknown'),
        phone=context.user_data.get('lead_phone'),
        whatsapp=context.user_data.get('lead_phone'),  # Same as phone for now
        email=context.user_data.get('lead_email'),
        dob=context.user_data.get('lead_dob'),
        anniversary=context.user_data.get('lead_anniversary'),
        city=context.user_data.get('lead_city'),
        need_type=context.user_data.get('lead_need', 'health'),
        notes=notes,
    )

    # DPDP consent: auto-mark as agent-collected consent
    try:
        await db.mark_lead_dpdp_consent(lead_id)
    except Exception:
        pass

    name = context.user_data.get('lead_name', 'Unknown')
    lang = context.user_data.get('lang', 'en')

    if lang == 'hi':
        keyboard = [
            [InlineKeyboardButton("📝 फॉलो-अप लॉग करें",
                                  callback_data=f"fusel_{lead_id}")],
            [InlineKeyboardButton("🔄 स्टेज बदलें",
                                  callback_data=f"quickconv_{lead_id}")],
            [InlineKeyboardButton("📊 कैलकुलेटर खोलें",
                                  callback_data="calc_menu")],
            [InlineKeyboardButton("👤 लीड विवरण देखें",
                                  callback_data=f"leadview_{lead_id}")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Log Follow-up",
                                  callback_data=f"fusel_{lead_id}")],
            [InlineKeyboardButton("🔄 Move Stage",
                                  callback_data=f"quickconv_{lead_id}")],
            [InlineKeyboardButton("📊 Open Calculators",
                                  callback_data="calc_menu")],
            [InlineKeyboardButton("👤 View Lead Detail",
                                  callback_data=f"leadview_{lead_id}")],
        ]

    await update.message.reply_text(
        i18n.t(lang, "lead_added",
               lead_id=lead_id, name=h(name),
               phone=h(context.user_data.get('lead_phone', 'N/A')),
               need=h(context.user_data.get('lead_need', 'health'))),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  /pipeline — SALES PIPELINE VIEW
# =============================================================================

@registered
async def cmd_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show sales pipeline overview."""
    agent = await _get_agent(update)
    if not agent:
        return

    pipeline = await db.get_pipeline_summary(agent['agent_id'])
    stats = await db.get_agent_stats(agent['agent_id'])

    lang = agent.get('lang', 'en')
    hi = lang == 'hi'

    # Pipeline stage emojis and labels
    stages = [
        ('🎯', 'संभावित' if hi else 'Prospect', 'prospect'),
        ('📞', 'संपर्क किया' if hi else 'Contacted', 'contacted'),
        ('📊', 'पिच किया' if hi else 'Pitched', 'pitched'),
        ('📄', 'प्रस्ताव भेजा' if hi else 'Proposal Sent', 'proposal_sent'),
        ('🤝', 'बातचीत' if hi else 'Negotiation', 'negotiation'),
    ]

    lines = [i18n.t(lang, "pipeline_title")]
    total_active = 0
    for emoji, label, key in stages:
        count = pipeline.get(key, 0)
        total_active += count
        bar = "█" * min(count, 15) + f" {count}" if count else "░ 0"
        lines.append(f"{emoji} {label}:\n   {bar}\n")

    won = pipeline.get('closed_won', 0)
    lost = pipeline.get('closed_lost', 0)
    lines.append(f"\n✅ {'जीते' if hi else 'Won'}: {won}  |  ❌ {'हारे' if hi else 'Lost'}: {lost}")
    lines.append(f"📋 {'सक्रिय लीड्स' if hi else 'Active Leads'}: {total_active}")
    lines.append(f"📈 {'रूपांतरण' if hi else 'Conversion'}: {_conversion_rate(won, won + lost)}")
    lines.append(f"\n💰 {'सक्रिय पॉलिसी' if hi else 'Active Policies'}: {stats.get('active_policies', 0)}")
    lines.append(f"💳 {'कुल प्रीमियम' if hi else 'Total Premium'}: ₹{stats.get('total_premium', 0):,.0f}")

    if hi:
        keyboard = [
            [InlineKeyboardButton("📋 संभावित देखें", callback_data="stage_prospect"),
             InlineKeyboardButton("📊 पिच देखें", callback_data="stage_pitched")],
            [InlineKeyboardButton("📄 प्रस्ताव", callback_data="stage_proposal_sent"),
             InlineKeyboardButton("🏆 जीते हुए", callback_data="stage_closed_won")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 View Prospects", callback_data="stage_prospect"),
             InlineKeyboardButton("📊 View Pitched", callback_data="stage_pitched")],
            [InlineKeyboardButton("📄 Proposals", callback_data="stage_proposal_sent"),
             InlineKeyboardButton("🏆 Closed Won", callback_data="stage_closed_won")],
        ]

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


# =============================================================================
#  /leads — SEARCH & BROWSE LEADS
# =============================================================================

@registered
async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search or list leads."""
    agent = await _get_agent(update)
    if not agent:
        return

    lang = agent.get('lang', 'en')
    hi = lang == 'hi'
    is_admin = agent.get('role') in ('owner', 'admin')

    # Check if search query provided
    args = context.args
    if args:
        query = " ".join(args)
        if is_admin:
            result = await db.get_leads_by_tenant(agent['tenant_id'], search=query)
            leads = result['leads']
        else:
            leads = await db.search_leads(agent['agent_id'], query)
        title = f"🔍 {'खोज' if hi else 'Search'}: '{h(query)}'"
    else:
        if is_admin:
            result = await db.get_leads_by_tenant(agent['tenant_id'])
            leads = result['leads']
            title = "📋 टीम के सभी लीड्स" if hi else "📋 All Team Leads"
        else:
            leads = await db.get_leads_by_agent(agent['agent_id'])
            title = "📋 सभी लीड्स" if hi else "📋 All Leads"

    if not leads:
        await update.message.reply_text(
            f"{title}\n\n{i18n.t(lang, 'no_leads')}")
        return

    _results = 'परिणाम' if hi else 'results'
    lines = [f"{title} ({len(leads)} {_results})\n"]
    keyboard = []
    for lead in leads[:15]:
        stage_emoji = _stage_emoji(lead['stage'])
        agent_tag = ""
        if is_admin and lead.get('agent_name'):
            agent_tag = f" 👤{h(lead['agent_name'])}"
        lines.append(
            f"{stage_emoji} <b>#{lead['lead_id']}</b> {h(lead['name'])}{agent_tag}\n"
            f"   📱 {h(lead.get('phone', 'N/A'))} | "
            f"{h(lead.get('need_type', 'health'))} | "
            f"{h(lead['stage'])}"
        )
        keyboard.append([InlineKeyboardButton(
            f"👤 #{lead['lead_id']} {lead['name']}",
            callback_data=f"leadview_{lead['lead_id']}")])

    if len(leads) > 15:
        _more = f"...और {len(leads) - 15} और। /leads नाम से खोजें।" if hi else \
                f"...and {len(leads) - 15} more. Use /leads name to search."
        lines.append(f"\n{_more}")

    _tap = "नीचे नाम टैप करें विवरण देखने के लिए:" if hi else "Tap a name below to view full details:"
    lines.append(f"\n<i>{_tap}</i>")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


# =============================================================================
#  /mytasks — VIEW MY TASKS WITH DATE FILTERS
# =============================================================================

@registered
async def cmd_mytasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show task date filter buttons."""
    agent = await _get_agent(update)
    if not agent:
        return
    lang = agent.get('lang', 'en')
    hi = lang == 'hi'

    keyboard = [
        [InlineKeyboardButton("📅 " + ("आज" if hi else "Today"), callback_data="mytasks_today"),
         InlineKeyboardButton("⏩ " + ("कल" if hi else "Tomorrow"), callback_data="mytasks_tomorrow")],
        [InlineKeyboardButton("⚠️ " + ("ओवरड्यू" if hi else "Overdue"), callback_data="mytasks_overdue"),
         InlineKeyboardButton("📋 " + ("इस हफ़्ते" if hi else "This Week"), callback_data="mytasks_week")],
        [InlineKeyboardButton("⏪ " + ("बीता कल" if hi else "Yesterday"), callback_data="mytasks_yesterday"),
         InlineKeyboardButton("✅ " + ("पूरे हुए" if hi else "Completed"), callback_data="mytasks_done")],
    ]

    title = "📋 <b>" + ("मेरे टास्क" if hi else "My Tasks") + "</b>\n\n"
    title += ("नीचे से चुनें कौन से टास्क देखने हैं:" if hi else "Choose which tasks to view:")

    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        await msg.reply_text(title, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def _mytasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mytasks date filter button clicks."""
    query = update.callback_query
    await query.answer()
    agent = await db.get_agent(str(query.from_user.id))
    if not agent:
        return

    lang = agent.get('lang', 'en')
    hi = lang == 'hi'
    data = query.data  # mytasks_today, mytasks_tomorrow, etc.
    filter_key = data.replace("mytasks_", "")

    from datetime import datetime as _dt_cls, timedelta
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    now = _dt_cls.now(ist)

    # Map filter to date/status params
    target_date = None
    status = "pending"
    label = ""

    if filter_key == "today":
        target_date = now.strftime("%Y-%m-%d")
        label = "📅 " + ("आज के टास्क" if hi else "Today's Tasks")
    elif filter_key == "tomorrow":
        target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        label = "⏩ " + ("कल के टास्क" if hi else "Tomorrow's Tasks")
    elif filter_key == "yesterday":
        target_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        status = "all"
        label = "⏪ " + ("बीता कल" if hi else "Yesterday's Tasks")
    elif filter_key == "overdue":
        target_date = "overdue"
        label = "⚠️ " + ("ओवरड्यू टास्क" if hi else "Overdue Tasks")
    elif filter_key == "week":
        # Show all pending (next 7 days default from DB)
        target_date = None
        label = "📋 " + ("इस हफ़्ते के टास्क" if hi else "This Week's Tasks")
    elif filter_key == "done":
        target_date = None
        status = "done"
        label = "✅ " + ("पूरे हुए टास्क" if hi else "Completed Tasks")

    agent_id = agent['agent_id']
    tasks = await db.get_tasks_by_date(agent_id=agent_id, target_date=target_date, status=status, limit=15)

    if not tasks:
        no_msg = "🎉 " + ("कोई टास्क नहीं!" if hi else "No tasks found!")
        keyboard = [[InlineKeyboardButton("🔙 " + ("वापस" if hi else "Back"), callback_data="mytasks_back")]]
        await query.edit_message_text(f"<b>{label}</b>\n\n{no_msg}",
                                       reply_markup=InlineKeyboardMarkup(keyboard),
                                       parse_mode=ParseMode.HTML)
        return

    today_str = now.strftime("%Y-%m-%d")
    lines = [f"<b>{label}</b> ({len(tasks)})\n"]
    for i, t in enumerate(tasks[:15], 1):
        lead_name = h(t.get('lead_name') or t.get('name') or '?')
        fd = t.get('follow_up_date', '')
        ft = t.get('follow_up_time', '')
        summary = h((t.get('summary') or '').replace(r'[', '').split(']')[-1].strip()[:80])
        is_done = t.get('follow_up_status') == 'done'
        is_overdue = bool(fd and fd < today_str and not is_done)

        status_icon = "✅" if is_done else ("⚠️" if is_overdue else "⏳")
        line = f"{status_icon} <b>{lead_name}</b>"
        if fd:
            line += f" | 📅 {fd[:10]}"
        if ft:
            line += f" {ft}"
        if summary:
            line += f"\n    📝 <i>{summary}</i>"
        lines.append(line)

    # Action buttons for pending tasks
    buttons = []
    if status != "done" and tasks:
        # Show "Mark Done" buttons for first 5 pending tasks
        for t in tasks[:5]:
            if t.get('follow_up_status') != 'done':
                lead_name = (t.get('lead_name') or '?')[:15]
                buttons.append([InlineKeyboardButton(
                    f"✅ {lead_name}",
                    callback_data=f"taskdone_{t['lead_id']}_{t['interaction_id']}"
                )])
    buttons.append([InlineKeyboardButton("🔙 " + ("वापस" if hi else "Back"), callback_data="mytasks_back")])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML)


async def _taskdone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task done button from /mytasks view."""
    query = update.callback_query
    await query.answer()
    agent = await db.get_agent(str(query.from_user.id))
    if not agent:
        return

    lang = agent.get('lang', 'en')
    hi = lang == 'hi'

    parts = query.data.split("_")  # taskdone_leadid_iid
    if len(parts) < 3:
        return
    try:
        iid = int(parts[2])
    except (ValueError, IndexError):
        return

    success = await db.mark_followup_done(iid)
    if success:
        await query.answer("✅ " + ("टास्क पूरा!" if hi else "Task done!"), show_alert=True)
        # Refresh the list — simulate pressing today filter
        query.data = "mytasks_today"
        await _mytasks_callback(update, context)
    else:
        await query.answer("❌ " + ("असफल" if hi else "Failed"), show_alert=True)


async def _mytasks_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button — show task filters again."""
    query = update.callback_query
    await query.answer()
    agent = await db.get_agent(str(query.from_user.id))
    if not agent:
        return
    lang = agent.get('lang', 'en')
    hi = lang == 'hi'

    keyboard = [
        [InlineKeyboardButton("📅 " + ("आज" if hi else "Today"), callback_data="mytasks_today"),
         InlineKeyboardButton("⏩ " + ("कल" if hi else "Tomorrow"), callback_data="mytasks_tomorrow")],
        [InlineKeyboardButton("⚠️ " + ("ओवरड्यू" if hi else "Overdue"), callback_data="mytasks_overdue"),
         InlineKeyboardButton("📋 " + ("इस हफ़्ते" if hi else "This Week"), callback_data="mytasks_week")],
        [InlineKeyboardButton("⏪ " + ("बीता कल" if hi else "Yesterday"), callback_data="mytasks_yesterday"),
         InlineKeyboardButton("✅ " + ("पूरे हुए" if hi else "Completed"), callback_data="mytasks_done")],
    ]

    title = "📋 <b>" + ("मेरे टास्क" if hi else "My Tasks") + "</b>\n\n"
    title += ("नीचे से चुनें कौन से टास्क देखने हैं:" if hi else "Choose which tasks to view:")
    await query.edit_message_text(title, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


# =============================================================================
#  /followup <lead_id> — LOG INTERACTION
# =============================================================================

@registered
async def cmd_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start follow-up logging for a lead."""
    agent = await _get_agent(update)
    if not agent:
        return ConversationHandler.END

    lang = agent.get('lang', 'en')

    if context.args:
        arg = ' '.join(context.args).strip()
        # Try as lead ID first
        try:
            lead_id = int(arg)
            lead = await db.get_lead(lead_id)
            _is_admin = agent.get('role') in ('owner', 'admin')
            if lead and (lead['agent_id'] == agent['agent_id'] or _is_admin):
                context.user_data['followup_lead_id'] = lead_id
                context.user_data['followup_lead_name'] = lead['name']

                keyboard = [
                    [InlineKeyboardButton("📞 कॉल" if lang == 'hi' else "📞 Call", callback_data="fu_call")],
                    [InlineKeyboardButton("💬 मैसेज" if lang == 'hi' else "💬 Message", callback_data="fu_whatsapp")],
                    [InlineKeyboardButton("🤝 मीटिंग" if lang == 'hi' else "🤝 Meeting", callback_data="fu_meeting")],
                    [InlineKeyboardButton("📧 ईमेल" if lang == 'hi' else "📧 Email", callback_data="fu_email")],
                    [InlineKeyboardButton("📊 पिच" if lang == 'hi' else "📊 Pitch", callback_data="fu_pitch")],
                    [InlineKeyboardButton("📄 प्रस्ताव" if lang == 'hi' else "📄 Proposal", callback_data="fu_proposal")],
                ]
                await update.message.reply_text(
                    i18n.t(lang, "followup_type_ask", name=h(lead['name'])),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML,
                )
                return FOLLOWUP_TYPE
        except (ValueError, IndexError):
            pass

        # Try as name search
        if not arg.isdigit():
            leads = await db.get_leads_by_agent(agent['agent_id'])
            search_lower = arg.lower()
            matches = [l for l in leads if search_lower in l['name'].lower()]
            if matches:
                keyboard = []
                for lead in matches[:10]:
                    keyboard.append([InlineKeyboardButton(
                        f"#{lead['lead_id']} {lead['name']}",
                        callback_data=f"fusel_{lead['lead_id']}"
                    )])
                hi = lang == 'hi'
                await update.message.reply_text(
                    f"🔍 {'खोज परिणाम' if hi else 'Search results'} \"<b>{h(arg)}</b>\":\n"
                    f"{'लीड चुनें' if hi else 'Select a lead'}:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML,
                )
                return FOLLOWUP_LEAD
            else:
                await update.message.reply_text(
                    f"❌ {'कोई लीड नहीं मिली' if lang == 'hi' else 'No leads found for'} \"{h(arg)}\"")
                return ConversationHandler.END

    # No valid lead_id — show recent leads to pick from
    leads = await db.get_leads_by_agent(agent['agent_id'])
    if not leads:
        lang = agent.get('lang', 'en')
        await update.message.reply_text(i18n.t(lang, "no_leads"))
        return ConversationHandler.END

    keyboard = []
    for lead in leads[:8]:
        keyboard.append([InlineKeyboardButton(
            f"#{lead['lead_id']} {lead['name']}",
            callback_data=f"fusel_{lead['lead_id']}"
        )])

    lang = agent.get('lang', 'en')
    await update.message.reply_text(
        i18n.t(lang, "followup_title"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return FOLLOWUP_LEAD


async def followup_select_lead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle lead selection for follow-up."""
    query = update.callback_query
    await query.answer()
    lead_id = int(query.data.replace("fusel_", ""))
    agent = await db.get_agent(str(query.from_user.id))
    if not agent:
        _lang = context.user_data.get('lang', 'en')
        await query.edit_message_text(i18n.t(_lang, "register_first"))
        return ConversationHandler.END
    lead = await db.get_lead(lead_id)
    _is_admin = agent.get('role') in ('owner', 'admin')
    if not lead or (lead['agent_id'] != agent['agent_id'] and not _is_admin):
        lang = agent.get('lang', 'en')
        await query.edit_message_text(i18n.t(lang, "lead_not_found_access"))
        return ConversationHandler.END

    context.user_data['followup_lead_id'] = lead_id
    context.user_data['followup_lead_name'] = lead['name']

    lang = agent.get('lang', context.user_data.get('lang', 'en'))
    if lang == 'hi':
        keyboard = [
            [InlineKeyboardButton("📞 कॉल", callback_data="fu_call")],
            [InlineKeyboardButton("💬 व्हाट्सएप", callback_data="fu_whatsapp")],
            [InlineKeyboardButton("🤝 मीटिंग", callback_data="fu_meeting")],
            [InlineKeyboardButton("📧 ईमेल", callback_data="fu_email")],
            [InlineKeyboardButton("📊 पिच", callback_data="fu_pitch")],
            [InlineKeyboardButton("📄 प्रस्ताव", callback_data="fu_proposal")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📞 Call", callback_data="fu_call")],
            [InlineKeyboardButton("💬 WhatsApp", callback_data="fu_whatsapp")],
            [InlineKeyboardButton("🤝 Meeting", callback_data="fu_meeting")],
            [InlineKeyboardButton("📧 Email", callback_data="fu_email")],
            [InlineKeyboardButton("📊 Pitch", callback_data="fu_pitch")],
            [InlineKeyboardButton("📄 Proposal", callback_data="fu_proposal")],
        ]
    lang = context.user_data.get('lang', 'en')
    await query.edit_message_text(
        i18n.t(lang, "followup_type_ask", name=h(lead['name'])),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return FOLLOWUP_TYPE


async def followup_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interaction type selection."""
    query = update.callback_query
    await query.answer()
    fu_type = query.data.replace("fu_", "")
    context.user_data['followup_type'] = fu_type
    lang = context.user_data.get('lang', 'en')
    await query.edit_message_text(
        i18n.t(lang, "followup_notes_ask", type=h(fu_type)),
        parse_mode=ParseMode.HTML)
    return FOLLOWUP_NOTES


async def followup_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['followup_notes'] = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(
        i18n.t(lang, "followup_date_ask"),
        parse_mode=ParseMode.HTML)
    return FOLLOWUP_DATE


async def followup_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    follow_date = None
    if text != '/skip':
        try:
            follow_date = _parse_date(text).isoformat()
        except ValueError:
            await update.message.reply_text("❌ Invalid format. Use DD-MM-YYYY or /skip")
            return FOLLOWUP_DATE

    agent = await _get_agent(update)
    lead_id = context.user_data.get('followup_lead_id')
    lead = await db.get_lead(lead_id) if lead_id else None

    # For admin: assign to lead's agent, track admin as creator
    _is_admin = agent.get('role') in ('owner', 'admin')
    target_agent_id = (lead.get('agent_id') if lead else None) or agent['agent_id']
    created_by = agent['agent_id'] if _is_admin and target_agent_id != agent['agent_id'] else None

    # Duplicate detection — update existing task if one exists
    is_update = False
    if follow_date and lead_id:
        existing = await db.get_pending_followups_for_lead(lead_id)
        if existing:
            ef = existing[0]
            is_update = True
            await db.update_followup(
                interaction_id=ef['interaction_id'],
                follow_up_date=follow_date,
                summary=context.user_data.get('followup_notes', '') or None
            )
        else:
            await db.log_interaction(
                lead_id=lead_id,
                agent_id=target_agent_id,
                interaction_type=context.user_data.get('followup_type', 'call'),
                channel='telegram',
                summary=context.user_data.get('followup_notes', ''),
                follow_up_date=follow_date,
                created_by_agent_id=created_by
            )
    else:
        await db.log_interaction(
            lead_id=lead_id,
            agent_id=target_agent_id,
            interaction_type=context.user_data.get('followup_type', 'call'),
            channel='telegram',
            summary=context.user_data.get('followup_notes', ''),
            follow_up_date=follow_date,
            created_by_agent_id=created_by
        )

    # Cross-agent notification for admin-created follow-ups
    if _is_admin and created_by and target_agent_id != agent['agent_id'] and follow_date:
        try:
            target_agent = await db.get_agent_by_id(target_agent_id)
            if target_agent and target_agent.get('telegram_id'):
                admin_name = agent.get('name', 'Admin')
                lead_name = context.user_data.get('followup_lead_name', 'Lead')
                nlang = target_agent.get('lang', 'en')
                if nlang == 'hi':
                    ntxt = (f"📋 *{admin_name} ने फॉलो-अप बनाया*\n\n"
                            f"👤 लीड: {lead_name}\n📅 तारीख: {follow_date}")
                else:
                    ntxt = (f"📋 *{admin_name} created a follow-up*\n\n"
                            f"👤 Lead: {lead_name}\n📅 Date: {follow_date}")
                import biz_reminders as rem
                await rem._send_telegram(target_agent['telegram_id'], ntxt)
        except Exception as e:
            logger.warning("Failed to notify agent of admin follow-up: %s", e)

    lead_name = context.user_data.get('followup_lead_name', 'Lead')
    follow_msg = f"\n📅 Follow-up: {text}" if follow_date else ""

    lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(
        i18n.t(lang, "followup_done",
               name=h(lead_name),
               type=h(context.user_data.get('followup_type', 'call')),
               notes=h(context.user_data.get('followup_notes', ''))[:100],
               follow_msg=h(follow_msg)),
        parse_mode=ParseMode.HTML,
    )
    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  /convert <lead_id> — MOVE LEAD STAGE
# =============================================================================

@registered
async def cmd_convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Move a lead to the next pipeline stage."""
    agent = await _get_agent(update)
    if not agent:
        return ConversationHandler.END

    lang = agent.get('lang', 'en')
    if not context.args:
        await update.message.reply_text(
            i18n.t(lang, "usage_convert"),
            parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    try:
        lead_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(i18n.t(lang, "enter_valid_number", example="5"))
        return ConversationHandler.END

    lead = await db.get_lead(lead_id)
    if not lead or lead['agent_id'] != agent['agent_id']:
        await update.message.reply_text(i18n.t(lang, "lead_not_found_access"))
        return ConversationHandler.END

    context.user_data['convert_lead_id'] = lead_id
    current = lead['stage']

    lang = agent.get('lang', 'en')
    hi = lang == 'hi'
    keyboard = [
        [InlineKeyboardButton("📞 संपर्क किया" if hi else "📞 Contacted", callback_data="stg_contacted")],
        [InlineKeyboardButton("📊 पिच किया" if hi else "📊 Pitched", callback_data="stg_pitched")],
        [InlineKeyboardButton("📄 प्रस्ताव भेजा" if hi else "📄 Proposal Sent", callback_data="stg_proposal_sent")],
        [InlineKeyboardButton("🤝 बातचीत" if hi else "🤝 Negotiation", callback_data="stg_negotiation")],
        [InlineKeyboardButton("✅ जीते" if hi else "✅ CLOSED WON", callback_data="stg_closed_won")],
        [InlineKeyboardButton("❌ हारे" if hi else "❌ CLOSED LOST", callback_data="stg_closed_lost")],
    ]

    await update.message.reply_text(
        i18n.t(lang, "convert_title",
               name=h(lead['name']),
               stage_emoji=_stage_emoji(current),
               stage=h(current)),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return CONVERT_STAGE


async def convert_stage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stage selection."""
    query = update.callback_query
    await query.answer()
    new_stage = query.data.replace("stg_", "")
    lead_id = context.user_data.get('convert_lead_id')

    success = await db.update_lead_stage(lead_id, new_stage)
    if success:
        lead = await db.get_lead(lead_id)
        lang = context.user_data.get('lang', 'en')
        msg = i18n.t(lang, "stage_updated",
                     name=h(lead['name']),
                     stage_emoji=_stage_emoji(new_stage),
                     stage=h(new_stage))
        if new_stage == 'closed_won':
            if lang == 'hi':
                msg += f"\n\n🎉 बधाई! /policy {lead_id} से पॉलिसी रिकॉर्ड करें।"
            else:
                msg += f"\n\n🎉 Congratulations! Use /policy {lead_id} to record the policy."
            # Trigger proactive deal celebration
            import biz_reminders as _rem
            asyncio.create_task(_rem.run_deal_won_celebration(
                agent_id=context.user_data.get('_agent', {}).get('agent_id', 0),
                lead_name=lead['name'],
                premium=lead.get('premium_budget', 0) or 0))
    else:
        msg = "❌ स्टेज अपडेट विफल।" if lang == 'hi' else "❌ Failed to update stage."

    await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  /policy <lead_id> — RECORD SOLD POLICY
# =============================================================================

@registered
async def cmd_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start recording a new policy for a lead."""
    agent = await _get_agent(update)
    if not agent:
        return ConversationHandler.END

    lang = agent.get('lang', 'en')
    if not context.args:
        await update.message.reply_text(
            i18n.t(lang, "usage_policy"),
            parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    try:
        lead_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(i18n.t(lang, "enter_valid_number", example="5"))
        return ConversationHandler.END

    lead = await db.get_lead(lead_id)
    if not lead or lead['agent_id'] != agent['agent_id']:
        await update.message.reply_text(i18n.t(lang, "lead_not_found_access"))
        return ConversationHandler.END

    context.user_data['policy_lead_id'] = lead_id
    context.user_data['policy_lead_name'] = lead['name']
    context.user_data['lang'] = lang

    await update.message.reply_text(
        i18n.t(lang, "policy_title", name=h(lead['name'])),
        parse_mode=ParseMode.HTML)
    return POLICY_INSURER


async def policy_insurer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['policy_insurer'] = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(i18n.t(lang, "policy_plan_ask"), parse_mode=ParseMode.HTML)
    return POLICY_PLAN


async def policy_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['policy_plan'] = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    types = ['health', 'term', 'endowment', 'ulip', 'child', 'retirement', 'motor', 'investment', 'nps', 'general']
    kb = [[InlineKeyboardButton(t.title(), callback_data=f"poltype_{t}") for t in types[i:i+3]] for i in range(0, len(types), 3)]
    await update.message.reply_text(
        "📋 <b>Select policy type:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb))
    return POLICY_TYPE


async def policy_type_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ptype = q.data.replace("poltype_", "")
    context.user_data['policy_type'] = ptype
    lang = context.user_data.get('lang', 'en')
    await q.edit_message_text(f"✅ Type: <b>{ptype.title()}</b>\n\n" + i18n.t(lang, "policy_si_ask"), parse_mode=ParseMode.HTML)
    return POLICY_SI


async def policy_si(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'en')
    try:
        val = float(update.message.text.strip().replace(',', '').replace('₹', ''))
        if val <= 0:
            await update.message.reply_text(i18n.t(lang, "si_invalid"))
            return POLICY_SI
        if val > 1_000_000_000:
            await update.message.reply_text(i18n.t(lang, "si_too_high"))
            return POLICY_SI
        context.user_data['policy_si'] = val
    except ValueError:
        await update.message.reply_text(i18n.t(lang, "enter_valid_number", example="500000"))
        return POLICY_SI
    await update.message.reply_text(i18n.t(lang, "policy_premium_ask"), parse_mode=ParseMode.HTML)
    return POLICY_PREMIUM


async def policy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'en')
    try:
        val = float(update.message.text.strip().replace(',', '').replace('₹', ''))
        if val <= 0:
            await update.message.reply_text(i18n.t(lang, "premium_invalid"))
            return POLICY_PREMIUM
        if val > 100_000_000:
            await update.message.reply_text(i18n.t(lang, "premium_too_high"))
            return POLICY_PREMIUM
        context.user_data['policy_premium'] = val
    except ValueError:
        await update.message.reply_text(i18n.t(lang, "enter_valid_number", example="25000"))
        return POLICY_PREMIUM

    modes = ['monthly', 'quarterly', 'half-yearly', 'annual']
    kb = [[InlineKeyboardButton(m.title(), callback_data=f"polmode_{m}") for m in modes]]
    await update.message.reply_text(
        "📅 <b>Premium payment frequency?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb))
    return POLICY_MODE


async def policy_mode_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    mode = q.data.replace("polmode_", "")
    context.user_data['policy_mode'] = mode
    lang = context.user_data.get('lang', 'en')
    await q.edit_message_text(
        f"✅ Mode: <b>{mode.title()}</b>\n\n" + i18n.t(lang, "policy_start_ask"),
        parse_mode=ParseMode.HTML)
    return POLICY_START


async def policy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'en')
    try:
        dt = _parse_date(update.message.text.strip())
        context.user_data['policy_start'] = dt.isoformat()
    except ValueError:
        await update.message.reply_text(i18n.t(lang, "invalid_date_format"))
        return POLICY_START

    # Auto-calculate renewal from start + premium_mode
    mode = context.user_data.get('policy_mode', 'annual')
    _MODE_MONTHS = {'monthly': 1, 'quarterly': 3, 'half-yearly': 6, 'annual': 12}
    months = _MODE_MONTHS.get(mode, 12)
    m = dt.month - 1 + months
    y = dt.year + m // 12
    m = m % 12 + 1
    d = min(dt.day, [31,29 if y%4==0 and (y%100!=0 or y%400==0) else 28,
                      31,30,31,30,31,31,30,31,30,31][m-1])
    from datetime import date as _date
    auto_renewal = _date(y, m, d).isoformat()
    context.user_data['policy_auto_renewal'] = auto_renewal

    await update.message.reply_text(
        f"📅 Auto-calculated expiry: <b>{auto_renewal}</b> ({mode})\n\n"
        + i18n.t(lang, "policy_renewal_ask")
        + "\n\n<i>Send the date above to confirm, or enter a different date.</i>",
        parse_mode=ParseMode.HTML)
    return POLICY_RENEWAL


async def policy_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'en')
    try:
        dt = _parse_date(update.message.text.strip())
        # Logical check: renewal should be after start date
        start_str = context.user_data.get('policy_start', '')
        if start_str:
            start_dt = datetime.fromisoformat(start_str)
            if dt <= start_dt:
                await update.message.reply_text(i18n.t(lang, "renewal_before_start"))
                return POLICY_RENEWAL
        renewal_date = dt.isoformat()
    except ValueError:
        await update.message.reply_text(i18n.t(lang, "invalid_date_format"))
        return POLICY_RENEWAL

    agent = await _get_agent(update)
    lead_id = context.user_data.get('policy_lead_id')
    mode = context.user_data.get('policy_mode', 'annual')

    policy_id = await db.add_policy(
        lead_id=lead_id,
        agent_id=agent['agent_id'],
        insurer=context.user_data.get('policy_insurer'),
        plan_name=context.user_data.get('policy_plan'),
        policy_type=context.user_data.get('policy_type', 'health'),
        sum_insured=context.user_data.get('policy_si'),
        premium=context.user_data.get('policy_premium'),
        premium_mode=mode,
        start_date=context.user_data.get('policy_start'),
        renewal_date=renewal_date,
    )

    # Also mark lead as closed_won
    await db.update_lead_stage(lead_id, 'closed_won')

    # Trigger proactive deal celebration
    import biz_reminders as _rem
    asyncio.create_task(_rem.run_deal_won_celebration(
        agent_id=agent['agent_id'],
        lead_name=context.user_data.get('policy_lead_name', ''),
        premium=context.user_data.get('policy_premium', 0) or 0))

    await update.message.reply_text(
        i18n.t(lang, "policy_recorded") + "\n\n"
        f"🆔 Policy ID: {policy_id}\n"
        f"👤 Client: {h(context.user_data.get('policy_lead_name', ''))}\n"
        f"🏢 Insurer: {h(context.user_data.get('policy_insurer', ''))}\n"
        f"📋 Plan: {h(context.user_data.get('policy_plan', ''))}\n"
        f"🏷️ Type: {h(context.user_data.get('policy_type', 'health')).title()}\n"
        f"💰 SI: ₹{context.user_data.get('policy_si', 0):,.0f}\n"
        f"💳 Premium: ₹{context.user_data.get('policy_premium', 0):,.0f}/{mode}\n"
        f"🔄 Renewal: {h(renewal_date)}\n\n"
        f"✅ Lead → Closed Won",
        parse_mode=ParseMode.HTML,
    )
    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  /scan — AI DOCUMENT SCANNER (Photo/PDF → Extract Policy Data → Save to CRM)
# =============================================================================

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the document scan flow — ask user to send a policy photo or PDF."""
    agent = await _get_agent(update)
    if not agent:
        return ConversationHandler.END

    lang = agent.get('lang', 'en')
    context.user_data['lang'] = lang
    context.user_data['scan_agent_id'] = agent['agent_id']

    if lang == 'hi':
        text = (
            "📸 <b>AI डॉक्यूमेंट स्कैनर</b>\n\n"
            "पॉलिसी डॉक्यूमेंट की <b>फोटो</b> भेजें या <b>PDF</b> फाइल भेजें।\n"
            "AI स्वचालित रूप से सभी विवरण निकालेगा।\n\n"
            "❌ रद्द करने के लिए /cancel टैप करें"
        )
    else:
        text = (
            "📸 <b>AI Document Scanner</b>\n\n"
            "Send a <b>photo</b> of a policy document or forward a <b>PDF</b>.\n"
            "AI will automatically extract all the details.\n\n"
            "❌ Tap /cancel to abort"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    return SCAN_WAIT


async def cmd_scan_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /scan from inline menu button (menu_scan callback)."""
    query = update.callback_query
    await query.answer()
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    object.__setattr__(update, 'message', query.message)
    return await cmd_scan(update, context)


async def _scan_process_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo message in scan flow — extract policy via Gemini Vision."""
    lang = context.user_data.get('lang', 'en')
    wait_msg = await update.message.reply_text(
        "🔍 " + ("AI विश्लेषण कर रहा है..." if lang == 'hi' else "AI is analyzing the document..."))

    try:
        photo = update.message.photo[-1]  # highest resolution
        file = await photo.get_file()
        img_bytes = await file.download_as_bytearray()

        result = await ai.extract_policy_from_image(bytes(img_bytes))
    except Exception as e:
        logger.error(f"Scan photo download failed: {e}")
        result = {"_error": "Failed to process image"}

    return await _scan_show_result(update, context, result, wait_msg)


async def _scan_process_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document (PDF) message in scan flow — multi-page support."""
    lang = context.user_data.get('lang', 'en')
    doc = update.message.document

    # Only accept PDF and image files
    fname = (doc.file_name or "").lower()
    mime = (doc.mime_type or "").lower()
    is_pdf = fname.endswith('.pdf') or 'pdf' in mime
    is_image = mime.startswith('image/')

    if not is_pdf and not is_image:
        if lang == 'hi':
            await update.message.reply_text("⚠️ कृपया PDF या फोटो भेजें। CSV इम्पोर्ट के लिए /cancel करें।")
        else:
            await update.message.reply_text("⚠️ Please send a PDF or image file. For CSV import, /cancel first.")
        return SCAN_WAIT

    wait_msg = await update.message.reply_text(
        "🔍 " + ("AI विश्लेषण कर रहा है..." if lang == 'hi' else "AI is analyzing the document..."))

    try:
        file = await doc.get_file()
        file_bytes = await file.download_as_bytearray()

        if is_pdf:
            # Try text extraction first (all pages), fall back to image OCR
            try:
                import fitz  # PyMuPDF
                pdf_doc = fitz.open(stream=bytes(file_bytes), filetype="pdf")
                text = ""
                max_pages = min(len(pdf_doc), 5)  # first 5 pages
                for i in range(max_pages):
                    text += pdf_doc[i].get_text()

                if len(text.strip()) > 50:
                    result = await ai.extract_policy_from_document(text)
                else:
                    # Scanned PDF — render first 3 pages as images and concatenate
                    pages_to_render = min(len(pdf_doc), 3)
                    # Use first page for extraction (Gemini Vision)
                    page = pdf_doc[0]
                    pix = page.get_pixmap(dpi=200)
                    img_bytes = pix.tobytes("png")
                    result = await ai.extract_policy_from_image(img_bytes, mime_type="image/png")
                pdf_doc.close()
            except ImportError:
                # PyMuPDF not available — try as image
                result = await ai.extract_policy_from_image(bytes(file_bytes))
        else:
            # Image file
            result = await ai.extract_policy_from_image(bytes(file_bytes), mime_type=mime)
    except Exception as e:
        logger.error(f"Scan document processing failed: {e}")
        result = {"_error": "Failed to process document"}

    return await _scan_show_result(update, context, result, wait_msg)


async def _scan_show_result(update, context, result, wait_msg):
    """Display extracted data (client + policy + members) with confirm/cancel."""
    lang = context.user_data.get('lang', 'en')

    try:
        await wait_msg.delete()
    except Exception:
        pass

    if result.get('_error'):
        err = result['_error']
        if lang == 'hi':
            await update.message.reply_text(
                f"⚠️ AI एक्सट्रैक्शन विफल: {h(err)}\n\nदोबारा फोटो भेजें या /cancel करें।",
                parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(
                f"⚠️ AI extraction failed: {h(err)}\n\nSend another photo or /cancel.",
                parse_mode=ParseMode.HTML)
        return SCAN_CONFIRM  # stays in loop, user can resend

    # Store extracted data
    context.user_data['scan_data'] = result

    # Extract client and policy from new nested format
    client = result.get('client') or {}
    policy = result.get('policy') or {}
    members = result.get('insured_members') or []
    nominees = result.get('nominees') or []
    doc_type = result.get('document_type') or 'unknown'

    # Client fields
    cl_name = client.get('name') or '—'
    cl_phone = client.get('phone') or '—'
    cl_email = client.get('email') or '—'
    cl_dob = client.get('dob') or '—'
    cl_conf = client.get('confidence') or 'medium'

    # Policy fields
    insurer = policy.get('insurer') or '—'
    plan = policy.get('plan_name') or '—'
    ptype = policy.get('policy_type') or '—'
    pnum = policy.get('policy_number') or '—'
    si = policy.get('sum_insured')
    prem = policy.get('premium')
    mode = policy.get('premium_mode') or '—'
    start = policy.get('start_date') or '—'
    renewal = policy.get('renewal_date') or '—'
    riders = policy.get('riders') or '—'

    si_str = f"₹{si:,.0f}" if si else '—'
    prem_str = f"₹{prem:,.0f}" if prem else '—'

    # Confidence indicator
    conf_icon = {"high": "✅", "medium": "⚠️", "low": "❓"}.get(cl_conf, "⚠️")

    # Members display
    members_text = ""
    if members:
        for m in members[:6]:  # show up to 6
            m_name = m.get('name', '?')
            m_rel = m.get('relation', '?')
            m_age = m.get('age') or m.get('dob', '')
            age_str = f" ({m_age})" if m_age else ""
            members_text += f"  • {h(m_name)} — {h(m_rel)}{age_str}\n"

    if lang == 'hi':
        text = (
            f"✅ <b>AI ने ये विवरण निकाले:</b>\n\n"
            f"<b>👤 ग्राहक विवरण</b> {conf_icon}\n"
            f"  नाम: <b>{h(cl_name)}</b>\n"
            f"  फोन: <b>{h(cl_phone)}</b>\n"
            f"  ईमेल: <b>{h(cl_email)}</b>\n\n"
            f"<b>📋 पॉलिसी विवरण</b>\n"
            f"  🏢 बीमाकर्ता: <b>{h(insurer)}</b>\n"
            f"  📋 प्लान: <b>{h(plan)}</b>\n"
            f"  🏷️ प्रकार: <b>{h(ptype).title()}</b>\n"
            f"  🔢 नंबर: <b>{h(pnum)}</b>\n"
            f"  💰 बीमा राशि: <b>{si_str}</b>\n"
            f"  💳 प्रीमियम: <b>{prem_str}/{h(mode)}</b>\n"
            f"  📅 शुरू: <b>{h(start)}</b> · नवीनीकरण: <b>{h(renewal)}</b>\n"
        )
        if members_text:
            text += f"\n<b>👥 बीमित सदस्य</b>\n{members_text}"
        if riders != '—':
            text += f"\n🛡️ राइडर्स: <i>{h(riders)}</i>\n"
        text += "\nक्या ये विवरण सही हैं?"
    else:
        text = (
            f"✅ <b>AI extracted these details:</b>\n\n"
            f"<b>👤 Client</b> {conf_icon}\n"
            f"  Name: <b>{h(cl_name)}</b>\n"
            f"  Phone: <b>{h(cl_phone)}</b>\n"
            f"  Email: <b>{h(cl_email)}</b>\n\n"
            f"<b>📋 Policy</b>\n"
            f"  🏢 Insurer: <b>{h(insurer)}</b>\n"
            f"  📋 Plan: <b>{h(plan)}</b>\n"
            f"  🏷️ Type: <b>{h(ptype).title()}</b>\n"
            f"  🔢 Number: <b>{h(pnum)}</b>\n"
            f"  💰 Sum Insured: <b>{si_str}</b>\n"
            f"  💳 Premium: <b>{prem_str}/{h(mode)}</b>\n"
            f"  📅 Start: <b>{h(start)}</b> · Renewal: <b>{h(renewal)}</b>\n"
        )
        if members_text:
            text += f"\n<b>👥 Insured Members</b>\n{members_text}"
        if riders != '—':
            text += f"\n🛡️ Riders: <i>{h(riders)}</i>\n"
        text += "\nAre these details correct?"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ " + ("सही है — सेव करें" if lang == 'hi' else "Correct — Save"),
                              callback_data="scan_confirm"),
         InlineKeyboardButton("🔄 " + ("दोबारा स्कैन" if lang == 'hi' else "Re-scan"),
                              callback_data="scan_rescan")],
        [InlineKeyboardButton("❌ " + ("रद्द करें" if lang == 'hi' else "Cancel"),
                              callback_data="scan_cancel")],
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return SCAN_CONFIRM


async def _scan_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirm/rescan/cancel after scan result."""
    query = update.callback_query
    await query.answer()
    action = query.data
    lang = context.user_data.get('lang', 'en')

    if action == "scan_cancel":
        await query.edit_message_text("❌ " + ("स्कैन रद्द।" if lang == 'hi' else "Scan cancelled."))
        context.user_data.clear()
        return ConversationHandler.END

    if action == "scan_rescan":
        await query.edit_message_text(
            "📸 " + ("दूसरी फोटो या PDF भेजें:" if lang == 'hi' else "Send another photo or PDF:"))
        return SCAN_WAIT

    # scan_confirm — check if client already exists (auto-match by phone)
    agent_id = context.user_data.get('scan_agent_id')
    data = context.user_data.get('scan_data', {})
    client = data.get('client') or {}
    cl_phone = client.get('phone')
    cl_name = client.get('name') or ''

    # Try matching by phone number
    matched_lead = None
    if cl_phone:
        matched_lead = await db.find_lead_by_phone(agent_id, cl_phone)

    if matched_lead:
        # Found existing client — ask to confirm
        m_name = matched_lead['name']
        m_phone = matched_lead.get('phone') or '—'
        if lang == 'hi':
            text = (
                f"🔎 <b>मौजूदा ग्राहक मिला!</b>\n\n"
                f"👤 {h(m_name)} ({h(m_phone)})\n\n"
                f"क्या इस ग्राहक की प्रोफ़ाइल में पॉलिसी जोड़ें?"
            )
        else:
            text = (
                f"🔎 <b>Existing client found!</b>\n\n"
                f"👤 {h(m_name)} ({h(m_phone)})\n\n"
                f"Add this policy to their portfolio?"
            )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ " + ("हाँ, इसमें जोड़ें" if lang == 'hi' else "Yes, add to this client"),
                                  callback_data=f"scanld_{matched_lead['lead_id']}")],
            [InlineKeyboardButton("➕ " + ("नया ग्राहक बनाएं" if lang == 'hi' else "No, create new client"),
                                  callback_data="scanld_new")],
        ])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                      reply_markup=kb)
        return SCAN_CLIENT

    # No phone match — show recent leads + create new option
    leads = await db.get_leads_by_agent(agent_id)
    recent = leads[:8]

    buttons = []
    for ld in recent:
        name = ld['name'][:20]
        buttons.append([InlineKeyboardButton(
            f"👤 {name}", callback_data=f"scanld_{ld['lead_id']}")])
    buttons.append([InlineKeyboardButton(
        "➕ " + ("नया ग्राहक बनाएं" if lang == 'hi' else "Create New Client"),
        callback_data="scanld_new")])

    if lang == 'hi':
        text = ("👤 <b>किस ग्राहक से जोड़ें?</b>\n\n"
                + (f"ग्राहक: <b>{h(cl_name)}</b>\n" if cl_name else "")
                + "ग्राहक चुनें या नया बनाएं:")
    else:
        text = ("👤 <b>Link to which client?</b>\n\n"
                + (f"Detected client: <b>{h(cl_name)}</b>\n" if cl_name else "")
                + "Pick a client or create new:")

    await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup(buttons))
    return SCAN_CLIENT


async def _scan_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client selection — ask sold_by question next."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get('lang', 'en')
    agent_id = context.user_data.get('scan_agent_id')
    data = context.user_data.get('scan_data', {})
    client = data.get('client') or {}
    policy = data.get('policy') or {}

    choice = query.data.replace("scanld_", "")

    if choice == "new":
        # Create lead from AI-extracted client details (not insurer name!)
        cl_name = client.get('name')
        if not cl_name or cl_name == '—':
            cl_name = f"Client ({policy.get('insurer') or 'Unknown'})"

        lead_id = await db.add_lead(
            agent_id=agent_id,
            name=cl_name,
            phone=client.get('phone'),
            email=client.get('email'),
            dob=client.get('dob'),
            city=client.get('address'),
            need_type='review',
            notes=f"Auto-created from scanned {policy.get('policy_type', 'policy')} document",
            source="scan",
        )
        # Update client_type if we have a policy
        try:
            import aiosqlite
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute(
                    "UPDATE leads SET client_type='customer' WHERE lead_id=?", (lead_id,))
                if client.get('pan'):
                    await conn.execute(
                        "UPDATE leads SET pan_number=? WHERE lead_id=?",
                        (client['pan'], lead_id))
                if client.get('address'):
                    await conn.execute(
                        "UPDATE leads SET address=? WHERE lead_id=?",
                        (client['address'], lead_id))
                await conn.commit()
        except Exception:
            pass
    else:
        try:
            lead_id = int(choice)
        except ValueError:
            await query.edit_message_text("⚠️ Invalid selection.")
            context.user_data.clear()
            return ConversationHandler.END
        # Update existing lead to customer status if not already
        try:
            import aiosqlite
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute(
                    "UPDATE leads SET client_type='customer' WHERE lead_id=? AND client_type='prospect'",
                    (lead_id,))
                await conn.commit()
        except Exception:
            pass

    context.user_data['scan_lead_id'] = lead_id

    # Ask: Did you sell this policy?
    if lang == 'hi':
        text = "💼 <b>क्या यह पॉलिसी आपने बेची है?</b>"
    else:
        text = "💼 <b>Did you sell this policy?</b>"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ " + ("हाँ, मैंने बेची" if lang == 'hi' else "Yes, I sold it"),
                              callback_data="scan_sold_yes"),
         InlineKeyboardButton("📋 " + ("नहीं, ट्रैकिंग के लिए" if lang == 'hi' else "No, tracking only"),
                              callback_data="scan_sold_no")],
    ])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return SCAN_SOLD_BY


async def _scan_sold_by_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle sold_by question — then check for missing fields or save."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get('lang', 'en')
    agent_id = context.user_data.get('scan_agent_id')
    lead_id = context.user_data.get('scan_lead_id')
    data = context.user_data.get('scan_data', {})
    client = data.get('client') or {}
    policy = data.get('policy') or {}
    members = data.get('insured_members') or []
    nominees = data.get('nominees') or []

    sold_by = 1 if query.data == "scan_sold_yes" else 0
    context.user_data['scan_sold_by'] = sold_by

    # Check for missing critical fields
    missing = []
    cl_name = client.get('name')
    cl_phone = client.get('phone')
    prem = policy.get('premium')
    renewal = policy.get('renewal_date')

    if not cl_name or cl_name == '—':
        missing.append('name')
    if not cl_phone or cl_phone == '—':
        missing.append('phone')
    if not prem:
        missing.append('premium')
    if not renewal:
        missing.append('renewal_date')

    if missing:
        context.user_data['scan_missing'] = missing
        context.user_data['scan_missing_idx'] = 0
        return await _scan_ask_next_field(query, context)

    # No missing fields — save directly
    return await _scan_save_all(query, context)


async def _scan_ask_next_field(query_or_update, context):
    """Ask the user for the next missing field."""
    lang = context.user_data.get('lang', 'en')
    missing = context.user_data.get('scan_missing', [])
    idx = context.user_data.get('scan_missing_idx', 0)

    if idx >= len(missing):
        return await _scan_save_all(query_or_update, context)

    field = missing[idx]
    prompts = {
        'name':  ("👤 ग्राहक का नाम दर्ज करें:" if lang == 'hi' else "👤 Enter client name:",),
        'phone': ("📱 ग्राहक का फोन नंबर दर्ज करें:" if lang == 'hi' else "📱 Enter client phone number:",),
        'premium': ("💳 प्रीमियम राशि दर्ज करें (₹):" if lang == 'hi' else "💳 Enter premium amount (₹):",),
        'renewal_date': ("📅 नवीनीकरण तिथि दर्ज करें (DD/MM/YYYY):" if lang == 'hi'
                         else "📅 Enter renewal date (DD/MM/YYYY):",),
    }
    prompt_text = prompts.get(field, ("Enter value:",))[0]

    skip_text = "Skip ⏭️" if lang != 'hi' else "छोड़ें ⏭️"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(skip_text, callback_data="scan_skip_field")]
    ])

    if hasattr(query_or_update, 'edit_message_text'):
        await query_or_update.edit_message_text(prompt_text, reply_markup=kb)
    else:
        await query_or_update.message.reply_text(prompt_text, reply_markup=kb)
    return SCAN_ASK_MISSING


async def _scan_receive_missing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive a missing field value from user text input."""
    lang = context.user_data.get('lang', 'en')
    missing = context.user_data.get('scan_missing', [])
    idx = context.user_data.get('scan_missing_idx', 0)
    data = context.user_data.get('scan_data', {})
    client = data.get('client') or {}
    policy = data.get('policy') or {}
    value = update.message.text.strip()

    if idx < len(missing):
        field = missing[idx]
        if field == 'name':
            client['name'] = value
            data['client'] = client
        elif field == 'phone':
            client['phone'] = value
            data['client'] = client
        elif field == 'premium':
            try:
                policy['premium'] = float(value.replace(',', '').replace('₹', ''))
            except ValueError:
                await update.message.reply_text(
                    "⚠️ " + ("कृपया सही राशि दर्ज करें:" if lang == 'hi' else "Please enter a valid amount:"))
                return SCAN_ASK_MISSING
            data['policy'] = policy
        elif field == 'renewal_date':
            # Try to parse DD/MM/YYYY
            import re as _re
            m = _re.match(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})', value)
            if m:
                policy['renewal_date'] = f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
            else:
                policy['renewal_date'] = value  # store as-is if can't parse
            data['policy'] = policy

        context.user_data['scan_data'] = data

    # Move to next missing field
    context.user_data['scan_missing_idx'] = idx + 1
    if idx + 1 < len(missing):
        return await _scan_ask_next_field(update, context)
    else:
        return await _scan_save_all(update, context)


async def _scan_skip_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip a missing field."""
    query = update.callback_query
    await query.answer()
    idx = context.user_data.get('scan_missing_idx', 0)
    missing = context.user_data.get('scan_missing', [])

    context.user_data['scan_missing_idx'] = idx + 1
    if idx + 1 < len(missing):
        return await _scan_ask_next_field(query, context)
    else:
        return await _scan_save_all(query, context)


async def _scan_save_all(query_or_update, context):
    """Save lead + policy + policy_members in one go."""
    lang = context.user_data.get('lang', 'en')
    agent_id = context.user_data.get('scan_agent_id')
    lead_id = context.user_data.get('scan_lead_id')
    data = context.user_data.get('scan_data', {})
    sold_by = context.user_data.get('scan_sold_by', 1)
    client = data.get('client') or {}
    policy = data.get('policy') or {}
    members = data.get('insured_members') or []
    nominees = data.get('nominees') or []

    # Update lead with any new client details from extraction
    try:
        import aiosqlite
        async with aiosqlite.connect(db.DB_PATH) as conn:
            updates = []
            params = []
            lead = await db.get_lead(lead_id)
            # Only update if we have better data and lead exists
            if lead and client.get('phone') and client['phone'] != '—' and not lead.get('phone'):
                updates.append("phone=?")
                params.append(client['phone'])
            if lead and client.get('email') and client['email'] != '—' and not lead.get('email'):
                updates.append("email=?")
                params.append(client['email'])
            if lead and client.get('dob') and client['dob'] != '—' and not lead.get('dob'):
                updates.append("dob=?")
                params.append(client['dob'])
            if updates:
                params.append(lead_id)
                await conn.execute(
                    f"UPDATE leads SET {', '.join(updates)} WHERE lead_id=?", params)
                await conn.commit()
    except Exception as e:
        logger.warning(f"Scan lead update failed: {e}")

    # Build nominee text for notes
    nominee_text = ""
    if nominees:
        parts = []
        for n in nominees[:3]:
            parts.append(f"{n.get('name', '?')} ({n.get('relation', '?')}, {n.get('share_pct', '100')}%)")
        nominee_text = "Nominees: " + ", ".join(parts)

    pol_notes = policy.get('notes') or ''
    if nominee_text:
        pol_notes = (pol_notes + " | " + nominee_text) if pol_notes else nominee_text

    # Save policy
    policy_id = await db.add_policy(
        lead_id=lead_id,
        agent_id=agent_id,
        insurer=policy.get('insurer'),
        plan_name=policy.get('plan_name'),
        policy_type=policy.get('policy_type') or 'health',
        sum_insured=policy.get('sum_insured'),
        premium=policy.get('premium'),
        premium_mode=policy.get('premium_mode') or 'annual',
        start_date=policy.get('start_date'),
        end_date=policy.get('end_date'),
        renewal_date=policy.get('renewal_date'),
        policy_number=policy.get('policy_number'),
        notes=pol_notes[:500] if pol_notes else None,
        sold_by_agent=sold_by,
        policy_status=policy.get('policy_status') or 'active',
        folio_number=policy.get('folio_number'),
        fund_name=policy.get('fund_name'),
        sip_amount=policy.get('sip_amount'),
        maturity_date=policy.get('maturity_date'),
        maturity_value=policy.get('maturity_value'),
        riders=policy.get('riders'),
    )

    # Save insured members
    members_saved = 0
    for m in members:
        if not m.get('name'):
            continue
        try:
            await db.add_policy_member(
                policy_id=policy_id,
                member_name=m['name'],
                relation=m.get('relation', 'self'),
                dob=m.get('dob'),
                age=m.get('age'),
                sum_insured=m.get('sum_insured'),
                premium_share=m.get('premium_share'),
                coverage_type='floater' if policy.get('policy_type') == 'health' else 'individual',
            )
            members_saved += 1
        except Exception as e:
            logger.warning(f"Failed to save policy member: {e}")

    # Get lead name for display
    lead = await db.get_lead(lead_id)
    lead_name = lead['name'] if lead else f"Lead #{lead_id}"

    si = policy.get('sum_insured')
    prem = policy.get('premium')
    si_str = f"₹{si:,.0f}" if si else '—'
    prem_str = f"₹{prem:,.0f}" if prem else '—'
    sold_tag = "✅" if sold_by else "📋"

    if lang == 'hi':
        text = (
            f"🎉 <b>पॉलिसी सफलतापूर्वक सेव!</b>\n\n"
            f"👤 ग्राहक: <b>{h(lead_name)}</b>\n"
            f"🏢 बीमाकर्ता: {h(policy.get('insurer', '—'))}\n"
            f"📋 प्लान: {h(policy.get('plan_name', '—'))}\n"
            f"💰 बीमा राशि: {si_str}\n"
            f"💳 प्रीमियम: {prem_str}/{h(policy.get('premium_mode', '—'))}\n"
            f"{sold_tag} {'आपने बेची' if sold_by else 'ट्रैकिंग के लिए'}\n"
        )
        if members_saved:
            text += f"👥 {members_saved} बीमित सदस्य सेव किए\n"
        text += f"\n📸 एक और डॉक्यूमेंट स्कैन करने के लिए /scan टाइप करें"
    else:
        text = (
            f"🎉 <b>Policy saved successfully!</b>\n\n"
            f"👤 Client: <b>{h(lead_name)}</b>\n"
            f"🏢 Insurer: {h(policy.get('insurer', '—'))}\n"
            f"📋 Plan: {h(policy.get('plan_name', '—'))}\n"
            f"💰 Sum Insured: {si_str}\n"
            f"💳 Premium: {prem_str}/{h(policy.get('premium_mode', '—'))}\n"
            f"{sold_tag} {'Sold by you' if sold_by else 'Tracked for reference'}\n"
        )
        if members_saved:
            text += f"👥 {members_saved} insured members saved\n"
        text += f"\n📸 Type /scan to scan another document"

    if hasattr(query_or_update, 'edit_message_text'):
        await query_or_update.edit_message_text(text, parse_mode=ParseMode.HTML)
    elif hasattr(query_or_update, 'message'):
        await query_or_update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # Log audit event
    await db.log_audit("policy_scanned",
                       detail=f"Policy #{policy_id} for lead #{lead_id} via AI scan (sold={sold_by}, members={members_saved})",
                       agent_id=agent_id)

    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  /calc — INTERACTIVE CALCULATOR (Conversation-based with step-by-step input)
# =============================================================================

# Calculator parameter definitions — each calculator has ordered input steps
_CALC_PARAMS = {
    "inflation": {
        "title": "📉 Inflation Eraser",
        "title_hi": "📉 महंगाई कैलकुलेटर",
        "params": [
            {"key": "amount", "prompt": "Monthly expense (₹)", "prompt_hi": "मासिक खर्च (₹)", "buttons": [25000, 50000, 75000, 100000], "fmt": "₹{:,.0f}", "type": "num", "min": 1000, "max": 10000000},
            {"key": "rate", "prompt": "Inflation rate (%)", "prompt_hi": "महंगाई दर (%)", "buttons": [5, 6, 7, 8], "fmt": "{}%", "type": "num", "min": 1, "max": 30},
            {"key": "years", "prompt": "Time period (years)", "prompt_hi": "समय अवधि (वर्ष)", "buttons": [5, 10, 15, 20, 25], "fmt": "{} yrs", "type": "num", "min": 1, "max": 50},
        ],
    },
    "hlv": {
        "title": "🛡️ Human Life Value",
        "title_hi": "🛡️ मानव जीवन मूल्य",
        "params": [
            {"key": "monthly_expense", "prompt": "Monthly household expense (₹)", "prompt_hi": "मासिक घरेलू खर्च (₹)", "buttons": [30000, 50000, 75000, 100000], "fmt": "₹{:,.0f}", "type": "num", "min": 1000, "max": 10000000},
            {"key": "loans", "prompt": "Outstanding loans (₹)", "prompt_hi": "बकाया लोन (₹)", "buttons": [0, 500000, 2000000, 5000000], "fmt": "₹{:,.0f}", "type": "num", "min": 0, "max": 100000000},
            {"key": "children", "prompt": "Children's future needs (₹)", "prompt_hi": "बच्चों की भविष्य ज़रूरतें (₹)", "buttons": [0, 1000000, 1500000, 3000000], "fmt": "₹{:,.0f}", "type": "num", "min": 0, "max": 100000000},
            {"key": "existing_cover", "prompt": "Existing life cover (₹)", "prompt_hi": "मौजूदा बीमा कवर (₹)", "buttons": [0, 500000, 2500000, 5000000], "fmt": "₹{:,.0f}", "type": "num", "min": 0, "max": 100000000},
        ],
    },
    "retirement": {
        "title": "🏖️ Retirement Planner",
        "title_hi": "🏖️ रिटायरमेंट प्लानर",
        "params": [
            {"key": "current_age", "prompt": "Your current age", "prompt_hi": "आपकी वर्तमान आयु", "buttons": [25, 30, 35, 40, 45], "fmt": "{} yrs", "type": "num", "min": 18, "max": 70},
            {"key": "retire_age", "prompt": "Retirement age", "prompt_hi": "रिटायरमेंट आयु", "buttons": [55, 58, 60, 65], "fmt": "{} yrs", "type": "num", "min": 40, "max": 80},
            {"key": "life_exp", "prompt": "Life expectancy", "prompt_hi": "जीवन प्रत्याशा", "buttons": [75, 80, 85, 90], "fmt": "{} yrs", "type": "num", "min": 60, "max": 100},
            {"key": "monthly_expense", "prompt": "Current monthly expense (₹)", "prompt_hi": "वर्तमान मासिक खर्च (₹)", "buttons": [30000, 50000, 75000, 100000], "fmt": "₹{:,.0f}", "type": "num", "min": 1000, "max": 10000000},
            {"key": "inflation", "prompt": "Expected inflation (%)", "prompt_hi": "अनुमानित महंगाई (%)", "buttons": [6, 7, 8], "fmt": "{}%", "type": "num", "min": 1, "max": 20},
            {"key": "pre_return", "prompt": "Pre-retirement return (%)", "prompt_hi": "रिटायरमेंट पूर्व रिटर्न (%)", "buttons": [10, 12, 14], "fmt": "{}%", "type": "num", "min": 1, "max": 30},
            {"key": "post_return", "prompt": "Post-retirement return (%)", "prompt_hi": "रिटायरमेंट बाद रिटर्न (%)", "buttons": [7, 8, 9], "fmt": "{}%", "type": "num", "min": 1, "max": 25},
        ],
    },
    "emi": {
        "title": "💳 Premium EMI Calculator",
        "title_hi": "💳 प्रीमियम EMI कैलकुलेटर",
        "params": [
            {"key": "premium", "prompt": "Annual premium (₹)", "prompt_hi": "वार्षिक प्रीमियम (₹)", "buttons": [10000, 20000, 50000, 100000], "fmt": "₹{:,.0f}", "type": "num", "min": 1000, "max": 50000000},
            {"key": "years", "prompt": "Number of years", "prompt_hi": "वर्षों की संख्या", "buttons": [3, 5, 7, 10], "fmt": "{} yrs", "type": "num", "min": 1, "max": 30},
            {"key": "gst", "prompt": "GST rate (%)", "prompt_hi": "GST दर (%)", "buttons": [18], "fmt": "{}%", "type": "num", "min": 0, "max": 28},
            {"key": "cibil_disc", "prompt": "CIBIL discount (%)", "prompt_hi": "CIBIL छूट (%)", "buttons": [0, 5, 10, 15], "fmt": "{}%", "type": "num", "min": 0, "max": 50},
            {"key": "down_pct", "prompt": "Down payment (%)", "prompt_hi": "डाउन पेमेंट (%)", "buttons": [20, 25, 30], "fmt": "{}%", "type": "num", "min": 0, "max": 100},
        ],
    },
    "health": {
        "title": "🏥 Health Cover Estimator",
        "title_hi": "🏥 स्वास्थ्य बीमा कैलकुलेटर",
        "params": [
            {"key": "age", "prompt": "Primary member's age", "prompt_hi": "मुख्य सदस्य की आयु", "buttons": [25, 30, 35, 40, 50, 60], "fmt": "{} yrs", "type": "num", "min": 1, "max": 100},
            {"key": "family", "prompt": "Family size", "prompt_hi": "परिवार का आकार", "buttons": ["1A", "2A", "2A+1C", "2A+2C"], "fmt": "{}", "type": "choice", "allowed": ["1A", "2A", "2A+1C", "2A+2C", "2A+3C"]},
            {"key": "city", "prompt": "City tier", "prompt_hi": "शहर का स्तर", "buttons": ["metro", "tier1", "tier2", "rural"], "fmt": "{}", "type": "choice", "allowed": ["metro", "tier1", "tier2", "rural"]},
            {"key": "income", "prompt": "Annual family income (₹)", "prompt_hi": "वार्षिक पारिवारिक आय (₹)", "buttons": [300000, 500000, 1000000, 2000000], "fmt": "₹{:,.0f}", "type": "num", "min": 50000, "max": 100000000},
            {"key": "existing", "prompt": "Existing health cover (₹)", "prompt_hi": "मौजूदा स्वास्थ्य कवर (₹)", "buttons": [0, 300000, 500000, 1000000], "fmt": "₹{:,.0f}", "type": "num", "min": 0, "max": 50000000},
        ],
    },
    "sip": {
        "title": "📈 SIP vs Lumpsum",
        "title_hi": "📈 SIP vs एकमुश्त",
        "params": [
            {"key": "amount", "prompt": "Investment amount (₹)", "prompt_hi": "निवेश राशि (₹)", "buttons": [100000, 500000, 1000000, 2500000], "fmt": "₹{:,.0f}", "type": "num", "min": 1000, "max": 100000000},
            {"key": "years", "prompt": "Investment period (years)", "prompt_hi": "निवेश अवधि (वर्ष)", "buttons": [5, 10, 15, 20], "fmt": "{} yrs", "type": "num", "min": 1, "max": 40},
            {"key": "return_rate", "prompt": "Expected annual return (%)", "prompt_hi": "अनुमानित वार्षिक रिटर्न (%)", "buttons": [10, 12, 14, 16], "fmt": "{}%", "type": "num", "min": 1, "max": 30},
        ],
    },
    "mfsip": {
        "title": "📊 MF SIP Planner",
        "title_hi": "📊 MF SIP प्लानर",
        "params": [
            {"key": "goal", "prompt": "Goal amount (₹)", "prompt_hi": "लक्ष्य राशि (₹)", "buttons": [1000000, 2500000, 5000000, 10000000], "fmt": "₹{:,.0f}", "type": "num", "min": 10000, "max": 1000000000},
            {"key": "years", "prompt": "Investment horizon (years)", "prompt_hi": "निवेश अवधि (वर्ष)", "buttons": [5, 10, 15, 20, 25], "fmt": "{} yrs", "type": "num", "min": 1, "max": 40},
            {"key": "return_rate", "prompt": "Expected annual return (%)", "prompt_hi": "अनुमानित वार्षिक रिटर्न (%)", "buttons": [10, 12, 14, 15], "fmt": "{}%", "type": "num", "min": 1, "max": 30},
            {"key": "existing", "prompt": "Existing savings (₹)", "prompt_hi": "मौजूदा बचत (₹)", "buttons": [0, 100000, 500000, 1000000], "fmt": "₹{:,.0f}", "type": "num", "min": 0, "max": 1000000000},
        ],
    },
    "ulip": {
        "title": "⚖️ ULIP vs Mutual Fund",
        "title_hi": "⚖️ ULIP vs म्यूचुअल फंड",
        "params": [
            {"key": "annual_inv", "prompt": "Annual investment (₹)", "prompt_hi": "वार्षिक निवेश (₹)", "buttons": [50000, 100000, 200000, 500000], "fmt": "₹{:,.0f}", "type": "num", "min": 5000, "max": 50000000},
            {"key": "years", "prompt": "Investment period (years)", "prompt_hi": "निवेश अवधि (वर्ष)", "buttons": [10, 15, 20, 25], "fmt": "{} yrs", "type": "num", "min": 5, "max": 40},
            {"key": "ulip_return", "prompt": "Expected ULIP return (%)", "prompt_hi": "अनुमानित ULIP रिटर्न (%)", "buttons": [8, 10, 12], "fmt": "{}%", "type": "num", "min": 1, "max": 25},
            {"key": "mf_return", "prompt": "Expected MF return (%)", "prompt_hi": "अनुमानित MF रिटर्न (%)", "buttons": [10, 12, 14], "fmt": "{}%", "type": "num", "min": 1, "max": 30},
        ],
    },
    "nps": {
        "title": "🏛️ NPS Planner",
        "title_hi": "🏛️ NPS प्लानर",
        "params": [
            {"key": "monthly", "prompt": "Monthly NPS contribution (₹)", "prompt_hi": "मासिक NPS योगदान (₹)", "buttons": [2000, 5000, 10000, 15000], "fmt": "₹{:,.0f}", "type": "num", "min": 500, "max": 1000000},
            {"key": "current_age", "prompt": "Your current age", "prompt_hi": "आपकी वर्तमान आयु", "buttons": [25, 30, 35, 40, 45], "fmt": "{} yrs", "type": "num", "min": 18, "max": 65},
            {"key": "retire_age", "prompt": "Retirement age", "prompt_hi": "रिटायरमेंट आयु", "buttons": [58, 60, 65, 70], "fmt": "{} yrs", "type": "num", "min": 40, "max": 75},
            {"key": "return_rate", "prompt": "Expected annual return (%)", "prompt_hi": "अनुमानित वार्षिक रिटर्न (%)", "buttons": [8, 10, 12], "fmt": "{}%", "type": "num", "min": 1, "max": 25},
            {"key": "tax_bracket", "prompt": "Tax bracket (%)", "prompt_hi": "टैक्स ब्रैकेट (%)", "buttons": [0, 10, 20, 30], "fmt": "{}%", "type": "num", "min": 0, "max": 30},
        ],
    },
    "stepupsip": {
        "title": "📈 Step-Up SIP",
        "title_hi": "📈 स्टेप-अप SIP",
        "params": [
            {"key": "initial_sip", "prompt": "Starting monthly SIP (₹)", "prompt_hi": "शुरुआती मासिक SIP (₹)", "buttons": [5000, 10000, 15000, 25000], "fmt": "₹{:,.0f}", "type": "num", "min": 500, "max": 10000000},
            {"key": "step_up", "prompt": "Annual increase (%)", "prompt_hi": "वार्षिक वृद्धि (%)", "buttons": [5, 10, 15, 20], "fmt": "{}%", "type": "num", "min": 1, "max": 50},
            {"key": "years", "prompt": "Investment period (years)", "prompt_hi": "निवेश अवधि (वर्ष)", "buttons": [10, 15, 20, 25, 30], "fmt": "{} yrs", "type": "num", "min": 1, "max": 40},
            {"key": "return_rate", "prompt": "Expected annual return (%)", "prompt_hi": "अनुमानित वार्षिक रिटर्न (%)", "buttons": [10, 12, 14, 15], "fmt": "{}%", "type": "num", "min": 1, "max": 30},
        ],
    },
    "swp": {
        "title": "💸 SWP Calculator",
        "title_hi": "💸 SWP कैलकुलेटर",
        "params": [
            {"key": "corpus", "prompt": "Initial corpus (₹)", "prompt_hi": "प्रारंभिक कॉर्पस (₹)", "buttons": [2500000, 5000000, 10000000, 25000000], "fmt": "₹{:,.0f}", "type": "num", "min": 100000, "max": 1000000000},
            {"key": "monthly_withdrawal", "prompt": "Monthly withdrawal (₹)", "prompt_hi": "मासिक निकासी (₹)", "buttons": [20000, 30000, 50000, 100000], "fmt": "₹{:,.0f}", "type": "num", "min": 1000, "max": 10000000},
            {"key": "return_rate", "prompt": "Expected annual return (%)", "prompt_hi": "अनुमानित वार्षिक रिटर्न (%)", "buttons": [6, 8, 10, 12], "fmt": "{}%", "type": "num", "min": 1, "max": 25},
            {"key": "years", "prompt": "Withdrawal period (years)", "prompt_hi": "निकासी अवधि (वर्ष)", "buttons": [10, 15, 20, 25, 30], "fmt": "{} yrs", "type": "num", "min": 1, "max": 50},
        ],
    },
    "delaycost": {
        "title": "⏰ Delay Cost",
        "title_hi": "⏰ विलंब लागत",
        "params": [
            {"key": "monthly_sip", "prompt": "Monthly SIP (₹)", "prompt_hi": "मासिक SIP (₹)", "buttons": [5000, 10000, 15000, 25000], "fmt": "₹{:,.0f}", "type": "num", "min": 500, "max": 10000000},
            {"key": "years", "prompt": "Total investment horizon (years)", "prompt_hi": "कुल निवेश अवधि (वर्ष)", "buttons": [15, 20, 25, 30], "fmt": "{} yrs", "type": "num", "min": 5, "max": 40},
            {"key": "return_rate", "prompt": "Expected annual return (%)", "prompt_hi": "अनुमानित वार्षिक रिटर्न (%)", "buttons": [10, 12, 14, 15], "fmt": "{}%", "type": "num", "min": 1, "max": 30},
            {"key": "delay_years", "prompt": "Delay by how many years?", "prompt_hi": "कितने वर्ष देरी?", "buttons": [1, 2, 3, 5], "fmt": "{} yrs", "type": "num", "min": 1, "max": 20},
        ],
    },
}


@registered
async def cmd_calc_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for calculator from inline menu button (menu_calc callback)."""
    query = update.callback_query
    await query.answer()
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    object.__setattr__(update, 'message', query.message)
    return await cmd_calc(update, context)


@registered
async def cmd_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Launch interactive financial calculator — shows menu of available calculators."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return ConversationHandler.END
    server_url = os.getenv("SERVER_URL", "http://localhost:8000")

    lang = agent.get('lang', 'en')
    if lang == 'hi':
        keyboard = [
            [InlineKeyboardButton("📉 महंगाई कैलकुलेटर", callback_data="csel_inflation"),
             InlineKeyboardButton("🛡️ मानव जीवन मूल्य", callback_data="csel_hlv")],
            [InlineKeyboardButton("🏖️ रिटायरमेंट प्लान", callback_data="csel_retirement"),
             InlineKeyboardButton("💳 प्रीमियम EMI", callback_data="csel_emi")],
            [InlineKeyboardButton("🏥 हेल्थ कवर", callback_data="csel_health"),
             InlineKeyboardButton("📈 SIP vs एकमुश्त", callback_data="csel_sip")],
            [InlineKeyboardButton("📊 MF SIP प्लानर", callback_data="csel_mfsip"),
             InlineKeyboardButton("⚖️ ULIP vs MF", callback_data="csel_ulip")],
            [InlineKeyboardButton("🏛️ NPS प्लानर", callback_data="csel_nps"),
             InlineKeyboardButton("📈 स्टेप-अप SIP", callback_data="csel_stepupsip")],
            [InlineKeyboardButton("💸 SWP कैलकुलेटर", callback_data="csel_swp"),
             InlineKeyboardButton("⏰ विलंब लागत", callback_data="csel_delaycost")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📉 Inflation Eraser", callback_data="csel_inflation"),
             InlineKeyboardButton("🛡️ Human Life Value", callback_data="csel_hlv")],
            [InlineKeyboardButton("🏖️ Retirement Plan", callback_data="csel_retirement"),
             InlineKeyboardButton("💳 Premium EMI", callback_data="csel_emi")],
            [InlineKeyboardButton("🏥 Health Cover", callback_data="csel_health"),
             InlineKeyboardButton("📈 SIP vs Lumpsum", callback_data="csel_sip")],
            [InlineKeyboardButton("📊 MF SIP Planner", callback_data="csel_mfsip"),
             InlineKeyboardButton("⚖️ ULIP vs MF", callback_data="csel_ulip")],
            [InlineKeyboardButton("🏛️ NPS Planner", callback_data="csel_nps"),
             InlineKeyboardButton("📈 Step-Up SIP", callback_data="csel_stepupsip")],
            [InlineKeyboardButton("💸 SWP Calculator", callback_data="csel_swp"),
             InlineKeyboardButton("⏰ Delay Cost", callback_data="csel_delaycost")],
        ]
    _web_label = 'Web स्लाइडर वर्जन:' if lang == 'hi' else 'Web versions (sliders & full details):'
    _tap_label = 'या यहाँ टैप करें — शुरू करें:' if lang == 'hi' else 'Or run interactively right here — tap to start:'
    await update.message.reply_text(
        i18n.t(lang, "calc_title")
        + f'🌐 <b>{_web_label}</b>\n'
        f'<a href="{server_url}/calculators#inflation">{"महंगाई" if lang == "hi" else "Inflation"}</a> · '
        f'<a href="{server_url}/calculators#hlv">HLV</a> · '
        f'<a href="{server_url}/calculators#retirement">{"रिटायरमेंट" if lang == "hi" else "Retirement"}</a> · '
        f'<a href="{server_url}/calculators#emi">EMI</a> · '
        f'<a href="{server_url}/calculators#health">{"हेल्थ" if lang == "hi" else "Health"}</a> · '
        f'<a href="{server_url}/calculators#sip">SIP</a> · '
        f'<a href="{server_url}/calculators#mfsip">MF SIP</a> · '
        f'<a href="{server_url}/calculators#ulip">ULIP vs MF</a> · '
        f'<a href="{server_url}/calculators#nps">NPS</a> · '
        f'<a href="{server_url}/calculators#stepupsip">{"स्टेप-अप SIP" if lang == "hi" else "Step-Up SIP"}</a> · '
        f'<a href="{server_url}/calculators#swp">SWP</a> · '
        f'<a href="{server_url}/calculators#delaycost">{"विलंब लागत" if lang == "hi" else "Delay Cost"}</a>\n\n'
        f"👇 <b>{_tap_label}</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    return CALC_TYPE


async def calc_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected a calculator — start collecting parameters step by step."""
    query = update.callback_query
    await query.answer()
    calc_type = query.data.replace("csel_", "")

    if calc_type not in _CALC_PARAMS:
        _agent = context.user_data.get('_agent')
        _l = _agent.get('lang', 'en') if _agent else 'en'
        await query.edit_message_text("❌ अज्ञात कैलकुलेटर।" if _l == 'hi' else "❌ Unknown calculator.")
        return ConversationHandler.END

    # Initialize calculator state
    context.user_data['_calc_type'] = calc_type
    context.user_data['_calc_values'] = {}
    context.user_data['_calc_step'] = 0

    return await _calc_ask_next_param(query, context, edit=True)


async def _calc_ask_next_param(msg_or_query, context, edit=False):
    """Ask the user for the next parameter, or compute results if done."""
    calc_type = context.user_data['_calc_type']
    step = context.user_data['_calc_step']
    params = _CALC_PARAMS[calc_type]['params']

    agent = context.user_data.get('_agent')
    lang = agent.get('lang', 'en') if agent else 'en'
    title = _CALC_PARAMS[calc_type].get('title_hi' if lang == 'hi' else 'title',
                                         _CALC_PARAMS[calc_type]['title'])

    if step >= len(params):
        # All params collected — compute and show results
        return await _calc_show_result(msg_or_query, context, edit=edit)

    param = params[step]
    total = len(params)

    # Build quick-select buttons
    buttons = []
    row = []
    for val in param['buttons']:
        display = param['fmt'].format(val) if isinstance(val, (int, float)) else str(val)
        row.append(InlineKeyboardButton(display, callback_data=f"cparam_{val}"))
        if len(row) >= 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Summary of values entered so far
    values = context.user_data.get('_calc_values', {})
    summary = ""
    for i, p in enumerate(params[:step]):
        v = values.get(p['key'], '?')
        display_v = p['fmt'].format(v) if isinstance(v, (int, float)) else str(v)
        p_label = p.get('prompt_hi' if lang == 'hi' else 'prompt', p['prompt'])
        summary += f"  ✅ {p_label}: <b>{display_v}</b>\n"

    prompt_label = param.get('prompt_hi' if lang == 'hi' else 'prompt', param['prompt'])
    if lang == 'hi':
        text = (
            f"{title}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{summary}"
            f"\n📊 <b>चरण {step + 1} / {total}</b>\n\n"
            f"<b>{prompt_label}</b> दर्ज करें:\n\n"
            f"👇 नीचे टैप करें, नंबर टाइप करें, या 🎙️ वॉयस नोट भेजें:"
        )
    else:
        text = (
            f"{title}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{summary}"
            f"\n📊 <b>Step {step + 1} of {total}</b>\n\n"
            f"Enter <b>{prompt_label}</b>:\n\n"
            f"👇 Tap a quick value, type your own, or send a 🎙️ voice note:"
        )

    kb = InlineKeyboardMarkup(buttons)
    if edit and hasattr(msg_or_query, 'edit_message_text'):
        await msg_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif hasattr(msg_or_query, 'reply_text'):
        await msg_or_query.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await msg_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    return CALC_INPUT


async def calc_param_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tapped a quick-select button for a calculator parameter."""
    query = update.callback_query
    await query.answer()

    raw = query.data.replace("cparam_", "")
    calc_type = context.user_data.get('_calc_type')
    step = context.user_data.get('_calc_step', 0)
    params = _CALC_PARAMS.get(calc_type, {}).get('params', [])

    if step >= len(params):
        return ConversationHandler.END

    param = params[step]

    # Parse value (numeric or string)
    try:
        val = float(raw)
        if val == int(val):
            val = int(val)
    except ValueError:
        val = raw

    context.user_data['_calc_values'][param['key']] = val
    context.user_data['_calc_step'] = step + 1

    return await _calc_ask_next_param(query, context, edit=True)


def _calc_validate_input(param: dict, raw_str: str, lang: str = 'en') -> tuple:
    """Validate a calculator parameter input.
    Returns (value, error_message). If error_message is None, value is valid."""
    ptype = param.get('type', 'num')
    hi = lang == 'hi'
    raw = raw_str.strip().replace(',', '').replace('₹', '').replace('%', '').strip()

    if ptype == 'choice':
        allowed = param.get('allowed', [])
        # Case-insensitive match
        for a in allowed:
            if raw.lower() == str(a).lower():
                return a, None
        options = ', '.join(str(a) for a in allowed)
        _err = f"❌ अमान्य। इनमें से चुनें: <b>{options}</b>" if hi else \
               f"❌ Invalid value. Please choose one of: <b>{options}</b>"
        return None, _err

    # Numeric validation
    try:
        val = float(raw)
        if val == int(val):
            val = int(val)
    except ValueError:
        _prompt = param.get('prompt_hi', param['prompt']) if hi else param['prompt']
        _err = (f"❌ <b>सही नंबर</b> दर्ज करें {_prompt} के लिए\n"
                f"💡 उदाहरण: {param['buttons'][0]}") if hi else (
            f"❌ Please enter a <b>valid number</b> for {_prompt}.\n"
            f"💡 Example: {param['buttons'][0]}"
        )
        return None, _err

    # Range check
    mn = param.get('min')
    mx = param.get('max')
    if mn is not None and val < mn:
        _prompt = param.get('prompt_hi', param['prompt']) if hi else param['prompt']
        _err = f"❌ बहुत कम। <b>{_prompt}</b> कम से कम <b>{mn}</b> होना चाहिए।" if hi else \
               f"❌ Value too low. <b>{_prompt}</b> must be at least <b>{mn}</b>."
        return None, _err
    if mx is not None and val > mx:
        _prompt = param.get('prompt_hi', param['prompt']) if hi else param['prompt']
        _err = f"❌ बहुत अधिक। <b>{_prompt}</b> अधिकतम <b>{mx:,}</b> होना चाहिए।" if hi else \
               f"❌ Value too high. <b>{_prompt}</b> must be at most <b>{mx:,}</b>."
        return None, _err

    return val, None


def _calc_error_keyboard(calc_type: str, lang: str = 'en') -> InlineKeyboardMarkup:
    """Build error recovery keyboard: Retry / Restart Calculator / Main Menu."""
    hi = lang == 'hi'
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 पुनः प्रयास" if hi else "🔄 Retry", callback_data=f"calc_retry"),
         InlineKeyboardButton("⏮️ शुरू से" if hi else "⏮️ Restart", callback_data=f"csel_{calc_type}")],
        [InlineKeyboardButton("🏠 मेनू" if hi else "🏠 Main Menu", callback_data="calc_cancel")],
    ])


async def calc_param_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User typed a custom value for a calculator parameter — with validation."""
    calc_type = context.user_data.get('_calc_type')
    step = context.user_data.get('_calc_step', 0)
    params = _CALC_PARAMS.get(calc_type, {}).get('params', [])

    if step >= len(params):
        return ConversationHandler.END

    param = params[step]
    raw = update.message.text.strip()

    agent = context.user_data.get('_agent')
    _lang = agent.get('lang', 'en') if agent else 'en'

    val, error = _calc_validate_input(param, raw, lang=_lang)
    if error:
        title = _CALC_PARAMS[calc_type].get('title_hi' if _lang == 'hi' else 'title',
                                              _CALC_PARAMS[calc_type]['title'])
        tip = "👇 नीचे टैप करें या सही नंबर टाइप करें:" if _lang == 'hi' else "👇 Tap a quick value below or type a valid number:"
        await update.message.reply_text(
            f"{title}\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{error}\n\n"
            f"{tip}",
            parse_mode=ParseMode.HTML,
            reply_markup=_calc_error_keyboard(calc_type, _lang),
        )
        return CALC_INPUT  # Stay on same step

    context.user_data['_calc_values'][param['key']] = val
    context.user_data['_calc_step'] = step + 1

    return await _calc_ask_next_param(update.message, context, edit=False)


async def calc_param_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User sent a voice note for a calculator parameter — transcribe & extract value."""
    calc_type = context.user_data.get('_calc_type')
    step = context.user_data.get('_calc_step', 0)
    params = _CALC_PARAMS.get(calc_type, {}).get('params', [])

    if step >= len(params):
        return ConversationHandler.END

    param = params[step]
    agent = context.user_data.get('_agent')
    _lang = agent.get('lang', 'en') if agent else 'en'
    hi = _lang == 'hi'

    voice = update.message.voice or update.message.audio
    if not voice:
        return CALC_INPUT

    # Duration check
    if (voice.duration or 0) > 30:
        await update.message.reply_text(
            "⚠️ वॉयस नोट 30 सेकंड से कम रखें।" if hi else
            "⚠️ Please keep voice note under 30 seconds for calculator input.")
        return CALC_INPUT

    client = _get_gemini()
    if not client:
        await update.message.reply_text(
            "👇 " + ("नीचे टैप करें या नंबर टाइप करें:" if hi else
                      "Tap a value below or type a number:"))
        return CALC_INPUT

    wait_msg = await update.message.reply_text(
        "🎙️ " + ("सुन रहा हूँ..." if hi else "Listening..."))

    try:
        tg_file = await context.bot.get_file(voice.file_id)
        audio_bytes = await tg_file.download_as_bytearray()

        prompt_label = param.get('prompt_hi' if hi else 'prompt', param['prompt'])
        extract_prompt = (
            f"Listen to this voice note. The user is providing a value for: {prompt_label}.\n"
            f"Extract ONLY the numeric value they said. "
            f"Understand Hindi, English, and mixed (Hinglish). "
            f"Handle words like lakh, crore, hazaar, percent.\n"
            f"Reply with JUST the number. Examples: 500000, 12, 25000.\n"
            f"If you cannot understand, reply: UNCLEAR"
        )

        response = await client.aio.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=[
                genai_types.Part.from_bytes(
                    data=bytes(audio_bytes), mime_type="audio/ogg"),
                extract_prompt
            ]
        )

        raw = response.text.strip()

        if raw.upper() == 'UNCLEAR' or not raw:
            await wait_msg.edit_text(
                "❌ " + ("समझ नहीं आया। नीचे टैप करें या नंबर टाइप करें:" if hi else
                         "Couldn't understand. Tap a value below or type a number:"))
            return CALC_INPUT

        # Try direct parse first, then _extract_number_from_text
        extracted = _extract_number_from_text(raw)
        if extracted is None:
            extracted = raw

        val, error = _calc_validate_input(param, str(extracted), lang=_lang)
        if error:
            title = _CALC_PARAMS[calc_type].get(
                'title_hi' if hi else 'title', _CALC_PARAMS[calc_type]['title'])
            await wait_msg.edit_text(
                f"{title}\n━━━━━━━━━━━━━━━━━━\n\n"
                f"🎙️ {'सुना' if hi else 'Heard'}: <b>{h(raw)}</b>\n\n"
                f"{error}\n\n"
                f"👇 {'नीचे टैप करें या सही नंबर टाइप करें:' if hi else 'Tap a quick value below or type a valid number:'}",
                parse_mode=ParseMode.HTML,
                reply_markup=_calc_error_keyboard(calc_type, _lang))
            return CALC_INPUT

        # Success — show what we heard and advance
        display_v = param['fmt'].format(val) if isinstance(val, (int, float)) else str(val)
        try:
            await wait_msg.edit_text(
                f"🎙️ {'सुना' if hi else 'Heard'}: <b>{display_v}</b> ✅",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass

        context.user_data['_calc_values'][param['key']] = val
        context.user_data['_calc_step'] = step + 1

        return await _calc_ask_next_param(update.message, context, edit=False)

    except Exception as e:
        logger.error("Calc voice error: %s", e)
        try:
            await wait_msg.edit_text(
                "❌ " + ("वॉयस प्रोसेस नहीं हो सका। नंबर टाइप करें या टैप करें:" if hi else
                         "Could not process voice. Please type or tap a value:"))
        except Exception:
            pass
        return CALC_INPUT


async def _calc_show_result(msg_or_query, context, edit=False):
    """Compute calculator result and display it."""
    calc_type = context.user_data['_calc_type']
    v = context.user_data['_calc_values']
    agent = context.user_data.get('_agent')
    lang = agent.get('lang', 'en') if agent else 'en'
    hi = lang == 'hi'

    try:
        if calc_type == "inflation":
            result = calc.inflation_eraser(v['amount'], v['rate'], v['years'])
            if hi:
                text = (
                    f"📉 <b>महंगाई कैलकुलेटर — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 वर्तमान: ₹{v['amount']:,.0f}/महीना\n"
                    f"📈 महंगाई: {v['rate']}% | अवधि: {v['years']} वर्ष\n\n"
                    f"⚠️ <b>क्रय शक्ति गिरकर:</b>\n"
                    f"<b>{h(calc.format_currency(result.purchasing_power_left))}/महीना</b>\n\n"
                    f"🔴 क्षरण: {result.erosion_percent:.1f}%\n"
                    f"💡 समान जीवनशैली बनाए रखने के लिए\n"
                    f"   <b>{h(calc.format_currency(result.future_value_needed))}/महीना</b> चाहिए।"
                )
            else:
                text = (
                    f"📉 <b>Inflation Eraser — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Current: ₹{v['amount']:,.0f}/month\n"
                    f"📈 Inflation: {v['rate']}% | Period: {v['years']} years\n\n"
                    f"⚠️ <b>Purchasing power drops to:</b>\n"
                    f"<b>{h(calc.format_currency(result.purchasing_power_left))}/month</b>\n\n"
                    f"🔴 Erosion: {result.erosion_percent:.1f}%\n"
                    f"💡 You'll need <b>{h(calc.format_currency(result.future_value_needed))}/month</b>\n"
                    f"   to maintain the same lifestyle."
                )
        elif calc_type == "hlv":
            result = calc.hlv_calculator(v['monthly_expense'], v['loans'], v['children'], v['existing_cover'], 0)
            if hi:
                text = (
                    f"🛡️ <b>मानव जीवन मूल्य — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 मासिक खर्च: ₹{v['monthly_expense']:,.0f}\n"
                    f"🏦 लोन: ₹{v['loans']:,.0f}\n"
                    f"👶 बच्चों की ज़रूरतें: ₹{v['children']:,.0f}\n"
                    f"🛡️ मौजूदा कवर: ₹{v['existing_cover']:,.0f}\n\n"
                    f"✅ <b>अनुशंसित बीमा कवर:</b>\n"
                    f"<b>{h(calc.format_currency(result.recommended_cover))}</b>\n\n"
                    f"💡 यह आपके परिवार की आर्थिक सुरक्षा सुनिश्चित करता है।"
                )
            else:
                text = (
                    f"🛡️ <b>Human Life Value — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Monthly Expense: ₹{v['monthly_expense']:,.0f}\n"
                    f"🏦 Loans: ₹{v['loans']:,.0f}\n"
                    f"👶 Children's Needs: ₹{v['children']:,.0f}\n"
                    f"🛡️ Existing Cover: ₹{v['existing_cover']:,.0f}\n\n"
                    f"✅ <b>Recommended Cover:</b>\n"
                    f"<b>{h(calc.format_currency(result.recommended_cover))}</b>\n\n"
                    f"💡 This ensures your family's financial security."
                )
        elif calc_type == "retirement":
            existing = v.get('existing_savings', 0)
            result = calc.retirement_planner(
                v['current_age'], v['retire_age'], v['life_exp'],
                v['monthly_expense'], v['inflation'], v['pre_return'], v['post_return'], existing)
            if hi:
                text = (
                    f"🏖️ <b>रिटायरमेंट प्लानर — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 आयु: {v['current_age']} → रिटायरमेंट: {v['retire_age']}\n"
                    f"📅 जीवन प्रत्याशा: {v['life_exp']}\n"
                    f"💰 मासिक खर्च: ₹{v['monthly_expense']:,.0f}\n\n"
                    f"💰 <b>ज़रूरी कॉर्पस:</b>\n"
                    f"<b>{h(calc.format_currency(result.corpus_needed))}</b>\n\n"
                    f"📊 <b>मासिक SIP ज़रूरी:</b>\n"
                    f"<b>{h(calc.format_currency(result.monthly_sip_needed))}</b>"
                )
            else:
                text = (
                    f"🏖️ <b>Retirement Planner — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 Age: {v['current_age']} → Retire at {v['retire_age']}\n"
                    f"📅 Life Expectancy: {v['life_exp']}\n"
                    f"💰 Monthly Expense: ₹{v['monthly_expense']:,.0f}\n\n"
                    f"💰 <b>Corpus Needed:</b>\n"
                    f"<b>{h(calc.format_currency(result.corpus_needed))}</b>\n\n"
                    f"📊 <b>Monthly SIP Required:</b>\n"
                    f"<b>{h(calc.format_currency(result.monthly_sip_needed))}</b>"
                )
        elif calc_type == "emi":
            result = calc.emi_calculator(v['premium'], v['years'], v['gst'], v['cibil_disc'], v['down_pct'])
            if hi:
                text = (
                    f"💳 <b>प्रीमियम EMI — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"कुल प्रीमियम: {h(calc.format_currency(result.total_premium))}\n"
                    f"GST ({v['gst']}%): {h(calc.format_currency(result.gst_amount))}\n"
                    f"CIBIL छूट: -{h(calc.format_currency(result.cibil_discount))}\n"
                    f"नेट प्रीमियम: <b>{h(calc.format_currency(result.net_premium))}</b>\n"
                    f"डाउन पेमेंट: {h(calc.format_currency(result.down_payment))}\n\n"
                    f"📊 <b>EMI विकल्प:</b>\n"
                )
            else:
                text = (
                    f"💳 <b>Premium EMI — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"Total Premium: {h(calc.format_currency(result.total_premium))}\n"
                    f"GST ({v['gst']}%): {h(calc.format_currency(result.gst_amount))}\n"
                    f"CIBIL Discount: -{h(calc.format_currency(result.cibil_discount))}\n"
                    f"Net Premium: <b>{h(calc.format_currency(result.net_premium))}</b>\n"
                    f"Down Payment: {h(calc.format_currency(result.down_payment))}\n\n"
                    f"📊 <b>EMI Options:</b>\n"
                )
            for opt in result.emi_options:
                text += f"  {opt['months']}mo → {h(calc.format_currency(opt['monthly_emi']))}/mo\n"
        elif calc_type == "health":
            age = int(v['age']) if isinstance(v['age'], (int, float)) else 35
            income = int(v['income']) if isinstance(v['income'], (int, float)) else 500000
            existing = int(v['existing']) if isinstance(v['existing'], (int, float)) else 0
            result = calc.health_cover_estimator(age, str(v['family']), str(v['city']), income, existing)
            if hi:
                text = (
                    f"🏥 <b>स्वास्थ्य बीमा — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 आयु: {result.age} | परिवार: {h(str(result.family_size))}\n"
                    f"🏙️ शहर: {h(str(result.city_tier))}\n\n"
                    f"✅ <b>अनुशंसित कवर:</b>\n"
                    f"<b>{h(calc.format_currency(result.recommended_si))}</b>\n\n"
                    f"🔴 कमी: <b>{h(calc.format_currency(result.gap))}</b>\n\n"
                    f"💳 अनुमानित प्रीमियम: {h(calc.format_currency(result.estimated_premium_range['low']))}"
                    f" – {h(calc.format_currency(result.estimated_premium_range['high']))}/वर्ष"
                )
            else:
                text = (
                    f"🏥 <b>Health Cover Estimate — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 Age: {result.age} | Family: {h(str(result.family_size))}\n"
                    f"🏙️ City: {h(str(result.city_tier))}\n\n"
                    f"✅ <b>Recommended Cover:</b>\n"
                    f"<b>{h(calc.format_currency(result.recommended_si))}</b>\n\n"
                    f"🔴 Gap: <b>{h(calc.format_currency(result.gap))}</b>\n\n"
                    f"💳 Est. Premium: {h(calc.format_currency(result.estimated_premium_range['low']))}"
                    f" – {h(calc.format_currency(result.estimated_premium_range['high']))}/year"
                )
        elif calc_type == "sip":
            result = calc.sip_vs_lumpsum(v['amount'], v['years'], v['return_rate'])
            if hi:
                text = (
                    f"📈 <b>SIP vs एकमुश्त — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 राशि: {h(calc.format_currency(result.investment_amount))}\n"
                    f"📅 अवधि: {result.years} वर्ष @ {result.expected_return}%\n\n"
                    f"📊 एकमुश्त: <b>{h(calc.format_currency(result.lumpsum_maturity))}</b>\n"
                    f"📊 SIP: <b>{h(calc.format_currency(result.sip_maturity))}</b>\n"
                    f"   ({h(calc.format_currency(result.sip_monthly))}/महीना)\n\n"
                    f"🏆 विजेता: <b>{h(str(result.winner))}</b>\n"
                    f"अंतर: {h(calc.format_currency(result.difference))}"
                )
            else:
                text = (
                    f"📈 <b>SIP vs Lumpsum — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Amount: {h(calc.format_currency(result.investment_amount))}\n"
                    f"📅 Period: {result.years} years @ {result.expected_return}%\n\n"
                    f"📊 Lumpsum: <b>{h(calc.format_currency(result.lumpsum_maturity))}</b>\n"
                    f"📊 SIP: <b>{h(calc.format_currency(result.sip_maturity))}</b>\n"
                    f"   ({h(calc.format_currency(result.sip_monthly))}/month)\n\n"
                    f"🏆 Winner: <b>{h(str(result.winner))}</b>\n"
                    f"Difference: {h(calc.format_currency(result.difference))}"
                )
        elif calc_type == "mfsip":
            result = calc.mf_sip_planner(v['goal'], v['years'], v['return_rate'], v.get('existing', 0))
            if hi:
                text = (
                    f"📊 <b>MF SIP प्लानर — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎯 लक्ष्य: {h(calc.format_currency(result.goal_amount))}\n"
                    f"📅 अवधि: {result.years} वर्ष @ {result.annual_return}%\n\n"
                    f"📈 <b>मासिक SIP ज़रूरी:</b>\n"
                    f"<b>{h(calc.format_currency(result.monthly_sip))}/महीना</b>\n\n"
                    f"💰 कुल निवेश: {h(calc.format_currency(result.total_invested))}\n"
                    f"📊 अनुमानित कॉर्पस: {h(calc.format_currency(result.expected_corpus))}\n"
                    f"🏆 संपत्ति लाभ: <b>{h(calc.format_currency(result.wealth_gained))}</b>"
                )
            else:
                text = (
                    f"📊 <b>MF SIP Planner — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎯 Goal: {h(calc.format_currency(result.goal_amount))}\n"
                    f"📅 Timeline: {result.years} years @ {result.annual_return}%\n\n"
                    f"📈 <b>Monthly SIP Needed:</b>\n"
                    f"<b>{h(calc.format_currency(result.monthly_sip))}/month</b>\n\n"
                    f"💰 Total Invested: {h(calc.format_currency(result.total_invested))}\n"
                    f"📊 Expected Corpus: {h(calc.format_currency(result.expected_corpus))}\n"
                    f"🏆 Wealth Gained: <b>{h(calc.format_currency(result.wealth_gained))}</b>"
                )
        elif calc_type == "ulip":
            result = calc.ulip_vs_mf(v['annual_inv'], v['years'], v['ulip_return'], v['mf_return'])
            if hi:
                text = (
                    f"⚖️ <b>ULIP vs म्यूचुअल फंड — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 वार्षिक निवेश: {h(calc.format_currency(result.investment_amount))}\n"
                    f"📅 अवधि: {result.years} वर्ष\n\n"
                    f"📊 <b>ULIP ({result.ulip_return}%):</b>\n"
                    f"  मैच्योरिटी: {h(calc.format_currency(result.ulip_maturity))}\n"
                    f"  शुल्क: {h(calc.format_currency(result.ulip_charges_total))}\n"
                    f"  बीमा: {h(calc.format_currency(result.insurance_cover))}\n\n"
                    f"📈 <b>म्यूचुअल फंड ({result.mf_return}%):</b>\n"
                    f"  मैच्योरिटी: {h(calc.format_currency(result.mf_maturity))}\n"
                    f"  शुल्क: {h(calc.format_currency(result.mf_charges_total))}\n\n"
                    f"🏆 विजेता: <b>{h(str(result.winner))}</b>\n"
                    f"अंतर: {h(calc.format_currency(result.difference))}"
                )
            else:
                text = (
                    f"⚖️ <b>ULIP vs Mutual Fund — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Annual Investment: {h(calc.format_currency(result.investment_amount))}\n"
                    f"📅 Period: {result.years} years\n\n"
                    f"📊 <b>ULIP ({result.ulip_return}%):</b>\n"
                    f"  Maturity: {h(calc.format_currency(result.ulip_maturity))}\n"
                    f"  Charges: {h(calc.format_currency(result.ulip_charges_total))}\n"
                    f"  Insurance: {h(calc.format_currency(result.insurance_cover))}\n\n"
                    f"📈 <b>Mutual Fund ({result.mf_return}%):</b>\n"
                    f"  Maturity: {h(calc.format_currency(result.mf_maturity))}\n"
                    f"  Charges: {h(calc.format_currency(result.mf_charges_total))}\n\n"
                    f"🏆 Winner: <b>{h(str(result.winner))}</b>\n"
                    f"Difference: {h(calc.format_currency(result.difference))}"
                )
        elif calc_type == "nps":
            result = calc.nps_planner(v['monthly'], v['current_age'], v['retire_age'], v['return_rate'], v.get('tax_bracket', 30))
            if hi:
                text = (
                    f"🏛️ <b>NPS प्लानर — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 मासिक: {h(calc.format_currency(result.monthly_contribution))}\n"
                    f"📅 {result.years_to_retire} वर्ष @ {result.annual_return}%\n\n"
                    f"📊 <b>रिटायरमेंट पर:</b>\n"
                    f"कॉर्पस: <b>{h(calc.format_currency(result.total_corpus))}</b>\n"
                    f"एकमुश्त (60%): {h(calc.format_currency(result.lumpsum_withdrawal))}\n"
                    f"एन्युटी (40%): {h(calc.format_currency(result.annuity_corpus))}\n\n"
                    f"💳 <b>मासिक पेंशन: {h(calc.format_currency(result.monthly_pension_estimate))}</b>\n\n"
                    f"🏷️ टैक्स बचत: {h(calc.format_currency(result.tax_saved_yearly))}/वर्ष\n"
                    f"कुल लाभ: {h(calc.format_currency(result.tax_saved_total))}"
                )
            else:
                text = (
                    f"🏛️ <b>NPS Planner — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Monthly: {h(calc.format_currency(result.monthly_contribution))}\n"
                    f"📅 {result.years_to_retire} years @ {result.annual_return}%\n\n"
                    f"📊 <b>At Retirement:</b>\n"
                    f"Corpus: <b>{h(calc.format_currency(result.total_corpus))}</b>\n"
                    f"Lumpsum (60%): {h(calc.format_currency(result.lumpsum_withdrawal))}\n"
                    f"Annuity (40%): {h(calc.format_currency(result.annuity_corpus))}\n\n"
                    f"💳 <b>Monthly Pension: {h(calc.format_currency(result.monthly_pension_estimate))}</b>\n\n"
                    f"🏷️ Tax Saved: {h(calc.format_currency(result.tax_saved_yearly))}/year\n"
                    f"Total Benefit: {h(calc.format_currency(result.tax_saved_total))}"
                )
        elif calc_type == "stepupsip":
            result = calc.stepup_sip_planner(v['initial_sip'], v['step_up'], v['years'], v['return_rate'])
            if hi:
                text = (
                    f"📈 <b>स्टेप-अप SIP प्लानर — परिणाम</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 शुरुआती SIP: {h(calc.format_currency(result.initial_monthly_sip))}/माह\n"
                    f"📊 वार्षिक वृद्धि: {result.annual_step_up}%\n"
                    f"📅 {result.years} वर्ष @ {result.annual_return}%\n\n"
                    f"🚀 <b>परिणाम:</b>\n"
                    f"कुल निवेश: {h(calc.format_currency(result.total_invested))}\n"
                    f"कुल कॉर्पस: <b>{h(calc.format_currency(result.total_corpus))}</b>\n"
                    f"संपत्ति लाभ: {h(calc.format_currency(result.wealth_gained))}\n"
                    f"अंतिम मासिक SIP: {h(calc.format_currency(result.final_monthly_sip))}\n\n"
                    f"⚡ <b>स्टेप-अप लाभ:</b>\n"
                    f"सामान्य SIP कॉर्पस: {h(calc.format_currency(result.regular_sip_corpus))}\n"
                    f"अतिरिक्त लाभ: <b>{h(calc.format_currency(result.stepup_advantage))}</b>"
                )
            else:
                text = (
                    f"📈 <b>Step-Up SIP Planner — Results</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Starting SIP: {h(calc.format_currency(result.initial_monthly_sip))}/month\n"
                    f"📊 Annual Step-Up: {result.annual_step_up}%\n"
                    f"📅 {result.years} years @ {result.annual_return}%\n\n"
                    f"🚀 <b>Results:</b>\n"
                    f"Total Invested: {h(calc.format_currency(result.total_invested))}\n"
                    f"Total Corpus: <b>{h(calc.format_currency(result.total_corpus))}</b>\n"
                    f"Wealth Gained: {h(calc.format_currency(result.wealth_gained))}\n"
                    f"Final Monthly SIP: {h(calc.format_currency(result.final_monthly_sip))}\n\n"
                    f"⚡ <b>Step-Up Advantage:</b>\n"
                    f"Regular SIP Corpus: {h(calc.format_currency(result.regular_sip_corpus))}\n"
                    f"Extra from Step-Up: <b>{h(calc.format_currency(result.stepup_advantage))}</b>"
                )
        elif calc_type == "swp":
            result = calc.swp_calculator(v['corpus'], v['monthly_withdrawal'], v['return_rate'], v['years'])
            _status_hi = "✅ टिकाऊ" if result.is_sustainable else f"⚠️ {result.corpus_lasted_months} महीनों में समाप्त"
            _status_en = "✅ Sustainable" if result.is_sustainable else f"⚠️ Depleted in {result.corpus_lasted_months} months"
            if hi:
                text = (
                    f"💸 <b>SWP (व्यवस्थित निकासी) योजना</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🏦 प्रारंभिक कॉर्पस: {h(calc.format_currency(result.initial_corpus))}\n"
                    f"💳 मासिक निकासी: {h(calc.format_currency(result.monthly_withdrawal))}\n"
                    f"📊 रिटर्न: {result.annual_return}% | अवधि: {result.years} वर्ष\n\n"
                    f"📋 <b>परिणाम:</b>\n"
                    f"कुल निकासी: {h(calc.format_currency(result.total_withdrawn))}\n"
                    f"शेष कॉर्पस: <b>{h(calc.format_currency(result.remaining_corpus))}</b>\n"
                    f"स्थिति: <b>{_status_hi}</b>"
                )
            else:
                text = (
                    f"💸 <b>SWP (Systematic Withdrawal) Plan</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🏦 Initial Corpus: {h(calc.format_currency(result.initial_corpus))}\n"
                    f"💳 Monthly Withdrawal: {h(calc.format_currency(result.monthly_withdrawal))}\n"
                    f"📊 Return: {result.annual_return}% | Period: {result.years} yrs\n\n"
                    f"📋 <b>Results:</b>\n"
                    f"Total Withdrawn: {h(calc.format_currency(result.total_withdrawn))}\n"
                    f"Remaining Corpus: <b>{h(calc.format_currency(result.remaining_corpus))}</b>\n"
                    f"Status: <b>{_status_en}</b>"
                )
        elif calc_type == "delaycost":
            result = calc.delay_cost_calculator(v['monthly_sip'], v['years'], v['return_rate'], v['delay_years'])
            if hi:
                text = (
                    f"⏰ <b>विलंब लागत रिपोर्ट</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 SIP: {h(calc.format_currency(result.monthly_sip))}/माह\n"
                    f"📅 अवधि: {result.years} वर्ष @ {result.annual_return}%\n"
                    f"⏳ विलंब: {result.delay_years} वर्ष\n\n"
                    f"📊 <b>प्रभाव:</b>\n"
                    f"आज शुरू करें: <b>{h(calc.format_currency(result.corpus_on_time))}</b>\n"
                    f"{result.delay_years} वर्ष बाद: {h(calc.format_currency(result.corpus_delayed))}\n"
                    f"🔴 विलंब की कीमत: <b>{h(calc.format_currency(result.cost_of_delay))}</b>\n\n"
                    f"⚡ बराबरी के लिए चाहिए:\n"
                    f"<b>{h(calc.format_currency(result.extra_sip_needed))}/माह</b>"
                )
            else:
                text = (
                    f"⏰ <b>Cost of Delay Report</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 SIP: {h(calc.format_currency(result.monthly_sip))}/month\n"
                    f"📅 Horizon: {result.years} yrs @ {result.annual_return}%\n"
                    f"⏳ Delay: {result.delay_years} years\n\n"
                    f"📊 <b>Impact:</b>\n"
                    f"Start Today: <b>{h(calc.format_currency(result.corpus_on_time))}</b>\n"
                    f"Start After {result.delay_years} yrs: {h(calc.format_currency(result.corpus_delayed))}\n"
                    f"🔴 Cost of Delay: <b>{h(calc.format_currency(result.cost_of_delay))}</b>\n\n"
                    f"⚡ To match, you'd need:\n"
                    f"<b>{h(calc.format_currency(result.extra_sip_needed))}/month</b>"
                )
        else:
            text = "❌ Unknown calculator type"
    except Exception as e:
        logger.error("Calculator error (%s): %s", calc_type, e, exc_info=True)
        if hi:
            text = f"❌ गणना त्रुटि: {h(str(e))}\nकृपया अपने इनपुट जांचें और फिर प्रयास करें।"
        else:
            text = f"❌ Calculation error: {h(str(e))}\nPlease check your inputs and try again."

    # Store for WhatsApp sharing
    context.user_data[f"last_calc_{calc_type}"] = text
    context.user_data['last_calc_type'] = calc_type
    _track_voice_context(context, intent='calc_compute', calc_type=calc_type)

    # Generate HTML report for "View Report" button
    report_url = None
    try:
        agent = context.user_data.get('_agent')
        if agent:
            server_url = os.getenv("SERVER_URL", "http://localhost:8000")
            agent_name = agent.get('name', 'Advisor')
            agent_phone = agent.get('phone', '')
            agent_photo_url = ""
            if agent.get('profile_photo'):
                agent_photo_url = f"{server_url}{agent['profile_photo']}"
            company = "Sarathi-AI Business Technologies"
            tenant = None
            try:
                tenant = await db.get_tenant(agent['tenant_id'])
                if tenant and tenant.get('firm_name'):
                    company = tenant['firm_name']
            except Exception:
                pass
            # Build compliance credentials for PDF footer
            _creds = ''
            try:
                _creds = await db.build_compliance_credentials(agent['agent_id'])
            except Exception:
                pass
            _brand = dict(agent_name=agent_name, agent_phone=agent_phone,
                          agent_photo_url=agent_photo_url, company=company)
            _brand_info = None
            if tenant:
                _ms_url = ""
                try:
                    if tenant.get('microsite_published') and tenant.get('microsite_slug'):
                        _ms_url = f"https://sarathi-ai.com/m/{tenant.get('microsite_slug')}"
                except Exception:
                    _ms_url = ""
                _brand_info = {
                    'firm_name': company,
                    'primary_color': tenant.get('brand_primary_color') or None,
                    'accent_color': tenant.get('brand_accent_color') or None,
                    'logo': tenant.get('brand_logo') or None,
                    'tagline': tenant.get('brand_tagline') or None,
                    'phone': tenant.get('brand_phone') or None,
                    'email': tenant.get('brand_email') or None,
                    'website': tenant.get('brand_website') or None,
                    'microsite_url': _ms_url or None,
                }
            _brand['brand'] = _brand_info
            gen_map = {
                'inflation': pdf.generate_inflation_html,
                'hlv': pdf.generate_hlv_html,
                'retirement': pdf.generate_retirement_html,
                'emi': pdf.generate_emi_html,
                'health': pdf.generate_health_html,
                'sip': pdf.generate_sip_html,
                'mfsip': pdf.generate_mfsip_html,
                'ulip': pdf.generate_ulip_html,
                'nps': pdf.generate_nps_html,
                'stepupsip': pdf.generate_stepupsip_html,
                'swp': pdf.generate_swp_html,
                'delaycost': pdf.generate_delaycost_html,
            }
            gen_fn = gen_map.get(calc_type)
            if gen_fn:
                html = gen_fn(result, "Client", **_brand)
                # Inject compliance credentials into PDF footer
                if _creds:
                    import html as _html_mod
                    _cred_html = (
                        '<div style="text-align:center;font-size:11px;color:#777;'
                        'padding:12px 20px 4px;border-top:1px solid #eee;'
                        'margin-top:10px;white-space:pre-line">'
                        f'{_html_mod.escape(_creds)}</div>'
                    )
                    html = html.replace('</body>', f'{_cred_html}\n</body>')
                fname = pdf.save_html_report(html, calc_type, "client", advisor_name=company)
                report_url = f"{server_url}/reports/{fname}"
    except Exception as e:
        logger.warning("Report generation failed for calc %s: %s", calc_type, e)

    # Store report URL for WhatsApp sharing
    context.user_data['last_report_url'] = report_url or ''

    # Result action buttons
    if hi:
        row1 = [InlineKeyboardButton("🔄 फिर से", callback_data=f"csel_{calc_type}"),
                InlineKeyboardButton("📱 WhatsApp शेयर", callback_data=f"wa_share_{calc_type}")]
    else:
        row1 = [InlineKeyboardButton("🔄 Recalculate", callback_data=f"csel_{calc_type}"),
                InlineKeyboardButton("📱 Share WhatsApp", callback_data=f"wa_share_{calc_type}")]
    rows = [row1]
    if report_url:
        rows.append([InlineKeyboardButton("📊 रिपोर्ट देखें" if hi else "📊 View Report", url=report_url)])
    rows.append([InlineKeyboardButton("🧮 अन्य कैलकुलेटर" if hi else "🧮 Other Calculator", callback_data="csel_menu")])
    kb = InlineKeyboardMarkup(rows)

    if edit and hasattr(msg_or_query, 'edit_message_text'):
        await msg_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await msg_or_query.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    return CALC_RESULT


async def calc_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Re-ask the current calculator step after a validation error."""
    query = update.callback_query
    await query.answer()
    # Re-show the current param prompt (step hasn't advanced)
    return await _calc_ask_next_param(query, context, edit=True)


async def calc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel calculator and return to main menu."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('_calc_type', None)
    context.user_data.pop('_calc_values', None)
    context.user_data.pop('_calc_step', None)
    agent = await db.get_agent(str(update.effective_user.id))
    lang = agent.get('lang', 'en') if agent else 'en'
    await query.edit_message_text(i18n.t(lang, "calc_cancelled"))
    return ConversationHandler.END


async def calc_result_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle actions from the calculator result screen."""
    query = update.callback_query
    await query.answer()

    if query.data == "csel_menu":
        # Re-show calculator menu (all 9 calculators)
        agent_for_lang = await db.get_agent(str(query.from_user.id))
        _lang = agent_for_lang.get('lang', 'en') if agent_for_lang else 'en'
        if _lang == 'hi':
            keyboard = [
                [InlineKeyboardButton("📉 महँगाई विश्लेषक", callback_data="csel_inflation"),
                 InlineKeyboardButton("🛡️ HLV कैलकुलेटर", callback_data="csel_hlv")],
                [InlineKeyboardButton("🏖️ रिटायरमेंट प्लान", callback_data="csel_retirement"),
                 InlineKeyboardButton("💳 EMI कैलकुलेटर", callback_data="csel_emi")],
                [InlineKeyboardButton("🏥 हेल्थ कवर", callback_data="csel_health"),
                 InlineKeyboardButton("📈 SIP vs एकमुश्त", callback_data="csel_sip")],
                [InlineKeyboardButton("📊 MF SIP प्लानर", callback_data="csel_mfsip"),
                 InlineKeyboardButton("⚖️ ULIP vs MF", callback_data="csel_ulip")],
                [InlineKeyboardButton("🏛️ NPS प्लानर", callback_data="csel_nps"),
                 InlineKeyboardButton("📈 स्टेप-अप SIP", callback_data="csel_stepupsip")],
                [InlineKeyboardButton("💸 SWP कैलकुलेटर", callback_data="csel_swp"),
                 InlineKeyboardButton("⏰ विलंब लागत", callback_data="csel_delaycost")],
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("📉 Inflation Eraser", callback_data="csel_inflation"),
                 InlineKeyboardButton("🛡️ Human Life Value", callback_data="csel_hlv")],
                [InlineKeyboardButton("🏖️ Retirement Plan", callback_data="csel_retirement"),
                 InlineKeyboardButton("💳 Premium EMI", callback_data="csel_emi")],
                [InlineKeyboardButton("🏥 Health Cover", callback_data="csel_health"),
                 InlineKeyboardButton("📈 SIP vs Lumpsum", callback_data="csel_sip")],
                [InlineKeyboardButton("📊 MF SIP Planner", callback_data="csel_mfsip"),
                 InlineKeyboardButton("⚖️ ULIP vs MF", callback_data="csel_ulip")],
                [InlineKeyboardButton("🏛️ NPS Planner", callback_data="csel_nps"),
                 InlineKeyboardButton("📈 Step-Up SIP", callback_data="csel_stepupsip")],
                [InlineKeyboardButton("💸 SWP Calculator", callback_data="csel_swp"),
                 InlineKeyboardButton("⏰ Delay Cost", callback_data="csel_delaycost")],
            ]
        await query.edit_message_text(
            i18n.t(_lang, "calc_select_prompt"),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return CALC_TYPE

    if query.data.startswith("csel_"):
        # Recalculate or new calculator
        calc_type = query.data.replace("csel_", "")
        if calc_type in _CALC_PARAMS:
            context.user_data['_calc_type'] = calc_type
            context.user_data['_calc_values'] = {}
            context.user_data['_calc_step'] = 0
            return await _calc_ask_next_param(query, context, edit=True)

    if query.data.startswith("wa_share_"):
        # WhatsApp share flow
        calc_type = query.data.replace("wa_share_", "")
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            _lang = context.user_data.get('lang', 'en')
            await query.edit_message_text(i18n.t(_lang, "register_first"))
            return ConversationHandler.END

        calc_text = context.user_data.get(f"last_calc_{calc_type}", "")
        if not calc_text:
            _lang = agent.get('lang', 'en')
            await query.edit_message_text(i18n.t(_lang, "no_result_to_share"))
            return ConversationHandler.END

        import re as re_mod
        clean_text = re_mod.sub(r'<[^>]+>', '', calc_text)

        company = "Sarathi-AI"
        _brand_web = ''
        _brand_email_addr = ''
        try:
            _t = await db.get_tenant(agent['tenant_id'])
            if _t and _t.get('firm_name'):
                company = _t['firm_name']
            if _t:
                _brand_web = _t.get('brand_website', '') or ''
                _brand_email_addr = _t.get('brand_email', '') or ''
        except Exception:
            pass

        _lang = agent.get('lang', 'en')
        agent_name = agent.get('name', 'Your Advisor')

        _footer = f"Prepared by: {agent_name}"
        if company and company != agent_name:
            _footer += f"\n{company} 🛡️"
        else:
            _footer += " 🛡️"

        _contact_parts = []
        if _brand_web:
            _contact_parts.append(f"🌐 {_brand_web}")
        if _brand_email_addr:
            _contact_parts.append(f"📧 {_brand_email_addr}")
        _brand_line = "\n".join(_contact_parts) if _contact_parts else "🌐 Powered by Sarathi-AI.com"

        _report_url = context.user_data.get('last_report_url', '')
        _report_line = f"\n\n📎 View detailed report:\n{_report_url}" if _report_url else ''

        _share_msg = (
            f"📊 {'वित्तीय विश्लेषण' if _lang == 'hi' else 'Financial Analysis'}\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"{clean_text}\n\n"
            f"{_footer}\n\n"
            f"{_brand_line}"
            f"{_report_line}"
        )
        import urllib.parse as _urlparse
        _direct_link = f"https://wa.me/?text={_urlparse.quote(_share_msg)}"

        context.user_data["wa_share_pending"] = {
            "calc_type": calc_type,
            "text": clean_text,
            "agent_name": agent_name,
            "company": company,
            "report_url": _report_url,
            "website": _brand_web,
            "email": _brand_email_addr,
        }

        if _lang == 'hi':
            _wa_text = (
                "📱 <b>WhatsApp पर शेयर करें</b>\n\n"
                f"👉 <a href=\"{h(_direct_link)}\">सीधे WhatsApp खोलें</a> — खुद कॉन्टैक्ट चुनें\n\n"
                "━━ या ━━\n\n"
                "क्लाइंट का फ़ोन नंबर टाइप करें (10 अंक):\n"
                "<i>उदाहरण: 9876543210</i>"
            )
        else:
            _wa_text = (
                "📱 <b>Share on WhatsApp</b>\n\n"
                f"👉 <a href=\"{h(_direct_link)}\">Open WhatsApp directly</a> — pick a contact yourself\n\n"
                "━━ OR ━━\n\n"
                "Type the client's phone number (10 digits):\n"
                "<i>Example: 9876543210</i>"
            )

        await query.edit_message_text(
            _wa_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return ConversationHandler.END  # Exit conv, wa_share_phone_handler picks it up

    return ConversationHandler.END


async def wa_share_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive phone number for WhatsApp sharing and generate link."""
    pending = context.user_data.get("wa_share_pending")
    if not pending:
        return  # Not in share flow, skip

    agent = await db.get_agent(str(update.effective_user.id))
    lang = agent.get('lang', 'en') if agent else context.user_data.get('lang', 'en')

    phone = update.message.text.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not (phone.isdigit() and len(phone) in (10, 12)):
        err = ("❌ अमान्य फ़ोन नंबर। कृपया 10 अंकों का नंबर दर्ज करें।\n"
               "उदाहरण: 9876543210") if lang == 'hi' else (
               "❌ Invalid phone number. Please enter a 10-digit number.\n"
               "Example: 9876543210")
        await update.message.reply_text(err)
        return

    # Generate WhatsApp share link
    calc_text = pending["text"]
    agent_name = pending.get("agent_name", "Your Advisor")
    company = pending.get("company", "Sarathi-AI")
    _rurl = pending.get("report_url", "")
    _p_web = pending.get("website", "")
    _p_email = pending.get("email", "")

    footer = f"Prepared by: {agent_name}"
    if company and company != agent_name:
        footer += f"\n{company} 🛡️"
    else:
        footer += " 🛡️"

    _cp = []
    if _p_web:
        _cp.append(f"🌐 {_p_web}")
    if _p_email:
        _cp.append(f"📧 {_p_email}")
    _bl = "\n".join(_cp) if _cp else "🌐 Powered by Sarathi-AI.com"

    _rpt_line = f"\n\n📎 View detailed report:\n{_rurl}" if _rurl else ''
    share_msg = (
        f"📊 {'वित्तीय विश्लेषण' if lang == 'hi' else 'Financial Analysis'}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"{calc_text}\n\n"
        f"{footer}\n\n"
        f"{_bl}"
        f"{_rpt_line}"
    )

    link = wa.generate_wa_link(phone, share_msg)

    if lang == 'hi':
        await update.message.reply_text(
            f"✅ <b>WhatsApp शेयर लिंक तैयार!</b>\n\n"
            f"📱 <a href=\"{h(link)}\">WhatsApp पर भेजने के लिए यहाँ क्लिक करें</a>\n\n"
            f"<i>यह WhatsApp में मैसेज पहले से भरा हुआ खोलेगा।</i>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    else:
        await update.message.reply_text(
            f"✅ <b>WhatsApp Share Link Ready!</b>\n\n"
            f"📱 <a href=\"{h(link)}\">Click here to send on WhatsApp</a>\n\n"
            f"<i>This will open WhatsApp with the message pre-filled.</i>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    # Clear pending state
    del context.user_data["wa_share_pending"]


# =============================================================================
#  /renewals — VIEW UPCOMING RENEWALS
# =============================================================================

@registered
async def cmd_renewals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upcoming policy renewals."""
    agent = await _get_agent(update)
    if not agent:
        return

    renewals = await db.get_upcoming_renewals(agent['agent_id'], days_ahead=60)
    lang = agent.get('lang', 'en')
    hi = lang == 'hi'
    if not renewals:
        _msg = "✅ अगले 60 दिनों में कोई रिन्यूअल नहीं। सब ठीक!" if hi else \
              "✅ No renewals due in the next 60 days. All clear!"
        await update.message.reply_text(_msg)
        return

    _title = "🔄 <b>आगामी रिन्यूअल</b>" if hi else "🔄 <b>Upcoming Renewals</b>"
    lines = [f"{_title}\n━━━━━━━━━━━━━━━━━━\n"]
    for pol in renewals[:10]:
        try:
            ren_dt = datetime.fromisoformat(pol['renewal_date'])
            days = (ren_dt - datetime.now()).days
            urgency = "🔴" if days <= 7 else "🟡" if days <= 30 else "🟢"
        except (ValueError, TypeError):
            days = "?"
            urgency = "⚪"

        lines.append(
            f"{urgency} <b>{h(pol.get('client_name', 'Client'))}</b>\n"
            f"   📋 {h(pol.get('plan_name', 'N/A'))} | "
            f"₹{pol.get('premium', 0):,.0f}\n"
            f"   📅 {h(pol['renewal_date'])} ({days} days)\n"
        )

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML)


# =============================================================================
#  /dashboard — FULL BUSINESS DASHBOARD
# =============================================================================

@registered
async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive business dashboard."""
    agent = await _get_agent(update)
    if not agent:
        return

    stats = await db.get_agent_stats(agent['agent_id'])
    pipeline = stats.get('pipeline', {})
    followups = await db.get_pending_followups(agent['agent_id'])
    renewals = await db.get_upcoming_renewals(agent['agent_id'], days_ahead=30)

    server_url = os.getenv("SERVER_URL", "http://localhost:8000")

    lang = agent.get('lang', 'en')
    hi = lang == 'hi'
    msg = (
        i18n.t(lang, "dashboard_title") + "\n"
        f"👤 {h(agent['name'])} | {h(agent.get('firm_name', ''))}\n\n"
        f"📈 <b>{'पाइपलाइन' if hi else 'Pipeline'}:</b>\n"
        f"  🎯 {pipeline.get('prospect', 0)} {'संभावित' if hi else 'Prospects'}\n"
        f"  📞 {pipeline.get('contacted', 0)} {'संपर्क' if hi else 'Contacted'}\n"
        f"  📊 {pipeline.get('pitched', 0)} {'पिच' if hi else 'Pitched'}\n"
        f"  📄 {pipeline.get('proposal_sent', 0)} {'प्रस्ताव' if hi else 'Proposals'}\n"
        f"  ✅ {pipeline.get('closed_won', 0)} {'जीते' if hi else 'Won'}\n\n"
        f"🏆 <b>{'पोर्टफोलियो' if hi else 'Portfolio'}:</b>\n"
        f"  📋 {'सक्रिय पॉलिसी' if hi else 'Active Policies'}: {stats.get('active_policies', 0)}\n"
        f"  💰 {'कुल प्रीमियम' if hi else 'Total Premium'}: ₹{stats.get('total_premium', 0):,.0f}\n"
        f"  💵 {'कमीशन' if hi else 'Commission'}: ₹{stats.get('total_commission', 0):,.0f}\n\n"
        f"📅 <b>{'आज' if hi else 'Today'}:</b>\n"
        f"  🆕 {'नई लीड्स' if hi else 'New Leads'}: {stats.get('today_new_leads', 0)}\n"
        f"  📞 {'इंटरैक्शन' if hi else 'Interactions'}: {stats.get('today_interactions', 0)}\n"
        f"  📋 {'फॉलो-अप बाकी' if hi else 'Follow-ups Due'}: {len(followups)}\n"
        f"  🔄 {'रिन्यूअल (30दिन)' if hi else 'Renewals (30d)'}: {len(renewals)}\n\n"
    )
    _dash_link_text = "वेब डैशबोर्ड खोलें" if hi else "Open Web Dashboard"
    msg += f'🌐 <a href="{server_url}/dashboard">{_dash_link_text}</a>'

    await update.message.reply_text(
        msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# =============================================================================
#  /wa <lead_id> <message> — SEND WHATSAPP MESSAGE
# =============================================================================

@registered
async def cmd_wa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a WhatsApp message to a lead — disabled, use personal messaging."""
    await update.message.reply_text(
        "ℹ️ WhatsApp API integration is disabled.\n\n"
        "Use personal messaging instead — it's more effective! "
        "Your Voice AI assistant can help draft messages.",
        parse_mode=ParseMode.HTML)
    return


# =============================================================================
#  /greet <lead_id> — MANUAL GREETING
# =============================================================================

@registered
async def cmd_greet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a manual greeting to a lead."""
    agent = await _get_agent(update)
    if not agent:
        return

    if not context.args:
        await update.message.reply_text("Usage: /greet &lt;lead_id&gt;",
                                       parse_mode=ParseMode.HTML)
        return

    try:
        lead_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid lead ID")
        return

    lead = await db.get_lead(lead_id)
    if not lead or lead['agent_id'] != agent['agent_id']:
        await update.message.reply_text("❌ Lead not found")
        return

    phone = lead.get('whatsapp') or lead.get('phone')
    if not phone:
        await update.message.reply_text("❌ No phone number for this lead")
        return

    keyboard = [
        [InlineKeyboardButton("🎂 Birthday", callback_data=f"greet_bday_{lead_id}")],
        [InlineKeyboardButton("💍 Anniversary", callback_data=f"greet_anniv_{lead_id}")],
        [InlineKeyboardButton("🙏 Thank You", callback_data=f"greet_thanks_{lead_id}")],
        [InlineKeyboardButton("🎉 Festival", callback_data=f"greet_festival_{lead_id}")],
    ]
    await update.message.reply_text(
        f"💌 <b>Send Greeting to {h(lead['name'])}</b>\n\nSelect type:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


async def greet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle greeting type selection and send."""
    query = update.callback_query

    parts = query.data.split("_")
    greet_type = parts[1]
    lead_id = int(parts[2])

    agent = await _require_agent_auth(update, context)
    if not agent:
        return
    lang = agent.get('lang', 'en')
    await query.answer("शुभकामना भेजी जा रही है..." if lang == 'hi' else "Sending greeting...")
    lead = await db.get_lead(lead_id)
    if not lead or lead['agent_id'] != agent['agent_id']:
        await query.edit_message_text(i18n.t(lang, "lead_not_found"))
        return

    phone = lead.get('whatsapp') or lead.get('phone')

    _co = agent.get('firm_name', 'Sarathi-AI')
    _tl = agent.get('brand_tagline', 'AI-Powered Financial Advisor CRM')
    # Build compliance footer for WhatsApp messages
    _cf = ''
    try:
        _cf = await db.build_compliance_credentials(agent['agent_id'])
    except Exception:
        pass

    if greet_type == 'bday':
        result = await wa.send_birthday_greeting(
            phone, lead['name'],
            agent_name=agent['name'], company=_co, tagline=_tl,
            compliance_footer=_cf)
    elif greet_type == 'anniv':
        result = await wa.send_anniversary_greeting(
            phone, lead['name'],
            agent_name=agent['name'], company=_co, tagline=_tl,
            compliance_footer=_cf)
    elif greet_type == 'thanks':
        msg = (f"Dear {lead['name'].split()[0]},\n\n"
               f"Thank you for trusting us with your financial security. "
               f"Your confidence means the world to us.\n\n"
               f"We're always here to help. Reach out anytime.\n\n"
               f"Warm regards,\n{agent['name']}\n_{_co}_\n_{_tl}_ 🌟")
        result = await wa.send_text(phone, msg)
    elif greet_type == 'festival':
        msg = (f"Dear {lead['name'].split()[0]},\n\n"
               f"Wishing you and your family a joyous festival season! "
               f"May this time bring health, wealth, and happiness.\n\n"
               f"Remember, the best celebration is knowing your "
               f"family is protected.\n\n"
               f"Warm wishes,\n{agent['name']}\n_{_co}_\n_{_tl}_ 🌟")
        result = await wa.send_text(phone, msg)
    else:
        result = {"error": "unknown type"}

    if result.get('success'):
        await db.log_greeting(lead_id, agent['agent_id'], greet_type,
                               'whatsapp', f"{greet_type} greeting")
        _lang = agent.get('lang', 'en')
        await query.edit_message_text(
            i18n.t(_lang, "greet_sent", gtype=greet_type.title(), name=lead['name']))
    else:
        _lang = agent.get('lang', 'en')
        await query.edit_message_text(
            i18n.t(_lang, "greet_failed", error=result.get('error', 'Unknown')))


# =============================================================================
#  /lead <lead_id> — VIEW LEAD DETAIL
# =============================================================================

@registered
async def cmd_lead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show full detail of a single lead."""
    agent = await _get_agent(update)
    if not agent:
        return

    if not context.args:
        lang = agent.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(lang, "usage_lead"),
            parse_mode=ParseMode.HTML)
        return

    try:
        lead_id = int(context.args[0])
    except ValueError:
        lang = agent.get('lang', 'en')
        await update.message.reply_text(i18n.t(lang, "invalid_id"))
        return

    lead = await db.get_lead(lead_id)
    if not lead or lead['agent_id'] != agent['agent_id']:
        lang = agent.get('lang', 'en')
        await update.message.reply_text(i18n.t(lang, "lead_not_found"))
        return

    lang = agent.get('lang', 'en')
    text = await _format_lead_detail(lead, lang)
    if lang == 'hi':
        keyboard = [
            [InlineKeyboardButton("📝 फॉलो-अप लॉग करें",
                                  callback_data=f"fusel_{lead_id}")],
            [InlineKeyboardButton("🔄 स्टेज बदलें",
                                  callback_data=f"quickconv_{lead_id}")],
            [InlineKeyboardButton("💌 शुभकामना भेजें",
                                  callback_data=f"greetpick_{lead_id}")],
            [InlineKeyboardButton("📊 कैलकुलेटर चलाएं",
                                  callback_data="calc_menu")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Log Follow-up",
                                  callback_data=f"fusel_{lead_id}")],
            [InlineKeyboardButton("🔄 Move Stage",
                                  callback_data=f"quickconv_{lead_id}")],
            [InlineKeyboardButton("💌 Send Greeting",
                                  callback_data=f"greetpick_{lead_id}")],
            [InlineKeyboardButton("📊 Run Calculator",
                                  callback_data="calc_menu")],
        ]
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


async def _format_lead_detail(lead: dict, lang: str = 'en') -> str:
    """Build a comprehensive detail view of a single lead."""
    lead_id = lead['lead_id']

    # Fetch history
    interactions = await db.get_lead_interactions(lead_id, limit=5)
    policies = await db.get_policies_by_lead(lead_id)
    greetings = await db.get_lead_greetings(lead_id, limit=5)

    msg = (
        f"{i18n.t(lang, 'lead_detail_header')} #{lead_id}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{i18n.t(lang, 'detail_name')}: <b>{h(lead['name'])}</b>\n"
        f"{i18n.t(lang, 'detail_phone')}: {h(lead.get('phone', 'N/A'))}\n"
        f"{i18n.t(lang, 'detail_whatsapp')}: {h(lead.get('whatsapp', 'N/A'))}\n"
        f"{i18n.t(lang, 'detail_email')}: {h(lead.get('email', 'N/A'))}\n"
        f"{i18n.t(lang, 'detail_dob')}: {h(lead.get('dob', 'N/A'))}\n"
        f"{i18n.t(lang, 'detail_anniversary')}: {h(lead.get('anniversary', 'N/A'))}\n"
        f"{i18n.t(lang, 'detail_city')}: {h(lead.get('city', 'N/A'))}\n"
        f"{i18n.t(lang, 'detail_need')}: {h(lead.get('need_type', 'N/A'))}\n"
        f"{i18n.t(lang, 'detail_stage')}: {_stage_emoji(lead['stage'])} {h(lead['stage'])}\n"
        f"{i18n.t(lang, 'detail_added')}: {h(lead.get('created_at', 'N/A'))}\n"
        f"{'🔐 DPDP' if lang != 'hi' else '🔐 डेटा सहमति'}: {'✅' if lead.get('dpdp_consent') else '❌'}\n"
    )

    if lead.get('notes'):
        msg += f"{i18n.t(lang, 'detail_notes')}: {h(lead['notes'])}\n"

    # Interaction History
    if interactions:
        msg += f"\n📞 <b>{i18n.t(lang, 'detail_interactions')}:</b>\n"
        for ix in interactions:
            ts = ix.get('created_at', '')[:10]
            ch = ix.get('channel', '')
            itype = ix.get('type', '')
            summary = (ix.get('summary') or '')[:60]
            status_icon = "✅" if ch == 'whatsapp' else "📞" if itype == 'call' else "📧"
            msg += f"  {status_icon} {ts} | {h(itype)} | {h(summary)}\n"
            if ix.get('follow_up_date'):
                msg += f"      ↳ Next follow-up: {h(ix['follow_up_date'][:10])}\n"
    else:
        msg += f"\n📞 {i18n.t(lang, 'detail_no_interactions')}\n"

    # Policies
    if policies:
        msg += f"\n{i18n.t(lang, 'detail_policies')}:\n"
        for pol in policies:
            status_icon = "✅" if pol.get('status') == 'active' else "⚪"
            msg += (f"  {status_icon} {h(pol.get('insurer', ''))} — "
                    f"{h(pol.get('plan_name', ''))}\n"
                    f"      ₹{pol.get('sum_insured', 0):,.0f} SI | "
                    f"₹{pol.get('premium', 0):,.0f}/yr\n")
    else:
        msg += f"\n📋 {i18n.t(lang, 'detail_no_policies')}\n"

    # Greetings sent
    if greetings:
        msg += f"\n{i18n.t(lang, 'detail_greetings')}:\n"
        for g in greetings:
            ts = (g.get('sent_at') or '')[:10]
            msg += f"  • {ts} — {h(g.get('type', ''))}\n"

    return msg


# =============================================================================
#  /help — COMMAND REFERENCE
# =============================================================================

@registered
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show role-aware command reference."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    lang = agent.get('lang', 'en') if agent else 'en'
    role = agent.get('role', 'agent') if agent else 'agent'
    is_owner = role in ('owner', 'admin')

    # Get plan info for feature gating display
    tenant = await db.get_tenant(agent['tenant_id']) if agent and agent.get('tenant_id') else None
    plan = tenant.get('plan', 'trial') if tenant else 'trial'
    has_ai = True  # AI tools available for all plans (quota-limited)
    has_wa = bool(tenant and tenant.get('wa_phone_id'))

    base_cmds = i18n.t(lang, "help_header") + "\n\n"
    base_cmds += i18n.t(lang, "help_lead_mgmt") + "\n\n"
    base_cmds += i18n.t(lang, "help_voice") + "\n\n"
    base_cmds += i18n.t(lang, "help_sales") + "\n\n"
    base_cmds += i18n.t(lang, "help_claims") + "\n\n"
    base_cmds += i18n.t(lang, "help_calc") + "\n"

    if has_wa:
        base_cmds += i18n.t(lang, "help_wa_calc") + "\n\n"
        base_cmds += i18n.t(lang, "help_wa_section") + "\n\n"
    else:
        base_cmds += "\n"

    base_cmds += i18n.t(lang, "help_reminders") + "\n\n"
    base_cmds += i18n.t(lang, "help_dashboard") + "\n\n"

    if has_ai:
        base_cmds += i18n.t(lang, "help_ai_active") + "\n"
    else:
        base_cmds += i18n.t(lang, "help_ai_locked") + "\n"

    # Only show /plans for owners (agents can't manage billing)
    if is_owner:
        base_cmds += i18n.t(lang, "help_plans") + "\n"

    if is_owner:
        base_cmds += "\n" + i18n.t(lang, "help_owner") + "\n"

    base_cmds += "\n" + i18n.t(lang, "help_footer") + "\n\n"
    base_cmds += i18n.t(lang, "help_plan_role", plan=plan.title(), role=role.title())

    await update.message.reply_text(base_cmds, parse_mode=ParseMode.HTML)


# =============================================================================
#  🔊 AUDIO HELP — Send voice explanations for top help topics
# =============================================================================

_AUDIO_HELP_TOPICS = {
    "voice_crm": {"en": "🎙️ Voice-First CRM", "hi": "🎙️ वॉइस-फर्स्ट CRM"},
    "ai_tools":  {"en": "🤖 AI Tools",         "hi": "🤖 AI टूल्स"},
    "calculators": {"en": "🧮 Calculators",     "hi": "🧮 कैलकुलेटर"},
    "getting_started": {"en": "🚀 Getting Started", "hi": "🚀 शुरू करें"},
    "welcome":   {"en": "👋 Welcome Guide",     "hi": "👋 स्वागत गाइड"},
}

@registered
async def cmd_listenhelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show inline keyboard to pick a help topic and receive it as voice note."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    lang = agent.get('lang', 'en') if agent else 'en'
    if lang == 'hi':
        text = "🔊 <b>ऑडियो हेल्प</b>\n\nकिसी टॉपिक पर टैप करें, हम वॉइस नोट भेजेंगे:"
    else:
        text = "🔊 <b>Audio Help</b>\n\nTap a topic to receive a voice explanation:"
    buttons = []
    for key, labels in _AUDIO_HELP_TOPICS.items():
        buttons.append([InlineKeyboardButton(labels[lang], callback_data=f"audiohelp_{key}")])
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons))


async def _audiohelp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle audio help topic selection — send voice note."""
    query = update.callback_query
    await query.answer()
    topic = query.data.replace("audiohelp_", "")
    agent = context.user_data.get('_agent') or {}
    lang = agent.get('lang', 'en')

    import pathlib
    audio_dir = pathlib.Path(__file__).parent / "static" / "audio"
    audio_file = audio_dir / f"{topic}_{lang}.mp3"
    if not audio_file.exists():
        # Fallback to English
        audio_file = audio_dir / f"{topic}_en.mp3"
    if not audio_file.exists():
        await query.message.reply_text("⚠️ Audio not available for this topic yet.")
        return

    label = _AUDIO_HELP_TOPICS.get(topic, {}).get(lang, topic)
    caption = f"🔊 {label}"
    with open(audio_file, "rb") as f:
        await query.message.reply_voice(voice=f, caption=caption)


# =============================================================================
#  /plans — SHOW SUBSCRIPTION PLANS
# =============================================================================

@registered
async def cmd_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available subscription plans with current status & subscribe buttons."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return
    # Non-owner agents in a team/enterprise plan can't manage billing
    role = agent.get('role', 'agent')
    if role not in ('owner', 'admin'):
        lang = agent.get('lang', 'en')
        if lang == 'hi':
            await update.message.reply_text(
                "ℹ️ सब्सक्रिप्शन प्लान आपके फर्म एडमिन द्वारा प्रबंधित किए जाते हैं।\n"
                "कृपया अपने एडमिन से संपर्क करें।")
        else:
            await update.message.reply_text(
                "ℹ️ Subscription plans are managed by your firm admin.\n"
                "Please contact your admin for plan changes.")
        return
    tenant = await db.get_tenant(agent['tenant_id']) if agent.get('tenant_id') else None
    status = tenant.get('subscription_status', 'unknown') if tenant else 'unknown'
    plan = tenant.get('plan', 'trial') if tenant else 'trial'
    trial_end = tenant.get('trial_ends_at', '') if tenant else ''

    status_line = ""
    if status == 'trial' and trial_end:
        try:
            days_left = (datetime.fromisoformat(trial_end) - datetime.now()).days
            status_line = f"📅 <b>Current: Free Trial</b> — {max(0, days_left)} days remaining\n\n"
        except ValueError:
            status_line = "📅 <b>Current: Free Trial</b>\n\n"
    elif status == 'active':
        status_line = f"✅ <b>Current: {plan.title()} Plan (Active)</b>\n\n"
    elif status == 'expired':
        status_line = "⚠️ <b>Current: Expired</b> — Subscribe to reactivate\n\n"

    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")

    # Build subscribe buttons based on current plan
    keyboard = []
    if plan != 'individual':
        keyboard.append([InlineKeyboardButton(
            "🧑 Solo Advisor — ₹199/mo",
            callback_data="pay_individual")])
    if plan != 'team':
        keyboard.append([InlineKeyboardButton(
            "👥 Team — ₹799/mo",
            callback_data="pay_team")])
    if plan != 'enterprise':
        keyboard.append([InlineKeyboardButton(
            "🏢 Enterprise — ₹1,999/mo",
            callback_data="pay_enterprise")])
    keyboard.append([InlineKeyboardButton(
        "🌐 Subscribe on Web", url=f"{server_url}/#pricing")])
    # Show cancel option for active paid subscribers
    if status == 'active' and plan not in ('trial',):
        keyboard.append([InlineKeyboardButton(
            "❌ Cancel Subscription", callback_data="cancel_sub")])

    await update.message.reply_text(
        f"💎 <b>Sarathi-AI Plans</b>\n\n"
        f"{status_line}"
        f"🧑 <b>Solo Advisor</b> — ₹199/mo\n"
        f"   └ Admin only, full CRM, calculators, reminders\n\n"
        f"👥 <b>Team</b> — ₹799/mo\n"
        f"   └ Admin + 5 advisors, WhatsApp API, campaigns, G-Drive\n\n"
        f"🏢 <b>Enterprise</b> — ₹1,999/mo\n"
        f"   └ Admin + 25 advisors, admin controls, custom branding, API\n\n"
        f"💳 <b>Pay via UPI, Card, or Net Banking</b>\n"
        f"Choose a plan below to subscribe:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard))


# =============================================================================
#  /wacalc <lead_id> — SHARE CALCULATOR REPORT VIA WHATSAPP
# =============================================================================

@registered
async def cmd_wacalc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Share calculator report via WhatsApp — disabled."""
    await update.message.reply_text(
        "ℹ️ WhatsApp API integration is disabled.\n\n"
        "Use /calc to generate reports and share them personally with clients.",
        parse_mode=ParseMode.HTML)
    return


def _wa_calc_summary(calc_type: str, result, client_name: str) -> str:
    """Build WhatsApp-friendly calculator summary text."""
    first = client_name.split()[0] if client_name else "Sir/Ma'am"
    fc = calc.format_currency

    if calc_type == "inflation":
        return (
            f"📉 *Inflation Impact Analysis*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"💰 Current Value: {fc(result.current_value)}/month\n"
            f"📅 Time Horizon: {result.years} years\n"
            f"📊 Inflation Rate: {result.inflation_rate}%\n\n"
            f"⚠️ *The Hard Truth:*\n"
            f"Your {fc(result.current_value)} today will only buy "
            f"*{fc(result.purchasing_power_left)}* worth of goods "
            f"in {result.years} years!\n\n"
            f"📈 You'll need *{fc(result.future_value_needed)}/month* "
            f"to maintain the same lifestyle.\n\n"
            f"🔴 Purchasing power eroded: *{result.erosion_percent:.1f}%*\n\n"
            f"💡 _Let me show you how we can protect your purchasing power._"
        )
    elif calc_type == "hlv":
        return (
            f"🛡️ *Human Life Value Analysis*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"Based on your financial profile:\n"
            f"💰 Monthly Expense: {fc(result.monthly_expense)}\n"
            f"🏦 Loans: {fc(result.outstanding_loans)}\n"
            f"📋 Existing Cover: {fc(result.existing_cover)}\n\n"
            f"✅ *Recommended Life Cover: {fc(result.recommended_cover)}*\n"
            f"🔴 Coverage Gap: *{fc(result.gap)}*\n\n"
            f"💡 _Protect your family's future with the right term plan._"
        )
    elif calc_type == "retirement":
        return (
            f"🏖️ *Retirement Planning Analysis*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"📅 Retire at {result.retirement_age} | Life Expectancy: {result.life_expectancy}\n"
            f"💰 Current Expense: {fc(result.monthly_expense)}/month\n\n"
            f"At retirement, you'll need:\n"
            f"📊 Monthly Expense: *{fc(result.expense_at_retirement)}*\n"
            f"💰 Total Corpus: *{fc(result.corpus_needed)}*\n\n"
            f"📈 Start SIP of *{fc(result.monthly_sip_needed)}/month* today!\n\n"
            f"💡 _The earlier you start, the less you need._"
        )
    elif calc_type == "emi":
        text = (
            f"💳 *Premium EMI Analysis*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"Total Premium: {fc(result.total_premium)}\n"
            f"Net Premium: *{fc(result.net_premium)}*\n"
            f"Down Payment: {fc(result.down_payment)}\n\n"
            f"📊 *EMI Options:*\n"
        )
        for opt in result.emi_options:
            text += f"  • {opt['months']}mo → *{fc(opt['monthly_emi'])}*/mo\n"
        text += f"\n💡 _Affordable protection is just an EMI away._"
        return text
    elif calc_type == "health":
        return (
            f"🏥 *Health Cover Analysis*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"👤 Age: {result.age} | Family: {result.family_size}\n"
            f"🏙️ City: {result.city_tier}\n\n"
            f"✅ Recommended Cover: *{fc(result.recommended_si)}*\n"
            f"🔴 Gap: *{fc(result.gap)}*\n\n"
            f"💳 Est. Premium: {fc(result.estimated_premium_range['low'])} "
            f"- {fc(result.estimated_premium_range['high'])}/year\n\n"
            f"💡 _Don't let medical bills wipe out your savings._"
        )
    elif calc_type == "sip":
        return (
            f"📈 *SIP vs Lumpsum Analysis*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"💰 Amount: {fc(result.investment_amount)}\n"
            f"📅 Period: {result.years} years @ {result.expected_return}%\n\n"
            f"📊 Lumpsum: *{fc(result.lumpsum_maturity)}*\n"
            f"📊 SIP: *{fc(result.sip_maturity)}* ({fc(result.sip_monthly)}/mo)\n\n"
            f"🏆 Winner: *{result.winner}*\n\n"
            f"💡 _Start your wealth creation journey today._"
        )
    elif calc_type == "mfsip":
        return (
            f"📊 *MF SIP Goal Planner*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"🎯 Goal: {fc(result.goal_amount)}\n"
            f"📅 Timeline: {result.years} years @ {result.annual_return}%\n\n"
            f"📈 Monthly SIP: *{fc(result.monthly_sip)}*\n"
            f"💰 Total Invested: {fc(result.total_invested)}\n"
            f"🏆 Wealth Gained: *{fc(result.wealth_gained)}*\n\n"
            f"💡 _Discipline + compounding = wealth creation._"
        )
    elif calc_type == "ulip":
        return (
            f"⚖️ *ULIP vs Mutual Fund Comparison*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"💰 Annual: {fc(result.investment_amount)} × {result.years} years\n\n"
            f"📊 ULIP Maturity: *{fc(result.ulip_maturity)}*\n"
            f"📈 MF Maturity: *{fc(result.mf_maturity)}*\n"
            f"🛡️ ULIP Insurance: {fc(result.insurance_cover)}\n\n"
            f"🏆 Winner: *{result.winner}* by {fc(result.difference)}\n\n"
            f"💡 _Choose based on your goals, not just returns._"
        )
    elif calc_type == "nps":
        return (
            f"🏛️ *NPS Pension Plan Analysis*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Dear *{first}*,\n\n"
            f"💰 Monthly: {fc(result.monthly_contribution)}\n"
            f"📅 {result.years_to_retire} yrs @ {result.annual_return}%\n\n"
            f"📊 Corpus: *{fc(result.total_corpus)}*\n"
            f"💳 Pension: *{fc(result.monthly_pension_estimate)}/mo*\n"
            f"🏷️ Tax Saved: {fc(result.tax_saved_yearly)}/yr\n\n"
            f"💡 _NPS: Tax savings today, pension tomorrow._"
        )
    return "Financial analysis prepared for you."


async def _run_and_send_calc(query, agent, lead, calc_type: str):
    """Run a calculator, generate report, send to lead's WhatsApp."""
    phone = lead.get('whatsapp') or lead.get('phone')
    lang = agent.get('lang', 'en')
    server_url = os.getenv("SERVER_URL", "http://localhost:8000")

    # Agent branding for PDF header/footer
    agent_name = agent.get('name', '')
    agent_phone = agent.get('phone', '')
    agent_photo_url = ""
    if agent.get('profile_photo'):
        agent_photo_url = f"{server_url}{agent['profile_photo']}"
    # Get firm name for branding
    company = "Sarathi-AI Business Technologies"
    tenant = None
    try:
        tenant = await db.get_tenant(agent['tenant_id'])
        if tenant and tenant.get('firm_name'):
            company = tenant['firm_name']
    except Exception:
        pass

    calc_labels = {
        "inflation": "Inflation Eraser",
        "hlv": "HLV (Human Life Value)",
        "retirement": "Retirement Planner",
        "emi": "EMI Calculator",
        "health": "Health Cover Estimator",
        "sip": "SIP vs Lumpsum",
        "mfsip": "MF SIP Planner",
        "ulip": "ULIP vs Mutual Fund",
        "nps": "NPS Planner",
    }

    # Agent branding kwargs for report generators
    _brand_info = None
    if tenant:
        _brand_info = {
            'firm_name': company,
            'primary_color': tenant.get('brand_primary_color') or None,
            'accent_color': tenant.get('brand_accent_color') or None,
            'logo': tenant.get('brand_logo') or None,
            'tagline': tenant.get('brand_tagline') or None,
            'phone': tenant.get('brand_phone') or None,
            'email': tenant.get('brand_email') or None,
            'website': tenant.get('brand_website') or None,
        }
    _brand = dict(agent_name=agent_name, agent_phone=agent_phone,
                  agent_photo_url=agent_photo_url, company=company,
                  brand=_brand_info)

    # Run calculator with sensible defaults
    report_url = None
    if calc_type == "inflation":
        result = calc.inflation_eraser(50000, 6.0, 10)
        html = pdf.generate_inflation_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "inflation", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    elif calc_type == "hlv":
        result = calc.hlv_calculator(50000, 2000000, 1500000, 0, 0)
        html = pdf.generate_hlv_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "hlv", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    elif calc_type == "retirement":
        result = calc.retirement_planner(35, 60, 85, 40000, 7.0, 12.0, 8.0, 0)
        html = pdf.generate_retirement_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "retirement", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    elif calc_type == "emi":
        result = calc.emi_calculator(25000, 5, 18.0, 10.0, 25.0)
        html = pdf.generate_emi_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "emi", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    elif calc_type == "health":
        result = calc.health_cover_estimator(35, "2A+2C", "metro", 50000, 0)
        html = pdf.generate_health_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "health", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    elif calc_type == "sip":
        result = calc.sip_vs_lumpsum(500000, 10, 12.0)
        html = pdf.generate_sip_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "sip", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    elif calc_type == "mfsip":
        result = calc.mf_sip_planner(5000000, 15, 12.0, 0)
        html = pdf.generate_mfsip_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "mfsip", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    elif calc_type == "ulip":
        result = calc.ulip_vs_mf(100000, 15, 10.0, 12.0)
        html = pdf.generate_ulip_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "ulip", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    elif calc_type == "nps":
        result = calc.nps_planner(5000, 30, 60, 10.0, 30.0)
        html = pdf.generate_nps_html(result, lead['name'], **_brand)
        fname = pdf.save_html_report(html, "nps", lead['name'], advisor_name=company)
        report_url = f"{server_url}/reports/{fname}"
    else:
        await query.edit_message_text("❌ Unknown calculator type")
        return

    # Build WhatsApp summary
    summary = _wa_calc_summary(calc_type, result, lead['name'])

    # Send via WhatsApp
    wa_result = await wa.send_pitch_summary(
        to=phone, client_name=lead['name'],
        calc_type=calc_labels.get(calc_type, calc_type),
        summary_text=summary,
        pdf_url=report_url,
        agent_name=agent['name'],
    )

    if wa_result.get('success'):
        # Log interaction
        await db.log_interaction(
            lead_id=lead['lead_id'], agent_id=agent['agent_id'],
            interaction_type='pitch', channel='whatsapp',
            summary=f"Sent {calc_labels.get(calc_type, calc_type)} report via WhatsApp")

        if wa_result.get('method') == 'link':
            link = wa_result.get('wa_link', '')
            await query.edit_message_text(
                f"📤 <b>{'भेजने के लिए क्लिक करें' if lang == 'hi' else 'Click to send via WhatsApp'}</b>\n\n"
                f"👤 {h(lead['name'])}\n"
                f"📱 <a href=\"{h(link)}\">WhatsApp {'पर भेजें' if lang == 'hi' else 'Send'}</a>",
                parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        else:
            report_line = f'📄 <a href="{h(report_url)}">View Report</a>' if report_url else ""
            await query.edit_message_text(
                i18n.t(lang, "wacalc_sent",
                       calc_type=calc_labels.get(calc_type, calc_type),
                       name=h(lead['name']), phone=h(phone),
                       report_line=report_line),
                parse_mode=ParseMode.HTML)
    else:
        err = wa_result.get('error', 'Unknown error')
        await query.edit_message_text(
            i18n.t(lang, "wa_failed", error=h(str(err))),
            parse_mode=ParseMode.HTML)


# =============================================================================
#  /wadash <lead_id> — SEND PORTFOLIO SUMMARY VIA WHATSAPP
# =============================================================================

@registered
async def cmd_wadash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send portfolio summary via WhatsApp — disabled."""
    await update.message.reply_text(
        "ℹ️ WhatsApp API integration is disabled.\n\n"
        "Use /lead &lt;lead_id&gt; to view the portfolio and share it personally.",
        parse_mode=ParseMode.HTML)
    return


# =============================================================================
#  /lang — CHANGE LANGUAGE
# =============================================================================

@registered
async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch bot language between English and Hindi."""
    agent = await _get_agent(update)
    if not agent:
        return
    lang = agent.get('lang', 'en')

    keyboard = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="lang_hi")],
    ]
    await update.message.reply_text(
        i18n.t(lang, "lang_ask"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


# =============================================================================
#  CALLBACK ROUTER (for inline buttons)
# =============================================================================

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route inline button callbacks."""
    query = update.callback_query
    data = query.data

    if data.startswith("stg_"):
        # Quick stage change from lead detail quickconv_ flow
        await query.answer()
        new_stage = data.replace("stg_", "")
        lead_id = context.user_data.get('convert_lead_id')
        if not lead_id:
            _agent = await db.get_agent(str(query.from_user.id))
            _l = _agent.get('lang', 'en') if _agent else 'en'
            expired_msg = "❌ सत्र समाप्त। कृपया लीड विवरण से पुनः प्रयास करें।" if _l == 'hi' else "❌ Session expired. Please try again from the lead detail."
            await query.edit_message_text(expired_msg)
            return
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        lang = agent.get('lang', 'en')
        success = await db.update_lead_stage(lead_id, new_stage)
        if success:
            lead = await db.get_lead(lead_id)
            msg = i18n.t(lang, "stage_updated",
                         name=h(lead['name']),
                         stage_emoji=_stage_emoji(new_stage),
                         stage=h(new_stage))
            if new_stage == 'closed_won':
                if lang == 'hi':
                    msg += f"\n\n🎉 बधाई हो! पॉलिसी रिकॉर्ड करने के लिए /policy {lead_id} दबाएं।"
                else:
                    msg += f"\n\n🎉 Congratulations! Use /policy {lead_id} to record the policy."
                # Trigger proactive deal celebration
                import biz_reminders as _rem
                asyncio.create_task(_rem.run_deal_won_celebration(
                    agent_id=agent['agent_id'],
                    lead_name=lead['name'],
                    premium=lead.get('premium_budget', 0) or 0))
        else:
            msg = "❌ Failed to update stage." if lang == 'en' else "❌ स्टेज अपडेट में विफल।"
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        context.user_data.pop('convert_lead_id', None)

    elif data.startswith("stage_"):
        # View leads by stage
        await query.answer()
        stage = data.replace("stage_", "")
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        leads = await db.get_leads_by_agent(agent['agent_id'], stage=stage)
        _lang = agent.get('lang', 'en')
        _hi = _lang == 'hi'
        if not leads:
            _no = f"'{stage}' में कोई लीड नहीं।" if _hi else f"No leads in '{stage}' stage."
            await query.edit_message_text(_no)
            return
        lines = [f"📋 <b>{h(stage.replace('_', ' ').title())}</b> ({len(leads)})\n"]
        kb = []
        for lead in leads[:10]:
            lines.append(
                f"• <b>#{lead['lead_id']}</b> {h(lead['name'])}\n"
                f"  📱 {h(lead.get('phone', 'N/A'))} | {h(lead.get('need_type', ''))}")
            kb.append([InlineKeyboardButton(
                f"👤 #{lead['lead_id']} {lead['name']}",
                callback_data=f"leadview_{lead['lead_id']}")])
        _tap = "नाम टैप करें विवरण देखें:" if _hi else "Tap a name to view full details:"
        lines.append(f"\n<i>{_tap}</i>")
        await query.edit_message_text("\n".join(lines),
                                     reply_markup=InlineKeyboardMarkup(kb),
                                     parse_mode=ParseMode.HTML)

    elif data.startswith("leadview_"):
        # Inline lead detail view
        await query.answer()
        lead_id = int(data.replace("leadview_", ""))
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        lead = await db.get_lead(lead_id)
        _is_admin = agent.get('role') in ('owner', 'admin')
        if not lead or (lead['agent_id'] != agent['agent_id'] and not _is_admin):
            _lang = agent.get('lang', 'en')
            await query.edit_message_text(i18n.t(_lang, "lead_not_found"))
            return
        _lang = agent.get('lang', 'en')
        text = await _format_lead_detail(lead, _lang)
        if _lang == "hi":
            keyboard = [
                [InlineKeyboardButton("📝 फॉलो-अप लॉग करें",
                                      callback_data=f"fusel_{lead_id}")],
                [InlineKeyboardButton("🔄 स्टेज बदलें",
                                      callback_data=f"quickconv_{lead_id}")],
                [InlineKeyboardButton("💌 शुभकामना भेजें",
                                      callback_data=f"greetpick_{lead_id}")],
                [InlineKeyboardButton("✏️ लीड संपादित करें",
                                      callback_data=f"editbtn_{lead_id}")],
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("📝 Log Follow-up",
                                      callback_data=f"fusel_{lead_id}")],
                [InlineKeyboardButton("🔄 Move Stage",
                                      callback_data=f"quickconv_{lead_id}")],
                [InlineKeyboardButton("💌 Send Greeting",
                                      callback_data=f"greetpick_{lead_id}")],
                [InlineKeyboardButton("✏️ Edit Lead",
                                      callback_data=f"editbtn_{lead_id}")],
            ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("quickconv_"):
        # Quick convert from lead detail — shows stage buttons
        await query.answer()
        lead_id = int(data.replace("quickconv_", ""))
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            _lang = context.user_data.get('lang', 'en')
            await query.edit_message_text(i18n.t(_lang, "register_first"))
            return
        lead = await db.get_lead(lead_id)
        _is_admin = agent.get('role') in ('owner', 'admin')
        if not lead or (lead['agent_id'] != agent['agent_id'] and not _is_admin):
            lang = agent.get('lang', 'en')
            await query.edit_message_text(i18n.t(lang, "lead_not_found_access"))
            return
        context.user_data['convert_lead_id'] = lead_id
        lang = agent.get('lang', 'en')
        if lang == "hi":
            keyboard = [
                [InlineKeyboardButton("📞 संपर्क किया", callback_data="stg_contacted")],
                [InlineKeyboardButton("📊 पिच किया", callback_data="stg_pitched")],
                [InlineKeyboardButton("📄 प्रस्ताव भेजा", callback_data="stg_proposal_sent")],
                [InlineKeyboardButton("🤝 बातचीत", callback_data="stg_negotiation")],
                [InlineKeyboardButton("✅ क्लोज़्ड WON", callback_data="stg_closed_won")],
                [InlineKeyboardButton("❌ क्लोज़्ड LOST", callback_data="stg_closed_lost")],
            ]
            stage_text = (f"🔄 <b>लीड स्टेज बदलें: {h(lead['name'])}</b>\n"
                          f"वर्तमान: {_stage_emoji(lead['stage'])} {h(lead['stage'])}\n\n"
                          f"नया स्टेज चुनें:")
        else:
            keyboard = [
                [InlineKeyboardButton("📞 Contacted", callback_data="stg_contacted")],
                [InlineKeyboardButton("📊 Pitched", callback_data="stg_pitched")],
                [InlineKeyboardButton("📄 Proposal Sent", callback_data="stg_proposal_sent")],
                [InlineKeyboardButton("🤝 Negotiation", callback_data="stg_negotiation")],
                [InlineKeyboardButton("✅ CLOSED WON", callback_data="stg_closed_won")],
                [InlineKeyboardButton("❌ CLOSED LOST", callback_data="stg_closed_lost")],
            ]
            stage_text = (f"🔄 <b>Move Lead: {h(lead['name'])}</b>\n"
                          f"Current: {_stage_emoji(lead['stage'])} {h(lead['stage'])}\n\n"
                          f"Select new stage:")
        await query.edit_message_text(
            stage_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("greetpick_"):
        await query.answer()
        lead_id = int(data.replace("greetpick_", ""))
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        lead = await db.get_lead(lead_id)
        _is_admin = agent.get('role') in ('owner', 'admin')
        if not lead or (lead['agent_id'] != agent['agent_id'] and not _is_admin):
            _lang = agent.get('lang', 'en')
            await query.edit_message_text(i18n.t(_lang, "lead_not_found"))
            return
        lang = agent.get('lang', 'en')
        if lang == 'hi':
            keyboard = [
                [InlineKeyboardButton("🎂 जन्मदिन", callback_data=f"greet_bday_{lead_id}")],
                [InlineKeyboardButton("💍 वर्षगांठ", callback_data=f"greet_anniv_{lead_id}")],
                [InlineKeyboardButton("🙏 धन्यवाद", callback_data=f"greet_thanks_{lead_id}")],
                [InlineKeyboardButton("🎉 त्योहार", callback_data=f"greet_festival_{lead_id}")],
            ]
            greet_title = "💌 <b>शुभकामना का प्रकार चुनें:</b>"
        else:
            keyboard = [
                [InlineKeyboardButton("🎂 Birthday", callback_data=f"greet_bday_{lead_id}")],
                [InlineKeyboardButton("💍 Anniversary", callback_data=f"greet_anniv_{lead_id}")],
                [InlineKeyboardButton("🙏 Thank You", callback_data=f"greet_thanks_{lead_id}")],
                [InlineKeyboardButton("🎉 Festival", callback_data=f"greet_festival_{lead_id}")],
            ]
            greet_title = "💌 <b>Select greeting type:</b>"
        await query.edit_message_text(
            greet_title,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data == "calc_menu":
        # Quick jump to calc — just show the command hint
        await query.answer()
        _agent = await db.get_agent(str(query.from_user.id))
        _lang = _agent.get('lang', 'en') if _agent else 'en'
        calc_txt = "📊 कैलकुलेटर खोलने के लिए /calc टाइप करें।" if _lang == 'hi' else "📊 Use /calc to open the calculator menu."
        await query.edit_message_text(calc_txt)

    elif data.startswith("editbtn_"):
        # Edit Lead button from leadview_ detail
        await query.answer()
        lead_id = int(data.replace("editbtn_", ""))
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        lead = await db.get_lead(lead_id)
        _is_admin = agent.get('role') in ('owner', 'admin')
        if not lead or (lead['agent_id'] != agent['agent_id'] and not _is_admin):
            _lang = agent.get('lang', 'en')
            await query.edit_message_text(i18n.t(_lang, "lead_not_found"))
            return
        _lang = agent.get('lang', 'en')
        # Store lead_id so the editlead conversation can pick it up
        context.user_data['editlead_id'] = lead_id
        context.user_data['lang'] = _lang
        if _lang == 'hi':
            keyboard = [
                [InlineKeyboardButton("📝 नाम", callback_data=f"editlead_name")],
                [InlineKeyboardButton("📱 फ़ोन", callback_data=f"editlead_phone")],
                [InlineKeyboardButton("📧 ईमेल", callback_data=f"editlead_email")],
                [InlineKeyboardButton("🎂 जन्मतिथि", callback_data=f"editlead_dob")],
                [InlineKeyboardButton("💍 वर्षगांठ", callback_data=f"editlead_anniversary")],
                [InlineKeyboardButton("🏙️ शहर", callback_data=f"editlead_city")],
                [InlineKeyboardButton("📝 नोट्स", callback_data=f"editlead_notes")],
                [InlineKeyboardButton("🏥 ज़रूरत", callback_data=f"editlead_need_type")],
            ]
            await query.edit_message_text(
                f"✏️ <b>लीड #{lead_id} संपादित करें: {h(lead['name'])}</b>\n\n"
                f"📱 फ़ोन: {h(lead.get('phone', 'N/A'))}\n"
                f"📧 ईमेल: {h(lead.get('email', 'N/A'))}\n"
                f"🎂 जन्मतिथि: {h(lead.get('dob', 'N/A'))}\n"
                f"💍 वर्षगांठ: {h(lead.get('anniversary', 'N/A'))}\n"
                f"🏙️ शहर: {h(lead.get('city', 'N/A'))}\n"
                f"🏥 ज़रूरत: {h(lead.get('need_type', 'N/A'))}\n"
                f"📝 नोट्स: {h(lead.get('notes', 'N/A'))}\n\n"
                f"कौन सा फ़ील्ड बदलना है?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML)
        else:
            keyboard = [
                [InlineKeyboardButton("📝 Name", callback_data=f"editlead_name")],
                [InlineKeyboardButton("📱 Phone", callback_data=f"editlead_phone")],
                [InlineKeyboardButton("📧 Email", callback_data=f"editlead_email")],
                [InlineKeyboardButton("🎂 DOB", callback_data=f"editlead_dob")],
                [InlineKeyboardButton("💍 Anniversary", callback_data=f"editlead_anniversary")],
                [InlineKeyboardButton("🏙️ City", callback_data=f"editlead_city")],
                [InlineKeyboardButton("📝 Notes", callback_data=f"editlead_notes")],
                [InlineKeyboardButton("🏥 Need Type", callback_data=f"editlead_need_type")],
            ]
            await query.edit_message_text(
                f"✏️ <b>Edit Lead #{lead_id}: {h(lead['name'])}</b>\n\n"
                f"📱 Phone: {h(lead.get('phone', 'N/A'))}\n"
                f"📧 Email: {h(lead.get('email', 'N/A'))}\n"
                f"🎂 DOB: {h(lead.get('dob', 'N/A'))}\n"
                f"💍 Anniversary: {h(lead.get('anniversary', 'N/A'))}\n"
                f"🏙️ City: {h(lead.get('city', 'N/A'))}\n"
                f"🏥 Need: {h(lead.get('need_type', 'N/A'))}\n"
                f"📝 Notes: {h(lead.get('notes', 'N/A'))}\n\n"
                f"Which field do you want to change?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML)

    elif data.startswith("calc_"):
        # Legacy calculator inline button — redirect to interactive flow
        # (The new calc ConversationHandler handles csel_* patterns)
        pass

    elif data.startswith("wa_share_"):
        # WhatsApp share from calculator result (outside conversation)
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            _lang = context.user_data.get('lang', 'en')
            await query.edit_message_text(i18n.t(_lang, "register_first"))
            return
        calc_type = data.replace("wa_share_", "")
        calc_text = context.user_data.get(f"last_calc_{calc_type}", "")
        if not calc_text:
            lang = agent.get('lang', 'en')
            await query.edit_message_text(i18n.t(lang, "no_result_to_share"))
            return
        import re as re_mod
        clean_text = re_mod.sub(r'<[^>]+>', '', calc_text)
        _company2 = "Sarathi-AI"
        _brand_web2 = ''
        _brand_email2 = ''
        try:
            _t2 = await db.get_tenant(agent['tenant_id'])
            if _t2 and _t2.get('firm_name'):
                _company2 = _t2['firm_name']
            if _t2:
                _brand_web2 = _t2.get('brand_website', '') or ''
                _brand_email2 = _t2.get('brand_email', '') or ''
        except Exception:
            pass
        _lang = agent.get('lang', 'en')
        _agent_name2 = agent.get('name', 'Your Advisor')

        _footer2 = f"Prepared by: {_agent_name2}"
        if _company2 and _company2 != _agent_name2:
            _footer2 += f"\n{_company2} 🛡️"
        else:
            _footer2 += " 🛡️"

        _cp2 = []
        if _brand_web2:
            _cp2.append(f"🌐 {_brand_web2}")
        if _brand_email2:
            _cp2.append(f"📧 {_brand_email2}")
        _bl2 = "\n".join(_cp2) if _cp2 else "🌐 Powered by Sarathi-AI.com"

        _report_url2 = context.user_data.get('last_report_url', '')
        _rpt_line2 = f"\n\n📎 View detailed report:\n{_report_url2}" if _report_url2 else ''

        _share_msg2 = (
            f"📊 {'वित्तीय विश्लेषण' if _lang == 'hi' else 'Financial Analysis'}\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"{clean_text}\n\n"
            f"{_footer2}\n\n"
            f"{_bl2}"
            f"{_rpt_line2}"
        )
        import urllib.parse as _urlparse2
        _direct_link2 = f"https://wa.me/?text={_urlparse2.quote(_share_msg2)}"

        context.user_data["wa_share_pending"] = {
            "calc_type": calc_type, "text": clean_text,
            "agent_name": _agent_name2,
            "company": _company2,
            "report_url": _report_url2,
            "website": _brand_web2,
            "email": _brand_email2,
        }

        if _lang == 'hi':
            wa_prompt = (
                "📱 <b>WhatsApp पर शेयर करें</b>\n\n"
                f"👉 <a href=\"{h(_direct_link2)}\">सीधे WhatsApp खोलें</a> — खुद कॉन्टैक्ट चुनें\n\n"
                "━━ या ━━\n\n"
                "क्लाइंट का फ़ोन नंबर टाइप करें (10 अंक):\n"
                "<i>उदाहरण: 9876543210</i>"
            )
        else:
            wa_prompt = (
                "📱 <b>Share on WhatsApp</b>\n\n"
                f"👉 <a href=\"{h(_direct_link2)}\">Open WhatsApp directly</a> — pick a contact yourself\n\n"
                "━━ OR ━━\n\n"
                "Type the client's phone number (10 digits):\n"
                "<i>Example: 9876543210</i>"
            )
        await query.edit_message_text(
            wa_prompt,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True)

    elif data == "show_calc_menu":
        pass  # Handled by ConversationHandler now

    elif data.startswith("wacalc_"):
        # wacalc_<type>_<lead_id>
        _agent2 = await db.get_agent(str(query.from_user.id))
        _lang2 = _agent2.get('lang', 'en') if _agent2 else 'en'
        gen_txt = "रिपोर्ट तैयार हो रही है..." if _lang2 == 'hi' else "Generating report..."
        await query.answer(gen_txt)
        parts = data.split("_")
        calc_type = parts[1]
        lead_id = int(parts[2])
        agent = _agent2
        if not agent:
            return
        lead = await db.get_lead(lead_id)
        if not lead or lead['agent_id'] != agent['agent_id']:
            await query.edit_message_text(i18n.t(_lang2, "lead_not_found"))
            return
        await _run_and_send_calc(query, agent, lead, calc_type)

    elif data.startswith("lang_"):
        await query.answer()
        new_lang = data.replace("lang_", "")
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        await db.update_agent_lang(agent['agent_id'], new_lang)
        context.user_data['lang'] = new_lang
        # Invalidate cached agent so next access picks up new lang
        cached = context.user_data.get('_agent')
        if cached:
            cached['lang'] = new_lang
            context.user_data['_agent'] = cached
        role = agent.get('role', 'agent')
        plan = agent.get('_plan', context.user_data.get('_agent', {}).get('_plan', 'trial'))
        menu = _main_menu_keyboard(new_lang, role, plan, agent)
        if new_lang == "hi":
            await query.edit_message_text(
                i18n.t(new_lang, "lang_changed_hi"),
                parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(
                i18n.t(new_lang, "lang_changed_en"),
                parse_mode=ParseMode.HTML)
        # Update the persistent menu to match new language
        try:
            await query.message.reply_text(
                "✅", reply_markup=menu)
        except Exception:
            pass

    elif data.startswith("settings_"):
        await query.answer()
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        if data == "settings_editprofile":
            _lang = agent.get('lang', 'en')
            if _lang == 'hi':
                await query.edit_message_text(
                    "✏️ प्रोफ़ाइल संपादित करने के लिए यह कमांड दबाएं:\n\n"
                    "<code>/editprofile</code>\n\n"
                    "आप अपना नाम, फ़ोन या ईमेल अपडेट कर सकते हैं।",
                    parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text(
                    "✏️ To edit your profile, use the command:\n\n"
                    "<code>/editprofile</code>\n\n"
                    "You can update your name, phone, or email.",
                    parse_mode=ParseMode.HTML)
        elif data == "settings_lang":
            _lang = agent.get('lang', 'en')
            sel_lang_txt = "🌐 अपनी पसंदीदा भाषा चुनें:" if _lang == 'hi' else "🌐 Select your preferred language:"
            keyboard = [
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
                [InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="lang_hi")],
            ]
            await query.edit_message_text(
                sel_lang_txt,
                reply_markup=InlineKeyboardMarkup(keyboard))
        elif data == "settings_team":
            _lang = agent.get('lang', 'en')
            if agent.get('role') == 'owner':
                # Check plan limits before generating invite
                cap = await db.can_add_agent(agent['tenant_id'])
                agents = await db.get_agents_by_tenant(agent['tenant_id'])
                team_lines = "\n".join(
                    f"  {'👑' if a['role']=='owner' else '👤'} {h(a['name'])} ({a['role']})"
                    for a in agents)

                if not cap['allowed']:
                    plan_names = {'individual': 'Solo (₹199/mo)',
                                  'team': 'Team (₹799/mo)',
                                  'enterprise': 'Enterprise (₹1,999/mo)',
                                  'trial': 'Trial'}
                    plan_label = plan_names.get(cap['plan'], cap['plan'])
                    if _lang == 'hi':
                        await query.edit_message_text(
                            f"👥 <b>टीम प्रबंधन</b>\n\n"
                            f"<b>वर्तमान टीम ({cap['current']}/{cap['max']}):</b>\n{team_lines}\n\n"
                            f"⚠️ <b>टीम भरी हुई है</b> — आपका <b>{plan_label}</b> प्लान "
                            f"अधिकतम <b>{cap['max']}</b> सलाहकार की अनुमति देता है।\n\n"
                            f"💎 और सदस्य जोड़ने के लिए अपना प्लान अपग्रेड करें।",
                            parse_mode=ParseMode.HTML)
                    else:
                        await query.edit_message_text(
                            f"👥 <b>Team Management</b>\n\n"
                            f"<b>Current Team ({cap['current']}/{cap['max']}):</b>\n{team_lines}\n\n"
                            f"⚠️ <b>Team full</b> — Your <b>{plan_label}</b> plan "
                            f"allows max <b>{cap['max']}</b> advisor(s).\n\n"
                            f"💎 Upgrade your plan to add more team members.\n"
                            f"Visit sarathi-ai.com → Pricing to upgrade.",
                            parse_mode=ParseMode.HTML)
                else:
                    # Generate invite code
                    code = await db.create_invite_code(
                        agent['tenant_id'], agent['agent_id'])
                    if _lang == 'hi':
                        await query.edit_message_text(
                            f"👥 <b>टीम प्रबंधन</b>\n\n"
                            f"<b>वर्तमान टीम ({cap['current']}/{cap['max']}):</b>\n{team_lines}\n\n"
                            f"<b>आमंत्रण कोड:</b> <code>{code}</code>\n"
                            f"<i>यह कोड एजेंट को अपनी फर्म में जोड़ने के लिए शेयर करें।\n"
                            f"7 दिन तक, 5 बार उपयोग योग्य।</i>\n\n"
                            f"नया एजेंट @SarathiBizBot (Sarathi-AI.com) खोले → Start → 'I have an Invite Code'",
                            parse_mode=ParseMode.HTML)
                    else:
                        await query.edit_message_text(
                            f"👥 <b>Team Management</b>\n\n"
                            f"<b>Current Team ({cap['current']}/{cap['max']}):</b>\n{team_lines}\n\n"
                            f"<b>Invite Code:</b> <code>{code}</code>\n"
                            f"<i>Share this code with agents to join your firm.\n"
                            f"Valid for 7 days, up to 5 uses.</i>\n\n"
                            f"New agent opens @SarathiBizBot (Sarathi-AI.com) → Start → 'I have an Invite Code'",
                            parse_mode=ParseMode.HTML)
            else:
                owner_only = "ℹ️ केवल फर्म मालिक ही टीम प्रबंधित कर सकता है।" if _lang == 'hi' else "ℹ️ Only the firm owner can manage the team."
                await query.edit_message_text(owner_only)
        elif data == "settings_testmode":
            lang = agent.get('lang', 'en')
            if agent.get('role') not in ('owner', 'admin'):
                await query.edit_message_text(
                    i18n.t(lang, "owner_only_feature"))
            else:
                await query.edit_message_text(
                    i18n.t(lang, "admin_test_mode_info"),
                    parse_mode=ParseMode.HTML)
        elif data == "settings_ai_usage":
            lang = agent.get('lang', 'en')
            quota = await db.check_ai_quota(agent['agent_id'])
            usage = await db.get_tenant_ai_usage_summary(
                agent.get('tenant_id', 0), days=30)
            plan_label = quota['plan'].title()
            lines = [f"📊 <b>AI Usage</b> — {plan_label} Plan\n"]
            lines.append(f"Today: <b>{quota['used']}/{quota['limit']}</b> calls")
            lines.append(f"30-day total: <b>{usage['total_calls']}</b> calls")
            lines.append(f"Est. cost: <b>${usage['total_cost_usd']:.4f}</b>\n")
            if usage.get('by_feature'):
                lines.append("<b>By Feature:</b>")
                for f in usage['by_feature'][:6]:
                    lines.append(f"  • {f['feature']}: {f['calls']} calls")
            await query.edit_message_text(
                "\n".join(lines), parse_mode=ParseMode.HTML)
        elif data == "settings_help":
            lang = agent.get('lang', 'en')
            await query.edit_message_text(
                i18n.t(lang, "help_text"),
                parse_mode=ParseMode.HTML)
        elif data == "settings_weblogin":
            # Trigger the weblogin flow — inject update.message so cmd_weblogin works
            await query.answer()
            update.message = query.message
            await cmd_weblogin(update, context)
        elif data == "settings_logout":
            # Trigger logout flow via settings button
            await query.answer()
            object.__setattr__(update, 'message', query.message)
            await cmd_logout(update, context)

    elif data.startswith("greet_"):
        await greet_callback(update, context)

    elif data.startswith("csel_") or data.startswith("cparam_") or data in ("calc_retry", "calc_cancel"):
        # Stale calculator button from before server restart or after conversation timeout.
        # Restart the calculator flow so the user isn't stranded.
        await query.answer()
        agent = await db.get_agent(str(query.from_user.id))
        lang = agent.get('lang', 'en') if agent else 'en'
        hint = ("⏳ सत्र समाप्त हो गया। कैलकुलेटर पुनः शुरू कर रहे हैं..."
                if lang == 'hi' else "⏳ Session expired. Restarting calculator...")
        try:
            await query.edit_message_text(hint)
        except Exception:
            pass
        # Trigger calculator menu fresh
        object.__setattr__(update, 'message', query.message)
        await cmd_calc(update, context)


# =============================================================================
#  INLINE MENU CALLBACK (handles ☰ Menu inline button taps)
# =============================================================================

async def _menu_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline menu button taps from _full_menu_inline keyboard."""
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. "menu_leads", "menu_calc"

    # Map callback_data → command function
    _menu_cmd_map = {
        "menu_leads": cmd_leads,
        "menu_followup": cmd_followup,
        "menu_mytasks": cmd_mytasks,
        # menu_calc handled by calc_conv entry point (cmd_calc_inline)
        "menu_renewals": cmd_renewals,
        "menu_dashboard": cmd_dashboard,
        "menu_settings": cmd_settings,
        "menu_ai": cmd_ai,
        "menu_team": cmd_team,
        "menu_plans": cmd_plans,
        "menu_partner": cmd_partner,
        "menu_lang": cmd_lang,
        "menu_help": cmd_help,
        "menu_admin": cmd_admin_controls,
    }

    handler = _menu_cmd_map.get(data)
    if not handler:
        return

    # Remove the inline keyboard to keep chat clean
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # For callback queries, update.message is None (Update uses frozen __slots__).
    # Command functions rely on update.message.reply_text(), so we inject
    # query.message via object.__setattr__ to bypass the frozen restriction.
    # update.effective_user already returns the real user for callback queries,
    # so @registered / _get_agent auth works correctly.
    object.__setattr__(update, 'message', query.message)

    return await handler(update, context)


# =============================================================================
#  NUDGE RESPONSE CALLBACKS (advisor taps ✅ Done / ⏰ Remind Later)
# =============================================================================

async def _nudge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle advisor response to a nudge inline button."""
    query = update.callback_query
    await query.answer()
    data = query.data  # nudge_act_123 or nudge_snooze_123

    parts = data.split("_")
    if len(parts) < 3:
        return
    action = parts[1]  # 'act' or 'snooze'
    try:
        nudge_id = int(parts[2])
    except (ValueError, IndexError):
        return

    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)
    if not agent:
        return

    lang = agent.get('lang', 'en')

    if action == 'act':
        await db.update_nudge_status(nudge_id, 'acted')
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        msg = "✅ Маркед as done!" if lang == 'en' else "✅ हो गया!"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=msg)
    elif action == 'snooze':
        await db.update_nudge_status(nudge_id, 'sent')  # back to sent = will remind
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        msg = "⏰ Will remind you later." if lang == 'en' else "⏰ बाद में याद दिलायेंगे।"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=msg)


# =============================================================================
#  FOLLOW-UP DONE / SNOOZE CALLBACKS (fudone_*, fusnz_*)
# =============================================================================

async def _followup_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Done ✅ / Snooze 🕐 buttons on follow-up reminders."""
    query = update.callback_query
    await query.answer()
    data = query.data  # fudone_123 or fusnz_123

    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)
    if not agent:
        return

    hi = agent.get('lang', 'en') == 'hi'

    if data.startswith('fudone_'):
        try:
            iid = int(data.replace('fudone_', ''))
        except ValueError:
            return

        success = await db.mark_followup_done(iid)
        if not success:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Follow-up not found." if not hi else "❌ Follow-up नहीं मिला।")
            return

        # Remove buttons
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        # Ask for notes — store pending note state
        context.user_data['pending_followup_note'] = {
            'interaction_id': iid,
            'asked_at': datetime.now().isoformat()
        }

        if hi:
            msg = ("✅ Follow-up done!\n\n"
                   "📋 *कैसा रहा? Notes भेजें* — वॉइस नोट या टाइप करें:\n"
                   "_(e.g. \"Client interested, next step proposal send karna hai\")_")
        else:
            msg = ("✅ Follow-up done!\n\n"
                   "📋 *How did it go? Send your notes* — voice or text:\n"
                   "_(e.g. \"Client interested, need to send proposal next\")_")

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=msg,
            parse_mode='Markdown')

    elif data.startswith('fusnz_'):
        try:
            iid = int(data.replace('fusnz_', ''))
        except ValueError:
            return

        success = await db.mark_followup_snoozed(iid)
        if not success:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Follow-up not found." if not hi else "❌ Follow-up नहीं मिला।")
            return

        # Remove buttons
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        if hi:
            msg = "🕐 1 घंटे बाद फिर याद दिलाएंगे।"
        else:
            msg = "🕐 Snoozed! Will remind you again in 1 hour."

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=msg)


# =============================================================================
#  PROACTIVE ASSISTANT CALLBACKS (pa_* buttons)
# =============================================================================

async def _proactive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle proactive assistant button taps."""
    query = update.callback_query
    await query.answer()
    data = query.data

    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)
    if not agent:
        return
    hi = agent.get('lang', 'en') == 'hi'

    # ── Dismiss buttons ──
    if data in ('pa_dismiss_fu', 'pa_dismiss_stale', 'pa_dismiss_suggest'):
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="👍" if not hi else "👍")
        return

    if data.startswith('pa_dismiss_celeb_'):
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ 9 AM पर भेजेंगे!" if hi else "✅ Will send at 9 AM!")
        return

    # ── View follow-ups ──
    if data == 'pa_view_followups':
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        followups = await db.get_pending_followups(agent['agent_id'])
        if not followups:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="✅ कोई pending follow-up नहीं!" if hi else "✅ No pending follow-ups!")
            return
        lines = [f"📋 <b>{'सभी Follow-ups' if hi else 'All Follow-ups'}</b>\n"]
        for i, fu in enumerate(followups[:15], 1):
            overdue_tag = ""
            if fu.get('follow_up_date'):
                try:
                    fu_dt = datetime.fromisoformat(fu['follow_up_date'])
                    if fu_dt.date() < datetime.now().date():
                        overdue_tag = " 🔴"
                except (ValueError, TypeError):
                    pass
            lines.append(
                f"{i}. <b>{fu.get('lead_name', '?')}</b>{overdue_tag}\n"
                f"   📞 {fu.get('lead_phone', 'N/A')} | {fu.get('type', '?')}\n"
                f"   📝 {fu.get('summary', '—')[:50]}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="\n".join(lines),
            parse_mode=ParseMode.HTML)
        return

    # ── View stale leads ──
    if data == 'pa_view_stale':
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        stale = await db.get_stale_leads_for_agent(agent['agent_id'], days=14)
        if not stale:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="✅ कोई stale leads नहीं!" if hi else "✅ No stale leads!")
            return
        lines = [f"⚠️ <b>{'निष्क्रिय लीड्स' if hi else 'Stale Leads'}</b>\n"]
        for i, lead in enumerate(stale[:10], 1):
            days_ago = (datetime.now() - datetime.fromisoformat(lead['updated_at'])).days
            lines.append(
                f"{i}. <b>{lead['name']}</b> — {lead.get('stage', '?')}\n"
                f"   📞 {lead.get('phone', 'N/A')} | {days_ago} {'दिन पहले' if hi else 'days ago'}\n"
                f"   /lead_{lead['lead_id']}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="\n".join(lines),
            parse_mode=ParseMode.HTML)
        return

    # ── Call a lead ──
    if data.startswith('pa_call_'):
        try:
            lead_id = int(data.split('_')[-1])
        except (ValueError, IndexError):
            return
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        lead = await db.get_lead(lead_id)
        if lead:
            phone = lead.get('phone', '')
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"📞 <b>{lead['name']}</b>\n"
                     f"{'फ़ोन' if hi else 'Phone'}: {phone}\n\n"
                     f"{'Call करके voice note भेजो meeting log करने के लिए' if hi else 'After the call, send a voice note to log it'}\n"
                     f"/lead_{lead_id}",
                parse_mode=ParseMode.HTML)
        return

    # ── Snooze follow-ups ──
    if data == 'pa_snooze_fu':
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⏰ 1 घंटे बाद याद दिलायेंगे!" if hi else "⏰ Will remind in 1 hour!")
        return

    # ── Reschedule all missed to tomorrow ──
    if data == 'pa_reschedule_tomorrow':
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        # Get today's pending + overdue, reschedule to tomorrow (update in-place)
        followups = await db.get_pending_followups(agent['agent_id'])
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        count = 0
        for fu in followups:
            try:
                iid = fu.get('interaction_id')
                if iid:
                    await db.update_followup(
                        interaction_id=iid,
                        follow_up_date=tomorrow,
                        summary=f"Rescheduled from {fu.get('follow_up_date', 'today')}")
                    count += 1
            except Exception:
                pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"📅 {count} follow-ups {'कल के लिए reschedule किए!' if hi else 'rescheduled for tomorrow!'}")
        return

    # ── Send birthday greeting now ──
    if data.startswith('pa_greet_bday_'):
        try:
            lead_id = int(data.split('_')[-1])
        except (ValueError, IndexError):
            return
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        lead = await db.get_lead(lead_id)
        if lead:
            phone = lead.get('whatsapp') or lead.get('phone')
            if phone:
                _cf2 = ''
                try:
                    _cf2 = await db.build_compliance_credentials(agent['agent_id'])
                except Exception:
                    pass
                result = await wa.send_birthday_greeting(
                    to=phone,
                    client_name=lead['name'],
                    agent_name=agent.get('name', 'Advisor'),
                    company=agent.get('firm_name', 'Sarathi-AI'),
                    compliance_footer=_cf2)
                if result.get('success'):
                    await db.log_greeting(lead_id, agent['agent_id'], 'birthday', 'whatsapp')
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"🎂 {'Birthday greeting भेज दी!' if hi else 'Birthday greeting sent!'}")
                elif result.get('wa_link'):
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                        "📤 WhatsApp पर भेजो" if hi else "📤 Send via WhatsApp",
                        url=result['wa_link'])]])
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"🎂 {'Click करके भेजो:' if hi else 'Click to send:'}",
                        reply_markup=kb)
        return

    # ── Send anniversary greeting now ──
    if data.startswith('pa_greet_anniv_'):
        try:
            lead_id = int(data.split('_')[-1])
        except (ValueError, IndexError):
            return
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        lead = await db.get_lead(lead_id)
        if lead:
            phone = lead.get('whatsapp') or lead.get('phone')
            if phone:
                _cf3 = ''
                try:
                    _cf3 = await db.build_compliance_credentials(agent['agent_id'])
                except Exception:
                    pass
                result = await wa.send_anniversary_greeting(
                    to=phone,
                    client_name=lead['name'],
                    agent_name=agent.get('name', 'Advisor'),
                    company=agent.get('firm_name', 'Sarathi-AI'),
                    compliance_footer=_cf3)
                if result.get('success'):
                    await db.log_greeting(lead_id, agent['agent_id'], 'anniversary', 'whatsapp')
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"💍 {'Anniversary greeting भेज दी!' if hi else 'Anniversary greeting sent!'}")
                elif result.get('wa_link'):
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                        "📤 WhatsApp पर भेजो" if hi else "📤 Send via WhatsApp",
                        url=result['wa_link'])]])
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"💍 {'Click करके भेजो:' if hi else 'Click to send:'}",
                        reply_markup=kb)
        return


# =============================================================================
#  BUTTON MENU HANDLER (maps button text to commands)
# =============================================================================

async def button_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Map persistent keyboard button taps to actual command functions."""
    # Guard: CRM buttons should not work on master bot
    if context.bot_data.get('_is_master'):
        await update.message.reply_text(
            "ℹ️ CRM features are available on your own bot.\n"
            "Use /start to see how to connect or access your bot.",
            reply_markup=ReplyKeyboardRemove(),
        )
        raise ApplicationHandlerStop

    text = update.message.text.strip()

    # Normalise by stripping Unicode variation selectors (U+FE0E / U+FE0F)
    _strip_vs = str.maketrans("", "", "\ufe0e\ufe0f")
    norm = text.translate(_strip_vs)

    # ── ☰ Menu button: show expanded inline menu ──
    if norm in ("☰ Menu", "☰ मेनू"):
        agent = context.user_data.get('_agent') or await _get_agent(update)
        lang = agent.get('lang', 'en') if agent else 'en'
        role = agent.get('role', 'agent') if agent else 'agent'
        plan = agent.get('_plan', agent.get('plan', 'trial')) if agent else 'trial'
        title = "📱 *मेनू*" if lang == "hi" else "📱 *Menu*"
        await update.message.reply_text(
            title,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=_full_menu_inline(lang, role, plan),
        )
        raise ApplicationHandlerStop

    # Map button labels to commands (English + Hindi)
    # NOTE: ➕ Add Lead, 📞 Follow-up, 🧮 Calculator are handled by their own
    # ConversationHandler entry points (higher priority), so not listed here.
    menu_map = {
        "📊 Pipeline": cmd_pipeline,
        "📊 पाइपलाइन": cmd_pipeline,
        "📋 Leads": cmd_leads,
        "📋 लीड्स": cmd_leads,
        "📋 My Leads": cmd_leads,
        "📋 मेरी लीड्स": cmd_leads,
        "🔄 Renewals": cmd_renewals,
        "🔄 रिन्यूअल": cmd_renewals,
        "📈 Dashboard": cmd_dashboard,
        "📈 डैशबोर्ड": cmd_dashboard,
        "🤖 AI Tools": cmd_ai,
        "🤖 AI टूल्स": cmd_ai,
        "⚙️ Settings": cmd_settings,
        "⚙️ सेटिंग्स": cmd_settings,
        "👥 Team": cmd_team,
        "👥 टीम": cmd_team,
        "🌐 Language": cmd_lang,
        "🌐 भाषा बदलें": cmd_lang,
        "🤝 Partner & Earn": cmd_partner,
        "🤝 पार्टनर और कमाएं": cmd_partner,
    }

    # Try exact match first, then normalised match
    handler = menu_map.get(text)
    if not handler:
        norm_map = {k.translate(_strip_vs): v for k, v in menu_map.items()}
        handler = norm_map.get(norm)

    if handler:
        logger.info("button_menu_handler dispatching '%s' → %s", text, handler.__name__)
        await handler(update, context)
        raise ApplicationHandlerStop


@registered
async def cmd_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send affiliate/partner portal link."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return
    lang = agent.get('lang', 'en')
    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
    partner_url = f"{server_url}/partner"
    if lang == "hi":
        text = (
            "🤝 <b>पार्टनर और कमाएं</b>\n\n"
            "Sarathi AI को रेफर करें और हर सफल रेफरल पर कमीशन कमाएं!\n\n"
            "👇 नीचे बटन पर क्लिक करके एफिलिएट पोर्टल खोलें"
        )
    else:
        text = (
            "🤝 <b>Partner & Earn</b>\n\n"
            "Refer Sarathi AI and earn commission on every successful referral!\n\n"
            "👇 Click the button below to open the Affiliate Portal"
        )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Open Affiliate Portal" if lang != "hi" else "🌐 एफिलिएट पोर्टल खोलें",
                              url=partner_url)]
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@registered
@owner_only
async def cmd_admin_controls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enterprise-only admin controls panel."""
    agent = context.user_data.get('_agent', {})
    lang = agent.get('lang', 'en')
    plan = agent.get('_plan', 'trial')

    if plan != 'enterprise':
        if lang == 'hi':
            await update.message.reply_text(
                "🔒 <b>एडमिन कंट्रोल</b> केवल Enterprise प्लान में उपलब्ध है।\n\n"
                "अपग्रेड करने के लिए /plans टाइप करें।",
                parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(
                "🔒 <b>Admin Controls</b> are available only on the Enterprise plan.\n\n"
                "Type /plans to upgrade.",
                parse_mode=ParseMode.HTML)
        return

    if lang == 'hi':
        text = (
            "🛡️ <b>एडमिन कंट्रोल</b>\n\n"
            "• 🎨 कस्टम ब्रांडिंग — PDF और रिपोर्ट में अपना लोगो\n"
            "• 🔑 API एक्सेस — अपने सिस्टम से इंटीग्रेट करें\n"
            "• 👥 एडवांस्ड टीम — 25 एजेंट तक\n"
            "• 📊 एडवांस्ड एनालिटिक्स\n\n"
            "वेब डैशबोर्ड से कॉन्फ़िगर करें: /weblogin"
        )
    else:
        text = (
            "🛡️ <b>Admin Controls</b>\n\n"
            "• 🎨 Custom Branding — your logo on PDFs & reports\n"
            "• 🔑 API Access — integrate with your systems\n"
            "• 👥 Advanced Team — up to 25 agents\n"
            "• 📊 Advanced Analytics\n\n"
            "Configure via web dashboard: /weblogin"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@registered
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return
    lang = agent.get('lang', 'en')
    context.user_data['lang'] = lang
    role = agent.get('role', 'agent')
    plan = agent.get('_plan', 'trial')
    await update.message.reply_text(
        i18n.t(lang, "settings_title"),
        reply_markup=_settings_keyboard(lang, role, plan),
        parse_mode=ParseMode.HTML)


# =============================================================================
#  /microsite — Show advisor's public landing page (Feature 4)
# =============================================================================

@registered
async def cmd_microsite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show advisor's public microsite link, view count, and a deep-link to settings."""
    import os as _os_micro
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return
    lang = agent.get('lang', 'en')
    hi = lang == 'hi'
    tenant = await db.get_tenant(agent.get('tenant_id'))
    if not tenant:
        await update.message.reply_text(
            "तुम्हारा firm नहीं मिला." if hi else "Could not find your firm profile.")
        return
    base = (_os_micro.getenv('SERVER_URL') or 'https://sarathi-ai.com').rstrip('/')
    slug = (tenant.get('microsite_slug') or '').strip()
    published = bool(tenant.get('microsite_published'))
    views = int(tenant.get('microsite_views') or 0)
    settings_url = f"{base}/dashboard#microsite"

    if not slug:
        msg = (
            "🌐 <b>आपका Microsite</b>\n\n"
            "अभी setup नहीं हुआ है। Dashboard में जाकर अपना URL slug और details भरें।\n\n"
            f"🔗 <a href='{settings_url}'>Open Microsite Settings</a>"
        ) if hi else (
            "🌐 <b>Your Microsite</b>\n\n"
            "Not set up yet. Open the dashboard to choose your URL and add your details.\n\n"
            f"🔗 <a href='{settings_url}'>Open Microsite Settings</a>"
        )
    else:
        public_url = f"{base}/m/{slug}"
        status = ("✅ <b>LIVE</b>" if published else "📝 <b>DRAFT</b> (not yet published)")
        if hi:
            msg = (
                f"🌐 <b>आपका Microsite</b>\n\n"
                f"Status: {status}\n"
                f"🔗 URL: <a href='{public_url}'>{public_url}</a>\n"
                f"👁 Total views: <b>{views}</b>\n\n"
                f"⚙️ <a href='{settings_url}'>Edit settings on dashboard</a>"
            )
        else:
            msg = (
                f"🌐 <b>Your Microsite</b>\n\n"
                f"Status: {status}\n"
                f"🔗 URL: <a href='{public_url}'>{public_url}</a>\n"
                f"👁 Total views: <b>{views}</b>\n\n"
                f"⚙️ <a href='{settings_url}'>Edit settings on dashboard</a>"
            )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# =============================================================================
#  /compliance — SEBI / IRDAI / AMFI Regulatory Details
# =============================================================================

@registered
async def cmd_compliance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show or update regulatory compliance details (ARN, EUIN, SEBI RIA, etc.)."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return
    lang = agent.get('lang', 'en')
    hi = lang == 'hi'
    role = agent.get('role', 'agent')

    # Parse arguments: /compliance arn ABC-12345
    args = context.args or []

    if len(args) >= 2:
        field = args[0].lower()
        value = ' '.join(args[1:]).strip()
        field_map = {
            'arn': ('arn_number', 'ARN Number'),
            'euin': ('euin', 'EUIN'),
            'irdai': ('irdai_license', 'IRDAI License'),
        }
        tenant_field_map = {
            'sebi': ('sebi_ria_code', 'SEBI RIA Code'),
            'amfi': ('amfi_reg', 'AMFI Registration'),
            'disclaimer': ('compliance_disclaimer', 'Compliance Disclaimer'),
        }

        if field in field_map:
            db_field, label = field_map[field]
            await db.update_agent_profile(agent['agent_id'], **{db_field: value})
            await update.message.reply_text(
                f"✅ <b>{label}</b> {'अपडेट हुआ' if hi else 'updated'}: <code>{h(value)}</code>\n\n"
                f"{'यह आपकी PDF रिपोर्ट्स और WhatsApp मैसेज में दिखेगा।' if hi else 'This will appear in your PDF reports and WhatsApp messages.'}",
                parse_mode=ParseMode.HTML)
            return
        elif field in tenant_field_map and role == 'owner':
            db_field, label = tenant_field_map[field]
            await db.update_tenant(agent['tenant_id'], **{db_field: value})
            await update.message.reply_text(
                f"✅ <b>{label}</b> {'अपडेट हुआ' if hi else 'updated'}: <code>{h(value)}</code>",
                parse_mode=ParseMode.HTML)
            return
        elif field in tenant_field_map and role != 'owner':
            await update.message.reply_text(
                "⚠️ " + ("केवल owner ही tenant-level फ़ील्ड बदल सकता है।" if hi else "Only the firm owner can update tenant-level fields."))
            return

    # Show current compliance status
    creds = await db.build_compliance_credentials(agent['agent_id'])
    tenant = await db.get_tenant(agent['tenant_id'])

    lines = []
    lines.append("🏛️ <b>" + ("अनुपालन विवरण" if hi else "Compliance Details") + "</b>\n")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"\n👤 <b>{'एजेंट' if hi else 'Agent'}:</b> {h(agent['name'])}")
    lines.append(f"📋 ARN: <code>{h(agent.get('arn_number') or '—')}</code>")
    lines.append(f"📋 EUIN: <code>{h(agent.get('euin') or '—')}</code>")
    lines.append(f"📋 IRDAI: <code>{h(agent.get('irdai_license') or '—')}</code>")

    if tenant:
        lines.append(f"\n🏢 <b>{'फर्म' if hi else 'Firm'}:</b> {h(tenant.get('firm_name', ''))}")
        lines.append(f"📋 SEBI RIA: <code>{h(tenant.get('sebi_ria_code') or '—')}</code>")
        lines.append(f"📋 AMFI: <code>{h(tenant.get('amfi_reg') or '—')}</code>")
        lines.append(f"📋 IRDAI (Firm): <code>{h(tenant.get('irdai_license') or '—')}</code>")
        disc = tenant.get('compliance_disclaimer', '')
        lines.append(f"📜 {'अस्वीकरण' if hi else 'Disclaimer'}: <i>{h(disc[:100]) if disc else '—'}</i>")

    if creds:
        lines.append(f"\n✅ <b>{'PDF/WA फ़ूटर' if hi else 'PDF/WA Footer'}:</b>")
        lines.append(f"<i>{h(creds[:200])}</i>")
    else:
        lines.append(f"\n⚠️ {'कोई credentials सेट नहीं — PDF/WA में दिखेगा नहीं।' if hi else 'No credentials set — nothing will appear in PDFs/WhatsApp.'}")

    lines.append(f"\n━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <b>" + ("अपडेट कैसे करें:" if hi else "How to update:") + "</b>")
    lines.append("<code>/compliance arn ARN-12345</code>")
    lines.append("<code>/compliance euin E123456</code>")
    lines.append("<code>/compliance irdai LIC-001</code>")
    if role == 'owner':
        lines.append("<code>/compliance sebi INH000001234</code>")
        lines.append("<code>/compliance amfi ARN-67890</code>")
        lines.append("<code>/compliance disclaimer Mutual Fund investments are subject to market risks</code>")

    await update.message.reply_text('\n'.join(lines), parse_mode=ParseMode.HTML)


# =============================================================================
#  /weblogin — TELEGRAM → WEB DASHBOARD LOGIN (no OTP needed)
# =============================================================================

@registered
async def cmd_weblogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a one-time web login link — lets users access web dashboard
    without requiring phone OTP (useful for agents with dummy phone numbers).
    SA users on the master bot get a tenant picker for impersonation."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return

    # SA on master bot: show tenant picker for impersonation
    is_sa = agent.get('phone', '') in SUPERADMIN_PHONES
    bot_tenant_id = context.bot_data.get('_tenant_id')
    if is_sa and not bot_tenant_id:
        # Master bot — show tenant list for SA impersonation weblogin
        import aiosqlite
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT tenant_id, firm_name, owner_name FROM tenants WHERE is_active=1 ORDER BY firm_name")
            tenants = [dict(r) for r in await cur.fetchall()]
        if not tenants:
            await update.message.reply_text("No active tenants found.")
            return
        kb = []
        for t in tenants:
            label = f"{t['firm_name']} ({t['owner_name']})"
            kb.append([InlineKeyboardButton(label, callback_data=f"sa_weblogin_{t['tenant_id']}")])
        await update.message.reply_text(
            "🌐 <b>SA Web Login — Select Tenant</b>\n\n"
            "Choose which tenant's dashboard to open:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML)
        return

    lang = agent.get('lang', 'en')
    hi = lang == 'hi'

    tenant_id = agent.get('tenant_id')
    agent_id = agent.get('agent_id')
    phone = agent.get('phone', '')
    role = agent.get('role', 'agent')
    tenant = await db.get_tenant(tenant_id)
    firm_name = tenant.get('firm_name', '') if tenant else ''

    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
    token = auth_mod.create_telegram_login_token(
        tenant_id=tenant_id, agent_id=agent_id,
        phone=phone, role=role, firm_name=firm_name
    )
    login_url = f"{server_url}/api/auth/telegram-login?token={token}"

    if hi:
        text = (
            "🌐 <b>वेब डैशबोर्ड लॉगिन</b>\n\n"
            "👇 नीचे बटन पर क्लिक करें — सीधे डैशबोर्ड खुल जाएगा।\n"
            "⏱ यह लिंक <b>5 मिनट</b> में expire हो जाएगा और सिर्फ <b>एक बार</b> इस्तेमाल हो सकता है।"
        )
        btn_text = "🌐 डैशबोर्ड खोलें"
    else:
        text = (
            "🌐 <b>Web Dashboard Login</b>\n\n"
            "👇 Click the button below to open your dashboard directly.\n"
            "⏱ This link expires in <b>5 minutes</b> and can only be used <b>once</b>."
        )
        btn_text = "🌐 Open Dashboard"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_text, url=login_url)]
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# =============================================================================
#  /editprofile — EDIT AGENT PROFILE (name, phone, email)
# =============================================================================

@registered
async def cmd_editprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start profile edit flow — show current profile and field selection."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return ConversationHandler.END
    lang = agent.get('lang', 'en')
    context.user_data['lang'] = lang
    hi = lang == 'hi'

    if hi:
        keyboard = [
            [InlineKeyboardButton("📝 नाम", callback_data="editprof_name")],
            [InlineKeyboardButton("📱 फ़ोन", callback_data="editprof_phone")],
            [InlineKeyboardButton("📧 ईमेल", callback_data="editprof_email")],
            [InlineKeyboardButton("📸 प्रोफाइल फोटो", callback_data="editprof_photo")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Name", callback_data="editprof_name")],
            [InlineKeyboardButton("📱 Phone", callback_data="editprof_phone")],
            [InlineKeyboardButton("📧 Email", callback_data="editprof_email")],
            [InlineKeyboardButton("📸 Profile Photo", callback_data="editprof_photo")],
        ]
    # Owner can also edit firm name
    if agent.get('role') == 'owner':
        keyboard.append(
            [InlineKeyboardButton("🏢 फर्म नाम" if hi else "🏢 Firm Name", callback_data="editprof_firm_name")])
    photo_status = ("✅ सेट" if hi else "✅ Set") if agent.get('profile_photo') else ("❌ नहीं" if hi else "❌ Not set")
    if hi:
        _text = (
            f"✏️ <b>प्रोफाइल संपादित करें</b>\n\n"
            f"👤 नाम: <b>{h(agent['name'])}</b>\n"
            f"📱 फ़ोन: <b>{h(agent.get('phone', 'N/A'))}</b>\n"
            f"📧 ईमेल: <b>{h(agent.get('email', 'N/A'))}</b>\n"
            f"📸 फोटो: {photo_status}\n"
            f"🏢 फर्म: <b>{h(agent.get('firm_name', 'N/A'))}</b>\n\n"
            f"कौन सा फील्ड बदलना है?"
        )
    else:
        _text = (
            f"✏️ <b>Edit Profile</b>\n\n"
            f"👤 Name: <b>{h(agent['name'])}</b>\n"
            f"📱 Phone: <b>{h(agent.get('phone', 'N/A'))}</b>\n"
            f"📧 Email: <b>{h(agent.get('email', 'N/A'))}</b>\n"
            f"📸 Photo: {photo_status}\n"
            f"🏢 Firm: <b>{h(agent.get('firm_name', 'N/A'))}</b>\n\n"
            f"Which field do you want to change?"
        )
    await update.message.reply_text(
        _text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)
    return EDITPROFILE_CHOICE


async def editprofile_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle profile field selection."""
    query = update.callback_query
    await query.answer()
    field = query.data.replace("editprof_", "")
    context.user_data['editprof_field'] = field
    lang = context.user_data.get('lang', 'en')
    hi = lang == 'hi'

    if field == 'photo':
        if hi:
            _photo_text = (
                "📸 <b>प्रोफाइल फोटो भेजें</b>\n\n"
                "एक फोटो भेजें (फाइल नहीं) और यह आपकी प्रोफाइल तस्वीर होगी।\n\n"
                "<i>या /cancel करें</i>"
            )
        else:
            _photo_text = (
                "📸 <b>Send me your profile photo</b>\n\n"
                "Send a photo (not as a file) and it will be set as your profile picture.\n"
                "This photo will appear in your dashboard profile.\n\n"
                "<i>Or /cancel to keep the current photo.</i>"
            )
        await query.edit_message_text(_photo_text, parse_mode=ParseMode.HTML)
        return EDITPROFILE_VALUE

    field_labels = {'name': 'पूरा नाम' if hi else 'full name',
                     'phone': 'फ़ोन नंबर' if hi else 'phone number',
                     'email': 'ईमेल' if hi else 'email address',
                     'firm_name': 'फर्म नाम' if hi else 'firm name'}
    _enter = "अपना नया" if hi else "Enter your new"
    _cancel = "/cancel करें मौजूदा रखने के लिए" if hi else "Or /cancel to keep the current value."
    await query.edit_message_text(
        f"📝 {_enter} <b>{field_labels.get(field, field)}</b>:\n\n"
        f"<i>{_cancel}</i>",
        parse_mode=ParseMode.HTML)
    return EDITPROFILE_VALUE


async def editprofile_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save the new profile value."""
    field = context.user_data.get('editprof_field', '')
    value = update.message.text.strip()
    agent = await db.get_agent(str(update.effective_user.id))
    if not agent:
        return ConversationHandler.END
    lang = agent.get('lang', 'en')

    # Validate based on field
    if field == 'phone':
        phone = _valid_phone(value)
        if not phone:
            _err = "❌ अमान्य फ़ोन। 10 अंकों का सही नंबर दर्ज करें।\n/cancel करें रखने के लिए" if lang == 'hi' else \
                  "❌ Invalid phone number. Enter a valid 10-digit Indian mobile number.\nOr /cancel to keep the current value."
            await update.message.reply_text(_err)
            return EDITPROFILE_VALUE
        value = phone
    elif field == 'email':
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', value):
            _err = "❌ अमान्य ईमेल। सही ईमेल दर्ज करें (name@example.com)\n/cancel करें" if lang == 'hi' else \
                  "❌ Invalid email format. Enter a valid email (e.g., name@example.com)\nOr /cancel to keep the current value."
            await update.message.reply_text(_err)
            return EDITPROFILE_VALUE
        value = value.lower()
    elif field == 'name':
        if len(value) < 2 or len(value) > 100:
            _err = "❌ नाम 2-100 अक्षरों का होना चाहिए।\n/cancel करें" if lang == 'hi' else \
                  "❌ Name must be 2-100 characters. Please try again.\nOr /cancel to keep the current value."
            await update.message.reply_text(_err)
            return EDITPROFILE_VALUE
    elif field == 'firm_name':
        if len(value) < 2 or len(value) > 200:
            _err = "❌ फर्म नाम 2-200 अक्षरों का होना चाहिए।\n/cancel करें" if lang == 'hi' else \
                  "❌ Firm name must be 2-200 characters. Please try again.\nOr /cancel to keep the current value."
            await update.message.reply_text(_err)
            return EDITPROFILE_VALUE
        # Owner-only: also update the tenant record
        if agent.get('role') == 'owner' and agent.get('tenant_id'):
            await db.update_tenant(agent['tenant_id'], firm_name=value)

    if field == 'firm_name':
        # Sync agents.firm_name to match tenant (keep in sync)
        await db.update_agent_profile(agent['agent_id'], firm_name=value)
    else:
        await db.update_agent_profile(agent['agent_id'], **{field: value})
    await db.log_audit("profile_edited", f"{field} changed",
                       tenant_id=agent['tenant_id'], agent_id=agent['agent_id'])

    field_labels = {'name': 'नाम' if lang == 'hi' else 'Name',
                    'phone': 'फ़ोन' if lang == 'hi' else 'Phone',
                    'email': 'ईमेल' if lang == 'hi' else 'Email',
                    'firm_name': 'फर्म नाम' if lang == 'hi' else 'Firm Name'}
    _updated = "अपडेट हो गया" if lang == 'hi' else "updated to"
    await update.message.reply_text(
        f"✅ {field_labels.get(field, field)} {_updated}: <b>{h(value)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=_main_menu_keyboard(lang))
    context.user_data.clear()
    return ConversationHandler.END


async def editprofile_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle profile photo upload via Telegram."""
    field = context.user_data.get('editprof_field', '')
    if field != 'photo':
        # Shouldn't happen — ignore
        return EDITPROFILE_VALUE

    agent = await db.get_agent(str(update.effective_user.id))
    if not agent:
        return ConversationHandler.END
    lang = agent.get('lang', 'en')

    try:
        # Get the highest resolution photo
        photo = update.message.photo[-1]
        file = await photo.get_file()

        # Save to uploads/photos/ with agent-scoped filename
        import pathlib
        photos_dir = pathlib.Path(__file__).parent / "uploads" / "photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        filename = f"agent_{agent['agent_id']}.jpg"
        filepath = photos_dir / filename
        await file.download_to_drive(str(filepath))

        # Update DB
        photo_url = f"/uploads/photos/{filename}"
        await db.update_agent_profile(agent['agent_id'], profile_photo=photo_url)
        await db.log_audit("profile_photo_updated", "Photo uploaded via Telegram",
                           tenant_id=agent['tenant_id'], agent_id=agent['agent_id'])

        await update.message.reply_text(
            "✅ प्रोफाइल फोटो अपडेट! 📸\n\nआपकी फोटो वेब डैशबोर्ड में दिखेगी।" if lang == 'hi' else
            "✅ Profile photo updated! 📸\n\nYour photo will appear in the web dashboard.",
            parse_mode=ParseMode.HTML,
            reply_markup=_main_menu_keyboard(lang))
    except Exception as e:
        logger.error("Profile photo upload failed: %s", e)
        _err = "❌ फोटो सेव विफल। पुनः प्रयास करें या /cancel करें।" if lang == 'hi' else \
              "❌ Failed to save photo. Please try again or /cancel."
        await update.message.reply_text(
            _err,
            parse_mode=ParseMode.HTML)
        return EDITPROFILE_VALUE

    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  /editagent — OWNER/ADMIN: EDIT TEAM AGENT DETAILS
# =============================================================================

@registered
async def cmd_editagent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of team agents to edit (owner/admin only)."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return ConversationHandler.END
    lang = agent.get('lang', 'en')
    context.user_data['lang'] = lang
    hi = lang == 'hi'

    if agent.get('role') not in ('owner', 'admin'):
        msg = "ℹ️ केवल फर्म मालिक/एडमिन ही एजेंट संपादित कर सकते हैं।" if hi else "ℹ️ Only the firm owner or admin can edit agents."
        await update.message.reply_text(msg)
        return ConversationHandler.END

    # Team+ plan required
    cap = await db.can_add_agent(agent['tenant_id'])
    if cap.get('plan') in ('trial', 'individual'):
        msg = "ℹ️ यह सुविधा टीम या एंटरप्राइज प्लान में उपलब्ध है।" if hi else "ℹ️ Edit agent requires a Team or Enterprise plan."
        await update.message.reply_text(msg)
        return ConversationHandler.END

    agents = await db.get_agents_by_tenant(agent['tenant_id'])
    editable = [a for a in agents if a['agent_id'] != agent['agent_id'] and a.get('role') != 'owner']
    if not editable:
        msg = "ℹ️ संपादित करने के लिए कोई एजेंट नहीं।" if hi else "ℹ️ No agents to edit."
        await update.message.reply_text(msg)
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(
        f"{'👤' if a.get('role')=='agent' else '🛡️'} {a['name']} ({a.get('role','agent')})",
        callback_data=f"teamedit_{a['agent_id']}"
    )] for a in editable]

    title = "✏️ <b>एजेंट संपादित करें</b>\n\nकिस एजेंट को बदलना है?" if hi else \
            "✏️ <b>Edit Agent</b>\n\nSelect an agent to edit:"
    await update.message.reply_text(title, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return TEAM_EDIT_FIELD


async def team_edit_select_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle agent selection → show field buttons."""
    query = update.callback_query
    await query.answer()
    data = query.data
    lang = context.user_data.get('lang', 'en')
    hi = lang == 'hi'

    if data.startswith("teamedit_"):
        agent_id = int(data.replace("teamedit_", ""))
        target = await db.get_agent_by_id(agent_id)
        if not target:
            await query.edit_message_text("❌ Agent not found.")
            return ConversationHandler.END
        context.user_data['team_edit_agent_id'] = agent_id
        context.user_data['team_edit_agent_name'] = target.get('name', '?')

        if hi:
            keyboard = [
                [InlineKeyboardButton("📝 नाम", callback_data="teamfield_name")],
                [InlineKeyboardButton("📱 फ़ोन", callback_data="teamfield_phone")],
                [InlineKeyboardButton("📧 ईमेल", callback_data="teamfield_email")],
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("📝 Name", callback_data="teamfield_name")],
                [InlineKeyboardButton("📱 Phone", callback_data="teamfield_phone")],
                [InlineKeyboardButton("📧 Email", callback_data="teamfield_email")],
            ]
        # Only owner can change roles
        caller = context.user_data.get('_agent') or await _get_agent_from_query(update)
        if caller and caller.get('role') == 'owner':
            current_role = target.get('role', 'agent')
            toggle_label = ("🛡️ एडमिन बनाएं" if current_role == 'agent' else "👤 एजेंट बनाएं") if hi else \
                           ("🛡️ Promote to Admin" if current_role == 'agent' else "👤 Demote to Agent")
            toggle_value = "admin" if current_role == 'agent' else "agent"
            keyboard.append([InlineKeyboardButton(toggle_label, callback_data=f"teamrole_{toggle_value}")])

        info = (
            f"✏️ <b>{h(target['name'])}</b> संपादित करें\n\n"
            f"📝 नाम: <b>{h(target['name'])}</b>\n"
            f"📱 फ़ोन: <b>{h(target.get('phone','N/A'))}</b>\n"
            f"📧 ईमेल: <b>{h(target.get('email','N/A'))}</b>\n"
            f"🏷️ भूमिका: <b>{target.get('role','agent')}</b>\n\n"
            f"कौन सा फील्ड बदलना है?"
        ) if hi else (
            f"✏️ Edit <b>{h(target['name'])}</b>\n\n"
            f"📝 Name: <b>{h(target['name'])}</b>\n"
            f"📱 Phone: <b>{h(target.get('phone','N/A'))}</b>\n"
            f"📧 Email: <b>{h(target.get('email','N/A'))}</b>\n"
            f"🏷️ Role: <b>{target.get('role','agent')}</b>\n\n"
            f"Which field do you want to change?"
        )
        await query.edit_message_text(info, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return TEAM_EDIT_FIELD

    elif data.startswith("teamfield_"):
        field = data.replace("teamfield_", "")
        context.user_data['team_edit_field'] = field
        field_labels = {'name': 'पूरा नाम' if hi else 'full name',
                        'phone': 'फ़ोन नंबर' if hi else 'phone number',
                        'email': 'ईमेल' if hi else 'email address'}
        agent_name = context.user_data.get('team_edit_agent_name', '?')
        _enter = "नया" if hi else "Enter the new"
        _for = "के लिए" if hi else "for"
        _cancel = "/cancel करें रखने के लिए" if hi else "Or /cancel to keep current value."
        await query.edit_message_text(
            f"📝 {_enter} <b>{field_labels.get(field, field)}</b> {_for} <b>{h(agent_name)}</b>:\n\n<i>{_cancel}</i>",
            parse_mode=ParseMode.HTML)
        return TEAM_EDIT_VALUE

    elif data.startswith("teamrole_"):
        new_role = data.replace("teamrole_", "")
        agent_id = context.user_data.get('team_edit_agent_id')
        agent_name = context.user_data.get('team_edit_agent_name', '?')
        if agent_id:
            await db.update_agent_profile(agent_id, role=new_role)
            role_label = ("एडमिन" if new_role == 'admin' else "एजेंट") if hi else new_role
            msg = f"✅ <b>{h(agent_name)}</b> की भूमिका <b>{role_label}</b> में बदली गई।" if hi else \
                  f"✅ <b>{h(agent_name)}</b> role changed to <b>{new_role}</b>."
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        context.user_data.clear()
        return ConversationHandler.END

    return TEAM_EDIT_FIELD


async def team_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save the new value for the selected agent field."""
    value = update.message.text.strip()
    field = context.user_data.get('team_edit_field', '')
    agent_id = context.user_data.get('team_edit_agent_id')
    agent_name = context.user_data.get('team_edit_agent_name', '?')
    lang = context.user_data.get('lang', 'en')
    hi = lang == 'hi'

    if not agent_id:
        await update.message.reply_text("❌ Session expired. Use /editagent again.")
        return ConversationHandler.END

    # Validate
    if field == 'phone':
        phone = _valid_phone(value)
        if not phone:
            _err = "❌ अमान्य फ़ोन। 10 अंकों का सही नंबर दर्ज करें।\n/cancel करें" if hi else \
                  "❌ Invalid phone. Enter a valid 10-digit number.\nOr /cancel."
            await update.message.reply_text(_err)
            return TEAM_EDIT_VALUE
        value = phone
    elif field == 'email':
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', value):
            _err = "❌ अमान्य ईमेल। सही ईमेल दर्ज करें।\n/cancel करें" if hi else \
                  "❌ Invalid email. Enter a valid email.\nOr /cancel."
            await update.message.reply_text(_err)
            return TEAM_EDIT_VALUE
        value = value.lower()
    elif field == 'name':
        if len(value) < 2 or len(value) > 100:
            _err = "❌ नाम 2-100 अक्षरों का होना चाहिए।\n/cancel करें" if hi else \
                  "❌ Name must be 2-100 characters.\nOr /cancel."
            await update.message.reply_text(_err)
            return TEAM_EDIT_VALUE

    await db.update_agent_profile(agent_id, **{field: value})
    field_hi = {'name': 'नाम', 'phone': 'फ़ोन', 'email': 'ईमेल'}
    field_label = field_hi.get(field, field) if hi else field
    msg = f"✅ <b>{h(agent_name)}</b> का {field_label} अपडेट किया: <b>{h(value)}</b>" if hi else \
          f"✅ <b>{h(agent_name)}</b> {field} updated to: <b>{h(value)}</b>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    context.user_data.clear()
    return ConversationHandler.END


async def _get_agent_from_query(update: Update):
    """Get agent from callback query user."""
    query = update.callback_query
    if query and query.from_user:
        return await db.get_agent(str(query.from_user.id))
    return None


# =============================================================================
#  /editlead — EDIT LEAD DETAILS
# =============================================================================

@registered
async def cmd_editlead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the edit-lead flow — expects /editlead <lead_id>."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return ConversationHandler.END
    lang = agent.get('lang', 'en')
    context.user_data['lang'] = lang

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Please provide a lead ID.\n"
            "Usage: <code>/editlead 42</code>",
            parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    try:
        lead_id = int(args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid lead ID. Use a number.\n"
            "Usage: <code>/editlead 42</code>",
            parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    lead = await db.get_lead(lead_id)
    if not lead or lead['agent_id'] != agent['agent_id']:
        await update.message.reply_text("❌ Lead not found or access denied.")
        return ConversationHandler.END

    context.user_data['editlead_id'] = lead_id

    keyboard = [
        [InlineKeyboardButton("📝 Name", callback_data="editlead_name")],
        [InlineKeyboardButton("📱 Phone", callback_data="editlead_phone")],
        [InlineKeyboardButton("📧 Email", callback_data="editlead_email")],
        [InlineKeyboardButton("🎂 DOB", callback_data="editlead_dob")],
        [InlineKeyboardButton("💍 Anniversary", callback_data="editlead_anniversary")],
        [InlineKeyboardButton("🏙️ City", callback_data="editlead_city")],
        [InlineKeyboardButton("🏥 Need Type", callback_data="editlead_need_type")],
        [InlineKeyboardButton("📝 Notes", callback_data="editlead_notes")],
    ]
    await update.message.reply_text(
        f"✏️ <b>Edit Lead #{lead_id}: {h(lead['name'])}</b>\n\n"
        f"📱 Phone: {h(lead.get('phone', 'N/A'))}\n"
        f"📧 Email: {h(lead.get('email', 'N/A'))}\n"
        f"🎂 DOB: {h(lead.get('dob', 'N/A'))}\n"
        f"💍 Anniversary: {h(lead.get('anniversary', 'N/A'))}\n"
        f"🏙️ City: {h(lead.get('city', 'N/A'))}\n"
        f"🏥 Need: {h(lead.get('need_type', 'N/A'))}\n"
        f"📝 Notes: {h(lead.get('notes', 'N/A'))}\n\n"
        f"Which field do you want to change?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)
    return EDITLEAD_FIELD


async def editlead_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle lead field selection."""
    query = update.callback_query
    await query.answer()
    field = query.data.replace("editlead_", "")
    context.user_data['editlead_field'] = field

    field_hints = {
        'name': 'Enter the new name:',
        'phone': 'Enter the new 10-digit phone number:',
        'email': 'Enter the new email address:',
        'dob': 'Enter the date of birth (DD-MM-YYYY):',
        'anniversary': 'Enter the anniversary date (DD-MM-YYYY):',
        'city': 'Enter the new city:',
        'need_type': ('Enter the insurance need type.\n\n'
                      'Valid options: <b>health, term, retirement, '
                      'child, investment, motor</b>\n'
                      '(or comma-separated for multiple, e.g. "health, term"):'),
        'notes': 'Enter the new notes:',
    }
    await query.edit_message_text(
        f"📝 <b>{field_hints.get(field, 'Enter the new value:')}</b>\n\n"
        f"<i>Or /cancel to keep the current value.</i>",
        parse_mode=ParseMode.HTML)
    return EDITLEAD_VALUE


async def editlead_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save the edited lead field."""
    field = context.user_data.get('editlead_field', '')
    lead_id = context.user_data.get('editlead_id')
    value = update.message.text.strip()
    agent = await db.get_agent(str(update.effective_user.id))
    if not agent:
        return ConversationHandler.END
    lang = agent.get('lang', 'en')

    # Validate based on field type
    if field == 'phone':
        phone = _valid_phone(value)
        if not phone:
            await update.message.reply_text(
                "❌ Invalid phone. Enter a valid 10-digit Indian mobile number.\n"
                "Or /cancel to keep the current value.")
            return EDITLEAD_VALUE
        value = phone
    elif field == 'email':
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', value):
            await update.message.reply_text(
                "❌ Invalid email format. Try again or /cancel.")
            return EDITLEAD_VALUE
        value = value.lower()
    elif field in ('dob', 'anniversary'):
        try:
            dt = _parse_date(value)
            # Range validation: not in the future, not before 1900
            if dt > datetime.now():
                await update.message.reply_text(
                    "❌ Date cannot be in the future. Try again or /cancel.")
                return EDITLEAD_VALUE
            if dt.year < 1900:
                await update.message.reply_text(
                    "❌ Invalid year. Try again or /cancel.")
                return EDITLEAD_VALUE
            value = dt.strftime('%Y-%m-%d')
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid date format. Use DD-MM-YYYY.\n"
                "Or /cancel to keep the current value.")
            return EDITLEAD_VALUE
    elif field == 'name':
        if len(value) < 2 or len(value) > 100:
            await update.message.reply_text(
                "❌ Name must be 2-100 characters. Try again or /cancel.")
            return EDITLEAD_VALUE
    elif field == 'need_type':
        _valid_needs = {'health', 'term', 'endowment', 'ulip', 'child', 'retirement', 'motor', 'investment', 'nps', 'general'}
        parts = [p.strip().lower() for p in value.replace(',', ' ').split()]
        invalid = [p for p in parts if p not in _valid_needs]
        if invalid or not parts:
            await update.message.reply_text(
                "❌ Invalid need type.\n"
                "Valid options: health, term, endowment, ulip, child, retirement, motor, investment, nps, general\n"
                "Enter one or comma-separated (e.g. \"health, term\").\n"
                "Or /cancel to keep the current value.")
            return EDITLEAD_VALUE
        value = ", ".join(sorted(set(parts)))

    # Ownership re-check
    lead = await db.get_lead(lead_id)
    if not lead or lead['agent_id'] != agent['agent_id']:
        await update.message.reply_text("❌ Lead not found or access denied.")
        context.user_data.clear()
        return ConversationHandler.END

    await db.update_lead(lead_id, **{field: value})
    await db.log_audit("lead_edited", f"Lead #{lead_id} {field} changed",
                       tenant_id=agent['tenant_id'], agent_id=agent['agent_id'])

    field_labels = {'name': 'Name', 'phone': 'Phone', 'email': 'Email',
                    'dob': 'DOB', 'anniversary': 'Anniversary', 'city': 'City',
                    'need_type': 'Need Type', 'notes': 'Notes'}
    await update.message.reply_text(
        f"✅ Lead #{lead_id} {field_labels.get(field, field)} updated to: <b>{h(value)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=_main_menu_keyboard(lang))
    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
#  VOICE-FIRST CRM — Voice note → AI-powered multi-action engine
# =============================================================================

# ── Abuse / content filter ────────────────────────────────────────────────
_ABUSE_WORDS_HI = {
    'madarchod', 'bhenchod', 'chutiya', 'gaand', 'lund', 'randi', 'harami',
    'saala', 'kutte', 'kamina', 'haramkhor', 'bhosdike', 'gandu',
    'mc', 'bc', 'bsdk', 'chutiye', 'randwe',
}
_ABUSE_WORDS_EN = {
    'fuck', 'shit', 'bitch', 'bastard', 'asshole', 'dick', 'cunt',
    'motherfucker', 'damn', 'piss', 'whore', 'slut', 'nigger', 'fag',
}
_ABUSE_WORDS = _ABUSE_WORDS_HI | _ABUSE_WORDS_EN


_HELP_KEYWORDS = {'help', 'stuck', 'issue', 'problem', 'confused', 'difficult',
                   'madad', 'dikkat', 'mushkil', 'samajh', 'nahi', 'kaise'}

async def _check_note_needs_admin(agent: dict, lead_id: int, note_text: str):
    """If advisor note has help/stuck keywords, notify the admin/owner."""
    try:
        words = set(re.findall(r'[a-zA-Z\u0900-\u097F]+', note_text.lower()))
        if not words & _HELP_KEYWORDS:
            return
        tid = agent.get('tenant_id')
        if not tid:
            return
        # Get owner for this tenant
        import aiosqlite
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await conn.execute(
                "SELECT telegram_id, lang FROM agents WHERE tenant_id = ? AND role = 'owner' AND is_active = 1 LIMIT 1",
                (tid,))
            owner = await row.fetchone()
        if not owner or not owner['telegram_id']:
            return
        lead = await db.get_lead(lead_id)
        lead_name = lead.get('name', 'Client') if lead else 'Client'
        agent_name = agent.get('name', 'Advisor')
        import biz_reminders as rem
        hi = owner.get('lang', 'en') == 'hi'
        if hi:
            msg = (f"🚨 *Advisor को मदद चाहिए!*\n\n"
                   f"👤 {agent_name} ने {lead_name} पर लिखा:\n"
                   f"📋 _{note_text}_\n\n"
                   f"_Dashboard पर lead timeline देखें._")
        else:
            msg = (f"🚨 *Advisor needs help!*\n\n"
                   f"👤 {agent_name} noted on lead {lead_name}:\n"
                   f"📋 _{note_text}_\n\n"
                   f"_Check the lead timeline on your dashboard._")
        await rem._send_telegram(owner['telegram_id'], msg)
    except Exception as e:
        logger.warning("Help keyword notification failed: %s", e)


def _contains_abuse(text: str) -> bool:
    """Check if text contains abusive/profane language."""
    if not text:
        return False
    words = set(re.findall(r'[a-zA-Z]+', text.lower()))
    return bool(words & _ABUSE_WORDS)


async def _check_abuse(agent_id: int, text: str, lang: str,
                       message_target) -> bool:
    """Check text for abuse. If found, record warning, send alert, return True.
    message_target: a message or query that has .edit_text or .reply_text."""
    flagged = _contains_abuse(text)
    if not flagged:
        return False

    rec = await db.record_abuse_warning(agent_id, text)
    count = rec['warning_count']

    if rec.get('blocked_until'):
        warn_msg = i18n.t(lang, "voice_blocked")
    else:
        warn_msg = i18n.t(lang, "voice_abuse_warning", count=count)

    try:
        if hasattr(message_target, 'edit_text'):
            await message_target.edit_text(warn_msg, parse_mode=ParseMode.HTML)
        else:
            await message_target.reply_text(warn_msg, parse_mode=ParseMode.HTML)
    except Exception:
        pass

    logger.warning("Abuse detected for agent %s (warning #%d): %s",
                   agent_id, count, text[:100])
    return True


# ── Safe edit helper (works with both Message and CallbackQuery) ────────────
async def _safe_edit_text(msg_or_query, text, **kwargs):
    """Edit message text — works with both Message and CallbackQuery objects."""
    if hasattr(msg_or_query, 'edit_message_text'):
        return await msg_or_query.edit_message_text(text, **kwargs)
    return await msg_or_query.edit_text(text, **kwargs)


# ── Fallback time extraction from transcript ─────────────────────────
def _extract_time_from_transcript(transcript: str) -> str | None:
    """Extract time from voice transcript when AI didn't return reminder_time.
    Returns HH:MM in 24hr format or None."""
    import re
    t = transcript.lower().strip()
    # Pattern: "4 pm", "4PM", "4:30 pm", "10 am", "10:00 AM"
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)', t, re.IGNORECASE)
    if m:
        hr, mn, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower().replace('.', '')
        if ampm == 'pm' and hr < 12: hr += 12
        elif ampm == 'am' and hr == 12: hr = 0
        return f"{hr:02d}:{mn:02d}"
    # Hindi patterns: "4 baje", "dopahar 4", "subah 10", "sham 6", "raat 9"
    m = re.search(r'(?:dopahar|afternoon)\s*(\d{1,2})', t)
    if m: return f"{int(m.group(1)) + (12 if int(m.group(1)) < 12 else 0):02d}:00"
    m = re.search(r'(?:subah|morning|savere)\s*(\d{1,2})', t)
    if m: return f"{int(m.group(1)):02d}:00"
    m = re.search(r'(?:sham|shaam|evening)\s*(\d{1,2})', t)
    if m: return f"{int(m.group(1)) + (12 if int(m.group(1)) < 12 else 0):02d}:00"
    m = re.search(r'(?:raat|night)\s*(\d{1,2})', t)
    if m:
        hr = int(m.group(1))
        return f"{hr + (12 if hr < 12 else 0):02d}:00"
    m = re.search(r'(\d{1,2})\s*baj[e]?', t)
    if m:
        hr = int(m.group(1))
        # Default "baje" to PM if <= 7 (contextually afternoon/evening)
        if hr <= 7: hr += 12
        return f"{hr:02d}:00"
    return None


# ── Lead fuzzy finder ─────────────────────────────────────────────────────
async def _find_lead_by_voice(agent_id: int, name: str = None,
                               phone: str = None, tenant_id: int = None) -> dict | None:
    """Try to find an existing lead by name or phone (fuzzy match).
    If tenant_id is provided (admin mode), search across all tenant leads."""
    if tenant_id:
        # Admin: search tenant-wide
        if phone:
            cleaned = _valid_phone(phone)
            if cleaned:
                result = await db.get_leads_by_tenant(tenant_id, search=cleaned, limit=5)
                if result['leads']:
                    return result['leads'][0]
        if name:
            result = await db.get_leads_by_tenant(tenant_id, search=name, limit=20)
            if result['leads']:
                name_lower = name.lower()
                for r in result['leads']:
                    if name_lower in r['name'].lower():
                        return r
                return result['leads'][0]
        return None
    # Normal agent: search own leads only
    if phone:
        cleaned = _valid_phone(phone)
        if cleaned:
            results = await db.search_leads(agent_id, cleaned)
            if results:
                return results[0]
    if name:
        results = await db.search_leads(agent_id, name)
        if results:
            # Prefer exact-ish name match
            name_lower = name.lower()
            for r in results:
                if name_lower in r['name'].lower():
                    return r
            return results[0]
    return None


async def _voice_to_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Voice-First CRM: transcribe via Gemini, detect intent, route to action."""
    agent = await _require_agent_auth(update, context)
    if not agent:
        return

    lang = agent.get('lang', 'en')

    # Check if agent is blocked for abuse
    if await db.is_agent_blocked(agent['agent_id']):
        await update.message.reply_text(
            i18n.t(lang, "voice_blocked"), parse_mode=ParseMode.HTML)
        return

    # ── AI quota check (voice is expensive) ─────────────────────────
    quota = await db.check_ai_quota(agent['agent_id'])
    if not quota['allowed']:
        await update.message.reply_text(
            i18n.t(lang, "ai_quota_reached",
                   used=quota['used'], limit=quota['limit']),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_menu_keyboard(lang))
        return

    client = _get_gemini()
    if not client:
        await update.message.reply_text(
            i18n.t(lang, "ai_not_configured"), parse_mode=ParseMode.HTML)
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    duration = voice.duration or 0
    if duration > 120:
        await update.message.reply_text(
            i18n.t(lang, "voice_too_long"), parse_mode=ParseMode.HTML)
        return

    # Show "please wait" with slow-network aware messaging
    processing_msg = await update.message.reply_text(
        i18n.t(lang, "voice_wait_slow"))

    data = None
    retry_count = 0
    max_retries = 2

    while retry_count <= max_retries:
        try:
            # Download voice file from Telegram
            tg_file = await context.bot.get_file(voice.file_id)
            audio_bytes = await tg_file.download_as_bytearray()

            # Update prompt with current date
            prompt = _VOICE_PROMPT.replace(
                _VOICE_PROMPT.split("Today's date is ")[1].split("\n")[0],
                datetime.now().strftime('%Y-%m-%d (%A)')
            ) if "Today's date is " in _VOICE_PROMPT else _VOICE_PROMPT

            # Inject recent context for pronoun/reference resolution
            ctx_block = _build_voice_context_block(context)
            if ctx_block:
                prompt = prompt + ctx_block

            response = await client.aio.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                contents=[
                    genai_types.Part.from_bytes(
                        data=bytes(audio_bytes),
                        mime_type="audio/ogg"),
                    prompt
                ]
            )

            # Parse JSON response
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
            data = json.loads(raw_text)
            # Debug: log intent + time extraction for follow-ups
            if data.get('intent') in ('setup_followup', 'create_reminder'):
                logger.info("🎙️ Voice follow-up AI response: intent=%s, date=%s, time=%s, lead=%s, transcript='%s'",
                            data.get('intent'), data.get('reminder_date') or data.get('follow_up'),
                            data.get('reminder_time'), data.get('lead_name'), (data.get('transcript') or '')[:80])
            break  # Success

        except json.JSONDecodeError:
            retry_count += 1
            if retry_count <= max_retries:
                try:
                    await processing_msg.edit_text(
                        i18n.t(lang, "voice_network_retry"))
                except Exception:
                    pass
                continue
            await processing_msg.edit_text(
                i18n.t(lang, "voice_no_data"), parse_mode=ParseMode.HTML)
            return

        except (ConnectionError, TimeoutError, OSError) as e:
            retry_count += 1
            logger.warning("Voice network error (attempt %d): %s", retry_count, e)
            if retry_count <= max_retries:
                try:
                    await processing_msg.edit_text(
                        i18n.t(lang, "voice_network_retry"))
                except Exception:
                    pass
                import asyncio
                await asyncio.sleep(2)
                continue
            await processing_msg.edit_text(
                i18n.t(lang, "voice_failed_retry"), parse_mode=ParseMode.HTML)
            return

        except Exception as e:
            logger.error("Voice-to-Action error: %s", e)
            await processing_msg.edit_text(
                i18n.t(lang, "voice_failed_retry"), parse_mode=ParseMode.HTML)
            return

    if not data:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_failed_retry"), parse_mode=ParseMode.HTML)
        return

    # ── Abuse check on transcript ─────────────────────────────────────
    transcript = data.get('transcript', '')
    has_abuse = data.get('has_abuse', False) or _contains_abuse(transcript)
    if has_abuse:
        abused = await _check_abuse(
            agent['agent_id'], transcript, lang, processing_msg)
        if abused:
            return

    # ── Log voice action ──────────────────────────────────────────────
    intent = data.get('intent', 'general')
    await db.log_voice_action(
        agent_id=agent['agent_id'],
        transcript=transcript,
        extracted_data=json.dumps(data),
        audio_duration=duration
    )
    # Track AI usage (voice is most expensive — audio processing)
    await db.log_ai_usage(
        tenant_id=agent.get('tenant_id'),
        agent_id=agent['agent_id'],
        feature='voice_to_action',
        tokens_in=int(duration * 25),  # audio token estimate
        tokens_out=len(json.dumps(data)) // 4,
        source='telegram')

    # ── Ask AI mode: voice note = question for AI ─────────────────────
    if context.user_data.get('awaiting_ai_question') and transcript:
        context.user_data.pop('awaiting_ai_question', None)
        try:
            await processing_msg.edit_text(
                i18n.t(lang, "ai_thinking"), parse_mode=ParseMode.HTML)
        except Exception:
            pass
        answer = await ai.ask_insurance_ai(transcript, lang=lang)
        keyboard = [[InlineKeyboardButton("💬 Ask Another Question",
                                          callback_data="ai_chat")],
                     [InlineKeyboardButton("🔙 Back to AI Tools",
                                          callback_data="ai_back")]]
        if len(answer) > 3800:
            answer = answer[:3800] + "\n\n... (truncated)"
        await processing_msg.edit_text(
            f"🎙 <b>Your question:</b> <i>{h(transcript)}</i>\n\n"
            f"💬 <b>AI Answer</b>\n━━━━━━━━━━━━━━━━━━\n\n{h(answer)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)
        return

    # ── Pending follow-up notes (voice note as CRM notes) ────────────
    pending_note = context.user_data.get('pending_followup_note')
    if pending_note and transcript:
        # Expire pending note after 10 minutes
        try:
            asked = datetime.fromisoformat(pending_note.get('asked_at', ''))
            if (datetime.now() - asked).total_seconds() > 600:
                context.user_data.pop('pending_followup_note', None)
                pending_note = None
        except (ValueError, TypeError):
            context.user_data.pop('pending_followup_note', None)
            pending_note = None
    if pending_note and transcript:
        import aiosqlite
        iid = pending_note['interaction_id']
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await conn.execute(
                "SELECT lead_id FROM interactions WHERE interaction_id = ?", (iid,))
            result = await row.fetchone()
        if result:
            lead_id = result['lead_id']
            await db.add_lead_note(
                lead_id=lead_id,
                agent_id=agent['agent_id'],
                note_text=transcript,
                interaction_id=iid,
                author_role='advisor')
            context.user_data.pop('pending_followup_note', None)
            hi = lang == 'hi'
            if hi:
                msg = (f"📋 *Notes save हो गए!* ✅\n\n"
                       f"🎙 _{transcript}_\n\n"
                       f"Dashboard पर lead timeline में दिखेंगे।")
            else:
                msg = (f"📋 *Notes saved!* ✅\n\n"
                       f"🎙 _{transcript}_\n\n"
                       f"Visible on the lead timeline in your dashboard.")
            await processing_msg.edit_text(msg, parse_mode='Markdown')
            # Check if advisor needs help
            asyncio.create_task(_check_note_needs_admin(agent, lead_id, transcript))
            return
        else:
            context.user_data.pop('pending_followup_note', None)

    # ── Multi-turn voice context (pending action from previous voice) ─
    voice_ctx = context.user_data.get('voice_context')
    if voice_ctx and transcript:
        # Expiry check: clear stale context older than 5 minutes
        ctx_created = voice_ctx.get('created_at', 0)
        if time.time() - ctx_created > 300:
            context.user_data.pop('voice_context', None)
            voice_ctx = None
        # Intent override: if AI clearly detected a different intent, break out
        if voice_ctx and intent not in ('general', voice_ctx.get('pending_action', '')):
            context.user_data.pop('voice_context', None)
            voice_ctx = None
    if voice_ctx and transcript:
        pending = voice_ctx.get('pending_action')
        if pending == 'setup_followup' and voice_ctx.get('awaiting') == 'date':
            # Parse date AND time from this voice note
            parsed_date = data.get('reminder_date') or data.get('follow_up')
            parsed_time = data.get('reminder_time')  # HH:MM in 24hr IST
            # Also check time stored from first voice note
            if not parsed_time:
                parsed_time = voice_ctx.get('reminder_time')
            if not parsed_date:
                # Try to extract date from transcript using simple parsing
                _today = datetime.now()
                t_lower = transcript.lower()
                if 'kal' in t_lower or 'tomorrow' in t_lower:
                    parsed_date = (_today + timedelta(days=1)).strftime('%Y-%m-%d')
                elif 'parso' in t_lower or 'day after' in t_lower:
                    parsed_date = (_today + timedelta(days=2)).strftime('%Y-%m-%d')
                elif 'agle hafte' in t_lower or 'next week' in t_lower:
                    parsed_date = (_today + timedelta(days=(7 - _today.weekday()))).strftime('%Y-%m-%d')
            # Fallback time extraction from transcript if AI didn't return it
            if not parsed_time and transcript:
                parsed_time = _extract_time_from_transcript(transcript)

            if parsed_date:
                lead_id = voice_ctx['lead_id']
                lead_name_ctx = voice_ctx.get('lead_name', '')
                msg_ctx = voice_ctx.get('message', '')
                context.user_data.pop('voice_context', None)

                # Admin assignment: use lead's agent, track admin as creator
                _is_admin = agent.get('role') in ('owner', 'admin')
                lead = await db.get_lead(lead_id)
                target_agent_id = (lead.get('agent_id') if lead else None) or agent['agent_id']
                created_by = agent['agent_id'] if _is_admin and target_agent_id != agent['agent_id'] else None

                # Check for existing pending follow-up to avoid duplicates
                existing = await db.get_pending_followups_for_lead(lead_id)
                is_update = False
                if existing:
                    ef = existing[0]
                    existing_iid = ef.get('interaction_id')
                    is_update = True
                    await db.update_followup(
                        interaction_id=existing_iid,
                        follow_up_date=parsed_date,
                        follow_up_time=parsed_time,
                        summary=f"Voice follow-up: {msg_ctx[:100]}" if msg_ctx else None
                    )
                    iid = existing_iid
                else:
                    iid = await db.log_interaction(
                        lead_id=lead_id,
                        agent_id=target_agent_id,
                        interaction_type='follow_up_scheduled',
                        summary=f"Voice follow-up: {msg_ctx[:100]}" if msg_ctx else "Voice follow-up",
                        follow_up_date=parsed_date,
                        follow_up_time=parsed_time,
                        created_by_agent_id=created_by
                    )

                # Cross-agent notification
                if _is_admin and target_agent_id != agent['agent_id']:
                    try:
                        target_agent = await db.get_agent_by_id(target_agent_id)
                        if target_agent and target_agent.get('telegram_id'):
                            admin_name = agent.get('name', 'Admin')
                            nlang = target_agent.get('lang', 'en')
                            ntxt = (f"📋 *{admin_name} {'ने फॉलो-अप बनाया' if nlang == 'hi' else 'created a follow-up'}*\n\n"
                                    f"👤 {'लीड' if nlang == 'hi' else 'Lead'}: {lead_name_ctx}\n"
                                    f"📅 {'तारीख' if nlang == 'hi' else 'Date'}: {parsed_date}\n"
                                    f"{'⏰ ' + parsed_time if parsed_time else ''}\n"
                                    f"📝 {msg_ctx[:100] if msg_ctx else '—'}")
                            import biz_reminders as rem
                            await rem._send_telegram(target_agent['telegram_id'], ntxt)
                    except Exception as e:
                        logger.warning("Multi-turn followup notify error: %s", e)

                # Build time display
                hi = lang == 'hi'
                time_display = ""
                if parsed_time:
                    try:
                        t = datetime.strptime(parsed_time, '%H:%M')
                        time_display = f"\n⏰ {t.strftime('%I:%M %p')} IST"
                        time_display += f"\n🔔 {'30 मिनट पहले रिमाइंडर आएगा' if hi else '30-min reminder will be sent'}"
                    except ValueError:
                        pass
                assigned_note = ""
                if _is_admin and target_agent_id != agent['agent_id']:
                    tgt_name = (await db.get_agent_by_id(target_agent_id) or {}).get('name', '')
                    assigned_note = f"\n👨‍💼 {'एजेंट को असाइन' if hi else 'Assigned to'}: {h(tgt_name)}" if tgt_name else ""

                await processing_msg.edit_text(
                    f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
                    f"{'✏️' if is_update else '✅'} {'टास्क अपडेट किया' if is_update and hi else 'Task updated' if is_update else 'टास्क शेड्यूल किया' if hi else 'Task scheduled'}!\n"
                    f"👤 <b>{h(lead_name_ctx)}</b> (#{lead_id})\n"
                    f"📅 {h(parsed_date)}{time_display}{assigned_note}\n"
                    f"📝 {h(msg_ctx[:200]) if msg_ctx else '—'}",
                    parse_mode=ParseMode.HTML)
                return
            # Date still not found — ask again
            hi = lang == 'hi'
            await processing_msg.edit_text(
                f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
                f"❓ {'तारीख समझ नहीं आई। कृपया फिर से बताएं' if hi else 'Could not understand the date. Please try again'}\n"
                f"{'उदा: कल, 25 मार्च, अगले सोमवार' if hi else 'e.g. tomorrow, March 25, next Monday'}",
                parse_mode=ParseMode.HTML)
            return

        if pending == 'calc_compute':
            # Multi-turn calculator — process voice param input
            await _voice_calc_multiturn(processing_msg, voice_ctx, transcript,
                                        data, agent, lang, context)
            return

    # ── Check if user is confirming a pending voice action ────────────
    pending_voice = context.user_data.get('voice_data')
    if pending_voice and transcript:
        # Detect affirmative/confirm intent from transcript
        t_lower = transcript.lower().strip()
        _confirm_phrases = {
            'yes', 'yeah', 'yep', 'ok', 'okay', 'confirm', 'create', 'save',
            'haan', 'ha', 'haa', 'ji', 'ji haan', 'ban do', 'bana do',
            'kar do', 'karo', 'create karo', 'yes create', 'create lead',
            'lead banao', 'lead bana do', 'yes please', 'go ahead',
            'yes create lead', 'theek hai', 'thik hai', 'chal', 'done',
            'bilkul', 'zaroor', 'sahi hai', 'correct', 'right', 'sure',
        }
        _cancel_phrases = {
            'no', 'nah', 'nahi', 'cancel', 'mat karo', 'nope', 'stop',
            'discard', 'hatao', 'band karo', 'ruk', 'delete', 'wrong',
        }
        # Check if transcript matches a confirm phrase (exact or starts with)
        is_confirm = (t_lower in _confirm_phrases or
                      any(t_lower.startswith(p + ' ') for p in ('yes', 'haan', 'ok', 'confirm', 'create', 'ji', 'sure'))
                      or intent == 'confirm_action')
        # Also treat as confirmation when Gemini re-classifies as same intent
        # (e.g. "haan ye lead bana do" → create_lead) and pending has same intent
        pending_intent = pending_voice.get('intent', '')
        if not is_confirm and intent == pending_intent and pending_intent in ('create_lead', 'update_stage'):
            # Voice said something matching pending intent → treat as confirm
            is_confirm = True
        is_cancel = (t_lower in _cancel_phrases or
                     any(t_lower.startswith(p + ' ') for p in ('no', 'nahi', 'cancel', 'mat')))
        if is_cancel:
            context.user_data.pop('voice_data', None)
            context.user_data.pop('voice_duration', None)
            hi = lang == 'hi'
            await processing_msg.edit_text(
                f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
                f"{'❌ रद्द किया गया।' if hi else '❌ Cancelled.'}",
                parse_mode=ParseMode.HTML)
            return
        if is_confirm:
            if pending_intent == 'create_lead':
                # Auto-confirm: create the lead from pending data
                voice_data = context.user_data.pop('voice_data', None)
                voice_duration = context.user_data.pop('voice_duration', 0)
                if voice_data:
                    name = voice_data.get('name') or 'Unknown Lead'
                    phone = voice_data.get('phone')
                    if phone:
                        phone = _valid_phone(phone)
                    need_type = voice_data.get('need_type') or 'general'
                    city = voice_data.get('city')
                    notes = voice_data.get('notes') or ''
                    budget = voice_data.get('budget')
                    follow_up = voice_data.get('follow_up')

                    lead_id = await db.add_lead(
                        agent_id=agent['agent_id'],
                        name=name, phone=phone, city=city,
                        need_type=need_type, notes=notes,
                        premium_budget=float(budget) if budget else None,
                        source="voice"
                    )
                    try:
                        await db.mark_lead_dpdp_consent(lead_id)
                    except Exception:
                        pass

                    followup_msg = ""
                    if follow_up:
                        try:
                            fu_date = datetime.strptime(follow_up, '%Y-%m-%d')
                            await db.add_reminder(
                                agent_id=agent['agent_id'],
                                reminder_type='follow_up',
                                due_date=fu_date.strftime('%Y-%m-%d'),
                                message=f"Follow up with {name}",
                                lead_id=lead_id
                            )
                            followup_msg = "\n📅 " + (f"रिमाइंडर: {fu_date.strftime('%d %b %Y')}"
                                                      if lang == 'hi'
                                                      else f"Reminder set: {fu_date.strftime('%d %b %Y')}")
                        except ValueError:
                            pass

                    await db.log_interaction(
                        lead_id=lead_id,
                        agent_id=agent['agent_id'],
                        interaction_type='voice_note',
                        summary=f"Lead created via voice confirm: {notes[:100]}"
                    )

                    hi = lang == 'hi'
                    created_title = "✅ <b>वॉइस से लीड बनी!</b>" if hi else "✅ <b>Lead Created via Voice!</b>"
                    await processing_msg.edit_text(
                        f"🎙️ <i>{h(transcript[:100])}</i>\n\n"
                        f"{created_title}\n\n"
                        f"🆔 Lead #{lead_id}\n"
                        f"👤 {h(name)}\n"
                        f"📱 {h(phone or 'N/A')}\n"
                        f"🏥 {h(need_type)}\n"
                        f"🏙️ {h(city or 'N/A')}"
                        f"{followup_msg}\n\n"
                        f"/lead {lead_id}",
                        parse_mode=ParseMode.HTML)
                    return
            elif pending_intent == 'update_stage':
                voice_data = context.user_data.pop('voice_data', None)
                context.user_data.pop('voice_duration', None)
                if voice_data:
                    lead_id = voice_data.get('lead_id')
                    new_stage = voice_data.get('new_stage')
                    lead = await db.get_lead(lead_id)
                    if lead and lead['agent_id'] == agent['agent_id']:
                        old_stage = lead.get('stage', 'prospect')
                        success = await db.update_lead_stage(lead_id, new_stage)
                        if success:
                            await processing_msg.edit_text(
                                f"🎙️ <i>{h(transcript[:100])}</i>\n\n"
                                + i18n.t(lang, "voice_stage_updated",
                                         name=h(lead['name']),
                                         lead_id=lead_id,
                                         old_stage=h(old_stage),
                                         new_stage=h(new_stage)),
                                parse_mode=ParseMode.HTML)
                            _track_voice_context(context, intent='update_stage',
                                                 lead_id=lead_id, lead_name=lead['name'])
                            if new_stage == 'closed_won':
                                import biz_reminders as _rem
                                asyncio.create_task(_rem.run_deal_won_celebration(
                                    agent_id=agent['agent_id'],
                                    lead_name=lead['name'],
                                    premium=lead.get('premium_budget', 0) or 0))
                            return

    # ── Confidence-based smart fallback ───────────────────────────────
    confidence = data.get('confidence', 'high')
    if confidence == 'low' and intent not in ('general', 'confirm_action'):
        hi = lang == 'hi'
        last_lead = context.user_data.get('last_lead')
        # Build contextual suggestion buttons
        buttons = []
        _intent_labels = {
            'create_lead': '➕ Create Lead' if not hi else '➕ लीड बनाएं',
            'edit_lead': '📝 Edit Lead' if not hi else '📝 लीड एडिट',
            'log_meeting': '📋 Log Meeting' if not hi else '📋 मीटिंग लॉग',
            'add_note': '📝 Add Note' if not hi else '📝 नोट जोड़ें',
            'setup_followup': '📅 Follow-up' if not hi else '📅 फॉलो-अप',
            'send_whatsapp': '📱 WhatsApp' if not hi else '📱 व्हाट्सएप',
            'send_greeting': '🎉 Greeting' if not hi else '🎉 ग्रीटिंग',
            'update_stage': '🔄 Update Stage' if not hi else '🔄 स्टेज बदलें',
            'open_calculator': '🧮 Calculator' if not hi else '🧮 कैलकुलेटर',
            'send_calc_result': '📤 Send Result' if not hi else '📤 रिज़ल्ट भेजें',
            'list_leads': '📋 My Leads' if not hi else '📋 मेरी लीड्स',
            'show_dashboard': '📊 Dashboard' if not hi else '📊 डैशबोर्ड',
            'ask_ai': '🤖 Ask AI' if not hi else '🤖 AI से पूछें',
        }
        # First button: the AI's best guess
        if intent in _intent_labels:
            label = _intent_labels[intent]
            if last_lead and intent in ('edit_lead', 'add_note', 'send_whatsapp', 'setup_followup', 'log_meeting', 'update_stage', 'send_greeting'):
                label += f" ({last_lead.get('name', '')[:15]})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"vc_go_{intent}")])
        # Add 2-3 other likely intents based on context
        _related = {
            'edit_lead': ['add_note', 'send_whatsapp', 'list_leads'],
            'add_note': ['edit_lead', 'setup_followup', 'list_leads'],
            'send_whatsapp': ['send_greeting', 'send_calc_result', 'edit_lead'],
            'send_calc_result': ['send_whatsapp', 'open_calculator', 'list_leads'],
            'log_meeting': ['setup_followup', 'add_note', 'update_stage'],
            'setup_followup': ['log_meeting', 'add_note', 'list_leads'],
            'create_lead': ['list_leads', 'edit_lead', 'ask_ai'],
            'update_stage': ['log_meeting', 'add_note', 'setup_followup'],
            'open_calculator': ['send_calc_result', 'list_leads', 'ask_ai'],
        }
        for alt_intent in _related.get(intent, ['list_leads', 'open_calculator', 'ask_ai'])[:2]:
            if alt_intent in _intent_labels and alt_intent != intent:
                buttons.append([InlineKeyboardButton(
                    _intent_labels[alt_intent],
                    callback_data=f"vc_go_{alt_intent}")])
        buttons.append([InlineKeyboardButton(
            "🔄 Try Again" if not hi else "🔄 फिर से बोलें",
            callback_data="vc_dismiss")])
        # Stash data so the chosen button can resume
        context.user_data['vc_pending'] = {
            'data': data, 'agent': agent, 'lang': lang,
            'duration': duration, 'ts': time.time()
        }
        await processing_msg.edit_text(
            f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
            f"{'🤔 मैं पूरी तरह समझ नहीं पाया। क्या आप ये करना चाहते हैं?' if hi else '🤔 Not fully sure. Did you mean?'}",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML)
        return

    # ── Route by intent ───────────────────────────────────────────────
    if intent == 'create_lead':
        await _voice_handle_create_lead(
            processing_msg, data, agent, lang, duration, context)
    elif intent == 'log_meeting':
        await _voice_handle_log_meeting(
            processing_msg, data, agent, lang, context)
    elif intent == 'update_stage':
        await _voice_handle_update_stage(
            processing_msg, data, agent, lang, context)
    elif intent == 'create_reminder':
        await _voice_handle_create_reminder(
            processing_msg, data, agent, lang)
    elif intent == 'add_note':
        await _voice_handle_add_note(
            processing_msg, data, agent, lang, context)
    elif intent == 'list_leads':
        await _voice_handle_list_leads(
            processing_msg, data, agent, lang)
    elif intent == 'show_pipeline':
        await _voice_handle_show_pipeline(
            processing_msg, data, agent, lang)
    elif intent == 'show_dashboard':
        await _voice_handle_show_dashboard(
            processing_msg, data, agent, lang)
    elif intent == 'show_renewals':
        await _voice_handle_show_renewals(
            processing_msg, data, agent, lang)
    elif intent == 'show_today':
        await _voice_handle_show_today(
            processing_msg, data, agent, lang)
    elif intent == 'setup_followup':
        await _voice_handle_setup_followup(
            processing_msg, data, agent, lang, context)
    elif intent == 'send_whatsapp':
        await _voice_handle_send_whatsapp(
            processing_msg, data, agent, lang, context)
    elif intent == 'send_greeting':
        await _voice_handle_send_greeting(
            processing_msg, data, agent, lang)
    elif intent == 'edit_lead':
        await _voice_handle_edit_lead(
            processing_msg, data, agent, lang, context)
    elif intent == 'ask_ai':
        await _voice_handle_ask_ai(
            processing_msg, data, agent, lang)
    elif intent == 'ai_lead_score':
        await _voice_handle_ai_lead_score(
            processing_msg, data, agent, lang)
    elif intent == 'ai_pitch':
        await _voice_handle_ai_tool(
            processing_msg, data, agent, lang, 'pitch')
    elif intent == 'ai_followup_suggest':
        await _voice_handle_ai_tool(
            processing_msg, data, agent, lang, 'followup')
    elif intent == 'ai_recommend':
        await _voice_handle_ai_tool(
            processing_msg, data, agent, lang, 'recommend')
    elif intent == 'open_calculator':
        await _voice_handle_open_calculator(
            processing_msg, data, agent, lang)
    elif intent == 'select_calculator':
        await _voice_handle_select_calculator(
            processing_msg, data, agent, lang)
    elif intent == 'calc_compute':
        await _voice_handle_calc_compute(
            processing_msg, data, agent, lang, context)
    elif intent == 'send_calc_result':
        await _voice_handle_send_calc_result(
            processing_msg, data, agent, lang, context)
    elif intent == 'show_team':
        await _voice_handle_show_team(
            processing_msg, data, agent, lang)
    elif intent == 'show_plans':
        await _voice_handle_show_plans(
            processing_msg, data, agent, lang)
    elif intent == 'show_settings':
        await _voice_handle_show_settings(
            processing_msg, data, agent, lang)
    elif intent == 'sa_panel':
        await _voice_handle_sa_panel(
            processing_msg, data, agent, lang)
    elif intent == 'log_payment':
        await _voice_handle_log_payment(
            processing_msg, data, agent, lang, context)
    elif intent == 'log_call':
        await _voice_handle_log_call(
            processing_msg, data, agent, lang, context)
    elif intent == 'add_policy':
        await _voice_handle_add_policy(
            processing_msg, data, agent, lang, context)
    elif intent == 'schedule_meeting':
        await _voice_handle_schedule_meeting(
            processing_msg, data, agent, lang, context)
    elif intent == 'mark_renewal_done':
        await _voice_handle_mark_renewal_done(
            processing_msg, data, agent, lang, context)
    elif intent == 'log_claim':
        await _voice_handle_log_claim(
            processing_msg, data, agent, lang, context)
    elif intent == 'confirm_action':
        # AI detected this is a confirmation — check for pending voice data
        pending_voice = context.user_data.get('voice_data')
        if pending_voice:
            # Simulate the confirm button press
            voice_data = context.user_data.pop('voice_data', None)
            voice_duration = context.user_data.pop('voice_duration', 0)
            pending_intent = voice_data.get('intent', '') if voice_data else ''
            if pending_intent == 'create_lead' and voice_data:
                name = voice_data.get('name') or 'Unknown Lead'
                phone = voice_data.get('phone')
                if phone:
                    phone = _valid_phone(phone)
                lead_id = await db.add_lead(
                    agent_id=agent['agent_id'],
                    name=name, phone=phone,
                    city=voice_data.get('city'),
                    need_type=voice_data.get('need_type') or 'general',
                    notes=voice_data.get('notes') or '',
                    premium_budget=float(voice_data['budget']) if voice_data.get('budget') else None,
                    source="voice"
                )
                try:
                    await db.mark_lead_dpdp_consent(lead_id)
                except Exception:
                    pass
                hi = lang == 'hi'
                await processing_msg.edit_text(
                    f"🎙️ <i>{h(transcript[:100])}</i>\n\n"
                    f"{'✅ <b>वॉइस से लीड बनी!</b>' if hi else '✅ <b>Lead Created via Voice!</b>'}\n\n"
                    f"🆔 Lead #{lead_id}\n👤 {h(name)}\n📱 {h(phone or 'N/A')}\n\n"
                    f"/lead {lead_id}",
                    parse_mode=ParseMode.HTML)
            else:
                hi = lang == 'hi'
                await processing_msg.edit_text(
                    f"🎙️ <i>{h(transcript[:100])}</i>\n\n"
                    f"{'⚠️ कोई पेंडिंग एक्शन नहीं मिली।' if hi else '⚠️ No pending action to confirm.'}",
                    parse_mode=ParseMode.HTML)
        else:
            hi = lang == 'hi'
            await processing_msg.edit_text(
                f"🎙️ <i>{h(transcript[:100])}</i>\n\n"
                f"{'⚠️ कोई पेंडिंग एक्शन नहीं है।' if hi else '⚠️ Nothing pending to confirm. Try a new action!'}",
                parse_mode=ParseMode.HTML)
    else:
        # General / unclear intent — show transcript + suggestions
        await _voice_handle_general(
            processing_msg, data, agent, lang, duration, context)


# ── Intent: CREATE LEAD ───────────────────────────────────────────────────
async def _voice_handle_create_lead(processing_msg, data, agent, lang,
                                     duration, context):
    """Handle voice intent: create a new lead."""
    context.user_data['voice_data'] = data
    context.user_data['voice_duration'] = duration

    transcript = data.get('transcript', 'N/A')
    name = data.get('name') or ('पहचान नहीं हुआ' if lang == 'hi' else 'Not detected')
    phone = data.get('phone') or ('पहचान नहीं हुआ' if lang == 'hi' else 'Not detected')
    need = data.get('need_type') or ('पहचान नहीं हुआ' if lang == 'hi' else 'Not detected')
    city = data.get('city') or ('पहचान नहीं हुआ' if lang == 'hi' else 'Not detected')
    budget = data.get('budget')
    follow_up = data.get('follow_up') or ('सेट नहीं' if lang == 'hi' else 'Not set')
    notes = data.get('notes') or 'None'
    nd = 'पहचान नहीं हुआ' if lang == 'hi' else 'Not detected'
    budget_str = f"₹{budget:,.0f}/mo" if budget else ('नहीं बताया' if lang == 'hi' else 'Not mentioned')

    missing = []
    if name == nd:
        missing.append("👤 " + ("नाम" if lang == 'hi' else "Name"))
    if phone == nd:
        missing.append("📱 " + ("फ़ोन" if lang == 'hi' else "Phone"))
    if need == nd:
        missing.append("🏥 " + ("ज़रूरत" if lang == 'hi' else "Need Type"))

    missing_warning = ""
    if missing:
        missing_warning = "\n⚠️ <b>" + ("कुछ जानकारी मिली नहीं:" if lang == 'hi' else "Missing Details:") + "</b> " + ", ".join(missing) + "\n"
        if name == nd:
            missing_warning += "\n<i>💡 " + ("नाम ज़रूरी है। 'Fill' दबाकर जोड़ें।" if lang == 'hi' else "Name is required. Tap 'Fill' to add.") + "</i>\n"

    title = "🎙️ <b>वॉइस एक्शन — नई लीड</b>" if lang == 'hi' else "🎙️ <b>Voice Action — New Lead</b>"
    create_q = "लीड बनाएँ?" if lang == 'hi' else "Create this lead?"

    msg = (
        f"{title}\n━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 <b>{'ट्रांसक्रिप्ट' if lang == 'hi' else 'Transcript'}:</b>\n<i>{h(transcript[:300])}</i>\n\n"
        f"👤 <b>{'नाम' if lang == 'hi' else 'Name'}:</b> {h(name)}\n"
        f"📱 <b>{'फ़ोन' if lang == 'hi' else 'Phone'}:</b> {h(phone)}\n"
        f"🏥 <b>{'ज़रूरत' if lang == 'hi' else 'Need'}:</b> {h(need)}\n"
        f"🏙️ <b>{'शहर' if lang == 'hi' else 'City'}:</b> {h(city)}\n"
        f"💰 <b>{'बजट' if lang == 'hi' else 'Budget'}:</b> {budget_str}\n"
        f"📅 <b>{'फ़ॉलो-अप' if lang == 'hi' else 'Follow-up'}:</b> {h(follow_up)}\n"
        f"📋 <b>{'नोट्स' if lang == 'hi' else 'Notes'}:</b> {h(notes[:200])}\n"
        f"{missing_warning}\n━━━━━━━━━━━━━━━━━━\n{create_q}"
    )

    kb = []
    if name == nd:
        kb.append([InlineKeyboardButton(
            "✏️ " + ("जानकारी भरें" if lang == 'hi' else "Fill Missing"),
            callback_data="voice_fill")])
        kb.append([InlineKeyboardButton(
            "✅ " + ("फिर भी बनाएँ" if lang == 'hi' else "Create Anyway"),
            callback_data="voice_confirm"),
                   InlineKeyboardButton(
            "❌ " + ("हटाएँ" if lang == 'hi' else "Discard"),
            callback_data="voice_discard")])
    else:
        kb.append([InlineKeyboardButton(
            "✅ " + ("लीड बनाएँ" if lang == 'hi' else "Create Lead"),
            callback_data="voice_confirm"),
                   InlineKeyboardButton(
            "❌ " + ("हटाएँ" if lang == 'hi' else "Discard"),
            callback_data="voice_discard")])
        if missing:
            kb.insert(0, [InlineKeyboardButton(
                "✏️ " + ("जानकारी भरें" if lang == 'hi' else "Fill Missing"),
                callback_data="voice_fill")])

    await processing_msg.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML)


# ── Intent: LOG MEETING ───────────────────────────────────────────────────
async def _voice_handle_log_meeting(processing_msg, data, agent, lang, context=None):
    """Handle voice intent: log a meeting/interaction with a lead."""
    lead_name = data.get('lead_name')
    lead_phone = data.get('lead_phone')
    summary = data.get('meeting_summary') or data.get('notes') or data.get('transcript', '')[:200]
    channel = data.get('meeting_channel') or 'in_person'
    follow_up = data.get('follow_up')
    transcript = data.get('transcript', '')

    # Find the lead (admin: search tenant-wide)
    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        # Lead not found — show transcript and suggest creating
        not_found = ("⚠️ लीड नहीं मिली" if lang == 'hi' else "⚠️ Lead not found")
        suggest = ("लीड बनाने के लिए 'Create Lead' दबाएँ" if lang == 'hi'
                   else "Tap 'Create Lead' to create this as a new lead")
        msg = (
            f"🎙️ <b>{'वॉइस — मीटिंग लॉग' if lang == 'hi' else 'Voice — Meeting Log'}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 <i>{h(transcript[:300])}</i>\n\n"
            f"{not_found}: <b>{h(lead_name or '?')}</b>\n"
            f"💡 {suggest}"
        )
        kb = [[InlineKeyboardButton(
            "➕ " + ("लीड बनाएँ" if lang == 'hi' else "Create Lead"),
            callback_data="voice_convert_lead"),
               InlineKeyboardButton(
            "❌ " + ("हटाएँ" if lang == 'hi' else "Discard"),
            callback_data="voice_discard")]]
        await processing_msg.edit_text(
            msg, reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML)
        return

    # Log the interaction
    followup_msg = ""
    if follow_up:
        try:
            fu_date = datetime.strptime(follow_up, '%Y-%m-%d')
            await db.add_reminder(
                agent_id=agent['agent_id'],
                reminder_type='follow_up',
                due_date=fu_date.strftime('%Y-%m-%d'),
                message=f"Follow up with {lead['name']}",
                lead_id=lead['lead_id']
            )
            followup_msg = "📅 " + (f"रिमाइंडर: {fu_date.strftime('%d %b %Y')}"
                                     if lang == 'hi'
                                     else f"Reminder set: {fu_date.strftime('%d %b %Y')}")
        except ValueError:
            pass

    await db.log_interaction(
        lead_id=lead['lead_id'],
        agent_id=agent['agent_id'],
        interaction_type='meeting',
        channel=channel,
        summary=summary[:500],
        follow_up_date=follow_up
    )

    await processing_msg.edit_text(
        i18n.t(lang, "voice_meeting_logged",
               name=h(lead['name']),
               lead_id=lead['lead_id'],
               summary=h(summary[:300]),
               followup=followup_msg),
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='log_meeting', lead_id=lead['lead_id'], lead_name=lead['name'])
    # Post-action suggestion
    import biz_reminders as _rem
    asyncio.create_task(_rem.run_smart_post_action_suggestion(
        agent_telegram_id=agent.get('telegram_id', ''),
        action='log_meeting',
        lead_name=lead['name'],
        lead_id=lead['lead_id'],
        lang=lang))


# ── Intent: UPDATE STAGE ──────────────────────────────────────────────────
async def _voice_handle_update_stage(processing_msg, data, agent, lang, context=None):
    """Handle voice intent: update a lead's pipeline stage."""
    lead_name = data.get('lead_name')
    lead_phone = data.get('lead_phone')
    new_stage = data.get('new_stage')
    transcript = data.get('transcript', '')

    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_lead_not_found"), parse_mode=ParseMode.HTML)
        return

    valid_stages = ['prospect', 'contacted', 'pitched', 'proposal_sent',
                    'negotiation', 'closed_won', 'closed_lost']
    if not new_stage or new_stage not in valid_stages:
        # Show stage picker
        title = "🎙️ " + ("कौन सा स्टेज?" if lang == 'hi' else "Which stage?")
        kb = []
        row = []
        stage_labels = {
            'prospect': '🆕 Prospect', 'contacted': '📞 Contacted',
            'pitched': '💡 Pitched', 'proposal_sent': '📄 Proposal Sent',
            'negotiation': '🤝 Negotiation', 'closed_won': '✅ Won',
            'closed_lost': '❌ Lost',
        }
        for stg, label in stage_labels.items():
            row.append(InlineKeyboardButton(label,
                       callback_data=f"vstg_{lead['lead_id']}_{stg}"))
            if len(row) >= 2:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        await processing_msg.edit_text(
            f"{title}\n👤 <b>{h(lead['name'])}</b>\n\n"
            f"📝 <i>{h(transcript[:200])}</i>",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML)
        return

    old_stage = lead.get('stage', 'prospect')
    if old_stage == new_stage:
        hi = lang == 'hi'
        await processing_msg.edit_text(
            f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
            f"ℹ️ <b>{h(lead['name'])}</b> {'पहले से' if hi else 'is already at'} "
            f"<b>{h(new_stage)}</b> {'स्टेज पर है' if hi else 'stage'}.",
            parse_mode=ParseMode.HTML)
        return

    # Store pending stage change for voice/text confirmation
    context.user_data['voice_data'] = {
        'intent': 'update_stage',
        'lead_id': lead['lead_id'],
        'lead_name': lead['name'],
        'old_stage': old_stage,
        'new_stage': new_stage,
    }
    hi = lang == 'hi'
    _stage_emoji = {'prospect':'🆕','contacted':'📞','pitched':'💡',
                    'proposal_sent':'📄','negotiation':'🤝','closed_won':'✅','closed_lost':'❌'}
    kb = [
        [InlineKeyboardButton(
            f"✅ {'हाँ, बदलो' if hi else 'Yes, update stage'}",
            callback_data="voice_confirm")],
        [InlineKeyboardButton(
            f"❌ {'नहीं, रहने दो' if hi else 'No, cancel'}",
            callback_data="voice_discard")],
    ]
    await processing_msg.edit_text(
        f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
        f"{'क्या मैं स्टेज बदलूँ?' if hi else 'Should I update the stage?'}\n\n"
        f"👤 <b>{h(lead['name'])}</b>\n"
        f"{_stage_emoji.get(old_stage,'')} {h(old_stage)} → "
        f"{_stage_emoji.get(new_stage,'')} <b>{h(new_stage)}</b>\n\n"
        f"<i>{'हाँ बोलें या बटन दबाएं' if hi else 'Say yes or tap the button'}</i>",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML)


# ── Intent: CREATE REMINDER ───────────────────────────────────────────────
async def _voice_handle_create_reminder(processing_msg, data, agent, lang):
    """Handle voice intent: create a reminder."""
    message = data.get('reminder_message') or data.get('notes') or 'Reminder'
    due_date = data.get('reminder_date') or data.get('follow_up')
    lead_name = data.get('lead_name')
    lead_phone = data.get('lead_phone')

    # Try to find associated lead
    lead = None
    lead_info = ""
    if lead_name or lead_phone:
        _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
        lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
        if lead:
            lead_info = "👤 " + ("लीड" if lang == 'hi' else "Lead") + f": <b>{h(lead['name'])}</b> (#{lead['lead_id']})\n"

    if not due_date:
        # Default to tomorrow
        due_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        fu_date = datetime.strptime(due_date, '%Y-%m-%d')
    except ValueError:
        fu_date = datetime.now() + timedelta(days=1)
        due_date = fu_date.strftime('%Y-%m-%d')

    reminder_id = await db.add_reminder(
        agent_id=agent['agent_id'],
        reminder_type='follow_up',
        due_date=due_date,
        message=message[:500],
        lead_id=lead['lead_id'] if lead else None
    )

    # Also log as interaction for dashboard visibility (cross-channel sync)
    await db.log_interaction(
        lead_id=lead['lead_id'] if lead else 0,
        agent_id=agent['agent_id'],
        interaction_type='follow_up',
        summary=message[:500],
        follow_up_date=due_date,
    )

    await processing_msg.edit_text(
        i18n.t(lang, "voice_reminder_set",
               message=h(message[:200]),
               due_date=fu_date.strftime('%d %b %Y'),
               lead_info=lead_info),
        parse_mode=ParseMode.HTML)


# ── Intent: ADD NOTE ──────────────────────────────────────────────────────
async def _voice_handle_add_note(processing_msg, data, agent, lang, context=None):
    """Handle voice intent: add a note to an existing lead."""
    lead_name = data.get('lead_name')
    lead_phone = data.get('lead_phone')
    note_text = data.get('note_text') or data.get('notes') or data.get('transcript', '')[:300]

    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_lead_not_found"), parse_mode=ParseMode.HTML)
        return

    # Append to existing notes
    existing_notes = lead.get('notes') or ''
    timestamp = datetime.now().strftime('%d/%m %H:%M')
    new_notes = f"{existing_notes}\n🎙️ [{timestamp}] {note_text}" if existing_notes else f"🎙️ [{timestamp}] {note_text}"

    await db.update_lead(lead['lead_id'], notes=new_notes.strip()[:2000])

    await db.log_interaction(
        lead_id=lead['lead_id'],
        agent_id=agent['agent_id'],
        interaction_type='note',
        summary=f"Voice note: {note_text[:100]}"
    )

    await processing_msg.edit_text(
        i18n.t(lang, "voice_note_added",
               name=h(lead['name']),
               lead_id=lead['lead_id'],
               note=h(note_text[:300])),
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='add_note', lead_id=lead['lead_id'], lead_name=lead['name'])


# ── Intents: LOG PAYMENT / LOG CALL / ADD POLICY / SCHEDULE MEETING / MARK RENEWAL DONE / LOG CLAIM ──

async def _voice_handle_log_payment(processing_msg, data, agent, lang, context=None):
    """Voice: record a premium payment received from a lead."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name') or data.get('name')
    lead_phone = data.get('lead_phone') or data.get('phone')
    raw_amount = data.get('amount')
    try:
        amount = float(raw_amount) if raw_amount not in (None, "") else None
    except (TypeError, ValueError):
        amount = None
    if amount is None or amount <= 0:
        await processing_msg.edit_text(
            "❌ " + ("राशि नहीं समझ पाया। फिर से बोलें।" if hi else "Couldn't detect a valid amount. Please try again."),
            parse_mode=ParseMode.HTML)
        return
    method = (data.get('payment_method') or 'cash').lower()
    if method not in {'cash', 'upi', 'cheque', 'bank', 'online', 'card'}:
        method = 'cash'
    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_lead_not_found"), parse_mode=ParseMode.HTML)
        return
    extra = (data.get('notes') or '').strip()[:200]
    summary = f"Payment received: ₹{amount:,.0f} via {method}"
    if extra:
        summary += f" — {extra}"
    await db.log_interaction(
        lead_id=lead['lead_id'], agent_id=agent['agent_id'],
        interaction_type='payment', summary=summary)
    await db.log_audit("voice_payment_logged",
                       f"Lead #{lead['lead_id']} payment ₹{amount:.0f} via {method}",
                       tenant_id=agent.get('tenant_id'),
                       agent_id=agent['agent_id'],
                       role=agent.get('role'))
    title = "✅ <b>पेमेंट लॉग किया</b>" if hi else "✅ <b>Payment Logged</b>"
    await processing_msg.edit_text(
        f"{title}\n\n"
        f"👤 {h(lead['name'])} (#{lead['lead_id']})\n"
        f"💰 ₹{amount:,.0f}\n"
        f"💳 {method.upper()}",
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='log_payment', lead_id=lead['lead_id'], lead_name=lead['name'])


async def _voice_handle_log_call(processing_msg, data, agent, lang, context=None):
    """Voice: log a phone call with a lead, optionally with follow-up date."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name') or data.get('name')
    lead_phone = data.get('lead_phone') or data.get('phone')
    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_lead_not_found"), parse_mode=ParseMode.HTML)
        return
    call_summary = (data.get('note_text') or data.get('notes')
                    or data.get('transcript') or '')[:1000]
    if not call_summary:
        call_summary = "Phone call logged via voice"
    fu_date_str = None
    fu = data.get('follow_up')
    if fu:
        try:
            fu_date = datetime.strptime(fu, '%Y-%m-%d')
            fu_date_str = fu_date.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    await db.log_interaction(
        lead_id=lead['lead_id'], agent_id=agent['agent_id'],
        interaction_type='call', summary=call_summary,
        follow_up_date=fu_date_str)
    fu_msg = ""
    if fu_date_str:
        await db.add_reminder(
            agent_id=agent['agent_id'], reminder_type='follow_up',
            due_date=fu_date_str,
            message=f"Follow up call with {lead['name']}",
            lead_id=lead['lead_id'])
        fu_msg = f"\n📅 {'फॉलो-अप' if hi else 'Follow-up'}: {fu_date_str}"
    title = "✅ <b>कॉल लॉग किया</b>" if hi else "✅ <b>Call Logged</b>"
    await processing_msg.edit_text(
        f"{title}\n\n"
        f"👤 {h(lead['name'])} (#{lead['lead_id']})\n"
        f"📞 {h(call_summary[:200])}{fu_msg}",
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='log_call', lead_id=lead['lead_id'], lead_name=lead['name'])


async def _voice_handle_add_policy(processing_msg, data, agent, lang, context=None):
    """Voice: record a sold policy under a lead and mark closed_won."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name') or data.get('name')
    lead_phone = data.get('lead_phone') or data.get('phone')
    insurer = (data.get('insurer') or '').strip()[:100] or None
    plan_name = (data.get('plan_name') or '').strip()[:200] or None
    if not (insurer or plan_name):
        await processing_msg.edit_text(
            "❌ " + ("बीमा कंपनी या प्लान नाम बताएं।" if hi else "Please mention the insurer or plan name."),
            parse_mode=ParseMode.HTML)
        return
    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_lead_not_found"), parse_mode=ParseMode.HTML)
        return
    valid_ptypes = {'health', 'term', 'endowment', 'ulip', 'child', 'retirement',
                    'motor', 'investment', 'nps', 'life'}
    policy_type = data.get('policy_type') or lead.get('need_type') or 'health'
    if policy_type not in valid_ptypes:
        policy_type = 'health'
    valid_modes = {'monthly', 'quarterly', 'half_yearly', 'annual', 'single'}
    premium_mode = data.get('premium_mode') or 'annual'
    if premium_mode not in valid_modes:
        premium_mode = 'annual'
    try:
        sum_insured = float(data['sum_insured']) if data.get('sum_insured') else None
    except (TypeError, ValueError):
        sum_insured = None
    try:
        premium = float(data['premium']) if data.get('premium') else None
    except (TypeError, ValueError):
        premium = None
    policy_number = (data.get('policy_number') or '').strip()[:50] or None
    policy_id = await db.add_policy(
        lead_id=lead['lead_id'], agent_id=agent['agent_id'],
        insurer=insurer, plan_name=plan_name, policy_type=policy_type,
        sum_insured=sum_insured, premium=premium, premium_mode=premium_mode,
        policy_number=policy_number, sold_by_agent=agent['agent_id'],
        policy_status='active', notes='Added via Voice AI')
    old_stage = lead.get('stage', 'prospect')
    if old_stage != 'closed_won':
        await db.update_lead_stage(lead['lead_id'], 'closed_won')
    await db.log_interaction(
        lead_id=lead['lead_id'], agent_id=agent['agent_id'],
        interaction_type='policy_sold',
        summary=f"Policy sold: {insurer or '?'} {plan_name or ''} (₹{premium or 0:.0f}/{premium_mode})")
    await db.log_audit("voice_policy_added",
                       f"Policy #{policy_id} for lead #{lead['lead_id']} via Voice AI",
                       tenant_id=agent.get('tenant_id'),
                       agent_id=agent['agent_id'],
                       role=agent.get('role'))
    details = []
    if insurer: details.append(f"🏢 {h(insurer)}")
    if plan_name: details.append(f"📋 {h(plan_name)}")
    if sum_insured: details.append(f"🛡️ ₹{sum_insured:,.0f}")
    if premium: details.append(f"💰 ₹{premium:,.0f}/{premium_mode}")
    title = "✅ <b>पॉलिसी जोड़ी</b>" if hi else "✅ <b>Policy Added</b>"
    await processing_msg.edit_text(
        f"{title}\n\n"
        f"👤 {h(lead['name'])} (#{lead['lead_id']})\n"
        f"🆔 Policy #{policy_id}\n" +
        "\n".join(details) +
        f"\n📊 Stage → closed_won",
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='add_policy', lead_id=lead['lead_id'], lead_name=lead['name'])
    # Trigger celebration if stage changed
    if old_stage != 'closed_won':
        try:
            import biz_reminders as _rem
            asyncio.create_task(_rem.run_deal_won_celebration(
                agent_id=agent['agent_id'], lead_name=lead['name'],
                premium=premium or 0))
        except Exception:
            pass


async def _voice_handle_schedule_meeting(processing_msg, data, agent, lang, context=None):
    """Voice: schedule a future meeting with a lead."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name') or data.get('name')
    lead_phone = data.get('lead_phone') or data.get('phone')
    m_date_raw = data.get('meeting_date')
    if not m_date_raw:
        await processing_msg.edit_text(
            "❌ " + ("मीटिंग की तारीख बताएं।" if hi else "Please mention the meeting date."),
            parse_mode=ParseMode.HTML)
        return
    try:
        m_date = datetime.strptime(m_date_raw, '%Y-%m-%d')
    except (ValueError, TypeError):
        await processing_msg.edit_text(
            "❌ " + ("अमान्य तारीख फॉर्मेट।" if hi else "Invalid meeting date format."),
            parse_mode=ParseMode.HTML)
        return
    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_lead_not_found"), parse_mode=ParseMode.HTML)
        return
    m_time = (data.get('meeting_time') or '').strip()
    import re as _re
    if m_time and not _re.match(r"^\d{1,2}:\d{2}$", m_time):
        m_time = ''
    location = (data.get('meeting_location') or '').strip()[:200]
    time_part = f" at {m_time}" if m_time else ''
    loc_part = f" — {location}" if location else ''
    msg = f"Meeting with {lead['name']}{time_part}{loc_part}"
    await db.add_reminder(
        agent_id=agent['agent_id'], reminder_type='meeting',
        due_date=m_date.strftime('%Y-%m-%d'),
        message=msg, lead_id=lead['lead_id'])
    await db.log_interaction(
        lead_id=lead['lead_id'], agent_id=agent['agent_id'],
        interaction_type='meeting', summary=msg,
        follow_up_date=m_date.strftime('%Y-%m-%d'))
    title = "✅ <b>मीटिंग शेड्यूल</b>" if hi else "✅ <b>Meeting Scheduled</b>"
    await processing_msg.edit_text(
        f"{title}\n\n"
        f"👤 {h(lead['name'])} (#{lead['lead_id']})\n"
        f"📅 {m_date.strftime('%d %b %Y')}{time_part}"
        + (f"\n📍 {h(location)}" if location else ''),
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='schedule_meeting', lead_id=lead['lead_id'], lead_name=lead['name'])


async def _voice_handle_mark_renewal_done(processing_msg, data, agent, lang, context=None):
    """Voice: mark a policy as renewed (bumps renewal_date by 1 year)."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name') or data.get('name')
    lead_phone = data.get('lead_phone') or data.get('phone')
    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_lead_not_found"), parse_mode=ParseMode.HTML)
        return
    policies = await db.get_policies_by_lead(lead['lead_id'])
    if not policies:
        await processing_msg.edit_text(
            "❌ " + (f"{lead['name']} के लिए कोई पॉलिसी नहीं मिली।" if hi
                    else f"No policies found for {lead['name']}."),
            parse_mode=ParseMode.HTML)
        return
    insurer_q = (data.get('insurer') or '').lower().strip()
    if insurer_q:
        matched = [p for p in policies if insurer_q in (p.get('insurer') or '').lower()]
        policies = matched or policies
    target = policies[0]
    try:
        if target.get('renewal_date'):
            cur = datetime.strptime(target['renewal_date'][:10], '%Y-%m-%d')
        else:
            cur = datetime.now()
        new_renewal = cur.replace(year=cur.year + 1).strftime('%Y-%m-%d')
    except Exception:
        new_renewal = (datetime.now().replace(year=datetime.now().year + 1)).strftime('%Y-%m-%d')
    await db.update_policy(target['policy_id'],
                           renewal_date=new_renewal, status='active')
    await db.log_interaction(
        lead_id=lead['lead_id'], agent_id=agent['agent_id'],
        interaction_type='renewal_done',
        summary=f"Renewal done: {target.get('insurer') or '?'} {target.get('plan_name') or ''} → next renewal {new_renewal}")
    title = "✅ <b>रिन्यूअल पूरा</b>" if hi else "✅ <b>Renewal Done</b>"
    await processing_msg.edit_text(
        f"{title}\n\n"
        f"👤 {h(lead['name'])} (#{lead['lead_id']})\n"
        f"🏢 {h(target.get('insurer') or '?')} {h(target.get('plan_name') or '')}\n"
        f"📅 {'अगला रिन्यूअल' if hi else 'Next renewal'}: {new_renewal}",
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='mark_renewal_done', lead_id=lead['lead_id'], lead_name=lead['name'])


async def _voice_handle_log_claim(processing_msg, data, agent, lang, context=None):
    """Voice: record a new claim filed by a lead."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name') or data.get('name')
    lead_phone = data.get('lead_phone') or data.get('phone')
    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            i18n.t(lang, "voice_lead_not_found"), parse_mode=ParseMode.HTML)
        return
    claim_type = (data.get('claim_type') or 'other').lower()
    if claim_type not in {'health', 'motor', 'life', 'accident', 'other'}:
        claim_type = 'other'
    try:
        claim_amount = float(data['claim_amount']) if data.get('claim_amount') else None
    except (TypeError, ValueError):
        claim_amount = None
    incident_date = None
    if data.get('incident_date'):
        try:
            incident_date = datetime.strptime(data['incident_date'], '%Y-%m-%d').strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    hospital = (data.get('hospital_name') or '').strip()[:200] or None
    description = (data.get('notes') or data.get('transcript') or '')[:1000] or None
    policies = await db.get_policies_by_lead(lead['lead_id'])
    policy_id = policies[0]['policy_id'] if policies else None
    claim_id = await db.add_claim(
        agent_id=agent['agent_id'], lead_id=lead['lead_id'], claim_type=claim_type,
        policy_id=policy_id, claim_amount=claim_amount,
        incident_date=incident_date, description=description,
        hospital_name=hospital, notes='Logged via Voice AI')
    await db.log_interaction(
        lead_id=lead['lead_id'], agent_id=agent['agent_id'],
        interaction_type='claim_filed',
        summary=f"Claim #{claim_id} filed: {claim_type}" +
                (f" ₹{claim_amount:,.0f}" if claim_amount else "") +
                (f" at {hospital}" if hospital else ""))
    await db.log_audit("voice_claim_logged",
                       f"Claim #{claim_id} for lead #{lead['lead_id']} via Voice AI",
                       tenant_id=agent.get('tenant_id'),
                       agent_id=agent['agent_id'],
                       role=agent.get('role'))
    details = [f"🏷️ {claim_type}"]
    if claim_amount: details.append(f"💰 ₹{claim_amount:,.0f}")
    if incident_date: details.append(f"📅 {incident_date}")
    if hospital: details.append(f"🏥 {h(hospital)}")
    title = "✅ <b>क्लेम दर्ज</b>" if hi else "✅ <b>Claim Logged</b>"
    await processing_msg.edit_text(
        f"{title}\n\n"
        f"👤 {h(lead['name'])} (#{lead['lead_id']})\n"
        f"🆔 Claim #{claim_id}\n" +
        "\n".join(details),
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='log_claim', lead_id=lead['lead_id'], lead_name=lead['name'])


# ── Intent: LIST LEADS ───────────────────────────────────────────────────
async def _voice_handle_list_leads(processing_msg, data, agent, lang):
    """Voice: show leads or search by name."""
    hi = lang == 'hi'
    search_query = data.get('search_query') or data.get('lead_name')

    if search_query:
        leads = await db.search_leads(agent['agent_id'], search_query)
        title = f"🔍 {'खोज' if hi else 'Search'}: '{h(search_query)}'"
    else:
        leads = await db.get_leads_by_agent(agent['agent_id'])
        title = "📋 " + ("सभी लीड्स" if hi else "All Leads")

    if not leads:
        no = "कोई लीड नहीं मिली" if hi else "No leads found"
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n{title}\n\n{no}",
            parse_mode=ParseMode.HTML)
        return

    lines = [f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n",
             f"{title} ({len(leads)} {'परिणाम' if hi else 'results'})\n"]
    keyboard = []
    for lead in leads[:15]:
        se = _stage_emoji(lead['stage'])
        lines.append(
            f"{se} <b>#{lead['lead_id']}</b> {h(lead['name'])}\n"
            f"   📱 {h(lead.get('phone', 'N/A'))} | {h(lead.get('need_type', ''))} | {h(lead['stage'])}")
        keyboard.append([InlineKeyboardButton(
            f"👤 #{lead['lead_id']} {lead['name']}",
            callback_data=f"leadview_{lead['lead_id']}")])

    if len(leads) > 15:
        lines.append(f"\n...{'और' if hi else 'and'} {len(leads) - 15} {'और' if hi else 'more'}")

    await processing_msg.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


# ── Intent: SHOW PIPELINE ────────────────────────────────────────────────
async def _voice_handle_show_pipeline(processing_msg, data, agent, lang):
    """Voice: show pipeline summary."""
    hi = lang == 'hi'
    pipeline = await db.get_pipeline_summary(agent['agent_id'])
    stats = await db.get_agent_stats(agent['agent_id'])

    stages = [
        ('🎯', 'संभावित' if hi else 'Prospect', 'prospect'),
        ('📞', 'संपर्क' if hi else 'Contacted', 'contacted'),
        ('📊', 'पिच' if hi else 'Pitched', 'pitched'),
        ('📄', 'प्रस्ताव' if hi else 'Proposal', 'proposal_sent'),
        ('🤝', 'बातचीत' if hi else 'Negotiation', 'negotiation'),
    ]

    lines = [f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n",
             "📊 <b>" + ("पाइपलाइन" if hi else "Sales Pipeline") + "</b>\n━━━━━━━━━━━━━━━━━━\n"]
    total = 0
    for emoji, label, key in stages:
        count = pipeline.get(key, 0)
        total += count
        bar = "█" * min(count, 15) + f" {count}" if count else "░ 0"
        lines.append(f"{emoji} {label}:\n   {bar}\n")

    won = pipeline.get('closed_won', 0)
    lost = pipeline.get('closed_lost', 0)
    lines.append(f"\n✅ {'जीते' if hi else 'Won'}: {won}  |  ❌ {'हारे' if hi else 'Lost'}: {lost}")
    lines.append(f"📋 {'सक्रिय' if hi else 'Active'}: {total}")
    lines.append(f"💰 {'प्रीमियम' if hi else 'Premium'}: ₹{stats.get('total_premium', 0):,.0f}")

    keyboard = [
        [InlineKeyboardButton("📋 " + ("संभावित" if hi else "Prospects"), callback_data="stage_prospect"),
         InlineKeyboardButton("📊 " + ("पिच" if hi else "Pitched"), callback_data="stage_pitched")],
        [InlineKeyboardButton("📄 " + ("प्रस्ताव" if hi else "Proposals"), callback_data="stage_proposal_sent"),
         InlineKeyboardButton("🏆 " + ("जीते" if hi else "Won"), callback_data="stage_closed_won")],
    ]
    await processing_msg.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


# ── Intent: SHOW DASHBOARD ──────────────────────────────────────────────
async def _voice_handle_show_dashboard(processing_msg, data, agent, lang):
    """Voice: show business dashboard stats."""
    hi = lang == 'hi'
    stats = await db.get_agent_stats(agent['agent_id'])
    pipeline = stats.get('pipeline', {})
    followups = await db.get_pending_followups(agent['agent_id'])
    renewals = await db.get_upcoming_renewals(agent['agent_id'], days_ahead=30)

    msg = (
        f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
        f"📈 <b>{'डैशबोर्ड' if hi else 'Dashboard'}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 {h(agent['name'])}\n\n"
        f"📊 <b>{'पाइपलाइन' if hi else 'Pipeline'}:</b>\n"
        f"  🎯 {pipeline.get('prospect', 0)} | 📞 {pipeline.get('contacted', 0)} | "
        f"📊 {pipeline.get('pitched', 0)} | ✅ {pipeline.get('closed_won', 0)}\n\n"
        f"🏆 <b>{'पोर्टफोलियो' if hi else 'Portfolio'}:</b>\n"
        f"  📋 {stats.get('active_policies', 0)} {'पॉलिसी' if hi else 'policies'} | "
        f"💰 ₹{stats.get('total_premium', 0):,.0f}\n\n"
        f"📅 <b>{'आज' if hi else 'Today'}:</b>\n"
        f"  🆕 {stats.get('today_new_leads', 0)} {'नई लीड' if hi else 'new leads'} | "
        f"📞 {stats.get('today_interactions', 0)} {'इंटरैक्शन' if hi else 'interactions'}\n"
        f"  📋 {len(followups)} {'फॉलो-अप' if hi else 'follow-ups'} | "
        f"🔄 {len(renewals)} {'रिन्यूअल' if hi else 'renewals'}\n"
    )
    await processing_msg.edit_text(msg, parse_mode=ParseMode.HTML)


# ── Intent: SHOW RENEWALS ───────────────────────────────────────────────
async def _voice_handle_show_renewals(processing_msg, data, agent, lang):
    """Voice: show upcoming policy renewals."""
    hi = lang == 'hi'
    renewals = await db.get_upcoming_renewals(agent['agent_id'], days_ahead=60)

    if not renewals:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
            f"✅ {'अगले 60 दिनों में कोई रिन्यूअल नहीं' if hi else 'No renewals in next 60 days'}",
            parse_mode=ParseMode.HTML)
        return

    lines = [f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n",
             f"🔄 <b>{'आगामी रिन्यूअल' if hi else 'Upcoming Renewals'}</b>\n━━━━━━━━━━━━━━━━━━\n"]
    for pol in renewals[:10]:
        try:
            ren_dt = datetime.fromisoformat(pol['renewal_date'])
            days = (ren_dt - datetime.now()).days
            urgency = "🔴" if days <= 7 else "🟡" if days <= 30 else "🟢"
        except (ValueError, TypeError):
            days, urgency = "?", "⚪"
        lines.append(
            f"{urgency} <b>{h(pol.get('client_name', 'Client'))}</b>\n"
            f"   📋 {h(pol.get('plan_name', 'N/A'))} | ₹{pol.get('premium', 0):,.0f}\n"
            f"   📅 {h(pol['renewal_date'])} ({days} {'दिन' if hi else 'days'})\n")

    await processing_msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── Intent: SHOW TODAY ───────────────────────────────────────────────────
async def _voice_handle_show_today(processing_msg, data, agent, lang):
    """Voice: show today's agenda — follow-ups, birthdays, tasks."""
    hi = lang == 'hi'
    followups = await db.get_todays_followups(agent['agent_id'])
    birthdays = await db.get_todays_birthdays(agent['agent_id'])
    anniversaries = await db.get_todays_anniversaries(agent['agent_id'])

    _title = "आज का एजेंडा" if hi else "Today's Agenda"
    lines = [f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n",
             f"📅 <b>{_title}</b>\n━━━━━━━━━━━━━━━━━━\n"]

    if followups:
        lines.append(f"📞 <b>{len(followups)} {'फॉलो-अप' if hi else 'Follow-ups'}:</b>")
        for fu in followups[:5]:
            lines.append(f"  • {h(fu.get('lead_name', 'Lead'))} — {h(fu.get('summary', '')[:50])}")
        lines.append("")
    else:
        lines.append(f"📞 {'कोई फॉलो-अप नहीं' if hi else 'No follow-ups today'}\n")

    if birthdays:
        lines.append(f"🎂 <b>{'जन्मदिन' if hi else 'Birthdays'}:</b>")
        for bd in birthdays[:5]:
            lines.append(f"  • {h(bd.get('name', 'Client'))}")
        lines.append("")

    if anniversaries:
        lines.append(f"💍 <b>{'वर्षगांठ' if hi else 'Anniversaries'}:</b>")
        for an in anniversaries[:5]:
            lines.append(f"  • {h(an.get('name', 'Client'))}")
        lines.append("")

    if not followups and not birthdays and not anniversaries:
        lines.append("✅ " + ("कोई टास्क नहीं — आराम करें!" if hi else "All clear — no pending tasks!"))

    await processing_msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── Intent: SETUP FOLLOWUP ──────────────────────────────────────────────
async def _voice_handle_setup_followup(processing_msg, data, agent, lang, context):
    """Voice: schedule a follow-up with a lead (multi-turn capable).
    Supports time-specific follow-ups with 30-min-before reminders."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name')
    lead_phone = data.get('lead_phone')
    reminder_date = data.get('reminder_date') or data.get('follow_up')
    reminder_time = data.get('reminder_time')  # HH:MM in 24hr IST
    reminder_msg = data.get('reminder_message') or data.get('notes') or ''
    # Fallback: extract time from transcript if AI didn't return it
    if not reminder_time and data.get('transcript'):
        reminder_time = _extract_time_from_transcript(data['transcript'])

    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
            f"❌ {'लीड नहीं मिली' if hi else 'Lead not found'}: "
            f"<b>{h(lead_name or 'unknown')}</b>\n\n"
            f"{'पहले /leads से लीड खोजें' if hi else 'Search with /leads first'}",
            parse_mode=ParseMode.HTML)
        return

    if not reminder_date:
        # Multi-turn: store context, ask for date
        context.user_data['voice_context'] = {
            'pending_action': 'setup_followup',
            'lead_id': lead['lead_id'],
            'lead_name': lead['name'],
            'message': reminder_msg,
            'reminder_time': reminder_time,  # Preserve time if mentioned without date
            'awaiting': 'date',
            'created_at': time.time(),
        }
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
            f"📅 {'फॉलो-अप' if hi else 'Follow-up'}: <b>{h(lead['name'])}</b>\n\n"
            f"{'कब करना है? तारीख और समय बताएं (वॉइस या टाइप करें)' if hi else 'When? Send date & time via voice or text'}\n"
            f"{'उदा: कल 4 बजे, अगले सोमवार 10 AM' if hi else 'e.g. tomorrow 4 PM, next Monday 10 AM'}",
            parse_mode=ParseMode.HTML)
        return

    # We have both lead and date — check for existing pending follow-ups (duplicate detection)
    _is_admin = agent.get('role') in ('owner', 'admin')
    existing = await db.get_pending_followups_for_lead(lead['lead_id'])
    is_update = False
    existing_iid = None
    if existing:
        ef = existing[0]
        existing_iid = ef.get('interaction_id')
        is_update = True  # Update existing task instead of creating duplicate

    # Resolve task assignee — who is RESPONSIBLE for this task
    task_assignee_raw = data.get('task_assignee')
    assigned_to_id = None
    assigned_to_name = ""
    target_agent_id = lead.get('agent_id') or agent['agent_id']
    created_by = agent['agent_id'] if _is_admin and target_agent_id != agent['agent_id'] else None

    if task_assignee_raw:
        if task_assignee_raw.lower() == 'self':
            # Assign to the speaker (creator)
            assigned_to_id = agent['agent_id']
            assigned_to_name = agent.get('name', 'Me')
        else:
            # Try to find the assignee by name among tenant agents
            from difflib import SequenceMatcher
            agents_list = await db.get_agents_by_tenant(agent['tenant_id'])
            best_match, best_score = None, 0.0
            for a in agents_list:
                score = SequenceMatcher(None, task_assignee_raw.lower(), a['name'].lower()).ratio()
                if score > best_score:
                    best_match, best_score = a, score
            if best_match and best_score >= 0.5:
                assigned_to_id = best_match['agent_id']
                assigned_to_name = best_match['name']

    if is_update and existing_iid:
        # UPDATE existing task instead of creating duplicate
        await db.update_followup(
            interaction_id=existing_iid,
            follow_up_date=reminder_date,
            follow_up_time=reminder_time,
            summary=f"Voice follow-up: {reminder_msg[:100]}" if reminder_msg else None,
            assigned_to_agent_id=assigned_to_id if assigned_to_id else None
        )
        iid = existing_iid
    else:
        iid = await db.log_interaction(
            lead_id=lead['lead_id'],
            agent_id=target_agent_id,
            interaction_type='follow_up_scheduled',
            summary=f"Voice follow-up: {reminder_msg[:100]}" if reminder_msg else "Voice follow-up scheduled",
            follow_up_date=reminder_date,
            follow_up_time=reminder_time,
            created_by_agent_id=created_by,
            assigned_to_agent_id=assigned_to_id
        )

    # Cross-agent notification: notify the assignee (or lead's agent if no explicit assignee)
    notify_agent_id = assigned_to_id or (target_agent_id if _is_admin and target_agent_id != agent['agent_id'] else None)
    if notify_agent_id and notify_agent_id != agent['agent_id']:
        try:
            notify_agent = await db.get_agent_by_id(notify_agent_id)
            if notify_agent and notify_agent.get('telegram_id'):
                admin_name = agent.get('name', 'Admin')
                nlang = notify_agent.get('lang', 'en')
                if nlang == 'hi':
                    ntxt = (f"📋 *{admin_name} ने आपको टास्क असाइन किया*\n\n"
                            f"👤 लीड: {lead['name']}\n"
                            f"📅 तारीख: {reminder_date}\n"
                            f"{'⏰ समय: ' + reminder_time if reminder_time else ''}\n"
                            f"📝 {reminder_msg[:100] if reminder_msg else '—'}")
                else:
                    ntxt = (f"📋 *{admin_name} assigned you a task*\n\n"
                            f"👤 Lead: {lead['name']}\n"
                            f"📅 Date: {reminder_date}\n"
                            f"{'⏰ Time: ' + reminder_time if reminder_time else ''}\n"
                            f"📝 {reminder_msg[:100] if reminder_msg else '—'}")
                import biz_reminders as rem
                await rem._send_telegram(notify_agent['telegram_id'], ntxt)
        except Exception as e:
            logger.warning("Failed to notify assignee of task: %s", e)

    # Build time display
    time_display = ""
    if reminder_time:
        try:
            t = datetime.strptime(reminder_time, '%H:%M')
            time_display = f"\n⏰ {t.strftime('%I:%M %p')} IST"
            reminder_note = '30 मिनट पहले रिमाइंडर आएगा' if hi else '30-min reminder will be sent'
            time_display += f"\n🔔 {reminder_note}"
        except ValueError:
            pass
    # Show assignee
    assigned_note = ""
    if assigned_to_name:
        lbl = 'टास्क असाइन' if hi else 'Task assigned to'
        assigned_note = f"\n👨‍💼 {lbl}: {h(assigned_to_name)}"
    elif _is_admin and target_agent_id != agent['agent_id']:
        target_name = (await db.get_agent_by_id(target_agent_id) or {}).get('name', '')
        assigned_note = f"\n👨‍💼 {'एजेंट को असाइन' if hi else 'Assigned to'}: {h(target_name)}" if target_name else ""
    await processing_msg.edit_text(
        f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
        f"{'✏️' if is_update else '✅'} {'टास्क अपडेट किया' if is_update and hi else 'Task updated' if is_update else 'टास्क शेड्यूल किया' if hi else 'Task scheduled'}!\n\n"
        f"👤 <b>{h(lead['name'])}</b> (#{lead['lead_id']})\n"
        f"📅 {h(reminder_date)}{time_display}{assigned_note}\n"
        f"📝 {h(reminder_msg[:200]) if reminder_msg else '—'}",
        parse_mode=ParseMode.HTML)
    _track_voice_context(context, intent='setup_followup', lead_id=lead['lead_id'], lead_name=lead['name'])


# ── Intent: SEND WHATSAPP ────────────────────────────────────────────────
async def _voice_handle_send_whatsapp(processing_msg, data, agent, lang, context=None):
    """Voice: send WhatsApp message to a lead."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name')
    lead_phone = data.get('lead_phone')
    wa_message = data.get('wa_message') or data.get('notes')

    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
            f"❌ {'लीड नहीं मिली' if hi else 'Lead not found'}: <b>{h(lead_name or 'unknown')}</b>",
            parse_mode=ParseMode.HTML)
        return

    phone = lead.get('whatsapp') or lead.get('phone')
    if not phone:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
            f"❌ {h(lead['name'])} — {'फोन नंबर नहीं है' if hi else 'no phone number'}",
            parse_mode=ParseMode.HTML)
        return

    if not wa_message:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
            f"❌ {'संदेश नहीं मिला। क्या भेजना है बताएं।' if hi else 'No message found. Please specify what to send.'}",
            parse_mode=ParseMode.HTML)
        return

    result = await wa.send_text(phone, wa_message)
    if result.get('success'):
        await db.log_interaction(
            lead_id=lead['lead_id'], agent_id=agent['agent_id'],
            interaction_type='whatsapp', channel='whatsapp',
            summary=f"Voice WA: {wa_message[:100]}")
        _track_voice_context(context, intent='send_whatsapp', lead_id=lead['lead_id'], lead_name=lead['name'])
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
            f"✅ WhatsApp {'भेजा' if hi else 'sent'}!\n"
            f"👤 {h(lead['name'])} | 📱 {h(phone)}\n"
            f"💬 {h(wa_message[:200])}",
            parse_mode=ParseMode.HTML)
    else:
        await processing_msg.edit_text(
            f"❌ WhatsApp {'भेजने में विफल' if hi else 'send failed'}: "
            f"{h(str(result.get('error', 'Unknown'))[:100])}",
            parse_mode=ParseMode.HTML)


# ── Intent: SEND GREETING ────────────────────────────────────────────────
async def _voice_handle_send_greeting(processing_msg, data, agent, lang):
    """Voice: send greeting (birthday/anniversary/etc.) to a lead."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name')
    lead_phone = data.get('lead_phone')
    greeting_type = data.get('greeting_type', 'thank_you')

    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
            f"❌ {'लीड नहीं मिली' if hi else 'Lead not found'}: <b>{h(lead_name or 'unknown')}</b>",
            parse_mode=ParseMode.HTML)
        return

    # Show greeting type picker for this lead
    lead_id = lead['lead_id']
    if hi:
        kb = [
            [InlineKeyboardButton("🎂 जन्मदिन", callback_data=f"greet_bday_{lead_id}")],
            [InlineKeyboardButton("💍 वर्षगांठ", callback_data=f"greet_anniv_{lead_id}")],
            [InlineKeyboardButton("🙏 धन्यवाद", callback_data=f"greet_thanks_{lead_id}")],
            [InlineKeyboardButton("🎉 त्योहार", callback_data=f"greet_festival_{lead_id}")],
        ]
    else:
        kb = [
            [InlineKeyboardButton("🎂 Birthday", callback_data=f"greet_bday_{lead_id}")],
            [InlineKeyboardButton("💍 Anniversary", callback_data=f"greet_anniv_{lead_id}")],
            [InlineKeyboardButton("🙏 Thank You", callback_data=f"greet_thanks_{lead_id}")],
            [InlineKeyboardButton("🎉 Festival", callback_data=f"greet_festival_{lead_id}")],
        ]

    await processing_msg.edit_text(
        f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
        f"🎉 {'ग्रीटिंग भेजें' if hi else 'Send Greeting'}: <b>{h(lead['name'])}</b>\n\n"
        f"{'कौन सी ग्रीटिंग?' if hi else 'Which greeting type?'}",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML)


# ── Intent: EDIT LEAD ────────────────────────────────────────────────────
async def _voice_handle_edit_lead(processing_msg, data, agent, lang, context=None):
    """Voice: edit a lead field (phone, email, city, etc.)."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name')
    lead_phone = data.get('lead_phone')
    edit_field = data.get('edit_field')
    edit_value = data.get('edit_value')

    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], lead_name, lead_phone, tenant_id=_tid)
    if not lead:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
            f"❌ {'लीड नहीं मिली' if hi else 'Lead not found'}: <b>{h(lead_name or 'unknown')}</b>",
            parse_mode=ParseMode.HTML)
        return

    allowed_fields = {'name', 'phone', 'email', 'city', 'need_type', 'notes',
                      'whatsapp', 'dob', 'anniversary'}

    if not edit_field or edit_field not in allowed_fields or not edit_value:
        # Show lead detail with edit buttons
        kb = [[InlineKeyboardButton(
            f"✏️ {'संपादित करें' if hi else 'Edit'}",
            callback_data=f"editbtn_{lead['lead_id']}")]]
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
            f"👤 <b>{h(lead['name'])}</b> (#{lead['lead_id']})\n"
            f"📱 {h(lead.get('phone', 'N/A'))}\n"
            f"📧 {h(lead.get('email', 'N/A'))}\n"
            f"🏙 {h(lead.get('city', 'N/A'))}\n\n"
            f"{'ऊपर बटन से एडिट करें' if hi else 'Tap Edit to update fields'}",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML)
        return

    # Apply the edit
    await db.update_lead(lead['lead_id'], **{edit_field: edit_value})
    _track_voice_context(context, intent='edit_lead', lead_id=lead['lead_id'], lead_name=lead['name'])
    await processing_msg.edit_text(
        f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
        f"✅ {'अपडेट किया' if hi else 'Updated'}!\n"
        f"👤 <b>{h(lead['name'])}</b> (#{lead['lead_id']})\n"
        f"📝 {h(edit_field)}: <b>{h(str(edit_value)[:100])}</b>",
        parse_mode=ParseMode.HTML)


# ── Intent: ASK AI ───────────────────────────────────────────────────────
async def _voice_handle_ask_ai(processing_msg, data, agent, lang):
    """Voice: answer an insurance/business question via AI."""
    question = data.get('ai_question') or data.get('transcript', '')
    if not question:
        await processing_msg.edit_text("❌ No question detected.", parse_mode=ParseMode.HTML)
        return

    try:
        await processing_msg.edit_text(
            i18n.t(lang, "ai_thinking"), parse_mode=ParseMode.HTML)
    except Exception:
        pass

    answer = await ai.ask_insurance_ai(question, lang=lang)
    keyboard = [[InlineKeyboardButton(
        "💬 " + ("और पूछें" if lang == 'hi' else "Ask Another"),
        callback_data="ai_chat")],
        [InlineKeyboardButton("🔙 " + ("AI टूल्स" if lang == 'hi' else "AI Tools"),
                              callback_data="ai_back")]]
    if len(answer) > 3800:
        answer = answer[:3800] + "\n\n... (truncated)"
    await processing_msg.edit_text(
        f"🎙 <b>{'सवाल' if lang == 'hi' else 'Question'}:</b> <i>{h(question[:200])}</i>\n\n"
        f"💬 <b>AI {'जवाब' if lang == 'hi' else 'Answer'}</b>\n━━━━━━━━━━━━━━━━━━\n\n{h(answer)}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


# ── Intent: AI LEAD SCORE ────────────────────────────────────────────────
async def _voice_handle_ai_lead_score(processing_msg, data, agent, lang):
    """Voice: AI-score all leads or a specific lead."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name')

    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    if lead_name:
        lead = await _find_lead_by_voice(agent['agent_id'], lead_name, tenant_id=_tid)
        if not lead:
            await processing_msg.edit_text(
                f"🎙️ <i>{h(data.get('transcript', '')[:200])}</i>\n\n"
                f"❌ {'लीड नहीं मिली' if hi else 'Lead not found'}: <b>{h(lead_name)}</b>",
                parse_mode=ParseMode.HTML)
            return
        try:
            await processing_msg.edit_text(
                f"🎯 {'स्कोर कर रहा हूँ' if hi else 'Scoring'}...", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        interactions = await db.get_lead_interactions(lead['lead_id'], limit=10)
        policies = await db.get_policies_by_lead(lead['lead_id'])
        score = await ai.score_lead(dict(lead), interactions, policies, lang=lang)
        score_val = score.get('score', 0)
        bar = "🟢" if score_val >= 70 else "🟡" if score_val >= 40 else "🔴"
        factors = "\n".join(f"  • {f}" for f in score.get('factors', []))
        await processing_msg.edit_text(
            f"🎯 <b>AI Score: {h(lead['name'])}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{bar} <b>Score: {score_val}/100</b>\n\n"
            f"📊 {'कारण' if hi else 'Factors'}:\n{factors}\n\n"
            f"💡 {h(score.get('recommendation', ''))}",
            parse_mode=ParseMode.HTML)
        return

    # Score all leads — show top leads with score buttons
    leads = await db.get_leads_by_agent(agent['agent_id'])
    if not leads:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
            f"{'कोई लीड नहीं' if hi else 'No leads to score'}",
            parse_mode=ParseMode.HTML)
        return
    keyboard = [[InlineKeyboardButton(
        f"🎯 #{l['lead_id']} {l['name'][:20]}",
        callback_data=f"aiscore_{l['lead_id']}")] for l in leads[:10]]
    keyboard.append([InlineKeyboardButton(
        "🏆 " + ("सभी स्कोर करें" if hi else "Score All"),
        callback_data="aiscore_all")])
    await processing_msg.edit_text(
        f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
        f"🎯 <b>{'लीड स्कोरिंग' if hi else 'Lead Scoring'}</b>\n\n"
        f"{'लीड चुनें' if hi else 'Select a lead to score'}:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


# ── Intent: AI PITCH / FOLLOWUP SUGGEST / RECOMMEND (common handler) ────
async def _voice_handle_ai_tool(processing_msg, data, agent, lang, tool_type):
    """Voice: trigger AI pitch/followup/recommend for a lead by name."""
    hi = lang == 'hi'
    lead_name = data.get('lead_name')

    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    if lead_name:
        lead = await _find_lead_by_voice(agent['agent_id'], lead_name, tenant_id=_tid)
    else:
        lead = None

    if not lead:
        # Show lead picker
        leads = await db.get_leads_by_agent(agent['agent_id'])
        if not leads:
            await processing_msg.edit_text(
                f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
                f"{'कोई लीड नहीं' if hi else 'No leads found'}",
                parse_mode=ParseMode.HTML)
            return
        cb_prefix = {'pitch': 'aipitch', 'followup': 'aifollowup', 'recommend': 'airec'}[tool_type]
        titles = {'pitch': ('पिच जेनरेटर', 'Pitch Generator'),
                  'followup': ('स्मार्ट फॉलो-अप', 'Smart Follow-up'),
                  'recommend': ('पॉलिसी सुझाव', 'Policy Recommender')}
        title = titles[tool_type][0] if hi else titles[tool_type][1]
        emojis = {'pitch': '💡', 'followup': '📅', 'recommend': '📋'}
        keyboard = [[InlineKeyboardButton(
            f"#{l['lead_id']} {l['name'][:20]}",
            callback_data=f"{cb_prefix}_{l['lead_id']}")] for l in leads[:10]]
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
            f"{emojis[tool_type]} <b>{title}</b>\n\n"
            f"{'लीड चुनें' if hi else 'Select a lead'}:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)
        return

    # Lead found — directly run the AI tool
    lead_id = lead['lead_id']

    if tool_type == 'pitch':
        try:
            await processing_msg.edit_text(
                f"💡 {'पिच बना रहा हूँ' if hi else 'Crafting pitch'}...", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        tenant = await db.get_tenant(agent['tenant_id'])
        firm = tenant.get('firm_name', 'Sarathi-AI') if tenant else 'Sarathi-AI'
        pitch = await ai.generate_pitch(
            dict(lead), agent['name'], firm,
            lead.get('need_type', 'general'), lang=lang)
        msg = (f"💡 <b>{'पिच' if hi else 'Pitch'}: {h(lead['name'])}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
               f"<b>{'शुरुआत' if hi else 'Opening'}:</b>\n{h(pitch.get('opening', ''))}\n\n"
               f"<b>{'मुख्य पिच' if hi else 'Main Pitch'}:</b>\n{h(pitch.get('pitch', ''))}\n\n"
               f"<b>{'मुख्य बिंदु' if hi else 'Key Points'}:</b>\n")
        for pt in pitch.get('key_points', []):
            msg += f"  ✅ {h(pt)}\n"
        msg += f"\n<b>{'समापन' if hi else 'Closing'}:</b>\n{h(pitch.get('closing', ''))}"
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        keyboard = [
            [InlineKeyboardButton("📱 WhatsApp Pitch", callback_data=f"aipitch_wa_{lead_id}")],
            [InlineKeyboardButton("🔙 AI Tools", callback_data="ai_back")]]
        context_data = pitch.get('whatsapp_message', '')
        await processing_msg.edit_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif tool_type == 'followup':
        try:
            await processing_msg.edit_text(
                f"📅 {'विश्लेषण कर रहा हूँ' if hi else 'Analyzing'}...", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        interactions = await db.get_lead_interactions(lead_id, limit=10)
        policies = await db.get_policies_by_lead(lead_id)
        suggestion = await ai.suggest_followup(dict(lead), interactions, policies, lang=lang)

        urgency_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
            suggestion.get('urgency', 'medium'), '⚪')
        tips = "\n".join(f"  💡 {t}" for t in suggestion.get('tips', []))
        msg = (f"📅 <b>{'फॉलो-अप' if hi else 'Follow-up'}: {h(lead['name'])}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
               f"{urgency_emoji} {'तत्कालता' if hi else 'Urgency'}: <b>{suggestion.get('urgency', 'medium').upper()}</b>\n"
               f"📱 {'चैनल' if hi else 'Channel'}: <b>{suggestion.get('channel', 'whatsapp')}</b>\n"
               f"⏰ {'समय' if hi else 'Timing'}: <b>{suggestion.get('timing', 'Today')}</b>\n\n"
               f"<b>{'सुझाव' if hi else 'Action'}:</b>\n→ {h(suggestion.get('action', 'Follow up'))}\n\n"
               f"<b>{'ड्राफ्ट' if hi else 'Draft'}:</b>\n<code>{h(suggestion.get('message_draft', ''))}</code>\n\n"
               f"<b>{'टिप्स' if hi else 'Tips'}:</b>\n{tips}")
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        keyboard = [
            [InlineKeyboardButton("💡 " + ("पिच बनाएं" if hi else "Generate Pitch"), callback_data=f"aipitch_{lead_id}")],
            [InlineKeyboardButton("🔙 AI Tools", callback_data="ai_back")]]
        await processing_msg.edit_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif tool_type == 'recommend':
        try:
            await processing_msg.edit_text(
                f"📋 {'विश्लेषण कर रहा हूँ' if hi else 'Analyzing needs'}...", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        policies = await db.get_policies_by_lead(lead_id)
        rec = await ai.recommend_policies(dict(lead), policies, lang=lang)
        msg = (f"📋 <b>{'सुझाव' if hi else 'Recommendations'}: {h(lead['name'])}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
               f"<b>{'गैप विश्लेषण' if hi else 'Gap Analysis'}:</b>\n{h(rec.get('gap_analysis', 'N/A'))}\n\n")
        for i, r in enumerate(rec.get('recommendations', []), 1):
            prio = {"must_have": "🔴", "recommended": "🟡", "nice_to_have": "🟢"}.get(r.get('priority', ''), '⚪')
            msg += (f"{prio} <b>{i}. {h(r.get('type', '').replace('_', ' ').title())}</b>\n"
                    f"   {'कवर' if hi else 'Cover'}: {h(r.get('suggested_cover', 'N/A'))}\n"
                    f"   {'प्रीमियम' if hi else 'Premium'}: {h(r.get('estimated_premium', 'N/A'))}\n\n")
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        keyboard = [
            [InlineKeyboardButton("💡 " + ("पिच" if hi else "Pitch"), callback_data=f"aipitch_{lead_id}")],
            [InlineKeyboardButton("🔙 AI Tools", callback_data="ai_back")]]
        await processing_msg.edit_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)


# ── Intent: OPEN CALCULATOR (show menu) ──────────────────────────────────
async def _voice_handle_open_calculator(processing_msg, data, agent, lang):
    """Voice: show the calculator menu."""
    hi = lang == 'hi'
    server_url = os.getenv("SERVER_URL", "http://localhost:8000")
    _calc_names = {
        'inflation': ('📉 Inflation Eraser', '📉 महंगाई कैलकुलेटर'),
        'hlv':       ('🛡️ Human Life Value', '🛡️ मानव जीवन मूल्य'),
        'retirement':('🏖️ Retirement Planner', '🏖️ रिटायरमेंट प्लानर'),
        'emi':       ('💳 Premium EMI', '💳 प्रीमियम EMI'),
        'health':    ('🏥 Health Cover', '🏥 स्वास्थ्य बीमा'),
        'sip':       ('📈 SIP vs Lumpsum', '📈 SIP vs एकमुश्त'),
        'mfsip':     ('📊 MF SIP Planner', '📊 MF SIP प्लानर'),
        'ulip':      ('⚖️ ULIP vs MF', '⚖️ ULIP vs MF'),
        'nps':       ('🏛️ NPS Planner', '🏛️ NPS प्लानर'),
    }
    keyboard = []
    for key, (en, hi_name) in _calc_names.items():
        keyboard.append([InlineKeyboardButton(
            hi_name if hi else en, callback_data=f"vcalc_{key}")])
    await _safe_edit_text(processing_msg,
        f"🎙️ <i>{h(data.get('transcript', '')[:150])}</i>\n\n"
        f"🧮 <b>{'कैलकुलेटर — कौन सा चलाएं?' if hi else 'Calculator — which one?'}</b>\n\n"
        f"{'नीचे टैप करें या वॉइस नोट भेजें' if hi else 'Tap below or send a voice note'}:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


# ── Intent: SELECT CALCULATOR (open specific one) ────────────────────────
async def _voice_handle_select_calculator(processing_msg, data, agent, lang):
    """Voice: open a specific calculator by name — show its param list with a compute hint."""
    hi = lang == 'hi'
    calc_type = (data.get('calc_type') or '').lower().strip()

    # Fuzzy match calc_type
    _alias = {
        'inflation': 'inflation', 'mehangai': 'inflation', 'mahangai': 'inflation',
        'hlv': 'hlv', 'human life': 'hlv', 'life value': 'hlv', 'term': 'hlv',
        'retirement': 'retirement', 'retire': 'retirement', 'pension': 'retirement',
        'emi': 'emi', 'premium emi': 'emi', 'premium': 'emi',
        'health': 'health', 'medical': 'health', 'health cover': 'health',
        'sip': 'sip', 'sip vs lumpsum': 'sip', 'lumpsum': 'sip',
        'mfsip': 'mfsip', 'mf sip': 'mfsip', 'mutual fund sip': 'mfsip', 'goal': 'mfsip',
        'ulip': 'ulip', 'ulip vs mf': 'ulip', 'ulip vs mutual fund': 'ulip',
        'nps': 'nps',
    }
    resolved = _alias.get(calc_type, calc_type)
    if resolved not in _CALC_PARAMS:
        # Couldn't resolve — show menu
        return await _voice_handle_open_calculator(processing_msg, data, agent, lang)

    params = _CALC_PARAMS[resolved]['params']
    title = _CALC_PARAMS[resolved].get('title_hi' if hi else 'title',
                                        _CALC_PARAMS[resolved]['title'])

    # Show what params are needed with a helpful hint
    param_list = ""
    for i, p in enumerate(params, 1):
        label = p.get('prompt_hi' if hi else 'prompt', p['prompt'])
        param_list += f"  {i}. {label}\n"

    _hint = ("अब एक वॉइस नोट में सारे नंबर बोलें" if hi
             else "Now send a voice note with all the numbers")
    _example = _voice_calc_example(resolved, hi)

    keyboard = [
        [InlineKeyboardButton(
            "🧮 " + ("बटन से भरें" if hi else "Fill Step-by-Step"),
            callback_data=f"csel_{resolved}")],
    ]

    await _safe_edit_text(processing_msg,
        f"🎙️ <i>{h(data.get('transcript', '')[:150])}</i>\n\n"
        f"{title}\n━━━━━━━━━━━━━━━━━━\n\n"
        f"{'ज़रूरी जानकारी' if hi else 'Required inputs'}:\n{param_list}\n"
        f"💡 <b>{_hint}</b>\n"
        f"<i>{_example}</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


def _voice_calc_example(calc_type: str, hi: bool) -> str:
    """Return an example voice command for a calculator."""
    _examples = {
        'inflation': ('उदा: "50 हज़ार monthly, 7% inflation, 15 साल"',
                       'e.g. "50000 monthly, 7% inflation, 15 years"'),
        'hlv':       ('उदा: "75 हज़ार expense, 20 लाख loan, 10 लाख बच्चे, 5 लाख cover"',
                       'e.g. "75000 expense, 20 lakh loan, 10 lakh children, 5 lakh cover"'),
        'retirement':('उदा: "35 age, 60 retire, 80 life, 50 हज़ार expense, 7% inflation"',
                       'e.g. "35 age, 60 retire, 80 life exp, 50k expense, 7% inflation"'),
        'emi':       ('उदा: "50 हज़ार premium, 5 साल, 18% GST"',
                       'e.g. "50000 premium, 5 years, 18% GST"'),
        'health':    ('उदा: "35 age, 2A+1C family, metro city, 10 lakh income"',
                       'e.g. "35 age, family 2A+1C, metro, 10 lakh income"'),
        'sip':       ('उदा: "10 लाख, 20 साल, 12% return"',
                       'e.g. "10 lakh amount, 20 years, 12% return"'),
        'mfsip':     ('उदा: "50 लाख goal, 15 साल, 12% return"',
                       'e.g. "50 lakh goal, 15 years, 12% return"'),
        'ulip':      ('उदा: "1 लाख annual, 15 साल, ULIP 10%, MF 12%"',
                       'e.g. "1 lakh annual, 15 years, ULIP 10%, MF 12%"'),
        'nps':       ('उदा: "10 हज़ार monthly, 30 age, 60 retire, 10% return, 30% tax"',
                       'e.g. "10000 monthly, 30 age, 60 retire, 10% return, 30% tax"'),
    }
    pair = _examples.get(calc_type, ('', ''))
    return pair[0] if hi else pair[1]


def _extract_number_from_text(text: str):
    """Extract a numeric value from text — handles digits, Hindi/English words, lakh/crore."""
    import re as _re
    if not text:
        return None
    t = text.lower().strip().replace(',', '').replace('₹', '').replace('%', '').strip()

    # Direct digits first: "5", "50000", "12.5"
    m = _re.search(r'(\d+\.?\d*)', t)
    if m:
        v = m.group(1)
        # Check for lakh/crore multiplier after the number
        rest = t[m.end():].strip()
        if rest.startswith('lakh') or rest.startswith('lac') or rest.startswith('लाख'):
            return str(float(v) * 100000)
        if rest.startswith('crore') or rest.startswith('cr') or rest.startswith('करोड़') or rest.startswith('करोड'):
            return str(float(v) * 10000000)
        if rest.startswith('k') or rest.startswith('हज़ार') or rest.startswith('हजार') or rest.startswith('hazaar') or rest.startswith('hazar'):
            return str(float(v) * 1000)
        return v

    # English number words
    _word_nums = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
        'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
        'twenty five': 25, 'thirty': 30, 'forty': 40, 'fifty': 50,
        'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90, 'hundred': 100,
    }
    # Hindi number words
    _word_nums.update({
        'sunya': 0, 'ek': 1, 'do': 2, 'teen': 3, 'char': 4, 'paanch': 5, 'panch': 5,
        'chhe': 6, 'saat': 7, 'aath': 8, 'nau': 9, 'das': 10, 'duss': 10,
        'gyarah': 11, 'barah': 12, 'terah': 13, 'chaudah': 14, 'pandrah': 15,
        'solah': 16, 'satrah': 17, 'atharah': 18, 'unees': 19, 'bees': 20,
        'pachees': 25, 'tees': 30, 'chaalis': 40, 'pachaas': 50, 'pachas': 50,
        'saath': 60, 'sattar': 70, 'assi': 80, 'nabbe': 90, 'sau': 100,
    })

    for word, val in sorted(_word_nums.items(), key=lambda x: -len(x[0])):
        if word in t:
            # Check for multipliers
            if 'lakh' in t or 'lac' in t or 'लाख' in t:
                return str(val * 100000)
            if 'crore' in t or 'करोड़' in t:
                return str(val * 10000000)
            if 'hazaar' in t or 'hazar' in t or 'हज़ार' in t or 'हजार' in t or 'thousand' in t:
                return str(val * 1000)
            return str(val)

    return None


# ── Intent: SEND CALC RESULT (share last result to a lead) ───────────────
async def _voice_handle_send_calc_result(processing_msg, data, agent, lang, context):
    """Voice: send the last calculator result to a lead via WhatsApp."""
    hi = lang == 'hi'
    transcript = data.get('transcript', '')
    send_to = data.get('send_to_lead') or data.get('lead_name')

    if not send_to:
        await _safe_edit_text(processing_msg,
            f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
            f"❓ {'किसको भेजें? लीड का नाम बताएं' if hi else 'Send to whom? Please mention the lead name'}",
            parse_mode=ParseMode.HTML)
        return

    # Find the last calculator result
    last_type = context.user_data.get('last_calc_type')
    calc_text = context.user_data.get(f"last_calc_{last_type}", "") if last_type else ""

    if not calc_text:
        await _safe_edit_text(processing_msg,
            f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
            f"❌ {'कोई कैलकुलेटर रिजल्ट नहीं मिला। पहले कैलकुलेशन करें।' if hi else 'No recent calculator result found. Please run a calculation first.'}\n\n"
            f"🧮 {'कैलकुलेटर खोलें' if hi else 'Open Calculator'} 👇",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🧮 " + ("कैलकुलेटर" if hi else "Calculator"),
                                     callback_data="vcalc_menu")
            ]]),
            parse_mode=ParseMode.HTML)
        return

    # Find lead
    _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
    lead = await _find_lead_by_voice(agent['agent_id'], send_to, tenant_id=_tid)
    if not lead:
        await _safe_edit_text(processing_msg,
            f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
            f"❌ {'लीड नहीं मिली' if hi else 'Lead not found'}: <b>{h(send_to)}</b>",
            parse_mode=ParseMode.HTML)
        return

    if not lead.get('phone'):
        await _safe_edit_text(processing_msg,
            f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
            f"❌ {h(lead['name'])} {'का फ़ोन नं. नहीं है' if hi else 'has no phone number'}",
            parse_mode=ParseMode.HTML)
        return

    # Send via WhatsApp (with auto-fallback to wa.me link)
    import re as _re_mod
    clean_text = _re_mod.sub(r'<[^>]+>', '', calc_text)
    agent_name = agent.get('name', 'Your Advisor')
    company = "Sarathi-AI"
    try:
        tenant = await db.get_tenant(agent['tenant_id'])
        if tenant and tenant.get('firm_name'):
            company = tenant['firm_name']
    except Exception:
        pass

    result = await wa.send_calc_report(
        lead['phone'], lead['name'], last_type,
        clean_text, agent_name=agent_name, company=company)

    if result.get('success'):
        if result.get('method') == 'link':
            link = result.get('wa_link', '')
            await _safe_edit_text(processing_msg,
                f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
                f"📤 <b>{'भेजने के लिए क्लिक करें' if hi else 'Click to send via WhatsApp'}</b>\n\n"
                f"👤 {h(lead['name'])}\n"
                f"📱 <a href=\"{h(link)}\">WhatsApp {'पर भेजें' if hi else 'Send'}</a>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True)
        else:
            await _safe_edit_text(processing_msg,
                f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
                f"✅ {'भेज दिया' if hi else 'Sent'}! 📤\n\n"
                f"👤 {h(lead['name'])}\n📱 {h(lead.get('phone', ''))}",
                parse_mode=ParseMode.HTML)
    else:
        await _safe_edit_text(processing_msg,
            f"🎙️ <i>{h(transcript[:200])}</i>\n\n"
            f"❌ {'भेजने में त्रुटि' if hi else 'Failed to send'}: "
            f"{h(str(result.get('error', 'Unknown'))[:100])}",
            parse_mode=ParseMode.HTML)


# ── Intent: CALC COMPUTE (extract params, calculate, show result) ────────
async def _voice_handle_calc_compute(processing_msg, data, agent, lang, context):
    """Voice: extract all calculator params from voice, compute, show result.
    If some params are missing, ask for them via multi-turn voice context.
    Also supports 'send to lead' in one shot."""
    hi = lang == 'hi'
    calc_type = (data.get('calc_type') or '').lower().strip()
    transcript = data.get('transcript', '')

    # Fuzzy-match calc type
    _alias = {
        'inflation': 'inflation', 'mehangai': 'inflation', 'mahangai': 'inflation',
        'hlv': 'hlv', 'human life': 'hlv', 'life value': 'hlv', 'term': 'hlv',
        'retirement': 'retirement', 'retire': 'retirement', 'pension': 'retirement',
        'emi': 'emi', 'premium emi': 'emi', 'premium': 'emi',
        'health': 'health', 'medical': 'health', 'health cover': 'health',
        'sip': 'sip', 'sip vs lumpsum': 'sip', 'lumpsum': 'sip',
        'mfsip': 'mfsip', 'mf sip': 'mfsip', 'mutual fund sip': 'mfsip', 'goal': 'mfsip',
        'ulip': 'ulip', 'ulip vs mf': 'ulip', 'ulip vs mutual fund': 'ulip',
        'nps': 'nps',
    }
    resolved = _alias.get(calc_type, calc_type)
    if resolved not in _CALC_PARAMS:
        # No calc_type — but if send_to_lead is present, send last result
        if data.get('send_to_lead') or data.get('lead_name'):
            return await _voice_handle_send_calc_result(
                processing_msg, data, agent, lang, context)
        # Can't determine calculator — show menu
        return await _voice_handle_open_calculator(processing_msg, data, agent, lang)

    params_def = _CALC_PARAMS[resolved]['params']
    title = _CALC_PARAMS[resolved].get('title_hi' if hi else 'title',
                                        _CALC_PARAMS[resolved]['title'])
    voice_params = data.get('calc_params') or {}

    # Build values dict — validate each param
    values = {}
    missing = []
    for p in params_def:
        key = p['key']
        raw = voice_params.get(key)
        if raw is not None and raw != '' and raw is not None:
            # Validate
            try:
                if p.get('type') == 'choice':
                    allowed = [str(a).lower() for a in p.get('allowed', [])]
                    if str(raw).lower() in allowed:
                        values[key] = str(raw)
                    else:
                        missing.append(p)
                else:
                    val = float(raw)
                    mn, mx = p.get('min', float('-inf')), p.get('max', float('inf'))
                    if mn <= val <= mx:
                        values[key] = int(val) if val == int(val) else val
                    else:
                        missing.append(p)
            except (ValueError, TypeError):
                missing.append(p)
        else:
            missing.append(p)

    if missing:
        # Some params missing — store context for multi-turn
        context.user_data['voice_context'] = {
            'pending_action': 'calc_compute',
            'calc_type': resolved,
            'values': values,
            'missing_keys': [p['key'] for p in missing],
            'missing_step': 0,
            'created_at': time.time(),
        }
        # Ask for first missing param
        first_missing = missing[0]
        label = first_missing.get('prompt_hi' if hi else 'prompt', first_missing['prompt'])
        btns = first_missing.get('buttons', [])
        keyboard = []
        row = []
        for bv in btns:
            display = first_missing['fmt'].format(bv) if isinstance(bv, (int, float)) else str(bv)
            row.append(InlineKeyboardButton(display, callback_data=f"vcparam_{bv}"))
            if len(row) >= 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        got_str = ""
        if values:
            got_items = []
            for p in params_def:
                if p['key'] in values:
                    v = values[p['key']]
                    disp = p['fmt'].format(v) if isinstance(v, (int, float)) else str(v)
                    plabel = p.get('prompt_hi' if hi else 'prompt', p['prompt'])
                    got_items.append(f"  ✅ {plabel}: <b>{disp}</b>")
            got_str = "\n".join(got_items) + "\n\n"

        remaining = len(missing)
        keyboard.append([InlineKeyboardButton(
            "❌ रद्द करें" if hi else "❌ Cancel",
            callback_data="voice_cancel")])
        await _safe_edit_text(processing_msg,
            f"🎙️ <i>{h(transcript[:150])}</i>\n\n"
            f"{title}\n━━━━━━━━━━━━━━━━━━\n"
            f"{got_str}"
            f"📊 <b>{'बाकी' if hi else 'Remaining'}: {remaining} {'जानकारी' if hi else 'inputs'}</b>\n\n"
            f"<b>{label}</b> {'दर्ज करें' if hi else 'enter'}:\n"
            f"{'वॉइस नोट, टाइप, या नीचे टैप करें' if hi else 'Voice note, type, or tap below'}:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)
        return

    # All params present — compute!
    await _voice_calc_compute_and_show(
        processing_msg, resolved, values, data, agent, lang, context)


async def _voice_calc_compute_and_show(processing_msg, calc_type, values,
                                        data, agent, lang, context):
    """Run the calculator and display results with action buttons."""
    hi = lang == 'hi'
    transcript = data.get('transcript', '') if data else ''
    send_to = data.get('send_to_lead') if data else None

    try:
        await _safe_edit_text(processing_msg,
            f"🧮 {'कैलकुलेट कर रहा हूँ' if hi else 'Calculating'}...",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass

    # Run calculation
    try:
        if calc_type == "inflation":
            result = calc.inflation_eraser(values['amount'], values['rate'], values['years'])
        elif calc_type == "hlv":
            result = calc.hlv_calculator(
                values['monthly_expense'], values['loans'],
                values['children'], values['existing_cover'], 0)
        elif calc_type == "retirement":
            result = calc.retirement_planner(
                values['current_age'], values['retire_age'], values['life_exp'],
                values['monthly_expense'], values['inflation'],
                values['pre_return'], values['post_return'],
                values.get('existing_savings', 0))
        elif calc_type == "emi":
            result = calc.emi_calculator(
                values['premium'], values['years'], values['gst'],
                values['cibil_disc'], values['down_pct'])
        elif calc_type == "health":
            result = calc.health_cover_estimator(
                int(values['age']), str(values['family']),
                str(values['city']), int(values['income']),
                int(values.get('existing', 0)))
        elif calc_type == "sip":
            result = calc.sip_vs_lumpsum(
                values['amount'], values['years'], values['return_rate'])
        elif calc_type == "mfsip":
            result = calc.mf_sip_planner(
                values['goal'], values['years'],
                values['return_rate'], values.get('existing', 0))
        elif calc_type == "ulip":
            result = calc.ulip_vs_mf(
                values['annual_inv'], values['years'],
                values['ulip_return'], values['mf_return'])
        elif calc_type == "nps":
            result = calc.nps_planner(
                values['monthly'], values['current_age'],
                values['retire_age'], values['return_rate'],
                values.get('tax_bracket', 30))
        elif calc_type == "stepupsip":
            result = calc.stepup_sip_planner(
                values['initial_sip'], values['step_up'],
                values['years'], values['return_rate'])
        elif calc_type == "swp":
            result = calc.swp_calculator(
                values['corpus'], values['monthly_withdrawal'],
                values['return_rate'], values['years'])
        elif calc_type == "delaycost":
            result = calc.delay_cost_calculator(
                values['monthly_sip'], values['years'],
                values['return_rate'], values['delay_years'])
        else:
            await _safe_edit_text(processing_msg, "❌ Unknown calculator type.")
            return
    except Exception as e:
        logger.error("Voice calc error (%s): %s", calc_type, e, exc_info=True)
        await _safe_edit_text(processing_msg,
            f"❌ {'गणना त्रुटि' if hi else 'Calculation error'}: {h(str(e))}",
            parse_mode=ParseMode.HTML)
        return

    # Format result text (reuse the same formatting as _calc_show_result)
    text = _format_calc_result_text(calc_type, values, result, hi)

    # Store for WhatsApp sharing
    context.user_data[f"last_calc_{calc_type}"] = text
    context.user_data['last_calc_type'] = calc_type
    _track_voice_context(context, intent='calc_compute', calc_type=calc_type)

    # Generate PDF report
    report_url = None
    try:
        server_url = os.getenv("SERVER_URL", "http://localhost:8000")
        agent_name = agent.get('name', 'Advisor')
        agent_phone = agent.get('phone', '')
        agent_photo_url = ""
        if agent.get('profile_photo'):
            agent_photo_url = f"{server_url}{agent['profile_photo']}"
        company = "Sarathi-AI Business Technologies"
        tenant = None
        try:
            tenant = await db.get_tenant(agent['tenant_id'])
            if tenant and tenant.get('firm_name'):
                company = tenant['firm_name']
        except Exception:
            pass
        # Build compliance credentials for PDF footer
        _creds = ''
        try:
            _creds = await db.build_compliance_credentials(agent['agent_id'])
        except Exception:
            pass
        _brand = dict(agent_name=agent_name, agent_phone=agent_phone,
                      agent_photo_url=agent_photo_url, company=company)
        _brand_info = None
        if tenant:
            _brand_info = {
                'firm_name': company,
                'primary_color': tenant.get('brand_primary_color') or None,
                'accent_color': tenant.get('brand_accent_color') or None,
                'logo': tenant.get('brand_logo') or None,
                'tagline': tenant.get('brand_tagline') or None,
                'phone': tenant.get('brand_phone') or None,
                'email': tenant.get('brand_email') or None,
                'website': tenant.get('brand_website') or None,
            }
        _brand['brand'] = _brand_info
        gen_map = {
            'inflation': pdf.generate_inflation_html,
            'hlv': pdf.generate_hlv_html,
            'retirement': pdf.generate_retirement_html,
            'emi': pdf.generate_emi_html,
            'health': pdf.generate_health_html,
            'sip': pdf.generate_sip_html,
            'mfsip': pdf.generate_mfsip_html,
            'ulip': pdf.generate_ulip_html,
            'nps': pdf.generate_nps_html,
            'stepupsip': pdf.generate_stepupsip_html,
            'swp': pdf.generate_swp_html,
            'delaycost': pdf.generate_delaycost_html,
        }
        gen_fn = gen_map.get(calc_type)
        if gen_fn:
            html = gen_fn(result, "Client", **_brand)
            # Inject compliance credentials into PDF footer
            if _creds:
                import html as _html_mod
                _cred_html = (
                    '<div style="text-align:center;font-size:11px;color:#777;'
                    'padding:12px 20px 4px;border-top:1px solid #eee;'
                    'margin-top:10px;white-space:pre-line">'
                    f'{_html_mod.escape(_creds)}</div>'
                )
                html = html.replace('</body>', f'{_cred_html}\n</body>')
            fname = pdf.save_html_report(html, calc_type, "client", advisor_name=company)
            report_url = f"{server_url}/reports/{fname}"
    except Exception as e:
        logger.warning("Voice calc report gen failed: %s", e)

    # Build action buttons
    rows = []
    row1 = [
        InlineKeyboardButton(
            "🔄 " + ("फिर से" if hi else "Recalculate"),
            callback_data=f"csel_{calc_type}"),
        InlineKeyboardButton(
            "📱 " + ("WhatsApp भेजें" if hi else "Send WhatsApp"),
            callback_data=f"wa_share_{calc_type}"),
    ]
    rows.append(row1)
    if report_url:
        rows.append([InlineKeyboardButton(
            "📊 " + ("रिपोर्ट देखें" if hi else "View Report"), url=report_url)])

    # If agent said "send to <lead_name>" — add a direct send button
    if send_to:
        _tid = agent['tenant_id'] if agent.get('role') in ('owner', 'admin') else None
        lead = await _find_lead_by_voice(agent['agent_id'], send_to, tenant_id=_tid)
        if lead and lead.get('phone'):
            rows.append([InlineKeyboardButton(
                f"📤 {'भेजें' if hi else 'Send to'} {h(lead['name'][:20])}",
                callback_data=f"vcalc_send_{calc_type}_{lead['lead_id']}")])

    rows.append([InlineKeyboardButton(
        "🧮 " + ("अन्य कैलकुलेटर" if hi else "Other Calculator"),
        callback_data="vcalc_menu")])

    await _safe_edit_text(processing_msg,
        f"🎙️ <i>{h(transcript[:150])}</i>\n\n{text}",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode=ParseMode.HTML)


def _format_calc_result_text(calc_type, v, result, hi):
    """Format calculator result as Telegram HTML text."""
    if calc_type == "inflation":
        if hi:
            return (
                f"📉 <b>महंगाई कैलकुलेटर — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 वर्तमान: ₹{v['amount']:,.0f}/महीना\n"
                f"📈 महंगाई: {v['rate']}% | अवधि: {v['years']} वर्ष\n\n"
                f"⚠️ <b>क्रय शक्ति गिरकर:</b>\n"
                f"<b>{h(calc.format_currency(result.purchasing_power_left))}/महीना</b>\n\n"
                f"🔴 क्षरण: {result.erosion_percent:.1f}%\n"
                f"💡 समान जीवनशैली के लिए <b>{h(calc.format_currency(result.future_value_needed))}/महीना</b> चाहिए।")
        return (
            f"📉 <b>Inflation Eraser — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Current: ₹{v['amount']:,.0f}/month\n"
            f"📈 Inflation: {v['rate']}% | Period: {v['years']} years\n\n"
            f"⚠️ <b>Purchasing power drops to:</b>\n"
            f"<b>{h(calc.format_currency(result.purchasing_power_left))}/month</b>\n\n"
            f"🔴 Erosion: {result.erosion_percent:.1f}%\n"
            f"💡 Need <b>{h(calc.format_currency(result.future_value_needed))}/month</b> to maintain lifestyle.")

    elif calc_type == "hlv":
        if hi:
            return (
                f"🛡️ <b>मानव जीवन मूल्य — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 मासिक खर्च: ₹{v['monthly_expense']:,.0f}\n"
                f"🏦 लोन: ₹{v['loans']:,.0f} | 👶 बच्चे: ₹{v['children']:,.0f}\n"
                f"🛡️ मौजूदा कवर: ₹{v['existing_cover']:,.0f}\n\n"
                f"✅ <b>अनुशंसित कवर: {h(calc.format_currency(result.recommended_cover))}</b>")
        return (
            f"🛡️ <b>Human Life Value — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Monthly Expense: ₹{v['monthly_expense']:,.0f}\n"
            f"🏦 Loans: ₹{v['loans']:,.0f} | 👶 Children: ₹{v['children']:,.0f}\n"
            f"🛡️ Existing Cover: ₹{v['existing_cover']:,.0f}\n\n"
            f"✅ <b>Recommended Cover: {h(calc.format_currency(result.recommended_cover))}</b>")

    elif calc_type == "retirement":
        if hi:
            return (
                f"🏖️ <b>रिटायरमेंट प्लानर — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 आयु: {v['current_age']} → {v['retire_age']} | जीवन: {v['life_exp']}\n"
                f"💰 खर्च: ₹{v['monthly_expense']:,.0f}/महीना\n\n"
                f"💰 <b>कॉर्पस: {h(calc.format_currency(result.corpus_needed))}</b>\n"
                f"📊 <b>SIP: {h(calc.format_currency(result.monthly_sip_needed))}/महीना</b>")
        return (
            f"🏖️ <b>Retirement Planner — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Age: {v['current_age']} → {v['retire_age']} | Life: {v['life_exp']}\n"
            f"💰 Expense: ₹{v['monthly_expense']:,.0f}/month\n\n"
            f"💰 <b>Corpus: {h(calc.format_currency(result.corpus_needed))}</b>\n"
            f"📊 <b>SIP: {h(calc.format_currency(result.monthly_sip_needed))}/month</b>")

    elif calc_type == "emi":
        text = (f"💳 <b>{'प्रीमियम EMI — परिणाम' if hi else 'Premium EMI — Results'}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"{'नेट प्रीमियम' if hi else 'Net Premium'}: <b>{h(calc.format_currency(result.net_premium))}</b>\n"
                f"{'डाउन पेमेंट' if hi else 'Down Payment'}: {h(calc.format_currency(result.down_payment))}\n\n"
                f"📊 <b>EMI {'विकल्प' if hi else 'Options'}:</b>\n")
        for opt in result.emi_options:
            text += f"  {opt['months']}mo → {h(calc.format_currency(opt['monthly_emi']))}/mo\n"
        return text

    elif calc_type == "health":
        if hi:
            return (
                f"🏥 <b>स्वास्थ्य बीमा — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 आयु: {result.age} | परिवार: {h(str(result.family_size))}\n"
                f"✅ <b>अनुशंसित: {h(calc.format_currency(result.recommended_si))}</b>\n"
                f"🔴 कमी: {h(calc.format_currency(result.gap))}")
        return (
            f"🏥 <b>Health Cover — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Age: {result.age} | Family: {h(str(result.family_size))}\n"
            f"✅ <b>Recommended: {h(calc.format_currency(result.recommended_si))}</b>\n"
            f"🔴 Gap: {h(calc.format_currency(result.gap))}")

    elif calc_type == "sip":
        if hi:
            return (
                f"📈 <b>SIP vs एकमुश्त — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 राशि: {h(calc.format_currency(result.investment_amount))}\n"
                f"📅 {result.years} वर्ष @ {result.expected_return}%\n\n"
                f"📊 एकमुश्त: <b>{h(calc.format_currency(result.lumpsum_maturity))}</b>\n"
                f"📊 SIP: <b>{h(calc.format_currency(result.sip_maturity))}</b>\n"
                f"🏆 विजेता: <b>{h(str(result.winner))}</b>")
        return (
            f"📈 <b>SIP vs Lumpsum — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Amount: {h(calc.format_currency(result.investment_amount))}\n"
            f"📅 {result.years} years @ {result.expected_return}%\n\n"
            f"📊 Lumpsum: <b>{h(calc.format_currency(result.lumpsum_maturity))}</b>\n"
            f"📊 SIP: <b>{h(calc.format_currency(result.sip_maturity))}</b>\n"
            f"🏆 Winner: <b>{h(str(result.winner))}</b>")

    elif calc_type == "mfsip":
        if hi:
            return (
                f"📊 <b>MF SIP प्लानर — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"🎯 लक्ष्य: {h(calc.format_currency(result.goal_amount))}\n"
                f"📅 {result.years} वर्ष @ {result.annual_return}%\n\n"
                f"📈 <b>SIP: {h(calc.format_currency(result.monthly_sip))}/महीना</b>\n"
                f"💰 कुल निवेश: {h(calc.format_currency(result.total_invested))}\n"
                f"📊 कॉर्पस: {h(calc.format_currency(result.expected_corpus))}")
        return (
            f"📊 <b>MF SIP Planner — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 Goal: {h(calc.format_currency(result.goal_amount))}\n"
            f"📅 {result.years} years @ {result.annual_return}%\n\n"
            f"📈 <b>SIP: {h(calc.format_currency(result.monthly_sip))}/month</b>\n"
            f"💰 Invested: {h(calc.format_currency(result.total_invested))}\n"
            f"📊 Corpus: {h(calc.format_currency(result.expected_corpus))}")

    elif calc_type == "ulip":
        if hi:
            return (
                f"⚖️ <b>ULIP vs MF — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 {h(calc.format_currency(result.investment_amount))}/वर्ष × {result.years} वर्ष\n\n"
                f"📊 ULIP: <b>{h(calc.format_currency(result.ulip_maturity))}</b>\n"
                f"📈 MF: <b>{h(calc.format_currency(result.mf_maturity))}</b>\n"
                f"🏆 विजेता: <b>{h(str(result.winner))}</b>")
        return (
            f"⚖️ <b>ULIP vs MF — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 {h(calc.format_currency(result.investment_amount))}/yr × {result.years} yrs\n\n"
            f"📊 ULIP: <b>{h(calc.format_currency(result.ulip_maturity))}</b>\n"
            f"📈 MF: <b>{h(calc.format_currency(result.mf_maturity))}</b>\n"
            f"🏆 Winner: <b>{h(str(result.winner))}</b>")

    elif calc_type == "nps":
        if hi:
            return (
                f"🏛️ <b>NPS प्लानर — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 {h(calc.format_currency(result.monthly_contribution))}/महीना × {result.years_to_retire} वर्ष\n\n"
                f"📊 कॉर्पस: <b>{h(calc.format_currency(result.total_corpus))}</b>\n"
                f"💳 पेंशन: <b>{h(calc.format_currency(result.monthly_pension_estimate))}/महीना</b>\n"
                f"🏷️ टैक्स बचत: {h(calc.format_currency(result.tax_saved_yearly))}/वर्ष")
        return (
            f"🏛️ <b>NPS Planner — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 {h(calc.format_currency(result.monthly_contribution))}/mo × {result.years_to_retire} yrs\n\n"
            f"📊 Corpus: <b>{h(calc.format_currency(result.total_corpus))}</b>\n"
            f"💳 Pension: <b>{h(calc.format_currency(result.monthly_pension_estimate))}/month</b>\n"
            f"🏷️ Tax Saved: {h(calc.format_currency(result.tax_saved_yearly))}/year")

    elif calc_type == "stepupsip":
        if hi:
            return (
                f"📈 <b>स्टेप-अप SIP प्लानर — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 शुरुआती SIP: {h(calc.format_currency(result.initial_monthly_sip))}/माह\n"
                f"📊 वार्षिक वृद्धि: {result.annual_step_up}% | {result.years} वर्ष @ {result.annual_return}%\n\n"
                f"🚀 कॉर्पस: <b>{h(calc.format_currency(result.total_corpus))}</b>\n"
                f"💰 निवेश: {h(calc.format_currency(result.total_invested))}\n"
                f"⚡ स्टेप-अप लाभ: <b>{h(calc.format_currency(result.stepup_advantage))}</b>")
        return (
            f"📈 <b>Step-Up SIP — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Starting SIP: {h(calc.format_currency(result.initial_monthly_sip))}/month\n"
            f"📊 Step-Up: {result.annual_step_up}% | {result.years} yrs @ {result.annual_return}%\n\n"
            f"🚀 Corpus: <b>{h(calc.format_currency(result.total_corpus))}</b>\n"
            f"💰 Invested: {h(calc.format_currency(result.total_invested))}\n"
            f"⚡ Step-Up Advantage: <b>{h(calc.format_currency(result.stepup_advantage))}</b>")

    elif calc_type == "swp":
        _status_hi = "✅ टिकाऊ" if result.is_sustainable else f"⚠️ {result.corpus_lasted_months} महीनों में समाप्त"
        _status_en = "✅ Sustainable" if result.is_sustainable else f"⚠️ Depleted in {result.corpus_lasted_months} months"
        if hi:
            return (
                f"💸 <b>SWP योजना — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"🏦 कॉर्पस: {h(calc.format_currency(result.initial_corpus))}\n"
                f"💳 मासिक निकासी: {h(calc.format_currency(result.monthly_withdrawal))}\n\n"
                f"📋 कुल निकासी: {h(calc.format_currency(result.total_withdrawn))}\n"
                f"🏦 शेष: <b>{h(calc.format_currency(result.remaining_corpus))}</b>\n"
                f"स्थिति: <b>{_status_hi}</b>")
        return (
            f"💸 <b>SWP Plan — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"🏦 Corpus: {h(calc.format_currency(result.initial_corpus))}\n"
            f"💳 Monthly: {h(calc.format_currency(result.monthly_withdrawal))}\n\n"
            f"📋 Total Withdrawn: {h(calc.format_currency(result.total_withdrawn))}\n"
            f"🏦 Remaining: <b>{h(calc.format_currency(result.remaining_corpus))}</b>\n"
            f"Status: <b>{_status_en}</b>")

    elif calc_type == "delaycost":
        if hi:
            return (
                f"⏰ <b>विलंब लागत — परिणाम</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 SIP: {h(calc.format_currency(result.monthly_sip))}/माह | {result.years} वर्ष\n"
                f"⏳ विलंब: {result.delay_years} वर्ष\n\n"
                f"📊 आज शुरू: <b>{h(calc.format_currency(result.corpus_on_time))}</b>\n"
                f"{result.delay_years} वर्ष बाद: {h(calc.format_currency(result.corpus_delayed))}\n"
                f"🔴 विलंब की कीमत: <b>{h(calc.format_currency(result.cost_of_delay))}</b>\n"
                f"⚡ बराबरी के लिए: <b>{h(calc.format_currency(result.extra_sip_needed))}/माह</b>")
        return (
            f"⏰ <b>Cost of Delay — Results</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 SIP: {h(calc.format_currency(result.monthly_sip))}/month | {result.years} yrs\n"
            f"⏳ Delay: {result.delay_years} years\n\n"
            f"📊 Start Today: <b>{h(calc.format_currency(result.corpus_on_time))}</b>\n"
            f"After {result.delay_years} yrs: {h(calc.format_currency(result.corpus_delayed))}\n"
            f"🔴 Cost of Delay: <b>{h(calc.format_currency(result.cost_of_delay))}</b>\n"
            f"⚡ To match: <b>{h(calc.format_currency(result.extra_sip_needed))}/month</b>")

    return "❌ Unknown calculator"


# ── Intent: SHOW TEAM (voice) ────────────────────────────────────────────
async def _voice_handle_show_team(processing_msg, data, agent, lang):
    """Voice: show team members — delegates to cmd_team logic."""
    hi = lang == 'hi'
    plan = agent.get('_plan') or agent.get('plan', 'trial')

    if plan not in ('team', 'enterprise'):
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
            f"{'🔒 टीम फीचर Team/Enterprise प्लान में उपलब्ध है।' if hi else '🔒 Team feature is available on Team/Enterprise plans.'}\n"
            f"{'अपग्रेड करने के लिए /plans टाइप करें।' if hi else 'Type /plans to upgrade.'}",
            parse_mode=ParseMode.HTML)
        return

    if agent.get('role') not in ('owner', 'admin'):
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
            f"{'⚠️ केवल फर्म ओनर/एडमिन ही टीम प्रबंधित कर सकते हैं।' if hi else '⚠️ Only firm owners/admins can manage the team.'}",
            parse_mode=ParseMode.HTML)
        return

    agents_list = await db.get_agents_by_tenant_all(agent['tenant_id'])
    cap = await db.can_add_agent(agent['tenant_id'])

    lines = [f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n",
             f"👥 <b>{'टीम प्रबंधन' if hi else 'Team Management'}</b>\n━━━━━━━━━━━━━━━━━━\n",
             f"📊 {'एजेंट' if hi else 'Agents'}: <b>{cap['current']}/{cap['max']}</b> ({cap['plan'].title()})\n"]

    for a in agents_list:
        status = "✅" if a.get('is_active') else "❌"
        role_icon = "👑" if a['role'] == 'owner' else "👤"
        leads = a.get('lead_count', 0)
        lines.append(f"{role_icon} {status} <b>{h(a['name'])}</b> ({a['role']}) — {leads} {'लीड' if hi else 'leads'}")

    lines.append(f"\n💡 {'विस्तृत प्रबंधन के लिए /team टाइप करें' if hi else 'Type /team for full management'}")
    await processing_msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── Intent: SHOW PLANS (voice) ───────────────────────────────────────────
async def _voice_handle_show_plans(processing_msg, data, agent, lang):
    """Voice: show subscription plans."""
    hi = lang == 'hi'
    plan = agent.get('_plan') or agent.get('plan', 'trial')
    tenant = await db.get_tenant(agent['tenant_id']) if agent.get('tenant_id') else None
    status = tenant.get('subscription_status', 'unknown') if tenant else 'unknown'

    status_line = ""
    if status == 'trial':
        status_line = f"📅 {'वर्तमान: फ्री ट्रायल' if hi else 'Current: Free Trial'}\n"
    elif status == 'active':
        status_line = f"✅ {'वर्तमान' if hi else 'Current'}: {plan.title()} ({'सक्रिय' if hi else 'Active'})\n"
    elif status == 'expired':
        status_line = f"⚠️ {'वर्तमान: समाप्त' if hi else 'Current: Expired'}\n"

    msg = (
        f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
        f"💎 <b>{'सारथी-AI प्लान' if hi else 'Sarathi-AI Plans'}</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"{status_line}\n"
        f"🧑 <b>Solo Advisor</b> — ₹199/{'माह' if hi else 'mo'}\n"
        f"   └ {'एडमिन, पूर्ण CRM, कैलकुलेटर' if hi else 'Admin only, full CRM, calculators'}\n\n"
        f"👥 <b>Team</b> — ₹799/{'माह' if hi else 'mo'}\n"
        f"   └ {'एडमिन + 5 एडवाइजर, WhatsApp, कैम्पेन' if hi else 'Admin + 5 advisors, WhatsApp API, campaigns'}\n\n"
        f"🏢 <b>Enterprise</b> — ₹1,999/{'माह' if hi else 'mo'}\n"
        f"   └ {'एडमिन + 25 एडवाइजर, एडमिन कंट्रोल, API' if hi else 'Admin + 25 advisors, admin controls, API'}\n\n"
        f"💡 {'विस्तृत जानकारी के लिए /plans टाइप करें' if hi else 'Type /plans for details & subscribe'}"
    )
    await processing_msg.edit_text(msg, parse_mode=ParseMode.HTML)


# ── Intent: SHOW SETTINGS (voice) ────────────────────────────────────────
async def _voice_handle_show_settings(processing_msg, data, agent, lang):
    """Voice: show settings menu."""
    hi = lang == 'hi'
    await processing_msg.edit_text(
        f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
        f"⚙️ {'सेटिंग्स मेनू खोलने के लिए /settings टाइप करें' if hi else 'Type /settings to open the settings menu'}",
        parse_mode=ParseMode.HTML)


# ── Intent: SA PANEL (voice) ─────────────────────────────────────────────
async def _voice_handle_sa_panel(processing_msg, data, agent, lang):
    """Voice: open super admin panel."""
    hi = lang == 'hi'
    if agent.get('phone', '') not in SUPERADMIN_PHONES:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
            f"{'🔒 सुपर एडमिन एक्सेस केवल अधिकृत उपयोगकर्ताओं के लिए।' if hi else '🔒 Super-admin access only.'}",
            parse_mode=ParseMode.HTML)
        return

    # Check SA OTP session
    sa_session = _sa_sessions.get(str(agent.get('phone', '')))
    if not sa_session or (time.time() - sa_session['ts']) > SA_SESSION_TIMEOUT:
        await processing_msg.edit_text(
            f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
            f"{'🔐 SA सेशन सक्रिय नहीं है। कृपया /sa टाइप करके OTP से लॉगिन करें।' if hi else '🔐 SA session not active. Please type /sa and verify OTP to login.'}",
            parse_mode=ParseMode.HTML)
        return

    stats = await _sa_get_stats()
    inactive_count = len(await db.get_inactive_agents(60))
    keyboard = [
        [InlineKeyboardButton("📊 Tenants", callback_data="sa_tenants"),
         InlineKeyboardButton("📈 Stats", callback_data="sa_stats")],
        [InlineKeyboardButton("🤖 Bots", callback_data="sa_bots"),
         InlineKeyboardButton("➕ Create Firm", callback_data="sa_create_firm")],
        [InlineKeyboardButton(f"😴 Inactive Agents ({inactive_count})", callback_data="sa_inactive")],
    ]
    inactive_line = f"\n😴 Inactive (60d+): {inactive_count}" if inactive_count else ""
    await processing_msg.edit_text(
        f"🎙️ <i>{h(data.get('transcript', '')[:100])}</i>\n\n"
        f"🛡️ <b>Super Admin Panel</b>\n\n"
        f"👥 Tenants: {stats['total']}  |  🟢 Active: {stats['active']}\n"
        f"⏳ Trials: {stats['trials']}  |  💰 Paid: {stats['paid']}\n"
        f"❌ Expired: {stats['expired']}  |  👤 Agents: {stats['agents']}\n"
        f"📋 Leads: {stats['leads']}{inactive_line}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard))


# ── Intent: GENERAL (unclear intent) ─────────────────────────────────────
async def _voice_handle_general(processing_msg, data, agent, lang,
                                 duration, context):
    """Handle voice with unclear intent — show transcript + action buttons."""
    context.user_data['voice_data'] = data
    context.user_data['voice_duration'] = duration

    transcript = data.get('transcript', 'N/A')

    title = "🎙️ <b>वॉइस नोट</b>" if lang == 'hi' else "🎙️ <b>Voice Note</b>"
    what_do = ("क्या करना चाहेंगे?" if lang == 'hi' else "What would you like to do?")

    msg = (
        f"{title}\n━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 <i>{h(transcript[:400])}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n{what_do}"
    )

    kb = [
        [InlineKeyboardButton(
            "➕ " + ("लीड बनाएँ" if lang == 'hi' else "Create Lead"),
            callback_data="voice_confirm"),
         InlineKeyboardButton(
            "📝 " + ("मीटिंग लॉग" if lang == 'hi' else "Log Meeting"),
            callback_data="voice_as_meeting")],
        [InlineKeyboardButton(
            "⏰ " + ("रिमाइंडर" if lang == 'hi' else "Reminder"),
            callback_data="voice_as_reminder"),
         InlineKeyboardButton(
            "❌ " + ("हटाएँ" if lang == 'hi' else "Discard"),
            callback_data="voice_discard")],
    ]

    await processing_msg.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML)


# ── Voice Calculator Multi-Turn Helpers ──────────────────────────────────

async def _voice_calc_multiturn(processing_msg, voice_ctx, transcript,
                                 data, agent, lang, context):
    """Handle subsequent voice/text input for missing calculator params."""
    hi = lang == 'hi'
    calc_type = voice_ctx['calc_type']
    values = voice_ctx['values']
    missing_keys = voice_ctx['missing_keys']
    step = voice_ctx.get('missing_step', 0)

    if step >= len(missing_keys):
        # All params collected
        context.user_data.pop('voice_context', None)
        await _voice_calc_compute_and_show(
            processing_msg, calc_type, values, data, agent, lang, context)
        return

    current_key = missing_keys[step]
    params_def = _CALC_PARAMS[calc_type]['params']
    param = next((p for p in params_def if p['key'] == current_key), None)
    if not param:
        context.user_data.pop('voice_context', None)
        return

    # Try to extract the value from the voice transcript
    # The AI might have already parsed calc_params in this voice note
    voice_params = (data or {}).get('calc_params') or {}
    raw = voice_params.get(current_key)

    if raw is None:
        if param.get('type') == 'choice':
            # For choice params, try matching transcript against allowed values
            allowed = [str(a).lower() for a in param.get('allowed', [])]
            t_lower = transcript.lower().strip()
            for a in allowed:
                if a in t_lower:
                    raw = a
                    break
        else:
            # Try to parse a number from the transcript (digits, words, Hindi)
            raw = _extract_number_from_text(transcript)

    if raw is not None:
        val, err = _calc_validate_input(param, str(raw), lang)
        if err is None:
            values[current_key] = val
            voice_ctx['missing_step'] = step + 1
            voice_ctx['values'] = values
            context.user_data['voice_context'] = voice_ctx

            # Check if more params needed
            if step + 1 >= len(missing_keys):
                context.user_data.pop('voice_context', None)
                await _voice_calc_compute_and_show(
                    processing_msg, calc_type, values, data, agent, lang, context)
                return

            # Ask for next missing param
            next_key = missing_keys[step + 1]
            next_param = next((p for p in params_def if p['key'] == next_key), None)
            if next_param:
                await _show_calc_param_prompt(
                    processing_msg, calc_type, values, next_param,
                    len(missing_keys) - step - 1, params_def, hi)
            return

    # Could not parse — re-ask same param
    await _show_calc_param_prompt(
        processing_msg, calc_type, values, param,
        len(missing_keys) - step, params_def, hi)


async def _text_calc_multiturn(update, voice_ctx, text, context):
    """Handle text input for multi-turn calculator param collection."""
    agent = await _require_agent_auth(update, context)
    if not agent:
        return
    lang = agent.get('lang', 'en')
    hi = lang == 'hi'
    calc_type = voice_ctx['calc_type']
    values = voice_ctx['values']
    missing_keys = voice_ctx['missing_keys']
    step = voice_ctx.get('missing_step', 0)

    if step >= len(missing_keys):
        context.user_data.pop('voice_context', None)
        processing = await update.message.reply_text(
            f"🧮 {'कैलकुलेट कर रहा हूँ' if hi else 'Calculating'}...",
            parse_mode=ParseMode.HTML)
        await _voice_calc_compute_and_show(
            processing, calc_type, values, None, agent, lang, context)
        return

    current_key = missing_keys[step]
    params_def = _CALC_PARAMS[calc_type]['params']
    param = next((p for p in params_def if p['key'] == current_key), None)
    if not param:
        context.user_data.pop('voice_context', None)
        return

    val, err = _calc_validate_input(param, text, lang)
    if err:
        title = _CALC_PARAMS[calc_type].get('title_hi' if hi else 'title',
                                              _CALC_PARAMS[calc_type]['title'])
        btns = param.get('buttons', [])
        keyboard = []
        row = []
        for bv in btns:
            display = param['fmt'].format(bv) if isinstance(bv, (int, float)) else str(bv)
            row.append(InlineKeyboardButton(display, callback_data=f"vcparam_{bv}"))
            if len(row) >= 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        await update.message.reply_text(
            f"{title}\n━━━━━━━━━━━━━━━━━━\n\n{err}",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode=ParseMode.HTML)
        return

    values[current_key] = val
    voice_ctx['missing_step'] = step + 1
    voice_ctx['values'] = values
    context.user_data['voice_context'] = voice_ctx

    if step + 1 >= len(missing_keys):
        context.user_data.pop('voice_context', None)
        processing = await update.message.reply_text(
            f"🧮 {'कैलकुलेट कर रहा हूँ' if hi else 'Calculating'}...",
            parse_mode=ParseMode.HTML)
        await _voice_calc_compute_and_show(
            processing, calc_type, values, None, agent, lang, context)
        return

    # Ask next param
    next_key = missing_keys[step + 1]
    next_param = next((p for p in params_def if p['key'] == next_key), None)
    if next_param:
        remaining = len(missing_keys) - step - 1
        label = next_param.get('prompt_hi' if hi else 'prompt', next_param['prompt'])
        btns = next_param.get('buttons', [])
        keyboard = []
        row = []
        for bv in btns:
            display = next_param['fmt'].format(bv) if isinstance(bv, (int, float)) else str(bv)
            row.append(InlineKeyboardButton(display, callback_data=f"vcparam_{bv}"))
            if len(row) >= 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        plabel = param.get('prompt_hi' if hi else 'prompt', param['prompt'])
        disp = param['fmt'].format(val) if isinstance(val, (int, float)) else str(val)
        title = _CALC_PARAMS[calc_type].get('title_hi' if hi else 'title',
                                              _CALC_PARAMS[calc_type]['title'])
        await update.message.reply_text(
            f"{title}\n━━━━━━━━━━━━━━━━━━\n"
            f"  ✅ {plabel}: <b>{disp}</b>\n\n"
            f"📊 <b>{'बाकी' if hi else 'Remaining'}: {remaining}</b>\n\n"
            f"<b>{label}</b> {'दर्ज करें' if hi else 'enter'}:",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode=ParseMode.HTML)


async def _show_calc_param_prompt(msg_obj, calc_type, values, param, remaining, params_def, hi):
    """Show prompt for a single calculator parameter."""
    title = _CALC_PARAMS[calc_type].get('title_hi' if hi else 'title',
                                          _CALC_PARAMS[calc_type]['title'])
    label = param.get('prompt_hi' if hi else 'prompt', param['prompt'])
    btns = param.get('buttons', [])
    keyboard = []
    row = []
    for bv in btns:
        display = param['fmt'].format(bv) if isinstance(bv, (int, float)) else str(bv)
        row.append(InlineKeyboardButton(display, callback_data=f"vcparam_{bv}"))
        if len(row) >= 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    got_str = ""
    for p in params_def:
        if p['key'] in values:
            v = values[p['key']]
            d = p['fmt'].format(v) if isinstance(v, (int, float)) else str(v)
            pl = p.get('prompt_hi' if hi else 'prompt', p['prompt'])
            got_str += f"  ✅ {pl}: <b>{d}</b>\n"
    if got_str:
        got_str += "\n"

    # Add cancel button at the bottom
    keyboard.append([InlineKeyboardButton(
        "❌ रद्द करें" if hi else "❌ Cancel",
        callback_data="voice_cancel")])
    await _safe_edit_text(msg_obj,
        f"{title}\n━━━━━━━━━━━━━━━━━━\n"
        f"{got_str}"
        f"📊 <b>{'बाकी' if hi else 'Remaining'}: {remaining}</b>\n\n"
        f"<b>{label}</b> {'दर्ज करें' if hi else 'enter'}:\n"
        f"{'वॉइस नोट, टाइप, या नीचे टैप करें' if hi else 'Voice note, type, or tap below'}:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


# ── Voice Cancel Callback ─────────────────────────────────────────────────

async def _voice_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel any pending multi-turn voice context (calculator, follow-up, etc.)."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('voice_context', None)
    context.user_data.pop('voice_data', None)
    agent = await db.get_agent(str(query.from_user.id))
    hi = (agent.get('lang', 'en') == 'hi') if agent else False
    await _safe_edit_text(query.message,
        f"{'❌ रद्द। वॉइस नोट भेजकर नया काम शुरू करें।' if hi else '❌ Cancelled. Send a voice note to start a new action.'}",
        parse_mode=ParseMode.HTML)


# ── Voice Confidence Choice Callback ─────────────────────────────────────

async def _vc_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle smart fallback buttons when confidence was low."""
    query = update.callback_query
    await query.answer()
    cb_data = query.data

    if cb_data == 'vc_dismiss':
        context.user_data.pop('vc_pending', None)
        agent = await db.get_agent(str(query.from_user.id))
        hi = (agent.get('lang', 'en') == 'hi') if agent else False
        await _safe_edit_text(query.message,
            f"{'👍 ठीक है, नया वॉइस नोट भेजें।' if hi else '👍 OK, send a new voice note.'}",
            parse_mode=ParseMode.HTML)
        return

    if not cb_data.startswith('vc_go_'):
        return

    chosen_intent = cb_data.replace('vc_go_', '')
    pending = context.user_data.pop('vc_pending', None)
    if not pending:
        return

    data = pending['data']
    agent = pending['agent']
    lang = pending['lang']
    duration = pending.get('duration', 0)
    data['intent'] = chosen_intent
    data['confidence'] = 'high'  # User confirmed

    # Re-process through the intent routing — send a processing message
    try:
        await _safe_edit_text(query.message,
            f"{'⏳ प्रोसेस कर रहा हूँ...' if lang == 'hi' else '⏳ Processing...'}",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass

    # Re-route using the same logic as _voice_to_action intent chain
    processing_msg = query.message
    transcript = data.get('transcript', '')
    intent = chosen_intent

    if intent == 'create_lead':
        await _voice_handle_create_lead(processing_msg, data, agent, lang, duration, context)
    elif intent == 'log_meeting':
        await _voice_handle_log_meeting(processing_msg, data, agent, lang, context)
    elif intent == 'update_stage':
        await _voice_handle_update_stage(processing_msg, data, agent, lang, context)
    elif intent == 'create_reminder':
        await _voice_handle_create_reminder(processing_msg, data, agent, lang)
    elif intent == 'add_note':
        await _voice_handle_add_note(processing_msg, data, agent, lang, context)
    elif intent == 'list_leads':
        await _voice_handle_list_leads(processing_msg, data, agent, lang)
    elif intent == 'show_pipeline':
        await _voice_handle_show_pipeline(processing_msg, data, agent, lang)
    elif intent == 'show_dashboard':
        await _voice_handle_show_dashboard(processing_msg, data, agent, lang)
    elif intent == 'show_renewals':
        await _voice_handle_show_renewals(processing_msg, data, agent, lang)
    elif intent == 'show_today':
        await _voice_handle_show_today(processing_msg, data, agent, lang)
    elif intent == 'setup_followup':
        await _voice_handle_setup_followup(processing_msg, data, agent, lang, context)
    elif intent == 'send_whatsapp':
        await _voice_handle_send_whatsapp(processing_msg, data, agent, lang, context)
    elif intent == 'send_greeting':
        await _voice_handle_send_greeting(processing_msg, data, agent, lang)
    elif intent == 'edit_lead':
        await _voice_handle_edit_lead(processing_msg, data, agent, lang, context)
    elif intent == 'ask_ai':
        await _voice_handle_ask_ai(processing_msg, data, agent, lang)
    elif intent == 'ai_lead_score':
        await _voice_handle_ai_lead_score(processing_msg, data, agent, lang)
    elif intent == 'ai_pitch':
        await _voice_handle_ai_tool(processing_msg, data, agent, lang, 'pitch')
    elif intent == 'ai_followup_suggest':
        await _voice_handle_ai_tool(processing_msg, data, agent, lang, 'followup')
    elif intent == 'ai_recommend':
        await _voice_handle_ai_tool(processing_msg, data, agent, lang, 'recommend')
    elif intent == 'open_calculator':
        await _voice_handle_open_calculator(processing_msg, data, agent, lang)
    elif intent == 'select_calculator':
        await _voice_handle_select_calculator(processing_msg, data, agent, lang)
    elif intent == 'calc_compute':
        await _voice_handle_calc_compute(processing_msg, data, agent, lang, context)
    elif intent == 'send_calc_result':
        await _voice_handle_send_calc_result(processing_msg, data, agent, lang, context)
    elif intent == 'show_team':
        await _voice_handle_show_team(processing_msg, data, agent, lang)
    elif intent == 'show_plans':
        await _voice_handle_show_plans(processing_msg, data, agent, lang)
    elif intent == 'show_settings':
        await _voice_handle_show_settings(processing_msg, data, agent, lang)
    elif intent == 'sa_panel':
        await _voice_handle_sa_panel(processing_msg, data, agent, lang)
    else:
        await _voice_handle_general(processing_msg, data, agent, lang, duration, context)


# ── Voice Calculator Callback Handlers ───────────────────────────────────

async def _vcalc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice calculator inline button callbacks (vcalc_, vcparam_)."""
    query = update.callback_query
    await query.answer()
    cb_data = query.data

    agent = await db.get_agent(str(query.from_user.id))
    if not agent:
        return
    lang = agent.get('lang', 'en')
    hi = lang == 'hi'

    # vcalc_menu — show calculator menu
    if cb_data == "vcalc_menu":
        await _voice_handle_open_calculator(
            query, {'transcript': ''}, agent, lang)
        return

    # vcalc_{calc_type} — start interactive calculator via ConversationHandler
    if cb_data.startswith("vcalc_") and not cb_data.startswith("vcalc_send_"):
        calc_type = cb_data.replace("vcalc_", "")
        if calc_type in _CALC_PARAMS:
            # Show param hints + step-by-step button
            params = _CALC_PARAMS[calc_type]['params']
            title = _CALC_PARAMS[calc_type].get('title_hi' if hi else 'title',
                                                  _CALC_PARAMS[calc_type]['title'])
            param_list = ""
            for i, p in enumerate(params, 1):
                label = p.get('prompt_hi' if hi else 'prompt', p['prompt'])
                param_list += f"  {i}. {label}\n"
            _hint = ("वॉइस नोट में सारे नंबर बोलें" if hi
                     else "Say all numbers in one voice note")
            _example = _voice_calc_example(calc_type, hi)
            keyboard = [
                [InlineKeyboardButton(
                    "🧮 " + ("बटन से भरें" if hi else "Fill Step-by-Step"),
                    callback_data=f"csel_{calc_type}")],
                [InlineKeyboardButton(
                    "🔙 " + ("कैलकुलेटर मेनू" if hi else "Calculator Menu"),
                    callback_data="vcalc_menu")],
            ]
            await query.edit_message_text(
                f"{title}\n━━━━━━━━━━━━━━━━━━\n\n"
                f"{'ज़रूरी जानकारी' if hi else 'Required inputs'}:\n{param_list}\n"
                f"💡 <b>{_hint}</b>\n<i>{_example}</i>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML)
        return

    # vcalc_send_{calc_type}_{lead_id} — send result to lead via WhatsApp
    if cb_data.startswith("vcalc_send_"):
        parts = cb_data.replace("vcalc_send_", "").split("_", 1)
        if len(parts) == 2:
            calc_type, lead_id_str = parts
            try:
                lead_id = int(lead_id_str)
            except ValueError:
                return
            calc_text = context.user_data.get(f"last_calc_{calc_type}", "")
            if not calc_text:
                await query.edit_message_text(
                    "❌ " + ("परिणाम नहीं मिला" if hi else "No result found"))
                return

            lead = await db.get_lead(lead_id)
            if not lead or not lead.get('phone'):
                await query.edit_message_text(
                    "❌ " + ("लीड का फ़ोन नहीं मिला" if hi else "Lead phone not found"))
                return

            import re as _re_mod
            clean_text = _re_mod.sub(r'<[^>]+>', '', calc_text)
            agent_name = agent.get('name', 'Your Advisor')
            company = "Sarathi-AI"
            try:
                tenant = await db.get_tenant(agent['tenant_id'])
                if tenant and tenant.get('firm_name'):
                    company = tenant['firm_name']
            except Exception:
                pass

            result = await wa.send_calc_report(
                lead['phone'], lead['name'], calc_type,
                clean_text, agent_name=agent_name, company=company)

            if result.get('success'):
                if result.get('method') == 'link':
                    link = result.get('wa_link', '')
                    await query.edit_message_text(
                        f"📤 <b>{'भेजने के लिए क्लिक करें' if hi else 'Click to send'}</b>\n\n"
                        f"👤 {h(lead['name'])}\n"
                        f"📱 <a href=\"{h(link)}\">WhatsApp {'पर भेजें' if hi else 'Send'}</a>",
                        parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                else:
                    await query.edit_message_text(
                        f"✅ {'भेज दिया' if hi else 'Sent'}! 📤\n\n"
                        f"👤 {h(lead['name'])}\n📱 {h(lead.get('phone', ''))}",
                        parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text(
                    f"❌ {'भेजने में त्रुटि' if hi else 'Failed to send'}: "
                    f"{h(str(result.get('error', 'Unknown'))[:100])}",
                    parse_mode=ParseMode.HTML)
        return

    # vcparam_{value} — quick-select button during multi-turn calc
    if cb_data.startswith("vcparam_"):
        raw = cb_data.replace("vcparam_", "")
        voice_ctx = context.user_data.get('voice_context')
        if not voice_ctx or voice_ctx.get('pending_action') != 'calc_compute':
            return

        calc_type = voice_ctx['calc_type']
        values = voice_ctx['values']
        missing_keys = voice_ctx['missing_keys']
        step = voice_ctx.get('missing_step', 0)

        if step >= len(missing_keys):
            return

        current_key = missing_keys[step]
        params_def = _CALC_PARAMS[calc_type]['params']
        param = next((p for p in params_def if p['key'] == current_key), None)
        if not param:
            return

        val, err = _calc_validate_input(param, raw, lang)
        if err:
            return

        values[current_key] = val
        voice_ctx['missing_step'] = step + 1
        voice_ctx['values'] = values
        context.user_data['voice_context'] = voice_ctx

        if step + 1 >= len(missing_keys):
            context.user_data.pop('voice_context', None)
            await _voice_calc_compute_and_show(
                query, calc_type, values, None, agent, lang, context)
            return

        # Ask next
        next_key = missing_keys[step + 1]
        next_param = next((p for p in params_def if p['key'] == next_key), None)
        if next_param:
            remaining = len(missing_keys) - step - 1
            await _show_calc_param_prompt(
                query, calc_type, values, next_param, remaining, params_def, hi)
        return


# ── Voice callback handler (updated for multi-intent) ────────────────────
async def _voice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice-to-action confirm/discard/fill/stage/convert callbacks."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "voice_fill":
        return await _voice_fill_callback(update, context)

    if data == "voice_discard":
        context.user_data.pop('voice_data', None)
        context.user_data.pop('voice_duration', None)
        agent = await db.get_agent(str(query.from_user.id))
        lang = agent.get('lang', 'en') if agent else 'en'
        msg = "🗑️ " + ("वॉइस नोट हटाया।" if lang == 'hi' else "Voice note discarded.")
        await query.edit_message_text(msg)
        return

    if data == "voice_convert_lead":
        # Convert a failed meeting-log into a create-lead flow
        voice_data = context.user_data.get('voice_data')
        if not voice_data:
            await query.edit_message_text("⚠️ No data. Send a new voice note.")
            return
        voice_data['intent'] = 'create_lead'
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        lang = agent.get('lang', 'en')
        duration = context.user_data.get('voice_duration', 0)
        await _voice_handle_create_lead(
            query.message, voice_data, agent, lang, duration, context)
        return

    if data == "voice_as_meeting":
        voice_data = context.user_data.get('voice_data')
        if not voice_data:
            await query.edit_message_text("⚠️ No data. Send a new voice note.")
            return
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        lang = agent.get('lang', 'en')
        voice_data['meeting_summary'] = voice_data.get('notes') or voice_data.get('transcript', '')[:200]
        await _voice_handle_log_meeting(query.message, voice_data, agent, lang, context)
        return

    if data == "voice_as_reminder":
        voice_data = context.user_data.get('voice_data')
        if not voice_data:
            await query.edit_message_text("⚠️ No data. Send a new voice note.")
            return
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            return
        lang = agent.get('lang', 'en')
        voice_data['reminder_message'] = voice_data.get('notes') or voice_data.get('transcript', '')[:200]
        await _voice_handle_create_reminder(query.message, voice_data, agent, lang)
        return

    if data.startswith("vstg_"):
        # Voice stage picker callback: vstg_{lead_id}_{stage}
        parts = data.split("_", 2)
        if len(parts) == 3:
            try:
                lead_id = int(parts[1])
                new_stage = parts[2]
            except ValueError:
                return
            agent = await db.get_agent(str(query.from_user.id))
            if not agent:
                return
            lang = agent.get('lang', 'en')
            lead = await db.get_lead(lead_id)
            if not lead or lead['agent_id'] != agent['agent_id']:
                await query.edit_message_text("❌ Lead not found or access denied.")
                return
            old_stage = lead.get('stage', 'prospect')
            success = await db.update_lead_stage(lead_id, new_stage)
            if success:
                await query.edit_message_text(
                    i18n.t(lang, "voice_stage_updated",
                           name=h(lead['name']),
                           lead_id=lead_id,
                           old_stage=h(old_stage),
                           new_stage=h(new_stage)),
                    parse_mode=ParseMode.HTML)
                if new_stage == 'closed_won':
                    import biz_reminders as _rem
                    asyncio.create_task(_rem.run_deal_won_celebration(
                        agent_id=agent['agent_id'],
                        lead_name=lead['name'],
                        premium=lead.get('premium_budget', 0) or 0))
            else:
                err = "❌ अपडेट नहीं हो पाया।" if lang == 'hi' else "❌ Failed to update."
                await query.edit_message_text(err)
        return

    if data == "voice_confirm":
        voice_data = context.user_data.pop('voice_data', None)
        voice_duration = context.user_data.pop('voice_duration', 0)
        if not voice_data:
            await query.edit_message_text("⚠️ No voice data found. Please try again.")
            return

        agent = await _require_agent_auth(update, context)
        if not agent:
            return
        lang = agent.get('lang', 'en')
        pending_intent = voice_data.get('intent', '')

        # ── Stage update confirmation ──
        if pending_intent == 'update_stage':
            lead_id = voice_data.get('lead_id')
            new_stage = voice_data.get('new_stage')
            lead = await db.get_lead(lead_id)
            if not lead or lead['agent_id'] != agent['agent_id']:
                await query.edit_message_text("❌ Lead not found or access denied.")
                return
            old_stage = lead.get('stage', 'prospect')
            success = await db.update_lead_stage(lead_id, new_stage)
            if success:
                await query.edit_message_text(
                    i18n.t(lang, "voice_stage_updated",
                           name=h(lead['name']),
                           lead_id=lead_id,
                           old_stage=h(old_stage),
                           new_stage=h(new_stage)),
                    parse_mode=ParseMode.HTML)
                _track_voice_context(context, intent='update_stage',
                                     lead_id=lead_id, lead_name=lead['name'])
                if new_stage == 'closed_won':
                    import biz_reminders as _rem
                    asyncio.create_task(_rem.run_deal_won_celebration(
                        agent_id=agent['agent_id'],
                        lead_name=lead['name'],
                        premium=lead.get('premium_budget', 0) or 0))
            else:
                hi = lang == 'hi'
                await query.edit_message_text(
                    "❌ " + ("स्टेज अपडेट नहीं हो पाया।" if hi else "Failed to update stage."))
            return

        # ── Create lead confirmation (default) ──
        name = voice_data.get('name') or 'Unknown Lead'
        phone = voice_data.get('phone')
        if phone:
            phone = _valid_phone(phone)

        need_type = voice_data.get('need_type') or 'general'
        city = voice_data.get('city')
        notes = voice_data.get('notes') or ''
        budget = voice_data.get('budget')
        follow_up = voice_data.get('follow_up')

        lead_id = await db.add_lead(
            agent_id=agent['agent_id'],
            name=name,
            phone=phone,
            city=city,
            need_type=need_type,
            notes=notes,
            premium_budget=float(budget) if budget else None,
            source="voice"
        )
        try:
            await db.mark_lead_dpdp_consent(lead_id)
        except Exception:
            pass

        # Set follow-up reminder if date was extracted
        followup_msg = ""
        if follow_up:
            try:
                fu_date = datetime.strptime(follow_up, '%Y-%m-%d')
                await db.add_reminder(
                    agent_id=agent['agent_id'],
                    reminder_type='follow_up',
                    due_date=fu_date.strftime('%Y-%m-%d'),
                    message=f"Follow up with {name}",
                    lead_id=lead_id
                )
                followup_msg = "\n📅 " + (f"रिमाइंडर: {fu_date.strftime('%d %b %Y')}"
                                          if lang == 'hi'
                                          else f"Reminder set: {fu_date.strftime('%d %b %Y')}")
            except ValueError:
                pass

        # Log interaction
        await db.log_interaction(
            lead_id=lead_id,
            agent_id=agent['agent_id'],
            interaction_type='voice_note',
            summary=f"Lead created via voice note: {notes[:100]}"
        )

        created_title = "✅ <b>वॉइस से लीड बनी!</b>" if lang == 'hi' else "✅ <b>Lead Created via Voice!</b>"
        _track_voice_context(context, intent='create_lead', lead_id=lead_id, lead_name=name)
        await query.edit_message_text(
            f"{created_title}\n\n"
            f"🆔 Lead #{lead_id}\n"
            f"👤 {h(name)}\n"
            f"📱 {h(phone or 'N/A')}\n"
            f"🏥 {h(need_type)}\n"
            f"🏙️ {h(city or 'N/A')}"
            f"{followup_msg}\n\n"
            f"/lead {lead_id}",
            parse_mode=ParseMode.HTML)
        # Post-action suggestion
        import biz_reminders as _rem
        asyncio.create_task(_rem.run_smart_post_action_suggestion(
            agent_telegram_id=agent.get('telegram_id', str(query.from_user.id)),
            action='create_lead',
            lead_name=name,
            lead_id=lead_id,
            lang=lang))


async def _voice_fill_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Fill Missing Details' button — prompt user for each missing field."""
    query = update.callback_query
    await query.answer()

    voice_data = context.user_data.get('voice_data')
    if not voice_data:
        await query.edit_message_text("⚠️ No voice data found. Please send a new voice note.")
        return

    # Determine which fields are missing and queue them
    fill_queue = []
    if not voice_data.get('name'):
        fill_queue.append('name')
    if not voice_data.get('phone'):
        fill_queue.append('phone')
    if not voice_data.get('need_type'):
        fill_queue.append('need_type')
    if not voice_data.get('city'):
        fill_queue.append('city')

    if not fill_queue:
        await query.edit_message_text("✅ All details are already filled!")
        return

    context.user_data['voice_fill_queue'] = fill_queue
    context.user_data['voice_fill_index'] = 0
    context.user_data['voice_fill_active'] = True

    agent = await db.get_agent(str(query.from_user.id))
    lang = agent.get('lang', 'en') if agent else 'en'

    field = fill_queue[0]
    prompts = {
        'name': "👤 " + ("<b>लीड का नाम बताएं:</b>" if lang == 'hi' else "<b>Enter the lead's name:</b>"),
        'phone': "📱 " + ("<b>फ़ोन नंबर दें</b> (10 अंक):" if lang == 'hi' else "<b>Enter phone number</b> (10-digit):"),
        'need_type': "🏥 " + ("<b>ज़रूरत चुनें:</b>\nhealth, term, retirement, child, investment, motor" if lang == 'hi' else "<b>Select need type:</b>\nhealth, term, retirement, child, investment, motor"),
        'city': "🏙️ " + ("<b>शहर का नाम:</b>" if lang == 'hi' else "<b>Enter city name:</b>"),
    }
    remaining = len(fill_queue)
    await query.edit_message_text(
        f"✏️ <b>{'जानकारी भरें' if lang == 'hi' else 'Fill Missing Details'}</b> "
        f"({remaining} {'फ़ील्ड' if lang == 'hi' else 'field' + ('s' if remaining > 1 else '')})\n\n"
        f"{prompts[field]}\n\n"
        f"<i>/cancel {'रद्द करें' if lang == 'hi' else 'to discard'}</i>",
        parse_mode=ParseMode.HTML)


async def _voice_fill_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for voice fill-in-the-blanks flow."""

    # ── Intercept: pending follow-up notes ──
    pending_note = context.user_data.get('pending_followup_note')
    if pending_note and update.message and update.message.text:
        # Expire pending note after 10 minutes
        try:
            asked = datetime.fromisoformat(pending_note.get('asked_at', ''))
            if (datetime.now() - asked).total_seconds() > 600:
                context.user_data.pop('pending_followup_note', None)
                pending_note = None
        except (ValueError, TypeError):
            context.user_data.pop('pending_followup_note', None)
            pending_note = None
    if pending_note and update.message and update.message.text:
        note_text = update.message.text.strip()
        if len(note_text) >= 2 and not note_text.startswith('/'):
            import aiosqlite
            iid = pending_note['interaction_id']
            agent = await db.get_agent(str(update.effective_user.id))
            if agent:
                # Get lead_id from the interaction
                async with aiosqlite.connect(db.DB_PATH) as conn:
                    conn.row_factory = aiosqlite.Row
                    row = await conn.execute(
                        "SELECT lead_id FROM interactions WHERE interaction_id = ?", (iid,))
                    result = await row.fetchone()
                if result:
                    lead_id = result['lead_id']
                    await db.add_lead_note(
                        lead_id=lead_id,
                        agent_id=agent['agent_id'],
                        note_text=note_text,
                        interaction_id=iid,
                        author_role='advisor')
                    context.user_data.pop('pending_followup_note', None)
                    hi = agent.get('lang', 'en') == 'hi'
                    if hi:
                        msg = "📋 Notes save हो गए! ✅\nDashboard पर timeline में दिखेंगे।"
                    else:
                        msg = "📋 Notes saved! ✅\nVisible on the lead timeline in your dashboard."
                    await update.message.reply_text(msg)
                    # Check if advisor needs help (async, fire-and-forget)
                    asyncio.create_task(_check_note_needs_admin(agent, lead_id, note_text))
                    return
            context.user_data.pop('pending_followup_note', None)

    if not context.user_data.get('voice_fill_active'):
        return  # Not in fill mode — let other handlers process

    # Auth check: verify agent is active with valid subscription
    agent = await _require_agent_auth(update, context)
    if not agent:
        context.user_data.pop('voice_fill_active', None)
        return

    voice_data = context.user_data.get('voice_data')
    fill_queue = context.user_data.get('voice_fill_queue', [])
    idx = context.user_data.get('voice_fill_index', 0)

    if not voice_data or idx >= len(fill_queue):
        context.user_data.pop('voice_fill_active', None)
        return

    field = fill_queue[idx]
    value = update.message.text.strip()

    # Validate the input
    valid_needs = {'health', 'term', 'endowment', 'ulip', 'child', 'retirement', 'motor', 'investment', 'nps', 'general'}

    if field == 'name':
        if len(value) < 2 or value.startswith('/'):
            await update.message.reply_text("❌ Please enter a valid name (at least 2 characters).")
            return
        voice_data['name'] = value
    elif field == 'phone':
        cleaned = _valid_phone(value)
        if not cleaned:
            await update.message.reply_text(
                "❌ Invalid phone number. Enter a 10-digit Indian mobile (e.g., 9876543210)."
            )
            return
        voice_data['phone'] = cleaned
    elif field == 'need_type':
        val_lower = value.lower().strip()
        if val_lower not in valid_needs:
            await update.message.reply_text(
                f"❌ Invalid. Choose one of: {', '.join(sorted(valid_needs))}"
            )
            return
        voice_data['need_type'] = val_lower
    elif field == 'city':
        if len(value) < 2:
            await update.message.reply_text("❌ Please enter a valid city name.")
            return
        voice_data['city'] = value

    # Move to next missing field
    idx += 1
    context.user_data['voice_fill_index'] = idx

    if idx < len(fill_queue):
        # Prompt next field
        next_field = fill_queue[idx]
        prompts = {
            'name': "👤 <b>Enter the lead's name:</b>",
            'phone': "📱 <b>Enter phone number</b> (10-digit Indian mobile):",
            'need_type': "🏥 <b>Select need type:</b>\nType one of: health, term, endowment, ulip, child, retirement, motor, investment, nps, general",
            'city': "🏙️ <b>Enter city name:</b>",
        }
        remaining = len(fill_queue) - idx
        await update.message.reply_text(
            f"✅ Got it!\n\n{prompts[next_field]}\n\n"
            f"<i>{remaining} field{'s' if remaining > 1 else ''} remaining</i>",
            parse_mode=ParseMode.HTML)
    else:
        # All fields filled — show updated confirmation
        context.user_data.pop('voice_fill_active', None)
        context.user_data.pop('voice_fill_queue', None)
        context.user_data.pop('voice_fill_index', None)

        name = voice_data.get('name') or 'Not detected'
        phone = voice_data.get('phone') or 'Not detected'
        need = voice_data.get('need_type') or 'Not detected'
        city = voice_data.get('city') or 'Not detected'
        budget = voice_data.get('budget')
        follow_up = voice_data.get('follow_up') or 'Not set'
        notes = voice_data.get('notes') or 'None'
        budget_str = f"₹{budget:,.0f}/mo" if budget else 'Not mentioned'

        msg = (
            "✅ <b>Updated Lead Details</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>Name:</b> {h(name)}\n"
            f"📱 <b>Phone:</b> {h(phone)}\n"
            f"🏥 <b>Need:</b> {h(need)}\n"
            f"🏙️ <b>City:</b> {h(city)}\n"
            f"💰 <b>Budget:</b> {budget_str}\n"
            f"📅 <b>Follow-up:</b> {h(follow_up)}\n"
            f"📋 <b>Notes:</b> {h(notes[:200])}\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "All details filled! Create this lead?"
        )
        kb = [
            [InlineKeyboardButton("✅ Create Lead", callback_data="voice_confirm"),
             InlineKeyboardButton("❌ Discard", callback_data="voice_discard")],
        ]
        await update.message.reply_text(
            msg, reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML)


# =============================================================================
#  CLAIMS HELPER — /claim — Assist with insurance claim filing
# =============================================================================

async def cmd_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the Claims Helper flow. Select a lead first."""
    agent = await _require_agent_auth(update, context)
    if not agent:
        return ConversationHandler.END

    lang = agent.get('lang', 'en')
    context.user_data['lang'] = lang

    # Get leads that have policies
    leads = await db.get_leads_by_agent(agent['agent_id'])
    if not leads:
        await update.message.reply_text(
            i18n.t(lang, "claims_no_leads"),
            parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    kb = []
    for lead in leads[:15]:
        policies = await db.get_policies_by_lead(lead['lead_id'])
        policy_count = len(policies) if policies else 0
        label = f"👤 {lead['name']}"
        if policy_count:
            word = "policy" if policy_count == 1 else "policies"
            if lang == 'hi':
                label += f" ({policy_count} पॉलिसी)"
            else:
                label += f" ({policy_count} {word})"
        kb.append([InlineKeyboardButton(
            label, callback_data=f"claimlead_{lead['lead_id']}")])

    await update.message.reply_text(
        i18n.t(lang, "claims_title") + "\n\n" +
        i18n.t(lang, "claim_select_client"),
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML)
    return CLAIM_LEAD


async def claim_select_lead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """After lead selection, show their policies or go to claim type."""
    query = update.callback_query
    await query.answer()
    lead_id = int(query.data.replace("claimlead_", ""))
    lang = context.user_data.get('lang', 'en')

    agent = await db.get_agent(str(query.from_user.id))
    if not agent:
        return ConversationHandler.END

    lead = await db.get_lead(lead_id)
    if not lead or lead['agent_id'] != agent['agent_id']:
        await query.edit_message_text(i18n.t(lang, "claim_lead_not_found"))
        return ConversationHandler.END

    context.user_data['claim_lead_id'] = lead_id
    context.user_data['claim_lead_name'] = lead['name']

    # Check if lead has policies
    policies = await db.get_policies_by_lead(lead_id)
    if policies:
        kb = []
        for p in policies[:10]:
            insurer = p.get('insurer', 'Unknown') if lang == 'en' else p.get('insurer', 'अज्ञात')
            plan = p.get('plan_name', 'N/A')
            label = f"📄 {insurer} — {plan}"
            if p.get('policy_number'):
                label += f" ({p['policy_number']})"
            kb.append([InlineKeyboardButton(
                label, callback_data=f"claimpol_{p['policy_id']}")])
        kb.append([InlineKeyboardButton(
            i18n.t(lang, "claim_no_policy_btn"), callback_data="claimpol_0")])

        await query.edit_message_text(
            i18n.t(lang, "claims_title") + f" — {h(lead['name'])}\n\n" +
            i18n.t(lang, "claim_select_policy"),
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML)
        return CLAIM_POLICY
    else:
        # No policies — go straight to claim type
        context.user_data['claim_policy_id'] = None
        return await _show_claim_types(query, context)


async def claim_select_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """After policy selection, show claim type options."""
    query = update.callback_query
    await query.answer()
    policy_id = int(query.data.replace("claimpol_", ""))
    context.user_data['claim_policy_id'] = policy_id if policy_id else None

    return await _show_claim_types(query, context)


async def _show_claim_types(query, context):
    """Display claim type selection buttons."""
    lang = context.user_data.get('lang', 'en')
    kb = [
        [InlineKeyboardButton(i18n.t(lang, "claim_type_health"), callback_data="claimtype_health")],
        [InlineKeyboardButton(i18n.t(lang, "claim_type_term"), callback_data="claimtype_term")],
        [InlineKeyboardButton(i18n.t(lang, "claim_type_motor"), callback_data="claimtype_motor")],
        [InlineKeyboardButton(i18n.t(lang, "claim_type_general"), callback_data="claimtype_general")],
    ]
    lead_name = context.user_data.get('claim_lead_name', 'Client')
    await query.edit_message_text(
        i18n.t(lang, "claims_title") + f" — {h(lead_name)}\n\n" +
        i18n.t(lang, "claim_what_type"),
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML)
    return CLAIM_TYPE


async def claim_select_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """After claim type selected, show document checklist + ask for description."""
    query = update.callback_query
    await query.answer()
    claim_type = query.data.replace("claimtype_", "")
    context.user_data['claim_type'] = claim_type
    lang = context.user_data.get('lang', 'en')

    lead_name = context.user_data.get('claim_lead_name', 'Client')
    docs = _get_claim_docs(claim_type, lang)

    type_label = i18n.t(lang, f"claim_type_{claim_type}_short")

    doc_list = "\n".join(f"  {d}" for d in docs)

    msg = (
        i18n.t(lang, "claims_title") + f" — {h(lead_name)}\n"
        f"📑 {i18n.t(lang, 'claim_type_label')}: {type_label}\n\n"
        f"<b>{i18n.t(lang, 'claim_docs_required')}</b>\n{doc_list}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{i18n.t(lang, 'claim_share_checklist')}\n\n"
        f"{i18n.t(lang, 'claim_describe_now')}\n"
        f"{i18n.t(lang, 'claim_describe_hint')}"
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
    return CLAIM_DESC


async def claim_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive claim description, ask for hospital (if health) or confirm."""
    desc = update.message.text.strip()
    lang = context.user_data.get('lang', 'en')
    if not desc or len(desc) < 5:
        await update.message.reply_text(
            i18n.t(lang, "claim_desc_too_short"))
        return CLAIM_DESC

    context.user_data['claim_desc'] = desc
    claim_type = context.user_data.get('claim_type', '')

    if claim_type == 'health':
        await update.message.reply_text(
            i18n.t(lang, "claim_hospital_name"),
            parse_mode=ParseMode.HTML)
        return CLAIM_HOSPITAL
    else:
        return await _show_claim_confirmation(update, context)


async def claim_hospital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive hospital name, then show confirmation."""
    hospital = update.message.text.strip()
    if hospital.lower() != 'skip':
        context.user_data['claim_hospital'] = hospital

    return await _show_claim_confirmation(update, context)


async def _show_claim_confirmation(update, context):
    """Display claim summary and ask for confirmation."""
    lang = context.user_data.get('lang', 'en')
    lead_name = context.user_data.get('claim_lead_name', 'Client')
    claim_type = context.user_data.get('claim_type', 'general')
    desc = context.user_data.get('claim_desc', 'N/A')
    hospital = context.user_data.get('claim_hospital', '')

    type_label = i18n.t(lang, f"claim_type_{claim_type}_short")

    msg = (
        i18n.t(lang, "claim_summary_title") + "\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>{i18n.t(lang, 'claim_client_label')}:</b> {h(lead_name)}\n"
        f"📑 <b>{i18n.t(lang, 'claim_type_label')}:</b> {type_label}\n"
        f"📝 <b>{i18n.t(lang, 'claim_desc_label')}:</b> {h(desc[:200])}\n"
    )
    if hospital:
        msg += f"🏥 <b>{i18n.t(lang, 'claim_hospital_label')}:</b> {h(hospital)}\n"

    msg += f"\n━━━━━━━━━━━━━━━━━━\n{i18n.t(lang, 'claim_submit_q')}"

    kb = [
        [InlineKeyboardButton(i18n.t(lang, "claim_submit_btn"), callback_data="claim_submit"),
         InlineKeyboardButton(i18n.t(lang, "claim_cancel_btn"), callback_data="claim_cancel")],
    ]
    await update.message.reply_text(
        msg, reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML)
    return CLAIM_CONFIRM


async def claim_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle claim submission or cancellation."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get('lang', 'en')

    if query.data == "claim_cancel":
        context.user_data.clear()
        await query.edit_message_text(i18n.t(lang, "claim_cancelled_msg"))
        return ConversationHandler.END

    if query.data == "claim_submit":
        agent = await db.get_agent(str(query.from_user.id))
        if not agent:
            await query.edit_message_text(i18n.t(lang, "claim_agent_not_found"))
            return ConversationHandler.END

        lead_id = context.user_data.get('claim_lead_id')
        policy_id = context.user_data.get('claim_policy_id')
        claim_type = context.user_data.get('claim_type', 'general')
        desc = context.user_data.get('claim_desc', '')
        hospital = context.user_data.get('claim_hospital')

        # Store English docs in DB for data consistency
        docs_en = _get_claim_docs(claim_type, 'en')
        docs_json = json.dumps([{"doc": d, "status": "pending"} for d in docs_en])

        claim_id = await db.add_claim(
            agent_id=agent['agent_id'],
            lead_id=lead_id,
            policy_id=policy_id,
            claim_type=claim_type,
            description=desc,
            hospital_name=hospital,
        )

        await db.update_claim(claim_id, documents_json=docs_json)

        await db.log_interaction(
            lead_id=lead_id,
            agent_id=agent['agent_id'],
            interaction_type='claim_initiated',
            summary=f"Claim #{claim_id} initiated: {claim_type} — {desc[:80]}"
        )

        lead_name = context.user_data.get('claim_lead_name', 'Client')
        type_label = i18n.t(lang, f"claim_type_{claim_type}_short")
        docs_display = _get_claim_docs(claim_type, lang)

        await query.edit_message_text(
            i18n.t(lang, "claim_initiated") + "\n\n"
            f"🆔 Claim #{claim_id}\n"
            f"👤 {h(lead_name)}\n"
            f"📑 {type_label}\n\n"
            f"{i18n.t(lang, 'claim_doc_checklist', count=len(docs_display))}\n"
            f"{i18n.t(lang, 'claim_status_initiated')}\n\n"
            f"{i18n.t(lang, 'claim_use_claims')}\n"
            f"{i18n.t(lang, 'claim_use_claimstatus', id=claim_id)}",
            parse_mode=ParseMode.HTML)

        context.user_data.clear()
        return ConversationHandler.END


# =============================================================================
#  /claims — View all claims for agent
# =============================================================================

async def cmd_claims(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all claims for the agent."""
    agent = await _require_agent_auth(update, context)
    if not agent:
        return

    lang = agent.get('lang', 'en')
    claims = await db.get_claims_by_agent(agent['agent_id'])
    if not claims:
        await update.message.reply_text(
            i18n.t(lang, "no_claims_msg"),
            parse_mode=ParseMode.HTML)
        return

    # Build status label map from i18n
    status_keys_en = "initiated|documents_pending|submitted|under_review|approved|rejected|settled".split("|")
    status_labels_raw = i18n.t(lang, "claim_status_map").split("|")
    status_label_map = dict(zip(status_keys_en, status_labels_raw))

    status_emoji = {
        'initiated': '🟡', 'documents_pending': '🟠',
        'submitted': '🔵', 'under_review': '🟣',
        'approved': '🟢', 'rejected': '🔴', 'settled': '✅'
    }

    lines = [i18n.t(lang, "claims_your_title") + "\n━━━━━━━━━━━━━━━━━━\n"]
    for c in claims[:15]:
        emoji = status_emoji.get(c['status'], '⚪')
        ctype = i18n.t(lang, f"claim_type_{c['claim_type']}_short") if c['claim_type'] in ('health', 'term', 'motor', 'general') else c['claim_type']
        # Remove emoji from short type since we already have status emoji
        status_text = status_label_map.get(c['status'], c['status'].replace('_', ' ').title())
        lines.append(
            f"{emoji} <b>#{c['claim_id']}</b> {h(c.get('lead_name', 'Unknown'))}\n"
            f"   {ctype} | {status_text}\n"
            f"   📅 {c['created_at'][:10]}\n")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# =============================================================================
#  /claimstatus <id> — View claim details + document checklist
# =============================================================================

async def cmd_claimstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed claim status with document checklist."""
    agent = await _require_agent_auth(update, context)
    if not agent:
        return

    lang = agent.get('lang', 'en')
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            i18n.t(lang, "claimstatus_usage"),
            parse_mode=ParseMode.HTML)
        return

    claim_id = int(args[0])
    claim = await db.get_claim(claim_id)
    if not claim or claim['agent_id'] != agent['agent_id']:
        await update.message.reply_text(i18n.t(lang, "claim_not_found"))
        return

    # Build status label map from i18n
    status_keys_en = "initiated|documents_pending|submitted|under_review|approved|rejected|settled".split("|")
    status_labels_raw = i18n.t(lang, "claim_status_map").split("|")
    status_label_map = dict(zip(status_keys_en, status_labels_raw))

    status_emoji = {
        'initiated': '🟡', 'documents_pending': '🟠',
        'submitted': '🔵', 'under_review': '🟣',
        'approved': '🟢', 'rejected': '🔴', 'settled': '✅'
    }

    emoji = status_emoji.get(claim['status'], '⚪')
    ctype = i18n.t(lang, f"claim_type_{claim['claim_type']}_short") if claim['claim_type'] in ('health', 'term', 'motor', 'general') else claim['claim_type']
    status_text = status_label_map.get(claim['status'], claim['status'].replace('_', ' ').title())

    msg = (
        i18n.t(lang, "claim_details_title", id=claim_id) + "\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>{i18n.t(lang, 'claim_client_label')}:</b> {h(claim.get('lead_name', 'Unknown'))}\n"
        f"📑 <b>{i18n.t(lang, 'claim_type_label')}:</b> {ctype}\n"
        f"{emoji} <b>{i18n.t(lang, 'claim_status_label')}:</b> {status_text}\n"
    )

    if claim.get('insurer'):
        msg += f"🏢 <b>{i18n.t(lang, 'claim_insurer_label')}:</b> {h(claim['insurer'])}\n"
    if claim.get('policy_number'):
        msg += f"📄 <b>{i18n.t(lang, 'claim_policy_label')}:</b> {h(claim['policy_number'])}\n"
    if claim.get('hospital_name'):
        msg += f"🏥 <b>{i18n.t(lang, 'claim_hospital_label')}:</b> {h(claim['hospital_name'])}\n"
    if claim.get('description'):
        msg += f"📝 <b>{i18n.t(lang, 'claim_details_label')}:</b> {h(claim['description'][:200])}\n"

    # Document checklist
    docs_json = claim.get('documents_json', '[]')
    try:
        docs = json.loads(docs_json) if docs_json else []
    except json.JSONDecodeError:
        docs = []

    if docs:
        # Display docs in user's language
        claim_type = claim.get('claim_type', 'general')
        docs_localized = _get_claim_docs(claim_type, lang)
        msg += f"\n<b>{i18n.t(lang, 'claim_docs_required')}</b>\n"
        for i, d in enumerate(docs):
            doc_status = d.get('status', 'pending')
            check = "✅" if doc_status == 'done' else "⬜"
            # Use localized doc name if available, else fallback to stored
            doc_name = docs_localized[i] if i < len(docs_localized) else d.get('doc', '')
            msg += f"  {check} {h(doc_name)}\n"

    msg += f"\n{i18n.t(lang, 'claim_created_label')}: {claim['created_at'][:10]}"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# =============================================================================
#  CONVERSATION FALLBACK HANDLERS
# =============================================================================

def _conv_recovery_keyboard(lang: str = 'en') -> InlineKeyboardMarkup:
    """Universal recovery keyboard for conversation errors."""
    if lang == 'hi':
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 पुनः प्रयास", callback_data="conv_retry"),
             InlineKeyboardButton("🏠 मुख्य मेन्यू", callback_data="conv_cancel")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Retry", callback_data="conv_retry"),
         InlineKeyboardButton("🏠 Main Menu", callback_data="conv_cancel")],
    ])


async def _conv_retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Retry' tap — re-prompt the last question by staying in state."""
    query = update.callback_query
    agent = await db.get_agent(str(query.from_user.id))
    lang = agent.get('lang', 'en') if agent else context.user_data.get('lang', 'en')
    retry_txt = "✏️ कृपया अब सही मान दर्ज करें।\n\nया /cancel टाइप करें।" if lang == 'hi' else "✏️ Please enter the correct value now.\n\nOr type /cancel to exit."
    await query.answer("पुनः प्रयास करें" if lang == 'hi' else "Let's try again")
    await query.edit_message_text(retry_txt,
        reply_markup=_conv_recovery_keyboard(lang))
    # We stay in the same conversation state — the next text will be handled


async def _conv_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Main Menu' tap from recovery keyboard — cancel conversation."""
    query = update.callback_query
    await query.answer()
    agent = await db.get_agent(str(update.effective_user.id))
    lang = agent.get('lang', 'en') if agent else context.user_data.get('lang', 'en')
    role = agent.get('role', 'agent') if agent else 'agent'
    plan = 'trial'
    if agent and agent.get('tenant_id'):
        t = await db.get_tenant(agent['tenant_id'])
        if t: plan = t.get('plan', 'trial')
    context.user_data.clear()
    await query.edit_message_text(i18n.t(lang, "conv_cancelled"))
    # Send the main menu so user isn't stranded
    menu_txt = "☰ <b>मेन्यू</b>" if lang == 'hi' else "☰ <b>Main Menu</b>"
    await query.message.reply_text(
        menu_txt,
        reply_markup=_full_menu_inline(lang, role, plan),
        parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def _conv_fallback_nontext(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-text messages (photos, stickers, voice, etc.) during conversations."""
    lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(
        i18n.t(lang, "only_text_now"),
        parse_mode=ParseMode.HTML,
        reply_markup=_conv_recovery_keyboard(lang))


async def _conv_fallback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unexpected commands during an active conversation."""
    lang = context.user_data.get('lang', 'en')
    await update.message.reply_text(
        i18n.t(lang, "conv_in_progress"),
        parse_mode=ParseMode.HTML,
        reply_markup=_conv_recovery_keyboard(lang))


# =============================================================================
#  🤖 AI TOOLS — Gemini-powered sales intelligence features
# =============================================================================

@registered
async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show AI Tools menu with all 8 AI features."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return
    lang = agent.get('lang', 'en')
    # AI tools available for all plans — quota-limited per plan

    if lang == 'hi':
        keyboard = [
            [InlineKeyboardButton("🎯 लीड स्कोरिंग", callback_data="ai_scoring"),
             InlineKeyboardButton("💡 पिच जेनरेटर", callback_data="ai_pitch")],
            [InlineKeyboardButton("📅 स्मार्ट फॉलो-अप", callback_data="ai_followup"),
             InlineKeyboardButton("📋 पॉलिसी सुझाव", callback_data="ai_recommend")],
            [InlineKeyboardButton("✉️ संदेश टेम्पलेट", callback_data="ai_templates"),
             InlineKeyboardButton("🎙️ वॉइस समरी", callback_data="ai_voice")],
            [InlineKeyboardButton("🛡️ आपत्ति हैंडलर", callback_data="ai_objection"),
             InlineKeyboardButton("🔄 रिन्यूअल इंटेलिजेंस", callback_data="ai_renewal")],
            [InlineKeyboardButton("💬 AI से पूछें", callback_data="ai_chat")],
        ]
        ai_text = (
            "🤖 <b>AI सेल्स इंटेलिजेंस</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Gemini AI — आपका पर्सनल सेल्स कोच।\n"
            "नीचे टूल चुनें:\n\n"
            "🎯 <b>लीड स्कोरिंग</b> — AI लीड्स को कन्वर्शन संभावना से रैंक करे\n"
            "💡 <b>पिच जेनरेटर</b> — हर क्लाइंट के लिए कस्टम सेल्स पिच\n"
            "📅 <b>स्मार्ट फॉलो-अप</b> — AI अगला बेस्ट एक्शन सुझाए\n"
            "📋 <b>पॉलिसी सुझाव</b> — क्लाइंट के लिए प्रोडक्ट रेकमेंडेशन\n"
            "✉️ <b>टेम्पलेट</b> — हर मौके के लिए प्रोफेशनल मैसेज\n"
            "🎙️ <b>वॉइस समरी</b> — वॉइस नोट भेजें, लीड ऑटो-बने\n"
            "🛡️ <b>आपत्ति हैंडलर</b> — क्लाइंट की आपत्तियों का जवाब\n"
            "🔄 <b>रिन्यूअल इंटेलिजेंस</b> — स्मार्ट रिन्यूअल और अपसेल\n"
            "💬 <b>AI से पूछें</b> — कोई भी बीमा सवाल, तुरंत जवाब")
    else:
        keyboard = [
            [InlineKeyboardButton("🎯 Lead Scoring", callback_data="ai_scoring"),
             InlineKeyboardButton("💡 Pitch Generator", callback_data="ai_pitch")],
            [InlineKeyboardButton("📅 Smart Follow-up", callback_data="ai_followup"),
             InlineKeyboardButton("📋 Policy Recommender", callback_data="ai_recommend")],
            [InlineKeyboardButton("✉️ Communication Templates", callback_data="ai_templates"),
             InlineKeyboardButton("🎙️ Voice Summary", callback_data="ai_voice")],
            [InlineKeyboardButton("🛡️ Objection Handler", callback_data="ai_objection"),
             InlineKeyboardButton("🔄 Renewal Intelligence", callback_data="ai_renewal")],
            [InlineKeyboardButton("💬 Ask AI Anything", callback_data="ai_chat")],
        ]
        ai_text = (
            "🤖 <b>AI Sales Intelligence</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Powered by Gemini AI — your personal sales coach.\n"
            "Select a tool below:\n\n"
            "🎯 <b>Lead Scoring</b> — AI ranks your leads by conversion probability\n"
            "💡 <b>Pitch Generator</b> — Custom sales pitches per client profile\n"
            "📅 <b>Smart Follow-up</b> — AI suggests your next best action\n"
            "📋 <b>Policy Recommender</b> — Product recommendations per client\n"
            "✉️ <b>Templates</b> — Professional messages for every occasion\n"
            "🎙️ <b>Voice Summary</b> — Send a voice note to auto-create leads\n"
            "🛡️ <b>Objection Handler</b> — Counter common client objections\n"
            "🔄 <b>Renewal Intelligence</b> — Smart renewal & upsell strategy\n"
            "💬 <b>Ask AI</b> — Any insurance question, answered instantly")
    await update.message.reply_text(
        ai_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML)


async def _ai_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle AI tool inline button callbacks."""
    query = update.callback_query
    data = query.data
    await query.answer()

    agent = await db.get_agent(str(query.from_user.id))
    if not agent:
        _lang = context.user_data.get('lang', 'en')
        await query.edit_message_text(i18n.t(_lang, "register_first"))
        return
    _lang = agent.get('lang', 'en')

    # ── Lead Scoring ─────────────────────────────────────────────────────
    if data == "ai_scoring":
        leads = await db.get_leads_by_agent(agent['agent_id'])
        if not leads:
            await query.edit_message_text(
                "📭 No leads yet. Add a lead first with ➕ Add Lead.")
            return
        keyboard = [[InlineKeyboardButton(
            f"#{l['lead_id']} {l['name'][:20]} ({l['stage']})",
            callback_data=f"aiscore_{l['lead_id']}"
        )] for l in leads[:10]]
        keyboard.append([InlineKeyboardButton(
            "🎯 Score ALL leads", callback_data="aiscore_all")])
        await query.edit_message_text(
            "🎯 <b>AI Lead Scoring</b>\n\n"
            "Select a lead to score, or score all at once:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("aiscore_"):
        target = data.replace("aiscore_", "")
        await query.edit_message_text(i18n.t(_lang, "ai_analyzing"),
                                      parse_mode=ParseMode.HTML)

        if target == "all":
            leads = await db.get_leads_by_agent(agent['agent_id'])
            results = []
            for lead in leads[:15]:
                interactions = await db.get_lead_interactions(lead['lead_id'], limit=5)
                policies = await db.get_policies_by_lead(lead['lead_id'])
                score = await ai.score_lead(dict(lead), interactions, policies, lang=_lang)
                results.append((lead, score))

            results.sort(key=lambda x: x[1].get('score', 0), reverse=True)
            msg = "🎯 <b>AI Lead Scores</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            for lead, score in results:
                grade_emoji = {"A": "🔥", "B": "⭐", "C": "💤", "D": "❄️"}.get(
                    score.get('grade', 'C'), '⚪')
                msg += (f"{grade_emoji} <b>#{lead['lead_id']} {h(lead['name'])}</b> — "
                        f"Score: <b>{score.get('score', 'N/A')}/100</b> "
                        f"({score.get('grade', '?')})\n"
                        f"   → {score.get('next_action', 'Follow up')}\n\n")
            msg += "<i>🔥=Hot  ⭐=Warm  💤=Cool  ❄️=Cold</i>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
        else:
            lead_id = int(target)
            lead = await db.get_lead(lead_id)
            if not lead or lead['agent_id'] != agent['agent_id']:
                await query.edit_message_text("❌ Lead not found")
                return
            interactions = await db.get_lead_interactions(lead_id, limit=10)
            policies = await db.get_policies_by_lead(lead_id)
            score = await ai.score_lead(dict(lead), interactions, policies, lang=_lang)

            grade_emoji = {"A": "🔥", "B": "⭐", "C": "💤", "D": "❄️"}.get(
                score.get('grade', 'C'), '⚪')
            reasons = "\n".join(f"  • {r}" for r in score.get('reasons', []))
            msg = (f"🎯 <b>AI Lead Score: #{lead_id} {h(lead['name'])}</b>\n"
                   f"━━━━━━━━━━━━━━━━━━\n\n"
                   f"{grade_emoji} Score: <b>{score.get('score', 'N/A')}/100</b> "
                   f"(Grade {score.get('grade', '?')})\n"
                   f"⚡ Priority: <b>{score.get('priority', 'medium')}</b>\n"
                   f"💰 Premium Potential: {score.get('estimated_premium_potential', 'N/A')}\n\n"
                   f"<b>Why this score:</b>\n{reasons}\n\n"
                   f"<b>Recommended Action:</b>\n"
                   f"→ {score.get('next_action', 'Follow up with the lead')}")
            keyboard = [
                [InlineKeyboardButton("💡 Generate Pitch",
                                      callback_data=f"aipitch_{lead_id}")],
                [InlineKeyboardButton("📅 Smart Follow-up",
                                      callback_data=f"aifollowup_{lead_id}")],
                [InlineKeyboardButton("🔙 Back to AI Tools",
                                      callback_data="ai_back")],
            ]
            await query.edit_message_text(msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML)

    # ── Pitch Generator ──────────────────────────────────────────────────
    elif data == "ai_pitch":
        leads = await db.get_leads_by_agent(agent['agent_id'])
        if not leads:
            await query.edit_message_text(i18n.t(_lang, "ai_no_leads"))
            return
        keyboard = [[InlineKeyboardButton(
            f"#{l['lead_id']} {l['name'][:20]} ({l.get('need_type', 'general')})",
            callback_data=f"aipitch_{l['lead_id']}"
        )] for l in leads[:10]]
        await query.edit_message_text(
            "💡 <b>AI Pitch Generator</b>\n\n"
            "Select a lead to create a personalized pitch:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("aipitch_"):
        lead_id = int(data.replace("aipitch_", ""))
        lead = await db.get_lead(lead_id)
        if not lead or lead['agent_id'] != agent['agent_id']:
            await query.edit_message_text("❌ Lead not found")
            return
        await query.edit_message_text(i18n.t(_lang, "ai_crafting_pitch"),
                                      parse_mode=ParseMode.HTML)
        tenant = await db.get_tenant(agent['tenant_id'])
        firm = tenant.get('firm_name', 'Sarathi-AI') if tenant else 'Sarathi-AI'
        pitch = await ai.generate_pitch(
            dict(lead), agent['name'], firm,
            lead.get('need_type', 'general'), lang=_lang)

        msg = (f"💡 <b>AI Sales Pitch for {h(lead['name'])}</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n\n"
               f"<b>Opening:</b>\n{h(pitch.get('opening', ''))}\n\n"
               f"<b>Main Pitch:</b>\n{h(pitch.get('pitch', ''))}\n\n"
               f"<b>Key Points:</b>\n")
        for pt in pitch.get('key_points', []):
            msg += f"  ✅ {h(pt)}\n"
        msg += (f"\n<b>Closing:</b>\n{h(pitch.get('closing', ''))}\n")

        # Store WhatsApp message for quick share
        wa_msg = pitch.get('whatsapp_message', '')
        context.user_data['ai_pitch_wa'] = wa_msg

        keyboard = [
            [InlineKeyboardButton("📱 Copy WhatsApp Pitch",
                                  callback_data=f"aipitch_wa_{lead_id}")],
            [InlineKeyboardButton("🎯 Score this Lead",
                                  callback_data=f"aiscore_{lead_id}")],
            [InlineKeyboardButton("🔙 Back to AI Tools",
                                  callback_data="ai_back")],
        ]
        # Truncate if too long for Telegram (4096 char limit)
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        await query.edit_message_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("aipitch_wa_"):
        lead_id = int(data.replace("aipitch_wa_", ""))
        wa_msg = context.user_data.get('ai_pitch_wa', '')
        if wa_msg:
            await query.edit_message_text(
                f"📱 <b>WhatsApp-ready pitch:</b>\n\n"
                f"<code>{h(wa_msg)}</code>\n\n"
                f"<i>Long-press to copy, then paste in WhatsApp</i>",
                parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text("❌ No pitch available. Generate one first.")

    # ── Smart Follow-up ──────────────────────────────────────────────────
    elif data == "ai_followup":
        leads = await db.get_leads_by_agent(agent['agent_id'])
        if not leads:
            await query.edit_message_text(i18n.t(_lang, "ai_no_leads"))
            return
        keyboard = [[InlineKeyboardButton(
            f"#{l['lead_id']} {l['name'][:20]} ({l['stage']})",
            callback_data=f"aifollowup_{l['lead_id']}"
        )] for l in leads[:10]]
        await query.edit_message_text(
            "📅 <b>AI Smart Follow-up</b>\n\n"
            "Select a lead for AI follow-up suggestions:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("aifollowup_"):
        lead_id = int(data.replace("aifollowup_", ""))
        lead = await db.get_lead(lead_id)
        if not lead or lead['agent_id'] != agent['agent_id']:
            await query.edit_message_text("❌ Lead not found")
            return
        await query.edit_message_text("📅 <i>AI is analyzing follow-up strategy...</i>",
                                      parse_mode=ParseMode.HTML)
        interactions = await db.get_lead_interactions(lead_id, limit=10)
        policies = await db.get_policies_by_lead(lead_id)
        suggestion = await ai.suggest_followup(dict(lead), interactions, policies, lang=_lang)

        urgency_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
            suggestion.get('urgency', 'medium'), '⚪')
        tips = "\n".join(f"  💡 {t}" for t in suggestion.get('tips', []))
        msg = (f"📅 <b>AI Follow-up: {h(lead['name'])}</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n\n"
               f"{urgency_emoji} Urgency: <b>{suggestion.get('urgency', 'medium').upper()}</b>\n"
               f"📱 Channel: <b>{suggestion.get('channel', 'whatsapp')}</b>\n"
               f"⏰ Timing: <b>{suggestion.get('timing', 'Today')}</b>\n\n"
               f"<b>Recommended Action:</b>\n"
               f"→ {h(suggestion.get('action', 'Follow up'))}\n\n"
               f"<b>Reasoning:</b>\n{h(suggestion.get('reasoning', ''))}\n\n"
               f"<b>Draft Message:</b>\n<code>{h(suggestion.get('message_draft', ''))}</code>\n\n"
               f"<b>Tips:</b>\n{tips}")

        keyboard = [
            [InlineKeyboardButton("💡 Generate Pitch",
                                  callback_data=f"aipitch_{lead_id}")],
            [InlineKeyboardButton("🔙 Back to AI Tools",
                                  callback_data="ai_back")],
        ]
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        await query.edit_message_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    # ── Policy Recommender ───────────────────────────────────────────────
    elif data == "ai_recommend":
        leads = await db.get_leads_by_agent(agent['agent_id'])
        if not leads:
            await query.edit_message_text(i18n.t(_lang, "ai_no_leads"))
            return
        keyboard = [[InlineKeyboardButton(
            f"#{l['lead_id']} {l['name'][:20]}",
            callback_data=f"airec_{l['lead_id']}"
        )] for l in leads[:10]]
        await query.edit_message_text(
            "📋 <b>AI Policy Recommender</b>\n\n"
            "Select a client for personalized product recommendations:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("airec_"):
        lead_id = int(data.replace("airec_", ""))
        lead = await db.get_lead(lead_id)
        if not lead or lead['agent_id'] != agent['agent_id']:
            await query.edit_message_text("❌ Lead not found")
            return
        await query.edit_message_text("📋 <i>AI is analyzing insurance needs...</i>",
                                      parse_mode=ParseMode.HTML)
        policies = await db.get_policies_by_lead(lead_id)
        rec = await ai.recommend_policies(dict(lead), policies, lang=_lang)

        msg = (f"📋 <b>AI Policy Recommendations: {h(lead['name'])}</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n\n"
               f"<b>Gap Analysis:</b>\n{h(rec.get('gap_analysis', 'N/A'))}\n\n"
               f"<b>Total Protection Needed:</b> {h(rec.get('total_protection_needed', 'N/A'))}\n\n")

        for i, r in enumerate(rec.get('recommendations', []), 1):
            prio_emoji = {"must_have": "🔴", "recommended": "🟡",
                          "nice_to_have": "🟢"}.get(r.get('priority', ''), '⚪')
            products = ", ".join(r.get('top_products', []))
            msg += (f"{prio_emoji} <b>{i}. {h(r.get('type', 'N/A').replace('_', ' ').title())}</b>\n"
                    f"   Cover: {h(r.get('suggested_cover', 'N/A'))}\n"
                    f"   Premium: {h(r.get('estimated_premium', 'N/A'))}\n"
                    f"   Products: {h(products)}\n"
                    f"   Why: {h(r.get('reason', 'N/A'))}\n\n")

        cross = rec.get('cross_sell_opportunities', [])
        if cross:
            msg += "<b>Cross-sell Opportunities:</b>\n"
            for c in cross:
                msg += f"  💡 {h(c)}\n"

        keyboard = [
            [InlineKeyboardButton("💡 Generate Pitch",
                                  callback_data=f"aipitch_{lead_id}")],
            [InlineKeyboardButton("🔙 Back to AI Tools",
                                  callback_data="ai_back")],
        ]
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        await query.edit_message_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    # ── Communication Templates ──────────────────────────────────────────
    elif data == "ai_templates":
        keyboard = [
            [InlineKeyboardButton("👋 Introduction", callback_data="aitpl_introduction"),
             InlineKeyboardButton("📞 Follow-up", callback_data="aitpl_follow_up")],
            [InlineKeyboardButton("📄 Proposal", callback_data="aitpl_proposal"),
             InlineKeyboardButton("🙏 Thank You", callback_data="aitpl_thank_you")],
            [InlineKeyboardButton("🤝 Referral Ask", callback_data="aitpl_referral_ask"),
             InlineKeyboardButton("🎂 Birthday", callback_data="aitpl_birthday")],
            [InlineKeyboardButton("💍 Anniversary", callback_data="aitpl_anniversary"),
             InlineKeyboardButton("🎉 Festival", callback_data="aitpl_festival")],
            [InlineKeyboardButton("🔄 Renewal", callback_data="aitpl_policy_renewal"),
             InlineKeyboardButton("💰 Premium Due", callback_data="aitpl_premium_reminder")],
            [InlineKeyboardButton("📊 Cross-sell", callback_data="aitpl_cross_sell"),
             InlineKeyboardButton("🔙 Reactivation", callback_data="aitpl_reactivation")],
            [InlineKeyboardButton("🔙 Back to AI Tools", callback_data="ai_back")],
        ]
        await query.edit_message_text(
            "✉️ <b>AI Communication Templates</b>\n\n"
            "Select a template type to generate professional messages\n"
            "(WhatsApp, Email, and SMS versions):",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("aitpl_"):
        tpl_type = data.replace("aitpl_", "")
        await query.edit_message_text(
            f"✉️ <i>Generating {tpl_type.replace('_', ' ')} template...</i>",
            parse_mode=ParseMode.HTML)
        tenant = await db.get_tenant(agent['tenant_id'])
        firm = tenant.get('firm_name', 'Sarathi-AI') if tenant else 'Sarathi-AI'
        tpl = await ai.generate_template(tpl_type, agent_name=agent['name'],
                                         firm_name=firm, lang=_lang)

        msg = (f"✉️ <b>{tpl_type.replace('_', ' ').title()} Template</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n\n"
               f"📱 <b>WhatsApp:</b>\n<code>{h(tpl.get('whatsapp', ''))}</code>\n\n"
               f"📧 <b>Email Subject:</b>\n{h(tpl.get('email_subject', ''))}\n\n"
               f"📧 <b>Email Body:</b>\n<code>{h(tpl.get('email_body', ''))}</code>\n\n"
               f"📲 <b>SMS:</b>\n<code>{h(tpl.get('sms', ''))}</code>\n\n"
               f"💡 <b>Tips:</b>\n")
        for tip in tpl.get('tips', []):
            msg += f"  • {h(tip)}\n"

        keyboard = [
            [InlineKeyboardButton("✉️ More Templates", callback_data="ai_templates")],
            [InlineKeyboardButton("🔙 Back to AI Tools", callback_data="ai_back")],
        ]
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        await query.edit_message_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    # ── Voice Summary note ───────────────────────────────────────────────
    elif data == "ai_voice":
        await query.edit_message_text(
            "🎙️ <b>Voice Meeting Summary</b>\n\n"
            "Send me a <b>voice note</b> (max 2 min) about:\n"
            "• A client meeting you just had\n"
            "• A phone call with a prospect\n"
            "• Quick notes about a lead\n\n"
            "🤖 AI will automatically:\n"
            "  ✅ Transcribe your voice note\n"
            "  ✅ Extract lead data (name, phone, need)\n"
            "  ✅ Create the lead in your CRM\n"
            "  ✅ Set follow-up reminders\n\n"
            "<i>Just record and send — no typing needed!</i>",
            parse_mode=ParseMode.HTML)

    # ── Objection Handler ────────────────────────────────────────────────
    elif data == "ai_objection":
        keyboard = [
            [InlineKeyboardButton("💰 Too Expensive",
                                  callback_data="aiobj_I think insurance is too expensive")],
            [InlineKeyboardButton("⏳ I'll Think About It",
                                  callback_data="aiobj_I need to think about it, maybe later")],
            [InlineKeyboardButton("🏥 I'm Young & Healthy",
                                  callback_data="aiobj_I'm young and healthy, I don't need insurance")],
            [InlineKeyboardButton("😤 Don't Trust Insurance",
                                  callback_data="aiobj_Insurance companies don't pay claims")],
            [InlineKeyboardButton("👨‍👩‍👧 Need Family Approval",
                                  callback_data="aiobj_I need to discuss with my family first")],
            [InlineKeyboardButton("🏦 Already Have Coverage",
                                  callback_data="aiobj_I already have insurance from my employer")],
            [InlineKeyboardButton("✍️ Type Custom Objection",
                                  callback_data="aiobj_custom")],
            [InlineKeyboardButton("🔙 Back to AI Tools",
                                  callback_data="ai_back")],
        ]
        await query.edit_message_text(
            "🛡️ <b>AI Objection Handler</b>\n\n"
            "Select a common objection, or type your own:\n"
            "<i>AI will provide empathy statements, counter-arguments,\n"
            "and closing questions to help you convert.</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("aiobj_"):
        objection_text = data.replace("aiobj_", "")
        if objection_text == "custom":
            context.user_data['awaiting_objection'] = True
            await query.edit_message_text(
                "✍️ Type the client's objection below:\n\n"
                "<i>Example: \"I already have a company policy\" or\n"
                "\"My friend said claims never get paid\"</i>",
                parse_mode=ParseMode.HTML)
            return
        await query.edit_message_text(
            i18n.t(_lang, "ai_objection_handling"),
            parse_mode=ParseMode.HTML)
        result = await ai.handle_objection(objection_text, lang=_lang)

        counters = "\n".join(f"  {i+1}. {h(c)}" for i, c in enumerate(
            result.get('counter_arguments', [])))
        msg = (f"🛡️ <b>Objection: \"{h(objection_text[:60])}\"</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n\n"
               f"📂 Category: <b>{h(result.get('category', 'general'))}</b>\n\n"
               f"💚 <b>Empathy First:</b>\n\"{h(result.get('empathy_statement', ''))}\"\n\n"
               f"💪 <b>Counter-arguments:</b>\n{counters}\n\n"
               f"🔄 <b>Reframe:</b>\n{h(result.get('reframe', ''))}\n\n"
               f"❓ <b>Closing Question:</b>\n\"{h(result.get('closing_question', ''))}\"\n\n"
               f"📖 <b>Real-world Example:</b>\n{h(result.get('real_world_example', ''))}\n\n"
               f"📊 <b>Supporting Data:</b>\n{h(result.get('supporting_data', ''))}")

        keyboard = [
            [InlineKeyboardButton("🛡️ Another Objection", callback_data="ai_objection")],
            [InlineKeyboardButton("🔙 Back to AI Tools", callback_data="ai_back")],
        ]
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        await query.edit_message_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    # ── Renewal Intelligence ─────────────────────────────────────────────
    elif data == "ai_renewal":
        leads = await db.get_leads_by_agent(agent['agent_id'])
        # Find leads with policies that have renewal dates
        renewal_leads = []
        for lead in (leads or []):
            policies = await db.get_policies_by_lead(lead['lead_id'])
            for pol in (policies or []):
                if pol.get('renewal_date'):
                    renewal_leads.append((lead, pol))
        if not renewal_leads:
            await query.edit_message_text(
                "📭 No policies with renewal dates found.\n"
                "Add policies with renewal dates to use this feature.",
                parse_mode=ParseMode.HTML)
            return
        keyboard = [[InlineKeyboardButton(
            f"#{l['lead_id']} {l['name'][:15]} — {p.get('insurer', '')[:10]} "
            f"({p.get('renewal_date', 'N/A')[:10]})",
            callback_data=f"airenew_{l['lead_id']}_{p['policy_id']}"
        )] for l, p in renewal_leads[:10]]
        keyboard.append([InlineKeyboardButton("🔙 Back to AI Tools",
                                              callback_data="ai_back")])
        await query.edit_message_text(
            "🔄 <b>AI Renewal Intelligence</b>\n\n"
            "Select a policy to get AI renewal strategy:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("airenew_"):
        parts = data.replace("airenew_", "").split("_")
        lead_id, policy_id = int(parts[0]), int(parts[1])
        lead = await db.get_lead(lead_id)
        if not lead or lead['agent_id'] != agent['agent_id']:
            await query.edit_message_text("❌ Lead not found")
            return
        policy = None
        all_policies = await db.get_policies_by_lead(lead_id)
        for p in (all_policies or []):
            if p.get('policy_id') == policy_id:
                policy = p
                break
        if not policy:
            await query.edit_message_text("❌ Policy not found")
            return
        await query.edit_message_text("🔄 <i>AI is analyzing renewal strategy...</i>",
                                      parse_mode=ParseMode.HTML)
        intel = await ai.renewal_intelligence(dict(policy), dict(lead), all_policies, lang=_lang)

        msg = (f"🔄 <b>Renewal Intelligence: {h(lead['name'])}</b>\n"
               f"<b>{h(policy.get('insurer', ''))} — {h(policy.get('plan_name', ''))}</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n\n"
               f"📊 Retention Risk: <b>{intel.get('retention_risk', 'N/A').upper()}</b>\n"
               f"💰 Premium Change: {h(intel.get('premium_change_estimate', 'N/A'))}\n\n"
               f"<b>Strategy:</b>\n{h(intel.get('renewal_strategy', ''))}\n\n"
               f"<b>Upsell Opportunity:</b>\n{h(intel.get('upsell_opportunity', ''))}\n\n"
               f"<b>Coverage Gap:</b>\n{h(intel.get('coverage_gap', ''))}\n\n"
               f"<b>Talking Points:</b>\n")
        for pt in intel.get('talking_points', []):
            msg += f"  ✅ {h(pt)}\n"
        msg += (f"\n<b>Competitor View:</b>\n{h(intel.get('competitor_comparison', ''))}\n\n"
                f"<b>Ready Message:</b>\n<code>{h(intel.get('message_draft', ''))}</code>")

        keyboard = [
            [InlineKeyboardButton("🔄 Another Renewal", callback_data="ai_renewal")],
            [InlineKeyboardButton("🔙 Back to AI Tools", callback_data="ai_back")],
        ]
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        await query.edit_message_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    # ── Ask AI Anything ──────────────────────────────────────────────────
    elif data == "ai_chat":
        context.user_data['awaiting_ai_question'] = True
        await query.edit_message_text(
            "💬 <b>Ask AI Anything</b>\n\n"
            "Type your insurance question below. Examples:\n\n"
            "• <i>What's the best term plan for a 30-year-old?</i>\n"
            "• <i>How does Section 80C tax benefit work?</i>\n"
            "• <i>Compare Star Health vs HDFC ERGO</i>\n"
            "• <i>What documents needed for health claim?</i>\n\n"
            "🤖 AI will answer instantly!",
            parse_mode=ParseMode.HTML)

    # ── Back to AI menu ──────────────────────────────────────────────────
    elif data == "ai_back":
        _agent = await db.get_agent(str(query.from_user.id))
        _lang = _agent.get('lang', 'en') if _agent else 'en'
        if _lang == 'hi':
            keyboard = [
                [InlineKeyboardButton("🎯 लीड स्कोरिंग", callback_data="ai_scoring"),
                 InlineKeyboardButton("💡 पिच जेनरेटर", callback_data="ai_pitch")],
                [InlineKeyboardButton("📅 स्मार्ट फॉलो-अप", callback_data="ai_followup"),
                 InlineKeyboardButton("📋 पॉलिसी सुझाव", callback_data="ai_recommend")],
                [InlineKeyboardButton("✉️ संदेश टेम्पलेट", callback_data="ai_templates"),
                 InlineKeyboardButton("🎙️ वॉइस समरी", callback_data="ai_voice")],
                [InlineKeyboardButton("🛡️ आपत्ति हैंडलर", callback_data="ai_objection"),
                 InlineKeyboardButton("🔄 रिन्यूअल इंटेल", callback_data="ai_renewal")],
                [InlineKeyboardButton("💬 AI से पूछें", callback_data="ai_chat")],
            ]
            ai_title = "🤖 <b>AI सेल्स इंटेलिजेंस</b>\n━━━━━━━━━━━━━━━━━━\n\nटूल चुनें:"
        else:
            keyboard = [
                [InlineKeyboardButton("🎯 Lead Scoring", callback_data="ai_scoring"),
                 InlineKeyboardButton("💡 Pitch Generator", callback_data="ai_pitch")],
                [InlineKeyboardButton("📅 Smart Follow-up", callback_data="ai_followup"),
                 InlineKeyboardButton("📋 Policy Recommender", callback_data="ai_recommend")],
                [InlineKeyboardButton("✉️ Templates", callback_data="ai_templates"),
                 InlineKeyboardButton("🎙️ Voice Summary", callback_data="ai_voice")],
                [InlineKeyboardButton("🛡️ Objection Handler", callback_data="ai_objection"),
                 InlineKeyboardButton("🔄 Renewal Intel", callback_data="ai_renewal")],
                [InlineKeyboardButton("💬 Ask AI Anything", callback_data="ai_chat")],
            ]
            ai_title = "🤖 <b>AI Sales Intelligence</b>\n━━━━━━━━━━━━━━━━━━\n\nSelect a tool:"
        await query.edit_message_text(
            ai_title,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)


async def _ai_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for AI features (custom objection, AI chat question)."""
    # Custom objection
    if context.user_data.get('awaiting_objection'):
        context.user_data.pop('awaiting_objection', None)
        text = update.message.text.strip()
        _lang = context.user_data.get('lang', 'en')
        processing = await update.message.reply_text(
            i18n.t(_lang, "ai_objection_handling"),
            parse_mode=ParseMode.HTML)
        result = await ai.handle_objection(text, lang=_lang)
        counters = "\n".join(f"  {i+1}. {h(c)}" for i, c in enumerate(
            result.get('counter_arguments', [])))
        msg = (f"🛡️ <b>Objection: \"{h(text[:60])}\"</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n\n"
               f"📂 Category: <b>{h(result.get('category', 'general'))}</b>\n\n"
               f"💚 <b>Empathy First:</b>\n\"{h(result.get('empathy_statement', ''))}\"\n\n"
               f"💪 <b>Counter-arguments:</b>\n{counters}\n\n"
               f"🔄 <b>Reframe:</b>\n{h(result.get('reframe', ''))}\n\n"
               f"❓ <b>Closing Question:</b>\n\"{h(result.get('closing_question', ''))}\"\n\n"
               f"📖 <b>Real-world:</b>\n{h(result.get('real_world_example', ''))}\n\n"
               f"📊 <b>Data:</b>\n{h(result.get('supporting_data', ''))}")
        keyboard = [
            [InlineKeyboardButton("🛡️ Another Objection", callback_data="ai_objection")],
            [InlineKeyboardButton("🔙 Back to AI Tools", callback_data="ai_back")],
        ]
        if len(msg) > 3800:
            msg = msg[:3800] + "\n\n<i>... (truncated)</i>"
        await processing.edit_text(msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)
        return True

    # AI chat question
    if context.user_data.get('awaiting_ai_question'):
        context.user_data.pop('awaiting_ai_question', None)
        text = update.message.text.strip()
        _lang = context.user_data.get('lang', 'en')
        processing = await update.message.reply_text(
            i18n.t(_lang, "ai_thinking"), parse_mode=ParseMode.HTML)
        answer = await ai.ask_insurance_ai(text, lang=_lang)
        keyboard = [[InlineKeyboardButton("💬 Ask Another Question",
                                          callback_data="ai_chat")],
                     [InlineKeyboardButton("🔙 Back to AI Tools",
                                          callback_data="ai_back")]]
        if len(answer) > 3800:
            answer = answer[:3800] + "\n\n... (truncated)"
        await processing.edit_text(
            f"💬 <b>AI Answer</b>\n━━━━━━━━━━━━━━━━━━\n\n{h(answer)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)
        return True

    return False


# =============================================================================
#  CSV IMPORT — Agents can send CSV files via Telegram to bulk-import leads
# =============================================================================

async def _csv_import_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle CSV file uploads for bulk lead import."""
    agent = await _require_agent_auth(update, context)
    if not agent:
        return

    # Plan gate: bulk import requires Team plan or higher
    if not await _check_plan(update, agent, 'bulk_campaigns'):
        return

    doc = update.message.document
    if not doc:
        return
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".csv"):
        return  # Not a CSV, ignore

    lang = agent.get('lang', 'en')
    processing = await update.message.reply_text(
        i18n.t(lang, "csv_processing"),
        parse_mode=ParseMode.HTML)

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        csv_bytes = await tg_file.download_as_bytearray()
        csv_text = csv_bytes.decode("utf-8-sig")

        import csv
        import io
        reader = csv.DictReader(io.StringIO(csv_text))
        leads_data = [dict(row) for row in reader]

        if not leads_data:
            await processing.edit_text("❌ CSV file is empty or has no valid rows.")
            return
        if len(leads_data) > 500:
            await processing.edit_text("❌ Max 500 leads per import. Your file has "
                                       f"{len(leads_data)} rows.")
            return

        result = await db.bulk_add_leads(agent['agent_id'], leads_data)

        msg = (f"📥 <b>CSV Import Complete</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n\n"
               f"✅ Imported: <b>{result['imported']}</b>\n"
               f"⏭️ Skipped: <b>{result['skipped']}</b>\n")
        if result['errors'][:5]:
            msg += "\n<b>Issues:</b>\n"
            for err in result['errors'][:5]:
                msg += f"  ⚠️ {h(err)}\n"
            if len(result['errors']) > 5:
                msg += f"  <i>...and {len(result['errors'])-5} more</i>\n"

        msg += ("\n<i>Expected CSV columns: name, phone, email, city, "
                "need_type, notes, dob, anniversary, occupation</i>")
        await processing.edit_text(msg, parse_mode=ParseMode.HTML)

        await db.log_audit("csv_import_bot",
                           f"Agent {agent['agent_id']} imported {result['imported']} leads",
                           tenant_id=agent.get('tenant_id'),
                           agent_id=agent['agent_id'])
    except Exception as e:
        logger.error("CSV import error: %s", e)
        await processing.edit_text(
            "❌ Error processing CSV. Make sure it has a header row with 'name' column.\n"
            f"Error: {str(e)[:100]}")


# =============================================================================
#  AGENT MANAGEMENT — /team command for firm owners
# =============================================================================

@registered
async def cmd_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage team agents — list, deactivate, reactivate, transfer data."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return

    if agent.get('role') not in ('owner', 'admin'):
        await update.message.reply_text(
            "⚠️ Only firm owners/admins can manage the team.")
        return

    # Plan gate: team management requires Team plan or higher
    if not await _check_plan(update, agent, 'team_dashboard'):
        return

    agents_list = await db.get_agents_by_tenant_all(agent['tenant_id'])
    cap = await db.can_add_agent(agent['tenant_id'])

    msg = (f"👥 <b>Team Management</b>\n"
           f"━━━━━━━━━━━━━━━━━━\n\n"
           f"📊 Agents: <b>{cap['current']}/{cap['max']}</b> "
           f"({cap['plan'].title()} plan)\n\n")

    keyboard = []
    for a in agents_list:
        status = "✅" if a.get('is_active') else "❌"
        role_icon = "👑" if a['role'] == 'owner' else "👤"
        leads = a.get('lead_count', 0)
        policies = a.get('policy_count', 0)
        msg += (f"{role_icon} {status} <b>{h(a['name'])}</b> ({a['role']})\n"
                f"   📋 {leads} leads, 📄 {policies} policies\n")

        # Add management buttons for non-owner agents
        if a['role'] != 'owner':
            if a.get('is_active'):
                keyboard.append([InlineKeyboardButton(
                    f"❌ Deactivate {a['name'][:15]}",
                    callback_data=f"teamdeact_{a['agent_id']}")])
            else:
                keyboard.append([InlineKeyboardButton(
                    f"✅ Reactivate {a['name'][:15]}",
                    callback_data=f"teamreact_{a['agent_id']}")])
            if leads > 0 or policies > 0:
                keyboard.append([InlineKeyboardButton(
                    f"🔄 Transfer {a['name'][:12]}'s data",
                    callback_data=f"teamxfer_{a['agent_id']}")])

    if not keyboard:
        msg += "\n<i>No agents to manage (you're the only one).</i>"

    await update.message.reply_text(
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        parse_mode=ParseMode.HTML)


async def _team_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team management inline button callbacks."""
    query = update.callback_query
    data = query.data
    await query.answer()

    agent = await db.get_agent(str(query.from_user.id))
    if not agent or agent.get('role') not in ('owner', 'admin'):
        await query.edit_message_text(i18n.t(agent.get('lang', 'en'), "team_manage_owner_only"))
        return

    if data.startswith("teamdeact_"):
        target_id = int(data.replace("teamdeact_", ""))
        target = await db.get_agent_by_id(target_id)
        if not target or target.get('tenant_id') != agent['tenant_id']:
            await query.edit_message_text("❌ Agent not found")
            return
        if target.get('role') == 'owner':
            await query.edit_message_text("❌ Cannot deactivate the firm owner.")
            return
        await db.deactivate_agent_full(target_id, tenant_id=agent['tenant_id'],
                                       reason='admin_action')
        _lang = agent.get('lang', 'en')
        await query.edit_message_text(
            f"✅ <b>{h(target['name'])}</b> has been deactivated.\n\n"
            f"Their Telegram access has been revoked immediately.\n"
            f"Their data (leads, policies) is preserved — use Transfer if needed.",
            parse_mode=ParseMode.HTML)

    elif data.startswith("teamreact_"):
        target_id = int(data.replace("teamreact_", ""))
        target = await db.get_agent_by_id(target_id)
        if not target or target.get('tenant_id') != agent['tenant_id']:
            await query.edit_message_text("❌ Agent not found")
            return
        await db.reactivate_agent(target_id)
        await db.log_audit("agent_reactivated", f"Agent {target_id}",
                           tenant_id=agent['tenant_id'], agent_id=agent['agent_id'])
        _lang = agent.get('lang', 'en')
        await query.edit_message_text(
            i18n.t(_lang, "agent_reactivated_msg", name=h(target['name'])),
            parse_mode=ParseMode.HTML)

    elif data.startswith("teamxfer_"):
        from_id = int(data.replace("teamxfer_", ""))
        from_agent = await db.get_agent_by_id(from_id)
        if not from_agent:
            await query.edit_message_text("❌ Agent not found")
            return
        # Show list of agents to transfer to
        agents_list = await db.get_agents_by_tenant_all(agent['tenant_id'])
        keyboard = []
        for a in agents_list:
            if a['agent_id'] != from_id and a.get('is_active'):
                keyboard.append([InlineKeyboardButton(
                    f"→ {a['name'][:20]}",
                    callback_data=f"teamxferto_{from_id}_{a['agent_id']}")])
        if not keyboard:
            _lang = agent.get('lang', 'en')
            await query.edit_message_text(i18n.t(_lang, "no_agents_to_transfer"))
            return
        await query.edit_message_text(
            f"🔄 Transfer <b>{h(from_agent['name'])}</b>'s data to:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML)

    elif data.startswith("teamxferto_"):
        parts = data.replace("teamxferto_", "").split("_")
        from_id, to_id = int(parts[0]), int(parts[1])
        counts = await db.transfer_agent_data(from_id, to_id)
        to_agent = await db.get_agent_by_id(to_id)
        from_agent = await db.get_agent_by_id(from_id)
        await db.log_audit("data_transfer",
                           f"{from_id}→{to_id}: {counts}",
                           tenant_id=agent['tenant_id'], agent_id=agent['agent_id'])
        await query.edit_message_text(
            f"✅ <b>Data Transferred</b>\n\n"
            f"From: {h(from_agent['name'] if from_agent else 'Unknown')}\n"
            f"To: {h(to_agent['name'] if to_agent else 'Unknown')}\n\n"
            f"📋 Leads: {counts.get('leads', 0)}\n"
            f"📄 Policies: {counts.get('policies', 0)}\n"
            f"📞 Interactions: {counts.get('interactions', 0)}\n"
            f"🏥 Claims: {counts.get('claims', 0)}\n"
            f"⏰ Reminders: {counts.get('reminders', 0)}\n\n"
            f"Use /team to continue managing.",
            parse_mode=ParseMode.HTML)


# =============================================================================
#  PAYMENT CALLBACK — Handle plan subscription from inline buttons
# =============================================================================

async def _payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription plan selection inline buttons."""
    query = update.callback_query
    data = query.data
    await query.answer()

    agent = await db.get_agent(str(query.from_user.id))
    if not agent:
        _lang = context.user_data.get('lang', 'en')
        await query.edit_message_text(i18n.t(_lang, "payment_register_first"))
        return

    # Handle cancel subscription callback
    if data == 'cancel_sub':
        role = agent.get('role', 'agent')
        if role not in ('owner', 'admin'):
            await query.edit_message_text("❌ Only the firm owner/admin can cancel the subscription.")
            return
        tenant = await db.get_tenant(agent['tenant_id']) if agent.get('tenant_id') else None
        if not tenant or tenant.get('subscription_status') != 'active':
            await query.edit_message_text("ℹ️ No active subscription to cancel.")
            return
        # Confirm cancellation via another callback
        await query.edit_message_text(
            "⚠️ <b>Cancel Subscription?</b>\n\n"
            "Your access will continue until the end of the current billing period.\n"
            "No refund will be issued for the current month.\n"
            "Auto-pay mandate will be stopped.\n\n"
            "Are you sure?",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Yes, Cancel", callback_data="pay_confirm_cancel")],
                [InlineKeyboardButton("◀️ No, Keep My Plan", callback_data="pay_back")],
            ]))
        return

    # Handle confirmed cancellation
    if data == 'pay_confirm_cancel':
        role = agent.get('role', 'agent')
        if role not in ('owner', 'admin'):
            await query.edit_message_text("❌ Unauthorized.")
            return
        tenant = await db.get_tenant(agent['tenant_id']) if agent.get('tenant_id') else None
        if not tenant or tenant.get('subscription_status') != 'active':
            await query.edit_message_text("ℹ️ No active subscription to cancel.")
            return
        # Call cancel API internally
        try:
            tid = agent['tenant_id']
            from sarathi_biz import payments as pay_mod
            # Cancel on Razorpay side
            razorpay_sub_id = tenant.get('razorpay_sub_id')
            if razorpay_sub_id and pay_mod.is_enabled():
                try:
                    await pay_mod._razorpay_request(
                        "POST", f"subscriptions/{razorpay_sub_id}/cancel",
                        {"cancel_at_cycle_end": 1})
                except Exception as e:
                    logger.error("Bot cancel razorpay sub %s: %s", razorpay_sub_id, e)
            # Update DB
            expires = tenant.get('subscription_expires_at', '')
            if tenant.get('subscription_expires_at'):
                await db.update_tenant(tid, subscription_status="cancelled")
            else:
                await db.update_tenant(tid, subscription_status="cancelled", is_active=0)
            # Audit log
            import aiosqlite, json as json_mod
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute(
                    "INSERT INTO audit_log (tenant_id, action, detail, created_at) VALUES (?, 'subscription_cancelled', ?, ?)",
                    (tid, json_mod.dumps({"reason": "Cancelled via Telegram bot", "wipe_after": ""}), datetime.now().isoformat()))
                await conn.commit()
            end_info = ''
            if expires:
                try:
                    end_info = f"\n\n📅 Your access continues until {datetime.fromisoformat(expires).strftime('%d %b %Y')}."
                except: pass
            await query.edit_message_text(
                f"✅ <b>Subscription Cancelled</b>\n\n"
                f"Your subscription for <b>{tenant.get('firm_name', '')}</b> has been cancelled."
                f"{end_info}\n\n"
                f"You can resubscribe anytime with /plans.",
                parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("Bot cancel subscription error: %s", e)
            await query.edit_message_text(f"❌ Error cancelling: {str(e)[:100]}")
        return

    # Handle pay_back
    if data == 'pay_back':
        await query.edit_message_text("👍 Use /plans to see available plans.")
        return

    plan_key = data.replace("pay_", "")
    if plan_key not in ("individual", "team", "enterprise"):
        return

    plan_names = {"individual": "Solo Advisor (₹199/mo)",
                  "team": "Team (₹799/mo)",
                  "enterprise": "Enterprise (₹1,999/mo)"}

    # Create Razorpay recurring subscription and get payment link
    try:
        from sarathi_biz import payments as pay_mod
        tid = agent['tenant_id']
        result = await pay_mod.create_subscription(tid, plan_key)
        if "error" in result:
            await query.edit_message_text(f"❌ {result['error']}")
            return
        checkout_url = result.get("short_url", "")
        if not checkout_url:
            server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
            checkout_url = f"{server_url}/#pricing?plan={plan_key}&tenant={tid}"
    except Exception as e:
        logger.error("Bot create subscription error: %s", e)
        server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
        checkout_url = f"{server_url}/#pricing?plan={plan_key}&tenant={agent['tenant_id']}"

    await query.edit_message_text(
        f"💳 <b>Subscribe to {plan_names[plan_key]}</b>\n\n"
        f"Click the button below to complete payment via "
        f"UPI, Debit Card, Credit Card, or Net Banking.\n\n"
        f"🔄 <b>Auto-renewing monthly</b> — cancel anytime.\n"
        f"🔒 Powered by Razorpay (100% secure)\n\n"
        f"<i>After payment, your plan activates instantly!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"💳 Pay for {plan_names[plan_key]}",
                url=checkout_url)],
            [InlineKeyboardButton("◀️ Back to Plans",
                                  callback_data="pay_back")],
        ]))


# =============================================================================
#  WHATSAPP SETUP — Bot command for WhatsApp integration guide
# =============================================================================

@registered
async def cmd_whatsapp_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user through WhatsApp Business API integration."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return
    # Owner-only command
    if agent.get('role') not in ('owner', 'admin'):
        await update.message.reply_text(
            "🔒 Only firm owners can configure WhatsApp integration.")
        return

    tenant = await db.get_tenant(agent['tenant_id']) if agent.get('tenant_id') else None
    wa_configured = bool(tenant and tenant.get('wa_phone_id') and tenant.get('wa_access_token'))
    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")

    if wa_configured:
        status = (
            f"✅ <b>WhatsApp is Connected!</b>\n"
            f"Phone ID: <code>{tenant['wa_phone_id']}</code>\n\n"
            f"You can send messages via:\n"
            f"• /wa &lt;lead_id&gt; &lt;message&gt;\n"
            f"• Dashboard → WhatsApp button\n\n"
            f"📥 Incoming messages are auto-routed to you here.\n\n"
            f"To reconfigure, go to Dashboard → Settings → WhatsApp"
        )
    else:
        status = (
            f"📱 <b>WhatsApp Integration — Setup Guide</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Step 1:</b> Go to developers.facebook.com\n"
            f"   → Create account + accept terms\n\n"
            f"<b>Step 2:</b> Create a 'Business' type app\n\n"
            f"<b>Step 3:</b> Add WhatsApp to your app\n"
            f"   → Note the <b>Phone Number ID</b>\n"
            f"   → Copy the <b>Access Token</b>\n\n"
            f"<b>Step 4:</b> Get a permanent token:\n"
            f"   → Business Settings → System Users → Generate Token\n\n"
            f"<b>Step 5:</b> Configure webhook:\n"
            f"   → URL: <code>{server_url}/webhook</code>\n"
            f"   → Subscribe to 'messages'\n\n"
            f"<b>Step 6:</b> Enter credentials in Sarathi-AI:\n"
            f"   → Dashboard → Settings → WhatsApp\n\n"
            f"💡 <i>Free tier: 1,000 conversations/month</i>\n"
            f"💡 <i>Test phone number available for free</i>"
        )

    keyboard = [
        [InlineKeyboardButton("📖 Full Setup Guide",
                              url=f"{server_url}/api/wa/setup-guide")],
        [InlineKeyboardButton("⚙️ Configure in Dashboard",
                              url=f"{server_url}/dashboard#whatsapp")],
        [InlineKeyboardButton("🔗 Meta Developer Portal",
                              url="https://developers.facebook.com/")],
    ]

    await update.message.reply_text(
        status,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True)


# =============================================================================
#  BOT CREATION GUIDANCE — Step-by-step BotFather walkthrough in Telegram
# =============================================================================

@registered
async def cmd_createbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user through creating their own Telegram bot via @BotFather."""
    agent = context.user_data.get('_agent') or await _get_agent(update)
    if not agent:
        return
    # Custom bot requires team plan or higher
    if not await _check_plan(update, agent, 'custom_branding'):
        return

    msg = (
        "🤖 <b>Create Your Own Bot — Step by Step</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Step 1:</b> Open @BotFather on Telegram\n"
        "   → <a href='https://t.me/BotFather'>Click here to open BotFather</a>\n\n"
        "<b>Step 2:</b> Send <code>/newbot</code> to BotFather\n\n"
        "<b>Step 3:</b> Enter your firm name as display name\n"
        "   → Example: <i>\"ABC Insurance Advisors\"</i>\n\n"
        "<b>Step 4:</b> Choose a username ending with 'bot'\n"
        "   → Example: <i>abc_insurance_bot</i>\n\n"
        "<b>Step 5:</b> Copy the token BotFather gives you\n"
        "   → It looks like: <code>123456789:ABCdefGHI...</code>\n\n"
        "<b>Step 6:</b> Come back here and paste the token\n"
        "   → Go to sarathi-ai.com → Dashboard → Settings → Connect Bot\n\n"
        "✅ <b>That's it!</b> Your custom bot will be live in seconds.\n"
        "Each agent in your firm can use this bot independently.\n\n"
        "💡 <i>It's 100% free to create a Telegram bot!</i>"
    )

    keyboard = [
        [InlineKeyboardButton("🤖 Open @BotFather",
                              url="https://t.me/BotFather")],
        [InlineKeyboardButton("📋 Go to Dashboard",
                              url=f"{os.getenv('SERVER_URL', 'https://sarathi-ai.com')}/dashboard")],
    ]
    await update.message.reply_text(msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True)


async def _conv_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle conversation timeout — auto-cancel after 30 min inactivity."""
    context.user_data.clear()
    agent = await db.get_agent(str(update.effective_user.id))
    lang = agent.get('lang', 'en') if agent else 'en'
    await update.message.reply_text(
        i18n.t(lang, "conv_timeout"),
        reply_markup=_main_menu_keyboard(lang))
    return ConversationHandler.END


async def _global_catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch-all for unrecognized text outside any conversation.
    Routes to 'Just Talk' AI mode if agent is authenticated and Gemini is available.
    """
    text = (update.message.text or "").strip()

    # ── SA OTP pending? Verify before anything else ──
    if context.user_data.get('_sa_otp_pending') and text:
        await _sa_verify_otp(update, context)
        return

    # ── WhatsApp share pending? Let group-1 handler process phone input ──
    if context.user_data.get("wa_share_pending"):
        if re.match(r'^\+?\d[\d\s\-]{8,13}$', text):
            return  # don't clear, don't respond — wa_share_phone_handler handles it
        # Not a phone number — prompt user
        lang = context.user_data.get('lang', 'en')
        await update.message.reply_text(
            i18n.t(lang, "wa_share_prompt"),
            parse_mode=ParseMode.HTML)
        return

    # Clear any orphaned conversation state (wa_share_pending already handled above)
    for key in ('convert_lead_id', 'followup_lead_id'):
        context.user_data.pop(key, None)

    # ── Multi-turn voice context (text response to pending voice action) ──
    voice_ctx = context.user_data.get('voice_context')
    if voice_ctx and text:
        pending = voice_ctx.get('pending_action')
        if pending == 'setup_followup' and voice_ctx.get('awaiting') == 'date':
            _today = datetime.now()
            t_lower = text.lower().strip()
            parsed_date = None
            # Try common date patterns
            if 'kal' in t_lower or 'tomorrow' in t_lower:
                parsed_date = (_today + timedelta(days=1)).strftime('%Y-%m-%d')
            elif 'parso' in t_lower or 'day after' in t_lower:
                parsed_date = (_today + timedelta(days=2)).strftime('%Y-%m-%d')
            elif 'agle hafte' in t_lower or 'next week' in t_lower:
                parsed_date = (_today + timedelta(days=(7 - _today.weekday()))).strftime('%Y-%m-%d')
            else:
                # Try ISO date or dd/mm/yyyy
                import re as _re
                m = _re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', t_lower)
                if m:
                    parsed_date = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
                else:
                    m = _re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', t_lower)
                    if m:
                        y = m.group(3) if len(m.group(3)) == 4 else f"20{m.group(3)}"
                        parsed_date = f"{y}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

            if parsed_date:
                lead_id = voice_ctx['lead_id']
                lead_name_ctx = voice_ctx.get('lead_name', '')
                msg_ctx = voice_ctx.get('message', '')
                context.user_data.pop('voice_context', None)
                agent = await _require_agent_auth(update, context)
                if not agent:
                    return
                # Duplicate detection — update existing task if one exists
                is_update = False
                existing = await db.get_pending_followups_for_lead(lead_id)
                if existing:
                    ef = existing[0]
                    is_update = True
                    await db.update_followup(
                        interaction_id=ef['interaction_id'],
                        follow_up_date=parsed_date,
                        summary=f"Voice follow-up: {msg_ctx[:100]}" if msg_ctx else None
                    )
                else:
                    await db.log_interaction(
                        lead_id=lead_id,
                        agent_id=agent['agent_id'],
                        interaction_type='follow_up_scheduled',
                        summary=f"Voice follow-up: {msg_ctx[:100]}" if msg_ctx else "Voice follow-up",
                        follow_up_date=parsed_date
                    )
                hi = agent.get('lang', 'en') == 'hi'
                await update.message.reply_text(
                    f"{'✏️' if is_update else '✅'} {'टास्क अपडेट किया' if is_update and hi else 'Task updated' if is_update else 'टास्क शेड्यूल किया' if hi else 'Task scheduled'}!\n"
                    f"👤 <b>{h(lead_name_ctx)}</b> (#{lead_id})\n"
                    f"📅 {h(parsed_date)}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=_main_menu_keyboard(agent.get('lang', 'en')))
                return
            # Date not parsed — ask again
            lang_ctx = context.user_data.get('lang', 'en')
            hi = lang_ctx == 'hi'
            await update.message.reply_text(
                f"❓ {'तारीख समझ नहीं आई।' if hi else 'Could not understand the date.'}\n"
                f"{'उदा: kal, 25/03/2026, 2026-03-25' if hi else 'e.g. tomorrow, 25/03/2026, 2026-03-25'}",
                parse_mode=ParseMode.HTML)
            return

        if pending == 'calc_compute':
            # Multi-turn calculator — process text param input
            await _text_calc_multiturn(update, voice_ctx, text, context)
            return

    # ── Menu-button dispatch (belt-and-suspenders) ──────────────────────
    # Normalise by stripping Unicode variation selectors (U+FE0E/FE0F)
    # so keyboard labels always match regardless of how Telegram sends them.
    _strip_vs = str.maketrans("", "", "\ufe0e\ufe0f")
    norm = text.translate(_strip_vs)

    _catch_all_menu = {
        # NOTE: Add Lead, Follow-up, Calculator are handled by ConversationHandler
        # entry points at higher priority, so they won't normally reach here.
        # But keep them as safety net.
        "➕ Add Lead": cmd_addlead,     "➕ लीड जोड़ें": cmd_addlead,
        "📊 Pipeline": cmd_pipeline,    "📊 पाइपलाइन": cmd_pipeline,
        "📋 Leads": cmd_leads,          "📋 लीड्स": cmd_leads,
        "📋 My Leads": cmd_leads,        "📋 मेरी लीड्स": cmd_leads,
        "📞 Follow-up": cmd_followup,   "📞 फॉलो-अप": cmd_followup,
        "🧮 Calculator": cmd_calc,      "🧮 कैलकुलेटर": cmd_calc,
        "🔄 Renewals": cmd_renewals,    "🔄 रिन्यूअल": cmd_renewals,
        "📈 Dashboard": cmd_dashboard,  "📈 डैशबोर्ड": cmd_dashboard,
        "🤖 AI Tools": cmd_ai,          "🤖 AI टूल्स": cmd_ai,
        "⚙️ Settings": cmd_settings,    "⚙️ सेटिंग्स": cmd_settings,
    }
    # Build a normalised lookup once
    norm_menu = {k.translate(_strip_vs): v for k, v in _catch_all_menu.items()}

    handler = norm_menu.get(norm)
    if handler:
        agent = await db.get_agent(str(update.effective_user.id))
        if not agent:
            await update.message.reply_text(
                "👋 Please register first — type /start",
                reply_markup=ReplyKeyboardRemove())
            return
        # Reset stuck counter on successful menu match
        context.user_data['_unrecognized_count'] = 0
        # Set _agent so @registered decorator (if present) can use it
        context.user_data['_agent'] = agent
        logger.info("Menu-button fallback dispatching '%s' → %s", text, handler.__name__)
        return await handler(update, context)

    # ── Check for AI text input (custom objection, AI chat) ──────────
    agent = await db.get_agent(str(update.effective_user.id))
    if agent:
        context.user_data['_agent'] = agent
        if await _ai_text_handler(update, context):
            return

    # ── Not a registered agent ──────────────────────────────────────────
    if not agent:
        await update.message.reply_text(
            i18n.t('en', "welcome_get_started"),
            reply_markup=ReplyKeyboardRemove())
        return

    # ── "Just Talk" AI Mode ─────────────────────────────────────────────
    # Instead of "didn't understand", use AI to detect intent from text
    lang = agent.get('lang', 'en')

    # ── Stuck detection: track consecutive unrecognized messages ────────
    _unrec_key = '_unrecognized_count'
    unrec_count = context.user_data.get(_unrec_key, 0) + 1
    context.user_data[_unrec_key] = unrec_count

    # After 3 unrecognized messages, proactively offer help
    if unrec_count >= 3 and unrec_count % 3 == 0:
        context.user_data[_unrec_key] = 0  # reset counter
        await update.message.reply_text(
            i18n.t(lang, "stuck_help"),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_menu_keyboard(lang))
        return

    # Skip very short / greeting-like messages
    if len(text) < 3:
        await update.message.reply_text(
            i18n.t(lang, "didnt_understand"),
            reply_markup=_main_menu_keyboard(lang))
        return

    # Check if agent is blocked
    if await db.is_agent_blocked(agent['agent_id']):
        await update.message.reply_text(
            i18n.t(lang, "voice_blocked"), parse_mode=ParseMode.HTML)
        return

    # ── AI quota check ──────────────────────────────────────────────────
    quota = await db.check_ai_quota(agent['agent_id'])
    if not quota['allowed']:
        await update.message.reply_text(
            i18n.t(lang, "ai_quota_reached",
                   used=quota['used'], limit=quota['limit']),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_menu_keyboard(lang))
        return

    client = _get_gemini()
    if not client:
        # No Gemini configured — fall back to old behaviour
        await update.message.reply_text(
            i18n.t(lang, "didnt_understand"),
            reply_markup=_main_menu_keyboard(lang))
        return

    # Show processing indicator
    processing_msg = await update.message.reply_text(
        i18n.t(lang, "just_talk_thinking"))

    try:
        prompt = _JUST_TALK_PROMPT.format(
            message=text[:500],
            today=datetime.now().strftime('%Y-%m-%d (%A)')
        )

        response = await client.aio.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=[prompt]
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
        data = json.loads(raw_text)

    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Just Talk parse error: %s", e)
        try:
            await processing_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            i18n.t(lang, "didnt_understand"),
            reply_markup=_main_menu_keyboard(lang))
        return

    # ── Abuse check ───────────────────────────────────────────────────
    has_abuse = data.get('has_abuse', False) or _contains_abuse(text)
    if has_abuse:
        abused = await _check_abuse(
            agent['agent_id'], text, lang, processing_msg)
        if abused:
            return

    intent = data.get('intent', 'general')
    confidence = data.get('confidence', 'low')
    data['transcript'] = data.get('transcript', text)

    # Successfully understood — reset stuck counter & log AI usage
    context.user_data['_unrecognized_count'] = 0
    await db.log_ai_usage(
        tenant_id=agent.get('tenant_id'),
        agent_id=agent['agent_id'],
        feature='just_talk',
        tokens_in=len(text) // 4,
        tokens_out=len(raw_text) // 4,
        source='telegram')

    # Log the just-talk action
    await db.log_voice_action(
        agent_id=agent['agent_id'],
        transcript=text,
        extracted_data=json.dumps(data),
        audio_duration=0  # text, not audio
    )

    # ── Route by intent ───────────────────────────────────────────────
    if intent == 'ask_ai':
        # Direct AI question — answer it
        question = data.get('ai_question') or text
        answer = await ai.ask_insurance_ai(question, lang=lang)
        if len(answer) > 3800:
            answer = answer[:3800] + "\n\n... (truncated)"
        await processing_msg.edit_text(
            f"💬 <b>AI Answer</b>\n━━━━━━━━━━━━━━━━━━\n\n{h(answer)}",
            parse_mode=ParseMode.HTML)
        return

    if intent == 'general':
        # Greeting or unclear — show Just Talk welcome
        await processing_msg.edit_text(
            i18n.t(lang, "just_talk_welcome"),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_menu_keyboard(lang))
        return

    # ── Calculator intents — handle regardless of confidence ──────────
    if intent == 'open_calculator':
        await _voice_handle_open_calculator(processing_msg, data, agent, lang)
        return
    if intent == 'select_calculator':
        await _voice_handle_select_calculator(processing_msg, data, agent, lang)
        return
    if intent == 'calc_compute':
        await _voice_handle_calc_compute(processing_msg, data, agent, lang, context)
        return
    if intent == 'send_calc_result':
        await _voice_handle_send_calc_result(processing_msg, data, agent, lang, context)
        return
    if intent == 'show_team':
        await _voice_handle_show_team(processing_msg, data, agent, lang)
        return
    if intent == 'show_plans':
        await _voice_handle_show_plans(processing_msg, data, agent, lang)
        return
    if intent == 'show_settings':
        await _voice_handle_show_settings(processing_msg, data, agent, lang)
        return
    if intent == 'sa_panel':
        await _voice_handle_sa_panel(processing_msg, data, agent, lang)
        return

    # ── Actionable intents — confirm before executing ─────────────────
    if confidence == 'high':
        # High confidence — show preview + confirm
        context.user_data['voice_data'] = data
        context.user_data['voice_duration'] = 0

        if intent == 'create_lead':
            await _voice_handle_create_lead(
                processing_msg, data, agent, lang, 0, context)
        elif intent == 'log_meeting':
            await _voice_handle_log_meeting(
                processing_msg, data, agent, lang, context)
        elif intent == 'update_stage':
            await _voice_handle_update_stage(
                processing_msg, data, agent, lang, context)
        elif intent == 'log_payment':
            await _voice_handle_log_payment(
                processing_msg, data, agent, lang, context)
        elif intent == 'log_call':
            await _voice_handle_log_call(
                processing_msg, data, agent, lang, context)
        elif intent == 'add_policy':
            await _voice_handle_add_policy(
                processing_msg, data, agent, lang, context)
        elif intent == 'schedule_meeting':
            await _voice_handle_schedule_meeting(
                processing_msg, data, agent, lang, context)
        elif intent == 'mark_renewal_done':
            await _voice_handle_mark_renewal_done(
                processing_msg, data, agent, lang, context)
        elif intent == 'log_claim':
            await _voice_handle_log_claim(
                processing_msg, data, agent, lang, context)
        elif intent == 'create_reminder':
            await _voice_handle_create_reminder(
                processing_msg, data, agent, lang)
        elif intent == 'add_note':
            await _voice_handle_add_note(
                processing_msg, data, agent, lang, context)
        else:
            await _voice_handle_general(
                processing_msg, data, agent, lang, 0, context)
    else:
        # Medium/low confidence — show what was understood + action buttons
        context.user_data['voice_data'] = data
        context.user_data['voice_duration'] = 0
        await _voice_handle_general(
            processing_msg, data, agent, lang, 0, context)


# =============================================================================
#  CANCEL HANDLER
# =============================================================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel any conversation, keep persistent menu."""
    context.user_data.clear()
    agent = await db.get_agent(str(update.effective_user.id))
    lang = agent.get('lang', 'en') if agent else 'en'
    await update.message.reply_text(
        i18n.t(lang, "cancelled"),
        reply_markup=_main_menu_keyboard(lang))
    return ConversationHandler.END


# =============================================================================
#  /refresh — Re-register command menus after bot updates (owner/admin only)
# =============================================================================

@registered
@owner_only
async def cmd_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Re-register bot command menu and clear cached data.
    Useful after bot updates so new features/translations take effect."""
    agent = context.user_data.get('_agent', {})
    lang = agent.get('lang', 'en')
    try:
        from telegram import BotCommand
        commands = [
            ("start", "Start / Main Menu"),
            ("addlead", "Add a new lead"),
            ("pipeline", "View lead pipeline"),
            ("leads", "List all leads"),
            ("followup", "Follow-up reminders"),
            ("calc", "Financial calculators"),
            ("renewals", "Policy renewals"),
            ("dashboard", "Business dashboard"),
            ("ai", "AI sales tools"),
            ("weblogin", "🌐 Login to web dashboard"),
            ("settings", "Bot settings"),
            ("lang", "🌐 Change language / भाषा बदलें"),
            ("help", "Help & commands list"),
        ]
        await context.bot.set_my_commands(
            [BotCommand(cmd, desc) for cmd, desc in commands])
        # Clear cached user data so fresh agent/plan info is loaded on next command
        context.user_data.pop('_agent', None)
        msg = "✅ बॉट मेनू अपडेट हो गया। नई सुविधाएँ अब सक्रिय हैं।" if lang == 'hi' else \
              "✅ Bot menu refreshed. New features are now active."
        await update.message.reply_text(msg, reply_markup=_main_menu_keyboard(lang))
    except Exception as e:
        logger.error("Error in /refresh: %s", e)
        err = "❌ रिफ्रेश विफल। बाद में पुनः प्रयास करें।" if lang == 'hi' else \
              "❌ Refresh failed. Please try again later."
        await update.message.reply_text(err)


# =============================================================================
#  SUPER-ADMIN COMMANDS (platform owner — phone in SUPERADMIN_PHONES)
# =============================================================================

async def _sa_get_stats() -> dict:
    """Platform-wide statistics for super-admin."""
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        r = lambda q: conn.execute(q)
        cur = await (await r("SELECT COUNT(*) FROM tenants")).fetchone(); total = cur[0]
        cur = await (await r("SELECT COUNT(*) FROM tenants WHERE is_active=1")).fetchone(); active = cur[0]
        cur = await (await r("SELECT COUNT(*) FROM tenants WHERE subscription_status='trial' AND is_active=1")).fetchone(); trials = cur[0]
        cur = await (await r("SELECT COUNT(*) FROM tenants WHERE subscription_status IN ('active','paid') AND is_active=1")).fetchone(); paid = cur[0]
        cur = await (await r("SELECT COUNT(*) FROM tenants WHERE subscription_status='expired'")).fetchone(); expired = cur[0]
        cur = await (await r("SELECT COUNT(*) FROM agents")).fetchone(); agents = cur[0]
        cur = await (await r("SELECT COUNT(*) FROM leads")).fetchone(); leads = cur[0]
    return dict(total=total, active=active, trials=trials, paid=paid,
                expired=expired, agents=agents, leads=leads)


async def _sa_verify_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle SA OTP verification from text message."""
    if not context.user_data.get('_sa_otp_pending'):
        return  # Not in SA OTP flow
    import biz_auth as auth
    otp = update.message.text.strip()
    phone = context.user_data.get('_sa_phone', '')

    # Allow cancel
    if otp.lower() in ('cancel', '/cancel', 'exit', 'quit'):
        context.user_data.pop('_sa_otp_pending', None)
        context.user_data.pop('_sa_phone', None)
        context.user_data.pop('_sa_otp_attempts', None)
        await update.message.reply_text("🔓 SA authentication cancelled.")
        return

    if not phone or phone not in SUPERADMIN_PHONES:
        context.user_data.pop('_sa_otp_pending', None)
        context.user_data.pop('_sa_phone', None)
        await update.message.reply_text("🔒 Super-admin access only.")
        return

    # Max attempts guard
    attempts = context.user_data.get('_sa_otp_attempts', 0) + 1
    context.user_data['_sa_otp_attempts'] = attempts
    if attempts > 5:
        context.user_data.pop('_sa_otp_pending', None)
        context.user_data.pop('_sa_phone', None)
        context.user_data.pop('_sa_otp_attempts', None)
        await update.message.reply_text(
            "❌ Too many failed attempts. Type /sa to try again.")
        return

    if not auth.verify_otp(phone, otp):
        remaining = 5 - attempts
        await update.message.reply_text(
            f"❌ Invalid OTP. ({remaining} attempts left)\n"
            f"Type /sa to resend, or 'cancel' to abort.")
        return

    # OTP verified — create session
    _sa_sessions[phone] = {'ts': time.time(), 'tg_id': str(update.effective_user.id)}
    context.user_data.pop('_sa_otp_pending', None)
    context.user_data.pop('_sa_phone', None)
    await db.log_audit("sa_otp_login",
                       f"SA logged in from Telegram {update.effective_user.id}",
                       tenant_id=0)

    # Show SA panel
    stats = await _sa_get_stats()
    inactive_count = len(await db.get_inactive_agents(60))
    keyboard = [
        [InlineKeyboardButton("📊 Tenants", callback_data="sa_tenants"),
         InlineKeyboardButton("📈 Stats", callback_data="sa_stats")],
        [InlineKeyboardButton("🤖 Bots", callback_data="sa_bots"),
         InlineKeyboardButton("➕ Create Firm", callback_data="sa_create_firm")],
        [InlineKeyboardButton(f"😴 Inactive Agents ({inactive_count})", callback_data="sa_inactive")],
    ]
    inactive_line = f"\n😴 Inactive (60d+): {inactive_count}" if inactive_count else ""
    await update.message.reply_text(
        f"✅ <b>SA Session Active</b> (1 hour)\n\n"
        f"🛡️ <b>Super Admin Panel</b>\n\n"
        f"👥 Tenants: {stats['total']}  |  🟢 Active: {stats['active']}\n"
        f"⏳ Trials: {stats['trials']}  |  💰 Paid: {stats['paid']}\n"
        f"❌ Expired: {stats['expired']}  |  👤 Agents: {stats['agents']}\n"
        f"📋 Leads: {stats['leads']}{inactive_line}\n\n"
        f"📝 Quick commands:\n"
        f"<code>/sa_create Firm | Owner | Phone | Email | Plan</code>\n"
        f"<code>/sa_edit TenantID | field | value</code>\n\n"
        f"Choose an action:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard))


async def cmd_sa_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End the super-admin OTP session."""
    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)
    if agent and agent.get('phone', '') in SUPERADMIN_PHONES:
        phone = agent['phone']
        _sa_sessions.pop(phone, None)
        await db.log_audit("sa_otp_logout",
                           f"SA logged out from Telegram {user_id}",
                           tenant_id=0)
        await update.message.reply_text("🔓 SA session ended. Type /sa to re-authenticate.")
    else:
        await update.message.reply_text("🔒 Super-admin access only.")


@superadmin_only
async def cmd_sa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Super-admin main panel with live stats."""
    stats = await _sa_get_stats()
    inactive_count = len(await db.get_inactive_agents(60))
    keyboard = [
        [InlineKeyboardButton("📊 Tenants", callback_data="sa_tenants"),
         InlineKeyboardButton("📈 Stats", callback_data="sa_stats")],
        [InlineKeyboardButton("🤖 Bots", callback_data="sa_bots"),
         InlineKeyboardButton("➕ Create Firm", callback_data="sa_create_firm")],
        [InlineKeyboardButton(f"😴 Inactive Agents ({inactive_count})", callback_data="sa_inactive")],
        [InlineKeyboardButton("🩺 Health Check", callback_data="sa_health")],
    ]
    inactive_line = f"\n😴 Inactive (60d+): {inactive_count}" if inactive_count else ""
    await update.message.reply_text(
        f"🛡️ *Super Admin Panel*\n\n"
        f"👥 Tenants: {stats['total']}  |  🟢 Active: {stats['active']}\n"
        f"⏳ Trials: {stats['trials']}  |  💰 Paid: {stats['paid']}\n"
        f"❌ Expired: {stats['expired']}  |  👤 Agents: {stats['agents']}\n"
        f"📋 Leads: {stats['leads']}{inactive_line}\n\n"
        f"📝 Quick commands:\n"
        f"`/sa_create Firm | Owner | Phone | Email | Plan`\n"
        f"`/sa_edit TenantID | field | value`\n\n"
        f"Choose an action:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard))


@superadmin_only
async def cmd_sa_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a firm manually.
    Usage: /sa_create Firm Name | Owner Name | Phone | Email | Plan"""
    raw = " ".join(context.args) if context.args else ""
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        await update.message.reply_text(
            "Usage:\n`/sa_create Firm | Owner | Phone | Email | Plan`\n\n"
            "Plans: trial, individual, team, enterprise\n"
            "Example:\n`/sa_create ABC Ins | Ravi Kumar | 9876543210 | ravi@email.com | team`",
            parse_mode=ParseMode.MARKDOWN)
        return

    firm, owner, phone = parts[0], parts[1], parts[2]
    email = parts[3] if len(parts) > 3 else None
    plan = parts[4] if len(parts) > 4 else 'trial'
    if plan not in ('trial', 'individual', 'team', 'enterprise'):
        plan = 'trial'

    # Duplicate check before creation
    dup = await db.check_phone_email_duplicate(phone=phone, email=email)
    if dup:
        field = dup['field']
        existing = dup['tenant']
        await update.message.reply_text(
            f"❌ *Duplicate {field}*\n\n"
            f"Already registered with: #{existing['tenant_id']} ({html_mod.escape(existing['firm_name'])})\n\n"
            f"Use /sa\\_edit to modify the existing tenant.",
            parse_mode=ParseMode.MARKDOWN)
        return

    pf = db.PLAN_FEATURES.get(plan, db.PLAN_FEATURES['trial'])

    tid = await db.create_tenant(firm_name=firm, owner_name=owner,
                                 phone=phone, email=email, lang='en',
                                 signup_channel='sa_manual')
    await db.update_tenant(tid, plan=plan, max_agents=pf['max_agents'])
    logger.info("🔧 SA created firm #%d '%s' plan=%s", tid, firm, plan)
    await update.message.reply_text(
        f"✅ *Firm Created*\n\n"
        f"🏢 {html_mod.escape(firm)}\n👤 {html_mod.escape(owner)}\n"
        f"📞 {phone}\n📧 {email or '—'}\n📋 Plan: {plan}\n🆔 ID: {tid}\n\n"
        f"Owner can /start in the bot to complete registration.",
        parse_mode=ParseMode.MARKDOWN)


@superadmin_only
async def cmd_sa_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SA: Edit tenant fields from bot.
    Usage: /sa_edit <tenant_id> <field> <value>
    Fields: firm_name, owner_name, phone, email, city, plan"""
    raw = " ".join(context.args) if context.args else ""
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        await update.message.reply_text(
            "Usage:\n`/sa_edit TenantID | field | new_value`\n\n"
            "Fields: firm\\_name, owner\\_name, phone, email, city, plan, is\\_active\n"
            "Example:\n`/sa_edit 5 | phone | 9876543210`\n"
            "`/sa_edit 5 | city | Mumbai`",
            parse_mode=ParseMode.MARKDOWN)
        return

    try:
        tid = int(parts[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid tenant ID. Must be a number.")
        return

    field = parts[1].strip().lower()
    value = parts[2].strip()
    allowed = {'firm_name', 'owner_name', 'phone', 'email', 'city', 'plan', 'is_active'}

    if field not in allowed:
        await update.message.reply_text(
            f"❌ Invalid field: {field}\n\nAllowed: {', '.join(sorted(allowed))}")
        return

    tenant = await db.get_tenant(tid)
    if not tenant:
        await update.message.reply_text(f"❌ Tenant #{tid} not found.")
        return

    # Type conversion
    if field == 'is_active':
        value = 1 if value.lower() in ('1', 'yes', 'true') else 0
    if field == 'plan':
        if value not in ('trial', 'individual', 'team', 'enterprise'):
            await update.message.reply_text("❌ Invalid plan. Use: trial, individual, team, enterprise")
            return
        pf = db.PLAN_FEATURES.get(value, db.PLAN_FEATURES['trial'])
        await db.update_tenant(tid, plan=value, max_agents=pf['max_agents'])
    else:
        # Dedup check for phone/email changes
        if field in ('phone', 'email'):
            dup = await db.check_phone_email_duplicate(
                phone=value if field == 'phone' else None,
                email=value if field == 'email' else None,
                exclude_tenant_id=tid)
            if dup:
                await update.message.reply_text(
                    f"❌ Duplicate {dup['field']}: already in use by tenant #{dup['tenant']['tenant_id']}")
                return
        await db.update_tenant(tid, **{field: value})

    logger.info("🔧 SA edited tenant #%d: %s=%s", tid, field, value)
    await update.message.reply_text(
        f"✅ *Tenant #{tid} Updated*\n\n"
        f"📝 {field} → `{value}`",
        parse_mode=ParseMode.MARKDOWN)


async def _sa_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all sa_* inline-button callbacks."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Auth check
    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)
    if not agent or agent.get('phone', '') not in SUPERADMIN_PHONES:
        await query.edit_message_text("🔒 Super-admin access only.")
        return

    # Check SA OTP session
    phone = agent.get('phone', '')
    sa_session = _sa_sessions.get(phone)
    if not sa_session or (time.time() - sa_session['ts']) > SA_SESSION_TIMEOUT:
        _sa_sessions.pop(phone, None)
        await query.edit_message_text("🔐 SA session expired. Type /sa to re-authenticate.")
        return

    # ── Router ──
    if data == "sa_tenants":
        await _sa_show_tenants(query, 0)
    elif data == "sa_stats":
        await _sa_show_stats(query)
    elif data == "sa_bots":
        await _sa_show_bots(query)
    elif data == "sa_create_firm":
        await query.edit_message_text(
            "➕ *Create Firm*\n\nSend:\n"
            "`/sa_create Firm | Owner | Phone | Email | Plan`\n\n"
            "Plans: trial, individual, team, enterprise",
            parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("sa_tenant_"):
        await _sa_show_tenant_detail(query, int(data.split("_")[2]))
    elif data.startswith("sa_activate_"):
        await _sa_do_activate(query, int(data.split("_")[2]))
    elif data.startswith("sa_deactivate_"):
        await _sa_do_deactivate(query, int(data.split("_")[2]))
    elif data.startswith("sa_extend_"):
        await _sa_do_extend(query, int(data.split("_")[2]))
    elif data.startswith("sa_agents_"):
        await _sa_show_agents(query, int(data.split("_")[2]))
    elif data.startswith("sa_agdeact_"):
        parts = data.split("_")
        await _sa_agent_deactivate(query, int(parts[2]), int(parts[3]))
    elif data.startswith("sa_agreact_"):
        parts = data.split("_")
        await _sa_agent_reactivate(query, int(parts[2]), int(parts[3]))
    elif data == "sa_inactive":
        await _sa_show_inactive_agents(query)
    elif data.startswith("sa_logs_"):
        await _sa_show_tenant_logs(query, int(data.split("_")[2]))
    elif data.startswith("sa_errors_"):
        await _sa_show_tenant_errors(query, int(data.split("_")[2]))
    elif data.startswith("sa_weblogin_"):
        await _sa_impersonate_weblogin(query, int(data.split("_")[2]))
    elif data.startswith("sa_plan_"):
        parts = data.split("_"); await _sa_do_change_plan(query, int(parts[2]), parts[3])
    elif data.startswith("sa_page_"):
        await _sa_show_tenants(query, int(data.split("_")[2]))
    elif data == "sa_health":
        await _sa_show_health(query)
    elif data == "sa_back":
        stats = await _sa_get_stats()
        inactive_count = len(await db.get_inactive_agents(60))
        kb = [
            [InlineKeyboardButton("📊 Tenants", callback_data="sa_tenants"),
             InlineKeyboardButton("📈 Stats", callback_data="sa_stats")],
            [InlineKeyboardButton("🤖 Bots", callback_data="sa_bots"),
             InlineKeyboardButton("➕ Create Firm", callback_data="sa_create_firm")],
            [InlineKeyboardButton(f"😴 Inactive Agents ({inactive_count})", callback_data="sa_inactive")],
            [InlineKeyboardButton("🩺 Health Check", callback_data="sa_health")],
        ]
        inactive_line = f"\n😴 Inactive (60d+): {inactive_count}" if inactive_count else ""
        await query.edit_message_text(
            f"🛡️ *Super Admin Panel*\n\n"
            f"👥 Tenants: {stats['total']}  |  🟢 Active: {stats['active']}\n"
            f"⏳ Trials: {stats['trials']}  |  💰 Paid: {stats['paid']}\n"
            f"❌ Expired: {stats['expired']}  |  👤 Agents: {stats['agents']}\n"
            f"📋 Leads: {stats['leads']}{inactive_line}\n\nChoose an action:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(kb))


async def _sa_show_tenants(query, page=0):
    """Paginated tenant list."""
    import aiosqlite
    per_page = 8
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT COUNT(*) FROM tenants")
        total = (await cur.fetchone())[0]
        cur = await conn.execute(
            "SELECT tenant_id, firm_name, plan, subscription_status, is_active "
            "FROM tenants ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, page * per_page))
        tenants = [dict(r) for r in await cur.fetchall()]

    _se = {'trial': '⏳', 'active': '💰', 'paid': '💰',
            'expired': '❌', 'wiped': '🗑️'}
    lines, btns = [], []
    for t in tenants:
        se = _se.get(t['subscription_status'], '❓')
        ac = '🟢' if t['is_active'] else '🔴'
        lines.append(f"{ac} #{t['tenant_id']} {html_mod.escape(t['firm_name'][:20])} — {se} {t['plan']}")
        btns.append([InlineKeyboardButton(
            f"#{t['tenant_id']} {t['firm_name'][:18]}",
            callback_data=f"sa_tenant_{t['tenant_id']}")])

    text = f"📊 *Tenants* (page {page+1}, {total} total)\n\n" + "\n".join(lines)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"sa_page_{page-1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"sa_page_{page+1}"))
    if nav: btns.append(nav)
    btns.append([InlineKeyboardButton("🔙 Back", callback_data="sa_back")])
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(btns))


async def _sa_show_tenant_detail(query, tenant_id):
    """Detailed tenant info + action buttons."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        await query.edit_message_text("❌ Tenant not found.")
        return

    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM agents WHERE tenant_id=?", (tenant_id,))
        ac = (await cur.fetchone())[0]
        cur = await conn.execute(
            "SELECT COUNT(*) FROM leads l JOIN agents a ON l.agent_id=a.agent_id "
            "WHERE a.tenant_id=?", (tenant_id,))
        lc = (await cur.fetchone())[0]
        cur = await conn.execute(
            "SELECT COUNT(*) FROM policies p JOIN agents a ON p.agent_id=a.agent_id "
            "WHERE a.tenant_id=?", (tenant_id,))
        pc = (await cur.fetchone())[0]

    act = '🟢 Active' if tenant['is_active'] else '🔴 Inactive'
    city = tenant.get('city', '') or '—'
    acct_type = (tenant.get('account_type', '') or 'firm').title()
    channel = (tenant.get('signup_channel', '') or 'web').upper()
    tg_id = tenant.get('owner_telegram_id', '') or '—'
    text = (
        f"🏢 *{html_mod.escape(tenant['firm_name'])}*\n\n"
        f"👤 Owner: {html_mod.escape(tenant['owner_name'])}\n"
        f"📞 {tenant.get('phone','—')}  |  📧 {tenant.get('email','—')}\n"
        f"🏙️ City: {city}  |  📂 Type: {acct_type}\n"
        f"📋 Plan: {tenant.get('plan','trial')}  |  💳 {tenant.get('subscription_status','—')}\n"
        f"🔘 {act}  |  📡 Channel: {channel}\n"
        f"⏳ Trial: {(tenant.get('trial_ends_at') or '—')[:10]}\n"
        f"👥 Agents: {ac}/{tenant.get('max_agents',1)}  |  📋 Leads: {lc}  |  🛡️ Policies: {pc}\n"
        f"🤖 Bot: {'✅' if tenant.get('tg_bot_token') else '❌'}  |  "
        f"💬 WA: {'✅' if tenant.get('wa_phone_id') else '❌'}\n"
        f"🆔 TG: {tg_id}\n"
        f"📅 Created: {(tenant.get('created_at') or '—')[:10]}\n")

    kb = []
    if tenant['is_active']:
        kb.append([InlineKeyboardButton("❌ Deactivate", callback_data=f"sa_deactivate_{tenant_id}")])
    else:
        kb.append([InlineKeyboardButton("✅ Activate", callback_data=f"sa_activate_{tenant_id}")])
    kb.append([InlineKeyboardButton("⏳ Extend +14d", callback_data=f"sa_extend_{tenant_id}")])
    plan_btns = [InlineKeyboardButton(f"→ {p.title()}", callback_data=f"sa_plan_{tenant_id}_{p}")
                 for p in ('individual', 'team', 'enterprise') if p != tenant.get('plan')]
    if plan_btns: kb.append(plan_btns)
    kb.append([InlineKeyboardButton("👥 Agents", callback_data=f"sa_agents_{tenant_id}"),
               InlineKeyboardButton("📋 Logs", callback_data=f"sa_logs_{tenant_id}")])
    kb.append([InlineKeyboardButton("⚠️ Errors", callback_data=f"sa_errors_{tenant_id}"),
               InlineKeyboardButton("🌐 Web Login", callback_data=f"sa_weblogin_{tenant_id}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="sa_tenants")])
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))


async def _sa_show_stats(query):
    """Detailed platform stats."""
    import aiosqlite
    stats = await _sa_get_stats()
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT plan, COUNT(*) FROM tenants WHERE is_active=1 GROUP BY plan")
        pdist = {r[0]: r[1] for r in await cur.fetchall()}
        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE created_at >= date('now','-7 days')")
        n7 = (await cur.fetchone())[0]
        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE created_at >= date('now','-30 days')")
        n30 = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM policies")
        tp = (await cur.fetchone())[0]
        cur = await conn.execute(
            "SELECT COUNT(*) FROM agents WHERE is_active=0")
        deact_agents = (await cur.fetchone())[0]
    inactive_60 = len(await db.get_inactive_agents(60))
    pd = "\n".join(f"  {p}: {c}" for p, c in pdist.items()) or "  (none)"
    text = (
        f"📈 *Platform Statistics*\n\n"
        f"👥 Total: {stats['total']}  |  🟢 Active: {stats['active']}\n"
        f"⏳ Trials: {stats['trials']}  |  💰 Paid: {stats['paid']}  |  ❌ Expired: {stats['expired']}\n\n"
        f"📊 *Plan Distribution:*\n{pd}\n\n"
        f"📈 New (7d): {n7}  |  New (30d): {n30}\n"
        f"👤 Agents: {stats['agents']}  |  🔴 Deactivated: {deact_agents}\n"
        f"😴 Inactive 60d+: {inactive_60}\n"
        f"📋 Leads: {stats['leads']}  |  🛡️ Policies: {tp}")
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="sa_back")]]
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))


async def _sa_show_bots(query):
    """Running bots status."""
    import biz_bot_manager as botmgr
    mgr = botmgr.bot_manager
    bl = []
    for tid, app_inst in mgr._bots.items():
        try:
            bi = app_inst.bot
            uname = (bi.username or '').replace('_', '\\_')
            fname = (bi.first_name or '').replace('_', '\\_')
            bl.append(f"  #{tid}: @{uname} ({fname})")
        except Exception:
            bl.append(f"  #{tid}: (error)")
    master = "🟢 Running" if mgr._master_bot else "🔴 Stopped"
    text = (f"🤖 *Bot Status*\n\nMaster: {master}\nTenant Bots: {len(bl)}\n\n"
            + ("\n".join(bl) if bl else "  No tenant bots running"))
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="sa_back")]]
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))


async def _sa_show_agents(query, tenant_id):
    """List agents for a tenant with full lifecycle info."""
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT agent_id, name, phone, role, is_active, last_active "
            "FROM agents WHERE tenant_id=?",
            (tenant_id,))
        agents = [dict(r) for r in await cur.fetchall()]
    if not agents:
        text = f"👥 *Agents for Tenant #{tenant_id}*\n\nNo agents registered."
        kb = [[InlineKeyboardButton("🔙 Tenant", callback_data=f"sa_tenant_{tenant_id}")]]
    else:
        lines = []
        for a in agents:
            re = '👑' if a['role'] == 'owner' else '👤'
            ae = '🟢' if a['is_active'] else '🔴'
            la = a.get('last_active')
            if la:
                try:
                    la_dt = datetime.fromisoformat(la)
                    days_ago = (datetime.now() - la_dt).days
                    la_str = f"{days_ago}d ago" if days_ago > 0 else "today"
                except (ValueError, TypeError):
                    la_str = "—"
            else:
                la_str = "never"
            lines.append(f"{ae} {re} {html_mod.escape(a['name'])} — {a.get('phone','—')} (active: {la_str})")
        active_count = sum(1 for a in agents if a['is_active'])
        text = f"👥 *Agents #{tenant_id}* ({active_count}/{len(agents)} active)\n\n" + "\n".join(lines)
        # Add per-agent action buttons for non-owner agents
        kb = []
        for a in agents:
            if a['role'] == 'owner':
                continue
            if a['is_active']:
                kb.append([InlineKeyboardButton(
                    f"🔴 Deactivate {a['name'][:15]}",
                    callback_data=f"sa_agdeact_{tenant_id}_{a['agent_id']}")])
            else:
                kb.append([InlineKeyboardButton(
                    f"🟢 Reactivate {a['name'][:15]}",
                    callback_data=f"sa_agreact_{tenant_id}_{a['agent_id']}")])
        kb.append([InlineKeyboardButton("🔙 Tenant", callback_data=f"sa_tenant_{tenant_id}")])
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))


async def _sa_agent_deactivate(query, tenant_id, agent_id):
    """SA deactivates an agent (full block)."""
    ok = await db.deactivate_agent_full(agent_id, tenant_id, reason='sa_action')
    if ok:
        await query.answer("🔴 Agent deactivated!")
        logger.info("🔧 SA deactivated agent %d in tenant %d", agent_id, tenant_id)
    else:
        await query.answer("❌ Failed to deactivate")
    await _sa_show_agents(query, tenant_id)


async def _sa_agent_reactivate(query, tenant_id, agent_id):
    """SA reactivates a deactivated agent."""
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE agents SET is_active=1, telegram_id=?, updated_at=datetime('now') "
            "WHERE agent_id=? AND tenant_id=?",
            (f"__unlinked_{agent_id}", agent_id, tenant_id))
        await conn.commit()
    await db.log_audit("agent_reactivated_sa",
                       f"Agent #{agent_id} reactivated by SA",
                       tenant_id=tenant_id, agent_id=agent_id)
    await query.answer("🟢 Agent reactivated! They need to /start again.")
    logger.info("🔧 SA reactivated agent %d in tenant %d", agent_id, tenant_id)
    await _sa_show_agents(query, tenant_id)


async def _sa_show_inactive_agents(query):
    """Platform-wide view of agents approaching or past 90-day inactivity."""
    inactive = await db.get_inactive_agents(60)  # Show from 60+ days
    if not inactive:
        text = "😴 *Inactive Agents*\n\nNo agents inactive for 60+ days."
    else:
        lines = []
        for a in inactive:
            la = a.get('last_active')
            if la:
                try:
                    days = (datetime.now() - datetime.fromisoformat(la)).days
                except (ValueError, TypeError):
                    days = '?'
            else:
                days = '?'
            warn = '🔴' if isinstance(days, int) and days >= 90 else '🟡'
            firm = a.get('firm_name', f"T#{a['tenant_id']}")[:15]
            lines.append(f"{warn} {html_mod.escape(a.get('name','?'))} — {firm} ({days}d)")
        text = (f"😴 *Inactive Agents* ({len(inactive)})\n"
                f"🟡 60-89 days  |  🔴 90+ days (auto-deactivate)\n\n"
                + "\n".join(lines[:30]))
        if len(lines) > 30:
            text += f"\n\n... and {len(lines) - 30} more"
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="sa_back")]]
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))


async def _sa_show_health(query):
    """Show system health: unresolved events, recent errors, component status."""
    try:
        event_stats = await db.get_system_event_stats()
        unresolved = event_stats.get('unresolved', 0)
        by_severity = event_stats.get('by_severity', {})
        critical = by_severity.get('critical', 0)
        warning = by_severity.get('warning', 0)

        # Get recent critical events
        events = await db.get_system_events(severity='critical', resolved=0, limit=5)
        recent_lines = []
        for e in events[:5]:
            title = (e.get('title') or '')[:60]
            ts = (e.get('created_at') or '')[:16]
            recent_lines.append(f"  🔴 {title}\n     {ts}")

        health_icon = "🟢" if critical == 0 else ("🔴" if critical > 3 else "🟡")
        text = (
            f"🩺 *System Health* {health_icon}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 *Unresolved Events:* {unresolved}\n"
            f"🔴 Critical: {critical}  |  🟡 Warning: {warning}\n"
        )
        if recent_lines:
            text += f"\n📋 *Recent Critical Events:*\n" + "\n".join(recent_lines)
        else:
            text += "\n✅ No critical events!"

        text += "\n\n_Check web SA panel for full details_"
    except Exception as e:
        text = f"🩺 *System Health*\n\n⚠️ Could not fetch health data: {str(e)[:100]}"

    kb = [[InlineKeyboardButton("🔙 Back", callback_data="sa_back")]]
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))


async def _sa_do_activate(query, tid):
    await db.update_tenant(tid, is_active=1, subscription_status='paid', plan='individual')
    logger.info("🔧 SA activated tenant %d", tid)
    await query.answer("✅ Activated!")
    await _sa_show_tenant_detail(query, tid)


async def _sa_do_deactivate(query, tid):
    await db.update_tenant(tid, is_active=0, subscription_status='expired')
    logger.info("🔧 SA deactivated tenant %d", tid)
    await query.answer("❌ Deactivated!")
    await _sa_show_tenant_detail(query, tid)


async def _sa_do_extend(query, tid):
    tenant = await db.get_tenant(tid)
    if not tenant:
        await query.answer("Not found"); return
    try:
        end_dt = datetime.fromisoformat(tenant.get('trial_ends_at', ''))
    except (ValueError, TypeError):
        end_dt = datetime.now()
    new_end = end_dt + timedelta(days=14)
    await db.update_tenant(tid, trial_ends_at=new_end.isoformat(),
                           is_active=1, subscription_status='trial')
    logger.info("🔧 SA extended trial %d → %s", tid, new_end.isoformat())
    await query.answer(f"⏳ Extended to {new_end.strftime('%d %b %Y')}")
    await _sa_show_tenant_detail(query, tid)


async def _sa_do_change_plan(query, tid, plan):
    pi = db.PLAN_PRICING.get(plan)
    if not pi:
        await query.answer("Invalid plan"); return
    status = 'paid' if plan != 'trial' else 'trial'
    await db.update_tenant(tid, plan=plan, max_agents=pi['max_agents'],
                           subscription_status=status)
    logger.info("🔧 SA plan %d → %s", tid, plan)
    await query.answer(f"✅ → {plan}")
    await _sa_show_tenant_detail(query, tid)


async def _sa_show_tenant_logs(query, tenant_id):
    """Show recent audit log & activity for a tenant — SA error viewer."""
    import aiosqlite
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        await query.edit_message_text("❌ Tenant not found.")
        return

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Recent audit entries
        cur = await conn.execute(
            "SELECT action, detail, created_at FROM audit_log "
            "WHERE tenant_id=? ORDER BY created_at DESC LIMIT 15",
            (tenant_id,))
        audits = [dict(r) for r in await cur.fetchall()]

        # Recent interactions (errors, complaints)
        cur = await conn.execute(
            "SELECT i.type, i.summary, i.created_at, a.name "
            "FROM interactions i JOIN agents a ON i.agent_id=a.agent_id "
            "WHERE a.tenant_id=? ORDER BY i.created_at DESC LIMIT 10",
            (tenant_id,))
        interactions = [dict(r) for r in await cur.fetchall()]

        # Recent support tickets
        cur = await conn.execute(
            "SELECT subject, status, priority, created_at FROM support_tickets "
            "WHERE tenant_id=? ORDER BY created_at DESC LIMIT 5",
            (tenant_id,))
        tickets = [dict(r) for r in await cur.fetchall()]

    text = f"📋 *Logs — {html_mod.escape(tenant['firm_name'])}*\n"
    text += f"Tenant #{tenant_id}\n\n"

    # Support tickets
    if tickets:
        text += "🎫 *Recent Tickets:*\n"
        for t in tickets:
            p = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(t.get('priority', ''), '⚪')
            s = t.get('status', '?')
            text += f"  {p} {html_mod.escape(str(t.get('subject', ''))[:40])} — {s}\n"
        text += "\n"

    # Audit trail
    if audits:
        text += "🔍 *Recent Audit:*\n"
        for a in audits[:10]:
            ts = (a.get('created_at', '') or '')[-8:]  # Time portion
            detail = html_mod.escape(str(a.get('detail', ''))[:50])
            text += f"  `{a['action'][:20]}` {detail}\n"
        text += "\n"

    # Recent interactions
    if interactions:
        text += "💬 *Recent Activity:*\n"
        for i in interactions[:5]:
            name = html_mod.escape(str(i.get('name', ''))[:12])
            summary = html_mod.escape(str(i.get('summary', ''))[:40])
            text += f"  {name}: {summary}\n"

    if not audits and not interactions and not tickets:
        text += "_(No recent activity)_"

    kb = [[InlineKeyboardButton("🔙 Tenant", callback_data=f"sa_tenant_{tenant_id}")]]
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))


async def _sa_show_tenant_errors(query, tenant_id):
    """Show errors and system events specific to a tenant — proactive SA visibility."""
    import aiosqlite
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        await query.edit_message_text("❌ Tenant not found.")
        return

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # System events for this tenant
        cur = await conn.execute(
            "SELECT title, severity, event_type, created_at, resolved FROM system_events "
            "WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 10",
            (tenant_id,))
        events = [dict(r) for r in await cur.fetchall()]

        # Error-related audit entries
        cur = await conn.execute(
            "SELECT action, detail, created_at FROM audit_log "
            "WHERE tenant_id = ? AND (action LIKE '%error%' OR action LIKE '%fail%' "
            "OR action LIKE '%denied%') ORDER BY created_at DESC LIMIT 10",
            (tenant_id,))
        error_logs = [dict(r) for r in await cur.fetchall()]

    text = f"⚠️ *Errors — {html_mod.escape(tenant['firm_name'])}*\n"
    text += f"Tenant #{tenant_id}\n\n"

    if events:
        text += "🔴 *System Events:*\n"
        for e in events[:8]:
            sev = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(e.get('severity', ''), '⚪')
            resolved = '✅' if e.get('resolved') else '❌'
            title = html_mod.escape(str(e.get('title', ''))[:45])
            ts = (e.get('created_at', '') or '')[:16]
            text += f"  {sev} {title}\n     {ts} {resolved}\n"
        text += "\n"

    if error_logs:
        text += "📋 *Error Audit Log:*\n"
        for a in error_logs[:8]:
            detail = html_mod.escape(str(a.get('detail', ''))[:50])
            ts = (a.get('created_at', '') or '')[:16]
            text += f"  `{a['action'][:20]}` {detail}\n"
        text += "\n"

    if not events and not error_logs:
        text += "✅ *No errors found!* This tenant is running clean."

    kb = [[InlineKeyboardButton("🔙 Tenant", callback_data=f"sa_tenant_{tenant_id}")]]
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))


async def _sa_impersonate_weblogin(query, tenant_id):
    """Generate impersonation web login link for SA to view tenant's dashboard."""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        await query.edit_message_text("❌ Tenant not found.")
        return

    agents = await db.get_agents_by_tenant(tenant_id)
    owner = next((a for a in agents if a.get('role') == 'owner'), None)
    if not owner:
        await query.edit_message_text("❌ No owner agent found for this tenant.")
        return

    # Create impersonation token (1 hour, imp:true)
    token = auth_mod.create_impersonation_token(
        tenant_id=tenant_id,
        phone=owner.get('phone', ''),
        firm_name=tenant.get('firm_name', ''),
        role='owner',
        agent_id=owner.get('agent_id')
    )
    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com")
    login_url = f"{server_url}/dashboard?_imp_token={token}&_imp_firm={tenant.get('firm_name', '')}"

    # Audit log
    sa_user = query.from_user
    await db.add_audit_log(tenant_id, None, "sa_impersonate",
                           f"SA ({sa_user.id}) impersonated via Telegram bot")
    logger.warning("👁️ SA IMPERSONATING tenant %d (%s) via Telegram bot — SA TG: %s",
                   tenant_id, tenant.get('firm_name', ''), sa_user.id)

    text = (
        f"🌐 *Web Login — {html_mod.escape(tenant['firm_name'])}*\n\n"
        f"👤 Logging in as: {html_mod.escape(owner.get('name', 'Owner'))}\n"
        f"⏱ Link expires in *1 hour*\n\n"
        f"👇 Click below to open this tenant's dashboard."
    )
    kb = [
        [InlineKeyboardButton("🌐 Open Dashboard", url=login_url)],
        [InlineKeyboardButton("🔙 Tenant", callback_data=f"sa_tenant_{tenant_id}")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(kb))

def build_bot(token: str, tenant_id: int = None, is_master: bool = True) -> Application:
    """Assemble the Telegram bot with all handlers.

    Args:
        token:     Telegram bot token
        tenant_id: If set, this bot is scoped to a specific tenant
        is_master: True for the shared @SarathiBizBot (Sarathi-AI.com), False for tenant bots
    """

    app = Application.builder().token(token).build()

    # Store tenant context so handlers know which bot they're on
    app.bot_data['_tenant_id'] = tenant_id
    app.bot_data['_is_master'] = is_master

    # Shared fallback list for all conversations
    # Menu-button-during-conversation fallback handler
    async def _conv_menu_button_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Catch persistent-menu button taps while inside a conversation."""
        text = (update.message.text or "").strip()
        if _is_menu_button(text):
            lang = context.user_data.get('lang', 'en')
            if lang == 'hi':
                await update.message.reply_text(
                    "\u26a0\ufe0f आप अभी डेटा दर्ज कर रहे हैं।\n"
                    "पहले यह चरण पूरा करें, या नीचे दबाकर रद्द करें:",
                    reply_markup=_conv_recovery_keyboard(lang))
            else:
                await update.message.reply_text(
                    "\u26a0\ufe0f You're in the middle of entering data.\n"
                    "Complete this step first, or tap below to cancel:",
                    reply_markup=_conv_recovery_keyboard(lang))
            return  # Stay in current state
        # Not a menu button — treat as invalid input for this step
        return

    _shared_fallbacks = [
        CommandHandler("cancel", cancel),
        CommandHandler("start", cmd_start),  # Allow /start to reset
        CallbackQueryHandler(_conv_retry_callback, pattern=r"^conv_retry$"),
        CallbackQueryHandler(_conv_cancel_callback, pattern=r"^conv_cancel$"),
        MessageHandler(_btn_filter(*_MENU_LABELS_ALL),
                       _conv_menu_button_fallback),
        MessageHandler(filters.COMMAND, _conv_fallback_command),
        MessageHandler(~filters.TEXT & ~filters.VOICE & ~filters.AUDIO, _conv_fallback_nontext),
    ]

    # --- Conversation: Onboarding (multi-tenant) ---
    onboard_conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            ONBOARD_LANG: [CallbackQueryHandler(onboard_lang,
                           pattern=r"^onboard_lang_")],
            ONBOARD_CHOICE: [CallbackQueryHandler(onboard_choice,
                             pattern=r"^onboard_")],
            ONBOARD_FIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                           onboard_firm)],
            ONBOARD_INVITE: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                             onboard_invite)],
            ONBOARD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                           onboard_name)],
            ONBOARD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                            onboard_phone)],
            ONBOARD_VERIFY_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                  onboard_verify_otp)],
            ONBOARD_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboard_email)],
            ONBOARD_VERIFY_EMAIL_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                        onboard_verify_email_otp)],
            ONBOARD_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                           onboard_city)],
            ONBOARD_BOT_TOKEN: [
                CallbackQueryHandler(onboard_bot_token_choice,
                                     pattern=r"^onboard_bot(token|guide)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               onboard_bot_token_text),
            ],
            ONBOARD_LINK_WEB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               onboard_link_web_phone),
            ],
            ONBOARD_LINK_WEB_OTP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               onboard_link_web_otp),
            ],
            LOGIN_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               login_phone),
            ],
            LOGIN_OTP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               login_verify_otp),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # --- Conversation: Add Lead (with duplicate detection) ---
    addlead_conv = ConversationHandler(
        entry_points=[
            CommandHandler("addlead", cmd_addlead),
            MessageHandler(_btn_filter("➕ Add Lead", "➕ लीड जोड़ें"), cmd_addlead),
        ],
        states={
            LEAD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_name)],
            LEAD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_phone)],
            LEAD_PHONE_CONFIRM: [CallbackQueryHandler(lead_phone_confirm,
                                  pattern=r"^(dup_|leadview_)")],
            LEAD_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_dob)],
            LEAD_ANNIVERSARY: [MessageHandler(filters.TEXT, lead_anniversary)],
            LEAD_CITY: [MessageHandler(filters.TEXT, lead_city)],
            LEAD_NEED: [CallbackQueryHandler(lead_need_callback, pattern=r"^need_")],
            LEAD_EMAIL: [MessageHandler(filters.TEXT, lead_email)],
            LEAD_NOTES: [MessageHandler(filters.TEXT, lead_notes)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # --- Conversation: Follow-up ---
    followup_conv = ConversationHandler(
        entry_points=[
            CommandHandler("followup", cmd_followup),
            MessageHandler(_btn_filter("📞 Follow-up", "📞 फॉलो-अप"), cmd_followup),
            CallbackQueryHandler(followup_select_lead, pattern=r"^fusel_"),
        ],
        states={
            FOLLOWUP_LEAD: [CallbackQueryHandler(followup_select_lead, pattern=r"^fusel_")],
            FOLLOWUP_TYPE: [CallbackQueryHandler(followup_type, pattern=r"^fu_")],
            FOLLOWUP_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, followup_notes)],
            FOLLOWUP_DATE: [MessageHandler(filters.TEXT, followup_date)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # --- Conversation: Convert Lead ---
    convert_conv = ConversationHandler(
        entry_points=[CommandHandler("convert", cmd_convert)],
        states={
            CONVERT_STAGE: [CallbackQueryHandler(convert_stage, pattern=r"^stg_")],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # --- Conversation: Policy ---
    policy_conv = ConversationHandler(
        entry_points=[CommandHandler("policy", cmd_policy)],
        states={
            POLICY_INSURER: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_insurer)],
            POLICY_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_plan)],
            POLICY_TYPE: [CallbackQueryHandler(policy_type_cb, pattern=r"^poltype_")],
            POLICY_SI: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_si)],
            POLICY_PREMIUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_premium)],
            POLICY_MODE: [CallbackQueryHandler(policy_mode_cb, pattern=r"^polmode_")],
            POLICY_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_start)],
            POLICY_RENEWAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_renewal)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # --- Conversation: Edit Profile ---
    editprofile_conv = ConversationHandler(
        entry_points=[CommandHandler("editprofile", cmd_editprofile)],
        states={
            EDITPROFILE_CHOICE: [CallbackQueryHandler(editprofile_choice,
                                  pattern=r"^editprof_")],
            EDITPROFILE_VALUE: [
                MessageHandler(filters.PHOTO, editprofile_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               editprofile_value),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # --- Conversation: Edit Lead ---
    editlead_conv = ConversationHandler(
        entry_points=[CommandHandler("editlead", cmd_editlead)],
        states={
            EDITLEAD_FIELD: [CallbackQueryHandler(editlead_field,
                             pattern=r"^editlead_")],
            EDITLEAD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                             editlead_value)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # --- Conversation: Claims Helper ---
    claim_conv = ConversationHandler(
        entry_points=[CommandHandler("claim", cmd_claim)],
        states={
            CLAIM_LEAD: [CallbackQueryHandler(claim_select_lead, pattern=r"^claimlead_")],
            CLAIM_POLICY: [CallbackQueryHandler(claim_select_policy, pattern=r"^claimpol_")],
            CLAIM_TYPE: [CallbackQueryHandler(claim_select_type, pattern=r"^claimtype_")],
            CLAIM_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, claim_description)],
            CLAIM_HOSPITAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, claim_hospital)],
            CLAIM_CONFIRM: [CallbackQueryHandler(claim_confirm, pattern=r"^claim_")],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # --- Conversation: Interactive Calculator ---
    calc_conv = ConversationHandler(
        entry_points=[
            CommandHandler("calc", cmd_calc),
            MessageHandler(_btn_filter("🧮 Calculator", "🧮 कैलकुलेटर"), cmd_calc),
            CallbackQueryHandler(cmd_calc_inline, pattern=r"^menu_calc$"),
        ],
        states={
            CALC_TYPE: [CallbackQueryHandler(calc_select, pattern=r"^csel_")],
            CALC_INPUT: [
                CallbackQueryHandler(calc_param_button, pattern=r"^cparam_"),
                CallbackQueryHandler(calc_retry, pattern=r"^calc_retry$"),
                CallbackQueryHandler(calc_cancel, pattern=r"^calc_cancel$"),
                CallbackQueryHandler(calc_select, pattern=r"^csel_"),  # Restart from error
                MessageHandler(filters.VOICE | filters.AUDIO, calc_param_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_param_text),
            ],
            CALC_RESULT: [
                CallbackQueryHandler(calc_result_action, pattern=r"^(csel_|wa_share_)"),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )

    # Add conversation handlers first (highest priority)
    app.add_handler(onboard_conv)
    app.add_handler(addlead_conv)
    app.add_handler(followup_conv)
    app.add_handler(convert_conv)
    app.add_handler(policy_conv)
    app.add_handler(editprofile_conv)

    # --- Conversation: Edit Team Agent ---
    editagent_conv = ConversationHandler(
        entry_points=[CommandHandler("editagent", cmd_editagent)],
        states={
            TEAM_EDIT_FIELD: [CallbackQueryHandler(team_edit_select_field,
                               pattern=r"^(teamedit_|teamfield_|teamrole_)")],
            TEAM_EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, team_edit_value),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )
    app.add_handler(editagent_conv)

    # --- Conversation: AI Document Scanner ---
    scan_conv = ConversationHandler(
        entry_points=[
            CommandHandler("scan", cmd_scan),
            CallbackQueryHandler(cmd_scan_inline, pattern=r"^menu_scan$"),
        ],
        states={
            SCAN_WAIT: [
                MessageHandler(filters.PHOTO, _scan_process_photo),
                MessageHandler(filters.Document.ALL, _scan_process_document),
            ],
            SCAN_CONFIRM: [
                CallbackQueryHandler(_scan_confirm_callback, pattern=r"^scan_"),
                MessageHandler(filters.PHOTO, _scan_process_photo),  # Allow re-scan by sending new photo
                MessageHandler(filters.Document.ALL, _scan_process_document),
            ],
            SCAN_CLIENT: [
                CallbackQueryHandler(_scan_client_callback, pattern=r"^scanld_"),
            ],
            SCAN_SOLD_BY: [
                CallbackQueryHandler(_scan_sold_by_callback, pattern=r"^scan_sold_"),
            ],
            SCAN_ASK_MISSING: [
                CallbackQueryHandler(_scan_skip_field, pattern=r"^scan_skip_field$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, _scan_receive_missing),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, _conv_timeout)],
        },
        fallbacks=_shared_fallbacks,
        conversation_timeout=CONV_TIMEOUT,
    )
    app.add_handler(scan_conv)

    app.add_handler(editlead_conv)
    app.add_handler(claim_conv)
    app.add_handler(calc_conv)

    # Simple command handlers
    app.add_handler(CommandHandler("pipeline", cmd_pipeline))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("lead", cmd_lead))
    app.add_handler(CommandHandler("renewals", cmd_renewals))
    app.add_handler(CommandHandler("dashboard", cmd_dashboard))
    app.add_handler(CommandHandler("wa", cmd_wa))
    app.add_handler(CommandHandler("wacalc", cmd_wacalc))
    app.add_handler(CommandHandler("wadash", cmd_wadash))
    app.add_handler(CommandHandler("greet", cmd_greet))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("microsite", cmd_microsite))
    app.add_handler(CommandHandler("compliance", cmd_compliance))
    app.add_handler(CommandHandler("weblogin", cmd_weblogin))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("listenhelp", cmd_listenhelp))
    app.add_handler(CallbackQueryHandler(_audiohelp_callback, pattern=r"^audiohelp_"))
    app.add_handler(CommandHandler("plans", cmd_plans))
    app.add_handler(CommandHandler("claims", cmd_claims))
    app.add_handler(CommandHandler("claimstatus", cmd_claimstatus))
    app.add_handler(CommandHandler("ai", cmd_ai))
    app.add_handler(CommandHandler("team", cmd_team))
    app.add_handler(CommandHandler("createbot", cmd_createbot))
    app.add_handler(CommandHandler("wasetup", cmd_whatsapp_setup))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("refresh", cmd_refresh))
    app.add_handler(CommandHandler("logout", cmd_logout))
    app.add_handler(CommandHandler("leave", cmd_leave))
    app.add_handler(CommandHandler("mytasks", cmd_mytasks))
    app.add_handler(CommandHandler("tasks", cmd_mytasks))

    # ── Super Admin commands (platform owner only) ──
    app.add_handler(CommandHandler("sa", cmd_sa))
    app.add_handler(CommandHandler("sa_create", cmd_sa_create))
    app.add_handler(CommandHandler("sa_edit", cmd_sa_edit))
    app.add_handler(CommandHandler("sa_logout", cmd_sa_logout))
    app.add_handler(CallbackQueryHandler(_sa_callback, pattern=r"^sa_"))

    # Voice-to-Action handler (process voice notes → auto-create leads)
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, _voice_to_action))

    # Voice-to-Action inline callbacks (confirm/discard/fill + stage picker)
    app.add_handler(CallbackQueryHandler(_voice_callback, pattern=r"^voice_"))
    app.add_handler(CallbackQueryHandler(_voice_callback, pattern=r"^vstg_"))

    # Voice Calculator callbacks (vcalc_, vcparam_)
    app.add_handler(CallbackQueryHandler(_vcalc_callback, pattern=r"^vcalc_"))
    app.add_handler(CallbackQueryHandler(_vcalc_callback, pattern=r"^vcparam_"))
    app.add_handler(CallbackQueryHandler(_voice_cancel_callback, pattern=r"^voice_cancel$"))
    app.add_handler(CallbackQueryHandler(_vc_choice_callback, pattern=r"^vc_(go_|dismiss)"))

    # Voice fill-in text handler (collects missing fields after voice note)
    # Must be before global catch-all so it intercepts text during fill flow
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, _voice_fill_text), group=2)

    # AI Tools inline callbacks
    app.add_handler(CallbackQueryHandler(_ai_callback, pattern=r"^ai"))

    # Team management inline callbacks
    app.add_handler(CallbackQueryHandler(_team_callback, pattern=r"^team"))

    # Payment/subscription inline callbacks
    app.add_handler(CallbackQueryHandler(_payment_callback, pattern=r"^(pay_|cancel_sub$)"))

    # CSV file import handler
    app.add_handler(MessageHandler(filters.Document.ALL, _csv_import_handler))

    # Callback router for inline buttons
    app.add_handler(CallbackQueryHandler(_menu_inline_callback, pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(_nudge_callback, pattern=r"^nudge_"))
    app.add_handler(CallbackQueryHandler(_followup_action_callback, pattern=r"^fu(done|snz)_"))
    app.add_handler(CallbackQueryHandler(_mytasks_callback, pattern=r"^mytasks_(today|tomorrow|yesterday|overdue|week|done)$"))
    app.add_handler(CallbackQueryHandler(_mytasks_back_callback, pattern=r"^mytasks_back$"))
    app.add_handler(CallbackQueryHandler(_taskdone_callback, pattern=r"^taskdone_"))
    app.add_handler(CallbackQueryHandler(_proactive_callback, pattern=r"^pa_"))
    app.add_handler(CallbackQueryHandler(callback_router))

    # WhatsApp share phone number handler (catches phone input during share flow)
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^\+?\d[\d\s\-]{8,13}$"),
        wa_share_phone_handler), group=1)

    # Persistent button menu handler (catches button taps as text messages)
    # Uses a custom filter that strips Unicode variation selectors (U+FE0E/FE0F)
    # before matching, because Telegram may inject them into emoji text.
    _menu_labels = {
        "➕ Add Lead", "➕ लीड जोड़ें",
        "📊 Pipeline", "📊 पाइपलाइन",
        "📋 Leads", "📋 लीड्स",
        "📋 My Leads", "📋 मेरी लीड्स",
        "☰ Menu", "☰ मेनू",
        "📞 Follow-up", "📞 फॉलो-अप",
        "🧮 Calculator", "🧮 कैलकुलेटर",
        "🔄 Renewals", "🔄 रिन्यूअल",
        "🤖 AI Tools", "🤖 AI टूल्स",
        "📈 Dashboard", "📈 डैशबोर्ड",
        "⚙️ Settings", "⚙️ सेटिंग्स",
        "👥 Team", "👥 टीम",
        "🌐 Language", "🌐 भाषा बदलें",
        "🤝 Partner & Earn", "🤝 पार्टनर और कमाएं",
    }
    _strip_vs = str.maketrans("", "", "\ufe0e\ufe0f")
    _norm_labels = {lbl.translate(_strip_vs) for lbl in _menu_labels}

    class _MenuButtonFilter(filters.MessageFilter):
        """Match incoming text against menu labels after stripping variation selectors."""
        def filter(self, message):
            if not message.text:
                return False
            return message.text.strip().translate(_strip_vs) in _norm_labels

    app.add_handler(MessageHandler(
        filters.TEXT & _MenuButtonFilter(),
        button_menu_handler), group=-1)

    # Global catch-all: respond to unrecognized messages instead of ignoring them
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _global_catch_all))

    # Global error handler — catches unhandled exceptions in all handlers
    app.add_error_handler(_error_handler)

    # Register Telegram's /commands menu (visible in Telegram command picker)
    async def _post_init(application: Application):
        """Set bot commands visible in Telegram's menu button."""
        _is_master_bot = application.bot_data.get('_is_master', True)
        if _is_master_bot:
            # Master/registration bot — show registration + SA-relevant commands
            commands = [
                ("start", "Start / Register your firm"),
                ("createbot", "Connect your Telegram bot"),
                ("sa", "🛡️ Super Admin panel"),
                ("weblogin", "🌐 Login to web dashboard"),
                ("refresh", "🔄 Refresh bot menu"),
                ("lang", "🌐 Change language / भाषा बदलें"),
                ("help", "Help & support"),
            ]
        else:
            # Tenant CRM bot — show full feature commands
            commands = [
                ("start", "Start / Main Menu"),
                ("addlead", "Add a new lead"),
                ("pipeline", "View lead pipeline"),
                ("leads", "List all leads"),
                ("followup", "Follow-up reminders"),
                ("calc", "Financial calculators"),
                ("renewals", "Policy renewals"),
                ("dashboard", "Business dashboard"),
                ("ai", "AI sales tools"),
                ("weblogin", "🌐 Login to web dashboard"),
                ("settings", "Bot settings"),
                ("logout", "🔓 Logout / Switch account"),
                ("lang", "🌐 Change language / भाषा बदलें"),
                ("help", "Help & commands list"),
            ]
        try:
            from telegram import BotCommand
            await application.bot.set_my_commands(
                [BotCommand(cmd, desc) for cmd, desc in commands])
            logger.info("Bot commands menu registered (%d commands, master=%s)",
                        len(commands), _is_master_bot)
        except Exception as e:
            logger.warning("Failed to set bot commands: %s", e)

    app.post_init = _post_init

    logger.info("Bot built: %s (tenant=%s, master=%s)",
                "master" if is_master else f"tenant-{tenant_id}",
                tenant_id, is_master)
    return app


# =============================================================================
#  ERROR HANDLER
# =============================================================================

async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler — logs the error, saves state for recovery, notifies user."""
    logger.error("Unhandled exception: %s", context.error, exc_info=context.error)

    # Save conversation state for recovery on network errors
    is_network_error = isinstance(context.error, (
        ConnectionError, TimeoutError, OSError,
    )) or "network" in str(context.error).lower()

    if is_network_error and update and hasattr(update, 'effective_user') and update.effective_user:
        user_id = str(update.effective_user.id)
        try:
            await resilience.save_user_state(
                user_id, "error_recovery",
                {"error": str(context.error)[:200], "timestamp": datetime.now().isoformat()})
        except Exception:
            pass

    # Try to send a message to the user
    try:
        if update and hasattr(update, 'effective_user') and update.effective_user:
            effective_msg = getattr(update, 'effective_message', None)
            error_text = (
                "⚠️ Connection issue. Your progress is saved — just try again."
                if is_network_error else
                "⚠️ Something went wrong. Please try again.\n"
                "If this keeps happening, type /cancel and retry."
            )
            if effective_msg:
                await resilience.safe_reply(effective_msg, error_text)
            elif hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.answer(
                    "⚠️ Something went wrong. Try again.", show_alert=True)
    except Exception:
        pass  # Don't let error handler errors propagate


# =============================================================================
#  HELPERS
# =============================================================================

def h(text) -> str:
    """Escape text for Telegram HTML mode. Safe for all user content."""
    if text is None:
        return "N/A"
    return html_mod.escape(str(text))


def _needs_keyboard(selected: list) -> list:
    """Build the multi-select needs keyboard with checkmarks."""
    options = [
        ("🏥 Health", "health"),
        ("🛡️ Term Life", "term"),
        ("📜 Endowment", "endowment"),
        ("📊 ULIP", "ulip"),
        ("🎓 Child Plan", "child"),
        ("🏖️ Retirement", "retirement"),
        ("🚗 Motor", "motor"),
        ("💰 Investment / MF", "investment"),
        ("🏛️ NPS", "nps"),
        ("📋 General", "general"),
    ]
    kb = []
    for label, key in options:
        check = "✅ " if key in selected else ""
        kb.append([InlineKeyboardButton(
            f"{check}{label}", callback_data=f"need_{key}")])
    # Done button at the bottom
    done_label = f"✅ Done ({len(selected)} selected)" if selected else "⬜ Select at least one"
    kb.append([InlineKeyboardButton(done_label, callback_data="need_done")])
    return kb


async def _get_agent(update: Update) -> Optional[dict]:
    """Get agent from update, or prompt registration."""
    user_id = str(update.effective_user.id)
    agent = await db.get_agent(user_id)
    if not agent:
        await update.message.reply_text(
            i18n.t('en', "not_registered"),  # no context available here, default to English
            parse_mode=ParseMode.HTML)
    return agent


async def _require_agent_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[dict]:
    """Full auth check (mirrors @registered) for handlers that can't use the decorator.
    Returns enriched agent dict if authorized, None otherwise.
    Works with both message and callback_query updates."""
    is_callback = update.callback_query is not None
    user_id = str(update.effective_user.id)

    async def _reply(text):
        if is_callback:
            try:
                await update.callback_query.edit_message_text(text)
            except Exception:
                pass
        elif update.message:
            await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())

    # Rate limit
    if _rate_limited(user_id):
        await _reply("⏳ Too many requests. Please wait a moment and try again.")
        return None

    agent = await db.get_agent(user_id)
    if not agent:
        await _reply("⚠️ You're not registered yet. Use /start to set up your profile.")
        return None

    # is_active check
    if not agent.get('is_active', 1):
        await _reply("⚠️ Your account has been deactivated. Contact your firm owner to reactivate.")
        return None

    # Subscription check
    if agent.get('tenant_id'):
        active = await db.check_subscription_active(agent['tenant_id'])
        if not active:
            await _reply("⚠️ Your subscription has expired. Please renew at sarathi-ai.com to continue.")
            return None

    # Tenant isolation: if per-tenant bot, verify agent belongs to this tenant
    bot_tenant_id = context.bot_data.get('_tenant_id')
    if bot_tenant_id and agent.get('tenant_id') != bot_tenant_id:
        await _reply("⚠️ You're not registered with this firm's bot.")
        return None

    # Inject plan for downstream feature gates
    if agent.get('tenant_id'):
        _t = await db.get_tenant(agent['tenant_id'])
        agent['_plan'] = _t.get('plan', 'trial') if _t else 'trial'
    else:
        agent['_plan'] = 'trial'

    # Track agent activity
    try:
        if agent.get('agent_id'):
            asyncio.get_event_loop().create_task(
                db.touch_agent_activity(agent['agent_id']))
    except Exception:
        pass

    return agent


def _parse_date(text: str) -> datetime:
    """Parse date from DD-MM-YYYY or DD/MM/YYYY format."""
    text = text.strip().replace('/', '-')
    for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {text}")


def _stage_emoji(stage: str) -> str:
    """Get emoji for pipeline stage."""
    emojis = {
        'prospect': '🎯', 'contacted': '📞', 'pitched': '📊',
        'proposal_sent': '📄', 'negotiation': '🤝',
        'closed_won': '✅', 'closed_lost': '❌',
    }
    return emojis.get(stage, '⚪')


def _conversion_rate(won: int, total: int) -> str:
    """Calculate conversion rate string."""
    if total == 0:
        return "N/A"
    rate = (won / total) * 100
    return f"{rate:.0f}%"

