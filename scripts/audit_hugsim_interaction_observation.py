#!/usr/bin/env python3
"""Audit CF-I state-to-rendered-observation transport on frozen controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def git_blob(root: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def first_qualified(indices: list[int], values: list[int], threshold: int) -> int | None:
    return next((index for index, value in zip(indices, values, strict=True) if value >= threshold), None)


def shifted_mask(mask: Any, horizontal_pixels: int) -> Any:
    import numpy as np

    shifted = np.zeros_like(mask)
    if horizontal_pixels >= 0:
        shifted[:, horizontal_pixels:] = mask[:, : mask.shape[1] - horizontal_pixels]
    else:
        shifted[:, :horizontal_pixels] = mask[:, -horizontal_pixels:]
    return shifted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hugsim-root", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    hugsim_root = args.hugsim_root.resolve()
    prereg_path = args.preregistration.resolve()
    output_dir = args.output_dir.resolve()
    audit_output = args.audit_output.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite {output_dir}")

    prereg = json.loads(prereg_path.read_text())
    revision = git_revision(hugsim_root)
    if revision != prereg["hugsim_commit"]:
        raise RuntimeError("HUGSIM revision differs from preregistration")
    resolved_prereg_commit = subprocess.run(
        ["git", "rev-parse", "--verify", f"{args.preregistration_commit}^{{commit}}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    prereg_relative = str(prereg_path.relative_to(repo_root))
    if git_blob(repo_root, resolved_prereg_commit, prereg_relative) != prereg_path.read_bytes():
        raise RuntimeError("preregistration differs from committed frozen version")
    script_relative = "scripts/audit_hugsim_interaction_observation.py"
    scenario_relative = prereg["scenario"]["relative_path"]
    if hashlib.sha256(git_blob(repo_root, resolved_prereg_commit, script_relative)).hexdigest() != prereg["analysis_script_sha256"]:
        raise RuntimeError("analysis script differs from preregistered hash")
    if hashlib.sha256(git_blob(repo_root, resolved_prereg_commit, scenario_relative)).hexdigest() != prereg["scenario"]["sha256"]:
        raise RuntimeError("scenario differs from preregistered hash")
    for asset in prereg["assets"].values():
        path = Path(asset["path"])
        if sha256(path) != asset["sha256"]:
            raise RuntimeError(f"asset hash mismatch: {path}")

    trace_path = Path(prereg["parent_trace"]["path"])
    if sha256(trace_path) != prereg["parent_trace"]["sha256"]:
        raise RuntimeError("parent trace hash mismatch")
    traces = json.loads(trace_path.read_text())

    output_dir.mkdir(parents=True)
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cf-i-obs")
    os.chdir(hugsim_root)
    sys.path[:0] = [str(hugsim_root), str(hugsim_root / "sim"), str(repo_root / "scripts")]

    import cv2
    import gymnasium
    import hugsim_env  # noqa: F401
    import matplotlib.pyplot as plt
    import numpy as np
    import torch
    from omegaconf import OmegaConf
    from scene.cameras import Camera
    from sim.utils.plan import planner

    from analyze_hugsim_occlusion_metamorphic import projected_mask

    scenario_path = repo_root / scenario_relative
    base_path = Path(prereg["assets"]["base_config"]["path"])
    camera_path = Path(prereg["assets"]["camera_config"]["path"])
    kinematic_path = Path(prereg["assets"]["kinematic_config"]["path"])
    scenario_config = OmegaConf.load(scenario_path)
    base_config = OmegaConf.load(base_path)
    camera_config = OmegaConf.load(camera_path)
    kinematic_config = OmegaConf.load(kinematic_path)
    kinematic_config.dt = float(prereg["execution"]["aligned_dt_seconds"])
    cfg = OmegaConf.merge(
        {"scenario": scenario_config},
        {"base": base_config},
        {"camera": camera_config},
        {"kinematic": kinematic_config},
    )
    local_model_path = Path(cfg.base.model_base) / cfg.scenario.scene_name
    cfg.update(OmegaConf.load(local_model_path / "cfg.yaml"))
    cfg.model_path = str(local_model_path)
    cfg.source_path = str(local_model_path)

    env = gymnasium.make("hugsim_env/HUGSim-v0", cfg=cfg, output=str(output_dir))
    env.reset()
    simulation = env.unwrapped

    selected_indices = [int(value) for value in prereg["execution"]["selected_indices"]]
    causal_indices = [int(value) for value in prereg["execution"]["causal_indices"]]
    conditions = tuple(prereg["execution"]["conditions"])
    state_tolerance = float(prereg["thresholds"]["state_replay_l2"])
    position_tolerance = float(prereg["thresholds"]["render_position_m"])
    yaw_tolerance = float(prereg["thresholds"]["render_yaw_rad"])
    difference_threshold = int(prereg["thresholds"]["rgb_difference"])
    minimum_pixels = int(prereg["thresholds"]["minimum_support_pixels"])
    minimum_depth = float(prereg["thresholds"]["minimum_projection_depth_m"])
    dilation_pixels = int(prereg["thresholds"]["projection_dilation_pixels"])
    minimum_inside_fraction = float(prereg["thresholds"]["minimum_support_inside_fraction"])
    negative_shift_pixels = int(prereg["controls"]["projection_shift_pixels"])
    temporal_shift = int(prereg["controls"]["observation_timestamp_shift_frames"])
    aligned_dt = float(prereg["execution"]["aligned_dt_seconds"])

    camera_names = tuple(simulation.cam_params.keys())
    expected_camera = prereg["controls"]["expected_visible_camera"]
    actor_model_root = Path(prereg["assets"]["vehicle_model"]["path"]).parent
    plan_list = [[
        0.0,
        -15.0,
        -0.3,
        0.0,
        3.0,
        str(actor_model_root),
        "AttackPlanner",
        {"pred_steps": 20, "ATTACK_FREQ": 1, "best_k": 1},
    ]]

    rendered: dict[str, dict[int, dict[str, Any]]] = {name: {} for name in conditions}
    replay_errors: list[float] = []
    transform_rows: list[dict[str, Any]] = []
    membership_rows: list[dict[str, Any]] = []
    spatial_rows: list[dict[str, Any]] = []
    shared_dynamics = Camera.__init__.__defaults__[-1]
    if not isinstance(shared_dynamics, dict):
        raise RuntimeError("unexpected Camera dynamics default; corrective control is unavailable")

    def clear_shared_camera_dynamics() -> None:
        """Prevent one paired render from contaminating the next Camera instance."""
        shared_dynamics.clear()

    for condition in conditions:
        loop = planner(
            plan_list,
            scene_path=str(local_model_path),
            unified_map=None,
            ground=simulation.ground_model,
            dt=aligned_dt,
        )
        torch.manual_seed(int(prereg["execution"]["torch_seed"]))
        for index, row in enumerate(traces[condition]):
            ego_state = np.asarray(row["ego_state"], dtype=np.float64)
            simulation.vab = ego_state[:2].copy()
            simulation.vr = np.asarray([0.0, ego_state[2], 0.0], dtype=np.float64)
            simulation.velo = float(ego_state[3])
            simulation.timestamp = index * aligned_dt

            observed_before = loop.stats["agent_0"][[0, 1, 3, 4]].detach().cpu().numpy()
            expected_before = np.asarray(row["actor_before"], dtype=np.float64)
            replay_errors.append(float(np.linalg.norm(observed_before - expected_before)))
            planning = loop.plan_traj(simulation.timestamp, simulation.ego_state)
            observed_after = loop.stats["agent_0"][[0, 1, 3, 4]].detach().cpu().numpy()
            expected_after = np.asarray(row["actor_after"], dtype=np.float64)
            replay_errors.append(float(np.linalg.norm(observed_after - expected_after)))

            if index not in selected_indices:
                continue
            simulation.planner = loop
            simulation.render_kwargs["planning"] = planning
            clear_shared_camera_dynamics()
            actor_observation = simulation._get_obs()
            actor_info = simulation._get_info()
            simulation.render_kwargs["planning"] = [{}, {}]
            clear_shared_camera_dynamics()
            empty_observation = simulation._get_obs()
            simulation.render_kwargs["planning"] = planning

            observed_box = np.asarray(actor_info["obj_boxes"][0], dtype=np.float64)
            observed_position = np.asarray([-observed_box[1], observed_box[0]])
            position_error = float(np.linalg.norm(observed_position - expected_after[:2]))
            yaw_error = float(abs(math.atan2(math.sin(observed_box[6] - expected_after[2]), math.cos(observed_box[6] - expected_after[2]))))
            transform_rows.append({
                "condition": condition,
                "index": index,
                "position_error_m": position_error,
                "yaw_error_rad": yaw_error,
            })

            rendered[condition][index] = {"rgb": actor_observation["rgb"]}
            for camera in camera_names:
                actor_rgb = np.asarray(actor_observation["rgb"][camera])
                empty_rgb = np.asarray(empty_observation["rgb"][camera])
                support = np.max(np.abs(actor_rgb.astype(np.int16) - empty_rgb.astype(np.int16)), axis=2) > difference_threshold
                try:
                    projection, _ = projected_mask(
                        actor_info,
                        observed_box,
                        camera,
                        actor_rgb.shape[:2],
                        minimum_depth,
                    )
                except ValueError:
                    projection = np.zeros(actor_rgb.shape[:2], dtype=bool)
                projected_pixels = int(np.count_nonzero(projection))
                support_pixels = int(np.count_nonzero(support))
                expected_visible = camera == expected_camera
                observed_visible = support_pixels >= minimum_pixels
                projected_visible = projected_pixels >= minimum_pixels
                membership_rows.append({
                    "condition": condition,
                    "index": index,
                    "camera": camera,
                    "expected_visible": expected_visible,
                    "projected_visible": projected_visible,
                    "observed_visible": observed_visible,
                    "projected_pixels": projected_pixels,
                    "support_pixels": support_pixels,
                    "passed": expected_visible == projected_visible == observed_visible,
                })
                if expected_visible:
                    kernel_width = 2 * dilation_pixels + 1
                    kernel = np.ones((kernel_width, kernel_width), dtype=np.uint8)
                    dilated = cv2.dilate(projection.astype(np.uint8), kernel).astype(bool)
                    shifted = shifted_mask(projection, negative_shift_pixels)
                    shifted_dilated = cv2.dilate(shifted.astype(np.uint8), kernel).astype(bool)
                    inside_fraction = float(np.count_nonzero(support & dilated) / max(support_pixels, 1))
                    shifted_inside_fraction = float(np.count_nonzero(support & shifted_dilated) / max(support_pixels, 1))
                    spatial_rows.append({
                        "condition": condition,
                        "index": index,
                        "support_inside_dilated_projection_fraction": inside_fraction,
                        "support_inside_shifted_projection_fraction": shifted_inside_fraction,
                        "positive_passed": support_pixels >= minimum_pixels and inside_fraction >= minimum_inside_fraction,
                        "shifted_negative_passed": support_pixels >= minimum_pixels and shifted_inside_fraction >= minimum_inside_fraction,
                    })

    env.close()

    replay_max = max(replay_errors)
    transform_positive = all(
        row["position_error_m"] <= position_tolerance and row["yaw_error_rad"] <= yaw_tolerance
        for row in transform_rows
    ) and replay_max <= state_tolerance
    transform_shift_errors = []
    for condition in conditions:
        for index in causal_indices[:-1]:
            row = next(item for item in transform_rows if item["condition"] == condition and item["index"] == index)
            current_box_position = np.asarray(traces[condition][index]["actor_after"][:2])
            next_position = np.asarray(traces[condition][index + 1]["actor_after"][:2])
            transform_shift_errors.append(float(np.linalg.norm(current_box_position - next_position)) - row["position_error_m"])
    transform_negative_rejected = max(transform_shift_errors) > position_tolerance
    o1 = transform_positive and transform_negative_rejected

    membership_positive = all(row["passed"] for row in membership_rows)
    rotated_mismatches = sum(
        row["observed_visible"] != (row["camera"] == prereg["controls"]["rotated_visible_camera"])
        for row in membership_rows
    )
    membership_negative_rejected = rotated_mismatches > 0
    o2 = membership_positive and membership_negative_rejected

    spatial_positive = all(row["positive_passed"] for row in spatial_rows)
    spatial_negative_rejected = any(not row["shifted_negative_passed"] for row in spatial_rows)
    o3 = spatial_positive and spatial_negative_rejected

    causal_counts = []
    for index in causal_indices:
        changed = 0
        for camera in camera_names:
            baseline = rendered["aligned_baseline"][index]["rgb"][camera]
            treatment = rendered["aligned_treatment"][index]["rgb"][camera]
            changed += int(np.count_nonzero(np.max(np.abs(baseline.astype(np.int16) - treatment.astype(np.int16)), axis=2) > difference_threshold))
        causal_counts.append(changed)
    causal_first = first_qualified(causal_indices, causal_counts, minimum_pixels)
    shifted_indices = [index for index in causal_indices if index + temporal_shift in rendered["aligned_treatment"]]
    shifted_counts = []
    for index in shifted_indices:
        changed = 0
        for camera in camera_names:
            baseline = rendered["aligned_baseline"][index]["rgb"][camera]
            treatment = rendered["aligned_treatment"][index + temporal_shift]["rgb"][camera]
            changed += int(np.count_nonzero(np.max(np.abs(baseline.astype(np.int16) - treatment.astype(np.int16)), axis=2) > difference_threshold))
        shifted_counts.append(changed)
    shifted_first = first_qualified(shifted_indices, shifted_counts, minimum_pixels)
    declared_stimulus = int(prereg["execution"]["declared_stimulus_index"])
    causal_positive = causal_first is not None and declared_stimulus <= causal_first <= causal_indices[-1]
    causal_negative_rejected = shifted_first is not None and shifted_first < declared_stimulus
    o4 = causal_positive and causal_negative_rejected

    decisions = {"CF-I-O1": o1, "CF-I-O2": o2, "CF-I-O3": o3, "CF-I-O4": o4}
    indicator_results = {
        "CF-I-O1": {
            "max_state_replay_l2": replay_max,
            "max_render_position_error_m": max(row["position_error_m"] for row in transform_rows),
            "max_render_yaw_error_rad": max(row["yaw_error_rad"] for row in transform_rows),
            "shifted_state_negative_decision": "rejected" if transform_negative_rejected else "accepted",
            "control_discrimination": "accepted" if o1 else "rejected",
        },
        "CF-I-O2": {
            "qualified_camera_rows": len(membership_rows),
            "positive_mismatch_count": sum(not row["passed"] for row in membership_rows),
            "rotated_mapping_mismatch_count": int(rotated_mismatches),
            "rotated_mapping_decision": "rejected" if membership_negative_rejected else "accepted",
            "control_discrimination": "accepted" if o2 else "rejected",
        },
        "CF-I-O3": {
            "minimum_support_inside_fraction": min(row["support_inside_dilated_projection_fraction"] for row in spatial_rows),
            "maximum_shifted_projection_inside_fraction": max(row["support_inside_shifted_projection_fraction"] for row in spatial_rows),
            "shifted_projection_decision": "rejected" if spatial_negative_rejected else "accepted",
            "control_discrimination": "accepted" if o3 else "rejected",
        },
        "CF-I-O4": {
            "declared_stimulus_index": declared_stimulus,
            "actual_first_observation_divergence_index": causal_first,
            "actual_changed_pixels": dict(zip(causal_indices, causal_counts, strict=True)),
            "shifted_first_divergence_index": shifted_first,
            "shifted_changed_pixels": dict(zip(shifted_indices, shifted_counts, strict=True)),
            "shifted_pairing_decision": "rejected" if causal_negative_rejected else "accepted",
            "control_discrimination": "accepted" if o4 else "rejected",
        },
    }

    prereg_ref = str(prereg_path.relative_to(repo_root))
    planner_ref = f"HUGSIM@{revision}:sim/utils/plan.py:planner.plan_traj"
    render_ref = f"HUGSIM@{revision}:sim/hugsim_env/envs/hug_sim.py:HUGSimEnv._get_obs"
    claims = {
        "cf_i_o1_state_to_render_transform_discrimination": "accepted" if o1 else "rejected",
        "cf_i_o2_camera_membership_discrimination": "accepted" if o2 else "rejected",
        "cf_i_o3_projection_localization_discrimination": "accepted" if o3 else "rejected",
        "cf_i_o4_observation_onset_discrimination": "accepted" if o4 else "rejected",
    }
    findings = {}
    labels = {
        "CF-I-O1": ("planner state to render transform", "state and transform controls discriminate", f"replay={replay_max:.3e} m; pass={o1}"),
        "CF-I-O2": ("projected camera membership", "CAM_BACK positive and five camera negatives discriminate", f"positive mismatches={sum(not row['passed'] for row in membership_rows)}; rotated mismatches={rotated_mismatches}"),
        "CF-I-O3": ("RGB support localization", "support lies in the independently projected actor region", f"minimum inside={min(row['support_inside_dilated_projection_fraction'] for row in spatial_rows):.4f}; pass={o3}"),
        "CF-I-O4": ("rendered causal onset", "no observation divergence before state cause and shifted pairing is rejected", f"actual first={causal_first}; shifted first={shifted_first}; pass={o4}"),
    }
    rejected_contexts = {}
    for index, (indicator, passed) in enumerate(decisions.items(), start=1):
        component, expected, observed = labels[indicator]
        finding_id = f"{prereg['experiment_id']}-D{index}"
        findings[finding_id] = {
            "component": component,
            "expected": expected,
            "observed": observed,
            "expectation_met": passed,
            "implication": "qualified only for frozen state-to-observation transport" if passed else "observation transport is not qualified",
            "evidence_decision": "accepted",
            "evidence_refs": [prereg_ref, planner_ref, render_ref],
        }
        claim_id = tuple(claims)[index - 1]
        if not passed:
            rejected_contexts[claim_id] = {
                "tested": True,
                "rejection_basis": "contradicted_by_evidence",
                "reason": f"{indicator} did not discriminate its frozen positive and negative controls",
                "evidence_refs": [prereg_ref, planner_ref, render_ref],
                "diagnostic_finding": finding_id,
            }

    audit = {
        "experiment_id": prereg["experiment_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hugsim_commit": revision,
        "preregistration": prereg_ref,
        "indicator_results": indicator_results,
        "credibility": {
            "evidence_decision": "down-weighted",
            "claim_decisions": claims,
            "rejected_claim_contexts": rejected_contexts,
        },
        "diagnostic_findings": findings,
        "measurement_chain": {
            "shared_camera_dynamics_cleared_before_each_paired_render": True,
            "reason": "HUGSIM Camera uses a mutable default dynamics dictionary that render mutates in place",
        },
        "strongest_allowed_claim": (
            "Within the frozen scene-0383 rear-actor window, planner state, camera membership, projected RGB location, and causal onset transport consistently into HUGSIM rendered observations. This does not establish real-sensor or AD-response credibility."
            if all(decisions.values())
            else "Only individually accepted indicator decisions may be retained; complete state-to-observation transport is not qualified."
        ),
        "stop_rule_triggered": not all(decisions.values()),
    }
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(audit, indent=2) + "\n")
    (output_dir / "interaction_observation_measurements.json").write_text(json.dumps({
        "transform_rows": transform_rows,
        "membership_rows": membership_rows,
        "spatial_rows": spatial_rows,
    }, indent=2) + "\n")

    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8), constrained_layout=True)
    axes[0].bar(["state replay", "render position", "render yaw"], [replay_max, max(row["position_error_m"] for row in transform_rows), max(row["yaw_error_rad"] for row in transform_rows)])
    axes[0].set_yscale("symlog", linthresh=1e-8)
    axes[0].set_title("O1 state-to-transform error")
    support_by_camera = {camera: [row["support_pixels"] for row in membership_rows if row["camera"] == camera] for camera in camera_names}
    axes[1].bar(range(len(camera_names)), [float(np.median(support_by_camera[camera])) for camera in camera_names])
    axes[1].set_xticks(range(len(camera_names)), [name.replace("CAM_", "") for name in camera_names], rotation=35, ha="right")
    axes[1].set_title("O2 median actor RGB support")
    axes[1].set_ylabel("changed pixels")
    axes[2].plot(causal_indices, causal_counts, marker="o", label="actual pairing")
    axes[2].plot(shifted_indices, shifted_counts, marker="o", label=f"{temporal_shift}-frame early label")
    axes[2].axvline(declared_stimulus, color="black", linestyle="--", label="declared cause")
    axes[2].set_title("O4 observation divergence")
    axes[2].set_xlabel("declared frame index")
    axes[2].set_ylabel("changed pixels, six cameras")
    axes[2].legend()
    figure.suptitle(f"{prereg['experiment_id']} state-to-observation transport")
    figure.savefig(output_dir / "interaction_observation_summary.png", dpi=160)
    plt.close(figure)

    contact, contact_axes = plt.subplots(2, len(selected_indices), figsize=(3.4 * len(selected_indices), 5.8), constrained_layout=True)
    for row_index, condition in enumerate(conditions):
        for column, index in enumerate(selected_indices):
            image = rendered[condition][index]["rgb"][expected_camera]
            contact_axes[row_index, column].imshow(image)
            contact_axes[row_index, column].set_title(f"{condition.replace('aligned_', '')} i={index}")
            contact_axes[row_index, column].axis("off")
    contact.suptitle("Receiver-facing CAM_BACK inputs")
    contact.savefig(output_dir / "interaction_observation_cam_back_contact_sheet.png", dpi=120)
    plt.close(contact)

    print(json.dumps(audit, indent=2))
    return 0 if all(decisions.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
