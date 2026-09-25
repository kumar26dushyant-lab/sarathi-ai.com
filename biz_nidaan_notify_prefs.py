# -*- coding: utf-8 -*-
"""Who wants to hear what — the switches behind the notification register.

Founder, 25 Sep 2026, answering the two questions this was waiting on:
  *"per event per role and per event per specific user involved, of course claim level settings
  will take precedence."*
And why it matters:
  *"just so I should not depend on notification thing on you every time to do code changes until
  anything breaks."*

That last sentence is the specification. Anything he can only change by asking me to edit code is
a failure of this module.

THE CHAIN, most specific first. The first rule that has an opinion wins, and the answer carries
the reason so a screen can show *why* somebody is or is not being told.

    1. claim × user    "stop telling ME about claim 200"
    2. user            "never send ME claim.status"
    3. role            "team members do not get bucket.move"
    4. the policy      biz_nidaan_notify_policy — what happens today
    5. on by default   an event nobody has an opinion about is sent

WHAT CANNOT BE SWITCHED OFF. Money, security and system health, exactly as the register already
locks them (biz_nidaan_notify_registry.EVENTS[*]["locked"]). A preference against a locked event
is not an error and is not silently dropped — it is stored, and ignored, and the resolver says so.
An off switch on "a customer paid and we have no record" is a footgun whoever flips it.

AND THE BELL IS NEVER SILENCED. Telegram and email interrupt a person; the dashboard bell waits
to be looked at. Turning it off would delete the record of having been told rather than stop an
interruption — and that is the difference between quiet and blind, which this project has already
paid to learn once.
"""
from __future__ import annotations

import logging

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.notify.prefs")


def _db() -> str:
    """The database, asked for at the moment it is needed, never remembered from import time.

    Tests and the journey runner point `db.DB_PATH` at a copy after this module is already
    imported; a snapshot taken at import would have them silently reading the live switches.
    """
    return db.DB_PATH

# The channels a preference can speak about. `bell` is deliberately absent: see the module note.
CHANNELS = ("telegram", "email")
ALL_EVENTS = "*"          # a preference that covers every event
ALL_CHANNELS = "*"        # ...and every channel it is allowed to touch

# How often, not just whether. `off` is the same as disabled and is kept as a separate word
# because that is how a person says it.
#
# `daily` IS NOT BUILT YET. There is no digest to hold a message in, so a daily preference
# currently behaves as immediate: the message still goes. That is the safe direction - a half-made
# digest would swallow notifications into a queue nobody drains, and quiet is worse than noisy
# here. Until the digest exists, the settings screen deliberately offers on/off only, so nobody
# can set something that does not do what it says.
FREQ_IMMEDIATE = "immediate"
FREQ_DAILY = "daily"      # accepted and stored; behaves as immediate until the digest is built
FREQ_OFF = "off"
FREQUENCIES = (FREQ_IMMEDIATE, FREQ_DAILY, FREQ_OFF)

SCOPE_CLAIM_USER = "claim_user"
SCOPE_USER = "user"
SCOPE_ROLE = "role"
# Order matters: this IS the precedence chain.
_SCOPE_ORDER = (SCOPE_CLAIM_USER, SCOPE_USER, SCOPE_ROLE)


def _locked(event_key: str) -> bool:
    """Is this one of the events nobody may switch off? Asked of the register, never restated."""
    try:
        import biz_nidaan_notify_registry as _reg
        e = _reg.BY_KEY.get((event_key or "").strip().lower())
        return bool(e and e.get("locked"))
    except Exception:  # noqa: BLE001
        # If the register cannot be read, treat the event as locked. Failing towards "you will be
        # told" is the safe direction for a notification.
        return True


async def set_pref(*, scope: str, event_key: str, channel: str = ALL_CHANNELS,
                   enabled: bool = True, frequency: str = FREQ_IMMEDIATE,
                   role: str = "", staff_id: int | None = None, claim_id: int | None = None,
                   updated_by: str = "") -> dict:
    """Record one preference. Returns {ok, ignored_because} — a switch against a locked event is
    STORED and reported, not refused: the person set it, and hiding that it will not take effect
    is how a screen starts lying."""
    scope = (scope or "").strip().lower()
    if scope not in _SCOPE_ORDER:
        return {"ok": False, "error": "unknown scope %r" % scope}
    if frequency not in FREQUENCIES:
        return {"ok": False, "error": "unknown frequency %r" % frequency}
    if channel != ALL_CHANNELS and channel not in CHANNELS:
        return {"ok": False, "error": "unknown channel %r" % channel}
    if scope == SCOPE_ROLE and not role:
        return {"ok": False, "error": "a role preference needs a role"}
    if scope in (SCOPE_USER, SCOPE_CLAIM_USER) and not staff_id:
        return {"ok": False, "error": "that preference needs a staff member"}
    if scope == SCOPE_CLAIM_USER and not claim_id:
        return {"ok": False, "error": "a claim preference needs a claim"}

    ek = (event_key or "").strip().lower() or ALL_EVENTS
    async with aiosqlite.connect(_db()) as c:
        await c.execute(
            "INSERT INTO nidaan_notify_prefs (scope, role, staff_id, claim_id, event_key, "
            "channel, enabled, frequency, updated_by, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(scope, COALESCE(role,''), COALESCE(staff_id,0), COALESCE(claim_id,0), "
            "event_key, channel) DO UPDATE SET enabled=excluded.enabled, "
            "frequency=excluded.frequency, updated_by=excluded.updated_by, "
            "updated_at=CURRENT_TIMESTAMP",
            (scope, role or None, staff_id, claim_id, ek, channel,
             1 if enabled else 0, frequency, (updated_by or "")[:80]))
        await c.commit()
    out = {"ok": True}
    if _locked(ek) and (not enabled or frequency == FREQ_OFF):
        out["ignored_because"] = ("money, security and system health cannot be switched off — "
                                 "this is saved, but it will not take effect")
    return out


async def clear_pref(*, scope: str, event_key: str, channel: str = ALL_CHANNELS,
                     role: str = "", staff_id: int | None = None,
                     claim_id: int | None = None) -> dict:
    """Remove one preference so the chain falls through to the next level.

    NOT a delete of anybody's data — it is one switch returning to its default, which is the only
    way to say "go back to whatever the role says". The founder's standing rule about deletion is
    about records; this is a setting.
    """
    async with aiosqlite.connect(_db()) as c:
        await c.execute(
            "DELETE FROM nidaan_notify_prefs WHERE scope=? AND COALESCE(role,'')=? "
            "AND COALESCE(staff_id,0)=? AND COALESCE(claim_id,0)=? AND event_key=? AND channel=?",
            ((scope or "").strip().lower(), role or "", staff_id or 0, claim_id or 0,
             (event_key or "").strip().lower() or ALL_EVENTS, channel))
        await c.commit()
    return {"ok": True}


async def _match(c, scope: str, event_key: str, channel: str, *,
                 role: str = "", staff_id=None, claim_id=None):
    """The best row at ONE scope: an exact event beats `*`, an exact channel beats `*`."""
    rows = [dict(r) for r in await (await c.execute(
        "SELECT event_key, channel, enabled, frequency FROM nidaan_notify_prefs "
        "WHERE scope=? AND COALESCE(role,'')=? AND COALESCE(staff_id,0)=? "
        "AND COALESCE(claim_id,0)=? AND event_key IN (?,?) AND channel IN (?,?)",
        (scope, role or "", staff_id or 0, claim_id or 0,
         event_key, ALL_EVENTS, channel, ALL_CHANNELS))).fetchall()]
    if not rows:
        return None
    rows.sort(key=lambda r: ((0 if r["event_key"] != ALL_EVENTS else 1),
                             (0 if r["channel"] != ALL_CHANNELS else 1)))
    return rows[0]


async def resolve(event_key: str, *, channel: str, staff_id: int | None = None,
                  role: str = "", claim_id: int | None = None,
                  involved: bool = True, owner: bool = False) -> dict:
    """Should this person be told, on this channel? Returns {send, frequency, why, locked}.

    `why` is written to be shown to a person, because "why am I not getting these?" is the
    question this module exists to answer without asking me.
    """
    ek = (event_key or "").strip().lower()
    ch = (channel or "").strip().lower()

    # The bell is not an interruption and is never switched off. See the module note.
    if ch not in CHANNELS:
        return {"send": True, "frequency": FREQ_IMMEDIATE, "locked": False,
                "why": "the dashboard bell always records it"}

    if _locked(ek):
        return {"send": True, "frequency": FREQ_IMMEDIATE, "locked": True,
                "why": "money, security and system health cannot be switched off"}

    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            for scope in _SCOPE_ORDER:
                if scope == SCOPE_CLAIM_USER and not (claim_id and staff_id):
                    continue
                if scope == SCOPE_USER and not staff_id:
                    continue
                if scope == SCOPE_ROLE and not role:
                    continue
                hit = await _match(
                    c, scope, ek, ch,
                    role=(role if scope == SCOPE_ROLE else ""),
                    staff_id=(staff_id if scope in (SCOPE_USER, SCOPE_CLAIM_USER) else None),
                    claim_id=(claim_id if scope == SCOPE_CLAIM_USER else None))
                if not hit:
                    continue
                freq = hit["frequency"] or FREQ_IMMEDIATE
                on = bool(hit["enabled"]) and freq != FREQ_OFF
                where = {SCOPE_CLAIM_USER: "this claim, for you",
                         SCOPE_USER: "your own setting",
                         SCOPE_ROLE: "the setting for %s" % (role or "your role")}[scope]
                return {"send": on, "frequency": freq, "locked": False,
                        "why": ("%s — %s" % (where, "on" if on else "off"))}
    except Exception as e:  # noqa: BLE001
        # FAIL TOWARDS BEING TOLD. A preferences table that will not answer must not silence a
        # notification: the failure people notice is noise, the failure that costs money is the
        # message that never came.
        logger.warning("notify prefs unreadable for %s (%s) — falling back to the policy", ek, e)

    # Nobody has an opinion: whatever the policy does today.
    try:
        import biz_nidaan_notify_policy as _pol
        if ch == "email":
            ok, why = _pol.should_email(ek, role=role, involved=involved, owner=owner)
            return {"send": bool(ok), "frequency": FREQ_IMMEDIATE, "locked": False,
                    "why": "no setting — %s" % why}
    except Exception:  # noqa: BLE001
        pass
    return {"send": True, "frequency": FREQ_IMMEDIATE, "locked": False, "why": "no setting"}


async def list_prefs(*, scope: str = "", staff_id: int | None = None, role: str = "",
                     claim_id: int | None = None, limit: int = 500) -> list[dict]:
    """Every switch somebody has set, for the screen that shows them."""
    q = ("SELECT pref_id, scope, COALESCE(role,'') role, staff_id, claim_id, event_key, channel, "
         "enabled, frequency, COALESCE(updated_by,'') updated_by, updated_at "
         "FROM nidaan_notify_prefs")
    conds, params = [], []
    if scope:
        conds.append("scope=?"); params.append(scope)
    if staff_id:
        conds.append("staff_id=?"); params.append(int(staff_id))
    if role:
        conds.append("COALESCE(role,'')=?"); params.append(role)
    if claim_id:
        conds.append("claim_id=?"); params.append(int(claim_id))
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY scope, event_key LIMIT ?"
    params.append(int(limit))
    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            return [dict(r) for r in await (await c.execute(q, params)).fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.warning("could not list notification preferences: %s", e)
        return []
