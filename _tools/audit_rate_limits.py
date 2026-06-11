"""Pre-flight audit for Sprint E.2 rate-limit additions.

For each target endpoint:
  - confirm it exists
  - confirm signature already has `request: Request`  (slowapi requirement)
  - confirm it doesn't ALREADY have @limiter.limit (avoid double-decoration)
"""
import re
import sys

SARATHI_BIZ = "/opt/sarathi/sarathi_biz.py"

TARGETS = [
    ("/nidaan/api/signup",                          "5/minute"),
    ("/nidaan/api/login",                           "10/minute"),
    ("/nidaan/ops/api/login",                       "5/minute"),
    ("/api/auth/telegram-login",                    "10/minute"),
    ("/nidaan/api/subscribe",                       "5/minute"),
    ("/nidaan/api/subscribe/recurring",             "5/minute"),
    ("/nidaan/api/subscribe/cancel",                "5/minute"),
    ("/nidaan/api/subscribe/verify",                "10/minute"),
    ("/nidaan/api/subscribe/recurring/verify",      "10/minute"),
    ("/nidaan/api/webhook",                         "60/minute"),
    ("/api/sa/restart-server",                      "2/minute"),
    ("/api/sa/tenants/bulk-activate",               "2/minute"),
    ("/api/sa/tenants/bulk-deactivate",             "2/minute"),
    ("/api/sa/tenants/bulk-plan",                   "2/minute"),
    ("/api/sa/tenant/{tenant_id}/impersonate",      "5/minute"),
    ("/api/sa/affiliate/{affiliate_id}/impersonate","5/minute"),
    ("/api/sa/events/bulk-resolve",                 "5/minute"),
    ("/api/sa/tenant/{tenant_id}/force-plan-change","5/minute"),
    ("/api/sa/tenant/{tenant_id}/bot/restart",      "5/minute"),
    ("/api/sa/agent/{agent_id}/toggle",             "10/minute"),
]

with open(SARATHI_BIZ, encoding="utf-8") as f:
    src = f.read()

for path, limit in TARGETS:
    epath = re.escape(path)
    pattern = (
        r'@app\.(get|post|put|patch|delete)\("' + epath + r'"[^\n]*\)\n'
        r'((?:@\w[^\n]*\n)*)'
        r'(?:async )?def (\w+)\(([\s\S]*?)\)\s*:'
    )
    m = re.search(pattern, src)
    if not m:
        print(f"  NOT FOUND: {path}")
        continue
    method = m.group(1).upper()
    decors = m.group(2)
    fn = m.group(3)
    params = m.group(4)
    already = "limiter.limit" in decors
    has_req = "request:" in params.replace(" ", "")
    status = "OK" if (has_req and not already) else ("ALREADY" if already else "NEEDS req: Request")
    print(f"  [{status:18}] {method:6} {path:55} | fn={fn:35} | limit={limit}")
