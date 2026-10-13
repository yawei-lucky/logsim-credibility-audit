#!/usr/bin/env python3
"""Compare inspectable image-annotation intervals; do not recognize objects."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SIZE = (800, 450)


class InputError(ValueError):
    """An image or annotation cannot establish the declared comparison."""


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"{name} must be a finite number")
    return float(value)


def interval(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise InputError(f"{name} must be a two-endpoint list")
    lo, hi = (finite_number(endpoint, name) for endpoint in value)
    if not 0 <= lo <= hi < IMAGE_SIZE[0]:
        raise InputError(f"{name} must be ordered and inside image width {IMAGE_SIZE[0]}")
    return [lo, hi]


def indexed_frames(rows, name):
    if not isinstance(rows, list):
        raise InputError(f"{name} frames must be a list")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("frame_index")) is not int or row["frame_index"] < 0:
            raise InputError(f"{name} frame_index must be a nonnegative integer")
        if row["frame_index"] in indexed:
            raise InputError(f"duplicate {name} frame_index {row['frame_index']}")
        indexed[row["frame_index"]] = row
    return indexed


def verify_rgb(row, root):
    value, expected_hash = row.get("rgb_path"), row.get("rgb_sha256")
    if not isinstance(value, str) or not value:
        raise InputError("rgb_path must identify an image")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
        raise InputError("rgb_sha256 must be a lowercase SHA-256")
    path = Path(value)
    if not path.is_absolute():
        path = Path(root) / path
    if not path.is_file():
        raise InputError(f"RGB file is missing: {path}")
    actual_hash = file_sha256(path)
    if actual_hash != expected_hash:
        raise InputError(f"RGB SHA-256 mismatch: {path}")
    try:
        with Image.open(path) as image:
            image.load()
            if image.mode != "RGB" or image.size != IMAGE_SIZE:
                raise InputError(f"RGB must have three channels and size {IMAGE_SIZE}: {path}")
    except (OSError, ValueError) as error:
        raise InputError(f"RGB decoding failed: {path}: {error}") from error
    return {"rgb_path": str(path.resolve()), "rgb_sha256": actual_hash, "rgb_size": list(IMAGE_SIZE)}


def invalid_result(frame_index, reason):
    return {"frame_index": frame_index if type(frame_index) is int else None, "evidence_label": "rejected", "tested": False,
            "failure_kind": "input_invalid", "minimum_gap_px": None, "reason": str(reason)}


def validate_reference(reference, root):
    if not isinstance(reference, dict) or not isinstance(reference.get("reference_id"), str) or not reference["reference_id"]:
        raise InputError("reference_id must be a nonempty string")
    if not isinstance(reference.get("coordinate_convention"), str) or not reference["coordinate_convention"]:
        raise InputError("reference coordinate_convention must be explicit")
    if reference.get("band_y_px") != [200, 240]:
        raise InputError("this bounded evaluator requires reference band_y_px [200,240]")
    frames = indexed_frames(reference.get("frames"), "reference")
    if len(frames) != 3:
        raise InputError("this bounded reference must contain exactly three frames")
    for row in frames.values():
        finite_number(row.get("timestamp_s"), "reference timestamp_s")
        if row.get("visibility") != "visible":
            raise InputError("reference must have visible candidate annotations")
        if not isinstance(row.get("target"), str) or not row["target"]:
            raise InputError("reference target must be explicit")
        interval(row.get("u_interval_px"), "reference u_interval_px")
        verify_rgb(row, root)
    return frames


def evaluate_frame(expected, submitted, root):
    result = {"frame_index": expected["frame_index"], "timestamp_s": expected["timestamp_s"],
              "target": expected["target"], "reference_u_interval_px": expected["u_interval_px"],
              "minimum_gap_px": None}
    try:
        if finite_number(submitted.get("timestamp_s"), "submission timestamp_s") != expected["timestamp_s"]:
            raise InputError("timestamp_s differs from the frozen reference")
        if submitted.get("target") != expected["target"]:
            raise InputError("target differs from the frozen visible shaft contour construct")
        basis = submitted.get("annotation_basis")
        if not isinstance(basis, str) or not basis.strip():
            raise InputError("annotation_basis must identify the image reader")
        visibility = submitted.get("visibility")
        if visibility not in ("visible", "unknown", "absent"):
            raise InputError("visibility must be visible, unknown or absent")
        if "u_interval_px" not in submitted:
            raise InputError("u_interval_px must be explicit; use null for unmeasured position")
        result.update(verify_rgb(submitted, root))
        result.update({"annotation_basis": basis, "submitted_visibility": visibility})
        if visibility != "visible":
            if submitted["u_interval_px"] is not None:
                raise InputError("unknown/absent position must remain null")
            result.update({"evidence_label": "down-weighted", "tested": False,
                           "failure_kind": "measurement_unqualified",
                           "submitted_u_interval_px": None,
                           "reason": "Position is unmeasured; presence/absence semantics are not independently qualified."})
            return result
        actual = interval(submitted["u_interval_px"], "submission u_interval_px")
        result["submitted_u_interval_px"] = actual
    except (InputError, OSError, TypeError, ValueError) as error:
        result.update(invalid_result(expected["frame_index"], error))
        return result
    expected_interval = interval(expected["u_interval_px"], "reference u_interval_px")
    gap = max(expected_interval[0] - actual[1], actual[0] - expected_interval[1], 0.0)
    result["minimum_gap_px"] = gap
    if gap > 0:
        result.update({"evidence_label": "rejected", "tested": True,
                       "failure_kind": "annotation_interval_conflict",
                       "reason": "Submitted and frozen candidate annotation intervals are strictly disjoint."})
    else:
        result.update({"evidence_label": "down-weighted", "tested": True,
                       "failure_kind": None, "comparison": "no_conflict",
                       "reason": "Intervals overlap; this necessary coarse check does not establish physical equivalence."})
    return result


def evaluate_submission(reference, submission, submission_root, reference_root=ROOT):
    """Validate images and compare submitted annotations without reading their semantics."""
    report = {"reference_id": reference.get("reference_id") if isinstance(reference, dict) else None,
              "evaluation_kind": "inspectable image-annotation interval comparison",
              "overall_evidence_label": "down-weighted", "input_errors": [], "frames": [],
              "limitations": ["No automated RGB object recognition or shaft measurement is performed.",
                              "Candidate intervals depend on visual readers and are not human ground truth.",
                              "Overlap is necessary only; it does not establish physical or task equivalence.",
                              "A conflict does not isolate a physical HUGSIM defect.",
                              "Unknown/absent observations do not establish an independently qualified visibility contradiction."]}
    try:
        expected = validate_reference(reference, reference_root)
        if not isinstance(submission, dict) or submission.get("reference_id") != reference["reference_id"]:
            raise InputError("submission reference_id must match frozen reference")
        convention = submission.get("coordinate_convention", reference["coordinate_convention"])
        if convention != reference["coordinate_convention"]:
            raise InputError("submission coordinate_convention differs from frozen reference")
        actual = indexed_frames(submission.get("frames"), "submission")
        if set(actual) != set(expected):
            raise InputError(f"required frame identities differ; missing {sorted(set(expected) - set(actual))}, extra {sorted(set(actual) - set(expected))}")
    except (InputError, OSError, TypeError, ValueError) as error:
        report["input_errors"].append(str(error))
        rows = reference.get("frames", []) if isinstance(reference, dict) else []
        report["frames"] = [invalid_result(row.get("frame_index"), error) for row in rows if isinstance(row, dict)]
        return report
    report["coordinate_convention"] = reference["coordinate_convention"]
    report["band_y_px"] = reference["band_y_px"]
    report["frames"] = [evaluate_frame(row, actual[index], submission_root) for index, row in expected.items()]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    environment = {"time_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
                   "role": "CPU image-annotation interval evaluator", "pid": os.getpid(),
                   "working_directory": str(Path.cwd()), "python": sys.executable,
                   "reference": str(args.reference.resolve()), "submission": str(args.submission.resolve()),
                   "output": str(args.output.resolve()), "argv": sys.argv,
                   "script_sha256": file_sha256(__file__), "health_status": "starting"}
    (args.output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    print(json.dumps(environment), flush=True)
    try:
        reference = json.loads(args.reference.read_text())
        submission = json.loads(args.submission.read_text())
        report = evaluate_submission(reference, submission, args.submission.parent)
        report.update({"reference_sha256": file_sha256(args.reference),
                       "submission_sha256": file_sha256(args.submission)})
        (args.output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        status = {"health_status": "completed_annotation_evaluation", "physical_equivalence_established": False}
        (args.output / "execution_status.json").write_text(json.dumps(status, indent=2) + "\n")
        print(json.dumps(status), flush=True)
        return 2 if report["input_errors"] or any(row["failure_kind"] == "input_invalid" for row in report["frames"]) else 0
    except Exception as error:
        (args.output / "failure.txt").write_text(f"{type(error).__name__}: {error}\n")
        (args.output / "execution_status.json").write_text(json.dumps({"health_status": "failed", "error": str(error)}, indent=2) + "\n")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
