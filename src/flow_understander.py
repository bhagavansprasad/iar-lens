# ---------------------------------------------------------------------------
# oic-lens | src/flow_understander.py
# Step 1 — M3: Flow Understander
#
# Reads {label}_delta.json + both extracted workspaces, calls the LLM to
# produce a rich {label}_flow_context.json describing:
#   - What the integration does (business purpose)
#   - Logical blocks / stages in each version
#   - Plain-English before/after narrative
#   - Change classification and narrative
#   - Modified steps summary (explicitly included in prompt)
#
# systems_involved is computed in Python — NOT by the LLM — to avoid
# truncation of the adapter list.
#
# Run standalone:
#   python src/flow_understander.py 32-33
#   python src/flow_understander.py 49-50
# ---------------------------------------------------------------------------

import os
import sys
import json
import re
import logging
import argparse
from datetime import datetime, timezone

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

import config
from extractor    import extract_iar
from flow_compare import extract_steps, compute_delta

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

FLOW_UNDERSTAND_PROMPT = """\
You are an Oracle Integration Cloud (OIC) integration architect.

You are given the complete, ordered list of flow steps for TWO versions of an
OIC integration, along with the adapters (external connections) used in each,
and a summary of what changed between the versions.

Your job is to deeply understand what this integration does as a whole, how it
changed between versions, and describe it clearly for BOTH a technical reviewer
(SME) and a non-technical business stakeholder (non-SME).

## Integration
- Name        : {integration}
- Version From: {version_from}
- Version To  : {version_to}

## What Changed (Step 1 analysis)
- New steps   : {new_count}
- Removed steps: {removed_count}
- Modified steps: {modified_count}

{modified_steps_detail}

## Adapters in Source Version ({version_from})
{source_adapters}

## Adapters in Target Version ({version_to})
{target_adapters}

## Complete Flow — Source Version ({version_from})
{source_flow}

## Complete Flow — Target Version ({version_to})
{target_flow}

## Legend for flow steps
- [NEW]     = step exists only in target version
- [REMOVED] = step exists only in source version
- [-> AdapterName] = step invokes this external adapter/system

---

## Your Task

Analyse both flows completely and respond ONLY with a valid JSON object in
this exact structure. No preamble, no markdown fences, just the JSON:

{{
  "integration_purpose": "2-3 sentences. What does this integration do as a business process? Who uses it? What systems does it connect? Write for a non-technical reader - no step names, no processor IDs.",

  "logical_blocks_source": [
    {{
      "block_name": "short label e.g. Initialisation, EI File Processing, Oracle Sync",
      "step_range": "positions e.g. 1-3 or 15-21",
      "description": "1-2 sentences - what does this block do in business terms?"
    }}
  ],

  "logical_blocks_target": [
    {{
      "block_name": "short label",
      "step_range": "positions",
      "description": "1-2 sentences"
    }}
  ],

  "flow_before": "3-5 sentences plain English. Walk through what the integration did end-to-end in the source version. Use business language - mention systems and outcomes, not step names.",

  "flow_after": "3-5 sentences plain English. Walk through what the integration does end-to-end in the target version. Highlight what is new or different.",

  "change_narrative": "3-5 sentences. Explain the change from a business perspective - what capability was added, what was removed, and what is the overall effect. Written for a non-SME who needs to approve this change. If there are modified steps, describe what specifically changed in plain English.",

  "change_type": "one of: additive_only | removal_only | refactor | scope_expansion | bug_fix | unknown",

  "change_type_reason": "1 sentence explaining why you classified it as that change type"
}}
"""


# ---------------------------------------------------------------------------
# Public helpers (exposed for use by agent / report generator)
# ---------------------------------------------------------------------------

def adapter_names(apps: list) -> list:
    """Return display names for a list of application dicts from extract_steps()."""
    names = []
    for a in apps:
        name = a.get("name") or a.get("code") or a.get("app_id") or "?"
        if name and name != "?":
            names.append(name)
    return names


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_systems_involved(source_apps: list, target_apps: list) -> dict:
    """
    Computes systems_involved entirely in Python from raw applications lists.
    Avoids relying on the LLM to enumerate adapters (caused truncation).
    Returns dict with keys: source, target, added, removed.
    """
    source_names = adapter_names(source_apps)
    target_names = adapter_names(target_apps)
    source_set   = set(source_names)
    target_set   = set(target_names)

    return {
        "source" : source_names,
        "target" : target_names,
        "added"  : sorted(target_set - source_set),
        "removed": sorted(source_set - target_set),
    }


def _format_adapter_list(applications: list) -> str:
    if not applications:
        return "  (none)"
    lines = []
    for app in applications:
        name = app.get("name") or app.get("code") or "?"
        role = app.get("role", "")
        code = app.get("code", "")
        lines.append(f"  - {name} ({code}, {role})")
    return "\n".join(lines)


def _format_flow(processors: list, new_ids: set, removed_ids: set) -> str:
    """Formats the full ordered processor list with NEW/REMOVED markers."""
    lines = []
    for p in processors:
        pid   = p["processor_id"]
        name  = p["name"]
        ptype = p["type"]
        pos   = p["position"]

        markers = []
        if pid in new_ids:
            markers.append("[NEW]")
        if pid in removed_ids:
            markers.append("[REMOVED]")

        marker_str = "  " + " ".join(markers) if markers else ""
        lines.append(f"  {pos:3d}. {ptype:25s}  {name}{marker_str}")

    return "\n".join(lines)


def _format_modified_steps_detail(modified_steps: list) -> str:
    """Formats modified steps for inclusion in the prompt."""
    if not modified_steps:
        return "  (no modified steps)"

    lines = ["### Modified Steps Detail"]
    for m in modified_steps:
        lines.append(f"\n  Processor: {m['processor_id']} ({m['type']}) — {m['name']}")
        for cf in m.get("changed_files", []):
            key     = cf.get("key", "")
            old_c   = cf.get("old_content", "")
            new_c   = cf.get("new_content", "")
            old_snip = _first_line(old_c)
            new_snip = _first_line(new_c)
            lines.append(f"    File  : {key}")
            lines.append(f"    Before: {old_snip}")
            lines.append(f"    After : {new_snip}")
    return "\n".join(lines)


def _first_line(text: str, max_len: int = 120) -> str:
    """Return first non-empty line of text, truncated."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:max_len] + ("..." if len(line) > max_len else "")
    return "(empty)"


def _parse_llm_json(text: str) -> dict | None:
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Strip markdown fences and retry
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        pass
    # Fall back to extracting first JSON block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def understand_flow(
    integration  : str,
    version_from : str,
    version_to   : str,
    source_data  : dict,
    target_data  : dict,
    delta        : dict,
    output_dir   : str,
    label        : str = None,
) -> dict:
    """
    Calls the LLM with the full flow context of both versions and produces
    {label}_flow_context.json in output_dir.

    Args:
        integration  : integration name string
        version_from : source version string
        version_to   : target version string
        source_data  : result of extract_steps() for source
        target_data  : result of extract_steps() for target
        delta        : result of compute_delta() — must include modified_steps
        output_dir   : directory to write the output file
        label        : run label e.g. "32-33"

    Returns:
        flow_context dict
    """
    import google.genai as genai

    logger.info("M3 — Flow Understander: building prompt...")

    new_ids     = {s["processor_id"] for s in delta.get("new_steps", [])}
    removed_ids = {s["processor_id"] for s in delta.get("removed_steps", [])}
    modified    = delta.get("modified_steps", [])

    source_flow_str = _format_flow(source_data["processors"], new_ids=set(),    removed_ids=removed_ids)
    target_flow_str = _format_flow(target_data["processors"], new_ids=new_ids,  removed_ids=set())

    systems_involved = _compute_systems_involved(
        source_data["applications"],
        target_data["applications"],
    )

    prompt = FLOW_UNDERSTAND_PROMPT.format(
        integration           = integration,
        version_from          = version_from,
        version_to            = version_to,
        new_count             = len(delta.get("new_steps", [])),
        removed_count         = len(delta.get("removed_steps", [])),
        modified_count        = len(modified),
        modified_steps_detail = _format_modified_steps_detail(modified),
        source_adapters       = _format_adapter_list(source_data["applications"]),
        target_adapters       = _format_adapter_list(target_data["applications"]),
        source_flow           = source_flow_str,
        target_flow           = target_flow_str,
    )

    logger.info("M3 — Flow Understander: calling LLM...")
    client   = genai.Client()
    response = client.models.generate_content(
        model    = config.GEMINI_MODEL,
        contents = prompt,
    )
    context = _parse_llm_json(response.text.strip())

    if not context:
        logger.error("Flow Understander: LLM returned no parseable JSON")
        context = {
            "integration_purpose"  : "Could not determine — LLM parse failed.",
            "logical_blocks_source": [],
            "logical_blocks_target": [],
            "flow_before"          : "Not available.",
            "flow_after"           : "Not available.",
            "change_narrative"     : "Not available.",
            "change_type"          : "unknown",
            "change_type_reason"   : "Parse failed.",
        }

    # Merge Python-computed fields — authoritative, not LLM-generated
    context["systems_involved"]    = systems_involved
    context["modified_steps_count"] = len(modified)

    # Metadata
    context["integration"]  = integration
    context["version_from"] = version_from
    context["version_to"]   = version_to
    context["generated_at"] = datetime.now(timezone.utc).isoformat()

    # Write output
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{label}_flow_context.json" if label else "flow_context.json"
    out_path = os.path.join(output_dir, filename)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2)

    logger.info(f"Flow context written: {out_path}")
    logger.info(f"  Change type : {context.get('change_type', '?')}")
    logger.info(f"  Purpose     : {context.get('integration_purpose', '')[:100]}")

    return context


# ---------------------------------------------------------------------------
# Known pairs (mirrors iar_compare.py)
# ---------------------------------------------------------------------------

KNOWN_PAIRS = {
    "32-33": ("flow-dump/32-33/FACTORYDOCK-TEST-32.car",  "flow-dump/32-33/FACTORYDOCK-TEST-33.car"),
    "34-35": ("flow-dump/34-35/FACTORYDOCK-TEST-34.car",  "flow-dump/34-35/FACTORYDOCK-TEST-35.car"),
    "36-37": ("flow-dump/36-37/FACTORYDOCK-TEST-36.car",  "flow-dump/36-37/FACTORYDOCK-TEST-37.car"),
    "39-40": ("flow-dump/39-40/FACTORYDOCK-TEST-39.car",  "flow-dump/39-40/FACTORYDOCK-TEST-40.car"),
    "41-42": ("flow-dump/41-42/FACTORYDOCK-TEST-41.car",  "flow-dump/41-42/FACTORYDOCK-TEST-42.car"),
    "45-46": ("flow-dump/45-46/FACTORYDOCK-TEST-45.car",  "flow-dump/45-46/FACTORYDOCK-TEST-46.car"),
    "47-48": ("flow-dump/47-48/FACTORYDOCK-TEST-47.car",  "flow-dump/47-48/FACTORYDOCK-TEST-47.car"),
    "49-50": ("flow-dump/49-50/FACTORYDOCK-TEST-49.car",  "flow-dump/49-50/FACTORYDOCK-TEST-50.car"),
    "51-52": ("flow-dump/51-52/FACTORYDOCK-TEST-51.car",  "flow-dump/51-52/FACTORYDOCK-TEST-52.car"),
    "53-54": ("flow-dump/53-54/FACTORYDOCK-TEST-53.car",  "flow-dump/53-54/FACTORYDOCK-TEST-54.car"),
    "55-56": ("flow-dump/55-56/INT03.00.0001.iar",         "flow-dump/55-56/INT03.00.0011.iar"),
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_understander(label: str):
    """Extract, diff, and understand flow for a given pair label."""
    if label not in KNOWN_PAIRS:
        print(f"Unknown label: {label!r}")
        print(f"Known labels : {sorted(KNOWN_PAIRS.keys())}")
        sys.exit(1)

    src_rel, tgt_rel = KNOWN_PAIRS[label]
    source_path = os.path.join(project_root, src_rel)
    target_path = os.path.join(project_root, tgt_rel)
    workspace   = os.path.join(project_root, config.WORKSPACE_DIR)
    output_dir  = os.path.join(project_root, config.OUTPUT_DIR)

    # Extract both workspaces
    src_ex = extract_iar(source_path, workspace)
    tgt_ex = extract_iar(target_path, workspace)

    source_data = extract_steps(src_ex["project_xml"])
    target_data = extract_steps(tgt_ex["project_xml"])

    # Reuse existing delta.json if present, otherwise recompute
    delta_path = os.path.join(output_dir, f"{label}_delta.json")
    if os.path.exists(delta_path):
        logger.info(f"Reusing existing delta: {delta_path}")
        with open(delta_path) as f:
            delta = json.load(f)
        # Patch in extract paths if missing (older delta.json without M2)
        if not delta.get("modified_steps"):
            logger.info("delta.json has no modified_steps — recomputing with M2")
            delta = compute_delta(
                source_data, target_data,
                source_extract_path=src_ex["extract_path"],
                target_extract_path=tgt_ex["extract_path"],
            )
    else:
        logger.info("No delta.json found — running Step 1 first")
        delta = compute_delta(
            source_data, target_data,
            source_extract_path=src_ex["extract_path"],
            target_extract_path=tgt_ex["extract_path"],
        )
        delta["label"]               = label
        delta["source_extract_path"] = src_ex["extract_path"]
        delta["target_extract_path"] = tgt_ex["extract_path"]
        delta["integration_code"]    = source_data["integration_code"]
        delta["integration_name"]    = source_data["integration_name"]
        os.makedirs(output_dir, exist_ok=True)
        with open(delta_path, "w") as f:
            json.dump(delta, f, indent=2)

    integration  = delta.get("integration_name") or delta.get("integration_code", "")
    version_from = delta["source_version"]
    version_to   = delta["target_version"]

    context = understand_flow(
        integration  = integration,
        version_from = version_from,
        version_to   = version_to,
        source_data  = source_data,
        target_data  = target_data,
        delta        = delta,
        output_dir   = output_dir,
        label        = label,
    )

    print(f"\n  Integration  : {integration}")
    print(f"  Label        : {label}")
    print(f"  Versions     : v{version_from} -> v{version_to}")
    print(f"  Change type  : {context.get('change_type', '?')}")
    print(f"  Modified     : {context.get('modified_steps_count', 0)} steps")
    print(f"  Output       : {os.path.join(output_dir, label + '_flow_context.json')}")
    print(f"\n  Purpose:\n  {context.get('integration_purpose', '')}")


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Step 1 M3 — Flow Understander: LLM summary of the full diff",
        epilog=(
            "Examples:\n"
            "  python src/flow_understander.py 32-33\n"
            "  python src/flow_understander.py 49-50"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "label", metavar="LABEL",
        help=f"Pair label to process. Known: {sorted(KNOWN_PAIRS.keys())}",
    )
    args = parser.parse_args()
    run_understander(args.label)
