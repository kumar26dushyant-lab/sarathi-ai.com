"""
biz_nidaan_tasks.py  —  NidaanPartner ERP Workflow Engine
─────────────────────────────────────────────────────────────────────────────
Phase 3 (Jun 2026).  Implements the state-machine for nidaan_tasks:
  * 18 default statuses + transition matrix (seeded on first boot)
  * SLA computation with pause-aware clock
  * Dependency-blocking (task A blocks task B until A is terminal)
  * Internal QC routing (junior → senior review)
  * Dual-approval (admin + SA both must approve high-cost transitions)
  * Workload-weighted round-robin assignment

Designed to be SAFE TO RE-RUN — seed function is idempotent.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.tasks")


# ═════════════════════════════════════════════════════════════════════════════
#  ROLES & PERMISSIONS
# ═════════════════════════════════════════════════════════════════════════════
ROLE_SUPER_ADMIN     = "super_admin"
ROLE_ADMIN           = "sub_super_admin"   # "Admin" in the spec
ROLE_ASSOCIATE       = "team_member"       # "Associate" in the spec
ROLES_ADMIN_OR_ABOVE = (ROLE_SUPER_ADMIN, ROLE_ADMIN)
ROLES_ALL            = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_ASSOCIATE)


# ═════════════════════════════════════════════════════════════════════════════
#  DEFAULT WORKFLOW (Q6 spec — Legal Consultant flow)
# ═════════════════════════════════════════════════════════════════════════════
# Each entry: (slug, label_en, label_hi, label_subscriber, color, stage,
#              default_sla_hours, is_paused, is_terminal, is_qc_required,
#              requires_approval, sort_order)
_DEFAULT_STATUSES: list[tuple] = [
    # ── INTAKE ──────────────────────────────────────────────────────────────
    ("intimated",              "Intimated",                  "प्राप्त हुआ",                "Case received",                   "#fbbf24", "intake",       24,  0, 0, 0, "",       10),
    ("initial_review",         "Initial Review",             "प्रारंभिक समीक्षा",          "Under initial review",            "#93c5fd", "intake",       24,  0, 0, 0, "",       20),
    ("fightability_decision",  "Fightability Decision",      "लड़ने योग्य?",                 "Assessing if we can pursue",      "#a78bfa", "intake",        4,  0, 0, 0, "",       30),

    # ── PREPARATION ─────────────────────────────────────────────────────────
    ("docs_requested",         "Documents Requested",        "दस्तावेज़ माँगे",            "We've asked you for documents",   "#fb923c", "preparation", 168,  0, 0, 0, "",       40),
    ("paused_docs",            "Awaiting Documents",         "दस्तावेज़ की प्रतीक्षा",     "Waiting for your documents",      "#a3a3a3", "preparation",   0,  1, 0, 0, "",       45),
    ("docs_verified",          "Documents Verified",         "दस्तावेज़ सत्यापित",        "Documents received & verified",   "#86efac", "preparation",  24,  0, 0, 0, "",       50),
    ("legal_drafting",         "Legal Notice Drafting",      "कानूनी मसौदा",               "Drafting your legal case",        "#c4b5fd", "preparation", 120,  0, 0, 1, "",       60),
    ("internal_qc",            "Internal QC",                "आंतरिक समीक्षा",             "Internal quality review",         "#fcd34d", "preparation",  48,  0, 0, 0, "",       70),

    # ── INSURER ENGAGEMENT ──────────────────────────────────────────────────
    ("notice_sent",            "Legal Notice Sent",          "नोटिस भेजा",                  "Notice sent to insurer",          "#22d3ee", "engagement",    0,  1, 0, 0, "",       80),
    ("paused_insurer",         "Awaiting Insurer Response",  "बीमाकर्ता प्रतिक्रिया",     "Awaiting insurer response",       "#a3a3a3", "engagement",    0,  1, 0, 0, "",       85),
    ("insurer_responded",      "Insurer Responded",          "बीमाकर्ता ने उत्तर दिया",   "Insurer has responded",           "#93c5fd", "engagement",   48,  0, 0, 0, "",       90),
    ("negotiation",            "Negotiation",                "बातचीत",                       "Negotiating with insurer",        "#c4b5fd", "engagement",  120,  0, 0, 0, "",      100),
    ("grievance_cell_filed",   "Insurer Grievance Filed",    "शिकायत कक्ष फाइल",          "Insurer grievance cell filed",    "#fdba74", "engagement",    0,  1, 0, 0, "",      110),

    # ── OMBUDSMAN / LOKPAL (dual approval required) ─────────────────────────
    ("ombudsman_drafting",     "Ombudsman Drafting",         "लोकपाल मसौदा",               "Preparing Ombudsman filing",      "#c4b5fd", "ombudsman",   120,  0, 0, 1, "both",   120),
    ("ombudsman_filed",        "Filed with Ombudsman",       "लोकपाल में दायर",            "Filed with Ombudsman",            "#22d3ee", "ombudsman",     0,  1, 0, 0, "both",   130),
    ("paused_lokpal_date",     "Awaiting Hearing Date",      "तारीख की प्रतीक्षा",         "Awaiting Ombudsman hearing date", "#a3a3a3", "ombudsman",     0,  1, 0, 0, "",      135),
    ("ombudsman_hearing",      "Ombudsman Hearing",          "लोकपाल सुनवाई",              "Ombudsman hearing in progress",   "#93c5fd", "ombudsman",     0,  0, 0, 0, "",      140),
    ("paused_lokpal_decision", "Awaiting Decision",          "निर्णय की प्रतीक्षा",        "Awaiting Ombudsman decision",     "#a3a3a3", "ombudsman",     0,  1, 0, 0, "",      145),

    # ── HIGHER ESCALATION (dual approval) ───────────────────────────────────
    ("consumer_forum",         "Consumer Forum",             "उपभोक्ता मंच",               "Escalated to Consumer Forum",     "#fb923c", "escalation",    0,  0, 0, 0, "both",   150),
    ("high_court",             "High Court",                 "उच्च न्यायालय",             "Escalated to High Court",         "#f87171", "escalation",    0,  0, 0, 0, "both",   160),

    # ── TERMINAL ────────────────────────────────────────────────────────────
    ("resolved_paid",          "Resolved — Paid",            "हल — भुगतान हुआ",            "Resolved — insurer paid",         "#22c55e", "closed",        0,  0, 1, 0, "",      200),
    ("resolved_settled",       "Resolved — Settled",         "हल — समझौता",                 "Resolved — settlement",           "#22c55e", "closed",        0,  0, 1, 0, "",      210),
    ("closed_lost",            "Closed — Lost",              "बंद — हार",                   "Case closed",                     "#f87171", "closed",        0,  0, 1, 0, "",      220),
    ("closed_withdrawn",       "Closed — Withdrawn",         "बंद — वापस लिया",            "Case withdrawn",                  "#a3a3a3", "closed",        0,  0, 1, 0, "",      230),
    ("closed_not_fightable",   "Closed — Declined",          "बंद — संभव नहीं",            "Case declined after review",      "#a3a3a3", "closed",        0,  0, 1, 0, "",      240),
    ("closed_cascade",         "Closed — Parent Closed",     "बंद — कैस्केड",              "Auto-closed",                     "#a3a3a3", "closed",        0,  0, 1, 0, "",      250),

    # ── QC HOLDING ──────────────────────────────────────────────────────────
    ("awaiting_qc",            "Awaiting QC",                "QC की प्रतीक्षा",             "Internal quality review pending", "#fcd34d", "preparation",  48,  1, 0, 0, "",      245),

    # ── APPROVAL HOLDING ────────────────────────────────────────────────────
    ("awaiting_approval",      "Awaiting Approval",          "अनुमोदन की प्रतीक्षा",       "Internal approval pending",       "#fbbf24", "preparation",   0,  1, 0, 0, "",      246),
]


# Allowed transitions (from_slug → to_slug). Empty list = anyone with role
# can transition. Notes recommended on terminal/decision points.
# Format: (from, to, allowed_roles_csv, requires_note)
_DEFAULT_TRANSITIONS: list[tuple] = [
    # Intake flow
    ("intimated",              "initial_review",         "",                                   0),
    ("intimated",              "closed_not_fightable",   "sub_super_admin,super_admin",        1),
    ("initial_review",         "fightability_decision",  "",                                   0),
    ("initial_review",         "paused_docs",            "",                                   0),
    ("fightability_decision",  "docs_requested",         "",                                   1),
    ("fightability_decision",  "closed_not_fightable",   "sub_super_admin,super_admin",        1),
    # Preparation flow
    ("docs_requested",         "paused_docs",            "",                                   0),
    ("paused_docs",            "docs_verified",          "",                                   0),
    ("paused_docs",            "closed_withdrawn",       "sub_super_admin,super_admin",        1),
    ("docs_verified",          "legal_drafting",         "",                                   0),
    ("legal_drafting",         "awaiting_qc",            "",                                   0),
    ("awaiting_qc",            "legal_drafting",         "sub_super_admin,super_admin",        1),  # QC kickback
    ("awaiting_qc",            "notice_sent",            "sub_super_admin,super_admin",        0),  # QC approve
    # Engagement flow
    ("notice_sent",            "paused_insurer",         "",                                   0),
    ("paused_insurer",         "insurer_responded",      "",                                   0),
    ("paused_insurer",         "grievance_cell_filed",   "",                                   0),
    ("insurer_responded",      "negotiation",            "",                                   0),
    ("insurer_responded",      "grievance_cell_filed",   "",                                   0),
    ("negotiation",            "resolved_paid",          "sub_super_admin,super_admin",        1),
    ("negotiation",            "resolved_settled",       "sub_super_admin,super_admin",        1),
    ("negotiation",            "grievance_cell_filed",   "",                                   0),
    ("grievance_cell_filed",   "ombudsman_drafting",     "",                                   0),
    # Ombudsman flow (requires dual approval at each step)
    ("ombudsman_drafting",     "awaiting_approval",      "",                                   0),
    ("awaiting_approval",      "ombudsman_filed",        "sub_super_admin,super_admin",        0),  # auto on dual approve
    ("awaiting_approval",      "ombudsman_drafting",     "sub_super_admin,super_admin",        1),  # rejection — back
    ("ombudsman_filed",        "paused_lokpal_date",     "",                                   0),
    ("paused_lokpal_date",     "ombudsman_hearing",      "",                                   0),
    ("ombudsman_hearing",      "paused_lokpal_decision", "",                                   0),
    ("paused_lokpal_decision", "resolved_paid",          "sub_super_admin,super_admin",        1),
    ("paused_lokpal_decision", "resolved_settled",       "sub_super_admin,super_admin",        1),
    ("paused_lokpal_decision", "closed_lost",            "sub_super_admin,super_admin",        1),
    ("paused_lokpal_decision", "consumer_forum",         "sub_super_admin,super_admin",        1),
    # Higher escalation (dual approval)
    ("consumer_forum",         "high_court",             "super_admin",                        1),
    ("consumer_forum",         "resolved_paid",          "sub_super_admin,super_admin",        1),
    ("consumer_forum",         "closed_lost",            "sub_super_admin,super_admin",        1),
    ("high_court",             "resolved_paid",          "super_admin",                        1),
    ("high_court",             "closed_lost",            "super_admin",                        1),
]


# Default system_flags rows. Read by code at decision points.
_DEFAULT_FLAGS: list[tuple] = [
    ("auto_assign_tasks",      "1", "Round-robin auto-assign new tasks. Toggle to 0 for manual-only."),
    ("auto_create_initial_task", "1", "Auto-create 'Initial review' task when a claim is filed."),
    ("wa_automation_paused",   "0", "Master switch — pause ALL outbound WhatsApp automation."),
    ("intake_paused",          "0", "Pause new claim intake. Subscribers see a notice."),
    ("subscriber_wa_default_opt_in", "0", "Default opt-in state for new subscriber WhatsApp notifications."),
    ("quiet_hours_start",      "21", "Quiet-hours start (24h IST). No outbound WA/SMS after this."),
    ("quiet_hours_end",        "8",  "Quiet-hours end (24h IST). Outbound resumes from this hour."),
    # Phase 4 — adaptive cap mechanics
    ("nidaan_wa_warmup_day_cap",   "30", "Per-number daily cap during day 1-7 warm-up."),
    ("nidaan_wa_ramp_day_cap",     "100","Per-number daily cap during day 8-30 ramp."),
    ("nidaan_wa_steady_day_cap",   "200","Per-number daily cap from day 31+."),
    ("nidaan_wa_defer_threshold_p2","30","Defer P2 notifications when cap usage% exceeds this."),
    ("nidaan_wa_defer_threshold_p1","10","Defer P1 notifications when cap remaining% drops below this."),
    ("nidaan_email_fallback_enabled","1","Send email fallback when WA delivery fails or recipient hasn't opted in."),
]


# ═════════════════════════════════════════════════════════════════════════════
#  ERRORS
# ═════════════════════════════════════════════════════════════════════════════
class TaskError(Exception):
    """Generic task-engine error."""
    def __init__(self, msg: str, status_code: int = 400):
        self.status_code = status_code
        super().__init__(msg)


class TransitionForbidden(TaskError):
    """Transition not allowed (state machine or RBAC)."""


# ═════════════════════════════════════════════════════════════════════════════
#  SEED
# ═════════════════════════════════════════════════════════════════════════════
async def seed_defaults():
    """Idempotently populate nidaan_status_def, nidaan_status_transitions,
    and system_flags with built-in defaults. Safe to re-run."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        # Statuses
        for row in _DEFAULT_STATUSES:
            (slug, label_en, label_hi, label_sub, color, stage,
             sla, paused, terminal, qc_req, req_approval, sort_order) = row
            await conn.execute("""
                INSERT INTO nidaan_status_def
                  (slug, label_en, label_hi, label_subscriber, color, stage,
                   default_sla_hours, is_paused, is_terminal, is_qc_required,
                   requires_approval, sort_order, system_owned, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
                ON CONFLICT(slug) DO NOTHING
            """, (slug, label_en, label_hi, label_sub, color, stage,
                  sla if sla else None, paused, terminal, qc_req,
                  req_approval, sort_order))
        # Transitions
        for ft in _DEFAULT_TRANSITIONS:
            from_s, to_s, allowed, req_note = ft
            await conn.execute("""
                INSERT INTO nidaan_status_transitions
                  (from_slug, to_slug, allowed_roles, requires_note, system_owned)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(from_slug, to_slug) DO NOTHING
            """, (from_s, to_s, allowed, req_note))
        # System flags
        for key, val, desc in _DEFAULT_FLAGS:
            await conn.execute("""
                INSERT INTO system_flags (flag_key, flag_value, description)
                VALUES (?, ?, ?)
                ON CONFLICT(flag_key) DO NOTHING
            """, (key, val, desc))
        await conn.commit()
    logger.info("Nidaan workflow defaults seeded (%d statuses, %d transitions, %d flags)",
                len(_DEFAULT_STATUSES), len(_DEFAULT_TRANSITIONS), len(_DEFAULT_FLAGS))


# ═════════════════════════════════════════════════════════════════════════════
#  SYSTEM FLAGS (SA-controlled toggles)
# ═════════════════════════════════════════════════════════════════════════════
async def get_flag(key: str, default: str = "") -> str:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT flag_value FROM system_flags WHERE flag_key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def set_flag(key: str, value: str, by_staff_id: int = 0, description: str = "") -> None:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO system_flags (flag_key, flag_value, description, updated_by, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(flag_key) DO UPDATE SET
              flag_value=excluded.flag_value,
              description=COALESCE(NULLIF(excluded.description,''), description),
              updated_by=excluded.updated_by,
              updated_at=excluded.updated_at
        """, (key, value, description, by_staff_id))
        await conn.commit()


async def list_flags() -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM system_flags ORDER BY flag_key")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


def _flag_truthy(val: str) -> bool:
    return str(val).strip().lower() in ("1", "true", "yes", "on")


# ═════════════════════════════════════════════════════════════════════════════
#  STATUS REGISTRY HELPERS
# ═════════════════════════════════════════════════════════════════════════════
async def get_status(slug: str) -> Optional[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_status_def WHERE slug=? AND is_active=1", (slug,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_statuses(active_only: bool = True) -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if active_only:
            cur = await conn.execute(
                "SELECT * FROM nidaan_status_def WHERE is_active=1 ORDER BY sort_order, slug")
        else:
            cur = await conn.execute(
                "SELECT * FROM nidaan_status_def ORDER BY sort_order, slug")
        return [dict(r) for r in await cur.fetchall()]


async def list_transitions_from(from_slug: str) -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_status_transitions WHERE from_slug=?", (from_slug,))
        return [dict(r) for r in await cur.fetchall()]


async def _transition_allowed(from_slug: str, to_slug: str, role: str) -> tuple[bool, bool, str]:
    """Returns (allowed, requires_note, reason). reason populated when not allowed."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_status_transitions WHERE from_slug=? AND to_slug=?",
            (from_slug, to_slug))
        row = await cur.fetchone()
    if not row:
        return (False, False, f"No transition defined from '{from_slug}' to '{to_slug}'")
    allowed_roles = (row["allowed_roles"] or "").strip()
    if allowed_roles:
        roles = {r.strip() for r in allowed_roles.split(",") if r.strip()}
        if role not in roles:
            return (False, False, f"Role '{role}' not permitted for this transition (need {sorted(roles)})")
    return (True, bool(row["requires_note"]), "")


# ═════════════════════════════════════════════════════════════════════════════
#  STAFF HELPERS
# ═════════════════════════════════════════════════════════════════════════════
async def get_staff(staff_id: int) -> Optional[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_staff WHERE staff_id=?", (staff_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_active_associates() -> list[dict]:
    """All staff who can take task assignments — admins included for flexibility."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_staff WHERE status='active' "
            "AND role IN ('team_member','sub_super_admin') ORDER BY staff_id")
        return [dict(r) for r in await cur.fetchall()]


async def _pick_next_assignee() -> Optional[int]:
    """Round-robin weighted by current OPEN-task count.
    The associate with FEWEST open tasks gets the next one (tiebreak by
    longest time since last_assigned_at). Returns staff_id or None."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT s.staff_id, s.last_assigned_at,
              (SELECT COUNT(*) FROM nidaan_tasks t
                WHERE t.assigned_to_staff_id = s.staff_id
                  AND t.completed_at IS NULL
                  AND t.closed_at IS NULL) AS open_count
            FROM nidaan_staff s
            WHERE s.status='active'
              AND s.role IN ('team_member','sub_super_admin')
            ORDER BY open_count ASC, COALESCE(s.last_assigned_at,'1970-01-01') ASC, s.staff_id ASC
            LIMIT 1
        """)
        row = await cur.fetchone()
        if not row:
            return None
        staff_id = row["staff_id"]
        await conn.execute(
            "UPDATE nidaan_staff SET last_assigned_at=datetime('now') WHERE staff_id=?",
            (staff_id,))
        await conn.commit()
        return staff_id


# ═════════════════════════════════════════════════════════════════════════════
#  SLA UTILS
# ═════════════════════════════════════════════════════════════════════════════
def _compute_sla_due_at(now_iso: str, sla_hours: Optional[int]) -> Optional[str]:
    if not sla_hours or sla_hours <= 0:
        return None
    now = datetime.fromisoformat(now_iso.replace("Z", "+00:00")) if "T" in now_iso else datetime.now(timezone.utc)
    due = now + timedelta(hours=int(sla_hours))
    return due.strftime("%Y-%m-%d %H:%M:%S")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ═════════════════════════════════════════════════════════════════════════════
#  TASK CRUD
# ═════════════════════════════════════════════════════════════════════════════
async def create_task(
    *,
    claim_id: int,
    title: str,
    description: str = "",
    status_slug: str = "intimated",
    priority: str = "normal",
    assigned_to_staff_id: Optional[int] = None,
    created_by_staff_id: Optional[int] = None,
    sla_hours_override: Optional[int] = None,
    depends_on_task_id: Optional[int] = None,
    parent_task_id: Optional[int] = None,
    auto_assign: Optional[bool] = None,
) -> int:
    """Create a task. Auto-assigns via round-robin when:
       (a) caller didn't pass assigned_to_staff_id, AND
       (b) auto_assign is True/None AND system flag 'auto_assign_tasks' is on.
    """
    status = await get_status(status_slug)
    if not status:
        raise TaskError(f"Unknown status_slug: {status_slug}", 400)
    # Determine stage from status
    stage = status["stage"]
    # Compute SLA
    sla_hours = sla_hours_override if sla_hours_override is not None else status["default_sla_hours"]
    sla_due_at = _compute_sla_due_at(_now_iso(), sla_hours)
    # Auto-assign?
    final_assignee = assigned_to_staff_id
    if final_assignee is None:
        if auto_assign is None:
            flag = await get_flag("auto_assign_tasks", "1")
            auto_assign = _flag_truthy(flag)
        if auto_assign:
            final_assignee = await _pick_next_assignee()
    # Validate dependency doesn't cycle
    if depends_on_task_id:
        await _assert_no_cycle(depends_on_task_id, None)

    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("""
            INSERT INTO nidaan_tasks (
                claim_id, parent_task_id, title, description, stage, status_slug,
                priority, assigned_to_staff_id, created_by_staff_id,
                sla_hours_override, sla_due_at, depends_on_task_id, is_qc_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (claim_id, parent_task_id, title.strip(), description.strip(),
              stage, status_slug, priority, final_assignee, created_by_staff_id,
              sla_hours_override, sla_due_at, depends_on_task_id,
              int(bool(status["is_qc_required"]))))
        task_id = cur.lastrowid
        # Audit
        await conn.execute("""
            INSERT INTO nidaan_task_status_log
              (task_id, from_status, to_status, changed_by_staff_id, note)
            VALUES (?, NULL, ?, ?, ?)
        """, (task_id, status_slug, created_by_staff_id, "Task created"))
        await conn.commit()
    logger.info("Task #%d created (claim=%d, status=%s, assignee=%s)",
                task_id, claim_id, status_slug, final_assignee)
    return task_id


async def _assert_no_cycle(start_task_id: int, candidate_dep_id: Optional[int]):
    """Walk the dependency chain to ensure no cycle is created."""
    visited = set()
    cur_id = start_task_id
    async with aiosqlite.connect(db.DB_PATH) as conn:
        while cur_id and cur_id not in visited:
            if candidate_dep_id and cur_id == candidate_dep_id:
                raise TaskError("Would create dependency cycle", 400)
            visited.add(cur_id)
            c = await conn.execute(
                "SELECT depends_on_task_id FROM nidaan_tasks WHERE task_id=?", (cur_id,))
            row = await c.fetchone()
            if not row or not row[0]:
                break
            cur_id = row[0]


async def get_task(task_id: int) -> Optional[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT t.*, s.label_en AS status_label, s.label_subscriber AS status_label_subscriber,
                   s.color AS status_color, s.is_terminal AS status_is_terminal,
                   s.is_paused AS status_is_paused,
                   c.insured_name AS claim_insured_name, c.claim_type AS claim_type,
                   c.stage AS claim_stage,
                   a.name AS assignee_name, a.role AS assignee_role
            FROM nidaan_tasks t
            LEFT JOIN nidaan_status_def s ON s.slug = t.status_slug
            LEFT JOIN nidaan_claims c ON c.claim_id = t.claim_id
            LEFT JOIN nidaan_staff a ON a.staff_id = t.assigned_to_staff_id
            WHERE t.task_id = ?
        """, (task_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_tasks(
    *, claim_id: Optional[int] = None,
    assigned_to_staff_id: Optional[int] = None,
    stage: Optional[str] = None,
    status_slug: Optional[str] = None,
    include_closed: bool = False,
    limit: int = 200, offset: int = 0
) -> list[dict]:
    where = []
    params: list = []
    if claim_id is not None:
        where.append("t.claim_id = ?"); params.append(claim_id)
    if assigned_to_staff_id is not None:
        where.append("t.assigned_to_staff_id = ?"); params.append(assigned_to_staff_id)
    if stage:
        where.append("t.stage = ?"); params.append(stage)
    if status_slug:
        where.append("t.status_slug = ?"); params.append(status_slug)
    if not include_closed:
        where.append("t.closed_at IS NULL")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(f"""
            SELECT t.*, s.label_en AS status_label, s.color AS status_color,
                   s.is_terminal AS status_is_terminal, s.is_paused AS status_is_paused,
                   c.insured_name AS claim_insured_name,
                   a.name AS assignee_name
            FROM nidaan_tasks t
            LEFT JOIN nidaan_status_def s ON s.slug = t.status_slug
            LEFT JOIN nidaan_claims c ON c.claim_id = t.claim_id
            LEFT JOIN nidaan_staff a ON a.staff_id = t.assigned_to_staff_id
            {where_sql}
            ORDER BY
              CASE WHEN t.sla_due_at IS NULL THEN 1 ELSE 0 END,
              t.sla_due_at ASC, t.created_at DESC
            LIMIT ? OFFSET ?
        """, params)
        return [dict(r) for r in await cur.fetchall()]


async def kanban_view(claim_id: Optional[int] = None) -> dict[str, list[dict]]:
    """Return open tasks grouped by stage → list of tasks. Ordered for board UI."""
    tasks = await list_tasks(claim_id=claim_id, include_closed=False, limit=500)
    by_stage: dict[str, list[dict]] = {
        "intake": [], "preparation": [], "engagement": [],
        "ombudsman": [], "escalation": [], "closed": [],
    }
    for t in tasks:
        by_stage.setdefault(t["stage"], []).append(t)
    return by_stage


# ═════════════════════════════════════════════════════════════════════════════
#  STATE-MACHINE TRANSITION
# ═════════════════════════════════════════════════════════════════════════════
async def transition_task(
    *, task_id: int, to_status: str, by_staff_id: int, by_staff_role: str,
    note: str = "", metadata: Optional[dict] = None
) -> dict:
    """Execute a state transition. Validates allowed move, RBAC, dependency,
    approval. Updates SLA clock for paused/unpaused statuses. Appends to audit
    log. Returns updated task."""
    task = await get_task(task_id)
    if not task:
        raise TaskError("Task not found", 404)
    cur_status = task["status_slug"]

    # Idempotent: same status = no-op
    if cur_status == to_status:
        return task

    # Validate transition allowed by state machine + RBAC
    ok, requires_note, reason = await _transition_allowed(cur_status, to_status, by_staff_role)
    if not ok:
        raise TransitionForbidden(reason, 403)
    if requires_note and not note.strip():
        raise TaskError("This transition requires a note explaining the reason", 400)

    # Dependency check — if blocked by another non-terminal task, refuse advance
    if task["depends_on_task_id"]:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("""
                SELECT t.status_slug, s.is_terminal FROM nidaan_tasks t
                LEFT JOIN nidaan_status_def s ON s.slug=t.status_slug
                WHERE t.task_id=?
            """, (task["depends_on_task_id"],))
            dep_row = await cur.fetchone()
        if dep_row and not dep_row["is_terminal"]:
            # Allow transitioning to closure / pause but not forward
            target_status = await get_status(to_status)
            if target_status and not target_status["is_paused"] and not target_status["is_terminal"]:
                raise TransitionForbidden(
                    f"Blocked by dependency task #{task['depends_on_task_id']} (status: {dep_row['status_slug']})", 409)

    # If target status requires_approval = "both", route through approvals
    target_status = await get_status(to_status)
    if target_status and target_status.get("requires_approval") == "both":
        # Don't transition yet — open an approval request and move to awaiting_approval
        await _open_approval(task_id, to_status, by_staff_id, by_staff_role)
        return await _do_transition(task_id, "awaiting_approval", by_staff_id, note or f"Approval requested for {to_status}", metadata or {})

    return await _do_transition(task_id, to_status, by_staff_id, note, metadata or {})


async def _do_transition(task_id: int, to_status: str, by_staff_id: int, note: str, metadata: dict) -> dict:
    """Inner transition (no validation). Updates task row, audit log, SLA clock."""
    task = await get_task(task_id)
    if not task:
        raise TaskError("Task not found", 404)
    cur_status = task["status_slug"]
    cur_status_def = await get_status(cur_status) if cur_status else None
    new_status_def = await get_status(to_status)
    if not new_status_def:
        raise TaskError(f"Unknown status_slug: {to_status}", 400)

    now_str = _now_iso()
    # SLA clock: if leaving a paused state, count elapsed pause time into total
    extra_paused = 0
    paused_at = task["paused_at"]
    new_paused_at: Optional[str] = task["paused_at"]
    new_sla_due = task["sla_due_at"]

    leaving_paused = (cur_status_def and cur_status_def["is_paused"]) and not new_status_def["is_paused"]
    entering_paused = (not (cur_status_def and cur_status_def["is_paused"])) and new_status_def["is_paused"]

    if leaving_paused and paused_at:
        try:
            paused_dt = datetime.fromisoformat(str(paused_at).replace(" ", "T"))
            elapsed = max(0, int((datetime.utcnow() - paused_dt.replace(tzinfo=None)).total_seconds()))
            extra_paused = elapsed
            # Shift sla_due_at forward by elapsed paused duration
            if new_sla_due:
                due_dt = datetime.fromisoformat(str(new_sla_due).replace(" ", "T"))
                due_dt = due_dt + timedelta(seconds=elapsed)
                new_sla_due = due_dt.strftime("%Y-%m-%d %H:%M:%S")
            new_paused_at = None
        except Exception:
            new_paused_at = None
    elif entering_paused:
        new_paused_at = now_str
        # Start computing SLA from default if not yet set
        if not new_sla_due and new_status_def["default_sla_hours"]:
            new_sla_due = _compute_sla_due_at(now_str, new_status_def["default_sla_hours"])

    # If new status defines its own SLA and we don't have an override, recompute
    if not task["sla_hours_override"] and new_status_def["default_sla_hours"]:
        # If entering a non-paused status with explicit SLA — bump the due
        if not new_status_def["is_paused"]:
            new_sla_due = _compute_sla_due_at(now_str, new_status_def["default_sla_hours"])

    is_completed = bool(new_status_def["is_terminal"])
    completed_at_val = now_str if is_completed else task["completed_at"]
    closed_at_val = now_str if is_completed and "closed_" in to_status else task["closed_at"]

    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("""
            UPDATE nidaan_tasks SET
              status_slug = ?, stage = ?,
              paused_at = ?, sla_due_at = ?,
              total_paused_seconds = total_paused_seconds + ?,
              completed_at = ?, closed_at = ?,
              updated_at = datetime('now')
            WHERE task_id = ?
        """, (to_status, new_status_def["stage"], new_paused_at, new_sla_due,
              extra_paused, completed_at_val, closed_at_val, task_id))
        await conn.execute("""
            INSERT INTO nidaan_task_status_log
              (task_id, from_status, to_status, changed_by_staff_id, note, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (task_id, cur_status, to_status, by_staff_id, note.strip(),
              json.dumps(metadata) if metadata else None))
        await conn.commit()

    logger.info("Task #%d: %s → %s (by staff %d)", task_id, cur_status, to_status, by_staff_id)
    return await get_task(task_id)


# ═════════════════════════════════════════════════════════════════════════════
#  DUAL APPROVAL FLOW
# ═════════════════════════════════════════════════════════════════════════════
async def _open_approval(task_id: int, target_status: str, by_staff_id: int, by_staff_role: str):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO nidaan_task_approvals
              (task_id, requested_by, target_status_slug, final_status)
            VALUES (?, ?, ?, 'pending')
        """, (task_id, by_staff_id, target_status))
        await conn.commit()


async def record_approval(*, task_id: int, by_staff_id: int, by_staff_role: str,
                          approve: bool, note: str = "") -> dict:
    """Admin or SA records their decision on the pending approval for this task.
    When BOTH have approved, the original transition fires."""
    if by_staff_role not in ROLES_ADMIN_OR_ABOVE:
        raise TransitionForbidden("Only Admin or Super Admin can record approvals", 403)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT * FROM nidaan_task_approvals
            WHERE task_id=? AND final_status='pending'
            ORDER BY approval_id DESC LIMIT 1
        """, (task_id,))
        ap = await cur.fetchone()
        if not ap:
            raise TaskError("No pending approval for this task", 404)
        ap = dict(ap)
        now_str = _now_iso()
        # Update appropriate role's slot
        if by_staff_role == ROLE_SUPER_ADMIN:
            await conn.execute("""
                UPDATE nidaan_task_approvals SET sa_staff_id=?, sa_approved_at=?, sa_note=?
                WHERE approval_id=?
            """, (by_staff_id, now_str if approve else None, note.strip(), ap["approval_id"]))
            ap["sa_approved_at"] = now_str if approve else None
        else:  # admin
            await conn.execute("""
                UPDATE nidaan_task_approvals SET admin_staff_id=?, admin_approved_at=?, admin_note=?
                WHERE approval_id=?
            """, (by_staff_id, now_str if approve else None, note.strip(), ap["approval_id"]))
            ap["admin_approved_at"] = now_str if approve else None
        # If THIS clicker disapproved → reject overall (one veto)
        if not approve:
            await conn.execute("""
                UPDATE nidaan_task_approvals SET final_status='rejected', resolved_at=?
                WHERE approval_id=?
            """, (now_str, ap["approval_id"]))
            await conn.commit()
            # Move task back to a safe status (drafting) so work can resume
            return await _do_transition(task_id, "ombudsman_drafting" if "ombudsman" in ap["target_status_slug"] else "negotiation",
                                        by_staff_id, f"Approval rejected: {note}", {"approval_id": ap["approval_id"]})
        # Check both approved
        if ap["admin_approved_at"] and ap["sa_approved_at"]:
            await conn.execute("""
                UPDATE nidaan_task_approvals SET final_status='approved', resolved_at=?
                WHERE approval_id=?
            """, (now_str, ap["approval_id"]))
            await conn.commit()
            # Execute the original transition
            return await _do_transition(task_id, ap["target_status_slug"], by_staff_id,
                                        f"Dual-approved by admin+SA", {"approval_id": ap["approval_id"]})
        await conn.commit()
    return await get_task(task_id)


# ═════════════════════════════════════════════════════════════════════════════
#  QC FLOW
# ═════════════════════════════════════════════════════════════════════════════
async def request_qc(*, task_id: int, by_staff_id: int) -> dict:
    """Associate marks task as ready for QC."""
    return await transition_task(task_id=task_id, to_status="awaiting_qc",
                                 by_staff_id=by_staff_id, by_staff_role=ROLE_ASSOCIATE,
                                 note="Submitted for QC")


async def review_qc(*, task_id: int, by_staff_id: int, by_staff_role: str,
                    approve: bool, note: str = "") -> dict:
    """Senior approves or rejects QC."""
    if by_staff_role not in ROLES_ADMIN_OR_ABOVE:
        raise TransitionForbidden("Only Admin or Super Admin can review QC", 403)
    if approve:
        next_status = "notice_sent"  # default QC-pass target for legal_drafting
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute("""
                UPDATE nidaan_tasks SET qc_status='approved', qc_reviewer_staff_id=?,
                  qc_completed_at=datetime('now'), qc_note=?
                WHERE task_id=?
            """, (by_staff_id, note.strip(), task_id))
            await conn.commit()
        return await transition_task(task_id=task_id, to_status=next_status,
                                     by_staff_id=by_staff_id, by_staff_role=by_staff_role,
                                     note=note or "QC approved")
    else:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute("""
                UPDATE nidaan_tasks SET qc_status='rejected', qc_reviewer_staff_id=?,
                  qc_completed_at=datetime('now'), qc_note=?
                WHERE task_id=?
            """, (by_staff_id, note.strip(), task_id))
            await conn.commit()
        return await transition_task(task_id=task_id, to_status="legal_drafting",
                                     by_staff_id=by_staff_id, by_staff_role=by_staff_role,
                                     note=note or "QC rejected — please revise")


# ═════════════════════════════════════════════════════════════════════════════
#  ASSIGNMENT
# ═════════════════════════════════════════════════════════════════════════════
async def reassign_task(*, task_id: int, new_assignee_staff_id: Optional[int],
                        by_staff_id: int) -> dict:
    """Admin/SA reassigns. None = unassign."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("""
            UPDATE nidaan_tasks SET assigned_to_staff_id=?, updated_at=datetime('now')
            WHERE task_id=?
        """, (new_assignee_staff_id, task_id))
        await conn.execute("""
            INSERT INTO nidaan_task_status_log (task_id, from_status, to_status, changed_by_staff_id, note, metadata)
            SELECT task_id, status_slug, status_slug, ?, 'Reassigned',
                   json_object('new_assignee', ?)
            FROM nidaan_tasks WHERE task_id=?
        """, (by_staff_id, new_assignee_staff_id, task_id))
        await conn.commit()
    return await get_task(task_id)


# ═════════════════════════════════════════════════════════════════════════════
#  NOTES
# ═════════════════════════════════════════════════════════════════════════════
async def add_task_note(*, task_id: int, staff_id: int, note: str,
                        is_internal: bool = True,
                        parent_note_id: Optional[int] = None) -> int:
    """Add a note. If parent_note_id is set, treat as 1-level reply.
    parent_note_id is flattened — a reply to a reply is recorded as a reply
    to the original parent, keeping the thread one level deep.
    """
    if parent_note_id:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT note_id, parent_note_id, task_id FROM nidaan_task_notes WHERE note_id=?",
                (parent_note_id,))).fetchone()
            if not row or row["task_id"] != task_id:
                parent_note_id = None
            elif row["parent_note_id"]:
                parent_note_id = row["parent_note_id"]
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("""
            INSERT INTO nidaan_task_notes (task_id, staff_id, note, is_internal, parent_note_id)
            VALUES (?, ?, ?, ?, ?)
        """, (task_id, staff_id, note.strip(), int(bool(is_internal)), parent_note_id))
        await conn.commit()
        return cur.lastrowid


async def list_task_notes(task_id: int) -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT n.*, s.name AS staff_name, s.role AS staff_role
            FROM nidaan_task_notes n LEFT JOIN nidaan_staff s ON s.staff_id=n.staff_id
            WHERE n.task_id=?
            ORDER BY n.created_at ASC
        """, (task_id,))
        return [dict(r) for r in await cur.fetchall()]


async def list_task_status_log(task_id: int) -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT l.*, s.name AS staff_name FROM nidaan_task_status_log l
            LEFT JOIN nidaan_staff s ON s.staff_id=l.changed_by_staff_id
            WHERE l.task_id=?
            ORDER BY l.changed_at ASC
        """, (task_id,))
        return [dict(r) for r in await cur.fetchall()]


# ═════════════════════════════════════════════════════════════════════════════
#  STATUS CONFIG (SA only)
# ═════════════════════════════════════════════════════════════════════════════
async def upsert_status(*, slug: str, label_en: str, label_hi: str = "",
                        label_subscriber: str = "", color: str = "#94a3b8",
                        stage: str = "preparation",
                        default_sla_hours: Optional[int] = None,
                        is_paused: bool = False, is_terminal: bool = False,
                        is_qc_required: bool = False,
                        requires_approval: str = "",
                        sort_order: int = 500,
                        created_by: int = 0) -> dict:
    existing = await get_status(slug)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        if existing:
            if existing.get("system_owned"):
                # Built-in: limit edits to labels/colors/sla/sort
                await conn.execute("""
                    UPDATE nidaan_status_def SET
                      label_en=?, label_hi=?, label_subscriber=?, color=?,
                      default_sla_hours=?, sort_order=?, updated_at=datetime('now')
                    WHERE slug=?
                """, (label_en, label_hi, label_subscriber, color,
                      default_sla_hours, sort_order, slug))
            else:
                await conn.execute("""
                    UPDATE nidaan_status_def SET
                      label_en=?, label_hi=?, label_subscriber=?, color=?, stage=?,
                      default_sla_hours=?, is_paused=?, is_terminal=?, is_qc_required=?,
                      requires_approval=?, sort_order=?, updated_at=datetime('now')
                    WHERE slug=?
                """, (label_en, label_hi, label_subscriber, color, stage,
                      default_sla_hours, int(bool(is_paused)), int(bool(is_terminal)),
                      int(bool(is_qc_required)), requires_approval, sort_order, slug))
        else:
            await conn.execute("""
                INSERT INTO nidaan_status_def
                  (slug, label_en, label_hi, label_subscriber, color, stage,
                   default_sla_hours, is_paused, is_terminal, is_qc_required,
                   requires_approval, sort_order, system_owned, is_active, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)
            """, (slug, label_en, label_hi, label_subscriber, color, stage,
                  default_sla_hours, int(bool(is_paused)), int(bool(is_terminal)),
                  int(bool(is_qc_required)), requires_approval, sort_order, created_by))
        await conn.commit()
    return await get_status(slug) or {}


async def upsert_transition(*, from_slug: str, to_slug: str,
                            allowed_roles: str = "", requires_note: bool = False) -> dict:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO nidaan_status_transitions
              (from_slug, to_slug, allowed_roles, requires_note, system_owned)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(from_slug, to_slug) DO UPDATE SET
              allowed_roles=excluded.allowed_roles,
              requires_note=excluded.requires_note
        """, (from_slug, to_slug, allowed_roles, int(bool(requires_note))))
        await conn.commit()
    return {"from_slug": from_slug, "to_slug": to_slug,
            "allowed_roles": allowed_roles, "requires_note": requires_note}


async def deactivate_status(slug: str) -> None:
    """Soft-disable a non-system status. Built-ins can't be deleted."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_status_def SET is_active=0 WHERE slug=? AND system_owned=0",
            (slug,))
        await conn.commit()
