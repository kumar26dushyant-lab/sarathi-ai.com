# =============================================================================
#  biz_pdf.py — Sarathi-AI Business Technologies: PDF Pitch Generator
# =============================================================================
#
#  Generates branded PDF reports from calculator results.
#  Uses pure HTML → PDF conversion (no external dependencies beyond httpx).
#  PDFs are served via FastAPI for WhatsApp delivery.
#
# =============================================================================

import html
import logging
import os
import time
from datetime import datetime
from typing import Optional

from biz_calculators import (
    InflationResult, HLVResult, RetirementResult, EMIResult,
    HealthCoverResult, SIPvLumpsumResult, MFSIPResult,
    ULIPvsMFResult, NPSResult, StepUpSIPResult, SWPResult,
    DelayCostResult, format_currency,
)

logger = logging.getLogger("sarathi.pdf")

# Directory to store generated PDFs
PDF_DIR = "generated_pdfs"

# =============================================================================
#  i18n — Hindi / English labels for PDF reports
# =============================================================================
_L = {
    # ── Common ──
    "prepared_for": {"en": "Prepared for", "hi": "के लिए तैयार"},
    "your_advisor": {"en": "Your Financial Advisor", "hi": "आपके वित्तीय सलाहकार"},
    "generated_on": {"en": "Generated on", "hi": "रिपोर्ट दिनांक"},
    "secure_future": {"en": "Secure Your Future Today", "hi": "आज ही अपना भविष्य सुरक्षित करें"},
    "wa_available": {"en": "WhatsApp Available Anytime", "hi": "WhatsApp पर कभी भी संपर्क करें"},
    "year": {"en": "Year", "hi": "वर्ष"},
    "years": {"en": "Years", "hi": "वर्ष"},
    "age": {"en": "Age", "hi": "आयु"},
    # ── Inflation ──
    "inf_title": {"en": "Inflation Eraser Report", "hi": "मुद्रास्फीति प्रभाव रिपोर्ट"},
    "inf_impact": {"en": "The Inflation Impact", "hi": "मुद्रास्फीति का प्रभाव"},
    "inf_current": {"en": "Current Monthly Value", "hi": "वर्तमान मासिक मूल्य"},
    "inf_rate": {"en": "Inflation Rate", "hi": "मुद्रास्फीति दर"},
    "inf_horizon": {"en": "Time Horizon", "hi": "समय अवधि"},
    "inf_eroded": {"en": "Power Eroded", "hi": "क्रय शक्ति हानि"},
    "inf_today": {"en": "Your {amt} today will only buy", "hi": "आपके आज के {amt} की कीमत रह जाएगी"},
    "inf_worth": {"en": "worth of goods in {yrs} years", "hi": "{yrs} वर्षों में केवल इतनी"},
    "inf_need": {"en": "You'll need {amt}/month", "hi": "आपको {amt}/माह चाहिए होंगे"},
    "inf_lifestyle": {"en": "to maintain the same lifestyle in {yrs} years.", "hi": "{yrs} वर्षों में वही जीवनशैली बनाए रखने के लिए।"},
    "inf_breakdown": {"en": "Year-by-Year Breakdown", "hi": "वर्ष-दर-वर्ष विवरण"},
    "inf_pp": {"en": "Purchasing Power", "hi": "क्रय शक्ति"},
    "inf_needed": {"en": "Amount Needed", "hi": "आवश्यक राशि"},
    "inf_erosion": {"en": "Erosion", "hi": "हानि"},
    # ── HLV ──
    "hlv_title": {"en": "Human Life Value (HLV) Report", "hi": "मानव जीवन मूल्य (HLV) रिपोर्ट"},
    "hlv_profile": {"en": "Your Profile", "hi": "आपकी प्रोफ़ाइल"},
    "hlv_expense": {"en": "Monthly Family Expense", "hi": "मासिक पारिवारिक खर्च"},
    "hlv_loans": {"en": "Outstanding Loans", "hi": "बकाया ऋण"},
    "hlv_child": {"en": "Child Education Fund", "hi": "बच्चों की शिक्षा निधि"},
    "hlv_retire_yrs": {"en": "Years to Retirement", "hi": "सेवानिवृत्ति तक वर्ष"},
    "hlv_analysis": {"en": "Financial Analysis", "hi": "वित्तीय विश्लेषण"},
    "hlv_total_need": {"en": "Total Future Need", "hi": "कुल भविष्य की आवश्यकता"},
    "hlv_savings": {"en": "Current Savings", "hi": "वर्तमान बचत"},
    "hlv_cover": {"en": "Existing Cover", "hi": "मौजूदा बीमा कवर"},
    "hlv_net": {"en": "Net HLV", "hi": "शुद्ध HLV"},
    "hlv_recommended": {"en": "Recommended Term Insurance Cover", "hi": "अनुशंसित टर्म बीमा कवर"},
    "hlv_protect": {"en": "To protect your family's lifestyle", "hi": "अपने परिवार की जीवनशैली की सुरक्षा के लिए"},
    "hlv_gap": {"en": "Coverage Gap: {amt}", "hi": "कवरेज अंतर: {amt}"},
    "hlv_under": {"en": "Your family is currently under-protected by this amount.", "hi": "आपका परिवार वर्तमान में इतनी राशि से कम-सुरक्षित है।"},
    # ── Retirement ──
    "ret_title": {"en": "Retirement Planning Report", "hi": "सेवानिवृत्ति योजना रिपोर्ट"},
    "ret_profile": {"en": "Retirement Profile", "hi": "सेवानिवृत्ति प्रोफ़ाइल"},
    "ret_current_age": {"en": "Current Age", "hi": "वर्तमान आयु"},
    "ret_retire_age": {"en": "Retirement Age", "hi": "सेवानिवृत्ति आयु"},
    "ret_expense": {"en": "Current Expense", "hi": "वर्तमान खर्च"},
    "ret_inflation": {"en": "Inflation Rate", "hi": "मुद्रास्फीति दर"},
    "ret_corpus": {"en": "Retirement Corpus Needed", "hi": "सेवानिवृत्ति कोष आवश्यक"},
    "ret_expense_at": {"en": "Monthly expense at retirement", "hi": "सेवानिवृत्ति पर मासिक खर्च"},
    "ret_sip": {"en": "Start a SIP of {amt}/month", "hi": "{amt}/माह की SIP शुरू करें"},
    "ret_gap": {"en": "Gap: {amt} | The earlier you start, the less you need.", "hi": "अंतर: {amt} | जितनी जल्दी शुरू करें, उतना कम चाहिए।"},
    "ret_milestones": {"en": "Growth Milestones", "hi": "विकास मील के पत्थर"},
    "ret_annual_exp": {"en": "Annual Expense", "hi": "वार्षिक खर्च"},
    "ret_proj_corpus": {"en": "Projected Corpus", "hi": "अनुमानित कोष"},
    # ── EMI ──
    "emi_title": {"en": "Premium EMI Calculation", "hi": "प्रीमियम EMI गणना"},
    "emi_breakdown": {"en": "Premium Breakdown", "hi": "प्रीमियम विवरण"},
    "emi_total": {"en": "Total Premium", "hi": "कुल प्रीमियम"},
    "emi_gst": {"en": "GST", "hi": "GST"},
    "emi_cibil": {"en": "CIBIL Discount", "hi": "CIBIL छूट"},
    "emi_net": {"en": "Net Premium", "hi": "शुद्ध प्रीमियम"},
    "emi_down": {"en": "Down Payment", "hi": "डाउन पेमेंट"},
    "emi_balance": {"en": "Balance payable in EMI", "hi": "शेष EMI में देय"},
    "emi_options": {"en": "EMI Options", "hi": "EMI विकल्प"},
    "emi_tenure": {"en": "Tenure", "hi": "अवधि"},
    "emi_monthly": {"en": "Monthly EMI", "hi": "मासिक EMI"},
    "emi_total_amt": {"en": "Total Amount", "hi": "कुल राशि"},
    "emi_months": {"en": "months", "hi": "माह"},
    # ── Health ──
    "health_title": {"en": "Health Cover Estimator", "hi": "स्वास्थ्य बीमा अनुमानक"},
    "health_recommended": {"en": "Recommended Sum Insured", "hi": "अनुशंसित बीमा राशि"},
    "health_for": {"en": "For {family} family, age {age}, {city} city", "hi": "{family} परिवार, आयु {age}, {city} शहर के लिए"},
    "health_components": {"en": "Coverage Components", "hi": "कवरेज घटक"},
    "health_component": {"en": "Component", "hi": "घटक"},
    "health_cost": {"en": "Estimated Cost", "hi": "अनुमानित लागत"},
    "health_base": {"en": "Base Total", "hi": "आधार कुल"},
    "health_gap": {"en": "Gap Analysis", "hi": "अंतर विश्लेषण"},
    "health_existing": {"en": "Existing Cover", "hi": "मौजूदा कवर"},
    "health_rec": {"en": "Recommended", "hi": "अनुशंसित"},
    "health_gap_fill": {"en": "Gap to Fill", "hi": "भरने योग्य अंतर"},
    "health_premium": {"en": "Estimated Annual Premium", "hi": "अनुमानित वार्षिक प्रीमियम"},
    "health_low": {"en": "Low Estimate", "hi": "न्यूनतम अनुमान"},
    "health_high": {"en": "High Estimate", "hi": "अधिकतम अनुमान"},
    "health_warn": {"en": "Medical inflation is ~14% in India. Your current cover may be inadequate in 3-5 years.", "hi": "भारत में मेडिकल मुद्रास्फीति ~14% है। आपका मौजूदा कवर 3-5 वर्षों में अपर्याप्त हो सकता है।"},
    "health_room": {"en": "Room Charges (15d × 2)", "hi": "कमरे का शुल्क (15दिन × 2)"},
    "health_icu": {"en": "ICU Charges (10 days)", "hi": "ICU शुल्क (10 दिन)"},
    "health_doctor": {"en": "Doctor / Specialist Fees", "hi": "डॉक्टर / विशेषज्ञ शुल्क"},
    "health_medicines": {"en": "Medicines & Consumables", "hi": "दवाइयाँ और उपभोग्य"},
    "health_diagnostics": {"en": "Tests & Imaging", "hi": "जाँच और इमेजिंग"},
    "health_ambulance": {"en": "Ambulance", "hi": "एम्बुलेंस"},
    "health_prepost": {"en": "Pre/Post Hospitalization", "hi": "अस्पताल से पहले/बाद"},
    # ── SIP vs Lumpsum ──
    "sip_title": {"en": "SIP vs Lumpsum Comparison", "hi": "SIP बनाम एकमुश्त तुलना"},
    "sip_winner": {"en": "Winner", "hi": "विजेता"},
    "sip_on": {"en": "On {amt} over {yrs} years at {ret}% return", "hi": "{amt} पर {yrs} वर्षों में {ret}% रिटर्न पर"},
    "sip_summary": {"en": "Comparison Summary", "hi": "तुलना सारांश"},
    "sip_lump_mat": {"en": "Lumpsum Maturity", "hi": "एकमुश्त परिपक्वता"},
    "sip_mat": {"en": "SIP Maturity", "hi": "SIP परिपक्वता"},
    "sip_monthly": {"en": "Monthly SIP", "hi": "मासिक SIP"},
    "sip_diff": {"en": "Difference", "hi": "अंतर"},
    "sip_growth": {"en": "Year-wise Growth", "hi": "वर्ष-दर-वर्ष वृद्धि"},
    "sip_lump_val": {"en": "Lumpsum Value", "hi": "एकमुश्त मूल्य"},
    "sip_val": {"en": "SIP Value", "hi": "SIP मूल्य"},
    "sip_period": {"en": "Period", "hi": "अवधि"},
    # ── MF SIP Planner ──
    "mfsip_title": {"en": "Mutual Fund SIP Planner", "hi": "म्यूचुअल फंड SIP योजनाकार"},
    "mfsip_needed": {"en": "Monthly SIP Required", "hi": "मासिक SIP आवश्यक"},
    "mfsip_to_reach": {"en": "To reach {goal} in {yrs} years at {ret}% return", "hi": "{goal} तक पहुँचने के लिए {yrs} वर्षों में {ret}% रिटर्न पर"},
    "mfsip_summary": {"en": "Investment Summary", "hi": "निवेश सारांश"},
    "mfsip_goal": {"en": "Goal Amount", "hi": "लक्ष्य राशि"},
    "mfsip_invested": {"en": "Total Invested", "hi": "कुल निवेश"},
    "mfsip_corpus": {"en": "Expected Corpus", "hi": "अपेक्षित कोष"},
    "mfsip_wealth": {"en": "Wealth Gained", "hi": "अर्जित संपत्ति"},
    "mfsip_growth": {"en": "Year-wise Growth", "hi": "वर्ष-दर-वर्ष वृद्धि"},
    "mfsip_portfolio": {"en": "Portfolio Value", "hi": "पोर्टफोलियो मूल्य"},
    # ── ULIP vs MF ──
    "ulip_title": {"en": "ULIP vs Mutual Fund Comparison", "hi": "ULIP बनाम म्यूचुअल फंड तुलना"},
    "ulip_winner": {"en": "Winner after {yrs} years", "hi": "{yrs} वर्षों बाद विजेता"},
    "ulip_diff": {"en": "Difference: {amt} on {inv}/year", "hi": "अंतर: {amt}, {inv}/वर्ष पर"},
    "ulip_compare": {"en": "Side-by-Side Comparison", "hi": "साथ-साथ तुलना"},
    "ulip_mat": {"en": "ULIP Maturity", "hi": "ULIP परिपक्वता"},
    "ulip_mf_mat": {"en": "MF Maturity", "hi": "MF परिपक्वता"},
    "ulip_charges": {"en": "ULIP Total Charges", "hi": "ULIP कुल शुल्क"},
    "ulip_mf_charges": {"en": "MF Total Charges", "hi": "MF कुल शुल्क"},
    "ulip_insurance": {"en": "ULIP Insurance Benefit", "hi": "ULIP बीमा लाभ"},
    "ulip_cover": {"en": "Life Cover Included", "hi": "जीवन बीमा शामिल"},
    "ulip_note": {"en": "ULIP provides 10× annual premium as life cover. Mutual Funds do not include insurance.", "hi": "ULIP वार्षिक प्रीमियम का 10 गुना जीवन बीमा देता है। म्यूचुअल फंड में बीमा शामिल नहीं है।"},
    "ulip_yearly": {"en": "Year-wise Comparison", "hi": "वर्ष-दर-वर्ष तुलना"},
    "ulip_corpus": {"en": "ULIP Corpus", "hi": "ULIP कोष"},
    "ulip_mf_corpus": {"en": "MF Corpus", "hi": "MF कोष"},
    "ulip_mf_lead": {"en": "MF Lead", "hi": "MF बढ़त"},
    # ── NPS ──
    "nps_title": {"en": "NPS (National Pension System) Planner", "hi": "NPS (राष्ट्रीय पेंशन योजना) प्लानर"},
    "nps_corpus": {"en": "Total Corpus at Retirement", "hi": "सेवानिवृत्ति पर कुल कोष"},
    "nps_desc": {"en": "{amt}/month for {yrs} years at {ret}%", "hi": "{amt}/माह, {yrs} वर्षों के लिए {ret}% पर"},
    "nps_summary": {"en": "Retirement Summary", "hi": "सेवानिवृत्ति सारांश"},
    "nps_invested": {"en": "Total Invested", "hi": "कुल निवेश"},
    "nps_wealth": {"en": "Wealth Gained", "hi": "अर्जित संपत्ति"},
    "nps_lumpsum": {"en": "Lumpsum (60%)", "hi": "एकमुश्त (60%)"},
    "nps_annuity": {"en": "Annuity Corpus (40%)", "hi": "वार्षिकी कोष (40%)"},
    "nps_pension": {"en": "Monthly Pension & Tax Benefits", "hi": "मासिक पेंशन और कर लाभ"},
    "nps_monthly_pension": {"en": "Est. Monthly Pension", "hi": "अनु. मासिक पेंशन"},
    "nps_tax_year": {"en": "Tax Saved / Year (80CCD)", "hi": "कर बचत / वर्ष (80CCD)"},
    "nps_tax_total": {"en": "Total Tax Saved", "hi": "कुल कर बचत"},
    "nps_growth": {"en": "Year-wise Growth", "hi": "वर्ष-दर-वर्ष वृद्धि"},
    "nps_invested_col": {"en": "Invested", "hi": "निवेश"},
    "nps_corpus_col": {"en": "Corpus", "hi": "कोष"},
    "nps_tax_col": {"en": "Tax Saved", "hi": "कर बचत"},
    "nps_tip": {"en": "NPS offers additional ₹50,000 tax deduction under Section 80CCD(1B) over and above 80C limit.", "hi": "NPS धारा 80CCD(1B) के तहत 80C सीमा से अतिरिक्त ₹50,000 कर कटौती प्रदान करता है।"},
    # ── Step-Up SIP ──
    "stepupsip_title": {"en": "Step-Up SIP Planner", "hi": "स्टेप-अप SIP प्लानर"},
    "stepupsip_corpus": {"en": "Total Corpus", "hi": "कुल कोष"},
    "stepupsip_desc": {"en": "{amt}/month, {step}% annual step-up, {yrs} years at {ret}%", "hi": "{amt}/माह, {step}% वार्षिक वृद्धि, {yrs} वर्ष {ret}% पर"},
    "stepupsip_summary": {"en": "Investment Summary", "hi": "निवेश सारांश"},
    "stepupsip_start_sip": {"en": "Starting SIP", "hi": "शुरुआती SIP"},
    "stepupsip_final_sip": {"en": "Final Monthly SIP", "hi": "अंतिम मासिक SIP"},
    "stepupsip_invested": {"en": "Total Invested", "hi": "कुल निवेश"},
    "stepupsip_wealth": {"en": "Wealth Gained", "hi": "अर्जित संपत्ति"},
    "stepupsip_advantage": {"en": "Step-Up Advantage", "hi": "स्टेप-अप लाभ"},
    "stepupsip_regular": {"en": "Regular SIP Corpus", "hi": "सामान्य SIP कोष"},
    "stepupsip_extra": {"en": "Extra from Step-Up", "hi": "स्टेप-अप से अतिरिक्त"},
    "stepupsip_growth": {"en": "Year-wise Growth", "hi": "वर्ष-दर-वर्ष वृद्धि"},
    "stepupsip_monthly": {"en": "Monthly SIP", "hi": "मासिक SIP"},
    "stepupsip_corpus_col": {"en": "Corpus", "hi": "कोष"},
    "stepupsip_tip": {"en": "Even a 10% annual step-up can nearly double your corpus compared to a flat SIP.", "hi": "10% वार्षिक वृद्धि भी सामान्य SIP की तुलना में कोष को लगभग दोगुना कर सकती है।"},
    # ── SWP ──
    "swp_title": {"en": "SWP (Systematic Withdrawal Plan)", "hi": "SWP (व्यवस्थित निकासी योजना)"},
    "swp_status": {"en": "Plan Status", "hi": "योजना स्थिति"},
    "swp_sustainable": {"en": "✅ Sustainable — Corpus lasts {yrs} years", "hi": "✅ टिकाऊ — कोष {yrs} वर्ष चलेगा"},
    "swp_depleted": {"en": "⚠️ Depleted in {m} months ({y} yrs {rm} mo)", "hi": "⚠️ {m} महीनों में समाप्त ({y} वर्ष {rm} माह)"},
    "swp_summary": {"en": "Withdrawal Summary", "hi": "निकासी सारांश"},
    "swp_corpus": {"en": "Initial Corpus", "hi": "प्रारंभिक कोष"},
    "swp_monthly": {"en": "Monthly Withdrawal", "hi": "मासिक निकासी"},
    "swp_return": {"en": "Annual Return", "hi": "वार्षिक रिटर्न"},
    "swp_withdrawn": {"en": "Total Withdrawn", "hi": "कुल निकासी"},
    "swp_remaining": {"en": "Remaining Corpus", "hi": "शेष कोष"},
    "swp_growth": {"en": "Year-wise Breakdown", "hi": "वर्ष-दर-वर्ष विवरण"},
    "swp_start": {"en": "Year Start", "hi": "वर्ष आरंभ"},
    "swp_withdrawn_col": {"en": "Withdrawn", "hi": "निकासी"},
    "swp_end": {"en": "Year End", "hi": "वर्ष अंत"},
    "swp_tip": {"en": "Plan withdrawals carefully. Withdrawing more than your returns erodes your principal faster.", "hi": "निकासी की योजना सावधानी से बनाएं। रिटर्न से अधिक निकासी आपकी मूल राशि को तेजी से कम करती है।"},
    # ── Delay Cost ──
    "delay_title": {"en": "Cost of Delay Report", "hi": "विलंब लागत रिपोर्ट"},
    "delay_cost_label": {"en": "Cost of Delaying {d} Years", "hi": "{d} वर्ष विलंब की कीमत"},
    "delay_desc": {"en": "{amt}/month SIP, {yrs} year horizon at {ret}%", "hi": "{amt}/माह SIP, {yrs} वर्ष अवधि {ret}% पर"},
    "delay_summary": {"en": "Impact Analysis", "hi": "प्रभाव विश्लेषण"},
    "delay_on_time": {"en": "Start Today Corpus", "hi": "आज शुरू करें — कोष"},
    "delay_delayed": {"en": "Start After {d} Years", "hi": "{d} वर्ष बाद शुरू करें"},
    "delay_loss": {"en": "Opportunity Loss", "hi": "अवसर हानि"},
    "delay_extra": {"en": "Extra SIP Needed", "hi": "अतिरिक्त SIP आवश्यक"},
    "delay_compare": {"en": "Delay Comparison", "hi": "विलंब तुलना"},
    "delay_d_col": {"en": "Delay (yrs)", "hi": "विलंब (वर्ष)"},
    "delay_invest_col": {"en": "Invest Years", "hi": "निवेश वर्ष"},
    "delay_corpus_col": {"en": "Corpus", "hi": "कोष"},
    "delay_loss_col": {"en": "Loss", "hi": "हानि"},
    "delay_sip_col": {"en": "SIP Needed", "hi": "SIP आवश्यक"},
    "delay_tip": {"en": "Every year you delay costs you lakhs. The best time to start is NOW.", "hi": "हर साल की देरी लाखों की कीमत है। शुरू करने का सबसे अच्छा समय अभी है।"},
}

def _t(key: str, lang: str = "en") -> str:
    """Get translated label. Falls back to English."""
    entry = _L.get(key, {})
    return entry.get(lang, entry.get("en", key))


def init_pdf():
    """Ensure PDF output directory exists."""
    os.makedirs(PDF_DIR, exist_ok=True)
    logger.info("PDF output directory: %s", PDF_DIR)


def _brand_css(brand: dict = None) -> str:
    """Return branded CSS for PDF reports. Uses dynamic brand colors if provided."""
    b = brand or {}
    primary = b.get('primary_color') or '#1a56db'
    accent = b.get('accent_color') or '#ea580c'
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Poppins', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #2d2d2d; background: #fff; padding: 40px;
        }}
        .firm-banner {{
            display: flex; align-items: center; gap: 16px;
            padding: 16px 24px; margin-bottom: 10px;
            border-bottom: 3px solid {primary};
        }}
        .firm-banner .firm-logo {{
            width: 64px; height: 64px; object-fit: contain; border-radius: 8px;
        }}
        .firm-banner .firm-info {{
            flex: 1;
        }}
        .firm-banner .firm-name {{
            font-size: 20px; font-weight: 700; color: {primary};
        }}
        .firm-banner .firm-tagline {{
            font-size: 12px; color: #666; font-style: italic;
        }}
        .firm-banner .firm-contact {{
            font-size: 11px; color: #888; margin-top: 2px;
        }}
        .header {{
            background: linear-gradient(135deg, {primary} 0%, {primary}dd 100%);
            color: white; padding: 30px; border-radius: 12px;
            margin-bottom: 30px; position: relative; overflow: hidden;
        }}
        .header::after {{
            content: ''; position: absolute; top: -50%; right: -10%;
            width: 300px; height: 300px; border-radius: 50%;
            background: rgba(234, 88, 12, 0.12);
        }}
        .header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 5px; }}
        .header .tagline {{
            color: #fdba74; font-size: 14px; font-style: italic;
        }}
        .header .prepared-for {{
            margin-top: 15px; font-size: 16px; opacity: 0.9;
        }}
        .header .date {{ font-size: 12px; opacity: 0.7; margin-top: 5px; }}
        .section {{
            background: #f8f9fa; border-radius: 10px; padding: 25px;
            margin-bottom: 20px; border-left: 4px solid {primary};
        }}
        .section h2 {{
            color: {primary}; font-size: 18px; margin-bottom: 15px;
            border-bottom: 2px solid {accent}; padding-bottom: 8px;
        }}
        .stat-grid {{
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 12px; margin: 15px 0;
        }}
        .stat-card {{
            background: white; padding: 15px; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .stat-card .label {{
            font-size: 12px; color: #666; text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat-card .value {{
            font-size: 22px; font-weight: 700; color: {primary};
            margin-top: 4px;
        }}
        .highlight-box {{
            background: linear-gradient(135deg, #dbeafe, #eff6ff);
            border: 2px solid {accent}; border-radius: 10px;
            padding: 20px; text-align: center; margin: 20px 0;
        }}
        .highlight-box .big-number {{
            font-size: 36px; font-weight: 700; color: {accent};
        }}
        .highlight-box .description {{ color: #555; margin-top: 5px; }}
        .warning-box {{
            background: #fff7ed; border: 2px solid {accent};
            border-radius: 10px; padding: 20px; margin: 15px 0;
        }}
        .warning-box .icon {{ font-size: 24px; margin-right: 10px; }}
        table {{
            width: 100%; border-collapse: collapse; margin: 15px 0;
            font-size: 13px;
        }}
        th {{
            background: {primary}; color: white; padding: 10px 12px;
            text-align: left; font-weight: 600;
        }}
        td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
        tr:nth-child(even) {{ background: #f8f9fa; }}
        .footer {{
            margin-top: 40px; padding: 20px; text-align: center;
            border-top: 2px solid {accent}; color: #666; font-size: 12px;
        }}
        .footer .brand {{
            font-size: 16px; font-weight: 700; color: {primary};
        }}
        .footer .cta {{
            color: {accent}; font-weight: 600; font-size: 14px;
            margin-top: 8px;
        }}
        .footer .contact {{ margin-top: 5px; }}
        /* Agent photo */
        .agent-photo {{
            width: 56px; height: 56px; border-radius: 50%;
            object-fit: cover; border: 3px solid rgba(255,255,255,0.5);
            vertical-align: middle;
        }}
        .header .agent-row {{
            display: flex; align-items: center; gap: 14px;
            margin-top: 12px;
        }}
        .header .agent-row .agent-photo {{
            width: 52px; height: 52px; border: 3px solid rgba(253,186,116,0.6);
        }}
        .header .agent-row .agent-info {{
            font-size: 13px; opacity: 0.9;
        }}
        .header .agent-row .agent-name {{
            font-weight: 600; font-size: 14px;
        }}
        .footer .agent-photo {{
            width: 40px; height: 40px;
            border: 2px solid {primary}; margin-right: 8px;
        }}
        .footer .agent-block {{
            display: flex; align-items: center; justify-content: center;
            gap: 8px; margin-top: 8px;
        }}
    </style>
    """


def _header_html(title: str, client_name: str = None,
                 tagline: str = "AI-Powered Financial Advisor CRM",
                 agent_name: str = "", agent_photo_url: str = "",
                 lang: str = "en", brand: dict = None) -> str:
    """Generate branded header with firm banner on top and optional agent photo."""
    b = brand or {}
    # ── Firm banner (TOP of page) ──
    firm_name = b.get('firm_name', '')
    firm_logo = b.get('logo', '')
    firm_tagline = b.get('tagline', '')
    firm_phone = b.get('phone', '')
    firm_email = b.get('email', '')
    firm_website = b.get('website', '')

    firm_banner = ""
    if firm_name:
        logo_tag = ""
        if firm_logo:
            logo_tag = f'<img class="firm-logo" src="{html.escape(firm_logo)}" alt="{html.escape(firm_name)}" onerror="this.style.display=\'none\'">'
        contact_parts = []
        if firm_phone:
            contact_parts.append(f'📞 {html.escape(firm_phone)}')
        if firm_email:
            contact_parts.append(f'📧 {html.escape(firm_email)}')
        if firm_website:
            contact_parts.append(f'🌐 {html.escape(firm_website)}')
        contact_line = f'<div class="firm-contact">{" | ".join(contact_parts)}</div>' if contact_parts else ''
        tagline_line = f'<div class="firm-tagline">{html.escape(firm_tagline)}</div>' if firm_tagline else ''
        firm_banner = f"""
    <div class="firm-banner">
        {logo_tag}
        <div class="firm-info">
            <div class="firm-name">{html.escape(firm_name)}</div>
            {tagline_line}
            {contact_line}
        </div>
    </div>"""

    prepared = ""
    if client_name:
        lbl = _t("prepared_for", lang)
        prepared = f'<div class="prepared-for">{lbl}: <strong>{html.escape(client_name)}</strong></div>'
    agent_row = ""
    if agent_name:
        photo_tag = ""
        if agent_photo_url:
            photo_tag = f'<img class="agent-photo" src="{html.escape(agent_photo_url)}" alt="{html.escape(agent_name)}" onerror="this.style.display=\'none\'">'
        adv_label = _t("your_advisor", lang)
        agent_row = f"""
        <div class="agent-row">
            {photo_tag}
            <div class="agent-info">
                <div class="agent-name">{html.escape(agent_name)}</div>
                <div>{adv_label}</div>
            </div>
        </div>"""
    gen_label = _t("generated_on", lang)
    return f"""
    {firm_banner}
    <div class="header">
        <h1>📊 {html.escape(title)}</h1>
        <div class="tagline">{html.escape(tagline)}</div>
        {prepared}
        {agent_row}
        <div class="date">{gen_label}: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</div>
    </div>
    """


def _footer_html(agent_name: str = "Your Advisor", phone: str = "",
                 company: str = "Sarathi-AI Business Technologies",
                 cta: str = "",
                 credentials: str = "",
                 agent_photo_url: str = "",
                 lang: str = "en",
                 brand: dict = None) -> str:
    """Generate branded footer."""
    if not cta:
        cta = _t("secure_future", lang)
    b = brand or {}
    firm_email = b.get('email', '')
    firm_website = b.get('website', '')
    microsite_url = b.get('microsite_url', '')
    contact_parts = [f'👤 {html.escape(agent_name)}']
    if phone:
        contact_parts.append(f'📞 {phone}')
    contact_line = ' | '.join(contact_parts)
    # Firm website + email line in footer
    firm_contact_parts = []
    if firm_email:
        firm_contact_parts.append(f'📧 {html.escape(firm_email)}')
    if firm_website:
        firm_contact_parts.append(f'🌐 {html.escape(firm_website)}')
    firm_contact_line = f'<div style="margin-top: 6px; font-size: 11px; color: #666;">{" | ".join(firm_contact_parts)}</div>' if firm_contact_parts else ''
    # Microsite CTA — prominently featured if available
    microsite_cta = ''
    if microsite_url:
        microsite_cta = (
            f'<div style="margin-top:10px;padding:8px 14px;background:linear-gradient(135deg,#0d9488,#0f766e);'
            f'color:#fff;border-radius:8px;display:inline-block;font-size:12px;font-weight:600">'
            f'🌐 Visit my page: <a href="{html.escape(microsite_url)}" '
            f'style="color:#fff;text-decoration:underline">{html.escape(microsite_url)}</a></div>'
        )
    cred_line = ""
    if credentials:
        cred_line = f'<div style="margin-top: 8px; font-size: 11px; color: #999;">{html.escape(credentials)}</div>'
    agent_block = ""
    if agent_photo_url:
        agent_block = f"""
        <div class="agent-block">
            <img class="agent-photo" src="{html.escape(agent_photo_url)}" alt="{html.escape(agent_name)}" onerror="this.style.display='none'">
            <span>{html.escape(agent_name)}</span>
        </div>"""
    return f"""
    <div class="footer">
        <div class="brand">🏢 {html.escape(company)}</div>
        <div class="cta">{html.escape(cta)}</div>
        {agent_block}
        <div class="contact">
            {contact_line}
        </div>
        {firm_contact_line}
        {microsite_cta}
        {cred_line}
    </div>
    """


# =============================================================================
#  PDF GENERATORS (return HTML string — rendered in browser for PDF)
# =============================================================================

def generate_inflation_html(result: InflationResult,
                            client_name: str = None,
                            agent_name: str = "",
                            agent_phone: str = "",
                            agent_photo_url: str = "",
                            company: str = "",
                            lang: str = "en",
                            brand: dict = None) -> str:
    """Generate Inflation Eraser report as HTML."""
    t = lambda k: _t(k, lang)
    # Build breakdown table
    table_rows = ""
    for yr in result.yearly_breakdown:
        table_rows += f"""
        <tr>
            <td>{t('year')} {yr['year']}</td>
            <td>{format_currency(yr['purchasing_power'])}</td>
            <td>{format_currency(yr['future_needed'])}</td>
            <td style="color: #CC0000; font-weight: 600;">{yr['erosion_percent']}%</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('inf_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('inf_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="section">
    <h2>📉 {t('inf_impact')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('inf_current')}</div>
            <div class="value">{format_currency(result.current_value)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('inf_rate')}</div>
            <div class="value">{result.inflation_rate}%</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('inf_horizon')}</div>
            <div class="value">{result.years} {t('years')}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('inf_eroded')}</div>
            <div class="value" style="color:#CC0000">{result.erosion_percent}%</div>
        </div>
    </div>
</div>

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('inf_today').format(amt=format_currency(result.current_value))}</div>
    <div class="big-number">{format_currency(result.purchasing_power_left)}</div>
    <div class="description">{t('inf_worth').format(yrs=result.years)}</div>
</div>

<div class="warning-box">
    <span class="icon">⚠️</span>
    <strong>{t('inf_need').format(amt=format_currency(result.future_value_needed))}</strong>
    {t('inf_lifestyle').format(yrs=result.years)}
</div>

<div class="section">
    <h2>📊 {t('inf_breakdown')}</h2>
    <table>
        <thead><tr>
            <th>{t('year')}</th><th>{t('inf_pp')}</th>
            <th>{t('inf_needed')}</th><th>{t('inf_erosion')}</th>
        </tr></thead>
        <tbody>{table_rows}</tbody>
    </table>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


def generate_hlv_html(result: HLVResult, client_name: str = None,
                      agent_name: str = "",
                      agent_phone: str = "",
                      agent_photo_url: str = "",
                      company: str = "",
                      lang: str = "en",
                      brand: dict = None) -> str:
    """Generate HLV report as HTML."""
    t = lambda k: _t(k, lang)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('hlv_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('hlv_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="section">
    <h2>👤 {t('hlv_profile')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('hlv_expense')}</div>
            <div class="value">{format_currency(result.monthly_expense)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('hlv_loans')}</div>
            <div class="value">{format_currency(result.outstanding_loans)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('hlv_child')}</div>
            <div class="value">{format_currency(result.child_education)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('hlv_retire_yrs')}</div>
            <div class="value">{result.years_to_retirement}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>📊 {t('hlv_analysis')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('hlv_total_need')}</div>
            <div class="value">{format_currency(result.total_liability)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('hlv_savings')}</div>
            <div class="value" style="color: green;">{format_currency(result.current_savings)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('hlv_cover')}</div>
            <div class="value">{format_currency(result.existing_cover)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('hlv_net')}</div>
            <div class="value">{format_currency(result.net_hlv)}</div>
        </div>
    </div>
</div>

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('hlv_recommended')}</div>
    <div class="big-number">{format_currency(result.recommended_cover)}</div>
    <div class="description">{t('hlv_protect')}</div>
</div>

<div class="warning-box">
    <span class="icon">🔴</span>
    <strong>{t('hlv_gap').format(amt=format_currency(result.gap))}</strong><br>
    <span style="font-size: 13px;">{t('hlv_under')}</span>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


def generate_retirement_html(result: RetirementResult,
                             client_name: str = None,
                             agent_name: str = "",
                             agent_phone: str = "",
                             agent_photo_url: str = "",
                             company: str = "",
                             lang: str = "en",
                             brand: dict = None) -> str:
    """Generate Retirement Planning report as HTML."""
    t = lambda k: _t(k, lang)
    table_rows = ""
    for yr in result.yearly_breakdown:
        if yr['year'] % 5 == 0 or yr['year'] == 1 or yr['year'] == len(result.yearly_breakdown):
            table_rows += f"""
            <tr>
                <td>{t('age')} {yr['age']}</td>
                <td>{format_currency(yr['annual_expense'])}/yr</td>
                <td>{format_currency(yr['total_corpus'])}</td>
            </tr>
            """

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('ret_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('ret_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="section">
    <h2>👤 {t('ret_profile')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('ret_current_age')}</div>
            <div class="value">{result.current_age}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('ret_retire_age')}</div>
            <div class="value">{result.retirement_age}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('ret_expense')}</div>
            <div class="value">{format_currency(result.monthly_expense)}/mo</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('ret_inflation')}</div>
            <div class="value">{result.inflation_rate}%</div>
        </div>
    </div>
</div>

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('ret_corpus')}</div>
    <div class="big-number">{format_currency(result.corpus_needed)}</div>
    <div class="description">
        {t('ret_expense_at')}: {format_currency(result.expense_at_retirement)}
    </div>
</div>

<div class="warning-box">
    <span class="icon">📈</span>
    <strong>{t('ret_sip').format(amt=format_currency(result.monthly_sip_needed))}</strong><br>
    <span style="font-size: 13px;">
        {t('ret_gap').format(amt=format_currency(result.gap))}
    </span>
</div>

<div class="section">
    <h2>📊 {t('ret_milestones')}</h2>
    <table>
        <thead><tr>
            <th>{t('age')}</th><th>{t('ret_annual_exp')}</th><th>{t('ret_proj_corpus')}</th>
        </tr></thead>
        <tbody>{table_rows}</tbody>
    </table>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


def generate_emi_html(result: EMIResult, client_name: str = None,
                      agent_name: str = "",
                      agent_phone: str = "",
                      agent_photo_url: str = "",
                      company: str = "",
                      lang: str = "en",
                      brand: dict = None) -> str:
    """Generate EMI calculator report as HTML."""
    t = lambda k: _t(k, lang)
    t = lambda k: _t(k, lang)
    emi_rows = ""
    for opt in result.emi_options:
        emi_rows += f"""
        <tr>
            <td>{opt['months']} {t('emi_months')}</td>
            <td>{format_currency(opt['monthly_emi'])}</td>
            <td>{format_currency(opt['total_amount'])}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('emi_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('emi_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="section">
    <h2>💳 {t('emi_breakdown')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('emi_total')}</div>
            <div class="value">{format_currency(result.total_premium)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('emi_gst')}</div>
            <div class="value">{format_currency(result.gst_amount)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('emi_cibil')} ({result.cibil_discount_pct}%)</div>
            <div class="value" style="color:green;">-{format_currency(result.cibil_discount)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('emi_net')}</div>
            <div class="value">{format_currency(result.net_premium)}</div>
        </div>
    </div>
</div>

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('emi_down')}</div>
    <div class="big-number">{format_currency(result.down_payment)}</div>
    <div class="description">{t('emi_balance')}</div>
</div>

<div class="section">
    <h2>📊 {t('emi_options')}</h2>
    <table>
        <thead><tr><th>{t('emi_tenure')}</th><th>{t('emi_monthly')}</th><th>{t('emi_total_amt')}</th></tr></thead>
        <tbody>{emi_rows}</tbody>
    </table>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  5. HEALTH COVER REPORT
# =============================================================================

def generate_health_html(result: HealthCoverResult, client_name: str = None,
                         agent_name: str = "", agent_phone: str = "",
                         agent_photo_url: str = "", company: str = "",
                         lang: str = "en",
                         brand: dict = None) -> str:
    """Generate Health Cover Estimator report as HTML."""
    t = lambda k: _t(k, lang)
    comp = result.coverage_components
    comp_rows = ""
    labels = {
        'room_charges': t('health_room'),
        'icu_charges': t('health_icu'),
        'doctor_fees': t('health_doctor'),
        'medicines': t('health_medicines'),
        'diagnostics': t('health_diagnostics'),
        'ambulance': t('health_ambulance'),
        'pre_post_hospitalization': t('health_prepost'),
    }
    for key, label in labels.items():
        val = comp.get(key, 0)
        comp_rows += f"<tr><td>{label}</td><td>{format_currency(val)}</td></tr>\n"

    prem = result.estimated_premium_range
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('health_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('health_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('health_recommended')}</div>
    <div class="big-number">{format_currency(result.recommended_si)}</div>
    <div class="description">{t('health_for').format(family=result.family_size, age=result.age, city=result.city_tier)}</div>
</div>

<div class="section">
    <h2>🏥 {t('health_components')}</h2>
    <table>
        <thead><tr><th>{t('health_component')}</th><th>{t('health_cost')}</th></tr></thead>
        <tbody>{comp_rows}</tbody>
        <tfoot><tr><th>{t('health_base')}</th><th>{format_currency(comp.get('base_total', 0))}</th></tr></tfoot>
    </table>
    <p style="font-size:12px;color:#888;">Family multiplier: {comp.get('family_multiplier', 1)}× | Medical inflation factor: {comp.get('inflation_factor', 1)}×</p>
</div>

<div class="section">
    <h2>📊 {t('health_gap')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('health_existing')}</div>
            <div class="value">{format_currency(result.existing_cover)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('health_rec')}</div>
            <div class="value">{format_currency(result.recommended_si)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('health_gap_fill')}</div>
            <div class="value" style="color:#dc2626;">{format_currency(result.gap)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>💰 {t('health_premium')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('health_low')}</div>
            <div class="value">{format_currency(prem.get('low', 0))}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('health_high')}</div>
            <div class="value">{format_currency(prem.get('high', 0))}</div>
        </div>
    </div>
</div>

<div class="warning-box">
    <span class="icon">⚠️</span>
    <span>{t('health_warn')}</span>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  6. SIP vs LUMPSUM REPORT
# =============================================================================

def generate_sip_html(result: SIPvLumpsumResult, client_name: str = None,
                      agent_name: str = "", agent_phone: str = "",
                      agent_photo_url: str = "", company: str = "",
                      lang: str = "en",
                      brand: dict = None) -> str:
    """Generate SIP vs Lumpsum comparison report as HTML."""
    t = lambda k: _t(k, lang)
    yearly_rows = ""
    for yr in result.yearly_comparison:
        yearly_rows += f"""<tr>
            <td>{t('year')} {yr['year']}</td>
            <td>{format_currency(yr['lumpsum_value'])}</td>
            <td>{format_currency(yr['sip_value'])}</td>
        </tr>\n"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('sip_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('sip_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('sip_winner')}</div>
    <div class="big-number">🏆 {result.winner}</div>
    <div class="description">{t('sip_on').format(amt=format_currency(result.investment_amount), yrs=result.years, ret=result.expected_return)}</div>
</div>

<div class="section">
    <h2>📊 {t('sip_summary')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('sip_lump_mat')}</div>
            <div class="value">{format_currency(result.lumpsum_maturity)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('sip_mat')}</div>
            <div class="value">{format_currency(result.sip_maturity)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('sip_monthly')}</div>
            <div class="value">{format_currency(result.sip_monthly)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('sip_diff')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.difference)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>📈 {t('sip_growth')}</h2>
    <table>
        <thead><tr><th>{t('sip_period')}</th><th>{t('sip_lump_val')}</th><th>{t('sip_val')}</th></tr></thead>
        <tbody>{yearly_rows}</tbody>
    </table>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  7. MF SIP PLANNER REPORT
# =============================================================================

def generate_mfsip_html(result: MFSIPResult, client_name: str = None,
                        agent_name: str = "", agent_phone: str = "",
                        agent_photo_url: str = "", company: str = "",
                        lang: str = "en",
                        brand: dict = None) -> str:
    """Generate MF SIP Planner report as HTML."""
    t = lambda k: _t(k, lang)
    yearly_rows = ""
    for yr in result.yearly_breakdown:
        yearly_rows += f"""<tr>
            <td>{t('year')} {yr['year']}</td>
            <td>{format_currency(yr['invested'])}</td>
            <td>{format_currency(yr['total_value'])}</td>
        </tr>\n"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('mfsip_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('mfsip_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('mfsip_needed')}</div>
    <div class="big-number">{format_currency(result.monthly_sip)}</div>
    <div class="description">{t('mfsip_to_reach').format(goal=format_currency(result.goal_amount), yrs=result.years, ret=result.annual_return)}</div>
</div>

<div class="section">
    <h2>📊 {t('mfsip_summary')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('mfsip_goal')}</div>
            <div class="value">{format_currency(result.goal_amount)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('mfsip_invested')}</div>
            <div class="value">{format_currency(result.total_invested)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('mfsip_corpus')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.expected_corpus)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('mfsip_wealth')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.wealth_gained)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>📈 {t('mfsip_growth')}</h2>
    <table>
        <thead><tr><th>{t('sip_period')}</th><th>{t('mfsip_invested')}</th><th>{t('mfsip_portfolio')}</th></tr></thead>
        <tbody>{yearly_rows}</tbody>
    </table>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  8. ULIP vs MUTUAL FUND REPORT
# =============================================================================

def generate_ulip_html(result: ULIPvsMFResult, client_name: str = None,
                       agent_name: str = "", agent_phone: str = "",
                       agent_photo_url: str = "", company: str = "",
                       lang: str = "en",
                       brand: dict = None) -> str:
    """Generate ULIP vs Mutual Fund comparison report as HTML."""
    t = lambda k: _t(k, lang)
    comparison_rows = ""
    for i in range(len(result.ulip_yearly)):
        uy = result.ulip_yearly[i]
        my = result.mf_yearly[i]
        comparison_rows += f"""<tr>
            <td>{t('year')} {uy['year']}</td>
            <td>{format_currency(uy['corpus'])}</td>
            <td>{format_currency(my['corpus'])}</td>
            <td>{format_currency(my['corpus'] - uy['corpus'])}</td>
        </tr>\n"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('ulip_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('ulip_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('ulip_winner').format(yrs=result.years)}</div>
    <div class="big-number">🏆 {result.winner}</div>
    <div class="description">{t('ulip_diff').format(amt=format_currency(result.difference), inv=format_currency(result.investment_amount))}</div>
</div>

<div class="section">
    <h2>⚖️ {t('ulip_compare')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('ulip_mat')}</div>
            <div class="value">{format_currency(result.ulip_maturity)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('ulip_mf_mat')}</div>
            <div class="value">{format_currency(result.mf_maturity)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('ulip_charges')}</div>
            <div class="value" style="color:#dc2626;">{format_currency(result.ulip_charges_total)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('ulip_mf_charges')}</div>
            <div class="value" style="color:#dc2626;">{format_currency(result.mf_charges_total)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>🛡️ {t('ulip_insurance')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('ulip_cover')}</div>
            <div class="value">{format_currency(result.insurance_cover)}</div>
        </div>
    </div>
    <p style="font-size:12px;color:#888;">{t('ulip_note')}</p>
</div>

<div class="section">
    <h2>📈 {t('ulip_yearly')}</h2>
    <table>
        <thead><tr><th>{t('sip_period')}</th><th>{t('ulip_corpus')}</th><th>{t('ulip_mf_corpus')}</th><th>{t('ulip_mf_lead')}</th></tr></thead>
        <tbody>{comparison_rows}</tbody>
    </table>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  9. NPS PLANNER REPORT
# =============================================================================

def generate_nps_html(result: NPSResult, client_name: str = None,
                      agent_name: str = "", agent_phone: str = "",
                      agent_photo_url: str = "", company: str = "",
                      lang: str = "en",
                      brand: dict = None) -> str:
    """Generate NPS Planner report as HTML."""
    t = lambda k: _t(k, lang)
    yearly_rows = ""
    # Show first 5, then every 5th year, then last
    shown = set()
    for yr in result.yearly_breakdown:
        y = yr['year']
        if y <= 5 or y % 5 == 0 or y == result.years_to_retire:
            if y not in shown:
                shown.add(y)
                yearly_rows += f"""<tr>
                    <td>{t('year')} {y} ({t('age')} {yr['age']})</td>
                    <td>{format_currency(yr['invested'])}</td>
                    <td>{format_currency(yr['corpus'])}</td>
                    <td>{format_currency(yr['tax_saved'])}</td>
                </tr>\n"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('nps_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('nps_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('nps_corpus')}</div>
    <div class="big-number">{format_currency(result.total_corpus)}</div>
    <div class="description">{t('nps_desc').format(amt=format_currency(result.monthly_contribution), yrs=result.years_to_retire, ret=result.annual_return)}</div>
</div>

<div class="section">
    <h2>📊 {t('nps_summary')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('nps_invested')}</div>
            <div class="value">{format_currency(result.total_invested)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('nps_wealth')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.wealth_gained)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('nps_lumpsum')}</div>
            <div class="value">{format_currency(result.lumpsum_withdrawal)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('nps_annuity')}</div>
            <div class="value">{format_currency(result.annuity_corpus)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>🏛️ {t('nps_pension')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('nps_monthly_pension')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.monthly_pension_estimate)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('nps_tax_year')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.tax_saved_yearly)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('nps_tax_total')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.tax_saved_total)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>📈 {t('nps_growth')}</h2>
    <table>
        <thead><tr><th>{t('sip_period')}</th><th>{t('nps_invested_col')}</th><th>{t('nps_corpus_col')}</th><th>{t('nps_tax_col')}</th></tr></thead>
        <tbody>{yearly_rows}</tbody>
    </table>
</div>

<div class="warning-box">
    <span class="icon">💡</span>
    <span>{t('nps_tip')}</span>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  10. STEP-UP SIP REPORT
# =============================================================================

def generate_stepupsip_html(result: StepUpSIPResult, client_name: str = None,
                            agent_name: str = "", agent_phone: str = "",
                            agent_photo_url: str = "", company: str = "",
                            lang: str = "en",
                            brand: dict = None) -> str:
    """Generate Step-Up SIP report as HTML."""
    t = lambda k: _t(k, lang)
    yearly_rows = ""
    for yr in result.yearly_breakdown:
        yearly_rows += f"""<tr>
            <td>{t('year')} {yr['year']}</td>
            <td>{format_currency(yr['monthly_sip'])}</td>
            <td>{format_currency(yr.get('corpus', 0))}</td>
        </tr>\n"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('stepupsip_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('stepupsip_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('stepupsip_corpus')}</div>
    <div class="big-number">{format_currency(result.total_corpus)}</div>
    <div class="description">{t('stepupsip_desc').format(amt=format_currency(result.initial_monthly_sip), step=result.annual_step_up, yrs=result.years, ret=result.annual_return)}</div>
</div>

<div class="section">
    <h2>📊 {t('stepupsip_summary')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('stepupsip_start_sip')}</div>
            <div class="value">{format_currency(result.initial_monthly_sip)}/mo</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('stepupsip_final_sip')}</div>
            <div class="value">{format_currency(result.final_monthly_sip)}/mo</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('stepupsip_invested')}</div>
            <div class="value">{format_currency(result.total_invested)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('stepupsip_wealth')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.wealth_gained)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>⚡ {t('stepupsip_advantage')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('stepupsip_regular')}</div>
            <div class="value">{format_currency(result.regular_sip_corpus)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('stepupsip_extra')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.stepup_advantage)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>📈 {t('stepupsip_growth')}</h2>
    <table>
        <thead><tr><th>{t('year')}</th><th>{t('stepupsip_monthly')}</th><th>{t('stepupsip_corpus_col')}</th></tr></thead>
        <tbody>{yearly_rows}</tbody>
    </table>
</div>

<div class="warning-box">
    <span>{t('stepupsip_tip')}</span>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  11. SWP REPORT
# =============================================================================

def generate_swp_html(result: SWPResult, client_name: str = None,
                      agent_name: str = "", agent_phone: str = "",
                      agent_photo_url: str = "", company: str = "",
                      lang: str = "en",
                      brand: dict = None) -> str:
    """Generate SWP report as HTML."""
    t = lambda k: _t(k, lang)

    if result.is_sustainable:
        status_text = t('swp_sustainable').format(yrs=result.years)
    else:
        y = result.corpus_lasted_months // 12
        rm = result.corpus_lasted_months % 12
        status_text = t('swp_depleted').format(m=result.corpus_lasted_months, y=y, rm=rm)

    yearly_rows = ""
    for yr in result.yearly_breakdown:
        yearly_rows += f"""<tr>
            <td>{t('year')} {yr['year']}</td>
            <td>{format_currency(yr['year_start'])}</td>
            <td>{format_currency(yr['withdrawn'])}</td>
            <td>{format_currency(yr['year_end'])}</td>
        </tr>\n"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('swp_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('swp_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('swp_status')}</div>
    <div class="big-number">{status_text}</div>
</div>

<div class="section">
    <h2>📊 {t('swp_summary')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('swp_corpus')}</div>
            <div class="value">{format_currency(result.initial_corpus)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('swp_monthly')}</div>
            <div class="value">{format_currency(result.monthly_withdrawal)}/mo</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('swp_withdrawn')}</div>
            <div class="value">{format_currency(result.total_withdrawn)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('swp_remaining')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.remaining_corpus)}</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>📈 {t('swp_growth')}</h2>
    <table>
        <thead><tr><th>{t('year')}</th><th>{t('swp_start')}</th><th>{t('swp_withdrawn_col')}</th><th>{t('swp_end')}</th></tr></thead>
        <tbody>{yearly_rows}</tbody>
    </table>
</div>

<div class="warning-box">
    <span>{t('swp_tip')}</span>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  12. DELAY COST REPORT
# =============================================================================

def generate_delaycost_html(result: DelayCostResult, client_name: str = None,
                            agent_name: str = "", agent_phone: str = "",
                            agent_photo_url: str = "", company: str = "",
                            lang: str = "en",
                            brand: dict = None) -> str:
    """Generate Delay Cost report as HTML."""
    t = lambda k: _t(k, lang)
    compare_rows = ""
    for c in result.comparison:
        compare_rows += f"""<tr>
            <td>{c['delay']}</td>
            <td>{c['invest_years']}</td>
            <td>{format_currency(c['corpus'])}</td>
            <td style="color:#dc2626;">{format_currency(c['loss'])}</td>
            <td>{format_currency(c['sip_needed'])}</td>
        </tr>\n"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t('delay_title')}</title>
{_brand_css(brand)}
</head><body>
{_header_html(t('delay_title'), client_name, agent_name=agent_name, agent_photo_url=agent_photo_url, lang=lang, brand=brand)}

<div class="highlight-box">
    <div style="font-size: 14px; color: #666;">{t('delay_cost_label').format(d=result.delay_years)}</div>
    <div class="big-number" style="color:#dc2626;">{format_currency(result.cost_of_delay)}</div>
    <div class="description">{t('delay_desc').format(amt=format_currency(result.monthly_sip), yrs=result.years, ret=result.annual_return)}</div>
</div>

<div class="section">
    <h2>📊 {t('delay_summary')}</h2>
    <div class="stat-grid">
        <div class="stat-card">
            <div class="label">{t('delay_on_time')}</div>
            <div class="value" style="color:#16a34a;">{format_currency(result.corpus_on_time)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('delay_delayed').format(d=result.delay_years)}</div>
            <div class="value">{format_currency(result.corpus_delayed)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('delay_loss')}</div>
            <div class="value" style="color:#dc2626;">{format_currency(result.cost_of_delay)}</div>
        </div>
        <div class="stat-card">
            <div class="label">{t('delay_extra')}</div>
            <div class="value">{format_currency(result.extra_sip_needed)}/mo</div>
        </div>
    </div>
</div>

<div class="section">
    <h2>📈 {t('delay_compare')}</h2>
    <table>
        <thead><tr><th>{t('delay_d_col')}</th><th>{t('delay_invest_col')}</th><th>{t('delay_corpus_col')}</th><th>{t('delay_loss_col')}</th><th>{t('delay_sip_col')}</th></tr></thead>
        <tbody>{compare_rows}</tbody>
    </table>
</div>

<div class="warning-box">
    <span>{t('delay_tip')}</span>
</div>

{_footer_html(agent_name=agent_name or 'Your Advisor', phone=agent_phone, company=company or 'Sarathi-AI Business Technologies', agent_photo_url=agent_photo_url, lang=lang, brand=brand)}
</body></html>"""


# =============================================================================
#  SAVE REPORT TO FILE
# =============================================================================

def save_html_report(html_content: str, report_type: str,
                     client_name: str = None, advisor_name: str = None) -> str:
    """
    Save HTML report to file and return the filename.
    The HTML file acts as the printable/PDF-able report.
    """
    init_pdf()
    import re as _re
    timestamp = int(time.time())
    safe_name = (client_name or "client").replace(" ", "-").replace("_", "-").lower()
    safe_name = _re.sub(r'[^a-zA-Z0-9-]', '', safe_name) or "client"
    # Include advisor/firm name for branded URLs
    safe_advisor = ""
    if advisor_name:
        safe_advisor = advisor_name.replace(" ", "-").replace("_", "-").lower()
        safe_advisor = _re.sub(r'[^a-zA-Z0-9-]', '', safe_advisor)
    if safe_advisor:
        filename = f"{report_type}-{safe_name}-by-{safe_advisor}-{timestamp}.html"
    else:
        filename = f"{report_type}-{safe_name}-{timestamp}.html"
    filepath = os.path.join(PDF_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    logger.info("Report saved: %s", filepath)
    return filename
