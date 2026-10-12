#!/usr/bin/env python3
"""Re-evaluate frozen seed RGB and qualify the screener with deliberate faults.

This CPU-only replay does not execute a new simulator or produce real-world
ground truth. Every output is written into a new directory.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from run_motion_observation_boundary_probe import synthetic_pair_variable_sigma
from run_motion_observation_probe import measure_pair, write_rgb

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(frame, suite):
    points = np.asarray(frame["marker_camera_xyz_m"], dtype=np.float64)
    homogeneous = (np.asarray(suite["camera"]["intrinsics"]) @ points.T).T
    return homogeneous[:, :2] / homogeneous[:, 2:3]


def qualify(suite, output):
    """Independent 2D rasterization at the prescribed projected coordinates."""
    height, width = suite["camera"]["height"], suite["camera"]["width"]
    yy, xx = np.indices((height, width))
    texture = np.stack([35 + xx % 41, 55 + yy % 37, 45 + (xx + yy) % 43], axis=-1).astype(np.uint8)
    rows = []
    for case in suite["cases"]:
        for frame in case["frames"]:
            if frame["expected_visible_markers"] != 2:
                continue
            uv = project(frame, suite)
            depths = np.asarray(frame["marker_camera_xyz_m"])[:, 2]
            sigmas = suite["camera"]["intrinsics"][0][0] * suite["render_contract"]["marker_sigma_m"] / depths
            expected = abs(float(uv[1, 0] - uv[0, 0]))
            for bg_id, bg in [("black", np.zeros_like(texture)), ("texture", texture)]:
                for phase in [0.0, 0.5]:
                    centres = uv + np.array([phase, 0.0])
                    pair = synthetic_pair_variable_sigma(bg, centres, sigmas, 0.9, [0.9, 0.1])
                    measured = measure_pair(*pair, suite["measurement"])
                    rows.append({"case_id": case["id"], "frame_id": frame["id"],
                                 "background": bg_id, "phase_px": phase,
                                 "error_px": measured["width_px"] - expected})
    maximum = max(abs(row["error_px"]) for row in rows)
    result = {"count": len(rows), "max_abs_width_error_px": maximum,
              "budget_px": suite["measurement"]["width_error_bound_px"],
              "qualified": maximum <= suite["measurement"]["width_error_bound_px"],
              "scope": "Finite 2D grid at seed target widths, sizes and phases; no other renderer or real-camera qualification.",
              "rows": rows}
    save(output / "measurement_qualification.json", result)
    if not result["qualified"]:
        raise ValueError("measurement qualification failed; seed replay not started")
    return result


def build_submission(suite, output):
    cases = []
    for case in suite["cases"]:
        frames = []
        for frame in case["frames"]:
            row = {"id": frame["id"], "capture_time_s": frame["capture_time_s"]}
            for role in ["bright", "dim"]:
                source = ROOT / frame["seed_rgb"][role]["path"]
                expected = frame["seed_rgb"][role]["sha256"]
                if sha256(source) != expected:
                    raise ValueError(f"frozen seed hash mismatch: {source}")
                target = output / "rgb" / case["id"] / f'{frame["id"]}_{role}.png'
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                row[role] = str(target.resolve())
            frames.append(row)
        cases.append({"id": case["id"], "frames": frames})
    return {"schema_version": 1, "suite_id": suite["suite_id"],
            "simulator": {"name": "HUGSIM historical seed replay", "version": "adeca402cad4af8635e13d0a105e2fee6a14de85"},
            "execution_scope": "Historical RGB replay, not a new simulator execution.", "cases": cases}


def find_case(submission, case_id):
    return next(case for case in submission["cases"] if case["id"] == case_id)


def controls(baseline, suite, output):
    """Faults are tester qualifications, never alleged new HUGSIM failures."""
    variants = []
    for name, condition in [("hidden_distance_bias_1m", "distance"),
                            ("hidden_capture_delay_0_5s", "delay"),
                            ("hidden_constant_scale_1_1", "constant_scale")]:
        altered = copy.deepcopy(baseline)
        case = find_case(altered, "motion_train_fast")
        control = next(item for item in suite["negative_control_inputs"] if item["condition"] == condition)
        by_id = {item["id"]: item for item in control["frames"]}
        for frame in case["frames"]:
            for role in ["bright", "dim"]:
                frozen = by_id[frame["id"]]["rgb"][role]
                path = ROOT / frozen["path"]
                # These are known interventions evaluated against an unchanged
                # baseline contract, with their intervention labels concealed.
                if sha256(path) != frozen["sha256"]:
                    raise ValueError(f"negative-control source hash mismatch: {path}")
                frame[role] = str(path)
        variants.append((name, altered, "motion_train_fast", "contradiction"))
    altered = copy.deepcopy(baseline)
    case = find_case(altered, "motion_train_fast")
    for frame in case["frames"][1:]:
        for role in ["bright", "dim"]:
            frame[role] = case["frames"][0][role]
    variants.append(("frozen_motion_frames", altered, "motion_train_fast", "contradiction"))
    for name, case_id in [("ignored_front_occluder", "geometry_left_marker_occluder_front"),
                          ("ignored_marker_removal", "geometry_left_marker_missing")]:
        altered = copy.deepcopy(baseline)
        good = find_case(altered, "geometry_equal_depth")["frames"][0]
        frame = find_case(altered, case_id)["frames"][0]
        frame.update({role: good[role] for role in ["bright", "dim"]})
        variants.append((name, altered, case_id, "contradiction"))
    altered = copy.deepcopy(baseline)
    altered["cases"].pop()
    variants.append(("missing_required_case", altered, "motion_heldout", "input_invalid"))
    altered = copy.deepcopy(baseline)
    find_case(altered, "motion_train_fast")["frames"][1]["capture_time_s"] += 0.25
    variants.append(("incorrect_capture_timestamp", altered, "motion_train_fast", "input_invalid"))
    # Construct an independently known, geometrically wrong common-depth image.
    altered = copy.deepcopy(baseline)
    case_spec = next(case for case in suite["cases"] if case["id"] == "geometry_depth_skew_12m")
    points = np.asarray(case_spec["frames"][0]["marker_camera_xyz_m"])
    wrong_points = points.copy()
    wrong_points[:, 2] = 24.0
    projected = (np.asarray(suite["camera"]["intrinsics"]) @ wrong_points.T).T
    uv = projected[:, :2] / projected[:, 2:3]
    bg = np.zeros((suite["camera"]["height"], suite["camera"]["width"], 3), dtype=np.uint8)
    pair = synthetic_pair_variable_sigma(bg, uv, [1.2, 1.2], 0.9, [0.9, 0.1])
    directory = output / "negative_control_rgb"
    directory.mkdir()
    frame = find_case(altered, "geometry_depth_skew_12m")["frames"][0]
    for role, pixels in zip(["bright", "dim"], pair, strict=True):
        path = directory / f'collapsed_depth_{role}.png'
        write_rgb(path, pixels)
        frame[role] = str(path.resolve())
    variants.append(("collapsed_endpoint_depths", altered, "geometry_depth_skew_12m", "contradiction"))
    return variants


def evaluate(suite_path, submission, output, name):
    path = output / f'{name}_submission.json'
    save(path, submission)
    directory = output / name
    command = [sys.executable, str(ROOT / "scripts/evaluate_credibility_screening.py"),
               "--suite", str(suite_path), "--submission", str(path), "--output", str(directory)]
    result = subprocess.run(command, capture_output=True, text=True)
    (output / f'{name}_log.txt').write_text(result.stdout + result.stderr)
    report_path = directory / "report.json"
    if not report_path.exists():
        raise RuntimeError(f"evaluator failed without report: {name}; see log")
    report = json.loads(report_path.read_text())
    failures = []
    for case in report["cases"]:
        if case.get("failure_kind"):
            failures.append({"case_id": case["id"], "frame_id": None,
                             "tested": case["tested"], "failure_kind": case["failure_kind"],
                             "reason": case["reason"]})
        for frame in case["frames"]:
            if frame.get("failure_kind"):
                failures.append({"case_id": case["id"], "frame_id": frame["id"],
                                 "tested": frame["tested"], "failure_kind": frame["failure_kind"],
                                 "reason": frame["reason"]})
    return {"name": name, "exit_code": result.returncode,
            "contract_passed": report["contract_passed"],
            "report": str(report_path.relative_to(output)), "command": command,
            "failures": failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=ROOT / "configs/credibility_screening_001.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    suite_path = args.suite.resolve()
    suite = json.loads(suite_path.read_text())
    # Fail before occupying output when frozen inputs are absent or modified.
    for path, expected in suite["reference_sources"].items():
        source = ROOT / path
        if sha256(source) != expected:
            raise ValueError(f"frozen reference hash mismatch: {source}")
    for case in suite["cases"]:
        for frame in case["frames"]:
            for item in frame["seed_rgb"].values():
                if sha256(ROOT / item["path"]) != item["sha256"]:
                    raise ValueError(f'frozen seed hash mismatch: {item["path"]}')
    for control in suite["negative_control_inputs"]:
        for frame in control["frames"]:
            for item in frame["rgb"].values():
                if sha256(ROOT / item["path"]) != item["sha256"]:
                    raise ValueError(f'frozen negative-control hash mismatch: {item["path"]}')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(suite_path, output / "suite.json")
    save(output / "environment.json", {"host": platform.node(), "cwd": str(Path.cwd()),
         "python": sys.executable, "role": "CPU historical seed and deliberate-fault qualification",
         "suite": str(suite_path), "suite_sha256": sha256(suite_path), "output": str(output),
         "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
         "audit_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
         "audit_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True),
         "code_hashes": {str(path.relative_to(ROOT)): sha256(path) for path in [
             Path(__file__).resolve(), ROOT / "scripts/evaluate_credibility_screening.py",
             ROOT / "scripts/run_motion_observation_probe.py", ROOT / "scripts/run_motion_observation_boundary_probe.py"]},
         "health_status": "starting"})
    print(f"CPU screening seed: {output}", flush=True)
    qualification = qualify(suite, output)
    baseline = build_submission(suite, output)
    results = [evaluate(suite_path, baseline, output, "baseline")]
    print("Historical baseline evaluated", flush=True)
    for name, submission, expected_case, expected_kind in controls(baseline, suite, output):
        item = evaluate(suite_path, submission, output, name)
        item["expected_case_id"] = expected_case
        item["expected_failure_kind"] = expected_kind
        item["expected_failure_detected"] = any(
            failure["case_id"] == expected_case and failure["failure_kind"] == expected_kind
            and failure["tested"] == (expected_kind == "contradiction") for failure in item["failures"])
        if expected_kind == "contradiction":
            # An input error anywhere in a mechanism control invalidates that
            # control's qualification, even if some other frame contradicted.
            item["expected_failure_detected"] &= all(failure["failure_kind"] == "contradiction" for failure in item["failures"])
        results.append(item)
        print(f"Deliberate fault evaluated: {name}", flush=True)
    qualified = results[0]["contract_passed"] and results[0]["exit_code"] == 0 and all(
        not item["contract_passed"] and item["exit_code"] == 1
        and item["expected_failure_detected"] for item in results[1:])
    summary = {"suite_id": suite["suite_id"], "case_count": len(suite["cases"]),
               "frame_count": sum(len(case["frames"]) for case in suite["cases"]),
               "measurement_qualification": {key: value for key, value in qualification.items() if key != "rows"},
               "negative_controls_detected": sum(item["expected_failure_detected"] for item in results[1:]),
               "negative_controls_expected": len(results) - 1,
               "mechanism_contradictions_detected": sum(item["expected_failure_detected"] for item in results[1:] if item["expected_failure_kind"] == "contradiction"),
               "input_integrity_blocks_detected": sum(item["expected_failure_detected"] for item in results[1:] if item["expected_failure_kind"] == "input_invalid"),
               "screener_qualification_passed": qualified, "runs": results,
               "decision": "down-weighted",
               "claim": "A retrospective seed plus deliberate faults qualifies only these narrow screening behaviors; no new simulator execution or general credibility verdict."}
    save(output / "summary.json", summary)
    save(output / "status.json", {"health_status": "completed", "screener_qualification_passed": qualified})
    print(json.dumps({key: summary[key] for key in ["case_count", "frame_count", "negative_controls_detected", "negative_controls_expected", "screener_qualification_passed"]}), flush=True)
    return 0 if qualified else 1


if __name__ == "__main__":
    raise SystemExit(main())
