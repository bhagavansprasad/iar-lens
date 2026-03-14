# ---------------------------------------------------------------------------
# test_comparison.py
# Standalone test for Stage 1 — run_comparison()
#
# Patches config for the requested pair and runs Stage 1 in isolation.
# Produces:
#   output/<label>_delta.json
#   output/<label>_flow_context.json
#
# Usage (from project root):
#   python test/test_comparison.py 55-56
#   python test/test_comparison.py 32-33
#   python test/test_comparison.py 49-50
# ---------------------------------------------------------------------------

import os
import sys
import argparse

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

import logging
import config

# Silence noisy third-party loggers
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("google_genai._api_client").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Pair definitions
# ---------------------------------------------------------------------------

PAIRS = {
    "32-33": {
        "label"     : "32-33",
        "source_iar": "flow-dump/32-33/FACTORYDOCK-TEST-32.car",
        "target_iar": "flow-dump/32-33/FACTORYDOCK-TEST-33.car",
    },
    "49-50": {
        "label"     : "49-50",
        "source_iar": "flow-dump/49-50/FACTORYDOCK-TEST-49.car",
        "target_iar": "flow-dump/49-50/FACTORYDOCK-TEST-50.car",
    },
    "55-56": {
        "label"     : "55-56",
        "source_iar": "flow-dump/55-56/INT03.00.0001.iar",
        "target_iar": "flow-dump/55-56/INT03.00.0011.iar",
    },
}

# ---------------------------------------------------------------------------

def run_test(pair_key: str):
    pair = PAIRS.get(pair_key)
    if not pair:
        print(f"Unknown pair '{pair_key}'. Choose from: {list(PAIRS.keys())}")
        sys.exit(1)

    label      = pair["label"]
    output_dir = os.path.join(project_root, "output")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"test_comparison — pair: {pair_key}")
    print(f"{'='*60}")

    # Patch config
    config.SOURCE_IAR    = os.path.join(project_root, pair["source_iar"])
    config.TARGET_IAR    = os.path.join(project_root, pair["target_iar"])
    config.OUTPUT_DIR    = output_dir + os.sep
    config.WORKSPACE_DIR = os.path.join(project_root, "workspace", label)
    config.LABEL         = label

    print(f"  Source : {config.SOURCE_IAR}")
    print(f"  Target : {config.TARGET_IAR}")
    print(f"  Output : {config.OUTPUT_DIR}")

    # Run Stage 1
    from iar_compare import run_comparison
    report = run_comparison()

    # Print summary
    stats = report.get("statistics", {})
    print(f"\n{'='*60}")
    print(f"RESULTS — pair: {label}")
    print(f"{'='*60}")
    print(f"  Integration : {report.get('integration', '?')}")
    print(f"  From → To   : v{report.get('version_from')} → v{report.get('version_to')}")
    print(f"  New steps   : {stats.get('new_steps_count', 0)}")
    print(f"  Removed     : {stats.get('removed_steps_count', 0)}")
    print(f"  Shifted     : {stats.get('positionally_shifted', 0)}")
    print(f"  Unchanged   : {stats.get('unchanged_count', 0)}")

    delta_path = os.path.join(output_dir, f"{label}_delta.json")
    fc_path    = os.path.join(output_dir, f"{label}_flow_context.json")

    print(f"\n  Outputs:")
    for path in [delta_path, fc_path]:
        status = "✅" if os.path.exists(path) else "❌"
        print(f"    {status} {path}")

    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Stage 1 comparison in isolation")
    parser.add_argument(
        "pair",
        choices=list(PAIRS.keys()),
        help="Which pair to test: 32-33, 49-50, or 55-56"
    )
    args = parser.parse_args()
    run_test(args.pair)
