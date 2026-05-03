
/* ═══════════════════════════════════════════════════════════
   SARATHI-AI ADMIN DASHBOARD
   ═══════════════════════════════════════════════════════════ */

let STATE = { tenant: null, plan: 'trial', features: {}, agents: [], pendingChange: null, role: localStorage.getItem('sarathi_role')||'owner' };
let _dlang = localStorage.getItem('sarathi_lang')||'en';
const _DT = {
  // Sidebar
  nav_overview:{en:'📊 Overview',hi:'📊 अवलोकन'},
  nav_leads:{en:'📋 Leads',hi:'📋 लीड्स'},
  nav_policies:{en:'📄 Policies',hi:'📄 पॉलिसियां'},
  nav_team:{en:'👥 Team',hi:'👥 टीम'},
  nav_subscription:{en:'💎 Subscription',hi:'💎 सदस्यता'},
  nav_profile:{en:'👤 Profile & Settings',hi:'👤 प्रोफ़ाइल और सेटिंग्स'},
  nav_support:{en:'🎫 Support',hi:'🎫 सहायता'},
  nav_calculators:{en:'🧮 Calculators',hi:'🧮 कैलकुलेटर'},
  nav_help:{en:'❓ Help',hi:'❓ मदद'},
  nav_affiliate:{en:'🤝 Affiliate Portal',hi:'🤝 एफिलिएट पोर्टल'},
  sidebar_crm:{en:'Financial CRM',hi:'वित्तीय CRM'},
  sidebar_dash:{en:'Advisor Dashboard',hi:'सलाहकार डैशबोर्ड'},
  free_trial:{en:'Free Trial',hi:'नि:शुल्क ट्रायल'},
  days_remaining:{en:'{0} days remaining',hi:'{0} दिन शेष'},
  logout:{en:'Logout',hi:'लॉगआउट'},
  // Tab titles
  tt_overview:{en:'📊 Overview',hi:'📊 अवलोकन'},
  tt_leads:{en:'📋 Lead Management',hi:'📋 लीड प्रबंधन'},
  tt_policies:{en:'📄 Policies',hi:'📄 पॉलिसियां'},
  tt_agents:{en:'👥 Team Management',hi:'👥 टीम प्रबंधन'},
  tt_subscription:{en:'💎 Subscription',hi:'💎 सदस्यता'},
  tt_profile:{en:'👤 Profile & Settings',hi:'👤 प्रोफ़ाइल और सेटिंग्स'},
  tt_support:{en:'🎫 Support',hi:'🎫 सहायता'},
  // Overview
  ov_pipeline:{en:'📊 Sales Pipeline',hi:'📊 सेल्स पाइपलाइन'},
  ov_followups:{en:'📞 Follow-ups Due',hi:'📞 फॉलो-अप बाकी'},
  ov_renewals:{en:'🔄 Upcoming Renewals',hi:'🔄 आगामी नवीनीकरण'},
  kpi_total_leads:{en:'Total Leads',hi:'कुल लीड्स'},
  kpi_todays_leads:{en:"Today's Leads",hi:'आज के लीड्स'},
  kpi_active_policies:{en:'Active Policies',hi:'सक्रिय पॉलिसियां'},
  kpi_total_premium:{en:'Total Premium',hi:'कुल प्रीमियम'},
  kpi_month_leads:{en:'Month Leads',hi:'महीने के लीड्स'},
  kpi_conversion:{en:'Conversion Rate',hi:'रूपांतरण दर'},
  kpi_agents:{en:'Agents',hi:'एजेंट'},
  stg_prospect:{en:'🎯 Prospect',hi:'🎯 संभावित'},
  stg_contacted:{en:'📞 Contacted',hi:'📞 संपर्क किया'},
  stg_pitched:{en:'📊 Pitched',hi:'📊 प्रस्तुति दी'},
  stg_proposal:{en:'📄 Proposal',hi:'📄 प्रस्ताव'},
  stg_negotiation:{en:'🤝 Negotiation',hi:'🤝 वार्ता'},
  stg_won:{en:'✅ Won',hi:'✅ जीता'},
  stg_lost:{en:'❌ Lost',hi:'❌ हारा'},
  no_followups:{en:'No follow-ups due!',hi:'कोई फॉलो-अप बाकी नहीं!'},
  followup:{en:'Follow-up',hi:'फॉलो-अप'},
  no_renewals:{en:'No upcoming renewals',hi:'कोई आगामी नवीनीकरण नहीं'},
  // Leads
  search_leads:{en:'Search leads...',hi:'लीड खोजें...'},
  all_stages:{en:'All Stages',hi:'सभी चरण'},
  stage_prospect:{en:'Prospect',hi:'संभावित'},
  stage_contacted:{en:'Contacted',hi:'संपर्क किया'},
  stage_pitched:{en:'Pitched',hi:'प्रस्तुति दी'},
  stage_proposal:{en:'Proposal Sent',hi:'प्रस्ताव भेजा'},
  stage_negotiation:{en:'Negotiation',hi:'वार्ता'},
  stage_won:{en:'Won',hi:'जीता'},
  stage_lost:{en:'Lost',hi:'हारा'},
  add_lead:{en:'+ Add Lead',hi:'+ लीड जोड़ें'},
  import_csv:{en:'📥 Import CSV',hi:'📥 CSV आयात'},
  th_name:{en:'Name',hi:'नाम'},
  th_phone:{en:'Phone',hi:'फ़ोन'},
  th_stage:{en:'Stage',hi:'चरण'},
  th_need:{en:'Need',hi:'आवश्यकता'},
  th_source:{en:'Source',hi:'स्रोत'},
  th_agent:{en:'Agent',hi:'एजेंट'},
  th_updated:{en:'Updated',hi:'अपडेट'},
  th_actions:{en:'Actions',hi:'कार्रवाई'},
  no_leads:{en:'No leads found. Add your first lead!',hi:'कोई लीड नहीं मिली। अपनी पहली लीड जोड़ें!'},
  showing:{en:'Showing {0} of {1} leads',hi:'{1} में से {0} लीड्स दिखा रहे हैं'},
  prev:{en:'← Prev',hi:'← पिछला'},
  next:{en:'Next →',hi:'अगला →'},
  // Policies
  all_status:{en:'All Status',hi:'सभी स्थिति'},
  status_active:{en:'Active',hi:'सक्रिय'},
  status_expired:{en:'Expired',hi:'समाप्त'},
  status_cancelled:{en:'Cancelled',hi:'रद्द'},
  add_policy:{en:'➕ Add Policy',hi:'➕ पॉलिसी जोड़ें'},
  th_client:{en:'Client',hi:'ग्राहक'},
  th_policy_no:{en:'Policy#',hi:'पॉलिसी#'},
  th_insurer:{en:'Insurer',hi:'बीमाकर्ता'},
  th_plan:{en:'Plan',hi:'प्लान'},
  th_type:{en:'Type',hi:'प्रकार'},
  th_premium:{en:'Premium',hi:'प्रीमियम'},
  th_renewal:{en:'Renewal',hi:'नवीनीकरण'},
  th_status:{en:'Status',hi:'स्थिति'},
  no_policies:{en:'No policies found',hi:'कोई पॉलिसी नहीं मिली'},
  // Team
  team_members:{en:'👥 Team Members',hi:'👥 टीम सदस्य'},
  gen_invite:{en:'📨 Generate Invite Code',hi:'📨 आमंत्रण कोड बनाएं'},
  invite_code:{en:'Invite Code:',hi:'आमंत्रण कोड:'},
  invite_valid:{en:'— Share with your team. Valid 7 days.',hi:'— अपनी टीम के साथ साझा करें। 7 दिन वैध।'},
  web_invite:{en:'🔗 Web invite:',hi:'🔗 वेब आमंत्रण:'},
  th_email:{en:'Email',hi:'ईमेल'},
  th_role:{en:'Role',hi:'भूमिका'},
  th_leads:{en:'Leads',hi:'लीड्स'},
  th_policies_col:{en:'Policies',hi:'पॉलिसियां'},
  agent_capacity:{en:'📊 Agent Capacity',hi:'📊 एजेंट क्षमता'},
  can_add_more:{en:'✅ Can add more',hi:'✅ और जोड़ सकते हैं'},
  limit_reached:{en:'⚠️ Limit reached',hi:'⚠️ सीमा पूरी'},
  // Subscription
  current_sub:{en:'📋 Current Subscription',hi:'📋 वर्तमान सदस्यता'},
  avail_plans:{en:'💎 Available Plans',hi:'💎 उपलब्ध प्लान'},
  plan_change_policy:{en:'ℹ️ Plan Change Policy',hi:'ℹ️ प्लान बदलने की नीति'},
  sub_plan:{en:'Plan',hi:'प्लान'},
  sub_status:{en:'Status',hi:'स्थिति'},
  sub_agents:{en:'Agents',hi:'एजेंट'},
  sub_features:{en:'Features',hi:'सुविधाएं'},
  sub_campaigns:{en:'Campaigns',hi:'अभियान'},
  sub_drive:{en:'Drive',hi:'ड्राइव'},
  sub_team:{en:'Team',hi:'टीम'},
  days_left:{en:'{0} days left',hi:'{0} दिन शेष'},
  renews_in:{en:'Renews in {0} days',hi:'{0} दिन में नवीनीकरण'},
  current_plan:{en:'Current Plan',hi:'वर्तमान प्लान'},
  scheduled:{en:'Scheduled',hi:'निर्धारित'},
  upgrade_now:{en:'Upgrade Now',hi:'अभी अपग्रेड करें'},
  schedule_downgrade:{en:'Schedule Downgrade',hi:'डाउनग्रेड शेड्यूल करें'},
  cancel_change:{en:'Cancel Change',hi:'बदलाव रद्द करें'},
  per_month:{en:'/month',hi:'/महीने'},
  plan_upgrade_q:{en:'Upgrade to {0}? You\'ll be directed to payment.',hi:'{0} में अपग्रेड करें? भुगतान पृष्ठ पर भेजा जाएगा।'},
  plan_downgrade_q:{en:'Schedule downgrade to {0}? Takes effect at next billing cycle.',hi:'{0} में डाउनग्रेड शेड्यूल करें? अगले बिलिंग साइकिल में लागू।'},
  cancel_change_q:{en:'Cancel the scheduled plan change?',hi:'निर्धारित प्लान बदलाव रद्द करें?'},
  upgrade_success:{en:'Upgrade successful! 🎉',hi:'अपग्रेड सफल! 🎉'},
  payment_failed:{en:'Payment verification failed. Contact support.',hi:'भुगतान सत्यापन विफल। सहायता से संपर्क करें।'},
  change_scheduled:{en:'Plan change scheduled!',hi:'प्लान बदलाव शेड्यूल हो गया!'},
  plan_trial:{en:'Free Trial',hi:'नि:शुल्क ट्रायल'},
  plan_solo:{en:'Solo Advisor',hi:'सोलो सलाहकार'},
  plan_team:{en:'Team',hi:'टीम'},
  plan_enterprise:{en:'Enterprise',hi:'एंटरप्राइज़'},
  trial_notice:{en:'Your free trial ends in {0} days. Subscribe to a plan to continue using all features.',hi:'आपका नि:शुल्क ट्रायल {0} दिन में समाप्त होगा। सभी सुविधाएं जारी रखने के लिए प्लान लें।'},
  subscribe_now:{en:'Subscribe Now',hi:'अभी सब्सक्राइब करें'},
  // Plan features
  pf_1advisor:{en:'1 Advisor',hi:'1 सलाहकार'},
  pf_unlimited_leads:{en:'Unlimited Leads',hi:'असीमित लीड्स'},
  pf_all_calc:{en:'All Calculators',hi:'सभी कैलकुलेटर'},
  pf_whatsapp:{en:'WhatsApp Integration',hi:'WhatsApp इंटीग्रेशन'},
  pf_reports:{en:'PDF Reports',hi:'PDF रिपोर्ट'},
  pf_5advisors:{en:'Up to 5 Advisors',hi:'5 सलाहकार तक'},
  pf_team_dash:{en:'Team Dashboard',hi:'टीम डैशबोर्ड'},
  pf_campaigns:{en:'Bulk Campaigns',hi:'बल्क अभियान'},
  pf_drive:{en:'Google Drive',hi:'Google Drive'},
  pf_transfer:{en:'Data Transfer',hi:'डेटा ट्रांसफर'},
  pf_all_solo:{en:'Everything in Solo',hi:'सोलो की सभी सुविधाएं'},
  pf_25advisors:{en:'Up to 25 Advisors',hi:'25 सलाहकार तक'},
  pf_admin:{en:'Admin Controls',hi:'एडमिन कंट्रोल'},
  pf_branding:{en:'Custom Branding',hi:'कस्टम ब्रांडिंग'},
  pf_api:{en:'API Access',hi:'API एक्सेस'},
  pf_priority:{en:'Priority Support',hi:'प्राथमिकता सहायता'},
  pf_all_team:{en:'Everything in Team',hi:'टीम की सभी सुविधाएं'},
  advisor_sg:{en:'advisor',hi:'सलाहकार'},
  advisors_pl:{en:'advisors',hi:'सलाहकार'},
  // Plan change policy
  pc_1:{en:'Upgrades take effect immediately after payment.',hi:'अपग्रेड भुगतान के बाद तुरंत लागू होते हैं।'},
  pc_2:{en:'Downgrades are scheduled for the next billing cycle — no prorata refund.',hi:'डाउनग्रेड अगले बिलिंग साइकिल के लिए शेड्यूल होते हैं — कोई प्रोरेटा रिफंड नहीं।'},
  pc_3:{en:'If downgrading to Solo, you must have only 1 active agent.',hi:'सोलो में डाउनग्रेड के लिए, केवल 1 सक्रिय एजेंट होना चाहिए।'},
  pc_4:{en:'You can cancel a scheduled change anytime before it takes effect.',hi:'आप लागू होने से पहले किसी भी समय शेड्यूल बदलाव रद्द कर सकते हैं।'},
  pc_5:{en:'Plan features (Team Dashboard, AI tools, etc.) change with the plan.',hi:'प्लान सुविधाएं (टीम डैशबोर्ड, AI टूल्स, आदि) प्लान के साथ बदलती हैं।'},
  // Profile
  my_profile:{en:'👤 My Profile',hi:'👤 मेरी प्रोफ़ाइल'},
  full_name:{en:'Full Name',hi:'पूरा नाम'},
  email:{en:'Email',hi:'ईमेल'},
  phone:{en:'Phone',hi:'फ़ोन'},
  city:{en:'City',hi:'शहर'},
  language:{en:'Language',hi:'भाषा'},
  lang_en:{en:'English',hi:'English'},
  lang_hi:{en:'हिंदी (Hindi)',hi:'हिंदी (Hindi)'},
  save_profile:{en:'💾 Save Profile',hi:'💾 प्रोफ़ाइल सेव करें'},
  saving:{en:'Saving...',hi:'सेव हो रहा है...'},
  profile_saved:{en:'✅ Profile saved!',hi:'✅ प्रोफ़ाइल सेव हो गई!'},
  session_expired:{en:'❌ Session expired',hi:'❌ सत्र समाप्त'},
  network_error:{en:'⚠️ Network error. Check your connection.',hi:'⚠️ नेटवर्क त्रुटि। अपना कनेक्शन जांचें।'},
  server_error:{en:'⚠️ Server error. Please try again.',hi:'⚠️ सर्वर त्रुटि। कृपया पुनः प्रयास करें।'},
  lead_saved:{en:'✅ Lead saved!',hi:'✅ लीड सेव हो गई!'},
  policy_saved:{en:'✅ Policy saved!',hi:'✅ पॉलिसी सेव हो गई!'},
  upload_pdf_or_image:{en:'📄 Upload PDF / Image',hi:'📄 PDF / इमेज अपलोड करें'},
  analyzing_doc:{en:'⏳ Analyzing document...',hi:'⏳ दस्तावेज़ विश्लेषण हो रहा है...'},
  // Branding
  firm_branding:{en:'🎨 Firm Branding',hi:'🎨 फर्म ब्रांडिंग'},
  brand_desc:{en:'Customize how your CRM brand appears to clients and on reports.',hi:'अपने CRM ब्रांड को ग्राहकों और रिपोर्ट में कैसे दिखे, कस्टमाइज़ करें।'},
  firm_logo:{en:'Firm Logo',hi:'फर्म लोगो'},
  logo_hint:{en:'JPEG or PNG, max 2MB',hi:'JPEG या PNG, अधिकतम 2MB'},
  remove:{en:'🗑️ Remove',hi:'🗑️ हटाएं'},
  firm_name:{en:'Firm Name',hi:'फर्म का नाम'},
  tagline:{en:'Tagline',hi:'टैगलाइन'},
  contact_phone:{en:'Contact Phone',hi:'संपर्क फ़ोन'},
  contact_email:{en:'Contact Email',hi:'संपर्क ईमेल'},
  cta_text:{en:'CTA Text (Call to Action)',hi:'CTA टेक्स्ट (कॉल टू एक्शन)'},
  primary_color:{en:'Primary Color',hi:'प्राइमरी रंग'},
  accent_color:{en:'Accent Color',hi:'एक्सेंट रंग'},
  credentials:{en:'Credentials / License (shown on reports & calculator pages)',hi:'क्रेडेंशियल / लाइसेंस (रिपोर्ट और कैलकुलेटर पेज पर दिखता है)'},
  save_branding:{en:'💾 Save Branding',hi:'💾 ब्रांडिंग सेव करें'},
  branding_saved:{en:'✅ Branding saved!',hi:'✅ ब्रांडिंग सेव हो गई!'},
  // Telegram Bot
  telegram_bot:{en:'🤖 Your Telegram Bot',hi:'🤖 आपका टेलीग्राम बॉट'},
  bot_username:{en:'Bot Username',hi:'बॉट यूज़रनेम'},
  not_configured:{en:'Not configured',hi:'कॉन्फ़िगर नहीं'},
  bot_status:{en:'Status',hi:'स्थिति'},
  bot_active:{en:'✅ Active',hi:'✅ सक्रिय'},
  bot_not_setup:{en:'⚠️ Not set up',hi:'⚠️ सेट अप नहीं'},
  bot_help:{en:'To create or change your bot, use the /createbot command on Telegram.',hi:'अपना बॉट बनाने या बदलने के लिए, टेलीग्राम पर /createbot कमांड का उपयोग करें।'},
  // Support
  all_tickets:{en:'All Tickets',hi:'सभी टिकट'},
  ticket_open:{en:'Open',hi:'खुला'},
  ticket_progress:{en:'In Progress',hi:'प्रगति में'},
  ticket_resolved:{en:'Resolved',hi:'हल किया'},
  ticket_closed:{en:'Closed',hi:'बंद'},
  new_ticket:{en:'🎫 New Ticket',hi:'🎫 नया टिकट'},
  th_id:{en:'ID',hi:'ID'},
  th_subject:{en:'Subject',hi:'विषय'},
  th_category:{en:'Category',hi:'श्रेणी'},
  th_priority:{en:'Priority',hi:'प्राथमिकता'},
  th_created:{en:'Created',hi:'बनाया गया'},
  no_tickets:{en:'No tickets yet',hi:'अभी कोई टिकट नहीं'},
  reply_placeholder:{en:'Type a reply...',hi:'उत्तर लिखें...'},
  send:{en:'Send',hi:'भेजें'},
  description:{en:'Description:',hi:'विवरण:'},
  // Add Lead Modal
  add_new_lead:{en:'Add New Lead',hi:'नई लीड जोड़ें'},
  edit_lead:{en:'Edit Lead',hi:'लीड संपादित करें'},
  name_required:{en:'Name *',hi:'नाम *'},
  phone_required:{en:'Phone *',hi:'फ़ोन *'},
  dob_required:{en:'DOB *',hi:'जन्म तिथि *'},
  need_type:{en:'Need Type',hi:'आवश्यकता का प्रकार'},
  nt_health:{en:'Health Insurance',hi:'स्वास्थ्य बीमा'},
  nt_term:{en:'Term Insurance',hi:'टर्म बीमा'},
  nt_endowment:{en:'Endowment / Traditional',hi:'एंडोमेंट / पारंपरिक'},
  nt_ulip:{en:'ULIP',hi:'ULIP'},
  nt_child:{en:'Child Plan',hi:'चाइल्ड प्लान'},
  nt_retirement:{en:'Retirement / Pension',hi:'रिटायरमेंट / पेंशन'},
  nt_motor:{en:'Motor Insurance',hi:'मोटर बीमा'},
  nt_investment:{en:'Investment / MF',hi:'निवेश / MF'},
  nt_nps:{en:'NPS',hi:'NPS'},
  nt_general:{en:'General',hi:'सामान्य'},
  source:{en:'Source',hi:'स्रोत'},
  src_web:{en:'Web Admin',hi:'वेब एडमिन'},
  src_referral:{en:'Referral',hi:'रेफरल'},
  src_social:{en:'Social Media',hi:'सोशल मीडिया'},
  src_cold:{en:'Cold Call',hi:'कोल्ड कॉल'},
  src_walkin:{en:'Walk-in',hi:'वॉक-इन'},
  src_direct:{en:'Direct',hi:'डायरेक्ट'},
  assign_agent:{en:'Assign to Agent',hi:'एजेंट को असाइन करें'},
  auto_owner:{en:'Auto (Owner)',hi:'ऑटो (मालिक)'},
  notes:{en:'Notes',hi:'नोट्स'},
  cancel:{en:'Cancel',hi:'रद्द करें'},
  save_lead:{en:'Save Lead',hi:'लीड सेव करें'},
  update_lead:{en:'Update Lead',hi:'लीड अपडेट करें'},
  // Add Policy Modal
  add_policy_title:{en:'Add Policy',hi:'पॉलिसी जोड़ें'},
  edit_policy:{en:'Edit Policy',hi:'पॉलिसी संपादित करें'},
  ai_extract:{en:'🤖 AI Extract',hi:'🤖 AI एक्सट्रैक्ट'},
  ai_extract_desc:{en:'Paste policy text or upload document photo',hi:'पॉलिसी टेक्स्ट पेस्ट करें या दस्तावेज़ फोटो अपलोड करें'},
  extract_text:{en:'🔍 Extract from Text',hi:'🔍 टेक्स्ट से निकालें'},
  upload_image:{en:'📷 Upload Image',hi:'📷 इमेज अपलोड करें'},
  select_lead:{en:'— Select Lead —',hi:'— लीड चुनें —'},
  client_lead:{en:'Client (Lead) *',hi:'ग्राहक (लीड) *'},
  policy_number:{en:'Policy Number',hi:'पॉलिसी नंबर'},
  insurer:{en:'Insurer *',hi:'बीमाकर्ता *'},
  plan_name:{en:'Plan Name',hi:'प्लान का नाम'},
  policy_type:{en:'Policy Type *',hi:'पॉलिसी प्रकार *'},
  sum_insured:{en:'Sum Insured (₹)',hi:'बीमित राशि (₹)'},
  premium_amt:{en:'Premium (₹) *',hi:'प्रीमियम (₹) *'},
  premium_mode:{en:'Premium Mode',hi:'प्रीमियम मोड'},
  pm_annual:{en:'Annual',hi:'वार्षिक'},
  pm_half:{en:'Half-Yearly',hi:'अर्ध-वार्षिक'},
  pm_quarterly:{en:'Quarterly',hi:'त्रैमासिक'},
  pm_monthly:{en:'Monthly',hi:'मासिक'},
  commission:{en:'Commission (₹)',hi:'कमीशन (₹)'},
  start_date:{en:'Start Date',hi:'आरंभ तिथि'},
  end_date:{en:'End Date',hi:'समाप्ति तिथि'},
  renewal_date:{en:'Renewal Date',hi:'नवीनीकरण तिथि'},
  save_policy:{en:'Save Policy',hi:'पॉलिसी सेव करें'},
  update_policy:{en:'Update Policy',hi:'पॉलिसी अपडेट करें'},
  // New Ticket Modal
  new_ticket_title:{en:'🎫 New Support Ticket',hi:'🎫 नया सहायता टिकट'},
  subject:{en:'Subject *',hi:'विषय *'},
  category:{en:'Category',hi:'श्रेणी'},
  cat_general:{en:'General',hi:'सामान्य'},
  cat_bug:{en:'Bug Report',hi:'बग रिपोर्ट'},
  cat_feature:{en:'Feature Request',hi:'फ़ीचर अनुरोध'},
  cat_billing:{en:'Billing',hi:'बिलिंग'},
  cat_technical:{en:'Technical',hi:'तकनीकी'},
  cat_other:{en:'Other',hi:'अन्य'},
  priority:{en:'Priority',hi:'प्राथमिकता'},
  pri_low:{en:'Low',hi:'कम'},
  pri_normal:{en:'Normal',hi:'सामान्य'},
  pri_high:{en:'High',hi:'उच्च'},
  pri_urgent:{en:'Urgent',hi:'अत्यावश्यक'},
  submit_ticket:{en:'Submit Ticket',hi:'टिकट जमा करें'},
  // Transfer & Stage modals
  transfer_title:{en:'Transfer Agent Data',hi:'एजेंट डेटा ट्रांसफर'},
  transfer_desc:{en:'Transfer all leads, policies, and interactions from {0} to:',hi:'{0} से सभी लीड्स, पॉलिसियां और इंटरैक्शन ट्रांसफर करें:'},
  target_agent:{en:'Target Agent',hi:'लक्ष्य एजेंट'},
  transfer_data:{en:'Transfer Data',hi:'डेटा ट्रांसफर'},
  change_stage:{en:'Change Lead Stage',hi:'लीड चरण बदलें'},
  move_to:{en:'Move {0} to:',hi:'{0} को ले जाएं:'},
  current:{en:'(current)',hi:'(वर्तमान)'},
  // Import CSV
  import_title:{en:'📥 Import Leads from CSV',hi:'📥 CSV से लीड्स आयात करें'},
  import_instructions:{en:'Instructions:',hi:'निर्देश:'},
  import_i1:{en:'Download the CSV template and fill in your leads.',hi:'CSV टेम्पलेट डाउनलोड करें और अपनी लीड्स भरें।'},
  import_i2:{en:'Required column: name. Optional: phone, email, city, need_type, stage, notes, dob, source.',hi:'आवश्यक कॉलम: name। वैकल्पिक: phone, email, city, need_type, stage, notes, dob, source।'},
  import_i3:{en:'Max 500 leads per import. Duplicates (same phone) are auto-skipped.',hi:'प्रति आयात अधिकतम 500 लीड्स। डुप्लिकेट (समान फ़ोन) अपने आप छोड़ दिए जाते हैं।'},
  csv_file:{en:'CSV File *',hi:'CSV फ़ाइल *'},
  assign_all:{en:'Assign All Leads To',hi:'सभी लीड्स को असाइन करें'},
  preview:{en:'Preview (first 5 rows):',hi:'पूर्वावलोकन (पहली 5 पंक्तियां):'},
  import_leads:{en:'Import Leads',hi:'लीड्स आयात करें'},
  import_complete:{en:'Import Complete!',hi:'आयात पूर्ण!'},
  imported:{en:'{0} imported',hi:'{0} आयात हुईं'},
  duplicates_skipped:{en:'{0} duplicates skipped',hi:'{0} डुप्लिकेट छोड़ी गईं'},
  errors:{en:'{0} errors',hi:'{0} त्रुटियां'},
  importing:{en:'Importing...',hi:'आयात हो रहा है...'},
  // Alerts
  name_is_required:{en:'Name is required',hi:'नाम आवश्यक है'},
  phone_is_required:{en:'Phone is required',hi:'फ़ोन आवश्यक है'},
  dob_is_required:{en:'Date of Birth is required',hi:'जन्म तिथि आवश्यक है'},
  invalid_phone:{en:'Phone must be a valid 10-digit Indian mobile number',hi:'फ़ोन 10 अंकों का वैध भारतीय मोबाइल नंबर होना चाहिए'},
  delete_lead_q:{en:'Delete "{0}" and all associated data? Cannot be undone.',hi:'"{0}" और सभी संबंधित डेटा हटाएं? पूर्ववत नहीं किया जा सकता।'},
  delete_policy_q:{en:'Delete policy "{0}"? This cannot be undone.',hi:'पॉलिसी "{0}" हटाएं? पूर्ववत नहीं किया जा सकता।'},
  subject_required:{en:'Subject is required',hi:'विषय आवश्यक है'},
  desc_required:{en:'Description is required',hi:'विवरण आवश्यक है'},
  // Extra HTML-ref keys
  firm_name_label:{en:'Firm Name',hi:'फर्म का नाम'},
  your_telegram_bot:{en:'🤖 Your Telegram Bot',hi:'🤖 आपका टेलीग्राम बॉट'},
  bot_help_text:{en:'To create or change your bot, use the /createbot command on Telegram.',hi:'अपना बॉट बनाने या बदलने के लिए, टेलीग्राम पर /createbot कमांड का उपयोग करें।'},
  open:{en:'Open',hi:'खुला'},
  in_progress:{en:'In Progress',hi:'प्रगति में'},
  resolved:{en:'Resolved',hi:'हल किया'},
  closed:{en:'Closed',hi:'बंद'},
  id:{en:'ID',hi:'ID'},
  status:{en:'Status',hi:'स्थिति'},
  created:{en:'Created',hi:'बनाया गया'},
  type_reply:{en:'Type a reply...',hi:'उत्तर लिखें...'},
  lead_name:{en:'Name *',hi:'नाम *'},
  lead_phone:{en:'Phone *',hi:'फ़ोन *'},
  dob:{en:'DOB *',hi:'जन्म तिथि *'},
  new_support_ticket:{en:'🎫 New Support Ticket',hi:'🎫 नया सहायता टिकट'},
  transfer_agent_data:{en:'Transfer Agent Data',hi:'एजेंट डेटा ट्रांसफर'},
  change_lead_stage:{en:'Change Lead Stage',hi:'लीड चरण बदलें'},
  import_leads_csv:{en:'📥 Import Leads from CSV',hi:'📥 CSV से लीड्स आयात करें'},
  premium:{en:'Premium (₹) *',hi:'प्रीमियम (₹) *'},
  description:{en:'Description *',hi:'विवरण *'},
  // switchDashLang
  lang_changed:{en:'Language changed to English',hi:'भाषा हिंदी में बदली गई'},
};
function _dt(k){ return (_DT[k]&&_DT[k][_dlang])||(_DT[k]&&_DT[k]['en'])||k; }
function _dtf(k,...a){ let s=_dt(k); a.forEach((v,i)=>{ s=s.replace(new RegExp('\\{'+i+'\\}','g'),v); }); return s; }
function applyDashI18n(){
  document.querySelectorAll('[data-i18n]').forEach(el=>{
    const k=el.getAttribute('data-i18n');
    if(_DT[k]&&_DT[k][_dlang]) el.textContent=_DT[k][_dlang];
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el=>{
    const k=el.getAttribute('data-i18n-ph');
    if(_DT[k]&&_DT[k][_dlang]) el.placeholder=_DT[k][_dlang];
  });
}
function switchDashLang(lang){
  _dlang = lang;
  localStorage.setItem('sarathi_lang', lang);
  applyDashI18n();
  // Update topbar lang button
  const lb=document.getElementById('topbar-lang-btn'); if(lb) lb.textContent=_dlang==='en'?'हिंदी':'English';
  // Update profile lang dropdown
  const pl=document.getElementById('prof-lang'); if(pl) pl.value=_dlang;
  // Refresh active tab title
  const activeTab = document.querySelector('.nav-item.active[data-tab]');
  if(activeTab) document.getElementById('page-title').textContent = _dt('tt_'+activeTab.dataset.tab);
  // Refresh PLAN_NAMES  
  PLAN_NAMES.trial=_dt('plan_trial'); PLAN_NAMES.individual=_dt('plan_solo'); PLAN_NAMES.team=_dt('plan_team'); PLAN_NAMES.enterprise=_dt('plan_enterprise');
  if(STATE.plan) { const s=document.querySelector('#sidebar-plan strong'); if(s) s.textContent=PLAN_NAMES[STATE.plan]||STATE.plan; }
  // Reload current tab to refresh dynamic text
  if(activeTab) {
    const t=activeTab.dataset.tab;
    if(t==='overview') loadOverview();
    else if(t==='leads') loadLeads();
    else if(t==='policies') loadPolicies();
    else if(t==='agents') loadAgents();
    else if(t==='subscription') loadSubscription();
    else if(t==='support') loadTickets();
  }
}
const PLAN_NAMES = { trial: _dt('plan_trial'), individual: _dt('plan_solo'), team: _dt('plan_team'), enterprise: _dt('plan_enterprise') };
const STAGE_LABELS = { prospect:'🎯 Prospect', contacted:'📞 Contacted', pitched:'📊 Pitched', proposal_sent:'📄 Proposal', negotiation:'🤝 Negotiation', closed_won:'✅ Won', closed_lost:'❌ Lost' };
const STAGES_LIST = ['prospect','contacted','pitched','proposal_sent','negotiation','closed_won','closed_lost'];
const STAGE_COLORS = { prospect:'#3b82f6', contacted:'#14b8a6', pitched:'#f59e0b', proposal_sent:'#f97316', negotiation:'#7c3aed', closed_won:'#16a34a', closed_lost:'#dc2626' };
const PLAN_ORDER = ['trial','individual','team','enterprise'];

// ── Toast Notification System ────
function showToast(msg, type='info', ms=3500) {
    let c = document.getElementById('toast-container');
    if (!c) { c = document.createElement('div'); c.id='toast-container'; c.style.cssText='position:fixed;top:20px;right:20px;z-index:99999;display:flex;flex-direction:column;gap:8px;max-width:380px;'; document.body.appendChild(c); }
    const t = document.createElement('div');
    const bg = {success:'#16a34a',error:'#dc2626',warn:'#f59e0b',info:'#3b82f6'}[type]||'#3b82f6';
    t.style.cssText = `background:${bg};color:#fff;padding:12px 18px;border-radius:8px;font-size:.88em;line-height:1.4;box-shadow:0 4px 12px rgba(0,0,0,.2);animation:slideIn .3s ease;cursor:pointer;`;
    t.textContent = msg; t.onclick = () => t.remove();
    c.appendChild(t); setTimeout(() => { t.style.opacity='0'; t.style.transition='opacity .3s'; setTimeout(()=>t.remove(),300); }, ms);
}

// ── Auth ────
const _tok = localStorage.getItem('sarathi_token');
if (!_tok) window.location.href = '/?login=1';

function hdrs() { const t = localStorage.getItem('sarathi_token'); return t ? { 'Authorization':'Bearer '+t, 'Content-Type':'application/json' } : {}; }

async function api(url, opts={}) {
    try {
        opts.headers = { ...hdrs(), ...(opts.headers||{}) };
        let res = await fetch(url, opts);
        if (res.status === 401) {
            const r = localStorage.getItem('sarathi_refresh');
            if (r) {
                const ref = await fetch('/api/auth/refresh', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh_token:r}) });
                if (ref.ok) { const d = await ref.json(); localStorage.setItem('sarathi_token',d.access_token); document.cookie='sarathi_token='+d.access_token+';path=/;max-age=86400;SameSite=Lax'; if(d.refresh_token) localStorage.setItem('sarathi_refresh',d.refresh_token); opts.headers={...hdrs(),...(opts.headers||{})}; res = await fetch(url,opts); }
                else { dashLogout(); return null; }
            } else { dashLogout(); return null; }
        }
        if (res.status >= 500) { showToast(_dt('server_error'), 'error'); }
        return res;
    } catch(e) {
        showToast(_dt('network_error'), 'error');
        return null;
    }
}

function dashLogout() {
    const t = localStorage.getItem('sarathi_token');
    if (t) fetch('/api/auth/logout',{method:'POST',headers:{'Authorization':'Bearer '+t}}).catch(()=>{});
    ['sarathi_token','sarathi_refresh','sarathi_tenant_id','sarathi_firm','sarathi_phone','sarathi_role'].forEach(k=>localStorage.removeItem(k));
    document.cookie = 'sarathi_token=;path=/;max-age=0';
    window.location.href = '/';
}

// ── Helpers ────
function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }
function fmt(n) { if(n>=10000000)return '₹'+(n/10000000).toFixed(1)+' Cr'; if(n>=100000)return '₹'+(n/100000).toFixed(1)+' L'; return '₹'+Number(n||0).toLocaleString('en-IN'); }
function fmtDate(d) { if(!d)return '-'; try{return new Date(d).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'});}catch{return d;} }
function closeModal(id) { document.getElementById(id).classList.remove('show'); }
function openModal(id) { document.getElementById(id).classList.add('show'); }
function isTeamPlan() { return ['team','enterprise'].includes(STATE.plan); }

let _debTimer;
function debouncedLoadLeads() { clearTimeout(_debTimer); _debTimer = setTimeout(()=>{_leadsPage=0;loadLeads();}, 400); }

// ── Tab Switching ────
function switchTab(tab) {
    document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
    document.querySelectorAll('.nav-item[data-tab]').forEach(n=>n.classList.remove('active'));
    const panel = document.getElementById('tab-'+tab);
    const nav = document.querySelector(`.nav-item[data-tab="${tab}"]`);
    if (panel) panel.classList.add('active');
    if (nav) nav.classList.add('active');
    document.getElementById('page-title').textContent = _dt('tt_'+tab)||tab;
    if (tab==='leads') loadLeads();
    else if (tab==='policies') loadPolicies();
    else if (tab==='agents') loadAgents();
    else if (tab==='subscription') loadSubscription();
    else if (tab==='profile') loadProfile();
    else if (tab==='support') loadTickets();
}

// ── Plan-based UI ────
function isOwnerRole() { return ['owner','admin'].includes(STATE.role); }

function configurePlanUI() {
    const isTeam = isTeamPlan();
    const isOwner = isOwnerRole();
    // Team tab: only show for owners/admins on team plans
    document.getElementById('nav-agents').classList.toggle('hidden', !(isTeam && isOwner));
    // Agent column in leads table: show on team plans (all roles can see agent name)
    document.querySelectorAll('.col-agent').forEach(el => el.style.display = isTeam ? '' : 'none');
    // Lead assign dropdown: only for owners
    document.getElementById('lead-assign-group').style.display = (isTeam && isOwner) ? '' : 'none';
    // Subscription tab: owner only
    const subNav = document.querySelector('.nav-item[data-tab="subscription"]');
    if (subNav) subNav.classList.toggle('hidden', !isOwner);
    // Affiliate Portal button: owner/admin only
    const affNav = document.getElementById('nav-affiliate');
    if (affNav) affNav.classList.toggle('hidden', !isOwner);
    // Import CSV button: owner only
    document.querySelectorAll('.import-csv-btn').forEach(el => el.style.display = isOwner ? '' : 'none');
    // Delete / Reassign buttons: owner only
    document.querySelectorAll('.owner-only').forEach(el => el.style.display = isOwner ? '' : 'none');
    // Plan badge
    document.getElementById('sidebar-plan').querySelector('strong').textContent = PLAN_NAMES[STATE.plan] || STATE.plan;
    if (STATE.tenant) {
        const firmName = STATE.tenant.firm_name || _dt('sidebar_crm');
        document.getElementById('sidebar-brand-name').textContent = firmName;
        document.getElementById('sidebar-firm').textContent = _dt('sidebar_dash');
        document.getElementById('topbar-user').textContent = STATE.tenant.owner_name || '';
    }
}

// ═══════════ OVERVIEW ═══════════
async function loadOverview() {
    const res = await api('/api/admin/overview');
    if (!res || !res.ok) return;
    const d = await res.json();
    STATE.tenant = d.tenant; STATE.plan = d.tenant?.plan||'trial'; STATE.features = d.plan_features||{}; STATE.pendingChange = d.pending_plan_change; STATE.role = d.role||localStorage.getItem('sarathi_role')||'owner';
    configurePlanUI();

    // Sidebar plan detail
    const t = d.tenant;
    let planDet = '';
    if (['trial','trialing'].includes(t.subscription_status) && t.trial_ends_at) {
        const dl=Math.max(0,Math.ceil((new Date(t.trial_ends_at)-new Date())/86400000));
        planDet = _dtf('days_left',dl);
    } else if (t.subscription_status==='active' && t.subscription_expires_at) {
        const dl=Math.max(0,Math.ceil((new Date(t.subscription_expires_at)-new Date())/86400000));
        planDet = _dtf('renews_in',dl);
    } else if (['expired','cancelled'].includes(t.subscription_status)) {
        planDet = t.subscription_status;
    }
    document.getElementById('sidebar-plan-detail').textContent = planDet;

    // Pending change banner — owner only
    if (d.pending_plan_change && isOwnerRole()) {
        document.getElementById('pending-change-banner').style.display = 'flex';
        const pc = d.pending_plan_change;
        document.getElementById('pending-change-text').innerHTML = `Plan change scheduled: <strong>${PLAN_NAMES[pc.current_plan]} → ${PLAN_NAMES[pc.new_plan]}</strong> — effective next billing cycle.`;
    } else { document.getElementById('pending-change-banner').style.display = 'none'; }

    // KPIs
    const kpis = [
        {icon:'📋',value:d.total_leads,label:_dt('kpi_total_leads')},
        {icon:'🆕',value:d.today_leads,label:_dt('kpi_todays_leads')},
        {icon:'✅',value:d.total_policies,label:_dt('kpi_active_policies')},
        {icon:'💰',value:fmt(d.total_premium),label:_dt('kpi_total_premium'),raw:1},
        {icon:'📈',value:d.month_leads,label:_dt('kpi_month_leads')},
        {icon:'🎯',value:d.conversion_rate+'%',label:_dt('kpi_conversion'),raw:1},
    ];
    if (isTeamPlan() && isOwnerRole()) kpis.push({icon:'👥',value:d.active_agents+'/'+d.total_agents,label:_dt('kpi_agents'),raw:1});
    document.getElementById('kpi-grid').innerHTML = kpis.map(k=>`<div class="kpi-card"><div class="kpi-icon">${k.icon}</div><div class="kpi-value">${k.raw?k.value:k.value}</div><div class="kpi-label">${k.label}</div></div>`).join('');

    // Pipeline
    const pipeline = d.pipeline||{};
    const stagesDef = [{l:_dt('stg_prospect'),k:'prospect',c:'#3b82f6'},{l:_dt('stg_contacted'),k:'contacted',c:'#14b8a6'},{l:_dt('stg_pitched'),k:'pitched',c:'#f59e0b'},{l:_dt('stg_proposal'),k:'proposal_sent',c:'#f97316'},{l:_dt('stg_negotiation'),k:'negotiation',c:'#7c3aed'},{l:_dt('stg_won'),k:'closed_won',c:'#16a34a'},{l:_dt('stg_lost'),k:'closed_lost',c:'#dc2626'}];
    const maxC = Math.max(...stagesDef.map(s=>pipeline[s.k]||0),1);
    document.getElementById('pipeline-chart').innerHTML = stagesDef.map(s=>{const c=pipeline[s.k]||0;const w=Math.max((c/maxC)*100,5);return `<div class="funnel-stage"><div class="funnel-label">${s.l}</div><div class="funnel-bar-bg"><div class="funnel-bar" style="width:${w}%;background:${s.c}">${c}</div></div><div class="funnel-count">${c}</div></div>`;}).join('');

    // Followups + Renewals
    const dRes = await api('/api/dashboard');
    if (dRes && dRes.ok) {
        const dd = await dRes.json();
        document.getElementById('followup-count').textContent = dd.followups_count||0;
        document.getElementById('followup-list').innerHTML = (dd.followups&&dd.followups.length) ?
            dd.followups.map(f=>{const safeP=(f.lead_phone||'').replace(/\D/g,'');return `<div style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)"><span style="font-size:1.1em;margin-right:10px">📞</span><div style="flex:1"><strong style="font-size:.85em">${esc(f.lead_name||'Client')}</strong><div style="font-size:.75em;color:var(--muted)">${esc(f.summary||_dt('followup'))} ${f.lead_phone?'• '+esc(f.lead_phone):''}</div></div>${safeP?`<a href="tel:${safeP}" style="margin-right:6px;text-decoration:none">📞</a><a href="https://wa.me/91${safeP}" target="_blank" style="text-decoration:none">💬</a>`:''}</div>`;}).join('') :
            `<div class="empty"><div class="icon">✅</div><p>${_dt('no_followups')}</p></div>`;
        document.getElementById('renewal-count').textContent = dd.renewals_count||0;
        document.getElementById('renewal-list').innerHTML = (dd.renewals&&dd.renewals.length) ?
            dd.renewals.slice(0,10).map(r=>`<div style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)"><span style="font-size:1.1em;margin-right:10px">🔄</span><div style="flex:1"><strong style="font-size:.85em">${esc(r.client_name||'Client')}</strong><div style="font-size:.75em;color:var(--muted)">${esc(r.plan_name||'Policy')} • ${fmtDate(r.renewal_date)} ${r.premium?'• '+fmt(r.premium):''}</div></div></div>`).join('') :
            `<div class="empty"><div class="icon">📅</div><p>${_dt('no_renewals')}</p></div>`;
    }
}

// ═══════════ LEADS ═══════════
let _leadsPage = 0;

async function loadLeads() {
    const search = document.getElementById('lead-search').value.trim();
    const stage = document.getElementById('lead-stage-filter').value;
    const limit = 50;
    let url = `/api/admin/leads?limit=${limit}&offset=${_leadsPage*limit}`;
    if (stage) url += `&stage=${stage}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    const res = await api(url);
    if (!res||!res.ok) return;
    const d = await res.json();
    const showA = isTeamPlan();

    // Ensure agents loaded for assignment
    if (showA && !STATE.agents.length) {
        const ar = await api('/api/agents');
        if (ar&&ar.ok) { const ad = await ar.json(); STATE.agents = ad.agents||[]; }
    }
    if (showA) {
        document.getElementById('lead-assign-agent').innerHTML = '<option value="">Auto (Owner)</option>' + STATE.agents.filter(a=>a.is_active).map(a=>`<option value="${a.agent_id}">${esc(a.name)} (${a.role})</option>`).join('');
    }

    document.getElementById('leads-body').innerHTML = d.leads.length ? d.leads.map(l=>`<tr>
        <td><strong>${esc(l.name)}</strong>${l.email?'<br><span style="font-size:.72em;color:var(--muted)">'+esc(l.email)+'</span>':''}</td>
        <td>${esc(l.phone||'-')}</td>
        <td><span class="badge stage-${l.stage}">${STAGE_LABELS[l.stage]||l.stage}</span></td>
        <td>${esc(l.need_type||'-')}</td>
        <td>${esc(l.source||'-')}</td>
        ${showA?'<td style="font-size:.82em">'+esc(l.agent_name||'-')+'</td>':''}
        <td style="font-size:.78em;color:var(--muted)">${fmtDate(l.updated_at)}</td>
        <td style="white-space:nowrap">
            <button class="btn btn-sm btn-outline" onclick="editLead(${l.lead_id})" title="Edit">✏️</button>
            <button class="btn btn-sm btn-outline" onclick="showStageModal(${l.lead_id},'${esc(l.name)}','${l.stage}')" title="Stage">📊</button>
            ${isOwnerRole()?`<button class="btn btn-sm btn-outline" onclick="deleteLead(${l.lead_id},'${esc(l.name).replace(/'/g,"\\'")}')" title="Delete" style="color:var(--red)">🗑️</button>`:''}
        </td></tr>`).join('') :
        `<tr><td colspan="${showA?8:7}"><div class="empty"><div class="icon">📋</div><p>${_dt('no_leads')}</p></div></td></tr>`;

    const pages = Math.ceil(d.total/limit);
    document.getElementById('leads-pagination').innerHTML = `<span>${_dtf('showing',d.leads.length,d.total)}</span>
        <div style="display:flex;gap:6px">
            ${_leadsPage>0?`<button class="btn btn-sm btn-outline" onclick="_leadsPage--;loadLeads()">${_dt('prev')}</button>`:''}
            <span style="padding:5px 10px;font-size:.82em">Page ${_leadsPage+1}/${Math.max(pages,1)}</span>
            ${_leadsPage<pages-1?`<button class="btn btn-sm btn-outline" onclick="_leadsPage++;loadLeads()">${_dt('next')}</button>`:''}
        </div>`;
}

function showAddLeadModal() {
    document.getElementById('lead-modal-title').textContent = _dt('add_new_lead');
    document.getElementById('lead-edit-id').value = '';
    ['lead-name','lead-phone','lead-email','lead-dob','lead-city','lead-notes'].forEach(id=>document.getElementById(id).value='');
    document.getElementById('lead-need').value = 'health';
    document.getElementById('lead-source').value = 'web_admin';
    document.getElementById('lead-assign-agent').value = '';
    document.getElementById('lead-save-btn').textContent = _dt('save_lead');
    openModal('lead-modal');
}

let _cachedLeads = [];
async function editLead(id) {
    // Find lead from cached page or re-fetch
    let lead = null;
    const res = await api(`/api/admin/leads?limit=200&offset=0`);
    if (res&&res.ok) { const d = await res.json(); _cachedLeads = d.leads; lead = d.leads.find(l=>l.lead_id===id); }
    if (!lead) { alert('Lead not found'); return; }

    document.getElementById('lead-modal-title').textContent = _dt('edit_lead');
    document.getElementById('lead-edit-id').value = id;
    document.getElementById('lead-name').value = lead.name||'';
    document.getElementById('lead-phone').value = lead.phone||'';
    document.getElementById('lead-email').value = lead.email||'';
    document.getElementById('lead-dob').value = lead.dob ? lead.dob.substring(0,10) : '';
    document.getElementById('lead-city').value = lead.city||'';
    document.getElementById('lead-need').value = lead.need_type||'health';
    document.getElementById('lead-source').value = lead.source||'direct';
    document.getElementById('lead-notes').value = lead.notes||'';
    document.getElementById('lead-save-btn').textContent = _dt('update_lead');
    openModal('lead-modal');
}

async function saveLead() {
    const editId = document.getElementById('lead-edit-id').value;
    const name = document.getElementById('lead-name').value.trim();
    const phone = document.getElementById('lead-phone').value.trim();
    const dob = document.getElementById('lead-dob').value;
    if (!name) { showToast(_dt('name_is_required'), 'warn'); return; }
    if (!editId && !phone) { showToast(_dt('phone_is_required'), 'warn'); return; }
    if (!editId && !dob) { showToast(_dt('dob_is_required'), 'warn'); return; }
    if (phone && !/^[6-9]\d{9}$/.test(phone)) { showToast(_dt('invalid_phone'), 'warn'); return; }

    const btn = document.getElementById('lead-save-btn'); const origText = btn.textContent;
    btn.disabled = true; btn.textContent = _dt('saving');
    try {
        const body = { name, phone:phone||null, email:document.getElementById('lead-email').value.trim()||null, dob:dob||null, city:document.getElementById('lead-city').value.trim()||null, need_type:document.getElementById('lead-need').value, source:document.getElementById('lead-source').value, notes:document.getElementById('lead-notes').value.trim()||null };
        if (!editId) { const ag = document.getElementById('lead-assign-agent').value; if(ag) body.assign_to_agent_id = parseInt(ag); }

        const url = editId ? `/api/admin/leads/${editId}` : '/api/admin/leads';
        const res = await api(url, { method: editId?'PUT':'POST', body:JSON.stringify(body) });
        if (!res) { btn.disabled=false; btn.textContent=origText; return; }
        const d = await res.json();
        if (d.error) { showToast(d.error, 'error'); btn.disabled=false; btn.textContent=origText; return; }
        showToast(_dt('lead_saved'), 'success');
        closeModal('lead-modal');
        loadLeads(); loadOverview();
    } catch(e) { showToast(_dt('network_error'), 'error'); }
    btn.disabled = false; btn.textContent = origText;
}

function showStageModal(id, name, current) {
    document.getElementById('stage-lead-id').value = id;
    document.getElementById('stage-lead-name').textContent = name;
    document.getElementById('stage-buttons').innerHTML = STAGES_LIST.map(s=>
        `<button class="btn ${s===current?'btn-outline':'btn-primary'}" style="justify-content:center;background:${s===current?'var(--bg)':STAGE_COLORS[s]};${s===current?'color:var(--muted);cursor:default':''}" ${s===current?'disabled':''} onclick="doStageChange(${id},'${s}')">${STAGE_LABELS[s]}${s===current?' '+_dt('current'):''}</button>`
    ).join('');
    openModal('stage-modal');
}

async function doStageChange(id, stage) {
    const res = await api(`/api/admin/leads/${id}/stage?stage=${stage}`, {method:'PUT'});
    if (res&&res.ok) { closeModal('stage-modal'); loadLeads(); loadOverview(); }
    else { const d = await res?.json(); alert(d?.error||'Failed'); }
}

async function deleteLead(id, name) {
    if (!confirm(_dtf('delete_lead_q',name))) return;
    const res = await api(`/api/admin/leads/${id}`, {method:'DELETE'});
    if (res&&res.ok) { loadLeads(); loadOverview(); }
    else { const d = await res?.json(); alert(d?.error||'Failed'); }
}

// ═══════════ POLICIES ═══════════
let _cachedPolicies = [];
async function loadPolicies() {
    const status = document.getElementById('policy-status-filter').value;
    let url = '/api/admin/policies?limit=200';
    if (status) url += `&status=${status}`;
    const res = await api(url);
    if (!res||!res.ok) return;
    const d = await res.json();
    _cachedPolicies = d.policies||[];
    const showA = isTeamPlan();
    const cols = showA ? 10 : 9;
    document.getElementById('policies-body').innerHTML = _cachedPolicies.length ? _cachedPolicies.map(p=>`<tr>
        <td><strong>${esc(p.lead_name||'-')}</strong>${p.lead_phone?'<br><span style="font-size:.72em;color:var(--muted)">'+esc(p.lead_phone)+'</span>':''}</td>
        <td style="font-size:.82em">${esc(p.policy_number||'-')}</td>
        <td>${esc(p.insurer||'-')}</td><td>${esc(p.plan_name||'-')}</td>
        <td><span class="badge badge-blue" style="font-size:.72em">${esc(p.policy_type||'-')}</span></td>
        <td>${p.premium?fmt(p.premium):'-'}${p.premium_mode?'<br><span style="font-size:.7em;color:var(--muted)">/'+esc(p.premium_mode)+'</span>':''}</td>
        <td>${fmtDate(p.renewal_date)}</td>
        <td><span class="badge ${p.status==='active'?'badge-green':'badge-muted'}">${esc(p.status||'-')}</span></td>
        ${showA?'<td style="font-size:.82em">'+esc(p.agent_name||'-')+'</td>':''}
        <td style="white-space:nowrap">
            <button class="btn-icon" title="Edit" onclick="editPolicy(${p.policy_id})">✏️</button>
            ${isOwnerRole()?`<button class="btn-icon" title="Delete" onclick="deletePolicy(${p.policy_id},'${esc(p.plan_name||'this policy')}')">🗑️</button>`:''}
        </td>
    </tr>`).join('') : `<tr><td colspan="${cols}"><div class="empty"><div class="icon">📄</div><p>${_dt('no_policies')}</p></div></td></tr>`;
}

async function openAddPolicy() {
    document.getElementById('policy-modal-title').textContent = _dt('add_policy_title');
    document.getElementById('policy-edit-id').value = '';
    document.getElementById('policy-number').value = '';
    document.getElementById('policy-insurer').value = '';
    document.getElementById('policy-plan').value = '';
    document.getElementById('policy-type').value = 'health';
    document.getElementById('policy-si').value = '';
    document.getElementById('policy-premium').value = '';
    document.getElementById('policy-mode').value = 'annual';
    document.getElementById('policy-commission').value = '';
    document.getElementById('policy-start').value = '';
    document.getElementById('policy-end').value = '';
    document.getElementById('policy-renewal').value = '';
    document.getElementById('policy-notes').value = '';
    document.getElementById('policy-ai-text').value = '';
    document.getElementById('policy-ai-status').textContent = '';
    document.getElementById('policy-status-group').style.display = 'none';
    document.getElementById('policy-lead-group').style.display = '';
    document.getElementById('policy-save-btn').textContent = _dt('save_policy');
    // Load leads for dropdown
    const sel = document.getElementById('policy-lead-id');
    sel.innerHTML = `<option value="">${_dt('select_lead')}</option>`;
    const res = await api('/api/admin/leads?limit=500');
    if (res&&res.ok) { const d = await res.json(); (d.leads||[]).forEach(l=>{ const o=document.createElement('option'); o.value=l.lead_id; o.textContent=`${l.name} (${l.phone||'no phone'})`; sel.appendChild(o); }); }
    openModal('policy-modal');
}

async function editPolicy(id) {
    const p = _cachedPolicies.find(x=>x.policy_id===id);
    if (!p) { alert('Policy not found'); return; }
    document.getElementById('policy-modal-title').textContent = _dt('edit_policy');
    document.getElementById('policy-edit-id').value = id;
    document.getElementById('policy-number').value = p.policy_number||'';
    document.getElementById('policy-insurer').value = p.insurer||'';
    document.getElementById('policy-plan').value = p.plan_name||'';
    document.getElementById('policy-type').value = p.policy_type||'health';
    document.getElementById('policy-si').value = p.sum_insured||'';
    document.getElementById('policy-premium').value = p.premium||'';
    document.getElementById('policy-mode').value = p.premium_mode||'annual';
    document.getElementById('policy-commission').value = p.commission||'';
    document.getElementById('policy-start').value = p.start_date ? p.start_date.substring(0,10) : '';
    document.getElementById('policy-end').value = p.end_date ? p.end_date.substring(0,10) : '';
    document.getElementById('policy-renewal').value = p.renewal_date ? p.renewal_date.substring(0,10) : '';
    document.getElementById('policy-notes').value = p.notes||'';
    document.getElementById('policy-ai-text').value = '';
    document.getElementById('policy-ai-status').textContent = '';
    document.getElementById('policy-status-group').style.display = '';
    document.getElementById('policy-status').value = p.status||'active';
    document.getElementById('policy-lead-group').style.display = 'none';
    document.getElementById('policy-save-btn').textContent = _dt('update_policy');
    openModal('policy-modal');
}

async function savePolicy() {
    const editId = document.getElementById('policy-edit-id').value;
    const body = {
        policy_number: document.getElementById('policy-number').value.trim()||null,
        insurer: document.getElementById('policy-insurer').value.trim()||null,
        plan_name: document.getElementById('policy-plan').value.trim()||null,
        policy_type: document.getElementById('policy-type').value,
        sum_insured: parseFloat(document.getElementById('policy-si').value)||null,
        premium: parseFloat(document.getElementById('policy-premium').value)||null,
        premium_mode: document.getElementById('policy-mode').value,
        commission: parseFloat(document.getElementById('policy-commission').value)||0,
        start_date: document.getElementById('policy-start').value||null,
        end_date: document.getElementById('policy-end').value||null,
        renewal_date: document.getElementById('policy-renewal').value||null,
        notes: document.getElementById('policy-notes').value.trim()||null,
    };
    if (!editId) {
        body.lead_id = parseInt(document.getElementById('policy-lead-id').value);
        if (!body.lead_id) { showToast(_dt('select_client_required')||'Please select a client', 'warn'); return; }
    }
    if (editId) { body.status = document.getElementById('policy-status').value; }
    const btn = event?.target || document.querySelector('#policy-modal .btn-primary');
    const origText = btn?.textContent||'';
    if(btn){btn.disabled=true; btn.textContent=_dt('saving');}
    try {
        const url = editId ? `/api/admin/policies/${editId}` : '/api/admin/policies';
        const res = await api(url, { method: editId?'PUT':'POST', body:JSON.stringify(body) });
        if (!res) { if(btn){btn.disabled=false;btn.textContent=origText;} return; }
        const d = await res.json();
        if (d.error) { showToast(d.error, 'error'); if(btn){btn.disabled=false;btn.textContent=origText;} return; }
        showToast(_dt('policy_saved'), 'success');
        closeModal('policy-modal');
        loadPolicies();
    } catch(e) { showToast(_dt('network_error'), 'error'); }
    if(btn){btn.disabled=false; btn.textContent=origText;}
}

async function deletePolicy(id, name) {
    if (!confirm(_dtf('delete_policy_q',name))) return;
    const res = await api(`/api/admin/policies/${id}`, {method:'DELETE'});
    if (res&&res.ok) { loadPolicies(); }
    else { const d = await res?.json(); alert(d?.error||'Failed to delete'); }
}

async function extractPolicyText() {
    const text = document.getElementById('policy-ai-text').value.trim();
    if (!text || text.length < 20) { alert('Please paste at least 20 characters of policy text'); return; }
    const status = document.getElementById('policy-ai-status');
    status.textContent = '⏳ Extracting...';
    try {
        const res = await api('/api/admin/policies/extract', { method:'POST', body:JSON.stringify({text}) });
        if (!res||!res.ok) { status.textContent = '❌ Extraction failed'; return; }
        const d = await res.json();
        if (d.extracted) { fillPolicyFromAI(d.extracted); status.textContent = '✅ Fields filled from AI'; }
        else { status.textContent = '❌ Could not extract'; }
    } catch(e) { status.textContent = '❌ Error: '+e.message; }
}

async function extractPolicyDoc(input) {
    if (!input.files||!input.files[0]) return;
    const file = input.files[0];
    if (file.size > 10*1024*1024) { showToast('File too large. Max 10MB.', 'warn'); return; }
    const status = document.getElementById('policy-ai-status');
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    status.textContent = isPdf ? _dt('analyzing_doc') : '⏳ Analyzing image...';
    try {
        const fd = new FormData(); fd.append('file', file);
        const token = localStorage.getItem('sarathi_token');
        const res = await fetch('/api/admin/policies/extract', { method:'POST', body: fd, headers: token?{'Authorization':'Bearer '+token}:{} });
        if (!res.ok) { status.textContent = '❌ Extraction failed'; return; }
        const d = await res.json();
        if (d.extracted) { fillPolicyFromAI(d.extracted); status.textContent = '✅ Fields filled from AI'; }
        else { status.textContent = '❌ Could not extract'; }
    } catch(e) { status.textContent = '❌ Error: '+e.message; }
    input.value = '';
}

function fillPolicyFromAI(data) {
    if (data.policy_number) document.getElementById('policy-number').value = data.policy_number;
    if (data.insurer) document.getElementById('policy-insurer').value = data.insurer;
    if (data.plan_name) document.getElementById('policy-plan').value = data.plan_name;
    if (data.policy_type) document.getElementById('policy-type').value = data.policy_type;
    if (data.sum_insured) document.getElementById('policy-si').value = data.sum_insured;
    if (data.premium) document.getElementById('policy-premium').value = data.premium;
    if (data.premium_mode) document.getElementById('policy-mode').value = data.premium_mode;
    if (data.start_date) document.getElementById('policy-start').value = data.start_date;
    if (data.end_date) document.getElementById('policy-end').value = data.end_date;
    if (data.renewal_date) document.getElementById('policy-renewal').value = data.renewal_date;
    if (data.notes) document.getElementById('policy-notes').value = data.notes;
}

// ═══════════ SUPPORT TICKETS ═══════════
let _ticketDetailId = null;
async function loadTickets() {
    const status = document.getElementById('ticket-status-filter').value;
    let url = '/api/support/tickets';
    if (status) url += `?status=${status}`;
    const res = await api(url);
    if (!res||!res.ok) return;
    const d = await res.json();
    const tickets = d.tickets||d||[];
    const priorityBadge = p => p==='urgent'?'badge-red':p==='high'?'badge-saffron':p==='normal'?'badge-blue':'badge-muted';
    const statusBadge = s => s==='open'?'badge-blue':s==='in_progress'?'badge-saffron':s==='resolved'?'badge-green':'badge-muted';
    document.getElementById('tickets-body').innerHTML = tickets.length ? tickets.map(t=>`<tr>
        <td style="font-size:.82em">#${t.ticket_id}</td>
        <td><strong>${esc(t.subject||'-')}</strong></td>
        <td style="font-size:.82em">${esc(t.category||'-')}</td>
        <td><span class="badge ${priorityBadge(t.priority)}" style="font-size:.72em">${esc(t.priority||'-')}</span></td>
        <td><span class="badge ${statusBadge(t.status)}">${esc((t.status||'-').replace('_',' '))}</span></td>
        <td style="font-size:.82em">${fmtDate(t.created_at)}</td>
        <td><button class="btn-icon" title="View" onclick="viewTicket(${t.ticket_id})">👁️</button></td>
    </tr>`).join('') : `<tr><td colspan="7"><div class="empty"><div class="icon">🎫</div><p>${_dt('no_tickets')}</p></div></td></tr>`;
    if (_ticketDetailId) viewTicket(_ticketDetailId);
}

async function viewTicket(id) {
    _ticketDetailId = id;
    const res = await api(`/api/support/tickets/${id}`);
    if (!res||!res.ok) return;
    const d = await res.json();
    const t = d.ticket||d;
    const msgs = d.messages||[];
    document.getElementById('ticket-detail-subject').textContent = `#${t.ticket_id} — ${t.subject}`;
    const statusBadge = t.status==='open'?'badge-blue':t.status==='in_progress'?'badge-saffron':t.status==='resolved'?'badge-green':'badge-muted';
    document.getElementById('ticket-detail-status').className = 'badge ' + statusBadge;
    document.getElementById('ticket-detail-status').textContent = (t.status||'').replace('_',' ');
    document.getElementById('ticket-detail-desc').innerHTML = `<strong>${_dt('description')}:</strong><br>${esc(t.description||'')}`;
    document.getElementById('ticket-messages').innerHTML = msgs.map(m=>`<div style="padding:8px 12px;margin-bottom:6px;border-radius:8px;font-size:.85em;${m.sender_type==='support'?'background:var(--primary);color:#fff':'background:var(--bg)'}">
        <strong>${esc(m.sender_name||m.sender_type)}</strong> <span style="font-size:.78em;opacity:.7">${fmtDate(m.created_at)}</span><br>${esc(m.message)}
    </div>`).join('');
    document.getElementById('ticket-reply-text').value = '';
    document.getElementById('ticket-detail').style.display = '';
}

function openNewTicket() {
    document.getElementById('ticket-subject').value = '';
    document.getElementById('ticket-desc').value = '';
    document.getElementById('ticket-category').value = 'general';
    document.getElementById('ticket-priority').value = 'normal';
    openModal('ticket-modal');
}

async function submitTicket() {
    const subject = document.getElementById('ticket-subject').value.trim();
    const description = document.getElementById('ticket-desc').value.trim();
    if (!subject) { alert(_dt('subject_required')); return; }
    if (!description) { alert(_dt('desc_required')); return; }
    const body = { subject, description, category: document.getElementById('ticket-category').value, priority: document.getElementById('ticket-priority').value };
    const res = await api('/api/support/tickets', { method:'POST', body:JSON.stringify(body) });
    if (!res) return;
    const d = await res.json();
    if (d.error) { alert(d.error); return; }
    closeModal('ticket-modal');
    loadTickets();
}

async function replyTicket() {
    if (!_ticketDetailId) return;
    const message = document.getElementById('ticket-reply-text').value.trim();
    if (!message) return;
    const res = await api(`/api/support/tickets/${_ticketDetailId}/reply`, { method:'POST', body:JSON.stringify({message}) });
    if (res&&res.ok) { viewTicket(_ticketDetailId); loadTickets(); }
    else { const d = await res?.json(); alert(d?.error||'Failed'); }
}

// ═══════════ AGENTS ═══════════
async function loadAgents() {
    const res = await api('/api/agents');
    if (!res||!res.ok) return;
    const d = await res.json();
    STATE.agents = d.agents||[];
    document.getElementById('agents-body').innerHTML = STATE.agents.map(a=>{
        const avatar = a.profile_photo
            ? `<img src="${esc(a.profile_photo)}?t=${Date.now()}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;margin-right:8px;vertical-align:middle">`
            : `<span style="display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;background:var(--primary);color:#fff;font-size:.8em;font-weight:600;margin-right:8px;vertical-align:middle">${esc((a.name||'?')[0].toUpperCase())}</span>`;
        return `<tr>
        <td style="white-space:nowrap">${avatar}<strong>${esc(a.name)}</strong></td><td>${esc(a.phone||'-')}</td><td>${esc(a.email||'-')}</td>
        <td><span class="badge ${a.role==='owner'?'badge-purple':'badge-blue'}">${a.role}</span></td>
        <td>${a.lead_count||0}</td><td>${a.policy_count||0}</td>
        <td><span class="badge ${a.is_active?'badge-green':'badge-red'}">${a.is_active?'Active':'Inactive'}</span></td>
        <td style="white-space:nowrap">
            <label class="btn btn-sm btn-outline" style="cursor:pointer;margin-right:2px" title="Upload photo"><input type="file" accept="image/jpeg,image/png" style="display:none" onchange="uploadAgentPhoto(${a.agent_id},this)">📸</label>
            ${a.role!=='owner'?`
            ${a.is_active?`<button class="btn btn-sm btn-outline" onclick="toggleAgent(${a.agent_id},false)" style="color:var(--red)">⏸️</button>`:`<button class="btn btn-sm btn-outline" onclick="toggleAgent(${a.agent_id},true)" style="color:var(--green)">▶️</button>`}
            <button class="btn btn-sm btn-outline" onclick="showTransfer(${a.agent_id},'${esc(a.name).replace(/'/g,"\\'")}')" title="Transfer">🔄</button>
        `:'<span style="font-size:.72em;color:var(--muted)">Owner</span>'}</td>
    </tr>`;}).join('');

    // Capacity
    const sr = await api('/api/subscription/status');
    if (sr&&sr.ok) {
        const sub = await sr.json();
        const used = sub.current_agents||0, max = sub.max_agents||1, pct = Math.round((used/max)*100);
        document.getElementById('agent-capacity').innerHTML = `<div style="display:flex;align-items:center;gap:16px"><div style="flex:1"><div style="display:flex;justify-content:space-between;font-size:.85em;margin-bottom:6px"><span><strong>${used}</strong> / <strong>${max}</strong></span><span>${pct}%</span></div><div style="background:var(--bg);border-radius:8px;height:12px;overflow:hidden"><div style="background:${pct>=90?'var(--red)':pct>=70?'var(--saffron)':'var(--green)'};height:100%;width:${pct}%;border-radius:8px;transition:width .4s"></div></div></div>${used<max?`<span style="font-size:.82em;color:var(--green)">${_dt('can_add_more')}</span>`:`<span style="font-size:.82em;color:var(--red)">${_dt('limit_reached')}</span>`}</div>`;
    }
}

async function toggleAgent(id, activate) {
    if (!confirm(`${activate?'Reactivate':'Deactivate'} this agent?`)) return;
    const res = await api(`/api/agents/${id}/${activate?'reactivate':'deactivate'}`,{method:'POST'});
    if (res&&res.ok) loadAgents(); else { const d=await res?.json(); alert(d?.error||'Failed'); }
}

async function uploadAgentPhoto(agentId, input) {
    const file = input.files[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) { alert('Please select an image file (JPEG or PNG)'); return; }
    if (file.size > 5*1024*1024) { alert('Image too large. Max 5MB.'); return; }
    const formData = new FormData();
    formData.append('photo', file);
    const tok = localStorage.getItem('sarathi_token');
    try {
        const res = await fetch(`/api/agent/${agentId}/photo`, {
            method: 'POST', headers: {'Authorization':'Bearer '+tok}, body: formData
        });
        const d = await res.json();
        if (d.error) { alert(d.error); return; }
        loadAgents();
    } catch(e) { alert('Upload failed: '+e.message); }
}

async function generateInvite() {
    const res = await api('/api/admin/invite',{method:'POST'});
    if (!res) return;
    const d = await res.json();
    if (d.error) { alert(d.error); return; }
    document.getElementById('invite-banner').style.display = 'flex';
    document.getElementById('invite-code-display').textContent = d.code;
    const linkEl = document.getElementById('invite-link-display');
    if (linkEl && d.invite_url) { linkEl.href = d.invite_url; linkEl.textContent = d.invite_url; linkEl.style.display = 'inline'; }
}

function showTransfer(fromId, fromName) {
    document.getElementById('transfer-from-id').value = fromId;
    document.getElementById('transfer-from-name').textContent = fromName;
    document.getElementById('transfer-to-agent').innerHTML = STATE.agents.filter(a=>a.agent_id!==fromId&&a.is_active).map(a=>`<option value="${a.agent_id}">${esc(a.name)} (${a.role})</option>`).join('');
    openModal('transfer-modal');
}

async function doTransfer() {
    const from = parseInt(document.getElementById('transfer-from-id').value);
    const to = parseInt(document.getElementById('transfer-to-agent').value);
    if (!to) { alert('Select target agent'); return; }
    if (!confirm('Transfer ALL data? Cannot be undone.')) return;
    const res = await api('/api/agents/transfer',{method:'POST',body:JSON.stringify({from_agent_id:from,to_agent_id:to})});
    if (res&&res.ok) { closeModal('transfer-modal'); loadAgents(); alert('Transfer complete!'); }
    else { const d=await res?.json(); alert(d?.error||'Failed'); }
}

// ═══════════ SUBSCRIPTION ═══════════
async function loadSubscription() {
    const res = await api('/api/subscription/status');
    if (!res||!res.ok) return;
    const sub = await res.json();

    const statusBadge = {trial:'badge-blue',trialing:'badge-blue',active:'badge-green',expired:'badge-red',cancelled:'badge-red',payment_failed:'badge-red'};
    let daysInfo = '';
    let trialDays = 0;
    if (['trial','trialing'].includes(sub.status)&&sub.trial_ends_at) { trialDays=Math.max(0,Math.ceil((new Date(sub.trial_ends_at)-new Date())/86400000)); daysInfo=`<span class="badge badge-yellow">${_dtf('days_left',trialDays)}</span>`; }
    else if (sub.status==='active'&&sub.subscription_expires_at) { const d=Math.max(0,Math.ceil((new Date(sub.subscription_expires_at)-new Date())/86400000)); daysInfo=`<span class="badge badge-green">${_dtf('renews_in',d)}</span>`; }

    // Show/hide trial notice banner
    const trialBanner = document.getElementById('trial-notice-banner');
    if(trialBanner) {
      if(['trial','trialing'].includes(sub.status)) { trialBanner.style.display='flex'; trialBanner.querySelector('span').textContent=_dtf('trial_notice',trialDays); }
      else { trialBanner.style.display='none'; }
    }

    document.getElementById('sub-current').innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px">
            <div><div style="font-size:.75em;color:var(--muted);text-transform:uppercase;font-weight:600">${_dt('sub_plan')}</div><div style="font-size:1.2em;font-weight:700;margin-top:4px">${PLAN_NAMES[sub.plan]||sub.plan}</div></div>
            <div><div style="font-size:.75em;color:var(--muted);text-transform:uppercase;font-weight:600">${_dt('sub_status')}</div><div style="margin-top:4px"><span class="badge ${statusBadge[sub.status]||'badge-muted'}">${sub.status}</span> ${daysInfo}</div></div>
            <div><div style="font-size:.75em;color:var(--muted);text-transform:uppercase;font-weight:600">${_dt('sub_agents')}</div><div style="font-size:1.2em;font-weight:700;margin-top:4px">${sub.current_agents} / ${sub.max_agents}</div></div>
            <div><div style="font-size:.75em;color:var(--muted);text-transform:uppercase;font-weight:600">${_dt('sub_features')}</div><div style="margin-top:4px;font-size:.82em">${sub.plan_features?.bulk_campaigns?'✅':'❌'} ${_dt('sub_campaigns')} • ${sub.plan_features?.google_drive?'✅':'❌'} ${_dt('sub_drive')} • ${sub.plan_features?.team_dashboard?'✅':'❌'} ${_dt('sub_team')}</div></div>
        </div>
        ${sub.pending_plan_change?`<div class="alert alert-warn" style="margin-top:16px"><span>📋</span><span>${_dt('scheduled')}: <strong>${PLAN_NAMES[sub.pending_plan_change.current_plan]} → ${PLAN_NAMES[sub.pending_plan_change.new_plan]}</strong></span><button class="btn btn-sm btn-outline" onclick="cancelPendingChange()" style="margin-left:auto">${_dt('cancel_change')}</button></div>`:''}
    `;

    // Plan cards
    const plans = [
        {key:'individual',name:_dt('plan_solo'),price:199,agents:1,feats:[_dt('pf_1advisor'),_dt('pf_unlimited_leads'),_dt('pf_all_calc'),_dt('pf_whatsapp'),_dt('pf_reports')]},
        {key:'team',name:_dt('plan_team'),price:799,agents:5,feats:[_dt('pf_5advisors'),_dt('pf_team_dash'),_dt('pf_campaigns'),_dt('pf_drive'),_dt('pf_transfer'),_dt('pf_all_solo')]},
        {key:'enterprise',name:_dt('plan_enterprise'),price:1999,agents:25,feats:[_dt('pf_25advisors'),_dt('pf_admin'),_dt('pf_branding'),_dt('pf_api'),_dt('pf_priority'),_dt('pf_all_team')]},
    ];
    const pending = sub.pending_plan_change;
    document.getElementById('plan-cards').innerHTML = plans.map(p=>{
        const isCur = sub.plan===p.key, isSched = pending?.new_plan===p.key;
        const isUp = PLAN_ORDER.indexOf(p.key) > PLAN_ORDER.indexOf(sub.plan);
        return `<div class="plan-card ${isCur?'current':''} ${isSched?'scheduled':''}" ${!isCur&&!isSched?`onclick="schedulePlanChange('${p.key}')"`:''}>
            ${isCur?`<div class="tag" style="background:var(--green);color:#fff">${_dt('current_plan')}</div>`:''}
            ${isSched?`<div class="tag" style="background:var(--saffron);color:#fff">${_dt('scheduled')}</div>`:''}
            <h4>${p.name}</h4>
            <div class="price">₹${p.price}<small>${_dt('per_month')}</small></div>
            <div class="features">${p.feats.map(f=>'✓ '+f).join('<br>')}</div>
            <div style="font-size:.78em;color:var(--muted)">${p.agents} ${p.agents>1?_dt('advisors_pl'):_dt('advisor_sg')}</div>
            ${!isCur&&!isSched?`<button class="btn ${isUp?'btn-primary':'btn-warn'}" style="margin-top:12px;width:100%">${isUp?_dt('upgrade_now'):_dt('schedule_downgrade')}</button>`:''}
        </div>`;
    }).join('');
}

async function schedulePlanChange(newPlan) {
    const isUp = PLAN_ORDER.indexOf(newPlan) > PLAN_ORDER.indexOf(STATE.plan);
    if (isUp) {
        if (!confirm(_dtf('plan_upgrade_q',PLAN_NAMES[newPlan]))) return;
        try {
            const t = STATE.tenant;
            const oRes = await api('/api/payments/create-order',{method:'POST',body:JSON.stringify({tenant_id:t.tenant_id,plan:newPlan})});
            if (!oRes||!oRes.ok) { const e=await oRes?.json(); alert(e?.detail||'Failed to create order'); return; }
            const order = await oRes.json();
            const pRes = await api('/api/payments/plans');
            const pData = await pRes.json();
            if (!pData.razorpay_key_id) { alert('Payments not configured'); return; }
            const opts = {
                key: pData.razorpay_key_id, amount: order.amount_paise, currency:'INR',
                name:'Sarathi-AI Business Technologies', description:PLAN_NAMES[newPlan]+' Plan',
                order_id: order.razorpay_order_id,
                handler: async function(r) {
                    const vRes = await api('/api/payments/verify',{method:'POST',body:JSON.stringify({tenant_id:t.tenant_id,plan:newPlan,razorpay_order_id:r.razorpay_order_id,razorpay_payment_id:r.razorpay_payment_id,razorpay_signature:r.razorpay_signature})});
                    if (vRes&&vRes.ok) { alert(_dt('upgrade_success')); location.reload(); } else { alert(_dt('payment_failed')); }
                },
                prefill:{name:t.owner_name||'',contact:t.phone||'',email:t.email||''}, theme:{color:'#0d9488'}
            };
            const rzp = new Razorpay(opts); rzp.open();
        } catch(e) { alert('Payment error: '+e.message); }
    } else {
        if (!confirm(_dtf('plan_downgrade_q',PLAN_NAMES[newPlan]))) return;
        const res = await api('/api/subscription/schedule-change',{method:'POST',body:JSON.stringify({new_plan:newPlan})});
        if (!res) return;
        const d = await res.json();
        if (d.error) { alert(d.error); return; }
        alert(d.message||_dt('change_scheduled'));
        loadSubscription(); loadOverview();
    }
}

async function cancelPendingChange() {
    if (!confirm(_dt('cancel_change_q'))) return;
    const res = await api('/api/subscription/pending-change',{method:'DELETE'});
    if (res&&res.ok) { document.getElementById('pending-change-banner').style.display='none'; loadSubscription(); loadOverview(); }
    else { const d=await res?.json(); alert(d?.error||'Failed'); }
}

// ═══════════ CSV IMPORT ═══════════
let _importParsed = [];

function showImportModal() {
    document.getElementById('import-file').value = '';
    document.getElementById('import-preview').style.display = 'none';
    document.getElementById('import-result').style.display = 'none';
    document.getElementById('import-btn').disabled = true;
    _importParsed = [];
    // Show agent assign dropdown for team plans
    const grp = document.getElementById('import-assign-group');
    if (isTeamPlan()) {
        grp.style.display = '';
        const sel = document.getElementById('import-assign-agent');
        sel.innerHTML = '<option value="">Auto (Owner)</option>';
        (STATE.agents||[]).forEach(a => { sel.innerHTML += `<option value="${a.agent_id}">${esc(a.name)}</option>`; });
    } else { grp.style.display = 'none'; }
    openModal('import-modal');
}

function parseCSV(text) {
    const lines = text.replace(/\r\n/g,'\n').replace(/\r/g,'\n').split('\n').filter(l=>l.trim());
    if (lines.length < 2) return [];
    // Handle BOM
    if (lines[0].charCodeAt(0) === 0xFEFF) lines[0] = lines[0].substring(1);
    const headers = lines[0].split(',').map(h=>h.trim().toLowerCase().replace(/[^a-z_]/g,''));
    const rows = [];
    for (let i=1; i<lines.length; i++) {
        const vals = lines[i].split(',');
        const obj = {};
        headers.forEach((h,j) => { obj[h] = (vals[j]||'').trim().replace(/^"|"$/g,''); });
        if (obj.name) rows.push(obj);
    }
    return rows;
}

function previewImport() {
    const file = document.getElementById('import-file').files[0];
    const preview = document.getElementById('import-preview');
    const result = document.getElementById('import-result');
    result.style.display = 'none';
    if (!file) { preview.style.display='none'; document.getElementById('import-btn').disabled=true; return; }
    const reader = new FileReader();
    reader.onload = function(e) {
        _importParsed = parseCSV(e.target.result);
        if (_importParsed.length === 0) {
            preview.style.display = 'none';
            document.getElementById('import-btn').disabled = true;
            alert('No valid rows found. Ensure the CSV has a header row with at least a "name" column.');
            return;
        }
        if (_importParsed.length > 500) {
            alert('Maximum 500 leads per import. Your file has ' + _importParsed.length + ' rows. Only the first 500 will be imported.');
            _importParsed = _importParsed.slice(0, 500);
        }
        // Show preview table
        const cols = ['name','phone','email','city','need_type','stage','source'];
        const available = cols.filter(c => _importParsed.some(r=>r[c]));
        let html = '<thead><tr>' + available.map(c=>'<th>'+esc(c)+'</th>').join('') + '</tr></thead><tbody>';
        _importParsed.slice(0,5).forEach(r => {
            html += '<tr>' + available.map(c=>'<td>'+esc(r[c]||'-')+'</td>').join('') + '</tr>';
        });
        html += '</tbody>';
        document.getElementById('import-preview-table').innerHTML = html;
        document.getElementById('import-stats').textContent = `Total: ${_importParsed.length} leads ready to import`;
        preview.style.display = '';
        document.getElementById('import-btn').disabled = false;
    };
    reader.readAsText(file, 'utf-8');
}

async function downloadTemplate() {
    try {
        const res = await api('/api/import/template');
        if (!res||!res.ok) { alert('Failed to download template'); return; }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href=url; a.download='sarathi_leads_template.csv'; a.click();
        URL.revokeObjectURL(url);
    } catch(e) { alert('Download failed: '+e.message); }
}

async function importLeads() {
    if (_importParsed.length === 0) return;
    const btn = document.getElementById('import-btn');
    btn.disabled = true; btn.textContent = 'Importing...';
    const resultDiv = document.getElementById('import-result');
    try {
        const assignTo = document.getElementById('import-assign-agent').value;
        const formData = new FormData();
        formData.append('file', document.getElementById('import-file').files[0]);
        const tok = localStorage.getItem('sarathi_token');
        const url = '/api/import/leads' + (assignTo ? '?assign_to='+assignTo : '');
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + tok },
            body: formData
        });
        if (!res) throw new Error('Network error');
        const d = await res.json();
        if (d.error) throw new Error(d.error);
        const imported = d.imported||0, skipped = d.skipped||0, dupes = d.duplicates||0;
        const total = imported + skipped + dupes;
        let html = `<strong>Import Complete!</strong><br>`;
        html += `✅ ${imported} imported`;
        if (dupes > 0) html += ` &nbsp;|&nbsp; 🔄 ${dupes} duplicates skipped`;
        if (skipped > 0) html += ` &nbsp;|&nbsp; ⚠️ ${skipped} errors`;
        if (d.errors && d.errors.length > 0) {
            html += '<div style="margin-top:8px;max-height:100px;overflow-y:auto;font-size:.82em;color:var(--muted)">';
            d.errors.slice(0,10).forEach(e => html += `<div>${esc(e)}</div>`);
            if (d.errors.length > 10) html += `<div>...and ${d.errors.length-10} more</div>`;
            html += '</div>';
        }
        resultDiv.style.background = imported > 0 ? '#ecfdf5' : '#fef2f2';
        resultDiv.style.color = imported > 0 ? '#065f46' : '#991b1b';
        resultDiv.innerHTML = html;
        resultDiv.style.display = '';
        if (imported > 0) loadLeads();
    } catch(e) {
        resultDiv.style.background = '#fef2f2'; resultDiv.style.color = '#991b1b';
        resultDiv.innerHTML = `<strong>Import Failed:</strong> ${esc(e.message)}`;
        resultDiv.style.display = '';
    } finally {
        btn.disabled = false; btn.textContent = 'Import Leads';
    }
}

// ═══════════ PROFILE & BRANDING ═══════════

async function loadProfile() {
    try {
        const res = await api('/api/profile');
        if (!res || !res.ok) return;
        const d = await res.json();
        if (!d || !d.agent) return;
        const a = d.agent, t = d.tenant;

        // Fill profile fields
        document.getElementById('prof-name').value = a.name || '';
        document.getElementById('prof-email').value = a.email || '';
        document.getElementById('prof-phone').value = a.phone || '';
        document.getElementById('prof-city').value = a.city || '';
        document.getElementById('prof-lang').value = a.lang || 'en';

        // Show branding section for owners
        if (a.role === 'owner' || a.role === 'admin') {
            document.getElementById('branding-section').style.display = '';
            document.getElementById('bot-info-section').style.display = '';
            document.getElementById('brand-firm').value = t.firm_name || '';
            document.getElementById('brand-tagline').value = t.brand_tagline || '';
            document.getElementById('brand-phone').value = t.brand_phone || '';
            document.getElementById('brand-email').value = t.brand_email || '';
            document.getElementById('brand-cta').value = t.brand_cta || '';

            // Colors
            const pc = t.brand_primary_color || '#1a56db';
            const ac = t.brand_accent_color || '#ea580c';
            document.getElementById('brand-primary-color').value = pc;
            document.getElementById('brand-primary-hex').textContent = pc;
            document.getElementById('brand-accent-color').value = ac;
            document.getElementById('brand-accent-hex').textContent = ac;
            document.getElementById('brand-primary-color').oninput = function(){ document.getElementById('brand-primary-hex').textContent = this.value; };
            document.getElementById('brand-accent-color').oninput = function(){ document.getElementById('brand-accent-hex').textContent = this.value; };

            // Credentials
            document.getElementById('brand-credentials').value = t.brand_credentials || '';

            // Logo
            if (t.brand_logo) {
                document.getElementById('brand-logo-preview').src = t.brand_logo;
                document.getElementById('brand-logo-preview').style.display = '';
                document.getElementById('brand-logo-delete').style.display = '';
            }

            // Bot info
            if (t.bot_username) {
                document.getElementById('bot-username').textContent = '@' + t.bot_username;
                document.getElementById('bot-status-badge').innerHTML = `<span style="color:#22c55e">${_dt('bot_active')}</span>`;
            } else {
                document.getElementById('bot-username').textContent = _dt('not_configured');
                document.getElementById('bot-status-badge').innerHTML = `<span style="color:#eab308">${_dt('bot_not_setup')}</span>`;
            }
        }

        // Update sidebar with firm name and logo
        if (t.firm_name) {
            document.getElementById('sidebar-brand-name').textContent = t.firm_name;
            document.getElementById('sidebar-logo-initial').textContent = t.firm_name.charAt(0).toUpperCase();
        }
        if (t.brand_logo) {
            document.getElementById('sidebar-logo').src = t.brand_logo;
            document.getElementById('sidebar-logo').style.display = '';
            document.getElementById('sidebar-logo-initial').style.display = 'none';
        } else {
            document.getElementById('sidebar-logo').style.display = 'none';
            document.getElementById('sidebar-logo-initial').style.display = 'flex';
        }
    } catch(e) { console.error('loadProfile error:', e); }
}

async function saveProfile() {
    const statusEl = document.getElementById('prof-status');
    statusEl.textContent = _dt('saving');
    statusEl.style.color = 'var(--muted)';
    try {
        const body = {
            name: document.getElementById('prof-name').value.trim(),
            email: document.getElementById('prof-email').value.trim(),
            phone: document.getElementById('prof-phone').value.trim(),
            city: document.getElementById('prof-city').value.trim(),
            lang: document.getElementById('prof-lang').value,
        };
        const r = await api('/api/profile', { method: 'PUT', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } });
        if (!r) { statusEl.textContent = _dt('session_expired'); statusEl.style.color = '#ef4444'; return; }
        if (!r.ok) {
            let detail = 'Failed (status ' + r.status + ')';
            try { const j = await r.json(); detail = Array.isArray(j.detail) ? j.detail.map(d=>d.msg).join(', ') : (j.detail || detail); } catch(_) {}
            statusEl.textContent = '❌ ' + detail;
            statusEl.style.color = '#ef4444';
            return;
        }
        const res = await r.json();
        if (res.status === 'ok') {
            statusEl.textContent = _dt('profile_saved');
            statusEl.style.color = '#22c55e';
            loadOverview();
        } else {
            statusEl.textContent = '❌ ' + (res.detail || 'Failed');
            statusEl.style.color = '#ef4444';
        }
    } catch(e) {
        statusEl.textContent = '❌ Error: ' + e.message;
        statusEl.style.color = '#ef4444';
    }
    setTimeout(() => { statusEl.textContent = ''; }, 4000);
}

async function saveBranding() {
    const statusEl = document.getElementById('brand-status');
    statusEl.textContent = _dt('saving');
    statusEl.style.color = 'var(--muted)';
    try {
        const body = {
            firm_name: document.getElementById('brand-firm').value.trim(),
            brand_tagline: document.getElementById('brand-tagline').value.trim(),
            brand_phone: document.getElementById('brand-phone').value.trim(),
            brand_email: document.getElementById('brand-email').value.trim(),
            brand_cta: document.getElementById('brand-cta').value.trim(),
            brand_primary_color: document.getElementById('brand-primary-color').value,
            brand_accent_color: document.getElementById('brand-accent-color').value,
            brand_credentials: document.getElementById('brand-credentials').value.trim(),
        };
        const r = await api('/api/tenant/branding', { method: 'PUT', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } });
        const res = r ? await r.json() : null;
        if (res && res.status === 'ok') {
            statusEl.textContent = _dt('branding_saved');
            statusEl.style.color = '#22c55e';
            // Update sidebar firm name
            if (body.firm_name) {
                document.getElementById('sidebar-brand-name').textContent = body.firm_name;
            }
        } else {
            statusEl.textContent = '❌ ' + (res?.detail || 'Failed');
            statusEl.style.color = '#ef4444';
        }
    } catch(e) {
        statusEl.textContent = '❌ Error: ' + e.message;
        statusEl.style.color = '#ef4444';
    }
    setTimeout(() => { statusEl.textContent = ''; }, 4000);
}

async function uploadLogo() {
    const fileInput = document.getElementById('brand-logo-file');
    if (!fileInput.files[0]) return;
    const file = fileInput.files[0];
    if (file.size > 2 * 1024 * 1024) { alert('Logo must be under 2MB'); return; }
    const fd = new FormData();
    fd.append('file', file);
    try {
        const r = await api('/api/tenant/logo', { method: 'POST', body: fd });
        const res = r ? await r.json() : null;
        if (res && res.url) {
            document.getElementById('brand-logo-preview').src = res.url;
            document.getElementById('brand-logo-preview').style.display = '';
            document.getElementById('brand-logo-delete').style.display = '';
            document.getElementById('sidebar-logo').src = res.url;
            document.getElementById('sidebar-logo').style.display = '';
            document.getElementById('sidebar-logo-initial').style.display = 'none';
        } else {
            alert('Upload failed: ' + (res?.detail || 'Unknown error'));
        }
    } catch(e) { alert('Upload error: ' + e.message); }
    fileInput.value = '';
}

async function deleteLogo() {
    if (!confirm('Remove firm logo?')) return;
    try {
        await api('/api/tenant/logo', { method: 'DELETE' });
        document.getElementById('brand-logo-preview').style.display = 'none';
        document.getElementById('brand-logo-delete').style.display = 'none';
        document.getElementById('brand-logo-preview').src = '';
        document.getElementById('sidebar-logo').src = '';
        document.getElementById('sidebar-logo').style.display = 'none';
        document.getElementById('sidebar-logo-initial').style.display = 'flex';
    } catch(e) { alert('Delete error: ' + e.message); }
}


// ═══════════ INIT ═══════════
applyDashI18n();
(function(){const lb=document.getElementById('topbar-lang-btn');if(lb)lb.textContent=_dlang==='en'?'हिंदी':'English';})();
loadOverview();
loadProfile();
setInterval(loadOverview, 120000);
