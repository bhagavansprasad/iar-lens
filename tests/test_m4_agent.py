# ---------------------------------------------------------------------------
# oic-lens | tests/test_m4_agent.py
# M4 — Agent Investigation
#
# Validates that the LLM-driven agent:
#   1. Correctly handles new / removed / modified steps
#   2. Produces a report.json with all three categories populated
#   3. Modified steps appear with medium or high risk (never low)
#   4. processor_964 (the canonical modified case) is correctly described
#
# Usage (from project root):
#   python tests/test_m4_agent.py 32-33
#   python tests/test_m4_agent.py 49-50
#   python tests/test_m4_agent.py 55-56
# ---------------------------------------------------------------------------

import os
import sys
import json
import asyncio
import argparse

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

import config

# ---------------------------------------------------------------------------
# Known validation expectations per pair
# ---------------------------------------------------------------------------

PAIRS = {
    "32-33": {
        "label"              : "32-33",
        "expected_new_count" : 8,
        "expected_removed"   : 0,
        "expected_modified"  : 7,
        "modified_processor" : "processor_964",
        "modified_keyword"   : "varCount",    # must appear in what_changed or technical_detail
    },
    "49-50": {
        "label"              : "49-50",
        "expected_new_count" : 0,
        "expected_removed"   : 0,
        "expected_modified"  : 2,
        "modified_processor" : "processor_1216",
        "modified_keyword"   : "Phone Number",
    },
    "51-52": {
        "label"              : "51-52",
        "expected_new_count" : 6,
        "expected_removed"   : 0,
        "expected_modified"  : 0,
        "modified_processor" : None,
        "modified_keyword"   : None,
    },
    "55-56": {
        "label"              : "55-56",
        "expected_new_count" : 15,
        "expected_removed"   : 8,
        "expected_modified"  : 10,
        "modified_processor" : "processor_1036",
        "modified_keyword"   : "File Name",
    },
}

PASS = "✅"
FAIL = "❌"
results = []


def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    msg    = f"  {status} {name}"
    if detail:
        msg += f"  [{detail}]"
    print(msg)
    results.append((name, condition))
    return condition


def check_inputs(output_dir: str, label: str) -> bool:
    """Verify Step 1 outputs exist before running the agent."""
    ok = True
    for fname in [f"{label}_delta.json", f"{label}_flow_context.json"]:
        path   = os.path.join(output_dir, fname)
        exists = os.path.exists(path)
        check(f"Input exists: {fname}", exists, path if not exists else "")
        if not exists:
            ok = False
    return ok


def run_checks(report: dict, pair_cfg: dict):
    """Run all validation checks against the produced report."""
    label = pair_cfg["label"]

    # --- Basic report structure ---
    check("report has overall_risk",   "overall_risk"   in report)
    check("report has recommendation", "recommendation" in report)
    check("report has summary",        bool(report.get("summary", "")))
    check("report has new_steps list",      isinstance(report.get("new_steps"),      list))
    check("report has removed_steps list",  isinstance(report.get("removed_steps"),  list))
    check("report has modified_steps list", isinstance(report.get("modified_steps"), list))

    # --- Count checks ---
    new_count      = len(report.get("new_steps", []))
    removed_count  = len(report.get("removed_steps", []))
    modified_count = len(report.get("modified_steps", []))

    exp_new      = pair_cfg["expected_new_count"]
    exp_removed  = pair_cfg["expected_removed"]
    exp_modified = pair_cfg["expected_modified"]

    check(f"new_steps count == {exp_new}",
          new_count == exp_new,
          f"got {new_count}")

    check(f"removed_steps count == {exp_removed}",
          removed_count == exp_removed,
          f"got {removed_count}")

    check(f"modified_steps count == {exp_modified}",
          modified_count == exp_modified,
          f"got {modified_count}")

    # --- Modified step risk floor ---
    low_risk_modified = [
        s for s in report.get("modified_steps", [])
        if s.get("risk_level", "").lower() == "low"
    ]
    check(
        "no modified steps have risk_level=low",
        len(low_risk_modified) == 0,
        f"low-risk modified: {[s.get('step_name') for s in low_risk_modified]}"
    )

    # --- Canonical modified processor check (32-33 only) ---
    if label == "32-33":
        mod_proc_id = pair_cfg["modified_processor"]
        keyword     = pair_cfg["modified_keyword"]

        # Check findings list (raw investigation results)
        findings = report.get("_findings", [])   # injected by test runner below
        pid_finding = next(
            (f for f in findings if f.get("processor_id") == mod_proc_id), None
        )
        check(
            f"{mod_proc_id} in findings",
            pid_finding is not None,
        )
        if pid_finding:
            combined = (
                pid_finding.get("what_changed", "") +
                pid_finding.get("technical_detail", "") +
                pid_finding.get("business_impact", "")
            ).lower()
            check(
                f"{mod_proc_id} finding mentions '{keyword}'",
                keyword.lower() in combined,
                f"searched in what_changed + technical_detail + business_impact"
            )
            risk = pid_finding.get("risk_level", "").lower()
            check(
                f"{mod_proc_id} risk_level is medium or high",
                risk in ("medium", "high"),
                f"got '{risk}'"
            )

    # --- Overall risk is a valid value ---
    check(
        "overall_risk is valid",
        report.get("overall_risk", "").lower() in ("low", "medium", "high", "unknown"),
        report.get("overall_risk", "")
    )

    # --- recommendation is a valid value ---
    check(
        "recommendation is valid",
        report.get("recommendation", "").lower() in (
            "approve", "approve_with_conditions", "reject", "manual_review_required"
        ),
        report.get("recommendation", "")
    )


def run_test(pair_key: str):
    pair_cfg   = PAIRS.get(pair_key)
    if not pair_cfg:
        print(f"Unknown pair '{pair_key}'. Known: {list(PAIRS.keys())}")
        sys.exit(1)

    label      = pair_cfg["label"]
    output_dir = os.path.join(project_root, "output")

    print(f"\n{'='*60}")
    print(f"test_m4_agent — pair: {pair_key}")
    print(f"{'='*60}")

    # Patch config
    config.OUTPUT_DIR = output_dir + os.sep
    config.LABEL      = label

    # Pre-check inputs
    print(f"\n[PRE-CHECK] Verifying Step 1 outputs...")
    if not check_inputs(output_dir, label):
        print(f"\n❌ Step 1 outputs missing. Run Step 1 first:")
        print(f"   python src/flow_understander.py {label}")
        sys.exit(1)

    # Run agent
    print(f"\n[AGENT] Running M4 agent for {label}...")
    from agent import run_agent
    result = asyncio.run(run_agent(label))

    # Load the written report for validation
    report_path = os.path.join(output_dir, f"{label}_report.json")
    if not os.path.exists(report_path):
        print(f"\n❌ report.json not found: {report_path}")
        sys.exit(1)

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    # Inject raw findings for deeper checks
    report["_findings"] = result.get("findings", [])

    # Run checks
    print(f"\n[CHECKS] Validating report...")
    run_checks(report, pair_cfg)

    # Summary
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    print(f"\n{'='*60}")
    print(f"RESULT: {passed}/{total} checks passed")
    if passed == total:
        print("✅ ALL CHECKS PASSED")
    else:
        failed = [name for name, ok in results if not ok]
        print(f"❌ FAILED: {failed}")
    print(f"{'='*60}\n")

    return passed == total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test M4 Agent Investigation in isolation",
        epilog=(
            "Examples:\n"
            "  python tests/test_m4_agent.py 32-33\n"
            "  python tests/test_m4_agent.py 49-50\n"
            "  python tests/test_m4_agent.py 55-56"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pair",
        choices=list(PAIRS.keys()),
        help="Which pair to test",
    )
    args = parser.parse_args()
    ok   = run_test(args.pair)
    sys.exit(0 if ok else 1)
