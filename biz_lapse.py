"""
biz_lapse.py — Lapse-Risk Prediction (Feature 2)
=================================================

Heuristic, fully-explainable risk score (0-100) for active policies.
Predicts which clients are most likely to let their policy lapse at the
next renewal, so the advisor can intervene early.

NOT machine-learning. NOT a black box. Every risk point is attributed
to a specific, advisor-visible factor with an actionable recommendation.

Buckets:
    0-24    LOW       — green   — no action needed
    25-49   MEDIUM    — yellow  — schedule a check-in
    50-74   HIGH      — orange  — call this week
    75-100  CRITICAL  — red     — call today

Public API
----------
    await get_at_risk_policies(tenant_id, days_ahead=120, min_score=25)
        -> list[dict] sorted by risk desc
    await get_policy_risk_detail(policy_id, tenant_id)
        -> dict with full factor breakdown

Each factor returned has shape:
    {"code": str, "weight": int, "label_en": str, "label_hi": str,
     "advice_en": str, "advice_hi": str}
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import aiosqlite

logger = logging.getLogger("sarathi.lapse")

DB_PATH = "sarathi_biz.db"


# ---- bucket helpers -----------------------------------------------------
def _bucket(score: int) -> tuple[str, str]:
    """Return (bucket_code, color_hex) for a 0-100 score."""
    if score >= 75:
        return ("critical", "#dc2626")
    if score >= 50:
        return ("high", "#ea580c")
    if score >= 25:
        return ("medium", "#eab308")
    return ("low", "#16a34a")


def _bucket_label(bucket: str, lang: str = "en") -> str:
    en = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
    hi = {"critical": "अति गंभीर", "high": "उच्च", "medium": "मध्यम", "low": "कम"}
    return (hi if lang == "hi" else en).get(bucket, bucket.upper())


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.split(" ")[0]).date()
    except Exception:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except Exception:
            return None


# ---- factor catalogue (ordered roughly by impact) -----------------------
# Each factor is a tuple of (code, weight, en_label, hi_label, en_advice, hi_advice).
_F = {
    "renewal_overdue":       (35, "Renewal date already passed",
                                  "नवीनीकरण तिथि पहले ही बीत चुकी है",
                                  "Call client today — policy is past due. Risk of immediate lapse.",
                                  "क्लाइंट को आज ही कॉल करें — पॉलिसी की नियत तिथि बीत चुकी है।"),
    "renewal_within_15":     (25, "Renewal within 15 days",
                                  "15 दिनों में नवीनीकरण",
                                  "Send renewal reminder + payment link this week.",
                                  "इस सप्ताह नवीनीकरण रिमाइंडर + भुगतान लिंक भेजें।"),
    "renewal_within_45":     (12, "Renewal within 45 days",
                                  "45 दिनों में नवीनीकरण",
                                  "Schedule a courtesy call before the due date.",
                                  "नियत तिथि से पहले एक शिष्टाचार कॉल करें।"),
    "no_contact_180d":       (20, "No interaction in 180+ days",
                                  "180+ दिनों से कोई संपर्क नहीं",
                                  "Cold client — re-engage with a value-add message before mentioning renewal.",
                                  "ठंडा क्लाइंट — नवीनीकरण की बात से पहले एक मूल्यवर्धक संदेश से दोबारा जुड़ें।"),
    "no_contact_90d":        (10, "No interaction in 90+ days",
                                  "90+ दिनों से कोई संपर्क नहीं",
                                  "Send a personal check-in WhatsApp this week.",
                                  "इस सप्ताह व्यक्तिगत व्हाट्सएप संदेश भेजें।"),
    "monthly_premium_mode":  (10, "Monthly-pay policy (highest lapse risk)",
                                  "मासिक भुगतान पॉलिसी (सबसे अधिक लैप्स जोखिम)",
                                  "Suggest switching to quarterly or annual mode — auto-debit recommended.",
                                  "तिमाही या वार्षिक मोड पर स्विच करने का सुझाव दें — ऑटो-डेबिट की सिफारिश करें।"),
    "quarterly_premium_mode":(5,  "Quarterly-pay policy",
                                  "तिमाही भुगतान पॉलिसी",
                                  "Annual mode reduces lapse risk; consider proposing it.",
                                  "वार्षिक मोड लैप्स जोखिम कम करता है; इसे प्रस्तावित करने पर विचार करें।"),
    "high_premium":          (8,  "High premium (>₹50,000/yr)",
                                  "उच्च प्रीमियम (₹50,000/वर्ष से अधिक)",
                                  "High-ticket policies need extra hand-holding around renewal.",
                                  "उच्च-मूल्य की पॉलिसियों को नवीनीकरण के समय अतिरिक्त सहायता की आवश्यकता होती है।"),
    "old_policy_5yr":        (8,  "Policy over 5 years old (renewal fatigue)",
                                  "5 वर्ष से पुरानी पॉलिसी (नवीनीकरण थकान)",
                                  "Long-tenured clients sometimes question value — share a maturity/benefit summary.",
                                  "लंबी अवधि के क्लाइंट कभी-कभी मूल्य पर सवाल उठाते हैं — एक परिपक्वता/लाभ सारांश साझा करें।"),
    "old_policy_3yr":        (4,  "Policy over 3 years old",
                                  "3 वर्ष से पुरानी पॉलिसी",
                                  "Re-affirm benefits and any new riders available.",
                                  "लाभ और कोई नए राइडर्स उपलब्ध हों तो उनकी पुष्टि करें।"),
    "many_reminders_no_resp":(15, "3+ reminders sent without response",
                                  "3+ रिमाइंडर भेजे, कोई जवाब नहीं",
                                  "Stop reminders — switch to a personal phone call from the advisor.",
                                  "रिमाइंडर बंद करें — सलाहकार से व्यक्तिगत फोन कॉल पर स्विच करें।"),
    "missing_renewal_date":  (6,  "No renewal date on file",
                                  "फ़ाइल पर कोई नवीनीकरण तिथि नहीं",
                                  "Update the policy record with the correct renewal date.",
                                  "सही नवीनीकरण तिथि के साथ पॉलिसी रिकॉर्ड अपडेट करें।"),
    "lead_cold_source":      (5,  "Originally a cold lead (no warm introduction)",
                                  "मूल रूप से एक ठंडा लीड (कोई गर्म परिचय नहीं)",
                                  "Cold-source clients lapse 2× more — invest in personal touch.",
                                  "कोल्ड-सोर्स क्लाइंट 2× ज्यादा लैप्स होते हैं — व्यक्तिगत संपर्क में निवेश करें।"),
}


def _factor(code: str) -> dict[str, Any]:
    w, en, hi, ae, ah = _F[code]
    return {"code": code, "weight": w, "label_en": en, "label_hi": hi,
            "advice_en": ae, "advice_hi": ah}


# ---- core scoring -------------------------------------------------------
def compute_policy_risk(
    policy: dict,
    last_interaction_at: str | None,
    reminders_sent_30d: int,
    lead_source: str | None,
) -> dict:
    """Return {score, bucket, color, factors:[...]}.

    Pure function — easy to unit-test. All inputs come from the database
    layer; this function does no I/O.
    """
    factors: list[dict] = []
    today = date.today()

    # ---- Renewal-window factors --------------------------------------
    rdate = _parse_date(policy.get("renewal_date"))
    if not rdate:
        factors.append(_factor("missing_renewal_date"))
    else:
        delta = (rdate - today).days
        if delta < 0:
            factors.append(_factor("renewal_overdue"))
        elif delta <= 15:
            factors.append(_factor("renewal_within_15"))
        elif delta <= 45:
            factors.append(_factor("renewal_within_45"))

    # ---- Engagement-decay factors ------------------------------------
    li = _parse_date(last_interaction_at)
    if li:
        gap = (today - li).days
        if gap >= 180:
            factors.append(_factor("no_contact_180d"))
        elif gap >= 90:
            factors.append(_factor("no_contact_90d"))
    else:
        # Never interacted — treat as 180d gap
        factors.append(_factor("no_contact_180d"))

    # ---- Premium-mode factors ----------------------------------------
    mode = (policy.get("premium_mode") or "annual").lower()
    if mode in ("monthly", "month"):
        factors.append(_factor("monthly_premium_mode"))
    elif mode in ("quarterly", "quarter"):
        factors.append(_factor("quarterly_premium_mode"))

    # ---- Premium amount ----------------------------------------------
    prem = float(policy.get("premium") or 0)
    if prem >= 50000:
        factors.append(_factor("high_premium"))

    # ---- Policy age --------------------------------------------------
    sdate = _parse_date(policy.get("start_date"))
    if sdate:
        age_yrs = (today - sdate).days / 365.0
        if age_yrs >= 5:
            factors.append(_factor("old_policy_5yr"))
        elif age_yrs >= 3:
            factors.append(_factor("old_policy_3yr"))

    # ---- Reminder fatigue --------------------------------------------
    if reminders_sent_30d >= 3:
        factors.append(_factor("many_reminders_no_resp"))

    # ---- Cold-lead origin --------------------------------------------
    if lead_source and lead_source.lower() in ("cold", "purchased", "scraped", "unknown"):
        factors.append(_factor("lead_cold_source"))

    score = min(100, sum(f["weight"] for f in factors))
    bucket, color = _bucket(score)
    return {"score": score, "bucket": bucket, "color": color, "factors": factors}


# ---- DB queries ---------------------------------------------------------
async def _fetch_active_policies(tenant_id: int, days_ahead: int = 120) -> list[dict]:
    """Pull active policies for this tenant. Joins lead info."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            """
            SELECT p.policy_id, p.lead_id, p.agent_id, p.policy_number, p.insurer,
                   p.plan_name, p.policy_type, p.sum_insured, p.premium,
                   p.premium_mode, p.start_date, p.end_date, p.renewal_date,
                   p.status, p.commission, p.notes,
                   l.name AS lead_name, l.phone, l.source AS lead_source,
                   a.tenant_id
              FROM policies p
              JOIN leads l   ON l.lead_id   = p.lead_id
              JOIN agents a  ON a.agent_id  = p.agent_id
             WHERE a.tenant_id = ?
               AND COALESCE(p.status,'active') NOT IN ('lapsed','cancelled','surrendered')
            """,
            (tenant_id,),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return rows


async def _last_interaction(conn: aiosqlite.Connection, lead_id: int) -> str | None:
    async with conn.execute(
        "SELECT MAX(created_at) FROM interactions WHERE lead_id = ?",
        (lead_id,),
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def _reminders_30d(conn: aiosqlite.Connection, policy_id: int) -> int:
    async with conn.execute(
        """SELECT COUNT(*) FROM reminders
            WHERE policy_id = ?
              AND date(due_date) >= date('now','-30 days')""",
        (policy_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0


# ---- Public API ---------------------------------------------------------
async def get_at_risk_policies(
    tenant_id: int,
    days_ahead: int = 120,
    min_score: int = 25,
    limit: int = 200,
) -> list[dict]:
    """Return list of policies with risk >= min_score, sorted by score desc."""
    policies = await _fetch_active_policies(tenant_id, days_ahead)
    if not policies:
        return []
    out: list[dict] = []
    async with aiosqlite.connect(DB_PATH) as conn:
        for p in policies:
            try:
                li = await _last_interaction(conn, p["lead_id"])
                rcount = await _reminders_30d(conn, p["policy_id"])
                risk = compute_policy_risk(p, li, rcount, p.get("lead_source"))
                if risk["score"] < min_score:
                    continue
                out.append({
                    "policy_id":     p["policy_id"],
                    "lead_id":       p["lead_id"],
                    "lead_name":     p.get("lead_name") or "—",
                    "phone":         p.get("phone") or "",
                    "insurer":       p.get("insurer") or "",
                    "plan_name":     p.get("plan_name") or "",
                    "policy_type":   p.get("policy_type") or "",
                    "premium":       p.get("premium") or 0,
                    "premium_mode":  p.get("premium_mode") or "annual",
                    "renewal_date":  p.get("renewal_date"),
                    "last_interaction_at": li,
                    "score":         risk["score"],
                    "bucket":        risk["bucket"],
                    "color":         risk["color"],
                    "factors":       risk["factors"],
                })
            except Exception as e:
                logger.warning("risk calc failed for policy %s: %s", p.get("policy_id"), e)
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


async def get_policy_risk_detail(policy_id: int, tenant_id: int) -> dict | None:
    """Return single policy + risk breakdown, or None if not found / not owned."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            """SELECT p.*, l.name AS lead_name, l.phone, l.source AS lead_source
                 FROM policies p
                 JOIN leads  l ON l.lead_id = p.lead_id
                 JOIN agents a ON a.agent_id = p.agent_id
                WHERE p.policy_id = ? AND a.tenant_id = ?""",
            (policy_id, tenant_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        p = dict(row)
        li = await _last_interaction(conn, p["lead_id"])
        rc = await _reminders_30d(conn, p["policy_id"])
    risk = compute_policy_risk(p, li, rc, p.get("lead_source"))
    return {**p, "last_interaction_at": li, "reminders_30d": rc, **risk}


# ---- Summary for dashboard widget ---------------------------------------
async def get_risk_summary(tenant_id: int) -> dict:
    """Counts by bucket for dashboard overview cards."""
    rows = await get_at_risk_policies(tenant_id, days_ahead=180, min_score=0)
    buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for r in rows:
        buckets[r["bucket"]] = buckets.get(r["bucket"], 0) + 1
    return {"total": len(rows), **buckets}
