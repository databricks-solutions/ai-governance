#!/usr/bin/env bash
set -euo pipefail
CI_SYSTEM="${CI_SYSTEM:-ado}"   # ado is the live CI here; the github path is kept for vendor portability

if [[ "$CI_SYSTEM" == "ado" ]]; then
  : "${ADO_ORG:?}"; : "${ADO_PROJECT:?}"; : "${ADO_REPO:?}"; : "${ADO_TOKEN:?}"; : "${ADO_BUILD_DEF_ID:?}"
  # ADO_AUTH: 'bearer' (default — CI OAuth token) or 'pat' (classic PAT, sent as HTTP Basic).
  # Running this by hand you'll typically use a PAT: export ADO_AUTH=pat.
  ADO_AUTH="${ADO_AUTH:-bearer}"
  if [[ "$ADO_AUTH" == "pat" ]]; then
    ADO_AUTH_HEADER="Authorization: Basic $(printf ':%s' "$ADO_TOKEN" | base64)"
  else
    ADO_AUTH_HEADER="Authorization: Bearer ${ADO_TOKEN}"
  fi
  if CI_SYSTEM=ado ADO_ORG="$ADO_ORG" ADO_PROJECT="$ADO_PROJECT" ADO_REPO="$ADO_REPO" \
     ADO_TOKEN="$ADO_TOKEN" ADO_AUTH="$ADO_AUTH" bash scripts/check-branch-protection.sh >/dev/null 2>&1; then
    echo "==> ADO build-validation policy already present on main — nothing to do."
    exit 0
  fi
  RID=$(curl -sf -H "$ADO_AUTH_HEADER" \
    "https://dev.azure.com/${ADO_ORG}/${ADO_PROJECT}/_apis/git/repositories/${ADO_REPO}?api-version=7.1" \
    | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
  curl -sf -X POST \
    "https://dev.azure.com/${ADO_ORG}/${ADO_PROJECT}/_apis/policy/configurations?api-version=7.1" \
    -H "Content-Type: application/json" -H "$ADO_AUTH_HEADER" \
    -d "{\"isEnabled\":true,\"isBlocking\":true,\"type\":{\"id\":\"0609b952-1397-4640-95ec-e00a01b2c241\"},\"settings\":{\"buildDefinitionId\":${ADO_BUILD_DEF_ID},\"displayName\":\"Skills CI (PR validation)\",\"manualQueueOnly\":false,\"queueOnSourceUpdateOnly\":true,\"validDuration\":0,\"scope\":[{\"repositoryId\":\"${RID}\",\"refName\":\"refs/heads/main\",\"matchKind\":\"Exact\"}]}}" \
    >/dev/null && echo "==> Created blocking build-validation policy on main."
elif [[ "$CI_SYSTEM" == "github" ]]; then
  : "${GH_REPO:?}"; : "${GH_TOKEN:?}"
  curl -sf -X PUT \
    "https://api.github.com/repos/${GH_REPO}/branches/main/protection" \
    -H "Authorization: Bearer ${GH_TOKEN}" -H "Accept: application/vnd.github+json" \
    -d '{"required_status_checks":null,"enforce_admins":true,"required_pull_request_reviews":{"require_code_owner_reviews":true,"required_approving_review_count":1},"restrictions":null}' \
    >/dev/null && echo "==> Enabled Code-Owner-review protection on main."
fi
