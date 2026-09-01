#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
source "$(dirname "$0")/_bootstrap.sh"; ensure_pydeps yaml

PROPOSALS_FILE="${PROPOSALS_FILE:-/tmp/ownership-proposals.json}"
CI_SYSTEM="${CI_SYSTEM:-github}"
RUN_ID="${RUN_ID:-manual}"
[[ -f "$PROPOSALS_FILE" ]] || { echo "No proposals file; nothing to do."; exit 0; }
COUNT=$(python3 -c "import json,sys;print(len(json.load(open(sys.argv[1]))))" "$PROPOSALS_FILE")
[[ "$COUNT" == "0" ]] && { echo "No ownerless skills to deprecate."; exit 0; }

git config user.email "ownership-health-bot@users.noreply.github.com"
git config user.name "ownership-health-bot"

python3 - "$PROPOSALS_FILE" << 'PYEOF' > /tmp/proposal_lines.txt
import json, sys
for p in json.load(open(sys.argv[1])):
    print(f"{p['name']}\t{p['removed_after']}\t{p['reason']}")
PYEOF

while IFS=$'\t' read -r NAME REMOVED_AFTER REASON; do
  [[ -z "$NAME" ]] && continue
  BRANCH="auto/deprecate-${NAME}-${RUN_ID}"
  if ! git check-ref-format "refs/heads/${BRANCH}"; then
    echo "WARNING: skipping '${NAME}' — invalid branch ref '${BRANCH}'" >&2
    continue
  fi
  git checkout -b "$BRANCH" main
  NAME="$NAME" REMOVED_AFTER="$REMOVED_AFTER" REASON="$REASON" python3 <<'PYEOF'
import os, yaml
reg = yaml.safe_load(open('config/registry.yaml')) or {'skills': []}
for s in reg.get('skills') or []:
    if s.get('name') == os.environ['NAME']:
        s['deprecated'] = True
        s['removed_after'] = os.environ['REMOVED_AFTER']
        s['deprecation_reason'] = os.environ['REASON']
        break
yaml.dump(reg, open('config/registry.yaml', 'w'), default_flow_style=False, sort_keys=False)
PYEOF
  git add config/registry.yaml
  git commit -m "chore: auto-propose deprecation of ownerless skill '${NAME}'

${REASON}. Removal after ${REMOVED_AFTER}. Reversible by closing this PR.

Co-authored-by: Isaac"

  TITLE="Auto-deprecate ownerless skill: ${NAME}"
  BODY="Automated proposal: \`${NAME}\` has no owner in governance.yaml (${REASON}). Sets deprecated=true, removed_after=${REMOVED_AFTER}. Reversible by closing this PR. Requires the same human review as any change."

  if [[ "$CI_SYSTEM" == "github" ]]; then
    git push -u origin "$BRANCH"
    gh pr create --base main --head "$BRANCH" --title "$TITLE" --body "$BODY" || \
      echo "WARNING: gh pr create failed for ${NAME}" >&2
  elif [[ "$CI_SYSTEM" == "ado" ]]; then
    # Build service pushes with System.AccessToken (mapped to ADO_TOKEN); origin is the ADO remote.
    git push -u origin "$BRANCH"   # persistCredentials:true on the ADO checkout pre-auths the push
    PAYLOAD=$(BRANCH="$BRANCH" TITLE="$TITLE" BODY="$BODY" python3 -c 'import json,os; print(json.dumps({"sourceRefName":"refs/heads/"+os.environ["BRANCH"],"targetRefName":"refs/heads/main","title":os.environ["TITLE"],"description":os.environ["BODY"]}))')
    curl -sf -X POST \
      "https://dev.azure.com/${ADO_ORG}/${ADO_PROJECT}/_apis/git/repositories/${ADO_REPO}/pullrequests?api-version=7.1" \
      -H "Content-Type: application/json" -H "Authorization: Bearer ${ADO_TOKEN}" \
      -d "$PAYLOAD" \
      >/dev/null || echo "WARNING: ADO PR create failed for ${NAME}" >&2
  fi
  git checkout main
done < /tmp/proposal_lines.txt
