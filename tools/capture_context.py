# ---------------------------------------------------------------------------
# oic-lens | tools/capture_context.py
#
# Generates a self-contained window handoff package at the end of each
# milestone. The output is a single markdown file that contains everything
# a new Claude window needs — no file hunting, no missing context.
#
# Usage:
#   python tools/capture_context.py --milestone M2
#   python tools/capture_context.py --milestone M2 --label 32-33
#
# Output:
#   output/context_{MILESTONE}.md
#
# The package contains:
#   1. Milestone summary — pipeline step, what was built, API snapshots
#   2. Design decisions log
#   3. Validation results against ground truth (automated)
#   4. Public API of every source file
#   5. Current delta.json schema (live sample)
#   6. Full content of oic_resource_file_reference.md
#   7. Handoff block — open questions + exact next action (manual)
#
# The master plan itself is NOT embedded here — paste it separately at the
# start of the next window. This file SUPPLEMENTS the master plan.
# ---------------------------------------------------------------------------

import os
import sys
import json
import ast
import argparse
import subprocess
from datetime import datetime, timezone

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(project_root, "src"))

OUTPUT_DIR   = os.path.join(project_root, "output")
SRC_DIR      = os.path.join(project_root, "src")
TESTS_DIR    = os.path.join(project_root, "tests")
TOOLS_DIR    = os.path.join(project_root, "tools")
RESOURCE_REF = os.path.join(project_root, "docs", "oic_resource_file_reference.md")

# ---------------------------------------------------------------------------
# Milestone metadata
# pipeline_step: which of the 3 pipeline steps this milestone belongs to
# Update status + validation_checks as milestones complete.
# ---------------------------------------------------------------------------

MILESTONE_META = {
    "M0": {
        "title":          "Project Bootstrap",
        "pipeline_step":  "Pre-pipeline scaffolding",
        "status":         "DONE",
        "files_built":    ["src/extractor.py", "src/file_reader.py", "run_batch.py",
                           "config.py", "requirements.txt"],
        "files_modified": [],
        "test_file":      None,
        "next_milestone": "M1",
    },
    "M1": {
        "title":          "Structural Delta — New + Removed Steps",
        "pipeline_step":  "Step 1: Extract and Diff",
        "status":         "DONE",
        "files_built":    ["src/flow_compare.py", "src/iar_compare.py",
                           "tests/test_m1_structural_delta.py"],
        "files_modified": [],
        "test_file":      "tests/test_m1_structural_delta.py",
        "next_milestone": "M2",
    },
    "M2": {
        "title":          "Modified Steps Detection",
        "pipeline_step":  "Step 1: Extract and Diff",
        "status":         "IN PROGRESS",
        "files_built":    ["src/file_diff.py", "tests/test_m2_modified_steps.py"],
        "files_modified": ["src/flow_compare.py", "src/iar_compare.py"],
        "test_file":      "tests/test_m2_modified_steps.py",
        "next_milestone": "M3",
    },
    "M3": {
        "title":          "Flow Understander",
        "pipeline_step":  "Step 1: Extract and Diff",
        "status":         "DONE",
        "files_built":    ["src/flow_understander.py",
                           "tests/test_m3_flow_understander.py"],
        "files_modified": [],
        "test_file":      "tests/test_m3_flow_understander.py",
        "next_milestone": "M4",
    },
    "M4": {
        "title":          "Agent Investigation",
        "pipeline_step":  "Step 2: Agent Investigation",
        "status":         "DONE",
        "files_built":    ["src/agent_state.py", "src/agent_prompts.py",
                           "src/agent.py", "tests/test_m4_agent.py"],
        "files_modified": [],
        "test_file":      "tests/test_m4_agent.py",
        "next_milestone": "M5",
    },
    "M5": {
        "title":          "Report Generator",
        "pipeline_step":  "Step 3: Report Generation",
        "status":         "IN PROGRESS",
        "files_built":    ["src/report_generator.py",
                           "tests/test_m5_report.py"],
        "files_modified": [],
        "test_file":      "tests/test_m5_report.py",
        "next_milestone": "M6",
    },
    "M6": {
        "title":          "End-to-End Integration Test",
        "pipeline_step":  "Cross-cutting",
        "status":         "PENDING",
        "files_built":    [],
        "files_modified": ["run_batch.py"],
        "test_file":      None,
        "next_milestone": "M7",
    },
    "M7": {
        "title":          "Hardening",
        "pipeline_step":  "Cross-cutting",
        "status":         "PENDING",
        "files_built":    [],
        "files_modified": [],
        "test_file":      None,
        "next_milestone": "M8",
    },
    "M8": {
        "title":          "Security Review",
        "pipeline_step":  "Cross-cutting",
        "status":         "PENDING",
        "files_built":    [],
        "files_modified": [],
        "test_file":      None,
        "next_milestone": None,
    },
}

# ---------------------------------------------------------------------------
# API extraction — reads Python source and extracts public function signatures
# ---------------------------------------------------------------------------

def extract_public_api(filepath: str) -> list:
    """
    Parse a Python file and return list of public function/class signatures
    with their docstrings (first line only).
    """
    if not os.path.isfile(filepath):
        return []

    try:
        source = open(filepath, encoding="utf-8").read()
        tree   = ast.parse(source)
    except (SyntaxError, OSError):
        return []

    results = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        # Skip private
        if node.name.startswith("_"):
            continue
        # Build signature
        if isinstance(node, ast.ClassDef):
            sig = f"class {node.name}"
        else:
            try:
                args = _format_args(node.args)
                returns = ""
                if node.returns:
                    returns = f" -> {ast.unparse(node.returns)}"
                sig = f"def {node.name}({args}){returns}"
            except Exception:
                sig = f"def {node.name}(...)"

        # First line of docstring
        doc = ""
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            doc = str(node.body[0].value.value).strip().split("\n")[0]

        results.append({"sig": sig, "doc": doc})

    return results


def _format_args(args) -> str:
    parts = []
    # positional args
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        part = arg.arg
        if arg.annotation:
            try:
                part += f": {ast.unparse(arg.annotation)}"
            except Exception:
                pass
        di = i - defaults_offset
        if di >= 0:
            try:
                part += f" = {ast.unparse(args.defaults[di])}"
            except Exception:
                pass
        parts.append(part)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Validation runner
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Ground truth per validation pair
# Verified by direct inspection of extracted workspace files.
# ---------------------------------------------------------------------------

# Random pair assigned per milestone — deterministic, different per milestone
MILESTONE_RANDOM_PAIR = {
    "M0": "34-35",
    "M1": "41-42",
    "M2": "47-48",
    "M3": "45-46",
    "M4": "51-52",
    "M5": "53-54",
    "M6": "36-37",
    "M7": "39-40",
    "M8": "34-35",
}

# Structural ground truth — verified from delta.json output
GROUND_TRUTH_STRUCTURAL = {
    "32-33": {
        "source_count":   71,
        "target_count":   79,
        "new_count":      8,
        "removed_count":  0,
        "new_ids": {
            "processor_11623", "processor_11630", "processor_11643",
            "processor_11649", "processor_11655", "processor_11739",
            "processor_11974", "processor_12068",
        },
        "removed_ids": set(),
    },
    "49-50": {
        "source_count":   81,
        "target_count":   81,
        "new_count":      0,
        "removed_count":  0,
        "new_ids":        set(),
        "removed_ids":    set(),
    },
    "55-56": {
        "source_count":   35,
        "target_count":   42,
        "new_count":      15,
        "removed_count":  8,
        "new_ids": {
            "processor_59",   "processor_74",   "processor_284",
            "processor_1300", "processor_1315", "processor_1340",
            "processor_1345", "processor_1384", "processor_1397",
            "processor_1412", "processor_1417", "processor_1458",
            "processor_1561", "processor_1566", "processor_1826",
        },
        "removed_ids": {
            "processor_2036", "processor_2049", "processor_2066",
            "processor_2090", "processor_2097", "processor_2157",
            "processor_2180", "processor_2272",
        },
    },
}

# Modified steps ground truth — verified by direct file inspection
# key: (pair, processor_id) -> what to assert
GROUND_TRUTH_MODIFIED = {
    "32-33": {
        "must_contain": ["processor_964"],
        "processor_964": {
            "changed_file_key": "output_966/expr.properties",
            "old_must_contain": "Awaiting Shipping",
            "old_must_not_contain": "varCount",
            "new_must_contain": "varCount",
        },
    },
    "49-50": {
        "must_contain": ["processor_1216", "processor_5418"],
        "processor_1216": {
            "changed_file_key": "notification_body.data",
            "old_must_contain": "Contact",
            "new_must_contain": "Phone Number",
        },
        "processor_5418": {
            "changed_file_key": None,   # XSL — key varies by hash
            "file_type":        ".xsl",
            "old_must_contain":  None,  # content verified structurally
            "new_must_contain":  None,
        },
    },
    "55-56": {
        "must_contain": [
            "processor_1221", "processor_1036", "processor_1159",
            "processor_386",  "processor_110",  "processor_1240",
            "processor_1293", "processor_542",  "processor_653",
            "processor_8",
        ],
        "processor_1221": {
            "changed_file_key": "output_1223/expr.properties",
            "old_must_contain": "Else",
            "new_must_contain": "count(File) > 0",
        },
        "processor_1036": {
            "changed_file_key": "notification_body.data",
            "old_must_contain": "OIC Instance Id",
            "new_must_contain": "File Name",
        },
        "processor_1159": {
            "changed_file_key": "notification_body.data",
            "old_must_contain": "OIC Instance Id",
            "new_must_contain": "Source Location",
        },
        "processor_386": {
            "changed_file_key": "notification_body.data",
            "old_must_contain": "OIC Instance Id",
            "new_must_contain": "File Name",
        },
    },
}


def run_validation(milestone: str, label: str) -> list:
    """
    Run automated validation checks for the given milestone.
    Always validates primary pair (32-33), 49-50, 55-56, and the
    milestone-specific random pair.
    The label arg is used as context label in the output header only.
    """
    results = []
    meta = MILESTONE_META.get(milestone, {})

    # Determine which pairs to validate
    random_pair  = MILESTONE_RANDOM_PAIR.get(milestone, "41-42")
    pairs_to_run = ["32-33", "49-50", "55-56", random_pair]
    # deduplicate while preserving order
    seen = set()
    validation_pairs = [p for p in pairs_to_run if not (p in seen or seen.add(p))]

    results.append({
        "check":  f"Validation pairs",
        "pass":   True,
        "detail": f"Running against: {validation_pairs}  (random for {milestone}: {random_pair})",
    })

    # ── Run test file once (uses primary pair) ───────────────────────────────
    test_file = meta.get("test_file")
    if test_file:
        test_path = os.path.join(project_root, test_file)
        if os.path.isfile(test_path):
            try:
                proc = subprocess.run(
                    [sys.executable, test_path, "32-33"],
                    capture_output=True, text=True, timeout=60,
                    cwd=project_root,
                )
                passed = proc.returncode == 0
                results.append({
                    "check":  f"Test suite: {test_file} (32-33)",
                    "pass":   passed,
                    "detail": (proc.stdout + proc.stderr).strip()[-500:],
                })
            except Exception as e:
                results.append({"check": f"Test suite: {test_file}",
                                 "pass": False, "detail": str(e)})
        else:
            results.append({"check": f"Test suite: {test_file}",
                             "pass": False, "detail": "FILE NOT FOUND"})

    # ── Per-pair checks ──────────────────────────────────────────────────────
    for pair in validation_pairs:
        delta_path   = os.path.join(OUTPUT_DIR, f"{pair}_delta.json")
        context_path = os.path.join(OUTPUT_DIR, f"{pair}_flow_context.json")
        report_path  = os.path.join(OUTPUT_DIR, f"{pair}_report.json")
        # change_report.md filename includes integration name + versions
        # e.g. ALTERA_CREATE_SO_INTEGRAT_01.00.0032_to_01.00.0033_change_report.md
        # Fall back to pair_change_report.md for simpler naming
        import glob as _glob
        _md_candidates = (
            _glob.glob(os.path.join(OUTPUT_DIR, f"*{pair}*change_report.md")) +
            _glob.glob(os.path.join(OUTPUT_DIR, "*change_report.md"))
        )
        md_path = _md_candidates[0] if _md_candidates else os.path.join(OUTPUT_DIR, f"{pair}_change_report.md")

        delta   = _load_json(delta_path)
        context = _load_json(context_path)
        report  = _load_json(report_path)
        md_text = _load_text(md_path)

        gt_struct   = GROUND_TRUTH_STRUCTURAL.get(pair)
        gt_modified = GROUND_TRUTH_MODIFIED.get(pair)

        prefix = f"[{pair}]"

        # ── M1 structural checks ─────────────────────────────────────────────
        if milestone in ("M1", "M2", "M3"):
            if not delta:
                results.append({"check": f"{prefix} Step 1 | delta.json exists",
                                 "pass": False, "detail": f"not found: {delta_path}"})
                continue

            if gt_struct:
                new_ids     = {p["processor_id"] for p in delta.get("new_steps", [])}
                removed_ids = {p["processor_id"] for p in delta.get("removed_steps", [])}

                results.append({
                    "check":  f"{prefix} Step 1 | source_count == {gt_struct['source_count']}",
                    "pass":   delta.get("source_count") == gt_struct["source_count"],
                    "detail": f"got {delta.get('source_count')}",
                })
                results.append({
                    "check":  f"{prefix} Step 1 | target_count == {gt_struct['target_count']}",
                    "pass":   delta.get("target_count") == gt_struct["target_count"],
                    "detail": f"got {delta.get('target_count')}",
                })
                results.append({
                    "check":  f"{prefix} Step 1 | new_steps count == {gt_struct['new_count']}",
                    "pass":   len(new_ids) == gt_struct["new_count"],
                    "detail": f"got {len(new_ids)}",
                })
                results.append({
                    "check":  f"{prefix} Step 1 | removed_steps count == {gt_struct['removed_count']}",
                    "pass":   len(removed_ids) == gt_struct["removed_count"],
                    "detail": f"got {len(removed_ids)}",
                })
                if gt_struct["new_ids"]:
                    results.append({
                        "check":  f"{prefix} Step 1 | new processor IDs correct",
                        "pass":   new_ids == gt_struct["new_ids"],
                        "detail": f"missing={gt_struct['new_ids']-new_ids} extra={new_ids-gt_struct['new_ids']}",
                    })
                if gt_struct["removed_ids"]:
                    results.append({
                        "check":  f"{prefix} Step 1 | removed processor IDs correct",
                        "pass":   removed_ids == gt_struct["removed_ids"],
                        "detail": f"missing={gt_struct['removed_ids']-removed_ids} extra={removed_ids-gt_struct['removed_ids']}",
                    })
            else:
                # Random pair — structural sanity only
                results.append({
                    "check":  f"{prefix} Step 1 | delta.json is well-formed",
                    "pass":   all(k in delta for k in
                                  ["new_steps","removed_steps","modified_steps",
                                   "source_count","target_count"]),
                    "detail": f"keys: {list(delta.keys())}",
                })

        # ── M2 modified steps checks ─────────────────────────────────────────
        if milestone in ("M2", "M3"):
            modified     = delta.get("modified_steps", [])
            mod_ids      = [p["processor_id"] for p in modified]

            # Noise false positive checks — apply to ALL pairs
            stateinfo_json_hits = [
                p["processor_id"] for p in modified
                if any(cf.get("key","").endswith("stateinfo.json")
                       for cf in p.get("changed_files", []))
            ]
            stateinfo_xml_hits = [
                p["processor_id"] for p in modified
                if any(cf.get("key","").endswith("_stateinfo.xml")
                       for cf in p.get("changed_files", []))
            ]
            results.append({
                "check":  f"{prefix} Step 1 | No *stateinfo.json false positives",
                "pass":   len(stateinfo_json_hits) == 0,
                "detail": f"hits: {stateinfo_json_hits}",
            })
            results.append({
                "check":  f"{prefix} Step 1 | No *_stateinfo.xml false positives",
                "pass":   len(stateinfo_xml_hits) == 0,
                "detail": f"hits: {stateinfo_xml_hits}",
            })

            if gt_modified:
                # Must-contain processor IDs
                must_ids = gt_modified.get("must_contain", [])
                for pid in must_ids:
                    results.append({
                        "check":  f"{prefix} Step 1 | {pid} in modified_steps",
                        "pass":   pid in mod_ids,
                        "detail": f"modified_steps: {mod_ids}",
                    })

                # Per-processor content checks
                for pid, checks in gt_modified.items():
                    if pid == "must_contain" or not isinstance(checks, dict):
                        continue
                    proc = next((p for p in modified
                                 if p["processor_id"] == pid), None)
                    if not proc:
                        continue

                    key = checks.get("changed_file_key")
                    ftype = checks.get("file_type")
                    cf = None

                    if key:
                        cf = next((f for f in proc.get("changed_files", [])
                                   if f.get("key") == key), None)
                    elif ftype:
                        cf = next((f for f in proc.get("changed_files", [])
                                   if f.get("key","").endswith(ftype)), None)

                    if cf:
                        old_c = cf.get("old_content", "")
                        new_c = cf.get("new_content", "")
                        if checks.get("old_must_contain"):
                            results.append({
                                "check":  f"{prefix} Step 1 | {pid} old content correct",
                                "pass":   checks["old_must_contain"] in old_c,
                                "detail": f"looking for {checks['old_must_contain']!r} in old",
                            })
                        if checks.get("old_must_not_contain"):
                            results.append({
                                "check":  f"{prefix} Step 1 | {pid} old content no false content",
                                "pass":   checks["old_must_not_contain"] not in old_c,
                                "detail": f"should not contain {checks['old_must_not_contain']!r}",
                            })
                        if checks.get("new_must_contain"):
                            results.append({
                                "check":  f"{prefix} Step 1 | {pid} new content correct",
                                "pass":   checks["new_must_contain"] in new_c,
                                "detail": f"looking for {checks['new_must_contain']!r} in new",
                            })
            else:
                # Random pair — sanity only
                results.append({
                    "check":  f"{prefix} Step 1 | modified_steps is a list",
                    "pass":   isinstance(delta.get("modified_steps"), list),
                    "detail": f"type: {type(delta.get('modified_steps')).__name__}",
                })

        # ── M3 flow context checks ───────────────────────────────────────────
        if milestone == "M3":
            ctx_text = json.dumps(context).lower() if context else ""
            results.append({
                "check":  f"{prefix} Step 1 | flow_context.json exists",
                "pass":   bool(context),
                "detail": f"path: {context_path}",
            })
            if context:
                results.append({
                    "check":  f"{prefix} Step 1 | flow_context mentions modified steps",
                    "pass":   "modified" in ctx_text,
                    "detail": "'modified' in flow_context",
                })

        # ── M4 agent report checks ───────────────────────────────────────────
        if milestone == "M4":
            rpt_text = json.dumps(report).lower() if report else ""
            results.append({
                "check":  f"{prefix} Step 2 | report.json exists",
                "pass":   bool(report),
                "detail": f"path: {report_path}",
            })
            if report:
                results.append({
                    "check":  f"{prefix} Step 2 | report.json has modified_steps section",
                    "pass":   "modified_steps" in rpt_text,
                    "detail": "'modified_steps' in report",
                })
                results.append({
                    "check":  f"{prefix} Step 2 | risk level present",
                    "pass":   any(w in rpt_text for w in ["medium","high","critical"]),
                    "detail": f"risk words: {[w for w in ['medium','high','critical'] if w in rpt_text]}",
                })

        # ── M5 report generation checks ──────────────────────────────────────
        if milestone == "M5":
            md_lower = md_text.lower() if md_text else ""
            results.append({
                "check":  f"{prefix} Step 3 | change_report.md exists",
                "pass":   bool(md_text),
                "detail": f"path: {md_path}",
            })
            if md_text:
                results.append({
                    "check":  f"{prefix} Step 3 | has Modified Steps section",
                    "pass":   "modified steps" in md_lower,
                    "detail": "'modified steps' in report",
                })
                results.append({
                    "check":  f"{prefix} Step 3 | has Architect Review Checklist",
                    "pass":   "architect" in md_lower and "checklist" in md_lower,
                    "detail": "'architect' and 'checklist' in report",
                })
                # processor_964 canonical checks (32-33 only)
                if pair == "32-33":
                    results.append({
                        "check":  f"{prefix} Step 3 | processor_964 in Modified Steps",
                        "pass":   "router_964" in md_lower or "processor_964" in md_lower,
                        "detail": "processor_964 or Router_964 in report",
                    })
                    results.append({
                        "check":  f"{prefix} Step 3 | varCount in Modified Steps",
                        "pass":   "varcount" in md_lower,
                        "detail": "varCount in report",
                    })
                    results.append({
                        "check":  f"{prefix} Step 3 | processor_964 in checklist",
                        "pass":   ("router_964" in md_lower or "processor_964" in md_lower)
                                  and ("checklist" in md_lower or "- [ ]" in md_text),
                        "detail": "processor_964 + checklist items present",
                    })
                    results.append({
                        "check":  f"{prefix} Step 3 | navigation path present",
                        "pass":   "navigate" in md_lower or "processor_964" in md_lower,
                        "detail": "navigation hint in report",
                    })

        # ── M6 end-to-end checks ─────────────────────────────────────────────
        if milestone == "M6":
            for path in [delta_path, context_path, report_path, md_path]:
                results.append({
                    "check":  f"{prefix} M6 | {os.path.basename(path)} exists",
                    "pass":   os.path.isfile(path),
                    "detail": path,
                })

    # ── M7 hardening ─────────────────────────────────────────────────────────
    if milestone == "M7":
        try:
            dry = subprocess.run(
                [sys.executable,
                 os.path.join(project_root, "src", "iar_compare.py"),
                 "32-33", "--dry-run"],
                capture_output=True, text=True, timeout=30, cwd=project_root,
            )
            results.append({
                "check":  "M7 | --dry-run flag works",
                "pass":   dry.returncode == 0,
                "detail": dry.stdout.strip()[-200:],
            })
        except Exception as e:
            results.append({"check": "M7 | --dry-run flag works",
                             "pass": False, "detail": str(e)})

    return results


def _load_json(path: str) -> dict:
    """Load JSON file, return empty dict if missing or invalid."""
    if not os.path.isfile(path):
        return {}
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def _load_text(path: str) -> str:
    """Load text file, return empty string if missing."""
    if not os.path.isfile(path):
        return ""
    try:
        return open(path, encoding="utf-8").read()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Delta schema snapshot
# ---------------------------------------------------------------------------

def delta_schema_snapshot(label: str) -> str:
    delta_path = os.path.join(OUTPUT_DIR, f"{label}_delta.json")
    if not os.path.isfile(delta_path):
        return "_Delta file not found — run iar_compare.py first._"

    try:
        delta = json.load(open(delta_path))
    except Exception as e:
        return f"_Could not read delta: {e}_"

    lines = []
    lines.append(f"**Label:** {delta.get('label')}")
    lines.append(f"**Versions:** v{delta.get('source_version')} → v{delta.get('target_version')}")
    lines.append(f"**Processors:** {delta.get('source_count')} → {delta.get('target_count')}")
    lines.append(f"**New steps:** {len(delta.get('new_steps', []))}")
    lines.append(f"**Removed steps:** {len(delta.get('removed_steps', []))}")
    lines.append(f"**Modified steps:** {len(delta.get('modified_steps', []))}")
    lines.append(f"**Top-level keys:** {list(delta.keys())}")

    if delta.get("new_steps"):
        lines.append("\n**new_steps[0] shape:**")
        lines.append("```json")
        lines.append(json.dumps(delta["new_steps"][0], indent=2))
        lines.append("```")

    if delta.get("modified_steps"):
        lines.append("\n**modified_steps[0] shape:**")
        lines.append("```json")
        ms = delta["modified_steps"][0]
        preview = dict(ms)
        if preview.get("changed_files"):
            cf = preview["changed_files"][0]
            preview["changed_files"] = [{
                "key": cf.get("key"),
                "old_content": cf.get("old_content","")[:80] + "...",
                "new_content": cf.get("new_content","")[:80] + "...",
            }]
        lines.append(json.dumps(preview, indent=2))
        lines.append("```")
    else:
        lines.append("\n_modified_steps is empty — M2 not yet complete._")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main document builder
# ---------------------------------------------------------------------------

def build_handoff(milestone: str, label: str) -> str:
    meta      = MILESTONE_META.get(milestone, {})
    now       = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections  = []

    # ── Header ──────────────────────────────────────────────────────────────
    sections.append(f"""# oic-lens — Window Handoff Package
**Milestone:** {milestone} — {meta.get('title','?')}
**Pipeline step:** {meta.get('pipeline_step','?')}
**Status:** {meta.get('status','?')}
**Generated:** {now}
**Validation pair:** {label}

> Paste this file into the next Claude window AFTER the master plan.
> It supplements the master plan — it does not replace it.

---
""")

    # ── Files built / modified ───────────────────────────────────────────────
    sections.append("## Files Built or Modified This Milestone\n")
    for f in meta.get("files_built", []):
        path = os.path.join(project_root, f)
        exists = "✅" if os.path.isfile(path) else "❌ MISSING"
        sections.append(f"- **{f}** (new) {exists}")
    for f in meta.get("files_modified", []):
        path = os.path.join(project_root, f)
        exists = "✅" if os.path.isfile(path) else "❌ MISSING"
        sections.append(f"- **{f}** (modified) {exists}")
    sections.append("")

    # ── Public API snapshot ──────────────────────────────────────────────────
    sections.append("## Public API Snapshot\n")
    all_src_files = sorted([
        f for f in os.listdir(SRC_DIR) if f.endswith(".py")
    ])
    for fname in all_src_files:
        fpath = os.path.join(SRC_DIR, fname)
        api   = extract_public_api(fpath)
        if not api:
            continue
        sections.append(f"### `src/{fname}`")
        for item in api:
            line = f"- `{item['sig']}`"
            if item["doc"]:
                line += f" — {item['doc']}"
            sections.append(line)
        sections.append("")

    # ── Delta schema snapshot ────────────────────────────────────────────────
    sections.append("## Delta JSON Schema (live sample)\n")
    sections.append(delta_schema_snapshot(label))
    sections.append("")

    # ── Validation results ───────────────────────────────────────────────────
    sections.append("## Validation Results\n")
    results = run_validation(milestone, label)
    if results:
        for r in results:
            icon   = "✅" if r["pass"] else "❌"
            detail = f" `{r['detail']}`" if r.get("detail") else ""
            sections.append(f"- {icon} {r['check']}{detail}")
    else:
        sections.append("_No validation checks defined for this milestone._")
    sections.append("")

    # ── Design decisions log ─────────────────────────────────────────────────
    sections.append("## Design Decisions Log\n")
    sections.append("""\
### Session: March 2026 — Source Tree Analysis

**LLM as architect, not whitelist**
The tool does not pre-filter what the LLM sees. The LLM receives an inventory
map upfront and requests file contents on demand. Only files with provably
zero semantic value are excluded.

**Exclude DVM lookup files**
`lookups/*.dvm` — out of scope. Contains PII (email addresses).

**Defer *.wsdl, *.jca, *.xsd to security review milestone (M8)**
LLM-readable but not in M2-M7 scope. Requires dedicated milestone with
appropriate prompts.

**XSL hash filename — treat as modified not removed+added**
If source has one `req_*.xsl` and target has one `req_*.xsl` for the same
processor, treat as a single modification. OIC generates new hash on content
change — naive diff loses before/after context.

**stitch.json — JSON key-sort normalisation**
Sort keys before comparing. OIC reorders JSON keys with no semantic change.
Without this, produces false positives.

**Two path depth variants**
- Shallow: `processor_{ID}/resourcegroup_{RG}/{file}`
- Deep (router branches): `processor_{ID}/output_{OUT}/resourcegroup_{RG}/{file}`
Strip `resourcegroup_{ID}`, preserve `output_{ID}`.

**Exclusion rules**
```python
def is_excluded(filename):
    if filename.endswith("stateinfo.json"):   return True
    if filename.endswith("_stateinfo.xml"):   return True
    if filename.endswith(".dvm"):             return True
    if filename == "nxsdmetadata.properties": return True
    if filename == "oic_project.properties":  return True
    if filename == "project.yaml":            return True
    if filename.endswith(".zip"):             return True
    return False

def is_deferred(filename):
    if filename.endswith(".wsdl"):  return True
    if filename.endswith(".jca"):   return True
    if filename.endswith(".xsd"):   return True
    return False
```
""")

    # ── Resource file reference ───────────────────────────────────────────────
    sections.append("## OIC Resource File Type Reference\n")
    if os.path.isfile(RESOURCE_REF):
        sections.append(open(RESOURCE_REF, encoding="utf-8").read())
    else:
        sections.append(
            f"_WARNING: {RESOURCE_REF} not found. "
            f"Copy oic_resource_file_reference.md to project root._"
        )
    sections.append("")

    # ── Handoff block ────────────────────────────────────────────────────────
    sections.append("## Handoff Block\n")
    sections.append("### Milestone status by pipeline step\n")
    sections.append("| Milestone | Title | Pipeline Step | Status |")
    sections.append("|---|---|---|---|")
    for m, info in MILESTONE_META.items():
        icon = "✅" if info["status"] == "DONE" else ("🔄" if info["status"] == "IN PROGRESS" else "⬜")
        sections.append(f"| {icon} {m} | {info['title']} | {info['pipeline_step']} | {info['status']} |")
    sections.append(f"\n### Current milestone")
    sections.append(f"**{milestone} — {meta.get('title')} ({meta.get('pipeline_step')}) — {meta.get('status')}**\n")
    next_m = meta.get("next_milestone")
    if next_m and next_m in MILESTONE_META:
        next_info = MILESTONE_META[next_m]
        sections.append(f"**Next milestone:** {next_m} — {next_info['title']} ({next_info['pipeline_step']})\n")
    sections.append("### Open questions")
    sections.append("_Update this section manually before saving._\n")
    sections.append("### Exact next action")
    sections.append("_Update this section manually before saving._\n")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a self-contained window handoff package.",
        epilog=(
            "Examples:\n"
            "  python tools/capture_context.py --milestone M2\n"
            "  python tools/capture_context.py --milestone M1\n"
            "\n"
            "Validation always runs against: 32-33, 49-50, 55-56,\n"
            "and the milestone-specific random pair.\n"
            "The --label arg is used only in the output header.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--milestone", required=True,
        choices=list(MILESTONE_META.keys()),
        help="Milestone to capture context for",
    )
    parser.add_argument(
        "--label", default="32-33",
        help="Label shown in output header (default: 32-33)",
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    content = build_handoff(args.milestone, args.label)

    out_path = os.path.join(OUTPUT_DIR, f"context_{args.milestone}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Handoff package written: {out_path}")
    print(f"Review it, update Open Questions and Exact Next Action, then save.")
