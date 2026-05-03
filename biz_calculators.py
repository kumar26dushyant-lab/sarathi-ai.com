# =============================================================================
#  biz_calculators.py — Sarathi-AI Business Technologies: Financial Calculator Library
# =============================================================================
#
#  Pure math functions for insurance & investment pitch calculators:
#    1. Inflation Eraser — Shows purchasing power erosion
#    2. HLV (Human Life Value) — Justifies term insurance cover
#    3. Retirement Planner — Gap analysis for retirement corpus
#    4. EMI Calculator — Premium EMI breakdown
#    5. Health Cover Estimator — Recommended sum insured
#    6. SIP vs Lumpsum — Investment mode comparison
#    7. Mutual Fund SIP — Goal-based SIP planner
#    8. ULIP vs Mutual Fund — Product comparison
#    9. NPS Planner — National Pension Scheme estimator
#
# =============================================================================

import math
from dataclasses import dataclass, asdict
from typing import List, Optional


# =============================================================================
#  1. INFLATION ERASER
# =============================================================================

@dataclass
class InflationResult:
    current_value: float
    future_value_needed: float
    purchasing_power_left: float
    erosion_percent: float
    years: int
    inflation_rate: float
    yearly_breakdown: List[dict]

    def to_dict(self):
        return asdict(self)


def inflation_eraser(current_amount: float, inflation_rate: float = 6.0,
                     years: int = 10) -> InflationResult:
    """
    Show how inflation erodes purchasing power.

    The Pitch: "Sir, your ₹50,000 income today will only buy ₹28,000
    worth of goods in 10 years at 6% inflation."

    Args:
        current_amount: Current monthly income/expense (₹)
        inflation_rate: Annual inflation rate (%)
        years: Number of years to project
    """
    rate = inflation_rate / 100.0
    yearly = []

    for y in range(1, years + 1):
        # What today's amount will be worth in future (purchasing power)
        purchasing_power = current_amount / ((1 + rate) ** y)
        # How much you'd need in future to match today's value
        future_needed = current_amount * ((1 + rate) ** y)
        erosion = ((current_amount - purchasing_power) / current_amount) * 100

        yearly.append({
            'year': y,
            'purchasing_power': round(purchasing_power, 2),
            'future_needed': round(future_needed, 2),
            'erosion_percent': round(erosion, 1),
        })

    final = yearly[-1]
    return InflationResult(
        current_value=current_amount,
        future_value_needed=final['future_needed'],
        purchasing_power_left=final['purchasing_power'],
        erosion_percent=final['erosion_percent'],
        years=years,
        inflation_rate=inflation_rate,
        yearly_breakdown=yearly,
    )


# =============================================================================
#  2. HLV (HUMAN LIFE VALUE) CALCULATOR
# =============================================================================

@dataclass
class HLVResult:
    monthly_expense: float
    annual_expense: float
    outstanding_loans: float
    child_education: float
    current_savings: float
    existing_cover: float
    years_to_retirement: int
    inflation_rate: float
    total_future_expense: float
    total_liability: float
    net_hlv: float
    recommended_cover: float
    gap: float

    def to_dict(self):
        return asdict(self)


def hlv_calculator(monthly_expense: float, outstanding_loans: float = 0,
                   child_education: float = 0, current_savings: float = 0,
                   existing_cover: float = 0, current_age: int = 35,
                   retirement_age: int = 60,
                   inflation_rate: float = 6.0) -> HLVResult:
    """
    Calculate Human Life Value — how much term cover is needed.

    The Pitch: "If something happens to you, how much does your family
    need to maintain their lifestyle?"

    Args:
        monthly_expense: Monthly family expense (₹)
        outstanding_loans: Total outstanding loans (₹)
        child_education: Future child education cost (₹)
        current_savings: Current savings + investments (₹)
        existing_cover: Existing life insurance cover (₹)
        current_age: Current age
        retirement_age: Expected retirement age
        inflation_rate: Expected inflation (%)
    """
    years = retirement_age - current_age
    rate = inflation_rate / 100.0
    annual_expense = monthly_expense * 12

    # Present value of future expenses (accounting for inflation)
    # Using annuity formula: PV = PMT × [(1 - (1+r)^-n) / r]
    # But with inflation, real rate = nominal - inflation ≈ discount_rate
    discount_rate = 0.02  # Conservative 2% real return above inflation
    if discount_rate > 0:
        pv_factor = (1 - (1 + discount_rate) ** (-years)) / discount_rate
    else:
        pv_factor = years

    total_future_expense = annual_expense * pv_factor
    total_liability = total_future_expense + outstanding_loans + child_education
    net_assets = current_savings + existing_cover
    net_hlv = total_liability - net_assets
    recommended_cover = max(net_hlv, 0)

    # Round to nearest lakh for cleaner presentation
    recommended_cover = math.ceil(recommended_cover / 100000) * 100000
    gap = recommended_cover - existing_cover

    return HLVResult(
        monthly_expense=monthly_expense,
        annual_expense=annual_expense,
        outstanding_loans=outstanding_loans,
        child_education=child_education,
        current_savings=current_savings,
        existing_cover=existing_cover,
        years_to_retirement=years,
        inflation_rate=inflation_rate,
        total_future_expense=round(total_future_expense, 2),
        total_liability=round(total_liability, 2),
        net_hlv=round(net_hlv, 2),
        recommended_cover=recommended_cover,
        gap=max(gap, 0),
    )


# =============================================================================
#  3. RETIREMENT PLANNER
# =============================================================================

@dataclass
class RetirementResult:
    current_age: int
    retirement_age: int
    life_expectancy: int
    monthly_expense: float
    inflation_rate: float
    pre_return_rate: float
    post_return_rate: float
    expense_at_retirement: float
    corpus_needed: float
    current_savings: float
    gap: float
    monthly_sip_needed: float
    yearly_breakdown: List[dict]

    def to_dict(self):
        return asdict(self)


def retirement_planner(current_age: int = 35, retirement_age: int = 60,
                       life_expectancy: int = 85,
                       monthly_expense: float = 40000,
                       inflation_rate: float = 7.0,
                       pre_retirement_return: float = 12.0,
                       post_retirement_return: float = 8.0,
                       current_savings: float = 0,
                       annual_income_increase: float = 10.0) -> RetirementResult:
    """
    Retirement gap analysis — matches the Excel template logic.

    Args:
        current_age: Client's current age
        retirement_age: Desired retirement age
        life_expectancy: Expected life span
        monthly_expense: Current monthly expense
        inflation_rate: Expected inflation rate (%)
        pre_retirement_return: Expected return rate before retirement (%)
        post_retirement_return: Expected return rate after retirement (%)
        current_savings: Current retirement savings (₹)
        annual_income_increase: Expected annual income growth (%)
    """
    years_to_retire = retirement_age - current_age
    years_in_retirement = life_expectancy - retirement_age
    inf = inflation_rate / 100.0
    pre_ret = pre_retirement_return / 100.0
    post_ret = post_retirement_return / 100.0

    # Monthly expense at retirement (inflation-adjusted)
    annual_expense = monthly_expense * 12
    expense_at_retirement = annual_expense * ((1 + inf) ** years_to_retire)
    monthly_at_retirement = expense_at_retirement / 12

    # Corpus needed at retirement
    # PV of annuity for post-retirement years (inflation-adjusted)
    real_post_rate = ((1 + post_ret) / (1 + inf)) - 1
    if real_post_rate > 0 and real_post_rate != 0:
        pv_factor = (1 - (1 + real_post_rate) ** (-years_in_retirement)) / real_post_rate
    else:
        pv_factor = years_in_retirement
    corpus_needed = expense_at_retirement * pv_factor

    # What current savings will grow to
    future_savings = current_savings * ((1 + pre_ret) ** years_to_retire)
    gap = max(corpus_needed - future_savings, 0)

    # Monthly SIP needed to bridge the gap
    monthly_rate = pre_ret / 12
    if monthly_rate > 0:
        months = years_to_retire * 12
        # FV of annuity = PMT × [((1+r)^n - 1) / r]
        # PMT = FV × r / ((1+r)^n - 1)
        fv_factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
        monthly_sip = gap / fv_factor if fv_factor > 0 else 0
    else:
        monthly_sip = gap / (years_to_retire * 12) if years_to_retire > 0 else 0

    # Year-by-year breakdown
    yearly = []
    for y in range(1, years_to_retire + 1):
        yr_expense = annual_expense * ((1 + inf) ** y)
        yr_savings = current_savings * ((1 + pre_ret) ** y)
        yr_sip_corpus = monthly_sip * 12 * (((1 + pre_ret) ** y - 1) / pre_ret) if pre_ret > 0 else monthly_sip * 12 * y
        yearly.append({
            'year': y,
            'age': current_age + y,
            'annual_expense': round(yr_expense, 0),
            'savings_growth': round(yr_savings, 0),
            'sip_corpus': round(yr_sip_corpus, 0),
            'total_corpus': round(yr_savings + yr_sip_corpus, 0),
        })

    return RetirementResult(
        current_age=current_age,
        retirement_age=retirement_age,
        life_expectancy=life_expectancy,
        monthly_expense=monthly_expense,
        inflation_rate=inflation_rate,
        pre_return_rate=pre_retirement_return,
        post_return_rate=post_retirement_return,
        expense_at_retirement=round(monthly_at_retirement, 0),
        corpus_needed=round(corpus_needed, 0),
        current_savings=current_savings,
        gap=round(gap, 0),
        monthly_sip_needed=round(monthly_sip, 0),
        yearly_breakdown=yearly,
    )


# =============================================================================
#  4. EMI / PREMIUM CALCULATOR
# =============================================================================

@dataclass
class EMIResult:
    total_premium: float
    gst_amount: float
    premium_with_gst: float
    cibil_discount_pct: float
    cibil_discount: float
    net_premium: float
    down_payment: float
    emi_options: List[dict]

    def to_dict(self):
        return asdict(self)


def emi_calculator(annual_premium: float, years: int = 5,
                   gst_rate: float = 18.0, cibil_discount_pct: float = 10.0,
                   down_payment_pct: float = 25.0) -> EMIResult:
    """
    Insurance premium EMI calculation — matches the Excel template.

    Args:
        annual_premium: Annual premium amount (₹)
        years: Number of years
        gst_rate: GST rate (%)
        cibil_discount_pct: CIBIL score discount (%)
        down_payment_pct: Down payment percentage (%)
    """
    total_premium = annual_premium * years
    gst_amount = total_premium * (gst_rate / 100.0)
    premium_with_gst = total_premium + gst_amount
    cibil_discount = premium_with_gst * (cibil_discount_pct / 100.0)
    net_premium = premium_with_gst - cibil_discount
    down_payment = net_premium * (down_payment_pct / 100.0)
    balance = net_premium - down_payment

    # EMI options for different tenures
    emi_options = []
    for months in [3, 6, 9, 12]:
        if months > 0:
            monthly_emi = balance / months
            total_paid = down_payment + (monthly_emi * months)
            interest = total_paid - net_premium
            emi_options.append({
                'months': months,
                'monthly_emi': round(monthly_emi, 0),
                'total_amount': round(total_paid, 0),
                'interest': round(interest, 0),
            })

    return EMIResult(
        total_premium=round(total_premium, 0),
        gst_amount=round(gst_amount, 0),
        premium_with_gst=round(premium_with_gst, 0),
        cibil_discount_pct=cibil_discount_pct,
        cibil_discount=round(cibil_discount, 0),
        net_premium=round(net_premium, 0),
        down_payment=round(down_payment, 0),
        emi_options=emi_options,
    )


# =============================================================================
#  5. HEALTH COVER ESTIMATOR
# =============================================================================

@dataclass
class HealthCoverResult:
    age: int
    family_size: str
    city_tier: str
    monthly_income: float
    existing_cover: float
    recommended_si: float
    coverage_components: dict
    gap: float
    estimated_premium_range: dict

    def to_dict(self):
        return asdict(self)


def health_cover_estimator(age: int = 35, family_size: str = "2A+2C",
                           city_tier: str = "metro",
                           monthly_income: float = 50000,
                           existing_cover: float = 0,
                           has_parents: bool = False) -> HealthCoverResult:
    """
    Estimate recommended health insurance sum insured.

    Components:
    - Base hospitalization (room rent × 15 days × 2)
    - ICU charges
    - Doctor fees
    - Medicines & diagnostics
    - Ambulance
    - Pre/post hospitalization
    - Inflation buffer (10% per year for 5 years)

    Args:
        age: Primary member age
        family_size: Family configuration (e.g., '1A', '2A', '2A+1C', '2A+2C')
        city_tier: 'metro', 'tier1', 'tier2', 'tier3'
        monthly_income: Monthly household income (₹)
        existing_cover: Existing health cover (₹)
        has_parents: Whether parents need coverage
    """
    # Room rent benchmarks by city tier
    room_rates = {
        'metro': 8000, 'tier1': 5000, 'tier2': 3500, 'tier3': 2500
    }
    room_rate = room_rates.get(city_tier, 5000)

    # Calculate components
    room_charges = room_rate * 15 * 2  # 15 days × 2 hospitalizations
    icu_charges = room_rate * 3 * 10  # ICU = 3x room rate, 10 days
    doctor_fees = 50000  # Specialist consultations
    medicines = 75000  # Medicines, consumables
    diagnostics = 30000  # Tests, imaging
    ambulance = 10000
    pre_post = 25000  # Pre/post hospitalization expenses

    base_cover = (room_charges + icu_charges + doctor_fees + medicines +
                  diagnostics + ambulance + pre_post)

    # Family multiplier
    member_count = family_size.count('A') + family_size.count('C') * 0.5
    if has_parents:
        member_count += 1.5
    family_multiplier = max(1.0, member_count * 0.7)

    # Inflation-adjusted (6% medical inflation, 5-year projection)
    inflation_factor = (1.06) ** 5

    total_needed = base_cover * family_multiplier * inflation_factor
    # Round to nearest 5 lakh
    recommended = math.ceil(total_needed / 500000) * 500000
    # Minimum 5 lakh
    recommended = max(recommended, 500000)

    gap = max(recommended - existing_cover, 0)

    # Estimated premium range (rough heuristic)
    base_premium = recommended * 0.012  # ~1.2% of SI for young family
    age_factor = 1 + max(0, (age - 30) * 0.03)  # 3% increase per year above 30
    est_premium_low = base_premium * age_factor * 0.8
    est_premium_high = base_premium * age_factor * 1.3

    return HealthCoverResult(
        age=age,
        family_size=family_size,
        city_tier=city_tier,
        monthly_income=monthly_income,
        existing_cover=existing_cover,
        recommended_si=recommended,
        coverage_components={
            'room_charges': round(room_charges, 0),
            'icu_charges': round(icu_charges, 0),
            'doctor_fees': doctor_fees,
            'medicines': medicines,
            'diagnostics': diagnostics,
            'ambulance': ambulance,
            'pre_post_hospitalization': pre_post,
            'base_total': round(base_cover, 0),
            'family_multiplier': round(family_multiplier, 2),
            'inflation_factor': round(inflation_factor, 2),
        },
        gap=gap,
        estimated_premium_range={
            'low': round(est_premium_low, 0),
            'high': round(est_premium_high, 0),
        },
    )


# =============================================================================
#  6. SIP vs LUMPSUM COMPARISON
# =============================================================================

@dataclass
class SIPvLumpsumResult:
    investment_amount: float
    years: int
    expected_return: float
    lumpsum_maturity: float
    sip_monthly: float
    sip_maturity: float
    sip_total_invested: float
    difference: float
    winner: str
    yearly_comparison: List[dict]

    def to_dict(self):
        return asdict(self)


def sip_vs_lumpsum(total_amount: float = 500000, years: int = 10,
                   expected_return: float = 12.0) -> SIPvLumpsumResult:
    """
    Compare lumpsum investment vs monthly SIP.

    Args:
        total_amount: Total investment amount (₹)
        years: Investment horizon
        expected_return: Expected annual return (%)
    """
    rate = expected_return / 100.0
    monthly_rate = rate / 12
    months = years * 12

    # Lumpsum
    lumpsum_maturity = total_amount * ((1 + rate) ** years)

    # SIP — invest the same total over the period
    monthly_sip = total_amount / months
    if monthly_rate > 0:
        sip_maturity = monthly_sip * (((1 + monthly_rate) ** months - 1) /
                                       monthly_rate) * (1 + monthly_rate)
    else:
        sip_maturity = total_amount

    # Yearly comparison
    yearly = []
    for y in range(1, years + 1):
        ls_val = total_amount * ((1 + rate) ** y)
        m = y * 12
        if monthly_rate > 0:
            sip_val = monthly_sip * (((1 + monthly_rate) ** m - 1) /
                                      monthly_rate) * (1 + monthly_rate)
        else:
            sip_val = monthly_sip * m
        yearly.append({
            'year': y,
            'lumpsum_value': round(ls_val, 0),
            'sip_value': round(sip_val, 0),
            'sip_invested': round(monthly_sip * m, 0),
        })

    winner = "Lumpsum" if lumpsum_maturity > sip_maturity else "SIP"

    return SIPvLumpsumResult(
        investment_amount=total_amount,
        years=years,
        expected_return=expected_return,
        lumpsum_maturity=round(lumpsum_maturity, 0),
        sip_monthly=round(monthly_sip, 0),
        sip_maturity=round(sip_maturity, 0),
        sip_total_invested=total_amount,
        difference=round(abs(lumpsum_maturity - sip_maturity), 0),
        winner=winner,
        yearly_comparison=yearly,
    )


# =============================================================================
#  7. MUTUAL FUND SIP PLANNER
# =============================================================================

@dataclass
class MFSIPResult:
    monthly_sip: float
    goal_amount: float
    years: int
    annual_return: float
    total_invested: float
    expected_corpus: float
    wealth_gained: float
    yearly_breakdown: List[dict]

    def to_dict(self):
        return asdict(self)


def mf_sip_planner(goal_amount: float = 5000000, years: int = 15,
                   annual_return: float = 12.0, existing_savings: float = 0) -> MFSIPResult:
    """
    Goal-based Mutual Fund SIP calculator.

    The Pitch: "Sir, to build ₹50L in 15 years, you just need ₹10,000/month
    in a good equity fund."

    Args:
        goal_amount: Target corpus (₹)
        years: Investment horizon
        annual_return: Expected annual return (%)
        existing_savings: Current savings already invested (₹)
    """
    rate = annual_return / 100.0
    monthly_rate = rate / 12
    months = years * 12

    # Future value of existing savings
    fv_existing = existing_savings * ((1 + rate) ** years)
    remaining_goal = max(goal_amount - fv_existing, 0)

    # Monthly SIP needed to reach remaining goal
    if monthly_rate > 0 and remaining_goal > 0:
        monthly_sip = remaining_goal / (
            (((1 + monthly_rate) ** months - 1) / monthly_rate) * (1 + monthly_rate)
        )
    else:
        monthly_sip = remaining_goal / months if months > 0 else 0

    total_invested = monthly_sip * months + existing_savings
    expected_corpus = goal_amount
    wealth_gained = expected_corpus - total_invested

    # Yearly breakdown
    yearly = []
    for y in range(1, years + 1):
        m = y * 12
        if monthly_rate > 0:
            sip_corpus = monthly_sip * (((1 + monthly_rate) ** m - 1) / monthly_rate) * (1 + monthly_rate)
        else:
            sip_corpus = monthly_sip * m
        fv_ex = existing_savings * ((1 + rate) ** y)
        total_val = sip_corpus + fv_ex
        yearly.append({
            'year': y,
            'sip_value': round(sip_corpus, 0),
            'existing_growth': round(fv_ex, 0),
            'total_value': round(total_val, 0),
            'invested': round(monthly_sip * m + existing_savings, 0),
        })

    return MFSIPResult(
        monthly_sip=round(monthly_sip, 0),
        goal_amount=goal_amount,
        years=years,
        annual_return=annual_return,
        total_invested=round(total_invested, 0),
        expected_corpus=round(expected_corpus, 0),
        wealth_gained=round(wealth_gained, 0),
        yearly_breakdown=yearly,
    )


# =============================================================================
#  8. ULIP vs MUTUAL FUND COMPARISON
# =============================================================================

@dataclass
class ULIPvsMFResult:
    investment_amount: float
    years: int
    ulip_return: float
    mf_return: float
    ulip_maturity: float
    ulip_charges_total: float
    ulip_net: float
    mf_maturity: float
    mf_charges_total: float
    mf_net: float
    difference: float
    winner: str
    ulip_yearly: List[dict]
    mf_yearly: List[dict]
    insurance_cover: float

    def to_dict(self):
        return asdict(self)


def ulip_vs_mf(annual_investment: float = 100000, years: int = 15,
               ulip_return: float = 10.0, mf_return: float = 12.0) -> ULIPvsMFResult:
    """
    Compare ULIP vs Mutual Fund returns.

    The Pitch: "Let me show you the real cost comparison between ULIP and
    Mutual Funds over 15 years."

    Args:
        annual_investment: Annual premium/investment (₹)
        years: Investment horizon
        ulip_return: Expected ULIP fund return (%)
        mf_return: Expected MF return (%)
    """
    # ULIP charges (typical)
    ulip_premium_alloc_yr1 = 0.60   # 60% allocation in year 1
    ulip_premium_alloc_later = 0.95  # 95% from year 3+
    ulip_fund_mgmt = 0.0135          # 1.35% annual fund management
    ulip_mortality = 0.003            # 0.3% mortality charge

    # MF charges
    mf_expense_ratio = 0.015  # 1.5% expense ratio (regular plan)

    ulip_corpus = 0
    ulip_total_charges = 0
    ulip_yearly = []

    mf_corpus = 0
    mf_total_charges = 0
    mf_yearly = []

    ulip_rate = ulip_return / 100.0
    mf_rate = mf_return / 100.0

    for y in range(1, years + 1):
        # ULIP: allocation based on year
        if y == 1:
            alloc = annual_investment * ulip_premium_alloc_yr1
        elif y == 2:
            alloc = annual_investment * 0.80
        else:
            alloc = annual_investment * ulip_premium_alloc_later

        premium_charge = annual_investment - alloc
        ulip_corpus = (ulip_corpus + alloc) * (1 + ulip_rate)
        fund_charge = ulip_corpus * ulip_fund_mgmt
        mort_charge = ulip_corpus * ulip_mortality
        ulip_corpus -= (fund_charge + mort_charge)
        yr_charges = premium_charge + fund_charge + mort_charge
        ulip_total_charges += yr_charges

        ulip_yearly.append({
            'year': y,
            'invested': round(annual_investment * y, 0),
            'corpus': round(ulip_corpus, 0),
            'charges': round(yr_charges, 0),
        })

        # MF: full investment, minus expense ratio
        mf_corpus = (mf_corpus + annual_investment) * (1 + mf_rate)
        exp_charge = mf_corpus * mf_expense_ratio
        mf_corpus -= exp_charge
        mf_total_charges += exp_charge

        mf_yearly.append({
            'year': y,
            'invested': round(annual_investment * y, 0),
            'corpus': round(mf_corpus, 0),
            'charges': round(exp_charge, 0),
        })

    # ULIP insurance cover (typically 10x annual premium)
    insurance_cover = annual_investment * 10

    difference = mf_corpus - ulip_corpus
    winner = "Mutual Fund" if difference > 0 else "ULIP"

    return ULIPvsMFResult(
        investment_amount=annual_investment,
        years=years,
        ulip_return=ulip_return,
        mf_return=mf_return,
        ulip_maturity=round(ulip_corpus, 0),
        ulip_charges_total=round(ulip_total_charges, 0),
        ulip_net=round(ulip_corpus, 0),
        mf_maturity=round(mf_corpus, 0),
        mf_charges_total=round(mf_total_charges, 0),
        mf_net=round(mf_corpus, 0),
        difference=round(abs(difference), 0),
        winner=winner,
        ulip_yearly=ulip_yearly,
        mf_yearly=mf_yearly,
        insurance_cover=insurance_cover,
    )


# =============================================================================
#  9. NPS (NATIONAL PENSION SCHEME) PLANNER
# =============================================================================

@dataclass
class NPSResult:
    monthly_contribution: float
    years_to_retire: int
    annual_return: float
    total_corpus: float
    total_invested: float
    wealth_gained: float
    annuity_corpus: float        # 40% mandatory annuity
    lumpsum_withdrawal: float    # 60% tax-free withdrawal
    monthly_pension_estimate: float
    tax_saved_yearly: float
    tax_saved_total: float
    yearly_breakdown: List[dict]

    def to_dict(self):
        return asdict(self)


def nps_planner(monthly_contribution: float = 5000, current_age: int = 30,
                retirement_age: int = 60, annual_return: float = 10.0,
                tax_bracket: float = 30.0) -> NPSResult:
    """
    NPS (National Pension Scheme) retirement planner.

    The Pitch: "Sir, with just ₹5,000/month in NPS, you can build ₹1 Cr+
    corpus AND save ₹18,000 tax every year under Section 80CCD(1B)."

    Args:
        monthly_contribution: Monthly NPS contribution (₹)
        current_age: Current age
        retirement_age: Retirement age (max 75)
        annual_return: Expected annual return (%)
        tax_bracket: Income tax bracket (%) for 80CCD benefit
    """
    years = retirement_age - current_age
    if years <= 0:
        years = 1
    rate = annual_return / 100.0
    monthly_rate = rate / 12
    months = years * 12

    # Corpus accumulation (monthly SIP)
    if monthly_rate > 0:
        total_corpus = monthly_contribution * (
            ((1 + monthly_rate) ** months - 1) / monthly_rate
        ) * (1 + monthly_rate)
    else:
        total_corpus = monthly_contribution * months

    total_invested = monthly_contribution * months
    wealth_gained = total_corpus - total_invested

    # NPS rules: 60% lumpsum (tax-free), 40% mandatory annuity
    lumpsum_withdrawal = total_corpus * 0.60
    annuity_corpus = total_corpus * 0.40

    # Estimate monthly pension (annuity at ~6% return)
    annuity_rate = 0.06 / 12
    # Annuity for 20 years post-retirement
    if annuity_rate > 0:
        monthly_pension = annuity_corpus * annuity_rate / (1 - (1 + annuity_rate) ** -240)
    else:
        monthly_pension = annuity_corpus / 240

    # Tax saving under 80CCD(1B) — max ₹50,000/year extra deduction
    annual_contribution = monthly_contribution * 12
    eligible_80ccd = min(annual_contribution, 50000)  # Section 80CCD(1B) limit
    tax_saved_yearly = eligible_80ccd * (tax_bracket / 100.0)
    tax_saved_total = tax_saved_yearly * years

    # Yearly breakdown
    yearly = []
    corpus = 0
    for y in range(1, years + 1):
        m = y * 12
        if monthly_rate > 0:
            corpus = monthly_contribution * (
                ((1 + monthly_rate) ** m - 1) / monthly_rate
            ) * (1 + monthly_rate)
        else:
            corpus = monthly_contribution * m
        yearly.append({
            'year': y,
            'age': current_age + y,
            'invested': round(monthly_contribution * m, 0),
            'corpus': round(corpus, 0),
            'tax_saved': round(tax_saved_yearly * y, 0),
        })

    return NPSResult(
        monthly_contribution=monthly_contribution,
        years_to_retire=years,
        annual_return=annual_return,
        total_corpus=round(total_corpus, 0),
        total_invested=round(total_invested, 0),
        wealth_gained=round(wealth_gained, 0),
        annuity_corpus=round(annuity_corpus, 0),
        lumpsum_withdrawal=round(lumpsum_withdrawal, 0),
        monthly_pension_estimate=round(monthly_pension, 0),
        tax_saved_yearly=round(tax_saved_yearly, 0),
        tax_saved_total=round(tax_saved_total, 0),
        yearly_breakdown=yearly,
    )


# =============================================================================
#  10. STEP-UP SIP CALCULATOR
# =============================================================================

@dataclass
class StepUpSIPResult:
    initial_monthly_sip: float
    annual_step_up: float
    years: int
    annual_return: float
    total_invested: float
    total_corpus: float
    wealth_gained: float
    final_monthly_sip: float
    regular_sip_corpus: float
    stepup_advantage: float
    yearly_breakdown: List[dict]

    def to_dict(self):
        return asdict(self)


def stepup_sip_planner(initial_sip: float = 10000,
                       annual_step_up: float = 10.0,
                       years: int = 20,
                       annual_return: float = 12.0) -> StepUpSIPResult:
    """
    Step-up SIP: Increase monthly SIP by a fixed percentage every year.

    Args:
        initial_sip: Starting monthly SIP amount (₹)
        annual_step_up: Yearly increase in SIP (%)
        years: Investment horizon
        annual_return: Expected annual return (%)
    """
    monthly_rate = annual_return / 100.0 / 12
    step_rate = annual_step_up / 100.0

    corpus = 0.0
    total_invested = 0.0
    yearly = []

    for y in range(1, years + 1):
        monthly_sip = initial_sip * ((1 + step_rate) ** (y - 1))
        year_investment = monthly_sip * 12
        total_invested += year_investment

        # Each month's SIP grows for remaining months
        for m in range(12):
            months_remaining = (years - y) * 12 + (12 - m)
            corpus += monthly_sip * ((1 + monthly_rate) ** months_remaining)

        yearly.append({
            'year': y,
            'monthly_sip': round(monthly_sip, 0),
            'year_invested': round(year_investment, 0),
            'cumulative_invested': round(total_invested, 0),
        })

    # Regular SIP (no step-up) for comparison
    regular_corpus = 0.0
    for m_total in range(years * 12):
        months_remaining = years * 12 - m_total
        regular_corpus += initial_sip * ((1 + monthly_rate) ** months_remaining)

    # Fill in corpus values at each year-end
    running_corpus = 0.0
    for idx, y in enumerate(range(1, years + 1)):
        monthly_sip = initial_sip * ((1 + step_rate) ** (y - 1))
        for m in range(12):
            running_corpus = running_corpus * (1 + monthly_rate) + monthly_sip
        yearly[idx]['corpus'] = round(running_corpus, 0)

    final_corpus = running_corpus
    final_monthly_sip = initial_sip * ((1 + step_rate) ** (years - 1))

    return StepUpSIPResult(
        initial_monthly_sip=initial_sip,
        annual_step_up=annual_step_up,
        years=years,
        annual_return=annual_return,
        total_invested=round(total_invested, 0),
        total_corpus=round(final_corpus, 0),
        wealth_gained=round(final_corpus - total_invested, 0),
        final_monthly_sip=round(final_monthly_sip, 0),
        regular_sip_corpus=round(regular_corpus, 0),
        stepup_advantage=round(final_corpus - regular_corpus, 0),
        yearly_breakdown=yearly,
    )


# =============================================================================
#  11. SWP (SYSTEMATIC WITHDRAWAL PLAN) CALCULATOR
# =============================================================================

@dataclass
class SWPResult:
    initial_corpus: float
    monthly_withdrawal: float
    annual_return: float
    years: int
    total_withdrawn: float
    remaining_corpus: float
    corpus_lasted_months: int
    is_sustainable: bool
    yearly_breakdown: List[dict]

    def to_dict(self):
        return asdict(self)


def swp_calculator(initial_corpus: float = 5000000,
                   monthly_withdrawal: float = 30000,
                   annual_return: float = 8.0,
                   years: int = 20) -> SWPResult:
    """
    SWP Calculator: Plan systematic withdrawals from a corpus.

    Args:
        initial_corpus: Starting investment corpus (₹)
        monthly_withdrawal: Monthly withdrawal amount (₹)
        annual_return: Expected annual return on remaining corpus (%)
        years: Planned withdrawal period
    """
    monthly_rate = annual_return / 100.0 / 12
    corpus = initial_corpus
    total_withdrawn = 0.0
    yearly = []
    lasted_months = 0
    depleted = False

    for y in range(1, years + 1):
        year_start = corpus
        year_withdrawn = 0.0
        for m in range(12):
            if corpus <= 0:
                depleted = True
                break
            # Grow corpus first, then withdraw
            corpus = corpus * (1 + monthly_rate)
            withdrawal = min(monthly_withdrawal, corpus)
            corpus -= withdrawal
            total_withdrawn += withdrawal
            year_withdrawn += withdrawal
            lasted_months += 1
        yearly.append({
            'year': y,
            'year_start': round(year_start, 0),
            'withdrawn': round(year_withdrawn, 0),
            'year_end': round(max(corpus, 0), 0),
        })
        if depleted:
            break

    is_sustainable = corpus > 0

    return SWPResult(
        initial_corpus=initial_corpus,
        monthly_withdrawal=monthly_withdrawal,
        annual_return=annual_return,
        years=years,
        total_withdrawn=round(total_withdrawn, 0),
        remaining_corpus=round(max(corpus, 0), 0),
        corpus_lasted_months=lasted_months,
        is_sustainable=is_sustainable,
        yearly_breakdown=yearly,
    )


# =============================================================================
#  12. DELAY COST CALCULATOR
# =============================================================================

@dataclass
class DelayCostResult:
    monthly_sip: float
    years: int
    annual_return: float
    delay_years: int
    corpus_on_time: float
    corpus_delayed: float
    cost_of_delay: float
    extra_sip_needed: float
    comparison: List[dict]

    def to_dict(self):
        return asdict(self)


def delay_cost_calculator(monthly_sip: float = 10000,
                          years: int = 25,
                          annual_return: float = 12.0,
                          delay_years: int = 5) -> DelayCostResult:
    """
    Delay Cost Calculator: Show the real cost of delaying investment.

    Args:
        monthly_sip: Monthly SIP amount (₹)
        years: Total investment horizon if starting today
        annual_return: Expected annual return (%)
        delay_years: How many years you might delay
    """
    monthly_rate = annual_return / 100.0 / 12

    def _sip_corpus(sip: float, months: int) -> float:
        if monthly_rate > 0:
            return sip * (((1 + monthly_rate) ** months - 1) / monthly_rate) * (1 + monthly_rate)
        return sip * months

    months_on_time = years * 12
    months_delayed = (years - delay_years) * 12

    corpus_on_time = _sip_corpus(monthly_sip, months_on_time)
    corpus_delayed = _sip_corpus(monthly_sip, max(months_delayed, 0))
    cost_of_delay = corpus_on_time - corpus_delayed

    # Extra SIP needed if delayed to reach same corpus
    if months_delayed > 0 and monthly_rate > 0:
        fv_factor = (((1 + monthly_rate) ** months_delayed - 1) / monthly_rate) * (1 + monthly_rate)
        extra_sip = corpus_on_time / fv_factor if fv_factor > 0 else 0
    else:
        extra_sip = 0

    # Year-by-year comparison
    comparison = []
    for d in range(delay_years + 1):
        m = (years - d) * 12
        c = _sip_corpus(monthly_sip, max(m, 0))
        if m > 0 and monthly_rate > 0:
            fv_factor = (((1 + monthly_rate) ** m - 1) / monthly_rate) * (1 + monthly_rate)
            needed = corpus_on_time / fv_factor if fv_factor > 0 else 0
        else:
            needed = 0
        comparison.append({
            'delay': d,
            'invest_years': years - d,
            'corpus': round(c, 0),
            'loss': round(corpus_on_time - c, 0),
            'sip_needed': round(needed, 0),
        })

    return DelayCostResult(
        monthly_sip=monthly_sip,
        years=years,
        annual_return=annual_return,
        delay_years=delay_years,
        corpus_on_time=round(corpus_on_time, 0),
        corpus_delayed=round(corpus_delayed, 0),
        cost_of_delay=round(cost_of_delay, 0),
        extra_sip_needed=round(extra_sip, 0),
        comparison=comparison,
    )


# =============================================================================
#  FORMATTERS (for Telegram display)
# =============================================================================

def format_currency(amount: float) -> str:
    """Format amount in Indian currency with lakhs/crores."""
    if amount >= 10000000:
        return f"₹{amount / 10000000:.2f} Cr"
    elif amount >= 100000:
        return f"₹{amount / 100000:.2f} L"
    else:
        return f"₹{amount:,.0f}"


def format_inflation_result(r: InflationResult) -> str:
    """Format inflation result for Telegram."""
    return (
        f"📉 *Inflation Eraser Report*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Current Value: {format_currency(r.current_value)}/month\n"
        f"📅 Time Horizon: {r.years} years\n"
        f"📊 Inflation Rate: {r.inflation_rate}%\n\n"
        f"⚠️ *The Hard Truth:*\n"
        f"Your {format_currency(r.current_value)} today will only buy\n"
        f"*{format_currency(r.purchasing_power_left)}* worth of goods\n"
        f"in {r.years} years\\!\n\n"
        f"📈 You'll need *{format_currency(r.future_value_needed)}/month*\n"
        f"to maintain the same lifestyle\\.\n\n"
        f"🔴 Purchasing power eroded: *{r.erosion_percent}%*\n\n"
        f"💡 _Secure your future with the right plan\\._\n"
        "_Sarathi\\-AI Business Technologies_ 🛡️"
    )


def format_hlv_result(r: HLVResult) -> str:
    """Format HLV result for Telegram."""
    return (
        f"🛡️ *Human Life Value Report*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Monthly Expense: {format_currency(r.monthly_expense)}\n"
        f"🏦 Outstanding Loans: {format_currency(r.outstanding_loans)}\n"
        f"🎓 Child Education: {format_currency(r.child_education)}\n"
        f"💰 Current Savings: {format_currency(r.current_savings)}\n"
        f"📋 Existing Cover: {format_currency(r.existing_cover)}\n"
        f"📅 Years to Retire: {r.years_to_retirement}\n\n"
        f"📊 *Analysis:*\n"
        f"Total Future Need: {format_currency(r.total_liability)}\n"
        f"Net HLV: *{format_currency(r.net_hlv)}*\n\n"
        f"✅ *Recommended Cover: {format_currency(r.recommended_cover)}*\n"
        f"🔴 Coverage Gap: *{format_currency(r.gap)}*\n\n"
        f"💡 _Don't leave your family unprotected\\._\n"
        f"_Secure Your Future Today_ 🛡️"
    )


def format_retirement_result(r: RetirementResult) -> str:
    """Format retirement planning result for Telegram."""
    return (
        f"🏖️ *Retirement Planning Report*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Age: {r.current_age} → Retire at {r.retirement_age}\n"
        f"📅 Life Expectancy: {r.life_expectancy} years\n"
        f"💰 Current Expense: {format_currency(r.monthly_expense)}/month\n"
        f"📊 Inflation: {r.inflation_rate}%\n\n"
        f"⚠️ *At Retirement:*\n"
        f"Monthly Expense: *{format_currency(r.expense_at_retirement)}*\n"
        f"Corpus Needed: *{format_currency(r.corpus_needed)}*\n\n"
        f"💰 Current Savings: {format_currency(r.current_savings)}\n"
        f"🔴 Gap: *{format_currency(r.gap)}*\n\n"
        f"📈 *Start SIP of {format_currency(r.monthly_sip_needed)}/month*\n"
        f"to bridge this gap\\!\n\n"
        f"💡 _The earlier you start, the less you need\\._\n"
        f"_Sarathi\\-AI Business Technologies_ 🛡️"
    )


def format_mfsip_result(r: MFSIPResult) -> str:
    """Format MF SIP result for Telegram."""
    return (
        f"📊 *Mutual Fund SIP Planner*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Goal: {format_currency(r.goal_amount)}\n"
        f"📅 Timeline: {r.years} years @ {r.annual_return}%\n\n"
        f"📈 *Monthly SIP Needed:*\n"
        f"*{format_currency(r.monthly_sip)}/month*\n\n"
        f"💰 Total Invested: {format_currency(r.total_invested)}\n"
        f"📊 Expected Corpus: {format_currency(r.expected_corpus)}\n"
        f"🏆 Wealth Gained: *{format_currency(r.wealth_gained)}*\n\n"
        f"💡 _Start early, grow steadily\\._\n"
        f"_Sarathi\\-AI Business Technologies_ 📊"
    )


def format_ulip_vs_mf_result(r: ULIPvsMFResult) -> str:
    """Format ULIP vs MF result for Telegram."""
    return (
        f"⚖️ *ULIP vs Mutual Fund Comparison*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Annual Investment: {format_currency(r.investment_amount)}\n"
        f"📅 Period: {r.years} years\n\n"
        f"📊 *ULIP:*\n"
        f"  Maturity: {format_currency(r.ulip_maturity)}\n"
        f"  Total Charges: {format_currency(r.ulip_charges_total)}\n"
        f"  Insurance Cover: {format_currency(r.insurance_cover)}\n\n"
        f"📈 *Mutual Fund:*\n"
        f"  Maturity: {format_currency(r.mf_maturity)}\n"
        f"  Total Charges: {format_currency(r.mf_charges_total)}\n\n"
        f"🏆 Winner: *{r.winner}*\n"
        f"Difference: {format_currency(r.difference)}\n\n"
        f"💡 _Know the facts before you invest\\._\n"
        f"_Sarathi\\-AI Business Technologies_ ⚖️"
    )


def format_nps_result(r: NPSResult) -> str:
    """Format NPS result for Telegram."""
    return (
        f"🏛️ *NPS Pension Planner*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Monthly: {format_currency(r.monthly_contribution)}\n"
        f"📅 {r.years_to_retire} years @ {r.annual_return}%\n\n"
        f"📊 *At Retirement:*\n"
        f"Total Corpus: *{format_currency(r.total_corpus)}*\n"
        f"Lumpsum \\(60%\\): {format_currency(r.lumpsum_withdrawal)}\n"
        f"Annuity \\(40%\\): {format_currency(r.annuity_corpus)}\n\n"
        f"💳 *Est\\. Monthly Pension:*\n"
        f"*{format_currency(r.monthly_pension_estimate)}/month*\n\n"
        f"🏷️ Tax Saved: {format_currency(r.tax_saved_yearly)}/year\n"
        f"Total Tax Benefit: {format_currency(r.tax_saved_total)}\n\n"
        f"💡 _NPS \\+ Tax savings \\= Smart retirement\\._\n"
        f"_Sarathi\\-AI Business Technologies_ 🏛️"
    )


def format_stepup_sip_result(r: StepUpSIPResult) -> str:
    """Format Step-up SIP result for Telegram."""
    return (
        f"📈 *Step\\-Up SIP Planner*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Starting SIP: {format_currency(r.initial_monthly_sip)}/month\n"
        f"📊 Annual Step\\-Up: {r.annual_step_up}%\n"
        f"📅 Period: {r.years} years @ {r.annual_return}%\n\n"
        f"🚀 *Results:*\n"
        f"Total Invested: {format_currency(r.total_invested)}\n"
        f"Total Corpus: *{format_currency(r.total_corpus)}*\n"
        f"Wealth Gained: {format_currency(r.wealth_gained)}\n"
        f"Final Monthly SIP: {format_currency(r.final_monthly_sip)}\n\n"
        f"⚡ *Step\\-Up Advantage:*\n"
        f"Regular SIP Corpus: {format_currency(r.regular_sip_corpus)}\n"
        f"Extra from Step\\-Up: *{format_currency(r.stepup_advantage)}*\n\n"
        f"💡 _Small annual increases create massive wealth\\._\n"
        f"_Sarathi\\-AI Business Technologies_ 📈"
    )


def format_swp_result(r: SWPResult) -> str:
    """Format SWP result for Telegram."""
    status = "✅ Sustainable" if r.is_sustainable else f"⚠️ Depleted in {r.corpus_lasted_months} months"
    return (
        f"💸 *SWP \\(Systematic Withdrawal\\) Plan*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 Initial Corpus: {format_currency(r.initial_corpus)}\n"
        f"💳 Monthly Withdrawal: {format_currency(r.monthly_withdrawal)}\n"
        f"📊 Return: {r.annual_return}% | Period: {r.years} yrs\n\n"
        f"📋 *Results:*\n"
        f"Total Withdrawn: {format_currency(r.total_withdrawn)}\n"
        f"Remaining Corpus: *{format_currency(r.remaining_corpus)}*\n"
        f"Status: *{status}*\n\n"
        f"💡 _Plan withdrawals wisely for a worry\\-free retirement\\._\n"
        f"_Sarathi\\-AI Business Technologies_ 💸"
    )


def format_delay_cost_result(r: DelayCostResult) -> str:
    """Format Delay Cost result for Telegram."""
    return (
        f"⏰ *Cost of Delay Report*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 SIP: {format_currency(r.monthly_sip)}/month\n"
        f"📅 Horizon: {r.years} yrs @ {r.annual_return}%\n"
        f"⏳ Delay: {r.delay_years} years\n\n"
        f"📊 *Impact:*\n"
        f"Start Today: *{format_currency(r.corpus_on_time)}*\n"
        f"Start After {r.delay_years} yrs: {format_currency(r.corpus_delayed)}\n"
        f"🔴 Cost of Delay: *{format_currency(r.cost_of_delay)}*\n\n"
        f"⚡ To match, you'd need:\n"
        f"*{format_currency(r.extra_sip_needed)}/month* after delay\\!\n\n"
        f"💡 _Every year you wait costs you lakhs\\._\n"
        f"_Sarathi\\-AI Business Technologies_ ⏰"
    )
