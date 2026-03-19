# ---------------------------------------------------------------------------
# oic-lens | src/iar_compare.py
# Step 1 orchestrator — extracts both CAR/IAR files, runs flow_compare,
# writes {label}_delta.json to output/.
#
# Run with a specific pair label:
#   python src/iar_compare.py 32-33
#   python src/iar_compare.py 49-50
#   python src/iar_compare.py 55-56
#
# Omit label to use config.py defaults.
# run_batch.py sets label + paths at runtime for each pair.
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
from extractor    import extract_iar
from flow_compare import extract_steps, compute_delta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known pairs — label -> (source_rel_path, target_rel_path)
# ---------------------------------------------------------------------------
KNOWN_PAIRS = {
    "32-33": ("flow-dump/32-33/FACTORYDOCK-TEST-32.car",  "flow-dump/32-33/FACTORYDOCK-TEST-33.car"),
    "34-35": ("flow-dump/34-35/FACTORYDOCK-TEST-34.car",  "flow-dump/34-35/FACTORYDOCK-TEST-35.car"),
    "36-37": ("flow-dump/36-37/FACTORYDOCK-TEST-36.car",  "flow-dump/36-37/FACTORYDOCK-TEST-37.car"),
    "39-40": ("flow-dump/39-40/FACTORYDOCK-TEST-39.car",  "flow-dump/39-40/FACTORYDOCK-TEST-40.car"),
    "41-42": ("flow-dump/41-42/FACTORYDOCK-TEST-41.car",  "flow-dump/41-42/FACTORYDOCK-TEST-42.car"),
    "45-46": ("flow-dump/45-46/FACTORYDOCK-TEST-45.car",  "flow-dump/45-46/FACTORYDOCK-TEST-46.car"),
    "47-48": ("flow-dump/47-48/FACTORYDOCK-TEST-47.car",  "flow-dump/47-48/FACTORYDOCK-TEST-48.car"),
    "49-50": ("flow-dump/49-50/FACTORYDOCK-TEST-49.car",  "flow-dump/49-50/FACTORYDOCK-TEST-50.car"),
    "51-52": ("flow-dump/51-52/FACTORYDOCK-TEST-51.car",  "flow-dump/51-52/FACTORYDOCK-TEST-52.car"),
    "53-54": ("flow-dump/53-54/FACTORYDOCK-TEST-53.car",  "flow-dump/53-54/FACTORYDOCK-TEST-54.car"),
    "55-56": ("flow-dump/55-56/INT03.00.0001.iar",         "flow-dump/55-56/INT03.00.0011.iar"),
}


# ---------------------------------------------------------------------------
# Core function — called by run_batch.py and __main__
# ---------------------------------------------------------------------------

def run_comparison(label=None, source_path=None, target_path=None):
    """
    Extract source + target CAR/IAR files, compute delta, write {label}_delta.json.

    Priority for paths:
      1. Arguments passed directly (run_batch.py uses this)
      2. Label lookup from KNOWN_PAIRS
      3. config.py defaults
    """
    # Resolve label
    if label is None:
        label = getattr(config, "LABEL", "output")

    # Resolve source / target paths
    if source_path is None or target_path is None:
        if label in KNOWN_PAIRS:
            src_rel, tgt_rel = KNOWN_PAIRS[label]
            source_path = os.path.join(project_root, src_rel)
            target_path = os.path.join(project_root, tgt_rel)
        else:
            source_path = os.path.abspath(os.path.join(project_root, config.SOURCE_IAR))
            target_path = os.path.abspath(os.path.join(project_root, config.TARGET_IAR))

    workspace = os.path.abspath(os.path.join(project_root, config.WORKSPACE_DIR))
    output    = os.path.abspath(os.path.join(project_root, config.OUTPUT_DIR))
    os.makedirs(workspace, exist_ok=True)
    os.makedirs(output,    exist_ok=True)

    # --- Extract ---
    logger.info(f"Extracting source: {source_path}")
    src_extract = extract_iar(source_path, workspace)
    if not src_extract["success"]:
        raise RuntimeError(f"Source extraction failed: {src_extract['error']}")

    logger.info(f"Extracting target: {target_path}")
    tgt_extract = extract_iar(target_path, workspace)
    if not tgt_extract["success"]:
        raise RuntimeError(f"Target extraction failed: {tgt_extract['error']}")

    # --- Parse ---
    logger.info("Parsing source project.xml")
    source_data = extract_steps(src_extract["project_xml"])
    if not source_data["success"]:
        raise RuntimeError(f"Source parse failed: {source_data['error']}")

    logger.info("Parsing target project.xml")
    target_data = extract_steps(tgt_extract["project_xml"])
    if not target_data["success"]:
        raise RuntimeError(f"Target parse failed: {target_data['error']}")

    # --- Delta (M1 + M2: pass extract paths so file diff runs) ---
    delta = compute_delta(
        source_data, target_data,
        source_extract_path=src_extract["extract_path"],
        target_extract_path=tgt_extract["extract_path"],
    )

    # Attach paths so downstream steps (M2+) can find workspace files
    delta["label"]                = label
    delta["source_extract_path"]  = src_extract["extract_path"]
    delta["target_extract_path"]  = tgt_extract["extract_path"]
    delta["integration_code"]     = source_data["integration_code"]
    delta["integration_name"]     = source_data["integration_name"]

    # --- Write ---
    delta_path = os.path.join(output, f"{label}_delta.json")
    with open(delta_path, "w", encoding="utf-8") as f:
        json.dump(delta, f, indent=2)

    logger.info(f"Delta written: {delta_path}")
    _print_summary(delta, delta_path)

    return delta_path


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(delta: dict, delta_path: str):
    print(f"\n  Integration : {delta.get('integration_name')} ({delta.get('integration_code')})")
    print(f"  Label       : {delta.get('label')}")
    print(f"  Versions    : v{delta['source_version']} -> v{delta['target_version']}")
    print(f"  Processors  : {delta['source_count']} -> {delta['target_count']}")
    print(f"  New steps   : {len(delta['new_steps'])}")
    print(f"  Removed     : {len(delta['removed_steps'])}")
    print(f"  Shifted     : {len(delta['positionally_shifted'])}")
    print(f"  Delta JSON  : {delta_path}")

    if delta["new_steps"]:
        print("\n  New processor IDs:")
        for p in delta["new_steps"]:
            print(f"    {p['processor_id']:20s}  {p['type']:22s}  {p['name']}")

    if delta["removed_steps"]:
        print("\n  Removed processor IDs:")
        for p in delta["removed_steps"]:
            print(f"    {p['processor_id']:20s}  {p['type']:22s}  {p['name']}")


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Step 1 — extract CAR/IAR and compute structural delta",
        epilog=(
            "Examples:\n"
            "  python src/iar_compare.py 32-33\n"
            "  python src/iar_compare.py 49-50\n"
            "  python src/iar_compare.py 55-56\n"
            "  python src/iar_compare.py          # uses config.py defaults"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "label", nargs="?", metavar="LABEL",
        help=f"Pair label to process. Known: {sorted(KNOWN_PAIRS.keys())}",
    )
    args = parser.parse_args()

    if args.label and args.label not in KNOWN_PAIRS:
        print(f"Unknown label: {args.label!r}")
        print(f"Known labels : {sorted(KNOWN_PAIRS.keys())}")
        sys.exit(1)

    run_comparison(label=args.label)