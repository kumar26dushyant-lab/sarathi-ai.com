# =============================================================================
#  biz_reminders.py — Sarathi-AI Business Technologies: Reminder & Greeting Engine
# =============================================================================
#
#  Background scheduler that runs daily scans for:
#    1. Birthday greetings (9:00 AM)
#    2. Anniversary greetings (9:00 AM)
#    3. Policy renewal reminders (T-60, T-30, T-15, T-7, T-1)
#    4. Follow-up reminders
#    5. Daily agent summary (8:30 AM)
#    6. Trial/subscription expiry reminders (Day 10, 13, 14, 15 → deactivate)
#    7. PROACTIVE AI ASSISTANT (hourly nudges throughout the day)
#       - Real-time follow-up nudges (morning + afternoon + evening)
#       - Meeting prep intelligence (30 min before)
#       - Stale lead alerts (weekly)
#       - Celebration assistant (eve-of-birthday/anniversary)
#       - Win celebrations + momentum (on deal close, weekly digest)
#       - Smart suggestions (post-action, idle-time)
#
# =============================================================================

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Callable, Optional

import aiosqlite
import biz_database as db
import biz_email as email_svc
import biz_whatsapp as wa
import biz_resilience as resilience
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("sarathi.reminders")

# Callback to send Telegram alerts
_telegram_alert: Optional[Callable] = None
_queue_processor: Optional[Callable] = None


def set_telegram_callback(callback: Callable):
    """Register the Telegram bot's send function for alerts."""
    global _telegram_alert
    _telegram_alert = callback
    logger.info("Telegram alert callback registered")


def set_queue_callback(callback: Callable):
    """Register the message queue processor (from biz_resilience)."""
    global _queue_processor
    _queue_processor = callback
    logger.info("Message queue processor registered")


async def _send_telegram(telegram_id: str, message: str, reply_markup=None):
    """Send a Telegram alert if callback is set."""
    if _telegram_alert:
        try:
            await _telegram_alert(telegram_id, message, reply_markup=reply_markup)
        except Exception as e:
            logger.error("Telegram alert failed: %s", e)


# =============================================================================
#  DAILY GREETING SCAN
# =============================================================================

async def run_birthday_scan():
    """Scan for today's birthdays and send greetings."""
    logger.info("Running birthday scan...")
    birthdays = await db.get_todays_birthdays()

    sent_count = 0
    for lead in birthdays:
        # Skip if already sent today
        if await db.was_greeting_sent_today(lead['lead_id'], 'birthday'):
            continue

        # Send WhatsApp greeting
        phone = lead.get('whatsapp') or lead.get('phone')
        if phone:
            # Build greeting message
            greeting_msg = wa.send_birthday_greeting
            result = await wa.send_birthday_greeting(
                to=phone,
                client_name=lead['name'],
                agent_name=lead.get('agent_name', 'Your Advisor'),
                company=lead.get('firm_name', 'Sarathi-AI'),
                tagline=lead.get('brand_tagline', 'AI-Powered Financial Advisor CRM'),
            )
            if result.get('success'):
                await db.log_greeting(
                    lead['lead_id'], lead['agent_id'],
                    'birthday', 'whatsapp'
                )
                sent_count += 1
            elif result.get('retryable') or result.get('method') == 'queued':
                # Network error — queue for retry
                logger.warning("Birthday greeting queued for retry: %s → %s",
                               lead['name'], phone)
                sent_count += 1  # Queued counts as handled
            else:
                logger.error("Birthday greeting failed for %s → %s: %s",
                             lead['name'], phone, result.get('error', 'Unknown'))

        # Notify agent via Telegram
        agent_tid = lead.get('agent_telegram_id')
        if agent_tid:
            _hi = lead.get('agent_lang', 'en') == 'hi'
            if _hi:
                await _send_telegram(
                    agent_tid,
                    f"🎂 *जन्मदिन अलर्ट!*\n\n"
                    f"आज *{lead['name']}* का जन्मदिन है!\n"
                    f"📞 {lead.get('phone', 'N/A')}\n\n"
                    f"{'✅ WhatsApp शुभकामनाएं स्वचालित भेजी गईं।' if phone else '⚠️ कोई फ़ोन नंबर नहीं — कृपया मैन्युअली शुभकामनाएं दें।'}"
                )
            else:
                await _send_telegram(
                    agent_tid,
                    f"🎂 *Birthday Alert!*\n\n"
                    f"Today is *{lead['name']}*'s birthday!\n"
                    f"📞 {lead.get('phone', 'N/A')}\n\n"
                    f"{'✅ WhatsApp greeting sent automatically.' if phone else '⚠️ No phone number — please greet manually.'}"
                )

    logger.info("Birthday scan complete: %d greetings sent", sent_count)
    return sent_count


async def run_anniversary_scan():
    """Scan for today's anniversaries and send greetings."""
    logger.info("Running anniversary scan...")
    anniversaries = await db.get_todays_anniversaries()

    sent_count = 0
    for lead in anniversaries:
        if await db.was_greeting_sent_today(lead['lead_id'], 'anniversary'):
            continue

        phone = lead.get('whatsapp') or lead.get('phone')
        if phone:
            result = await wa.send_anniversary_greeting(
                to=phone,
                client_name=lead['name'],
                agent_name=lead.get('agent_name', 'Your Advisor'),
                company=lead.get('firm_name', 'Sarathi-AI'),
                tagline=lead.get('brand_tagline', 'AI-Powered Financial Advisor CRM'),
            )
            if result.get('success'):
                await db.log_greeting(
                    lead['lead_id'], lead['agent_id'],
                    'anniversary', 'whatsapp'
                )
                sent_count += 1
            elif result.get('retryable') or result.get('method') == 'queued':
                logger.warning("Anniversary greeting queued for retry: %s → %s",
                               lead['name'], phone)
                sent_count += 1
            else:
                logger.error("Anniversary greeting failed for %s → %s: %s",
                             lead['name'], phone, result.get('error', 'Unknown'))

        agent_tid = lead.get('agent_telegram_id')
        if agent_tid:
            _hi = lead.get('agent_lang', 'en') == 'hi'
            if _hi:
                await _send_telegram(
                    agent_tid,
                    f"💍 *विवाह वार्षिकोत्सव अलर्ट!*\n\n"
                    f"आज *{lead['name']}* की विवाह वार्षिकोत्सव है!\n"
                    f"📞 {lead.get('phone', 'N/A')}\n\n"
                    f"{'✅ WhatsApp शुभकामनाएं भेजी गईं।' if phone else '⚠️ कोई फ़ोन नहीं — कृपया मैन्युअली शुभकामनाएं दें।'}"
                )
            else:
                await _send_telegram(
                    agent_tid,
                    f"💍 *Anniversary Alert!*\n\n"
                    f"Today is *{lead['name']}*'s anniversary!\n"
                    f"📞 {lead.get('phone', 'N/A')}\n\n"
                    f"{'✅ WhatsApp greeting sent.' if phone else '⚠️ No phone — please greet manually.'}"
                )

    logger.info("Anniversary scan complete: %d greetings sent", sent_count)
    return sent_count


# =============================================================================
#  RENEWAL REMINDER SCAN
# =============================================================================

async def run_renewal_scan():
    """Scan for upcoming policy renewals and send reminders."""
    logger.info("Running renewal scan...")

    # Step 0: auto-advance expired renewal dates based on premium_mode
    try:
        advanced = await db.advance_expired_renewals()
        if advanced:
            logger.info("Auto-advanced %d expired renewal dates", advanced)
    except Exception as e:
        logger.error("advance_expired_renewals failed: %s", e)

    # Mode-aware trigger days
    _MODE_TRIGGERS = {
        'monthly':     {7, 3, 1, 0},
        'quarterly':   {15, 7, 3, 1, 0},
        'half-yearly': {30, 15, 7, 3, 1, 0},
        'half_yearly': {30, 15, 7, 3, 1, 0},
        'annual':      {60, 30, 15, 7, 3, 1, 0},
        'yearly':      {60, 30, 15, 7, 3, 1, 0},
    }

    agents = await db.get_all_active_agents()
    total_sent = 0

    for agent in agents:
        renewals = await db.get_upcoming_renewals(agent['agent_id'], days_ahead=60)

        for policy in renewals:
            renewal_date = policy.get('renewal_date')
            if not renewal_date:
                continue

            try:
                ren_dt = datetime.fromisoformat(renewal_date)
                days_left = (ren_dt - datetime.now()).days
            except (ValueError, TypeError):
                continue

            # Pick trigger days based on premium_mode
            mode = (policy.get('premium_mode') or 'annual').lower().strip()
            trigger_days = _MODE_TRIGGERS.get(mode, _MODE_TRIGGERS['annual'])
            if days_left not in trigger_days:
                continue

            # Send WhatsApp to client
            phone = policy.get('client_whatsapp') or policy.get('client_phone')
            if phone:
                result = await wa.send_renewal_reminder(
                    to=phone,
                    client_name=policy.get('client_name', 'Client'),
                    policy_number=policy.get('policy_number', 'N/A'),
                    renewal_date=renewal_date,
                    days_left=days_left,
                    agent_name=agent.get('name', 'Your Advisor'),
                    agent_phone=agent.get('brand_phone', ''),
                    company=agent.get('firm_name', 'Sarathi-AI'),
                    cta=agent.get('brand_cta', 'Secure Your Future Today'),
                )
                if result.get('success'):
                    total_sent += 1
                elif result.get('retryable'):
                    logger.warning("Renewal reminder queued for retry: %s → %s (%s)",
                                   policy.get('client_name'), phone,
                                   policy.get('policy_number'))
                    # Enqueue for later delivery
                    await resilience.enqueue_message(
                        channel='whatsapp', recipient=phone,
                        message=f"Renewal reminder for policy {policy.get('policy_number', 'N/A')}",
                        tenant_id=agent.get('tenant_id'),
                        agent_id=agent.get('agent_id'))
                    total_sent += 1  # Queued counts as handled
                else:
                    logger.error("Renewal reminder failed: %s → %s: %s",
                                 policy.get('client_name'), phone,
                                 result.get('error', 'Unknown'))

            # Notify agent
            _hi = agent.get('lang', 'en') == 'hi'
            if _hi:
                await _send_telegram(
                    agent['telegram_id'],
                    f"🔔 *नवीनीकरण रिमाइंडर*\n\n"
                    f"क्लाइंट: *{policy.get('client_name')}*\n"
                    f"पॉलिसी: #{policy.get('policy_number', 'N/A')}\n"
                    f"प्लान: {policy.get('plan_name', 'N/A')}\n"
                    f"प्रीमियम: ₹{policy.get('premium', 0):,.0f}\n"
                    f"नवीनीकरण: *{renewal_date}* ({days_left} दिन)\n\n"
                    f"📞 {phone or 'कोई फ़ोन नहीं'}"
                )
            else:
                await _send_telegram(
                    agent['telegram_id'],
                    f"🔔 *Renewal Reminder*\n\n"
                    f"Client: *{policy.get('client_name')}*\n"
                    f"Policy: #{policy.get('policy_number', 'N/A')}\n"
                    f"Plan: {policy.get('plan_name', 'N/A')}\n"
                    f"Premium: ₹{policy.get('premium', 0):,.0f}\n"
                    f"Renewal: *{renewal_date}* ({days_left} days)\n\n"
                    f"📞 {phone or 'No phone'}"
                )

    logger.info("Renewal scan complete: %d reminders sent", total_sent)
    return total_sent


# =============================================================================
#  FOLLOW-UP REMINDER SCAN
# =============================================================================

async def run_followup_scan():
    """Scan for today's follow-up tasks and notify agents."""
    logger.info("Running follow-up scan...")
    agents = await db.get_all_active_agents()
    total = 0

    for agent in agents:
        followups = await db.get_pending_followups(agent['agent_id'])
        if not followups:
            continue

        # Build summary message
        _hi = agent.get('lang', 'en') == 'hi'
        header = 'आज के फॉलो-अप्स' if _hi else "Today's Follow-ups"
        lines = [f"📋 *{header}*\n"]
        for i, fu in enumerate(followups[:10], 1):
            overdue = ""
            if fu.get('follow_up_date'):
                try:
                    fu_dt = datetime.fromisoformat(fu['follow_up_date'])
                    if fu_dt.date() < datetime.now().date():
                        overdue = f" 🔴 {'बकाया' if _hi else 'OVERDUE'}"
                except ValueError:
                    pass
            lines.append(
                f"{i}. *{fu.get('lead_name', 'Unknown')}*{overdue}\n"
                f"   📞 {fu.get('lead_phone', 'N/A')} | {fu.get('type', 'follow-up')}\n"
                f"   📝 {fu.get('summary', 'No notes')[:50]}"
            )
            total += 1

        if len(followups) > 10:
            lines.append(f"\n...and {len(followups) - 10} more")

        await _send_telegram(agent['telegram_id'], "\n".join(lines))

    logger.info("Follow-up scan complete: %d tasks sent", total)
    return total


# =============================================================================
#  DAILY SUMMARY
# =============================================================================

async def send_daily_summary():
    """Send daily business summary to all agents at 8:30 AM."""
    logger.info("Generating daily summaries...")
    agents = await db.get_all_active_agents()

    for agent in agents:
        stats = await db.get_agent_stats(agent['agent_id'])
        pipeline = stats.get('pipeline', {})

        # Today's agenda
        followups = await db.get_pending_followups(agent['agent_id'])
        birthdays = await db.get_todays_birthdays(agent['agent_id'])
        anniversaries = await db.get_todays_anniversaries(agent['agent_id'])
        renewals = await db.get_upcoming_renewals(agent['agent_id'], days_ahead=7)

        _hi = agent.get('lang', 'en') == 'hi'
        if _hi:
            msg = (
                f"☀️ *सुप्रभात! दैनिक बिज़नेस सारांश*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📅 {datetime.now().strftime('%A, %B %d, %Y')}\n\n"
                f"📊 *आज का एजेंडा:*\n"
                f"  📋 फॉलो-अप्स: *{len(followups)}*\n"
                f"  🎂 जन्मदिन: *{len(birthdays)}*\n"
                f"  💍 वार्षिकोत्सव: *{len(anniversaries)}*\n"
                f"  🔄 नवीनीकरण (7 दिन): *{len(renewals)}*\n\n"
                f"📈 *पाइपलाइन:*\n"
                f"  🎯 प्रॉस्पेक्ट: {pipeline.get('prospect', 0)}\n"
                f"  📞 संपर्क किए: {pipeline.get('contacted', 0)}\n"
                f"  📊 पिच किए: {pipeline.get('pitched', 0)}\n"
                f"  📄 प्रस्ताव भेजे: {pipeline.get('proposal_sent', 0)}\n"
                f"  🤝 बातचीत: {pipeline.get('negotiation', 0)}\n\n"
                f"🏆 *पोर्टफोलियो:*\n"
                f"  ✅ सक्रिय पॉलिसी: {stats.get('active_policies', 0)}\n"
                f"  💰 कुल प्रीमियम: ₹{stats.get('total_premium', 0):,.0f}\n"
                f"  📊 कुल लीड्स: {stats.get('total_leads', 0)}\n\n"
                f"💪 _आज का दिन शानदार बनाएं!_\n"
                "_Sarathi\\-AI Business Technologies_ 🛡️"
            )
        else:
            msg = (
                f"☀️ *Good Morning! Daily Business Summary*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📅 {datetime.now().strftime('%A, %B %d, %Y')}\n\n"
                f"📊 *Today's Agenda:*\n"
                f"  📋 Follow-ups due: *{len(followups)}*\n"
                f"  🎂 Birthdays: *{len(birthdays)}*\n"
                f"  💍 Anniversaries: *{len(anniversaries)}*\n"
                f"  🔄 Renewals (7 days): *{len(renewals)}*\n\n"
                f"📈 *Pipeline Overview:*\n"
                f"  🎯 Prospects: {pipeline.get('prospect', 0)}\n"
                f"  📞 Contacted: {pipeline.get('contacted', 0)}\n"
                f"  📊 Pitched: {pipeline.get('pitched', 0)}\n"
                f"  📄 Proposals: {pipeline.get('proposal_sent', 0)}\n"
                f"  🤝 Negotiation: {pipeline.get('negotiation', 0)}\n\n"
                f"🏆 *Portfolio:*\n"
                f"  ✅ Active Policies: {stats.get('active_policies', 0)}\n"
                f"  💰 Total Premium: ₹{stats.get('total_premium', 0):,.0f}\n"
                f"  📊 Total Leads: {stats.get('total_leads', 0)}\n\n"
                f"💪 _Make today count!_\n"
                "_Sarathi\\-AI Business Technologies_ 🛡️"
            )

        await _send_telegram(agent['telegram_id'], msg)

    logger.info("Daily summaries sent to %d agents", len(agents))


# =============================================================================
#  TRIAL / SUBSCRIPTION EXPIRY REMINDERS
# =============================================================================

TRIAL_REMINDER_DAYS = {10, 13, 14}  # Days after trial start to send reminders (before expiry)
GRACE_PERIOD_DAYS = 10              # Days 15-25: daily reminders after deactivation
DATA_WIPE_DAY = 25                  # Day 25: full data wipe


async def _wipe_tenant_data(tenant_id: int, firm_name: str):
    """
    Completely wipe all tenant data — leads, policies, interactions,
    reminders, greetings, calculator sessions, summaries, agents.
    Called on Day 25 when tenant hasn't subscribed.
    """
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            # Get all agent_ids for this tenant
            cursor = await conn.execute(
                "SELECT agent_id FROM agents WHERE tenant_id = ?", (tenant_id,))
            agent_rows = await cursor.fetchall()
            agent_ids = [r[0] for r in agent_rows]

            if agent_ids:
                placeholders = ','.join('?' * len(agent_ids))
                # Delete all agent-scoped data
                await conn.execute(f"DELETE FROM leads WHERE agent_id IN ({placeholders})", agent_ids)
                await conn.execute(f"DELETE FROM policies WHERE agent_id IN ({placeholders})", agent_ids)
                await conn.execute(f"DELETE FROM interactions WHERE agent_id IN ({placeholders})", agent_ids)
                await conn.execute(f"DELETE FROM reminders WHERE agent_id IN ({placeholders})", agent_ids)
                await conn.execute(f"DELETE FROM greetings_log WHERE agent_id IN ({placeholders})", agent_ids)
                await conn.execute(f"DELETE FROM calculator_sessions WHERE agent_id IN ({placeholders})", agent_ids)
                await conn.execute(f"DELETE FROM daily_summary WHERE agent_id IN ({placeholders})", agent_ids)

            # Delete agents and invite codes
            await conn.execute("DELETE FROM agents WHERE tenant_id = ?", (tenant_id,))
            await conn.execute("DELETE FROM invite_codes WHERE tenant_id = ?", (tenant_id,))

            # Mark tenant as wiped (keep the row for device-lock checks)
            await conn.execute(
                "UPDATE tenants SET is_active = 0, subscription_status = 'wiped', "
                "firm_name = firm_name || ' [WIPED]' WHERE tenant_id = ?",
                (tenant_id,)
            )
            await conn.commit()

        logger.warning("🗑️ DATA WIPED for tenant %d (%s) — all leads, policies, agents removed",
                       tenant_id, firm_name)
    except Exception as e:
        logger.error("Data wipe failed for tenant %d: %s", tenant_id, e, exc_info=True)


async def run_trial_expiry_scan():
    """
    Enhanced trial expiry scan with 3-stage deactivation:
      1. Pre-expiry reminders (Day 10, 13, 14)
      2. Day 15: Deactivate account + warn data will be deleted
      3. Day 15-25: Daily reactivation reminders with countdown
      4. Day 25: Complete data wipe — all leads, policies, agents deleted
    """
    total_reminded = 0
    total_deactivated = 0
    total_wiped = 0

    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com").rstrip("/")
    subscribe_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Subscribe Now", url=f"{server_url}/static/dashboard.html#subscription")]
    ])

    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            # Include active trial, expired, AND cancelled (for grace period + data wipe)
            cursor = await conn.execute(
                "SELECT * FROM tenants WHERE subscription_status IN ('trial', 'expired', 'cancelled') "
                "AND subscription_status != 'wiped'"
            )
            tenants = [dict(row) for row in await cursor.fetchall()]

        now = datetime.now()

        for tenant in tenants:
            # Determine the relevant end date:
            # - For trial: trial_ends_at
            # - For cancelled paid: subscription_expires_at (fallback to trial_ends_at)
            # - For expired: trial_ends_at
            status = tenant.get('subscription_status', '')
            if status == 'cancelled':
                end_str = (tenant.get('subscription_expires_at')
                           or tenant.get('trial_ends_at'))
            else:
                end_str = tenant.get('trial_ends_at')
            if not end_str:
                continue

            try:
                trial_end = datetime.fromisoformat(end_str)
            except ValueError:
                continue

            trial_start = trial_end - timedelta(days=14)
            days_elapsed = (now - trial_start).days
            days_past_expiry = (now - trial_end).days  # negative = still in trial

            firm_name = tenant.get('firm_name', 'Your Firm')
            tenant_id = tenant['tenant_id']
            owner_tg_id = tenant.get('owner_telegram_id')

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            #  STAGE 4: Day 25+ → COMPLETE DATA WIPE
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if days_past_expiry >= GRACE_PERIOD_DAYS:
                await _wipe_tenant_data(tenant_id, firm_name)
                total_wiped += 1

                if owner_tg_id:
                    wipe_msg = (
                        "🗑️ *Account Data Deleted*\n\n"
                        f"Hi\\! The grace period for *{_escape_md(firm_name)}* "
                        "has ended\\.\n\n"
                        "All your data has been *permanently deleted*:\n"
                        "• All leads & pipeline data\n"
                        "• All policies & interactions\n"
                        "• All agent profiles\n"
                        "• All calculator sessions & reports\n\n"
                        "This action is *irreversible*\\.\n\n"
                        "To start fresh, sign up again at:\n"
                        "🌐 *sarathi\\-ai\\.com*\n\n"
                        "Note: A new subscription \\(paid\\) is required\\. "
                        "Free trial is available once per phone number\\."
                    )
                    await _send_telegram(owner_tg_id, wipe_msg)
                continue

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            #  STAGE 3: Day 15-25 → DAILY REACTIVATION REMINDERS
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if days_past_expiry > 0 and tenant.get('subscription_status') in ('expired', 'cancelled'):
                days_until_wipe = GRACE_PERIOD_DAYS - days_past_expiry
                if owner_tg_id and days_until_wipe > 0:
                    grace_msg = (
                        f"⚠️ *Data Deletion in {days_until_wipe} Days*\n\n"
                        f"Hi\\! Your *{_escape_md(firm_name)}* account "
                        "is deactivated\\.\n\n"
                        f"📅 *{days_until_wipe} days* until your data "
                        "is *permanently deleted*:\n"
                        f"• {tenant.get('firm_name', '?')} leads & policies\n"
                        "• All client interactions & reports\n"
                        "• Calculator sessions & PDFs\n\n"
                        "💳 *Subscribe NOW* to save your data:\n"
                        "• Solo Advisor: ₹199/mo\n"
                        "• Team: ₹799/mo\n"
                        "• Enterprise: ₹1,999/mo\n\n"
                        "🔑 Use /subscribe or visit sarathi\\-ai\\.com"
                    )
                    await _send_telegram(owner_tg_id, grace_msg, reply_markup=subscribe_kb)
                    total_reminded += 1
                    logger.info("⚠️ Grace period reminder: tenant %d (%s), %d days until wipe",
                                tenant_id, firm_name, days_until_wipe)

                # Send data deletion warning email (every 3 days to avoid spam)
                email = tenant.get('email')
                if email and days_until_wipe in (7, 4, 1):
                    asyncio.create_task(email_svc.send_data_deletion_warning(
                        email, tenant.get('owner_name', ''), firm_name, days_until_wipe))

                continue

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            #  STAGE 2: Day 15 → DEACTIVATE + WARN
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if days_past_expiry >= 0 and tenant.get('is_active') == 1:
                await db.update_tenant(tenant_id,
                                       is_active=0,
                                       subscription_status='expired')
                total_deactivated += 1
                logger.warning("🚫 Trial expired → DEACTIVATED tenant %d (%s)",
                               tenant_id, firm_name)

                if owner_tg_id:
                    deactivate_msg = (
                        "🚫 *Trial Expired — Account Deactivated*\n\n"
                        f"Hi\\! Your 14\\-day free trial for *{_escape_md(firm_name)}* "
                        "has ended\\.\n\n"
                        "Your account is now *deactivated*\\. "
                        "All features are disabled\\.\n\n"
                        "⚠️ *IMPORTANT:* You have *10 days* to subscribe\\. "
                        "After that, all your data will be *permanently deleted*\\.\n\n"
                        "💳 *Subscribe now* to reactivate:\n"
                        "• Solo Advisor: ₹199/mo\n"
                        "• Team: ₹799/mo\n"
                        "• Enterprise: ₹1,999/mo\n\n"
                        "Pay via UPI, Debit Card, or Credit Card\\.\n"
                        "Use /subscribe in the bot\\."
                    )
                    await _send_telegram(owner_tg_id, deactivate_msg, reply_markup=subscribe_kb)

                # Send deactivation email
                email = tenant.get('email')
                if email:
                    asyncio.create_task(email_svc.send_account_deactivated(
                        email, tenant.get('owner_name', ''), firm_name, GRACE_PERIOD_DAYS))

                continue

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            #  STAGE 1: Pre-expiry reminders (Day 10, 13, 14)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            days_remaining = (trial_end - now).days
            if days_elapsed in TRIAL_REMINDER_DAYS and owner_tg_id:
                if days_remaining <= 0:
                    urgency = "⚠️ *LAST DAY*"
                    urgency_text = "Today is your *last day*\\!"
                elif days_remaining == 1:
                    urgency = "⏰ *EXPIRING TOMORROW*"
                    urgency_text = "Your trial expires *tomorrow*\\!"
                else:
                    urgency = f"📅 *{days_remaining} Days Left*"
                    urgency_text = f"You have *{days_remaining} days* remaining\\."

                reminder_msg = (
                    f"{urgency}\n\n"
                    f"Hi\\! Your free trial for *{_escape_md(firm_name)}* "
                    f"on Sarathi\\-AI is ending soon\\.\n\n"
                    f"{urgency_text}\n\n"
                    "🔑 *Subscribe now* to keep your CRM running:\n"
                    "• All your leads & policies stay safe\n"
                    "• Auto\\-greetings keep working\n"
                    "• Calculators & reports remain active\n\n"
                    "💳 Pay via UPI, Debit Card, or Credit Card\\.\n"
                    "Use /subscribe in the bot to upgrade\\."
                )
                await _send_telegram(owner_tg_id, reminder_msg, reply_markup=subscribe_kb)
                total_reminded += 1
                logger.info("📧 Trial reminder sent: tenant %d (%s), day %d, %d days left",
                            tenant_id, firm_name, days_elapsed, days_remaining)

        logger.info("Trial expiry scan: %d reminders, %d deactivated, %d wiped",
                     total_reminded, total_deactivated, total_wiped)
    except Exception as e:
        logger.error("Trial expiry scan error: %s", e, exc_info=True)


def _escape_md(text: str) -> str:
    """Escape text for Telegram MarkdownV2."""
    special = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in special else c for c in str(text))


# =============================================================================
#  90-DAY INACTIVE AGENT AUTO-DEACTIVATION
# =============================================================================

async def run_inactive_agent_cleanup(days: int = 90):
    """Auto-deactivate agents inactive for N days. Notifies admin owners."""
    try:
        inactive = await db.get_inactive_agents(days)
        if not inactive:
            logger.info("Inactive agent scan: 0 agents to deactivate")
            return

        logger.info("Inactive agent scan: %d agents found (>%d days)", len(inactive), days)

        # Group by tenant for batch admin notification
        by_tenant = {}
        for agent in inactive:
            tid = agent['tenant_id']
            if tid not in by_tenant:
                by_tenant[tid] = []
            by_tenant[tid].append(agent)

        deactivated = 0
        for tid, agents in by_tenant.items():
            names = []
            for agent in agents:
                ok = await db.deactivate_agent_full(
                    agent['agent_id'], tid, reason='inactive_90d')
                if ok:
                    deactivated += 1
                    names.append(agent.get('name', f"Agent #{agent['agent_id']}"))

            # Notify tenant owner
            if names:
                try:
                    owner = await db.get_owner_agent_by_tenant(tid)
                    if owner and owner.get('telegram_id'):
                        firm = agents[0].get('firm_name', f'Tenant #{tid}')
                        agent_list = "\n".join(f"  • {n}" for n in names)
                        msg = (
                            f"🔔 *Inactive Agent Auto-Cleanup*\n\n"
                            f"The following agents were auto-deactivated "
                            f"after {days} days of inactivity:\n\n"
                            f"{agent_list}\n\n"
                            f"Firm: {firm}\n"
                            f"They can be reactivated from Team Management.")
                        await _send_telegram(owner['telegram_id'], msg)
                except Exception as ne:
                    logger.error("Failed to notify owner for tenant %d: %s", tid, ne)

        logger.info("Inactive agent cleanup: %d/%d deactivated", deactivated, len(inactive))

    except Exception as e:
        logger.error("Inactive agent cleanup error: %s", e, exc_info=True)


# =============================================================================
#  PROACTIVE AI ASSISTANT — 24/7 Smart Nudges
# =============================================================================

# Track what nudges were sent today to avoid duplicates
_proactive_sent_today: dict = {}  # key: f"{agent_id}:{nudge_type}:{entity_id}" → True
_proactive_last_date: str = ""


def _proactive_key(agent_id, nudge_type, entity_id=None):
    return f"{agent_id}:{nudge_type}:{entity_id or '0'}"


def _reset_proactive_if_new_day():
    global _proactive_sent_today, _proactive_last_date
    today = datetime.now().strftime("%Y-%m-%d")
    if today != _proactive_last_date:
        _proactive_sent_today = {}
        _proactive_last_date = today


def _was_proactive_sent(agent_id, nudge_type, entity_id=None):
    _reset_proactive_if_new_day()
    return _proactive_key(agent_id, nudge_type, entity_id) in _proactive_sent_today


def _mark_proactive_sent(agent_id, nudge_type, entity_id=None):
    _reset_proactive_if_new_day()
    _proactive_sent_today[_proactive_key(agent_id, nudge_type, entity_id)] = True


async def run_timed_followup_reminder():
    """
    30-min-before timed follow-up reminder.
    Runs every 5 minutes. Checks for follow-ups with specific times
    that are due within the next 30 minutes. Sends reminder with
    Done ✅ / Snooze 🕐 buttons.
    """
    logger.info("Checking timed follow-up reminders...")
    try:
        upcoming = await db.get_upcoming_timed_followups(minutes_ahead=30)
        if not upcoming:
            return

        sent = 0
        for fu in upcoming:
            iid = fu['interaction_id']
            agent_id = fu.get('agent_id')
            tid = fu.get('agent_telegram_id')
            if not tid:
                continue

            # Dedup: don't send same reminder twice
            if _was_proactive_sent(agent_id, 'fu_30min', iid):
                continue

            hi = fu.get('agent_lang', 'en') == 'hi'
            lead_name = fu.get('lead_name', 'Client')
            fu_time = fu.get('follow_up_time', '')
            fu_type = fu.get('type', 'Follow-up')

            # Format time for display (24hr → 12hr)
            try:
                t = datetime.strptime(fu_time, '%H:%M')
                time_display = t.strftime('%I:%M %p').lstrip('0')
            except (ValueError, TypeError):
                time_display = fu_time or 'soon'

            if hi:
                msg = (f"⏰ *30 मिनट बाद Follow-up!*\n\n"
                       f"👤 {lead_name}\n"
                       f"📋 {fu_type}\n"
                       f"🕐 {time_display}\n\n"
                       f"तैयार रहें! Call/meeting के बाद ✅ Done दबाएं।")
            else:
                msg = (f"⏰ *Follow-up in 30 minutes!*\n\n"
                       f"👤 {lead_name}\n"
                       f"📋 {fu_type}\n"
                       f"🕐 {time_display}\n\n"
                       f"Get ready! Tap ✅ Done after your call/meeting.")

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Done", callback_data=f"fudone_{iid}"),
                 InlineKeyboardButton("🕐 Snooze 1hr", callback_data=f"fusnz_{iid}")]
            ])

            await _send_telegram(tid, msg, reply_markup=keyboard)
            _mark_proactive_sent(agent_id, 'fu_30min', iid)
            sent += 1

        if sent:
            logger.info("Sent %d timed follow-up reminders", sent)

    except Exception as e:
        logger.error("Timed follow-up reminder error: %s", e, exc_info=True)


async def run_notes_missing_nudge():
    """
    Nudge advisors who marked follow-ups as done but didn't add notes.
    Runs once at 5 PM. Checks last 3 days.
    """
    logger.info("Running notes-missing nudge...")
    try:
        overdue = await db.get_overdue_followups_without_notes()
        if not overdue:
            return

        # Group by agent
        by_agent = {}
        for item in overdue:
            aid = item.get('agent_id')
            if aid not in by_agent:
                by_agent[aid] = {'tid': item.get('agent_telegram_id'),
                                 'hi': item.get('agent_lang', 'en') == 'hi',
                                 'items': []}
            by_agent[aid]['items'].append(item)

        sent = 0
        for aid, info in by_agent.items():
            if not info['tid']:
                continue
            if _was_proactive_sent(aid, 'notes_missing'):
                continue

            count = len(info['items'])
            names = ', '.join(i.get('lead_name', '?') for i in info['items'][:3])
            if count > 3:
                names += f" +{count - 3} more"

            if info['hi']:
                msg = (f"📋 *{count} follow-up notes pending!*\n\n"
                       f"आपने follow-up done किया लेकिन notes नहीं डाले:\n"
                       f"👤 {names}\n\n"
                       f"Notes भेजने के लिए वॉइस नोट या टाइप करें।")
            else:
                msg = (f"📋 *{count} follow-up notes pending!*\n\n"
                       f"You marked these follow-ups done but didn't add notes:\n"
                       f"👤 {names}\n\n"
                       f"Send a voice note or type your notes.")

            await _send_telegram(info['tid'], msg)
            _mark_proactive_sent(aid, 'notes_missing')
            sent += 1

        if sent:
            logger.info("Sent %d notes-missing nudges", sent)

    except Exception as e:
        logger.error("Notes-missing nudge error: %s", e, exc_info=True)


async def run_admin_followup_digest():
    """
    Evening admin digest — shows accountability summary for the tenant's team.
    Runs at 7 PM daily. Owner/admin sees: done+noted, done but no notes, missed, pending.
    """
    logger.info("Running admin follow-up digest...")
    try:
        # Get all tenants with team plans
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """SELECT DISTINCT t.tenant_id, t.firm_name,
                          a.telegram_id as owner_telegram_id, a.lang as owner_lang
                   FROM tenants t
                   JOIN agents a ON a.tenant_id = t.tenant_id AND a.role = 'owner'
                   WHERE t.is_active = 1 AND a.is_active = 1
                     AND t.plan IN ('team', 'enterprise')""")
            tenants = [dict(r) for r in await cursor.fetchall()]

        sent = 0
        for t in tenants:
            tid = t['tenant_id']
            owner_tid = t.get('owner_telegram_id')
            if not owner_tid:
                continue
            if _was_proactive_sent(0, 'admin_digest', tid):
                continue

            digest = await db.get_admin_followup_digest(tid)
            total = digest.get('total', 0)
            if total == 0:
                continue

            hi = t.get('owner_lang', 'en') == 'hi'
            done_noted = len(digest.get('done_with_notes', []))
            done_no_notes = len(digest.get('done_without_notes', []))
            missed = len(digest.get('missed', []))
            pending = len(digest.get('pending_today', []))

            if hi:
                msg = (f"📊 *आज का Follow-up Report*\n"
                       f"━━━━━━━━━━━━━━━━━━\n\n"
                       f"✅ Done + Notes: {done_noted}\n"
                       f"⚠️ Done, notes pending: {done_no_notes}\n"
                       f"❌ Missed: {missed}\n"
                       f"⏳ Aaj pending: {pending}\n\n"
                       f"Total: {total} follow-ups\n\n"
                       f"_Dashboard पर full details देखें._")
            else:
                msg = (f"📊 *Today's Follow-up Report*\n"
                       f"━━━━━━━━━━━━━━━━━━\n\n"
                       f"✅ Done + notes added: {done_noted}\n"
                       f"⚠️ Done, notes pending: {done_no_notes}\n"
                       f"❌ Missed follow-ups: {missed}\n"
                       f"⏳ Still pending today: {pending}\n\n"
                       f"Total: {total} follow-ups\n\n"
                       f"_Check your dashboard for full details._")

            # Add agent-level breakdown for missed
            missed_items = digest.get('missed', [])
            if missed_items:
                by_agent = {}
                for m in missed_items:
                    aname = m.get('agent_name', 'Unknown')
                    if aname not in by_agent:
                        by_agent[aname] = []
                    by_agent[aname].append(m.get('lead_name', '?'))

                if hi:
                    msg += "\n\n🔴 *Missed by advisor:*\n"
                else:
                    msg += "\n\n🔴 *Missed by advisor:*\n"
                for aname, leads in by_agent.items():
                    lead_list = ', '.join(leads[:3])
                    if len(leads) > 3:
                        lead_list += f" +{len(leads)-3}"
                    msg += f"  • {aname}: {lead_list}\n"

            await _send_telegram(owner_tid, msg)
            _mark_proactive_sent(0, 'admin_digest', tid)
            sent += 1

        if sent:
            logger.info("Sent %d admin follow-up digests", sent)

    except Exception as e:
        logger.error("Admin follow-up digest error: %s", e, exc_info=True)


async def run_proactive_followup_nudge():
    """
    Real-time follow-up nudges — runs multiple times per day.
    Morning: "Aaj ke follow-ups" with full list + action buttons.
    Afternoon: "2 follow-ups baaki hain" gentle reminder.
    Evening: "Missed follow-ups" with reschedule option.
    """
    logger.info("Running proactive follow-up nudge...")
    agents = await db.get_all_active_agents()
    now = datetime.now()
    hour = now.hour
    total = 0

    for agent in agents:
        agent_id = agent['agent_id']
        hi = agent.get('lang', 'en') == 'hi'

        followups = await db.get_agent_followups_with_time(agent_id)
        if not followups:
            continue

        overdue = []
        today_due = []
        for fu in followups:
            try:
                fu_dt = datetime.fromisoformat(fu['follow_up_date'])
                if fu_dt.date() < now.date():
                    overdue.append(fu)
                else:
                    today_due.append(fu)
            except (ValueError, TypeError):
                today_due.append(fu)

        # ── MORNING (9 AM): Full agenda with action buttons ──
        if 9 <= hour < 10:
            if _was_proactive_sent(agent_id, 'fu_morning'):
                continue

            if not today_due and not overdue:
                continue

            lines = []
            if hi:
                lines.append("🔔 <b>आज के फॉलो-अप्स</b>\n")
            else:
                lines.append("🔔 <b>Today's Follow-ups</b>\n")

            if overdue:
                lines.append(f"🔴 <b>{'ओवरड्यू' if hi else 'Overdue'}: {len(overdue)}</b>")
                for fu in overdue[:3]:
                    lines.append(f"  • <b>{fu['lead_name']}</b> — {fu.get('type', 'call')}")

            if today_due:
                lines.append(f"\n📋 <b>{'आज' if hi else 'Today'}: {len(today_due)}</b>")
                for fu in today_due[:5]:
                    lines.append(
                        f"  • <b>{fu['lead_name']}</b> — {fu.get('type', 'call')}"
                        f"\n    📝 {fu.get('summary', '—')[:60]}")

            if len(today_due) + len(overdue) > 8:
                remaining = len(today_due) + len(overdue) - 8
                lines.append(f"\n...{'और' if hi else 'and'} {remaining} {'और' if hi else 'more'}")

            lines.append(f"\n💡 {'वॉइस नोट भेजें: \"फॉलो-अप लिस्ट दिखाओ\"' if hi else 'Send voice: \"Show my follow-ups\"'}")

            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📋 सभी देखें" if hi else "📋 View All",
                    callback_data="pa_view_followups")],
                [InlineKeyboardButton(
                    "✅ सब हो गया" if hi else "✅ All Done",
                    callback_data="pa_dismiss_fu")]
            ])

            await _send_telegram(agent['telegram_id'], "\n".join(lines),
                                 reply_markup=buttons)
            _mark_proactive_sent(agent_id, 'fu_morning')
            total += 1

        # ── AFTERNOON (2 PM): Gentle reminder ──
        elif 14 <= hour < 15:
            if _was_proactive_sent(agent_id, 'fu_afternoon'):
                continue

            pending = len(today_due) + len(overdue)
            if pending == 0:
                continue

            if hi:
                msg = (f"⏰ <b>{pending} फॉलो-अप बाकी</b>\n\n"
                       f"अभी तक {pending} follow-ups pending हैं।\n"
                       f"सबसे ज़रूरी: <b>{(overdue or today_due)[0]['lead_name']}</b>\n\n"
                       f"📞 अभी call करें?")
            else:
                msg = (f"⏰ <b>{pending} follow-ups pending</b>\n\n"
                       f"Most urgent: <b>{(overdue or today_due)[0]['lead_name']}</b>\n\n"
                       f"📞 Call now?")

            top_lead = (overdue or today_due)[0]
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"📞 {top_lead['lead_name'][:15]}",
                    callback_data=f"pa_call_{top_lead['lead_id']}"),
                 InlineKeyboardButton(
                    "⏰ 1hr बाद" if hi else "⏰ In 1hr",
                    callback_data="pa_snooze_fu")]
            ])

            await _send_telegram(agent['telegram_id'], msg, reply_markup=buttons)
            _mark_proactive_sent(agent_id, 'fu_afternoon')
            total += 1

        # ── EVENING (6 PM): Missed follow-ups ──
        elif 18 <= hour < 19:
            if _was_proactive_sent(agent_id, 'fu_evening'):
                continue

            pending = len(today_due) + len(overdue)
            if pending == 0:
                continue

            if hi:
                msg = (f"📌 <b>आज {pending} फॉलो-अप छूट गए</b>\n\n"
                       f"कल reschedule करें?\n")
            else:
                msg = (f"📌 <b>{pending} follow-ups missed today</b>\n\n"
                       f"Reschedule for tomorrow?\n")

            for fu in (overdue + today_due)[:5]:
                msg += f"  • {fu['lead_name']}\n"

            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📅 कल करो" if hi else "📅 Move to Tomorrow",
                    callback_data="pa_reschedule_tomorrow"),
                 InlineKeyboardButton(
                    "✅ हो गया" if hi else "✅ Done",
                    callback_data="pa_dismiss_fu")]
            ])

            await _send_telegram(agent['telegram_id'], msg, reply_markup=buttons)
            _mark_proactive_sent(agent_id, 'fu_evening')
            total += 1

    logger.info("Proactive follow-up nudge: %d sent", total)
    return total


async def run_celebration_assistant():
    """
    Eve-of-birthday/anniversary alerts at 7 PM.
    'Kal Priya ka birthday hai — greeting bhejein?'
    """
    logger.info("Running celebration assistant...")
    total = 0

    # Tomorrow's birthdays
    tmrw_bdays = await db.get_tomorrows_birthdays()
    for lead in tmrw_bdays:
        agent_tid = lead.get('agent_telegram_id')
        if not agent_tid:
            continue

        lead_key = f"bday_eve_{lead['lead_id']}"
        agent_id = lead.get('agent_id', 0)
        if _was_proactive_sent(agent_id, 'celebration', lead['lead_id']):
            continue

        hi = lead.get('lang', 'en') == 'hi'
        if hi:
            msg = (f"🎂 <b>कल {lead['name']} का Birthday है!</b>\n\n"
                   f"📞 {lead.get('phone', 'N/A')}\n\n"
                   f"ऑटो-greeting भेजी जाएगी सुबह 9 बजे।\n"
                   f"या अभी custom message भेजें?")
        else:
            msg = (f"🎂 <b>{lead['name']}'s Birthday is tomorrow!</b>\n\n"
                   f"📞 {lead.get('phone', 'N/A')}\n\n"
                   f"Auto-greeting will be sent at 9 AM.\n"
                   f"Or send a custom message now?")

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🎂 अभी भेजो" if hi else "🎂 Send Now",
                callback_data=f"pa_greet_bday_{lead['lead_id']}"),
             InlineKeyboardButton(
                "✅ 9 AM ठीक है" if hi else "✅ 9 AM is fine",
                callback_data=f"pa_dismiss_celeb_{lead['lead_id']}")]
        ])

        await _send_telegram(agent_tid, msg, reply_markup=buttons)
        _mark_proactive_sent(agent_id, 'celebration', lead['lead_id'])
        total += 1

    # Tomorrow's anniversaries
    tmrw_anniv = await db.get_tomorrows_anniversaries()
    for lead in tmrw_anniv:
        agent_tid = lead.get('agent_telegram_id')
        if not agent_tid:
            continue

        agent_id = lead.get('agent_id', 0)
        if _was_proactive_sent(agent_id, 'celebration', f"anniv_{lead['lead_id']}"):
            continue

        hi = lead.get('lang', 'en') == 'hi'
        if hi:
            msg = (f"💍 <b>कल {lead['name']} की Anniversary है!</b>\n\n"
                   f"📞 {lead.get('phone', 'N/A')}\n"
                   f"ऑटो-greeting सुबह 9 बजे भेजी जाएगी।")
        else:
            msg = (f"💍 <b>{lead['name']}'s Anniversary is tomorrow!</b>\n\n"
                   f"📞 {lead.get('phone', 'N/A')}\n"
                   f"Auto-greeting will be sent at 9 AM.")

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "💍 अभी भेजो" if hi else "💍 Send Now",
                callback_data=f"pa_greet_anniv_{lead['lead_id']}"),
             InlineKeyboardButton(
                "✅ 9 AM ठीक है" if hi else "✅ OK",
                callback_data=f"pa_dismiss_celeb_{lead['lead_id']}")]
        ])

        await _send_telegram(agent_tid, msg, reply_markup=buttons)
        _mark_proactive_sent(agent_id, 'celebration', f"anniv_{lead['lead_id']}")
        total += 1

    logger.info("Celebration assistant: %d alerts sent", total)
    return total


async def run_stale_lead_alert():
    """
    Weekly stale lead alert — runs Monday at 11 AM.
    'X leads ko 2+ hafte se contact nahi kiya.'
    """
    logger.info("Running stale lead alert...")
    agents = await db.get_all_active_agents()
    total = 0

    for agent in agents:
        agent_id = agent['agent_id']
        if _was_proactive_sent(agent_id, 'stale_weekly'):
            continue

        hi = agent.get('lang', 'en') == 'hi'
        stale = await db.get_stale_leads_for_agent(agent_id, days=14)
        if not stale:
            continue

        if hi:
            msg = (f"⚠️ <b>{len(stale)} leads को 2+ हफ्ते से contact नहीं किया</b>\n\n")
        else:
            msg = (f"⚠️ <b>{len(stale)} leads untouched for 2+ weeks</b>\n\n")

        for i, lead in enumerate(stale[:5], 1):
            days_ago = (datetime.now() - datetime.fromisoformat(lead['updated_at'])).days
            msg += f"  {i}. <b>{lead['name']}</b> — {lead.get('stage', '?')} ({days_ago}d ago)\n"

        if len(stale) > 5:
            msg += f"\n  ...{'और' if hi else 'and'} {len(stale) - 5} {'और' if hi else 'more'}\n"

        msg += f"\n💡 {'वॉइस: \"stale leads दिखाओ\"' if hi else 'Voice: \"show stale leads\"'}"

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📋 लिस्ट देखो" if hi else "📋 View List",
                callback_data="pa_view_stale"),
             InlineKeyboardButton(
                "👋 बाद में" if hi else "👋 Later",
                callback_data="pa_dismiss_stale")]
        ])

        await _send_telegram(agent['telegram_id'], msg, reply_markup=buttons)
        _mark_proactive_sent(agent_id, 'stale_weekly')
        total += 1

    logger.info("Stale lead alert: %d sent", total)
    return total


async def run_weekly_momentum():
    """
    Weekly momentum digest — runs Saturday at 6 PM.
    Celebrates wins, shows streaks, motivates for next week.
    """
    logger.info("Running weekly momentum digest...")
    agents = await db.get_all_active_agents()
    total = 0

    for agent in agents:
        agent_id = agent['agent_id']
        if _was_proactive_sent(agent_id, 'weekly_momentum'):
            continue

        hi = agent.get('lang', 'en') == 'hi'
        stats = await db.get_agent_weekly_stats(agent_id)

        # Skip if zero activity
        if stats['interactions'] == 0 and stats['deals_won'] == 0:
            continue

        # Build celebration message
        if hi:
            msg = "📊 <b>इस हफ्ते का Performance</b>\n━━━━━━━━━━━━━━━\n\n"
        else:
            msg = "📊 <b>This Week's Performance</b>\n━━━━━━━━━━━━━━━\n\n"

        if stats['deals_won'] > 0:
            msg += f"🎉 {'डील्स Won' if hi else 'Deals Won'}: <b>{stats['deals_won']}</b>\n"
            if stats['premium_won'] > 0:
                msg += f"💰 {'Premium' if hi else 'Premium'}: <b>₹{stats['premium_won']:,.0f}</b>\n"

        msg += f"📞 {'इंटरैक्शन' if hi else 'Interactions'}: {stats['interactions']}\n"
        msg += f"👤 {'नए लीड्स' if hi else 'New Leads'}: {stats['new_leads']}\n"
        msg += f"✅ {'फॉलो-अप्स पूरे' if hi else 'Follow-ups Done'}: {stats['followups_done']}\n"

        if stats['streak_days'] >= 3:
            msg += f"\n🔥 {'स्ट्रीक' if hi else 'Streak'}: <b>{stats['streak_days']} {'दिन लगातार!' if hi else 'days in a row!'}</b>\n"

        # Motivational closer
        if stats['deals_won'] >= 3:
            msg += f"\n🏆 {'शानदार हफ्ता! Keep crushing it!' if hi else 'Amazing week! Keep crushing it!'}"
        elif stats['deals_won'] >= 1:
            msg += f"\n💪 {'अच्छा काम! अगले हफ्ते और ज़्यादा!' if hi else 'Good work! Aim higher next week!'}"
        elif stats['interactions'] >= 10:
            msg += f"\n📈 {'Active रहे! Deals आएंगे!' if hi else 'Staying active! Deals will follow!'}"
        else:
            msg += f"\n💡 {'अगले हफ्ते ज़्यादा follow-ups करो!' if hi else 'More follow-ups next week = more wins!'}"

        await _send_telegram(agent['telegram_id'], msg)
        _mark_proactive_sent(agent_id, 'weekly_momentum')
        total += 1

    logger.info("Weekly momentum: %d sent", total)
    return total


async def run_deal_won_celebration(agent_id: int, lead_name: str, premium: float = 0):
    """
    Instant celebration when a deal is closed.
    Called from bot handler when stage changes to closed_won.
    """
    agent = await db.get_agent_by_id(agent_id)
    if not agent or not agent.get('telegram_id'):
        return

    hi = agent.get('lang', 'en') == 'hi'
    if hi:
        msg = f"🎉🎉🎉 <b>बधाई हो!</b>\n\n"
        msg += f"<b>{lead_name}</b> का deal close हो गया!"
        if premium > 0:
            msg += f"\n💰 Premium: <b>₹{premium:,.0f}</b>"
        msg += "\n\n🏆 मेहनत रंग लाई! Keep going! 💪"
    else:
        msg = f"🎉🎉🎉 <b>Congratulations!</b>\n\n"
        msg += f"<b>{lead_name}</b>'s deal is closed!"
        if premium > 0:
            msg += f"\n💰 Premium: <b>₹{premium:,.0f}</b>"
        msg += "\n\n🏆 Hard work pays off! Keep going! 💪"

    # Also show weekly stats inline
    stats = await db.get_agent_weekly_stats(agent_id)
    if stats['deals_won'] > 1:
        msg += f"\n\n📊 {'इस हफ्ते' if hi else 'This week'}: {stats['deals_won']} {'deals won' if not hi else 'deals close'}!"

    await _send_telegram(agent['telegram_id'], msg)


async def run_smart_post_action_suggestion(agent_telegram_id: str, action: str,
                                            lead_name: str, lead_id: int,
                                            lang: str = 'en'):
    """
    Smart suggestion after completing an action.
    Called from bot handlers after log_meeting, create_lead, calc_compute etc.
    """
    hi = lang == 'hi'

    suggestions = {
        'log_meeting': {
            'hi': f"💡 <b>{lead_name}</b> से meeting हो गई?\n\nNext step?",
            'en': f"💡 Meeting with <b>{lead_name}</b> logged!\n\nWhat's next?",
            'buttons': [
                ("📄 Proposal भेजो" if hi else "📄 Send Proposal", f"pa_pitch_{lead_id}"),
                ("📅 Follow-up लगाओ" if hi else "📅 Set Follow-up", f"pa_followup_{lead_id}"),
            ]
        },
        'create_lead': {
            'hi': f"💡 <b>{lead_name}</b> add हो गया!\n\nNeed कैसे शुरू करें:",
            'en': f"💡 <b>{lead_name}</b> added!\n\nGet started:",
            'buttons': [
                ("📞 Call Log करो" if hi else "📞 Log a Call", f"pa_logcall_{lead_id}"),
                ("🧮 Calculator भेजो" if hi else "🧮 Send Calculator", f"pa_calc_{lead_id}"),
            ]
        },
        'calc_compute': {
            'hi': f"💡 Calculator result तैयार!\n\n<b>{lead_name}</b> को भेजें?",
            'en': f"💡 Calculator result ready!\n\nSend to <b>{lead_name}</b>?",
            'buttons': [
                ("📤 WhatsApp भेजो" if hi else "📤 Send via WhatsApp", f"pa_sendcalc_{lead_id}"),
                ("👋 बाद में" if hi else "👋 Later", "pa_dismiss_suggest"),
            ]
        }
    }

    config = suggestions.get(action)
    if not config:
        return

    msg = config['hi'] if hi else config['en']
    keyboard = [[InlineKeyboardButton(label, callback_data=cb)]
                for label, cb in config['buttons']]
    buttons = InlineKeyboardMarkup(keyboard)

    await _send_telegram(agent_telegram_id, msg, reply_markup=buttons)


# =============================================================================
#  SCHEDULER (runs as background asyncio task)
# =============================================================================

async def start_scheduler():
    """
    Main scheduler loop — runs continuously.
    Checks time and triggers scans at appropriate hours.
    """
    logger.info("Reminder scheduler started")
    last_run_date = None
    last_monitor_date = None

    while True:
        try:
            now = datetime.now()
            today = now.date()
            hour = now.hour
            minute = now.minute

            # Run at 6:00 AM — Auto-remediation + Anomaly Scan (before business hours)
            if hour == 6 and 0 <= minute < 5 and last_monitor_date != today:
                logger.info("Running daily auto-remediation + anomaly scan")
                try:
                    # Auto-remediation first
                    remediation = await db.run_auto_remediation()
                    logger.info("Auto-remediation: %d fixes applied", remediation.get('total_fixes', 0))

                    # Then anomaly scan
                    findings = await db.run_anomaly_scan()
                    for f in findings:
                        await db.add_system_event(
                            event_type=f["type"], severity=f["severity"],
                            category=f["category"], title=f["title"],
                            detail=f.get("detail"), tenant_id=f.get("tenant_id"))
                    logger.info("Daily anomaly scan: %d issues found", len(findings))

                    last_monitor_date = today

                    # Inactive agent auto-cleanup (90 days)
                    await run_inactive_agent_cleanup(90)
                except Exception as me:
                    logger.error("Daily monitor scan error: %s", me, exc_info=True)

            # Run at 12:00 PM — Mid-day anomaly scan (catch issues during business hours)
            if hour == 12 and 0 <= minute < 5 and last_monitor_date == today:
                try:
                    findings = await db.run_anomaly_scan()
                    for f in findings:
                        await db.add_system_event(
                            event_type=f["type"], severity=f["severity"],
                            category=f["category"], title=f["title"],
                            detail=f.get("detail"), tenant_id=f.get("tenant_id"))
                    if findings:
                        logger.info("Mid-day anomaly scan: %d issues found", len(findings))
                except Exception as me:
                    logger.error("Mid-day scan error: %s", me, exc_info=True)

            # Run once per day at 8:30 AM — Daily Summary
            if hour == 8 and 30 <= minute < 35 and last_run_date != today:
                await send_daily_summary()

            # Run at 9:00 AM — Birthday + Anniversary greetings
            if hour == 9 and 0 <= minute < 5 and last_run_date != today:
                await run_birthday_scan()
                await run_anniversary_scan()

            # Run at 10:00 AM — Renewal + Follow-up reminders
            if hour == 10 and 0 <= minute < 5 and last_run_date != today:
                await run_renewal_scan()
                await run_followup_scan()

            # Run at 11:00 AM — Trial/subscription expiry reminders
            if hour == 11 and 0 <= minute < 5 and last_run_date != today:
                await run_trial_expiry_scan()
                last_run_date = today  # Mark today as processed

            # ════════════════════════════════════════════════════════════
            #  PROACTIVE AI ASSISTANT — runs throughout the day
            # ════════════════════════════════════════════════════════════

            # Follow-up nudges: Morning (9 AM), Afternoon (2 PM), Evening (6 PM)
            if hour in (9, 14, 18) and 0 <= minute < 5:
                try:
                    await run_proactive_followup_nudge()
                except Exception as pe:
                    logger.error("Proactive follow-up nudge error: %s", pe, exc_info=True)

            # Celebration assistant: Eve-of-birthday/anniversary at 7 PM
            if hour == 19 and 0 <= minute < 5:
                try:
                    await run_celebration_assistant()
                except Exception as pe:
                    logger.error("Celebration assistant error: %s", pe, exc_info=True)

            # Stale lead alerts: Monday at 11 AM
            if now.weekday() == 0 and hour == 11 and 5 <= minute < 10:
                try:
                    await run_stale_lead_alert()
                except Exception as pe:
                    logger.error("Stale lead alert error: %s", pe, exc_info=True)

            # Weekly momentum digest: Saturday at 6 PM
            if now.weekday() == 5 and hour == 18 and 5 <= minute < 10:
                try:
                    await run_weekly_momentum()
                except Exception as pe:
                    logger.error("Weekly momentum error: %s", pe, exc_info=True)

            # Process message queue every 2 minutes
            if minute % 2 == 0 and _queue_processor:
                try:
                    await _queue_processor()
                except Exception as qe:
                    logger.error("Queue processing error: %s", qe)

            # Timed follow-up 30-min-before reminders: every 5 minutes (8 AM - 9 PM)
            if 8 <= hour <= 21 and minute % 5 == 0:
                try:
                    await run_timed_followup_reminder()
                except Exception as te:
                    logger.error("Timed follow-up reminder error: %s", te, exc_info=True)

            # ════════════════════════════════════════════════════════════
            #  DRIP NURTURE SEQUENCES — every 10 min during business hours
            # ════════════════════════════════════════════════════════════
            if 8 <= hour <= 21 and minute % 10 == 0:
                try:
                    import biz_nurture as nurture
                    await nurture.process_due_enrollments()
                except Exception as ne:
                    logger.error("Nurture tick error: %s", ne, exc_info=True)

            # Notes-missing nudge: 5 PM daily
            if hour == 17 and 0 <= minute < 5:
                try:
                    await run_notes_missing_nudge()
                except Exception as ne:
                    logger.error("Notes-missing nudge error: %s", ne, exc_info=True)

            # Admin follow-up digest: 7 PM daily (team/enterprise plans)
            if hour == 19 and 0 <= minute < 5:
                try:
                    await run_admin_followup_digest()
                except Exception as de:
                    logger.error("Admin digest error: %s", de, exc_info=True)

            # ════════════════════════════════════════════════════════════
            #  TIER 2 HEALTH MONITOR — every 15 minutes
            # ════════════════════════════════════════════════════════════
            if minute % 15 == 0:
                try:
                    import biz_health_monitor as hm
                    await hm.run_full_health_check()
                except Exception as he:
                    logger.error("Health monitor error: %s", he, exc_info=True)

            # Cleanup old health data: once a day at 3 AM
            if hour == 3 and 0 <= minute < 5:
                try:
                    import biz_health_monitor as hm
                    await hm.cleanup_old_data(30)
                except Exception:
                    pass

            # Sleep 60 seconds between checks
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("Scheduler stopped")
            break
        except Exception as e:
            logger.error("Scheduler error: %s", e, exc_info=True)
            await asyncio.sleep(300)  # Wait 5 min on error
