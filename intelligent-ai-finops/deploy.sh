#!/usr/bin/env bash
#
# One-step deploy (and optional live wiring) of the Intelligent AI FinOps app.
#
# Deploy only:
#   ./deploy.sh --profile <profile>                        # build + deploy + run + URL
#   ./deploy.sh --profile <profile> --var demo_mode=true   # zero-setup offline demo
#   ./deploy.sh --profile <profile> --no-build             # reuse ./dist
#
# Full LIVE setup in one shot (deploy + grant the app SP + readiness + smoke test):
#   ./deploy.sh --profile <profile> --warehouse-id <id> --grant-embedding --check --smoke
#
# Flags:
#   --profile <p>            (required) Databricks CLI profile = target workspace
#   --target <t>             bundle target (default: prod)
#   --no-build               skip npm build, reuse ./dist
#   --var k=v                extra bundle variable (repeatable), passed through
#   --warehouse-id <id>      set warehouse_id var AND grant the app SP CAN_USE on it
#   --grant-embedding [name] grant the app SP CAN_QUERY on the embedding endpoint
#                            (default name: databricks-gte-large-en)
#   --check                  after deploy, GET /api/setup/readiness and print it
#   --smoke                  after deploy, POST a finops-auto call and print the receipt
#   -h | --help
#
# The one step this cannot script: the first-login OAuth consent (model-serving + sql).
# The script prints the app URL so you can approve it in the browser. Grants are
# best-effort (a warning, not a failure, if you lack permission on that object).
#
# Prerequisites: Databricks CLI, Node/npm (unless --no-build), an authenticated profile,
# and (for --check/--smoke) an OAuth-capable profile so `databricks auth token` works.

set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="intelligent-ai-finops-v2"
BUNDLE_RESOURCE="intelligent_ai_finops_v2"

PROFILE=""; TARGET="prod"; BUILD=1
WAREHOUSE_ID=""; GRANT_EMB=0; EMB_NAME="databricks-gte-large-en"
DO_CHECK=0; DO_SMOKE=0
PASS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --target)  TARGET="${2:-}";  shift 2 ;;
    --no-build) BUILD=0; shift ;;
    --var) PASS+=(--var "${2:-}"); shift 2 ;;
    --warehouse-id) WAREHOUSE_ID="${2:-}"; shift 2 ;;
    --grant-embedding)
      GRANT_EMB=1
      if [[ $# -ge 2 && "${2:0:2}" != "--" ]]; then EMB_NAME="$2"; shift 2; else shift; fi ;;
    --check) DO_CHECK=1; shift ;;
    --smoke) DO_SMOKE=1; shift ;;
    -h|--help) sed -n '2,31p' "$0"; exit 0 ;;
    --) shift; while [[ $# -gt 0 ]]; do PASS+=("$1"); shift; done ;;
    *) echo "Unknown argument: $1" >&2; echo "Run: ./deploy.sh --help" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROFILE" ]]; then
  echo "ERROR: --profile is required." >&2
  echo "Usage: ./deploy.sh --profile <profile> [--target prod] [--no-build] [--var k=v] \\" >&2
  echo "                   [--warehouse-id <id>] [--grant-embedding [name]] [--check] [--smoke]" >&2
  exit 1
fi

# --warehouse-id also drives the bundle var so the app reads live cost data.
[[ -n "$WAREHOUSE_ID" ]] && PASS+=(--var "warehouse_id=$WAREHOUSE_ID")

echo "==> Intelligent AI FinOps deploy  (profile=$PROFILE, target=$TARGET)"

if [[ "$BUILD" -eq 1 ]]; then
  echo "==> [1/3] Building the frontend (npm ci && npm run build)"
  npm ci
  npm run build
else
  echo "==> [1/3] Skipping build (--no-build); reusing ./dist"
  [[ -d dist ]] || { echo "ERROR: --no-build set but ./dist is missing. Run once without --no-build." >&2; exit 1; }
fi

echo "==> [2/3] Deploying the bundle"
databricks bundle deploy -t "$TARGET" --profile "$PROFILE" "${PASS[@]}"

echo "==> [3/3] Starting the app"
databricks bundle run "$BUNDLE_RESOURCE" -t "$TARGET" --profile "$PROFILE"

# ---- discover the app URL + its service principal -------------------------
INFO=$(databricks apps get "$APP_NAME" --profile "$PROFILE" -o json 2>/dev/null || echo '{}')
APP_URL=$(echo "$INFO" | python3 -c "import sys,json;print(json.load(sys.stdin).get('url',''))" 2>/dev/null || true)
APP_SP=$(echo "$INFO" | python3 -c "import sys,json;print(json.load(sys.stdin).get('service_principal_client_id',''))" 2>/dev/null || true)
echo "==> App URL: ${APP_URL:-<open the workspace Apps page to find it>}"
[[ -n "$APP_SP" ]] && echo "==> App service principal: $APP_SP"

# ---- optional live grants (best-effort) -----------------------------------
_grant() { local label="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "==> [grant] $label: OK"
  else echo "==> [grant] $label: could not apply (you may lack permission on that object; grant it manually)"; fi; }

if [[ -n "$WAREHOUSE_ID" && -n "$APP_SP" ]]; then
  _grant "warehouse $WAREHOUSE_ID -> CAN_USE" \
    databricks permissions update warehouses "$WAREHOUSE_ID" \
      --json "{\"access_control_list\":[{\"service_principal_name\":\"$APP_SP\",\"permission_level\":\"CAN_USE\"}]}" \
      --profile "$PROFILE"
fi
if [[ "$GRANT_EMB" -eq 1 && -n "$APP_SP" ]]; then
  _grant "$EMB_NAME -> CAN_QUERY" \
    databricks serving-endpoints update-permissions "$EMB_NAME" \
      --json "{\"access_control_list\":[{\"service_principal_name\":\"$APP_SP\",\"permission_level\":\"CAN_QUERY\"}]}" \
      --profile "$PROFILE"
fi

# ---- the one non-scriptable step ------------------------------------------
echo
echo "==> ACTION REQUIRED (browser, one time): open the app and approve the consent"
echo "    for the model-serving + sql scopes so live calls run on your behalf:"
echo "      ${APP_URL:-<app URL above>}"

_token() { databricks auth token -p "$PROFILE" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null || true; }

# ---- optional readiness check ---------------------------------------------
if [[ "$DO_CHECK" -eq 1 && -n "$APP_URL" ]]; then
  echo "==> [check] /api/setup/readiness"
  TOK=$(_token)
  curl -sS "$APP_URL/api/setup/readiness" -H "Authorization: Bearer $TOK" | python3 -m json.tool \
    || echo "    (readiness call failed - approve the consent above, then retry)"
fi

# ---- optional live smoke test ---------------------------------------------
if [[ "$DO_SMOKE" -eq 1 && -n "$APP_URL" ]]; then
  echo "==> [smoke] finops-auto test call"
  TOK=${TOK:-$(_token)}
  curl -sS "$APP_URL/v1/chat/completions" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
    -d '{"model":"finops-auto","messages":[{"role":"user","content":"Design an optimal Spark SQL plan for a 50TB skewed join."}]}' \
    | python3 -c "import sys,json;d=json.load(sys.stdin);f=d.get('x_finops',{});print('    routed:',d.get('model'),'| cost:',f.get('costUsd'),'| saved%:',f.get('savingsPct'))" \
    || echo "    (smoke call failed - approve the consent above, then retry)"
fi

echo "==> Done."
