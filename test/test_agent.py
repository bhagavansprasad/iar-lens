# ---------------------------------------------------------------------------
# test_agent.py
# Standalone test for the Phase 2 IAR Review Agent.
#
# Assumes Stage 1 (run_comparison) has already run and produced:
#   output/<label>_delta.json
#   output/<label>_flow_context.json
#
# Usage (from project root):
#   python test/test_agent.py 55-56
#   python test/test_agent.py 32-33
#   python test/test_agent.py 49-50
# ---------------------------------------------------------------------------

import os
import sys
import asyncio
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
    """Verify Stage 1 outputs exist before running the agent."""
    required = [
        (os.path.join(output_dir, f"{label}_delta.json"),           f"{label}_delta.json"),
        (os.path.join(output_dir, f"{label}_flow_context.json"),   f"{label}_flow_context.json"),
    ]
    ok = True
    for path, name in required:
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
    print(f"test_agent — pair: {pair_key}")
    print(f"{'='*60}")

    # Patch config so agent finds the right files
    config.OUTPUT_DIR = output_dir + os.sep
    config.LABEL      = label

    # Pre-check Stage 1 outputs
    print(f"\n[PRE-CHECK] Verifying Stage 1 outputs in output/...")
    if not check_inputs(output_dir, label):
        print(f"\n❌ Stage 1 outputs missing. Run Stage 1 first:")
        print(f"   Ensure pair {label} is active in run_batch.py, then:")
        print(f"   python src/run_batch.py")
        print(f"   (or run test/test_flow_understander.py {label} and copy outputs)")
        sys.exit(1)

    # Run agent
    print(f"\n[AGENT] Running Phase 2 agent for {label}...")
    from iar_agent import run_agent
    result = asyncio.run(run_agent())

    # Print results
    print(f"\n{'='*60}")
    print(f"RESULTS — pair: {label}")
    print(f"{'='*60}")
    report = result.get("final_report", {})
    print(f"  Overall risk   : {report.get('overall_risk', '?').upper()}")
    print(f"  Recommendation : {report.get('recommendation', '?')}")
    print(f"  Summary        :\n    {report.get('summary', '—')}")

    new_steps     = report.get("new_steps", [])
    removed_steps = report.get("removed_steps", [])

    if new_steps:
        print(f"\n  New steps ({len(new_steps)}):")
        for s in new_steps:
            print(f"    [{s.get('risk_level','?'):6}] {s.get('step_name','?'):35} — {s.get('purpose','')[:70]}")

    if removed_steps:
        print(f"\n  Removed steps ({len(removed_steps)}):")
        for s in removed_steps:
            print(f"    [{s.get('risk_level','?'):6}] {s.get('step_name','?'):35} — {s.get('purpose','')[:70]}")

    print(f"\n  Key observations:")
    for obs in report.get("key_observations", []):
        print(f"    • {obs}")

    if report.get("conditions"):
        print(f"\n  Conditions:")
        for c in report.get("conditions", []):
            print(f"    • {c}")

    print(f"\n  {label}_report.json written to: {os.path.join(output_dir, label + '_report.json')}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Phase 2 agent in isolation")
    parser.add_argument(
        "pair",
        choices=list(PAIRS.keys()),
        help="Which pair to test: 32-33, 49-50, or 55-56"
    )
    args = parser.parse_args()
    run_test(args.pair)
