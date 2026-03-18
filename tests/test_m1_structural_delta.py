# ---------------------------------------------------------------------------
# oic-lens | tests/test_m1_structural_delta.py
# Validates M1: structural delta (new + removed steps).
# Ground truth discovered by running against actual CAR/IAR files.
#
# Run all pairs:
#   python tests/test_m1_structural_delta.py
#
# Run specific pairs by label:
#   python tests/test_m1_structural_delta.py 32-33
#   python tests/test_m1_structural_delta.py 32-33 49-50 55-56
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

logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s | %(message)s")

# ---------------------------------------------------------------------------
# Ground truth for every pair
# Fields: label, src_file, tgt_file,
#         src_version, tgt_version,
#         src_proc_count, tgt_proc_count,
#         new_ids (set of "processor_NNNN"),
#         removed_ids (set of "processor_NNNN")
# ---------------------------------------------------------------------------

FLOW_DUMP = os.path.join(project_root, "flow-dump")

PAIRS = [
    {
        "label"      : "32-33",
        "src"        : "32-33/FACTORYDOCK-TEST-32.car",
        "tgt"        : "32-33/FACTORYDOCK-TEST-33.car",
        "src_version": "01.00.0032",
        "tgt_version": "01.00.0033",
        "src_count"  : 71,
        "tgt_count"  : 79,
        "new_ids"    : {"processor_11623","processor_11630","processor_11643",
                        "processor_11649","processor_11655","processor_11739",
                        "processor_11974","processor_12068"},
        "removed_ids": set(),
    },
    {
        "label"      : "34-35",
        "src"        : "34-35/FACTORYDOCK-TEST-34.car",
        "tgt"        : "34-35/FACTORYDOCK-TEST-35.car",
        "src_version": "01.00.0034",
        "tgt_version": "01.00.0035",
        "src_count"  : 79,
        "tgt_count"  : 79,
        "new_ids"    : set(),
        "removed_ids": set(),
    },
    {
        "label"      : "36-37",
        "src"        : "36-37/FACTORYDOCK-TEST-36.car",
        "tgt"        : "36-37/FACTORYDOCK-TEST-37.car",
        "src_version": "01.00.0036",
        "tgt_version": "01.00.0038",
        "src_count"  : 79,
        "tgt_count"  : 80,
        "new_ids"    : {"processor_12869"},
        "removed_ids": set(),
    },
    {
        "label"      : "39-40",
        "src"        : "39-40/FACTORYDOCK-TEST-39.car",
        "tgt"        : "39-40/FACTORYDOCK-TEST-40.car",
        "src_version": "01.00.0039",
        "tgt_version": "01.00.0040",
        "src_count"  : 80,
        "tgt_count"  : 80,
        "new_ids"    : set(),
        "removed_ids": set(),
    },
    {
        "label"      : "41-42",
        "src"        : "41-42/FACTORYDOCK-TEST-41.car",
        "tgt"        : "41-42/FACTORYDOCK-TEST-42.car",
        "src_version": "01.00.0041",
        "tgt_version": "01.00.0042",
        "src_count"  : 81,
        "tgt_count"  : 81,
        "new_ids"    : set(),
        "removed_ids": set(),
    },
    {
        "label"      : "45-46",
        "src"        : "45-46/FACTORYDOCK-TEST-45.car",
        "tgt"        : "45-46/FACTORYDOCK-TEST-46.car",
        "src_version": "01.00.0045",
        "tgt_version": "01.00.0046",
        "src_count"  : 81,
        "tgt_count"  : 81,
        "new_ids"    : set(),
        "removed_ids": set(),
    },
    {
        "label"      : "47-48",
        "src"        : "47-48/FACTORYDOCK-TEST-47.car",
        "tgt"        : "47-48/FACTORYDOCK-TEST-48.car",
        "src_version": "01.00.0047",
        "tgt_version": "01.00.0048",
        "src_count"  : 81,
        "tgt_count"  : 81,
        "new_ids"    : set(),
        "removed_ids": set(),
    },
    {
        "label"      : "49-50",
        "src"        : "49-50/FACTORYDOCK-TEST-49.car",
        "tgt"        : "49-50/FACTORYDOCK-TEST-50.car",
        "src_version": "01.00.0049",
        "tgt_version": "01.00.0050",
        "src_count"  : 81,
        "tgt_count"  : 81,
        "new_ids"    : set(),
        "removed_ids": set(),
    },
    {
        "label"      : "51-52",
        "src"        : "51-52/FACTORYDOCK-TEST-51.car",
        "tgt"        : "51-52/FACTORYDOCK-TEST-52.car",
        "src_version": "01.00.0006",
        "tgt_version": "01.00.0007",
        "src_count"  : 37,
        "tgt_count"  : 43,
        "new_ids"    : {"processor_1505","processor_1528","processor_1533",
                        "processor_1558","processor_1563","processor_1587"},
        "removed_ids": set(),
    },
    {
        "label"      : "53-54",
        "src"        : "53-54/FACTORYDOCK-TEST-53.car",
        "tgt"        : "53-54/FACTORYDOCK-TEST-54.car",
        "src_version": "01.00.0043",
        "tgt_version": "01.00.0044",
        "src_count"  : 81,
        "tgt_count"  : 81,
        "new_ids"    : set(),
        "removed_ids": set(),
    },
    {
        "label"      : "55-56",
        "src"        : "55-56/INT03.00.0001.iar",
        "tgt"        : "55-56/INT03.00.0011.iar",
        "src_version": "03.00.0001",
        "tgt_version": "03.00.0011",
        "src_count"  : 35,
        "tgt_count"  : 42,
        "new_ids"    : {"processor_59","processor_74","processor_284",
                        "processor_1300","processor_1315","processor_1340",
                        "processor_1345","processor_1384","processor_1397",
                        "processor_1412","processor_1417","processor_1458",
                        "processor_1561","processor_1566","processor_1826"},
        "removed_ids": {"processor_2036","processor_2049","processor_2066",
                        "processor_2090","processor_2097","processor_2157",
                        "processor_2180","processor_2272"},
    },
]

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

PASS = "✅ PASS"
FAIL = "❌ FAIL"


class Results:
    def __init__(self):
        self.checks  = []
        self.passed  = 0
        self.failed  = 0

    def check(self, name, actual, expected):
        ok = actual == expected
        self.checks.append((ok, name, expected, actual))
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            print(f"    {FAIL}  {name}")
            print(f"            expected : {expected!r}")
            print(f"            actual   : {actual!r}")
        return ok

    def check_set(self, name, actual_set, expected_set):
        missing = expected_set - actual_set
        extra   = actual_set - expected_set
        ok = not missing and not extra
        self.checks.append((ok, name, sorted(expected_set), sorted(actual_set)))
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            print(f"    {FAIL}  {name}")
            if missing:
                print(f"            missing  : {sorted(missing)}")
            if extra:
                print(f"            extra    : {sorted(extra)}")
        return ok


def run_pair(pair: dict, workspace: str, results: Results):
    label    = pair["label"]
    src_path = os.path.join(FLOW_DUMP, pair["src"])
    tgt_path = os.path.join(FLOW_DUMP, pair["tgt"])

    print(f"\n  [{label}]")

    # Extract
    src_ext = extract_iar(src_path, workspace)
    tgt_ext = extract_iar(tgt_path, workspace)

    if not src_ext["success"]:
        print(f"    {FAIL}  source extraction: {src_ext['error']}")
        results.failed += 1
        return
    if not tgt_ext["success"]:
        print(f"    {FAIL}  target extraction: {tgt_ext['error']}")
        results.failed += 1
        return

    # Parse
    src_data = extract_steps(src_ext["project_xml"])
    tgt_data = extract_steps(tgt_ext["project_xml"])

    if not src_data["success"]:
        print(f"    {FAIL}  source parse: {src_data['error']}")
        results.failed += 1
        return
    if not tgt_data["success"]:
        print(f"    {FAIL}  target parse: {tgt_data['error']}")
        results.failed += 1
        return

    # Delta
    delta = compute_delta(src_data, tgt_data)

    # --- Assertions ---
    results.check(f"[{label}] source version",    src_data["integration_version"], pair["src_version"])
    results.check(f"[{label}] target version",    tgt_data["integration_version"], pair["tgt_version"])
    results.check(f"[{label}] source proc count", src_data["processor_count"],     pair["src_count"])
    results.check(f"[{label}] target proc count", tgt_data["processor_count"],     pair["tgt_count"])
    results.check(f"[{label}] new count",         len(delta["new_steps"]),         len(pair["new_ids"]))
    results.check(f"[{label}] removed count",     len(delta["removed_steps"]),     len(pair["removed_ids"]))

    actual_new = {p["processor_id"] for p in delta["new_steps"]}
    actual_rmv = {p["processor_id"] for p in delta["removed_steps"]}
    results.check_set(f"[{label}] new IDs",     actual_new, pair["new_ids"])
    results.check_set(f"[{label}] removed IDs", actual_rmv, pair["removed_ids"])

    # All new/removed steps must have non-empty names
    for p in delta["new_steps"]:
        results.check(f"[{label}] {p['processor_id']} name non-empty", bool(p["name"]), True)
    for p in delta["removed_steps"]:
        results.check(f"[{label}] {p['processor_id']} name non-empty", bool(p["name"]), True)

    # modified_steps must be [] placeholder (M2 will fill it)
    results.check(f"[{label}] modified_steps placeholder", delta["modified_steps"], [])

    # Print one-line summary for passing pairs
    new_count = len(delta["new_steps"])
    rmv_count = len(delta["removed_steps"])
    print(f"    {PASS}  v{src_data['integration_version']} -> v{tgt_data['integration_version']}  |  "
          f"new={new_count}  removed={rmv_count}  "
          f"src_procs={src_data['processor_count']}  tgt_procs={tgt_data['processor_count']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="M1 test — structural delta validation",
        epilog=(
            "Examples:\n"
            "  python tests/test_m1_structural_delta.py\n"
            "  python tests/test_m1_structural_delta.py 32-33\n"
            "  python tests/test_m1_structural_delta.py 32-33 49-50 55-56"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "labels", nargs="*", metavar="LABEL",
        help="Pair labels to test e.g. 32-33 49-50 55-56. Omit to run all.",
    )
    args = parser.parse_args()

    valid_labels = {p["label"].strip() for p in PAIRS}

    if args.labels:
        unknown = [l for l in args.labels if l not in valid_labels]
        if unknown:
            print(f"Unknown label(s): {unknown}")
            print(f"Available: {sorted(valid_labels)}")
            sys.exit(1)
        selected = [p for p in PAIRS if p["label"].strip() in args.labels]
    else:
        selected = PAIRS

    print("=" * 70)
    print("M1 TEST — Structural Delta")
    label_str = "all" if not args.labels else ", ".join(args.labels)
    print(f"Pairs: {len(selected)} of {len(PAIRS)}  ({label_str})")
    print("=" * 70)

    workspace = os.path.join(project_root, "workspace")
    os.makedirs(workspace, exist_ok=True)

    results = Results()

    for pair in selected:
        run_pair(pair, workspace, results)

    total = results.passed + results.failed
    print("\n" + "=" * 70)
    print(f"RESULTS: {results.passed}/{total} passed  |  {results.failed} failed")
    print("=" * 70)

    if results.failed > 0:
        print("\n❌  M1 FAILED — fix before proceeding to M2.")
        sys.exit(1)
    else:
        print(f"\n✅  M1 PASSED — {len(selected)} pair(s) validated.")

if __name__ == "__main__":
    main()
