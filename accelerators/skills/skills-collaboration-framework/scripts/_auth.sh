# Shared Databricks auth resolution — SOURCE this, don't execute it.
#   source "$(dirname "$0")/_auth.sh"
#   resolve_auth_env          # populates the AUTH_ENV array (or exits 1 with a message)
#   env DATABRICKS_HOST="$WS" "${AUTH_ENV[@]}" databricks ...
#
# One definition of "how a script authenticates to a workspace", shared by sync-skills.sh
# and prune-deprecated.sh so the two can never disagree. OAuth M2M (CLIENT_ID + CLIENT_SECRET)
# is preferred — PATs are disabled on hardened workspaces — with a PAT (DATABRICKS_TOKEN) as
# the fallback where it's still enabled.
#
# Reads: DATABRICKS_TOKEN, DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET (from the environment).
# Sets:  AUTH_ENV (bash array of KEY=VALUE creds to pass through `env`).

resolve_auth_env() {
  if [[ -n "${DATABRICKS_TOKEN:-}" ]]; then
    AUTH_ENV=(DATABRICKS_TOKEN="$DATABRICKS_TOKEN")
  elif [[ -n "${DATABRICKS_CLIENT_ID:-}" && -n "${DATABRICKS_CLIENT_SECRET:-}" ]]; then
    AUTH_ENV=(DATABRICKS_CLIENT_ID="$DATABRICKS_CLIENT_ID" DATABRICKS_CLIENT_SECRET="$DATABRICKS_CLIENT_SECRET")
  else
    echo "ERROR: set DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET (OAuth M2M) or DATABRICKS_TOKEN (PAT)." >&2
    exit 1
  fi
}
