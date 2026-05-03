# =============================================================================
#  biz_campaigns.py — Bulk Communication / Campaign Engine for Sarathi-AI
# =============================================================================
#
#  Provides:
#    - Create campaigns (birthday, festival, announcement, promotion)
#    - Filter recipients by criteria (all leads, stage, city, need_type)
#    - Send via WhatsApp (Cloud API or wa.me links batch)
#    - Send via Email (if SMTP configured)
#    - Track delivery status per recipient
#    - Campaign analytics (sent, delivered, failed)
#
# =============================================================================

import asyncio
import logging
from datetime import datetime
from typing import Optional

import biz_database as db
import biz_whatsapp as wa
import biz_email as email_svc

logger = logging.getLogger("sarathi.campaigns")

# =============================================================================
#  CAMPAIGN TYPES
# =============================================================================

CAMPAIGN_TYPES = {
    "birthday": {"label": "🎂 Birthday Wishes", "icon": "🎂"},
    "anniversary": {"label": "💍 Anniversary Wishes", "icon": "💍"},
    "festival": {"label": "🎉 Festival Greeting", "icon": "🎉"},
    "announcement": {"label": "📢 Announcement", "icon": "📢"},
    "promotion": {"label": "🏷️ Product Promotion", "icon": "🏷️"},
    "renewal_reminder": {"label": "🔄 Renewal Reminder", "icon": "🔄"},
    "custom": {"label": "✉️ Custom Message", "icon": "✉️"},
}


# =============================================================================
#  DATABASE SCHEMA (campaigns + campaign_recipients tables)
# =============================================================================

CAMPAIGNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       INTEGER NOT NULL,
    agent_id        INTEGER,
    campaign_type   TEXT NOT NULL DEFAULT 'custom',
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    channel         TEXT NOT NULL DEFAULT 'whatsapp',
    filters         TEXT DEFAULT '{}',
    status          TEXT DEFAULT 'draft',
    total_recipients INTEGER DEFAULT 0,
    sent_count      INTEGER DEFAULT 0,
    failed_count    INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    sent_at         TEXT,
    completed_at    TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE IF NOT EXISTS campaign_recipients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id     INTEGER NOT NULL,
    lead_id         INTEGER,
    phone           TEXT,
    email           TEXT,
    name            TEXT,
    status          TEXT DEFAULT 'pending',
    wa_link         TEXT,
    sent_at         TEXT,
    error           TEXT,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);
"""


async def init_campaigns_db():
    """Create campaigns tables if they don't exist."""
    async with db._get_db() as conn:
        await conn.executescript(CAMPAIGNS_SCHEMA)
        await conn.commit()
    logger.info("✅ Campaigns tables ready")


# =============================================================================
#  CAMPAIGN CRUD
# =============================================================================

async def create_campaign(
    tenant_id: int,
    title: str,
    message: str,
    campaign_type: str = "custom",
    channel: str = "whatsapp",
    filters: dict = None,
    agent_id: int = None,
) -> int:
    """Create a new campaign. Returns campaign_id."""
    import json
    async with db._get_db() as conn:
        cursor = await conn.execute(
            """INSERT INTO campaigns
               (tenant_id, agent_id, campaign_type, title, message, channel, filters, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')""",
            (tenant_id, agent_id, campaign_type, title, message, channel,
             json.dumps(filters or {})),
        )
        await conn.commit()
        return cursor.lastrowid


async def get_campaign(campaign_id: int) -> Optional[dict]:
    """Get a campaign by ID."""
    async with db._get_db() as conn:
        conn.row_factory = db.aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_campaigns(tenant_id: int, limit: int = 20) -> list:
    """List campaigns for a tenant."""
    async with db._get_db() as conn:
        conn.row_factory = db.aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM campaigns WHERE tenant_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (tenant_id, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def delete_campaign(campaign_id: int, tenant_id: int) -> bool:
    """Delete a draft campaign."""
    async with db._get_db() as conn:
        await conn.execute(
            "DELETE FROM campaign_recipients WHERE campaign_id = ?",
            (campaign_id,),
        )
        cursor = await conn.execute(
            "DELETE FROM campaigns WHERE campaign_id = ? AND tenant_id = ? AND status = 'draft'",
            (campaign_id, tenant_id),
        )
        await conn.commit()
        return cursor.rowcount > 0


# =============================================================================
#  RECIPIENT SELECTION
# =============================================================================

async def select_recipients(
    tenant_id: int,
    campaign_id: int,
    filters: dict = None,
) -> int:
    """
    Select recipients based on filters and add to campaign_recipients.
    Filters: {"stage": "pitched", "city": "Mumbai", "need_type": "life"}
    Returns count of recipients added.
    """
    # Get all agents for this tenant
    agents = await db.get_agents_by_tenant(tenant_id)
    if not agents:
        return 0

    all_leads = []
    for agent in agents:
        leads = await db.get_leads_by_agent(agent["agent_id"])
        all_leads.extend(leads)

    # Apply filters
    filters = filters or {}
    filtered = all_leads

    if filters.get("stage"):
        filtered = [l for l in filtered if l.get("stage") == filters["stage"]]
    if filters.get("city"):
        city = filters["city"].lower()
        filtered = [l for l in filtered if city in (l.get("city", "").lower())]
    if filters.get("need_type"):
        need = filters["need_type"].lower()
        filtered = [l for l in filtered if need in (l.get("need_type", "").lower())]

    # Deduplicate by phone
    seen_phones = set()
    unique_leads = []
    for lead in filtered:
        phone = lead.get("phone", "").strip()
        if phone and phone not in seen_phones:
            seen_phones.add(phone)
            unique_leads.append(lead)

    # Insert recipients
    count = 0
    async with db._get_db() as conn:
        for lead in unique_leads:
            await conn.execute(
                """INSERT INTO campaign_recipients
                   (campaign_id, lead_id, phone, email, name, status)
                   VALUES (?, ?, ?, ?, ?, 'pending')""",
                (campaign_id, lead.get("lead_id"), lead.get("phone", ""),
                 lead.get("email", ""), lead.get("name", "")),
            )
            count += 1

        # Update campaign total
        await conn.execute(
            "UPDATE campaigns SET total_recipients = ? WHERE campaign_id = ?",
            (count, campaign_id),
        )
        await conn.commit()

    return count


async def get_recipients(campaign_id: int) -> list:
    """Get all recipients for a campaign."""
    async with db._get_db() as conn:
        conn.row_factory = db.aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM campaign_recipients WHERE campaign_id = ? ORDER BY id",
            (campaign_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


# =============================================================================
#  CAMPAIGN EXECUTION
# =============================================================================

async def send_campaign(campaign_id: int, tenant_id: int) -> dict:
    """
    Execute a campaign — send messages to all pending recipients.
    Returns: {"sent": int, "failed": int, "links": [wa.me links if no API]}
    """
    campaign = await get_campaign(campaign_id)
    if not campaign or campaign["tenant_id"] != tenant_id:
        return {"error": "Campaign not found"}

    if campaign["status"] == "completed":
        return {"error": "Campaign already completed"}

    # Mark as sending
    async with db._get_db() as conn:
        await conn.execute(
            "UPDATE campaigns SET status = 'sending', sent_at = ? WHERE campaign_id = ?",
            (datetime.now().isoformat(), campaign_id),
        )
        await conn.commit()

    recipients = await get_recipients(campaign_id)
    channel = campaign.get("channel", "whatsapp")
    message_template = campaign["message"]

    sent = 0
    failed = 0
    wa_links = []

    for recip in recipients:
        if recip["status"] != "pending":
            continue

        # Personalize message
        name = recip.get("name", "Sir/Ma'am")
        first_name = name.split()[0] if name else "Sir/Ma'am"
        personal_msg = message_template.replace("{name}", name).replace("{first_name}", first_name)

        try:
            if channel == "whatsapp":
                phone = recip.get("phone", "")
                if not phone:
                    raise ValueError("No phone number")

                result = await wa.send_or_link(phone, personal_msg)

                if result.get("method") == "link":
                    # Fallback — collect links for manual sending
                    wa_links.append({
                        "name": name,
                        "phone": phone,
                        "link": result["wa_link"],
                    })
                    status = "link_generated"
                else:
                    status = "sent" if result.get("success") else "failed"

                async with db._get_db() as conn:
                    await conn.execute(
                        """UPDATE campaign_recipients
                           SET status = ?, wa_link = ?, sent_at = ?
                           WHERE id = ?""",
                        (status, result.get("wa_link", ""),
                         datetime.now().isoformat(), recip["id"]),
                    )
                    await conn.commit()

                if status in ("sent", "link_generated"):
                    sent += 1
                else:
                    failed += 1

            elif channel == "email":
                email = recip.get("email", "")
                if not email or not email_svc.is_enabled():
                    raise ValueError("Email not available")

                # Send email
                await email_svc.send_email(
                    to_email=email,
                    subject=campaign["title"],
                    html_body=email_svc._wrap_template(
                        campaign["title"],
                        f"<p>{personal_msg}</p>",
                    ),
                )

                async with db._get_db() as conn:
                    await conn.execute(
                        "UPDATE campaign_recipients SET status = 'sent', sent_at = ? WHERE id = ?",
                        (datetime.now().isoformat(), recip["id"]),
                    )
                    await conn.commit()
                sent += 1

        except Exception as e:
            failed += 1
            async with db._get_db() as conn:
                await conn.execute(
                    "UPDATE campaign_recipients SET status = 'failed', error = ? WHERE id = ?",
                    (str(e)[:200], recip["id"]),
                )
                await conn.commit()
            logger.warning("Campaign send failed for %s: %s", recip.get("name"), e)

        # Rate limit: small delay between sends
        await asyncio.sleep(0.5)

    # Update campaign stats
    async with db._get_db() as conn:
        await conn.execute(
            """UPDATE campaigns
               SET status = 'completed', sent_count = ?, failed_count = ?,
                   completed_at = ?
               WHERE campaign_id = ?""",
            (sent, failed, datetime.now().isoformat(), campaign_id),
        )
        await conn.commit()

    logger.info("Campaign #%d completed: %d sent, %d failed", campaign_id, sent, failed)

    return {
        "sent": sent,
        "failed": failed,
        "total": len(recipients),
        "wa_links": wa_links if wa_links else None,
    }


# =============================================================================
#  CAMPAIGN ANALYTICS
# =============================================================================

async def get_campaign_stats(campaign_id: int) -> dict:
    """Get execution stats for a campaign."""
    campaign = await get_campaign(campaign_id)
    if not campaign:
        return {}

    async with db._get_db() as conn:
        cursor = await conn.execute(
            """SELECT status, COUNT(*) as count
               FROM campaign_recipients
               WHERE campaign_id = ?
               GROUP BY status""",
            (campaign_id,),
        )
        status_counts = {row[0]: row[1] for row in await cursor.fetchall()}

    return {
        "campaign_id": campaign_id,
        "title": campaign["title"],
        "type": campaign["campaign_type"],
        "channel": campaign["channel"],
        "status": campaign["status"],
        "total": campaign["total_recipients"],
        "sent": status_counts.get("sent", 0),
        "link_generated": status_counts.get("link_generated", 0),
        "failed": status_counts.get("failed", 0),
        "pending": status_counts.get("pending", 0),
        "created_at": campaign["created_at"],
        "sent_at": campaign.get("sent_at"),
        "completed_at": campaign.get("completed_at"),
    }
