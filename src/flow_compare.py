# ---------------------------------------------------------------------------
# iar-lens | src/flow_compare.py
# Responsible for: parsing project.xml and computing flow step delta
# ---------------------------------------------------------------------------

import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)

# XML namespaces used in OIC project.xml
NS = {
    "ns3": "http://www.oracle.com/2014/03/ics/project",
    "ns2": "http://www.oracle.com/2014/03/ics/flow/definition",
    "ns" : "http://www.oracle.com/2014/03/ics/project/definition"
}

# Step types to skip — infrastructure/boilerplate, not meaningful business steps
SKIP_TYPES = {"messageTracker", "integrationMetadata", "typeDefinitions"}


def extract_steps(project_xml_path: str) -> dict:
    """
    Parses project.xml and extracts:
      - Integration metadata (name, version)
      - Ordered list of flow steps (processors)
      - Registered adapter applications

    Args:
        project_xml_path: full path to project.xml

    Returns:
        dict with keys:
            - integration_name   : project code
            - version            : project version
            - steps              : ordered list of step dicts
            - applications       : list of registered adapters
            - success            : True/False
            - error              : error message if failed
    """
    result = {
        "integration_name": None,
        "version": None,
        "steps": [],
        "applications": [],
        "success": False,
        "error": None
    }

    try:
        tree = ET.parse(project_xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        result["error"] = f"Failed to parse project.xml: {str(e)}"
        logger.error(result["error"])
        return result

    # Extract integration metadata
    result["integration_name"] = _get_text(root, "projectCode")
    result["version"]          = _get_text(root, "projectVersion")

    logger.info(f"Parsing: {result['integration_name']} v{result['version']}")

    # Extract adapter applications (connections used in the flow)
    applications = []
    for app in root.iter("{http://www.oracle.com/2014/03/ics/flow/definition}application"):
        adapter_name = app.find("ns2:adapter/ns2:name", NS)
        adapter_code = app.find("ns2:adapter/ns2:code", NS)
        adapter_type = app.find("ns2:adapter/ns2:type", NS)
        role         = app.find("ns2:role", NS)

        applications.append({
            "app_id"      : app.get("name"),
            "adapter_name": adapter_name.text if adapter_name is not None else None,
            "adapter_code": adapter_code.text if adapter_code is not None else None,
            "adapter_type": adapter_type.text if adapter_type is not None else None,
            "role"        : role.text if role is not None else None
        })

    result["applications"] = applications
    logger.info(f"Found {len(applications)} adapter applications")

    # Extract ordered flow steps (processors)
    steps = []
    position = 1

    for processor in root.iter("{http://www.oracle.com/2014/03/ics/flow/definition}processor"):
        processor_id   = processor.get("name")
        step_type_elem = processor.find("ns2:type", NS)
        step_type      = step_type_elem.text if step_type_elem is not None else "unknown"

        # Skip infrastructure boilerplate steps
        if step_type in SKIP_TYPES:
            continue

        # Get human-readable processor name if available
        proc_name_elem = processor.find("ns2:processorName", NS)
        proc_name      = proc_name_elem.text if proc_name_elem is not None else None

        # Try to find referenced adapter application name for invoke steps
        ref_app = _find_referenced_app(processor, applications)

        steps.append({
            "position"    : position,
            "processor_id": processor_id,
            "type"        : step_type,
            "name"        : proc_name or ref_app or _infer_name(step_type, processor_id),
            "adapter_ref" : ref_app
        })

        position += 1

    result["steps"] = steps
    result["success"] = True

    logger.info(f"Extracted {len(steps)} flow steps")
    return result


def compute_delta(source_data: dict, target_data: dict) -> dict:
    """
    Compares two extracted flow step sequences and computes the delta.

    Uses Longest Common Subsequence (LCS) to correctly distinguish between:
      - Genuinely reordered steps (relative order changed)
      - Positionally shifted steps (same relative order, pushed by insertions)

    Args:
        source_data: result from extract_steps() for the older version
        target_data: result from extract_steps() for the newer version

    Returns:
        dict with keys:
            - new_steps           : steps in target but not in source
            - removed_steps       : steps in source but not in target
            - reordered_steps     : steps in both but with changed relative order
            - positionally_shifted: steps in both, same relative order, different absolute position
            - unchanged_steps     : steps in both at exact same absolute position
    """
    source_steps = source_data["steps"]
    target_steps = target_data["steps"]

    source_by_name = {s["name"]: s for s in source_steps}
    target_by_name = {s["name"]: s for s in target_steps}

    source_names_set = set(source_by_name.keys())
    target_names_set = set(target_by_name.keys())

    # Ordered name sequences for LCS (only common steps)
    common_names = source_names_set & target_names_set
    source_seq = [s["name"] for s in source_steps if s["name"] in common_names]
    target_seq = [s["name"] for s in target_steps if s["name"] in common_names]

    # Compute LCS — steps that maintained their relative order in both versions
    lcs_set = _lcs(source_seq, target_seq)

    # New steps — in target but not in source
    new_step_names = target_names_set - source_names_set
    new_steps = sorted([
        {
            "name"        : target_by_name[n]["name"],
            "type"        : target_by_name[n]["type"],
            "position"    : target_by_name[n]["position"],
            "processor_id": target_by_name[n]["processor_id"],
            "adapter_ref" : target_by_name[n]["adapter_ref"]
        }
        for n in new_step_names
    ], key=lambda x: x["position"])

    # Removed steps — in source but not in target
    removed_step_names = source_names_set - target_names_set
    removed_steps = sorted([
        {
            "name"        : source_by_name[n]["name"],
            "type"        : source_by_name[n]["type"],
            "position"    : source_by_name[n]["position"],
            "processor_id": source_by_name[n]["processor_id"],
            "adapter_ref" : source_by_name[n]["adapter_ref"]
        }
        for n in removed_step_names
    ], key=lambda x: x["position"])

    # Classify common steps using LCS
    reordered_steps     = []
    positionally_shifted = []
    unchanged_steps     = []

    for name in common_names:
        src = source_by_name[name]
        tgt = target_by_name[name]

        if name in lcs_set:
            # Relative order is preserved
            if src["position"] == tgt["position"]:
                # Absolute position also same — truly unchanged
                unchanged_steps.append({
                    "name"    : name,
                    "type"    : tgt["type"],
                    "position": tgt["position"]
                })
            else:
                # Absolute position changed only due to insertions/removals above
                positionally_shifted.append({
                    "name"          : name,
                    "type"          : tgt["type"],
                    "position_from" : src["position"],
                    "position_to"   : tgt["position"],
                    "shift"         : tgt["position"] - src["position"]
                })
        else:
            # Relative order changed — genuinely reordered
            reordered_steps.append({
                "name"             : name,
                "type"             : tgt["type"],
                "position_from"    : src["position"],
                "position_to"      : tgt["position"],
                "processor_id_from": src["processor_id"],
                "processor_id_to"  : tgt["processor_id"]
            })

    # Sort all lists by position for readability
    reordered_steps.sort(key=lambda x: x["position_to"])
    positionally_shifted.sort(key=lambda x: x["position_to"])
    unchanged_steps.sort(key=lambda x: x["position"])

    logger.info(
        f"Delta — New: {len(new_steps)} | "
        f"Removed: {len(removed_steps)} | "
        f"Reordered: {len(reordered_steps)} | "
        f"Shifted: {len(positionally_shifted)} | "
        f"Unchanged: {len(unchanged_steps)}"
    )

    return {
        "new_steps"           : new_steps,
        "removed_steps"       : removed_steps,
        "reordered_steps"     : reordered_steps,
        "positionally_shifted": positionally_shifted,
        "unchanged_steps"     : unchanged_steps
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lcs(source_names: list, target_names: list) -> set:
    """
    Computes the Longest Common Subsequence of two name sequences.
    Returns the set of names whose relative order is preserved in both.

    This is the key to distinguishing genuine reordering from positional
    shifts caused by insertions or removals above a step.
    """
    m, n = len(source_names), len(target_names)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if source_names[i-1] == target_names[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])

    # Backtrack to recover the LCS names
    lcs = []
    i, j = m, n
    while i > 0 and j > 0:
        if source_names[i-1] == target_names[j-1]:
            lcs.append(source_names[i-1])
            i -= 1
            j -= 1
        elif dp[i-1][j] > dp[i][j-1]:
            i -= 1
        else:
            j -= 1

    return set(lcs)

def _get_text(root, tag: str) -> str | None:
    """
    Finds a direct child tag and returns its text.
    Tries default namespace first, then no namespace.
    """
    DEFAULT_NS = "http://www.oracle.com/2014/03/ics/project/definition"
    elem = root.find(f"{{{DEFAULT_NS}}}{tag}")
    if elem is None:
        elem = root.find(tag)
    return elem.text if elem is not None else None


def _find_referenced_app(processor, applications: list) -> str | None:
    """
    Tries to find an adapter name referenced by a processor.
    Looks for invoke/target references in the processor block.
    """
    # For invoke-type processors, the adapter reference is in nested invoke elements
    for app in applications:
        app_id = app["app_id"]
        # Check if this processor references the application by searching raw attribs
        proc_str = ET.tostring(processor, encoding="unicode")
        if app_id and app_id in proc_str:
            return app["adapter_name"]
    return None


def _infer_name(step_type: str, processor_id: str) -> str:
    """
    Fallback name inference when no processorName is available.
    Produces a readable label from type + id.
    """
    type_labels = {
        "assignment"        : "Assign",
        "transformer"       : "Transform",
        "for"               : "ForEach",
        "stageFile"         : "StageFile",
        "notification"      : "Notify",
        "catchAll"          : "CatchAll",
        "contentBasedRouter": "Router",
        "scheduleReceive"   : "ScheduleTrigger",
        "target"            : "Invoke",
    }
    label = type_labels.get(step_type, step_type)
    # Extract numeric suffix from processor_id for uniqueness
    num = processor_id.replace("processor_", "")
    return f"{label}_{num}"