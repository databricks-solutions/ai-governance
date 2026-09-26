#!/usr/bin/env bash
#
# Roll back / tear down the Intelligent AI FinOps app deployment.
#
# This is the inverse of deploy.sh: it runs `databricks bundle destroy`, which
# removes everything the bundle created in the target workspace - the app
# (intelligent-ai-finops-v2) and the uploaded source files - so you can redeploy
# a completely clean slate (e.g. to re-record a demo from the first-deploy moment).
#
# Usage:
#   ./rollback.sh --profile <profile> [--target prod] [--yes]
#
#   --profile <p>   (required) Databricks CLI profile = target workspace
#   --target <t>    bundle target (default: prod) - must match what you deployed
#   --yes | -y      skip the confirmation prompt (non-interactive / CI)
#   -h | --help
#
# Notes:
#   - bundle destroy prompts for confirmation unless --yes is passed.
#   - After teardown, re-deploy with deploy.sh. A fresh deploy creates a NEW app
#     service principal, so re-run deploy.sh with --warehouse-id/--grant-embedding
#     to re-grant it (the old grants become harmless dangling references).
#   - This does not delete the serverless warehouse, model, or embedding endpoints
#     (those are workspace resources the app only *uses*, not bundle-managed).

set -euo pipefail
cd "$(dirname "$0")"

PROFILE=""; TARGET="prod"; ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --target)  TARGET="${2:-}";  shift 2 ;;
    --yes|-y)  ASSUME_YES=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; echo "Run: ./rollback.sh --help" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROFILE" ]]; then
  echo "ERROR: --profile is required." >&2
  echo "Usage: ./rollback.sh --profile <profile> [--target prod] [--yes]" >&2
  exit 1
fi

echo "==> Rolling back Intelligent AI FinOps  (profile=$PROFILE, target=$TARGET)"
echo "    This DELETES the app 'intelligent-ai-finops-v2' and the bundle-uploaded"
echo "    files in the workspace. Warehouse / model / embedding endpoints are left"
echo "    untouched (the app only uses them)."

if [[ "$ASSUME_YES" -eq 1 ]]; then
  databricks bundle destroy -t "$TARGET" --profile "$PROFILE" --auto-approve
else
  databricks bundle destroy -t "$TARGET" --profile "$PROFILE"
fi

echo "==> Rollback complete. Re-deploy a clean slate with:"
echo "      ./deploy.sh --profile $PROFILE --warehouse-id <id> --grant-embedding --check --smoke"
