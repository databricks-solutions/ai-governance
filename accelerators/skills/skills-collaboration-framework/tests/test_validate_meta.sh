#!/usr/bin/env bash
set -uo pipefail
PASS=0; FAIL=0
REPO_ROOT="$(git rev-parse --show-toplevel)"
SCRIPT="$REPO_ROOT/scripts/_validate_meta.py"

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

# Test: valid T1 skill passes
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
cp "$REPO_ROOT/config/registry.yaml" "$TMPDIR/config/"
mkdir -p "$TMPDIR/tier1/testuser/test-valid-skill"
cp "$REPO_ROOT/tests/fixtures/valid-skill/SKILL.md" "$TMPDIR/tier1/testuser/test-valid-skill/SKILL.md"
assert_exit "valid T1 skill passes" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: missing name exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
cp "$REPO_ROOT/config/registry.yaml" "$TMPDIR/config/"
mkdir -p "$TMPDIR/tier1/testuser/bad"
cp "$REPO_ROOT/tests/fixtures/invalid-no-name/SKILL.md" "$TMPDIR/tier1/testuser/bad/SKILL.md"
assert_exit "missing name exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: missing description exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
cp "$REPO_ROOT/config/registry.yaml" "$TMPDIR/config/"
mkdir -p "$TMPDIR/tier1/testuser/bad"
cp "$REPO_ROOT/tests/fixtures/invalid-no-description/SKILL.md" "$TMPDIR/tier1/testuser/bad/SKILL.md"
assert_exit "missing description exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: extra frontmatter fields exit 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
cp "$REPO_ROOT/config/registry.yaml" "$TMPDIR/config/"
mkdir -p "$TMPDIR/tier1/testuser/bad"
cp "$REPO_ROOT/tests/fixtures/invalid-extra-fields/SKILL.md" "$TMPDIR/tier1/testuser/bad/SKILL.md"
assert_exit "extra frontmatter fields exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: T3 skill missing council/security approvals exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
mkdir -p "$TMPDIR/tier3/needs-approval"
cp "$REPO_ROOT/tests/fixtures/valid-skill/SKILL.md" "$TMPDIR/tier3/needs-approval/SKILL.md"
python3 -c "
p='$TMPDIR/tier3/needs-approval/SKILL.md'
c=open(p).read().replace('test-valid-skill','needs-approval')
open(p,'w').write(c)
"
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: needs-approval
    tier: 3
    owner: cedric.boisvert@databricks.com
    description: A T3 skill with empty approvals.
    data_classification: internal
    pii: false
    unity_catalog_scopes: []
    approvals: {steward: "", council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
assert_exit "T3 missing council/security approvals exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: duplicate skill name across two folders exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
cp "$REPO_ROOT/config/registry.yaml" "$TMPDIR/config/"
for d in a b; do
  mkdir -p "$TMPDIR/tier1/testuser/dup-$d"
  cp "$REPO_ROOT/tests/fixtures/valid-skill/SKILL.md" "$TMPDIR/tier1/testuser/dup-$d/SKILL.md"
done
assert_exit "duplicate skill name exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: T2 skill missing registry 'version' exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
mkdir -p "$TMPDIR/tier2/platform/needs-version"
cp "$REPO_ROOT/tests/fixtures/valid-skill/SKILL.md" "$TMPDIR/tier2/platform/needs-version/SKILL.md"
python3 -c "
p='$TMPDIR/tier2/platform/needs-version/SKILL.md'
open(p,'w').write(open(p).read().replace('test-valid-skill','needs-version'))
"
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: needs-version
    tier: 2
    owner: cedric.boisvert@databricks.com
    domain: platform
    description: A T2 skill with no version field.
    data_classification: internal
    pii: false
    approvals: {steward: "", council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
assert_exit "T2 missing version exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Helper: write a registry + governance + SKILL.md for a T2 platform skill.
# Usage: make_t2_skill <tmpdir> <steward> <scopes_yaml_block> <sql_block>
write_governance() {
  mkdir -p "$1/config"
  cat > "$1/config/governance.yaml" << 'GOVEOF'
platform_team:
  - cedric.boisvert@databricks.com
tier2:
  stewards:
    platform:
      - cedric.boisvert@databricks.com
tier3:
  council: [cedric.boisvert@databricks.com]
  security: [security@example.invalid]
GOVEOF
}

# Writes a workspaces.json whose tier2 maps only the 'platform' domain (matching write_governance)
# and a non-empty tier3, so check_domain_mapped has something to validate against.
write_workspaces() {
  mkdir -p "$1/config"
  cat > "$1/config/workspaces.json" << 'WSEOF'
{
  "skills_path": "/.assistant/skills",
  "tier2": { "platform": ["https://example-staging.cloud.databricks.com"] },
  "tier3": { "workspaces": ["https://example-prod.cloud.databricks.com"] }
}
WSEOF
}

# Test: T2 skill with NO unity_catalog_scopes passes (scopes are optional — footprint
# lives in the SKILL.md prose; UC enforces access at runtime regardless)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/needs-scope"
cat > "$TMPDIR/tier2/platform/needs-scope/SKILL.md" << 'EOF'
---
name: needs-scope
description: A T2 skill with no declared UC scopes.
---
## Query
```sql
SELECT * FROM system.billing.usage
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: needs-scope
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: platform
    description: A T2 skill with no declared UC scopes.
    data_classification: internal
    pii: false
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
assert_exit "T2 with no unity_catalog_scopes passes (optional)" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: SKILL.md SQL referencing a table outside declared scopes is ADVISORY (passes, warns)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/leaky"
cat > "$TMPDIR/tier2/platform/leaky/SKILL.md" << 'EOF'
---
name: leaky
description: A T2 skill whose SQL escapes its declared scope.
---
## Query
```sql
SELECT * FROM system.billing.usage u
LEFT JOIN main.secrets.customer_pii p ON u.account_id = p.account_id
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: leaky
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: platform
    description: A T2 skill whose SQL escapes its declared scope.
    data_classification: internal
    pii: false
    unity_catalog_scopes: [system.billing.usage]
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
OUT=$(cd "$TMPDIR" && python3 "$SCRIPT" 2>&1); RC=$?
assert_exit "out-of-scope table in SKILL.md is advisory (exit 0)" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
if echo "$OUT" | grep -qi "outside the declared"; then
  echo "PASS: out-of-scope table emits an advisory warning"; PASS=$((PASS+1))
else
  echo "FAIL: expected an out-of-scope advisory warning"; echo "$OUT"; FAIL=$((FAIL+1))
fi
rm -rf "$TMPDIR"

# Unit test: extract_tables must NOT treat a WITH-clause (CTE) alias as a real table
if python3 - "$SCRIPT" << 'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("vm", sys.argv[1])
vm = importlib.util.module_from_spec(spec); spec.loader.exec_module(vm)
sql = "WITH mtd AS (SELECT SUM(usage_quantity) c FROM system.billing.usage) SELECT c FROM mtd"
tables, ok = vm.extract_tables(sql)
assert 'mtd' not in tables, f"CTE alias leaked as a table: {tables}"
assert 'system.billing.usage' in tables, f"real table missing: {tables}"
PYEOF
then echo "PASS: extract_tables excludes CTE aliases"; PASS=$((PASS+1))
else echo "FAIL: extract_tables treated a CTE alias as a table"; FAIL=$((FAIL+1)); fi

# Test: T2 steward not authorized in governance.yaml exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/unauth"
cat > "$TMPDIR/tier2/platform/unauth/SKILL.md" << 'EOF'
---
name: unauth
description: A T2 skill signed off by an unauthorized steward.
---
## Query
```sql
SELECT * FROM system.billing.usage
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: unauth
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: platform
    description: A T2 skill signed off by an unauthorized steward.
    data_classification: internal
    pii: false
    unity_catalog_scopes: [system.billing.usage]
    approvals: {steward: random.person@example.invalid, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
assert_exit "T2 steward not in governance.yaml exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: valid T2 skill (scopes + in-scope SQL + authorized steward) passes
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/good"
cat > "$TMPDIR/tier2/platform/good/SKILL.md" << 'EOF'
---
name: good
description: A well-formed, in-bounds T2 skill.
---
## Query
```sql
SELECT u.sku_name, SUM(u.usage_quantity) AS dbus
FROM system.billing.usage u
LEFT JOIN system.lakeflow.jobs j ON u.usage_metadata.job_id = j.job_id
GROUP BY 1
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: good
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: platform
    description: A well-formed, in-bounds T2 skill.
    data_classification: internal
    pii: false
    unity_catalog_scopes: [system.billing.usage, system.lakeflow.jobs]
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
assert_exit "valid T2 skill (scopes + steward) passes" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: T2 skill whose owner is not in governance.yaml exits 1
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/orphan"
cat > "$TMPDIR/tier2/platform/orphan/SKILL.md" << 'EOF'
---
name: orphan
description: A T2 skill owned by someone not in the directory.
---
## Query
```sql
SELECT * FROM system.billing.usage
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: orphan
    tier: 2
    version: 1.0.0
    owner: ghost@example.invalid
    domain: platform
    description: A T2 skill owned by someone not in the directory.
    data_classification: internal
    pii: false
    unity_catalog_scopes: [system.billing.usage]
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
assert_exit "T2 owner not in governance.yaml exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: deprecated T2 skill with orphaned owner passes validation (Fix A regression lock)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/retired"
cat > "$TMPDIR/tier2/platform/retired/SKILL.md" << 'EOF'
---
name: retired
description: A deprecated T2 skill whose owner has left.
---
## Query
```sql
SELECT * FROM system.billing.usage
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: retired
    tier: 2
    version: 1.0.0
    owner: ghost@example.invalid
    domain: platform
    description: A deprecated T2 skill whose owner has left.
    data_classification: internal
    pii: false
    unity_catalog_scopes: [system.billing.usage]
    approvals: {steward: "", council: "", security: ""}
    deprecated: true
    removed_after: "2099-01-01"
    deprecation_reason: Owner left the organization; auto-proposed for retirement.
REGEOF
assert_exit "deprecated ownerless skill passes validation" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: stray non-SKILL.md markdown under a tier tree exits 1 (would bypass all checks)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
cp "$REPO_ROOT/config/registry.yaml" "$TMPDIR/config/"
mkdir -p "$TMPDIR/tier3/analytics"
cp "$REPO_ROOT/tests/fixtures/valid-skill/SKILL.md" "$TMPDIR/tier3/analytics/stray-skill.md"
assert_exit "stray non-SKILL.md under tier exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: misplaced SKILL.md (wrong depth for its tier) exits 1
# tier3 expects tier3/<skill>/SKILL.md; an extra domain level is wrong.
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
cp "$REPO_ROOT/config/registry.yaml" "$TMPDIR/config/"
mkdir -p "$TMPDIR/tier3/analytics/some-skill"
cp "$REPO_ROOT/tests/fixtures/valid-skill/SKILL.md" "$TMPDIR/tier3/analytics/some-skill/SKILL.md"
assert_exit "misplaced SKILL.md (wrong tier depth) exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: multi-file skill (supporting .md beside SKILL.md) passes — skills may bundle resources
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
cp "$REPO_ROOT/config/registry.yaml" "$TMPDIR/config/"
mkdir -p "$TMPDIR/tier1/testuser/multi-file-skill"
cp "$REPO_ROOT/tests/fixtures/valid-skill/SKILL.md" "$TMPDIR/tier1/testuser/multi-file-skill/SKILL.md"
printf '# Supporting patterns\nReference material for the skill.\n' > "$TMPDIR/tier1/testuser/multi-file-skill/patterns.md"
assert_exit "multi-file skill (supporting .md) passes" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: T2 skill with pii: true exits 1 (spec §2.2 — PII must be Tier 3)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
mkdir -p "$TMPDIR/tier2/analytics/pii-skill"
cat > "$TMPDIR/tier2/analytics/pii-skill/SKILL.md" << 'EOF'
---
name: pii-skill
description: A T2 skill that improperly declares PII access.
---
## Query
```sql
SELECT * FROM system.billing.usage
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: pii-skill
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: analytics
    description: A T2 skill that improperly declares PII access.
    data_classification: internal
    pii: true
    unity_catalog_scopes: [system.billing.usage]
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
cp "$REPO_ROOT/config/governance.yaml" "$TMPDIR/config/"
assert_exit "T2 skill with pii:true exits 1 (must be T3)" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: T2 skill with data_classification: regulated exits 1 (spec §2.2)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
mkdir -p "$TMPDIR/tier2/analytics/reg-skill"
cat > "$TMPDIR/tier2/analytics/reg-skill/SKILL.md" << 'EOF'
---
name: reg-skill
description: A T2 skill that improperly declares regulated data.
---
## Query
```sql
SELECT * FROM system.billing.usage
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: reg-skill
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: analytics
    description: A T2 skill that improperly declares regulated data.
    data_classification: regulated
    pii: false
    unity_catalog_scopes: [system.billing.usage]
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
cp "$REPO_ROOT/config/governance.yaml" "$TMPDIR/config/"
assert_exit "T2 skill with regulated classification exits 1 (must be T3)" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: T2 skill whose SQL performs a write/mutation exits 1 (spec §2.2 — write skills are T3)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
mkdir -p "$TMPDIR/tier2/analytics/write-skill"
cat > "$TMPDIR/tier2/analytics/write-skill/SKILL.md" << 'EOF'
---
name: write-skill
description: A T2 skill that mutates a table.
---
## Query
```sql
DELETE FROM system.billing.usage WHERE usage_date < '2020-01-01'
```
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: write-skill
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: analytics
    description: A T2 skill that mutates a table.
    data_classification: internal
    pii: false
    unity_catalog_scopes: [system.billing.usage]
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
cp "$REPO_ROOT/config/governance.yaml" "$TMPDIR/config/"
assert_exit "T2 skill with write/mutation SQL exits 1 (must be T3)" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: T2 skill with an unfilled TODO placeholder exits 1 (must be authored before shipping)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/analytics/todo-skill"
cat > "$TMPDIR/tier2/analytics/todo-skill/SKILL.md" << 'EOF'
---
name: todo-skill
description: Analyze something useful and recommend concrete next steps.
---
## Overview
Does a thing.
## When to use this skill
- "do the thing"
## Instructions
TODO: fill in the actual steps.
## Examples
Request/response here.
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: todo-skill
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: analytics
    description: Analyze something useful and recommend concrete next steps.
    data_classification: internal
    pii: false
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
assert_exit "T2 skill with leftover TODO exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: T1 skill with a TODO is ADVISORY only (sandbox scratch — passes, warns)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier1/testuser/todo-sandbox"
cat > "$TMPDIR/tier1/testuser/todo-sandbox/SKILL.md" << 'EOF'
---
name: todo-sandbox
description: A personal sandbox skill still being drafted.
---
## Overview
TODO: still figuring this out.
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills: []
REGEOF
OUT=$(cd "$TMPDIR" && python3 "$SCRIPT" 2>&1); RC=$?
assert_exit "T1 skill with TODO is advisory (exit 0)" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
if echo "$OUT" | grep -qi "unfilled 'TODO'"; then
  echo "PASS: T1 TODO emits an advisory warning"; PASS=$((PASS+1))
else
  echo "FAIL: expected a T1 TODO advisory warning"; echo "$OUT"; FAIL=$((FAIL+1))
fi
rm -rf "$TMPDIR"

# Test: T2 skill missing recommended sections warns (advisory) but passes
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/thin-skill"
cat > "$TMPDIR/tier2/platform/thin-skill/SKILL.md" << 'EOF'
---
name: thin-skill
description: Summarize daily active users from the events table for a given date range.
---
Just some prose with no headings at all, so every recommended section concept is missing.
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: thin-skill
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: platform
    description: Summarize daily active users from the events table for a given date range.
    data_classification: internal
    pii: false
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
OUT=$(cd "$TMPDIR" && python3 "$SCRIPT" 2>&1); RC=$?
assert_exit "T2 skill missing sections still passes (advisory)" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
if echo "$OUT" | grep -qi "missing recommended section"; then
  echo "PASS: missing sections emit an advisory warning"; PASS=$((PASS+1))
else
  echo "FAIL: expected a missing-sections advisory warning"; echo "$OUT"; FAIL=$((FAIL+1))
fi
rm -rf "$TMPDIR"

# Test: a well-authored T2 skill (filled sections, substantive description) is advisory-CLEAN
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/good-skill"
cat > "$TMPDIR/tier2/platform/good-skill/SKILL.md" << 'EOF'
---
name: good-skill
description: Rank the most expensive Databricks jobs over a date range and recommend cost cuts.
---
## Overview
Ranks jobs by DBU spend and suggests optimizations.
## When to use this skill
- "what are my most expensive jobs this month?"
## Instructions
1. Query billing usage joined to jobs.
2. Rank by cost and summarize.
## Examples
Request: "top 5 costly jobs" -> ranked table plus recommendations.
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: good-skill
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: platform
    description: Rank the most expensive Databricks jobs over a date range and recommend cost cuts.
    data_classification: internal
    pii: false
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
OUT=$(cd "$TMPDIR" && python3 "$SCRIPT" 2>&1)
assert_exit "well-authored T2 skill passes" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
if echo "$OUT" | grep -qiE "missing recommended section|unfilled 'TODO'|description is very short"; then
  echo "FAIL: well-authored skill should not trigger body advisories"; echo "$OUT"; FAIL=$((FAIL+1))
else
  echo "PASS: well-authored skill is advisory-clean"; PASS=$((PASS+1))
fi
rm -rf "$TMPDIR"

# Test: check_domain_mapped — a T2 skill whose domain IS mapped in workspaces.json passes
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_governance "$TMPDIR"
write_workspaces "$TMPDIR"
mkdir -p "$TMPDIR/tier2/platform/mapped-skill"
cat > "$TMPDIR/tier2/platform/mapped-skill/SKILL.md" << 'EOF'
---
name: mapped-skill
description: Analyze DBU cost trends and recommend concrete optimizations for the team.
---
## Overview
Reads cost data.
## When to use this skill
- "what are my costs"
## Instructions
1. Query usage.
## Examples
**Request:** "costs?" **Expected:** a ranked table.
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: mapped-skill
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: platform
    description: Analyze DBU cost trends and recommend concrete optimizations for the team.
    data_classification: internal
    pii: false
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
assert_exit "T2 skill in a mapped domain passes" 0 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
rm -rf "$TMPDIR"

# Test: check_domain_mapped — a T2 skill whose domain is NOT in workspaces.json exits 1
# (would merge but reach no workspace at sync time — the gate moves that failure left to the PR)
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR/config"
write_workspaces "$TMPDIR"
mkdir -p "$TMPDIR/tier2/ghost-domain/unmapped-skill"
cat > "$TMPDIR/tier2/ghost-domain/unmapped-skill/SKILL.md" << 'EOF'
---
name: unmapped-skill
description: Analyze DBU cost trends and recommend concrete optimizations for the team.
---
## Overview
Reads cost data.
## When to use this skill
- "what are my costs"
## Instructions
1. Query usage.
## Examples
**Request:** "costs?" **Expected:** a ranked table.
EOF
cat > "$TMPDIR/config/registry.yaml" << 'REGEOF'
skills:
  - name: unmapped-skill
    tier: 2
    version: 1.0.0
    owner: cedric.boisvert@databricks.com
    domain: ghost-domain
    description: Analyze DBU cost trends and recommend concrete optimizations for the team.
    data_classification: internal
    pii: false
    approvals: {steward: cedric.boisvert@databricks.com, council: "", security: ""}
    deprecated: false
    removed_after: null
REGEOF
# governance authorizes ghost-domain's steward, so the ONLY remaining failure is the
# unmapped-domain gate (ghost-domain is intentionally absent from write_workspaces' tier2).
cat > "$TMPDIR/config/governance.yaml" << 'GOVEOF'
platform_team:
  - cedric.boisvert@databricks.com
tier2:
  stewards:
    ghost-domain:
      - cedric.boisvert@databricks.com
tier3:
  council: [cedric.boisvert@databricks.com]
  security: [security@example.invalid]
GOVEOF
assert_exit "T2 skill in an unmapped domain exits 1" 1 bash -c "cd '$TMPDIR' && python3 '$SCRIPT'"
# Confirm it exits 1 for the RIGHT reason (the domain gate, not an unrelated error).
OUT=$(cd "$TMPDIR" && python3 "$SCRIPT" 2>&1)
if echo "$OUT" | grep -q "not.*mapped in workspaces.json"; then
  echo "PASS: unmapped-domain exit is the domain gate (not an incidental error)"; PASS=$((PASS+1))
else
  echo "FAIL: unmapped-domain exited 1 but NOT via the domain gate:"; echo "$OUT"; FAIL=$((FAIL+1))
fi
rm -rf "$TMPDIR"

# Test: actual repo skills validate cleanly
assert_exit "repo skills pass validation" 0 bash -c "cd '$REPO_ROOT' && python3 '$SCRIPT'"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
