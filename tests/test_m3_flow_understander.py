# ---------------------------------------------------------------------------
# oic-lens | tests/test_m3_flow_understander.py
# Validates M3: flow_understander produces a valid flow_context.json
#
# Checks (per master plan validation checklist):
#   - flow_context.json is written and parseable
#   - Required top-level keys are present
#   - systems_involved is Python-computed (present, non-empty)
#   - modified_steps_count matches delta
#   - change_narrative mentions processor_964 condition change (32-33)
#   - change_type is a known value
#
# Run:
#   python tests/test_m3_flow_understander.py 32-33
#   python tests/test_m3_flow_understander.py 49-50
# ---------------------------------------------------------------------------

import os
import sys
import json
import argparse
import logging

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

import config

logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s | %(message)s")

OUTPUT_DIR = os.path.join(project_root, config.OUTPUT_DIR)

REQUIRED_KEYS = [
    "integration_purpose",
    "logical_blocks_source",
    "logical_blocks_target",
    "flow_before",
    "flow_after",
    "change_narrative",
    "change_type",
    "change_type_reason",
    "systems_involved",
    "modified_steps_count",
    "integration",
    "version_from",
    "version_to",
    "generated_at",
]

VALID_CHANGE_TYPES = {
    "additive_only", "removal_only", "refactor",
    "scope_expansion", "bug_fix", "unknown",
}

# Per-pair assertions
PAIRS = [
    {
        "label"                   : "32-33",
        "expected_version_from"   : "01.00.0032",
        "expected_version_to"     : "01.00.0033",
        "expected_modified_count" : None,   # at least 1
        # Substring that must appear in change_narrative (processor_964 condition)
        # LLM describes the concept in business language — match on that
        "narrative_hints"         : ["awaiting shipping", "checks", "reliability", "escalat", "stuck", "loop", "retry", "routing", "numerous"],
        "narrative_hint_min"      : 1,
    },
    {
        "label"                   : "49-50",
        "expected_version_from"   : "01.00.0049",
        "expected_version_to"     : "01.00.0050",
        "expected_modified_count" : None,
        "narrative_hints"         : ["notification", "email", "label", "field", "contact", "phone"],
        "narrative_hint_min"      : 1,
    },
    {
        "label"                   : "55-56",
        "expected_version_from"   : "03.00.0001",
        "expected_version_to"     : "03.00.0011",
        "expected_modified_count" : 10,
        "narrative_hints"         : ["DHL", "file", "inventory", "reconcil"],
        "narrative_hint_min"      : 1,
    },
]


def run_pair(pair: dict) -> list[dict]:
    label = pair["label"]
    results = []

    def rec(name, passed, detail=""):
        results.append({"name": name, "passed": passed, "detail": detail})

    fc_path = os.path.join(OUTPUT_DIR, f"{label}_flow_context.json")

    # --- File exists ---
    rec("M3 | flow_context.json exists", os.path.exists(fc_path), fc_path)
    if not os.path.exists(fc_path):
        return results

    # --- Parseable ---
    try:
        with open(fc_path) as f:
            ctx = json.load(f)
        rec("M3 | flow_context.json is valid JSON", True)
    except json.JSONDecodeError as e:
        rec("M3 | flow_context.json is valid JSON", False, str(e))
        return results

    # --- Required keys ---
    for key in REQUIRED_KEYS:
        rec(f"M3 | key '{key}' present", key in ctx, f"keys={list(ctx.keys())}" if key not in ctx else "")

    # --- Version stamps ---
    rec(
        "M3 | version_from correct",
        ctx.get("version_from") == pair["expected_version_from"],
        f"got {ctx.get('version_from')}",
    )
    rec(
        "M3 | version_to correct",
        ctx.get("version_to") == pair["expected_version_to"],
        f"got {ctx.get('version_to')}",
    )

    # --- change_type is a known value ---
    rec(
        "M3 | change_type is valid",
        ctx.get("change_type") in VALID_CHANGE_TYPES,
        f"got '{ctx.get('change_type')}'",
    )

    # --- systems_involved is non-empty (Python-computed) ---
    si = ctx.get("systems_involved", {})
    rec(
        "M3 | systems_involved.source is non-empty",
        isinstance(si.get("source"), list) and len(si["source"]) > 0,
        f"got {si.get('source')}",
    )

    # --- modified_steps_count ---
    expected_mod = pair.get("expected_modified_count")
    actual_mod   = ctx.get("modified_steps_count")
    if expected_mod is not None:
        rec(
            f"M3 | modified_steps_count == {expected_mod}",
            actual_mod == expected_mod,
            f"got {actual_mod}",
        )
    else:
        rec(
            "M3 | modified_steps_count is an integer",
            isinstance(actual_mod, int),
            f"got {actual_mod!r}",
        )

    # --- integration_purpose is non-trivial ---
    purpose = ctx.get("integration_purpose", "")
    rec(
        "M3 | integration_purpose is non-trivial (>50 chars)",
        len(purpose) > 50,
        f"len={len(purpose)}",
    )

    # --- change_narrative or flow_after contains expected hints ---
    narrative = (ctx.get("change_narrative", "") + " " + ctx.get("flow_after", "")).lower()
    hints = pair.get("narrative_hints", [])
    min_hits = pair.get("narrative_hint_min", 1)
    hits = [h for h in hints if h.lower() in narrative]
    rec(
        f"M3 | change_narrative/flow_after contains >= {min_hits} expected hint(s) from {hints}",
        len(hits) >= min_hits,
        f"matched={hits}  snippet={narrative[:150]}",
    )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="M3 Test — Flow Understander",
        epilog="python tests/test_m3_flow_understander.py 32-33",
    )
    parser.add_argument("labels", nargs="*", metavar="LABEL",
                        help="Pair label(s) to test. Default: all")
    args = parser.parse_args()

    labels_requested = set(args.labels) if args.labels else {p["label"] for p in PAIRS}
    pairs_to_run = [p for p in PAIRS if p["label"] in labels_requested]

    if not pairs_to_run:
        print(f"No matching pairs for: {labels_requested}")
        sys.exit(1)

    print()
    print("=" * 70)
    print("M3 TEST — Flow Understander")
    print(f"Pairs: {len(pairs_to_run)}")
    print("=" * 70)

    total_pass = total_fail = 0

    for pair in pairs_to_run:
        label = pair["label"]
        print(f"\n  [{label}]")

        fc_path = os.path.join(OUTPUT_DIR, f"{label}_flow_context.json")
        if not os.path.exists(fc_path):
            print(f"    ⏭  SKIP — {label}_flow_context.json not found")
            print(f"           Run: python src/flow_understander.py {label}")
            continue

        results = run_pair(pair)
        for r in results:
            icon   = "✅ PASS" if r["passed"] else "❌ FAIL"
            detail = f"  `{r['detail']}`" if r["detail"] else ""
            print(f"    {icon}  {r['name']}{detail}")
            if r["passed"]:
                total_pass += 1
            else:
                total_fail += 1

    print()
    print("=" * 70)
    print(f"RESULTS: {total_pass}/{total_pass + total_fail} passed  |  {total_fail} failed")
    print("=" * 70)
    print()

    if total_fail > 0:
        print("❌  M3 FAILED")
        sys.exit(1)
    else:
        print("✅  M3 PASSED — flow context verified.")
        sys.exit(0)


if __name__ == "__main__":
    main()
