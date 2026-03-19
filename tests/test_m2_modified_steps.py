# ---------------------------------------------------------------------------
# oic-lens | tests/test_m2_modified_steps.py
# Validates M2: modified steps detection (file-level content diff).
#
# Ground truth for 32-33 (from master plan):
#   - processor_964 (contentBasedRouter) is modified
#   - Old condition: Status = 'Awaiting Shipping'
#   - New condition: Status = 'Awaiting Shipping' OR varCount >= '11'
#   - No stateinfo false positives in modified_steps
#
# Run:
#   python tests/test_m2_modified_steps.py           # 32-33 only
#   python tests/test_m2_modified_steps.py 32-33
# ---------------------------------------------------------------------------

import os
import sys
import argparse
import logging

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from extractor    import extract_iar
from flow_compare import extract_steps, compute_delta
import file_diff as fd

logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s | %(message)s")

FLOW_DUMP = os.path.join(project_root, "flow-dump")
WORKSPACE = os.path.join(project_root, "workspace")

# ---------------------------------------------------------------------------
# Ground truth — 32-33 is the primary validation pair for M2
# ---------------------------------------------------------------------------

PAIRS = [
    {
        "label"              : "32-33",
        "src"                : "32-33/FACTORYDOCK-TEST-32.car",
        "tgt"                : "32-33/FACTORYDOCK-TEST-33.car",
        "src_version"        : "01.00.0032",
        "tgt_version"        : "01.00.0033",
        "src_count"          : 71,
        "tgt_count"          : 79,
        "new_count"          : 8,
        "removed_count"      : 0,
        # Processor that MUST be in modified_steps
        "must_contain_pid"   : "processor_964",
        "changed_file_key"   : "output_966/expr.properties",
        "old_condition_hint" : "Status = 'Awaiting Shipping'",
        "new_condition_hint" : "varCount >= '11'",
        "forbidden_key_hints": ["stateinfo"],
    },
    {
        "label"              : "49-50",
        "src"                : "49-50/FACTORYDOCK-TEST-49.car",
        "tgt"                : "49-50/FACTORYDOCK-TEST-50.car",
        "src_version"        : "01.00.0049",
        "tgt_version"        : "01.00.0050",
        "src_count"          : 81,
        "tgt_count"          : 81,
        "new_count"          : 0,
        "removed_count"      : 0,
        # Notification body HTML edit
        "must_contain_pid"   : "processor_1216",
        "changed_file_key"   : "notification_body.data",
        "old_condition_hint" : "<b>Contact:</b>",        # old label
        "new_condition_hint" : "<b>Phone Number:</b>",   # new label (renamed)
        "forbidden_key_hints": ["stateinfo"],
    },
    {
        "label"              : "55-56",
        "src"                : "55-56/INT03.00.0001.iar",
        "tgt"                : "55-56/INT03.00.0011.iar",
        "src_version"        : "03.00.0001",
        "tgt_version"        : "03.00.0011",
        "src_count"          : 35,
        "tgt_count"          : 42,
        "new_count"          : 15,
        "removed_count"      : 8,
        # 55-56 has large structural changes (15 new, 8 removed) and no known
        # modified processors — validate structural counts + no false positives
        "must_contain_pid"   : None,
        "changed_file_key"   : None,
        "old_condition_hint" : None,
        "new_condition_hint" : None,
        "forbidden_key_hints": ["stateinfo"],
    },
]

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_pair(pair: dict) -> list[dict]:
    """Run M2 checks for one pair. Returns list of {name, passed, detail}."""
    label = pair["label"]
    src_path = os.path.join(FLOW_DUMP, pair["src"])
    tgt_path = os.path.join(FLOW_DUMP, pair["tgt"])
    results: list[dict] = []

    def rec(name, passed, detail=""):
        results.append({"name": name, "passed": passed, "detail": detail})

    # --- Extraction ---
    src_ex = extract_iar(src_path, WORKSPACE)
    tgt_ex = extract_iar(tgt_path, WORKSPACE)

    if not src_ex["success"] or not tgt_ex["success"]:
        rec("Extraction", False, f"src={src_ex.get('error')} tgt={tgt_ex.get('error')}")
        return results

    # --- Parse ---
    src_data = extract_steps(src_ex["project_xml"])
    tgt_data = extract_steps(tgt_ex["project_xml"])

    if not src_data["success"] or not tgt_data["success"]:
        rec("Parse project.xml", False,
            f"src={src_data.get('error')} tgt={tgt_data.get('error')}")
        return results

    # --- Compute delta with M2 file diff ---
    delta = compute_delta(
        src_data, tgt_data,
        source_extract_path=src_ex["extract_path"],
        target_extract_path=tgt_ex["extract_path"],
    )

    modified = delta.get("modified_steps", [])
    modified_ids = {m["processor_id"] for m in modified}

    # --- Structural counts (M1 regression) ---
    rec(
        "Step 1 | source_count correct",
        src_data["processor_count"] == pair["src_count"],
        f"got {src_data['processor_count']}",
    )
    rec(
        "Step 1 | target_count correct",
        tgt_data["processor_count"] == pair["tgt_count"],
        f"got {tgt_data['processor_count']}",
    )
    rec(
        "Step 1 | new_steps count correct",
        len(delta["new_steps"]) == pair["new_count"],
        f"got {len(delta['new_steps'])}",
    )
    rec(
        "Step 1 | removed_steps count correct",
        len(delta["removed_steps"]) == pair["removed_count"],
        f"got {len(delta['removed_steps'])}",
    )

    # --- resources/ dirs found ---
    src_res = fd.find_resources_dir(src_ex["extract_path"])
    tgt_res = fd.find_resources_dir(tgt_ex["extract_path"])
    rec("Step 1 | source resources/ dir found", src_res is not None, str(src_res))
    rec("Step 1 | target resources/ dir found", tgt_res is not None, str(tgt_res))

    # --- No stateinfo false positives ---
    forbidden = pair.get("forbidden_key_hints", [])
    false_positives = []
    for m in modified:
        for cf in m["changed_files"]:
            for fh in forbidden:
                if fh in cf["key"]:
                    false_positives.append(f"{m['processor_id']}:{cf['key']}")
    rec(
        "Step 1 | no stateinfo false positives in modified_steps",
        len(false_positives) == 0,
        f"false positives={false_positives}" if false_positives else "",
    )

    # --- Processor-level checks (skipped when must_contain_pid is None) ---
    must_pid = pair.get("must_contain_pid")
    if must_pid is None:
        return results

    rec(
        f"Step 1 | {must_pid} in modified_steps",
        must_pid in modified_ids,
        f"modified_ids={sorted(modified_ids)}",
    )

    proc_entry = next((m for m in modified if m["processor_id"] == must_pid), None)
    if proc_entry:
        expected_key = pair["changed_file_key"]
        actual_keys = [cf["key"] for cf in proc_entry["changed_files"]]
        key_found = any(expected_key in k for k in actual_keys)
        rec(
            f"Step 1 | {must_pid} has changed file '{expected_key}'",
            key_found,
            f"actual keys={actual_keys}",
        )

        old_hint = pair["old_condition_hint"]
        old_ok = any(old_hint in cf.get("old_content", "") for cf in proc_entry["changed_files"])
        rec(
            f"Step 1 | {must_pid} old_content contains expected text",
            old_ok,
            _snippet(proc_entry["changed_files"], "old_content"),
        )

        new_hint = pair["new_condition_hint"]
        new_ok = any(new_hint in cf.get("new_content", "") for cf in proc_entry["changed_files"])
        rec(
            f"Step 1 | {must_pid} new_content contains expected text",
            new_ok,
            _snippet(proc_entry["changed_files"], "new_content"),
        )
    else:
        for label_hint in ("changed file", "old_content", "new_content"):
            rec(f"Step 1 | {must_pid} {label_hint}", False, f"{must_pid} not found in modified_steps")

    return results


def _snippet(changed_files: list, field: str, max_len: int = 120) -> str:
    """Return first non-empty content snippet for the given field."""
    for cf in changed_files:
        val = cf.get(field, "")
        if val:
            return repr(val[:max_len])
    return "(empty)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="M2 Test — Modified Steps Detection",
        epilog="python tests/test_m2_modified_steps.py 32-33",
    )
    parser.add_argument("labels", nargs="*", metavar="LABEL",
                        help="Pair label(s) to test. Default: 32-33")
    args = parser.parse_args()

    labels_requested = set(args.labels) if args.labels else {p["label"] for p in PAIRS}
    pairs_to_run = [p for p in PAIRS if p["label"] in labels_requested]

    if not pairs_to_run:
        print(f"No matching pairs for: {labels_requested}")
        print(f"Available: {[p['label'] for p in PAIRS]}")
        sys.exit(1)

    print()
    print("=" * 70)
    print("M2 TEST — Modified Steps Detection")
    print(f"Pairs: {len(pairs_to_run)}")
    print("=" * 70)

    total_pass = 0
    total_fail = 0

    for pair in pairs_to_run:
        label = pair["label"]
        print(f"\n  [{label}]")

        # Check CAR files exist
        src_path = os.path.join(FLOW_DUMP, pair["src"])
        tgt_path = os.path.join(FLOW_DUMP, pair["tgt"])
        if not os.path.exists(src_path) or not os.path.exists(tgt_path):
            print(f"    ⏭  SKIP — CAR/IAR files not found")
            print(f"           src: {src_path}")
            print(f"           tgt: {tgt_path}")
            continue

        results = run_pair(pair)

        for r in results:
            icon = "✅ PASS" if r["passed"] else "❌ FAIL"
            detail = f"  `{r['detail']}`" if r["detail"] else ""
            print(f"    {icon}  {r['name']}{detail}")
            if r["passed"]:
                total_pass += 1
            else:
                total_fail += 1

    print()
    print("=" * 70)
    print(f"RESULTS: {total_pass}/{total_pass + total_fail} passed  |  {total_fail} failed")
    print("=" * 70)
    print()

    if total_fail > 0:
        print("❌  M2 FAILED")
        sys.exit(1)
    else:
        print("✅  M2 PASSED — modified steps detection verified.")
        sys.exit(0)


if __name__ == "__main__":
    main()
