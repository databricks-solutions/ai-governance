#!/usr/bin/env bash
#
# One-step deploy of the Intelligent AI FinOps app to ANY Databricks workspace.
#
# It runs the three steps the bundle needs, in order:
#   1. build the React frontend  (npm ci && npm run build  -> ./dist)
#   2. databricks bundle deploy  (upload files + create the app resource)
#   3. databricks bundle run     (start the app)
# then prints the app URL.
#
# Everything workspace-specific is a bundle variable with a safe default, so a
# first deploy always comes up (features degrade gracefully until you grant them
# - see V2_SETUP.md). For a zero-prerequisite demo, deploy with demo mode on:
#   ./deploy.sh --profile <profile> --var demo_mode=true
#
# Usage:
#   ./deploy.sh --profile <profile> [--target prod] [--no-build] [--var k=v ...]
#
# Examples:
#   ./deploy.sh --profile my-workspace                       # build + deploy + run (target: prod)
#   ./deploy.sh --profile my-workspace --var demo_mode=true  # zero-setup offline demo
#   ./deploy.sh --profile my-workspace --no-build            # skip npm build (reuse ./dist)
#
# Prerequisites: Databricks CLI (>= v0.230), Node.js/npm (unless --no-build), and
# an authenticated profile (`databricks auth login --profile <profile>`).

set -euo pipefail

# Always run from the app directory (this script's location), so it works no
# matter where the caller invokes it from.
cd "$(dirname "$0")"

APP_NAME="intelligent-ai-finops-v2"      # the deployed Databricks App name
BUNDLE_RESOURCE="intelligent_ai_finops_v2"  # the resource key in databricks.yml

PROFILE=""
TARGET="prod"
BUILD=1
PASS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --target)  TARGET="${2:-}";  shift 2 ;;
    --no-build) BUILD=0; shift ;;
    --var) PASS+=(--var "${2:-}"); shift 2 ;;
    -h|--help)
      sed -n '2,29p' "$0"; exit 0 ;;
    --) shift; while [[ $# -gt 0 ]]; do PASS+=("$1"); shift; done ;;
    *) echo "Unknown argument: $1" >&2; echo "Run: ./deploy.sh --help" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROFILE" ]]; then
  echo "ERROR: --profile is required." >&2
  echo "Usage: ./deploy.sh --profile <profile> [--target prod] [--no-build] [--var k=v ...]" >&2
  exit 1
fi

echo "==> Intelligent AI FinOps deploy  (profile=$PROFILE, target=$TARGET)"

if [[ "$BUILD" -eq 1 ]]; then
  echo "==> [1/3] Building the frontend (npm ci && npm run build)"
  npm ci
  npm run build
else
  echo "==> [1/3] Skipping build (--no-build); reusing ./dist"
  if [[ ! -d dist ]]; then
    echo "ERROR: --no-build was set but ./dist does not exist. Run once without --no-build first." >&2
    exit 1
  fi
fi

echo "==> [2/3] Deploying the bundle"
databricks bundle deploy -t "$TARGET" --profile "$PROFILE" "${PASS[@]}"

echo "==> [3/3] Starting the app"
databricks bundle run "$BUNDLE_RESOURCE" -t "$TARGET" --profile "$PROFILE"

echo "==> Done. App URL:"
databricks apps get "$APP_NAME" --profile "$PROFILE" -o json \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('url','(deploy succeeded; check the workspace Apps page)'))" \
  2>/dev/null || echo "  (deploy succeeded; open the Apps page in your workspace to find the URL)"
