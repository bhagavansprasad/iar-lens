# ---------------------------------------------------------------------------
# oic-lens | src/agent.py
# M4 — Agent Investigation (Step 2)
#
# LangGraph agent — LLM-driven investigation of all three change categories:
#   NEW processors   — read files from target version
#   REMOVED          — read files from source version
#   MODIFIED         — read files from BOTH versions (medium risk floor)
#
# Graph:
#   INIT → BUILD_INVENTORY → INVESTIGATE → SYNTHESIZE → END
#
# INVESTIGATE is LLM-driven: the LLM receives the full inventory upfront,
# calls read_processor_files() on demand, and calls finish_investigation()
# when done — which terminates the tool-use loop.
#
# Run standalone:
#   python src/agent.py 32-33
#   python src/agent.py 49-50
#   python src/agent.py 55-56
# ---------------------------------------------------------------------------

import os
import sys
import json
import logging
import re
import asyncio
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from langgraph.graph  import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools    import tool
import google.genai as genai
from google.genai import types as genai_types

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

import config
from agent_state   import AgentState
from agent_prompts import (
    format_investigate_prompt,
    format_synthesize_prompt,
    format_flow_context_section,
)
from file_reader import list_processor_files, read_file

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _get_gemini_client():
    return genai.Client()


def _parse_llm_json(text: str) -> Optional[Dict]:
    """Extract and parse the first JSON object from LLM response text."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Tool definitions — these are what the LLM calls during INVESTIGATE
# ---------------------------------------------------------------------------

# Global state for tools to write into (populated before INVESTIGATE runs)
_tool_state: Dict[str, Any] = {
    "files_read"    : [],
    "finish_called" : False,
    "findings"      : [],
}


@tool
def read_processor_files(processor_id: str, version: str) -> str:
    """
    Read all files for a processor from a specific version workspace.

    Args:
        processor_id: e.g. "processor_964"
        version: version string e.g. "01.00.0032" or "01.00.0033"
                 Use version_from for REMOVED, version_to for NEW.
                 For MODIFIED, call twice — once per version.

    Returns:
        JSON string with file contents for the processor.
    """
    result = list_processor_files(processor_id, version=version)

    if not result["success"]:
        return json.dumps({
            "processor_id": processor_id,
            "version"     : version,
            "success"     : False,
            "error"       : result["error"],
            "files"       : []
        })

    files_out = []
    for f in result["files"]:
        read_result = read_file(f["file_path"])
        entry = {
            "file_name": f["file_name"],
            "file_type": f["file_type"],
            "file_role": f["file_role"],
            "content"  : read_result.get("content", "") if read_result["success"] else f"[read error: {read_result.get('error')}]",
            "success"  : read_result["success"],
        }
        files_out.append(entry)
        if read_result["success"]:
            _tool_state["files_read"].append(f["file_path"])
            logger.info(f"  Tool read: {processor_id}/{f['file_name']} (v{version})")

    return json.dumps({
        "processor_id": processor_id,
        "version"     : version,
        "success"     : True,
        "file_count"  : len(files_out),
        "files"       : files_out,
    }, indent=2)


@tool
def finish_investigation(findings_json: str) -> str:
    """
    Signal that investigation is complete and submit all findings.

    Args:
        findings_json: JSON string with key "findings" — a list of per-processor
                       finding objects. Call this ONCE after investigating ALL
                       processors in the inventory.

    Returns:
        Confirmation string.
    """
    try:
        data = json.loads(findings_json)
        findings = data.get("findings", [])
    except (json.JSONDecodeError, AttributeError):
        # LLM may pass a plain list string — try parsing directly
        try:
            findings = json.loads(findings_json)
            if isinstance(findings, list):
                pass
            else:
                findings = []
        except Exception:
            findings = []

    _tool_state["finish_called"] = True
    _tool_state["findings"]      = findings
    logger.info(f"  finish_investigation called — {len(findings)} findings submitted")
    return f"Investigation complete. {len(findings)} findings recorded."


TOOLS = [read_processor_files, finish_investigation]

# Gemini tool declarations (for direct Gemini API calls)
TOOL_DECLARATIONS = [
    genai_types.Tool(function_declarations=[
        genai_types.FunctionDeclaration(
            name        = "read_processor_files",
            description = read_processor_files.__doc__,
            parameters  = genai_types.Schema(
                type       = genai_types.Type.OBJECT,
                properties = {
                    "processor_id": genai_types.Schema(type=genai_types.Type.STRING,
                                                        description="e.g. processor_964"),
                    "version"     : genai_types.Schema(type=genai_types.Type.STRING,
                                                        description="version string e.g. 01.00.0032"),
                },
                required = ["processor_id", "version"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name        = "finish_investigation",
            description = finish_investigation.__doc__,
            parameters  = genai_types.Schema(
                type       = genai_types.Type.OBJECT,
                properties = {
                    "findings_json": genai_types.Schema(
                        type        = genai_types.Type.STRING,
                        description = 'JSON string: {"findings": [...]}'
                    ),
                },
                required = ["findings_json"],
            ),
        ),
    ])
]


# ---------------------------------------------------------------------------
# NODE: INIT
# ---------------------------------------------------------------------------

async def init_node(state: AgentState) -> AgentState:
    """
    Loads {label}_delta.json and {label}_flow_context.json.
    Initialises all state fields.
    """
    print("\n[INIT] Loading delta and flow context...")

    label      = getattr(config, "LABEL", None)
    delta_name = f"{label}_delta.json" if label else "delta.json"
    delta_path = state.get("delta_path") or os.path.join(
        project_root, config.OUTPUT_DIR, delta_name
    )
    delta_path = os.path.abspath(delta_path)

    if not os.path.exists(delta_path):
        raise FileNotFoundError(f"delta.json not found: {delta_path}")

    with open(delta_path, "r", encoding="utf-8") as f:
        delta = json.load(f)

    state["delta"]         = delta
    state["version_from"]  = delta.get("source_version", state.get("version_from", ""))
    state["version_to"]    = delta.get("target_version", state.get("version_to", ""))
    state["integration"]   = (
        delta.get("integration_name") or
        delta.get("integration_code") or
        state.get("integration", "")
    )
    state["modified_steps"] = delta.get("modified_steps", [])
    state["files_read"]     = []
    state["findings"]       = []
    state["final_report"]   = None
    state["messages"]       = []

    new_count      = len(delta.get("new_steps", []))
    removed_count  = len(delta.get("removed_steps", []))
    modified_count = len(state["modified_steps"])

    print(f"✅ Delta loaded : {state['integration']}")
    print(f"   v{state['version_from']} → v{state['version_to']}")
    print(f"   New: {new_count} | Removed: {removed_count} | Modified: {modified_count}")

    # Load flow_context
    output_dir   = os.path.join(project_root, config.OUTPUT_DIR)
    fc_labelled  = os.path.join(output_dir, f"{label}_flow_context.json") if label else None
    fc_plain     = os.path.join(output_dir, "flow_context.json")
    flow_context = None

    for candidate in filter(None, [fc_labelled, fc_plain]):
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                flow_context = json.load(f)
            print(f"✅ Flow context  : {candidate}")
            print(f"   Change type  : {flow_context.get('change_type', '?')}")
            break

    if not flow_context:
        print("⚠️  No flow_context.json found — agent will run without M3 context")

    state["flow_context"] = flow_context
    return state


# ---------------------------------------------------------------------------
# NODE: BUILD_INVENTORY
# ---------------------------------------------------------------------------

async def build_inventory_node(state: AgentState) -> AgentState:
    """
    Pure Python node — builds the structured inventory map the LLM
    will use upfront to plan its investigation.

    For each processor:
      - new/removed: lists files available to read
      - modified: includes changed_files diff (key + content snippets)
    """
    print("\n[BUILD_INVENTORY] Building structured inventory map...")

    delta        = state["delta"]
    version_from = state["version_from"]
    version_to   = state["version_to"]

    def _list_files_for(processor_id: str, version: str) -> List[str]:
        result = list_processor_files(processor_id, version=version)
        if result["success"]:
            return [f["file_name"] for f in result["files"]]
        return []

    # NEW processors
    new_inventory = []
    for step in delta.get("new_steps", []):
        pid = step["processor_id"]
        new_inventory.append({
            "processor_id": pid,
            "type"        : step["type"],
            "name"        : step["name"],
            "files"       : _list_files_for(pid, version_to),
        })

    # REMOVED processors
    removed_inventory = []
    for step in delta.get("removed_steps", []):
        pid = step["processor_id"]
        removed_inventory.append({
            "processor_id": pid,
            "type"        : step["type"],
            "name"        : step["name"],
            "files"       : _list_files_for(pid, version_from),
        })

    # MODIFIED processors — include changed_files for upfront context
    modified_inventory = []
    for step in state.get("modified_steps", []):
        pid = step["processor_id"]
        modified_inventory.append({
            "processor_id" : pid,
            "type"         : step["type"],
            "name"         : step["name"],
            "changed_files": step.get("changed_files", []),
        })

    inventory = {
        "new"     : new_inventory,
        "removed" : removed_inventory,
        "modified": modified_inventory,
    }

    state["inventory"] = inventory

    total = len(new_inventory) + len(removed_inventory) + len(modified_inventory)
    print(f"✅ Inventory built: {total} processors to investigate")
    print(f"   New: {len(new_inventory)} | "
          f"Removed: {len(removed_inventory)} | "
          f"Modified: {len(modified_inventory)}")

    for p in new_inventory:
        print(f"   [NEW     ] {p['name']:35} ({p['processor_id']})")
    for p in removed_inventory:
        print(f"   [REMOVED ] {p['name']:35} ({p['processor_id']})")
    for p in modified_inventory:
        print(f"   [MODIFIED] {p['name']:35} ({p['processor_id']})")

    return state


# ---------------------------------------------------------------------------
# NODE: INVESTIGATE (LLM-driven tool-use loop)
# ---------------------------------------------------------------------------

def _run_investigation_batch(
    client       : Any,
    prompt       : str,
    batch_label  : str,
    max_turns    : int = 50,
) -> tuple[List[Dict], List[str]]:
    """
    Run one tool-use investigation loop for a focused batch of processors.
    Returns (findings, files_read) for that batch.
    """
    # Reset tool state for this batch
    _tool_state["finish_called"] = False
    _tool_state["findings"]      = []
    # files_read accumulates across batches — do not reset here

    contents: List[genai_types.Content] = [
        genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])
    ]

    turn = 0
    while turn < max_turns:
        turn += 1
        logger.debug(f"  [{batch_label}] Turn {turn}")

        response = client.models.generate_content(
            model    = config.GEMINI_MODEL,
            contents = contents,
            config   = genai_types.GenerateContentConfig(tools=TOOL_DECLARATIONS),
        )

        # Guard: empty candidates = safety filter or quota error — skip turn
        if not response.candidates or not response.candidates[0].content:
            logger.warning(f"[{batch_label}] Turn {turn}: empty response (safety filter or quota) — skipping")
            break

        candidate_content = response.candidates[0].content
        contents.append(candidate_content)

        parts = candidate_content.parts or []
        function_calls = [
            part.function_call
            for part in parts
            if part.function_call
        ]

        if not function_calls:
            logger.warning(f"[{batch_label}] LLM stopped without finish_investigation — "
                           "attempting to parse findings from final response")
            text = "".join(
                part.text for part in parts
                if hasattr(part, "text") and part.text
            )
            parsed = _parse_llm_json(text)
            if parsed and "findings" in parsed:
                _tool_state["findings"] = parsed["findings"]
            break

        tool_results = []
        for fc in function_calls:
            fn_name = fc.name
            fn_args = dict(fc.args)
            print(f"   → Tool call : {fn_name}({', '.join(f'{k}={v!r}' for k, v in fn_args.items())})")

            if fn_name == "read_processor_files":
                result_str = read_processor_files.invoke(fn_args)
            elif fn_name == "finish_investigation":
                result_str = finish_investigation.invoke(fn_args)
            else:
                result_str = json.dumps({"error": f"Unknown tool: {fn_name}"})

            tool_results.append(
                genai_types.Part(
                    function_response=genai_types.FunctionResponse(
                        name     = fn_name,
                        response = {"result": result_str},
                    )
                )
            )

        contents.append(
            genai_types.Content(role="user", parts=tool_results)
        )

        if _tool_state["finish_called"]:
            print(f"   ✅ [{batch_label}] finish_investigation called after {turn} turn(s)")
            break
    else:
        logger.warning(f"[{batch_label}] hit max_turns ({max_turns}) without finish_investigation")

    return list(_tool_state["findings"]), list(_tool_state["files_read"])


async def investigate_node(state: AgentState) -> AgentState:
    """
    LLM-driven investigation node — runs in three focused batches:
      Batch 1: NEW processors
      Batch 2: REMOVED processors
      Batch 3: MODIFIED processors (most critical)

    Batching prevents context overload on large diffs (e.g. 55-56 with
    15 new + 8 removed + 10 modified = 33 processors in one shot caused
    the LLM to submit empty findings).
    """
    print("\n[INVESTIGATE] Starting LLM-driven investigation (3 batches)...")

    # Reset shared tool state
    _tool_state["files_read"]    = []
    _tool_state["finish_called"] = False
    _tool_state["findings"]      = []

    client    = _get_gemini_client()
    inventory = state["inventory"]
    all_findings : List[Dict] = []

    # ------------------------------------------------------------------
    # Helper: build a single-category inventory and run a batch
    # ------------------------------------------------------------------
    def _run_batch(category: str, processors: List[Dict], label: str) -> List[Dict]:
        if not processors:
            print(f"   [{label}] No processors — skipping")
            return []

        print(f"\n   [{label}] {len(processors)} processor(s)...")
        batch_inventory = {
            "new"     : processors if category == "new"      else [],
            "removed" : processors if category == "removed"  else [],
            "modified": processors if category == "modified" else [],
        }
        prompt = format_investigate_prompt(
            integration  = state["integration"],
            version_from = state["version_from"],
            version_to   = state["version_to"],
            flow_context = state.get("flow_context"),
            inventory    = batch_inventory,
        )
        findings, _ = _run_investigation_batch(client, prompt, label)
        print(f"   [{label}] findings: {len(findings)}")
        return findings

    CHUNK_SIZE = 5  # max processors per LLM call — prevents context overload on large diffs

    def _run_chunked(category: str, processors: List[Dict], label: str) -> List[Dict]:
        """Split large processor lists into chunks and run each as a separate LLM call."""
        if not processors:
            print(f"   [{label}] No processors — skipping")
            return []
        chunks = [processors[i:i+CHUNK_SIZE] for i in range(0, len(processors), CHUNK_SIZE)]
        findings = []
        for idx, chunk in enumerate(chunks, 1):
            chunk_label = f"{label} {idx}/{len(chunks)}"
            findings += _run_batch(category, chunk, chunk_label)
        return findings

    all_findings += _run_chunked("new",      inventory.get("new",      []), "NEW")
    all_findings += _run_chunked("removed",  inventory.get("removed",  []), "REMOVED")
    all_findings += _run_chunked("modified", inventory.get("modified", []), "MODIFIED")

    files_read = list(_tool_state["files_read"])

    # Enforce risk floor: modified steps are NEVER low risk.
    modified_ids = {s["processor_id"] for s in state.get("modified_steps", [])}
    for finding in all_findings:
        if (finding.get("processor_id") in modified_ids and
                finding.get("risk_level", "").lower() == "low"):
            finding["risk_level"]  = "medium"
            finding["risk_reason"] = (
                finding.get("risk_reason", "") +
                " [risk floor: modified steps are minimum medium]"
            ).strip()
            logger.info(f"  Risk floor applied: {finding['processor_id']} low → medium")

    state["findings"]   = all_findings
    state["files_read"] = files_read

    print(f"\n✅ Investigation complete")
    print(f"   Findings   : {len(all_findings)}")
    print(f"   Files read : {len(files_read)}")
    for f in all_findings:
        risk   = f.get("risk_level", "?").upper()
        name   = f.get("step_name", f.get("processor_id", "?"))
        status = f.get("status", "?")
        print(f"   [{risk:6}] [{status:8}] {name}")

    return state


# ---------------------------------------------------------------------------
# NODE: SYNTHESIZE
# ---------------------------------------------------------------------------

async def synthesize_node(state: AgentState) -> AgentState:
    """
    Sends all findings + flow_context to the LLM to produce the final
    structured report with overall risk, recommendation, and summary.
    """
    print("\n[SYNTHESIZE] Generating final report...")

    client   = _get_gemini_client()
    delta    = state["delta"]
    findings = state.get("findings", [])

    # Build statistics
    modified_steps = state.get("modified_steps", [])
    statistics = {
        "new_steps_count"       : len(delta.get("new_steps", [])),
        "removed_steps_count"   : len(delta.get("removed_steps", [])),
        "modified_steps_count"  : len(modified_steps),
        "positionally_shifted"  : len(delta.get("positionally_shifted", [])),
        "unchanged_count"       : len(delta.get("unchanged_steps", [])),
        "total_investigated"    : len(findings),
        "files_read"            : len(state.get("files_read", [])),
    }

    prompt = format_synthesize_prompt(
        integration     = state["integration"],
        version_from    = state["version_from"],
        version_to      = state["version_to"],
        statistics      = statistics,
        findings        = findings,
        shifted_steps   = delta.get("positionally_shifted", []),
        unchanged_count = len(delta.get("unchanged_steps", [])),
        flow_context    = state.get("flow_context"),
    )

    try:
        response      = client.models.generate_content(
            model    = config.GEMINI_MODEL,
            contents = prompt,
        )
        response_text = response.text.strip()
        report        = _parse_llm_json(response_text)

        if not report:
            logger.error("SYNTHESIZE: LLM returned no parseable JSON")
            report = _fallback_report(state, "Automated synthesis failed — manual review required.")

    except Exception as e:
        logger.error(f"SYNTHESIZE LLM call failed: {e}")
        report = _fallback_report(state, f"Synthesis error: {e}")

    # Enforce risk floor on modified_steps in the report.
    # SYNTHESIZE LLM generates these independently from findings —
    # must clamp here too, same as in investigate_node.
    for step in report.get("modified_steps", []):
        if step.get("risk_level", "").lower() == "low":
            step["risk_level"] = "medium"
            step["risk_reason"] = (
                step.get("risk_reason", "") +
                " [risk floor: modified steps are minimum medium]"
            ).strip()
            logger.info(f"  Risk floor applied in report: {step.get('step_name')} low -> medium")

    # Enforce count integrity — LLM sometimes collapses multiple findings into one.
    # If the report arrays are shorter than findings, backfill from findings directly.
    def _backfill(report_key: str, status: str):
        report_entries  = report.get(report_key, [])
        finding_entries = [f for f in findings if f.get("status", "").upper() == status]
        if len(report_entries) < len(finding_entries):
            logger.warning(
                f"SYNTHESIZE truncated {report_key}: "
                f"report={len(report_entries)}, findings={len(finding_entries)} — backfilling"
            )
            report[report_key] = [
                {
                    "step_name"      : f.get("step_name", f.get("processor_id", "?")),
                    "step_type"      : f.get("step_type", "?"),
                    "purpose"        : f.get("purpose", ""),
                    "business_impact": f.get("business_impact", ""),
                    "risk_level"     : f.get("risk_level", "low"),
                    "what_changed"   : f.get("what_changed", ""),
                }
                for f in finding_entries
            ]

    _backfill("new_steps",      "NEW")
    _backfill("removed_steps",  "REMOVED")
    _backfill("modified_steps", "MODIFIED")

    # Metadata
    report["generated_at"]            = datetime.now(timezone.utc).isoformat()
    report["files_read"]              = len(state.get("files_read", []))
    report["processors_investigated"] = len(findings)
    report["statistics"]              = statistics

    # Write {label}_report.json
    label      = getattr(config, "LABEL", None)
    filename   = f"{label}_report.json" if label else "report.json"
    output_dir = os.path.join(project_root, config.OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)
    out_path   = os.path.join(output_dir, filename)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    state["final_report"] = report

    print(f"\n✅ Final report generated")
    print(f"   Overall risk   : {report.get('overall_risk', '?').upper()}")
    print(f"   Recommendation : {report.get('recommendation', '?')}")
    print(f"   Summary        : {report.get('summary', '')[:120]}...")
    print(f"   Written        : {out_path}")

    return state


def _fallback_report(state: AgentState, message: str) -> Dict:
    return {
        "integration"     : state.get("integration", ""),
        "version_from"    : state.get("version_from", ""),
        "version_to"      : state.get("version_to", ""),
        "overall_risk"    : "unknown",
        "recommendation"  : "manual_review_required",
        "summary"         : message,
        "new_steps"       : [],
        "removed_steps"   : [],
        "modified_steps"  : [],
        "key_observations": ["Synthesis failed — raw findings available in agent state"],
        "conditions"      : [],
    }


# ---------------------------------------------------------------------------
# GRAPH CONSTRUCTION
# ---------------------------------------------------------------------------

def create_agent_graph():
    """Build and compile the M4 Investigator Agent LangGraph."""
    print("\n🔧 Building M4 Investigator Agent Graph...")

    workflow = StateGraph(AgentState)

    workflow.add_node("INIT",            init_node)
    workflow.add_node("BUILD_INVENTORY", build_inventory_node)
    workflow.add_node("INVESTIGATE",     investigate_node)
    workflow.add_node("SYNTHESIZE",      synthesize_node)

    workflow.add_edge(START,             "INIT")
    workflow.add_edge("INIT",            "BUILD_INVENTORY")
    workflow.add_edge("BUILD_INVENTORY", "INVESTIGATE")
    workflow.add_edge("INVESTIGATE",     "SYNTHESIZE")
    workflow.add_edge("SYNTHESIZE",       END)

    app = workflow.compile()
    print("✅ M4 Agent compiled\n")
    return app


agent_graph = create_agent_graph()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_agent(label: str = None) -> Dict:
    """Run the M4 Investigator Agent for the given label."""
    logging.basicConfig(
        level   = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt = "%Y-%m-%d %H:%M:%S",
    )
    for noisy in ["google_genai", "google_genai._api_client",
                  "google_genai.models", "httpx"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if label:
        config.LABEL = label

    lbl        = getattr(config, "LABEL", None)
    delta_name = f"{lbl}_delta.json" if lbl else "delta.json"
    delta_path = os.path.join(project_root, config.OUTPUT_DIR, delta_name)

    initial_state: AgentState = {
        "delta_path"    : delta_path,
        "version_from"  : "",
        "version_to"    : "",
        "integration"   : "",
        "delta"         : None,
        "flow_context"  : None,
        "inventory"     : None,
        "modified_steps": None,
        "messages"      : [],
        "files_read"    : [],
        "findings"      : [],
        "final_report"  : None,
    }

    result = await agent_graph.ainvoke(initial_state)

    print("\n" + "=" * 60)
    print("M4 INVESTIGATOR AGENT — COMPLETE")
    print("=" * 60)
    report = result.get("final_report", {})
    print(f"Integration : {result.get('integration', '?')}")
    print(f"Versions    : v{result.get('version_from')} → v{result.get('version_to')}")
    print(f"Findings    : {len(result.get('findings', []))}")
    print(f"Risk        : {report.get('overall_risk', '?').upper()}")
    print(f"Decision    : {report.get('recommendation', '?')}")
    lbl_str = f"{lbl}_report.json" if lbl else "report.json"
    print(f"Report      : output/{lbl_str}")
    print("=" * 60)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

KNOWN_LABELS = ["32-33", "34-35", "36-37", "39-40", "41-42",
                "45-46", "47-48", "49-50", "51-52", "53-54", "55-56"]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="M4 — Agent Investigation: LLM-driven processor analysis",
        epilog=(
            "Examples:\n"
            "  python src/agent.py 32-33\n"
            "  python src/agent.py 49-50\n"
            "  python src/agent.py 55-56"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "label", metavar="LABEL",
        help=f"Pair label. Known: {KNOWN_LABELS}",
    )
    args = parser.parse_args()
    asyncio.run(run_agent(args.label))
