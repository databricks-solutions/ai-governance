#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
source "$(dirname "$0")/_bootstrap.sh"; ensure_pydeps yaml

SKILL_FILE="${1:-}"
PR_NUMBER="${2:-}"
CI_SYSTEM="${CI_SYSTEM:-ado}"   # ado is the live CI here; the github path is kept for vendor portability
REPORT_FILE="${REPORT_FILE:-}"   # if set, append a markdown eval report (CI surfaces it as a build/step summary)
MIN_EVAL_SCORE="${MIN_EVAL_SCORE:-0.8}"   # advisory threshold — see EVAL_GATE_MODE for how a below-threshold score is handled
EVAL_GATE_MODE="${EVAL_GATE_MODE:-advisory}"   # global default | advisory | human-review | auto-drop — what a below-threshold eval_score does
# Per-tier override (spec §16.3 recommends advisory@T2, blocking@T3). If EVAL_GATE_MODE_T2 /
# EVAL_GATE_MODE_T3 is set, it wins for that tier; otherwise the global EVAL_GATE_MODE applies.
# The effective mode is resolved from the skill's tier once SKILL_FILE is validated (below).
EVAL_GATE_MODE_T2="${EVAL_GATE_MODE_T2:-}"
EVAL_GATE_MODE_T3="${EVAL_GATE_MODE_T3:-}"
DATABRICKS_HOST="${DATABRICKS_HOST:-}"
DATABRICKS_TOKEN="${DATABRICKS_TOKEN:-}"
DATABRICKS_CLIENT_ID="${DATABRICKS_CLIENT_ID:-}"
DATABRICKS_CLIENT_SECRET="${DATABRICKS_CLIENT_SECRET:-}"
AI_ENDPOINT_NAME="${AI_ENDPOINT_NAME:-}"

# Decide the build outcome from the eval verdict + score, honoring EVAL_GATE_MODE.
#   - verdict "fail" (any dimension < 0.5) is a HARD gate: blocks in every mode.
#   - a below-threshold eval_score is handled by mode:
#       advisory     (default) — warn only, never blocks (the verdict still governs)
#       human-review           — warn + emit a "::needs-human-review::" marker, does not block
#       auto-drop              — block the build (exit 1)
# Returns 0 = allow, 1 = block. Pure decision logic — no endpoint needed — so it is unit-tested
# directly via the `--gate-decision <score> [verdict]` dry path below.
gate_decision() {
  local score="$1" verdict="${2:-pass}" mode="${EVAL_GATE_MODE:-advisory}" min="${MIN_EVAL_SCORE:-0.8}"
  if [[ "$verdict" == "fail" ]]; then
    echo "ERROR: AI review verdict is FAIL — blocking (hard gate, applies in every mode)." >&2
    return 1
  fi
  # Below the advisory threshold?
  if python3 -c "import sys; sys.exit(0 if float('$score') < float('$min') else 1)"; then
    case "$mode" in
      auto-drop)
        echo "AUTO-DROP: eval_score ${score} is below the ${min} threshold — blocking build (EVAL_GATE_MODE=auto-drop)." >&2
        return 1 ;;
      human-review)
        echo "::needs-human-review:: eval_score ${score} is below the ${min} threshold — requires steward sign-off (EVAL_GATE_MODE=human-review)."
        return 0 ;;
      advisory|*)
        echo "ADVISORY: eval_score ${score} is below the ${min} threshold (non-blocking — verdict governs; EVAL_GATE_MODE=${mode})."
        return 0 ;;
    esac
  fi
  return 0
}

# Resolve the effective gate mode for a tier: EVAL_GATE_MODE_T{2,3} wins if set, else the global
# EVAL_GATE_MODE. Echoes the mode. (Tier 1 never reaches AI review, so only 2/3 are meaningful.)
resolve_gate_mode() {
  local tier="$1"
  case "$tier" in
    2) echo "${EVAL_GATE_MODE_T2:-$EVAL_GATE_MODE}" ;;
    3) echo "${EVAL_GATE_MODE_T3:-$EVAL_GATE_MODE}" ;;
    *) echo "$EVAL_GATE_MODE" ;;
  esac
}

# Tier of a skill from its path (tier2/… → 2, tier3/… → 3), for per-tier mode resolution.
tier_from_path() {
  case "$1" in
    tier2/*|*/tier2/*) echo 2 ;;
    tier3/*|*/tier3/*) echo 3 ;;
    *) echo 0 ;;
  esac
}

# Unit-testable dry path: decide the gate from a stubbed score/verdict with no AI call.
# Optional 4th arg = tier (2/3) so per-tier mode resolution is testable without an endpoint.
if [[ "${1:-}" == "--gate-decision" ]]; then
  if [[ -n "${4:-}" ]]; then EVAL_GATE_MODE="$(resolve_gate_mode "$4")"; fi
  if gate_decision "${2:-0}" "${3:-pass}"; then exit 0; else exit 1; fi
fi

if [[ -z "$SKILL_FILE" || ! -f "$SKILL_FILE" ]]; then
  echo "Usage: ai-review.sh <path/to/SKILL.md> [pr_number]" >&2
  exit 1
fi

# Resolve the per-tier effective mode for this skill and reassign EVAL_GATE_MODE so every
# downstream consumer (gate_decision, the report band) sees the tier-specific mode.
SKILL_TIER="$(tier_from_path "$SKILL_FILE")"
EVAL_GATE_MODE="$(resolve_gate_mode "$SKILL_TIER")"
echo "==> Gate mode for Tier ${SKILL_TIER}: ${EVAL_GATE_MODE}"

# Graceful fallback: advisory mode when host/endpoint or any auth credential is missing.
HAVE_AUTH=false
[[ -n "$DATABRICKS_TOKEN" ]] && HAVE_AUTH=true
[[ -n "$DATABRICKS_CLIENT_ID" && -n "$DATABRICKS_CLIENT_SECRET" ]] && HAVE_AUTH=true
if [[ -z "$DATABRICKS_HOST" || "$HAVE_AUTH" != "true" || -z "$AI_ENDPOINT_NAME" ]]; then
  echo "WARNING: need DATABRICKS_HOST, AI_ENDPOINT_NAME, and a credential (DATABRICKS_TOKEN, or DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET)." >&2
  echo "ai-review: ADVISORY — skipped (no endpoint configured)"
  exit 0
fi

# Resolve a Bearer token. PAT is used directly; OAuth M2M client creds are exchanged for a
# short-lived access token at the workspace OIDC endpoint (PATs are disabled on hardened workspaces).
BEARER="$DATABRICKS_TOKEN"
if [[ -z "$BEARER" ]]; then
  echo "==> Exchanging OAuth M2M client credentials for an access token..."
  TOK_BODY=$(mktemp)
  TOK_STATUS=$(curl -sS -o "$TOK_BODY" -w '%{http_code}' --request POST "${DATABRICKS_HOST%/}/oidc/v1/token" \
    --user "${DATABRICKS_CLIENT_ID}:${DATABRICKS_CLIENT_SECRET}" \
    --data 'grant_type=client_credentials&scope=all-apis' || echo "000")
  if [[ "$TOK_STATUS" != "200" ]]; then
    # Surface the failure loudly — a wrong/expired DATABRICKS_CLIENT_SECRET lands here (HTTP 401).
    echo "ERROR: OAuth M2M token exchange failed (HTTP ${TOK_STATUS})." >&2
    echo "       Check DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET. Response:" >&2
    head -c 300 "$TOK_BODY" >&2; echo >&2
    rm -f "$TOK_BODY"
    exit 1
  fi
  BEARER=$(python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' < "$TOK_BODY")
  rm -f "$TOK_BODY"
  if [[ -z "$BEARER" ]]; then
    echo "ERROR: token endpoint returned 200 but no access_token." >&2
    exit 1
  fi
fi

ENDPOINT_URL="${DATABRICKS_HOST%/}/serving-endpoints/${AI_ENDPOINT_NAME}/invocations"

# Build the request body safely. The SKILL content is read INSIDE python from a file
# path passed via env — never interpolated into a shell-quoted string (that was the
# original quoting bug, since the prompt contains quotes, braces, and newlines).
REQUEST_BODY=$(SKILL_FILE="$SKILL_FILE" python3 <<'PYEOF'
import json, os
skill = open(os.environ['SKILL_FILE']).read()
instructions = (
  "You are the governance reviewer for a Databricks Genie Code skill file (SKILL.md).\n"
  "Score three dimensions 0.0-1.0. Evaluate each dimension against EVERY listed criterion, and "
  "write the note so it states how each criterion fared.\n\n"
  "clarity:\n"
  "  (a) the description names concrete triggers/keywords a router can match;\n"
  "  (b) scope is unambiguous — clear what the skill does AND does not cover;\n"
  "  (c) neither so broad it would over-trigger nor so narrow it never loads.\n"
  "safety:\n"
  "  (a) no secrets, tokens, or credentials embedded;\n"
  "  (b) no PII or sensitive-data exposure;\n"
  "  (c) no destructive or state-changing instructions (read-only intent);\n"
  "  (d) any queries/commands scoped to least privilege.\n"
  "format:\n"
  "  (a) frontmatter contains ONLY name + description;\n"
  "  (b) frontmatter is valid, parseable YAML;\n"
  "  (c) the description is a reasonable length (roughly 1-3 sentences).\n\n"
  "Scoring: a dimension reaches 1.0 only if ALL its criteria are met; deduct for each criterion "
  "missed. eval_score = the MINIMUM of the three dimension scores. verdict = \"fail\" if any "
  "dimension scores below 0.5, otherwise \"pass\". Keep notes and summary concise.\n\n"
  "SKILL.md content:\n" + skill
)
# A small, low-cost model (e.g. databricks-claude-haiku-4-5) is plenty for a markdown review.
# response_format=json_schema forces a clean, structured object — no prose, no code fences.
schema = {
  "type": "object",
  "properties": {
    "verdict": {"type": "string", "enum": ["pass", "fail"]},
    "eval_score": {"type": "number"},
    "dimensions": {
      "type": "object",
      "properties": {
        "clarity": {"type": "object", "properties": {"score": {"type": "number"}, "note": {"type": "string"}}},
        "safety":  {"type": "object", "properties": {"score": {"type": "number"}, "note": {"type": "string"}}},
        "format":  {"type": "object", "properties": {"score": {"type": "number"}, "note": {"type": "string"}}},
      },
    },
    "summary": {"type": "string"},
  },
  "required": ["verdict", "eval_score", "dimensions", "summary"],
}
print(json.dumps({"messages": [{"role": "user", "content": instructions}],
                  "max_tokens": 700, "temperature": 0.0,
                  "response_format": {"type": "json_schema",
                                      "json_schema": {"name": "skill_eval", "schema": schema}}}))
PYEOF
)

echo "==> Calling AI gateway: ${AI_ENDPOINT_NAME}..."
RESPONSE=$(curl -sf \
  -H "Authorization: Bearer ${BEARER}" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_BODY" \
  "$ENDPOINT_URL") || {
  echo "WARNING: AI gateway call failed (network/auth error). Running advisory mode." >&2
  exit 0
}

# Parse verdict/score/rationale once. Response is passed via env (not argv) and we
# tolerate models that wrap JSON in prose or use a non-OpenAI envelope.
PARSED=$(RESPONSE="$RESPONSE" python3 <<'PYEOF'
import json, os, re
resp = json.loads(os.environ['RESPONSE'])

def _flatten(c):
    # content may be a plain string, or a list of parts. Reasoning models (e.g. gpt-oss)
    # return [{type:'reasoning',summary:[...]}, {type:'text',text:'...'}] — keep text parts.
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        out = [p['text'] for p in c
               if isinstance(p, dict) and isinstance(p.get('text'), str)]
        return '\n'.join(out)
    return ''

content = ''
try:
    content = _flatten(resp['choices'][0]['message']['content'])
except Exception:
    preds = resp.get('predictions')
    if isinstance(preds, list) and preds:
        content = preds[0] if isinstance(preds[0], str) else json.dumps(preds[0])
    else:
        content = _flatten(resp.get('content', ''))

def _dim(d, k):
    v = (d.get('dimensions') or {}).get(k) or {}
    try:    s = float(v.get('score', 0.0))
    except Exception: s = 0.0
    return {'score': s, 'note': str(v.get('note', ''))}

out = {'verdict': 'fail', 'eval_score': 0.0,
       'dimensions': {k: {'score': 0.0, 'note': ''} for k in ('clarity', 'safety', 'format')},
       'summary': 'Unable to parse AI review response.'}
try:
    m = re.search(r'\{.*\}', content, re.DOTALL)
    r = json.loads(m.group(0)) if m else json.loads(content)
    dims = {k: _dim(r, k) for k in ('clarity', 'safety', 'format')}
    out['dimensions'] = dims
    # Trust the model's eval_score if present, else derive it as the min of dimension scores.
    out['eval_score'] = float(r['eval_score']) if 'eval_score' in r else min(d['score'] for d in dims.values())
    out['verdict'] = r.get('verdict') or ('fail' if any(d['score'] < 0.5 for d in dims.values()) else 'pass')
    out['summary'] = str(r.get('summary', '')) or out['summary']
except Exception:
    pass
print(json.dumps(out))
PYEOF
)

VERDICT=$(echo "$PARSED"   | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])")
EVAL_SCORE=$(echo "$PARSED" | python3 -c "import json,sys; print(json.load(sys.stdin)['eval_score'])")

echo "==> Verdict: ${VERDICT}  Score: ${EVAL_SCORE}"
echo "$PARSED" | python3 -c "import json,sys; d=json.load(sys.stdin); print('==> Dimensions: ' + ', '.join(f\"{k} {v['score']}\" for k,v in d['dimensions'].items())); print('==> Summary:', d['summary'])"

# Resolve skill name from frontmatter (file path via env — no interpolation).
SKILL_NAME=$(SKILL_FILE="$SKILL_FILE" python3 <<'PYEOF'
import re, yaml, os
content = open(os.environ['SKILL_FILE']).read()
m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
print(yaml.safe_load(m.group(1)).get('name', '') if m else '')
PYEOF
)

# eval_score is surfaced in the build report + build tags on merge (see azure-pipelines.yml
# "Report eval_score" step) — never written back to registry.yaml, since main is branch-protected
# and CI cannot push to it. The build is the durable record of the score.

# Render the structured verdict as a markdown block (verdict, score, per-dimension table, summary).
# Built once from PARSED and reused for both the build report and the PR comment.
BODY_MD=$(PARSED="$PARSED" SKILL_NAME="$SKILL_NAME" VERDICT="$VERDICT" EVAL_SCORE="$EVAL_SCORE" \
          AI_ENDPOINT_NAME="$AI_ENDPOINT_NAME" MIN_EVAL_SCORE="$MIN_EVAL_SCORE" \
          EVAL_GATE_MODE="$EVAL_GATE_MODE" python3 <<'PYEOF'
import json, os
d = json.loads(os.environ['PARSED'])
name = os.environ['SKILL_NAME']; verdict = os.environ['VERDICT']
score = os.environ['EVAL_SCORE']; endpoint = os.environ['AI_ENDPOINT_NAME']
threshold = os.environ['MIN_EVAL_SCORE']
mode = os.environ.get('EVAL_GATE_MODE', 'advisory')
icon = '✅' if verdict == 'pass' else '❌'
try:    below = float(score) < float(threshold)
except Exception: below = False
if below and mode == 'auto-drop':
    band = f"⛔ below threshold ({threshold}) — BLOCKING (gate mode: auto-drop)"
elif below and mode == 'human-review':
    band = f"⚠️ below threshold ({threshold}) — needs human review (gate mode: human-review)"
elif below:
    band = f"⚠️ below advisory threshold ({threshold}) — non-blocking, please review"
else:
    band = f"✓ meets advisory threshold ({threshold})"
lines = [
    f"## AI Skill Review — `{name}`", "",
    f"**Verdict:** {icon} {verdict}  |  **eval_score:** {score}/1.0  |  {band}", "",
    "| Dimension | Score | Notes |", "|-----------|-------|-------|",
]
for k in ('clarity', 'safety', 'format'):
    dim = d['dimensions'].get(k, {})
    note = str(dim.get('note', '')).replace('|', '\\|').replace('\n', ' ')
    lines.append(f"| {k.capitalize()} | {dim.get('score', 0.0)} | {note} |")
lines += ["", f"**Summary:** {d.get('summary','')}", "",
          f"*Reviewed by `{endpoint}` via Databricks AI Gateway. eval_score = min of the dimension "
          f"scores. Hard gate = verdict (any dimension below 0.5 fails); the {threshold} threshold is "
          f"handled per EVAL_GATE_MODE='{mode}' (advisory = warn, human-review = warn + flag, "
          "auto-drop = block). On merge the score is recorded in the build's report, not committed "
          "back to the protected branch.*"]
print("\n".join(lines))
PYEOF
)

# Optional vendor-neutral eval report. On merge, CI surfaces this instead of committing the
# score back to a protected branch (ADO build summary / GitHub step summary). Append-mode so
# multiple changed skills accumulate into one report.
if [[ -n "$REPORT_FILE" ]]; then
  { echo "$BODY_MD"; echo ""; } >> "$REPORT_FILE"
  echo "==> Appended eval_score report for ${SKILL_NAME} to ${REPORT_FILE}"
fi

# Post PR comment (when a PR number is supplied). Never writes the branch.
if [[ -n "$PR_NUMBER" ]]; then
  COMMENT="$BODY_MD"

  if [[ "$CI_SYSTEM" == "github" ]] && command -v gh >/dev/null 2>&1; then
    gh pr comment "$PR_NUMBER" --body "$COMMENT" 2>/dev/null || \
      echo "WARNING: Could not post GitHub PR comment (check GH_TOKEN)" >&2
  elif [[ "$CI_SYSTEM" == "ado" ]]; then
    ADO_ORG="${ADO_ORG:-cedricboisvert}"
    ADO_PROJECT="${ADO_PROJECT:-cicd-demo}"
    ADO_REPO="${ADO_REPO:-skills-collaboration-framework}"
    ADO_TOKEN="${ADO_TOKEN:-}"   # Azure DevOps token — set to $(System.AccessToken) in the pipeline.
    if [[ -z "$ADO_TOKEN" ]]; then
      echo "WARNING: ADO_TOKEN not set — skipping ADO PR comment. Map \$(System.AccessToken) → ADO_TOKEN." >&2
    else
      COMMENT_JSON=$(COMMENT="$COMMENT" python3 -c "import json,os; print(json.dumps(os.environ['COMMENT']))")
      # System.AccessToken is an OAuth bearer token; if you use a classic ADO PAT instead,
      # switch to: -H "Authorization: Basic $(printf ':%s' "$ADO_TOKEN" | base64)"
      curl -sf -X POST \
        "https://dev.azure.com/${ADO_ORG}/${ADO_PROJECT}/_apis/git/repositories/${ADO_REPO}/pullRequests/${PR_NUMBER}/threads?api-version=7.1" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${ADO_TOKEN}" \
        -d "{\"comments\": [{\"content\": ${COMMENT_JSON}, \"commentType\": 1}], \"status\": 1}" \
        >/dev/null 2>&1 || echo "WARNING: Could not post ADO PR comment (check ADO_TOKEN + build-service 'Contribute to PRs' permission)" >&2
    fi
  fi
fi

# Final gate: verdict is the unconditional hard gate; EVAL_GATE_MODE governs the advisory threshold.
if gate_decision "$EVAL_SCORE" "$VERDICT"; then
  exit 0
else
  exit 1
fi
