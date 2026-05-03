# =============================================================================
#  biz_ai.py — Sarathi-AI Business Technologies: AI Sales Intelligence Module
# =============================================================================
#
#  8 Gemini AI-powered features for insurance sales agents:
#    1. Lead Scoring          — AI ranks leads by conversion probability
#    2. Pitch Generator       — Custom sales pitches per lead profile
#    3. Smart Follow-up       — AI suggests next best action
#    4. Policy Recommender    — Recommend policies based on client profile
#    5. Communication Templates — Professional messages for every occasion
#    6. Voice Meeting Summary — (already in biz_bot.py as Voice-to-Action)
#    7. Objection Handling    — Counter common insurance objections
#    8. Renewal Intelligence  — Smart renewal strategy & upsell suggestions
#
# =============================================================================

import json
import logging
import os
from datetime import datetime, date
from typing import Optional

from google import genai
from google.genai import types as genai_types

logger = logging.getLogger("sarathi.ai")

# ── Gemini model & client ─────────────────────────────────────────────────────
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_client = None


def _get_client():
    """Lazy-init Gemini client (shared with biz_bot.py pattern)."""
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if key:
            _client = genai.Client(api_key=key)
            logger.info("AI module: Gemini client initialized")
    return _client


async def _ask_gemini(prompt: str, json_mode: bool = False) -> str:
    """Send a text prompt to Gemini and return the response text."""
    client = _get_client()
    if not client:
        raise RuntimeError("Gemini API key not configured")

    config = None
    if json_mode:
        config = genai_types.GenerateContentConfig(
            response_mime_type="application/json"
        )

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text.strip()


def _clean_json(text: str) -> dict:
    """Strip markdown code fences and parse JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return json.loads(t.strip())


_LANG_NAMES = {"en": "English", "hi": "Hindi (हिन्दी)"}

def _lang_instruction(lang: str) -> str:
    """Return a prompt suffix instructing Gemini to respond in the user's language."""
    if lang and lang != "en":
        name = _LANG_NAMES.get(lang, lang)
        return (f"\n\nIMPORTANT: Respond ENTIRELY in {name}. "
                f"All text values in the JSON must be in {name}. "
                f"Keep JSON keys in English but all human-readable string values must be in {name}.")
    return ""


# =============================================================================
#  1. LEAD SCORING — AI ranks lead by conversion probability
# =============================================================================

async def score_lead(lead: dict, interactions: list = None,
                     policies: list = None, lang: str = "en") -> dict:
    """Score a lead 1-100 based on profile, engagement, and history.

    Returns:
        {
            "score": 85,
            "grade": "A",          # A/B/C/D
            "reasons": [...],      # why this score
            "next_action": "...",  # recommended next step
            "priority": "high"     # high/medium/low
        }
    """
    interaction_summary = "None"
    if interactions:
        interaction_summary = "\n".join(
            f"- {ix.get('type', 'N/A')} on {ix.get('created_at', 'N/A')[:10]}: "
            f"{(ix.get('summary') or 'no notes')[:80]}"
            for ix in interactions[:10]
        )

    policy_summary = "None"
    if policies:
        policy_summary = "\n".join(
            f"- {p.get('insurer', 'N/A')} {p.get('plan_name', 'N/A')}: "
            f"₹{p.get('premium', 0):,.0f}/yr, status={p.get('status', 'N/A')}"
            for p in policies
        )

    today = datetime.now().strftime('%Y-%m-%d')
    prompt = f"""You are an expert Indian insurance sales AI. Score this lead for conversion probability.

LEAD PROFILE:
- Name: {lead.get('name', 'N/A')}
- Phone: {'Yes' if lead.get('phone') else 'No'}
- City: {lead.get('city', 'N/A')}
- Need: {lead.get('need_type', 'N/A')}
- Stage: {lead.get('stage', 'prospect')}
- Budget: ₹{lead.get('premium_budget', 'N/A')}/month
- Sum Insured: ₹{lead.get('sum_insured', 'N/A')}
- Notes: {(lead.get('notes') or 'None')[:200]}
- Added: {lead.get('created_at', 'N/A')}
- DOB: {lead.get('dob', 'N/A')}
- Occupation: {lead.get('occupation', 'N/A')}
- Family Size: {lead.get('family_size', 'N/A')}

INTERACTION HISTORY:
{interaction_summary}

EXISTING POLICIES:
{policy_summary}

TODAY: {today}

Return ONLY valid JSON:
{{
    "score": <1-100>,
    "grade": "<A/B/C/D>",
    "reasons": ["reason1", "reason2", "reason3"],
    "next_action": "<specific recommended next step>",
    "priority": "<high/medium/low>",
    "estimated_premium_potential": "<₹X,XXX/month estimate>"
}}

SCORING RULES:
- 80-100 (A): Hot lead — has budget, need, recent engagement, clear intent
- 60-79 (B): Warm lead — interested but needs nurturing
- 40-59 (C): Cool lead — has potential but low engagement
- 0-39 (D): Cold — no engagement, unclear need, or stale >30 days
- Factor in: stage progression, interaction recency, completeness of profile
- Indian insurance context: health for families, term for breadwinners, child plans for parents"""
    prompt += _lang_instruction(lang)

    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("Lead scoring error: %s", e)
        return {"score": 50, "grade": "C", "reasons": ["AI scoring unavailable"],
                "next_action": "Follow up manually", "priority": "medium"}


# =============================================================================
#  2. PITCH GENERATOR — Custom sales pitch per lead profile
# =============================================================================

async def generate_pitch(lead: dict, agent_name: str,
                         firm_name: str = "your advisor",
                         pitch_type: str = "general", lang: str = "en") -> dict:
    """Generate a personalized sales pitch for a lead.

    pitch_type: general, health, term, investment, retirement, child, renewal

    Returns:
        {
            "opening": "...",       # ice-breaker line
            "pitch": "...",         # main sales pitch (3-5 paragraphs)
            "key_points": [...],    # bullet points to cover
            "closing": "...",       # strong call-to-action
            "whatsapp_message": "..." # ready-to-send WhatsApp message
        }
    """
    first_name = (lead.get('name') or 'Sir/Ma\'am').split()[0]
    need = lead.get('need_type', pitch_type)
    if need in ('N/A', None, ''):
        need = pitch_type

    prompt = f"""You are an expert Indian insurance sales advisor. Generate a compelling, personalized sales pitch.

CLIENT PROFILE:
- Name: {lead.get('name', 'Sir/Ma\'am')} (call them "{first_name}" ji)
- City: {lead.get('city', 'N/A')}
- Need: {need}
- Age: {_calc_age(lead.get('dob'))}
- Occupation: {lead.get('occupation', 'N/A')}
- Family: {lead.get('family_size', 'N/A')}
- Budget: ₹{lead.get('premium_budget', 'N/A')}/month
- Stage: {lead.get('stage', 'prospect')}
- Notes: {(lead.get('notes') or 'None')[:200]}

AGENT: {agent_name} from {firm_name}

PITCH TYPE: {pitch_type}

Return ONLY valid JSON:
{{
    "opening": "<warm ice-breaker referencing their life situation>",
    "pitch": "<3-5 paragraph persuasive pitch in Indian English, use real insurance product examples>",
    "key_points": ["point1", "point2", "point3", "point4"],
    "closing": "<strong call-to-action with urgency>",
    "whatsapp_message": "<ready-to-send WhatsApp message, 150-200 words, professional yet warm, with emojis>"
}}

RULES:
- Use Indian context: mention relevant Indian insurance companies (LIC, HDFC Life, ICICI Pru, Star Health, etc.)
- Reference real product types relevant to their need
- Include specific numbers/statistics about insurance gaps in India
- Be warm, professional, use Hindi terms naturally (ji, namaste)
- WhatsApp message should be self-contained and ready to copy-paste"""
    prompt += _lang_instruction(lang)

    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("Pitch generation error: %s", e)
        return {
            "opening": f"Namaste {first_name} ji!",
            "pitch": "I'd love to discuss how we can protect your family's financial future.",
            "key_points": ["Financial protection", "Tax benefits", "Wealth creation"],
            "closing": "Let's schedule a quick 15-minute call this week?",
            "whatsapp_message": f"Namaste {first_name} ji! 🙏\n\nI hope you're doing well. I wanted to share some important insights about securing your family's financial future.\n\nWould you be available for a quick 15-minute call this week?\n\nBest regards,\n{agent_name}"
        }


# =============================================================================
#  3. SMART FOLLOW-UP SUGGESTIONS — AI suggests next best action
# =============================================================================

async def suggest_followup(lead: dict, interactions: list = None,
                           policies: list = None, lang: str = "en") -> dict:
    """AI suggests the best follow-up action and timing.

    Returns:
        {
            "action": "...",           # specific follow-up action
            "timing": "...",           # when (today, tomorrow, this week)
            "channel": "...",          # whatsapp, call, meeting, email
            "message_draft": "...",    # ready-to-use message
            "urgency": "high/medium/low",
            "reasoning": "..."         # why this action
        }
    """
    interaction_lines = "None logged"
    if interactions:
        interaction_lines = "\n".join(
            f"- [{ix.get('created_at', '')[:10]}] {ix.get('type', 'N/A')} "
            f"via {ix.get('channel', 'N/A')}: {(ix.get('summary') or '')[:80]}"
            for ix in interactions[:10]
        )

    prompt = f"""You are a smart Indian financial advisor CRM AI. Suggest the best follow-up action for this lead.

LEAD:
- Name: {lead.get('name', 'N/A')}
- Stage: {lead.get('stage', 'prospect')}
- Need: {lead.get('need_type', 'N/A')}
- City: {lead.get('city', 'N/A')}
- Added: {lead.get('created_at', 'N/A')}
- Last Update: {lead.get('updated_at', 'N/A')}
- Notes: {(lead.get('notes') or 'None')[:200]}

INTERACTION HISTORY:
{interaction_lines}

TODAY: {datetime.now().strftime('%Y-%m-%d (%A)')}

Return ONLY valid JSON:
{{
    "action": "<specific action to take — be very concrete>",
    "timing": "<when to do it: today/tomorrow/in 2 days/this Friday/etc.>",
    "channel": "<whatsapp/phone_call/in_person/email>",
    "message_draft": "<ready-to-send message if channel is whatsapp/email>",
    "urgency": "<high/medium/low>",
    "reasoning": "<why this is the best next step>",
    "tips": ["<tip1>", "<tip2>"]
}}

RULES:
- Consider days since last contact (>7 days = re-engage priority)
- Match channel to stage: WhatsApp for warm leads, phone for hot, meeting for closing
- For Indian insurance: festivals, tax-saving season (Jan-Mar), policy anniversaries matter
- Be specific: "Call tomorrow at 11 AM to discuss term plan options" not "Follow up soon"
- Draft message should be in natural Indian English with appropriate warmth"""

    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("Follow-up suggestion error: %s", e)
        return {
            "action": "Send a friendly WhatsApp check-in message",
            "timing": "Today",
            "channel": "whatsapp",
            "message_draft": f"Hi {(lead.get('name') or 'there').split()[0]} ji, hope you're doing well! Just checking in. Let me know if you'd like to discuss any insurance needs. 🙏",
            "urgency": "medium",
            "reasoning": "Regular follow-up to stay top of mind",
            "tips": ["Be warm and non-pushy", "Reference previous conversation if any"]
        }


# =============================================================================
#  4. POLICY RECOMMENDER — AI recommends insurance products
# =============================================================================

async def recommend_policies(lead: dict, existing_policies: list = None, lang: str = "en") -> dict:
    """Recommend insurance policies based on client profile and gaps.

    Returns:
        {
            "recommendations": [
                {
                    "type": "term_life",
                    "reason": "...",
                    "suggested_cover": "₹1 Cr",
                    "estimated_premium": "₹8,000-12,000/yr",
                    "top_products": ["LIC Tech Term", "HDFC Click2Protect"],
                    "priority": "high"
                }, ...
            ],
            "gap_analysis": "...",
            "total_protection_needed": "...",
            "cross_sell_opportunities": [...]
        }
    """
    existing = "None"
    if existing_policies:
        existing = "\n".join(
            f"- {p.get('policy_type', 'N/A')}: {p.get('insurer', 'N/A')} "
            f"{p.get('plan_name', 'N/A')}, SI=₹{p.get('sum_insured', 0):,.0f}, "
            f"Premium=₹{p.get('premium', 0):,.0f}/{p.get('premium_mode', 'annual')}"
            for p in existing_policies
        )

    prompt = f"""You are an expert Indian insurance advisor AI. Recommend insurance products for this client.

CLIENT PROFILE:
- Name: {lead.get('name', 'N/A')}
- Age: {_calc_age(lead.get('dob'))}
- City: {lead.get('city', 'N/A')}
- Occupation: {lead.get('occupation', 'N/A')}
- Monthly Income: ₹{lead.get('monthly_income', 'N/A')}
- Family: {lead.get('family_size', 'N/A')}
- Stated Need: {lead.get('need_type', 'N/A')}
- Budget: ₹{lead.get('premium_budget', 'N/A')}/month
- Sum Insured Interest: ₹{lead.get('sum_insured', 'N/A')}

EXISTING POLICIES:
{existing}

Return ONLY valid JSON:
{{
    "recommendations": [
        {{
            "type": "<health/term_life/investment/retirement/child_plan/motor/critical_illness>",
            "reason": "<why this client needs this>",
            "suggested_cover": "<₹X Lakh/Cr>",
            "estimated_premium": "<₹X,XXX-Y,YYY/yr>",
            "top_products": ["Product1 by Company", "Product2 by Company"],
            "priority": "<must_have/recommended/nice_to_have>"
        }}
    ],
    "gap_analysis": "<summary of insurance gaps>",
    "total_protection_needed": "<total cover calculation>",
    "cross_sell_opportunities": ["opportunity1", "opportunity2"]
}}

RULES:
- Use REAL Indian insurance products: LIC, HDFC Life, ICICI Prudential, Star Health, Max Life, SBI Life, etc.
- Apply thumb rules: Term cover = 10-15x annual income, Health cover = ₹10-25 lakh for family
- Don't recommend what they already have (check existing policies)
- Prioritize: Term > Health > others for breadwinners
- For families with kids: add child education plans
- Give realistic premium estimates for 2024 Indian market"""
    prompt += _lang_instruction(lang)

    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("Policy recommendation error: %s", e)
        return {
            "recommendations": [
                {"type": "health", "reason": "Every family needs health coverage",
                 "suggested_cover": "₹10 Lakh", "estimated_premium": "₹15,000-25,000/yr",
                 "top_products": ["Star Health Family Floater", "HDFC ERGO Optima Secure"],
                 "priority": "must_have"}
            ],
            "gap_analysis": "Unable to perform detailed analysis. Basic health cover recommended.",
            "total_protection_needed": "Consult for detailed calculation",
            "cross_sell_opportunities": ["Term life insurance", "Investment plans"]
        }


# =============================================================================
#  5. COMMUNICATION TEMPLATES — Professional messages for every occasion
# =============================================================================

async def generate_template(template_type: str, lead: dict = None,
                            agent_name: str = "", firm_name: str = "",
                            custom_context: str = "", lang: str = "en") -> dict:
    """Generate professional communication templates.

    template_types:
        introduction, follow_up, proposal, thank_you, referral_ask,
        birthday, anniversary, festival, policy_renewal, claim_update,
        premium_reminder, cross_sell, reactivation, testimonial_request

    Returns:
        {
            "whatsapp": "...",   # WhatsApp-ready message
            "email_subject": "...",
            "email_body": "...",
            "sms": "...",        # short SMS version
            "tips": [...]
        }
    """
    client_name = (lead.get('name', 'valued client') if lead else 'valued client')
    first_name = client_name.split()[0] if client_name else 'Sir/Ma\'am'

    prompt = f"""You are a professional Indian insurance communication specialist. Generate templates for the following scenario.

TEMPLATE TYPE: {template_type}
CLIENT: {client_name} ({first_name} ji)
AGENT: {agent_name}
FIRM: {firm_name}
ADDITIONAL CONTEXT: {custom_context or 'None'}

LEAD DETAILS (if available):
- Need: {lead.get('need_type', 'N/A') if lead else 'N/A'}
- Stage: {lead.get('stage', 'N/A') if lead else 'N/A'}
- City: {lead.get('city', 'N/A') if lead else 'N/A'}

Return ONLY valid JSON:
{{
    "whatsapp": "<WhatsApp message with emojis, 100-200 words, warm professional Indian tone>",
    "email_subject": "<professional email subject line>",
    "email_body": "<email body, 200-300 words, formal yet warm>",
    "sms": "<SMS version, under 160 characters>",
    "tips": ["<delivery tip1>", "<delivery tip2>"]
}}

RULES:
- Use natural Indian English with Hindi greetings (Namaste, ji)
- WhatsApp: Use emojis appropriately, keep it conversational
- Email: More formal but still warm, include proper salutation and sign-off
- SMS: Very concise, include callback number reference
- For festivals: reference specific Indian festivals (Diwali, Holi, Eid, Pongal, etc.)
- For renewals: create urgency without being pushy
- Brand every message with agent name and firm"""
    prompt += _lang_instruction(lang)

    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("Template generation error: %s", e)
        return {
            "whatsapp": f"Namaste {first_name} ji! 🙏\n\nI hope you're doing well.\n\nBest regards,\n{agent_name}\n{firm_name}",
            "email_subject": f"Hello from {agent_name} - {firm_name}",
            "email_body": f"Dear {first_name} ji,\n\nI hope this message finds you well.\n\nWarm regards,\n{agent_name}\n{firm_name}",
            "sms": f"Hi {first_name} ji, {agent_name} here from {firm_name}. Would love to connect!",
            "tips": ["Send during business hours", "Follow up within 48 hours"]
        }


# =============================================================================
#  6. VOICE MEETING SUMMARY — Already implemented in biz_bot.py
# =============================================================================
# (Voice-to-Action in biz_bot.py handles voice notes via Gemini)


# =============================================================================
#  7. OBJECTION HANDLING — Counter common insurance objections
# =============================================================================

async def handle_objection(objection: str, lead: dict = None,
                           product_type: str = "general", lang: str = "en") -> dict:
    """AI-powered objection handling for insurance sales.

    Returns:
        {
            "category": "price/trust/timing/need/competitor",
            "empathy_statement": "...",
            "counter_arguments": [...],
            "reframe": "...",
            "closing_question": "...",
            "real_world_example": "...",
            "supporting_data": "..."
        }
    """
    client_info = ""
    if lead:
        client_info = f"""
CLIENT CONTEXT:
- Name: {lead.get('name', 'N/A')}
- Need: {lead.get('need_type', 'N/A')}
- City: {lead.get('city', 'N/A')}
- Budget: ₹{lead.get('premium_budget', 'N/A')}/month
- Stage: {lead.get('stage', 'N/A')}"""

    prompt = f"""You are an expert Indian insurance sales coach. Help counter this objection.

OBJECTION FROM CLIENT: "{objection}"
PRODUCT BEING DISCUSSED: {product_type}
{client_info}

Return ONLY valid JSON:
{{
    "category": "<price/trust/timing/need/competitor/family_decision>",
    "empathy_statement": "<acknowledge their concern warmly>",
    "counter_arguments": [
        "<argument 1 with specific data/example>",
        "<argument 2 with emotional appeal>",
        "<argument 3 with logical reasoning>"
    ],
    "reframe": "<reframe the objection into an opportunity>",
    "closing_question": "<a question that moves towards commitment>",
    "real_world_example": "<a relatable Indian scenario showing why insurance matters>",
    "supporting_data": "<specific Indian insurance statistic or fact>"
}}

RULES:
- Use REAL Indian insurance data and statistics
- Reference actual scenarios (medical inflation 14%/yr, avg hospital bill ₹5L+)
- Be empathetic first, then logical
- Use Indian cultural context (family protection, elder care, children's future)
- For "too expensive": compare with daily coffee/eating out costs
- For "I'm young/healthy": cite accident stats, early premium advantage
- For timing: reference tax-saving deadline (Section 80C/80D)
- Never be aggressive — gentle persistence with warmth"""
    prompt += _lang_instruction(lang)

    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("Objection handling error: %s", e)
        return {
            "category": "general",
            "empathy_statement": "I completely understand your concern.",
            "counter_arguments": [
                "Insurance premiums increase significantly with age",
                "Medical inflation in India is 14% per year",
                "67% of Indians are underinsured"
            ],
            "reframe": "Think of it as an investment in your family's peace of mind.",
            "closing_question": "Would a smaller cover to start with work better for your budget?",
            "real_world_example": "Many families face financial crisis from a single hospital visit.",
            "supporting_data": "Average Indian hospital bill exceeds ₹5 lakh for major procedures."
        }


# =============================================================================
#  8. RENEWAL INTELLIGENCE — Smart renewal strategy & upsell
# =============================================================================

async def renewal_intelligence(policy: dict, lead: dict,
                               all_policies: list = None, lang: str = "en") -> dict:
    """AI-powered renewal strategy with upsell opportunities.

    Returns:
        {
            "renewal_strategy": "...",
            "upsell_opportunity": "...",
            "talking_points": [...],
            "competitor_comparison": "...",
            "retention_risk": "low/medium/high",
            "message_draft": "...",
            "premium_change_estimate": "..."
        }
    """
    other_policies = ""
    if all_policies:
        other_policies = "\n".join(
            f"- {p.get('policy_type', 'N/A')}: {p.get('insurer', 'N/A')}, "
            f"₹{p.get('premium', 0):,.0f}/yr"
            for p in all_policies if p.get('policy_id') != policy.get('policy_id')
        ) or "None"

    prompt = f"""You are an expert Indian insurance renewal strategist. Provide renewal intelligence.

POLICY UP FOR RENEWAL:
- Type: {policy.get('policy_type', 'N/A')}
- Insurer: {policy.get('insurer', 'N/A')}
- Plan: {policy.get('plan_name', 'N/A')}
- Sum Insured: ₹{policy.get('sum_insured', 0):,.0f}
- Premium: ₹{policy.get('premium', 0):,.0f}/{policy.get('premium_mode', 'annual')}
- Renewal Date: {policy.get('renewal_date', 'N/A')}
- Status: {policy.get('status', 'N/A')}

CLIENT:
- Name: {lead.get('name', 'N/A')}
- Age: {_calc_age(lead.get('dob'))}
- City: {lead.get('city', 'N/A')}
- Occupation: {lead.get('occupation', 'N/A')}
- Family: {lead.get('family_size', 'N/A')}

OTHER POLICIES OF THIS CLIENT:
{other_policies}

Return ONLY valid JSON:
{{
    "renewal_strategy": "<step-by-step renewal approach>",
    "upsell_opportunity": "<specific upsell recommendation with rationale>",
    "talking_points": ["<point1>", "<point2>", "<point3>"],
    "competitor_comparison": "<why staying with current insurer is better + if not, alternatives>",
    "retention_risk": "<low/medium/high>",
    "retention_risk_reasons": ["<reason1>", "<reason2>"],
    "message_draft": "<WhatsApp message for renewal conversation, warm and professional>",
    "premium_change_estimate": "<expected premium change at renewal>",
    "coverage_gap": "<any gap in current coverage that can be addressed at renewal>"
}}

RULES:
- Use current Indian insurance market knowledge
- Consider medical inflation for health policies (14% annually)
- For term plans: age-based premium increase
- Suggest rider additions where appropriate (critical illness, accident)
- Reference NCB (No Claim Bonus) for health policies
- For high retention risk: suggest proactive contact 30 days before renewal
- Be specific about upsell: "increase health cover from ₹5L to ₹10L" not vague"""
    prompt += _lang_instruction(lang)

    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("Renewal intelligence error: %s", e)
        return {
            "renewal_strategy": "Contact client 30 days before renewal via WhatsApp, follow up with a call.",
            "upsell_opportunity": "Consider increasing coverage based on inflation.",
            "talking_points": ["No Claim Bonus benefit", "Inflation-adjusted coverage", "New rider options"],
            "competitor_comparison": "Current insurer offers loyalty benefits at renewal.",
            "retention_risk": "medium",
            "retention_risk_reasons": ["Annual premium increase", "Competitive market"],
            "message_draft": f"Hi {(lead.get('name') or 'there').split()[0]} ji, your policy renewal is coming up. Let's review your coverage together! 🙏",
            "premium_change_estimate": "5-10% increase expected",
            "coverage_gap": "Review if current coverage matches your lifestyle changes."
        }


# =============================================================================
#  BONUS: Quick AI Chat — Ask any insurance question
# =============================================================================

async def ask_insurance_ai(question: str, agent_context: str = "", lang: str = "en") -> str:
    """General insurance AI assistant for agents. Returns text answer."""
    prompt = f"""You are Sarathi-AI, an expert AI assistant for Indian insurance advisors.

AGENT'S QUESTION: {question}

CONTEXT: {agent_context or 'General insurance query'}

RULES:
- Answer in clear, concise Indian English
- Reference Indian insurance regulations (IRDAI), companies, products where relevant
- If it's a calculation question, show the math
- Keep response under 300 words
- Be practical and actionable
- If you don't know something specific, say so rather than guessing

Respond directly (no JSON needed)."""
    prompt += _lang_instruction(lang)

    try:
        return await _ask_gemini(prompt)
    except Exception as e:
        logger.error("AI chat error: %s", e)
        return "❌ AI service temporarily unavailable. Please try again."


# =============================================================================
#  HELPER: Calculate age from DOB string
# =============================================================================


# =============================================================================
#  11. AI ANOMALY CLASSIFICATION — Smart system event analysis for Super Admin
# =============================================================================

async def classify_anomalies(events: list) -> dict:
    """Use Gemini to classify, prioritize, and suggest fixes for system anomalies.

    Args:
        events: List of system_events dicts from database

    Returns:
        {
            "analysis": [
                {"event_id": N, "priority": 1-5, "root_cause": "...",
                 "recommended_action": "...", "can_auto_fix": true/false,
                 "risk_level": "critical/high/medium/low"},
                ...
            ],
            "summary": "...",
            "patterns": ["<pattern1>", ...],
            "immediate_actions": ["<action1>", ...]
        }
    """
    if not events:
        return {"analysis": [], "summary": "No events to analyze.",
                "patterns": [], "immediate_actions": []}

    events_text = "\n".join(
        f"- [{e.get('event_id')}] {e.get('event_type','?').upper()} / {e.get('severity','?')} / "
        f"{e.get('category','?')}: {e.get('title','')} — {e.get('detail','')[:200]} "
        f"(tenant:{e.get('tenant_id','N/A')}, at:{e.get('created_at','')})"
        for e in events[:50]  # cap at 50 to stay within context
    )

    prompt = f"""You are a SaaS platform security analyst for Sarathi-AI, an Indian insurance advisor CRM.
Analyze these system events and provide classification, root cause analysis, and recommended actions.

EVENTS:
{events_text}

Return ONLY valid JSON:
{{
    "analysis": [
        {{
            "event_id": <event ID number>,
            "priority": <1-5, where 1 is most urgent>,
            "root_cause": "<brief root cause analysis>",
            "recommended_action": "<specific actionable step>",
            "can_auto_fix": <true if system can fix automatically, false if needs human>,
            "risk_level": "<critical|high|medium|low>"
        }}
    ],
    "summary": "<2-3 sentence executive summary of system health>",
    "patterns": ["<any patterns you see across events>"],
    "immediate_actions": ["<top 3 things to do RIGHT NOW>"]
}}

RULES:
- Prioritize security events (brute force, data leaks) as highest priority
- Group related events (same tenant, same category) in your analysis
- For each event, suggest whether it can be auto-fixed by the system
- Focus on actionable, specific recommendations
- Consider Indian business context (working hours IST, tenant = insurance firm)"""

    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("AI anomaly classification error: %s", e)
        return {
            "analysis": [{"event_id": e.get("event_id"), "priority": 3,
                           "root_cause": "AI classification unavailable",
                           "recommended_action": "Manual review required",
                           "can_auto_fix": False, "risk_level": e.get("severity", "medium")}
                         for e in events[:10]],
            "summary": "AI classification temporarily unavailable. Manual review recommended.",
            "patterns": [],
            "immediate_actions": ["Review critical events manually", "Check AI service status"]
        }


# =============================================================================
#  HELPER: Calculate age from DOB string
# =============================================================================

def _calc_age(dob_str) -> str:
    """Calculate age from DOB string (various formats). Returns 'N/A' if unparseable."""
    if not dob_str or dob_str == 'N/A':
        return 'N/A'
    try:
        dob_str = str(dob_str).strip().replace('/', '-')
        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y'):
            try:
                dob = datetime.strptime(dob_str, fmt).date()
                today = date.today()
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                return f"{age} years"
            except ValueError:
                continue
        return 'N/A'
    except Exception:
        return 'N/A'


# =============================================================================
#  HEALTH CHECK — Verify Gemini API is working
# =============================================================================

async def verify_gemini() -> dict:
    """Test Gemini API connection. Returns status dict."""
    try:
        client = _get_client()
        if not client:
            return {"status": "error", "message": "GEMINI_API_KEY not configured"}
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents="Reply with exactly: OK"
        )
        text = response.text.strip()
        return {"status": "ok", "message": f"Gemini API working. Response: {text}",
                "model": GEMINI_MODEL}
    except Exception as e:
        return {"status": "error", "message": str(e)}


_DOC_EXTRACT_PROMPT = """You are an expert Indian financial document parser for a CRM system.
Your job is to extract ALL useful information from insurance policies, mutual fund statements,
SIP confirmations, ULIP bonds, and other financial documents used by Indian insurance/MF advisors.

Return ONLY valid JSON with this structure:

{
  "document_type": "<one of: health_insurance, term_insurance, endowment, ulip, child_plan, retirement, motor_insurance, mutual_fund, sip, nps, general_insurance, unknown>",

  "client": {
    "name": "<proposer/policyholder/investor full name — the PERSON, NOT the company>",
    "phone": "<mobile number if found, else null>",
    "email": "<email if found, else null>",
    "dob": "<date of birth YYYY-MM-DD if found, else null>",
    "pan": "<PAN number if found, else null>",
    "address": "<full address or city if found, else null>",
    "confidence": "<high if name clearly identified, medium if inferred, low if guessing>"
  },

  "policy": {
    "policy_number": "<policy/folio number if found, else null>",
    "insurer": "<insurance company or AMC/fund house name>",
    "plan_name": "<product/plan/scheme name>",
    "policy_type": "<one of: health, term, endowment, ulip, child, retirement, motor, investment, nps, general>",
    "policy_status": "<one of: active, lapsed, paid_up, surrendered, matured, in_force, null if unknown>",
    "sum_insured": "<sum insured/sum assured as number, null if N/A>",
    "premium": "<premium/installment amount as number>",
    "premium_mode": "<one of: monthly, quarterly, half-yearly, annual>",
    "start_date": "<YYYY-MM-DD>",
    "end_date": "<YYYY-MM-DD>",
    "renewal_date": "<next due/renewal date YYYY-MM-DD>",
    "maturity_date": "<maturity date YYYY-MM-DD if applicable>",
    "maturity_value": "<projected/guaranteed maturity value as number, null if N/A>",
    "riders": "<comma-separated rider names if any, else null>",
    "folio_number": "<MF folio number if applicable, else null>",
    "fund_name": "<MF scheme/fund name if applicable, else null>",
    "sip_amount": "<monthly SIP/EMI amount if applicable, else null>",
    "notes": "<nominee details, exclusions, special conditions — max 300 chars>"
  },

  "insured_members": [
    {
      "name": "<insured person name>",
      "relation": "<self, spouse, son, daughter, father, mother, father-in-law, mother-in-law>",
      "dob": "<YYYY-MM-DD if found>",
      "age": "<age as number if found>",
      "sum_insured": "<individual SI if mentioned, else null>",
      "premium_share": "<individual premium if mentioned, else null>"
    }
  ],

  "nominees": [
    {
      "name": "<nominee name>",
      "relation": "<relation to policyholder>",
      "share_pct": "<percentage share, default 100>"
    }
  ]
}

CRITICAL RULES:
1. The CLIENT NAME must be the PROPOSER/POLICYHOLDER/INVESTOR — a PERSON's name. NEVER use the insurance company name as client name. "Star Health And Allied Insurance Co Ltd" is the INSURER, not the client.
2. Distinguish: Proposer (who pays) vs Insured (who is covered) vs Nominee (who gets claim). The client is always the Proposer.
3. For health/family floater policies, list ALL insured members in insured_members array.
4. Convert lakh/crore: "5 lakh" = 500000, "1 crore" = 10000000, "5L" = 500000, "1Cr" = 10000000.
5. Convert dates: DD/MM/YYYY, DD-Mon-YYYY, DD.MM.YYYY → YYYY-MM-DD.
6. Indian phone numbers: 10 digits starting with 6-9. Include country code only if +91 prefix present.
7. For MF/SIP: use folio_number, fund_name, sip_amount fields. policy_type = "investment".
8. If document has NO insured members list (e.g., term/endowment), put the policyholder as the single member with relation "self".
9. Return null for any field you cannot confidently extract. Do NOT guess or fabricate.
10. If renewal_date not explicit but start_date and premium_mode are known, calculate: annual → start + 1yr, half-yearly → start + 6mo, quarterly → start + 3mo, monthly → start + 1mo."""


async def extract_policy_from_document(text_content: str) -> dict:
    """Extract structured policy + client data from document text using Gemini AI."""
    try:
        prompt = _DOC_EXTRACT_PROMPT + f"\n\nDOCUMENT TEXT:\n{text_content[:12000]}"
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error(f"Policy extraction failed: {e}")
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            return {"_error": "AI rate limit exceeded — please try again in a minute"}
        if "API key" in err_str:
            return {"_error": "AI service not configured"}
        return {"_error": "AI extraction failed — please try again"}


async def extract_policy_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Extract structured policy + client data from a photo/scan of a document."""
    try:
        client = _get_client()
        if not client:
            raise RuntimeError("Gemini API key not configured")

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _DOC_EXTRACT_PROMPT,
            ],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        return _clean_json(response.text.strip())
    except Exception as e:
        logger.error(f"Policy image extraction failed: {e}")
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            return {"_error": "AI rate limit exceeded — please try again in a minute"}
        if "API key" in err_str:
            return {"_error": "AI service not configured"}
        return {"_error": "AI extraction failed — please try again"}


async def extract_policy_from_images(image_bytes_list: list) -> dict:
    """Extract structured policy + client data from multiple page images of a scanned document."""
    try:
        client = _get_client()
        if not client:
            raise RuntimeError("Gemini API key not configured")

        contents = []
        for img_bytes in image_bytes_list:
            contents.append(genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
        contents.append(f"These are {len(image_bytes_list)} pages of the same document. " + _DOC_EXTRACT_PROMPT)

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        return _clean_json(response.text.strip())
    except Exception as e:
        logger.error(f"Policy multi-image extraction failed: {e}")
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            return {"_error": "AI rate limit exceeded — please try again in a minute"}
        if "API key" in err_str:
            return {"_error": "AI service not configured"}
        return {"_error": "AI extraction failed — please try again"}


# =============================================================================
#  NUDGE MESSAGE GENERATION
# =============================================================================

async def generate_nudge_message(
    nudge_type: str,
    lead: dict,
    interactions: list = None,
    advisor_name: str = "",
    owner_note: str = "",
    lang: str = "en",
) -> dict:
    """AI-generate a contextual nudge message for an advisor about a lead."""
    interactions = interactions or []
    last_interaction = interactions[0] if interactions else {}

    # Bulk nudge: multiple pending follow-ups for one advisor
    if lead.get("_bulk"):
        leads_list = lead.get("_leads", [])
        leads_text = "\n".join(
            f"  {i+1}. {lx.get('lead_name','N/A')} — follow-up due: {lx.get('follow_up_date','N/A')}"
            + (f" — notes: {lx['notes']}" if lx.get('notes') else "")
            for i, lx in enumerate(leads_list)
        )
        prompt = f"""You are an expert Indian insurance sales manager AI assistant.
The firm owner wants to send a bulk nudge to an advisor about their pending follow-ups.
Generate a concise, actionable Telegram message listing the pending leads.

ADVISOR NAME: {advisor_name or 'Advisor'}
TOTAL PENDING FOLLOW-UPS: {lead.get('_count', len(leads_list))}

PENDING LEADS:
{leads_text}

Rules:
- Keep it under 300 words, Telegram-friendly with emojis
- List each lead name clearly (numbered)
- Emphasize urgency — these are overdue or due today
- End with motivational call-to-action
- If more than 10 leads, mention "and X more"

Return ONLY valid JSON:
{{
    "message": "<the Telegram message with emojis and HTML formatting (use <b>, <i> tags)>",
    "summary": "<one-line summary like 'Bulk nudge: 5 pending follow-ups'>"
}}"""
    else:
        prompt = f"""You are an expert Indian insurance sales manager AI assistant.
The firm owner wants to send a quick nudge message to their advisor via Telegram.
Generate a concise, actionable nudge message.

NUDGE TYPE: {nudge_type}
ADVISOR NAME: {advisor_name or 'Advisor'}

LEAD DETAILS:
- Name: {lead.get('name', 'N/A')}
- Phone: {lead.get('phone', 'N/A')}
- Need: {lead.get('need_type', 'N/A')}
- Stage: {lead.get('stage', 'N/A')}
- City: {lead.get('city', 'N/A')}
- Premium Budget: {lead.get('premium_budget', 'N/A')}
- Sum Insured: {lead.get('sum_insured', 'N/A')}
- Notes: {lead.get('notes', '')}

LAST INTERACTION:
- Type: {last_interaction.get('type', 'none')}
- Date: {last_interaction.get('created_at', 'N/A')}
- Summary: {last_interaction.get('summary', 'No previous interaction')}
- Follow-up due: {last_interaction.get('follow_up_date', 'N/A')}

OWNER'S NOTE: {owner_note or '(none — auto-generate appropriate message)'}

Rules:
- Keep it under 200 words, Telegram-friendly with emojis
- Include the lead's name and phone
- Be specific about what action is needed
- If nudge_type is 'followup', emphasize urgency of pending follow-up
- If nudge_type is 'new_lead', emphasize speed-to-contact
- If nudge_type is 'renewal', emphasize renewal date urgency
- If owner provided a note, incorporate it naturally
- End with a clear call-to-action

Return ONLY valid JSON:
{{
    "message": "<the Telegram message with emojis and HTML formatting (use <b>, <i> tags)>",
    "summary": "<one-line summary for the owner's dashboard log>"
}}"""

    prompt += _lang_instruction(lang)
    try:
        raw = await _ask_gemini(prompt, json_mode=True)
        return _clean_json(raw)
    except Exception as e:
        logger.error("Nudge message generation failed: %s", e)
        if lead.get("_bulk"):
            count = lead.get("_count", 0)
            return {
                "message": f"⚡ <b>Pending Follow-ups Alert</b>\n\n"
                           f"Hi {advisor_name or 'Advisor'}, you have <b>{count}</b> pending follow-ups that need attention today.\n\n"
                           f"Please check your Sarathi dashboard and update the status.",
                "summary": f"Bulk nudge: {count} pending follow-ups"
            }
        name = lead.get('name', 'Client')
        phone = lead.get('phone', '')
        return {
            "message": f"⚡ <b>Action needed</b>\n\n"
                       f"Lead: <b>{name}</b>\nPhone: {phone}\n"
                       f"Stage: {lead.get('stage', 'N/A')}\n\n"
                       f"{owner_note or 'Please follow up on this lead today.'}",
            "summary": f"Nudge sent about {name}"
        }


# =============================================================================
#  SUPPORT TICKET AI — Level 1 Auto-Response
# =============================================================================

_SUPPORT_L1_PROMPT = """You are Sarathi-AI's Level 1 support assistant.

A customer/visitor has submitted a support ticket. Analyze their question and respond.

TICKET SUBJECT: {subject}
TICKET DESCRIPTION: {description}
CATEGORY: {category}

PRODUCT KNOWLEDGE (use this to answer):
- Sarathi-AI is a CRM SaaS for Indian insurance/financial advisors
- Plans: Solo (₹199/mo, 1 user), Team (₹799/mo, 6 users), Enterprise (₹1,999/mo, 26 users)
- 14-day free trial for all plans, no credit card needed
- Features: Lead management, Voice AI ("Just Talk"), Sales pipeline, Policy tracking,
  AI tools (scoring, pitch, follow-up suggestions), Calculators (HLV, EMI, Retirement, Inflation),
  Renewals, Reminders, WhatsApp/Telegram integration, PDF reports, Google Drive backup
- Telegram bot: Each firm creates their own bot via BotFather, connects token in Sarathi
- Multi-device: Same Telegram account works on all devices automatically
- Agent invite: Owner generates invite code from Settings → Team, agent enters code on /start
- Web dashboard: Login via phone/email OTP at sarathi-ai.com/dashboard
- Solo plan: Only 1 user (owner), no agent addition
- Payment: Via Razorpay (UPI, cards, net banking)
- Data: Stored securely, per-tenant isolation, no cross-tenant data access
- Voice notes: Max 2 minutes, AI transcribes and creates leads/meetings/reminders
- Calculators: Shareable via WhatsApp with client branding
- Super admin: Internal management, not customer-facing

RULES:
1. If the question is clearly about HOW TO USE a feature → answer with step-by-step guidance
2. If the question is about PRICING/BILLING → answer with plan details
3. If the question seems like a genuine BUG or ERROR → set escalate=true
4. If user mentions "not working", "error", "broken" → check if it's a known flow first:
   - "Bot not responding" → They may need to connect their bot token first
   - "Can't add agent" → Plan limit reached, need upgrade
   - "OTP not received" → Check phone number format, try again in 2 minutes
   - "Dashboard empty" → Need to add leads first via Telegram bot
   If it matches a known pattern, answer it. If truly broken, escalate.
5. If question is about something NOT in scope → set escalate=true
6. Keep answer concise (under 200 words), friendly, professional
7. Include specific steps when relevant

Respond in JSON:
{{
  "answer": "Your helpful response text (plain text, no HTML)",
  "confidence": "high" | "medium" | "low",
  "escalate": true | false,
  "matched_topic": "billing|setup|feature|bot|calculator|general|bug|unknown"
}}"""


async def ai_support_auto_respond(subject: str, description: str,
                                  category: str = "general") -> dict:
    """Generate AI Level 1 response for a support ticket.
    Returns {answer, confidence, escalate, matched_topic} or None on failure."""
    try:
        prompt = _SUPPORT_L1_PROMPT.format(
            subject=subject[:200],
            description=description[:1000],
            category=category
        )
        raw = await _ask_gemini(prompt, json_mode=True)
        data = json.loads(raw)
        return {
            'answer': data.get('answer', ''),
            'confidence': data.get('confidence', 'low'),
            'escalate': data.get('escalate', True),
            'matched_topic': data.get('matched_topic', 'unknown'),
        }
    except Exception as e:
        logger.warning("Support AI L1 failed: %s", e)
        return None
