"""
NidaanPartner END-OF-DAY SUMMARY on Telegram - the team's, and each person's own.

Founder, 30 Sep: "End of the day telegram summary bucket-wise working and also how many claims move
from one bucket to another, and who did it ... send to all superadmins and every staff will get
their individual working summary, for example, Dr. Ashish worked on 5 cases and which bucket ...
voice note summary too in their preferred language hindi/english ... it's saying dollar instead of
rupee, make sure this is not happening anywhere else."

At 20:00 IST:
  * every super-admin gets the TEAM summary: where the claims are now, bucket by bucket, with how
    many came in and went out today; every move today, by person, from -> to; who worked on how
    many claims and in which bucket; who has nothing recorded (leave shown separately); new
    claims, payments and what is overdue - plus their own day if they worked;
  * every other active staff member with Telegram gets THEIR OWN day - the claims they worked on
    and where those claims sit, the moves they made, what they did, their tasks. A day with
    nothing recorded sends nothing (a message saying "nothing" every evening is how people learn
    to ignore the bot);
  * each message comes with a voice note in the person's language (English, Hindi or Hinglish).

Written from our own records with fixed wording in each language - no AI. A summary is the one
place a made-up number or a "$" would do real harm, and the facts are already exact. Voices read
money through biz_speakable, so rupees are always said as rupees.

It reports what the system RECORDED. Work done off the system does not appear, which is itself a
reason for staff to record their work on the claim.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.daily_summary")
DB_PATH = db.DB_PATH
IST = timezone(timedelta(hours=5, minutes=30))
LAST_KEY = "daily_summary_last"
L2_WAITING = "l2_claims"
INTAKE = "_intake"
_CLOSED = ("closed", "withdrawn", "resolved_won", "resolved_lost")

# What each recorded action means, in words a person would use. Anything not listed is counted
# under "other actions" rather than shown as a code.
ACTIONS = {
    "claim.doc_upload":        ("documents uploaded", "दस्तावेज़ अपलोड किए", "documents upload kiye"),
    "doc.tick":                ("documents checked off", "दस्तावेज़ टिक किए", "documents tick kiye"),
    "claim.docs_complete":     ("marked 'all documents received'", "'सभी दस्तावेज़ मिले' लगाया", "'sab documents mile' lagaya"),
    "claim.doc_rename":        ("documents renamed", "दस्तावेज़ का नाम बदला", "documents ka naam badla"),
    "claim.doc_delete":        ("documents removed", "दस्तावेज़ हटाए", "documents hataye"),
    "claim.doc_set":           ("document sets prepared", "दस्तावेज़ सेट बनाए", "document sets banaye"),
    "claim.contact_confirm":   ("contact confirmations sent", "संपर्क पुष्टि भेजी", "contact confirmation bheje"),
    "claim.info_edit":         ("claim details corrected", "क्लेम की जानकारी सुधारी", "claim details sudhaare"),
    "claim.gist":              ("case gists written", "केस का सार लिखा", "case gist likhe"),
    "claimant_portal.link":    ("claim-page links sent", "क्लेम पेज लिंक भेजे", "claim page links bheje"),
    "claimant_portal.email":   ("claim-page emails sent", "क्लेम पेज ईमेल भेजे", "claim page emails bheje"),
    "claim_message":           ("messages to customers", "ग्राहकों को संदेश", "customers ko messages"),
    "l2.handover":             ("handed to Level-2", "लेवल-2 को सौंपा", "Level-2 ko saunpa"),
    "l2.pay_link":             ("payment links sent", "भुगतान लिंक भेजे", "payment links bheje"),
    "claim.raised_on_behalf":  ("raised for the subscriber", "सब्सक्राइबर के लिए दर्ज किया", "subscriber ke liye darj kiya"),
    "case.draft_query":        ("draft queries raised", "ड्राफ़्ट सवाल उठाए", "draft queries uthaye"),
    "case.assign":             ("assigned", "सौंपा", "assign kiya"),
    "claim.assign":            ("assigned", "सौंपा", "assign kiya"),
    "claim.note":              ("notes added", "नोट जोड़े", "notes jode"),
    "claim.status":            ("status changed", "स्टेटस बदला", "status badla"),
    "case.draft_query_resolved": ("draft query answered", "ड्राफ़्ट सवाल का जवाब", "draft query ka jawab"),
    "claim.escalation_answered": ("escalation answered", "एस्केलेशन का जवाब", "escalation ka jawab"),
    "escalation.reply":        ("insurer's reply recorded", "बीमा कंपनी का जवाब दर्ज", "insurer ka jawab darj"),
    "claimant_portal.push_auth": ("authorisation requested", "अनुमति माँगी", "authorisation maangi"),
    "case.query_contact":      ("query sent to the customer", "ग्राहक से सवाल पूछा", "customer se sawal poocha"),
    "doc.request":             ("documents requested", "दस्तावेज़ माँगे", "documents maange"),
    "claim.doc_set_parts":     ("document sets prepared", "दस्तावेज़ सेट बनाए", "document sets banaye"),
    "claim.doc_auto":          ("documents sorted", "दस्तावेज़ छाँटे", "documents chhante"),
    "claim.involve":           ("colleagues involved", "साथियों को जोड़ा", "saathiyon ko joda"),
    "note":                    ("notes written", "नोट लिखे", "notes likhe"),
    "doc_reminder":            ("document reminders sent", "दस्तावेज़ रिमाइंडर भेजे", "document reminders bheje"),
    "doc_call":                ("calls made about documents", "दस्तावेज़ के लिए कॉल किए", "documents ke liye call kiye"),
    "contact_confirm_sent":    ("contact confirmations sent", "संपर्क पुष्टि भेजी", "contact confirmation bheje"),
    # 2 Oct: the work staff report in their own evening messages that was not counted before.
    "doc.chase":               ("documents chased", "दस्तावेज़ के लिए याद दिलाया", "documents ke liye yaad dilaya"),
    "doc.called":              ("calls made about documents", "दस्तावेज़ के लिए कॉल किए", "documents ke liye call kiye"),
    "doc.add":                 ("documents added to the list", "दस्तावेज़ सूची में जोड़े", "documents list mein jode"),
    "doc_sorted":              ("WhatsApp files filed on claims", "WhatsApp फ़ाइलें क्लेम पर लगाईं", "WhatsApp files claim par lagayi"),
    "claim.wa_start":          ("WhatsApp document collection started", "WhatsApp से दस्तावेज़ माँगना शुरू किया", "WhatsApp se documents maangna shuru kiya"),
    "wa.reply":                ("WhatsApp replies to customers", "ग्राहकों को WhatsApp जवाब", "customers ko WhatsApp jawab"),
    "case.secret_set":         ("case email / password updated", "केस ईमेल / पासवर्ड अपडेट", "case email / password update"),
    "case.blocker":            ("blockers recorded", "रुकावट दर्ज की", "rukawat darj ki"),
}

# What counts as what. Progress and follow-ups are the work; document handling is the work's
# raw material; notes are the record; the rest is housekeeping and is never counted as
# achievement (founder: "not only claim open closed and edit for no reason ... records high
# number achieved, that doesnt make any sense").
PROGRESS = {"l2.handover", "claim.docs_complete", "claim.status", "case.draft_query_resolved",
            "claim.escalation_answered", "escalation.reply", "claim.raised_on_behalf"}
FOLLOW = {"claim_message", "claimant_portal.link", "claimant_portal.email", "claimant_portal.push_auth",
          "claim.contact_confirm", "l2.pay_link", "doc.request", "case.query_contact",
          "doc_reminder", "doc_call", "contact_confirm_sent", "doc.chase", "doc.called",
          "claim.wa_start", "wa.reply", "case.secret_set"}
DOCS = {"claim.doc_upload", "doc.tick", "claim.doc_set", "claim.doc_set_parts", "claim.doc_rename",
        "claim.doc_delete", "claim.doc_auto", "doc.remove", "myclaim.doc_delete", "doc.add", "doc_sorted"}
NOTES = {"claim.gist", "case.draft_query", "note", "case.blocker"}
KINDS = ("progress", "follow", "docs", "notes", "other")
KIND_WORDS = {
    "en": {"progress": "moved forward", "follow": "followed up", "docs": "documents",
           "notes": "notes", "other": "only edited"},
    "hi": {"progress": "आगे बढ़ाए", "follow": "फ़ॉलो-अप", "docs": "दस्तावेज़",
           "notes": "नोट", "other": "सिर्फ़ बदलाव"},
    "hinglish": {"progress": "aage badhaye", "follow": "follow-up", "docs": "documents",
                 "notes": "notes", "other": "sirf edit"},
}


def kind_of(action: str) -> str:
    if action in PROGRESS:
        return "progress"
    if action in FOLLOW:
        return "follow"
    if action in DOCS:
        return "docs"
    if action in NOTES:
        return "notes"
    return "other"
# Moves are counted from the move record, not twice from the audit log.
_MOVE_ACTIONS = {"bucket.move", "case.pipeline_move", "case.pipeline_start", "l2.handover_undo"}

T = {
    "en": {
        "team_head": "🌙 *NidaanPartner — today* ({d})",
        "own_head": "🌙 *Your day* ({d})",
        "new_claims": "New claims: {n}", "payments": "Payments received: {n} ({amt})",
        "where_now": "*Where the claims are now* (came in / went out today):",
        "moves_head": "*Moves today* ({n}):", "moves_none": "No claims moved between buckets today.",
        "who_head": "*Who worked on what:*",
        "worked": "{name} — {n} claim(s): {where}",
        "moved_n": "{name} — {n} move(s): {what}",
        "idle": "Nothing recorded today: {names}", "leave": "On leave: {names}",
        "pend": "Still open: {o} overdue task(s) · {u} Level-2 claim(s) with nobody assigned",
        "you_worked": "You worked on *{n} claim(s)*:", "you_moved": "You moved *{n} claim(s)*:",
        "you_did": "What you did: {what}", "tasks": "Tasks: {done} done · {over} overdue",
        "thanks": "Thank you for today 🙏",
        "l2": "Level-2 claims (waiting)", "intake": "Intake & review",
        "other": "other actions", "your_part": "*Your own day:*",
        "v_team": "NidaanPartner, today. {new} new claims. {pay}{moves} claims moved between buckets. {who}",
        "v_pay": "{n} payments received, {amt} in total. ",
        "v_who": "{name} worked on {n} claims. ",
        "v_own": "Your day. You worked on {n} claims{where}. {moved}{tasks}Thank you for today.",
        "v_where": ", mostly in {b}", "v_moved": "You moved {n} claims. ",
        "v_tasks": "You finished {n} tasks. ",
        "blk_head": "*Blockers on our side* ({n}; {u} with NOBODY on them):", "nobody": "⚠️ NOBODY", "owner": "owner",
        "focus": "Focus: {what}", "pad_head": "*Worth a look* (counts that grew without a claim moving):",
    },
    "hi": {
        "team_head": "🌙 *NidaanPartner — आज* ({d})",
        "own_head": "🌙 *आपका दिन* ({d})",
        "new_claims": "नए क्लेम: {n}", "payments": "भुगतान मिले: {n} ({amt})",
        "where_now": "*क्लेम अभी कहाँ हैं* (आज आए / आज गए):",
        "moves_head": "*आज की मूव* ({n}):", "moves_none": "आज कोई क्लेम एक बकेट से दूसरे में नहीं गया।",
        "who_head": "*किसने किस पर काम किया:*",
        "worked": "{name} — {n} क्लेम: {where}",
        "moved_n": "{name} — {n} मूव: {what}",
        "idle": "आज कुछ दर्ज नहीं: {names}", "leave": "छुट्टी पर: {names}",
        "pend": "बाकी: {o} टास्क समय से पीछे · {u} लेवल-2 क्लेम किसी को नहीं सौंपे",
        "you_worked": "आपने *{n} क्लेम* पर काम किया:", "you_moved": "आपने *{n} क्लेम* आगे/पीछे किए:",
        "you_did": "आपने क्या किया: {what}", "tasks": "टास्क: {done} पूरे · {over} समय से पीछे",
        "thanks": "आज के काम के लिए धन्यवाद 🙏",
        "l2": "लेवल-2 क्लेम (इंतज़ार में)", "intake": "इनटेक और रिव्यू",
        "other": "अन्य काम", "your_part": "*आपका अपना दिन:*",
        "v_team": "NidaanPartner, आज का सार। {new} नए क्लेम। {pay}{moves} क्लेम एक बकेट से दूसरे में गए। {who}",
        "v_pay": "{n} भुगतान मिले, कुल {amt}। ",
        "v_who": "{name} ने {n} क्लेम पर काम किया। ",
        "v_own": "आपका दिन। आपने {n} क्लेम पर काम किया{where}। {moved}{tasks}आज के काम के लिए धन्यवाद।",
        "v_where": ", ज़्यादातर {b} में", "v_moved": "आपने {n} क्लेम आगे बढ़ाए। ",
        "v_tasks": "आपने {n} टास्क पूरे किए। ",
        "blk_head": "*हमारी तरफ़ रुके क्लेम* ({n}; {u} पर कोई नहीं):", "nobody": "⚠️ कोई नहीं", "owner": "ज़िम्मेदार",
        "focus": "ध्यान दें: {what}", "pad_head": "*एक नज़र देखें* (गिनती बढ़ी, क्लेम आगे नहीं बढ़ा):",
    },
    "hinglish": {
        "team_head": "🌙 *NidaanPartner — aaj* ({d})",
        "own_head": "🌙 *Aapka din* ({d})",
        "new_claims": "Naye claims: {n}", "payments": "Payment mile: {n} ({amt})",
        "where_now": "*Claims abhi kahan hain* (aaj aaye / aaj gaye):",
        "moves_head": "*Aaj ke moves* ({n}):", "moves_none": "Aaj koi claim ek bucket se doosre mein nahi gaya.",
        "who_head": "*Kisne kis par kaam kiya:*",
        "worked": "{name} — {n} claim: {where}",
        "moved_n": "{name} — {n} move: {what}",
        "idle": "Aaj kuch record nahi: {names}", "leave": "Chhutti par: {names}",
        "pend": "Baaki: {o} task late · {u} Level-2 claims kisi ko assign nahi",
        "you_worked": "Aapne *{n} claims* par kaam kiya:", "you_moved": "Aapne *{n} claims* move kiye:",
        "you_did": "Aapne kya kiya: {what}", "tasks": "Tasks: {done} poore · {over} late",
        "thanks": "Aaj ke kaam ke liye dhanyavaad 🙏",
        "l2": "Level-2 claims (intezaar mein)", "intake": "Intake aur review",
        "other": "aur kaam", "your_part": "*Aapka apna din:*",
        "v_team": "NidaanPartner, aaj ka saar. {new} naye claims. {pay}{moves} claims ek bucket se doosre mein gaye. {who}",
        "v_pay": "{n} payment mile, kul {amt}. ",
        "v_who": "{name} ne {n} claims par kaam kiya. ",
        "v_own": "Aapka din. Aapne {n} claims par kaam kiya{where}. {moved}{tasks}Aaj ke kaam ke liye dhanyavaad.",
        "v_where": ", zyada tar {b} mein", "v_moved": "Aapne {n} claims move kiye. ",
        "v_tasks": "Aapne {n} tasks poore kiye. ",
        "blk_head": "*Hamari taraf ruke claims* ({n}; {u} par koi nahi):", "nobody": "⚠️ KOI NAHI", "owner": "owner",
        "focus": "Focus: {what}", "pad_head": "*Ek nazar dekhein* (count badha, claim aage nahi badha):",
    },
}
_LI = {"en": 0, "hi": 1, "hinglish": 2}


def _lang(v: str) -> str:
    v = (v or "en").strip().lower()
    return v if v in T else "en"


def _inr(rupees: float) -> str:
    """₹1,56,48,929 / ₹588.82 - Indian grouping, paise only when there are some."""
    paise_total = int(round((rupees or 0) * 100))
    n, paise = divmod(abs(paise_total), 100)
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return "₹" + s + ((".%02d" % paise) if paise else "")


# ── collecting the day ───────────────────────────────────────────────────────
async def gather(start_utc: str, end_utc: str, today_ist: str) -> dict:
    import biz_nidaan_moves as _mv
    out = {"staff": [], "on_leave": set(), "audit": [], "moves": [], "notes": [], "acts": [],
           "claims": {},
           "buckets": {}, "bucket_order": [], "snapshot": {}, "claims_new": 0,
           "payments_n": 0, "payments_rs": 0.0, "tasks_done": {}, "tasks_over": {},
           "overdue_tasks": 0, "l2_unassigned": 0}
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row

        async def q(sql, args=()):
            try:
                return [dict(r) for r in await (await c.execute(sql, args)).fetchall()]
            except Exception as e:  # noqa: BLE001 - one missing source never sinks the summary
                logger.info("summary query skipped: %s", e)
                return []

        out["staff"] = await q(
            "SELECT staff_id, name, role, COALESCE(telegram_chat_id,'') chat, "
            "COALESCE(telegram_lang,'en') lang FROM nidaan_staff "
            "WHERE status='active' AND deleted_at IS NULL ORDER BY name")
        out["on_leave"] = {r["staff_id"] for r in await q(
            "SELECT staff_id FROM nidaan_leave_requests WHERE status='approved' "
            "AND start_date<=? AND end_date>=?", (today_ist, today_ist))}
        for b in await q("SELECT bucket_key, name_en, name_hi, sort_order FROM nidaan_buckets "
                         "WHERE active=1 ORDER BY sort_order"):
            out["buckets"][b["bucket_key"]] = b
            out["bucket_order"].append(b["bucket_key"])
        out["audit"] = await q(
            "SELECT actor_id, action, target_type, target_id FROM nidaan_audit_log "
            "WHERE actor_type='staff' AND created_at>=? AND created_at<?", (start_utc, end_utc))
        out["moves"] = await _mv.between(start_utc, end_utc)
        # Notes are the record of a call or a conversation; the timeline holds the reminders and
        # calls a person logged. Both are work the audit log does not see.
        out["notes"] = await q("SELECT staff_id, claim_id FROM nidaan_claim_notes "
                               "WHERE created_at>=? AND created_at<?", (start_utc, end_utc))
        out["acts"] = await q("SELECT actor, claim_id, kind FROM nidaan_claim_activity "
                              "WHERE created_at>=? AND created_at<? AND kind IN ('doc_reminder','doc_call','doc_sorted')",
                              (start_utc, end_utc))
        # A gist save that CHANGED something leaves a 'gist' remark; one that changed nothing
        # does not. The audit row is written either way - so only these count as work.
        out["gist_changed"] = {(int(r["claim_id"]), (r["actor"] or "").split(" (as ")[0].strip().lower())
                               for r in await q("SELECT DISTINCT claim_id, actor FROM nidaan_claim_activity "
                                                "WHERE kind='gist' AND created_at>=? AND created_at<?",
                                                (start_utc, end_utc)) if r.get("claim_id")}
        # Yesterday too - "updated today and again tomorrow" is a two-day pattern.
        y0 = (datetime.strptime(start_utc, "%Y-%m-%d %H:%M:%S") - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        out["audit_prev"] = await q(
            "SELECT actor_id, action, target_type, target_id FROM nidaan_audit_log "
            "WHERE actor_type='staff' AND created_at>=? AND created_at<?", (y0, start_utc))
        out["moves_prev"] = await _mv.between(y0, start_utc)
        out["status_flips"] = await q(
            "SELECT claim_id, from_status, to_status, changed_by_id, changed_at FROM nidaan_claim_status_log "
            "WHERE changed_by_type='staff' AND changed_at>=? AND changed_at<? ORDER BY changed_at",
            (y0, end_utc))
        out["test_claims"] = {r["claim_id"] for r in await q(
            "SELECT claim_id FROM nidaan_claims WHERE UPPER(COALESCE(insured_name,'')||' '||"
            "COALESCE(complainant_name,'')) LIKE '%TEST%'")}
        ids = {int(a["target_id"]) for a in out["audit"]
               if a.get("target_type") == "claim" and str(a.get("target_id") or "").isdigit()}
        ids |= {int(m["claim_id"]) for m in out["moves"]}
        ids |= {int(n["claim_id"]) for n in out["notes"] if n.get("claim_id")}
        ids |= {int(a["claim_id"]) for a in out["acts"] if a.get("claim_id")}
        if ids:
            ph = ",".join("?" * len(ids))
            for r in await q("SELECT claim_id, COALESCE(pipeline_stage,'') st, "
                             "COALESCE(review_outcome,'') ro FROM nidaan_claims "
                             "WHERE claim_id IN (%s)" % ph, tuple(ids)):
                out["claims"][r["claim_id"]] = r
        for r in await q(
                "SELECT COALESCE(pipeline_stage,'') st, COUNT(*) n FROM nidaan_claims "
                "WHERE COALESCE(archived,0)=0 AND COALESCE(status,'') NOT IN (%s) "
                "AND COALESCE(pipeline_stage,'')<>'' GROUP BY 1" % ",".join("?" * len(_CLOSED)),
                _CLOSED):
            out["snapshot"][r["st"]] = r["n"]
        r = await q("SELECT COUNT(*) n FROM nidaan_claims WHERE COALESCE(archived,0)=0 "
                    "AND COALESCE(status,'') NOT IN (%s) AND review_outcome='can_fight' "
                    "AND COALESCE(pipeline_stage,'')='' AND l2_handover_at IS NULL"
                    % ",".join("?" * len(_CLOSED)), _CLOSED)
        out["snapshot"][L2_WAITING] = r[0]["n"] if r else 0
        r = await q("SELECT COUNT(*) n FROM nidaan_claims WHERE created_at>=? AND created_at<?",
                    (start_utc, end_utc))
        out["claims_new"] = r[0]["n"] if r else 0
        r = await q("SELECT COUNT(*) n, COALESCE(SUM(total_paise),0) p FROM nidaan_payments "
                    "WHERE created_at>=? AND created_at<? AND status!='refunded'", (start_utc, end_utc))
        if r:
            out["payments_n"], out["payments_rs"] = r[0]["n"], (r[0]["p"] or 0) / 100.0
        for r in await q("SELECT assigned_to_staff_id s, COUNT(*) n FROM nidaan_quick_tasks "
                         "WHERE completed_at>=? AND completed_at<? AND deleted_at IS NULL GROUP BY 1",
                         (start_utc, end_utc)):
            out["tasks_done"][r["s"]] = r["n"]
        for r in await q("SELECT assigned_to_staff_id s, COUNT(*) n FROM nidaan_quick_tasks "
                         "WHERE status NOT IN ('done','cancelled') AND deleted_at IS NULL "
                         "AND due_date IS NOT NULL AND due_date<? GROUP BY 1", (today_ist,)):
            out["tasks_over"][r["s"]] = r["n"]
        out["overdue_tasks"] = sum(out["tasks_over"].values())
        r = await q("SELECT COUNT(*) n FROM nidaan_claims WHERE review_outcome='can_fight' "
                    "AND COALESCE(assigned_to_staff_id,0)=0 AND COALESCE(archived,0)=0 "
                    "AND COALESCE(status,'') NOT IN (%s)" % ",".join("?" * len(_CLOSED)), _CLOSED)
        out["l2_unassigned"] = r[0]["n"] if r else 0
    return out


def _place(day: dict, claim_id: int) -> str:
    c = day["claims"].get(claim_id) or {}
    if c.get("st"):
        return c["st"]
    return L2_WAITING if c.get("ro") == "can_fight" else INTAKE


def _bname(day: dict, key: str, lang: str) -> str:
    t = T[lang]
    if key == L2_WAITING:
        return t["l2"]
    if key == INTAKE:
        return t["intake"]
    b = day["buckets"].get(key) or {}
    if lang == "hi" and b.get("name_hi"):
        return b["name_hi"]
    return b.get("name_en") or key


def per_person(day: dict) -> dict:
    """{staff_id: {claim_ids, claims: {place: [ids]}, moves, per_claim: {id: {...}}, actions}}"""
    people: dict = {}
    by_name = {(st.get("name") or "").strip().lower(): st["staff_id"] for st in day.get("staff", [])}

    def p(sid):
        return people.setdefault(int(sid), {"claims": {}, "claim_ids": set(), "moves": [],
                                            "actions": {}, "per_claim": {}, "empty_saves": 0})

    def on(me, cid, action):
        pc = me["per_claim"].setdefault(int(cid), {"moves": [], "acts": {}})
        pc["acts"][action] = pc["acts"].get(action, 0) + 1
        me["actions"][action] = me["actions"].get(action, 0) + 1
        me["claim_ids"].add(int(cid))

    names_by_id = {st["staff_id"]: (st.get("name") or "").strip().lower() for st in day.get("staff", [])}
    for a in day["audit"]:
        if not a.get("actor_id") or a["action"] in _MOVE_ACTIONS:
            continue
        me = p(a["actor_id"])
        if a["action"] == "claim.gist" and str(a.get("target_id") or "").isdigit() and \
                (int(a["target_id"]), names_by_id.get(a["actor_id"], "")) not in day.get("gist_changed", set()):
            me["empty_saves"] = me.get("empty_saves", 0) + 1     # saved, changed nothing
            continue
        if a.get("target_type") == "claim" and str(a.get("target_id") or "").isdigit():
            on(me, int(a["target_id"]), a["action"])
        else:
            me["actions"][a["action"]] = me["actions"].get(a["action"], 0) + 1
    for n in day.get("notes", []):
        if n.get("staff_id") and n.get("claim_id"):
            on(p(n["staff_id"]), n["claim_id"], "note")
    for a in day.get("acts", []):
        actor = (a.get("actor") or "").split(" (as ")[0].strip().lower()
        sid = by_name.get(actor)
        if sid and a.get("claim_id"):
            on(p(sid), a["claim_id"], a["kind"])
    for m in day["moves"]:
        if m.get("staff_id"):
            me = p(m["staff_id"])
            me["moves"].append(m)
            me["claim_ids"].add(int(m["claim_id"]))
            me["per_claim"].setdefault(int(m["claim_id"]), {"moves": [], "acts": {}})["moves"].append(m)
    for sid, me in people.items():
        for cid in sorted(me["claim_ids"]):
            me["claims"].setdefault(_place(day, cid), []).append(cid)
    return people


def tally(me: dict) -> dict:
    """How many claims had each kind of work. A claim with only housekeeping is 'other'."""
    t = {k: 0 for k in KINDS}
    for cid in me["claim_ids"]:
        pc = me["per_claim"].get(cid) or {"moves": [], "acts": {}}
        kinds = {kind_of(a) for a in pc["acts"]}
        if pc["moves"]:
            kinds.add("progress")
        real = kinds - {"other"}
        for k in real:
            t[k] += 1
        if not real:
            t["other"] += 1
    return t


def tally_text(t: dict, lang: str) -> str:
    w = KIND_WORDS[lang]
    return " · ".join("%s %d" % (w[k], t[k]) for k in KINDS if t[k])


def claim_line(day: dict, cid: int, pc: dict, lang: str) -> str:
    """'NP-212: Live Cases → Pending Draft · documents uploaded 3 · claim-page links sent 1'"""
    li, bits = _LI[lang], []
    for m in pc.get("moves", []):
        bits.append("%s → %s" % (_bname(day, m["from_key"], lang), _bname(day, m["to_key"], lang)))
    acts = pc.get("acts", {})
    for k in ("progress", "follow", "docs", "notes", "other"):
        for a, n in sorted(acts.items(), key=lambda x: -x[1]):
            if kind_of(a) != k or a not in ACTIONS:
                continue
            bits.append("%s %d" % (ACTIONS[a][li], n) if n > 1 else ACTIONS[a][li])
    unknown = sum(n for a, n in acts.items() if a not in ACTIONS)
    if unknown:
        bits.append("%s %d" % (T[lang]["other"], unknown))
    return "NP-%d: %s" % (cid, " · ".join(bits) if bits else "—")


def _order(day: dict, keys) -> list:
    rank = {k: i for i, k in enumerate([INTAKE, L2_WAITING] + day["bucket_order"])}
    return sorted(keys, key=lambda k: rank.get(k, 999))


def _where(day: dict, claims: dict, lang: str, with_ids: bool = True) -> str:
    bits = []
    for k in _order(day, claims):
        ids = claims[k]
        s = "%s %d" % (_bname(day, k, lang), len(ids))
        if with_ids:
            shown = ", ".join("NP-%d" % i for i in ids[:6]) + (" …" if len(ids) > 6 else "")
            s += " (%s)" % shown
        bits.append(s)
    return "; ".join(bits)


def _move_pairs(day: dict, moves: list, lang: str) -> list:
    pairs: dict = {}
    for m in moves:
        k = (m["from_key"], m["to_key"])
        pairs[k] = pairs.get(k, 0) + 1
    return ["%s → %s: %d" % (_bname(day, a, lang), _bname(day, b, lang), n)
            for (a, b), n in sorted(pairs.items(), key=lambda x: -x[1])]


def _actions_text(actions: dict, lang: str) -> str:
    li, bits, other = _LI[lang], [], 0
    for act, n in sorted(actions.items(), key=lambda x: -x[1]):
        if act in ACTIONS:
            bits.append("%s %d" % (ACTIONS[act][li], n))
        else:
            other += n
    if other:
        bits.append("%s %d" % (T[lang]["other"], other))
    return " · ".join(bits)


# ── blockers and "worth a look" (founder, 2 Oct) ──────────────────────────────
async def blockers(limit: int = 12) -> dict:
    """Open claims that are stuck on US, worst first, each with who owns it - or NOBODY."""
    try:
        import biz_nidaan_case_state as _cs
        b = await _cs.board(limit=1000)
    except Exception as e:  # noqa: BLE001
        logger.info("summary blockers skipped: %s", e)
        return {"items": [], "by_flag": {}, "unowned": 0}
    ids = [it["claim_id"] for it in b["items"]]
    extra: dict = {}
    if ids:
        async with aiosqlite.connect(DB_PATH) as c:
            ph = ",".join("?" * len(ids))
            try:
                for cid, sid in await (await c.execute(
                        "SELECT claim_id, staff_id FROM nidaan_claim_assignees WHERE claim_id IN (%s)" % ph,
                        ids)).fetchall():
                    extra.setdefault(cid, set()).add(sid)
            except Exception:  # noqa: BLE001
                pass
    stuck = []
    for it in b["items"]:
        if it.get("blocker") not in ("none", "internal") or not it.get("flags"):
            continue
        owners = set(extra.get(it["claim_id"], set()))
        if it.get("assigned_to"):
            owners.add(it["assigned_to"])
        stuck.append({"claim_id": it["claim_id"], "who": it.get("who", ""), "stage": it.get("stage", ""),
                      "flags": it["flags"], "age": it.get("age_days") or 0, "owners": owners})
    stuck.sort(key=lambda x: (bool(x["owners"]), -x["age"]))     # nobody's first, then the oldest
    flags: dict = {}
    for s in stuck:
        for f in s["flags"]:
            flags[f] = flags.get(f, 0) + 1
    return {"items": stuck[:limit], "total": len(stuck), "by_flag": flags,
            "unowned": sum(1 for s in stuck if not s["owners"])}


def padding(day: dict, people: dict) -> dict:
    """{staff_id: [reasons]} - patterns that make a count bigger without moving a claim: saves
    that changed nothing, the same claim re-touched today and yesterday with no progress,
    a claim moved there and back, a status flipped and flipped back. Never super-admins, never
    test claims. It says 'worth a look', not 'guilty' - a person decides."""
    roles = {s["staff_id"]: s.get("role") for s in day.get("staff", [])}
    tests = day.get("test_claims", set())
    out: dict = {}

    def add(sid, why):
        if sid and roles.get(sid) and roles.get(sid) != "super_admin":
            out.setdefault(sid, []).append(why)

    for sid, me in people.items():
        if me.get("empty_saves", 0) >= 3:
            add(sid, "%d saves that changed nothing" % me["empty_saves"])
    prev: dict = {}
    for a in day.get("audit_prev", []):
        if a.get("target_type") == "claim" and str(a.get("target_id") or "").isdigit():
            prev.setdefault(a.get("actor_id"), {}).setdefault(int(a["target_id"]), set()).add(a["action"])
    for sid, me in people.items():
        again = []
        for cid in me["claim_ids"]:
            if cid in tests:
                continue
            pc = me["per_claim"].get(cid) or {}
            today_kinds = {kind_of(x) for x in (pc.get("acts") or {})}
            y = prev.get(sid, {}).get(cid)
            if y and not pc.get("moves") and today_kinds <= {"other"} and {kind_of(x) for x in y} <= {"other"}:
                again.append(cid)
        if len(again) >= 3:
            add(sid, "%d claims edited yesterday and again today with no progress (%s)"
                % (len(again), ", ".join("NP-%d" % c for c in sorted(again)[:5])))
    seen: dict = {}
    for m in list(day.get("moves_prev", [])) + list(day.get("moves", [])):
        key = (m.get("staff_id"), m["claim_id"])
        if m["claim_id"] in tests:
            continue
        last = seen.get(key)
        if last and last["from_key"] == m["to_key"] and last["to_key"] == m["from_key"]:
            add(m.get("staff_id"), "NP-%d moved %s and straight back" % (m["claim_id"], m["from_key"]))
        seen[key] = m
    flips: dict = {}
    for r in day.get("status_flips", []):
        key = (r.get("changed_by_id"), r["claim_id"])
        last = flips.get(key)
        if last and last["from_status"] == r["to_status"] and r["claim_id"] not in tests:
            add(r.get("changed_by_id"), "NP-%d status changed and changed back" % r["claim_id"])
        flips[key] = r
    return out


# ── writing it ───────────────────────────────────────────────────────────────
def own_text(day: dict, me: dict, staff_id: int, lang: str, date_label: str,
             head: bool = True) -> str:
    t = T[lang]
    lines = [t["own_head"].format(d=date_label)] if head else [t["your_part"]]
    if me["claim_ids"]:
        lines.append(t["you_worked"].format(n=len(me["claim_ids"])) + " " + tally_text(tally(me), lang))
        shown = 0
        for k in _order(day, me["claims"]):
            ids = me["claims"][k]
            lines.append("")
            lines.append("*%s* (%d)" % (_bname(day, k, lang), len(ids)))
            for cid in ids:
                if shown >= 25:
                    break
                lines.append("• " + claim_line(day, cid, me["per_claim"].get(cid) or {}, lang))
                shown += 1
        if len(me["claim_ids"]) > shown:
            lines.append("… +%d" % (len(me["claim_ids"]) - shown))
    done, over = day["tasks_done"].get(staff_id, 0), day["tasks_over"].get(staff_id, 0)
    if done or over:
        lines += ["", t["tasks"].format(done=done, over=over)]
    if head:
        lines += ["", t["thanks"]]
    return "\n".join(lines)


def own_voice(day: dict, me: dict, staff_id: int, lang: str) -> str:
    t, w = T[lang], KIND_WORDS[lang]
    tl = tally(me)
    parts = ", ".join("%s %d" % (w[k], tl[k]) for k in KINDS if tl[k] and k != "other")
    done = day["tasks_done"].get(staff_id, 0)
    tasks = t["v_tasks"].format(n=done) if done else ""
    return t["v_own"].format(n=len(me["claim_ids"]), where=(": " + parts) if parts else "",
                             moved="", tasks=tasks)


def team_text(day: dict, people: dict, names: dict, lang: str, date_label: str) -> str:
    t = T[lang]
    lines = [t["team_head"].format(d=date_label)]
    head = t["new_claims"].format(n=day["claims_new"])
    if day["payments_n"]:
        head += " · " + t["payments"].format(n=day["payments_n"], amt=_inr(day["payments_rs"]))
    lines += [head, "", t["where_now"]]
    came, went = {}, {}
    for m in day["moves"]:
        came[m["to_key"]] = came.get(m["to_key"], 0) + 1
        went[m["from_key"]] = went.get(m["from_key"], 0) + 1
    for k in [L2_WAITING] + day["bucket_order"]:
        n = day["snapshot"].get(k, 0)
        if n or came.get(k) or went.get(k):
            lines.append("• %s: %d (+%d / −%d)" % (_bname(day, k, lang), n, came.get(k, 0),
                                                    went.get(k, 0)))
    lines.append("")
    if day["moves"]:
        lines.append(t["moves_head"].format(n=len(day["moves"])))
        by: dict = {}
        for m in day["moves"]:
            by.setdefault(m.get("staff_id") or 0, []).append(m)
        for sid, ms in sorted(by.items(), key=lambda x: -len(x[1])):
            who = names.get(sid) or (ms[0].get("actor") or "system")
            lines.append("• " + t["moved_n"].format(name=who, n=len(ms),
                                                    what="; ".join(_move_pairs(day, ms, lang))))
    else:
        lines.append(t["moves_none"])
    worked = [(sid, me) for sid, me in people.items() if me["claim_ids"] and sid in names]
    if worked:
        lines += ["", t["who_head"]]
        for sid, me in sorted(worked, key=lambda x: -len(x[1]["claim_ids"])):
            lines.append("• " + t["worked"].format(name=names[sid], n=len(me["claim_ids"]),
                                                   where=tally_text(tally(me), lang))
                         + " — " + _where(day, me["claims"], lang, False))
    idle = [names[s["staff_id"]] for s in day["staff"]
            if s["staff_id"] not in people and s["staff_id"] not in day["on_leave"]]
    if idle:
        lines += ["", t["idle"].format(names=", ".join(idle))]
    leave = [names[s] for s in day["on_leave"] if s in names]
    if leave:
        lines.append(t["leave"].format(names=", ".join(leave)))
    if day["overdue_tasks"] or day["l2_unassigned"]:
        lines += ["", t["pend"].format(o=day["overdue_tasks"], u=day["l2_unassigned"])]
    # BLOCKERS: stuck on us, who owns each - and the ones nobody owns, first (founder, 2 Oct).
    bl = day.get("blockers") or {}
    if bl.get("items"):
        import biz_nidaan_case_state as _cs
        lines += ["", t["blk_head"].format(n=bl.get("total", 0), u=bl.get("unowned", 0))]
        for s in bl["items"]:
            own = ", ".join(names.get(o, "?") for o in s["owners"]) if s["owners"] else t["nobody"]
            why = "; ".join(_cs.FLAG_LABEL.get(f, f) for f in s["flags"][:2])
            lines.append("• NP-%d %s — %s — %s: %s" % (s["claim_id"], s["who"][:24], why,
                                                    t["owner"], own))
        if bl.get("by_flag"):
            import biz_nidaan_case_state as _cs2
            top = sorted(bl["by_flag"].items(), key=lambda x: -x[1])[:3]
            lines.append(t["focus"].format(what="; ".join("%s %d" % (_cs2.FLAG_LABEL.get(f, f), n) for f, n in top)))
    # WORTH A LOOK: counts that grew without a claim moving (never super-admins, never tests).
    pad = day.get("padding") or {}
    if pad:
        lines += ["", t["pad_head"]]
        for sid, why in pad.items():
            if sid in names:
                lines.append("• %s — %s" % (names[sid], "; ".join(why)))
    return "\n".join(lines)


def team_voice(day: dict, people: dict, names: dict, lang: str) -> str:
    t = T[lang]
    pay = (t["v_pay"].format(n=day["payments_n"], amt=_inr(day["payments_rs"]))
           if day["payments_n"] else "")
    who = "".join(t["v_who"].format(name=names[sid], n=len(me["claim_ids"]))
                  .rstrip(". ").rstrip("।") + " (" + tally_text(tally(me), lang).replace(" · ", ", ") + "). "
                  for sid, me in sorted(people.items(), key=lambda x: -len(x[1]["claim_ids"]))
                  if me["claim_ids"] and sid in names)
    return t["v_team"].format(new=day["claims_new"], pay=pay, moves=len(day["moves"]), who=who)


# ── voice ────────────────────────────────────────────────────────────────────
def _wav_to_ogg(wav: bytes) -> "bytes | None":
    """Convert WAV → Opus/OGG via ffmpeg for a Telegram voice note. None on any failure."""
    wp = op = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav); wp = f.name
        op = wp[:-4] + ".ogg"
        subprocess.run(["ffmpeg", "-y", "-i", wp, "-c:a", "libopus", "-b:a", "32k", op],
                       check=True, capture_output=True, timeout=90)
        with open(op, "rb") as f:
            return f.read()
    except Exception as e:  # noqa: BLE001
        logger.info("daily_summary wav->ogg failed: %s", e); return None
    finally:
        for p in (wp, op):
            try:
                if p and os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass


def _split_message(text: str, n: int = 3900) -> list:
    """Telegram takes 4,096 characters a message: split at line ends, keep every line."""
    out, cur = [], ""
    for line in (text or "").split("\n"):
        while len(line) > n:
            out.append(line[:n]); line = line[n:]
        if len(cur) + 1 + len(line) > n:
            out.append(cur); cur = line
        else:
            cur = (cur + "\n" + line) if cur else line
    if cur:
        out.append(cur)
    return out


async def _voice_bytes(text: str) -> "bytes | None":
    """The voice note. biz_tts reads money as rupees (biz_speakable) - never dollars."""
    if os.getenv("NIDAAN_NO_OUTBOUND") == "1":
        return None
    try:
        import biz_tts
        # The WHOLE summary, not a short script and not cut at 1,500 characters (founder, 2 Oct).
        wav = await biz_tts.long_wav(text, voice="Kore")
        return _wav_to_ogg(wav) if wav else None
    except Exception as e:  # noqa: BLE001
        logger.info("daily_summary tts failed: %s", e); return None


# ── sending ──────────────────────────────────────────────────────────────────
async def build(now_ist: datetime | None = None) -> dict:
    """Everything that would be sent, without sending it - also what the tests read."""
    now_ist = now_ist or datetime.now(IST)
    start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    fmt = "%Y-%m-%d %H:%M:%S"
    day = await gather(start_ist.astimezone(timezone.utc).strftime(fmt),
                       (now_ist + timedelta(seconds=1)).astimezone(timezone.utc).strftime(fmt),
                       now_ist.strftime("%Y-%m-%d"))
    date_label = now_ist.strftime("%d %b %Y")
    people = per_person(day)
    day["blockers"] = await blockers()
    day["padding"] = padding(day, people)
    names = {s["staff_id"]: s["name"] for s in day["staff"]}
    admins = ("super_admin",)   # the team view is for super-admins; everyone else gets their own day
    out = []
    for s in day["staff"]:
        sid, lang = s["staff_id"], _lang(s["lang"])
        if sid in day["on_leave"]:
            continue
        me = people.get(sid)
        if s["role"] in admins:
            text = team_text(day, people, names, lang, date_label)
            if me:
                text += "\n\n" + own_text(day, me, sid, lang, date_label, head=False)
            out.append({"staff_id": sid, "name": s["name"], "chat": s["chat"], "lang": lang,
                        "kind": "team", "text": text, "voice": text})
        elif me:
            own = own_text(day, me, sid, lang, date_label)
            out.append({"staff_id": sid, "name": s["name"], "chat": s["chat"], "lang": lang,
                        "kind": "own", "text": own, "voice": own})
    return {"date": date_label, "messages": out, "moves": len(day["moves"])}


async def run_daily_ops_summary(force: bool = False) -> dict:
    """Send tonight's summaries on Telegram - text and a voice note each. Once a day."""
    import biz_nidaan as _n
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if not force:
        try:
            if str(await _n.get_ops_setting("daily_summary_enabled", "1")).strip().lower() \
                    not in ("1", "true", "on", "yes"):
                return {"ok": False, "error": "disabled"}
            if str(await _n.get_ops_setting(LAST_KEY, "") or "") == today:
                return {"ok": True, "skipped": "already sent today"}
        except Exception:
            pass
    plan = await build()
    import biz_nidaan_telegram as _tg
    sent = voiced = 0
    for m in plan["messages"]:
        if not m["chat"]:
            continue
        try:
            # The whole text: several messages when it is long, never cut off.
            ok = True
            for part in _split_message(m["text"]):
                ok = (await _tg.send_message(str(m["chat"]), part))[0] and ok
            if ok:
                sent += 1
                v = await _voice_bytes(m["voice"])
                if v and (await _tg.send_voice(str(m["chat"]), v))[0]:
                    voiced += 1
        except Exception as e:  # noqa: BLE001
            logger.info("daily summary to %s failed: %s", m.get("name"), e)
    if not force:
        try:
            await _n.set_ops_setting(LAST_KEY, today)
        except Exception:
            pass
    logger.info("🌙 Daily summaries: %d sent, %d with voice", sent, voiced)
    return {"ok": True, "sent": sent, "voiced": voiced,
            "team": sum(1 for m in plan["messages"] if m["kind"] == "team"),
            "own": sum(1 for m in plan["messages"] if m["kind"] == "own")}
