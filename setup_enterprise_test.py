"""
Create an Enterprise test tenant for plan testing.
Run: py -3.12 setup_enterprise_test.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import biz_database as db

ENTERPRISE_TEST = {
    "firm_name": "Verma Wealth Partners",
    "owner_name": "Amit Verma",
    "phone": "9000000001",
    "email": "amit@vermawp.com",
    "city": "Mumbai",
}


async def main():
    await db.init_db()

    # Check if already exists
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT tenant_id, plan FROM tenants WHERE phone = ?",
            (ENTERPRISE_TEST["phone"],))
        existing = await cur.fetchone()

    if existing:
        tid = existing["tenant_id"]
        print(f"Tenant already exists (ID: {tid}, plan: {existing['plan']})")
        if existing["plan"] != "enterprise":
            pf = db.PLAN_FEATURES["enterprise"]
            await db.update_tenant(tid, plan="enterprise", max_agents=pf["max_agents"])
            print(f"  → Upgraded to enterprise (max_agents={pf['max_agents']})")
        print_details(tid)
        return

    result = await db.create_tenant_with_owner(
        firm_name=ENTERPRISE_TEST["firm_name"],
        owner_name=ENTERPRISE_TEST["owner_name"],
        phone=ENTERPRISE_TEST["phone"],
        email=ENTERPRISE_TEST["email"],
        city=ENTERPRISE_TEST["city"],
        account_type="firm",
        signup_channel="web",
    )
    tid = result["tenant_id"]

    pf = db.PLAN_FEATURES["enterprise"]
    await db.update_tenant(tid, plan="enterprise", max_agents=pf["max_agents"])

    print(f"✅ Enterprise test tenant created!")
    print_details(tid)


def print_details(tid):
    print(f"\n{'='*50}")
    print(f"  ENTERPRISE TEST ACCOUNT")
    print(f"{'='*50}")
    print(f"  Tenant ID  : {tid}")
    print(f"  Firm Name  : {ENTERPRISE_TEST['firm_name']}")
    print(f"  Owner      : {ENTERPRISE_TEST['owner_name']}")
    print(f"  Phone      : {ENTERPRISE_TEST['phone']}")
    print(f"  Email      : {ENTERPRISE_TEST['email']}")
    print(f"  Plan       : enterprise")
    print(f"  Max Agents : 26 (Admin + 25)")
    print(f"{'='*50}")
    print(f"\n  LOGIN: Go to dashboard.html → enter phone {ENTERPRISE_TEST['phone']}")
    print(f"  OTP will be sent via WhatsApp (or check server logs)")
    print(f"  Features: Admin controls, custom branding, API access,")
    print(f"            bulk campaigns, Google Drive, team dashboard")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
