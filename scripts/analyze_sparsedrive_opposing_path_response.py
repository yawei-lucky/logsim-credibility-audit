#!/usr/bin/env python3
"""Analyze preregistered SparseDrive response to scene-0041 phase stimuli."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import shape

from analyze_hugsim_conflict_region_contract import (
    classify_boolean_occupancy,
    interpolate_path,
    oriented_footprint,
    signed_occupancy_gap,
)
from make_hugsim_actor_placement_metadata import reference_model_path
from render_hugsim_exact_source_pose import select_camera_records, sha256_file
from run_sparsedrive_real_source import model_to_world


CONDITIONS = ("separated", "boundary", "overlap")


def git_blob(repo: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def verify_preregistration(
    repo: Path, commit: str, preregistration_path: Path
) -> str:
    resolved = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{commit}}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative = str(preregistration_path.relative_to(repo))
    if git_blob(repo, resolved, relative) != preregistration_path.read_bytes():
        raise ValueError("preregistration differs from committed version")
    return resolved


def plan_to_world_xz(plan_right_forward: np.ndarray, ego_model_to_world: np.ndarray) -> np.ndarray:
    plan = np.asarray(plan_right_forward, dtype=np.float64)
    pose = np.asarray(ego_model_to_world, dtype=np.float64)
    if plan.ndim != 2 or plan.shape[1] != 2 or pose.shape != (4, 4):
        raise ValueError("invalid plan or ego pose")
    local = np.column_stack([plan, np.zeros(len(plan)), np.ones(len(plan))])
    world = (pose @ local.T).T
    return world[:, [0, 2]]


def branched_plan_path(
    reference_times: np.ndarray,
    reference_points: np.ndarray,
    anchor_time: float,
    anchor_point: np.ndarray,
    plan_world_points: np.ndarray,
    plan_step_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    keep = reference_times < anchor_time - 1e-9
    times = np.concatenate(
        [
            reference_times[keep],
            np.asarray([anchor_time]),
            anchor_time + plan_step_s * np.arange(1, len(plan_world_points) + 1),
        ]
    )
    points = np.vstack([reference_points[keep], anchor_point, plan_world_points])
    if np.any(np.diff(times) <= 0.0):
        raise ValueError("branched plan timestamps are not increasing")
    return times, points


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--receiver-report", type=Path, required=True)
    parser.add_argument("--dynamic-manifest", type=Path, required=True)
    parser.add_argument("--conflict-contract", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--calibration-reference-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    preregistration_path = args.preregistration.expanduser().resolve()
    receiver_path = args.receiver_report.expanduser().resolve()
    dynamic_manifest_path = args.dynamic_manifest.expanduser().resolve()
    conflict_contract_path = args.conflict_contract.expanduser().resolve()
    source_metadata_path = args.source_metadata.expanduser().resolve()
    calibration_run = args.calibration_reference_run.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (
        preregistration_path,
        receiver_path,
        dynamic_manifest_path,
        conflict_contract_path,
        source_metadata_path,
        calibration_run / "infos.pkl",
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output: {output}")

    preregistration_commit = verify_preregistration(
        repo, args.preregistration_commit, preregistration_path
    )
    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    receiver = json.loads(receiver_path.read_text(encoding="utf-8"))
    dynamic_manifest = json.loads(dynamic_manifest_path.read_text(encoding="utf-8"))
    conflict_contract = json.loads(conflict_contract_path.read_text(encoding="utf-8"))
    source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
    if receiver["preregistration_sha256"] != sha256_file(preregistration_path):
        raise ValueError("receiver used a different preregistration")
    if not receiver["qualification"]["all_replicates_within_tolerance"]:
        raise ValueError("receiver repeats are not qualified")
    if not receiver["qualification"]["held_fixed_command"]:
        raise ValueError("receiver command was not held fixed")
    reference_contracts = receiver["runs"]["separated"]["replicate_1"]["frames"]
    for condition in CONDITIONS[1:]:
        candidate_contracts = receiver["runs"][condition]["replicate_1"]["frames"]
        if len(candidate_contracts) != len(reference_contracts):
            raise ValueError("receiver frame count differs across conditions")
        for reference_frame, candidate_frame in zip(
            reference_contracts, candidate_contracts, strict=True
        ):
            for key in ("timestamp_s", "front_to_world", "ego_status_10d", "command_one_hot_right_left_straight"):
                if reference_frame["input_contract"][key] != candidate_frame["input_contract"][key]:
                    raise ValueError(f"held-fixed receiver field differs: {key}")

    with (calibration_run / "infos.pkl").open("rb") as stream:
        infos = pickle.load(stream)
    front_l2c = np.asarray(infos[0]["cam_params"]["CAM_FRONT"]["l2c"], dtype=float)
    reference = reference_model_path(source_metadata, front_l2c)
    reference_times = np.asarray([row["timestamp_s"] for row in reference])
    reference_points = np.asarray(
        [[row["world_x_m"], row["world_z_m"]] for row in reference]
    )
    anchor_frame = int(preregistration["receiver"]["evaluation_source_frame"])
    anchor_time = float(
        select_camera_records(source_metadata, anchor_frame)["CAM_FRONT"]["timestamp"]
    )
    anchor_pose = model_to_world(source_metadata, anchor_frame, front_l2c)
    anchor_point = anchor_pose[[0, 2], 3]
    horizon_s = float(preregistration["receiver"]["planning_horizon_s"])
    plan_step_s = horizon_s / 6.0
    sample_dt = float(
        conflict_contract["motion_and_yaw"]["sampling_dt_s"]
    )
    sample_times = np.arange(0.0, anchor_time + horizon_s + sample_dt * 0.5, sample_dt)
    region_geojson = Path(conflict_contract["conflict_region"]["polygon_geojson"])
    region = shape(json.loads(region_geojson.read_text(encoding="utf-8"))["geometry"])
    ego_width, ego_length = (
        float(value) for value in conflict_contract["footprints"]["ego_width_length_m"]
    )
    actor_width, actor_length, _ = (
        float(value) for value in dynamic_manifest["actor"]["dimensions_wlh_m"]
    )

    rows = {}
    for condition in CONDITIONS:
        run = receiver["runs"][condition]
        plan = np.asarray(run["final_plan_replicate_1_m"], dtype=float)
        plan_world = plan_to_world_xz(plan, anchor_pose)
        branch_times, branch_points = branched_plan_path(
            reference_times,
            reference_points,
            anchor_time,
            anchor_point,
            plan_world,
            plan_step_s,
        )
        dense_plan, plan_headings = interpolate_path(
            branch_times, branch_points, sample_times
        )
        plan_flags = np.asarray(
            [
                oriented_footprint(point, heading, ego_width, ego_length).intersects(region)
                for point, heading in zip(dense_plan, plan_headings, strict=True)
            ]
        )
        plan_occupancy = classify_boolean_occupancy(sample_times, plan_flags)
        observed_interval_count = len(
            plan_occupancy.get(
                "observed_intervals",
                [plan_occupancy["interval"]] if plan_occupancy["interval"] else [],
            )
        )

        dynamic_metadata = json.loads(
            Path(dynamic_manifest["conditions"][condition]["metadata"]).read_text(
                encoding="utf-8"
            )
        )
        actor_frame_indices = [int(value) for value in dynamic_manifest["frame_indices"]]
        actor_times = np.asarray(
            [float(dynamic_manifest["timestamps_s"][str(index)]) for index in actor_frame_indices]
        )
        actor_points = np.asarray(
            [
                np.asarray(
                    select_camera_records(dynamic_metadata, index)["CAM_FRONT"]["dynamics"]
                    [dynamic_manifest["actor"]["id"]],
                    dtype=float,
                )[[0, 2], 3]
                for index in actor_frame_indices
            ]
        )
        full_actor_sample_times = np.arange(
            actor_times[0], actor_times[-1] + sample_dt * 0.5, sample_dt
        )
        full_actor_sample_times = full_actor_sample_times[
            full_actor_sample_times <= actor_times[-1] + 1e-12
        ]
        dense_actor, actor_headings = interpolate_path(
            actor_times, actor_points, full_actor_sample_times
        )
        actor_flags = np.asarray(
            [
                oriented_footprint(point, heading, actor_width, actor_length).intersects(region)
                for point, heading in zip(dense_actor, actor_headings, strict=True)
            ]
        )
        actor_occupancy = classify_boolean_occupancy(
            full_actor_sample_times, actor_flags
        )
        plan_gap = signed_occupancy_gap(plan_occupancy, actor_occupancy)
        public_gap = float(preregistration["conditions"][condition]["expected_signed_occupancy_gap_s"])
        rows[condition] = {
            "public_reference_signed_gap_s": public_gap,
            "plan_world_xz_m": plan_world.tolist(),
            "plan_occupancy": plan_occupancy,
            "plan_observed_interval_count": observed_interval_count,
            "multiple_plan_occupancy_intervals_observed": observed_interval_count > 1,
            "actor_occupancy": actor_occupancy,
            "plan_signed_occupancy_gap_s": plan_gap,
            "conflict_mitigation_delta_s": (
                float(plan_gap - public_gap) if plan_gap is not None else None
            ),
            "final_forward_m": float(run["replicate_1"]["frames"][-1]["plan_geometry"]["final_forward_m"]),
            "selected_mode_index": int(run["replicate_1"]["frames"][-1]["planning_selection"]["selected_mode_index"]),
            "repeat_max_abs_plan_difference_m": float(run["repeat_max_abs_plan_difference_m"]),
        }

    repeat_envelope = max(row["repeat_max_abs_plan_difference_m"] for row in rows.values())
    pair_differences = {}
    for left, right in zip(CONDITIONS[:-1], CONDITIONS[1:], strict=True):
        left_plan = np.asarray(receiver["runs"][left]["final_plan_replicate_1_m"])
        right_plan = np.asarray(receiver["runs"][right]["final_plan_replicate_1_m"])
        difference = float(np.max(np.abs(right_plan - left_plan)))
        pair_differences[f"{left}_vs_{right}"] = {
            "maximum_absolute_plan_difference_m": difference,
            "exceeds_repeat_envelope": difference > repeat_envelope,
        }
    finite_mitigations = all(
        rows[condition]["conflict_mitigation_delta_s"] is not None for condition in CONDITIONS
    )
    expected_mitigation_order = None
    if finite_mitigations:
        values = [rows[condition]["conflict_mitigation_delta_s"] for condition in CONDITIONS]
        expected_mitigation_order = values[0] <= values[1] <= values[2]
    forward_values = [rows[condition]["final_forward_m"] for condition in CONDITIONS]
    raw_forward_expected = forward_values[2] <= forward_values[1] <= forward_values[0]
    same_mode = len({rows[condition]["selected_mode_index"] for condition in CONDITIONS}) == 1
    multiple_intervals_observed = any(
        rows[condition]["multiple_plan_occupancy_intervals_observed"]
        for condition in CONDITIONS
    )

    if finite_mitigations:
        task_decision = "accepted" if expected_mitigation_order else "rejected"
        task_reason = "finite conflict mitigation order evaluated"
    else:
        task_decision = "down-weighted"
        task_reason = (
            "the 3 s plan occupancies are right-censored; separated and overlap "
            "also show multiple short occupancy intervals, so preregistered finite c fails closed"
        )

    output.mkdir(parents=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    region_x, region_z = region.exterior.xy
    axes[0].fill(region_x, region_z, color="#ef8a62", alpha=0.35, label="C")
    axes[0].plot(reference_points[:, 0], reference_points[:, 1], color="#555555", label="released path")
    colors = {"separated": "#1b9e77", "boundary": "#d95f02", "overlap": "#7570b3"}
    for condition in CONDITIONS:
        plan_world = np.asarray(rows[condition]["plan_world_xz_m"])
        axes[0].plot(
            np.r_[anchor_point[0], plan_world[:, 0]],
            np.r_[anchor_point[1], plan_world[:, 1]],
            marker="o",
            label=condition,
            color=colors[condition],
        )
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].set_xlabel("world x (m)")
    axes[0].set_ylabel("world z (m)")
    axes[0].set_title("SparseDrive selected plans in conflict geometry")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    axes[1].bar(CONDITIONS, forward_values, color=[colors[name] for name in CONDITIONS])
    axes[1].set_ylabel("3 s final forward progress (m)")
    axes[1].set_title("Auxiliary progress; not the conflict verdict")
    axes[1].grid(axis="y", alpha=0.25)
    visualization = output / "sparsedrive_opposing_path_response.png"
    figure.savefig(visualization, dpi=180)
    plt.close(figure)

    result = {
        "audit_id": "sparsedrive_scene0041_opposing_path_response_001",
        "preregistration": str(preregistration_path),
        "preregistration_commit": preregistration_commit,
        "receiver_report": str(receiver_path),
        "receiver_report_sha256": sha256_file(receiver_path),
        "conditions": rows,
        "pairwise_plan_response": pair_differences,
        "repeat_envelope_m": repeat_envelope,
        "same_selected_mode_across_conditions": same_mode,
        "held_fixed_timestamp_pose_ego_status_and_command": True,
        "multiple_plan_occupancy_intervals_observed": multiple_intervals_observed,
        "raw_final_forward_order_expected": raw_forward_expected,
        "finite_conflict_mitigation_order_available": finite_mitigations,
        "conflict_mitigation_order_expected": expected_mitigation_order,
        "task_response_decision": task_decision,
        "task_response_reason": task_reason,
        "auxiliary_directional_diagnostic": {
            "decision": "rejected" if not raw_forward_expected and same_mode else "down-weighted",
            "finding": (
                "The overlap plan advances farther than the boundary plan despite "
                "the same selected mode; final forward progress is auxiliary and "
                "cannot replace the unavailable finite conflict verdict."
            ),
        },
        "visualization": str(visualization),
        "visualization_sha256": sha256_file(visualization),
        "claim_boundary": (
            "The result concerns one fixed receiver and one designed simulator-side "
            "phase grid. It does not establish real-world response correctness, "
            "physical safety, collision probability or general HUGSIM credibility."
        ),
    }
    result_path = output / "sparsedrive_opposing_path_response.json"
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
