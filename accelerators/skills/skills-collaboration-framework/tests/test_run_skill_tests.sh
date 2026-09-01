#!/usr/bin/env bash
# Tests for the per-skill regression harness (scripts/_run_skill_tests.py).
set -uo pipefail
PASS=0; FAIL=0
REPO_ROOT="$(git rev-parse --show-toplevel)"
SCRIPT="$REPO_ROOT/scripts/_run_skill_tests.py"

assert_exit() {
  local desc="$1" expected="$2"; shift 2
  "$@" >/dev/null 2>&1
  local actual=$?
  if [[ $actual -eq $expected ]]; then
    echo "PASS: $desc"; ((PASS++))
  else
    echo "FAIL: $desc (expected exit $expected, got $actual)"; ((FAIL++))
  fi
}

SKILL_MD='---
name: cost-skill
description: A T2 cost skill.
---
## Query
```sql
SELECT sku_name, SUM(usage_quantity) FROM system.billing.usage GROUP BY 1
```
'

# Test: expect_tables satisfied → passes
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/tier2/analytics/cost-skill"
printf '%s' "$SKILL_MD" > "$TMPDIR/tier2/analytics/cost-skill/SKILL.md"
cat > "$TMPDIR/tier2/analytics/cost-skill/TESTS.yaml" << 'EOF'
tests:
  - name: uses-billing
    trigger: "spend by sku?"
    expect_tables: [system.billing.usage]
EOF
assert_exit "expect_tables satisfied passes" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: expected table missing → exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/tier2/analytics/cost-skill"
printf '%s' "$SKILL_MD" > "$TMPDIR/tier2/analytics/cost-skill/SKILL.md"
cat > "$TMPDIR/tier2/analytics/cost-skill/TESTS.yaml" << 'EOF'
tests:
  - name: needs-jobs
    trigger: "job costs?"
    expect_tables: [system.lakeflow.jobs]
EOF
assert_exit "missing expected table exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: forbidden table referenced → exits 1 (guardrail violation)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/tier2/analytics/cost-skill"
printf '%s' "$SKILL_MD" > "$TMPDIR/tier2/analytics/cost-skill/SKILL.md"
cat > "$TMPDIR/tier2/analytics/cost-skill/TESTS.yaml" << 'EOF'
tests:
  - name: no-billing-allowed
    trigger: "anything"
    forbid_tables: [system.billing.usage]
EOF
assert_exit "forbidden table referenced exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: forbidden table absent → passes (negative guardrail holds)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/tier2/analytics/cost-skill"
printf '%s' "$SKILL_MD" > "$TMPDIR/tier2/analytics/cost-skill/SKILL.md"
cat > "$TMPDIR/tier2/analytics/cost-skill/TESTS.yaml" << 'EOF'
tests:
  - name: never-touches-hr
    trigger: "anything"
    forbid_tables: [main.hr.employees]
EOF
assert_exit "forbidden table absent passes" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: no TESTS.yaml → advisory-untested, still passes (incremental adoption)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/tier2/analytics/cost-skill"
printf '%s' "$SKILL_MD" > "$TMPDIR/tier2/analytics/cost-skill/SKILL.md"
assert_exit "skill without TESTS.yaml passes (advisory)" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: empty test case (neither expect nor forbid) → exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/tier2/analytics/cost-skill"
printf '%s' "$SKILL_MD" > "$TMPDIR/tier2/analytics/cost-skill/SKILL.md"
cat > "$TMPDIR/tier2/analytics/cost-skill/TESTS.yaml" << 'EOF'
tests:
  - name: empty
    trigger: "anything"
EOF
assert_exit "empty test case exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: the actual repo skill's TESTS.yaml passes
assert_exit "repo skill regression tests pass" 0 bash -c "cd '$REPO_ROOT' && python3 '$SCRIPT'"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
