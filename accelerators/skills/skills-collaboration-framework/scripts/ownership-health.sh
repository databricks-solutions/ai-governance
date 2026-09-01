#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
source "$(dirname "$0")/_bootstrap.sh"; ensure_pydeps yaml

REPORT_FILE="${REPORT_FILE:-ownership-health-report.md}"
PROPOSALS_FILE="${PROPOSALS_FILE:-/tmp/ownership-proposals.json}"
T2_INTERVAL_DAYS="${T2_INTERVAL_DAYS:-180}"
T3_INTERVAL_DAYS="${T3_INTERVAL_DAYS:-90}"
GRACE_DAYS="${GRACE_DAYS:-30}"
TODAY="$(date +%Y-%m-%d)"

# Gather last-commit date per skill folder (YYYY-MM-DD) into a name=date list.
# Empty (never-committed) folders are treated as fresh (no date -> not stale).
DATES=""
while IFS= read -r skill_md; do
  [[ -z "$skill_md" ]] && continue
  folder="$(dirname "$skill_md")"
  name="$(basename "$folder")"
  d="$(git log -1 --format=%cd --date=short -- "$folder" 2>/dev/null || true)"
  [[ -n "$d" ]] && DATES+="${name}=${d}"$'\n'
done < <(find tier2 tier3 -name SKILL.md 2>/dev/null)

# Run the classifier; render the report and the proposals file.
REPORT="$(DATES="$DATES" TODAY="$TODAY" T2="$T2_INTERVAL_DAYS" T3="$T3_INTERVAL_DAYS" \
          GRACE="$GRACE_DAYS" PROPOSALS_FILE="$PROPOSALS_FILE" python3 <<'PYEOF'
import os, json, yaml, datetime, importlib.util
spec = importlib.util.spec_from_file_location("oh", "scripts/_ownership_health.py")
oh = importlib.util.module_from_spec(spec); spec.loader.exec_module(oh)

reg = yaml.safe_load(open('config/registry.yaml')) or {'skills': []}
skills = reg.get('skills') or []

gov = yaml.safe_load(open('config/governance.yaml')) if os.path.exists('config/governance.yaml') else {}
people = oh.governance_people(gov)

dates = {}
for line in os.environ['DATES'].splitlines():
    if '=' in line:
        k, v = line.split('=', 1)
        dates[k] = datetime.date.fromisoformat(v)

today = datetime.date.fromisoformat(os.environ['TODAY'])
intervals = {2: int(os.environ['T2']), 3: int(os.environ['T3'])}
result = oh.classify(skills, people, dates, today, intervals, int(os.environ['GRACE']))
json.dump(result['proposals'], open(os.environ['PROPOSALS_FILE'], 'w'))
print(oh.render_report(result, today))
PYEOF
)"

printf '%s\n' "$REPORT" | tee "$REPORT_FILE"
echo "==> Proposals written to ${PROPOSALS_FILE}"
