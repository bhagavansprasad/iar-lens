# ---------------------------------------------------------------------------
# oic-lens | src/file_diff.py
# Step 1 — M2: File-level content diff for common processors.
#
# Detects which processors were modified between two versions by comparing
# the actual file contents in their workspace resource directories.
#
# Rules (per master plan + oic_resource_file_reference.md):
#   - Skip excluded files (stateinfo, .dvm, .zip, etc.)
#   - Skip deferred files (.wsdl, .jca, .xsd — deferred to M8)
#   - Normalise paths: strip resourcegroup_{ID}, preserve output_{ID}
#   - XSL hash rule: one req_*.xsl each side → modified (not removed+added)
#   - stitch.json: JSON key-sort before comparing (suppress OIC key-order churn)
#   - Strip trailing whitespace per line before comparing expr.properties etc.
# ---------------------------------------------------------------------------

import os
import re
import json
import fnmatch
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exclusion and deferral predicates (mirrored from master plan)
# ---------------------------------------------------------------------------

def is_excluded(filename: str) -> bool:
    """Files never included in diff output — provably zero semantic value."""
    if filename.endswith("stateinfo.json"):    return True  # UI designer state
    if filename.endswith("_stateinfo.xml"):    return True  # XSL mapper UI state
    if filename.endswith(".dvm"):              return True  # PII lookups
    if filename == "nxsdmetadata.properties":  return True  # always empty
    if filename == "oic_project.properties":   return True  # internal hash
    if filename == "project.yaml":             return True  # timestamps only
    if filename.endswith(".zip"):              return True  # binary
    return False


def is_deferred(filename: str) -> bool:
    """LLM-readable but excluded until M8 security review milestone."""
    if filename.endswith(".wsdl"):  return True
    if filename.endswith(".jca"):   return True
    if filename.endswith(".xsd"):   return True
    return False


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------

def find_resources_dir(extract_path: str) -> str | None:
    """
    Find the integration resources/ directory inside an extracted CAR/IAR workspace.

    Two workspace layouts observed:

    FACTORYDOCK pairs:
      extract_path/project/integrations/{CODE}_{VER}/resources/
      (resources/ is a child of integrations/{CODE}_{VER}/)

    INT303 pair (55-56):
      extract_path/icspackage/project/{CODE}_{VER}/resources/
      (no integrations/ segment — resources/ is a direct child of the versioned dir)

    In both cases:
      - resources/ contains processor_* subdirectories
      - resources/ must NOT be under ai_agents/ (which also has processor_* children)
    """
    for root, dirs, _ in os.walk(extract_path):
        # Limit depth
        depth = root.replace(extract_path, "").count(os.sep)
        if depth >= 8:
            dirs.clear()
            continue

        if os.path.basename(root) != "resources":
            continue

        norm = root.replace("\\", "/")

        # Exclude ai_agents resources — they are not integration flow processors
        if "/ai_agents/" in norm:
            continue

        # Confirm it has processor_* subdirs
        if any(d.startswith("processor_") for d in dirs):
            return root

    return None


def _list_processor_files(resources_dir: str, processor_id: str) -> dict[str, str]:
    """
    Walk the processor's resource folder and return {normalised_key: abs_path}.

    Normalisation:
      - Strip resourcegroup_{ID} path segment
      - Preserve output_{ID} path segment (router branch identifier)
      - Skip excluded and deferred files
    """
    proc_dir = os.path.join(resources_dir, processor_id)
    if not os.path.isdir(proc_dir):
        return {}

    files: dict[str, str] = {}
    for dirpath, _dirs, filenames in os.walk(proc_dir):
        for fname in filenames:
            if is_excluded(fname) or is_deferred(fname):
                continue
            abs_path = os.path.join(dirpath, fname)
            key = _normalise_key(proc_dir, abs_path)
            files[key] = abs_path

    return files


def _normalise_key(proc_dir: str, abs_path: str) -> str:
    """
    Strip proc_dir prefix and resourcegroup_{N} segments.
    Preserve output_{N} segments.

    Examples:
      proc_dir/.../resourcegroup_5/expr.properties
        → expr.properties
      proc_dir/output_966/resourcegroup_5/expr.properties
        → output_966/expr.properties
    """
    rel = os.path.relpath(abs_path, proc_dir)
    parts = rel.replace("\\", "/").split("/")
    # Remove resourcegroup_* segments; keep everything else
    parts = [p for p in parts if not re.fullmatch(r"resourcegroup_\d+", p)]
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Content normalisation
# ---------------------------------------------------------------------------

def _read_and_normalise(abs_path: str) -> str:
    """
    Read a file and apply normalisation rules:
      - stitch.json: JSON key-sort
      - *.properties / *.data / *.xsl / *.jq / *.txt: strip trailing whitespace per line
      - Everything else: raw text
    """
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        logger.warning(f"Could not read {abs_path}: {e}")
        return ""

    fname = os.path.basename(abs_path)

    if fname == "stitch.json":
        try:
            obj = json.loads(raw)
            return json.dumps(obj, sort_keys=True, indent=2)
        except json.JSONDecodeError:
            pass  # fall through to plain strip

    # Strip trailing whitespace per line (covers .properties, .data, .xsl, .jq, .txt)
    lines = raw.splitlines()
    return "\n".join(line.rstrip() for line in lines)


# ---------------------------------------------------------------------------
# XSL hash detection
# ---------------------------------------------------------------------------

def _xsl_keys(file_map: dict[str, str]) -> list[str]:
    """Return all normalised keys matching req_*.xsl."""
    return [k for k in file_map if fnmatch.fnmatch(os.path.basename(k), "req_*.xsl")]


# ---------------------------------------------------------------------------
# Core diff logic
# ---------------------------------------------------------------------------

def detect_modified(
    src_resources: str,
    tgt_resources: str,
    common_ids: set[str],
    processor_meta: dict[str, dict],
) -> list[dict]:
    """
    For each processor in common_ids, compare file contents between source
    and target workspace resource directories.

    Returns a list of modified processor dicts:
    [
      {
        "processor_id": "processor_964",
        "type": "contentBasedRouter",
        "name": "Router_964",
        "changed_files": [
          {
            "key": "output_966/expr.properties",
            "old_content": "...",
            "new_content": "..."
          }
        ]
      },
      ...
    ]

    Only processors with at least one changed file are returned.
    """
    modified: list[dict] = []

    for pid in sorted(common_ids, key=_numeric_id):
        src_files = _list_processor_files(src_resources, pid)
        tgt_files = _list_processor_files(tgt_resources, pid)

        changed_files = _diff_processor_files(src_files, tgt_files)

        if changed_files:
            meta = processor_meta.get(pid, {})
            modified.append({
                "processor_id":  pid,
                "type":          meta.get("type", ""),
                "name":          meta.get("name", ""),
                "changed_files": changed_files,
            })
            logger.debug(
                f"  Modified: {pid} ({meta.get('name', '')}) — "
                f"{len(changed_files)} changed file(s)"
            )

    logger.info(f"detect_modified: {len(modified)} processor(s) modified out of {len(common_ids)} common")
    return modified


def _diff_processor_files(
    src_files: dict[str, str],
    tgt_files: dict[str, str],
) -> list[dict]:
    """
    Compare two {key: abs_path} file maps for a single processor.
    Returns list of {key, old_content, new_content} for every changed file.
    """
    changed: list[dict] = []

    # --- Handle XSL hash filename change ---
    # If source has exactly one req_*.xsl and target has exactly one req_*.xsl,
    # treat as a single modified file regardless of hash difference.
    src_xsl_keys = _xsl_keys(src_files)
    tgt_xsl_keys = _xsl_keys(tgt_files)

    xsl_handled_src: set[str] = set()
    xsl_handled_tgt: set[str] = set()

    if len(src_xsl_keys) == 1 and len(tgt_xsl_keys) == 1:
        src_k, tgt_k = src_xsl_keys[0], tgt_xsl_keys[0]
        old_c = _read_and_normalise(src_files[src_k])
        new_c = _read_and_normalise(tgt_files[tgt_k])
        if old_c != new_c:
            # Report using the target key (new canonical name) — include both filenames
            changed.append({
                "key":         tgt_k,
                "old_key":     src_k,
                "old_content": old_c,
                "new_content": new_c,
            })
        xsl_handled_src.add(src_k)
        xsl_handled_tgt.add(tgt_k)
    elif len(src_xsl_keys) > 1 or len(tgt_xsl_keys) > 1:
        # Multiple XSLs — match by output branch prefix (output_{ID}/req_*.xsl)
        src_by_prefix = _group_xsl_by_output(src_xsl_keys)
        tgt_by_prefix = _group_xsl_by_output(tgt_xsl_keys)
        for prefix, src_k in src_by_prefix.items():
            tgt_k = tgt_by_prefix.get(prefix)
            if tgt_k:
                old_c = _read_and_normalise(src_files[src_k])
                new_c = _read_and_normalise(tgt_files[tgt_k])
                if old_c != new_c:
                    changed.append({
                        "key":         tgt_k,
                        "old_key":     src_k,
                        "old_content": old_c,
                        "new_content": new_c,
                    })
                xsl_handled_src.add(src_k)
                xsl_handled_tgt.add(tgt_k)

    # --- All other files: compare by normalised key ---
    src_non_xsl = {k: v for k, v in src_files.items() if k not in xsl_handled_src}
    tgt_non_xsl = {k: v for k, v in tgt_files.items() if k not in xsl_handled_tgt}

    all_keys = set(src_non_xsl.keys()) | set(tgt_non_xsl.keys())

    for key in sorted(all_keys):
        in_src = key in src_non_xsl
        in_tgt = key in tgt_non_xsl

        if in_src and in_tgt:
            old_c = _read_and_normalise(src_non_xsl[key])
            new_c = _read_and_normalise(tgt_non_xsl[key])
            if old_c != new_c:
                changed.append({"key": key, "old_content": old_c, "new_content": new_c})
        elif in_src and not in_tgt:
            # File removed from this processor
            old_c = _read_and_normalise(src_non_xsl[key])
            changed.append({"key": key, "old_content": old_c, "new_content": ""})
        elif not in_src and in_tgt:
            # File added to this processor
            new_c = _read_and_normalise(tgt_non_xsl[key])
            changed.append({"key": key, "old_content": "", "new_content": new_c})

    return changed


def _group_xsl_by_output(xsl_keys: list[str]) -> dict[str, str]:
    """
    Group req_*.xsl keys by their output_{ID} prefix.
    Keys without an output prefix are grouped under "".
    Returns {prefix: key}.
    """
    groups: dict[str, str] = {}
    for k in xsl_keys:
        parts = k.split("/")
        if len(parts) == 2 and parts[0].startswith("output_"):
            groups[parts[0]] = k
        else:
            groups[""] = k
    return groups


def _numeric_id(processor_id: str) -> int:
    try:
        return int(processor_id.replace("processor_", ""))
    except ValueError:
        return 0
