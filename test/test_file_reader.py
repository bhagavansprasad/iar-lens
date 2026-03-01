# ---------------------------------------------------------------------------
# iar-lens | test/test_file_reader.py
# Validates all three file_reader functions independently
# ---------------------------------------------------------------------------

import sys
import os
import json
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

from file_reader import read_file, list_processor_files, list_all_processor_files

SEP = "=" * 60

def test_read_file():
    """Test reading a single known file from the workspace."""
    print(f"\n{SEP}")
    print("TEST 1: read_file()")
    print(SEP)

    # Read the XSL mapper for a known new processor in v011
    test_path = (
        "workspace/INT303_INVENTOR_EI_RECONCIL_03.00.0011/"
        "icspackage/project/INT303_INVENTOR_EI_RECONCIL_03.00.0011/"
        "resources/processor_59/resourcegroup_62/"
        "req_f7e06ea9e3a14136be43885a90a9e922.xsl"
    )

    result = read_file(test_path)

    print(f"Success    : {result['success']}")
    print(f"File name  : {result['file_name']}")
    print(f"File type  : {result['file_type']}")
    print(f"File role  : {result['file_role']}")
    print(f"Size bytes : {result['size_bytes']}")
    print(f"Line count : {result['line_count']}")
    print(f"Content preview (first 200 chars):")
    if result["content"]:
        print(result["content"][:200])
    else:
        print(f"  ERROR: {result['error']}")


def test_list_processor_files():
    """Test listing all files for a specific processor."""
    print(f"\n{SEP}")
    print("TEST 2: list_processor_files()")
    print(SEP)

    # Test with the new DHL ForEach processor
    result = list_processor_files("processor_1345", version="03.00.0011")

    print(f"Success      : {result['success']}")
    print(f"Processor ID : {result['processor_id']}")
    print(f"Version      : {result['version']}")
    print(f"File count   : {result['file_count']}")

    if result["success"]:
        print("Files found:")
        for f in result["files"]:
            print(f"  [{f['file_type']:10}] {f['file_name']:50} ({f['size_bytes']} bytes)")
            print(f"             Role: {f['file_role']}")
    else:
        print(f"ERROR: {result['error']}")


def test_list_all_processor_files():
    """Test listing all processors and files for a version."""
    print(f"\n{SEP}")
    print("TEST 3: list_all_processor_files()")
    print(SEP)

    result = list_all_processor_files("03.00.0011")

    print(f"Success       : {result['success']}")
    print(f"Version       : {result['version']}")
    print(f"Total files   : {result['total_files']}")
    print(f"Processor count: {len(result['processors'])}")

    if result["success"]:
        print("\nProcessor summary:")
        for proc_id, files in sorted(result["processors"].items(),
                                      key=lambda x: int(x[0].replace("processor_", ""))):
            file_types = [f["file_type"] for f in files]
            print(f"  {proc_id:20} → {len(files)} file(s): {file_types}")
    else:
        print(f"ERROR: {result['error']}")


def test_read_file_not_found():
    """Test error handling for missing file."""
    print(f"\n{SEP}")
    print("TEST 4: read_file() — file not found")
    print(SEP)

    result = read_file("workspace/nonexistent/file.xsl")
    print(f"Success : {result['success']}")
    print(f"Error   : {result['error']}")


if __name__ == "__main__":
    test_read_file()
    test_list_processor_files()
    test_list_all_processor_files()
    test_read_file_not_found()

    print(f"\n{SEP}")
    print("All tests complete")
    print(SEP)
