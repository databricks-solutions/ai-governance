#!/usr/bin/env bash
# Convenience wrapper around the Databricks CLI for the Unity AI Gateway labs bundle.
#
# Usage:
#   scripts/deploy.sh validate          # validate the bundle (no workspace changes)
#   scripts/deploy.sh deploy            # deploy endpoint + schema + job to the dev target
#   scripts/deploy.sh run               # run the "run core labs" job
#   scripts/deploy.sh destroy           # tear everything down
#
# Requires the Databricks CLI (>= 0.230) authenticated to a workspace, e.g. via
#   export DATABRICKS_HOST=... DATABRICKS_TOKEN=...   or a configured CLI profile.
set -euo pipefail

TARGET="${TARGET:-dev}"
cmd="${1:-validate}"

case "$cmd" in
  validate) databricks bundle validate -t "$TARGET" ;;
  deploy)   databricks bundle deploy   -t "$TARGET" ;;
  run)      databricks bundle run run_core_labs -t "$TARGET" ;;
  destroy)  databricks bundle destroy  -t "$TARGET" ;;
  *) echo "Unknown command: $cmd" >&2; exit 1 ;;
esac
