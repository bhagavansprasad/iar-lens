# ---------------------------------------------------------------------------
# iar-lens | src/flow_understander.py
# Phase 1b — Flow Understander
#
# Takes the full extracted flow data for both source and target versions
# and calls an LLM to produce a rich flow_context.json that describes:
#   - What the integration does (business purpose)
#   - The logical blocks / stages in each version
#   - What external systems / adapters are involved
#   - A plain-English before/after narrative
#
# This context is fed into Phase 2 (agent investigation) and
# Phase 3 (report generation) so both have full flow awareness.
# ---------------------------------------------------------------------------

import os
import sys
import json
import re
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt — systems_involved is intentionally excluded from what the LLM
# is asked to produce. It is computed in Python from raw applications data
# and merged back after the LLM call. This avoids LLM truncation of the
# adapter list, which was observed when it was LLM-generated.
# ---------------------------------------------------------------------------

FLOW_UNDERSTAND_PROMPT = """
You are an Oracle Integration Cloud (OIC) integration architect.

You are given the complete, ordered list of flow steps for TWO versions of an
OIC integration, along with the adapters (external connections) used in each.

Your job is to deeply understand what this integration does as a whole, how it
changed between versions, and describe it clearly for BOTH a technical reviewer
(SME) and a non-technical business stakeholder (non-SME).

## Integration
- Name        : {integration}
- Version From: {version_from}
- Version To  : {version_to}

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
this exact structure:

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

  "change_narrative": "3-5 sentences. Explain the change from a business perspective - what capability was added, what was removed, and what is the overall effect. Written for a non-SME who needs to approve this change.",

  "change_type": "one of: additive_only | removal_only | refactor | scope_expansion | bug_fix | unknown",

  "change_type_reason": "1 sentence explaining why you classified it as that change type"
}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_systems_involved(source_apps: list, target_apps: list) -> dict:
    """
    Computes systems_involved entirely in Python from raw applications lists.
    Avoids relying on the LLM to enumerate adapters, which caused truncation.
    Returns dict with keys: source, target, added, removed.
    """
    def adapter_names(apps: list) -> list:
        return [
            a.get("adapter_name") or a.get("app_id", "?")
            for a in apps
            if (a.get("adapter_name") or a.get("app_id"))
        ]

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
        name = app.get("adapter_name") or app.get("app_id", "?")
        role = app.get("role", "")
        lines.append(f"  - {name} ({role})")
    return "\n".join(lines)


def _format_flow(steps: list, new_names: set, removed_names: set,
                 applications: list) -> str:
    """
    Formats the full ordered step list with NEW/REMOVED markers
    and adapter references where available.
    """
    lines = []
    for s in steps:
        name    = s["name"]
        stype   = s["type"]
        pos     = s["position"]
        adapter = s.get("adapter_ref")

        markers = []
        if name in new_names:
            markers.append("[NEW]")
        if name in removed_names:
            markers.append("[REMOVED]")
        if adapter:
            markers.append(f"[-> {adapter}]")

        marker_str = "  " + " ".join(markers) if markers else ""
        lines.append(f"  {pos:3d}. {stype:25s}  {name}{marker_str}")

    return "\n".join(lines)


def _parse_llm_json(text: str) -> dict | None:
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
    label        : str = None
) -> dict:
    """
    Calls the LLM with the full flow context of both versions and produces
    <label>_flow_context.json (or flow_context.json if no label) in output_dir.

    Args:
        integration  : integration name
        version_from : source version string
        version_to   : target version string
        source_data  : result of extract_steps() for source
        target_data  : result of extract_steps() for target
        delta        : result of compute_delta()
        output_dir   : where to write the output file
        label        : optional run label e.g. "32-33" for named output file

    Returns:
        flow_context dict
    """
    import google.genai as genai

    logger.info("Phase 1b - Flow Understander: calling LLM...")

    # Build NEW / REMOVED marker sets
    new_names     = {s["name"] for s in delta["new_steps"]}
    removed_names = {s["name"] for s in delta["removed_steps"]}

    source_flow_str = _format_flow(
        source_data["steps"],
        new_names     = set(),
        removed_names = removed_names,
        applications  = source_data["applications"]
    )
    target_flow_str = _format_flow(
        target_data["steps"],
        new_names     = new_names,
        removed_names = set(),
        applications  = target_data["applications"]
    )

    # Compute systems_involved in Python — do NOT ask the LLM
    systems_involved = _compute_systems_involved(
        source_apps = source_data["applications"],
        target_apps = target_data["applications"]
    )

    prompt = FLOW_UNDERSTAND_PROMPT.format(
        integration     = integration,
        version_from    = version_from,
        version_to      = version_to,
        source_adapters = _format_adapter_list(source_data["applications"]),
        target_adapters = _format_adapter_list(target_data["applications"]),
        source_flow     = source_flow_str,
        target_flow     = target_flow_str,
    )

    # Call LLM
    client   = genai.Client()
    response = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
    context  = _parse_llm_json(response.text.strip())

    if not context:
        logger.error("Flow Understander: LLM returned no parseable JSON")
        context = {
            "integration_purpose"  : "Could not determine - LLM parse failed.",
            "logical_blocks_source": [],
            "logical_blocks_target": [],
            "flow_before"          : "Not available.",
            "flow_after"           : "Not available.",
            "change_narrative"     : "Not available.",
            "change_type"          : "unknown",
            "change_type_reason"   : "Parse failed."
        }

    # Merge Python-computed systems_involved — overrides any LLM attempt
    context["systems_involved"] = systems_involved

    # Stamp metadata
    context["integration"]  = integration
    context["version_from"] = version_from
    context["version_to"]   = version_to
    context["generated_at"] = datetime.now(timezone.utc).isoformat()

    # Write output file — labelled if label provided
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{label}_flow_context.json" if label else "flow_context.json"
    out_path = os.path.join(output_dir, filename)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2)

    logger.info(f"Flow context written: {out_path}")
    logger.info(f"  Change type : {context.get('change_type', '?')}")
    logger.info(f"  Purpose     : {context.get('integration_purpose', '')[:100]}")

    return context
