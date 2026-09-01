#!/usr/bin/env bash
#
# Convenience deploy — picks the SQL warehouse for you so nobody has to hunt for an id.
#
# The documented two-command path still works and stays the source of truth:
#   databricks bundle deploy -t dev -p <profile> --var="warehouse_id=<id>" --var="catalog=<cat>"
#   databricks bundle run ai_governance_workshop_app -t dev -p <profile> --var=...
#
# This wrapper only removes the "which warehouse?" question: it selects the SMALLEST serverless
# SQL warehouse the caller can use (a serverless warehouse auto-starts on first query, so a
# stopped one is fine), then runs the same two commands. Everything else is identical.
#
# Usage:
#   ./deploy.sh -p <profile> -c <catalog> [-s <schema>] [-g <group>] [-t dev|prod] [-w <warehouse_id>] [-y]
#
#   -w  override the auto-pick with a specific warehouse id.
#   -y  pass --auto-approve to `bundle deploy` (needed only when the deploy plans a destructive
#       change, e.g. recreating a schema/volume). Use deliberately — it can drop data.
set -euo pipefail

PROFILE=""; CATALOG=""; SCHEMA=""; GROUP=""; TARGET="dev"; WID=""; AUTO=""
while getopts "p:c:s:g:t:w:y" opt; do
  case "$opt" in
    p) PROFILE=$OPTARG ;; c) CATALOG=$OPTARG ;; s) SCHEMA=$OPTARG ;;
    g) GROUP=$OPTARG ;; t) TARGET=$OPTARG ;; w) WID=$OPTARG ;; y) AUTO="--auto-approve" ;;
    *) echo "usage: ./deploy.sh -p <profile> -c <catalog> [-s schema] [-g group] [-t dev|prod] [-w warehouse_id] [-y]" >&2; exit 2 ;;
  esac
done
if [ -z "$PROFILE" ] || [ -z "$CATALOG" ]; then
  echo "usage: ./deploy.sh -p <profile> -c <catalog> [-s schema] [-g group] [-t dev|prod] [-w warehouse_id]" >&2
  exit 2
fi

if [ -z "$WID" ]; then
  echo "Selecting the smallest serverless SQL warehouse on profile '$PROFILE'..."
  # Rank serverless sizes smallest-first and take the first; a caller only sees warehouses it has
  # at least CAN_USE on, and the deploy grants the app CAN_USE too, so "visible" == usable here.
  WID=$(databricks warehouses list -p "$PROFILE" -o json | jq -r '
    def rank: {"2X-Small":0,"X-Small":1,"Small":2,"Medium":3,"Large":4,
               "X-Large":5,"2X-Large":6,"3X-Large":7,"4X-Large":8}[.] // 99;
    [ .[] | select(.enable_serverless_compute == true) | select((.state // "") != "DELETED") ]
      | sort_by(.cluster_size | rank) | (.[0].id // empty)')
  if [ -z "$WID" ]; then
    echo "No serverless SQL warehouse found on '$PROFILE'. Create one, or pass -w <id>." >&2
    exit 1
  fi
  echo "Using warehouse: $WID"
fi

VARS=(--var="warehouse_id=$WID" --var="catalog=$CATALOG")
[ -n "$SCHEMA" ] && VARS+=(--var="schema=$SCHEMA")
[ -n "$GROUP" ] && VARS+=(--var="workshop_group=$GROUP")

set -x
databricks bundle deploy -t "$TARGET" -p "$PROFILE" "${VARS[@]}" $AUTO
databricks bundle run ai_governance_workshop_app -t "$TARGET" -p "$PROFILE" "${VARS[@]}"
