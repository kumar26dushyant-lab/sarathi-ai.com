"""
biz_quotes.py
=============
Multi-provider Quote Comparison Engine for Sarathi-AI.

Curates rate-card data for the top 8 insurers per product (term life, health),
estimates indicative premiums via standard actuarial formulas, and generates
branded comparison PDFs. Tenants may upload their own broker rate-cards
(PDF/Excel/CSV) to override the seed data.

NOTE on premium accuracy:
    Real insurers gate their live premium APIs behind broker partnerships.
    The premiums computed here are *indicative* — they use industry-standard
    base rates per ₹1000 sum-insured and the same age/smoker/sum-insured
    loading curves the insurers publish. Always disclaim "Indicative —
    final premium subject to underwriting" on the PDF.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import aiosqlite

logger = logging.getLogger("sarathi.quotes")

DB_PATH = "sarathi_biz.db"
RATECARD_DIR = "uploads/ratecards"

# =============================================================================
#  CURATED PROVIDER DATA (Top 8 per product)
#  - base_per_1k_si: base annual premium per ₹1000 sum insured (age 30, non-smoker)
#  - claim_ratio: latest IRDAI claim settlement ratio (FY24-25)
#  - features: dict of feature → value for comparison
# =============================================================================

TERM_PROVIDERS: list[dict] = [
    {
        "code": "hdfc_life",
        "name": "HDFC Life",
        "logo": "🟦",
        "base_per_1k_si": 0.85,
        "claim_ratio": 99.5,
        "features": {
            "max_cover_cr": 20,
            "max_age_entry": 65,
            "max_age_cover": 85,
            "riders": "Critical Illness, Accidental Death, Waiver of Premium",
            "online_discount_pct": 7,
            "claim_settlement_days": 7,
        },
    },
    {
        "code": "icici_pru",
        "name": "ICICI Prudential Life",
        "logo": "🟧",
        "base_per_1k_si": 0.88,
        "claim_ratio": 98.7,
        "features": {
            "max_cover_cr": 25,
            "max_age_entry": 65,
            "max_age_cover": 85,
            "riders": "Critical Illness, Accidental Death, Disability",
            "online_discount_pct": 8,
            "claim_settlement_days": 5,
        },
    },
    {
        "code": "sbi_life",
        "name": "SBI Life",
        "logo": "🟦",
        "base_per_1k_si": 0.82,
        "claim_ratio": 98.4,
        "features": {
            "max_cover_cr": 20,
            "max_age_entry": 65,
            "max_age_cover": 80,
            "riders": "Accidental Death, Critical Illness",
            "online_discount_pct": 6,
            "claim_settlement_days": 8,
        },
    },
    {
        "code": "max_life",
        "name": "Max Life",
        "logo": "🟪",
        "base_per_1k_si": 0.83,
        "claim_ratio": 99.3,
        "features": {
            "max_cover_cr": 20,
            "max_age_entry": 65,
            "max_age_cover": 85,
            "riders": "Critical Illness, Accidental Death, WoP",
            "online_discount_pct": 10,
            "claim_settlement_days": 6,
        },
    },
    {
        "code": "lic",
        "name": "LIC of India",
        "logo": "🟨",
        "base_per_1k_si": 1.05,
        "claim_ratio": 98.6,
        "features": {
            "max_cover_cr": 5,
            "max_age_entry": 65,
            "max_age_cover": 80,
            "riders": "Accidental Death, Disability",
            "online_discount_pct": 0,
            "claim_settlement_days": 14,
        },
    },
    {
        "code": "tata_aia",
        "name": "TATA AIA Life",
        "logo": "🟥",
        "base_per_1k_si": 0.81,
        "claim_ratio": 99.0,
        "features": {
            "max_cover_cr": 20,
            "max_age_entry": 65,
            "max_age_cover": 100,
            "riders": "Critical Illness, Accidental Death",
            "online_discount_pct": 8,
            "claim_settlement_days": 7,
        },
    },
    {
        "code": "bajaj_life",
        "name": "Bajaj Allianz Life",
        "logo": "🟩",
        "base_per_1k_si": 0.84,
        "claim_ratio": 98.5,
        "features": {
            "max_cover_cr": 20,
            "max_age_entry": 65,
            "max_age_cover": 85,
            "riders": "Critical Illness, Accidental Death",
            "online_discount_pct": 7,
            "claim_settlement_days": 8,
        },
    },
    {
        "code": "absli",
        "name": "Aditya Birla Sun Life",
        "logo": "🟫",
        "base_per_1k_si": 0.86,
        "claim_ratio": 98.1,
        "features": {
            "max_cover_cr": 15,
            "max_age_entry": 65,
            "max_age_cover": 85,
            "riders": "Critical Illness, Accidental Death",
            "online_discount_pct": 5,
            "claim_settlement_days": 9,
        },
    },
]

HEALTH_PROVIDERS: list[dict] = [
    {
        "code": "hdfc_ergo",
        "name": "HDFC ERGO",
        "logo": "🟦",
        "base_per_1k_si": 5.5,  # health is ~5x term per ₹1000 SI at age 30
        "claim_ratio": 96.5,
        "features": {
            "network_hospitals": 13000,
            "room_rent_cap": "Single AC",
            "copay_pct": 0,
            "waiting_period_pre_existing_yrs": 3,
            "restoration_benefit": "Yes (100%)",
            "no_claim_bonus_pct": 50,
            "pre_post_hospitalization_days": "60/180",
        },
    },
    {
        "code": "star_health",
        "name": "Star Health",
        "logo": "🟨",
        "base_per_1k_si": 5.2,
        "claim_ratio": 82.3,
        "features": {
            "network_hospitals": 14000,
            "room_rent_cap": "No limit",
            "copay_pct": 0,
            "waiting_period_pre_existing_yrs": 3,
            "restoration_benefit": "Yes (100%)",
            "no_claim_bonus_pct": 100,
            "pre_post_hospitalization_days": "60/90",
        },
    },
    {
        "code": "icici_lom",
        "name": "ICICI Lombard",
        "logo": "🟧",
        "base_per_1k_si": 5.8,
        "claim_ratio": 89.2,
        "features": {
            "network_hospitals": 7500,
            "room_rent_cap": "Single Private",
            "copay_pct": 0,
            "waiting_period_pre_existing_yrs": 2,
            "restoration_benefit": "Yes (unlimited)",
            "no_claim_bonus_pct": 50,
            "pre_post_hospitalization_days": "60/180",
        },
    },
    {
        "code": "niva_bupa",
        "name": "Niva Bupa",
        "logo": "🟩",
        "base_per_1k_si": 5.6,
        "claim_ratio": 91.4,
        "features": {
            "network_hospitals": 10000,
            "room_rent_cap": "No limit",
            "copay_pct": 0,
            "waiting_period_pre_existing_yrs": 3,
            "restoration_benefit": "Yes (unlimited)",
            "no_claim_bonus_pct": 50,
            "pre_post_hospitalization_days": "30/60",
        },
    },
    {
        "code": "care_health",
        "name": "Care Health (Religare)",
        "logo": "🟥",
        "base_per_1k_si": 5.0,
        "claim_ratio": 87.0,
        "features": {
            "network_hospitals": 21000,
            "room_rent_cap": "No limit",
            "copay_pct": 0,
            "waiting_period_pre_existing_yrs": 3,
            "restoration_benefit": "Yes (100%)",
            "no_claim_bonus_pct": 50,
            "pre_post_hospitalization_days": "30/60",
        },
    },
    {
        "code": "tata_aig",
        "name": "TATA AIG",
        "logo": "🟪",
        "base_per_1k_si": 5.7,
        "claim_ratio": 90.5,
        "features": {
            "network_hospitals": 7200,
            "room_rent_cap": "Single AC",
            "copay_pct": 0,
            "waiting_period_pre_existing_yrs": 3,
            "restoration_benefit": "Yes (100%)",
            "no_claim_bonus_pct": 50,
            "pre_post_hospitalization_days": "60/90",
        },
    },
    {
        "code": "abhi",
        "name": "Aditya Birla Health",
        "logo": "🟫",
        "base_per_1k_si": 5.4,
        "claim_ratio": 95.5,
        "features": {
            "network_hospitals": 11000,
            "room_rent_cap": "No limit",
            "copay_pct": 0,
            "waiting_period_pre_existing_yrs": 3,
            "restoration_benefit": "Yes (unlimited)",
            "no_claim_bonus_pct": 100,
            "pre_post_hospitalization_days": "60/180",
        },
    },
    {
        "code": "bajaj_gen",
        "name": "Bajaj Allianz General",
        "logo": "🟩",
        "base_per_1k_si": 5.3,
        "claim_ratio": 93.8,
        "features": {
            "network_hospitals": 8000,
            "room_rent_cap": "Single Private",
            "copay_pct": 0,
            "waiting_period_pre_existing_yrs": 3,
            "restoration_benefit": "Yes (100%)",
            "no_claim_bonus_pct": 50,
            "pre_post_hospitalization_days": "60/90",
        },
    },
]

# -----------------------------------------------------------------------------
# Endowment / Traditional Life (guaranteed savings + life cover)
# -----------------------------------------------------------------------------
ENDOWMENT_PROVIDERS: list[dict] = [
    {"code":"hdfc_sanchay","name":"HDFC Life Sanchay Plus","logo":"🟦","base_per_1k_si":18.0,"claim_ratio":99.5,
     "features":{"guaranteed_irr_pct":6.0,"policy_term_yrs":"10-40","ppt_yrs":"5/10/12","payout":"Lumpsum or Income","tax_benefit":"80C + 10(10D)"}},
    {"code":"icici_gift","name":"ICICI Pru GIFT Pro","logo":"🟧","base_per_1k_si":17.5,"claim_ratio":98.7,
     "features":{"guaranteed_irr_pct":6.2,"policy_term_yrs":"10-30","ppt_yrs":"5/7/10","payout":"Income for 30 yrs","tax_benefit":"80C + 10(10D)"}},
    {"code":"sbi_smart_bachat","name":"SBI Life Smart Bachat","logo":"🟦","base_per_1k_si":17.8,"claim_ratio":98.4,
     "features":{"guaranteed_irr_pct":5.8,"policy_term_yrs":"12-25","ppt_yrs":"7/10/15","payout":"Lumpsum at maturity","tax_benefit":"80C + 10(10D)"}},
    {"code":"max_smart_wealth","name":"Max Life Smart Wealth Plan","logo":"🟪","base_per_1k_si":17.6,"claim_ratio":99.3,
     "features":{"guaranteed_irr_pct":6.1,"policy_term_yrs":"5-67","ppt_yrs":"5/6/10/12","payout":"Lumpsum or Income","tax_benefit":"80C + 10(10D)"}},
    {"code":"lic_jeevan_anand","name":"LIC Jeevan Anand","logo":"🟨","base_per_1k_si":21.0,"claim_ratio":98.6,
     "features":{"guaranteed_irr_pct":5.2,"policy_term_yrs":"15-35","ppt_yrs":"Same as term","payout":"SA + Bonus + Whole Life cover","tax_benefit":"80C + 10(10D)"}},
    {"code":"tata_fortune_g","name":"TATA AIA Fortune Guarantee","logo":"🟥","base_per_1k_si":17.4,"claim_ratio":99.0,
     "features":{"guaranteed_irr_pct":6.3,"policy_term_yrs":"5-50","ppt_yrs":"5/7/10","payout":"Income for 30 yrs","tax_benefit":"80C + 10(10D)"}},
    {"code":"bajaj_guaranteed","name":"Bajaj Allianz Guaranteed Income Goal","logo":"🟩","base_per_1k_si":17.7,"claim_ratio":98.5,
     "features":{"guaranteed_irr_pct":6.0,"policy_term_yrs":"10-40","ppt_yrs":"5/8/10","payout":"Income for 25 yrs","tax_benefit":"80C + 10(10D)"}},
    {"code":"absli_assured","name":"ABSLI Assured Income Plus","logo":"🟫","base_per_1k_si":17.9,"claim_ratio":98.1,
     "features":{"guaranteed_irr_pct":5.9,"policy_term_yrs":"10-30","ppt_yrs":"6/8/10","payout":"Income or Lumpsum","tax_benefit":"80C + 10(10D)"}},
]

# -----------------------------------------------------------------------------
# ULIP (Unit Linked Insurance Plan — market-linked + life cover)
# -----------------------------------------------------------------------------
ULIP_PROVIDERS: list[dict] = [
    {"code":"hdfc_click2wealth","name":"HDFC Life Click 2 Wealth","logo":"🟦","base_per_1k_si":12.0,"claim_ratio":99.5,
     "features":{"premium_alloc_charge_pct":0,"fund_mgmt_charge_pct":1.35,"mortality_charge":"Returned at maturity","expected_5y_cagr_pct":11.5,"lock_in_yrs":5,"funds_count":11}},
    {"code":"icici_signature","name":"ICICI Pru Signature","logo":"🟧","base_per_1k_si":12.5,"claim_ratio":98.7,
     "features":{"premium_alloc_charge_pct":0,"fund_mgmt_charge_pct":1.35,"mortality_charge":"Returned at maturity","expected_5y_cagr_pct":12.0,"lock_in_yrs":5,"funds_count":15}},
    {"code":"sbi_ewealth","name":"SBI Life eWealth Insurance","logo":"🟦","base_per_1k_si":11.8,"claim_ratio":98.4,
     "features":{"premium_alloc_charge_pct":0,"fund_mgmt_charge_pct":1.35,"mortality_charge":"Standard","expected_5y_cagr_pct":10.8,"lock_in_yrs":5,"funds_count":7}},
    {"code":"max_online_savings","name":"Max Life Online Savings","logo":"🟪","base_per_1k_si":12.2,"claim_ratio":99.3,
     "features":{"premium_alloc_charge_pct":0,"fund_mgmt_charge_pct":1.25,"mortality_charge":"Returned at maturity","expected_5y_cagr_pct":11.8,"lock_in_yrs":5,"funds_count":10}},
    {"code":"lic_siip","name":"LIC SIIP","logo":"🟨","base_per_1k_si":13.5,"claim_ratio":98.6,
     "features":{"premium_alloc_charge_pct":3.3,"fund_mgmt_charge_pct":1.35,"mortality_charge":"Standard","expected_5y_cagr_pct":9.5,"lock_in_yrs":5,"funds_count":4}},
    {"code":"tata_fortune_pro","name":"TATA AIA Fortune Pro","logo":"🟥","base_per_1k_si":12.1,"claim_ratio":99.0,
     "features":{"premium_alloc_charge_pct":0,"fund_mgmt_charge_pct":1.35,"mortality_charge":"Returned at maturity","expected_5y_cagr_pct":12.5,"lock_in_yrs":5,"funds_count":13}},
    {"code":"bajaj_goal_assure","name":"Bajaj Allianz Goal Assure","logo":"🟩","base_per_1k_si":12.3,"claim_ratio":98.5,
     "features":{"premium_alloc_charge_pct":0,"fund_mgmt_charge_pct":1.35,"mortality_charge":"Returned at maturity","expected_5y_cagr_pct":11.6,"lock_in_yrs":5,"funds_count":8}},
    {"code":"absli_wealth_aspire","name":"ABSLI Wealth Aspire","logo":"🟫","base_per_1k_si":12.4,"claim_ratio":98.1,
     "features":{"premium_alloc_charge_pct":0,"fund_mgmt_charge_pct":1.35,"mortality_charge":"Standard","expected_5y_cagr_pct":11.2,"lock_in_yrs":5,"funds_count":16}},
]

# -----------------------------------------------------------------------------
# SIP / Mutual Fund (Equity — top large/flexi cap funds for SIP comparison)
# -----------------------------------------------------------------------------
SIP_PROVIDERS: list[dict] = [
    {"code":"hdfc_flexi_cap","name":"HDFC Flexi Cap Fund","logo":"🟦","claim_ratio":None,
     "features":{"category":"Flexi Cap","cagr_5y_pct":18.4,"cagr_10y_pct":15.2,"expense_ratio_pct":0.96,"aum_cr":68000,"risk":"Very High","rating":4}},
    {"code":"icici_bluechip","name":"ICICI Pru Bluechip Fund","logo":"🟧","claim_ratio":None,
     "features":{"category":"Large Cap","cagr_5y_pct":17.2,"cagr_10y_pct":14.1,"expense_ratio_pct":0.91,"aum_cr":63000,"risk":"Very High","rating":5}},
    {"code":"sbi_bluechip","name":"SBI Bluechip Fund","logo":"🟦","claim_ratio":None,
     "features":{"category":"Large Cap","cagr_5y_pct":16.5,"cagr_10y_pct":13.8,"expense_ratio_pct":0.79,"aum_cr":55000,"risk":"Very High","rating":4}},
    {"code":"axis_bluechip","name":"Axis Bluechip Fund","logo":"🟥","claim_ratio":None,
     "features":{"category":"Large Cap","cagr_5y_pct":14.8,"cagr_10y_pct":13.5,"expense_ratio_pct":0.62,"aum_cr":34000,"risk":"Very High","rating":4}},
    {"code":"nippon_largecap","name":"Nippon India Large Cap Fund","logo":"🟧","claim_ratio":None,
     "features":{"category":"Large Cap","cagr_5y_pct":19.1,"cagr_10y_pct":15.6,"expense_ratio_pct":0.84,"aum_cr":31000,"risk":"Very High","rating":5}},
    {"code":"absl_frontline","name":"Aditya Birla SL Frontline Equity","logo":"🟫","claim_ratio":None,
     "features":{"category":"Large Cap","cagr_5y_pct":15.9,"cagr_10y_pct":13.9,"expense_ratio_pct":1.03,"aum_cr":29000,"risk":"Very High","rating":3}},
    {"code":"kotak_equity","name":"Kotak Equity Opportunities","logo":"🟨","claim_ratio":None,
     "features":{"category":"Large & Mid","cagr_5y_pct":19.8,"cagr_10y_pct":15.4,"expense_ratio_pct":0.55,"aum_cr":24000,"risk":"Very High","rating":5}},
    {"code":"uti_nifty","name":"UTI Nifty 50 Index Fund","logo":"🟪","claim_ratio":None,
     "features":{"category":"Index","cagr_5y_pct":15.2,"cagr_10y_pct":13.1,"expense_ratio_pct":0.21,"aum_cr":18500,"risk":"Very High","rating":4}},
]


# =============================================================================
#  PREMIUM ENGINE
# =============================================================================

def _term_age_factor(age: int) -> float:
    """Indicative age multiplier curve for term life (base = age 30 = 1.0)."""
    if age < 25:   return 0.80
    if age < 30:   return 0.90
    if age < 35:   return 1.00
    if age < 40:   return 1.30
    if age < 45:   return 1.75
    if age < 50:   return 2.40
    if age < 55:   return 3.30
    if age < 60:   return 4.50
    return 6.00


def _health_age_factor(age: int) -> float:
    """Indicative age multiplier curve for health insurance (base = age 30 = 1.0)."""
    if age < 18:   return 0.55
    if age < 25:   return 0.75
    if age < 30:   return 0.90
    if age < 35:   return 1.00
    if age < 40:   return 1.20
    if age < 45:   return 1.45
    if age < 50:   return 1.85
    if age < 55:   return 2.40
    if age < 60:   return 3.10
    if age < 65:   return 4.00
    return 5.00


def estimate_term_premium(
    provider: dict,
    age: int,
    sum_insured: int,
    smoker: bool = False,
    gender: str = "M",
    term_years: int = 30,
) -> dict:
    """
    Indicative annual term-life premium.
    Returns: {annual_premium, monthly_premium, online_discount_applied, total_payable_term}
    """
    si_in_k = sum_insured / 1000.0
    base = provider["base_per_1k_si"] * si_in_k
    base *= _term_age_factor(age)
    if smoker:
        base *= 1.50
    if gender.upper() == "F":
        base *= 0.92  # standard female discount
    # Term length adjustment (longer = slightly higher annual)
    if term_years >= 30:
        base *= 1.05
    elif term_years <= 15:
        base *= 0.92
    # Online discount
    discount_pct = provider["features"].get("online_discount_pct", 0)
    discounted = base * (1 - discount_pct / 100.0)
    annual = round(discounted)
    return {
        "annual_premium": annual,
        "monthly_premium": round(annual / 12),
        "online_discount_applied_pct": discount_pct,
        "total_payable_term": annual * term_years,
    }


def estimate_health_premium(
    provider: dict,
    age: int,
    sum_insured: int,
    family_size: int = 1,
    city_tier: int = 1,
) -> dict:
    """
    Indicative annual health premium (individual or family floater).
    city_tier: 1 = Metro (highest), 2, 3 = lowest
    """
    si_in_k = sum_insured / 1000.0
    base = provider["base_per_1k_si"] * si_in_k
    base *= _health_age_factor(age)
    # City tier loading
    if city_tier == 1:
        base *= 1.15
    elif city_tier == 3:
        base *= 0.90
    # Family floater multiplier
    if family_size > 1:
        # 2 members ≈ 1.6x, 3 ≈ 2.0x, 4 ≈ 2.3x, 5+ ≈ 2.5x
        floater = {2: 1.6, 3: 2.0, 4: 2.3}.get(family_size, 2.5)
        base *= floater
    annual = round(base)
    return {
        "annual_premium": annual,
        "monthly_premium": round(annual / 12),
        "for_family_size": family_size,
    }


# =============================================================================
#  COMPARISON ENGINE
# =============================================================================

def _score_term(provider: dict, premium: dict) -> float:
    """Lower is better. Composite of price + claim ratio."""
    p = premium["annual_premium"]
    cr = provider["claim_ratio"]
    # Normalise: cheaper premium good, higher claim ratio good
    return p - (cr * 100)  # ₹100 saved is worth 1 pp claim ratio


def _score_health(provider: dict, premium: dict) -> float:
    p = premium["annual_premium"]
    cr = provider["claim_ratio"]
    return p - (cr * 100)


async def compare_term(
    age: int,
    sum_insured: int,
    smoker: bool = False,
    gender: str = "M",
    term_years: int = 30,
    tenant_id: int | None = None,
) -> list[dict]:
    """Returns ranked list of providers with premiums + features."""
    providers = await _get_active_providers("term", tenant_id)
    rows = []
    for prov in providers:
        prem = estimate_term_premium(prov, age, sum_insured, smoker, gender, term_years)
        rows.append({
            **prov,
            "premium": prem,
            "_score": _score_term(prov, prem),
        })
    rows.sort(key=lambda r: r["_score"])
    # Mark recommendation
    if rows:
        rows[0]["recommended"] = True
    return _attach_cols(rows, "term")


async def compare_health(
    age: int,
    sum_insured: int,
    family_size: int = 1,
    city_tier: int = 1,
    tenant_id: int | None = None,
) -> list[dict]:
    providers = await _get_active_providers("health", tenant_id)
    rows = []
    for prov in providers:
        prem = estimate_health_premium(prov, age, sum_insured, family_size, city_tier)
        rows.append({
            **prov,
            "premium": prem,
            "_score": _score_health(prov, prem),
        })
    rows.sort(key=lambda r: r["_score"])
    if rows:
        rows[0]["recommended"] = True
    return _attach_cols(rows, "health")


async def _get_active_providers(product_type: str, tenant_id: int | None) -> list[dict]:
    """Return seed providers, with tenant overrides applied if any."""
    seed_fn = _PRODUCT_PROVIDERS.get(product_type)
    seed = seed_fn() if seed_fn else (TERM_PROVIDERS if product_type == "term" else HEALTH_PROVIDERS)
    providers = [dict(p) for p in seed]  # deep-ish copy
    if tenant_id is None:
        return providers
    # Apply tenant overrides
    overrides = await get_tenant_ratecards(tenant_id, product_type)
    by_code = {p["code"]: p for p in providers}
    for ov in overrides:
        data = ov.get("parsed_data") or {}
        code = data.get("code") or ov.get("provider")
        if not code:
            continue
        if code in by_code:
            # Merge override (only non-empty fields)
            target = by_code[code]
            for k, v in data.items():
                if k == "features" and isinstance(v, dict):
                    target["features"].update({fk: fv for fk, fv in v.items() if fv not in (None, "")})
                elif v not in (None, ""):
                    target[k] = v
        else:
            # Brand-new provider added by tenant
            providers.append(data)
    return providers


# =============================================================================
#  RATE-CARD UPLOAD / PARSE / STORE
# =============================================================================

async def init_quotes_schema():
    """Create the provider_ratecards table if missing."""
    os.makedirs(RATECARD_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS provider_ratecards (
                ratecard_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id      INTEGER NOT NULL,
                provider       TEXT NOT NULL,
                product_type   TEXT NOT NULL,
                file_path      TEXT,
                file_type      TEXT,
                parsed_data    TEXT NOT NULL DEFAULT '{}',
                is_active      INTEGER NOT NULL DEFAULT 1,
                uploaded_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ratecards_tenant ON provider_ratecards(tenant_id, product_type, is_active)")
        await conn.commit()
    logger.info("✅ provider_ratecards schema ready")


def parse_ratecard_file(file_bytes: bytes, file_name: str) -> dict:
    """
    Best-effort parse of an uploaded rate-card file.
    Supports CSV, Excel (.xlsx/.xls), and PDF (text extract).
    Returns a dict that can be merged into a provider entry:
        {code?, name?, base_per_1k_si?, claim_ratio?, features: {...}}
    """
    fn = file_name.lower()
    text = ""
    rows: list[dict] = []
    try:
        if fn.endswith(".csv"):
            content = file_bytes.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(content))
            rows = [dict(r) for r in reader]
            text = content
        elif fn.endswith((".xlsx", ".xls")):
            try:
                import pandas as pd  # type: ignore
                df = pd.read_excel(io.BytesIO(file_bytes))
                rows = df.to_dict(orient="records")
                text = df.to_csv(index=False)
            except Exception as e:
                logger.warning("Excel parse failed, falling back to text: %s", e)
                text = file_bytes.decode("utf-8", errors="replace")
        elif fn.endswith(".pdf"):
            try:
                import pdfplumber  # type: ignore
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    text = "\n".join((page.extract_text() or "") for page in pdf.pages)
            except Exception as e:
                logger.warning("PDF parse failed: %s", e)
                text = ""
        else:
            text = file_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.error("parse_ratecard_file error: %s", e)

    return _extract_provider_fields(rows, text, file_name)


def _extract_provider_fields(rows: list[dict], text: str, file_name: str) -> dict:
    """Heuristic extraction of provider fields from parsed rows/text."""
    out: dict = {"features": {}}
    # If structured rows exist, look for common columns
    if rows:
        first = rows[0]
        keys_lower = {k.lower(): k for k in first.keys()}
        def get(*names):
            for n in names:
                if n in keys_lower:
                    return first.get(keys_lower[n])
            return None
        out["name"] = get("provider", "insurer", "company", "name")
        out["code"] = get("code", "provider_code")
        cr = get("claim_ratio", "claim_settlement_ratio", "csr")
        if cr is not None:
            try:
                out["claim_ratio"] = float(str(cr).replace("%", "").strip())
            except Exception:
                pass
        base = get("base_per_1k_si", "rate_per_1000", "premium_per_1000")
        if base is not None:
            try:
                out["base_per_1k_si"] = float(str(base).strip())
            except Exception:
                pass
        # Any other field becomes a feature
        for k, v in first.items():
            kl = k.lower()
            if kl in ("provider", "insurer", "company", "name", "code", "provider_code",
                     "claim_ratio", "claim_settlement_ratio", "csr",
                     "base_per_1k_si", "rate_per_1000", "premium_per_1000"):
                continue
            if v not in (None, ""):
                out["features"][k] = v
    # If no structured rows, just keep raw text snippet
    if not rows and text:
        out["features"]["raw_text_excerpt"] = text[:500]
    if not out.get("name"):
        # Use file-name as fallback name (strip extension)
        out["name"] = os.path.splitext(os.path.basename(file_name))[0]
    if not out.get("code"):
        out["code"] = (out["name"] or "custom").lower().replace(" ", "_")[:32]
    return out


async def save_ratecard(
    tenant_id: int,
    provider: str,
    product_type: str,
    file_bytes: bytes,
    file_name: str,
) -> dict:
    """Persist rate-card file + parsed metadata. Returns the row dict."""
    await init_quotes_schema()
    os.makedirs(RATECARD_DIR, exist_ok=True)
    timestamp = int(time.time())
    safe_name = "".join(c for c in file_name if c.isalnum() or c in "._-")
    file_path = os.path.join(RATECARD_DIR, f"t{tenant_id}_{timestamp}_{safe_name}")
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    parsed = parse_ratecard_file(file_bytes, file_name)
    parsed_json = json.dumps(parsed, default=str)
    file_type = os.path.splitext(file_name)[1].lstrip(".").lower() or "unknown"
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO provider_ratecards
               (tenant_id, provider, product_type, file_path, file_type, parsed_data, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (tenant_id, provider, product_type, file_path, file_type, parsed_json),
        )
        await conn.commit()
        rid = cursor.lastrowid
    return {
        "ratecard_id": rid,
        "tenant_id": tenant_id,
        "provider": provider,
        "product_type": product_type,
        "file_path": file_path,
        "file_type": file_type,
        "parsed_data": parsed,
    }


async def get_tenant_ratecards(tenant_id: int, product_type: str | None = None) -> list[dict]:
    await init_quotes_schema()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if product_type:
            cursor = await conn.execute(
                """SELECT * FROM provider_ratecards
                   WHERE tenant_id=? AND product_type=? AND is_active=1
                   ORDER BY uploaded_at DESC""",
                (tenant_id, product_type),
            )
        else:
            cursor = await conn.execute(
                """SELECT * FROM provider_ratecards
                   WHERE tenant_id=? AND is_active=1
                   ORDER BY uploaded_at DESC""",
                (tenant_id,),
            )
        rows = await cursor.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["parsed_data"] = json.loads(d["parsed_data"] or "{}")
        except Exception:
            d["parsed_data"] = {}
        out.append(d)
    return out


async def delete_ratecard(tenant_id: int, ratecard_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "UPDATE provider_ratecards SET is_active=0 WHERE ratecard_id=? AND tenant_id=?",
            (ratecard_id, tenant_id),
        )
        await conn.commit()
        return cursor.rowcount > 0


# =============================================================================
#  HTML / PDF GENERATION
# =============================================================================

_LABELS = {
    "title": {"en": "Insurance Quote Comparison", "hi": "बीमा कोटेशन तुलना"},
    "prepared_for": {"en": "Prepared for", "hi": "के लिए तैयार"},
    "prepared_by": {"en": "Prepared by", "hi": "द्वारा तैयार"},
    "date": {"en": "Date", "hi": "तारीख"},
    "product": {"en": "Product", "hi": "उत्पाद"},
    "term_life": {"en": "Term Life Insurance", "hi": "टर्म जीवन बीमा"},
    "health_ins": {"en": "Health Insurance", "hi": "स्वास्थ्य बीमा"},
    "client_age": {"en": "Client Age", "hi": "ग्राहक की आयु"},
    "sum_insured": {"en": "Sum Insured", "hi": "बीमित राशि"},
    "term_yrs": {"en": "Policy Term (Years)", "hi": "पॉलिसी अवधि (वर्ष)"},
    "smoker": {"en": "Smoker", "hi": "धूम्रपान करने वाला"},
    "yes": {"en": "Yes", "hi": "हाँ"},
    "no": {"en": "No", "hi": "नहीं"},
    "family_size": {"en": "Family Members Covered", "hi": "कवर किए गए परिवार के सदस्य"},
    "city_tier": {"en": "City Tier", "hi": "शहर श्रेणी"},
    "rank": {"en": "Rank", "hi": "रैंक"},
    "insurer": {"en": "Insurer", "hi": "बीमाकर्ता"},
    "annual": {"en": "Annual Premium (₹)", "hi": "वार्षिक प्रीमियम (₹)"},
    "monthly": {"en": "Monthly (₹)", "hi": "मासिक (₹)"},
    "claim_ratio": {"en": "Claim Settlement %", "hi": "दावा निपटान %"},
    "key_features": {"en": "Key Features", "hi": "मुख्य विशेषताएं"},
    "recommended": {"en": "RECOMMENDED", "hi": "अनुशंसित"},
    "disclaimer": {
        "en": "Premiums shown are indicative and based on standard rate cards. Final premium is subject to underwriting, medical tests, and IRDAI approval. This document is for informational purposes only and does not constitute an insurance offer.",
        "hi": "दिखाए गए प्रीमियम सांकेतिक हैं और मानक दर कार्ड पर आधारित हैं। अंतिम प्रीमियम अंडरराइटिंग, चिकित्सा परीक्षण और IRDAI अनुमोदन के अधीन है। यह दस्तावेज़ केवल जानकारी के लिए है और बीमा प्रस्ताव नहीं है।",
    },
}


def _t(key: str, lang: str) -> str:
    return _LABELS.get(key, {}).get(lang) or _LABELS.get(key, {}).get("en") or key


def generate_comparison_html(
    rows: list[dict],
    product_type: str,
    inputs: dict,
    client_name: str = "Client",
    advisor_name: str = "Advisor",
    firm_name: str = "Sarathi-AI CRM",
    brand: dict | None = None,
    lang: str = "en",
) -> str:
    """Build a branded comparison HTML report."""
    b = brand or {}
    primary = b.get("primary_color") or "#1a56db"
    accent = b.get("accent_color") or "#ea580c"
    logo = b.get("logo") or ""
    cta = b.get("cta") or "Grow Your Advisory Business"
    irdai = b.get("irdai_license") or ""

    product_label = _t("term_life" if product_type == "term" else "health_ins", lang)
    today = time.strftime("%d %b %Y")

    # Inputs panel
    inputs_html_parts = [f'<div><b>{_t("product", lang)}:</b> {product_label}</div>']
    inputs_html_parts.append(f'<div><b>{_t("client_age", lang)}:</b> {inputs.get("age", "—")}</div>')
    si = inputs.get("sum_insured", 0)
    inputs_html_parts.append(f'<div><b>{_t("sum_insured", lang)}:</b> ₹{si:,}</div>')
    if product_type == "term":
        inputs_html_parts.append(f'<div><b>{_t("term_yrs", lang)}:</b> {inputs.get("term_years", 30)}</div>')
        smoker = inputs.get("smoker", False)
        inputs_html_parts.append(f'<div><b>{_t("smoker", lang)}:</b> {_t("yes" if smoker else "no", lang)}</div>')
    else:
        inputs_html_parts.append(f'<div><b>{_t("family_size", lang)}:</b> {inputs.get("family_size", 1)}</div>')
        inputs_html_parts.append(f'<div><b>{_t("city_tier", lang)}:</b> {inputs.get("city_tier", 1)}</div>')

    # Comparison table rows
    table_rows = []
    for i, r in enumerate(rows, start=1):
        is_rec = r.get("recommended")
        row_bg = f"background:linear-gradient(90deg,{primary}15,#fff);border-left:4px solid {accent};" if is_rec else ""
        rec_badge = f'<span style="background:{accent};color:white;padding:2px 8px;border-radius:6px;font-size:0.7em;font-weight:700;margin-left:6px">{_t("recommended", lang)}</span>' if is_rec else ""
        feat_lines = []
        for k, v in (r.get("features") or {}).items():
            if k == "raw_text_excerpt":
                continue
            label = k.replace("_", " ").title()
            feat_lines.append(f"<div style='font-size:0.78em;color:#555'>• {label}: <b>{v}</b></div>")
        feats_html = "".join(feat_lines[:6])  # cap at 6 features per row
        prem = r["premium"]
        table_rows.append(f"""
        <tr style="{row_bg}">
            <td style="padding:14px 10px;text-align:center;font-weight:700;color:{primary};font-size:1.1em">#{i}</td>
            <td style="padding:14px 10px"><div style="font-weight:700;font-size:1.05em">{r.get('logo','')} {r['name']}{rec_badge}</div></td>
            <td style="padding:14px 10px;text-align:right;font-weight:700;color:{primary};font-size:1.1em">₹{prem['annual_premium']:,}</td>
            <td style="padding:14px 10px;text-align:right;color:#555">₹{prem['monthly_premium']:,}</td>
            <td style="padding:14px 10px;text-align:center"><b style="color:#16a34a">{r.get('claim_ratio','—')}%</b></td>
            <td style="padding:14px 10px">{feats_html}</td>
        </tr>
        """)

    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<title>{_t('title', lang)} — {client_name}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Poppins',sans-serif;color:#222;background:#fff;padding:40px}}
.firm-banner{{display:flex;align-items:center;gap:16px;padding:16px 24px;margin-bottom:20px;border-bottom:3px solid {primary}}}
.firm-logo{{width:64px;height:64px;object-fit:contain;border-radius:8px}}
.firm-name{{font-size:20px;font-weight:700;color:{primary}}}
.firm-cta{{font-size:13px;color:#666;margin-top:2px}}
h1{{color:{primary};font-size:26px;margin-bottom:6px}}
.meta{{color:#666;font-size:13px;margin-bottom:20px}}
.inputs{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px 24px;background:#f8fafc;padding:16px 20px;border-radius:10px;margin-bottom:24px;font-size:14px}}
table{{width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}}
th{{background:{primary};color:white;padding:12px 10px;text-align:left;font-size:13px;font-weight:600}}
tr{{border-bottom:1px solid #f1f5f9}}
.disclaimer{{margin-top:24px;padding:14px 18px;background:#fffbeb;border-left:4px solid {accent};font-size:12px;color:#78350f;border-radius:6px}}
.footer{{margin-top:30px;text-align:center;color:#888;font-size:11px;border-top:1px solid #eee;padding-top:14px}}
@media print{{body{{padding:20px}}}}
</style>
</head>
<body>
<div class="firm-banner">
  {f'<img class="firm-logo" src="{logo}" alt="logo">' if logo else f'<div class="firm-logo" style="background:{primary};color:white;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700">{(firm_name or "S")[0].upper()}</div>'}
  <div style="flex:1">
    <div class="firm-name">{firm_name}</div>
    <div class="firm-cta">{cta}</div>
    {f'<div style="font-size:11px;color:#888;margin-top:2px">IRDAI Reg: {irdai}</div>' if irdai else ''}
  </div>
</div>

<h1>{_t('title', lang)}</h1>
<div class="meta">
  <b>{_t('prepared_for', lang)}:</b> {client_name} &nbsp;•&nbsp;
  <b>{_t('prepared_by', lang)}:</b> {advisor_name} &nbsp;•&nbsp;
  <b>{_t('date', lang)}:</b> {today}
</div>

<div class="inputs">{''.join(inputs_html_parts)}</div>

<table>
<thead><tr>
  <th style="text-align:center">{_t('rank', lang)}</th>
  <th>{_t('insurer', lang)}</th>
  <th style="text-align:right">{_t('annual', lang)}</th>
  <th style="text-align:right">{_t('monthly', lang)}</th>
  <th style="text-align:center">{_t('claim_ratio', lang)}</th>
  <th>{_t('key_features', lang)}</th>
</tr></thead>
<tbody>
{''.join(table_rows)}
</tbody>
</table>

<div class="disclaimer"><b>⚠️ {_t('disclaimer', lang)[:30] if lang=='en' else 'अस्वीकरण'}:</b> {_t('disclaimer', lang)}</div>

<div class="footer">
  Generated by Sarathi-AI · {today} · {firm_name}
</div>
</body></html>
"""
    return html


# =============================================================================
#  EXTENDED PRODUCTS (Endowment / ULIP / SIP) + GENERIC COLS METADATA
#  Added 2026-04-23 — adds clear column headings + tooltips for all products.
# =============================================================================

# Map of product_type → seed providers list
_PRODUCT_PROVIDERS = {
    "term":      lambda: TERM_PROVIDERS,
    "health":    lambda: HEALTH_PROVIDERS,
    "endowment": lambda: ENDOWMENT_PROVIDERS,
    "ulip":      lambda: ULIP_PROVIDERS,
    "sip":       lambda: SIP_PROVIDERS,
}

# ---- estimators ----
def estimate_endowment_premium(provider: dict, age: int, sum_insured: int, term_years: int = 20) -> dict:
    """Indicative endowment annual premium. Rate per ₹1000 SI scaled by age + term."""
    si_in_k = sum_insured / 1000.0
    base = provider["base_per_1k_si"] * si_in_k
    age_mult = 1.0 + max(0, age - 30) * 0.025  # ~2.5%/yr above 30
    base *= age_mult
    if term_years <= 10: base *= 1.4
    elif term_years <= 15: base *= 1.15
    elif term_years >= 30: base *= 0.92
    annual = round(base)
    irr = float(provider["features"].get("guaranteed_irr_pct", 6.0))
    # rough projected maturity: PV grown at IRR for term_years
    maturity = round(annual * term_years * ((1 + irr/100) ** (term_years/2)))
    return {"annual_premium": annual, "monthly_premium": round(annual/12),
            "guaranteed_irr_pct": irr, "projected_maturity": maturity, "term_years": term_years}


def estimate_ulip_premium(provider: dict, age: int, annual_investment: int, term_years: int = 15) -> dict:
    """Indicative ULIP. annual_investment IS the premium chosen by client. Compute charges + projected fund value."""
    feats = provider["features"]
    alloc = float(feats.get("premium_alloc_charge_pct", 0))
    fmc = float(feats.get("fund_mgmt_charge_pct", 1.35))
    cagr = float(feats.get("expected_5y_cagr_pct", 11.0))
    # Net invested per year after allocation charge
    net = annual_investment * (1 - alloc/100)
    # Compound at (cagr - fmc) for term, summing each year's contribution
    eff = max(0.0, (cagr - fmc) / 100.0)
    fund_value = 0.0
    for y in range(term_years):
        fund_value = (fund_value + net) * (1 + eff)
    fund_value = round(fund_value)
    total_paid = annual_investment * term_years
    sum_assured = annual_investment * 10  # standard 10x SA for tax benefit
    return {"annual_premium": annual_investment, "monthly_premium": round(annual_investment/12),
            "projected_fund_value": fund_value, "total_invested": total_paid,
            "sum_assured": sum_assured, "expected_cagr_pct": cagr,
            "fund_mgmt_charge_pct": fmc, "term_years": term_years}


def estimate_sip_projection(provider: dict, monthly_sip: int, years: int = 10) -> dict:
    """Project SIP value at fund's historical 5Y CAGR (illustrative)."""
    feats = provider["features"]
    cagr = float(feats.get("cagr_5y_pct", 12.0))
    er = float(feats.get("expense_ratio_pct", 1.0))
    # Net return = CAGR - expense ratio
    r = max(0.0, (cagr - er) / 100.0) / 12.0  # monthly rate
    n = years * 12
    if r > 0:
        fv = monthly_sip * (((1 + r) ** n - 1) / r) * (1 + r)
    else:
        fv = monthly_sip * n
    fv = round(fv)
    invested = monthly_sip * n
    return {"monthly_sip": monthly_sip, "years": years, "total_invested": invested,
            "projected_value": fv, "wealth_gain": fv - invested,
            "net_cagr_pct": round(cagr - er, 2), "expense_ratio_pct": er}


# ---- cols metadata (clear headings + tooltips, bilingual) ----
def _money(v): return f"₹{int(v):,}"

def _term_cols(row: dict) -> list[dict]:
    p = row["premium"]; f = row.get("features", {})
    return [
        {"key":"annual","label_en":"Annual Premium","label_hi":"वार्षिक प्रीमियम","value":_money(p["annual_premium"]),"tip_en":"Total amount you pay each year for this term cover","tip_hi":"इस टर्म कवर के लिए हर साल चुकाई जाने वाली कुल राशि","align":"right","highlight":True},
        {"key":"monthly","label_en":"Monthly Equiv.","label_hi":"मासिक समतुल्य","value":_money(p["monthly_premium"]),"tip_en":"Annual premium ÷ 12","tip_hi":"वार्षिक प्रीमियम ÷ 12","align":"right"},
        {"key":"csr","label_en":"Claim Settlement Ratio","label_hi":"दावा निपटान अनुपात","value":f"{row.get('claim_ratio','—')}%","tip_en":"% of death claims paid by insurer last year (IRDAI). Higher is safer.","tip_hi":"पिछले वर्ष भुगतान किए गए मृत्यु दावों का % (IRDAI)। अधिक सुरक्षित है।","align":"center","good":"high"},
        {"key":"max_cover","label_en":"Max Cover","label_hi":"अधिकतम कवर","value":f"₹{f.get('max_cover_cr','—')} Cr","tip_en":"Maximum sum assured this insurer offers","tip_hi":"इस बीमाकर्ता द्वारा दी जाने वाली अधिकतम बीमा राशि","align":"center"},
        {"key":"online_disc","label_en":"Online Discount","label_hi":"ऑनलाइन छूट","value":f"{p['online_discount_applied_pct']}%","tip_en":"Discount applied for online purchase (already in shown premium)","tip_hi":"ऑनलाइन खरीद पर छूट (पहले से दिखाए गए प्रीमियम में)","align":"center"},
        {"key":"riders","label_en":"Available Riders","label_hi":"उपलब्ध राइडर्स","value":str(f.get("riders","—")),"tip_en":"Optional add-ons like critical illness, accidental death","tip_hi":"वैकल्पिक ऐड-ऑन जैसे गंभीर बीमारी, दुर्घटना मृत्यु"},
    ]

def _health_cols(row: dict) -> list[dict]:
    p = row["premium"]; f = row.get("features", {})
    return [
        {"key":"annual","label_en":"Annual Premium","label_hi":"वार्षिक प्रीमियम","value":_money(p["annual_premium"]),"tip_en":"Yearly premium for this health plan","tip_hi":"इस स्वास्थ्य योजना के लिए वार्षिक प्रीमियम","align":"right","highlight":True},
        {"key":"monthly","label_en":"Monthly Equiv.","label_hi":"मासिक समतुल्य","value":_money(p["monthly_premium"]),"tip_en":"Annual premium ÷ 12","tip_hi":"वार्षिक प्रीमियम ÷ 12","align":"right"},
        {"key":"csr","label_en":"Claim Settlement Ratio","label_hi":"दावा निपटान अनुपात","value":f"{row.get('claim_ratio','—')}%","tip_en":"% of health claims paid last year (IRDAI). Higher is safer.","tip_hi":"पिछले वर्ष भुगतान किए गए स्वास्थ्य दावों का % (IRDAI)।","align":"center","good":"high"},
        {"key":"network","label_en":"Network Hospitals","label_hi":"नेटवर्क अस्पताल","value":f"{f.get('network_hospitals','—'):,}" if isinstance(f.get('network_hospitals'),int) else str(f.get('network_hospitals','—')),"tip_en":"Cashless treatment available at these hospitals","tip_hi":"इन अस्पतालों में कैशलेस उपचार उपलब्ध","align":"center"},
        {"key":"room","label_en":"Room Rent Cap","label_hi":"कमरे के किराए की सीमा","value":str(f.get("room_rent_cap","—")),"tip_en":"Room category covered without sub-limits","tip_hi":"उप-सीमा के बिना कवर की गई कमरे की श्रेणी","align":"center"},
        {"key":"copay","label_en":"Co-pay","label_hi":"सह-भुगतान","value":f"{f.get('copay_pct',0)}%","tip_en":"% of every claim YOU pay (lower is better)","tip_hi":"हर दावे का % जो आप भरते हैं (कम बेहतर)","align":"center","good":"low"},
        {"key":"pre_ex","label_en":"Pre-existing Wait","label_hi":"पूर्व-मौजूदा प्रतीक्षा","value":f"{f.get('waiting_period_pre_existing_yrs','—')} yrs","tip_en":"Years before pre-existing diseases get covered","tip_hi":"पूर्व-मौजूदा बीमारियाँ कवर होने से पहले के वर्ष","align":"center","good":"low"},
        {"key":"restoration","label_en":"Restoration","label_hi":"पुनर्स्थापना","value":str(f.get("restoration_benefit","—")),"tip_en":"If you exhaust your cover, it gets refilled","tip_hi":"यदि आपका कवर समाप्त हो जाए, तो वह फिर से भर जाता है","align":"center"},
        {"key":"ncb","label_en":"No-Claim Bonus","label_hi":"नो-क्लेम बोनस","value":f"{f.get('no_claim_bonus_pct',0)}%/yr","tip_en":"% increase in cover for each claim-free year","tip_hi":"हर दावा-रहित वर्ष पर कवर में वृद्धि का %","align":"center","good":"high"},
    ]

def _endowment_cols(row: dict) -> list[dict]:
    p = row["premium"]; f = row.get("features", {})
    return [
        {"key":"annual","label_en":"Annual Premium","label_hi":"वार्षिक प्रीमियम","value":_money(p["annual_premium"]),"tip_en":"Yearly premium you pay","tip_hi":"वार्षिक प्रीमियम","align":"right","highlight":True},
        {"key":"irr","label_en":"Guaranteed IRR","label_hi":"गारंटीड IRR","value":f"{p['guaranteed_irr_pct']}%","tip_en":"Internal Rate of Return — your guaranteed yield. Higher is better.","tip_hi":"आंतरिक प्रतिफल दर — आपकी गारंटीड उपज। अधिक बेहतर।","align":"center","good":"high"},
        {"key":"maturity","label_en":"Projected Maturity","label_hi":"अनुमानित परिपक्वता","value":_money(p["projected_maturity"]),"tip_en":"Estimated lump-sum at end of policy term","tip_hi":"पॉलिसी अवधि के अंत में अनुमानित एकमुश्त राशि","align":"right","highlight":True},
        {"key":"csr","label_en":"Claim Settlement Ratio","label_hi":"दावा निपटान अनुपात","value":f"{row.get('claim_ratio','—')}%","tip_en":"IRDAI death-claim settlement %","tip_hi":"IRDAI मृत्यु-दावा निपटान %","align":"center","good":"high"},
        {"key":"term","label_en":"Policy Term","label_hi":"पॉलिसी अवधि","value":str(f.get("policy_term_yrs","—")),"tip_en":"Available policy term range","tip_hi":"उपलब्ध पॉलिसी अवधि सीमा","align":"center"},
        {"key":"ppt","label_en":"Premium Pay Term","label_hi":"प्रीमियम भुगतान अवधि","value":str(f.get("ppt_yrs","—")),"tip_en":"Years for which you pay premiums","tip_hi":"जितने वर्ष आप प्रीमियम भरते हैं","align":"center"},
        {"key":"payout","label_en":"Payout Mode","label_hi":"भुगतान विधि","value":str(f.get("payout","—")),"tip_en":"How maturity benefit is paid (lumpsum or income)","tip_hi":"परिपक्वता लाभ कैसे मिलता है (एकमुश्त या आय)","align":"center"},
        {"key":"tax","label_en":"Tax Benefit","label_hi":"कर लाभ","value":str(f.get("tax_benefit","—")),"tip_en":"Income Tax sections applicable","tip_hi":"लागू आयकर धाराएं","align":"center"},
    ]

def _ulip_cols(row: dict) -> list[dict]:
    p = row["premium"]; f = row.get("features", {})
    return [
        {"key":"annual","label_en":"Annual Investment","label_hi":"वार्षिक निवेश","value":_money(p["annual_premium"]),"tip_en":"Premium you invest each year","tip_hi":"हर साल जो प्रीमियम आप निवेश करते हैं","align":"right"},
        {"key":"sa","label_en":"Life Cover (SA)","label_hi":"जीवन कवर","value":_money(p["sum_assured"]),"tip_en":"Sum assured (life cover) included with the investment","tip_hi":"निवेश के साथ शामिल बीमित राशि (जीवन कवर)","align":"right"},
        {"key":"alloc","label_en":"Allocation Charge","label_hi":"आवंटन शुल्क","value":f"{f.get('premium_alloc_charge_pct',0)}%","tip_en":"% of premium deducted before investing (lower is better)","tip_hi":"निवेश से पहले काटा गया प्रीमियम का % (कम बेहतर)","align":"center","good":"low"},
        {"key":"fmc","label_en":"Fund Mgmt Charge","label_hi":"फंड प्रबंधन शुल्क","value":f"{p['fund_mgmt_charge_pct']}%/yr","tip_en":"Annual fund management fee (lower is better)","tip_hi":"वार्षिक फंड प्रबंधन शुल्क (कम बेहतर)","align":"center","good":"low"},
        {"key":"cagr","label_en":"Expected 5Y CAGR","label_hi":"अनुमानित 5Y CAGR","value":f"{p['expected_cagr_pct']}%","tip_en":"Indicative annualised return (past 5 years, illustrative)","tip_hi":"सांकेतिक वार्षिक प्रतिफल (पिछले 5 वर्ष, उदाहरण)","align":"center","good":"high"},
        {"key":"fund_value","label_en":"Projected Fund Value","label_hi":"अनुमानित फंड मूल्य","value":_money(p["projected_fund_value"]),"tip_en":f"Estimated value after {p['term_years']} years at expected CAGR","tip_hi":f"{p['term_years']} वर्ष बाद अनुमानित मूल्य","align":"right","highlight":True},
        {"key":"funds","label_en":"Funds Available","label_hi":"उपलब्ध फंड","value":str(f.get("funds_count","—")),"tip_en":"Number of fund options to switch between","tip_hi":"स्विच के लिए उपलब्ध फंड विकल्पों की संख्या","align":"center"},
    ]

def _sip_cols(row: dict) -> list[dict]:
    p = row["premium"]; f = row.get("features", {})
    return [
        {"key":"category","label_en":"Category","label_hi":"श्रेणी","value":str(f.get("category","—")),"tip_en":"Fund category (Large/Mid/Flexi/Index etc.)","tip_hi":"फंड श्रेणी","align":"center"},
        {"key":"sip","label_en":"Monthly SIP","label_hi":"मासिक SIP","value":_money(p["monthly_sip"]),"tip_en":"Amount invested every month","tip_hi":"हर महीने निवेश की गई राशि","align":"right"},
        {"key":"5y","label_en":"5Y CAGR","label_hi":"5 वर्ष CAGR","value":f"{f.get('cagr_5y_pct','—')}%","tip_en":"Annualised return over the last 5 years","tip_hi":"पिछले 5 वर्षों का वार्षिक प्रतिफल","align":"center","good":"high"},
        {"key":"10y","label_en":"10Y CAGR","label_hi":"10 वर्ष CAGR","value":f"{f.get('cagr_10y_pct','—')}%","tip_en":"Annualised return over the last 10 years","tip_hi":"पिछले 10 वर्षों का वार्षिक प्रतिफल","align":"center","good":"high"},
        {"key":"er","label_en":"Expense Ratio","label_hi":"व्यय अनुपात","value":f"{p['expense_ratio_pct']}%","tip_en":"Annual fee charged by the AMC (lower is better)","tip_hi":"AMC द्वारा लिया गया वार्षिक शुल्क (कम बेहतर)","align":"center","good":"low"},
        {"key":"projected","label_en":"Projected Value","label_hi":"अनुमानित मूल्य","value":_money(p["projected_value"]),"tip_en":f"Estimated value after {p['years']} years (illustrative)","tip_hi":f"{p['years']} वर्ष बाद अनुमानित मूल्य","align":"right","highlight":True},
        {"key":"gain","label_en":"Wealth Gain","label_hi":"धन लाभ","value":_money(p["wealth_gain"]),"tip_en":"Projected value − total invested","tip_hi":"अनुमानित मूल्य − कुल निवेश","align":"right","good":"high"},
        {"key":"aum","label_en":"AUM","label_hi":"AUM","value":f"₹{f.get('aum_cr','—'):,} Cr" if isinstance(f.get('aum_cr'),int) else "—","tip_en":"Assets Under Management (size of the fund)","tip_hi":"प्रबंधन के तहत संपत्ति (फंड का आकार)","align":"center"},
        {"key":"risk","label_en":"Risk","label_hi":"जोखिम","value":str(f.get("risk","—")),"tip_en":"Riskometer reading (Equity = Very High)","tip_hi":"जोखिम मीटर (इक्विटी = बहुत अधिक)","align":"center"},
        {"key":"rating","label_en":"Rating","label_hi":"रेटिंग","value":"⭐"*int(f.get("rating",0) or 0) or "—","tip_en":"Independent fund rating (out of 5)","tip_hi":"स्वतंत्र फंड रेटिंग (5 में से)","align":"center","good":"high"},
    ]

_COLS_FN = {"term": _term_cols, "health": _health_cols, "endowment": _endowment_cols, "ulip": _ulip_cols, "sip": _sip_cols}

def _attach_cols(rows: list[dict], product_type: str) -> list[dict]:
    fn = _COLS_FN.get(product_type)
    if not fn:
        return rows
    for r in rows:
        try:
            r["cols"] = fn(r)
        except Exception as e:
            logger.warning("attach cols failed for %s: %s", product_type, e)
            r["cols"] = []
    return rows


# ---- new compare functions for endowment / ulip / sip ----
async def compare_endowment(age: int, sum_insured: int, term_years: int = 20, tenant_id: int | None = None) -> list[dict]:
    providers = await _get_active_providers("endowment", tenant_id)
    rows = []
    for prov in providers:
        prem = estimate_endowment_premium(prov, age, sum_insured, term_years)
        # Score: prefer higher IRR, lower premium
        score = -prem["guaranteed_irr_pct"] * 1000 + prem["annual_premium"] / 100
        rows.append({**prov, "premium": prem, "_score": score})
    rows.sort(key=lambda r: r["_score"])
    if rows:
        rows[0]["recommended"] = True
    return _attach_cols(rows, "endowment")


async def compare_ulip(age: int, annual_investment: int, term_years: int = 15, tenant_id: int | None = None) -> list[dict]:
    providers = await _get_active_providers("ulip", tenant_id)
    rows = []
    for prov in providers:
        prem = estimate_ulip_premium(prov, age, annual_investment, term_years)
        # Score: prefer higher projected fund value
        score = -prem["projected_fund_value"]
        rows.append({**prov, "premium": prem, "_score": score})
    rows.sort(key=lambda r: r["_score"])
    if rows:
        rows[0]["recommended"] = True
    return _attach_cols(rows, "ulip")


async def compare_sip(monthly_sip: int, years: int = 10, tenant_id: int | None = None) -> list[dict]:
    providers = await _get_active_providers("sip", tenant_id)
    rows = []
    for prov in providers:
        prem = estimate_sip_projection(prov, monthly_sip, years)
        # Score: prefer higher projected value
        score = -prem["projected_value"]
        rows.append({**prov, "premium": prem, "_score": score})
    rows.sort(key=lambda r: r["_score"])
    if rows:
        rows[0]["recommended"] = True
    return _attach_cols(rows, "sip")


# ---- generic HTML PDF generator (uses cols metadata) ----
_PRODUCT_LABEL = {
    "term":      {"en":"Term Life Insurance",        "hi":"टर्म जीवन बीमा"},
    "health":    {"en":"Health Insurance",            "hi":"स्वास्थ्य बीमा"},
    "endowment": {"en":"Endowment / Traditional Life","hi":"एंडोमेंट / पारंपरिक जीवन बीमा"},
    "ulip":      {"en":"ULIP (Unit Linked Plan)",     "hi":"ULIP (यूनिट लिंक्ड प्लान)"},
    "sip":       {"en":"Mutual Fund SIP",             "hi":"म्यूचुअल फंड SIP"},
}

def generate_comparison_html_v2(
    rows: list[dict], product_type: str, inputs: dict,
    client_name: str = "Client", advisor_name: str = "Advisor",
    firm_name: str = "Sarathi-AI CRM", brand: dict | None = None, lang: str = "en",
) -> str:
    b = brand or {}
    primary = b.get("primary_color") or "#1a56db"
    accent = b.get("accent_color") or "#ea580c"
    logo = b.get("logo") or ""
    cta = b.get("cta") or "Grow Your Advisory Business"
    irdai = b.get("irdai_license") or ""
    today = time.strftime("%d %b %Y")
    plabel = _PRODUCT_LABEL.get(product_type, {}).get(lang) or product_type.title()

    # Inputs panel
    inp_rows = [f'<div><b>{_t("product", lang)}:</b> {plabel}</div>']
    for k, v in inputs.items():
        if k in ("client_name", "lang", "tenant_id", "product_type"): continue
        if v in (None, ""): continue
        label = k.replace("_", " ").title()
        if isinstance(v, int) and ("amount" in k or "sum" in k or "investment" in k or "sip" in k):
            v = f"₹{v:,}"
        inp_rows.append(f'<div><b>{label}:</b> {v}</div>')

    # Build table from cols
    if not rows:
        return "<html><body><h2>No providers</h2></body></html>"
    headers = rows[0].get("cols") or []
    head_html = '<th style="padding:12px 10px;text-align:center">#</th><th style="padding:12px 10px;text-align:left">{}</th>'.format(_t("insurer", lang))
    for c in headers:
        lab = c.get(f"label_{lang}") or c.get("label_en") or c.get("key")
        tip = c.get(f"tip_{lang}") or c.get("tip_en") or ""
        head_html += f'<th style="padding:12px 10px;text-align:{c.get("align","left")}" title="{tip}">{lab}<div style="font-weight:400;font-size:10px;opacity:.85;margin-top:2px">{tip[:55]}{"…" if len(tip)>55 else ""}</div></th>'
    body_html = ""
    for i, r in enumerate(rows, start=1):
        is_rec = r.get("recommended")
        bg = f"background:linear-gradient(90deg,{primary}15,#fff);border-left:4px solid {accent};" if is_rec else ""
        rec_badge = f'<span style="background:{accent};color:white;padding:2px 8px;border-radius:6px;font-size:0.7em;font-weight:700;margin-left:6px">{_t("recommended", lang)}</span>' if is_rec else ""
        body_html += f'<tr style="{bg}border-bottom:1px solid #eee">'
        body_html += f'<td style="padding:14px 10px;text-align:center;font-weight:700;color:{primary}">#{i}</td>'
        body_html += f'<td style="padding:14px 10px"><b>{r.get("logo","")} {r["name"]}</b>{rec_badge}</td>'
        for c in r.get("cols", []):
            val = c.get("value", "—")
            style = f'padding:14px 10px;text-align:{c.get("align","left")};'
            if c.get("highlight"): style += f"font-weight:700;color:{primary};"
            body_html += f'<td style="{style}">{val}</td>'
        body_html += '</tr>'

    return f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8"><title>{_t('title', lang)} — {client_name}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Poppins',sans-serif;color:#222;background:#fff;padding:40px}}
.firm-banner{{display:flex;align-items:center;gap:16px;padding:16px 24px;margin-bottom:20px;border-bottom:3px solid {primary}}}
.firm-logo{{width:64px;height:64px;object-fit:contain;border-radius:8px}}
h1{{color:{primary};font-size:24px;margin-bottom:6px}}
.meta{{color:#666;font-size:13px;margin-bottom:18px}}
.inputs{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 24px;background:#f8fafc;padding:14px 18px;border-radius:8px;margin-bottom:20px;font-size:13px}}
table{{width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;font-size:13px}}
th{{background:{primary};color:white;font-weight:600;font-size:12px;vertical-align:top}}
.disclaimer{{margin-top:22px;padding:12px 16px;background:#fffbeb;border-left:4px solid {accent};font-size:11px;color:#78350f;border-radius:6px}}
.footer{{margin-top:24px;text-align:center;color:#888;font-size:11px;border-top:1px solid #eee;padding-top:12px}}
</style></head><body>
<div class="firm-banner">
  {f'<img class="firm-logo" src="{logo}">' if logo else f'<div class="firm-logo" style="background:{primary};color:white;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700">{(firm_name or "S")[0].upper()}</div>'}
  <div style="flex:1"><div style="font-size:20px;font-weight:700;color:{primary}">{firm_name}</div><div style="font-size:13px;color:#666">{cta}</div>{f'<div style="font-size:11px;color:#888;margin-top:2px">IRDAI Reg: {irdai}</div>' if irdai else ''}</div>
</div>
<h1>{_t('title', lang)} — {plabel}</h1>
<div class="meta"><b>{_t('prepared_for', lang)}:</b> {client_name} · <b>{_t('prepared_by', lang)}:</b> {advisor_name} · <b>{_t('date', lang)}:</b> {today}</div>
<div class="inputs">{''.join(inp_rows)}</div>
<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>
<div class="disclaimer"><b>⚠️ Disclaimer:</b> {_t('disclaimer', lang)}</div>
<div class="footer">Generated by Sarathi-AI · {today} · {firm_name}</div>
</body></html>"""
