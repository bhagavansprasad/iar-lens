# ---------------------------------------------------------------------------
# iar-lens | src/file_reader.py
# Responsible for: reading files and listing processor files from workspace
# Designed to be registered as LangGraph tools in Phase 3
# ---------------------------------------------------------------------------

import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config

logger = logging.getLogger(__name__)

# Supported file types and their human-readable role descriptions
FILE_TYPE_ROLES = {
    "xsl"       : "XSLT transformation mapper — defines field mapping logic",
    "xml"       : "XML configuration — JCA adapter or state definition",
    "json"      : "JSON state/layout info",
    "properties": "Expression or assignment definition (key=value pairs)",
    "wsdl"      : "WSDL service interface definition",
    "xsd"       : "XML Schema definition",
    "jca"       : "JCA adapter connection configuration",
    "data"      : "Notification template (email body / subject / to / from)",
}


def read_file(file_path: str) -> dict:
    """
    Reads a single file from the IAR workspace and returns its content
    with metadata.

    Args:
        file_path: path to the file — can be absolute or relative to
                   project root

    Returns:
        dict with keys:
            - file_path  : normalized path as provided
            - file_name  : basename of the file
            - file_type  : extension (xsl, xml, json, properties, etc.)
            - file_role  : human-readable description of what this file type does
            - size_bytes : file size in bytes
            - line_count : number of lines in the file
            - content    : raw file content as string
            - success    : True/False
            - error      : error message if success is False
    """
    result = {
        "file_path" : file_path,
        "file_name" : os.path.basename(file_path),
        "file_type" : None,
        "file_role" : None,
        "size_bytes": None,
        "line_count": None,
        "content"   : None,
        "success"   : False,
        "error"     : None
    }

    # Resolve path — if relative, resolve from project root
    resolved_path = _resolve_path(file_path)

    if not os.path.exists(resolved_path):
        result["error"] = f"File not found: {resolved_path}"
        logger.warning(result["error"])
        return result

    if not os.path.isfile(resolved_path):
        result["error"] = f"Path is not a file: {resolved_path}"
        logger.warning(result["error"])
        return result

    # Determine file type from extension
    _, ext = os.path.splitext(resolved_path)
    file_type = ext.lstrip(".").lower()
    result["file_type"] = file_type
    result["file_role"] = FILE_TYPE_ROLES.get(file_type, f"Unknown file type: {file_type}")

    # File size
    result["size_bytes"] = os.path.getsize(resolved_path)

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            content = f.read()

        result["line_count"] = content.count("\n") + 1
        result["content"]    = content
        result["success"]    = True

        logger.info(
            f"Read: {os.path.basename(resolved_path)} "
            f"({result['size_bytes']} bytes, {result['line_count']} lines)"
        )

    except UnicodeDecodeError:
        # Fallback to latin-1 for files with non-UTF-8 encoding
        try:
            with open(resolved_path, "r", encoding="latin-1") as f:
                content = f.read()
            result["line_count"] = content.count("\n") + 1
            result["content"]    = content
            result["success"]    = True
            logger.info(f"Read (latin-1 fallback): {os.path.basename(resolved_path)}")
        except Exception as e:
            result["error"] = f"Failed to read file: {str(e)}"
            logger.error(result["error"])

    except Exception as e:
        result["error"] = f"Failed to read file: {str(e)}"
        logger.error(result["error"])

    return result


def list_processor_files(processor_id: str, version: str = None) -> dict:
    """
    Lists all files associated with a given processor ID inside the workspace.

    Args:
        processor_id: the processor folder name e.g. "processor_1345"
        version     : optional version string e.g. "03.00.0011" to target
                      a specific IAR extraction. If None, searches all.

    Returns:
        dict with keys:
            - processor_id : as provided
            - version      : as provided or "all"
            - files        : list of file info dicts (path, name, type, role, size_bytes)
            - file_count   : total number of files found
            - success      : True/False
            - error        : error message if success is False
    """
    result = {
        "processor_id": processor_id,
        "version"     : version or "all",
        "files"       : [],
        "file_count"  : 0,
        "success"     : False,
        "error"       : None
    }

    workspace = _resolve_path(config.WORKSPACE_DIR)

    if not os.path.exists(workspace):
        result["error"] = f"Workspace not found: {workspace}"
        logger.error(result["error"])
        return result

    found_files = []

    for dirpath, dirnames, filenames in os.walk(workspace):
        # Filter by version if specified
        if version and version not in dirpath:
            continue

        # Check if this directory is under the target processor folder
        if processor_id in dirpath.split(os.sep):
            for filename in sorted(filenames):
                full_path = os.path.join(dirpath, filename)
                _, ext = os.path.splitext(filename)
                file_type = ext.lstrip(".").lower()

                found_files.append({
                    "file_path" : full_path,
                    "file_name" : filename,
                    "file_type" : file_type,
                    "file_role" : FILE_TYPE_ROLES.get(file_type, f"Unknown: {file_type}"),
                    "size_bytes": os.path.getsize(full_path)
                })

    if not found_files:
        result["error"] = (
            f"No files found for processor '{processor_id}'"
            + (f" in version '{version}'" if version else "")
        )
        logger.warning(result["error"])
        return result

    result["files"]      = found_files
    result["file_count"] = len(found_files)
    result["success"]    = True

    logger.info(
        f"Listed {len(found_files)} file(s) for {processor_id}"
        + (f" (v{version})" if version else "")
    )

    return result


def list_all_processor_files(version: str) -> dict:
    """
    Lists all processor folders and their files for a given IAR version.
    Useful for giving the agent a complete map of what's available to read.

    Args:
        version: version string e.g. "03.00.0011"

    Returns:
        dict with keys:
            - version     : as provided
            - processors  : dict keyed by processor_id, value is list of file info dicts
            - total_files : total file count across all processors
            - success     : True/False
            - error       : error message if success is False
    """
    result = {
        "version"    : version,
        "processors" : {},
        "total_files": 0,
        "success"    : False,
        "error"      : None
    }

    workspace = _resolve_path(config.WORKSPACE_DIR)

    if not os.path.exists(workspace):
        result["error"] = f"Workspace not found: {workspace}"
        logger.error(result["error"])
        return result

    # Find the extraction folder matching the version
    version_dir = None
    for entry in os.listdir(workspace):
        if version in entry:
            version_dir = os.path.join(workspace, entry)
            break

    if not version_dir:
        result["error"] = f"No extracted folder found for version: {version}"
        logger.error(result["error"])
        return result

    processors = {}
    total = 0

    for dirpath, dirnames, filenames in os.walk(version_dir):
        parts = dirpath.split(os.sep)
        # Find processor_XXX segments in the path
        proc_parts = [p for p in parts if p.startswith("processor_")]
        if not proc_parts or not filenames:
            continue

        processor_id = proc_parts[0]  # Use outermost processor folder
        if processor_id not in processors:
            processors[processor_id] = []

        for filename in sorted(filenames):
            full_path = os.path.join(dirpath, filename)
            _, ext = os.path.splitext(filename)
            file_type = ext.lstrip(".").lower()

            processors[processor_id].append({
                "file_path" : full_path,
                "file_name" : filename,
                "file_type" : file_type,
                "file_role" : FILE_TYPE_ROLES.get(file_type, f"Unknown: {file_type}"),
                "size_bytes": os.path.getsize(full_path)
            })
            total += 1

    result["processors"]  = processors
    result["total_files"] = total
    result["success"]     = True

    logger.info(
        f"Mapped {len(processors)} processors, "
        f"{total} total files for v{version}"
    )

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_path(path: str) -> str:
    """
    Resolves a path relative to the project root if not absolute.
    Project root is two levels up from this file (src/../)
    """
    if os.path.isabs(path):
        return path
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    return os.path.join(project_root, path)
