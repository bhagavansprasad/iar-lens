# ---------------------------------------------------------------------------
# test_report.py
# Standalone test for Stage 3 — generate_report()
#
# Assumes Stage 1 and Stage 2 have already run and produced:
#   output/<label>_delta.json
#   output/<label>_flow_context.json
#   output/<label>_report.json
#
# Usage (from project root):
#   python test/test_report.py 55-56
#   python test/test_report.py 32-33
#   python test/test_report.py 49-50
# ---------------------------------------------------------------------------

import os
import sys
import argparse

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

import config

PAIRS = {
    "32-33": {"label": "32-33"},
    "49-50": {"label": "49-50"},
    "55-56": {"label": "55-56"},
}

# ---------------------------------------------------------------------------

def check_inputs(output_dir: str, label: str) -> bool:
    required = [
        os.path.join(output_dir, f"{label}_delta.json"),
        os.path.join(output_dir, f"{label}_flow_context.json"),
        os.path.join(output_dir, f"{label}_report.json"),
    ]
    ok = True
    for path in required:
        name = os.path.basename(path)
        if os.path.exists(path):
            print(f"  ✅ {name}")
        else:
            print(f"  ❌ Missing: {path}")
            ok = False
    return ok


def run_test(pair_key: str):
    pair = PAIRS.get(pair_key)
    if not pair:
        print(f"Unknown pair '{pair_key}'. Choose from: {list(PAIRS.keys())}")
        sys.exit(1)

    label      = pair["label"]
    output_dir = os.path.join(project_root, "output")

    print(f"\n{'='*60}")
    print(f"test_report — pair: {pair_key}")
    print(f"{'='*60}")

    # Patch config
    config.OUTPUT_DIR = output_dir + os.sep
    config.LABEL      = label

    # Pre-check inputs
    print(f"\n[PRE-CHECK] Verifying Stage 1 + 2 outputs...")
    if not check_inputs(output_dir, label):
        print(f"\n❌ Missing inputs. Run Stage 1 and Stage 2 first:")
        print(f"   python test/test_comparison.py {label}")
        print(f"   python test/test_agent.py {label}")
        sys.exit(1)

    # Run report generation
    delta_path  = os.path.join(output_dir, f"{label}_delta.json")
    report_path = os.path.join(output_dir, f"{label}_report.json")
    md_path     = os.path.join(output_dir, f"{label}_change_report.md")

    print(f"\n[REPORT] Generating markdown report...")
    from report_generator import generate_report
    out = generate_report(
        delta_path  = delta_path,
        report_path = report_path,
        output_path = md_path
    )

    print(f"\n{'='*60}")
    print(f"RESULTS — pair: {label}")
    print(f"{'='*60}")
    print(f"  ✅ Report written: {out}")

    # Print first 60 lines so we can spot-check the new sections
    print(f"\n--- Preview (first 60 lines) ---")
    with open(out) as f:
        for i, line in enumerate(f):
            if i >= 60:
                print("  ... (truncated)")
                break
            print(line, end="")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Stage 3 report generation in isolation")
    parser.add_argument(
        "pair",
        choices=list(PAIRS.keys()),
        help="Which pair to test: 32-33, 49-50, or 55-56"
    )
    args = parser.parse_args()
    run_test(args.pair)
