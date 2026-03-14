# ---------------------------------------------------------------------------
# iar-lens | src/report_generator.py
# Phase 4 — Report Generator
# Reads delta.json + report.json and produces a structured .md report
# with grouped Mermaid flow diagrams, risk color coding, and numbered steps
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
# Risk helpers
# ---------------------------------------------------------------------------

RISK_ICON = {
    "high"   : "🔴 HIGH",
    "medium" : "🟡 Medium",
    "low"    : "🟢 Low",
    "unknown": "⚪ Unknown",
}

RECOMMENDATION_ICON = {
    "approve"                 : "✅",
    "approve_with_conditions" : "🟡",
    "reject"                  : "❌",
}

def _risk(level: str) -> str:
    return RISK_ICON.get(str(level).lower(), f"⚪ {level}")

def _rec_icon(recommendation: str, overall_risk: str) -> str:
    """
    Returns the appropriate icon for the recommendation.
    approve_with_conditions uses 🔴 when overall risk is HIGH, else 🟡.
    """
    rec = str(recommendation).lower()
    if rec == "approve_with_conditions" and str(overall_risk).lower() == "high":
        return "🔴"
    return RECOMMENDATION_ICON.get(rec, "⚠️")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _trim_purpose(text: str) -> str:
    """
    Remove verbose LLM preamble from PURPOSE text.
    Strips subject phrases, leaving a clean verb-led sentence.
    e.g. 'This step transforms...' -> 'Transforms...'
         'This assignment step was responsible for assigning...' -> 'Assigns...'
    """
    if not text:
        return "—"
    patterns = [
        r"^This step (is designed to |was designed to |was responsible for |)",
        r"^This assignment step (is responsible for |was responsible for |)",
        r"^This transformer step ",
        r"^This transformation step (is responsible for |was responsible for |)",
        r"^This content-based router step ",
        r"^This `catchAll` step is designed to ",
        r"^This `for` loop ",
        r"^This 'for' loop ",
    ]
    result = text.strip()
    for pattern in patterns:
        match = re.match(pattern, result, re.IGNORECASE)
        if match:
            result = result[match.end():]
            result = result[0].upper() + result[1:] if result else result
            break
    return result


def _trim_impact(text: str) -> str:
    """
    Remove verbose LLM preamble from BUSINESS IMPACT text.
    Two categories:
      - ADDED patterns: strip wrapper, preserve the verb that follows
        e.g. 'Adding this step improves...' -> 'Improves...'
      - REMOVED patterns: strip wrapper entirely, keep remainder as-is
        e.g. 'The removal of this step means the integration...' -> 'The integration...'
    """
    if not text:
        return "—"

    # Patterns where we PRESERVE the captured verb (added step impacts)
    verb_patterns = [
        r"^Adding this step (enables|improves|introduces|ensures|enhances|provides|allows) ",
        r"^The addition of this step (enables|improves|introduces|ensures|enhances|provides|allows) ",
        r"^The introduction of this step (enables|improves|introduces|ensures|enhances|provides|allows) ",
        r"^This new step (introduces|enables|allows|provides) ",
    ]

    # Patterns where we preserve the action verb (removed step impacts with a key verb)
    removed_verb_patterns = [
        r"^Removing this (step|router|[a-z]+ step) (eliminates|removes|halts|stops|prevents) ",
        r"^The removal of this (step|router) (eliminates|removes|halts|stops|prevents) ",
    ]

    # Patterns where we just strip the preamble entirely (removed step impacts)
    strip_patterns = [
        r"^The removal of this step (means|implies) (that |)",
        r"^Removing this (step|router|[a-z]+ step) (means|implies) ",
        r"^The removal of this router (means|implies) (that |)",
    ]

    result = text.strip()

    for pattern in verb_patterns:
        match = re.match(pattern, result, re.IGNORECASE)
        if match:
            verb      = match.group(1)
            remainder = result[match.end():]
            result    = verb[0].upper() + verb[1:] + " " + remainder
            return result

    for pattern in removed_verb_patterns:
        match = re.match(pattern, result, re.IGNORECASE)
        if match:
            verb      = match.group(2)
            remainder = result[match.end():]
            result    = verb[0].upper() + verb[1:] + " " + remainder
            return result

    for pattern in strip_patterns:
        match = re.match(pattern, result, re.IGNORECASE)
        if match:
            remainder = result[match.end():]
            result    = remainder[0].upper() + remainder[1:] if remainder else remainder
            return result

    return result


def _infer_block_label(block: list, status: str) -> str:
    """
    Infer a meaningful block label from step names and types.
    Groups by dominant type or common name pattern.
    """
    names = [s["name"] for s in block]
    types = [s["type"] for s in block]

    # Check for known DHL patterns
    dhl_names = [n for n in names if "dhl" in n.lower() or "DHL" in n]
    oracle_names = [n for n in names if "oracle" in n.lower() or "Oracle" in n]
    notify_names = [n for n in names if "notification" in n.lower() or "Notification" in n]
    catch_names  = [n for n in names if "catchall" in n.lower() or "CatchAll" in n]
    loop_names   = [s["name"] for s in block if s["type"] == "for"]
    throw_names  = [s["name"] for s in block if s["type"] == "throw" or "throw" in s["name"].lower()]

    # Priority label inference — order matters: specific before generic
    if dhl_names and "for" in types:
        return "DHL File Processing Loop"
    if dhl_names and notify_names:
        return "DHL Notifications"
    if dhl_names:
        return "DHL Directory Setup"
    if oracle_names or any("oracle" in n.lower() for n in names):
        return "Oracle Inventory Sync & Fault Handling"
    if throw_names and notify_names:
        return "Fault Handling & Notifications"
    if catch_names and notify_names:
        return "Error Handling"
    if loop_names and notify_names:
        return "FTP Directory Listing & Notification"
    if loop_names:
        return "FTP Directory Listing"
    if notify_names:
        return "Notifications"
    if "for" in types and status == "new":
        return "FTP Directory Listing"
    if "for" in types and status == "removed":
        return "Loop Processing"
    if all(t == "assignment" for t in types):
        return "Variable Assignments"
    if all(t == "transformer" for t in types):
        return "Data Transformations"
    if "contentBasedRouter" in types:
        return "Routing Logic"
    if "throw" in types:
        return "Fault Handling"

    # Fallback — use first step name cleaned up
    first_name = names[0].replace("_", " ").strip()
    parts = [p for p in first_name.split() if not p.isdigit()]
    label = " ".join(parts[:3])
    if len(block) > 1:
        label += f" & {len(block)-1} more"
    return label


# ---------------------------------------------------------------------------
# Mermaid helpers
# ---------------------------------------------------------------------------

def _node(step: dict, style: str) -> str:
    name  = step["name"].replace('"', "")
    stype = step.get("type", "").replace('"', "")
    return f'[{name}<br/>{stype}]:::{style}'


def _build_window(full_sequence: list, positions: list, status: str) -> str:
    pos_set      = set(positions)
    all_positions = [s["position"] for s in full_sequence]

    first_pos = min(positions)
    last_pos  = max(positions)

    try:
        first_idx = all_positions.index(first_pos)
        last_idx  = all_positions.index(last_pos)
    except ValueError:
        return ""

    start_idx = max(0, first_idx - 2)
    end_idx   = min(len(full_sequence) - 1, last_idx + 2)
    window    = full_sequence[start_idx : end_idx + 1]

    node_ids  = []
    node_defs = []

    for i, step in enumerate(window):
        nid   = f"N{i}"
        style = status if step["position"] in pos_set else "ctx"
        node_ids.append(nid)
        node_defs.append(f"    {nid}{_node(step, style)}")

    edges = [f"    {node_ids[i]} --> {node_ids[i+1]}" for i in range(len(node_ids) - 1)]

    if status == "new":
        classdef = (
            "    classDef new fill:#ccffcc,stroke:#008800,color:#004400\n"
            "    classDef ctx fill:#e8e8e8,stroke:#aaa,color:#444"
        )
    else:
        classdef = (
            "    classDef removed fill:#ffcccc,stroke:#cc0000,color:#800000\n"
            "    classDef ctx fill:#e8e8e8,stroke:#aaa,color:#444"
        )

    lines = ["```mermaid", "flowchart LR"] + node_defs + edges + [classdef, "```"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Block grouping
# ---------------------------------------------------------------------------

def _group_consecutive(steps: list, gap: int = 3) -> list:
    if not steps:
        return []
    sorted_steps  = sorted(steps, key=lambda s: s["position"])
    blocks        = []
    current_block = [sorted_steps[0]]
    for step in sorted_steps[1:]:
        if step["position"] - current_block[-1]["position"] <= gap:
            current_block.append(step)
        else:
            blocks.append(current_block)
            current_block = [step]
    blocks.append(current_block)
    return blocks


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_header(delta: dict, report: dict) -> str:
    integration  = delta.get("integration", "")
    version_from = delta.get("version_from", "")
    version_to   = delta.get("version_to", "")
    generated_at = report.get("generated_at", datetime.now(timezone.utc).isoformat())
    files_read   = report.get("files_read", 0)
    processors   = report.get("processors_investigated", 0)
    overall_risk    = _risk(report.get("overall_risk", "unknown"))
    rec_raw         = report.get("recommendation", "")
    rec_label       = rec_raw.replace("_", " ").upper()
    rec_icon        = _rec_icon(rec_raw, report.get("overall_risk", ""))

    return f"""# {integration} — Change Review Report

**Version:** {version_from} → {version_to}
**Overall Risk:** {overall_risk} | **Recommendation:** {rec_icon} {rec_label}

---

## 1. Header

| Field | Value |
|---|---|
| **Integration** | {integration} |
| **Version From** | {version_from} |
| **Version To** | {version_to} |
| **Generated At** | {generated_at} |
| **Generated By** | iar-lens |
| **Files Read** | {files_read} |
| **Processors Investigated** | {processors} |"""


def _build_executive_summary(report: dict, delta: dict) -> str:
    stats        = delta.get("statistics", {})
    overall_risk    = _risk(report.get("overall_risk", "unknown"))
    rec_raw         = report.get("recommendation", "")
    rec             = rec_raw.replace("_", " ").upper()
    rec_icon        = _rec_icon(rec_raw, report.get("overall_risk", ""))
    new_steps       = report.get("new_steps", [])
    removed_steps= report.get("removed_steps", [])

    # What changed
    what_changed = (
        f"- Step count changed from **{stats.get('source_step_count','?')} → "
        f"{stats.get('target_step_count','?')}** "
        f"({stats.get('new_steps_count',0)} new, "
        f"{stats.get('removed_steps_count',0)} removed, "
        f"{stats.get('positionally_shifted',0)} positionally shifted)"
    )

    # What was added — trimmed one-liners
    added_lines = "\n".join(
        f"- **{s['step_name']}** ({s['step_type']}) — {_trim_purpose(s.get('purpose',''))}"
        for s in new_steps
    )

    # What was removed — trimmed one-liners
    removed_lines = "\n".join(
        f"- **{s['step_name']}** ({s['step_type']}) — {_trim_purpose(s.get('purpose',''))}"
        for s in removed_steps
    )

    return f"""
---

## 2. Executive Summary

| Field | Value |
|---|---|
| **Overall Risk** | {overall_risk} |
| **Recommendation** | {rec_icon} {rec} |

**What Changed:**
{what_changed}

**What Was Added:**
{added_lines}

**What Was Removed:**
{removed_lines}"""


def _build_statistics(delta: dict) -> str:
    s = delta.get("statistics", {})
    return f"""
---

## 3. Statistics

| Metric | Count |
|---|---|
| Source step count | {s.get('source_step_count', 0)} |
| Target step count | {s.get('target_step_count', 0)} |
| New steps | {s.get('new_steps_count', 0)} |
| Removed steps | {s.get('removed_steps_count', 0)} |
| Genuinely reordered | {s.get('reordered_count', 0)} |
| Positionally shifted | {s.get('positionally_shifted', 0)} |
| Unchanged | {s.get('unchanged_count', 0)} |"""


def _build_legend() -> str:
    return """
---

## 4. Legend

| Style | Meaning |
|---|---|
| 🟢 Green box | New step added in target version |
| 🔴 Red box | Removed step, existed in source version |
| ⚪ Grey box | Context step, unchanged or shifted, shown for reference |
| 🔴 HIGH | High risk change — requires immediate attention |
| 🟡 Medium | Medium risk — verify before approving |
| 🟢 Low | Low risk — informational |"""


def _build_new_steps(delta: dict, report: dict) -> tuple:
    """Returns (section_md, next_step_num, next_block_num)"""
    new_steps_delta  = delta["delta"]["new_steps"]
    new_steps_report = {s["step_name"]: s for s in report.get("new_steps", [])}
    target_sequence  = _build_target_sequence(delta)

    blocks    = _group_consecutive(new_steps_delta)
    sections  = ["\n---\n\n## 5. New Steps"]
    step_num  = 1
    block_num = 1

    for block in blocks:
        positions = [s["position"] for s in block]
        pos_range = (
            f"position {positions[0]}"
            if len(positions) == 1
            else f"positions {positions[0]}–{positions[-1]}"
        )
        label   = _infer_block_label(block, "new")
        diagram = _build_window(target_sequence, positions, "new")

        sections.append(f"\n### Block {block_num} — {label} ({pos_range})\n")
        sections.append(diagram)
        sections.append("\n| # | Step | Type | Purpose | Business Impact | Risk |")
        sections.append("|---|---|---|---|---|---|")

        for step in block:
            rdata   = new_steps_report.get(step["name"], {})
            purpose = _trim_purpose(rdata.get("purpose", "—"))
            impact  = _trim_impact(rdata.get("business_impact", "—"))
            risk    = _risk(rdata.get("risk_level", "unknown"))
            sections.append(
                f"| {step_num} | {step['name']} | {step['type']} | {purpose} | {impact} | {risk} |"
            )
            step_num  += 1
        block_num += 1

    return "\n".join(sections), step_num, block_num


def _build_removed_steps(delta: dict, report: dict, start_step: int, start_block: int) -> str:
    removed_steps_delta  = delta["delta"]["removed_steps"]
    removed_steps_report = {s["step_name"]: s for s in report.get("removed_steps", [])}
    source_sequence      = _build_source_sequence(delta)

    blocks    = _group_consecutive(removed_steps_delta)
    sections  = ["\n---\n\n## 6. Removed Steps"]
    step_num  = start_step
    block_num = start_block

    for block in blocks:
        positions  = [s["position"] for s in block]
        pos_range  = (
            f"position {positions[0]}"
            if len(positions) == 1
            else f"positions {positions[0]}–{positions[-1]}"
        )
        label      = _infer_block_label(block, "removed")
        diagram    = _build_window(source_sequence, positions, "removed")

        high_risk  = any(
            removed_steps_report.get(s["name"], {}).get("risk_level", "").lower() == "high"
            for s in block
        )
        risk_badge = " 🔴 HIGH RISK" if high_risk else ""

        sections.append(f"\n### Block {block_num} — {label} ({pos_range}){risk_badge}\n")
        sections.append(diagram)
        sections.append("\n| # | Step | Type | Purpose | Business Impact | Risk |")
        sections.append("|---|---|---|---|---|---|")

        for step in block:
            rdata   = removed_steps_report.get(step["name"], {})
            purpose = _trim_purpose(rdata.get("purpose", "—"))
            impact  = _trim_impact(rdata.get("business_impact", "—"))
            risk    = _risk(rdata.get("risk_level", "unknown"))
            sections.append(
                f"| {step_num} | {step['name']} | {step['type']} | {purpose} | {impact} | {risk} |"
            )
            step_num  += 1
        block_num += 1

    return "\n".join(sections)


def _build_observations(report: dict) -> str:
    observations = report.get("key_observations", [])
    lines = ["\n---\n\n## 7. Key Observations\n"]
    for i, obs in enumerate(observations, 1):
        lines.append(f"{i}. {obs}")
    return "\n".join(lines)


def _build_conditions(report: dict) -> str:
    conditions = report.get("conditions", [])
    lines = ["\n---\n\n## 8. Approval Conditions\n"]
    lines.append("| # | Condition | Risk |")
    lines.append("|---|---|---|")
    for i, cond in enumerate(conditions, 1):
        risk = "🔴 HIGH" if any(
            w in cond.lower()
            for w in ["removal", "critical", "halted", "blind", "intentional", "no file"]
        ) else "🟡 Medium"
        lines.append(f"| {i} | {cond} | {risk} |")
    lines.append(
        "\n---\n\n"
        "*Generated by **iar-lens** — Hybrid Python + LLM IAR Change Review Tool*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sequence builders
# ---------------------------------------------------------------------------

def _build_target_sequence(delta: dict) -> list:
    steps = []
    for s in delta["delta"]["new_steps"]:
        steps.append({"name": s["name"], "type": s["type"], "position": s["position"]})
    for s in delta["delta"]["positionally_shifted"]:
        steps.append({"name": s["name"], "type": s["type"], "position": s["position_to"]})
    for s in delta["delta"]["unchanged_steps"]:
        steps.append({"name": s["name"], "type": s["type"], "position": s["position"]})
    return sorted(steps, key=lambda x: x["position"])


def _build_source_sequence(delta: dict) -> list:
    steps = []
    for s in delta["delta"]["removed_steps"]:
        steps.append({"name": s["name"], "type": s["type"], "position": s["position"]})
    for s in delta["delta"]["positionally_shifted"]:
        steps.append({"name": s["name"], "type": s["type"], "position": s["position_from"]})
    for s in delta["delta"]["unchanged_steps"]:
        steps.append({"name": s["name"], "type": s["type"], "position": s["position"]})
    return sorted(steps, key=lambda x: x["position"])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report(
    delta_path : str = None,
    report_path: str = None,
    output_path: str = None
) -> str:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    delta_path   = delta_path  or os.path.join(project_root, config.OUTPUT_DIR, "delta.json")
    report_path  = report_path or os.path.join(project_root, config.OUTPUT_DIR, "report.json")

    logger.info(f"Loading delta  : {delta_path}")
    logger.info(f"Loading report : {report_path}")

    with open(delta_path,  "r", encoding="utf-8") as f:
        delta = json.load(f)
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    integration  = delta.get("integration", "integration")
    version_from = delta.get("version_from", "v1")
    version_to   = delta.get("version_to",   "v2")

    if not output_path:
        filename    = f"{integration}_{version_from}_to_{version_to}_change_report.md"
        output_path = os.path.join(project_root, config.OUTPUT_DIR, filename)

    new_steps_section, next_step, next_block = _build_new_steps(delta, report)

    sections = [
        _build_header(delta, report),
        _build_executive_summary(report, delta),
        _build_statistics(delta),
        _build_legend(),
        new_steps_section,
        _build_removed_steps(delta, report, start_step=next_step, start_block=next_block),
        _build_observations(report),
        _build_conditions(report),
    ]

    md_content = "\n".join(sections)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    logger.info(f"Report written : {output_path}")
    print(f"\n✅ Report generated: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_report()