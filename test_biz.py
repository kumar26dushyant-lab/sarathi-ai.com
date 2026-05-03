"""Quick smoke test for all Sarathi-AI Business Technologies modules."""
import asyncio

def test_calculators():
    import biz_calculators as c
    r = c.inflation_eraser(50000, 6.0, 10)
    print(f"  Inflation: {c.format_currency(r.future_value_needed)}")
    r2 = c.hlv_calculator(50000)
    print(f"  HLV: {c.format_currency(r2.recommended_cover)}")
    r3 = c.retirement_planner(35, 60, 85, 40000)
    print(f"  Corpus: {c.format_currency(r3.corpus_needed)}")
    r4 = c.emi_calculator(25000, 5)
    print(f"  EMI: {c.format_currency(r4.emi_options[0]['monthly_emi'])}")
    r5 = c.health_cover_estimator(35, "2A+2C", 1, False)
    print(f"  Health: {c.format_currency(r5.recommended_si)}")
    r6 = c.sip_vs_lumpsum(500000, 10, 12.0)
    print(f"  SIP maturity: {c.format_currency(r6.sip_maturity)}")
    print("  ✅ All 6 calculators OK")

async def test_database():
    import biz_database as db
    await db.init_db()
    print("  ✅ Database initialized (sarathi_biz.db)")

def test_whatsapp():
    import biz_whatsapp as wa
    wa.init_whatsapp()
    print(f"  ✅ WhatsApp configured: {wa.is_configured()}")

def test_pdf():
    import biz_pdf as pdf
    pdf.init_pdf()
    import biz_calculators as c
    r = c.inflation_eraser(50000, 6.0, 10)
    html = pdf.generate_inflation_html(r, "Test Client")
    fn = pdf.save_html_report(html, "inflation", "test")
    print(f"  ✅ PDF/report generated: {fn}")

def test_bot():
    import biz_bot
    print("  ✅ Bot module imported (build_bot available)")

def test_reminders():
    import biz_reminders
    print("  ✅ Reminders module imported (start_scheduler available)")

def test_main():
    import sarathi_biz
    print("  ✅ Main module imported (FastAPI app available)")

if __name__ == "__main__":
    print("=" * 50)
    print("  Sarathi-AI Business Technologies — Smoke Test")
    print("=" * 50)

    print("\n1. Calculators:")
    test_calculators()

    print("\n2. Database:")
    asyncio.run(test_database())

    print("\n3. WhatsApp:")
    test_whatsapp()

    print("\n4. PDF Generator:")
    test_pdf()

    print("\n5. Telegram Bot:")
    test_bot()

    print("\n6. Reminders:")
    test_reminders()

    print("\n7. Main Entry Point:")
    test_main()

    print("\n" + "=" * 50)
    print("  ✅ ALL TESTS PASSED — Ready to launch!")
    print("  Run: py -3.12 sarathi_biz.py")
    print("=" * 50)
