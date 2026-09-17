"""
NidaanPartner — DID THE LOGIN CODE ACTUALLY GO OUT?

On 17 Sep every branch stopped being able to log in and nothing anywhere said so. The endpoint
returned "otp_sent", Brevo's API returned 201, the logs said the mail was sent — and Google was
silently discarding every one of them because a third party cannot send mail claiming to be from
our own domain. The delivery was broken; every screen we had said it was fine.

The transport bug is fixed. This module fixes the blindness, which is the more dangerous half:
every login code we send now records what happened to it, so App Health can answer "is the way in
working, and if not, why" from evidence instead of from configuration.

Kept deliberately small:
  • NO NEW TABLE — a rolling window lives in the nidaan_ops_settings JSON blob, like the health
    watchdog's state. Login codes are low-volume, so a ring of the last few dozen is plenty.
  • NEVER RAISES — recording is a side-channel. A failure to record must never stop someone
    logging in, so every entry point swallows its own errors.
  • NO SECRETS — the code itself is never stored, and the address it went to is masked.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("nidaan.login.health")

_KEY = "login_health_ring"
_KEEP = 60           # entries; a couple of days of real traffic
_WINDOW_HOURS = 24   # what "recently" means in the summary

# The ways in we track. The label is what App Health shows.
SYSTEMS = {
    "branch": "Branch login",
    "subscriber": "Subscriber login",
    "staff": "Staff login",
    "portal": "Complainant portal",
}


def mask(target: str) -> str:
    """Enough to recognise WHICH branch or person, not enough to be a contact list.

    App Health is super-admin-only, but a health panel is the wrong place to accumulate a
    readable directory of every address and number we send codes to.
    """
    t = (target or "").strip()
    if not t:
        return "?"
    if "@" in t:
        user, _, dom = t.partition("@")
        head = user[:2] if len(user) > 3 else user[:1]
        return "%s%s@%s" % (head, "*" * max(2, len(user) - len(head)), dom)
    digits = "".join(ch for ch in t if ch.isdigit())
    return ("*" * max(0, len(digits) - 4)) + digits[-4:] if digits else "?"


async def _load() -> list:
    try:
        import biz_nidaan as _n
        raw = await _n.get_ops_setting(_KEY, "") or ""
        data = json.loads(raw) if raw else []
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def _save(ring: list) -> None:
    try:
        import biz_nidaan as _n
        # updated_by is a staff id; this writer is the system, so it stays unset.
        await _n.set_ops_setting(_KEY, json.dumps(ring[-_KEEP:])[:60000])
    except Exception as e:  # noqa: BLE001
        logger.debug("login health save failed: %s", e)


async def record(system: str, channel: str, target: str, ok: bool,
                 detail: str = "", via: str = "") -> None:
    """One login-code attempt. `detail` is the reason when it failed — that reason is the whole
    point of the record, so pass the real one, not a tidied-up version."""
    try:
        ring = await _load()
        ring.append({
            "t": datetime.utcnow().isoformat(timespec="seconds"),
            "sys": (system or "?")[:20],
            "ch": (channel or "?")[:20],
            "to": mask(target),
            "ok": bool(ok),
            "via": (via or "")[:40],
            "err": (detail or "")[:160],
        })
        await _save(ring)
    except Exception as e:  # noqa: BLE001
        logger.debug("login health record failed: %s", e)


def _age(entry: dict, now: datetime):
    try:
        return now - datetime.fromisoformat(entry.get("t") or "")
    except (TypeError, ValueError):
        return None


async def summary() -> dict:
    """{system: {sent, failed, last_at, last_ok, last_via, last_error, channels}} over the window.

    Everything a check needs to say what is working and why it isn't.
    """
    ring = await _load()
    now = datetime.utcnow()
    out: dict = {}
    for e in ring:
        age = _age(e, now)
        if age is None or age > timedelta(hours=_WINDOW_HOURS):
            continue
        s = out.setdefault(e.get("sys") or "?", {
            "sent": 0, "failed": 0, "last_at": "", "last_ok": None,
            "last_via": "", "last_error": "", "channels": {},
        })
        ok = bool(e.get("ok"))
        s["sent"] += 1
        if not ok:
            s["failed"] += 1
            s["last_error"] = e.get("err") or ""
        ch = s["channels"].setdefault(e.get("ch") or "?", {"sent": 0, "failed": 0})
        ch["sent"] += 1
        if not ok:
            ch["failed"] += 1
        # The ring is append-ordered, so the last one seen is the most recent.
        s["last_at"] = e.get("t") or ""
        s["last_ok"] = ok
        s["last_via"] = e.get("via") or ""
    return out


async def recent(limit: int = 20) -> list:
    """The newest attempts first — the detail view behind the check."""
    ring = await _load()
    return list(reversed(ring[-max(1, int(limit)):]))
