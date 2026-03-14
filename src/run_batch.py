# ---------------------------------------------------------------------------
# iar-lens | run_batch.py
# Batch runner — static input dictionary defines all pairs to process
# For each pair runs all 3 phases and produces a change report .md
# ---------------------------------------------------------------------------

import os
import sys
import logging

# run_batch.py lives in src/ — project root is one level up
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

import config
from iar_compare      import run_comparison
from iar_agent        import run_agent
from report_generator import generate_report
import asyncio

def run_agent_sync():
    """Sync wrapper around the async run_agent() for use in batch processing."""
    asyncio.run(run_agent())

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# STATIC INPUT — add or remove pairs here
# Each entry: { "label": output filename prefix, "source": v1 file, "target": v2 file }
# ---------------------------------------------------------------------------

FLOW_DUMP = os.path.join(project_root, "flow-dump")
OUTPUT    = os.path.join(project_root, config.OUTPUT_DIR)

PAIRS = [
    # {
    #     "label"  : "32-33",
    #     "source" : os.path.join(FLOW_DUMP, "32-33", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "32-33", "FACTORYDOCK-TEST-02.car"),
    # },
    # {
    #     "label"  : "34-35",
    #     "source" : os.path.join(FLOW_DUMP, "34-35", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "34-35", "FACTORYDOCK-TEST-02.car"),
    # },
    {
        "label"  : "36-37",
        "source" : os.path.join(FLOW_DUMP, "36-37", "FACTORYDOCK-TEST-01.car"),
        "target" : os.path.join(FLOW_DUMP, "36-37", "FACTORYDOCK-TEST-02.car"),
    },
    # {
    #     "label"  : "39-40",
    #     "source" : os.path.join(FLOW_DUMP, "39-40", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "39-40", "FACTORYDOCK-TEST-02.car"),
    # },
    # {
    #     "label"  : "41-42",
    #     "source" : os.path.join(FLOW_DUMP, "41-42", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "41-42", "FACTORYDOCK-TEST-02.car"),
    # },
    # {
    #     "label"  : "45-46",
    #     "source" : os.path.join(FLOW_DUMP, "45-46", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "45-46", "FACTORYDOCK-TEST-02.car"),
    # },
    # {
    #     "label"  : "47-48",
    #     "source" : os.path.join(FLOW_DUMP, "47-48", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "47-48", "FACTORYDOCK-TEST-02.car"),
    # },
    # {
    #     "label"  : "49-50",
    #     "source" : os.path.join(FLOW_DUMP, "49-50", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "49-50", "FACTORYDOCK-TEST-02.car"),
    # },
    # {
    #     "label"  : "51-52",
    #     "source" : os.path.join(FLOW_DUMP, "51-52", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "51-52", "FACTORYDOCK-TEST-02.car"),
    # },
    # {
    #     "label"  : "53-54",
    #     "source" : os.path.join(FLOW_DUMP, "53-54", "FACTORYDOCK-TEST-01.car"),
    #     "target" : os.path.join(FLOW_DUMP, "53-54", "FACTORYDOCK-TEST-02.car"),
    # },
    # {
    #     "label"  : "INT303",
    #     "source" : os.path.join(FLOW_DUMP, "INT303_INVENTOR_EI_RECONCIL_03.00.0001.iar.zip"),
    #     "target" : os.path.join(FLOW_DUMP, "INT303_INVENTOR_EI_RECONCIL_03.00.0011.iar.zip"),
    # },
]

# ---------------------------------------------------------------------------

def run_batch():
    os.makedirs(OUTPUT, exist_ok=True)
    results = []

    for i, pair in enumerate(PAIRS, 1):
        label       = pair["label"]
        source_path = pair["source"]
        target_path = pair["target"]

        print(f"\n{'='*60}")
        print(f"[{i}/{len(PAIRS)}] {label}")
        print(f"  Source : {os.path.basename(source_path)}")
        print(f"  Target : {os.path.basename(target_path)}")
        print(f"{'='*60}")

        delta_path  = os.path.join(OUTPUT, f"{label}_delta.json")
        report_path = os.path.join(OUTPUT, "report.json")
        md_path     = os.path.join(OUTPUT, f"{label}_change_report.md")

        try:
            print(f"\n▶ Phase 1: Structural comparison...")
            # Option B — patch config at runtime before calling run_comparison()
            config.SOURCE_IAR  = source_path
            config.TARGET_IAR  = target_path
            config.OUTPUT_DIR  = OUTPUT
            config.LABEL       = label
            config.WORKSPACE_DIR = os.path.join(project_root, "workspace", label)
            run_comparison()

            print(f"\n▶ Phase 2: AI analysis...")
            run_agent_sync()

            print(f"\n▶ Phase 3: Generating report...")
            generate_report(delta_path=delta_path, report_path=report_path, output_path=md_path)

            print(f"\n✅ Done: output/{label}_change_report.md")
            results.append((label, "SUCCESS"))

        except Exception as e:
            logger.error(f"Failed '{label}': {e}", exc_info=True)
            results.append((label, f"FAILED — {e}"))

    # Summary
    print(f"\n{'='*60}")
    print(f"BATCH SUMMARY — {len(PAIRS)} pair(s)")
    print(f"{'='*60}")
    for label, status in results:
        icon = "✅" if status == "SUCCESS" else "❌"
        print(f"  {icon}  {label:25s} {status}")
    print(f"{'='*60}")
    print(f"\nReports in: {OUTPUT}")


if __name__ == "__main__":
    run_batch()