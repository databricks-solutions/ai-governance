#!/usr/bin/env bash
set -uo pipefail
PASS=0; FAIL=0
REPO_ROOT="$(git rev-parse --show-toplevel)"
check() { local d="$1" exp="$2" act="$3"; if [[ "$exp" == "$act" ]]; then echo "PASS: $d"; ((PASS++)); else echo "FAIL: $d (want '$exp' got '$act')"; ((FAIL++)); fi; }

OUT=$(python3 - "$REPO_ROOT" << 'PYEOF'
import sys, importlib.util, datetime
spec = importlib.util.spec_from_file_location("oh", sys.argv[1] + "/scripts/_ownership_health.py")
oh = importlib.util.module_from_spec(spec); spec.loader.exec_module(oh)
skills = [
  {"name": "fresh", "tier": 2, "owner": "a@x.com"},
  {"name": "stale", "tier": 3, "owner": "a@x.com"},
  {"name": "gone",  "tier": 2, "owner": "left@x.com"},
]
people = {"a@x.com"}
today = datetime.date(2026, 6, 18)
dates = {"fresh": datetime.date(2026, 6, 1),
         "stale": datetime.date(2025, 1, 1),
         "gone":  datetime.date(2026, 6, 1)}
r = oh.classify(skills, people, dates, today, {2: 180, 3: 90}, 30)
print("stale=" + ",".join(sorted(s["name"] for s in r["stale"])))
print("ownerless=" + ",".join(sorted(s["name"] for s in r["ownerless"])))
print("proposal_removed_after=" + (r["proposals"][0]["removed_after"] if r["proposals"] else ""))
PYEOF
)
check "stale list" "stale=stale" "$(echo "$OUT" | grep '^stale=')"
check "ownerless list" "ownerless=gone" "$(echo "$OUT" | grep '^ownerless=')"
check "grace = today+30d" "proposal_removed_after=2026-07-18" "$(echo "$OUT" | grep '^proposal_removed_after=')"

GOV_OUT=$(python3 - "$REPO_ROOT" << 'PYEOF'
import sys, importlib.util
spec = importlib.util.spec_from_file_location("oh", sys.argv[1] + "/scripts/_ownership_health.py")
oh = importlib.util.module_from_spec(spec); spec.loader.exec_module(oh)
result = oh.governance_people({"platform_team": ["A@X.com"], "tier2": {"stewards": {"p": ["b@x.com"]}}})
print(",".join(sorted(result)))
PYEOF
)
check "governance_people lowercases union" "a@x.com,b@x.com" "$GOV_OUT"

echo "Results: $PASS passed, $FAIL failed"; [[ $FAIL -eq 0 ]]
