# -*- coding: utf-8 -*-
"""What a payment MUST cost - one answer, checked before every charge.

Founder, 29 Sep: "how can we prevent all payment endpoints to talk same rather different amount?
... is our payment bot watching all payments carefully before they are initiating? ... GST
collected properly for all."

THE PROBLEM THIS CLOSES. Nine places ask Razorpay for money (review fee x3, Level-2 fee as order
and as link for an AP and for My Business, admin payment links, the subscription order). On
29 Sep every one of them computed its amount correctly - fee from the shared rule, GST through
biz_nidaan.charge_with_gst. But nothing ENFORCED that; each was right because each was written
carefully. The ledger shows what that costs: between August and mid-September the same Silver
plan was charged Rs 588.00, 589.00, 588.82 and 590 as GST rounding changed in one path and not
another, and nothing noticed.

So:
  * `expected()` is the ONE answer to "what must this purpose cost", built from the same rules
    the endpoints use (review_fee_for, branch_l2_fee_for_claim, the plan's configured price,
    charge_with_gst). Nothing here invents a price.
  * `guard()` runs at every endpoint immediately before Razorpay is asked. If the amount about to
    be charged is not what `expected()` says, the charge is REFUSED - the customer is asked to
    refresh - and the super admins are told what was stopped. Fail closed: if the expected price
    cannot be worked out, the charge does not start either.
  * After the money moves, the Payment Guardian re-checks every recorded payment's GST split
    (biz_nidaan_pay_guard, check "price").
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("sarathi.nidaan.pricing")

# Purposes. A new way of taking money must add itself here - the guard refuses an unknown one.
L2_FEE = "l2_fee"                 # a branch / My Business Level-2 fee, bound to a claim
REVIEW_FEE = "review_fee"         # the tiered review fee, from the disputed amount
REVIEW_PURCHASE = "review_purchase"   # a review whose base fee was fixed when it was bought
SUBSCRIPTION = "subscription"     # a plan's first payment, at the plan's configured price
CUSTOM = "custom"                 # an admin payment link for an amount the admin typed
PURPOSES = (L2_FEE, REVIEW_FEE, REVIEW_PURCHASE, SUBSCRIPTION, CUSTOM)


class PriceMismatch(Exception):
    """The amount about to be charged is not what this purpose costs. Never charge."""


async def expected(purpose: str, *, claim_id: Optional[int] = None,
                   disputed_amount: Optional[int] = None, base_rupees: Optional[float] = None,
                   plan: str = "") -> dict:
    """{purpose, base_rupees, total_paise, gst_paise} for one charge, from the shared rules.

    Raises PriceMismatch when the price cannot be established - never guesses.
    """
    import biz_nidaan as n
    if purpose == L2_FEE:
        if not claim_id:
            raise PriceMismatch("a Level-2 fee needs its claim")
        p = await n.branch_l2_fee_for_claim(int(claim_id))
        if not p.get("charge_required"):
            raise PriceMismatch("no Level-2 fee is due on claim %s" % claim_id)
        base = float(p["fee"])
    elif purpose == REVIEW_FEE:
        base = float(await n.review_fee_for(disputed_amount))
    elif purpose in (REVIEW_PURCHASE, CUSTOM):
        if base_rupees is None or float(base_rupees) <= 0:
            raise PriceMismatch("%s needs its base amount" % purpose)
        base = float(base_rupees)
    elif purpose == SUBSCRIPTION:
        cfg = await n.get_plan_cfg(plan) if plan else None
        price = int((cfg or {}).get("price_paise") or 0)
        if not price:
            info = (getattr(n, "NIDAAN_RAZORPAY_PLANS", {}) or {}).get(plan) or {}
            price = int(info.get("amount_paise") or 0)
        if price <= 0:
            raise PriceMismatch("no configured price for plan %r" % plan)
        base = price / 100.0
    else:
        raise PriceMismatch("unknown payment purpose %r" % purpose)
    g = await n.charge_with_gst(base)
    return {"purpose": purpose, "base_rupees": base, "total_paise": int(g["total_paise"]),
            "gst_paise": int(round(float(g.get("gst") or 0) * 100))}


async def guard(purpose: str, amount_paise: int, **ctx) -> dict:
    """Call immediately before asking Razorpay for money. Returns the expected price; raises
    PriceMismatch (and tells the super admins) when the amount differs or cannot be checked."""
    try:
        exp = await expected(purpose, **ctx)
    except PriceMismatch as e:
        await _tell(purpose, amount_paise, None, str(e), ctx)
        raise
    except Exception as e:  # noqa: BLE001 - cannot check the price: do not charge
        await _tell(purpose, amount_paise, None, "price could not be checked: %s" % e, ctx)
        raise PriceMismatch("price could not be checked") from e
    if int(amount_paise) != exp["total_paise"]:
        why = "about to charge Rs %.2f, the price is Rs %.2f" % (int(amount_paise) / 100,
                                                                exp["total_paise"] / 100)
        await _tell(purpose, amount_paise, exp["total_paise"], why, ctx)
        raise PriceMismatch(why)
    return exp


async def _tell(purpose: str, amount_paise: int, expected_paise, why: str, ctx: dict) -> None:
    """A stopped charge is a code fault on our side - the super admins hear it at once."""
    logger.error("PRICE GUARD stopped a %s charge (%s): %s", purpose, ctx, why)
    try:
        import biz_nidaan_notifications as nn
        ids = [a["staff_id"] for a in await nn._super_admin_staff()]
        bits = ["Purpose: %s" % purpose]
        if ctx.get("claim_id"):
            bits.append("Claim: NP-%s" % ctx["claim_id"])
        if ctx.get("plan"):
            bits.append("Plan: %s" % ctx["plan"])
        if ids:
            await nn.notify_staff_inapp(
                ids, "\U0001f6d1 A payment was stopped before it started — wrong amount",
                "The price check refused a charge: %s.\n\n%s\n\nNobody was charged. The customer "
                "was asked to refresh and try again; if this repeats, a payment path has a fault."
                % (why, "\n".join(bits)),
                event_key="payment.price_guard", email=True)
    except Exception as e:  # noqa: BLE001 - the refusal stands whether or not the alert went
        logger.warning("price guard alert failed: %s", e)
