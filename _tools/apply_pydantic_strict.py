"""Bulk-apply `model_config = ConfigDict(extra="forbid")` to every BaseModel
in sarathi_biz.py that doesn't already have it.

Safety:
- Only modifies class bodies that START with a non-config line (preserves
  models that already opt-in)
- Adds the config as the FIRST line of the class body, with 4-space indent
- Skips any class that already mentions `model_config` or `extra=`
- Skips Config (old pydantic v1) classes — those need manual review

Usage:
    python3 _tools/apply_pydantic_strict.py /path/to/sarathi_biz.py

Output:
    Writes modified file to /tmp/sarathi_biz_strict.py
    Reports list of touched models
"""
import re
import sys

if len(sys.argv) != 2:
    print("Usage: apply_pydantic_strict.py <path-to-sarathi_biz.py>")
    sys.exit(1)

src_path = sys.argv[1]
with open(src_path, encoding="utf-8") as f:
    src = f.read()

# Pattern: class FooReq(BaseModel): \n <body>
#   - Captures: name(group 1), base(group 2), body_indent(group 3), first_body_line(group 4)
#   - Body starts with at least 4 spaces of indent
CLASS_RE = re.compile(
    r"^class\s+(\w+)\s*\(\s*(BaseModel)\s*\)\s*:\s*\n"
    r"((?:    [^\n]*\n)+)",
    re.MULTILINE
)

touched = []
skipped_already_strict = []
skipped_v1_config = []

def replace(m):
    name = m.group(1)
    body = m.group(3)
    # Already has model_config or extra?
    if "model_config" in body or "extra=" in body or 'extra ' in body:
        skipped_already_strict.append(name)
        return m.group(0)
    # Has v1-style Config class?
    if re.search(r"^    class Config", body, re.MULTILINE):
        skipped_v1_config.append(name)
        return m.group(0)
    # Insert as first line of class body
    new_body = '    model_config = ConfigDict(extra="forbid")  # Sprint E.3\n' + body
    touched.append(name)
    return f"class {name}(BaseModel):\n{new_body}"

new_src = CLASS_RE.sub(replace, src)

out_path = "/tmp/sarathi_biz_strict.py"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(new_src)

print(f"Input:  {src_path}")
print(f"Output: {out_path}")
print(f"Models touched:               {len(touched)}")
print(f"Skipped (already strict):     {len(skipped_already_strict)}")
print(f"Skipped (v1 Config — review): {len(skipped_v1_config)}")
print()
if touched:
    print("Touched:")
    for n in sorted(touched):
        print(f"  + {n}")
if skipped_v1_config:
    print()
    print("Need manual review (v1 Config class detected):")
    for n in skipped_v1_config:
        print(f"  ! {n}")
