#!/usr/bin/env bash
# Installs a local pre-commit hook that runs gitleaks before every commit.
# This is a SECOND line of defense — GitHub Actions catches things after push,
# this catches them BEFORE push, saving you from publishing a secret even briefly.
#
# Usage (from repo root):  bash deploy/install-precommit-hook.sh
# Uninstall:               rm .git/hooks/pre-commit
#
# Requires: gitleaks installed locally
#   Windows: https://github.com/gitleaks/gitleaks/releases (download .zip, add to PATH)
#   macOS:   brew install gitleaks
#   Linux:   apt install gitleaks   OR   download from GitHub releases

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_PATH="$REPO_ROOT/.git/hooks/pre-commit"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "✗ gitleaks not found in PATH."
  echo "  Install from: https://github.com/gitleaks/gitleaks/releases"
  echo "  Or: brew install gitleaks   (macOS)"
  echo "      apt install gitleaks    (Linux)"
  echo "      scoop install gitleaks  (Windows)"
  exit 1
fi

cat > "$HOOK_PATH" <<'HOOK'
#!/usr/bin/env bash
# Auto-installed pre-commit hook — runs gitleaks on staged changes only.
# Bypass for emergencies:  git commit --no-verify
# (Only bypass if you're CERTAIN there are no secrets. Better: fix the leak.)

set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
CONFIG="$REPO_ROOT/.gitleaks.toml"

# Use --staged to scan only what's about to be committed (fast, accurate)
if ! gitleaks protect --staged --config "$CONFIG" --redact --verbose; then
  echo
  echo "✗ gitleaks detected a possible secret in your staged changes."
  echo "  Review the lines above. If they're false positives, add them to"
  echo "  .gitleaks.toml [allowlist] and retry. If they're real secrets:"
  echo "    1. Unstage the file:  git restore --staged <file>"
  echo "    2. Remove the secret value from the file"
  echo "    3. Move the secret to biz.env (and ensure biz.env is .gitignored)"
  echo "    4. Re-stage and commit"
  echo
  exit 1
fi
HOOK

chmod +x "$HOOK_PATH"
echo "✓ Pre-commit hook installed at $HOOK_PATH"
echo "  Test it: stage a file with a fake key and try to commit."
echo "  Bypass once (NOT RECOMMENDED): git commit --no-verify"
