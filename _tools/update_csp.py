"""Update nginx CSP header — Sprint E.3b.

Adds: frame-ancestors 'self', form-action 'self', upgrade-insecure-requests,
and 'self' to frame-src (fixes microsite preview iframe).
Keeps unsafe-inline/unsafe-eval (removal needs nonce refactor — separate project).

Run on the server:  python3 /tmp/update_csp.py
"""
import shutil
import datetime

PATH = "/etc/nginx/sites-available/sarathi"

bak = PATH + ".bak." + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
shutil.copy(PATH, bak)
print("Backup:", bak)

with open(PATH) as f:
    content = f.read()

OLD = ("frame-src https://api.razorpay.com https://accounts.google.com; "
       "object-src 'none'; base-uri 'self';")

NEW = ("frame-src 'self' https://api.razorpay.com https://accounts.google.com; "
       "frame-ancestors 'self'; form-action 'self'; "
       "object-src 'none'; base-uri 'self'; upgrade-insecure-requests;")

count = content.count(OLD)
if count == 0:
    print("WARNING: target substring not found — NO CHANGE. Manual review needed.")
elif count > 1:
    print(f"WARNING: target found {count} times — ambiguous. NO CHANGE. Manual review.")
else:
    content = content.replace(OLD, NEW)
    with open(PATH, "w") as f:
        f.write(content)
    print("CSP updated successfully (1 occurrence replaced):")
    print("  + frame-src 'self'  (fixes microsite preview)")
    print("  + frame-ancestors 'self'")
    print("  + form-action 'self'")
    print("  + upgrade-insecure-requests")
