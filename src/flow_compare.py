# ---------------------------------------------------------------------------
# oic-lens | src/flow_compare.py
# Step 1 — Parse project.xml and compute structural delta.
#
# M1: new_steps + removed_steps (by processor_id)
# M2: modified_steps added (file-level content diff)
#
# Processor naming priority (per master plan):
#   1. <ns2:processorName>  if present
#   2. orchestration element name= attr  if present  (none seen in practice)
#   3. {Type}_{numeric_id}  e.g. Router_964
# ---------------------------------------------------------------------------

import xml.etree.ElementTree as ET
import logging
import os
import sys

# Allow importing file_diff from the same src/ directory
_src_dir = os.path.dirname(__file__)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

logger = logging.getLogger(__name__)

NS2 = "http://www.oracle.com/2014/03/ics/flow/definition"
NS3 = "http://www.oracle.com/2014/03/ics/project"
NSM = "http://www.oracle.com/2014/03/ics/project/definition"   # metadata fields

# Processor types excluded from delta — infrastructure, not flow steps
SKIP_TYPES = {"integrationMetadata", "messageTracker", "globalVariableDefinition"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_steps(project_xml_path: str) -> dict:
    """
    Parse a project.xml and return structured metadata.

    Returns dict with keys:
        integration_code, integration_version, integration_name,
        applications, processors, processor_count, success, error
    """
    result = {
        "integration_code":    None,
        "integration_version": None,
        "integration_name":    None,
        "applications":        [],
        "processors":          [],
        "processor_count":     0,
        "success":             False,
        "error":               None,
    }

    try:
        tree = ET.parse(project_xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        result["error"] = f"XML parse error: {e}"
        logger.error(result["error"])
        return result
    except FileNotFoundError:
        result["error"] = f"project.xml not found: {project_xml_path}"
        logger.error(result["error"])
        return result

    # Integration metadata — fields are in the /definition sub-namespace
    result["integration_code"]    = root.findtext(f"{{{NSM}}}projectCode")    or ""
    result["integration_version"] = root.findtext(f"{{{NSM}}}projectVersion") or ""
    result["integration_name"]    = root.findtext(f"{{{NSM}}}projectName")    or ""

    # Applications (external connections)
    result["applications"] = _parse_applications(root)

    # Processors — build name lookup from orchestration, then ordered list
    orchestration = root.find(f".//{{{NS2}}}orchestration")
    seq_names = _build_seq_name_map(orchestration) if orchestration is not None else {}

    raw_processors = root.findall(f".//{{{NS2}}}processor")
    ordered = _build_ordered_list(raw_processors, seq_names)

    result["processors"]      = ordered
    result["processor_count"] = len(ordered)
    result["success"]         = True

    logger.info(
        f"Extracted: {result['integration_code']} v{result['integration_version']} "
        f"— {result['processor_count']} flow processors"
    )
    return result


def compute_delta(
    source_data: dict,
    target_data: dict,
    source_extract_path: str = None,
    target_extract_path: str = None,
) -> dict:
    """
    Compare source (old) and target (new) extract_steps() results.

    When source_extract_path and target_extract_path are provided (M2+),
    also computes modified_steps via file-level content diff.

    Returns dict with keys:
        source_version, target_version, source_count, target_count,
        new_steps, removed_steps, modified_steps, positionally_shifted
    """
    source_map = {p["processor_id"]: p for p in source_data["processors"]}
    target_map = {p["processor_id"]: p for p in target_data["processors"]}

    source_ids = set(source_map.keys())
    target_ids = set(target_map.keys())

    new_ids     = target_ids - source_ids
    removed_ids = source_ids - target_ids
    common_ids  = source_ids & target_ids

    new_steps     = [target_map[pid] for pid in sorted(new_ids,     key=_numeric_id)]
    removed_steps = [source_map[pid] for pid in sorted(removed_ids, key=_numeric_id)]

    # Positionally shifted: common ids whose relative order changed (LCS backbone)
    shifted = _find_shifted(source_data["processors"], target_data["processors"], common_ids)

    # M2: Modified steps — requires extract paths
    modified_steps = []
    if source_extract_path and target_extract_path and common_ids:
        modified_steps = _compute_modified_steps(
            source_extract_path, target_extract_path,
            common_ids, source_map, target_map,
        )

    delta = {
        "source_version":       source_data["integration_version"],
        "target_version":       target_data["integration_version"],
        "source_count":         source_data["processor_count"],
        "target_count":         target_data["processor_count"],
        "new_steps":            new_steps,
        "removed_steps":        removed_steps,
        "modified_steps":       modified_steps,
        "positionally_shifted": shifted,
    }

    logger.info(
        f"Delta: {len(new_steps)} new, {len(removed_steps)} removed, "
        f"{len(modified_steps)} modified, {len(shifted)} shifted  "
        f"(v{delta['source_version']} -> v{delta['target_version']})"
    )
    return delta


def _compute_modified_steps(
    source_extract_path: str,
    target_extract_path: str,
    common_ids: set,
    source_map: dict,
    target_map: dict,
) -> list:
    """
    Call file_diff.detect_modified() for all common processor IDs.
    Uses target processor metadata (name/type) for the output records.
    """
    try:
        import file_diff
    except ImportError:
        logger.warning("file_diff not available — modified_steps will be empty")
        return []

    src_resources = file_diff.find_resources_dir(source_extract_path)
    tgt_resources = file_diff.find_resources_dir(target_extract_path)

    if not src_resources:
        logger.warning(f"resources/ dir not found in source: {source_extract_path}")
        return []
    if not tgt_resources:
        logger.warning(f"resources/ dir not found in target: {target_extract_path}")
        return []

    # Processor metadata: prefer target, fall back to source
    processor_meta = {}
    for pid in common_ids:
        meta = target_map.get(pid) or source_map.get(pid) or {}
        processor_meta[pid] = meta

    return file_diff.detect_modified(src_resources, tgt_resources, common_ids, processor_meta)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_applications(root) -> list:
    apps = []
    for app in root.findall(f".//{{{NS2}}}application"):
        role    = app.findtext(f"{{{NS2}}}role") or ""
        adapter = app.find(f"{{{NS2}}}adapter")
        code    = adapter.findtext(f"{{{NS2}}}code") if adapter is not None else ""
        name    = adapter.findtext(f"{{{NS2}}}name") if adapter is not None else ""
        operation = ""
        for direction in ("inbound", "outbound"):
            op = app.findtext(f".//{{{NS2}}}{direction}/{{{NS2}}}operation")
            if op:
                operation = op
                break
        apps.append({
            "role":      role,
            "code":      code or "",
            "name":      name or "",
            "operation": operation,
        })
    return apps


def _build_seq_name_map(orchestration) -> dict:
    """
    Walk orchestration tree; return {processor_id: name} for any sequence
    element that has both refUri=processor_xxx AND a name= attribute.
    In practice this is always empty for this integration type, but kept per spec.
    """
    seq_names = {}
    for el in orchestration.iter():
        ref  = el.get("refUri")
        name = el.get("name")
        if ref and ref.startswith("processor_") and "/" not in ref and name:
            seq_names[ref] = name
    return seq_names


def _build_ordered_list(raw_processors: list, seq_names: dict) -> list:
    """Build filtered, named processor list in XML document order."""
    ordered = []
    for pos, p in enumerate(raw_processors):
        pid   = p.get("name")
        ptype = p.findtext(f"{{{NS2}}}type") or "unknown"

        if ptype in SKIP_TYPES:
            continue

        # Naming priority: processorName > seq name attr > type_id fallback
        pname = (
            p.findtext(f"{{{NS2}}}processorName")
            or seq_names.get(pid)
            or _fallback_name(pid, ptype)
        )

        ordered.append({
            "processor_id": pid,
            "type":         ptype,
            "name":         pname,
            "position":     pos,
        })

    return ordered


def _fallback_name(processor_id: str, ptype: str) -> str:
    numeric    = processor_id.replace("processor_", "")
    type_label = _type_display(ptype)
    return f"{type_label}_{numeric}"


def _type_display(ptype: str) -> str:
    labels = {
        "assignment":          "Assign",
        "transformer":         "Map",
        "contentBasedRouter":  "Router",
        "notification":        "Notify",
        "for":                 "ForEach",
        "while":               "While",
        "catch":               "Catch",
        "catchAll":            "CatchAll",
        "stitch":              "Stitch",
        "wait":                "Wait",
        "activityStreamLogger":"Logger",
    }
    return labels.get(ptype, ptype.capitalize())


def _numeric_id(processor_id: str) -> int:
    try:
        return int(processor_id.replace("processor_", ""))
    except ValueError:
        return 0


def _find_shifted(source_procs: list, target_procs: list, common_ids: set) -> list:
    """
    LCS on common processor IDs (document order) to find the stable backbone.
    Processors in common_ids but NOT in the LCS = positionally shifted.
    """
    src_ids = [p["processor_id"] for p in source_procs if p["processor_id"] in common_ids]
    tgt_ids = [p["processor_id"] for p in target_procs if p["processor_id"] in common_ids]
    lcs_ids = set(_lcs(src_ids, tgt_ids))
    return [p for p in target_procs if p["processor_id"] in common_ids and p["processor_id"] not in lcs_ids]


def _lcs(a: list, b: list) -> list:
    """Standard LCS returning the common subsequence as a list."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    result = []
    i, j = m, n
    while i > 0 and j > 0:
        if a[i-1] == b[j-1]:
            result.append(a[i-1])
            i -= 1
            j -= 1
        elif dp[i-1][j] >= dp[i][j-1]:
            i -= 1
        else:
            j -= 1
    return result[::-1]
