#!/usr/bin/env python3
"""Qualify, run, and read back a bounded history/current RGB exchange probe."""

from __future__ import annotations

import argparse
import itertools
import json
import os
import platform
import subprocess
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from compare_fixed_trajectory_receiver_regression import (
    CAMERAS, check_hash, git, load_json, normalized_input_contract, resolve, sha256,
)

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("RR", "RS", "SR", "SS")
VARIANTS = ("baseline", "baseline_repeat")


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def records(metadata, frame):
    result = {}
    for row in metadata["frames"]:
        path = Path(row["rgb_path"])
        if int(path.stem) == frame:
            camera = path.parent.name
            if camera in result:
                raise ValueError(f"duplicate camera record: {frame}/{camera}")
            result[camera] = row
    if set(result) != set(CAMERAS):
        raise ValueError(f"incomplete six-camera frame: {frame}")
    return result


def domain_for(arm, frame, final_frame):
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    return arm[1] if frame == final_frame else arm[0]


def prepare(config):
    primary = load_json(resolve(config["primary_config"]))
    check_hash(resolve(config["primary_config"]), config["primary_config_sha256"], "primary config")
    window = next(w for w in primary["windows"] if w["id"] == config["window"])
    frames = window["frames"]
    if frames != config["frames"] or len(frames) < 4:
        raise ValueError("window frames differ from frozen reference")
    real_report = load_json(resolve(window["real_receiver_report"]))
    check_hash(resolve(window["real_receiver_report"]), window["real_receiver_report_sha256"], "real report")
    real_root = Path(real_report["source"]["root"])
    real_manifest_path = Path(real_report["source"]["archive_manifest"])
    check_hash(real_manifest_path, real_report["source"]["archive_manifest_sha256"], "real manifest")
    real_manifest = load_json(real_manifest_path)
    members = {row["output_relative_path"]: row for row in real_manifest["members"]}
    source_meta_path = resolve(primary["source_metadata"])
    check_hash(source_meta_path, primary["source_metadata_sha256"], "source metadata")
    source_meta = load_json(source_meta_path)
    sim_root = resolve(window["current_input_root"])
    sim_manifest_path = sim_root / "assembled_render_manifest.json"
    sim_manifest = load_json(sim_manifest_path)
    sim_meta_path = sim_root / "metadata_exact_pose_window.json"
    check_hash(sim_meta_path, sim_manifest["output_metadata_sha256"], "sim metadata")
    if sim_manifest["metadata_source_sha256"] != primary["source_metadata_sha256"]:
        raise ValueError("render metadata source mismatch")
    sim_meta = load_json(sim_meta_path)
    sim_rows = {(r["frame_index"], r["camera"]): r for r in sim_manifest["images"]}
    image_rows = []
    for frame in frames:
        source_records, sim_records = records(source_meta, frame), records(sim_meta, frame)
        if len({r["timestamp"] for r in source_records.values()}) != 1:
            raise ValueError("source cameras do not share a declared timestamp")
        for camera in CAMERAS:
            sr, sm = source_records[camera], sim_records[camera]
            if {k: v for k, v in sr.items() if k != "rgb_path"} != {
                k: v for k, v in sm.items() if k != "rgb_path"
            }:
                raise ValueError(f"non-RGB metadata mismatch at {frame}/{camera}")
            for domain in ("R", "S"):
                row = {"frame": frame, "camera": camera, "domain": domain}
                if domain == "R":
                    relative = sr["rgb_path"].removeprefix("./")
                    path = real_root / relative
                    member = members[relative]
                    check_hash(path, member["sha256"], "real archive member")
                    payload = path.read_bytes()
                    if len(payload) != member["uncompressed_size"] or zlib.crc32(payload) != member["crc32"]:
                        raise ValueError("real archive member CRC/length mismatch")
                    row["archive_member"] = member["name"]
                else:
                    rendered = sim_rows[(frame, camera)]
                    path = Path(rendered["destination"])
                    check_hash(path, rendered["destination_sha256"], "sim image")
                    report_path = Path(rendered["render_report"])
                    check_hash(report_path, rendered["render_report_sha256"], "render report")
                    report = load_json(report_path)
                    factual = report["variants"]["factual"]
                    if report["frame_index"] != frame or factual["metadata_sha256"] != primary["source_metadata_sha256"]:
                        raise ValueError("render frame/metadata mismatch")
                    if factual["native_dynamics_omitted"]:
                        raise ValueError("native actor omitted from factual input")
                    check_hash(path, factual["camera_results"][camera]["render_sha256"], "render RGB")
                with Image.open(path) as im:
                    im.load()
                    if im.size != (sr["width"], sr["height"]):
                        raise ValueError(f"wrong image dimensions: {path}")
                row.update(path=str(path.resolve()), sha256=sha256(path), width=sr["width"], height=sr["height"])
                image_rows.append(row)

    # Compare the two actual metadata records, without fitting a pose correction.
    released_path = resolve(config["released_metadata"])
    released = load_json(released_path)
    # Their first front-camera frames define the gauge comparison; not a physical calibration.
    initial = np.asarray(records(source_meta, 0)["CAM_FRONT"]["camtoworld"])
    released_initial = np.asarray(records(released, 0)["CAM_FRONT"]["camtoworld"])
    alignment = released_initial @ np.linalg.inv(initial)
    pose_differences = []
    for frame in frames:
        for camera in CAMERAS:
            a = alignment @ np.asarray(records(source_meta, frame)[camera]["camtoworld"])
            b = np.asarray(records(released, frame)[camera]["camtoworld"])
            angle = np.degrees(np.arccos(np.clip((np.trace(a[:3, :3].T @ b[:3, :3]) - 1) / 2, -1, 1)))
            pose_differences.append({"frame": frame, "camera": camera,
                                     "translation_m": float(np.linalg.norm(a[:3, 3] - b[:3, 3])),
                                     "rotation_deg": float(angle)})
    output = resolve(config["qualification_root"])
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.mkdir(parents=True)
    lookup = {(r["domain"], r["frame"], r["camera"]): r for r in image_rows}
    arm_rows = []
    for arm in ARMS:
        arm_root = output / "inputs" / arm
        linked = []
        for frame in frames:
            domain = domain_for(arm, frame, frames[-1])
            for camera, record in records(source_meta, frame).items():
                row = lookup[(domain, frame, camera)]
                destination = arm_root / record["rgb_path"].removeprefix("./")
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(row["path"], destination)
                linked.append({**row, "linked_path": str(destination)})
        arm_manifest = arm_root / "input_manifest.json"
        write_json(arm_manifest, {"arm": arm, "images": linked,
                                  "boundary": "Only RGB origin changes; logical frame indices and metadata do not."})
        arm_rows.append({"arm": arm, "root": str(arm_root), "manifest": str(arm_manifest),
                         "manifest_sha256": sha256(arm_manifest)})
    result = {
        "prepared_utc": now(), "host": platform.node(), "frames": frames,
        "unique_image_count": len(image_rows), "images": image_rows, "arms": arm_rows,
        "declared_non_rgb_metadata_equal": True,
        "real_manifest": str(real_manifest_path), "real_manifest_sha256": sha256(real_manifest_path),
        "sim_manifest": str(sim_manifest_path), "sim_manifest_sha256": sha256(sim_manifest_path),
        "released_metadata": str(released_path), "released_metadata_sha256": sha256(released_path),
        "source_metadata": str(source_meta_path), "source_metadata_sha256": sha256(source_meta_path),
        "initial_gauge_alignment": alignment.tolist(), "pose_record_differences": pose_differences,
        "source_gate_decision": "down-weighted",
        "unresolved": ["original nuScenes sample identities and calibrated sensor/CAN records",
                       "physical pairing of initial poses with optimized reconstruction coordinates",
                       "checkpoint training/split provenance", "externally qualified task tolerance"],
        "allowed_claim": "fixed-receiver input-domain/history diagnostic; no physical real-sim equivalence",
    }
    write_json(output / "qualification.json", result)
    print(json.dumps({k: result[k] for k in ("host", "unique_image_count", "source_gate_decision", "allowed_claim")}))


def verify_inputs(config):
    path = resolve(config["qualification_root"]) / "qualification.json"
    check_hash(path, config["qualification_sha256"], "qualification")
    qualification = load_json(path)
    for row in qualification["images"]:
        check_hash(Path(row["path"]), row["sha256"], "input image")
    for arm in qualification["arms"]:
        check_hash(Path(arm["manifest"]), arm["manifest_sha256"], "arm manifest")
        for row in load_json(arm["manifest"])["images"]:
            check_hash(Path(row["linked_path"]), row["sha256"], "linked input")
    for key in ("source_metadata", "released_metadata", "real_manifest", "sim_manifest"):
        check_hash(Path(qualification[key]), qualification[key + "_sha256"], key)
    return qualification


def run(config, config_path):
    from compare_fixed_trajectory_receiver_process_repeat import directory_tree_sha256, verify_live_primary_assets
    primary = load_json(resolve(config["primary_config"]))
    check_hash(resolve(config["primary_config"]), config["primary_config_sha256"], "primary config")
    check_hash(Path(__file__), config["runner_sha256"], "probe runner")
    qualification = verify_inputs(config)
    # Keep the old regression immutable; explicitly freeze reviewed current helpers here.
    if {r["path"] for r in config["current_receiver_helpers"]} != {
        r["path"] for r in primary["transitive_helper_sha256"]
    }:
        raise ValueError("receiver helper path set changed")
    primary["transitive_helper_sha256"] = config["current_receiver_helpers"]
    verify_live_primary_assets(primary)
    if directory_tree_sha256(resolve(primary["runtime_deps"])) != config["runtime_deps_tree"]:
        raise ValueError("runtime dependency tree changed")
    if git(ROOT, "status", "--short"):
        raise ValueError("commit the frozen experiment before GPU execution")
    output = resolve(config["receiver_root"])
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.mkdir(parents=True)
    manifest = {"status": "running", "started_utc": now(), "host": platform.node(), "cwd": str(ROOT),
                "branch": git(ROOT, "branch", "--show-current"), "preregistration_commit": git(ROOT, "rev-parse", "HEAD"),
                "config_sha256": sha256(config_path), "commands": [],
                "gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.used", "--format=csv,noheader"], text=True).strip()}
    write_json(output / "run_manifest.json", manifest)
    print(json.dumps(manifest), flush=True)
    try:
        for arm in qualification["arms"]:
            label = arm["arm"]
            command = [str(resolve(primary["runtime_python"])), str(resolve(primary["receiver_adapter"])),
                       "--sparsedrive-root", str(resolve(primary["sparsedrive_root"])),
                       "--checkpoint", str(resolve(primary["checkpoint"])),
                       "--runtime-deps", str(resolve(primary["runtime_deps"])),
                       "--anchor-dir", str(resolve(primary["anchor_dir"])),
                       "--source-root", arm["root"], "--metadata", qualification["source_metadata"],
                       "--source-archive-manifest", arm["manifest"],
                       "--metadata-archive-manifest", str(resolve(primary["metadata_archive_manifest"])),
                       "--calibration-reference-run", str(resolve(primary["calibration_reference_run"]))]
            for frame in config["frames"]:
                command.extend(("--frame-index", str(frame)))
            command.extend(("--baseline-only", "--output", str(output / label)))
            item = {"arm": label, "command": command, "started_utc": now(), "returncode": None}
            manifest["commands"].append(item)
            write_json(output / "run_manifest.json", manifest)
            print(f"starting {label}: seven-frame prefix + current frame, two reset replicates", flush=True)
            with (output / f"{label}.log").open("w") as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                started = time.monotonic()
                while process.poll() is None:
                    if time.monotonic() - started > 900:
                        process.kill()
                        process.wait()
                        raise TimeoutError(f"{label}: exceeded 900 seconds; inspect {log.name}")
                    time.sleep(1)
            item.update(returncode=process.returncode, finished_utc=now())
            write_json(output / "run_manifest.json", manifest)
            if process.returncode:
                raise RuntimeError(f"{label} exited {process.returncode}; inspect {output / (label + '.log')}")
            print(f"completed {label}", flush=True)
        verify_inputs(config)
        verify_live_primary_assets(primary)
        if directory_tree_sha256(resolve(primary["runtime_deps"])) != config["runtime_deps_tree"]:
            raise ValueError("runtime dependency tree changed during execution")
        manifest["status"] = "completed"
    except BaseException as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        manifest["finished_utc"] = now()
        write_json(output / "run_manifest.json", manifest)


def contrast(plans, coefficients, epsilon):
    """Finite replicate envelope plus a declared numerical guard, not a confidence interval."""
    lower = np.zeros((6, 2), dtype=np.float64)
    upper = lower.copy()
    center = lower.copy()
    for arm, coefficient in coefficients.items():
        values = np.asarray(plans[arm], dtype=np.float64)
        if values.shape != (2, 6, 2) or not np.isfinite(values).all():
            raise ValueError("each arm must have two finite six-waypoint plans")
        lo, hi = values.min(axis=0) - epsilon, values.max(axis=0) + epsilon
        lower += coefficient * (lo if coefficient > 0 else hi)
        upper += coefficient * (hi if coefficient > 0 else lo)
        center += coefficient * values.mean(axis=0)
    excluded = (lower > 0) | (upper < 0)
    distance = np.where(lower > 0, lower, np.where(upper < 0, -upper, 0))
    return {"coefficients": coefficients, "mean_contrast_xy_m": center.tolist(),
            "lower_xy_m": lower.tolist(), "upper_xy_m": upper.tolist(),
            "max_abs_mean_m": float(np.abs(center).max()),
            "max_coordinate_distance_from_zero_m": float(distance.max()),
            "numerically_resolved_nonzero": bool(excluded.any()),
            "endpoint_forward_mean_m": float(center[-1, 1]),
            "endpoint_euclidean_mean_m": float(np.linalg.norm(center[-1]))}


def analyze(config):
    import torch
    from compare_fixed_trajectory_receiver_regression import recompute_reset_repeat, report_native_plan_difference
    qualification = verify_inputs(config)
    output = resolve(config["analysis_root"])
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    root = resolve(config["receiver_root"])
    manifest = load_json(root / "run_manifest.json")
    if manifest["status"] != "completed":
        raise ValueError("receiver run is incomplete")
    epsilon = float(config["numerical_guard_per_output_m"])
    reports, plans, repeat_checks, artifacts = {}, {}, {}, []
    for arm in ARMS:
        path = root / arm / "sparsedrive_real_source_qualification.json"
        report = load_json(path)
        native_path = root / arm / "native_outputs.pt"
        check_hash(native_path, report["artifacts"]["native_outputs_sha256"], "native output")
        native = torch.load(native_path, map_location="cpu")
        if report_native_plan_difference(report, native) != 0:
            raise ValueError("JSON plan differs from native tensor")
        repeat = recompute_reset_repeat(native)
        repeat_checks[arm] = {"max_abs_plan_difference_m": repeat, "within_guard": repeat <= epsilon}
        if not report["qualification"]["all_native_outputs_finite"]:
            raise ValueError("nonfinite native output")
        if not report["qualification"]["baseline_plans_non_degenerate"]:
            raise ValueError("degenerate baseline plan")
        reports[arm] = report
        plans[arm] = [np.asarray(report[v]["frames"][-1]["native"]["final_planning_values"]) for v in VARIANTS]
        artifacts.extend({"path": str(p), "sha256": sha256(p)} for p in (path, native_path))
    # All 64 delivered frames: exact non-image contracts and intended per-camera bytes.
    lookup = {(r["domain"], r["frame"], r["camera"]): r for r in qualification["images"]}
    contracts_checked = 0
    for arm, report in reports.items():
        for variant in VARIANTS:
            rows = report[variant]["frames"]
            if [r["source_frame_index"] for r in rows] != config["frames"]:
                raise ValueError("receiver logical frame mismatch")
            for position, row in enumerate(rows):
                reference = reports["RR"]["baseline"]["frames"][position]
                if normalized_input_contract(row["input_contract"]) != normalized_input_contract(reference["input_contract"]):
                    raise ValueError("non-image receiver contract changed")
                frame = row["source_frame_index"]
                domain = domain_for(arm, frame, config["frames"][-1])
                for camera in row["input_contract"]["camera_inputs"]:
                    expected = lookup[(domain, frame, camera["camera"])]
                    check_hash(Path(camera["image_path"]), expected["sha256"], "delivered input")
                contracts_checked += 1
    prefix_checks = {}
    for history, arms in (("R", ("RR", "RS")), ("S", ("SR", "SS"))):
        sequences = [reports[a][v]["frames"][:-1] for a in arms for v in VARIANTS]
        delta = max(float(np.max(np.abs(
            np.asarray(x[i]["native"]["final_planning_values"]) -
            np.asarray(y[i]["native"]["final_planning_values"]))))
            for x, y in itertools.combinations(sequences, 2) for i in range(len(config["frames"]) - 1))
        prefix_checks[history] = {"max_pairwise_plan_difference_m": delta, "within_guard": delta <= epsilon}
    eligible = all(c["within_guard"] for c in (*repeat_checks.values(), *prefix_checks.values()))
    coefficients = {
        "current_effect_given_real_history": {"RS": 1, "RR": -1},
        "current_effect_given_sim_history": {"SS": 1, "SR": -1},
        "history_effect_given_real_current": {"SR": 1, "RR": -1},
        "history_effect_given_sim_current": {"SS": 1, "RS": -1},
        "total_domain_effect": {"SS": 1, "RR": -1},
        "interaction": {"SS": 1, "SR": -1, "RS": -1, "RR": 1},
    }
    contrasts = {name: contrast(plans, c, epsilon) for name, c in coefficients.items()}
    summary = {
        "experiment_id": config["experiment_id"], "analyzed_utc": now(),
        "preregistration_commit": manifest["preregistration_commit"], "input_qualification": qualification["source_gate_decision"],
        "final_frame": config["frames"][-1], "prefix_frame_count": len(config["frames"]) - 1,
        "receiver_frame_contracts_checked": contracts_checked, "repeat_checks": repeat_checks,
        "prefix_checks": prefix_checks, "numerical_attribution_eligible": eligible,
        "numerical_guard_per_output_m": epsilon, "contrasts": contrasts,
        "arms": {a: {"plans_xy_m": [p.tolist() for p in plans[a]],
                      "planning_selection": [reports[a][v]["frames"][-1]["planning_selection"] for v in VARIANTS]} for a in ARMS},
        "candidate_claims": {
            "current_only_explains_output_at_numerical_resolution": {
                "decision": "rejected" if eligible and any(contrasts[n]["numerically_resolved_nonzero"] for n in (
                    "history_effect_given_real_current", "history_effect_given_sim_current")) else "down-weighted"},
            "history_only_explains_output_at_numerical_resolution": {
                "decision": "rejected" if eligible and any(contrasts[n]["numerically_resolved_nonzero"] for n in (
                    "current_effect_given_real_history", "current_effect_given_sim_history")) else "down-weighted"},
            "additive_history_current_explanation_at_numerical_resolution": {
                "decision": "rejected" if eligible and contrasts["interaction"]["numerically_resolved_nonzero"] else "down-weighted"},
        },
        "artifacts": artifacts, "overall_decision": "down-weighted",
        "boundary": "Input-domain diagnostic at a fixed factual path; mixed histories are diagnostic interventions, not physical sensor recordings. No accuracy, task safety, measured delay, or closed-loop equivalence claim.",
    }
    output.mkdir(parents=True)
    write_json(output / "analysis.json", summary)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    colors = dict(zip(ARMS, ("#2878b5", "#f28e2b", "#59a14f", "#b45a9a")))
    for arm in ARMS:
        mean = np.mean(plans[arm], axis=0)
        axes[0].plot(np.r_[0, mean[:, 0]], np.r_[0, mean[:, 1]], "o-", label=arm, color=colors[arm])
        axes[1].plot(np.arange(1, 7) * 0.5, (mean - np.mean(plans["RR"], axis=0))[:, 1], "o-", label=arm, color=colors[arm])
    axes[0].set(xlabel="Right (m)", ylabel="Forward (m)", title="Final-frame native plans; frame 54")
    axes[0].axis("equal")
    axes[1].set(xlabel="Plan horizon (s)", ylabel="Forward difference from RR (m)", title="History/current RGB origins: RR, RS, SR, SS")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend()
    fig.suptitle("Input-domain diagnosis; physical pairing and task tolerance remain unqualified", fontsize=10)
    fig.tight_layout()
    fig.savefig(output / "history_current_plans.png", dpi=160)
    plt.close(fig)
    print(json.dumps({"eligible": eligible, "contrasts": {n: {k: r[k] for k in ("max_abs_mean_m", "endpoint_forward_mean_m", "numerically_resolved_nonzero")} for n, r in contrasts.items()}}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run", "analyze"))
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = load_json(config_path)
    if args.phase == "run":
        run(config, config_path)
    else:
        {"prepare": prepare, "analyze": analyze}[args.phase](config)


if __name__ == "__main__":
    main()
