# ---------------------------------------------------------------------------
# iar-lens | src/extractor.py
# Responsible for: unzipping .iar files and locating project.xml
# ---------------------------------------------------------------------------

import os
import zipfile
import logging

logger = logging.getLogger(__name__)


def extract_iar(iar_path: str, workspace_dir: str) -> dict:
    """
    Extracts a .iar.zip file into the workspace directory.

    Args:
        iar_path     : path to the .iar.zip file (relative to project root)
        workspace_dir: path to the workspace directory

    Returns:
        dict with keys:
            - extract_path : folder where the IAR was extracted
            - project_xml  : full path to project.xml inside extracted folder
            - success      : True/False
            - error        : error message if success is False
    """
    result = {
        "extract_path": None,
        "project_xml": None,
        "success": False,
        "error": None
    }

    # Validate input file exists
    if not os.path.exists(iar_path):
        result["error"] = f"IAR file not found: {iar_path}"
        logger.error(result["error"])
        return result

    # Derive extraction folder name from IAR filename
    iar_filename = os.path.basename(iar_path)
    folder_name = iar_filename.replace(".iar.zip", "").replace(".iar", "").replace(".zip", "")
    extract_path = os.path.join(workspace_dir, folder_name)

    logger.info(f"Extracting: {iar_path} → {extract_path}")

    try:
        os.makedirs(extract_path, exist_ok=True)

        with zipfile.ZipFile(iar_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

        logger.info(f"Extraction complete: {extract_path}")

    except zipfile.BadZipFile as e:
        result["error"] = f"Invalid zip file: {iar_path} | {str(e)}"
        logger.error(result["error"])
        return result

    except Exception as e:
        result["error"] = f"Extraction failed: {str(e)}"
        logger.error(result["error"])
        return result

    # Locate project.xml inside the extracted folder
    project_xml_path = find_project_xml(extract_path)

    if not project_xml_path:
        result["error"] = f"project.xml not found inside: {extract_path}"
        logger.error(result["error"])
        return result

    logger.info(f"Found project.xml: {project_xml_path}")

    result["extract_path"] = extract_path
    result["project_xml"] = project_xml_path
    result["success"] = True

    return result


def find_project_xml(root_dir: str) -> str | None:
    """
    Recursively searches for project.xml inside the extracted IAR folder.

    Args:
        root_dir: root of the extracted IAR

    Returns:
        Full path to project.xml, or None if not found
    """
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename == "project.xml":
                return os.path.join(dirpath, filename)

    return None
