# ---------------------------------------------------------------------------
# oic-lens | src/agent_prompts.py
# M4 — Agent Investigation
# All LLM prompts for the Investigator Agent
# ---------------------------------------------------------------------------

import json
from typing import Dict, List, Any, Optional


# ---------------------------------------------------------------------------
# INVESTIGATE prompt — shown once to the LLM at the start of investigation.
# LLM uses tools to read files, then calls finish_investigation when done.
# ---------------------------------------------------------------------------

INVESTIGATE_PROMPT = """\
You are an Oracle Integration Cloud (OIC) integration architect.

You are reviewing changes between two versions of an OIC integration.
Your job is to investigate every changed processor and produce a structured finding for each one.

## Integration
- Name        : {integration}
- Version From: {version_from}
- Version To  : {version_to}

## Integration Context
{flow_context_section}

## Inventory of Changes
{inventory_section}

---

## Your Tools

You have one tool available:

**read_processor_files(processor_id, version)**
  - Reads all files for a processor from a specific version workspace.
  - Use version="{version_from}" for REMOVED processors.
  - Use version="{version_to}" for NEW processors.
  - For MODIFIED processors, call it TWICE — once per version — to see both sides.

---

## Investigation Rules

**NEW processors:**
  - Read files from version {version_to}.
  - Assess: what does this step do, why was it added, what is the risk?

**REMOVED processors:**
  - Read files from version {version_from}.
  - Assess: what did this step do, what is the impact of removing it?

**MODIFIED processors — MOST CRITICAL:**
  - Read files from BOTH versions ({version_from} AND {version_to}).
  - The inventory already shows you which files changed and a content snippet.
  - Read the full files if you need more context.
  - Risk floor is MEDIUM — a silent logic change is NEVER low risk.
  - Assess: what specifically changed, is this an improvement or a risk?

---

## Output Format

For each processor you investigate, produce one finding in this JSON shape:

For NEW or REMOVED:
{{
  "processor_id"    : "processor_XXX",
  "step_name"       : "...",
  "step_type"       : "...",
  "status"          : "NEW" | "REMOVED",
  "purpose"         : "one sentence — what does/did this step do?",
  "business_impact" : "one sentence — business effect of adding/removing it",
  "technical_detail": "2-3 sentences — key observations from the file contents",
  "risk_level"      : "low | medium | high",
  "risk_reason"     : "brief reason"
}}

For MODIFIED:
{{
  "processor_id"    : "processor_XXX",
  "step_name"       : "...",
  "step_type"       : "...",
  "status"          : "MODIFIED",
  "what_changed"    : "specific description of what changed — reference actual values",
  "purpose"         : "one sentence — what does this step do?",
  "business_impact" : "one sentence — business effect of this change",
  "technical_detail": "2-3 sentences — what exactly changed and how",
  "risk_level"      : "medium | high",
  "risk_reason"     : "brief reason — never low for modified steps"
}}

---

## When You Are Done

Call finish_investigation with a JSON object containing your findings list:
{{
  "findings": [ ... all findings ... ]
}}

Investigate ALL processors in the inventory before calling finish_investigation.
"""


# ---------------------------------------------------------------------------
# SYNTHESIZE prompt — given all findings, produce the final report
# ---------------------------------------------------------------------------

SYNTHESIZE_PROMPT = """\
You are an Oracle Integration Cloud (OIC) integration architect producing a change review report.

You have investigated all changed processors between two versions of an integration.

## Integration
- Name        : {integration}
- Version From: {version_from}
- Version To  : {version_to}

## Integration Context
{flow_context_section}

## Statistics
{statistics}

## All Findings (investigated processors)
{findings}

## Positionally Shifted Steps (same logic, pushed by insertions — no action needed)
{shifted_steps}

## Unchanged Steps (count for reference)
{unchanged_count} steps unchanged.

---

## Your Task

Produce a final structured change report that an architect can use to approve or reject this change.
Ground your summary in business terms using the Integration Context above.

CRITICAL RULES:
- new_steps array MUST contain exactly one entry per finding with status=NEW — do NOT collapse or summarise
- removed_steps array MUST contain exactly one entry per finding with status=REMOVED
- modified_steps array MUST contain exactly one entry per finding with status=MODIFIED
- If statistics says new_steps_count=6, your new_steps array must have exactly 6 entries
- Every finding in the findings list above must appear in the appropriate array

Respond ONLY with a valid JSON object — no preamble, no markdown fences:

{{
  "integration"   : "{integration}",
  "version_from"  : "{version_from}",
  "version_to"    : "{version_to}",
  "overall_risk"  : "low | medium | high",
  "recommendation": "approve | approve_with_conditions | reject",
  "summary"       : "3-5 sentences plain English — what changed, why, overall assessment",
  "new_steps"     : [
    {{
      "step_name"      : "...",
      "step_type"      : "...",
      "purpose"        : "...",
      "business_impact": "...",
      "risk_level"     : "low | medium | high"
    }}
  ],
  "removed_steps" : [
    {{
      "step_name"      : "...",
      "step_type"      : "...",
      "purpose"        : "...",
      "business_impact": "...",
      "risk_level"     : "low | medium | high"
    }}
  ],
  "modified_steps": [
    {{
      "step_name"      : "...",
      "step_type"      : "...",
      "what_changed"   : "...",
      "business_impact": "...",
      "risk_level"     : "medium | high"
    }}
  ],
  "key_observations": ["observation 1", "observation 2", "observation 3"],
  "conditions"      : ["condition if approve_with_conditions, else empty list"]
}}
"""


# ---------------------------------------------------------------------------
# Prompt formatters
# ---------------------------------------------------------------------------

def format_flow_context_section(flow_context: Optional[Dict]) -> str:
    """Formats flow_context into a readable prompt section."""
    if not flow_context:
        return "  (flow context not available — running without M3 output)"

    lines = []

    purpose = flow_context.get("integration_purpose", "")
    if purpose:
        lines.append(f"Purpose:\n  {purpose}")

    change_type   = flow_context.get("change_type", "")
    change_reason = flow_context.get("change_type_reason", "")
    if change_type:
        lines.append(f"\nChange Type: {change_type}")
        if change_reason:
            lines.append(f"  Reason: {change_reason}")

    narrative = flow_context.get("change_narrative", "")
    if narrative:
        lines.append(f"\nChange Narrative:\n  {narrative}")

    flow_before = flow_context.get("flow_before", "")
    flow_after  = flow_context.get("flow_after", "")
    if flow_before:
        lines.append(f"\nFlow Before:\n  {flow_before}")
    if flow_after:
        lines.append(f"\nFlow After:\n  {flow_after}")

    si      = flow_context.get("systems_involved", {})
    added   = si.get("added", [])
    removed = si.get("removed", [])
    if added:
        lines.append(f"\nAdapters Added   : {', '.join(added)}")
    if removed:
        lines.append(f"Adapters Removed : {', '.join(removed)}")

    return "\n".join(lines)


def format_inventory_section(inventory: Dict) -> str:
    """Formats the inventory map into a readable prompt section."""
    lines = []

    new_steps      = inventory.get("new", [])
    removed_steps  = inventory.get("removed", [])
    modified_steps = inventory.get("modified", [])

    if new_steps:
        lines.append(f"### NEW Processors ({len(new_steps)})")
        for p in new_steps:
            files_str = ", ".join(p.get("files", [])) or "no files listed"
            lines.append(f"  - {p['processor_id']} | {p['type']:25s} | {p['name']}")
            lines.append(f"    Files: {files_str}")
        lines.append("")

    if removed_steps:
        lines.append(f"### REMOVED Processors ({len(removed_steps)})")
        for p in removed_steps:
            files_str = ", ".join(p.get("files", [])) or "no files listed"
            lines.append(f"  - {p['processor_id']} | {p['type']:25s} | {p['name']}")
            lines.append(f"    Files: {files_str}")
        lines.append("")

    if modified_steps:
        lines.append(f"### MODIFIED Processors ({len(modified_steps)}) — MOST CRITICAL")
        for p in modified_steps:
            lines.append(f"  - {p['processor_id']} | {p['type']:25s} | {p['name']}")
            for cf in p.get("changed_files", []):
                key = cf.get("key", "")
                old_snippet = cf.get("old_content", "")[:120].replace("\n", " ")
                new_snippet = cf.get("new_content", "")[:120].replace("\n", " ")
                lines.append(f"    File   : {key}")
                lines.append(f"    Before : {old_snippet}")
                lines.append(f"    After  : {new_snippet}")
        lines.append("")

    if not (new_steps or removed_steps or modified_steps):
        lines.append("  (no changed processors — positional shifts or unchanged only)")

    return "\n".join(lines)


def format_investigate_prompt(
    integration    : str,
    version_from   : str,
    version_to     : str,
    flow_context   : Optional[Dict],
    inventory      : Dict,
) -> str:
    """Formats the INVESTIGATE_PROMPT with actual data."""
    return INVESTIGATE_PROMPT.format(
        integration          = integration,
        version_from         = version_from,
        version_to           = version_to,
        flow_context_section = format_flow_context_section(flow_context),
        inventory_section    = format_inventory_section(inventory),
    )


def format_synthesize_prompt(
    integration    : str,
    version_from   : str,
    version_to     : str,
    statistics     : Dict,
    findings       : List[Dict],
    shifted_steps  : List[Dict],
    unchanged_count: int,
    flow_context   : Optional[Dict],
) -> str:
    """Formats the SYNTHESIZE_PROMPT with actual data."""
    return SYNTHESIZE_PROMPT.format(
        integration          = integration,
        version_from         = version_from,
        version_to           = version_to,
        flow_context_section = format_flow_context_section(flow_context),
        statistics           = json.dumps(statistics, indent=2),
        findings             = json.dumps(findings,   indent=2),
        shifted_steps        = json.dumps(shifted_steps, indent=2),
        unchanged_count      = unchanged_count,
    )
