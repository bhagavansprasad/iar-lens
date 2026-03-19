#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# oic-lens | tools/regression_test.sh
# Full clean regression — M1, M2, M3 across all test pairs.
#
# Usage:
#   bash tools/regression_test.sh
#
# What it does:
#   1. Cleans output/ and workspace/
#   2. Regenerates delta.json for all pairs (M1 + M2, pure Python)
#   3. Regenerates flow_context.json for all pairs (M3, LLM call)
#   4. Runs M1, M2, M3 test suites
#   5. Spot-checks 41-42 flow_context.json (random pair)
#   6. Prints a final pass/fail summary
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"

# Pairs to run through the full pipeline
STEP1_PAIRS=(32-33 49-50 55-56 41-42)

# Pairs to run through M3 (LLM — costs money, skip pairs with no meaningful diff if needed)
STEP3_PAIRS=(32-33 49-50 55-56 41-42)

# Test pairs for each milestone test suite
M1_TEST_PAIRS=(32-33 49-50 55-56 41-42)
M2_TEST_PAIRS=(32-33 49-50 55-56)
M3_TEST_PAIRS=(32-33 49-50 55-56)

PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

header() {
    echo ""
    echo "======================================================================"
    echo "  $1"
    echo "======================================================================"
}

step() {
    echo ""
    echo "--- $1"
}

ok() {
    echo "  ✅  $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "  ❌  $1"
    FAIL=$((FAIL + 1))
}

run_and_check() {
    local desc="$1"
    shift
    if "$@"; then
        ok "$desc"
    else
        fail "$desc"
    fi
}

# ---------------------------------------------------------------------------
# 1. Clean
# ---------------------------------------------------------------------------

header "STEP 1 — Clean artifacts"

step "Removing output/ and workspace/ contents"
rm -rf output/* workspace/*
echo "  Cleaned: output/ and workspace/"

# ---------------------------------------------------------------------------
# 2. Regenerate Step 1 delta.json (M1 + M2, pure Python)
# ---------------------------------------------------------------------------

header "STEP 2 — Regenerate delta.json (M1 + M2)"

for PAIR in "${STEP1_PAIRS[@]}"; do
    step "iar_compare $PAIR"
    if python src/iar_compare.py "$PAIR"; then
        ok "iar_compare $PAIR → delta.json written"
    else
        fail "iar_compare $PAIR FAILED"
    fi
done

# ---------------------------------------------------------------------------
# 3. Regenerate flow_context.json (M3, LLM)
# ---------------------------------------------------------------------------

header "STEP 3 — Regenerate flow_context.json (M3 — LLM calls)"

for PAIR in "${STEP3_PAIRS[@]}"; do
    step "flow_understander $PAIR"
    if python src/flow_understander.py "$PAIR"; then
        ok "flow_understander $PAIR → flow_context.json written"
    else
        fail "flow_understander $PAIR FAILED"
    fi
done

# ---------------------------------------------------------------------------
# 4. Run test suites
# ---------------------------------------------------------------------------

header "STEP 4 — Run test suites"

step "M1 — Structural Delta"
run_and_check "M1 tests: ${M1_TEST_PAIRS[*]}" \
    python tests/test_m1_structural_delta.py "${M1_TEST_PAIRS[@]}"

step "M2 — Modified Steps Detection"
run_and_check "M2 tests: ${M2_TEST_PAIRS[*]}" \
    python tests/test_m2_modified_steps.py "${M2_TEST_PAIRS[@]}"

step "M3 — Flow Understander"
run_and_check "M3 tests: ${M3_TEST_PAIRS[*]}" \
    python tests/test_m3_flow_understander.py "${M3_TEST_PAIRS[@]}"

# ---------------------------------------------------------------------------
# 5. Spot-check 41-42 flow_context (random pair)
# ---------------------------------------------------------------------------

header "STEP 5 — Spot-check 41-42 flow_context.json (random pair)"

FC_PATH="output/41-42_flow_context.json"

if [[ -f "$FC_PATH" ]]; then
    echo ""
    echo "  change_type        : $(python -c "import json; d=json.load(open('$FC_PATH')); print(d.get('change_type','?'))")"
    echo "  change_type_reason : $(python -c "import json; d=json.load(open('$FC_PATH')); print(d.get('change_type_reason','?'))")"
    echo "  modified_steps     : $(python -c "import json; d=json.load(open('$FC_PATH')); print(d.get('modified_steps_count','?'))")"
    echo "  systems (source)   : $(python -c "import json; d=json.load(open('$FC_PATH')); print(len(d.get('systems_involved',{}).get('source',[])), 'adapters')")"
    echo ""
    echo "  integration_purpose:"
    python -c "import json; d=json.load(open('$FC_PATH')); print('  ' + d.get('integration_purpose','?'))"
    echo ""
    echo "  change_narrative:"
    python -c "import json; d=json.load(open('$FC_PATH')); print('  ' + d.get('change_narrative','?'))"
    ok "41-42 flow_context.json spot-check complete"
else
    fail "41-42 flow_context.json not found — spot-check skipped"
fi

# ---------------------------------------------------------------------------
# 6. Output file inventory
# ---------------------------------------------------------------------------

header "STEP 6 — Output file inventory"

echo ""
echo "  output/ contents:"
ls -lh output/ | awk '{print "    " $0}'

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

echo ""
echo "======================================================================"
echo "  REGRESSION SUMMARY"
echo "======================================================================"
echo "  ✅  Passed : $PASS"
echo "  ❌  Failed : $FAIL"
echo "======================================================================"
echo ""

if [[ $FAIL -gt 0 ]]; then
    echo "❌  REGRESSION FAILED — $FAIL step(s) failed above"
    exit 1
else
    echo "✅  FULL REGRESSION PASSED"
    exit 0
fi
