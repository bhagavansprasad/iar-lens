# ---------------------------------------------------------------------------
# iar-lens | src/iar_compare.py
# Entry point for Phase 1 — orchestrates extraction and comparison
# ---------------------------------------------------------------------------

import os
import sys
import json
import logging
import shutil
from datetime import datetime, timezone

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from extractor    import extract_iar
from flow_compare      import extract_steps, compute_delta
from flow_understander import understand_flow


def setup_logging():
    """Configure logging based on config.LOG_LEVEL."""
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def run_comparison() -> dict:
    """
    Main orchestration function for Phase 1.

    Steps:
        1. Extract both IAR files into workspace
        2. Parse project.xml from each
        3. Compute the flow step delta
        4. Write delta.json to output directory

    Returns:
        Final delta report as a dict
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("iar-lens | Phase 1 — Structural Extractor")
    logger.info("=" * 60)

    # Ensure workspace and output directories exist
    os.makedirs(config.WORKSPACE_DIR, exist_ok=True)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # -----------------------------------------------------------------------
    # Step 1: Extract both IAR files
    # -----------------------------------------------------------------------
    logger.info("Step 1: Extracting IAR files")

    source_extraction = extract_iar(config.SOURCE_IAR, config.WORKSPACE_DIR)
    if not source_extraction["success"]:
        logger.error(f"Source IAR extraction failed: {source_extraction['error']}")
        sys.exit(1)

    target_extraction = extract_iar(config.TARGET_IAR, config.WORKSPACE_DIR)
    if not target_extraction["success"]:
        logger.error(f"Target IAR extraction failed: {target_extraction['error']}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 2: Parse project.xml from each extracted IAR
    # -----------------------------------------------------------------------
    logger.info("Step 2: Parsing project.xml files")

    source_data = extract_steps(source_extraction["project_xml"])
    if not source_data["success"]:
        logger.error(f"Source project.xml parsing failed: {source_data['error']}")
        sys.exit(1)

    target_data = extract_steps(target_extraction["project_xml"])
    if not target_data["success"]:
        logger.error(f"Target project.xml parsing failed: {target_data['error']}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 3: Compute the flow step delta
    # -----------------------------------------------------------------------
    logger.info("Step 3: Computing flow step delta")

    delta = compute_delta(source_data, target_data)

    # -----------------------------------------------------------------------
    # Step 4: Assemble final report
    # -----------------------------------------------------------------------
    report = {
        "integration"   : source_data["integration_name"],
        "version_from"  : source_data["version"],
        "version_to"    : target_data["version"],
        "generated_at"  : datetime.now(timezone.utc).isoformat(),
        "statistics": {
            "source_step_count"      : len(source_data["steps"]),
            "target_step_count"      : len(target_data["steps"]),
            "new_steps_count"        : len(delta["new_steps"]),
            "removed_steps_count"    : len(delta["removed_steps"]),
            "reordered_count"        : len(delta["reordered_steps"]),
            "positionally_shifted"   : len(delta["positionally_shifted"]),
            "unchanged_count"        : len(delta["unchanged_steps"])
        },
        "delta": {
            "new_steps"           : delta["new_steps"],
            "removed_steps"       : delta["removed_steps"],
            "reordered_steps"     : delta["reordered_steps"],
            "positionally_shifted": delta["positionally_shifted"],
            "unchanged_steps"     : delta["unchanged_steps"]
        },
        "source_applications": source_data["applications"],
        "target_applications": target_data["applications"]
    }


    # -----------------------------------------------------------------------
    # Step 4b: Flow Understander — understand full flow context (Phase 1b)
    # -----------------------------------------------------------------------
    logger.info("Step 4b: Running Flow Understander (LLM)")

    label = getattr(config, "LABEL", None)
    try:
        understand_flow(
            integration  = source_data["integration_name"],
            version_from = source_data["version"],
            version_to   = target_data["version"],
            source_data  = source_data,
            target_data  = target_data,
            delta        = delta,
            output_dir   = config.OUTPUT_DIR,
            label        = label
        )
    except Exception as e:
        logger.warning(f"Flow Understander failed (non-fatal): {e}")

    # -----------------------------------------------------------------------
    # Step 5: Write delta.json
    # -----------------------------------------------------------------------
    output_file = os.path.join(config.OUTPUT_DIR, "delta.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Output written: {output_file}")

    # -----------------------------------------------------------------------
    # Step 6: Cleanup workspace if configured
    # -----------------------------------------------------------------------
    if not config.KEEP_WORKSPACE:
        logger.info("Cleaning up workspace...")
        shutil.rmtree(config.WORKSPACE_DIR, ignore_errors=True)
        logger.info("Workspace removed")
    else:
        logger.info("Workspace retained (KEEP_WORKSPACE=True)")

    # Summary
    logger.info("=" * 60)
    logger.info(f"Integration : {report['integration']}")
    logger.info(f"From        : v{report['version_from']}  →  v{report['version_to']}")
    logger.info(f"New steps   : {report['statistics']['new_steps_count']}")
    logger.info(f"Removed     : {report['statistics']['removed_steps_count']}")
    logger.info(f"Reordered   : {report['statistics']['reordered_count']}")
    logger.info(f"Shifted     : {report['statistics']['positionally_shifted']}")
    logger.info(f"Unchanged   : {report['statistics']['unchanged_count']}")
    logger.info("=" * 60)

    return report


if __name__ == "__main__":
    setup_logging()
    run_comparison()