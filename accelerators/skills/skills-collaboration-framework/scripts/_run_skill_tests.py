#!/usr/bin/env python3
"""Per-skill regression tests — static, behavior-oriented (spec Ch 10.2 / §16.3).

Each T2/T3 skill MAY ship a `TESTS.yaml` beside its `SKILL.md`. It declares test cases that
assert on what the skill *does* (which tables its SQL references, and which it must never touch),
NOT on the literal wording of any generated natural-language output — that is fragile against
model drift and is explicitly out of scope per the spec.

TESTS.yaml schema (beside SKILL.md):

    tests:
      - name: top-jobs-cost
        trigger: "What are my top 5 most expensive jobs?"   # documents the invoking prompt
        expect_tables:                                       # every one MUST appear in the skill SQL
          - system.billing.usage
          - system.lakeflow.jobs
      - name: never-touches-identity
        trigger: "Show me who owns the most expensive job"
        forbid_tables:                                       # none of these may appear in the skill SQL
          - system.access.audit
          - main.hr.employees

Assertion model (both kinds from the spec):
  - Deterministic: expect_tables — each listed table must be referenced by some SQL block in SKILL.md.
  - Negative:      forbid_tables — no SQL block in SKILL.md may reference any listed table
                   (the guardrail case: the skill stays inside its declared scope).

This is a STATIC check over the SQL declared in SKILL.md — it shares extraction with validate-meta
and needs no workspace/endpoint. Skills without a TESTS.yaml are reported as untested (advisory),
never failed, so the harness can be adopted incrementally.
"""
import sys
import os
import glob

import yaml

# Reuse the exact SQL/table extraction validate-meta uses, so "tables referenced" means the
# same thing in both gates.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _validate_meta import (  # noqa: E402
    extract_sql_blocks, extract_tables, get_tier_from_path, parse_frontmatter,
)

ERRORS = []
UNTESTED = []
CASES_RUN = 0


def error(msg):
    ERRORS.append(msg)
    print(f"FAIL: {msg}", file=sys.stderr)


def skill_tables(skill_md_path):
    """Union of all qualified tables referenced by any SQL block in the SKILL.md."""
    markdown = open(skill_md_path).read()
    tables = set()
    for block in extract_sql_blocks(markdown):
        found, _ = extract_tables(block)
        tables |= found
    return tables


def run_case(skill_name, case, tables):
    global CASES_RUN
    CASES_RUN += 1
    name = case.get('name', '<unnamed>')
    expect = [str(t).lower() for t in (case.get('expect_tables') or [])]
    forbid = [str(t).lower() for t in (case.get('forbid_tables') or [])]
    if not expect and not forbid:
        error(f"{skill_name} / {name}: test case has neither expect_tables nor forbid_tables")
        return
    for t in expect:
        if t not in tables:
            error(f"{skill_name} / {name}: expected table '{t}' is not referenced by the skill's "
                  f"SQL (skill references: {sorted(tables) or 'none'})")
    for t in forbid:
        if t in tables:
            error(f"{skill_name} / {name}: forbidden table '{t}' IS referenced by the skill's SQL "
                  f"(guardrail violated — the skill must stay within its declared scope)")


def main():
    skill_files = sorted(
        f for f in (
            glob.glob('tier2/**/*.md', recursive=True) +
            glob.glob('tier3/**/*.md', recursive=True)
        )
        if os.path.basename(f) == 'SKILL.md'
    )
    for skill_md in skill_files:
        tier = get_tier_from_path(skill_md)
        if tier not in (2, 3):
            continue
        fm = parse_frontmatter(skill_md)
        skill_name = (fm or {}).get('name') or os.path.dirname(skill_md)
        tests_path = os.path.join(os.path.dirname(skill_md), 'TESTS.yaml')
        if not os.path.exists(tests_path):
            UNTESTED.append(skill_name)
            continue
        try:
            spec = yaml.safe_load(open(tests_path)) or {}
        except yaml.YAMLError as e:
            error(f"{skill_name}: TESTS.yaml is not valid YAML: {e}")
            continue
        cases = spec.get('tests') or []
        if not cases:
            error(f"{skill_name}: TESTS.yaml has no 'tests' cases")
            continue
        tables = skill_tables(skill_md)
        for case in cases:
            run_case(skill_name, case, tables)

    if UNTESTED:
        print(f"\nADVISORY: {len(UNTESTED)} T2/T3 skill(s) have no TESTS.yaml (untested): "
              f"{', '.join(sorted(UNTESTED))}", file=sys.stderr)
    if ERRORS:
        print(f"\nrun-skill-tests: {len(ERRORS)} failing assertion(s) across {CASES_RUN} case(s).",
              file=sys.stderr)
        sys.exit(1)
    print(f"run-skill-tests: {CASES_RUN} test case(s) passed "
          f"({len(UNTESTED)} skill(s) untested — advisory).")
    sys.exit(0)


if __name__ == '__main__':
    main()
