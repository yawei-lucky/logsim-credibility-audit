#!/usr/bin/env python3
"""Evaluate a finite marker screening contract from submitted RGB pairs on CPU."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path

import cv2
import numpy as np

from run_motion_observation_probe import measure_pair


class InputError(ValueError):
    """The submitted inputs cannot establish the declared test contract."""


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numeric(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{name} must be a finite number")
    if not math.isfinite(value):
        raise InputError(f"{name} must be a finite number")
    return float(value)


def indexed(rows, name):
    if not isinstance(rows, list):
        raise InputError(f"{name} must be a list")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise InputError(f"{name} requires a nonempty string id for every entry")
        if row["id"] in result:
            raise InputError(f"duplicate {name} id: {row['id']}")
        result[row["id"]] = row
    if not result:
        raise InputError(f"{name} cannot be empty")
    return result


def projection_width(points, intrinsics):
    """Independent endpoint projection, with each endpoint's own camera depth."""
    try:
        xyz = np.asarray(points, dtype=np.float64)
        matrix = np.asarray(intrinsics, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise InputError(f"invalid projection inputs: {error}") from error
    if xyz.shape != (2, 3) or not np.isfinite(xyz).all() or np.any(xyz[:, 2] <= 0):
        raise InputError("marker_camera_xyz_m requires two finite points in front of the camera")
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise InputError("intrinsics requires a finite 3x3 camera matrix")
    projected = (matrix @ xyz.T).T
    if np.any(projected[:, 2] <= 0):
        raise InputError("projection denominator must be positive")
    uv = projected[:, :2] / projected[:, 2:3]
    if not np.isfinite(uv).all():
        raise InputError("nonfinite endpoint projection")
    return float(abs(uv[1, 0] - uv[0, 0])), uv.tolist()


def read_rgb(value, root, camera):
    if not isinstance(value, str) or not value:
        raise InputError("bright and dim must identify RGB files")
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        raise InputError(f"RGB file is missing: {path}")
    rgb = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if rgb is None or rgb.dtype != np.uint8 or rgb.shape != (camera["height"], camera["width"], 3):
        raise InputError(f"RGB must be uint8 with declared height, width, and three channels: {path}")
    return cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB), str(path.resolve()), file_sha256(path)


def failure(message, kind="input_invalid", tested=False):
    return {"evidence_label": "rejected", "tested": tested, "failure_kind": kind, "reason": str(message)}


def evaluate_frame(expected, submitted, suite, root):
    result = {"id": expected["id"], "expected_visible_markers": expected["expected_visible_markers"]}
    try:
        expected_time = numeric(expected.get("capture_time_s"), "suite capture_time_s")
        actual_time = numeric(submitted.get("capture_time_s"), "submission capture_time_s")
        if actual_time != expected_time:
            raise InputError(f"capture_time_s mismatch: expected {expected_time}, received {actual_time}")
        width, uv = projection_width(expected.get("marker_camera_xyz_m"), suite["camera"]["intrinsics"])
        budget = suite["measurement"]["width_error_bound_px"]
        if expected["expected_visible_markers"] == 2 and width <= 2 * budget:
            raise InputError("reference marker width is unresolved under the frozen measurement budget")
        bright, bright_path, bright_hash = read_rgb(submitted.get("bright"), root, suite["camera"])
        dim, dim_path, dim_hash = read_rgb(submitted.get("dim"), root, suite["camera"])
        result.update({"capture_time_s": actual_time, "expected_width_px": width, "projected_uv_px": uv,
                       "rgb": [bright_path, dim_path], "rgb_sha256": [bright_hash, dim_hash]})
    except (InputError, KeyError, TypeError, ValueError) as error:
        result.update(failure(error))
        return result
    try:
        observation = measure_pair(bright, dim, suite["measurement"])
    except ValueError as error:
        message = str(error)
        result["measurement_failure"] = message
        if expected["expected_visible_markers"] == 1 and message == "expected exactly two visible markers, found 1":
            result.update({"evidence_label": "accepted", "tested": True, "observed_visible_markers": 1,
                           "measured_width_px": None, "failure_kind": None})
        elif message.startswith("expected exactly two visible markers, found "):
            result.update(failure(message, "contradiction", True))
        else:
            result.update(failure(message))
        return result
    result.update({"observed_visible_markers": 2, "measured_width_px": observation["width_px"],
                   "measurement": observation})
    if expected["expected_visible_markers"] != 2:
        result.update(failure("two measurable markers contradict the declared single-marker condition", "contradiction", True))
        return result
    residual = observation["width_px"] - width
    result["width_residual_px"] = residual
    if abs(residual) > budget:
        result.update(failure(f"width residual {residual} px exceeds the frozen {budget} px budget", "contradiction", True))
    else:
        result.update({"evidence_label": "accepted", "tested": True, "failure_kind": None})
    return result


def validate_suite(suite):
    if not isinstance(suite, dict) or type(suite.get("schema_version")) is not int or suite.get("schema_version") != 1:
        raise InputError("suite schema_version must be 1")
    if not isinstance(suite.get("suite_id"), str) or not suite["suite_id"]:
        raise InputError("suite_id must be a nonempty string")
    camera = suite.get("camera", {})
    if not isinstance(camera, dict):
        raise InputError("camera must be an object")
    for field in ("width", "height"):
        if isinstance(camera.get(field), bool) or not isinstance(camera.get(field), int) or camera[field] <= 0:
            raise InputError(f"camera {field} must be a positive integer")
    measurement = suite.get("measurement", {})
    if not isinstance(measurement, dict):
        raise InputError("measurement must be an object")
    if numeric(measurement.get("width_error_bound_px"), "width_error_bound_px") <= 0:
        raise InputError("width_error_bound_px must be positive")
    if not 0 < numeric(measurement.get("difference_threshold_u8"), "difference_threshold_u8") < 255:
        raise InputError("difference_threshold_u8 must lie between 0 and 255")
    area = measurement.get("min_component_area_px")
    if isinstance(area, bool) or not isinstance(area, int) or area <= 0:
        raise InputError("min_component_area_px must be a positive integer")
    cases = indexed(suite.get("cases"), "suite case")
    for case in cases.values():
        frames = indexed(case.get("frames"), "suite frame")
        times = []
        for frame in frames.values():
            times.append(numeric(frame.get("capture_time_s"), "suite capture_time_s"))
            if type(frame.get("expected_visible_markers")) is not int or frame["expected_visible_markers"] not in (1, 2):
                raise InputError("expected_visible_markers must be 1 or 2")
            projection_width(frame.get("marker_camera_xyz_m"), camera.get("intrinsics"))
        if any(after <= before for before, after in zip(times, times[1:])):
            raise InputError(f"suite frame times must increase strictly: {case['id']}")
    return cases


def evaluate_submission(suite, submission, submission_root):
    report = {"schema_version": 1, "suite_id": suite.get("suite_id") if isinstance(suite, dict) else None,
              "simulator": submission.get("simulator") if isinstance(submission, dict) else None,
              "claim": "This submitted RGB set satisfies the specified finite marker width and visibility contract.",
              "overall_evidence_label": "rejected", "contract_passed": False,
              "screening_contract_satisfied": False, "input_errors": [], "cases": [],
              "limitations": ["Passing supports only this finite declared camera, marker, and measurement contract.",
                              "Width does not detect a common translation of both markers.",
                              "Declared capture timestamps are checked; actual capture or delivery age is not independently observed.",
                              "A single visible component establishes count only; the surviving marker's identity or absolute location is not checked.",
                              "No ordinary vehicle geometry, real-camera equivalence, driving safety, or event replay rate is qualified.",
                              "Historical seed cases reused here are not new independent held-out samples."]}
    try:
        expected_cases = validate_suite(suite)
        if not isinstance(submission, dict) or type(submission.get("schema_version")) is not int or submission.get("schema_version") != 1 or submission.get("suite_id") != suite["suite_id"]:
            raise InputError("submission schema_version or suite_id mismatch")
        simulator = submission.get("simulator")
        if not isinstance(simulator, dict) or any(not isinstance(simulator.get(key), str) or not simulator[key] for key in ("name", "version")):
            raise InputError("submission must identify simulator name and version")
        actual_cases = indexed(submission.get("cases"), "submission case")
    except (InputError, KeyError, TypeError, ValueError) as error:
        report["input_errors"].append(str(error))
        suite_cases = suite.get("cases") if isinstance(suite, dict) else None
        report["not_tested_case_ids"] = [case.get("id") for case in suite_cases if isinstance(case, dict)] if isinstance(suite_cases, list) else []
        return report
    missing_cases = sorted(expected_cases.keys() - actual_cases.keys())
    extra_cases = sorted(actual_cases.keys() - expected_cases.keys())
    if missing_cases or extra_cases:
        report["input_errors"].append(f"case ID mismatch: missing={missing_cases}, extra={extra_cases}")
    for case_id, case in expected_cases.items():
        case_report = {"id": case_id, "question": case.get("question"), "frames": []}
        try:
            if case_id not in actual_cases:
                raise InputError("required case was not submitted")
            actual_frames = indexed(actual_cases[case_id].get("frames"), "submission frame")
            expected_frames = indexed(case["frames"], "suite frame")
            missing_frames = sorted(expected_frames.keys() - actual_frames.keys())
            extra_frames = sorted(actual_frames.keys() - expected_frames.keys())
            if missing_frames or extra_frames:
                raise InputError(f"frame ID mismatch: missing={missing_frames}, extra={extra_frames}")
        except (InputError, TypeError) as error:
            case_report.update(failure(error))
            case_report["not_tested_frame_ids"] = [frame["id"] for frame in case["frames"]]
            report["cases"].append(case_report)
            continue
        for frame_id, frame in expected_frames.items():
            case_report["frames"].append(evaluate_frame(frame, actual_frames[frame_id], suite, Path(submission_root)))
        case_report["not_tested_frame_ids"] = [frame["id"] for frame in case_report["frames"] if not frame["tested"]]
        case_report["evidence_label"] = "accepted" if all(frame["evidence_label"] == "accepted" for frame in case_report["frames"]) else "rejected"
        case_report["tested"] = all(frame["tested"] for frame in case_report["frames"])
        report["cases"].append(case_report)
    report["not_tested_case_ids"] = [case["id"] for case in report["cases"] if not case["tested"]]
    report["expected_case_count"] = len(expected_cases)
    report["accepted_case_count"] = sum(case["evidence_label"] == "accepted" for case in report["cases"])
    report["expected_frame_count"] = sum(len(case["frames"]) for case in expected_cases.values())
    report["tested_frame_count"] = sum(frame["tested"] for case in report["cases"] for frame in case["frames"])
    report["screening_contract_satisfied"] = not report["input_errors"] and all(case["evidence_label"] == "accepted" for case in report["cases"])
    report["contract_passed"] = report["screening_contract_satisfied"]
    if report["screening_contract_satisfied"]:
        report["overall_evidence_label"] = "down-weighted"
    return report


evaluate_suite = evaluate_submission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--submission", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    environment = {"host": platform.node(), "role": "CPU credibility screening evaluator", "cwd": str(Path.cwd()),
                   "suite": str(args.suite.resolve()), "submission": str(args.submission.resolve()),
                   "output": str(args.output.resolve())}
    try:
        def reject_nonfinite_constant(value):
            raise InputError(f"nonfinite JSON constant: {value}")
        suite = json.loads(args.suite.read_text(), parse_constant=reject_nonfinite_constant)
        submission = json.loads(args.submission.read_text(), parse_constant=reject_nonfinite_constant)
        report = evaluate_submission(suite, submission, args.submission.resolve().parent)
        environment["suite_sha256"] = file_sha256(args.suite)
        environment["submission_sha256"] = file_sha256(args.submission)
    except (OSError, ValueError) as error:
        report = {"overall_evidence_label": "rejected", "screening_contract_satisfied": False, "contract_passed": False,
                  "input_errors": [str(error)], "cases": []}
    report["environment"] = environment
    report["health_status"] = "completed" if not report.get("input_errors") else "input rejected"
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"report": str((args.output / "report.json").resolve()),
                      "overall_evidence_label": report["overall_evidence_label"],
                      "screening_contract_satisfied": report.get("screening_contract_satisfied", False)}))
    return 0 if report.get("screening_contract_satisfied", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
