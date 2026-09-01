#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
ERRORS=0

for cmd in markdownlint yamllint gitleaks; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: $cmd not found. Install it first." >&2
    exit 1
  fi
done

echo "==> markdownlint on SKILL.md files..."
SKILL_FILES=$(find tier1 tier2 tier3 -name 'SKILL.md' 2>/dev/null | sort || true)
if [[ -n "$SKILL_FILES" ]]; then
  echo "$SKILL_FILES" | xargs markdownlint --config .markdownlint.yaml || ERRORS=$((ERRORS + 1))
fi

echo "==> yamllint on config/registry.yaml..."
yamllint -c .yamllint.yaml config/registry.yaml || ERRORS=$((ERRORS + 1))

echo "==> JSON validation on config/workspaces.json..."
# workspaces.json is JSON, not YAML — validate as JSON (yamllint mis-flags JSON style).
python3 -m json.tool config/workspaces.json >/dev/null || {
  echo "ERROR: config/workspaces.json is not valid JSON." >&2
  ERRORS=$((ERRORS + 1))
}

echo "==> gitleaks secret scan..."
gitleaks detect --source . --no-git --redact 2>&1 || {
  echo "ERROR: gitleaks detected potential secrets." >&2
  ERRORS=$((ERRORS + 1))
}

if [[ $ERRORS -gt 0 ]]; then
  echo "==> FAILED: $ERRORS lint/scan check(s) failed." >&2
  exit 1
fi
echo "==> lint-and-scan: all checks passed."
