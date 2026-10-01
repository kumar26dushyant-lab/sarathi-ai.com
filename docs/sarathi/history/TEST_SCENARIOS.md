# ═══════════════════════════════════════════════════════════════════
#  SARATHI-AI — END-TO-END TEST SCENARIOS
#  Complete test cases for Solo Advisor & Team plans
#  Use these dummy details to test signup → bot → CRM → payments
# ═══════════════════════════════════════════════════════════════════


## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
##  PART A — SOLO ADVISOR PLAN (₹199/mo) — 5 SCENARIOS
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### SCENARIO S1: Solo — Life Insurance Advisor (Mumbai)
─────────────────────────────────────────────────────
**SIGNUP DETAILS:**
- Firm Name:        Sharma Financial Services
- Owner Name:       Vikram Sharma
- Phone:            9876543210
- Email:            vikram.sharma@testmail.com
- City:             Mumbai
- IRDAI License:    IRDAI/AGT/2024/001234
- Plan:             individual (Solo Advisor ₹199/mo)

**TEST LEADS (add via /addlead):**
| # | Name             | Phone       | DOB        | Anniversary | City    | Need Type       | Notes                           |
|---|------------------|-------------|------------|-------------|---------|-----------------|----------------------------------|
| 1 | Rajesh Kumar     | 9811223344  | 1985-03-15 | 2012-11-20  | Mumbai  | Term Life       | Works at TCS, family of 4        |
| 2 | Priya Mehta      | 8877665544  | 1990-07-22 | -           | Thane   | Health Insurance| Single, IT professional          |
| 3 | Anil Deshmukh    | 7766554433  | 1978-12-01 | 2005-06-10  | Pune    | ULIP            | Existing LIC policy, wants MF    |
| 4 | Sunita Joshi     | 9988776655  | 1982-09-08 | 2008-02-14  | Mumbai  | Retirement Plan | Govt employee, pension concern   |
| 5 | Rohan Patil      | 8899001122  | 1995-01-30 | -           | Navi Mumbai | Motor + Health | Bought new car, no health cover |

**END-TO-END TEST FLOW:**
1. Web Signup → Go to homepage → Pricing → Click "Start Free Trial" for Solo plan
2. Fill signup form with above details → Get deep link → Open in Telegram
3. /start → Register firm → Enter name, phone, email
4. /addlead → Add all 5 leads above one by one
5. /leads → Verify all 5 appear
6. /lead 1 → View Rajesh Kumar's full detail
7. /pipeline → Should show 5 Prospects
8. /followup → Log a "📞 Call" for Rajesh Kumar
9. /convert 1 → Move Rajesh to "Contacted"
10. /calc → Run Inflation calculator (₹50K, 7%, 15 years)
11. Share calculator result via WhatsApp (test wa.me link flow)
12. /policy 1 → Record policy: LIC Jeevan Anand, ₹50L cover, ₹18,000 premium, start today, renewal +1 year
13. /renewals → Should show Rajesh's policy
14. /dashboard → Verify pipeline stats (4 Prospect, 0 Contacted, 1 Won)
15. /editlead 2 → Change Priya's city to "Mumbai"
16. /claim → Start claim for Rajesh → Health claim → Check document checklist
17. /claims → View the claim
18. /ai → Should show "upgrade to Team plan" message (Solo blocks AI)
19. /lang → Switch to Hindi → Verify Hindi messages → Switch back
20. /settings → Edit profile → Change email
21. /plans → View subscription status, trial days remaining

**PAYMENT TEST (after trial):**
- Razorpay Test Mode Card: 4111 1111 1111 1111 (any expiry, any CVV)
- Razorpay Test UPI: success@razorpay
- Amount: ₹199 (Solo plan monthly)
- Verify: After payment, /plans shows "Active" status

---

### SCENARIO S2: Solo — Health Insurance Specialist (Delhi)
──────────────────────────────────────────────────────────
**SIGNUP DETAILS:**
- Firm Name:        HealthFirst Advisory
- Owner Name:       Neha Gupta
- Phone:            9123456789
- Email:            neha.gupta@testmail.com
- City:             New Delhi
- IRDAI License:    IRDAI/AGT/2024/005678
- Plan:             individual

**TEST LEADS:**
| # | Name             | Phone       | DOB        | City      | Need Type        | Notes                        |
|---|------------------|-------------|------------|-----------|------------------|------------------------------|
| 1 | Manoj Tiwari     | 9334455667  | 1975-06-12 | Delhi     | Health Insurance  | Diabetes, family of 5        |
| 2 | Kavita Reddy     | 8445566778  | 1988-11-03 | Gurgaon   | Health + Term     | Pregnant, needs maternity     |
| 3 | Deepak Verma     | 7556677889  | 1969-04-25 | Noida     | Super Top-up     | Has ₹5L base, needs more    |
| 4 | Ritu Singh       | 9667788990  | 1992-02-18 | Delhi     | Personal Accident | Rides motorcycle daily       |
| 5 | Suresh Khanna    | 8778899001  | 1965-08-30 | Faridabad | Health + Critical | Senior citizen, heart patient |

**KEY TEST ACTIONS:**
1. Signup + Bot registration
2. /addlead → Add all 5, test duplicate detection by re-adding Manoj's phone
3. /calc → Run Health Cover Estimator for all leads
4. /wacalc 1 → Send health calculator report to Manoj via WhatsApp
5. /greet 2 → Send Birthday greeting to Kavita (set DOB to today for test)
6. /followup → Log meetings for Deepak and Ritu
7. /convert → Move Kavita to "Pitched", Manoj to "Proposal Sent"
8. /pipeline → Verify mixed stages
9. /policy 1 → Star Health Family plan, ₹10L, ₹14,200/yr
10. Voice test → Record: "Met Suresh uncle at Faridabad, heart patient, needs critical illness cover, budget 20000, follow up Thursday"
11. /claims → No claims yet (empty state)
12. CSV import → Create a CSV with 3 extra leads, upload to bot

---

### SCENARIO S3: Solo — Motor Insurance Agent (Bangalore)
─────────────────────────────────────────────────────────
**SIGNUP DETAILS:**
- Firm Name:        AutoShield Insurance
- Owner Name:       Karthik Nair
- Phone:            9234567890
- Email:            karthik.nair@testmail.com
- City:             Bangalore
- IRDAI License:    IRDAI/AGT/2024/009012
- Plan:             individual

**TEST LEADS:**
| # | Name            | Phone       | DOB        | City       | Need Type    | Notes                         |
|---|-----------------|-------------|------------|------------|--------------|-------------------------------|
| 1 | Ravi Hegde      | 9112233445  | 1986-05-20 | Bangalore  | Motor        | New Hyundai Creta, comp cover |
| 2 | Meena Shetty    | 8223344556  | 1991-10-14 | Mysore     | Motor + Health | Two-wheeler + family health  |
| 3 | Prasad Rao      | 7334455667  | 1980-01-07 | Bangalore  | Commercial   | Fleet of 5 delivery vans     |
| 4 | Shalini Das     | 9445566778  | 1993-08-28 | Mangalore  | Motor        | Used car, third-party only   |
| 5 | Vinay Kumar     | 8556677889  | 1972-03-16 | Hubli      | Motor + Term  | Truck driver, high risk      |

**KEY TEST ACTIONS:**
1. Full signup + onboarding flow
2. Add all leads, test /leads search with "Shetty"
3. /calc → Run EMI calculator: ₹45,000 premium, 12 months, 18% GST
4. /claim → Motor claim for Ravi: accident, enter vehicle details
5. /claimstatus → Check document checklist (FIR, RC, DL, photos)
6. /convert through full pipeline: Prospect → Contacted → Pitched → Won
7. Test /wa 1 → Send WhatsApp message: "Hi Ravi, your motor insurance renewal is due next month. Shall I get you best quotes?"
8. /renewals → Test with a policy expiring in 5 days (set renewal date accordingly)
9. /dashboard → Verify all stats
10. /help → Check command list matches Solo plan features

---

### SCENARIO S4: Solo — Investment + Insurance Advisor (Pune)
────────────────────────────────────────────────────────────
**SIGNUP DETAILS:**
- Firm Name:        WealthGuard Advisors
- Owner Name:       Amit Kulkarni
- Phone:            9345678901
- Email:            amit.kulkarni@testmail.com
- City:             Pune
- IRDAI License:    IRDAI/AGT/2024/003456
- Plan:             individual

**TEST LEADS:**
| # | Name             | Phone       | DOB        | City  | Need Type        | Notes                          |
|---|------------------|-------------|------------|-------|------------------|--------------------------------|
| 1 | Sachin Tendulkar | 9001122334  | 1973-04-24 | Pune  | ULIP + MF SIP    | Wants to compare both          |
| 2 | Anita Pawar      | 8112233445  | 1985-12-10 | Pune  | NPS + Retirement  | Govt teacher, retire at 60     |
| 3 | Nitin Gadkari    | 7223344556  | 1968-07-15 | Pune  | Term + Health    | BusinessOwner, high NW          |
| 4 | Pooja Bhatt      | 9334455667  | 1990-05-02 | Pune  | SIP              | Young professional, ₹10K SIP  |
| 5 | Mahesh Babu      | 8445566778  | 1979-11-22 | Pune  | Child Plan + ULIP | 2 kids, edu planning          |

**KEY TEST ACTIONS:**
1. Signup + bot registration
2. Add all leads
3. /calc → Test ALL 9 calculators one by one:
   - Inflation: ₹30K, 6%, 20 years
   - HLV: ₹50K expense, ₹10L loan, 2 children, ₹25L existing cover
   - Retirement: age 35, retire 60, life 85, ₹40K expense, 7% inflation, 12%/8% returns
   - EMI: ₹36,000 premium, 12 months, 18% GST, 0.5% CIBIL discount
   - Health: age 40, family 4, Tier 1, ₹15L income, ₹5L existing
   - SIP vs Lumpsum: ₹50,000, 10 years, 12%
   - MF SIP: ₹1 Cr goal, 15 years, 12%, ₹5L existing
   - ULIP vs MF: ₹1L/yr, 15 years, 8% ULIP, 12% MF
   - NPS: ₹5000/mo, age 35, retire 60, 10%, 30% bracket
4. Share ULIP vs MF result to lead #1 via WhatsApp
5. /wacalc 2 → NPS report to Anita
6. /policy → Record 2 policies for different leads
7. Test multiple /convert stages in sequence
8. /editlead → Update lead notes after meetings

---

### SCENARIO S5: Solo — Fresh Agent (Jaipur) — Empty State Test
──────────────────────────────────────────────────────────────
**SIGNUP DETAILS:**
- Firm Name:        Rajasthan Insurance Hub
- Owner Name:       Prateek Agarwal
- Phone:            9456789012
- Email:            prateek.agarwal@testmail.com
- City:             Jaipur
- IRDAI License:    (leave empty — optional field)
- Plan:             individual

**TEST LEADS:** None initially — test empty states

**KEY TEST ACTIONS (Empty State Testing):**
1. Signup + registration
2. /leads → Should show "No leads yet" message
3. /pipeline → Should show empty pipeline
4. /dashboard → All zeros
5. /renewals → "No upcoming renewals"
6. /claims → "No claims yet"
7. /followup → Should prompt to add a lead first
8. /addlead → Add 1 lead: Manish Jain, 9567890123, Jaipur, Term Life
9. /leads → Now shows 1 lead
10. /lead 1 → View detail
11. Exercise /cancel mid-wizard (start /addlead, type name, then /cancel)
12. Test /help → Verify all commands shown correctly
13. Test /lang → Switch to Hindi → /help in Hindi → /lang back to English
14. /plans → Check trial countdown
15. Try re-signup with same phone → Should get "already exists" error


## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
##  PART B — TEAM PLAN (₹799/mo) — 5 SCENARIOS
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### SCENARIO T1: Team — Multi-Agent Insurance Firm (Hyderabad)
──────────────────────────────────────────────────────────────
**SIGNUP DETAILS (Owner):**
- Firm Name:        Deccan Insurance Brokers
- Owner Name:       Srinivas Reddy
- Phone:            9567890123
- Email:            srinivas@deccaninsurance.test
- City:             Hyderabad
- IRDAI License:    IRDAI/BRK/2024/HYD001
- Plan:             team

**AGENTS TO INVITE (via Settings → Team → Generate Invite):**
| # | Agent Name       | Phone       | Role  | City        |
|---|------------------|-------------|-------|-------------|
| 1 | Lakshmi Devi     | 9678901234  | agent | Hyderabad   |
| 2 | Raju Naidu       | 8789012345  | agent | Secunderabad|
| 3 | Fatima Begum     | 7890123456  | agent | Warangal    |

**TEST LEADS (split across agents):**

*Owner (Srinivas) leads:*
| Name             | Phone       | Need Type       |
|------------------|-------------|-----------------|
| Krishna Murthy   | 9111222333  | Term + Health   |
| Padma Rani       | 8222333444  | Child Plan      |

*Agent Lakshmi's leads:*
| Name             | Phone       | Need Type       |
|------------------|-------------|-----------------|
| Venkat Rao       | 7333444555  | Health          |
| Swathi Kumari    | 9444555666  | Motor           |

*Agent Raju's leads:*
| Name             | Phone       | Need Type       |
|------------------|-------------|-----------------|
| Suresh Babu      | 8555666777  | ULIP            |
| Mahesh Chary     | 7666777888  | Retirement      |

**END-TO-END TEST FLOW:**
1. Owner signup on web → Plan = team → Get deep link
2. /start in Telegram → Register as owner
3. /settings → Team → Generate Invite Code → Copy code
4. Agent Lakshmi: open bot → /start → "I have Invite Code" → enters code → registers
5. Agent Raju: same invite code → registers
6. Agent Fatima: same invite code → registers (tests multi-use code)
7. Owner: /team → Verify all 3 agents listed with roles
8. Each agent: /addlead → Add their respective leads
9. Owner: /pipeline → sees ONLY owner's leads
10. **AI TOOLS (Team plan unlocked):**
    - /ai → Lead Scoring → Score Krishna Murthy
    - /ai → Pitch Generator → Generate pitch for Padma Rani
    - /ai → Objection Handler → "Insurance is too expensive"
    - /ai → Communication Templates → Introduction template
    - /ai → Ask AI → "What's the difference between term and whole life?"
11. Owner: /team → Deactivate Fatima → Verify Fatima can't use bot
12. Owner: /team → Reactivate Fatima → Verify access restored
13. Owner: /team → Transfer Fatima's data to Raju (if Fatima leaves)
14. /greet → Send birthday greeting to Krishna Murthy
15. /wacalc 1 → Send HLV calculator to Krishna Murthy on WhatsApp
16. /wadash 1 → Send portfolio summary (after recording a policy)

**PAYMENT TEST:**
- Test Card: 4111 1111 1111 1111, Expiry: 12/28, CVV: 123
- Test UPI: success@razorpay
- Amount: ₹799/mo (Team plan)

---

### SCENARIO T2: Team — Family Business Firm (Chennai)
─────────────────────────────────────────────────────
**SIGNUP DETAILS (Owner):**
- Firm Name:        Tamil Nadu Insurance Solutions
- Owner Name:       Murugan Pillai
- Phone:            9678901234
- Email:            murugan@tamilnaduinsurance.test
- City:             Chennai
- IRDAI License:    IRDAI/BRK/2024/CHN001
- Plan:             team

**AGENTS:**
| # | Agent Name       | Phone       | Relation     |
|---|------------------|-------------|--------------|
| 1 | Lakshmi Pillai   | 8789012345  | Wife         |
| 2 | Karthik Pillai   | 7890123456  | Son          |

**TEST LEADS (15 total, distributed):**

*Owner Murugan (5 leads):*
| Name              | Phone       | Need Type       |
|-------------------|-------------|-----------------|
| Anand Krishnan    | 9201122334  | Term Life       |
| Bala Subramaniam  | 8312233445  | Health          |
| Chitra Devi       | 7423344556  | Retirement      |
| Durai Raj         | 9534455667  | Motor           |
| Ezhil Arasan      | 8645566778  | ULIP + NPS      |

*Agent Lakshmi (5 leads):*
| Name              | Phone       | Need Type       |
|-------------------|-------------|-----------------|
| Fathima Bee       | 7756677889  | Health + Maternity|
| Ganesh Iyer       | 9867788990  | Child Plan      |
| Hema Malini       | 8978899001  | Term Life       |
| Indira Gandhi     | 7089900112  | Super Top-up    |
| Jayanthi Raman    | 9190011223  | Personal Accident|

*Agent Karthik (5 leads):*
| Name              | Phone       | Need Type       |
|-------------------|-------------|-----------------|
| Karthik Subbu     | 8201122334  | SIP + MF        |
| Lalitha Priya     | 7312233445  | NPS             |
| Mohan Das         | 9423344556  | Motor           |
| Nandini Srinivas  | 8534455667  | Health          |
| Omkar Prasad      | 7645566778  | Retirement      |

**KEY TEST ACTIONS:**
1. Full signup + invite + 2 agents join
2. All 3 add 5 leads each → Total 15 leads across firm
3. Owner exercises /team → Verifies all agents + lead counts
4. Each agent moves leads through pipeline independently
5. /ai tools on various leads:
   - AI Lead Scoring (batch all) → Check A/B/C/D grades
   - AI Smart Follow-up for top leads
   - AI Policy Recommender → Gap analysis
   - AI Renewal Intelligence (after adding policies)
6. Record policies for 5 different leads → /renewals shows them
7. File 2 claims: one Health, one Motor → Track through statuses
8. /calc → Run calculator → /wacalc → send to client → verify WhatsApp flow
9. Voice-to-action: record voice note for new lead in Tamil-accented English
10. CSV import: upload 10 more leads via CSV file
11. Hindi mode: /lang → switch Murugan to Hindi → test all commands in Hindi

---

### SCENARIO T3: Team — Corporate Insurance Broker (Delhi NCR)
─────────────────────────────────────────────────────────────
**SIGNUP DETAILS (Owner):**
- Firm Name:        National Insurance Advisors Pvt Ltd
- Owner Name:       Rajiv Malhotra
- Phone:            9789012345
- Email:            rajiv@nationalinsurance.test
- City:             New Delhi
- IRDAI License:    IRDAI/BRK/2024/DEL005
- Plan:             team

**AGENTS:**
| # | Agent Name       | Phone       | Specialty        |
|---|------------------|-------------|------------------|
| 1 | Sneha Kapoor     | 8890123456  | Health specialist |
| 2 | Arjun Singh      | 7901234567  | Life specialist   |
| 3 | Pooja Verma      | 9012345678  | Motor specialist  |
| 4 | Danish Khan      | 8123456789  | Investments       |

**KEY TEST ACTIONS (Stress-Test Team Features):**
1. Signup → Invite all 4 agents
2. Each agent adds 5 leads → 25 leads total + owner's 5 = 30 leads
3. **Capacity test:** Try adding agent #5 → should get "team full" error (max 5 total for Team plan)
4. Owner: /team → View all agents, lead counts, policy counts
5. **Deactivation flow:** Deactivate Danish → transfer his leads to Arjun → verify data moved
6. AI batch scoring: Owner runs AI Lead Scoring → "Score All" → verify all owner's leads scored
7. /pipeline → Each agent sees ONLY their own pipeline (data isolation check)
8. Owner creates 3 claims → Tests all claim types (Health, Term, Motor)
9. Each agent runs different calculators and shares via WhatsApp
10. Test /help from each role → Owner sees /team, agents don't

---

### SCENARIO T4: Team — Rural Insurance Advisor (Hindi-First)
─────────────────────────────────────────────────────────────
**SIGNUP DETAILS (Owner):**
- Firm Name:        Bharat Bima Seva Kendra
- Owner Name:       Ramesh Yadav
- Phone:            9890123456
- Email:            ramesh.yadav@testmail.com
- City:             Lucknow
- IRDAI License:    IRDAI/AGT/2024/LKO007
- Plan:             team

**AGENTS:**
| # | Agent Name       | Phone       | City      |
|---|------------------|-------------|-----------|
| 1 | Sunil Yadav      | 8901234567  | Varanasi  |
| 2 | Geeta Devi       | 7012345678  | Kanpur    |

**KEY TEST ACTIONS (Hindi-First Experience):**
1. Signup → /start → Immediately /lang → Switch to Hindi
2. All subsequent testing in Hindi interface
3. Add leads with Hindi names:
   | Name              | Phone       | Need Type    |
   |-------------------|-------------|--------------|
   | राजेश कुमार        | 9101122334  | Term Life    |
   | सुनीता देवी        | 8212233445  | Health       |
   | मनोज तिवारी       | 7323344556  | Motor        |
   | प्रेम चंद          | 9434455667  | Retirement   |
   | कमला देवी         | 8545566778  | Child Plan   |
4. Voice-to-action in Hindi: "आज मनोज तिवारी से मिला, लखनऊ में रहते हैं, फोन 73233-44556, हेल्थ इंश्योरेंस चाहिए, फैमिली 6 लोगों की, बजट 12000, अगले सोमवार फॉलो अप"
5. AI tools in Hindi context:
   - /ai → Pitch Generator → Should generate Hindi-friendly pitch
   - /ai → Objection → "बीमा बहुत महंगा है"
6. /calc in Hindi → Run calculator → Share via WhatsApp
7. Invite Agent Sunil → he joins → /lang → Hindi → adds his leads
8. Test all menus and buttons appear in Hindi
9. Switch back to English mid-session → Everything toggles correctly

---

### SCENARIO T5: Team — Upgrade Journey (Trial → Solo → Team)
─────────────────────────────────────────────────────────────
**SIGNUP DETAILS (Start as Solo, upgrade to Team):**
- Firm Name:        Growth Insurance Partners
- Owner Name:       Akash Mehta
- Phone:            9901234567
- Email:            akash.mehta@testmail.com
- City:             Ahmedabad
- IRDAI License:    IRDAI/AGT/2024/AHM010
- Plan:             individual (start as Solo)

**KEY TEST ACTIONS (Plan Upgrade Journey):**
1. **Phase 1 — Free Trial (14 days):**
   - Signup as Solo plan → Get 14-day trial
   - /plans → Shows "Trial: 14 days remaining"
   - Add 5 leads, run calculators, manage pipeline
   - /ai → Blocked ("Upgrade to Team plan")
   - /team → Not available on Solo

2. **Phase 2 — Pay for Solo (₹199/mo):**
   - /plans → Click "Subscribe" → Razorpay checkout
   - Pay with test card: 4111 1111 1111 1111, Exp: 12/28, CVV: 123
   - Or test UPI: success@razorpay
   - /plans → Now shows "Solo Advisor — Active"
   - /ai → Still blocked (Solo doesn't include AI)

3. **Phase 3 — Upgrade to Team (₹799/mo):**
   - Go to web dashboard → Change plan → Team
   - Or /plans → Select Team plan → Pay difference
   - Pay with test card
   - /plans → Shows "Team — Active"
   - /ai → NOW UNLOCKED! Test all AI tools
   - /settings → Team → Generate invite code
   - Invite 2 agents → They join

4. **Phase 4 — Test Team Features:**
   - /team → See 2 agents
   - /ai → Lead Scoring, Pitch Generator, etc.
   - Agents add leads, manage pipeline independently
   - Test data isolation (agents can't see each other's leads)

5. **Phase 5 — Test Expiry (if possible):**
   - Manually set subscription to expired (admin/DB)
   - Try any command → Should get "subscription expired" message
   - /plans → Should offer renewal option


## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
##  PART C — PAYMENT TEST DETAILS (Razorpay Test Mode)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Test Cards (Razorpay Test Mode)
| Card Type   | Number              | Expiry  | CVV  | Result    |
|-------------|---------------------|---------|------|-----------|
| Visa        | 4111 1111 1111 1111 | 12/28   | 123  | ✅ Success |
| Mastercard  | 5267 3181 8797 5449 | 12/28   | 123  | ✅ Success |
| Visa (fail) | 4000 0000 0000 0002 | 12/28   | 123  | ❌ Decline |

### Test UPI IDs (Razorpay Test Mode)
| UPI ID              | Result    |
|---------------------|-----------|
| success@razorpay    | ✅ Success |
| failure@razorpay    | ❌ Failure |

### Test Net Banking
- Bank: Any test bank
- Username: doesn't matter in test mode
- Password: doesn't matter in test mode
- OTP: Any 6 digits (e.g., 123456)

### Plan Pricing
| Plan           | Monthly  | Plan Key     |
|----------------|----------|--------------|
| Solo Advisor   | ₹199     | individual   |
| Team           | ₹799     | team         |
| Enterprise     | ₹1,999   | enterprise   |

### Razorpay Test Mode Checklist
- [ ] Razorpay dashboard → Settings → API Keys → Generate Test Keys
- [ ] Set in biz.env: RAZORPAY_KEY_ID=rzp_test_xxxxx
- [ ] Set in biz.env: RAZORPAY_KEY_SECRET=xxxxx
- [ ] All payments in test mode appear in Razorpay dashboard under "Test Transactions"
- [ ] Switch to Live keys only after ALL test scenarios pass


## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
##  PART D — WHATSAPP INTERACTION TEST FLOWS
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Flow 1: Calculator → WhatsApp Share (Click-to-Send Link)
1. Advisor: /calc → Inflation → Complete calculation
2. Advisor: Tap "📱 Share WhatsApp" → Enter client phone: 9811223344
3. Bot generates wa.me link with pre-filled message
4. Advisor: Click link → WhatsApp opens → Send to client
5. Client (Rajesh) sees: "Dear Rajesh, here's your Inflation Impact analysis from Sharma Financial Services..."

### Flow 2: Direct WhatsApp API Message
1. (Requires WhatsApp API configured)
2. Advisor: /wa 1 Hello Rajesh! Your policy renewal is coming up. Can we discuss?
3. Bot sends via API → Rajesh receives on WhatsApp
4. Bot confirms: "✅ WhatsApp message sent to Rajesh Kumar"
5. Interaction logged automatically

### Flow 3: Calculator Report via WhatsApp API
1. Advisor: /wacalc 1 → Select "🛡️ HLV"
2. Bot runs HLV calculator with Rajesh's profile data
3. Sends personalized report to 9811223344 via WhatsApp API
4. Rajesh sees branded professional report on WhatsApp

### Flow 4: Portfolio Summary via WhatsApp
1. (After recording policies for a lead)
2. Advisor: /wadash 1
3. Bot compiles all of Rajesh's policies into formatted summary
4. Sends to WhatsApp: "Your Insurance Portfolio — 2 Active Policies..."

### Flow 5: Automated Greeting
1. Advisor: /greet 1
2. Select: 🎂 Birthday
3. Bot sends: "🎂 Happy Birthday Rajesh! Wishing you health, happiness, and prosperity. — Vikram Sharma, Sharma Financial Services"
4. Client sees branded greeting on WhatsApp


## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
##  PART E — EDGE CASE / NEGATIVE TESTS
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **Duplicate phone signup:** Try signing up with same phone twice → Should reject
2. **Duplicate email signup:** Try signing up with same email twice → Should reject
3. **Invalid phone format:** Enter 5-digit phone during signup → Should validate and reject
4. **Expired trial access:** After 14 days, try any command → Should show "trial expired" + upgrade prompt
5. **Solo plan AI access:** /ai on Solo plan → Should show upgrade message, not crash
6. **Team capacity overflow:** Add 6th agent on Team plan (max 5) → Should reject with "team full"
7. **Empty lead search:** /leads xyznonexistent → Should show "no leads found"
8. **Cancel mid-wizard:** Start /addlead → type name → /cancel → Should cancel cleanly
9. **Double /start:** Type /start when already registered → Should NOT re-register, just show menu
10. **Invalid lead ID:** /lead 99999 → Should show "lead not found"
11. **Voice too long:** Record 3+ minute voice note → Should warn "max 2 minutes"
12. **Rate limiting:** Send 31+ commands in 60 seconds → Should get rate-limited
13. **Large CSV:** Upload CSV with 501+ rows → Should warn "max 500"
14. **Wrong invite code:** /start → Invite Code → enter "WRONGCODE" → Should reject
15. **Cross-agent data:** Agent A tries to view Agent B's lead → Should be blocked


## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
##  TESTING CHECKLIST (copy & tick off)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Registration & Auth
- [ ] Web signup (Solo plan)
- [ ] Web signup (Team plan)
- [ ] Telegram bot /start → Register firm
- [ ] Telegram bot /start → Join via invite code
- [ ] OTP login on web (send + verify)
- [ ] Duplicate phone blocked
- [ ] Duplicate email blocked

### Lead Management
- [ ] /addlead → Full wizard flow
- [ ] /leads → List all
- [ ] /leads <search> → Search by name
- [ ] /leads <phone> → Search by phone
- [ ] /lead <id> → Full detail
- [ ] /editlead <id> → Edit each field
- [ ] Duplicate phone detection in addlead
- [ ] CSV bulk import (upload .csv file)

### Pipeline & Follow-ups
- [ ] /pipeline → Visual overview
- [ ] /convert <id> → Move through all stages
- [ ] /followup → Log all interaction types
- [ ] /dashboard → All stats correct
- [ ] Follow-up reminders arrive on scheduled date

### Policies & Renewals
- [ ] /policy <id> → Record full policy
- [ ] /renewals → Shows correct urgency colors
- [ ] Policy auto-marks lead as "Closed Won"

### Calculators
- [ ] /calc → All 9 calculators work
- [ ] Quick-select buttons work correctly
- [ ] Custom value input works
- [ ] Recalculate works
- [ ] Share WhatsApp (wa.me link) works

### WhatsApp Integration
- [ ] /wa <id> <msg> → Direct message sent
- [ ] /wacalc <id> → Calculator report sent
- [ ] /wadash <id> → Portfolio summary sent
- [ ] /greet <id> → Birthday/Anniversary greeting sent
- [ ] Calculator "Share WhatsApp" button generates link

### Claims
- [ ] /claim → Full wizard (Health type)
- [ ] /claim → Motor claim type
- [ ] /claims → List view
- [ ] /claimstatus <id> → Document checklist

### AI Tools (Team+ only)
- [ ] /ai → Menu appears (Team plan)
- [ ] /ai → Blocked (Solo plan)
- [ ] Lead Scoring (single + batch)
- [ ] Pitch Generator → WhatsApp copy
- [ ] Smart Follow-up suggestions
- [ ] Policy Recommender / Gap analysis
- [ ] Communication Templates (all 12 types)
- [ ] Objection Handler (preset + custom)
- [ ] Renewal Intelligence
- [ ] Ask AI Anything

### Voice-to-Action
- [ ] Record voice note → AI extracts entities
- [ ] Confirm → Lead created + follow-up set
- [ ] Discard → Data cleared
- [ ] Hindi voice recognition
- [ ] Hinglish (mixed) recognition

### Team Management (Team+ only)
- [ ] /settings → Team → Generate invite code
- [ ] Agent joins via invite code
- [ ] /team → List all agents
- [ ] Deactivate agent → Verified blocked
- [ ] Reactivate agent → Verified restored
- [ ] Transfer data between agents
- [ ] Agent capacity enforced (max 5 Team, max 25 Enterprise)

### Settings & Language
- [ ] /settings → All options work
- [ ] /editprofile → Edit name, phone, email
- [ ] /lang → Switch to Hindi
- [ ] /lang → Switch back to English
- [ ] /help → Correct commands for plan/role
- [ ] /plans → Shows current status

### Payments (Razorpay Test Mode)
- [ ] Create order → Razorpay checkout loads
- [ ] Pay with test card → Success
- [ ] Pay with test UPI → Success
- [ ] Verify payment signature
- [ ] Subscription activated after payment
- [ ] /plans shows "Active" after payment
- [ ] Test failed payment → Handled gracefully

### Edge Cases
- [ ] /cancel during any wizard
- [ ] 30-minute conversation timeout
- [ ] Rate limiting (31+ commands/minute)
- [ ] Invalid lead IDs
- [ ] Voice note > 2 minutes
- [ ] CSV > 500 rows
- [ ] Cross-agent data isolation
