# Sarathi-AI — Human Tester Guide
**Date:** May 14, 2026  
**App URL:** https://sarathi-ai.com  
**Role needed:** Owner (to access all features including Test Automation)

---

## Step 1 — How to Log In

1. Open **https://sarathi-ai.com** in your browser
2. Click **"Login"** in the top-right corner
3. Enter your **10-digit mobile number** (the number registered as owner)
4. Click **"Send OTP"** — you'll receive a 6-digit code via SMS or WhatsApp
5. Enter the OTP and click **"Verify"**
6. You land on the **Dashboard** automatically

> If you don't have a registered account, click **"Start Free Trial"** on the home page and complete signup first.

---

## Step 2 — Dashboard Overview

After login, you see a **left sidebar** with all the navigation tabs. Here is what each tab does and how to test it.

---

## Feature 1 — Overview Tab
**Navigate:** Sidebar → 📊 Overview

**What it shows:**
- Total leads, policies, renewals due, tasks pending
- Quick summary cards at a glance

**Test:**
1. Log in → you land here automatically
2. Verify counts are not zero (should reflect your actual data)
3. Scroll down to see all summary cards

---

## Feature 2 — Leads (Client List)
**Navigate:** Sidebar → 👥 Leads

**What it shows:** Your complete list of clients/prospects

**Test — Add a Lead:**
1. Click **"+ Add Lead"** (top right of the page)
2. Fill: Name = `Test Client`, Phone = `9999900000`, Date of Birth = any past date
3. Click **Save**
4. Verify the new lead appears in the list

**Test — WhatsApp a Lead:**
1. Find any lead in the list
2. Click the green **"💬 WhatsApp"** pill button next to their name
3. A success toast should appear: *"WhatsApp message sent ✓"*
4. Check if the lead's WhatsApp received the message

**Test — Search a Lead:**
1. Type a name in the search box at the top
2. List should filter instantly

**Test — Edit a Lead:**
1. Click any lead's name to open their profile
2. Edit a field and save
3. Verify changes are saved

---

## Feature 3 — Policies
**Navigate:** Sidebar → 📄 Policies

**What it shows:** All insurance policies linked to your clients

**Test — Add a Policy:**
1. Click **"+ Add Policy"**
2. Fill: Client = pick from dropdown, Policy No = `TEST-001`, Premium = `5000`, Renewal Date = next month's date
3. Click **Save**
4. Verify it appears in the list

**Test — Renewal Alert:**
- Policies with renewal dates within 30 days will appear highlighted
- Add a policy with today's date + 10 days and confirm it shows as "Due Soon"

---

## Feature 4 — Tasks
**Navigate:** Sidebar → 📋 Tasks

**What it shows:** Your to-do list / follow-up reminders

**Test — Add a Task:**
1. Click **"+ New Task"**
2. Fill: Title = `Call Test Client`, Due date = today, Priority = High
3. Save
4. Verify it appears in the task list

**Test — Complete a Task:**
1. Find a task and click the checkbox or "Mark Done"
2. Task should move to completed or disappear from pending list

---

## Feature 5 — AI Tools
**Navigate:** Sidebar → 🤖 AI Tools

**What it shows:** AI-powered tools for advisors

**Test — AI Nudge:**
1. Select a lead from the dropdown
2. Click **"Generate Nudge"** or similar button
3. An AI-written message should appear within a few seconds
4. You can copy it and send manually

**Test — Objection Handler:**
1. Type a client objection (e.g. "Premium is too high")
2. Click **"Get Response"**
3. AI should return a professional reply

---

## Feature 6 — Drip Sequences (Nurture)
**Navigate:** Sidebar → 🌱 Drip Sequences

**What it shows:** Automated message sequences for leads

**Test — Create a Drip:**
1. Click **"+ New Sequence"**
2. Give it a name, add 2–3 messages with delays (Day 1, Day 3, Day 7)
3. Save

**Test — Enroll a Lead:**
1. Open a lead's profile
2. Find the "Enroll in Drip" option and pick the sequence you just created
3. Confirm enrollment
4. The lead should now receive messages on schedule

---

## Feature 7 — Quote Compare
**Navigate:** Sidebar → 💰 Quote Compare

**What it shows:** Side-by-side insurance plan comparison tool

**Test:**
1. Fill in: Age = `35`, Cover = `1 Crore`, Gender = Male
2. Click **"Compare"**
3. A table with multiple insurer quotes should appear
4. Click **"Generate PDF"** or **"Share"** to send to client

---

## Feature 8 — Lapse Risk
**Navigate:** Sidebar → 🚨 Lapse Risk

**What it shows:** Clients at risk of policy lapse (missed premium)

**Test:**
1. Open this tab
2. You should see a list of clients with lapse risk scores
3. Click any client row to see the risk details and recommended action

---

## Feature 9 — WhatsApp
**Navigate:** Sidebar → 💬 WhatsApp

**What it shows:** WhatsApp connection status and messaging tools

**Test — Check Connection:**
1. Open this tab
2. Verify it shows **"Connected"** status for your WhatsApp number

**Test — Send a Direct Message:**
1. Find the "Direct Message" section
2. Enter a phone number and a message
3. Click **Send**
4. Verify the message is delivered on WhatsApp

**Test — Broadcast:**
1. Find the "Broadcast" section (if on Team plan)
2. Type a team broadcast message
3. Click **Send to Team**
4. All advisors in your team should receive it via Telegram/WhatsApp

---

## Feature 10 — Team (Owner Only)
**Navigate:** Sidebar → 👥 Team  
*(Only visible on Team/Enterprise plan)*

**What it shows:** Your advisor/agent team members

**Test — Add Team Member:**
1. Click **"+ Add Agent"**
2. Fill name, phone, email
3. They will receive an invite via WhatsApp/SMS

**Test — View Agent Activity:**
1. Click on any agent name
2. See their leads, tasks, and activity

---

## Feature 11 — Subscription
**Navigate:** Sidebar → 💎 Subscription  
*(Owner only)*

**What it shows:** Your current plan, billing, and upgrade options

**Test:**
1. Open this tab
2. Verify plan name and expiry date are correct
3. Do NOT click "Pay" unless you intend to upgrade

---

## Feature 12 — Profile & Settings
**Navigate:** Sidebar → 👤 Profile & Settings

**What it shows:** Your firm details, name, logo, notification preferences

**Test — Update Profile:**
1. Change your firm name or phone number
2. Click **Save**
3. Verify the sidebar updates with the new name

**Test — Language Switch:**
1. Find the language toggle (Hindi / English)
2. Switch to Hindi — entire dashboard should switch language
3. Switch back to English

---

## Feature 13 — My Microsite
**Navigate:** Sidebar → 🌐 My Microsite

**What it shows:** Your personal client-facing landing page

**Test:**
1. Open this tab
2. Click the **"Preview"** or **"View Live"** link
3. A public page opens — this is what your clients see when you share your link
4. Check your name, photo, and contact details are correct

---

## Feature 14 — Calculators
**Navigate:** Sidebar → 🧮 Calculators (opens a new page)

**Test:**
1. Click Calculators
2. Try the **Premium Calculator** — enter age and sum assured
3. Try the **SIP Calculator** or **HLV Calculator**
4. Results should appear instantly

---

## Feature 15 — Support
**Navigate:** Sidebar → 🎫 Support

**What it shows:** Raise and track support tickets

**Test — Raise a Ticket:**
1. Click **"🎫 New Ticket"**
2. Fill subject: `Test ticket`, category: General, priority: Low
3. Submit
4. Verify it appears in the ticket list with status "Open"

---

## Feature 16 — Test Automation Panel (Owner Only)
**Navigate:** Sidebar → 🧪 Test Automation

**Purpose:** Trigger automated background scans with one click to verify automation works — no console scripts needed.

**Test — Run each scan:**

| Button | What it tests | Expected result |
|---|---|---|
| 🎂 Birthday Scan | Finds clients with birthday today/tomorrow and sends greetings | Toast: "Birthday scan complete". Log shows count |
| 💍 Anniversary Scan | Finds clients with marriage anniversary today | Toast: "Anniversary scan complete" |
| 🔔 Renewal Scan | Finds policies due for renewal in next 30 days, notifies advisor | Toast: "Renewal scan complete" |
| 📋 Follow-up Scan | Finds overdue follow-ups and sends reminders to advisor | Toast: "Follow-up scan complete" |
| 🌱 Nurture Drip | Processes enrolled leads and sends their next drip message | Toast: "Nurture Drip scan complete" |

**Test — WhatsApp Direct Send Test:**
1. Enter your own phone number (10 digits)
2. Click **"📤 Send Test WA"**
3. You should receive a test WhatsApp message within 30 seconds

**Test — Broadcast to Team:**
1. Type a message in the broadcast box (or leave the default)
2. Click **"📢 Send Broadcast"**
3. All team advisors should receive it on Telegram

**Result Log:** After each test, the log area at the bottom shows the outcome in real time (green = success, red = failure).

---

## What to Check After Each Test

| Check | How |
|---|---|
| Toast notification appeared | Green banner at top of screen |
| Data saved correctly | Refresh the page and see if it persists |
| WhatsApp delivered | Check the recipient's WhatsApp |
| Telegram notification | Check the advisor's Telegram (if configured) |
| No error pages | Page should never go blank or show "500 error" |

---

## Test Accounts to Use

> Fill this in before sharing with tester:

| Role | Phone | Name |
|---|---|---|
| Owner | _(your registered phone)_ | _(your name)_ |
| Test Lead | 9999900000 | Test Client |
| Test Policy | Policy No: TEST-001 | Renewal: next month |

---

## Reporting Issues

When something doesn't work, note down:
1. Which tab you were on
2. What button you clicked
3. What you expected to happen
4. What actually happened (screenshot preferred)

Share via WhatsApp or Telegram to the owner.
