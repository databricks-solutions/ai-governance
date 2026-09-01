#!/usr/bin/env bash
# Tests the configurable eval-gate decision logic in ai-review.sh, exercised through its
# `--gate-decision <score> [verdict]` dry path so no live AI endpoint is required.
set -uo pipefail
PASS=0; FAIL=0
REPO_ROOT="$(git rev-parse --show-toplevel)"
SCRIPT="$REPO_ROOT/scripts/ai-review.sh"

# assert_exit <desc> <expected_exit> <env...> -- <score> [verdict]
# Runs the dry gate path with the given EVAL_GATE_MODE / MIN_EVAL_SCORE env and checks exit code.
assert_gate() {
  local desc="$1" expected="$2" mode="$3" min="$4" score="$5" verdict="${6:-pass}"
  EVAL_GATE_MODE="$mode" MIN_EVAL_SCORE="$min" bash "$SCRIPT" --gate-decision "$score" "$verdict" >/dev/null 2>&1
  local actual=$?
  if [[ $actual -eq $expected ]]; then
    echo "PASS: $desc"; ((PASS++))
  else
    echo "FAIL: $desc (expected exit $expected, got $actual)"; ((FAIL++))
  fi
}

# assert_marker <desc> <mode> <min> <score> -- expects the needs-human-review marker on stdout
assert_marker() {
  local desc="$1" mode="$2" min="$3" score="$4"
  local out
  out=$(EVAL_GATE_MODE="$mode" MIN_EVAL_SCORE="$min" bash "$SCRIPT" --gate-decision "$score" pass 2>/dev/null)
  if echo "$out" | grep -q "needs-human-review"; then
    echo "PASS: $desc"; ((PASS++))
  else
    echo "FAIL: $desc (expected needs-human-review marker, got: $out)"; ((FAIL++))
  fi
}

# advisory (default): below threshold warns but never blocks
assert_gate "advisory: below threshold passes (exit 0)"        0 advisory     0.8 0.5 pass
assert_gate "advisory: above threshold passes (exit 0)"        0 advisory     0.8 0.95 pass

# auto-drop: below threshold blocks the build
assert_gate "auto-drop: below threshold blocks (exit 1)"       1 auto-drop    0.8 0.5 pass
assert_gate "auto-drop: above threshold passes (exit 0)"       0 auto-drop    0.8 0.95 pass

# human-review: below threshold does NOT block, but emits a marker
assert_gate "human-review: below threshold passes (exit 0)"    0 human-review 0.8 0.5 pass
assert_marker "human-review: emits needs-human-review marker"    human-review 0.8 0.5

# verdict=fail is a hard gate in EVERY mode (any dimension < 0.5 upstream)
assert_gate "advisory: verdict fail blocks (exit 1)"           1 advisory     0.8 0.95 fail
assert_gate "auto-drop: verdict fail blocks (exit 1)"          1 auto-drop    0.8 0.95 fail
assert_gate "human-review: verdict fail blocks (exit 1)"       1 human-review 0.8 0.95 fail

# default mode (env unset) behaves as advisory
DEFAULT_EXIT=$(MIN_EVAL_SCORE=0.8 bash "$SCRIPT" --gate-decision 0.5 pass >/dev/null 2>&1; echo $?)
if [[ "$DEFAULT_EXIT" -eq 0 ]]; then echo "PASS: default mode is advisory (exit 0)"; ((PASS++)); else echo "FAIL: default mode is advisory (got $DEFAULT_EXIT)"; ((FAIL++)); fi

# --- Per-tier gate resolution (4th arg = tier). Recommended config: T2 advisory, T3 human-review.
# assert_tier <desc> <expected_exit> <tier> <env-assignments...>
assert_tier() {
  local desc="$1" expected="$2" tier="$3"; shift 3
  env "$@" MIN_EVAL_SCORE=0.8 bash "$SCRIPT" --gate-decision 0.5 pass "$tier" >/dev/null 2>&1
  local actual=$?
  if [[ $actual -eq $expected ]]; then echo "PASS: $desc"; ((PASS++)); else echo "FAIL: $desc (expected $expected, got $actual)"; ((FAIL++)); fi
}

# T2 override advisory, T3 override auto-drop, global advisory: T2 passes, T3 blocks — same score.
assert_tier "per-tier: T2 advisory below-threshold passes"  0 2 EVAL_GATE_MODE=advisory EVAL_GATE_MODE_T2=advisory EVAL_GATE_MODE_T3=auto-drop
assert_tier "per-tier: T3 auto-drop below-threshold blocks" 1 3 EVAL_GATE_MODE=advisory EVAL_GATE_MODE_T2=advisory EVAL_GATE_MODE_T3=auto-drop

# T3 human-review does NOT block (recommended default) but emits the marker.
T3_HR_OUT=$(EVAL_GATE_MODE=advisory EVAL_GATE_MODE_T3=human-review MIN_EVAL_SCORE=0.8 bash "$SCRIPT" --gate-decision 0.5 pass 3 2>/dev/null)
T3_HR_EXIT=$?
if [[ $T3_HR_EXIT -eq 0 ]] && echo "$T3_HR_OUT" | grep -q "needs-human-review"; then
  echo "PASS: per-tier: T3 human-review passes with marker"; ((PASS++))
else
  echo "FAIL: per-tier: T3 human-review passes with marker (exit $T3_HR_EXIT, out: $T3_HR_OUT)"; ((FAIL++))
fi

# No per-tier override → falls back to global EVAL_GATE_MODE for that tier.
assert_tier "per-tier: T3 falls back to global auto-drop"   1 3 EVAL_GATE_MODE=auto-drop
assert_tier "per-tier: T2 falls back to global advisory"    0 2 EVAL_GATE_MODE=advisory

echo "---"
echo "PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]]
