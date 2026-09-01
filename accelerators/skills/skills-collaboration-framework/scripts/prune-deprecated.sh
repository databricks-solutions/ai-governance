#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
HERE="$(dirname "$0")"
source "$HERE/_bootstrap.sh"; ensure_pydeps yaml
source "$HERE/_auth.sh"

DATABRICKS_HOST="${DATABRICKS_HOST:-}"
DRY_RUN="${DRY_RUN:-false}"
# --this-host-only: prune only from the workspace in DATABRICKS_HOST (per-env CI job, own SP).
# Mirrors sync-skills.sh so prune and sync use the same targeting.
THIS_HOST_ONLY="${THIS_HOST_ONLY:-false}"
for a in "$@"; do [[ "$a" == "--this-host-only" ]] && THIS_HOST_ONLY=true; done

if [[ -z "$DATABRICKS_HOST" ]]; then
  echo "ERROR: DATABRICKS_HOST must be set." >&2
  exit 1
fi

resolve_auth_env   # populates AUTH_ENV (OAuth M2M preferred, PAT fallback) or exits 1

TODAY=$(date +%Y-%m-%d)

SKILLS_TO_PRUNE=$(python3 - <<PYEOF
import yaml
from datetime import datetime

with open('config/registry.yaml') as f:
    reg = yaml.safe_load(f) or {'skills': []}

today = datetime.strptime('${TODAY}', '%Y-%m-%d')
for skill in reg.get('skills', []) or []:
    if not skill.get('deprecated'):
        continue
    removed_after = skill.get('removed_after')
    if not removed_after:
        continue
    if datetime.strptime(str(removed_after), '%Y-%m-%d') <= today:
        tier = skill.get('tier', 0)
        name = skill.get('name', '')
        domain = skill.get('domain', '')
        print(f"{tier}:{domain}:{name}")
PYEOF
)

if [[ -z "$SKILLS_TO_PRUNE" ]]; then
  echo "==> No deprecated skills past their removal date. Nothing to prune."
  exit 0
fi

echo "==> Skills to prune:"
echo "$SKILLS_TO_PRUNE"

# Resolve skills_path once (the same for every skill); the per-skill targets come from the
# shared resolver so prune removes from exactly the workspaces sync published to.
SKILLS_PATH=$(python3 "$HERE/_workspaces.py" skills-path)

while IFS=: read -r tier domain name; do
  [[ -z "$name" ]] && continue

  # Skills are flat under skills_path. Remove the skill from EVERY workspace it was synced to —
  # _workspaces.py is the ONE place that maps tier/domain -> URLs (shared with sync-skills.sh).
  # Unmapped here is skip-with-warning (not fatal): the skill's mapping may have been removed
  # from workspaces.json before its deprecation was pruned.
  if ! TARGET_URLS=$(python3 "$HERE/_workspaces.py" targets "$tier" "$domain" 2>/dev/null); then
    echo "WARNING: no target workspaces for tier=${tier} domain=${domain} — skipping '${name}'" >&2
    continue
  fi

  # Per-env job: keep only this workspace. If DATABRICKS_HOST isn't a target for this skill's
  # tier/domain, there's nothing to prune here — skip quietly (another env's job handles it).
  if [[ "$THIS_HOST_ONLY" == "true" ]]; then
    TARGET_URLS=$(TARGETS="$TARGET_URLS" HOST="$DATABRICKS_HOST" python3 -c "
import os
host=os.environ['HOST'].rstrip('/')
print('\n'.join(u for u in os.environ['TARGETS'].splitlines() if u.strip().rstrip('/')==host))
")
    [[ -z "$TARGET_URLS" ]] && continue
  fi

  WS_SKILL_REL="${SKILLS_PATH}/${name}"
  while IFS= read -r WS_URL; do
    [[ -z "$WS_URL" ]] && continue
    echo "==> Pruning: ${WS_URL}${WS_SKILL_REL}"
    if [[ "$DRY_RUN" == "true" ]]; then
      echo "[DRY RUN] databricks workspace delete ${WS_SKILL_REL} --recursive (host=${WS_URL})"
    else
      env DATABRICKS_HOST="$WS_URL" "${AUTH_ENV[@]}" \
        databricks workspace delete "$WS_SKILL_REL" --recursive 2>&1 || \
        echo "WARNING: Could not delete ${WS_URL}${WS_SKILL_REL} (may already be absent)" >&2
      echo "==> Pruned: ${WS_URL}${WS_SKILL_REL}"
    fi
  done <<< "$TARGET_URLS"
done <<< "$SKILLS_TO_PRUNE"

echo "==> Prune job complete."
