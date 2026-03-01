# ---------------------------------------------------------------------------
# iar-lens | src/iar_agent_prompts.py
# All Gemini prompts for the IAR Review Agent
# ---------------------------------------------------------------------------

import json
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# INVESTIGATE node prompt
# Given a processor and its files, understand what it does
# ---------------------------------------------------------------------------

INVESTIGATE_PROCESSOR_PROMPT = """
You are an Oracle Integration Cloud (OIC) integration architect reviewing changes between two versions of an IAR integration archive.

You are investigating a specific processor step that is NEW or REMOVED in the newer version.

## Processor Details
- Processor ID  : {processor_id}
- Step Name     : {step_name}
- Step Type     : {step_type}
- Status        : {status}
- Version       : {version}

## Files Associated with this Processor
{files_summary}

## File Contents
{file_contents}

## Your Task
Based on the files above, provide a concise technical analysis of this processor step.

Respond ONLY with a valid JSON object in this exact structure:
{{
  "processor_id"  : "{processor_id}",
  "step_name"     : "{step_name}",
  "step_type"     : "{step_type}",
  "status"        : "{status}",
  "purpose"       : "one sentence — what does this step do in the integration flow?",
  "business_impact": "one sentence — what is the business effect of adding or removing this step?",
  "technical_detail": "2-3 sentences — key technical observations from the file contents",
  "risk_level"    : "low | medium | high",
  "risk_reason"   : "brief reason for the risk level"
}}
"""


# ---------------------------------------------------------------------------
# SYNTHESIZE node prompt
# Given all findings, produce the final delta report with summary
# ---------------------------------------------------------------------------

SYNTHESIZE_REPORT_PROMPT = """
You are an Oracle Integration Cloud (OIC) integration architect producing a change review report.

You have investigated all new and removed steps between two versions of an integration.

## Integration Details
- Integration  : {integration}
- Version From : {version_from}
- Version To   : {version_to}

## Statistics
{statistics}

## Investigated Findings
{findings}

## Positionally Shifted Steps (same logic, pushed by insertions)
{shifted_steps}

## Unchanged Steps
{unchanged_steps}

## Your Task
Produce a final structured change report that an architect can use to approve or reject this integration change.

Respond ONLY with a valid JSON object in this exact structure:
{{
  "integration"     : "{integration}",
  "version_from"    : "{version_from}",
  "version_to"      : "{version_to}",
  "overall_risk"    : "low | medium | high",
  "recommendation"  : "approve | approve_with_conditions | reject",
  "summary"         : "3-5 sentences plain English summary of what changed and why",
  "new_steps"       : [
    {{
      "step_name"       : "...",
      "step_type"       : "...",
      "purpose"         : "...",
      "business_impact" : "...",
      "risk_level"      : "low | medium | high"
    }}
  ],
  "removed_steps"   : [
    {{
      "step_name"       : "...",
      "step_type"       : "...",
      "purpose"         : "...",
      "business_impact" : "...",
      "risk_level"      : "low | medium | high"
    }}
  ],
  "key_observations": ["observation 1", "observation 2", "observation 3"],
  "conditions"      : ["condition 1 if recommendation is approve_with_conditions, else empty list"]
}}
"""


# ---------------------------------------------------------------------------
# Helpers to format prompts
# ---------------------------------------------------------------------------

def format_investigate_prompt(
    processor_id : str,
    step_name    : str,
    step_type    : str,
    status       : str,
    version      : str,
    files        : List[Dict],
    file_contents: List[Dict]
) -> str:
    """Formats the INVESTIGATE_PROCESSOR_PROMPT with actual data."""

    # Build files summary table
    files_summary_lines = []
    for f in files:
        files_summary_lines.append(
            f"  - {f['file_name']:50} [{f['file_type']:10}] {f['file_role']}"
        )
    files_summary = "\n".join(files_summary_lines) if files_summary_lines else "  No files found"

    # Build file contents section — include content with clear separators
    content_sections = []
    for fc in file_contents:
        if fc.get("success") and fc.get("content"):
            content_sections.append(
                f"### {fc['file_name']} ({fc['file_type']})\n"
                f"Role: {fc['file_role']}\n"
                f"```\n{fc['content'][:2000]}\n```"  # cap at 2000 chars per file
            )
    file_contents_str = "\n\n".join(content_sections) if content_sections else "No file contents available"

    return INVESTIGATE_PROCESSOR_PROMPT.format(
        processor_id  = processor_id,
        step_name     = step_name,
        step_type     = step_type,
        status        = status,
        version       = version,
        files_summary = files_summary,
        file_contents = file_contents_str
    )


def format_synthesize_prompt(
    integration   : str,
    version_from  : str,
    version_to    : str,
    statistics    : Dict,
    findings      : List[Dict],
    shifted_steps : List[Dict],
    unchanged_steps: List[Dict]
) -> str:
    """Formats the SYNTHESIZE_REPORT_PROMPT with actual data."""

    return SYNTHESIZE_REPORT_PROMPT.format(
        integration    = integration,
        version_from   = version_from,
        version_to     = version_to,
        statistics     = json.dumps(statistics, indent=2),
        findings       = json.dumps(findings, indent=2),
        shifted_steps  = json.dumps(shifted_steps, indent=2),
        unchanged_steps= json.dumps(unchanged_steps, indent=2)
    )
