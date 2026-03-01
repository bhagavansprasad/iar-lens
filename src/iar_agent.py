# ---------------------------------------------------------------------------
# iar-lens | src/iar_agent.py
# Phase 3 — LangGraph Investigator Agent
# Reads processor files and produces a structured delta report using Gemini
# ---------------------------------------------------------------------------

import os
import sys
import json
import logging
import re
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

from langgraph.graph import StateGraph, START, END
import google.generativeai as genai

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import config
from iar_agent_state   import IARReviewAgentState
from iar_agent_prompts import format_investigate_prompt, format_synthesize_prompt
from file_reader       import list_processor_files, read_file

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gemini helper
# ---------------------------------------------------------------------------

def _get_gemini_model():
    """Configure and return a Gemini model instance."""
    api_key = os.getenv(config.GEMINI_API_KEY_ENV)
    if not api_key:
        raise EnvironmentError(
            f"Gemini API key not found. "
            f"Set the '{config.GEMINI_API_KEY_ENV}' environment variable."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(config.GEMINI_MODEL)


def _parse_llm_json(response_text: str) -> Dict | None:
    """Extract and parse JSON from Gemini response."""
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
    return None


# ---------------------------------------------------------------------------
# NODE: INIT
# ---------------------------------------------------------------------------

async def init_node(state: IARReviewAgentState) -> IARReviewAgentState:
    """
    Loads delta.json and initializes all working state fields.
    """
    print("\n[INIT] Loading delta and initializing state...")

    delta_path = state.get("delta_path", config.OUTPUT_DIR + "delta.json")

    resolved = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", delta_path)
    )

    if not os.path.exists(resolved):
        raise FileNotFoundError(f"delta.json not found at: {resolved}")

    with open(resolved, "r", encoding="utf-8") as f:
        delta = json.load(f)

    state["delta"]       = delta
    state["version_from"] = delta.get("version_from", state.get("version_from", ""))
    state["version_to"]   = delta.get("version_to",   state.get("version_to", ""))
    state["integration"]  = delta.get("integration",  state.get("integration", ""))
    state["reading_list"] = []
    state["files_read"]   = []
    state["findings"]     = []
    state["final_report"] = None

    print(f"✅ Loaded delta: {state['integration']} "
          f"v{state['version_from']} → v{state['version_to']}")
    print(f"   New: {delta['statistics']['new_steps_count']} | "
          f"Removed: {delta['statistics']['removed_steps_count']} | "
          f"Shifted: {delta['statistics']['positionally_shifted']} | "
          f"Unchanged: {delta['statistics']['unchanged_count']}")

    return state


# ---------------------------------------------------------------------------
# NODE: BUILD_READING_LIST
# ---------------------------------------------------------------------------

async def build_reading_list_node(state: IARReviewAgentState) -> IARReviewAgentState:
    """
    Pure Python node — builds a focused reading list of processors
    to investigate based on the delta (new + removed steps only).
    Shifted and unchanged steps are excluded — no investigation needed.
    """
    print("\n[BUILD_READING_LIST] Building focused processor reading list...")

    delta       = state["delta"]
    reading_list = []

    # New steps — investigate in target version
    for step in delta["delta"]["new_steps"]:
        reading_list.append({
            "processor_id": step["processor_id"],
            "step_name"   : step["name"],
            "step_type"   : step["type"],
            "status"      : "NEW",
            "version"     : state["version_to"],
            "adapter_ref" : step.get("adapter_ref")
        })

    # Removed steps — investigate in source version
    for step in delta["delta"]["removed_steps"]:
        reading_list.append({
            "processor_id": step["processor_id"],
            "step_name"   : step["name"],
            "step_type"   : step["type"],
            "status"      : "REMOVED",
            "version"     : state["version_from"],
            "adapter_ref" : step.get("adapter_ref")
        })

    state["reading_list"] = reading_list

    print(f"✅ Reading list built: {len(reading_list)} processors to investigate")
    for item in reading_list:
        print(f"   [{item['status']:7}] {item['step_name']:35} "
              f"({item['step_type']}) — {item['processor_id']}")

    return state


# ---------------------------------------------------------------------------
# NODE: INVESTIGATE
# ---------------------------------------------------------------------------

async def investigate_node(state: IARReviewAgentState) -> IARReviewAgentState:
    """
    For each processor in the reading list:
      1. List its files using file_reader
      2. Read each file's content
      3. Send to Gemini for analysis
      4. Collect findings
    """
    print("\n[INVESTIGATE] Investigating processors with Gemini...")

    model        = _get_gemini_model()
    reading_list = state["reading_list"]
    findings     = []
    all_files_read = []

    for i, item in enumerate(reading_list, 1):
        processor_id = item["processor_id"]
        step_name    = item["step_name"]
        step_type    = item["step_type"]
        status       = item["status"]
        version      = item["version"]

        print(f"\n   [{i}/{len(reading_list)}] {status} — {step_name} ({processor_id})")

        # Step 1: List files for this processor
        file_list_result = list_processor_files(processor_id, version=version)

        if not file_list_result["success"]:
            logger.warning(f"No files found for {processor_id}: {file_list_result['error']}")
            findings.append({
                "processor_id"   : processor_id,
                "step_name"      : step_name,
                "step_type"      : step_type,
                "status"         : status,
                "purpose"        : "Files not found — could not investigate",
                "business_impact": "Unknown",
                "technical_detail": file_list_result["error"],
                "risk_level"     : "medium",
                "risk_reason"    : "Unable to read processor files"
            })
            continue

        files = file_list_result["files"]
        print(f"      Found {len(files)} file(s): "
              f"{[f['file_name'] for f in files]}")

        # Step 2: Read file contents
        file_contents = []
        for f in files:
            read_result = read_file(f["file_path"])
            if read_result["success"]:
                file_contents.append(read_result)
                all_files_read.append(read_result)

        # Step 3: Send to Gemini for analysis
        prompt = format_investigate_prompt(
            processor_id  = processor_id,
            step_name     = step_name,
            step_type     = step_type,
            status        = status,
            version       = version,
            files         = files,
            file_contents = file_contents
        )

        try:
            response      = model.generate_content(prompt)
            response_text = response.text.strip()
            finding       = _parse_llm_json(response_text)

            if finding:
                print(f"      ✅ Gemini: {finding.get('purpose', 'No purpose extracted')[:80]}")
                findings.append(finding)
            else:
                logger.warning(f"Gemini returned no parseable JSON for {processor_id}")
                findings.append({
                    "processor_id"   : processor_id,
                    "step_name"      : step_name,
                    "step_type"      : step_type,
                    "status"         : status,
                    "purpose"        : "Gemini analysis failed",
                    "business_impact": "Unknown",
                    "technical_detail": response_text[:300],
                    "risk_level"     : "medium",
                    "risk_reason"    : "LLM response could not be parsed"
                })

        except Exception as e:
            logger.error(f"Gemini call failed for {processor_id}: {e}")
            findings.append({
                "processor_id"   : processor_id,
                "step_name"      : step_name,
                "step_type"      : step_type,
                "status"         : status,
                "purpose"        : f"Error during investigation: {str(e)}",
                "business_impact": "Unknown",
                "technical_detail": str(e),
                "risk_level"     : "medium",
                "risk_reason"    : "Investigation error"
            })

    state["findings"]   = findings
    state["files_read"] = all_files_read

    print(f"\n✅ Investigation complete: {len(findings)} findings, "
          f"{len(all_files_read)} files read")

    return state


# ---------------------------------------------------------------------------
# NODE: SYNTHESIZE
# ---------------------------------------------------------------------------

async def synthesize_node(state: IARReviewAgentState) -> IARReviewAgentState:
    """
    Sends all findings to Gemini to produce the final structured
    delta report with overall risk, recommendation, and plain English summary.
    """
    print("\n[SYNTHESIZE] Generating final report with Gemini...")

    model    = _get_gemini_model()
    delta    = state["delta"]
    findings = state["findings"]

    prompt = format_synthesize_prompt(
        integration    = state["integration"],
        version_from   = state["version_from"],
        version_to     = state["version_to"],
        statistics     = delta["statistics"],
        findings       = findings,
        shifted_steps  = delta["delta"]["positionally_shifted"],
        unchanged_steps= delta["delta"]["unchanged_steps"]
    )

    try:
        response      = model.generate_content(prompt)
        response_text = response.text.strip()
        report        = _parse_llm_json(response_text)

        if not report:
            logger.error("Gemini synthesis returned no parseable JSON")
            report = {
                "integration" : state["integration"],
                "version_from": state["version_from"],
                "version_to"  : state["version_to"],
                "overall_risk": "unknown",
                "recommendation": "manual_review_required",
                "summary"     : "Automated synthesis failed — manual review required.",
                "new_steps"   : [],
                "removed_steps": [],
                "key_observations": ["Synthesis failed — raw findings available in agent state"],
                "conditions"  : []
            }

    except Exception as e:
        logger.error(f"Gemini synthesis failed: {e}")
        report = {
            "integration" : state["integration"],
            "version_from": state["version_from"],
            "version_to"  : state["version_to"],
            "overall_risk": "unknown",
            "recommendation": "manual_review_required",
            "summary"     : f"Synthesis error: {str(e)}",
            "new_steps"   : [],
            "removed_steps": [],
            "key_observations": [],
            "conditions"  : []
        }

    # Add metadata
    report["generated_at"]  = datetime.now(timezone.utc).isoformat()
    report["files_read"]    = len(state["files_read"])
    report["processors_investigated"] = len(state["findings"])

    # Write final report to output
    output_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", config.OUTPUT_DIR, "report.json")
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    state["final_report"] = report

    print(f"\n✅ Final report generated")
    print(f"   Overall risk    : {report.get('overall_risk', 'N/A').upper()}")
    print(f"   Recommendation  : {report.get('recommendation', 'N/A')}")
    print(f"   Summary         : {report.get('summary', '')[:120]}...")
    print(f"   Output written  : {output_path}")

    return state


# ---------------------------------------------------------------------------
# GRAPH CONSTRUCTION
# ---------------------------------------------------------------------------

def create_iar_review_agent_graph():
    """Build and compile the IAR Review Agent LangGraph."""
    print("\n🔧 Building IAR Review Agent Graph...")

    workflow = StateGraph(IARReviewAgentState)

    # Add nodes
    workflow.add_node("INIT",              init_node)
    workflow.add_node("BUILD_READING_LIST", build_reading_list_node)
    workflow.add_node("INVESTIGATE",       investigate_node)
    workflow.add_node("SYNTHESIZE",        synthesize_node)

    # Sequential flow
    workflow.add_edge(START,               "INIT")
    workflow.add_edge("INIT",              "BUILD_READING_LIST")
    workflow.add_edge("BUILD_READING_LIST","INVESTIGATE")
    workflow.add_edge("INVESTIGATE",       "SYNTHESIZE")
    workflow.add_edge("SYNTHESIZE",         END)

    app = workflow.compile()

    print("✅ IAR Review Agent compiled\n")
    return app


# Export graph
iar_review_agent_graph = create_iar_review_agent_graph()


# ---------------------------------------------------------------------------
# MAIN — entry point for running the agent
# ---------------------------------------------------------------------------

async def run_agent():
    """Run the IAR Review Agent."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    initial_state = IARReviewAgentState(
        delta_path   = config.OUTPUT_DIR + "delta.json",
        version_from = "",   # will be populated from delta.json in INIT
        version_to   = "",
        integration  = "",
        delta        = None,
        reading_list = None,
        files_read   = None,
        findings     = None,
        final_report = None
    )

    result = await iar_review_agent_graph.ainvoke(initial_state)

    print("\n" + "=" * 60)
    print("IAR REVIEW AGENT — COMPLETE")
    print("=" * 60)
    print(f"Integration  : {result['integration']}")
    print(f"From → To    : v{result['version_from']} → v{result['version_to']}")
    print(f"Findings     : {len(result['findings'])}")
    print(f"Files read   : {len(result['files_read'])}")
    print(f"Report       : output/report.json")
    print("=" * 60)

    return result


if __name__ == "__main__":
    asyncio.run(run_agent())
