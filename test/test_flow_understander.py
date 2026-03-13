# ---------------------------------------------------------------------------
# test_flow_understander.py
# Standalone test for flow_understander.understand_flow()
#
# Does NOT run the full pipeline — directly feeds extracted flow data
# into understand_flow() and prints the result for review.
#
# Usage (from project root):
#   python test/test_flow_understander.py 55-56
#   python test/test_flow_understander.py 32-33
#   python test/test_flow_understander.py 49-50
# ---------------------------------------------------------------------------

import os
import sys
import json
import argparse

# Allow imports from src/ and project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from flow_compare      import extract_steps, compute_delta
from flow_understander import understand_flow

# ---------------------------------------------------------------------------
# Test pair definitions — project.xml paths for each pair
# ---------------------------------------------------------------------------

PAIRS = {
    "32-33": {
        "source_xml" : "workspace/32-33/FACTORYDOCK-TEST-32/project/integrations/ALTERA_CREATE_SO_INTEGRAT_01.00.0032/PROJECT-INF/project.xml",
        "target_xml" : "workspace/32-33/FACTORYDOCK-TEST-33/project/integrations/ALTERA_CREATE_SO_INTEGRAT_01.00.0033/PROJECT-INF/project.xml",
        "label"      : "32-33",
    },
    "49-50": {
        "source_xml" : "workspace/49-50/FACTORYDOCK-TEST-49/project/integrations/ALTERA_CREATE_SO_INTEGRAT_01.00.0049/PROJECT-INF/project.xml",
        "target_xml" : "workspace/49-50/FACTORYDOCK-TEST-50/project/integrations/ALTERA_CREATE_SO_INTEGRAT_01.00.0050/PROJECT-INF/project.xml",
        "label"      : "49-50",
    },
    "55-56": {
        "source_xml" : "workspace/55-56/INT03.00.0001/icspackage/project/INT303_INVENTOR_EI_RECONCIL_03.00.0001/PROJECT-INF/project.xml",
        "target_xml" : "workspace/55-56/INT03.00.0011/icspackage/project/INT303_INVENTOR_EI_RECONCIL_03.00.0011/PROJECT-INF/project.xml",
        "label"      : "55-56",
    },
}

# ---------------------------------------------------------------------------

def run_test(pair_key: str):
    pair = PAIRS.get(pair_key)
    if not pair:
        print(f"Unknown pair '{pair_key}'. Choose from: {list(PAIRS.keys())}")
        sys.exit(1)

    source_xml = os.path.join(project_root, pair["source_xml"])
    target_xml = os.path.join(project_root, pair["target_xml"])
    output_dir = os.path.join(project_root, "output", "test")

    print(f"\n{'='*60}")
    print(f"test_flow_understander — pair: {pair_key}")
    print(f"{'='*60}")
    print(f"  Source XML : {source_xml}")
    print(f"  Target XML : {target_xml}")

    # ── Step 1: Extract steps from both XMLs ────────────────────────────────
    print(f"\n[1/3] Extracting steps from project.xml files...")

    source_data = extract_steps(source_xml)
    if not source_data["success"]:
        print(f"  ❌ Source extraction failed: {source_data['error']}")
        sys.exit(1)

    target_data = extract_steps(target_xml)
    if not target_data["success"]:
        print(f"  ❌ Target extraction failed: {target_data['error']}")
        sys.exit(1)

    print(f"  ✅ Source: {source_data['integration_name']} v{source_data['version']} — {len(source_data['steps'])} steps, {len(source_data['applications'])} adapters")
    print(f"  ✅ Target: {target_data['integration_name']} v{target_data['version']} — {len(target_data['steps'])} steps, {len(target_data['applications'])} adapters")

    # ── Step 2: Compute delta ────────────────────────────────────────────────
    print(f"\n[2/3] Computing delta...")

    delta = compute_delta(source_data, target_data)
    print(f"  ✅ New: {len(delta['new_steps'])} | Removed: {len(delta['removed_steps'])} | Shifted: {len(delta['positionally_shifted'])} | Unchanged: {len(delta['unchanged_steps'])}")

    # ── Step 3: Call understand_flow ─────────────────────────────────────────
    print(f"\n[3/3] Calling understand_flow() — Gemini in progress...")

    context = understand_flow(
        integration  = source_data["integration_name"],
        version_from = source_data["version"],
        version_to   = target_data["version"],
        source_data  = source_data,
        target_data  = target_data,
        delta        = delta,
        output_dir   = output_dir,
        label        = pair["label"]
    )

    # ── Print results ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS — flow_context.json")
    print(f"{'='*60}")

    print(f"\n📌 change_type     : {context.get('change_type', '?')}")
    print(f"📌 change_type_reason: {context.get('change_type_reason', '?')}")

    print(f"\n📋 integration_purpose:")
    print(f"   {context.get('integration_purpose', '—')}")

    print(f"\n📋 flow_before:")
    print(f"   {context.get('flow_before', '—')}")

    print(f"\n📋 flow_after:")
    print(f"   {context.get('flow_after', '—')}")

    print(f"\n📋 change_narrative:")
    print(f"   {context.get('change_narrative', '—')}")

    print(f"\n🔌 systems_involved:")
    si = context.get("systems_involved", {})
    print(f"   Source  : {si.get('source', [])}")
    print(f"   Target  : {si.get('target', [])}")
    print(f"   Added   : {si.get('added', [])}")
    print(f"   Removed : {si.get('removed', [])}")

    print(f"\n🧱 logical_blocks_source:")
    for b in context.get("logical_blocks_source", []):
        print(f"   [{b.get('step_range','?'):>6}]  {b.get('block_name','?'):30s}  {b.get('description','')[:80]}")

    print(f"\n🧱 logical_blocks_target:")
    for b in context.get("logical_blocks_target", []):
        print(f"   [{b.get('step_range','?'):>6}]  {b.get('block_name','?'):30s}  {b.get('description','')[:80]}")

    filename = f"{pair['label']}_flow_context.json"
    out_path = os.path.join(output_dir, filename)
    print(f"\n✅ Full JSON written to: {out_path}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test flow_understander.py in isolation")
    parser.add_argument(
        "pair",
        choices=list(PAIRS.keys()),
        help="Which pair to test: 32-33, 49-50, or 55-56"
    )
    args = parser.parse_args()
    run_test(args.pair)
