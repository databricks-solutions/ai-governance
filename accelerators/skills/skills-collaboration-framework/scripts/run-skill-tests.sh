#!/usr/bin/env bash
# Per-skill regression tests (spec Ch 10.2 / §16.3): static, behavior-oriented assertions over
# the SQL declared in each T2/T3 SKILL.md. Runs on every PR alongside validate-meta; needs no
# workspace or endpoint. Skills without a TESTS.yaml are advisory-untested, never a hard failure.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
exec python3 "$(dirname "$0")/_run_skill_tests.py" "$@"
