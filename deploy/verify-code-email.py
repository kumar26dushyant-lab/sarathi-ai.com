"""Does the code email actually render?

It is built with %-formatting, and it now carries a URL and a button full of CSS. A stray % in
that CSS would raise at the moment somebody asks for a code - the one path where a failure means
a person is sitting on a screen unable to get in.

So the template is pulled out of the module and formatted, exactly as the sender does it.
"""
import ast
import io
import re
import sys

src = io.open("biz_nidaan_claim_access.py", encoding="utf-8").read()
tree = ast.parse(src)

# The one statement that builds the email body.
tmpl = None
for node in ast.walk(tree):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        try:
            left = ast.literal_eval(node.left)
        except Exception:
            continue
        if isinstance(left, str) and "Your code to open your claim page" in left:
            tmpl = left
            break

if tmpl is None:
    print("FAIL  could not find the code email template")
    sys.exit(1)

P = F = 0


def check(label, ok):
    global P, F
    if ok:
        P += 1
        print("  PASS  " + label)
    else:
        F += 1
        print("  FAIL  " + label)


print("\nThe email a person waiting on a screen receives\n")
URL = "https://nidaanpartner.com/nidaan/claim"
try:
    html = tmpl % ("GARVIT", "235522", 10, URL, URL)
    check("it renders at all", True)
except Exception as e:
    check("it renders at all (raised: %s)" % e, False)
    print("\n%d passed, %d failed" % (P, F))
    sys.exit(1)

check("the code is in it", "235522" in html)
check("and how long it lasts", "10 minutes" in html)
check("there is a link to the page where the code is typed", 'href="%s"' % URL in html)
check("the address is also written out, for a client that strips buttons",
      html.count(URL) >= 2)
check("it says the page is theirs, in both languages",
      "Open my claim page" in html and "क्लेम" in html)
check("it still warns that we never ask for the code",
      "never ask you for this code" in html)
# The link must NOT sign them in - the code is the security.
check("the link does not carry a token that would bypass the code",
      "token=" not in html and "magic" not in html)
check("no placeholder was left unfilled", "%s" not in html and "%d" not in html)

print("\n%d passed, %d failed" % (P, F))
sys.exit(1 if F else 0)
