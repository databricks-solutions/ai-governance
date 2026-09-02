#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
HERE="$(dirname "$0")"
source "$HERE/_bootstrap.sh"; ensure_pydeps yaml
source "$HERE/_auth.sh"

# --this-host-only restricts the sync to the single workspace named by DATABRICKS_HOST, even when
# the tier resolves to several (e.g. the Tier-3 fan-out). Each per-environment CI job then
# authenticates with its OWN service principal (from its own variable group) and publishes only to
# its own workspace — no shared credential, true least-privilege. Strip the flag from anywhere in
# the args so the remaining positionals are still <tier> [domain].
THIS_HOST_ONLY="${THIS_HOST_ONLY:-false}"
ARGS=()
for a in "$@"; do
  if [[ "$a" == "--this-host-only" ]]; then THIS_HOST_ONLY=true; else ARGS+=("$a"); fi
done
set -- "${ARGS[@]:-}"

TIER="${1:-}"
DOMAIN="${2:-}"
DATABRICKS_HOST="${DATABRICKS_HOST:-}"
DRY_RUN="${DRY_RUN:-false}"

if [[ -z "$TIER" ]]; then
  echo "Usage: sync-skills.sh <tier> [domain] [--this-host-only]" >&2
  echo "  Tier 2 requires domain (e.g. 'platform'). Tier 3 does not." >&2
  echo "  --this-host-only: publish only to the workspace in DATABRICKS_HOST (per-env CI job)." >&2
  exit 1
fi

if [[ -z "$DATABRICKS_HOST" ]]; then
  echo "ERROR: DATABRICKS_HOST must be set." >&2
  exit 1
fi

resolve_auth_env   # populates AUTH_ENV (OAuth M2M preferred, PAT fallback) or exits 1

# Skills always land FLAT at skills_path; the tier/domain resolver (_workspaces.py) is the ONE
# place that maps a tier/domain to its target workspace URLs — shared with prune-deprecated.sh
# so sync and prune can never disagree about where a skill lives.
SKILLS_PATH=$(python3 "$HERE/_workspaces.py" skills-path)

# Missing tier/domain mapping is FATAL for sync (a skill would silently reach no workspace).
TARGET_URLS=$(python3 "$HERE/_workspaces.py" targets "$TIER" "$DOMAIN") || {
  echo "ERROR: could not resolve target workspaces for tier ${TIER}${DOMAIN:+ domain $DOMAIN}." >&2
  exit 1
}

# Restrict to this job's own workspace when asked. If DATABRICKS_HOST isn't one of the tier's
# targets, that's a config error (this job would sync nothing) — fail loudly rather than silently.
if [[ "$THIS_HOST_ONLY" == "true" ]]; then
  TARGET_URLS=$(TARGETS="$TARGET_URLS" HOST="$DATABRICKS_HOST" python3 -c "
import os
host=os.environ['HOST'].rstrip('/')
keep=[u for u in os.environ['TARGETS'].splitlines() if u.strip().rstrip('/')==host]
print('\n'.join(keep))
")
  if [[ -z "$TARGET_URLS" ]]; then
    echo "ERROR: --this-host-only set, but DATABRICKS_HOST ($DATABRICKS_HOST) is not among the tier ${TIER} targets in workspaces.json." >&2
    exit 1
  fi
fi

# SOURCE is the tier/domain folder in the repo; its skill subfolders are copied into
# SKILLS_PATH, so a skill lands at SKILLS_PATH/{skill}/ (flat — no tier/domain nesting).
if [[ "$TIER" == "2" ]]; then
  SOURCE_DIR="tier2/${DOMAIN}"
else
  SOURCE_DIR="tier3"
fi

if [[ ! -d "$SOURCE_DIR" ]] || [[ -z "$(find "$SOURCE_DIR" -name 'SKILL.md' 2>/dev/null | head -1)" ]]; then
  echo "WARNING: No SKILL.md files found in ${SOURCE_DIR} — nothing to sync."
  exit 0
fi

# Stage the source into a temp dir and strip repo-only governance artifacts so they never reach
# the runtime skills folder. TESTS.yaml (per-skill regression tests) lives beside SKILL.md in Git
# but is NOT a runtime skill resource — Genie Code should only see the skill's own files.
STAGE_DIR=$(mktemp -d)
trap 'rm -rf "$STAGE_DIR"' EXIT
cp -R "$SOURCE_DIR/." "$STAGE_DIR/"
# Repo-only files to exclude from the workspace (extend this list as new governance artifacts appear).
# TESTS.yaml = per-skill regression tests (not a runtime resource); .gitkeep = empty-dir placeholder.
find "$STAGE_DIR" \( -name 'TESTS.yaml' -o -name '.gitkeep' \) -delete

# Import to each target workspace. AUTH_ENV must be valid for every URL in TARGET_URLS. With
# --this-host-only that's exactly one workspace (this per-env job's own SP); without it, the
# credential must be entitled in every listed workspace (an account-level SP).
while IFS= read -r WS_URL; do
  [[ -z "$WS_URL" ]] && continue
  echo "==> Syncing ${SOURCE_DIR} (staged, governance artifacts stripped) → ${WS_URL}${SKILLS_PATH}"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY RUN] databricks workspace import-dir <staged ${SOURCE_DIR}> ${SKILLS_PATH} --overwrite (host=${WS_URL})"
    continue
  fi
  env DATABRICKS_HOST="$WS_URL" "${AUTH_ENV[@]}" \
    databricks workspace import-dir "$STAGE_DIR" "$SKILLS_PATH" --overwrite || {
    echo "ERROR: import-dir failed for ${WS_URL}" >&2
    exit 1
  }
  echo "==> Sync complete: ${SOURCE_DIR} → ${WS_URL}${SKILLS_PATH}"
done <<< "$TARGET_URLS"
