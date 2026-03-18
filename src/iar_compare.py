# ---------------------------------------------------------------------------
# oic-lens | src/iar_compare.py
# Step 1 orchestrator — extracts both CAR/IAR files, runs flow_compare,
# writes {label}_delta.json to output/.
# ---------------------------------------------------------------------------

import os
import sys
import json
import logging

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

import config
from extractor    import extract_iar
from flow_compare import extract_steps, compute_delta

logger = logging.getLogger(__name__)


def run_comparison():
    """
    Extract source + target CAR/IAR files, compute delta, write delta.json.
    Reads all paths from config (run_batch.py overrides config at runtime).
    """
    workspace = os.path.abspath(os.path.join(project_root, config.WORKSPACE_DIR))
    output    = os.path.abspath(os.path.join(project_root, config.OUTPUT_DIR))
    os.makedirs(workspace, exist_ok=True)
    os.makedirs(output,    exist_ok=True)

    label       = getattr(config, "LABEL", "output")
    source_path = os.path.abspath(os.path.join(project_root, config.SOURCE_IAR))
    target_path = os.path.abspath(os.path.join(project_root, config.TARGET_IAR))

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

    # --- Delta ---
    delta = compute_delta(source_data, target_data)

    # Attach extract paths so downstream steps can find workspace files
    delta["source_extract_path"] = src_extract["extract_path"]
    delta["target_extract_path"] = tgt_extract["extract_path"]
    delta["integration_code"]    = source_data["integration_code"]
    delta["integration_name"]    = source_data["integration_name"]

    # --- Write ---
    delta_path = os.path.join(output, f"{label}_delta.json")
    with open(delta_path, "w", encoding="utf-8") as f:
        json.dump(delta, f, indent=2)

    logger.info(f"Delta written: {delta_path}")
    _print_summary(delta, delta_path)

    return delta_path


def _print_summary(delta: dict, delta_path: str):
    print(f"\n  Integration : {delta.get('integration_name')} ({delta.get('integration_code')})")
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
    run_comparison()
