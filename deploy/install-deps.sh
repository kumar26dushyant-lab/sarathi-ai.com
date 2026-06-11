#!/usr/bin/env bash
# Install Sarathi-AI Python dependencies on a fresh venv.
#
# Why this script exists:
#   moviepy 2.2.1's metadata declares pillow<12.0, but Pillow 12.2.0+ is
#   required to close 7 CVEs (CVE-2026-25990, 40192, 42309/10/11, PYSEC-2026-165).
#   The two work fine together at runtime — we just have to install in the
#   right order to side-step pip's resolver.
#
# Usage:
#   bash deploy/install-deps.sh /opt/sarathi/venv
#   bash deploy/install-deps.sh ./venv          # for local dev
#
# Pre-req: venv already created (python3.12 -m venv ./venv).

set -euo pipefail

VENV="${1:-/opt/sarathi/venv}"
PIP="$VENV/bin/pip"

if [ ! -x "$PIP" ]; then
  echo "✗ pip not found at $PIP"
  echo "  Create the venv first: python3.12 -m venv $VENV"
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
REQ="$REPO_ROOT/biz_requirements.txt"

if [ ! -f "$REQ" ]; then
  echo "✗ biz_requirements.txt not found at $REQ"
  exit 1
fi

echo "═══ Step 1: Install moviepy first (so its old-Pillow constraint doesn't trip the resolver) ═══"
"$PIP" install 'moviepy>=2.2.1'

echo
echo "═══ Step 2: Force-upgrade Pillow to the CVE-free version ═══"
"$PIP" install --upgrade 'Pillow>=12.2.0'

echo
echo "═══ Step 3: Install everything else from biz_requirements.txt ═══"
# --upgrade-strategy=only-if-needed (pip default since 21+) prevents
# downgrading Pillow back below 12.
"$PIP" install -r "$REQ"

echo
echo "═══ Verify ═══"
"$PIP" show Pillow moviepy 2>&1 | grep -E '^(Name|Version)'

echo
echo "═══ Run pip-audit for CVE check ═══"
"$PIP" install --quiet pip-audit
"$VENV/bin/pip-audit" --format=columns 2>&1 | head -10

echo
echo "✓ Dependency install complete."
