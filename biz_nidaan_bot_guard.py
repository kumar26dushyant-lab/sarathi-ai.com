# -*- coding: utf-8 -*-
"""What a linked Telegram account may do, how often, and what gets written down.

Founder, 26 Sep 2026, on letting staff send claim documents through the bot:
  *"for that reason we need to make bot highly secure from cybersecurity point of view"*

The bot has had NO rate limiting of any kind. Every HTTP route is behind slowapi; the bot is a
long-polling loop, so none of that applies to it. A linked account - which is a phone, and a
phone can be borrowed, shared, stolen or simply left unlocked on a desk - could until now ask
the AI a thousand questions, pull a thousand files, or walk claim numbers one after another, and
nothing would slow it down or leave a mark.

TWO KINDS OF LIMIT, and they fail in opposite directions on purpose:

  - NAVIGATION (menus, task lists) fails OPEN. If the guard itself breaks, staff keep working.
    The damage from unlimited menu taps is a warm CPU.
  - EXPENSIVE OR DANGEROUS (AI questions, file downloads, claim lookups) fails CLOSED. Those
    cost money, touch medical documents, or can be used to find out which claim numbers exist.
    If we cannot tell whether someone is over the line, the answer is no.

COUNTED IN MEMORY, ON PURPOSE. The polling loop is a single worker process, so a dict is enough
and it costs no database write per button press - and a limiter that writes a row every time
somebody taps a menu is a limiter that becomes the load. A worker restart clears the counters,
which is fine for throttling abuse: nobody can make the worker restart to get a fresh allowance.
What must survive a restart is the RECORD of what was done, and that goes to the database.
"""
from __future__ import annotations

import logging
import time
from collections import deque

logger = logging.getLogger("nidaan.bot.guard")

# action -> (how many, per how many seconds, fail_closed)
LIMITS: dict[str, tuple[int, int, bool]] = {
    "nav":    (90, 60, False),     # menus, lists, going back - generous, fails open
    "write":  (30, 60, True),      # notes, stage moves, task creation
    "ai":     (20, 3600, True),    # Gemini costs real money per question
    "claim":  (60, 3600, True),    # claim lookups - also the enumeration surface
    "upload": (40, 3600, True),    # files attached to claims
}

# A Telegram bot cannot download anything larger than 20 MB anyway; saying so ourselves means a
# clear message to the person instead of a confusing failure from the API.
from biz_nidaan_limits import TELEGRAM_BOT_MAX_BYTES as MAX_FILE_BYTES, DOC_MAX_MB  # Telegram's rule
MAX_FILES_PER_BATCH = 10

_hits: dict[tuple[int, str], deque] = {}


def _window(staff_id: int, action: str) -> deque:
    key = (int(staff_id or 0), action)
    d = _hits.get(key)
    if d is None:
        d = deque()
        _hits[key] = d
    return d


def allow(staff_id: int | None, action: str) -> dict:
    """May this person do this now? {ok, retry_after, reason}.

    `reason` is written to be shown to the person, plainly and without blame - somebody who is
    simply working fast should not be told they look like an attacker.
    """
    limit = LIMITS.get(action)
    if not limit:
        return {"ok": True, "retry_after": 0, "reason": ""}
    count, per, fail_closed = limit
    try:
        sid = int(staff_id or 0)
        if sid <= 0:
            return {"ok": False, "retry_after": 0, "reason": "Please connect your Telegram first."}
        now = time.monotonic()
        w = _window(sid, action)
        while w and (now - w[0]) > per:
            w.popleft()
        if len(w) >= count:
            wait = int(per - (now - w[0])) + 1
            logger.info("bot guard: staff %s over the %s limit (%d/%ds)", sid, action, count, per)
            return {"ok": False, "retry_after": wait,
                    "reason": ("That is a lot at once. Please wait %s and try again."
                               % _human(wait))}
        w.append(now)
        return {"ok": True, "retry_after": 0, "reason": ""}
    except Exception as e:  # noqa: BLE001
        logger.warning("bot guard failed for %s/%s: %s", staff_id, action, e)
        if fail_closed:
            return {"ok": False, "retry_after": 5,
                    "reason": "Could not do that just now. Please try again."}
        return {"ok": True, "retry_after": 0, "reason": ""}


def _human(seconds: int) -> str:
    if seconds < 60:
        return "%d seconds" % max(seconds, 1)
    if seconds < 3600:
        return "%d minutes" % ((seconds + 59) // 60)
    return "%d hours" % ((seconds + 3599) // 3600)


def check_file(name: str, data: bytes) -> dict:
    """Size and emptiness, before anything else looks at it. {ok, reason}.

    This is NOT the virus scan and NOT the type check - biz_nidaan_doc_intake.accept() does both,
    fail-closed, and is the single place that decides what may be stored. This only stops the
    obviously impossible early, so the person gets a sentence they can act on instead of a
    failure five steps later.
    """
    n = len(data or b"")
    if n == 0:
        return {"ok": False, "reason": "That file came through empty. Please send it again."}
    return check_size(n)


def check_size(n: int) -> dict:
    """Over Telegram's own 20 MB rule for bots? Checked on the size Telegram DECLARES, before
    downloading - a bigger file used to fail inside Telegram and read "did not come through"."""
    if n and n > MAX_FILE_BYTES:
        return {"ok": False,
                "reason": ("That file is %d MB. Telegram lets a bot receive files up to %d MB only - "
                           "please upload it on the website instead (up to %d MB), or send a smaller scan."
                           % (n // (1024 * 1024), MAX_FILE_BYTES // (1024 * 1024), DOC_MAX_MB))}
    return {"ok": True, "reason": ""}


async def record(staff: dict | None, action: str, *, claim_id=None, detail: str = "",
                 allowed: bool = True) -> None:
    """Write down what was done - or refused - through the bot.

    Refusals are recorded as well as successes, deliberately. A refused upload against somebody
    else's claim is exactly the event worth seeing later, and a trail that only holds what
    succeeded cannot show an attempt. Best-effort: the audit must never be the reason an action
    fails, but a failure to write it IS logged rather than swallowed.
    """
    staff = staff or {}
    try:
        import biz_nidaan as nidaan
        await nidaan.log_activity(
            action=("bot." + action) if allowed else ("bot.refused." + action),
            actor_type="staff", actor_id=staff.get("staff_id"),
            actor_name=(staff.get("name") or "")[:80],
            actor_role=staff.get("role", ""),
            target_type=("claim" if claim_id else "telegram"),
            target_id=(claim_id or 0), detail=detail[:400], ip="telegram")
    except Exception as e:  # noqa: BLE001
        logger.warning("could not record bot action %s for staff %s: %s",
                       action, staff.get("staff_id"), e)


def reset_for_tests() -> None:
    """Clear the counters. Only for tests - nothing in the app calls this."""
    _hits.clear()
