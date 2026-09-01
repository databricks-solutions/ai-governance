#!/usr/bin/env bash
PASS=0; FAIL=0
REPO_ROOT="$(git rev-parse --show-toplevel)"

assert_exit() {
  local desc="$1" expected="$2"; shift 2
  "$@" >/dev/null 2>&1
  local actual=$?
  if [[ $actual -eq $expected ]]; then echo "PASS: $desc"; ((PASS++))
  else echo "FAIL: $desc (expected exit $expected, got $actual)"; ((FAIL++)); fi
}

assert_exit "repo passes lint-and-scan" 0 bash "$REPO_ROOT/scripts/lint-and-scan.sh"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
