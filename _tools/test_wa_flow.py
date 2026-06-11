"""Unit test for biz_nidaan_wa_flow — the WhatsApp onboarding decision logic.

Pure logic, no DB. Run on the server:
  cd /opt/sarathi && PYTHONPATH=/opt/sarathi /opt/sarathi/venv/bin/python /tmp/test_wa_flow.py
"""
import biz_nidaan_wa_flow as f

passed = failed = 0


def check(name, got, want):
    global passed, failed
    ok = got == want
    passed += ok
    failed += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got!r} want={want!r}")


def check_true(name, got):
    check(name, bool(got), True)


def check_contains(name, hay, needle):
    global passed, failed
    ok = needle in (hay or "")
    passed += ok
    failed += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {'contains' if ok else 'MISSING'} {needle!r}")


# ── parse_language_choice ──
check("parse '1'", f.parse_language_choice("1"), "en")
check("parse '2'", f.parse_language_choice("2"), "hi")
check("parse '3'", f.parse_language_choice("3"), "mr")
check("parse '2.'", f.parse_language_choice("2."), "hi")
check("parse 'english'", f.parse_language_choice("english"), "en")
check("parse 'हिंदी'", f.parse_language_choice("हिंदी"), "hi")
check("parse 'मराठी'", f.parse_language_choice("मराठी"), "mr")
check("parse 'Marathi'", f.parse_language_choice("Marathi"), "mr")
check("parse 'hello' -> None", f.parse_language_choice("hello"), None)
check("parse '' -> None", f.parse_language_choice(""), None)

# ── change-language command ──
check_true("change 'change language'", f.is_change_language_command("change language"))
check_true("change 'change the language'", f.is_change_language_command("Change the Language"))
check_true("change 'भाषा बदला'", f.is_change_language_command("भाषा बदला"))
check_true("change 'भाषा बदलें'", f.is_change_language_command("भाषा बदलें"))
check("change 'hello' -> False", f.is_change_language_command("hello"), False)

# ── consent yes/stop ──
check_true("yes 'YES'", f.is_consent_yes("YES"))
check_true("yes 'haan'", f.is_consent_yes("haan"))
check_true("yes 'हाँ'", f.is_consent_yes("हाँ"))
check_true("stop 'STOP'", f.is_consent_stop("STOP"))
check_true("stop 'नको'", f.is_consent_stop("नको"))
check("yes 'maybe' -> False", f.is_consent_yes("maybe"), False)

# ── consent rendering names advisor + firm ──
c = f.render_consent("en", "Rahul Verma", "Verma Insurance")
check_contains("consent has advisor", c, "Rahul Verma")
check_contains("consent has firm", c, "Verma Insurance")
c_hi = f.render_consent("hi", "Rahul Verma", "Verma Insurance")
check_contains("consent hi has who", c_hi, "Rahul Verma, Verma Insurance")
c_only_firm = f.render_consent("en", "", "Verma Insurance")
check_contains("consent firm-only", c_only_firm, "Verma Insurance")

# ── welcome is trilingual ──
w = f.render_welcome()
check_contains("welcome has English", w, "English")
check_contains("welcome has हिंदी", w, "हिंदी")
check_contains("welcome has मराठी", w, "मराठी")
check_contains("welcome asks to save", w, "SAVE this number")
check_contains("welcome has verify line", w, "nidaanpartner.com")

# ── decide_onboarding_action ──
print("  --- decision: new contact, junk text ---")
r = f.decide_onboarding_action(has_lang=False, lang=None, opted_in=False,
                               is_advisor_managed=False, inbound_text="hi there")
check("new+junk -> send_welcome", r["action"], f.ACT_SEND_WELCOME)

print("  --- decision: new self-service contact picks English ---")
r = f.decide_onboarding_action(has_lang=False, lang=None, opted_in=False,
                               is_advisor_managed=False, inbound_text="1")
check("self-serve pick en -> set_lang", r["action"], f.ACT_SET_LANG)
check("self-serve lang=en", r["lang"], "en")
check("self-serve no consent needed", r["needs_consent_next"], False)

print("  --- decision: new advisor-managed customer picks Hindi ---")
r = f.decide_onboarding_action(has_lang=False, lang=None, opted_in=False,
                               is_advisor_managed=True, inbound_text="2",
                               advisor_name="Rahul Verma", firm_name="Verma Insurance")
check("adv-managed pick hi -> set_lang", r["action"], f.ACT_SET_LANG)
check("adv-managed lang=hi", r["lang"], "hi")
check("adv-managed needs consent", r["needs_consent_next"], True)
check_contains("adv-managed ack includes consent w/ advisor", r["message"], "Rahul Verma")

print("  --- decision: change language anytime ---")
r = f.decide_onboarding_action(has_lang=True, lang="en", opted_in=True,
                               is_advisor_managed=False, inbound_text="change language")
check("change-lang -> resend_picker", r["action"], f.ACT_RESEND_PICKER)

print("  --- decision: advisor-managed, lang set, replies YES ---")
r = f.decide_onboarding_action(has_lang=True, lang="hi", opted_in=False,
                               is_advisor_managed=True, inbound_text="YES")
check("consent yes -> set_consent_yes", r["action"], f.ACT_SET_CONSENT_YES)

print("  --- decision: advisor-managed, lang set, replies STOP ---")
r = f.decide_onboarding_action(has_lang=True, lang="hi", opted_in=False,
                               is_advisor_managed=True, inbound_text="STOP")
check("consent stop -> set_consent_stop", r["action"], f.ACT_SET_CONSENT_STOP)

print("  --- decision: advisor-managed, lang set, junk -> re-ask consent ---")
r = f.decide_onboarding_action(has_lang=True, lang="hi", opted_in=False,
                               is_advisor_managed=True, inbound_text="what is this",
                               advisor_name="A", firm_name="F")
check("consent junk -> send_consent", r["action"], f.ACT_SEND_CONSENT)

print("  --- decision: fully onboarded self-service -> proceed ---")
r = f.decide_onboarding_action(has_lang=True, lang="en", opted_in=True,
                               is_advisor_managed=False, inbound_text="here is my doc")
check("onboarded -> proceed", r["action"], f.ACT_PROCEED)

print("  --- decision: advisor-managed but already opted in -> proceed ---")
r = f.decide_onboarding_action(has_lang=True, lang="hi", opted_in=True,
                               is_advisor_managed=True, inbound_text="hello")
check("adv-managed opted-in -> proceed", r["action"], f.ACT_PROCEED)

print(f"\n{'='*52}\n  {passed} passed, {failed} failed\n{'='*52}")
raise SystemExit(1 if failed else 0)
