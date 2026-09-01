#!/usr/bin/env bash
set -euo pipefail
CI_SYSTEM="${CI_SYSTEM:-ado}"   # ado is the live CI here; the github path is kept for vendor portability

if [[ "$CI_SYSTEM" == "ado" ]]; then
  : "${ADO_ORG:?}"; : "${ADO_PROJECT:?}"; : "${ADO_REPO:?}"; : "${ADO_TOKEN:?}"
  # ADO_AUTH selects the auth scheme: 'bearer' (default — CI's $(System.AccessToken) OAuth token)
  # or 'pat' (a classic Personal Access Token, which must be sent as HTTP Basic ':<pat>').
  ADO_AUTH="${ADO_AUTH:-bearer}"
  if [[ "$ADO_AUTH" == "pat" ]]; then
    ADO_AUTH_HEADER="Authorization: Basic $(printf ':%s' "$ADO_TOKEN" | base64)"
  else
    ADO_AUTH_HEADER="Authorization: Bearer ${ADO_TOKEN}"
  fi
  RID=$(curl -sf -H "$ADO_AUTH_HEADER" \
    "https://dev.azure.com/${ADO_ORG}/${ADO_PROJECT}/_apis/git/repositories/${ADO_REPO}?api-version=7.1" \
    | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
  OK=$(RID="$RID" ADO_ORG="$ADO_ORG" ADO_PROJECT="$ADO_PROJECT" ADO_AUTH_HEADER="$ADO_AUTH_HEADER" python3 <<'PYEOF'
import os, json, urllib.request
url=f"https://dev.azure.com/{os.environ['ADO_ORG']}/{os.environ['ADO_PROJECT']}/_apis/policy/configurations?api-version=7.1"
hk, hv = os.environ['ADO_AUTH_HEADER'].split(': ', 1)
req=urllib.request.Request(url, headers={hk: hv})
cfgs=json.load(urllib.request.urlopen(req)).get('value', [])
rid=os.environ['RID']
def on_main_for_repo(c):
    for s in c.get('settings', {}).get('scope', []):
        if s.get('repositoryId') in (rid, None) and (s.get('refName') or '') == 'refs/heads/main':
            return True
    return False
build = any(c.get('isEnabled') and c.get('isBlocking') and on_main_for_repo(c)
            and c.get('type', {}).get('displayName') == 'Build' for c in cfgs)
print('yes' if build else 'no')
PYEOF
)
  if [[ "$OK" != "yes" ]]; then
    echo "ERROR: main has no blocking Build-validation policy. Run scripts/setup-branch-protection.sh." >&2
    exit 1
  fi
  echo "==> Branch protection OK (blocking build validation on main)."
elif [[ "$CI_SYSTEM" == "github" ]]; then
  : "${GH_REPO:?}"; : "${GH_TOKEN:?}"
  ENF=$(curl -sf -H "Authorization: Bearer ${GH_TOKEN}" \
    "https://api.github.com/repos/${GH_REPO}/branches/main/protection" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print('yes' if d.get('required_pull_request_reviews',{}).get('require_code_owner_reviews') else 'no')" 2>/dev/null || echo "no")
  if [[ "$ENF" != "yes" ]]; then
    echo "ERROR: main lacks 'Require review from Code Owners'. Run scripts/setup-branch-protection.sh." >&2
    exit 1
  fi
  echo "==> Branch protection OK (Code Owner reviews required on main)."
fi
