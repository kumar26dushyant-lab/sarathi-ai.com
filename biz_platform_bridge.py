"""
biz_platform_bridge.py — Sarathi ⇄ Nidaan internal boundary.

This is the ONLY module permitted to read or write Sarathi's product tables
(`tenants`, `agents`) on behalf of the Nidaan product. It exists to keep the two
co-hosted products decoupled: Nidaan calls these named operations instead of
reaching into Sarathi's schema directly.

Today both products share one SQLite file, so these functions run local SQL.
This seam is the natural place to become a network API if the products are ever
split into separate services — only this file would change, not Nidaan's logic.

RULE: Nidaan code (biz_nidaan*.py) must NOT contain `FROM tenants` / `FROM agents`
(or any other Sarathi table). Route every such need through a function here.

The SQL below was moved verbatim from biz_nidaan.py (same statements, same order,
same commit boundaries) so behavior is unchanged.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import aiosqlite

logger = logging.getLogger("sarathi.platform_bridge")

# Same resolution as biz_nidaan.py so the bridge always targets the same DB
# as the code that used to run these statements inline.
DB_PATH = os.environ.get("DB_PATH", "sarathi_biz.db")


async def upsert_bundle_tenant(*, email: str, owner_name: str, firm_name: str,
                               phone: str, sarathi_plan: str,
                               bundled_until: str) -> int:
    """Find-or-create a Sarathi tenant for a Nidaan bundle and grant/refresh
    bundled access. For a brand-new tenant, also create the owner agent so the
    tenant is usable on first login. Returns the Sarathi tenant_id.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT tenant_id FROM tenants WHERE email=? LIMIT 1", (email,)
        )
        row = await cur.fetchone()
        if row:
            tenant_id = row["tenant_id"]
            # Update plan + source + expiry + reactivate (covers expired/trial tenants)
            await conn.execute(
                """UPDATE tenants
                   SET plan=?, plan_source='nidaan_bundle', bundled_until=?,
                       subscription_status='active', updated_at=CURRENT_TIMESTAMP
                   WHERE tenant_id=?""",
                (sarathi_plan, bundled_until, tenant_id),
            )
        else:
            # Create a new Sarathi tenant (they'll login via magic link from Nidaan dashboard)
            cur2 = await conn.execute(
                """INSERT INTO tenants
                       (owner_name, firm_name, email, phone,
                        plan, plan_source, bundled_until, subscription_status)
                   VALUES (?, ?, ?, ?, ?, 'nidaan_bundle', ?, 'active')""",
                (owner_name, firm_name or "", email, phone or "",
                 sarathi_plan, bundled_until),
            )
            tenant_id = cur2.lastrowid
            # Create owner agent so the tenant is usable immediately on first login
            tg_placeholder = f"web_{tenant_id}"
            await conn.execute(
                """INSERT INTO agents
                       (tenant_id, telegram_id, name, phone, email, role, lang)
                   VALUES (?, ?, ?, ?, ?, 'owner', 'en')""",
                (tenant_id, tg_placeholder, owner_name, phone or "", email),
            )
        await conn.commit()
    return tenant_id


async def shorten_bundle_tenant(*, tenant_id: int, grace_until: str) -> Optional[bool]:
    """Shorten a bundle tenant's `bundled_until` to grace_until (only shortens,
    never extends) and mark lifetime_trial_used so the ex-bundle user can't
    restart a Sarathi free trial. Returns:
        None  → tenant row not found
        False → skipped (existing grace already <= grace_until)
        True  → updated
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT bundled_until, plan_source FROM tenants WHERE tenant_id=?",
            (tenant_id,))).fetchone()
        if not row:
            return None
        cur_bu = (row["bundled_until"] or "")
        # Only shorten — never extend.
        if cur_bu and cur_bu <= grace_until:
            return False
        await conn.execute(
            """UPDATE tenants
               SET bundled_until=?, lifetime_trial_used=1,
                   updated_at=CURRENT_TIMESTAMP
               WHERE tenant_id=? AND plan_source='nidaan_bundle'""",
            (grace_until, tenant_id))
        await conn.commit()
    return True


async def find_bundle_tenants_ending_on(target_date: str) -> list[dict]:
    """Sarathi bundle tenants whose `bundled_until` equals target_date
    (YYYY-MM-DD). Source for the T-4 / T-2 / T-0 bundle-ending nudges.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT tenant_id, firm_name, owner_name, email, phone, plan, "
            "       bundled_until "
            "FROM tenants WHERE plan_source='nidaan_bundle' "
            "AND date(bundled_until) = ?", (target_date,))
        return [dict(r) for r in await cur.fetchall()]
