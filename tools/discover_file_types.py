# tools/discover_file_types.py
# Run from project root: python tools/discover_file_types.py
#
# Extracts all known pairs and lists every unique file type
# found under processor_* directories across all workspaces.

import os
import sys
import json
from collections import defaultdict

project_root = os.path.abspath(os.path.dirname(__file__) + "/..")
sys.path.insert(0, os.path.join(project_root, "src"))

from extractor import extract_iar
from iar_compare import KNOWN_PAIRS

WORKSPACE = os.path.join(project_root, "workspace")

def get_resources_dir(extract_path):
    for root, dirs, files in os.walk(extract_path):
        if os.path.basename(root) == "resources":
            children = os.listdir(root)
            if any(c.startswith("processor_") or c.startswith("application_") for c in children):
                return root
    return None

def classify(fname):
    if fname.endswith("stateinfo.json"):   return "NOISE"
    if fname.endswith("_stateinfo.xml"):   return "NOISE"
    if fname == "expr.properties":         return "SIGNAL"
    if fname.endswith(".xsl"):             return "SIGNAL"
    if fname.startswith("notification_"):  return "SIGNAL"
    if fname == "stitch.json":             return "SIGNAL"
    return "UNKNOWN"

# {filename: {"pairs": set(), "classification": str}}
seen = defaultdict(lambda: {"pairs": set(), "classification": "UNKNOWN"})

for label, (src_rel, tgt_rel) in sorted(KNOWN_PAIRS.items()):
    print(f"\nProcessing pair {label}...")
    for rel_path in (src_rel, tgt_rel):
        full_path = os.path.join(project_root, rel_path)
        result = extract_iar(full_path, WORKSPACE)
        if not result["success"]:
            print(f"  SKIP (extraction failed): {rel_path}")
            continue
        res_dir = get_resources_dir(result["extract_path"])
        if not res_dir:
            print(f"  SKIP (no resources dir): {result['extract_path']}")
            continue
        for proc in os.listdir(res_dir):
            if not proc.startswith("processor_"):
                continue
            for root, dirs, files in os.walk(os.path.join(res_dir, proc)):
                for fname in files:
                    entry = seen[fname]
                    entry["pairs"].add(label)
                    entry["classification"] = classify(fname)

print("\n\n=== UNIQUE FILE NAMES ACROSS ALL PAIRS ===")
print(f"{'FILE':<55} {'CLASS':<8} {'PAIRS'}")
print("-" * 90)

by_class = defaultdict(list)
for fname, info in sorted(seen.items()):
    by_class[info["classification"]].append((fname, info["pairs"]))

for cls in ("SIGNAL", "NOISE", "UNKNOWN"):
    for fname, pairs in sorted(by_class[cls]):
        print(f"{fname:<55} {cls:<8} {', '.join(sorted(pairs))}")