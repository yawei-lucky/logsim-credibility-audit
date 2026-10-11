#!/usr/bin/env python3
"""Compare two independent process runs of the boundary probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def compare_runs(left, right):
    left_rows = load(Path(left) / "measurements.json")
    right_rows = load(Path(right) / "measurements.json")
    if len(left_rows) != len(right_rows):
        raise ValueError("run row counts differ")
    identity_fields = ("context", "center_depth_m", "condition", "kind")
    details = []
    for first, second in zip(left_rows, right_rows, strict=True):
        identity_equal = all(first[field] == second[field] for field in identity_fields)
        hashes_equal = (
            first["rgb_sha256"] == second["rgb_sha256"]
            and first.get("state_restore_check") == second.get("state_restore_check")
        )
        measurements_equal = first["measurement"] == second["measurement"]
        records_equal = first == second
        decisions_equal = all(
            first[field] == second[field]
            for field in (
                "measurement_failure",
                "full_prediction_within_budget",
                "simple_prediction_excluded",
                "common_depth_prediction_excluded",
                "availability_correct",
            )
        )
        details.append(
            {
                "identity": {field: first[field] for field in identity_fields},
                "identity_equal": identity_equal,
                "png_hashes_equal": hashes_equal,
                "measurements_equal": measurements_equal,
                "decisions_equal": decisions_equal,
                "records_equal": records_equal,
            }
        )
    return {
        "pair_count": len(details),
        "rgb_count": sum(
            2 + (2 if row.get("state_restore_check") is not None else 0)
            for row in left_rows
        ),
        "all_identities_equal": all(row["identity_equal"] for row in details),
        "all_png_hashes_equal": all(row["png_hashes_equal"] for row in details),
        "all_measurements_equal": all(row["measurements_equal"] for row in details),
        "all_decisions_equal": all(row["decisions_equal"] for row in details),
        "all_records_equal": all(row["records_equal"] for row in details),
        "all_repeat_checks_passed": all(
            all(row[key] for key in row if key.endswith("_equal")) for row in details
        ),
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = compare_runs(args.left.resolve(), args.right.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, indent=2))
    return 0 if result["all_repeat_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
